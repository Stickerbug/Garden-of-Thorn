# -*- coding: utf-8 -*-
"""补发脚本：玩家皮肤入库、暗港背景从主题搬到战斗、重复执行不重复发放。"""
import gc
import importlib.util
import os
import tempfile
import unittest

import battle_pass as bp
import backgrounds
import db
import player_skins

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    'backfill_pass_cosmetics', os.path.join(ROOT, 'scripts', 'backfill_pass_cosmetics.py'))
backfill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backfill)


class PassCosmeticBackfillTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'backfill.sqlite3')
        db.init_db()
        self.user, err = db.create_user('BackfillUser1', 'Passw0rd!xyz')
        assert self.user, err
        self.uid = int(self.user['id'])
        with db.get_db_connection() as conn:
            bp.ensure_pass_schema(conn)
            player_skins.ensure_player_skin_schema(conn)
            backgrounds.ensure_background_schema(conn)
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            # Windows 上 WAL keeper 句柄释放略滞后，临时目录清不掉不影响断言。
            pass

    def test_dark_harbor_moves_from_theme_to_battle(self):
        with db.get_db_connection() as conn:
            conn.execute(
                '''INSERT INTO user_backgrounds
                   (user_id, kind, background_id, acquired_source, acquired_ref, acquired_at)
                   VALUES (?, 'theme', 'tower_curse_dark_harbor', 'battle_pass', 'pass:S1', '2026-11-12')''',
                (self.uid,),
            )
            conn.commit()
            result = backfill.migrate_dark_harbor(conn)
            conn.commit()
            kinds = [row['kind'] for row in conn.execute(
                'SELECT kind FROM user_backgrounds WHERE user_id = ? AND background_id = ?',
                (self.uid, 'tower_curse_dark_harbor'),
            ).fetchall()]
        self.assertEqual(result, {'moved': 1, 'removed': 1})
        self.assertEqual(kinds, ['battle'])

    def test_claimed_milestones_get_player_skins(self):
        with db.get_db_connection() as conn:
            for level in (30, 50):
                conn.execute(
                    '''INSERT INTO battle_pass_claims
                       (user_id, season_id, track, level, reward_json, claimed_at)
                       VALUES (?, ?, ?, ?, '{"kind":"card_skin"}', '2026-11-12')''',
                    (self.uid, bp.season_id(), bp.TRACK_FREE, level),
                )
            conn.commit()
            grants = backfill.backfill_claims(conn)
            conn.commit()
            owned = sorted(row['skin_id'] for row in conn.execute(
                'SELECT skin_id FROM user_player_skins WHERE user_id = ?', (self.uid,)).fetchall())
            again = backfill.backfill_claims(conn)
            conn.commit()
            owned_again = sorted(row['skin_id'] for row in conn.execute(
                'SELECT skin_id FROM user_player_skins WHERE user_id = ?', (self.uid,)).fetchall())
        self.assertEqual(owned, ['tower_curse_ironclad', 'tower_curse_silent'])
        self.assertEqual(owned_again, owned)
        self.assertEqual(len(grants), 2)
        # 再跑一遍：写入是 INSERT OR IGNORE，重复执行不会多出皮肤。
        self.assertEqual(owned_again, owned)

    def test_dry_run_writes_nothing(self):
        with db.get_db_connection() as conn:
            conn.execute(
                '''INSERT INTO user_backgrounds
                   (user_id, kind, background_id, acquired_source, acquired_ref, acquired_at)
                   VALUES (?, 'theme', 'tower_curse_dark_harbor', 'battle_pass', 'pass:S1', '2026-11-12')''',
                (self.uid,),
            )
            conn.commit()
            backfill.migrate_dark_harbor(conn, dry_run=True)
            kinds = [row['kind'] for row in conn.execute(
                'SELECT kind FROM user_backgrounds WHERE user_id = ?', (self.uid,)).fetchall()]
        self.assertEqual(kinds, ['theme'])


if __name__ == '__main__':
    unittest.main()
