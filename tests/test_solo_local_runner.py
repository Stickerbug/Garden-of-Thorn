# -*- coding: utf-8 -*-
"""本地单人训练场运行器的真实 Python 引擎回归。"""

import json
import unittest

import solo_local_runner as runner


class SoloLocalRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = json.loads(runner.initialize('{}'))
        assert result['success']
        assert result['card_count'] >= 300

    def setUp(self):
        self.start = json.loads(runner.dispatch('solo_start', {
            'deck0': ['Basic'] * 15,
            'deck1': ['Basic'] * 15,
        }))
        self.engine = runner._ENGINE

    def tearDown(self):
        runner.dispatch('solo_pause', {})

    def test_local_start_play_end_undo_and_redo(self):
        self.assertIsNotNone(self.engine)
        event_names = [name for name, _ in self.start['events']]
        self.assertIn('game_phase', event_names)
        self.assertIn('solo_state', event_names)
        state = next(data for name, data in self.start['events'] if name == 'solo_state')
        self.assertTrue(state['solo'])
        self.assertTrue(state['local_engine'])
        self.assertEqual(state['phase'], 'action')

        player = self.engine.current_player
        playable = next(
            card for card in self.engine.players[player].hand
            if self.engine.can_play_card(player, card)[0]
        )
        played = json.loads(runner.dispatch('solo_play_card', {
            'card_instance_id': playable.instance_id,
        }))
        self.assertFalse(any(name == 'server_error' for name, _ in played['events']))
        self.assertEqual(len(self.engine._solo_undo_stack), 1)

        ended = json.loads(runner.dispatch('solo_end_turn', {}))
        self.assertFalse(any(name == 'server_error' for name, _ in ended['events']))
        undone = json.loads(runner.dispatch('solo_undo', {}))
        self.assertFalse(any(name == 'server_error' for name, _ in undone['events']))
        redone = json.loads(runner.dispatch('solo_redo', {}))
        self.assertFalse(any(name == 'server_error' for name, _ in redone['events']))

    def test_prediction_next_draw_and_full_resync_are_local(self):
        player = self.engine.current_player
        card = self.engine.players[player].hand[0]
        predictions = json.loads(runner.dispatch('predict_hand', {
            'cards': [{'player_id': 0, 'instance_id': card.instance_id, 'target_player_id': 1}],
        }))
        payload = predictions['events'][0][1]
        self.assertIn(f'0:{card.instance_id}:1', payload['predictions'])

        changed = json.loads(runner.dispatch('solo_set_next_draw', {'def_ids': ['Basic']}))
        self.assertFalse(any(name == 'server_error' for name, _ in changed['events']))
        synced = json.loads(runner.dispatch('request_game_state', {}))
        self.assertTrue(any(name == 'solo_state' for name, _ in synced['events']))

    def test_counter_response_and_damage_prediction_are_local(self):
        started = json.loads(runner.dispatch('solo_start', {
            'deck0': ['Basic'] * 15,
            'deck1': ['Bubble'] * 15,
        }))
        self.engine = runner._ENGINE
        player = self.engine.current_player
        card = next(
            card for card in self.engine.players[player].hand
            if card.def_id == 'Basic' and self.engine.can_play_card(player, card)[0]
        )
        played = json.loads(runner.dispatch('solo_play_card', {
            'card_instance_id': card.instance_id,
        }))
        responses = [data for name, data in played['events'] if name == 'response_request']
        self.assertTrue(responses)
        counters = responses[0].get('counter_cards') or []
        self.assertTrue(any(item.get('def_id') == 'Bubble' for item in counters))
        self.assertIn('damage_prediction', responses[0])
        counter = next(item for item in counters if item.get('def_id') == 'Bubble')
        resolved = json.loads(runner.dispatch('solo_response', {
            'card_instance_id': counter['instance_id'],
        }))
        self.assertFalse(any(name == 'server_error' for name, _ in resolved['events']))

    def test_pause_requires_a_new_start(self):
        paused = json.loads(runner.dispatch('solo_pause', {}))
        self.assertEqual(paused['events'][0][0], 'solo_paused')
        missing = json.loads(runner.dispatch('solo_end_turn', {}))
        self.assertEqual(missing['events'][0][0], 'server_error')
        self.assertEqual(missing['events'][0][1]['message'], '训练场尚未开始')


if __name__ == '__main__':
    unittest.main()
