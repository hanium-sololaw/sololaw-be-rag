"""판례 검색 정확도 평가 — 원본 판례 재검색 성능 (Recall@k·MRR).

코퍼스에서 층화 추출한 판례의 판시사항을 일반인의 사건 설명으로 바꿔 질의로 쓰고, 원본 판례를
정답 하나로 둔다. 전문가가 평가한 전체 검색 관련도가 아니라 '원본을 다시 찾아내는가'를 잰다.

같은 코퍼스(precedents 테이블)에서 비교:
- keyword : 코퍼스 대상 BM25 (한글 2글자 단위 토큰)
- vector  : 운영과 같은 임베딩 유사도 검색 (search_similar)
- hybrid  : keyword·vector 상위 20건을 RRF(k=60)로 합침
- hybrid_rerank: hybrid 후보에 운영 예선 채점(LLM) 적용
참고(검색 대상이 다름): production — 운영 경로 그대로. law.go.kr 실시간 키워드(전국 판례 DB) +
  코퍼스 벡터 → 예선 채점. 키워드 후보는 코퍼스 밖 판례를 포함한다.

1) 질의 생성(로컬): PYTHONPATH=. .venv/bin/python -m scripts.eval_search make-queries <sample.json>
   → scripts/benchmark/search_queries.json (검색 실행 전에 커밋해 고정)
2) 평가(EC2 컨테이너, 벡터 DB 필요): python -m scripts.eval_search run --out <폴더>
"""

import argparse
import asyncio
import json
import re
import statistics
import time
from array import array
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np
from pydantic import BaseModel

from app.cases import client, embedding, service
from app.cases.schemas import SearchRequest
from app.core.config import settings
from app.shared.llm import get_openai_client

QUERIES = Path(__file__).parent / "benchmark" / "search_queries.json"
TOP = 20
KS = (1, 5, 10, 20)
METHODS = ("keyword", "vector", "hybrid", "hybrid_rerank", "production")

QUERY_PROMPT = """당신은 법률 지식이 없는 일반인입니다. 아래 판례의 판시사항·판결요지를 읽고, 이와 비슷한
일을 겪은 사람이 판례 검색창에 자기 사정을 설명하듯 2~3문장으로 씁니다.

## 규칙
- 사건번호·법원명·선고일·당사자 이름은 쓰지 않는다.
- 판시사항의 법률 문구를 그대로 옮기지 말고 일상 표현으로 바꾼다.
  (예: "임대차보증금 반환채무" → "집주인이 보증금을 안 돌려줌")
- 판례의 결론(누가 이겼는지)은 쓰지 않는다. 겪은 상황과 궁금한 점만 쓴다."""


class Query(BaseModel):
    query: str


async def make_queries(sample_path: str):
    data = json.loads(Path(sample_path).read_text())
    out = []
    for s in data["sample"]:
        res = await get_openai_client().chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": QUERY_PROMPT},
                {
                    "role": "user",
                    "content": f"[사건명] {s['name']}\n[판시사항] {s['summary']}\n"
                    f"[판결요지] {s['holding'][:1500]}",
                },
            ],
            response_format=Query,
        )
        q = res.choices[0].message.parsed
        out.append(
            {
                "serial_id": s["serial_id"],
                "case_no": s["case_no"],
                "stratum": s["stratum"],
                "category": s["category"],
                "query": q.query if q else "",
            }
        )
        print(len(out), s["stratum"], out[-1]["query"][:60])
    QUERIES.write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "model": settings.OPENAI_MODEL,
                "corpus_size": data["corpus_size"],
                "strata_sizes": data["strata_sizes"],
                "seed": data["seed"],
                "note": "검색 실행 전 고정. 정답 = serial_id 원본 판례 1건",
                "queries": out,
            },
            ensure_ascii=False,
            indent=1,
        )
    )


def _bigrams(text: str) -> list[str]:
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", text)
    return [t[i : i + 2] for i in range(len(t) - 1)]


