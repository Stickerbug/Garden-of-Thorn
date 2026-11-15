/* 长期奖励统一展示：只负责表现，奖励是否发放仍由服务端及原业务流程决定。 */
(function () {
  'use strict';

  const ASSETS = Object.freeze({
    dew: '/static/assets/ui-icons/thorn-dew.svg',
    golden_dew: '/static/assets/ui-icons/golden-dew.svg',
    leisure_ticket: '/static/assets/leisure/tickets.svg',
    rank_shield: '/static/assets/rewards/score-insurance-card.svg',
    rank_double: '/static/assets/rewards/double-card.svg',
    pass_xp: '/static/assets/ui-icons/pass-xp.svg',
  });
  const TEXT_ART_KINDS = new Set(['title', 'skin', 'mod', 'character', 'unlock']);
  const ALIASES = Object.freeze({
    dew: 'dew', thorn_dew: 'dew', golden_dew: 'golden_dew', golden: 'golden_dew',
    leisure_ticket: 'leisure_ticket', ticket: 'leisure_ticket',
    rank_shield: 'rank_shield', shield: 'rank_shield',
    rank_double: 'rank_double', double: 'rank_double',
    pass_xp: 'pass_xp', xp: 'pass_xp', exp: 'pass_xp',
    title: 'title', title_unlock: 'title',
    skin: 'skin', card_skin: 'skin',
    mod: 'mod', mod_unlock: 'mod',
    character: 'character', character_unlock: 'character',
    unlock: 'unlock',
  });
  const TEXT = Object.freeze({
    zh: { heading: '获得奖励', dew: '荆露', golden_dew: '金露', leisure_ticket: '休闲门票', rank_shield: '保分卡', rank_double: '双倍卡', pass_xp: '通行证经验', title: '称号', skin: '皮肤', mod: '解锁模组', character: '角色', unlock: '解锁内容', collect: '收下', skip: '跳过动画' },
    en: { heading: 'Reward acquired', dew: 'Thorn Dew', golden_dew: 'Golden Dew', leisure_ticket: 'Leisure Ticket', rank_shield: 'Shield Card', rank_double: 'Double Card', pass_xp: 'Pass XP', title: 'Title', skin: 'Skin', mod: 'Mod unlocked', character: 'Character', unlock: 'Content unlocked', collect: 'Collect', skip: 'Skip animation' },
    fr: { heading: 'Récompense obtenue', dew: 'Rosée d’épines', golden_dew: 'Rosée dorée', leisure_ticket: 'Ticket loisir', rank_shield: 'Carte Bouclier', rank_double: 'Carte Double', pass_xp: 'XP du pass', title: 'Titre', skin: 'Skin', mod: 'Mod déverrouillé', character: 'Personnage', unlock: 'Contenu déverrouillé', collect: 'Récupérer', skip: 'Passer l’animation' },
    ja: { heading: '報酬を獲得', dew: 'ソーンデュー', golden_dew: 'ゴールデンデュー', leisure_ticket: 'レジャーチケット', rank_shield: '保分カード', rank_double: '倍増カード', pass_xp: 'パス経験値', title: '称号', skin: 'スキン', mod: 'Mod解放', character: 'キャラクター', unlock: 'コンテンツ解放', collect: '受け取る', skip: 'アニメーションをスキップ' },
  });
  const PARTICLE_COLORS = ['#9dbb55', '#d18bcf', '#dfa07c', '#b6a4d4'];
  let queue = [];
  let active = null;

  function reducedMotion() {
    if (window.GTNMotion && typeof window.GTNMotion.shouldAnimate === 'function') {
      return !window.GTNMotion.shouldAnimate('continuous');
    }
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function lang() {
    const value = typeof currentLang !== 'undefined' ? currentLang : document.documentElement.lang;
    return TEXT[value] ? value : 'zh';
  }

  // 设置·外观「加快物品获取动画」：勾选后整段演出时长减半（播放速度翻倍）。
  // game.js 把偏好放进 window.GTN_REWARD_ANIM_FAST，直接读存储只是兜底。
  function fastAnimation() {
    if (typeof window !== 'undefined' && window.GTN_REWARD_ANIM_FAST) return true;
    try {
      return window.localStorage.getItem('gtn_fast_reward_animation') === '1';
    } catch (_) {
      return false;
    }
  }

  function scaledDuration(ms) {
    return fastAnimation() ? Math.round(ms / 2) : ms;
  }

  function normalizeItems(input) {
    const list = Array.isArray(input) ? input : [input];
    const output = [];
    list.forEach((raw) => {
      if (!raw || typeof raw !== 'object') return;
      const kind = ALIASES[String(raw.kind || raw.type || '').toLowerCase()];
      if (!kind || (!ASSETS[kind] && !TEXT_ART_KINDS.has(kind))) return;
      const amount = Math.floor(Number(raw.amount ?? 1));
      if (!Number.isFinite(amount) || amount <= 0) return;
      const imageUrl = String(raw.image_url || raw.image || '');
      output.push({
        kind,
        amount: Math.min(amount, 1000000000),
        name: String(raw.name || '').slice(0, 80),
        image_url: imageUrl.startsWith('/static/') || imageUrl.startsWith('data:image/') ? imageUrl : '',
        reason: String(raw.reason || '').slice(0, 160),
      });
    });
    return output;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function charText(text, className, delayStart = 0.5) {
    const root = el('div', className);
    root.setAttribute('aria-label', text);
    Array.from(text).forEach((char, index) => {
      const span = el('span', 'gra-char', char);
      span.setAttribute('aria-hidden', 'true');
      span.style.setProperty('--gra-char-delay', `${scaledDuration((delayStart + index * 0.035) * 1000) / 1000}s`);
      root.appendChild(span);
    });
    return root;
  }

  function clearTimers(session) {
    [session.readyTimer, session.autoTimer, session.closeTimer].forEach((timer) => {
      if (timer) window.clearTimeout(timer);
    });
    session.readyTimer = null;
    session.autoTimer = null;
    session.closeTimer = null;
  }

  function stopParticles(session) {
    if (!session.particles) return;
    window.cancelAnimationFrame(session.particles.frame);
    window.removeEventListener('resize', session.particles.resize);
    session.particles = null;
  }

  function startParticles(session) {
    if (reducedMotion()) return;
    const canvas = session.root.querySelector('.gra-particles');
    const context = canvas && canvas.getContext ? canvas.getContext('2d') : null;
    if (!context) return;
    const particles = Array.from({ length: 38 }, (_, index) => ({
      x: Math.random(),
      y: Math.random(),
      radius: 1.1 + Math.random() * 2.5,
      speedX: (Math.random() - .5) * .000018,
      speedY: -.000008 - Math.random() * .000022,
      phase: Math.random() * Math.PI * 2,
      frequency: .0007 + Math.random() * .0015,
      color: PARTICLE_COLORS[index % PARTICLE_COLORS.length],
      star: index % 6 === 0,
    }));
    const state = { frame: 0, resize: null };
    state.resize = () => {
      const ratio = Math.min(2, Math.max(1, Number(window.devicePixelRatio) || 1));
      canvas.width = Math.max(1, Math.floor(window.innerWidth * ratio));
      canvas.height = Math.max(1, Math.floor(window.innerHeight * ratio));
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    state.resize();
    window.addEventListener('resize', state.resize, { passive: true });
    const drawStar = (x, y, radius) => {
      context.beginPath();
      context.moveTo(x, y - radius * 2.2);
      context.lineTo(x + radius * .55, y - radius * .55);
      context.lineTo(x + radius * 2.2, y);
      context.lineTo(x + radius * .55, y + radius * .55);
      context.lineTo(x, y + radius * 2.2);
      context.lineTo(x - radius * .55, y + radius * .55);
      context.lineTo(x - radius * 2.2, y);
      context.lineTo(x - radius * .55, y - radius * .55);
      context.closePath();
      context.fill();
    };
    const frame = (timestamp) => {
      if (active !== session || session.closing) return;
      context.clearRect(0, 0, window.innerWidth, window.innerHeight);
      particles.forEach((particle) => {
        particle.x = (particle.x + particle.speedX * 16 + 1) % 1;
        particle.y = (particle.y + particle.speedY * 16 + 1) % 1;
        const alpha = .18 + .72 * Math.abs(Math.sin(particle.phase + timestamp * particle.frequency));
        context.globalAlpha = Math.min(.92, alpha);
        context.fillStyle = particle.color;
        const x = particle.x * window.innerWidth;
        const y = particle.y * window.innerHeight;
        if (particle.star) drawStar(x, y, particle.radius);
        else {
          context.beginPath();
          context.arc(x, y, particle.radius, 0, Math.PI * 2);
          context.fill();
        }
      });
      context.globalAlpha = 1;
      state.frame = window.requestAnimationFrame(frame);
    };
    session.particles = state;
    state.frame = window.requestAnimationFrame(frame);
  }

  function close(session, discardQueue = false) {
    if (!session || session.closing) return;
    session.closing = true;
    clearTimers(session);
    stopParticles(session);
    if (discardQueue) queue = [];
    document.removeEventListener('keydown', session.onKeydown);
    session.root.classList.add('is-leaving');
    const finish = () => {
      session.root.remove();
      session.resolve();
      if (active === session) active = null;
      // 在关闭过程中新到的奖励不会复用旧舞台，直接开启下一场。
      if (active === null && queue.length) show(queue.splice(0));
    };
    session.closeTimer = window.setTimeout(finish, reducedMotion() ? 0 : scaledDuration(460));
  }

  function next(session) {
    if (active !== session || session.closing) return;
    clearTimers(session);
    if (!queue.length) {
      close(session);
      return;
    }
    const item = queue.shift();
    session.current = item;
    const copy = TEXT[lang()];
    const stage = session.root.querySelector('.gra-stage');
    stage.replaceChildren();
    const kicker = el('div', 'gra-kicker', copy.heading);
    stage.appendChild(kicker);
    const artWrap = el('div', 'gra-art-wrap');
    const itemName = item.name || copy[item.kind];
    const imageUrl = item.image_url || ASSETS[item.kind] || '';
    if (imageUrl) {
      const image = el('img', 'gra-art');
      image.src = imageUrl;
      image.alt = itemName;
      image.style.setProperty('--gra-tilt', `${(-4 + Math.random() * 8).toFixed(2)}deg`);
      artWrap.appendChild(image);
    } else {
      // 没有贴图的长期奖励使用名称本身作为视觉主体。
      artWrap.appendChild(charText(itemName, 'gra-text-art', .22));
    }
    stage.appendChild(artWrap);
    const amountText = ['title', 'skin'].includes(item.kind)
      ? '获得'
      : (['mod', 'character', 'unlock'].includes(item.kind) ? '解锁' : `+${item.amount.toLocaleString()}`);
    stage.appendChild(charText(amountText, 'gra-amount', .55));
    stage.appendChild(charText(itemName, 'gra-name', .72));
    if (item.reason) stage.appendChild(charText(item.reason, 'gra-reason', .88));
    const collect = el('button', 'gra-collect', copy.collect);
    collect.type = 'button';
    collect.addEventListener('click', () => next(session));
    stage.appendChild(collect);
    const counter = el('div', 'gra-progress', `${session.index + 1} / ${session.total}`);
    session.index += 1;
    stage.appendChild(counter);
    const reveal = () => {
      if (active !== session || session.closing) return;
      collect.classList.add('is-ready');
      collect.focus({ preventScroll: true });
    };
    session.readyTimer = window.setTimeout(reveal, reducedMotion() ? 40 : scaledDuration(1450));
    if (session.auto) session.autoTimer = window.setTimeout(() => next(session), reducedMotion() ? 1800 : scaledDuration(3400));
  }

  function show(input, options = {}) {
    const items = normalizeItems(input);
    if (!items.length) return Promise.resolve();
    if (active && !active.closing) {
      active.total += items.length;
      queue.push(...items);
      return active.promise;
    }
    queue = items;
    const root = el('div', 'gra-overlay');
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', TEXT[lang()].heading);
    if (fastAnimation()) root.classList.add('is-fast');
    root.appendChild(el('canvas', 'gra-particles'));
    ['one', 'two', 'three'].forEach((name) => root.appendChild(el('div', `gra-wipe gra-wipe-${name}`)));
    const skip = el('button', 'gra-skip', TEXT[lang()].skip);
    skip.type = 'button';
    root.appendChild(skip);
    root.appendChild(el('div', 'gra-stage'));
    let resolvePromise;
    const session = {
      root,
      promise: new Promise((resolve) => { resolvePromise = resolve; }),
      resolve: resolvePromise,
      auto: options.auto !== false,
      current: null,
      closing: false,
      readyTimer: null,
      autoTimer: null,
      closeTimer: null,
      particles: null,
      onKeydown: null,
      index: 0,
      total: items.length,
    };
    active = session;
    skip.addEventListener('click', () => close(session, true));
    session.onKeydown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close(session, true);
      }
    };
    document.addEventListener('keydown', session.onKeydown);
    document.body.appendChild(root);
    startParticles(session);
    next(session);
    return session.promise;
  }

  const watch = {
    userId: null,
    cursor: null,
    xpCursor: null,
    leisureTickets: 0,
    rankCards: { shield: 0, double: 0 },
    inventory: { titles: [], skins: [], mods: [], characters: [] },
    inFlight: false,
    started: false,
  };

  function rewardItemsFromSnapshot(data, previous) {
    if (!data || !data.success || previous.userId !== String(data.user_id) || previous.cursor === null) return [];
    const items = [];
    (Array.isArray(data.golden_dew_rewards) ? data.golden_dew_rewards : []).forEach((reward) => {
      const id = Number(reward.id || 0);
      const amount = Math.floor(Number(reward.amount || 0));
      if (id > previous.cursor && amount > 0) {
        items.push({ kind: 'golden_dew', amount, reason: String(reward.reason || '') });
      }
    });
    (Array.isArray(data.dew_rewards) ? data.dew_rewards : []).forEach((reward) => {
      // 对局结算的荆露不再播动画；签到、成就、等其他来源照常。
      if (String(reward.source_type || '') === 'match_reward') return;
      const id = Number(reward.id || 0);
      const amount = Math.floor(Number(reward.amount || 0));
      if (id > previous.cursor && amount > 0) {
        items.push({ kind: 'dew', amount, reason: String(reward.reason || '') });
      }
    });
    const ticketDelta = Math.max(0, Number(data.leisure_tickets || 0) - previous.leisureTickets);
    if (ticketDelta > 0) items.push({ kind: 'leisure_ticket', amount: ticketDelta, reason: '休闲门票到账' });
    (Array.isArray(data.xp_rewards) ? data.xp_rewards : []).forEach((reward) => {
      // 对局经验不播动画（结算面板已有「通行证经验 +N」）；爬塔、签到、管理调整照常。
      if (String(reward.source_type || '') === 'match') return;
      const id = Number(reward.id || 0);
      const amount = Math.floor(Number(reward.amount || 0));
      if (previous.xpCursor !== null && id > previous.xpCursor && amount > 0) {
        items.push({ kind: 'pass_xp', amount, reason: String(reward.reason || '') });
      }
    });
    ['shield', 'double'].forEach((kind) => {
      const owned = Number((data.rank_cards && data.rank_cards[kind] && (Number(data.rank_cards[kind].owned || 0) + (data.rank_cards[kind].armed ? 1 : 0))) || 0);
      const delta = Math.max(0, owned - Number(previous.rankCards[kind] || 0));
      if (delta > 0) items.push({ kind: `rank_${kind}`, amount: delta, reason: '段位卡到账' });
    });
    const inventory = data.inventory || {};
    const kinds = {
      titles: ['title', '称号到账'],
      skins: ['skin', '皮肤到账'],
      mods: ['mod', '模组解锁'],
      characters: ['character', '角色解锁'],
    };
    Object.entries(kinds).forEach(([inventoryKey, [kind, reason]]) => {
      const previousIds = new Set((previous.inventory && previous.inventory[inventoryKey]) || []);
      const entries = Array.isArray(inventory[inventoryKey]) ? inventory[inventoryKey] : [];
      entries.forEach((entry) => {
        const id = String((entry && entry.id) || '');
        if (!id || previousIds.has(id)) return;
        items.push({
          kind,
          amount: 1,
          name: String(entry.name || id),
          image_url: String(entry.image_url || ''),
          reason,
        });
      });
    });
    return items;
  }

  function resetWatch() {
    watch.userId = null;
    watch.cursor = null;
    watch.xpCursor = null;
    watch.leisureTickets = 0;
    watch.rankCards = { shield: 0, double: 0 };
    watch.inventory = { titles: [], skins: [], mods: [], characters: [] };
  }

  async function refresh() {
    if (watch.inFlight) return;
    watch.inFlight = true;
    try {
      const suffix = watch.cursor === null
        ? ''
        : `?after=${encodeURIComponent(watch.cursor)}&xp_after=${encodeURIComponent(watch.xpCursor || 0)}`;
      const response = await fetch(`/api/rewards/status${suffix}`, {
        credentials: 'same-origin',
        cache: 'no-store',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.success) {
        if (response.status === 401) resetWatch();
        return;
      }
      const items = rewardItemsFromSnapshot(data, watch);
      watch.userId = String(data.user_id);
      watch.cursor = Math.max(0, Number(data.dew_cursor) || 0);
      watch.xpCursor = Math.max(0, Number(data.xp_cursor) || 0);
      watch.leisureTickets = Math.max(0, Number(data.leisure_tickets) || 0);
      ['shield', 'double'].forEach((kind) => {
        watch.rankCards[kind] = Math.max(0, Number(
          (data.rank_cards && data.rank_cards[kind] && (Number(data.rank_cards[kind].owned || 0) + (data.rank_cards[kind].armed ? 1 : 0))) || 0,
        ));
      });
      const inventory = data.inventory || {};
      Object.keys(watch.inventory).forEach((key) => {
        const entries = Array.isArray(inventory[key]) ? inventory[key] : [];
        watch.inventory[key] = entries.map(entry => String((entry && entry.id) || '')).filter(Boolean);
      });
      if (items.length) show(items);
    } catch (_) {
      // 网络或登录状态变化时保留游标，下次恢复后继续，不重复播放。
    } finally {
      watch.inFlight = false;
    }
  }

  function startWatch() {
    if (watch.started || window.__GTN_DISABLE_REWARD_WATCH__) return;
    watch.started = true;
    window.setInterval(refresh, 4000);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refresh();
    });
    refresh();
  }

  window.GtnRewardAnimation = Object.freeze({
    show,
    normalizeItems,
    rewardItemsFromSnapshot,
    refresh,
    startWatch,
  });
  startWatch();
})();
