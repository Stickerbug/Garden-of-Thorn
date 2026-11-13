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
