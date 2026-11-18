# -*- coding: utf-8 -*-
"""对局邀请：被邀请方点「接受」失败时必须有提示，邀请超时要通知双方。

2026-11-18 事故：邀请方关掉「接受对局邀请」后，被邀请方隔了一会儿才点接受，
邀请早已在 30 秒后自动作废，accept_invite 落到静默 return —— 界面毫无反应。
"""

from __future__ import annotations

from pathlib import Path

import app as gtn
import mod_unlocks

ROOT = Path(__file__).resolve().parents[1]


def _fake_player(user_id, state, *, accept_invites=True, match_mode='casual_1v1'):
    engine_mode, match_type, canonical = gtn.pvp_match_mode_parts(match_mode)
    return {
        'nickname': f'P{user_id}',
        'user_id': user_id,
        'is_registered_user': True,
        'mode': engine_mode,
        'match_type': match_type,
        'match_mode': canonical,
        'mod_unlock_state': state,
        'entertainment_mods': [],
        'community_mods': [],
        'mod_source': 'official',
        'preferred_disabled_mods': [],
        'status': 'lobby',
        'room_id': None,
        'beta_mode': False,
        'accept_game_invites': accept_invites,
    }


def _setup(monkeypatch, *, inviter_accepts=True):
    clients = [gtn.socketio.test_client(gtn.app), gtn.socketio.test_client(gtn.app)]
    room_map = gtn.socketio.server.manager.rooms['/'][None]
    sids = [
        next(key for key, value in room_map.items() if value == client.eio_sid)
        for client in clients
    ]
    states = {
        511: mod_unlocks.compute_state(20, ('Void Card Addition.gtnmod',)),
        512: mod_unlocks.compute_state(20, ('Hel Cards Addition.gtnmod',)),
    }
    monkeypatch.setattr(gtn.mod_unlocks, 'load_state', lambda uid: states[int(uid)])
    gtn.players[sids[0]] = _fake_player(511, states[511], accept_invites=inviter_accepts)
    gtn.players[sids[1]] = _fake_player(512, states[512])
    for client in clients:
        client.get_received()
    return clients, sids


def _teardown(sids, clients):
    for room in list(gtn.rooms.values()):
        if set(room.player_sids) & set(sids):
            gtn.rooms.pop(room.room_id, None)
    for sid in sids:
        gtn.players.pop(sid, None)
        gtn.invites.pop(sid, None)
        gtn.invite_special_modes.pop(sid, None)
    for client in clients:
        client.disconnect()


def _events(client, name):
    return [pkt for pkt in client.get_received() if pkt['name'] == name]


def test_inviter_with_invites_disabled_can_still_have_an_invite_accepted(monkeypatch):
    """邀请方自己关了「接受对局邀请」，不影响他发出去的邀请被接受。"""
    clients, sids = _setup(monkeypatch, inviter_accepts=False)
    gtn.invites[sids[0]] = sids[1]
    try:
        clients[1].emit('accept_invite', {'inviter_sid': sids[0]})
        created = next((room for room in gtn.rooms.values() if set(room.player_sids) == set(sids)), None)
        assert created is not None, '邀请方关掉开关后，被邀请方接受邀请仍然应该能成局'
        assert _events(clients[1], 'game_phase'), '被邀请方应该收到开局事件'
    finally:
        _teardown(sids, clients)


def test_accepting_an_expired_invite_returns_a_visible_error(monkeypatch):
    """邀请已作废时点接受：必须收到 server_error，而不是什么都没有。"""
    clients, sids = _setup(monkeypatch)
    try:
        clients[1].emit('accept_invite', {'inviter_sid': sids[0]})
        errors = _events(clients[1], 'server_error')
        assert errors, '接受已失效的邀请时应该给被邀请方一个提示'
        payload = errors[-1]['args'][0]
        assert payload.get('reason') == 'invite_expired'
        assert '邀请已失效' in str(payload.get('message') or '')
        assert not gtn.rooms, '邀请失效时不应该建局'
    finally:
        _teardown(sids, clients)


def test_invite_timeout_notifies_both_sides(monkeypatch):
    """30 秒自动作废时通知双方，客户端才能关掉那个已经没用的弹窗。"""

    class _ImmediateTimer:
        def __init__(self, interval, fn, args=None, kwargs=None):
            self.daemon = False
            self._fn = fn
            self._args = tuple(args or ())
            self._kwargs = dict(kwargs or {})
            self.interval = interval

        def start(self):
            self._fn(*self._args, **self._kwargs)

        def cancel(self):
            pass

    monkeypatch.setattr(gtn.threading, 'Timer', _ImmediateTimer)
    clients, sids = _setup(monkeypatch)
    try:
        clients[0].get_received()
        clients[1].get_received()
        clients[0].emit('invite', {'target_sid': sids[1]})
        clients[0].emit('invite', {'target_sid': sids[1], 'confirmed': True})
        inviter_notices = _events(clients[0], 'invite_expired')
        invitee_notices = _events(clients[1], 'invite_expired')
        assert invitee_notices, '被邀请方应该被告知邀请已超时'
        assert '超时' in str(invitee_notices[-1]['args'][0].get('message') or '')
        assert inviter_notices, '邀请方也应该被告知邀请已超时'
        assert sids[0] not in gtn.invites
    finally:
        _teardown(sids, clients)


def test_client_closes_the_invite_modal_when_the_invite_expires():
    source = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
    assert "bindSocketEvent('invite_expired'" in source
    assert "if ($('invite-accept')) hideModal();" in source
