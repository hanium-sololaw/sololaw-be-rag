"""업로드 파일 내용 추출 (도메인 공통).

증거 파일 등에서 AI 분석용 내용을 뽑아낸다. 파일은 저장하지 않는다 (무상태).
- 이미지(JPG/PNG) → base64 data URI (Vision 입력용)
- PDF → pypdf 텍스트 추출 (텍스트 없는 스캔본은 미지원)
- TXT(카카오톡 내보내기 등) → 텍스트 디코딩
"""

import base64
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

MAX_FILE_SIZE = 10 * 1024 * 1024  # 파일당 10MB
MAX_TEXT_CHARS = 8000  # LLM 입력 과대 방지 (앞부분만 사용)

_IMAGE_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


class ExtractError(Exception):
    """추출 실패 — 사용자에게 보여줄 사유 메시지를 담는다."""


@dataclass
class ExtractedContent:
    """추출 결과. 이미지면 data URI, 텍스트 계열이면 본문."""

    kind: str  # "image" | "text"
    text: str | None = None
    image_data_uri: str | None = None


def _detect_kind(filename: str, content_type: str | None) -> str:
    """확장자와 content_type 으로 파일 종류 판별.

    curl 등이 content_type 을 octet-stream 으로 보내는 경우가 있어 확장자를 함께 본다.
    """
    name = filename.lower()
    ct = (content_type or "").lower()
    if ct in ("image/jpeg", "image/png") or name.endswith((".jpg", ".jpeg", ".png")):
        return "image"
    if ct == "application/pdf" or name.endswith(".pdf"):
        return "pdf"
    if ct.startswith("text/") or name.endswith(".txt"):
        return "text"
    return "unknown"


def _decode_text(data: bytes) -> str:
    """utf-8 우선, 실패 시 cp949 (카카오톡 PC 내보내기 등 한국어 환경 대비)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("cp949")
        except UnicodeDecodeError as e:
            raise ExtractError("텍스트 인코딩을 해석할 수 없습니다.") from e


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except ExtractError:
        raise
    except Exception as e:
        raise ExtractError("PDF 파일을 읽을 수 없습니다.") from e
    if not text.strip():
        raise ExtractError(
            "텍스트를 추출할 수 없는 PDF 입니다. 스캔본 PDF 는 아직 미지원입니다."
        )
    return text


def extract_content(
    filename: str, content_type: str | None, data: bytes
) -> ExtractedContent:
    """파일 한 개의 내용을 추출한다. 실패 시 ExtractError."""
    if len(data) > MAX_FILE_SIZE:
        raise ExtractError("파일이 10MB 를 초과합니다.")
    if not data:
        raise ExtractError("빈 파일입니다.")

    kind = _detect_kind(filename, content_type)

    if kind == "image":
        ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        media = _IMAGE_MEDIA.get(ext, "image/jpeg")
        encoded = base64.b64encode(data).decode("ascii")
        return ExtractedContent(
            kind="image", image_data_uri=f"data:{media};base64,{encoded}"
        )

    if kind == "pdf":
        return ExtractedContent(
            kind="text", text=_extract_pdf_text(data)[:MAX_TEXT_CHARS]
        )

    if kind == "text":
        return ExtractedContent(kind="text", text=_decode_text(data)[:MAX_TEXT_CHARS])

    raise ExtractError(
        "지원하지 않는 파일 형식입니다. PDF·JPG·PNG·TXT 만 업로드할 수 있습니다."
    )
