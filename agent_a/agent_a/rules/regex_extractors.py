from __future__ import annotations

import json
import re
from hashlib import sha1
from typing import Any

from agent_a.rules.dictionaries import load_keyword_dictionary
from agent_a.rules.normalize_ko_numbers import normalize_ko_number
from agent_a.schema import Candidate, Mention, Segment

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:01[0-9]-?\d{3,4}-?\d{4}|0[2-9]-?\d{3,4}-?\d{4})\b")
MENTION_RE = re.compile(r"(?<![A-Za-z0-9._%+-])@([A-Za-z가-힣][A-Za-z가-힣0-9_]{1,30})")
PERCENT_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)\s*%")
NUMBER_RANGE_UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)\s*(회|명|건|개(?!월))")
CURRENCY_RE = re.compile(r"((?:약\s*)?(?:\d+(?:\.\d+)?\s*(?:천만|억|만|천|백|십)?\s*)+)원")
DURATION_RE = re.compile(r"((?:약\s*)?\d+(?:\.\d+)?)\s*(개월|주|일|시간)")
DATE_ABS_RE = re.compile(r"\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b")
DATE_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:\((월|화|수|목|금|토|일)\))?")
TIME_EXPR_RE = re.compile(r"(오전|오후)\s*(\d{1,2})(?::(\d{2}))?\s*시?")
COMPACT_DATE_KO_RE = re.compile(r"\b(\d{2})(\d{2})(\d{2})\s*-\s*(월|화|수|목|금|토|일)\b")
TIME_RANGE_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\s*~\s*([01]?\d|2[0-3]):([0-5]\d)\b")
DATE_KO_RE = re.compile(r"(\d{1,2})월\s*(상순|중순|하순|초|말|\d{1,2}일)(까지)?")
SHORT_YM_RE = re.compile(r"[\"'’`]?\s*(\d{2})[./](\d{1,2})")
SHORT_YM_RANGE_RE = re.compile(
    r"[\"'’`]?\s*(\d{2})[./](\d{1,2})\s*~\s*[\"'’`]?\s*(\d{2})[./](\d{1,2})"
)
COUNTER_RE = re.compile(
    r"((?:약\s*)?(?:\d+(?:\.\d+)?\s*(?:천만|억|만|천|백|십)?\s*)+여?)\s*(명|건|개(?!월))"
)

TARGET_HINTS = ("타깃", "타겟", "대상", "모수", "target")
TEAM_HINTS = ("팀", "인력", "인원", "제작팀", "디자이너", "담당")
CASE_HINTS = ("사례", "케이스", "case")
LEAD_HINTS = ("리드", "lead", "mql", "sql")
SALES_HINTS = ("sdr", "콜", "아웃바운드", "미팅", "발송", "푸시")
DOWNLOAD_HINTS = ("다운로드", "download")
ATTRITION_HINTS = ("이직률", "turnover", "퇴사")
MATCH_HINTS = ("매칭", "match", "전환율")
ACTION_TITLE_HINTS = ("action items", "action item", "액션", "할 일", "todo")
SENTIMENT_TITLE_HINTS = ("customer sentiment", "sentiment", "우려", "리스크", "고민")
NEED_TITLE_HINTS = ("니즈", "needs", "need")
QUESTION_TITLE_HINTS = ("문의", "질문", "q&a", "문의사항")
BUDGET_UNKNOWN_RE = re.compile(r"예산\s*[:：]\s*(아직\s*)?(책정된\s*바\s*없음|미정|없음|없다|미확정)")
ACTION_LINE_RE = re.compile(r"(요청|진행|수립|확정|검토|발송|회신|필요)")
RISK_LINE_RE = re.compile(r"(우려|문제|리스크|어렵|불가|미비|부재)")
COLLAB_LINE_RE = re.compile(r"(협업|협의|공유|전달|연계|도입|필요|희망)")



