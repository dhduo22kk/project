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

### tbl_ds_msg_history
전사 문자발송이력. 캠페인 무관 전사 발송 시스템에서 적재.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| SEND_DT | TIMESTAMP | 발송일시 |
| MSG_CONTENT | VARCHAR | 문자 내용 (SMS/LMS 텍스트) |
| MSG_TYPE | VARCHAR | 'SMS' \| 'LMS' \| 'MMS' |

> Tab1 이력 고객: 최근 2~3건 조회 → LLM 컨텍스트 주입 ("지난주에 보내드린 XX 안내 문자 보셨나요?" 활용)
> Tab2: 추출 조건 필터 ("최근 N일 내 문자 발송 고객 제외/포함")
> Oracle 소스: 전사 문자발송 시스템 테이블 (쿼리 수령 예정)

---

### tbl_ds_sales_focus
월별 영업 포커스. Gradio Tab2 편집 UI로 운영자가 매달 업데이트.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| FOCUS_YM | VARCHAR | 연월 키 (PK, e.g. '2026-06') |
| FOCUS_TEXT | VARCHAR | 자유형식 전문 (주력상품/이슈/제외상품) |
| UPDATED_AT | TIMESTAMP | 마지막 수정 시각 |

> Agent가 매 요청 시 `WHERE FOCUS_YM = strftime('%Y-%m', current_date)` 조회 → system message에 주입

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
    messages: list              # 대화 히스토리 (멀티턴, Tab2 전용)
    active_tab: str             # "tab1" | "tab2"
    # Tab1 전용
    ctmno: str | None           # 조회 고객번호
    db_tier: str | None         # "신규" | "미연결" | "이력"
    customer_data: dict         # DuckDB 조회 캐시
    rag_results: list           # Chroma 조회 캐시
    # Tab2 전용
    selected_campaign_nm: str | None  # 선택한 캠페인명
    campaign_step: int          # 폼 Q&A 진행 단계 (0~4)
    campaign_conditions: dict   # 수집된 조건 dict → build_campaign_query() 입력
                                # 필드: product_type / channel / gender / age_range /
                                #       want_new / target_count / strategy / custom_cond
    extraction_strategy: str | None  # "history" | "model" | "custom"
    final_answer: str | None
```

- Tab1: checkpoint 없음 (매 요청 fresh), Tab2: checkpoint-sqlite (IP 기반 멀티턴 세션)
- 세션 키: 사내망 IP (동시 사용자 ~5명)

---

## 5. Tab2 캠페인 선택 및 폼 Q&A 흐름

의도 분류 라우터 없음 — 사용자가 캠페인 리스트에서 직접 선택.

```
[캠페인 선택 화면 (좌측 패널)]
    tbl_ds_campaign_history DISTINCT 캠페인명 + CAMPAIGN_TYPE → 리스트 표시
    체결율 표시 없음 — 캠페인명 + 채널만
    + "신규 캠페인" 항목
         ↓ 선택
[폼 Q&A — LangGraph 단계별 진행] (신규/기존 동일 플로우)

  campaign_step=0: 어떤 캠페인인지 (구조화 칩 선택)
                   - 상품 유형: 건강/암/운전자/실손/뇌심혈관/치매/기타/선택안함
                   - 채    널: TM / CM / POM / 선택안함
                   - 타겟 성별: 여성/남성/전체/선택안함
                   - 타겟 연령대: 20대/30대/40대/50대/60대+/선택안함
                   → conditions['product_type'], ['channel'], ['gender'], ['age_range']
         ↓
  campaign_step=1: 신규 리스트 여부
                   [네, 새로 만들게요] / [아니오, 기존 리스트 활용]
                   → conditions['want_new']
         ↓
  campaign_step=2: 목표 인원 수 (숫자 입력)
                   → conditions['target_count']
         ↓
  campaign_step=3: 추출 방식 선택
                   [과거 실적 기반] → 배정+90일 체결 성공 세그먼트 재현
                   [모델 추천도]    → campaign_score + 고객 활성도 상위
                   [조건 직접 입력] → 자유 텍스트 → LLM 파싱
                   ※ "과거 실적 기반이란?" 토글 설명 제공
                   → conditions['strategy'], conditions['custom_cond']
         ↓
  campaign_step=4: 직전 캠페인 비교 (기존 캠페인 이력 있을 때만)
                   → tbl_ds_campaign_history 직전 동일 캠패인 체결율 조회
                   → "ML 예측 아님, 과거 실적 참고치" 명시
                   → 조건 요약 확인 → [추출] 버튼
                   → DuckDB 조회 → Excel 생성 → 다운로드 링크
