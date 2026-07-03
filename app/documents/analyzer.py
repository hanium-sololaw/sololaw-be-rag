"""증거 파일 분석 오케스트레이션.

파일 내용 추출(shared/extract) → LLM 분류(structured output) → 결과 조립.
generate 파이프라인(service/registry)과 독립된 흐름이며, 파일은 저장하지 않는다.
"""

import asyncio
import logging

from fastapi import UploadFile

from app.core.config import settings
from app.documents.prompts import evidence_analyze as prompt
from app.documents.schemas.evidence_list import (
    AnalyzedEvidence,
    AnalyzeResponse,
    EvidenceDraft,
    EvidenceItem,
)
from app.shared.extract import ExtractError, extract_content
from app.shared.llm import get_openai_client

logger = logging.getLogger(__name__)

MAX_FILES = 10  # 요청당 파일 수 제한
_CONCURRENCY = 5  # 동시 LLM 호출 제한


async def analyze_files(
    files: list[UploadFile], case_context: str | None
) -> AnalyzeResponse:
    """파일별로 병렬 분석한다. 일부 실패해도 나머지는 정상 반환 (부분 실패 허용)."""
    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _bounded(file: UploadFile) -> AnalyzedEvidence:
        async with semaphore:
            return await _analyze_one(file, case_context)

    results = await asyncio.gather(*(_bounded(f) for f in files))
    return AnalyzeResponse(items=list(results))


async def _analyze_one(file: UploadFile, case_context: str | None) -> AnalyzedEvidence:
    filename = file.filename or "이름 없는 파일"

    try:
        data = await file.read()
        extracted = extract_content(filename, file.content_type, data)
    except ExtractError as e:
        return AnalyzedEvidence(filename=filename, success=False, error=str(e))

    try:
        completion = await get_openai_client().chat.completions.parse(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": prompt.SYSTEM},
                {
                    "role": "user",
                    "content": prompt.build_user_content(
                        filename, extracted, case_context
                    ),
                },
            ],
            response_format=EvidenceDraft,
        )
        draft = completion.choices[0].message.parsed
        if draft is None:
            return AnalyzedEvidence(
                filename=filename,
                success=False,
                error="분류 결과를 해석하지 못했습니다.",
            )
        return AnalyzedEvidence(
            filename=filename,
            success=True,
            item=EvidenceItem(name=draft.name, date=draft.date, purpose=draft.purpose),
        )
    except Exception:
        logger.exception("증거 파일 분석 실패 (file=%s)", filename)
        return AnalyzedEvidence(
            filename=filename, success=False, error="AI 분석 중 오류가 발생했습니다."
        )
