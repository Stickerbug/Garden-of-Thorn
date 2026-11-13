"""本地模式爬塔：引擎在浏览器里跑，服务端只校验检查点。

约定（见 docs/aegis/plans/2026-11-13-story-local-engine.md）：
- 客户端在楼层层切换与每场战斗结束时各提交一次检查点；
- 每个检查点携带自上一个已校验点以来的动作日志与客户端摘要；
- 服务端用同一份 story_engine 从上一个已校验状态重放，摘要一致才推进；
- 校验失败时按上一个已校验存档结算并结束本轮（视为放弃）。
"""

import hashlib
import json
import os
import secrets
import threading
import time

import db
import story_mode
import story_verify

ROLLOUT_ENV = 'GTN_STORY_LOCAL_MODE'
RATE_WINDOW_SECONDS = 60
RATE_MAX_CHECKPOINTS = 30
VERIFY_STATUS_BY_REASON = {
    'mismatch': 'mismatch',
    'invalid_action': 'invalid_action',
    'engine_error': 'error',
    'actions_not_list': 'invalid_payload',
    'action_limit': 'invalid_payload',
    'action_not_object': 'invalid_payload',
    'action_type_missing': 'invalid_payload',
    'action_payload_invalid': 'invalid_payload',
}

_rate_buckets = {}
_rate_lock = threading.Lock()
_mode_file_cache = {'path': '', 'mtime': -1.0, 'value': ''}
_mode_file_lock = threading.Lock()

VALID_MODES = ('off', 'staff', 'all')


def _mode_file_path():
    configured = (os.environ.get('GTN_STORY_LOCAL_MODE_FILE') or '').strip()
    if configured:
        return configured
    data_dir = (os.environ.get('GTN_DATA_DIR') or '').strip()
    base = data_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    return os.path.join(base, 'story-local-mode')


def _mode_from_file():
    """运营开关文件：改了立即生效，不需要重启进程。"""
    path = _mode_file_path()
    with _mode_file_lock:
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            _mode_file_cache.update({'path': path, 'mtime': -1.0, 'value': ''})
            return ''
        if _mode_file_cache['path'] == path and _mode_file_cache['mtime'] == mtime:
            return _mode_file_cache['value']
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                value = (handle.readline() or '').strip().lower()
        except OSError:
            value = ''
        _mode_file_cache.update({'path': path, 'mtime': mtime, 'value': value})
        return value


def rollout_mode():
    return _mode_from_file() or (os.environ.get(ROLLOUT_ENV) or 'off').strip().lower()


def set_rollout_mode(mode):
    """写入运营开关文件；返回 (mode, error)。"""
    value = str(mode or '').strip().lower()
    if value.startswith('pct:'):
        try:
            percent = int(value.split(':', 1)[1])
        except (TypeError, ValueError):
            return '', 'bad_percent'
        if percent < 0 or percent > 100:
            return '', 'bad_percent'
        value = f'pct:{percent}'
    elif value not in VALID_MODES:
        return '', 'bad_mode'
    path = _mode_file_path()
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='') as handle:
            handle.write(value + '\n')
    except OSError:
        return '', 'write_failed'
    return value, ''


def metrics_snapshot(hours=24):
    """最近窗口内的校验指标：检查点状态分布、重放耗时、失败原因、本地局数。"""
    window = max(1, min(24 * 30, int(hours or 24)))
    since = db.utc_iso(db.utc_now_dt() - __import__('datetime').timedelta(hours=window))
    with db.get_db_connection() as conn:
        db.ensure_story_local_schema(conn)
        status_rows = conn.execute(
            'SELECT verify_status, COUNT(*) AS n FROM story_run_checkpoints '
            'WHERE created_at >= ? GROUP BY verify_status',
            (since,),
        ).fetchall()
        ms_rows = conn.execute(
            'SELECT verify_ms FROM story_run_checkpoints WHERE created_at >= ? AND verify_ms > 0 '
            'ORDER BY verify_ms ASC',
            (since,),
        ).fetchall()
        reason_rows = conn.execute(
            'SELECT reason, COUNT(*) AS n FROM story_checkpoint_failures '
            'WHERE created_at >= ? GROUP BY reason ORDER BY n DESC',
            (since,),
        ).fetchall()
        runs = conn.execute(
            'SELECT COUNT(*) AS n FROM story_runs WHERE local_mode = 1 AND status = \'active\''
        ).fetchone()
    by_status = {str(row['verify_status'] or 'unknown'): int(row['n']) for row in status_rows}
    latencies = [int(row['verify_ms']) for row in ms_rows]

    def _percentile(values, ratio):
        if not values:
            return 0
        index = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
        return values[index]

    total = sum(by_status.values())
    mismatched = sum(
        count for status, count in by_status.items() if status not in ('verified', 'pending')
    )
    return {
        'hours': window,
        'since': since,
        'checkpoints': total,
        'by_status': by_status,
        'mismatch_rate': round(mismatched / total, 6) if total else 0.0,
        'verify_ms': {
            'p50': _percentile(latencies, 0.5),
            'p95': _percentile(latencies, 0.95),
            'max': latencies[-1] if latencies else 0,
        },
        'failure_reasons': {str(row['reason'] or 'unknown'): int(row['n']) for row in reason_rows},
        'active_local_runs': int(runs['n'] if runs else 0),
        'rollout_mode': rollout_mode(),
        'in_rollout_percent': rollout_percent(),
    }


