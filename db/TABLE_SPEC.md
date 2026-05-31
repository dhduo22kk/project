# DuckDB 적재 테이블 명세

> Oracle 쿼리 작성 참고용. Oracle 테이블명은 기존 이름에 `_DS_` 삽입 패턴 적용.
> MVP 범위 테이블만 포함. 이월 항목은 하단 별도 표기.

---

## 1. tbl_ds_customer — 고객 기본정보

**Oracle 소스**: `CUS_DS_CTM` LEFT JOIN `GDREC_DS_ORIGIN_MAIN_FIN_PRED`
**행 수**: ~30만 명 (신규 고객 포함, 계약 없는 고객도 포함)
**갱신**: 매일 cron

| 컬럼 | 타입 | 설명 | 비고 |
|------|------|------|------|
| CTMNO | VARCHAR | 고객번호 (PK) | |
| CTM_AGE | INTEGER | 나이 | |
| CTM_SEX | VARCHAR | 성별 (1=남 / 2=여) | |
| REGION | VARCHAR | 지역 | |
| REG_DT | DATE | 등록일 | |
| INFLOW_CAMPAIGN_NM | VARCHAR | 유입 캠페인명 | tbl_ds_campaign_history에서 JOIN |
| HOSP_CLAIM | VARCHAR | 입원청구 | 유병자 판단용, 컴플라이언스 승인 완료 |
| HOSP_NOTI | VARCHAR | 입원고지 | 유병자 판단용 |
| MAJOR_DSAS_NOTI | VARCHAR | 중대질환고지 | 유병자 판단용 |
| MAJOR_DSAS_CLAIM | VARCHAR | 중대질환청구 | 유병자 판단용 |

---

## 2. tbl_ds_coverage — 보장분석 대분류 담보금액 (wide)

**Oracle 소스**: `GDREC_DS_ORIGIN_MAIN_FIN_PRED` (최종 마트, 단순 SELECT)
**행 수**: 기존 계약 고객만. 신규 고객은 row 없음 → LEFT JOIN 시 null
**갱신**: 매일 cron

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

---

## 3. tbl_ds_call_detail — 통화이력

**Oracle 소스**: TODO (`_DS_` 패턴 적용)
**용도**: Tab1 3분기 분기 핵심, Chroma Pipeline A 매핑
**갱신**: 매일 cron

| 컬럼 | 타입 | 설명 | 비고 |
|------|------|------|------|
| CALL_ID | VARCHAR | 통화ID (PK) | WAV 파일명 = CALL_ID.wav |
| CTMNO | VARCHAR | 고객번호 | |
| CALL_DT | TIMESTAMP | 통화일시 | 시:분 포함 필수 (시간대 분석용) |
| CALL_DURATION | INTEGER | 통화시간 (초) | 30초 기준으로 UI 표시 분기 |
| RESULT_CD | VARCHAR | 통화 결과 | Oracle 코드 → **"미연결"/"연결성공"** 으로 ETL 시 번역 저장 |
| CAMPAIGN_NM | VARCHAR | 캠페인명 | |
| CHANNEL_TYPE | VARCHAR | 채널 유형 | TM/CM/POM 등, Chroma 메타데이터 필터용 |

> **RESULT_CD 적재 규칙**: Oracle 원본 코드는 저장하지 않음. ETL에서 CASE WHEN으로 번역.
> 결번/무응답 계열 코드 → `"미연결"`, 실제 통화 계열 코드 → `"연결성공"`

---

## 4. tbl_ds_contract_history — 계약이력

**Oracle 소스**: TODO (`_DS_` 패턴 적용)
**용도**: 가입 상품 수, 월 납입 보험료 합계, 최근 가입 시점 집계
**갱신**: 매일 cron

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| PLYNO | VARCHAR | 증권번호 |
| GDCD | VARCHAR | 상품코드 |
| GDNM | VARCHAR | 상품명 |
| INS_ST | DATE | 보험시기 |
| INS_CLSTR | DATE | 보험종기 |
| AP_PRM | BIGINT | 월 납입 보험료 |
| CR_STCD | VARCHAR | 계약상태코드 (정상 계약 필터용) |

---

## 5. tbl_ds_campaign_history — 캠페인·배정이력