```

**룰 베이스 조건 추출 로직:**
```python
# 과거 캠페인 성공 고객 프로파일 추출
SELECT c.CTM_AGE, c.CTM_SEX,
       COUNT(*) FILTER (WHERE ct.CTMNO IS NOT NULL) * 1.0 / COUNT(*) AS success_rate
FROM tbl_ds_campaign_history ch
JOIN tbl_ds_customer c ON ch.CTMNO = c.CTMNO
LEFT JOIN tbl_ds_contract_history ct
       ON ch.CTMNO = ct.CTMNO
      AND ct.INS_ST BETWEEN ch.ASSIGN_DT AND ch.ASSIGN_DT + 90
WHERE ch.CAMPAIGN_NM = :campaign_nm
GROUP BY c.CTM_AGE / 10, c.CTM_SEX   -- 10세 단위 집계
ORDER BY success_rate DESC
LIMIT 3  -- 상위 세그먼트 조건 추출
```

**모델 추천도 조건:**
```python
# 활성도 = 최근 6개월 내 연결성공 OR 배정이력
active_ctmno = """
  SELECT DISTINCT CTMNO FROM tbl_ds_call_detail
  WHERE RESULT_CD = '연결성공'
    AND CALL_DT >= CURRENT_DATE - INTERVAL 6 MONTH
  UNION
  SELECT DISTINCT CTMNO FROM tbl_ds_campaign_history
  WHERE ASSIGN_DT >= CURRENT_DATE - INTERVAL 6 MONTH
"""
# campaign_score 상위 + 활성 고객 교집합 → 정렬
```

---

## 6. 파이프라인 흐름 요약

### Pipeline A — STT (1회성)
1. WAV 디렉토리 스캔
2. **CALL_ID 단위** `collection.get(ids=[call_id])` → 존재하면 skip
3. `Path.stem` → CALL_ID → tbl_call_detail 조회 → CTMNO + 메타데이터
4. tbl_coverage 조회 → 담보금액 12개
5. **tbl_customer 조회 → CTM_AGE, CTM_SEX** (embedded_text 구성용)
6. faster-whisper → 원문
7. Regex 마스킹 (1단계)
8. Qwen3.6 → JSON (masked_text / sentiment / keywords / summary)
9. keywords: list → `",".join(keywords)` 변환 후 metadata 저장
10. **embedded_text 구성**: `f"[고객: {age}세 {sex}, {campaign_nm}] {summary}"`
    → 신규/미연결 고객 RAG 쿼리(인구통계+담보gap 텍스트)와 동일 시맨틱 공간 확보
11. nomic-embed-text → embedded_text 임베딩 → Chroma upsert

### Pipeline B — 문서 인덱싱 (1회성)
1. docs/ 디렉토리 스캔
2. **문서명 단위** `collection.get()` → 존재하면 skip
3. 포맷별 파싱 (PDF→pymupdf4llm / DOCX→mammoth / PPTX→python-pptx)
4. (이미지 포함 시) 비전 LLM 처리
5. nomic-embed-text → Chroma upsert

### Pipeline C — DuckDB 마트 갱신 (매일 cron)
1. **시작 시 mart_new.db 존재하면 무조건 삭제** (이전 실패 잔존 파일 제거)
2. cx_Oracle 접속
3. 도메인별 Oracle 마트 쿼리 실행 (db/oracle_queries.py)
4. **mart_new.db** 에 TRUNCATE & INSERT
5. 완료 후 `mart_new.db` → `mart.db` atomic rename
6. `data/duckdb/last_updated.txt` 에 완료 시각 기록 (UI 갱신 시각 표시용)

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

## 8. Tab2 — 캠페인 추천 대상 생성 상세 플로우

```
[캠페인 선택 리스트 쿼리]
    SELECT DISTINCT CAMPAIGN_NM, CAMPAIGN_TYPE
    FROM tbl_ds_campaign_history
    ORDER BY CAMPAIGN_NM
    -- 체결율 집계 없음 (리스트에 미표시)

