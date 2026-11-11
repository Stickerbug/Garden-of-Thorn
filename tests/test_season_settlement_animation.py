# -*- coding: utf-8 -*-
"""赛季结算三页动画的数据、入口与已读键。"""

import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import app
import db
import rank_system


ROOT = Path(__file__).resolve().parents[1]
SEASON_JS = (ROOT / 'static/js/season-settlement.js').read_text(encoding='utf-8')
SEASON_CSS = (ROOT / 'static/css/season-settlement.css').read_text(encoding='utf-8')
DIRECT_NODE = Path.home() / 'AppData/Local/Programs/Kimi/resources/resources/runtime/node.cmd'
NODE = str(DIRECT_NODE) if DIRECT_NODE.exists() else shutil.which('node')


class SeasonSettlementDataTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'season-settlement.sqlite3')
        db.init_db()
        self.user, error = db.create_user('SeasonReview', 'Aa1!aaaa')
        self.assertIsNone(error)
        self.other, error = db.create_user('SeasonOpponent', 'Aa1!aaaa')
        self.assertIsNone(error)
        self.uid = int(self.user['id'])
        self.other_uid = int(self.other['id'])
        self.month = '2026-10'
        self.season_id = f'{db.GR_RANKED_ERA}-S202610'
        self.before = rank_system.rank_payload(25, 120)
        self.before.update({
            'absolute_points': rank_system.tier_to_absolute(25, 120),
            'season_ranked_games': 100,
            'season_name': 'S3',
        })
        self.after = rank_system.rank_payload(24, 10)
        with db.get_db_connection() as conn:
            conn.execute(
                '''
                INSERT INTO rank_monthly_settlements (
                    month_key, user_id, before_json, after_json, dew_granted, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    self.month, self.uid, json.dumps(self.before), json.dumps(self.after),
                    self.before['absolute_points'] * 10 + 10000, db.utc_now(),
                ),
            )
            rows = []
            for match_id, mode, participants, team_a, team_b, winner_side, is_draw in (
                (101, '1v1', [self.uid, self.other_uid], [self.uid], [self.other_uid], 0, 0),
                (102, '1v1', [self.other_uid, self.uid], [self.other_uid], [self.uid], 0, 0),
                (103, '2v2', [self.uid, self.other_uid, 9001, 9002], [self.uid, self.other_uid], [9001, 9002], None, 1),
                (104, '1v1', [self.other_uid, 9003], [self.other_uid], [9003], 0, 0),
            ):
                rows.append((
                    match_id, self.season_id, mode, db.utc_now(),
                    json.dumps(participants), json.dumps(team_a), json.dumps(team_b),
                    winner_side, is_draw, '{}', '{}', '{}', '{}',
                ))
            conn.executemany(
                '''
                INSERT INTO gr_match_results (
                    match_id, season_id, mode, played_at, participant_ids_json,
                    team_a_ids_json, team_b_ids_json, winner_side, is_draw,
                    total_deltas_json, season_deltas_json, before_json, after_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                rows,
            )
            conn.commit()
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_stats_rank_changes_and_both_rewards(self):
        result = db.get_rank_season_settlement(self.uid)
        self.assertEqual(result['season_name'], 'S3')
        self.assertEqual(result['stats']['games'], 3)
        self.assertEqual(result['stats']['wins'], 1)
        self.assertEqual(result['stats']['losses'], 1)
        self.assertEqual(result['stats']['draws'], 1)
        self.assertEqual(result['stats']['win_rate'], 33.3)
        self.assertEqual(result['stats']['modes']['1v1']['games'], 2)
        self.assertEqual(result['stats']['modes']['2v2']['games'], 1)
        self.assertEqual(result['stats']['modes']['2v2']['draws'], 1)
        self.assertEqual(result['changes']['subtiers'], -1)
        self.assertEqual(result['changes']['points'], 10 - 120)
        self.assertEqual(
            result['changes']['absolute_points'],
            rank_system.tier_to_absolute(24, 10) - self.before['absolute_points'],
        )
        self.assertTrue(result['rewards']['base']['earned'])
        self.assertEqual(
            result['rewards']['base']['dew'],
            5000 + self.before['absolute_points'] * 10,
        )
        self.assertTrue(result['rewards']['advanced']['earned'])
        self.assertEqual(result['rewards']['advanced']['dew'], 5000)
        self.assertEqual(result['rewards']['advanced']['title'], 'S3赛季参与者')

    def test_partial_participation_shows_remaining_games(self):
        before = dict(self.before, season_ranked_games=40)
        with db.get_db_connection() as conn:
            conn.execute(
                'UPDATE rank_monthly_settlements SET before_json = ? WHERE user_id = ?',
                (json.dumps(before), self.uid),
            )
            conn.commit()
        rewards = db.get_rank_season_settlement(self.uid)['rewards']
        self.assertTrue(rewards['base']['earned'])
        self.assertEqual(rewards['base']['remaining_games'], 0)
        self.assertFalse(rewards['advanced']['earned'])
        self.assertEqual(rewards['advanced']['remaining_games'], 60)
        self.assertEqual(rewards['advanced']['dew'], 0)

    def test_zero_ranked_games_keeps_both_rewards_locked(self):
        before = dict(self.before, season_ranked_games=0)
        with db.get_db_connection() as conn:
            conn.execute(
                'UPDATE rank_monthly_settlements SET before_json = ? WHERE user_id = ?',
                (json.dumps(before), self.uid),
            )
            conn.commit()
        result = db.get_rank_season_settlement(self.uid)
        # 旧计分记录只用于数据回顾，奖励局数以结算快照为准。
        self.assertEqual(result['stats']['games'], 3)
        self.assertFalse(result['rewards']['base']['earned'])
        self.assertEqual(result['rewards']['base']['remaining_games'], 30)
        self.assertEqual(result['rewards']['base']['dew'], 0)
        self.assertFalse(result['rewards']['advanced']['earned'])
        self.assertEqual(result['rewards']['advanced']['remaining_games'], 100)

    def test_api_is_private_and_returns_current_users_settlement(self):
        with mock.patch.object(app, '_current_account_user', return_value=None):
            response = self.client.get('/api/rank/season-settlement')
            self.assertEqual(response.status_code, 401)
        with mock.patch.object(app, '_current_account_user', return_value=self.user):
            response = self.client.get('/api/rank/season-settlement')
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload['success'])
            self.assertEqual(payload['user_id'], self.uid)
            self.assertEqual(payload['settlement']['month_key'], self.month)
        with mock.patch.object(app, '_current_account_user', return_value=self.other):
            payload = self.client.get('/api/rank/season-settlement').get_json()
            self.assertTrue(payload['success'])
            self.assertIsNone(payload['settlement'])

    def test_legacy_settlement_table_gains_animation_seen_column(self):
        with db.get_db_connection() as conn:
            conn.execute('DROP TABLE rank_monthly_settlements')
            conn.execute(
                '''
                CREATE TABLE rank_monthly_settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    month_key TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    dew_granted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE (month_key, user_id)
                )
                '''
            )
            conn.commit()
        db.init_db()
        with db.get_db_connection() as conn:
            columns = {
                row['name'] for row in conn.execute(
                    'PRAGMA table_info(rank_monthly_settlements)'
                ).fetchall()
            }
        self.assertIn('animation_seen_at', columns)

    def test_animation_claim_is_persistent_and_idempotent(self):
        self.assertEqual(db.get_rank_season_settlement(self.uid)['animation_seen_at'], '')
        with mock.patch.object(app, '_current_account_user', return_value=self.user):
            first = self.client.post(
                '/api/rank/season-settlement/seen', json={'month_key': self.month},
            )
            second = self.client.post(
                '/api/rank/season-settlement/seen', json={'month_key': self.month},
            )
            invalid = self.client.post(
                '/api/rank/season-settlement/seen', json={'month_key': 'S3'},
            )
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.get_json()['claimed'])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.get_json()['claimed'])
        self.assertEqual(invalid.status_code, 400)
        with mock.patch.object(app, '_current_account_user', return_value=self.other):
            other = self.client.post(
                '/api/rank/season-settlement/seen', json={'month_key': self.month},
            )
        self.assertFalse(other.get_json()['claimed'])
        self.assertNotEqual(db.get_rank_season_settlement(self.uid)['animation_seen_at'], '')
        with db.get_db_connection() as conn:
            claimed_rows = conn.execute(
                "SELECT COUNT(*) FROM rank_monthly_settlements "
                "WHERE user_id = ? AND month_key = ? AND animation_seen_at != ''",
                (self.uid, self.month),
            ).fetchone()[0]
        self.assertEqual(claimed_rows, 1)


