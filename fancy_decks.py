# -*- coding: utf-8 -*-
"""花样百出：数据库表 + CRUD + 导入导出。"""
import json
import base64
import zlib

SCHEMA = """
CREATE TABLE IF NOT EXISTS fancy_decks (
    user_id INTEGER NOT NULL,
    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 3),
    name TEXT NOT NULL DEFAULT '',
    cards_json TEXT NOT NULL DEFAULT '[]',
    opening_event_id INTEGER,
    active INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, slot)
)
"""

FANCY_DECK_SIZE = 15
FANCY_MAX_SLOTS = 3


def ensure_fancy_schema(conn):
    conn.execute(SCHEMA)


def list_fancy_decks_conn(conn, user_id):
    ensure_fancy_schema(conn)
    rows = conn.execute(
        'SELECT slot, name, cards_json, opening_event_id, active, updated_at '
        'FROM fancy_decks WHERE user_id = ? ORDER BY slot',
        (int(user_id),),
    ).fetchall()
    decks = []
    for row in rows:
        try:
            cards = json.loads(row['cards_json'] or '[]')
        except (TypeError, ValueError):
            cards = []
        decks.append({
            'slot': int(row['slot']),
            'name': str(row['name'] or ''),
            'cards': [str(c) for c in cards if c],
            'opening_event_id': row['opening_event_id'],
            'active': bool(row['active']),
            'updated_at': str(row['updated_at'] or ''),
        })
    return decks


def save_fancy_deck_conn(conn, user_id, slot, name, cards, opening_event_id, active):
    ensure_fancy_schema(conn)
    slot = int(slot)
    if not 1 <= slot <= FANCY_MAX_SLOTS:
        return None, '槽位必须是1-3'
    if len(cards) != FANCY_DECK_SIZE:
        return None, f'卡组必须恰好{FANCY_DECK_SIZE}张'
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    if active:
        conn.execute(
            'UPDATE fancy_decks SET active = 0 WHERE user_id = ?', (int(user_id),)
        )
    conn.execute(
        '''
        INSERT INTO fancy_decks (user_id, slot, name, cards_json, opening_event_id, active, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, slot) DO UPDATE SET
            name = excluded.name,
            cards_json = excluded.cards_json,
            opening_event_id = excluded.opening_event_id,
            active = excluded.active,
            updated_at = excluded.updated_at
        ''',
        (int(user_id), slot, str(name or f'卡组{slot}')[:24],
         json.dumps([str(c) for c in cards]), opening_event_id, 1 if active else 0, now),
    )
    return {'slot': slot, 'saved': True}, None


def delete_fancy_deck_conn(conn, user_id, slot):
    ensure_fancy_schema(conn)
    conn.execute(
        'DELETE FROM fancy_decks WHERE user_id = ? AND slot = ?',
        (int(user_id), int(slot)),
    )


def encode_fancy_deck(name, cards, opening_event_id):
    payload = json.dumps(
        {'n': name, 'c': cards, 'e': opening_event_id},
        ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')
    return 'F' + base64.urlsafe_b64encode(zlib.compress(payload, 9)).decode('ascii')


def decode_fancy_deck(code):
    code = str(code or '').strip()
    if not code.startswith('F'):
        return None, '无效的花样百出卡组代码'
    try:
        payload = zlib.decompress(base64.urlsafe_b64decode(code[1:].encode('ascii')))
        data = json.loads(payload.decode('utf-8'))
    except Exception:
        return None, '卡组代码解析失败'
    cards = [str(c) for c in (data.get('c') or []) if c]
    if len(cards) != FANCY_DECK_SIZE:
        return None, f'卡组必须恰好{FANCY_DECK_SIZE}张'
    return {
        'name': str(data.get('n') or '导入卡组')[:24],
        'cards': cards,
        'opening_event_id': data.get('e'),
    }, None


def get_active_fancy_deck_conn(conn, user_id):
    decks = list_fancy_decks_conn(conn, user_id)
    return next((d for d in decks if d['active']), None)
