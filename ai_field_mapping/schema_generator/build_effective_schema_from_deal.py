#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request
import time


DEFAULT_BASE_URL = "https://business-canvas.recatch.cc"
DEFAULT_API_BASE_URL = "https://api.recatch.cc"
DEFAULT_VIEW_VERSION = "20250519"
DEFAULT_LAYOUT_VERSION = "20241114"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_RAW_DIR = DEFAULT_OUTPUT_DIR / "raw"


def _headers(token: str, base_url: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {token}",
        "x-recatch-request": "true",
        "x-locale": "Asia/Seoul",
        "origin": base_url,
        "referer": f"{base_url}/",
        "accept": "application/json, text/plain, */*",
        "user-agent": "Mozilla/5.0",
    }


def _fetch_json(url: str, headers: dict[str, str]) -> Any:
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_json_with_retry(url: str, headers: dict[str, str], label: str, retries: int = 2) -> Any:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _fetch_json(url, headers)
        except error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = "<failed to read body>"
            # Retry only on 5xx.
            if 500 <= e.code < 600 and attempt < retries:
                time.sleep(0.6 * (attempt + 1))
                last_err = RuntimeError(
                    f"[{label}] {e.code} {e.reason} url={url} body={body[:500]}"
                )
                continue
            raise SystemExit(
                f"[{label}] HTTP {e.code} {e.reason}\nurl: {url}\nbody: {body[:1200]}"
            ) from e
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise SystemExit(f"[{label}] request failed\nurl: {url}\nerror: {e}") from e
    if last_err:
        raise SystemExit(str(last_err))
    raise SystemExit(f"[{label}] unknown fetch error: {url}")


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _hangul_count(s: str) -> int:
    return sum(1 for ch in s if "\uac00" <= ch <= "\ud7a3")


def _latin_noise_count(s: str) -> int:
    return sum(1 for ch in s if "\u00c0" <= ch <= "\u024f")


def _fix_mojibake_text(s: str) -> str:
    if not isinstance(s, str) or not s:
        return s
    try:
        repaired = s.encode("latin1").decode("utf-8")
    except Exception:
        return s
    before_score = _hangul_count(s) - _latin_noise_count(s)
    after_score = _hangul_count(repaired) - _latin_noise_count(repaired)
    return repaired if after_score > before_score else s


def _fix_obj(v: Any) -> Any:
    if isinstance(v, str):
        return _fix_mojibake_text(v)
    if isinstance(v, list):
        return [_fix_obj(x) for x in v]
    if isinstance(v, dict):
        return {k: _fix_obj(val) for k, val in v.items()}
    return v


def _extract_field_defs(node: Any, out: dict[str, dict[str, Any]]) -> None:
    if node is None:
        return
    if isinstance(node, list):
        for item in node:
            _extract_field_defs(item, out)
        return
    if not isinstance(node, dict):
        return
    if all(k in node for k in ("id", "label", "type", "category")):
        fid = str(node["id"])
        merged = dict(node)
        if fid in out:
            prev_visible = bool(out[fid].get("is_visible"))
            cur_visible = bool(merged.get("is_visible"))
            merged["is_visible"] = prev_visible or cur_visible
        out[fid] = merged
    for value in node.values():
        _extract_field_defs(value, out)


