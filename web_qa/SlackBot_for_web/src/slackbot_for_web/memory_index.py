from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from slackbot_for_web.config import Settings, load_settings

INDEX_SCHEMA_VERSION = 3
HASH_BACKEND = "hash_char_ngram_v1"
SENTENCE_TRANSFORMERS_BACKEND = "sentence_transformers"
HASH_VECTOR_DIMENSIONS = 384
HASH_NGRAM_RANGE = (2, 4)
DEFAULT_RETRIEVAL_TOP_K = 5
DEFAULT_QUERY_INSTRUCTION = "Retrieve the most relevant past web QA issue memory cards for the current QA query."
DEFAULT_COMPARE_QUERY_SET: list[dict[str, Any]] = [
    {
        "query_id": "Q01",
        "text": "\uc2a4\ud06c\ub864\uc744 \uc704\uc544\ub798\ub85c \uc6c0\uc9c1\uc774\uba74 \uc560\ub2c8\uba54\uc774\uc158\uc774 \ub2e4\uc2dc \uc7ac\uc0dd\ub429\ub2c8\ub2e4.",
        "expected_issue_types": ["animation_replay"],
    },
    {
        "query_id": "Q02",
        "text": "\uc2a4\ud06c\ub864 \uacbd\uacc4\uc5d0\uc11c \uc560\ub2c8\uba54\uc774\uc158\uc774 \uacc4\uc18d \uae5c\ube61\uc785\ub2c8\ub2e4.",
        "expected_issue_types": ["flicker"],
    },
    {
        "query_id": "Q03",
        "text": "\ubaa8\ubc14\uc77c\uc5d0\uc11c \uae00\uc790 \uc704 \ub3c4\ud2b8 \uc815\ub82c\uc774 \ub9de\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.",
        "expected_issue_types": ["mobile_alignment"],
    },
    {
        "query_id": "Q04",
        "text": "\uce74\ub4dc \ud14d\uc2a4\ud2b8 \uc904\ubc14\uafc8\uc774 \ubd80\uc790\uc5f0\uc2a4\ub7fd\uace0 \uac00\ub3c5\uc131\uc774 \ub5a8\uc5b4\uc9d1\ub2c8\ub2e4.",
        "expected_issue_types": ["text_wrap"],
    },
    {
        "query_id": "Q05",
        "text": "\uacf5\uc720 \ub9c1\ud06c \ubbf8\ub9ac\ubcf4\uae30\uc5d0 \ub300\ud45c \uc774\ubbf8\uc9c0\uac00 \ubcf4\uc774\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.",
        "expected_issue_types": ["share_preview"],
    },
    {
        "query_id": "Q06",
        "text": "\ubaa8\ubc14\uc77c\uc5d0\uc11c \ud50c\ub85c\ud305 CTA \ud3fc\uc774 \ubc30\uacbd \uc544\ub798 depth\ub85c \uae54\ub9bd\ub2c8\ub2e4.",
        "expected_issue_types": ["mobile_overlay_depth"],
    },
    {
        "query_id": "Q07",
        "text": "\ubaa8\ubc14\uc77c\uc5d0\uc11c \ub3d9\uc601\uc0c1 \ud50c\ub808\uc774\uc5b4 \uc774\ubbf8\uc9c0\uac00 \uc5ec\ub7ec \uc7a5 \uacb9\uccd0 \ubcf4\uc785\ub2c8\ub2e4.",
        "expected_issue_types": ["mobile_media_render"],
    },
    {
        "query_id": "Q08",
        "text": "\uc6f9\uacfc \ubaa8\ubc14\uc77c\uc758 \ub9d0\ud48d\uc120 \uc0c1\ud558 \uc5ec\ubc31\uc774 \uc11c\ub85c \ub2e4\ub985\ub2c8\ub2e4.",
        "expected_issue_types": ["spacing_layout"],
    },
    {
        "query_id": "Q09",
        "text": "\ud0dc\ube14\ub9bf \ubdf0\uc5d0\uc11c \uac00\uc7a5 \ud558\ub2e8 \ub85c\uace0\uac00 \uc67c\ucabd\uc73c\ub85c \uc3e0\ub9bd\ub2c8\ub2e4.",
        "expected_issue_types": ["footer_alignment", "mobile_alignment"],
    },
    {
        "query_id": "Q10",
        "text": "\ubc30\uacbd\uacfc \uc560\ub2c8\uba54\uc774\uc158\uc774 \ubc84\ubc85\uc774\uace0 \uc774\uc0c1\ud558\uac8c \uc6c0\uc9c1\uc785\ub2c8\ub2e4.",
        "expected_issue_types": ["performance_motion"],
    },
]
_MODEL_CACHE: dict[str, Any] = {}


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="Build/query local vector memory index for Slack QA issue cards.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build local vector index from issue_memory_cards.json files")
    build_parser.add_argument("--memory-id", help="Build index from a single memory archive only")
    build_parser.add_argument("--backend", help="Embedding backend override")
    build_parser.add_argument("--model", help="Embedding model override")

    query_parser = subparsers.add_parser("query", help="Query local vector index")
    query_parser.add_argument("--text", required=True, help="Query text")
    query_parser.add_argument("--platform", help="Optional platform hint")
    query_parser.add_argument("--top-k", type=int, default=DEFAULT_RETRIEVAL_TOP_K)
    query_parser.add_argument("--backend", help="Embedding backend override")
    query_parser.add_argument("--model", help="Embedding model override")

    compare_parser = subparsers.add_parser("compare", help="Compare embedding models on the same benchmark query set")
    compare_parser.add_argument("--top-k", type=int, default=DEFAULT_RETRIEVAL_TOP_K)
    compare_parser.add_argument("--models", nargs="+", help="Model names to compare")
    compare_parser.add_argument("--queries-file", help="Optional JSON file with benchmark queries")
    compare_parser.add_argument("--memory-id", help="Optional single memory archive restriction")

    args = parser.parse_args()
    settings = _load_runtime_settings()

    if args.command == "build":
        payload = build_local_memory_index(
            settings=settings,
            memory_id=args.memory_id,
            backend=args.backend,
            model_name=args.model,
        )
        print(
            f"index_built backend={payload['backend']} model={payload.get('model_name') or '-'} "
            f"cards={payload['card_count']} memories={len(payload['source_memory_ids'])} path={payload['index_path']}"
        )
        return

    if args.command == "query":
        result = retrieve_issue_memory_cards(
            settings=settings,
            query_text=str(args.text or ""),
            top_k=max(1, int(args.top_k or DEFAULT_RETRIEVAL_TOP_K)),
            platform_hint=str(args.platform or "").strip() or None,
            backend=args.backend,
            model_name=args.model,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    compare_payload = compare_embedding_models(
        settings=settings,
        model_names=args.models or list(settings.memory_compare_models),
        top_k=max(1, int(args.top_k or DEFAULT_RETRIEVAL_TOP_K)),
        queries=_load_benchmark_queries(args.queries_file),
        memory_id=args.memory_id,
    )
    print(json.dumps(compare_payload, ensure_ascii=False, indent=2))


def build_local_memory_index(
    settings: Settings,
    memory_id: str | None = None,
    *,
    backend: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    selected_backend = _resolve_backend(settings, backend)
    selected_model = _resolve_model_name(settings, selected_backend, model_name)
    cards = _collect_cards(settings=settings, memory_id=memory_id)
    index_root = _memory_index_root(settings)
    index_root.mkdir(parents=True, exist_ok=True)
    index_path = _memory_index_path(settings, backend=selected_backend, model_name=selected_model)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    vector_texts = [str(card.get("vector_text", "") or "").strip() for card in cards]
    if selected_backend == SENTENCE_TRANSFORMERS_BACKEND:
        embeddings = _embed_texts_with_sentence_transformers(vector_texts, selected_model, kind="document")
        dimensions = len(embeddings[0]) if embeddings else 0
    else:
        embeddings = [_hash_embed_text(vector_text) for vector_text in vector_texts]
        dimensions = HASH_VECTOR_DIMENSIONS

    records: list[dict[str, Any]] = []
    source_memory_ids: list[str] = []
    seen_memory_ids: set[str] = set()
    for card, embedding, vector_text in zip(cards, embeddings, vector_texts):
        memory_ref = str(card.get("memory_id", "")).strip()
        if memory_ref and memory_ref not in seen_memory_ids:
            source_memory_ids.append(memory_ref)
            seen_memory_ids.add(memory_ref)
        records.append(
            {
                "card_id": str(card.get("card_id", "")).strip(),
                "memory_id": memory_ref,
                "thread_key": str(card.get("thread_key", "")).strip(),
                "source_message_ts": str(card.get("source_message_ts", "")).strip(),
                "dedupe_key": str(card.get("dedupe_key", "")).strip(),
                "issue_types": _safe_str_list(card.get("issue_types"), limit=12),
                "platform": str(card.get("platform", "")).strip(),
                "section_hint": str(card.get("section_hint", "")).strip(),
                "page_roles": _safe_str_list(card.get("page_roles"), limit=8),
                "component_types": _safe_str_list(card.get("component_types"), limit=12),
                "interaction_kinds": _safe_str_list(card.get("interaction_kinds"), limit=12),
                "layout_signals": _safe_str_list(card.get("layout_signals"), limit=12),
                "framework_hints": _safe_str_list(card.get("framework_hints"), limit=8),
                "pattern_tags": _safe_str_list(card.get("pattern_tags"), limit=24),
                "summary": str(card.get("summary", "")).strip(),
                "observation": str(card.get("observation", "")).strip(),
                "expected_behavior": str(card.get("expected_behavior", "")).strip(),
                "keywords": _safe_str_list(card.get("keywords"), limit=20),
                "severity_hint": str(card.get("severity_hint", "")).strip(),
                "evidence_refs": card.get("evidence_refs") if isinstance(card.get("evidence_refs"), list) else [],
                "vector_text": vector_text,
                "embedding": embedding,
            }
        )

    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "backend": selected_backend,
        "model_name": selected_model,
        "dimensions": dimensions,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "card_count": len(records),
        "source_memory_ids": source_memory_ids,
        "records": records,
    }
    if selected_backend == HASH_BACKEND:
        payload["ngram_range"] = list(HASH_NGRAM_RANGE)
    index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "index_path": str(index_path),
        "backend": selected_backend,
        "model_name": selected_model,
        "card_count": len(records),
        "source_memory_ids": source_memory_ids,
    }


