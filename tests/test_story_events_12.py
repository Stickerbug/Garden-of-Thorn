from story_events_12 import STORY_EVENTS_12, event_12_action_hint
from story_engine import _resolve_new_event_12
from story_mode import build_initial_story_state


def _scale_run(deck_size=2, health=40):
    state = build_initial_story_state('run-scale', 'common_flower')
    player = state['player']
    player['health'] = health
    player['max_health'] = 80
    player['deck'] = [
        {
            'def_id': 'basic' if index % 2 == 0 else 'bone',
            'instance_id': f'scale-{index}',
            'upgraded': True,
            'upgrade_level': 1,
        }
        for index in range(deck_size)
    ]
    return state


def test_all_18_workbook_events_are_defined():
    assert len(STORY_EVENTS_12) == 18
    assert set(STORY_EVENTS_12) == {
        'crusher_machine', 'library', 'enchanter', 'midas_coin',
        'world_tree_branch', 'endless_marathon', 'herald', 'strange_anvil',
        'bbq', 'titan', 'deep_branch', 'withered_trunk', 'card_machine',
        'secret_passage', 'card_giftpack', 'talent_lottery',
        'scale_judgement', 'bank',
    }


def test_new_events_carry_intro_copy_and_split_option_descriptions():
    for event_id, definition in STORY_EVENTS_12.items():
        assert definition.get('body') and definition['body'].get('zh'), event_id
        assert definition.get('speaker') and definition['speaker'].get('zh'), event_id
        for option in definition.get('options') or ():
            option_id = str(option.get('id') or '')
            if option_id == 'leave':
                continue
            assert option.get('label') and option['label'].get('zh'), (
                f'{event_id}:{option_id}'
            )
            assert option.get('description') and option['description'].get('zh'), (
                f'{event_id}:{option_id}'
            )


def test_option_ids_are_unique_and_leave_has_hint():
    for event_id, definition in STORY_EVENTS_12.items():
        ids = [str(option['id']) for option in definition['options']]
        assert len(ids) == len(set(ids)), event_id
        for option in definition['options']:
            if str(option['id']) == 'leave':
                assert event_12_action_hint(event_id, 'leave') == 'leave'
            else:
                assert event_12_action_hint(event_id, str(option['id']))


def test_action_hint_unknown_is_empty():
    assert event_12_action_hint('missing', 'x') == ''


def test_scale_judgement_offers_a_balance_option_matching_the_workbook():
    options = STORY_EVENTS_12['scale_judgement']['options']
    assert [option['id'] for option in options] == [
        'scale_you', 'scale_cards', 'scale_balance',
    ]
    balance = options[2]
    assert balance['label']['zh'] == '平衡'
    assert '随机降级一张牌' in balance['description']['zh']
    assert '20H' in balance['description']['zh']
    assert event_12_action_hint('scale_judgement', 'scale_balance') == 'scale_balance'


def test_scale_balance_downgrades_exactly_one_card_and_heals_twenty():
    state = _scale_run(deck_size=3, health=40)
    player = state['player']
    events = []

    _resolve_new_event_12(
        state, 'scale_judgement', 'scale_balance', {}, 'scale-seed', events,
    )

    downgraded = [card for card in player['deck'] if not card.get('upgraded')]
    assert len(downgraded) == 1
    assert player['health'] == 60
    assert [event['type'] for event in events].count('heal') == 1


def test_scale_toward_player_grants_exactly_one_fatigued_card():
    state = _scale_run(deck_size=2, health=30)
    player = state['player']
    events = []

    _resolve_new_event_12(
        state, 'scale_judgement', 'scale_you', {}, 'scale-seed', events,
    )

    fatigued = [card for card in player['deck'] if card.get('def_id') == 'fatigued']
    assert len(fatigued) == 1
    assert player['max_health'] == 160


def _choice_run(deck_size=4, health=40):
    state = build_initial_story_state('run-choice', 'common_flower')
    player = state['player']
    player['health'] = health
    player['max_health'] = 80
    player['deck'] = [
        {
            'def_id': 'basic' if index % 2 == 0 else 'bone',
            'instance_id': f'choice-{index}',
            'upgraded': False,
        }
        for index in range(deck_size)
    ]
    # room 必须非空：引擎普遍使用 ``state.get('room') or {}``，空 dict 会被替换。
    state['room'] = {'type': 'event', 'event_id': 'choice-test'}
    return state


