from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_a.rules.normalize_ko_numbers import normalize_ko_number, parse_korean_number_value
from agent_a.rules.regex_extractors import extract_hard_candidates
from agent_a.segmenter import split_segments


@pytest.fixture
def sample_text() -> str:
    p = Path(__file__).parent / "fixtures" / "sample_memo.txt"
    return p.read_text(encoding="utf-8")


def test_normalize_ko_numbers_unit_cases() -> None:
    assert parse_korean_number_value("3.3만") == 33000
    assert parse_korean_number_value("1억") == 100000000
    assert parse_korean_number_value("2천만") == 20000000
    assert parse_korean_number_value("7만 4천") == 74000
    assert normalize_ko_number("150여") == {"value": 150, "approx": True}


def test_hard_extractors_expected_values(sample_text: str) -> None:
    segments = split_segments(sample_text)
    cands = extract_hard_candidates(segments)

    def has(semantic: str, value_type: str, predicate) -> bool:
        for c in cands:
            if c.semantic_type == semantic and c.value_type == value_type and predicate(c.normalized or {}):
                return True
        return False

    assert has("budget", "currency", lambda n: n.get("value") == 100000000 and n.get("currency") == "KRW" and n.get("approx") is True)
    assert has("team_size", "number", lambda n: n.get("value") == 9)
    assert has("target_population", "number", lambda n: n.get("value") == 74000)
    assert has("target_population", "number", lambda n: n.get("value") == 17000)
    assert has("case_metric", "number", lambda n: n.get("value") == 33000)
    assert has("case_metric", "number", lambda n: n.get("value") == 28000)
    assert has("sales_activity", "number_range", lambda n: n.get("min") == 4 and n.get("max") == 5 and n.get("unit") == "times")
    assert has("match_rate", "percentage_range", lambda n: n.get("min") == 0.3 and n.get("max") == 0.5)
    assert has("duration", "duration", lambda n: n.get("value") == 2.5 and n.get("unit") == "months" and n.get("approx") is True)
    assert not has("case_metric", "number", lambda n: n.get("value") == 2.5 and n.get("unit") == "count")
    assert has("sales_activity", "text", lambda n: n.get("keyword") == "SDR")

    # Evidence offsets must map to exact quote in full text.
    for c in cands:
        for m in c.mentions:
            assert sample_text[m.start_char:m.end_char] == m.exact_quote


def test_sample_expected_hard_snapshot(sample_text: str) -> None:
    expected_path = Path(__file__).parent / "fixtures" / "sample_expected_hard.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8-sig"))
    cands = extract_hard_candidates(split_segments(sample_text))
    got = [{"semantic_type": c.semantic_type, "value_type": c.value_type, "normalized": c.normalized} for c in cands]
    for item in expected:
        matched = False
        for g in got:
            if g["semantic_type"] != item["semantic_type"] or g["value_type"] != item["value_type"]:
                continue
            exp_norm = item.get("normalized") or {}
            got_norm = g.get("normalized") or {}
            if all(got_norm.get(k) == v for k, v in exp_norm.items()):
                matched = True
                break
        assert matched


def test_month_only_not_extracted_but_short_year_range_is() -> None:
    text = "타임라인은 1월, 12월 그리고 '25.11 ~ '26.1 까지 채용 시즌"
    cands = extract_hard_candidates(split_segments(text))
    date_cands = [c for c in cands if c.value_type == "date_expression"]
    raws = [c.raw_text for c in date_cands]
    assert all(raw.strip() not in {"1월", "12월"} for raw in raws)
    assert any("25.11" in raw and "26.1" in raw for raw in raws)


def test_people_range_extracted_before_single_counts() -> None:
    text = "팀장님 당 적게 4~5명 정도, 많은 팀은 30~40명 정도"
    cands = extract_hard_candidates(split_segments(text))
    ranges = [c for c in cands if c.value_type == "number_range" and (c.normalized or {}).get("unit") == "people"]
    singles = [c for c in cands if c.value_type == "number" and (c.normalized or {}).get("unit") == "people"]
    assert len(ranges) >= 2
    # No single-count leakage from matched ranges.
    assert not any((c.normalized or {}).get("value") in {5, 40} for c in singles)


def test_contact_schedule_and_budget_unknown_extraction() -> None:
    text = (
        "(주)델타아이에스 이소중님 (support@delta-is.com,010-3852-3253)\n"
        "예산: 아직 책정된 바 없음\n"
        "미팅일정: 7/15(화) 오후 2시 줌 미팅 희망 @박동주 (Vincent Park)\n"
        "니즈:\n"
        "기업 패키지 가격 비교표 필요\n"
        "문의사항:\n"
        "AI튜터 결합 시 비교 포인트는?\n"
    )
    cands = extract_hard_candidates(split_segments(text))

    assert any(c.value_type == "email" and c.raw_text == "support@delta-is.com" for c in cands)
    assert any((c.normalized or {}).get("kind") == "phone" for c in cands)
    assert any(c.semantic_type == "timeline" and "7/15" in c.raw_text for c in cands)
    assert any(c.semantic_type == "timeline" and "오후 2시" in c.raw_text for c in cands)
    assert any(c.semantic_type == "stakeholder_or_team" and c.raw_text.startswith("@박동주") for c in cands)
    assert not any(c.semantic_type == "stakeholder_or_team" and "@delta" in c.raw_text for c in cands)
    assert any(
        c.semantic_type == "budget"
        and c.value_type == "text"
        and (c.normalized or {}).get("status") == "unknown"
        for c in cands
    )


def test_compact_date_weekday_and_time_range() -> None:
    text = "일정: 251102-일 / KTX(12:38 ~ 15:00) 이동"
    cands = extract_hard_candidates(split_segments(text))
    assert any((c.normalized or {}).get("kind") == "compact_date_weekday" for c in cands)
    assert any((c.normalized or {}).get("kind") == "time_range" for c in cands)
