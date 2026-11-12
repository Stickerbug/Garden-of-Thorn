# -*- coding: utf-8 -*-
"""主题／战斗背景目录、每日商店、永久解锁与账号装备偏好。"""

import secrets

import db


BACKGROUND_KINDS = ('theme', 'battle')
DEFAULT_BACKGROUNDS = {'theme': 'classic', 'battle': 'classic'}
BACKGROUND_OFFER_COUNT = 3
BACKGROUND_REFRESH_BASE_COST = 700
BACKGROUND_REFRESH_COST_STEP = 300
BACKGROUND_BIOMES = (
    ('garden', '花园', '花园战场', '花园底色、随机草地色块、岩石与向日葵。'),
    ('desert', '沙漠', '沙漠战场', '暖色沙丘、石块与沙漠纹理。'),
    ('ocean', '海洋', '海洋战场', '海洋蓝、气泡与睡莲组成的水面战场。'),
    ('jungle', '丛林', '丛林战场', '丛林绿、枝叶与湿润林地纹理。'),
    ('factory', '工厂', '工厂战场', '工厂灰、金属板与齿轮组成的机械战场。'),
)
BACKGROUND_CATALOG = (
    {'kind': 'theme', 'background_id': 'classic', 'name': '经典主题', 'price': 0, 'weight': 0, 'asset_url': '', 'biome': '', 'description': '保持游戏原有的界面背景。'},
    *[
        {
            'kind': 'theme', 'background_id': biome, 'name': name, 'price': 10000, 'weight': 5,
            'asset_url': '', 'biome': biome, 'description': description,
        }
        for biome, name, _battle_name, description in BACKGROUND_BIOMES
    ],
    {'kind': 'battle', 'background_id': 'classic', 'name': '经典战场', 'price': 0, 'weight': 0, 'asset_url': '', 'biome': '', 'description': '保持游戏原有的对战与观战背景。'},
    *[
        {
            'kind': 'battle', 'background_id': biome, 'name': battle_name, 'price': 10000, 'weight': 5,
            'asset_url': '', 'biome': biome, 'description': description,
        }
        for biome, _name, battle_name, description in BACKGROUND_BIOMES
    ],
    # 赛季「塔之诅咒」主题背景：不上架商店（price=0, weight=0），
    # 由赛季/活动系统单独发放。
    {
        'kind': 'theme', 'background_id': 'tower_curse_deepwood', 'name': '密林',
        'price': 0, 'weight': 0,
        'asset_url': '/static/assets/backgrounds/theme-tower-curse-deepwood.svg',
        'biome': '', 'description': '塔之诅咒赛季主题背景：密林。',
    },
    {
        # 2026-11-12 按用户要求从主题背景改为战斗背景（对局/观战背景）。
        'kind': 'battle', 'background_id': 'tower_curse_dark_harbor', 'name': '暗港',
        'price': 0, 'weight': 0,
        'asset_url': '/static/assets/backgrounds/theme-tower-curse-dark-harbor.svg',
        'biome': '', 'description': '塔之诅咒赛季战斗背景：暗港。',
    },
)
BACKGROUND_BY_KEY = {
    (item['kind'], item['background_id']): item
    for item in BACKGROUND_CATALOG
}


def normalize_kind(value):
    kind = str(value or '').strip().lower()
    return kind if kind in BACKGROUND_KINDS else ''


def get_background_definition(kind, background_id):
    return BACKGROUND_BY_KEY.get((normalize_kind(kind), str(background_id or '').strip().lower()))


def ensure_background_schema(conn):
    for statement in (
        '''
        CREATE TABLE IF NOT EXISTS user_backgrounds (
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            background_id TEXT NOT NULL,
            acquired_source TEXT NOT NULL DEFAULT 'shop',
            acquired_ref TEXT,
            acquired_at TEXT NOT NULL,
            PRIMARY KEY(user_id, kind, background_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS user_background_preferences (
            user_id INTEGER PRIMARY KEY,
            theme_background_id TEXT NOT NULL DEFAULT 'classic',
            battle_background_id TEXT NOT NULL DEFAULT 'classic',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS background_shop_sets (
            set_id TEXT PRIMARY KEY,
            shop_date TEXT NOT NULL,
            scope_key TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS background_shop_offers (
            set_id TEXT NOT NULL,
            slot INTEGER NOT NULL,
            background_id TEXT NOT NULL,
            price INTEGER NOT NULL,
            PRIMARY KEY(set_id, slot)
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS background_shop_purchases (
            user_id INTEGER NOT NULL,
            set_id TEXT NOT NULL,
            slot INTEGER NOT NULL,
            acquired_at TEXT NOT NULL,
            PRIMARY KEY(user_id, set_id, slot)
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS background_shop_user_state (
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            active_set_id TEXT NOT NULL,
            locked INTEGER NOT NULL DEFAULT 0,
            refresh_date TEXT NOT NULL,
            refresh_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, kind)
        )
        ''',
    ):
        conn.execute(statement)
    conn.commit()


