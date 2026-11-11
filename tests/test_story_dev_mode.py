# -*- coding: utf-8 -*-
"""开发人员模式旅程：只保留当前旅程状态，不写永久数据。"""

import gc
import os
import tempfile
import unittest

import db


def _dev_state(*, phase='room', completed=False):
    return {
        'content_version': 'story-dev-mode-test',
        'phase': phase,
        'completed': completed,
        'dev_mode': True,
        'stage': 3,
        'difficulty': 'normal',
        'character_id': 'common_flower',
        'journey_mode': 'standard',
        'seed': 'seed-dev-mode',
        'map': {
            'floors': [{
                'floor': 16,
                'nodes': [{
                    'id': 'n1', 'type': 'boss', 'status': 'completed',
                    'x': 1, 'y': 1, 'floor': 16,
                }],
            }],
            'floor_count': 16,
            'edges': [],
        },
        'current_node_id': 'n1',
        'journey_route': [{'stage': 3, 'floor': 16, 'type': 'boss', 'completed': True}],
        'player': {
            'health': 42,
            'max_health': 70,
            'gold': 25,
            'deck': [{'def_id': 'basic', 'instance_id': 'c1'}],
            'relics': [],
            'enchantment_books': [],
        },
    }


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone() is not None


class StoryDeveloperModePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'story-dev-mode.sqlite3')
        db.init_db()
        self.user, error = db.create_user('StoryDevOwner', 'Passw0rd!xyz')
        assert self.user, error

    def tearDown(self):
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_dev_completion_skips_rewards_progress_and_history(self):
        pre_state = _dev_state()
        run, created = db.create_story_run(
            self.user['id'], 'seed-dev-mode', 'story-dev-mode-test', pre_state,
        )
        self.assertTrue(created)
        completed_state = _dev_state(phase='complete', completed=True)
        updated, outcome = db.commit_story_run_action(
            self.user['id'],
            run['id'],
            int(run['state_version']),
            'dev-finish-1',
            'resolve_room',
            {},
            completed_state,
        )
        self.assertEqual(outcome, 'committed')
        self.assertEqual(updated['state']['phase'], 'complete')
        self.assertTrue(updated['state']['completed'])
        with db.get_db_connection() as conn:
            if _table_exists(conn, 'story_reward_ledger'):
                ledgers = conn.execute(
                    'SELECT COUNT(*) AS n FROM story_reward_ledger',
                ).fetchone()['n']
            else:
                ledgers = 0
            currencies = conn.execute(
                'SELECT COUNT(*) AS n FROM user_currency_transactions',
            ).fetchone()['n']
            completions = conn.execute(
                'SELECT COUNT(*) AS n FROM story_progress_completions',
            ).fetchone()['n']
            if _table_exists(conn, 'story_run_summaries'):
                summaries = conn.execute(
                    'SELECT COUNT(*) AS n FROM story_run_summaries',
                ).fetchone()['n']
            else:
                summaries = 0
        self.assertEqual(ledgers, 0)
        self.assertEqual(currencies, 0)
        self.assertEqual(completions, 0)
        self.assertEqual(summaries, 0)
        self.assertEqual(db.get_user_thorn_dew(self.user['id'])['total'], 0)
        self.assertEqual(db.get_user_golden_dew(self.user['id']), 0)

    def test_dev_abandon_skips_history_summary(self):
        run, created = db.create_story_run(
            self.user['id'], 'seed-dev-abandon', 'story-dev-mode-test', _dev_state(),
        )
        self.assertTrue(created)
        self.assertTrue(db.abandon_story_run(self.user['id'], run['id']))
        with db.get_db_connection() as conn:
            summaries = (
                conn.execute(
                    'SELECT COUNT(*) AS n FROM story_run_summaries WHERE run_id = ?',
                    (run['id'],),
                ).fetchone()['n']
                if _table_exists(conn, 'story_run_summaries')
                else 0
            )
            run_row = conn.execute(
                'SELECT id FROM story_runs WHERE id = ?',
                (run['id'],),
            ).fetchone()
            action_count = conn.execute(
                'SELECT COUNT(*) AS n FROM story_run_actions WHERE run_id = ?',
                (run['id'],),
            ).fetchone()['n']
        self.assertEqual(summaries, 0)
        self.assertIsNone(run_row)
        self.assertEqual(action_count, 0)


class StoryDeveloperModeFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open('templates/story.html', encoding='utf-8') as handle:
            cls.template = handle.read()
        with open('static/js/story.js', encoding='utf-8') as handle:
            cls.script = handle.read()

    def test_start_option_is_offered_with_permanent_data_notice(self):
        self.assertIn('id="story-dev-mode-start"', self.template)
        self.assertIn('开启后本局不会向服务器上传任何永久数据', self.template)
        self.assertIn('devStartNote', self.script)
        self.assertIn('dev_mode: Boolean(', self.script)

    def test_developer_entry_is_hidden_by_default(self):
        self.assertIn(
            'id="story-dev-toggle" class="story-dev-toggle hidden"',
            self.template,
        )
        self.assertIn('function syncStoryDeveloperVisibility(', self.script)
        self.assertIn('storyRunIsDeveloper', self.script)


if __name__ == '__main__':
    unittest.main()
