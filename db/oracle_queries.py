"""
Oracle → DuckDB ETL 쿼리 매핑

실행 순서:
  1. (Oracle) 상품추천쿼리_리팩토링.sql  → GDREC_DS_ORIGIN_MAIN_FIN_PRED 갱신
  2. (Oracle) db/oracle_queries.sql      → AI_* 추출 테이블 생성
  3. (Python) pipeline_c_duckdb.py       → AI_* 테이블 SELECT * → DuckDB 적재

복잡한 추출 로직은 oracle_queries.sql 에서 관리.
여기서는 DuckDB 테이블명 ↔ Oracle AI_* 테이블명 매핑만 관리.
"""

# 공통 기준: 전월 YYYYMM (Oracle 마트 D-1 데이터 기준)
_PREV_YYMM = "TO_CHAR(ADD_MONTHS(SYSDATE, -1), 'YYYYMM')"
_3M_AGO    = "ADD_MONTHS(SYSDATE, -3)"

# GD_TYPE 분류 CASE (상품명 기준, 4개 테이블에서 동일 사용)
_GD_TYPE_CASE = """\
    CASE
        WHEN GDNM LIKE '%Young%'                                            THEN 'L04'
        WHEN GDNM LIKE '%더건강 더실속%' OR MKTG_GD_CSFCD IN ('L02','L01') THEN 'L01'
        WHEN GDNM LIKE '%더건강%'                                           THEN 'L01'
        WHEN GDNM LIKE '%시그니처 여성 건강%'                               THEN 'L01'
        WHEN MKTG_GD_CSFCD = 'L03' THEN 'L03'
        WHEN MKTG_GD_CSFCD = 'L04' THEN 'L04'
        WHEN MKTG_GD_CSFCD = 'L06' THEN 'L06'
        WHEN MKTG_GD_CSFCD = 'L08' THEN 'L08'
        WHEN MKTG_GD_CSFCD = 'L11' THEN 'L11'
        WHEN GDNM LIKE '%세이프투게더%'                                     THEN 'SAFE'
        WHEN GDNM LIKE '%실손의료보험%'                                     THEN 'SS'
        WHEN REGEXP_LIKE(GDNM, '참 편한|WELL100|간편|3N5|355')             THEN '유병자'
        WHEN MKTG_GD_CSFCD IN ('L12','L13')                               THEN 'L123'
        ELSE 'ETC'
    END"""


# ──────────────────────────────────────────────────────────────────────────────
# [1] 고객 기본정보 → tbl_ds_customer
#     소스: CUS_CTM (전체 ~30만) LEFT JOIN GDREC_DS_ORIGIN_MAIN_FIN_PRED (유병자 4컬럼)
#     검증: REGION 컬럼명, INFLOW_CAMPAIGN_NM은 캠페인 쿼리 수령 후 채움
# ──────────────────────────────────────────────────────────────────────────────
QUERY_CUSTOMER = f"""
SELECT
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
    NULL                                  AS REGION,             -- TODO: 지역 컬럼 확인 (CTM_ADDR1 등)
    A.CTM_RGDT                            AS REG_DT,
    NULL                                  AS INFLOW_CAMPAIGN_NM, -- TODO: 캠페인 쿼리 수령 후 추가
    B.HOSP_CLAIM,
    B.HOSP_NOTI,
    B.MAJOR_DSAS_NOTI,
    B.MAJOR_DSAS_CLAIM
FROM CUS_CTM A
LEFT JOIN (
    -- 유병자 판단 4컬럼: 동일 MN_NRDPS_CTMNO가 복수 행이면 MIN(최근 발생 기준)
    SELECT
        MN_NRDPS_CTMNO,
        MIN(입원청구)    AS HOSP_CLAIM,
        MIN(입원고지)    AS HOSP_NOTI,
        MIN(중대질환고지) AS MAJOR_DSAS_NOTI,
        MIN(중대질환청구) AS MAJOR_DSAS_CLAIM
    FROM GDREC_DS_ORIGIN_MAIN_FIN_PRED
    WHERE CLS_YYMM = {_PREV_YYMM}
    GROUP BY MN_NRDPS_CTMNO
) B ON A.CTMNO = B.MN_NRDPS_CTMNO
"""


