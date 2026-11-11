# -*- coding: utf-8 -*-
"""眼睛款式目录、每日商店、永久库存与装备。"""

import json

import db


BASE_EYE_SHAPES = frozenset({'oval', 'rectangle', 'diamond', 'hexagon'})
EYE_STYLE_CATALOG = (
    {'eye_shape': 'oval', 'name': '椭圆', 'price': 0, 'weight': 0, 'asset_url': ''},
    {'eye_shape': 'rectangle', 'name': '长方形', 'price': 0, 'weight': 0, 'asset_url': ''},
    {'eye_shape': 'diamond', 'name': '菱形', 'price': 0, 'weight': 0, 'asset_url': ''},
    {'eye_shape': 'hexagon', 'name': '六边形', 'price': 0, 'weight': 0, 'asset_url': ''},
    {'eye_shape': 'angry', 'name': '愤怒', 'price': 10000, 'weight': 5, 'asset_url': '/static/assets/eye-styles/angry.svg'},
    {'eye_shape': 'coin', 'name': '金币', 'price': 10000, 'weight': 5, 'asset_url': '/static/assets/eye-styles/coin.svg'},
    {'eye_shape': 'dizzy', 'name': '眩晕', 'price': 10000, 'weight': 5, 'asset_url': '/static/assets/eye-styles/dizzy.svg'},
)
EYE_STYLE_BY_ID = {item['eye_shape']: item for item in EYE_STYLE_CATALOG}
EYE_STYLE_OFFER_COUNT = 3
EYE_STYLE_REFRESH_BASE_COST = 700
EYE_STYLE_REFRESH_COST_STEP = 300