class BM25:
    """코퍼스 대상 키워드 검색 — 형태소 분석기 없이 2글자 단위로 쪼갠다.

    운영 서버 메모리가 작아(여유 1GB 미만) 문서별 사전 대신 numpy 역색인으로 담는다.
    """

    def __init__(self, docs: dict[str, str], k1=1.5, b=0.75):
        self.ids = list(docs)
        vocab: dict[str, int] = {}
        tok, doc, tf = array("i"), array("i"), array("f")
        lens = np.zeros(len(self.ids), dtype=np.float32)
        for d, sid in enumerate(self.ids):
            counts = Counter(_bigrams(docs[sid]))
            lens[d] = sum(counts.values())
            for t, c in counts.items():
                tok.append(vocab.setdefault(t, len(vocab)))
                doc.append(d)
                tf.append(c)
        order = np.argsort(np.frombuffer(tok, dtype=np.int32), kind="stable")
        tok_s = np.frombuffer(tok, dtype=np.int32)[order]
        self.doc = np.frombuffer(doc, dtype=np.int32)[order]
        self.tf = np.frombuffer(tf, dtype=np.float32)[order]
        self.start = np.searchsorted(tok_s, np.arange(len(vocab) + 1))
        df = np.diff(self.start)
        n = len(self.ids)
        self.idf = np.log(1 + (n - df + 0.5) / (df + 0.5)).astype(np.float32)
        self.norm = k1 * (1 - b + b * lens / lens.mean())
        self.vocab, self.k1 = vocab, k1

    def search(self, query: str, top: int) -> list[str]:
        scores = np.zeros(len(self.ids), dtype=np.float32)
        for t in set(_bigrams(query)):
            i = self.vocab.get(t)
            if i is None:
                continue
            lo, hi = self.start[i], self.start[i + 1]
            d, f = self.doc[lo:hi], self.tf[lo:hi]
            scores[d] += self.idf[i] * f * (self.k1 + 1) / (f + self.norm[d])
        hits = np.nonzero(scores)[0]
        best = hits[np.argsort(-scores[hits], kind="stable")][:top]
        return [self.ids[d] for d in best]


def _rrf(*lists: list[str], k=60) -> list[str]:
    score: dict[str, float] = {}
    for lst in lists:
        for rank, sid in enumerate(lst):
            score[sid] = score.get(sid, 0) + 1 / (k + rank + 1)
    return sorted(score, key=lambda s: -score[s])


async def _rerank(query: str, order: list[str], meta: dict) -> list[str]:
    """운영 예선 채점을 그대로 적용한다 — 동점은 입력 순서(RRF 순)를 유지한다."""
    items = [{"사건명": meta[s]["name"]} for s in order]
    details = [{"판시사항": meta[s]["summary"]} for s in order]
    req = SearchRequest(query=query, case_context=query)
    ranked = await service._rerank(req, items, details)
    return [order[i] for i, _ in ranked]


async def _production(query: str, http) -> list[str]:
    """운영 경로 — 키워드 확정(LLM) → law.go.kr 키워드 + 코퍼스 벡터 → 예선 채점."""
    keywords = await service.resolve_query(None, query)
    _, kw_items = await client.search_precedents(http, keywords, display=TOP)
    [vec] = await embedding.embed_texts([keywords])
    vec_rows = await embedding.search_similar(vec, top_k=TOP)
    items = service._merge_candidates(kw_items, vec_rows)
    details = []
    for it in items:
        if "_detail" in it:
            details.append(it["_detail"])
            continue
        try:
            details.append(
                await client.fetch_precedent_detail(http, str(it["판례일련번호"]))
            )
        except Exception:  # noqa: BLE001 — 운영도 본문 조회 실패는 빈 본문으로 진행한다
            details.append({})
    req = SearchRequest(query=keywords, case_context=query)
    ranked = await service._rerank(req, items, details)
    return [str(items[i]["판례일련번호"]) for i, _ in ranked]