def _mention(segment: Segment, start: int, end: int) -> Mention:
    return Mention(
        segment_id=segment.segment_id,
        section_path=segment.section_path,
        exact_quote=segment.text[start:end],
        start_char=segment.start_char + start,
        end_char=segment.start_char + end,
    )


def _signature(normalized: dict[str, Any] | None) -> str:
    if not normalized:
        return "null"
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


def _make_candidate(
    *,
    kind: str,
    semantic_type: str,
    value_type: str,
    raw_text: str,
    normalized: dict[str, Any] | None,
    mention: Mention,
    confidence: float,
) -> Candidate:
    dedupe_key = f"{semantic_type}:{sha1(_signature(normalized).encode('utf-8')).hexdigest()[:16]}"
    return Candidate(
        kind=kind,
        semantic_type=semantic_type,  # type: ignore[arg-type]
        value_type=value_type,  # type: ignore[arg-type]
        raw_text=raw_text,
        normalized=normalized,
        mentions=[mention],
        dedupe_key=dedupe_key,
        confidence=confidence,
    )


def _section_title(segment: Segment) -> str:
    if not segment.section_path:
        return ""
    return segment.section_path[-1].strip().lower()


def _context_window(text: str, start: int, end: int, width: int = 36) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    return text[left:right]


def _overlaps(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    for s, e in spans:
        if start < e and end > s:
            return True
    return False


def _label_hint(context: str) -> str | None:
    mapping = [
        (r"전체\s*사원수|사원수", "전체 사원수"),
        (r"팀장\s*수", "팀장 수"),
        (r"임원\s*수|본부장", "임원 수"),
        (r"신규\s*팀장|최근\s*3년", "신규 팀장 수"),
        (r"사무직", "사무직 인원"),
        (r"생산직", "생산직 인원"),
        (r"이직률", "이직률"),
    ]
    for pattern, label in mapping:
        if re.search(pattern, context, flags=re.IGNORECASE):
            return label
    return None


def _semantic_for_percent(context_text: str) -> str:
    lowered = context_text.lower()
    if any(h in lowered for h in ATTRITION_HINTS):
        return "attrition_rate"
    if any(h in lowered for h in MATCH_HINTS):
        return "match_rate"
    return "match_rate"


def _semantic_for_counter(context_text: str, counter: str) -> str:
    lowered = context_text.lower()
    if counter == "명":
        if any(h in lowered for h in TARGET_HINTS):
            return "target_population"
        if any(h in context_text for h in TEAM_HINTS):
            return "team_size"
        if any(h in lowered for h in CASE_HINTS):
            return "case_metric"
        return "people_count"
    if counter == "건":
        if any(h in lowered for h in SALES_HINTS):
            return "sales_activity"
        if any(h in lowered for h in LEAD_HINTS):
            return "lead_volume"
        if any(h in lowered for h in DOWNLOAD_HINTS):
            return "case_metric"
        if any(h in lowered for h in CASE_HINTS):
            return "case_metric"
        return "case_metric"
    return "case_metric"


def _semantic_for_range(context_text: str, unit: str) -> str:
    lowered = context_text.lower()
    if unit == "명":
        if any(h in lowered for h in TARGET_HINTS):
            return "target_population"
        if any(h in context_text for h in TEAM_HINTS):
            return "team_size"
        return "people_count"
    if unit == "건":
        if any(h in lowered for h in LEAD_HINTS):
            return "lead_volume"
        if any(h in lowered for h in SALES_HINTS):
            return "sales_activity"
        return "case_metric"
    if unit == "회":
        return "sales_activity"
    return "case_metric"


def _extract_section_text_candidates(segment: Segment) -> list[Candidate]:
    title = _section_title(segment)
    semantic_type: str | None = None
    label_hint: str | None = None
    if any(h in title for h in ACTION_TITLE_HINTS):
        semantic_type = "action_item"
    elif any(h in title for h in SENTIMENT_TITLE_HINTS):
        semantic_type = "risk_or_concern"
    elif any(h in title for h in NEED_TITLE_HINTS):
        semantic_type = "collaboration_need"
        label_hint = "need_item"
    elif any(h in title for h in QUESTION_TITLE_HINTS):
        semantic_type = "other"
        label_hint = "question_item"
    if semantic_type is None:
        return []

    out: list[Candidate] = []
    bullet_matches = list(re.finditer(r"(?m)^\s*[-*•]\s*(.+?)\s*$", segment.text))
    if bullet_matches:
        for m in bullet_matches:
            quote = m.group(1).strip()
            quote_start = m.start(1)
            quote_end = m.end(1)
            mention = _mention(segment, quote_start, quote_end)
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type=semantic_type,
                    value_type="text",
                    raw_text=quote,
                    normalized={"text": quote, **({"label_hint": label_hint} if label_hint else {})},
                    mention=mention,
                    confidence=0.88,
                )
            )
        return out

    if segment.text.strip():
        if label_hint in {"need_item", "question_item"}:
            for line_match in re.finditer(r"(?m)^\s*(.+?)\s*$", segment.text):
                quote = line_match.group(1).strip()
                if not quote:
                    continue
                mention = _mention(segment, line_match.start(1), line_match.end(1))
                out.append(
                    _make_candidate(
                        kind="hard",
                        semantic_type=semantic_type,
                        value_type="text",
                        raw_text=quote,
                        normalized={"text": quote, "label_hint": label_hint},
                        mention=mention,
                        confidence=0.82,
                    )
                )
        else:
            start = segment.text.find(segment.text.strip())
            end = start + len(segment.text.strip())
            mention = _mention(segment, start, end)
            quote = segment.text.strip()
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type=semantic_type,
                    value_type="text",
                    raw_text=quote,
                    normalized={"text": quote, **({"label_hint": label_hint} if label_hint else {})},
                    mention=mention,
                    confidence=0.82,
                )
            )
    return out


