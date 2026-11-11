import unittest
from unittest import mock

import app as gtn


class StoryDeveloperPermissionTests(unittest.TestCase):
    def setUp(self):
        gtn.app.config.update(TESTING=True)
        self.client = gtn.app.test_client()
        self.user = {
            "id": 41,
            "username": "StoryTester",
            "display_name": "StoryTester",
            "skin": {},
            "keybindings": {},
        }

    def test_regular_account_does_not_receive_developer_controls(self):
        with (
            mock.patch.object(gtn, "_current_account_user", return_value=self.user),
            mock.patch.object(gtn, "feedback_is_staff", return_value=False),
            mock.patch.object(gtn, "STORY_DEV_TOOLS_ENABLED", True),
        ):
            response = self.client.get("/story")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn('id="story-dev-toggle"', html)
        self.assertNotIn('id="story-dev-panel"', html)
        self.assertNotIn('id="story-reset-map"', html)

    def test_staff_account_receives_developer_controls(self):
        with (
            mock.patch.object(gtn, "_current_account_user", return_value=self.user),
            # 2026-10-14：故事开发工具门禁改为 user_role_type（admin/staff/tester）。
            mock.patch.object(gtn, "user_role_type", return_value="staff"),
            mock.patch.object(gtn, "STORY_DEV_TOOLS_ENABLED", True),
        ):
            response = self.client.get("/story")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="story-dev-toggle"', html)
        self.assertIn('id="story-dev-panel"', html)
        self.assertIn('id="story-reset-map"', html)
        # 开发人员模式默认隐藏：入口存在但带 hidden，只有 dev 局才显示。
        self.assertIn('id="story-dev-toggle" class="story-dev-toggle hidden"', html)
        self.assertIn('id="story-dev-mode-start"', html)
        self.assertIn('开启后本局不会向服务器上传任何永久数据', html)

    def test_regular_account_cannot_call_developer_action_api(self):
        payload = {
            "run_id": "test-run",
            "action_id": "test-action",
            "action_type": "dev_set_values",
            "state_version": 1,
            "payload": {"health": 99},
        }
        with (
            mock.patch.object(gtn, "_require_account_json", return_value=(41, "StoryTester", None)),
            mock.patch.object(gtn, "feedback_is_staff", return_value=False),
            mock.patch.object(gtn, "STORY_DEV_TOOLS_ENABLED", True),
        ):
            response = self.client.post("/api/story/run/action", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["code"], "DEV_TOOLS_DISABLED")

    def test_regular_account_cannot_reset_story_map(self):
        with (
            mock.patch.object(gtn, "_require_account_json", return_value=(41, "StoryTester", None)),
            mock.patch.object(gtn, "feedback_is_staff", return_value=False),
            mock.patch.object(gtn, "STORY_DEV_TOOLS_ENABLED", True),
        ):
            response = self.client.post("/api/story/run/reset-map", json={"run_id": "test-run"})
        self.assertEqual(response.status_code, 404)

    def test_staff_developer_mode_is_ignored_on_regular_runs(self):
        payload = {
            "run_id": "normal-run",
            "action_id": "normal-dev-action",
            "action_type": "dev_set_values",
            "state_version": 1,
            "payload": {"health": 99},
        }
        run = {
            "id": "normal-run",
            "content_version": gtn.STORY_CONTENT_VERSION,
            "state_version": 1,
            "state": {"phase": "map", "dev_mode": False, "content_version": gtn.STORY_CONTENT_VERSION},
        }
        with (
            mock.patch.object(gtn, "_require_account_json", return_value=(41, "StoryTester", None)),
            mock.patch.object(gtn, "_story_dev_tools_allowed", return_value=True),
            mock.patch.object(gtn, "get_story_run_action", return_value=None),
            mock.patch.object(gtn, "_current_story_run", return_value=run),
        ):
            response = self.client.post("/api/story/run/action", json=payload)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["code"], "DEV_TOOLS_DISABLED")

    def test_staff_dev_mode_start_skips_permanent_writes(self):
        created_run = {
            "id": "dev-run",
            "content_version": gtn.STORY_CONTENT_VERSION,
            "state_version": 1,
            "state": {"dev_mode": True},
        }
        with (
            mock.patch.object(gtn, "_require_account_json", return_value=(41, "StoryTester", None)),
            mock.patch.object(gtn, "_current_story_run", return_value=None),
            mock.patch.object(gtn, "_story_dev_tools_allowed", return_value=True),
            mock.patch.object(gtn, "story_character_is_unlocked", return_value=True),
            mock.patch.object(gtn, "create_story_run", return_value=(created_run, True)) as create_run,
            mock.patch.object(gtn, "record_story_play", return_value=True) as record_play,
            mock.patch.object(gtn, "get_story_bank", return_value=777) as get_bank,
            mock.patch.object(gtn, "_story_run_with_compatibility", side_effect=lambda run: run),
            mock.patch.object(gtn, "_sync_story_discoveries", return_value=[]),
            mock.patch.object(gtn, "_list_story_discoveries_without_blocking", return_value=[]),
            mock.patch.object(gtn, "_story_progress_without_blocking", return_value={}),
        ):
            response = self.client.post(
                "/api/story/run",
                json={"character_id": "common_flower", "dev_mode": True},
            )
        self.assertEqual(response.status_code, 200)
        state = create_run.call_args.args[3]
        self.assertTrue(state["dev_mode"])
        self.assertEqual(state["event_bank"], 0)
        record_play.assert_not_called()
        get_bank.assert_not_called()

    def test_dev_mode_start_is_ignored_for_regular_accounts(self):
        created_run = {
            "id": "normal-run",
            "content_version": gtn.STORY_CONTENT_VERSION,
            "state_version": 1,
            "state": {"dev_mode": False},
        }
        with (
            mock.patch.object(gtn, "_require_account_json", return_value=(41, "StoryTester", None)),
            mock.patch.object(gtn, "_current_story_run", return_value=None),
            mock.patch.object(gtn, "_story_dev_tools_allowed", return_value=False),
            mock.patch.object(gtn, "story_character_is_unlocked", return_value=True),
            mock.patch.object(gtn, "create_story_run", return_value=(created_run, True)) as create_run,
            mock.patch.object(gtn, "record_story_play", return_value=True) as record_play,
            mock.patch.object(gtn, "get_story_bank", return_value=777),
            mock.patch.object(gtn, "_story_run_with_compatibility", side_effect=lambda run: run),
            mock.patch.object(gtn, "_sync_story_discoveries", return_value=[]),
            mock.patch.object(gtn, "_list_story_discoveries_without_blocking", return_value=[]),
            mock.patch.object(gtn, "_story_progress_without_blocking", return_value={}),
        ):
            response = self.client.post(
                "/api/story/run",
                json={"character_id": "common_flower", "dev_mode": True},
            )
        self.assertEqual(response.status_code, 200)
        state = create_run.call_args.args[3]
        self.assertFalse(state["dev_mode"])
        self.assertEqual(state["event_bank"], 777)
        record_play.assert_called_once_with(41, "common_flower")

    def test_staff_reset_abandons_the_run_and_returns_to_character_selection(self):
        with (
            mock.patch.object(gtn, "_require_account_json", return_value=(41, "StoryTester", None)),
            # 2026-10-14：故事开发工具门禁改为 user_role_type（admin/staff/tester）。
            mock.patch.object(gtn, "user_role_type", return_value="staff"),
            mock.patch.object(gtn, "STORY_DEV_TOOLS_ENABLED", True),
            mock.patch.object(
                gtn, "_current_story_run",
                return_value={"id": "test-run", "state": {"dev_mode": True}},
            ),
            mock.patch.object(gtn, "abandon_story_run", return_value=True) as abandon,
            mock.patch.object(gtn, "_list_story_discoveries_without_blocking", return_value=[]),
        ):
            response = self.client.post(
                "/api/story/run/reset-map",
                json={"run_id": "test-run"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["run"])
        abandon.assert_called_once_with(41, "test-run")


if __name__ == "__main__":
    unittest.main()
