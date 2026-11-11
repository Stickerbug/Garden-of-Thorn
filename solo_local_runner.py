# -*- coding: utf-8 -*-
"""浏览器 Worker 内的单人训练场运行器。

直接复用项目的 Python GameEngine 与模组加载器；本模块只负责会话、序列化、
训练场历史与消息编排，不包含第二套卡牌规则。CPython 测试与 Pyodide 共用。
"""
from __future__ import annotations

import copy
import json
import os
import pickle
import uuid
import zlib
from collections import deque
from typing import Any

from cards import (
    ALL_MOD_SHARED_CARD_IDS, CARD_DEFS, ERROR_CARD_ID, FIRST_PLAYER_ELIXIR,
    FIRST_PLAYER_HAND_SIZE, INITIAL_ELIXIR, INITIAL_HAND_SIZE, INITIAL_MAGIC,
    INITIAL_HEALTH, SECOND_PLAYER_HEALTH, CardDef, CardInstance,
    normalize_card_flag, normalize_card_flags,
)
from card_i18n import apply_card_i18n_defaults
from game_engine import GameEngine
from mod_loadout_v2 import build_v2_loadout
from mod_loader import load_all_mods, load_mod_from_data, merge_mod_cards_to_card_defs
import mod_loader


SOLO_HISTORY_LIMIT = 100
SOLO_LOG_LIMIT = 1200
SOLO_ACTION_WORK_BUDGET = 20000
SNAPSHOT_MAGIC = b'GTNS1\0'
SHARED_ATTRS = GameEngine.DEEPCOPY_SHARED_ATTRS
DETACHED_ATTRS = ('_solo_undo_stack', '_solo_redo_stack', *SHARED_ATTRS)
STATUS_TOTAL_ATTRS = (
    'poison', 'fire', 'dodge', 'toxic', 'triangle_stacks', 'overload',
    'foresight', 'fracture', 'stagnation', 'blind', 'heal_block',
    'weakness', 'bleed', 'skip_turn', 'attack_blocked', 'attack_only',
    'magic_blocked', 'honey_control_turns', 'untargetable',
)
STATUS_TOTAL_EXCLUDED_CUSTOM_KEYS = {
    'jungle:root', 'jungle:root_status', 'root_status', 'equipment_protection', 'armor',
}

_ENGINE = None
_MANIFEST: dict[str, Any] = {}
_DISABLED_CARD_IDS: set[str] = set()
_DISABLED_MOD_FILES: set[str] = set()
_DISABLED_MOD_IDS: set[str] = set()


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _positive_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _status_type_count(player):
    total = sum(1 for attr in STATUS_TOTAL_ATTRS if _positive_int(getattr(player, attr, 0)) > 0)
    total += int(bool(getattr(player, 'bandage_active', False)))
    total += int(bool(getattr(player, 'bandage_death_pending', False)))
    custom = getattr(player, 'custom_statuses', {}) or {}
    if isinstance(custom, dict):
        total += sum(
            1 for key, value in custom.items()
            if str(key) not in STATUS_TOTAL_EXCLUDED_CUSTOM_KEYS and _positive_int(value) > 0
        )
    return total


def _v2_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _v2_card_type(value):
    text = str(value or '').strip().lower()
    return {
        'attack': 'thorn', 'skill': 'bloom', 'equipment': 'root', 'counter': 'guard',
        'thorn': 'thorn', 'bloom': 'bloom', 'root': 'root', 'guard': 'guard',
    }.get(text, 'bloom')


def _v2_card_name_from_id(card_id):
    path = str(card_id or '').split(':')[-1]
    return ' '.join(part.capitalize() for part in path.replace('/', '_').split('_') if part) or str(card_id or 'Card')


