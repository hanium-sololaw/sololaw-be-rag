# AGENTS.md — sololaw-be-rag (FastAPI AI 서버) Codex 작업 지침

> 상태: 문서 생성 도메인(`app/documents/`) 구현·배포 완료, CI/CD 운영 중. 판례 검색·증거 분석 도메인은 미착수. `(TBD)` 항목은 변경될 수 있다.

## 프로젝트 개요
나홀로 소송(변호사 없이 진행하는 민사소송)을 돕는 AI Agent의 **FastAPI 기반 AI 추론 서버**다.
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

회원가입/로그인, 소송 절차 안내, 마이페이지, 소송비용 계산 등은 Spring Boot 담당이며 본 서버 범위 밖이다.

## 기술 스택
- Framework: FastAPI + Uvicorn
- Package/venv: **uv** (Python 3.11+)
- AI/ML: LangChain, LangGraph (도입 예정)
- LLM: **OpenAI API** — 기본 모델 gpt-4o, `OPENAI_MODEL` 설정으로 교체 가능
- RAG: 벡터스토어 (FAISS 또는 pgvector) (TBD)
- Infra: AWS EC2(스프링과 공용 1대), Docker, GitHub Actions — **CI/CD 구축 완료**
- 설정: pydantic-settings + `.env`

## 현재 구조
**도메인 기반(feature module) 구조**를 유지한다. 각 도메인은 `app/<도메인>/` 폴더 하나에 router, schemas, service, generators, prompts를 자체 완결로 모은다. 레이어별 공통 폴더로 흩지 않는다.

- `app/core/` — 공통 설정/유틸 (`config.py` 등)
- `app/documents/` — 문서 생성 도메인 **구현·배포 완료**
  - 소장·준비서면·증거목록·신청서 4종 생성 + 증거 파일 자동 분석
  - `router.py`: 유형별 엔드포인트
  - `schemas/`: 유형별 입력·출력 스키마
  - `service.py`: 공용 SSE 파이프라인·섹션 파싱
  - `registry.py`: 유형→생성기 매핑
  - `generators/`: 유형별 OpenAI 스트리밍
  - `prompts/`: 유형별 프롬프트
  - `analyzer.py`: 증거 파일 분석. generate와 독립 흐름
- `app/shared/` — 도메인 공통 AI 인프라
  - `llm.py`: OpenAI 클라이언트, 지연 생성. 키 없이도 import 가능해야 CI 통과
  - `extract.py`: 업로드 파일 내용 추출. 이미지 base64, PDF 텍스트, TXT 디코딩
  - 파일은 저장하지 않는다. 무상태 구조를 유지하며, S3 등 저장은 스프링 담당
- 향후 도메인: `app/cases/`(판례 검색), `app/evidence/`(증거 분석) 등 동일 패턴
- 엔트리는 루트 `main.py` — 각 도메인 `router`를 `/api/v1` 아래로 `include_router`

배포 관련으로 `docker/`(Dockerfile·docker-compose.yml), `.github/workflows/`(ci.yml·cd.yml), 루트 `.dockerignore`가 있다.

## 문서 생성 도메인 규칙
새 문서 유형을 추가할 때는 `schemas/`, `generators/`, `prompts/`에 같은 이름 파일을 추가하고 `registry.py`에 한 줄 등록한다. 가능하면 `router.py`와 `service.py`는 변경하지 않는다.

생성 엔드포인트 공통 패턴은 **SSE 스트리밍**이다.

```text
delta(텍스트 조각) 여러 번 -> done(sections 구조화 + raw_text)
error
```

LLM이 고정 마크다운 헤더(`## 청구취지` 등)로 쓰도록 강제하고, 완료 시 generator의 `section_map`으로 파싱한다. 호증 번호 등 결정적 값은 AI에 맡기지 않고 코드에서 확정한다. 주민등록번호 등 민감정보는 LLM에 전달하지 않는다.

## 아키텍처 (잠정, TBD)
```text
사용자 입력 -> Supervisor Agent -> 판례 검색 Agent (RAG) -> 문서 생성 Agent -> 설명 Agent (XAI) -> 최종 출력
```

## 연동 (프론트 직접 호출)
- 프론트엔드가 본 FastAPI 서버를 **직접 호출**한다. AI 기능 한정이다.
- 로그인·CRUD는 프론트 → 스프링 흐름이다.
- 공개 base URL: `https://api.sololaw.site/rag`
- 호스트 nginx가 `/rag/` → `127.0.0.1:18000`으로 프록시하며 prefix를 제거한다.
- 이 때문에 `ROOT_PATH=/rag` 환경변수로 `FastAPI(root_path=...)`를 설정한다. Swagger `/docs` 경로 보정용이며 API 라우팅에는 영향 없다.
- Swagger: `https://api.sololaw.site/rag/docs`
- 본 서버가 외부에 직접 노출되므로 **CORS 설정 + 인증 토큰 검증**이 필요하다. JWT 키 공유 방식은 스프링과 협의 예정이다.
- Spring Boot ↔ FastAPI는 REST(JSON) 통신이다.
- 본 서버는 AI 추론 결과를 JSON 또는 SSE로 반환한다.
- 모든 AI 관련 로직은 본 FastAPI 서버에서 처리한다.

