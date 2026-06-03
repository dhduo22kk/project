


/*
================================================================================
  상품 추천 쿼리 - 리팩토링 및 최적화 최종본
  
  [실행 순서]
  01. GDRES_SYS_YYMM_PRED          기준 날짜
  02. GDREC_TMGD_LIST               판매중 상품 목록
  03. GDREC_TMGD_LIST_INFO          상품/담보 가입조건
  04. M_BIZ_CTM_INFO_CVR_LIST_RECT_T01  담보보장조건 코드
  05. GDREC_SYS_STF_PRED            TM 채널 직원
  06. GDREC_ORIGIN_INS_CR_PRED      장기TM 취급 계약 (핵심 소스)
  07. M_BIZ_CTM_INFO_CVR_LIST_RECT_T02  보유고객 (보험나이 계산)
  08. M_BIZ_CTM_INFO_CVR_LIST_RECT_T03  담보 가입금액
  09. M_BIZ_CTM_INFO_CVR_LIST_RECT_T04  담보보장조건 매핑
  10. M_BIZ_CTM_INFO_CVR_LIST_RECT_T06  가입금액 보정
  -- ※ T09(PIVOT), M_BIZ_RECT_GDINFO_* 는 T06 이후 (원본 파일 참조)
  11. GDREC_ORIGIN_INS_GD_PRED      상품별 기가입 (PIVOT)
  12. GDREC_ORIGIN_INS_PRMCNT_PRED  계약수/보험료 합계
  13. GDREC_ORIGIN_INS_NRD_PRED     피보험자수/미성년 여부
  14. GDREC_ORIGIN_INS_CA_PRED      자동차보험 계약수
  15. GDREC_ORIGIN_INS_INSDIFF_PRED 최초가입 경과월
  16. GDREC_ORIGIN_INS_CRTINFO_PRED 계약자 연령/성별
  17. GDREC_ORIGIN_INS_NRDINFO_PRED 피보험자 연령/성별
  18. GDREC_ORIGIN_INS_CRTJB_PRED   계약자 직업 분류
  19. GDREC_ORIGIN_INS_OVD_PRED     연체 보험료
  20. GDREC_ORIGIN_INS_CLM_PRED     지급 보험금 (장기+자동차)
  21. GDREC_ORIGIN_INS_PRVGD_PRED   해지/해약 이력
  22. GDREC_ORIGIN_INS_NOCVR_XC_PRED 부담보/할증 이력
  -- ※ ADDCR_PRED, CHNL_PRED 는 이 위치에서 생성 (원본 파일 참조)
  23. GDREC_ORIGIN_MAIN99_PRED      1차 취합
  24. GDREC_ORIGIN_PL_PRED          설계 정보
  25. GDREC_ORIGIN_PL_ALL_PRED      설계 이력 (PIVOT)
  26. GDREC_ORIGIN_PL_CL_PRED       설계 완료 이력 (PIVOT)
  27. GDREC_TMGD_PL_INFO_PRED       설계 정보 종합
  28. GDREC_ORIGIN_CLM_ALL_PRED     사고/지급 (무사고 판별)
  29. GDREC_ORIGIN_CLM_CSF_PRED     중대질환 청구
  30. GDREC_ORIGIN_CLM_MTT_PRED     중대질환 고지
  31. GDREC_ORIGIN_CLM_HSP_PRED     입원/수술 고지
  32. GDREC_ORIGIN_CLM_G_PRED       최근 입원 청구
  33. GDREC_TMGD_CLM_INFO_PRED      청구 정보 종합
  34. GDREC_ORIGIN_MAIN9_PRED       2차 취합
  35. GDREC_ORIGIN_MAIN_FIN_PRED    최종 결과

  [GD_TYPE 공통 분류 로직 - 4개 테이블에서 동일하게 사용]
  CASE WHEN GDNM LIKE '%Young%'                                       THEN 'L04'
       WHEN GDNM LIKE '%더건강 더실속%' OR MKTG_GD_CSFCD IN ('L02','L01') THEN 'L01'
       WHEN GDNM LIKE '%더건강%'                                       THEN 'L01'
       WHEN GDNM LIKE '%시그니처 여성 건강%'                             THEN 'L01'
       WHEN MKTG_GD_CSFCD = 'L03' THEN 'L03'  WHEN MKTG_GD_CSFCD = 'L04' THEN 'L04'
       WHEN MKTG_GD_CSFCD = 'L06' THEN 'L06'  WHEN MKTG_GD_CSFCD = 'L11' THEN 'L11'
       WHEN MKTG_GD_CSFCD = 'L08' THEN 'L08'
       WHEN GDNM LIKE '%세이프투게더%' THEN 'SAFE'
       WHEN GDNM LIKE '%실손의료보험%' THEN 'SS'
       WHEN REGEXP_LIKE(GDNM,'참 편한|WELL100|간편|3N5|355') THEN '유병자'
       WHEN MKTG_GD_CSFCD IN ('L12','L13') THEN 'L123'
       ELSE 'ETC' END AS GD_TYPE
  ※ 운영 환경에서 M_CRM_GD_CSF_INFO 기반 VIEW(GD_TYPE_V)로 중앙화 권장
  ※ 'SI' vs '유병자' 혼용 → 담당자 확인 후 통일 필요
================================================================================
*/



/* ============================================================================
   [01] 기준 날짜 세팅
============================================================================ */
DROP TABLE GDRES_SYS_YYMM_PRED PURGE;
CREATE TABLE GDRES_SYS_YYMM_PRED AS
SELECT
    YYMM                                                                    AS CLS_YYMM
    , F_ADD_MONTHS_A(F_LAST_DAY(YYMM), -2)                                 AS CLS_YYMM_2MB
    , F_ADD_MONTHS_A(F_LAST_DAY(YYMM), -1)                                 AS CLS_YYMM_1MB
    , FIRST_DAY(YYMM)                                                       AS CLS_STRDT
    , LEAST(SYSDATE, YYMM_NDDT)                                             AS CLS_NDDT
    , LEAST(SYSDATE,
        TO_DATE(TO_CHAR(YYMM_NDDT,'YYYY-MM-DD')||' 23:59:59','YYYY-MM-DD HH24:MI:SS'))
                                                                            AS CLS_NDDT_TS
    , LEAST(CAST(F_LAST_DAY(YYMM) AS DATE), SYSDATE)                       AS CLS_NDDT_LD
FROM M_COD_YYMM
WHERE YYMM = TO_CHAR(SYSDATE, 'YYYYMM');


/* ============================================================================
   [02] 장기 TM 판매 중인 상품 목록
============================================================================ */
DROP TABLE GDREC_TMGD_LIST PURGE;
CREATE TABLE GDREC_TMGD_LIST AS
SELECT DISTINCT
    A.*
    , CASE
        WHEN B.GDNM LIKE '%Young%'                                          THEN 'L04'
        WHEN B.GDNM LIKE '%더건강 더실속%' OR B.MKTG_GD_CSFCD IN ('L02','L01') THEN 'L01'
        WHEN B.GDNM LIKE '%더건강%'                                          THEN 'L01'
        WHEN B.GDNM LIKE '%시그니처 여성 건강%'                                THEN 'L01'
        WHEN B.MKTG_GD_CSFCD = 'L03' THEN 'L03'  WHEN B.MKTG_GD_CSFCD = 'L04' THEN 'L04'
        WHEN B.MKTG_GD_CSFCD = 'L06' THEN 'L06'  WHEN B.MKTG_GD_CSFCD = 'L11' THEN 'L11'
        WHEN B.MKTG_GD_CSFCD = 'L08' THEN 'L08'
        WHEN B.GDNM LIKE '%세이프투게더%' THEN 'SAFE'
        WHEN B.GDNM LIKE '%실손의료보험%' THEN 'SS'
        WHEN REGEXP_LIKE(B.GDNM,'참 편한|WELL100|간편|3N5|355') THEN 'SI'
        WHEN B.MKTG_GD_CSFCD IN ('L12','L13') THEN 'L123'
        ELSE 'ETC'
      END AS GD_TYPE
    , B.GDNM
    , D.DTCNM AS SL_CHNCD
FROM IGD_GD_SL_TRM A
LEFT JOIN M_CRM_GD_CSF_INFO  B ON A.GDCD     = B.GDCD
LEFT JOIN IGD_GD_SL_CHN_REL  C ON A.GDCD     = C.GDCD
LEFT JOIN SL_CHNCD           D ON C.SL_CHNCD = D.SL_CHNCD
WHERE A.SL_NDDT  >= SYSDATE
  AND A.GDCD     LIKE '%LA%'
  AND D.DTCNM    = 'TM'
  AND A.GDCD     IN (SELECT GDCD FROM TB_LNG_BJONG_MASTER WHERE SALE_END_YN = 'Y');


/* ============================================================================
   [03] 상품/담보별 가입 연령 및 필수담보 여부
============================================================================ */
DROP TABLE GDREC_TMGD_LIST_INFO PURGE;
CREATE TABLE GDREC_TMGD_LIST_INFO AS
SELECT DISTINCT
    A.*
    , B.CVRCD
    , B.CVR_PRSNM                                   -- 담보명
    , B.CVR_CLA_CN                                  -- 담보약관내용
    , B.CVR_BA_TRT_FLGCD                            -- 특약여부
    , B.ISAMT_NEED_YN                               -- 가입금액필요여부
    , B.MN_IS_AGE, B.MX_IS_AGE                     -- 최소/최대가입연령
    , B.IS_AV_SEXCD                                 -- 성별코드
    , C.ESSN_IS_YN                                  -- 필수가입여부
    , C.MN_IS_AV_AGE, C.MX_IS_AV_AGE
    , C.ISAMT_MNVL, C.ISAMT_MXVL                   -- 최소/최대가입금액
    , C.REC_CVR_YN                                  -- 추천담보여부
    , CASE WHEN F.GDCD IS NOT NULL THEN 1 ELSE 0 END AS 무사고_YN
FROM      GDREC_TMGD_LIST    A
LEFT JOIN IGD_GD_CVR          B ON A.GDCD = B.GDCD
LEFT JOIN INS_GD_CE_PL_CVR    C ON A.GDCD = C.GDCD AND B.CVRCD = C.CVRCD
-- ※ D(IGD_GD_CVR_ACM_RK): 원본에서 조인되나 출력 컬럼 없음 → 제거
LEFT JOIN IGD_GD_US_ATR       F ON F.GDCD = A.GDCD AND F.ATRCD = 'PA00119';


