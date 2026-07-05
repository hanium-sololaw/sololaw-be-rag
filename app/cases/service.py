"""판례 검색 오케스트레이션 — 하이브리드 RAG + 2단계 랭킹.

키워드 확정 → 후보 확보 [하이브리드: (a) law.go.kr 키워드 검색 + (b) 판례 임베딩
유사도 검색] → 병합·중복 제거 → 본문 확보(벡터 후보는 코퍼스 프리로드 재사용)
→ [예선] LLM 1회 일괄 관련도 채점 → 상위 limit 건 선발
→ [본선] 참고 포인트 병렬 생성 → 참조조문 집계(관련 법령) → 응답.
점수의 출처는 예선 하나로 통일하며, 벡터 저장소 미가용 시 키워드 검색만으로 폴백한다.
"""

import asyncio
import logging
import re

import httpx

from app.cases import client, embedding
from app.cases.prompts import keywords as keywords_prompt
from app.cases.prompts import relevance as note_prompt
from app.cases.prompts import rerank as rerank_prompt
from app.cases.schemas import (
    CaseCard,
    CaseCategory,
    KeywordsDraft,
    NoteDraft,
    RelatedStatute,
    RerankDraft,
    SearchRequest,
    SearchResponse,
)
from app.core.config import settings
from app.shared.llm import get_openai_client

logger = logging.getLogger(__name__)

_CANDIDATES = 20  # 예선 후보 수 (law.go.kr 조회 건수)
_EXCERPT_CHARS = 300  # 예선용 판시사항 발췌 길이
_CONCURRENCY = 5  # 동시 LLM 호출 제한 (본선)

# 분야 필터 → 국가법령정보센터 사건종류명 매칭 문자열
_CATEGORY_LABELS: dict[CaseCategory, str] = {
    CaseCategory.CIVIL: "민사",
    CaseCategory.CRIMINAL: "형사",
    CaseCategory.ADMINISTRATIVE: "행정",
    CaseCategory.FAMILY: "가사",
}

# 참조조문에서 "법명 제N조(의M)" 추출. 법명 생략 시 직전 법명을 승계.
# 법명은 띄어쓰기 포함 가능 (예: 상가건물 임대차보호법)
_STATUTE_RE = re.compile(
    r"(?:([가-힣][가-힣·]*(?:\s[가-힣][가-힣·]*)*?(?:법|법률)"
    r"(?:\s?시행령|\s?시행규칙)?)\s*)?제(\d+)조(의\d+)?"
)


def _aggregate_statutes(texts: list[str], top: int = 5) -> list[RelatedStatute]:
    """판례별 참조조문 텍스트에서 조문을 추출해 판례 단위로 집계한다."""
    counts: dict[str, int] = {}
    for text in texts:
        found: set[str] = set()
        current_law: str | None = None
        for m in _STATUTE_RE.finditer(text):
            law, jo, ui = m.group(1), m.group(2), m.group(3) or ""
            if law:
                current_law = law
            if not current_law:
                continue
            found.add(f"{current_law} 제{jo}조{ui}")
        for name in found:
            counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [RelatedStatute(name=n, count=c) for n, c in ranked[:top]]


def _ranked_indices(n: int, score_map: dict[int, int]) -> list[tuple[int, int]]:
    """(후보 인덱스, 0~100 보정 점수) 를 점수 내림차순으로 반환. 누락 후보는 0점."""
    scored = [(i, max(0, min(100, score_map.get(i, 0)))) for i in range(n)]
    return sorted(scored, key=lambda x: -x[1])


def _vector_row_to_item(row: dict) -> dict:
    """벡터 검색 결과를 키워드 검색 item 형태로 정규화한다.

    코퍼스에 본문(판시사항·판결요지·참조조문)이 이미 있으므로 _detail 로
    프리로드해 law.go.kr 본문 조회를 생략한다.
    """
    return {
        "판례일련번호": row["serial_id"],
        "사건명": row["name"],
        "사건번호": row["case_no"],
        "법원명": row["court"],
        "선고일자": row["decision_date"],
        "사건종류명": row["category"],
        "_similarity": round(row["similarity"] * 100),
        "_detail": {
            "판시사항": row["summary"],
            "판결요지": row["holding"],
            "참조조문": row["statutes"],
        },
    }


def _merge_candidates(keyword_items: list[dict], vector_rows: list[dict]) -> list[dict]:
    """키워드·벡터 후보를 병합한다 — 판례일련번호 기준 중복 제거.

    양쪽에 모두 있는 판례는 키워드 항목을 유지하고 유사도·프리로드만 보강한다.
    """
    merged: dict[str, dict] = {}
    for item in keyword_items:
        sid = str(item.get("판례일련번호", ""))
        if sid:
            merged[sid] = dict(item)
    for row in vector_rows:
        sid = str(row["serial_id"])
        normalized = _vector_row_to_item(row)
        if sid in merged:
            merged[sid]["_similarity"] = normalized["_similarity"]
            merged[sid]["_detail"] = normalized["_detail"]
        else:
            merged[sid] = normalized
    return list(merged.values())


