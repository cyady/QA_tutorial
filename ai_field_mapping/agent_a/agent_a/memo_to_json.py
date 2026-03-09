from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+)[.)]\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
NUMBERED_BULLET_RE = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$")


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if HEADING_RE.match(stripped) or NUMBERED_HEADING_RE.match(stripped):
        return True
    # Question/label style headings: "대상자들은 어떤 사람인지?", "타임라인"
    if len(stripped) <= 40 and (stripped.endswith("?") or stripped.endswith(":")):
        return True
    # Short noun-phrase style heading often used in interview memos.
    words = [w for w in stripped.split() if w]
    if len(stripped) <= 22 and len(words) <= 4 and re.search(r"[.!]", stripped) is None:
        if re.search(r"(습니다|하였다|했다|된다|됨|있다|없다|같다|합니다)$", stripped) is None:
            return True
    return False


def parse_memo_sections(text: str) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    current_title = "본문"
    current_lines: list[str] = []
    current_bullets: list[str] = []

    def flush() -> None:
        nonlocal current_lines, current_bullets
        body = "\n".join(current_lines).strip()
        if body or current_bullets:
            sections.append(
                {
                    "title": current_title,
                    "body": body,
                    "bullet_items": current_bullets,
                }
            )
        current_lines = []
        current_bullets = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        bullet = BULLET_RE.match(line)
        numbered_bullet = NUMBERED_BULLET_RE.match(line)
        if bullet:
            current_bullets.append(bullet.group(1).strip())
            continue
        if numbered_bullet:
            current_bullets.append(numbered_bullet.group(1).strip())
            continue

        heading = HEADING_RE.match(line)
        numbered_heading = NUMBERED_HEADING_RE.match(line)
        if heading:
            flush()
            current_title = heading.group(1).strip()
            continue
        if numbered_heading:
            flush()
            current_title = numbered_heading.group(2).strip()
            continue
        if _looks_like_heading(line):
            flush()
            current_title = line.strip().lstrip("#").strip()
            continue

        current_lines.append(line)

    flush()
    return sections


def build_memo_json(memo_id: str, text: str) -> dict[str, object]:
    return {
        "memo_id": memo_id,
        "text": text,
        "sections": parse_memo_sections(text),
    }


def _read_text(args: argparse.Namespace) -> str:
    if args.input_txt:
        return Path(args.input_txt).read_text(encoding="utf-8")
    if args.text:
        return args.text
    raise ValueError("Either --input-txt or --text is required")


def _resolve_outputs(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.output_dir:
        run_name = args.run_name or datetime.utcnow().strftime("memo-%Y%m%d-%H%M%S")
        run_dir = Path(args.output_dir) / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir / "memo_structured.json", run_dir / "memos.jsonl"

    output_json = Path(args.output_json or "outputs/memo_structured.json")
    output_jsonl = Path(args.output_jsonl or "outputs/memos.jsonl")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    return output_json, output_jsonl


def run(args: argparse.Namespace) -> None:
    text = _read_text(args)
    obj = build_memo_json(args.memo_id, text)
    out_json, out_jsonl = _resolve_outputs(args)

    out_json.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    line_obj = {"memo_id": args.memo_id, "text": text}
    out_jsonl.write_text(json.dumps(line_obj, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Convert memo text to JSON/JSONL")
    p.add_argument("--memo-id", default="M-001", help="Memo ID")
    p.add_argument("--input-txt", help="Input raw memo text file")
    p.add_argument("--text", help="Inline raw memo text")
    p.add_argument("--output-json", help="Output structured JSON path (default: outputs/memo_structured.json)")
    p.add_argument("--output-jsonl", help="Output memos.jsonl path (default: outputs/memos.jsonl)")
    p.add_argument("--output-dir", help="Output directory root. Writes to <output-dir>/<run-name>/memo_structured.json and memos.jsonl")
    p.add_argument("--run-name", help="Folder name under --output-dir (default: UTC timestamp)")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.input_txt and not args.text:
        parser.error("Either --input-txt or --text is required")
    run(args)


if __name__ == "__main__":
    main()