def get_background_preferences(conn, user_id):
    defaults = dict(DEFAULT_BACKGROUNDS)
    if user_id is None:
        return defaults
    ensure_background_schema(conn)
    row = conn.execute(
        'SELECT theme_background_id, battle_background_id FROM user_background_preferences WHERE user_id = ?',
        (int(user_id),),
    ).fetchone()
    if row is None:
        return defaults
    for kind in BACKGROUND_KINDS:
        column = f'{kind}_background_id'
        candidate = str(row[column] or '')
        if get_background_definition(kind, candidate):
            defaults[kind] = candidate
    return defaults


def list_owned_background_ids(conn, user_id, kind):
    kind = normalize_kind(kind)
    owned = {DEFAULT_BACKGROUNDS[kind]}
    if user_id is None:
        return owned
    ensure_background_schema(conn)
    rows = conn.execute(
        'SELECT background_id FROM user_backgrounds WHERE user_id = ? AND kind = ?',
        (int(user_id), kind),
    ).fetchall()
    for row in rows:
        background_id = str(row['background_id'] or '')
        if get_background_definition(kind, background_id):
            owned.add(background_id)
    return owned


def _create_background_shop_set_conn(conn, kind, shop_date, scope_key):
    rows = [
        {'skin_id': item['background_id'], 'price': item['price'], 'shop_weight': item['weight']}
        for item in BACKGROUND_CATALOG
        if item['kind'] == kind and int(item['weight']) > 0
    ]
    if len(rows) < BACKGROUND_OFFER_COUNT:
        raise ValueError('可售背景不足')
    set_id = f'{kind}:{shop_date}:{secrets.token_hex(8)}'
    now = db.utc_now()
    conn.execute(
        'INSERT INTO background_shop_sets (set_id, shop_date, scope_key, kind, created_at) VALUES (?, ?, ?, ?, ?)',
        (set_id, shop_date, str(scope_key or '')[:80], kind, now),
    )
    for slot, row in enumerate(db._weighted_unique_skin_ids(rows, BACKGROUND_OFFER_COUNT), start=1):
        conn.execute(
            'INSERT INTO background_shop_offers (set_id, slot, background_id, price) VALUES (?, ?, ?, ?)',
            (set_id, slot, row['skin_id'], max(0, int(row['price']))),
        )
    return set_id


def _ensure_global_background_set_conn(conn, kind, shop_date):
    row = conn.execute(
        "SELECT set_id FROM background_shop_sets WHERE shop_date = ? AND scope_key = 'global' AND kind = ? ORDER BY created_at ASC LIMIT 1",
        (shop_date, kind),
    ).fetchone()
    if row is not None:
        count = conn.execute(
            'SELECT COUNT(*) AS count FROM background_shop_offers WHERE set_id = ?',
            (row['set_id'],),
        ).fetchone()['count']
        if int(count or 0) == BACKGROUND_OFFER_COUNT:
            return str(row['set_id'])
    return _create_background_shop_set_conn(conn, kind, shop_date, 'global')


def _ensure_background_user_state_conn(conn, user_id, kind, shop_date):
    uid = int(user_id)
    global_set_id = _ensure_global_background_set_conn(conn, kind, shop_date)
    row = conn.execute(
        'SELECT * FROM background_shop_user_state WHERE user_id = ? AND kind = ?',
        (uid, kind),
    ).fetchone()
    now = db.utc_now()
    if row is None:
        conn.execute(
            'INSERT INTO background_shop_user_state (user_id, kind, active_set_id, locked, refresh_date, refresh_count, updated_at) VALUES (?, ?, ?, 0, ?, 0, ?)',
            (uid, kind, global_set_id, shop_date, now),
        )
        return conn.execute(
            'SELECT * FROM background_shop_user_state WHERE user_id = ? AND kind = ?',
            (uid, kind),
        ).fetchone()
    active_set_id = str(row['active_set_id'] or '')
    locked = bool(row['locked'])
    refresh_date = str(row['refresh_date'] or '')
    refresh_count = max(0, int(row['refresh_count'] or 0))
    active = conn.execute(
        'SELECT shop_date FROM background_shop_sets WHERE set_id = ?', (active_set_id,),
    ).fetchone() if active_set_id else None
    if refresh_date != shop_date:
        refresh_date = shop_date
        refresh_count = 0
    if not locked and (active is None or str(active['shop_date'] or '') != shop_date):
        active_set_id = global_set_id
    elif active is None:
        active_set_id = global_set_id
    conn.execute(
        'UPDATE background_shop_user_state SET active_set_id = ?, refresh_date = ?, refresh_count = ?, updated_at = ? WHERE user_id = ? AND kind = ?',
        (active_set_id, refresh_date, refresh_count, now, uid, kind),
    )
    return conn.execute(
        'SELECT * FROM background_shop_user_state WHERE user_id = ? AND kind = ?',
        (uid, kind),
    ).fetchone()


