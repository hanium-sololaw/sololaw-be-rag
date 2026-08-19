"""소장(complaint) 입력/출력 스키마."""

from enum import Enum

from pydantic import BaseModel, Field

from app.documents.schemas.common import CitedPrecedent, Party


class LawsuitType(str, Enum):
    """소송 유형 (step1 에서 선택)."""

    DEPOSIT_RETURN = "deposit_return"  # 임대차보증금 반환
    LOAN_RETURN = "loan_return"  # 대여금 반환
    WAGE_CLAIM = "wage_claim"  # 임금체불 청구
    DAMAGES = "damages"  # 손해배상
    BUILDING_SURRENDER = "building_surrender"  # 건물명도 (미납월세·무단점거)


class ClaimType(str, Enum):
    """청구구분 (정보입력 1단계)."""

    PROPERTY = "property"  # 재산권상 청구
    NON_PROPERTY = "non_property"  # 비재산권상 청구


class ValuationType(str, Enum):
    """소가구분 (정보입력 1단계)."""

    AMOUNT = "amount"  # 금액
    LAND_VALUE = "land_value"  # 토지 등의 평가액
    UNCALCULABLE = "uncalculable"  # 소가 산출 불가


class DemandMethod(str, Enum):
    """이행 요구(최고) 방법 (정보입력 5단계)."""

    CERTIFIED_MAIL = "certified_mail"  # 내용증명
    MESSAGE = "message"  # 문자·카카오톡
    VERBAL = "verbal"  # 전화·구두
    NONE = "none"  # 요구한 적 없음


