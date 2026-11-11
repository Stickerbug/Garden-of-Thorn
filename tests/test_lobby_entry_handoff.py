# -*- coding: utf-8 -*-
"""主页自动入厅交接：每次跳转最多点击一次，手动回主页可取消。"""

import json
from pathlib import Path
import shutil
import subprocess
import textwrap
import unittest


GAME_JS = Path(__file__).resolve().parents[1] / 'static' / 'js' / 'game.js'
GAME_SOURCE = GAME_JS.read_text(encoding='utf-8')
START = 'let lobbyEntryHandoffTimer = null;'
END = 'let transientLoginRetryTimer = null;'
HANDOFF_SOURCE = START + GAME_SOURCE.split(START, 1)[1].split(END, 1)[0]
DIRECT_NODE = Path.home() / 'AppData/Local/Programs/Kimi/resources/resources/runtime/node.cmd'
NODE = str(DIRECT_NODE) if DIRECT_NODE.exists() else shutil.which('node')


@unittest.skipIf(NODE is None, '需要 Node.js 运行客户端计时器测试')
class LobbyEntryHandoffTests(unittest.TestCase):
    def run_client_script(self, body):
        harness = textwrap.dedent(
            f'''
            const vm = require('vm');
            const handoffSource = {json.dumps(HANDOFF_SOURCE)};

            function createScenario() {{
                let now = 0;
                let nextTimerId = 1;
                let clicks = 0;
                let loginHidden = false;
                const timers = new Map();
                const loginView = {{
                    classList: {{ contains: (name) => name === 'hidden' && loginHidden }},
                }};
                const connectButton = {{ disabled: false, click: () => {{ clicks += 1; }} }};
                const context = {{
                    Date: {{ now: () => now }},
                    window: {{
                        setTimeout(callback, delay) {{
                            const id = nextTimerId++;
                            timers.set(id, {{ at: now + delay, callback }});
                            return id;
                        }},
                        clearTimeout(id) {{ timers.delete(id); }},
                    }},
                    $(id) {{
                        if (id === 'view-login') return loginView;
                        if (id === 'btn-connect') return connectButton;
                        return null;
                    }},
                }};
                vm.createContext(context);
                vm.runInContext(handoffSource, context, {{ filename: 'lobby-handoff.js' }});

                function advance(milliseconds) {{
                    const target = now + milliseconds;
                    while (true) {{
                        let selectedId = null;
                        let selected = null;
                        for (const [id, timer] of timers) {{
                            if (timer.at > target) continue;
                            if (!selected || timer.at < selected.at ||
                                    (timer.at === selected.at && id < selectedId)) {{
                                selectedId = id;
                                selected = timer;
                            }}
                        }}
                        if (!selected) break;
                        timers.delete(selectedId);
                        now = selected.at;
                        selected.callback();
                    }}
                    now = target;
                }}

                return {{
                    schedule: () => context.scheduleLobbyEntryHandoff(),
                    cancel: () => context.cancelLobbyEntryHandoff(),
                    advance,
                    setLoginHidden: (value) => {{ loginHidden = value; }},
                    get clicks() {{ return clicks; }},
                    get pending() {{ return timers.size; }},
                }};
            }}
            '''
        )
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.cjs', prefix='tmp_lobby_handoff_',
            dir=GAME_JS.parents[2], delete=False, encoding='utf-8',
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
                if not exc.stdout:
                    self.fail(f'Node 测试未返回结果：{exc.stderr or "无错误输出"}')
                output = exc.stdout
        finally:
            script_path.unlink(missing_ok=True)
        return json.loads(output)

    def test_waits_for_login_then_clicks_only_once(self):
        result = self.run_client_script(
            '''
            const scenario = createScenario();
            scenario.setLoginHidden(true);
            scenario.schedule();
            scenario.advance(400);
            const waiting = { clicks: scenario.clicks, pending: scenario.pending };
            scenario.setLoginHidden(false);
            scenario.advance(400);
            const afterClick = { clicks: scenario.clicks, pending: scenario.pending };
            scenario.advance(25000);
            const afterWait = { clicks: scenario.clicks, pending: scenario.pending };
            console.log(JSON.stringify({ waiting, afterClick, afterWait }));
            '''
        )
        self.assertEqual(result['waiting'], {'clicks': 0, 'pending': 1})
        self.assertEqual(result['afterClick'], {'clicks': 1, 'pending': 0})
        self.assertEqual(result['afterWait'], {'clicks': 1, 'pending': 0})

    def test_manual_home_cancels_pending_entry(self):
        result = self.run_client_script(
            '''
            const scenario = createScenario();
            scenario.setLoginHidden(true);
            scenario.schedule();
            scenario.advance(400);
            scenario.cancel();
            const afterCancel = { clicks: scenario.clicks, pending: scenario.pending };
            scenario.setLoginHidden(false);
            scenario.advance(25000);
            const afterWait = { clicks: scenario.clicks, pending: scenario.pending };
            console.log(JSON.stringify({ afterCancel, afterWait }));
            '''
        )
        self.assertEqual(result['afterCancel'], {'clicks': 0, 'pending': 0})
        self.assertEqual(result['afterWait'], {'clicks': 0, 'pending': 0})

    def test_both_entry_params_share_scheduler_and_back_cancels_it(self):
        self.assertIn(
            'if (minigameInviteHandoff || enterLobbyHandoff) {\n'
            '        scheduleLobbyEntryHandoff();\n'
            '    }',
            GAME_SOURCE,
        )
        back_start = GAME_SOURCE.index("$('btn-lobby-back').addEventListener")
        back_end = GAME_SOURCE.index("$('btn-surrender')", back_start)
        back_handler = GAME_SOURCE[back_start:back_end]
        self.assertIn('cancelLobbyEntryHandoff();', back_handler)
        self.assertLess(
            back_handler.index('cancelLobbyEntryHandoff();'),
            back_handler.index("showView('view-login')"),
        )
        self.assertNotIn('lastClickAt', HANDOFF_SOURCE)


if __name__ == '__main__':
    unittest.main()
