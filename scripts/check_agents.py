"""Multi-Agent 그래프 회귀 점검 — LLM·law.go.kr·벡터 DB 를 가짜로 바꿔 분기를 확인한다.

외부 호출이 없어 키 없이 돌고 비용이 들지 않는다. 그래프·검증 로직을 바꾸면 돌린다.
실행: PYTHONPATH=. .venv/bin/python -m scripts.check_agents
"""

import asyncio
import logging
import re
from types import SimpleNamespace

from app.agent import document_graph as dg
from app.agent import search_graph as sg
from app.agent import verify
from app.agent.schemas import (
    Explanation,
    ExplanationDraft,
    RelevanceDraft,
    RelevanceItem,
    SupervisorDecision,
)
from app.cases import client, embedding, service
from app.cases.schemas import CaseCard, SearchRequest
from app.documents.registry import GENERATORS
from app.documents.schemas.common import DocumentType

calls: dict[str, list] = {}


def _log(name, *args):
    calls.setdefault(name, []).append(args)


def _kw_item(sid):
    return {
        "판례일련번호": sid,
        "사건명": "대여금",
        "사건번호": f"2020다{sid}",
        "법원명": "대법원",
        "선고일자": "20200101",
        "사건종류명": "민사",
    }


def _vec_row(sid):
    return {
        "serial_id": sid,
        "name": "대여금",
        "case_no": f"2021다{sid}",
        "court": "대법원",
        "decision_date": "20210101",
        "category": "민사",
        "similarity": 0.8,
        "summary": "판시",
        "holding": "요지",
        "statutes": "민법 제598조",
    }


def _install(law_fails=False, vector_rows=(), keyword_ids=()):
    """판례 검색 도메인의 외부 호출을 가짜로 바꾼다. vector_rows=None 이면 벡터 DB 장애."""
    calls.clear()

    async def search_precedents(http, q, display):
        _log("search_precedents", q)
        if law_fails:
            raise client.LawApiError("down")
        return len(keyword_ids), [_kw_item(s) for s in keyword_ids]

    async def fetch_detail(http, sid):
        _log("fetch_detail", sid)
        return {
            "판시사항": "p",
            "판결요지": "h",
            "참조조문": "민법 제598조",
            "주문": "원고 승",
        }

    async def statute_title(http, law, jo, ui=""):
        _log("statute_title", law, jo)
        return "소비대차의 의의"

    async def embed(texts):
        return [[0.0] * 3]

    async def similar(vec, top_k, category):
        if vector_rows is None:
            raise embedding.VectorDbError("no db")
        return [_vec_row(s) for s in vector_rows]

    async def rerank(req, items, details):
        return [(i, 90) for i in range(len(items))]

    async def classify(cands):
        return {c[0]: "win" for c in cands}

    async def card(req, item, detail, relevance, outcome):
        return CaseCard(
            serial_id=str(item["판례일련번호"]),
            name="n",
            case_no="c",
            court="c",
            decision_date="d",
            category="민사",
            relevance=relevance,
            outcome=outcome,
            similarity=item.get("_similarity"),
            reference_note="note",
            detail_url="u",
        )

    client.search_precedents = search_precedents
    client.fetch_precedent_detail = fetch_detail
    client.fetch_statute_title = statute_title
    embedding.embed_texts = embed
    embedding.search_similar = similar
    service._rerank = rerank
    service.classify_outcomes = classify
    service._make_card = card


def check_case_numbers():
    c = verify.case_numbers
    assert c("대법원 2019다12345 판결, 2024가단123456 사건") == {
        "2019다12345",
        "2024가단123456",
    }
    assert c("101동1203호, 10억2000만원, 2024년1월, 제3조의2, 갑 제1호증") == set()
    assert c("89다카1234, 2026카합10, 2024차전55") == {
        "89다카1234",
        "2026카합10",
        "2024차전55",
    }
    inputs = {
        "case_no": "2024가단123456",
        "rebuttal_points": [{"precedent_ref": "2015다222222"}],
        "cited_precedents": [{"case_no": "대법원 2020다12345"}],
    }
    # 현재 사건번호·쟁점별 판례는 오탐이 아니다
    assert not verify.unknown_case_numbers(
        "사건 2024가단123456 (대법원 2020다12345 판결 참조) 2015다222222", inputs
    )
    assert verify.unknown_case_numbers("대법원 2021다99999 판결", inputs) == [
        "2021다99999"
    ]


