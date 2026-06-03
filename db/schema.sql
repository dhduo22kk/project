-- DuckDB 스키마 정의
-- 모든 테이블명: tbl_ds_* 패턴
-- Oracle 소스: oracle_queries.sql → AI_* 테이블 → pipeline_c_duckdb.py → DuckDB

CREATE TABLE IF NOT EXISTS tbl_ds_customer (
    CTMNO            VARCHAR PRIMARY KEY,
    CTM_AGE          INTEGER,
    CTM_SEX          VARCHAR,   -- Oracle 원본값 그대로 ('1.M', '2.F')
    REGION           VARCHAR,
    REG_DT           DATE,
    INFLOW_CAMPAIGN_NM VARCHAR,
    -- 유병자 판단용 (컴플라이언스 승인 완료)
    HOSP_CLAIM       VARCHAR,
    HOSP_NOTI        VARCHAR,
    MAJOR_DSAS_NOTI  VARCHAR,
    MAJOR_DSAS_CLAIM VARCHAR
);

CREATE TABLE IF NOT EXISTS tbl_ds_coverage (
    CTMNO                    VARCHAR PRIMARY KEY,
    CANCR_DASCS_AMT          BIGINT,  -- 암진단비
    ISMC_HEART_DSAS_DASCS_AMT BIGINT, -- 허혈성심장질환진단비
    CRLR_DSAS_DASCS_AMT      BIGINT,  -- 뇌혈관질환진단비
    DSAS_HSP_RLPMI_AMT       BIGINT,  -- 질병입원실손
    DSAS_OTP_RLPMI_AMT       BIGINT,  -- 질병통원실손
    SERI_DEMEN_AMT           BIGINT,  -- 중증치매
    LTRM_RCPR_DGN_RANK4_AMT  BIGINT,  -- 장기요양진단4급
    BDIN_CCA_SUAMT_AMT       BIGINT,  -- 대인형사합의지원금
    LWR_SNRT_CS_AMT          BIGINT,  -- 변호사선임비용
    DRV_PNLTY_AMT            BIGINT,  -- 운전자벌금
    FIRE_PNLTY_AMT           BIGINT,  -- 화재벌금
    USLLF_LBTRS_AMT          BIGINT   -- 일상생활배상책임
);

CREATE TABLE IF NOT EXISTS tbl_ds_call_detail (
    CALL_ID       VARCHAR PRIMARY KEY,
    CTMNO         VARCHAR,
    CALL_DT       TIMESTAMP,  -- 통화 일시
    CALL_DURATION INTEGER,    -- 통화시간(초): TB_CONTACT.INTIME
    RESULT_CD     VARCHAR,    -- '미연결' | '연결성공' | '결번' | '타인통화' (ETL 시 번역)
    CAMPAIGN_NM   VARCHAR,
    CHANNEL_TYPE  VARCHAR     -- TM/CM/POM (Chroma RAG 필터용)
);

CREATE TABLE IF NOT EXISTS tbl_ds_contract_history (
    CTMNO      VARCHAR,
    PLYNO      VARCHAR,
    GDCD       VARCHAR,
    GDNM       VARCHAR,
    INS_ST     DATE,
    INS_CLSTR  DATE,
    AP_PRM     BIGINT,    -- 월 납입 보험료
    CR_STCD    VARCHAR
);

CREATE TABLE IF NOT EXISTS tbl_ds_campaign_history (
    CTMNO           VARCHAR,
    CAMPAIGN_NM     VARCHAR,
    ASSIGN_DT       DATE,
    MSG_SEND_DT     DATE,
    CAMPAIGN_TYPE   VARCHAR   -- TM/CM
);

CREATE TABLE IF NOT EXISTS tbl_ds_design_history (
    CTMNO       VARCHAR,
    DESIGN_DT   DATE,
    GDCD        VARCHAR,
    GDNM        VARCHAR,
    DESIGN_PRM  BIGINT,
    RESULT_CD   VARCHAR   -- '체결' | '미체결'
);

CREATE TABLE IF NOT EXISTS tbl_ds_new_coverage (
    CTMNO        VARCHAR,
    CVR_CD       VARCHAR,
    CVR_NM       VARCHAR,
    CVR_START_DT DATE,
    ISAMT        BIGINT
);

CREATE TABLE IF NOT EXISTS tbl_ds_recommendation (
    CTMNO      VARCHAR,
    REC_RANK   INTEGER,
    REC_GDCD   VARCHAR,
    REC_GDNM   VARCHAR,
    REC_POCT   FLOAT
);

CREATE TABLE IF NOT EXISTS tbl_ds_ineligible (
    CTMNO  VARCHAR,
    GDCD   VARCHAR
    -- 소스: GDREC_CTM_FILTER_1(나이/성별/고지포기) + GDREC_CTM_FILTER_2(보장충족)
    -- 쿼리 타임에 이 테이블로 추천 제외 필터 적용
);

CREATE TABLE IF NOT EXISTS tbl_ds_contact_exclusion (
    CTMNO       VARCHAR,
    EXCL_REASON VARCHAR  -- '두낫콜' | '전화임시거절' | '결번' | '인수유의자' | '스케줄예약'
    -- Tab2 캠페인 추출 시 연락 불가 고객 제외 필터
    -- AI_INELIGIBLE(상품 가입 불가)과 다른 개념
);

CREATE TABLE IF NOT EXISTS tbl_ds_cmpg_result (
    CTMNO        VARCHAR,
    CAMPAIGN_NM  VARCHAR,
    ASSIGN_DT    DATE,
    CONTRACT_YN  INTEGER,   -- 배정일 기준 90일 내 체결: 1=성공, 0=미체결
    CONTRACT_DT  DATE,      -- 체결일 (미체결이면 NULL)
    CONTRACT_PRM BIGINT     -- 체결 월납보험료 (미체결이면 NULL)
    -- Tab2 "과거 실적 기반" 전략: 성공 세그먼트 조건 재현에 사용
    -- CAMPAIGN_SUCCESS_DAYS = 90 (settings.py 상수)
);

CREATE TABLE IF NOT EXISTS tbl_ds_product_master (
    GDCD        VARCHAR PRIMARY KEY,
    GD_TYPE     VARCHAR,
    GDNM        VARCHAR,
    GDNM_CLEAN  VARCHAR
);

CREATE TABLE IF NOT EXISTS tbl_ds_sales_focus (
    FOCUS_YM    VARCHAR PRIMARY KEY,  -- 'YYYYMM'
    FOCUS_TEXT  VARCHAR,
    UPDATED_AT  TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tbl_ds_msg_history (
    CTMNO       VARCHAR,
    SEND_DT     TIMESTAMP,
    MSG_CONTENT VARCHAR,
    MSG_TYPE    VARCHAR   -- 'SMS' | 'LMS' | 'MMS'
);
