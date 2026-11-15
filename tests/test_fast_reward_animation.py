"""设置·外观「加快物品获取动画」的契约测试。

勾选后物品获取演出（reward-animation.js）整体时长减半：三个脚本计时器按
`scaledDuration(...)` 缩放，CSS 动画由 `.gra-overlay.is-fast` 覆盖。
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


class FastRewardAnimationSettingTests(unittest.TestCase):
    def test_appearance_page_has_the_toggle(self) -> None:
        html = read("templates/index.html")
        appearance = html.index('id="settings-page-appearance"')
        toggle = html.index('id="settings-fast-reward-animation"')
        self.assertLess(appearance, toggle)
        self.assertIn('id="settings-fast-reward-animation-row"', html)
        self.assertIn(
            'for="settings-fast-reward-animation">加快物品获取动画</label>', html
        )

    def test_game_keeps_the_preference_and_feeds_the_animation_script(self) -> None:
        source = read("static/js/game.js")
        self.assertGreaterEqual(source.count("'gtn_fast_reward_animation'"), 4)
        self.assertIn(
            "let fastRewardAnimation = localStorage.getItem('gtn_fast_reward_animation') === '1';",
            source,
        )
        self.assertIn("window.GTN_REWARD_ANIM_FAST = fastRewardAnimation;", source)
        self.assertIn("function applyFastRewardAnimation(value) {", source)
        self.assertIn("localStorage.setItem('gtn_fast_reward_animation'", source)
        self.assertIn(
            "fastRewardAnimationToggle.addEventListener('change', (e) => applyFastRewardAnimation(e.target.checked));",
            source,
        )

    def test_reward_animation_scales_every_timer(self) -> None:
        source = read("static/js/reward-animation.js")
        self.assertIn("function fastAnimation() {", source)
        self.assertIn("window.localStorage.getItem('gtn_fast_reward_animation') === '1'", source)
        self.assertIn("return fastAnimation() ? Math.round(ms / 2) : ms;", source)
        for delay in ("scaledDuration(1450)", "scaledDuration(3400)", "scaledDuration(460)"):
            self.assertIn(delay, source)
        self.assertIn("root.classList.add('is-fast');", source)
        self.assertIn("scaledDuration((delayStart + index * 0.035) * 1000) / 1000", source)

    def test_css_halves_the_entrance_animations(self) -> None:
        css = read("static/css/reward-animation.css")
        self.assertIn(".gra-overlay.is-fast .gra-wipe { animation-duration: .33s; }", css)
        self.assertIn(".gra-overlay.is-fast .gra-art-wrap { animation-duration: .35s; animation-delay: .11s; }", css)
        self.assertIn(".gra-overlay.is-fast .gra-char { animation-duration: .21s; }", css)


if __name__ == "__main__":
    unittest.main()
