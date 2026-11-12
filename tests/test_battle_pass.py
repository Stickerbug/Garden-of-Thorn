# -*- coding: utf-8 -*-
"""通行证：奖励表、经验公式、台账幂等、解锁与领取、黄金之路增益。"""

import gc
import os
import tempfile
import unittest
from datetime import datetime

import battle_pass as bp
import backgrounds
import db
import leisure_ticket
import player_skins


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
            player_skins.ensure_player_skin_schema(conn)
            backgrounds.ensure_background_schema(conn)
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
        self.assertEqual(bp.reward_for(10, bp.TRACK_GOLDEN)['kind'], 'player_skin')
        self.assertEqual(bp.reward_for(40, bp.TRACK_FREE)['kind'], 'golden_dew')
        self.assertEqual(bp.reward_for(40, bp.TRACK_GOLDEN)['amount'], 500)
        self.assertEqual(bp.reward_for(100, bp.TRACK_FREE)['kind'], 'player_skin')
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

    def test_pass_rewards_ignore_the_global_thorn_dew_multiplier(self):
        with self._conn() as conn:
            db.ensure_dew_gain_mod_table(conn)
            conn.execute(
                "UPDATE dew_gain_modifiers SET multiplicative = 2.5 WHERE id = 1")
            bp._apply_xp(conn, self.uid, 100, source='test', source_key='seed-mult')
            conn.commit()
        before = int(self._users_row()['thorn_dew_free'] or 0)
        with self._conn() as conn:
            payload, err = bp.claim(conn, self.uid, bp.TRACK_FREE, 1)
            conn.commit()
        self.assertIsNone(err)
        self.assertEqual(payload['reward']['amount'], 200)
        after = int(self._users_row()['thorn_dew_free'] or 0)
        # 通行证格子是定额奖励：全局荆露倍率（2.5x）不得放大，也不得缩水。
        self.assertEqual(after - before, 200)

        with self._conn() as conn:
            grant = bp.grant_checkin_xp(
                conn, self.uid, base_xp=40, checkin_date='2026-11-12')
            conn.commit()
        # 经验同样不吃荆露倍率，只吃黄金之路倍率（未解锁 → 1.0）。
        self.assertEqual(grant['xp'], 40)

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

    def test_track_entries_carry_reward_icons(self):
        """通行证格子上要有图标：皮肤/背景借实物素材，货币与道具用现成图标。"""
        with self._conn() as conn:
            payload = bp.state_payload(conn, self.uid)
            conn.commit()
        free = {entry['level']: entry for entry in payload['tracks'][bp.TRACK_FREE]['entries']}
        self.assertEqual(free[1]['icon'], '/static/assets/ui-icons/thorn-dew.svg')
        self.assertIn('/static/assets/leisure/tickets.svg', free[4]['icon'])
        self.assertEqual(free[5]['icon'], '/static/assets/ui-icons/golden-dew.svg')
        self.assertIn('/static/assets/player-avatars/tower-curse-ironclad.svg', free[30]['icon'])
        self.assertIn('/static/assets/ui-icons/gallery.svg', free[60]['icon'])
        golden = {entry['level']: entry for entry in payload['tracks'][bp.TRACK_GOLDEN]['entries']}
        self.assertIn('/static/assets/player-avatars/tower-curse-regent.svg', golden[10]['icon'])

    def test_track_entries_name_the_reward_type(self):
        """预览要写明白奖励类型：玩家皮肤 / 卡牌皮肤 / 主题背景 / 战斗背景 / 称号。"""
        with self._conn() as conn:
            payload = bp.state_payload(conn, self.uid)
            conn.commit()
        free = {entry['level']: entry for entry in payload['tracks'][bp.TRACK_FREE]['entries']}
        golden = {entry['level']: entry for entry in payload['tracks'][bp.TRACK_GOLDEN]['entries']}
        self.assertEqual(free[1]['type'], '')
        self.assertEqual(free[10]['type'], '称号')
        self.assertEqual(free[30]['type'], '玩家皮肤')
        self.assertEqual(free[60]['type'], '战斗背景')
        self.assertEqual(golden[10]['type'], '玩家皮肤')
        # 主题背景目前不在里程碑里，但类型标签本身要能区分（密林是主题背景）。
        self.assertEqual(bp.reward_type_label({'kind': 'background', 'item_id': 'tower_curse_deepwood'}), '主题背景')

    def test_levels_continue_past_one_hundred(self):
        """100 级不是终点：继续升级，轨道上要出现溢出格。"""
        with self._conn() as conn:
            bp._apply_xp(conn, self.uid, 12500, source='test', source_key='seed-12500')
            payload = bp.state_payload(conn, self.uid)
            conn.commit()
        self.assertEqual(payload['level'], 125)
        self.assertEqual(payload['max_level'], 125)
        self.assertEqual(payload['base_max_level'], 100)
        self.assertEqual(len(payload['tracks'][bp.TRACK_FREE]['entries']), 125)
        over = payload['tracks'][bp.TRACK_FREE]['entries'][100]  # 第 101 级
        self.assertEqual(over['level'], 101)
        self.assertEqual(over['reward']['kind'], 'dew')
        self.assertEqual(over['reward']['amount'], 100)
        self.assertTrue(over['reward']['overflow'])
        self.assertEqual(payload['overflow_rewards'][bp.TRACK_GOLDEN], '50 荆露')

    def test_overflow_level_can_be_claimed(self):
        """溢出格也要能领：101 级领 100 荆露。"""
        with self._conn() as conn:
            bp._apply_xp(conn, self.uid, 12500, source='test', source_key='seed-12500')
            before = conn.execute(
                'SELECT thorn_dew_free FROM users WHERE id = ?', (self.uid,)
            ).fetchone()['thorn_dew_free']
            result, error = bp.claim(conn, self.uid, bp.TRACK_FREE, 101)
            after = conn.execute(
                'SELECT thorn_dew_free FROM users WHERE id = ?', (self.uid,)
            ).fetchone()['thorn_dew_free']
            conn.commit()
        self.assertIsNone(error)
        self.assertEqual(result['level'], 101)
        self.assertEqual(int(after) - int(before), 100)

    def test_xp_reward_updates_feed_the_reward_animation(self):
        """长期奖励接口拿到的经验增量：正数、带来源、游标只前进。"""
        with self._conn() as conn:
            bp._apply_xp(conn, self.uid, 40, source='checkin', source_key='checkin:2026-11-12')
            bp._apply_xp(conn, self.uid, 60, source='story', source_key='story:9')
            first = bp.xp_reward_updates(conn, self.uid, 0)
            conn.commit()
        self.assertEqual([item['amount'] for item in first['items']], [40, 60])
        self.assertEqual(first['items'][0]['source_type'], 'checkin')
        self.assertEqual(first['items'][0]['reason'], '签到经验到账')
        self.assertEqual(first['items'][1]['reason'], '爬塔经验到账')
        self.assertEqual(first['cursor'], first['items'][-1]['id'])
        with self._conn() as conn:
            again = bp.xp_reward_updates(conn, self.uid, first['cursor'])
        self.assertEqual(again['items'], [])
        self.assertEqual(again['cursor'], first['cursor'])

    def test_milestone_cosmetics_resolve_to_real_catalogs(self):
        """里程碑只能发真实存在的皮肤/背景/称号，否则玩家领到的是空气。"""
        from backgrounds import get_background_definition
        from card_skins import SKIN_BY_ID

        from player_skins import PLAYER_SKIN_BY_ID

        for level, tracks in bp.MILESTONES.items():
            for track_key, reward in tracks.items():
                kind = reward['kind']
                if kind == 'card_skin':
                    self.assertIn(reward['item_id'], SKIN_BY_ID,
                                  f'{track_key} {level} 的皮肤 {reward["item_id"]} 不在目录里')
                    self.assertTrue(bp.cosmetic_name(kind, reward['item_id']))
                elif kind == 'player_skin':
                    self.assertIn(reward['item_id'], PLAYER_SKIN_BY_ID,
                                  f'{track_key} {level} 的玩家皮肤 {reward["item_id"]} 不在目录里')
                    self.assertTrue(bp.cosmetic_name(kind, reward['item_id']))
                    self.assertTrue(bp.reward_icon_url(reward).endswith('.svg'))
                elif kind == 'background':
                    background_kind, _ = bp.background_entry(reward['item_id'])
                    self.assertIsNotNone(bp.background_entry(reward['item_id'])[1],
                                         f'{track_key} {level} 的背景 {reward["item_id"]} 不在目录里')
                    self.assertTrue(bp.cosmetic_name(kind, reward['item_id']))
                    if reward['item_id'] == 'tower_curse_dark_harbor':
                        self.assertEqual(background_kind, 'battle')
                        self.assertIsNotNone(get_background_definition('battle', reward['item_id']))
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
                'SELECT COUNT(*) AS n FROM user_player_skins WHERE user_id = ? AND skin_id = ?',
                (self.uid, 'tower_curse_ironclad'),
            ).fetchone()['n']
            conn.commit()
        self.assertEqual(result['reward']['kind'], 'player_skin')
        self.assertEqual(owned, 1)

    def test_milestones_hand_out_all_five_tower_curse_player_skins(self):
        """五款「塔之诅咒」玩家皮肤都要在通行证里出场。"""
        granted = {
            reward['item_id']
            for tracks in bp.MILESTONES.values()
            for reward in tracks.values()
            if reward['kind'] == 'player_skin'
        }
        self.assertEqual(granted, {
            'tower_curse_ironclad',
            'tower_curse_silent',
            'tower_curse_defect',
            'tower_curse_necrobinder',
            'tower_curse_regent',
        })


    # ---- 控制台经验指令 ----

    def test_admin_adjust_xp_moves_levels_and_writes_ledger(self):
        result, error = bp.admin_adjust_xp(self.uid, 150, source='admin', reason='补偿', admin_username='console')
        self.assertEqual(error, '')
        self.assertEqual(result['applied'], 150)
        self.assertEqual(result['xp_total'], 150)
        self.assertEqual(result['level_before'], 0)
        self.assertEqual(result['level_after'], 1)

        with self._conn() as conn:
            rows = [dict(row) for row in conn.execute(
                'SELECT source, base_xp, xp, multiplier FROM battle_pass_xp_ledger WHERE user_id = ?',
                (self.uid,),
            ).fetchall()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['source'], 'admin')
        self.assertEqual(rows[0]['xp'], 150)

        result, error = bp.admin_adjust_xp(self.uid, -40, source='admin', admin_username='console')
        self.assertEqual(error, '')
        self.assertEqual(result['applied'], -40)
        self.assertEqual(result['xp_total'], 110)

    def test_admin_adjust_xp_never_drops_below_zero(self):
        result, error = bp.admin_adjust_xp(self.uid, -50, source='admin')
        self.assertIsNone(result)
        self.assertEqual(error, '累计经验已是 0，无法再扣除')

        bp.admin_adjust_xp(self.uid, 20, source='admin')
        result, error = bp.admin_adjust_xp(self.uid, -200, source='admin')
        self.assertEqual(error, '')
        self.assertEqual(result['applied'], -20)
        self.assertEqual(result['xp_total'], 0)

    def test_admin_adjust_xp_rejects_bad_arguments(self):
        self.assertEqual(bp.admin_adjust_xp(self.uid, 0, source='admin')[1], '调整数量不能为0')
        self.assertEqual(bp.admin_adjust_xp(self.uid, 10, source='nope')[1], '未知经验来源：nope')
        self.assertEqual(bp.admin_adjust_xp(self.uid, 'abc', source='admin')[1], '数量必须是整数')

    def test_admin_xp_summary_splits_by_source(self):
        with self._conn() as conn:
            bp._apply_xp(conn, self.uid, 40, source='match', source_key='m-1')
            bp._apply_xp(conn, self.uid, 60, source='story', source_key='s-1')
            bp._apply_xp(conn, self.uid, 25, source='checkin', source_key='c-1')
            conn.commit()
        summary = bp.admin_xp_summary(self.uid)
        self.assertEqual(summary['xp_total'], 125)
        self.assertEqual(summary['level'], 1)
        self.assertEqual(summary['xp_into_level'], 25)
        self.assertEqual(summary['by_source']['match']['xp'], 40)
        self.assertEqual(summary['by_source']['story']['xp'], 60)
        self.assertEqual(summary['by_source']['checkin']['xp'], 25)
        self.assertEqual(summary['by_source']['admin']['xp'], 0)

    def test_admin_list_xp_transactions_can_filter_source(self):
        bp.admin_adjust_xp(self.uid, 30, source='match')
        bp.admin_adjust_xp(self.uid, 70, source='story')
        self.assertEqual(len(bp.admin_list_xp_transactions(self.uid)), 2)
        only_story = bp.admin_list_xp_transactions(self.uid, source='story')
        self.assertEqual([row['source'] for row in only_story], ['story'])
        self.assertEqual(only_story[0]['xp'], 70)

    def test_xp_source_labels_cover_every_source(self):
        for source in bp.XP_SOURCES:
            self.assertIn(source, bp.XP_SOURCE_LABELS)
            self.assertTrue(bp.source_label(source))
            self.assertEqual(bp.normalize_source(source), source)
        self.assertEqual(bp.normalize_source('bogus'), '')
        self.assertEqual(bp.source_label('bogus'), 'bogus')

    def test_season_ends_on_november_30_2359(self):
        def stamp(*args):
            return datetime(*args, tzinfo=bp._CN_TZ).timestamp()

        start, end, active = bp.season_bounds(stamp(2026, 11, 15, 12, 0, 0))
        self.assertEqual(start, bp.PASS_SEASON_START)
        self.assertEqual((end.year, end.month, end.day, end.hour, end.minute), (2026, 11, 30, 23, 59))
        self.assertTrue(active)
        # 23:59 仍在赛季内，00:00（次日）已经结束。
        _, _, still_active = bp.season_bounds(stamp(2026, 11, 30, 23, 59, 30))
        self.assertTrue(still_active)
        _, _, closed = bp.season_bounds(stamp(2026, 12, 1, 0, 0, 1))
        self.assertFalse(closed)
        self.assertFalse(hasattr(bp, 'PASS_SEASON_WEEKS'))

    def test_season_payload_reports_the_new_window(self):
        with db.get_db_connection() as conn:
            bp.ensure_pass_schema(conn)
            payload = bp.state_payload(conn, self.uid)
            conn.commit()
        self.assertEqual(payload['season_end'][:10], '2026-11-30')
        self.assertEqual(payload['season_start'][:10], '2026-11-11')
        self.assertTrue(payload['season_active'])

    def test_xp_grants_stop_after_the_season_closes(self):
        closed = datetime(2026, 12, 1, 0, 0, 1, tzinfo=bp._CN_TZ).timestamp()
        with db.get_db_connection() as conn:
            bp.ensure_pass_schema(conn)
            result = bp.grant_match_xp(
                conn, self.uid, match_id='late-match', seconds=300, rounds=10, won=True, now=closed,
            )
            ledger = conn.execute(
                'SELECT COUNT(*) AS c FROM battle_pass_xp_ledger WHERE user_id = ?', (self.uid,),
            ).fetchone()
            conn.commit()
        self.assertFalse(result['applied'])
        self.assertEqual(result['reason'], 'season_closed')
        self.assertEqual(int(ledger['c']), 0)
        # 赛季内同样的对局照常发经验。
        inside = datetime(2026, 11, 20, 12, 0, 0, tzinfo=bp._CN_TZ).timestamp()
        with db.get_db_connection() as conn:
            allowed = bp.grant_match_xp(
                conn, self.uid, match_id='on-time-match', seconds=300, rounds=10, won=True, now=inside,
            )
            conn.commit()
        self.assertTrue(allowed['applied'])
        self.assertGreater(allowed['xp'], 0)


if __name__ == '__main__':
    unittest.main()
