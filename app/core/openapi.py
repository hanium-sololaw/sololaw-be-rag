"""OpenAPI 스키마 보정 유틸.

FastAPI 는 OpenAPI 3.1 방식으로 파일 업로드를 contentMediaType 으로만 표기하는데,
Swagger UI 는 format: binary(3.0 방식)가 있어야 파일 선택 입력으로 렌더링한다.
둘을 병기해 문서 화면을 보정한다. 런타임 동작에는 영향 없음.
"""

from fastapi import FastAPI

_OCTET = "application/octet-stream"


def _patch_upload_fields(spec: dict) -> None:
    """multipart 파일 필드(단일·배열)에 format: binary 를 보강한다."""
    for schema in spec.get("components", {}).get("schemas", {}).values():
        for prop in schema.get("properties", {}).values():
            if not isinstance(prop, dict):
                continue
            items = prop.get("items")
            if isinstance(items, dict) and items.get("contentMediaType") == _OCTET:
                items.setdefault("format", "binary")
            if prop.get("contentMediaType") == _OCTET:
                prop.setdefault("format", "binary")


def install_upload_schema_fix(app: FastAPI) -> None:
    """앱의 openapi() 를 감싸 파일 업로드 스키마 보정을 적용한다."""
    original = app.openapi

    def patched() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        spec = original()  # 결과는 app.openapi_schema 에 캐시됨
        _patch_upload_fields(spec)
        return spec

    app.openapi = patched
