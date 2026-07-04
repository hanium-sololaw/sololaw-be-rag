"""판례 검색 API 라우터."""

from fastapi import APIRouter, HTTPException

from app.cases import service
from app.cases.client import LawApiError
from app.cases.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="판례 검색",
    description="국가법령정보센터에서 판례를 검색하고 AI 가 사건 맥락 대비 관련도와 "
    "참고 포인트를 산출한다.\n\n"
    "**탭별 입력 방법 — query 또는 case_context 중 하나는 필수**\n\n"
    "| 필드 | 내 사건 기반 탭 | 키워드 검색 탭 |\n"
    "|---|---|---|\n"
    "| query | 보내지 않음 | 사용자가 입력한 키워드 |\n"
    "| case_context | 사건 설명 — AI 가 검색 키워드 추출 | 보내지 않음 |\n"
    "| category | 사건 유형으로 프론트가 자동 지정 | 사용자가 필터에서 선택 |\n"
    "| limit | 동일 — 선택 | 동일 — 선택 |\n\n"
    "둘을 같이 보내면 query 로 검색하고 관련도는 case_context 기준으로 채점한다.\n\n"
    "**category 관련 설명**\n\n"
    " civil=민사\n\n"
    "criminal=형사 \n\n"
    "administrative=행정 \n\n"
    "family=가사 \n\n"
    "빈값=전체 \n\n"
    ""
    "**응답**\n\n"
    "- **cases**: 관련도 내림차순 판례 카드 — 관련도 0~100, 참고할 수 있는 내용 요약, "
    "원문보기 링크\n"
    "- **statutes**: 관련 법령 — 검색된 판례들의 참조조문 집계 (AI 생성 아님, "
    "실제 판례 인용 조문)\n"
    "- limit 만큼 AI 분석하므로 응답에 수 초 소요",
)
async def search(req: SearchRequest):
    try:
        return await service.search_cases(req)
    except LawApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