**Oracle 소스**: TODO (`_DS_` 패턴 적용)
**용도**: 유입 캠페인명 조회, Tab2 모드C 과거 성과 분석
**갱신**: 매일 cron

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| CAMPAIGN_NM | VARCHAR | 캠페인명 |
| ASSIGN_DT | DATE | 배정일 |
| MSG_SEND_DT | DATE | 문자발송일 (null = 미발송) |
| CAMPAIGN_TYPE | VARCHAR | 캠페인 유형 (TM/CM) |

---

## 6. tbl_ds_design_history — 설계이력

**Oracle 소스**: TODO (`_DS_` 패턴 적용)
**용도**: Tab1 이력 고객 설계 여부 확인
**갱신**: 매일 cron

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| DESIGN_DT | DATE | 설계일 |
| GDCD | VARCHAR | 상품코드 |
| GDNM | VARCHAR | 상품명 |
| DESIGN_PRM | BIGINT | 설계보험료 |
| RESULT_CD | VARCHAR | 결과 (체결/미체결) |

---

## 7. tbl_ds_new_coverage — 3개월 내 신규 가입 담보

**Oracle 소스**: `INS_DS_CR_CVR` 계열, `CVR_START_DT >= SYSDATE - 90` 필터
**용도**: Tab1 계약 현황 "NEW" 표시, 스크립트 "최근 가입하신 [담보명]과 연계하여"
**갱신**: 매일 cron

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| CVR_CD | VARCHAR | 담보코드 |
| CVR_NM | VARCHAR | 담보명 |
| CVR_START_DT | DATE | 담보 가입일 |
| ISAMT | BIGINT | 가입금액 |

---

## 8. tbl_ds_recommendation — 레거시 ML 추천결과

**Oracle 소스**: `M_DS_CRM_REC_RLT_BIZ`
**용도**: Tab1 추천 상품 조회 (신규 고객은 row 없음 → RAG로 대체)
**갱신**: 매일 cron

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| REC_RANK | INTEGER | 추천순위 (1/2/3) |
| REC_GDCD | VARCHAR | 추천상품코드 |
| REC_GDNM | VARCHAR | 추천상품명 |
| REC_POCT | FLOAT | 구매확률 (0~1) |

> REC_RS1 (기존 스크립트 텍스트) 제외

---

## 9. tbl_ds_campaign_score — 캠페인 추천도 점수

**Oracle 소스**: 외부 모델 결과 테이블 (TODO)
**용도**: Tab2 모드C 고객 리스트 생성 시 SCORE 높은 순 정렬
**갱신**: 외부 모델 재스코어링 주기에 따름

| 컬럼 | 타입 | 설명 |
|------|------|------|
| CTMNO | VARCHAR | 고객번호 |
| CAMPAIGN_TYPE | VARCHAR | 캠페인 유형 (TM/CM) |
| SCORE | FLOAT | 추천도 점수 (0~1) |
| SCORE_DT | DATE | 스코어 생성일 |

---

## 이월 항목 (MVP 제외)

| 테이블 | 이유 |
|--------|------|
| tbl_ds_coverage_detail | 담보코드 단위 LIKE 검색 — Tab2 모드A 자유질의용, MVP 이후 |
| tbl_ds_cvr_group_map | LLM 초안 + 전문가 검수 필요, 1회성 작업 |
| tbl_ds_change_log | M4 구현 예정 |

---

## Chroma calls 메타데이터 (Pipeline A 적재 시)

STT 인덱싱 시 `tbl_ds_call_detail`에서 함께 가져와야 하는 필드:

| 필드 | 출처 |
|------|------|
| CALL_ID | tbl_ds_call_detail |
| CTMNO | tbl_ds_call_detail |
| CALL_DURATION | tbl_ds_call_detail |
| RESULT_CD | tbl_ds_call_detail ("미연결"/"연결성공") |
| CAMPAIGN_NM | tbl_ds_call_detail |
| CHANNEL_TYPE | tbl_ds_call_detail |
| 담보금액 12개 컬럼 | tbl_ds_coverage LEFT JOIN |
| masked_text | Pipeline A LLM 생성 |
| sentiment | Pipeline A LLM 생성 (우호적/비우호적) |
| keywords | Pipeline A LLM 생성 (comma-separated string) |
| summary | Pipeline A LLM 생성 (임베딩 대상) |
