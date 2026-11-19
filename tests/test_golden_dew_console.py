# -*- coding: utf-8 -*-
"""控制台金露发放指令的余额、流水与参数校验。"""

import gc
import os
import tempfile
import unittest

import app
import db


class GoldenDewConsoleCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'golden-console.sqlite3')
        db.init_db()
        self.user, error = db.create_user('GoldenConsole', 'Aa1!aaaa')
        self.assertIsNone(error)
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET golden_dew = 7 WHERE id = ?', (self.user['id'],))
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_addgolden_grants_balance_and_writes_audit_transaction(self):
        result = app.execute_admin_command(
            f"account dew addgolden {self.user['username']} 5 测试发放",
            actor='test-console',
        )
        self.assertTrue(result['success'], result['output'])
        self.assertIn('金露：12', result['output'])
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 12)
        with db.get_db_connection() as conn:
            transaction = conn.execute(
                '''SELECT free_delta, paid_delta, reason, source_type,
                          admin_username, balance_free_after
                   FROM user_currency_transactions
                   WHERE user_id = ? AND currency = 'golden_dew' ''',
                (self.user['id'],),
            ).fetchone()
        self.assertIsNotNone(transaction)
        self.assertEqual(
            tuple(transaction),
            (5, 0, '测试发放', 'admin_command', 'console', 12),
        )

    def test_getgolden_returns_current_balance(self):
        result = app.execute_admin_command(
            f'account dew getgolden {self.user["username"]}', actor='test-console',
        )
        self.assertTrue(result['success'], result['output'])
        self.assertIn(self.user['username'], result['output'])
        self.assertIn('金露：7', result['output'])

    def test_txgolden_lists_only_golden_transactions(self):
        granted = app.execute_admin_command(
            f'account dew addgolden {self.user["username"]} 5 测试发放',
            actor='test-console',
        )
        self.assertTrue(granted['success'], granted['output'])
        db.adjust_user_thorn_dew(
            self.user['id'], free_delta=50, reason='荆露流水', source_type='test',
        )
        result = app.execute_admin_command(
            f'account dew txgolden {self.user["username"]}', actor='test-console',
        )
        self.assertTrue(result['success'], result['output'])
        self.assertIn('最近金露流水', result['output'])
        self.assertIn('金露+5', result['output'])
        self.assertIn('余额=12', result['output'])
        self.assertIn('测试发放', result['output'])
        self.assertNotIn('荆露流水', result['output'])

    def test_txgolden_shows_empty_history(self):
        result = app.execute_admin_command(
            f'account dew txgolden {self.user["username"]}', actor='test-console',
        )
        self.assertTrue(result['success'], result['output'])
        self.assertIn('暂无流水', result['output'])

    def test_addgolden_rejects_invalid_amounts_without_mutating_account(self):
        for amount in ('0', 'not-a-number'):
            with self.subTest(amount=amount):
                result = app.execute_admin_command(
                    f'account dew addgolden {self.user["username"]} {amount}',
                    actor='test-console',
                )
                self.assertFalse(result['success'])
                self.assertEqual(db.get_user_golden_dew(self.user['id']), 7)
        with db.get_db_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM user_currency_transactions WHERE user_id = ? AND currency = 'golden_dew'",
                (self.user['id'],),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_addgolden_allows_negative_adjustment_and_preserves_negative_balance(self):
        result = app.execute_admin_command(
            f'account dew addgolden {self.user["username"]} -10 测试扣除',
            actor='test-console',
        )
        self.assertTrue(result['success'], result['output'])
        self.assertIn('金露：-3', result['output'])
        self.assertEqual(db.get_user_golden_dew(self.user['id']), -3)
        second = app.execute_admin_command(
            f'account dew addgolden {self.user["username"]} -2 再次扣除',
            actor='test-console',
        )
        self.assertTrue(second['success'], second['output'])
        self.assertEqual(db.get_user_golden_dew(self.user['id']), -5)
        with db.get_db_connection() as conn:
            transactions = conn.execute(
                '''SELECT free_delta, balance_free_after, reason
                   FROM user_currency_transactions
                   WHERE user_id = ? AND currency = 'golden_dew'
                   ORDER BY id''',
                (self.user['id'],),
            ).fetchall()
        self.assertEqual(
            [tuple(row) for row in transactions],
            [(-10, -3, '测试扣除'), (-2, -5, '再次扣除')],
        )

    def test_console_spend_and_add_allow_negative_thorn_dew_balance(self):
        with db.get_db_connection() as conn:
            conn.execute(
                'UPDATE users SET thorn_dew_free = 0, thorn_dew_paid = 0 WHERE id = ?',
                (self.user['id'],),
            )
            conn.commit()
        spent = app.execute_admin_command(
            f'account dew spend {self.user["username"]} 20 测试超额扣款',
            actor='test-console',
        )
        self.assertTrue(spent['success'], spent['output'])
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], -20)
        added = app.execute_admin_command(
            f'account dew add {self.user["username"]} -7 测试负调整',
            actor='test-console',
        )
        self.assertTrue(added['success'], added['output'])
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], -27)
        with db.get_db_connection() as conn:
            transactions = conn.execute(
                '''SELECT free_delta, balance_free_after, reason
                   FROM user_currency_transactions
                   WHERE user_id = ? AND currency = 'thorn_dew'
                   ORDER BY id''',
                (self.user['id'],),
            ).fetchall()
        self.assertEqual(
            [tuple(row) for row in transactions],
            [(-20, -20, '测试超额扣款'), (-7, -27, '测试负调整')],
        )

    def test_negative_balances_remain_visible_in_console_queries_and_history(self):
        deducted = app.execute_admin_command(
            f'account dew addgolden {self.user["username"]} -10 测试负数查询',
            actor='test-console',
        )
        self.assertTrue(deducted['success'], deducted['output'])
        golden = app.execute_admin_command(
            f'account dew getgolden {self.user["username"]}', actor='test-console',
        )
        self.assertIn('金露：-3', golden['output'])
        golden_tx = app.execute_admin_command(
            f'account dew txgolden {self.user["username"]}', actor='test-console',
        )
        self.assertIn('金露-10', golden_tx['output'])
        self.assertIn('余额=-3', golden_tx['output'])

        spent = app.execute_admin_command(
            f'account dew spend {self.user["username"]} 20 测试负数流水',
            actor='test-console',
        )
        self.assertTrue(spent['success'], spent['output'])
        dew = app.execute_admin_command(
            f'account dew get {self.user["username"]}', actor='test-console',
        )
        self.assertIn('荆露：-20', dew['output'])
        dew_tx = app.execute_admin_command(
            f'account dew tx {self.user["username"]}', actor='test-console',
        )
        self.assertIn('普通-20', dew_tx['output'])
        self.assertIn('余额=-20', dew_tx['output'])
        center = db.get_user_thorn_dew_center(self.user['id'])
        self.assertEqual(center['balance']['total'], -20)
        self.assertEqual(center['golden_balance'], -3)

    def test_frontend_preserves_negative_balances(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        source = (root / 'static/js/game.js').read_text(encoding='utf-8')
        center = source.split('function thornDewCenterHtml', 1)[1].split('function thornDewCheckinHtml', 1)[0]
        profile = source.split('function renderAccountInfoPanel', 1)[1].split('function ', 1)[0]
        blocks = [
            center,
            source.split('async function loadThornDewCenter', 1)[1].split('async function onThornDewCheckin', 1)[0],
            profile,
        ]
        for block in blocks:
            self.assertNotIn('Math.max(0', block)
        self.assertIn("thornDewAmountHtml(total, 'dew-amount', '/static/assets/ui-icons/thorn-dew.svg', true)", center)
        self.assertIn("thornDewAmountHtml(golden, 'dew-amount', '/static/assets/ui-icons/golden-dew.svg', true)", center)
        self.assertIn("thornDewAmountHtml(value, 'dew-amount', undefined, true)", profile)
        self.assertIn("goldenDew, 'golden'],", profile)
        self.assertIn("kind === 'golden'", profile)
        self.assertIn("thornDewAmountHtml(value, 'dew-amount', '/static/assets/ui-icons/golden-dew.svg', true)", profile)
        amount = source.split('function thornDewAmountHtml', 1)[1].split('function titleShopRemainingSeconds', 1)[0]
        self.assertIn('allowNegative = false', amount)
        self.assertIn('allowNegative ? numericAmount : Math.max(0, numericAmount)', amount)
        hud = (root / 'static/js/dew-hud.js').read_text(encoding='utf-8')
        self.assertNotIn('Math.max(0', hud)

    def test_regular_spend_still_rejects_insufficient_balance(self):
        with db.get_db_connection() as conn:
            conn.execute(
                'UPDATE users SET thorn_dew_free = 0, thorn_dew_paid = 0 WHERE id = ?',
                (self.user['id'],),
            )
            conn.commit()
        updated, error = db.spend_user_thorn_dew(self.user['id'], 1, reason='普通购买')
        self.assertIsNone(updated)
        self.assertEqual(error, '荆露不足')
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], 0)

    def test_addgolden_rejects_unknown_account(self):
        result = app.execute_admin_command(
            'account dew addgolden NoSuchAccount 2', actor='test-console',
        )
        self.assertFalse(result['success'])
        self.assertIn('账号不存在', result['output'])


if __name__ == '__main__':
    unittest.main()
