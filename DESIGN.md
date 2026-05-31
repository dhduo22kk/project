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
│   │   ├── router.py        # 탭 라우팅 + Tab2 의도 분류
│   │   ├── tab1.py          # 콜 전 준비 노드 (핵심)
│   │   └── tab2.py          # 영업지원 Agent 노드 (자유질의/스크립트/리스트)
│   └── tools/
│       ├── duckdb_tools.py  # DuckDB 조회 Tool 등록
│       └── chroma_tools.py  # Chroma RAG Tool 등록
│
├── db/
│   ├── schema.sql           # DuckDB DDL (전체 테이블)
│   ├── oracle_queries.py    # DuckDB 적재용 Oracle SELECT 쿼리
│   └── manager.py           # DuckDB 연결·쿼리 헬퍼 (atomic rename 지원)
│
├── ui/
│   ├── app.py               # Gradio 2탭 메인 앱
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
        mart.db              # DuckDB 메인 DB (서비스 중 읽기 전용)
        mart_new.db          # DuckDB 갱신용 임시 DB (갱신 후 rename)
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
| HOSP_CLAIM | VARCHAR | 입원청구 (유병자 판단용) |
| HOSP_NOTI | VARCHAR | 입원고지 (유병자 판단용) |
| MAJOR_DSAS_NOTI | VARCHAR | 중대질환고지 (유병자 판단용) |
| MAJOR_DSAS_CLAIM | VARCHAR | 중대질환청구 (유병자 판단용) |

> Oracle 소스: CUS_CTM + GDREC_ORIGIN_MAIN_FIN_PRED LEFT JOIN
> 병력 컬럼 4개: 컴플라이언스 승인 확인, DuckDB 적재 가능

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
| CALL_DT | TIMESTAMP | 통화일시 (시:분 포함 — 시간대 분석 필수) |
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
| CAMPAIGN_TYPE | VARCHAR | 캠페인 유형 (TM/CM) |

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
| REC_POCT | FLOAT | 상품 구매 확률 (0~1) |

> REC_RS1(기존 스크립트) 제외. 신규 고객은 row 없음.
> REC_POCT: Tab2 모드C 고객 정렬 보조 활용 가능 (tbl_campaign_score 없을 때 폴백)

---

### tbl_new_coverage
3개월 이내 신규 가입 담보. Tab1 계약 현황 + 스크립트 생성용.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| CVR_CD | VARCHAR | 담보코드 |
| CVR_NM | VARCHAR | 담보명 |
| CVR_GRP_NM | VARCHAR | 커스텀 그룹명 (tbl_cvr_group_map JOIN) |
| CVR_START_DT | DATE | 담보 가입일 |
| ISAMT | BIGINT | 가입금액 |

> Oracle 소스: INS_CR_CVR 계열, CVR_START_DT >= SYSDATE - 90 필터
> 갱신 주기: 매일 cron (Pipeline C와 동일)

---

### tbl_campaign_score
외부 캠페인 추천도 모델 결과. 레거시 상품추천시스템과 동일 방식으로 외부 생성 후 적재.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| CAMPAIGN_TYPE | VARCHAR | 캠페인 유형 (TM/CM 등) |
| SCORE | FLOAT | 추천도 점수 (0~1) |
| SCORE_DT | DATE | 스코어 생성일 |

> Tab2 모드C 고객 리스트 생성 시 SCORE 높은 순 정렬
> 외부 모델 결과를 DuckDB에 적재하는 방식 (실시간 추론 없음)

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
- **metadata**: CALL_ID, CTMNO, 체결여부, CALL_DURATION, 우호적여부(bool), keywords(comma-separated string), CAMPAIGN_NM, + COVERAGE_COLS 12개
- **주의**: keywords는 list 불가 → `"암진단,거절,보험료"` 형식으로 저장

### products
- **임베딩 대상**: 문서 마크다운 청크
- **metadata**: 문서명, 카테고리, 페이지/슬라이드 번호

