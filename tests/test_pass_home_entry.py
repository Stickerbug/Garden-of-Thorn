# -*- coding: utf-8 -*-
"""通行证主界面入口：Season Pass / Season Pass Pro 图标与独立弹层。"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


class PassHomeEntryTests(unittest.TestCase):
    def test_icons_are_packaged(self):
        self.assertTrue((ROOT / 'static/assets/ui-icons/season-pass.svg').is_file())
        self.assertTrue((ROOT / 'static/assets/ui-icons/season-pass-pro.svg').is_file())

    def test_home_screen_has_a_standalone_pass_entry(self):
        html = read('templates/index.html')
        self.assertIn('id="btn-pass-top"', html)
        self.assertIn('class="top-icon-btn pass-top-btn"', html)
        self.assertIn('id="home-entry-pass"', html)
        self.assertIn('id="home-entry-pass-icon"', html)
        self.assertIn('id="pass-popover"', html)
        self.assertIn('id="pass-panel"', html)

    def test_pass_tab_is_gone_from_the_achievements_popover(self):
        html = read('templates/index.html')
        self.assertNotIn('data-achievement-tab="pass"', html)
        # 旧面板节点保留，既有渲染代码仍然能找到它，不会整段中断
        self.assertIn('id="achievements-pass-panel"', html)

    def test_top_button_swaps_to_the_pro_icon(self):
        css = read('static/css/style.css')
        self.assertIn('.pass-top-btn::before { --ui-icon-url: url("/static/assets/ui-icons/season-pass.svg"); }', css)
        self.assertIn('.pass-top-btn.pass-top-btn-pro::before { --ui-icon-url: url("/static/assets/ui-icons/season-pass-pro.svg"); }', css)
        self.assertIn('.home-entry-icon {', css)
        # 入口固定在右上角，上边缘紧贴荆露栏下沿，尺寸按图形比例放大
        self.assertIn('button.pass-top-btn {\n  position: fixed;', css)
        self.assertIn('top: 36px;', css)
        self.assertIn('width: 170px;', css)
        self.assertIn('aspect-ratio: 246 / 148;', css)
        self.assertIn('button.pass-top-btn::before { width: 100%; height: 100%; }', css)
        # 两张图都裁掉了上下透明留白，否则顶部对不齐
        for name in ('season-pass.svg', 'season-pass-pro.svg'):
            self.assertIn('viewBox="19 66 246 148"', (ROOT / 'static/assets/ui-icons' / name).read_text(encoding='utf-8'))

    def test_game_js_syncs_the_icon_with_golden_road(self):
        js = read('static/js/game.js')
        self.assertIn('function applyPassEntryIcon(golden)', js)
        self.assertIn("top.classList.toggle('pass-top-btn-pro', passEntryGolden)", js)
        self.assertIn("'/static/assets/ui-icons/season-pass-pro.svg'", js)
        self.assertIn('async function syncPassEntryIconForAccount()', js)
        self.assertIn("authRequest('/api/battle-pass'", js)
        self.assertIn('window.gtnSyncPassEntryIcons = syncPassEntryIcons;', js)
        self.assertIn('function togglePassPopover(force)', js)
        self.assertIn("if ($('btn-pass-top')) $('btn-pass-top').addEventListener('click'", js)
        self.assertIn("if ($('home-entry-pass')) $('home-entry-pass').addEventListener('click'", js)
        # 账号状态每次渲染都会走一遍；同一账号不重复请求
        self.assertIn('syncPassEntryIconForAccount();\n    const accountDisplay', js)

    def test_battle_pass_panel_renders_into_both_mount_points(self):
        js = read('static/js/battle-pass.js')
        self.assertIn("if (typeof window.gtnSyncPassEntryIcons === 'function') window.gtnSyncPassEntryIcons(data);", js)
        self.assertIn("['achievements-pass-panel', 'pass-panel'].forEach((id) => {", js)
        self.assertIn('function renderInto(panel)', js)
        # 样式原本只作用于成就弹层里的面板，移出后必须同时覆盖新容器
        css = read('static/css/battle-pass.css')
        self.assertIn(':is(#achievements-pass-panel, #pass-panel)', css)
        self.assertIn('#pass-popover {', css)


if __name__ == '__main__':
    unittest.main()
