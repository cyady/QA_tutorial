from __future__ import annotations

import re
from typing import Any

APPROX_MARKERS = ("약", "여", "내외", "정도", "수준", "가량")
UNIT_MULTIPLIERS = {
    "억": 100_000_000,
    "천만": 10_000_000,
    "만": 10_000,
    "천": 1_000,
    "백": 100,
    "십": 10,
}

TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(천만|억|만|천|백|십)?")


def is_approximate(text: str) -> bool:
    return any(marker in text for marker in APPROX_MARKERS)


def parse_korean_number_value(text: str) -> float | int | None:
    cleaned = text.replace(",", "")
    tokens = [(n, u or "") for n, u in TOKEN_RE.findall(cleaned)]
    if not tokens:
        return None

    has_unit = any(u for _, u in tokens)
    if has_unit:
        total = 0.0
        for num_str, unit in tokens:
            if not num_str:
                continue
            num = float(num_str)
            if unit:
                total += num * UNIT_MULTIPLIERS[unit]
            else:
                total += num
    else:
        if len(tokens) != 1:
            return None
        total = float(tokens[0][0])

    if abs(total - round(total)) < 1e-9:
        return int(round(total))
    return total


def normalize_ko_number(text: str, *, unit: str | None = None) -> dict[str, Any] | None:
    value = parse_korean_number_value(text)
    if value is None:
        return None

    out: dict[str, Any] = {
        "value": value,
        "approx": is_approximate(text),
    }
    if unit:
        out["unit"] = unit
    return out
