# -*- coding: utf-8 -*-
"""反馈 #371：休闲门票会话暂停/恢复——离开再回来不丢剩余时间、不重复扣票。"""

import os
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import leisure_ticket  # noqa: E402

try:
    from test_leisure_ticket import _TempDbCase  # 复用临时库基类
except ImportError:
    from tests.test_leisure_ticket import _TempDbCase  # noqa: F401


class SessionResumeTests(_TempDbCase):
    def test_paused_session_resumes_without_new_ticket(self):
        import db as db_module
        with db_module.get_db_connection() as conn:
            leisure_ticket.grant_tickets(conn, self.user['id'], 2)
        first = leisure_ticket.start_play_session(self.user['id'])
        self.assertTrue(first['active'])
        # 玩 2 分钟后离开（暂停）
        import db as dbm
        with dbm.get_db_connection() as conn:
            conn.execute(
                'UPDATE leisure_play_sessions SET elapsed_seconds = 120 WHERE user_id = ?',
                (self.user['id'],),
            )
        leisure_ticket.pause_play_session(self.user['id'])
        # 回来再进：恢复而不是再扣一张票
        second = leisure_ticket.start_play_session(self.user['id'])
        self.assertTrue(second['active'])
        self.assertLessEqual(second['elapsed'], 125)   # 保留已玩时间（含暂停结算的秒级误差）
        self.assertGreater(second['remaining'], 8 * 60 - 10)
        with dbm.get_db_connection() as conn:
            self.assertEqual(leisure_ticket.get_ticket_balance(conn, self.user['id']), 1)

    def test_resume_only_never_consumes_ticket(self):
        import db as dbm
        with dbm.get_db_connection() as conn:
            leisure_ticket.grant_tickets(conn, self.user['id'], 1)
        # 没有任何会话：resume_only 返回 None，不扣票
        result = leisure_ticket.start_play_session(self.user['id'], resume_only=True)
        self.assertIsNone(result)
        with dbm.get_db_connection() as conn:
            self.assertEqual(leisure_ticket.get_ticket_balance(conn, self.user['id']), 1)

    def test_finished_session_not_resumable(self):
        import db as dbm
        with dbm.get_db_connection() as conn:
            leisure_ticket.grant_tickets(conn, self.user['id'], 1)
        leisure_ticket.start_play_session(self.user['id'])
        info = leisure_ticket.finish_play_session(self.user['id'])
        self.assertFalse(info['active'])
        self.assertEqual(info['remaining'], 0)
        # 结束的会话恢复分支不应续时间
        result = leisure_ticket.start_play_session(self.user['id'], resume_only=True)
        self.assertIsNone(result)
        # 正常进入需要新票
        with self.assertRaises(leisure_ticket.TicketError):
            leisure_ticket.start_play_session(self.user['id'])

    def test_resuming_an_active_session_keeps_its_remaining_time(self):
        """2026-11-16 事故：更新/断线重连时 minigame_presence 会触发 resume。

        活动中的会话 elapsed_seconds 还停在 0（只有暂停才写），旧实现直接把
        started_at 改成 now，剩余时间就被重置回整 10 分钟。
        """
        import db as dbm
        with dbm.get_db_connection() as conn:
            leisure_ticket.grant_tickets(conn, self.user['id'], 1)
        leisure_ticket.start_play_session(self.user['id'])
        started = (dbm.utc_now_dt() - timedelta(seconds=240)).isoformat().replace('+00:00', 'Z')
        with dbm.get_db_connection() as conn:
            conn.execute(
                'UPDATE leisure_play_sessions SET started_at = ?, elapsed_seconds = 0'
                ' WHERE user_id = ?',
                (started, self.user['id']),
            )
        info = leisure_ticket.resume_play_session(self.user['id'])
        self.assertTrue(info['resumed'])
        self.assertAlmostEqual(info['elapsed'], 240, delta=5)
        self.assertAlmostEqual(info['remaining'], 360, delta=5)
        self.assertLess(info['remaining'], leisure_ticket.PLAY_SESSION_SECONDS - 60)
        with dbm.get_db_connection() as conn:
            remaining = leisure_ticket.session_remaining_seconds(conn, self.user['id'])
        self.assertAlmostEqual(remaining, 360, delta=5)

    def test_resuming_an_elapsed_active_session_finishes_it(self):
        import db as dbm
        with dbm.get_db_connection() as conn:
            leisure_ticket.grant_tickets(conn, self.user['id'], 1)
        leisure_ticket.start_play_session(self.user['id'])
        started = (dbm.utc_now_dt() - timedelta(seconds=601)).isoformat().replace('+00:00', 'Z')
        with dbm.get_db_connection() as conn:
            conn.execute(
                'UPDATE leisure_play_sessions SET started_at = ?, elapsed_seconds = 0'
                ' WHERE user_id = ?',
                (started, self.user['id']),
            )
        info = leisure_ticket.resume_play_session(self.user['id'])
        self.assertFalse(info['active'])
        self.assertEqual(info['remaining'], 0)

    def test_resume_does_not_touch_a_paused_session(self):
        import db as dbm
        with dbm.get_db_connection() as conn:
            leisure_ticket.grant_tickets(conn, self.user['id'], 1)
        leisure_ticket.start_play_session(self.user['id'])
        leisure_ticket.pause_play_session(self.user['id'])
        self.assertIsNone(leisure_ticket.resume_play_session(self.user['id']))


if __name__ == '__main__':
    unittest.main()
