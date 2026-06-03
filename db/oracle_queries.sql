/*
================================================================================
  oracle_queries.sql  —  Oracle AI_* 추출 테이블 생성 (DuckDB 적재용)

  실행 환경: Oracle SQL Developer / Toad / sqlplus
  실행 후:   pipeline_c_duckdb.py 가 각 AI_* 테이블을 SELECT * 하여 DuckDB 적재

  실행 순서:
    1. (선행) 레거시 배치 실행 → GDREC_ORIGIN_MAIN_FIN_PRED, M_CRM_REC_RLT_BIZ,
                                  GDREC_CTM_FILTER_1, GDREC_CTM_FILTER_2 갱신
    2. 이 스크립트 실행 → AI_* 테이블 생성
    3. pipeline_c_duckdb.py 실행 → DuckDB 적재

  테이블 명명: AI_* 접두어 (운영 테이블과 충돌 방지)
  갱신 방식:   DROP(safe) → CREATE NOLOGGING AS SELECT
================================================================================
*/

ALTER SESSION ENABLE PARALLEL DDL;
ALTER SESSION ENABLE PARALLEL DML;
ALTER SESSION FORCE PARALLEL QUERY PARALLEL 8;
ALTER SESSION SET db_file_multiblock_read_count = 128;


-- ============================================================
-- [1] 고객 기본정보  →  AI_CUSTOMER  (tbl_ds_customer)
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_CUSTOMER PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_CUSTOMER NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    A.CTMNO,
    CASE
        WHEN F_ISDATE(F_BIRTH_DAY_DEC(A.CTM_DSCNO)) = 'T'
        THEN TRUNC(MONTHS_BETWEEN(SYSDATE, TO_DATE(F_BIRTH_DAY_DEC(A.CTM_DSCNO),'YYYYMMDD')) / 12)
    END                                   AS CTM_AGE,
    CASE
        WHEN F_SEX_DEC(A.CTM_DSCNO) = 'M' THEN '1.M'
        WHEN F_SEX_DEC(A.CTM_DSCNO) = 'F' THEN '2.F'
    END                                   AS CTM_SEX,
    NULL                                  AS REGION,              -- TODO: CTM_ADDR1 등 확인
    A.CTM_RGDT                            AS REG_DT,
    NULL                                  AS INFLOW_CAMPAIGN_NM,  -- TODO: 캠페인 쿼리 확인 후 추가
    B.HOSP_CLAIM,
    B.HOSP_NOTI,
    B.MAJOR_DSAS_NOTI,
    B.MAJOR_DSAS_CLAIM
FROM CUS_CTM A
LEFT JOIN (
    SELECT /*+ PARALLEL(8) */
        MN_NRDPS_CTMNO,
        MIN(입원청구)     AS HOSP_CLAIM,
        MIN(입원고지)     AS HOSP_NOTI,
        MIN(중대질환고지)  AS MAJOR_DSAS_NOTI,
        MIN(중대질환청구)  AS MAJOR_DSAS_CLAIM
    FROM GDREC_DS_ORIGIN_MAIN_FIN_PRED
    WHERE CLS_YYMM = TO_CHAR(ADD_MONTHS(SYSDATE,-1),'YYYYMM')
    GROUP BY MN_NRDPS_CTMNO
) B ON A.CTMNO = B.MN_NRDPS_CTMNO;


-- ============================================================
-- [2] 보장 대분류 담보금액  →  AI_COVERAGE  (tbl_ds_coverage)
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_COVERAGE PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_COVERAGE NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    MN_NRDPS_CTMNO                         AS CTMNO,
    SUM(NVL(CANCR_DASCS_AMT,            0)) AS CANCR_DASCS_AMT,
    SUM(NVL(ISMC_HEART_DSAS_DASCS_AMT,  0)) AS ISMC_HEART_DSAS_DASCS_AMT,
    SUM(NVL(CRLR_DSAS_DASCS_AMT,        0)) AS CRLR_DSAS_DASCS_AMT,
    SUM(NVL(DSAS_HSP_RLPMI_AMT,         0)) AS DSAS_HSP_RLPMI_AMT,
    SUM(NVL(DSAS_OTP_RLPMI_AMT,         0)) AS DSAS_OTP_RLPMI_AMT,
    SUM(NVL(SERI_DEMEN_AMT,             0)) AS SERI_DEMEN_AMT,
    SUM(NVL(LTRM_RCPR_DGN_RANK4_AMT,   0)) AS LTRM_RCPR_DGN_RANK4_AMT,
    SUM(NVL(BDIN_CCA_SUAMT_AMT,         0)) AS BDIN_CCA_SUAMT_AMT,
    SUM(NVL(LWR_SNRT_CS_AMT,            0)) AS LWR_SNRT_CS_AMT,
    SUM(NVL(DRV_PNLTY_AMT,             0)) AS DRV_PNLTY_AMT,
    SUM(NVL(FIRE_PNLTY_AMT,            0)) AS FIRE_PNLTY_AMT,
    SUM(NVL(USLLF_LBTRS_AMT,           0)) AS USLLF_LBTRS_AMT
