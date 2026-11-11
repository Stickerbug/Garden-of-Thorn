# -*- coding: utf-8 -*-
"""玩家皮肤贴图：统一视觉大小（viewBox 收紧到内容方形）+ 素材版本号。

皮肤贴图铺满头像是靠 `object-fit: contain`，所以"看起来多大"完全由 SVG
viewBox 里的留白决定。这里锁住归一化结果，避免有人重新导出素材时又带一圈空白、
让某几款皮肤突然变小。
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AVATARS = ROOT / 'static/assets/player-avatars'

# 归一化后各文件的 viewBox（内容方形 + 2% 留白）。换图后重新量一遍再更新此表。
EXPECTED_VIEWBOX = {
    'centipede-head.svg': (32.92, 32.92, 218.12, 218.12),
    'desert-centipede-head.svg': (32.92, 32.92, 218.12, 218.12),
    'evil-centipede-head.svg': (32.92, 32.92, 218.12, 218.12),
    'tower-curse-ironclad.svg': (41.26, 41.26, 200.97, 200.97),
    'tower-curse-silent.svg': (54.90, 50.39, 173.71, 173.71),
    'tower-curse-defect.svg': (46.72, 46.72, 190.06, 190.06),
    'tower-curse-necrobinder.svg': (54.90, 54.90, 173.71, 173.71),
    'tower-curse-regent.svg': (54.90, 54.90, 173.71, 173.71),
}

# 本来就画满画布的皮肤，归一化时应保持原样
FULL_CANVAS = (
    'faceless-body.svg',
    'ghost-body.svg',
    'brain-damage-body.svg',
    'corrupted-body.svg',
    'mark-body.svg',
    'nazar-body.svg',
    'right-angle-body.svg',
)


def read_viewbox(name):
    text = (AVATARS / name).read_text(encoding='utf-8')
    match = re.search(r'viewBox="([^"]+)"', text)
    if not match:
        raise AssertionError(f'{name} 没有 viewBox')
    return [float(v) for v in match.group(1).replace(',', ' ').split()]


class PlayerSkinAssetTests(unittest.TestCase):
    def test_view_boxes_are_square(self):
        """viewBox 必须是正方形：头像框是方的，非方形会被 contain 缩掉一截。"""
        for path in sorted(AVATARS.glob('*.svg')):
            if path.name.startswith('phelren-frame'):
                continue
            vx, vy, vw, vh = read_viewbox(path.name)
            self.assertAlmostEqual(vw, vh, places=2, msg=path.name)
            self.assertGreater(vw, 0, path.name)

    def test_art_is_normalized_to_the_same_size(self):
        """画不满的素材已把 viewBox 收紧到内容包围盒（±1），放大到铺满头像。"""
        for name, expected in EXPECTED_VIEWBOX.items():
            got = read_viewbox(name)
            for a, b in zip(got, expected):
                self.assertAlmostEqual(a, b, delta=1.0, msg=name)

    def test_full_canvas_skins_keep_their_view_box(self):
        for name in FULL_CANVAS:
            self.assertEqual(read_viewbox(name), [0.0, 0.0, 283.46, 283.46], name)

    def test_textures_carry_an_art_revision(self):
        """贴图 URL 带素材版本号，换图后不会被浏览器缓存住。"""
        script = (ROOT / 'static/js/player-skins.js').read_text(encoding='utf-8')
        self.assertIn('const PLAYER_SKIN_ART_REVISION = ', script)
        self.assertIn('function withArtRevision(url)', script)
        self.assertIn('withArtRevision(definition.texture)', script)
        self.assertIn('withArtRevision(definition.decoration)', script)


if __name__ == '__main__':
    unittest.main()
