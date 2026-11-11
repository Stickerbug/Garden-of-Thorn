# -*- coding: utf-8 -*-
"""长期奖励动画与对应的真实发放数据。"""

import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import app
import db
import leisure_ticket


ROOT = Path(__file__).resolve().parents[1]
REWARD_JS = (ROOT / 'static/js/reward-animation.js').read_text(encoding='utf-8')
REWARD_CSS = (ROOT / 'static/css/reward-animation.css').read_text(encoding='utf-8')
GAME_JS = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
LEISURE_JS = (ROOT / 'static/js/leisure-ticket.js').read_text(encoding='utf-8')
DIRECT_NODE = Path.home() / 'AppData/Local/Programs/Kimi/resources/resources/runtime/node.cmd'
NODE = str(DIRECT_NODE) if DIRECT_NODE.exists() else shutil.which('node')


class RewardAnimationContractTests(unittest.TestCase):
    def test_all_four_svg_assets_are_valid(self):
        for relative in (
            'static/assets/ui-icons/thorn-dew.svg',
            'static/assets/leisure/tickets.svg',
            'static/assets/rewards/score-insurance-card.svg',
            'static/assets/rewards/double-card.svg',
        ):
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            root = ET.parse(path).getroot()
            self.assertTrue(root.attrib.get('viewBox'), relative)
            self.assertIn(relative, REWARD_JS)

    def test_pages_load_animation_component(self):
        for relative in (
            'templates/index.html', 'templates/minigame_2048.html',
            'templates/minigame_suika.html', 'templates/story.html', 'templates/afdian.html',
        ):
            page = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn('/static/css/reward-animation.css', page, relative)
            self.assertIn('/static/js/reward-animation.js', page, relative)

    def test_animation_has_particles_reveal_and_reduced_motion(self):
        self.assertIn('requestAnimationFrame', REWARD_JS)
        self.assertIn('prefers-reduced-motion: reduce', REWARD_CSS)
        self.assertIn('clip-path', REWARD_CSS)
        self.assertIn('normalizeItems', REWARD_JS)
        self.assertIn('rewardItemsFromSnapshot', REWARD_JS)
        self.assertIn('TEXT_ART_KINDS', REWARD_JS)
        self.assertIn('gra-text-art', REWARD_CSS)
        self.assertIn('close(session, true)', REWARD_JS)
        self.assertIn("['title', 'skin'].includes(item.kind)", REWARD_JS)
        self.assertIn("['mod', 'character', 'unlock'].includes(item.kind)", REWARD_JS)
        self.assertIn("? '获得'", REWARD_JS)
        self.assertIn("? '解锁'", REWARD_JS)

    def test_animation_uses_a_light_palette(self):
        self.assertIn('--gra-bg: #f7f4ea', REWARD_CSS)
        self.assertIn('--gra-ink: #40334f', REWARD_CSS)
        self.assertIn('color: var(--gra-ink);', REWARD_CSS)
        self.assertIn('--gra-wipe-lavender: #ddd2f0', REWARD_CSS)
        self.assertIn("['#9dbb55', '#d18bcf', '#dfa07c', '#b6a4d4']", REWARD_JS)

    def test_entry_points_use_actual_reward_payloads(self):
        for marker in (
            'data.checkin_granted',
            'showMatchLongTermRewards(gs)',
            'result.leisure_ticket_awarded',
            'window.GtnRewardAnimation.refresh()',
        ):
            self.assertIn(marker, GAME_JS)
        self.assertIn('window.GtnRewardAnimation.refresh()', LEISURE_JS)
        self.assertNotIn('GtnRewardAnimation.show', GAME_JS)
        self.assertNotIn('GtnRewardAnimation.show', LEISURE_JS)
        pvp_source = (ROOT / 'pvp_economy.py').read_text(encoding='utf-8')
        self.assertIn("'leisure_ticket_awarded': ticket_awards", pvp_source)
        app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn("/api/rewards/status", app_source)
        for key in ("'titles'", "'skins'", "'mods'", "'characters'"):
            self.assertIn(key, app_source)


