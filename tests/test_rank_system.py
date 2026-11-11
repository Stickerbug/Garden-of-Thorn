# -*- coding: utf-8 -*-
"""段位系统（设计 2026-10-02）：纯函数 + 对局结算集成 + 月度结算。

11 大段（Craft Eternal 顺序）× 4 小段（basic/sewage/disc/golden nazar）
共 44 段；胜利 +10+修正（至少 1、最多 20），失败 -6+修正（至少 1、最多 10）；胜利后到达上限
即升段（2026-10-11 平衡，取消两连胜要求）、归零后再败降段（0 分时保分卡
不拦截掉段）；每日（北京）前 5 局胜利翻倍；赛季末按 ultra 分界掉段，
段内分置 10，并按 30/100 局天梯对局发放基础／进阶奖励。花阶分（GR）只在后台运行。
"""

import os
import tempfile
import unittest
from unittest import mock

import rank_system as rs


class RankMathTests(unittest.TestCase):
    def test_tier_structure(self):
        self.assertEqual(44, rs.RANK_COUNT)
        self.assertEqual('common basic', rs.rank_label(1))
        self.assertEqual('common golden_nazar', rs.rank_label(4))
        self.assertEqual('unusual basic', rs.rank_label(5))
        self.assertEqual('eternal golden_nazar', rs.rank_label(44))
        self.assertEqual(20, rs.rank_cap(1))
        self.assertEqual(30, rs.rank_cap(5))
        self.assertEqual(50, rs.rank_cap(9))
        self.assertEqual(100, rs.rank_cap(13))
        self.assertEqual(200, rs.rank_cap(17))   # epic golden nazar → legendary 前沿
        self.assertEqual(500, rs.rank_cap(37))   # unique basic
        self.assertEqual(1000, rs.rank_cap(41))   # eternal basic
        self.assertEqual(1000, rs.rank_cap(44))

    def test_design_example(self):
        """设计用例：rare basic(9) 输给 rare golden nazar(12)。"""
        self.assertEqual(3, rs.match_loss(9, 12, 0))    # 6-3=3
        self.assertEqual(7, rs.match_gain(12, 9, 0))    # 10-3=7

    def test_win_loss_bounds(self):
        # 胜 +1~+20、败 -1~-10（封顶后再吃倍率）
        self.assertEqual(2, rs.match_gain(9, 1, 0))     # 10-8=2
        self.assertEqual(20, rs.match_gain(1, 44, 0))   # 大幅修正后封顶 20
        self.assertEqual(10, rs.match_loss(12, 1, 0))   # 6+11 → 封顶 10
        self.assertEqual(1, rs.match_loss(1, 44, 0))    # 大幅负修正后至少 1

    def test_promote_on_single_win_at_cap(self):
        """2026-10-11 平衡：满段后赢一局即升段（取消两连胜要求）。"""
        r1 = rs.apply_match_result(1, 20, 0, outcome='win', opponent_tier_avg=1)
        self.assertTrue(r1['promoted'])
        self.assertEqual(2, r1['tier_index'])
        self.assertEqual(0, r1['points'])
        # 2026-10-18：升段不再清零连胜（跨段继续累计，仅负/平清零）
        self.assertEqual(1, r1['streak'])

    def test_promote_when_win_fills_to_cap(self):
        """未满段的一胜只打到满（48+10 → 50/50），不升段；下一胜升。"""
        r = rs.apply_match_result(9, 48, 0, outcome='win', opponent_tier_avg=9)
        self.assertFalse(r['promoted'])
        self.assertEqual(9, r['tier_index'])
        self.assertEqual(50, r['points'])
        r2 = rs.apply_match_result(9, 50, 1, outcome='win', opponent_tier_avg=9)
        self.assertTrue(r2['promoted'])
        self.assertEqual(10, r2['tier_index'])

    def test_win_below_cap_counts_streak(self):
        """未到上限的胜利：普通连胜计数 +1，不升段。"""
        r = rs.apply_match_result(9, 10, 0, outcome='win', opponent_tier_avg=9)
        self.assertFalse(r['promoted'])
        self.assertEqual(20, r['points'])
        self.assertEqual(1, r['streak'])

    def test_cap_loss_breaks_streak(self):
        # unusual（tier5，cap30；loss 6→减半 3）
        r = rs.apply_match_result(5, 30, 1, outcome='loss', opponent_tier_avg=5)
        self.assertFalse(r['promoted'])
        self.assertEqual(0, r['streak'])
        self.assertEqual(27, r['points'])   # 30-ceil(6/2)

    def test_loss_shield_blocks_points_but_not_demotion_at_zero(self):
        """2026-10-11 平衡：保分卡 0 分时无法阻止掉段。"""
        r = rs.apply_match_result(12, 0, 3, outcome='loss', opponent_tier_avg=12, loss_shield=True)
        self.assertTrue(r['demoted'])
        self.assertEqual(11, r['tier_index'])
        self.assertEqual(50, r['points'])   # 降段后 = 新段上限
        self.assertFalse(r.get('shielded'))
        # 有分可保时照常拦截
        r2 = rs.apply_match_result(12, 10, 0, outcome='loss', opponent_tier_avg=12, loss_shield=True)
        self.assertTrue(r2.get('shielded'))
        self.assertFalse(r2['demoted'])
        self.assertEqual(10, r2['points'])

    def test_demote_at_zero(self):
        # 2026-10-02：common 不降段——改用 unusual basic（tier5）验证降段
        r = rs.apply_match_result(5, 0, 0, outcome='loss', opponent_tier_avg=5)
        self.assertTrue(r['demoted'])
        self.assertEqual(4, r['tier_index'])
        self.assertEqual(20, r['points'])   # 降段后 = 新段(common golden_nazar)上限

    def test_floor_no_demote(self):
        r = rs.apply_match_result(1, 0, 0, outcome='loss', opponent_tier_avg=1)
        self.assertFalse(r['demoted'])
        self.assertEqual(1, r['tier_index'])
        self.assertEqual(0, r['points'])

    def test_draw_breaks_streak_no_points(self):
        r = rs.apply_match_result(1, 20, 1, outcome='draw', opponent_tier_avg=1)
        self.assertEqual(20, r['points'])
        self.assertEqual(0, r['streak'])

    def test_daily_double_win_only_after_min(self):
        # 封顶 +20 之后再乘倍率；common 失败不掉分
        r = rs.apply_match_result(9, 10, 0, outcome='win', opponent_tier_avg=12, daily_double=True)
        # gain = min(20, 10+3) = 13 → ×2 = 26 → 36
        self.assertEqual(36, r['points'])
        self.assertTrue(r['daily_double'])
        # 封顶 +20 再翻倍：低段打高 44 → gain 封顶 20 → ×2=40 → cap(common)=20
        r2 = rs.apply_match_result(1, 0, 0, outcome='win', opponent_tier_avg=44, daily_double=True)
        self.assertEqual(20, r2['points'])
        # 失败不翻倍且 common 不掉分
        r3 = rs.apply_match_result(1, 5, 0, outcome='loss', opponent_tier_avg=1, daily_double=True)
        self.assertEqual(5, r3['points'])
        self.assertFalse(r3['daily_double'])

    def test_top_rank_no_promote(self):
        r = rs.apply_match_result(44, 1000, 1, outcome='win', opponent_tier_avg=44)
        self.assertFalse(r['promoted'])
        self.assertEqual(44, r['tier_index'])

    def test_migration(self):
        self.assertEqual((1, 0), rs.gr_to_rank(1000))
        self.assertEqual((1, 0), rs.gr_to_rank(980))
        self.assertEqual((4, 10), rs.gr_to_rank(1035))
        tier, _ = rs.gr_to_rank(1400)
        self.assertEqual(41, tier)   # eternal basic

    def test_monthly_settlement_rules(self):
        self.assertEqual(7, rs.monthly_settlement_tier(9))     # ultra 以下掉 2 个小段
        self.assertEqual(19, rs.monthly_settlement_tier(21))   # mythic basic 仍属 ultra 以下
        self.assertEqual(24, rs.monthly_settlement_tier(25))   # ultra basic 掉 1 个小段
        self.assertEqual(32, rs.monthly_settlement_tier(33))   # ultra 以上同样掉 1 个
        self.assertEqual(1, rs.monthly_settlement_tier(1))     # 最低段不再下降
        self.assertEqual(1, rs.monthly_settlement_tier(2))
        self.assertEqual(10, rs.SEASON_SETTLEMENT_POINTS)
        self.assertEqual(0, rs.settlement_reward_dew(12, 10, 29))
        self.assertEqual(
            5000 + rs.tier_to_absolute(12, 10) * 10,
            rs.settlement_reward_dew(12, 10, 30),
        )
        self.assertEqual(
            rs.settlement_reward_dew(12, 10, 30),
            rs.settlement_reward_dew(12, 10, 100),
        )
        self.assertEqual('S2', rs.season_name_for_month('2026-09'))
        self.assertEqual('S3', rs.season_name_for_month('2026-10'))
        self.assertEqual('S4', rs.season_name_for_month('2026-11'))

    def test_beijing_day_key(self):
        from datetime import datetime, timezone
        dt = datetime(2026, 10, 1, 16, 30, tzinfo=timezone.utc)   # 北京 10-02 00:30
        self.assertEqual('2026-10-02', rs.beijing_day_key(dt))
        self.assertEqual('2026-10', rs.beijing_month_key(dt))
        dt2 = datetime(2026, 10, 1, 15, 59, tzinfo=timezone.utc)  # 北京 10-01 23:59
        self.assertEqual('2026-10-01', rs.beijing_day_key(dt2))


