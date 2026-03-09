from __future__ import annotations

import re

from agent_a.schema import Segment


MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+?)\s*$")
NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+)[.)]\s+(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*([-*•]|\d+[.)])\s+")
SENTENCEY_END_RE = re.compile(r"(습니다|하였다|했다|된다|됨|있다|없다|같다|합니다)$")


def _is_heading(lines: list[str], idx: int) -> bool:
    line = lines[idx].strip()
    if not line:
        return False
    if BULLET_RE.match(line):
        return False
    if MARKDOWN_HEADING_RE.match(line) or NUMBERED_HEADING_RE.match(line):
        return True
    if line.endswith("?") or line.endswith(":"):
        return len(line) <= 48
    if idx + 1 < len(lines) and BULLET_RE.match(lines[idx + 1]):
        if len(line) <= 40:
            return True

    words = [w for w in line.split() if w]
    if len(line) <= 24 and len(words) <= 5 and "." not in line:
        if re.search(r"\d", line):
            return False
        if SENTENCEY_END_RE.search(line) is None:
            has_blank_around = False
            if idx > 0 and not lines[idx - 1].strip():
                has_blank_around = True
            if idx + 1 < len(lines) and not lines[idx + 1].strip():
                has_blank_around = True
            if has_blank_around:
                return True
    return False


def split_segments(text: str) -> list[Segment]:
    lines = text.splitlines(keepends=True)
    segments: list[Segment] = []

    paragraph_lines: list[str] = []
    paragraph_start = 0
    paragraph_end = 0

    line_starts: list[int] = []
    pos = 0
    for line in lines:
        line_starts.append(pos)
        pos += len(line)

    section_path: list[str] = []

    def add_segment(start_pos: int, end_pos: int) -> None:
        if end_pos <= start_pos:
            return
        chunk = text[start_pos:end_pos]
        if chunk.strip():
            segments.append(
                Segment(
                    segment_id=f"S-{len(segments) + 1:04d}",
                    section_path=list(section_path),
                    text=chunk,
                    start_char=start_pos,
                    end_char=end_pos,
                )
            )

    def flush_paragraph() -> None:
        nonlocal paragraph_lines, paragraph_start, paragraph_end
        if not paragraph_lines:
            return
        add_segment(paragraph_start, paragraph_end)
        paragraph_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        line_start = line_starts[i]
        line_end = line_start + len(line)

        if _is_heading(lines, i):
            flush_paragraph()
            heading = stripped.lstrip("#").rstrip(":")
            section_path = [heading]
            continue

        if BULLET_RE.match(line):
            flush_paragraph()
            add_segment(line_start, line_end)
            continue

        if not stripped:
            flush_paragraph()
            continue

        if not paragraph_lines:
            paragraph_start = line_start
        paragraph_lines.append(line)
        paragraph_end = line_end

    flush_paragraph()

    if not segments and text.strip():
        add_segment(0, len(text))

    return segments