def _register_v2_cards(v2_loadout):
    registered = []
    cards = getattr(v2_loadout, 'registries', {}).get('cards', {}) or {}
    for card_id, resource in cards.items():
        if not isinstance(resource, dict):
            continue
        runtime_id = str(resource.get('legacy_id') or resource.get('runtime_id') or card_id)
        cost = resource.get('cost') if isinstance(resource.get('cost'), dict) else {}
        flags = normalize_card_flags(resource.get('flags', []) if isinstance(resource.get('flags', []), list) else [])
        if isinstance(resource.get('tags'), list):
            for tag in resource.get('tags') or []:
                tag_text = str(tag)
                if tag_text.startswith('gtn:'):
                    tag_text = tag_text.split(':', 1)[1]
                flags.add(normalize_card_flag(tag_text))
        CARD_DEFS[runtime_id] = CardDef(
            id=runtime_id,
            name_en=str(resource.get('name_en') or resource.get('name') or _v2_card_name_from_id(card_id)),
            name_cn=str(resource.get('name_cn') or resource.get('name') or resource.get('name_en') or _v2_card_name_from_id(card_id)),
            cost_e=_v2_int(resource.get('cost_e', cost.get('e', 0)), 0),
            cost_m=_v2_int(resource.get('cost_m', cost.get('m', 0)), 0),
            card_type=_v2_card_type(resource.get('card_type', resource.get('type', 'bloom'))),
            count=max(0, _v2_int(resource.get('count', resource.get('weight', 3)), 3)),
            quality=str(resource.get('quality') or 'Common'),
            description=str(resource.get('description') or resource.get('description_cn') or ''),
            effect_text=str(resource.get('effect_text') or resource.get('effect_text_cn') or ''),
            name_i18n=dict(resource.get('name_i18n') or {}) if isinstance(resource.get('name_i18n'), dict) else {},
            description_i18n=dict(resource.get('description_i18n') or {}) if isinstance(resource.get('description_i18n'), dict) else {},
            effect_text_i18n=dict(resource.get('effect_text_i18n') or {}) if isinstance(resource.get('effect_text_i18n'), dict) else {},
            flags=flags,
            trigger_cost_e=_v2_int(resource.get('trigger_cost_e', -1), -1),
            trigger_cost_m=_v2_int(resource.get('trigger_cost_m', 0), 0),
            trigger_effect_text=str(resource.get('trigger_effect_text') or ''),
            trigger_effect_text_i18n=dict(resource.get('trigger_effect_text_i18n') or {}) if isinstance(resource.get('trigger_effect_text_i18n'), dict) else {},
            response_trigger=str(resource.get('response_trigger') or ''),
            effects=[], scripts={},
            response_title=str(resource.get('response_title') or ''),
            response_content=str(resource.get('response_content') or ''),
            response_title_i18n=dict(resource.get('response_title_i18n') or {}) if isinstance(resource.get('response_title_i18n'), dict) else {},
            response_content_i18n=dict(resource.get('response_content_i18n') or {}) if isinstance(resource.get('response_content_i18n'), dict) else {},
            v2_events=resource.get('events') if isinstance(resource.get('events'), dict) else {},
            v2_resource=dict(resource), v2_mod_id=str(resource.get('_mod_id') or ''),
            image=str(resource.get('image') or ''),
            image_url=str(resource.get('image_url') or resource.get('image') or ''),
            upgraded_image=str(resource.get('upgraded_image') or ''),
            upgraded_image_url=str(resource.get('upgraded_image_url') or resource.get('upgraded_image') or ''),
            copy_count=_v2_int(resource.get('copy_count', 0), 0),
            swift_value=_v2_int(resource.get('swift_value', 0), 0),
            magic_swift_value=_v2_int(resource.get('magic_swift_value', 0), 0),
            fission_level=max(1, _v2_int(resource.get('fission_level', _v2_int(resource.get('fission_count', 0), 0) + 1), 1)),
            fusion_level=max(1, _v2_int(resource.get('fusion_level', resource.get('fusion_multiplier', 1)), 1)),
            damage=_v2_int(resource.get('damage', 0), 0), hits=_v2_int(resource.get('hits', 1), 1),
            ui_effect_size=str(resource.get('ui_effect_size') or ''),
        )
        registered.append(runtime_id)
    if registered:
        apply_card_i18n_defaults(CARD_DEFS)
    return registered


def _build_solo_card(entry):
    if isinstance(entry, dict):
        card = CardInstance(def_id=entry.get('def_id'))
        card.instance_flags = set(entry.get('instance_flags', []))
        card.disabled_flags = set(entry.get('disabled_flags', []))
        return card
    return CardInstance(def_id=entry)


def _reset_player_for_solo(player, deck_entries, is_first):
    player.health = INITIAL_HEALTH if is_first else SECOND_PLAYER_HEALTH
    player.max_health = player.health
    player.base_max_health = player.health
    player.elixir = FIRST_PLAYER_ELIXIR if is_first else INITIAL_ELIXIR
    player.max_elixir = 10
    player.magic = INITIAL_MAGIC
    player.max_magic = 10
    for attr in (
        'armor', 'poison', 'fire', 'vulnerable', 'toxic', 'triangle_stacks', 'dodge',
        'nazar_big_hits', 'equipment_protection', 'magic_battery_m_this_turn',
        'attack_blocked', 'enemy_draw_reduction', 'enemy_e_reduction', 'attack_only',
    ):
        setattr(player, attr, 0)
    player.nazar_active = False
    player.coffee_first_use = True
    player.invincible = False
    player.skip_turn = False
    player.damage_multiplier = 1.0
    player.bandage_active = False
    player.bandage_death_pending = False
    player.untargetable = False
    player.sponge_active = False
    player.shovel_active = False
    player.hand = []
    player.deck = []
    for entry in deck_entries:
        def_id = entry.get('def_id') if isinstance(entry, dict) else entry
        if def_id in CARD_DEFS:
            player.deck.append(_build_solo_card(entry))
    player.discard = []
    player.exile = []
    player.equipment = []
    player.cards_played_this_turn = {}
    player.custom_vars = {'咖啡首次使用': 1, '三角形层数': 0, '魔法电池本回合回魔': 0}
    player.negate_next_skill = False
    player.is_first_player = is_first


