# -*- coding: utf-8 -*-
"""玩家形象贴图／装饰层及其存档兼容测试。"""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

import db


ROOT = Path(__file__).resolve().parents[1]
PLAYER_SKINS_JS = (ROOT / 'static/js/player-skins.js').read_text(encoding='utf-8')
PLAYER_SKINS_CSS = (ROOT / 'static/css/player-skins.css').read_text(encoding='utf-8')
GAME_JS = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
STORY_JS = (ROOT / 'static/js/story.js').read_text(encoding='utf-8')
SUIKA_JS = (ROOT / 'static/js/minigame_suika.js').read_text(encoding='utf-8')
DIRECT_NODE = Path.home() / 'AppData/Local/Programs/Kimi/resources/resources/runtime/node.cmd'
NODE = str(DIRECT_NODE) if DIRECT_NODE.exists() else shutil.which('node')


def source_between(source, start, end):
    start_index = source.index(start)
    return source[start_index:source.index(end, start_index)]


class PlayerSkinConfigTests(unittest.TestCase):
    def test_valid_ids_and_legacy_configs_are_normalized(self):
        for skin_id in sorted(db.SKIN_IDS):
            normalized = db.normalize_skin_config({
                'primary_color': '#a1b2c3',
                'eye_shape': 'diamond',
                'skin_id': skin_id,
            })
            self.assertEqual(normalized, {
                'primary_color': '#A1B2C3',
                'eye_shape': 'diamond',
                'mouth_shape': 'original',
                'skin_id': skin_id,
            })
        legacy = db.normalize_skin_config({'primary_color': '#FFE763'})
        self.assertEqual(legacy['skin_id'], 'classic')
        camel_case = db.normalize_skin_config({'skinId': 'GHOST'})
        self.assertEqual(camel_case['skin_id'], 'ghost')
        from_json = db.normalize_skin_config('{"skin_id":"ghost"}')
        self.assertEqual(from_json['skin_id'], 'ghost')

    def test_unknown_or_unsafe_ids_fall_back_to_classic(self):
        for value in ('unknown', 'sprout', 'thorn', 'javascript:alert(1)', '../../secret', {'id': 'ghost'}):
            normalized = db.normalize_skin_config({'skin_id': value})
            self.assertEqual(normalized['skin_id'], 'classic')


