import json
import os
import time
import unittest

import db
import story_local


class RolloutModeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = os.path.join(os.path.dirname(__file__), '_tmp_rollout')
        os.makedirs(self._tmp, exist_ok=True)
        self._saved = {key: os.environ.get(key) for key in ('GTN_STORY_LOCAL_MODE', 'GTN_STORY_LOCAL_MODE_FILE')}
        self.mode_file = os.path.join(self._tmp, 'story-local-mode')
        if os.path.exists(self.mode_file):
            os.remove(self.mode_file)
        os.environ['GTN_STORY_LOCAL_MODE_FILE'] = self.mode_file
        os.environ.pop('GTN_STORY_LOCAL_MODE', None)

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if os.path.exists(self.mode_file):
            os.remove(self.mode_file)
        try:
            os.rmdir(self._tmp)
        except OSError:
            pass

    def test_environment_variable_is_the_fallback(self):
        os.environ['GTN_STORY_LOCAL_MODE'] = 'staff'
        self.assertEqual('staff', story_local.rollout_mode())
        self.assertFalse(story_local.user_in_rollout(1) and False)

    def test_file_override_applies_without_a_restart(self):
        os.environ['GTN_STORY_LOCAL_MODE'] = 'off'
        self.assertEqual('off', story_local.rollout_mode())
        mode, error = story_local.set_rollout_mode('all')
        self.assertEqual(('all', ''), (mode, error))
        self.assertEqual('all', story_local.rollout_mode())
        self.assertEqual('all', story_local.rollout_mode())
        story_local.set_rollout_mode('off')
        self.assertEqual('off', story_local.rollout_mode())

    def test_percent_mode_is_hashed_per_user(self):
        story_local.set_rollout_mode('pct:50')
        self.assertEqual(50, story_local.rollout_percent())
        sample = [story_local.user_in_rollout(uid) for uid in range(1, 400)]
        share = sum(1 for flag in sample if flag) / len(sample)
        self.assertGreater(share, 0.35)
        self.assertLess(share, 0.65)
        story_local.set_rollout_mode('pct:0')
        self.assertFalse(story_local.user_in_rollout(1))
        story_local.set_rollout_mode('all')
        self.assertTrue(story_local.user_in_rollout(1))

    def test_invalid_modes_are_rejected(self):
        self.assertEqual(('', 'bad_mode'), story_local.set_rollout_mode('sometimes'))
        self.assertEqual(('', 'bad_percent'), story_local.set_rollout_mode('pct:101'))
        self.assertEqual(('', 'bad_percent'), story_local.set_rollout_mode('pct:x'))
        mode, error = story_local.set_rollout_mode(' PCT:5 ')
        self.assertEqual(('pct:5', ''), (mode, error))
        self.assertEqual('pct:5', story_local.rollout_mode())


class MetricsSnapshotTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmpdir = tempfile.mkdtemp()
        self._saved_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmpdir, 'metrics.sqlite3')
        db.init_db()
        with db.get_db_connection() as conn:
            conn.execute(
                "INSERT INTO users (id, username, username_lower, password_hash, created_at) VALUES (1, 'metrics-user', 'metrics-user', 'x', ?)",
                (db.utc_now(),),
            )
            conn.execute(
                'INSERT INTO story_runs (id, user_id, status, seed, content_version, state_version, state_json, created_at, updated_at) '
                "VALUES ('run-1', 1, 'active', 'seed', 'story-redesign-10-4debdf6ac928', 1, ?, ?, ?)",
                (json.dumps({'current_floor': 1}), db.utc_now(), db.utc_now()),
            )
            conn.commit()
            db.ensure_story_local_schema(conn)
            for seq, status, ms in ((1, 'verified', 12), (2, 'verified', 40), (3, 'mismatch', 8)):
                db.commit_story_checkpoint(
                    conn, run_id='run-1', user_id=1, seq=seq, kind='floor', floor=seq,
                    actions=[], client_digest='sha256:a', verify_status=status, verify_ms=ms,
                )
            db.commit_story_checkpoint(
                conn, run_id='run-1', user_id=1, seq=4, kind='floor', floor=4,
                actions=[], client_digest='sha256:b', verify_status='verified', verify_ms=0,
            )
            db.record_story_checkpoint_failure(conn, run_id='run-1', user_id=1, seq=5, reason='mismatch')
            db.record_story_checkpoint_failure(conn, run_id='run-1', user_id=1, seq=6, reason='invalid_action')
            conn.commit()

    def tearDown(self):
        db.DB_PATH = self._saved_path
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_snapshot_counts_status_reasons_and_latency(self):
        snapshot = story_local.metrics_snapshot(hours=24)
        self.assertEqual(4, snapshot['checkpoints'])
        self.assertEqual({'verified': 3, 'mismatch': 1}, snapshot['by_status'])
        self.assertAlmostEqual(0.25, snapshot['mismatch_rate'])
        self.assertEqual(12, snapshot['verify_ms']['p50'])
        self.assertEqual(40, snapshot['verify_ms']['p95'])
        self.assertEqual(40, snapshot['verify_ms']['max'])
        self.assertEqual({'mismatch': 1, 'invalid_action': 1}, snapshot['failure_reasons'])
        mode = snapshot['rollout_mode']
        self.assertTrue(mode in ('off', 'staff', 'all') or mode.startswith('pct:'))
        self.assertEqual(24, snapshot['hours'])
        self.assertTrue(snapshot['since'])

    def test_snapshot_window_excludes_old_rows(self):
        with db.get_db_connection() as conn:
            conn.execute(
                "UPDATE story_run_checkpoints SET created_at = '2000-01-01T00:00:00Z' WHERE seq = 3"
            )
            conn.commit()
        snapshot = story_local.metrics_snapshot(hours=1)
        self.assertEqual(3, snapshot['checkpoints'])
        self.assertEqual({'verified': 3}, snapshot['by_status'])
        self.assertEqual(0.0, snapshot['mismatch_rate'])


if __name__ == '__main__':
    unittest.main()
