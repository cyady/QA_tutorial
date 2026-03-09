from __future__ import annotations

import json
from pathlib import Path

from agent_a.csv_to_memo_txt import run


class Args:
    def __init__(self, csv: str, out_dir: str):
        self.csv = csv
        self.out_dir = out_dir
        self.text_column = "text"
        self.id_column = "id"
        self.group_column = "is_example_format"
        self.memo_prefix = "M-"
        self.limit = None


def test_csv_to_grouped_memo_files(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "id,is_example_format,text\n"
        "1,X,첫번째 메모\n"
        "2,O (High Quality),두번째 메모\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "memo_corpus"
    run(Args(str(csv_path), str(out_dir)))

    x_dir = out_dir / "X"
    hq_dir = out_dir / "O_High_Quality"

    assert x_dir.exists()
    assert hq_dir.exists()

    x_files = list(x_dir.glob("memo_*.txt"))
    hq_files = list(hq_dir.glob("memo_*.txt"))
    assert len(x_files) == 1
    assert len(hq_files) == 1

    assert "첫번째 메모" in x_files[0].read_text(encoding="utf-8")
    assert "두번째 메모" in hq_files[0].read_text(encoding="utf-8")

    manifest = (out_dir / "manifest.csv").read_text(encoding="utf-8-sig")
    assert "source_id,memo_id,group,file,text_length" in manifest

    all_jsonl = (out_dir / "memos_all.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(all_jsonl) == 2
    first = json.loads(all_jsonl[0])
    assert "memo_id" in first and "text" in first