def _extract_cue_line_candidates(segment: Segment) -> list[Candidate]:
    # For memo styles without explicit "Action Items/Sentiment" headings, promote cue lines as soft-like hard candidates.
    out: list[Candidate] = []
    for m in re.finditer(r"(?m)^\s*(.+?)\s*$", segment.text):
        line = m.group(1).strip()
        if not line or len(line) < 8 or len(line) > 220:
            continue
        if line.endswith(":"):
            continue

        semantic: str | None = None
        label_hint: str | None = None
        if ACTION_LINE_RE.search(line):
            semantic = "action_item"
            label_hint = "line_action"
        if RISK_LINE_RE.search(line):
            semantic = "risk_or_concern"
            label_hint = "line_risk"
        if semantic is None and COLLAB_LINE_RE.search(line):
            semantic = "collaboration_need"
            label_hint = "line_collaboration"

        if semantic is None:
            continue

        mention = _mention(segment, m.start(1), m.end(1))
        out.append(
            _make_candidate(
                kind="hard",
                semantic_type=semantic,
                value_type="text",
                raw_text=line,
                normalized={"text": line, "label_hint": label_hint},
                mention=mention,
                confidence=0.74,
            )
        )
    return out


def extract_hard_candidates(
    segments: list[Segment], keyword_dict: dict[str, list[str]] | None = None
) -> list[Candidate]:
    out: list[Candidate] = []
    kw = keyword_dict or load_keyword_dictionary()

    for segment in segments:
        text = segment.text
        occupied_spans: list[tuple[int, int]] = []

        out.extend(_extract_section_text_candidates(segment))
        out.extend(_extract_cue_line_candidates(segment))

        for m in EMAIL_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="other",
                    value_type="email",
                    raw_text=m.group(0),
                    normalized={"value": m.group(0).lower()},
                    mention=mention,
                    confidence=0.98,
                )
            )

        for m in PHONE_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            normalized_phone = re.sub(r"\D", "", m.group(0))
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="other",
                    value_type="text",
                    raw_text=m.group(0),
                    normalized={"kind": "phone", "value": normalized_phone},
                    mention=mention,
                    confidence=0.97,
                )
            )

        for m in MENTION_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="stakeholder_or_team",
                    value_type="text",
                    raw_text=m.group(0),
                    normalized={"name": m.group(1)},
                    mention=mention,
                    confidence=0.9,
                )
            )

        for m in BUDGET_UNKNOWN_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="budget",
                    value_type="text",
                    raw_text=m.group(0),
                    normalized={"status": "unknown"},
                    mention=mention,
                    confidence=0.92,
                )
            )

        for m in SHORT_YM_RANGE_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="timeline",
                    value_type="date_expression",
                    raw_text=m.group(0),
                    normalized={
                        "start": {"year": 2000 + int(m.group(1)), "month": int(m.group(2))},
                        "end": {"year": 2000 + int(m.group(3)), "month": int(m.group(4))},
                        "kind": "short_year_month_range",
                    },
                    mention=mention,
                    confidence=0.93,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in DATE_SLASH_RE.finditer(text):
            if _overlaps(occupied_spans, m.start(), m.end()):
                continue
            mention = _mention(segment, m.start(), m.end())
            norm: dict[str, Any] = {"month": int(m.group(1)), "day": int(m.group(2)), "kind": "month_day"}
            if m.group(3):
                norm["weekday_ko"] = m.group(3)
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="timeline",
                    value_type="date_expression",
                    raw_text=m.group(0),
                    normalized=norm,
                    mention=mention,
                    confidence=0.9,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in TIME_EXPR_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            hour = int(m.group(2))
            minute = int(m.group(3) or "0")
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="timeline",
                    value_type="date_expression",
                    raw_text=m.group(0),
                    normalized={"time_period": m.group(1), "hour": hour, "minute": minute, "kind": "time_expression"},
                    mention=mention,
                    confidence=0.88,
                )
            )

        for m in DATE_ABS_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="timeline",
                    value_type="date_expression",
                    raw_text=m.group(0),
                    normalized={"expression": m.group(0)},
                    mention=mention,
                    confidence=0.92,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in COMPACT_DATE_KO_RE.finditer(text):
            if _overlaps(occupied_spans, m.start(), m.end()):
                continue
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="timeline",
                    value_type="date_expression",
                    raw_text=m.group(0),
                    normalized={
                        "year": 2000 + int(m.group(1)),
                        "month": int(m.group(2)),
                        "day": int(m.group(3)),
                        "weekday_ko": m.group(4),
                        "kind": "compact_date_weekday",
                    },
                    mention=mention,
                    confidence=0.9,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in DATE_KO_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            raw = m.group(0)
            part = m.group(2) or ""
            norm: dict[str, Any] = {"month": int(m.group(1))}
            if part in ("상순", "중순", "하순", "초", "말"):
                part_map = {
                    "상순": "early",
                    "중순": "mid",
                    "하순": "late",
                    "초": "early",
                    "말": "late",
                }
                norm["part"] = part_map[part]
            elif part.endswith("일"):
                norm["day"] = int(part[:-1])
            if m.group(3):
                norm["until"] = True
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="timeline",
                    value_type="date_expression",
                    raw_text=raw,
                    normalized=norm,
                    mention=mention,
                    confidence=0.9,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in TIME_RANGE_RE.finditer(text):
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="timeline",
                    value_type="date_expression",
                    raw_text=m.group(0),
                    normalized={
                        "start": {"hour": int(m.group(1)), "minute": int(m.group(2))},
                        "end": {"hour": int(m.group(3)), "minute": int(m.group(4))},
                        "kind": "time_range",
                    },
                    mention=mention,
                    confidence=0.88,
                )
            )

        for m in SHORT_YM_RE.finditer(text):
            if _overlaps(occupied_spans, m.start(), m.end()):
                continue
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="timeline",
                    value_type="date_expression",
                    raw_text=m.group(0),
                    normalized={
                        "year": 2000 + int(m.group(1)),
                        "month": int(m.group(2)),
                        "kind": "short_year_month",
                    },
                    mention=mention,
                    confidence=0.87,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in PERCENT_RANGE_RE.finditer(text):
            vmin = float(m.group(1)) / 100.0
            vmax = float(m.group(2)) / 100.0
            context = _context_window(text, m.start(), m.end())
            semantic = _semantic_for_percent(context)
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type=semantic,
                    value_type="percentage_range",
                    raw_text=m.group(0),
                    normalized={"min": vmin, "max": vmax, "label_hint": _label_hint(context)},
                    mention=mention,
                    confidence=0.95,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in NUMBER_RANGE_UNIT_RE.finditer(text):
            context = _context_window(text, m.start(), m.end())
            unit = m.group(3)
            mention = _mention(segment, m.start(), m.end())
            semantic = _semantic_for_range(context, unit)
            norm: dict[str, Any] = {
                "min": float(m.group(1)),
                "max": float(m.group(2)),
                "unit": {"회": "times", "명": "people", "건": "cases", "개": "count"}[unit],
            }
            label_hint = _label_hint(context)
            if label_hint:
                norm["label_hint"] = label_hint
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type=semantic,
                    value_type="number_range",
                    raw_text=m.group(0),
                    normalized=norm,
                    mention=mention,
                    confidence=0.94,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in CURRENCY_RE.finditer(text):
            raw = m.group(0)
            num_part = raw[:-1]
            n = normalize_ko_number(num_part)
            if not n:
                continue
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="budget",
                    value_type="currency",
                    raw_text=raw,
                    normalized={"value": n["value"], "currency": "KRW", "approx": n.get("approx", False)},
                    mention=mention,
                    confidence=0.97,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in DURATION_RE.finditer(text):
            raw = m.group(0)
            value = float(m.group(1).replace("약", "").strip())
            unit_map = {"개월": "months", "주": "weeks", "일": "days", "시간": "hours"}
            mention = _mention(segment, m.start(), m.end())
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type="duration",
                    value_type="duration",
                    raw_text=raw,
                    normalized={
                        "value": value,
                        "unit": unit_map[m.group(2)],
                        "approx": "약" in raw,
                    },
                    mention=mention,
                    confidence=0.94,
                )
            )
            occupied_spans.append((m.start(), m.end()))

        for m in COUNTER_RE.finditer(text):
            if _overlaps(occupied_spans, m.start(), m.end()):
                continue
            raw = m.group(0)
            num_expr = m.group(1)
            counter = m.group(2)
            n = normalize_ko_number(num_expr)
            if not n:
                continue
            context = _context_window(text, m.start(), m.end())
            mention = _mention(segment, m.start(), m.end())
            semantic = _semantic_for_counter(context, counter)
            norm = {
                "value": n["value"],
                "unit": {"명": "people", "건": "cases", "개": "count"}[counter],
                "approx": n.get("approx", False),
            }
            label_hint = _label_hint(context)
            if label_hint:
                norm["label_hint"] = label_hint
            out.append(
                _make_candidate(
                    kind="hard",
                    semantic_type=semantic,
                    value_type="number",
                    raw_text=raw,
                    normalized=norm,
                    mention=mention,
                    confidence=0.93,
                )
            )

        for semantic_type, keywords in kw.items():
            sem = (
                semantic_type
                if semantic_type in {"tool_or_channel", "kpi_definition", "constraint", "sales_activity"}
                else "other"
            )
            for keyword in keywords:
                for m in re.finditer(re.escape(keyword), text, flags=re.IGNORECASE):
                    mention = _mention(segment, m.start(), m.end())
                    out.append(
                        _make_candidate(
                            kind="hard",
                            semantic_type=sem,
                            value_type="text",
                            raw_text=m.group(0),
                            normalized={"keyword": keyword},
                            mention=mention,
                            confidence=0.86,
                        )
                    )

    return out
