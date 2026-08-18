"""신청서(application) 생성기 — OpenAI 스트리밍."""

from collections.abc import AsyncIterator

from app.core.config import settings
from app.documents.generators.base import BaseGenerator
from app.documents.prompts import application as prompt
from app.documents.schemas.application import ApplicationInput
from app.shared.llm import get_openai_client


class ApplicationGenerator(BaseGenerator):
    # 섹션 구성이 신청서 종류마다 달라 고정 맵을 두지 않는다.
    # None 이면 service 가 마크다운 헤더를 그대로 키로 써서 파싱한다.
    section_map = None

    async def generate_stream(self, inputs: dict) -> AsyncIterator[str]:
        data = ApplicationInput(
            **inputs
        )  # dict → 타입 검증 (라우터에서 이미 검증되지만 방어)
        stream = await get_openai_client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            stream=True,
            messages=[
                {
                    "role": "system",
                    "content": prompt.build_system_prompt(data.application_type),
                },
                {"role": "user", "content": prompt.build_user_prompt(data)},
            ],
        )
        async for chunk in stream:
            if chunk.choices and (delta := chunk.choices[0].delta.content):
                yield delta
