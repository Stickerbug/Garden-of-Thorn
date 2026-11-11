# -*- coding: utf-8 -*-
"""故事模式通关奖励（设计 2026-09-26）。

分数 = 基础分 × 难度乘区 × SL 系数，1 分 = 1 荆露。

基础分：
- 每通过一个阶段 +100；通过全部 3 阶段额外 +100
- 每打一层精英 +30，每打一层小怪 +10
- 每 5 金币 +1（单局最多计入 400 分，防止囤金刷通关奖励），每有一张卡 +3，
  每有一个天赋 +5，每有一本附魔书 +10

乘区：
- 难度：easy 0.5 / normal 1.0 / hard 1.5 / lunatic 2.0
- SL 系数：手动读档或使用过重新开始本层为 1，否则 no SL 为 1.5
"""

import json
import math


DIFFICULTY_MULTIPLIERS = {
    'easy': 0.5,
    'normal': 1.0,
    'hard': 1.5,
    'lunatic': 2.0,
}
STORY_STAGES_TOTAL = 3
NO_SL_BONUS = 1.5
POINTS = {
    'stage': 100,
    'all_stages_bonus': 100,
    'elite': 30,
    'normal': 10,
    'gold_per': 5,
    'gold_points': 1,
    'card': 3,
    'talent': 5,
    'enchantment_book': 10,
}
# 金币分上限：400 分 = 2000 金币。防止玩家在通关前囤积/刷取金币放大荆露收益。
GOLD_SCORE_CAP = 400