/* ============================================================================
   [04] 담보보장조건 코드 (T01)
   ※ 원본 WHERE 조건 정리:
      CASE WHEN (IN(13,25) AND <59) THEN '0' ELSE '1' END = '1'
      → NOT (THCP_INSTR_MNVL IN (13,25) AND THCP_INSTR_MXVL < 59) 와 동일
      ※ 원본 내 OR 조건(THCP_INSTR_MNVL IN(13,25) OR THCP_INSTR_MXVL IN(12,24))은
         상위 AND 조건에 논리적으로 흡수 → 제거. 원의도 재확인 권장.
============================================================================ */
DROP TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T01 PURGE;
CREATE TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T01 AS
SELECT
    THCP_GN_CND_SEQNO, THCP_GD_XCPT_MTT, THCP_CVRCD
    , THCP_IBAMT_STNM, THCP_INS_MULT_STAMT, THCP_INSTR_CSFNM
    , THCP_INSTR_MNVL, THCP_INSTR_MXVL
    , THCP_INS_AGE_MNVL, THCP_INS_AGE_MXVL
    , THCP_AN_PY_CT, THCP_AN_ND_DTNM, THCP_AN_TRM_NM
    , THCP_GNAMT_ITCD, THCP_GNAMT
FROM SFA_THCP_CVR_GN_CND
WHERE THCP_INSTR_CSFNM = '만기'
  AND NOT (THCP_INSTR_MNVL IN (13,25) AND THCP_INSTR_MXVL < 59);


/* ============================================================================
   [05→06 통합] 장기 TM 취급 계약 (핵심 소스 테이블)
   ※ [최적화] GDREC_SYS_STF_PRED 중간 테이블 제거
              → 장기TM(CHNL='31') 조건을 EXISTS 인라인으로 직접 처리
   ※ 소스: M_ORG_MTHY_BZ_ORGN (월별 스냅샷, CLS_YYMM 매칭)
   ※ CHNL='31' 조건: HDQT_ORGCD IN ('1300012','1301363','1303053')
                      OR BR_ORGCD IN ('1300280','1301363','1303054','1303055')
      우선순위 높은 타 채널 제외: LIFE WITH(BZ_ATRCD 30/31), 교차(TMNM '%교차%'),
                                  GA(BZ_FML_QUFCD 'G01'), 방카(HDQT_ORGCD 1300013 등)
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_CR_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_CR_PRED AS
SELECT A.*
FROM GDRES_SYS_YYMM_PRED T
INNER JOIN M_CRM_MTHY_PS_CR A ON A.CLS_YYMM = T.CLS_YYMM
WHERE A.IKD_GRPCD = 'LA'
  AND A.DH_STFNO IN (
      SELECT STFNO FROM M_ORG_BZ_ORGN
      WHERE HDQT_ORGCD = '1300012'
        AND BRNM LIKE '%장기%'
        AND STF_FLGCD = '02'
  );


/* ============================================================================
   [07] 보유고객 월별 기준 + 보험나이 계산 (T02)
   ※ [성능] INS_AGE 계산 시 동일 AGE() 표현식 2회 반복 → CROSS APPLY로 1회로 축약
   ※ [제거] WHERE A1.IKD_GRPCD='LA' : GDREC_ORIGIN_INS_CR_PRED가 이미 LA 전용
============================================================================ */
DROP TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T02 PURGE;
CREATE TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T02 AS
SELECT
    A2.CLS_YYMM, A2.PLYNO, A2.CTMNO, A2.RELPC_SEQNO
    , A2.STFNO, A2.USRNO, A2.GDCD, A2.INS_ST, A2.INS_CLSTR, A2.BRTH
    , CASE
        WHEN F_ISDATE(A2.BRTH) = 'T'
        THEN TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A2.CLS_YYMM),
                   TO_DATE(A2.BRTH, 'YYYYMMDD')) / 12)
      END AS INS_AGE
FROM (
    SELECT
        A1.CLS_YYMM
        , A1.PLYNO, B1.CTMNO, B1.RELPC_SEQNO
        , A1.DH_STFNO                       AS STFNO
        , COALESCE(A1.DH_USR_NO, '9999999') AS USRNO
        , A1.GDCD, A1.INS_ST, A1.INS_CLSTR
        , F_BIRTH_DAY_DEC(B1.CTM_DSCNO)    AS BRTH
        , ROW_NUMBER() OVER (
            PARTITION BY A1.PLYNO, B1.CTMNO, A1.CLS_YYMM
            ORDER BY B1.RELPC_SEQNO
          ) AS RN
    FROM (
        SELECT A.*, B.GDNM_CLEAN
        FROM   GDREC_ORIGIN_INS_CR_PRED A
        LEFT JOIN M_DS_CRM_REC_GDNM_TM B ON A.GDCD = B.GDCD
    ) A1
    INNER JOIN INS_CR_RELPC B1
        ON  A1.PLYNO            = B1.PLYNO
        AND B1.IKD_GRPCD        IN ('LA')
        AND B1.RELPC_STCD       IN ('01','04')
        AND B1.RELPC_TPCD        = '02'
        AND B1.VALD_NDS_YN       = '1'
        AND B1.NDS_AP_STR_DTHMS <= F_LAST_DAY(A1.CLS_YYMM)
        AND B1.NDS_AP_ND_DTHMS   > F_LAST_DAY(A1.CLS_YYMM)
        AND B1.CTMNO            IS NOT NULL
) A2
WHERE A2.RN = 1;


/* ============================================================================
   [08] 담보 가입금액 추출 (T03)
   ※ [성능] EXISTS → INNER JOIN으로 변경 (대용량 INS_CR_CVR 스캔 시 더 효율적)
============================================================================ */
DROP TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T03 PURGE;
CREATE TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T03 AS
-- ※ [최적화] GDRES_SYS_YYMM_PRED 조인 제거: 날짜 조건을 INS_CR_CVR WHERE에 선행 적용
--            → INS_CR_CVR 풀스캔 전에 현재 유효 담보만 필터, 대상 건수 대폭 감소
SELECT
    A1.CLS_YYMM, A1.PLYNO, B1.CVRCD, B1.CVR_SEQNO
    , A1.CTMNO, A1.RELPC_SEQNO, A1.STFNO, A1.USRNO
    , A1.INS_ST, A1.INS_CLSTR, A1.GDCD, A1.BRTH, A1.INS_AGE
    , B1.CVR_STCD
    , B1.INS_ST                                             AS CVR_INS_ST
    , B1.INS_CLSTR                                          AS CVR_INS_CLSTR
    , F_DIFF_DATE('MM', TO_CHAR(B1.INS_CLSTR,'YYYYMMDD'),
                        TO_CHAR(F_LAST_DAY(A1.CLS_YYMM),'YYYYMMDD')) AS CVR_CLSTR_ST_RNDMC
    , F_DIFF_DATE('MM', TO_CHAR(B1.INS_ST,'YYYYMMDD'),
                        TO_CHAR(F_LAST_DAY(A1.CLS_YYMM),'YYYYMMDD')) AS CVR_ST_ST_RNDMC
    , B1.AP_PRM, B1.ISAMT
    , B1.AUTO_RNW_AV_YN, B1.AUTO_RNW_CVR_CNLDT, B1.RNW_NDDT
    , C1.MDCS_RGT_BJ_YN, C1.RLPMI_CVR_YN
FROM M_BIZ_CTM_INFO_CVR_LIST_RECT_T02 A1
INNER JOIN (
    SELECT B1.*
        , ROW_NUMBER() OVER (
            PARTITION BY B1.PLYNO, B1.RELPC_OJ_SEQNO, B1.CVRCD, B1.CVR_SEQNO
            ORDER BY B1.NDSNO DESC
          ) AS RN
    FROM (
        SELECT
            CVR_STCD, INS_ST, INS_CLSTR, AP_PRM, ISAMT
            , AUTO_RNW_AV_YN, AUTO_RNW_CVR_CNLDT, RNW_NDDT
            , RELPC_OJ_SEQNO, PLYNO, CVRCD, CVR_SEQNO
            , NDS_AP_STR_DTHMS, NDS_AP_ND_DTHMS, NDSNO
        FROM INS_CR_CVR
        INNER JOIN (SELECT DISTINCT THCP_CVRCD FROM M_BIZ_CTM_INFO_CVR_LIST_RECT_T01) T01
            ON CVRCD = T01.THCP_CVRCD
        WHERE IKD_GRPCD             = 'LA'
          AND VALD_NDS_YN           = '1'
          AND CVR_STCD              IN ('01','07','08')
          AND CVR_BJ_FLGCD          IN ('01','03')
          AND NDS_AP_STR_DTHMS      <= F_LAST_DAY(TO_CHAR(SYSDATE,'YYYYMM'))  -- 날짜 조건 선행
          AND NDS_AP_ND_DTHMS        > F_LAST_DAY(TO_CHAR(SYSDATE,'YYYYMM'))
    ) B1
) B1
    ON  A1.PLYNO        = B1.PLYNO
    AND A1.RELPC_SEQNO  = B1.RELPC_OJ_SEQNO
    AND B1.INS_CLSTR   >= F_LAST_DAY(A1.CLS_YYMM)
    AND B1.RN           = 1
LEFT JOIN IGD_GD_CVR C1
    ON  B1.CVRCD        = C1.CVRCD
    AND A1.GDCD         = C1.GDCD
    AND C1.AP_NDDT       > F_LAST_DAY(A1.CLS_YYMM)
    AND C1.AP_STRDT     <= F_LAST_DAY(A1.CLS_YYMM);


/* ============================================================================
   [09] 담보보장조건 ↔ 담보코드 매핑 (T04)
============================================================================ */
DROP TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T04 PURGE;
CREATE TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T04 AS
SELECT *
FROM (
    SELECT 
        A1.CLS_YYMM, A1.PLYNO, A1.CVRCD, A1.CVR_SEQNO
        , A1.CTMNO, A1.RELPC_SEQNO, A1.STFNO, A1.USRNO
        , A1.INS_ST, A1.INS_CLSTR, A1.GDCD, A1.CVR_STCD
        , A1.INS_ST    AS CVR_INS_ST     -- ※ 원본 중복 컬럼 유지 (하위 호환)
        , A1.INS_CLSTR AS CVR_INS_CLSTR
        , A1.AP_PRM, A1.ISAMT
        , A1.AUTO_RNW_AV_YN, A1.AUTO_RNW_CVR_CNLDT, A1.RNW_NDDT
        , A1.MDCS_RGT_BJ_YN, A1.RLPMI_CVR_YN
        , A1.BRTH, A1.INS_AGE, A1.CVR_ST_ST_RNDMC, A1.CVR_CLSTR_ST_RNDMC
        , B1.THCP_GN_CND_SEQNO, B1.THCP_GD_XCPT_MTT, B1.THCP_CVRCD
        , B1.THCP_IBAMT_STNM, B1.THCP_INS_MULT_STAMT, B1.THCP_INSTR_CSFNM
        , B1.THCP_INSTR_MNVL, B1.THCP_INSTR_MXVL
        , B1.THCP_INS_AGE_MNVL, B1.THCP_INS_AGE_MXVL
        , B1.THCP_AN_PY_CT, B1.THCP_AN_ND_DTNM, B1.THCP_AN_TRM_NM
        , B1.THCP_GNAMT_ITCD, B1.THCP_GNAMT
        -- 일배책/화재벌금/운전자벌금: 동일 고객+항목 내 최신가입 1건만
        , CASE
            WHEN B1.THCP_GNAMT_ITCD IN ('SH0001','SH0003','WJ0001')
                THEN ROW_NUMBER() OVER (
                         PARTITION BY A1.CLS_YYMM, A1.CTMNO, B1.THCP_GNAMT_ITCD
                         ORDER BY A1.INS_ST DESC)
            ELSE 1
          END AS RN
    FROM M_BIZ_CTM_INFO_CVR_LIST_RECT_T03 A1
    INNER JOIN M_BIZ_CTM_INFO_CVR_LIST_RECT_T01 B1
        ON  A1.CVRCD = B1.THCP_CVRCD
        AND (B1.THCP_GD_XCPT_MTT IS NULL OR B1.THCP_GD_XCPT_MTT LIKE '%'||A1.GDCD||'%')
)
WHERE RN = 1;


