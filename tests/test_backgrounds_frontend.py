# -*- coding: utf-8 -*-
"""背景系统前端资源、视图切换与独立商店契约。"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = os.environ.get('GTN_NODE_BINARY') or shutil.which('node')


class BackgroundFrontendTests(unittest.TestCase):
    def test_shop_inventory_and_player_pages_are_registered(self):
        index = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
        game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
        for marker in (
            'data-shop-tab="theme-backgrounds"', 'data-shop-tab="battle-backgrounds"',
            'theme-background-shop-grid', 'battle-background-shop-grid',
            'data-skin-tab="backgrounds"', 'theme-background-list', 'battle-background-list',
        ):
            self.assertIn(marker, index)
        for marker in ('loadBackgroundShops', 'purchaseBackground', 'refreshBackgroundShop', 'equipBackground', 'renderBackgroundInventory'):
            self.assertIn(marker, game)
        for name in ('index.html', 'minigame_2048.html', 'minigame_suika.html', 'afdian.html', 'titleeditor.html'):
            with self.subTest(template=name):
                page = (ROOT / 'templates' / name).read_text(encoding='utf-8')
                self.assertEqual(page.count('/static/css/backgrounds.css'), 1)
                self.assertEqual(page.count('/static/js/backgrounds.js'), 1)
        story = (ROOT / 'templates/story.html').read_text(encoding='utf-8')
        self.assertNotIn('/static/css/backgrounds.css', story)
        self.assertNotIn('/static/js/backgrounds.js', story)

    def test_theme_assets_and_all_battle_biomes_exist(self):
        source = (ROOT / 'static/js/backgrounds.js').read_text(encoding='utf-8')
        for old_id in ('olive_nocturne', 'desert_mist', 'parchment_grove'):
            self.assertNotIn(f"id: '{old_id}'", source)
        for biome in ('garden', 'desert', 'ocean', 'jungle', 'factory'):
            self.assertEqual(source.count(f"id: '{biome}'"), 2, biome)
            self.assertIn(f"data-biome='{biome}'", (ROOT / 'static/css/backgrounds.css').read_text(encoding='utf-8'))

    def test_backdrop_generation_restores_story_original_layers(self):
        source = (ROOT / 'static/js/backgrounds.js').read_text(encoding='utf-8')
        renderer = source[source.index('function renderBiome'):source.index('function removeTheme')]
        self.assertIn("['story-backdrop-v3', visualSeed, 1, biome]", renderer)
        self.assertIn('appendBase(container, signature, biome);', renderer)
        self.assertIn('appendGardenPatches(container, signature);', renderer)
        self.assertIn('appendDesertPatches(container, signature);', renderer)
        self.assertIn('appendLandmarks(container, signature, biome);', renderer)
        self.assertNotIn('appendPatches(', renderer)
        self.assertEqual(source.count('range(seed, `${key}:ratio`, .8, 1.2)'), 1)
        self.assertEqual(source.count('range(seed, `${key}:ratio`, .68, 1.18)'), 1)
        self.assertIn('range(seed, `${key}:width`, 3.2, 7.2)', source)
        self.assertIn('if (unit(seed, `${key}:present`) > .92) continue;', source)
        self.assertNotIn('range(seed, `${key}:ratio`, .28, .62)', source)

    def test_background_readability_override_is_reverted(self):
        css = (ROOT / 'static/css/backgrounds.css').read_text(encoding='utf-8')
        for marker in (
            '--player-readable-surface', '--player-readable-border', '--player-readable-halo',
            'body.has-player-theme-background #app .view :is(h1, h2, h3, h4)',
            'body.has-player-theme-background #view-login .home-extra-entry .btn',
            'body[data-player-battle-background] .battle-classic .classic-top-hud',
            'backdrop-filter: blur(8px)', 'outline: 3px solid var(--magic, #3498db)',
        ):
            self.assertNotIn(marker, css)
        self.assertNotIn('/* 彩色背景上的文字和控件', css)
        self.assertIn('.title-shop-tabs { grid-template-columns: repeat(8, minmax(0, 1fr)); }', css)

    @unittest.skipUnless(NODE, '需要 Node.js 验证背景视图切换')
    def test_theme_and_battle_backgrounds_switch_with_game_view(self):
        source = (ROOT / 'static/js/backgrounds.js').read_text(encoding='utf-8')
        theme_css = (ROOT / 'static/css/backgrounds.css').read_text(encoding='utf-8')
        harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.style = {};
    this.parentNode = null;
    const values = new Set();
    this.classList = {
      add: (...items) => items.forEach(item => values.add(item)),
      remove: (...items) => items.forEach(item => values.delete(item)),
      contains: (item) => values.has(item),
    };
  }
  append(...nodes) { nodes.forEach(node => { node.parentNode = this; this.children.push(node); }); }
  prepend(...nodes) { nodes.forEach(node => { node.parentNode = this; this.children.unshift(node); }); }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }
  setAttribute(key, value) { this.attributes[key] = String(value); }
}
const game = new Element('div');
game.id = 'view-game';
game.classList.add('hidden');
const body = new Element('body');
const views = { 'view-game': game, 'story-app': null };
const document = {
  readyState: 'loading',
  body,
  createElement: (tag) => new Element(tag),
  createDocumentFragment: () => new Element('fragment'),
  getElementById: (id) => views[id] || null,
  addEventListener: (name, callback) => { document.listeners[name] = callback; },
  listeners: {},
};
class MutationObserver {
  constructor(callback) { this.callback = callback; }
  observe(target) { target.observer = this; }
}
const context = {
  document,
  window: { MutationObserver },
  fetch: async () => ({
    ok: true,
    json: async () => ({ success: true, preferences: { theme: 'garden', battle: 'garden' }, shops: {} }),
  }),
};
vm.runInNewContext(SOURCE, context);
document.listeners.DOMContentLoaded();
setImmediate(() => {
  try {
    assert.equal(body.children.length, 1, '普通界面应显示主题背景');
    assert.equal(body.children[0].id, 'player-theme-backdrop');
    assert.equal(game.children.length, 0, '普通界面不显示战斗背景');
    game.classList.remove('hidden');
    game.observer.callback([]);
    assert.equal(body.children.length, 0, '对局／观战应隐藏主题背景');
    assert.equal(game.children.length, 1, '对局／观战应显示战斗背景');
    assert.equal(game.children[0].id, 'player-battle-backdrop');
    assert.equal(game.children.some(function hasPatch(node) {
      return /story-seeded-backdrop-(patch|landmark)/.test(String(node.className || '')) || node.children.some(hasPatch);
    }), true, '应完整保留故事原版色块和地标');
    const allPatches = [];
    function collectPatches(node) {
      if (String(node.className || '').includes('story-seeded-backdrop-patch') && node.style.width && node.style.height) {
        allPatches.push(node);
      }
      node.children.forEach(collectPatches);
    }
    ['garden', 'desert', 'ocean', 'jungle', 'factory'].forEach((biome) => {
      const preview = context.window.GtnBackgrounds.createPreview('battle', biome);
      assert.equal(preview.dataset.biome, biome, `${biome} 应使用对应群系`);
      assert.equal(preview.children.length > 0, true, `${biome} 应保留底纹或地标`);
      collectPatches(preview);
    });
    assert.equal(allPatches.length > 0, true, '全部群系的色块应保留');
    allPatches.forEach((patch) => {
      const ratio = parseFloat(patch.style.height) / parseFloat(patch.style.width);
      const garden = /is-(dark|light)/.test(String(patch.className || ''));
      const minimum = garden ? 0.68 : 0.8;
      const maximum = garden ? 1.18 : 1.2;
      assert.equal(ratio >= minimum && ratio <= maximum, true, `色块应保持故事原版比例而非异常长条：${ratio}`);
    });
    const organicGarden = context.window.GtnBackgrounds.createPreview('theme', 'garden');
    function assertOrganicPatches(node) {
      if (String(node.className || '').includes('story-seeded-backdrop-patch') && node.style.width) {
        assert.notEqual(node.style.borderRadius, '50%', '花园色块应使用故事原版圆角样式');
        const width = parseFloat(node.style.width);
        assert.equal(width >= 3.2 && width <= 7.2, true, '花园色块应恢复故事原版尺寸');
      }
      node.children.forEach(assertOrganicPatches);
    }
    assertOrganicPatches(organicGarden);
    function hasLandmark(node, className) {
      return String(node.className || '').includes(className) || node.children.some(child => hasLandmark(child, className));
    }
    assert.equal(hasLandmark(organicGarden, 'is-rock'), true, '修正高度覆盖后应保留岩石地标');
    assert.equal(hasLandmark(organicGarden, 'is-sunflower'), true, '修正高度覆盖后应保留向日葵地标');
    assert.match(THEME_CSS, /\.player-theme-backdrop > img \{[^}]*height: 100%;/, '整幅贴图样式不得覆盖内部 SVG 地标');
    assert.match(THEME_CSS, /\.player-theme-backdrop \.story-seeded-backdrop-landmark \{[^}]*height: auto;/, '地标应使用 SVG 固有比例，不得拉伸为背景高度');
    game.classList.add('hidden');
    game.observer.callback([]);
    assert.equal(game.children.length, 0, '退出后移除战斗背景');
    assert.equal(body.children.length, 1, '退出后恢复主题背景');
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  }
});
'''.replace('SOURCE', json.dumps(source)).replace('THEME_CSS', json.dumps(theme_css))
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.cjs', prefix='tmp_backgrounds_', dir=ROOT, delete=False, encoding='utf-8',
        ) as script_file:
            script_path = Path(script_file.name)
            script_file.write(harness)
        try:
            result = subprocess.run(
                [NODE, str(script_path)], cwd=ROOT, capture_output=True, text=True, timeout=60,
            )
        finally:
            script_path.unlink(missing_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == '__main__':
    unittest.main()
