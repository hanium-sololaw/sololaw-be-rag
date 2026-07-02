"""신청서(application) 입력/출력 스키마."""

from enum import Enum

from pydantic import BaseModel, Field


class ApplicationType(str, Enum):
    """신청서 종류 (드롭다운)."""

    HEARING_DATE_CHANGE = "hearing_date_change"  # 기일변경신청서
    DOCUMENT_TRANSMISSION = "document_transmission"  # 문서송부촉탁신청서
    CORRECTION = "correction"  # 보정서/보정신청서
    LITIGATION_AID = "litigation_aid"  # 소송구조신청서


class ApplicantRole(str, Enum):
    """신청인이 사건에서 갖는 지위."""

    PLAINTIFF = "plaintiff"  # 원고
    DEFENDANT = "defendant"  # 피고


class ApplicationInput(BaseModel):
    """신청서 - 정보 입력 (step2)."""

    application_type: ApplicationType = Field(
        description="신청서 종류 (hearing_date_change=기일변경신청서, "
        "document_transmission=문서송부촉탁신청서, correction=보정서/보정신청서, "
        "litigation_aid=소송구조신청서)",
        examples=["hearing_date_change"],
    )
    case_no: str = Field(
        description="사건 번호", examples=["2024가단123456 임대차보증금반환"]
    )
    court: str = Field(
        description="사건이 계속 중인 법원", examples=["서울중앙지방법원"]
    )
    plaintiff: str = Field(description="원고 이름", examples=["홍길동"])
    defendant: str = Field(description="피고 이름", examples=["김철수"])
    applicant_role: ApplicantRole = Field(
        default=ApplicantRole.PLAINTIFF,
        description="신청인이 원고/피고 중 누구인지 (기본 원고)",
        examples=["plaintiff"],
    )
    reason_text: str = Field(
        description="신청하는 이유 — 일상 언어로 쓰면 AI가 법률 문언으로 변환",
        examples=[
            "기일 당일 출장이 잡혀서 변론기일을 2주 뒤로 미뤄달라고 신청하려 합니다."
        ],
    )
    related_date: str | None = Field(
        None,
        description="관련 날짜 (변경 대상 기일, 보정명령 수령일 등)",
        examples=["변론기일 2026-07-15"],
    )
    attachments: list[str] = Field(
        default=[],
        description="첨부 서류 라벨 목록 — 첨부서류 섹션 작성에 반영",
        examples=[["출장확인서"]],
    )


class ApplicationSections(BaseModel):
    """신청서 구조화 결과 (스트림 완료 시 파싱). PDF·편집용."""

    title: str = Field("", description="신청서 제목 (예: 기일변경 신청서)")
    case_info: str = Field("", description="사건 표시 (사건번호·원고·피고)")
    purpose: str = Field("", description="신청취지")
    reason: str = Field("", description="신청이유")
    attachments: str = Field("", description="첨부서류")
    court: str = Field("", description="관할법원 (○○법원 귀중)")
