#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把策划表导出的 tips 原始表（TSV/CSV）转换成 static/data/tips.json。

用法：
    python scripts/tips_from_csv.py                     # 用默认源文件生成
    python scripts/tips_from_csv.py <源文件> [--check]   # 指定源文件；--check 只校验不写

源文件格式：首行表头，两列 `author,text`（也接受 `作者` / `Tip正文` 作为表头）。
分隔符按扩展名推断：.tsv/.txt 用 Tab，.csv 用逗号（csv 模块处理引号）。
运行时**不读**这个源文件；它只是留档 + 重新导入用，日常编辑直接改 tips.json。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "docs" / "tips" / "tips-source.tsv"
TARGET = ROOT / "static" / "data" / "tips.json"

MAX_TEXT_LEN = 160
SCHEMA = 1


def _read_rows(path: Path) -> list[tuple[str, str]]:
    delimiter = "," if path.suffix.lower() == ".csv" else "\t"
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise SystemExit(f"源文件为空：{path}")
    header = [cell.strip().lower() for cell in rows[0]]
    if len(header) < 2:
        raise SystemExit(f"表头至少需要两列（作者、正文），实际：{header}")
    out: list[tuple[str, str]] = []
    for row in rows[1:]:
        author = (row[0] if len(row) > 0 else "").strip()
        text = (row[1] if len(row) > 1 else "").strip()
        if not text:
            continue
        out.append((author or "佚名", text))
    return out


def build(rows: list[tuple[str, str]]) -> dict:
    tips: list[dict] = []
    seen: dict[str, str] = {}
    for index, (author, text) in enumerate(rows, start=1):
        if "\n" in text or "\r" in text:
            raise SystemExit(f"第 {index} 条含换行，请先合并：{text[:40]}…")
        if len(text) > MAX_TEXT_LEN:
            print(f"[warn] 第 {index} 条 {len(text)} 字超过 {MAX_TEXT_LEN}：{text[:30]}…", file=sys.stderr)
        if text in seen:
            print(f"[warn] 第 {index} 条与 {seen[text]} 重复，已跳过：{text[:30]}…", file=sys.stderr)
            continue
        seen[text] = f"第 {index} 条"
        tips.append(
            {
                "id": f"t{len(tips) + 1:04d}",
                "author": author,
                "text": {"zh": text},
            }
        )
    return {
        "schema": SCHEMA,
        "version": "2026-11-20.1",
        "updated_at": "2026-11-20",
        "tips": tips,
    }


def validate(payload: dict) -> list[str]:
    problems: list[str] = []
    if payload.get("schema") != SCHEMA:
        problems.append(f"schema 应为 {SCHEMA}")
    tips = payload.get("tips")
    if not isinstance(tips, list) or not tips:
        return problems + ["tips 为空"]
    ids: set[str] = set()
    texts: dict[str, str] = {}
    for tip in tips:
        tid = tip.get("id")
        if not tid:
            problems.append("存在缺少 id 的条目")
            continue
        if tid in ids:
            problems.append(f"id 重复：{tid}")
        ids.add(tid)
        if not tip.get("author"):
            problems.append(f"{tid} 缺少作者")
        body = tip.get("text")
        if isinstance(body, str):
            body = {"zh": body}
        if not isinstance(body, dict) or not body.get("zh"):
            problems.append(f"{tid} 缺少中文正文")
            continue
        zh = body["zh"]
        if len(zh) > MAX_TEXT_LEN:
            problems.append(f"{tid} 正文 {len(zh)} 字超过 {MAX_TEXT_LEN}")
        if "\n" in zh:
            problems.append(f"{tid} 正文含换行")
        if zh in texts:
            problems.append(f"{tid} 与 {texts[zh]} 正文重复")
        texts[zh] = tid
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default=str(DEFAULT_SOURCE))
    parser.add_argument("--check", action="store_true", help="只校验 tips.json，不重新生成")
    args = parser.parse_args()

    if args.check:
        payload = json.loads(TARGET.read_text(encoding="utf-8"))
        problems = validate(payload)
        for problem in problems:
            print(f"[fail] {problem}", file=sys.stderr)
        if problems:
            return 1
        print(f"OK：{len(payload['tips'])} 条，version={payload.get('version')}")
        return 0

    source = Path(args.source)
    if not source.is_absolute():
        source = (ROOT / source).resolve()
    rows = _read_rows(source)
    payload = build(rows)
    problems = validate(payload)
    if problems:
        for problem in problems:
            print(f"[fail] {problem}", file=sys.stderr)
        return 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    authors = sorted({tip["author"] for tip in payload["tips"]})
    print(f"写入 {TARGET.relative_to(ROOT)}：{len(payload['tips'])} 条，作者 {len(authors)} 位（{'、'.join(authors)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
