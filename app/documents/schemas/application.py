"""신청서(application) 입력 스키마.

신청서는 사건 유형이 아니라 '절차적 목적' 으로 갈린다. 종류마다 필요한 입력과
완성 문서의 섹션 구성이 서로 달라, 소장처럼 사실관계를 facts 로 받고
출력 섹션도 종류별 스펙(prompts/application.py)에 맡긴다.
"""

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.documents.schemas.common import CitedPrecedent, Party


class ApplicationType(str, Enum):
    """신청서 종류 — 화면 목록과 1:1."""

    PAYMENT_ORDER = "payment_order"  # 지급명령신청서
    LITIGATION_AID = "litigation_aid"  # 소송구조신청서
    LEASE_REGISTRATION = "lease_registration"  # 임차권등기명령신청서
    ENFORCEMENT = "enforcement"  # 강제집행신청서
    PROVISIONAL_SEIZURE = "provisional_seizure"  # 가압류신청서


# 상대방 없이 법원에만 내는 신청서 (respondent 불필요)
SOLO_TYPES = {ApplicationType.LITIGATION_AID}


class ApplicationInput(BaseModel):
    """신청서 - 정보 입력 (위저드 결과를 한 번에 받는다)."""

    model_config = {
        "json_schema_extra": {
            "example": {
                "application_type": "payment_order",
                "court": "서울중앙지방법원",
                "claim_amount": 10000000,
                "applicant": {
                    "name": "홍길동",
                    "address": "서울특별시 동작구 상도로 200 1102호",
                    "phone": "010-2841-7306",
                },
                "respondent": {
                    "name": "김철수",
                    "address": "서울특별시 강남구 테헤란로 152 1204호",
                    "phone": "010-9274-1185",
                },
                "facts": {
                    "청구 종류": "대여금",
                    "채권 발생일": "2023-05-10",
                    "변제기": "2024-05-10",
                    "이자·지연손해금": "청구함",
                },
                "narrative": "2023년 5월에 빌려준 돈인데 갚기로 한 날이 지나도 "
                "안 갚고 연락도 잘 안 받아요.",
                "attachments": ["차용증·계약서", "계좌이체 내역", "내용증명 우편물"],
                "cited_precedents": [],
            }
        }
    }

    application_type: ApplicationType = Field(
        description="신청서 종류 (payment_order=지급명령, litigation_aid=소송구조, "
        "lease_registration=임차권등기명령, enforcement=강제집행, "
        "provisional_seizure=가압류)",
        examples=["payment_order"],
    )
    court: str = Field(
        description="신청할 법원. 종류마다 관할이 다르다 — 지급명령은 채무자 주소지",
        examples=["서울중앙지방법원"],
    )

    applicant: Party = Field(
        description="신청하는 쪽. 종류에 따라 채권자·신청인·임차인으로 표시된다"
    )
    respondent: Party | None = Field(
        None,
        description="상대방. 종류에 따라 채무자·피신청인·임대인으로 표시된다. "
        "소송구조신청서는 상대방이 없어 생략한다",
    )

    case_no: str | None = Field(
        None,
        description="사건번호. 소송구조는 계속 중인 사건, 강제집행은 집행권원의 사건",
        examples=["2024가단123456"],
    )
    case_name: str | None = Field(
        None,
        description="사건명 (소송구조신청서)",
        examples=["임대차 보증금 반환 청구"],
    )
    claim_amount: int | None = Field(
        None,
        description="청구·집행 금액(원). 지급명령·강제집행·가압류에서 쓴다",
        examples=[10000000],
    )

    facts: dict[str, str] = Field(
        default={},
        description="종류별 구조화 입력을 {화면 항목: 답} 으로 그대로 담는다. "
        "신청서마다 묻는 항목이 달라 스키마를 고정하지 않는다",
        examples=[{"청구 종류": "대여금", "채권 발생일": "2023-05-10"}],
    )
    narrative: str = Field(
        description="신청 사유 자유서술 — 일상 언어로 쓰면 AI 가 법률 문언으로 변환",
        examples=["갚기로 한 날이 지나도 안 갚고 연락도 잘 안 받아요."],
    )

    attachments: list[str] = Field(
        default=[],
        description="함께 낼 서류 라벨 목록",
        examples=[["차용증·계약서", "계좌이체 내역"]],
    )
    cited_precedents: list[CitedPrecedent] = Field(
        default=[],
        description="인용할 판례. 임차권등기명령신청서의 '관련 법리' 섹션에 반영된다",
    )

    @model_validator(mode="after")
    def _require_respondent(self):
        """상대방이 있는 신청서인데 respondent 가 비면 당사자 표시를 못 만든다."""
        if self.application_type not in SOLO_TYPES and self.respondent is None:
            raise ValueError("이 신청서 종류는 상대방(respondent) 정보가 필요합니다.")
        return self