/* ============================================================================
   [10] 가입금액 보정 (T06) - 지급금액 산출
============================================================================ */
DROP TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T06 PURGE;
CREATE TABLE M_BIZ_CTM_INFO_CVR_LIST_RECT_T06 AS
SELECT
    A2.*
    , CASE
        WHEN A2.THCP_IBAMT_STNM = '가입금액'
             AND A2.THCP_GNAMT_ITCD IN ('JH0004','JH0005','JH0006','JH0007','JH0008','JH0009')
            THEN A2.ISAMT                                                           -- 후유장해 6종
        WHEN A2.THCP_IBAMT_STNM = '가입금액'
            THEN (A2.ISAMT / A2.THCP_INS_MULT_STAMT) * A2.THCP_GNAMT
        WHEN A2.THCP_IBAMT_STNM = '정액'
            THEN A2.THCP_GNAMT * 10000
        WHEN A2.THCP_IBAMT_STNM IN ('보험료','일시납')
            THEN ((A2.AP_PRM / 10000) / A2.THCP_INS_MULT_STAMT) * A2.THCP_GNAMT * 10000
      END AS CALC_PYAMT
FROM M_BIZ_CTM_INFO_CVR_LIST_RECT_T04 A2;

/*
   ※ [T09] M_BIZ_CTM_INFO_CVR_LIST_RECT_T09: T06을 PIVOT → 고객-담보 Wide 테이블
      원본 파일 참조. T06 이후 즉시 실행.

   ※ [M_BIZ_RECT_GDINFO_*] 연령별 상위75% 가입금액 (L01/L03/SS/L08/L11):
      T09 이후 실행. 원본 파일 참조.
*/


/* ============================================================================
   [11] 상품별 기가입 현황 PIVOT
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_GD_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_GD_PRED AS
SELECT *
FROM (
    SELECT
        CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO, GD_TYPE
        , COUNT(DISTINCT PLYNO) AS PLY_CNT
    FROM (
        SELECT A.*
            , CASE
                WHEN GDNM LIKE '%Young%'                                        THEN 'L04'
                WHEN GDNM LIKE '%더건강 더실속%' OR MKTG_GD_CSFCD IN ('L02','L01') THEN 'L01'
                WHEN GDNM LIKE '%더건강%'                                        THEN 'L01'
                WHEN GDNM LIKE '%시그니처 여성 건강%'                              THEN 'L01'
                WHEN MKTG_GD_CSFCD = 'L03' THEN 'L03'  WHEN MKTG_GD_CSFCD = 'L04' THEN 'L04'
                WHEN MKTG_GD_CSFCD = 'L06' THEN 'L06'  WHEN MKTG_GD_CSFCD = 'L11' THEN 'L11'
                WHEN MKTG_GD_CSFCD = 'L08' THEN 'L08'
                WHEN GDNM LIKE '%세이프투게더%' THEN 'SAFE'
                WHEN GDNM LIKE '%실손의료보험%' THEN 'SS'
                WHEN REGEXP_LIKE(GDNM,'참 편한|WELL100|간편|3N5|355') THEN '유병자'
                WHEN MKTG_GD_CSFCD IN ('L12','L13') THEN 'L123'
                ELSE 'ETC'
              END AS GD_TYPE
        FROM GDREC_ORIGIN_INS_CR_PRED A
    )
    GROUP BY CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO, GD_TYPE
)
PIVOT (MAX(PLY_CNT) FOR GD_TYPE IN (
    'L01' AS L01,'L03' AS L03,'L04' AS L04,'L06' AS L06,'L08' AS L08,
    'SAFE' AS SAFE,'SS' AS SS,'유병자' AS 유병자,'L11' AS L11,'L123' AS L123
)) P;

/*
   ※ GDREC_ORIGIN_INS_ADDCR_GD_PRED: 구조 동일, 소스만 ADDCR_PRED로 변경. 원본 파일 참조.
*/


