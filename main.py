from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.documents.router import router as documents_router

app = FastAPI(title=settings.APP_NAME, root_path=settings.ROOT_PATH)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 도메인 라우터 등록 (도메인 추가 시 여기에 include_router 한 줄)
app.include_router(documents_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"app": settings.APP_NAME, "env": settings.ENV}


@app.get("/health")
def health():
    return {"status": "ok"}
