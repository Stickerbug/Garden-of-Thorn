import unittest
from unittest import mock

import app as gtn


class StoryCooperativeAccessTests(unittest.TestCase):
    def setUp(self):
        gtn.app.config.update(TESTING=True)
        self.client = gtn.app.test_client()
        self.user = {
            'id': 41,
            'username': 'StoryTester',
            'display_name': 'StoryTester',
            'skin': {},
            'keybindings': {},
        }

    def _get_story_page(self, *, staff=True, dev_tools=False):
        with (
            mock.patch.object(gtn, '_current_account_user', return_value=self.user),
            mock.patch.object(gtn, 'feedback_is_staff', return_value=staff),
            mock.patch.object(gtn, 'get_user_role_profile', return_value={}),
            mock.patch.object(gtn, 'STORY_DEV_TOOLS_ENABLED', dev_tools),
            mock.patch.object(gtn, '_story_dev_tools_allowed', return_value=dev_tools),
        ):
            return self.client.get('/story')

    def test_cooperative_experiment_is_removed_for_every_account(self):
        for staff in (False, True):
            with self.subTest(staff=staff):
                response = self._get_story_page(staff=staff)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                for element_id in (
                    'story-coop-entry', 'story-coop-preview-dialog',
                    'story-coop-combat-dialog', 'story-coop-setup-panel',
                    'story-coop-opening-panel', 'story-coop-reward-panel',
                    'story-coop-map-panel', 'story-coop-seeded-backdrop',
                ):
                    self.assertNotIn(f'id="{element_id}"', html)
                self.assertNotIn('协作故事实验', html)
                self.assertIn('window.__STORY_COOP_ACCESS__ = false;', html)
                self.assertIn('id="story-start"', html)

    def test_multiplayer_demo_entry_and_namespace_are_preserved(self):
        response = self._get_story_page(staff=True, dev_tools=True)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="story-coop-demo-entry"', html)
        self.assertIn('多人爬塔', html)
        self.assertNotIn('id="story-coop-entry"', html)
        routes = {rule.rule for rule in gtn.app.url_map.iter_rules()}
        self.assertIn('/api/coop-demo/run', routes)
        self.assertIn('/api/coop-demo/action', routes)

    def test_cooperative_bootstrap_returns_removed_without_doing_work(self):
        with mock.patch.object(
            gtn, '_require_account_json', return_value=(41, 'StoryTester', None),
        ):
            response = self.client.get('/api/story/coop/bootstrap')
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.get_json()['code'], 'COOP_STORY_REMOVED')

    def test_party_and_run_endpoints_also_return_removed(self):
        with mock.patch.object(
            gtn, '_require_account_json', return_value=(41, 'StoryTester', None),
        ):
            party = self.client.get('/api/story/coop/party')
            run = self.client.post('/api/story/coop/run/example/action', json={})
        self.assertEqual(party.status_code, 410)
        self.assertEqual(run.status_code, 410)
        self.assertEqual(party.get_json()['code'], 'COOP_STORY_REMOVED')
        self.assertEqual(run.get_json()['code'], 'COOP_STORY_REMOVED')

    def test_permission_gate_is_always_closed(self):
        self.assertFalse(gtn._story_coop_allowed(41))


if __name__ == '__main__':
    unittest.main()
