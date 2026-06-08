# 프로젝트 파일 구조

> 각 파일의 역할과 의존 관계 정리.
> ✅ 완성 | 🔧 리팩토링됨 | 📋 계획됨

---

## 루트

| 파일 | 상태 | 설명 |
|------|------|------|
| `CLAUDE.md` | ✅ | 프로젝트 전체 스펙. Key Decisions 포함. 경진대회 고도화 결정사항 추가됨 |
| `DESIGN.md` | ✅ | 디렉토리 구조, 테이블 스키마, 플로우 상세 |
| `PROJECT_FILES.md` | ✅ | 이 문서 — 파일별 역할/상태 |
| `competition_guide.md` | ✅ | **경진대회 발표자료 콘텐츠 기준 문서.** PPT/기술레포트 구성·디자인·WOW포인트·금지표현 정의 |
| `sample_scripts.md` | ✅ | **한화손해보험 상품 기반 샘플 스크립트 3종.** 신규/이력/미연결 시나리오. 데모·발표용 |

---

## Inputs/ (참고·레거시·반입 파일)

| 파일 | 설명 |
|------|------|
| `colab_bundle_download.py` | Colab에서 실행. 폐쇄망 반입용 pip 번들 다운로드 |
| `colab_model_download.py` | Colab에서 실행. Qwen3.6 GGUF 다운로드 + tar.gz 분할 |
| `server_env.txt` | 폐쇄망 서버 기설치 패키지 목록 |
| `sql.txt` | 레거시 Oracle SQL 원본 (참고용) |
| `상품추천py.txt` | 레거시 Python 코드 (gd_filter_func 등 참고용) |
| `상품추천쿼리.txt` | 레거시 Oracle 쿼리 (학습 데이터 생성용, 참고만) |

---

## outputs/ (경진대회 제출·발표 결과물)

