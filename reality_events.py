# -*- coding: utf-8 -*-
"""操纵现实（2026-10-24）：开局随机三个全局事件，双方各可 ban 一个。

事件作用于整场对局（双方共同生效）。房间层在模组抽取后进入 reality_ban
阶段，双方各禁用一个（或跳过），剩余事件写入引擎 ``reality_events``。
效果实现全部集中在 :class:`RealityEngineMixin`，引擎在对应钩子点调用；
未启用事件时钩子为零开销（集合查询）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

REALITY_EVENTS: Dict[int, Dict[str, object]] = {
    1: {'name': '攻守之势异也', 'desc': '攻击牌选择量-1，技能牌选择量+1'},
    2: {'name': '塔之诅咒', 'desc': '反制牌选择量设为0，技能牌选择量增加同等值；每回合多抽3张牌，回合结束丢弃所有非反制牌，回合开始时（回复前）清空费用'},
    3: {'name': '等我启动', 'desc': '回合费用回复量-2，玩家回合开始时该数值+1（最多为7）'},
    4: {'name': '肚皮', 'desc': '所有玩家初始血量+50'},
    5: {'name': '潦草急就', 'desc': '每回合多抽4张牌，多回复5E'},
    6: {'name': '那么，我们开始吧？', 'desc': '初始血量+900，每回合伤害加1倍'},
    7: {'name': '发现', 'desc': '跳过开局选卡，每次抽牌时从三选一中获得（权重按对应类型在选牌中出现的次数决定），回合开始时获得一次重抽机会'},
    8: {'name': '烈焰升腾', 'desc': '开局就进入叠加烧伤阶段（第十回合开始的叠火）'},
    9: {'name': '帝国之力', 'desc': '反制牌选择量-2，技能牌选择量+2'},
    10: {'name': '认知偏差', 'desc': '回合费用回复量+5，玩家回合开始回合回复量-1（最低降为0）'},
    11: {'name': '创世纪', 'desc': '每回合开始时还会回复5M，魔法卡选择权重翻倍'},
    12: {'name': '宾邦', 'desc': '每次选卡时还会将一张复制加入卡组，但所有卡获得放逐'},
    13: {'name': '紧握', 'desc': '所有卡打出后沉重+1，所有卡回合结束时在手中则迅捷+1'},
    14: {'name': '贤者的归隐', 'desc': '每回合开始时将一张虚无，放逐拟态加入手中'},
    15: {'name': '人体蜂房', 'desc': '玩家每回合出第三张牌时获得一层眩晕（一回合一次）'},
    16: {'name': '杂耍', 'desc': '玩家每回合出第三张牌时，将其复制一张并附加虚无、放逐后加入手中'},
    17: {'name': '谜语人', 'desc': '装备牌选择量-3，反制牌选择量+3'},
    18: {'name': '慷慨捐助', 'desc': '玩家打出的牌会进入对手弃牌堆'},
    19: {'name': '启动流程', 'desc': '开局获得10层灼烧，装备牌选择量+7，其他选择量全部为0，将5张污水加入卡组'},
    20: {'name': '鲁莽攻击', 'desc': '所有卡强制指向与上次不相同的目标（取消攻击牌无法指向自己的限制，取消所有不选择目标tag的限制）'},
}

REALITY_EVENT_COUNT = 3


def reality_adjusted_draft_ratio(base_ratio: Dict[str, int], events: Set[int]) -> Dict[str, int]:
    """按生效事件调整选牌类型配额（事件1/2/9/17/19）。"""
    ratio = dict(base_ratio)
    if 1 in events:
        ratio['thorn'] = max(0, ratio.get('thorn', 0) - 1)
        ratio['bloom'] = ratio.get('bloom', 0) + 1
    if 9 in events:
        ratio['guard'] = max(0, ratio.get('guard', 0) - 2)
        ratio['bloom'] = ratio.get('bloom', 0) + 2
    if 17 in events:
        ratio['root'] = max(0, ratio.get('root', 0) - 3)
        ratio['guard'] = ratio.get('guard', 0) + 3
    if 2 in events:
        # 塔之诅咒：反制额度归零，只把当前实际减少的额度转给技能，
        # 避免与事件9同时生效时重复转移同一批反制额度。
        removed_guard = max(0, ratio.get('guard', 0))
        ratio['guard'] = 0
        ratio['bloom'] = ratio.get('bloom', 0) + removed_guard
    if 19 in events:
        # 装备牌+7，其他全 0；卡组余量由污水补足（见 deck 钩子）。
        ratio = {'thorn': 0, 'bloom': 0, 'root': ratio.get('root', 0) + 7, 'guard': 0}
    return ratio


class RealityEngineMixin:
    """操纵现实效果钩子。宿主需提供 ``self.reality_events: Set[int]``、
    ``self.reality_vars: Dict[str, int]``、``self.players``、``self.log_msg``、
    ``self.pn`` 等引擎常规成员。"""

    def reality_event_details(self):
        """本局生效事件明细（名称+描述），供对局内HUD显示。"""
        events = sorted(int(x) for x in (getattr(self, 'reality_events', None) or set()))
        if not events:
            return []
        return [
            {'id': cid,
             'name': str(REALITY_EVENTS.get(cid, {}).get('name') or cid),
             'desc': str(REALITY_EVENTS.get(cid, {}).get('desc') or '')}
            for cid in events
        ]

    def reality_active(self, event_id: int) -> bool:
        return int(event_id) in (getattr(self, 'reality_events', None) or set())

    # ------------------------------------------------------------------
    # 开局
    # ------------------------------------------------------------------
    def reality_initial_max_health_bonus(self) -> int:
        bonus = 0
        if self.reality_active(4):
            bonus += 50
        if self.reality_active(6):
            bonus += 900
        return bonus

    def reality_after_decks_built(self):
        """卡组建成后：事件19 洗入5张污水；事件12 全卡获得放逐。"""
        from cards import CardInstance
        if self.reality_active(19):
            for ps in self.players:
                for _ in range(5):
                    ps.deck.append(CardInstance('Sewage'))
            self.log_msg('操纵现实：将5张污水加入双方卡组')
        if self.reality_active(12):
            from cards import normalize_card_flags
            for ps in self.players:
                for card in ps.deck:
                    flags = set(getattr(card, 'instance_flags', set()) or set())
                    flags.add('exile')
                    card.instance_flags = flags
                    card_flags = set(getattr(card.card_def, 'flags', set()) or set())
                    card_flags = normalize_card_flags(card_flags | {'exile'})
                    try:
                        card.card_def.flags = card_flags
                    except Exception:
                        pass
            self.log_msg('操纵现实：所有卡获得放逐')

    def reality_game_start_setup(self):
        """对局正式开始（调度后）：战报展示生效事件；事件19 双方+10灼烧；事件6 倍率初始化。"""
        if self.reality_events:
            from reality_events import REALITY_EVENTS
            names = '、'.join(
                str(REALITY_EVENTS.get(cid, {}).get('name') or cid)
                for cid in sorted(self.reality_events)
            )
            self.log_msg(f'⚙ 操纵现实：本局生效事件——{names}')
        if self.reality_active(19):
            for ps in self.players:
                ps.fire += 10
            self.log_msg('操纵现实：双方获得10层灼烧')
        if self.reality_active(6):
            self.reality_vars['titan_damage_multiplier'] = 1

    # ------------------------------------------------------------------
    # 回合开始
    # ------------------------------------------------------------------
    def reality_turn_start_before_recovery(self, player_id: int):
        """回复费用之前：事件2 清空能量（魔力不清——2026-10-27修订，
        塔之诅咒原文仅"清空费用"指E）；事件3/10 更新回复修正。"""
        ps = self.players[player_id]
        if self.reality_active(2):
            ps.elixir = 0
            self.log_msg(f'{self.pn(player_id)}的操纵现实：回合开始清空能量')

    def reality_elixir_recovery_modifier(self, player_id: int) -> int:
        """事件3（-2起步每回合+1，上限7）与事件10（+5起步每回合-1）。

        事件10的负值保留到最终回复量结算，再由调用方把最终值钳制到 0。
        """
        modifier = 0
        ps = self.players[player_id]
        if self.reality_active(3):
            modifier += min(7, -2 + max(0, int(ps.custom_vars.get('reality_regen_ramp', 0) or 0)))
        if self.reality_active(10):
            modifier += 5 - max(0, int(ps.custom_vars.get('reality_regen_decay', 0) or 0))
        return modifier

    def reality_turn_start_advance_ramps(self, player_id: int):
        ps = self.players[player_id]
        if self.reality_active(3):
            ps.custom_vars['reality_regen_ramp'] = min(
                9, max(0, int(ps.custom_vars.get('reality_regen_ramp', 0) or 0)) + 1,
            )
        if self.reality_active(10):
            ps.custom_vars['reality_regen_decay'] = (
                max(0, int(ps.custom_vars.get('reality_regen_decay', 0) or 0)) + 1
            )

    def reality_extra_draw_count(self, player_id: int) -> int:
        extra = 0
        if self.reality_active(2):
            extra += 3
        if self.reality_active(5):
            extra += 4
        return extra

    def reality_extra_magic_recovery(self, player_id: int) -> int:
        return 5 if self.reality_active(11) else 0

    def reality_turn_start_tokens(self, player_id: int):
        """事件7：回合开始获得一次重抽机会；事件14：虚无拟态入手。"""
        ps = self.players[player_id]
        if self.reality_active(7):
            ps.custom_vars['reality_redraw_charges'] = (
                max(0, int(ps.custom_vars.get('reality_redraw_charges', 0) or 0)) + 1
            )
        if self.reality_active(14):
            self._reality_grant_void(player_id, mimic=True)

    def _reality_grant_void(self, player_id: int, mimic: bool = False, source_card=None):
        """发放带「虚无、放逐」标签的牌；事件16复制刚打出的第三张牌。"""
        from cards import CARD_DEFS, CardInstance
        if source_card is not None:
            card_id = str(getattr(source_card, 'def_id', '') or '')
            label = str(getattr(source_card, 'name_cn', '') or card_id)
        elif mimic:
            card_id = 'Mimic' if 'Mimic' in CARD_DEFS else 'Basic'
            label = '拟态' if card_id == 'Mimic' else '基本'
        else:
            card_id = 'Basic' if 'Basic' in CARD_DEFS else 'Void'
            label = '基本'
        if card_id not in CARD_DEFS:
            self.log_msg('操纵现实：卡定义不可用，跳过发放')
            return
        try:
            card = source_card.copy() if source_card is not None else CardInstance(card_id)
            flags = set(getattr(card, 'instance_flags', set()) or set())
            flags.update({'ethereal', 'exile'})
            card.instance_flags = flags
            self.players[player_id].hand.append(card)
            self.log_msg(f'{self.pn(player_id)}获得一张{label}（虚无，放逐）')
        except Exception as exc:  # 卡定义缺失时不阻塞回合
            self.log_msg(f'操纵现实：发放失败({type(exc).__name__})')

    # ------------------------------------------------------------------
    # 抽牌替代（事件7）
    # ------------------------------------------------------------------
    def reality_replaces_turn_draw(self) -> bool:
        return self.reality_active(7)

    def reality_turn_start_draw_choices(self, player_id: int, count: int) -> Optional[dict]:
        """事件7：本回合的抽牌改为三选一（权重=对应类型在选牌配额中的次数）。

        每个窗口只呈现一次三选一；多次抽牌通过 ``remaining`` 逐窗连续结算。
        """
        if not self.reality_active(7) or count <= 0:
            return None
        pick = self._reality_draw_option(player_id, 0)
        if pick is None:
            return None
        return {
            'kind': 'reality_draw',
            'choice_type': 'reality_draw',
            'title': {'zh': '操纵现实：三选一', 'en': 'Reality: choose one'},
            'minimum': 1,
            'maximum': 1,
            'cards': [pick],
            'remaining': int(count),
            'choice_params': {
                'options': list(pick.get('options') or []),
                'title': '操纵现实：三选一',
                'cancellable': False,
                'reality_remaining': int(count),
            },
        }

    def _reality_draw_option(self, player_id: int, seq: int) -> Optional[dict]:
        import random as _random
        from cards import CARD_DEFS, DRAFT_RATIO
        ratio = reality_adjusted_draft_ratio(
            DRAFT_RATIO, set(getattr(self, 'reality_events', set()) or set()),
        )
        allowed = getattr(self, 'allowed_card_ids', None)
        allowed_ids = set(CARD_DEFS) if allowed is None else set(allowed)
        weights = {
            card_id: float(getattr(card_def, 'draft_weight', 1.0) or 1.0) * ratio.get(
                str(getattr(card_def, 'card_type', '') or ''), 0,
            ) * (2.0 if self.reality_active(11) and int(getattr(card_def, 'cost_m', 0) or 0) > 0 else 1.0)
            for card_id, card_def in CARD_DEFS.items()
            if card_id in allowed_ids
            and int(getattr(card_def, 'count', 0) or 0) > 0
            and ratio.get(str(getattr(card_def, 'card_type', '') or ''), 0) > 0
        }
        weights = {card_id: weight for card_id, weight in weights.items() if weight > 0}
        if not weights:
            return None
        ids = list(weights.keys())
        # 按权重无放回抽取3个（与选牌 weighted_unique_sample 同思路）。
        picks: List[str] = []
        pool = list(ids)
        while pool and len(picks) < 3:
            choice = _random.choices(pool, weights=[weights[cid] for cid in pool], k=1)[0]
            picks.append(choice)
            pool.remove(choice)
        if not picks:
            return None
        return {
            'instance_id': f'reality-draw-{player_id}-{seq}',
            'def_id': picks[0],
            'options': picks,
        }

    def resolve_reality_draw_choice(self, player_id: int, choice_def_id: str, seq: int):
        """三选一确认：所选卡直接入手（不经过牌库）。"""
        from cards import CardInstance
        card = CardInstance(str(choice_def_id))
        if self.reality_active(12):
            flags = set(getattr(card, 'instance_flags', set()) or set())
            flags.add('exile')
            card.instance_flags = flags
        self.players[player_id].hand.append(card)
        self.log_msg(f'{self.pn(player_id)}三选一获得了{card.card_def.name_cn}')
        ps = self.players[player_id]
        ps.custom_vars.pop(f'reality_draw_seq_{seq}', None)

    # ------------------------------------------------------------------
    # 回合结束
    # ------------------------------------------------------------------
    def reality_end_of_turn(self, player_id: int):
        ps = self.players[player_id]
        if self.reality_active(2):
            discarded = [
                card for card in list(ps.hand)
                if getattr(card.card_def, 'card_type', '') != 'guard'
            ]
            for card in discarded:
                ps.hand.remove(card)
                ps.discard.append(card)
            if discarded:
                self.log_msg(f'{self.pn(player_id)}的操纵现实：回合结束丢弃{len(discarded)}张非反制牌')
        if self.reality_active(13):
            granted = 0
            for card in ps.hand:
                try:
                    card.swift_value = max(0, int(getattr(card, 'swift_value', 0) or 0)) + 1
                    granted += 1
                except Exception:
                    pass
            if granted:
                self.log_msg(f'{self.pn(player_id)}的操纵现实：手中{granted}张牌迅捷+1')

    # ------------------------------------------------------------------
    # 出牌结算
    # ------------------------------------------------------------------
    def reality_after_card_played(self, player_id: int, card) -> None:
        """出牌结算完成后：事件13沉重+1；15/16第三张牌；18进对手弃牌堆。"""
        ps = self.players[player_id]
        if self.reality_active(13) and card is not None:
            try:
                card.heavy_value = max(0, int(getattr(card, 'heavy_value', 0) or 0)) + 1
            except Exception:
                pass
        played_this_turn = int(ps.custom_vars.get('reality_cards_played_turn', 0) or 0) + 1
        ps.custom_vars['reality_cards_played_turn'] = played_this_turn
        if played_this_turn == 3:
            if self.reality_active(15):
                ps.skip_turn = max(0, int(getattr(ps, 'skip_turn', 0) or 0)) + 1
                self.log_msg(f'{self.pn(player_id)}的操纵现实：第三张牌，获得1层眩晕')
            if self.reality_active(16):
                self._reality_grant_void(player_id, source_card=card)

    def reality_turn_reset_play_counter(self, player_id: int):
        self.players[player_id].custom_vars.pop('reality_cards_played_turn', None)

    def reality_played_card_destination(self, player_id: int, card):
        """事件18：打出的牌进入对手弃牌堆。返回 True 表示已接管去向。"""
        if not self.reality_active(18) or card is None:
            return False
        opponents = [
            index for index, ps in enumerate(self.players)
            if index != player_id and ps.health > 0
        ] or [
            index for index in range(len(self.players)) if index != player_id
        ]
        if opponents:
            self.players[opponents[0]].discard.append(card)
            return True
        return False

    # ------------------------------------------------------------------
    # 伤害倍率（事件6）
    # ------------------------------------------------------------------
    def reality_damage_multiplier(self) -> float:
        if self.reality_active(6):
            return max(1.0, float(self.reality_vars.get('titan_damage_multiplier', 1) or 1))
        return 1.0

    def reality_advance_titan_multiplier(self):
        if self.reality_active(6):
            current = max(1.0, float(self.reality_vars.get('titan_damage_multiplier', 1) or 1))
            self.reality_vars['titan_damage_multiplier'] = current + 1.0

    # ------------------------------------------------------------------
    # 选牌钩子（事件11/12）
    # ------------------------------------------------------------------
    def reality_adjust_draft_weights(self, pool) -> None:
        """事件11：魔法卡选择权重翻倍（作用于卡实例 draft_weight）。"""
        if not self.reality_active(11):
            return
        for card in pool:
            try:
                if int(getattr(card.card_def, 'cost_m', 0) or 0) > 0:
                    card.draft_weight = float(getattr(card, 'draft_weight', 1.0) or 1.0) * 2.0
            except Exception:
                continue

    def reality_after_draft_pick(self, player_id: int, def_id: str) -> None:
        """事件12：每次选卡额外加入一张复制；复制在开局建立牌库时合入。"""
        if not self.reality_active(12):
            return
        copies = getattr(self, '_reality_draft_copies', None)
        if not isinstance(copies, list) or len(copies) <= player_id:
            copies = [[] for _ in self.players]
            self._reality_draft_copies = copies
        copies[player_id].append(str(def_id))
        self.log_msg(f'{self.pn(player_id)}的操纵现实：选卡复制已加入卡组')

    # ------------------------------------------------------------------
    # 目标规则（事件20）
    # ------------------------------------------------------------------
    def reality_forces_distinct_target(self) -> bool:
        return self.reality_active(20)

    def reality_last_target(self, player_id: int) -> Optional[int]:
        value = self.players[player_id].custom_vars.get('reality_last_target')
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def reality_record_last_target(self, player_id: int, target_id: Optional[int]):
        if target_id is None:
            return
        self.players[player_id].custom_vars['reality_last_target'] = int(target_id)

    def reality_cancel_target_restrictions(self) -> bool:
        """事件20：取消攻击牌无法指向自己的限制与不选目标 tag 的限制。"""
        return self.reality_active(20)
