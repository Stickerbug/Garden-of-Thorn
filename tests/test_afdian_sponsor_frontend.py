# -*- coding: utf-8 -*-
"""赞助页累计金额与称号进度展示。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sponsor_page_shows_tiers_progress_and_no_golden_exchange():
    page = (ROOT / 'templates/afdian.html').read_text(encoding='utf-8')
    assert 'id="sponsor-total"' in page
    assert 'id="sponsor-titles"' in page
    assert '累计满 1 元获得灰色称号「赞助者」' in page
    assert '满 10 元获得彩虹称号「大赞助者」' in page
    assert '.sponsor-title-basic' in page
    assert '.sponsor-title-major' in page
    assert '赞助不再发放金露。' not in page
    assert '按方案兑换<b>金露' not in page


def test_sponsor_script_renders_actual_amounts_and_refreshes_progress():
    script = (ROOT / 'static/js/afdian.js').read_text(encoding='utf-8')
    assert 'function renderSponsor(data)' in script
    assert 'sponsor.total_amount' in script
    assert 'title.threshold_amount' in script
    assert 'title.owned' in script
    assert 'o.total_amount' in script
    assert 'p.dew_amount' not in script
    assert 'o.dew_amount' not in script
    assert 'renderSponsor(data.sponsor);' in script
    assert '-afdian-sponsor-titles-1' in (ROOT / 'static_version.txt').read_text(encoding='utf-8')


def test_home_shop_sponsor_panel_does_not_show_legacy_currency_mapping():
    page = (ROOT / 'templates/index.html').read_text(encoding='utf-8')
    assert '通过爱发电赞助获得<b>付费荆露</b>' not in page
    assert '完整赞助页（累计进度 / 重置绑定码 / 查询补单）' in page
    script = (ROOT / 'static/js/game.js').read_text(encoding='utf-8')
    assert 'p.dew_amount' not in script
    assert '累计赞助满1元获得灰色「赞助者」，满10元获得彩虹「大赞助者」；不再发放金露。' in script
