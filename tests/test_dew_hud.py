# -*- coding: utf-8 -*-
"""玩家页面右上角荆露 / 金露余额栏。"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE_BINARY = os.environ.get('GTN_NODE_BINARY') or shutil.which('node')
TEMPLATES = ('index.html', 'story.html', 'minigame_2048.html', 'minigame_suika.html', 'afdian.html')


class DewHudTests(unittest.TestCase):
    def test_assets_and_all_player_templates_are_registered(self):
        self.assertTrue((ROOT / 'static/assets/ui-icons/thorn-dew.svg').is_file())
        self.assertTrue((ROOT / 'static/assets/ui-icons/golden-dew.svg').is_file())
        css = (ROOT / 'static/css/dew-hud.css').read_text(encoding='utf-8')
        self.assertIn('position: fixed', css)
        self.assertIn('pointer-events: none', css)
        for name in TEMPLATES:
            with self.subTest(template=name):
                page = (ROOT / 'templates' / name).read_text(encoding='utf-8')
                self.assertEqual(page.count('/static/css/dew-hud.css'), 1)
                self.assertEqual(page.count('/static/js/dew-hud.js'), 1)
                self.assertLess(page.index('/static/css/reward-animation.css'), page.index('/static/css/dew-hud.css'))
                self.assertLess(page.index('/static/js/reward-animation.js'), page.index('/static/js/dew-hud.js'))
        self.assertIn('-dew-hud-1', (ROOT / 'static_version.txt').read_text(encoding='utf-8'))

    def test_hud_is_hidden_during_battle_and_spectate(self):
        css = (ROOT / 'static/css/dew-hud.css').read_text(encoding='utf-8')
        self.assertIn('body:has(#view-game:not(.hidden)) .dew-hud { display: none; }', css)

    def test_hud_is_hidden_throughout_story_mode(self):
        css = (ROOT / 'static/css/dew-hud.css').read_text(encoding='utf-8')
        self.assertIn('body:has(#story-app:not(.hidden)) .dew-hud { display: none; }', css)
        story = (ROOT / 'templates/story.html').read_text(encoding='utf-8')
        self.assertIn('id="story-app"', story)

    @unittest.skipUnless(NODE_BINARY, '需要 Node.js；可用 GTN_NODE_BINARY 指定路径')
    def test_script_reads_balances_refreshes_and_hides_logged_out(self):
        source = (ROOT / 'static/js/dew-hud.js').read_text(encoding='utf-8')
        self.assertIn('data.balance.total', source)
        self.assertIn('data.golden_balance', source)
        harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
function makeClassList(initial) {
  const values = new Set(initial);
  return {
    contains: (value) => values.has(value),
    add: (value) => values.add(value),
    remove: (value) => values.delete(value),
  };
}
class Element {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.hidden = false;
    this.textContent = '';
  }
  appendChild(child) { this.children.push(child); return child; }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  querySelector(selector) {
    const key = selector.match(/data-dew-hud-value="([^"]+)"/)[1];
    const walk = (node) => {
      if (node.dataset.dewHudValue === key) return node;
      for (const child of node.children) {
        const result = walk(child);
        if (result) return result;
      }
      return null;
    };
    return walk(this);
  }
}
const viewGame = new Element('div');
viewGame.classList = makeClassList(['view', 'hidden']);
const storyApp = new Element('div');
storyApp.classList = makeClassList(['hidden']);
const views = { 'view-game': viewGame, 'story-app': storyApp };
const document = {
  readyState: 'loading',
  hidden: false,
  documentElement: { lang: 'zh-CN' },
  body: new Element('body'),
  createElement: (tag) => new Element(tag),
  getElementById: (id) => views[id] || null,
  addEventListener: (name, callback) => { document.listeners[name] = callback; },
  listeners: {},
};
class MutationObserver {
  constructor(callback) { this.callback = callback; }
  observe(target) { target.viewObserver = this; }
}
function setViewVisible(view, visible) {
  if (visible) view.classList.remove('hidden');
  else view.classList.add('hidden');
  view.viewObserver.callback([]);
}
let intervalCount = 0;
let fetchCount = 0;
const responses = [
  { ok: true, json: async () => ({ success: true, balance: { total: 12345 }, golden_balance: 678 }) },
  { ok: true, json: async () => ({ success: true, balance: { total: -12345 }, golden_balance: -678 }) },
  { ok: false, json: async () => ({ success: false }) },
];
const context = {
  document,
  window: { setInterval: () => { intervalCount += 1; }, MutationObserver },
  fetch: async () => { fetchCount += 1; return responses[Math.min(fetchCount - 1, responses.length - 1)]; },
};
vm.runInNewContext(SOURCE, context);
assert.equal(document.body.children.length, 0);
document.listeners.DOMContentLoaded();
document.listeners.DOMContentLoaded();
setImmediate(async () => {
  try {
    const hud = document.body.children[0];
    assert.equal(document.body.children.length, 1);
    assert.equal(intervalCount, 1);
    assert.equal(fetchCount, 1);
    assert.equal(hud.hidden, false);
    assert.equal(hud.children[0].children[1].textContent, '12,345');
    assert.equal(hud.children[1].children[1].textContent, '678');
    assert.equal(hud.children[0].children[0].src, '/static/assets/ui-icons/thorn-dew.svg');
    assert.equal(hud.children[1].children[0].src, '/static/assets/ui-icons/golden-dew.svg');
    setViewVisible(viewGame, true);
    assert.equal(hud.hidden, true, '进入对局或观战后应立即隐藏');
    await context.window.GtnDewHud.refresh();
    assert.equal(fetchCount, 2);
    assert.equal(hud.children[0].children[1].textContent, '-12,345');
    assert.equal(hud.children[1].children[1].textContent, '-678');
    assert.equal(hud.hidden, true, '观战中的余额刷新不得重新显示货币栏');
    setViewVisible(viewGame, false);
    assert.equal(hud.hidden, false, '退出对局或观战后应恢复');
    setViewVisible(storyApp, true);
    assert.equal(hud.hidden, true, '故事模式应保持隐藏');
    setViewVisible(storyApp, false);
    assert.equal(hud.hidden, false);
    await context.window.GtnDewHud.refresh();
    assert.equal(fetchCount, 3);
    assert.equal(hud.hidden, true, '退出登录后应隐藏');
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  }
});
'''.replace('SOURCE', json.dumps(source))
        result = subprocess.run(
            [NODE_BINARY, '-e', harness], cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