class SeasonSettlementFrontendTests(unittest.TestCase):
    def test_three_pages_navigation_seen_state_and_template_are_present(self):
        for marker in (
            'function renderReview', 'function renderRank', 'function renderRewards',
            'function navigate', 'function markSeen', 'storageKey',
            'rewards.base', 'rewards.advanced', 'prefers-reduced-motion',
            'mask-position', 'session.switchTimer', 'animation_seen_at',
            '/api/rank/season-settlement/seen', 'claim.claimed',
            "method: 'POST'", 'await show(data, { force: true })',
        ):
            self.assertIn(marker, SEASON_JS if marker not in ('mask-position',) else SEASON_CSS)
        self.assertNotIn('setInterval', SEASON_JS)
        template = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        self.assertIn('/static/css/season-settlement.css', template)
        self.assertIn('/static/js/season-settlement.js', template)
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        self.assertEqual(game.count('window.GtnSeasonSettlement.refresh()'), 3)
        self.assertIn('season-settlement-once-1', (ROOT / 'static_version.txt').read_text(encoding='utf-8'))

    def test_season_settlement_uses_a_light_palette(self):
        self.assertIn('--ssr-bg: #f7f4ea', SEASON_CSS)
        self.assertIn('--ssr-panel: #fffdf7', SEASON_CSS)
        self.assertIn('--ssr-cream: #40334f', SEASON_CSS)
        self.assertIn('background: linear-gradient(145deg, #fffdf7, #f4edfa);', SEASON_CSS)
        self.assertIn('background: #a4c865;', SEASON_CSS)
        self.assertIn('-season-settlement-light-1', (ROOT / 'static_version.txt').read_text(encoding='utf-8'))

    @unittest.skipIf(NODE is None, '需要 Node.js 检查结算载荷与已读键')
    def test_payload_normalization_and_seen_key_include_user_and_season(self):
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.cjs', prefix='tmp_season_settlement_',
            dir=ROOT, delete=False, encoding='utf-8',
        ) as script_file:
            script_path = Path(script_file.name)
            script_file.write(
                'const vm = require("vm");\n'
                'globalThis.window = { __GTN_DISABLE_SEASON_SETTLEMENT__: true, setTimeout: () => 0 };\n'
                'globalThis.document = { documentElement: { lang: "zh" } };\n'
                f'vm.runInThisContext({json.dumps(SEASON_JS)});\n'
                'const raw = { user_id: 7, month_key: "2026-10", season_name: "S3", before: {}, after: {} };\n'
                'const data = window.GtnSeasonSettlement.normalizeSettlement(raw);\n'
                'console.log(JSON.stringify({ data, key: window.GtnSeasonSettlement.storageKey(data), invalid: window.GtnSeasonSettlement.normalizeSettlement({}) }));\n'
            )
        try:
            completed = subprocess.run(
                [NODE, str(script_path)], capture_output=True,
                text=True, encoding='utf-8', timeout=5,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        finally:
            script_path.unlink(missing_ok=True)
        result = json.loads(completed.stdout)
        self.assertEqual(result['data']['stats']['win_rate'], 0)
        self.assertEqual(result['data']['stats']['modes']['1v1']['games'], 0)
        self.assertEqual(result['key'], 'gtn-season-settlement-seen-v1:7:2026-10')
        self.assertIsNone(result['invalid'])


if __name__ == '__main__':
    unittest.main()
