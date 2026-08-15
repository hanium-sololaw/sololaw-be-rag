"""문서 유형 → 생성기 매핑.

새 문서 유형 추가 시 여기 한 줄만 등록하면 router/service 는 그대로 동작한다.
"""

from app.documents.generators.application import ApplicationGenerator
from app.documents.generators.base import BaseGenerator
from app.documents.generators.brief import BriefGenerator
from app.documents.generators.complaint import ComplaintGenerator
from app.documents.generators.evidence_list import EvidenceListGenerator
from app.documents.schemas.common import DocumentType

GENERATORS: dict[DocumentType, BaseGenerator] = {
    DocumentType.COMPLAINT: ComplaintGenerator(),
    DocumentType.BRIEF: BriefGenerator(),
    DocumentType.EVIDENCE_LIST: EvidenceListGenerator(),
    DocumentType.APPLICATION: ApplicationGenerator(),
}