def _init_history(engine):
    engine._solo_undo_stack = deque(maxlen=SOLO_HISTORY_LIMIT)
    engine._solo_redo_stack = deque(maxlen=SOLO_HISTORY_LIMIT)


def _apply_loadout(engine, v2_loadout):
    engine.v2_loadout = v2_loadout
    registries = getattr(v2_loadout, 'registries', {}) or {}
    def enabled(source):
        return {key: value for key, value in dict(source or {}).items() if str((value or {}).get('_mod_id') or '') not in _DISABLED_MOD_IDS}
    engine.v2_ui_components = enabled(registries.get('ui_components') or {})
    engine.v2_tag_defs = enabled(registries.get('tags') or {})
    engine.v2_status_defs = enabled(registries.get('statuses') or {})
    engine.v2_opening_event_defs = enabled(registries.get('opening_events') or {})
    engine.v2_event_hooks = [
        hook for hook in list(getattr(v2_loadout, 'event_hooks', []) or [])
        if str(hook.get('_mod_id') or '') not in _DISABLED_MOD_IDS
    ]


def _create_engine(payload, v2_loadout, allowed_card_ids):
    deck0 = payload.get('deck0') or []
    deck1 = payload.get('deck1') or []
    if not isinstance(deck0, list) or not isinstance(deck1, list) or len(deck0) > 50 or len(deck1) > 50:
        raise ValueError('训练场牌组必须各为0-50张')
    def valid(entry):
        def_id = entry.get('def_id') if isinstance(entry, dict) else entry
        return def_id in CARD_DEFS and def_id in allowed_card_ids
    if any(not valid(entry) for entry in deck0 + deck1):
        raise ValueError('训练场牌组中包含当前不可用的卡牌')
    event0, event1 = payload.get('event0'), payload.get('event1')
    engine = GameEngine()
    builtin_ids = set(GameEngine.BUILTIN_SETUP_CARD_IDS)
    if 'Vanilla Cards.gtnmod' in _DISABLED_MOD_FILES:
        builtin_ids.clear()
    engine.available_builtin_setup_card_ids = builtin_ids.difference(_DISABLED_CARD_IDS)
    _apply_loadout(engine, v2_loadout)
    engine.allowed_card_ids = set(allowed_card_ids) or None
    engine.player_names = ['Player A', 'Player B']
    engine.phase = 'playing'
    force_first = [idx for idx, event_id in enumerate((event0, event1)) if str(event_id) == '7']
    engine.first_player = force_first[0] if len(force_first) == 1 else 0
    engine.current_player = engine.first_player
    engine.round_num = 1
    engine.opening_event_picks = [event0, event1]
    engine.opening_event_sub_choices = [payload.get('sub0'), payload.get('sub1')]
    engine.log = []
    engine.pending_response = None
    engine.pending_choice = None
    _reset_player_for_solo(engine.players[0], deck0, engine.first_player == 0)
    _reset_player_for_solo(engine.players[1], deck1, engine.first_player == 1)
    if engine.allowed_card_ids is not None:
        for player in engine.players:
            player.deck = [card for card in player.deck if card.def_id in engine.allowed_card_ids]
    for index in range(2):
        if engine.opening_event_picks[index] is not None:
            engine._apply_opening_event(index)
    for index in range(2):
        if index == engine.first_player:
            hand_size = FIRST_PLAYER_HAND_SIZE
            if str(engine.opening_event_picks[index]) == '7' and len(force_first) == 1:
                hand_size = 4
                engine.players[index].elixir += 3
            if str(engine.opening_event_picks[index]) == '5':
                hand_size = max(0, hand_size - 1)
            engine.players[index].draw_cards(hand_size)
        else:
            hand_size = INITIAL_HAND_SIZE
            if str(engine.opening_event_picks[index]) == '5':
                hand_size = max(0, hand_size - 1)
            engine.players[index].draw_cards(hand_size)
    engine.log_msg(f"单人训练场开始！{engine.pn(engine.first_player)}先手。")
    engine.log_msg(f'=== 第{engine.round_num}回合 ===')
    engine.phase = 'action'
    engine._start_player_turn(engine.first_player)
    _init_history(engine)
    return engine