## 배포 / CI-CD
- 스프링 레포(`sololaw-be-spring`) CI/CD를 미러링하고, Java/Gradle을 Python(uv)로 치환한 구조다.
- 단일 EC2라 dev/prod를 나누지 않고 배포는 `main` 단일로 통합한다.
- 이미지: DockerHub `zmarzmar/sololaw-be-rag:latest`
- 서버: 공용 EC2 `/opt/sololaw-be-rag`
- 컨테이너: `sololaw-be-rag`
- 포트: `18000:8000`
- 외부 네트워크: `sololaw-network`(스프링과 공유, external)
- 흐름: `feature/*` 작업·push → `ci.yml` 자동 실행(Ruff + 빌드 검증, `main` 외 모든 브랜치 push 트리거, PR 이벤트 아님) → PR → `main` 머지 → `cd.yml`: 이미지 빌드·push → EC2 자동 배포
- 문서(`**.md`)만 변경 시 CI/CD 모두 스킵된다.
- 배포 설정값은 GitHub Secrets로 관리한다.
  - `DOCKER_USERNAME`
  - `DOCKER_PASSWORD`
  - `DOCKER_REPO`
  - `SSH_*`
  - `ENV_FILE`
- `ENV_FILE`이 배포 시 서버 `.env`로 떨어진다.
- 실제 값은 커밋하지 않는다.
- RAG 컨테이너만 뜨고 내리므로 스프링·postgres·redis에는 영향이 없도록 스코프가 격리되어 있다.

## 개발 규칙
- 브랜치: `main`, `feature/<기능명>`
- 작업은 feature 브랜치에서 진행한다.
- `main` 머지 시 자동 배포된다.
- 스프링은 `develop`도 쓰지만 RAG 배포는 `main` 단일이다.
- 환경변수는 `.env`로 관리한다.
- `.env.example`은 항상 최신으로 유지한다.
- 실제 키·시크릿은 커밋하지 않는다.
- 의존성은 `uv add`로 추가하고 `pyproject.toml` / `uv.lock`을 함께 커밋한다.

## 실행과 검증
로컬 실행:

```bash
uv sync
uv run uvicorn main:app --reload
```

코드 변경 후 가능한 검증:

```bash
uv run ruff check .
uv run python -m compileall app main.py
```

현재 명시적 테스트 디렉토리는 없다. 테스트가 추가되면 이 문서의 검증 명령도 함께 갱신한다.

## 커밋 메시지 규칙
커밋 메시지는 다음 형식을 따른다.

```text
{emoji} {Type}: 설명
```

설명은 한글로 작성한다. 조사 없이 명사형으로 간결하게 쓰고, 괄호를 넣지 않는다. 커밋 본문도 동일한 원칙을 따른다.

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

예시:

```text
✨ Feat: 판례 검색 엔드포인트 추가
✨ Feat: 신청서 자동 생성 구현
📝 Docs: Codex 작업 지침 추가
```

`(SSE 스트리밍)` 같은 괄호 표기는 사용하지 않는다.

## Codex 작업 방식
1. Plan: 변경 계획(파일 목록·주요 내용)을 먼저 제시한다.
2. Confirm: 사용자 승인 전에는 어떤 파일도 생성/수정하지 않는다.
3. Implement: 승인된 범위만 구현한다.
4. Review: 구현 후 변경된 파일 목록과 제안 커밋 메시지를 보여주고, 사용자 확인을 받는다.
5. Commit: 사용자 확인을 받은 뒤에만 커밋한다.
6. Push: 자동으로 push 하지 않는다. push는 사용자가 명시적으로 지시할 때만 수행한다.

추가 규칙:

- 요청하지 않은 디렉토리/파일을 임의로 만들지 않는다.
- 기존 사용자 변경사항을 되돌리지 않는다.
- `AGENTS.md` 자체를 수정할 때는 별도 브랜치를 만들지 않고 현재 브랜치에서 작업한다.
- `CLAUDE.md`는 Claude Code 작업 지침이고, `AGENTS.md`는 Codex 작업 지침이다.
- 프로젝트 구조, 배포 방식, 개발 규칙이 바뀌면 두 문서의 핵심 내용이 서로 어긋나지 않게 갱신한다.
