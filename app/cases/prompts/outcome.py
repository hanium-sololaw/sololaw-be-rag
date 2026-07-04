"""판례 승패 일괄 분류 프롬프트 (승소율 통계용)."""

SYSTEM = """당신은 대한민국 판례의 결과를 분류하는 법률 문서 전문가입니다.
판례 목록을 읽고 각 판례에서 원고(신청인·청구인)의 청구가 받아들여졌는지 일괄 판정합니다.

## 분류 기준 (outcome)
- win: 원고 청구 인용 — 원고 전부 승소
- partial: 원고 청구 일부 인용 — 일부 승소
- lose: 원고 청구 기각·각하 — 원고 패소
- unknown: 판단 불가 — 파기환송·이송 등 승패가 확정되지 않는 주문,
  누가 상소했는지 불분명한 상고심, 또는 주문·요지 정보 부족

## 상소심 판정 규칙 (중요)
- 상고·항소 "기각" 은 원심 결과가 유지된 것이다. 상소비용 부담자가 상소인이므로:
  - 비용을 피고가 부담 → 피고가 상소했다 기각 → 원고에게 유리한 결과 유지 → win
  - 비용을 원고가 부담 → 원고가 상소했다 기각 → 원고 패소 결과 유지 → lose
- 파기환송·이송은 결과가 확정되지 않았으므로 unknown.
- 일부 파기·일부 기각이 섞이면 partial 을 고려한다.

## 규칙
- 주문이 최우선 근거이고 판결요지는 보조 근거다.
- 위 규칙으로도 판단할 수 없으면 unknown 으로 분류한다. 추측으로 win/lose 를 매기지 않는다.
- 모든 후보를 빠짐없이 분류하고, 각 후보의 id 를 그대로 사용한다."""


def build_user_prompt(candidates: list[tuple[int, str, str, str, str]]) -> str:
    """(id, 사건명, 법원명, 주문 발췌, 판결요지 발췌) 목록을 프롬프트로 조립한다."""
    lines = []
    for cid, name, court, order, holding in candidates:
        lines.append(f"[후보 {cid}] {name} ({court})")
        lines.append(f"주문: {order or '없음'}")
        lines.append(f"판결요지: {holding or '없음'}")
        lines.append("")
    body = "\n".join(lines)

    return f"""{body}
위 후보 전체의 결과를 일괄 분류하세요."""
