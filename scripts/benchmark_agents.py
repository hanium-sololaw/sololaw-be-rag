"""실험 A — 단일 호출과 Multi-Agent 문서 생성 비교 벤치마크.

같은 입력·같은 판례(cited_precedents)·같은 문서 프롬프트를 두 방식에 주고, 자동 검사 통과율·
정상 완료율·처리 시간·토큰 비용을 잰다. 구조만 다르게 하고 제공 자료는 같게 둔다.
- single: 문서 생성기 1회 호출 (선별·검증·설명 없음)
- multi : Multi-Agent 문서 그래프 전체 (판례가 주어졌으므로 검색은 건너뛴다)

실행 (레포 루트, .env 필요, OpenAI·law.go.kr 비용 발생):
  PYTHONPATH=. .venv/bin/python -m scripts.benchmark_agents --reps 3 --out <결과 폴더>
  uv run --with matplotlib python -m scripts.benchmark_plot <결과 폴더>

자동 검사는 형식·입력값 보존·청구 구성·인용 일치를 본다. 법률 전문가의 품질 평가를 대체하지 않는다.
"""

import argparse
import asyncio
import csv
import json
import logging
import random
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path

from app.agent import document_graph as dg
from app.agent import verify
from app.cases import service as case_service
from app.core.config import settings
from app.documents.prompts.application import SPECS
from app.documents.registry import GENERATORS
from app.documents.schemas.common import DocumentType
from app.documents.service import parse_sections
from app.shared.llm import get_openai_client

SCENARIOS = Path(__file__).parent / "benchmark" / "scenarios.json"
# shortcut: 단가는 상수다(gpt-4o 공개 단가, USD/1M 토큰), 모델·단가가 바뀌면 고친다.
PRICE = {"input": 2.50, "output": 10.00}
TYPES = {
    "complaint": DocumentType.COMPLAINT,
    "brief": DocumentType.BRIEF,
    "application": DocumentType.APPLICATION,
}

# 실행 1건 동안의 LLM 호출·토큰. 동시 실행을 하지 않으므로 실행마다 비우고 쓴다.
usage = {"calls": 0, "input": 0, "output": 0}


def _add(u):
    if u:
        usage["input"] += u.prompt_tokens
        usage["output"] += u.completion_tokens


def _instrument():
    client = get_openai_client()
    parse, create = client.chat.completions.parse, client.chat.completions.create

    async def counted_parse(*a, **k):
        usage["calls"] += 1
        res = await parse(*a, **k)
        _add(res.usage)
        return res

    async def counted_create(*a, **k):
        usage["calls"] += 1
        if k.get("stream"):
            # 스트리밍은 마지막 청크에만 usage 가 실린다 (choices 가 비어 생성기는 건너뛴다)
            k["stream_options"] = {"include_usage": True}
            stream = await create(*a, **k)

            async def relay():
                async for chunk in stream:
                    _add(chunk.usage)
                    yield chunk

            return relay()
        res = await create(*a, **k)
        _add(res.usage)
        return res

    client.chat.completions.parse = counted_parse
    client.chat.completions.create = counted_create


async def _no_search(req):
    """실험 A 는 두 방식에 같은 판례만 준다 — Multi-Agent 가 스스로 검색해 자료를 더 얻지 않게 한다.
    Supervisor 의 검색 판단 호출은 구조의 일부라 그대로 두고 비용에 포함한다."""
    return case_service.Retrieval(0, [], [], [], None)


async def _single(doc_type, inputs):
    text = "".join([d async for d in GENERATORS[doc_type].generate_stream(inputs)])
    return "done", text, {}


async def _multi(doc_type, inputs):
    final = await dg.graph.ainvoke({"doc_type": doc_type, "inputs": inputs})
    status = "error" if final.get("issues") else "done"
    return status, final.get("text", ""), final


def _expected_sections(doc_type, inputs):
    if doc_type == DocumentType.APPLICATION:
        return set(SPECS[inputs["application_type"]].sections)
    return set(GENERATORS[doc_type].section_map.values())


def score(sc, doc_type, status, text):
    """시나리오 기대값으로 채점한다. 실패한 실행은 모든 검사를 불통과로 센다."""
    exp = sc["expect"]
    if status != "done":
        return {
            "sections": False,
            "values": False,
            "composition": False,
            "no_hallucination": False,
            "no_irrelevant": False,
            "pass_all": False,
        }
    sections = parse_sections(text, GENERATORS[doc_type].section_map)
    flat = text.replace(" ", "")
    values = all(
        any(alt.replace(" ", "") in flat for alt in alts) for alts in exp["required"]
    )
    composition = None  # 소장만 검사한다
    if exp["conclusion_need"] or exp["cause_ban"]:
        cause = sections.get("claim_cause", "")
        concl = cause[cause.rfind("3.") :] if "3." in cause else cause
        composition = all(w in concl for w in exp["conclusion_need"]) and not any(
            w in cause for w in exp["cause_ban"]
        )
    cited = verify.case_numbers(text)
    checks = {
        "sections": _expected_sections(doc_type, sc["inputs"]) <= set(sections),
        "values": values,
        "composition": composition,
        # 입력에 없는 사건번호 — Multi-Agent 내부 검증과 같은 정의라 독립 검증은 아니다
        "no_hallucination": not verify.unknown_case_numbers(text, sc["inputs"]),
        "no_irrelevant": not (cited & set(exp["irrelevant_precedents"])),
    }
    checks["pass_all"] = all(v is not False for v in checks.values())
    return checks


