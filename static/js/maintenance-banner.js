(function () {
    'use strict';

    // 服务端公告横幅：更新前 5 分钟的提示要一直贴在屏幕最顶端，
    // 刷新页面、切到故事页也都得看得到，所以这里既轮询接口也接受 socket 推送。
    var POLL_INTERVAL_MS = 15000;
    var BANNER_ID = 'gtn-maintenance-banner';

    var bannerNode = null;
    var messageNode = null;
    var clockNode = null;
    var tickTimer = null;

    function ensureNode() {
        if (bannerNode && bannerNode.isConnected) {
            return bannerNode;
        }
        bannerNode = document.createElement('div');
        bannerNode.id = BANNER_ID;
        bannerNode.className = 'gtn-maintenance-banner';
        bannerNode.setAttribute('role', 'status');
        bannerNode.setAttribute('aria-live', 'assertive');
        bannerNode.hidden = true;

        messageNode = document.createElement('span');
        messageNode.className = 'gtn-maintenance-message';
        clockNode = document.createElement('span');
        clockNode.className = 'gtn-maintenance-clock';

        bannerNode.appendChild(messageNode);
        bannerNode.appendChild(clockNode);
        (document.body || document.documentElement).appendChild(bannerNode);
        return bannerNode;
    }

    function formatClock(seconds) {
        var total = Math.max(0, Math.round(Number(seconds) || 0));
        var minutes = Math.floor(total / 60);
        var rest = total % 60;
        return minutes + ':' + (rest < 10 ? '0' : '') + rest;
    }

    function stopTicking() {
        if (tickTimer) {
            window.clearInterval(tickTimer);
            tickTimer = null;
        }
    }

    function hide() {
        stopTicking();
        if (!bannerNode) {
            return;
        }
        bannerNode.hidden = true;
        bannerNode.classList.remove('is-visible');
        bannerNode.removeAttribute('data-expires-at');
        bannerNode.removeAttribute('data-sequence');
        document.documentElement.classList.remove('gtn-maintenance-active');
    }

    function tick() {
        if (!bannerNode || bannerNode.hidden) {
            return;
        }
        var expiresAt = Number(bannerNode.getAttribute('data-expires-at') || 0);
        if (!expiresAt) {
            return;
        }
        var remaining = expiresAt - Date.now() / 1000;
        if (remaining <= 0) {
            hide();
            return;
        }
        clockNode.textContent = '剩余 ' + formatClock(remaining);
    }

    function show(payload) {
        if (!payload || !payload.active || !payload.message) {
            hide();
            return;
        }
        ensureNode();
        var sequence = String(payload.sequence || 0);
        if (bannerNode.getAttribute('data-sequence') === sequence && !bannerNode.hidden) {
            bannerNode.setAttribute('data-expires-at', String(Number(payload.expires_at) || 0));
            tick();
            return;
        }
        bannerNode.setAttribute('data-sequence', sequence);
        bannerNode.setAttribute('data-expires-at', String(Number(payload.expires_at) || 0));
        messageNode.textContent = String(payload.message);
        bannerNode.hidden = false;
        bannerNode.classList.add('is-visible');
        document.documentElement.classList.add('gtn-maintenance-active');
        tick();
        stopTicking();
        tickTimer = window.setInterval(tick, 1000);
    }

    function poll() {
        fetch('/api/maintenance/notice', { credentials: 'same-origin', cache: 'no-store' })
            .then(function (response) {
                return response.ok ? response.json() : null;
            })
            .then(function (payload) {
                if (payload) {
                    show(payload);
                }
            })
            .catch(function () {
                // 网络抖动时保留当前横幅，下一次轮询再对齐。
            });
    }

    function start() {
        poll();
        window.setInterval(poll, POLL_INTERVAL_MS);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }

    window.GtnMaintenanceBanner = { show: show, hide: hide, poll: poll };
})();
