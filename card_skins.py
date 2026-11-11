# -*- coding: utf-8 -*-
"""卡牌皮肤（Card Skin）目录与装备（设计 2026-09-26）。

- 皮肤是**全局外观**：装备后玩家所有手牌的卡背换成该皮肤的卡背图；
  自己看自己的明牌卡面时，卡面区域显示该皮肤的卡面图（其余元素照常）。
- 特殊皮肤「区」：其他玩家视角里，该玩家的明牌卡面区域也显示**卡背图**
  （真卡面只对自己可见——卡面含微恐元素）。
- 素材：/static/assets/card-skins/{front,back}/<skin_id>.svg
- 默认卡背「初始」永远免费，不进商店（替换原问号卡背）。

目录是静态的（与 title_shop_catalog 同风格），入库到 card_skin_catalog。
"""

import db

SKIN_IDS = (
    '区', '叶框', '金叶框', '绷带', '标靶', '蠕虫', '阴阳', '阴阳玉',
    'tower_curse_ironclad', 'tower_curse_silent', 'tower_curse_defect',
    'tower_curse_necrobinder', 'tower_curse_regent',
)

# ---------- 皮肤分类与布局绑定 ----------
# 一般皮肤（normal）：用默认布局，卡面元素都在默认数据显示位置。
# 特殊皮肤（special）：卡面自带徽记/装饰，元素要按皮肤图做特殊绑定，
#   由 layout 指定用哪一套绑定；默认布局以外的实现都算特殊皮肤。
SKIN_CATEGORY_NORMAL = 'normal'
SKIN_CATEGORY_SPECIAL = 'special'
SKIN_LAYOUT_DEFAULT = 'default'
# 卡面自带橙色六边形（能量）与蓝色辉星（魔力）：消耗数字挂到徽记正中间、
# 类型名嵌进黄框下端的金色小标签（坐标见 static/css/style.css 的
# `.card.card-mana-on-star` 段）。缺失该绑定的皮肤按 default 渲染。
SKIN_LAYOUT_MANA_ON_STAR = 'mana_on_star'
# id -> (价格, 商店权重, 分类/布局)。与设计表一致；权重越高越常出现。
# layout：一般皮肤一律 SKIN_LAYOUT_DEFAULT（默认数据显示位置）；
#   特殊皮肤写自己的绑定，由客户端按绑定套用卡面元素的特殊位置。
CARD_SKIN_CATALOG = [
    {'skin_id': '区', 'name': '区', 'price': 50000, 'weight': 1, 'special': 'back_as_front',
     'layout': SKIN_LAYOUT_DEFAULT},
    {'skin_id': '叶框', 'name': '叶框', 'price': 10000, 'weight': 10, 'special': '',
     'layout': SKIN_LAYOUT_DEFAULT},
    {'skin_id': '金叶框', 'name': '金叶框', 'price': 20000, 'weight': 5, 'special': '',
     'layout': SKIN_LAYOUT_DEFAULT},
    {'skin_id': '绷带', 'name': '绷带', 'price': 30000, 'weight': 5, 'special': '',
     'layout': SKIN_LAYOUT_DEFAULT},
    {'skin_id': '标靶', 'name': '标靶', 'price': 15000, 'weight': 3, 'special': '',
     'layout': SKIN_LAYOUT_DEFAULT},
    {'skin_id': '蠕虫', 'name': '蠕虫', 'price': 25000, 'weight': 5, 'special': '',
     'layout': SKIN_LAYOUT_DEFAULT},
    {'skin_id': '阴阳', 'name': '阴阳', 'price': 10000, 'weight': 10, 'special': '',
     'layout': SKIN_LAYOUT_DEFAULT},
    {'skin_id': '阴阳玉', 'name': '阴阳玉', 'price': 30000, 'weight': 3, 'special': '',
     'layout': SKIN_LAYOUT_DEFAULT},
    # 赛季「塔之诅咒」素材：特殊皮肤（卡面自带徽记）。不上架商店
    # （price=0, weight=0），由赛季/活动系统单独发放。
    {'skin_id': 'tower_curse_ironclad', 'name': '铁甲战士', 'price': 0, 'weight': 0, 'special': '',
     'layout': SKIN_LAYOUT_MANA_ON_STAR},
    {'skin_id': 'tower_curse_silent', 'name': '静默猎手', 'price': 0, 'weight': 0, 'special': '',
     'layout': SKIN_LAYOUT_MANA_ON_STAR},
    {'skin_id': 'tower_curse_defect', 'name': '故障机器人', 'price': 0, 'weight': 0, 'special': '',
     'layout': SKIN_LAYOUT_MANA_ON_STAR},
    {'skin_id': 'tower_curse_necrobinder', 'name': '亡灵契约师', 'price': 0, 'weight': 0, 'special': '',
     'layout': SKIN_LAYOUT_MANA_ON_STAR},
    {'skin_id': 'tower_curse_regent', 'name': '储君', 'price': 0, 'weight': 0, 'special': '',
     'layout': SKIN_LAYOUT_MANA_ON_STAR},
]