def _catalog_item_payload(item, owned, equipped, slot=None):
    background_id = item['background_id']
    payload = {
        'background_id': background_id,
        'name': item['name'],
        'price': int(item['price']),
        'weight': int(item['weight']),
        'asset_url': item['asset_url'],
        'biome': item['biome'],
        'description': item['description'],
        'owned': background_id in owned,
        'equipped': equipped,
    }
    if slot is not None:
        payload['slot'] = int(slot)
    return payload


def get_background_payload(conn, user_id):
    preferences = get_background_preferences(conn, user_id)
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    seconds_to_refresh = db._title_shop_seconds_to_refresh(current)
    shops = {}
    for kind in BACKGROUND_KINDS:
        owned = list_owned_background_ids(conn, user_id, kind)
        state = _ensure_background_user_state_conn(conn, user_id, kind, shop_date) if user_id is not None else None
        active_set_id = str(state['active_set_id'] or '') if state is not None else ''
        refresh_count = max(0, int(state['refresh_count'] or 0)) if state is not None else 0
        offers = []
        if active_set_id:
            rows = conn.execute(
                'SELECT slot, background_id, price FROM background_shop_offers WHERE set_id = ? ORDER BY slot',
                (active_set_id,),
            ).fetchall()
            for row in rows:
                item = get_background_definition(kind, row['background_id'])
                if item is not None:
                    offers.append(_catalog_item_payload(item, owned, preferences[kind] == item['background_id'], row['slot']))
        items = [
            _catalog_item_payload(item, owned, preferences[kind] == item['background_id'])
            for item in BACKGROUND_CATALOG if item['kind'] == kind
        ]
        shops[kind] = {
            'kind': kind,
            'set_id': active_set_id,
            'locked': bool(state['locked']) if state is not None else False,
            'refresh_cost': BACKGROUND_REFRESH_BASE_COST + refresh_count * BACKGROUND_REFRESH_COST_STEP,
            'refresh_count': refresh_count,
            'seconds_to_refresh': seconds_to_refresh,
            'shop_date': shop_date,
            'offers': offers,
            'items': items,
            'equipped': preferences[kind],
            'owned_background_ids': sorted(owned),
            'offer_count': BACKGROUND_OFFER_COUNT,
        }
    if user_id is not None:
        conn.commit()
    return {'preferences': preferences, 'shops': shops}


