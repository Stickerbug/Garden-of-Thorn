import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STORY_JS = ROOT / "static" / "js" / "story.js"
STORY_CSS = ROOT / "static" / "css" / "story.css"
VERSION_FILE = ROOT / "static_version.txt"


class StoryMobileCombatFitTest(unittest.TestCase):
    """回归：手机竖屏下怪物超过 4 只 / 手牌到第 10 张时点不到。

    `static/js/story.js` 的敌人组与手牌扇原本只靠 CSS clamp 定尺寸，
    390px 竖屏下 6 只怪物与 10 张手牌都会跑到视口外，被 body{overflow:hidden} 裁掉。
    现在由 `fitStoryEnemyActors()` / `fitStoryHandLayout()` 按容器可用宽度重排。
    """

    @classmethod
    def setUpClass(cls):
        cls.js = STORY_JS.read_text(encoding="utf-8")
        cls.css = STORY_CSS.read_text(encoding="utf-8")

    def test_enemy_fit_measures_container_and_scales_actors(self):
        self.assertIn("function fitStoryEnemyActors(group, actors, baseScale) {", self.js)
        start = self.js.index("function fitStoryEnemyActors(group, actors, baseScale) {")
        body = self.js[start:start + 2600]
        self.assertIn("const available = group.clientWidth;", body)
        self.assertIn("const gap = parseFloat(window.getComputedStyle(group).columnGap) || 0;", body)
        self.assertIn("actor.style.setProperty('--story-fighter-scale', String(scale));", body)
        self.assertIn("actor.style.marginInline = ", body)

    def test_enemy_fit_wraps_when_one_row_would_be_too_small(self):
        self.assertIn("const STORY_ENEMY_MAX_ROWS = 2;", self.js)
        self.assertIn("const shouldWrap = count >= 3 && singleRowScale < .55;", self.js)
        self.assertIn("group.classList.toggle('is-wrapped', perRow < count);", self.js)
        self.assertIn(".story-enemy-group.is-wrapped {", self.css)
        self.assertIn("flex-wrap: wrap;", self.css)

    def test_hand_fit_spreads_cards_across_the_hand_bar(self):
        self.assertIn("function fitStoryHandLayout(hand) {", self.js)
        start = self.js.index("function fitStoryHandLayout(hand) {")
        body = self.js[start:start + 2600]
        self.assertIn("const available = Math.max(0, target.clientWidth - paddingLeft - paddingRight);", body)
        self.assertIn("let step = (available - width) / (count - 1);", body)
        self.assertIn("const margin = (step - width) / 2;", body)
        self.assertIn("card.style.width = ", body)
        self.assertIn("card.style.marginInline = ", body)

    def test_hand_fit_runs_after_the_fan_is_rendered(self):
        self.assertIn("fitStoryHandLayout(hand);\n        syncStoryCursorCard(state);", self.js)

    def test_resize_reapplies_both_fits(self):
        self.assertIn("window.addEventListener('resize', () => {", self.js)
        start = self.js.index("window.addEventListener('resize', () => {")
        body = self.js[start:start + 400]
        self.assertIn("syncStoryEnemyGroupLayout();", body)
        self.assertIn("fitStoryHandLayout();", body)

    def test_enemy_layout_sync_calls_the_fit(self):
        start = self.js.index("function syncStoryEnemyGroupLayout() {")
        body = self.js[start:start + 900]
        self.assertIn("fitStoryEnemyActors(group, actors, baseScale);", body)

    def test_version_bumped(self):
        version = VERSION_FILE.read_text(encoding="utf-8").strip()
        self.assertTrue(version.endswith("-story-mobile-fit-1"), version)


if __name__ == "__main__":
    unittest.main()
