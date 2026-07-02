"""소장(complaint) 입력/출력 스키마."""

from enum import Enum

from pydantic import BaseModel, Field


class LawsuitType(str, Enum):
    """소송 유형 (드롭다운)."""

    DEPOSIT_RETURN = "deposit_return"  # 임대차 보증금 반환
    WAGE_CLAIM = "wage_claim"  # 임금 청구
    DAMAGES = "damages"  # 손해 배상
    CONTRACT_BREACH = "contract_breach"  # 계약 위반
    LOAN_RETURN = "loan_return"  # 대여금 반환


class Party(BaseModel):
    """당사자 (원고/피고). 공동소송 대비 리스트로 받는다."""

    name: str = Field(description="이름 또는 상호", examples=["홍길동"])
    resident_id: str | None = Field(
        None,
        description="주민등록번호 (선택). LLM에는 전달되지 않으며 문서 표시는 프론트에서 처리",
        examples=["900101-1234567"],
    )
    address: str = Field(
        description="주소 (도로명)", examples=["서울특별시 서초구 서초대로 12"]
    )


class CitedPrecedent(BaseModel):
    """인용할 판례 (판례 검색에서 담아온 것). 1차는 텍스트만, 추후 판례검색 도메인 연동."""

    case_no: str = Field(description="사건번호", examples=["대법원 2020다12345"])
    summary: str | None = Field(
        None, description="판례 요지", examples=["임대차 종료 시 보증금 반환 의무"]
    )


class ComplaintInput(BaseModel):
    """소장 - 정보 입력 (step2)."""

    court: str = Field(description="관할 법원", examples=["서울중앙지방법원"])
    lawsuit_type: LawsuitType = Field(
        description="소송 유형 (deposit_return=임대차 보증금 반환, wage_claim=임금 청구, "
        "damages=손해 배상, contract_breach=계약 위반, loan_return=대여금 반환)",
        examples=["deposit_return"],
    )
    claim_amount: int | None = Field(
        None, description="청구 금액(원)", examples=[10000000]
    )
    object_value: int | None = Field(
        None,
        description="소송 목적물 가액(원). 미기재 시 청구 금액 사용",
        examples=[10000000],
    )
    plaintiffs: list[Party] = Field(description="원고 목록 (공동소송 시 여러 명)")
    defendants: list[Party] = Field(description="피고 목록")
    cause_text: str = Field(
        description="어떤 일이 있었나요? — 일상 언어로 쓰면 AI가 법률 문언으로 변환",
        examples=[
            "2년 전에 전세 계약을 했고 올해 3월에 계약이 끝났는데 집주인이 보증금을 안 돌려주고 있어요."
        ],
    )
    key_dates: str | None = Field(
        None,
        description="핵심 날짜 (사건 발생일, 계약일 등)",
        examples=["계약일 2024-03-01, 계약 종료일 2026-03-01"],
    )
    attachments: list[str] = Field(
        default=[],
        description="첨부 증거 라벨 목록 — 입증방법(갑 호증) 작성에 반영. 파일 내용 분석은 추후 지원",
        examples=[["임대차계약서", "카카오톡 대화 캡처"]],
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
        "", description="청구취지 (지급명령·소송비용·가집행 3단)"
    )
    claim_cause: str = Field(
        "", description="청구원인 (당사자의 지위 → 사건의 경위 → 결론)"
    )
    evidence: str = Field("", description="입증방법 (갑 제N호증 목록)")
    attachments: str = Field("", description="첨부서류")
    court: str = Field("", description="관할법원 (○○법원 귀중)")
