"""소장(complaint) 생성기 — OpenAI 스트리밍."""

from collections.abc import AsyncIterator

from app.core.config import settings
from app.documents.generators.base import BaseGenerator
from app.documents.prompts import complaint as prompt
from app.documents.schemas.common import DocumentType
from app.documents.schemas.complaint import ComplaintInput
from app.shared.llm import get_openai_client


class ComplaintGenerator(BaseGenerator):
    doc_type = DocumentType.COMPLAINT
    section_map = prompt.SECTION_MAP

    async def generate_stream(self, inputs: dict) -> AsyncIterator[str]:
        data = ComplaintInput(
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
