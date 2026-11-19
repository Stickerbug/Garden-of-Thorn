// 左下角 Tips 小贴士。
// 数据：/static/data/tips.json（可编辑，随包发布）。
// 抽取：最近 50 条不重复 + 候选池内均匀随机；状态存 localStorage。
// 富文本：[[card:xxx]] / [[icon:xxx]] / [[status:xxx]] 复用 game.js 的 colorizeCardText，
//        卡牌 chip 的悬停预览由 bindInlineCardChips 绑定。
(function () {
    'use strict';

    var VIEWS = ['view-login', 'view-lobby', 'view-draft', 'view-event-select'];
    var STATE_KEY = 'gtn_tips_state_v1';
    var MIN_INTERVAL_MS = 30000;
    var MAX_RECENT = 50;
    var LONG_PRESS_MS = 400;
    var AUTHOR_HOLD_MS = 1800;

    var box = null;
    var textEl = null;
    var authorEl = null;
    var labelEl = null;
    var tips = [];
    var fileVersion = '';
    var loaded = false;
    var loading = false;
    var current = null;
    var lastDrawAt = 0;
    var pendingView = null;
    var authorTimer = 0;
    var authorHideTimer = 0;

    function $(id) {
        return document.getElementById(id);
    }

    function lang() {
        var raw = String(document.documentElement.getAttribute('lang') || 'zh').toLowerCase().slice(0, 2);
        return /^(zh|en|fr|ja)$/.test(raw) ? raw : 'zh';
    }

    function escapeHtml(value) {
        if (typeof window.escapeHtml === 'function') return window.escapeHtml(value);
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (ch) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
        });
    }

    // ---- 状态 ----

    function readState() {
        try {
            var raw = window.localStorage.getItem(STATE_KEY);
            var parsed = raw ? JSON.parse(raw) : null;
            if (parsed && parsed.v === 1 && Array.isArray(parsed.recent)) {
                return { v: 1, file: String(parsed.file || ''), recent: parsed.recent.filter(function (id) { return typeof id === 'string'; }) };
            }
        } catch (e) { /* 隐私模式 / 脏数据：当作空状态 */ }
        return { v: 1, file: '', recent: [] };
    }

    function writeState(state) {
        try {
            window.localStorage.setItem(STATE_KEY, JSON.stringify(state));
        } catch (e) { /* 写不进去就只用内存态，不影响本次会话 */ }
    }

    // ---- 抽取 ----

    function draw() {
        if (!tips.length) return;
        var state = readState();
        var known = {};
        tips.forEach(function (tip) { known[tip.id] = true; });
        var recent = state.recent.filter(function (id) { return known[id]; });
        var pool = tips.filter(function (tip) { return recent.indexOf(tip.id) < 0; });
        if (!pool.length) {
            recent = [];
            pool = tips.slice();
        }
        var picked = pool[Math.floor(Math.random() * pool.length)];
        recent.unshift(picked.id);
        state.recent = recent.slice(0, Math.min(MAX_RECENT, tips.length - 1));
        state.file = fileVersion;
        writeState(state);
        current = picked;
        lastDrawAt = Date.now();
        render(picked);
    }

    // ---- 渲染 ----

    function colorize(segment) {
        if (typeof window.colorizeCardText === 'function') {
            try {
                return window.colorizeCardText(segment, { terms: false });
            } catch (e) { /* 落到纯文本 */ }
        }
        return escapeHtml(segment);
    }

    // 链接文字：解码后通常短得多（wiki 那条是中文路径），仍然过长就退化成域名。
    function linkLabel(href) {
        var shown = href;
        try {
            shown = decodeURI(href);
        } catch (e) { /* 编码不规范就保留原样 */ }
        if (shown.length > 64) {
            try {
                shown = new URL(href).host + '/…';
            } catch (e) {
                shown = shown.slice(0, 61) + '…';
            }
        }
        return shown;
    }

    // 裸链接（例如 wiki 那条）自动变成可点击的 <a>，其余片段交给 colorizeCardText。
    function renderBody(text) {
        var parts = String(text || '').split(/(https?:\/\/[^\s<>"'）)】\]]+)/g);
        var html = '';
        for (var i = 0; i < parts.length; i += 1) {
            var part = parts[i];
            if (!part) continue;
            if (i % 2 === 1) {
                var href = part.replace(/[.,;:!?]+$/, '');
                var tail = part.slice(href.length);
                html += '<a class="gtn-tips-link" href="' + escapeHtml(href) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(linkLabel(href)) + '</a>' + escapeHtml(tail);
            } else {
                html += colorize(part);
            }
        }
        return html;
    }

    function textFor(tip) {
        var body = tip && tip.text;
        if (typeof body === 'string') return body;
        if (!body || typeof body !== 'object') return '';
        return body[lang()] || body.zh || '';
    }

    function render(tip) {
        if (!box || !textEl) return;
        var text = textFor(tip);
        if (!text) {
            box.classList.add('hidden');
            return;
        }
        textEl.innerHTML = renderBody(text);
        if (typeof window.bindInlineCardChips === 'function') {
            try {
                window.bindInlineCardChips(textEl, { interactive: true });
            } catch (e) { /* chip 交互绑不上不影响展示 */ }
        }
        if (labelEl) labelEl.textContent = 'Tips:';
        if (authorEl) authorEl.textContent = tip.author ? '—— ' + tip.author : '';
        box.classList.remove('hidden');
        box.classList.add('is-visible');
        hideAuthor();
    }

    function hide() {
        if (box) {
            box.classList.add('hidden');
            box.classList.remove('is-visible');
        }
        hideAuthor();
    }

    // ---- 作者：桌面悬停 / 移动端长按 ----

    function showAuthor() {
        if (!authorEl || !current || !current.author) return;
        if (authorHideTimer) {
            window.clearTimeout(authorHideTimer);
            authorHideTimer = 0;
        }
        authorEl.classList.add('is-visible');
    }

    function hideAuthor() {
        if (authorTimer) {
            window.clearTimeout(authorTimer);
            authorTimer = 0;
        }
        if (authorHideTimer) {
            window.clearTimeout(authorHideTimer);
            authorHideTimer = 0;
        }
        if (authorEl) authorEl.classList.remove('is-visible');
    }

    function bindAuthorTriggers() {
        if (!textEl) return;
        textEl.addEventListener('mouseenter', showAuthor);
        textEl.addEventListener('mouseleave', hideAuthor);
        textEl.addEventListener('touchstart', function () {
            hideAuthor();
            authorTimer = window.setTimeout(function () {
                authorTimer = 0;
                showAuthor();
                authorHideTimer = window.setTimeout(hideAuthor, AUTHOR_HOLD_MS);
            }, LONG_PRESS_MS);
        }, { passive: true });
        ['touchend', 'touchcancel', 'touchmove'].forEach(function (name) {
            textEl.addEventListener(name, function () {
                if (authorTimer) {
                    window.clearTimeout(authorTimer);
                    authorTimer = 0;
                }
            }, { passive: true });
        });
    }

    // ---- 数据加载 ----

    function normalize(raw) {
        var list = raw && Array.isArray(raw.tips) ? raw.tips : [];
        fileVersion = String((raw && raw.version) || '');
        var out = [];
        var seenId = {};
        list.forEach(function (item, index) {
            if (!item || typeof item !== 'object') return;
            var id = String(item.id || ('t' + (index + 1))).trim();
            if (!id || seenId[id]) return;
            var body = item.text;
            if (typeof body === 'string') body = { zh: body };
            if (!body || typeof body !== 'object') return;
            var has = false;
            ['zh', 'en', 'fr', 'ja'].forEach(function (key) {
                if (typeof body[key] === 'string' && body[key].trim()) {
                    body[key] = body[key].trim();
                    has = true;
                }
            });
            if (!has) return;
            seenId[id] = true;
            out.push({ id: id, author: String(item.author || '').trim(), text: body });
        });
        return out;
    }

    function load() {
        if (loaded || loading) return;
        loading = true;
        var version = (box && box.getAttribute('data-version')) || document.documentElement.getAttribute('data-static-version') || '';
        var url = '/static/data/tips.json' + (version ? '?v=' + encodeURIComponent(version) : '');
        window.fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                if (!res.ok) throw new Error('tips.json ' + res.status);
                return res.json();
            })
            .then(function (raw) {
                tips = normalize(raw);
                loaded = true;
                loading = false;
                if (!tips.length) return;
                if (pendingView && VIEWS.indexOf(pendingView) >= 0) {
                    pendingView = null;
                    onView(document.querySelector('.view:not(.hidden)') ? document.querySelector('.view:not(.hidden)').id : 'view-login', true);
                }
            })
            .catch(function () {
                loading = false;
                hide();
            });
    }

    // ---- 对外接口 ----

    function onView(viewId, force) {
        if (!box) return;
        if (VIEWS.indexOf(viewId) < 0) {
            hide();
            return;
        }
        box.setAttribute('data-view', viewId);
        if (!loaded) {
            pendingView = viewId;
            load();
            return;
        }
        if (!tips.length) {
            hide();
            return;
        }
        var now = Date.now();
        if (!current || force || now - lastDrawAt >= MIN_INTERVAL_MS) {
            draw();
        } else {
            render(current);
        }
    }

    function onLang() {
        if (current) render(current);
    }

    function onCardsReady() {
        if (current) render(current);
    }

    function init() {
        box = $('gtn-tips');
        if (!box) return;
        textEl = $('gtn-tips-text');
        authorEl = $('gtn-tips-author');
        labelEl = $('gtn-tips-label');
        bindAuthorTriggers();
        load();
        var visible = document.querySelector('.view:not(.hidden)');
        if (visible && visible.id) onView(visible.id);
    }

    window.GtnTips = {
        onView: function (viewId) {
            try { onView(viewId); } catch (e) { /* 展示模块绝不能影响视图切换 */ }
        },
        onLang: function () {
            try { onLang(); } catch (e) { /* ignore */ }
        },
        onCardsReady: function () {
            try { onCardsReady(); } catch (e) { /* ignore */ }
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
