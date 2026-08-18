"""국가법령정보센터 Open API 클라이언트.

- 판례 목록 검색: /DRF/lawSearch.do?target=prec
- 판례 본문 조회: /DRF/lawService.do?target=prec
인증은 OC 파라미터(발급 이메일 ID). 응답의 목록 키는 단건이면 dict,
여러 건이면 list 로 내려와 정규화가 필요하다.
"""

import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://www.law.go.kr/DRF"
_TIMEOUT = 10.0

# 조문 제목은 거의 바뀌지 않으므로 프로세스 메모리에 캐시한다 (재시작 시 초기화).
_mst_cache: dict[str, str | None] = {}
_title_cache: dict[tuple[str, str], str | None] = {}

_TAG_RE = re.compile(r"<[^>]+>")

# 판례 전문에서 주문 섹션 발췌 ("주 문 ... 이 유" 구조)
_ORDER_RE = re.compile(r"주\s*문(.*?)(?:이\s*유|청\s*구\s*취\s*지|$)", re.DOTALL)


class LawApiError(Exception):
    """국가법령정보센터 API 호출 실패."""


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _extract_order(content: str) -> str:
    """판례 전문에서 주문 부분을 발췌한다 (승패 판정의 최우선 근거)."""
    cleaned = content.replace("【", " ").replace("】", " ")
    m = _ORDER_RE.search(cleaned)
    return m.group(1).strip()[:300] if m else ""


def _ensure_key() -> str:
    if not settings.LAW_API_KEY:
        raise LawApiError("LAW_API_KEY 가 설정되지 않았습니다.")
    return settings.LAW_API_KEY


def _headers() -> dict:
    # law.go.kr 은 Open API 신청 시 등록한 도메인을 Referer 로 검증한다.
    # 누락 시 "필수 입력값" 오류로 위장된 거부 응답이 온다.
    return {"Referer": settings.LAW_API_REFERER}


def _as_list(value) -> list[dict]:
    """단건 dict / 다건 list 응답을 list 로 정규화."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return list(value)


async def search_precedents(
    client: httpx.AsyncClient, query: str, display: int = 20, page: int = 1
) -> tuple[int, list[dict]]:
    """판례 목록 검색. (전체 건수, 목록) 반환."""
    params = {
        "OC": _ensure_key(),
        "target": "prec",
        "type": "JSON",
        "query": query,
        "display": display,
        "page": page,
        "search": 2,  # 본문 검색 (1=판례명)
    }
    try:
        res = await client.get(
            f"{_BASE}/lawSearch.do",
            params=params,
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        raise LawApiError("판례 검색 API 호출에 실패했습니다.") from e

    body = data.get("PrecSearch")
    if body is None:
        # 인증 실패 등은 JSON 이 아닌 에러 페이지 또는 다른 구조로 내려온다
        raise LawApiError(
            "판례 검색 API 응답을 해석할 수 없습니다. 인증키를 확인하세요."
        )
    total = int(body.get("totalCnt", 0))
    return total, _as_list(body.get("prec"))


async def fetch_precedent_detail(client: httpx.AsyncClient, serial_id: str) -> dict:
    """판례 본문 조회 — 판시사항·판결요지·참조조문 등."""
    params = {
        "OC": _ensure_key(),
        "target": "prec",
        "type": "JSON",
        "ID": serial_id,
    }
    try:
        res = await client.get(
            f"{_BASE}/lawService.do",
            params=params,
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        raise LawApiError("판례 본문 API 호출에 실패했습니다.") from e

    body = data.get("PrecService")
    if body is None:
        raise LawApiError("판례 본문 API 응답을 해석할 수 없습니다.")
    return {
        "판시사항": _strip_html(body.get("판시사항") or ""),
        "판결요지": _strip_html(body.get("판결요지") or ""),
        "참조조문": _strip_html(body.get("참조조문") or ""),
        "주문": _extract_order(_strip_html(body.get("판례내용") or "")),
    }


async def _law_mst(client: httpx.AsyncClient, law_name: str) -> str | None:
    """법령명으로 법령일련번호(MST)를 찾는다 — 부분 일치가 섞이므로 정확 일치만."""
    if law_name in _mst_cache:
        return _mst_cache[law_name]
    res = await client.get(
        f"{_BASE}/lawSearch.do",
        params={
            "OC": _ensure_key(),
            "target": "law",
            "type": "JSON",
            "query": law_name,
            "display": 50,
        },
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    res.raise_for_status()
    found = None
    for law in _as_list(res.json().get("LawSearch", {}).get("law")):
        if law.get("법령명한글") == law_name:
            found = law.get("법령일련번호")
            break
    _mst_cache[law_name] = found
    return found


async def fetch_statute_title(
    client: httpx.AsyncClient, law_name: str, jo: str, ui: str = ""
) -> str | None:
    """조문 제목을 조회한다 (예: 민법 제618조 → "임대차의 의의").

    JO 파라미터는 조 4자리 + 가지번호 2자리다 (제618조=061800, 제3조의2=000302).
    조문 제목은 거의 바뀌지 않으므로 프로세스 메모리에 캐시한다.
    실패하면 None — 조문 번호만 표시하고 넘어간다.
    """
    branch = re.sub(r"\D", "", ui or "") or "0"
    code = f"{int(jo):04d}{int(branch):02d}"
    cache_key = (law_name, code)
    if cache_key in _title_cache:
        return _title_cache[cache_key]

    title = None
    try:
        mst = await _law_mst(client, law_name)
        if mst:
            res = await client.get(
                f"{_BASE}/lawService.do",
                params={
                    "OC": _ensure_key(),
                    "target": "law",
                    "type": "JSON",
                    "MST": mst,
                    "JO": code,
                },
                headers=_headers(),
                timeout=_TIMEOUT,
            )
            res.raise_for_status()
            units = _as_list(res.json().get("법령", {}).get("조문", {}).get("조문단위"))
            # 같은 조문번호로 절 제목 등이 함께 오므로 조문제목이 있는 항목만 쓴다
            titles = [u.get("조문제목") for u in units if u.get("조문제목")]
            title = titles[0] if titles else None
    except Exception:
        logger.warning("조문 제목 조회 실패 (%s 제%s조)", law_name, jo, exc_info=True)

    _title_cache[cache_key] = title
    return title


def public_detail_url(serial_id: str) -> str:
    """프론트 원문보기용 공개 링크 (OC 미노출)."""
    return f"https://www.law.go.kr/LSW/precInfoP.do?precSeq={serial_id}"
