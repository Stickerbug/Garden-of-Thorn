# -*- coding: utf-8 -*-
"""主题背景文字自适应（theme-ink）源码契约。

只做源码级断言：模块存在、复用卡牌墨色同一套对比度参数与解算、
只在有主题背景时生效、被面板覆盖的文字不参与、模板与主题切换都已接线。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'static' / 'js' / 'theme-ink.js'
TEMPLATE = ROOT / 'templates' / 'index.html'
GAME = ROOT / 'static' / 'js' / 'game.js'


class ThemeInkContractTests(unittest.TestCase):
    def setUp(self):
        self.source = MODULE.read_text(encoding='utf-8')

    def test_module_is_served_by_the_home_template(self):
        self.assertTrue(MODULE.exists())
        html = TEMPLATE.read_text(encoding='utf-8')
        self.assertIn('/static/js/theme-ink.js?v=', html)
        self.assertIn('window.GtnThemeInk', self.source)

    def test_constants_match_the_card_ink_algorithm(self):
        self.assertIn('const NEUTRAL_HALF = 0.12;', self.source)
        self.assertIn('const DARK_CONTRAST = 0.66;', self.source)
        self.assertIn('const LIGHT_ANCHOR = 0.90;', self.source)

    def test_light_side_solves_contrast_against_the_default_card_base(self):
        self.assertIn('function wcagContrastRatio(', self.source)
        self.assertIn('getPropertyValue(\'--bg-card\')', self.source)
        self.assertIn('const delta = Math.max(0.12, LIGHT_ANCHOR - lo);', self.source)

    def test_only_adjusts_lightness_and_keeps_hue_and_saturation(self):
        self.assertIn('const [h, s] = rgbToHsl(base);', self.source)
        self.assertIn('const rgb = hslToRgb(h, s, lightness);', self.source)
        self.assertNotRegex(self.source, r'filter:\s*brightness')

    def test_neutral_band_and_tiny_delta_leave_text_alone(self):
        self.assertIn('if (strength <= 0.001) return null;', self.source)
        self.assertIn('if (Math.abs(target - baseLuma) < MIN_DELTA) return null;', self.source)

    def test_inactive_without_a_theme_backdrop_and_restores_text(self):
        self.assertIn("document.body.classList.contains('has-player-theme-background')", self.source)
        self.assertIn('function restoreAll()', self.source)

    def test_text_under_an_opaque_panel_is_skipped(self):
        self.assertIn('function coveredByPanel(el)', self.source)
        self.assertIn('bg[3] >= 0.5', self.source)
        self.assertIn('if (coveredByPanel(el)) continue;', self.source)

    def test_cards_keep_using_their_own_ink_pipeline(self):
        self.assertIn("el.closest('#player-theme-backdrop, .card, script, style, .hidden')", self.source)

    def test_theme_switch_recomputes_card_ink_base_colors(self):
        game = GAME.read_text(encoding='utf-8', errors='replace')
        block = re.search(r'function applyTheme\(theme\) \{(.*?)\n\}', game, re.S)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn('stripSkinInkFromCard', body)
        self.assertIn("removeAttribute('data-ink-base')", body)
        self.assertIn('GtnThemeInk.apply', body)


if __name__ == '__main__':
    unittest.main()