DEFAULT_CARD_BACK = '初始'

# 卡面/卡背美术修订号：换图时 bump（客户端 game.js 的 CARD_SKIN_ART_REVISION 同步改），
# 让 URL 带参避免浏览器缓存旧 SVG。
CARD_SKIN_ART_REVISION = 8
# 赛季「塔之诅咒」五款卡面单独计版本号：只有换过图的这五款升版本，
# 其余皮肤的 URL 保持不变，不用陪着重下一次图。
TOWER_CURSE_SKIN_ART_REVISION = 12


def skin_art_revision(skin_id):
    """按皮肤取美术修订号：塔之诅咒五款用独立版本号，其余沿用全局值。"""
    return TOWER_CURSE_SKIN_ART_REVISION if str(skin_id or '').startswith('tower_curse_') else CARD_SKIN_ART_REVISION


def skin_layout(skin_id):
    """皮肤的数据显示布局；空/未知皮肤一律按一般皮肤的默认布局。"""
    item = SKIN_BY_ID.get(str(skin_id or '').strip())
    return str((item or {}).get('layout') or SKIN_LAYOUT_DEFAULT)


def skin_category(skin_id):
    """一般 / 特殊：默认布局以外的都算特殊皮肤。"""
    return SKIN_CATEGORY_NORMAL if skin_layout(skin_id) == SKIN_LAYOUT_DEFAULT else SKIN_CATEGORY_SPECIAL


SKIN_BY_ID = {item['skin_id']: item for item in CARD_SKIN_CATALOG}