def compute_score_breakdown(state, difficulty=None, load_count=0):
    """逐项拆分基础分，供通关结算动画与计分共用。"""
    state = state if isinstance(state, dict) else {}
    player = state.get('player') if isinstance(state.get('player'), dict) else {}
    completed = state.get('completed') is True
    stages = int(state.get('stage') or 1)
    completed_stages = max(0, stages if completed else stages - 1)
    all_stages = 1 if completed and stages >= STORY_STAGES_TOTAL else 0
    normals = int(state.get('normal_battles') or 0)
    encounter = state.get('encounter_history') if isinstance(state.get('encounter_history'), dict) else {}
    elite_history = encounter.get('elite') if isinstance(encounter.get('elite'), dict) else {}
    elites = sum(len(v) for v in elite_history.values() if isinstance(v, list))
    gold = int(player.get('gold') or 0)
    deck = player.get('deck') or []
    talents = player.get('relics') or player.get('talents') or []
    books = player.get('enchantment_books') or state.get('enchantment_books') or state.get('books') or []

    items = {
        'stages': {'count': completed_stages, 'unit': POINTS['stage']},
        'all_stages_bonus': {'count': all_stages, 'unit': POINTS['all_stages_bonus']},
        'normal_battles': {'count': normals, 'unit': POINTS['normal']},
        'elite_battles': {'count': elites, 'unit': POINTS['elite']},
        'gold': {'count': gold, 'unit': POINTS['gold_per']},
        'cards': {'count': len(deck), 'unit': POINTS['card']},
        'relics': {'count': len(talents), 'unit': POINTS['talent']},
        'enchantment_books': {'count': len(books), 'unit': POINTS['enchantment_book']},
    }
    for item in items.values():
        if item is items['gold']:
            item['points'] = min(
                GOLD_SCORE_CAP,
                (item['count'] // item['unit']) * POINTS['gold_points'],
            )
        else:
            item['points'] = item['count'] * item['unit']
    difficulty_mult = DIFFICULTY_MULTIPLIERS.get(str(difficulty or state.get('difficulty') or 'normal').lower(), 1.0)
    sl_mult = compute_multiplier(load_count)
    return {
        'items': items,
        'base_score': sum(item['points'] for item in items.values()),
        'total_score': int(math.floor(sum(item['points'] for item in items.values()) * difficulty_mult * sl_mult)),
        'difficulty_multiplier': difficulty_mult,
        'sl_multiplier': sl_mult,
        'reward_multiplier': difficulty_mult * sl_mult,
        'load_count': max(0, int(load_count or 0)),
    }


def compute_base_score(state):
    """从旅程终态统计基础分（与结算拆分共用同一实现）。"""
    return compute_score_breakdown(state)['base_score']


def compute_multiplier(load_count):
    """SL 只区分是否用过重新开始本层，不再按次数额外递减。"""
    load_count = max(0, int(load_count or 0))
    return NO_SL_BONUS if load_count == 0 else 1.0


def compute_score(state, difficulty, load_count):
    base = compute_base_score(state)
    difficulty_mult = DIFFICULTY_MULTIPLIERS.get(str(difficulty or '').lower(), 1.0)
    total = base * difficulty_mult * compute_multiplier(load_count)
    return int(math.floor(total)), int(base)


def completed_stage_count(state):
    """已通过幕数，与通关计分中的完成阶段口径一致。"""
    state = state if isinstance(state, dict) else {}
    stages = max(0, int(state.get('stage') or 1))
    return stages if state.get('completed') is True else max(0, stages - 1)


def _ensure_ledger_schema(conn):
    """建通关台账表并补齐新增列；重复执行无副作用。"""
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS story_reward_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            base_score INTEGER NOT NULL,
            total_score INTEGER NOT NULL,
            load_count INTEGER NOT NULL,
            bank_cleared INTEGER NOT NULL DEFAULT 0,
            dev_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        ''',
    )
    # 旧库补列（#331 上线时生产库已存在该表）
    try:
        conn.execute('ALTER TABLE story_reward_ledger ADD COLUMN dev_used INTEGER NOT NULL DEFAULT 0')
    except Exception:
        pass  # 列已存在
    ensure_story_clear_animation_schema(conn)


def settle_story_clear_conn(conn, *, user_id, run_id, state):
    """通关事务内：清银行 → 算分 → 发荆露 → 记账。

    conn 由调用方持有 IMMEDIATE 事务。
    开发模式（#331）：本次旅程用过任何 dev_* 操作则不发荆露——开发模式可以
    直接改金币/塞卡/跳层，正常算分等于无限刷荆露。
    幂等：同一 (run_id, user_id) 已有台账时直接返回首次结算结果，不再发钱。
    """
    from db import _thorn_dew_now  # noqa: F401  (保持与 db 模块一致的时间源)

    state = state if isinstance(state, dict) else {}
    difficulty = str(state.get('difficulty') or 'normal')
    player = state.get('player') if isinstance(state.get('player'), dict) else {}

    # 0) 幂等守卫：先确保台账表存在，再检查本旅程是否已经结算过。
    #    正常流程由 commit_story_run_action 的“首次通关”判断拦截；这里兜住
    #    直接调用、旧数据或未来新增调用方，避免重复发放荆露/金露。
    _ensure_ledger_schema(conn)
    existing = conn.execute(
        '''SELECT difficulty, base_score, total_score, load_count, bank_cleared,
                  dev_used, golden_dew_reward, completed_stages, golden_multiplier,
                  dew_gain_multiplier, xp_gain
           FROM story_reward_ledger
           WHERE run_id = ? AND user_id = ?
           ORDER BY id DESC LIMIT 1''',
        (str(run_id or ''), int(user_id)),
    ).fetchone()
    if existing is not None:
        return {
            'total': int(existing['total_score'] or 0),
            'base': int(existing['base_score'] or 0),
            'difficulty': str(existing['difficulty'] or difficulty),
            'load_count': int(existing['load_count'] or 0),
            'bank_cleared': int(existing['bank_cleared'] or 0),
            'dev_used': bool(int(existing['dev_used'] or 0)),
            'golden_dew_reward': int(existing['golden_dew_reward'] or 0),
            'completed_stages': int(existing['completed_stages'] or 0),
            'golden_multiplier': float(existing['golden_multiplier'] or 1),
            'dew_gain_multiplier': float(existing['dew_gain_multiplier'] or 1),
            'xp_gain': int(existing['xp_gain'] or 0),
        }

    # 1) 银行存款清零（设计：做了这个系统后清除玩家在银行的存款）
    row = conn.execute(
        'SELECT deposit FROM story_bank_accounts WHERE user_id = ?', (int(user_id),),
    ).fetchone()
    bank_before = int(row['deposit'] or 0) if row is not None else 0
    if bank_before > 0:
        conn.execute('UPDATE story_bank_accounts SET deposit = 0 WHERE user_id = ?', (int(user_id),))

    # 2) SL：手动读档与“重新开始本层”动作都视为使用过 SL。
    run_row = conn.execute(
        'SELECT manual_load_count FROM story_runs WHERE id = ?', (str(run_id or ''),),
    ).fetchone()
    load_count = int(run_row['manual_load_count'] or 0) if run_row is not None else 0
    restart_row = conn.execute(
        "SELECT COUNT(*) AS n FROM story_run_actions WHERE run_id = ? AND action_type = 'restart_floor'",
        (str(run_id or ''),),
    ).fetchone()
    load_count += int(restart_row['n'] or 0) if restart_row is not None else 0

    # 2.5) 开发模式检测：旅程动作日志里出现过 dev_* 操作
    dev_row = conn.execute(
        "SELECT COUNT(*) AS n FROM story_run_actions "
        "WHERE run_id = ? AND substr(action_type, 1, 4) = 'dev_'",
        (str(run_id or ''),),
    ).fetchone()
    dev_used = int(dev_row['n'] or 0) > 0 if dev_row is not None else False

    # 3) 分数与荆露（开发模式不发）
    total, base = compute_score(state, difficulty, load_count)
    # 通行证经验按「旅程分数」算，取全局倍率/开发模式清零之前的原始分。
    xp_score = int(total)
    difficulty_mult = DIFFICULTY_MULTIPLIERS.get(str(difficulty or '').lower(), 1.0)
    from db import dew_gain_multiplier_conn, scale_dew_gain_conn
    dew_gain_multiplier = dew_gain_multiplier_conn(conn)
    if dev_used:
        total = 0
    if total > 0:
        # 荆露获取全局倍率（控制台调控）
        total = scale_dew_gain_conn(conn, total)
        # 通行证 · 黄金之路：荆露收益 ×1.5（金露奖励不参与该倍率）
        try:
            import battle_pass as _bp
            total = _bp.apply_golden_dew(conn, user_id, total)
        except Exception:
            pass
    if total > 0:
        user_row = conn.execute(
            'SELECT thorn_dew_free, thorn_dew_paid FROM users WHERE id = ?', (int(user_id),),
        ).fetchone()
        if user_row is not None:
            free = int(user_row['thorn_dew_free'] or 0) + total
            paid = int(user_row['thorn_dew_paid'] or 0)
            conn.execute('UPDATE users SET thorn_dew_free = ? WHERE id = ?', (free, int(user_id)))
            conn.execute(
                '''
                INSERT INTO user_currency_transactions
                    (user_id, currency, free_delta, paid_delta, reason, source_type, source_id,
                     balance_free_after, balance_paid_after, admin_username, created_at)
                VALUES (?, 'thorn_dew', ?, 0, ?, 'story_clear', ?, ?, ?, '', datetime('now'))
                ''',
                (
                    int(user_id), total,
                    f'故事通关奖励 难度{difficulty}×{difficulty_mult:g} 基础{base} SL×{compute_multiplier(load_count):g}',
                    f'story:{run_id}',
                    free, paid,
                ),
            )

    # 3.5) 通行证经验（2026-11-11）：Min{1000, ceil(Score/5)}；每周前 3 次爬塔 ×3。
    # 开发模式（dev_*）不发，避免跳层刷经验。
    xp_gain = 0
    xp_level = 0
    if not dev_used and xp_score > 0:
        try:
            import battle_pass as _bp
            xp_result = _bp.grant_story_xp(conn, user_id, run_id=run_id, score=xp_score)
            if xp_result.get('applied'):
                xp_gain = int(xp_result.get('xp') or 0)
                xp_level = int(xp_result.get('level_after') or 0)
        except Exception as exc:
            print(f'[story] battle pass xp failed: {type(exc).__name__}: {exc}', flush=True)

    # 4) 金露：完成幕数 × 难度系数 × 无 SL 奖励系数（不经过荆露全局倍率）。
    completed_stages = completed_stage_count(state)
    no_sl_multiplier = NO_SL_BONUS if load_count == 0 else 1.0
    golden_multiplier = difficulty_mult * no_sl_multiplier
    golden_reward = int(math.floor(completed_stages * golden_multiplier))
    if dev_used:
        golden_reward = 0
    if golden_reward > 0:
        golden_row = conn.execute(
            'SELECT golden_dew FROM users WHERE id = ?', (int(user_id),),
        ).fetchone()
        if golden_row is not None:
            golden_after = int(golden_row['golden_dew'] or 0) + golden_reward
            conn.execute('UPDATE users SET golden_dew = ? WHERE id = ?', (golden_after, int(user_id)))
            conn.execute(
                '''
                INSERT INTO user_currency_transactions
                    (user_id, currency, free_delta, paid_delta, reason, source_type, source_id,
                     balance_free_after, balance_paid_after, admin_username, created_at)
                VALUES (?, 'golden_dew', ?, 0, ?, 'story_clear_golden_dew', ?, ?, ?, '', datetime('now'))
                ''',
                (
                    int(user_id), golden_reward,
                    f'故事通关金露 幕数{completed_stages} ×难度{difficulty_mult:g} ×无SL奖励{no_sl_multiplier:g}',
                    f'story:{run_id}', golden_after, 0,
                ),
            )

    # 5) 分数与金露留档（神秘人物事件用：伤害 = 本次得分）
    #    台账表与新增列已在函数入口由 _ensure_ledger_schema 建好。
    conn.execute(
        '''
        INSERT INTO story_reward_ledger
            (user_id, run_id, difficulty, base_score, total_score, load_count,
             bank_cleared, dev_used, golden_dew_reward, completed_stages, golden_multiplier,
             dew_gain_multiplier, xp_gain)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            int(user_id), str(run_id or ''), difficulty,
            int(base), int(total), int(load_count), 1 if bank_before > 0 else 0,
            1 if dev_used else 0, golden_reward, completed_stages, golden_multiplier,
            dew_gain_multiplier, int(xp_gain),
        ),
    )
    return {
        'total': total,
        'base': base,
        'difficulty': difficulty,
        'load_count': load_count,
        'bank_cleared': bank_before,
        'dev_used': dev_used,
        'golden_dew_reward': golden_reward,
        'completed_stages': completed_stages,
        'golden_multiplier': golden_multiplier,
        'dew_gain_multiplier': dew_gain_multiplier,
        'xp_gain': xp_gain,
        'xp_level': xp_level,
    }