def initialize(config_json='{}'):
    global _MANIFEST, _DISABLED_CARD_IDS, _DISABLED_MOD_FILES, _DISABLED_MOD_IDS
    config = json.loads(config_json) if isinstance(config_json, str) else dict(config_json or {})
    root = os.path.dirname(os.path.abspath(__file__))
    manifest_path = os.path.join(root, 'solo_local_manifest.json')
    if os.path.isfile(manifest_path):
        with open(manifest_path, encoding='utf-8') as handle:
            _MANIFEST = json.load(handle)
    else:
        _MANIFEST = dict(config.get('manifest') or {})
    _DISABLED_CARD_IDS = set(_MANIFEST.get('disabled_card_ids') or config.get('disabled_card_ids') or [])
    _DISABLED_MOD_FILES = set(_MANIFEST.get('disabled_mod_files') or config.get('disabled_mod_files') or [])
    mod_loader.MODS_DIR = os.path.join(root, 'mods')
    mod_loader.invalidate_mod_cache()
    mods = load_all_mods(force=True)
    merge_mod_cards_to_card_defs()
    _DISABLED_MOD_IDS = {
        str(getattr(getattr(mod, 'manifest', None), 'id', '') or '')
        for mod in mods if mod.filename in _DISABLED_MOD_FILES
    }
    community_mods = []
    for entry in config.get('community_mod_data') or []:
        if not isinstance(entry, dict):
            continue
        data = entry.get('data') if isinstance(entry.get('data'), dict) else entry
        mod = load_mod_from_data(data, source=str(entry.get('public_url') or 'community'), allow_scripts=False)
        if mod.errors:
            raise ValueError('; '.join(mod.errors))
        mod.community_sha256 = str(entry.get('sha256') or '')
        mod.community_data = data
        community_mods.append(mod)
        for card in mod.cards:
            if card.id != ERROR_CARD_ID:
                CARD_DEFS[card.id] = card.to_card_def()
    v2_mods = [mod for mod in mods if not mod.errors and getattr(mod, 'format_version', 1) == 2]
    v2_mods.extend(mod for mod in community_mods if getattr(mod, 'format_version', 1) == 2)
    v2_loadout = build_v2_loadout(v2_mods)
    if not v2_loadout.ok:
        raise ValueError('v2 模组组合错误: ' + '; '.join(v2_loadout.errors))
    registered_v2_ids = _register_v2_cards(v2_loadout)
    allowed = {ERROR_CARD_ID} | set(GameEngine.BUILTIN_SETUP_CARD_IDS)
    if 'Vanilla Cards.gtnmod' in _DISABLED_MOD_FILES:
        allowed.difference_update(GameEngine.BUILTIN_SETUP_CARD_IDS)
    for mod in mods:
        if mod.errors:
            continue
        for card in mod.cards:
            if card.id in CARD_DEFS:
                allowed.add(card.id)
    for mod in community_mods:
        for card in mod.cards:
            if card.id in CARD_DEFS:
                allowed.add(card.id)
    allowed.update(registered_v2_ids)
    if mods or community_mods:
        allowed.update(card_id for card_id in ALL_MOD_SHARED_CARD_IDS if card_id in CARD_DEFS)
    allowed = {
        card_id for card_id in allowed
        if card_id not in _DISABLED_CARD_IDS and not (
            card_id not in ALL_MOD_SHARED_CARD_IDS
            and str(getattr(CARD_DEFS.get(card_id), 'v2_mod_id', '') or '') in _DISABLED_MOD_IDS
        )
    }
    initialize.allowed_card_ids = allowed
    initialize.v2_loadout = v2_loadout
    return _json({'success': True, 'card_count': len(CARD_DEFS), 'allowed_count': len(allowed), 'manifest': _MANIFEST})


def _snapshot(engine):
    saved = {}
    for attr in DETACHED_ATTRS:
        if hasattr(engine, attr):
            saved[attr] = getattr(engine, attr)
            try:
                delattr(engine, attr)
            except Exception:
                pass
    try:
        try:
            return SNAPSHOT_MAGIC + zlib.compress(pickle.dumps(engine, protocol=pickle.HIGHEST_PROTOCOL), level=1)
        except Exception:
            restored = copy.deepcopy(engine)
            for attr in SHARED_ATTRS:
                if attr in saved:
                    setattr(restored, attr, saved[attr])
            return {'kind': 'deepcopy', 'engine': restored}
    finally:
        for attr, value in saved.items():
            setattr(engine, attr, value)


def _restore(engine, snapshot):
    undo_stack = getattr(engine, '_solo_undo_stack', deque(maxlen=SOLO_HISTORY_LIMIT))
    redo_stack = getattr(engine, '_solo_redo_stack', deque(maxlen=SOLO_HISTORY_LIMIT))
    shared = {attr: getattr(engine, attr) for attr in SHARED_ATTRS if hasattr(engine, attr)}
    if isinstance(snapshot, (bytes, bytearray)) and bytes(snapshot).startswith(SNAPSHOT_MAGIC):
        restored = pickle.loads(zlib.decompress(bytes(snapshot)[len(SNAPSHOT_MAGIC):]))
        for attr, value in shared.items():
            setattr(restored, attr, value)
    elif isinstance(snapshot, dict) and snapshot.get('kind') == 'deepcopy':
        restored = copy.deepcopy(snapshot.get('engine'), {id(value): value for value in shared.values()})
        for attr, value in shared.items():
            setattr(restored, attr, value)
    else:
        restored = copy.deepcopy(snapshot, {id(value): value for value in shared.values()})
    engine.__dict__.clear()
    engine.__dict__.update(restored.__dict__)
    engine._solo_undo_stack = undo_stack
    engine._solo_redo_stack = redo_stack
    engine._bind_player_callbacks()
    return True


