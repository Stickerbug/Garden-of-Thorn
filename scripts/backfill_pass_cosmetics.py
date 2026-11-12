"""补发通行证里程碑实物：玩家皮肤 + 暗港战斗背景。

背景：
- 通行证的 10 个外观格是 5 个玩家皮肤 + 5 个卡牌皮肤（卡背）的混合；
  早期上线时部分格子发错了种类（全发成玩家皮肤），已领取的玩家既要保留当时
  实际到手的实物，也要按当前里程碑表补发正确的那一份。
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
    # 偏好表：把「暗港当作主题背景」的选择迁到战斗背景，否则改分类后玩家看到的是经典战场。
    preferred = conn.execute(
        '''UPDATE user_background_preferences
           SET battle_background_id = ?, updated_at = ?
           WHERE theme_background_id = ?''',
        (DARK_HARBOR, db.utc_iso(datetime.now(timezone.utc)), DARK_HARBOR),
    ).rowcount
    reset = conn.execute(
        '''UPDATE user_background_preferences
           SET theme_background_id = 'classic'
           WHERE theme_background_id = ?''',
        (DARK_HARBOR,),
    ).rowcount
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {'moved': moved, 'removed': removed, 'preferred': preferred, 'theme_reset': reset}


def backfill_claims(conn, dry_run=False):
    """按已领取记录重放实物奖励（只补外观，不补货币）。"""
    now_text = db.utc_iso(datetime.now(timezone.utc))
    rows = conn.execute(
        'SELECT user_id, track, level, season_id, reward_json FROM battle_pass_claims '
        'ORDER BY user_id, track, level'
    ).fetchall()
    granted = []
    seen = set()

    def grant(user_id, reward):
        if not reward or reward.get('kind') not in COSMETIC_KINDS:
            return
        item_id = str(reward.get('item_id') or '')
        if not item_id:
            return
        key = (int(user_id), reward['kind'], item_id)
        if key in seen:
            return
        seen.add(key)
        bp._grant_cosmetic(conn, key[0], key[1], key[2], now_text)
        granted.append({'user_id': key[0], 'kind': key[1], 'item_id': key[2]})

    for row in rows:
        # ① 当时实际写进 reward_json 的那份实物（保留既得利益）
        stored = None
        try:
            import json
            stored = json.loads(str(row['reward_json'] or '{}'))
        except (TypeError, ValueError):
            stored = None
        grant(row['user_id'], stored)
        # ② 按当前里程碑表应得的那份实物（修正发错种类的格子）
        grant(row['user_id'], bp.reward_for(int(row['level']), str(row['track'])))
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
    print(f"dark_harbor: moved={background_result['moved']} removed={background_result['removed']} "
          f"preferred={background_result['preferred']} theme_reset={background_result['theme_reset']}")
    print(f"cosmetic grants replayed: {len(granted)}")
    print(f"player skins granted: {len(player_skin_grants)}")
    for item in player_skin_grants:
        print(f"  user={item['user_id']} skin={item['item_id']}")


if __name__ == '__main__':
    main()
