from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "sololaw-be-rag"
    ENV: str = "local"
    OPENAI_API_KEY: str = "" 

    # CORS 허용 출처 
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
