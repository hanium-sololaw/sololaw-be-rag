"""준비서면(brief) 입력/출력 스키마.

준비서면은 상대방 서면에 대응하는 문서라 '쟁점 하나 = 상대 주장 + 반박 + 근거'
묶음이 문서 구조를 이룬다. 호증 번호는 사건 전체에서 이어지므로 시작 번호를
받아 코드에서 확정한다 (AI 에 맡기지 않는다).
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.documents.schemas.complaint import CitedPrecedent


class SubmitterRole(str, Enum):
    """준비서면 제출자가 사건에서 갖는 지위."""

    PLAINTIFF = "plaintiff"  # 원고 — 갑 호증
    DEFENDANT = "defendant"  # 피고 — 을 호증


class RebuttalPoint(BaseModel):
    """쟁점 하나 — 화면의 '반박 포인트' 한 묶음."""

    claim: str = Field(
        description="상대방은 뭐라고 하나요 — 이 쟁점에서 상대가 든 주장·항변",
        examples=["공제 주장 (원상회복비 등)"],
    )
    rebuttal: str = Field(
        description="어디가 사실과 다른가요 — 일상 언어로 쓰면 AI 가 법률 문언으로 변환",
        examples=["2년 살면서 생긴 벽지 색 바램하고 장판 눌린 자국뿐이에요."],
    )
    evidence_ref: str | None = Field(
        None,
        description="무엇으로 보여줄 수 있나요 — 이 쟁점의 근거 증거. 반박 끝에 "
        "'(근거 : 갑 제7호증 …)' 형태로 붙는다",
        examples=["갑 제7호증 목적물 인도 확인서"],
    )
    precedent_ref: str | None = Field(
        None,
        description="이 쟁점에 인용할 판례 사건번호 (선택)",
        examples=["2025다220329"],
    )


class BriefInput(BaseModel):
    """준비서면 - 정보 입력 (위저드 1~4단계 결과를 한 번에 받는다)."""

    model_config = {
        "json_schema_extra": {
            "example": {
                "court": "서울중앙지방법원",
                "panel": "제12민사단독",
                "case_no": "2024가단123456",
                "case_name": "임대차보증금",
                "plaintiff": "홍길동",
                "defendant": "김철수",
                "submitter_role": "plaintiff",
                "brief_no": "준비서면(2)",
                "stage": "상대방 답변서를 받았어요",
                "hearing_date": "2026-08-22",
                "opponent_doc_type": "준비서면(1)",
                "opponent_doc_date": "2026-08-07",
                "opponent_claim": "피고는 제가 나갈 때 도배랑 장판을 다 망가뜨려 놨다고 "
                "합니다. 그래서 120만원을 빼고 주는 게 맞다고 해요.",
                "defenses": ["공제 주장 (원상회복비 등)", "동시이행 항변"],
                "undisputed_facts": "보증금 1,000만원을 받은 사실과 계약이 2026년 1월 "
                "1일에 끝난 건 피고도 맞다고 인정합니다.",
                "evidence_start_no": 7,
                "new_evidence": ["목적물 인도 확인서", "통상손모 비교 사진"],
                "rebuttal_points": [
                    {
                        "claim": "공제 주장 (원상회복비 등)",
                        "rebuttal": "2년 살면서 생긴 벽지 색 바램하고 장판 눌린 "
                        "자국뿐이에요. 나갈 때 사진도 다 찍어뒀습니다.",
                        "evidence_ref": "갑 제7호증 목적물 인도 확인서",
                    },
                    {
                        "claim": "동시이행 항변",
                        "rebuttal": "이미 2026년 1월 3일에 열쇠 넘기고 다 비웠어요. "
                        "관리사무소 확인도 받았습니다.",
                        "evidence_ref": "갑 제8호증 통상손모 비교 사진",
                    },
                ],
                "my_argument": "피고 주장은 근거가 없으니 보증금 1,000만원 전부와 "
                "늦어진 기간만큼의 이자를 돌려받게 해주세요.",
                "cited_precedents": [
                    {
                        "case_no": "대법원 2026. 5. 8. 선고 2025다220329 판결",
                        "summary": "상속인이 기존 조건을 유지한 채 임대차기간만 연장한 "
                        "행위가 상속재산의 처분이 아니라 관리행위에 해당하는지가 문제 된 사건.",
                    }
                ],
            }
        }
    }

    # --- 1단계: 어떤 사건의 준비서면인가요 ---
    court: str = Field(
        description="사건이 계속 중인 법원", examples=["서울중앙지방법원"]
    )
    panel: str | None = Field(
        None,
        description="담당 재판부. 기일통지서·전자소송 화면에 적혀 있다. "
        "있으면 '○○법원 제12민사단독 귀중' 으로 표시된다",
        examples=["제12민사단독"],
    )
    case_no: str = Field(description="사건 번호", examples=["2024가단123456"])
    case_name: str | None = Field(None, description="사건명", examples=["임대차보증금"])
    plaintiff: str = Field(description="원고 이름", examples=["홍길동"])
    defendant: str = Field(description="피고 이름", examples=["김철수"])
    submitter_role: SubmitterRole = Field(
        default=SubmitterRole.PLAINTIFF,
        description="제출자가 원고/피고 중 누구인지. 호증 접두어(갑·을)를 정한다",
        examples=["plaintiff"],
    )
    brief_no: str | None = Field(
        None,
        description="준비서면 회차. 문서 제목이 된다. 없으면 '준비서면'",
        examples=["준비서면(2)"],
    )
    stage: str | None = Field(
        None,
        description="지금 소송이 어느 단계인지 (화면 선택지 라벨 그대로)",
        examples=["상대방 답변서를 받았어요"],
    )
    hearing_date: str | None = Field(
        None, description="제출 기한 / 다음 변론기일", examples=["2026-08-22"]
    )

    # --- 2단계: 상대방은 뭐라고 했나요 ---
    opponent_doc_type: str | None = Field(
        None,
        description="상대방이 낸 서면 종류 (답변서·준비서면(1)·증거설명서·기타)",
        examples=["준비서면(1)"],
    )
    opponent_doc_date: str | None = Field(
        None,
        description="그 서면을 받은 날(도달일). '2026. 8. 7.자 준비서면(1)에서' 로 특정된다",
        examples=["2026-08-07"],
    )
    opponent_claim: str = Field(
        description="상대방이 뭐라고 주장하던가요 — 읽은 대로 적으면 AI 가 요지로 정리",
        examples=["도배와 장판을 망가뜨려 놨으니 120만원을 빼고 주겠다고 합니다."],
    )
    defenses: list[str] = Field(
        default=[],
        description="상대방이 든 항변 종류 (부인·변제·소멸시효·상계·공제·동시이행·"
        "과실상계 등). 화면 선택지 라벨 그대로",
        examples=[["공제 주장 (원상회복비 등)", "동시이행 항변"]],
    )
    undisputed_facts: str | None = Field(
        None,
        description="상대방이 맞다고 인정한 부분. 다툼 없는 사실로 먼저 갈라내면 "
        "재판부가 볼 쟁점이 줄어든다",
        examples=["보증금 1,000만원을 받은 사실은 피고도 인정합니다."],
    )

    # --- 3단계: 증거·판례 첨부 ---
    evidence_start_no: int = Field(
        1,
        ge=1,
        description="이번 서면에서 시작할 호증 번호. **호증은 사건 전체에서 이어진다** — "
        "소장에서 갑 제6호증까지 냈다면 7 을 보낸다. 사건 기록을 세는 것은 "
        "본 서버 범위 밖이라 프론트가 확정해 보낸다",
        examples=[7],
    )
    new_evidence: list[str] = Field(
        default=[],
        description="이번에 함께 낼 증거의 서증명. 보낸 순서대로 "
        "evidence_start_no 부터 호증 번호가 매겨진다",
        examples=[["목적물 인도 확인서", "통상손모 비교 사진"]],
    )
    cited_precedents: list[CitedPrecedent] = Field(
        default=[],
        description="인용할 판례 목록 — '관련 법리' 섹션에 반영된다",
    )

    # --- 4단계: 어떤 부분을 반박하나요 ---
    rebuttal_points: list[RebuttalPoint] = Field(
        default=[],
        description="쟁점별 반박 묶음. 하나가 준비서면의 '가.', '나.' 항목이 된다",
    )
    my_argument: str | None = Field(
        None,
        description="재판부에 마지막으로 강조하고 싶은 것. 비우면 관례 문구로 맺는다",
        examples=["피고 주장은 근거가 없으니 보증금 전부를 돌려받게 해주세요."],
    )


class BriefSections(BaseModel):
    """준비서면 구조화 결과 (스트림 완료 시 파싱). PDF·편집용."""

    title: str = Field("", description="제목 (예: 준비서면(2))")
    case_info: str = Field("", description="사건 표시 (사건번호·사건명·원고·피고)")
    opponent_summary: str = Field(
        "", description="상대방 주장의 요지 — 항변 분류와 다툼 없는 사실 포함"
    )
    rebuttal: str = Field("", description="반박 — 쟁점별 가·나·다 항목")
    related_law: str = Field(
        "", description="관련 법리 — 인용 판례. 판례가 없으면 빈 값"
    )
    conclusion: str = Field("", description="결론")
    evidence: str = Field("", description="입증방법 (호증 목록)")
    attachments: str = Field("", description="첨부서류")
    court: str = Field("", description="관할법원 (○○법원 ○○재판부 귀중)")