class RankSettlementIntegrationTests(unittest.TestCase):
    def setUp(self):
        # 与 test_ranked_mode_contract 同款隔离：只换 db.DB_PATH，不换模块，
        # 避免污染同会话其他测试的 db 状态。
        import db
        self.db = db
        self._old_path = db.DB_PATH
        self.tmpdir = tempfile.mkdtemp()
        db.DB_PATH = os.path.join(self.tmpdir, 'rank_test.sqlite3')
        db.init_db()
        u1, e1 = db.create_user('RankA', 'Aa1!aaaa')
        u2, e2 = db.create_user('RankB', 'Aa1!aaaa')
        self.assertFalse(e1 or e2)
        self.uid1, self.uid2 = u1['id'], u2['id']

    def tearDown(self):
        self.db.DB_PATH = self._old_path

    def _set_rank(self, uid, tier, points=0):
        import sqlite3
        conn = sqlite3.connect(self.db.DB_PATH)
        conn.execute('UPDATE users SET rank_tier = ?, rank_points = ? WHERE id = ?', (tier, points, uid))
        conn.commit()
        conn.close()

    def _summary(self, **kwargs):
        base = {
            'match_type': 'ranked', 'match_mode': 'ranked_1v1', 'mode': '1v1',
            'valid_for_ranking': True, 'result': 'finished',
            'player_ids': [self.uid1, self.uid2],
            'ended_at': '2026-10-02T12:00:00Z',
        }
        base.update(kwargs)
        return base

    def test_match_settles_rank_with_daily_double(self):
        self._set_rank(self.uid1, 9)    # rare basic
        self._set_rank(self.uid2, 12)   # rare golden nazar
        res = self.db.apply_gr_match_result(91001, self._summary(winner_index=1, winner_user_ids=[self.uid2]))
        self.assertTrue(res.get('applied'))
        rank = res['rank']
        after1 = rank['after'][str(self.uid1)]
        after2 = rank['after'][str(self.uid2)]
        # 输家在 0 分再败 → 降段到 unusual golden nazar，分=上限30
        self.assertTrue(after1['demoted'])
        self.assertEqual(8, after1['tier_index'])
        self.assertEqual(30, after1['points'])
        # 赢家 +7（当日首局翻倍 → +14）
        self.assertEqual(14, after2['delta'])
        self.assertEqual(14, after2['points'])

    def test_settlement_idempotent(self):
        self._set_rank(self.uid1, 9)
        self._set_rank(self.uid2, 12)
        summary = self._summary(winner_index=1, winner_user_ids=[self.uid2])
        self.db.apply_gr_match_result(91002, summary)
        again = self.db.apply_gr_match_result(91002, summary)
        self.assertTrue(again.get('duplicate'))

    def test_monthly_settlement_grants_dew_and_demotes(self):
        self._set_rank(self.uid1, 12, 10)   # rare golden nazar，满 30 局
        self._set_rank(self.uid2, 1)        # common basic，不足 30 局
        base_dew = 5000 + rs.tier_to_absolute(12, 10) * 10
        with mock.patch.object(
            self.db,
            '_gr_season_valid_match_counts_for_conn',
            return_value={self.uid1: 30, self.uid2: 0},
        ) as count_mock:
            result = self.db.settle_ranks_monthly('2026-09')
        self.assertEqual('R1-S202609', count_mock.call_args.args[2])
        self.assertEqual(2, result['users'])
        self.assertEqual(1, result['base_rewards'])
        self.assertEqual(0, result['advanced_rewards'])
        self.assertEqual(base_dew, result['dew_total'])
        self.assertEqual(base_dew, self.db.get_user_thorn_dew(self.uid1).get('total'))
        self.assertEqual(0, self.db.get_user_thorn_dew(self.uid2).get('total'))
        row1 = self.db.get_user_by_id(self.uid1)
        row2 = self.db.get_user_by_id(self.uid2)
        self.assertEqual('rare sewage', row1['rank']['label'])
        self.assertEqual(10, row1['rank']['points'])
        self.assertEqual(1, row2['rank']['tier_index'])
        self.assertEqual(10, row2['rank']['points'])
        # 幂等：重复结算不重复发
        again = self.db.settle_ranks_monthly('2026-09')
        self.assertEqual(0, again['users'])
        self.assertEqual(base_dew, self.db.get_user_thorn_dew(self.uid1).get('total'))

    def test_advanced_season_reward_grants_title_and_extra_dew_once(self):
        self._set_rank(self.uid1, 25, 50)   # ultra basic，满 100 局
        self._set_rank(self.uid2, 22, 20)   # mythic sewage，99 局仅基础奖励
        base1 = 5000 + rs.tier_to_absolute(25, 50) * 10
        base2 = 5000 + rs.tier_to_absolute(22, 20) * 10
        with mock.patch.object(
            self.db,
            '_gr_season_valid_match_counts_for_conn',
            return_value={self.uid1: 100, self.uid2: 99},
        ):
            result = self.db.settle_ranks_monthly('2026-10')
        self.assertEqual(2, result['base_rewards'])
        self.assertEqual(1, result['advanced_rewards'])
        self.assertEqual(base1 + base2 + 5000, result['dew_total'])
        self.assertEqual(base1 + 5000, self.db.get_user_thorn_dew(self.uid1).get('total'))
        self.assertEqual(base2, self.db.get_user_thorn_dew(self.uid2).get('total'))
        self.assertEqual(24, self.db.get_user_by_id(self.uid1)['rank']['tier_index'])
        self.assertEqual(20, self.db.get_user_by_id(self.uid2)['rank']['tier_index'])
        titles1 = self.db.list_user_titles(self.uid1)
        participant = next(item for item in titles1 if item['id'] == 'season:s3-participant')
        self.assertEqual('S3赛季参与者', participant['name'])
        self.assertFalse(any(item['id'] == 'season:s3-participant' for item in self.db.list_user_titles(self.uid2)))
        transactions = self.db.list_user_thorn_dew_transactions(self.uid1, limit=10)
        self.assertEqual(
            {'rank_season_base', 'rank_season_advanced'},
            {item['source_type'] for item in transactions if item['source_type'].startswith('rank_season_')},
        )
        again = self.db.settle_ranks_monthly('2026-10')
        self.assertEqual(0, again['users'])
        self.assertEqual(base1 + 5000, self.db.get_user_thorn_dew(self.uid1).get('total'))
        self.assertEqual(len(titles1), len(self.db.list_user_titles(self.uid1)))

    def test_special_correction_stacks(self):
        self.db.set_rank_global_special(1.0)
        self.db.set_user_rank_special('RankA', 0.5)
        self._set_rank(self.uid1, 9)
        self._set_rank(self.uid2, 9, 10)
        res = self.db.apply_gr_match_result(91003, self._summary(winner_index=0, winner_user_ids=[self.uid1]))
        # RankA 胜：10+0+1.5=11.5 → 12；双倍日 → 24
        after1 = res['rank']['after'][str(self.uid1)]
        self.assertEqual(24, after1['points'])
        # RankB 负：6-0-1.5=4.5 → 5（不翻倍）
        after2 = res['rank']['after'][str(self.uid2)]
        self.assertEqual(-5, after2['delta'])
        self.assertEqual(5, after2['points'])

    def test_preview_rank_match(self):
        self._set_rank(self.uid1, 9)
        self._set_rank(self.uid2, 12)
        preview = self.db.preview_rank_match_result('1v1', [self.uid1, self.uid2], viewer_user_id=self.uid2)
        self.assertTrue(preview['applied'])
        viewer = preview['viewer']
        self.assertEqual('rare golden_nazar', viewer['label'])
        # 新账号当日首胜 → 每日双倍 ×2（#351 预估口径与结算对齐）
        self.assertTrue(viewer.get('daily_double_active'))
        self.assertEqual(14, viewer['win_delta'])
        self.assertEqual(9, viewer['loss_delta'])    # 6+3=9；输不参与双倍

    def test_user_payload_has_rank_no_gr_leak(self):
        payload = self.db.user_rank_payload(self.uid1)
        self.assertEqual('common basic', payload['label'])
        user = self.db.get_user_by_id(self.uid1)
        self.assertIn('rank', user)


if __name__ == '__main__':
    unittest.main()
