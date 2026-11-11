# -*- coding: utf-8 -*-
"""玩家形象皮肤目录、购买库存与装备。

装备值继续使用 users.skin_json；本模块只负责商品目录与拥有记录，
因此大厅、对局、故事模式仍沿用现有皮肤同步链。
"""

import json

import db


PLAYER_SKIN_CATALOG = [
    {'skin_id': 'classic', 'name': '经典', 'price': 0, 'weight': 0, 'texture_url': ''},
    {'skin_id': 'faceless', 'name': '无脸', 'price': 20000, 'weight': 2, 'texture_url': '/static/assets/player-avatars/faceless-body.svg'},
    {'skin_id': 'ghost', 'name': '幽灵', 'price': 20000, 'weight': 2, 'texture_url': '/static/assets/player-avatars/ghost-body.svg'},
    {'skin_id': 'brain_damage', 'name': '脑损伤', 'price': 50000, 'weight': 1, 'texture_url': '/static/assets/player-avatars/brain-damage-body.svg'},
    {'skin_id': 'corrupted', 'name': '腐化', 'price': 10000, 'weight': 0, 'texture_url': '/static/assets/player-avatars/corrupted-body.svg'},
    {'skin_id': 'mark', 'name': '标记', 'price': 20000, 'weight': 2, 'texture_url': '/static/assets/player-avatars/mark-body.svg'},
    {'skin_id': 'nazar', 'name': '邪眼', 'price': 20000, 'weight': 2, 'texture_url': '/static/assets/player-avatars/nazar-body.svg'},
    {'skin_id': 'right_angle', 'name': '直角', 'price': 10000, 'weight': 5, 'texture_url': '/static/assets/player-avatars/right-angle-body.svg'},
    {'skin_id': 'centipede_head', 'name': '蜈蚣头', 'price': 20000, 'weight': 5, 'texture_url': '/static/assets/player-avatars/centipede-head.svg'},
    {'skin_id': 'desert_centipede_head', 'name': '沙漠蜈蚣头', 'price': 20000, 'weight': 5, 'texture_url': '/static/assets/player-avatars/desert-centipede-head.svg'},
    {'skin_id': 'evil_centipede_head', 'name': '邪恶蜈蚣头', 'price': 20000, 'weight': 5, 'texture_url': '/static/assets/player-avatars/evil-centipede-head.svg'},
    # 赛季「塔之诅咒」角色皮肤：不上架商店（price=0, weight=0）。
    {'skin_id': 'tower_curse_ironclad', 'name': '铁甲战士', 'price': 0, 'weight': 0, 'texture_url': '/static/assets/player-avatars/tower-curse-ironclad.svg'},
    {'skin_id': 'tower_curse_silent', 'name': '静默猎手', 'price': 0, 'weight': 0, 'texture_url': '/static/assets/player-avatars/tower-curse-silent.svg'},
    {'skin_id': 'tower_curse_defect', 'name': '故障机器人', 'price': 0, 'weight': 0, 'texture_url': '/static/assets/player-avatars/tower-curse-defect.svg'},
    {'skin_id': 'tower_curse_necrobinder', 'name': '亡灵契约师', 'price': 0, 'weight': 0, 'texture_url': '/static/assets/player-avatars/tower-curse-necrobinder.svg'},
    {'skin_id': 'tower_curse_regent', 'name': '储君', 'price': 0, 'weight': 0, 'texture_url': '/static/assets/player-avatars/tower-curse-regent.svg'},
]
PLAYER_SKIN_BY_ID = {item['skin_id']: item for item in PLAYER_SKIN_CATALOG}
DEFAULT_PLAYER_SKIN = 'classic'
PLAYER_SKIN_OFFER_COUNT = 3
PLAYER_SKIN_REFRESH_BASE_COST = 700
PLAYER_SKIN_REFRESH_COST_STEP = 300