# ──────────────────────────────────────────────────────────────────────────────
# [2] 보장 대분류 담보금액 → tbl_ds_coverage
#     소스: GDREC_DS_ORIGIN_MAIN_FIN_PRED (직전월 기준, SUM 집계)
#     12개 컬럼 스키마와 1:1 대응
# ──────────────────────────────────────────────────────────────────────────────
QUERY_COVERAGE = f"""
SELECT
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
WHERE CLS_YYMM = {_PREV_YYMM}
GROUP BY MN_NRDPS_CTMNO
"""


# ──────────────────────────────────────────────────────────────────────────────
# [3] 계약이력 → tbl_ds_contract_history
#     소스: M_CRM_MTHY_PS_CR (직전월 스냅샷, 전채널 장기LA)
#     검증: LTRM_MPY_CV_PRM 컬럼명 (월납환산보험료)
# ──────────────────────────────────────────────────────────────────────────────
QUERY_CONTRACT_HISTORY = f"""
SELECT
    R.CTMNO,
    A.PLYNO,
    A.GDCD,
    NVL(G.GDNM_CLEAN, A.GDCD)  AS GDNM,
    A.INS_ST,
    A.INS_CLSTR,
    A.LTRM_MPY_CV_PRM           AS AP_PRM,  -- 검증: 월납환산보험료 컬럼명
    A.CR_STCD
FROM M_CRM_MTHY_PS_CR A
INNER JOIN INS_CR_RELPC R
    ON  A.PLYNO              = R.PLYNO
    AND R.IKD_GRPCD          = 'LA'
    AND R.RELPC_TPCD         = '01'         -- 계약자
    AND R.RELPC_STCD         IN ('01','04') -- 정상, 납입면제
    AND R.NDS_AP_STR_DTHMS  <= SYSDATE
    AND R.NDS_AP_ND_DTHMS    > SYSDATE
    AND R.VALD_NDS_YN        = '1'
LEFT JOIN M_DS_CRM_REC_GDNM_TM G ON A.GDCD = G.GDCD
WHERE A.CLS_YYMM  = {_PREV_YYMM}
  AND A.IKD_GRPCD = 'LA'
"""


# ──────────────────────────────────────────────────────────────────────────────
# [4] 설계이력 → tbl_ds_design_history
#     소스: INS_INS_PL + INS_PL_RELPC (계약자 기준)
#     검증: DESIGN_PRM 소스 컬럼 (설계보험료, NULL 스텁)
# ──────────────────────────────────────────────────────────────────────────────
QUERY_DESIGN_HISTORY = """
SELECT
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
    AND R.RELPC_TPCD    = '01'  -- 계약자
LEFT JOIN M_CRM_GD_CSF_INFO G ON A.GDCD = G.GDCD
WHERE A.PL_FLGCD   = '01'   -- 일반 설계
  AND A.IKD_GRPCD  = 'LA'
  AND A.VALD_PL_YN = '1'
"""


# ──────────────────────────────────────────────────────────────────────────────
# [5] 신규 담보 (3개월 이내) → tbl_ds_new_coverage
#     소스: INS_CR_CVR (담보 단위) JOIN INS_CR_RELPC (피보험자)
# ──────────────────────────────────────────────────────────────────────────────
QUERY_NEW_COVERAGE = f"""
SELECT
    R.CTMNO,
    C.CVRCD                     AS CVR_CD,
    NVL(G.CVR_PRSNM, C.CVRCD)  AS CVR_NM,
    C.INS_ST                    AS CVR_START_DT,
    C.ISAMT
FROM INS_CR_CVR C
INNER JOIN INS_CR_RELPC R
    ON  C.PLYNO             = R.PLYNO
    AND R.IKD_GRPCD         = 'LA'
    AND R.RELPC_TPCD        = '02'          -- 피보험자
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
  AND C.CVR_STCD     IN ('01','07','08')  -- 정상, 완납, 납입면제
  AND C.CVR_BJ_FLGCD IN ('01','03')      -- 인담보, 적립담보
  AND C.INS_ST       >= {_3M_AGO}
  AND C.VALD_NDS_YN  = '1'
  AND C.NDS_AP_ND_DTHMS > SYSDATE
"""


