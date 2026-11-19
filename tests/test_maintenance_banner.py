"""页面顶部维护公告：服务端状态、广播命令、前端横幅与模板接线。"""
from __future__ import annotations

import io
import pathlib
import unittest
from unittest import mock

import app

REPO = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = REPO / 'templates'
BANNER_JS = REPO / 'static' / 'js' / 'maintenance-banner.js'
BANNER_CSS = REPO / 'static' / 'css' / 'maintenance-banner.css'


def read_text(path: pathlib.Path) -> str:
    with io.open(path, encoding='utf-8', newline='') as handle:
        return handle.read()


class MaintenanceNoticePayloadTests(unittest.TestCase):
    def test_active_notice_reports_the_remaining_seconds(self):
        payload = app.maintenance_notice_payload(
            {'message': '五分钟后更新', 'started_at': 100.0, 'expires_at': 400.0, 'sequence': 3},
            now=220.0,
        )
        self.assertTrue(payload['active'])
        self.assertEqual(payload['message'], '五分钟后更新')
        self.assertEqual(payload['seconds_remaining'], 180)
        self.assertEqual(payload['sequence'], 3)

    def test_expired_notice_hides_itself(self):
        payload = app.maintenance_notice_payload(
            {'message': '五分钟后更新', 'started_at': 100.0, 'expires_at': 400.0, 'sequence': 3},
            now=400.0,
        )
        self.assertFalse(payload['active'])
        self.assertEqual(payload['message'], '')
        self.assertEqual(payload['seconds_remaining'], 0)

    def test_empty_notice_is_inactive(self):
        payload = app.maintenance_notice_payload({'message': '', 'expires_at': 0.0}, now=10.0)
        self.assertFalse(payload['active'])
        self.assertEqual(payload['seconds_remaining'], 0)


class SetMaintenanceNoticeTests(unittest.TestCase):
    def tearDown(self):
        with app._MAINTENANCE_NOTICE_LOCK:
            app._MAINTENANCE_NOTICE.update(
                {'message': '', 'started_at': 0.0, 'expires_at': 0.0, 'sequence': 0}
            )

    def test_setting_a_notice_emits_the_banner_and_broadcasts_the_text(self):
        with mock.patch.object(app, 'socketio') as fake_socketio, \
                mock.patch.object(app, 'send_system_broadcast', return_value=7) as fake_broadcast, \
                mock.patch.object(app, 'admin_event'):
            result = app.set_maintenance_notice('服务器将在五分钟后更新', 300)

        fake_broadcast.assert_called_once_with('服务器将在五分钟后更新')
        event, payload = fake_socketio.emit.call_args[0]
        self.assertEqual(event, 'maintenance_banner')
        self.assertTrue(payload['active'])
        self.assertEqual(payload['message'], '服务器将在五分钟后更新')
        self.assertEqual(payload['seconds_remaining'], 300)
        self.assertEqual(result['sent'], 7)

    def test_notice_duration_is_clamped_to_one_hour(self):
        with mock.patch.object(app, 'socketio'), \
                mock.patch.object(app, 'send_system_broadcast', return_value=0), \
                mock.patch.object(app, 'admin_event'):
            result = app.set_maintenance_notice('长公告', 99999)
        self.assertEqual(result['notice']['seconds_remaining'], 3600)

    def test_blank_message_is_rejected(self):
        with self.assertRaises(ValueError):
            app.set_maintenance_notice('   ', 300)


    def test_console_command_routes_through_the_structured_tree(self):
        with mock.patch.object(app, 'socketio'), \
                mock.patch.object(app, 'send_system_broadcast', return_value=5), \
                mock.patch.object(app, 'admin_event'):
            result = app.execute_admin_command('maintenance notice 120 服务器将在两分钟后更新')

        self.assertTrue(result['success'], result.get('output'))
        self.assertEqual(result['notice']['seconds_remaining'], 120)
        self.assertEqual(app.current_maintenance_notice()['message'], '服务器将在两分钟后更新')
        self.assertEqual(app.current_maintenance_notice()['active'], True)


class BannerFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = read_text(BANNER_JS)
        cls.css = read_text(BANNER_CSS)

    def test_banner_is_pinned_to_the_bottom_of_the_screen(self):
        self.assertIn('position: fixed;', self.css)
        self.assertIn('bottom: 0;', self.css)
        self.assertNotIn('top: 0;', self.css)
        self.assertIn('border-top: 1px solid', self.css)
        self.assertIn('translateY(100%)', self.css)
        self.assertIn('z-index: 2147482000;', self.css)
        self.assertIn('pointer-events: none;', self.css)

    def test_active_banner_shrinks_the_app_and_lifts_the_bottom_layers(self):
        self.assertIn('html.gtn-maintenance-active #app {', self.css)
        self.assertIn('height: calc(100% - var(--gtn-maintenance-h, 40px));', self.css)
        self.assertIn('html.gtn-maintenance-active #gtn-tips,', self.css)
        self.assertIn('html.gtn-maintenance-active #phase-chat-panel {', self.css)
        self.assertIn('translate: 0 calc(-1 * var(--gtn-maintenance-h, 40px));', self.css)
        self.assertIn('function syncHeight()', self.js)
        self.assertIn("root.style.setProperty('--gtn-maintenance-h'", self.js)

    def test_banner_polls_the_public_endpoint_and_counts_down(self):
        self.assertIn("fetch('/api/maintenance/notice'", self.js)
        self.assertIn('cache: \'no-store\'', self.js)
        self.assertIn('window.setInterval(poll, POLL_INTERVAL_MS);', self.js)
        self.assertIn('function formatClock(', self.js)
        self.assertIn("clockNode.textContent = '剩余 ' + formatClock(remaining);", self.js)
        self.assertIn('window.GtnMaintenanceBanner', self.js)

    def test_both_pages_load_the_banner(self):
        for name in ('index.html', 'story.html'):
            text = read_text(TEMPLATES / name)
            self.assertIn('/static/js/maintenance-banner.js', text, name)
            self.assertIn('/static/css/maintenance-banner.css', text, name)

    def test_lobby_forwards_the_socket_event_to_the_banner(self):
        game_js = read_text(REPO / 'static' / 'js' / 'game.js')
        self.assertIn("bindSocketEvent('maintenance_banner'", game_js)
        self.assertIn('window.GtnMaintenanceBanner.show(data)', game_js)


if __name__ == '__main__':
    unittest.main()
