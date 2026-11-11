"""排行榜只保留总榜（2026-11-11 删除赛季榜）。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_templates_expose_only_the_total_board():
    html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert 'data-leaderboard-scope="total"' in html
    assert 'data-leaderboard-scope="season"' not in html


def test_client_pins_the_leaderboard_to_total():
    js = (ROOT / 'static' / 'js' / 'game.js').read_text(encoding='utf-8')
    assert "let leaderboardScope = 'total';" in js
    start = js.index('function setLeaderboardScope(')
    body = js[start:js.index('\n}', start)]
    assert "leaderboardScope = 'total';" in body
    assert "'season'" not in body


def test_leaderboard_api_serves_only_the_total_board():
    src = (ROOT / 'app.py').read_text(encoding='utf-8')
    start = src.index('def api_leaderboard():')
    body = src[start:src.index('\n@app.route', start)]
    assert "scope = 'total'" in body
    assert 'default_min_games = 20' in body