def build_effective_schema(
    active_fields: list[dict[str, Any]],
    deal_view: dict[str, Any],
    layout_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    field_map = {str(f["id"]): f for f in active_fields if isinstance(f, dict) and "id" in f}
    active_ids = set(field_map.keys())
    base_ids = {
        str(f["id"])
        for f in active_fields
        if isinstance(f, dict) and f.get("category") in ("system", "standard") and "id" in f
    }
    custom_ids = set((deal_view.get("deal", {}).get("custom_field") or {}).keys())

    visible_ids: set[str] = set()
    if layout_settings:
        tmp: dict[str, dict[str, Any]] = {}
        _extract_field_defs(layout_settings, tmp)
        visible_ids = {k for k, v in tmp.items() if bool(v.get("is_visible"))}

    effective_ids = (base_ids | custom_ids | visible_ids) & active_ids
    effective_fields = [field_map[x] for x in effective_ids]
    effective_fields.sort(
        key=lambda x: (
            0 if x.get("category") == "system" else 1 if x.get("category") == "standard" else 2,
            int(x.get("order", 10**9)),
            str(x.get("id")),
        )
    )
    effective_fields = _fix_obj(effective_fields)
    record_type = deal_view.get("deal", {}).get("record_type") or {}

    return {
        "meta": {
            "deal_id": deal_view.get("deal", {}).get("id"),
            "record_type_id": record_type.get("id"),
            "record_type_name": _fix_mojibake_text(str(record_type.get("name") or "")),
        },
        "counts": {
            "active_total": len(active_fields),
            "effective_total": len(effective_fields),
            "custom_keys_in_deal_view": len(custom_ids),
            "layout_visible_count": len(visible_ids),
        },
        "effective_field_ids": [str(f.get("id")) for f in effective_fields],
        "effective_fields": effective_fields,
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Fetch raw schema/view by deal_id and build effective_schema in one shot."
    )
    p.add_argument("--deal-id", type=int, required=True)
    p.add_argument("--token", help="Bearer token. If omitted, RECATCH_FB_TOKEN env var is used.")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    p.add_argument("--view-version", default=DEFAULT_VIEW_VERSION)
    p.add_argument("--layout-version", default=DEFAULT_LAYOUT_VERSION)
    p.add_argument(
        "--output",
        help="Output effective_schema path. default: <this module>/output/effective_schema_<deal_id>.json",
    )
    p.add_argument(
        "--raw-dir",
        default=str(DEFAULT_RAW_DIR),
        help="Directory to store raw API JSON files",
    )
    args = p.parse_args()

    token = args.token or os.getenv("RECATCH_FB_TOKEN", "")
    if not token:
        raise SystemExit("token required: --token or RECATCH_FB_TOKEN")

    base_url = args.base_url.rstrip("/")
    api_base = args.api_base_url.rstrip("/")
    hdrs = _headers(token=token, base_url=base_url)

    raw_dir = Path(args.raw_dir) / f"deal_{args.deal_id}"
    raw_dir.mkdir(parents=True, exist_ok=True)

    active_url = f"{base_url}/api/field-definitions/active/deal"
    deal_view_url = f"{api_base}/views/sales-entity/deal/{args.deal_id}?version={args.view_version}"

    active_fields = _fetch_json_with_retry(active_url, hdrs, label="active_deal")
    deal_view = _fetch_json_with_retry(deal_view_url, hdrs, label="deal_view")

    record_type_id = deal_view.get("deal", {}).get("record_type", {}).get("id")
    layout_settings = None
    if record_type_id is not None:
        layout_url = (
            f"{api_base}/sales-entity/deal/record-type/{record_type_id}/views/details/settings"
            f"?version={args.layout_version}"
        )
        try:
            layout_settings = _fetch_json_with_retry(layout_url, hdrs, label="layout_settings")
        except Exception:
            layout_settings = None

    _save_json(raw_dir / "active_deal.json", active_fields)
    _save_json(raw_dir / "deal_view.json", deal_view)
    if layout_settings is not None:
        _save_json(raw_dir / "layout_settings.json", layout_settings)

    effective = build_effective_schema(
        active_fields=active_fields if isinstance(active_fields, list) else active_fields.get("value", []),
        deal_view=deal_view,
        layout_settings=layout_settings,
    )

    out_path = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / f"effective_schema_{args.deal_id}.json"
    _save_json(out_path, effective)

    print(
        json.dumps(
            {
                "ok": True,
                "deal_id": args.deal_id,
                "record_type_id": effective["meta"]["record_type_id"],
                "effective_total": effective["counts"]["effective_total"],
                "output": str(out_path),
                "raw_dir": str(raw_dir),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