def _metrics(rank: int | None) -> dict:
    m = {f"recall@{k}": int(rank is not None and rank <= k) for k in KS}
    m["rr"] = 1 / rank if rank is not None and rank <= TOP else 0.0
    return m


def _agg(rs: list[dict], methods: list[str]) -> dict:
    return {
        m: {
            **{
                f"recall@{k}": round(
                    statistics.mean(r[m][f"recall@{k}"] for r in rs) * 100, 1
                )
                for k in KS
            },
            "mrr@20": round(statistics.mean(r[m]["rr"] for r in rs), 3),
        }
        for m in methods
    }


async def _evaluate(qs, with_production, f) -> tuple[list[dict], list[dict]]:
    rows = await _load_corpus()  # 풀은 이벤트 루프에 묶여 있어 같은 루프에서 읽는다
    meta = {r["serial_id"]: r for r in rows}
    bm25 = BM25(
        {r["serial_id"]: f"{r['name']} {r['summary']} {r['holding']}" for r in rows}
    )
    results = []
    async with httpx.AsyncClient() as http:
        for i, q in enumerate(qs):
            t0 = time.monotonic()
            kw = bm25.search(q["query"], TOP)
            [vec] = await embedding.embed_texts([q["query"]])
            vr = [
                r["serial_id"] for r in await embedding.search_similar(vec, top_k=TOP)
            ]
            hy = _rrf(kw, vr)
            lists = {
                "keyword": kw,
                "vector": vr,
                "hybrid": hy[:TOP],
                "hybrid_rerank": (await _rerank(q["query"], hy, meta))[:TOP],
            }
            row = dict(q)
            if with_production:
                try:
                    lists["production"] = (await _production(q["query"], http))[:TOP]
                except Exception as e:  # noqa: BLE001 — 장애도 결과로 남긴다
                    lists["production"] = []
                    row["production_error"] = repr(e)[:200]
            row["seconds"] = round(time.monotonic() - t0, 1)
            for name, lst in lists.items():
                rank = lst.index(q["serial_id"]) + 1 if q["serial_id"] in lst else None
                row[name] = {"rank": rank, **_metrics(rank)}
            results.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(i + 1, q["stratum"], {n: row[n]["rank"] for n in lists}, flush=True)
    return rows, results


async def _load_corpus() -> list[dict]:
    pool = await embedding.get_pool()
    async with pool.acquire() as c:
        return [
            dict(r)
            for r in await c.fetch(
                "SELECT serial_id, name, summary, holding, category FROM precedents"
            )
        ]


def run(out: Path, with_production: bool):
    qs = json.loads(QUERIES.read_text())["queries"]
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now().isoformat(timespec="seconds")
    with open(out / "runs.jsonl", "w") as f:
        rows, results = asyncio.run(_evaluate(qs, with_production, f))
    methods = [m for m in METHODS if m in results[0]]
    strata = sorted({r["stratum"] for r in results})
    summary = {
        "overall": {"n": len(results), **_agg(results, methods)},
        "by_stratum": {
            s: {
                "n": sum(r["stratum"] == s for r in results),
                **_agg([r for r in results if r["stratum"] == s], methods),
            }
            for s in strata
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    meta = {
        "started": started,
        "model": settings.OPENAI_MODEL,
        "corpus_size": len(rows),
        "queries": len(qs),
        "top": TOP,
        "rrf_k": 60,
        "keyword": "코퍼스 BM25(한글 2-gram, k1=1.5, b=0.75)",
        "production_note": "law.go.kr 실시간 키워드는 전국 판례 DB 대상이라 검색 대상이 다름",
        "concurrency": 1,
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(json.dumps(summary["overall"], ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    mq = sub.add_parser("make-queries")
    mq.add_argument("sample")
    rn = sub.add_parser("run")
    rn.add_argument("--out", required=True)
    rn.add_argument("--no-production", action="store_true")
    args = ap.parse_args()
    if args.cmd == "make-queries":
        asyncio.run(make_queries(args.sample))
    else:
        run(Path(args.out), not args.no_production)


if __name__ == "__main__":
    main()
