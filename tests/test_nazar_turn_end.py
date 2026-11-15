"""邪眼（nazar）在自己回合结束时衰减：1v1 与 2v2 共用同一约定。

2v2 的 ``_end_player_turn`` 是独立实现，2026-11-15 之前漏掉了 1v1 里那段
邪眼衰减，导致邪眼在 2v2 永远不消失。现在两边都调用共享的
``_decay_nazar_turn_end``。测试用真实的 ``_nazar_status_value`` /
``_set_nazar_status_value`` 语义（通过注入卡牌数据里的 status_aliases
声明）验证行为。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_engine import GameEngine
from game_engine_2v2 import GameEngine2v2


NAZAR_ALIAS_DECLARATION = {
    'role': 'nazar',
    'canonical': 'nazar',
    'aliases': ['邪眼'],
    'legacy': {'active': 'nazar_active', 'hits': 'nazar_big_hits', 'max': 3},
}


class _NazarTurnEndMixin:
    engine_class = None
    player_count = 2

    def build_engine(self):
        engine = self.engine_class()
        engine.phase = 'action'
        engine.current_player = 0
        engine._status_alias_declarations = [dict(NAZAR_ALIAS_DECLARATION)]
        for player in engine.players:
            player.health = 100
            player.elixir = 10
            player.magic = 10
            player.hand = []
        return engine

    def test_nazar_loses_one_layer_at_the_end_of_your_turn(self):
        engine = self.build_engine()
        engine.players[0].custom_statuses['nazar'] = 2

        result = engine.end_turn(0)

        self.assertTrue(result.get('success'))
        self.assertEqual(engine._nazar_status_value(0), 1)
        self.assertFalse(any('邪眼效果消失' in line for line in engine.log))

    def test_last_nazar_layer_disappears_and_is_logged(self):
        engine = self.build_engine()
        engine.players[0].custom_statuses['nazar'] = 1

        result = engine.end_turn(0)

        self.assertTrue(result.get('success'))
        self.assertEqual(engine._nazar_status_value(0), 0)
        self.assertNotIn('nazar', engine.players[0].custom_statuses)
        self.assertTrue(any('邪眼效果消失' in line for line in engine.log))

    def test_other_players_nazar_is_not_decayed_by_your_turn_end(self):
        engine = self.build_engine()
        engine.players[0].custom_statuses['nazar'] = 1
        engine.players[1].custom_statuses['nazar'] = 2

        result = engine.end_turn(0)

        self.assertTrue(result.get('success'))
        self.assertEqual(engine._nazar_status_value(1), 2)


class NazarTurnEnd1v1Tests(_NazarTurnEndMixin, unittest.TestCase):
    engine_class = GameEngine
    player_count = 2


class NazarTurnEnd2v2Tests(_NazarTurnEndMixin, unittest.TestCase):
    engine_class = GameEngine2v2
    player_count = 4


if __name__ == '__main__':
    unittest.main()
