"""反馈 #183：致臻化境（``enchant_amulet``）转化护身符时不能丢牌上的修饰。

以前这里 ``card.pop('modifiers', None)`` 把整段修饰删掉，[钟爱] 标记会凭空消失。
"""

from pathlib import Path

from story_engine import _queue_deck_operation, apply_story_action
from story_mode import build_initial_story_state

SEED = 'feedback-183-perfection'


def _state_with_amulet():
    state = build_initial_story_state(SEED)
    state, _ = apply_story_action(
        state,
        'start_journey',
        {'biome': 'garden', 'difficulty': 'normal'},
        SEED,
    )
    deck = state['player']['deck']
    amulet = next(card for card in deck if card.get('def_id') == 'amulet')
    amulet.setdefault('modifiers', {})['favorite'] = 1
    return state, amulet


def test_perfection_transform_keeps_favorite_modifier():
    state, amulet = _state_with_amulet()
    operation = _queue_deck_operation(
        state,
        'enchant_amulet',
        'perfection',
        1,
        [amulet['instance_id']],
    )
    assert operation is not None

    state, _events = apply_story_action(
        state,
        'resolve_deck_operation',
        {'selected_card_ids': [amulet['instance_id']]},
        SEED,
    )

    transformed = next(
        card for card in state['player']['deck']
        if card.get('instance_id') == amulet['instance_id']
    )
    assert transformed['def_id'] == 'enchanted_amulet'
    assert transformed.get('modifiers', {}).get('favorite') == 1


def test_perfection_transform_still_rejects_non_starter():
    """2026-10-26改版：附魔对象是初始牌（护身符/魔法基本/更快），basic仍被拒。"""
    state, _amulet = _state_with_amulet()
    basic = next(card for card in state['player']['deck'] if card.get('def_id') == 'basic')
    _queue_deck_operation(state, 'enchant_amulet', 'perfection', 1, [basic['instance_id']])

    try:
        apply_story_action(
            state,
            'resolve_deck_operation',
            {'selected_card_ids': [basic['instance_id']]},
            SEED,
        )
    except Exception as exc:  # StoryActionError
        assert '致臻化境只能选择初始牌' in str(exc)
    else:  # pragma: no cover - 不允许通过
        raise AssertionError('非初始牌不应被致臻化境转化')


def test_perfection_enchants_starter_per_character():
    """2026-10-26改版：护身符/魔法基本/更快按角色各自转为附魔版。"""
    from story_content import STORY_CARDS
    from story_engine import _gain_relic

    cases = {
        'common_flower': 'enchanted_amulet',
        'orbiter': 'enchanted_faster',
        'mage': 'enchanted_magic_basic',
    }
    for character_id, expected in cases.items():
        state = build_initial_story_state(f'perf-{character_id}', character_id)
        state, _ = apply_story_action(
            state, 'start_journey', {'biome': 'garden', 'difficulty': 'normal'},
            f'perf-{character_id}',
        )
        _gain_relic(state, 'perfection', f'perf-{character_id}', [])
        operations = state.get('pending_deck_operations') or []
        assert operations, character_id
        operation = operations[0]
        candidates = operation.get('candidate_ids') or []
        assert candidates, character_id
        state, _events = apply_story_action(
            state, 'resolve_deck_operation',
            {'selected_card_ids': [candidates[0]]},
            f'perf-{character_id}',
        )
        assert expected in [c.get('def_id') for c in state['player']['deck']]
        assert expected in STORY_CARDS