async def resolve_query(query: str | None, case_context: str | None) -> str:
    """검색 키워드 확정 — query 가 없으면 사건 맥락에서 LLM 으로 추출한다.

    내 사건 기반 탭은 query 없이 case_context 만 보낸다.
    추출 실패 시 사건 맥락 앞부분으로 폴백 (본문 검색이라 어느 정도 동작).
    """
    if query and query.strip():
        return query.strip()
    try:
        completion = await get_openai_client().chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": keywords_prompt.SYSTEM},
                {
                    "role": "user",
                    "content": keywords_prompt.build_user_prompt(case_context or ""),
                },
            ],
            response_format=KeywordsDraft,
        )
        draft = completion.choices[0].message.parsed
        if draft and draft.keywords.strip():
            return draft.keywords.strip()
    except Exception:
        logger.exception("검색 키워드 추출 실패 — 사건 맥락 앞부분으로 폴백")
    return (case_context or "").strip()[:50]


async def _rerank(
    req: SearchRequest, items: list[dict], details: list[dict]
) -> list[tuple[int, int]]:
    """예선 — 후보 전체를 LLM 1회로 일괄 채점. 실패 시 검색 순서 폴백(0점)."""
    candidates = [
        (
            i,
            item.get("사건명", ""),
            (detail.get("판시사항") or "")[:_EXCERPT_CHARS],
        )
        for i, (item, detail) in enumerate(zip(items, details))
    ]
    try:
        completion = await get_openai_client().chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": rerank_prompt.SYSTEM},
                {
                    "role": "user",
                    "content": rerank_prompt.build_user_prompt(
                        req.query, req.case_context, candidates
                    ),
                },
            ],
            response_format=RerankDraft,
        )
        draft = completion.choices[0].message.parsed
        score_map = {s.id: s.relevance for s in draft.scores} if draft else {}
    except Exception:
        logger.exception("판례 예선 채점 실패 — 검색 순서로 폴백")
        score_map = {}
    return _ranked_indices(len(items), score_map)


async def _make_card(
    req: SearchRequest, item: dict, detail: dict, relevance: int
) -> CaseCard:
    """본선 — 예선을 통과한 판례의 참고 포인트를 생성해 카드로 만든다."""
    serial_id = str(item.get("판례일련번호", ""))
    name = item.get("사건명", "")
    note = "AI 요약에 실패했습니다."
    try:
        completion = await get_openai_client().chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": note_prompt.SYSTEM},
                {
                    "role": "user",
                    "content": note_prompt.build_user_prompt(
                        req.query,
                        req.case_context,
                        name,
                        detail.get("판시사항", ""),
                        detail.get("판결요지", ""),
                    ),
                },
            ],
            response_format=NoteDraft,
        )
        draft = completion.choices[0].message.parsed
        if draft:
            note = draft.reference_note
    except Exception:
        logger.exception("판례 참고 포인트 생성 실패 (serial=%s)", serial_id)

    return CaseCard(
        serial_id=serial_id,
        name=name,
        case_no=item.get("사건번호", ""),
        court=item.get("법원명", ""),
        decision_date=str(item.get("선고일자", "")),
        category=item.get("사건종류명", ""),
        relevance=relevance,
        similarity=item.get("_similarity"),
        reference_note=note,
        detail_url=client.public_detail_url(serial_id),
    )


async def search_cases(req: SearchRequest) -> SearchResponse:
    # 키워드 확정 (내 사건 기반 탭은 case_context 에서 추출)
    resolved = await resolve_query(req.query, req.case_context)
    req = req.model_copy(update={"query": resolved})
    label = _CATEGORY_LABELS[req.category] if req.category else None

    async with httpx.AsyncClient() as http:
        # (a) 키워드 후보 — law.go.kr 실시간 검색 (최신 판례 커버)
        total, keyword_items = await client.search_precedents(
            http, req.query, display=_CANDIDATES
        )
        if label:
            keyword_items = [
                i for i in keyword_items if label in (i.get("사건종류명") or "")
            ]

        # (b) 벡터 후보 — 판례 임베딩 코퍼스 유사도 검색 (용어 불일치 커버)
        vector_rows: list[dict] = []
        try:
            [query_vec] = await embedding.embed_texts([req.query])
            vector_rows = await embedding.search_similar(
                query_vec, top_k=_CANDIDATES, category=label
            )
        except Exception:
            logger.warning("벡터 검색 미가용 — 키워드 후보만 사용", exc_info=True)

        items = _merge_candidates(keyword_items, vector_rows)

        # 본문 확보 — 벡터 후보는 코퍼스 프리로드 사용, 키워드 후보만 API 조회
        async def _detail_of(item: dict) -> dict:
            if "_detail" in item:
                return item["_detail"]
            return await client.fetch_precedent_detail(http, str(item["판례일련번호"]))

        detail_results = await asyncio.gather(
            *(_detail_of(i) for i in items), return_exceptions=True
        )
    details: list[dict] = []
    for i, d in zip(items, detail_results):
        if isinstance(d, BaseException):
            logger.warning(
                "판례 본문 조회 실패 (serial=%s): %s", i.get("판례일련번호"), d
            )
            d = {}
        details.append(d)

    # [예선] 일괄 채점 → 상위 limit 건 선발
    ranked = await _rerank(req, items, details)
    finalists = ranked[: req.limit]

    # [본선] 참고 포인트 병렬 생성
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _bounded(idx: int, score: int) -> CaseCard:
        async with semaphore:
            return await _make_card(req, items[idx], details[idx], score)

    cards = await asyncio.gather(*(_bounded(i, s) for i, s in finalists))

    # 관련 법령은 본선 진출작 기준으로 집계 (무관한 판례의 조문 배제)
    statutes = _aggregate_statutes(
        [details[i].get("참조조문", "") for i, _ in finalists]
    )

    return SearchResponse(total=total, cases=list(cards), statutes=statutes)
