"""通行证（战斗通行证）：S1「荆棘之路」（免费）/「黄金之路」（250 金露）。

设计文档：docs/通行证-计划.md

核心规则（2026-11-11 定稿）：
- 经验（XP）三个来源：对局 / 爬塔 / 每日签到；累计 100 XP 升 1 级，1 级推进 1 格泡泡。
- 对局 XP = Min{40, ceil(用时秒/10), 回合数*5}，胜利 ×1.5。
- 爬塔 XP = Min{1000, ceil(Score/5)}；每周前 3 次爬塔奖励 ×3（无每日上限）。
- 签到：原本的荆露奖励等额换成 XP。
- 双轨各 100 格；100 格之后每级 100 荆露（免费）/50 荆露（进阶）。
- 黄金之路增益：荆露与 XP ×1.5、天梯特殊修正 +2、每日签到额外 1 保分卡 + 1 双倍卡。
- 通行证领取的门票**允许溢出**上限；签到/对局/爬塔产出的门票仍受 leisure_ticket.TICKET_CAP 约束。

所有写操作都接收调用方传入的 conn，且假定调用方已开启事务（与 pvp_economy.settle_conn
同一约定），以便与对局结算 / 爬塔结算原子落库。
"""
from __future__ import annotations

import json
import math
import time
import uuid
from datetime import datetime, timedelta, timezone

PASS_SEASON_ID = 'S1'
PASS_MAX_LEVEL = 100
XP_PER_LEVEL = 100
GOLDEN_PRICE_GOLDEN_DEW = 250
# 2026-11-15：金露兑换经验（固定 5 金露 → 100 经验；不叠加黄金之路 ×1.5）。
XP_BUY_GOLDEN_DEW = 5
XP_BUY_AMOUNT = 100

MATCH_XP_CAP = 40
MATCH_XP_SECONDS_DIVISOR = 10
MATCH_XP_PER_ROUND = 5
MATCH_XP_WIN_MULTIPLIER = 1.5

STORY_XP_CAP = 1000
STORY_XP_SCORE_DIVISOR = 5
STORY_WEEKLY_TRIPLE_COUNT = 3
STORY_WEEKLY_TRIPLE_MULTIPLIER = 3.0

GOLDEN_XP_MULTIPLIER = 1.5
GOLDEN_DEW_MULTIPLIER = 1.5
GOLDEN_RANK_SPECIAL_BONUS = 2.0
GOLDEN_CHECKIN_SHIELD_CARDS = 1
GOLDEN_CHECKIN_DOUBLE_CARDS = 1

TRACK_FREE = 'free'
TRACK_GOLDEN = 'golden'
TRACKS = (TRACK_FREE, TRACK_GOLDEN)
TRACK_LABELS = {TRACK_FREE: '荆棘之路', TRACK_GOLDEN: '黄金之路'}

_CN_TZ = timezone(timedelta(hours=8))
# 赛季锚点：上线日 2026-11-11 00:00 开始，到 2026-11-30 23:59:59 截止（北京时间，含 23:59 整分钟）。
PASS_SEASON_START = datetime(2026, 11, 11, 0, 0, 0, tzinfo=_CN_TZ)
PASS_SEASON_END = datetime(2026, 11, 30, 23, 59, 59, tzinfo=_CN_TZ)

REWARD_KIND_LABELS = {
    'dew': '荆露',
    'golden_dew': '金露',
    'shield_card': '保分卡',
    'double_card': '双倍卡',
    'ticket': '休闲花园门票',
    'title': '称号',
    'card_skin': '卡牌皮肤',
    'player_skin': '玩家皮肤',
    'background': '背景',
}

REWARD_ICONS = {
    'dew': '/static/assets/ui-icons/thorn-dew.svg',
    'golden_dew': '/static/assets/ui-icons/golden-dew.svg',
    'shield_card': '/static/assets/rewards/score-insurance-card.svg',
    'double_card': '/static/assets/rewards/double-card.svg',
    'ticket': '/static/assets/leisure/tickets.svg',
    'title': '/static/assets/ui-icons/achievements.svg',
}


def _dew(amount):
    return {'kind': 'dew', 'amount': int(amount)}


def _gold(amount):
    return {'kind': 'golden_dew', 'amount': int(amount)}


def _shield(amount=1):
    return {'kind': 'shield_card', 'amount': int(amount)}


def _double(amount=1):
    return {'kind': 'double_card', 'amount': int(amount)}


def _ticket(amount=1):
    return {'kind': 'ticket', 'amount': int(amount)}


def _title(item_id):
    return {'kind': 'title', 'item_id': item_id}


def _skin(item_id):
    return {'kind': 'card_skin', 'item_id': item_id}


def _player_skin(item_id):
    return {'kind': 'player_skin', 'item_id': item_id}


def _background(item_id):
    return {'kind': 'background', 'item_id': item_id}


# 个位格（每 10 级重复一次）。键是 1..9 的个位。
PATTERN_FREE = {
    1: _dew(200),
    2: _shield(),
    3: _dew(200),
    4: _ticket(),
    5: _gold(5),
    6: _double(),
    7: _dew(200),
    8: _ticket(),
    9: _dew(200),
}

PATTERN_GOLDEN = {
    1: _shield(),
    2: _dew(100),
    3: _double(),
    4: _dew(100),
    5: _ticket(),
    6: _dew(100),
    7: _double(),
    8: _dew(100),
    9: _shield(),
}

