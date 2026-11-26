/* 实验性 UI 开关（实验版界面外壳）
 * - 只负责「开关状态 + 外壳属性」，具体样式在 static/css/experimental-ui.css。
 * - 独立保存到 gtn_ui_shell，不影响既有 gtn_ui_style / gtn_home_ui 的语义；
 *   关掉开关即回到原版界面，不清空牌组、旅程或帐号偏好。
 * - 仅管理员 / staff / tester 可在设置里看到并勾选；无权限时强制回落原版。 */
(function () {
    'use strict';

    var SHELL_KEY = 'gtn_ui_shell';
    var SHELL_EXPERIMENTAL = 'experimental';
    var SHELL_STANDARD = 'standard';
    var ROLE_ALLOWED = { admin: true, staff: true, tester: true };
    var ROW_ID = 'settings-experimental-ui-row';
    var INPUT_ID = 'settings-experimental-ui';

    function storageKey(key) {
        if (!window.__GTN_BETA_MODE__) return key;
        return 'gtn_beta_' + String(key).slice(4);
    }

    function readCookie(key) {
        try {
            var prefix = encodeURIComponent(key) + '=';
            var part = String(document.cookie || '').split(';')
                .map(function (item) { return item.trim(); })
                .filter(function (item) { return item.indexOf(prefix) === 0; })[0];
            return part ? decodeURIComponent(part.slice(prefix.length)) : null;
        } catch (err) {
            return null;
        }
    }

    function writeCookie(key, value) {
        try {
            var secure = window.location.protocol === 'https:' ? '; Secure' : '';
            document.cookie = encodeURIComponent(key) + '=' + encodeURIComponent(String(value))
                + '; Max-Age=31536000; Path=/; SameSite=Lax' + secure;
        } catch (err) {
            /* ignore */
        }
    }

    /* 与模板里的引导脚本、game.js 的持久化层一致：cookie → localStorage → sessionStorage，
     * 这样隐私模式、清理缓存等情况下开关状态也能保持。 */
    function readShell() {
        var key = storageKey(SHELL_KEY);
        var value = readCookie(key);
        if (value == null) {
            try { value = window.localStorage.getItem(key); } catch (err) { value = null; }
        }
        if (value == null) {
            try { value = window.sessionStorage.getItem(key); } catch (err) { value = null; }
        }
        return value === SHELL_EXPERIMENTAL ? SHELL_EXPERIMENTAL : SHELL_STANDARD;
    }

    function writeShell(value) {
        var key = storageKey(SHELL_KEY);
        writeCookie(key, value);
        try { window.localStorage.setItem(key, value); } catch (err) { /* ignore */ }
        try { window.sessionStorage.setItem(key, value); } catch (err) { /* ignore */ }
    }

    function roleOf(account) {
        if (!account) return '';
        return String(account.role_type || account.role || '').toLowerCase();
    }

    function isAvailable(account) {
        return !!ROLE_ALLOWED[roleOf(account)];
    }

    function isEnabled() {
        return readShell() === SHELL_EXPERIMENTAL;
    }

    function apply() {
        var root = document.documentElement;
        if (!root) return;
        root.setAttribute('data-ui-shell', isEnabled() ? SHELL_EXPERIMENTAL : SHELL_STANDARD);
    }

    function setEnabled(enabled) {
        writeShell(enabled ? SHELL_EXPERIMENTAL : SHELL_STANDARD);
        apply();
        // 两种外壳的 DOM 结构差异不只样式，整页重载最稳，也避免半切换状态。
        try {
            window.location.reload();
        } catch (err) {
            /* ignore */
        }
    }

    function isSignedIn(account) {
        if (!account || typeof account !== 'object') return false;
        return Boolean(account.user_id || account.id || account.username || account.username_lower);
    }

    function syncAccount(account) {
        var available = isAvailable(account);
        var row = document.getElementById(ROW_ID);
        var input = document.getElementById(INPUT_ID);
        if (row) row.classList.toggle('hidden', !available);
        if (input) input.checked = isEnabled();
        // 只在「确实已登录但没有权限」时回落原版；游客对象与未恢复的登录态都保留
        // 上一次的选择，否则刷新时帐号还没恢复就会把开关冲掉。
        if (isSignedIn(account) && !available && isEnabled()) {
            writeShell(SHELL_STANDARD);
            apply();
        }
    }

    function onToggle(event) {
        if (!event || !event.target) return;
        if (event.target.id !== INPUT_ID) return;
        setEnabled(!!event.target.checked);
    }

    function bind() {
        var input = document.getElementById(INPUT_ID);
        if (input && !input.dataset.gtnExperimentalBound) {
            input.dataset.gtnExperimentalBound = '1';
            input.addEventListener('change', onToggle);
        }
        if (!document.documentElement.dataset.gtnExperimentalDelegated) {
            document.documentElement.dataset.gtnExperimentalDelegated = '1';
            document.addEventListener('change', onToggle, true);
        }
    }

    apply();


    /* 公告面板：补一个显眼的「关闭」按钮，并保证它压在游戏各种遮罩之上 */
    var annCloseBound = false;
    function ensureAnnClose() {
        var pop = document.getElementById('changelog-popover');
        if (!pop || pop.dataset.xuiClose === '1') return;
        var head = pop.querySelector('.account-popover-head');
        if (!head) return;
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'xui-ann-close';
        btn.textContent = '关闭';
        btn.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();
            if (typeof window.toggleChangelogPopover === 'function') window.toggleChangelogPopover(false);
            else pop.classList.add('hidden');
        });
        head.appendChild(btn);
        pop.dataset.xuiClose = '1';
    }
    function watchAnnClose() {
        if (annCloseBound) return;
        annCloseBound = true;
        ensureAnnClose();
        var pop = document.getElementById('changelog-popover');
        if (pop && window.MutationObserver) {
            new MutationObserver(ensureAnnClose).observe(pop, { attributes: true, attributeFilter: ['class'], childList: true, subtree: true });
        }
        document.addEventListener('click', function (event) {
            if (event.target && event.target.closest && event.target.closest('#btn-changelog-top')) {
                window.setTimeout(ensureAnnClose, 0);
            }
        }, true);
    }
    watchAnnClose();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bind);
    } else {
        bind();
    }

    window.GtnExperimentalUi = {
        KEY: SHELL_KEY,
        isEnabled: isEnabled,
        isAvailable: isAvailable,
        setEnabled: setEnabled,
        syncAccount: syncAccount,
        apply: apply
    };
})();