def ensure_story_clear_animation_schema(conn):
    """补充通关动画已读时间与奖励结算字段；重复执行无副作用。"""
    for statement in (
        'ALTER TABLE story_reward_ledger ADD COLUMN animation_seen_at TEXT',
        'ALTER TABLE story_reward_ledger ADD COLUMN golden_dew_reward INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE story_reward_ledger ADD COLUMN completed_stages INTEGER NOT NULL DEFAULT 0',
        'ALTER TABLE story_reward_ledger ADD COLUMN golden_multiplier REAL NOT NULL DEFAULT 1',
        'ALTER TABLE story_reward_ledger ADD COLUMN dew_gain_multiplier REAL',
        'ALTER TABLE story_reward_ledger ADD COLUMN xp_gain INTEGER NOT NULL DEFAULT 0',
    ):
        try:
            conn.execute(statement)
        except Exception:
            pass  # 列已存在


def claim_story_clear_settlement_animation(conn, user_id, run_id):
    """原子认领一次通关结算播放，避免刷新和多端重复播放。"""
    ensure_story_clear_animation_schema(conn)
    cursor = conn.execute(
        "UPDATE story_reward_ledger SET animation_seen_at = datetime('now') "
        'WHERE run_id = ? AND user_id = ? AND animation_seen_at IS NULL',
        (str(run_id), int(user_id)),
    )
    conn.commit()
    return cursor.rowcount == 1
