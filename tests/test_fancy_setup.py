# -*- coding: utf-8 -*-
from types import SimpleNamespace
from unittest import mock

import app
from cards import CARD_DEFS


class _FancyEngine:
    OPENING_EVENTS = {2: {'id': 2, 'name': 'Mana Conversion', 'desc': ''}}

    def start_event_select_first(self):
        self.phase = 'event_select'
        self.opening_event_options = [[{'id': 2}], [{'id': 2}]]
        self.opening_event_picks = [None, None]
        self.player_draft_started = [False, False]
        self.player_ready = [False, False]
        self.draft_picks = [[], []]
        self.draft_pool = []

    def needs_sub_choice(self, pidx):
        return self.opening_event_picks[pidx] == 2


def test_fancy_match_keeps_event_setup_sub_choice_interactive():
    card_ids = list(CARD_DEFS)[:15]
    room = SimpleNamespace(engine=_FancyEngine(), player_sids=['fancy-a', 'fancy-b'])
    original_players = dict(app.players)
    app.players.clear()
    app.players.update({
        'fancy-a': {'user_id': 101},
        'fancy-b': {'user_id': 202},
    })
    decks = {
        101: {'cards': card_ids, 'opening_event_id': 2},
        202: {'cards': card_ids, 'opening_event_id': 2},
    }
    connection = mock.MagicMock()
    try:
        with mock.patch.object(app, 'get_db_connection', return_value=connection), \
             mock.patch.object(
                 app.fancy_decks,
                 'get_active_fancy_deck_conn',
                 side_effect=lambda conn, uid: decks[uid],
             ), \
             mock.patch.object(app, 'record_room_replay_keyframe'), \
             mock.patch.object(app, 'schedule_pregame_state') as schedule_state, \
             mock.patch.object(app, '_fancy_start_game') as start_game:
            assert app._fancy_start_match(room) is True

        assert room.engine.phase == 'draft'
        assert room.engine.opening_event_picks == [2, 2]
        assert room.engine.draft_picks == [card_ids, card_ids]
        assert room.engine.player_ready == [False, False]
        assert schedule_state.call_count == 2
        start_game.assert_not_called()
    finally:
        app.players.clear()
        app.players.update(original_players)


def test_fancy_setup_submissions_for_all_supported_events_reach_mulligan():
    event_choices = {
        2: {},
        3: {'convert_def_ids': []},
        5: None,
        8: None,
        11: None,
    }
    original_players = dict(app.players)
    original_rooms = dict(app.rooms)
    app.players.clear()
    app.rooms.clear()
    try:
        for room_id, event_id in enumerate(event_choices, start=7100):
            clients = [app.socketio.test_client(app.app) for _ in range(2)]
            sids = []
            for client in clients:
                room_map = app.socketio.server.manager.rooms['/'][None]
                sids.append(next(key for key, value in room_map.items() if value == client.eio_sid))
            room = app.GameRoom(
                room_id,
                sids,
                None,
                mode='1v1',
                match_type='casual',
                match_mode='casual_1v1',
            )
            room.fancy_mode = True
            engine = room.engine
            engine.start_event_select_first()
            event = dict(engine.OPENING_EVENTS[event_id])
            engine.opening_event_options = [[dict(event)], [dict(event)]]
            engine.opening_event_picks = [event_id, event_id]
            engine.opening_event_sub_choices = [None, None]
            engine.player_draft_started = [True, True]
            card_ids = list(CARD_DEFS)[:15]
            engine.draft_picks = [list(card_ids), list(card_ids)]
            engine.player_ready = [False, False]
            engine.phase = 'draft'
            engine._fancy_prebuilt_deck = True
            app.rooms[room_id] = room
            for sid in sids:
                app.players[sid] = {
                    'nickname': sid,
                    'user_id': 1000 + len(app.players),
                    'is_registered_user': True,
                    'status': 'in_game',
                    'room_id': room_id,
                    'mode': '1v1',
                    'beta_mode': False,
                }

            choice = event_choices[event_id]
            if event_id == 5:
                choice = {'add_def_ids': [engine.fated_draw_pool_defs()[0]]}
            elif event_id == 8:
                choice = {'yggdrasil_convert_def_id': card_ids[0]}
            elif event_id == 11:
                choice = {'deck_order_def_ids': engine.opening_event_topdeck_candidates(0)}

            with (
                mock.patch.object(app, 'schedule_pregame_state'),
                mock.patch.object(app, 'schedule_pregame_status_update'),
                mock.patch.object(app, 'schedule_start_game', side_effect=app.start_game),
                mock.patch.object(app, 'record_room_replay_action'),
                mock.patch.object(app, 'record_room_replay_keyframe'),
                mock.patch.object(app, 'emit_room_game_phase'),
                mock.patch.object(app, '_broadcast_game_state_now'),
                mock.patch.object(app, 'emit_initial_pending_interaction'),
                mock.patch.object(app, 'broadcast_lobby'),
            ):
                clients[0].emit('submit_event_sub_choice', {'sub_choice': choice})
                clients[1].emit('submit_event_sub_choice', {'sub_choice': choice})

            assert engine.phase == 'mulligan', f'event {event_id} did not reach mulligan'
            assert engine.player_ready == [True, True]
            assert all(choice is not None for choice in engine.opening_event_sub_choices)
            for client in clients:
                client.disconnect()
            app.rooms.pop(room_id, None)
            for sid in sids:
                app.players.pop(sid, None)
    finally:
        app.players.clear()
        app.players.update(original_players)
        app.rooms.clear()
        app.rooms.update(original_rooms)
