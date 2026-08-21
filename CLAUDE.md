# CLAUDE.md — sololaw-be-rag (FastAPI AI 서버)

> 상태: 문서 생성(`app/documents/`)·판례 검색(`app/cases/`, 하이브리드 RAG 포함) 도메인 구현·배포 완료, CI/CD 운영 중. **문서 생성 4종과 판례 검색 모두 화면 대조·검증 완료, 연동 문서 9쪽 노션 전달 완료(2026-08-22).** 대시보드 AI 제안·기일통지서 PDF 추출 도메인은 미착수. **인증(JWT) 미구현 — 최우선 과제.** `(TBD)` 항목은 변경될 수 있음.

## 프로젝트 개요
나홀로 소송(변호사 없이 진행하는 민사소송)을 돕는 AI Agent의 **FastAPI 기반 AI 추론 서버**.
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

> 회원가입/로그인, 소송 절차 안내, 마이페이지, 소송비용 계산 등은 Spring Boot 담당 (본 서버 범위 밖).

## 기술 스택
- Framework: FastAPI + Uvicorn
- Package/venv: **uv** (Python 3.11+)
- AI/ML: LangChain, LangGraph (도입 예정)
- LLM: **OpenAI API** — 기본 모델 gpt-4o, `OPENAI_MODEL` 설정으로 교체 가능
- RAG: **pgvector** (RAG 전용 `vector-db` 컨테이너) + `text-embedding-3-small`(1536차원) — 판례 코퍼스 약 4,500건 적재·운영 중
- 판례·법령 데이터: **국가법령정보센터 Open API** (law.go.kr) — 인증키 `LAW_API_KEY`(OC)
- Infra: AWS EC2(스프링과 공용 1대), Docker, GitHub Actions — **CI/CD 구축 완료** (자세한 건 `## 배포 / CI-CD`)
- 설정: pydantic-settings + `.env`

