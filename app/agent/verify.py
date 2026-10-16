"""설명 Agent 의 근거 검증 — 문서에 나온 사건번호가 실제로 주어진 것인지 확인한다.

허용 목록 = 요청 입력에 들어 있는 모든 사건번호(현재 사건·원심·인용 판례 등).
입력에도 없는 사건번호는 LLM 이 지어낸 것으로 본다.
"""

import json
import re

# 법원 사건별 부호문자. 숫자+한글+숫자를 모두 잡으면 "101동1203호"·"10억2000만원"
# 같은 표현이 걸리므로 알려진 부호만 인정한다.
# shortcut: 목록에 없는 부호의 사건번호는 검증을 건너뛴다, 오탐이 보이면 부호를 추가.
_CODES = (  # noqa: SIM905 — 한 줄씩 나열하면 70줄이 된다
    "가합 가단 가소 나 다 다카 라 마 그 머 차 차전 카 카합 카단 카기 카담 카확 카열 "
    "카명 카조 카구 카공 카경 카불 카임 타경 타기 타채 타배 하합 하단 하면 회합 회단 "
    "개회 드합 드단 르 므 느합 느단 브 스 즈합 즈단 즈기 구합 구단 누 두 아 허 후 "
    "고합 고단 고정 고약 노 도 모 오 초 헌가 헌바 헌마 헌라 재다 재나 재가합 재가단"
).split()
_CASE_NO_RE = re.compile(
    r"(?<!\d)(?:\d{4}|\d{2})(?:"
    + "|".join(sorted(_CODES, key=len, reverse=True))
    + r")\d{1,7}(?!\d)"
)


def case_numbers(text: str) -> set[str]:
    return set(_CASE_NO_RE.findall(text))


def unknown_case_numbers(text: str, inputs: dict) -> list[str]:
    """문서 본문의 사건번호 중 입력 어디에도 없는 것."""
    allowed = case_numbers(json.dumps(inputs, ensure_ascii=False, default=str))
    return sorted(case_numbers(text) - allowed)
