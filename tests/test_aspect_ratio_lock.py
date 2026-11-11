# -*- coding: utf-8 -*-
"""设置 · 锁定长宽比：16:9 等比布局、持久化与关闭恢复。"""

import json
from pathlib import Path
import shutil
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
GAME_SOURCE = (ROOT / 'static' / 'js' / 'game.js').read_text(encoding='utf-8')
INDEX_HTML = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
START = 'function calculateAspectRatioLockSize('
END = 'function getPageFullscreenElement('
ASPECT_SOURCE = START + GAME_SOURCE.split(START, 1)[1].split(END, 1)[0]
VIEWPORT_START = 'function readClassicViewportSize()'
VIEWPORT_END = 'function getClassicViewportSize('
VIEWPORT_SOURCE = VIEWPORT_START + GAME_SOURCE.split(VIEWPORT_START, 1)[1].split(VIEWPORT_END, 1)[0]
DIRECT_NODE = Path.home() / 'AppData/Local/Programs/Kimi/resources/resources/runtime/node.cmd'
NODE = str(DIRECT_NODE) if DIRECT_NODE.exists() else shutil.which('node')


class AspectRatioLockContractTests(unittest.TestCase):
    def test_setting_storage_and_translation_contract(self):
        self.assertIn('id="settings-lock-aspect-ratio"', INDEX_HTML)
        self.assertIn('id="settings-label-lock-aspect-ratio"', INDEX_HTML)
        self.assertIn('锁定长宽比（16:9）', INDEX_HTML)
        self.assertIn("setText('#settings-label-lock-aspect-ratio', t.lockAspectRatio)", INDEX_HTML)
        for language in ('en', 'zh', 'fr', 'ja'):
            marker = f'Object.assign(I18N.{language}, {{ settings_landscape_mode:'
            section = GAME_SOURCE[GAME_SOURCE.index(marker):]
            section = section[:section.index('});')]
            self.assertIn('settings_lock_aspect_ratio:', section)
        for start, end in (
            ('const GTN_BETA_STORAGE_EXACT_KEYS', 'const GTN_BETA_STORAGE_PREFIXES'),
            ('const GTN_COOKIE_FALLBACK_KEYS', 'const gtnConfirmedCookieFallbackKeys'),
        ):
            section = GAME_SOURCE.split(start, 1)[1].split(end, 1)[0]
            self.assertIn("'gtn_lock_aspect_ratio'", section)
        self.assertIn('handleBattleViewportResize', GAME_SOURCE)
        self.assertIn('handleFullscreenChange', GAME_SOURCE)


