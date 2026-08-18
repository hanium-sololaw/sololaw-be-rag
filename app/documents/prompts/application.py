"""신청서 생성 프롬프트.

신청서는 종류마다 완성 문서의 섹션 구성이 다르다 (강제집행은 신청이유가 없고,
임차권등기명령에는 관련 법리·별지가, 가압류에는 별도 서면인 진술서가 붙는다).
그래서 프롬프트는 하나만 두고 종류별 스펙(SPECS)을 주입한다.
섹션이 고정이 아니므로 파싱은 헤더 이름을 그대로 키로 쓴다 (generator 의 section_map=None).
"""

from dataclasses import dataclass

from app.documents.schemas.application import ApplicationInput, ApplicationType


@dataclass(frozen=True)
class Spec:
    """신청서 한 종류의 출력 명세."""

    title: str
    parties: tuple[str, str | None]  # (신청하는 쪽 호칭, 상대방 호칭)
    sections: tuple[str, ...]  # 출력할 '## 헤더' 순서
    rules: str  # 종류별 작성 규칙


SPECS: dict[ApplicationType, Spec] = {
    ApplicationType.PAYMENT_ORDER: Spec(
        title="지급명령신청서",
        parties=("채권자", "채무자"),
        sections=("당사자", "청구 종류", "신청취지", "신청이유"),
        rules="""- 청구 종류: "{청구 종류} 청구의 독촉사건" 한 줄로 적는다.
- 신청취지는 3줄 구성이다.
  1) "채무자는 채권자에게 {청구금액}원 및 이에 대하여 이 사건 지급명령 정본이 송달된
     다음 날부터 다 갚는 날까지 연 12%의 비율로 계산한 돈을 지급하라."
     (이자·지연손해금을 청구하지 않으면 지연이자 부분을 빼고 원금만 적는다)
  2) "독촉절차비용은 채무자가 부담한다."
  3) "라는 재판을 구합니다."
- 신청이유는 번호 목차로 쓰고 마지막 항목은
  "따라서 신청취지와 같은 지급명령을 구합니다." 로 맺는다.""",
    ),
    ApplicationType.LITIGATION_AID: Spec(
        title="소송구조신청서",
        parties=("신청인", None),
        sections=("사건", "당사자", "신청취지", "신청이유"),
        rules="""- 사건: "사 건  {사건번호} {사건명}" 형식. 소 제기 전이면 [사건번호 기재 필요] 로 둔다.
- 상대방은 표시하지 않는다. 신청인만 적는다.
- 신청취지: "신청인에게 위 사건에 관한 {구조받을 비용}의 납입을 유예하는 소송구조를
  하여 주시기 바랍니다."
- 신청이유는 번호 목차로 쓰되 자금능력이 부족하다는 점(소득·재산·부양가족)을 먼저 적고,
  "위 사건은 현재 소송 계속 중입니다."(또는 소 제기 예정),
  "또한 이 사건 청구는 패소할 것이 분명하지 아니합니다.",
  "따라서 신청취지와 같은 재판을 구합니다." 로 맺는다.""",
    ),
    ApplicationType.LEASE_REGISTRATION: Spec(
        title="임차권등기명령신청서",
        parties=("신청인", "피신청인"),
        sections=("당사자", "신청취지", "신청이유", "관련 법리", "첨부서류", "별지"),
        rules="""- 신청취지: "별지 목록 기재 건물에 관하여 아래와 같은 주택임차권등기를 명한다.
  라는 재판을 구합니다." 를 먼저 쓰고, 이어서 번호 목록으로 아래를 적는다.
  1. 임대차계약일자  2. 임차보증금액 / 차임, 임차 부분
  3. 주민등록일자    4. 점유개시일자  5. 확정일자
  (상가 임대차면 "상가건물임차권등기" 로 바꾼다)
- 신청이유는 번호 목차로 계약 체결·입주·전입신고 → 임대차 종료 → 보증금 미반환 →
  "대항력과 우선변제권을 유지하기 위하여 이 사건 신청에 이르렀습니다." 순으로 쓴다.
- 관련 법리: 인용할 판례가 주어졌을 때만 쓴다. "대법원 {선고일} 선고 {사건번호} 판결"
  을 적고 다음 줄에 요지를 큰따옴표로 인용한다. 판례가 없으면 이 섹션은 헤더만 두고
  "[인용할 판례 없음]" 이라고 적는다.
- 별지: "부동산의 표시" 라는 줄 뒤에 목적물 주소와 건물 내역을 등기부 표기대로 적는다.""",
    ),
    ApplicationType.ENFORCEMENT: Spec(
        title="강제집행신청서",
        parties=("채권자", "채무자"),
        sections=("당사자", "집행권원", "집행목적물", "청구금액", "신청취지"),
        rules="""- 이 신청서에는 신청이유를 쓰지 않는다. 위 섹션만 출력한다.
- 집행권원: "{법원} {사건번호} {집행권원 종류}({확정일} 확정)" 한 줄.
- 집행목적물: 압류·집행할 대상을 특정해 적는다.
- 청구금액: "금 {금액}원" 을 적고 다음 줄에
  "(위 집행권원에 표시된 원금·지연손해금 및 소송비용)" 을 붙인다.
- 신청취지: "위 집행권원에 기초하여 채무자에 대하여 {집행 방법}을(를) 하여 주시기
  바랍니다." 형식. 집행문을 아직 받지 않았다면 그 사실을 한 줄 덧붙인다.""",
    ),
    ApplicationType.PROVISIONAL_SEIZURE: Spec(
        title="가압류신청서",
        parties=("채권자", "채무자"),
        sections=(
            "당사자",
            "청구채권의 표시",
            "가압류할 목적물의 표시",
            "신청취지",
            "신청이유",
            "가압류신청 진술서",
        ),
        rules="""- 청구채권의 표시: "금 {금액}원" 과 채권의 발생일·종류를 적는다.
- 가압류할 목적물의 표시: 묶을 재산을 특정해 적는다.
- 신청취지: "채권자가 채무자에 대하여 가지는 위 청구채권의 집행을 보전하기 위하여,
  채무자 소유의 별지 목록 기재 재산을 가압류한다. 라는 재판을 구합니다."
- 신청이유는 번호 목차로 채권 취득 → 보전의 필요성 → 담보 제공 순으로 쓰고,
  "따라서 지금 가압류해 두지 않으면 나중에 승소하더라도 집행이 불가능하거나 매우
  곤란해질 우려가 있습니다." 취지를 포함한다.
- 가압류신청 진술서: **신청서와 별개의 서면**이다. 법원 양식이 정해져 있으므로
  **아래 항목·순서를 그대로** 쓰고, 각 물음 아래에 제공된 답변을 적는다.
  항목을 옮기거나 합치거나 새로 만들지 않는다.

  맨 앞에 "채권자는 가압류신청과 관련하여 다음 사실을 진술하며, 만일 허위진술을
  하거나 진술 사항을 고의로 누락한 경우에는 특별한 사정이 없는 한 보전명령 없이
  신청이 기각될 것임을 잘 알고 있습니다." 를 적는다.

  1. 피보전권리(청구채권)와 관련하여
     가. 채무자가 신청서에 기재한 청구채권을 인정하고 있습니까?
     나. 채무자의 의사를 언제, 어떠한 방법으로 확인하였습니까?
     다. 채권자가 신청서에 기재한 청구채권 외에 다른 채권이 있습니까?
  2. 보전의 필요성과 관련하여
     가. 가압류하지 않으면 향후 강제집행이 불가능하거나 매우 곤란해질 사유는
        무엇입니까?
     나. 신청서에 기재한 청구금액은 본안소송에서 승소할 수 있는 금액으로 적정하게
        산출된 것입니까?
     다. (채무자가 법인인 경우) 채무자가 영업활동을 하고 있습니까?
  3. 본안소송과 관련하여
     가. 채권자는 이 청구채권과 관련하여 본안소송을 제기한 사실이 있습니까?
     나. 채권자가 최근 5년 안에 채무자를 상대로 신청한 보전처분 사건이 있습니까?
  4. 중복 보전처분과 관련하여
     가. 같은 청구채권에 기하여 이 신청 이전에 보전처분을 신청하여 결정을 받은
        사실이 있습니까?

  답하지 않은 항목은 [확인 필요] 로 표시한다. 사실과 다르게 적으면 보정 기회 없이
  기각될 수 있으므로 주어진 답변을 바꾸지 않는다(재민 2003-4 제3조).""",
    ),
}


