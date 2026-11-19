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
    assert "-webkit-text-stroke: 1px #000" in block


def test_buttons_are_not_outlined() -> None:
    block = _block()
    head = block.split("{", 1)[0]
    assert "button" not in head, "按钮不应进入描边规则"


def test_status_bar_outlined_only_on_home() -> None:
    assert "#view-login:not(.hidden) ~ .status-bar {" in STYLE
    assert "#view-login:not(.hidden) ~ .status-bar #status-text {" in STYLE