def ensure_eye_style_schema(conn):
    for statement in (
        '''
        CREATE TABLE IF NOT EXISTS user_eye_styles (
            user_id INTEGER NOT NULL,
            eye_shape TEXT NOT NULL,
            acquired_source TEXT NOT NULL DEFAULT 'shop',
            acquired_ref TEXT,
            acquired_at TEXT NOT NULL,
            PRIMARY KEY(user_id, eye_shape),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS eye_shop_sets (
            set_id TEXT PRIMARY KEY,
            shop_date TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS eye_shop_offers (
            set_id TEXT NOT NULL,
            slot INTEGER NOT NULL,
            eye_shape TEXT NOT NULL,
            price INTEGER NOT NULL,
            PRIMARY KEY(set_id, slot)
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS eye_shop_purchases (
            user_id INTEGER NOT NULL,
            set_id TEXT NOT NULL,
            slot INTEGER NOT NULL,
            acquired_at TEXT NOT NULL,
            PRIMARY KEY(user_id, set_id, slot)
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS eye_shop_user_state (
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


def list_owned_eye_shapes(conn, user_id):
    ensure_eye_style_schema(conn)
    rows = conn.execute(
        'SELECT eye_shape FROM user_eye_styles WHERE user_id = ?', (int(user_id),),
    ).fetchall()
    owned = {str(row['eye_shape']) for row in rows if str(row['eye_shape']) in EYE_STYLE_BY_ID}
    return owned | set(BASE_EYE_SHAPES)


def get_equipped_eye_shape(conn, user_id):
    row = conn.execute(
        'SELECT skin_json FROM users WHERE id = ? AND deleted_at IS NULL', (int(user_id),),
    ).fetchone()
    if row is None:
        return 'oval'
    eye_shape = db.normalize_skin_config(row['skin_json'])['eye_shape']
    return eye_shape if eye_shape in EYE_STYLE_BY_ID else 'oval'


def eye_style_payload(conn, user_id):
    owned = list_owned_eye_shapes(conn, user_id)
    equipped = get_equipped_eye_shape(conn, user_id)
    items = []
    for item in EYE_STYLE_CATALOG:
        eye_shape = item['eye_shape']
        items.append({
            'eye_shape': eye_shape,
            'name': item['name'],
            'price': int(item['price']),
            'asset_url': item['asset_url'],
            'owned': eye_shape in owned,
            'equipped': eye_shape == equipped,
        })
    return {'items': items, 'equipped': equipped, 'owned_eye_shapes': sorted(owned)}


def _create_eye_style_shop_set_conn(conn, shop_date, scope_key, kind):
    import secrets

    rows = [
        {'skin_id': item['eye_shape'], 'price': item['price'], 'shop_weight': item['weight']}
        for item in EYE_STYLE_CATALOG if int(item['weight']) > 0
    ]
    if len(rows) < EYE_STYLE_OFFER_COUNT:
        raise ValueError('可售眼睛款式不足')
    set_id = f"eye:{shop_date}:{secrets.token_hex(8)}"
    now = db.utc_now()
    conn.execute(
        'INSERT INTO eye_shop_sets (set_id, shop_date, scope_key, kind, created_at) VALUES (?, ?, ?, ?, ?)',
        (set_id, shop_date, str(scope_key or '')[:80], kind, now),
    )
    for slot, row in enumerate(db._weighted_unique_skin_ids(rows, EYE_STYLE_OFFER_COUNT), start=1):
        conn.execute(
            'INSERT INTO eye_shop_offers (set_id, slot, eye_shape, price) VALUES (?, ?, ?, ?)',
            (set_id, slot, row['skin_id'], max(0, int(row['price']))),
        )
    return set_id


def _ensure_global_eye_style_set_conn(conn, shop_date):
    row = conn.execute(
        "SELECT set_id FROM eye_shop_sets WHERE shop_date = ? AND scope_key = 'global' AND kind = 'daily' ORDER BY created_at ASC LIMIT 1",
        (shop_date,),
    ).fetchone()
    if row is not None:
        count = conn.execute(
            'SELECT COUNT(*) AS count FROM eye_shop_offers WHERE set_id = ?', (row['set_id'],),
        ).fetchone()['count']
        if int(count or 0) == EYE_STYLE_OFFER_COUNT:
            return str(row['set_id'])
    return _create_eye_style_shop_set_conn(conn, shop_date, 'global', 'daily')


def _ensure_eye_style_user_state_conn(conn, user_id, shop_date):
    uid = int(user_id)
    global_set_id = _ensure_global_eye_style_set_conn(conn, shop_date)
    row = conn.execute(
        'SELECT * FROM eye_shop_user_state WHERE user_id = ?', (uid,),
    ).fetchone()
    now = db.utc_now()
    if row is None:
        conn.execute(
            "INSERT INTO eye_shop_user_state (user_id, active_set_id, locked, refresh_date, refresh_count, updated_at) VALUES (?, ?, 0, ?, 0, ?)",
            (uid, global_set_id, shop_date, now),
        )
        return conn.execute('SELECT * FROM eye_shop_user_state WHERE user_id = ?', (uid,)).fetchone()
    active_set_id = str(row['active_set_id'] or '')
    locked = bool(row['locked'])
    refresh_date = str(row['refresh_date'] or '')
    refresh_count = max(0, int(row['refresh_count'] or 0))
    active = conn.execute(
        'SELECT shop_date FROM eye_shop_sets WHERE set_id = ?', (active_set_id,),
    ).fetchone() if active_set_id else None
    if refresh_date != shop_date:
        refresh_date = shop_date
        refresh_count = 0
    if not locked and (active is None or str(active['shop_date'] or '') != shop_date):
        active_set_id = global_set_id
    elif active is None:
        active_set_id = global_set_id
    conn.execute(
        'UPDATE eye_shop_user_state SET active_set_id = ?, refresh_date = ?, refresh_count = ?, updated_at = ? WHERE user_id = ?',
        (active_set_id, refresh_date, refresh_count, now, uid),
    )
    return conn.execute('SELECT * FROM eye_shop_user_state WHERE user_id = ?', (uid,)).fetchone()


def _offer_payload(item, owned, equipped, slot):
    eye_shape = item['eye_shape']
    return {
        'slot': int(slot),
        'eye_shape': eye_shape,
        'name': item['name'],
        'price': int(item['price']),
        'asset_url': item['asset_url'],
        'owned': eye_shape in owned,
        'equipped': eye_shape == equipped,
    }


def get_eye_style_shop(user_id):
    uid = int(user_id)
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    with db.get_db_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_eye_style_schema(conn)
        state = _ensure_eye_style_user_state_conn(conn, uid, shop_date)
        active_set_id = str(state['active_set_id'] or '')
        refresh_count = max(0, int(state['refresh_count'] or 0))
        offers = conn.execute(
            'SELECT slot, eye_shape, price FROM eye_shop_offers WHERE set_id = ? ORDER BY slot',
            (active_set_id,),
        ).fetchall()
        owned = list_owned_eye_shapes(conn, uid)
        equipped = get_equipped_eye_shape(conn, uid)
        conn.commit()
    items = [
        _offer_payload(EYE_STYLE_BY_ID[str(offer['eye_shape'])], owned, equipped, offer['slot'])
        for offer in offers if str(offer['eye_shape']) in EYE_STYLE_BY_ID
    ]
    return {
        'set_id': active_set_id,
        'locked': bool(state['locked']),
        'refresh_cost': EYE_STYLE_REFRESH_BASE_COST + refresh_count * EYE_STYLE_REFRESH_COST_STEP,
        'refresh_count': refresh_count,
        'seconds_to_refresh': db._title_shop_seconds_to_refresh(current),
        'shop_date': shop_date,
        'equipped': equipped,
        'owned_eye_shapes': sorted(owned),
        'offers': items,
        'offer_count': EYE_STYLE_OFFER_COUNT,
    }, None


def _spend_thorn_dew_conn(conn, user_id, cost, reason, source_type, source_id):
    user = conn.execute('SELECT * FROM users WHERE id = ? AND deleted_at IS NULL', (int(user_id),)).fetchone()
    if user is None:
        return '账号不存在'
    cost = max(0, int(cost))
    free_before = max(0, int(user['thorn_dew_free'] or 0))
    paid_before = max(0, int(user['thorn_dew_paid'] or 0))
    if free_before + paid_before < cost:
        return '荆露不足'
    free_spent = min(free_before, cost)
    paid_spent = cost - free_spent
    conn.execute(
        'UPDATE users SET thorn_dew_free = ?, thorn_dew_paid = ? WHERE id = ?',
        (free_before - free_spent, paid_before - paid_spent, int(user_id)),
    )
    conn.execute(
        "INSERT INTO user_currency_transactions (user_id, currency, free_delta, paid_delta, reason, source_type, source_id, balance_free_after, balance_paid_after, admin_username, created_at) VALUES (?, 'thorn_dew', ?, ?, ?, ?, ?, ?, ?, '', ?)",
        (int(user_id), -free_spent, -paid_spent, reason, source_type, source_id,
         free_before - free_spent, paid_before - paid_spent, db.utc_now()),
    )
    return None


def refresh_eye_style_shop(user_id):
    uid = int(user_id)
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    with db.get_db_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_eye_style_schema(conn)
        state = _ensure_eye_style_user_state_conn(conn, uid, shop_date)
        refresh_count = max(0, int(state['refresh_count'] or 0))
        cost = EYE_STYLE_REFRESH_BASE_COST + refresh_count * EYE_STYLE_REFRESH_COST_STEP
        error = _spend_thorn_dew_conn(
            conn, uid, cost, f'刷新眼睛商店（第{refresh_count + 1}次）',
            'eye_shop_refresh', f'{state["active_set_id"]}:refresh',
        )
        if error:
            conn.rollback()
            return None, error
        set_id = _create_eye_style_shop_set_conn(conn, shop_date, f'user:{uid}', 'manual')
        conn.execute(
            'INSERT INTO eye_shop_user_state (user_id, active_set_id, locked, refresh_date, refresh_count, updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET active_set_id = excluded.active_set_id, locked = excluded.locked, refresh_date = excluded.refresh_date, refresh_count = excluded.refresh_count, updated_at = excluded.updated_at',
            (uid, set_id, int(state['locked'] or 0), shop_date, refresh_count + 1, db.utc_now()),
        )
        conn.commit()
    return get_eye_style_shop(uid)


def purchase_eye_style_offer(user_id, set_id, slot):
    try:
        uid = int(user_id)
        offer_slot = int(slot)
    except (TypeError, ValueError):
        return None, '商品不存在或已下架'
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    with db.get_db_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        ensure_eye_style_schema(conn)
        state = _ensure_eye_style_user_state_conn(conn, uid, shop_date)
        active_set_id = str(state['active_set_id'] or '')
        if str(set_id or '') != active_set_id:
            conn.rollback()
            return None, '商店内容已刷新，请按当前商品操作'
        offer = conn.execute(
            'SELECT slot, eye_shape, price FROM eye_shop_offers WHERE set_id = ? AND slot = ?',
            (active_set_id, offer_slot),
        ).fetchone()
        if offer is None or str(offer['eye_shape']) not in EYE_STYLE_BY_ID:
            conn.rollback()
            return None, '商品不存在或已下架'
        item = EYE_STYLE_BY_ID[str(offer['eye_shape'])]
        eye_shape = str(offer['eye_shape'])
        purchased = conn.execute(
            'SELECT 1 FROM eye_shop_purchases WHERE user_id = ? AND set_id = ? AND slot = ?',
            (uid, active_set_id, offer_slot),
        ).fetchone()
        if purchased is not None:
            conn.rollback()
            return None, '本轮已购买该商品'
        already_owned = conn.execute(
            'SELECT 1 FROM user_eye_styles WHERE user_id = ? AND eye_shape = ?',
            (uid, eye_shape),
        ).fetchone()
        if already_owned is not None:
            conn.rollback()
            return None, '你已经拥有这款眼睛了！'
        price = max(0, int(offer['price'] or 0))
        error = _spend_thorn_dew_conn(
            conn, uid, price, '购买眼睛：' + item['name'], 'eye_style_purchase',
            f'{active_set_id}:{offer_slot}',
        )
        if error:
            conn.rollback()
            return None, error
        now = db.utc_now()
        conn.execute(
            "INSERT INTO user_eye_styles (user_id, eye_shape, acquired_source, acquired_ref, acquired_at) VALUES (?, ?, 'shop', ?, ?)",
            (uid, eye_shape, f'{active_set_id}:{offer_slot}', now),
        )
        conn.execute(
            'INSERT INTO eye_shop_purchases (user_id, set_id, slot, acquired_at) VALUES (?, ?, ?, ?)',
            (uid, active_set_id, offer_slot, now),
        )
        conn.commit()
    return get_eye_style_shop(uid)


def equip_eye_style(conn, user_id, eye_shape):
    eye_shape = str(eye_shape or '').strip().lower()
    if eye_shape not in EYE_STYLE_BY_ID:
        return '未知眼睛款式'
    if eye_shape not in list_owned_eye_shapes(conn, user_id):
        return '尚未拥有这款眼睛'
    row = conn.execute(
        'SELECT skin_json FROM users WHERE id = ? AND deleted_at IS NULL', (int(user_id),),
    ).fetchone()
    if row is None:
        return '请先登录账号'
    skin = db.normalize_skin_config(row['skin_json'])
    skin['eye_shape'] = eye_shape
    conn.execute(
        'UPDATE users SET skin_json = ? WHERE id = ?',
        (json.dumps(skin, ensure_ascii=False, separators=(',', ':')), int(user_id)),
    )
    return None
