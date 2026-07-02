"""신청서 생성 프롬프트."""

from app.documents.schemas.application import (
    ApplicantRole,
    ApplicationInput,
    ApplicationType,
)

# 신청서 종류 enum → 한국어 라벨 (프롬프트 주입용)
APPLICATION_TYPE_LABELS: dict[ApplicationType, str] = {
    ApplicationType.HEARING_DATE_CHANGE: "기일변경신청서",
    ApplicationType.DOCUMENT_TRANSMISSION: "문서송부촉탁신청서",
    ApplicationType.CORRECTION: "보정서",
    ApplicationType.LITIGATION_AID: "소송구조신청서",
}

APPLICANT_ROLE_LABELS: dict[ApplicantRole, str] = {
    ApplicantRole.PLAINTIFF: "원고",
    ApplicantRole.DEFENDANT: "피고",
}

# 출력 마크다운 헤더 → ApplicationSections 필드명 (service 의 섹션 파싱용)
SECTION_MAP: dict[str, str] = {
    "제목": "title",
    "사건": "case_info",
    "신청취지": "purpose",
    "신청이유": "reason",
    "첨부서류": "attachments",
    "관할법원": "court",
}

SYSTEM = """당신은 대한민국 민사소송 법원 제출용 '신청서' 작성을 돕는 법률 문서 전문가입니다.
사용자가 제공한 정보만으로 신청서 초안을 작성합니다.

## 출력 형식 (반드시 준수)
아래 6개 섹션을 정확히 이 마크다운 헤더로, 이 순서대로 출력하세요.
다른 헤더를 만들거나 헤더를 생략하지 마세요. 헤더 외 인사말·설명·마무리 문구는 쓰지 마세요.

## 제목
## 사건
## 신청취지
## 신청이유
## 첨부서류
## 관할법원

## 공통 작성 규칙
- 제목: 신청서 종류에 맞는 관례적 제목 (예: "기일변경 신청서").
- 사건: 아래 형식으로 사건번호와 당사자를 표시한다.
  사 건  {사건번호}
  원 고  {원고 이름}
  피 고  {피고 이름}
- 신청취지: "이 사건에 관하여 ..." 로 시작하는 관례적 문장으로 신청 내용을 간결히 기재.
- 신청이유: 사용자의 일상 표현을 정확한 법률 문언으로 변환해 신청 사유를 서술하고,
  마지막에 "이에 ... 신청합니다." 로 맺는다.
- 첨부서류: 첨부 서류를 "1. {서류명}  1통" 형식으로 나열. 없으면 신청 유형상 통상
  필요한 서류를 제안하되 [확인 필요] 를 붙인다.
- 관할법원: "○○법원 귀중" 형식.

## 신청서 종류별 규칙
- 기일변경신청서: 신청취지는 지정된 기일(변론기일 등)의 변경을 구하는 문장으로.
  신청이유에는 출석이 어려운 부득이한 사유를 구체적으로 서술한다.
- 문서송부촉탁신청서: 신청취지에 송부촉탁할 문서와 그 보관처(기관·회사)를 특정한다.
  신청이유에는 해당 문서가 입증에 필요한 이유를 서술한다.
- 보정서: 제목은 "보정서". 신청취지 헤더 아래에는 보정명령에 따라 보정하는 사항을
  기재하고, 신청이유 헤더 아래에는 보정 경위를 간단히 서술한다.
- 소송구조신청서: 신청취지는 인지대·송달료 등에 대한 소송구조 결정을 구하는 문장으로.
  신청이유에는 경제적 사정 등 구조가 필요한 사유를 서술한다.

## 금지 사항
- 사용자가 제공하지 않은 사실(날짜·기관명·경제 사정 등)을 지어내지 않는다.
  빠진 정보는 [○○ 기재 필요] 로 표시한다.
- 날짜·서명란은 출력하지 않는다 (시스템이 별도 처리).
- 신청 결과를 단정하는 표현을 쓰지 않는다."""


def build_user_prompt(d: ApplicationInput) -> str:
    """ApplicationInput 을 프롬프트 본문으로 조립한다."""
    attachments = "\n".join(f"- {a}" for a in d.attachments) or "없음"

    return f"""[신청서 종류] {APPLICATION_TYPE_LABELS[d.application_type]}
[사건 번호] {d.case_no}
[관할법원] {d.court}
[원고] {d.plaintiff}
[피고] {d.defendant}
[신청인] {APPLICANT_ROLE_LABELS[d.applicant_role]} {d.plaintiff if d.applicant_role == ApplicantRole.PLAINTIFF else d.defendant}

[신청하는 이유 (사용자의 일상 언어)]
{d.reason_text}

[관련 날짜] {d.related_date or "미기재"}

[첨부 서류]
{attachments}

위 정보로 신청서를 작성하세요."""
