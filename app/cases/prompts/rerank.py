"""판례 예선 일괄 채점 프롬프트.

후보 전체(사건명·판시사항 발췌)를 LLM 호출 1회로 채점해 본선 진출작을 고른다.
점수의 유일한 출처 — 본선(relevance.py)은 참고 포인트만 생성한다.
"""

SYSTEM = """당신은 대한민국 민사소송을 준비하는 일반인을 돕는 법률 정보 전문가입니다.
판례 후보 목록을 읽고, 사용자 사건 맥락(없으면 검색 키워드) 대비 각 후보의
관련도(relevance)를 0~100 정수로 일괄 채점합니다.

## 채점 기준표 (반드시 준수)
- 90~100: 쟁점과 사실관계가 모두 유사 — 거의 같은 유형의 사건
- 70~89: 핵심 쟁점이 같음 — 사실관계는 다소 다름
- 40~69: 관련 법리를 다루나 중심 쟁점이 다름
- 10~39: 같은 법 영역일 뿐 직접 관련 없음
- 0~9: 무관하거나 판단할 정보 부족

## 규칙
- 모든 후보를 빠짐없이 채점하고, 각 후보의 id 를 그대로 사용한다.
- 판시사항이 없는 후보는 사건명만으로 보수적으로(낮게) 판단한다.
- 후보 내용에 없는 사실을 추정하지 않는다."""


def build_user_prompt(
    query: str,
    case_context: str | None,
    candidates: list[tuple[int, str, str]],
) -> str:
    """(id, 사건명, 판시사항 발췌) 목록을 예선 프롬프트로 조립한다."""
    lines = []
    for cid, name, excerpt in candidates:
        lines.append(f"[후보 {cid}]")
        lines.append(f"사건명: {name}")
        lines.append(f"판시사항: {excerpt or '없음'}")
        lines.append("")
    body = "\n".join(lines)

    return f"""[검색 키워드] {query}
[사용자 사건 맥락] {case_context or "미제공 - 검색 키워드 기준으로 판단"}

{body}
위 후보 전체의 관련도를 일괄 채점하세요."""
