# CLAUDE.md — sololaw-be-rag (FastAPI AI 서버)

> 상태: 문서 생성(`app/documents/`)·판례 검색(`app/cases/`, 하이브리드 RAG 포함) 도메인 구현·배포 완료, CI/CD 운영 중. 증거 분석 도메인은 미착수. `(TBD)` 항목은 변경될 수 있음.

## 프로젝트 개요
나홀로 소송(변호사 없이 진행하는 민사소송)을 돕는 AI Agent의 **FastAPI 기반 AI 추론 서버**.
판례 검색·분석, 법률 문서 생성, 증거 분석 등 **AI 기능만** 담당한다.
사용자 인증·CRUD·통계 등은 별도 Spring Boot 서버가 담당하며, 본 서버는 AI 추론 결과만 반환한다.

## 담당 범위 (AI 파트)
| 도메인 | 기능 |
|---|---|
| 대시보드 | AI 제안 작업 생성 |
| 판례 검색 | AI 판례 검색/분석, 관련도 산출, 승소율 분석 |
| 문서 생성 | AI 문서 내용 생성 (소장/준비서면 등) |
| 증빙 자료 | AI 증거 분석/보완 제안 |
| 일정 관리 | 기일통지서 PDF → AI 추출 |

> 회원가입/로그인, 소송 절차 안내, 마이페이지, 소송비용 계산 등은 Spring Boot 담당 (본 서버 범위 밖).

## 기술 스택
- Framework: FastAPI + Uvicorn
- Package/venv: **uv** (Python 3.11+)
- AI/ML: LangChain, LangGraph (도입 예정)
- LLM: **OpenAI API** — 기본 모델 gpt-4o, `OPENAI_MODEL` 설정으로 교체 가능
- RAG: **pgvector** (RAG 전용 `vector-db` 컨테이너) + `text-embedding-3-small`(1536차원) — 판례 코퍼스 약 1,700건 적재·운영 중
- 판례·법령 데이터: **국가법령정보센터 Open API** (law.go.kr) — 인증키 `LAW_API_KEY`(OC)
- Infra: AWS EC2(스프링과 공용 1대), Docker, GitHub Actions — **CI/CD 구축 완료** (자세한 건 `## 배포 / CI-CD`)
- 설정: pydantic-settings + `.env`

