from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_DICT_PATH = Path(__file__).with_name("keywords.yaml")


def load_keyword_dictionary(path: str | None = None) -> dict[str, list[str]]:
    target = Path(path) if path else DEFAULT_DICT_PATH
    with target.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out: dict[str, list[str]] = {}
    for key, values in data.items():
        out[str(key)] = [str(v) for v in (values or [])]
    return out
