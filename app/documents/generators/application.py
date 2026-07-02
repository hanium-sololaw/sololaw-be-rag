"""신청서(application) 생성기."""

from collections.abc import AsyncIterator

from app.documents.generators.base import BaseGenerator
from app.documents.schemas.common import DocumentType


class ApplicationGenerator(BaseGenerator):
    doc_type = DocumentType.APPLICATION

    async def generate_stream(self, inputs: dict) -> AsyncIterator[str]:
        # TODO: 신청서 스트리밍 생성 구현
        raise NotImplementedError("신청서 생성 미구현")
        yield  # async generator 표식 (도달하지 않음)
