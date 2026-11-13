/* 本地模式爬塔：在 Web Worker 里跑同一份 Pyodide 引擎，服务端只校验检查点。
 *
 * 设计见 docs/aegis/plans/2026-11-13-story-local-engine.md：
 * - 层层切换与每场战斗结束各上传一次检查点；
 * - 每个检查点带自上次成功上传以来的动作日志与最终状态摘要；
 * - 服务端重放不一致时回滚到最近一次已校验存档。
 */
(function () {
    'use strict';

    const WORKER_URL = '/static/story-engine/engine-worker.js';
    const REQUEST_TIMEOUT_MS = 20000;

    const state = {
        active: false,
        run: null,
        seq: 0,
        lastDigest: '',
        stateDigest: '',
        log: [],
        worker: null,
        nextId: 1,
        pending: new Map(),
        listeners: new Set(),
        lastError: '',
    };

    function snapshot() {
        return {
            active: state.active,
            runId: state.run ? state.run.id : '',
            seq: state.seq,
            floor: state.run && state.run.state ? state.run.state.current_floor : 0,
            phase: state.run && state.run.state ? state.run.state.phase : '',
            digest: state.stateDigest,
            pendingActions: state.log.length,
            lastError: state.lastError,
        };
    }

    function notify() {
        const view = snapshot();
        state.listeners.forEach((fn) => {
            try {
                fn(view);
            } catch (error) {
                console.warn('[story-local] listener failed', error);
            }
        });
    }

    async function requestJson(url, options) {
        const response = await fetch(url, {
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        let payload = null;
        try {
            payload = await response.json();
        } catch (error) {
            payload = null;
        }
        if (!response.ok) {
            const failure = new Error((payload && (payload.error || payload.message)) || `HTTP ${response.status}`);
            failure.status = response.status;
            failure.payload = payload || {};
            throw failure;
        }
        return payload || {};
    }

    function ensureWorker() {
        if (state.worker) return state.worker;
        const worker = new Worker(WORKER_URL);
        worker.onmessage = (event) => {
            const message = event.data || {};
            if (message.type === 'result' && state.pending.has(message.id)) {
                state.pending.get(message.id).resolve(message.result);
                state.pending.delete(message.id);
                return;
            }
            if (message.type === 'error' && state.pending.has(message.id)) {
                state.pending.get(message.id).reject(new Error(message.message || 'engine error'));
                state.pending.delete(message.id);
                return;
            }
            if (message.type === 'ready' && state.pending.has('boot')) {
                state.pending.get('boot').resolve(message);
                state.pending.delete('boot');
            }
        };
        worker.onerror = (event) => {
            const error = new Error((event && event.message) || 'worker failed');
            state.pending.forEach((entry) => entry.reject(error));
            state.pending.clear();
        };
        state.worker = worker;
        return worker;
    }

    function send(type, payload, timeoutMs = REQUEST_TIMEOUT_MS) {
        const worker = ensureWorker();
        const id = state.nextId++;
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                state.pending.delete(id);
                reject(new Error('engine timeout'));
            }, timeoutMs);
            state.pending.set(id, {
                resolve: (value) => {
                    clearTimeout(timer);
                    resolve(value);
                },
                reject: (error) => {
                    clearTimeout(timer);
                    reject(error);
                },
            });
            worker.postMessage({ type, id, payload });
        });
    }

    function boot(timeoutMs = 30000) {
        return new Promise((resolve, reject) => {
            const worker = ensureWorker();
            const timer = setTimeout(() => {
                state.pending.delete('boot');
                reject(new Error('engine boot timeout'));
            }, timeoutMs);
            state.pending.set('boot', {
                resolve: (value) => {
                    clearTimeout(timer);
                    resolve(value);
                },
                reject: (error) => {
                    clearTimeout(timer);
                    reject(error);
                },
            });
            worker.postMessage({ type: 'boot' });
        });
    }

    async function start(characterId) {
        const result = await requestJson('/api/story/run/local/start', {
            method: 'POST',
            body: JSON.stringify({ character_id: characterId || 'common_flower' }),
        });
        state.active = true;
        state.run = {
            id: result.run.id,
            seed: result.run.seed,
            state: result.state,
            state_version: 1,
            content_version: result.run.content_version,
        };
        state.seq = 0;
        state.lastDigest = '';
        state.stateDigest = '';
        state.log = [];
        state.lastError = '';
        // 服务端可能已有本轮的检查点（页面刷新/重进），对齐 seq 与摘要。
        try {
            const resumed = await requestJson('/api/story/run/local/resume', {
                method: 'POST',
                body: JSON.stringify({ run_id: state.run.id }),
            });
            if (resumed.checkpoint) {
                state.seq = Number(resumed.checkpoint.seq || 0);
                state.lastDigest = String(resumed.checkpoint.server_digest || '');
                state.run.state = resumed.state || state.run.state;
                state.stateDigest = state.lastDigest;
            }
        } catch (error) {
            console.warn('[story-local] resume during start failed', error);
        }
        notify();
        return result;
    }

    function checkpointKind(previous, next) {
        const previousPhase = String((previous && previous.phase) || '');
        const nextPhase = String((next && next.phase) || '');
        if (previousPhase === 'combat' && nextPhase !== 'combat') return 'combat';
        const previousFloor = Number((previous && previous.current_floor) || 0);
        const nextFloor = Number((next && next.current_floor) || 0);
        if (nextFloor > previousFloor) return 'floor';
        return '';
    }

    async function apply(actionType, payload) {
        if (!state.active || !state.run) throw new Error('local run not started');
        const previousState = state.run.state;
        const result = await send('step', {
            state: previousState,
            action_type: actionType,
            payload: payload || {},
            seed: state.run.seed,
        });
        state.log.push({ type: actionType, payload: payload || {} });
        state.run = {
            ...state.run,
            state: result.state,
            state_version: (state.run.state_version || 1) + 1,
        };
        state.stateDigest = result.digest || '';
        notify();
        const kind = checkpointKind(previousState, result.state);
        if (kind) {
            try {
                await checkpoint(kind);
            } catch (error) {
                state.lastError = error.message || 'checkpoint failed';
                console.warn('[story-local] checkpoint failed', error);
            }
        }
        return { run: state.run, events: result.events || [], local: true };
    }

    async function checkpoint(kind) {
        if (!state.active || !state.run) throw new Error('local run not started');
        if (!state.log.length) return null;
        const actions = state.log.slice();
        const body = {
            run_id: state.run.id,
            seq: state.seq + 1,
            kind: kind || 'floor',
            floor: Number((state.run.state && state.run.state.current_floor) || 0),
            actions,
            client_digest: state.stateDigest,
            prev_digest: state.lastDigest,
        };
        try {
            const result = await requestJson('/api/story/run/local/checkpoint', {
                method: 'POST',
                body: JSON.stringify(body),
            });
            state.seq = Number(result.seq || body.seq);
            state.lastDigest = String(result.server_digest || state.stateDigest);
            state.log = state.log.slice(actions.length);
            state.lastError = '';
            notify();
            return result;
        } catch (error) {
            if (error.status === 409) {
                state.lastError = error.payload && error.payload.error === 'STORY_CHECKPOINT_MISMATCH'
                    ? 'checkpoint_mismatch'
                    : (error.payload && error.payload.error) || 'checkpoint_rejected';
                notify();
                await resume();
            }
            throw error;
        }
    }

    async function resume() {
        if (!state.run) throw new Error('local run not started');
        const result = await requestJson('/api/story/run/local/resume', {
            method: 'POST',
            body: JSON.stringify({ run_id: state.run.id }),
        });
        if (result.checkpoint) {
            state.seq = Number(result.checkpoint.seq || 0);
            state.lastDigest = String(result.checkpoint.server_digest || '');
            state.run = { ...state.run, state: result.state, state_version: (state.run.state_version || 1) + 1 };
            state.stateDigest = state.lastDigest;
        } else {
            state.run = { ...state.run, state: result.state };
            state.seq = 0;
            state.lastDigest = '';
        }
        state.log = [];
        notify();
        return result;
    }

    window.GtnStoryLocal = {
        isActive: () => Boolean(state.active),
        start,
        apply,
        resume,
        checkpoint,
        boot,
        subscribe(fn) {
            state.listeners.add(fn);
            return () => state.listeners.delete(fn);
        },
        snapshot,
    };
})();