# 整十里程碑。
# 2026-11-12：皮肤格改发「塔之诅咒」系列玩家皮肤（大厅/对局头像），不再是卡牌皮肤；
# 5 款玩家皮肤 + 2 款赛季背景 + 2 个称号，每条轨道各拿一遍
# （同款在不同轨道重复出场是刻意的：只买一条轨道收不全）。
_TITLE_FREE = 'pass_s1_free_lv10'
_TITLE_GOLDEN = 'pass_s1_golden_lv20'
# 外观格共 10 个：五个卡牌皮肤（卡背）+ 五个玩家皮肤，各出现一次。
MILESTONES = {
    10: {TRACK_FREE: _title(_TITLE_FREE),
         TRACK_GOLDEN: _skin('tower_curse_ironclad')},
    20: {TRACK_FREE: _dew(1000),
         TRACK_GOLDEN: _title(_TITLE_GOLDEN)},
    30: {TRACK_FREE: _skin('tower_curse_silent'),
         TRACK_GOLDEN: _player_skin('tower_curse_ironclad')},
    40: {TRACK_FREE: _gold(25),
         TRACK_GOLDEN: _dew(500)},
    50: {TRACK_FREE: _player_skin('tower_curse_silent'),
         TRACK_GOLDEN: _skin('tower_curse_defect')},
    60: {TRACK_FREE: _background('tower_curse_dark_harbor'),
         TRACK_GOLDEN: _player_skin('tower_curse_defect')},
    70: {TRACK_FREE: _dew(1000),
         TRACK_GOLDEN: _skin('tower_curse_necrobinder')},
    80: {TRACK_FREE: _player_skin('tower_curse_necrobinder'),
         TRACK_GOLDEN: _background('tower_curse_deepwood')},
    90: {TRACK_FREE: _gold(25),
         TRACK_GOLDEN: _dew(500)},
    100: {TRACK_FREE: _skin('tower_curse_regent'),
          TRACK_GOLDEN: _player_skin('tower_curse_regent')},
}

# 称号实物：进 title_catalog，玩家领取后可在称号列表里装备。
PASS_TITLES = {
    _TITLE_FREE: {
        'name': '塔之诅咒',
        'color': '#8a8a8a',
        'markup': '{solid:#8a8a8a}塔之诅咒{/}',
    },
    _TITLE_GOLDEN: {
        'name': '塔之诅咒',
        'color': '#7857d8',
        'markup': '{rainbow}塔之诅咒{/}',
    },
}

# 100 级之后每级（溢出格）的固定奖励。
OVERFLOW = {TRACK_FREE: _dew(100), TRACK_GOLDEN: _dew(50)}


# --------------------------------------------------------------------------
# 时间与等级
# --------------------------------------------------------------------------

def season_id():
    return PASS_SEASON_ID


def _now_iso(now=None):
    ts = float(now if now is not None else time.time())
    return datetime.fromtimestamp(ts, _CN_TZ).isoformat(timespec='seconds')


def _beijing(now=None):
    ts = float(now if now is not None else time.time())
    return datetime.fromtimestamp(ts, _CN_TZ)


def season_bounds(now=None):
    start, end = PASS_SEASON_START, PASS_SEASON_END
    return start, end, _beijing(now) < end


def week_key(now=None):
    moment = _beijing(now)
    iso = moment.isocalendar()
    return f'{iso[0]}-W{iso[1]:02d}'


def level_for_xp(xp_total):
    """100 XP 一级；第 1 级需要 100 XP，0 XP 是 0 级。"""
    try:
        xp = max(0, int(xp_total))
    except (TypeError, ValueError):
        return 0
    return xp // XP_PER_LEVEL


def xp_into_level(xp_total):
    try:
        xp = max(0, int(xp_total))
    except (TypeError, ValueError):
        return 0
    return xp % XP_PER_LEVEL


def reward_for(level, track):
    track_key = track if track in TRACKS else TRACK_FREE
    try:
        lv = int(level)
    except (TypeError, ValueError):
        return None
    if lv <= 0:
        return None
    if lv > PASS_MAX_LEVEL:
        overflow = dict(OVERFLOW[track_key])
        overflow['overflow'] = True
        overflow['level'] = lv
        return overflow
    if lv % 10 == 0:
        base = MILESTONES.get(lv, {}).get(track_key)
    else:
        base = PATTERN_FREE.get(lv % 10) if track_key == TRACK_FREE else PATTERN_GOLDEN.get(lv % 10)
    if base is None:
        return None
    reward = dict(base)
    reward['overflow'] = False
    reward['level'] = lv
    return reward


def background_entry(item_id):
    """按 id 查背景（主题/战斗两种都查），返回 (kind, definition)。"""
    try:
        from backgrounds import BACKGROUND_KINDS, get_background_definition
    except Exception:
        return None, None
    for kind in BACKGROUND_KINDS:
        entry = get_background_definition(kind, item_id)
        if entry is not None:
            return kind, entry
    return None, None


def cosmetic_name(kind, item_id):
    """皮肤/背景/称号的展示名；查不到就退回 id（目录未上线时不至于渲染成空白）。"""
    item_id = str(item_id or '')
    if not item_id:
        return ''
    try:
        if kind == 'card_skin':
            from card_skins import SKIN_BY_ID
            entry = SKIN_BY_ID.get(item_id)
            if entry:
                return str(entry.get('name') or item_id)
        elif kind == 'player_skin':
            from player_skins import PLAYER_SKIN_BY_ID
            entry = PLAYER_SKIN_BY_ID.get(item_id)
            if entry:
                return str(entry.get('name') or item_id)
        elif kind == 'background':
            _, entry = background_entry(item_id)
            if entry:
                return str(entry.get('name') or item_id)
    except Exception:
        pass
    if kind == 'title' and item_id in PASS_TITLES:
        return PASS_TITLES[item_id]['name']
    return item_id


def reward_type_label(reward):
    """奖励类型标签：皮肤/背景/称号要写明白是哪一种；货币与道具返回空串（文字本身已说明）。"""
    if not reward:
        return ''
    kind = str(reward.get('kind') or '')
    if kind == 'card_skin':
        return '卡牌皮肤'
    if kind == 'player_skin':
        return '玩家皮肤'
    if kind == 'title':
        return '称号'
    if kind == 'background':
        bg_kind, _ = background_entry(reward.get('item_id'))
        return '战斗背景' if bg_kind == 'battle' else '主题背景'
    return ''


