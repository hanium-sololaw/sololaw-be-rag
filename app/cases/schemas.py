"""판례 검색 도메인 스키마."""

from enum import Enum

from pydantic import BaseModel, Field


class CaseCategory(str, Enum):
    """사건 분야 필터 (전체는 미지정)."""

    CIVIL = "civil"  # 민사
    CRIMINAL = "criminal"  # 형사
    ADMINISTRATIVE = "administrative"  # 행정
    FAMILY = "family"  # 가사


class SearchRequest(BaseModel):
    """판례 검색 요청."""

    query: str = Field(description="검색 키워드", examples=["임대차 보증금 반환"])
    category: CaseCategory | None = Field(
        None,
        description="사건 분야 필터 (civil=민사, criminal=형사, "
        "administrative=행정, family=가사). 미지정 시 전체",
        examples=["civil"],
    )
    case_context: str | None = Field(
        None,
        description="진행 중인 사건 맥락 — 관련도·참고 포인트 정확도 향상",
        examples=["임대차 계약 종료 후 임대인이 보증금 1,000만원 반환을 거부하는 사건"],
    )
    limit: int = Field(
        5, ge=1, le=10, description="AI 분석해 반환할 판례 수 (기본 5, 최대 10)"
    )


class CaseCard(BaseModel):
    """판례 검색 결과 카드."""

    serial_id: str = Field(description="판례 일련번호 (국가법령정보센터)")
    name: str = Field(description="사건명")
    case_no: str = Field(description="사건번호")
    court: str = Field(description="법원명")
    decision_date: str = Field(description="선고일자")
    category: str = Field(description="사건종류명 (민사·형사 등)")
    relevance: int = Field(description="사건 맥락 대비 관련도 0~100 (AI 산출)")
    reference_note: str = Field(description="이 판례에서 참고할 수 있는 내용 (AI 요약)")
    detail_url: str = Field(description="원문보기 링크 (law.go.kr)")


class RelatedStatute(BaseModel):
    """관련 법령 — 검색된 판례들의 참조조문 집계."""

    name: str = Field(description="법령·조문 (예: 민법 제618조)")
    count: int = Field(description="검색된 판례 중 인용 횟수")


class SearchResponse(BaseModel):
    """판례 검색 응답."""

    total: int = Field(description="검색 API 전체 매칭 건수")
    cases: list[CaseCard] = Field(description="AI 분석된 판례 (관련도 내림차순)")
    statutes: list[RelatedStatute] = Field(description="관련 법령 (인용 횟수순)")


class RelevanceDraft(BaseModel):
    """LLM 관련도 산출 출력 (structured output 강제용)."""

    relevance: int
    reference_note: str