def retrieve_issue_memory_cards(
    settings: Settings,
    query_text: str,
    *,
    top_k: int = DEFAULT_RETRIEVAL_TOP_K,
    platform_hint: str | None = None,
    page_role_hints: list[str] | None = None,
    component_type_hints: list[str] | None = None,
    interaction_kind_hints: list[str] | None = None,
    layout_signal_hints: list[str] | None = None,
    framework_hints: list[str] | None = None,
    backend: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    selected_backend = _resolve_backend(settings, backend)
    selected_model = _resolve_model_name(settings, selected_backend, model_name)
    try:
        index = _load_or_build_index(settings, backend=selected_backend, model_name=selected_model)
        if not index:
            return _empty_result(selected_backend, selected_model, query_text, top_k, reason="no_index")
        query_vector = _embed_query_text(query_text, backend=selected_backend, model_name=selected_model)
    except Exception as exc:  # noqa: BLE001
        if selected_backend != HASH_BACKEND:
            fallback = retrieve_issue_memory_cards(
                settings=settings,
                query_text=query_text,
                top_k=top_k,
                platform_hint=platform_hint,
                page_role_hints=page_role_hints,
                component_type_hints=component_type_hints,
                interaction_kind_hints=interaction_kind_hints,
                layout_signal_hints=layout_signal_hints,
                framework_hints=framework_hints,
                backend=HASH_BACKEND,
                model_name="",
            )
            fallback["requested_backend"] = selected_backend
            fallback["requested_model_name"] = selected_model
            fallback["fallback_reason"] = str(exc)
            return fallback
        return _empty_result(selected_backend, selected_model, query_text, top_k, reason=str(exc))

    if not any(query_vector):
        return _empty_result(selected_backend, selected_model, query_text, top_k, reason="empty_query")

    platform_hint_norm = str(platform_hint or "").strip().lower()
    page_role_hint_list = _normalize_hint_list(page_role_hints, limit=8)
    component_type_hint_list = _normalize_hint_list(component_type_hints, limit=12)
    interaction_kind_hint_list = _normalize_hint_list(interaction_kind_hints, limit=12)
    layout_signal_hint_list = _normalize_hint_list(layout_signal_hints, limit=12)
    framework_hint_list = _normalize_hint_list(framework_hints, limit=8)
    scored: list[dict[str, Any]] = []
    for record in index.get("records", []):
        if not isinstance(record, dict):
            continue
        embedding = record.get("embedding")
        if not isinstance(embedding, list):
            continue
        base_score = _cosine_similarity(query_vector, embedding)
        boost_breakdown = {
            "platform": 0.0,
            "page_roles": 0.0,
            "component_types": 0.0,
            "interaction_kinds": 0.0,
            "layout_signals": 0.0,
            "framework_hints": 0.0,
        }
        score = base_score
        if platform_hint_norm and str(record.get("platform", "")).strip().lower() == platform_hint_norm:
            boost_breakdown["platform"] = 0.03
            score += boost_breakdown["platform"]
        boost_breakdown["page_roles"] = _score_hint_overlap(
            page_role_hint_list,
            record.get("page_roles"),
            per_match=0.05,
            max_boost=0.12,
        )
        boost_breakdown["component_types"] = _score_hint_overlap(
            component_type_hint_list,
            record.get("component_types"),
            per_match=0.04,
            max_boost=0.12,
        )
        boost_breakdown["interaction_kinds"] = _score_hint_overlap(
            interaction_kind_hint_list,
            record.get("interaction_kinds"),
            per_match=0.035,
            max_boost=0.1,
        )
        boost_breakdown["layout_signals"] = _score_hint_overlap(
            layout_signal_hint_list,
            record.get("layout_signals"),
            per_match=0.03,
            max_boost=0.09,
        )
        boost_breakdown["framework_hints"] = _score_hint_overlap(
            framework_hint_list,
            record.get("framework_hints"),
            per_match=0.04,
            max_boost=0.08,
        )
        metadata_boost = round(sum(boost_breakdown.values()), 4)
        score += metadata_boost
        if score <= 0:
            continue
        scored.append(
            {
                "card_id": str(record.get("card_id", "")).strip(),
                "memory_id": str(record.get("memory_id", "")).strip(),
                "score": round(score, 4),
                "base_score": round(base_score, 4),
                "metadata_boost": metadata_boost,
                "summary": str(record.get("summary", "")).strip(),
                "issue_types": _safe_str_list(record.get("issue_types"), limit=12),
                "platform": str(record.get("platform", "")).strip(),
                "section_hint": str(record.get("section_hint", "")).strip(),
                "page_roles": _safe_str_list(record.get("page_roles"), limit=8),
                "component_types": _safe_str_list(record.get("component_types"), limit=12),
                "interaction_kinds": _safe_str_list(record.get("interaction_kinds"), limit=12),
                "layout_signals": _safe_str_list(record.get("layout_signals"), limit=12),
                "framework_hints": _safe_str_list(record.get("framework_hints"), limit=8),
                "pattern_tags": _safe_str_list(record.get("pattern_tags"), limit=24),
                "severity_hint": str(record.get("severity_hint", "")).strip(),
                "source_message_ts": str(record.get("source_message_ts", "")).strip(),
                "evidence_count": len(record.get("evidence_refs") or []),
                "observation": str(record.get("observation", "")).strip(),
                "expected_behavior": str(record.get("expected_behavior", "")).strip(),
                "score_breakdown": {key: round(value, 4) for key, value in boost_breakdown.items()},
            }
        )

    scored.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item.get("card_id") or "")))
    hits = scored[: max(1, int(top_k or DEFAULT_RETRIEVAL_TOP_K))]
    issue_type_counter: Counter[str] = Counter()
    for hit in hits:
        for issue_type in _safe_str_list(hit.get("issue_types"), limit=12):
            issue_type_counter[issue_type] += 1

    return {
        "enabled": True,
        "backend": str(index.get("backend", selected_backend)).strip(),
        "model_name": str(index.get("model_name", selected_model)).strip(),
        "query_text": query_text,
        "query_hints": {
            "platform": platform_hint_norm,
            "page_roles": page_role_hint_list,
            "component_types": component_type_hint_list,
            "interaction_kinds": interaction_kind_hint_list,
            "layout_signals": layout_signal_hint_list,
            "framework_hints": framework_hint_list,
        },
        "top_k": max(1, int(top_k or DEFAULT_RETRIEVAL_TOP_K)),
        "total_hits": len(hits),
        "issue_type_counts": dict(issue_type_counter.most_common()),
        "hits": hits,
        "index_stats": {
            "card_count": int(index.get("card_count") or 0),
            "source_memory_ids": _safe_str_list(index.get("source_memory_ids"), limit=1000),
        },
    }


