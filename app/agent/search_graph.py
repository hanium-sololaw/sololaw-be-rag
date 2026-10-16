"""판례 검색 Multi-Agent 그래프 (LangGraph StateGraph).

Supervisor(요청 분석·검색어 확정) → 판례 검색 Agent(하이브리드 후보 + 예선)
→ 설명 Agent(승패 분류·참고 포인트·관련 법령 + 승소율 통계).
각 Agent 는 app/cases/service 의 검증된 함수를 그대로 쓴다.
"""

import asyncio
import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.cases import service
from app.cases.schemas import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)


class SearchState(TypedDict, total=False):
    req: SearchRequest
    # 띄운 통계 작업. 그래프 밖(search_cases)이 같은 리스트를 들고 있다가 실패·취소 시
    # 정리한다 — 노드가 예외로 끝나면 상태가 반환되지 않기 때문. 체크포인터가 없어 직렬화 불필요.
    tasks: list[asyncio.Task]
    retrieval: service.Retrieval
    response: SearchResponse


async def supervisor(state: SearchState) -> SearchState:
    req = state["req"]
    # 내 사건 기반 탭은 case_context 에서 검색어를 추출한다. 카드와 통계가 같은 기준을 쓴다.
    resolved = await service.resolve_query(req.query, req.case_context)
    req = req.model_copy(update={"query": resolved})
    # 통계는 검색과 독립이라 먼저 띄워두고 설명 Agent 가 거둔다 (벽시계 시간 절약).
    state["tasks"].append(
        asyncio.create_task(
            service.compute_statistics(resolved, req.category, req.sample_size)
        )
    )
    return {"req": req}


async def search_agent(state: SearchState) -> SearchState:
    return {"retrieval": await service.retrieve(state["req"])}


async def explain_agent(state: SearchState) -> SearchState:
    response = await service.explain(state["req"], state["retrieval"])
    # 통계가 실패해도 카드·법령은 그대로 내려준다.
    try:
        response.statistics = await state["tasks"][0]
    except Exception:
        logger.exception("승소율 통계 산출 실패 — statistics 는 null 로 응답")
    return {"response": response}


_builder = StateGraph(SearchState)
_builder.add_node("supervisor", supervisor)
_builder.add_node("search_agent", search_agent)
_builder.add_node("explain_agent", explain_agent)
_builder.add_edge(START, "supervisor")
_builder.add_edge("supervisor", "search_agent")
_builder.add_edge("search_agent", "explain_agent")
_builder.add_edge("explain_agent", END)
graph = _builder.compile()


async def search_cases(req: SearchRequest) -> SearchResponse:
    tasks: list[asyncio.Task] = []
    try:
        state = await graph.ainvoke({"req": req, "tasks": tasks})
        return state["response"]
    finally:
        # 검색·설명 단계 실패나 요청 취소로 끝나도 통계 LLM 호출이 남아 돌지 않게 한다.
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
