# 프로젝트 파일 구조

> 각 파일의 역할과 의존 관계 정리. 코딩 시작 전 참고.
> ✅ 완성 | 🔲 미작성

---

## 루트

| 파일 | 상태 | 설명 |
|------|------|------|
| `CLAUDE.md` | ✅ | 프로젝트 전체 스펙 (기술스택, 아키텍처, 확정 결정사항) |
| `DESIGN.md` | ✅ | 디렉토리 구조, 테이블 스키마, 플로우 상세 |
| `PROJECT_FILES.md` | ✅ | 이 문서 — 파일별 역할 설명 |
| `colab_bundle_download.py` | ✅ | Colab에서 실행. 폐쇄망 반입용 pip 패키지 번들 다운로드 |
| `colab_model_download.py` | ✅ | Colab에서 실행. Qwen3.6 GGUF 모델 다운로드 + tar.gz 분할 |
| `server_env.txt` | ✅ | 폐쇄망 서버 기설치 패키지 목록 (번들 다운로드 중복 제외용) |
| `상품추천쿼리.txt` | ✅ | 레거시 Oracle 쿼리 (학습 데이터 생성용, 참고만) |
| `상품추천py.txt` | ✅ | 레거시 Python 코드 (gd_filter_func 등 포팅 참고용) |

---

## config/

| 파일 | 상태 | 설명 |
|------|------|------|
| `config/settings.py` | ✅ | **전체 설정 중앙 관리.** 경로(DuckDB/Chroma/WAV/docs), Ollama 모델명, Oracle 접속정보, 테이블명 상수. 모든 파일이 이것을 import함 |
| `config/allowed_ips.txt` | 🔲 | 허용 IP 목록 (한 줄에 IP 하나). ui/middleware.py가 읽음 |

---

## db/

| 파일 | 상태 | 설명 |
|------|------|------|
| `db/schema.sql` | ✅ | **DuckDB DDL.** 9개 테이블 정의 (`tbl_ds_*`). db/manager.py가 서비스 시작 시 자동 실행 |
| `db/manager.py` | ✅ | **DuckDB 연결 헬퍼.** `query_df()` `query_one()` `atomic_replace()` 제공. 에이전트/파이프라인 전 범위에서 import해서 사용 |
| `db/oracle_queries.py` | 🔲 | **Oracle → DuckDB 적재 쿼리.** 테이블별 SELECT 쿼리 함수 모음. CASE WHEN으로 RESULT_CD 번역 포함. 6/1 사용자 제공 쿼리 기반으로 작성 |
| `db/TABLE_SPEC.md` | ✅ | DuckDB 테이블 명세 (컬럼/타입/Oracle 소스). Oracle 쿼리 작성 참고용 |
| `db/DUCKDB_LOADING_GUIDE.md` | ✅ | DuckDB 적재 절차 가이드 (Jupyter 검증 → LLM 컨테이너 실행) |

---

## pipelines/

배치 파이프라인. 서비스와 별개로 1회 또는 cron으로 실행.

| 파일 | 상태 | 설명 |
|------|------|------|
| `pipelines/pipeline_a_stt.py` | 🔲 | **STT 인덱싱 (1회성).** WAV → faster-whisper → 마스킹+분석(Qwen3.6) → nomic-embed-text → Chroma `calls`. CALL_ID 단위 resume 지원. Day 3 시작, 약 41~83시간 소요 |
| `pipelines/pipeline_b_docs.py` | 🔲 | **문서 인덱싱 (1회성).** DOCX/PPTX/PDF → 마크다운 → nomic-embed-text → Chroma `products`. 문서명 단위 resume 지원 |
| `pipelines/pipeline_c_duckdb.py` | 🔲 | **DuckDB 마트 갱신 (매일 cron).** cx_Oracle → oracle_queries.py → mart_new.db 적재 → atomic rename. `os.makedirs` 자동 생성 포함 |

---

## agent/

LangGraph 에이전트. Tab1/Tab2 모든 대화 처리.

