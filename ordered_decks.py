# -*- coding: utf-8 -*-
"""乱中有序：40 张自组卡组的存储、校验与导入导出。"""
import base64
import json
import zlib

SCHEMA = """
CREATE TABLE IF NOT EXISTS ordered_decks (
    user_id INTEGER NOT NULL,
    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 3),
    name TEXT NOT NULL DEFAULT '',
    cards_json TEXT NOT NULL DEFAULT '[]',
    active INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, slot)
)
"""

ORDERED_DECK_SIZE = 40
ORDERED_MAX_SLOTS = 3
ORDERED_MAX_EQUIPMENT = 5
ORDERED_MAX_COPIES = 3
ORDERED_UNLIMITED_CARD_IDS = frozenset({'Sewage'})


def ensure_ordered_schema(conn):
    conn.execute(SCHEMA)


def validate_ordered_cards(cards):
    from cards import CARD_DEFS
    values = [str(card_id) for card_id in (cards or []) if str(card_id)]
    if len(values) != ORDERED_DECK_SIZE:
        return f'卡组必须恰好{ORDERED_DECK_SIZE}张'
    unknown = [card_id for card_id in values if card_id not in CARD_DEFS]
    if unknown:
        return f'卡组包含未知卡牌: {unknown[:3]}'
    zero_weight = [
        card_id for card_id in values
        if int(getattr(CARD_DEFS[card_id], 'count', 0) or 0) <= 0
    ]
    if zero_weight:
        return f'卡组包含权重为0的卡牌: {sorted(set(zero_weight))[:3]}'
    equipment = sum(
        1 for card_id in values
        if str(getattr(CARD_DEFS[card_id], 'card_type', '') or '') == 'root'
    )
    if equipment > ORDERED_MAX_EQUIPMENT:
        return f'装备牌最多{ORDERED_MAX_EQUIPMENT}张（当前{equipment}张）'
    counts = {}
    for card_id in values:
        counts[card_id] = counts.get(card_id, 0) + 1
    over_limit = [
        card_id for card_id, count in counts.items()
        if card_id not in ORDERED_UNLIMITED_CARD_IDS and count > ORDERED_MAX_COPIES
    ]
    if over_limit:
        examples = '、'.join(sorted(over_limit)[:3])
        return f'除污水外，每种卡最多{ORDERED_MAX_COPIES}张（超限：{examples}）'
    return ''


def list_ordered_decks_conn(conn, user_id):
    ensure_ordered_schema(conn)
    rows = conn.execute(
        'SELECT slot, name, cards_json, active, updated_at '
        'FROM ordered_decks WHERE user_id = ? ORDER BY slot',
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
            'cards': [str(card_id) for card_id in cards if card_id],
            'opening_event_id': None,
            'active': bool(row['active']),
            'updated_at': str(row['updated_at'] or ''),
        })
    return decks


def save_ordered_deck_conn(conn, user_id, slot, name, cards, active):
    ensure_ordered_schema(conn)
    slot = int(slot)
    if not 1 <= slot <= ORDERED_MAX_SLOTS:
        return None, '槽位必须是1-3'
    error = validate_ordered_cards(cards)
    if error:
        return None, error
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    if active:
        conn.execute('UPDATE ordered_decks SET active = 0 WHERE user_id = ?', (int(user_id),))
    conn.execute(
        '''
        INSERT INTO ordered_decks (user_id, slot, name, cards_json, active, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, slot) DO UPDATE SET
            name = excluded.name,
            cards_json = excluded.cards_json,
            active = excluded.active,
            updated_at = excluded.updated_at
        ''',
        (
            int(user_id), slot, str(name or f'卡组{slot}')[:24],
            json.dumps([str(card_id) for card_id in cards]), 1 if active else 0, now,
        ),
    )
    return {'slot': slot, 'saved': True}, None


def delete_ordered_deck_conn(conn, user_id, slot):
    ensure_ordered_schema(conn)
    conn.execute('DELETE FROM ordered_decks WHERE user_id = ? AND slot = ?', (int(user_id), int(slot)))


def clear_ordered_decks_conn(conn):
    """仅清空乱中有序卡组；其他模式的卡组表不受影响。"""
    ensure_ordered_schema(conn)
    return int(conn.execute('DELETE FROM ordered_decks').rowcount)


def get_active_ordered_deck_conn(conn, user_id):
    decks = list_ordered_decks_conn(conn, user_id)
    return next((deck for deck in decks if deck['active']), None)


def encode_ordered_deck(name, cards):
    payload = json.dumps(
        {'n': name, 'c': cards}, ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')
    return 'O' + base64.urlsafe_b64encode(zlib.compress(payload, 9)).decode('ascii')


def decode_ordered_deck(code):
    code = str(code or '').strip()
    if not code.startswith('O'):
        return None, '无效的乱中有序卡组代码'
    try:
        payload = zlib.decompress(base64.urlsafe_b64decode(code[1:].encode('ascii')))
        data = json.loads(payload.decode('utf-8'))
    except Exception:
        return None, '卡组代码解析失败'
    cards = [str(card_id) for card_id in (data.get('c') or []) if card_id]
    error = validate_ordered_cards(cards)
    if error:
        return None, error
    return {
        'name': str(data.get('n') or '导入卡组')[:24],
        'cards': cards,
        'opening_event_id': None,
    }, None
