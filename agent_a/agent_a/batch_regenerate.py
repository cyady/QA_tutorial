from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from agent_a.memo_to_json import build_memo_json
from agent_a.merge import merge_candidates
from agent_a.rules.regex_extractors import extract_hard_candidates
from agent_a.schema import CandidatePoolLine, ExtractionMetadata, now_iso
from agent_a.segmenter import split_segments


def run(args: argparse.Namespace) -> None:
    data_root = Path(args.data_root)
    structured_root = Path(args.structured_root)
    runs_root = Path(args.runs_root)
    structured_root.mkdir(parents=True, exist_ok=True)
    runs_root.mkdir(parents=True, exist_ok=True)

    run_id = datetime.utcnow().strftime("RUN-%Y%m%d-%H%M%S")
    done = 0
    missing: list[int] = []

    for i in range(args.start, args.end + 1):
        src = data_root / f"memo_w{i}.txt"
        if not src.exists():
            missing.append(i)
            continue

        text = src.read_text(encoding="utf-8")
        memo_id = f"M-W{i}"
        run_name = f"w{i}"

        sdir = structured_root / run_name
        rdir = runs_root / run_name
        sdir.mkdir(parents=True, exist_ok=True)
        rdir.mkdir(parents=True, exist_ok=True)

        structured = build_memo_json(memo_id, text)
        (sdir / "memo_structured.json").write_text(
            json.dumps(structured, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (sdir / "memos.jsonl").write_text(
            json.dumps({"memo_id": memo_id, "text": text}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        segments = split_segments(text)
        hard = extract_hard_candidates(segments)
        merged = merge_candidates(hard)

        line = CandidatePoolLine(
            run_id=run_id,
            memo_id=memo_id,
            candidates=merged,
            extraction_metadata=ExtractionMetadata(
                llm_enabled=False,
                created_at=now_iso(),
            ),
        )
        (rdir / "candidate_pool.jsonl").write_text(
            line.model_dump_json(ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        done += 1

    summary = {"done": done, "missing": len(missing), "start": args.start, "end": args.end}
    if args.summary:
        sp = Path(args.summary)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Batch regenerate structured/candidate outputs from data_w memo txt files")
    p.add_argument("--data-root", default="data_w")
    p.add_argument("--structured-root", default="outputs/structured_runs")
    p.add_argument("--runs-root", default="outputs/runs")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--end", type=int, default=6000)
    p.add_argument("--summary", default="outputs/reports/regenerate_summary.json")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
