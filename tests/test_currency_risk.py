# -*- coding: utf-8 -*-
"""异常流水检测（currency_risk）单元测试。

阈值：荆露 5 分钟内重复同额 >1000 / 单笔 >5000 / 日流水 >20000；
金露 5 分钟内重复同额 >5 / 日流水 >100。
"""

import os
import sqlite3
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import currency_risk


def tx(tx_id, user_id=1, currency='thorn_dew', free_delta=0, paid_delta=0, created_at='2026-11-12T01:00:00Z', reason='', source_type='pvp'):
    return {
        'id': tx_id,
        'user_id': user_id,
        'currency': currency,
        'free_delta': free_delta,
        'paid_delta': paid_delta,
        'created_at': created_at,
        'reason': reason,
        'source_type': source_type,
        'username': 'Tester',
    }


class DetectTests(unittest.TestCase):
    def test_duplicate_thorn_over_thousand_within_five_minutes(self):
        rows = [
            tx(1, free_delta=1200, created_at='2026-11-12T01:00:00Z'),
            tx(2, free_delta=1200, created_at='2026-11-12T01:04:00Z'),
        ]
        items = currency_risk.detect(rows)
        kinds = [item['kind'] for item in items]
        self.assertIn('duplicate', kinds)
        duplicate = next(item for item in items if item['kind'] == 'duplicate')
        self.assertEqual(duplicate['amount'], 1200)
        self.assertEqual(duplicate['threshold'], 1000)
        self.assertEqual(duplicate['transaction_ids'], [1, 2])

    def test_duplicate_at_threshold_or_outside_window_is_ignored(self):
        rows = [
            tx(1, free_delta=1000, created_at='2026-11-12T01:00:00Z'),
            tx(2, free_delta=1000, created_at='2026-11-12T01:01:00Z'),
            tx(3, free_delta=1500, created_at='2026-11-12T03:00:00Z'),
            tx(4, free_delta=1500, created_at='2026-11-12T03:10:00Z'),
        ]
        items = currency_risk.detect(rows)
        self.assertEqual([item['kind'] for item in items], [])

    def test_single_thorn_over_five_thousand(self):
        items = currency_risk.detect([tx(1, free_delta=6000)])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['kind'], 'single')
        self.assertEqual(items[0]['amount'], 6000)
        self.assertEqual(items[0]['threshold'], 5000)

    def test_daily_thorn_total_over_twenty_thousand(self):
        rows = [
            tx(1, free_delta=8000, created_at='2026-11-12T01:00:00Z'),
            tx(2, free_delta=8000, created_at='2026-11-12T05:00:00Z'),
            tx(3, free_delta=5000, created_at='2026-11-12T09:00:00Z'),
        ]
        items = currency_risk.detect(rows)
        kinds = [item['kind'] for item in items]
        self.assertIn('daily', kinds)
        daily = next(item for item in items if item['kind'] == 'daily')
        self.assertEqual(daily['amount'], 21000)
        self.assertEqual(daily['threshold'], 20000)
        self.assertEqual(daily['count'], 3)

    def test_gold_thresholds_are_tighter(self):
        rows = [
            tx(1, currency='golden_dew', free_delta=6, created_at='2026-11-12T01:00:00Z'),
            tx(2, currency='golden_dew', free_delta=6, created_at='2026-11-12T01:02:00Z'),
        ]
        items = currency_risk.detect(rows)
        self.assertEqual([item['kind'] for item in items], ['duplicate'])
        self.assertEqual(items[0]['currency_label'], '金露')
        self.assertEqual(items[0]['threshold'], 5)

    def test_gold_daily_total_over_hundred(self):
        rows = [tx(index, currency='golden_dew', free_delta=20, created_at=f'2026-11-12T0{index}:00:00Z') for index in range(1, 7)]
        items = currency_risk.detect(rows)
        self.assertEqual([item['kind'] for item in items], ['daily'])
        self.assertEqual(items[0]['amount'], 120)

    def test_gold_spending_is_summed_by_absolute_value(self):
        rows = [
            tx(1, currency='golden_dew', free_delta=60, created_at='2026-11-12T01:00:00Z'),
            tx(2, currency='golden_dew', free_delta=-60, created_at='2026-11-12T02:00:00Z'),
        ]
        items = currency_risk.detect(rows)
        self.assertEqual([item['kind'] for item in items], ['daily'])
        self.assertEqual(items[0]['total'] if 'total' in items[0] else items[0]['amount'], 120)

    def test_users_and_currencies_are_scanned_separately(self):
        rows = [
            tx(1, user_id=1, free_delta=11000, created_at='2026-11-12T01:00:00Z'),
            tx(2, user_id=2, free_delta=11000, created_at='2026-11-12T01:00:00Z'),
            tx(3, user_id=1, currency='golden_dew', free_delta=60, created_at='2026-11-12T01:00:00Z'),
        ]
        items = currency_risk.detect(rows)
        # 两个玩家各一条单笔超额；荆露 11000 未到日流水线，金露 60 也未到 100。
        self.assertEqual([item['kind'] for item in items], ['single', 'single'])
        self.assertEqual({item['user_id'] for item in items}, {1, 2})
        self.assertTrue(all(item['currency'] == 'thorn_dew' for item in items))

    def test_items_sorted_by_latest_time_desc(self):
        rows = [
            tx(1, user_id=1, free_delta=6000, created_at='2026-11-12T01:00:00Z'),
            tx(2, user_id=2, free_delta=7000, created_at='2026-11-12T05:00:00Z'),
        ]
        items = currency_risk.detect(rows)
        self.assertEqual([item['last_at'] for item in items], [
            '2026-11-12T05:00:00Z',
            '2026-11-12T01:00:00Z',
        ])


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript('''
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE user_currency_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, currency TEXT, free_delta INTEGER, paid_delta INTEGER,
                reason TEXT, source_type TEXT, source_id TEXT, created_at TEXT
            );
        ''')
        self.conn.execute("INSERT INTO users (id, username) VALUES (1, 'Tester')")

    def tearDown(self):
        self.conn.close()

    def _insert(self, free_delta, created_at, currency='thorn_dew', user_id=1):
        self.conn.execute(
            'INSERT INTO user_currency_transactions (user_id, currency, free_delta, paid_delta, reason, source_type, source_id, created_at)'
            " VALUES (?, ?, ?, 0, 'test', 'pvp', 'm1', ?)",
            (user_id, currency, free_delta, created_at),
        )

    def test_scan_only_reads_the_requested_beijing_day(self):
        self._insert(6000, '2026-11-11T15:59:59Z')  # 北京时间 11-11 23:59:59
        self._insert(6000, '2026-11-11T16:00:00Z')  # 北京时间 11-12 00:00:00
        self.conn.commit()
        data = currency_risk.scan(self.conn, day='2026-11-12')
        self.assertEqual(data['day'], '2026-11-12')
        self.assertEqual(data['scanned'], 1)
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['counts'], {'single': 1})
        self.assertEqual(data['items'][0]['username'], 'Tester')

    def test_scan_returns_rules_for_the_ui(self):
        data = currency_risk.scan(self.conn, day='2026-11-12')
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['items'], [])
        self.assertEqual(data['rules']['thorn_dew']['daily_total'], 20000)
        self.assertEqual(data['rules']['golden_dew']['duplicate_amount'], 5)

    def test_scan_limit_is_clamped(self):
        for index in range(5):
            self._insert(6000 + index, f'2026-11-12T0{index + 1}:00:00Z')
        self.conn.commit()
        data = currency_risk.scan(self.conn, day='2026-11-12', limit=2)
        # 5 条单笔超额 + 1 条日流水超额（30010 > 20000）
        self.assertEqual(data['total'], 6)
        self.assertEqual(len(data['items']), 2)


class DayBoundsTests(unittest.TestCase):
    def test_beijing_day_converts_to_utc_window(self):
        start, end = currency_risk.day_bounds('2026-11-12')
        self.assertEqual(start, '2026-11-11T16:00:00Z')
        self.assertEqual(end, '2026-11-12T16:00:00Z')

    def test_beijing_today_accepts_epoch(self):
        # 2026-11-11T16:30:00Z == 北京时间 11-12 00:30
        epoch = datetime(2026, 11, 11, 16, 30, tzinfo=timezone.utc).timestamp()
        self.assertEqual(currency_risk.beijing_today(epoch), '2026-11-12')


if __name__ == '__main__':
    unittest.main()
