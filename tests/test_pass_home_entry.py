# -*- coding: utf-8 -*-
"""通行证主界面入口：Season Pass / Season Pass Pro 图标与独立弹层。"""

from __future__ import annotations

import re
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
        # 第二条虚线左侧显示荆棘之路奖励，右侧显示黄金之路奖励并带金光
        self.assertIn('id="pass-hud-glow"', read('templates/index.html'))
        self.assertIn('id="pass-hud-golden-text"', read('templates/index.html'))
        pro_next = css.split('.pass-top-btn-pro .pass-hud-next {', 1)[1].split('}', 1)[0]
        self.assertIn('left: 44.6%;', pro_next)
        self.assertIn('width: 26.4%;', pro_next)
        golden = css.split('.pass-hud-golden {', 1)[1].split('}', 1)[0]
        self.assertIn('left: 72.2%;', golden)
        self.assertIn('width: 26.5%;', golden)
        self.assertIn('.pass-top-btn-pro .pass-hud-golden { display: flex; }', css)
        self.assertIn('.pass-hud-golden[hidden] { display: none !important; }', css)
        glow = css.split('.pass-top-btn-pro .pass-hud-glow {', 1)[1].split('}', 1)[0]
        self.assertIn('left: 71.4%;', glow)
        self.assertIn('animation: pass-hud-gold-pulse', glow)
        self.assertIn('@keyframes pass-hud-gold-pulse', css)
        self.assertIn('.pass-hud-glow[hidden] { display: none !important; }', css)
        js = read('static/js/game.js')
        self.assertIn("if (glow) glow.hidden = !passEntryGolden;", js)
        self.assertIn("payload.tracks.free", js)
        self.assertIn("payload.tracks.golden", js)
        self.assertIn("fillReward('pass-hud-golden-icon', 'pass-hud-golden-text'", js)
        # 黄金之路未解锁时右侧那格不显示
        self.assertIn("if (goldenBox) goldenBox.hidden = !payload.golden;", js)

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
    def test_progress_bar_fills_exactly_the_visible_track(self):
        """Pro 图的进度条必须盖住整条可见深色轨道，且不压到奶油描边。

        season-pass-pro.svg 的 viewBox 是 0 60 360 158；深色轨道矩形 x=70、宽 286，
        带 10px 奶油描边，所以真正露出来的深色区是 75.3..350.3；金叶子右沿在 77.5。
        旧值（19.4% / 79.5%）对应 70..356：右侧压到描边、左侧钻到叶子底下。
        左端再往叶子底下探一点是必要的：只对齐 75.3 时实测绿条从 77 才开始画，
        满级会留一道 1 像素的黑缝（用户报障「填上多余的黑色部分」）。
        """
        css = read('static/css/style.css')
        block = css.split('.pass-top-btn-pro .pass-hud-bar,', 1)[1].split('}', 1)[0]
        left = float(re.search(r'left:\s*([\d.]+)%', block).group(1))
        width = float(re.search(r'width:\s*([\d.]+)%', block).group(1))
        start_unit = left / 100 * 360
        end_unit = (left + width) / 100 * 360
        self.assertLessEqual(start_unit, 75.3, '左端必须盖到黑轨起点，否则满级留黑缝')
        self.assertGreaterEqual(start_unit, 64, '左端不能跑到奶油描边外沿 65 以外')
        self.assertAlmostEqual(end_unit, 350.3, delta=0.4, msg='右端要贴住可见黑轨终点')
        self.assertLessEqual(end_unit, 351, '进度条不能压到奶油色描边')

    def test_progress_bar_left_end_follows_the_leaf_outline(self):
        """左端不能用一条竖直边把金叶子切平，要顺着叶子的轮廓收进去。

        做法是在 .pass-hud-bar 上叠两层同源 SVG mask：白底 + 叶子 / 白底 + EXP 角标 各挖一个洞，
        两层 mask-composite: intersect 求交，这样绿条的左端同时避开叶子和角标。
        叶子那层洞的起点要从 77.5 右移 1.7 到 79.2：叶子本体还带 3.4 的描边，可见轮廓比
        path 外扩 1.7，不补偿的话绿条会啃掉叶子那一圈金色描边。
        """
        css = read('static/css/style.css')
        block = css.split('.pass-top-btn-pro .pass-hud-bar {', 1)[1].split('}', 1)[0]
        self.assertIn('mask-image', block)
        self.assertIn('evenodd', block)
        self.assertIn('M79.2,165.3', block, '遮罩洞要右移 1.7，把叶子的 3.4 描边一起挖掉')
        self.assertNotIn('M77.5,165.3', block, '直接复用未外扩的叶子 path 会让绿条压在金色描边上')
        self.assertIn('viewBox=\'65 170 285.32 35.08\'', block.replace('%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 ', '%3Csvg '))
        self.assertIn('M75,195H47v16h28Z', block, '第二层遮罩要把 EXP 角标（50..72 / 196.7..209.9）挖掉')
        self.assertIn('mask-composite: intersect', block, '两层不能塞进一条 evenodd：叶子与角标重叠处会被重新填上')
        self.assertIn('source-in', block, '老 WebKit 只认 -webkit-mask-composite')

    def test_exp_bar_is_clipped_by_the_leaf(self):
        """经验条（深色圆角矩形）的左端也不能平切进金叶子，要按叶子轮廓裁。

        做法：defs 里建一张 evenodd 裁剪路径（描边外框 65,165..361,210 挖掉叶子形状），
        再把 <rect class="st1"> 包进 <g clip-path>。裁剪范围取描边外框而不是填充框，
        否则 10px 奶油描边会被整圈切掉。
        """
        svg = (ROOT / 'static/assets/ui-icons/season-pass-pro.svg').read_text(encoding='utf-8')
        self.assertIn('<clipPath id="exp-bar-clip">', svg)
        clip = svg.split('<clipPath id="exp-bar-clip">', 1)[1].split('</clipPath>', 1)[0]
        self.assertIn('fill-rule="evenodd"', clip, '要挖洞，默认 nonzero 会把叶子整块涂黑')
        self.assertIn('M65,165H361V210H65Z', clip, '裁剪范围要覆盖 10px 描边外框')
        self.assertIn('M77.5,165.3', clip, '裁剪路径里要含那片金叶子的轮廓')
        self.assertIn('<g clip-path="url(#exp-bar-clip)">', svg, '经验条必须真的套上这张裁剪路径')

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
        self.assertIn('left: 18.0556%;', pro_bar)
        self.assertIn('width: 79.2556%;', pro_bar)
        js = read('static/js/game.js')
        self.assertIn('function applyPassEntryHud(payload)', js)
        self.assertIn("Math.max(1, Number(payload.xp_per_level) || 100)", js)
        # 2026-11-19：图标等级跟随真实等级（原来一直是模板里的 1）。
        self.assertIn("const level = Math.max(0, Number(payload.level) || 0);", js)
        self.assertIn("levelEl.textContent = String(level);", js)
        self.assertIn("payload.tracks.free", js)
        self.assertIn("payload.tracks.golden", js)
        self.assertIn("fill.style.width = Math.round((into / perLevel) * 100) + '%';", js)
        self.assertIn('applyPassEntryHud(payload);', js)
        self.assertIn('applyPassEntryHud(null);', js)


if __name__ == '__main__':
    unittest.main()