@unittest.skipIf(NODE is None, '需要 Node.js 检查共享玩家皮肤目录')
class PlayerSkinCatalogTests(unittest.TestCase):
    def test_shared_catalog_and_layer_markup(self):
        script = (
            'const vm = require("vm");\n'
            'globalThis.window = {};\n'
            f'vm.runInThisContext({json.dumps(PLAYER_SKINS_JS)});\n'
            'console.log(JSON.stringify({\n'
            '  ids: window.GTNPlayerSkins.definitions.map((item) => item.id),\n'
            '  definitions: window.GTNPlayerSkins.definitions,\n'
            '  fixedColorIds: window.GTNPlayerSkins.definitions.filter((item) => item.fixedColor).map((item) => item.id),\n'
            '  invalid: window.GTNPlayerSkins.normalize("../../secret"),\n'
            '  classic: window.GTNPlayerSkins.renderLayers("classic"),\n'
            '  ghost: window.GTNPlayerSkins.renderLayers("ghost"),\n'
            '  facelessSvg: decodeURIComponent(window.GTNPlayerSkins.textureUrl("faceless", "#123456", "#654321").split(",").slice(1).join(",")),\n'
            '  ghostColor: window.GTNPlayerSkins.textureUrl("ghost", "#123456", "#654321"),\n'
            '  corruptedColor: window.GTNPlayerSkins.textureUrl("corrupted", "#123456", "#654321"),\n'
            '  eyelessClasses: window.GTNPlayerSkins.layerClass("nazar"),\n'
            '  rotations: [\n'
            '    window.GTNPlayerSkins.lookRotation({ x: 0.707, y: -0.707 }),\n'
            '    window.GTNPlayerSkins.lookRotation({ x: 1, y: 0 }),\n'
            '    window.GTNPlayerSkins.lookRotation({ x: 0, y: 1 }),\n'
            '  ],\n'
            '}));\n'
        )
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.cjs', prefix='tmp_player_skins_',
            dir=ROOT, delete=False, encoding='utf-8',
        ) as script_file:
            script_path = Path(script_file.name)
            script_file.write(script)
        try:
            try:
                completed = subprocess.run(
                    [NODE, str(script_path)], capture_output=True,
                    text=True, encoding='utf-8', timeout=20,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
                output = completed.stdout
            except subprocess.TimeoutExpired as exc:
                # eventlet 接管 subprocess/time 后，已完成进程也可能抛出负剩余时间。
                if not exc.stdout:
                    self.fail(f'Node 未返回皮肤目录：{exc.stderr or "无错误输出"}')
                output = exc.stdout
        finally:
            script_path.unlink(missing_ok=True)
        result = json.loads(output)
        self.assertEqual(set(result['ids']), db.SKIN_IDS)
        self.assertEqual(set(result['fixedColorIds']), {
            'corrupted', 'mark', 'nazar',
            'centipede_head', 'desert_centipede_head', 'evil_centipede_head',
            'tower_curse_ironclad', 'tower_curse_silent', 'tower_curse_defect',
            'tower_curse_necrobinder', 'tower_curse_regent',
        })
        self.assertEqual(result['invalid'], 'classic')
        self.assertEqual(result['classic'], '')
        self.assertIn('fill="#123456"', result['facelessSvg'])
        self.assertIn('stroke="#654321"', result['facelessSvg'])
        self.assertNotIn('__FILL__', result['facelessSvg'])
        self.assertNotIn('__STROKE__', result['facelessSvg'])
        self.assertTrue(result['ghostColor'].startswith('data:image/svg+xml'))
        self.assertEqual(result['corruptedColor'], '/static/assets/player-avatars/corrupted-body.svg')
        self.assertEqual(result['ghost'].count('skin-texture-layer'), 1)
        self.assertEqual(result['ghost'].count('skin-decoration-layer'), 0)
        self.assertIn('skin-hide-eyes', result['eyelessClasses'])
        self.assertIn('skin-hide-mouth', result['eyelessClasses'])
        for actual, expected in zip(result['rotations'], (0, 45, 135)):
            self.assertAlmostEqual(actual, expected, places=6)
        for definition in result['definitions']:
            if definition['id'] in {'faceless', 'ghost', 'brain_damage', 'right_angle'}:
                self.assertTrue(definition.get('art'), definition['id'])
            if definition['id'] in {
                'corrupted', 'mark', 'nazar',
                'centipede_head', 'desert_centipede_head', 'evil_centipede_head',
            }:
                self.assertFalse(definition.get('art'), definition['id'])
            for key in ('texture', 'decoration'):
                relative = definition[key]
                if not relative:
                    continue
                path = ROOT / 'static' / relative.removeprefix('/static/')
                # 所有共享目录资源必须位于 static 内，不能逃逸到工作区外。
                self.assertTrue(path.is_file(), relative)
                svg = ET.parse(path).getroot()
                self.assertTrue(svg.attrib.get('viewBox'), relative)


class PlayerSkinRenderingContractTests(unittest.TestCase):
    def test_all_player_pages_load_shared_catalog_and_styles(self):
        for relative, renderer in (
            ('templates/index.html', 'game.js'),
            ('templates/story.html', 'story.js'),
            ('templates/minigame_suika.html', 'minigame_suika.js'),
        ):
            page = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn('/static/css/player-skins.css', page, relative)
            self.assertLess(page.index('/static/js/player-skins.js'), page.index(renderer), relative)
        index = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        self.assertIn('id="skin-preset-list"', index)
        self.assertIn('role="radiogroup"', index)

    def test_fixed_color_skins_use_original_palette(self):
        self.assertEqual(PLAYER_SKINS_JS.count('fixedColor: true'), 11)
        self.assertIn('get(selected).fixedColor', GAME_JS)
        self.assertNotIn('get(selected).bodyArt', GAME_JS)
        self.assertIn('renderLayers(skin.skin_id, { mainColor, borderColor: border }', GAME_JS)
        self.assertIn('renderLayers(skin.skinId, {', STORY_JS)
        self.assertIn('renderLayers(seatSkin.skinId, {', STORY_JS)
        self.assertIn('window.GTNPlayerSkins?.textureUrl', SUIKA_JS)

    def test_main_renderer_preserves_dynamic_face_and_battle_states(self):
        renderer = source_between(GAME_JS, 'function renderSkinAvatar', 'function renderSkinPresetList')
        for marker in ('skinLayers', 'skin-eye-left', 'skin-mouth-line', 'damageMood', 'is-corrupted', 'is-defeated'):
            self.assertIn(marker, renderer)
        self.assertIn('skin-eye-left', STORY_JS)
        self.assertIn('seatSkin.skinId', STORY_JS)
        self.assertIn('storySkinMouthPathAt', STORY_JS)
        texture = SUIKA_JS.index('target.drawImage(playerSkinTexture')
        face = SUIKA_JS.index('drawSkinFace(', texture)
        decoration = SUIKA_JS.index('target.drawImage(playerSkinDecoration', face)
        self.assertLess(texture, face)
        self.assertLess(face, decoration)

    def test_eyeless_and_mouthless_skins_hide_dynamic_face(self):
        for skin_id in (
            'faceless', 'nazar', 'centipede_head', 'desert_centipede_head', 'evil_centipede_head',
            'tower_curse_ironclad', 'tower_curse_silent', 'tower_curse_defect',
            'tower_curse_necrobinder', 'tower_curse_regent',
        ):
            self.assertIn(f"id: '{skin_id}'", PLAYER_SKINS_JS)
        self.assertEqual(PLAYER_SKINS_JS.count('hideEyes: true'), 10)
        self.assertEqual(PLAYER_SKINS_JS.count('hideMouth: true'), 10)
        self.assertIn('skin-hide-eyes', PLAYER_SKINS_CSS)
        self.assertIn('skin-hide-mouth', PLAYER_SKINS_CSS)
        self.assertIn('rotate(var(--skin-look-rotate', PLAYER_SKINS_CSS)
        self.assertIn('if (!definition?.hideEyes || !definition?.hideMouth)', SUIKA_JS)
        self.assertIn('!definition?.hideEyes, !definition?.hideMouth', SUIKA_JS)
        self.assertIn('function lookRotation', PLAYER_SKINS_JS)
        self.assertIn('window.GTNPlayerSkins?.lookRotation', GAME_JS)
        self.assertIn('window.GTNPlayerSkins?.lookRotation', STORY_JS)

    def test_centipede_textures_are_calibrated_to_face_mouse(self):
        for skin_id in ('centipede_head', 'desert_centipede_head', 'evil_centipede_head'):
            self.assertRegex(PLAYER_SKINS_JS, rf"id: '{skin_id}',[\s\S]{{0,700}}?textureRotate: 90")
        self.assertEqual(PLAYER_SKINS_JS.count('textureRotate: 90'), 3)
        self.assertIn('--skin-texture-rotate', PLAYER_SKINS_JS)
        self.assertIn('transform: rotate(var(--skin-texture-rotate', PLAYER_SKINS_CSS)
        self.assertIn('const textureRotate = Number(definition?.textureRotate)', SUIKA_JS)

    def test_css_keeps_texture_below_face_and_decoration_above_it(self):
        self.assertIn('.skin-avatar .skin-texture-layer', PLAYER_SKINS_CSS)
        self.assertIn('.skin-avatar .skin-decoration-layer', PLAYER_SKINS_CSS)
        self.assertIn('z-index: 1;', source_between(PLAYER_SKINS_CSS, '.skin-avatar .skin-texture-layer {', '}'))
        face = source_between(PLAYER_SKINS_CSS, '.skin-avatar .skin-eye,', '/* 外观')
        self.assertIn('z-index: 2;', face)
        self.assertIn('.skin-avatar .skin-decoration-layer {\n  z-index: 3;', PLAYER_SKINS_CSS)


if __name__ == '__main__':
    unittest.main()
