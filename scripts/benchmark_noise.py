"""실험 A-잡음 — 실제 검색 후보를 그대로 두 방식에 주고 인용 품질을 비교한다.

후보는 scripts/benchmark/noise_candidates.json 에 실행 전 고정했다(검색어·후보·관련성 라벨).
- keyword_filtered  : 키워드 검색 후 필터 적용 후보 — 예선 상위 3건 중 70점 이상·본문 있음(운영 필터와 같음)
- keyword_unfiltered: 키워드 검색 필터 전 후보(잡음 조건) — 예선 상위 5건 중 본문 있음(70점 필터 생략)
후보는 로컬(벡터 DB 없음) 키워드 검색 결과다. 운영은 하이브리드 검색이라 후보가 다를 수 있다.
두 방식의 시작 자료를 같게 하려고 Multi-Agent 는 고정 후보를 생성 전 선별 단계에 직접 넣는다
(운영 그래프와 같은 선별·생성·검증·설명 노드, Supervisor·검색 단계만 생략 — 그 호출 비용은 빠진다).
단일 호출은 같은 후보를 cited_precedents 로 받는다. 인용의 근거 불일치는 평가용 LLM 판정 하나로 두 방식을 같은
기준으로 본다(평가 호출은 시스템 비용에 넣지 않는다).

실행: PYTHONPATH=. .venv/bin/python -m scripts.benchmark_noise --reps 3 --out <결과 폴더>
"""

import argparse
import asyncio
import json
import logging
import random
import statistics
from datetime import datetime
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.agent import document_graph as dg
from app.agent import verify
from app.core.config import settings
from app.shared.llm import get_openai_client
from scripts import benchmark_agents as base

HERE = Path(__file__).parent / "benchmark"
# (후보 수, 최소 예선 점수)
CONDITIONS = {"keyword_filtered": (3, 70), "keyword_unfiltered": (5, 0)}


def _screen_graph():
    """운영 문서 그래프에서 Supervisor·검색만 뺀 것 — 생성 전 선별부터 시작한다."""
    g = StateGraph(dg.DocumentState)
    g.add_node("screen_agent", dg.screen_agent)
    g.add_node("generate_agent", dg.generate_agent)
    g.add_node("verify", dg.verify_node)
    g.add_node("explain_agent", dg.explain_agent)
    g.add_edge(START, "screen_agent")
    g.add_edge("screen_agent", "generate_agent")
    g.add_edge("generate_agent", "verify")
    g.add_conditional_edges(
        "verify",
        dg._route_after_check("explain_agent"),
        ["explain_agent", "generate_agent", END],
    )
    g.add_conditional_edges(
        "explain_agent", dg._route_after_check(END), ["generate_agent", END]
    )
    return g.compile()


SCREEN_GRAPH = _screen_graph()

JUDGE = """당신은 법률 문서의 판례 인용을 평가하는 검토자입니다.
[판례 발췌]는 판시사항·판결요지 일부이며 판결 전문이 아닙니다.
[인용 문장]이 그 판례를 근거로 드는 주장을 발췌에 비추어 하나로 판정하세요.
- consistent: 발췌가 그 주장을 뒷받침한다
- contradicts: 발췌의 특정 구절과 주장이 명확히 어긋난다
- not_found: 발췌에서 근거를 찾을 수 없다 (발췌가 짧아 보이지 않는 경우 포함)"""


class Verdict(BaseModel):
    verdict: str  # consistent | contradicts | not_found
    reason: str


def _nos(case_nos) -> set[str]:
    return set().union(set(), *(verify.case_numbers(n) for n in case_nos))


def _usable(cands, n, min_score):
    """운영 search_agent 와 같은 규칙 — 상위 n 건 중 점수·본문 조건을 만족하는 것."""
    return [
        c
        for c in cands[:n]
        if c["score"] >= min_score and (c["판결요지"] or c["판시사항"])
    ]


