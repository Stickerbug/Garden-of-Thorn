import json

import db


def _bootstrap(monkeypatch, tmp_path):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'story-local.sqlite3'))
    db.init_db()
    conn = db.get_db_connection()
    conn.execute(
        'INSERT INTO users(id, username, username_lower, password_hash, created_at) VALUES (?,?,?,?,?)',
        (1, 'local1', 'local1', 'unused', db.utc_iso(db.utc_now_dt())),
    )
    run_id = 'run-local-1'
    conn.execute(
        '''INSERT INTO story_runs
           (id, user_id, seed, content_version, state_json, state_version, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (run_id, 1, 'seed-local', 'story-redesign-10-test', '{}', 1, 'active',
         db.utc_iso(db.utc_now_dt()), db.utc_iso(db.utc_now_dt())),
    )
    conn.commit()
    return conn, run_id


def test_local_schema_is_idempotent(monkeypatch, tmp_path):
    conn, _run_id = _bootstrap(monkeypatch, tmp_path)
    db.ensure_story_local_schema(conn)
    db.ensure_story_local_schema(conn)
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(story_runs)').fetchall()}
    for name in ('local_mode', 'last_verified_floor', 'last_verified_seq',
                 'checkpoint_seq', 'state_digest', 'suspicion_score', 'state_mutated_by_admin'):
        assert name in columns
    tables = {row['name'] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    assert {'story_run_checkpoints', 'story_run_rewards'} <= tables
    conn.close()


def test_checkpoint_insert_is_unique_per_sequence(monkeypatch, tmp_path):
    conn, run_id = _bootstrap(monkeypatch, tmp_path)
    db.ensure_story_local_schema(conn)
    first, status = db.commit_story_checkpoint(
        conn, run_id=run_id, user_id=1, seq=1, kind='combat', floor=2,
        actions=[{'type': 'end_turn', 'payload': {}}], client_digest='sha256:' + 'a' * 64,
        verify_status='verified', server_digest='sha256:' + 'a' * 64,
        state={'phase': 'combat', 'current_floor': 2},
    )
    conn.commit()
    assert status == 'stored'
    assert first['action_count'] == 1
    again, status = db.commit_story_checkpoint(
        conn, run_id=run_id, user_id=1, seq=1, kind='combat', floor=2,
        actions=[], client_digest='sha256:' + 'b' * 64,
    )
    conn.commit()
    assert status == 'duplicate'
    assert again['client_digest'] == first['client_digest']
    assert conn.execute('SELECT COUNT(*) FROM story_run_checkpoints').fetchone()[0] == 1
    conn.close()


def test_verified_checkpoint_advances_the_run(monkeypatch, tmp_path):
    conn, run_id = _bootstrap(monkeypatch, tmp_path)
    db.ensure_story_local_schema(conn)
    db.commit_story_checkpoint(
        conn, run_id=run_id, user_id=1, seq=1, kind='floor', floor=3,
        actions=[], client_digest='sha256:' + 'c' * 64,
        verify_status='verified', server_digest='sha256:' + 'c' * 64,
        state={'phase': 'room', 'current_floor': 3},
    )
    db.commit_story_checkpoint(
        conn, run_id=run_id, user_id=1, seq=2, kind='combat', floor=4,
        actions=[], client_digest='sha256:' + 'd' * 64,
        verify_status='pending',
    )
    conn.commit()
    run = conn.execute('SELECT * FROM story_runs WHERE id = ?', (run_id,)).fetchone()
    assert run['local_mode'] == 1
    assert run['last_verified_floor'] == 3
    assert run['last_verified_seq'] == 1
    assert run['checkpoint_seq'] == 2
    assert run['state_digest'] == 'sha256:' + 'c' * 64
    conn.close()


def test_latest_checkpoint_prefers_verified(monkeypatch, tmp_path):
    conn, run_id = _bootstrap(monkeypatch, tmp_path)
    db.ensure_story_local_schema(conn)
    for seq, status in ((1, 'verified'), (2, 'mismatch')):
        db.commit_story_checkpoint(
            conn, run_id=run_id, user_id=1, seq=seq, kind='combat', floor=seq,
            actions=[], client_digest='sha256:' + str(seq) * 64, verify_status=status,
            state={'phase': 'combat', 'current_floor': seq},
        )
    conn.commit()
    conn.close()
    verified = db.latest_story_checkpoint(run_id, verified_only=True)
    latest = db.latest_story_checkpoint(run_id, verified_only=False)
    assert verified['seq'] == 1
    assert latest['seq'] == 2
    assert latest['verify_status'] == 'mismatch'
    listed = db.list_story_checkpoints(run_id)
    assert [item['seq'] for item in listed] == [2, 1]


def test_run_rewards_are_idempotent(monkeypatch, tmp_path):
    conn, run_id = _bootstrap(monkeypatch, tmp_path)
    db.ensure_story_local_schema(conn)
    assert db.record_story_run_reward(conn, run_id, 5, 'floor_clear', 30) is True
    assert db.record_story_run_reward(conn, run_id, 5, 'floor_clear', 30) is False
    assert db.record_story_run_reward(conn, run_id, 5, 'dew', 12) is True
    conn.commit()
    total = conn.execute('SELECT COUNT(*) FROM story_run_rewards').fetchone()[0]
    assert total == 2
    conn.close()


def test_checkpoint_actions_round_trip(monkeypatch, tmp_path):
    conn, run_id = _bootstrap(monkeypatch, tmp_path)
    db.ensure_story_local_schema(conn)
    actions = [{'type': 'play_card', 'payload': {'card_id': 'strike'}}]
    db.commit_story_checkpoint(
        conn, run_id=run_id, user_id=1, seq=1, kind='combat', floor=1,
        actions=actions, client_digest='sha256:' + 'e' * 64,
    )
    conn.commit()
    payload = db.latest_story_checkpoint(run_id, verified_only=False)
    assert payload['actions'] == actions
    assert json.dumps(payload['actions'])[0] == '['
    conn.close()