async def check_search():
    req = SearchRequest(query="대여금", limit=5)

    # 벡터 후보는 코퍼스 본문을 재사용하고, 키워드 전용 후보만 본문을 조회한다
    _install(vector_rows=["1", "2"], keyword_ids=["2", "3"])
    r = await service.retrieve(req)
    assert sorted(a[0] for a in calls["fetch_detail"]) == ["3"], calls["fetch_detail"]
    assert {it["판례일련번호"] for it in r.items} == {"1", "2", "3"}

    # 주문이 없는 본선 진출작(벡터 후보 1·2)만 law.go.kr 에서 재조회한다
    calls["fetch_detail"].clear()
    resp = await service.explain(req, r)
    assert sorted(a[0] for a in calls["fetch_detail"]) == ["1", "2"]
    assert resp.statutes and resp.statutes[0].title == "소비대차의 의의"

    # law.go.kr 장애 + 벡터 후보 → 벡터만으로 진행하고 이후 law.go.kr 를 부르지 않는다
    _install(law_fails=True, vector_rows=["1"])
    r = await service.retrieve(req)
    assert r.law_error and [it["판례일련번호"] for it in r.items] == ["1"]
    resp = await service.explain(req, r)
    assert "fetch_detail" not in calls and "statute_title" not in calls, calls
    assert resp.statutes[0].title is None and resp.cases[0].similarity == 80

    # law.go.kr 장애 + 벡터 없음 → 빈 결과로 위장하지 않고 장애를 올린다
    _install(law_fails=True, vector_rows=None)
    try:
        await service.retrieve(req)
        raise AssertionError("LawApiError 가 나야 한다")
    except client.LawApiError:
        pass


async def check_stats_cleanup():
    started: list[asyncio.Task] = []

    async def slow_stats(*a):
        started.append(asyncio.current_task())
        await asyncio.sleep(30)

    async def keep_query(q, c):
        return q

    orig = (service.compute_statistics, service.resolve_query, service.explain)
    service.compute_statistics, service.resolve_query = slow_stats, keep_query
    req = SearchRequest(query="대여금")
    _install(vector_rows=["1"])

    # 설명 단계가 실패해도 통계 작업이 남아 돌지 않는다
    async def broken_explain(req, r):
        raise RuntimeError("explain down")

    service.explain = broken_explain
    try:
        await sg.search_cases(req)
        raise AssertionError("RuntimeError 가 나야 한다")
    except RuntimeError:
        pass
    service.explain = orig[2]
    assert started and started[-1].cancelled(), "설명 실패 시 통계 작업이 남았다"

    # 검색 중 요청이 취소돼도 마찬가지
    async def hang(req):
        await asyncio.sleep(30)

    orig_retrieve, service.retrieve = service.retrieve, hang
    outer = asyncio.create_task(sg.search_cases(req))
    await asyncio.sleep(0.1)
    outer.cancel()
    await asyncio.gather(outer, return_exceptions=True)
    service.retrieve = orig_retrieve
    assert len(started) == 2 and started[-1].cancelled(), "취소 시 통계 작업이 남았다"
    service.compute_statistics, service.resolve_query = orig[0], orig[1]


class _Doc:
    """문서 생성 그래프용 가짜 — 생성기·Supervisor·판례 선별·설명 LLM 을 대본대로 돌린다.

    screen 은 {사건번호: 판정}(없으면 relevant), screen=None 이면 선별 LLM 장애.
    """

    def __init__(
        self, drafts, verdicts, need_precedents=False, retrieved=(), screen=()
    ):
        self.drafts, self.verdicts = list(drafts), list(verdicts)
        self.generation_cited: list[list[str]] = []
        self.feedbacks: list = []
        self.screen_calls = 0
        screen = None if screen is None else dict(screen)

        async def stream(inputs, feedback=None):
            self.generation_cited.append(
                [p["case_no"] for p in inputs["cited_precedents"]]
            )
            self.feedbacks.append(feedback)
            yield self.drafts.pop(0)

        async def explain(text, precedents):
            return ExplanationDraft(items=self.verdicts.pop(0))

        async def parse(model, messages, response_format):
            if response_format is RelevanceDraft:
                self.screen_calls += 1
                assert (
                    "홍길동" not in messages[1]["content"]
                )  # 당사자 정보는 넘기지 않는다
                if screen is None:
                    raise RuntimeError("screen down")
                ids = re.findall(r"\[후보 (\d+)\] (.+)", messages[1]["content"])
                parsed = RelevanceDraft(
                    items=[
                        RelevanceItem(
                            id=int(i),
                            verdict=next(
                                (v for k, v in screen.items() if k in no), "relevant"
                            ),
                            reason=f"{no} 사유",
                        )
                        for i, no in ids
                    ]
                )
            else:
                parsed = SupervisorDecision(
                    need_precedents=need_precedents, search_query="대여금 반환"
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))]
            )

        async def retrieve(req):
            return service.Retrieval(
                total=len(retrieved),
                items=[
                    {"법원명": court, "사건번호": no, "판례일련번호": no}
                    for court, no in retrieved
                ],
                details=[{"판시사항": "판시", "판결요지": "요지"} for _ in retrieved],
                finalists=[(i, 90) for i in range(len(retrieved))],
                law_error=None,
            )

        GENERATORS[DocumentType.COMPLAINT].generate_stream = stream
        dg._explain = explain
        dg.get_openai_client = lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))
        )
        service.retrieve = retrieve

    async def run(self, inputs):
        out = [e async for e in dg.stream_document(DocumentType.COMPLAINT, inputs)]
        return [e.split("\n")[0].removeprefix("event: ") for e in out], out[-1]

    async def state(self, inputs):
        return await dg.graph.ainvoke(
            {"doc_type": DocumentType.COMPLAINT, "inputs": inputs}
        )


