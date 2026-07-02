"""준비서면(brief) 입력/출력 스키마."""

from pydantic import BaseModel


class BriefInput(BaseModel):
    """준비서면 - 정보 입력. TODO: 필드 정의."""


class BriefSections(BaseModel):
    """준비서면 구조화 결과. TODO: 섹션 정의."""
