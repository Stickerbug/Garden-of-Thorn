"""更新前「广播 + 顶部公告 + 等满 5 分钟」的契约测试（2026-11-15 起的发布纪律）。"""
from __future__ import annotations

import importlib.util
import io
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
BROADCAST_SCRIPT = REPO / 'scripts' / 'gtn_broadcast.py'
UPDATE_SCRIPT = REPO / 'scripts' / 'gtn_update.sh'


def load_broadcast_module():
    spec = importlib.util.spec_from_file_location('gtn_broadcast', BROADCAST_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_text(path: pathlib.Path) -> str:
    with io.open(path, encoding='utf-8', newline='') as handle:
        return handle.read()


class BroadcastToolTests(unittest.TestCase):
    def setUp(self):
        self.module = load_broadcast_module()

    def test_default_notice_is_the_agreed_wording(self):
        self.assertEqual(
            self.module.DEFAULT_NOTICE,
            '五分钟后更新，请大家尽快结束对局',
        )
        self.assertEqual(self.module.DEFAULT_WAIT_SECONDS, 300)

    def test_command_line_shows_the_top_banner_and_broadcasts(self):
        self.assertEqual(
            self.module.build_command_line('五分钟后更新，请大家尽快结束对局'),
            'maintenance notice 420 五分钟后更新，请大家尽快结束对局',
        )
        self.assertEqual(
            self.module.build_command_line('演练公告', 90),
            'maintenance notice 90 演练公告',
        )

    def test_old_servers_still_get_a_plain_broadcast(self):
        self.assertEqual(
            self.module.build_fallback_command_line('五分钟后更新，请大家尽快结束对局'),
            'lobby broadcast 五分钟后更新，请大家尽快结束对局',
        )

    def test_session_cookie_round_trips_with_the_flask_serializer(self):
        from flask import Flask
        from flask.sessions import SecureCookieSessionInterface

        cookie = self.module.build_session_cookie(
            'unit-test-secret',
            now=1_700_000_000.0,
            session_id='ops-session-1',
            csrf_token='ops-csrf-1',
        )
        self.assertNotIn('unit-test-secret', cookie)

        app = Flask('cookie-check')
        app.secret_key = 'unit-test-secret'
        serializer = SecureCookieSessionInterface().get_signing_serializer(app)
        payload = serializer.loads(cookie)
        self.assertTrue(payload['admin_console_authenticated'])
        self.assertEqual(payload['admin_console_session_id'], 'ops-session-1')
        self.assertEqual(payload['admin_console_csrf'], 'ops-csrf-1')
        self.assertEqual(payload['admin_console_login_time'], 1_700_000_000.0)
        self.assertEqual(payload['admin_console_last_seen'], 1_700_000_000.0)

    def test_dry_run_does_not_need_a_secret_or_a_server(self):
        out = io.StringIO()
        original = self.module.sys.stdout
        self.module.sys.stdout = out
        try:
            code = self.module.main(['--dry-run', '测试公告'])
        finally:
            self.module.sys.stdout = original
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), 'maintenance notice 420 测试公告')


class UpdateScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read_text(UPDATE_SCRIPT)

    def test_notice_is_sent_before_the_service_is_stopped(self):
        broadcast_at = self.text.index('全服广播')
        stop_at = self.text.index('systemctl stop gtn-release')
        self.assertLess(broadcast_at, stop_at)

    def test_default_wait_is_a_full_five_minutes(self):
        self.assertIn('GTN_NOTICE_WAIT_SECONDS:-300', self.text)
        self.assertIn('sleep "$WAIT"', self.text)
        self.assertIn('五分钟后更新，请大家尽快结束对局', self.text)

    def test_banner_outlives_the_wait_and_the_restart(self):
        self.assertIn('GTN_NOTICE_BANNER_SECONDS:-$((WAIT + 120))', self.text)
        self.assertIn('--seconds "$BANNER_SECONDS"', self.text)

    def test_uses_the_broadcast_tool_from_the_incoming_bundle(self):
        # 线上旧版的广播脚本可能还不支持 --seconds，必须优先用新包里的那份。
        self.assertIn('if [ -f "$STAGE/scripts/gtn_broadcast.py" ]; then', self.text)
        self.assertIn('BROADCAST_SCRIPT=$STAGE/scripts/gtn_broadcast.py', self.text)

    def test_staging_unpacks_with_the_gtn_prefix_and_compiles_first(self):
        self.assertIn('--strip-components=1', self.text)
        self.assertIn('py_compile "$STAGE/app.py"', self.text)
        self.assertIn('mv "$RELEASE/venv" "$STAGE/venv"', self.text)

    def test_release_env_is_edited_line_by_line(self):
        for name in ('GTN_VERSION', 'GTN_GIT_SHA', 'GTN_STATIC_VERSION'):
            self.assertIn(f'sed -i "s/^{name}=.*/{name}=${{SHA}}/"', self.text)
        self.assertNotIn('cat > "$RELEASE_ENV"', self.text)


if __name__ == '__main__':
    unittest.main()
