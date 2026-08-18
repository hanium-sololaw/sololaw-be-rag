"""문서 생성 도메인 공통 스키마 (유형 무관)."""

from enum import Enum

from pydantic import BaseModel, Field


class Party(BaseModel):
    """당사자 — 문서 유형에 따라 원고·피고, 채권자·채무자, 신청인·피신청인이 된다.

    호칭은 문서마다 다르지만 담기는 정보는 같아 한 모델을 공유한다.
    """

    name: str = Field(description="이름 또는 상호", examples=["홍길동"])
    resident_id: str | None = Field(
        None,
        description="주민등록번호. **LLM 에는 전달되지 않는다** — 문서 표시·마스킹은 "
        "프론트가 처리한다 (신청서는 기재사항이라 법원 제출본에만 들어간다)",
        examples=["900101-1234567"],
    )
    address: str = Field(
        description="주소 (도로명)", examples=["서울특별시 서초구 서초대로 12"]
    )
    phone: str | None = Field(None, description="연락처", examples=["010-1234-5678"])
    email: str | None = Field(None, description="이메일", examples=["hong@example.com"])
    service_address: str | None = Field(
        None,
        description="송달받을 주소 (주소와 다를 때만)",
        examples=["서울특별시 강남구 테헤란로 1"],
    )
    fax: str | None = Field(None, description="팩스 번호", examples=["02-1234-5678"])
    representative: str | None = Field(
        None,
        description="법인 대표자 또는 미성년자의 법정대리인. 당사자 표시에 병기된다",
        examples=["대표이사 김철수"],
    )


class CitedPrecedent(BaseModel):
    """인용할 판례 (판례 검색에서 담아온 것)."""

    case_no: str = Field(description="사건번호", examples=["대법원 2020다12345"])
    summary: str | None = Field(
        None, description="판례 요지", examples=["임대차 종료 시 보증금 반환 의무"]
    )


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
