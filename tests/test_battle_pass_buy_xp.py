"""5 金露 → 100 通行证经验：扣款、发经验、幂等与赛季边界。"""

from __future__ import annotations

import os
import gc
import tempfile
import unittest
from unittest import mock

import backgrounds
import battle_pass as bp
import db
import leisure_ticket
import player_skins


class BuyPassXpTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'battle-pass-buy-xp.sqlite3')
        db.init_db()
        self.user, err = db.create_user('BuyXpOwner1', 'Passw0rd!xyz')
        self.assertIsNone(err)
        self.uid = int(self.user['id'])
        with db.get_db_connection() as conn:
            bp.ensure_pass_schema(conn)
            leisure_ticket.ensure_ticket_columns(conn)
            player_skins.ensure_player_skin_schema(conn)
            backgrounds.ensure_background_schema(conn)
            conn.execute('UPDATE users SET golden_dew = 0 WHERE id = ?', (self.uid,))
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def _set_golden(self, amount):
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET golden_dew = ? WHERE id = ?', (int(amount), self.uid))
            conn.commit()

    def _golden(self):
        with db.get_db_connection() as conn:
            return int(conn.execute(
                'SELECT golden_dew FROM users WHERE id = ?', (self.uid,)
            ).fetchone()['golden_dew'] or 0)

    def _xp_total(self):
        with db.get_db_connection() as conn:
            row = conn.execute(
                'SELECT xp_total FROM battle_pass_progress WHERE user_id = ? AND season_id = ?',
                (self.uid, bp.season_id()),
            ).fetchone()
            return int(row['xp_total']) if row else 0

    def _buy(self):
        with db.get_db_connection() as conn:
            payload, error = bp.buy_xp(conn, self.uid)
            conn.commit()
            return payload, error

    def test_buy_xp_spends_five_golden_and_grants_hundred_xp(self):
        self._set_golden(12)
        payload, error = self._buy()
        self.assertIsNone(error)
        self.assertEqual(payload['cost'], 5)
        self.assertEqual(payload['xp_gained'], 100)
        self.assertEqual(payload['golden_dew'], 7)
        self.assertEqual(self._golden(), 7)
        self.assertEqual(self._xp_total(), 100)
        self.assertEqual(payload['level_before'], 0)
        self.assertEqual(payload['level_after'], 1)

    def test_buy_xp_records_a_ledger_entry_and_a_currency_transaction(self):
        self._set_golden(5)
        self._buy()
        with db.get_db_connection() as conn:
            ledger = conn.execute(
                'SELECT source, xp, base_xp, multiplier FROM battle_pass_xp_ledger '
                'WHERE user_id = ? ORDER BY id',
                (self.uid,),
            ).fetchall()
            tx = conn.execute(
                'SELECT currency, free_delta, reason FROM user_currency_transactions '
                'WHERE user_id = ? ORDER BY id DESC LIMIT 1',
                (self.uid,),
            ).fetchone()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]['source'], 'golden')
        self.assertEqual(int(ledger[0]['xp']), 100)
        self.assertEqual(int(ledger[0]['base_xp']), 100)
        self.assertEqual(float(ledger[0]['multiplier']), 1.0)
        self.assertEqual(tx['currency'], 'golden_dew')
        self.assertEqual(int(tx['free_delta']), -5)
        self.assertIn('金露兑换经验', tx['reason'])

    def test_buy_xp_requires_five_golden(self):
        self._set_golden(4)
        payload, error = self._buy()
        self.assertIsNone(payload)
        self.assertEqual(error, '金露不足')
        self.assertEqual(self._golden(), 4)
        self.assertEqual(self._xp_total(), 0)

    def test_each_purchase_is_its_own_exchange(self):
        self._set_golden(10)
        for _ in range(2):
            _, error = self._buy()
            self.assertIsNone(error)
        self.assertEqual(self._golden(), 0)
        self.assertEqual(self._xp_total(), 200)
        with db.get_db_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM battle_pass_xp_ledger "
                "WHERE user_id = ? AND source = 'golden'",
                (self.uid,),
            ).fetchone()['c']
        self.assertEqual(int(count), 2)

    def test_buy_xp_rejects_a_closed_season(self):
        self._set_golden(10)
        closed = (bp.PASS_SEASON_START, bp.PASS_SEASON_START, False)
        with mock.patch.object(bp, 'season_bounds', return_value=closed):
            payload, error = self._buy()
        self.assertIsNone(payload)
        self.assertEqual(error, '赛季已结束，无法兑换经验')
        self.assertEqual(self._golden(), 10)
        self.assertEqual(self._xp_total(), 0)

    def test_state_payload_exposes_the_exchange_rate(self):
        with db.get_db_connection() as conn:
            payload = bp.state_payload(conn, self.uid)
        self.assertEqual(payload['xp_buy_cost'], 5)
        self.assertEqual(payload['xp_buy_amount'], 100)


if __name__ == '__main__':
    unittest.main()
