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
    "별지": "annex",
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
## 별지

## 작성 규칙
- 사건명: 소송 유형에 맞는 관례적 명칭 (예: "임대차보증금반환 청구의 소", "건물명도 청구의 소").
  **손해배상은 법원 사건부호를 괄호로 붙인다.** [사실관계] 의 사건 종류 값을 그대로 옮긴다.
  일반=`손해배상(기)` · 교통사고=`손해배상(자)` · 산업재해=`손해배상(산)` · 의료=`손해배상(의)`.
  값이 없으면 `손해배상(기)` 로 쓴다.
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
    "피고는 원고에게 별지 목록 기재 부동산을 인도하라." 로 쓰고,
    2항은 미납 차임에 더해 **인도할 때까지 발생할 차임 상당액**을 함께 구한다.
    "피고는 원고에게 {미납 합계}원 및 이 사건 소장 부본 송달일 다음 날부터 위 부동산
    인도 완료일까지 월 {월 차임}원의 비율에 의한 돈을 지급하라."
    (인도 완료일까지의 차임 상당 부당이득을 빠뜨리지 않는다)
  마지막에 "소송비용은 피고가 부담한다.", "제1항은 가집행할 수 있다." 를 각 항으로 붙이고
  마지막 줄은 "라는 판결을 구합니다."
  **청구취지의 항 번호는 1. 2. 3. 으로 올려 쓴다** (아래 입증방법·첨부서류의 "1." 반복
  관행은 청구취지에 적용하지 않는다).

- 지연손해금 **기산일**: 소송 유형마다 다르다. 아래 유형별 기준일을 먼저 보고,
  해당 날짜가 [사실관계]에 없을 때만 최고일(요구한 날) → 소장 부본 송달일 순으로 내려간다.
  | 소송 유형 | 기산일 |
  |---|---|
  | 대여금 반환 | 변제기 다음 날 (변제기를 정하지 않았으면 최고일 다음 날) |
  | 임대차보증금 반환 | 목적물을 인도한 날 (아직 살고 있으면 인도와 동시이행이므로 소장 부본 송달 다음 날) |
  | 손해배상 | 불법행위일(사고일) |
  | 임금체불 (퇴사) | 퇴직일부터 14일이 지난 다음 날 (근로기준법 제36조). **날짜를 더하지 말고 퇴직일을 그대로 넣어** "2026. 6. 30.로부터 14일이 지난 다음 날부터" 형식으로 쓴다 |
  | 임금체불 (재직 중) | 각 급여 지급일 다음 날 |
  | 건물명도 | 소장 부본 송달 다음 날 |
  근거 없는 날짜를 지어내지 않는다.

- 지연손해금 **이율**: 원칙적으로 **2단 구조**로 쓴다.
  "…부터 이 사건 소장 부본 송달일까지는 연 5%, 그 다음 날부터 다 갚는 날까지는
  연 12%의 각 비율로 계산한 돈을 지급하라."
  앞의 연 5%는 민법 법정이율, 뒤의 연 12%는 소송촉진 등에 관한 특례법 이율이다.
  · 약정이율이 주어졌으면 앞부분을 그 이율로 바꾼다.
  · **임금체불은 재직 여부로 갈린다.** [사실관계] 의 근무 상태 값을 본다.
    - **퇴사한 경우**: 연 20% 단일 이율 (근로기준법 제37조는 퇴직 근로자의 미지급
      임금에 적용된다). 2단으로 쓰지 않는다.
    - **아직 근무 중인 경우**: 20% 를 쓰지 않는다. 위 2단 구조(연 5% → 연 12%)를
      그대로 쓰고, 기산일은 급여 지급일 다음 날로 한다. 못 받은 달이 여럿이면
      **가장 이른 지급일 다음 날**을 기산일로 삼는다.
      앞 구간의 끝은 **언제나 "이 사건 소장 부본 송달일"** 이다. 다른 날짜를 넣지 않는다.
      예) "2026. 5. 26.부터 이 사건 소장 부본 송달일까지는 연 5%, 그 다음 날부터 …"
    근무 상태가 미기재면 퇴사로 단정하지 말고 2단 구조를 쓴다.
  · 기산일이 소장 부본 송달 다음 날이면 앞 구간이 없으므로 연 12% 단일로 쓴다.

- 청구원인: "1. 당사자의 지위 → 2. 사건의 경위 → 3. 결론" 순서의 번호 목차로.
  청구의 근거와 결론은 [청구원인 구성] 을 따른다. 다른 소송 유형의 책임 구성
  (예: 대여금·임금 사건에 불법행위·손해배상 책임)을 끌어오지 않는다.
  [사실관계] 로 주어진 항목은 날짜·금액·조건을 그대로 살려 경위에 녹인다. 값을 바꾸지 않는다.
  [피고의 반응과 현재 상태] 가 주어지면 최고 경위와 불이행 사실로 나누어 정리한다.
  사용자의 일상 표현을 정확한 법률 문언으로 변환한다.
  인용할 판례가 주어지면 "(대법원 ○○다○○ 판결 참조)" 형식으로 자연스럽게 반영한다.
- 입증방법: 첨부 증거를 "1. 갑 제1호증  ○○○" 형식으로 나열한다.
  법률문서 관행상 **줄머리 번호는 모두 "1." 로 쓰고** 호증 번호만 1·2·3 으로 올린다.
    1. 갑 제1호증  임대차계약서
    1. 갑 제2호증  보증금 입금증
  증거가 없으면 사건 내용상 통상 필요한 증거를 제안하되 [확인 필요]를 붙인다.
