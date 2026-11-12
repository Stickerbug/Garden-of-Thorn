"""补发通行证里程碑实物：玩家皮肤 + 暗港战斗背景。

背景：
- 2026-11-12 之前通行证皮肤格发的是卡牌皮肤（card_skin），但赛季计划上线的是
  五款「塔之诅咒」玩家皮肤；已领取过这些格子的玩家需要补发对应玩家皮肤。
- 「暗港」背景原先登记为主题背景（kind='theme'），按要求改为战斗背景（kind='battle'），
  已入库的旧记录也要搬到 battle 分类下。

脚本幂等：重复执行只补缺、不重复发放。用法（服务端）：

    PYTHONPATH=/opt/gtn-release /opt/gtn-release/venv/bin/python \
        scripts/backfill_pass_cosmetics.py [--dry-run]
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backgrounds  # noqa: E402
import battle_pass as bp  # noqa: E402
import db  # noqa: E402
import player_skins  # noqa: E402


DARK_HARBOR = 'tower_curse_dark_harbor'
COSMETIC_KINDS = ('title', 'card_skin', 'player_skin', 'background')


def migrate_dark_harbor(conn, dry_run=False):
    """把暗港背景从主题分类搬到战斗分类（PK 是 user+kind+id，先插后删）。"""
    moved = conn.execute(
        '''INSERT OR IGNORE INTO user_backgrounds
           (user_id, kind, background_id, acquired_source, acquired_ref, acquired_at)
           SELECT user_id, 'battle', background_id, acquired_source, acquired_ref, acquired_at
           FROM user_backgrounds WHERE background_id = ? AND kind = 'theme' ''',
        (DARK_HARBOR,),
    ).rowcount
    removed = conn.execute(
        "DELETE FROM user_backgrounds WHERE background_id = ? AND kind = 'theme'",
        (DARK_HARBOR,),
    ).rowcount
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {'moved': moved, 'removed': removed}


def backfill_claims(conn, dry_run=False):
    """按已领取记录重放实物奖励（只补外观，不补货币）。"""
    now_text = db.utc_iso(datetime.now(timezone.utc))
    rows = conn.execute(
        'SELECT user_id, track, level, season_id FROM battle_pass_claims ORDER BY user_id, track, level'
    ).fetchall()
    granted = []
    seen = set()
    for row in rows:
        reward = bp.reward_for(int(row['level']), str(row['track']))
        if not reward or reward.get('kind') not in COSMETIC_KINDS:
            continue
        key = (int(row['user_id']), reward['kind'], str(reward.get('item_id') or ''))
        if key in seen:
            continue
        seen.add(key)
        bp._grant_cosmetic(conn, key[0], key[1], key[2], now_text)
        granted.append({'user_id': key[0], 'kind': key[1], 'item_id': key[2]})
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return granted


def main():
    parser = argparse.ArgumentParser(description='补发通行证玩家皮肤与暗港战斗背景')
    parser.add_argument('--dry-run', action='store_true', help='只统计，不写库')
    args = parser.parse_args()

    with db.get_db_connection() as conn:
        bp.ensure_pass_schema(conn)
        bp.ensure_pass_titles(conn)
        player_skins.ensure_player_skin_schema(conn)
        backgrounds.ensure_background_schema(conn)

        background_result = migrate_dark_harbor(conn, dry_run=args.dry_run)
        granted = backfill_claims(conn, dry_run=args.dry_run)

    player_skin_grants = [g for g in granted if g['kind'] == 'player_skin']
    print(f"dark_harbor: moved={background_result['moved']} removed={background_result['removed']}")
    print(f"cosmetic grants replayed: {len(granted)}")
    print(f"player skins granted: {len(player_skin_grants)}")
    for item in player_skin_grants:
        print(f"  user={item['user_id']} skin={item['item_id']}")


if __name__ == '__main__':
    main()
