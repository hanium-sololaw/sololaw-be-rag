"""문서 생성 API 라우터.

유형별로 엔드포인트를 나누되(입력 타입 명확), 생성 로직은 service 의 공용
스트리밍 파이프라인을 공유한다. 응답은 SSE(text/event-stream).
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.documents import analyzer, service
from app.documents.schemas.application import ApplicationInput
from app.documents.schemas.brief import BriefInput
from app.documents.schemas.common import DocumentType, DocumentTypeInfo
from app.documents.schemas.complaint import ComplaintInput
from app.documents.schemas.evidence_list import AnalyzeResponse, EvidenceListInput

router = APIRouter(prefix="/documents", tags=["documents"])

SSE_MEDIA = "text/event-stream"

# 생성 엔드포인트 공통 응답 설명
_SSE_DOC = """
---

**생성 엔드포인트 관련 공동 응답 설명**

스트리밍 응답 — 발생 이벤트(event):

1. **delta** — 생성 중 보이는 실시간 스트리밍 문자. **data: {"text": "..."}**
2. **done** — 생성 완료. **data: {"sections": {섹션별 구조화}, "raw_text": "전체 원문"}**
3. **error** — 실패 시. **data: {"message": "..."}**
"""


@router.get(
    "/types",
    response_model=list[DocumentTypeInfo],
    summary="문서 유형 목록",
    description="작성 가능한 문서 유형 카드 목록 (step1: 문서 선택).",
)
def get_document_types():
    return service.list_document_types()


@router.post(
    "/complaint/generate",
    summary="소장 자동 생성",
    response_description="SSE 스트림 (delta*N → done)",
    description="정보입력 위저드 1~6단계 결과를 한 번에 받아 법원 제출용 소장으로 변환한다.\n\n"
    "**소송 유형 5종** (`lawsuit_type`) — `deposit_return`(임대차보증금 반환), "
    "`loan_return`(대여금 반환), `wage_claim`(임금체불 청구), `damages`(손해배상), "
    "`building_surrender`(건물명도). 건물명도만 청구취지 1항이 금전 지급이 아니라 "
    "**건물 인도**로 작성되고, 미납 차임이 있으면 2항의 금전 청구로 이어진다.\n\n"
    "**단계별 대응 필드**\n"
    "- 1단계(어느 법원에 얼마) → `court` · `claim_type` · `valuation_type` · "
    "`claim_amount` · `object_value`\n"
    "- 2단계(누가 누구에게) → `plaintiffs` · `defendants`. 법인 대표자·법정대리인은 "
    "`representative`, 송달 주소·팩스는 `service_address` · `fax`\n"
    "- 3~4단계(유형별 사실관계) → `facts` 에 `{화면 항목: 답}` 을 그대로 담는다. "
    "소송 유형마다 항목이 달라 스키마를 고정하지 않는다. 자유서술은 `cause_text`\n"
    "- 5단계(요구·독촉) → `partial_repaid` · `demand_method` · `demand_date` · "
    "`response_text`. `demand_date`(최고일)는 지연손해금 기산일 판단에 쓰인다\n"
    "- 6단계(가지고 있는 자료) → `attachments` 라벨 목록이 입증방법(갑 호증)이 된다. "
    "파일 업로드는 `POST /documents/evidence/analyze` 별도 호출\n\n"
    "인지대·송달료 계산은 본 서버 범위 밖(스프링 담당)이며, 주민등록번호는 LLM 에 "
    "전달되지 않는다.\n\n"
    "**done** 이벤트의 **sections** 는 사건명, 소송목적의 값, 당사자, 청구취지, 청구원인, "
    "입증방법, 첨부서류, 관할법원 8개 필드 (**ComplaintSections**).\n" + _SSE_DOC,
)
async def generate_complaint(req: ComplaintInput):
    return StreamingResponse(
        service.stream_document(DocumentType.COMPLAINT, req.model_dump()),
        media_type=SSE_MEDIA,
    )


@router.post(
    "/brief/generate",
    summary="준비서면 자동 생성",
    response_description="SSE 스트림 (delta*N → done)",
    description="사건 정보와 반박할 상대방 주장, 내 주장·새로운 증거, 인용 판례를 "
    "법원 제출용 준비서면으로 변환한다.\n\n"
    "**done** 이벤트의 **sections** 는 사건, 상대방 주장의 요지, 반박, 결론, "
    "입증방법, 관할법원 6개 필드 (**BriefSections**).\n" + _SSE_DOC,
)
async def generate_brief(req: BriefInput):
    return StreamingResponse(
        service.stream_document(DocumentType.BRIEF, req.model_dump()),
        media_type=SSE_MEDIA,
    )


@router.post(
    "/evidence-list/generate",
    summary="증거목록 자동 생성",
    response_description="SSE 스트림 (delta*N → done)",
    description="사건 정보와 증거 목록을 법원 제출용 증거목록으로 변환한다. "
    "호증 번호는 evidence_items 리스트 순서대로 서버가 확정하고 — 제출자 지위에 따라 "
    "갑·을·병 접두어 — AI 는 비어 있는 입증취지 제안과 표 정리만 담당한다.\n\n"
    "**done** 이벤트의 **sections** 는 제목, 사건, 증거목록, 비고, 관할법원 "
    "5개 필드 (**EvidenceListSections**).\n" + _SSE_DOC,
)
async def generate_evidence_list(req: EvidenceListInput):
    return StreamingResponse(
        service.stream_document(DocumentType.EVIDENCE_LIST, req.model_dump()),
        media_type=SSE_MEDIA,
    )


@router.post(
    "/evidence-list/analyze",
    response_model=AnalyzeResponse,
    summary="증거 파일 자동 분석",
    description="업로드한 증거 파일을 AI 가 읽고 서증명·작성일·입증취지를 분류해 "
    "EvidenceItem 리스트로 반환한다. 사용자가 결과를 확인·정렬한 뒤 "
    "evidence-list/generate 의 evidence_items 로 전달하는 흐름.\n\n"
    "- 지원 형식: PDF, JPG, PNG, TXT — 카카오톡 내보내기 등\n"
    "- 제한: 파일당 10MB, 요청당 최대 10개\n"
    "- 텍스트 없는 스캔본 PDF 미지원 — 해당 파일만 success=false 로 반환\n"
    "- 일부 파일이 실패해도 나머지는 정상 분석 (부분 실패 허용)\n"
    "- 파일은 저장하지 않고 분석 후 폐기",
)
async def analyze_evidence(
    files: list[UploadFile] = File(..., description="증거 파일들"),
    case_context: str | None = Form(
        None,
        description="사건 맥락 — 입증취지 제안 정확도 향상 (예: 임대차 보증금 반환 사건)",
    ),
):
    if len(files) > analyzer.MAX_FILES:
        raise HTTPException(
            status_code=422,
            detail=f"파일은 최대 {analyzer.MAX_FILES}개까지 업로드할 수 있습니다.",
        )
    return await analyzer.analyze_files(files, case_context)


@router.post(
    "/application/generate",
    summary="신청서 자동 생성",
    response_description="SSE 스트림 (delta*N → done)",
    description="신청서 종류별 입력을 법원 제출용 신청서로 변환한다. 신청서는 사건 "
    "유형이 아니라 **절차적 목적**으로 갈린다.\n\n"
    "**신청서 종류 5종** (`application_type`)\n\n"
    "| 값 | 문서 | 언제 쓰나 |\n"
    "|---|---|---|\n"
    "| `payment_order` | 지급명령신청서 | 다툼 적은 금전채권을 빠르게 회수 |\n"
    "| `litigation_aid` | 소송구조신청서 | 소송비용 낼 형편이 안 될 때 |\n"
    "| `lease_registration` | 임차권등기명령신청서 | 보증금 못 받고 이사해야 할 때 |\n"
    "| `enforcement` | 강제집행신청서 | 판결 후 상대가 이행하지 않을 때 |\n"
    "| `provisional_seizure` | 가압류신청서 | 소송 전·중에 재산을 묶을 때 |\n\n"
    "**⚠️ sections 키가 종류마다 다르다**\n\n"
    "완성 문서의 구성이 신청서마다 달라 `sections` 는 고정 필드가 아니라 "
    "**문서에 나온 헤더 이름을 키로** 내려간다. dict 순서가 곧 문서 순서이므로 "
    "프론트는 키를 미리 알 필요 없이 순서대로 렌더링하면 된다.\n\n"
    "```\n"
    "지급명령   → 당사자 · 청구 종류 · 신청취지 · 신청이유\n"
    "소송구조   → 사건 · 당사자 · 신청취지 · 신청이유\n"
    "임차권등기 → 당사자 · 신청취지 · 신청이유 · 관련 법리 · 첨부서류 · 별지\n"
    "강제집행   → 당사자 · 집행권원 · 집행목적물 · 청구금액 · 신청취지\n"
    "가압류     → 당사자 · 청구채권의 표시 · 가압류할 목적물의 표시 · 신청취지 · "
    "신청이유 · 가압류신청 진술서\n"
    "```\n\n"
    "- **별개의 서면**: 임차권등기명령의 `별지`, 가압류의 `가압류신청 진술서` 는 "
    "신청서 본문과 따로 제출하는 서면이다. 화면에서도 구분선 아래에 렌더링한다\n"
    "- **강제집행에는 신청이유가 없다**\n"
    "- **관련 법리**는 임차권등기명령에만 있고 `cited_precedents` 가 반영된다\n\n"
    "**입력 규칙**\n\n"
    "- `facts` 에 종류별 구조화 입력을 `{화면 항목: 답}` 으로 담는다. 신청서마다 "
    "묻는 항목이 달라 스키마를 고정하지 않는다\n"
    "- `respondent` 는 소송구조신청서만 생략 가능하다. 나머지는 필수\n"
    "- 주민등록번호는 LLM 에 전달되지 않는다. 표시·마스킹은 프론트가 처리한다\n"
    "- 날짜·서명란·`○○법원 귀중` 은 생성하지 않는다. 프론트가 렌더링한다\n"
    "- 인지대 계산은 본 서버 범위 밖이다 (지급명령은 소장의 1/10)\n" + _SSE_DOC,
)
async def generate_application(req: ApplicationInput):
    return StreamingResponse(
        service.stream_document(DocumentType.APPLICATION, req.model_dump()),
        media_type=SSE_MEDIA,
    )