def _cited(c):
    return {
        "case_no": c["case_no"],
        "summary": (c["판결요지"] or c["판시사항"])[: dg._SUMMARY_CHARS] or None,
    }


async def judge(text, c):
    nos = verify.case_numbers(c["case_no"])
    lines = [ln for ln in text.splitlines() if verify.case_numbers(ln) & nos]
    excerpt = (
        f"[판시사항] {c['판시사항'] or '없음'}\n[판결요지] {c['판결요지'] or '없음'}"
    )
    res = await get_openai_client().chat.completions.parse(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": JUDGE},
            {
                "role": "user",
                "content": f"[판례 발췌]\n{excerpt[: dg._SOURCE_CHARS]}\n\n[인용 문장]\n"
                + "\n".join(lines),
            },
        ],
        response_format=Verdict,
    )
    v = res.choices[0].message.parsed
    return v.verdict if v else "not_found"


def _auto(c):
    """운영 search_agent 가 만드는 것과 같은 형태의 자동 보강 판례."""
    excerpt = (
        f"[판시사항] {c['판시사항'] or '없음'}\n[판결요지] {c['판결요지'] or '없음'}"
    )
    return {**_cited(c), "source": excerpt[: dg._SOURCE_CHARS], "auto": True}


async def run_one(sc, given, labels, system):
    with_given = {**sc["inputs"], "cited_precedents": [_cited(c) for c in given]}
    if system == "single":
        row = await base.run({**sc, "inputs": with_given}, "single")
    else:
        precedents = [_auto(c) for c in given]

        async def from_screen(doc_type, inputs):
            final = await SCREEN_GRAPH.ainvoke(
                {"doc_type": doc_type, "inputs": inputs, "precedents": precedents}
            )
            status = "error" if final.get("issues") else "done"
            return status, final.get("text", ""), final

        base._multi = from_screen  # base.run 이 시간·토큰을 같은 방식으로 잰다
        empty = {**sc["inputs"], "cited_precedents": []}
        row = await base.run({**sc, "inputs": empty}, "multi")
    text = row["text"]
    # 채점은 두 방식 모두 '후보를 받은 입력' 기준 — 후보 사건번호는 제공된 것으로 본다
    row.update(
        base.score(
            {**sc, "inputs": with_given},
            base.TYPES[sc["doc_type"]],
            row["status"],
            text,
        )
    )
    in_text = verify.case_numbers(text)
    cited = [c for c in given if verify.case_numbers(c["case_no"]) & in_text]
    irrelevant = {no for no, v in labels.items() if v["label"] == "irrelevant"}
    grounding = [await judge(text, c) for c in cited]
    row.update(
        given=[c["case_no"] for c in given],
        given_irrelevant=sorted(_nos(c["case_no"] for c in given) & irrelevant),
        cited=[c["case_no"] for c in cited],
        cited_irrelevant=sorted(_nos(c["case_no"] for c in cited) & irrelevant),
        grounding=grounding,
        multi_started_with=len(row.get("screening") or [])
        if system == "multi"
        else None,
    )
    return row


def _pct(n, d):
    return round(n / d * 100, 1) if d else None


