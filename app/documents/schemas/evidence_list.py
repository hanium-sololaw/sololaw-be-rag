"""증거목록(evidence_list) 입력/출력 스키마."""

from pydantic import BaseModel


class EvidenceListInput(BaseModel):
    """증거목록 - 정보 입력. TODO: 필드 정의."""


class EvidenceListSections(BaseModel):
    """증거목록 구조화 결과. TODO: 섹션 정의."""
