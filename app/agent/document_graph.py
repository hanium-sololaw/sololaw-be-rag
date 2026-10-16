"""문서 생성 Multi-Agent 그래프 (LangGraph StateGraph).

Supervisor ─(판례 필요)→ 판례 검색 Agent ─→ 판례 선별 ─→ 문서 생성 Agent → 검증 → 설명 Agent
          └─(불필요)────────────────────────↗              ↑           │        │
                                                          └─ 재작성 ──┴────────┘
- Supervisor: 사용자가 판례를 고르지 않았으면 판례 검색이 필요한지 LLM 이 판단한다.
- 판례 검색 Agent: 판례 검색 도메인의 하이브리드 검색·예선으로 인용 후보를 찾고,
  판시사항·판결요지 발췌를 검증용으로 보관한다.
- 판례 선별(생성 전): 원래 사건 입력만 보고 판례가 사건 쟁점과 맞는지 한 번에 판정해
  무관한 판례를 생성용 목록에서 뺀다. 판례가 없으면 건너뛴다.
- 문서 생성 Agent: 유형별 생성기(registry)로 스트리밍 생성한다.
- 검증: 입력에 없는 사건번호가 본문에 있으면 재작성시킨다.
- 설명 Agent(생성 후): 인용 근거별로 무엇을 뒷받침하는지 설명하고, 판례 발췌가 그 주장과
  명확히 어긋나면 주장·구절을 짚어 재작성시킨다. 판례를 목록에서 빼지는 않는다.
  조문은 law.go.kr 로 조회해 존재 확인 여부만 기록한다.
재작성은 두 검증이 같은 한도(2회)를 공유하고, 넘기면 문서를 내보내지 않고 error 로 끝낸다.
판례 판정은 모두 LLM 판정이며, 판결 전문이 아니라 조회한 판시사항·판결요지(최대 2,000자)
범위에서 이뤄진다.

SSE 계약은 기존과 같다 — delta*N → done(sections, raw_text) / error.
done 에 explanations 가 더해지고, 재작성 직전에 retry 이벤트가 나간다.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import TypedDict

import httpx
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.agent import verify
from app.agent.prompts import explain as explain_prompt
from app.agent.prompts import relevance as relevance_prompt
from app.agent.prompts import supervisor as supervisor_prompt
from app.agent.schemas import ExplanationDraft, RelevanceDraft, SupervisorDecision
from app.cases import client as law_client
from app.cases import service as case_service
from app.cases.schemas import SearchRequest
from app.core.config import settings
from app.documents.registry import GENERATORS
from app.documents.schemas.common import DocumentType
from app.documents.service import DOCUMENT_TYPES, parse_sections, sse
from app.shared.llm import get_openai_client

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3  # 첫 생성 + 재작성 2회
_PRECEDENTS = 3  # 문서에 넣을 판례 수
_MIN_RELEVANCE = 70  # 예선 기준표의 "핵심 쟁점이 같음" 이상만 인용
_SUMMARY_CHARS = 300  # 생성기에 넘기는 판례 요지 길이
_SOURCE_CHARS = 2000  # 검증용 판례 원문 길이 (판례당, 프롬프트 길이 제한)
_CONTEXT_CHARS = 4000
_MAX_STATUTES = 20
# 당사자 정보(주민등록번호·주소 등)는 Supervisor·검색에 넘기지 않는다.
_EXCLUDED_KEYS = {
    "plaintiffs",
    "defendants",
    "applicant",
    "respondent",
    "plaintiff",
    "defendant",
    "agent",
    "cited_precedents",
}
_LABELS = {t.type: t.name for t in DOCUMENT_TYPES}


class DocumentState(TypedDict, total=False):
    doc_type: DocumentType
    inputs: dict  # 원래 요청 — 바꾸지 않는다
    search_query: str
    # 생성에 쓸 판례 {case_no, summary, source(검증용 원문 | None), auto(자동 보강 여부)}
    precedents: list[dict]
    # 생성 전 판례 선별 기록 {case_no, auto, verdict, reason, used} — 실행 기록·평가용
    screening: list[dict]
    excluded: list[str]  # 선별에서 생성용 목록에서 뺀 판례 case_no
    attempts: int
    text: str
    issues: list[str]  # 직전 초안의 검증 지적. 남은 채로 끝나면 error
    explanations: list[dict]


def _generation_inputs(state: DocumentState) -> dict:
    """생성기에 넘길 입력 — 원래 요청에 현재 생성용 판례 목록을 끼운다."""
    excluded = set(state.get("excluded", []))
    cited = [
        {"case_no": p["case_no"], "summary": p["summary"]}
        for p in state.get("precedents", [])
        if p["case_no"] not in excluded
    ]
    return {**state["inputs"], "cited_precedents": cited}


def _case_context(inputs: dict) -> str:
    facts = {k: v for k, v in inputs.items() if k not in _EXCLUDED_KEYS and v}
    return json.dumps(facts, ensure_ascii=False, default=str)[:_CONTEXT_CHARS]


async def supervisor(state: DocumentState) -> DocumentState:
    # 사용자가 고른 판례는 덮어쓰지 않고, 증거목록은 판례를 쓰는 섹션이 없다.
    user_cited = [
        {
            "case_no": p["case_no"],
            "summary": p.get("summary"),
            "source": None,
            "auto": False,
        }
        for p in state["inputs"].get("cited_precedents") or []
    ]
    skip = {"search_query": "", "precedents": user_cited}
    if state["doc_type"] == DocumentType.EVIDENCE_LIST or user_cited:
        return skip
    try:
        completion = await get_openai_client().chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": supervisor_prompt.SYSTEM},
                {
                    "role": "user",
                    "content": supervisor_prompt.build_user_prompt(
                        _LABELS[state["doc_type"]], _case_context(state["inputs"])
                    ),
                },
            ],
            response_format=SupervisorDecision,
        )
        decision = completion.choices[0].message.parsed
    except Exception:
        logger.exception("Supervisor 판단 실패 — 판례 검색 없이 진행")
        return skip
    if decision and decision.need_precedents and decision.search_query.strip():
        return {**skip, "search_query": decision.search_query.strip()}
    return skip


def _route_supervisor(state: DocumentState) -> str:
    return "search_agent" if state["search_query"] else "screen_agent"


async def search_agent(state: DocumentState) -> DocumentState:
    # 판례 보강은 부가 기능이라 실패해도 문서 생성은 계속한다.
    try:
        r = await case_service.retrieve(
            SearchRequest(
                query=state["search_query"],
                case_context=_case_context(state["inputs"]),
                limit=_PRECEDENTS,
            )
        )
    except Exception:
        logger.exception("판례 검색 Agent 실패 — 판례 없이 생성")
        return {}
    found = []
    for i, score in r.finalists:
        if score < _MIN_RELEVANCE:
            continue
        item, detail = r.items[i], r.details[i]
        case_no = f"{item.get('법원명', '')} {item.get('사건번호', '')}".strip()
        holding = detail.get("판결요지") or ""
        issues = detail.get("판시사항") or ""
        # 판시사항·판결요지가 없는 판례(하급심에 흔함)는 근거를 검증할 수 없어 인용하지 않는다.
        if not (holding or issues):
            continue
        found.append(
            {
                "case_no": case_no,
                "summary": (holding or issues)[:_SUMMARY_CHARS] or None,
                "source": (
                    f"[판시사항] {issues or '없음'}\n[판결요지] {holding or '없음'}"
                )[:_SOURCE_CHARS],
                "auto": True,
            }
        )
    return {"precedents": found}


async def screen_agent(state: DocumentState) -> DocumentState:
    precedents = state.get("precedents", [])
    if not precedents:
        return {}
    candidates = [
        (i, p["case_no"], p["source"] or p["summary"] or "")
        for i, p in enumerate(precedents)
    ]
    draft = None
    try:
        completion = await get_openai_client().chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": relevance_prompt.SYSTEM},
                {
                    "role": "user",
                    "content": relevance_prompt.build_user_prompt(
                        _case_context(state["inputs"]), candidates
                    ),
                },
            ],
            response_format=RelevanceDraft,
        )
        draft = completion.choices[0].message.parsed
    except Exception:
        # 예선(관련도 70점 이상)은 이미 통과했으므로 선별 없이 진행하고 기록을 남긴다.
        logger.exception("판례 선별 실패 — 선별 없이 진행")
    verdicts = {it.id: it for it in draft.items} if draft else {}
    screening, excluded = [], []
    for i, p in enumerate(precedents):
        v = verdicts.get(i)
        verdict = v.verdict if v else "unscreened"
        # 명확히 무관하면 뺀다. 불확실하면 자동 보강 판례만 뺀다 — 사용자 판례는 사용자 선택을 존중.
        drop = verdict == "irrelevant" or (verdict == "uncertain" and p["auto"])
        if drop:
            excluded.append(p["case_no"])
        screening.append(
            {
                "case_no": p["case_no"],
                "auto": p["auto"],
                "verdict": verdict,
                "reason": v.reason if v else "",
                "used": not drop,
            }
        )
    if excluded:
        logger.info("생성 전 판례 제외: %s", [s for s in screening if not s["used"]])
    return {"screening": screening, "excluded": excluded}


async def generate_agent(state: DocumentState) -> DocumentState:
    write = get_stream_writer()
    attempts = state.get("attempts", 0)
    feedback = None
    if attempts:
        issues = state["issues"]
        write(("retry", {"attempt": attempts + 1, "reason": "; ".join(issues)}))
        feedback = (
            "직전 초안의 인용 근거에 다음 문제가 있었습니다.\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\n[인용할 판례]에 없는 사건번호는 쓰지 마세요. 지적된 인용은 판례 요지에 맞게 "
            "고치거나 그 주장에서 판례를 빼세요. 판례에 맞춰 사실관계·청구 구성을 바꾸지 "
            "마세요. 문서 전체를 처음부터 다시 작성하세요."
        )
    buffer: list[str] = []
    generator = GENERATORS[state["doc_type"]]
    async for delta in generator.generate_stream(_generation_inputs(state), feedback):
        buffer.append(delta)
        write(("delta", {"text": delta}))
    return {"text": "".join(buffer), "attempts": attempts + 1}


def verify_node(state: DocumentState) -> DocumentState:
    # 허용 = 원래 요청(사용자 판례 포함) + 현재 생성용 판례. 빼낸 자동 보강 판례는 다시 쓰면 걸린다.
    allowed = {"request": state["inputs"], "generation": _generation_inputs(state)}
    unknown = verify.unknown_case_numbers(state["text"], allowed)
    return {
        "issues": [f"{no}: 입력과 인용 판례 목록에 없는 사건번호" for no in unknown]
    }


def _route_after_check(next_node: str):
    def route(state: DocumentState) -> str:
        if not state["issues"]:
            return next_node
        return "generate_agent" if state["attempts"] < _MAX_ATTEMPTS else END

    return route


async def _lookup_statutes(text: str) -> dict[str, bool]:
    """본문의 조문을 law.go.kr 로 조회한다 — {조문 키: 조회 성공}.
    조회 실패와 없는 조문은 구별되지 않아 미확인으로 기록만 하고 재작성 조건으로 쓰지 않는다."""
    ranked = case_service.aggregate_statutes([text], top=_MAX_STATUTES)
    async with httpx.AsyncClient() as http:
        titles = await asyncio.gather(
            *(
                law_client.fetch_statute_title(http, law, jo, ui)
                for (law, jo, ui), _ in ranked
            ),
            return_exceptions=True,
        )
    return {
        f"{law}제{jo}조{ui}".replace(" ", ""): isinstance(t, str)
        for ((law, jo, ui), _), t in zip(ranked, titles)
    }


async def _explain(text: str, precedents: list[tuple[str, str]]):
    completion = await get_openai_client().chat.completions.parse(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": explain_prompt.SYSTEM},
            {
                "role": "user",
                "content": explain_prompt.build_user_prompt(text, precedents),
            },
        ],
        response_format=ExplanationDraft,
    )
    return completion.choices[0].message.parsed


def _match(citation: str, precedents: list[dict]) -> dict | None:
    nos = verify.case_numbers(citation)
    return next(
        (p for p in precedents if verify.case_numbers(p["case_no"]) & nos), None
    )


async def explain_agent(state: DocumentState) -> DocumentState:
    if state["doc_type"] == DocumentType.EVIDENCE_LIST:  # 표만 있어 인용 근거가 없다
        return {"explanations": [], "issues": []}
    text = state["text"]
    excluded = list(state.get("excluded", []))
    active = [p for p in state.get("precedents", []) if p["case_no"] not in excluded]
    # 사용자가 고른 판례는 원문을 조회하지 않아 요지로만 판정한다.
    # shortcut: 사용자 판례 원문은 조회하지 않는다, 사건번호로 law.go.kr 본문을 받아오면 보강.
    draft, statutes = await asyncio.gather(
        _explain(
            text, [(p["case_no"], p["source"] or p["summary"] or "") for p in active]
        ),
        _lookup_statutes(text),
        return_exceptions=True,
    )
    if isinstance(statutes, BaseException):
        logger.warning("조문 조회 실패 — 모두 미확인 처리", exc_info=statutes)
        statutes = {}
    if isinstance(draft, BaseException) or draft is None:
        # 사건번호 검증은 통과한 상태라 문서는 내보내고, 근거 판정이 없었음을 남긴다.
        logger.error("설명 Agent 실패 — 근거 판정 없이 응답", exc_info=draft or None)
        return {"explanations": [], "issues": []}

    explanations, issues = [], []
    cited_nos = verify.case_numbers(text)
    flat = text.replace(" ", "")
    for e in draft.items:
        # LLM 이 제공 목록만 보고 본문에 없는 인용을 지어낼 수 있어, 본문에 실제로 있는 것만 남긴다.
        if e.kind == "precedent":
            if not verify.case_numbers(e.citation) & cited_nos:
                continue
        elif e.citation.replace(" ", "") not in flat:
            continue
        # exists: 판례는 판례 DB 에서 조회해 온 것인지, 조문은 law.go.kr 조회에 성공했는지.
        # grounded: 판례 발췌가 주장을 뒷받침하는지에 대한 LLM 판정. 발췌에서 근거를
        #   찾지 못했거나(not_found) 발췌가 없으면 None — 미확인을 확인됨으로 내보내지 않는다.
        if e.kind == "precedent":
            p = _match(e.citation, active)
            has_source = bool(p and (p["source"] or p["summary"]))
            if has_source and e.grounding == "contradicts":
                # 관련 있는 판례를 잘못 쓴 것이라 목록에서 빼지 않고 고쳐 쓰게 한다.
                issues.append(
                    f"{e.citation}: 문서의 주장 「{e.claim}」이 판례 구절 「{e.passage}」과 "
                    f"어긋남 — {e.issue}"
                )
            exists = True if p and p["auto"] else None
            grounded = (
                {"consistent": True, "contradicts": False}.get(e.grounding)
                if has_source
                else None
            )
        else:
            cited = e.citation.replace(" ", "")
            exists = (
                True if any(ok and k in cited for k, ok in statutes.items()) else None
            )
            grounded = None
        explanations.append(
            {
                "citation": e.citation,
                "kind": e.kind,
                "supports": e.supports,
                "exists": exists,
                "grounded": grounded,
            }
        )
    return {"explanations": explanations, "issues": issues}


_builder = StateGraph(DocumentState)
_builder.add_node("supervisor", supervisor)
_builder.add_node("search_agent", search_agent)
_builder.add_node("screen_agent", screen_agent)
_builder.add_node("generate_agent", generate_agent)
_builder.add_node("verify", verify_node)
_builder.add_node("explain_agent", explain_agent)
_builder.add_edge(START, "supervisor")
_builder.add_conditional_edges(
    "supervisor", _route_supervisor, ["search_agent", "screen_agent"]
)
_builder.add_edge("search_agent", "screen_agent")
_builder.add_edge("screen_agent", "generate_agent")
_builder.add_edge("generate_agent", "verify")
_builder.add_conditional_edges(
    "verify",
    _route_after_check("explain_agent"),
    ["explain_agent", "generate_agent", END],
)
_builder.add_conditional_edges(
    "explain_agent", _route_after_check(END), ["generate_agent", END]
)
graph = _builder.compile()


async def stream_document(doc_type: DocumentType, inputs: dict) -> AsyncIterator[str]:
    """그래프를 돌리며 Agent 이벤트를 SSE 로 흘리고, 끝나면 done / error 를 낸다."""
    final: DocumentState = {}
    try:
        async for mode, chunk in graph.astream(
            {"doc_type": doc_type, "inputs": inputs},
            stream_mode=["custom", "values"],
        ):
            if mode == "custom":
                event, data = chunk
                yield sse(event, data)
            else:
                final = chunk
        if final.get("issues"):
            logger.warning("재작성 한도 초과 — 남은 검증 지적 %s", final["issues"])
            yield sse(
                "error",
                {
                    "message": "인용 근거를 확인하지 못해 문서 생성을 중단했습니다. "
                    "다시 시도해 주세요."
                },
            )
            return
        text = final["text"]
        sections = parse_sections(text, GENERATORS[doc_type].section_map)
        yield sse(
            "done",
            {
                "sections": sections,
                "raw_text": text,
                "explanations": final.get("explanations", []),
            },
        )
    except NotImplementedError as e:
        yield sse("error", {"message": str(e)})
    except Exception:
        logger.exception("문서 생성 실패 (type=%s)", doc_type.value)
        yield sse("error", {"message": "문서 생성 중 오류가 발생했습니다."})
