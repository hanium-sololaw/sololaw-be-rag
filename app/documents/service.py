"""문서 생성 공용 유틸 — 유형 목록·SSE 포맷·섹션 파싱.

생성 흐름(Multi-Agent 그래프)은 app/agent/document_graph.py 에 있다.
"""

import json
import re

from app.documents.schemas.common import DocumentType, DocumentTypeInfo

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


def sse(event: str, data: dict) -> str:
    """SSE 한 이벤트를 문자열로 포맷."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


_HEADER_RE = re.compile(r"^##\s*(.+?)\s*$")


def parse_sections(text: str, section_map: dict[str, str] | None) -> dict[str, str]:
    """생성 텍스트를 '## 헤더' 기준으로 잘라 {필드명: 본문} 으로 변환.

    section_map 이 None 이면 헤더 이름을 그대로 키로 쓴다 (신청서처럼 종류마다
    섹션이 다른 경우). 이때 키 순서는 문서에 나온 순서와 같다.
    """
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            if current:
                sections[current] = "\n".join(buf).strip()
            header = m.group(1)
            current = header if section_map is None else section_map.get(header)
            buf = []
        elif current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    return sections