def purchase_background(user_id, kind, set_id, slot):
    kind = normalize_kind(kind)
    try:
        offer_slot = int(slot)
    except (TypeError, ValueError):
        return None, '商品不存在或已下架'
    if user_id is None or not kind:
        return None, '商品不存在或已下架'
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    with db.get_db_connection() as conn:
        ensure_background_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        state = _ensure_background_user_state_conn(conn, user_id, kind, shop_date)
        active_set_id = str(state['active_set_id'] or '')
        if str(set_id or '') != active_set_id:
            conn.rollback()
            return None, '商店内容已刷新，请按当前商品操作'
        offer = conn.execute(
            'SELECT slot, background_id, price FROM background_shop_offers WHERE set_id = ? AND slot = ?',
            (active_set_id, offer_slot),
        ).fetchone()
        definition = get_background_definition(kind, offer['background_id']) if offer is not None else None
        if offer is None or definition is None:
            conn.rollback()
            return None, '商品不存在或已下架'
        background_id = definition['background_id']
        purchased = conn.execute(
            'SELECT 1 FROM background_shop_purchases WHERE user_id = ? AND set_id = ? AND slot = ?',
            (int(user_id), active_set_id, offer_slot),
        ).fetchone()
        if purchased is not None:
            conn.rollback()
            return None, '本轮已购买该商品'
        if background_id in list_owned_background_ids(conn, user_id, kind):
            conn.rollback()
            return None, '你已经拥有这个背景了！'
        user = conn.execute('SELECT * FROM users WHERE id = ? AND deleted_at IS NULL', (int(user_id),)).fetchone()
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
            (free_after, paid_after, int(user_id)),
        )
        source_id = f'{active_set_id}:{offer_slot}'
        conn.execute(
            "INSERT INTO user_currency_transactions (user_id, currency, free_delta, paid_delta, reason, source_type, source_id, balance_free_after, balance_paid_after, admin_username, created_at) VALUES (?, 'thorn_dew', ?, ?, ?, 'background_purchase', ?, ?, ?, '', ?)",
            (int(user_id), -free_spent, -paid_spent, '购买背景：' + definition['name'], source_id,
             free_after, paid_after, now),
        )
        conn.execute(
            "INSERT INTO user_backgrounds (user_id, kind, background_id, acquired_source, acquired_ref, acquired_at) VALUES (?, ?, ?, 'shop', ?, ?)",
            (int(user_id), kind, background_id, source_id, now),
        )
        conn.execute(
            'INSERT INTO background_shop_purchases (user_id, set_id, slot, acquired_at) VALUES (?, ?, ?, ?)',
            (int(user_id), active_set_id, offer_slot, now),
        )
        conn.commit()
        return get_background_payload(conn, user_id), None


def refresh_background_shop(user_id, kind):
    kind = normalize_kind(kind)
    if user_id is None or not kind:
        return None, '商店不存在'
    current = db._title_shop_now()
    shop_date = db._title_shop_date(current)
    with db.get_db_connection() as conn:
        ensure_background_schema(conn)
        conn.execute('BEGIN IMMEDIATE')
        state = _ensure_background_user_state_conn(conn, user_id, kind, shop_date)
        refresh_count = max(0, int(state['refresh_count'] or 0))
        cost = BACKGROUND_REFRESH_BASE_COST + refresh_count * BACKGROUND_REFRESH_COST_STEP
        user = conn.execute('SELECT * FROM users WHERE id = ? AND deleted_at IS NULL', (int(user_id),)).fetchone()
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
            (free_after, paid_after, int(user_id)),
        )
        set_id = _create_background_shop_set_conn(conn, kind, shop_date, f'user:{int(user_id)}')
        conn.execute(
            'INSERT INTO background_shop_user_state (user_id, kind, active_set_id, locked, refresh_date, refresh_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(user_id, kind) DO UPDATE SET active_set_id = excluded.active_set_id, locked = excluded.locked, refresh_date = excluded.refresh_date, refresh_count = excluded.refresh_count, updated_at = excluded.updated_at',
            (int(user_id), kind, set_id, int(state['locked'] or 0), shop_date, refresh_count + 1, db.utc_now()),
        )
        conn.execute(
            "INSERT INTO user_currency_transactions (user_id, currency, free_delta, paid_delta, reason, source_type, source_id, balance_free_after, balance_paid_after, admin_username, created_at) VALUES (?, 'thorn_dew', ?, ?, ?, 'background_shop_refresh', ?, ?, ?, '', ?)",
            (int(user_id), -free_spent, -paid_spent, '刷新背景商店（第%d次）' % (refresh_count + 1),
             set_id + ':refresh', free_after, paid_after, db.utc_now()),
        )
        conn.commit()
        return get_background_payload(conn, user_id), None


def equip_background(conn, user_id, kind, background_id):
    kind = normalize_kind(kind)
    definition = get_background_definition(kind, background_id)
    if user_id is None or not definition:
        return '背景不存在'
    background_id = definition['background_id']
    if background_id not in list_owned_background_ids(conn, user_id, kind):
        return '尚未拥有该背景'
    preferences = get_background_preferences(conn, user_id)
    conn.execute(
        '''
        INSERT INTO user_background_preferences (user_id, theme_background_id, battle_background_id, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            theme_background_id = excluded.theme_background_id,
            battle_background_id = excluded.battle_background_id,
            updated_at = excluded.updated_at
        ''',
        (int(user_id), preferences['theme'], preferences['battle'], db.utc_now()),
    )
    column = 'theme_background_id' if kind == 'theme' else 'battle_background_id'
    conn.execute(
        f'UPDATE user_background_preferences SET {column} = ?, updated_at = ? WHERE user_id = ?',
        (background_id, db.utc_now(), int(user_id)),
    )
    return None