/* ============================================================================
   [12] 고객별 계약수/보험료 합계
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_PRMCNT_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_PRMCNT_PRED AS
SELECT
    CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO
    , SUM(LTRM_MPY_CV_PRM)  AS PRM
    , COUNT(DISTINCT PLYNO) AS PLY_CNT
FROM GDREC_ORIGIN_INS_CR_PRED
GROUP BY CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO;


/* ============================================================================
   [13] 피보험자수 및 미성년 피보험자 존재 여부
   ※ [논리] AP_STRDT/AP_NDDT 기준을 SYSDATE → F_LAST_DAY(CLS_YYMM)으로 변경
      다른 테이블들이 모두 CLS_YYMM 기준이므로 통일 (원본은 SYSDATE → 기준일 불일치)
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_NRD_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_NRD_PRED AS
SELECT
    A.CLS_YYMM, A.CRT_CTMNO
    , COUNT(DISTINCT B.CTMNO) AS NRD_CNT
    , MAX(CASE
        WHEN F_ISDATE(F_BIRTH_DAY_DEC(B.CTM_DSCNO)) = 'T'
         AND TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A.CLS_YYMM),
                  TO_DATE(F_BIRTH_DAY_DEC(B.CTM_DSCNO),'YYYYMMDD')) / 12) < 20
        THEN 1 ELSE 0
      END) AS KIDS_YN
FROM (SELECT DISTINCT CRT_CTMNO, PLYNO, CLS_YYMM FROM GDREC_ORIGIN_INS_CR_PRED) A
INNER JOIN INS_CR_RELPC B
    ON  A.PLYNO        = B.PLYNO
    AND B.AP_STRDT    <= F_LAST_DAY(A.CLS_YYMM)   -- ※ 수정: SYSDATE → CLS_YYMM 기준 통일
    AND B.AP_NDDT      > F_LAST_DAY(A.CLS_YYMM)
    AND B.RELPC_TPCD  IN ('02')
GROUP BY A.CLS_YYMM, A.CRT_CTMNO;


/* ============================================================================
   [14] 계약자별 자동차보험 계약수
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_CA_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_CA_PRED AS
SELECT
    A.CLS_YYMM, A.CRT_CTMNO
    , COUNT(DISTINCT B.PLYNO) AS CA_CNT
FROM (SELECT DISTINCT CRT_CTMNO, CLS_YYMM FROM GDREC_ORIGIN_INS_CR_PRED) A
LEFT JOIN M_CRM_MTHY_PS_CR B
    ON  A.CRT_CTMNO  = B.MN_NRDPS_CTMNO
    AND A.CLS_YYMM   = B.CLS_YYMM
    AND B.IKD_GRPCD  = 'CA'
GROUP BY A.CLS_YYMM, A.CRT_CTMNO;


/* ============================================================================
   [15] 최초 보험 가입 후 경과 개월수
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_INSDIFF_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_INSDIFF_PRED AS
SELECT CLS_YYMM, CRT_CTMNO
    , TRUNC(MONTHS_BETWEEN(F_LAST_DAY(CLS_YYMM), INS_ST), 0) AS INS_DIFF
FROM (
    SELECT A.*
        , ROW_NUMBER() OVER (PARTITION BY CRT_CTMNO, CLS_YYMM ORDER BY INS_ST) AS RN
    FROM GDREC_ORIGIN_INS_CR_PRED A
)
WHERE RN = 1;


/* ============================================================================
   [16] 계약자 연령/성별
   [17] 피보험자 연령/성별
   ※ 두 테이블은 JOIN 키(CRT_CTMNO vs MN_NRDPS_CTMNO)만 다르고 구조 동일
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_CRTINFO_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_CRTINFO_PRED AS
SELECT A.*
    , CASE WHEN F_ISDATE(F_BIRTH_DAY_DEC(B.CTM_DSCNO)) = 'T'
           THEN TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A.CLS_YYMM),
                    TO_DATE(F_BIRTH_DAY_DEC(B.CTM_DSCNO),'YYYYMMDD')) / 12)
      END AS CTM_AGE
    , CASE WHEN F_SEX_DEC(B.CTM_DSCNO) = 'M' THEN '1.M'
           WHEN F_SEX_DEC(B.CTM_DSCNO) = 'F' THEN '2.F' END AS CTM_SEX
FROM (SELECT DISTINCT CRT_CTMNO, CLS_YYMM FROM GDREC_ORIGIN_INS_CR_PRED) A
LEFT JOIN CUS_CTM B ON B.CTMNO = A.CRT_CTMNO;

DROP TABLE GDREC_ORIGIN_INS_NRDINFO_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_NRDINFO_PRED AS
SELECT A.*
    , CASE WHEN F_ISDATE(F_BIRTH_DAY_DEC(B.CTM_DSCNO)) = 'T'
           THEN TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A.CLS_YYMM),
                    TO_DATE(F_BIRTH_DAY_DEC(B.CTM_DSCNO),'YYYYMMDD')) / 12)
      END AS CTM_AGE
    , CASE WHEN F_SEX_DEC(B.CTM_DSCNO) = 'M' THEN '1.M'
           WHEN F_SEX_DEC(B.CTM_DSCNO) = 'F' THEN '2.F' END AS CTM_SEX
FROM (SELECT DISTINCT MN_NRDPS_CTMNO, CLS_YYMM FROM GDREC_ORIGIN_INS_CR_PRED) A
LEFT JOIN CUS_CTM B ON B.CTMNO = A.MN_NRDPS_CTMNO;


/* ============================================================================
   [18] 계약자 직업 분류
   ※ 전문직 LIKE 패턴 → REGEXP_LIKE 단일 표현식으로 압축 (가독성+성능)
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_CRTJB_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_CRTJB_PRED AS
-- ※ [최적화] A.* → 필요 컬럼만 (CLS_YYMM, CTMNO, JB_SEG). MAIN99에서 JB_SEG만 사용
SELECT
    A.CLS_YYMM
    , A.CTMNO
    , CASE
        WHEN SPJOB_YN = 1             THEN '전문직'
        WHEN STF_YN   = '내근직'      THEN '내근직'
        WHEN STF_YN   = '영업가족'    THEN '영업가족'
        WHEN JB_TYPE IN ('1','2','3') THEN '화이트'
        WHEN JB_TYPE IN ('4','5')     THEN '자영업'
        WHEN JB_TYPE IN ('B1','C','B2') THEN '주부/학생'
        ELSE '블루'
      END AS JB_SEG
FROM (
    SELECT
        A.*
        , E2.JBNM, E3.BZPS_TPCD
        -- [가독성] 전문직 포함/제외 패턴을 REGEXP_LIKE로 단일화
        , CASE
            WHEN REGEXP_LIKE(E2.JBNM,
                 '전문 간호|조종사|관제사|항해사|선박 기관사|선장|교수|고위|임원|경무관 이상|'||
                 '소방감 이상|계리|금융 상품|자산|외환 딜러|소프트웨어|프로그래머|데이터|'||
                 '감독|장학관|판사|검사|변호사|법무사|변리사|노무사|회계사|세무사|'||
                 '감정평가사|관세사|의사|치과의사|수의사|한의사|약사|손해사정사|'||
                 '건축사|행정사|도선사')
             AND NOT REGEXP_LIKE(E2.JBNM,
                 '장의사|스포츠|건설|코치|검사원|검사공|검사기사|사육|판매|사무원|'||
                 '종사원|의료인|공무원|보조원|현장기술|감독자|제조|공급|사무및감독|경비원')
                THEN 1 ELSE 0
          END AS SPJOB_YN
        , CASE
            WHEN E4.BZ_PART_FLGCD = '09' AND E4.STF_BZ_STCD = '01' THEN '내근직'
            WHEN E4.STFNO IS NOT NULL     AND E4.STF_BZ_STCD = '01' THEN '영업가족'
          END AS STF_YN
        , CASE
            WHEN E2.JBNM LIKE '%주부%'                            THEN 'B2'
            WHEN E1.JBCD='0' AND E1.JB_CH_SEQNO='2'              THEN '1'
            WHEN E1.JBCD='1' AND E1.JB_CH_SEQNO='2'              THEN '2'
            WHEN E1.JBCD='1' AND E1.JB_CH_SEQNO IN ('3','4')     THEN '1'
            WHEN E1.JBCD='2' AND E1.JB_CH_SEQNO IN ('2','3','4') THEN '2'
            WHEN E1.JBCD='3' AND E1.JB_CH_SEQNO='2'              THEN '2'
            WHEN E1.JBCD='3' AND E1.JB_CH_SEQNO IN ('3','4')     THEN '3'
            WHEN E1.JBCD='4' AND E1.JB_CH_SEQNO IN ('3','4')     THEN '4'
            WHEN E1.JBCD='5' AND E1.JB_CH_SEQNO='2'              THEN '4'
            WHEN E1.JBCD IN ('6','8','9') AND E1.JB_CH_SEQNO='1' THEN '4'
            WHEN E1.JBCD='4' AND E1.JB_CH_SEQNO='2'              THEN '5'
            WHEN E1.JBCD='5' AND E1.JB_CH_SEQNO IN ('3','4')     THEN '5'
            WHEN E1.JBCD='1' AND E1.JB_CH_SEQNO='1'              THEN '6'
            WHEN E1.JBCD='6' AND E1.JB_CH_SEQNO IN ('3','4')     THEN '6'
            WHEN E1.JBCD='9' AND E1.JB_CH_SEQNO='2'              THEN '6'
            WHEN E1.JBCD='4' AND E1.JB_CH_SEQNO='1'              THEN '7'
            WHEN E1.JBCD='5' AND E1.JB_CH_SEQNO='1'              THEN '7'
            WHEN E1.JBCD IN ('6','7','8') AND E1.JB_CH_SEQNO='2' THEN '7'
            WHEN E1.JBCD='7' AND E1.JB_CH_SEQNO IN ('3','4')     THEN '7'
            WHEN E1.JBCD IN ('3','7') AND E1.JB_CH_SEQNO='1'     THEN '8'
            WHEN E1.JBCD='8' AND E1.JB_CH_SEQNO IN ('3','4')     THEN '8'
            WHEN E1.JBCD='2' AND E1.JB_CH_SEQNO='1'              THEN '9'
            WHEN E1.JBCD='9' AND E1.JB_CH_SEQNO IN ('3','4')     THEN '9'
            WHEN E1.JBCD='A' AND E1.JB_CH_SEQNO IN ('2','3','4') THEN 'A'
            WHEN E1.JBCD='B' AND E1.JB_CH_SEQNO IN ('2','3','4') THEN 'B1'
            WHEN E2.JBCD='B3200'                                   THEN 'B2'
            ELSE 'C'
          END AS JB_TYPE
    FROM (
        SELECT AA.CLS_YYMM, AA.CTMNO, BB.JBCD, BB.JB_CH_SEQNO
            , ROW_NUMBER() OVER (PARTITION BY AA.CLS_YYMM, AA.CTMNO ORDER BY BB.AP_STR_DTHMS DESC) AS RN
        FROM (SELECT DISTINCT CRT_CTMNO AS CTMNO, CLS_YYMM FROM GDREC_ORIGIN_INS_CR_PRED) AA
        LEFT JOIN CUS_CTM_JB_CRR BB
            ON  AA.CTMNO        = BB.CTMNO
            AND BB.AP_STR_DTHMS <= F_LAST_DAY(AA.CLS_YYMM)
            AND BB.AP_ND_DTHMS   > F_LAST_DAY(AA.CLS_YYMM)
    ) A
    LEFT JOIN CUS_JB        E1 ON SUBSTR(A.JBCD,1,1) = E1.JBCD AND A.JB_CH_SEQNO = E1.JB_CH_SEQNO
    LEFT JOIN CUS_JB        E2 ON A.JBCD = E2.JBCD AND A.JB_CH_SEQNO = E2.JB_CH_SEQNO
    LEFT JOIN CUS_CTM       E3 ON A.CTMNO = E3.CTMNO
    LEFT JOIN M_ORG_BZ_ORGN E4 ON E3.CTM_DSCNO = E4.RSNO
    WHERE A.RN = 1
) A;


/* ============================================================================
   [19] 연체 보험료
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_OVD_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_OVD_PRED AS
SELECT DISTINCT A.*, C1.CTMNO
FROM GDRES_SYS_YYMM_PRED T
INNER JOIN INS_DCN_PRM A
    ON  A.CLS_YYMM BETWEEN F_PREV_MONTH(T.CLS_YYMM,'12') AND T.CLS_YYMM
INNER JOIN INS_CR_RELPC C1
    ON  A.PLYNO                 = C1.PLYNO
    AND C1.NDS_AP_STR_DTHMS    <= F_LAST_DAY(T.CLS_YYMM)
    AND C1.NDS_AP_ND_DTHMS      > F_LAST_DAY(T.CLS_YYMM)
    AND C1.RELPC_TPCD          IN ('01')          -- 계약자
    AND C1.RELPC_STCD          IN ('01','04')      -- 정상, 납입면제
    AND C1.RELPC_DSCNO_FLGCD   IN ('01','05')      -- 개인고객
    AND C1.IKD_GRPCD            = 'LA'
WHERE A.CLS_BFAF_FLGCD = '03'                     -- 확정 마감
  AND A.DU_AR_FLGCD   IN ('01','02')              -- 응당
  AND EXISTS (
      SELECT 1 FROM GDREC_ORIGIN_INS_CR_PRED B
      WHERE C1.CTMNO = B.CRT_CTMNO AND T.CLS_YYMM = B.CLS_YYMM
  );


/* ============================================================================
   [20] 지급 보험금 (장기 + 자동차)
   ※ [성능] LEFT JOIN + WHERE B.컬럼 → 사실상 INNER JOIN. 명시적으로 변경.
   ※ [성능] 원본 UNION → UNION ALL: 두 소스는 완전히 다른 계통
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_CLM_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_CLM_PRED AS
-- 장기 보험
SELECT
    T.CLS_YYMM, T.CLS_NDDT, A.MN_NRDPS_CTMNO
    , CASE WHEN B.IKD_GRPCD IN ('FA','MA') THEN 'FAMA' ELSE B.IKD_GRPCD END AS IKD_GRPCD
    , B.CLMDT
    , SUM(B.WONCR_CV_PYAMT) AS PY_AMT
FROM GDRES_SYS_YYMM_PRED T
INNER JOIN GDREC_ORIGIN_INS_CR_PRED    A ON T.CLS_YYMM = A.CLS_YYMM
INNER JOIN M_CMP_GN_CVRCL_PY_IBNF_LIST B            -- [수정] LEFT→INNER (WHERE로 필터 중)
    ON  A.MN_NRDPS_CTMNO = B.CLMPS_CTMNO
    AND B.CLMDT BETWEEN F_LAST_DAY(F_PREV_MONTH(T.CLS_YYMM,'60')) AND T.CLS_NDDT
GROUP BY T.CLS_YYMM, T.CLS_NDDT, A.MN_NRDPS_CTMNO
       , CASE WHEN B.IKD_GRPCD IN ('FA','MA') THEN 'FAMA' ELSE B.IKD_GRPCD END, B.CLMDT

UNION ALL  -- [수정] UNION → UNION ALL: 소스가 다른 테이블이므로 중복 없음

-- 자동차 보험
SELECT CLS_YYMM, CLS_NDDT, MN_NRDPS_CTMNO, IKD_GRPCD, CLMDT
    , SUM(RPBL_PY_IBAMT) + SUM(OPTN_PY_IBAMT) AS PY_AMT
FROM (
    SELECT DISTINCT
        T.CLS_YYMM, T.CLS_NDDT, A.MN_NRDPS_CTMNO, 'CA' AS IKD_GRPCD
        , C.CLMDT, B.RPBL_PY_IBAMT, B.OPTN_PY_IBAMT
    FROM GDRES_SYS_YYMM_PRED T
    INNER JOIN GDREC_ORIGIN_INS_CR_PRED A ON T.CLS_YYMM = A.CLS_YYMM
    LEFT  JOIN M_CMP_CR_CLM_CRST        B ON A.MN_NRDPS_CTMNO = B.NRDPS_CTMNO
    INNER JOIN M_CMP_CR_CMP_CLM_CR      C            -- [수정] LEFT→INNER
        ON  B.RCPDT = C.RCPDT AND B.RCP_NV_SEQNO = C.RCP_NV_SEQNO
        AND C.CLMDT BETWEEN F_LAST_DAY(F_PREV_MONTH(T.CLS_YYMM,'60')) AND T.CLS_NDDT
) AA
GROUP BY CLS_YYMM, CLS_NDDT, MN_NRDPS_CTMNO, IKD_GRPCD, CLMDT;


/* ============================================================================
   [21] 해지/해약 계약 이력
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_PRVGD_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_INS_PRVGD_PRED AS
SELECT DISTINCT
    A.CLS_YYMM, A.MN_NRDPS_CTMNO, A.CRT_CTMNO
    , B.PLYNO, D.CR_STCD
    , CASE
        WHEN E.GDNM LIKE '%Young%'                                          THEN 'L04'
        WHEN E.GDNM LIKE '%더건강 더실속%' OR E.MKTG_GD_CSFCD IN ('L02','L01') THEN 'L01'
        WHEN E.GDNM LIKE '%더건강%'                                          THEN 'L01'
        WHEN E.GDNM LIKE '%시그니처 여성 건강%'                                THEN 'L01'
        WHEN E.MKTG_GD_CSFCD = 'L03' THEN 'L03'  WHEN E.MKTG_GD_CSFCD = 'L04' THEN 'L04'
        WHEN E.MKTG_GD_CSFCD = 'L06' THEN 'L06'  WHEN E.MKTG_GD_CSFCD = 'L11' THEN 'L11'
        WHEN E.MKTG_GD_CSFCD = 'L08' THEN 'L08'
        WHEN E.GDNM LIKE '%세이프투게더%' THEN 'SAFE'
        WHEN E.GDNM LIKE '%실손의료보험%' THEN 'SS'
        WHEN REGEXP_LIKE(E.GDNM,'참 편한|WELL100|간편|3N5|355') THEN '유병자'
        WHEN E.MKTG_GD_CSFCD IN ('L12','L13') THEN 'L123'
        ELSE 'ETC'
      END AS GD_TYPE
    , C.INS_ST
FROM (SELECT DISTINCT CRT_CTMNO, MN_NRDPS_CTMNO, CLS_YYMM FROM GDREC_ORIGIN_INS_CR_PRED) A
LEFT JOIN INS_CR_RELPC B
    ON  A.CRT_CTMNO  = B.CTMNO
    AND B.AP_STRDT   <= F_LAST_DAY(A.CLS_YYMM) AND B.AP_NDDT > F_LAST_DAY(A.CLS_YYMM)
    AND B.RELPC_TPCD IN ('01')
LEFT JOIN INS_CR_RELPC B2
    ON  A.MN_NRDPS_CTMNO = B2.CTMNO
    AND B2.AP_STRDT  <= F_LAST_DAY(A.CLS_YYMM) AND B2.AP_NDDT > F_LAST_DAY(A.CLS_YYMM)
    AND B2.RELPC_TPCD IN ('02')
INNER JOIN INS_INS_CR C
    ON  B.PLYNO    = C.PLYNO
    AND C.AP_STRDT <= F_LAST_DAY(A.CLS_YYMM) AND C.AP_NDDT > F_LAST_DAY(A.CLS_YYMM)
    AND C.IKD_GRPCD = 'LA'
INNER JOIN INS_CR_ST_CRR D      -- CR_STCD 조회용 (NDS 기준)
    ON  D.PLYNO              = B.PLYNO
    AND D.NDS_AP_STR_DTHMS  <= F_LAST_DAY(A.CLS_YYMM)
    AND D.NDS_AP_ND_DTHMS    > F_LAST_DAY(A.CLS_YYMM)
INNER JOIN M_CRM_GD_CSF_INFO E ON C.GDCD = E.GDCD
WHERE D.CR_STCD NOT IN ('00','10');


/* ============================================================================
   [22] 부담보/표준하체할증 이력
============================================================================ */
DROP TABLE GDREC_ORIGIN_INS_NOCVR_XC_PRED PURGE;
-- ※ [최적화] DISTINCT + 불필요 컬럼(AP_STRDT/CVRCD/ATRVL/PLYNO) 제거 → GROUP BY로 미리 집계
--            MAIN9에서 MAX(NO_CVR_YN)/MAX(XC_YN) GROUP BY 연산 불필요해짐
CREATE TABLE GDREC_ORIGIN_INS_NOCVR_XC_PRED AS
SELECT
    A.CLS_YYMM
    , A.MN_NRDPS_CTMNO AS CTMNO
    , MAX(CASE WHEN C1.PLYNO IS NULL THEN 0 ELSE 1 END) AS NO_CVR_YN
    , MAX(CASE WHEN D1.PLYNO IS NULL THEN 0 ELSE 1 END) AS XC_YN
