# -*- coding: utf-8 -*-
"""荆露与金露双向原子兑换。"""

from concurrent.futures import ThreadPoolExecutor
import gc
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import app
import db


class DewConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'dew-conversion.sqlite3')
        db.init_db()
        self.user, error = db.create_user('ConversionUser', 'Aa1!aaaa')
        self.assertIsNone(error)
        self.uid = int(self.user['id'])
        with db.get_db_connection() as conn:
            conn.execute(
                'UPDATE users SET thorn_dew_free = 5000, thorn_dew_paid = 0, golden_dew = 3 WHERE id = ?',
                (self.uid,),
            )
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def balances(self):
        with db.get_db_connection() as conn:
            row = conn.execute(
                'SELECT thorn_dew_free, thorn_dew_paid, golden_dew FROM users WHERE id = ?',
                (self.uid,),
            ).fetchone()
            return tuple(row)

    def test_both_directions_use_exact_rates_and_linked_ledgers(self):
        first, error = db.convert_user_dew(self.uid, 'golden_to_dew', 2)
        self.assertIsNone(error)
        self.assertEqual((first['spent'], first['received']), (2, 200))
        self.assertEqual(self.balances(), (5200, 0, 1))

        second, error = db.convert_user_dew(self.uid, 'dew_to_golden', 1000)
        self.assertIsNone(error)
        self.assertEqual((second['spent'], second['received']), (1000, 1))
        self.assertEqual(self.balances(), (4200, 0, 2))
        with db.get_db_connection() as conn:
            rows = conn.execute(
                "SELECT currency, free_delta, source_type, source_id, reason FROM user_currency_transactions "
                "WHERE user_id = ? AND source_type = 'currency_conversion' ORDER BY id",
                (self.uid,),
            ).fetchall()
        self.assertEqual(len(rows), 4)
        self.assertEqual([row['free_delta'] for row in rows], [200, -2, -1000, 1])
        self.assertEqual(rows[0]['source_id'], rows[1]['source_id'])
        self.assertEqual(rows[2]['source_id'], rows[3]['source_id'])
        self.assertEqual(rows[0]['reason'], '2金露兑换为200荆露')
        self.assertEqual(rows[2]['reason'], '1000荆露兑换为1金露')

    def test_invalid_amounts_and_insufficient_balances_do_not_change_anything(self):
        cases = [
            ('dew_to_golden', 0),
            ('dew_to_golden', -1000),
            ('dew_to_golden', 1500),
            ('dew_to_golden', 6000),
            ('golden_to_dew', 4),
            ('other', 1),
            ('dew_to_golden', 'abc'),
        ]
        for direction, amount in cases:
            with self.subTest(direction=direction, amount=amount):
                _, error = db.convert_user_dew(self.uid, direction, amount)
                self.assertTrue(error)
                self.assertEqual(self.balances(), (5000, 0, 3))
        with db.get_db_connection() as conn:
            count = conn.execute(
                'SELECT COUNT(*) AS count FROM user_currency_transactions WHERE user_id = ?',
                (self.uid,),
            ).fetchone()['count']
        self.assertEqual(count, 0)

    def test_concurrent_conversion_cannot_spend_the_same_balance_twice(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _: db.convert_user_dew(self.uid, 'golden_to_dew', 2),
                range(2),
            ))
        self.assertEqual(sum(error is None for _, error in results), 1)
        self.assertEqual(sum(error is not None for _, error in results), 1)
        self.assertEqual(self.balances(), (5200, 0, 1))
        with db.get_db_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM user_currency_transactions "
                "WHERE user_id = ? AND source_type = 'currency_conversion'",
                (self.uid,),
            ).fetchone()['count']
        self.assertEqual(count, 2)

    def test_convert_api_returns_fresh_balances_and_rejects_bad_input(self):
        app.app.config.update(TESTING=True)
        client = app.app.test_client()
        with mock.patch.object(app, '_current_account_user', return_value=self.user):
            response = client.post('/api/thorn-dew/convert', json={
                'direction': 'dew_to_golden', 'amount': 1000,
            })
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload['success'])
            self.assertEqual(payload['conversion']['received'], 1)
            self.assertEqual(payload['balance']['total'], 4000)
            self.assertEqual(payload['golden_balance'], 4)
            bad = client.post('/api/thorn-dew/convert', json={
                'direction': 'dew_to_golden', 'amount': 1500,
            })
            self.assertEqual(bad.status_code, 400)
            fractional = client.post('/api/thorn-dew/convert', json={
                'direction': 'dew_to_golden', 'amount': 1000.5,
            })
            self.assertEqual(fractional.status_code, 400)
        self.assertEqual(self.balances(), (4000, 0, 4))

    def test_frontend_conversion_controls_and_version_are_registered(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / 'static/js/game.js').read_text(encoding='utf-8')
        for token in (
            '/api/thorn-dew/convert',
            'btn-golden-to-dew',
            'btn-dew-to-golden',
            'dew-convert-golden-amount',
            'dew-convert-thorn-amount',
            "onDewConvert('golden_to_dew')",
            "onDewConvert('dew_to_golden')",
        ):
            self.assertIn(token, script)
        self.assertIn('.dew-convert-row', (root / 'static/css/style.css').read_text(encoding='utf-8'))
        self.assertIn('-dew-conversion-1', (root / 'static_version.txt').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
