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
