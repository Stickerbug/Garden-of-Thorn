# -*- coding: utf-8 -*-
"""控制台通行证经验指令（account xp ...）的余额、来源与参数校验。"""

import gc
import os
import tempfile
import unittest

import app
import battle_pass as bp
import db


class BattlePassXpConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'pass-console.sqlite3')
        db.init_db()
        self.user, error = db.create_user('PassConsole', 'Aa1!aaaa')
        self.assertIsNone(error)
        self.uid = int(self.user['id'])
        with db.get_db_connection() as conn:
            bp.ensure_pass_schema(conn)
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def run_line(self, line):
        return app.execute_admin_command(line, actor='test-console')

    def test_add_xp_grants_level_and_writes_ledger(self):
        result = self.run_line(f"account xp add {self.user['username']} 120 测试发放")
        self.assertTrue(result['success'], result['output'])
        self.assertIn('累计经验：120', result['output'])
        self.assertIn('Lv.0 → Lv.1', result['output'])
        summary = bp.admin_xp_summary(self.uid)
        self.assertEqual(summary['xp_total'], 120)
        self.assertEqual(summary['level'], 1)
        self.assertEqual(summary['by_source']['admin']['xp'], 120)

    def test_addmatch_and_addstory_land_on_their_own_source(self):
        self.assertTrue(self.run_line(f"account xp addmatch {self.user['username']} 40 补发对局")['success'])
        self.assertTrue(self.run_line(f"account xp addstory {self.user['username']} 60 补发爬塔")['success'])
        summary = bp.admin_xp_summary(self.uid)
        self.assertEqual(summary['xp_total'], 100)
        self.assertEqual(summary['by_source']['match']['xp'], 40)
        self.assertEqual(summary['by_source']['story']['xp'], 60)

    def test_get_lists_every_source(self):
        self.run_line(f"account xp addmatch {self.user['username']} 30")
        result = self.run_line(f"account xp get {self.user['username']}")
        self.assertTrue(result['success'], result['output'])
        for label in ('对局经验', '爬塔经验', '签到经验', '管理调整'):
            self.assertIn(label, result['output'])

    def test_spend_cannot_push_total_below_zero(self):
        result = self.run_line(f"account xp spend {self.user['username']} 50")
        self.assertFalse(result['success'])
        self.assertIn('无法再扣除', result['output'])
        self.assertEqual(bp.admin_xp_summary(self.uid)['xp_total'], 0)

    def test_txstory_only_lists_story_rows(self):
        self.run_line(f"account xp addmatch {self.user['username']} 30 对局")
        self.run_line(f"account xp addstory {self.user['username']} 70 爬塔")
        result = self.run_line(f"account xp txstory {self.user['username']}")
        self.assertTrue(result['success'], result['output'])
        self.assertIn('爬塔经验+70', result['output'])
        self.assertNotIn('对局经验+30', result['output'])

    def test_unknown_account_and_bad_amount_are_reported(self):
        missing = self.run_line('account xp get 不存在的账号')
        self.assertFalse(missing['success'])
        self.assertIn('账号不存在', missing['output'])
        bad = self.run_line(f"account xp add {self.user['username']} 1.5")
        self.assertFalse(bad['success'])
        self.assertIn('数量必须是整数', bad['output'])
        zero = self.run_line(f"account xp add {self.user['username']} 0")
        self.assertFalse(zero['success'])
        self.assertIn('调整数量不能为0', zero['output'])


if __name__ == '__main__':
    unittest.main()
