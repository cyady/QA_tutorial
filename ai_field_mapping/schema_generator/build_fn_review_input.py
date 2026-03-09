#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any


WS_RE = re.compile(r"\s+")
NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_json_or_jsonl(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return None
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    lines = [json.loads(line) for line in text.splitlines() if line.strip()]
    return lines


def _norm_text(s: str) -> str:
    return WS_RE.sub(" ", s.strip().lower())


def _hangul_count(s: str) -> int:
    return sum(1 for ch in s if "\uac00" <= ch <= "\ud7a3")


def _latin_noise_count(s: str) -> int:
    return sum(1 for ch in s if "\u00c0" <= ch <= "\u024f")


def _fix_mojibake_text(s: str) -> str:
    if not s:
        return s
    try:
        repaired = s.encode("latin1").decode("utf-8")
    except Exception:
        return s
    # Prefer repaired text only when it clearly looks better for Korean.
    before_score = _hangul_count(s) - _latin_noise_count(s)
    after_score = _hangul_count(repaired) - _latin_noise_count(repaired)
    return repaired if after_score > before_score else s


def _float_or_none(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _extract_numbers(text: str) -> list[float]:
    return [float(x) for x in NUM_RE.findall(text)]


def _candidate_signature(c: dict[str, Any]) -> dict[str, Any]:
    vtype = c.get("value_type")
    norm = c.get("normalized") or {}
    raw = c.get("raw_text", "")

    if vtype in ("number", "currency", "percentage", "duration"):
        if "value" in norm:
            return {"kind": "scalar", "value": _float_or_none(norm.get("value"))}
    if vtype in ("number_range", "percentage_range"):
        mn = _float_or_none(norm.get("min"))
        mx = _float_or_none(norm.get("max"))
        if mn is not None and mx is not None:
            return {"kind": "range", "min": min(mn, mx), "max": max(mn, mx)}
    if vtype == "email":
        return {"kind": "email", "value": _norm_text(raw)}

    text_val = norm.get("text") if isinstance(norm, dict) else None
    return {"kind": "text", "value": _norm_text(str(text_val or raw))}


def _flatten_model_output(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        out: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, list):
                out.extend(_flatten_model_output(item))
        return out
    return []


def _model_value_tokens(v: Any) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    if isinstance(v, (int, float)):
        tokens.append({"kind": "scalar", "value": float(v)})
        return tokens
    if isinstance(v, str):
        t = _norm_text(v)
        nums = _extract_numbers(t)
        for n in nums:
            tokens.append({"kind": "scalar", "value": n})
        tokens.append({"kind": "text", "value": t})
        return tokens
    if isinstance(v, list):
        for item in v:
            if isinstance(item, dict) and "value" in item:
                val = item["value"]
                if isinstance(val, (int, float)):
                    tokens.append({"kind": "scalar", "value": float(val)})
                else:
                    tokens.append({"kind": "text", "value": _norm_text(str(val))})
            else:
                tokens.extend(_model_value_tokens(item))
        return tokens
    if isinstance(v, dict):
        for vv in v.values():
            tokens.extend(_model_value_tokens(vv))
    return tokens


def _candidate_matches_model(candidate: dict[str, Any], model_fact: dict[str, Any]) -> bool:
    sig = _candidate_signature(candidate)
    extracted = model_fact.get("extracted_value")
    tokens = _model_value_tokens(extracted)

    if sig["kind"] == "scalar":
        val = sig.get("value")
        if val is None:
            return False
        for t in tokens:
            if t["kind"] == "scalar" and math.isclose(val, t["value"], rel_tol=1e-6, abs_tol=1e-6):
                return True
        return False

    if sig["kind"] == "range":
        mn = sig["min"]
        mx = sig["max"]
        vals = [t["value"] for t in tokens if t["kind"] == "scalar"]
        if len(vals) >= 2:
            vals.sort()
            if math.isclose(mn, vals[0], rel_tol=1e-6, abs_tol=1e-6) and math.isclose(
                mx, vals[-1], rel_tol=1e-6, abs_tol=1e-6
            ):
                return True
        for t in tokens:
            if t["kind"] == "text":
                if str(int(mn) if mn.is_integer() else mn) in t["value"] and str(
                    int(mx) if mx.is_integer() else mx
                ) in t["value"]:
                    return True
        return False

    if sig["kind"] == "email":
        em = sig["value"]
        for t in tokens:
            if t["kind"] == "text" and em in t["value"]:
                return True
        return False

    # text
    text = sig["value"]
    if not text:
        return False
    for t in tokens:
        if t["kind"] == "text" and (text in t["value"] or t["value"] in text):
            return True
    return False


def _value_type_compatible(vtype: str, field_type: str) -> bool:
    mapping = {
        "currency": {"currency", "number", "text", "textarea"},
        "number": {"number", "text", "textarea", "select"},
        "number_range": {"number", "text", "textarea", "select"},
        "percentage": {"number", "text", "textarea", "select"},
        "percentage_range": {"number", "text", "textarea", "select"},
        "date_expression": {"date", "date-time", "text", "textarea"},
        "duration": {"number", "text", "textarea"},
        "email": {"email", "text", "textarea"},
        "text": {"text", "textarea", "select", "multi-select"},
        "text_list": {"text", "textarea", "multi-select", "select"},
    }
    allow = mapping.get(vtype, {"text", "textarea", "select", "multi-select"})
    return field_type in allow


def _field_text_blob(field: dict[str, Any]) -> str:
    parts = [
        _fix_mojibake_text(str(field.get("label", ""))),
        _fix_mojibake_text(str(field.get("description", ""))),
        _fix_mojibake_text(str(field.get("caption", ""))),
    ]
    attrs = field.get("attributes") or {}
    if isinstance(attrs, dict):
        opts = attrs.get("options")
        if isinstance(opts, list):
            parts.extend(
                _fix_mojibake_text(str(o.get("label", ""))) for o in opts if isinstance(o, dict)
            )
    return _norm_text(" ".join(parts))


def _suggest_fields(candidate: dict[str, Any], effective_fields: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    cand_text = _norm_text(candidate.get("raw_text", ""))
    cand_sem = _norm_text(str(candidate.get("semantic_type", "")))
    cand_tokens = set((cand_text + " " + cand_sem).split())
    vtype = str(candidate.get("value_type", "text"))

    scored: list[tuple[float, dict[str, Any]]] = []
    for f in effective_fields:
        ftype = str(f.get("type", ""))
        if not _value_type_compatible(vtype, ftype):
            continue
        blob = _field_text_blob(f)
        ftokens = set(blob.split())
        overlap = len(cand_tokens & ftokens)
        type_bonus = 1.0 if _value_type_compatible(vtype, ftype) else 0.0
        score = overlap + type_bonus
        if score <= 0:
            continue
        scored.append((score, f))

    scored.sort(key=lambda x: (-x[0], str(x[1].get("id"))))
    return [
        {
            "field_id": str(f.get("id")),
            "label": _fix_mojibake_text(str(f.get("label", ""))),
            "type": f.get("type"),
            "score": float(score),
        }
        for score, f in scored[:top_k]
    ]


def build_fn_review_records(
    candidate_pool_obj: dict[str, Any],
    model_output: list[dict[str, Any]],
    effective_schema: dict[str, Any],
    top_k: int,
) -> list[dict[str, Any]]:
    candidates = candidate_pool_obj.get("candidates", [])
    memo_id = candidate_pool_obj.get("memo_id")
    effective_fields = effective_schema.get("effective_fields", [])
    records: list[dict[str, Any]] = []

    for c in candidates:
        matched = []
        for mf in model_output:
            if _candidate_matches_model(c, mf):
                fd = mf.get("field_definition") or {}
                matched.append(
                    {
                        "field_id": str(fd.get("id")) if fd.get("id") is not None else None,
                        "field_label": fd.get("label"),
                        "extracted_value": mf.get("extracted_value"),
                    }
                )

        if matched:
            continue

        suggestions = _suggest_fields(c, effective_fields, top_k=top_k)
        mentions = c.get("mentions") or []
        primary_mention = mentions[0] if mentions else {}

        records.append(
            {
                "memo_id": memo_id,
                "candidate_id": c.get("candidate_id"),
                "semantic_type": c.get("semantic_type"),
                "value_type": c.get("value_type"),
                "raw_text": c.get("raw_text"),
                "normalized": c.get("normalized"),
                "evidence": {
                    "segment_id": primary_mention.get("segment_id"),
                    "section_path": primary_mention.get("section_path"),
                    "exact_quote": primary_mention.get("exact_quote"),
                    "start_char": primary_mention.get("start_char"),
                    "end_char": primary_mention.get("end_char"),
                },
                "fn_candidate": True,
                "suggested_fields": suggestions,
                "qa_decision": None,
                "qa_notes": None,
            }
        )

    return records


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build human-QA FN review input from candidate_pool, model_output, and effective_schema."
    )
    p.add_argument("--candidate-pool", required=True, help="candidate_pool json/jsonl path")
    p.add_argument("--model-output", required=True, help="model output json/jsonl path")
    p.add_argument("--effective-schema", required=True, help="effective schema json path")
    p.add_argument("--output", required=True, help="Output path (.json or .jsonl)")
    p.add_argument("--top-k", type=int, default=5, help="Top-K suggested fields per FN candidate")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    candidate_raw = _read_json_or_jsonl(Path(args.candidate_pool))
    if isinstance(candidate_raw, list):
        if not candidate_raw:
            raise ValueError("candidate pool is empty")
        candidate_obj = candidate_raw[0]
    else:
        candidate_obj = candidate_raw

    model_raw = _read_json_or_jsonl(Path(args.model_output))
    model_facts = _flatten_model_output(model_raw)
    effective_schema = _read_json(Path(args.effective_schema))

    fn_records = build_fn_review_records(
        candidate_pool_obj=candidate_obj,
        model_output=model_facts,
        effective_schema=effective_schema,
        top_k=args.top_k,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".jsonl":
        with out_path.open("w", encoding="utf-8") as f:
            for row in fn_records:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    else:
        out_path.write_text(json.dumps(fn_records, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "output": str(out_path),
                "total_fn_candidates": len(fn_records),
                "total_model_facts": len(model_facts),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
