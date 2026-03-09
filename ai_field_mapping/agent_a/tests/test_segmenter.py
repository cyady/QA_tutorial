from pathlib import Path

from agent_a.segmenter import split_segments


def test_segmenter_stable_ids_and_offsets() -> None:
    text = (Path(__file__).parent / "fixtures" / "sample_memo.txt").read_text(encoding="utf-8")
    segs = split_segments(text)

    assert segs
    assert segs[0].segment_id == "S-0001"
    assert segs[-1].segment_id == f"S-{len(segs):04d}"

    for s in segs:
        assert text[s.start_char:s.end_char] == s.text
        assert s.start_char < s.end_char
    assert len({s.segment_id for s in segs}) == len(segs)
    assert any(s.section_path for s in segs)


def test_segmenter_splits_bullets() -> None:
    text = "제목\n- 첫번째\n- 두번째\n본문"
    segs = split_segments(text)
    assert len(segs) >= 3
