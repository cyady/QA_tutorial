from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


def _sanitize(value: str) -> str:
    v = value.strip()
    if not v:
        return "ungrouped"
    v = v.replace(" ", "_")
    v = re.sub(r"[^0-9A-Za-z가-힣_.-]", "_", v)
    v = re.sub(r"_+", "_", v)
    return v.strip("_") or "ungrouped"


def _clean_id(raw_id: str) -> str:
    cleaned = raw_id.replace(",", "").strip()
    return _sanitize(cleaned) or "unknown"


def run(args: argparse.Namespace) -> None:
    csv_path = Path(args.csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, str]] = []
    group_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    used_names: set[tuple[str, str]] = set()

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            if args.limit is not None and count >= args.limit:
                break

            text = (row.get(args.text_column) or "").strip()
            if not text:
                continue

            raw_id = str(row.get(args.id_column) or "")
            memo_id = args.memo_prefix + _clean_id(raw_id) if raw_id else f"{args.memo_prefix}{count+1:06d}"
            group_raw = str(row.get(args.group_column) or "ungrouped")
            group = _sanitize(group_raw)

            group_dir = out_dir / group
            group_dir.mkdir(parents=True, exist_ok=True)

            base_name = f"memo_{memo_id}"
            candidate_name = base_name
            suffix = 2
            while (group, candidate_name) in used_names:
                candidate_name = f"{base_name}_{suffix}"
                suffix += 1
            used_names.add((group, candidate_name))

            txt_path = group_dir / f"{candidate_name}.txt"
            txt_path.write_text(text, encoding="utf-8")

            rel_txt = txt_path.relative_to(out_dir).as_posix()
            item = {"memo_id": memo_id, "text": text}
            group_rows[group].append(item)

            manifest_rows.append(
                {
                    "source_id": raw_id,
                    "memo_id": memo_id,
                    "group": group,
                    "file": rel_txt,
                    "text_length": str(len(text)),
                }
            )
            count += 1

    for group, items in group_rows.items():
        jsonl_path = out_dir / group / "memos.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as w:
            for item in items:
                w.write(json.dumps(item, ensure_ascii=False) + "\n")

    all_jsonl = out_dir / "memos_all.jsonl"
    with all_jsonl.open("w", encoding="utf-8") as w:
        for group in sorted(group_rows.keys()):
            for item in group_rows[group]:
                w.write(json.dumps(item, ensure_ascii=False) + "\n")

    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source_id", "memo_id", "group", "file", "text_length"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"written_rows={len(manifest_rows)}")
    print(f"groups={len(group_rows)}")
    print(f"out_dir={out_dir}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Export CSV text rows to grouped memo txt files")
    p.add_argument("--csv", required=True, help="Input CSV path")
    p.add_argument("--out-dir", default="outputs/memo_corpus", help="Output directory root")
    p.add_argument("--text-column", default="text", help="Column name containing memo text")
    p.add_argument("--id-column", default="id", help="Column name used for memo_id")
    p.add_argument("--group-column", default="is_example_format", help="Column name used for folder grouping")
    p.add_argument("--memo-prefix", default="M-", help="Prefix for generated memo_id")
    p.add_argument("--limit", type=int, default=None, help="Optional max rows to export")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
