"""소장(complaint) 입력/출력 스키마."""

from enum import Enum

from pydantic import BaseModel


class LawsuitType(str, Enum):
    """소송 유형 (드롭다운)."""

    DEPOSIT_RETURN = "deposit_return"  # 임대차 보증금 반환
    WAGE_CLAIM = "wage_claim"  # 임금 청구
    DAMAGES = "damages"  # 손해 배상
    CONTRACT_BREACH = "contract_breach"  # 계약 위반
    LOAN_RETURN = "loan_return"  # 대여금 반환


class Party(BaseModel):
    """당사자 (원고/피고). 공동소송 대비 리스트로 받는다."""

    name: str  # 이름/상호 *
    resident_id: str | None = None  # 주민등록번호 (민감 — LLM에 전달하지 않음)
    address: str  # 주소 *


class CitedPrecedent(BaseModel):
    """인용할 판례 (판례 검색에서 담아온 것). 1차는 텍스트만, 추후 판례검색 도메인 연동."""

    case_no: str  # 사건번호 (예: 대법원 2020다12345)
    summary: str | None = None  # 판례 요지


class ComplaintInput(BaseModel):
    """소장 - 정보 입력 (step2)."""

    court: str  # 법원 선택 *
    lawsuit_type: LawsuitType  # 소송 유형 *
    claim_amount: int | None = None  # 청구 금액(원)
    object_value: int | None = None  # 소송 목적물 가액(원)
    plaintiffs: list[Party]  # 원고(나)
    defendants: list[Party]  # 피고(상대방)
    cause_text: str  # "어떤 일이 있었나요?" (자연어) *
    key_dates: str | None = None  # 핵심 날짜
    attachments: list[str] = []  # 첨부 증거 라벨 (1차는 이름만, 파일 분석은 추후)
    cited_precedents: list[CitedPrecedent] = []  # 인용할 판례


class ComplaintSections(BaseModel):
    """소장 구조화 결과 (스트림 완료 시 파싱). PDF·편집용."""

    case_name: str = ""  # 사건명 (예: 임대차보증금반환 청구의 소)
    object_value: str = ""  # 소송목적의 값
    parties: str = ""  # 당사자 표시 (원고/피고)
    claim_purpose: str = ""  # 청구취지
    claim_cause: str = ""  # 청구원인
    evidence: str = ""  # 입증방법 (갑 제N호증)
    attachments: str = ""  # 첨부서류
    court: str = ""  # 관할법원 (○○법원 귀중)
