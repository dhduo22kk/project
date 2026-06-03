/*
================================================================================
  oracle_queries.sql  —  Oracle 추출 테이블 생성 (AI 상담 에이전트 DuckDB 적재용)

  실행 환경: Oracle SQL Developer / Toad / sqlplus
  실행 후:   pipeline_c_duckdb.py 가 각 AI_* 테이블을 SELECT * 하여 DuckDB 적재

  테이블 명명: AI_* 접두어 (기존 운영 테이블과 충돌 방지)
  갱신 방식:   DROP(safe) → CREATE NOLOGGING AS SELECT
================================================================================
*/

-- 세션 설정 (스크립트 시작 시 1회)
ALTER SESSION ENABLE PARALLEL DDL;
ALTER SESSION ENABLE PARALLEL DML;
ALTER SESSION FORCE PARALLEL QUERY PARALLEL 8;
ALTER SESSION SET db_file_multiblock_read_count = 128;

-- ============================================================
-- 공통: 기준 월 (전월 YYYYMM)
--   TO_CHAR(ADD_MONTHS(SYSDATE, -1), 'YYYYMM')
-- ============================================================


-- ──────────────────────────────────────────────────────────────────────────────
-- [1] 고객 기본정보  →  AI_CUSTOMER  (DuckDB: tbl_ds_customer)
--     소스: CUS_CTM (~30만) LEFT JOIN GDREC_DS_ORIGIN_MAIN_FIN_PRED (유병자 4컬럼)
--     검증: REGION 컬럼명 확인 필요 (CTM_ADDR1 등)
--           INFLOW_CAMPAIGN_NM 은 캠페인 쿼리 수령 후 채울 것
-- ──────────────────────────────────────────────────────────────────────────────
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE AI_CUSTOMER PURGE';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

CREATE TABLE AI_CUSTOMER NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    A.CTMNO,
    CASE
        WHEN F_ISDATE(F_BIRTH_DAY_DEC(A.CTM_DSCNO)) = 'T'
        THEN TRUNC(
                 MONTHS_BETWEEN(SYSDATE,
                     TO_DATE(F_BIRTH_DAY_DEC(A.CTM_DSCNO), 'YYYYMMDD')
                 ) / 12
             )
    END                                   AS CTM_AGE,
    CASE
        WHEN F_SEX_DEC(A.CTM_DSCNO) = 'M' THEN '1.M'
        WHEN F_SEX_DEC(A.CTM_DSCNO) = 'F' THEN '2.F'
    END                                   AS CTM_SEX,
    NULL                                  AS REGION,             -- TODO: CTM_ADDR1 등 확인
    A.CTM_RGDT                            AS REG_DT,
    NULL                                  AS INFLOW_CAMPAIGN_NM, -- TODO: 캠페인 쿼리 수령 후 추가
    B.HOSP_CLAIM,
    B.HOSP_NOTI,
    B.MAJOR_DSAS_NOTI,
    B.MAJOR_DSAS_CLAIM
FROM CUS_CTM A
LEFT JOIN (
    SELECT /*+ PARALLEL(8) */
        MN_NRDPS_CTMNO,
        MIN(입원청구)    AS HOSP_CLAIM,
        MIN(입원고지)    AS HOSP_NOTI,
        MIN(중대질환고지) AS MAJOR_DSAS_NOTI,
        MIN(중대질환청구) AS MAJOR_DSAS_CLAIM
    FROM GDREC_DS_ORIGIN_MAIN_FIN_PRED
    WHERE CLS_YYMM = TO_CHAR(ADD_MONTHS(SYSDATE, -1), 'YYYYMM')
    GROUP BY MN_NRDPS_CTMNO
) B ON A.CTMNO = B.MN_NRDPS_CTMNO;


