# -*- coding: utf-8 -*-
"""金露：历史迁移、后续充值、余额流水与奖励接口。"""

import gc
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import app
import db


class GoldenDewMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'golden-dew.sqlite3')
        db.init_db()
        self.user, error = db.create_user('GoldenUser', 'Aa1!aaaa')
        self.assertIsNone(error)
        self.other, error = db.create_user('GoldenOther', 'Aa1!aaaa')
        self.assertIsNone(error)
        self.uid = int(self.user['id'])
        self.other_uid = int(self.other['id'])
        with db.get_db_connection() as conn:
            conn.executemany(
                '''
                INSERT INTO user_currency_transactions (
                    user_id, currency, free_delta, paid_delta, reason,
                    source_type, source_id, balance_free_after,
                    balance_paid_after, created_at
                ) VALUES (?, 'thorn_dew', ?, ?, ?, 'afdian', ?, 0, 0, ?)
                ''',
                [
                    (self.uid, 0, 1000, '首次充值', 'one', db.utc_now()),
                    (self.uid, 0, 50, '小额充值', 'two', db.utc_now()),
                    (self.uid, 0, -20, '历史消费', 'spend', db.utc_now()),
                    (self.other_uid, 0, 50, '不足一百', 'three', db.utc_now()),
                ],
            )
            conn.execute('UPDATE users SET thorn_dew_paid = 500 WHERE id = ?', (self.uid,))
            conn.execute('UPDATE users SET thorn_dew_paid = 50 WHERE id = ?', (self.other_uid,))
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_migration_uses_earned_paid_dew_and_is_idempotent(self):
        db.init_db()
        self.assertEqual(db.get_user_golden_dew(self.uid), 10)
        self.assertEqual(db.get_user_golden_dew(self.other_uid), 0)
        with db.get_db_connection() as conn:
            balances = {
                row['id']: (row['thorn_dew_paid'], row['golden_dew'])
                for row in conn.execute(
                    'SELECT id, thorn_dew_paid, golden_dew FROM users WHERE id IN (?, ?)',
                    (self.uid, self.other_uid),
                ).fetchall()
            }
            self.assertEqual(balances[self.uid], (0, 10))
            self.assertEqual(balances[self.other_uid], (0, 0))
            marker = conn.execute(
                'SELECT paid_earned, golden_granted FROM golden_dew_migration WHERE user_id = ?',
                (self.uid,),
            ).fetchone()
            self.assertEqual(tuple(marker), (1050, 10))
            tx = conn.execute(
                "SELECT free_delta, paid_delta, currency FROM user_currency_transactions "
                "WHERE user_id = ? AND source_type = 'golden_dew_migration'",
                (self.uid,),
            ).fetchone()
            self.assertEqual(tuple(tx), (10, 0, 'golden_dew'))
        # 重复初始化不重复发币；累计获得 1050，而不是当前余额 500。
        db.init_db()
        self.assertEqual(db.get_user_golden_dew(self.uid), 10)

    def test_future_credit_and_old_api_compatibility_use_golden_dew(self):
        db.init_db()
        updated, error = db.adjust_user_thorn_dew(
            self.uid, paid_delta=200, reason='后续充值', source_type='afdian', source_id='new-order',
        )
        self.assertIsNone(error)
        self.assertEqual(updated['golden_dew'], 12)
        self.assertEqual(updated['thorn_dew_paid'], 0)
        updated, error = db.adjust_user_golden_dew(
            self.uid, 3, reason='管理员补发', source_type='admin_command',
        )
        self.assertIsNone(error)
        self.assertEqual(updated['golden_dew'], 15)
        with db.get_db_connection() as conn:
            tx = conn.execute(
                "SELECT currency, free_delta, paid_delta FROM user_currency_transactions "
                "WHERE user_id = ? AND source_id = 'new-order'",
                (self.uid,),
            ).fetchone()
            self.assertEqual(tuple(tx), ('golden_dew', 2, 0))
        center = db.get_user_thorn_dew_center(self.uid)
        self.assertEqual(center['golden_balance'], 15)
        self.assertGreaterEqual(len(center['golden_transactions']), 2)
        app.app.config.update(TESTING=True)
        client = app.app.test_client()
        with mock.patch.object(app, '_current_account_user', return_value=self.user):
            payload = client.get('/api/rewards/status?after=0').get_json()
        self.assertTrue(payload['success'])
        rewards = payload['golden_dew_rewards']
        self.assertEqual(sum(int(row['amount']) for row in rewards), 15)
        self.assertEqual(payload['dew_cursor'], max(row['id'] for row in rewards)
        )

    def test_frontend_golden_dew_asset_and_animation_are_registered(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / 'static/assets/ui-icons/golden-dew.svg').is_file())
        script = (root / 'static/js/reward-animation.js').read_text(encoding='utf-8')
        self.assertIn("golden_dew: '/static/assets/ui-icons/golden-dew.svg'", script)
        self.assertIn('data.golden_dew_rewards', script)
        self.assertIn("kind: 'golden_dew'", script)
        game = (root / 'static/js/game.js').read_text(encoding='utf-8')
        self.assertIn('golden_dew', game)
        self.assertIn('golden_transactions', game)
        self.assertIn('golden-dew-1', (root / 'static_version.txt').read_text(encoding='utf-8'))
        afdian = (root / 'templates/afdian.html').read_text(encoding='utf-8')
        self.assertNotIn('赞助不再发放金露。', afdian)
        self.assertNotIn('按方案兑换<b>金露（Golden Dew）</b>', afdian)
        self.assertNotIn('兑换的荆露仅为感谢回馈', afdian)


if __name__ == '__main__':
    unittest.main()