def rollout_percent():
    mode = rollout_mode()
    if not mode.startswith('pct:'):
        return 0
    try:
        return max(0, min(100, int(mode.split(':', 1)[1])))
    except (TypeError, ValueError):
        return 0


def user_in_rollout(user_id):
    mode = rollout_mode()
    if mode in ('', 'off', '0', 'false', 'no'):
        return False
    if mode in ('all', 'on', '1', '100'):
        return True
    if mode == 'staff':
        return bool(db.feedback_is_staff(user_id))
    percent = rollout_percent()
    if percent <= 0:
        return False
    digest = hashlib.sha256(f'story-local:{int(user_id)}'.encode('utf-8')).hexdigest()
    return int(digest[:8], 16) % 100 < percent


def _rate_limited(user_id):
    now = time.time()
    key = int(user_id)
    with _rate_lock:
        stamps = [stamp for stamp in _rate_buckets.get(key, []) if now - stamp < RATE_WINDOW_SECONDS]
        stamps.append(now)
        _rate_buckets[key] = stamps
        return len(stamps) > RATE_MAX_CHECKPOINTS


def _load_run(conn, user_id, run_id):
    return conn.execute(
        'SELECT * FROM story_runs WHERE id = ? AND user_id = ?',
        (str(run_id), int(user_id)),
    ).fetchone()


def start_run(user_id, character_id='common_flower'):
    """开始一局本地模式：下发 seed 与初始状态。"""
    if not user_in_rollout(user_id):
        return {'error': 'local_mode_disabled'}, 403
    seed = secrets.token_hex(16)
    state = story_mode.build_initial_story_state(seed, character_id)
    state['dev_mode'] = False
    run, created = db.create_story_run(user_id, seed, story_mode.STORY_CONTENT_VERSION, state)
    if not run:
        return {'error': 'run_create_failed'}, 500
    with db.get_db_connection() as conn:
        db.ensure_story_local_schema(conn)
        conn.execute('UPDATE story_runs SET local_mode = 1 WHERE id = ?', (run['id'],))
        conn.commit()
    return {
        'success': True,
        'created': bool(created),
        'run': {'id': run['id'], 'seed': run['seed'], 'content_version': run['content_version']},
        'state': run.get('state') or state,
    }, 200


