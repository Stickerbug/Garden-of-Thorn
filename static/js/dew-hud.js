/* 全局右上角货币栏：只读余额，自动刷新，不持有或修改玩家资产。 */
(function () {
  'use strict';

  let root = null;
  let dewValue = null;
  let goldenValue = null;
  let inFlight = false;
  let started = false;

  function number(value) {
    const parsed = Math.floor(Number(value) || 0);
    return parsed.toLocaleString(document.documentElement.lang || 'zh-CN');
  }

  function item(currency, icon, label) {
    const wrapper = document.createElement('span');
    wrapper.className = `dew-hud-item is-${currency}`;
    wrapper.title = label;
    const image = document.createElement('img');
    image.src = icon;
    image.alt = '';
    image.setAttribute('aria-hidden', 'true');
    const value = document.createElement('span');
    value.dataset.dewHudValue = currency;
    value.textContent = '0';
    wrapper.appendChild(image);
    wrapper.appendChild(value);
    return wrapper;
  }

  function ensureRoot() {
    if (root) return root;
    root = document.createElement('div');
    root.id = 'dew-hud';
    root.className = 'dew-hud';
    root.hidden = true;
    root.setAttribute('aria-live', 'polite');
    root.appendChild(item('dew', '/static/assets/ui-icons/thorn-dew.svg', '荆露'));
    root.appendChild(item('golden', '/static/assets/ui-icons/golden-dew.svg', '金露'));
    document.body.appendChild(root);
    dewValue = root.querySelector('[data-dew-hud-value="dew"]');
    goldenValue = root.querySelector('[data-dew-hud-value="golden"]');
    return root;
  }

  function viewIsVisible(id) {
    const view = document.getElementById(id);
    return Boolean(view && !view.classList.contains('hidden'));
  }

  function syncVisibility() {
    if (!root) return;
    const hasBalance = root.dataset.hasBalance === 'true';
    const hiddenForView = viewIsVisible('view-game') || viewIsVisible('story-app');
    root.hidden = !hasBalance || hiddenForView;
  }

  async function refresh() {
    if (inFlight) return;
    inFlight = true;
    try {
      const response = await fetch('/api/thorn-dew', { credentials: 'same-origin', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      const hud = ensureRoot();
      if (!response.ok || !data.success || !data.balance) {
        hud.dataset.hasBalance = 'false';
        syncVisibility();
        return;
      }
      const dew = Number(data.balance.total || 0) || 0;
      const golden = Number(data.golden_balance || 0) || 0;
      dewValue.textContent = number(dew);
      goldenValue.textContent = number(golden);
      hud.setAttribute('aria-label', `荆露 ${dew}，金露 ${golden}`);
      hud.dataset.hasBalance = 'true';
      syncVisibility();
    } catch (_) {
      if (root) {
        root.dataset.hasBalance = 'false';
        syncVisibility();
      }
    } finally {
      inFlight = false;
    }
  }

  function start() {
    if (started) return;
    started = true;
    ensureRoot();
    syncVisibility();
    if (window.MutationObserver) {
      const observer = new window.MutationObserver(syncVisibility);
      ['view-game', 'story-app'].forEach((id) => {
        const view = document.getElementById(id);
        if (view) observer.observe(view, { attributes: true, attributeFilter: ['class', 'hidden'] });
      });
      root.viewObserver = observer;
    }
    refresh();
    window.setInterval(refresh, 15000);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refresh();
    });
    document.addEventListener('gtn:dew-updated', refresh);
    document.addEventListener('gtn:account-updated', refresh);
  }

  window.GtnDewHud = Object.freeze({ refresh });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