def ensure_player_skin_schema(conn):
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS user_player_skins (
            user_id INTEGER NOT NULL,
            skin_id TEXT NOT NULL,
            acquired_source TEXT NOT NULL DEFAULT 'shop',
            acquired_ref TEXT,
            acquired_at TEXT NOT NULL,
            PRIMARY KEY(user_id, skin_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        '''
    )
    for statement in (
        '''
        CREATE TABLE IF NOT EXISTS player_skin_shop_sets (
            set_id TEXT PRIMARY KEY,
            shop_date TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS player_skin_shop_offers (
            set_id TEXT NOT NULL,
            slot INTEGER NOT NULL,
            skin_id TEXT NOT NULL,
            price INTEGER NOT NULL,
            PRIMARY KEY(set_id, slot)
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS player_skin_shop_purchases (
            user_id INTEGER NOT NULL,
            set_id TEXT NOT NULL,
            slot INTEGER NOT NULL,
            acquired_at TEXT NOT NULL,
            PRIMARY KEY(user_id, set_id, slot)
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS player_skin_shop_user_state (
            user_id INTEGER PRIMARY KEY,
            active_set_id TEXT NOT NULL,
            locked INTEGER NOT NULL DEFAULT 0,
            refresh_date TEXT NOT NULL,
            refresh_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        ''',
    ):
        conn.execute(statement)
    conn.commit()


def list_owned_player_skins(conn, user_id):
    ensure_player_skin_schema(conn)
    rows = conn.execute(
        'SELECT skin_id FROM user_player_skins WHERE user_id = ?',
        (int(user_id),),
    ).fetchall()
    owned = {str(row['skin_id']) for row in rows if str(row['skin_id']) in PLAYER_SKIN_BY_ID}
    owned.add(DEFAULT_PLAYER_SKIN)
    return owned


def get_equipped_player_skin(conn, user_id):
    row = conn.execute(
        'SELECT skin_json FROM users WHERE id = ? AND deleted_at IS NULL',
        (int(user_id),),
    ).fetchone()
    if row is None:
        return DEFAULT_PLAYER_SKIN
    skin = db.normalize_skin_config(row['skin_json'])
    skin_id = str(skin.get('skin_id') or DEFAULT_PLAYER_SKIN)
    return skin_id if skin_id in PLAYER_SKIN_BY_ID else DEFAULT_PLAYER_SKIN


def player_skin_payload(conn, user_id):
    owned = list_owned_player_skins(conn, user_id)
    equipped = get_equipped_player_skin(conn, user_id)
    items = []
    for item in PLAYER_SKIN_CATALOG:
        skin_id = item['skin_id']
        items.append({
            'skin_id': skin_id,
            'name': item['name'],
            'price': int(item['price']),
            'texture_url': item['texture_url'],
            'owned': skin_id in owned,
            'equipped': skin_id == equipped,
        })
    return {'items': items, 'equipped': equipped}


def _create_player_skin_shop_set_conn(conn, shop_date, scope_key, kind):
    import secrets

    rows = [
        {'skin_id': item['skin_id'], 'price': item['price'], 'shop_weight': item['weight']}
        for item in PLAYER_SKIN_CATALOG if int(item['weight']) > 0
    ]
    if len(rows) < PLAYER_SKIN_OFFER_COUNT:
        raise ValueError('可售玩家皮肤不足')
    set_id = f"{kind}:{shop_date}:{secrets.token_hex(8)}"
    now = db.utc_now()
    conn.execute(
        'INSERT INTO player_skin_shop_sets (set_id, shop_date, scope_key, kind, created_at) VALUES (?, ?, ?, ?, ?)',
        (set_id, shop_date, str(scope_key or '')[:80], kind, now),
    )
    for slot, row in enumerate(db._weighted_unique_skin_ids(rows, PLAYER_SKIN_OFFER_COUNT), start=1):
        conn.execute(
            'INSERT INTO player_skin_shop_offers (set_id, slot, skin_id, price) VALUES (?, ?, ?, ?)',
            (set_id, slot, row['skin_id'], max(0, int(row['price']))),
        )
    return set_id


def _player_skin_shop_set_is_saleable_conn(conn, set_id):
    """旧商品组含下架皮肤、重复槽位或旧价格时，不再继续使用。"""
    offers = conn.execute(
        'SELECT slot, skin_id, price FROM player_skin_shop_offers WHERE set_id = ? ORDER BY slot',
        (str(set_id or ''),),
    ).fetchall()
    if len(offers) != PLAYER_SKIN_OFFER_COUNT:
        return False
    seen = set()
    for offer in offers:
        skin_id = str(offer['skin_id'])
        item = PLAYER_SKIN_BY_ID.get(skin_id)
        if item is None or int(item['weight']) <= 0 or skin_id in seen:
            return False
        if int(offer['price'] or 0) != int(item['price']):
            return False
        seen.add(skin_id)
    return True


def _ensure_global_player_skin_set_conn(conn, shop_date):
    rows = conn.execute(
        "SELECT set_id FROM player_skin_shop_sets WHERE shop_date = ? AND scope_key = 'global' AND kind = 'daily' ORDER BY created_at DESC, rowid DESC",
        (shop_date,),
    ).fetchall()
    for row in rows:
        if _player_skin_shop_set_is_saleable_conn(conn, row['set_id']):
            return str(row['set_id'])
    return _create_player_skin_shop_set_conn(conn, shop_date, 'global', 'daily')


def _ensure_player_skin_user_state_conn(conn, user_id, shop_date):
    uid = int(user_id)
    global_set_id = _ensure_global_player_skin_set_conn(conn, shop_date)
    row = conn.execute(
        'SELECT * FROM player_skin_shop_user_state WHERE user_id = ?', (uid,),
    ).fetchone()
    now = db.utc_now()
    if row is None:
        conn.execute(
            "INSERT INTO player_skin_shop_user_state (user_id, active_set_id, locked, refresh_date, refresh_count, updated_at) VALUES (?, ?, 0, ?, 0, ?)",
            (uid, global_set_id, shop_date, now),
        )
        return conn.execute('SELECT * FROM player_skin_shop_user_state WHERE user_id = ?', (uid,)).fetchone()
    active_set_id = str(row['active_set_id'] or '')
    locked = bool(row['locked'])
    refresh_date = str(row['refresh_date'] or '')
    refresh_count = max(0, int(row['refresh_count'] or 0))
    active = conn.execute(
        'SELECT shop_date FROM player_skin_shop_sets WHERE set_id = ?', (active_set_id,),
    ).fetchone() if active_set_id else None
    if refresh_date != shop_date:
        refresh_date = shop_date
        refresh_count = 0
    if active is None or not _player_skin_shop_set_is_saleable_conn(conn, active_set_id):
        active_set_id = global_set_id
    elif not locked and str(active['shop_date'] or '') != shop_date:
        active_set_id = global_set_id
    conn.execute(
        'UPDATE player_skin_shop_user_state SET active_set_id = ?, refresh_date = ?, refresh_count = ?, updated_at = ? WHERE user_id = ?',
        (active_set_id, refresh_date, refresh_count, now, uid),
    )
    return conn.execute('SELECT * FROM player_skin_shop_user_state WHERE user_id = ?', (uid,)).fetchone()


def get_player_skin_shop(user_id):
    """每日/手动商品组：3 个槽位、拥有态、刷新价与倒计时。"""
    uid = int(user_id)
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    with db.get_db_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_player_skin_schema(conn)
        state = _ensure_player_skin_user_state_conn(conn, uid, shop_date)
        active_set_id = str(state['active_set_id'] or '')
        refresh_count = max(0, int(state['refresh_count'] or 0))
        offers = conn.execute(
            'SELECT slot, skin_id, price FROM player_skin_shop_offers WHERE set_id = ? ORDER BY slot',
            (active_set_id,),
        ).fetchall()
        owned = list_owned_player_skins(conn, uid)
        equipped = get_equipped_player_skin(conn, uid)
        conn.commit()
    items = []
    for offer in offers:
        skin_id = str(offer['skin_id'])
        item = PLAYER_SKIN_BY_ID.get(skin_id)
        if item is None or int(item['weight']) <= 0:
            continue
        items.append({
            'slot': int(offer['slot']),
            'skin_id': skin_id,
            'name': item['name'],
            'price': int(offer['price'] or 0),
            'texture_url': item['texture_url'],
            'owned': skin_id in owned,
            'equipped': skin_id == equipped,
        })
    return {
        'set_id': active_set_id,
        'locked': bool(state['locked']),
        'refresh_cost': PLAYER_SKIN_REFRESH_BASE_COST + refresh_count * PLAYER_SKIN_REFRESH_COST_STEP,
        'refresh_count': refresh_count,
        'seconds_to_refresh': db._title_shop_seconds_to_refresh(current),
        'shop_date': shop_date,
        'equipped': equipped,
        'owned_skin_ids': sorted(owned),
        'offers': items,
        'offer_count': PLAYER_SKIN_OFFER_COUNT,
    }, None


def refresh_player_skin_shop(user_id):
    """手动刷新：700+300×当日次数，生成玩家专属三槽商品组。"""
    uid = int(user_id)
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    with db.get_db_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_player_skin_schema(conn)
        state = _ensure_player_skin_user_state_conn(conn, uid, shop_date)
        refresh_count = max(0, int(state['refresh_count'] or 0))
        cost = PLAYER_SKIN_REFRESH_BASE_COST + refresh_count * PLAYER_SKIN_REFRESH_COST_STEP
        user = conn.execute('SELECT * FROM users WHERE id = ? AND deleted_at IS NULL', (uid,)).fetchone()
        if user is None:
            conn.rollback()
            return None, '账号不存在'
        free_before = max(0, int(user['thorn_dew_free'] or 0))
        paid_before = max(0, int(user['thorn_dew_paid'] or 0))
        if free_before + paid_before < cost:
            conn.rollback()
            return None, '荆露不足'
        free_spent = min(free_before, cost)
        paid_spent = cost - free_spent
        free_after = free_before - free_spent
        paid_after = paid_before - paid_spent
        conn.execute(
            'UPDATE users SET thorn_dew_free = ?, thorn_dew_paid = ? WHERE id = ?',
            (free_after, paid_after, uid),
        )
        set_id = _create_player_skin_shop_set_conn(conn, shop_date, f'user:{uid}', 'manual')
        conn.execute(
            'INSERT INTO player_skin_shop_user_state (user_id, active_set_id, locked, refresh_date, refresh_count, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET active_set_id = excluded.active_set_id, locked = excluded.locked, refresh_date = excluded.refresh_date, refresh_count = excluded.refresh_count, updated_at = excluded.updated_at',
            (uid, set_id, int(state['locked'] or 0), shop_date, refresh_count + 1, db.utc_now()),
        )
        conn.execute(
            "INSERT INTO user_currency_transactions (user_id, currency, free_delta, paid_delta, reason, source_type, source_id, balance_free_after, balance_paid_after, admin_username, created_at) VALUES (?, 'thorn_dew', ?, ?, ?, 'player_skin_shop_refresh', ?, ?, ?, '', ?)",
            (uid, -free_spent, -paid_spent, '刷新玩家皮肤商店（第%d次）' % (refresh_count + 1),
             set_id + ':refresh', free_after, paid_after, db.utc_now()),
        )
        conn.commit()
    return get_player_skin_shop(uid)


def purchase_player_skin_offer(user_id, set_id, slot):
    """购买当前商品组槽位：校验商品组、扣款并永久解锁。"""
    try:
        uid = int(user_id)
        offer_slot = int(slot)
    except (TypeError, ValueError):
        return None, '商品不存在或已下架'
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    with db.get_db_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_player_skin_schema(conn)
        state = _ensure_player_skin_user_state_conn(conn, uid, shop_date)
        active_set_id = str(state['active_set_id'] or '')
        if str(set_id or '') != active_set_id:
            conn.rollback()
            return None, '商店内容已刷新，请按当前商品操作'
        offer = conn.execute(
            'SELECT slot, skin_id, price FROM player_skin_shop_offers WHERE set_id = ? AND slot = ?',
            (active_set_id, offer_slot),
        ).fetchone()
        item = PLAYER_SKIN_BY_ID.get(str(offer['skin_id'])) if offer is not None else None
        if offer is None or item is None or int(item['weight']) <= 0:
            conn.rollback()
            return None, '商品不存在或已下架'
        skin_id = str(offer['skin_id'])
        purchased = conn.execute(
            'SELECT 1 FROM player_skin_shop_purchases WHERE user_id = ? AND set_id = ? AND slot = ?',
            (uid, active_set_id, offer_slot),
        ).fetchone()
        if purchased is not None:
            conn.rollback()
            return None, '本轮已购买该商品'
        already_owned = conn.execute(
            'SELECT 1 FROM user_player_skins WHERE user_id = ? AND skin_id = ?',
            (uid, skin_id),
        ).fetchone()
        if already_owned is not None:
            conn.rollback()
            return None, '你已经拥有这个玩家皮肤了！'
        user = conn.execute('SELECT * FROM users WHERE id = ? AND deleted_at IS NULL', (uid,)).fetchone()
        if user is None:
            conn.rollback()
            return None, '账号不存在'
        price = max(0, int(offer['price'] or 0))
        free_before = max(0, int(user['thorn_dew_free'] or 0))
        paid_before = max(0, int(user['thorn_dew_paid'] or 0))
        if free_before + paid_before < price:
            conn.rollback()
            return None, '荆露不足'
        free_spent = min(free_before, price)
        paid_spent = price - free_spent
        free_after = free_before - free_spent
        paid_after = paid_before - paid_spent
        now = db.utc_now()
        conn.execute(
            'UPDATE users SET thorn_dew_free = ?, thorn_dew_paid = ? WHERE id = ?',
            (free_after, paid_after, uid),
        )
        source_id = f'{active_set_id}:{offer_slot}'
        conn.execute(
            "INSERT INTO user_currency_transactions (user_id, currency, free_delta, paid_delta, reason, source_type, source_id, balance_free_after, balance_paid_after, admin_username, created_at) VALUES (?, 'thorn_dew', ?, ?, ?, 'player_skin_purchase', ?, ?, ?, '', ?)",
            (uid, -free_spent, -paid_spent, '购买玩家皮肤：' + item['name'], source_id,
             free_after, paid_after, now),
        )
        conn.execute(
            "INSERT INTO user_player_skins (user_id, skin_id, acquired_source, acquired_ref, acquired_at) VALUES (?, ?, 'shop', ?, ?)",
            (uid, skin_id, source_id, now),
        )
        conn.execute(
            'INSERT INTO player_skin_shop_purchases (user_id, set_id, slot, acquired_at) VALUES (?, ?, ?, ?)',
            (uid, active_set_id, offer_slot, now),
        )
        conn.commit()
    return get_player_skin_shop(uid)


def equip_player_skin(conn, user_id, skin_id):
    """在现有 skin_json 中只切换款式，保留颜色和眼型。"""
    skin_id = str(skin_id or '').strip().lower()
    if skin_id not in PLAYER_SKIN_BY_ID:
        return '未知玩家皮肤'
    owned = list_owned_player_skins(conn, user_id)
    if skin_id not in owned:
        return '尚未拥有该玩家皮肤'
    row = conn.execute(
        'SELECT skin_json FROM users WHERE id = ? AND deleted_at IS NULL',
        (int(user_id),),
    ).fetchone()
    if row is None:
        return '请先登录账号'
    skin = db.normalize_skin_config(row['skin_json'])
    skin['skin_id'] = skin_id
    conn.execute(
        'UPDATE users SET skin_json = ? WHERE id = ?',
        (json.dumps(skin, ensure_ascii=False, separators=(',', ':')), int(user_id)),
    )
    return None
