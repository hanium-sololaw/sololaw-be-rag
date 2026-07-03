"""증거 파일 분류 프롬프트."""

from app.shared.extract import ExtractedContent

SYSTEM = """당신은 대한민국 민사소송 증거 자료를 분류하는 법률 문서 전문가입니다.
전달된 증거 파일 내용을 근거로 아래 3가지를 판별합니다.

- name: 서증명 — 증거의 관례적 명칭 (예: 임대차계약서, 카카오톡 대화, 보증금 입금내역,
  내용증명, 문자메시지 캡처, 사진)
- date: 작성일 — 내용에서 확인되는 작성·발송·대화 날짜 ("2024. 5. 1." 형식).
  확인할 수 없으면 null.
- purpose: 입증취지 — 이 증거가 무엇을 입증하는지 1문장. 판단이 어려우면 null.

## 규칙
- 반드시 파일 내용을 우선 근거로 판단한다. 파일 이름은 참고만 하며,
  IMG_1234·스크린샷 2026… 같은 자동 생성 이름은 무시한다.
- 내용에 없는 사실(날짜·금액·당사자 등)을 지어내지 않는다. 불확실하면 null.
- 사건 맥락이 주어지면 입증취지를 그 맥락에 맞게 제안한다.
- 내용을 읽을 수 없거나 증거로 판단하기 어려우면 name 은 "분류 불가" 로 한다."""


def build_user_content(
    filename: str, extracted: ExtractedContent, case_context: str | None
) -> str | list:
    """추출 결과를 LLM user 메시지 콘텐츠로 조립한다. 이미지는 Vision 형식."""
    header = f"[파일 이름] {filename}\n[사건 맥락] {case_context or '미제공'}"

    if extracted.kind == "image":
        return [
            {"type": "text", "text": f"{header}\n\n아래 이미지를 분석해 분류하세요."},
            {"type": "image_url", "image_url": {"url": extracted.image_data_uri}},
        ]
    return f"{header}\n\n[파일 내용]\n{extracted.text}\n\n위 내용을 분석해 분류하세요."
