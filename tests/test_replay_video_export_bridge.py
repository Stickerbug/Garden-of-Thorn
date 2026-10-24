import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReplayVideoExportBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "js" / "game.js").read_text(encoding="utf-8")

    def test_bridge_version_matches_current_exporter(self):
        self.assertIn("window.GTNReplayVideoBridge = {\n    version: 13,", self.source)

    def test_export_loads_all_bundled_mods_independent_of_browser_settings(self):
        self.assertIn("function buildReplayExportModQueryString", self.source)
        self.assertIn("params.set('disabled_mods', '');", self.source)
        self.assertIn("fetchReplayExportCardDefs(accountReplayData)", self.source)

    def test_export_preserves_replay_community_mod_selection(self):
        self.assertIn("params.set('community_mods', JSON.stringify(communityMods));", self.source)


if __name__ == "__main__":
    unittest.main()


class ReplaySubjectiveViewTests(unittest.TestCase):
    """回放主观/旁观视角（2026-10-24）：还原对局可见度。"""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "js" / "game.js").read_text(encoding="utf-8")

    def test_subjective_visibility_transform_exists(self):
        self.assertIn("function applyReplaySubjectiveVisibility", self.source)
        self.assertIn("function replaySubjectiveHiddenEnemyView", self.source)
        self.assertIn("function replaySubjectiveTeammateView", self.source)
        self.assertIn("function replayFrameOpensEnemyHandWindow", self.source)

    def test_subjective_mode_wires_into_frame_rendering(self):
        self.assertIn("let accountReplayViewMode = 'spectate';", self.source)
        self.assertIn("accountReplayViewMode === 'subjective'", self.source)
        self.assertIn("applyReplaySubjectiveVisibility(replayState, frame);", self.source)
        self.assertIn("isSpectating = !videoPlayerView && !subjectiveView;", self.source)

    def test_viewmode_toggle_is_rendered_and_clickable(self):
        self.assertIn("function renderReplayViewModeButtons", self.source)
        self.assertIn('data-account-replay-viewmode="${mode.id}"', self.source)
        self.assertIn("accountReplayViewMode = viewMode.dataset.accountReplayViewmode", self.source)

    def test_enemy_hiding_preserves_counts_and_revealed_cards(self):
        # 敌方手牌清空但保留 hand_count；revealed 旗帜牌进入 revealed_tag_cards
        self.assertIn("hidden.hand = [];", self.source)
        self.assertIn("hidden.hand_count = Number(player.hand_count", self.source)
        self.assertIn("flags.includes('revealed')", self.source)
        self.assertIn("hidden.revealed_tag_cards = revealed;", self.source)

    def test_teammate_blind_and_deck_order_rules_match_live_game(self):
        # 2v2：自己失明时队友手牌显示问号（设计9.22），队友牌堆乱序
        self.assertIn("__blind_for_teammate: true", self.source)
        self.assertIn("deck_order_hidden = true", self.source)

    def test_reveal_window_restoration_predicates(self):
        # 从敌方手牌选牌（磁铁/重构机）：resolve 帧 target_instance_id 或
        # choose_from_enemy_hand 窗口帧 → 该帧还原敌方手牌
        self.assertIn("choice.target_instance_id != null", self.source)
        self.assertIn("'choose_from_enemy_hand'", self.source)


class StoryMusicPolicyTests(unittest.TestCase):
    """故事模式音乐策略（2026-10-24）：淡入淡出/静音页/童祭/暂停续播。"""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "js" / "story.js").read_text(encoding="utf-8")

    def test_fade_durations_are_configured(self):
        self.assertIn("STORY_MUSIC_FADE_IN_SECONDS = 5", self.source)
        self.assertIn("STORY_MUSIC_FADE_OUT_SECONDS = 1", self.source)

    def test_pool_pause_resume_instead_of_restart(self):
        self.assertIn("const storyMusicPool = new Map();", self.source)
        self.assertIn("function storyMusicEntry(key)", self.source)
        self.assertIn("function storyMusicResetPool()", self.source)

    def test_silent_pages_blessing_and_endings(self):
        self.assertIn("if (phase === 'blessing') return '';", self.source)
        self.assertIn("'complete', 'game_over', 'terminal'", self.source)

    def test_mysterious_person_uses_tongji(self):
        self.assertIn("mysterious: '/static/audio/story/tongji.mp3'", self.source)
        self.assertIn("event_id || '' === 'mysterious_person'", self.source.replace(
            "String(state?.room?.event_id || '') === 'mysterious_person'",
            "event_id || '' === 'mysterious_person'"))
        self.assertIn("'mysterious_person') return 'mysterious'", self.source)

    def test_leaving_story_resets_pool(self):
        self.assertIn("stopStoryMusic({ reset: true });", self.source)


class StoryOrbitMirrorTests(unittest.TestCase):
    """轨道使（2026-10-24）：触发点镜像到右侧 + 恒顺时针旋转。"""

    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "static" / "js" / "story.js").read_text(encoding="utf-8")

    def test_trigger_angle_is_right_side(self):
        # CSS rotate(90deg)+translateY(-r) 落在中心右侧（旧值 -90 为左侧）
        self.assertIn("const STORY_ORBIT_TRIGGER_ANGLE = 90;", self.source)
        self.assertNotIn("const STORY_ORBIT_TRIGGER_ANGLE = -90;", self.source)

    def test_rotation_is_always_clockwise(self):
        # 旧算法取最短路径（可能逆时针）；新算法恒为 [0,360) 正向增量
        # （敌方机械轨道 animateStoryMechanicalTrackActivation 保留最短路径，不在范围）
        orbit_start = self.source.index("const STORY_ORBIT_TRIGGER_ANGLE")
        orbit_end = self.source.index("function settleStoryOrbitTrigger")
        orbit_block = self.source[orbit_start:orbit_end]
        self.assertIn("delta = ((delta % 360) + 360) % 360;", orbit_block)
        self.assertNotIn("((delta + 540) % 360) - 180", orbit_block)
