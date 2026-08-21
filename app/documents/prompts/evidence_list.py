"""증거목록 생성 프롬프트."""

from app.documents.schemas.evidence_list import (
    EvidenceListInput,
    OriginalType,
    SubmitterRole,
)

# 원본/사본 enum → 표에 찍히는 한국어
ORIGINAL_LABELS: dict[OriginalType, str] = {
    OriginalType.COPY: "사본",
    OriginalType.ORIGINAL: "원본",
}

SUBMITTER_ROLE_LABELS: dict[SubmitterRole, str] = {
    SubmitterRole.PLAINTIFF: "원고",
    SubmitterRole.DEFENDANT: "피고",
    SubmitterRole.INTERVENOR: "참가인",
}

# 제출자 지위 → 호증 접두어
EVIDENCE_PREFIX: dict[SubmitterRole, str] = {
    SubmitterRole.PLAINTIFF: "갑",
    SubmitterRole.DEFENDANT: "을",
    SubmitterRole.INTERVENOR: "병",
}

# 출력 마크다운 헤더 → EvidenceListSections 필드명 (service 의 섹션 파싱용)
SECTION_MAP: dict[str, str] = {
    "제목": "title",
    "사건": "case_info",
    "증거목록": "evidence_table",
    "비고": "note",
    "관할법원": "court",
}

SYSTEM = """당신은 대한민국 민사소송 법원 제출용 '증거목록' 작성을 돕는 법률 문서 전문가입니다.
사용자가 제공한 증거 정보만으로 증거목록 초안을 작성합니다.

## 출력 형식 (반드시 준수)
아래 5개 섹션을 정확히 이 마크다운 헤더로, 이 순서대로 출력하세요.
다른 헤더를 만들거나 헤더를 생략하지 마세요. 헤더 외 인사말·설명·마무리 문구는 쓰지 마세요.

## 제목
## 사건
## 증거목록
## 비고
## 관할법원

## 작성 규칙
- 제목: "{제출자} 제출 {접두어}호증" 형식의 부제만 기재한다. (예: "원고 제출 갑호증")
- 사건: 아래 형식으로 사건번호와 당사자를 표시한다.
  사 건  {사건번호}
  원 고  {원고 이름}
  피 고  {피고 이름}
- 증거목록: 아래 형식의 마크다운 표로 작성한다. 열은 6개이고 순서를 바꾸지 않는다.
  | 호증번호 | 서증명 | 입증취지 | 원본 | 작성자 | 작성일 |
  |---|---|---|---|---|---|
  - 호증번호·원본·작성자·작성일은 **사용자가 전달한 값을 그대로** 쓴다. 바꾸거나
    순서를 재배열하지 않는다.
  - 입증취지가 비어 있으면 서증명과 사건명을 근거로 통상적인 입증취지를 1문장으로
    제안하되, 구체적 사실관계(금액·날짜·경위)를 창작하지 않는다.
  - 입증취지가 주어져 있으면 법률 문언으로 다듬어 사용한다.
  - 작성자·작성일이 비어 있으면 각각 [작성자 기재 필요], [작성일 기재 필요] 로 표시한다.
    민사소송규칙 제105조 제1항이 요구하는 기재사항이라 빈칸으로 두지 않는다.
- 비고: "※ 각 호증은 원본을 소지하고 있으며, 필요 시 법원에 제출하겠습니다." 관례 문구로
  시작한다. 개별 증거에 [비고] 가 주어졌으면 "※ {호증번호}에는 …" 형식으로 줄을 덧붙인다.
- 관할법원: 재판부가 주어지면 "○○법원 ○○재판부 귀중", 없으면 "○○법원 귀중".

## 금지 사항
- 사용자가 제공하지 않은 증거를 추가하거나 제공된 증거를 빠뜨리지 않는다.
- 사용자가 제공하지 않은 사실을 지어내지 않는다.
- 날짜·서명란은 출력하지 않는다 (시스템이 별도 처리)."""


def build_user_prompt(d: EvidenceListInput) -> str:
    """EvidenceListInput 을 프롬프트 본문으로 조립한다.

    호증 번호는 AI 에 맡기지 않고 여기서 리스트 순서대로 확정해 전달한다.
    """
    submitter = SUBMITTER_ROLE_LABELS[d.submitter_role]
    prefix = EVIDENCE_PREFIX[d.submitter_role]

    lines = []
    for i, item in enumerate(d.evidence_items, start=d.evidence_start_no):
        label = f"{prefix} 제{i}호증"
        if item.branch_no:
            label += f"의 {item.branch_no}"
        parts = [
            f"- {label}",
            f"서증명: {item.name}",
            f"입증취지: {item.purpose or '미기재 - 제안 필요'}",
            f"원본: {ORIGINAL_LABELS[item.original_type]}",
            f"작성자: {item.author or '미기재'}",
            f"작성일: {item.date or '미기재'}",
        ]
        if item.note:
            parts.append(f"비고: {item.note}")
        lines.append(" | ".join(parts))
    items = "\n".join(lines)

    return f"""[사건 번호] {d.case_no}
[관할법원] {d.court}
[재판부] {d.panel or "미기재"}
[원고] {d.plaintiff}
[피고] {d.defendant}
[제출자] {submitter} ({prefix}호증)

[증거 목록 (번호 확정, 순서 변경 금지)]
{items}

위 정보로 증거목록을 작성하세요."""
