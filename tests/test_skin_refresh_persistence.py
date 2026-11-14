"""刷新后皮肤界面的眼睛/嘴型不能被「拥有列表未知」重置。

2026-11-14 的 bug：刷新页面后第一次进入皮肤界面，/api/eye-styles 与
/api/mouth-styles 还没返回，`updateSkinEyeShapeOptions` 把 owned=null 当成
「什么都没有」，于是把已保存的 angry/coin/dizzy 等眼睛改成 oval、把 cat/smirk
等嘴型改成 original。这里锁住「未知 ≠ 未拥有」的契约。
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / 'static/js/game.js'


class SkinRefreshPersistenceTests(unittest.TestCase):
    def _segment(self, start_marker, end_marker):
        source = GAME.read_text(encoding='utf-8')
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def test_eye_shape_options_do_not_reset_before_ownership_is_known(self):
        segment = self._segment('function updateSkinEyeShapeOptions()', 'async function loadEyeStyleOwnership(')
        self.assertIn('const known = Array.isArray(owned);', segment)
        self.assertIn('option.disabled = known ? !allowed : false;', segment)
        self.assertIn(
            "if (known && select.selectedIndex >= 0 && select.options[select.selectedIndex].disabled) select.value = 'oval';",
            segment,
        )
        self.assertNotIn(
            "if (select.selectedIndex >= 0 && select.options[select.selectedIndex].disabled) select.value = 'oval';",
            segment,
        )

    def test_mouth_shape_options_do_not_reset_before_ownership_is_known(self):
        segment = self._segment('function updateSkinMouthShapeOptions()', 'async function loadMouthStyleOwnership(')
        self.assertIn('const known = Array.isArray(owned);', segment)
        self.assertIn('option.disabled = known ? !allowed : false;', segment)
        self.assertIn(
            "if (known && select.selectedIndex >= 0 && select.options[select.selectedIndex].disabled) select.value = 'original';",
            segment,
        )
        self.assertNotIn(
            "if (select.selectedIndex >= 0 && select.options[select.selectedIndex].disabled) select.value = 'original';",
            segment,
        )

    def test_skin_form_is_seeded_from_the_saved_account_skin(self):
        segment = self._segment('function syncSkinFormFromCurrent()', 'async function saveSkinFromEditor()')
        self.assertIn('if (shapeSelect) shapeSelect.value = skin.eye_shape;', segment)
        self.assertIn('if (mouthSelect) mouthSelect.value = skin.mouth_shape;', segment)
        # 先写选中值，再拉拥有列表（ajax 回来后只会禁用未拥有的选项）。
        self.assertLess(segment.index('shapeSelect.value = skin.eye_shape'), segment.index('updateSkinEyeShapeOptions();'))
        self.assertLess(segment.index('mouthSelect.value = skin.mouth_shape'), segment.index('updateSkinMouthShapeOptions();'))


if __name__ == '__main__':
    unittest.main()
