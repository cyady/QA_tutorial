from agent_a.memo_to_json import parse_memo_sections


def test_parse_non_bullet_heading_style_memo() -> None:
    text = """데모미팅 w/ 신현철 수석

STX엔진 요약

지금까지 단 한번도 리더십 교육을 안 한 회사

TIPP을 찾게 된 배경

지난 주 신임팀장 오프라인 집체 교육 진행

대상자들은 어떤 사람인지?

팀장 수는 40명 정도 / 전체 사원수는 900명 정도
"""
    sections = parse_memo_sections(text)

    titles = [s["title"] for s in sections]
    assert "STX엔진 요약" in titles
    assert "TIPP을 찾게 된 배경" in titles
    assert "대상자들은 어떤 사람인지?" in titles