FROM GDREC_DS_ORIGIN_MAIN_FIN_PRED
WHERE CLS_YYMM = TO_CHAR(ADD_MONTHS(SYSDATE,-1),'YYYYMM')
GROUP BY MN_NRDPS_CTMNO;


-- ============================================================
-- [3] 계약이력  →  AI_CONTRACT  (tbl_ds_contract_history)
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_CONTRACT PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
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
    ON  A.PLYNO             = R.PLYNO
    AND R.IKD_GRPCD         = 'LA'
    AND R.RELPC_TPCD        = '01'
    AND R.RELPC_STCD        IN ('01','04')
    AND R.NDS_AP_STR_DTHMS <= SYSDATE
    AND R.NDS_AP_ND_DTHMS   > SYSDATE
    AND R.VALD_NDS_YN       = '1'
LEFT JOIN M_DS_CRM_REC_GDNM_TM G ON A.GDCD = G.GDCD
WHERE A.CLS_YYMM  = TO_CHAR(ADD_MONTHS(SYSDATE,-1),'YYYYMM')
  AND A.IKD_GRPCD = 'LA';


-- ============================================================
-- [4] 설계이력  →  AI_DESIGN  (tbl_ds_design_history)
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_DESIGN PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_DESIGN NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    R.CTMNO,
    A.PLDT                                                     AS DESIGN_DT,
    A.GDCD,
    NVL(G.GDNM_CLEAN, A.GDCD)                                 AS GDNM,
    NULL                                                       AS DESIGN_PRM, -- TODO: 설계보험료 컬럼 확인
    CASE
        WHEN A.PL_STCD IN ('03','04','05','06','07','08','09') THEN '체결'
        ELSE '미체결'
    END                                                        AS RESULT_CD
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


-- ============================================================
-- [5] 신규 담보 (3개월 이내)  →  AI_NEW_CVR  (tbl_ds_new_coverage)
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_NEW_CVR PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_NEW_CVR NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    R.CTMNO,
    C.CVRCD                    AS CVR_CD,
    NVL(G.CVR_PRSNM, C.CVRCD) AS CVR_NM,
    C.INS_ST                   AS CVR_START_DT,
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
  AND C.INS_ST       >= ADD_MONTHS(SYSDATE,-3)
  AND C.VALD_NDS_YN  = '1'
  AND C.NDS_AP_ND_DTHMS > SYSDATE;


-- ============================================================
-- [6] ML 추천결과  →  AI_RECOMM  (tbl_ds_recommendation)
--     선행 조건: 레거시 배치(상품추천시스템)가 M_CRM_REC_RLT_BIZ 갱신 완료 후 실행
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_RECOMM PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_RECOMM NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    CTMNO,
    REC_RANK,
    REC_GDCD,
    REC_GDNM,
    REC_POCT
FROM M_CRM_REC_RLT_BIZ
WHERE REC_RANK <= 3;


-- ============================================================
-- [7] 가입불가 상품 목록  →  AI_INELIGIBLE  (tbl_ds_ineligible)
--     FILTER_1: 나이/성별/고지포기/취소요청 기반 가입불가
--     FILTER_2: 보장충족(CV_CNT2/CV_CNT >= 0.4) 기반 가입불가
--     선행 조건: 레거시 배치가 GDREC_CTM_FILTER_1/2 갱신 완료 후 실행
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_INELIGIBLE PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_INELIGIBLE NOLOGGING AS
SELECT /*+ PARALLEL(8) */ CTMNO, GDCD FROM GDREC_CTM_FILTER_1 WHERE CTMNO IS NOT NULL
UNION
SELECT /*+ PARALLEL(8) */ CTMNO, GDCD FROM GDREC_CTM_FILTER_2 WHERE CV_CNT2 / CV_CNT >= 0.4;


