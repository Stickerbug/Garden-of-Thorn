"""Tips 系统：数据文件、前端接线与抽取规则的静态校验。"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIPS_JSON = ROOT / "static" / "data" / "tips.json"
TIPS_JS = ROOT / "static" / "js" / "tips.js"
TIPS_CSS = ROOT / "static" / "css" / "tips.css"
INDEX_HTML = ROOT / "templates" / "index.html"
GAME_JS = ROOT / "static" / "js" / "game.js"
STATIC_VERSION = ROOT / "static_version.txt"

VIEW_IDS = ("view-login", "view-lobby", "view-draft", "view-event-select")
MAX_TEXT_LEN = 160


def _payload() -> dict:
    return json.loads(TIPS_JSON.read_text(encoding="utf-8"))


def _text_of(tip: dict) -> str:
    body = tip.get("text")
    if isinstance(body, str):
        return body
    return (body or {}).get("zh", "")


def test_tips_json_shape() -> None:
    payload = _payload()
    assert payload["schema"] == 1
    assert payload["version"]
    tips = payload["tips"]
    assert len(tips) >= 100, f"tips 数量异常：{len(tips)}"


def test_tip_ids_unique_and_present() -> None:
    tips = _payload()["tips"]
    ids = [tip["id"] for tip in tips]
    assert all(ids), "存在空 id"
    assert len(ids) == len(set(ids)), "id 重复"


def test_tip_text_rules() -> None:
    for tip in _payload()["tips"]:
        text = _text_of(tip)
        assert text.strip(), f"{tip['id']} 正文为空"
        assert "\n" not in text, f"{tip['id']} 正文含换行"
        assert len(text) <= MAX_TEXT_LEN, f"{tip['id']} 正文 {len(text)} 字超长"


def test_tip_authors_present() -> None:
    authors = {tip.get("author") for tip in _payload()["tips"]}
    assert "" not in authors
    assert len(authors) >= 5


def test_tip_texts_unique() -> None:
    texts = [_text_of(tip) for tip in _payload()["tips"]]
    assert len(texts) == len(set(texts)), "存在重复文案"


def test_tip_markup_preserved() -> None:
    texts = " ".join(_text_of(tip) for tip in _payload()["tips"])
    assert "[[card:" in texts
    assert "[[icon:electric_damage]]" in texts
    # 卡牌标记必须闭合，否则前端会原样显示方括号
    assert texts.count("[[card:") == texts.count("]]") - texts.count("[[icon:")


def test_tips_js_contract() -> None:
    source = TIPS_JS.read_text(encoding="utf-8")
    assert "gtn_tips_state_v1" in source
    assert "MIN_INTERVAL_MS" in source
    assert "colorizeCardText" in source
    assert "bindInlineCardChips" in source
    assert "decodeURI" in source  # 长链接解码后再显示，避免整条 tip 被链接占满
    # 「这里[说明…https://…]」：中括号里的说明不显示，改让紧邻在前的字变成超链接
    assert "ANNOTATED_LINK" in source
    assert "\\u0000" in source
    for view_id in VIEW_IDS:
        assert view_id in source, f"tips.js 未包含 {view_id}"
    assert "window.GtnTips" in source
    # 轮换：每 15 秒自动换一条，点一下也换一条（点卡牌 chip / 链接时不抢）
    assert "ROTATE_MS = 15000" in source
    assert "function startRotate()" in source
    assert "function rotateNow()" in source
    assert "is-fading" in source
    assert "'.inline-card-chip, a'" in source


def test_tips_css_contract() -> None:
    source = TIPS_CSS.read_text(encoding="utf-8")
    assert "#gtn-tips" in source or ".gtn-tips" in source
    assert 'data-view="view-login"' in source
    assert "pointer-events" in source
    # 需求：不要外框，直接显示文字（不能有底板 / 描边 / 投影 / 毛玻璃）
    panel = source.split(".gtn-tips-panel {", 1)[1].split("}", 1)[0]
    for banned in ("background", "border", "box-shadow", "backdrop-filter"):
        assert banned not in panel, f".gtn-tips-panel 不应再有 {banned}"
    # 轮换时的淡出效果 + 文字区域可点击的指针
    assert ".gtn-tips.is-fading" in source
    assert "cursor: pointer" in source


def test_index_html_wires_tips() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="gtn-tips"' in html
    assert 'id="gtn-tips-text"' in html
    assert "/static/css/tips.css" in html
    assert "/static/js/tips.js" in html
    # 缓存破坏：tips.json 的 ?v= 从容器上取，跟随 static_version
    assert 'data-version="{{ static_version' in html
    assert ">Tips:<" in html


def test_game_js_hooks() -> None:
    source = GAME_JS.read_text(encoding="utf-8")
    assert "window.GtnTips.onView(viewId)" in source
    assert "window.GtnTips.onLang(lang)" in source
    assert "window.GtnTips.onCardsReady()" in source
    # 三个调用点都必须带守卫，避免展示模块拖垮视图切换
    guarded = re.findall(r"if \(window\.GtnTips\) \{\s*try \{ window\.GtnTips\.", source)
    assert len(guarded) == 3, f"tips 钩子守卫数量异常：{len(guarded)}"


def test_static_version_bumped() -> None:
    assert "tips-system-1" in STATIC_VERSION.read_text(encoding="utf-8")


def _draw_sequence(total: int, draws: int, seed: int = 7) -> list[int]:
    """复刻 tips.js 的抽取规则：最近 50 条排除 + 候选池内均匀随机。"""
    rng = random.Random(seed)
    recent: list[int] = []
    limit = min(50, total - 1)
    out: list[int] = []
    for _ in range(draws):
        pool = [i for i in range(total) if i not in recent]
        if not pool:
            recent = []
            pool = list(range(total))
        picked = rng.choice(pool)
        recent.insert(0, picked)
        recent = recent[:limit]
        out.append(picked)
    return out


def test_draw_never_repeats_within_50() -> None:
    total = len(_payload()["tips"])
    sequence = _draw_sequence(total, 500)
    for index in range(50, len(sequence)):
        window = sequence[index - 50:index]
        assert sequence[index] not in window, f"第 {index} 次与最近 50 次重复"


def test_draw_is_roughly_uniform() -> None:
    total = len(_payload()["tips"])
    sequence = _draw_sequence(total, 20000, seed=11)
    counts = [0] * total
    for picked in sequence:
        counts[picked] += 1
    expected = len(sequence) / total
    for index, count in enumerate(counts):
        assert 0.6 * expected <= count <= 1.4 * expected, f"第 {index} 条出现 {count} 次，期望约 {expected:.0f}"
