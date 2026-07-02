"""증거목록(evidence_list) 생성기."""

from collections.abc import AsyncIterator

from app.documents.generators.base import BaseGenerator
from app.documents.schemas.common import DocumentType


class EvidenceListGenerator(BaseGenerator):
    doc_type = DocumentType.EVIDENCE_LIST

    async def generate_stream(self, inputs: dict) -> AsyncIterator[str]:
        # TODO: 증거목록 스트리밍 생성 구현
        raise NotImplementedError("증거목록 생성 미구현")
        yield  # async generator 표식 (도달하지 않음)
