/* 使用 Edge CDP 验证预览交互；不依赖 npm 包，由 validate_preview.py 调用。 */
const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const ROOT = __dirname;
const BASE = process.argv[2] || 'http://127.0.0.1:7132';
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const SHOTS = path.join(ROOT, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

const profile = fs.mkdtempSync(path.join(ROOT, '.edge-check-'));
const browser = spawn(EDGE, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
  '--no-default-browser-check', '--remote-debugging-pipe', `--user-data-dir=${profile}`,
  '--window-size=1440,1000', 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'], windowsHide: true });

let nextId = 0;
let inbound = '';
let sessionId = '';
const pending = new Map();
const eventWaiters = new Set();
const errors = [];
const responses = [];
let encodedBytes = 0;
let finishedRequests = 0;

let expectedGeneric404s = 0;
function expectedNoise(message) {
  const text = String(message || '');
  // 游客账号接口的预期 401、主动断网的网络错误，以及与本地训练无关的既有皮肤资源。
  if (text.includes('status of 404') && expectedGeneric404s > 0) {
    expectedGeneric404s -= 1;
    return true;
  }
  return text.includes('status of 401') || text.includes('net::ERR_INTERNET_DISCONNECTED') || text.includes('net::ERR_NETWORK_CHANGED') || text.includes('%E5%88%9D%E5%A7%8B.svg');
}
function recordError(message) {
  if (!expectedNoise(message)) errors.push(String(message));
}
function expectedResponse(response) {
  const knownAsset404 = response.status === 404 && response.url.includes('%E5%88%9D%E5%A7%8B.svg');
  if (knownAsset404) expectedGeneric404s += 1;
  return response.status === 401 || knownAsset404;
}

browser.stderr.on('data', () => {});
browser.stdio[4].on('data', chunk => {
  inbound += chunk.toString('utf8');
  let boundary;
  while ((boundary = inbound.indexOf('\0')) >= 0) {
    const raw = inbound.slice(0, boundary);
    inbound = inbound.slice(boundary + 1);
    if (!raw) continue;
    const message = JSON.parse(raw);
    if (message.id) {
      const request = pending.get(message.id);
      if (!request) continue;
      pending.delete(message.id);
      clearTimeout(request.timer);
      if (message.error) request.reject(new Error(`${request.method}: ${message.error.message}`));
      else request.resolve(message.result || {});
      continue;
    }
    for (const waiter of [...eventWaiters]) {
      if (waiter.method === message.method && (!waiter.sessionId || waiter.sessionId === message.sessionId)) {
        eventWaiters.delete(waiter);
        clearTimeout(waiter.timer);
        waiter.resolve(message.params || {});
      }
    }
    if (message.sessionId && message.sessionId !== sessionId) continue;
    if (message.method === 'Runtime.exceptionThrown') {
      recordError(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text || '页面脚本异常');
    } else if (message.method === 'Runtime.consoleAPICalled' && message.params?.type === 'error') {
      recordError((message.params.args || []).map(arg => arg.value || arg.description || '').join(' '));
    } else if (message.method === 'Log.entryAdded' && message.params?.entry?.level === 'error') {
      recordError(message.params.entry.text);
    } else if (message.method === 'Network.responseReceived') {
      const response = message.params?.response;
      if (response) {
        responses.push({ url: response.url, status: response.status });
        if (response.status >= 400 && !expectedResponse(response)) recordError(`HTTP ${response.status}: ${response.url}`);
      }
    } else if (message.method === 'Network.loadingFailed' && !message.params?.canceled) {
      recordError(`资源加载失败: ${message.params?.errorText || 'unknown'}`);
    } else if (message.method === 'Network.loadingFinished') {
      encodedBytes += Number(message.params?.encodedDataLength || 0);
      finishedRequests += 1;
    }
  }
});
browser.once('exit', code => {
  for (const request of pending.values()) {
    clearTimeout(request.timer);
    request.reject(new Error(`浏览器提前退出 (${code})`));
  }
  pending.clear();
});

function send(method, params = {}, withSession = true) {
  const id = ++nextId;
  const message = { id, method, params };
  if (withSession && sessionId) message.sessionId = sessionId;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`${method} 验证超时`));
    }, 180000);
    pending.set(id, { resolve, reject, timer, method });
    browser.stdio[3].write(`${JSON.stringify(message)}\0`);
  });
}
function waitEvent(method, timeout = 180000) {
  return new Promise((resolve, reject) => {
    const waiter = { method, sessionId, resolve };
    waiter.timer = setTimeout(() => {
      eventWaiters.delete(waiter);
      reject(new Error(`${method} 等待超时`));
    }, timeout);
    eventWaiters.add(waiter);
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result?.value;
}
function assert(value, message) {
  if (!value) throw new Error(message);
  console.log(`PASS ${message}`);
}
async function navigate(url) {
  const loaded = waitEvent('Page.loadEventFired');
  await send('Page.navigate', { url });
  await loaded;
  await evaluate(`Promise.all([...document.images].map(img => img.complete ? Promise.resolve() : new Promise(resolve => { img.addEventListener('load', resolve, { once: true }); img.addEventListener('error', resolve, { once: true }); }))).then(() => true)`);
}
async function screenshot(name, width, minimumHeight) {
  const height = Math.max(minimumHeight, await evaluate('document.documentElement.scrollHeight'));
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
  const result = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  const output = path.join(SHOTS, `${name}.png`);
  fs.writeFileSync(output, Buffer.from(result.data, 'base64'));
  console.log(`SCREENSHOT ${name}: ${output} (${fs.statSync(output).size} bytes)`);
}

async function waitFor(expression, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await evaluate(expression);
    if (value) return value;
    await new Promise(resolve => setTimeout(resolve, 120));
  }
  throw new Error(`等待条件超时：${expression}`);
}

async function run() {
  const created = await send('Target.createTarget', { url: 'about:blank' }, false);
  const attached = await send('Target.attachToTarget', { targetId: created.targetId, flatten: true }, false);
  sessionId = attached.sessionId;
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Log.enable');
  await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });

  await navigate(`${BASE}/`);
  await waitFor(`typeof emitSoloStart === 'function' && !!window.GTNSoloLocal`);
  await evaluate(`connectSocket(getServerAddress(), { handlersOnly: true })`);
  await waitFor(`GTNSoloLocal.getDiagnostics().registeredEvents.includes('solo_state')`);
  await evaluate(`(() => {
    window.__serverTrainingEvents = [];
    window.__soloWorkerMessages = [];
    if (window.socket) {
      const originalEmit = socket.emit.bind(socket);
      socket.emit = (eventName, ...args) => {
        if (String(eventName).startsWith('solo_') || eventName === 'predict_hand' || eventName === 'request_game_state') {
          window.__serverTrainingEvents.push(eventName);
        }
        return originalEmit(eventName, ...args);
      };
    }
    return true;
  })()`);

  const started = await evaluate(`Promise.race([
    window.GTNSoloLocal.dispatch('solo_start', { deck0: Array(15).fill('Basic'), deck1: Array(15).fill('Basic') }),
    new Promise(resolve => setTimeout(() => resolve({ debugTimeout: true }), 150000)),
  ])`);
  if (started?.debugTimeout) {
    const debug = await evaluate(`({ diagnostics: GTNSoloLocal.getDiagnostics(), workerMessages: window.__soloWorkerMessages, resources: performance.getEntriesByType('resource').filter(item => item.name.includes('/static/vendor/pyodide/') || item.name.includes('/api/solo-local-runtime')).map(item => ({ name: item.name, duration: item.duration })) })`);
    console.log(`SOLO_DEBUG ${JSON.stringify(debug)}`);
    console.log(`SOLO_NET_DEBUG ${JSON.stringify(responses.filter(item => item.url.includes('/static/vendor/pyodide/') || item.url.includes('/api/solo-local-runtime')))}`);
    throw new Error('本地训练场初始化超时');
  }
  assert(started?.events?.some(([name]) => name === 'game_phase'), '本地训练场返回开局消息');
  assert(started?.events?.some(([name, data]) => name === 'solo_state' && data.local_engine), '本地训练场返回本地引擎状态');
  const initial = await evaluate(`({ phase: gameState?.phase, hand: gameState?.you?.hand?.length, local: gameState?.local_engine, skins: gameState?.player_skins?.length, gameKeys: Object.keys(gameState || {}), diagnostics: GTNSoloLocal.getDiagnostics() })`);
  console.log(`SOLO_START_STATE ${JSON.stringify(initial)}`);
  assert(initial.phase === 'action' && initial.hand > 0 && initial.local && initial.skins === 2, `开局状态与皮肤注入正常：${JSON.stringify(initial)}`);
  assert(initial.diagnostics.active && initial.diagnostics.initialized, 'Worker 初始化完成且处于活动状态');
  await evaluate(`if (typeof hideModal === 'function') hideModal()`);
  await screenshot('local-start', 1440, 1000);

  const played = await evaluate(`(() => {
    const card = gameState.you.hand.find(item => item.def_id === 'Basic') || gameState.you.hand[0];
    return window.GTNSoloLocal.dispatch('solo_play_card', { card_instance_id: card.instance_id });
  })()`);
  assert(!played?.events?.some(([name]) => name === 'server_error'), '出牌在本地完成且没有规则错误');
  const predicted = await evaluate(`(() => {
    const card = gameState.you.hand[0];
    return window.GTNSoloLocal.dispatch('predict_hand', { cards: [{ player_id: 0, instance_id: card.instance_id, target_player_id: 1 }] });
  })()`);
  assert(predicted?.events?.some(([name]) => name === 'play_predictions'), '伤害预测在本地返回');
  const ended = await evaluate(`window.GTNSoloLocal.dispatch('solo_end_turn', {})`);
  assert(!ended?.events?.some(([name]) => name === 'server_error'), '回合结束在本地完成');
  assert(!(await evaluate(`window.GTNSoloLocal.dispatch('solo_undo', {})`))?.events?.some(([name]) => name === 'server_error'), '撤销在本地完成');
  assert(!(await evaluate(`window.GTNSoloLocal.dispatch('solo_redo', {})`))?.events?.some(([name]) => name === 'server_error'), '重做在本地完成');
  assert(!(await evaluate(`window.GTNSoloLocal.dispatch('solo_set_next_draw', { def_ids: ['Basic'] })`))?.events?.some(([name]) => name === 'server_error'), '设置下次抽牌在本地完成');

  await evaluate(`(() => {
    if (typeof stopSocialNetworkActivity === 'function') stopSocialNetworkActivity();
    if (window.socket) socket.disconnect();
    return true;
  })()`);
  await send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });

  const offlinePlayed = await evaluate(`(() => {
    const card = gameState.you.hand.find(item => item.def_id === 'Basic') || gameState.you.hand[0];
    return window.GTNSoloLocal.dispatch('solo_play_card', { card_instance_id: card.instance_id });
  })()`);
  assert(!offlinePlayed?.events?.some(([name]) => name === 'server_error'), '断网后出牌仍在本地完成');
  assert(!(await evaluate(`window.GTNSoloLocal.dispatch('solo_end_turn', {})`))?.events?.some(([name]) => name === 'server_error'), '断网后回合结算仍在本地完成');
  assert(!(await evaluate(`window.GTNSoloLocal.dispatch('solo_undo', {})`))?.events?.some(([name]) => name === 'server_error'), '断网后撤销仍可用');
  assert(!(await evaluate(`window.GTNSoloLocal.dispatch('solo_redo', {})`))?.events?.some(([name]) => name === 'server_error'), '断网后重做仍可用');
  assert(!(await evaluate(`window.GTNSoloLocal.dispatch('request_game_state', {})`))?.events?.some(([name]) => name === 'server_error'), '断网后本地全量状态同步仍可用');
  const offlinePredicted = await evaluate(`(() => {
    const card = gameState.you.hand[0];
    return window.GTNSoloLocal.dispatch('predict_hand', { cards: [{ player_id: 0, instance_id: card.instance_id, target_player_id: 1 }] });
  })()`);
  assert(offlinePredicted?.events?.some(([name]) => name === 'play_predictions'), '断网后伤害预测仍可用');
  await screenshot('local-offline', 1440, 1000);

  const paused = await evaluate(`window.GTNSoloLocal.dispatch('solo_pause', {})`);
  assert(paused?.events?.some(([name]) => name === 'solo_paused'), '断网后可暂停并退出本地训练');
  const serverEvents = await evaluate(`window.__serverTrainingEvents`);
  assert(serverEvents.length === 0, `没有任何训练场操作发往服务器：${JSON.stringify(serverEvents)}`);
  const performance = await evaluate(`({ resources: performance.getEntriesByType('resource').length, loadMs: Math.round(performance.getEntriesByType('navigation')[0]?.duration || 0) })`);
  console.log(`METRICS ${JSON.stringify({ ...performance, finishedRequests, encodedBytes, httpResponses: responses.length })}`);
  assert(errors.length === 0, `浏览器控制台无错误且没有资源 404${errors.length ? '：' + errors.join(' | ') : ''}`);
}

function browserProcessAlive() {
  try { process.kill(browser.pid, 0); return true; }
  catch (_) { return false; }
}
async function waitForBrowserExit(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (browser.exitCode === null && browser.signalCode === null && Date.now() < deadline) {
    if (!browserProcessAlive()) return true;
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  return browser.exitCode !== null || browser.signalCode !== null || !browserProcessAlive();
}

run().catch(error => {
  recordError(error.stack || error.message || error);
  console.error(errors.join('\n'));
  process.exitCode = 1;
}).finally(async () => {
  try {
    if (browser.exitCode === null && browser.signalCode === null) {
      await Promise.race([
        send('Browser.close', {}, false),
        new Promise(resolve => setTimeout(resolve, 2500)),
      ]);
    }
  } catch (_) {}
  if (!await waitForBrowserExit(2500)) {
    spawnSync('taskkill', ['/PID', String(browser.pid), '/T', '/F'], { stdio: 'ignore' });
  }
  const stopped = await waitForBrowserExit(5000);
  try { fs.rmSync(profile, { recursive: true, force: true, maxRetries: 4, retryDelay: 150 }); } catch (_) {}
  console.log(`Edge stopped: ${stopped}`);
  if (!stopped) process.exitCode = 1;
});
