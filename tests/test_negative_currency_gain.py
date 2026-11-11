# -*- coding: utf-8 -*-
"""负余额账户获得荆露/金露时不能被 max(0, 余额) 抹平为 0。"""

import gc
import os
import tempfile
import unittest

import db
import leisure_ticket_settlement
import story_score


def _completed_state():
    return {
        'completed': True,
        'stage': 3,
        'difficulty': 'normal',
        'normal_battles': 10,
        'encounter_history': {'elite': {'garden': [0, 1], 'desert': [0]}},
        'current_node_id': 'n1',
        'map': {
            'floors': [{
                'floor': 1,
                'nodes': [{
                    'id': 'n1', 'type': 'boss', 'status': 'completed',
                    'x': 380, 'y': 100,
                }],
            }],
            'edges': [],
        },
        'journey_route': [{'stage': 3, 'floor': 1, 'type': 'boss', 'enemies': [], 'cards_gained': []}],
        'player': {
            'health': 42, 'max_health': 70, 'gold': 25,
            'deck': [{'def_id': 'basic'}, {'def_id': 'rose', 'upgraded': True}],
            'relics': ['r1', 'r2'], 'enchantment_books': [{'id': 'b1'}],
        },
    }


class NegativeBalanceGainTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'negative-dew.sqlite3')
        db.init_db()
        self.user, error = db.create_user('NegativeDewOwner', 'Passw0rd!xyz')
        assert self.user, error
        self.uid = self.user['id']

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def _set_negative(self, free=-100, golden=-5):
        if free:
            updated, error = db.adjust_user_thorn_dew(
                self.uid, free_delta=free, reason='test debt',
                source_type='test', allow_negative=True,
            )
            self.assertIsNone(error)
        if golden:
            updated, error = db.adjust_user_golden_dew(
                self.uid, golden, reason='test debt',
                source_type='test', allow_negative=True,
            )
            self.assertIsNone(error)

    def test_thorn_dew_gain_keeps_negative_balance(self):
        self._set_negative(free=-100, golden=0)
        updated, error = db.adjust_user_thorn_dew(
            self.uid, free_delta=30, reason='测试获取', source_type='test',
        )
        self.assertIsNone(error)
        self.assertEqual(int(updated['thorn_dew_free']), -70)
        self.assertEqual(db.get_user_thorn_dew(self.uid)['free'], -70)
        with db.get_db_connection() as conn:
            last = conn.execute(
                'SELECT free_delta, balance_free_after FROM user_currency_transactions '
                'WHERE user_id = ? ORDER BY id DESC LIMIT 1',
                (self.uid,),
            ).fetchone()
        self.assertEqual(int(last['free_delta']), 30)
        self.assertEqual(int(last['balance_free_after']), -70)

    def test_golden_dew_gain_keeps_negative_balance(self):
        self._set_negative(free=0, golden=-5)
        updated, error = db.adjust_user_golden_dew(
            self.uid, 2, reason='测试获取', source_type='test',
        )
        self.assertIsNone(error)
        self.assertEqual(int(updated['golden_dew']), -3)
        self.assertEqual(db.get_user_golden_dew(self.uid), -3)

    def test_story_clear_rewards_add_to_negative_balances(self):
        self._set_negative(free=-100, golden=-5)
        with db.get_db_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            result = story_score.settle_story_clear_conn(
                conn, user_id=self.uid, run_id='negative-clear', state=_completed_state(),
            )
            conn.commit()
        self.assertEqual(result['total'], 931)
        self.assertEqual(result['golden_dew_reward'], 4)
        self.assertEqual(db.get_user_thorn_dew(self.uid)['free'], -100 + 931)
        self.assertEqual(db.get_user_golden_dew(self.uid), -5 + 4)

    def test_leisure_reward_adds_to_negative_balance(self):
        self._set_negative(free=-100, golden=0)
        with db.get_db_connection() as conn:
            granted = leisure_ticket_settlement._grant_dew(
                conn, self.uid, 50, '测试休闲奖励',
            )
            conn.commit()
        self.assertTrue(granted)
        self.assertEqual(db.get_user_thorn_dew(self.uid)['free'], -50)

    def test_conversion_does_not_reset_negative_component(self):
        self._set_negative(free=-250, golden=10)
        result, error = db.convert_user_dew(self.uid, 'golden_to_dew', 1)
        self.assertIsNone(error)
        self.assertEqual(result['received'], 100)
        self.assertEqual(db.get_user_thorn_dew(self.uid)['free'], -150)
        self.assertEqual(db.get_user_golden_dew(self.uid), 9)


if __name__ == '__main__':
    unittest.main()