async def run(sc, system):
    doc_type = TYPES[sc["doc_type"]]
    usage.update(calls=0, input=0, output=0)
    t0 = time.monotonic()
    try:
        status, text, final = await (_single if system == "single" else _multi)(
            doc_type, sc["inputs"]
        )
    except Exception as e:  # noqa: BLE001 — 실패한 실행도 결과로 집계한다
        status, text, final = f"exception: {e!r}"[:200], "", {}
    seconds = time.monotonic() - t0
    cost = (usage["input"] * PRICE["input"] + usage["output"] * PRICE["output"]) / 1e6
    return {
        "scenario": sc["id"],
        "holdout": sc["holdout"],
        "system": system,
        "status": status,
        "seconds": round(seconds, 2),
        "llm_calls": usage["calls"],
        "input_tokens": usage["input"],
        "output_tokens": usage["output"],
        "cost_usd": round(cost, 5),
        "attempts": final.get("attempts", 1),
        "screening": final.get("screening"),
        "explanations": final.get("explanations"),
        **score(sc, doc_type, status, text),
        "text": text,
    }


def _rate(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return round(sum(vals) / len(vals) * 100, 1) if vals else None


def summarize(rows):
    out = []
    for system in ("single", "multi"):
        rs = [r for r in rows if r["system"] == system]
        secs = sorted(r["seconds"] for r in rs)
        out.append(
            {
                "system": system,
                "runs": len(rs),
                "completed_pct": round(
                    sum(r["status"] == "done" for r in rs) / len(rs) * 100, 1
                ),
                "pass_all_pct": _rate(rs, "pass_all"),
                "sections_pct": _rate(rs, "sections"),
                "values_pct": _rate(rs, "values"),
                "composition_pct": _rate(rs, "composition"),
                "no_hallucination_pct": _rate(rs, "no_hallucination"),
                "no_irrelevant_pct": _rate(rs, "no_irrelevant"),
                "rewrite_pct": round(
                    sum(r["attempts"] > 1 for r in rs) / len(rs) * 100, 1
                ),
                "seconds_median": round(statistics.median(secs), 2),
                "seconds_p90": secs[min(len(secs) - 1, int(len(secs) * 0.9))],
                "llm_calls_mean": round(statistics.mean(r["llm_calls"] for r in rs), 2),
                "tokens_mean": round(
                    statistics.mean(r["input_tokens"] + r["output_tokens"] for r in rs)
                ),
                "cost_usd_mean": round(statistics.mean(r["cost_usd"] for r in rs), 5),
            }
        )
    return out


async def collect(scenarios, reps, seed, f) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for rep in range(reps):
        for sc in scenarios:
            # 시스템 순서를 시나리오마다 섞는다 (시간대·캐시 영향 분산)
            for system in rng.sample(["single", "multi"], 2):
                row = {"rep": rep, **await run(sc, system)}
                rows.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                mark = "pass" if row["pass_all"] else "FAIL"
                print(rep, sc["id"], system, row["status"], row["seconds"], mark)
    return rows


def _git(*args) -> str:
    cmd = ["git", "-C", str(Path(__file__).parent.parent), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*", help="시나리오 id 일부만")
    ap.add_argument("--seed", type=int, default=20261016)
    args = ap.parse_args()
    logging.disable(logging.CRITICAL)
    _instrument()
    case_service.retrieve = _no_search

    data = json.loads(SCENARIOS.read_text())
    scenarios = [s for s in data["scenarios"] if not args.only or s["id"] in args.only]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    with open(out / "runs.jsonl", "w") as f:
        rows = asyncio.run(collect(scenarios, args.reps, args.seed, f))

    summary = summarize(rows)
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    meta = {
        "experiment": "A",
        "started": started,
        "commit": _git("rev-parse", "--short", "HEAD").strip()
        + ("-dirty" if _git("status", "--porcelain", "app", "scripts").strip() else ""),
        "model": settings.OPENAI_MODEL,
        "price_usd_per_1m": PRICE,
        "scenarios_version": data["version"],
        "scenarios": len(scenarios),
        "holdout": sum(s["holdout"] for s in scenarios),
        "reps": args.reps,
        "concurrency": 1,
        "seed": args.seed,
        "vector_db": bool(settings.VECTOR_DB_URL),
        "search": "disabled — 두 방식 모두 시나리오의 cited_precedents 만 사용",
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
