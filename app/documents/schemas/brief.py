"""준비서면(brief) 입력/출력 스키마."""

from enum import Enum

from pydantic import BaseModel, Field

from app.documents.schemas.complaint import CitedPrecedent


class SubmitterRole(str, Enum):
    """준비서면 제출자가 사건에서 갖는 지위."""

    PLAINTIFF = "plaintiff"  # 원고
    DEFENDANT = "defendant"  # 피고


class BriefInput(BaseModel):
    """준비서면 - 정보 입력 (step2)."""

    case_no: str = Field(
        description="사건 번호", examples=["2024가단123456 임대차보증금반환"]
    )
    court: str = Field(
        description="사건이 계속 중인 법원", examples=["서울중앙지방법원"]
    )
    plaintiff: str = Field(description="원고 이름", examples=["홍길동"])
    defendant: str = Field(description="피고 이름", examples=["김철수"])
    submitter_role: SubmitterRole = Field(
        default=SubmitterRole.PLAINTIFF,
        description="준비서면 제출자가 원고/피고 중 누구인지 (기본 원고)",
        examples=["plaintiff"],
    )
    panel: str | None = Field(None, description="담당 재판부", examples=["민사 3단독"])
    hearing_date: str | None = Field(
        None, description="다음 변론기일", examples=["2026-07-15"]
    )
    opponent_claim: str = Field(
        description="반박할 상대방 주장 — 답변서 내용 붙여넣기 또는 핵심 요약",
        examples=[
            "임대차 계약이 묵시적으로 갱신되었으므로 보증금을 반환할 의무가 없다고 주장합니다."
        ],
    )
    rebuttal_points: list[str] = Field(
        default=[],
        description="반박 포인트 (사실관계 오류, 법리 해석 차이, 증거 부족 지적, "
        "시효·기한 문제, 당사자 적격 등)",
        examples=[["사실관계 오류", "법리 해석 차이"]],
    )
    my_argument: str | None = Field(
        None,
        description="추가로 주장할 내용 — 일상 언어로 쓰면 AI가 법률 문언으로 변환",
        examples=["계약 끝나기 두 달 전에 내용증명으로 갱신 안 한다고 알렸어요."],
    )
    new_evidence: list[str] = Field(
        default=[],
        description="새로운 증거 라벨 목록 — 입증방법 작성에 반영",
        examples=[["내용증명 우편"]],
    )
    evidence_note: str | None = Field(
        None,
        description="증거 설명 — 이 증거가 왜 중요한지",
        examples=["계약 종료 2개월 전에 갱신 거절 의사를 통지한 사실 입증"],
    )
    cited_precedents: list[CitedPrecedent] = Field(
        default=[], description="인용할 판례 목록 — 반박·결론에 반영"
    )


class BriefSections(BaseModel):
    """준비서면 구조화 결과 (스트림 완료 시 파싱). PDF·편집용."""

    case_info: str = Field("", description="사건 표시 (사건번호·원고·피고)")
    opponent_summary: str = Field("", description="상대방 주장의 요지")
    rebuttal: str = Field("", description="반박")
    conclusion: str = Field("", description="결론")
    evidence: str = Field("", description="입증방법")
    court: str = Field("", description="관할법원 (○○법원 귀중)")
