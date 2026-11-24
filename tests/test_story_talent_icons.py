"""天赋贴图契约：每个天赋都有 static/assets/talents/<relic id>.svg，并在 UI 上渲染出来。"""

from __future__ import annotations


import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import story_content  # noqa: E402
from story_content import STORY_RELICS  # noqa: E402

ASSET_DIR = ROOT / 'static' / 'assets' / 'talents'
EXPECTED_IMAGE_PREFIX = '/static/assets/talents/'
# 素材包里没有这张（策划漏图），前端回落成 ★，不算失败。
KNOWN_MISSING = {'miracle_spring'}


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


class TestTalentIcons(unittest.TestCase):
    def test_every_talent_has_an_image_url(self):
        known = sorted(set(STORY_RELICS) - KNOWN_MISSING)
        self.assertGreaterEqual(len(known), 70)
        self.assertEqual(set(story_content.STORY_RELIC_IMAGE_URLS), set(known))
        for relic_id in known:
            self.assertEqual(
                story_content.STORY_RELIC_IMAGE_URLS[relic_id],
                f'{EXPECTED_IMAGE_PREFIX}{relic_id}.svg',
                f'{relic_id} 缺少贴图地址',
            )

    def test_known_missing_talent_stays_without_url(self):
        for relic_id in KNOWN_MISSING:
            self.assertIn(relic_id, STORY_RELICS)
            self.assertNotIn(relic_id, story_content.STORY_RELIC_IMAGE_URLS)

    def test_image_url_is_added_only_by_the_story_payload(self):
        # 协作模式编译器要求遗物字段集合严格等于 7 个字段，本体不能多出 image_url。
        for relic_id, definition in STORY_RELICS.items():
            self.assertNotIn('image_url', definition, f'{relic_id} 污染了 STORY_RELICS')

    def test_asset_files_exist_and_are_svg(self):
        for relic_id, definition in STORY_RELICS.items():
            if relic_id in KNOWN_MISSING:
                continue
            path = ASSET_DIR / f'{relic_id}.svg'
            self.assertTrue(path.is_file(), f'缺少天赋贴图文件：{path}')
            head = _read(path)[:4000].lower()
            self.assertIn('<svg', head, f'{path} 不是 SVG')
            self.assertGreater(path.stat().st_size, 200, f'{path} 太小，可能是空文件')

    def test_no_orphan_asset_files(self):
        expected = {
            f'{relic_id}.svg'
            for relic_id in STORY_RELICS
            if relic_id not in KNOWN_MISSING
        }
        actual = {path.name for path in ASSET_DIR.glob('*.svg')}
        self.assertEqual(actual, expected)

    def test_payload_carries_versioned_asset_urls(self):
        payload = story_content.story_content_payload(asset_version='v9')
        relics = payload['relics']
        self.assertEqual(len(relics), len(STORY_RELICS))
        self.assertTrue(relics['energetic']['image_url'].endswith('energetic.svg?v=v9'))
        self.assertNotIn('image_url', relics['miracle_spring'])


class TestTalentIconRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = _read(ROOT / 'static' / 'js' / 'story.js')
        cls.css = _read(ROOT / 'static' / 'css' / 'story.css')

    def test_js_exposes_relic_icon_helpers(self):
        self.assertIn('function storyRelicIconUrl(relicKey)', self.js)
        self.assertIn("String(storyRelicDefinition(relicKey)?.image_url || '').trim()", self.js)
        self.assertIn('function createStoryRelicIcon(relicKey, className)', self.js)
        self.assertIn("icon.className = className || 'story-relic-icon';", self.js)

    def test_js_renders_icons_in_every_relic_surface(self):
        # 天赋总览
        self.assertRegex(
            self.js,
            r"marker\.className = 'story-talent-overview-marker';[\s\S]{0,400}has-icon",
        )
        # 图鉴天赋详情
        self.assertRegex(
            self.js,
            r"marker\.className = 'story-codex-talent-marker';[\s\S]{0,500}has-icon",
        )
        # 天赋三选一
        self.assertRegex(
            self.js,
            r"mark\.className = 'story-choice-mark';[\s\S]{0,400}createStoryRelicIcon",
        )
        # 术语徽标 / 合作商店 / 历史记录
        self.assertIn("const badgeIcon = createStoryRelicIcon(item.id);", self.js)
        self.assertIn("const shopIcon = createStoryRelicIcon(relicId);", self.js)
        self.assertIn("const chipIcon = createStoryRelicIcon(relicId);", self.js)

    def test_css_sizes_the_icons(self):
        self.assertIn('.story-talent-overview-marker.has-icon', self.css)
        self.assertIn('.story-codex-talent-marker.has-icon', self.css)
        self.assertIn('.story-choice-mark.has-icon img', self.css)
        self.assertNotIn('.story-choice-mark.has-icon::after', self.css)
        self.assertIn('.story-history-relic-chip img', self.css)
        self.assertIn('.story-coop-shop-relic img', self.css)
        self.assertRegex(
            self.css,
            r'\.story-talent-overview-marker img,[\s\S]{0,200}object-fit: contain;',
        )


class TestTalentIconVersion(unittest.TestCase):
    def test_static_version_mentions_talent_icons(self):
        version = _read(ROOT / 'static_version.txt').strip()
        self.assertIn('-story-talent-icons-1', version)


if __name__ == '__main__':
    unittest.main()