## 현재 구조
**도메인 기반(feature module) 구조.** 각 도메인은 `app/<도메인>/` 폴더 하나에 router·schemas·service·generators·prompts를 자체 완결로 모은다 (레이어별로 흩지 않음).
- `app/core/` — 공통 설정/유틸 (`config.py` 등).
- `app/documents/` — 문서 생성 도메인 **(구현·배포 완료)**: 소장·준비서면·증거목록·신청서 4종 생성 + 증거 파일 자동 분석. 구성: `router.py`(유형별 엔드포인트), `schemas/`(유형별 입력·출력 스키마), `service.py`(공용 SSE 파이프라인·섹션 파싱), `registry.py`(유형→생성기 매핑), `generators/`(유형별 OpenAI 스트리밍), `prompts/`(유형별 프롬프트), `analyzer.py`(증거 파일 분석 — generate 와 독립 흐름). **새 문서 유형 = schemas/·generators/·prompts/에 같은 이름 파일 추가 + registry 한 줄 등록**, 라우터·서비스는 불변.
- 생성 엔드포인트 공통 패턴: **SSE 스트리밍** — `delta`(텍스트 조각)×N → `done`(`sections` 구조화 + `raw_text`) / `error`. LLM 이 고정 마크다운 헤더(`## 청구취지` 등)로 쓰도록 강제하고 완료 시 generator 의 `section_map` 으로 파싱한다. 호증 번호 등 결정적 값은 AI 에 맡기지 않고 코드에서 확정한다. 주민등록번호 등 민감정보는 LLM 에 전달하지 않는다.
- **4종 모두 화면 대조 완료.** 디자이너 프로토타입(`naholo-law-test.vercel.app`)에서 위저드와 완성본을 확인해 맞췄다. 그 사이트는 규칙 기반 목업이라 참고용이고, 실제 생성은 본 서버가 한다.
- `Party`·`CitedPrecedent` 는 `schemas/common.py` 공용 — 소장·신청서가 함께 쓴다. 당사자 호칭(원고·채권자·신청인·임차인)은 문서마다 다르지만 담기는 정보가 같아 한 모델을 공유하고, 호칭은 프롬프트가 붙인다.
- 소장(`complaint`)은 위저드(자가진단 → 정보입력 1~6단계)에 맞춰 정비 완료. 소송 유형 5종(`deposit_return`·`loan_return`·`wage_claim`·`damages`·`building_surrender`)이 화면과 1:1.
- 신청서(`application`)는 **절차적 목적**으로 갈리는 5종 — `payment_order`·`litigation_aid`·`lease_registration`·`enforcement`·`provisional_seizure`. 종류마다 완성 문서의 섹션 구성이 달라 **`section_map = None` 으로 두고 마크다운 헤더를 그대로 키로 파싱**한다(`_parse_sections` 의 동적 모드). 프롬프트는 하나만 두고 종류별 스펙(`SPECS`: 제목·당사자 호칭·섹션 순서·작성 규칙)을 시스템 프롬프트에 주입한다. 강제집행에는 신청이유가 없고, 임차권등기명령에는 `관련 법리`(인용 판례)·`별지` 가, 가압류에는 별개 서면인 `가압류신청 진술서`(재민 2003-4 양식, 가·나·다 물음 고정)가 붙는다. **⚠️ 스프링 `ApplicationSubtype`(PR #10)은 `DATE_CHANGE`·`DOC_DISPATCH`·`CORRECTION`·`LITIGATION_AID` 4종이라 `litigation_aid` 하나만 겹친다.** 이대로면 프론트가 생성받은 신청서 5종 중 4종을 스프링에 저장할 수 없다. 어느 쪽이 화면 기준인지 확인 대기 중(2026-08-22 노션으로 전달).
- 준비서면(`brief`)은 **쟁점 단위 구조**다 — `RebuttalPoint`(상대 주장·반박·근거 증거·인용 판례) 하나가 문서의 "가.", "나." 항목이 된다. 상대 서면 종류·도달일로 "2026. 8. 7.자 준비서면(1)에서" 를 특정하고, `defenses`(항변 종류)·`undisputed_facts`(다툼 없는 사실)로 쟁점을 정리한다. 대리인(`agent`)은 민사소송법 제274조 제1항의 기재사항이라 당사자 표시 마지막 줄에 들어가는데, **줄머리(`원고`/`피고`)가 `submitter_role` 로 정해지는 결정적 값이라 코드에서 `원고 소송대리인  변호사 ○○○` 까지 완성해 프롬프트에 넘긴다.** 프롬프트에 `{제출자}` 플레이스홀더로 맡겼더니 LLM 이 리터럴로 옮겨 적거나 위치 설명("피고 줄 아래")을 줄머리로 오해했다.
- 증거목록(`evidence_list`)은 민사소송규칙 제105조 제1항이 요구하는 **제목·작성자·작성일**에 입증취지와 원본/사본 구별을 더한 표(6열)다. 법에서는 「증거설명서」라 부른다. 재판부(`panel`)를 받아 관할법원을 "○○법원 ○○재판부 귀중" 으로 쓴다 — 준비서면과 같은 사건에 함께 내는 서면이라 수신처 표기가 갈리면 안 된다.
- **화면 대조 완료** — 소장 5종 위저드·신청서 5종·준비서면 4단계·증거목록 3단계 모두 일치. 2026-08-19 에 찾은 미반영 필드 2건(`BriefInput.agent`·`EvidenceListInput.panel`)은 2026-08-22 반영·배포했다. Pydantic 기본값이 `extra="ignore"` 라 **스키마에 없는 필드는 422 없이 조용히 버려진다** — 화면에 칸이 생기면 스키마에도 자리를 만들어야 하고, 안 그러면 프론트·백 양쪽이 누락을 눈치채지 못한다.
- **유형별 사실관계는 `facts: dict[str, str]` 로 받는다** — 3~4단계 질문이 유형마다 7~14개씩 다르다. 판별 유니온 스키마 5개를 만드는 대신 `{화면 항목: 답}` 을 그대로 담아 프롬프트에 나열한다. 화면 문구가 바뀌어도 백엔드는 불변. 대신 **날짜·금액 등 결정적 값은 명시 필드로 뺀다**(`demand_date` 등).
- 청구취지는 **금전 청구와 인도 청구로 분기**한다. 건물명도(`building_surrender`)만 1항이 "별지 목록 기재 부동산을 인도하라"이고, 2항은 미납 차임에 더해 **인도 완료일까지의 차임 상당액**을 함께 구한다. 건물명도는 `annex`(별지 — 부동산의 표시)가 붙고, 나머지 유형은 "해당 없음".
- **지연손해금은 원칙적으로 2단 구조**다 — "…부터 소장 부본 송달일까지는 연 5%(민법 법정이율), 그 다음 날부터 연 12%(소송촉진법)". 기산일은 소송 유형마다 다르다: 대여금=변제기 다음 날, 임대차보증금=목적물 인도일, 손해배상=불법행위일, 임금체불=퇴직일+14일 다음 날, 건물명도=소장 송달 다음 날. **임금체불은 퇴사한 경우에만 연 20% 단일**(근로기준법 제37조는 퇴직 근로자 대상)이고 재직 중이면 2단 구조를 쓴다.
- 손해배상은 사건명에 **법원 사건부호**를 붙인다 — `손해배상(기)`·`(자)`·`(산)`·`(의)`. 계약 관계 유무로 불법행위(민법 750조)와 채무불이행(390조) 중 책임 구성이 갈린다. 둘 다 화면 3단계에서 고르는 값이라 `facts` 로 들어온다.
- **호증 번호는 사건 전체에서 이어진다**(민사소송규칙 제107조 제2항, 제출 순서대로). 소장에서 갑 제6호증까지 냈으면 준비서면은 7부터다. AI 에 맡기지 않고 `evidence_start_no` 를 받아 코드에서 확정해 프롬프트에 넣는다(`numbered_evidence`). 접두어는 제출자 지위가 정한다 — 원고 `갑`, 피고 `을`, 참가인 `병`. 사건 기록을 세는 것은 본 서버 범위 밖(스프링·프론트)이며, 안 받으면 매번 1번부터 다시 매겨져 번호가 겹친다.
- 줄머리 번호 관행이 문서마다 다르다 — 소장의 입증방법·첨부서류는 모두 `1.` 로 쓰고 호증 번호만 올리지만, 준비서면 입증방법은 `1. 2. 3.` 순번이다. 청구취지는 항상 순번.
- 소송비용(인지대·송달료·소가) 계산은 본 서버 범위 밖이다. 화면 1단계에 자동계산 박스가 있으나 스프링 담당.
- `app/shared/` — 도메인 공통 AI 인프라: `llm.py`(OpenAI 클라이언트, 지연 생성 — 키 없이도 import 가능해야 CI 통과), `extract.py`(업로드 파일 내용 추출 — 이미지 base64·PDF 텍스트·TXT 디코딩). 파일은 저장하지 않는다(무상태, S3 등 저장은 스프링 담당).
- `app/cases/` — 판례 검색 도메인 **(구현·배포 완료, 피그마 화면 대조 완료)**: 엔드포인트는 **`/cases/search` 하나뿐**이다. 구성: `router.py`, `schemas.py`, `service.py`(**하이브리드 후보 확보 + 2단계 랭킹 + 승패 분류 + 승소율 통계**), `client.py`(국가법령정보센터 API — 판례 검색·본문·조문 제목), `embedding.py`(pgvector 적재·유사도 검색), `prompts/`(rerank·relevance·keywords·outcome). 프론트 탭 2개(내 사건 기반/키워드 검색)가 같은 API 공용 — `query` 또는 `case_context` 중 하나 필수, 후자만 오면 LLM 이 검색 키워드 추출.
- 판례 검색 흐름: 후보를 **하이브리드**로 확보 — (a) law.go.kr 키워드 top-20(최신 판례 커버) + (b) 임베딩 코퍼스 유사도 top-20(용어 불일치 커버) → 판례일련번호 병합·중복 제거(벡터 후보는 코퍼스 본문 프리로드 재사용) → [예선] LLM 1회 일괄 채점(rubric) → 상위 limit 건만 [본선] 참고 포인트 생성 + 승패 분류. 벡터 저장소 미가용 시 키워드 검색만으로 폴백. 응답의 `similarity` 는 벡터 후보에만 제공.
- **검색과 승소율 통계는 한 응답으로 나간다** — `/cases/statistics` 는 제거했다. `search_cases` 가 키워드 확정 후 `compute_statistics` 를 `create_task` 로 먼저 띄우고 마지막에 거둔다. 벽시계 시간은 따로 부르던 때와 같고, 키워드 추출(LLM)이 한 번만 돌아 카드와 통계가 같은 기준을 쓴다. 통계 실패 시 `statistics: null` 로 카드·법령은 정상 반환.
- 승패(`outcome`)는 카드 배지와 승소율 통계가 **같은 분류기**(`classify_outcomes`)를 쓴다. 판정 근거는 **주문**인데 임베딩 코퍼스에는 주문이 없어, 본선 진출작 중 주문이 빠진 건만 law.go.kr 에서 재조회한다. 상고심은 상소인이 불분명해 `unknown` 이 흔하다 — 추측하지 않는 게 의도된 동작이고 프론트는 배지를 그리지 않는다.
- **승소율은 일부 승소를 포함해 계산한다**(`(win+partial)/classified`). 민사는 일부 인용이 다수라 전부 승소만 세면 실제보다 크게 낮게 나온다(실측: 손해배상 판단 13건 중 승 2·일부 10 → 제외 시 15%). 판단 가능 5건 미만이면 `null`.
- 필터 칩(`category`)은 화면과 1:1 — `civil`(민사)·`loan`(대여금)·`lease`(임대차), 빈값이면 전체. 대여금·임대차는 사건종류명이 아니라 민사 안의 **주제**라 사건종류명 + 사건명 키워드 2단으로 거른다(`matches_category`). 후보를 좁히므로 **결과가 0건일 수 있다.** 통계 표본은 필터로 줄어들 것을 감안해 `sample_size * 3` 만큼 받아 필터 후 자른다.
- 관련 법령은 참조조문 정규식 집계에 더해 **조문 제목**까지 붙인다(`민법 제618조 (임대차의 의의)`). 법령명으로 MST 조회 후 JO 코드(조 4자리 + 가지 2자리, 제3조의2 = `000302`)로 조문 단위를 받는다. 프로세스 메모리 캐시. 조회 실패 시 `title: null`.
- Swagger 에서 **이름 붙은 요청 예시는 `Body(openapi_examples=...)` 에 둔다.** Pydantic `json_schema_extra` 의 `examples` 에 `{summary, value}` 를 넣으면 그 래퍼째로 요청 본문이 되어 422 가 난다(과거 사고).
- 판례 코퍼스: `scripts/collect_precedents.py` 로 수집(시드 24개 주제, 재실행 멱등 — 이미 적재된 판례는 건너뛴다). 2026-08-19 기준 4,524건. `--pages 10` 기준 3~5시간 걸리고 `docker exec -d` 로 붙이면 SSH 가 끊겨도 계속 돈다. **다만 배포하면 컨테이너가 재시작돼 죽으므로 수집 중에는 머지를 피한다**(멱등이라 다시 돌리면 이어서 한다). EC2 실행: `docker exec -d sololaw-be-rag sh -c "python -u -m scripts.collect_precedents --pages 3 > /tmp/collect.log 2>&1"`. 판시사항·판결요지 없는 판례는 적재 제외. 코퍼스는 공개 판례 파생 데이터만 담는다(사용자 데이터 무관).
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
- 본 서버가 외부에 직접 노출되므로 **CORS 설정 + 인증 토큰 검증**이 필요. **⚠️ 현재 토큰 검증이 없어 누구나 호출 가능하고 호출마다 OpenAI 비용이 나간다.** 스프링에서 JWT 서명 알고리즘·키 공유 방식·클레임 구조를 받으면 검증만 붙이면 된다 — 최우선 과제.
- **스프링은 본 서버를 호출하지 않는다.** 흐름은 `프론트 → AI 서버(생성·검색) → 프론트 → 스프링(저장)`. 문서 생성이 SSE 스트리밍이라 스프링이 중계하면 실시간 타이핑이 깨지고 커넥션이 10초씩 묶인다. 스프링이 만들 건 전부 평범한 CRUD 다.
- 역할 분리 원칙: **저장·계산·인증은 전부 스프링.** 본 서버는 무상태다 — 파일도 임시저장도 보관하지 않고, 인지대·송달료 같은 결정적 계산도 하지 않는다. 판단이 필요한 것만 담당한다.
- 표기법: 본 서버는 snake_case, 스프링은 camelCase. **변환은 프론트가 한다.**
- 본 서버는 AI 추론 결과를 JSON으로 반환한다.
- 모든 AI 관련 로직은 본 FastAPI 서버에서 처리.
- **연동 문서는 노션 9쪽**(2026-08-22 전달) — `AI 서버 연동 — 공통 사항` 1쪽 + 문서 생성 6쪽(스프링 2·프론트 4) + 판례 검색 2쪽. 원본 마크다운은 `~/Desktop/sololaw-docs/`. 스키마·엔드포인트를 바꾸면 해당 쪽도 같이 고쳐야 한다 — 필드 표·`sections` 키·API 경로가 코드와 1:1로 적혀 있다. 스프링용은 4종 공통 1쪽(`documents-spring.md`)에 모여 있고 신청서만 enum 충돌 때문에 따로 뺐다(`application-spring.md`).
- 노션 퍼블릭 사이트(`*.notion.site`)는 **CDN 캐시가 남아 옛 내용이 보일 수 있다** — 갱신 확인은 `?cb=<임의값>` 을 붙여 캐시를 우회한다. 또 JS 렌더링이라 단순 fetch 로는 "Notion" 한 단어만 나오므로 브라우저로 읽어야 한다.

## 배포 / CI-CD
- 스프링 레포(`sololaw-be-spring`) CI/CD를 미러링, Java/Gradle → Python(uv)로 치환. 단, **단일 EC2라 dev/prod를 나누지 않고 배포는 `main` 단일로 통합**.
- 이미지: DockerHub `zmarzmar/sololaw-be-rag:latest`. 서버: 공용 EC2 `/opt/sololaw-be-rag`, 컨테이너 `sololaw-be-rag`(포트 `18000:8000`) + `sololaw-rag-vector`(pgvector, 내부 전용·볼륨 영속·512m 제한), 외부 네트워크 `sololaw-network`(스프링과 공유, external).
- 흐름: `feature/*` 작업·push → `ci.yml` 자동 실행(Ruff + 빌드 검증, `main` 외 모든 브랜치 push 트리거 — PR 이벤트 아님) → PR → `main` 머지 → `cd.yml`: 이미지 빌드·push → EC2 자동 배포. 문서(`**.md`)만 변경 시 CI/CD 모두 스킵.
- 배포 설정값은 GitHub Secrets로 관리(`DOCKER_USERNAME/PASSWORD/REPO`, `SSH_*`, `ENV_FILE`). `ENV_FILE`이 배포 시 서버 `.env`로 떨어진다. **실제 값은 커밋 금지.**
- RAG 소유 컨테이너(app·vector-db)만 뜨고 내리므로 스프링·postgres·redis엔 영향 없음(스코프 격리). 배포 시 vector-db 도 재시작되지만 데이터는 볼륨(`vector_data`)에 유지.
- **PR 을 연달아 머지하면 CD 가 겹쳐 일부 run 이 실패한다.** 배포가 동시에 돌며 컨테이너를 서로 내렸다 올리기 때문. 마지막 run 이 성공하면 최종 상태는 정상이지만, 확인은 실행 로그가 아니라 **배포된 `/openapi.json` 으로 한다.** 한 번에 하나씩 머지하면 안 겪는다.
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
- 테스트 디렉토리(`tests/`)는 아직 없다. 프롬프트·응답 변경은 **실제 OpenAI 호출로 확인**하고, 순수 로직은 `PYTHONPATH=. .venv/bin/python -c "..."` 로 인라인 점검한다. CI 는 Ruff + 빌드 검증만 돈다.
- 로컬에는 `VECTOR_DB_URL` 이 없어 판례 검색이 **키워드 폴백**으로만 돈다. 하이브리드 경로(벡터 후보·주문 재조회)는 배포 후 실제 API 호출로 확인해야 한다 — `similarity` 에 값이 오면 벡터가 붙은 것이다.

## Claude Code 작업 방식
1. Plan: 변경 계획(파일 목록·주요 내용)을 먼저 제시한다.
2. Confirm: 사용자 승인 전에는 어떤 파일도 생성/수정하지 않는다.
3. Implement: 승인된 범위만 구현한다.
4. Review: 구현 후 변경된 파일 목록과 제안 커밋 메시지를 보여주고, 사용자 확인을 받는다.
5. Commit: 사용자 확인을 받은 뒤에만 커밋한다.
6. Push: 자동으로 push 하지 않는다. push는 사용자가 명시적으로 지시할 때만 수행한다.
- 요청하지 않은 디렉토리/파일을 임의로 만들지 않는다.
- `CLAUDE.md` 자체를 수정할 때는 별도 브랜치를 만들지 않고 `main`에 직접 커밋한다.