def reward_amount_text(level, track):
    reward = reward_for(level, track)
    if reward is None:
        return ''
    kind = reward['kind']
    amount = int(reward.get('amount') or 0)
    if kind in ('card_skin', 'player_skin', 'background', 'title'):
        return cosmetic_name(kind, reward.get('item_id'))
    label = REWARD_KIND_LABELS.get(kind, kind)
    if amount > 1:
        return f'{amount} {label}'
    return label


def reward_icon_url(reward):
    """格子上的图标：货币/道具用现成图标，皮肤与背景直接借用实物素材。"""
    if not reward:
        return ''
    kind = str(reward.get('kind') or '')
    item_id = str(reward.get('item_id') or '')
    if kind == 'card_skin' and item_id:
        try:
            from card_skins import skin_art_revision
            revision = skin_art_revision(item_id)
        except Exception:
            revision = 1
        return f'/static/assets/card-skins/front/{item_id}.svg?v={revision}'
    if kind == 'player_skin' and item_id:
        try:
            from player_skins import PLAYER_SKIN_BY_ID
            entry = PLAYER_SKIN_BY_ID.get(item_id) or {}
            return str(entry.get('texture_url') or '')
        except Exception:
            return ''
    if kind == 'background':
        # 背景原图是 1366x768 的场景图，缩到 18px 只是一块深色方块，格子统一用图形图标。
        return '/static/assets/ui-icons/gallery.svg'
    return REWARD_ICONS.get(kind, '')


# --------------------------------------------------------------------------
# 表结构
# --------------------------------------------------------------------------

_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS battle_pass_progress (
        user_id INTEGER NOT NULL,
        season_id TEXT NOT NULL,
        xp_total INTEGER NOT NULL DEFAULT 0,
        golden_unlocked_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, season_id)
    )''',
    '''CREATE TABLE IF NOT EXISTS battle_pass_xp_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        season_id TEXT NOT NULL,
        source TEXT NOT NULL,
        source_key TEXT NOT NULL,
        base_xp INTEGER NOT NULL DEFAULT 0,
        xp INTEGER NOT NULL DEFAULT 0,
        multiplier REAL NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        UNIQUE (user_id, season_id, source_key)
    )''',
    '''CREATE TABLE IF NOT EXISTS battle_pass_claims (
        user_id INTEGER NOT NULL,
        season_id TEXT NOT NULL,
        track TEXT NOT NULL,
        level INTEGER NOT NULL,
        reward_json TEXT NOT NULL DEFAULT '{}',
        claimed_at TEXT NOT NULL,
        PRIMARY KEY (user_id, season_id, track, level)
    )''',
    '''CREATE TABLE IF NOT EXISTS battle_pass_story_week (
        user_id INTEGER NOT NULL,
        season_id TEXT NOT NULL,
        week_key TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, season_id, week_key)
    )''',
    '''CREATE TABLE IF NOT EXISTS battle_pass_cosmetics (
        user_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        item_id TEXT NOT NULL,
        acquired_source TEXT NOT NULL DEFAULT 'battle_pass',
        acquired_at TEXT NOT NULL,
        PRIMARY KEY (user_id, kind, item_id)
    )''',
)


def ensure_pass_schema(conn):
    for statement in _SCHEMA:
        conn.execute(statement)


def ensure_pass_titles(conn):
    """保证通行证称号在 title_catalog 里存在（幂等，样式随 PASS_TITLES 更新）。"""
    import db  # 延迟导入：db 会反向 import battle_pass
    import title_styles
    for title_id, meta in PASS_TITLES.items():
        markup = str(meta.get('markup') or '').strip()
        style = title_styles.parse_title_style(markup) if markup else None
        db._upsert_title_catalog_conn(
            conn,
            title_id,
            meta['name'],
            meta.get('color') or '',
            source_type='battle_pass',
            source_ref=f'pass:{season_id()}',
            purchasable=False,
            active=True,
            style=style,
            style_markup=markup,
        )


# --------------------------------------------------------------------------
# 进度
# --------------------------------------------------------------------------

def _ensure_progress(conn, user_id, now=None):
    sid = season_id()
    now_text = _now_iso(now)
    conn.execute(
        '''INSERT OR IGNORE INTO battle_pass_progress
           (user_id, season_id, xp_total, created_at, updated_at)
           VALUES (?, ?, 0, ?, ?)''',
        (int(user_id), sid, now_text, now_text),
    )
    return conn.execute(
        'SELECT * FROM battle_pass_progress WHERE user_id = ? AND season_id = ?',
        (int(user_id), sid),
    ).fetchone()


def progress_row(conn, user_id):
    ensure_pass_schema(conn)
    return _ensure_progress(conn, user_id)


def golden_active(conn, user_id):
    row = progress_row(conn, user_id)
    return bool(row is not None and row['golden_unlocked_at'])


def xp_total(conn, user_id):
    row = progress_row(conn, user_id)
    return int(row['xp_total'] or 0) if row is not None else 0


def current_level(conn, user_id):
    return level_for_xp(xp_total(conn, user_id))


def golden_dew_multiplier(conn, user_id):
    return GOLDEN_DEW_MULTIPLIER if golden_active(conn, user_id) else 1.0


def golden_xp_multiplier(conn, user_id):
    return GOLDEN_XP_MULTIPLIER if golden_active(conn, user_id) else 1.0


def golden_rank_special_bonus(conn, user_id):
    return GOLDEN_RANK_SPECIAL_BONUS if golden_active(conn, user_id) else 0.0


def apply_golden_dew(conn, user_id, amount, *, source_key=''):
    """荆露收益的黄金之路 ×1.5（四舍五入），返回加成后的整数。"""
    try:
        value = int(amount or 0)
    except (TypeError, ValueError):
        return 0
    if value <= 0:
        return value
    multiplier = golden_dew_multiplier(conn, user_id)
    if multiplier <= 1.0:
        return value
    return _round_half_up(value * multiplier)


def _round_half_up(value):
    return int(math.floor(float(value) + 0.5))


# --------------------------------------------------------------------------
# 经验发放
# --------------------------------------------------------------------------

def _ledger_exists(conn, user_id, source_key):
    row = conn.execute(
        'SELECT 1 FROM battle_pass_xp_ledger WHERE user_id = ? AND season_id = ? AND source_key = ? LIMIT 1',
        (int(user_id), season_id(), str(source_key)),
    ).fetchone()
    return row is not None


def _apply_xp(conn, user_id, base_xp, *, source, source_key, multiplier=1.0, now=None):
    """写入经验台账 + 推进等级；source_key 幂等（同一 key 只发一次）。"""
    ensure_pass_schema(conn)
    uid = int(user_id)
    key = str(source_key)
    _, _, season_open = season_bounds(now)
    if not season_open:
        progress = _ensure_progress(conn, uid, now)
        current = int(progress['xp_total'] or 0)
        return {
            'applied': False, 'reason': 'season_closed', 'xp': 0,
            'xp_total': current, 'level_before': level_for_xp(current),
            'level_after': level_for_xp(current), 'multiplier': float(multiplier),
        }
    progress = _ensure_progress(conn, uid, now)
    before_xp = int(progress['xp_total'] or 0)
    if _ledger_exists(conn, uid, key):
        return {
            'applied': False, 'reason': 'duplicate', 'xp': 0,
            'xp_total': before_xp, 'level_before': level_for_xp(before_xp),
            'level_after': level_for_xp(before_xp), 'multiplier': float(multiplier),
        }
    base = max(0, int(base_xp or 0))
    gained = _round_half_up(base * float(multiplier)) if base else 0
    after_xp = before_xp + gained
    now_text = _now_iso(now)
    conn.execute(
        '''INSERT INTO battle_pass_xp_ledger
           (user_id, season_id, source, source_key, base_xp, xp, multiplier, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (uid, season_id(), str(source)[:40], key, base, gained, float(multiplier), now_text),
    )
    conn.execute(
        'UPDATE battle_pass_progress SET xp_total = ?, updated_at = ? WHERE user_id = ? AND season_id = ?',
        (after_xp, now_text, uid, season_id()),
    )
    return {
        'applied': True, 'reason': 'ok', 'xp': gained,
        'xp_total': after_xp,
        'level_before': level_for_xp(before_xp),
        'level_after': level_for_xp(after_xp),
        'multiplier': float(multiplier),
    }