def build_system_prompt(app_type: ApplicationType) -> str:
    """종류별 스펙을 끼운 시스템 프롬프트를 만든다."""
    spec = SPECS[app_type]
    headers = "\n".join(f"## {s}" for s in spec.sections)
    applicant, respondent = spec.parties
    party_rule = (
        f"- 당사자: 신청하는 쪽은 '{applicant}', 상대방은 '{respondent}' 로 표시한다."
        if respondent
        else f"- 당사자: '{applicant}' 만 표시한다. 상대방은 적지 않는다."
    )

    return f"""당신은 대한민국 민사소송 법원 제출용 '{spec.title}' 작성을 돕는 법률 문서 전문가입니다.
사용자가 제공한 정보만으로 신청서 초안을 작성합니다.

## 출력 형식 (반드시 준수)
아래 섹션을 정확히 이 마크다운 헤더로, 이 순서대로 출력하세요.
목록에 없는 헤더를 만들지 마세요. 헤더 외 인사말·설명·마무리 문구는 쓰지 마세요.

{headers}

## 공통 작성 규칙
{party_rule}
  이름과 주소를 줄을 나누어 적고, 연락처가 주어지면 "전화 {{번호}}" 를 덧붙인다.
  대표자·법정대리인이 주어지면 이름 아래에 병기한다.
  **주민등록번호는 쓰지 않는다** (시스템이 별도로 처리한다).
- 사용자의 일상 표현을 정확한 법률 문언으로 변환한다.
- [사실관계] 로 주어진 항목은 날짜·금액·조건을 그대로 살려 반영한다. 값을 바꾸지 않는다.
- 날짜·서명란·법원 표시("○○법원 귀중")는 출력하지 않는다. 시스템이 별도로 붙인다.

## 이 신청서의 작성 규칙
{spec.rules}

## 금지 사항
- 사용자가 제공하지 않은 사실(날짜·금액·계약 조건 등)을 지어내지 않는다.
  빠진 정보는 [○○ 기재 필요] 로 표시한다.
- 법률 자문이 아닌 초안 작성이므로 단정적 승소 표현을 쓰지 않는다."""


