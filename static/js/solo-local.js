/* 普通单人训练场的浏览器本地运行桥；教程、Phelren 与多人对战不使用此模块。 */
(() => {
  const handlers = new Map();
  const pending = new Map();
  const v2Timers = new Map();
  let worker = null;
  let nextRequestId = 1;
  let generation = 0;
  let active = false;
  let initialized = false;
  let initializedKey = '';
  let initializePromise = null;
  let achievementSent = false;
  let workerStage = 'created';
  // 首次启动要下载并解压 Pyodide 运行时，实测约 8-12 秒；这段时间必须有持续的提示，
  // 否则玩家会以为「开始训练」没反应而反复点击（每次点击都会重启 generation）。
  const LOADING_HINT = '正在加载本地训练场引擎…（首次约 10 秒）';

  function register(eventName, handler) {
    if (eventName && typeof handler === 'function') handlers.set(eventName, handler);
  }

  function receive(eventName, payload) {
    const handler = handlers.get(eventName);
    if (handler) handler(payload);
  }

  function workerFailed(error) {
    const message = String(error?.message || error || '本地引擎运行失败');
    for (const request of pending.values()) request.reject(new Error(message));
    pending.clear();
    initialized = false;
    initializePromise = null;
    initializedKey = '';
    active = false;
  }

  function ensureWorker() {
    if (worker) return worker;
    worker = new Worker('/static/js/solo-local-worker.js', { type: 'module' });
    worker.addEventListener('message', (event) => {
      const data = event.data || {};
      if (data.type === 'status') {
        workerStage = data.stage || workerStage;
        if (typeof flashStatus === 'function') flashStatus(LOADING_HINT, 1800);
        receive('solo_boot_status', { stage: workerStage, booting: true, loading: false });
        return;
      }
      if (data.type === 'ready') {
        workerStage = 'ready';
        receive('solo_boot_status', { stage: 'ready', booting: true, loading: false });
        return;
      }
      const request = pending.get(data.id);
      if (!request) return;
      pending.delete(data.id);
      if (data.type === 'error') {
        request.reject(new Error(data.message || '本地引擎运行失败'));
        return;
      }
      if (data.type === 'action_result') {
        for (const [eventName, payload] of data.result?.events || []) receiveActionEvent(eventName, payload, request.generation);
      }
      request.resolve(data.result);
    });
    worker.addEventListener('error', workerFailed);
    worker.addEventListener('messageerror', workerFailed);
    return worker;
  }

  function request(type, body = {}) {
    ensureWorker();
    const id = nextRequestId++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject, generation });
      worker.postMessage({ id, type, ...body });
    });
  }

  async function communityData(payload) {
    if (payload?.mod_source !== 'community') return [];
    const response = await fetch('/api/solo-local-community', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) throw new Error(data.error || '社区模组读取失败');
    return data.mods || [];
  }

  async function initialize(payload) {
    const communityKey = payload?.mod_source === 'community'
      ? String(payload.community_mod_hash || JSON.stringify(payload.community_mods || []))
      : 'official';
    if (initializePromise && initializedKey === communityKey) return initializePromise;
    initializedKey = communityKey;
    initializePromise = (async () => {
      const community_mod_data = await communityData(payload);
      const result = await request('initialize', { config: { ...payload, community_mod_data } });
      if (!result?.success) throw new Error(result?.error || '本地引擎初始化失败');
      initialized = true;
      return result;
    })().catch((error) => {
      initialized = false;
      initializePromise = null;
      throw error;
    });
    return initializePromise;
  }

  function enrichState(state) {
    try {
      const ownSkin = typeof normalizeSkinConfig === 'function'
        ? normalizeSkinConfig(getCurrentSkinConfig())
        : { primary_color: '#FFE763', eye_shape: 'oval', mouth_shape: 'original', skin_id: 'classic' };
      const defaultSkin = typeof normalizeSkinConfig === 'function'
        ? normalizeSkinConfig({})
        : ownSkin;
      const look = typeof DEFAULT_SKIN_LOOK !== 'undefined' ? DEFAULT_SKIN_LOOK : { x: 0.707, y: -0.707 };
      const cardSkin = typeof myEquippedCardSkin === 'function' ? myEquippedCardSkin() : '';
      state.player_skins = [ownSkin, defaultSkin];
      state.player_skin_looks = [{ ...look }, { ...look }];
      state.player_card_skins = [cardSkin, cardSkin];
    } catch (_) {
      /* 皮肤只是展示层，不影响本地引擎状态。 */
    }
    return state;
  }

  function recordAchievement(state) {
    const total = Number(state?.local_status_type_count || 0);
    if (achievementSent || total < 30) return;
    achievementSent = true;
    void fetch('/api/solo-local-achievement', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ flag: 'flag_solo_status_25', status_type_count: total }),
    }).catch(() => { achievementSent = false; });
  }

  function receiveActionEvent(eventName, payload, eventGeneration) {
    if (eventGeneration !== generation) return;
    if (eventName === 'solo_state') {
      enrichState(payload);
      recordAchievement(payload);
    } else if (eventName === 'v2_ui_request') {
      const requestId = String(payload?.request_id || '');
      if (v2Timers.has(requestId)) clearTimeout(v2Timers.get(requestId));
      const timeout = Number(payload?.timeout_ms || 0);
      if (requestId && timeout > 0) {
        v2Timers.set(requestId, setTimeout(() => {
          v2Timers.delete(requestId);
          void dispatch('solo_v2_ui_timeout', { request_id: requestId });
        }, timeout));
      }
    } else if (eventName === 'solo_paused') {
      active = false;
    }
    receive(eventName, payload);
  }

  async function dispatch(eventName, payload = {}) {
    if (eventName === 'solo_start') {
      generation += 1;
      active = true;
      achievementSent = false;
      for (const timer of v2Timers.values()) clearTimeout(timer);
      v2Timers.clear();
      const startGeneration = generation;
      receive('solo_boot_status', { stage: 'starting', loading: true });
      try {
        await initialize(payload);
        if (startGeneration !== generation) return null;
        return await request('action', { eventName, payload });
      } catch (error) {
        if (startGeneration === generation) active = false;
        receive('server_error', { message: `本地训练场启动失败：${error?.message || error}` });
        return null;
      } finally {
        if (startGeneration === generation) {
          receive('solo_boot_status', { stage: 'done', loading: false, done: true });
        }
      }
    }
    if (eventName === 'solo_pause') {
      generation += 1;
      active = false;
      for (const timer of v2Timers.values()) clearTimeout(timer);
      v2Timers.clear();
    }
    try {
      await initializePromise;
      return await request('action', { eventName, payload });
    } catch (error) {
      receive('server_error', { message: `本地训练场操作失败：${error?.message || error}` });
      return null;
    }
  }

  function isActive() { return active; }
  // 进入训练场就预热运行时，避免点「开始训练」后才开始下载 Pyodide。
  function preload() {
    if (initialized) return Promise.resolve(null);
    ensureWorker();
    return request('boot').catch(() => null);
  }
  function getDiagnostics() {
    return {
      active, initialized, generation, pendingRequests: pending.size,
      workerCreated: !!worker, initializedKey, workerStage,
      registeredEvents: [...handlers.keys()],
    };
  }

  window.GTNSoloLocal = Object.freeze({ register, dispatch, isActive, preload, getDiagnostics });
})();
