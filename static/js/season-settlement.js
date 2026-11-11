/* 赛季结算三页回顾：数据只读，已读状态按账号与赛季保存在本机。 */
(function () {
  'use strict';

  const STORAGE_PREFIX = 'gtn-season-settlement-seen-v1';
  const sessionSeen = new Set();
  let active = null;
  let inFlight = false;

  const TEXT = Object.freeze({
    zh: {
      settlement: '赛季结算', review: '赛季回顾', rank: '段位变化', rewards: '赛季奖励',
      winRate: '赛季胜率', games: '天梯对局', wins: '胜利', losses: '失败', draws: '平局',
      participations: '各模式参与次数', gamesUnit: '局', before: '结算前', after: '结算后',
      points: '段内分', absolute: '总段位分', subtiersDown: '下降 {0} 个小段',
      subtiersUp: '上升 {0} 个小段', sameTier: '段位保持不变', seasonGames: '本赛季天梯 {0} 局',
      base: '基础赛季奖励', advanced: '进阶赛季奖励', threshold: '{0} 局天梯解锁',
      unlocked: '已获得', locked: '未获得', remaining: '还差 {0} 局', dew: '荆露',
      baseFormula: '5000 + 总段位分 × 10 荆露', allGranted: '达到条件的奖励已随赛季结算发放',
      noRewards: '本赛季未达到奖励条件', next: '下一页', back: '上一页', finish: '收下赛季回顾',
      skip: '跳过', modes: { '1v1': '单人对决', '2v2': '双人对决', unknown: '其他模式' },
    },
    en: {
      settlement: 'Season Settlement', review: 'Season Review', rank: 'Rank Change', rewards: 'Season Rewards',
      winRate: 'Season Win Rate', games: 'Ranked Games', wins: 'Wins', losses: 'Losses', draws: 'Draws',
      participations: 'Games by Mode', gamesUnit: 'games', before: 'Before', after: 'After',
      points: 'Tier Points', absolute: 'Total Rank Points', subtiersDown: 'Down {0} subtiers',
      subtiersUp: 'Up {0} subtiers', sameTier: 'Rank unchanged', seasonGames: '{0} ranked games this season',
      base: 'Base Season Reward', advanced: 'Advanced Season Reward', threshold: 'Unlock at {0} ranked games',
      unlocked: 'Earned', locked: 'Not earned', remaining: '{0} games short', dew: 'Thorn Dew',
      baseFormula: '5000 + total rank points × 10 Thorn Dew', allGranted: 'Eligible rewards were granted with settlement',
      noRewards: 'No season reward requirements met', next: 'Next', back: 'Back', finish: 'Finish Season Review',
      skip: 'Skip', modes: { '1v1': '1v1 Duel', '2v2': '2v2 Team', unknown: 'Other' },
    },
    fr: {
      settlement: 'Bilan de saison', review: 'Revue de saison', rank: 'Changement de rang', rewards: 'Récompenses',
      winRate: 'Taux de victoire', games: 'Parties classées', wins: 'Victoires', losses: 'Défaites', draws: 'Nuls',
      participations: 'Parties par mode', gamesUnit: 'parties', before: 'Avant', after: 'Après',
      points: 'Points du rang', absolute: 'Points de rang totaux', subtiersDown: '{0} sous-rangs perdus',
      subtiersUp: '{0} sous-rangs gagnés', sameTier: 'Rang inchangé', seasonGames: '{0} parties classées cette saison',
      base: 'Récompense de base', advanced: 'Récompense avancée', threshold: 'Déblocage à {0} parties',
      unlocked: 'Obtenue', locked: 'Non obtenue', remaining: 'Encore {0} parties', dew: 'Rosée d’épines',
      baseFormula: '5000 + points de rang totaux × 10 Rosée', allGranted: 'Les récompenses éligibles ont été distribuées',
      noRewards: 'Aucune condition de récompense remplie', next: 'Suivant', back: 'Retour', finish: 'Terminer le bilan',
      skip: 'Passer', modes: { '1v1': 'Duel 1v1', '2v2': 'Équipe 2v2', unknown: 'Autre' },
    },
    ja: {
      settlement: 'シーズン精算', review: 'シーズン振り返り', rank: 'ランク変化', rewards: 'シーズン報酬',
      winRate: 'シーズン勝率', games: 'ランク戦', wins: '勝利', losses: '敗北', draws: '引分',
      participations: 'モード別参加回数', gamesUnit: '戦', before: '精算前', after: '精算後',
      points: 'ランク内ポイント', absolute: '総ランクポイント', subtiersDown: '{0} 小ランク下降',
      subtiersUp: '{0} 小ランク上昇', sameTier: 'ランク変化なし', seasonGames: '今シーズンのランク戦 {0} 戦',
      base: '基础シーズン報酬', advanced: '上級シーズン報酬', threshold: 'ランク戦 {0} 戦で解放',
      unlocked: '獲得済み', locked: '未獲得', remaining: 'あと {0} 戦', dew: 'ソーンデュー',
      baseFormula: '5000 + 総ランクポイント × 10 ソーンデュー', allGranted: '条件を満たした報酬は精算時に付与されました',
      noRewards: '報酬条件を達成していません', next: '次へ', back: '戻る', finish: '振り返りを完了',
      skip: 'スキップ', modes: { '1v1': '1v1 デュエル', '2v2': '2v2 チーム', unknown: 'その他' },
    },
  });

  function lang() {
    const value = typeof currentLang !== 'undefined' ? currentLang : document.documentElement.lang;
    return TEXT[value] ? value : 'zh';
  }

  function copy() { return TEXT[lang()]; }
  function format(template, value) { return String(template).replace('{0}', String(value)); }
  function integer(value) { return Math.max(0, Math.floor(Number(value) || 0)); }
  function signed(value) { const n = Math.floor(Number(value) || 0); return n > 0 ? `+${n}` : String(n); }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function storageKey(data) {
    const userId = String((data && data.user_id) || 'anonymous');
    const month = String((data && data.month_key) || 'unknown');
    return `${STORAGE_PREFIX}:${userId}:${month}`;
  }

  function normalizeSettlement(input) {
    if (!input || typeof input !== 'object' || !input.month_key || !input.before || !input.after) return null;
    const data = Object.assign({}, input);
    data.user_id = String(input.user_id || '');
    data.season_name = String(input.season_name || 'S3').slice(0, 30);
    data.stats = Object.assign({ games: 0, wins: 0, losses: 0, draws: 0, win_rate: 0, modes: {} }, input.stats || {});
    data.stats.modes = Object.assign({ '1v1': { games: 0 }, '2v2': { games: 0 } }, input.stats && input.stats.modes || {});
    return data;
  }

  function isSeen(data) {
    const key = storageKey(data);
    if (sessionSeen.has(key)) return true;
    try { return window.localStorage.getItem(key) === '1'; } catch (_) { return false; }
  }

  function markSeen(data) {
    const key = storageKey(data);
    sessionSeen.add(key);
    try { window.localStorage.setItem(key, '1'); } catch (_) {}
  }

  function rankBadge(rank) {
    const holder = el('div', 'ssr-rank-badge');
    if (typeof window.renderRankBadgeHtml === 'function') {
      holder.innerHTML = window.renderRankBadgeHtml(rank, { showPoints: true });
    } else {
      holder.textContent = `${String(rank.label || rank.tier || '-')} ${integer(rank.points)}/${integer(rank.cap)}`;
    }
    return holder;
  }

  function header(data, title, page) {
    const fragment = document.createDocumentFragment();
    fragment.appendChild(el('div', 'ssr-kicker', `${data.season_name} · ${copy().settlement}`));
    fragment.appendChild(el('h1', 'ssr-title', title));
    fragment.appendChild(el('div', 'ssr-page-label', `0${page} / 03`));
    return fragment;
  }

  function statCell(label, value, className = '') {
    const cell = el('div', `ssr-stat-cell ${className}`.trim());
    cell.appendChild(el('strong', '', value));
    cell.appendChild(el('span', '', label));
    return cell;
  }

  function renderReview(session) {
    const data = session.data;
    const stats = data.stats;
    const t = copy();
    const page = el('section', 'ssr-page ssr-review-page');
    page.appendChild(header(data, t.review, 1));
    const hero = el('div', 'ssr-win-hero');
    const ring = el('div', 'ssr-win-ring');
    ring.style.setProperty('--ssr-win-rate', `${Math.max(0, Math.min(100, Number(stats.win_rate) || 0)) * 3.6}deg`);
    const ringValue = el('div', 'ssr-win-ring-value');
    ringValue.appendChild(el('strong', '', `${Number(stats.win_rate) || 0}%`));
    ringValue.appendChild(el('span', '', t.winRate));
    ring.appendChild(ringValue);
    hero.appendChild(ring);
    const grid = el('div', 'ssr-stats-grid');
    grid.appendChild(statCell(t.games, integer(stats.games)));
    grid.appendChild(statCell(t.wins, integer(stats.wins), 'is-win'));
    grid.appendChild(statCell(t.losses, integer(stats.losses), 'is-loss'));
    grid.appendChild(statCell(t.draws, integer(stats.draws), 'is-draw'));
    hero.appendChild(grid);
    page.appendChild(hero);
    page.appendChild(el('h2', 'ssr-section-title', t.participations));
    const modes = el('div', 'ssr-mode-list');
    const entries = Object.entries(stats.modes || {}).sort(([a], [b]) => {
      const order = { '1v1': 0, '2v2': 1 };
      return (order[a] ?? 2) - (order[b] ?? 2) || a.localeCompare(b);
    });
    entries.forEach(([mode, values]) => {
      const row = el('div', 'ssr-mode-row');
      const name = el('div', 'ssr-mode-name');
      name.appendChild(el('span', 'ssr-mode-glyph', mode === '2v2' ? '2×2' : (mode === '1v1' ? '1×1' : '·')));
      name.appendChild(el('strong', '', t.modes[mode] || mode));
      row.appendChild(name);
      row.appendChild(el('span', 'ssr-mode-record', `${integer(values.wins)} / ${integer(values.losses)} / ${integer(values.draws)}`));
      row.appendChild(el('strong', 'ssr-mode-games', `${integer(values.games)} ${t.gamesUnit}`));
      modes.appendChild(row);
    });
    page.appendChild(modes);
    return page;
  }

  function renderRank(session) {
    const data = session.data;
    const t = copy();
    const before = data.before;
    const after = data.after;
    const changes = data.changes || {};
    const page = el('section', 'ssr-page ssr-rank-page');
    page.appendChild(header(data, t.rank, 2));
    const ranks = el('div', 'ssr-rank-comparison');
    const beforePanel = el('div', 'ssr-rank-panel is-before');
    beforePanel.appendChild(el('span', 'ssr-panel-label', t.before));
    beforePanel.appendChild(rankBadge(before));
    ranks.appendChild(beforePanel);
    ranks.appendChild(el('div', 'ssr-rank-arrow', '→'));
    const afterPanel = el('div', 'ssr-rank-panel is-after');
    afterPanel.appendChild(el('span', 'ssr-panel-label', t.after));
    afterPanel.appendChild(rankBadge(after));
    ranks.appendChild(afterPanel);
    page.appendChild(ranks);
    const tierDelta = Math.floor(Number(changes.subtiers) || 0);
    const tierText = tierDelta < 0 ? format(t.subtiersDown, Math.abs(tierDelta))
      : (tierDelta > 0 ? format(t.subtiersUp, tierDelta) : t.sameTier);
    page.appendChild(el('div', 'ssr-tier-change', tierText));
    const points = el('div', 'ssr-points-change');
    points.appendChild(el('span', 'ssr-points-label', t.points));
    const values = el('div', 'ssr-points-values');
    values.appendChild(el('strong', 'is-before', integer(before.points)));
    values.appendChild(el('span', '', '→'));
    values.appendChild(el('strong', 'is-after', integer(after.points)));
    points.appendChild(values);
    page.appendChild(points);
    const absolute = el('div', 'ssr-absolute-change');
    absolute.appendChild(el('span', '', `${t.absolute} ${integer(before.absolute_points)} → ${integer(after.absolute_points)}`));
    absolute.appendChild(el('strong', Number(changes.absolute_points) <= 0 ? 'is-loss' : 'is-win', signed(changes.absolute_points)));
    page.appendChild(absolute);
    return page;
  }

  function rewardCard(kind, reward, data) {
    const t = copy();
    const earned = !!reward.earned;
    const card = el('article', `ssr-reward-card is-${kind} ${earned ? 'is-earned' : 'is-locked'}`);
    const top = el('div', 'ssr-reward-top');
    const heading = el('div', 'ssr-reward-heading');
    heading.appendChild(el('span', 'ssr-reward-icon', kind === 'base' ? 'Ⅰ' : 'Ⅱ'));
    heading.appendChild(el('h2', '', kind === 'base' ? t.base : t.advanced));
    top.appendChild(heading);
    top.appendChild(el('span', 'ssr-reward-status', earned ? t.unlocked : t.locked));
    card.appendChild(top);
    card.appendChild(el('div', 'ssr-reward-threshold', format(t.threshold, integer(reward.required_games))));
    const items = el('div', 'ssr-reward-items');
    const dew = el('div', 'ssr-reward-dew');
    const image = el('img', 'ssr-dew-icon');
    image.src = '/static/assets/ui-icons/thorn-dew.svg';
    image.alt = '';
    dew.appendChild(image);
    const dewAmount = earned ? `+${integer(reward.dew).toLocaleString()}` : (kind === 'base' ? t.baseFormula : `+${integer(reward.dew || 5000).toLocaleString()}`);
    dew.appendChild(el('strong', '', dewAmount));
    if (kind === 'base' && earned) dew.appendChild(el('span', '', t.dew));
    items.appendChild(dew);
    if (kind === 'advanced') items.appendChild(el('div', 'ssr-reward-title', `「${String(reward.title || `${data.season_name}赛季参与者`)}」`));
    card.appendChild(items);
    if (!earned) card.appendChild(el('div', 'ssr-reward-remaining', format(t.remaining, integer(reward.remaining_games))));
    return card;
  }

  function renderRewards(session) {
    const data = session.data;
    const rewards = data.rewards || {};
    const t = copy();
    const page = el('section', 'ssr-page ssr-rewards-page');
    page.appendChild(header(data, t.rewards, 3));
    const games = data.before.season_ranked_games == null
      ? integer(data.stats.games) : integer(data.before.season_ranked_games);
    page.appendChild(el('div', 'ssr-season-games', format(t.seasonGames, games)));
    const list = el('div', 'ssr-reward-list');
    list.appendChild(rewardCard('base', rewards.base || {}, data));
    list.appendChild(rewardCard('advanced', rewards.advanced || {}, data));
    page.appendChild(list);
    const anyEarned = !!((rewards.base && rewards.base.earned) || (rewards.advanced && rewards.advanced.earned));
    page.appendChild(el('p', 'ssr-reward-note', anyEarned ? t.allGranted : t.noRewards));
    return page;
  }

  function render(session) {
    const t = copy();
    const body = session.root.querySelector('.ssr-body');
    body.classList.remove('is-switching');
    body.replaceChildren();
    const page = session.page === 0 ? renderReview(session) : (session.page === 1 ? renderRank(session) : renderRewards(session));
    body.appendChild(page);
    session.switching = false;
    session.back.disabled = session.page === 0;
    session.back.classList.toggle('is-hidden', session.page === 0);
    session.next.textContent = session.page === 2 ? t.finish : t.next;
    session.dots.forEach((dot, index) => {
      dot.classList.toggle('is-active', index === session.page);
      dot.setAttribute('aria-current', index === session.page ? 'page' : 'false');
    });
  }

  function close(session) {
    if (!session || session.closing) return;
    session.closing = true;
    window.clearTimeout(session.switchTimer);
    markSeen(session.data);
    document.removeEventListener('keydown', session.onKeydown);
    session.root.classList.add('is-leaving');
    const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.setTimeout(() => {
      session.root.remove();
      if (active === session) active = null;
      session.resolve();
    }, reduced ? 0 : 300);
  }

  function navigate(session, delta) {
    if (session.closing || session.switching) return;
    if (session.page === 2 && delta > 0) {
      close(session);
      return;
    }
    const nextPage = Math.max(0, Math.min(2, session.page + delta));
    if (nextPage === session.page) return;
    const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      session.page = nextPage;
      render(session);
      return;
    }
    session.switching = true;
    session.root.querySelector('.ssr-body').classList.add('is-switching');
    session.switchTimer = window.setTimeout(() => {
      session.page = nextPage;
      render(session);
    }, 300);
  }

  function show(input, options = {}) {
    const data = normalizeSettlement(input);
    if (!data) return Promise.resolve(false);
    if (!options.force && isSeen(data)) return Promise.resolve(false);
    if (active) return active.promise;
    const t = copy();
    const root = el('div', 'ssr-overlay');
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-label', `${data.season_name} ${t.settlement}`);
    root.appendChild(el('div', 'ssr-wipe ssr-wipe-one'));
    root.appendChild(el('div', 'ssr-wipe ssr-wipe-two'));
    root.appendChild(el('div', 'ssr-ambient ssr-ambient-one'));
    root.appendChild(el('div', 'ssr-ambient ssr-ambient-two'));
    const skip = el('button', 'ssr-skip', t.skip);
    skip.type = 'button';
    root.appendChild(skip);
    const shell = el('div', 'ssr-shell');
    const body = el('div', 'ssr-body');
    shell.appendChild(body);
    const footer = el('div', 'ssr-footer');
    const back = el('button', 'ssr-nav ssr-back', t.back);
    back.type = 'button';
    const dots = el('div', 'ssr-dots');
    const dotList = [];
    for (let index = 0; index < 3; index += 1) {
      const dot = el('span', 'ssr-dot');
      dot.setAttribute('aria-hidden', 'true');
      dots.appendChild(dot);
      dotList.push(dot);
    }
    const next = el('button', 'ssr-nav ssr-next', t.next);
    next.type = 'button';
    footer.appendChild(back);
    footer.appendChild(dots);
    footer.appendChild(next);
    shell.appendChild(footer);
    root.appendChild(shell);
    let resolvePromise;
    const session = {
      root, data, page: 0, back, next, dots: dotList, closing: false, onKeydown: null,
      promise: new Promise((resolve) => { resolvePromise = resolve; }), resolve: resolvePromise,
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

  async function refresh() {
    if (inFlight || window.__GTN_DISABLE_SEASON_SETTLEMENT__) return false;
    inFlight = true;
    try {
      const response = await fetch('/api/rank/season-settlement', { credentials: 'same-origin', cache: 'no-store' });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success || !payload.settlement) return false;
      const data = Object.assign({ user_id: String(payload.user_id || '') }, payload.settlement);
      if (data.animation_seen_at) {
        markSeen(data);
        return false;
      }
      // 服务端先原子认领，成功才播放；本地缓存不再决定自动触发次数。
      const claimResponse = await fetch('/api/rank/season-settlement/seen', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ month_key: data.month_key }),
      });
      const claim = await claimResponse.json().catch(() => ({}));
      if (!claimResponse.ok || !claim.success || !claim.claimed) {
        markSeen(data);
        return false;
      }
      await show(data, { force: true });
      return true;
    } catch (_) {
      return false;
    } finally {
      inFlight = false;
    }
  }

  window.GtnSeasonSettlement = Object.freeze({ show, refresh, normalizeSettlement, storageKey });
  window.setTimeout(refresh, 1200);
})();
