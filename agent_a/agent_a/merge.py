from __future__ import annotations

import json
import re
from hashlib import sha1
from typing import Any

from agent_a.schema import Candidate, Mention, Segment, SoftLLMCandidate


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _norm_signature(normalized: dict[str, Any] | None) -> str:
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True) if normalized is not None else "null"


def _hard_dedupe_payload(c: Candidate) -> dict[str, Any] | None:
    if c.normalized is None:
        return None
    payload = dict(c.normalized)
    # Currency dedupe should focus on value+currency; approx is merged via OR later.
    if c.value_type == "currency":
        payload.pop("approx", None)
    return payload


def _build_soft_mention(s: Segment, exact_quote: str) -> Mention | None:
    idx = s.text.find(exact_quote)
    if idx < 0:
        return None
    end = idx + len(exact_quote)
    return Mention(
        segment_id=s.segment_id,
        section_path=s.section_path,
        exact_quote=exact_quote,
        start_char=s.start_char + idx,
        end_char=s.start_char + end,
    )


def soft_to_candidates(soft: list[SoftLLMCandidate], segments: list[Segment]) -> list[Candidate]:
    seg_by_id = {s.segment_id: s for s in segments}
    out: list[Candidate] = []
    for item in soft:
        seg = seg_by_id.get(item.segment_id)
        if not seg:
            continue
        quote = item.exact_quote.strip() or item.raw_text.strip()
        mention = _build_soft_mention(seg, quote)
        if mention is None:
            continue
        norm = {"text": _norm_text(item.raw_text)}
        dedupe_key = f"{item.semantic_type}:{sha1(norm['text'].encode('utf-8')).hexdigest()[:16]}"
        out.append(
            Candidate(
                kind="soft",
                semantic_type=item.semantic_type,
                value_type=item.value_type,
                raw_text=item.raw_text,
                normalized=norm,
                mentions=[mention],
                dedupe_key=dedupe_key,
                confidence=item.confidence,
            )
        )
    return out


def merge_candidates(candidates: list[Candidate]) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for c in candidates:
        if c.kind == "hard":
            key = f"{c.semantic_type}:{sha1(_norm_signature(_hard_dedupe_payload(c)).encode('utf-8')).hexdigest()[:16]}"
        else:
            text = (c.normalized or {}).get("text", c.raw_text)
            key = f"{c.semantic_type}:{sha1(_norm_text(str(text)).encode('utf-8')).hexdigest()[:16]}"

        if key not in merged:
            c.dedupe_key = key
            merged[key] = c
            continue

        existing = merged[key]
        mention_keys = {
            (m.segment_id, m.start_char, m.end_char, m.exact_quote) for m in existing.mentions
        }
        for m in c.mentions:
            mk = (m.segment_id, m.start_char, m.end_char, m.exact_quote)
            if mk not in mention_keys:
                existing.mentions.append(m)
                mention_keys.add(mk)
        # Preserve "approx" if any merged candidate was approximate.
        if existing.value_type == "currency" and isinstance(existing.normalized, dict):
            existing_approx = bool(existing.normalized.get("approx"))
            incoming_approx = bool((c.normalized or {}).get("approx"))
            existing.normalized["approx"] = existing_approx or incoming_approx
        existing.confidence = max(existing.confidence, c.confidence)

    ordered = list(merged.values())
    for i, c in enumerate(ordered, start=1):
        c.candidate_id = f"C-{i:04d}"
    return ordered
