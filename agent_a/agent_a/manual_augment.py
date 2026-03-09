from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from agent_a.merge import merge_candidates
from agent_a.schema import Candidate, Mention
from agent_a.segmenter import split_segments

ACTION_CUES = re.compile(r"(요청|진행|수립|확정|검토|발송|회신|필요)")
RISK_CUES = re.compile(r"(우려|문제|리스크|어렵|불가|미비|부재)")
COLLAB_CUES = re.compile(r"(협업|협의|공유|전달|연계|도입|필요|희망)")
CONSTRAINT_CUES = re.compile(r"(제한|불가|컴플라이언스|승인|결재|예산 없음|미정)")
KPI_CUES = re.compile(r"(KPI|전환율|성과|목표|MQL|SQL|SDR)", re.IGNORECASE)
DELIVERABLE_CUES = re.compile(r"(제안서|리포트|교육|콘텐츠|웹사이트|리뉴얼|뉴스레터|블로그|챗봇)")


def _soft_mention(segment_id: str, section_path: list[str], text: str, start: int, end: int) -> Mention:
    return Mention(
        segment_id=segment_id,
        section_path=section_path,
        exact_quote=text[start:end],
        start_char=start,
        end_char=end,
    )


def _semantic_for_line(line: str) -> str | None:
    if ACTION_CUES.search(line):
        return "action_item"
    if RISK_CUES.search(line):
        return "risk_or_concern"
    if CONSTRAINT_CUES.search(line):
        return "constraint"
    if KPI_CUES.search(line):
        return "kpi_definition"
    if DELIVERABLE_CUES.search(line):
        return "deliverable_scope"
    if COLLAB_CUES.search(line):
        return "collaboration_need"
    return None


def manual_soft_candidates(memo_text: str) -> list[Candidate]:
    out: list[Candidate] = []
    segments = split_segments(memo_text)

    for seg in segments:
        seg_start = seg.start_char
        for m in re.finditer(r"(?m)^\s*(.+?)\s*$", seg.text):
            line = m.group(1).strip()
            if not line or len(line) < 8 or len(line) > 220:
                continue
            sem = _semantic_for_line(line)
            if sem is None:
                continue

            local_start = m.start(1)
            local_end = m.end(1)
            mention = Mention(
                segment_id=seg.segment_id,
                section_path=seg.section_path,
                exact_quote=seg.text[local_start:local_end],
                start_char=seg_start + local_start,
                end_char=seg_start + local_end,
            )

            out.append(
                Candidate(
                    candidate_id="",
                    kind="soft",
                    semantic_type=sem,  # type: ignore[arg-type]
                    value_type="text",
                    raw_text=line,
                    normalized={"text": re.sub(r"\s+", " ", line.strip().lower()), "source": "manual_rule_v1"},
                    mentions=[mention],
                    dedupe_key="",
                    confidence=0.65,
                )
            )

    return out


def run(args: argparse.Namespace) -> None:
    queue_path = Path(args.queue)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    lines = [json.loads(x) for x in queue_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    done = 0
    added_total = 0
    for item in lines:
        run_name = item["run_name"]
        cp_path = Path(item["candidate_pool_path"])
        memos_path = Path(item["memos_jsonl_path"])
        if not cp_path.exists() or not memos_path.exists():
            continue

        original = json.loads(cp_path.read_text(encoding="utf-8").splitlines()[0])
        memo_obj = json.loads(memos_path.read_text(encoding="utf-8").splitlines()[0])
        memo_text = memo_obj.get("text", "")

        base_candidates = original.get("candidates", [])
        base_objs = [Candidate.model_validate(c) for c in base_candidates]
        soft_objs = manual_soft_candidates(memo_text)
        merged = merge_candidates(base_objs + soft_objs)

        added = max(0, len(merged) - len(base_objs))
        added_total += added

        out_dir = output_root / run_name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_line = dict(original)
        out_line["candidates"] = [c.model_dump() for c in merged]
        out_line["extraction_metadata"]["llm_enabled"] = False
        out_line["extraction_metadata"]["prompt_version"] = "manual_soft_v1"

        (out_dir / "candidate_pool_manual.jsonl").write_text(
            json.dumps(out_line, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        done += 1

    summary = {"processed": done, "queue_size": len(lines), "added_candidates_total": added_total}
    if args.summary:
        sp = Path(args.summary)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manual soft augmentation for selected queue items")
    p.add_argument("--queue", default="outputs/llm_queue/queue.jsonl")
    p.add_argument("--output-root", default="outputs/runs_manual")
    p.add_argument("--summary", default="outputs/reports/manual_augment_summary.json")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