def compare_embedding_models(
    *,
    settings: Settings,
    model_names: list[str],
    top_k: int,
    queries: list[dict[str, Any]],
    memory_id: str | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for model_name in model_names:
        try:
            build_local_memory_index(
                settings=settings,
                memory_id=memory_id,
                backend=SENTENCE_TRANSFORMERS_BACKEND,
                model_name=model_name,
            )
            per_query: list[dict[str, Any]] = []
            top1_hits = 0
            top3_hits = 0
            mrr_total = 0.0
            for query in queries:
                query_text = str(query.get("text", "")).strip()
                expected_issue_types = _safe_str_list(query.get("expected_issue_types"), limit=8)
                retrieval = retrieve_issue_memory_cards(
                    settings=settings,
                    query_text=query_text,
                    top_k=top_k,
                    backend=SENTENCE_TRANSFORMERS_BACKEND,
                    model_name=model_name,
                )
                hits = _safe_obj_list(retrieval.get("hits"), limit=top_k)
                top1_match = _hit_matches_expected(hits[:1], expected_issue_types)
                top3_match = _hit_matches_expected(hits[:3], expected_issue_types)
                rank = _first_matching_rank(hits, expected_issue_types)
                if top1_match:
                    top1_hits += 1
                if top3_match:
                    top3_hits += 1
                if rank > 0:
                    mrr_total += 1.0 / rank
                per_query.append(
                    {
                        "query_id": str(query.get("query_id", "")).strip(),
                        "text": query_text,
                        "expected_issue_types": expected_issue_types,
                        "top1_match": top1_match,
                        "top3_match": top3_match,
                        "first_match_rank": rank or None,
                        "top_hits": [
                            {
                                "card_id": str(hit.get("card_id", "")).strip(),
                                "score": float(hit.get("score") or 0.0),
                                "issue_types": _safe_str_list(hit.get("issue_types"), limit=12),
                                "summary": str(hit.get("summary", "")).strip(),
                            }
                            for hit in hits[:3]
                        ],
                    }
                )
            query_count = len(queries) or 1
            results.append(
                {
                    "backend": SENTENCE_TRANSFORMERS_BACKEND,
                    "model_name": model_name,
                    "status": "ok",
                    "query_count": len(queries),
                    "metrics": {
                        "top1_accuracy": round(top1_hits / query_count, 4),
                        "top3_accuracy": round(top3_hits / query_count, 4),
                        "mrr": round(mrr_total / query_count, 4),
                    },
                    "queries": per_query,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "backend": SENTENCE_TRANSFORMERS_BACKEND,
                    "model_name": model_name,
                    "status": "error",
                    "error": str(exc),
                    "query_count": len(queries),
                    "metrics": {
                        "top1_accuracy": 0.0,
                        "top3_accuracy": 0.0,
                        "mrr": 0.0,
                    },
                    "queries": [],
                }
            )

    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backend": SENTENCE_TRANSFORMERS_BACKEND,
        "models": results,
        "query_set": queries,
    }
    report_path = _memory_index_root(settings) / f"benchmark_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["report_path"] = str(report_path)
    return payload


