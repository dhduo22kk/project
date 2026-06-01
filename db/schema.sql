-- DuckDB 스키마 정의
-- 모든 테이블명: tbl_ds_* 패턴
-- Oracle 소스 테이블명: 기존명에 _DS_ 삽입 (oracle_queries.py 참고)

CREATE TABLE IF NOT EXISTS tbl_ds_customer (
    CTMNO            VARCHAR PRIMARY KEY,
    CTM_AGE          INTEGER,
    CTM_SEX          VARCHAR,   -- Oracle 원본값 그대로 (예: '1.M', '2.F')
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
    CALL_DT       TIMESTAMP,  -- 시:분 포함 (시간대 분석용)
    CALL_DURATION INTEGER,    -- 통화시간(초), 30초 기준으로 UI 표시 분기
    RESULT_CD     VARCHAR,    -- "미연결" | "연결성공" (ETL 시 번역 적재)
    CAMPAIGN_NM   VARCHAR,
    CHANNEL_TYPE  VARCHAR     -- TM/CM/POM 등 (Chroma RAG 필터용)
);

CREATE TABLE IF NOT EXISTS tbl_ds_contract_history (
    CTMNO      VARCHAR,
    PLYNO      VARCHAR,   -- 증권번호
    GDCD       VARCHAR,   -- 상품코드
    GDNM       VARCHAR,   -- 상품명
    INS_ST     DATE,      -- 보험시기
    INS_CLSTR  DATE,      -- 보험종기
    AP_PRM     BIGINT,    -- 월 납입 보험료
    CR_STCD    VARCHAR    -- 계약상태코드 (정상 계약 필터용)
);

CREATE TABLE IF NOT EXISTS tbl_ds_campaign_history (
    CTMNO           VARCHAR,
    CAMPAIGN_NM     VARCHAR,
    ASSIGN_DT       DATE,
    MSG_SEND_DT     DATE,     -- null = 문자 미발송
    CAMPAIGN_TYPE   VARCHAR   -- TM/CM
);

CREATE TABLE IF NOT EXISTS tbl_ds_design_history (
    CTMNO       VARCHAR,
    DESIGN_DT   DATE,
    GDCD        VARCHAR,
    GDNM        VARCHAR,
    DESIGN_PRM  BIGINT,   -- 설계보험료
    RESULT_CD   VARCHAR   -- 체결/미체결
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
    REC_RANK   INTEGER,  -- 추천순위 1/2/3
    REC_GDCD   VARCHAR,
    REC_GDNM   VARCHAR,
    REC_POCT   FLOAT    -- 구매확률 0~1
);

-- tbl_ds_campaign_score 제거: ML 점수 테이블 MVP 스코프 제외
-- 활성도 기반 DuckDB 집계로 대체 (tbl_ds_call_detail + tbl_ds_campaign_history)

CREATE TABLE IF NOT EXISTS tbl_ds_product_master (
    GDCD        VARCHAR PRIMARY KEY,
    GD_TYPE     VARCHAR,   -- L01, L03, L04, SS, 유병자 등
    GDNM        VARCHAR,
    GDNM_CLEAN  VARCHAR    -- 괄호/연월 제거된 상품명 (gd_filter_func 반환값과 매칭)
);

CREATE TABLE IF NOT EXISTS tbl_ds_sales_focus (
    FOCUS_YM    VARCHAR PRIMARY KEY,  -- '2026-06' (월 단위 키)
    FOCUS_TEXT  VARCHAR,              -- 자유형식 전문 (주력상품/이슈/제외상품 등)
    UPDATED_AT  TIMESTAMP             -- 마지막 수정 시각
);

CREATE TABLE IF NOT EXISTS tbl_ds_msg_history (
    CTMNO       VARCHAR,
    SEND_DT     TIMESTAMP,  -- 발송일시
    MSG_CONTENT VARCHAR,    -- 문자 내용 (SMS/LMS 텍스트)
    MSG_TYPE    VARCHAR     -- 'SMS' | 'LMS' | 'MMS'
);