-- ──────────────────────────────────────────────────────────────────────────────
-- [2] 보장 대분류 담보금액  →  AI_COVERAGE  (DuckDB: tbl_ds_coverage)
--     소스: GDREC_DS_ORIGIN_MAIN_FIN_PRED (직전월 기준, SUM 집계)
-- ──────────────────────────────────────────────────────────────────────────────
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE AI_COVERAGE PURGE';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

CREATE TABLE AI_COVERAGE NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    MN_NRDPS_CTMNO                        AS CTMNO,
    SUM(NVL(CANCR_DASCS_AMT,           0)) AS CANCR_DASCS_AMT,
    SUM(NVL(ISMC_HEART_DSAS_DASCS_AMT, 0)) AS ISMC_HEART_DSAS_DASCS_AMT,
    SUM(NVL(CRLR_DSAS_DASCS_AMT,       0)) AS CRLR_DSAS_DASCS_AMT,
    SUM(NVL(DSAS_HSP_RLPMI_AMT,        0)) AS DSAS_HSP_RLPMI_AMT,
    SUM(NVL(DSAS_OTP_RLPMI_AMT,        0)) AS DSAS_OTP_RLPMI_AMT,
    SUM(NVL(SERI_DEMEN_AMT,            0)) AS SERI_DEMEN_AMT,
    SUM(NVL(LTRM_RCPR_DGN_RANK4_AMT,  0)) AS LTRM_RCPR_DGN_RANK4_AMT,
    SUM(NVL(BDIN_CCA_SUAMT_AMT,        0)) AS BDIN_CCA_SUAMT_AMT,
    SUM(NVL(LWR_SNRT_CS_AMT,           0)) AS LWR_SNRT_CS_AMT,
    SUM(NVL(DRV_PNLTY_AMT,            0)) AS DRV_PNLTY_AMT,
    SUM(NVL(FIRE_PNLTY_AMT,           0)) AS FIRE_PNLTY_AMT,
    SUM(NVL(USLLF_LBTRS_AMT,          0)) AS USLLF_LBTRS_AMT
FROM GDREC_DS_ORIGIN_MAIN_FIN_PRED
WHERE CLS_YYMM = TO_CHAR(ADD_MONTHS(SYSDATE, -1), 'YYYYMM')
GROUP BY MN_NRDPS_CTMNO;


-- ──────────────────────────────────────────────────────────────────────────────
-- [3] 계약이력  →  AI_CONTRACT  (DuckDB: tbl_ds_contract_history)
--     소스: M_DS_CRM_MTHY_PS_CR (직전월 스냅샷, 현재 유효 계약 전체)
--     검증: LTRM_MPY_CV_PRM 컬럼명 (월납환산보험료)
-- ──────────────────────────────────────────────────────────────────────────────
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE AI_CONTRACT PURGE';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

CREATE TABLE AI_CONTRACT NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    R.CTMNO,
    A.PLYNO,
    A.GDCD,
    NVL(G.GDNM_CLEAN, A.GDCD)  AS GDNM,
    A.INS_ST,
    A.INS_CLSTR,
    A.LTRM_MPY_CV_PRM           AS AP_PRM,
    A.CR_STCD
FROM M_DS_CRM_MTHY_PS_CR A
INNER JOIN INS_CR_RELPC R
    ON  A.PLYNO              = R.PLYNO
    AND R.IKD_GRPCD          = 'LA'
    AND R.RELPC_TPCD         = '01'
    AND R.RELPC_STCD         IN ('01','04')
    AND R.NDS_AP_STR_DTHMS  <= SYSDATE
    AND R.NDS_AP_ND_DTHMS    > SYSDATE
    AND R.VALD_NDS_YN        = '1'
LEFT JOIN M_DS_CRM_REC_GDNM_TM G ON A.GDCD = G.GDCD
WHERE A.CLS_YYMM  = TO_CHAR(ADD_MONTHS(SYSDATE, -1), 'YYYYMM')
  AND A.IKD_GRPCD = 'LA';


