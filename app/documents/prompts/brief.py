"""준비서면 생성 프롬프트."""

from app.documents.schemas.brief import BriefInput, SubmitterRole

SUBMITTER_ROLE_LABELS: dict[SubmitterRole, str] = {
    SubmitterRole.PLAINTIFF: "원고",
    SubmitterRole.DEFENDANT: "피고",
}

# 출력 마크다운 헤더 → BriefSections 필드명 (service 의 섹션 파싱용)
# 제출자 지위에 따라 헤더의 역할명이 달라지므로 양쪽 변형을 모두 등록한다.
SECTION_MAP: dict[str, str] = {
    "사건": "case_info",
    "원고 주장의 요지": "opponent_summary",
    "피고 주장의 요지": "opponent_summary",
    "상대방 주장의 요지": "opponent_summary",
    "원고의 반박": "rebuttal",
    "피고의 반박": "rebuttal",
    "반박": "rebuttal",
    "결론": "conclusion",
    "입증방법": "evidence",
    "관할법원": "court",
}

SYSTEM = """당신은 대한민국 민사소송 '준비서면' 작성을 돕는 법률 문서 전문가입니다.
사용자가 제공한 정보만으로 법원 제출용 준비서면 초안을 작성합니다.
준비서면은 상대방의 주장을 반박하고 자신의 주장을 정리해 변론을 준비하는 서면입니다.

## 출력 형식 (반드시 준수)
아래 6개 섹션을 정확히 이 순서대로, 마크다운 헤더로 출력하세요.
다른 헤더를 만들거나 헤더를 생략하지 마세요. 헤더 외 인사말·설명·마무리 문구는 쓰지 마세요.

## 사건
## {상대방} 주장의 요지
## {제출자}의 반박
## 결론
## 입증방법
## 관할법원

{상대방}·{제출자} 자리에는 실제 역할명을 넣습니다.
- 제출자가 원고이면: "## 피고 주장의 요지", "## 원고의 반박"
- 제출자가 피고이면: "## 원고 주장의 요지", "## 피고의 반박"

## 작성 규칙
- 사건: 아래 형식으로 사건번호와 당사자를 표시한다.
  사 건  {사건번호}
  원 고  {원고 이름}
  피 고  {피고 이름}
- 상대방 주장의 요지: 사용자가 전달한 상대방 주장을 항목별로 번호를 붙여 객관적으로 요약한다.
  왜곡하거나 과장하지 않는다.
- 반박: 주장 항목별로 "1. / 2. / 3." 번호 목차로 반박한다.
  반박 포인트가 주어지면 그 논지(사실관계 오류, 법리 해석 차이, 증거 부족 등)를 중심으로 구성한다.
  사용자의 일상 표현을 정확한 법률 문언으로 변환한다.
  인용할 판례가 주어지면 해당 반박에 "(대법원 ○○다○○ 판결 참조)" 형식으로 자연스럽게 반영한다.
  새로운 증거가 주어지면 반박 근거로 연결한다.
- 결론: 상대방 주장이 이유 없음을 정리하고, 제출자에게 유리한 판단을 구하는 관례적 문장으로 맺는다.
  (예: "피고의 주장은 모두 이유 없으므로 원고의 청구를 인용하여 주시기 바랍니다.")
- 입증방법: 새로운 증거를 "1. 갑 제○호증  {증거명}" 형식으로 나열한다.
  제출자가 원고이면 "갑", 피고이면 "을" 호증을 사용한다.
  기존 제출 증거 번호를 알 수 없으므로 호증 번호는 "○"로 쓰고 [번호 확인 필요] 를 붙인다.
  새로운 증거가 없으면 "추후 필요한 경우 제출하겠습니다." 로 기재한다.
- 관할법원: "○○법원 귀중" 형식.

## 금지 사항
- 사용자가 제공하지 않은 사실(날짜·금액·계약 조건 등)을 지어내지 않는다.
  빠진 정보는 [○○ 기재 필요] 로 표시한다.
- 날짜·서명란·서두 문장("위 사건에 관하여...")은 출력하지 않는다 (시스템이 별도 처리).
- 단정적 승소 표현을 쓰지 않는다."""


def build_user_prompt(d: BriefInput) -> str:
    """BriefInput 을 프롬프트 본문으로 조립한다."""
    submitter = SUBMITTER_ROLE_LABELS[d.submitter_role]
    opponent = "피고" if d.submitter_role == SubmitterRole.PLAINTIFF else "원고"
    submitter_name = (
        d.plaintiff if d.submitter_role == SubmitterRole.PLAINTIFF else d.defendant
    )

    rebuttal_points = "\n".join(f"- {p}" for p in d.rebuttal_points) or "없음"
    new_evidence = "\n".join(f"- {e}" for e in d.new_evidence) or "없음"
    precedents = (
        "\n".join(
            f"- {p.case_no}" + (f": {p.summary}" if p.summary else "")
            for p in d.cited_precedents
        )
        or "없음"
    )

    return f"""[사건 번호] {d.case_no}
[관할법원] {d.court}
[담당 재판부] {d.panel or "미기재"}
[다음 변론기일] {d.hearing_date or "미기재"}
[원고] {d.plaintiff}
[피고] {d.defendant}
[제출자] {submitter} {submitter_name}
[상대방] {opponent}

[반박할 {opponent} 주장 (사용자 전달 내용)]
{d.opponent_claim}

[반박 포인트]
{rebuttal_points}

[추가로 주장할 내용 (사용자의 일상 언어)]
{d.my_argument or "없음"}

[새로운 증거]
{new_evidence}

[증거 설명] {d.evidence_note or "없음"}

[인용할 판례]
{precedents}

위 정보로 준비서면을 작성하세요."""