@unittest.skipIf(NODE is None, '需要 Node.js 检查奖励载荷整理')
class RewardAnimationPayloadTests(unittest.TestCase):
    def test_normalize_items_filters_and_bounds_rewards(self):
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.cjs', prefix='tmp_reward_payload_',
            dir=ROOT, delete=False, encoding='utf-8',
        ) as script_file:
            script_path = Path(script_file.name)
            script_file.write(
                'const vm = require("vm");\n'
                'globalThis.window = { __GTN_DISABLE_REWARD_WATCH__: true };\n'
                'globalThis.document = { documentElement: { lang: "zh" } };\n'
                f'vm.runInThisContext({json.dumps(REWARD_JS)});\n'
                'const items = window.GtnRewardAnimation.normalizeItems([\n'
                '  { kind: "dew", amount: 40.9, reason: "签到" },\n'
                '  { kind: "ticket", amount: 2 },\n'
                '  { kind: "shield", amount: 1 },\n'
                '  { kind: "double", amount: 1 },\n'
                '  { kind: "title", name: "S3参与者" },\n'
                '  { kind: "mod", name: "Ocean Cards Addition" },\n'
                '  { kind: "skin", name: "叶框", image_url: "/static/assets/card-skins/front/leaf.svg" },\n'
                '  { kind: "dew", amount: 0 },\n'
                '  { kind: "unknown", amount: 100 },\n'
                '  null,\n'
                ']);\n'
                'console.log(JSON.stringify(items));\n'
            )
        try:
            try:
                completed = subprocess.run(
                    [NODE, str(script_path)], capture_output=True,
                    text=True, encoding='utf-8', timeout=5,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
                output = completed.stdout
            except subprocess.TimeoutExpired as exc:
                if not exc.stdout:
                    self.fail(f'Node 未返回奖励载荷：{exc.stderr or "无错误输出"}')
                output = exc.stdout
        finally:
            script_path.unlink(missing_ok=True)
        items = json.loads(output)
        self.assertEqual(
            [item['kind'] for item in items],
            ['dew', 'leisure_ticket', 'rank_shield', 'rank_double', 'title', 'mod', 'skin'],
        )
        self.assertEqual([item['amount'] for item in items], [40, 2, 1, 1, 1, 1, 1])
        self.assertEqual(items[0]['reason'], '签到')
        self.assertEqual(items[4]['name'], 'S3参与者')
        self.assertEqual(items[5]['image_url'], '')
        self.assertEqual(items[6]['image_url'], '/static/assets/card-skins/front/leaf.svg')


    def test_snapshot_covers_every_reward_kind_without_replaying(self):
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.cjs', prefix='tmp_reward_snapshot_',
            dir=ROOT, delete=False, encoding='utf-8',
        ) as script_file:
            script_path = Path(script_file.name)
            script_file.write(
                'const vm = require("vm");\n'
                'globalThis.window = { __GTN_DISABLE_REWARD_WATCH__: true };\n'
                'globalThis.document = { documentElement: { lang: "zh" } };\n'
                f'vm.runInThisContext({json.dumps(REWARD_JS)});\n'
                'const previous = { userId: "1", cursor: 10, leisureTickets: 2, rankCards: { shield: 1, double: 0 } };\n'
                'const data = { success: true, user_id: 1, dew_rewards: [\n'
                '  { id: 11, amount: 40, reason: "赛季奖励" },\n'
                '  { id: 12, amount: 100, source_type: "match_reward", reason: "对局奖励" },\n'
                '  { id: 10, amount: 99, reason: "旧奖励" },\n'
                '], leisure_tickets: 4, rank_cards: { shield: { owned: 2 }, double: { owned: 1 } },\n'
                'inventory: { titles: [{ id: "s3", name: "S3参与者" }], skins: [{ id: "leaf", name: "叶框", image_url: "/static/leaf.svg" }], mods: [{ id: "ocean.gtnmod", name: "ocean.gtnmod" }], characters: [{ id: "orbiter", name: "轨道使" }] } };\n'
                'const first = window.GtnRewardAnimation.rewardItemsFromSnapshot(data, previous);\n'
                'const after = { userId: "1", cursor: 12, leisureTickets: 4, rankCards: { shield: 2, double: 1 }, inventory: { titles: ["s3"], skins: ["leaf"], mods: ["ocean.gtnmod"], characters: ["orbiter"] } };\n'
                'const second = window.GtnRewardAnimation.rewardItemsFromSnapshot(data, after);\n'
                'const baseline = window.GtnRewardAnimation.rewardItemsFromSnapshot(data, { userId: null, cursor: null, leisureTickets: 0, rankCards: { shield: 0, double: 0 } });\n'
                'console.log(JSON.stringify({ baseline, first, second }));\n'
            )
        try:
            try:
                completed = subprocess.run(
                    [NODE, str(script_path)], capture_output=True,
                    text=True, encoding='utf-8', timeout=5,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
                output = completed.stdout
            except subprocess.TimeoutExpired as exc:
                if not exc.stdout:
                    self.fail(f'Node 未返回快照结果：{exc.stderr or "无错误输出"}')
                output = exc.stdout
        finally:
            script_path.unlink(missing_ok=True)
        result = json.loads(output)
        self.assertEqual(result['baseline'], [])
        self.assertEqual(result['second'], [])
        self.assertEqual(
            [item['kind'] for item in result['first']],
            ['dew', 'leisure_ticket', 'rank_shield', 'rank_double', 'title', 'skin', 'mod', 'character'],
        )
        self.assertEqual([item['amount'] for item in result['first']], [40, 2, 1, 1, 1, 1, 1, 1])

    def test_disarm_and_activation_switch_do_not_create_card_rewards(self):
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.cjs', prefix='tmp_reward_disarm_',
            dir=ROOT, delete=False, encoding='utf-8',
        ) as script_file:
            script_path = Path(script_file.name)
            script_file.write(
                'const vm = require("vm");\n'
                'globalThis.window = { __GTN_DISABLE_REWARD_WATCH__: true };\n'
                'globalThis.document = { documentElement: { lang: "zh" } };\n'
                f'vm.runInThisContext({json.dumps(REWARD_JS)});\n'
                'const previous = { userId: "1", cursor: 10, leisureTickets: 2, rankCards: { shield: 1, double: 1 } };\n'
                'const makeData = (shield, double) => ({ success: true, user_id: 1, dew_rewards: [], leisure_tickets: 2, rank_cards: { shield, double } });\n'
                'const disarm = window.GtnRewardAnimation.rewardItemsFromSnapshot(makeData({ owned: 1, armed: false }, { owned: 0, armed: false }), previous);\n'
                'const switched = window.GtnRewardAnimation.rewardItemsFromSnapshot(makeData({ owned: 1, armed: false }, { owned: 0, armed: true }), previous);\n'
                'const purchased = window.GtnRewardAnimation.rewardItemsFromSnapshot(makeData({ owned: 2, armed: false }, { owned: 0, armed: true }), previous);\n'
                'console.log(JSON.stringify({ disarm, switched, purchased }));\n'
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
        self.assertEqual(result['disarm'], [])
        self.assertEqual(result['switched'], [])
        self.assertEqual(
            [(item['kind'], item['amount']) for item in result['purchased']],
            [('rank_shield', 1)],
        )


class CheckinRewardPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'reward-animation.sqlite3')
        db.init_db()
        self.user, error = db.create_user('RewardAnim', 'Aa1!aaaa')
        self.assertIsNone(error)

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_successful_checkin_returns_actual_dew_and_ticket_count(self):
        center, error = db.claim_user_daily_checkin(self.user['id'])
        self.assertIsNone(error)
        granted = center.get('checkin_granted') or {}
        self.assertGreater(granted.get('dew', 0), 0)
        self.assertEqual(granted.get('leisure_tickets'), 1)
        self.assertEqual(granted.get('streak_ticket_bonus'), 0)


class RewardStatusApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'reward-status.sqlite3')
        db.init_db()
        self.user, error = db.create_user('RewardAll', 'Aa1!aaaa')
        self.assertIsNone(error)
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_status_returns_new_dew_and_inventory_increments(self):
        with mock.patch.object(app, '_current_account_user', return_value=self.user):
            baseline = self.client.get('/api/rewards/status').get_json()
            self.assertTrue(baseline['success'])
            self.assertEqual(baseline['dew_cursor'], 0)
            self.assertEqual(baseline['dew_rewards'], [])

            with db.get_db_connection() as conn:
                conn.executemany(
                    '''
                    INSERT INTO user_currency_transactions (
                        user_id, currency, free_delta, paid_delta, reason,
                        source_type, source_id, balance_free_after,
                        balance_paid_after, created_at
                    ) VALUES (?, 'thorn_dew', ?, ?, ?, 'test_reward', ?, 0, 0, ?)
                    ''',
                    [
                        (self.user['id'], 100, 0, '正向奖励', 'one', db.utc_now()),
                        (self.user['id'], -20, 0, '消费', 'spend', db.utc_now()),
                        (self.user['id'], 0, 5, '充值奖励', 'two', db.utc_now()),
                    ],
                )
                conn.commit()

            first = self.client.get('/api/rewards/status?after=0').get_json()
            self.assertEqual([item['amount'] for item in first['dew_rewards']], [100, 5])
            self.assertNotIn('消费', [item['reason'] for item in first['dew_rewards']])
            cursor = first['dew_cursor']
            self.assertGreater(cursor, 0)
            second = self.client.get(f'/api/rewards/status?after={cursor}').get_json()
            self.assertEqual(second['dew_rewards'], [])

            with db.get_db_connection() as conn:
                leisure_ticket.grant_tickets(conn, self.user['id'], 2)
                db._upsert_title_catalog_conn(conn, 'test-title', '测试称号', '#D4AF37')
                db._grant_user_title_conn(
                    conn, self.user['id'], 'test-title',
                    acquired_source='test', acquired_ref='reward-status',
                )
                conn.execute(
                    'INSERT INTO user_card_skins (user_id, skin_id, acquired_source, acquired_ref, acquired_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (self.user['id'], '叶框', 'test', 'reward-status', db.utc_now()),
                )
                conn.execute(
                    'INSERT INTO story_character_plays (user_id, character_id, plays, first_played_at, last_played_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (self.user['id'], 'common_flower', 1, db.utc_now(), db.utc_now()),
                )
                conn.execute(
                    'UPDATE users SET rank_shield_cards = 2, rank_double_cards = 1, rank_tier = 5 WHERE id = ?',
                    (self.user['id'],),
                )
                conn.commit()
            third = self.client.get(f'/api/rewards/status?after={cursor}').get_json()
            self.assertEqual(third['leisure_tickets'], 2)
            self.assertEqual(third['rank_cards']['shield']['owned'], 2)
            self.assertEqual(third['rank_cards']['double']['owned'], 1)
            inventory = third['inventory']
            self.assertIn('test-title', {item['id'] for item in inventory['titles']})
            self.assertIn('叶框', {item['id'] for item in inventory['skins']})
            self.assertIn('Garden Cards Addition.gtnmod', {item['id'] for item in inventory['mods']})
            self.assertIn('common_flower', {item['id'] for item in inventory['characters']})


if __name__ == '__main__':
    unittest.main()