# ──────────────────────────────────────────────────────────────────────────────
# [6] ML 추천결과 (레거시) → tbl_ds_recommendation
#     소스: M_DS_CRM_REC_RLT_BIZ (REC_RS1 제외, 상위 3개)
#     검증: REC_POCT 컬럼 존재 여부
# ──────────────────────────────────────────────────────────────────────────────
QUERY_RECOMMENDATION = """
SELECT
    CTMNO,
    REC_RANK,
    REC_GDCD,
    REC_GDNM,
    REC_POCT  -- 검증: 컬럼 없으면 NULL AS REC_POCT 로 교체
FROM M_DS_CRM_REC_RLT_BIZ
WHERE REC_RANK <= 3
"""


# ──────────────────────────────────────────────────────────────────────────────
# [7] 판매중 TM 상품 마스터 → tbl_ds_product_master
#     소스: IGD_GD_SL_TRM (판매기간) + M_CRM_GD_CSF_INFO (상품명/GD_TYPE)
#     검증: TB_LNG_BJONG_MASTER 테이블명, SALE_END_YN 컬럼
# ──────────────────────────────────────────────────────────────────────────────
QUERY_PRODUCT_MASTER = f"""
SELECT DISTINCT
    A.GDCD,
    {_GD_TYPE_CASE.replace('GDNM', 'B.GDNM').replace('MKTG_GD_CSFCD', 'B.MKTG_GD_CSFCD')}
                            AS GD_TYPE,
    B.GDNM,
    NVL(C.GDNM_CLEAN, B.GDNM) AS GDNM_CLEAN
FROM IGD_GD_SL_TRM A
LEFT JOIN M_CRM_GD_CSF_INFO  B ON A.GDCD     = B.GDCD
LEFT JOIN M_DS_CRM_REC_GDNM_TM  C ON A.GDCD     = C.GDCD
LEFT JOIN IGD_GD_SL_CHN_REL  D ON A.GDCD     = D.GDCD
LEFT JOIN SL_CHNCD            E ON D.SL_CHNCD = E.SL_CHNCD
WHERE A.SL_NDDT  >= SYSDATE
  AND A.GDCD     LIKE '%LA%'
  AND E.DTCNM    = 'TM'
  AND A.GDCD     IN (
      SELECT GDCD FROM TB_LNG_BJONG_MASTER WHERE SALE_END_YN = 'Y'
  )
"""


# ──────────────────────────────────────────────────────────────────────────────
# TODO: 별도 수령 예정 쿼리 (소스 테이블 미확정)
# ──────────────────────────────────────────────────────────────────────────────

QUERY_CALL_DETAIL      = None  # TODO: 통화이력 소스 테이블 확인 후 작성
QUERY_CAMPAIGN_HISTORY = None  # TODO: 캠페인/배정이력 소스 테이블 확인 후 작성
QUERY_CAMPAIGN_SCORE   = None  # TODO: 외부 모델 점수 테이블 확인 후 작성
QUERY_MSG_HISTORY      = None  # TODO: 전사 문자발송이력 소스 테이블 확인 후 작성


# ──────────────────────────────────────────────────────────────────────────────
# DuckDB 테이블명 ↔ Oracle AI_* 테이블명 매핑
# oracle_queries.sql 실행 후 AI_* 테이블이 존재해야 함
# None인 항목은 pipeline_c_duckdb.py가 자동 skip
# ──────────────────────────────────────────────────────────────────────────────
QUERIES: dict[str, str | None] = {
    "tbl_ds_customer":         "SELECT * FROM AI_CUSTOMER",
    "tbl_ds_coverage":         "SELECT * FROM AI_COVERAGE",
    "tbl_ds_contract_history": "SELECT * FROM AI_CONTRACT",
    "tbl_ds_design_history":   "SELECT * FROM AI_DESIGN",
    "tbl_ds_new_coverage":     "SELECT * FROM AI_NEW_CVR",
    "tbl_ds_recommendation":   "SELECT * FROM AI_RECOMM",
    "tbl_ds_product_master":   "SELECT * FROM AI_PRODUCT",
    "tbl_ds_call_detail":      None,   # TODO: AI_CALL_DETAIL 생성 후 "SELECT * FROM AI_CALL_DETAIL"
    "tbl_ds_campaign_history": None,   # TODO: AI_CAMPAIGN 생성 후 "SELECT * FROM AI_CAMPAIGN"
    "tbl_ds_campaign_score":   None,   # TODO: AI_CAMP_SCORE 생성 후 "SELECT * FROM AI_CAMP_SCORE"
    "tbl_ds_msg_history":      None,   # TODO: AI_MSG_HISTORY 생성 후 "SELECT * FROM AI_MSG_HISTORY"
}