def submit_checkpoint(user_id, run_id, payload):
    """校验并保存一个检查点。"""
    if not user_in_rollout(user_id):
        return {'error': 'local_mode_disabled'}, 403
    if _rate_limited(user_id):
        return {'error': 'STORY_CHECKPOINT_RATE_LIMIT'}, 429
    payload = payload if isinstance(payload, dict) else {}
    try:
        seq = int(payload.get('seq') or 0)
        floor = int(payload.get('floor') or 0)
    except (TypeError, ValueError):
        return {'error': 'bad_seq'}, 400
    if seq < 1:
        return {'error': 'bad_seq'}, 400
    kind = str(payload.get('kind') or 'floor')[:24]
    actions = payload.get('actions')
    client_digest = str(payload.get('client_digest') or '')
    prev_digest = str(payload.get('prev_digest') or '')
    conn = db.get_db_connection()
    try:
        db.ensure_story_local_schema(conn)
        row = _load_run(conn, user_id, run_id)
        if row is None:
            return {'error': 'run_not_found'}, 404
        if row['status'] != 'active':
            return {'error': 'run_not_active', 'status': row['status']}, 409
        last = db.latest_story_checkpoint(run_id, verified_only=True)
        if last and last['seq'] == seq:
            return {'success': True, 'duplicate': True, 'seq': seq}, 200
        expected_seq = (last['seq'] if last else 0) + 1
        if seq != expected_seq:
            return {'error': 'STORY_CHECKPOINT_OUT_OF_ORDER', 'expected_seq': expected_seq}, 409
        expected_prev = last['server_digest'] if last else ''
        if prev_digest and expected_prev and prev_digest != expected_prev:
            return {'error': 'STORY_CHECKPOINT_CHAIN_MISMATCH'}, 409
        base_state = last['state'] if last else json.loads(row['state_json'] or '{}')
        started = time.time()
        result = story_verify.replay_checkpoint(
            base_state, actions, row['seed'], expected_digest=client_digest
        )
        elapsed_ms = int((time.time() - started) * 1000)
        verify_status = 'verified' if result['ok'] else VERIFY_STATUS_BY_REASON.get(
            result['reason'], 'error'
        )
        chain = story_verify.chain_digest(
            expected_prev, actions if isinstance(actions, list) else [], result['digest']
        )
        if not result['ok']:
            # 校验失败的检查点不占用序号：客户端修正后可以用同一 seq 重试。
            db.record_story_checkpoint_failure(
                conn,
                run_id=row['id'],
                user_id=int(user_id),
                seq=seq,
                floor=floor,
                kind=kind,
                reason=result['reason'] or 'mismatch',
                client_digest=client_digest,
                server_digest=result['digest'],
                actions=actions if isinstance(actions, list) else [],
            )
            conn.execute(
                'UPDATE story_runs SET suspicion_score = suspicion_score + 1, updated_at = ? WHERE id = ?',
                (db.utc_iso(db.utc_now_dt()), row['id']),
            )
            conn.commit()
            conn.close()
            return {
                'error': 'STORY_CHECKPOINT_MISMATCH',
                'reason': result['reason'],
                'seq': seq,
                'client_digest': client_digest,
                'server_digest': result['digest'],
            }, 409
        saved, store_status = db.commit_story_checkpoint(
            conn,
            run_id=row['id'],
            user_id=int(user_id),
            seq=seq,
            kind=kind,
            floor=floor,
            actions=actions if isinstance(actions, list) else [],
            client_digest=client_digest,
            prev_digest=expected_prev,
            chain_digest=chain,
            verify_status=verify_status,
            verify_reason=str(result.get('error') or ''),
            server_digest=result['digest'],
            verify_ms=elapsed_ms,
            state=result['state'],
            verified_floor=floor,
        )
        if store_status == 'run_missing':
            conn.rollback()
            return {'error': 'run_not_found'}, 404
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return {
        'success': True,
        'seq': seq,
        'server_digest': result['digest'],
        'verify_ms': elapsed_ms,
        'checkpoint': saved,
    }, 200


def resume_run(user_id, run_id):
    """回滚到最近一个已校验检查点。"""
    with db.get_db_connection() as conn:
        db.ensure_story_local_schema(conn)
        row = _load_run(conn, user_id, run_id)
        if row is None:
            return {'error': 'run_not_found'}, 404
        last = db.latest_story_checkpoint(run_id, verified_only=True)
        if last is None:
            return {
                'success': True,
                'run': {'id': row['id'], 'seed': row['seed'], 'content_version': row['content_version']},
                'checkpoint': None,
                'state': json.loads(row['state_json'] or '{}'),
            }, 200
        return {
            'success': True,
            'run': {'id': row['id'], 'seed': row['seed'], 'content_version': row['content_version']},
            'checkpoint': {
                'seq': last['seq'],
                'floor': last['floor'],
                'server_digest': last['server_digest'],
            },
            'state': last['state'],
        }, 200


def finish_run(user_id, run_id):
    """按最近一个已校验检查点结算并结束本轮。"""
    with db.get_db_connection() as conn:
        db.ensure_story_local_schema(conn)
        row = _load_run(conn, user_id, run_id)
        if row is None:
            return {'error': 'run_not_found'}, 404
        last = db.latest_story_checkpoint(run_id, verified_only=True)
        state = last['state'] if last else json.loads(row['state_json'] or '{}')
        now = db.utc_iso(db.utc_now_dt())
        conn.execute(
            "UPDATE story_runs SET status = 'completed', state_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(state, ensure_ascii=False, separators=(',', ':')), now, row['id']),
        )
        conn.commit()
    return {
        'success': True,
        'run_id': row['id'],
        'status': 'completed',
        'last_verified_seq': last['seq'] if last else 0,
        'last_verified_floor': last['floor'] if last else 0,
        'state': state,
    }, 200
