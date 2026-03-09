from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from agent_a.llm.client import MockLLMClient, make_llm_client
from agent_a.merge import merge_candidates, soft_to_candidates
from agent_a.rules.regex_extractors import extract_hard_candidates
from agent_a.schema import CandidatePoolLine, ExtractionMetadata, now_iso
from agent_a.segmenter import split_segments


def _load_jsonl(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows.append({"memo_id": obj["memo_id"], "text": obj["text"]})
    return rows


def _load_txt(path: Path, memo_id: str) -> list[dict[str, str]]:
    return [{"memo_id": memo_id, "text": path.read_text(encoding="utf-8")}]


def _resolve_output_path(args: argparse.Namespace, run_id: str) -> Path:
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        return out_path

    output_dir = Path(args.output_dir)
    run_name = args.run_name or run_id
    run_dir = output_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "candidate_pool.jsonl"


def run(args: argparse.Namespace) -> None:
    run_id = datetime.utcnow().strftime("RUN-%Y%m%d-%H%M%S")

    if args.input:
        memos = _load_jsonl(Path(args.input))
    else:
        memos = _load_txt(Path(args.input_txt), args.memo_id)

    llm_flag = not args.no_llm and bool(os.getenv("OPENAI_API_KEY"))
    llm_client = make_llm_client(llm_flag)

    out_path = _resolve_output_path(args, run_id)

    with out_path.open("w", encoding="utf-8") as w:
        for memo in memos:
            segments = split_segments(memo["text"])
            hard = extract_hard_candidates(segments)
            soft_raw = llm_client.extract_soft_candidates(segments)
            soft = soft_to_candidates(soft_raw, segments)
            merged = merge_candidates(hard + soft)

            line = CandidatePoolLine(
                run_id=run_id,
                memo_id=memo["memo_id"],
                candidates=merged,
                extraction_metadata=ExtractionMetadata(
                    llm_enabled=not isinstance(llm_client, MockLLMClient),
                    created_at=now_iso(),
                ),
            )
            w.write(line.model_dump_json(ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Agent A candidate pool extractor")
    p.add_argument("--input", help="Input memos.jsonl")
    p.add_argument("--input-txt", help="Input .txt memo for quick test")
    p.add_argument("--memo-id", default="M-001", help="memo_id for --input-txt")
    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument("--output", help="Output candidate_pool.jsonl file path")
    out.add_argument("--output-dir", help="Output root directory (creates <output-dir>/<run-name-or-run-id>/candidate_pool.jsonl)")
    p.add_argument("--run-name", help="Folder name under --output-dir. Default: run_id")
    p.add_argument("--no-llm", action="store_true", help="Skip LLM soft extraction")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.input and not args.input_txt:
        parser.error("Either --input or --input-txt is required")
    run(args)


if __name__ == "__main__":
    main()
