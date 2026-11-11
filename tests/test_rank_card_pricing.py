# -*- coding: utf-8 -*-
"""保分/双倍卡定价：每天第一张 300 荆露，之后每张 5 金露。"""

import gc
import os
import tempfile
import unittest

import db


class RankCardPricingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'rank-cards.sqlite3')
        db.init_db()
        self.user, err = db.create_user('CardBuyer1', 'Passw0rd!xyz')
        assert self.user, err
        self.uid = int(self.user['id'])
        with db.get_db_connection() as conn:
            conn.execute(
                'UPDATE users SET thorn_dew_free = 1000, golden_dew = 100,'
                ' rank_card_buys = 0, rank_card_day = ? WHERE id = ?',
                ('', self.uid),
            )
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def _balances(self):
        with db.get_db_connection() as conn:
            row = conn.execute(
                'SELECT thorn_dew_free, thorn_dew_paid, golden_dew FROM users WHERE id = ?',
                (self.uid,),
            ).fetchone()
            conn.commit()
        return (
            int(row['thorn_dew_free']) + int(row['thorn_dew_paid']),
            int(row['golden_dew']),
        )

    def test_price_ladder_uses_thorn_dew_then_golden_dew(self):
        self.assertEqual(db.rank_card_price(0), (300, 'thorn_dew'))
        self.assertEqual(db.rank_card_price(1), (5, 'golden_dew'))
        self.assertEqual(db.rank_card_price(9), (5, 'golden_dew'))

    def test_first_purchase_costs_thorn_dew_and_second_costs_golden_dew(self):
        dew_before, gold_before = self._balances()
        payload, error = db.purchase_rank_card(self.uid, 'shield')
        self.assertIsNone(error)
        self.assertEqual(payload['buys_today'], 1)
        self.assertEqual(payload['price_today_currency'], 'golden_dew')
        dew_after, gold_after = self._balances()
        self.assertEqual(dew_before - dew_after, 300)
        self.assertEqual(gold_before - gold_after, 0)

        payload, error = db.purchase_rank_card(self.uid, 'double')
        self.assertIsNone(error)
        self.assertEqual(payload['buys_today'], 2)
        dew_final, gold_final = self._balances()
        self.assertEqual(dew_after - dew_final, 0)
        self.assertEqual(gold_after - gold_final, 5)

    def test_second_purchase_needs_golden_dew(self):
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET golden_dew = 0 WHERE id = ?', (self.uid,))
            conn.commit()
        _, error = db.purchase_rank_card(self.uid, 'shield')
        self.assertIsNone(error)
        _, error = db.purchase_rank_card(self.uid, 'shield')
        self.assertEqual(error, '金露不足')
        with db.get_db_connection() as conn:
            row = conn.execute(
                'SELECT rank_shield_cards FROM users WHERE id = ?', (self.uid,),
            ).fetchone()
            conn.commit()
        self.assertEqual(int(row['rank_shield_cards']), 1)

    def test_first_purchase_needs_thorn_dew(self):
        with db.get_db_connection() as conn:
            conn.execute(
                'UPDATE users SET thorn_dew_free = 0, thorn_dew_paid = 0 WHERE id = ?',
                (self.uid,),
            )
            conn.commit()
        _, error = db.purchase_rank_card(self.uid, 'double')
        self.assertEqual(error, '荆露不足')

    def test_shared_daily_counter_across_both_card_types(self):
        payload, _ = db.purchase_rank_card(self.uid, 'shield')
        self.assertEqual(payload['price_today_currency'], 'golden_dew')
        payload, _ = db.purchase_rank_card(self.uid, 'double')
        self.assertEqual(payload['price_today_currency'], 'golden_dew')
        self.assertEqual(payload['price_today'], 5)
        self.assertEqual(payload['price_next_currency'], 'golden_dew')


if __name__ == '__main__':
    unittest.main()
