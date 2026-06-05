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
- Infra: AWS EC2 / S3, Docker, GitHub Actions (추후)
- 설정: pydantic-settings + `.env`

## 현재 구조 (최소)
루트에 `main.py` 단일 파일부터 시작. `app/` 패키지 구조(agents/rag/services 등)는
기능을 붙이면서 점진적으로 도입한다. 지금은 디렉토리를 만들지 않는다.

## 아키텍처 (잠정, TBD)
사용자 입력 → Supervisor Agent → 판례 검색 Agent (RAG) → 문서 생성 Agent → 설명 Agent (XAI) → 최종 출력

## 연동 (요청 유입 경로 TBD)
- Spring Boot ↔ FastAPI: REST(JSON) 통신.
- 요청 유입 경로는 미정: ① Spring이 사용자 요청을 받아 본 서버로 전달하거나, ② 클라이언트 요청이 본 FastAPI 서버로 직접 들어올 수도 있음.
- 어느 경우든 본 서버는 AI 추론 결과를 JSON으로 반환한다.
- 모든 AI 관련 로직은 본 FastAPI 서버에서 처리.

## 개발 규칙
- 브랜치: `main`, `develop`, `feature/<기능명>` (스프링 레포와 동일)
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