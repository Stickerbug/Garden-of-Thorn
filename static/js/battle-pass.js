// 通行证（S1 荆棘之路 / 黄金之路）UI。
// 设计：docs/通行证-计划.md；后端：battle_pass.py + /api/battle-pass*。
// 挂到 window.gtnBattlePass，由 game.js 的成就弹层在「通行证」页签调用。
(function () {
    'use strict';

    const API_BASE = '/api/battle-pass';
    const state = {
        payload: null,
        loading: false,
        error: '',
        claiming: false,
        purchasing: false,
    };

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        })[ch]);
    }

    async function request(url, options) {
        const response = await fetch(url, Object.assign({
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
        }, options || {}));
        let data = null;
        try {
            data = await response.json();
        } catch (_) {
            data = null;
        }
        if (!response.ok) {
            const message = (data && (data.error || data.message)) || `HTTP ${response.status}`;
            const error = new Error(message);
            error.status = response.status;
            throw error;
        }
        return data || {};
    }

    function applyPayload(data) {
        if (!data || !data.tracks) return;
        state.payload = data;
        state.error = '';
    }

    async function ensureLoaded(force) {
        if (state.loading) return;
        if (!force && state.payload) return;
        state.loading = true;
        state.error = '';
        renderPanel();
        try {
            const data = await request(API_BASE);
            applyPayload(data);
        } catch (err) {
            state.error = String(err && err.message ? err.message : err);
        } finally {
            state.loading = false;
            renderPanel();
        }
    }

    function splitReward(text) {
        const raw = String(text || '').trim();
        const match = raw.match(/^(\d[\d,]*)\s*(.+)$/);
        if (match) return { amount: match[1], unit: match[2] };
        return { amount: '', unit: raw };
    }

    function trackNodes(track, view, currentLevel) {
        const entries = Array.isArray(view.entries) ? view.entries : [];
        return entries.map((entry) => {
            const classes = ['bp-node'];
            if (entry.level % 10 === 0) classes.push('milestone');
            if (entry.claimed) classes.push('claimed');
            else if (entry.claimable) classes.push('claimable');
            else if (!entry.unlocked) classes.push('locked');
            if (entry.level === currentLevel) classes.push('current');
            const reward = splitReward(entry.text);
            const amount = reward.amount ? `<span class="bp-node-amount">${escapeHtml(reward.amount)}</span>` : '';
            const unit = reward.unit ? `<span class="bp-node-unit">${escapeHtml(reward.unit)}</span>` : '';
            const icon = entry.icon ? `<img class="bp-node-icon" src="${escapeHtml(entry.icon)}" alt="" aria-hidden="true">` : '';
            const attrs = ` data-track="${track}" data-level="${entry.level}"${entry.claimable ? ' data-claim="1"' : ''}`;
            const tag = entry.claimable ? 'button' : 'div';
            const title = `Lv.${entry.level} · ${escapeHtml(entry.text || '')}${entry.claimed ? '（已领取）' : ''}`;
            return `<${tag} class="${classes.join(' ')}"${entry.claimable ? ' type="button"' : ''}${attrs} title="${title}">
                <span class="bp-bubble"><span class="bp-bubble-lv">${entry.level}</span>${entry.level % 10 === 0 ? '<span class="bp-bubble-star">★</span>' : ''}</span>
                <span class="bp-node-reward">${icon}${amount}${unit}</span>
            </${tag}>`;
        }).join('');
    }

    function renderTrack(track, payload) {
        const view = payload.tracks[track] || { entries: [], label: '', claimable_count: 0 };
        const golden = track === 'golden';
        const locked = golden && !payload.golden;
        const currentLevel = Number(payload.level || 0);
        const head = `<div class="bp-track-head">
            <span class="bp-track-name ${golden ? 'golden' : 'free'}">${escapeHtml(view.label || track)}</span>
            <span class="bp-track-meta">已领 ${Number(view.claimed_count || 0)} / ${Number(payload.max_level || 100)}</span>
            ${view.claimable_count && !locked
                ? `<button class="bp-claim-all" type="button" data-track="${track}">一键领取 (${view.claimable_count})</button>`
                : ''}
        </div>`;
        const note = locked
            ? `<div class="bp-locked-note">${Number(payload.golden_price || 250)} 金露解锁后可领取本轨奖励</div>`
            : '';
        const rail = `<div class="bp-rail${locked ? ' bp-rail-locked' : ''}" data-track="${track}" data-current="${currentLevel}">
            ${trackNodes(track, view, currentLevel)}
        </div>`;
        return `<section class="bp-track ${golden ? 'golden' : 'free'}">${head}${note}${rail}</section>`;
    }

    function scrollRailsToCurrent(panel) {
        panel.querySelectorAll('.bp-rail').forEach((rail) => {
            const current = rail.querySelector('.bp-node.current');
            if (!current) return;
            const target = current.offsetLeft - rail.clientWidth / 2 + current.clientWidth / 2;
            rail.scrollLeft = Math.max(0, target);
        });
    }

    function renderPanel(container) {
        const panel = container || document.getElementById('achievements-pass-panel');
        if (!panel) return;
        if (state.loading && !state.payload) {
            panel.innerHTML = '<div class="account-replay-sub">通行证加载中…</div>';
            return;
        }
        if (state.error && !state.payload) {
            panel.innerHTML = `<div class="account-replay-sub">${escapeHtml(state.error)}</div>
                <button class="bp-retry" type="button" data-bp-retry="1">重试</button>`;
            return;
        }
        const payload = state.payload;
        if (!payload) {
            panel.innerHTML = '<div class="account-replay-sub">登录后查看通行证。</div>';
            return;
        }
        const level = Number(payload.level || 0);
        const xpInto = Number(payload.xp_into_level || 0);
        const xpPer = Number(payload.xp_per_level || 100);
        const pct = Math.max(0, Math.min(100, Math.round((xpInto / Math.max(1, xpPer)) * 100)));
        const price = Number(payload.golden_price || 250);
        const affordable = Number(payload.golden_dew || 0) >= price;
        const golden = payload.golden
            ? '<span class="bp-golden-on">黄金之路已解锁</span>'
            : `<button class="bp-buy" type="button" data-bp-buy="1"${affordable ? '' : ' disabled'}>解锁黄金之路 · ${price} 金露</button>`;
        const perks = `<div class="bp-perks">
            <span>荆露 ×${payload.golden_perks.dew_multiplier}</span>
            <span>经验 ×${payload.golden_perks.xp_multiplier}</span>
            <span>天梯特殊修正 +${payload.golden_perks.rank_special_bonus}</span>
            <span>每日签到额外 保分卡 + 双倍卡</span>
        </div>`;
        const weekly = `<div class="bp-weekly">本周爬塔加成：前 ${Number(payload.story_weekly_triple_count || 3)} 次 ×3（已用 ${Number(payload.story_week_used || 0)} 次）</div>`;
        const maxLevel = Number(payload.max_level || 100);
        const nextHint = level >= maxLevel
            ? '已达满级，继续升级可循环领取溢出奖励'
            : `距下一级还差 ${Math.max(0, xpPer - xpInto)} 经验`;
        const seasonStart = String(payload.season_start || '').slice(0, 10);
        const seasonEndRaw = String(payload.season_end || '');
        const seasonEnd = seasonEndRaw.slice(0, 10);
        const seasonEndClock = seasonEndRaw.slice(11, 16);
        const endMs = payload.season_end ? Date.parse(payload.season_end) : 0;
        const daysLeft = endMs ? Math.max(0, Math.ceil((endMs - Date.now()) / 86400000)) : 0;
        const seasonMeta = seasonStart && seasonEnd
            ? `<div class="bp-season-meta">赛季 ${seasonStart} → ${seasonEnd}${seasonEndClock ? ' ' + seasonEndClock : ''} · 剩余 ${daysLeft} 天</div>`
            : '';
        panel.innerHTML = `
            <div class="bp-season">
                <div class="bp-head">
                    <div class="bp-head-title"><span class="bp-season-chip">S1</span>荆棘之路 · 黄金之路</div>
                    <div class="bp-golden-row">${golden}<span class="bp-balance">金露 ${Number(payload.golden_dew || 0)}</span></div>
                </div>
                <div class="bp-level-row">
                    <div class="bp-head-level">Lv.<strong>${level}</strong></div>
                    <div class="bp-bar"><div class="bp-bar-fill" style="width:${pct}%"></div></div>
                    <div class="bp-head-xp"><span class="bp-xp-value"><img class="bp-xp-icon" src="/static/assets/ui-icons/pass-xp.svg" alt="" aria-hidden="true">${xpInto} / ${xpPer} XP</span><small>${nextHint}</small></div>
                </div>
                ${perks}
                ${weekly}
                ${seasonMeta}
            </div>
            <div class="bp-tracks">
                ${renderTrack('free', payload)}
                ${renderTrack('golden', payload)}
            </div>`;
        scrollRailsToCurrent(panel);
    }

    async function claim(track, level) {
        if (state.claiming) return;
        state.claiming = true;
        try {
            const data = await request(`${API_BASE}/claim`, {
                method: 'POST',
                body: JSON.stringify({ track, level }),
            });
            applyPayload(data);
        } catch (err) {
            state.error = String(err && err.message ? err.message : err);
        } finally {
            state.claiming = false;
            renderPanel();
        }
    }

    async function claimAll(track) {
        if (state.claiming) return;
        state.claiming = true;
        try {
            const data = await request(`${API_BASE}/claim-all`, {
                method: 'POST',
                body: JSON.stringify({ track }),
            });
            applyPayload(data);
        } catch (err) {
            state.error = String(err && err.message ? err.message : err);
        } finally {
            state.claiming = false;
            renderPanel();
        }
    }

    async function purchase() {
        if (state.purchasing) return;
        const price = Number((state.payload && state.payload.golden_price) || 250);
        if (!window.confirm(`确认花费 ${price} 金露解锁黄金之路？`)) return;
        state.purchasing = true;
        try {
            const data = await request(`${API_BASE}/purchase`, { method: 'POST', body: '{}' });
            applyPayload(data);
        } catch (err) {
            state.error = String(err && err.message ? err.message : err);
        } finally {
            state.purchasing = false;
            renderPanel();
        }
    }

    document.addEventListener('click', (event) => {
        const target = event.target;
        if (!target || !target.closest) return;
        const claimNode = target.closest('[data-claim="1"]');
        if (claimNode) {
            claim(claimNode.dataset.track, Number(claimNode.dataset.level));
            return;
        }
        const allBtn = target.closest('.bp-claim-all');
        if (allBtn) {
            claimAll(allBtn.dataset.track);
            return;
        }
        if (target.closest('.bp-buy')) {
            purchase();
            return;
        }
        if (target.closest('.bp-retry')) {
            ensureLoaded(true);
        }
    });

    window.gtnBattlePass = {
        ensureLoaded,
        render: renderPanel,
        state,
    };
    document.addEventListener('DOMContentLoaded', () => {
        if (document.getElementById('achievements-pass-panel')) renderPanel();
    });
})();
