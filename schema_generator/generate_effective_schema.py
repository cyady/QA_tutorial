#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request


DEFAULT_VIEW_VERSION = "20250519"
DEFAULT_LAYOUT_VERSION = "20241114"


@dataclass
class HttpConfig:
    base_url: str
    api_base_url: str
    token: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap_ps_list(payload: Any) -> Any:
    if isinstance(payload, dict) and "value" in payload and isinstance(payload["value"], list):
        return payload["value"]
    return payload


def _json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _fetch_json(url: str, headers: dict[str, str]) -> Any:
    req = request.Request(url=url, headers=headers, method="GET")
    with request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
        field_id = str(node["id"])
        merged = dict(node)
        if field_id in out:
            # Keep latest visibility if provided in nested layouts.
            prev_visible = bool(out[field_id].get("is_visible"))
            merged_visible = bool(merged.get("is_visible"))
            merged["is_visible"] = prev_visible or merged_visible
        out[field_id] = merged

    for value in node.values():
        _extract_field_defs(value, out)


def _build_effective_field_ids(
    active_fields: list[dict[str, Any]],
    deal_view: dict[str, Any],
    layout_settings: dict[str, Any] | None,
) -> tuple[set[str], set[str], set[str]]:
    active_ids = {str(f["id"]) for f in active_fields}
    base_ids = {
        str(f["id"])
        for f in active_fields
        if f.get("category") in ("system", "standard")
    }

    custom_field_map = deal_view.get("deal", {}).get("custom_field", {})
    custom_ids = {str(k) for k in custom_field_map.keys()}

    visible_ids: set[str] = set()
    if layout_settings:
        layout_fields: dict[str, dict[str, Any]] = {}
        _extract_field_defs(layout_settings, layout_fields)
        visible_ids = {
            fid for fid, field in layout_fields.items() if bool(field.get("is_visible"))
        }

    # Primary signal: active + (system/standard always) + custom keys in this deal.
    # Secondary signal: visible fields in layout settings (union).
    effective = (base_ids | custom_ids | visible_ids) & active_ids
    return effective, custom_ids, visible_ids


def _to_field_map(fields: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(f["id"]): f for f in fields}


def build_effective_schema(
    active_fields: list[dict[str, Any]],
    deal_view: dict[str, Any],
    layout_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    field_map = _to_field_map(active_fields)
    effective_ids, custom_ids, visible_ids = _build_effective_field_ids(
        active_fields=active_fields,
        deal_view=deal_view,
        layout_settings=layout_settings,
    )

    effective_fields = [field_map[fid] for fid in effective_ids if fid in field_map]
    effective_fields.sort(
        key=lambda x: (
            0 if x.get("category") == "system" else 1 if x.get("category") == "standard" else 2,
            int(x.get("order", 10**9)),
            str(x.get("id")),
        )
    )

    record_type = deal_view.get("deal", {}).get("record_type") or {}
    missing_custom_from_active = sorted(fid for fid in custom_ids if fid not in field_map)

    return {
        "meta": {
            "generated_at": _utc_now_iso(),
            "deal_id": deal_view.get("deal", {}).get("id"),
            "record_type_id": record_type.get("id"),
            "record_type_name": record_type.get("name"),
        },
        "counts": {
            "active_total": len(active_fields),
            "effective_total": len(effective_fields),
            "custom_keys_in_deal_view": len(custom_ids),
            "layout_visible_count": len(visible_ids),
            "missing_custom_from_active": len(missing_custom_from_active),
        },
        "effective_field_ids": [str(f["id"]) for f in effective_fields],
        "missing_custom_field_ids_in_active": missing_custom_from_active,
        "effective_fields": effective_fields,
    }


def _from_api(
    cfg: HttpConfig,
    deal_id: int,
    view_version: str,
    layout_version: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    headers = {
        "authorization": f"Bearer {cfg.token}",
        "x-recatch-request": "true",
        "x-locale": "Asia/Seoul",
    }
    active_url = f"{cfg.base_url}/api/field-definitions/active/deal"
    deal_view_url = (
        f"{cfg.api_base_url}/views/sales-entity/deal/{deal_id}?version={view_version}"
    )

    active_fields = _fetch_json(active_url, headers=headers)
    deal_view = _fetch_json(deal_view_url, headers=headers)

    layout_settings = None
    record_type_id = deal_view.get("deal", {}).get("record_type", {}).get("id")
    if record_type_id is not None:
        layout_url = (
            f"{cfg.api_base_url}/sales-entity/deal/record-type/{record_type_id}"
            f"/views/details/settings?version={layout_version}"
        )
        try:
            layout_settings = _fetch_json(layout_url, headers=headers)
        except Exception:
            layout_settings = None

    return active_fields, deal_view, layout_settings


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate effective deal schema (visible/usable field set) from Recatch APIs or JSON files."
    )
    p.add_argument("--output", required=True, help="Output JSON path")

    p.add_argument("--from-api", action="store_true", help="Fetch source JSON from APIs")
    p.add_argument("--deal-id", type=int, help="Deal ID (required with --from-api)")
    p.add_argument(
        "--token",
        help="Bearer token. If omitted, RECATCH_FB_TOKEN env var is used.",
    )
    p.add_argument(
        "--base-url",
        default="https://business-canvas.recatch.cc",
        help="Frontend base URL for active fields endpoint",
    )
    p.add_argument(
        "--api-base-url",
        default="https://api.recatch.cc",
        help="API base URL",
    )
    p.add_argument(
        "--view-version",
        default=DEFAULT_VIEW_VERSION,
        help="Version query for deal view endpoint",
    )
    p.add_argument(
        "--layout-version",
        default=DEFAULT_LAYOUT_VERSION,
        help="Version query for record-type layout endpoint",
    )

    p.add_argument("--active-fields-json", help="Local JSON path for active fields")
    p.add_argument("--deal-view-json", help="Local JSON path for deal view")
    p.add_argument("--layout-settings-json", help="Local JSON path for layout settings (optional)")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.from_api:
        if args.deal_id is None:
            parser.error("--deal-id is required with --from-api")
        token = args.token
        if not token:
            import os

            token = os.getenv("RECATCH_FB_TOKEN", "")
        if not token:
            parser.error("--token or RECATCH_FB_TOKEN is required with --from-api")

        cfg = HttpConfig(
            base_url=args.base_url.rstrip("/"),
            api_base_url=args.api_base_url.rstrip("/"),
            token=token,
        )
        active_fields, deal_view, layout_settings = _from_api(
            cfg=cfg,
            deal_id=args.deal_id,
            view_version=args.view_version,
            layout_version=args.layout_version,
        )
    else:
        if not args.active_fields_json or not args.deal_view_json:
            parser.error(
                "Either use --from-api or provide --active-fields-json and --deal-view-json"
            )
        active_fields = _unwrap_ps_list(_json_load(Path(args.active_fields_json)))
        deal_view = _json_load(Path(args.deal_view_json))
        layout_settings = (
            _json_load(Path(args.layout_settings_json))
            if args.layout_settings_json
            else None
        )

    out = build_effective_schema(
        active_fields=active_fields,
        deal_view=deal_view,
        layout_settings=layout_settings,
    )
    _json_dump(Path(args.output), out)
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(Path(args.output)),
                "effective_total": out["counts"]["effective_total"],
                "record_type_id": out["meta"]["record_type_id"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