FROM GDREC_ORIGIN_INS_CR_PRED A
LEFT JOIN INS_CVR_AD_ATRVL C1
    ON  A.PLYNO = C1.PLYNO AND C1.CVRCD = 'CLA00503' AND C1.ATRCD = 'CA00119'
    AND C1.AP_STRDT < F_LAST_DAY(A.CLS_YYMM) AND C1.AP_NDDT >= F_LAST_DAY(A.CLS_YYMM)
LEFT JOIN INS_CR_CVR D1
    ON  A.PLYNO = D1.PLYNO AND D1.SUSTD_XC_RK_NDX > 0 AND D1.CVR_STCD = '01'
    AND D1.AP_STRDT < F_LAST_DAY(A.CLS_YYMM) AND D1.AP_NDDT >= F_LAST_DAY(A.CLS_YYMM)
GROUP BY A.CLS_YYMM, A.MN_NRDPS_CTMNO;

/*
   ※ GDREC_ORIGIN_INS_CHNL_PRED (채널별 기가입) → 여기 위치. 원본 파일 참조.
*/


/* ============================================================================
   [23] 1차 취합: 고객 기본 특성
============================================================================ */
DROP TABLE GDREC_ORIGIN_MAIN99_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_MAIN99_PRED AS
SELECT
    A.*
    , B1.NRD_CNT, B1.KIDS_YN
    , B2.CA_CNT
    , B3.INS_DIFF
    , B7.CTM_AGE, B7.CTM_SEX
    , B77.CTM_AGE AS NRD_AGE, B77.CTM_SEX AS NRD_SEX
    , B4.JB_SEG
    , B5.CLM_CNT, B5.PY_AMT
    , B6.NO_CVR_YN, B6.XC_YN
    , B8.DELAY_YYMM
FROM GDREC_ORIGIN_INS_PRMCNT_PRED A
LEFT JOIN GDREC_ORIGIN_INS_NRD_PRED     B1  ON A.CLS_YYMM = B1.CLS_YYMM AND A.CRT_CTMNO = B1.CRT_CTMNO
LEFT JOIN GDREC_ORIGIN_INS_CA_PRED      B2  ON A.CLS_YYMM = B2.CLS_YYMM AND A.CRT_CTMNO = B2.CRT_CTMNO
LEFT JOIN GDREC_ORIGIN_INS_INSDIFF_PRED B3  ON A.CLS_YYMM = B3.CLS_YYMM AND A.CRT_CTMNO = B3.CRT_CTMNO
LEFT JOIN GDREC_ORIGIN_INS_CRTJB_PRED  B4  ON A.CLS_YYMM = B4.CLS_YYMM AND A.CRT_CTMNO = B4.CTMNO
LEFT JOIN (
    SELECT CLS_YYMM, MN_NRDPS_CTMNO
        , COUNT(DISTINCT CLMDT) AS CLM_CNT
        , SUM(PY_AMT)           AS PY_AMT
    FROM GDREC_ORIGIN_INS_CLM_PRED
    GROUP BY CLS_YYMM, MN_NRDPS_CTMNO
) B5 ON A.CLS_YYMM = B5.CLS_YYMM AND A.MN_NRDPS_CTMNO = B5.MN_NRDPS_CTMNO
-- ※ NOCVR_XC_PRED가 이미 (CLS_YYMM, CTMNO) 단위로 집계됨 → GROUP BY 인라인뷰 불필요
LEFT JOIN GDREC_ORIGIN_INS_NOCVR_XC_PRED B6
    ON A.CLS_YYMM = B6.CLS_YYMM AND A.MN_NRDPS_CTMNO = B6.CTMNO
LEFT JOIN GDREC_ORIGIN_INS_CRTINFO_PRED  B7  ON A.CLS_YYMM = B7.CLS_YYMM  AND A.CRT_CTMNO      = B7.CRT_CTMNO
LEFT JOIN GDREC_ORIGIN_INS_NRDINFO_PRED  B77 ON A.CLS_YYMM = B77.CLS_YYMM AND A.MN_NRDPS_CTMNO = B77.MN_NRDPS_CTMNO
LEFT JOIN (
    SELECT CLS_YYMM, CTMNO
        , SUM(CASE WHEN DU_AR_FLGCD='01' THEN AP_PRM END) AS AP_PRM
        , SUM(CASE WHEN DU_AR_FLGCD='02' THEN AP_PRM END) AS DELAY_PRM
        , COUNT(DISTINCT CASE WHEN DU_AR_FLGCD='02' THEN CLS_YYMM END) AS DELAY_YYMM
        , SUM(CASE WHEN DU_AR_FLGCD='02' AND NW_AR_CTUAR_FLGCD='03' THEN AP_PRM END) AS CTU_DELAY_PRM
        , COUNT(DISTINCT CASE WHEN DU_AR_FLGCD='02' AND NW_AR_CTUAR_FLGCD='03' THEN CLS_YYMM END) AS CTU_DELAY_YYMM
    FROM GDREC_ORIGIN_INS_OVD_PRED
    GROUP BY CLS_YYMM, CTMNO
) B8 ON A.CLS_YYMM = B8.CLS_YYMM AND A.CRT_CTMNO = B8.CTMNO;


