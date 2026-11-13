# -*- coding: utf-8 -*-
"""Contract tests for the canonical digest helpers shared with the browser engine."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import story_verify


class CanonicalJsonTests(unittest.TestCase):
    def test_key_order_and_whitespace_do_not_change_the_digest(self):
        left = {'b': 1, 'a': {'d': [1, 2], 'c': '中文'}}
        right = {'a': {'c': '中文', 'd': [1, 2]}, 'b': 1}
        self.assertEqual(story_verify.canonical_json(left), story_verify.canonical_json(right))
        self.assertEqual(story_verify.state_digest(left), story_verify.state_digest(right))

    def test_floats_keep_round_trip_form(self):
        self.assertEqual(story_verify.canonical_json({'x': 1.5}), '{"x":1.5}')
        self.assertEqual(story_verify.canonical_json({'x': 0.1}), '{"x":0.1}')
        # 1 和 1.0 在 JSON 里是不同文本，摘要也必须区分
        self.assertNotEqual(story_verify.state_digest({'x': 1}), story_verify.state_digest({'x': 1.0}))

    def test_nan_and_infinity_are_rejected(self):
        for bad in (float('nan'), float('inf'), float('-inf')):
            with self.assertRaises(ValueError):
                story_verify.canonical_json({'x': bad})

    def test_digest_format(self):
        digest = story_verify.state_digest({'phase': 'map'})
        self.assertTrue(story_verify.is_digest(digest))
        self.assertFalse(story_verify.is_digest('sha256:xyz'))
        self.assertFalse(story_verify.is_digest(None))


class ChainDigestTests(unittest.TestCase):
    ACTIONS = [
        {'id': 'a1', 'type': 'play_card', 'payload': {'card_id': 'strike'}},
        {'id': 'a2', 'type': 'end_turn', 'payload': {}},
    ]

    def test_chain_is_stable_and_ignores_action_ids(self):
        head = story_verify.state_digest({'phase': 'combat'})
        first = story_verify.chain_digest(head, self.ACTIONS, 'sha256:aa')
        renamed = [dict(action, id='other-%s' % action['id']) for action in self.ACTIONS]
        self.assertEqual(first, story_verify.chain_digest(head, renamed, 'sha256:aa'))

    def test_reordering_or_truncation_changes_the_chain(self):
        head = story_verify.state_digest({'phase': 'combat'})
        base = story_verify.chain_digest(head, self.ACTIONS, 'sha256:aa')
        self.assertNotEqual(base, story_verify.chain_digest(head, self.ACTIONS[::-1], 'sha256:aa'))
        self.assertNotEqual(base, story_verify.chain_digest(head, self.ACTIONS[:1], 'sha256:aa'))
        self.assertNotEqual(base, story_verify.chain_digest(head, self.ACTIONS, 'sha256:bb'))
        self.assertNotEqual(base, story_verify.chain_digest('sha256:cc', self.ACTIONS, 'sha256:aa'))

    def test_empty_action_list_still_binds_previous_and_final(self):
        value = story_verify.chain_digest('sha256:00', [], 'sha256:11')
        self.assertTrue(story_verify.is_digest(value))
        self.assertNotEqual(value, story_verify.chain_digest('sha256:00', [], 'sha256:12'))


if __name__ == '__main__':
    unittest.main()

class HostProjectionTests(unittest.TestCase):
    def test_host_fields_are_ignored_by_the_checkpoint_digest(self):
        base = {'phase': 'combat', 'current_floor': 3, 'player': {'hp': 20}}
        server = dict(base, dev_mode=False, event_bank=120, sl_used=True,
                      last_events=[{'type': 'x'}],
                      floor_entry_checkpoint={'state': {'phase': 'room'}},
                      recovery_checkpoint={'state': {'phase': 'combat'}})
        self.assertEqual(story_verify.state_digest(base), story_verify.state_digest(server))
        self.assertNotEqual(
            story_verify.state_digest(base, include_host=True),
            story_verify.state_digest(server, include_host=True),
        )

    def test_gameplay_fields_still_change_the_digest(self):
        base = {'phase': 'combat', 'current_floor': 3, 'player': {'hp': 20}}
        changed = {'phase': 'combat', 'current_floor': 3, 'player': {'hp': 19}}
        self.assertNotEqual(story_verify.state_digest(base), story_verify.state_digest(changed))

    def test_gameplay_state_projection_keeps_nested_keys(self):
        state = {'phase': 'combat', 'combat': {'seat_states': {0: {'elixir': 3}}}, 'dev_mode': True}
        projection = story_verify.gameplay_state(state)
        self.assertNotIn('dev_mode', projection)
        self.assertEqual(projection['combat']['seat_states'][0]['elixir'], 3)

class ReplayCheckpointTests(unittest.TestCase):
    SEED = 'replay-checkpoint-seed'
    START_ACTIONS = [
        {'type': 'start_journey', 'payload': {'biome': '', 'difficulty': 'normal', 'mode': 'standard'}},
    ]

    def _initial(self):
        import story_mode
        return story_mode.build_initial_story_state(self.SEED, character_id='common_flower')

    def test_a_valid_log_replays_to_the_client_digest(self):
        result = story_verify.replay_checkpoint(self._initial(), self.START_ACTIONS, self.SEED)
        self.assertTrue(result['ok'])
        self.assertEqual(result['reason'], None)
        self.assertEqual(result['actions'], 1)
        self.assertTrue(story_verify.is_digest(result['digest']))
        self.assertEqual(result['state']['phase'], 'blessing')

    def test_expected_digest_mismatch_is_reported_not_raised(self):
        result = story_verify.replay_checkpoint(
            self._initial(), self.START_ACTIONS, self.SEED,
            expected_digest='sha256:' + '0' * 64,
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'mismatch')
        self.assertTrue(story_verify.is_digest(result['digest']))

    def test_invalid_action_type_is_rejected(self):
        result = story_verify.replay_checkpoint(
            self._initial(), [{'type': 'dev_grant_everything', 'payload': {}}], self.SEED,
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'invalid_action')
        self.assertTrue(result['error'])

    def test_action_log_shape_is_validated(self):
        for bad in ('nope', [1], [{'payload': {}}], [{'type': 'x', 'payload': []}]):
            result = story_verify.replay_checkpoint(self._initial(), bad, self.SEED)
            self.assertFalse(result['ok'], bad)
            self.assertIn(result['reason'], {'actions_not_list', 'action_not_object', 'action_type_missing', 'action_payload_invalid'})

    def test_action_log_is_capped(self):
        actions = [{'type': 'end_turn', 'payload': {}}] * (story_verify.MAX_CHECKPOINT_ACTIONS + 1)
        result = story_verify.replay_checkpoint(self._initial(), actions, self.SEED)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'action_limit')

    def test_normalize_actions_drops_client_ids(self):
        cleaned, error = story_verify.normalize_actions([{'id': 'x', 'type': 'end_turn', 'payload': {'a': 1}}])
        self.assertIsNone(error)
        self.assertEqual(cleaned, [{'type': 'end_turn', 'payload': {'a': 1}}])
