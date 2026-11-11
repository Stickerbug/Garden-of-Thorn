# -*- coding: utf-8 -*-
"""故事事件银行：取款清零后不能把数据库旧余额写回去。"""

import unittest
from unittest import mock

import app as gtn


class StoryEventBankRouteTests(unittest.TestCase):
    def setUp(self):
        gtn.app.config.update(TESTING=True)
        self.client = gtn.app.test_client()
        self.run_state = {
            'phase': 'room',
            'event_bank': 100,
            'dev_mode': False,
            'content_version': gtn.STORY_CONTENT_VERSION,
            'player': {'gold': 10},
        }
        self.run = {
            'id': 'run-bank',
            'seed': 'seed-bank',
            'content_version': gtn.STORY_CONTENT_VERSION,
            'state_version': 1,
            'state': self.run_state,
        }

    def _post_action(self, next_state, action_id='bank-withdraw-1'):
        updated_run = {
            'id': self.run['id'],
            'content_version': gtn.STORY_CONTENT_VERSION,
            'state_version': 2,
            'state': next_state,
        }
        payload = {
            'run_id': self.run['id'],
            'action_id': action_id,
            'action_type': 'resolve_room',
            'state_version': 1,
            'payload': {'option': 'withdraw'},
        }
        with (
            mock.patch.object(gtn, '_require_account_json', return_value=(41, 'Tester', None)),
            mock.patch.object(gtn, 'get_story_run_action', return_value=None),
            mock.patch.object(gtn, '_current_story_run', return_value=self.run),
            mock.patch.object(gtn, 'get_story_bank', return_value=100),
            mock.patch.object(gtn, 'apply_story_action', return_value=(next_state, [])),
            mock.patch.object(gtn, 'commit_story_run_action', return_value=(updated_run, 'committed')),
            mock.patch.object(gtn, 'set_story_bank') as set_bank,
            mock.patch.object(gtn, 'run_off_event_loop', side_effect=lambda fn, *a, **kw: fn(*a, **kw)),
            mock.patch.object(gtn, '_story_run_with_compatibility', side_effect=lambda run: run),
            mock.patch.object(gtn, '_sync_story_discoveries', return_value=[]),
            mock.patch.object(gtn, '_list_story_discoveries_without_blocking', return_value=[]),
            mock.patch.object(gtn, '_story_progress_without_blocking', return_value={}),
        ):
            response = self.client.post('/api/story/run/action', json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        return set_bank

    def test_withdraw_all_persists_zero_bank(self):
        next_state = {
            **self.run_state,
            'event_bank': 0,
            'player': {'gold': 110},
        }
        set_bank = self._post_action(next_state)
        set_bank.assert_called_once_with(41, 0)

    def test_deposit_still_persists_new_bank(self):
        next_state = {
            **self.run_state,
            'event_bank': 300,
            'player': {'gold': 0},
        }
        set_bank = self._post_action(next_state, action_id='bank-deposit-1')
        set_bank.assert_called_once_with(41, 300)

    def test_missing_bank_value_falls_back_to_database(self):
        next_state = {
            key: value for key, value in self.run_state.items() if key != 'event_bank'
        }
        set_bank = self._post_action(next_state, action_id='bank-legacy-1')
        set_bank.assert_called_once_with(41, 100)


if __name__ == '__main__':
    unittest.main()