def summarize(rows):
    out = []
    for cond in CONDITIONS:
        for system in ("single", "multi"):
            rs = [r for r in rows if r["condition"] == cond and r["system"] == system]
            with_irr = [r for r in rs if r["given_irrelevant"]]
            with_given = [r for r in rs if r["given"]]
            g = [v for r in rs for v in r["grounding"]]
            out.append(
                {
                    "condition": cond,
                    "system": system,
                    "runs": len(rs),
                    "completed_pct": _pct(
                        sum(r["status"] == "done" for r in rs), len(rs)
                    ),
                    "pass_all_pct": base._rate(rs, "pass_all"),
                    "runs_with_irrelevant_given": len(with_irr),
                    # 분모 1: 무관 판례가 후보에 있던 실행 / 분모 2: 전체 실행
                    "irrelevant_cited": sum(
                        bool(r["cited_irrelevant"]) for r in with_irr
                    ),
                    "irrelevant_cited_pct": _pct(
                        sum(bool(r["cited_irrelevant"]) for r in with_irr),
                        len(with_irr),
                    ),
                    "irrelevant_cited_pct_all_runs": _pct(
                        sum(bool(r["cited_irrelevant"]) for r in rs), len(rs)
                    ),
                    "runs_without_citation": sum(not r["cited"] for r in with_given),
                    "runs_with_candidates": len(with_given),
                    "citations": len(g),
                    "contradicts_pct": _pct(g.count("contradicts"), len(g)),
                    "consistent_pct": _pct(g.count("consistent"), len(g)),
                    "no_citation_pct": _pct(
                        sum(not r["cited"] for r in with_given), len(with_given)
                    ),
                    "seconds_median": round(
                        statistics.median(r["seconds"] for r in rs), 2
                    ),
                    "llm_calls_mean": round(
                        statistics.mean(r["llm_calls"] for r in rs), 2
                    ),
                    "cost_usd_mean": round(
                        statistics.mean(r["cost_usd"] for r in rs), 5
                    ),
                }
            )
    return out


async def collect(scenarios, frozen, reps, seed, f):
    rng = random.Random(seed)
    rows = []
    for rep in range(reps):
        for cond, (n, min_score) in CONDITIONS.items():
            for sc in scenarios:
                fz = frozen["scenarios"][sc["id"]]
                given = _usable(fz["candidates"], n, min_score)
                labels = frozen["labels"]["by_scenario"].get(sc["id"], {})
                for system in rng.sample(["single", "multi"], 2):
                    row = {
                        "rep": rep,
                        "condition": cond,
                        **await run_one(sc, given, labels, system),
                    }
                    rows.append(row)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    print(
                        rep,
                        cond,
                        sc["id"],
                        system,
                        row["status"],
                        row["cited"],
                        row["cited_irrelevant"],
                        row["grounding"],
                        flush=True,
                    )
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261017)
    args = ap.parse_args()
    logging.disable(logging.CRITICAL)
    base._instrument()

    frozen = json.loads((HERE / "noise_candidates.json").read_text())
    all_sc = {
        s["id"]: s
        for s in json.loads((HERE / "scenarios.json").read_text())["scenarios"]
    }
    excluded = frozen.get("excluded_scenarios", {})
    scenarios = [all_sc[s] for s in frozen["scenarios"] if s not in excluded]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    with open(out / "runs.jsonl", "w") as f:
        rows = asyncio.run(collect(scenarios, frozen, args.reps, args.seed, f))
    summary = summarize(rows)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    meta = {
        "experiment": "A-noise",
        "started": started,
        "commit": base._git("rev-parse", "--short", "HEAD").strip()
        + (
            "-dirty"
            if base._git("status", "--porcelain", "app", "scripts").strip()
            else ""
        ),
        "model": settings.OPENAI_MODEL,
        "conditions": {
            k: {"top_n": n, "min_score": s} for k, (n, s) in CONDITIONS.items()
        },
        "candidates_frozen_at": frozen["frozen_at"],
        "labels_at": frozen["labels"]["labeled_at"],
        "scenarios": [s["id"] for s in scenarios],
        "excluded": excluded,
        "reps": args.reps,
        "seed": args.seed,
        "judge": "평가용 LLM 판정(gpt-4o), 두 방식 동일 기준, 시스템 비용 미포함",
        "cost_scope": "검색 단계(Supervisor 판단·예선 채점·임베딩) 비용 제외 — 두 방식 모두 고정 후보에서 시작",
        "candidate_source": "로컬 키워드 검색(벡터 DB 없음). 운영은 하이브리드라 후보가 다를 수 있음",
        "vector_db": bool(settings.VECTOR_DB_URL),
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
