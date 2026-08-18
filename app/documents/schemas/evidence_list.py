"""증거목록(evidence_list) 입력/출력 스키마."""

from enum import Enum

from pydantic import BaseModel, Field


class SubmitterRole(str, Enum):
    """증거목록 제출자가 사건에서 갖는 지위. 호증 접두어를 결정한다."""

    PLAINTIFF = "plaintiff"  # 원고 → 갑호증
    DEFENDANT = "defendant"  # 피고 → 을호증
    INTERVENOR = "intervenor"  # 참가인 → 병호증


class OriginalType(str, Enum):
    """서식의 「원본」란 — 내는 서증이 원본인지 사본인지.

    서증은 사본으로 내는 것이 원칙이다 (민사소송규칙 제105조 제2항).
    """

    COPY = "copy"  # 사본
    ORIGINAL = "original"  # 원본


class EvidenceItem(BaseModel):
    """증거 한 건. 리스트 순서가 곧 호증 번호가 된다.

    민사소송규칙 제105조 제1항이 서증 제출 시 문서의 제목·작성자·작성일을 밝히도록
    정하고 있어, 여기에 입증취지와 원본·사본 구별을 더한 것이 증거목록(증거설명서)이다.
    사용자 직접 입력 또는 파일 분석 API 결과로 채워진다.
    """

    name: str = Field(description="서증명 (문서의 제목)", examples=["임대차계약서"])
    author: str | None = Field(
        None,
        description="작성자 — 문서를 작성한 사람. 증거설명서 필수 기재사항",
        examples=["홍길동·김철수"],
    )
    date: str | None = Field(None, description="작성일", examples=["2024. 1. 1."])
    purpose: str | None = Field(
        None,
        description="입증취지 — 비우면 AI가 서증명 기준으로 제안",
        examples=["원·피고 간 계약 체결 및 보증금 지급 사실"],
    )
    original_type: OriginalType = Field(
        default=OriginalType.COPY,
        description="원본/사본 구별 (copy=사본, original=원본). 기본은 사본",
        examples=["copy"],
    )
    branch_no: str | None = Field(
        None,
        description="가지번호 — 한 서증을 여러 건으로 나눌 때. 값을 주면 "
        "'갑 제1호증의 2' 형태가 된다",
        examples=["2"],
    )
    note: str | None = Field(
        None,
        description="비고 — 가림 처리 등 특이사항",
        examples=["제3자의 전화번호가 포함되어 있어 해당 부분을 가림 처리하였습니다."],
    )


class EvidenceListInput(BaseModel):
    """증거목록 - 정보 입력 (step2)."""

    case_no: str = Field(
        description="사건 번호", examples=["2024가단123456 임대차보증금반환"]
    )
    court: str = Field(
        description="사건이 계속 중인 법원", examples=["서울중앙지방법원"]
    )
    plaintiff: str = Field(description="원고 이름", examples=["홍길동"])
    defendant: str = Field(description="피고 이름", examples=["김철수"])
    submitter_role: SubmitterRole = Field(
        default=SubmitterRole.PLAINTIFF,
        description="제출자 지위 — 호증 접두어 결정 (plaintiff=갑, defendant=을, "
        "intervenor=병)",
        examples=["plaintiff"],
    )
    evidence_start_no: int = Field(
        1,
        ge=1,
        description="시작 호증 번호. **호증은 사건 전체에서 이어진다** — 소장에서 "
        "갑 제2호증까지 냈다면 3 을 보낸다. 번호는 제출 순서대로 붙는다"
        "(민사소송규칙 제107조 제2항). 사건 기록을 세는 것은 본 서버 범위 밖이라 "
        "프론트가 확정해 보낸다",
        examples=[3],
    )
    evidence_items: list[EvidenceItem] = Field(
        min_length=1,
        description="증거 목록 — 리스트 순서대로 evidence_start_no 부터 호증 번호가 "
        "매겨짐 (프론트 드래그 순서)",
        examples=[
            [
                {
                    "name": "임대차계약서",
                    "author": "홍길동·김철수",
                    "date": "2024. 1. 1.",
                    "purpose": "원·피고 간 계약 체결 및 보증금 지급 사실",
                    "original_type": "copy",
                },
                {
                    "name": "보증금 입금내역",
                    "author": "국민은행",
                    "date": "2024. 1. 1.",
                    "purpose": None,
                    "original_type": "copy",
                },
            ]
        ],
    )


class EvidenceListSections(BaseModel):
    """증거목록 구조화 결과 (스트림 완료 시 파싱). PDF·편집용."""

    title: str = Field("", description="제목 부제 (예: 원고 제출 갑호증)")
    case_info: str = Field("", description="사건 표시 (사건번호·원고·피고)")
    evidence_table: str = Field(
        "", description="증거 표 (호증번호·서증명·작성일·입증취지, 마크다운 표)"
    )
    note: str = Field("", description="비고 (원본 소지·제출 예정 문구)")
    court: str = Field("", description="관할법원 (○○법원 귀중)")


# --- 증거 파일 자동 분석 (analyze) ---


class EvidenceDraft(BaseModel):
    """LLM 분류 출력 (structured output 강제용). EvidenceItem 과 동일 3필드."""

    name: str
    date: str | None
    purpose: str | None


class AnalyzedEvidence(BaseModel):
    """파일 한 개의 분석 결과."""

    filename: str = Field(description="업로드한 파일 이름 (프론트 매핑용)")
    success: bool = Field(description="분석 성공 여부")
    item: EvidenceItem | None = Field(
        None,
        description="성공 시 분류 결과 — generate 의 evidence_items 에 그대로 사용",
    )
    error: str | None = Field(None, description="실패 시 사유")


class AnalyzeResponse(BaseModel):
    """증거 파일 분석 응답. 업로드 순서 유지."""

    items: list[AnalyzedEvidence]