- 첨부서류: 줄머리 번호를 모두 "1." 로 쓰고 아래 관례를 따른다.
    1. 위 입증방법  각 1통
    1. 소장 부본  1통
    1. 송달료 납부서  1통
    1. 주민등록초본  1통
  건물명도 등 인도 청구에는 "부동산 등기사항증명서" 를 포함한다.
- 관할법원: "○○법원 귀중" 형식.
- 별지: **건물명도처럼 부동산을 특정해야 하는 사건에서만** 쓴다. "부동산의 표시" 라는
  줄 뒤에 [사실관계]의 부동산 표시를 등기부 표기대로 옮겨 적는다.
  부동산이 목적물이 아닌 사건(대여금·임금·손해배상 등)은 이 헤더 아래에
  "해당 없음" 한 줄만 적는다. 별지는 소장 본문과 별개로 첨부하는 서면이다.

## 금지 사항
- 사용자가 제공하지 않은 사실(날짜·금액·계약 조건 등)을 지어내지 않는다. 빠진 정보는 [○○ 기재 필요] 로 표시한다.
- 날짜·서명란은 출력하지 않는다 (시스템이 별도 처리).
- 판례는 입력된 청구를 뒷받침하는 참고자료다. 판례가 다루는 쟁점에 해당하는 주장에만
  인용하고, 판례에 맞춰 사실관계·청구 구성·책임의 근거를 새로 만들거나 바꾸지 않는다.
- 법률 자문이 아닌 초안 작성이므로 단정적 승소 표현을 쓰지 않는다."""


# 청구원인의 근거·결론은 소송 유형마다 다르다. 공통 규칙에 한 유형의 문장을 두면 다른
# 유형에도 옮겨 쓰므로(대여금 소장에 "불법행위에 해당하므로…") 해당 유형 것만 주입한다.
CAUSE_RULES: dict[LawsuitType, str] = {
    LawsuitType.LOAN_RETURN: """금전소비대차(민법 제598조)에 따른 대여금 반환 청구로 구성한다.
대여 사실 → 변제기 도래 → 변제 요구와 불이행 순으로 쓴다.
결론 예) "따라서 피고는 원고에게 대여금 ○○원을 반환하고, 이에 대한 지연손해금을 지급할 의무가 있습니다." """,
    LawsuitType.DEPOSIT_RETURN: """임대차 종료에 따른 임대차보증금 반환 청구로 구성한다.
계약 체결·보증금 지급 → 임대차 종료 → 목적물 인도(또는 인도와 동시이행) → 반환 거부 순으로 쓴다.
결론 예) "따라서 피고는 원고에게 임대차보증금 ○○원을 반환하고, 이에 대한 지연손해금을 지급할 의무가 있습니다." """,
    LawsuitType.WAGE_CLAIM: """근로계약에 따른 미지급 임금 지급 청구로 구성한다.
근로 제공 → 임금 미지급(기간·금액) → (퇴사한 경우) 퇴직 순으로 쓴다.
결론 예) "따라서 피고는 원고에게 미지급 임금 ○○원 및 이에 대한 지연이자를 지급할 의무가 있습니다." """,
    LawsuitType.DAMAGES: """손해배상 청구다. 책임의 근거는 입력된 청구 근거를 따르고 단정하지 않는다.
[사실관계] 의 계약 관계 값을 본다.
· 계약 관계 없음(사고 등) → 불법행위 책임(민법 제750조).
  결론 예) "이는 피고의 불법행위에 해당하므로, 피고는 원고가 입은 손해를 배상할 책임이 있습니다."
· 계약 관계 있음(계약 위반) → 채무불이행 책임(민법 제390조).
  결론 예) "피고는 위 계약상 의무를 이행하지 아니하였으므로, 그로 인한 손해를 배상할 책임이 있습니다."
· 값이 없으면 [사건 경위] 에 드러난 근거를 따르고, 판단할 수 없으면 [책임 근거 기재 필요] 로 표시한다.
둘을 섞어 쓰지 않는다.""",
    LawsuitType.BUILDING_SURRENDER: """임대차 종료(해지)에 따른 건물 인도 청구와 차임 관련 금전 청구로 구성한다.
계약 체결 → 차임 연체 등 종료(해지) 사유 → 종료(해지) 통지 → 인도 거부 순으로 쓴다.
인도 청구와 금전 청구(미납 차임, 인도 완료일까지의 차임 상당 부당이득)를 구분해 쓴다.
결론 예) "따라서 피고는 원고에게 별지 목록 기재 부동산을 인도하고, 미납 차임 ○○원 및 인도 완료일까지 월 ○○원의 비율에 의한 차임 상당액을 지급할 의무가 있습니다." """,
}


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

[청구원인 구성]
{CAUSE_RULES[d.lawsuit_type]}

[첨부 증거]
{attachments}

[인용할 판례]
{precedents}

위 정보로 소장을 작성하세요."""


# 라벨 표는 enum 이 늘어나면 조용히 KeyError 를 내므로 import 시점에 정합성을 확인한다.
assert set(LAWSUIT_TYPE_LABELS) == set(LawsuitType)
assert set(CAUSE_RULES) == set(LawsuitType)
assert set(CLAIM_TYPE_LABELS) == set(ClaimType)
assert set(VALUATION_TYPE_LABELS) == set(ValuationType)
assert set(DEMAND_METHOD_LABELS) == set(DemandMethod)
