from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import FastAPI


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "sololaw-be-rag"
    ENV: str = "local"
    OPENAI_API_KEY: str = ""  # placeholder, 실제 키는 .env에서 주입


settings = Settings()

app = FastAPI(title=settings.APP_NAME)


@app.get("/")
def root():
    return {"app": settings.APP_NAME, "env": settings.ENV}


@app.get("/health")
def health():
    return {"status": "ok"}