def _party_block(label: str, p) -> str:
    lines = [f"[{label}] {p.name}"]
    if p.representative:
        lines.append(f"- 대표자·법정대리인: {p.representative}")
    lines.append(f"- 주소: {p.address}")
    if p.phone:
        lines.append(f"- 연락처: {p.phone}")
    if p.email:
        lines.append(f"- 이메일: {p.email}")
    return "\n".join(lines)


def build_user_prompt(d: ApplicationInput) -> str:
    """ApplicationInput 을 프롬프트 본문으로 조립한다. (주민등록번호는 제외)"""
    spec = SPECS[d.application_type]
    applicant_label, respondent_label = spec.parties

    parties = _party_block(applicant_label, d.applicant)
    if respondent_label and d.respondent:
        parties += "\n\n" + _party_block(respondent_label, d.respondent)

    facts = "\n".join(f"- {k}: {v}" for k, v in d.facts.items()) or "없음"
    attachments = "\n".join(f"- {a}" for a in d.attachments) or "없음"
    precedents = (
        "\n".join(
            f"- {p.case_no}" + (f": {p.summary}" if p.summary else "")
            for p in d.cited_precedents
        )
        or "없음"
    )
    amount = f"{d.claim_amount:,}원" if d.claim_amount is not None else "미기재"

    return f"""[신청서 종류] {spec.title}
[신청할 법원] {d.court}
[사건번호] {d.case_no or "미기재"}
[사건명] {d.case_name or "미기재"}
[청구·집행 금액] {amount}

{parties}

[사실관계]
{facts}

[신청 사유 (사용자의 일상 언어)]
{d.narrative}

[함께 낼 서류]
{attachments}

[인용할 판례]
{precedents}

위 정보로 {spec.title}를 작성하세요."""


# 스펙 표는 종류가 늘면 조용히 KeyError 를 내므로 import 시점에 정합성을 확인한다.
assert set(SPECS) == set(ApplicationType)