/* 第二批增强：公告筛选/搜索/逐条已读、商店购买确认。
 * 只在实验外壳启用时接管；关掉开关后完全回到原行为。 */
(function () {
    'use strict';

    var READ_KEY = 'gtn_ui_ann_read_v1';
    var state = { filter: 'all', query: '' };

    function shellOn() {
        return document.documentElement.getAttribute('data-ui-shell') === 'experimental';
    }

    function readSet() {
        try {
            var raw = window.localStorage.getItem(READ_KEY);
            var list = raw ? JSON.parse(raw) : [];
            return new Set(Array.isArray(list) ? list : []);
        } catch (err) {
            return new Set();
        }
    }

    function writeRead(set) {
        try {
            window.localStorage.setItem(READ_KEY, JSON.stringify(Array.from(set).slice(-400)));
        } catch (err) {
            /* ignore */
        }
    }

    function itemKey(item) {
        var title = item.querySelector('.ann-title');
        return [item.dataset.kind || '', item.dataset.time || '', title ? title.textContent : ''].join('|');
    }

    function decorate() {
        var list = document.getElementById('ann-list');
        if (!list) return;
        var read = readSet();
        Array.from(list.querySelectorAll('details.ann-item')).forEach(function (item) {
            var key = itemKey(item);
            if (read.has(key)) {
                item.classList.add('is-read');
            } else {
                item.classList.remove('is-read');
            }
            var summary = item.querySelector('summary.ann-summary');
            if (summary && !summary.querySelector('.xui-ann-dot')) {
                var dot = document.createElement('span');
                dot.className = 'xui-ann-dot';
                dot.setAttribute('aria-hidden', 'true');
                summary.appendChild(dot);
            }
            if (!item.dataset.xuiAnnBound) {
                item.dataset.xuiAnnBound = '1';
                item.addEventListener('toggle', function () {
                    if (!item.open) return;
                    var set = readSet();
                    set.add(itemKey(item));
                    writeRead(set);
                    item.classList.add('is-read');
                });
            }
        });
        applyFilter();
    }

    function applyFilter() {
        var list = document.getElementById('ann-list');
        if (!list) return;
        var query = state.query.trim().toLowerCase();
        var shown = 0;
        Array.from(list.querySelectorAll('details.ann-item')).forEach(function (item) {
            var kindOk = state.filter === 'all' || (item.dataset.kind || '') === state.filter;
            var text = (item.textContent || '').toLowerCase();
            var queryOk = !query || text.indexOf(query) >= 0;
            var visible = kindOk && queryOk;
            item.hidden = !visible;
            if (visible) shown += 1;
        });
        var count = document.querySelector('.xui-ann-count');
        if (count) count.textContent = shown + ' 条';
        var empty = list.querySelector(':scope > .xui-ann-empty');
        if (!shown) {
            if (!empty) {
                empty = document.createElement('p');
                empty.className = 'xui-ann-empty';
                empty.textContent = '没有符合条件的条目。';
                list.appendChild(empty);
            }
        } else if (empty) {
            empty.remove();
        }
    }

    function buildTools() {
        var pop = document.getElementById('changelog-popover');
        var list = document.getElementById('ann-list');
        if (!pop || !list || pop.querySelector('.xui-ann-tools')) return;
        var tools = document.createElement('div');
        tools.className = 'xui-ann-tools';

        [['all', '全部'], ['announcement', '公告'], ['changelog', '更新']].forEach(function (pair) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'xui-ann-tab' + (pair[0] === 'all' ? ' is-active' : '');
            btn.dataset.annFilter = pair[0];
            btn.textContent = pair[1];
            btn.addEventListener('click', function () {
                state.filter = pair[0];
                tools.querySelectorAll('.xui-ann-tab').forEach(function (node) {
                    node.classList.toggle('is-active', node === btn);
                });
                applyFilter();
            });
            tools.appendChild(btn);
        });

        var search = document.createElement('input');
        search.type = 'search';
        search.className = 'xui-ann-search';
        search.placeholder = '搜索公告…';
        search.addEventListener('input', function () {
            state.query = search.value || '';
            applyFilter();
        });
        tools.appendChild(search);

        var count = document.createElement('span');
        count.className = 'xui-ann-count';
        tools.appendChild(count);

        list.parentNode.insertBefore(tools, list);

        if (window.MutationObserver) {
            var observer = new MutationObserver(function () { decorate(); });
            observer.observe(list, { childList: true });
        }
    }

    var CONFIRM_SELECTOR = '[data-title-shop-buy], [data-player-skin-buy], [data-eye-style-buy], [data-mouth-style-buy], [data-background-buy]';

    function confirmPurchase(event) {
        var button = event.target && event.target.closest ? event.target.closest(CONFIRM_SELECTOR) : null;
        if (!button || button.disabled) return;
        if (button.dataset.xuiConfirmed === '1') {
            delete button.dataset.xuiConfirmed;
            return;
        }
        if (button.getAttribute('data-xui-skip-confirm') === '1') return;
        event.preventDefault();
        event.stopImmediatePropagation();
        var price = (button.textContent || '').replace(/\s+/g, ' ').trim();
        var card = button.closest('.title-shop-item');
        var name = card ? (card.querySelector('.title-shop-preview-name') || {}).textContent || '' : '';
        var message = (name ? name + '：' : '') + (price || '确认购买') + '\n购买后立即扣除，无法撤销。';
        var confirmFn = window.gameConfirm;
        var done = function (ok) {
            if (!ok) return;
            button.dataset.xuiConfirmed = '1';
            button.click();
        };
        if (typeof confirmFn === 'function') {
            confirmFn('确认购买', message).then(done);
        } else if (window.confirm(message)) {
            done(true);
        }
    }

    function init() {
        if (!shellOn()) return;
        buildTools();
        decorate();
        document.addEventListener('click', confirmPurchase, true);
        window.GtnExperimentalUi.debug = { applyFilter: applyFilter, decorate: decorate };
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