-- ──────────────────────────────────────────────────────────────────────────────
-- [4] 설계이력  →  AI_DESIGN  (DuckDB: tbl_ds_design_history)
--     소스: INS_INS_PL + INS_PL_RELPC (계약자, 유효 설계 전체)
--     검증: DESIGN_PRM 소스 컬럼 (설계보험료)
-- ──────────────────────────────────────────────────────────────────────────────
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE AI_DESIGN PURGE';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

CREATE TABLE AI_DESIGN NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    R.CTMNO,
    A.PLDT                                                    AS DESIGN_DT,
    A.GDCD,
    NVL(G.GDNM_CLEAN, A.GDCD)                                AS GDNM,
    NULL                                                      AS DESIGN_PRM, -- TODO: 설계보험료 컬럼 확인
    CASE
        WHEN A.PL_STCD IN ('03','04','05','06','07','08','09') THEN '체결'
        ELSE '미체결'
    END                                                       AS RESULT_CD
FROM INS_INS_PL A
INNER JOIN INS_PL_RELPC R
    ON  A.PLNO          = R.PLNO
    AND A.CGAF_CH_SEQNO = R.CGAF_CH_SEQNO
    AND R.IKD_GRPCD     = 'LA'
    AND R.RELPC_TPCD    = '01'
LEFT JOIN M_CRM_GD_CSF_INFO G ON A.GDCD = G.GDCD
WHERE A.PL_FLGCD   = '01'
  AND A.IKD_GRPCD  = 'LA'
  AND A.VALD_PL_YN = '1';


-- ──────────────────────────────────────────────────────────────────────────────
-- [5] 신규 담보 (3개월 이내)  →  AI_NEW_CVR  (DuckDB: tbl_ds_new_coverage)
--     소스: INS_CR_CVR + INS_CR_RELPC (피보험자)
-- ──────────────────────────────────────────────────────────────────────────────
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE AI_NEW_CVR PURGE';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

CREATE TABLE AI_NEW_CVR NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    R.CTMNO,
    C.CVRCD                     AS CVR_CD,
    NVL(G.CVR_PRSNM, C.CVRCD)  AS CVR_NM,
    C.INS_ST                    AS CVR_START_DT,
    C.ISAMT
FROM INS_CR_CVR C
INNER JOIN INS_CR_RELPC R
    ON  C.PLYNO             = R.PLYNO
    AND R.IKD_GRPCD         = 'LA'
    AND R.RELPC_TPCD        = '02'
    AND R.RELPC_STCD        IN ('01','04')
    AND R.NDS_AP_STR_DTHMS <= SYSDATE
    AND R.NDS_AP_ND_DTHMS   > SYSDATE
    AND R.VALD_NDS_YN       = '1'
LEFT JOIN IGD_GD_CVR G
    ON  C.CVRCD     = G.CVRCD
    AND C.GDCD      = G.GDCD
    AND G.AP_STRDT <= SYSDATE
    AND G.AP_NDDT   > SYSDATE
WHERE C.IKD_GRPCD    = 'LA'
  AND C.CVR_STCD     IN ('01','07','08')
  AND C.CVR_BJ_FLGCD IN ('01','03')
  AND C.INS_ST       >= ADD_MONTHS(SYSDATE, -3)
  AND C.VALD_NDS_YN  = '1'
  AND C.NDS_AP_ND_DTHMS > SYSDATE;


-- ──────────────────────────────────────────────────────────────────────────────
-- [6] ML 추천결과 (레거시)  →  AI_RECOMM  (DuckDB: tbl_ds_recommendation)
--     소스: M_DS_CRM_REC_RLT_BIZ (REC_RS1 제외, 상위 3개)
--     검증: REC_POCT 컬럼 없으면 NULL AS REC_POCT
-- ──────────────────────────────────────────────────────────────────────────────
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE AI_RECOMM PURGE';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

CREATE TABLE AI_RECOMM NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    CTMNO,
    REC_RANK,
    REC_GDCD,
    REC_GDNM,
    REC_POCT
