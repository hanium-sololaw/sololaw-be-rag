"""신청서(application) 입력/출력 스키마."""

from pydantic import BaseModel


class ApplicationInput(BaseModel):
    """신청서 - 정보 입력. TODO: 필드 정의."""


class ApplicationSections(BaseModel):
    """신청서 구조화 결과. TODO: 섹션 정의."""
