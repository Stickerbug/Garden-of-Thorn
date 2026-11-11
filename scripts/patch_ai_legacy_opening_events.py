#!/usr/bin/env python3
"""让 GTN-AI 运行时的 Vanilla 契约接受“已退役”的开局事件。

背景
----
``gtn_ai/vanilla_scope.py`` 的 ``vanilla_capability_manifest`` 要求
``BUILTIN_SETUP_EVENT_CARD_PRODUCTS``（当前是 2→ManaOrb、3→Light、8→Yggdrasil、
9→Dust）里的每个事件 id 都出现在 ``GameEngine.OPENING_EVENTS`` 里，否则抛::

    ValueError: setup-card producer events are absent from GameEngine.OPENING_EVENTS: 9

但游戏引擎在 b5a05f69 之后把可选的 9 号事件「多重瓣」移到了
``GameEngine.LEGACY_OPENING_EVENTS``（保留给统计/回放），并把它的产物牌
``Dust`` 继续留在 ``BUILTIN_SETUP_CARD_IDS`` 里。于是引擎自身是自洽的，
只是运行时把一个“历史事件”误判成“缺失事件”，worker 启动即退出。

修法
----
把 ``GameEngine.LEGACY_OPENING_EVENTS`` 的 id 并入校验集合。事件 9 的产物牌
仍然在 ``BUILTIN_SETUP_CARD_IDS`` 与牌包里，牌面/行为都不受影响。

用法
----
    /opt/gtn-ai-venv/bin/python scripts/patch_ai_legacy_opening_events.py \
        [/opt/gtn-ai-runtime/gtn_ai/vanilla_scope.py]

脚本幂等：已打过补丁会打印 ALREADY_PATCHED 并退出 0；找不到锚点退出 2。
重新安装 AI 运行时（``scripts/setup_gtn_ai.sh``）会覆盖该文件，装完要再跑一次。
"""

from __future__ import annotations

import io
import sys

DEFAULT_TARGET = "/opt/gtn-ai-runtime/gtn_ai/vanilla_scope.py"

OLD = (
    "    opening_event_ids = tuple(sorted(_event_id(value) for value in opening_events))\n"
    "    missing_product_events"
)

NEW = (
    "    opening_event_ids = tuple(sorted(_event_id(value) for value in opening_events))\n"
    "    # The game engine retires selectable opening events into LEGACY_OPENING_EVENTS\n"
    "    # while keeping their setup cards for history and replays (e.g. event 9 -> Dust).\n"
    '    legacy_events = getattr(GameEngine, "LEGACY_OPENING_EVENTS", {}) or {}\n'
    "    if isinstance(legacy_events, dict):\n"
    "        opening_event_ids = tuple(\n"
    "            sorted(set(opening_event_ids) | {_event_id(value) for value in legacy_events})\n"
    "        )\n"
    "    missing_product_events"
)


def main(argv: list[str]) -> int:
    target = argv[1] if len(argv) > 1 else DEFAULT_TARGET
    try:
        src = io.open(target, encoding="utf-8").read()
    except OSError as exc:
        print(f"CANNOT_READ {target}: {exc}")
        return 2

    if "LEGACY_OPENING_EVENTS" in src:
        print("ALREADY_PATCHED")
        return 0
    if OLD not in src:
        print("ANCHOR_NOT_FOUND")
        return 2

    io.open(target, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
    print(f"PATCH_OK {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