def match_xp(seconds, rounds, won):
    """对局基础经验：Min{40, ceil(秒/10), 回合*5}，胜利再 ×1.5（四舍五入）。"""
    try:
        sec = max(0, float(seconds or 0))
        rnd = max(0, int(rounds or 0))
    except (TypeError, ValueError):
        return 0
    by_time = int(math.ceil(sec / MATCH_XP_SECONDS_DIVISOR)) if sec > 0 else 0
    by_round = rnd * MATCH_XP_PER_ROUND
    base = min(MATCH_XP_CAP, by_time, by_round)
    base = max(0, base)
    if won:
        base = _round_half_up(base * MATCH_XP_WIN_MULTIPLIER)
    return base


def grant_match_xp(conn, user_id, *, match_id, seconds, rounds, won, extra_key='', now=None):
    base = match_xp(seconds, rounds, won)
    if base <= 0:
        return {'applied': False, 'reason': 'empty', 'xp': 0, 'base_xp': 0}
    multiplier = golden_xp_multiplier(conn, user_id)
    result = _apply_xp(
        conn, user_id, base,
        source='match',
        source_key=f'match:{match_id}:{int(user_id)}{extra_key}',
        multiplier=multiplier,
        now=now,
    )
    result['base_xp'] = base
    return result


def story_xp(score):
    try:
        value = max(0.0, float(score or 0))
    except (TypeError, ValueError):
        return 0
    if value <= 0:
        return 0
    return min(STORY_XP_CAP, int(math.ceil(value / STORY_XP_SCORE_DIVISOR)))


def _story_week_used(conn, user_id, now=None):
    row = conn.execute(
        '''SELECT used FROM battle_pass_story_week
           WHERE user_id = ? AND season_id = ? AND week_key = ?''',
        (int(user_id), season_id(), week_key(now)),
    ).fetchone()
    return int(row['used'] or 0) if row is not None else 0


def grant_story_xp(conn, user_id, *, run_id, score, now=None):
    base = story_xp(score)
    if base <= 0:
        return {'applied': False, 'reason': 'empty', 'xp': 0, 'base_xp': 0}
    ensure_pass_schema(conn)
    uid = int(user_id)
    key = f'story:{run_id}'
    if _ledger_exists(conn, uid, key):
        used = _story_week_used(conn, uid, now)
        return {'applied': False, 'reason': 'duplicate', 'xp': 0, 'base_xp': base, 'week_used': used}
    used = _story_week_used(conn, uid, now)
    multiplier = golden_xp_multiplier(conn, uid)
    tripled = used < STORY_WEEKLY_TRIPLE_COUNT
    if tripled:
        multiplier *= STORY_WEEKLY_TRIPLE_MULTIPLIER
    result = _apply_xp(
        conn, uid, base, source='story', source_key=key,
        multiplier=multiplier, now=now,
    )
    if tripled and result.get('applied'):
        now_text = _now_iso(now)
        conn.execute(
            '''INSERT INTO battle_pass_story_week
               (user_id, season_id, week_key, used, updated_at)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(user_id, season_id, week_key)
               DO UPDATE SET used = used + 1, updated_at = excluded.updated_at''',
            (uid, season_id(), week_key(now), now_text),
        )
        used += 1
    result['base_xp'] = base
    result['tripled'] = bool(tripled and result.get('applied'))
    result['week_used'] = used
    return result