def test_crusher_decompose_lets_player_choose_three_removals():
    """裂解机（2026-10-24）：删除的3张牌由玩家自选，不再是随机。"""
    state = _choice_run(deck_size=5)
    player = state['player']
    events = []

    _resolve_new_event_12(
        state, 'crusher_machine', 'decompose_self', {}, 'crusher-seed', events,
    )

    room = state['room']
    assert room['crusher_remaining'] == 3
    assert room['choices'][0]['id'] == 'crusher_remove_card'
    assert room['choices'][0]['selection'] == 'remove'
    assert player['max_health'] == 80 - 24  # ceil(80 * 0.3)
    assert len(player['deck']) == 5  # 阶段一不删牌

    keep = {card['instance_id'] for card in player['deck'][3:]}
    for _ in range(3):
        victim = player['deck'][0]['instance_id']
        _resolve_new_event_12(
            state, 'crusher_machine', 'crusher_remove_card',
            {'card_instance_id': victim}, 'crusher-seed', events,
        )
    assert 'crusher_remaining' not in room
    assert len(player['deck']) == 2
    assert keep == {card['instance_id'] for card in player['deck']}


def test_enchanter_upgrades_player_chosen_cards_per_book():
    """附魔师（2026-10-24）：每失去一本附魔书升级玩家自选的一张牌。"""
    state = _choice_run(deck_size=3)
    player = state['player']
    player['enchantment_books'] = [
        {'instance_id': 'book-1', 'book_id': 'sharp'},
        {'instance_id': 'book-2', 'book_id': 'protection'},
    ]
    events = []

    _resolve_new_event_12(
        state, 'enchanter', 'enchant', {}, 'enchanter-seed', events,
    )

    room = state['room']
    assert room['enchanter_remaining'] == 2
    assert player['enchantment_books'] == []
    assert room['choices'][0]['id'] == 'enchanter_upgrade_card'
    assert room['choices'][0]['selection'] == 'upgrade'

    _resolve_new_event_12(
        state, 'enchanter', 'enchanter_upgrade_card',
        {'card_instance_id': 'choice-0'}, 'enchanter-seed', events,
    )
    assert room['enchanter_remaining'] == 1
    assert player['deck'][0]['upgraded'] is True

    _resolve_new_event_12(
        state, 'enchanter', 'enchanter_upgrade_card',
        {'card_instance_id': 'choice-2'}, 'enchanter-seed', events,
    )
    assert 'enchanter_remaining' not in room
    upgraded = [card for card in player['deck'] if card.get('upgraded')]
    assert {card['instance_id'] for card in upgraded} == {'choice-0', 'choice-2'}


def test_herald_resist_lets_player_choose_two_transforms():
    """传令官（2026-10-24）：变化的2张牌由玩家自选，完成后才获得疲倦。"""
    state = _choice_run(deck_size=3)
    player = state['player']
    events = []

    _resolve_new_event_12(
        state, 'herald', 'resist', {}, 'herald-seed', events,
    )

    room = state['room']
    assert room['herald_remaining'] == 2
    pick = room['choices'][0]
    assert pick['id'] == 'herald_transform_card'
    assert pick['selection'] == 'transform'
    assert set(pick['candidate_ids']) == {
        'choice-0', 'choice-1', 'choice-2',
    }
    assert not any(card['def_id'] == 'fatigued' for card in player['deck'])

    _resolve_new_event_12(
        state, 'herald', 'herald_transform_card',
        {'card_instance_id': 'choice-1'}, 'herald-seed', events,
    )
    assert room['herald_remaining'] == 1
    assert not any(card['def_id'] == 'fatigued' for card in player['deck'])

    _resolve_new_event_12(
        state, 'herald', 'herald_transform_card',
        {'card_instance_id': 'choice-2'}, 'herald-seed', events,
    )
    assert 'herald_remaining' not in room
    assert sum(1 for card in player['deck'] if card['def_id'] == 'fatigued') == 1
