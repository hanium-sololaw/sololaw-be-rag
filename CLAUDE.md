# CLAUDE.md — sololaw-be-rag (FastAPI AI 서버)

> 상태: 초기 세팅 단계. 패키지 구조는 아직 잡지 않음. `(TBD)` 항목은 변경될 수 있음.

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
- LLM: **OpenAI API**
- RAG: 벡터스토어 (FAISS 또는 pgvector) (TBD)
- Infra: AWS EC2(스프링과 공용 1대), Docker, GitHub Actions — **CI/CD 구축 완료** (자세한 건 `## 배포 / CI-CD`)
- 설정: pydantic-settings + `.env`

## 현재 구조
**도메인 기반(feature module) 구조.** 각 도메인은 `app/<도메인>/` 폴더 하나에 router·schemas·service·generators·prompts를 자체 완결로 모은다 (레이어별로 흩지 않음).
- `app/core/` — 공통 설정/유틸 (`config.py` 등).
- `app/documents/` — 문서 생성 도메인 (소장/준비서면/증거목록/신청서). 구성: `router.py`(API), `schemas.py`, `service.py`(오케스트레이션), `registry.py`(유형→생성기 매핑), `generators/`(유형별 생성 로직), `prompts/`(유형별 프롬프트). **새 문서 유형 = generators/·prompts/에 파일 추가 + registry 한 줄 등록**, 라우터·서비스는 불변.
- 향후 도메인: `app/cases/`(판례 검색), `app/evidence/`(증거 분석) 등 동일 패턴. 도메인 공통 AI 인프라(LLM/RAG/LangGraph)는 필요 시 `app/shared/`에 둔다.
- 엔트리는 루트 `main.py` — 각 도메인 `router`를 `/api/v1` 아래로 `include_router`.
- 초기라 도메인 파일은 스텁 + `# TODO` 위주(실제 LLM 로직 미구현).

배포 관련으로 `docker/`(Dockerfile·docker-compose.yml), `.github/workflows/`(ci.yml·cd.yml), 루트 `.dockerignore`가 추가돼 있다.

## 아키텍처 (잠정, TBD)
사용자 입력 → Supervisor Agent → 판례 검색 Agent (RAG) → 문서 생성 Agent → 설명 Agent (XAI) → 최종 출력

## 연동 (프론트 직접 호출)
- 프론트엔드가 본 FastAPI 서버를 **직접 호출**한다 (AI 기능 한정). 로그인·CRUD는 프론트 → 스프링.
- 본 서버가 외부에 직접 노출되므로 **CORS 설정 + 인증 토큰 검증**이 필요. (JWT 키 공유 방식은 스프링과 협의 예정)
- Spring Boot ↔ FastAPI: REST(JSON) 통신.
- 본 서버는 AI 추론 결과를 JSON으로 반환한다.
- 모든 AI 관련 로직은 본 FastAPI 서버에서 처리.

## 배포 / CI-CD
- 스프링 레포(`sololaw-be-spring`) CI/CD를 미러링, Java/Gradle → Python(uv)로 치환. 단, **단일 EC2라 dev/prod를 나누지 않고 배포는 `main` 단일로 통합**.
- 이미지: DockerHub `zmarzmar/sololaw-be-rag:latest`. 서버: 공용 EC2 `/opt/sololaw-be-rag`, 컨테이너 `sololaw-be-rag`, 포트 `18000:8000`, 외부 네트워크 `sololaw-network`(스프링과 공유, external).
- 흐름: `feature/*` 작업 → PR(`ci.yml`: Ruff + 빌드 검증) → `main` 머지 → `cd.yml`: 이미지 빌드·push → EC2 자동 배포.
- 배포 설정값은 GitHub Secrets로 관리(`DOCKER_USERNAME/PASSWORD/REPO`, `SSH_*`, `ENV_FILE`). `ENV_FILE`이 배포 시 서버 `.env`로 떨어진다. **실제 값은 커밋 금지.**
- RAG 컨테이너만 뜨고 내리므로 스프링·postgres·redis엔 영향 없음(스코프 격리).

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
- 환경변수는 `.env`로 관리, `.env.example` 항상 최신 유지. **실제 키·시크릿 커밋 금지.**
- 의존성은 `uv add`로 추가하고 `pyproject.toml` / `uv.lock` 커밋.

## Claude Code 작업 방식
1. Plan: 변경 계획(파일 목록·주요 내용)을 먼저 제시한다.
2. Confirm: 사용자 승인 전에는 어떤 파일도 생성/수정하지 않는다.
3. Implement: 승인된 범위만 구현한다.
4. Review: 구현 후 변경된 파일 목록과 제안 커밋 메시지를 보여주고, 사용자 확인을 받는다.
5. Commit: 사용자 확인을 받은 뒤에만 커밋한다.
6. Push: 자동으로 push 하지 않는다. push는 사용자가 명시적으로 지시할 때만 수행한다.
- 요청하지 않은 디렉토리/파일을 임의로 만들지 않는다. 초기엔 스텁/`# TODO` 위주.
- `CLAUDE.md` 자체를 수정할 때는 별도 브랜치를 만들지 않고 `main`에 직접 커밋한다.