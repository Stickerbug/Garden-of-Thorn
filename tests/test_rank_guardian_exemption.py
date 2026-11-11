# -*- coding: utf-8 -*-
"""升段局/0分局段位差规则的例外：总榜前十之间互相对战不受限制。

规则本体在 app._rank_match_block_reason；这里用打桩把段位分和榜单固定住，
不依赖真实数据库内容。
"""

import app as gtn

import rank_system


def _player(user_id, tier, points):
    state = (int(tier), int(points))
    player = {'user_id': user_id, 'is_registered_user': True, 'rank_tier': tier}
    # _rank_state_of_player 会查库，这里直接按 user_id 返回固定状态
    player['__state'] = state
    return player


def _patch_states(monkeypatch, mapping):
    def fake(_player):
        return mapping[int(_player.get('user_id') or 0)]

    monkeypatch.setattr(gtn, '_rank_state_of_player', fake)


def _patch_guardians(monkeypatch, ids):
    calls = {'n': 0}

    def fake():
        calls['n'] += 1
        return frozenset(int(i) for i in ids)

    monkeypatch.setattr(gtn, 'rank_guardian_ids', fake)
    return calls


def _at_cap(tier):
    return rank_system.rank_cap(tier)


def test_promotion_match_against_much_lower_rank_is_blocked(monkeypatch):
    """基线：升段局（段位分打满）遇到低 4 个小段的对手 → 拦截。"""
    _patch_states(monkeypatch, {1: (20, _at_cap(20)), 2: (16, 5)})
    _patch_guardians(monkeypatch, [])
    reason = gtn._rank_match_block_reason(_player(1, 20, _at_cap(20)), _player(2, 16, 5))
    assert reason == 'rank_risk_gap'


def test_three_subtier_gap_is_still_allowed(monkeypatch):
    """边界：正好低 3 个小段仍然可以打（规则是「超过 3 小段」）。"""
    _patch_states(monkeypatch, {1: (20, _at_cap(20)), 2: (17, 5)})
    _patch_guardians(monkeypatch, [])
    assert gtn._rank_match_block_reason(_player(1, 20, _at_cap(20)), _player(2, 17, 5)) is None


def test_zero_point_match_against_much_lower_rank_is_blocked(monkeypatch):
    """0 分局同样受限制。"""
    _patch_states(monkeypatch, {1: (20, 0), 2: (15, 5)})
    _patch_guardians(monkeypatch, [])
    assert gtn._rank_match_block_reason(_player(1, 20, 0), _player(2, 15, 5)) == 'rank_risk_gap'


def test_top_ten_may_fight_each_other_regardless_of_gap(monkeypatch):
    """例外：双方都在总榜前十 → 段位差再大也放行。"""
    _patch_states(monkeypatch, {1: (20, _at_cap(20)), 2: (16, 5)})
    _patch_guardians(monkeypatch, [1, 2])
    assert gtn._rank_match_block_reason(_player(1, 20, _at_cap(20)), _player(2, 16, 5)) is None


def test_exemption_needs_both_sides_in_top_ten(monkeypatch):
    """只有一方在前十 → 不豁免，仍按原规则拦截。"""
    _patch_states(monkeypatch, {1: (20, _at_cap(20)), 2: (16, 5)})
    _patch_guardians(monkeypatch, [1])
    assert gtn._rank_match_block_reason(_player(1, 20, _at_cap(20)), _player(2, 16, 5)) == 'rank_risk_gap'


def test_exemption_also_applies_from_the_lower_side(monkeypatch):
    """低段前十主动邀请高段前十：同样放行（两个方向都不拦）。"""
    _patch_states(monkeypatch, {1: (20, _at_cap(20)), 2: (16, 5)})
    _patch_guardians(monkeypatch, [1, 2])
    assert gtn._rank_match_block_reason(_player(2, 16, 5), _player(1, 20, _at_cap(20))) is None


def test_guardian_list_failure_falls_back_to_restriction(monkeypatch):
    """榜单查询失败 → 白名单为空 → 退回原限制（不会因为异常放开规则）。"""
    _patch_states(monkeypatch, {1: (20, _at_cap(20)), 2: (16, 5)})

    def boom(**_kwargs):
        raise RuntimeError('db down')

    monkeypatch.setattr(gtn.db_module, 'list_leaderboard_ids', boom)
    monkeypatch.setattr(gtn, '_RANK_GUARDIAN_CACHE', {'ts': 0.0, 'ids': frozenset()})
    assert gtn.rank_guardian_ids() == frozenset()
    assert gtn._rank_match_block_reason(_player(1, 20, _at_cap(20)), _player(2, 16, 5)) == 'rank_risk_gap'


def test_guardian_ids_are_cached(monkeypatch):
    """白名单结果按 TTL 缓存，不在每次判断时查库。"""
    calls = {'n': 0}

    def fake_ids(**_kwargs):
        calls['n'] += 1
        return {7, 8}

    monkeypatch.setattr(gtn.db_module, 'list_leaderboard_ids', fake_ids)
    monkeypatch.setattr(gtn, '_RANK_GUARDIAN_CACHE', {'ts': 0.0, 'ids': frozenset()})
    assert gtn.rank_guardian_ids() == frozenset({7, 8})
    assert gtn.rank_guardian_ids() == frozenset({7, 8})
    assert calls['n'] == 1


def test_guardian_limit_is_read_from_config():
    """默认前十，可用环境变量调整（GTN_RANK_GUARDIAN_LIMIT）。"""
    assert gtn.RANK_GUARDIAN_LIMIT == 10
