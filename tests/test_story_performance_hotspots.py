# -*- coding: utf-8 -*-
"""故事引擎热路径优化的行为与性能契约。"""

import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import story_engine as engine


class StoryPerformanceHotspotTests(unittest.TestCase):
    def test_checkpoint_excludes_old_checkpoints_before_deepcopy(self):
        player = {'deck': [{'def_id': 'basic', 'instance_id': 'card-1'}]}
        state = {
            'player': player,
            'players': [player],
            'map': {'floors': [{'nodes': []}]},
            'last_events': [{'type': 'old-event'}],
            'recovery_checkpoint': {'state': {'large': list(range(100))}},
            'floor_entry_checkpoint': {'state': {'large': list(range(100))}},
        }
        expected = copy.deepcopy(state)
        expected.pop('recovery_checkpoint', None)
        expected.pop('floor_entry_checkpoint', None)
        expected['last_events'] = []

        with patch('story_engine.copy.deepcopy', wraps=copy.deepcopy) as deepcopy_mock:
            snapshot = engine._checkpoint_snapshot(state)

        copied_input = deepcopy_mock.call_args_list[0].args[0]
        self.assertNotIn('recovery_checkpoint', copied_input)
        self.assertNotIn('floor_entry_checkpoint', copied_input)
        self.assertEqual(snapshot, expected)
        self.assertIs(snapshot['player'], snapshot['players'][0])
        self.assertIsNot(snapshot['map'], state['map'])

    def test_damage_prediction_has_no_overwritten_third_hit_calculation(self):
        state = {
            'player': {'relics': []},
            'combat': {'elixir': 3, 'magic': 0, 'turn_damage_multiplier': 1},
        }
        card = {'def_id': 'basic', 'instance_id': 'card-basic', 'upgraded': False}
        enemy = {'id': 'enemy-1', 'health': 30, 'shield': 0}
        with patch('story_engine._player_attack_hit_amount', wraps=engine._player_attack_hit_amount) as hit_mock:
            prediction = engine._card_damage_prediction(state, card, enemy)
        self.assertIsNotNone(prediction)
        self.assertEqual(hit_mock.call_count, 2)

    def test_projection_parses_each_hand_card_once(self):
        enemy_def_id = next(iter(engine.STORY_ENEMIES))
        state = {
            'player': {'relics': []},
            'combat': {
                'turn': 'player',
                'elixir': 3,
                'magic': 0,
                'hand': [
                    {'def_id': 'basic', 'instance_id': 'card-1', 'upgraded': False},
                    {'def_id': 'basic', 'instance_id': 'card-2', 'upgraded': False},
                ],
                'enemies': [{
                    'id': 'enemy-1', 'def_id': enemy_def_id,
                    'health': 30, 'max_health': 30, 'shield': 0, 'move_index': 0,
                }],
            },
        }
        with patch('story_engine._card_values', wraps=engine._card_values) as values_mock:
            engine._refresh_combat_projections(state)
        self.assertEqual(values_mock.call_count, 2)
        self.assertIn('card-1', state['combat']['damage_predictions'])
        self.assertIn('card-2', state['combat']['damage_predictions'])

    def test_playable_check_has_no_unused_hand_projection(self):
        source = Path(engine.__file__).read_text(encoding='utf-8')
        block = source.split('def _is_card_playable(', 1)[1].split('def _selected_cards(', 1)[0]
        self.assertNotIn('selectable_hand', block)


if __name__ == '__main__':
    unittest.main()
