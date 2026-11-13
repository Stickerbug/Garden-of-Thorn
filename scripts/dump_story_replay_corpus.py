# -*- coding: utf-8 -*-
"""T0: dump story-run replay corpus and check that the engine reproduces stored states.

Usage:
    python scripts/dump_story_replay_corpus.py --limit 5 --db <sqlite> [--out dir]

For every run it rebuilds the initial state from the run seed and character,
replays the recorded actions with ``apply_story_action`` and compares the
canonical digest with the stored ``state_json``.
"""

import argparse
import gzip
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default=os.environ.get('GTN_DB_PATH') or r'D:\gtn\deploy-20261109-all\preview.sqlite3')
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--out', default=r'D:\gtn\tmp_cardstar\story_corpus')
    args = parser.parse_args()

    # db.DB_PATH is read at import time, so the env override has to land first.
    os.environ['GTN_DB_PATH'] = os.path.abspath(args.db)

    import db  # noqa: E402
    import story_mode  # noqa: E402
    import story_verify  # noqa: E402
    from story_engine import apply_story_action  # noqa: E402

    os.makedirs(args.out, exist_ok=True)
    conn = db.get_db_connection()
    runs = conn.execute(
        "SELECT id, seed, content_version, state_json FROM story_runs "
        "WHERE status IN ('active', 'completed', 'ended') "
        "ORDER BY updated_at DESC LIMIT ?",
        (args.limit,),
    ).fetchall()

    ok = 0
    for row in runs:
        actions = conn.execute(
            'SELECT action_id, action_type, payload_json FROM story_run_actions '
            'WHERE run_id = ? ORDER BY sequence ASC',
            (row['id'],),
        ).fetchall()
        try:
            stored = json.loads(row['state_json'] or '{}')
        except ValueError:
            print('SKIP', row['id'], 'invalid state_json')
            continue
        character_id = str(
            (stored.get('player') or {}).get('character_id')
            or stored.get('character_id')
            or 'common_flower'
        )
        started = time.perf_counter()
        try:
            state = story_mode.build_initial_story_state(row['seed'], character_id=character_id)
            state['event_bank'] = int(stored.get('event_bank') or 0)
            for action in actions:
                state, _events = apply_story_action(
                    state, action['action_type'], json.loads(action['payload_json'] or '{}'), row['seed'],
                )
        except Exception as exc:  # noqa: BLE001 - corpus probe wants the message
            print('REPLAY_FAIL', row['id'], type(exc).__name__, str(exc)[:120])
            continue
        elapsed = (time.perf_counter() - started) * 1000
        stored_digest = story_verify.state_digest(stored)
        replayed_digest = story_verify.state_digest(state)
        same = stored_digest == replayed_digest
        ok += 1 if same else 0
        print(
            'RUN', row['id'], 'actions', len(actions), 'ms', round(elapsed, 1),
            'match', same, 'stored', stored_digest[:19], 'replayed', replayed_digest[:19],
        )
        with gzip.open(os.path.join(args.out, f"{row['id']}.json.gz"), 'wt', encoding='utf-8') as fh:
            json.dump({
                'run_id': row['id'],
                'seed': row['seed'],
                'content_version': row['content_version'],
                'character_id': character_id,
                'actions': [
                    {'id': a['action_id'], 'type': a['action_type'], 'payload': json.loads(a['payload_json'] or '{}')}
                    for a in actions
                ],
                'stored_digest': stored_digest,
                'replayed_digest': replayed_digest,
                'match': same,
            }, fh, ensure_ascii=False)
    print('SUMMARY', ok, '/', len(runs), 'match')
    conn.close()


if __name__ == '__main__':
    main()
