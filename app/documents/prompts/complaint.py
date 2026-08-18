"""소장 생성 프롬프트."""

from app.documents.schemas.complaint import (
    ClaimType,
    ComplaintInput,
    DemandMethod,
    LawsuitType,
    ValuationType,
)

# 소송 유형 enum → 한국어 라벨 (프롬프트 주입용)
LAWSUIT_TYPE_LABELS: dict[LawsuitType, str] = {
    LawsuitType.DEPOSIT_RETURN: "임대차보증금 반환",
    LawsuitType.LOAN_RETURN: "대여금 반환",
    LawsuitType.WAGE_CLAIM: "임금체불 청구",
    LawsuitType.DAMAGES: "손해배상",
    LawsuitType.BUILDING_SURRENDER: "건물명도 (미납월세·무단점거)",
}

# 건물 인도(명도) 청구가 주된 청구인 유형 — 청구취지 1항이 금전 지급이 아니다
SURRENDER_TYPES = {LawsuitType.BUILDING_SURRENDER}

CLAIM_TYPE_LABELS: dict[ClaimType, str] = {
    ClaimType.PROPERTY: "재산권상 청구",
    ClaimType.NON_PROPERTY: "비재산권상 청구",
}

VALUATION_TYPE_LABELS: dict[ValuationType, str] = {
    ValuationType.AMOUNT: "금액",
    ValuationType.LAND_VALUE: "토지 등의 평가액",
    ValuationType.UNCALCULABLE: "소가 산출 불가",
}

DEMAND_METHOD_LABELS: dict[DemandMethod, str] = {
    DemandMethod.CERTIFIED_MAIL: "내용증명 발송",
    DemandMethod.MESSAGE: "문자·카카오톡으로 요구",
    DemandMethod.VERBAL: "전화·구두로만 요구",
    DemandMethod.NONE: "요구한 적 없음",
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
- 사건명: 소송 유형에 맞는 관례적 명칭 (예: "임대차보증금반환 청구의 소", "건물명도 청구의 소").
- 소송목적의 값: "금 ○○○원" 형식.
  [소송 목적물 가액] 이 주어졌으면 **반드시 그 값**을 쓴다 (청구 금액과 달라도 그렇다).
  목적물 가액이 미기재일 때만 청구 금액을 쓴다.
  단 소가구분이 "소가 산출 불가"면 금액 대신 "소가 산출 불가"로 적는다.
- 당사자: 원고·피고를 각각 "원고 ○○○ / 주소" 형식으로. 주민등록번호는 쓰지 않는다.
  대표자·법정대리인이 주어지면 "피고 주식회사 ○○ / 대표이사 ○○○ / 주소" 로 병기한다.
  송달받을 주소나 팩스가 주어지면 해당 당사자 아래에 "송달장소: ○○○" 로 덧붙인다.

- 청구취지: 관례적 구성. **주된 청구의 성질에 따라 1항이 달라진다.**
  · 금전 청구(대여금·보증금·임금·손해배상)인 경우 1항은 금전 지급 청구로 쓴다.
  · 건물명도(인도) 청구인 경우 1항은 반드시
    "피고는 원고에게 별지 목록 기재 건물을 인도하라." 로 쓰고,
    미납 차임·관리비 등 금전 청구가 있으면 이를 2항의 금전 지급 청구로 잇는다.
  마지막에 "소송비용은 피고가 부담한다.", "제1항은 가집행할 수 있다." 를 각 항으로 붙이고
  마지막 줄은 "라는 판결을 구합니다."

- 지연손해금 기산일: 아래 순서로 **위에서부터** 판단한다. 앞 순위가 있으면 뒤 순위는 쓰지 않는다.
  1. [사실관계]에 변제기·이행기·지급기일에 해당하는 날짜가 있으면 **그 다음 날부터**.
     최고일(요구한 날)이 따로 있어도 변제기가 우선한다.
     예) 변제기 2026-05-01, 최고일 2026-07-19 → 기산일은 2026년 5월 2일.
  2. 변제기가 없을 때만, 최고일이 주어졌으면 그 다음 날부터.
  3. 둘 다 없으면 "이 사건 소장 부본 송달 다음 날부터".
  근거 없는 날짜를 지어내지 않는다.
  이율은 "다 갚는 날까지 연 12%의 비율로 계산한 돈"(소송촉진 등에 관한 특례법)을 기본으로 한다.

