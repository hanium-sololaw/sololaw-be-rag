"""문서 생성기 공통 인터페이스 (스트리밍).

새 문서 유형 추가 시: 이 클래스를 상속한 생성기를 만들고 registry.py 에 등록한다.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.documents.schemas.common import DocumentType


class BaseGenerator(ABC):
    """문서 유형별 생성기 베이스."""

    doc_type: DocumentType
    # 출력 마크다운 헤더 → 구조화 필드명. service 가 완료 시 섹션 파싱에 사용.
    section_map: dict[str, str] = {}

    @abstractmethod
    def generate_stream(self, inputs: dict) -> AsyncIterator[str]:
        """입력값으로 문서 본문을 스트리밍 생성한다.

        텍스트 델타를 순차적으로 yield 하는 async generator 를 반환한다.
        (누적·구조화 파싱은 service 계층에서 담당)
        """
        raise NotImplementedError
