# AI 상담 에이전트 — 구현 설계서

> 확정된 설계 결정을 코드 작성 전 정리한 문서.
> 아래 항목 중 `TODO` 표시된 것은 Oracle 접속 후 확인 필요.

---

## 1. 프로젝트 디렉토리 구조 (안)

```
ai-consultation-agent/
├── CLAUDE.md
├── DESIGN.md
├── colab_bundle_download.py
├── colab_model_download.py
│
├── config/
│   ├── settings.py          # 경로·모델·IP 설정 중앙 관리
│   └── allowed_ips.txt      # 허용 IP 목록
│
├── pipelines/
│   ├── pipeline_a_stt.py    # STT 배치 (WAV → Chroma calls)
│   ├── pipeline_b_docs.py   # 문서 인덱싱 (DOCX/PPTX/PDF → Chroma products)
│   ├── pipeline_c_duckdb.py # DuckDB 마트 갱신 (Oracle → DuckDB, 매일 cron)
│   └── pipeline_cvr_map.py  # tbl_cvr_group_map 생성 (LLM 초안, 1회성)
│
├── agent/
│   ├── state.py             # LangGraph AgentState 정의
│   ├── graph.py             # LangGraph 그래프 조립
│   ├── nodes/
│   │   ├── router.py        # 탭 라우팅 + 1차/2차 분기
│   │   ├── tab1.py          # 통화 평가 노드
│   │   ├── tab2.py          # 콜 전 준비 노드 (핵심)
│   │   └── tab3.py          # 스크립트/분석/모의상담 노드
│   └── tools/
│       ├── duckdb_tools.py  # DuckDB 조회 Tool 등록
│       └── chroma_tools.py  # Chroma RAG Tool 등록
│
├── db/
│   ├── schema.sql           # DuckDB DDL (전체 테이블)
│   └── manager.py           # DuckDB 연결·쿼리 헬퍼
│
├── ui/
│   ├── app.py               # Gradio 3탭 메인 앱
│   └── middleware.py        # FastAPI IP 필터 미들웨어
│
└── utils/
    ├── masking.py           # 개인정보 마스킹 (Regex 1단계)
    └── eligibility.py       # gd_filter_func (가입 가능 여부 룰)

data/                        # 서버 로컬 (git 제외)
    wav/                     # WAV 파일 (CALL_ID.wav)
    docs/                    # 내부 문서 (DOCX/PPTX/PDF)
    chroma/                  # Chroma 벡터DB 저장소
    duckdb/
        mart.db              # DuckDB 메인 DB
        checkpoints.sqlite   # LangGraph 세션 체크포인트
```

---

## 2. DuckDB 테이블 스키마

### tbl_customer
고객 기본정보. Oracle 신규 마트(CUS_CTM + GDREC_ORIGIN_MAIN_FIN_PRED LEFT JOIN)에서 적재.
전체 ~30만 명, 신규 고객 포함.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 (PK) |
| CTM_AGE | INTEGER | 나이 |
| CTM_SEX | VARCHAR | 성별 (1.M / 2.F) |
| REGION | VARCHAR | 지역 |
| REG_DT | DATE | 등록일 |
| INFLOW_CAMPAIGN_NM | VARCHAR | 유입 캠페인명 (tbl_campaign_history JOIN) |

> Oracle 소스 테이블명: TODO (CUS_CTM 확인 필요)

---

### tbl_coverage
보장분석 대분류 담보금액 wide (스크립트 생성용).
고객번호당 1 row. 신규 고객은 전체 null.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 (PK) |
| CANCR_DASCS_AMT | BIGINT | 암진단비 |
| ISMC_HEART_DSAS_DASCS_AMT | BIGINT | 허혈성심장질환진단비 |
| CRLR_DSAS_DASCS_AMT | BIGINT | 뇌혈관질환진단비 |
| DSAS_HSP_RLPMI_AMT | BIGINT | 질병입원실손 |
| DSAS_OTP_RLPMI_AMT | BIGINT | 질병통원실손 |
| SERI_DEMEN_AMT | BIGINT | 중증치매 |
| LTRM_RCPR_DGN_RANK4_AMT | BIGINT | 장기요양진단4급 |
| BDIN_CCA_SUAMT_AMT | BIGINT | 대인형사합의지원금 |
| LWR_SNRT_CS_AMT | BIGINT | 변호사선임비용 |
| DRV_PNLTY_AMT | BIGINT | 운전자벌금 |
| FIRE_PNLTY_AMT | BIGINT | 화재벌금 |
| USLLF_LBTRS_AMT | BIGINT | 일상생활배상책임 |

> Oracle 소스: GDREC_ORIGIN_MAIN_FIN_PRED (기존 계약 고객만 → 신규는 null 처리)

---

### tbl_coverage_detail
담보코드 단위 상세금액 long (LIKE 검색용).

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| CVR_CD | VARCHAR | 담보코드 (e.g. ARLA10661) |
| CVR_NM | VARCHAR | 담보명 |
| CVR_GRP_NM | VARCHAR | 커스텀 그룹명 (tbl_cvr_group_map JOIN) |
| AMT | BIGINT | 가입금액 |

> Oracle 소스: TODO (INS_CR_CVR 계열 확인 필요)

---

### tbl_cvr_group_map
담보코드 → 커스텀 그룹명 매핑. LLM 초안 + 전문가 검수로 1회성 구축.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CVR_CD | VARCHAR | 담보코드 (PK) |
| CVR_GRP_CD | VARCHAR | 그룹코드 |
| CVR_GRP_NM | VARCHAR | 그룹명 (e.g. '2대질병치료비') |

---

