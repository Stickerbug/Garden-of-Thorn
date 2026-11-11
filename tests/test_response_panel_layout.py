# -*- coding: utf-8 -*-
"""反制窗口位置及换牌窗口隔离。"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ResponsePanelLayoutTests(unittest.TestCase):
    def test_response_panel_is_lowered_with_scroll_protection(self):
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8')
        block = re.search(r'\.response-panel\s*\{(?P<body>.*?)\}', css, re.S)
        self.assertIsNotNone(block)
        body = block.group('body')
        self.assertIn('top: 68%;', body)
        self.assertIn('max-height: calc(100vh - 48px);', body)
        self.assertIn('overflow-y: auto;', body)
        self.assertIn('z-index: 12020;', body)

    def test_mulligan_panel_stays_centered(self):
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8')
        block = re.search(r'\.mulligan-panel\s*\{(?P<body>.*?)\}', css, re.S)
        self.assertIsNotNone(block)
        self.assertIn('top: 50%;', block.group('body'))

    def test_mobile_canvas_transforms_remain_supported(self):
        css = (ROOT / 'static/css/style.css').read_text(encoding='utf-8')
        for selector in ('html.classic-mobile-canvas', 'html.minimal-mobile-canvas'):
            self.assertIn(selector, css)
        self.assertIn('transform: translate(-50%, -50%) rotate(var(--classic-mobile-rotate, 0deg)) scale(var(--classic-mobile-scale, 1));', css)
        self.assertIn('animation-name: centeredPanelPopInMobileCanvas;', css)

    def test_response_and_mulligan_are_distinct_elements(self):
        index = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        self.assertIn('id="response-panel" class="response-panel hidden"', index)
        self.assertIn('id="mulligan-panel" class="response-panel mulligan-panel hidden"', index)


if __name__ == '__main__':
    unittest.main()
