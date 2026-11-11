# -*- coding: utf-8 -*-
"""卡牌与配装统计的天梯、娱乐原版及特殊娱乐模式筛选。"""

import gc
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import app
import db


ROOT = Path(__file__).resolve().parents[1]


class CardDraftModeFilterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'card-draft-mode-filters.sqlite3')
        db.init_db()
        self.samples = {
            '1v1': (1, 0),
            '1v1:ranked': (10, 4),
            '2v2:ranked': (20, 6),
            '1v1:original': (30, 9),
            '1v1:reality': (40, 12),
            '1v1:fancy': (50, 15),
            '1v1:ordered': (60, 18),
            '1v1:reality+fancy': (70, 21),
        }
        for mode, counts in self.samples.items():
            self.assertTrue(db.record_card_draft_counts(mode, {'alpha': counts}))
            self.assertTrue(db.record_card_draft_win_result(mode, [['alpha']], [0]))
            self.assertTrue(db.record_opening_event_pick_counts(mode, {'event_a': counts}))
            self.assertTrue(db.record_opening_event_win_result(mode, ['event_a'], [0]))

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    @staticmethod
    def modes(data):
        return {item['mode'] for item in data['items']}

    def test_ranked_and_original_filters_include_only_expected_modes(self):
        self.assertEqual(self.modes(db.list_card_draft_stats(mode='ranked')), {'1v1:ranked', '2v2:ranked'})
        self.assertEqual(self.modes(db.list_card_draft_stats(mode='original')), {'1v1:original'})

    def test_special_filters_and_combinations_count_each_enabled_mode(self):
        self.assertEqual(
            self.modes(db.list_card_draft_stats(mode='reality')),
            {'1v1:reality', '1v1:reality+fancy'},
        )
        self.assertEqual(
            self.modes(db.list_card_draft_stats(mode='fancy')),
            {'1v1:fancy', '1v1:reality+fancy'},
        )
        self.assertEqual(self.modes(db.list_card_draft_stats(mode='ordered')), {'1v1:ordered'})

    def test_engine_mode_filter_includes_all_variants_and_legacy_data(self):
        self.assertEqual(
            self.modes(db.list_card_draft_stats(mode='1v1')),
            {
                '1v1', '1v1:ranked', '1v1:original', '1v1:reality',
                '1v1:fancy', '1v1:ordered', '1v1:reality+fancy',
            },
        )
        merged = db.list_card_draft_stats(mode='reality', merge_modes=True)
        self.assertEqual(len(merged['items']), 1)
        self.assertEqual(merged['items'][0]['shown_count'], 110)
        self.assertEqual(merged['items'][0]['picked_count'], 33)

    def test_week_and_opening_event_filters_follow_same_rules(self):
        weekly = db.list_card_draft_stats(mode='reality', scope='week')
        self.assertEqual(self.modes(weekly), {'1v1:reality', '1v1:reality+fancy'})
        opening = db.list_opening_event_stats(mode='reality')
        self.assertEqual(self.modes(opening), {'1v1:reality', '1v1:reality+fancy'})
        opening_week = db.list_opening_event_stats(mode='fancy', scope='week')
        self.assertEqual(self.modes(opening_week), {'1v1:fancy', '1v1:reality+fancy'})
        opening_original = db.list_opening_event_stats(mode='original')
        self.assertEqual(self.modes(opening_original), {'1v1:original'})

    def test_mode_key_normalization_and_summary_mapping(self):
        self.assertEqual(db.card_draft_stats_mode_key('1v1:fancy+reality'), '1v1:reality+fancy')
        self.assertEqual(db.card_draft_stats_mode_key('1v1:unknown'), '')
        self.assertEqual(db._card_draft_stats_mode_from_summary({'match_mode': 'ranked_2v2'}, '2v2'), '2v2:ranked')
        self.assertEqual(
            db._card_draft_stats_mode_from_summary({'special_modes': ['fancy', 'reality']}, '1v1'),
            '1v1:reality+fancy',
        )
        self.assertEqual(db._card_draft_stats_mode_from_summary({}, '1v1'), '1v1')

    def test_app_room_mode_mapping(self):
        self.assertEqual(app.room_card_draft_stats_mode(SimpleNamespace(mode='1v1', match_mode='ranked_1v1')), '1v1:ranked')
        self.assertEqual(app.room_card_draft_stats_mode(SimpleNamespace(mode='1v1', match_mode='casual_1v1')), '1v1:original')
        self.assertEqual(
            app.room_card_draft_stats_mode(SimpleNamespace(
                mode='1v1', match_mode='casual_1v1', reality_mode=True, fancy_mode=True,
            )),
            '1v1:reality+fancy',
        )
        self.assertEqual(app.room_card_draft_stats_mode(SimpleNamespace(mode='2v2', match_mode='casual_2v2')), '2v2:original')

    def test_template_options_labels_and_script_version(self):
        template = (ROOT / 'templates/admin_stats.html').read_text(encoding='utf-8')
        for value, label in (
            ('ranked', '天梯'), ('original', '娱乐原版'), ('reality', '操纵现实'),
            ('fancy', '花样百出'), ('ordered', '乱中有序'),
        ):
            self.assertIn(f'<option value="{value}">', template)
            self.assertIn(label, template)
        self.assertIn('/static/js/admin.js?v=33', template)
        script = (ROOT / 'static/js/admin.js').read_text(encoding='utf-8')
        self.assertIn('function draftStatsModeLabel', script)
        self.assertIn('draftStatsModeLabel(item.mode)', script)


if __name__ == '__main__':
    unittest.main()