/* ============================================================================
   [24] 설계 정보
   ※ [성능] INNER JOIN BBB WHERE CTMNO IN (SELECT DISTINCT ...) →
      EXISTS로 변경 (PRMCNT가 이미 유니크키 수준이므로 semi-join이 더 효율적)
============================================================================ */
DROP TABLE GDREC_ORIGIN_PL_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_PL_PRED AS
SELECT *
FROM (
    SELECT DISTINCT
        AA.PL_YYMM, AA.PLNO, AA.PLDT, AA.PL_STCD, AA.PL_ST_CHDT
        , AA.DH_STFNO AS CE_STFNO, AA.USRNO AS CE_USRNO
        , BB.CTMNO AS CRT_CTMNO, BBB.CTMNO AS MN_NRDPS_CTMNO
        , AA.PLNM, AA.GD_TYPE, AA.PL_FIN_CD
        , ROW_NUMBER() OVER (PARTITION BY AA.PLNO ORDER BY AA.PLDT DESC) AS RN
    FROM (
        SELECT
            TO_CHAR(A.PLDT,'YYYYMM') AS PL_YYMM, A.PLNO, A.PLDT, A.CGAF_CH_SEQNO
            , A.PL_STCD, A.PL_ST_CHDT, B.DH_STFNO, B.USRNO, C.PLNM
            , CASE
                WHEN E.GDNM LIKE '%Young%'                                          THEN 'L04'
                WHEN E.GDNM LIKE '%더건강 더실속%' OR E.MKTG_GD_CSFCD IN ('L02','L01') THEN 'L01'
                WHEN E.GDNM LIKE '%더건강%'                                          THEN 'L01'
                WHEN E.GDNM LIKE '%시그니처 여성 건강%'                                THEN 'L01'
                WHEN E.MKTG_GD_CSFCD = 'L03' THEN 'L03'  WHEN E.MKTG_GD_CSFCD = 'L04' THEN 'L04'
                WHEN E.MKTG_GD_CSFCD = 'L06' THEN 'L06'  WHEN E.MKTG_GD_CSFCD = 'L11' THEN 'L11'
                WHEN E.MKTG_GD_CSFCD = 'L08' THEN 'L08'
                WHEN E.GDNM LIKE '%세이프투게더%' THEN 'SAFE'
                WHEN E.GDNM LIKE '%실손의료보험%' THEN 'SS'
                WHEN REGEXP_LIKE(E.GDNM,'참 편한|WELL100|간편|3N5|355') THEN '유병자'
                WHEN E.MKTG_GD_CSFCD IN ('L12','L13') THEN 'L123'
                ELSE 'ETC'
              END AS GD_TYPE
            , CASE WHEN A.PL_STCD IN ('03','04','05','06','07','08','09') THEN 1 ELSE 0 END AS PL_FIN_CD
        FROM INS_INS_PL A
        LEFT JOIN INS_PL_DH_STF  B ON A.PLNO=B.PLNO AND A.CGAF_CH_SEQNO=B.CGAF_CH_SEQNO
                                  AND B.DH_STF_TPCD='01' AND B.IKD_GRPCD='LA'
        LEFT JOIN INS_GD_CE_PL   C ON A.PLCD=C.PLCD AND A.GDCD=C.GDCD
        LEFT JOIN M_CRM_GD_CSF_INFO E ON A.GDCD=E.GDCD
        WHERE A.PL_FLGCD='01' AND A.IKD_GRPCD='LA' AND A.VALD_PL_YN='1'
    ) AA
    INNER JOIN INS_PL_RELPC BB
        ON  AA.PLNO=BB.PLNO AND AA.CGAF_CH_SEQNO=BB.CGAF_CH_SEQNO
        AND BB.IKD_GRPCD='LA' AND BB.RELPC_TPCD IN ('01')
        -- [성능] IN(SELECT DISTINCT ...) → EXISTS (semi-join, PRMCNT 재스캔 방지)
        AND EXISTS (SELECT 1 FROM GDREC_ORIGIN_INS_PRMCNT_PRED P WHERE BB.CTMNO = P.CRT_CTMNO)
    INNER JOIN INS_PL_RELPC BBB
        ON  AA.PLNO=BBB.PLNO AND AA.CGAF_CH_SEQNO=BBB.CGAF_CH_SEQNO
        AND BBB.IKD_GRPCD='LA' AND BBB.RELPC_TPCD IN ('02')
        AND EXISTS (SELECT 1 FROM GDREC_ORIGIN_INS_PRMCNT_PRED P WHERE BBB.CTMNO = P.MN_NRDPS_CTMNO)
)
WHERE RN = 1;


/* ============================================================================
   [25] 설계 이력 건수 PIVOT
   [26] 설계 완료 건수 PIVOT
   ※ 두 테이블은 WHERE PL_FIN_CD=1 유무만 다름 → 공통 인라인 뷰 구조 사용
============================================================================ */
DROP TABLE GDREC_ORIGIN_PL_ALL_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_PL_ALL_PRED AS
SELECT *
FROM (
    SELECT CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO, GD_TYPE
        , COUNT(DISTINCT PLNO) AS PLNO_CNT
    FROM (
        SELECT A.*, B.PLDT, B.GD_TYPE, B.PLNO
            , RANK() OVER (PARTITION BY A.CRT_CTMNO, A.MN_NRDPS_CTMNO ORDER BY A.CLS_YYMM DESC) AS RN
        FROM GDREC_ORIGIN_INS_PRMCNT_PRED A
        LEFT JOIN GDREC_ORIGIN_PL_PRED    B
            ON  A.CRT_CTMNO = B.CRT_CTMNO AND A.MN_NRDPS_CTMNO = B.MN_NRDPS_CTMNO
            AND F_LAST_DAY(A.CLS_YYMM) >= B.PLDT
    )
    WHERE RN = 1
    GROUP BY CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO, GD_TYPE
)
PIVOT (MAX(PLNO_CNT) FOR GD_TYPE IN (
    'L01' AS L01,'L03' AS L03,'L04' AS L04,'L06' AS L06,'L08' AS L08,
    'SAFE' AS SAFE,'SS' AS SS,'유병자' AS 유병자,'L11' AS L11,'L123' AS L123
)) P;

DROP TABLE GDREC_ORIGIN_PL_CL_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_PL_CL_PRED AS
SELECT *
FROM (
    SELECT CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO, GD_TYPE
        , COUNT(DISTINCT PLNO) AS PLNO_CNT
    FROM (
        SELECT A.*, B.PLDT, B.GD_TYPE, B.PLNO
            , RANK() OVER (PARTITION BY A.CRT_CTMNO, A.MN_NRDPS_CTMNO ORDER BY A.CLS_YYMM DESC) AS RN
        FROM GDREC_ORIGIN_INS_PRMCNT_PRED A
        LEFT JOIN GDREC_ORIGIN_PL_PRED    B
            ON  A.CRT_CTMNO = B.CRT_CTMNO AND A.MN_NRDPS_CTMNO = B.MN_NRDPS_CTMNO
            AND F_LAST_DAY(A.CLS_YYMM) >= B.PLDT
        WHERE B.PL_FIN_CD = 1          -- 설계 완료만
    )
    WHERE RN = 1
    GROUP BY CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO, GD_TYPE
)
PIVOT (MAX(PLNO_CNT) FOR GD_TYPE IN (
    'L01' AS L01,'L03' AS L03,'L04' AS L04,'L06' AS L06,'L08' AS L08,
    'SAFE' AS SAFE,'SS' AS SS,'유병자' AS 유병자,'L11' AS L11,'L123' AS L123
)) P;


/* ============================================================================
   [27] 설계 정보 종합
============================================================================ */
DROP TABLE GDREC_TMGD_PL_INFO_PRED PURGE;
CREATE TABLE GDREC_TMGD_PL_INFO_PRED AS
SELECT
    A.CLS_YYMM, A.CRT_CTMNO, A.MN_NRDPS_CTMNO
    , NVL(B1.L01,0) AS L01_설계이력,  NVL(B1.L03,0) AS L03_설계이력
    , NVL(B1.L04,0) AS L04_설계이력,  NVL(B1.L06,0) AS L06_설계이력
    , NVL(B1.L08,0) AS L08_설계이력,  NVL(B1.SAFE,0) AS SAFE_설계이력
    , NVL(B1.SS,0)  AS SS_설계이력,   NVL(B1.유병자,0) AS 유병자_설계이력
    , NVL(B1.L11,0) AS L11_설계이력,  NVL(B1.L123,0) AS L123_설계이력
    , NVL(B2.L01,0) AS L01_설계완료,  NVL(B2.L03,0) AS L03_설계완료
    , NVL(B2.L04,0) AS L04_설계완료,  NVL(B2.L06,0) AS L06_설계완료
    , NVL(B2.L08,0) AS L08_설계완료,  NVL(B2.SAFE,0) AS SAFE_설계완료
    , NVL(B2.SS,0)  AS SS_설계완료,   NVL(B2.유병자,0) AS 유병자_설계완료
    , NVL(B2.L11,0) AS L11_설계완료,  NVL(B2.L123,0) AS L123_설계완료
    , B3.GD_TYPE AS 최근가입설계상품
FROM GDREC_ORIGIN_INS_PRMCNT_PRED A
LEFT JOIN GDREC_ORIGIN_PL_ALL_PRED B1
    ON A.CLS_YYMM=B1.CLS_YYMM AND A.CRT_CTMNO=B1.CRT_CTMNO AND A.MN_NRDPS_CTMNO=B1.MN_NRDPS_CTMNO
LEFT JOIN GDREC_ORIGIN_PL_CL_PRED B2
    ON A.CLS_YYMM=B2.CLS_YYMM AND A.CRT_CTMNO=B2.CRT_CTMNO AND A.MN_NRDPS_CTMNO=B2.MN_NRDPS_CTMNO
LEFT JOIN (
    SELECT *
    FROM (
        SELECT A.*, B.GD_TYPE, B.PLNO
            , RANK()       OVER (PARTITION BY A.CRT_CTMNO,A.MN_NRDPS_CTMNO ORDER BY A.CLS_YYMM DESC)      AS RN
            , ROW_NUMBER() OVER (PARTITION BY A.CRT_CTMNO,A.MN_NRDPS_CTMNO ORDER BY A.CLS_YYMM DESC, B.PLDT DESC) AS RN2
        FROM GDREC_ORIGIN_INS_PRMCNT_PRED A
        LEFT JOIN GDREC_ORIGIN_PL_PRED    B
            ON A.CRT_CTMNO=B.CRT_CTMNO AND A.MN_NRDPS_CTMNO=B.MN_NRDPS_CTMNO
            AND F_LAST_DAY(A.CLS_YYMM) >= B.PLDT
    )
    WHERE RN=1 AND RN2=1
) B3 ON A.CLS_YYMM=B3.CLS_YYMM AND A.CRT_CTMNO=B3.CRT_CTMNO AND A.MN_NRDPS_CTMNO=B3.MN_NRDPS_CTMNO;


/* ============================================================================
   [28+32] 사고/지급 보험금 통합 (무사고 판별용 + 최근 입원 청구)
   ※ [최적화] 원본 CLM_ALL + CLM_G 가 동일 소스(M_CMP_GN_CVRCL_PY_IBNF_LIST) 2회 풀스캔
              → 1회 스캔 후 CASE WHEN으로 분기, 테이블 1개로 통합
   ※ [최적화] 출력에 미사용인 LEFT JOIN 4개(LSE_CLMPS/LSE_DGN/M_LCR_LTINS_CR/SUS_DSACD) 제거
   ※ CLM_INFO(step 33)에서 B1(CLM_G)/B5(CLM_ALL) → B1.G_최근사고일자/B5.ALL_최근사고일자 로 참조
============================================================================ */
DROP TABLE GDREC_ORIGIN_CLM_ALL_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_CLM_ALL_PRED AS
SELECT
    A.CLS_YYMM, A.CLMPS_CTMNO, A.CLMPS_CTM_DSCNO
    -- 전체 사고 (CLM_ALL 역할)
    , SUM(A.WONCR_CV_PYAMT)                                                     AS 지급보험금
    , MAX(A.PRVDT)                                                               AS 최근사고일자
    -- 입원/수술 청구(G001) (CLM_G 역할)
    , SUM(CASE WHEN A.CLM_CVR_LCLCD IN ('G001') THEN A.WONCR_CV_PYAMT ELSE 0 END) AS G_지급보험금
    , MAX(CASE WHEN A.CLM_CVR_LCLCD IN ('G001') THEN A.PRVDT END)               AS G_최근사고일자
