import { loadPyodide } from '/static/vendor/pyodide/pyodide.esm.js';

const RUNTIME_ROOT = '/home/pyodide/solo-local';
let pyodide = null;
let runner = null;
let readyPromise = null;

async function boot() {
  if (readyPromise) return readyPromise;
  readyPromise = (async () => {
    self.postMessage({ type: 'status', stage: 'python' });
    pyodide = await loadPyodide({ indexURL: '/static/vendor/pyodide/' });
    self.postMessage({ type: 'status', stage: 'bundle' });
    const response = await fetch('/api/solo-local-runtime', { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`本地引擎包下载失败（${response.status}）`);
    self.postMessage({ type: 'status', stage: 'bundle_response' });
    const buffer = await response.arrayBuffer();
    self.postMessage({ type: 'status', stage: 'bundle_buffer', bytes: buffer.byteLength });
    pyodide.FS.writeFile('/tmp/gtn-solo-local.zip', new Uint8Array(buffer));
    pyodide.runPython(`
import zipfile
zipfile.ZipFile('/tmp/gtn-solo-local.zip').extractall('${RUNTIME_ROOT}')
`);
    self.postMessage({ type: 'status', stage: 'bundle_unpack' });
    pyodide.runPython(`
import sys
sys.path.insert(0, '${RUNTIME_ROOT}')
import solo_local_runner as runner
`);
    runner = pyodide.globals.get('runner');
    self.postMessage({ type: 'status', stage: 'bundle_import' });
    self.postMessage({ type: 'ready' });
  })();
  return readyPromise;
}

async function handle(message) {
  const { id, type } = message;
  try {
    await boot();
    if (type === 'initialize') {
      const result = runner.initialize(JSON.stringify(message.config || {}));
      self.postMessage({ id, type: 'initialize_result', result: JSON.parse(result) });
      return;
    }
    if (type === 'action') {
      const result = runner.dispatch(message.eventName, JSON.stringify(message.payload || {}));
      self.postMessage({ id, type: 'action_result', result: JSON.parse(result) });
      return;
    }
    throw new Error(`未知本地引擎请求：${type}`);
  } catch (error) {
    self.postMessage({ id, type: 'error', message: String(error?.message || error), stack: String(error?.stack || '') });
  }
}

let queue = Promise.resolve();
self.onmessage = (event) => {
  queue = queue.then(() => handle(event.data)).catch((error) => {
    self.postMessage({ id: event.data?.id, type: 'error', message: String(error?.message || error) });
  });
};