class ComplaintInput(BaseModel):
    """소장 - 정보 입력 (위저드 1~6단계 결과를 한 번에 받는다)."""

    # 필드별 examples 를 Swagger 가 기계적으로 조립하면 원고·피고가 같은 사람이 되는 등
    # 앞뒤가 안 맞는 예시가 나오므로, 대여금 반환 한 건을 통째로 예시로 고정한다.
    model_config = {
        "json_schema_extra": {
            "example": {
                "court": "서울중앙지방법원",
                "lawsuit_type": "loan_return",
                "claim_type": "property",
                "valuation_type": "amount",
                "claim_amount": 3000000,
                "object_value": 3000000,
                "plaintiffs": [
                    {"name": "홍길동", "address": "서울특별시 서초구 서초대로 12"}
                ],
                "defendants": [
                    {"name": "김철수", "address": "서울특별시 강남구 테헤란로 5"}
                ],
                "facts": {
                    "빌려주기로 약속한 날": "2026-02-01",
                    "처음 빌려준 총액": "3,000,000원",
                    "실제로 돈을 건넨 날": "약속한 날 바로",
                    "교부 방법": "계좌이체",
                    "횟수": "한 번에 전부",
                    "변제기": "2026-05-01",
                    "이자 약정": "약정 없음",
                },
                "cause_text": "대학 동창인데 가게 보증금이 급하다고 해서 빌려줬어요. "
                "가게 계약이 끝나면 바로 갚겠다고 했어요.",
                "partial_repaid": False,
                "demand_method": "certified_mail",
                "demand_date": "2026-07-19",
                "response_text": "두 달만 기다려 달라고 했는데 아직도 갚지 않았어요.",
                "attachments": [
                    "차용증",
                    "계좌이체 내역",
                    "문자 메시지·카카오톡 대화내역",
                    "내용증명 우편물",
                ],
                "cited_precedents": [],
            }
        }
    }

    # --- 1단계: 어느 법원에 얼마를 청구하나요 ---
    court: str = Field(description="관할 법원", examples=["서울중앙지방법원"])
    lawsuit_type: LawsuitType = Field(
        description="소송 유형 (deposit_return=임대차보증금 반환, loan_return=대여금 반환, "
        "wage_claim=임금체불 청구, damages=손해배상, building_surrender=건물명도)",
        examples=["loan_return"],
    )
    claim_type: ClaimType | None = Field(
        None,
        description="청구구분 (property=재산권상, non_property=비재산권상)",
        examples=["property"],
    )
    valuation_type: ValuationType | None = Field(
        None,
        description="소가구분 (amount=금액, land_value=토지 등의 평가액, "
        "uncalculable=소가 산출 불가)",
        examples=["amount"],
    )
    claim_amount: int | None = Field(
        None, description="청구 금액(원)", examples=[3000000]
    )
    object_value: int | None = Field(
        None,
        description="소송 목적물 가액(원). 미기재 시 청구 금액 사용",
        examples=[3000000],
    )

    # --- 2단계: 누가 누구에게 청구하나요 ---
    plaintiffs: list[Party] = Field(description="원고 목록 (공동소송 시 여러 명)")
    defendants: list[Party] = Field(description="피고 목록")

    # --- 3~4단계: 유형별 사실관계 ---
    facts: dict[str, str] = Field(
        default={},
        description="유형별 구조화 입력을 {화면 질문/항목: 답} 으로 그대로 담는다. "
        "소송 유형마다 항목이 달라 스키마를 고정하지 않는다",
        examples=[
            {
                "빌려주기로 약속한 날": "2026-02-01",
                "처음 빌려준 총액": "3,000,000원",
                "교부 방법": "계좌이체",
                "변제기": "2026-05-01",
                "이자 약정": "약정 없음",
            }
        ],
    )
    cause_text: str = Field(
        description="사건 경위 (자유서술) — 일상 언어로 쓰면 AI가 법률 문언으로 변환",
        examples=[
            "대학 동창인데 가게 보증금이 급하다고 해서 빌려줬어요. 가게 계약이 끝나면 바로 갚겠다고 했어요."
        ],
    )

    # --- 5단계: 돌려받은 돈과 독촉 내용 ---
    partial_repaid: bool | None = Field(
        None, description="일부라도 변제·이행받았는지 여부", examples=[False]
    )
    demand_method: DemandMethod | None = Field(
        None,
        description="이행 요구(최고) 방법 (certified_mail=내용증명, message=문자·카카오톡, "
        "verbal=전화·구두, none=요구한 적 없음)",
        examples=["certified_mail"],
    )
    demand_date: str | None = Field(
        None,
        description="요구한 날(최고일). 지연손해금 기산일 판단에 쓰인다",
        examples=["2026-07-19"],
    )
    response_text: str | None = Field(
        None,
        description="피고의 반응과 현재 상태 (자유서술)",
        examples=["두 달만 기다려 달라고 했는데 아직도 갚지 않았어요."],
    )

    # --- 6단계: 가지고 있는 자료 ---
    attachments: list[str] = Field(
        default=[],
        description="첨부 증거 라벨 목록 — 입증방법(갑 호증) 작성에 반영",
        examples=[["차용증", "계좌이체 내역", "문자 메시지"]],
    )
    cited_precedents: list[CitedPrecedent] = Field(
        default=[], description="인용할 판례 목록 — 청구원인에 반영"
    )


class ComplaintSections(BaseModel):
    """소장 구조화 결과 (스트림 완료 시 파싱). PDF·편집용."""

    case_name: str = Field("", description="사건명 (예: 임대차보증금반환 청구의 소)")
    object_value: str = Field("", description="소송목적의 값 (예: 금 10,000,000원)")
    parties: str = Field("", description="당사자 표시 (원고/피고)")
    claim_purpose: str = Field(
        "", description="청구취지 (지급·인도명령·소송비용·가집행 3단)"
    )
    claim_cause: str = Field(
        "", description="청구원인 (당사자의 지위 → 사건의 경위 → 결론)"
    )
    evidence: str = Field("", description="입증방법 (갑 제N호증 목록)")
    attachments: str = Field("", description="첨부서류")
    court: str = Field("", description="관할법원 (○○법원 귀중)")
    annex: str = Field(
        "",
        description="별지 — 부동산의 표시. 건물명도처럼 목적물을 특정해야 하는 사건에만 "
        "값이 있고, 나머지는 '해당 없음'. 소장 본문과 별개로 첨부하는 서면이라 "
        "화면에서도 구분선 아래에 렌더링한다",
    )
