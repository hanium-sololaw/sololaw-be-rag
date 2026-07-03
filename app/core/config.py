from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "sololaw-be-rag"
    ENV: str = "local"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # 국가법령정보센터 Open API 인증키 (OC, law.go.kr 발급 이메일 ID)
    LAW_API_KEY: str = ""
    # Open API 신청 시 등록한 서비스 도메인 — Referer 로 검증됨 (없으면 호출 거부)
    LAW_API_REFERER: str = "https://www.sololaw.site"

    # nginx 리버스 프록시 경로 prefix. 로컬은 "", 배포(nginx /rag/ 뒤)는 "/rag".
    # Swagger(/docs)·openapi.json 이 prefix 뒤에서도 안 깨지게 하는 용도.
    ROOT_PATH: str = ""

    # CORS 허용 출처
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