@unittest.skipIf(NODE is None, '需要 Node.js 运行布局行为测试')
class AspectRatioLockBehaviorTests(unittest.TestCase):
    def run_scenario(self, body):
        harness = textwrap.dedent(
            f'''
            const vm = require('vm');
            const aspectSource = {json.dumps(ASPECT_SOURCE)};
            const viewportSource = {json.dumps(VIEWPORT_SOURCE)};
            function makeStyle() {{
                const values = {{}};
                const target = {{
                    values,
                    setProperty(key, value) {{ values[key] = String(value); }},
                    getPropertyValue(key) {{ return values[key] || ''; }},
                    removeProperty(key) {{ const old = values[key]; delete values[key]; return old || ''; }},
                }};
                return new Proxy(target, {{
                    set(object, key, value) {{
                        object[key] = value;
                        if (!['values', 'setProperty', 'getPropertyValue', 'removeProperty'].includes(key)) {{
                            values[key] = String(value);
                        }}
                        return true;
                    }},
                }});
            }}
            const app = {{ style: makeStyle() }};
            const classes = {{}};
            const root = {{
                clientWidth: 1000,
                clientHeight: 1000,
                style: makeStyle(),
                classList: {{ toggle: (name, value) => {{ classes[name] = !!value; }} }},
            }};
            const checkbox = {{ checked: false }};
            const storage = {{}};
            const scenario = {{
                app, root, classes, checkbox, storage,
                window: {{ innerWidth: 1000, innerHeight: 1000, visualViewport: null }},
                document: {{ documentElement: root }},
                localStorage: {{ setItem: (key, value) => {{ storage[key] = String(value); }} }},
                aspectRatioLocked: false,
                battleMobileStableViewport: {{ width: 1, height: 1 }},
                canvasUpdates: 0,
                adjustCalls: 0,
                updateClassicMobileCanvas() {{ scenario.canvasUpdates += 1; }},
                scheduleAdjust() {{ scenario.adjustCalls += 1; }},
                $(id) {{
                    if (id === 'app') return app;
                    if (id === 'settings-lock-aspect-ratio') return checkbox;
                    return null;
                }},
            }};
            vm.createContext(scenario);
            vm.runInContext(aspectSource, scenario, {{ filename: 'aspect-ratio-lock.js' }});
            vm.runInContext(viewportSource, scenario, {{ filename: 'classic-viewport.js' }});
            '''
        )
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.cjs', prefix='tmp_aspect_ratio_',
            dir=ROOT, delete=False, encoding='utf-8',
        ) as script_file:
            script_path = Path(script_file.name)
            script_file.write(harness + '\n' + textwrap.dedent(body))
        try:
            try:
                completed = subprocess.run(
                    [NODE, str(script_path)],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=5,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
                output = completed.stdout
            except subprocess.TimeoutExpired as exc:
                # 桌面 Electron 转发器可能输出后仍保留父进程；结果完整即可。
                if not exc.stdout:
                    self.fail(f'Node 测试未返回结果：{exc.stderr or "无错误输出"}')
                output = exc.stdout
        finally:
            script_path.unlink(missing_ok=True)
        return json.loads(output)

    def test_lock_size_stays_inside_viewport_at_sixteen_by_nine(self):
        result = self.run_scenario(
            '''
            console.log(JSON.stringify({
                exact: scenario.calculateAspectRatioLockSize(1600, 900),
                square: scenario.calculateAspectRatioLockSize(1000, 1000),
                portrait: scenario.calculateAspectRatioLockSize(390, 844),
                wide: scenario.calculateAspectRatioLockSize(1920, 800),
            }));
            '''
        )
        self.assertEqual(result['exact'], {'width': 1600, 'height': 900})
        self.assertEqual(result['square'], {'width': 1000, 'height': 562})
        self.assertEqual(result['portrait'], {'width': 390, 'height': 219})
        self.assertEqual(result['wide'], {'width': 1422, 'height': 800})

    def test_toggle_persists_resize_and_restores_original_layout(self):
        result = self.run_scenario(
            '''
            scenario.applyAspectRatioLock(true);
            const locked = {
                stored: scenario.storage.gtn_lock_aspect_ratio,
                checked: scenario.checkbox.checked,
                width: scenario.app.style.values.width,
                height: scenario.app.style.values.height,
                position: scenario.app.style.values.position,
                rootClass: scenario.classes['aspect-ratio-locked'],
                viewport: scenario.readClassicViewportSize(),
                stableViewport: scenario.battleMobileStableViewport,
            };
            scenario.window.innerWidth = 390;
            scenario.window.innerHeight = 844;
            scenario.updateAspectRatioLayout();
            const resized = {
                width: scenario.app.style.values.width,
                height: scenario.app.style.values.height,
                viewport: scenario.readClassicViewportSize(),
            };
            scenario.applyAspectRatioLock(false);
            const restored = {
                stored: scenario.storage.gtn_lock_aspect_ratio,
                checked: scenario.checkbox.checked,
                width: scenario.app.style.values.width || '',
                position: scenario.app.style.values.position || '',
                transform: scenario.app.style.values.transform || '',
                flex: scenario.app.style.values.flex || '',
                rootWidth: scenario.root.style.getPropertyValue('--gtn-aspect-lock-width'),
                rootClass: scenario.classes['aspect-ratio-locked'],
                canvasUpdates: scenario.canvasUpdates,
            };
            console.log(JSON.stringify({ locked, resized, restored }));
            '''
        )
        self.assertEqual(result['locked'], {
            'stored': '1',
            'checked': True,
            'width': '1000px',
            'height': '562px',
            'position': 'fixed',
            'rootClass': True,
            'viewport': {'width': 1000, 'height': 562},
            'stableViewport': None,
        })
        self.assertEqual(result['resized'], {
            'width': '390px',
            'height': '219px',
            'viewport': {'width': 390, 'height': 219},
        })
        self.assertEqual(result['restored'], {
            'stored': '0',
            'checked': False,
            'width': '',
            'position': '',
            'transform': '',
            'flex': '',
            'rootWidth': '',
            'rootClass': False,
            'canvasUpdates': 2,
        })


if __name__ == '__main__':
    unittest.main()
