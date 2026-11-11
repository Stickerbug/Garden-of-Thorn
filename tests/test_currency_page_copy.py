# -*- coding: utf-8 -*-
"""货币页标题与货币名称分离。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dew_page_is_named_currency_without_renaming_thorn_dew():
    page = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    assert 'id="achievements-popover-title" class="account-popover-title">成就与货币</div>' in page
    assert 'data-achievement-tab="dew">货币</button>' in page
    assert '成就与荆露' not in page
    script = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
    assert "achievements_title: '成就与货币'" in script
    assert "thorn_dew: '荆露'" in script
    assert "achievements_title: 'Achievements & Currency'" in script
    assert '-currency-page-name-1' in (ROOT / 'static_version.txt').read_text(encoding='utf-8')
