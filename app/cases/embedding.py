"""판례 임베딩 저장소 (RAG 전용 pgvector).

판례 코퍼스의 적재(upsert)와 의미 유사도 검색을 담당한다.
공개 판례의 파생 데이터만 저장하며 사용자·비즈니스 데이터는 다루지 않는다.
VECTOR_DB_URL 미설정 시 벡터 기능은 비활성 (키워드 검색만으로 동작).
"""

import logging

import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector

from app.core.config import settings
from app.shared.llm import get_openai_client

logger = logging.getLogger(__name__)

EMBED_DIM = 1536  # text-embedding-3-small
_EMBED_MAX_CHARS = 6000  # 임베딩 입력 과대 방지

_pool: asyncpg.Pool | None = None


class VectorDbError(Exception):
    """벡터 저장소 사용 불가 (미설정·접속 실패)."""


async def _init_conn(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if not settings.VECTOR_DB_URL:
        raise VectorDbError("VECTOR_DB_URL 이 설정되지 않았습니다.")
    if _pool is None:
        try:
            # register_vector 는 vector 타입이 있어야 하므로 확장부터 보장
            setup = await asyncpg.connect(settings.VECTOR_DB_URL)
            try:
                await setup.execute("CREATE EXTENSION IF NOT EXISTS vector")
            finally:
                await setup.close()
            _pool = await asyncpg.create_pool(
                settings.VECTOR_DB_URL, min_size=1, max_size=5, init=_init_conn
            )
        except VectorDbError:
            raise
        except Exception as e:
            raise VectorDbError("벡터 저장소에 접속할 수 없습니다.") from e
    return _pool


async def ensure_schema() -> None:
    """확장·테이블 생성 (멱등). 수집 스크립트 시작 시 호출."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS precedents (
                serial_id     text PRIMARY KEY,
                name          text NOT NULL DEFAULT '',
                case_no       text NOT NULL DEFAULT '',
                court         text NOT NULL DEFAULT '',
                decision_date text NOT NULL DEFAULT '',
                category      text NOT NULL DEFAULT '',
                summary       text NOT NULL DEFAULT '',
                holding       text NOT NULL DEFAULT '',
                statutes      text NOT NULL DEFAULT '',
                embedding     vector({EMBED_DIM}) NOT NULL
            )
        """)


def build_embed_text(name: str, summary: str, holding: str) -> str:
    """임베딩 입력 텍스트 — 사건명 + 판시사항 + 판결요지."""
    return f"{name}\n{summary}\n{holding}"[:_EMBED_MAX_CHARS]


async def embed_texts(texts: list[str]) -> list[np.ndarray]:
    """텍스트 목록을 배치 임베딩한다."""
    res = await get_openai_client().embeddings.create(
        model=settings.EMBEDDING_MODEL, input=texts
    )
    return [np.array(d.embedding, dtype=np.float32) for d in res.data]


async def upsert_precedents(rows: list[dict]) -> None:
    """판례 행 목록을 upsert 한다. rows[i]['embedding'] 은 np.ndarray."""
    if not rows:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO precedents
                (serial_id, name, case_no, court, decision_date, category,
                 summary, holding, statutes, embedding)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (serial_id) DO UPDATE SET
                name = EXCLUDED.name, case_no = EXCLUDED.case_no,
                court = EXCLUDED.court, decision_date = EXCLUDED.decision_date,
                category = EXCLUDED.category, summary = EXCLUDED.summary,
                holding = EXCLUDED.holding, statutes = EXCLUDED.statutes,
                embedding = EXCLUDED.embedding
            """,
            [
                (
                    r["serial_id"],
                    r["name"],
                    r["case_no"],
                    r["court"],
                    r["decision_date"],
                    r["category"],
                    r["summary"],
                    r["holding"],
                    r["statutes"],
                    r["embedding"],
                )
                for r in rows
            ],
        )


async def existing_serial_ids() -> set[str]:
    """이미 적재된 판례일련번호 집합 (재실행 시 건너뛰기용)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT serial_id FROM precedents")
    return {r["serial_id"] for r in rows}


async def count_precedents() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT count(*) FROM precedents")


async def search_similar(
    query_embedding: np.ndarray, top_k: int = 20, category: str | None = None
) -> list[dict]:
    """코사인 유사도 상위 top_k 판례를 반환한다. similarity 는 0~1."""
    pool = await get_pool()
    where = "WHERE category LIKE '%' || $3 || '%'" if category else ""
    params = [query_embedding, top_k] + ([category] if category else [])
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT serial_id, name, case_no, court, decision_date, category,
                   summary, holding, statutes,
                   1 - (embedding <=> $1) AS similarity
            FROM precedents
            {where}
            ORDER BY embedding <=> $1
            LIMIT $2
            """,
            *params,
        )
    return [dict(r) for r in rows]