-- ============================================================
-- [8] 판매중 TM 상품 마스터  →  AI_PRODUCT  (tbl_ds_product_master)
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_PRODUCT PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_PRODUCT NOLOGGING AS
SELECT /*+ PARALLEL(8) */ DISTINCT
    A.GDCD,
    CASE
        WHEN B.GDNM LIKE '%Young%'                                              THEN 'L04'
        WHEN B.GDNM LIKE '%더건강 더실속%' OR B.MKTG_GD_CSFCD IN ('L02','L01') THEN 'L01'
        WHEN B.GDNM LIKE '%더건강%'                                             THEN 'L01'
        WHEN B.GDNM LIKE '%시그니처 여성 건강%'                                   THEN 'L01'
        WHEN B.MKTG_GD_CSFCD = 'L03' THEN 'L03'
        WHEN B.MKTG_GD_CSFCD = 'L04' THEN 'L04'
        WHEN B.MKTG_GD_CSFCD = 'L06' THEN 'L06'
        WHEN B.MKTG_GD_CSFCD = 'L08' THEN 'L08'
        WHEN B.MKTG_GD_CSFCD = 'L11' THEN 'L11'
        WHEN B.GDNM LIKE '%세이프투게더%'                                        THEN 'SAFE'
        WHEN B.GDNM LIKE '%실손의료보험%'                                        THEN 'SS'
        WHEN REGEXP_LIKE(B.GDNM,'참 편한|WELL100|간편|3N5|355')                 THEN '유병자'
        WHEN B.MKTG_GD_CSFCD IN ('L12','L13')                                 THEN 'L123'
        ELSE 'ETC'
    END                             AS GD_TYPE,
    B.GDNM,
    NVL(C.GDNM_CLEAN, B.GDNM)      AS GDNM_CLEAN
FROM IGD_GD_SL_TRM A
LEFT JOIN M_CRM_GD_CSF_INFO    B ON A.GDCD = B.GDCD
LEFT JOIN M_DS_CRM_REC_GDNM_TM C ON A.GDCD = C.GDCD
LEFT JOIN IGD_GD_SL_CHN_REL    D ON A.GDCD = D.GDCD
LEFT JOIN SL_CHNCD             E ON D.SL_CHNCD = E.SL_CHNCD
WHERE A.SL_NDDT >= SYSDATE
  AND A.GDCD    LIKE '%LA%'
  AND E.DTCNM   = 'TM'
  AND A.GDCD    IN (SELECT GDCD FROM TB_LNG_BJONG_MASTER WHERE SALE_END_YN = 'Y');


-- ============================================================
-- [9] 통화이력  →  AI_CALL_DETAIL  (tbl_ds_call_detail)
--     TB_CALL_LOG(콜 기본) + TB_CONTACT(통화시간/결과) + CUS_CTM(CTMNO 매핑)
--     최근 3년 데이터, 장기TM 채널(CALLGB IN '01','02','03') 한정
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_CALL_DETAIL PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_CALL_DETAIL NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    L.CALLID                                               AS CALL_ID,
    C2.CTMNO,
    TO_TIMESTAMP(TO_CHAR(TO_DATE(T.INDATE,'YYYYMMDD'),'YYYY-MM-DD')
                 || ' ' || SUBSTR(LPAD(T.INTIME,6,'0'),1,2)
                 || ':' || SUBSTR(LPAD(T.INTIME,6,'0'),3,2)
                 || ':' || SUBSTR(LPAD(T.INTIME,6,'0'),5,2),
                 'YYYY-MM-DD HH24:MI:SS')                 AS CALL_DT,
    T.INTIME                                              AS CALL_DURATION, -- 통화시간(초)
    CASE
        WHEN T.CONTACTMINORCD IN ('020206','030202')      THEN '결번'
        WHEN T.DIALRESULTCD   = '02'                      THEN '타인통화'
        WHEN T.DIALRESULTCD   IS NOT NULL                 THEN '연결성공'
        ELSE '미연결'
    END                                                   AS RESULT_CD,
    CG.CMS_CMPG_NM                                        AS CAMPAIGN_NM,
    CASE
        WHEN CG.CMPG_MDCCD LIKE '%POM%'   THEN 'POM'
        WHEN CG.CMPG_MDCCD LIKE '%CM%'
          OR CG.CMPG_MDCCD LIKE '%갱신%'  THEN 'CM'
        ELSE 'TM'
    END                                                   AS CHANNEL_TYPE
FROM TB_CALL_LOG L
LEFT JOIN TB_CONTACT T
    ON  L.CALLID   = T.CALLID
    AND T.CHANNELGB = '02'                -- 장기 채널