def grant_checkin_xp(conn, user_id, *, base_xp, checkin_date, now=None):
    multiplier = golden_xp_multiplier(conn, user_id)
    result = _apply_xp(
        conn, user_id, base_xp,
        source='checkin',
        source_key=f'checkin:{checkin_date}',
        multiplier=multiplier,
        now=now,
    )
    return result


def preview_checkin_xp(conn, user_id, base_xp):
    """签到预览：与 grant_checkin_xp 同口径（含黄金之路 ×1.5）。"""
    try:
        base = max(0, int(base_xp or 0))
    except (TypeError, ValueError):
        base = 0
    if base <= 0:
        return 0
    return _round_half_up(base * golden_xp_multiplier(conn, user_id))


# --------------------------------------------------------------------------
# 解锁 / 领取
# --------------------------------------------------------------------------

def purchase_golden(conn, user_id, *, now=None):
    """250 金露解锁黄金之路；返回 (payload, error)。"""
    ensure_pass_schema(conn)
    uid = int(user_id)
    progress = _ensure_progress(conn, uid, now)
    if progress['golden_unlocked_at']:
        return None, '已经解锁黄金之路'
    row = conn.execute('SELECT golden_dew FROM users WHERE id = ?', (uid,)).fetchone()
    if row is None:
        return None, '账号不存在'
    balance = int(row['golden_dew'] or 0)
    if balance < GOLDEN_PRICE_GOLDEN_DEW:
        return None, '金露不足'
    after = balance - GOLDEN_PRICE_GOLDEN_DEW
    now_text = _now_iso(now)
    conn.execute('UPDATE users SET golden_dew = ? WHERE id = ?', (after, uid))
    conn.execute(
        '''INSERT INTO user_currency_transactions (
               user_id, currency, free_delta, paid_delta, reason, source_type, source_id,
               balance_free_after, balance_paid_after, admin_username, created_at)
           VALUES (?, 'golden_dew', ?, 0, ?, 'battle_pass', ?, ?, 0, '', ?)''',
        (uid, -GOLDEN_PRICE_GOLDEN_DEW, '通行证 · 黄金之路', f'pass:{season_id()}', after, now_text),
    )
    conn.execute(
        'UPDATE battle_pass_progress SET golden_unlocked_at = ?, updated_at = ? WHERE user_id = ? AND season_id = ?',
        (now_text, now_text, uid, season_id()),
    )
    return {'golden_dew': after, 'price': GOLDEN_PRICE_GOLDEN_DEW}, None


def buy_xp(conn, user_id, *, now=None, source_key=''):
    """5 金露兑换 100 经验；返回 (payload, error)。

    固定汇率，不叠加黄金之路的 ×1.5——玩家付的是付费货币，换到的是确定数值。
    每次兑换写一条独立 source_key，重复调用是独立购买而不是幂等重放。
    """
    ensure_pass_schema(conn)
    uid = int(user_id)
    _, _, season_open = season_bounds(now)
    if not season_open:
        return None, '赛季已结束，无法兑换经验'
    row = conn.execute('SELECT golden_dew FROM users WHERE id = ?', (uid,)).fetchone()
    if row is None:
        return None, '账号不存在'
    balance = int(row['golden_dew'] or 0)
    if balance < XP_BUY_GOLDEN_DEW:
        return None, '金露不足'
    after = balance - XP_BUY_GOLDEN_DEW
    now_text = _now_iso(now)
    conn.execute('UPDATE users SET golden_dew = ? WHERE id = ?', (after, uid))
    conn.execute(
        '''INSERT INTO user_currency_transactions (
               user_id, currency, free_delta, paid_delta, reason, source_type, source_id,
               balance_free_after, balance_paid_after, admin_username, created_at)
           VALUES (?, 'golden_dew', ?, 0, ?, 'battle_pass', ?, ?, 0, '', ?)''',
        (
            uid, -XP_BUY_GOLDEN_DEW, '通行证 · 金露兑换经验',
            f'pass:{season_id()}', after, now_text,
        ),
    )
    key = str(source_key or '').strip() or (
        f'golden_xp:{season_id()}:{now_text}:{uuid.uuid4().hex}'
    )
    result = _apply_xp(
        conn, uid, XP_BUY_AMOUNT,
        source='golden', source_key=key, multiplier=1.0, now=now,
    )
    if not result.get('applied'):
        # 台账冲突（理论上不会发生）：把金露退回去，避免白扣。
        conn.execute('UPDATE users SET golden_dew = ? WHERE id = ?', (balance, uid))
        return None, '兑换失败，请重试'
    return {
        'golden_dew': after,
        'cost': XP_BUY_GOLDEN_DEW,
        'xp_gained': int(result['xp']),
        'xp_total': int(result['xp_total']),
        'xp_before': int(result['xp_total']) - int(result['xp']),
        'level_before': int(result['level_before']),
        'level_after': int(result['level_after']),
    }, None


def _claimed_levels(conn, user_id, track):
    rows = conn.execute(
        'SELECT level FROM battle_pass_claims WHERE user_id = ? AND season_id = ? AND track = ?',
        (int(user_id), season_id(), track),
    ).fetchall()
    return sorted(int(row['level']) for row in rows)


