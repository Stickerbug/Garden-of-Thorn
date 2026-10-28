# -*- coding: utf-8 -*-
"""操纵现实（2026-10-24）：全局事件引擎钩子回归测试。"""

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cards import CARD_DEFS, CardInstance
from game_engine import GameEngine
from game_engine_2v2 import GameEngine2v2
import reality_events


def make_engine(events, cls=GameEngine):
    e = cls()
    e.reality_events = set(events)
    e.phase = 'action'
    e.current_player = 0
    for p in e.players:
        p.health = 100
        p.max_health = 100
        p.base_max_health = 100
        p.elixir = 10
        p.magic = 10
        p.hand = []
        p.deck = []
        p.discard = []
        p.exile = []
        p.equipment = []
        p.custom_vars = {}
        p.skip_turn = 0
    return e


class RealityEventTests(unittest.TestCase):
    def test_all_20_events_defined(self):
        self.assertEqual(20, len(reality_events.REALITY_EVENTS))
        self.assertEqual(list(range(1, 21)), sorted(reality_events.REALITY_EVENTS))

    def test_draft_ratio_adjustments(self):
        base = {'thorn': 6, 'bloom': 4, 'root': 3, 'guard': 2}
        self.assertEqual(reality_events.reality_adjusted_draft_ratio(base, {1}),
                         {'thorn': 5, 'bloom': 5, 'root': 3, 'guard': 2})
        self.assertEqual(reality_events.reality_adjusted_draft_ratio(base, {9}),
                         {'thorn': 6, 'bloom': 6, 'root': 3, 'guard': 0})
        self.assertEqual(reality_events.reality_adjusted_draft_ratio(base, {17}),
                         {'thorn': 6, 'bloom': 4, 'root': 0, 'guard': 5})
        self.assertEqual(reality_events.reality_adjusted_draft_ratio(base, {19}),
                         {'thorn': 0, 'bloom': 0, 'root': 10, 'guard': 0})

    def test_health_bonus_events_4_and_6(self):
        e = make_engine({4})
        self.assertEqual(50, e.reality_initial_max_health_bonus())
        e = make_engine({4, 6})
        self.assertEqual(950, e.reality_initial_max_health_bonus())

    def test_regen_ramp_events_3_and_10(self):
        e = make_engine({3})
        self.assertEqual(-2, e.reality_elixir_recovery_modifier(0))
        e.players[0].custom_vars['reality_regen_ramp'] = 9
        self.assertEqual(7, e.reality_elixir_recovery_modifier(0))
        e = make_engine({10})
        self.assertEqual(5, e.reality_elixir_recovery_modifier(0))
        e.players[0].custom_vars['reality_regen_decay'] = 9
        self.assertEqual(0, e.reality_elixir_recovery_modifier(0))

    def test_extra_draw_events_2_and_5(self):
        e = make_engine({2, 5})
        self.assertEqual(7, e.reality_extra_draw_count(0))

    def test_third_card_stun_event_15(self):
        e = make_engine({15})
        cards = [CardInstance('Basic') for _ in range(3)]
        e.players[0].hand = list(cards)
        for card in cards:
            e.play_card(0, card.instance_id,
                        {'target_player': 1, 'target_player_id': 1, 'target_id': 1})
        self.assertEqual(1, e.players[0].skip_turn)

    def test_juggle_copies_the_third_card_with_void_and_exile(self):
        e = make_engine({16})
        cards = [CardInstance('Basic'), CardInstance('Bone'), CardInstance('Fire')]
        e.players[0].hand = list(cards)
        for card in cards:
            e.reality_after_card_played(0, card)
        granted = e.players[0].hand[-1]
        self.assertEqual('Fire', granted.def_id)
        self.assertNotEqual('Basic', granted.def_id)
        self.assertTrue({'ethereal', 'exile'} <= set(granted.instance_flags))
        self.assertNotEqual(cards[-1].instance_id, granted.instance_id)

    def test_played_card_to_opponent_event_18(self):
        e = make_engine({18})
        card = CardInstance('Basic')
        e.players[0].hand = [card]
        e.play_card(0, card.instance_id,
                    {'target_player': 1, 'target_player_id': 1, 'target_id': 1})
        self.assertEqual(['Basic'], [c.def_id for c in e.players[1].discard])
        self.assertEqual([], e.players[0].discard)

    def test_end_of_turn_events_2_and_13(self):
        e = make_engine({2, 13})
        e.players[0].hand = [CardInstance('Basic'), CardInstance('Bone')]
        e.reality_end_of_turn(0)
        self.assertEqual(0, len(e.players[0].hand))
        self.assertEqual(2, len(e.players[0].discard))

    def test_titan_multiplier_event_6(self):
        e = make_engine({6})
        e.reality_vars['titan_damage_multiplier'] = 3
        self.assertEqual(30, e._deal_direct_damage(1, 10, 'test', 0))

    def test_distinct_target_redirect_event_20(self):
        e = make_engine({20})
        c1, c2 = CardInstance('Basic'), CardInstance('Basic')
        e.players[0].hand = [c1, c2]
        e.play_card(0, c1.instance_id,
                    {'target_player': 1, 'target_player_id': 1, 'target_id': 1})
        e.play_card(0, c2.instance_id,
                    {'target_player': 1, 'target_player_id': 1, 'target_id': 1})
        self.assertEqual(0, e.players[0].custom_vars.get('reality_last_target'))

    def test_event_20_cancels_self_only(self):
        e = make_engine({20})
        e2 = make_engine(set())
        # 无事件时 self_only 正常判定（构造一个带标志的假卡难以直接建，此处只验证钩子开关）
        self.assertTrue(e.reality_cancel_target_restrictions())
        self.assertFalse(e2.reality_cancel_target_restrictions())

    def test_2v2_engine_has_reality_state(self):
        e = make_engine({5}, GameEngine2v2)
        self.assertTrue(e.reality_active(5))
        self.assertEqual(4, e.reality_extra_draw_count(0))


if __name__ == '__main__':
    unittest.main()