def _prec(citation, grounding="consistent", claim="", passage="", issue=""):
    return Explanation(
        citation=citation,
        kind="precedent",
        supports="s",
        grounding=grounding,
        claim=claim,
        passage=passage,
        issue=issue,
    )


def _contradicts(citation):
    return _prec(
        citation,
        "contradicts",
        claim="대여금 미반환은 불법행위다",
        passage="채무불이행 책임",
        issue="책임 근거가 다름",
    )


_STATUTE = Explanation(
    citation="민법 제598조",
    kind="statute",
    supports="소비대차 성립",
    grounding="not_found",
    claim="",
    passage="",
    issue="",
)
_FACTS = {"plaintiffs": [{"name": "홍길동"}], "facts": {"빌려준 돈": "1천만원"}}
_USER = {
    **_FACTS,
    "cited_precedents": [{"case_no": "대법원 2020다12345", "summary": "요지"}],
}
# 실제 호출에서 나온 사례: 대여금 소장에 중복제소 판례(A)가 변제 판례(B)와 함께 검색됐다
_A, _B = ("서울고등법원", "2023나2056133"), ("대법원", "2024다258921")


async def check_documents():
    _install()
    orig_retrieve = service.retrieve

    # 사용자 판례 + 근거 부합 → done. 조문은 존재 확인, 사용자 판례는 존재 미확인(null)
    d = _Doc(
        ["(대법원 2020다12345 판결 참조) 민법 제598조"],
        [[_prec("대법원 2020다12345 판결"), _STATUTE]],
    )
    ev, last = await d.run(_USER)
    assert ev == ["delta", "done"], ev
    assert (
        '"kind": "precedent", "supports": "s", "exists": null, "grounded": true' in last
    )
    assert (
        '"kind": "statute", "supports": "소비대차 성립", "exists": true, "grounded": null'
        in last
    )

    # 본문에 없는 판례·조문을 설명 LLM 이 지어내면 explanations 에서 뺀다
    d = _Doc(
        ["판례 없이 작성한 본문"],
        [[_prec("대법원 2020다12345 판결"), _STATUTE]],
    )
    ev, last = await d.run(_USER)
    assert ev == ["delta", "done"] and '"explanations": []' in last, last

    # 발췌와 명확히 어긋남 1회 → 주장·구절을 짚어 재작성. 관련 판례는 목록에 남긴다
    d = _Doc(
        ["(대법원 2020다12345 판결 참조)"] * 2,
        [[_contradicts("대법원 2020다12345 판결")], [_prec("대법원 2020다12345 판결")]],
    )
    ev, _ = await d.run(_USER)
    assert ev == ["delta", "retry", "delta", "done"], ev
    assert d.feedbacks[0] is None
    assert (
        "대여금 미반환은 불법행위다" in d.feedbacks[1]
        and "채무불이행 책임" in d.feedbacks[1]
    )
    assert d.generation_cited == [["대법원 2020다12345"]] * 2, d.generation_cited

    # 계속 어긋남 → 3회 시도 후 error
    bad = [_contradicts("대법원 2020다12345 판결")]
    d = _Doc(["(대법원 2020다12345 판결 참조)"] * 3, [bad] * 3)
    ev, _ = await d.run(_USER)
    assert ev == ["delta", "retry", "delta", "retry", "delta", "error"], ev

    # 발췌에서 근거를 못 찾음(not_found) → 모순이 아니므로 재작성하지 않고 grounded null
    d = _Doc(
        ["(대법원 2020다12345 판결 참조)"],
        [[_prec("대법원 2020다12345 판결", "not_found")]],
    )
    ev, last = await d.run(_USER)
    assert ev == ["delta", "done"] and '"grounded": null' in last, last

    # 조문 조회 실패는 기록만(exists null) — 재작성하지 않는다
    async def no_title(http, law, jo, ui=""):
        return None

    client.fetch_statute_title = no_title
    d = _Doc(["민법 제598조"], [[_STATUTE]])
    ev, last = await d.run(_FACTS)
    assert ev == ["delta", "done"] and '"exists": null, "grounded": null' in last, last
    assert d.screen_calls == 0  # 판례가 없으면 선별 호출을 생략한다
    _install()

    # 회귀: 쟁점이 다른 자동 보강 판례(A)는 생성 전에 빠져 생성기에 가지 않는다
    d = _Doc(
        ["(대법원 2024다258921 판결 참조)"],
        [[_prec("대법원 2024다258921 판결")]],
        need_precedents=True,
        retrieved=[_A, _B],
        screen={"2023나2056133": "irrelevant"},
    )
    ev, last = await d.run(_FACTS)
    assert ev == ["delta", "done"], ev
    assert d.generation_cited == [["대법원 2024다258921"]], d.generation_cited
    assert d.screen_calls == 1  # 후보들을 한 번에 판정한다
    assert '"exists": true, "grounded": true' in last
    d = _Doc(
        ["(대법원 2024다258921 판결 참조)"],
        [[_prec("대법원 2024다258921 판결")]],
        need_precedents=True,
        retrieved=[_A, _B],
        screen={"2023나2056133": "irrelevant"},
    )
    st = await d.state(_FACTS)
    a = next(x for x in st["screening"] if "2023나2056133" in x["case_no"])
    assert a == {
        "case_no": "서울고등법원 2023나2056133",
        "auto": True,
        "verdict": "irrelevant",
        "reason": "서울고등법원 2023나2056133 사유",
        "used": False,
    }, a

    # 불확실: 자동 보강 판례는 빼고, 사용자 판례는 사용자 선택을 존중해 남긴다
    d = _Doc(
        ["판례 없이 작성"],
        [[]],
        need_precedents=True,
        retrieved=[_A],
        screen={"2023나2056133": "uncertain"},
    )
    await d.run(_FACTS)
    assert d.generation_cited == [[]], d.generation_cited
    d = _Doc(
        ["(대법원 2020다12345 판결 참조)"],
        [[_prec("대법원 2020다12345 판결")]],
        screen={"2020다12345": "uncertain"},
    )
    await d.run(_USER)
    assert d.generation_cited == [["대법원 2020다12345"]], d.generation_cited

    # 사용자 판례가 명확히 무관하면 생성용 목록에서만 빼고 원본 입력은 보존한다
    d = _Doc(["판례 없이 작성"], [[]], screen={"2020다12345": "irrelevant"})
    ev, _ = await d.run(_USER)
    assert ev == ["delta", "done"] and d.generation_cited == [[]]
    assert _USER["cited_precedents"][0]["case_no"] == "대법원 2020다12345"

    # 선별 LLM 장애 → 예선은 통과했으므로 선별 없이 진행하고 unscreened 로 기록
    d = _Doc(
        ["(대법원 2024다258921 판결 참조)"],
        [[_prec("대법원 2024다258921 판결")]],
        need_precedents=True,
        retrieved=[_B],
        screen=None,
    )
    st = await d.state(_FACTS)
    assert st["screening"][0]["verdict"] == "unscreened" and st["screening"][0]["used"]

    # 판시사항·판결요지가 없는 판례는 관련도가 높아도 인용 후보에서 뺀다
    async def retrieve_no_text(req):
        return service.Retrieval(
            total=1,
            items=[{"법원명": "인천지방법원", "사건번호": "2024나74413"}],
            details=[{"판시사항": "", "판결요지": ""}],
            finalists=[(0, 90)],
            law_error=None,
        )

    d = _Doc(["판례 없이 작성"], [[]], need_precedents=True)
    service.retrieve = retrieve_no_text
    ev, _ = await d.run(_FACTS)
    assert ev == ["delta", "done"] and d.generation_cited == [[]], d.generation_cited
    assert d.screen_calls == 0

    # 생성 전에 빼낸 자동 보강 판례를 생성기가 그래도 쓰면 사건번호 검증에 걸린다
    d = _Doc(
        ["(서울고등법원 2023나2056133 판결 참조)", "판례 없이 작성"],
        [[]],
        need_precedents=True,
        retrieved=[_A],
        screen={"2023나2056133": "irrelevant"},
    )
    ev, _ = await d.run(_FACTS)
    assert ev == ["delta", "retry", "delta", "done"], ev
    assert "2023나2056133: 입력과 인용 판례 목록에 없는 사건번호" in d.feedbacks[1]

    service.retrieve = orig_retrieve


async def main():
    logging.disable(logging.CRITICAL)  # 의도한 장애 시나리오의 경고 로그를 숨긴다
    check_case_numbers()
    await check_search()
    await check_stats_cleanup()
    await check_documents()
    print("check_agents: all ok")


if __name__ == "__main__":
    asyncio.run(main())
