from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TARGET_SOFT_TYPES = {
    "action_item",
    "constraint",
    "risk_or_concern",
    "collaboration_need",
    "kpi_definition",
    "deliverable_scope",
    "stakeholder_or_team",
}


@dataclass
class QueueItem:
    run_name: str
    memo_id: str
    candidate_count: int
    text_length: int
    reason_codes: list[str]
    candidate_pool_path: str
    structured_path: str
    memos_jsonl_path: str


def _load_candidate_line(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    return json.loads(lines[0])


def _load_memo_text_length(memos_jsonl_path: Path) -> int:
    if not memos_jsonl_path.exists():
        return 0
    line = memos_jsonl_path.read_text(encoding="utf-8").splitlines()[0]
    return len(json.loads(line).get("text", ""))


def _reason_codes(candidates: list[dict[str, Any]], text_length: int) -> list[str]:
    reasons: list[str] = []
    count = len(candidates)
    if count <= 2:
        reasons.append("LOW_CANDIDATE_COUNT")

    sem_types = [c.get("semantic_type") for c in candidates]
    soft_hits = sum(1 for s in sem_types if s in TARGET_SOFT_TYPES)
    if soft_hits == 0:
        reasons.append("NO_SOFT_SEMANTIC_TYPES")

    other_count = sum(1 for s in sem_types if s == "other")
    if count > 0 and (other_count / count) >= 0.6:
        reasons.append("HIGH_OTHER_RATIO")

    if text_length >= 400 and count <= 5:
        reasons.append("LONG_TEXT_LOW_COVERAGE")

    value_types = {c.get("value_type") for c in candidates}
    if value_types and value_types.issubset({"email", "text"}) and count <= 3:
        reasons.append("TEXT_ONLY_OUTPUT")

    return reasons


def build_queue(
    runs_root: Path,
    structured_root: Path,
    *,
    start: int,
    end: int,
    sample_size: int,
    seed: int,
) -> tuple[list[QueueItem], dict[str, int]]:
    queue: list[QueueItem] = []

    for i in range(start, end + 1):
        run_name = f"w{i}"
        candidate_path = runs_root / run_name / "candidate_pool.jsonl"
        structured_path = structured_root / run_name / "memo_structured.json"
        memos_jsonl_path = structured_root / run_name / "memos.jsonl"

        line = _load_candidate_line(candidate_path)
        if line is None:
            continue

        cands = line.get("candidates", [])
        text_length = _load_memo_text_length(memos_jsonl_path)
        reasons = _reason_codes(cands, text_length)
        if not reasons:
            continue

        queue.append(
            QueueItem(
                run_name=run_name,
                memo_id=line.get("memo_id", ""),
                candidate_count=len(cands),
                text_length=text_length,
                reason_codes=reasons,
                candidate_pool_path=str(candidate_path),
                structured_path=str(structured_path),
                memos_jsonl_path=str(memos_jsonl_path),
            )
        )

    reason_hist: dict[str, int] = {}
    for item in queue:
        for r in item.reason_codes:
            reason_hist[r] = reason_hist.get(r, 0) + 1

    if sample_size > 0 and len(queue) > sample_size:
        rng = random.Random(seed)
        queue = rng.sample(queue, sample_size)

    return queue, reason_hist


def run(args: argparse.Namespace) -> None:
    queue, reason_hist = build_queue(
        Path(args.runs_root),
        Path(args.structured_root),
        start=args.start,
        end=args.end,
        sample_size=args.sample_size,
        seed=args.seed,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as w:
        for item in queue:
            w.write(json.dumps(item.__dict__, ensure_ascii=False) + "\n")

    report = {
        "queue_size": len(queue),
        "reason_hist": reason_hist,
        "range": {"start": args.start, "end": args.end},
    }
    if args.report:
        rpath = Path(args.report)
        rpath.parent.mkdir(parents=True, exist_ok=True)
        rpath.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Select memos requiring LLM augmentation")
    p.add_argument("--runs-root", default="outputs/runs", help="Root directory of candidate_pool runs")
    p.add_argument("--structured-root", default="outputs/structured_runs", help="Root directory of structured runs")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--end", type=int, default=6000)
    p.add_argument("--output", default="outputs/llm_queue/queue.jsonl")
    p.add_argument("--report", default="outputs/llm_queue/report.json")
    p.add_argument("--sample-size", type=int, default=0, help="Optional random sample size from selected queue")
    p.add_argument("--seed", type=int, default=42)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
