"""준비서면 생성 프롬프트.

준비서면은 상대방 서면에 대응하는 문서라 '쟁점 = 상대 주장 + 반박 + 근거' 묶음이
그대로 문서의 가·나·다 항목이 된다. 호증 번호는 사건 전체에서 이어지므로
evidence_start_no 부터 코드에서 확정해 프롬프트에 넣는다 (AI 가 매기지 않는다).
"""

from app.documents.schemas.brief import BriefInput, SubmitterRole

# 제출자 지위 → 호증 접두어. 원고는 갑, 피고는 을.
EVIDENCE_PREFIX: dict[SubmitterRole, str] = {
    SubmitterRole.PLAINTIFF: "갑",
    SubmitterRole.DEFENDANT: "을",
}

ROLE_LABELS: dict[SubmitterRole, str] = {
    SubmitterRole.PLAINTIFF: "원고",
    SubmitterRole.DEFENDANT: "피고",
}

# 출력 마크다운 헤더 → BriefSections 필드명 (service 의 섹션 파싱용)
SECTION_MAP: dict[str, str] = {
    "제목": "title",
    "사건": "case_info",
    "상대방 주장의 요지": "opponent_summary",
    "반박": "rebuttal",
    "관련 법리": "related_law",
    "결론": "conclusion",
    "입증방법": "evidence",
    "첨부서류": "attachments",
    "관할법원": "court",
}

SYSTEM = """당신은 대한민국 민사소송 '준비서면' 작성을 돕는 법률 문서 전문가입니다.
사용자가 제공한 정보만으로 법원 제출용 준비서면 초안을 작성합니다.

## 출력 형식 (반드시 준수)
아래 9개 섹션을 정확히 이 마크다운 헤더로, 이 순서대로 출력하세요.
다른 헤더를 만들거나 헤더를 생략하지 마세요. 헤더 외 인사말·설명·마무리 문구는 쓰지 마세요.

## 제목
## 사건
## 상대방 주장의 요지
## 반박
## 관련 법리
## 결론
## 입증방법
## 첨부서류
## 관할법원

## 작성 규칙
- 제목: [준비서면 회차] 를 그대로 쓴다. 없으면 "준비서면".
- 사건: 아래 형식으로 적는다. 사건명이 없으면 그 줄을 생략한다.
    사 건  {사건번호} {사건명}
    원 고  {원고 이름}
    피 고  {피고 이름}
  그 아래 한 줄을 띄우고
  "위 사건에 관하여 {제출자}는 다음과 같이 변론을 준비합니다." 를 덧붙인다.

- 상대방 주장의 요지: 아래 순서로 쓴다.
  1) "{상대방}은 {받은 날}자 {서면 종류}에서 다음과 같이 주장합니다." 로 시작한다.
     (받은 날·서면 종류가 없으면 "{상대방}은 다음과 같이 주장합니다." 로 줄인다)
  2) 상대방 주장을 법률 문언으로 정리해 적는다.
  3) [상대방 항변] 이 주어지면 "이는 ○○, ○○에 해당합니다." 로 항변의 성질을 분류한다.
  4) [다툼 없는 사실] 이 주어지면 "다만 …은 {상대방}도 인정합니다. 이 점은 당사자
     사이에 다툼이 없습니다." 로 맺는다. 없으면 이 문장을 쓰지 않는다.

- 반박: [쟁점] 하나가 항목 하나다. "가.", "나.", "다." 순으로 나눈다.
    가. 쟁점 1 — {상대방 주장}.
        {반박 내용을 법률 문언으로}
        (근거 : {근거 증거})
  · 근거 증거가 주어진 쟁점에만 "(근거 : …)" 줄을 붙인다.
  · 쟁점이 하나도 없으면 상대방 주장 전체에 대한 반박을 문단으로 쓴다.

- 관련 법리: 인용할 판례가 주어졌을 때만 쓴다.
  "{법원} {선고일} 선고 {사건번호} 판결" 을 적고 다음 줄에 요지를 큰따옴표로 인용한다.
  판례가 없으면 이 헤더 아래에 "해당 없음" 한 줄만 적는다.

- 결론: [마무리 강조] 를 법률 문언으로 정리해 쓴다.
  비어 있으면 "{제출자}의 청구는 이유 있으므로 인용되어야 합니다." 로 맺는다.

- 입증방법: [이번에 낼 증거] 에 **이미 확정된 호증 번호**가 붙어 있다.
  번호를 바꾸거나 다시 매기지 말고 그대로 옮겨 적는다.
    1. 갑 제7호증  목적물 인도 확인서
    2. 갑 제8호증  통상손모 비교 사진
  줄머리는 1. 2. 3. 순번으로 올린다. 증거가 없으면 "해당 없음" 한 줄만 적는다.

- 첨부서류: 아래 관례를 따른다.
    1. 위 입증방법  각 1통
    2. 준비서면 부본  1통

- 관할법원: 재판부가 주어지면 "○○법원 ○○재판부 귀중", 없으면 "○○법원 귀중".

## 금지 사항
- 사용자가 제공하지 않은 사실(날짜·금액·경위 등)을 지어내지 않는다.
  빠진 정보는 [○○ 기재 필요] 로 표시한다.
- 호증 번호를 새로 매기지 않는다. 주어진 번호를 그대로 쓴다.
- 날짜·서명란은 출력하지 않는다 (시스템이 별도 처리).
- 이미 한 주장을 반복하지 않는다. 상대방이 새로 낸 주장에만 대응한다.
- 법률 자문이 아닌 초안 작성이므로 단정적 승소 표현을 쓰지 않는다."""