| 파일 | 상태 | 설명 |
|------|------|------|
| `agent/state.py` | 🔲 | **LangGraph AgentState.** `messages` `active_tab` `ctmno` `db_tier` `customer_data` `rag_results` `campaign_conditions` 등 정의 |
| `agent/graph.py` | 🔲 | **LangGraph 그래프 조립.** 노드 연결, 조건 엣지, 체크포인트(SQLite) 설정 |
| `agent/nodes/router.py` | 🔲 | **탭 라우팅 + Tab1 3분기 분기.** tbl_ds_call_detail 조회 → 신규/미연결/이력 결정. Tab2 의도 분류 (query/script/list) |
| `agent/nodes/tab1.py` | 🔲 | **콜 전 준비 노드.** 신규/미연결/이력 3개 서브플로우. DuckDB 조회 즉시 표시 + Qwen3.6 스크립트 스트리밍 |
| `agent/nodes/tab2.py` | 🔲 | **영업지원 Agent 노드.** 모드A(자유질의) / 모드B(스크립트생성) / 모드C(캠페인리스트) |
| `agent/tools/duckdb_tools.py` | 🔲 | **DuckDB LangGraph Tool 등록.** 테이블별 조회 함수를 Tool로 래핑. LLM이 description 보고 선택 |
| `agent/tools/chroma_tools.py` | 🔲 | **Chroma RAG Tool 등록.** `calls` / `products` 컬렉션 검색. 채널/캠페인/체결여부 메타데이터 필터 포함 |

---

## ui/

Gradio 앱. 사내망 IP 접근.

| 파일 | 상태 | 설명 |
|------|------|------|
| `ui/app.py` | 🔲 | **Gradio 메인 앱.** Tab1(콜 전 준비) + Tab2(영업지원 Agent) 2탭. Tab1: gr.Markdown 즉시 + gr.Textbox 스트리밍. DuckDB 수동 갱신 버튼 + 마지막 갱신 시각 표시 |
| `ui/middleware.py` | 🔲 | **FastAPI IP 필터 미들웨어.** allowed_ips.txt 읽어서 허용 IP 검사. Gradio를 FastAPI로 마운트해서 적용 |

---

## utils/

공통 유틸리티.

| 파일 | 상태 | 설명 |
|------|------|------|
| `utils/masking.py` | 🔲 | **개인정보 마스킹 1단계 (Regex).** 전화번호/주민번호/계좌번호/카드번호 패턴 치환. STT 원문에 먼저 적용 후 Qwen3.6 전달 |
| `utils/eligibility.py` | 🔲 | **상품 가입 가능 여부 체크 (gd_filter_func).** `상품추천py.txt`의 GDREC_GD_filter.py 포팅. L01/L04/L03/SS: 나이+성별 분기. 유병자: 병력 4개 컬럼 min값 분기 |

---

## data/ (git 제외)

| 경로 | 설명 |
|------|------|
| `data/duckdb/mart.db` | DuckDB 메인 DB (서비스 중 읽기) |
| `data/duckdb/mart_new.db` | 갱신 시 임시 파일 (완료 후 mart.db로 교체) |
| `data/duckdb/checkpoints.sqlite` | LangGraph 세션 체크포인트 (자동 생성) |
| `data/chroma/` | Chroma 벡터DB 저장소 |
| `data/wav/` | WAV 녹취 파일 (CALL_ID.wav) |
| `data/docs/` | 내부 문서 (DOCX/PPTX/PDF) |

---

## 실행 순서 (폐쇄망 서버 최초 배포)

```
1. pip 번들 설치 (install.sh)
2. ollama serve 백그라운드 시작
3. python pipelines/pipeline_c_duckdb.py   # DuckDB 마트 초기 적재
4. python pipelines/pipeline_b_docs.py     # 상품 문서 인덱싱
5. python pipelines/pipeline_a_stt.py      # STT 인덱싱 (백그라운드, 41~83시간)
6. python ui/app.py                        # Gradio 서비스 시작
```

---

## 개발 환경 주의

- **LLM 컨테이너 (VS Code)**: 모든 Python 코드 실행, DuckDB 생성·운영
- **Jupyter 컨테이너**: Oracle 쿼리 검증 전용 — DuckDB 생성 금지
- 두 컨테이너는 파일시스템 분리됨 (shared volume 없음)
