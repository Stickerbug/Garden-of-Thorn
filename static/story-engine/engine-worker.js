/* Pyodide story engine worker.
 *
 * Runs the exact same Python modules the server uses so a browser checkpoint
 * and a server replay produce the same digest. Classic worker on purpose:
 * ``python -m http.server`` serves .mjs as octet-stream, so module imports of
 * pyodide.mjs are rejected by the browser; pyodide.js exposes loadPyodide()
 * through importScripts() instead.
 */

const PYODIDE_URL = '/static/pyodide/';
const SOURCE_FILES = [
  'story_verify.py',
  'story_content_model.py',
  'story_character_content.py',
  'story_events_12.py',
  'story_content.py',
  'story_engine.py',
  'story_mode.py',
];

const REPLAY_SCRIPT = `
import json, time
from story_engine import apply_story_action
from story_mode import build_initial_story_state
import story_verify

def replay_for_worker(raw):
    payload = json.loads(raw)
    started = time.perf_counter()
    state = build_initial_story_state(payload['seed'], character_id=payload['character_id'])
    state['event_bank'] = int(payload.get('event_bank') or 0)
    for action in payload['actions']:
        state, _events = apply_story_action(state, action['type'], action.get('payload') or {}, payload['seed'])
    return json.dumps({
        'digest': story_verify.state_digest(json.loads(json.dumps(state, ensure_ascii=False))),
        'ms': round((time.perf_counter() - started) * 1000, 1),
        'floor': state.get('current_floor'),
        'phase': state.get('phase'),
        'rng_counter': state.get('rng_counter'),
    }, ensure_ascii=False)
`;

const APPLY_SCRIPT = `
import json
import story_verify
from story_engine import apply_story_action

def step_in_worker(raw):
    payload = json.loads(raw)
    state = payload['state']
    new_state, events = apply_story_action(
        state,
        payload['action_type'],
        payload.get('payload') or {},
        payload['seed'],
    )
    projected = json.loads(json.dumps(new_state, ensure_ascii=False))
    return json.dumps({
        'state': projected,
        'events': list(events or []),
        'digest': story_verify.state_digest(projected),
        'phase': new_state.get('phase'),
        'floor': new_state.get('current_floor'),
    }, ensure_ascii=False)
`;

let pyodideReady = null;

async function boot() {
  const started = performance.now();
  importScripts(PYODIDE_URL + 'pyodide.js');
  const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });
  const bootMs = Math.round(performance.now() - started);
  for (const name of SOURCE_FILES) {
    const response = await fetch('/static/story-engine/src/' + name);
    if (!response.ok) throw new Error('fetch failed: ' + name + ' ' + response.status);
    pyodide.FS.writeFile('/home/pyodide/' + name, await response.text());
  }
  pyodide.runPython("import sys\nif '/home/pyodide' not in sys.path:\n    sys.path.insert(0, '/home/pyodide')");
  pyodide.runPython(REPLAY_SCRIPT);
  pyodide.runPython(APPLY_SCRIPT);
  return { pyodide, bootMs };
}

async function step(request) {
  const ready = pyodideReady || (pyodideReady = boot());
  const { pyodide, bootMs } = await ready;
  pyodide.globals.set('payload_json', JSON.stringify(request));
  const started = performance.now();
  const raw = pyodide.runPython('step_in_worker(payload_json)');
  const parsed = JSON.parse(raw);
  parsed.bootMs = bootMs;
  parsed.ms = Math.round(performance.now() - started);
  return parsed;
}

async function replay(request) {
  const ready = pyodideReady || (pyodideReady = boot());
  const { pyodide, bootMs } = await ready;
  pyodide.globals.set('payload_json', JSON.stringify(request));
  const started = performance.now();
  const raw = pyodide.runPython('replay_for_worker(payload_json)');
  const totalMs = Math.round(performance.now() - started);
  const parsed = JSON.parse(raw);
  parsed.bootMs = bootMs;
  parsed.totalMs = totalMs;
  return parsed;
}

self.onmessage = async (event) => {
  const message = event.data || {};
  try {
    if (message.type === 'boot') {
      const ready = pyodideReady || (pyodideReady = boot());
      const { bootMs } = await ready;
      self.postMessage({ type: 'ready', bootMs });
      return;
    }
    if (message.type === 'step') {
      const result = await step(message.payload);
      self.postMessage({ type: 'result', id: message.id, result });
      return;
    }
    if (message.type === 'run') {
      const result = await replay(message.payload);
      self.postMessage({ type: 'result', id: message.id, result });
      return;
    }
    self.postMessage({ type: 'error', message: 'unknown message type' });
  } catch (error) {
    self.postMessage({ type: 'error', id: message.id, message: String((error && error.stack) || error) });
  }
};