- 청구원인: "1. 당사자의 지위 → 2. 사건의 경위 → 3. 결론" 순서의 번호 목차로.
  [사실관계] 로 주어진 항목은 날짜·금액·조건을 그대로 살려 경위에 녹인다. 값을 바꾸지 않는다.
  [피고의 반응과 현재 상태] 가 주어지면 최고 경위와 불이행 사실로 나누어 정리한다.
  사용자의 일상 표현을 정확한 법률 문언으로 변환한다.
  인용할 판례가 주어지면 "(대법원 ○○다○○ 판결 참조)" 형식으로 자연스럽게 반영한다.
- 입증방법: 첨부 증거를 "1. 갑 제1호증  ○○○" 형식으로 순번을 붙여 나열. 증거가 없으면 사건 내용상 통상 필요한 증거를 제안하되 [확인 필요]를 붙인다.
- 첨부서류: "1. 위 입증방법  각 1통 / 2. 소장 부본  1통 / 3. 송달료 납부서  1통" 관례를 따른다.
  건물명도 등 인도 청구에는 "별지 목록" 을 첨부서류에 포함한다.
- 관할법원: "○○법원 귀중" 형식.

## 금지 사항
- 사용자가 제공하지 않은 사실(날짜·금액·계약 조건 등)을 지어내지 않는다. 빠진 정보는 [○○ 기재 필요] 로 표시한다.
- 날짜·서명란은 출력하지 않는다 (시스템이 별도 처리).
- 법률 자문이 아닌 초안 작성이므로 단정적 승소 표현을 쓰지 않는다."""


def _party_lines(parties: list) -> str:
    lines = []
    for p in parties:
        parts = [p.name, p.address]
        if p.representative:
            parts.insert(1, p.representative)
        if p.service_address:
            parts.append(f"송달장소 {p.service_address}")
        if p.fax:
            parts.append(f"팩스 {p.fax}")
        lines.append("- " + " / ".join(parts))
    return "\n".join(lines)


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
    facts = "\n".join(f"- {k}: {v}" for k, v in d.facts.items()) or "없음"

    claim_kind = (
        "건물 인도(명도) 청구"
        if d.lawsuit_type in SURRENDER_TYPES
        else "금전 지급 청구"
    )
    demand = DEMAND_METHOD_LABELS[d.demand_method] if d.demand_method else "미기재"
    repaid = {True: "일부 받음", False: "한 푼도 받지 못함", None: "미기재"}[
        d.partial_repaid
    ]

    return f"""[관할법원] {d.court}
[소송 유형] {LAWSUIT_TYPE_LABELS[d.lawsuit_type]}
[주된 청구의 성질] {claim_kind}
[청구구분] {CLAIM_TYPE_LABELS[d.claim_type] if d.claim_type else "미기재"}
[소가구분] {VALUATION_TYPE_LABELS[d.valuation_type] if d.valuation_type else "미기재"}
[청구 금액] {_won(d.claim_amount)}
[소송 목적물 가액] {_won(d.object_value)}

[원고]
{_party_lines(d.plaintiffs)}

[피고]
{_party_lines(d.defendants)}

[사실관계]
{facts}

[사건 경위 (사용자의 일상 언어)]
{d.cause_text}

[이행 요구]
- 일부 이행 여부: {repaid}
- 요구 방법: {demand}
- 요구한 날(최고일): {d.demand_date or "미기재"}

[피고의 반응과 현재 상태]
{d.response_text or "미기재"}

[첨부 증거]
{attachments}

[인용할 판례]
{precedents}

위 정보로 소장을 작성하세요."""


# 라벨 표는 enum 이 늘어나면 조용히 KeyError 를 내므로 import 시점에 정합성을 확인한다.
assert set(LAWSUIT_TYPE_LABELS) == set(LawsuitType)
assert set(CLAIM_TYPE_LABELS) == set(ClaimType)
assert set(VALUATION_TYPE_LABELS) == set(ValuationType)
assert set(DEMAND_METHOD_LABELS) == set(DemandMethod)
