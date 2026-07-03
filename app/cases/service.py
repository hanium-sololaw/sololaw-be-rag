"""판례 검색 오케스트레이션.

검색(law.go.kr) → 분야 필터 → 본문 병렬 조회 → LLM 관련도·참고 포인트 병렬 산출
→ 참조조문 집계(관련 법령) → 관련도순 응답.
"""

import asyncio
import logging
import re

import httpx

from app.cases import client
from app.cases.prompts import relevance as prompt
from app.cases.schemas import (
    CaseCard,
    CaseCategory,
    RelatedStatute,
    RelevanceDraft,
    SearchRequest,
    SearchResponse,
)
from app.core.config import settings
from app.shared.llm import get_openai_client

logger = logging.getLogger(__name__)

_CONCURRENCY = 5  # 동시 LLM 호출 제한

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


async def _score_case(req: SearchRequest, item: dict, detail: dict) -> CaseCard:
    """판례 한 건의 관련도·참고 포인트를 LLM 으로 산출해 카드로 만든다."""
    serial_id = str(item.get("판례일련번호", ""))
    name = item.get("사건명", "")
    relevance, note = 0, "AI 분석에 실패했습니다."
    try:
        completion = await get_openai_client().chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": prompt.SYSTEM},
                {
                    "role": "user",
                    "content": prompt.build_user_prompt(
                        req.query,
                        req.case_context,
                        name,
                        detail.get("판시사항", ""),
                        detail.get("판결요지", ""),
                    ),
                },
            ],
            response_format=RelevanceDraft,
        )
        draft = completion.choices[0].message.parsed
        if draft:
            relevance = max(0, min(100, draft.relevance))
            note = draft.reference_note
    except Exception:
        logger.exception("판례 관련도 산출 실패 (serial=%s)", serial_id)

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
        total, items = await client.search_precedents(http, req.query)

        if req.category:
            label = _CATEGORY_LABELS[req.category]
            items = [i for i in items if label in (i.get("사건종류명") or "")]

        top_items = items[: req.limit]

        # 본문 병렬 조회 (실패한 건은 빈 본문으로 계속 진행)
        detail_results = await asyncio.gather(
            *(
                client.fetch_precedent_detail(http, str(i["판례일련번호"]))
                for i in top_items
            ),
            return_exceptions=True,
        )
    details: list[dict] = []
    for i, d in zip(top_items, detail_results):
        if isinstance(d, BaseException):
            logger.warning(
                "판례 본문 조회 실패 (serial=%s): %s", i.get("판례일련번호"), d
            )
            d = {}
        details.append(d)

    # LLM 관련도 산출 병렬 실행
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _bounded(item: dict, detail: dict) -> CaseCard:
        async with semaphore:
            return await _score_case(req, item, detail)

    cards = await asyncio.gather(*(_bounded(i, d) for i, d in zip(top_items, details)))
    cards = sorted(cards, key=lambda c: -c.relevance)

    statutes = _aggregate_statutes([d.get("참조조문", "") for d in details])

    return SearchResponse(total=total, cases=list(cards), statutes=statutes)