| 파일 | 상태 | 설명 |
|------|------|------|
| `technical_report.html` | 🔧 | 기술 레포트. LangGraph CoT·HyDE·Dynamic Few-Shot 반영 필요 |
| `ai_consultation_agent_interim_report_v2.html` | ✅ | 중간 발표용 HTML. **디자인 토큰 기준 파일** (주황 #f37321, Urbanist/Noto Sans KR) |
| `ui_demo.html` | 🔧 | HTML 데모. 해시태그 키워드·샘플 스크립트 반영 필요 |
| `summary.html` | ✅ | 초기 요약 HTML |

---

## recommendation/ (레거시 ML 추천 시스템)

| 파일 | 설명 |
|------|------|
| `recommendation/config.py` | 레거시 추천 시스템 설정 |
| `recommendation/db.py` | 레거시 DB 연결 |
| `recommendation/gd_filter.py` | 가입 가능 여부 필터 (gd_filter_func). 현재 프로젝트는 tbl_ds_ineligible로 대체 |
| `recommendation/main.py` | 레거시 추천 메인 실행 |
| `recommendation/model.py` | AutoGluon 기반 ML 모델 |

---

## config/

| 파일 | 상태 | 설명 |
|------|------|------|
| `config/settings.py` | ✅ | **전체 설정 중앙 관리.** 경로·모델·Oracle접속·테이블명 상수. 모든 파일이 import |

---

## db/

| 파일 | 상태 | 설명 |
|------|------|------|
| `db/schema.sql` | ✅ | **DuckDB DDL.** `tbl_ds_*` 테이블 정의 |
| `db/manager.py` | ✅ | **DuckDB 연결 헬퍼.** `query_df()` `query_one()` `atomic_replace()`. 전 범위에서 import |
| `db/oracle_queries.py` | ✅ | **DuckDB 테이블명 ↔ Oracle AI_* 매핑.** `QUERIES` dict. tbl_ds_msg_history None(TODO) |

---

## pipelines/

| 파일 | 상태 | 설명 |
|------|------|------|
| `pipelines/pipeline_a_stt.py` | ✅ | **STT 인덱싱 (1회성).** WAV → faster-whisper → Regex마스킹 → Qwen3.6(마스킹+분석 JSON) → Chroma `calls`. Chroma embedded_text: `[고객: {age}세 {sex}, {campaign}] {summary}` |
| `pipelines/pipeline_b_docs.py` | ✅ | **문서 인덱싱 (1회성).** DOCX/PPTX/PDF → 마크다운 → Chroma `products`. 문서명 단위 resume |
| `pipelines/pipeline_c_duckdb.py` | ✅ | **DuckDB 마트 갱신 (매일 cron).** Oracle AI_* → mart_new.db 청크 적재(50k행) → atomic rename |

---

## agent/

Tab1 LangGraph 파이프라인 + Tab2 캠페인 추출.

| 파일 | 상태 | 설명 |
|------|------|------|
| `agent/state.py` | ✅ | **LangGraph Tab1State TypedDict.** ctmno/tier/data/db_markdown/hyde_query/rag_cases/rag_products/customer_insight/approach_angle/needs_product_search/product_query/final_prompt |
| `agent/graph.py` | ✅ | **LangGraph 8노드 파이프라인.** classify → fetch_data → format_db → hyde(HyDE) → rag(Dynamic Few-Shot) → analyze(ReAct lite) → [fetch_extra_products] → prepare_prompt. `TAB1_GRAPH` 컴파일본 모듈 레벨 노출 |
| `agent/tab1_handler.py` | 🔧 | **스트리밍 래퍼 (50줄).** `stream_tab1(ctmno)` → TAB1_GRAPH.invoke() → LLM.stream(final_prompt). Gradio generator 인터페이스 유지 |
| `agent/campaign.py` | ✅ | **Tab2 캠페인 추출.** `get_campaign_list()` `get_prev_campaign_stats()` `build_campaign_query(conditions)` `extract_campaign_list()` `to_excel_tempfile()`. 3종 전략: past_performance/activity_based/rule_based |

**삭제/미생성 (구버전 계획과 다름)**:
- `agent/nodes/` — graph.py에 통합됨
- `agent/tools/` — graph.py 내 노드 함수로 구현됨

---

## ui/

| 파일 | 상태 | 설명 |
|------|------|------|
| `ui/app.py` | ✅ | **Gradio 2탭 메인 앱.** Tab1(상담사): ctmno → stream_tab1() 스트리밍. Tab2(기획자): 캠페인선택 → 폼Q&A → 추출 → Excel. DuckDB 갱신 확인 버튼 포함 |

**삭제**: `ui/middleware.py` — 네트워크 레벨 접근제어로 대체

---

## utils/

| 파일 | 상태 | 설명 |
|------|------|------|
| `utils/masking.py` | ✅ | **개인정보 마스킹 1단계 (Regex).** 카드번호→주민번호→전화번호→계좌번호 순 치환. Pipeline A에서 STT 직후 호출 |

**삭제**: `utils/eligibility.py` — tbl_ds_ineligible(레거시 배치 결과)로 대체

---

## 경진대회 관련 HTML (발표용)

| 파일 | 상태 | 설명 |
|------|------|------|
| `technical_report.html` | 🔧 | 기술 레포트. 현재 버전은 업데이트 필요 (LangGraph CoT·HyDE·Dynamic Few-Shot 미반영) |
| `ai_consultation_agent_interim_report_v2.html` | ✅ | 중간 발표용 HTML. 디자인 토큰 기준 파일 |
| `ui_demo.html` | 🔧 | HTML 데모. 해시태그 키워드·샘플 스크립트 반영 필요 |

---

## data/ (git 제외)

| 경로 | 설명 |
|------|------|
| `data/duckdb/mart.db` | DuckDB 메인 DB |
| `data/duckdb/mart_new.db` | 갱신 임시 파일 |
| `data/chroma/` | Chroma 벡터DB (calls + products 컬렉션) |
| `data/wav/` | WAV 녹취 (CALL_ID.wav) |
| `data/docs/` | 내부 문서 (DOCX/PPTX/PDF) |

---

## 실행 순서

```bash
# 최초 배포
1. ./install.sh                          # pip 번들
2. ollama serve &                        # Ollama 백그라운드
3. python pipelines/pipeline_c_duckdb.py # DuckDB 적재
4. python pipelines/pipeline_b_docs.py   # 상품 문서 인덱싱
5. python pipelines/pipeline_a_stt.py    # STT 인덱싱 (백그라운드, 41~83시간)
6. python ui/app.py                      # Gradio 서비스
```

---

## 남은 작업

| 작업 | 우선순위 | 설명 |
|------|---------|------|
| Tab2 DB 직접 생성 | 중 | Excel 외 DuckDB 타겟 리스트 테이블 직접 생성 → 전사관리시스템 연동 |
| ui_demo.html 업데이트 | 높음 | 해시태그 키워드 + 샘플 스크립트 3종 반영 |
| technical_report.html 업데이트 | 높음 | LangGraph CoT·HyDE·Dynamic Few-Shot·경진대회 스코프 반영 |
| PPT 제작 | 높음 | competition_guide.md 기준 9슬라이드 |
| 데모 URL 확정 | 높음 | Gradio 서비스 주소 competition_guide.md에 삽입 |