[직전 캠페인 비교 쿼리] — Step 4, 기존 캠페인 이력 있을 때만
    SELECT COUNT(*) FILTER (WHERE ct.CTMNO IS NOT NULL) * 1.0 / COUNT(*) AS prev_rate
    FROM tbl_ds_campaign_history ch
    LEFT JOIN tbl_ds_contract_history ct
           ON ch.CTMNO = ct.CTMNO
          AND ct.INS_ST BETWEEN ch.ASSIGN_DT AND ch.ASSIGN_DT + 90
    WHERE ch.CAMPAIGN_NM = :prev_campaign_nm  -- 직전 동일 캠페인명

폼 Q&A Step 0 (신규/기존 동일):
    → 구조화 칩 선택 (상품유형/채널/성별/연령대), 확인 버튼
    → conditions['product_type'], ['channel'], ['gender'], ['age_range']

폼 Q&A Step 1:
    → "신규 추천 대상 리스트를 새로 만들까요?"
    → conditions['want_new'] = True | False

폼 Q&A Step 2:
    → "추출할 목표 인원 수를 입력해주세요." (숫자 입력)
    → conditions['target_count']

폼 Q&A Step 3:
    → 추출 방식: [과거 실적 기반] [모델 추천도] [조건 직접 입력]
    → conditions['strategy'] = 'history' | 'model' | 'custom'
    → strategy='custom': 자유 텍스트 → conditions['custom_cond']

폼 Q&A Step 4:
    → 직전 캠페인 비교 카드 (기존 캠페인 이력 있을 때만, ML 예측 아님 명시)
    → 조건 요약 표시 → [추출] 버튼
    → build_campaign_query(conditions) → DuckDB 실행
    → Excel (CTMNO만) + 접근 전략 요약 (Qwen3.6)
```

---

## 9. Tab1 스크립트 방향 결정 로직 (script_angle)

Tab1 모든 분기에서 DuckDB 조회 후 `script_angle`을 결정하고 Qwen3.6 프롬프트에 명시 전달.

```python
has_contract = len(contract_rows) > 0       # tbl_ds_contract_history
has_design   = len(design_rows) > 0         # tbl_ds_design_history

if has_contract:
    script_angle = "complement"   # 이미 가입 → 담보 gap 기반 보완 상품 추천
elif has_design:
    script_angle = "followup"     # 설계만 있고 미체결 → 해당 설계 건 팔로업
else:
    script_angle = "new_product"  # 이력 없음 → 신상품 연계 공략
```

- 담보 gap이 이미 "무엇이 필요한지"를 나타내므로 이미 가입한 GDCD 필터 불필요
- gd_filter_func + tbl_ds_product_master로 eligible 상품 확정 후 LLM 스크립트 생성
- 이력 고객: 연결성공 있고 체결 없으면 시간 무관하게 같은 각도 유지 (script_angle 로직 그대로)

---

## 10. Chroma RAG 쿼리 전략 (케이스별)

```
이력 고객 → collection.get(where={"CTMNO": ctmno})
            CTMNO 직접 조회, 유사도 검색 아님
            결과 없으면(WAV 없는 고객) 빈 리스트 → 정상 진행

신규/미연결 → collection.query(query_texts=[query_text], where=filter)
              query_text = f"[고객: {age}세 {sex}, {campaign_nm}] {coverage_gap_summary}"
              filter = {"RESULT_CD": "연결성공"} (+ CAMPAIGN_NM 있으면 추가)
              캠페인명 매칭 없으면 filter에서 CAMPAIGN_NM 제거 후 재쿼리

Tab2 모드B  → collection.query(query_texts=[topic_text])
              topic_text = 사용자 입력에서 추출한 스크립트 주제
```

Chroma calls 결과는 선택적 컨텍스트 — 없어도 DuckDB 구조화 데이터 + Products RAG로 스크립트 생성 가능.

---

## 11. 미확정 항목 (Oracle 접속 후 확인)

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
| tbl_ds_product_master Oracle 소스 | GDREC_TMGD_LIST와 동일 마스터 테이블 — 정확한 테이블명 + SALE_END_YN 필터 컬럼명 확인 |