def numbered_evidence(d: BriefInput) -> list[str]:
    """호증 번호를 확정해 '갑 제7호증  목적물 인도 확인서' 형태로 만든다.

    사건 전체에서 이어지는 번호라 AI 에 맡기지 않고 여기서 매긴다.
    """
    prefix = EVIDENCE_PREFIX[d.submitter_role]
    return [
        f"{prefix} 제{d.evidence_start_no + i}호증  {name}"
        for i, name in enumerate(d.new_evidence)
    ]


def build_user_prompt(d: BriefInput) -> str:
    """BriefInput 을 프롬프트 본문으로 조립한다."""
    submitter = ROLE_LABELS[d.submitter_role]
    opponent = "피고" if d.submitter_role == SubmitterRole.PLAINTIFF else "원고"

    defenses = "\n".join(f"- {x}" for x in d.defenses) or "없음"
    evidence = "\n".join(f"- {x}" for x in numbered_evidence(d)) or "없음"
    precedents = (
        "\n".join(
            f"- {p.case_no}" + (f": {p.summary}" if p.summary else "")
            for p in d.cited_precedents
        )
        or "없음"
    )

    if d.rebuttal_points:
        blocks = []
        for i, r in enumerate(d.rebuttal_points, start=1):
            lines = [
                f"[쟁점 {i}]",
                f"- 상대방 주장: {r.claim}",
                f"- 반박: {r.rebuttal}",
            ]
            if r.evidence_ref:
                lines.append(f"- 근거 증거: {r.evidence_ref}")
            if r.precedent_ref:
                lines.append(f"- 인용 판례: {r.precedent_ref}")
            blocks.append("\n".join(lines))
        points = "\n\n".join(blocks)
    else:
        points = "없음"

    return f"""[제출자] {submitter}
[상대방] {opponent}
[관할법원] {d.court}
[재판부] {d.panel or "미기재"}
[사건번호] {d.case_no}
[사건명] {d.case_name or "미기재"}
[원고] {d.plaintiff}
[피고] {d.defendant}
[준비서면 회차] {d.brief_no or "준비서면"}
[소송 단계] {d.stage or "미기재"}
[다음 변론기일] {d.hearing_date or "미기재"}

[상대방이 낸 서면] {d.opponent_doc_type or "미기재"}
[받은 날] {d.opponent_doc_date or "미기재"}

[상대방 주장 (사용자가 읽은 대로)]
{d.opponent_claim}

[상대방 항변]
{defenses}

[다툼 없는 사실]
{d.undisputed_facts or "없음"}

{points}

[마무리 강조]
{d.my_argument or "없음"}

[이번에 낼 증거 — 호증 번호 확정됨]
{evidence}

[인용할 판례]
{precedents}

위 정보로 준비서면을 작성하세요."""


assert set(EVIDENCE_PREFIX) == set(SubmitterRole)
assert set(ROLE_LABELS) == set(SubmitterRole)
