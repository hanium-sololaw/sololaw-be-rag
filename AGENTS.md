# AGENTS.md — sololaw-be-rag (FastAPI AI 서버) Codex 작업 지침

> 상태: 문서 생성(`app/documents/`)·판례 검색(`app/cases/`, 하이브리드 RAG 포함) 도메인 구현·배포 완료, CI/CD 운영 중. 문서 생성 4종과 판례 검색 화면 대조·연동 문서 전달 완료는 `CLAUDE.md`의 2026-08-22 기록 기준이다. 대시보드 AI 제안·기일통지서 PDF 추출·독립 증거 분석 도메인은 미착수. **JWT 검증 미구현 — 우선 과제.** `(TBD)` 항목은 변경될 수 있다.

## 프로젝트 개요
나홀로 소송(변호사 없이 진행하는 민사소송)을 돕는 AI Agent의 **FastAPI 기반 AI 추론 서버**다.
판례 검색·분석, 법률 문서 생성, 증거 분석 등 **AI 기능만** 담당한다.
사용자 인증·CRUD·통계 등은 별도 Spring Boot 서버가 담당하며, 본 서버는 AI 추론 결과만 반환한다.

## 담당 범위 (AI 파트)
| 도메인 | 기능 |
|---|---|
| 대시보드 | AI 제안 작업 생성 |
| 판례 검색 | AI 판례 검색/분석, 관련도 산출, 판례별 승패 판정, 승소율 분석, 관련 법령 집계 |
| 문서 생성 | AI 문서 내용 생성 (소장·준비서면·증거목록·신청서) |
| 증빙 자료 | AI 증거 분석/보완 제안 |
| 일정 관리 | 기일통지서 PDF → AI 추출 |

회원가입/로그인, 소송 절차 안내, 마이페이지, 소송비용 계산 등은 Spring Boot 담당이며 본 서버 범위 밖이다.

## 기술 스택
- Framework: FastAPI + Uvicorn
- Package/venv: **uv** (Python 3.11+)
- AI/ML: LangChain, LangGraph (도입 예정)
- LLM: **OpenAI API** — 기본 모델 gpt-4o, `OPENAI_MODEL` 설정으로 교체 가능
- RAG: **pgvector** — RAG 전용 `vector-db` 컨테이너, 기본 임베딩 모델 `text-embedding-3-small`(1536차원)
- 판례·법령 데이터: **국가법령정보센터 Open API**(law.go.kr), 인증키 `LAW_API_KEY`(OC)
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
- `app/cases/` — 판례 검색 도메인 **구현·배포 완료**
  - `router.py`, `schemas.py`: 검색 엔드포인트·요청/응답
  - `service.py`: 하이브리드 후보 확보·2단계 랭킹·승패 분류·통계
  - `client.py`: 국가법령정보센터 판례·본문·조문 제목 조회
  - `embedding.py`: pgvector 적재·유사도 검색
  - `prompts/`: rerank·relevance·keywords·outcome
- `scripts/collect_precedents.py` — 공개 판례 코퍼스 수집·적재
- 향후 도메인: `app/evidence/`(독립 증거 분석) 등 동일 패턴
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

### 문서 유형별 구현 규칙
- `schemas/common.py`의 `Party`·`CitedPrecedent`를 소장·신청서가 공유한다. 당사자 호칭은 문서별 프롬프트에서 정한다.
- 소장 유형은 `deposit_return`·`loan_return`·`wage_claim`·`damages`·`building_surrender` 5종이다. 유형별 사실관계는 `facts: dict[str, str]`로 받되 날짜·금액 등 결정적 값은 명시 필드로 둔다.
- 건물명도는 금전 청구와 달리 인도 청구·인도 완료일까지의 차임 상당액·부동산 표시 `annex`를 사용한다. 유형별 청구취지·지연손해금·기산일 분기를 보존하고, 변경 시 해당 프롬프트를 확인한다.
- 신청서 유형은 `payment_order`·`litigation_aid`·`lease_registration`·`enforcement`·`provisional_seizure` 5종이다. `SPECS`의 제목·호칭·섹션 순서·작성 규칙을 공통 프롬프트에 주입한다.
- 신청서는 유형마다 섹션이 달라 `section_map = None`을 사용한다. `_parse_sections`가 마크다운 헤더를 그대로 응답 키로 쓰므로 고정 섹션 매핑을 강제하지 않는다.
- 준비서면은 `RebuttalPoint` 단위로 상대 주장·반박·증거·인용 판례를 묶는다. `agent`의 줄머리는 `submitter_role`에 따라 코드에서 확정한다.
- 증거목록은 호증·제목·작성자·작성일·입증취지·원본/사본의 6열 표다. `panel`을 포함한 법원 수신처를 준비서면과 일치시킨다.
- 호증 번호는 사건 전체에서 이어진다. 준비서면·증거목록의 `evidence_start_no`를 받아 코드에서 확정하며 접두어는 원고 `갑`, 피고 `을`, 참가인 `병`이다. 기존 사건의 마지막 번호 관리는 스프링·프론트 담당이다.
- Pydantic의 기본 `extra="ignore"` 때문에 스키마에 없는 입력은 조용히 버려질 수 있다. 화면 입력 변경 시 스키마·프롬프트 전달까지 함께 확인한다.
- 스프링 신청서 enum 충돌은 **2026-08-22 기준 확인 대기 기록**이다. 당시 `DATE_CHANGE`·`DOC_DISPATCH`·`CORRECTION`·`LITIGATION_AID` 중 AI 서버와 겹치는 것은 `litigation_aid`뿐이었다. 연동 변경 전 최신 스프링 계약을 확인한다.

