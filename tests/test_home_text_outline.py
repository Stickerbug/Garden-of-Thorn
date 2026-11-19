"""主界面（登录/主页）非按钮文字：白色填充 + 黑色描边。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")


def _block() -> str:
    marker = "#view-login .title-main,"
    start = STYLE.index(marker)
    return STYLE[start:start + 1200]


def test_outline_block_targets_home_text() -> None:
    block = _block()
    for selector in (
        "#view-login .title-main",
        "#view-login .title-sub",
        "#view-login .subtitle",
        "#view-login .login-divider span",
        "#view-login .home-copyright",
        "#view-login .home-icp",
    ):
        assert selector in block, f"缺少选择器 {selector}"
    assert "-webkit-text-fill-color: #fff" in block
    assert "-webkit-text-stroke: 3px #000" in block


def test_titles_use_a_thicker_stroke() -> None:
    assert "-webkit-text-stroke-width: 6px" in STYLE


def test_buttons_are_not_outlined() -> None:
    block = _block()
    head = block.split("{", 1)[0]
    assert "button" not in head, "按钮不应进入描边规则"


def test_status_bar_outlined_only_on_home() -> None:
    assert "#view-login:not(.hidden) ~ .status-bar {" in STYLE
    assert "#view-login:not(.hidden) ~ .status-bar #status-text {" in STYLE


def test_small_text_is_enlarged_for_legibility() -> None:
    tail = STYLE[STYLE.index("配合 3px 黑色描边") :]
    # 12px 的几处（游客模式分隔 / 版权 / ICP / 副标题）抬到 14–15px
    assert "#view-login #guest-divider-label" in tail
    assert "font-size: 15px" in tail
    assert "font-size: 14px" in tail


def test_stroke_width_follows_font_size() -> None:
    # 字号越小描边越细，否则 14px 的字会被 3px 描边糊死
    assert "#view-login .title-sub {\n  -webkit-text-stroke-width: 4px;" in STYLE
    assert "-webkit-text-stroke-width: 2px;" in STYLE
