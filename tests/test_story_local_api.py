import json

import pytest

import db
import story_local
import story_verify

def _start_action(state):
    room = state.get('room') or {}
    biome = (room.get('biomes') or ['garden'])[0]
    difficulty = (room.get('difficulties') or ['normal'])[0]
    mode = (room.get('modes') or ['standard'])[0]
    return {'type': 'start_journey', 'payload': {'biome': biome, 'difficulty': difficulty, 'mode': mode}}


def _setup(monkeypatch, tmp_path, rollout='all'):
    monkeypatch.setenv('GTN_STORY_LOCAL_MODE', rollout)
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'story-local-api.sqlite3'))
    db.init_db()
    with db.get_db_connection() as conn:
        conn.execute(
            'INSERT INTO users(id, username, username_lower, password_hash, created_at) VALUES (?,?,?,?,?)',
            (1, 'localapi', 'localapi', 'unused', db.utc_iso(db.utc_now_dt())),
        )
        conn.commit()
    story_local._rate_buckets.clear()


def _start(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    payload, status = story_local.start_run(1)
    assert status == 200, payload
    return payload


def _digest(state, seed):
    result = story_verify.replay_checkpoint(state, [_start_action(state)], seed)
    assert result['ok'], result
    return result


def test_rollout_gate_blocks_when_off(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, rollout='off')
    payload, status = story_local.start_run(1)
    assert status == 403
    assert payload['error'] == 'local_mode_disabled'


def test_rollout_percent_is_stable(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path, rollout='pct:0')
    assert story_local.user_in_rollout(1) is False
    monkeypatch.setenv('GTN_STORY_LOCAL_MODE', 'pct:100')
    assert story_local.user_in_rollout(1) is True
    monkeypatch.setenv('GTN_STORY_LOCAL_MODE', 'pct:25')
    first = story_local.user_in_rollout(1)
    assert first == story_local.user_in_rollout(1)
    monkeypatch.setenv('GTN_STORY_LOCAL_MODE', 'all')
    assert story_local.user_in_rollout(1) is True


def test_start_run_returns_seed_and_state(monkeypatch, tmp_path):
    payload = _start(monkeypatch, tmp_path)
    assert payload['run']['seed']
    assert payload['run']['content_version'].startswith('story-redesign-10-')
    assert payload['state']['phase']
    with db.get_db_connection() as conn:
        row = conn.execute('SELECT * FROM story_runs WHERE id = ?', (payload['run']['id'],)).fetchone()
    assert row['local_mode'] == 1


def test_checkpoint_accepts_a_matching_digest(monkeypatch, tmp_path):
    started = _start(monkeypatch, tmp_path)
    run_id = started['run']['id']
    result = _digest(started['state'], started['run']['seed'])
    payload, status = story_local.submit_checkpoint(1, run_id, {
        'seq': 1,
        'kind': 'floor',
        'floor': 2,
        'actions': [_start_action(started['state'])],
        'client_digest': result['digest'],
        'prev_digest': '',
    })
    assert status == 200, payload
    assert payload['seq'] == 1
    with db.get_db_connection() as conn:
        row = conn.execute('SELECT * FROM story_runs WHERE id = ?', (run_id,)).fetchone()
        checkpoint = db.latest_story_checkpoint(run_id)
    assert row['last_verified_seq'] == 1
    assert row['last_verified_floor'] == 2
    assert row['state_digest'] == result['digest']
    assert checkpoint['verify_status'] == 'verified'


def test_checkpoint_mismatch_keeps_the_run_unadvanced(monkeypatch, tmp_path):
    started = _start(monkeypatch, tmp_path)
    run_id = started['run']['id']
    payload, status = story_local.submit_checkpoint(1, run_id, {
        'seq': 1,
        'kind': 'floor',
        'floor': 3,
        'actions': [_start_action(started['state'])],
        'client_digest': 'sha256:' + '0' * 64,
    })
    assert status == 409
    assert payload['error'] == 'STORY_CHECKPOINT_MISMATCH'
    with db.get_db_connection() as conn:
        row = conn.execute('SELECT * FROM story_runs WHERE id = ?', (run_id,)).fetchone()
        row_digest = row['state_digest']
    assert row['last_verified_seq'] == 0
    assert row_digest == ''
    assert row['suspicion_score'] == 1
    failures = db.list_story_checkpoint_failures(limit=10)
    assert [item['reason'] for item in failures] == ['mismatch']
    assert failures[0]['username'] == 'localapi'
    assert failures[0]['run_id'] == run_id
    assert failures[0]['seq'] == 1
    assert failures[0]['action_count'] == 1
    summary = db.story_checkpoint_failure_summary()
    assert summary == {'total': 1, 'by_reason': {'mismatch': 1}}


def test_checkpoint_rejects_out_of_order_and_duplicates(monkeypatch, tmp_path):
    started = _start(monkeypatch, tmp_path)
    run_id = started['run']['id']
    result = _digest(started['state'], started['run']['seed'])
    body = {
        'seq': 1,
        'kind': 'combat',
        'floor': 1,
        'actions': [_start_action(started['state'])],
        'client_digest': result['digest'],
    }
    assert story_local.submit_checkpoint(1, run_id, body)[1] == 200
    duplicate, dup_status = story_local.submit_checkpoint(1, run_id, body)
    assert dup_status == 200 and duplicate.get('duplicate') is True
    skipped, skip_status = story_local.submit_checkpoint(1, run_id, {
        'seq': 3, 'kind': 'combat', 'floor': 1, 'actions': [], 'client_digest': result['digest'],
    })
    assert skip_status == 409
    assert skipped['error'] == 'STORY_CHECKPOINT_OUT_OF_ORDER'


def test_rate_limit_kicks_in(monkeypatch, tmp_path):
    started = _start(monkeypatch, tmp_path)
    monkeypatch.setattr(story_local, 'RATE_MAX_CHECKPOINTS', 2)
    run_id = started['run']['id']
    for seq in (1, 2, 3):
        payload, status = story_local.submit_checkpoint(1, run_id, {'seq': 0, 'actions': []})
    assert status == 429
    assert payload['error'] == 'STORY_CHECKPOINT_RATE_LIMIT'


def test_resume_and_finish_use_the_last_verified_checkpoint(monkeypatch, tmp_path):
    started = _start(monkeypatch, tmp_path)
    run_id = started['run']['id']
    result = _digest(started['state'], started['run']['seed'])
    assert story_local.submit_checkpoint(1, run_id, {
        'seq': 1, 'kind': 'floor', 'floor': 4,
        'actions': [_start_action(started['state'])], 'client_digest': result['digest'],
    })[1] == 200
    resumed, resume_status = story_local.resume_run(1, run_id)
    assert resume_status == 200
    assert resumed['checkpoint']['seq'] == 1
    assert resumed['checkpoint']['floor'] == 4
    finished, finish_status = story_local.finish_run(1, run_id)
    assert finish_status == 200
    assert finished['last_verified_floor'] == 4
    with db.get_db_connection() as conn:
        row = conn.execute('SELECT status FROM story_runs WHERE id = ?', (run_id,)).fetchone()
    assert row['status'] == 'completed'


def test_foreign_run_is_not_visible(monkeypatch, tmp_path):
    started = _start(monkeypatch, tmp_path)
    payload, status = story_local.resume_run(999, started['run']['id'])
    assert status == 404
    assert payload['error'] == 'run_not_found'
