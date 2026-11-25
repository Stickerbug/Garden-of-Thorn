from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
OPS = (ROOT / 'templates' / 'community_ops.html').read_text(encoding='utf-8')
PUBLIC_JS = (ROOT / 'static' / 'js' / 'community.js').read_text(encoding='utf-8')
OPS_JS = (ROOT / 'static' / 'js' / 'community_ops.js').read_text(encoding='utf-8')
STYLE = (ROOT / 'static' / 'css' / 'style.css').read_text(encoding='utf-8')
OPS_STYLE = (ROOT / 'static' / 'css' / 'community_ops.css').read_text(encoding='utf-8')


def test_main_page_has_one_announcement_surface_with_polls_inside():
    """公告与投票已合并成一个面板（2026-11-25），只保留顶栏「公告」入口。"""
    required = (
        'id="btn-changelog-top"',
        'id="changelog-popover"',
        'id="changelog-popover-body"',
        'id="community-feed"',
        'id="community-manage-link"',
        'id="btn-community-refresh"',
        '/static/js/community.js',
        '/static/css/community.css',
    )
    for marker in required:
        assert marker in INDEX
    # 独立的投票入口与投票弹层都必须彻底移除，避免两个入口展示同一份内容。
    assert 'id="btn-community-top"' not in INDEX
    assert 'id="community-popover"' not in INDEX
    assert '.community-top-btn' not in STYLE
    assert '.changelog-top-btn::before { --ui-icon-url: url("/static/assets/ui-icons/log.svg"); }' in STYLE


def test_public_client_uses_safe_dom_and_private_vote_results_contract():
    assert "requestJson('/api/community/feed')" in PUBLIC_JS
    assert "'X-Community-CSRF': state.csrfToken" in PUBLIC_JS
    assert "item.effective_state === 'closed'" in PUBLIC_JS
    assert "option.vote_count" in PUBLIC_JS
    assert 'textContent' in PUBLIC_JS
    assert '.innerHTML' not in PUBLIC_JS


def test_ops_page_and_client_cover_all_operations():
    required_ids = (
        'announcement-create-form',
        'poll-create-form',
        'announcement-list',
        'poll-list',
        'audit-list',
    )
    for item in required_ids:
        assert f'id="{item}"' in OPS
    for endpoint in (
        '/api/community/ops/workspace',
        '/api/community/ops/announcements',
        '/api/community/ops/polls',
    ):
        assert endpoint in OPS_JS
    assert "'X-Community-Ops-CSRF'" in OPS_JS
    assert '.innerHTML' not in OPS_JS


def test_ops_page_has_no_changelog_controls():
    assert 'announcement-changelog' not in OPS
    assert 'draft-list' not in OPS
    assert '更新日志草稿' not in OPS
    assert 'changelog_draft' not in OPS_JS
    assert '/api/community/ops/changelog-drafts/' not in OPS_JS


def test_ops_refresh_button_keeps_a_readable_width():
    assert '#ops-refresh' in OPS_STYLE
    assert 'min-width: 68px' in OPS_STYLE
    assert 'white-space: nowrap' in OPS_STYLE


def test_new_announcements_and_polls_have_a_persistent_unread_dot():
    assert 'gtn_community_announcement_reads_v1' in PUBLIC_JS
    assert 'function pollReceipt(item)' in PUBLIC_JS
    assert 'function currentFeedItems()' in PUBLIC_JS
    assert 'function applyServerRead(payload)' in PUBLIC_JS
    assert "'/api/community/read'" in PUBLIC_JS
    assert 'gtn_community_reads_v1' in PUBLIC_JS
    assert 'function updateAnnouncementBadge()' in PUBLIC_JS
    assert "button.classList.toggle('has-community-unread', hasUnread)" in PUBLIC_JS
    assert 'function markCommunityItemsRead()' in PUBLIC_JS
    assert '.changelog-top-btn.has-community-unread::after' in STYLE


def test_announcement_panel_hosts_the_poll_section():
    """单一「公告」面板：上面是更新日志，下面挂投票与接龙。"""
    assert 'aria-label="公告"' in INDEX
    assert 'id="changelog-popover-title" class="account-popover-title">公告</div>' in INDEX
    assert 'class="changelog-popover-section"' in INDEX
    assert 'class="changelog-section-title">投票与接龙</div>' in INDEX
    # 投票区必须在公告面板内部，而不是另一层弹窗。
    start = INDEX.index('id="changelog-popover"')
    end = INDEX.index('id="changelog-popover-body"', start)
    later = INDEX.index('id="community-feed"', end)
    assert start < end < later
    game = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
    assert 'const community = (Array.isArray(announcements)' in game
    assert 'pinned: true' in game
    assert 'const entries = [...community, ...logs]' in game
    assert "body: JSON.stringify({ types: ['announcement'] })" in game
    assert 'communityReadIds' in game
    assert 'window.GtnCommunity' in game
    assert "body: JSON.stringify({ types: ['poll', 'chain'] })" in PUBLIC_JS
    assert '目前没有正在展示的投票或接龙。' in PUBLIC_JS


def test_changelog_api_includes_announcements_and_scoped_read():
    app_source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert "'announcements': feed.get('announcements') or []" in app_source
    assert 'mark_community_feed_read(user_id, content_types=content_types)' in app_source
    ops_source = (ROOT / 'community_ops.py').read_text(encoding='utf-8')
    assert 'def mark_community_feed_read(user_id, content_types=None):' in ops_source
    assert "if 'announcement' in requested:" in ops_source
    assert "if 'poll' in requested:" in ops_source
    assert "if 'chain' in requested:" in ops_source
    assert 'community-announcements-merged-1' in (ROOT / 'static_version.txt').read_text(encoding='utf-8')
