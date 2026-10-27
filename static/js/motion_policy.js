/* Shared animation policy for every GTN surface. */
(function installGtnMotionPolicy(root) {
    'use strict';

    const reduceQuery = root.matchMedia
        ? root.matchMedia('(prefers-reduced-motion: reduce)')
        : null;
    const listeners = new Set();
    let reduced = Boolean(reduceQuery && reduceQuery.matches);
    let hidden = Boolean(document.hidden);

    function deviceIsConstrained() {
        const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        const memory = Number(navigator.deviceMemory);
        const cores = Number(navigator.hardwareConcurrency);
        return Boolean(
            (connection && connection.saveData)
            || (Number.isFinite(memory) && memory > 0 && memory <= 2)
            || (Number.isFinite(cores) && cores > 0 && cores <= 2)
            || (Number.isFinite(memory) && memory > 0 && memory <= 4
                && Number.isFinite(cores) && cores > 0 && cores <= 4),
        );
    }

    let constrained = deviceIsConstrained();

    function notify() {
        const html = document.documentElement;
        html.classList.toggle('gtn-motion-reduce', reduced);
        html.classList.toggle('gtn-low-performance', constrained && !reduced);
        html.classList.toggle('gtn-page-hidden', hidden);
        html.dataset.gtnMotion = reduced ? 'reduce' : (constrained ? 'low' : 'full');
        listeners.forEach((listener) => {
            try { listener(api); } catch (_) { /* optional observers must not break UI */ }
        });
    }

    function onChange(listener) {
        if (typeof listener !== 'function') return () => {};
        listeners.add(listener);
        return () => listeners.delete(listener);
    }

    function shouldAnimate(kind = 'decorative') {
        if (hidden) return false;
        if (reduced) return kind === 'essential';
        if (constrained && (kind === 'continuous' || kind === 'bulk' || kind === 'trail')) return false;
        return true;
    }

    function duration(value, kind = 'decorative') {
        const base = Math.max(0, Number(value) || 0);
        if (reduced) return kind === 'essential' ? Math.min(base, 80) : 1;
        if (constrained && (kind === 'continuous' || kind === 'bulk' || kind === 'trail')) {
            return Math.min(base, 140);
        }
        return base;
    }

    const api = Object.freeze({
        get reduced() { return reduced; },
        get constrained() { return constrained; },
        get hidden() { return hidden; },
        isReduced: () => reduced,
        isLowPerformance: () => constrained,
        isHidden: () => hidden,
        shouldAnimate,
        duration,
        onChange,
        refresh: () => {
            reduced = Boolean(reduceQuery && reduceQuery.matches);
            constrained = deviceIsConstrained();
            hidden = Boolean(document.hidden);
            notify();
        },
    });

    function bindMediaQuery(query) {
        if (!query) return;
        const handler = () => {
            reduced = Boolean(query.matches);
            notify();
        };
        if (typeof query.addEventListener === 'function') query.addEventListener('change', handler);
        else if (typeof query.addListener === 'function') query.addListener(handler);
    }

    bindMediaQuery(reduceQuery);
    document.addEventListener('visibilitychange', () => {
        hidden = Boolean(document.hidden);
        notify();
    });
    notify();
    root.GTNMotion = api;
})(window);
