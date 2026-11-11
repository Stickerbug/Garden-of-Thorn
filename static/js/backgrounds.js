/* 玩家主题／战斗背景：账号偏好、独立商店预览与对局视图渲染。 */
(() => {
  'use strict';

  const DEFAULTS = Object.freeze({ theme: 'classic', battle: 'classic' });
  const DEFINITIONS = Object.freeze([
    { kind: 'theme', id: 'classic', name: '经典主题', asset: '', biome: '' },
    { kind: 'theme', id: 'garden', name: '花园', asset: '', biome: 'garden' },
    { kind: 'theme', id: 'desert', name: '沙漠', asset: '', biome: 'desert' },
    { kind: 'theme', id: 'ocean', name: '海洋', asset: '', biome: 'ocean' },
    { kind: 'theme', id: 'jungle', name: '丛林', asset: '', biome: 'jungle' },
    { kind: 'theme', id: 'factory', name: '工厂', asset: '', biome: 'factory' },
    { kind: 'theme', id: 'tower_curse_deepwood', name: '密林', asset: '/static/assets/backgrounds/theme-tower-curse-deepwood.svg', biome: '' },
    { kind: 'theme', id: 'tower_curse_dark_harbor', name: '暗港', asset: '/static/assets/backgrounds/theme-tower-curse-dark-harbor.svg', biome: '' },
    { kind: 'battle', id: 'classic', name: '经典战场', asset: '', biome: '' },
    { kind: 'battle', id: 'garden', name: '花园战场', asset: '', biome: 'garden' },
    { kind: 'battle', id: 'desert', name: '沙漠战场', asset: '', biome: 'desert' },
    { kind: 'battle', id: 'ocean', name: '海洋战场', asset: '', biome: 'ocean' },
    { kind: 'battle', id: 'jungle', name: '丛林战场', asset: '', biome: 'jungle' },
    { kind: 'battle', id: 'factory', name: '工厂战场', asset: '', biome: 'factory' },
  ]);
  const LANDMARKS = Object.freeze({
    desert: Object.freeze([
      { className: 'is-desert-dune', src: '/static/assets/story-backgrounds/desert-dune.svg', rotation: [-30, 30] },
      { className: 'is-desert-stone', src: '/static/assets/story-backgrounds/desert-stone.svg', rotation: [-40, 40] },
    ]),
    garden: Object.freeze([
      { className: 'is-sunflower', src: '/static/assets/story-backgrounds/garden-sunflower.svg', rotation: [-165, 165] },
      { className: 'is-rock', src: '/static/assets/story-backgrounds/garden-rock.svg', rotation: [-165, 165] },
    ]),
    jungle: Object.freeze([
      { className: 'is-jungle-branch', src: '/static/assets/story-backgrounds/jungle-branch.svg', rotation: [-180, 180] },
      { className: 'is-jungle-leaf', src: '/static/assets/story-backgrounds/jungle-leaf.svg', rotation: [-180, 180] },
    ]),
    ocean: Object.freeze([
      { className: 'is-ocean-bubble', src: '/static/assets/story-backgrounds/ocean-bubble.svg', rotation: [-24, 24] },
      { className: 'is-ocean-lily', src: '/static/assets/story-backgrounds/ocean-lily.svg', rotation: [-28, 28] },
    ]),
    factory: Object.freeze([
      { className: 'is-factory-plate', src: '/static/assets/story-backgrounds/factory-plate.svg', rotation: [-180, 180] },
      { className: 'is-factory-gear', src: '/static/assets/story-backgrounds/factory-gear.svg', rotation: [-180, 180] },
    ]),
  });
  const byKey = new Map(DEFINITIONS.map(item => [`${item.kind}:${item.id}`, item]));
  let preferences = { ...DEFAULTS };
  let themeRoot = null;
  let battleRoot = null;
  let observer = null;
  let started = false;

  function definition(kind, id) {
    return byKey.get(`${kind}:${id}`) || byKey.get(`${kind}:${DEFAULTS[kind]}`);
  }
  function visibleView(id) {
    const view = document.getElementById(id);
    return Boolean(view && !view.classList.contains('hidden'));
  }
  function hash(value) {
    let result = 0x811c9dc5;
    const text = String(value || '');
    for (let index = 0; index < text.length; index += 1) {
      result ^= text.charCodeAt(index);
      result = Math.imul(result, 0x01000193);
    }
    return result >>> 0;
  }
  function unit(seed, key) { return hash(`${seed}:${key}`) / 0x100000000; }
  function range(seed, key, minimum, maximum) {
    return minimum + unit(seed, key) * (maximum - minimum);
  }

  function appendBase(container, seed, biome) {
    if (biome === 'garden') return;
    const ranges = { desert: [112, 158], jungle: [142, 192], ocean: [176, 232], factory: [126, 176] };
    const bounds = ranges[biome];
    if (!bounds) return;
    const size = range(seed, 'base:size', bounds[0], bounds[1]);
    const base = document.createElement('span');
    base.className = `story-seeded-backdrop-base is-${biome}`;
    base.style.backgroundSize = `${size.toFixed(2)}px ${size.toFixed(2)}px`;
    base.style.backgroundPosition = `${range(seed, 'base:x', -size, 0).toFixed(2)}px ${range(seed, 'base:y', -size, 0).toFixed(2)}px`;
    container.append(base);
  }
  function appendGardenPatches(container, seed) {
    const fragment = document.createDocumentFragment();
    const columns = 10;
    const rows = 7;
    for (let row = 0; row < rows; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        const key = `patch:${column}:${row}`;
        if (unit(seed, `${key}:present`) > .92) continue;
        const patch = document.createElement('span');
        const dark = unit(seed, `${key}:tone`) < .58;
        patch.className = `story-seeded-backdrop-patch ${dark ? 'is-dark' : 'is-light'}`;
        const left = ((column + range(seed, `${key}:x`, .12, .88)) / columns) * 100;
        const top = ((row + range(seed, `${key}:y`, .12, .88)) / rows) * 100;
        const width = range(seed, `${key}:width`, 3.2, 7.2);
        const height = width * range(seed, `${key}:ratio`, .68, 1.18);
        const rotation = range(seed, `${key}:rotation`, -80, 80);
        patch.style.left = `${left.toFixed(3)}%`;
        patch.style.top = `${top.toFixed(3)}%`;
        patch.style.width = `${width.toFixed(3)}vmin`;
        patch.style.height = `${height.toFixed(3)}vmin`;
        patch.style.transform = `translate(-50%, -50%) rotate(${rotation.toFixed(2)}deg)`;
        fragment.append(patch);
      }
    }
    container.append(fragment);
  }
  function appendDesertPatches(container, seed) {
    const fragment = document.createDocumentFragment();
    const columns = 10;
    const rows = 7;
    for (let row = 0; row < rows; row += 1) {
      for (let column = 0; column < columns; column += 1) {
        const key = `desert:${column}:${row}`;
        if (unit(seed, `${key}:present`) > .9) continue;
        const patch = document.createElement('span');
        const dune = unit(seed, `${key}:kind`) < .68;
        const left = ((column + range(seed, `${key}:x`, .12, .88)) / columns) * 100;
        const top = ((row + range(seed, `${key}:y`, .12, .88)) / rows) * 100;
        const width = range(seed, `${key}:width`, 3.4, 7.8);
        const height = width * range(seed, `${key}:ratio`, .8, 1.2);
        const rotation = range(seed, `${key}:rotation`, -24, 24);
        patch.className = `story-seeded-backdrop-patch ${dune ? 'is-desert-dune' : 'is-desert-stone'}`;
        patch.style.left = `${left.toFixed(3)}%`;
        patch.style.top = `${top.toFixed(3)}%`;
        patch.style.width = `${width.toFixed(3)}vmin`;
        patch.style.height = `${height.toFixed(3)}vmin`;
        patch.style.transform = `translate(-50%, -50%) rotate(${rotation.toFixed(2)}deg)`;
        fragment.append(patch);
      }
    }
    container.append(fragment);
  }
  function appendLandmarks(container, seed, biome) {
    const assets = LANDMARKS[biome] || [];
    const fragment = document.createDocumentFragment();
    for (let row = 0; row < 3; row += 1) {
      for (let column = 0; column < 5; column += 1) {
        const key = `landmark:${column}:${row}`;
        if (unit(seed, `${key}:present`) > .76) continue;
        const asset = assets[Math.min(assets.length - 1, Math.floor(unit(seed, `${key}:kind`) * assets.length))];
        if (!asset) continue;
        const left = ((column + range(seed, `${key}:x`, .18, .82)) / 5) * 100;
        const top = ((row + range(seed, `${key}:y`, .18, .82)) / 3) * 100;
        const size = range(seed, `${key}:size`, 5.5, 9.5);
        const image = document.createElement('img');
        image.className = `story-seeded-backdrop-landmark ${asset.className}`;
        image.src = asset.src;
        image.alt = '';
        image.draggable = false;
        image.style.left = `${left.toFixed(3)}%`;
        image.style.top = `${top.toFixed(3)}%`;
        image.style.width = `clamp(36px, ${size.toFixed(3)}vmin, 96px)`;
        image.style.transform = `translate(-50%, -50%) rotate(${range(seed, `${key}:rotation`, asset.rotation[0], asset.rotation[1]).toFixed(2)}deg)`;
        fragment.append(image);
      }
    }
    container.append(fragment);
  }
  function renderBiome(container, biome, visualSeed) {
    const signature = ['story-backdrop-v3', visualSeed, 1, biome].join(':');
    container.replaceChildren();
    container.dataset.biome = biome;
    appendBase(container, signature, biome);
    // 与故事模式完全一致的三层结构：平铺底纹、群系色块、地标。
    if (biome === 'garden') appendGardenPatches(container, signature);
    if (biome === 'desert') appendDesertPatches(container, signature);
    appendLandmarks(container, signature, biome);
    container.classList.add('is-active');
  }

  function removeTheme() {
    if (themeRoot) themeRoot.remove();
    themeRoot = null;
    document.body.classList.remove('has-player-theme-background');
    delete document.body.dataset.playerThemeBackground;
  }
  function removeBattle() {
    if (battleRoot) battleRoot.remove();
    battleRoot = null;
    delete document.body.dataset.playerBattleBackground;
  }
  function applyTheme() {
    const id = definition('theme', preferences.theme).id;
    if (id === 'classic' || visibleView('view-game') || visibleView('story-app')) {
      removeTheme();
      return;
    }
    const selected = definition('theme', id);
    if (!selected.asset && !selected.biome) { removeTheme(); return; }
    if (!themeRoot) {
      themeRoot = document.createElement('div');
      themeRoot.id = 'player-theme-backdrop';
      themeRoot.setAttribute('aria-hidden', 'true');
      document.body.prepend(themeRoot);
    }
    themeRoot.className = 'player-theme-backdrop';
    themeRoot.dataset.background = id;
    themeRoot.replaceChildren();
    delete themeRoot.dataset.biome;
    if (selected.asset) {
      const image = document.createElement('img');
      image.src = selected.asset;
      image.alt = '';
      image.draggable = false;
      themeRoot.append(image);
    } else {
      themeRoot.classList.add('player-battle-backdrop', 'story-seeded-backdrop');
      renderBiome(themeRoot, selected.biome, id);
    }
    document.body.dataset.playerThemeBackground = id;
    document.body.classList.add('has-player-theme-background');
  }
  function applyBattle() {
    const id = definition('battle', preferences.battle).id;
    const game = document.getElementById('view-game');
    if (id === 'classic' || !game || game.classList.contains('hidden')) {
      removeBattle();
      return;
    }
    const selected = definition('battle', id);
    if (!selected.biome) { removeBattle(); return; }
    if (!battleRoot) {
      battleRoot = document.createElement('div');
      battleRoot.id = 'player-battle-backdrop';
      battleRoot.className = 'player-battle-backdrop story-seeded-backdrop';
      battleRoot.setAttribute('aria-hidden', 'true');
      game.prepend(battleRoot);
    }
    document.body.dataset.playerBattleBackground = id;
    renderBiome(battleRoot, selected.biome, id);
  }
  function applyPreferences(input) {
    preferences = {
      theme: definition('theme', input?.theme).id,
      battle: definition('battle', input?.battle).id,
    };
    applyTheme();
    applyBattle();
    return { ...preferences };
  }
  async function refresh() {
    try {
      const response = await fetch('/api/backgrounds', { credentials: 'same-origin', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.success) applyPreferences(data.preferences);
      else applyPreferences(DEFAULTS);
      return { ...preferences, shops: data.shops || null };
    } catch (_) {
      applyPreferences(DEFAULTS);
      return { ...preferences, shops: null };
    }
  }

  function createPreview(kind, id) {
    const selected = definition(kind, id);
    const root = document.createElement('div');
    root.className = 'background-preview';
    root.dataset.kind = kind;
    root.dataset.background = selected.id;
    if (selected.asset) {
      const image = document.createElement('img');
      image.src = selected.asset;
      image.alt = '';
      image.draggable = false;
      root.append(image);
    } else if (selected.biome) {
      root.classList.add('player-battle-backdrop', 'story-seeded-backdrop');
      renderBiome(root, selected.biome, `preview:${selected.id}`);
    } else {
      root.classList.add('is-classic');
      const label = document.createElement('span');
      label.textContent = '原界面';
      root.append(label);
    }
    return root;
  }

  function start() {
    if (started || document.getElementById('story-app')) return;
    started = true;
    applyPreferences(preferences);
    if (window.MutationObserver) {
      observer = new window.MutationObserver(() => { applyTheme(); applyBattle(); });
      ['view-game', 'story-app'].forEach((id) => {
        const view = document.getElementById(id);
        if (view) observer.observe(view, { attributes: true, attributeFilter: ['class', 'hidden'] });
      });
    }
    document.addEventListener('gtn:account-updated', refresh);
    document.addEventListener('gtn:backgrounds-updated', (event) => {
      if (event.detail?.preferences) applyPreferences(event.detail.preferences);
      else refresh();
    });
    refresh();
  }

  window.GtnBackgrounds = Object.freeze({
    definitions: Object.freeze(DEFINITIONS.map(item => Object.freeze({ ...item }))),
    createPreview,
    applyPreferences,
    refresh,
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
