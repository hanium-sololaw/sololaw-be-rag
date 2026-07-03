"""판례 검색 오케스트레이션 — 2단계 랭킹.

검색(law.go.kr) → 분야 필터 → 후보 전체 본문 병렬 조회
→ [예선] LLM 1회 일괄 관련도 채점 → 상위 limit 건 선발
→ [본선] 참고 포인트 병렬 생성 → 참조조문 집계(관련 법령) → 응답.
점수의 출처는 예선 하나로 통일한다.
"""

import asyncio
import logging
import re

import httpx

from app.cases import client
from app.cases.prompts import relevance as note_prompt
from app.cases.prompts import rerank as rerank_prompt
from app.cases.schemas import (
    CaseCard,
    CaseCategory,
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
        reference_note=note,
        detail_url=client.public_detail_url(serial_id),
    )


async def search_cases(req: SearchRequest) -> SearchResponse:
    async with httpx.AsyncClient() as http:
        total, items = await client.search_precedents(
            http, req.query, display=_CANDIDATES
        )

        if req.category:
            label = _CATEGORY_LABELS[req.category]
            items = [i for i in items if label in (i.get("사건종류명") or "")]
        items = items[:_CANDIDATES]

        # 후보 전체 본문 병렬 조회 (실패한 건은 빈 본문으로 계속 진행)
        detail_results = await asyncio.gather(
            *(
                client.fetch_precedent_detail(http, str(i["판례일련번호"]))
                for i in items
            ),
            return_exceptions=True,
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
