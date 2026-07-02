"""OpenAI 클라이언트 (도메인 공통).

지연 생성: import 시점이 아니라 실제 호출 시점에만 키를 요구한다.
(키 없이도 모듈 import·앱 기동이 가능해야 함 — CI 스모크 테스트 등)
"""

from functools import lru_cache

from openai import AsyncOpenAI

from app.core.config import settings


@lru_cache
def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