FROM (
    SELECT BB.CLS_YYMM, AA.*
    FROM M_CMP_GN_CVRCL_PY_IBNF_LIST AA
    INNER JOIN GDREC_ORIGIN_INS_PRMCNT_PRED BB
        ON AA.CLMPS_CTMNO = BB.CRT_CTMNO AND F_LAST_DAY(BB.CLS_YYMM) >= AA.PRVDT
    WHERE AA.PLYNO IS NOT NULL AND AA.IKD_GRPCD='LA' AND AA.CCL_YN='0'
      AND COALESCE(AA.UDRTK_TYCD,'01') <> '03'
      AND AA.XI_PY_FLGCD IN ('02','03') AND AA.CLM_NV_CSFCD='11'
) A
GROUP BY A.CLS_YYMM, A.CLMPS_CTMNO, A.CLMPS_CTM_DSCNO;


/* ============================================================================
   [29] 중대질환 청구 여부
============================================================================ */
DROP TABLE GDREC_ORIGIN_CLM_CSF_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_CLM_CSF_PRED AS
SELECT A.CLS_YYMM, A.CLMPS_CTMNO AS CTMNO, MAX(A.CLMDT) AS DT
FROM (
    SELECT BB.CLS_YYMM, AA.*
    FROM M_CMP_GN_CVRCL_PY_IBNF_LIST AA
    INNER JOIN GDREC_ORIGIN_INS_PRMCNT_PRED BB
        ON AA.CLMPS_CTMNO = BB.CRT_CTMNO AND F_LAST_DAY(BB.CLS_YYMM) >= AA.PRVDT
) A
INNER JOIN LSE_DGN C
    ON A.RCP_YYMM=C.RCP_YYMM AND A.RCP_NV_SEQNO=C.RCP_NV_SEQNO
   AND A.CLMPS_SEQNO=C.CLMPS_SEQNO AND A.CLM_NV_SEQNO=C.CLM_NV_SEQNO
INNER JOIN (
    SELECT DISTINCT DSACD FROM INS_UD_DSAS_CSF_REL
    WHERE AP_NDDT = F_LAST_DAY('999912')
      AND DSAS_CSFCD IN (
        'UW02010','UW02020','UW02030','UW02040','UW02050','UW02060','UW02070','UW02080','UW02090',
        'UW02100','UW02110','UW02120','UW02130','UW02140','UW02150','UW02160','UW02170','UW02180',
        'UW03010','UW03020','UW03030','UW03040','UW03050','UW03060',
        'UW04010','UW04020','UW04030','UW04040',
        'UW09070','UW09090','UW09250','UW09260',
        'UW12220','UW12210','UW12290','UW12300','UW12110','UW16120')
) Z ON C.DGNCD = Z.DSACD
GROUP BY A.CLS_YYMM, A.CLMPS_CTMNO;


/* ============================================================================
   [30] 중대질환 고지 여부
   [31] 입원/수술 고지 여부
   ※ 두 테이블은 INS_BFPL_DSAS_NC_MTT 조인 구조 동일, WHERE 조건만 다름
============================================================================ */
DROP TABLE GDREC_ORIGIN_CLM_MTT_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_CLM_MTT_PRED AS
SELECT AA.*, BB.DGNDT
FROM GDREC_ORIGIN_INS_PRMCNT_PRED AA
INNER JOIN (
    SELECT NVL(B.CTMNO, A.CTMNO) AS CTMNO, MAX(A.DGNDT) AS DGNDT
    FROM INS_BFPL_DSAS_NC_MTT A
    LEFT JOIN INS_PL_RELPC    B ON A.PLNO=B.PLNO AND A.CGAF_CH_SEQNO=B.CGAF_CH_SEQNO AND A.RELPC_SEQNO=B.RELPC_SEQNO
    WHERE A.DSACD IN (
        'UW02010','UW02020','UW02030','UW02040','UW02050','UW02060','UW02070','UW02080','UW02090',
        'UW02100','UW02110','UW02120','UW02130','UW02140','UW02150','UW02160','UW02170','UW02180',
        'UW03010','UW03020','UW03030','UW03040','UW03050','UW03060',
        'UW04010','UW04020','UW04030','UW04040',
        'UW09070','UW09090','UW09250','UW09260',
        'UW12220','UW12210','UW12290','UW12300','UW12110','UW16120')
    GROUP BY NVL(B.CTMNO, A.CTMNO)
) BB ON AA.MN_NRDPS_CTMNO = BB.CTMNO AND F_LAST_DAY(AA.CLS_YYMM) >= BB.DGNDT;

DROP TABLE GDREC_ORIGIN_CLM_HSP_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_CLM_HSP_PRED AS
SELECT AA.*, BB.DGNDT
FROM GDREC_ORIGIN_INS_PRMCNT_PRED AA
INNER JOIN (
    SELECT NVL(B.CTMNO, A.CTMNO) AS CTMNO, MAX(A.DGNDT) AS DGNDT
    FROM INS_BFPL_DSAS_NC_MTT A
    LEFT JOIN INS_PL_RELPC    B ON A.PLNO=B.PLNO AND A.CGAF_CH_SEQNO=B.CGAF_CH_SEQNO AND A.RELPC_SEQNO=B.RELPC_SEQNO
    WHERE NVL(A.OP_RMDY_YN,0) + NVL(A.RL_HSP_YN,0) >= 1   -- 입원 또는 수술
    GROUP BY NVL(B.CTMNO, A.CTMNO)
) BB ON AA.MN_NRDPS_CTMNO = BB.CTMNO AND F_LAST_DAY(AA.CLS_YYMM) >= BB.DGNDT;


-- ※ [32] CLM_G_PRED 제거 — CLM_ALL_PRED에 G_최근사고일자 컬럼으로 통합됨


/* ============================================================================
   [33] 청구 정보 종합
============================================================================ */
DROP TABLE GDREC_TMGD_CLM_INFO_PRED PURGE;
CREATE TABLE GDREC_TMGD_CLM_INFO_PRED AS
-- ※ B1(CLM_G) 제거 → CLM_ALL의 G_최근사고일자 컬럼으로 대체
SELECT
    A.CLS_YYMM, A.CRT_CTMNO, A.MN_NRDPS_CTMNO
    , TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A.CLS_YYMM), B5.G_최근사고일자) / 12, 0) AS 입원청구
    , TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A.CLS_YYMM), B2.DGNDT)          / 12, 0) AS 입원고지
    , TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A.CLS_YYMM), B3.DGNDT)          / 12, 0) AS 중대질환고지
    , TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A.CLS_YYMM), B4.DT)             / 12, 0) AS 중대질환청구
    , TRUNC(MONTHS_BETWEEN(F_LAST_DAY(A.CLS_YYMM), B5.최근사고일자)   / 12, 0) AS 무사고
FROM GDREC_ORIGIN_INS_PRMCNT_PRED A
LEFT JOIN GDREC_ORIGIN_CLM_HSP_PRED B2 ON A.CLS_YYMM=B2.CLS_YYMM AND A.MN_NRDPS_CTMNO=B2.MN_NRDPS_CTMNO
LEFT JOIN GDREC_ORIGIN_CLM_MTT_PRED B3 ON A.CLS_YYMM=B3.CLS_YYMM AND A.MN_NRDPS_CTMNO=B3.MN_NRDPS_CTMNO
LEFT JOIN GDREC_ORIGIN_CLM_CSF_PRED B4 ON A.CLS_YYMM=B4.CLS_YYMM AND A.MN_NRDPS_CTMNO=B4.CTMNO
LEFT JOIN GDREC_ORIGIN_CLM_ALL_PRED B5 ON A.CLS_YYMM=B5.CLS_YYMM AND A.MN_NRDPS_CTMNO=B5.CLMPS_CTMNO;