## 판례 검색 도메인 규칙
- 엔드포인트는 **`POST /api/v1/cases/search` 하나**다. 내 사건 기반 탭·키워드 검색 탭이 공용으로 사용한다. `query` 또는 `case_context` 중 하나가 필수이며, 사건 설명만 오면 LLM이 키워드를 추출한다. 둘 다 있으면 검색은 `query`, 관련도는 `case_context`를 기준으로 한다.
- 후보 확보: law.go.kr 키워드 top-20 + 코퍼스 벡터 유사도 top-20 → 판례일련번호 병합·중복 제거 → LLM 일괄 관련도 채점 → 상위 `limit`건 참고 포인트 생성·승패 분류. 벡터 후보의 코퍼스 본문은 재사용한다.
- 벡터 저장소 미설정·미가용 시 키워드 검색으로 폴백한다. `similarity`는 벡터 후보에만 제공하며 키워드 후보는 `null`일 수 있다.
- `search_cases`는 키워드 확정 후 `compute_statistics`를 `create_task`로 시작하고 검색 결과와 함께 반환한다. 별도 `/cases/statistics` 엔드포인트는 없다. 통계 실패 시 `statistics: null`로 카드·법령을 반환한다.
- 카드와 통계는 같은 `classify_outcomes`를 쓴다. 주문을 근거로 `win`·`partial`·`lose`·`unknown`을 판정한다. 코퍼스에 주문이 없으므로 본선 후보 중 필요한 판례만 원문을 재조회한다. 판단 불가를 추측으로 채우지 않으며 프론트는 `unknown` 배지를 숨긴다.
- 승소율은 `(win + partial) / classified * 100`이다. 판단 불가를 분모에서 제외하고 판단 가능 5건 미만이면 `null`이다. 전국 통계나 개인 사건 예측값이 아닌 **검색 표본 참고 지표**이며 응답 `disclaimer`를 프론트에 필수 표시한다. 쟁점별 승소율은 제공하지 않는다.
- 카드의 `limit`과 통계의 `sample_size`는 별개다. 통계는 같은 조건에 대해 1시간 캐시한다.
- 필터는 `civil`·`loan`·`lease`, 미지정·빈값은 전체다. 대여금·임대차는 민사 사건종류와 사건명 키워드로 좁히므로 결과가 0건일 수 있다. 통계 후보는 필터링 전 `sample_size * 3`을 요청하되 API 상한 100건을 적용한다.
- 관련 법령은 참조조문 **정규식 집계**이며 AI가 생성하지 않는다. 조문 제목은 국가법령정보센터에서 조회하고 프로세스 메모리에 캐시한다. 조회 실패 시 `title: null`이다. JO 코드는 조 4자리 + 가지 2자리다.
- 국가법령정보센터의 Referer 검증에 맞춰 `LAW_API_REFERER`를 사용한다. 기본값은 `https://www.sololaw.site`이며 신청 시 등록한 도메인과 일치해야 한다.
- Swagger의 이름 붙은 요청 예시는 `Body(openapi_examples=...)`에 둔다. Pydantic `json_schema_extra`의 `examples`에 `{summary, value}` 래퍼를 넣지 않는다.

