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
        # 入口固定在左上角图标行下方，尺寸按图形比例放大
        self.assertIn('button.pass-top-btn {\n  position: fixed;', css)
        self.assertIn('top: 68px;', css)
        self.assertIn('left: 10px;', css)
        self.assertIn('width: 170px;', css)
        self.assertIn('aspect-ratio: 246 / 148;', css)
        self.assertIn('button.pass-top-btn::before { width: 100%; height: 100%; }', css)
        # 只在主界面（#view-login 可见）显示，其余视图一律隐藏
        self.assertIn('  display: none;\n}\nbutton.pass-top-btn::before', css)
        self.assertIn('body:has(#view-login:not(.hidden)) button.pass-top-btn { display: block; }', css)
        self.assertNotIn('body:has(#view-game:not(.hidden)) button.pass-top-btn', css)
        # 基础图标裁掉了上下透明留白，否则顶部对不齐
        self.assertIn('viewBox="19 66 246 148"', (ROOT / 'static/assets/ui-icons/season-pass.svg').read_text(encoding='utf-8'))
        # 黄金之路图标用改版 Pro 图，画布更宽（360×158）
        self.assertIn('viewBox="0 60 360 158"', (ROOT / 'static/assets/ui-icons/season-pass-pro.svg').read_text(encoding='utf-8'))

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
    def test_top_button_shows_level_reward_and_progress(self):
        html = read('templates/index.html')
        for anchor in ('id="pass-hud"', 'id="pass-hud-level"', 'id="pass-hud-next-icon"',
                       'id="pass-hud-next-text"', 'id="pass-hud-bar-fill"', 'id="pass-hud-xp"'):
            self.assertIn(anchor, html)
        css = read('static/css/style.css')
        self.assertIn('.pass-hud-level {', css)
        self.assertIn('.pass-hud-bar-fill {', css)
        # 顶栏按钮里的 img 默认 display:none，奖励图标必须显式放开
        self.assertIn('.pass-top-btn .pass-hud-next-icon {', css)
        # 虚线右侧整块叶面（54%..100%）居中，奖励不能被挤到右半边的一小条里
        next_block = css.split('.pass-hud-next {', 1)[1].split('}', 1)[0]
        self.assertIn('left: 54%;', next_block)
        self.assertIn('width: 46%;', next_block)
        self.assertIn('align-items: center;', next_block)
        self.assertIn('transform: translateY(3px);', next_block)
        # 拥有黄金之路后按钮按 Pro 图比例变宽，三层信息按新图位置重排
        css2 = read('static/css/style.css')
        self.assertIn('button.pass-top-btn.pass-top-btn-pro { width: 232px; aspect-ratio: 360 / 158; }', css2)
        pro_level = css2.split('.pass-top-btn-pro .pass-hud-level {', 1)[1].split('}', 1)[0]
        self.assertIn('left: 12%;', pro_level)
        self.assertIn('font-size: 30px;', pro_level)
        pro_bar = css2.split('.pass-top-btn-pro .pass-hud-bar,', 1)[1].split('}', 1)[0]
        self.assertIn('left: 19.4%;', pro_bar)
        self.assertIn('width: 79.5%;', pro_bar)
        js = read('static/js/game.js')
        self.assertIn('function applyPassEntryHud(payload)', js)
        self.assertIn("Math.max(1, Number(payload.xp_per_level) || 100)", js)
        self.assertIn("payload.tracks[payload.golden ? 'golden' : 'free']", js)
        self.assertIn("fill.style.width = Math.round((into / perLevel) * 100) + '%';", js)
        self.assertIn('applyPassEntryHud(payload);', js)
        self.assertIn('applyPassEntryHud(null);', js)


if __name__ == '__main__':
    unittest.main()
