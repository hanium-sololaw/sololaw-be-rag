"""국가법령정보센터 Open API 클라이언트.

- 판례 목록 검색: /DRF/lawSearch.do?target=prec
- 판례 본문 조회: /DRF/lawService.do?target=prec
인증은 OC 파라미터(발급 이메일 ID). 응답의 목록 키는 단건이면 dict,
여러 건이면 list 로 내려와 정규화가 필요하다.
"""

import re

import httpx

from app.core.config import settings

_BASE = "https://www.law.go.kr/DRF"
_TIMEOUT = 10.0

_TAG_RE = re.compile(r"<[^>]+>")


class LawApiError(Exception):
    """국가법령정보센터 API 호출 실패."""


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


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
    client: httpx.AsyncClient, query: str, display: int = 20
) -> tuple[int, list[dict]]:
    """판례 목록 검색. (전체 건수, 목록) 반환."""
    params = {
        "OC": _ensure_key(),
        "target": "prec",
        "type": "JSON",
        "query": query,
        "display": display,
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
    except LawApiError:
        raise
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
    except LawApiError:
        raise
    except Exception as e:
        raise LawApiError("판례 본문 API 호출에 실패했습니다.") from e

    body = data.get("PrecService")
    if body is None:
        raise LawApiError("판례 본문 API 응답을 해석할 수 없습니다.")
    return {
        "판시사항": _strip_html(body.get("판시사항") or ""),
        "판결요지": _strip_html(body.get("판결요지") or ""),
        "참조조문": _strip_html(body.get("참조조문") or ""),
    }


def public_detail_url(serial_id: str) -> str:
    """프론트 원문보기용 공개 링크 (OC 미노출)."""
    return f"https://www.law.go.kr/LSW/precInfoP.do?precSeq={serial_id}"
