"""문서 생성 도메인 공통 스키마 (유형 무관)."""

from enum import Enum

from pydantic import BaseModel


class DocumentType(str, Enum):
    """작성 가능한 문서 유형."""

    COMPLAINT = "complaint"  # 소장
    BRIEF = "brief"  # 준비서면
    EVIDENCE_LIST = "evidence_list"  # 증거목록
    APPLICATION = "application"  # 신청서


class DocumentTypeInfo(BaseModel):
    """문서 유형 카드 메타 (step1: 문서 선택)."""

    type: DocumentType
    name: str
    description: str


# --- SSE 스트리밍 이벤트 프로토콜 ---
# 생성 흐름: delta(조각) * N  →  done(구조화 최종본) / error
class DeltaEvent(BaseModel):
    """생성 중 텍스트 조각."""

    text: str


class DoneEvent(BaseModel):
    """생성 완료 — 구조화된 최종 섹션."""

    # TODO: 유형별 ~Sections 로 구체화 (지금은 자유 형식)
    sections: dict


class ErrorEvent(BaseModel):
    """생성 실패."""

    message: str
