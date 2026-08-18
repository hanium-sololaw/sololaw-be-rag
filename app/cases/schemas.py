"""판례 검색 도메인 스키마."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# 원고 기준 승패. 판례 카드 배지와 승소율 통계가 같은 분류를 공유한다.
Outcome = Literal["win", "partial", "lose", "unknown"]


class CaseCategory(str, Enum):
    """검색 필터 칩 (전체는 미지정).

    민사는 법원의 사건종류명이고, 대여금·임대차는 그 안의 사건 주제다.
    나홀로 소송이 민사만 다루므로 형사·행정·가사는 두지 않는다.
    """

    CIVIL = "civil"  # 민사 전체
    LOAN = "loan"  # 대여금
    LEASE = "lease"  # 임대차


class _SearchBase(BaseModel):
    """검색·통계 공통 입력 — query 또는 case_context 중 하나는 필수."""

    query: str | None = Field(
        None,
        description="검색 키워드 (키워드 검색 탭). 없으면 case_context 에서 AI 가 추출",
        examples=["임대차 보증금 반환"],
    )
    category: CaseCategory | None = Field(
        None,
        description="검색 필터 칩 (civil=민사, loan=대여금, lease=임대차). "
        "미지정·빈값 시 전체. 대여금·임대차는 민사 안에서 사건명으로 한 번 더 좁힌다. "
        "내 사건 기반 탭은 프론트가 사건 유형으로 자동 지정 권장",
        examples=["loan"],
    )
    case_context: str | None = Field(
        None,
        description="진행 중인 사건 맥락 (내 사건 기반 탭) — 관련도 산출·키워드 추출에 사용",
        examples=["임대차 계약 종료 후 임대인이 보증금 1,000만원 반환을 거부하는 사건"],
    )

    @field_validator("category", mode="before")
    @classmethod
    def _blank_category_as_none(cls, v):
        """빈 문자열·공백 category 는 전체(미지정)로 취급 — 프론트 select 빈값 대응."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _require_query_or_context(self):
        if not (self.query and self.query.strip()) and not (
            self.case_context and self.case_context.strip()
        ):
            raise ValueError("query 또는 case_context 중 하나는 필요합니다.")
        return self


class SearchRequest(_SearchBase):
    """판례 검색 요청."""

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
    outcome: Outcome = Field(
        "unknown",
        description="이 판례에서 원고가 이겼는지 (AI 판정) — 카드의 결과 배지용. "
        "win=원고 승소, partial=원고 일부승소, lose=원고 패소, "
        "unknown=판단 불가(파기환송 등). unknown 은 배지를 표시하지 않는다",
        examples=["win"],
    )
    similarity: int | None = Field(
        None,
        description="판례 임베딩 코사인 유사도 % (벡터 검색으로 확보된 후보만, "
        "'내 사건과 유사한 판례 N%' 게이지용)",
    )
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


# --- 승소율 통계 (statistics) ---


class StatisticsRequest(_SearchBase):
    """승소율 통계 요청."""

    sample_size: int = Field(
        30, ge=10, le=50, description="분석할 판례 표본 수 (기본 30, 10~50)"
    )


class OutcomeCounts(BaseModel):
    """표본의 승패 분포."""

    win: int = Field(description="원고 승소")
    partial: int = Field(description="원고 일부 승소")
    lose: int = Field(description="원고 패소")
    unknown: int = Field(description="판단 불가 (파기환송·정보 부족 등)")


class StatisticsResponse(BaseModel):
    """승소율 통계 응답 — 검색 표본 기반 참고 지표."""

    sample_size: int = Field(description="분석한 판례 표본 수")
    classified: int = Field(description="승패 판단이 가능했던 건수")
    plaintiff_win_rate: int | None = Field(
        description="판단 가능 건 중 원고 승소·일부 승소 비율 %. "
        "판단 가능 건이 5건 미만이면 소표본 왜곡 방지를 위해 null"
    )
    outcomes: OutcomeCounts = Field(description="승패 분포")
    disclaimer: str = Field(description="면책 문구 — 프론트에서 반드시 함께 표시")


# --- LLM structured output 모델 ---


class CandidateScore(BaseModel):
    """예선 채점 결과 한 건."""

    id: int
    relevance: int


class RerankDraft(BaseModel):
    """LLM 예선 일괄 채점 출력 (structured output 강제용)."""

    scores: list[CandidateScore]


class NoteDraft(BaseModel):
    """LLM 참고 포인트 요약 출력 (structured output 강제용, 본선)."""

    reference_note: str


class KeywordsDraft(BaseModel):
    """LLM 검색 키워드 추출 출력 (structured output 강제용)."""

    keywords: str  # 판례 검색용 키워드 문자열 (예: "임대차 보증금 반환")


class OutcomeItem(BaseModel):
    """LLM 승패 분류 결과 한 건."""

    id: int
    outcome: Outcome


class OutcomeBatchDraft(BaseModel):
    """LLM 승패 일괄 분류 출력 (structured output 강제용)."""

    results: list[OutcomeItem]