---

## 4. LangGraph AgentState (안)

```python
class AgentState(TypedDict):
    messages: list              # 대화 히스토리 (멀티턴)
    active_tab: str             # "tab1" | "tab2"
    tab2_mode: str | None       # "query" | "script" | "list" (Tab2 전용)
    ctmno: str | None           # Tab1: 조회 고객번호
    call_id: str | None         # Tab1: 통화ID (미사용, 향후 확장용)
    db_tier: str | None         # Tab1: "신규" | "미연결" | "이력"
    customer_data: dict         # DuckDB 조회 캐시
    rag_results: list           # Chroma 조회 캐시
    campaign_conditions: dict   # Tab2 모드C: 수집된 캠페인 조건
    final_answer: str | None
```

- 탭 전환 시 ctmno / customer_data 유지 가능 (향후 Tab1 → Tab2 컨텍스트 연계)
- 세션 키: 사내망 IP (동시 사용자 ~5명)
- 영속성: langgraph-checkpoint-sqlite

---

## 5. Tab2 의도 라우팅

단일 채팅 인터페이스에서 LangGraph가 세 가지 모드로 자동 분기.

```
사용자 입력
    ↓
[의도 분류 노드] Qwen3.6 → tab2_mode 결정
    ↓
[확인 메시지 출력] — 오분류 복구 포인트
    예: "캠페인 고객 리스트 생성으로 이해했습니다.
         조건을 같이 정해볼까요? (아니라면 원하는 작업을 다시 말씀해 주세요)"
    ↓
사용자가 확인 or 수정
    ├─ "query"  → 모드A: 자유 질의 (캠페인 매출, 신상품 정보 등)
    ├─ "script" → 모드B: 스크립트 생성 (TM 녹취 기반)
    └─ "list"   → 모드C: 캠페인 고객 리스트 생성 → Excel 출력
```

**확인 메시지 템플릿:**
| 분류 결과 | 확인 메시지 |
|----------|------------|
| query | "성과/정보 조회로 이해했습니다. 바로 찾아드릴게요. (다른 작업이라면 말씀해 주세요)" |
| script | "스크립트 생성으로 이해했습니다. 어떤 상황의 스크립트가 필요하신가요? (다른 작업이라면 말씀해 주세요)" |
| list | "캠페인 고객 리스트 생성으로 이해했습니다. 조건을 같이 정해볼까요? (다른 작업이라면 말씀해 주세요)" |

**분류 기준 예시:**
| 입력 | 모드 |
|------|------|
| "이번 달 TM 캠페인 체결율 어때?" | query |
| "암보험 캠페인 매출 보여줘" | query |
| "마케팅 동의봇 스크립트 만들어줘" | script |
| "50대 거절 극복 스크립트" | script |
| "신상품 내용 알려줘" | query |
| "마케팅 동의 문자 발송 캠페인 고객 뽑아줘" | list |

---

## 6. 파이프라인 흐름 요약

### Pipeline A — STT (1회성)
1. WAV 디렉토리 스캔
2. **CALL_ID 단위** `collection.get(ids=[call_id])` → 존재하면 skip
3. `Path.stem` → CALL_ID → tbl_call_detail 조회 → CTMNO + 메타데이터
4. tbl_coverage 조회 → 담보금액 12개
5. faster-whisper → 원문
6. Regex 마스킹 (1단계)
7. Qwen3.6 → JSON (masked_text / sentiment / keywords / summary)
8. keywords: list → `",".join(keywords)` 변환 후 metadata 저장
9. nomic-embed-text → 임베딩 → Chroma upsert

### Pipeline B — 문서 인덱싱 (1회성)
1. docs/ 디렉토리 스캔
2. **문서명 단위** `collection.get()` → 존재하면 skip
3. 포맷별 파싱 (PDF→pymupdf4llm / DOCX→mammoth / PPTX→python-pptx)
4. (이미지 포함 시) 비전 LLM 처리
5. nomic-embed-text → Chroma upsert