## 현재 구조
**도메인 기반(feature module) 구조.** 각 도메인은 `app/<도메인>/` 폴더 하나에 router·schemas·service·generators·prompts를 자체 완결로 모은다 (레이어별로 흩지 않음).
- `app/core/` — 공통 설정/유틸 (`config.py` 등).
- `app/documents/` — 문서 생성 도메인 **(구현·배포 완료)**: 소장·준비서면·증거목록·신청서 4종 생성 + 증거 파일 자동 분석. 구성: `router.py`(유형별 엔드포인트), `schemas/`(유형별 입력·출력 스키마), `service.py`(공용 SSE 파이프라인·섹션 파싱), `registry.py`(유형→생성기 매핑), `generators/`(유형별 OpenAI 스트리밍), `prompts/`(유형별 프롬프트), `analyzer.py`(증거 파일 분석 — generate 와 독립 흐름). **새 문서 유형 = schemas/·generators/·prompts/에 같은 이름 파일 추가 + registry 한 줄 등록**, 라우터·서비스는 불변.
- 생성 엔드포인트 공통 패턴: **SSE 스트리밍** — `delta`(텍스트 조각)×N → `done`(`sections` 구조화 + `raw_text`) / `error`. LLM 이 고정 마크다운 헤더(`## 청구취지` 등)로 쓰도록 강제하고 완료 시 generator 의 `section_map` 으로 파싱한다. 호증 번호 등 결정적 값은 AI 에 맡기지 않고 코드에서 확정한다. 주민등록번호 등 민감정보는 LLM 에 전달하지 않는다.
- `app/shared/` — 도메인 공통 AI 인프라: `llm.py`(OpenAI 클라이언트, 지연 생성 — 키 없이도 import 가능해야 CI 통과), `extract.py`(업로드 파일 내용 추출 — 이미지 base64·PDF 텍스트·TXT 디코딩). 파일은 저장하지 않는다(무상태, S3 등 저장은 스프링 담당).
- `app/cases/` — 판례 검색 도메인 **(구현·배포 완료)**: 판례 검색 + 승소율 통계. 구성: `router.py`(`/cases/search`·`/cases/statistics`), `schemas.py`, `service.py`(**하이브리드 후보 확보 + 2단계 랭킹**), `client.py`(국가법령정보센터 API), `embedding.py`(pgvector 적재·유사도 검색), `statistics.py`(승소율 통계 + 1시간 TTL 인메모리 캐시), `prompts/`(rerank·relevance·keywords·outcome). 프론트 탭 2개(내 사건 기반/키워드 검색)가 같은 API 공용 — `query` 또는 `case_context` 중 하나 필수, 후자만 오면 LLM 이 검색 키워드 추출.
- 판례 검색 흐름: 후보를 **하이브리드**로 확보 — (a) law.go.kr 키워드 top-20(최신 판례 커버) + (b) 임베딩 코퍼스 유사도 top-20(용어 불일치 커버) → 판례일련번호 병합·중복 제거(벡터 후보는 코퍼스 본문 프리로드 재사용) → [예선] LLM 1회 일괄 채점(rubric) → 상위 limit 건만 [본선] 참고 포인트 생성. 벡터 저장소 미가용 시 키워드 검색만으로 폴백. 응답의 `similarity` 는 벡터 후보에만 제공("유사한 판례 N%" 게이지용).
- 판례 코퍼스: `scripts/collect_precedents.py` 로 수집(시드 24개 주제, 재실행 멱등 — 실패분 자동 재시도). EC2 실행: `docker exec -d sololaw-be-rag sh -c "python -u -m scripts.collect_precedents --pages 3 > /tmp/collect.log 2>&1"`. 판시사항·판결요지 없는 판례는 적재 제외. 코퍼스는 공개 판례 파생 데이터만 담는다(사용자 데이터 무관).
- 판례 도메인 원칙: 관련 법령은 판례 **참조조문의 정규식 집계**(AI 생성 아님). 승소율은 **검색 표본 기반 참고 지표** — 판단 불가(파기환송 등)는 비율에서 제외, 판단 가능 5건 미만이면 null, 응답의 `disclaimer` 는 프론트 필수 표시. 쟁점별 승소율은 소표본 왜곡으로 제외 확정. 상소심 승패는 상소비용 부담자로 상소인을 추론해 판정.
- 국가법령정보센터 API 주의: 신청 시 등록한 도메인을 **Referer 로 검증**(`LAW_API_REFERER`, 기본 `https://www.sololaw.site`) — 누락 시 "필수 입력값" 오류로 위장된 거부 응답이 온다.
- 향후 도메인: `app/evidence/`(증거 분석) 등 동일 패턴.
- 엔트리는 루트 `main.py` — 각 도메인 `router`를 `/api/v1` 아래로 `include_router`.

배포 관련으로 `docker/`(Dockerfile·docker-compose.yml), `.github/workflows/`(ci.yml·cd.yml), 루트 `.dockerignore`가 추가돼 있다.

## 아키텍처 (잠정, TBD)
사용자 입력 → Supervisor Agent → 판례 검색 Agent (RAG) → 문서 생성 Agent → 설명 Agent (XAI) → 최종 출력

## 연동 (프론트 직접 호출)
- 프론트엔드가 본 FastAPI 서버를 **직접 호출**한다 (AI 기능 한정). 로그인·CRUD는 프론트 → 스프링.
- 공개 base URL: `https://api.sololaw.site/rag` — 호스트 nginx 가 `/rag/` → `127.0.0.1:18000` 으로 프록시하며 prefix 를 제거한다. 이 때문에 `ROOT_PATH=/rag` 환경변수로 `FastAPI(root_path=...)` 를 설정한다 — Swagger `/docs` 경로 보정용, API 라우팅에는 영향 없음. Swagger: `https://api.sololaw.site/rag/docs`.
- 본 서버가 외부에 직접 노출되므로 **CORS 설정 + 인증 토큰 검증**이 필요. (JWT 키 공유 방식은 스프링과 협의 예정)
- Spring Boot ↔ FastAPI: REST(JSON) 통신.
- 본 서버는 AI 추론 결과를 JSON으로 반환한다.
- 모든 AI 관련 로직은 본 FastAPI 서버에서 처리.

