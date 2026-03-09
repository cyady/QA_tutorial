from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def run(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    queue_rows = [json.loads(x) for x in Path(args.queue).read_text(encoding="utf-8").splitlines() if x.strip()]

    queue_run_names = {row["run_name"] for row in queue_rows}
    non_queue = []
    for i in range(args.start, args.end + 1):
        run_name = f"w{i}"
        if run_name in queue_run_names:
            continue
        cp = Path(args.runs_root) / run_name / "candidate_pool.jsonl"
        mj = Path(args.structured_root) / run_name / "memos.jsonl"
        if cp.exists() and mj.exists():
            line = json.loads(cp.read_text(encoding="utf-8").splitlines()[0])
            text = json.loads(mj.read_text(encoding="utf-8").splitlines()[0]).get("text", "")
            non_queue.append(
                {
                    "run_name": run_name,
                    "memo_id": line.get("memo_id", ""),
                    "candidate_count": len(line.get("candidates", [])),
                    "text_length": len(text),
                    "reason_codes": [],
                    "candidate_pool_path": str(cp),
                    "structured_path": str(Path(args.structured_root) / run_name / "memo_structured.json"),
                    "memos_jsonl_path": str(mj),
                    "source": "non_queue",
                }
            )

    # queue stratified by major reasons
    by_reason: dict[str, list[dict]] = {}
    for row in queue_rows:
        row = dict(row)
        row["source"] = "queue"
        reasons = row.get("reason_codes") or ["NO_REASON"]
        primary = reasons[0]
        by_reason.setdefault(primary, []).append(row)

    queue_target = min(args.queue_size, len(queue_rows))
    selected_queue: list[dict] = []
    reason_keys = sorted(by_reason.keys())
    if reason_keys:
        per_bucket = max(1, queue_target // len(reason_keys))
        for key in reason_keys:
            bucket = by_reason[key]
            k = min(per_bucket, len(bucket))
            selected_queue.extend(rng.sample(bucket, k))
        if len(selected_queue) < queue_target:
            remaining = [r for r in queue_rows if r not in selected_queue]
            need = queue_target - len(selected_queue)
            if remaining:
                selected_queue.extend(rng.sample(remaining, min(need, len(remaining))))
        selected_queue = selected_queue[:queue_target]

    non_queue_target = max(0, args.size - len(selected_queue))
    selected_non_queue = rng.sample(non_queue, min(non_queue_target, len(non_queue)))

    selected = selected_queue + selected_non_queue
    rng.shuffle(selected)

    out_jsonl = Path(args.output_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as w:
        for row in selected:
            w.write(json.dumps(row, ensure_ascii=False) + "\n")

    out_csv = Path(args.output_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "run_name",
        "memo_id",
        "source",
        "candidate_count",
        "text_length",
        "reason_codes",
        "candidate_pool_path",
        "structured_path",
        "memos_jsonl_path",
    ]
    lines = [",".join(header)]
    for r in selected:
        values = [
            str(r.get("run_name", "")),
            str(r.get("memo_id", "")),
            str(r.get("source", "")),
            str(r.get("candidate_count", "")),
            str(r.get("text_length", "")),
            "|".join(r.get("reason_codes", [])),
            str(r.get("candidate_pool_path", "")),
            str(r.get("structured_path", "")),
            str(r.get("memos_jsonl_path", "")),
        ]
        safe = [v.replace('"', "''") for v in values]
        lines.append(",".join(f'\"{v}\"' for v in safe))
    out_csv.write_text("\n".join(lines), encoding="utf-8-sig")

    summary = {
        "selected": len(selected),
        "selected_queue": len(selected_queue),
        "selected_non_queue": len(selected_non_queue),
        "seed": args.seed,
    }
    if args.summary:
        sp = Path(args.summary)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Create fixed validation set from queue/non-queue")
    p.add_argument("--queue", default="outputs/llm_queue/queue.jsonl")
    p.add_argument("--runs-root", default="outputs/runs")
    p.add_argument("--structured-root", default="outputs/structured_runs")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--end", type=int, default=6000)
    p.add_argument("--size", type=int, default=100)
    p.add_argument("--queue-size", type=int, default=70)
    p.add_argument("--seed", type=int, default=20260221)
    p.add_argument("--output-jsonl", default="outputs/validation/fixed_100.jsonl")
    p.add_argument("--output-csv", default="outputs/validation/fixed_100.csv")
    p.add_argument("--summary", default="outputs/validation/fixed_100_summary.json")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
