# -*- coding: utf-8 -*-
"""天梯开放窗口、大厅降级与对局不受影响。"""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import app
import ranked_availability
import rank_system


UTC = timezone.utc


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=UTC)


class RankedAvailabilityTests(unittest.TestCase):
    def test_weekday_boundaries(self):
        self.assertFalse(ranked_availability.ranked_is_open(at(2, 11, 59)))  # 周一 19:59
        self.assertTrue(ranked_availability.ranked_is_open(at(2, 12)))       # 周一 20:00
        self.assertTrue(ranked_availability.ranked_is_open(at(2, 13, 59)))   # 周一 21:59
        self.assertFalse(ranked_availability.ranked_is_open(at(2, 14)))      # 周一 22:00
        status = ranked_availability.ranked_status(at(2, 12, 30))
        self.assertTrue(status['open'])
        self.assertEqual(status['seconds_to_close'], 5400)

    def test_weekend_boundaries_and_next_open(self):
        self.assertTrue(ranked_availability.ranked_is_open(at(7, 0)))        # 周六 08:00
        self.assertFalse(ranked_availability.ranked_is_open(at(7, 4)))       # 周六 12:00
        self.assertTrue(ranked_availability.ranked_is_open(at(7, 6)))        # 周六 14:00
        self.assertFalse(ranked_availability.ranked_is_open(at(7, 12)))      # 周六 20:00
        closed = ranked_availability.ranked_status(at(7, 5))
        self.assertFalse(closed['open'])
        self.assertEqual(closed['seconds_to_open'], 3600)
        self.assertEqual(closed['next_change_at'], '2026-11-07T06:00:00Z')
        weekend_closed = ranked_availability.ranked_status(at(8, 12))        # 周日 20:00
        self.assertEqual(weekend_closed['next_change_at'], '2026-11-09T12:00:00Z')

    def test_rank_score_bases_and_caps(self):
        self.assertEqual(rank_system.WIN_BASE, 10)
        self.assertEqual(rank_system.MAX_WIN, 20)
        self.assertEqual(rank_system.LOSS_BASE, 6)
        self.assertEqual(rank_system.MAX_LOSS, 10)
        self.assertEqual(rank_system.match_gain(10, 10), 10)
        self.assertEqual(rank_system.match_gain(1, 44), 20)
        self.assertEqual(rank_system.match_loss(10, 10), 6)
        self.assertEqual(rank_system.match_loss(44, 1), 10)

    def test_eligibility_rejects_new_entry_when_closed(self):
        participant = {
            'is_registered_user': True, 'user_id': 1,
            'mod_source': 'official', 'entertainment_mods': [],
        }
        with mock.patch.object(app.ranked_availability, 'ranked_is_open', return_value=False):
            eligible, reason = app.ranked_match_eligibility([participant], check_reputation=False)
        self.assertFalse(eligible)
        self.assertEqual(reason, 'ranked_closed')
        with mock.patch.object(app.ranked_availability, 'ranked_is_open', return_value=True):
            eligible, reason = app.ranked_match_eligibility([participant], check_reputation=False)
        self.assertTrue(eligible)
        self.assertEqual(reason, '')

    def test_finished_ranked_room_remains_valid_when_closed(self):
        room = SimpleNamespace(
            ai_match=False,
            engine=SimpleNamespace(game_over=True),
            player_sids=['ranked-player'],
            _ended_by_surrender=True,
        )
        with (
            mock.patch.object(app.ranked_availability, 'ranked_is_open', return_value=False),
            mock.patch.object(app, 'room_match_type', return_value='ranked'),
            mock.patch.object(app, 'room_player_profile', return_value={
                'is_registered_user': True, 'user_id': 1,
                'mod_source': 'official', 'entertainment_mods': [],
            }),
        ):
            self.assertEqual(app.is_room_valid_for_ranking(room), (True, ''))

    def test_lobby_players_switch_to_casual_but_game_players_stay(self):
        original_players = dict(app.players)
        app.players.clear()
        app.players.update({
            'lobby-ranked': {
                'status': 'lobby', 'match_type': 'ranked', 'match_mode': 'ranked_2v2',
                'mode': '2v2', 'preferred_disabled_mods': [],
            },
            'game-ranked': {
                'status': 'in_game', 'match_type': 'ranked', 'match_mode': 'ranked_1v1',
                'mode': '1v1',
            },
            'lobby-casual': {
                'status': 'lobby', 'match_type': 'casual', 'match_mode': 'casual_1v1',
                'mode': '1v1',
            },
        })
        try:
            with (
                mock.patch.object(app.ranked_availability, 'ranked_status', return_value={
                    'open': False, 'seconds_to_open': 3600, 'seconds_to_close': 0,
                    'next_change_at': '2026-11-09T12:00:00Z',
                }),
                mock.patch.object(app, 'apply_casual_mode_loadout_to_player'),
                mock.patch.object(app.socketio, 'emit'),
            ):
                app.enforce_ranked_availability_locked()
            self.assertEqual(app.players['lobby-ranked']['match_type'], 'casual')
            self.assertEqual(app.players['lobby-ranked']['match_mode'], 'casual_2v2')
            self.assertEqual(app.players['game-ranked']['match_type'], 'ranked')
            self.assertEqual(app.players['game-ranked']['match_mode'], 'ranked_1v1')
            self.assertEqual(app.players['lobby-casual']['match_mode'], 'casual_1v1')
        finally:
            app.players.clear()
            app.players.update(original_players)

    def test_rematch_checks_availability_before_starting_new_game(self):
        clients = [app.socketio.test_client(app.app), app.socketio.test_client(app.app)]
        room_id = 97226
        try:
            sids = []
            for index, client in enumerate(clients):
                client.emit('login', {'nickname': f'RematchWindow{index}', 'mode': '1v1'})
                login = next(event['args'][0] for event in client.get_received() if event['name'] == 'login_ok')
                sids.append(login['sid'])
            with app._lock:
                room = app.GameRoom(room_id, sids, {'Basic', 'Rose'}, mode='1v1', match_mode='ranked_1v1')
                room.engine.player_names = ['RematchWindow0', 'RematchWindow1']
                room.engine.phase = 'game_over'
                room.engine.game_over = True
                app.capture_room_match_loadout(room, app.players[sids[0]])
                for sid in sids:
                    app.players[sid]['room_id'] = room_id
                    app.players[sid]['status'] = 'in_game'
                app.rooms[room_id] = room
            with (
                mock.patch.object(app.ranked_availability, 'ranked_is_open', return_value=False),
                mock.patch.object(app, 'send_pregame_state'),
                mock.patch.object(app, 'record_room_replay_keyframe'),
            ):
                clients[0].emit('rematch', {})
            errors = [event['args'][0] for event in clients[0].get_received() if event['name'] == 'server_error']
            self.assertTrue(errors)
            self.assertEqual(errors[-1]['reason'], 'ranked_closed')
            self.assertEqual(room._rematch_votes, set())
            self.assertEqual(room.match_seq, 1)
            self.assertEqual(room.engine.phase, 'game_over')
            with (
                mock.patch.object(app.ranked_availability, 'ranked_is_open', return_value=True),
                mock.patch.object(app, 'runtime_card_pool_issue', return_value=''),
                mock.patch.object(app, 'send_pregame_state'),
                mock.patch.object(app, 'record_room_replay_keyframe'),
            ):
                clients[0].emit('rematch', {})
                clients[1].emit('rematch', {})
            self.assertEqual(room.match_seq, 2)
        finally:
            with app._lock:
                app.rooms.pop(room_id, None)
                for player in app.players.values():
                    if player.get('room_id') == room_id:
                        player['room_id'] = None
                        player['status'] = 'lobby'
            for client in clients:
                if client.is_connected():
                    client.disconnect()

    def test_frontend_has_disabled_tabs_countdown_and_cache_marker(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / 'static/js/game.js').read_text(encoding='utf-8')
        self.assertIn('renderRankedAvailability(data.ranked_availability)', script)
        self.assertIn("newMode.startsWith('ranked_')", script)
        self.assertIn('距关闭', script)
        self.assertIn('距下次开放', script)
        template = (root / 'templates/index.html').read_text(encoding='utf-8')
        self.assertIn('id="ranked-availability"', template)
        self.assertIn('ranked-schedule-1', (root / 'static_version.txt').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