def _grant_cosmetic(conn, user_id, kind, item_id, now_text):
    if not item_id:
        return
    conn.execute(
        '''INSERT OR IGNORE INTO battle_pass_cosmetics
           (user_id, kind, item_id, acquired_source, acquired_at)
           VALUES (?, ?, ?, 'battle_pass', ?)''',
        (int(user_id), kind, item_id, now_text),
    )
    if kind == 'title':
        ensure_pass_titles(conn)
        conn.execute(
            '''INSERT OR IGNORE INTO user_titles
               (user_id, title_id, acquired_source, acquired_ref, acquired_at)
               VALUES (?, ?, 'battle_pass', ?, ?)''',
            (int(user_id), item_id, f'pass:{season_id()}', now_text),
        )
    elif kind == 'card_skin':
        # 通行证皮肤尚未进 card_skins 目录时只记账，目录上线后自动可用。
        try:
            from card_skins import SKIN_BY_ID
            known = item_id in SKIN_BY_ID
        except Exception:
            known = False
        if known:
            conn.execute(
                '''INSERT OR IGNORE INTO user_card_skins
                   (user_id, skin_id, acquired_source, acquired_ref, acquired_at)
                   VALUES (?, ?, 'battle_pass', ?, ?)''',
                (int(user_id), item_id, f'pass:{season_id()}', now_text),
            )
    elif kind == 'player_skin':
        try:
            from player_skins import PLAYER_SKIN_BY_ID
            known = item_id in PLAYER_SKIN_BY_ID
        except Exception:
            known = False
        if known:
            conn.execute(
                '''INSERT OR IGNORE INTO user_player_skins
                   (user_id, skin_id, acquired_source, acquired_ref, acquired_at)
                   VALUES (?, ?, 'battle_pass', ?, ?)''',
                (int(user_id), item_id, f'pass:{season_id()}', now_text),
            )
    elif kind == 'background':
        background_kind, definition = background_entry(item_id)
        if definition is not None:
            conn.execute(
                '''INSERT OR IGNORE INTO user_backgrounds
                   (user_id, kind, background_id, acquired_source, acquired_ref, acquired_at)
                   VALUES (?, ?, ?, 'battle_pass', ?, ?)''',
                (int(user_id), background_kind, item_id, f'pass:{season_id()}', now_text),
            )


def _grant_reward(conn, user_id, reward, *, now_text):
    """发奖；返回实际入账描述（用于回执与测试）。"""
    uid = int(user_id)
    kind = reward.get('kind')
    amount = int(reward.get('amount') or 0)
    item_id = str(reward.get('item_id') or '')
    granted = {'kind': kind, 'amount': amount, 'item_id': item_id}
    if kind == 'dew' and amount > 0:
        row = conn.execute('SELECT thorn_dew_free FROM users WHERE id = ?', (uid,)).fetchone()
        before = int(row['thorn_dew_free'] or 0) if row is not None else 0
        after = before + amount
        conn.execute('UPDATE users SET thorn_dew_free = ? WHERE id = ?', (after, uid))
        conn.execute(
            '''INSERT INTO user_currency_transactions (
                   user_id, currency, free_delta, paid_delta, reason, source_type, source_id,
                   balance_free_after, balance_paid_after, admin_username, created_at)
               VALUES (?, 'thorn_dew', ?, 0, ?, 'battle_pass', ?, ?, 0, '', ?)''',
            (uid, amount, f'通行证 · 第{reward.get("level")}级', f'pass:{season_id()}:lv{reward.get("level")}',
             after, now_text),
        )
    elif kind == 'golden_dew' and amount > 0:
        row = conn.execute('SELECT golden_dew FROM users WHERE id = ?', (uid,)).fetchone()
        before = int(row['golden_dew'] or 0) if row is not None else 0
        after = before + amount
        conn.execute('UPDATE users SET golden_dew = ? WHERE id = ?', (after, uid))
        conn.execute(
            '''INSERT INTO user_currency_transactions (
                   user_id, currency, free_delta, paid_delta, reason, source_type, source_id,
                   balance_free_after, balance_paid_after, admin_username, created_at)
               VALUES (?, 'golden_dew', ?, 0, ?, 'battle_pass', ?, ?, 0, '', ?)''',
            (uid, amount, f'通行证 · 第{reward.get("level")}级', f'pass:{season_id()}:lv{reward.get("level")}',
             after, now_text),
        )
    elif kind == 'shield_card' and amount > 0:
        conn.execute(
            'UPDATE users SET rank_shield_cards = COALESCE(rank_shield_cards, 0) + ? WHERE id = ?',
            (amount, uid),
        )
    elif kind == 'double_card' and amount > 0:
        conn.execute(
            'UPDATE users SET rank_double_cards = COALESCE(rank_double_cards, 0) + ? WHERE id = ?',
            (amount, uid),
        )
    elif kind == 'ticket' and amount > 0:
        # 通行证门票允许溢出上限：直接加库存，不走 leisure_ticket.grant_tickets 的封顶逻辑。
        import leisure_ticket
        leisure_ticket.ensure_ticket_columns(conn)
        conn.execute(
            'UPDATE users SET leisure_tickets = COALESCE(leisure_tickets, 0) + ? WHERE id = ?',
            (amount, uid),
        )
    elif kind in ('title', 'card_skin', 'player_skin', 'background'):
        _grant_cosmetic(conn, uid, kind, item_id, now_text)
    return granted


