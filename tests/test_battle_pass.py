# -*- coding: utf-8 -*-
"""通行证：奖励表、经验公式、台账幂等、解锁与领取、黄金之路增益。"""

import gc
import os
import tempfile
import unittest

import battle_pass as bp
import db
import leisure_ticket


class BattlePassTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'battle-pass.sqlite3')
        db.init_db()
        self.user, err = db.create_user('PassOwner1', 'Passw0rd!xyz')
        assert self.user, err
        self.uid = int(self.user['id'])
        with db.get_db_connection() as conn:
            bp.ensure_pass_schema(conn)
            leisure_ticket.ensure_ticket_columns(conn)
            conn.execute('UPDATE users SET golden_dew = 0 WHERE id = ?', (self.uid,))
            conn.commit()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def _conn(self):
        return db.get_db_connection()

    def _set_golden(self, amount):
        with db.get_db_connection() as conn:
            conn.execute('UPDATE users SET golden_dew = ? WHERE id = ?', (int(amount), self.uid))
            conn.commit()

    def _users_row(self):
        with db.get_db_connection() as conn:
            return conn.execute(
                'SELECT golden_dew, thorn_dew_free, rank_shield_cards, rank_double_cards, leisure_tickets '
                'FROM users WHERE id = ?', (self.uid,)
            ).fetchone()

    # ---- 奖励表 ----

    def test_reward_pattern_repeats_every_ten_levels(self):
        for level in (1, 11, 21, 91):
            reward = bp.reward_for(level, bp.TRACK_FREE)
            self.assertEqual(reward['kind'], 'dew')
            self.assertEqual(reward['amount'], 200)
            self.assertFalse(reward['overflow'])
        for level in (2, 12, 22):
            self.assertEqual(bp.reward_for(level, bp.TRACK_FREE)['kind'], 'shield_card')
        for level in (1, 11):
            self.assertEqual(bp.reward_for(level, bp.TRACK_GOLDEN)['kind'], 'shield_card')
        for level in (2, 12):
            golden = bp.reward_for(level, bp.TRACK_GOLDEN)
            self.assertEqual((golden['kind'], golden['amount']), ('dew', 100))

    def test_milestone_levels_use_explicit_table(self):
        self.assertEqual(bp.reward_for(10, bp.TRACK_FREE)['kind'], 'title')
        self.assertEqual(bp.reward_for(10, bp.TRACK_GOLDEN)['kind'], 'card_skin')
        self.assertEqual(bp.reward_for(40, bp.TRACK_FREE)['kind'], 'golden_dew')
        self.assertEqual(bp.reward_for(40, bp.TRACK_GOLDEN)['amount'], 500)
        self.assertEqual(bp.reward_for(100, bp.TRACK_FREE)['kind'], 'card_skin')
        for level in range(10, 101, 10):
            self.assertIsNotNone(bp.reward_for(level, bp.TRACK_FREE))
            self.assertIsNotNone(bp.reward_for(level, bp.TRACK_GOLDEN))

    def test_levels_above_max_pay_overflow_dew(self):
        free = bp.reward_for(101, bp.TRACK_FREE)
        golden = bp.reward_for(150, bp.TRACK_GOLDEN)
        self.assertTrue(free['overflow'])
        self.assertEqual((free['kind'], free['amount']), ('dew', 100))
        self.assertEqual((golden['kind'], golden['amount']), ('dew', 50))
        self.assertIsNone(bp.reward_for(0, bp.TRACK_FREE))

    # ---- 经验公式 ----

    def test_match_xp_takes_the_smallest_of_three_limits(self):
        self.assertEqual(bp.match_xp(600, 20, False), 40)   # 时间封顶
        self.assertEqual(bp.match_xp(100, 3, False), 10)    # 时间限制 (ceil(100/10))
        self.assertEqual(bp.match_xp(100, 1, False), 5)     # 回合限制
        self.assertEqual(bp.match_xp(0, 0, False), 0)
        self.assertEqual(bp.match_xp(100, 3, True), 15)     # 胜 ×1.5
        self.assertEqual(bp.match_xp(1000, 100, True), 60)  # 40 × 1.5
        self.assertEqual(bp.match_xp(None, None, False), 0)

    def test_story_xp_follows_score_over_five(self):
        self.assertEqual(bp.story_xp(0), 0)
        self.assertEqual(bp.story_xp(5), 1)
        self.assertEqual(bp.story_xp(100), 20)
        self.assertEqual(bp.story_xp(5000), 1000)
        self.assertEqual(bp.story_xp(50000), 1000)  # 封顶

    def test_level_advances_every_hundred_xp(self):
        self.assertEqual(bp.level_for_xp(0), 0)
        self.assertEqual(bp.level_for_xp(99), 0)
        self.assertEqual(bp.level_for_xp(100), 1)
        self.assertEqual(bp.level_for_xp(250), 2)
        self.assertEqual(bp.xp_into_level(250), 50)

    # ---- 台账 ----

    def test_xp_ledger_is_idempotent_per_source_key(self):
        with self._conn() as conn:
            first = bp.grant_match_xp(conn, self.uid, match_id='m1', seconds=100, rounds=3, won=False)
            second = bp.grant_match_xp(conn, self.uid, match_id='m1', seconds=100, rounds=3, won=False)
            total = conn.execute(
                'SELECT COUNT(*) AS n FROM battle_pass_xp_ledger WHERE user_id = ?', (self.uid,)
            ).fetchone()['n']
            conn.commit()
        self.assertTrue(first['applied'])
        self.assertEqual(first['xp'], 10)
        self.assertFalse(second['applied'])
        self.assertEqual(second['reason'], 'duplicate')
        self.assertEqual(total, 1)
        self.assertEqual(bp.xp_total(self._conn_read(), self.uid), 10)

    def _conn_read(self):
        return db.get_db_connection()

    def test_story_weekly_first_three_runs_are_tripled(self):
        gains = []
        with self._conn() as conn:
            for run_id in (1, 2, 3, 4):
                result = bp.grant_story_xp(conn, self.uid, run_id=run_id, score=100)
                gains.append(result['xp'])
            used = conn.execute(
                'SELECT used FROM battle_pass_story_week WHERE user_id = ?', (self.uid,)
            ).fetchone()['used']
            conn.commit()
        self.assertEqual(gains, [60, 60, 60, 20])
        self.assertEqual(used, 3)

    # ---- 解锁与领取 ----

    def test_claim_requires_level_then_pays_once(self):
        with self._conn() as conn:
            payload, err = bp.claim(conn, self.uid, bp.TRACK_FREE, 1)
            conn.commit()
        self.assertIsNone(payload)
        self.assertEqual(err, '等级不足')

        with self._conn() as conn:
            bp._apply_xp(conn, self.uid, 100, source='test', source_key='seed-100')
            conn.commit()
        before = int(self._users_row()['thorn_dew_free'] or 0)
        with self._conn() as conn:
            payload, err = bp.claim(conn, self.uid, bp.TRACK_FREE, 1)
            conn.commit()
        self.assertIsNone(err)
        self.assertEqual(payload['level'], 1)
        after = int(self._users_row()['thorn_dew_free'] or 0)
        self.assertEqual(after - before, 200)

        with self._conn() as conn:
            payload, err = bp.claim(conn, self.uid, bp.TRACK_FREE, 1)
            conn.commit()
        self.assertIsNone(payload)
        self.assertEqual(err, '已经领取过了')

    def test_golden_track_is_locked_until_purchased(self):
        with self._conn() as conn:
            bp._apply_xp(conn, self.uid, 100, source='test', source_key='seed-100')
            conn.commit()
            payload, err = bp.claim(conn, self.uid, bp.TRACK_GOLDEN, 1)
            conn.commit()
        self.assertIsNone(payload)
        self.assertEqual(err, '需要先解锁黄金之路')

        self._set_golden(300)
        with self._conn() as conn:
            info, err = bp.purchase_golden(conn, self.uid)
            conn.commit()
        self.assertIsNone(err)
        self.assertEqual(info['golden_dew'], 50)
        with self._conn() as conn:
            _, err2 = bp.purchase_golden(conn, self.uid)
            conn.commit()
        self.assertEqual(err2, '已经解锁黄金之路')

        shield_before = int(self._users_row()['rank_shield_cards'] or 0)
        with self._conn() as conn:
            payload, err = bp.claim(conn, self.uid, bp.TRACK_GOLDEN, 1)
            conn.commit()
        self.assertIsNone(err)
        self.assertEqual(int(self._users_row()['rank_shield_cards'] or 0), shield_before + 1)

    def test_purchase_requires_enough_golden_dew(self):
        self._set_golden(249)
        with self._conn() as conn:
            info, err = bp.purchase_golden(conn, self.uid)
            conn.commit()
        self.assertIsNone(info)
        self.assertEqual(err, '金露不足')
        self.assertFalse(bp.golden_active(self._conn_read(), self.uid))

    # ---- 黄金之路增益 ----

    def test_golden_multiplies_checkin_xp_and_dew(self):
        with self._conn() as conn:
            base = bp.preview_checkin_xp(conn, self.uid, 100)
            plain = bp.grant_checkin_xp(conn, self.uid, base_xp=100, checkin_date='2026-11-11')
            conn.commit()
        self.assertEqual(base, 100)
        self.assertEqual(plain['xp'], 100)

        self._set_golden(300)
        with self._conn() as conn:
            bp.purchase_golden(conn, self.uid)
            preview = bp.preview_checkin_xp(conn, self.uid, 100)
            boosted = bp.grant_checkin_xp(conn, self.uid, base_xp=100, checkin_date='2026-11-12')
            dew = bp.apply_golden_dew(conn, self.uid, 100)
            conn.commit()
        self.assertEqual(preview, 150)
        self.assertEqual(boosted['xp'], 150)
        self.assertEqual(dew, 150)

    def test_plain_account_does_not_get_golden_perks(self):
        with self._conn() as conn:
            self.assertEqual(bp.golden_xp_multiplier(conn, self.uid), 1.0)
            self.assertEqual(bp.golden_dew_multiplier(conn, self.uid), 1.0)
            self.assertEqual(bp.golden_rank_special_bonus(conn, self.uid), 0.0)
            self.assertEqual(bp.apply_golden_dew(conn, self.uid, 100), 100)
            conn.commit()

    def test_state_payload_lists_both_tracks(self):
        with self._conn() as conn:
            bp._apply_xp(conn, self.uid, 250, source='test', source_key='seed-250')
            payload = bp.state_payload(conn, self.uid)
            conn.commit()
        self.assertEqual(payload['level'], 2)
        self.assertEqual(payload['xp_into_level'], 50)
        self.assertEqual(len(payload['tracks'][bp.TRACK_FREE]['entries']), 100)
        self.assertEqual(len(payload['tracks'][bp.TRACK_GOLDEN]['entries']), 100)
        self.assertEqual(payload['claimable'][bp.TRACK_FREE], [1, 2])
        self.assertEqual(payload['claimable'][bp.TRACK_GOLDEN], [])  # 未解锁
        self.assertFalse(payload['golden'])
        self.assertEqual(payload['golden_price'], 250)

    def test_milestone_cosmetics_resolve_to_real_catalogs(self):
        """里程碑只能发真实存在的皮肤/背景/称号，否则玩家领到的是空气。"""
        from backgrounds import get_background_definition
        from card_skins import SKIN_BY_ID

        for level, tracks in bp.MILESTONES.items():
            for track_key, reward in tracks.items():
                kind = reward['kind']
                if kind == 'card_skin':
                    self.assertIn(reward['item_id'], SKIN_BY_ID,
                                  f'{track_key} {level} 的皮肤 {reward["item_id"]} 不在目录里')
                    self.assertTrue(bp.cosmetic_name(kind, reward['item_id']))
                elif kind == 'background':
                    self.assertIsNotNone(get_background_definition('theme', reward['item_id']),
                                         f'{track_key} {level} 的背景 {reward["item_id"]} 不在目录里')
                    self.assertTrue(bp.cosmetic_name(kind, reward['item_id']))
                elif kind == 'title':
                    self.assertIn(reward['item_id'], bp.PASS_TITLES,
                                  f'{track_key} {level} 的称号 {reward["item_id"]} 未登记')

    def test_pass_titles_share_the_season_name_and_differ_by_paint(self):
        """10 级与 20 级都叫「塔之诅咒」，只是灰色 / 彩色两种样式。"""
        import title_styles

        free = bp.PASS_TITLES[bp._TITLE_FREE]
        golden = bp.PASS_TITLES[bp._TITLE_GOLDEN]
        self.assertEqual(free['name'], '塔之诅咒')
        self.assertEqual(golden['name'], '塔之诅咒')
        self.assertNotEqual(free['markup'], golden['markup'])
        free_style = title_styles.parse_title_style(free['markup'])
        golden_style = title_styles.parse_title_style(golden['markup'])
        free_paint = free_style['segments'][0]['paint']
        golden_paint = golden_style['segments'][0]['paint']
        self.assertEqual(free_paint['kind'], 'solid')
        self.assertEqual(golden_paint['kind'], 'rainbow')
        self.assertGreaterEqual(len(golden_paint['colors']), 4)

        with self._conn() as conn:
            bp.ensure_pass_titles(conn)
            rows = {
                row['title_id']: dict(row)
                for row in conn.execute(
                    "SELECT title_id, name, color, style_markup FROM title_catalog WHERE source_type = 'battle_pass'")
            }
        self.assertEqual(rows[bp._TITLE_FREE]['name'], '塔之诅咒')
        self.assertEqual(rows[bp._TITLE_GOLDEN]['name'], '塔之诅咒')
        self.assertEqual(rows[bp._TITLE_FREE]['style_markup'], free['markup'])
        self.assertEqual(rows[bp._TITLE_GOLDEN]['style_markup'], golden['markup'])

    def test_claiming_a_skin_milestone_grants_ownership(self):
        with self._conn() as conn:
            bp._apply_xp(conn, self.uid, 3000, source='test', source_key='seed-3000')
            result, error = bp.claim(conn, self.uid, bp.TRACK_FREE, 30)
            self.assertIsNone(error)
            owned = conn.execute(
                'SELECT COUNT(*) AS n FROM user_card_skins WHERE user_id = ? AND skin_id = ?',
                (self.uid, 'tower_curse_ironclad'),
            ).fetchone()['n']
            conn.commit()
        self.assertEqual(result['reward']['kind'], 'card_skin')
        self.assertEqual(owned, 1)


if __name__ == '__main__':
    unittest.main()
