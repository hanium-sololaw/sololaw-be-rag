"""Agent 간 주고받는 LLM 구조화 출력 (structured output 강제용)."""

from typing import Literal

from pydantic import BaseModel


class SupervisorDecision(BaseModel):
    """Supervisor 의 라우팅 판단 — 판례 검색 Agent 를 부를지."""

    need_precedents: bool
    search_query: str  # need_precedents 가 false 면 빈 문자열


class RelevanceItem(BaseModel):
    id: int
    # relevant: 쟁점이 같다 / uncertain: 발췌만으로 판단 어려움 / irrelevant: 명확히 다른 쟁점
    verdict: Literal["relevant", "uncertain", "irrelevant"]
    reason: str


class RelevanceDraft(BaseModel):
    """생성 전 관련성 판정 — 판례가 원래 사건의 쟁점과 맞는지 (문서 본문은 보지 않는다)."""

    items: list[RelevanceItem]


class Explanation(BaseModel):
    citation: str  # 본문에 인용된 판례 또는 조문 (예: "대법원 2020다12345 판결")
    kind: Literal["precedent", "statute"]
    supports: str  # 그 근거가 뒷받침하는 문서 속 주장 한 문장
    # 판례만 판정. consistent: 발췌가 주장을 뒷받침 / contradicts: 발췌의 특정 구절과 명확히
    # 어긋남 / not_found: 발췌에서 근거를 찾을 수 없음 (모순과 다르다). 조문은 not_found.
    grounding: Literal["consistent", "contradicts", "not_found"]
    claim: str  # contradicts 일 때 문서 속 주장 원문, 아니면 빈 문자열
    passage: str  # contradicts 일 때 어긋나는 판례 구절, 아니면 빈 문자열
    issue: str  # contradicts 일 때 어긋나는 점 한 문장, 아니면 빈 문자열


class ExplanationDraft(BaseModel):
    items: list[Explanation]