### Pipeline C — DuckDB 마트 갱신 (매일 cron)
1. cx_Oracle 접속
2. 도메인별 Oracle 마트 쿼리 실행 (db/oracle_queries.py)
3. **mart_new.db** 에 TRUNCATE & INSERT
4. 완료 후 `mart_new.db` → `mart.db` atomic rename
5. 갱신 완료 시각 기록

---

## 7. DuckDB 자주 쓰는 템플릿 쿼리 (Tab2 모드A)

복잡한 자유 질의 대신 자주 쓰는 지표는 사전 정의 쿼리로 제공.
결과 신뢰도 향상 + 응답 속도 개선.

| 지표명 | 쿼리 설명 |
|--------|---------|
| 캠페인별 체결율 | tbl_call_detail GROUP BY CAMPAIGN_NM, RESULT_CD |
| 캠페인별 매출 | tbl_contract_history JOIN tbl_campaign_history |
| 월별 체결 추이 | tbl_contract_history GROUP BY MONTH(INS_ST) |
| 채널별 성과 비교 | tbl_campaign_history.CAMPAIGN_TYPE 기준 집계 |

자유 질의 결과에는 UI에서 "AI가 생성한 쿼리 결과입니다. 반드시 확인하세요." 경고 표시.

---

## 8. Tab2 모드C — 캠페인 고객 리스트 생성 플로우

```
Step 1. 운영자 입력: 캠페인 방향 설명
    예: "마케팅 동의 문자 발송 캠페인"

Step 2. 유사 과거 캠페인 탐색
    → DuckDB: tbl_campaign_history WHERE CAMPAIGN_NM LIKE '%마케팅동의%'
    ├─ [유사 있음] 과거 타겟 세그먼트 + 체결율 요약 → 조건 제안
    └─ [신규] Agent가 조건 추가 질의
        → 조건 없으면: 고객 활성도 기반 / 랜덤 추출 중 안내

Step 3. 고객 리스트 생성
    → DuckDB: tbl_customer + tbl_coverage + tbl_contract_history
              + tbl_recommendation → 조건 매칭 + 우선순위 정렬
    → CM 채널: 갱신 가능성 높은 고객 제외

Step 4. 결과 출력
    ① Excel 다운로드 (CTMNO 컬럼만)  ← pandas.to_excel() + openpyxl
    ② 예상 효율 참고치 (과거 유사 캠페인 체결율 기반)
    ③ 채널별 접근 전략 요약 텍스트
```

---

## 9. 미확정 항목 (Oracle 접속 후 확인)

| 항목 | 내용 |
|------|------|
| tbl_call_detail Oracle 소스 | 통화이력 원본 테이블명 |
| tbl_campaign_history Oracle 소스 | 캠페인·배정이력 원본 테이블명 |
| tbl_contract_history Oracle 소스 | 계약이력 원본 테이블명 |
| tbl_design_history Oracle 소스 | 설계이력 원본 테이블명 |
| tbl_coverage_detail Oracle 소스 | 담보코드별 금액 원본 테이블명 |
| tbl_customer Oracle 마트 DDL | CUS_CTM + GDREC_ORIGIN_MAIN_FIN_PRED 조인 쿼리 |
| CM 채널 갱신 가능성 데이터 소스 | 갱신 가능성 높은 고객 제외 기준 (예측모델 결과 테이블명) |
| tbl_new_coverage Oracle 소스 | INS_CR_CVR 계열 정확한 테이블명 + CVR_START_DT 컬럼명 확인 |
| tbl_campaign_score 생성 주기 | 외부 모델 재학습/스코어링 주기 확정 필요 |
| 비전 LLM 모델 확정 | Qwen2-VL 계열 경량 — VRAM 요구량 및 모델명 |