def _load_runtime_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    return load_settings(require_slack_tokens=False)


def _load_benchmark_queries(queries_file: str | None) -> list[dict[str, Any]]:
    if not queries_file:
        return list(DEFAULT_COMPARE_QUERY_SET)
    path = Path(queries_file).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Invalid benchmark query file: {path}")
    return [item for item in payload if isinstance(item, dict)]


def _collect_cards(settings: Settings, memory_id: str | None = None) -> list[dict[str, Any]]:
    memory_root = Path(settings.artifact_root) / "_memory"
    targets: list[Path] = []
    if memory_id:
        targets = [memory_root / str(memory_id).strip()]
    elif memory_root.exists():
        targets = sorted(
            [path for path in memory_root.iterdir() if path.is_dir() and path.name.startswith("MEM-")],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    cards: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for directory in targets:
        cards_path = directory / "issue_memory_cards.json"
        if not cards_path.exists():
            continue
        try:
            payload = json.loads(cards_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        raw_cards = payload.get("cards")
        if not isinstance(raw_cards, list):
            continue
        for card in raw_cards:
            if not isinstance(card, dict):
                continue
            dedupe_key = str(card.get("dedupe_key") or "").strip()
            if not dedupe_key:
                thread_key = str(card.get("thread_key") or "").strip()
                source_message_ts = str(card.get("source_message_ts") or "").strip()
                dedupe_key = f"{thread_key}:{source_message_ts}"
            if not dedupe_key or dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            cards.append(card)
    cards.reverse()
    return cards


def _memory_index_root(settings: Settings) -> Path:
    return Path(settings.artifact_root) / "_runtime" / "vector_memory"


def _memory_index_path(settings: Settings, *, backend: str, model_name: str) -> Path:
    slug = _index_slug(backend=backend, model_name=model_name)
    return _memory_index_root(settings) / slug / "issue_memory_index.json"


def _load_or_build_index(settings: Settings, *, backend: str, model_name: str) -> dict[str, Any] | None:
    index_path = _memory_index_path(settings, backend=backend, model_name=model_name)
    if not index_path.exists():
        build_local_memory_index(settings, backend=backend, model_name=model_name)
    if not index_path.exists():
        return None
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version") or 0) < INDEX_SCHEMA_VERSION:
        build_local_memory_index(settings, backend=backend, model_name=model_name)
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(payload, dict):
            return None
    return payload


def _resolve_backend(settings: Settings, override: str | None) -> str:
    value = str(override or settings.memory_embedding_backend or HASH_BACKEND).strip().lower()
    if value in {HASH_BACKEND, "hash", "hash_char_ngram"}:
        return HASH_BACKEND
    if value in {SENTENCE_TRANSFORMERS_BACKEND, "st", "hf"}:
        return SENTENCE_TRANSFORMERS_BACKEND
    return HASH_BACKEND


def _resolve_model_name(settings: Settings, backend: str, override: str | None) -> str:
    if backend == HASH_BACKEND:
        return ""
    value = str(override or settings.memory_embedding_model or "").strip()
    return value or "intfloat/multilingual-e5-large-instruct"


def _index_slug(*, backend: str, model_name: str) -> str:
    raw = backend if backend == HASH_BACKEND else f"{backend}_{model_name}"
    sanitized = re_sub_non_filename(raw.lower())
    return sanitized.strip("_") or "default"


def re_sub_non_filename(raw: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in _normalize_unicode(raw))


def _embed_query_text(query_text: str, *, backend: str, model_name: str) -> list[float]:
    normalized = _normalize_for_vector(query_text)
    if not normalized:
        return []
    if backend == SENTENCE_TRANSFORMERS_BACKEND:
        return _embed_texts_with_sentence_transformers([normalized], model_name, kind="query")[0]
    return _hash_embed_text(normalized)


def _embed_texts_with_sentence_transformers(texts: list[str], model_name: str, *, kind: str) -> list[list[float]]:
    if not texts:
        return []
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("sentence-transformers is not installed") from exc

    normalized_texts = [_prepare_text_for_model(text, model_name=model_name, kind=kind) for text in texts]
    model = _MODEL_CACHE.get(model_name)
    if model is None:
        model = SentenceTransformer(model_name, trust_remote_code=True)
        _MODEL_CACHE[model_name] = model
    embeddings = model.encode(
        normalized_texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
        batch_size=min(16, max(1, len(normalized_texts))),
    )
    return [[round(float(value), 6) for value in row.tolist()] for row in embeddings]


def _prepare_text_for_model(text: str, *, model_name: str, kind: str) -> str:
    normalized = _normalize_for_vector(text)
    lower_name = model_name.lower()
    if kind == "query" and "multilingual-e5" in lower_name and "instruct" in lower_name:
        return f"Instruct: {DEFAULT_QUERY_INSTRUCTION}\nQuery: {normalized}"
    return normalized


def _empty_result(backend: str, model_name: str, query_text: str, top_k: int, *, reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "backend": backend,
        "model_name": model_name,
        "query_text": query_text,
        "top_k": top_k,
        "total_hits": 0,
        "issue_type_counts": {},
        "hits": [],
        "reason": reason,
    }


def _hit_matches_expected(hits: list[dict[str, Any]], expected_issue_types: list[str]) -> bool:
    expected = {issue_type.strip() for issue_type in expected_issue_types if issue_type.strip()}
    if not expected:
        return False
    for hit in hits:
        actual = set(_safe_str_list(hit.get("issue_types"), limit=12))
        if expected.intersection(actual):
            return True
    return False


def _first_matching_rank(hits: list[dict[str, Any]], expected_issue_types: list[str]) -> int:
    expected = {issue_type.strip() for issue_type in expected_issue_types if issue_type.strip()}
    if not expected:
        return 0
    for index, hit in enumerate(hits, start=1):
        actual = set(_safe_str_list(hit.get("issue_types"), limit=12))
        if expected.intersection(actual):
            return index
    return 0


def _hash_embed_text(text: str) -> list[float]:
    source = _normalize_for_vector(text)
    if not source:
        return [0.0] * HASH_VECTOR_DIMENSIONS

    values = [0.0] * HASH_VECTOR_DIMENSIONS
    for ngram in _iter_char_ngrams(source, HASH_NGRAM_RANGE[0], HASH_NGRAM_RANGE[1]):
        digest = hashlib.blake2b(ngram.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "little", signed=False) % HASH_VECTOR_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        values[bucket] += sign

    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return [0.0] * HASH_VECTOR_DIMENSIONS
    return [round(value / norm, 6) for value in values]


def _iter_char_ngrams(text: str, min_n: int, max_n: int) -> list[str]:
    cleaned = text.replace("\n", " ").strip()
    ngrams: list[str] = []
    length = len(cleaned)
    for n in range(min_n, max_n + 1):
        if length < n:
            continue
        for index in range(0, length - n + 1):
            chunk = cleaned[index : index + n]
            if not chunk.strip():
                continue
            ngrams.append(chunk)
    return ngrams


def _normalize_for_vector(text: str) -> str:
    normalized = _normalize_unicode(text).lower()
    return " ".join(normalized.split())


def _normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", str(text or ""))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _normalize_hint_list(value: list[str] | None, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _normalize_for_vector(str(item or ""))
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
        if len(normalized) >= limit:
            break
    return normalized


def _score_hint_overlap(hints: list[str], record_values: Any, *, per_match: float, max_boost: float) -> float:
    if not hints or not isinstance(record_values, list):
        return 0.0
    record_set = {_normalize_for_vector(str(item or "")) for item in record_values if _normalize_for_vector(str(item or ""))}
    if not record_set:
        return 0.0
    match_count = len([hint for hint in hints if hint in record_set])
    if match_count <= 0:
        return 0.0
    return min(max_boost, round(match_count * per_match, 4))


def _safe_obj_list(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
        if len(out) >= limit:
            break
    return out


def _safe_str_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _configure_stdout() -> None:
    stream = getattr(sys, "stdout", None)
    if stream is None:
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return


if __name__ == "__main__":
    main()