def ensure_card_skin_schema(conn):
    """幂等建目录表 + users 装备列 + 种子目录。"""
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS card_skin_catalog (
            skin_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            shop_weight INTEGER NOT NULL DEFAULT 0,
            special TEXT NOT NULL DEFAULT '',
            layout TEXT NOT NULL DEFAULT 'default',
            active INTEGER NOT NULL DEFAULT 1
        )
        '''
    )
    catalog_columns = {row['name'] for row in conn.execute('PRAGMA table_info(card_skin_catalog)').fetchall()}
    if 'layout' not in catalog_columns:
        # 老库补列：默认布局 = 一般皮肤，历史皮肤都保持原样
        conn.execute("ALTER TABLE card_skin_catalog ADD COLUMN layout TEXT NOT NULL DEFAULT 'default'")
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(users)').fetchall()}
    if 'card_skin' not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN card_skin TEXT DEFAULT ''")
    for item in CARD_SKIN_CATALOG:
        conn.execute(
            '''
            INSERT INTO card_skin_catalog (skin_id, name, price, shop_weight, special, layout, active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(skin_id) DO UPDATE SET
                name = excluded.name,
                price = excluded.price,
                shop_weight = excluded.shop_weight,
                special = excluded.special,
                layout = excluded.layout,
                active = 1
            ''',
            (item['skin_id'], item['name'], item['price'], item['weight'], item['special'],
             item.get('layout') or SKIN_LAYOUT_DEFAULT),
        )
    conn.commit()


def get_equipped_card_skin(conn, user_id):
    """装备中的皮肤 id；空串/None = 默认卡背。"""
    row = conn.execute(
        'SELECT card_skin FROM users WHERE id = ? AND deleted_at IS NULL',
        (int(user_id),),
    ).fetchone()
    if row is None:
        return ''
    skin_id = str(row['card_skin'] or '').strip()
    return skin_id if skin_id and skin_id in SKIN_BY_ID else ''


def list_owned_card_skins(conn, user_id):
    """已拥有的皮肤 id 集合（ purchases 表与称号的 user_titles 同构）。"""
    ensure_card_skin_schema(conn)
    rows = conn.execute(
        'SELECT skin_id FROM user_card_skins WHERE user_id = ?',
        (int(user_id),),
    ).fetchall()
    return {str(row['skin_id']) for row in rows}


def equip_card_skin(conn, user_id, skin_id):
    """装备（或换装/卸下）。未拥有的皮肤拒绝。返回错误文案或 None。"""
    ensure_card_skin_schema(conn)
    skin_id = str(skin_id or '').strip()
    if skin_id and skin_id not in SKIN_BY_ID:
        return '未知皮肤'
    if skin_id:
        owned = conn.execute(
            'SELECT 1 FROM user_card_skins WHERE user_id = ? AND skin_id = ?',
            (int(user_id), skin_id),
        ).fetchone()
        if owned is None:
            return '尚未拥有该皮肤'
    conn.execute(
        'UPDATE users SET card_skin = ? WHERE id = ?',
        (skin_id, int(user_id)),
    )
    return None


def card_skin_payload(conn, user_id):
    """外观页/客户端需要的完整皮肤信息。"""
    ensure_card_skin_schema(conn)
    owned = list_owned_card_skins(conn, user_id)
    equipped = get_equipped_card_skin(conn, user_id)
    items = []
    for item in CARD_SKIN_CATALOG:
        items.append({
            'skin_id': item['skin_id'],
            'name': item['name'],
            'special': item['special'],
            'category': skin_category(item['skin_id']),
            'layout': skin_layout(item['skin_id']),
            'owned': item['skin_id'] in owned,
            'equipped': item['skin_id'] == equipped,
            'front_url': f"/static/assets/card-skins/front/{item['skin_id']}.svg?v={skin_art_revision(item['skin_id'])}",
            'back_url': f"/static/assets/card-skins/back/{item['skin_id']}.svg?v={skin_art_revision(item['skin_id'])}",
        })
    return {
        'items': items,
        'equipped': equipped,
        'default_back_url': f'/static/assets/card-skins/back/{DEFAULT_CARD_BACK}.svg?v={CARD_SKIN_ART_REVISION}',
    }


def public_card_skins_for_room(room):
    """对局状态/回放 meta 用：按座位序列出每个玩家的装备皮肤（未装备为空串）。"""
    skins = []
    for psid in getattr(room, 'player_sids', []) or []:
        profile = room_player_card_skin(room, psid)
        skins.append(profile)
    return skins


def room_player_card_skin(room, sid):
    """单个玩家的卡牌皮肤 id（房间 profile 快照优先，回落 users 表）。"""
    profile = {}
    if room is not None and hasattr(room, 'get_player_profile'):
        profile = room.get_player_profile(sid) or {}
    skin_id = str(profile.get('card_skin') or '')
    if skin_id:
        return skin_id
    user_id = profile.get('user_id')
    if user_id:
        try:
            with db.get_db_connection() as conn:
                return get_equipped_card_skin(conn, user_id)
        except Exception:
            return ''
    return ''
