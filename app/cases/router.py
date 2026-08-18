"""판례 검색 API 라우터."""

from fastapi import APIRouter, HTTPException

from app.cases import service, statistics
from app.cases.client import LawApiError
from app.cases.schemas import (
    SearchRequest,
    SearchResponse,
    StatisticsRequest,
    StatisticsResponse,
)

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
    "화면의 필터 칩과 1:1 대응한다.\n\n"
    "civil=민사 \n\n"
    "loan=대여금 \n\n"
    "lease=임대차 \n\n"
    "빈값=전체 \n\n"
    "대여금·임대차는 사건종류명이 아니라 민사 안의 주제이므로 "
    "사건명 키워드로 한 번 더 좁힌다. 그만큼 후보가 줄어 결과 건수가 적을 수 있다.\n\n"
    "**응답**\n\n"
    "- **cases**: 관련도 내림차순 판례 카드 — 관련도 0~100, 참고할 수 있는 내용 요약, "
    "원문보기 링크\n"
    "- **outcome**: 그 판례에서 원고가 이겼는지 — 카드의 결과 배지용. "
    "win=원고 승소, partial=원고 일부승소, lose=원고 패소, "
    "unknown=판단 불가. unknown 은 배지를 표시하지 않는다. "
    "주문을 근거로 판정하므로 주문을 얻지 못한 판례는 unknown 이 된다\n"
    "- **similarity**: 판례 임베딩 유사도 % — 벡터 검색 후보에만 제공, "
    "'내 사건과 유사한 판례 N%' 게이지용\n"
    "- **statutes**: 관련 법령 — 검색된 판례들의 참조조문 집계 (AI 생성 아님, "
    "실제 판례 인용 조문)\n"
    "- 후보는 하이브리드로 확보 — law.go.kr 키워드 검색 + 판례 임베딩 코퍼스 유사도 "
    "검색, 벡터 저장소 미가용 시 키워드만으로 자동 폴백\n"
    "- limit 만큼 AI 분석하므로 응답에 수 초 소요",
)
async def search(req: SearchRequest):
    try:
        return await service.search_cases(req)
    except LawApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post(
    "/statistics",
    response_model=StatisticsResponse,
    summary="유사 판례 승소율 통계",
    description="검색 표본(최근 공개 판례 최대 50건)의 승패를 AI 가 분류해 원고 승소 "
    "비율을 산출한다.\n\n"
    "**탭별 입력 방법 — 판례 검색과 동일 규칙, query 또는 case_context 중 하나는 필수**\n\n"
    "| 필드 | 내 사건 기반 탭 | 키워드 검색 탭 |\n"
    "|---|---|---|\n"
    "| query | 보내지 않음 | 사용자가 입력한 키워드 |\n"
    "| case_context | 사건 설명 — AI 가 검색 키워드 추출 | 보내지 않음 |\n"
    "| category | 사건 유형으로 프론트가 자동 지정 | 사용자가 필터에서 선택 |\n"
    "| sample_size | 동일 — 선택, 기본 30 | 동일 — 선택, 기본 30 |\n\n"
    "**응답**\n\n"
    "- **sample_size**: 분석한 표본 수\n"
    "- **classified**: 승패 판단 가능 건수 — 파기환송 등 판단 불가는 비율에서 제외\n"
    "- **plaintiff_win_rate**: 판단 가능 건 중 원고 승소·일부 승소 %. "
    "판단 가능 건 5건 미만이면 null — 소표본 왜곡 방지\n"
    "- **outcomes**: 승패 분포 (win·partial·lose·unknown)\n"
    "- **disclaimer**: 면책 문구 — 프론트에서 반드시 함께 표시\n\n"
    "전국 통계가 아닌 검색 표본 기반 참고 지표이다. 동일 조건 재조회는 1시간 캐시로 "
    "즉시 응답, 첫 호출은 5~10초 소요.",
)
async def get_statistics(req: StatisticsRequest):
    try:
        return await statistics.get_statistics(req)
    except LawApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