### 판례 코퍼스 운영
- 수집 스크립트는 24개 주제를 시드로 사용하고 이미 적재된 판례는 건너뛴다. 판시사항·판결요지가 없는 판례는 제외한다. 사용자 데이터가 아닌 공개 판례 파생 데이터만 적재한다.
- **4,524건은 `CLAUDE.md`의 2026-08-19 기준 기록**이다. 현재 적재 건수로 단정하지 않고 필요 시 DB에서 확인한다.
- EC2에서 백그라운드 수집하는 예시:

```bash
docker exec -d sololaw-be-rag sh -c "python -u -m scripts.collect_precedents --pages 3 > /tmp/collect.log 2>&1"
```

- 수집 중 배포하면 앱 컨테이너 재시작으로 작업이 종료되므로 머지를 피한다. 중단 후 재실행하면 이미 적재된 판례는 건너뛴다.

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
- CORS는 설정되어 있으나 **JWT 토큰 검증은 미구현**이다. 스프링의 서명 알고리즘·키 공유 방식·클레임 구조를 확인한 뒤 검증을 추가해야 한다.
- 실제 흐름은 **프론트 → AI 서버 생성·검색 → 프론트 → 스프링 저장**이다. 스프링이 AI 서버를 호출하거나 SSE를 중계하는 구조가 아니다.
- 저장·결정적 비용 계산·회원 인증은 스프링 담당이며 AI 서버는 자체 API의 접근 토큰을 검증해야 한다.
- AI 서버는 snake_case, 스프링은 camelCase를 사용하며 변환은 프론트가 담당한다.
- 본 서버는 AI 추론 결과를 JSON 또는 SSE로 반환한다.
- 모든 AI 관련 로직은 본 FastAPI 서버에서 처리한다.

### 연동 문서
- `CLAUDE.md` 기준 2026-08-22에 노션 9쪽을 전달했다. 공통 1쪽·문서 생성 6쪽·판례 검색 2쪽이며 원본은 `~/Desktop/sololaw-docs/`에 있다.
- 스키마·엔드포인트 변경 시 관련 원본 문서의 필드 표·`sections` 키·API 경로도 함께 갱신한다. 스프링 문서 생성 공통은 `documents-spring.md`, 신청서 enum 관련 내용은 `application-spring.md`다.
- 외부 연동 상태·화면 검증 기록은 위 날짜 기준이다. 후속 작업에서는 최신 계약을 확인한다.

## 배포 / CI-CD
- 스프링 레포(`sololaw-be-spring`) CI/CD를 미러링하고, Java/Gradle을 Python(uv)로 치환한 구조다.
- 단일 EC2라 dev/prod를 나누지 않고 배포는 `main` 단일로 통합한다.
- 이미지: DockerHub `zmarzmar/sololaw-be-rag:latest`
- 서버: 공용 EC2 `/opt/sololaw-be-rag`
- 컨테이너: `sololaw-be-rag` + `sololaw-rag-vector`
- 벡터 DB: 호스트 포트 미공개, 메모리 제한 512m, `vector_data` 볼륨으로 영속화
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
- RAG 소유 `app`·`vector-db`만 배포 대상으로 삼는다. 스프링·스프링 postgres·redis에는 영향이 없도록 스코프를 격리한다. 벡터 DB도 재시작되지만 데이터는 `vector_data`에 유지된다.
- 연속 머지로 CD가 겹치면 컨테이너 재시작이 충돌할 수 있으므로 배포 완료 후 다음 머지를 진행한다. 배포 결과는 실행 로그뿐 아니라 공개 `/rag/openapi.json`으로도 확인한다.
- `ENV_FILE`만 변경할 때는 마지막 CD run을 `gh run rerun`으로 재실행할 수 있다. 편집 시 다른 키를 누락하지 않도록 전체 내용을 유지한다.

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
uv run ruff format --check .
uv run python -m compileall app main.py
uv run python -c "import main"
```

- 현재 명시적 테스트 디렉토리는 없다. 테스트가 추가되면 이 문서의 검증 명령도 함께 갱신한다.
- CI는 Ruff lint·format 검사와 `uv sync --frozen` 후 `import main` 검증을 수행한다. OpenAI 키 없이도 import가 가능해야 한다.
- 순수 로직은 인라인 Python 점검으로 확인할 수 있다. 프롬프트·응답 변경은 실제 OpenAI 호출로 확인하며 수행 여부와 결과를 보고한다.
- `VECTOR_DB_URL`이 없는 환경에서는 키워드 폴백만 검증된다. 하이브리드 경로는 벡터 DB가 연결된 환경에서 확인하고, 응답 `similarity`와 주문 재조회 경로를 점검한다.
- 문서만 변경할 때는 문서 대조와 `git diff --check`로 검증한다.

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