### tbl_call_detail
통화이력. 1차/2차 분기 핵심.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CALL_ID | VARCHAR | 통화ID (PK) |
| CTMNO | VARCHAR | 고객번호 |
| CALL_DT | DATE | 통화일시 |
| CALL_DURATION | INTEGER | 통화시간(초) |
| RESULT_CD | VARCHAR | 결과코드 (체결/거절/결번/무응답 등) |
| CAMPAIGN_NM | VARCHAR | 캠페인명 |

> Oracle 소스: TODO (통화이력 원본 테이블명 확인 필요)

---

### tbl_campaign_history
캠페인이력 + 배정이력 통합.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| CAMPAIGN_NM | VARCHAR | 캠페인명 |
| ASSIGN_DT | DATE | 배정일 |
| MSG_SEND_DT | DATE | 문자발송일 (null이면 미발송) |
| CAMPAIGN_TYPE | VARCHAR | 캠페인 유형 |

> Oracle 소스: TODO (배정이력/캠페인이력 테이블명 확인 필요)

---

### tbl_contract_history
계약이력.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| PLYNO | VARCHAR | 증권번호 |
| GDCD | VARCHAR | 상품코드 |
| GDNM | VARCHAR | 상품명 |
| INS_ST | DATE | 보험시기 |
| INS_CLSTR | DATE | 보험종기 |
| AP_PRM | BIGINT | 적용보험료 |
| CR_STCD | VARCHAR | 계약상태코드 |

> Oracle 소스: TODO

---

### tbl_design_history
설계이력.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| DESIGN_DT | DATE | 설계일 |
| GDCD | VARCHAR | 상품코드 |
| GDNM | VARCHAR | 상품명 |
| DESIGN_PRM | BIGINT | 설계보험료 |
| RESULT_CD | VARCHAR | 결과코드 (체결/미체결) |

> Oracle 소스: TODO

---

### tbl_recommendation
레거시 ML 추천결과. Oracle M_CRM_REC_RLT_BIZ에서 적재.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| REC_RANK | INTEGER | 추천순위 (1/2/3) |
| REC_GDCD | VARCHAR | 추천상품코드 |
| REC_GDNM | VARCHAR | 추천상품명 |

> REC_RS1(기존 스크립트) 제외. 신규 고객은 row 없음.

---

### tbl_change_log
M4에서 구현. 임팩트 있는 변경 감지.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| CHANGE_TYPE | VARCHAR | 변경유형 (통화진행/문자발송/계약체결) |
| CHANGE_DT | TIMESTAMP | 변경일시 |
| DETAIL | VARCHAR | 상세내용 |

---

## 3. Chroma 컬렉션

### calls
- **임베딩 대상**: 녹취 요약 텍스트
- **metadata**: CALL_ID, CTMNO, 체결여부, CALL_DURATION, 우호적여부(bool), keywords(list), CAMPAIGN_NM, + COVERAGE_COLS 12개

### products
- **임베딩 대상**: 문서 마크다운 청크
- **metadata**: 문서명, 카테고리, 페이지/슬라이드 번호

---

## 4. LangGraph AgentState (안)

```python
class AgentState(TypedDict):
    messages: list              # 대화 히스토리 (멀티턴)
    active_tab: str             # "tab1" | "tab2" | "tab3"
    tab3_mode: str              # "analysis" | "script" | "roleplay"
    ctmno: str | None           # 조회 고객번호
    call_id: str | None         # Tab1용 CALL_ID
    db_tier: str | None         # "1차" | "2차"
    customer_data: dict         # DuckDB 조회 캐시
    rag_results: list           # Chroma 조회 캐시
    final_answer: str | None
```

- 탭 전환 시 ctmno / customer_data 유지 (Tab2 → Tab3 모의상담 연계)
- 세션 키: 사내망 IP (동시 사용자 ~5명)
- 영속성: langgraph-checkpoint-sqlite

---

## 5. 파이프라인 흐름 요약

### Pipeline A — STT (1회성)
1. WAV 디렉토리 스캔
2. Chroma calls 컬렉션 ID 체크 → 이미 있으면 skip
3. `Path.stem` → CALL_ID → tbl_call_detail 조회 → CTMNO + 메타데이터
4. tbl_coverage 조회 → 담보금액 12개
5. faster-whisper → 원문
6. Regex 마스킹 (1단계)
7. Qwen3.6 → JSON (masked_text / sentiment / keywords / summary)
8. nomic-embed-text → 임베딩 → Chroma upsert

### Pipeline B — 문서 인덱싱 (1회성)
1. docs/ 디렉토리 스캔
2. Chroma products 컬렉션 ID 체크 → skip
3. 포맷별 파싱 (PDF→pymupdf4llm / DOCX→mammoth / PPTX→python-pptx)
4. (이미지 포함 시) 비전 LLM 처리
5. nomic-embed-text → Chroma upsert

### Pipeline C — DuckDB 마트 갱신 (매일 cron)
1. cx_Oracle 접속
2. 도메인별 Oracle 마트 쿼리 실행
3. DuckDB 테이블 TRUNCATE & INSERT (또는 UPSERT)
4. 갱신 완료 시각 기록

---

## 6. 미확정 항목 (Oracle 접속 후 확인)

| 항목 | 내용 |
|------|------|
| tbl_call_detail Oracle 소스 | 통화이력 원본 테이블명 |
| tbl_campaign_history Oracle 소스 | 캠페인·배정이력 원본 테이블명 |
| tbl_contract_history Oracle 소스 | 계약이력 원본 테이블명 |
| tbl_design_history Oracle 소스 | 설계이력 원본 테이블명 |
| tbl_coverage_detail Oracle 소스 | 담보코드별 금액 원본 테이블명 |
| tbl_customer Oracle 마트 DDL | CUS_CTM + GDREC_ORIGIN_MAIN_FIN_PRED 조인 쿼리 |
