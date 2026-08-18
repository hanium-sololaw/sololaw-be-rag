"""판례 검색 API 라우터."""

from typing import Annotated

from fastapi import APIRouter, Body, HTTPException

from app.cases import service
from app.cases.client import LawApiError
from app.cases.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/cases", tags=["cases"])

# 탭마다 보내는 필드가 달라 예시를 나눠 둔다 (Swagger 의 Examples 드롭다운).
_SEARCH_EXAMPLES = {
    "keyword": {
        "summary": "키워드로 판례 검색 탭",
        "description": "사용자가 입력한 검색어로 찾는다. case_context 는 보내지 않는다.",
        "value": {
            "query": "임대차 보증금 반환 거부",
            "category": "lease",
            "limit": 10,
        },
    },
    "case_context": {
        "summary": "내 사건과 비슷한 판례 탭",
        "description": "사건 설명만 보내면 AI 가 검색 키워드를 뽑는다. query 는 보내지 않는다.",
        "value": {
            "case_context": "임대차 계약이 끝났는데 임대인이 보증금 1,000만원 "
            "반환을 거부하고 있는 사건",
            "category": "lease",
            "limit": 10,
        },
    },
}


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
    "| limit | 동일 — 선택 | 동일 — 선택 |\n"
    "| sample_size | 동일 — 선택, 기본 30 | 동일 — 선택, 기본 30 |\n\n"
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
    "실제 판례 인용 조문). **title** 은 국가법령정보센터에서 조회한 조문 제목으로 "
    "`민법 제618조 (임대차의 의의)` 형태로 표시하면 되고, 조회 실패 시 null 이라 "
    "조문 번호만 쓰면 된다\n"
    "- 후보는 하이브리드로 확보 — law.go.kr 키워드 검색 + 판례 임베딩 코퍼스 유사도 "
    "검색, 벡터 저장소 미가용 시 키워드만으로 자동 폴백\n"
    "- **null 이 올 수 있는 값**: `similarity`(키워드로만 찾은 판례), "
    "`statutes[].title`(조문 제목 조회 실패). 아래 예시에는 값이 있는 경우만 담았지만 "
    "키 자체는 항상 내려간다\n"
    "- 대여금·임대차 필터는 후보를 좁히므로 **결과가 0건일 수 있다** — 빈 결과 처리 필요\n\n"
    "**statistics — 유사 판례 승소율 통계**\n\n"
    "화면 우측 `유사 판례 통계` 패널용이다. 검색과 **동시에 계산해 한 응답에 함께** "
    "내려주므로 따로 호출하지 않는다. 산출에 실패하면 `statistics` 만 null 이고 "
    "카드·법령은 정상 반환된다.\n\n"
    "- **plaintiff_win_rate**: 판단 가능 건 중 원고 승소·일부 승소 %. "
    "판단 가능 건 5건 미만이면 null — 소표본 왜곡 방지. "
    "민사는 일부 인용이 다수라 **일부 승소도 승소로 센다**\n"
    "- **classified**: 승패 판단 가능 건수 — 파기환송 등 판단 불가는 비율에서 제외\n"
    "- **outcomes**: 승패 분포 (win·partial·lose·unknown)\n"
    "- **disclaimer**: 면책 문구 — 프론트에서 반드시 함께 표시\n"
    "- 카드(`limit` 건)와 통계 표본(`sample_size` 건)은 별개다. 화면에 뜨는 건수가 "
    "서로 달라도 정상이다\n"
    "- 전국 통계가 아닌 검색 표본 기반 참고 지표다. 동일 조건 재조회는 1시간 캐시\n\n"
    "AI 호출이 여러 번 일어나 응답에 10초 안팎이 걸린다. 로딩 상태가 필요하다.",
)
async def search(
    req: Annotated[SearchRequest, Body(openapi_examples=_SEARCH_EXAMPLES)],
):
    try:
        return await service.search_cases(req)
    except LawApiError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
