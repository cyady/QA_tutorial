from agent_a.merge import merge_candidates
from agent_a.schema import Candidate, Mention


def test_merge_dedupe_hard_candidates() -> None:
    m1 = Mention(segment_id="S-0001", section_path=[], exact_quote="약 1억 원", start_char=10, end_char=16)
    m2 = Mention(segment_id="S-0002", section_path=[], exact_quote="1억 원", start_char=30, end_char=34)

    c1 = Candidate(
        kind="hard",
        semantic_type="budget",
        value_type="currency",
        raw_text="약 1억 원",
        normalized={"value": 100000000, "currency": "KRW", "approx": True},
        mentions=[m1],
        dedupe_key="x",
        confidence=0.9,
    )
    c2 = Candidate(
        kind="hard",
        semantic_type="budget",
        value_type="currency",
        raw_text="1억 원",
        normalized={"value": 100000000, "currency": "KRW", "approx": False},
        mentions=[m2],
        dedupe_key="y",
        confidence=0.8,
    )

    merged = merge_candidates([c1, c2])
    assert len(merged) == 1
    assert len(merged[0].mentions) == 2
    assert merged[0].candidate_id == "C-0001"
    assert merged[0].normalized is not None
    assert merged[0].normalized.get("approx") is True
