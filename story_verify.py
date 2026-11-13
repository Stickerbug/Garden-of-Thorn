"""Deterministic digest helpers for local (browser-side) story runs.

The same rules must run in the browser (Pyodide, CPython 3.x) and on the
server, so this module only depends on the standard library and uses the
canonical JSON form already used elsewhere in the codebase:
``ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')``.
"""

import hashlib
import json

DIGEST_PREFIX = 'sha256:'

# Host-owned keys never participate in a checkpoint digest: the server injects
# ``dev_mode`` when a run is created, re-injects the account-level ``event_bank``
# before every action, sets ``sl_used`` when a manual save is loaded, and keeps
# ``*_checkpoint`` snapshots (which embed copies of older states). Replaying the
# action log reproduces none of them, so digesting the whole dict makes every
# comparison fail for reasons that are not gameplay.
HOST_STATE_KEYS = (
    'dev_mode',
    'event_bank',
    'sl_used',
    'last_events',
    'floor_entry_checkpoint',
    'recovery_checkpoint',
)


def canonical_json(value):
    """Canonical, byte-stable JSON for a story state or action payload."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(',', ':'),
    )


def gameplay_state(state):
    """Projection of a story state that only the deterministic engine owns."""
    if not isinstance(state, dict):
        return {}
    return {key: value for key, value in state.items() if key not in HOST_STATE_KEYS}


def state_digest(state, include_host=False):
    """Digest of a story state (a checkpoint fingerprint).

    Host-injected fields are dropped by default so a browser checkpoint and a
    server replay compare equal; pass ``include_host=True`` for diagnostics.
    """
    payload = state if include_host else gameplay_state(state)
    return DIGEST_PREFIX + hashlib.sha256(canonical_json(payload).encode('utf-8')).hexdigest()


def action_digest(action):
    """Fingerprint one action; the client-side action id is not part of it."""
    payload = {
        'type': str((action or {}).get('type') or ''),
        'payload': (action or {}).get('payload') or {},
    }
    return hashlib.sha256(canonical_json(payload).encode('utf-8')).hexdigest()


def chain_digest(prev_digest, actions, final_state_digest):
    """Chain a checkpoint onto the previous one so truncation/reordering shows."""
    digest = hashlib.sha256()
    digest.update(str(prev_digest or '').encode('utf-8'))
    for action in actions or []:
        digest.update(b'\x1f')
        digest.update(action_digest(action).encode('utf-8'))
    digest.update(b'\x1e')
    digest.update(str(final_state_digest or '').encode('utf-8'))
    return DIGEST_PREFIX + digest.hexdigest()


def is_digest(value):
    """True when *value* looks like a digest produced by this module."""
    text = str(value or '')
    if not text.startswith(DIGEST_PREFIX):
        return False
    body = text[len(DIGEST_PREFIX):]
    return len(body) == 64 and all(ch in '0123456789abcdef' for ch in body)

# One checkpoint may not carry an unbounded action log: a floor is a few dozen
# actions and a whole battle is usually under 200. The cap keeps a malicious
# client from making the server replay forever.
MAX_CHECKPOINT_ACTIONS = 400


def normalize_actions(actions, max_actions=MAX_CHECKPOINT_ACTIONS):
    """Validate and trim a client action log; returns ``(actions, error)``."""
    if not isinstance(actions, list):
        return [], 'actions_not_list'
    if len(actions) > max_actions:
        return [], 'action_limit'
    cleaned = []
    for entry in actions:
        if not isinstance(entry, dict):
            return [], 'action_not_object'
        action_type = str(entry.get('type') or '').strip()
        if not action_type:
            return [], 'action_type_missing'
        payload = entry.get('payload')
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            return [], 'action_payload_invalid'
        cleaned.append({'type': action_type, 'payload': payload})
    return cleaned, None


def replay_checkpoint(state, actions, seed, expected_digest=None, max_actions=MAX_CHECKPOINT_ACTIONS):
    """Replay ``actions`` on ``state`` and compare the resulting digest.

    Returns a dict with ``ok``, ``state``, ``digest``, ``actions`` (count),
    ``reason`` (``None`` when everything checks out) and ``error`` (a short
    engine message for invalid actions). Never raises for client input.
    """
    # Imported lazily: the browser worker imports this module before the engine
    # sources exist, and the server must not pay the engine import cost twice.
    from story_engine import StoryActionError, apply_story_action

    cleaned, error = normalize_actions(actions, max_actions=max_actions)
    if error:
        return {
            'ok': False,
            'reason': error,
            'error': '',
            'state': state,
            'digest': state_digest(state) if isinstance(state, dict) else '',
            'actions': 0,
        }

    current = state
    for action in cleaned:
        try:
            current, _events = apply_story_action(current, action['type'], action['payload'], seed)
        except StoryActionError as exc:
            return {
                'ok': False,
                'reason': 'invalid_action',
                'error': str(exc)[:200],
                'state': current,
                'digest': state_digest(current) if isinstance(current, dict) else '',
                'actions': 0,
            }
        except Exception as exc:  # noqa: BLE001 - client input must never 500
            return {
                'ok': False,
                'reason': 'engine_error',
                'error': f'{type(exc).__name__}: {str(exc)[:160]}',
                'state': current,
                'digest': state_digest(current) if isinstance(current, dict) else '',
                'actions': 0,
            }

    digest = state_digest(json.loads(json.dumps(current, ensure_ascii=False)))
    if expected_digest is not None and digest != expected_digest:
        return {
            'ok': False,
            'reason': 'mismatch',
            'error': '',
            'state': current,
            'digest': digest,
            'actions': len(cleaned),
        }
    return {
        'ok': True,
        'reason': None,
        'error': '',
        'state': current,
        'digest': digest,
        'actions': len(cleaned),
    }
