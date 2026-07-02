"""문서 생성 API 라우터.

유형별로 엔드포인트를 나누되(입력 타입 명확), 생성 로직은 service 의 공용
스트리밍 파이프라인을 공유한다. 응답은 SSE(text/event-stream).
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.documents import service
from app.documents.schemas.application import ApplicationInput
from app.documents.schemas.brief import BriefInput
from app.documents.schemas.common import DocumentType, DocumentTypeInfo
from app.documents.schemas.complaint import ComplaintInput
from app.documents.schemas.evidence_list import EvidenceListInput

router = APIRouter(prefix="/documents", tags=["documents"])

SSE_MEDIA = "text/event-stream"


@router.get("/types", response_model=list[DocumentTypeInfo])
def get_document_types():
    """작성 가능한 문서 유형 목록 (step1: 문서 선택)."""
    return service.list_document_types()


@router.post("/complaint/generate")
async def generate_complaint(req: ComplaintInput):
    """소장 생성 (SSE 스트리밍)."""
    return StreamingResponse(
        service.stream_document(DocumentType.COMPLAINT, req.model_dump()),
        media_type=SSE_MEDIA,
    )


@router.post("/brief/generate")
async def generate_brief(req: BriefInput):
    """준비서면 생성 (SSE 스트리밍)."""
    return StreamingResponse(
        service.stream_document(DocumentType.BRIEF, req.model_dump()),
        media_type=SSE_MEDIA,
    )


@router.post("/evidence-list/generate")
async def generate_evidence_list(req: EvidenceListInput):
    """증거목록 생성 (SSE 스트리밍)."""
    return StreamingResponse(
        service.stream_document(DocumentType.EVIDENCE_LIST, req.model_dump()),
        media_type=SSE_MEDIA,
    )


@router.post("/application/generate")
async def generate_application(req: ApplicationInput):
    """신청서 생성 (SSE 스트리밍)."""
    return StreamingResponse(
        service.stream_document(DocumentType.APPLICATION, req.model_dump()),
        media_type=SSE_MEDIA,
    )
