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
    description="입력 정보(법원·소송유형·당사자·청구원인 등)를 법원 제출용 소장으로 변환한다.\n\n"
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
    description="신청서 종류(기일변경·문서송부촉탁·보정서·소송구조)와 사건·당사자 정보, "
    "신청 사유를 법원 제출용 신청서로 변환한다.\n\n"
    "**done** 이벤트의 **sections** 는 제목, 사건, 신청취지, 신청이유, 첨부서류, "
    "관할법원 6개 필드 (**ApplicationSections**).\n\n\n"
    "**신청서 종류**\n\n"
    "hearing_date_change=기일변경신청서\n\n"
    "document_transmission=문서송부촉탁신청서\n\n"
    "correction=보정서/보정신청서\n\n "
    "litigation_aid=소송구조신청서\n\n" + _SSE_DOC,
)
async def generate_application(req: ApplicationInput):
    return StreamingResponse(
        service.stream_document(DocumentType.APPLICATION, req.model_dump()),
        media_type=SSE_MEDIA,
    )
