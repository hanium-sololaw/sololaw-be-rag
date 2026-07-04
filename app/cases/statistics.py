"""유사 판례 승소율 통계 오케스트레이션.

검색 표본(최근 공개 판례 N건)의 승패를 LLM 배치 분류로 판정해 비율을 낸다.
전국 통계가 아닌 표본 기반 참고 지표이므로 응답에 면책 문구를 포함한다.
동일 키워드 재조회 대비 TTL 인메모리 캐시를 둔다.
"""

import asyncio
import logging
import time

import httpx

from app.cases import client
from app.cases.prompts import outcome as outcome_prompt
from app.cases.schemas import (
    OutcomeBatchDraft,
    OutcomeCounts,
    StatisticsRequest,
    StatisticsResponse,
)
from app.cases.service import _CATEGORY_LABELS, resolve_query
from app.core.config import settings
from app.shared.llm import get_openai_client

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "검색된 공개 판례 표본의 통계적 경향이며 실제 재판 결과를 예측하거나 "
    "보장하지 않습니다. 구체적인 결과는 사건의 사실관계에 따라 달라질 수 있습니다."
)

_BATCH = 25  # LLM 배치 분류 1회당 판례 수
_HOLDING_EXCERPT = 200  # 분류용 판결요지 발췌 길이
_TTL_SECONDS = 3600  # 캐시 유효 시간 1시간
_MIN_CLASSIFIED = 5  # 승소율 산출 최소 판단 건수 — 미만이면 null (소표본 왜곡 방지)

# {캐시키: (저장 시각, 응답)} — 프로세스 재시작 시 초기화되는 인메모리 캐시
_cache: dict[str, tuple[float, StatisticsResponse]] = {}


async def _classify(
    candidates: list[tuple[int, str, str, str, str]],
) -> dict[int, str]:
    """배치 단위로 승패를 병렬 분류해 {후보 인덱스: outcome} 으로 합친다."""
    chunks = [candidates[i : i + _BATCH] for i in range(0, len(candidates), _BATCH)]

    async def _one(chunk: list) -> dict[int, str]:
        try:
            completion = await get_openai_client().chat.completions.parse(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": outcome_prompt.SYSTEM},
                    {
                        "role": "user",
                        "content": outcome_prompt.build_user_prompt(chunk),
                    },
                ],
                response_format=OutcomeBatchDraft,
            )
            draft = completion.choices[0].message.parsed
            return {r.id: r.outcome for r in draft.results} if draft else {}
        except Exception:
            logger.exception("판례 승패 분류 실패 — 해당 배치는 판단 불가 처리")
            return {}

    results = await asyncio.gather(*(_one(c) for c in chunks))
    merged: dict[int, str] = {}
    for m in results:
        merged.update(m)
    return merged


async def get_statistics(req: StatisticsRequest) -> StatisticsResponse:
    query = await resolve_query(req.query, req.case_context)

    cache_key = (
        f"{query}|{req.category.value if req.category else ''}|{req.sample_size}"
    )
    now = time.monotonic()
    hit = _cache.get(cache_key)
    if hit and now - hit[0] < _TTL_SECONDS:
        return hit[1]

    async with httpx.AsyncClient() as http:
        _, items = await client.search_precedents(http, query, display=req.sample_size)
        if req.category:
            label = _CATEGORY_LABELS[req.category]
            items = [i for i in items if label in (i.get("사건종류명") or "")]
        items = items[: req.sample_size]

        detail_results = await asyncio.gather(
            *(
                client.fetch_precedent_detail(http, str(i["판례일련번호"]))
                for i in items
            ),
            return_exceptions=True,
        )

    candidates: list[tuple[int, str, str, str, str]] = []
    for idx, (item, d) in enumerate(zip(items, detail_results)):
        if isinstance(d, BaseException):
            logger.warning(
                "판례 본문 조회 실패 (serial=%s): %s", item.get("판례일련번호"), d
            )
            d = {}
        candidates.append(
            (
                idx,
                item.get("사건명", ""),
                item.get("법원명", ""),
                d.get("주문", ""),
                (d.get("판결요지") or "")[:_HOLDING_EXCERPT],
            )
        )

    outcome_map = await _classify(candidates)

    counts = {"win": 0, "partial": 0, "lose": 0, "unknown": 0}
    for i in range(len(candidates)):
        counts[outcome_map.get(i, "unknown")] += 1
    classified = counts["win"] + counts["partial"] + counts["lose"]
    win_rate = (
        round((counts["win"] + counts["partial"]) / classified * 100)
        if classified >= _MIN_CLASSIFIED
        else None
    )

    resp = StatisticsResponse(
        sample_size=len(candidates),
        classified=classified,
        plaintiff_win_rate=win_rate,
        outcomes=OutcomeCounts(**counts),
        disclaimer=DISCLAIMER,
    )
    _cache[cache_key] = (now, resp)
    return resp
