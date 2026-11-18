# -*- coding: utf-8 -*-
"""开局调度（mulligan）倒计时：有人断线时要暂停，不能继续倒数。"""
from __future__ import annotations

import types
import unittest
from pathlib import Path

import app as gtn

ROOT = Path(__file__).resolve().parent.parent


def _room(disconnected=None, deadline=1000.0):
    return types.SimpleNamespace(
        mode='1v1',
        player_sids=['sid-a', 'sid-b'],
        disconnected_players=dict(disconnected or {}),
        _mulligan_deadline=deadline,
    )


class MulliganDisconnectPauseTests(unittest.TestCase):
    def test_deadline_is_stretched_while_an_opponent_is_disconnected(self):
        room = _room({'sid-b': {'since': 0}})
        self.assertFalse(gtn._mulligan_force_due_locked(room, 1100.0))
        self.assertEqual(room._mulligan_deadline, 1000.0)  # 第一次只记录暂停起点
        self.assertFalse(gtn._mulligan_force_due_locked(room, 1140.0))
        self.assertAlmostEqual(room._mulligan_deadline, 1040.0, delta=0.001)
        self.assertFalse(gtn._mulligan_force_due_locked(room, 1180.0))
        self.assertAlmostEqual(room._mulligan_deadline, 1080.0, delta=0.001)

    def test_deadline_resumes_after_reconnect(self):
        room = _room({'sid-b': {'since': 0}})
        gtn._mulligan_force_due_locked(room, 1100.0)
        gtn._mulligan_force_due_locked(room, 1140.0)
        room.disconnected_players = {}
        self.assertTrue(gtn._mulligan_force_due_locked(room, 1200.0))
        self.assertFalse(hasattr(room, '_mulligan_pause_last_tick'))

    def test_deadline_still_fires_when_nobody_is_disconnected(self):
        room = _room()
        self.assertFalse(gtn._mulligan_force_due_locked(room, 900.0))
        self.assertTrue(gtn._mulligan_force_due_locked(room, 1000.0))
        self.assertIsNone(getattr(room, '_mulligan_pause_last_tick', None))

    def test_watchdog_uses_the_pause_aware_check(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn('if _mulligan_force_due_locked(room, now):', source)
        self.assertIn('def _pause_mulligan_deadline_locked(', source)
        self.assertIn('def _clear_mulligan_deadline_pause(', source)

    def test_client_freezes_its_own_countdown_on_disconnect(self):
        source = (ROOT / 'static' / 'js' / 'game.js').read_text(encoding='utf-8')
        self.assertIn('pauseMulliganCountdownForDisconnect();', source)
        self.assertIn('resumeMulliganCountdownAfterReconnect();', source)
        self.assertIn('const reference = mulliganPausedAt || Date.now();', source)
        self.assertIn('if (mulliganCountdown <= 0 && !mulliganPausedAt)', source)
        self.assertIn('mulliganAutoDeadline += Math.max(0, Date.now() - mulliganPausedAt);', source)


if __name__ == '__main__':
    unittest.main()
