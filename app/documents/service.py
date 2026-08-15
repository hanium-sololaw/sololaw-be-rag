"""문서 생성 오케스트레이션 + 공용 스트리밍(SSE) 파이프라인.

유형별 라우터는 얇게 두고, 실제 스트리밍 흐름은 여기 한 곳에서 공유한다.
"""

import json
import logging
import re
from collections.abc import AsyncIterator

from app.documents.registry import GENERATORS
from app.documents.schemas.common import DocumentType, DocumentTypeInfo

logger = logging.getLogger(__name__)

# 문서 유형 카드 메타 (step1). TODO: 문구 확정
DOCUMENT_TYPES: list[DocumentTypeInfo] = [
    DocumentTypeInfo(
        type=DocumentType.COMPLAINT,
        name="소장",
        description="소송을 제기하기 위한 기본 문서",
    ),
    DocumentTypeInfo(
        type=DocumentType.BRIEF,
        name="준비서면",
        description="주장과 증거를 정리한 문서",
    ),
    DocumentTypeInfo(
        type=DocumentType.EVIDENCE_LIST,
        name="증거목록",
        description="제출할 증거의 목록",
    ),
    DocumentTypeInfo(
        type=DocumentType.APPLICATION,
        name="신청서",
        description="법원에 제출하는 각종 신청서",
    ),
]


def list_document_types() -> list[DocumentTypeInfo]:
    return DOCUMENT_TYPES


def _sse(event: str, data: dict) -> str:
    """SSE 한 이벤트를 문자열로 포맷."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_HEADER_RE = re.compile(r"^##\s*(.+?)\s*$")


def _parse_sections(text: str, section_map: dict[str, str]) -> dict[str, str]:
    """생성 텍스트를 '## 헤더' 기준으로 잘라 {필드명: 본문} 으로 변환."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            if current:
                sections[current] = "\n".join(buf).strip()
            current = section_map.get(m.group(1))
            buf = []
        elif current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections


async def stream_document(doc_type: DocumentType, inputs: dict) -> AsyncIterator[str]:
    """유형 공용 스트리밍 파이프라인.

    generator 의 델타를 SSE `delta` 이벤트로 흘리고, 완료 시 누적 텍스트를
    section_map 으로 구조화해 `done` 이벤트로, 실패 시 `error` 이벤트로 방출한다.
    done 에는 파싱 실패 대비용 원문(raw_text)도 함께 담는다.
    """
    generator = GENERATORS[doc_type]
    buffer: list[str] = []
    try:
        async for delta in generator.generate_stream(inputs):
            buffer.append(delta)
            yield _sse("delta", {"text": delta})
        full_text = "".join(buffer)
        sections = _parse_sections(full_text, generator.section_map)
        yield _sse("done", {"sections": sections, "raw_text": full_text})
    except NotImplementedError as e:
        yield _sse("error", {"message": str(e)})
    except Exception:
        logger.exception("문서 생성 실패 (type=%s)", doc_type.value)
        yield _sse("error", {"message": "문서 생성 중 오류가 발생했습니다."})
