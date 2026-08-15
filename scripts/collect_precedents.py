"""판례 코퍼스 수집·임베딩 적재 스크립트.

나홀로소송 빈출 주제 시드 키워드로 국가법령정보센터 판례를 수집해
임베딩과 함께 pgvector 에 적재한다. 재실행 시 이미 적재된 판례는 건너뛴다.

사용 예:
  # 전체 시드, 시드당 3페이지 (페이지당 100건)
  uv run python -m scripts.collect_precedents --pages 3

  # 소량 테스트
  uv run python -m scripts.collect_precedents --seeds "임대차 보증금 반환" --pages 1 --display 20

필요 환경변수: VECTOR_DB_URL, LAW_API_KEY, OPENAI_API_KEY
"""

import argparse
import asyncio
import sys
import time

import httpx

from app.cases import client, embedding

# 나홀로소송 빈출 주제 시드 (민사 중심)
SEEDS = [
    "임대차 보증금 반환",
    "전세 보증금",
    "월세 연체 명도",
    "임대차 계약 해지",
    "권리금 회수",
    "대여금 반환",
    "약정금 청구",
    "임금 체불",
    "퇴직금 청구",
    "손해배상 불법행위",
    "교통사고 손해배상",
    "누수 손해배상",
    "매매대금 청구",
    "계약금 반환",
    "부당이득 반환",
    "물품대금",
    "용역대금",
    "공사대금",
    "양육비 청구",
    "위자료 청구",
    "재산분할",
    "사기 손해배상",
    "명예훼손 손해배상",
    "채무부존재 확인",
]

_EMBED_BATCH = 100  # 임베딩·적재 배치 크기


async def collect(seeds: list[str], pages: int, display: int, delay: float) -> None:
    await embedding.ensure_schema()
    already = await embedding.existing_serial_ids()
    print(f"기존 적재: {len(already)}건 — 중복은 건너뜁니다")

    seen: set[str] = set(already)
    pending: list[dict] = []
    stats = {"collected": 0, "skipped_dup": 0, "skipped_empty": 0, "failed": 0}
    started = time.monotonic()

    async def flush() -> None:
        if not pending:
            return
        texts = [
            embedding.build_embed_text(r["name"], r["summary"], r["holding"])
            for r in pending
        ]
        vectors = await embedding.embed_texts(texts)
        for r, v in zip(pending, vectors):
            r["embedding"] = v
        await embedding.upsert_precedents(pending)
        stats["collected"] += len(pending)
        elapsed = int(time.monotonic() - started)
        print(f"  적재 +{len(pending)} (누적 {stats['collected']}건, {elapsed}s)")
        pending.clear()

    async with httpx.AsyncClient() as http:
        for seed in seeds:
            print(f"[시드] {seed}")
            for page in range(1, pages + 1):
                try:
                    _, items = await client.search_precedents(
                        http, seed, display=display, page=page
                    )
                except client.LawApiError as e:
                    print(f"  검색 실패 (page={page}): {e}")
                    break
                if not items:
                    break
                for item in items:
                    serial = str(item.get("판례일련번호", ""))
                    if not serial or serial in seen:
                        stats["skipped_dup"] += 1
                        continue
                    seen.add(serial)
                    await asyncio.sleep(delay)  # API 호출 예의
                    try:
                        detail = await client.fetch_precedent_detail(http, serial)
                    except client.LawApiError:
                        stats["failed"] += 1
                        continue
                    summary = detail.get("판시사항", "")
                    holding = detail.get("판결요지", "")
                    if not summary and not holding:
                        stats["skipped_empty"] += 1  # 임베딩할 내용 없음
                        continue
                    pending.append(
                        {
                            "serial_id": serial,
                            "name": item.get("사건명", ""),
                            "case_no": item.get("사건번호", ""),
                            "court": item.get("법원명", ""),
                            "decision_date": str(item.get("선고일자", "")),
                            "category": item.get("사건종류명", ""),
                            "summary": summary,
                            "holding": holding,
                            "statutes": detail.get("참조조문", ""),
                        }
                    )
                    if len(pending) >= _EMBED_BATCH:
                        await flush()
    await flush()

    total_in_db = await embedding.count_precedents()
    print(
        f"\n완료 — 신규 {stats['collected']}건 / 중복 {stats['skipped_dup']} / "
        f"내용없음 {stats['skipped_empty']} / 실패 {stats['failed']}"
    )
    print(f"DB 총 적재: {total_in_db}건")


def main() -> None:
    parser = argparse.ArgumentParser(description="판례 코퍼스 수집·임베딩 적재")
    parser.add_argument(
        "--seeds", type=str, default=None, help="쉼표 구분 시드 (기본: 내장 24개)"
    )
    parser.add_argument(
        "--pages", type=int, default=3, help="시드당 페이지 수 (기본 3)"
    )
    parser.add_argument(
        "--display", type=int, default=100, help="페이지당 건수 (기본 100)"
    )
    parser.add_argument(
        "--delay", type=float, default=0.4, help="본문 조회 간격 초 (기본 0.4)"
    )
    args = parser.parse_args()

    seeds = [s.strip() for s in args.seeds.split(",")] if args.seeds else SEEDS
    try:
        asyncio.run(collect(seeds, args.pages, args.display, args.delay))
    except KeyboardInterrupt:
        print("\n중단됨 — 지금까지 적재분은 유지되며 재실행 시 이어서 수집합니다")
        sys.exit(1)


if __name__ == "__main__":
    main()