def _capture_undo(engine):
    if not hasattr(engine, '_solo_undo_stack') or not hasattr(engine, '_solo_redo_stack'):
        _init_history(engine)
    return _snapshot(engine)


def _commit_undo(engine, snapshot):
    if snapshot is None:
        return
    if not hasattr(engine, '_solo_undo_stack') or not hasattr(engine, '_solo_redo_stack'):
        _init_history(engine)
    engine._solo_undo_stack.append(snapshot)
    engine._solo_redo_stack.clear()


def _response_trigger_types(engine, played_card):
    played_def = CARD_DEFS.get((played_card or {}).get('def_id', ''))
    result = []
    def add(value):
        if value and value not in result:
            result.append(value)
    if played_def:
        if played_def.card_type == 'thorn':
            add('thorn')
        elif played_def.card_type == 'bloom':
            add('bloom')
        elif played_def.card_type == 'root':
            add('root')
        try:
            instance = CardInstance.from_dict(played_card)
        except Exception:
            instance = None
        would_destroy = False
        checker = getattr(engine, '_would_destroy_equipment', None)
        if callable(checker) and instance is not None:
            try:
                would_destroy = bool(checker(instance))
            except Exception:
                would_destroy = False
        if would_destroy or played_def.id in ('Sewage', 'MagicSewage'):
            add('equipment_destroy')
        try:
            from engine_runtime_support import card_applies_hand_charge
            if instance is not None and card_applies_hand_charge(instance):
                add('hand_charge')
        except Exception:
            pass
        healer = getattr(engine, '_would_heal', None)
        if callable(healer) and instance is not None:
            try:
                if healer(instance):
                    add('heal')
            except Exception:
                pass
        add('targeted')
        add('any')
    return result


def _response_destroy_target_equipments(engine, played_card, pending, responder_id):
    choice = pending.get('original_choice') if isinstance(pending, dict) else None
    try:
        source = CardInstance.from_dict(played_card)
        destroys = bool(engine._would_destroy_equipment(source))
    except (AttributeError, TypeError, ValueError, KeyError):
        return []
    try:
        player = engine.players[responder_id]
    except (IndexError, TypeError):
        return []
    card_id = str(getattr(source, 'def_id', '') or '').lower()
    legacy_id = str(getattr(getattr(source, 'card_def', None), 'legacy_id', '') or '').lower()
    is_magic = card_id in ('magicsewage', 'vanilla:magicsewage') or legacy_id == 'magicsewage'
    candidates = [eq for eq in player.equipment if 'indestructible' not in eq.card_instance.flags]
    if not is_magic:
        target_id = None
        if isinstance(choice, dict) and choice.get('target_instance_id') is not None:
            try:
                target_id = int(choice['target_instance_id'])
            except (TypeError, ValueError):
                return []
        if target_id is not None:
            candidates = [eq for eq in candidates if getattr(eq.card_instance, 'instance_id', None) == target_id]
        else:
            candidates = candidates[:1]
    protection = max(0, int(getattr(player, 'equipment_protection', 0) or 0))
    destroyed = []
    for equipment in candidates:
        if int(getattr(equipment, 'armor', 0) or 0) > 0:
            continue
        if protection > 0:
            protection -= 1
            continue
        serialized = equipment.to_dict()
        serialized['owner_id'] = responder_id
        destroyed.append(serialized)
    return destroyed


def _response_payload(engine, responder_id, played_card, player_id, counter_cards, target_player_id=None):
    serialized = [card.to_dict() if hasattr(card, 'to_dict') else card for card in counter_cards or []]
    pending = getattr(engine, 'pending_response', None) or {}
    if target_player_id is None:
        target_player_id = pending.get('target_player_id')
    display = played_card
    confusion = False
    disguise = getattr(engine, '_sewers_confusion_disguise', None)
    if callable(disguise):
        try:
            display = disguise(responder_id, played_card) or played_card
            confusion = bool(isinstance(display, dict) and display.get('sewers_confusion_disguise'))
        except Exception:
            pass
    payload = {
        'card': display, 'player_id': player_id, 'target_player_id': target_player_id,
        'counter_cards': serialized,
    }
    destroyed = _response_destroy_target_equipments(engine, played_card, pending, responder_id)
    if destroyed:
        payload['destroy_target_equipments'] = destroyed
        if len(destroyed) == 1:
            payload['destroy_target_equipment'] = destroyed[0]
    predictor = getattr(engine, 'build_response_damage_prediction', None)
    if confusion:
        predictor = getattr(engine, 'build_sewers_confusion_damage_prediction', predictor)
    if callable(predictor):
        try:
            if confusion:
                payload['damage_prediction'] = predictor(responder_id, played_card, counter_cards or serialized)
            else:
                payload['damage_prediction'] = predictor(responder_id, counter_cards or serialized)
        except Exception:
            pass
    return payload