/* ============================================================================
   [34] 2차 취합: 기가입/채널/담보금액/이력 통합
============================================================================ */
DROP TABLE GDREC_ORIGIN_MAIN9_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_MAIN9_PRED AS
SELECT
    A.*
    -- 상품 유형별 기가입
    , NVL(B1.L01,0) AS L01_기가입,   NVL(B1.L03,0) AS L03_기가입
    , NVL(B1.L04,0) AS L04_기가입,   NVL(B1.L06,0) AS L06_기가입
    , NVL(B1.L08,0) AS L08_기가입,   NVL(B1.SAFE,0) AS SAFE_기가입
    , NVL(B1.SS,0)  AS SS_기가입,    NVL(B1.유병자,0) AS 유병자_기가입
    , NVL(B1.L11,0) AS L11_기가입,   NVL(B1.L123,0) AS L123_기가입
    -- 채널별 기가입
    , NVL(B2.전속,0) AS 전속_기가입,  NVL(B2.교차,0) AS 교차_기가입
    , NVL(B2.GA,0)   AS GA_기가입,   NVL(B2.TM,0)   AS TM_기가입
    , NVL(B2.CM,0)   AS CM_기가입
    , NVL(B2.방카,0)+NVL(B2.기업,0)+NVL(B2.LIFEWITH,0)+NVL(B2.본사기타,0) AS 그외채널_기가입
    -- 담보 가입금액 (SDADAM.M_BIZ_CTM_INFO_CVR_LIST 에서)
    , NVL(B3.DSDE_AMT,0) AS DSDE_AMT,                 NVL(B3.INJR_DE_AMT,0) AS INJR_DE_AMT
    , NVL(B3.CANCR_DE_AMT,0) AS CANCR_DE_AMT,         NVL(B3.TRF_INJR_DE_AMT,0) AS TRF_INJR_DE_AMT
    , NVL(B3.DSAS_SLOBS_AMT,0) AS DSAS_SLOBS_AMT,     NVL(B3.DSAS_DGR_SLOBS_AMT,0) AS DSAS_DGR_SLOBS_AMT
    , NVL(B3.INJR_SLOBS_AMT,0) AS INJR_SLOBS_AMT,     NVL(B3.INJR_DGR_SLOBS_AMT,0) AS INJR_DGR_SLOBS_AMT
    , NVL(B3.SMLY_CANCR_DASCS_AMT,0) AS SMLY_CANCR_DASCS_AMT
    , NVL(B3.CANCR_DASCS_AMT,0) AS CANCR_DASCS_AMT,   NVL(B3.HAMT_CANCR_DASCS_AMT,0) AS HAMT_CANCR_DASCS_AMT
    , NVL(B3.RE_DGN_CANCR_AMT,0) AS RE_DGN_CANCR_AMT, NVL(B3.CANCR_HSP_DDALW_AMT,0) AS CANCR_HSP_DDALW_AMT
    , NVL(B3.CANCR_OPCCS_AMT,0) AS CANCR_OPCCS_AMT,   NVL(B3.CRLR_DSAS_DASCS_AMT,0) AS CRLR_DSAS_DASCS_AMT
    , NVL(B3.STRK_DASCS_AMT,0) AS STRK_DASCS_AMT,     NVL(B3.CBHMH_DASCS_AMT,0) AS CBHMH_DASCS_AMT
    , NVL(B3.CRLR_DSAS_OPCCS_AMT,0) AS CRLR_DSAS_OPCCS_AMT
    , NVL(B3.ISMC_HEART_DSAS_DASCS_AMT,0) AS ISMC_HEART_DSAS_DASCS_AMT
    , NVL(B3.AMIFN_INCR_DASCS_AMT,0) AS AMIFN_INCR_DASCS_AMT
    , NVL(B3.ISMC_HEART_DSAS_OPCCS_AMT,0) AS ISMC_HEART_DSAS_OPCCS_AMT
    , NVL(B3.CI_AMT,0) AS CI_AMT,                     NVL(B3.GI_AMT,0) AS GI_AMT
    , NVL(B3.DSAS_HSP_RLPMI_AMT,0) AS DSAS_HSP_RLPMI_AMT
    , NVL(B3.DSAS_OTP_RLPMI_AMT,0) AS DSAS_OTP_RLPMI_AMT
    , NVL(B3.INJR_HSP_RLPMI_AMT,0) AS INJR_HSP_RLPMI_AMT
    , NVL(B3.INJR_OTP_RLPMI_AMT,0) AS INJR_OTP_RLPMI_AMT
    , NVL(B3.DSAS_HSP_DDALW_1_AMT,0) AS DSAS_HSP_DDALW_1_AMT
    , NVL(B3.DSAS_HSP_DDALW_4_AMT,0) AS DSAS_HSP_DDALW_4_AMT
    , NVL(B3.INJR_HSP_DDALW_1_AMT,0) AS INJR_HSP_DDALW_1_AMT
    , NVL(B3.INJR_HSP_DDALW_4_AMT,0) AS INJR_HSP_DDALW_4_AMT
    , NVL(B3.DSAS_OPCCS_AMT,0) AS DSAS_OPCCS_AMT,     NVL(B3.INJR_OPCCS_AMT,0) AS INJR_OPCCS_AMT
    , NVL(B3.MILD_DEMEN_AMT,0) AS MILD_DEMEN_AMT,     NVL(B3.SERI_DEMEN_AMT,0) AS SERI_DEMEN_AMT
    , NVL(B3.LTRM_RCPR_DGN_RANK4_AMT,0) AS LTRM_RCPR_DGN_RANK4_AMT
    , NVL(B3.LTRM_RCPR_DGN_RANK1_AMT,0) AS LTRM_RCPR_DGN_RANK1_AMT
    , NVL(B3.BDIN_CCA_SUAMT_AMT,0) AS BDIN_CCA_SUAMT_AMT
    , NVL(B3.LWR_SNRT_CS_AMT,0) AS LWR_SNRT_CS_AMT,  NVL(B3.DRV_PNLTY_AMT,0) AS DRV_PNLTY_AMT
    , NVL(B3.AUTO_CRCLM_INJ_URAMT,0) AS AUTO_CRCLM_INJ_URAMT
    , NVL(B3.FIRE_PNLTY_AMT,0) AS FIRE_PNLTY_AMT,    NVL(B3.USLLF_LBTRS_AMT,0) AS USLLF_LBTRS_AMT
    , NVL(B3.IMPL_MDCF_AMT,0) AS IMPL_MDCF_AMT,       NVL(B3.CROW_MDCF_AMT,0) AS CROW_MDCF_AMT
    , NVL(B3.FRCTR_DASCS_AMT,0) AS FRCTR_DASCS_AMT,   NVL(B3.BURN_DASCS_AMT,0) AS BURN_DASCS_AMT
    , NVL(B3.FOCUS_ANTI_MEDI_APPR_MDCF,0) AS FOCUS_ANTI_MEDI_APPR_MDCF
    , NVL(B3.DSAS_OPCCS_14_KND_ISYN,0) AS DSAS_OPCCS_14_KND_ISYN
    , NVL(B3.DSAS_OPCCS_16_KND_ISYN,0) AS DSAS_OPCCS_16_KND_ISYN
    , NVL(B3.DSAS_OPCCS_18_KND_ISYN,0) AS DSAS_OPCCS_18_KND_ISYN
    , NVL(B3.DSAS_OPCCS_34_KND_ISYN,0) AS DSAS_OPCCS_34_KND_ISYN
    , NVL(B3.DSAS_OPCCS_56_KND_ISYN,0) AS DSAS_OPCCS_56_KND_ISYN
    , NVL(B3.DSAS_OPCCS_121_KND_ISYN,0) AS DSAS_OPCCS_121_KND_ISYN
    , NVL(B3.GB_AMT,0) AS GB_AMT,                     NVL(B3.GB_AMT2,0) AS GB_AMT2
    -- 해지/해약 이력
    , NVL(B5.L01,0) AS L01_이력,   NVL(B5.L03,0) AS L03_이력
    , NVL(B5.L04,0) AS L04_이력,   NVL(B5.L06,0) AS L06_이력
    , NVL(B5.L08,0) AS L08_이력,   NVL(B5.SAFE,0) AS SAFE_이력
    , NVL(B5.SS,0)  AS SS_이력,    NVL(B5.유병자,0) AS 유병자_이력
    , NVL(B5.L11,0) AS L11_이력,   NVL(B5.L123,0) AS L123_이력
    , NVL(B4.PRED_INCOME,0) AS PRED_INCOME
FROM GDREC_ORIGIN_MAIN99_PRED A
LEFT JOIN GDREC_ORIGIN_INS_GD_PRED    B1
    ON A.CLS_YYMM=B1.CLS_YYMM AND A.CRT_CTMNO=B1.CRT_CTMNO AND A.MN_NRDPS_CTMNO=B1.MN_NRDPS_CTMNO
LEFT JOIN GDREC_ORIGIN_INS_CHNL_PRED  B2
    ON A.CLS_YYMM=B2.CLS_YYMM AND A.CRT_CTMNO=B2.CRT_CTMNO AND A.MN_NRDPS_CTMNO=B2.MN_NRDPS_CTMNO
LEFT JOIN SDADAM.M_BIZ_CTM_INFO_CVR_LIST B3
    ON A.CLS_YYMM = F_PREV_MONTH(B3.CLS_YYMM,'-1') AND A.MN_NRDPS_CTMNO=B3.CTMNO
LEFT JOIN SDADAM.FINANCIAL_DAM_PRED    B4
    ON A.CLS_YYMM = F_PREV_MONTH(B4.STYYMM,'-1') AND A.CRT_CTMNO=B4.CTMNO
LEFT JOIN (
    SELECT *
    FROM (
        SELECT CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO, GD_TYPE
            , COUNT(DISTINCT PLYNO) AS PLY_CNT
        FROM GDREC_ORIGIN_INS_PRVGD_PRED
        GROUP BY CLS_YYMM, CRT_CTMNO, MN_NRDPS_CTMNO, GD_TYPE
    )
    PIVOT (MAX(PLY_CNT) FOR GD_TYPE IN (
        'L01' AS L01,'L03' AS L03,'L04' AS L04,'L06' AS L06,'L08' AS L08,
        'SAFE' AS SAFE,'SS' AS SS,'유병자' AS 유병자,'L11' AS L11,'L123' AS L123
    )) P
) B5 ON A.CLS_YYMM=B5.CLS_YYMM AND A.CRT_CTMNO=B5.CRT_CTMNO AND A.MN_NRDPS_CTMNO=B5.MN_NRDPS_CTMNO;


/* ============================================================================
   [35] 최종 결과
============================================================================ */
DROP TABLE GDREC_ORIGIN_MAIN_FIN_PRED PURGE;
CREATE TABLE GDREC_ORIGIN_MAIN_FIN_PRED AS
SELECT
    A.*
    , B1.L01_설계이력, B1.L03_설계이력, B1.L04_설계이력, B1.L06_설계이력, B1.L08_설계이력
    , B1.SAFE_설계이력, B1.SS_설계이력, B1.유병자_설계이력, B1.L11_설계이력, B1.L123_설계이력
    , B1.L01_설계완료, B1.L03_설계완료, B1.L04_설계완료, B1.L06_설계완료, B1.L08_설계완료
    , B1.SAFE_설계완료, B1.SS_설계완료, B1.유병자_설계완료, B1.L11_설계완료, B1.L123_설계완료
    , B1.최근가입설계상품
    -- NULL='X', >10='10', 그 외=연수 문자열
    , CASE WHEN B2.입원청구    > 10 THEN '10' WHEN B2.입원청구    IS NULL THEN 'X' ELSE TO_CHAR(B2.입원청구)    END AS 입원청구
    , CASE WHEN B2.입원고지    > 10 THEN '10' WHEN B2.입원고지    IS NULL THEN 'X' ELSE TO_CHAR(B2.입원고지)    END AS 입원고지
    , CASE WHEN B2.중대질환고지 > 10 THEN '10' WHEN B2.중대질환고지 IS NULL THEN 'X' ELSE TO_CHAR(B2.중대질환고지) END AS 중대질환고지
    , CASE WHEN B2.중대질환청구 > 10 THEN '10' WHEN B2.중대질환청구 IS NULL THEN 'X' ELSE TO_CHAR(B2.중대질환청구) END AS 중대질환청구
    , CASE WHEN B2.무사고      > 10 THEN '10' WHEN B2.무사고      IS NULL THEN 'X' ELSE TO_CHAR(B2.무사고)      END AS 무사고
FROM GDREC_ORIGIN_MAIN9_PRED A
LEFT JOIN GDREC_TMGD_PL_INFO_PRED  B1
    ON A.CRT_CTMNO=B1.CRT_CTMNO AND A.CLS_YYMM=B1.CLS_YYMM AND A.MN_NRDPS_CTMNO=B1.MN_NRDPS_CTMNO
LEFT JOIN GDREC_TMGD_CLM_INFO_PRED B2
    ON A.CRT_CTMNO=B2.CRT_CTMNO AND A.CLS_YYMM=B2.CLS_YYMM AND A.MN_NRDPS_CTMNO=B2.MN_NRDPS_CTMNO;


/* 추천 상품 결과 최종 */
SELECT 
	CTMNO
	, REC_CD
	, REC_RANK
	, AP_SEQ
	, AP_STRDT
	, AP_NDDT
	, REC_GDCD
	, REC_GDNM
	, REC_POCT
	, REC_RS1
	, CUSTID
	, FIN_YN
FROM SDADAM.M_CRM_REC_RLT_BIZ;
