# -*- coding: utf-8 -*-
"""同名卡副本的抽到胜利计数与历史重建口径。"""

import gc
import os
from pathlib import Path
import tempfile
import unittest

import db


ROOT = Path(__file__).resolve().parents[1]


class CardDraftCopyCountTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'card-draft-copy-counts.sqlite3')
        db.init_db()

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def stats(self, table='card_draft_win_stats', mode='1v1'):
        with db.get_db_connection() as conn:
            rows = conn.execute(
                f'''SELECT card_id,SUM(picked_games) AS picked_games,
                           SUM(win_games) AS win_games,SUM(draw_games) AS draw_games
                    FROM {table} WHERE mode=? GROUP BY card_id ORDER BY card_id''',
                (mode,),
            ).fetchall()
        return {
            row['card_id']: (row['picked_games'], row['win_games'], row['draw_games'])
            for row in rows
        }

    def test_live_result_counts_winning_copies_but_not_duplicate_games(self):
        db.record_card_draft_counts('1v1', {'alpha': (10, 5), 'beta': (10, 4)})
        self.assertTrue(db.record_card_draft_win_result(
            '1v1',
            [
                ['alpha', 'alpha', 'alpha', 'beta'],
                ['alpha', 'beta', 'beta'],
            ],
            [0],
            player_rank_tiers=[9, 1],
        ))
        # 平局只增加一次抽到局数和平局局数，不把同名副本累计到胜利卡数。
        self.assertTrue(db.record_card_draft_win_result(
            '1v1', [['alpha', 'alpha'], ['alpha']], [], result='draw',
            player_rank_tiers=[9, 1],
        ))
        expected = {'alpha': (4, 3, 2), 'beta': (2, 1, 0)}
        self.assertEqual(self.stats(), expected)
        self.assertEqual(self.stats('card_draft_win_stats_weekly'), expected)

        payload = db.list_card_draft_stats(mode='1v1', merge_modes=True)
        items = {item['card_id']: item for item in payload['items']}
        self.assertEqual(items['alpha']['win_games'], 3)
        self.assertEqual(items['alpha']['picked_games'], 4)
        self.assertAlmostEqual(items['alpha']['card_win_rate'], 60.0)
        self.assertAlmostEqual(items['alpha']['winner_pick_rate'], 75.0)
        self.assertAlmostEqual(items['beta']['card_win_rate'], 25.0)
        self.assertAlmostEqual(items['beta']['winner_pick_rate'], 25.0)

    def test_rebuild_uses_the_same_copy_count_rules_for_total_and_weekly(self):
        common = {
            'mode': '1v1',
            'match_type': 'ranked',
            'match_mode': 'ranked_1v1',
            'players': ['winner', 'loser'],
            'player_ids': [None, None],
            'duration_seconds': 300,
            'valid_for_stats': True,
            'valid_for_ranking': True,
        }
        db.save_match_summary({
            **common,
            'started_at': '2026-11-08T10:00:00Z',
            'ended_at': '2026-11-08T10:05:00Z',
            'winner_index': 0,
            'winner_player_indices': [0],
            'player_rank_tiers': [9, 1],
            'result': 'finished',
            'draft_card_ids_by_player': [
                ['alpha', 'alpha', 'beta'],
                ['alpha', 'beta', 'beta', 'beta'],
            ],
        })
        db.save_match_summary({
            **common,
            'player_ids': [101, 102],
            'started_at': '2026-11-08T11:00:00Z',
            'ended_at': '2026-11-08T11:05:00Z',
            'winner_index': -1,
            'winner_player_indices': [],
            'result': 'draw',
            'gr_result': {'rank': {'before': {
                '101': {'tier_index': 9}, '102': {'tier_index': 1},
            }}},
            'draft_card_ids_by_player': [['alpha', 'alpha'], ['alpha']],
        })
        result = db.rebuild_card_draft_win_stats_from_matches()
        self.assertEqual(result['counted_matches'], 2)
        expected = {'alpha': (4, 2, 2), 'beta': (2, 1, 0)}
        self.assertEqual(self.stats(mode='1v1:ranked'), expected)
        self.assertEqual(self.stats('card_draft_win_stats_weekly', mode='1v1:ranked'), expected)
        with db.get_db_connection() as conn:
            rank_rows = {
                (row['rank_tier'], row['card_id']): (row['picked_games'], row['win_games'], row['draw_games'])
                for row in conn.execute(
                    "SELECT rank_tier,card_id,picked_games,win_games,draw_games FROM card_draft_win_stats WHERE mode='1v1:ranked'"
                )
            }
        self.assertEqual(rank_rows[(9, 'alpha')], (2, 2, 1))
        self.assertEqual(rank_rows[(1, 'alpha')], (2, 0, 1))
        self.assertEqual(rank_rows[(9, 'beta')], (1, 1, 0))
        self.assertEqual(rank_rows[(1, 'beta')], (1, 0, 0))

    def test_admin_labels_describe_card_copies_and_refresh_script(self):
        template = (ROOT / 'templates/admin_stats.html').read_text(encoding='utf-8')
        script = (ROOT / 'static/js/admin.js').read_text(encoding='utf-8')
        self.assertIn('<option value="win_games">胜利卡数</option>', template)
        self.assertIn('抽到胜利（卡数）', script)
        self.assertIn('胜者选中（卡数）', script)
        self.assertIn('玩家×卡牌×对局去重', template)
        self.assertIn('同名卡副本数量累计', template)
        self.assertIn('/static/js/admin.js?v=33', template)


if __name__ == '__main__':
    unittest.main()
