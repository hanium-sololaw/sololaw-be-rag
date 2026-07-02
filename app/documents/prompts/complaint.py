"""소장 생성 프롬프트."""

from app.documents.schemas.complaint import ComplaintInput, LawsuitType

# 소송 유형 enum → 한국어 라벨 (프롬프트 주입용)
LAWSUIT_TYPE_LABELS: dict[LawsuitType, str] = {
    LawsuitType.DEPOSIT_RETURN: "임대차 보증금 반환",
    LawsuitType.WAGE_CLAIM: "임금 청구",
    LawsuitType.DAMAGES: "손해 배상",
    LawsuitType.CONTRACT_BREACH: "계약 위반",
    LawsuitType.LOAN_RETURN: "대여금 반환",
}

# 출력 마크다운 헤더 → ComplaintSections 필드명 (service 의 섹션 파싱용)
SECTION_MAP: dict[str, str] = {
    "사건명": "case_name",
    "소송목적의 값": "object_value",
    "당사자": "parties",
    "청구취지": "claim_purpose",
    "청구원인": "claim_cause",
    "입증방법": "evidence",
    "첨부서류": "attachments",
    "관할법원": "court",
}

SYSTEM = """당신은 대한민국 민사소송 '소장' 작성을 돕는 법률 문서 전문가입니다.
사용자가 제공한 정보만으로 법원 제출용 소장 초안을 작성합니다.

## 출력 형식 (반드시 준수)
아래 8개 섹션을 정확히 이 마크다운 헤더로, 이 순서대로 출력하세요.
다른 헤더를 만들거나 헤더를 생략하지 마세요. 헤더 외 인사말·설명·마무리 문구는 쓰지 마세요.

## 사건명
## 소송목적의 값
## 당사자
## 청구취지
## 청구원인
## 입증방법
## 첨부서류
## 관할법원

## 작성 규칙
- 사건명: 소송 유형에 맞는 관례적 명칭 (예: "임대차보증금반환 청구의 소").
- 소송목적의 값: "금 ○○○원" 형식. 미기재면 청구 금액을 사용.
- 당사자: 원고·피고를 각각 "원고 ○○○ / 주소" 형식으로. 주민등록번호는 쓰지 않는다.
- 청구취지: 관례적 3단 구성.
  1. 금전 지급 청구 — 지연이자는 "이 사건 소장 부본 송달 다음 날부터 다 갚는 날까지 연 12%의 비율로 계산한 돈"(소송촉진 등에 관한 특례법)을 기본으로 한다.
  2. "소송비용은 피고가 부담한다."
  3. "제1항은 가집행할 수 있다."
  마지막 줄은 "라는 판결을 구합니다."
- 청구원인: "1. 당사자의 지위 → 2. 사건의 경위 → 3. 결론" 순서의 번호 목차로.
  사용자의 일상 표현을 정확한 법률 문언으로 변환한다.
  인용할 판례가 주어지면 사건의 경위 또는 결론에 "(대법원 ○○다○○ 판결 참조)" 형식으로 자연스럽게 반영한다.
- 입증방법: 첨부 증거를 "1. 갑 제1호증  ○○○" 형식으로 순번을 붙여 나열. 증거가 없으면 사건 내용상 통상 필요한 증거를 제안하되 [확인 필요]를 붙인다.
- 첨부서류: "1. 위 입증방법  각 1통 / 2. 소장 부본  1통 / 3. 송달료 납부서  1통" 관례를 따른다.
- 관할법원: "○○법원 귀중" 형식.

## 금지 사항
- 사용자가 제공하지 않은 사실(날짜·금액·계약 조건 등)을 지어내지 않는다. 빠진 정보는 [○○ 기재 필요] 로 표시한다.
- 날짜·서명란은 출력하지 않는다 (시스템이 별도 처리).
- 법률 자문이 아닌 초안 작성이므로 단정적 승소 표현을 쓰지 않는다."""


def _party_lines(parties) -> str:
    return "\n".join(f"- {p.name} / {p.address}" for p in parties)


def _won(amount: int | None) -> str:
    return f"{amount:,}원" if amount is not None else "미기재"


def build_user_prompt(d: ComplaintInput) -> str:
    """ComplaintInput 을 프롬프트 본문으로 조립한다. (주민등록번호는 제외)"""
    precedents = (
        "\n".join(
            f"- {p.case_no}" + (f": {p.summary}" if p.summary else "")
            for p in d.cited_precedents
        )
        or "없음"
    )
    attachments = "\n".join(f"- {a}" for a in d.attachments) or "없음"

    return f"""[관할법원] {d.court}
[소송 유형] {LAWSUIT_TYPE_LABELS[d.lawsuit_type]}
[청구 금액] {_won(d.claim_amount)}
[소송 목적물 가액] {_won(d.object_value)}

[원고]
{_party_lines(d.plaintiffs)}

[피고]
{_party_lines(d.defendants)}

[사건 설명 (사용자의 일상 언어)]
{d.cause_text}

[핵심 날짜] {d.key_dates or "미기재"}

[첨부 증거]
{attachments}

[인용할 판례]
{precedents}

위 정보로 소장을 작성하세요."""
