(() => {
  'use strict';

  const state = {
    feed: null,
    csrfToken: '',
    loadPromise: null,
    votePromise: null,
    chainPromise: null,
    epoch: 0,
  };
  const ANNOUNCEMENT_READ_KEY = 'gtn_community_announcement_reads_v1';
  const ANNOUNCEMENT_READ_COOKIE = 'gtn_community_reads_v1';
  const announcementReadMemory = new Set();
  const serverReadAnnouncementIds = new Set();
  const serverReadPollIds = new Set();
  const serverReadChainIds = new Set();
  let serverReadRequest = null;

  const byId = (id) => document.getElementById(id);

  function announcementStorageKey() {
    if (typeof window.gtnBetaStorageKey === 'function') {
      return String(window.gtnBetaStorageKey(ANNOUNCEMENT_READ_KEY));
    }
    return ANNOUNCEMENT_READ_KEY;
  }

  function announcementReceipt(item) {
    const id = Number(item?.id || 0);
    if (!Number.isInteger(id) || id <= 0) return '';
    const publishedAt = String(item?.published_at || item?.starts_at || '');
    return `${id}:${publishedAt}`;
  }

  function pollReceipt(item) {
    const id = Number(item?.id || 0);
    if (!Number.isInteger(id) || id <= 0) return '';
    const publishedAt = String(item?.published_at || item?.starts_at || '');
    return `poll:${id}:${publishedAt}`;
  }

  function chainReceipt(item) {
    const id = Number(item?.id || 0);
    if (!Number.isInteger(id) || id <= 0) return '';
    const publishedAt = String(item?.published_at || item?.starts_at || '');
    return `chain:${id}:${publishedAt}`;
  }

  function readAnnouncementReceipts() {
    const receipts = new Set(announcementReadMemory);
    const key = announcementStorageKey();
    ['localStorage', 'sessionStorage'].forEach((name) => {
      try {
        const storage = window[name];
        const values = JSON.parse(storage.getItem(key) || '[]');
        if (Array.isArray(values)) values.forEach((value) => receipts.add(String(value || '')));
      } catch (_) {}
    });
    try {
      const cookieValue = document.cookie
        .split(';')
        .map((part) => part.trim())
        .find((part) => part.startsWith(`${ANNOUNCEMENT_READ_COOKIE}=`));
      if (cookieValue) {
        const values = JSON.parse(decodeURIComponent(cookieValue.slice(ANNOUNCEMENT_READ_COOKIE.length + 1)) || '[]');
        if (Array.isArray(values)) values.forEach((value) => receipts.add(String(value || '')));
      }
    } catch (_) {}
    receipts.delete('');
    return receipts;
  }

  function writeAnnouncementReceipts(receipts) {
    const values = Array.from(receipts).filter(Boolean).slice(-120);
    announcementReadMemory.clear();
    values.forEach((value) => announcementReadMemory.add(value));
    const serialized = JSON.stringify(values);
    const key = announcementStorageKey();
    ['localStorage', 'sessionStorage'].forEach((name) => {
      try { window[name].setItem(key, serialized); } catch (_) {}
    });
    try {
      document.cookie = `${ANNOUNCEMENT_READ_COOKIE}=${encodeURIComponent(serialized)}; path=/; max-age=15552000; SameSite=Lax`;
    } catch (_) {}
  }

  function currentFeedItems() {
    const polls = Array.isArray(state.feed?.polls) ? state.feed.polls : [];
    const chains = Array.isArray(state.feed?.chains) ? state.feed.chains : [];
    return [
      ...polls.map((item) => ({ type: 'polls', receipt: pollReceipt(item), id: Number(item?.id || 0) })),
      ...chains.map((item) => ({ type: 'chains', receipt: chainReceipt(item), id: Number(item?.id || 0) })),
    ].filter((item) => item.receipt && item.id > 0);
  }

  function serverReadIds(type) {
    if (type === 'polls') return serverReadPollIds;
    if (type === 'chains') return serverReadChainIds;
    return serverReadAnnouncementIds;
  }

  function applyServerRead(payload) {
    const read = payload?.viewer?.read;
    serverReadAnnouncementIds.clear();
    serverReadPollIds.clear();
    serverReadChainIds.clear();
    if (!read) return;
    (Array.isArray(read.announcements) ? read.announcements : [])
      .forEach((value) => serverReadAnnouncementIds.add(Number(value)));
    (Array.isArray(read.polls) ? read.polls : [])
      .forEach((value) => serverReadPollIds.add(Number(value)));
    (Array.isArray(read.chains) ? read.chains : [])
      .forEach((value) => serverReadChainIds.add(Number(value)));
  }

  function updateAnnouncementBadge() {
    // 2026-11-25：投票并入公告面板，独立入口按钮已移除；社区未读改成
    // 公告按钮上的一个小圆点（数字角标仍由 game.js 的更新日志徽标负责，
    // 两者共用同一个按钮但写入不同 class，避免互相覆盖）。
    const button = byId('btn-changelog-top');
    if (!button) return;
    const read = readAnnouncementReceipts();
    const hasUnread = currentFeedItems().some((item) => (
      !read.has(item.receipt) && !serverReadIds(item.type).has(item.id)
    ));
    button.classList.toggle('has-community-unread', hasUnread);
  }

  async function markCommunityItemsRead() {
    const authenticated = Boolean(state.feed?.viewer?.authenticated);
    const csrf = state.csrfToken;
    if (authenticated && csrf) {
      if (serverReadRequest) return serverReadRequest;
      serverReadRequest = requestJson('/api/community/read', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Community-CSRF': csrf,
        },
        body: JSON.stringify({ types: ['poll', 'chain'] }),
      })
        .then((payload) => {
          applyServerRead(payload);
          updateAnnouncementBadge();
        })
        .catch(() => {})
        .finally(() => { serverReadRequest = null; });
      return serverReadRequest;
    }
    const receipts = readAnnouncementReceipts();
    currentFeedItems().forEach((item) => receipts.add(item.receipt));
    writeAnnouncementReceipts(receipts);
    updateAnnouncementBadge();
    return null;
  }

  function isCommunityPopoverOpen() {
    // 合并后社区内容寄生在公告面板里，面板开合由 game.js 的 toggleChangelogPopover 负责。
    const popover = byId('changelog-popover');
    return Boolean(popover && !popover.classList.contains('hidden'));
  }

  function setStatus(message, kind = '') {
    const node = byId('community-status');
    if (!node) return;
    node.textContent = String(message || '');
    node.className = `community-status ${kind ? `is-${kind}` : 'muted'}`;
  }

  function formatTime(value) {
    const date = new Date(String(value || ''));
    if (Number.isNaN(date.getTime())) return String(value || '');
    try {
      return new Intl.DateTimeFormat(document.documentElement.lang || 'zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date);
    } catch (_) {
      return String(value || '');
    }
  }

  function createElement(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function renderAnnouncement(item) {
    const article = createElement('article', 'community-card community-announcement');
    const heading = createElement('div', 'community-card-heading');
    const title = createElement('h3', '', item.title || '公告');
    heading.appendChild(title);
    if (item.pinned) heading.appendChild(createElement('span', 'community-badge is-pinned', '置顶'));
    article.appendChild(heading);
    article.appendChild(createElement('p', 'community-card-body', item.body || ''));
    article.appendChild(createElement('div', 'community-card-meta', `发布于 ${formatTime(item.starts_at)}`));
    return article;
  }

  function renderPoll(item) {
    const article = createElement('article', 'community-card community-poll');
    const heading = createElement('div', 'community-card-heading');
    heading.appendChild(createElement('h3', '', item.question || '投票'));
    if (item.pinned) heading.appendChild(createElement('span', 'community-badge is-pinned', '置顶'));
    if (item.reminder_due) heading.appendChild(createElement('span', 'community-badge is-reminder', '即将截止'));
    if (item.effective_state === 'closed') heading.appendChild(createElement('span', 'community-badge', '已结束'));
    article.appendChild(heading);

    const options = createElement('div', 'community-poll-options');
    const totalVotes = Number(item.total_votes || 0);
    (Array.isArray(item.options) ? item.options : []).forEach((option) => {
      const selected = Number(item.selected_option_id) === Number(option.id);
      const button = createElement('button', `community-poll-option${selected ? ' is-selected' : ''}`);
      button.type = 'button';
      button.dataset.pollId = String(item.id);
      button.dataset.optionId = String(option.id);
      const label = createElement('span', 'community-option-label', option.label || '');
      button.appendChild(label);
      if (item.effective_state === 'closed') {
        const count = Number(option.vote_count || 0);
        const percent = totalVotes > 0 ? Math.round((count / totalVotes) * 100) : 0;
        button.appendChild(createElement('span', 'community-option-count', `${count}票 · ${percent}%`));
        button.disabled = true;
      } else if (selected) {
        button.appendChild(createElement('span', 'community-option-count', '已选择'));
        button.disabled = true;
      } else {
        button.disabled = !item.can_vote || Boolean(state.votePromise);
      }
      // GB-213：投票到达截止时间后按钮要立即失效，不等玩家手动刷新
      if (item.effective_state === 'active' && item.ends_at) {
        const endsMs = Date.parse(item.ends_at);
        if (Number.isFinite(endsMs)) {
          const timeout = setTimeout(() => {
            clearTimeout(timeout);
            if (state.epoch !== epoch) return;
            renderFeed();
          }, Math.max(0, endsMs - Date.now() + 500));
        }
      }
      options.appendChild(button);
    });
    article.appendChild(options);

    let footer = `截止 ${formatTime(item.ends_at)}`;
    if (item.effective_state === 'closed') footer += ` · 共 ${totalVotes} 票`;
    else if (!state.feed?.viewer?.authenticated) footer += ' · 登录后可投票';
    else if (item.selected_option_id) footer += ' · 投票后不可改票';
    article.appendChild(createElement('div', 'community-card-meta', footer));
    return article;
  }

  function renderChain(item) {
    const article = createElement('article', 'community-card community-chain');
    const heading = createElement('div', 'community-card-heading');
    heading.appendChild(createElement('h3', '', item.title || '接龙'));
    if (item.effective_state === 'closed') heading.appendChild(createElement('span', 'community-badge', '已结束'));
    else if (item.effective_state === 'scheduled') heading.appendChild(createElement('span', 'community-badge', '未开始'));
    article.appendChild(heading);
    article.appendChild(createElement('p', 'community-card-body', item.description || ''));

    const entries = createElement('ol', 'community-chain-entries');
    (Array.isArray(item.entries) ? item.entries : []).forEach((entry) => {
      const line = createElement('li', '');
      line.appendChild(createElement('b', '', `${entry.nickname || '已注销玩家'}：`));
      line.appendChild(document.createTextNode(entry.content || ''));
      entries.appendChild(line);
    });
    article.appendChild(entries);

    let footer = `共 ${Number(item.entry_count || 0)} 人接龙`;
    const viewer = state.feed?.viewer;
    if (item.can_join) {
      const joinRow = createElement('div', 'community-chain-join');
      const input = createElement('input', 'community-chain-input');
      input.type = 'text';
      input.maxLength = 500;
      input.placeholder = item.my_entry ? '修改我的接龙内容' : '写一条接龙内容';
      if (item.my_entry) input.value = item.my_entry;
      const button = createElement('button', 'community-poll-option', item.my_entry ? '更新' : '接龙');
      button.type = 'button';
      button.dataset.chainId = String(item.id);
      button.dataset.chainJoin = 'true';
      button.disabled = Boolean(state.chainPromise);
      joinRow.append(input, button);
      article.appendChild(joinRow);
    } else if (!viewer?.authenticated) {
      footer += ' · 登录后可接龙';
    }
    article.appendChild(createElement('div', 'community-card-meta', footer));
    return article;
  }

  function announcementAccordion(node, meta) {
    const details = createElement('details', 'ann-item');
    details.dataset.source = 'community';
    details.dataset.kind = meta.kind;
    details.dataset.key = `${meta.kind}:${meta.id}`;
    details.dataset.time = String(meta.time || '');
    if (meta.pinned) details.dataset.pinned = '1';
    const summary = createElement('summary', 'ann-summary');
    if (meta.pinned) summary.appendChild(createElement('span', 'ann-pin', '置顶'));
    summary.appendChild(createElement('span', 'ann-title', meta.title));
    if (meta.note) summary.appendChild(createElement('span', 'ann-meta', meta.note));
    details.appendChild(summary);
    const body = createElement('div', 'ann-body');
    const heading = node.querySelector('.community-card-heading');
    if (heading) heading.remove();
    body.appendChild(node);
    details.appendChild(body);
    return details;
  }

  function pollNote(item) {
    if (item.effective_state === 'closed') return '已结束';
    if (item.effective_state === 'scheduled') return '未开始';
    const ends = item.ends_at ? formatTime(item.ends_at) : '';
    if (item.reminder_due) return ends ? `即将截止 · ${ends}` : '即将截止';
    return ends ? `截止 ${ends}` : '';
  }

  function renderFeed() {
    const list = byId('ann-list');
    if (!list) return;
    // 重新渲染（投票、刷新）时保留玩家已经展开的条目。
    const openKeys = new Set(
      Array.from(list.querySelectorAll(':scope > details.ann-item[data-source="community"][open]'))
        .map((node) => node.dataset.key),
    );
    list.querySelectorAll(':scope > details.ann-item[data-source="community"]').forEach((node) => node.remove());

    const polls = Array.isArray(state.feed?.polls) ? state.feed.polls : [];
    const chains = Array.isArray(state.feed?.chains) ? state.feed.chains : [];
    polls.forEach((item) => {
      list.appendChild(announcementAccordion(renderPoll(item), {
        kind: 'poll',
        id: item.id,
        title: item.question || '投票',
        note: pollNote(item),
        time: item.starts_at || item.published_at || '',
        pinned: item.pinned,
      }));
    });
    chains.forEach((item) => {
      list.appendChild(announcementAccordion(renderChain(item), {
        kind: 'chain',
        id: item.id,
        title: item.title || '接龙',
        note: `${Number(item.entry_count || 0)} 人接龙`,
        time: item.starts_at || item.published_at || '',
        pinned: item.pinned,
      }));
    });

    if (openKeys.size) {
      list.querySelectorAll(':scope > details.ann-item[data-source="community"]').forEach((node) => {
        if (openKeys.has(node.dataset.key)) node.open = true;
      });
    }

    const sorter = window.GtnAnnouncementList;
    if (sorter && typeof sorter.sort === 'function') sorter.sort();

    const manage = byId('community-manage-link');
    if (manage) manage.classList.toggle('hidden', !state.feed?.viewer?.can_manage);
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      credentials: 'same-origin',
      cache: 'no-store',
      ...options,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (_) {
      payload = {};
    }
    if (!response.ok || !payload?.success) {
      const error = new Error(String(payload?.error || `请求失败（${response.status}）`));
      error.status = response.status;
      error.code = payload?.code || '';
      throw error;
    }
    return payload;
  }

  async function loadFeed({ silent = false } = {}) {
    if (state.loadPromise) return state.loadPromise;
    const epoch = state.epoch;
    if (!silent) setStatus('正在加载…');
    const promise = requestJson('/api/community/feed')
      .then((payload) => {
        if (epoch !== state.epoch) return;
        state.feed = payload;
        state.csrfToken = String(payload.csrf_token || '');
        applyServerRead(payload);
        renderFeed();
        updateAnnouncementBadge();
        if (isCommunityPopoverOpen()) markCommunityItemsRead();
        if (!silent) setStatus('');
      })
      .catch((error) => {
        if (epoch !== state.epoch) return;
        if (!silent) setStatus(error.message || '公告加载失败', 'error');
      })
      .finally(() => {
        if (state.loadPromise === promise) state.loadPromise = null;
      });
    state.loadPromise = promise;
    return promise;
  }

  async function vote(pollId, optionId) {
    if (state.votePromise) return;
    if (!state.csrfToken) {
      setStatus('请先登录账号再投票。', 'error');
      return;
    }
    renderFeed();
    setStatus('正在提交投票…');
    const epoch = state.epoch;
    const promise = requestJson(`/api/community/polls/${encodeURIComponent(pollId)}/vote`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Community-CSRF': state.csrfToken,
      },
      body: JSON.stringify({ option_id: Number(optionId) }),
    })
      .then((payload) => {
        if (epoch !== state.epoch) return;
        const polls = Array.isArray(state.feed?.polls) ? state.feed.polls : [];
        const index = polls.findIndex((item) => Number(item.id) === Number(payload.poll?.id));
        if (index >= 0) polls.splice(index, 1, payload.poll);
        renderFeed();
        setStatus(payload.duplicate ? '该选择此前已提交。' : '投票已提交，选择不可更改。', 'success');
      })
      .catch((error) => {
        if (epoch !== state.epoch) return;
        setStatus(error.message || '投票提交失败', 'error');
      })
      .finally(() => {
        if (state.votePromise === promise) state.votePromise = null;
        if (epoch === state.epoch) renderFeed();
      });
    state.votePromise = promise;
    renderFeed();
    await promise;
  }

  async function joinChain(chainId, content) {
    if (state.chainPromise) return;
    const value = String(content || '').trim();
    if (!value) {
      setStatus('请先写一条接龙内容。', 'error');
      return;
    }
    if (!state.csrfToken) {
      setStatus('请先登录账号再参与接龙。', 'error');
      return;
    }
    renderFeed();
    setStatus('正在提交接龙…');
    const epoch = state.epoch;
    const promise = requestJson(`/api/community/chains/${encodeURIComponent(chainId)}/join`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Community-CSRF': state.csrfToken,
      },
      body: JSON.stringify({ content: value }),
    })
      .then((payload) => {
        if (epoch !== state.epoch) return;
        const chains = Array.isArray(state.feed?.chains) ? state.feed.chains : [];
        const index = chains.findIndex((item) => Number(item.id) === Number(payload.chain?.id));
        if (index >= 0) chains.splice(index, 1, payload.chain);
        renderFeed();
        setStatus(payload.duplicate ? '已更新你的接龙内容。' : '接龙成功。', 'success');
      })
      .catch((error) => {
        if (epoch !== state.epoch) return;
        setStatus(error.message || '接龙提交失败', 'error');
      })
      .finally(() => {
        if (state.chainPromise === promise) state.chainPromise = null;
        if (epoch === state.epoch) renderFeed();
      });
    state.chainPromise = promise;
    renderFeed();
    await promise;
  }

  function closePopover() {
    if (!isCommunityPopoverOpen()) return;
    if (typeof window.toggleChangelogPopover === 'function') window.toggleChangelogPopover(false);
    else byId('changelog-popover')?.classList.add('hidden');
    state.epoch += 1;
  }

  function openPopover() {
    if (typeof window.toggleChangelogPopover === 'function') window.toggleChangelogPopover(true);
    else byId('changelog-popover')?.classList.remove('hidden');
    state.epoch += 1;
    loadFeed();
  }

  function togglePopover() {
    if (isCommunityPopoverOpen()) closePopover();
    else openPopover();
  }

  document.addEventListener('DOMContentLoaded', () => {
    byId('btn-community-refresh')?.addEventListener('click', () => loadFeed());
    byId('ann-list')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-poll-id][data-option-id]');
      if (!button || button.disabled) return;
      vote(button.dataset.pollId, button.dataset.optionId);
    });
    byId('ann-list')?.addEventListener('click', (event) => {
      const button = event.target.closest('[data-chain-id][data-chain-join]');
      if (!button || button.disabled) return;
      const article = button.closest('.community-chain');
      const input = article?.querySelector('.community-chain-input');
      joinChain(button.dataset.chainId, input?.value || '');
    });
    document.addEventListener('click', (event) => {
      const otherTopButton = event.target.closest('.top-icon-btn:not(#btn-changelog-top)');
      if (otherTopButton) closePopover();
    }, true);
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape' || !isCommunityPopoverOpen()) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      closePopover();
      byId('btn-changelog-top')?.focus();
    }, true);
    updateAnnouncementBadge();
    loadFeed({ silent: true });
    window.setInterval(() => {
      if (document.visibilityState === 'visible') loadFeed({ silent: true });
    }, 60000);
    window.addEventListener('focus', () => loadFeed({ silent: true }));
    if (isCommunityPopoverOpen()) loadFeed();
  });

  window.toggleCommunityPopover = (force) => {
    if (force === true) openPopover();
    else if (force === false) closePopover();
    else togglePopover();
  };

  // 投票已并入公告面板（2026-11-25），公告打开时由 game.js 调它刷新一次。
  window.GtnCommunity = {
    refresh: () => loadFeed(),
    isOpen: () => isCommunityPopoverOpen(),
    markRead: () => markCommunityItemsRead(),
  };
})();
