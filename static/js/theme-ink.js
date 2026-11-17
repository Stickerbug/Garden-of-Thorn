/* 主题背景文字自适应（2026-11-17）
   把卡牌皮肤那套算法（采样文字脚下的背景亮度 → 用 WCAG 对比度方程解出
   同色相/饱和度下的目标明度）应用到主题背景上显示的所有文字。
   亮底压深、暗底提亮、中性带 ±0.12 强度渐变到 0；明度变化 <0.02 不动。
   只调整字色明度，不改布局、不加阴影；没有主题背景时整段不生效。 */
(() => {
  'use strict';

  const SAMPLE_WIDTH = 320;        // 采样画布宽（按 viewport 等比缩放）
  const NEUTRAL_HALF = 0.12;       // 与 SKIN_INK_NEUTRAL_HALF 一致
  const DARK_CONTRAST = 0.66;      // 与 SKIN_INK_CONTRAST_DARK 一致
  const LIGHT_ANCHOR = 0.90;       // 与 SKIN_INK_LIGHT_ANCHOR 一致
  const MAX_TARGETS = 600;
  const MIN_DELTA = 0.02;
  const MIN_CONTRAST = 3.0;        // 与底色对比度下限（WCAG AA 大字号口径）
  const SKIP_TAGS = new Set([
    'SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'CANVAS', 'IMG', 'SVG', 'VIDEO',
    'INPUT', 'TEXTAREA', 'SELECT', 'OPTION', 'BR', 'HR', 'PATH', 'CIRCLE', 'RECT',
  ]);

  const tileImages = new Map();
  let canvas = null;
  let ctx = null;
  let pixels = null;
  let canvasWidth = 0;
  let canvasHeight = 0;
  let scale = 1;
  let pending = 0;
  let scheduled = false;
  let running = false;

  function backdrop() {
    return document.getElementById('player-theme-backdrop');
  }

  function parseColor(text) {
    const raw = String(text || '').trim();
    if (!raw || raw === 'transparent') return null;
    const m = /rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?\)/.exec(raw);
    if (m) return [Number(m[1]), Number(m[2]), Number(m[3]), m[4] == null ? 1 : Number(m[4])];
    const hex = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec(raw);
    if (hex) {
      const h = hex[1].length === 3 ? hex[1].split('').map(c => c + c).join('') : hex[1];
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1];
    }
    return null;
  }

  function lumaOfRgb(rgb) {
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255;
  }

  function rgbToHsl(rgb) {
    const r = rgb[0] / 255, g = rgb[1] / 255, b = rgb[2] / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    if (max === min) return [0, 0, l];
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    let h;
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
    return [h, s, l];
  }

  function hueToRgb(p, q, t) {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  }

  function hslToRgb(h, s, l) {
    if (s === 0) {
      const v = Math.round(l * 255);
      return [v, v, v];
    }
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    return [
      Math.round(hueToRgb(p, q, h + 1 / 3) * 255),
      Math.round(hueToRgb(p, q, h) * 255),
      Math.round(hueToRgb(p, q, h - 1 / 3) * 255),
    ];
  }

  function wcagContrastRatio(a, b) {
    const f = v => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    const la = 0.2126 * f(a[0]) + 0.7152 * f(a[1]) + 0.0722 * f(a[2]);
    const lb = 0.2126 * f(b[0]) + 0.7152 * f(b[1]) + 0.0722 * f(b[2]);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }

  // 与卡牌侧同解：以默认卡底（--bg-card，亮色主题≈白）为对比基准，
  // 二分出同色相/饱和度下与 0.90 灰达到同等对比度的明度，取差值。
  let defaultBgLumaCache = null;
  function defaultBgLuma() {
    if (defaultBgLumaCache != null) return defaultBgLumaCache;
    let value = 1.0;
    try {
      for (const scope of [document.documentElement, document.body]) {
        if (!scope) continue;
        const rgb = parseColor(getComputedStyle(scope).getPropertyValue('--bg-card'));
        if (rgb) { value = lumaOfRgb(rgb); break; }
      }
    } catch (_) {}
    defaultBgLumaCache = value;
    return value;
  }
  const lightDeltaCache = new Map();
  function lightDeltaFor(baseRgb) {
    const key = baseRgb.slice(0, 3).join(',');
    if (lightDeltaCache.has(key)) return lightDeltaCache.get(key);
    const [h, s] = rgbToHsl(baseRgb);
    const bg = Math.round(defaultBgLuma() * 255);
    const baseline = wcagContrastRatio(baseRgb, [bg, bg, bg]);
    const anchor = Math.round(LIGHT_ANCHOR * 255);
    let lo = 0.06, hi = 0.9;
    for (let i = 0; i < 18; i++) {
      const mid = (lo + hi) / 2;
      if (wcagContrastRatio(hslToRgb(h, s, mid), [anchor, anchor, anchor]) >= baseline) lo = mid;
      else hi = mid;
    }
    const delta = Math.max(0.12, LIGHT_ANCHOR - lo);
    lightDeltaCache.set(key, delta);
    return delta;
  }

  function targetLightness(baseRgb, bgLuma) {
    if (bgLuma == null || !Number.isFinite(bgLuma)) return null;
    const side = bgLuma - 0.5;
    const strength = Math.min(1, Math.abs(side) / NEUTRAL_HALF);
    if (strength <= 0.001) return null; // 中性带：保持原色
    const baseLuma = lumaOfRgb(baseRgb);
    const raw = side >= 0
      ? bgLuma - lightDeltaFor(baseRgb)
      : Math.min(0.9, bgLuma + DARK_CONTRAST);
    const clamped = side >= 0 ? Math.min(baseLuma, raw) : Math.max(baseLuma, raw);
    const [, sat] = rgbToHsl(baseRgb);
    const satScale = (sat > 0.25 && side < 0) ? 0.55 : 1; // 暗底提亮不洗掉识别色
    const target = baseLuma + (clamped - baseLuma) * strength * satScale;
    if (Math.abs(target - baseLuma) < MIN_DELTA) return null;
    // 中性带附近两侧亮度接近时上面的方程几乎不动（灰字压灰底），
    // 补一个可读性下限：与底色对比度不足 MIN_CONTRAST 就继续往远离底色的方向推。
    const [hue, sat2] = rgbToHsl(baseRgb);
    const bgGrey = Math.round(Math.max(0, Math.min(1, bgLuma)) * 255);
    let lightness = Math.max(0.06, Math.min(0.94, target));
    const away = side >= 0 ? -1 : 1;
    for (let step = 0; step < 24; step++) {
      if (wcagContrastRatio(hslToRgb(hue, sat2, lightness), [bgGrey, bgGrey, bgGrey]) >= MIN_CONTRAST) break;
      lightness += away * 0.03;
      if (lightness <= 0.06 || lightness >= 0.94) break;
    }
    return Math.max(0.06, Math.min(0.94, lightness));
  }

  function loadTile(url) {
    if (tileImages.has(url)) return tileImages.get(url);
    const promise = new Promise(resolve => {
      const image = new Image();
      image.decoding = 'async';
      image.onload = () => resolve(image);
      image.onerror = () => resolve(null);
      image.src = url;
    });
    tileImages.set(url, promise);
    return promise;
  }

  function collectTileUrls() {
    const root = backdrop();
    if (!root) return [];
    const urls = new Set();
    root.querySelectorAll('img').forEach(img => { if (img.src) urls.add(img.src); });
    root.querySelectorAll('*').forEach(node => {
      const bg = getComputedStyle(node).backgroundImage || '';
      const m = /url\("?([^")]+)"?\)/.exec(bg);
      if (m) urls.add(m[1]);
    });
    return Array.from(urls);
  }

  function drawCover(image, x, y, w, h) {
    const iw = image.naturalWidth || image.width;
    const ih = image.naturalHeight || image.height;
    if (!iw || !ih) return;
    const ratio = Math.max(w / iw, h / ih);
    const dw = iw * ratio;
    const dh = ih * ratio;
    ctx.drawImage(image, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
  }

  function paintNode(node) {
    try {
      const cs = getComputedStyle(node);
      if (cs.display === 'none' || Number(cs.opacity) === 0) return;
      const rect = node.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) return;
      const x = rect.left * scale;
      const y = rect.top * scale;
      const w = rect.width * scale;
      const h = rect.height * scale;
      ctx.save();
      ctx.globalAlpha = Math.max(0, Math.min(1, Number(cs.opacity) || 1));
      if (node.tagName === 'IMG') {
        const image = tileImages.get(node.src);
        if (image && image.value) drawCover(image.value, x, y, w, h);
      } else {
        const bg = parseColor(cs.backgroundColor);
        if (bg && bg[3] > 0) {
          ctx.fillStyle = `rgba(${bg[0]}, ${bg[1]}, ${bg[2]}, ${bg[3]})`;
          ctx.fillRect(x, y, w, h);
        }
        const m = /url\("?([^")]+)"?\)/.exec(cs.backgroundImage || '');
        if (m) {
          const image = tileImages.get(m[1]);
          if (image && image.value) {
            const pattern = ctx.createPattern(image.value, 'repeat');
            if (pattern) {
              ctx.fillStyle = pattern;
              ctx.fillRect(x, y, w, h);
            }
          }
        }
      }
      ctx.restore();
      for (const child of node.children) paintNode(child);
    } catch (_) {}
  }

  function paintBackdrop() {
    const root = backdrop();
    const vw = Math.max(1, window.innerWidth);
    const vh = Math.max(1, window.innerHeight);
    canvasWidth = Math.max(32, Math.min(SAMPLE_WIDTH, Math.round(vw)));
    scale = canvasWidth / vw;
    canvasHeight = Math.max(1, Math.round(vh * scale));
    if (!canvas) {
      canvas = document.createElement('canvas');
      ctx = canvas.getContext('2d', { willReadFrequently: true });
    }
    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.clearRect(0, 0, canvasWidth, canvasHeight);
    if (root) {
      const bg = parseColor(getComputedStyle(root).backgroundColor);
      if (bg && bg[3] > 0) {
        ctx.fillStyle = `rgba(${bg[0]}, ${bg[1]}, ${bg[2]}, ${bg[3]})`;
        ctx.fillRect(0, 0, canvasWidth, canvasHeight);
      }
      for (const child of root.children) paintNode(child);
    }
    pixels = ctx.getImageData(0, 0, canvasWidth, canvasHeight);
  }

  function sampleLuma(rect) {
    if (!pixels) return null;
    const data = pixels.data;
    const x0 = Math.max(0, Math.floor(rect.left * scale));
    const y0 = Math.max(0, Math.floor(rect.top * scale));
    const x1 = Math.min(canvasWidth, Math.ceil((rect.left + rect.width) * scale));
    const y1 = Math.min(canvasHeight, Math.ceil((rect.top + rect.height) * scale));
    if (x1 <= x0 || y1 <= y0) return null;
    let sum = 0;
    let count = 0;
    for (let y = y0; y < y1; y += 2) {
      for (let x = x0; x < x1; x += 2) {
        const i = (y * canvasWidth + x) * 4;
        const alpha = data[i + 3] / 255;
        if (alpha <= 0.02) continue;
        sum += ((0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]) / 255) * alpha;
        count++;
      }
    }
    return count ? sum / count : null;
  }

  // 只有「文字与主题背景之间没有不透明面板」时才改色：向上找到有
  // 实色底（alpha≥0.5）或背景图的祖先即视为被面板覆盖。
  function coveredByPanel(el) {
    let node = el;
    while (node && node !== document.body && node !== document.documentElement) {
      try {
        const cs = getComputedStyle(node);
        const bg = parseColor(cs.backgroundColor);
        if (bg && bg[3] >= 0.5) return true;
        if (cs.backgroundImage && cs.backgroundImage !== 'none') {
          if (node.id !== 'player-theme-backdrop') return true;
        }
      } catch (_) {}
      node = node.parentElement;
    }
    return false;
  }

  function hasVisibleText(el) {
    for (const child of el.childNodes) {
      if (child.nodeType === 3 && child.nodeValue && child.nodeValue.trim()) return true;
    }
    return false;
  }

  function collectTargets() {
    const roots = Array.from(document.querySelectorAll('#app .view:not(.hidden)'));
    const targets = [];
    const walker = document.createTreeWalker(document.getElementById('app') || document.body, NodeFilter.SHOW_ELEMENT);
    while (walker.nextNode() && targets.length < MAX_TARGETS) {
      const el = walker.currentNode;
      if (!roots.some(root => root.contains(el)) && el.id !== 'app') {
        // 只处理当前可见视图里的节点
        if (!roots.some(root => root === el)) continue;
      }
      if (SKIP_TAGS.has(el.tagName)) continue;
      if (el.closest('#player-theme-backdrop, .card, script, style, .hidden')) continue;
      if (!hasVisibleText(el)) continue;
      try {
        const style = getComputedStyle(el);
        // 渐变字（background-clip:text）由背景图绘制，改 color 反而会盖掉渐变
        if (style.webkitTextFillColor === 'rgba(0, 0, 0, 0)') continue;
        if (style.textFillColor === 'rgba(0, 0, 0, 0)') continue;
      } catch (_) {}
      let rect;
      try { rect = el.getBoundingClientRect(); } catch (_) { continue; }
      if (rect.width < 4 || rect.height < 4) continue;
      if (rect.bottom < -8 || rect.top > window.innerHeight + 8) continue;
      if (coveredByPanel(el)) continue;
      targets.push({ el, rect });
    }
    return targets;
  }

  function baseColorFor(el) {
    const theme = document.documentElement.getAttribute('data-theme') || '';
    if (el.__themeInkBase && el.__themeInkTheme === theme) return el.__themeInkBase;
    if (el.__themeInkApplied) el.style.removeProperty('color');
    const rgb = parseColor(getComputedStyle(el).color);
    if (!rgb) return null;
    el.__themeInkBase = rgb;
    el.__themeInkTheme = theme;
    return rgb;
  }

  function restoreAll() {
    document.querySelectorAll('[data-theme-ink]').forEach(el => {
      try {
        el.style.removeProperty('color');
        el.removeAttribute('data-theme-ink');
      } catch (_) {}
    });
  }

  function applyTo(el, rect) {
    const base = baseColorFor(el);
    if (!base) return;
    const bgLuma = sampleLuma(rect);
    const lightness = targetLightness(base, bgLuma);
    if (lightness == null) {
      el.style.removeProperty('color');
      el.removeAttribute('data-theme-ink');
      return;
    }
    const [h, s] = rgbToHsl(base);
    const rgb = hslToRgb(h, s, lightness);
    el.style.color = `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
    el.setAttribute('data-theme-ink', '1');
    el.__themeInkApplied = true;
  }

  async function refresh() {
    if (running) return;
    running = true;
    try {
      if (!document.body.classList.contains('has-player-theme-background') || !backdrop()) {
        restoreAll();
        return;
      }
      const urls = collectTileUrls();
      await Promise.all(urls.map(url => loadTile(url)));
      paintBackdrop();
      const targets = collectTargets();
      for (const { el, rect } of targets) applyTo(el, rect);
    } catch (_) {
    } finally {
      running = false;
    }
  }

  function schedule(delay = 120) {
    pending = delay;
    if (scheduled) return;
    scheduled = true;
    const run = () => {
      scheduled = false;
      if (pending > 0) {
        pending = 0;
        window.setTimeout(run, 0);
        return;
      }
      refresh();
    };
    window.setTimeout(run, delay);
  }

  function start() {
    if (document.getElementById('story-app')) return;
    const observer = new MutationObserver(() => schedule(160));
    try {
      observer.observe(document.body, { attributes: true, attributeFilter: ['class'], childList: true, subtree: true });
      const app = document.getElementById('app');
      if (app) observer.observe(app, { attributes: true, attributeFilter: ['class'], childList: true, subtree: true });
      const html = document.documentElement;
      observer.observe(html, { attributes: true, attributeFilter: ['data-theme', 'data-ui-style', 'data-home-ui'] });
    } catch (_) {}
    window.addEventListener('resize', () => schedule(260), { passive: true });
    document.addEventListener('gtn:backgrounds-updated', () => schedule(80));
    document.addEventListener('gtn:account-updated', () => schedule(220));
    schedule(60);
  }

  window.GtnThemeInk = Object.freeze({ refresh: () => refresh(), apply: () => schedule(0) });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