FROM M_DS_CRM_REC_RLT_BIZ
WHERE REC_RANK <= 3;


-- ──────────────────────────────────────────────────────────────────────────────
-- [7] 판매중 TM 상품 마스터  →  AI_PRODUCT  (DuckDB: tbl_ds_product_master)
--     소스: IGD_GD_SL_TRM + M_CRM_GD_CSF_INFO + M_DS_CRM_REC_GDNM_TM
--     검증: TB_LNG_BJONG_MASTER 테이블명, SALE_END_YN 컬럼
-- ──────────────────────────────────────────────────────────────────────────────
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE AI_PRODUCT PURGE';
EXCEPTION WHEN OTHERS THEN NULL;
END;
/

CREATE TABLE AI_PRODUCT NOLOGGING AS
SELECT /*+ PARALLEL(8) */ DISTINCT
    A.GDCD,
    CASE
        WHEN B.GDNM LIKE '%Young%'                                            THEN 'L04'
        WHEN B.GDNM LIKE '%더건강 더실속%' OR B.MKTG_GD_CSFCD IN ('L02','L01') THEN 'L01'
        WHEN B.GDNM LIKE '%더건강%'                                           THEN 'L01'
        WHEN B.GDNM LIKE '%시그니처 여성 건강%'                               THEN 'L01'
        WHEN B.MKTG_GD_CSFCD = 'L03' THEN 'L03'
        WHEN B.MKTG_GD_CSFCD = 'L04' THEN 'L04'
        WHEN B.MKTG_GD_CSFCD = 'L06' THEN 'L06'
        WHEN B.MKTG_GD_CSFCD = 'L08' THEN 'L08'
        WHEN B.MKTG_GD_CSFCD = 'L11' THEN 'L11'
        WHEN B.GDNM LIKE '%세이프투게더%'                                     THEN 'SAFE'
        WHEN B.GDNM LIKE '%실손의료보험%'                                     THEN 'SS'
        WHEN REGEXP_LIKE(B.GDNM, '참 편한|WELL100|간편|3N5|355')             THEN '유병자'
        WHEN B.MKTG_GD_CSFCD IN ('L12','L13')                               THEN 'L123'
        ELSE 'ETC'
    END                              AS GD_TYPE,
    B.GDNM,
    NVL(C.GDNM_CLEAN, B.GDNM)       AS GDNM_CLEAN
FROM IGD_GD_SL_TRM A
LEFT JOIN M_CRM_GD_CSF_INFO    B ON A.GDCD     = B.GDCD
LEFT JOIN M_DS_CRM_REC_GDNM_TM C ON A.GDCD     = C.GDCD
LEFT JOIN IGD_GD_SL_CHN_REL    D ON A.GDCD     = D.GDCD
LEFT JOIN SL_CHNCD             E ON D.SL_CHNCD = E.SL_CHNCD
WHERE A.SL_NDDT  >= SYSDATE
  AND A.GDCD     LIKE '%LA%'
  AND E.DTCNM    = 'TM'
  AND A.GDCD     IN (
      SELECT GDCD FROM TB_LNG_BJONG_MASTER WHERE SALE_END_YN = 'Y'
  );


-- ──────────────────────────────────────────────────────────────────────────────
-- TODO: 별도 수령 예정 (소스 테이블 미확정)
-- ──────────────────────────────────────────────────────────────────────────────
-- [8]  통화이력         AI_CALL_DETAIL    (DuckDB: tbl_ds_call_detail)      최근 3년
-- [9]  캠페인이력       AI_CAMPAIGN       (DuckDB: tbl_ds_campaign_history)  최근 3년
-- [10] 캠페인 추천도    AI_CAMP_SCORE     (DuckDB: tbl_ds_campaign_score)
-- [11] 문자발송이력     AI_MSG_HISTORY    (DuckDB: tbl_ds_msg_history)
