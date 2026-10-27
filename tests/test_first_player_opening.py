# -*- coding: utf-8 -*-
"""多人对战先手开局资源与「先手压制」（2026-10-27 改版）：

- 取消初始能量（0E），第1回合抽牌阶段在开局结算（不触发抽取效果），
  调度紧随其后；回复在各自第1回合开始时结算。
- 默认先手：起手 3 张牌、第1回合回复 5-2=3E；后手：起手 5 张牌（3+2）、第1回合回复 5E。
- 先手压制：尽可能获得先手（选择者中随机一人，双选也生效），
  选择者起手多 1 张牌、第1回合回复 +4E。
"""

import unittest

from cards import (
    FIRST_PLAYER_ELIXIR,
    FIRST_PLAYER_HAND_SIZE,
    INITIAL_ELIXIR,
    INITIAL_HAND_SIZE,
)
from game_engine import GameEngine
from game_engine_2v2 import GameEngine2v2


def _start_engine(opening=(1, 1)):
    engine = GameEngine()
    engine.phase = 'draft'
    for player_id in range(2):
        engine.opening_event_picks[player_id] = opening[player_id]
        engine.player_draft_started[player_id] = True
        engine.opening_event_sub_choices[player_id] = None
        first_allowed = engine.fated_draw_pool_defs()[0]
        engine.draft_picks[player_id] = [first_allowed] * engine.draft_target_count(player_id)
        engine.player_ready[player_id] = True
    engine.start_game(skip_pregame_validation=True, mulligan=False)
    return engine


class FirstPlayerOpeningTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(FIRST_PLAYER_HAND_SIZE, 3)
        self.assertEqual(FIRST_PLAYER_ELIXIR, 3)
        self.assertEqual(INITIAL_HAND_SIZE, 5)
        self.assertEqual(INITIAL_ELIXIR, 5)

    def test_default_first_player_gets_3_cards_3e(self):
        engine = _start_engine(opening=(1, 1))
        first = engine.players[engine.first_player]
        second = engine.players[1 - engine.first_player]
        # 2026-10-27：先手回复已在开局回合结算（5-2=3）；后手0E，待其回合回复。
        self.assertEqual(len(first.hand), 3)
        self.assertEqual(first.elixir, 3)
        self.assertEqual(len(second.hand), 5)
        self.assertEqual(second.elixir, 0)
        engine.end_turn(engine.first_player)
        self.assertEqual(second.elixir, 5)

    def test_opening_pressure_single_picker(self):
        engine = _start_engine(opening=(7, 1))
        first = engine.players[engine.first_player]
        self.assertEqual(engine.opening_event_picks[engine.first_player], 7)
        # 2026-10-27：+1张在起手；+4E并入第1回合回复（先手5-2+4=7）。
        self.assertEqual(len(first.hand), 4)
        self.assertEqual(first.elixir, 7)

    def test_opening_pressure_both_pick_still_applies_randomly(self):
        # 双选不再互相抵消：随机一人获得先手；增益与先手解耦——两个选择者
        # 都拿 +1 张 +4E（2026-10-11 调整：不论先手后手）。
        engine = _start_engine(opening=(7, 7))
        first = engine.players[engine.first_player]
        second = engine.players[1 - engine.first_player]
        self.assertEqual(engine.opening_event_picks[engine.first_player], 7)
        self.assertEqual(len(first.hand), 4)
        self.assertEqual(first.elixir, 7)
        self.assertEqual(len(second.hand), 6)   # 5+1
        # 2026-10-27：后手0E起步；+4E并入其第1回合回复（5+4=9）。
        self.assertEqual(second.elixir, 0)
        engine.end_turn(engine.first_player)
        self.assertEqual(second.elixir, 9)

    def test_opening_pressure_buff_only_for_pickers(self):
        # 只有对手选压制：对手得先手+增益；未选择者按普通后手结算（5张5E）。
        engine = _start_engine(opening=(1, 7))
        first = engine.players[engine.first_player]
        second = engine.players[1 - engine.first_player]
        self.assertEqual(engine.first_player, 1)
        self.assertEqual(len(first.hand), 4)
        self.assertEqual(first.elixir, 7)
        self.assertEqual(len(second.hand), 5)   # 普通后手 5 张
        # 2026-10-27：后手0E起步，其回合回复5E。
        self.assertEqual(second.elixir, 0)
        engine.end_turn(engine.first_player)
        self.assertEqual(second.elixir, 5)


class OpeningPressure2v2Tests(unittest.TestCase):
    def _engine_with_picks(self, picks):
        engine = GameEngine2v2()
        for pid, pick in enumerate(picks):
            engine.opening_event_picks[pid] = pick
        return engine

    def test_no_pickers_means_nobody_effective(self):
        engine = self._engine_with_picks([1, 1, 1, 1])
        self.assertEqual(engine._effective_first_pressure_players(), set())

    def test_effective_player_is_randomly_chosen_from_all_pickers(self):
        seen = set()
        for _ in range(60):
            # 两队各一人选择：不再按队伍人数比较，四个选择者都可能生效
            engine = self._engine_with_picks([7, 1, 7, 7])
            effective = engine._effective_first_pressure_players()
            self.assertEqual(len(effective), 1)
            self.assertIn(next(iter(effective)), {0, 2, 3})
            seen.add(next(iter(effective)))
        self.assertTrue({0, 2, 3} <= seen)


if __name__ == '__main__':
    unittest.main()
