# -*- coding: utf-8 -*-
"""通关三页结算：逐项分数、历史数据与单次播放认领。"""

import gc
import os
from pathlib import Path
import tempfile
import unittest

import db
import story_history
import story_score


ROOT = Path(__file__).resolve().parents[1]


def completed_state():
    return {
        'phase': 'complete', 'completed': True, 'stage': 3, 'difficulty': 'normal',
        'normal_battles': 10,
        'encounter_history': {'elite': {'garden': [0, 1], 'desert': [0]}},
        'current_node_id': 'n1',
        'map': {'floors': [{'floor': 1, 'nodes': [{'id': 'n1', 'type': 'boss', 'status': 'completed', 'x': 380, 'y': 100}]}], 'edges': []},
        'journey_route': [{'stage': 3, 'floor': 1, 'type': 'boss', 'enemies': [], 'cards_gained': []}],
        'player': {
            'health': 42, 'max_health': 70, 'gold': 25,
            'deck': [{'def_id': 'basic'}, {'def_id': 'rose', 'upgraded': True}],
            'relics': ['r1', 'r2'], 'enchantment_books': [{'id': 'b1'}],
        },
    }


class StoryClearSettlementTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'story-clear.sqlite3')
        db.init_db()
        self.user, error = db.create_user('StoryClearOwner1', 'Passw0rd!xyz')
        assert self.user, error

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_score_breakdown_matches_original_score(self):
        state = completed_state()
        breakdown = story_score.compute_score_breakdown(state, 'normal', 0)
        self.assertEqual(breakdown['base_score'], story_score.compute_base_score(state))
        self.assertEqual(breakdown['base_score'], 621)
        self.assertEqual(breakdown['items']['stages']['points'], 300)
        self.assertEqual(breakdown['items']['all_stages_bonus']['points'], 100)
        self.assertEqual(breakdown['items']['normal_battles']['points'], 100)
        self.assertEqual(breakdown['items']['elite_battles']['points'], 90)
        self.assertEqual(breakdown['items']['gold']['points'], 5)
        self.assertEqual(breakdown['items']['cards']['points'], 6)
        self.assertEqual(breakdown['items']['relics']['points'], 10)
        self.assertEqual(breakdown['items']['enchantment_books']['points'], 10)
        self.assertEqual(breakdown['reward_multiplier'], 1.5)
        self.assertEqual(breakdown['total_score'], 931)
        self.assertEqual(int(breakdown['base_score'] * breakdown['reward_multiplier']), 931)

    def test_sl_multiplier_is_binary_for_restart_floor(self):
        state = completed_state()
        for load_count, expected_multiplier, expected_score in (
            (0, 1.5, 931), (1, 1.0, 621), (3, 1.0, 621), (25, 1.0, 621),
        ):
            with self.subTest(load_count=load_count):
                breakdown = story_score.compute_score_breakdown(state, 'normal', load_count)
                self.assertEqual(breakdown['sl_multiplier'], expected_multiplier)
                self.assertEqual(breakdown['total_score'], expected_score)
                self.assertEqual(
                    story_score.compute_score(state, 'normal', load_count)[0],
                    expected_score,
                )

    def test_restart_floor_action_disables_no_sl_bonus(self):
        state = completed_state()
        run, created = db.create_story_run(self.user['id'], 'seed-restart', 'story-restart-test', state)
        self.assertTrue(created)
        with db.get_db_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute(
                'INSERT INTO story_run_actions '
                '(run_id, sequence, action_id, action_type, payload_json, created_at) '
                "VALUES (?, 1, 'restart-1', 'restart_floor', '{}', '2026-11-01T01:10:00Z')",
                (run['id'],),
            )
            result = story_score.settle_story_clear_conn(
                conn, user_id=self.user['id'], run_id=run['id'], state=state,
            )
            conn.commit()
        self.assertEqual(result['load_count'], 1)
        self.assertEqual(result['total'], 621)
        self.assertEqual(result['golden_multiplier'], 1.0)
        self.assertEqual(result['golden_dew_reward'], 3)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 3)

    def test_golden_reward_uses_stages_not_floors_or_sl_penalty(self):
        state = completed_state()
        state['difficulty'] = 'hard'
        state['journey_route'] = [
            {'stage': index // 16 + 1, 'floor': index % 16 + 1, 'completed': True}
            for index in range(48)
        ]
        expected_balance = 0
        for load_count, expected_reward, expected_multiplier in ((0, 6, 2.25), (3, 4, 1.5)):
            run, created = db.create_story_run(
                self.user['id'], f'seed-golden-{load_count}', f'story-golden-{load_count}', state,
            )
            self.assertTrue(created)
            with db.get_db_connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute(
                    'UPDATE story_runs SET manual_load_count = ? WHERE id = ?',
                    (load_count, run['id']),
                )
                result = story_score.settle_story_clear_conn(
                    conn, user_id=self.user['id'], run_id=run['id'], state=state,
                )
                conn.execute("UPDATE story_runs SET status = 'completed' WHERE id = ?", (run['id'],))
                conn.commit()
            self.assertEqual(result['completed_stages'], 3)
            self.assertEqual(result['golden_multiplier'], expected_multiplier)
            self.assertEqual(result['golden_dew_reward'], expected_reward)
            expected_balance += expected_reward
            self.assertEqual(db.get_user_golden_dew(self.user['id']), expected_balance)
        with db.get_db_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM user_currency_transactions WHERE source_type = 'story_clear_golden_dew'",
            ).fetchone()['n']
        self.assertEqual(count, 2)

    def test_clear_grants_battle_pass_xp(self):
        # 通行证经验（2026-11-11）：Min{1000, ceil(Score/5)}，每周前 3 次 ×3。
        state = completed_state()
        run, _ = db.create_story_run(self.user['id'], 'seed-pass-xp', 'story-pass-xp', state)
        with db.get_db_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            result = story_score.settle_story_clear_conn(
                conn, user_id=self.user['id'], run_id=run['id'], state=state,
            )
            conn.commit()
        import battle_pass
        self.assertGreater(result['xp_gain'], 0)
        self.assertEqual(result['xp_gain'], min(1000, -(-result['total'] // 5)) * 3)
        with db.get_db_connection() as conn:
            row = conn.execute(
                'SELECT xp, multiplier, source FROM battle_pass_xp_ledger WHERE user_id = ? AND source_key = ?',
                (self.user['id'], f'story:{run["id"]}'),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['source'], 'story')
        self.assertEqual(int(row['xp']), result['xp_gain'])
        self.assertEqual(battle_pass.xp_total(db.get_db_connection(), self.user['id']), result['xp_gain'])

    def test_history_detail_and_single_animation_claim(self):
        state = completed_state()
        db.set_dew_gain_modifiers(2.0)
        run, _ = db.create_story_run(self.user['id'], 'seed-clear', 'story-clear-test', state)
        with db.get_db_connection() as conn:
            story_history.record_run_summary_conn(
                conn, run['id'], self.user['id'], state,
                started_at='2026-11-01T01:00:00Z', ended_at='2026-11-01T01:22:05Z', result='victory',
            )
            conn.commit()
            conn.execute('BEGIN IMMEDIATE')
            result = story_score.settle_story_clear_conn(conn, user_id=self.user['id'], run_id=run['id'], state=state)
            conn.commit()
        self.assertEqual(result['total'], 1862)
        self.assertEqual(result['dew_gain_multiplier'], 2.0)
        self.assertEqual(result['completed_stages'], 3)
        self.assertEqual(result['golden_multiplier'], 1.5)
        self.assertEqual(result['golden_dew_reward'], 4)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 4)
        # 结算后调整全局倍率，不改变历史台账记录的实际结算乘数。
        db.set_dew_gain_modifiers(3.0)
        with db.get_db_connection() as conn:
            golden_tx = conn.execute(
                'SELECT currency, free_delta, paid_delta, source_type, source_id, balance_free_after '
                'FROM user_currency_transactions WHERE user_id = ? AND source_type = ?',
                (self.user['id'], 'story_clear_golden_dew'),
            ).fetchall()
            self.assertEqual(len(golden_tx), 1)
            self.assertEqual(dict(golden_tx[0]), {
                'currency': 'golden_dew', 'free_delta': 4, 'paid_delta': 0,
                'source_type': 'story_clear_golden_dew', 'source_id': f"story:{run['id']}",
                'balance_free_after': 4,
            })
            detail = story_history.get_history_detail(conn, self.user['id'], run['id'])
        settlement = detail['settlement']
        self.assertTrue(settlement['recorded'])
        self.assertEqual(settlement['score']['base_score'], 621)
        self.assertEqual(settlement['score']['total_score'], 931)
        self.assertEqual(settlement['raw_total'], 931)
        self.assertEqual(settlement['dew_awarded'], 1862)
        self.assertEqual(settlement['global_adjustment'], 931)
        self.assertEqual(settlement['dew_gain_multiplier'], 2.0)
        self.assertEqual(settlement['completed_stages'], 3)
        self.assertEqual(settlement['golden_multiplier'], 1.5)
        self.assertEqual(settlement['golden_dew_reward'], 4)
        self.assertEqual(settlement['animation_seen_at'], '')
        self.assertEqual(len(detail['deck']), 2)
        self.assertEqual(len(detail['route']['visited']), 1)
        self.assertTrue(detail['maps'])
        with db.get_db_connection() as conn:
            self.assertTrue(story_score.claim_story_clear_settlement_animation(conn, self.user['id'], run['id']))
            self.assertFalse(story_score.claim_story_clear_settlement_animation(conn, self.user['id'], run['id']))
            detail = story_history.get_history_detail(conn, self.user['id'], run['id'])
        self.assertTrue(detail['settlement']['animation_seen_at'])

    @staticmethod
    def _pre_completion_state():
        state = completed_state()
        state['phase'] = 'room'
        state['completed'] = False
        state['content_version'] = 'story-clear-test'
        return state

    def test_repeated_completion_settles_only_once(self):
        run, created = db.create_story_run(
            self.user['id'], 'seed-repeat', 'story-clear-test',
            self._pre_completion_state(),
        )
        self.assertTrue(created)
        next_state = completed_state()
        next_state['content_version'] = 'story-clear-test'
        version = int(run['state_version'])
        for index in (1, 2):
            updated, outcome = db.commit_story_run_action(
                self.user['id'], run['id'], version, f'repeat-{index}',
                'discard_enchantment_book',
                {'book_instance_id': 'seb-00001'},
                next_state,
            )
            self.assertEqual(outcome, 'committed')
            version = int(updated['state_version'])
        with db.get_db_connection() as conn:
            ledger_count = conn.execute(
                'SELECT COUNT(*) AS n FROM story_reward_ledger WHERE run_id = ?',
                (run['id'],),
            ).fetchone()['n']
            thorn_count = conn.execute(
                "SELECT COUNT(*) AS n FROM user_currency_transactions "
                "WHERE source_type = 'story_clear'",
            ).fetchone()['n']
            golden_count = conn.execute(
                "SELECT COUNT(*) AS n FROM user_currency_transactions "
                "WHERE source_type = 'story_clear_golden_dew'",
            ).fetchone()['n']
        self.assertEqual((ledger_count, thorn_count, golden_count), (1, 1, 1))
        self.assertGreater(db.get_user_thorn_dew(self.user['id'])['total'], 0)

    def test_settlement_is_idempotent_for_same_run(self):
        state = completed_state()
        state['content_version'] = 'story-clear-test'
        run, created = db.create_story_run(
            self.user['id'], 'seed-idempotent', 'story-clear-test', state,
        )
        self.assertTrue(created)
        with db.get_db_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            first = story_score.settle_story_clear_conn(
                conn, user_id=self.user['id'], run_id=run['id'], state=state,
            )
            second = story_score.settle_story_clear_conn(
                conn, user_id=self.user['id'], run_id=run['id'], state=state,
            )
            conn.commit()
        self.assertEqual(second['total'], first['total'])
        self.assertEqual(second['golden_dew_reward'], first['golden_dew_reward'])
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], first['total'])
        self.assertEqual(db.get_user_golden_dew(self.user['id']), first['golden_dew_reward'])
        with db.get_db_connection() as conn:
            ledger_count = conn.execute(
                'SELECT COUNT(*) AS n FROM story_reward_ledger WHERE run_id = ?',
                (run['id'],),
            ).fetchone()['n']
        self.assertEqual(ledger_count, 1)

    def test_settlement_failure_rolls_back_completion(self):
        from unittest import mock

        run, created = db.create_story_run(
            self.user['id'], 'seed-settle-fail', 'story-clear-test',
            self._pre_completion_state(),
        )
        self.assertTrue(created)
        next_state = completed_state()
        next_state['content_version'] = 'story-clear-test'
        with mock.patch.object(
            story_score, 'settle_story_clear_conn', side_effect=RuntimeError('boom'),
        ):
            with self.assertRaises(RuntimeError):
                db.commit_story_run_action(
                    self.user['id'], run['id'], int(run['state_version']),
                    'settle-fail-1', 'enter_node', {}, next_state,
                )
        refreshed = db.get_active_story_run(self.user['id'])
        self.assertEqual(int(refreshed['state_version']), 1)
        with db.get_db_connection() as conn:
            action_count = conn.execute(
                'SELECT COUNT(*) AS n FROM story_run_actions WHERE run_id = ?',
                (run['id'],),
            ).fetchone()['n']
            ledger_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'story_reward_ledger'",
            ).fetchone()
            ledger_count = (
                conn.execute(
                    'SELECT COUNT(*) AS n FROM story_reward_ledger WHERE run_id = ?',
                    (run['id'],),
                ).fetchone()['n']
                if ledger_table is not None
                else 0
            )
        self.assertEqual(action_count, 0)
        self.assertEqual(ledger_count, 0)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], 0)

    def test_gold_component_is_capped_at_400(self):
        state = completed_state()
        state['player']['gold'] = 10_000_000
        breakdown = story_score.compute_score_breakdown(state, 'normal', 0)
        self.assertEqual(breakdown['items']['gold']['points'], 400)
        # 300(幕) + 100(全通) + 100(小怪) + 90(精英) + 400(金币) + 6(卡) + 10(天赋) + 10(书)
        self.assertEqual(breakdown['base_score'], 1016)
        self.assertEqual(breakdown['total_score'], 1524)
        state['player']['gold'] = 25
        self.assertEqual(
            story_score.compute_score_breakdown(state, 'normal', 0)['items']['gold']['points'],
            5,
        )

    def test_mysterious_person_damage_uses_sl_flag(self):
        import story_engine

        state = completed_state()
        no_sl = story_engine._mysterious_person_damage(state)
        state['sl_used'] = True
        used_sl = story_engine._mysterious_person_damage(state)
        self.assertEqual(no_sl, 931)
        self.assertEqual(used_sl, 621)

    def test_three_page_frontend_and_real_render_hooks(self):
        component = (ROOT / 'static/js/story-clear-settlement.js').read_text(encoding='utf-8')
        story = (ROOT / 'static/js/story.js').read_text(encoding='utf-8')
        template = (ROOT / 'templates/story.html').read_text(encoding='utf-8')
        app = (ROOT / 'app.py').read_text(encoding='utf-8')
        for title in ('通关分数', '通关得分', '通关路线', '最终牌组'):
            self.assertIn(title, component)
        for marker in ('scs-score-ledger', 'scs-dew-result', 'scs-golden-result', 'scs-route-map', 'scs-deck-grid'):
            self.assertIn(marker, component)
        self.assertIn('score.total_score', component)
        self.assertIn('dew_gain_multiplier', component)
        self.assertIn('全局荆露收益乘数', component)
        self.assertIn('golden-dew.svg', component)
        self.assertIn('difficultyKey', component)
        self.assertIn('（sl）', component)
        self.assertNotIn('无SL奖励系数', component)
        self.assertNotIn('向下取整为', component)
        for item in ('stages', 'all_stages_bonus', 'normal_battles', 'elite_battles', 'gold', 'cards', 'relics', 'enchantment_books'):
            self.assertIn(item, component)
        self.assertIn('window.GtnStoryClearSettlementRenderers', story)
        self.assertIn('maybeAutoStoryClearSettlement', story)
        self.assertIn('story-history-settlement', story)
        self.assertIn('/api/story/runs/clear-settlement/seen', story)
        self.assertIn('/api/story/runs/clear-settlement/seen', app)
        self.assertIn('/static/js/story-clear-settlement.js', template)
        self.assertIn('/static/css/story-clear-settlement.css', template)
        self.assertIn('isDefeat', component)
        self.assertIn('旅程结算 · 战败', component)

    def _defeat_state(self, *, stage=2):
        state = completed_state()
        state['phase'] = 'game_over'
        state['completed'] = False
        state['stage'] = stage
        state['content_version'] = 'story-clear-test'
        return state

    def test_defeat_settles_by_cleared_bosses(self):
        pre = self._pre_completion_state()
        pre['stage'] = 2
        run, created = db.create_story_run(
            self.user['id'], 'seed-defeat', 'story-clear-test', pre,
        )
        self.assertTrue(created)
        next_state = self._defeat_state()
        updated, outcome = db.commit_story_run_action(
            self.user['id'], run['id'], int(run['state_version']),
            'defeat-1', 'end_turn', {}, next_state,
        )
        self.assertEqual(outcome, 'committed')
        with db.get_db_connection() as conn:
            ledger = conn.execute(
                'SELECT completed_stages, total_score, bank_cleared, golden_dew_reward '
                'FROM story_reward_ledger WHERE run_id = ?',
                (run['id'],),
            ).fetchone()
            detail = story_history.get_history_detail(conn, self.user['id'], run['id'])
        self.assertIsNotNone(ledger)
        # 第 2 幕没打完 boss，只能算 1 幕。
        self.assertEqual(int(ledger['completed_stages']), 1)
        self.assertGreater(int(ledger['total_score']), 0)
        self.assertEqual(int(ledger['bank_cleared']), 0)
        self.assertGreater(db.get_user_thorn_dew(self.user['id'])['total'], 0)
        self.assertEqual(detail['summary']['result'], 'defeat')
        self.assertIsNotNone(detail['settlement'])

    def test_defeat_settlement_runs_once(self):
        pre = self._pre_completion_state()
        pre['stage'] = 2
        run, _ = db.create_story_run(
            self.user['id'], 'seed-defeat-once', 'story-clear-test', pre,
        )
        next_state = self._defeat_state()
        version = int(run['state_version'])
        for index in (1, 2):
            updated, outcome = db.commit_story_run_action(
                self.user['id'], run['id'], version, f'defeat-{index}',
                'end_turn', {}, next_state,
            )
            self.assertEqual(outcome, 'committed')
            version = int(updated['state_version'])
        with db.get_db_connection() as conn:
            ledger_count = conn.execute(
                'SELECT COUNT(*) AS n FROM story_reward_ledger WHERE run_id = ?',
                (run['id'],),
            ).fetchone()['n']
        self.assertEqual(ledger_count, 1)

    def test_surrender_records_history_without_reward(self):
        pre = self._pre_completion_state()
        pre['stage'] = 2
        run, _ = db.create_story_run(
            self.user['id'], 'seed-surrender', 'story-clear-test', pre,
        )
        next_state = self._defeat_state()
        _, outcome = db.commit_story_run_action(
            self.user['id'], run['id'], int(run['state_version']),
            'surrender-1', 'surrender', {}, next_state,
        )
        self.assertEqual(outcome, 'committed')
        with db.get_db_connection() as conn:
            ledger_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'story_reward_ledger'",
            ).fetchone()
            ledger_count = (
                conn.execute(
                    'SELECT COUNT(*) AS n FROM story_reward_ledger WHERE run_id = ?',
                    (run['id'],),
                ).fetchone()['n']
                if ledger_table is not None
                else 0
            )
            detail = story_history.get_history_detail(conn, self.user['id'], run['id'])
        self.assertEqual(ledger_count, 0)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], 0)
        self.assertEqual(detail['summary']['result'], 'defeat')
        self.assertIsNone(detail['settlement'])


if __name__ == '__main__':
    unittest.main()