def claim(conn, user_id, track, level, *, now=None):
    """领取某一格奖励；返回 (payload, error)。"""
    ensure_pass_schema(conn)
    uid = int(user_id)
    track_key = str(track or '').strip()
    if track_key not in TRACKS:
        return None, '未知轨道'
    try:
        lv = int(level)
    except (TypeError, ValueError):
        return None, '等级无效'
    reward = reward_for(lv, track_key)
    if reward is None:
        return None, '等级无效'
    current = current_level(conn, uid)
    if lv > current:
        return None, '等级不足'
    if track_key == TRACK_GOLDEN and not golden_active(conn, uid):
        return None, '需要先解锁黄金之路'
    already = conn.execute(
        '''SELECT 1 FROM battle_pass_claims
           WHERE user_id = ? AND season_id = ? AND track = ? AND level = ? LIMIT 1''',
        (uid, season_id(), track_key, lv),
    ).fetchone()
    if already is not None:
        return None, '已经领取过了'
    now_text = _now_iso(now)
    granted = _grant_reward(conn, uid, reward, now_text=now_text)
    conn.execute(
        '''INSERT INTO battle_pass_claims
           (user_id, season_id, track, level, reward_json, claimed_at)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (uid, season_id(), track_key, lv,
         json.dumps(granted, ensure_ascii=False, separators=(',', ':')), now_text),
    )
    return {
        'level': lv, 'track': track_key, 'reward': granted,
        'xp_total': xp_total(conn, uid),
    }, None


def claimable_levels(conn, user_id):
    """返回两条轨道可领（已达标、未领）的等级列表。"""
    ensure_pass_schema(conn)
    uid = int(user_id)
    current = current_level(conn, uid)
    golden = golden_active(conn, uid)
    out = {TRACK_FREE: [], TRACK_GOLDEN: []}
    for track in TRACKS:
        if track == TRACK_GOLDEN and not golden:
            continue
        claimed = set(_claimed_levels(conn, uid, track))
        for lv in range(1, current + 1):
            if lv not in claimed:
                out[track].append(lv)
    return out


# --------------------------------------------------------------------------
# 对外视图
# --------------------------------------------------------------------------

def state_payload(conn, user_id, *, now=None):
    ensure_pass_schema(conn)
    uid = int(user_id)
    row = _ensure_progress(conn, uid, now)
    total = int(row['xp_total'] or 0)
    level = level_for_xp(total)
    golden = bool(row['golden_unlocked_at'])
    claimed = {track: _claimed_levels(conn, uid, track) for track in TRACKS}
    claimed_sets = {track: set(claimed[track]) for track in TRACKS}

    def _track_view(track):
        entries = []
        visible_max = max(PASS_MAX_LEVEL, level)
        for lv in range(1, visible_max + 1):
            reward = reward_for(lv, track)
            entries.append({
                'level': lv,
                'reward': reward,
                'text': reward_amount_text(lv, track),
                'type': reward_type_label(reward),
                'icon': reward_icon_url(reward),
                'unlocked': lv <= level,
                'claimed': lv in claimed_sets[track],
                'claimable': lv <= level and lv not in claimed_sets[track] and (track == TRACK_FREE or golden),
            })
        return {
            'track': track,
            'label': TRACK_LABELS[track],
            'entries': entries,
            'claimed_count': len(claimed[track]),
            'claimable_count': sum(1 for entry in entries if entry['claimable']),
        }

    start, end, active = season_bounds(now)
    balance = conn.execute(
        'SELECT golden_dew, thorn_dew_free FROM users WHERE id = ?', (uid,)
    ).fetchone()
    tracks = {track: _track_view(track) for track in TRACKS}
    return {
        'season_id': season_id(),
        'season_start': start.isoformat(timespec='seconds'),
        'season_end': end.isoformat(timespec='seconds'),
        'season_active': bool(active),
        'xp_per_level': XP_PER_LEVEL,
        'max_level': max(PASS_MAX_LEVEL, level),
        'base_max_level': PASS_MAX_LEVEL,
        'overflow_rewards': {track: reward_amount_text(PASS_MAX_LEVEL + 1, track) for track in TRACKS},
        'xp_total': total,
        'level': level,
        'level_raw': level,
        'xp_into_level': xp_into_level(total),
        'golden': golden,
        'golden_price': GOLDEN_PRICE_GOLDEN_DEW,
        'xp_buy_cost': XP_BUY_GOLDEN_DEW,
        'xp_buy_amount': XP_BUY_AMOUNT,
        'golden_perks': {
            'xp_multiplier': GOLDEN_XP_MULTIPLIER,
            'dew_multiplier': GOLDEN_DEW_MULTIPLIER,
            'rank_special_bonus': GOLDEN_RANK_SPECIAL_BONUS,
            'checkin_shield_cards': GOLDEN_CHECKIN_SHIELD_CARDS,
            'checkin_double_cards': GOLDEN_CHECKIN_DOUBLE_CARDS,
        },
        'golden_dew': int(balance['golden_dew'] or 0) if balance is not None else 0,
        'thorn_dew_free': int(balance['thorn_dew_free'] or 0) if balance is not None else 0,
        'claimable': {track: [e['level'] for e in tracks[track]['entries'] if e['claimable']]
                      for track in TRACKS},
        'story_week_used': _story_week_used(conn, uid, now),
        'story_weekly_triple_count': STORY_WEEKLY_TRIPLE_COUNT,
        'tracks': tracks,
    }


# --------------------------------------------------------------------------
# 管理端：经验查询与调整（控制台 account xp ...）
# --------------------------------------------------------------------------

XP_SOURCES = ('match', 'story', 'checkin', 'golden', 'admin')

XP_SOURCE_LABELS = {
    'match': '对局经验',
    'story': '爬塔经验',
    'checkin': '签到经验',
    'golden': '金露兑换',
    'admin': '管理调整',
}


def source_label(source):
    """经验来源的中文标签；未知来源原样返回。"""
    key = str(source or '').strip()
    return XP_SOURCE_LABELS.get(key, key or '-')


def normalize_source(source):
    key = str(source or '').strip().lower()
    return key if key in XP_SOURCES else ''


def xp_summary(conn, user_id, now=None):
    """控制台用：赛季经验总览（总量/等级/分来源合计）。"""
    ensure_pass_schema(conn)
    uid = int(user_id)
    progress = _ensure_progress(conn, uid, now)
    total = int(progress['xp_total'] or 0)
    rows = conn.execute(
        '''SELECT source, SUM(xp) AS total, COUNT(*) AS entries
           FROM battle_pass_xp_ledger
           WHERE user_id = ? AND season_id = ?
           GROUP BY source''',
        (uid, season_id()),
    ).fetchall()
    by_source = {key: {'xp': 0, 'entries': 0} for key in XP_SOURCES}
    for row in rows:
        key = str(row['source'] or '')
        by_source[key] = {'xp': int(row['total'] or 0), 'entries': int(row['entries'] or 0)}
    level = level_for_xp(total)
    return {
        'season_id': season_id(),
        'xp_per_level': XP_PER_LEVEL,
        'xp_total': total,
        'level': level,
        'level_display': level,
        'xp_into_level': xp_into_level(total),
        'golden': bool(progress['golden_unlocked_at']),
        'by_source': by_source,
    }


def adjust_xp(conn, user_id, delta, *, source='admin', reason='', admin_username='', now=None):
    """管理端增减通行证经验（正数发放、负数扣除），写经验台账。

    返回 (result, error)。扣除时不会把累计经验压到 0 以下。
    """
    ensure_pass_schema(conn)
    try:
        value = int(delta)
    except (TypeError, ValueError):
        return None, '数量必须是整数'
    if value == 0:
        return None, '调整数量不能为0'
    key = normalize_source(source)
    if not key:
        return None, f'未知经验来源：{source}'
    uid = int(user_id)
    progress = _ensure_progress(conn, uid, now)
    before = int(progress['xp_total'] or 0)
    after = max(0, before + value)
    applied = after - before
    if applied == 0:
        return None, '累计经验已是 0，无法再扣除'
    now_text = _now_iso(now)
    operator = (str(admin_username or 'console').strip() or 'console')[:24]
    source_key = f'admin:{operator}:{uuid.uuid4().hex}'
    conn.execute(
        '''INSERT INTO battle_pass_xp_ledger
           (user_id, season_id, source, source_key, base_xp, xp, multiplier, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 1.0, ?)''',
        (uid, season_id(), key, source_key, applied, applied, now_text),
    )
    conn.execute(
        'UPDATE battle_pass_progress SET xp_total = ?, updated_at = ? WHERE user_id = ? AND season_id = ?',
        (after, now_text, uid, season_id()),
    )
    return {
        'applied': applied,
        'requested': value,
        'source': key,
        'reason': str(reason or ''),
        'xp_total': after,
        'level_before': level_for_xp(before),
        'level_after': level_for_xp(after),
    }, ''


def list_xp_transactions(conn, user_id, limit=20, source=None):
    """控制台用：最近经验台账（可按来源过滤）。"""
    ensure_pass_schema(conn)
    uid = int(user_id)
    try:
        limit = max(1, min(200, int(limit or 20)))
    except (TypeError, ValueError):
        limit = 20
    sql = ('SELECT source, source_key, base_xp, xp, multiplier, created_at '
           'FROM battle_pass_xp_ledger WHERE user_id = ? AND season_id = ?')
    params = [uid, season_id()]
    key = normalize_source(source) if source else ''
    if key:
        sql += ' AND source = ?'
        params.append(key)
    sql += ' ORDER BY created_at DESC, rowid DESC LIMIT ?'
    params.append(limit)
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


XP_REWARD_LABELS = {
    'match': '对局经验到账',
    'story': '爬塔经验到账',
    'checkin': '签到经验到账',
    'admin': '管理调整',
}


def xp_reward_updates(conn, user_id, after_id=0, limit=20):
    """长期奖励接口用：游标之后的正向经验记录（按 id 递增）。

    after_id 为 None 表示客户端还没有游标（刚打开页面）：只回报最新游标，
    不回放历史记录。否则历史记录会在每批 20 条的翻页边界被当成新奖励，
    每次进主页都重播一遍动画。
    """
    ensure_pass_schema(conn)
    if after_id is None:
        row = conn.execute(
            'SELECT COALESCE(MAX(id), 0) FROM battle_pass_xp_ledger '
            'WHERE user_id = ? AND xp > 0',
            (int(user_id),),
        ).fetchone()
        return {'cursor': int(row[0] or 0), 'items': []}
    try:
        after = max(0, int(after_id or 0))
    except (TypeError, ValueError):
        after = 0
    try:
        limit = max(1, min(50, int(limit or 20)))
    except (TypeError, ValueError):
        limit = 20
    rows = conn.execute(
        'SELECT id, source, xp FROM battle_pass_xp_ledger '
        'WHERE user_id = ? AND id > ? AND xp > 0 ORDER BY id ASC LIMIT ?',
        (int(user_id), after, limit),
    ).fetchall()
    items = [
        {
            'id': int(row['id']),
            'amount': int(row['xp']),
            'source_type': str(row['source']),
            'reason': XP_REWARD_LABELS.get(str(row['source']), '通行证经验到账'),
        }
        for row in rows
    ]
    cursor = max([after] + [item['id'] for item in items])
    return {'cursor': cursor, 'items': items}


# 控制台入口：自建连接并提交（db 反向 import battle_pass，故延迟导入 db）

def admin_xp_summary(user_id, now=None):
    import db
    with db.get_db_connection() as conn:
        return xp_summary(conn, user_id, now)


def admin_list_xp_transactions(user_id, limit=20, source=None):
    import db
    with db.get_db_connection() as conn:
        return list_xp_transactions(conn, user_id, limit=limit, source=source)


def admin_adjust_xp(user_id, delta, *, source='admin', reason='', admin_username='console', now=None):
    """控制台增减经验：自建连接、提交事务，返回 (result, error)。"""
    import db
    with db.get_db_connection() as conn:
        result, error = adjust_xp(
            conn, user_id, delta, source=source, reason=reason,
            admin_username=admin_username, now=now,
        )
        if error:
            return None, error
        conn.commit()
        return result, ''
