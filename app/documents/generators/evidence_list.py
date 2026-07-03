"""증거목록(evidence_list) 생성기 — OpenAI 스트리밍."""

from collections.abc import AsyncIterator

from app.core.config import settings
from app.documents.generators.base import BaseGenerator
from app.documents.prompts import evidence_list as prompt
from app.documents.schemas.common import DocumentType
from app.documents.schemas.evidence_list import EvidenceListInput
from app.shared.llm import get_openai_client


class EvidenceListGenerator(BaseGenerator):
    doc_type = DocumentType.EVIDENCE_LIST
    section_map = prompt.SECTION_MAP

    async def generate_stream(self, inputs: dict) -> AsyncIterator[str]:
        data = EvidenceListInput(
            **inputs
        )  # dict → 타입 검증 (라우터에서 이미 검증되지만 방어)
        stream = await get_openai_client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            stream=True,
            messages=[
                {"role": "system", "content": prompt.SYSTEM},
                {"role": "user", "content": prompt.build_user_prompt(data)},
            ],
        )
        async for chunk in stream:
            if chunk.choices and (delta := chunk.choices[0].delta.content):
                yield delta
