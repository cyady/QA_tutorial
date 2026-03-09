#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _hangul_count(s: str) -> int:
    return sum(1 for ch in s if "\uac00" <= ch <= "\ud7a3")


def _latin_noise_count(s: str) -> int:
    return sum(1 for ch in s if "\u00c0" <= ch <= "\u024f")


def fix_mojibake_text(s: str) -> str:
    if not isinstance(s, str) or not s:
        return s
    try:
        repaired = s.encode("latin1").decode("utf-8")
    except Exception:
        return s
    before_score = _hangul_count(s) - _latin_noise_count(s)
    after_score = _hangul_count(repaired) - _latin_noise_count(repaired)
    return repaired if after_score > before_score else s


def fix_obj(v: Any) -> Any:
    if isinstance(v, str):
        return fix_mojibake_text(v)
    if isinstance(v, list):
        return [fix_obj(x) for x in v]
    if isinstance(v, dict):
        return {k: fix_obj(val) for k, val in v.items()}
    return v


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair UTF-8/latin1 mojibake strings in a JSON file.")
    parser.add_argument("--input", required=True, help="Input JSON path")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    data = json.loads(src.read_text(encoding="utf-8-sig"))
    repaired = fix_obj(data)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "input": str(src), "output": str(dst)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