LEFT JOIN TB_CUSTOMER CUST ON L.CUSTID = CUST.CUSTID
LEFT JOIN CUS_CTM C2       ON CUST.CUST_DSCNO = C2.CTM_DSCNO
LEFT JOIN (
    -- 캠페인명: LIST_NO/SEQNO → M_DABRD_CMPG (월별 최신 1건)
    SELECT LISTID, LISTSEQID, CMS_CMPG_NM, CMPG_MDCCD,
           ROW_NUMBER() OVER (PARTITION BY LISTID, LISTSEQID
                              ORDER BY CLS_YYMM DESC) AS RN
    FROM M_DABRD_CMPG
) CG ON L.LISTID = CG.LISTID AND L.LISTSEQID = CG.LISTSEQID AND CG.RN = 1
WHERE L.CALLGB IN ('01','02','03')                 -- 콜구분: 인바운드/아웃바운드
  AND L.INDATE >= TO_CHAR(ADD_MONTHS(SYSDATE,-36),'YYYYMMDD');  -- 최근 3년


-- ============================================================
-- [10] 캠페인 배정이력  →  AI_CAMPAIGN  (tbl_ds_campaign_history)
--      M_DABRD_CMPG(배정) + TB_LIST(리스트) + CUS_CTM(CTMNO 매핑)
--      최근 3년, 삭제 제외(DELYN<>'Y'), 배정자 있는 건만
-- ============================================================
BEGIN EXECUTE IMMEDIATE 'DROP TABLE AI_CAMPAIGN PURGE'; EXCEPTION WHEN OTHERS THEN NULL; END;
/
CREATE TABLE AI_CAMPAIGN NOLOGGING AS
SELECT /*+ PARALLEL(8) */
    C2.CTMNO,
    A.CMS_CMPG_NM                                         AS CAMPAIGN_NM,
    TRUNC(TO_DATE(A.ASDT,'YYYYMMDD'))                     AS ASSIGN_DT,
    TRUNC(B.MSG_SEND_DT)                                  AS MSG_SEND_DT,  -- null=미발송
    CASE
        WHEN A.CMPG_MDCCD LIKE '%POM%'   THEN 'POM'
        WHEN A.CMPG_MDCCD LIKE '%CM%'
          OR A.CMPG_MDCCD LIKE '%갱신%'  THEN 'CM'
        ELSE 'TM'
    END                                                   AS CAMPAIGN_TYPE
FROM M_DABRD_CMPG A
LEFT JOIN TB_LIST B
    ON  A.LIST_NO    = B.LISTID
    AND A.LIST_SEQNO = B.LISTSEQID
LEFT JOIN TB_CUSTOMER CUST ON B.CUSTID = CUST.CUSTID
LEFT JOIN CUS_CTM C2       ON CUST.CUST_DSCNO = C2.CTM_DSCNO
WHERE NVL(B.DELYN,'N')    <> 'Y'
  AND A.CMPG_ALLCT_STFNO  IS NOT NULL
  AND C2.CTMNO             IS NOT NULL
  AND A.ASDT              >= TO_CHAR(ADD_MONTHS(SYSDATE,-36),'YYYYMMDD');  -- 최근 3년


-- ============================================================
-- TODO: 전사 문자발송이력  →  AI_MSG_HISTORY  (tbl_ds_msg_history)
--       소스 테이블 미확인 — 확인 후 작성
-- ============================================================


-- ============================================================
-- 실행 완료 확인용
-- ============================================================
SELECT 'AI_CUSTOMER'   AS TBL, COUNT(*) AS CNT FROM AI_CUSTOMER   UNION ALL
SELECT 'AI_COVERAGE',          COUNT(*)         FROM AI_COVERAGE   UNION ALL
SELECT 'AI_CONTRACT',          COUNT(*)         FROM AI_CONTRACT   UNION ALL
SELECT 'AI_DESIGN',            COUNT(*)         FROM AI_DESIGN     UNION ALL
SELECT 'AI_NEW_CVR',           COUNT(*)         FROM AI_NEW_CVR    UNION ALL
SELECT 'AI_RECOMM',            COUNT(*)         FROM AI_RECOMM     UNION ALL
SELECT 'AI_INELIGIBLE',        COUNT(*)         FROM AI_INELIGIBLE UNION ALL
SELECT 'AI_PRODUCT',           COUNT(*)         FROM AI_PRODUCT    UNION ALL
SELECT 'AI_CALL_DETAIL',       COUNT(*)         FROM AI_CALL_DETAIL UNION ALL
SELECT 'AI_CAMPAIGN',          COUNT(*)         FROM AI_CAMPAIGN;