def _counter_payload(engine, source_id=None):
    pending = getattr(engine, 'pending_response', None)
    if not isinstance(pending, dict) or getattr(engine, 'game_over', False):
        return None
    if source_id is None:
        source_id = int(pending.get('player_id', getattr(engine, 'current_player', 0)))
    responder = 1 - int(source_id)
    played = pending.get('card') or {}
    counters = []
    seen = set()
    for trigger in _response_trigger_types(engine, played):
        for card in engine.get_counter_cards(responder, trigger):
            key = getattr(card, 'instance_id', None)
            if key in seen:
                continue
            seen.add(key)
            counters.append(card)
    return _response_payload(
        engine, responder, played, int(source_id), counters,
        pending.get('target_player_id', responder),
    )


def _choice_payload(source):
    source = source or {}
    payload = {
        'choice_type': source.get('choice_type', ''),
        'card': source.get('card', {}),
        'choice_params': source.get('choice_params', {}),
        'target_player_id': source.get('target_player_id'),
    }
    for key in ('hand_cards', 'deck_cards', 'discard_cards', 'exile_cards', 'equipment_cards', 'top_cards', 'max_replace', 'message'):
        value = source.get(key)
        if value is not None and value != [] and value != '':
            payload[key] = value
    return payload


def _v2_payload(engine):
    pending = getattr(engine, 'pending_v2_ui', None)
    if not pending:
        return None
    return {
        'request_id': pending.get('request_id'), 'component': pending.get('component') or {},
        'card': pending.get('card'), 'timeout_ms': pending.get('timeout_ms', 0),
        'player_id': pending.get('player_id'),
    }


def _slice_log(state, engine, force_full=False):
    log = state.get('log')
    if not isinstance(log, list) or not log:
        return
    start = max(0, int(state.get('log_start') or 0))
    total = start + len(log)
    generation = int(getattr(engine, '_log_rewrite_generation', 0) or 0)
    state['log_gen'] = generation
    sent = getattr(engine, '_log_sent_totals', None)
    if not isinstance(sent, dict):
        sent = {}
        engine._log_sent_totals = sent
    last = sent.get('owner:local')
    if not force_full and isinstance(last, dict) and start <= int(last.get('total') or 0) <= total and int(last.get('gen') or 0) == generation:
        skip = int(last.get('total') or 0) - start
        if skip:
            state['log'] = log[skip:]
            state['log_start'] = int(last.get('total') or 0)
    sent['owner:local'] = {'total': total, 'gen': generation}


def _state(perspective=None, force_full=False):
    engine = _ENGINE
    if engine is None:
        return None
    if perspective is None:
        perspective = engine.current_player if not engine.game_over else 0
    state = engine.get_public_state(perspective)
    offset = max(0, int(getattr(engine, '_solo_log_offset', 0) or 0))
    state['log_start'] = offset
    state['log_total'] = offset + len(state.get('log') or [])
    _slice_log(state, engine, force_full=force_full)
    state['your_id'] = perspective
    if not getattr(engine, '_gtn_match_key_tag', None):
        engine._gtn_match_key_tag = f'solo-local:{uuid.uuid4().hex[:12]}'
    state['match_key'] = engine._gtn_match_key_tag
    state['your_name'] = 'Player A' if perspective == 0 else 'Player B'
    state['opponent_name'] = 'Player B' if perspective == 0 else 'Player A'
    state['solo'] = True
    state['local_engine'] = True
    state['local_status_type_count'] = sum(_status_type_count(player) for player in engine.players)
    return state


def _mutate(engine, fn, record_history=True):
    history = _capture_undo(engine) if record_history else None
    rollback = history if history is not None else _snapshot(engine)
    engine._begin_action_work_budget(SOLO_ACTION_WORK_BUDGET)
    try:
        result = fn()
        if isinstance(result, dict) and getattr(engine, 'pending_response', None):
            result['_solo_response_request_payload'] = _counter_payload(engine)
        log = getattr(engine, 'log', None)
        if isinstance(log, list) and len(log) > SOLO_LOG_LIMIT:
            trim = len(log) - SOLO_LOG_LIMIT
            del log[:trim]
            engine._solo_log_offset = max(0, int(getattr(engine, '_solo_log_offset', 0) or 0)) + trim
            engine._log_compaction_floor = max(0, int(getattr(engine, '_log_compaction_floor', 0) or 0) - trim)
    except Exception:
        if rollback is not None:
            _restore(engine, rollback)
        raise
    finally:
        engine._end_action_work_budget()
    return result, history


