/* 单人故事通关三页结算：分数逐项累计 → 实际路线 → 最终牌组。 */
(function () {
  'use strict';

  const ITEM_ORDER = ['stages', 'all_stages_bonus', 'normal_battles', 'elite_battles', 'gold', 'cards', 'relics', 'enchantment_books'];
  const LABELS = {
    stages: '完成阶段', all_stages_bonus: '全阶段通关奖励', normal_battles: '普通战斗', elite_battles: '精英战斗',
    gold: '剩余金币', cards: '最终卡组', relics: '遗物', enchantment_books: '附魔书',
  };
  let active = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }
  function integer(value) { return Math.max(0, Math.floor(Number(value) || 0)); }
  function multiplier(value) {
    const number = Number(value);
    return Number.isFinite(number) ? String(Math.round(number * 100) / 100) : '1';
  }
  function signed(value) {
    const number = Math.floor(Number(value) || 0);
    return number > 0 ? `+${number}` : String(number);
  }
  function reducedMotion() {
    return Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
      || Boolean(window.GTNMotion?.isLowPerformance?.());
  }
  function normalizeSettlement(input) {
    const data = input && typeof input === 'object' ? input : null;
    const settlement = data?.settlement;
    const score = settlement?.score;
    if (!data?.summary?.run_id || !settlement || !score?.items || !Number.isFinite(Number(score.base_score))) return null;
    return {
      summary: data.summary,
      deck: Array.isArray(data.deck) ? data.deck : [],
      relics: Array.isArray(data.relics) ? data.relics : [],
      maps: Array.isArray(data.maps) ? data.maps : [],
      map: data.map || { floors: [], edges: [] },
      route: data.route || { visited: [] },
      settlement,
    };
  }
  function renderer(session, key) {
    return session.renderers[key] || null;
  }
  function summaryMeta(data, session) {
    const summary = data.summary;
    const character = renderer(session, 'characterName')?.(summary.character_id) || summary.character_id || '普通的花花';
    const difficulty = renderer(session, 'difficultyLabel')?.(summary.difficulty) || summary.difficulty || '普通';
    const duration = renderer(session, 'duration')?.(summary.duration_seconds) || `${integer(summary.duration_seconds)}s`;
    return `${character} · ${difficulty} · ${summary.stage_reached || 1}幕${summary.floor_reached || 1}层 · H ${integer(summary.health)}/${integer(summary.max_health)} · G ${integer(summary.gold)} · ${duration}`;
  }
  function pageHeader(data, title, index) {
    const fragment = document.createDocumentFragment();
    fragment.appendChild(el('div', 'scs-kicker', '旅程结算 · 通关'));
    fragment.appendChild(el('h1', 'scs-title', title));
    fragment.appendChild(el('div', 'scs-page-count', `0${index} / 03`));
    return fragment;
  }
  function scoreFormula(key, item) {
    const count = integer(item.count);
    const unit = integer(item.unit);
    if (key === 'gold') return `${count} G ÷ ${unit}`;
    return `${count} × ${unit}`;
  }
  function renderScore(session) {
    const data = session.data;
    const score = data.settlement.score;
    const page = el('section', 'scs-page scs-score-page');
    page.appendChild(pageHeader(data, '通关分数', 1));
    const layout = el('div', 'scs-score-layout');
    const total = el('div', 'scs-total-block');
    const finalScore = integer(score.total_score);
    total.appendChild(el('span', 'scs-total-label', '通关得分'));
    const totalValue = el('strong', 'scs-total-value', '0');
    totalValue.setAttribute('aria-label', String(finalScore));
    total.appendChild(totalValue);
    total.appendChild(el('span', 'scs-total-note', `基础分 ${integer(score.base_score)} · 难度与 SL 倍率已计入`));
    layout.appendChild(total);
    const ledger = el('div', 'scs-score-ledger');
    const rows = [];
    ITEM_ORDER.forEach((key) => {
      const item = score.items[key] || { count: 0, unit: 0, points: 0 };
      const row = el('div', 'scs-ledger-row');
      row.appendChild(el('span', 'scs-ledger-name', LABELS[key]));
      const formula = el('span', 'scs-ledger-formula', scoreFormula(key, item));
      row.appendChild(formula);
      row.appendChild(el('strong', 'scs-ledger-points', `+${integer(item.points)}`));
      ledger.appendChild(row);
      rows.push(row);
    });
    layout.appendChild(ledger);
    page.appendChild(layout);
    const multipliers = el('div', 'scs-multipliers');
    multipliers.appendChild(el('span', '', `基础分 ${integer(score.base_score)}`));
    multipliers.appendChild(el('span', '', `难度倍率 ×${multiplier(score.difficulty_multiplier)}`));
    multipliers.appendChild(el('span', '', `SL 倍率 ×${multiplier(score.sl_multiplier)}`));
    multipliers.appendChild(el('strong', '', `通关得分 ${finalScore}`));
    page.appendChild(multipliers);
    const dew = el('section', 'scs-dew-result');
    const dewTop = el('div', 'scs-dew-heading');
    const icon = el('img', 'scs-dew-icon');
    icon.src = '/static/assets/ui-icons/thorn-dew.svg';
    icon.alt = '';
    dewTop.appendChild(icon);
    dewTop.appendChild(el('span', '', '荆露收益'));
    const dewAwarded = integer(data.settlement.dew_awarded);
    dewTop.appendChild(el('strong', 'scs-dew-amount', `+${dewAwarded.toLocaleString()}`));
    dew.appendChild(dewTop);
    const globalDewMultiplier = Number(data.settlement.dew_gain_multiplier);
    const globalDew = Number.isFinite(globalDewMultiplier) ? globalDewMultiplier : 1;
    const dewProduct = finalScore * globalDew;
    const actualSuffix = (!Number.isInteger(dewProduct) || dewAwarded !== Math.round(dewProduct))
      ? `，实际发放 ${dewAwarded}` : '';
    dew.appendChild(el('div', 'scs-dew-formula',
      `${finalScore} × 全局荆露收益乘数 ${globalDew} = ${multiplier(dewProduct)}${actualSuffix}`
    ));
    if (data.settlement.dev_used) dew.appendChild(el('div', 'scs-dew-adjustment', '本局使用过开发模式，不发荆露'));
    if (!data.settlement.recorded) dew.appendChild(el('div', 'scs-dew-adjustment', '本局没有荆露结算台账'));
    page.appendChild(dew);
    const golden = el('section', 'scs-golden-result');
    const goldenTop = el('div', 'scs-dew-heading');
    const goldenIcon = el('img', 'scs-dew-icon');
    goldenIcon.src = '/static/assets/ui-icons/golden-dew.svg';
    goldenIcon.alt = '';
    goldenTop.appendChild(goldenIcon);
    goldenTop.appendChild(el('span', '', '金露奖励'));
    goldenTop.appendChild(el('strong', 'scs-dew-amount', `+${integer(data.settlement.golden_dew_reward).toLocaleString()}`));
    golden.appendChild(goldenTop);
    const stages = integer(data.settlement.completed_stages);
    const difficulty = multiplier(score.difficulty_multiplier);
    const difficultyKey = String(data.summary.difficulty || 'normal').toLowerCase();
    const noSl = multiplier(Number(score.sl_multiplier) === 1.5 ? 1.5 : 1);
    golden.appendChild(el('div', 'scs-dew-formula',
      `${stages}x${difficulty}（${difficultyKey}）x${noSl}（sl）=${integer(data.settlement.golden_dew_reward)}`
    ));
    if (data.settlement.dev_used) golden.appendChild(el('div', 'scs-dew-adjustment', '本局使用过开发模式，不发金露'));
    page.appendChild(golden);
    // 通行证经验（2026-11-11）：Min{1000, ceil(分数/5)}，赛季内每周前 3 次通关 ×3。
    const xpGain = integer(data.settlement.xp_gain);
    let xp = null;
    if (xpGain > 0) {
      xp = el('section', 'scs-dew-result scs-xp-result');
      const xpTop = el('div', 'scs-dew-heading');
      const xpIcon = el('img', 'scs-dew-icon');
      xpIcon.src = '/static/assets/ui-icons/pass-xp.svg';
      xpIcon.alt = '';
      xpTop.appendChild(xpIcon);
      xpTop.appendChild(el('span', '', '通行证经验'));
      xpTop.appendChild(el('strong', 'scs-dew-amount', `+${xpGain.toLocaleString()}`));
      xp.appendChild(xpTop);
      xp.appendChild(el('div', 'scs-dew-formula', '分数/5 通行证经验（最多 1000）'));
      page.appendChild(xp);
    }
    return { page, rows, totalValue, dew, xp };
  }
  function fallbackMap(svg, map) {
    const ns = 'http://www.w3.org/2000/svg';
    const nodes = new Map();
    (map.floors || []).forEach((floor, floorIndex) => {
      (floor.nodes || []).forEach((node, nodeIndex) => {
        const x = Number(node.x) || (120 + nodeIndex * 130);
        const y = Number(node.y) || (90 + floorIndex * 120);
        nodes.set(String(node.id), { node, x, y });
      });
    });
    (map.edges || []).forEach((edge) => {
      const from = nodes.get(String(edge.from));
      const to = nodes.get(String(edge.to));
      if (!from || !to) return;
      const line = document.createElementNS(ns, 'line');
      line.setAttribute('x1', from.x); line.setAttribute('y1', from.y);
      line.setAttribute('x2', to.x); line.setAttribute('y2', to.y);
      line.setAttribute('class', 'scs-map-edge');
      svg.appendChild(line);
    });
    nodes.forEach(({ node, x, y }) => {
      const group = document.createElementNS(ns, 'g');
      const circle = document.createElementNS(ns, 'circle');
      circle.setAttribute('cx', x); circle.setAttribute('cy', y); circle.setAttribute('r', 13);
      circle.setAttribute('class', `scs-map-node is-${node.type || 'unknown'}${node.status === 'completed' ? ' is-complete' : ''}`);
      const label = document.createElementNS(ns, 'text');
      label.setAttribute('x', x); label.setAttribute('y', y + 4);
      label.setAttribute('class', 'scs-map-label');
      label.textContent = node.status === 'completed' ? '✓' : ({ combat: '战', elite: '精', boss: '首', rest: '休', shop: '商', chest: '宝', event: '事' })[node.type] || '·';
      group.append(circle, label);
      svg.appendChild(group);
    });
  }
  function renderRoute(session) {
    const data = session.data;
    const page = el('section', 'scs-page scs-route-page');
    page.appendChild(pageHeader(data, '通关路线', 2));
    page.appendChild(el('p', 'scs-summary', summaryMeta(data, session)));
    const visited = Array.isArray(data.route?.visited) ? data.route.visited : [];
    const stageCount = new Set(visited.map(node => node.stage || 1)).size;
    page.appendChild(el('div', 'scs-route-stats', `${visited.length} 个节点 · ${Math.max(1, stageCount)} 个阶段`));
    const mapStack = el('div', 'scs-map-stack');
    const maps = data.maps.length ? data.maps : [{ stage: data.summary.stage_reached || 1, map: data.map }];
    maps.forEach((section, index) => {
      const stage = section.stage || index + 1;
      mapStack.appendChild(el('h2', 'scs-map-stage', `第 ${stage} 幕`));
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 760 1040');
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      svg.classList.add('scs-route-map');
      mapStack.appendChild(svg);
      const map = section.map || { floors: [], edges: [] };
      const render = renderer(session, 'renderMap');
      if (render) render(map, section.map?.current_node_id || '', { readOnly: true, target: svg });
      else fallbackMap(svg, map);
    });
    page.appendChild(mapStack);
    return { page, rows: [], totalValue: null, dew: null };
  }
  function fallbackCard(card) {
    const article = el('article', 'story-card card is-compact scs-fallback-card');
    article.appendChild(el('strong', '', card.def_id || '?'));
    article.appendChild(el('span', '', card.upgraded ? '已升级' : '未升级'));
    return article;
  }
  function renderDeck(session) {
    const data = session.data;
    const page = el('section', 'scs-page scs-deck-page');
    page.appendChild(pageHeader(data, '最终牌组', 3));
    page.appendChild(el('p', 'scs-summary', `${data.deck.length} 张卡牌 · 通关时的最终构筑`));
    const grid = el('div', 'scs-deck-grid');
    const create = renderer(session, 'createStoryCard');
    data.deck.forEach((card, index) => {
      const item = create ? create({
        def_id: card.def_id,
        instance_id: `settlement-${index}-${card.def_id}`,
        upgraded: card.upgraded,
        modifiers: card.modifiers || {},
      }, { interactive: false, compact: true }) : fallbackCard(card);
      item.classList.add('scs-deck-card');
      item.style.setProperty('--scs-card-index', Math.min(index, 16));
      grid.appendChild(item);
    });
    page.appendChild(grid);
    return { page, rows: [], totalValue: null, dew: null };
  }
  function cleanupAnimation(session) {
    (session.timers || []).forEach(timer => window.clearTimeout(timer));
    session.timers = [];
    if (session.raf) cancelAnimationFrame(session.raf);
    session.raf = 0;
  }
  function revealScore(session, view) {
    cleanupAnimation(session);
    const score = session.data.settlement.score;
    const finalScore = integer(score.total_score);
    const finish = () => {
      view.totalValue.textContent = finalScore.toLocaleString();
      view.dew.classList.add('is-visible');
      if (view.xp) view.xp.classList.add('is-visible');
    };
    if (reducedMotion()) {
      view.rows.forEach(row => row.classList.add('is-visible'));
      finish();
      return;
    }
    view.rows.forEach((row, index) => {
      session.timers.push(window.setTimeout(() => row.classList.add('is-visible'), 100 + index * 115));
    });
    session.timers.push(window.setTimeout(() => {
      const started = performance.now();
      const duration = 520;
      const tick = (now) => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        view.totalValue.textContent = Math.round(finalScore * eased).toLocaleString();
        if (progress < 1) session.raf = requestAnimationFrame(tick);
        else finish();
      };
      session.raf = requestAnimationFrame(tick);
    }, 180 + view.rows.length * 115));
  }
  function render(session) {
    cleanupAnimation(session);
    const body = session.root.querySelector('.scs-body');
    body.classList.remove('is-switching');
    body.replaceChildren();
    const view = session.page === 0 ? renderScore(session) : (session.page === 1 ? renderRoute(session) : renderDeck(session));
    body.appendChild(view.page);
    session.back.classList.toggle('is-hidden', session.page === 0);
    session.next.textContent = session.page === 2 ? '收下旅程回顾' : '下一页';
    session.dots.forEach((dot, index) => dot.classList.toggle('is-active', index === session.page));
    session.root.querySelectorAll('.scs-rail-step').forEach((step, index) => {
      step.classList.toggle('is-active', index === session.page);
      step.classList.toggle('is-complete', index < session.page);
    });
    if (session.page === 0) revealScore(session, view);
  }
  function close(session) {
    if (!session || session.closing) return;
    session.closing = true;
    cleanupAnimation(session);
    document.removeEventListener('keydown', session.onKeydown);
    session.root.classList.add('is-leaving');
    window.setTimeout(() => {
      session.root.remove();
      if (active === session) active = null;
      session.resolve(true);
    }, reducedMotion() ? 0 : 260);
  }
  function navigate(session, delta) {
    if (session.closing || session.switching) return;
    if (session.page === 2 && delta > 0) { close(session); return; }
    const next = Math.max(0, Math.min(2, session.page + delta));
    if (next === session.page) return;
    session.switching = true;
    session.root.querySelector('.scs-body').classList.add('is-switching');
    session.timers.push(window.setTimeout(() => {
      session.page = next;
      session.switching = false;
      render(session);
    }, reducedMotion() ? 0 : 220));
  }
  function show(input, options = {}) {
    const data = normalizeSettlement(input);
    if (!data) return Promise.resolve(false);
    if (active) return active.promise;
    const root = el('div', 'scs-overlay');
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', '通关旅程结算');
    root.appendChild(el('div', 'scs-wipe scs-wipe-one'));
    root.appendChild(el('div', 'scs-wipe scs-wipe-two'));
    const skip = el('button', 'scs-skip', '跳过');
    skip.type = 'button';
    root.appendChild(skip);
    const shell = el('div', 'scs-shell');
    const rail = el('div', 'scs-rail');
    ['分数', '路线', '牌组'].forEach((label, index) => {
      const step = el('div', 'scs-rail-step');
      step.appendChild(el('strong', '', `0${index + 1}`));
      step.appendChild(el('span', '', label));
      rail.appendChild(step);
    });
    shell.appendChild(rail);
    const body = el('div', 'scs-body');
    shell.appendChild(body);
    const footer = el('div', 'scs-footer');
    const back = el('button', 'scs-nav scs-back is-hidden', '上一页');
    back.type = 'button';
    const dots = el('div', 'scs-dots');
    const dotList = [];
    for (let index = 0; index < 3; index += 1) {
      const dot = el('span', 'scs-dot');
      dots.appendChild(dot);
      dotList.push(dot);
    }
    const next = el('button', 'scs-nav scs-next', '下一页');
    next.type = 'button';
    footer.append(back, dots, next);
    shell.appendChild(footer);
    root.appendChild(shell);
    let resolvePromise;
    const session = {
      root, data, page: 0, back, next, dots: dotList, closing: false, switching: false,
      timers: [], raf: 0, onKeydown: null,
      renderers: Object.assign({}, window.GtnStoryClearSettlementRenderers || {}, options.renderers || {}),
      promise: new Promise(resolve => { resolvePromise = resolve; }), resolve: resolvePromise,
    };
    skip.addEventListener('click', () => close(session));
    back.addEventListener('click', () => navigate(session, -1));
    next.addEventListener('click', () => navigate(session, 1));
    session.onKeydown = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); close(session); }
      if (event.key === 'ArrowRight') navigate(session, 1);
      if (event.key === 'ArrowLeft') navigate(session, -1);
    };
    document.addEventListener('keydown', session.onKeydown);
    document.body.appendChild(root);
    active = session;
    render(session);
    window.setTimeout(() => next.focus({ preventScroll: true }), 80);
    return session.promise;
  }

  window.GtnStoryClearSettlement = Object.freeze({ show, normalizeSettlement });
})();