## 배포 / CI-CD
- 스프링 레포(`sololaw-be-spring`) CI/CD를 미러링, Java/Gradle → Python(uv)로 치환. 단, **단일 EC2라 dev/prod를 나누지 않고 배포는 `main` 단일로 통합**.
- 이미지: DockerHub `zmarzmar/sololaw-be-rag:latest`. 서버: 공용 EC2 `/opt/sololaw-be-rag`, 컨테이너 `sololaw-be-rag`(포트 `18000:8000`) + `sololaw-rag-vector`(pgvector, 내부 전용·볼륨 영속·512m 제한), 외부 네트워크 `sololaw-network`(스프링과 공유, external).
- 흐름: `feature/*` 작업·push → `ci.yml` 자동 실행(Ruff + 빌드 검증, `main` 외 모든 브랜치 push 트리거 — PR 이벤트 아님) → PR → `main` 머지 → `cd.yml`: 이미지 빌드·push → EC2 자동 배포. 문서(`**.md`)만 변경 시 CI/CD 모두 스킵.
- 배포 설정값은 GitHub Secrets로 관리(`DOCKER_USERNAME/PASSWORD/REPO`, `SSH_*`, `ENV_FILE`). `ENV_FILE`이 배포 시 서버 `.env`로 떨어진다. **실제 값은 커밋 금지.**
- RAG 소유 컨테이너(app·vector-db)만 뜨고 내리므로 스프링·postgres·redis엔 영향 없음(스코프 격리). 배포 시 vector-db 도 재시작되지만 데이터는 볼륨(`vector_data`)에 유지.
- `ENV_FILE` 수정만 반영할 때는 커밋 없이 마지막 CD run 을 rerun 하면 된다(`gh run rerun`). **주의: ENV_FILE 를 수정할 때 다른 키 값을 지우지 않도록 전체 내용을 유지한 채 편집할 것** (과거 OPENAI_API_KEY 누락으로 전체 AI 기능 중단 사고 있었음).

## 개발 규칙
- 브랜치: `main`, `feature/<기능명>` — 작업은 feature 브랜치, `main` 머지 시 자동 배포(단일 EC2). (스프링은 `develop`도 쓰나 RAG 배포는 `main` 단일.)
- 커밋: `{emoji} {Type}: 설명` — **설명은 한글로 작성**
  | 이모지 | 타입 | 설명 |
  |---|---|---|
  | 🎉 | Start | Start new project |
  | ✨ | Feat | Add new feature |
  | 🐛 | Fix | Fix a bug |
  | 🎨 | Design | Change UI/CSS |
  | ♻️ | Refactor | Refactor code |
  | 🔧 | Settings | Change configuration files |
  | 🔥 | Remove | Delete files |
  | 📝 | Docs | Update documentation |
  - 예) `✨ Feat: 판례 검색 엔드포인트 추가`
  - 설명은 조사 없이 명사형으로 간결하게 쓰고, 괄호를 넣지 않는다. 커밋 본문도 동일. 예) `✨ Feat: 신청서 자동 생성 구현` — `(SSE 스트리밍)` 같은 괄호 표기 금지
- 환경변수는 `.env`로 관리, `.env.example` 항상 최신 유지. **실제 키·시크릿 커밋 금지.**
- 의존성은 `uv add`로 추가하고 `pyproject.toml` / `uv.lock` 커밋.

## Claude Code 작업 방식
1. Plan: 변경 계획(파일 목록·주요 내용)을 먼저 제시한다.
2. Confirm: 사용자 승인 전에는 어떤 파일도 생성/수정하지 않는다.
3. Implement: 승인된 범위만 구현한다.
4. Review: 구현 후 변경된 파일 목록과 제안 커밋 메시지를 보여주고, 사용자 확인을 받는다.
5. Commit: 사용자 확인을 받은 뒤에만 커밋한다.
6. Push: 자동으로 push 하지 않는다. push는 사용자가 명시적으로 지시할 때만 수행한다.
- 요청하지 않은 디렉토리/파일을 임의로 만들지 않는다.
- `CLAUDE.md` 자체를 수정할 때는 별도 브랜치를 만들지 않고 `main`에 직접 커밋한다.