def _fire_stand_ready(engine):
    pending = getattr(engine, 'pending_response', None)
    if not isinstance(pending, dict) or engine.game_over:
        return False
    try:
        responder = 1 - int(pending.get('player_id', 0))
        played = pending.get('card') or {}
        for trigger in _response_trigger_types(engine, played):
            for card in engine.get_counter_cards(responder, trigger):
                if 'stand_ready' not in (getattr(card.card_def, 'flags', set()) or set()):
                    continue
                result = engine.handle_response(responder, card.instance_id)
                return bool(isinstance(result, dict) and result.get('success'))
    except Exception:
        return False
    return False


def _with_pending(events, perspective=None, response_payload=None, force_full=False, _depth=0):
    engine = _ENGINE
    state = _state(perspective, force_full=force_full)
    if state is not None:
        events.append(('solo_state', state))
    if engine is None or engine.game_over:
        return
    pending = getattr(engine, 'pending_response', None)
    if pending:
        if _depth < 8 and _fire_stand_ready(engine):
            _with_pending(events, None, force_full=force_full, _depth=_depth + 1)
            return
        payload = response_payload if isinstance(response_payload, dict) else _counter_payload(engine)
        if payload:
            events.append(('response_request', payload))
        return
    if getattr(engine, 'pending_choice', None):
        events.append(('choice_request', _choice_payload(engine.pending_choice)))
        return
    v2 = _v2_payload(engine)
    if v2:
        events.append(('v2_ui_request', v2))


def _finish_result(events, result, player_id, undo_snapshot, commit_on_error=False):
    result = result or {}
    if result.get('needs_response'):
        _commit_undo(_ENGINE, undo_snapshot)
        events.append(('solo_state', _state(1 - int(player_id))))
        payload = result.get('_solo_response_request_payload') or _counter_payload(_ENGINE)
        if payload:
            events.append(('response_request', payload))
        return
    if result.get('needs_choice'):
        _commit_undo(_ENGINE, undo_snapshot)
        events.append(('solo_state', _state()))
        events.append(('choice_request', _choice_payload(result)))
        return
    if result.get('needs_v2_ui'):
        _commit_undo(_ENGINE, undo_snapshot)
        _with_pending(events)
        return
    if result.get('success'):
        _commit_undo(_ENGINE, undo_snapshot)
        _with_pending(events, response_payload=result.get('_solo_response_request_payload'))
        return
    events.append(('server_error', {'message': result.get('error', 'Operation failed')}))
    if result.get('keep_window') and getattr(_ENGINE, 'pending_v2_ui', None):
        events.append(('v2_ui_request', _v2_payload(_ENGINE)))
    if commit_on_error:
        _commit_undo(_ENGINE, undo_snapshot)
        _with_pending(events)


def _predict_hand(payload):
    if _ENGINE is None:
        return []
    entries = payload.get('cards') or []
    if not isinstance(entries, list):
        return []
    results = {}
    log_len = len(getattr(_ENGINE, 'log', []) or [])
    for item in entries[:12]:
        if not isinstance(item, dict):
            continue
        try:
            owner = int(item.get('player_id'))
            instance = int(item.get('instance_id'))
            target = int(item.get('target_player_id', -1))
        except (TypeError, ValueError):
            continue
        if owner != 0:
            prediction = {'ok': False, 'error': 'not-visible'}
        else:
            choice = None if target < 0 else {'target_player_id': target, 'target_player': target, 'target_id': target}
            prediction = _ENGINE.simulate_card_play_prediction(owner, instance, choice)
        results[f'{owner}:{instance}:{target}'] = prediction
    return [('play_predictions', {'predictions': results, 'log_len': log_len, 'room_id': None})]


