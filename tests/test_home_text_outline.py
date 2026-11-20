"""主界面（登录/主页）非按钮文字：白色填充 + 黑色外描边。

外描边用 16 个方向的硬投影拼成（`--gtn-ring-*`），不用 -webkit-text-stroke：
后者是居中描边，一半压在字形里，细笔画被吃掉一半填充后各方向粗细不一。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLE = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
TIPS = (ROOT / "static" / "css" / "tips.css").read_text(encoding="utf-8")

OUTLINE_START = STYLE.index("/* 主界面（登录/主页）文字样式")


def _block() -> str:
    marker = "#view-login .title-main,"
    start = STYLE.index(marker)
    return STYLE[start:start + 1400]


def _preset(name: str) -> str:
    start = STYLE.index(f"--gtn-ring-{name}:")
    return STYLE[start : STYLE.index(";", start)]


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
    assert "text-shadow: var(--gtn-ring-1-5)" in block


def test_outline_no_longer_uses_centered_text_stroke() -> None:
    outline = STYLE[OUTLINE_START:]
    # 注释里会提到 -webkit-text-stroke，这里只检查真正生效的声明
    assert not re.search(r"-webkit-text-stroke(-width|-color)?\s*:", outline), (
        "描边应改用环形投影，不再用居中描边"
    )


def test_ring_presets_are_sixteen_directions() -> None:
    for name, radius in (("1", 1), ("1-5", 1.5), ("2", 2), ("3", 3)):
        preset = _preset(name)
        shadows = preset.split("0 #000")
        assert len(shadows) - 1 == 16, f"--gtn-ring-{name} 应有 16 个方向的投影"
        assert f"{radius:g}px 0px" in preset, f"--gtn-ring-{name} 半径应为 {radius}px"


def test_buttons_are_not_outlined() -> None:
    block = _block()
    head = block.split("{", 1)[0]
    assert "button" not in head, "按钮不应进入描边规则"


def test_status_bar_outlined_only_on_home() -> None:
    assert "#view-login:not(.hidden) ~ .status-bar {" in STYLE
    assert "#view-login:not(.hidden) ~ .status-bar #status-text {" in STYLE


def test_small_text_is_enlarged_for_legibility() -> None:
    tail = STYLE[STYLE.index("把主界面上的小字统一抬到可读尺寸") :]
    assert "#view-login #guest-divider-label" in tail
    assert "font-size: 15px" in tail
    assert "font-size: 14px" in tail


def test_outline_width_follows_font_size() -> None:
    # 字号越小外圈越细，否则 14px 的字会被描边糊死
    assert "#view-login .title-sub {\n  text-shadow: var(--gtn-ring-2);" in STYLE
    small = STYLE[STYLE.index("#view-login .subtitle,\n#view-login #guest-divider-label,") :]
    assert "text-shadow: var(--gtn-ring-1);" in small


def test_tips_reuses_the_same_ring_presets() -> None:
    assert "text-shadow: var(--gtn-ring-1);" in TIPS
    assert "-webkit-text-stroke" not in TIPS


def test_lobby_only_outlines_text_off_white_cards() -> None:
    # 大厅标题压在浅色页面底上 → 白字 + 外描边；白卡片里的文字保持深色
    lobby = STYLE[STYLE.index("/* 多人游戏大厅：") :]
    assert "#view-lobby .lobby-header h2 {" in lobby
    assert "text-shadow: var(--gtn-ring-2);" in lobby
    assert "#view-lobby #season-countdown," in lobby
    head = lobby[: lobby.index("{")]
    for dark in (".lobby-section h3", ".info-text", ".lobby-chat-title", ".mode-tab"):
        assert dark not in head, f"{dark} 在白卡片上，不该改成白字"