def dispatch(event_name, payload_json='{}'):
    global _ENGINE
    payload = json.loads(payload_json) if isinstance(payload_json, str) else dict(payload_json or {})
    if event_name == 'predict_hand':
        return _json({'events': _predict_hand(payload)})
    if event_name == 'solo_start':
        _ENGINE = _create_engine(payload, initialize.v2_loadout, initialize.allowed_card_ids)
        events = [('game_phase', {'phase': 'playing', 'solo': True, 'local_engine': True})]
        _with_pending(events, force_full=True)
        return _json({'events': events})
    if event_name == 'solo_pause':
        _ENGINE = None
        return _json({'events': [('solo_paused', {})]})
    if _ENGINE is None:
        return _json({'events': [('server_error', {'message': '训练场尚未开始'})]})
    if event_name == 'request_game_state':
        events = []
        _with_pending(events, force_full=True)
        return _json({'events': events})

    engine = _ENGINE
    events = []
    if event_name == 'solo_play_card':
        player = engine.current_player
        choice = payload.get('choice')
        target = int(payload.get('target_player_id', -1))
        if target >= 0:
            choice = dict(choice or {})
            choice.setdefault('target_player', target)
            choice.setdefault('target_player_id', target)
            choice.setdefault('target_id', target)
        result, undo = _mutate(engine, lambda: engine.play_card(player, int(payload.get('card_instance_id')), choice))
        _finish_result(events, result, player, undo)
    elif event_name == 'solo_response':
        had_pending = bool(getattr(engine, 'pending_response', None))
        responder = 1 - engine.pending_response['player_id'] if had_pending else engine.current_player
        raw = payload.get('card_instance_id')
        instance = None if raw in (None, '', 'none') else int(raw)
        result, undo = _mutate(engine, lambda: engine.handle_response(responder, instance), record_history=had_pending)
        if had_pending and undo is not None:
            _commit_undo(engine, undo)
            undo = None
        if getattr(engine, 'pending_response', None):
            pending_player = int(engine.pending_response.get('player_id', engine.current_player))
            events.append(('solo_state', _state(1 - pending_player)))
            response = result.get('_solo_response_request_payload') or _counter_payload(engine)
            if response:
                events.append(('response_request', response))
        elif getattr(engine, 'pending_choice', None):
            events.append(('solo_state', _state()))
            events.append(('choice_request', _choice_payload(engine.pending_choice)))
        elif getattr(engine, 'pending_v2_ui', None):
            _with_pending(events)
        else:
            events.append(('solo_state', _state()))
    elif event_name == 'solo_resolve_choice':
        if not getattr(engine, 'pending_choice', None):
            events.append(('solo_state', _state()))
        else:
            player = engine.pending_choice.get('player_id', engine.current_player)
            result, undo = _mutate(engine, lambda: engine.resolve_choice(player, payload.get('choice')))
            _finish_result(events, result, player, undo, commit_on_error=True)
    elif event_name == 'solo_v2_ui_response':
        pending = getattr(engine, 'pending_v2_ui', None)
        if not pending:
            return _json({'events': []})
        player = int(pending.get('player_id', engine.current_player))
        result, undo = _mutate(
            engine,
            lambda: engine.handle_v2_ui_response(player, str(payload.get('request_id') or ''), payload),
        )
        _finish_result(events, result, player, undo)
    elif event_name == 'solo_v2_ui_timeout':
        pending = getattr(engine, 'pending_v2_ui', None)
        if pending and str(pending.get('request_id') or '') == str(payload.get('request_id') or ''):
            player = int(pending.get('player_id', engine.current_player))
            result, undo = _mutate(
                engine,
                lambda: engine.handle_v2_ui_response(
                    player, str(payload.get('request_id') or ''),
                    {'button': 'cancel', 'values': {}},
                ),
                record_history=False,
            )
            _finish_result(events, result, player, undo)
    elif event_name == 'solo_use_trigger':
        player = engine.current_player
        result, undo = _mutate(
            engine,
            lambda: engine.use_trigger(
                player, int(payload.get('equipment_instance_id')),
                target_player_id=int(payload.get('target_player_id', -1)),
            ),
        )
        _finish_result(events, result, player, undo)
    elif event_name == 'solo_end_turn':
        player = engine.current_player
        result, undo = _mutate(engine, lambda: engine.end_turn(player))
        _finish_result(events, result, player, undo)
    elif event_name == 'solo_set_next_draw':
        def_ids = payload.get('def_ids') or ([payload.get('def_id')] if payload.get('def_id') else [])
        def set_next():
            player = engine.players[engine.current_player]
            picked = []
            for def_id in def_ids[:10]:
                index = next((idx for idx, card in enumerate(player.deck) if card.def_id == def_id), -1)
                if index >= 0:
                    picked.append(player.deck.pop(index))
            if not picked:
                return {'success': False, 'error': '设置失败：牌堆中没有这些牌'}
            for card in reversed(picked):
                player.deck.insert(0, card)
            names = '、'.join(card.name_cn for card in picked)
            engine.log_msg(f'训练场：{engine.pn(engine.current_player)} 设置下次抽牌：{names}')
            return {'success': True}
        result, undo = _mutate(engine, set_next)
        _finish_result(events, result, engine.current_player, undo)
    elif event_name in ('solo_undo', 'solo_redo'):
        source = engine._solo_undo_stack if event_name == 'solo_undo' else engine._solo_redo_stack
        target = engine._solo_redo_stack if event_name == 'solo_undo' else engine._solo_undo_stack
        if not source:
            events.append(('server_error', {'message': '没有可撤销操作' if event_name == 'solo_undo' else '没有可重做操作'}))
        else:
            current = _snapshot(engine)
            snapshot = source.pop()
            if current is not None:
                target.append(current)
            _restore(engine, snapshot)
            _with_pending(events, force_full=True)
    else:
        events.append(('server_error', {'message': f'未知训练场操作：{event_name}'}))
    return _json({'events': events})
