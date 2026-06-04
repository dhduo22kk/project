import json
import random
import warnings
import numpy as np
import pandas as pd
from datetime import datetime
warnings.filterwarnings('ignore')

from config import VAR_CONFIG, SQL_FILES
from db import connect, run_sql_file, recreate_and_insert
from gd_filter import load_filter_data, gd_filter_func, cus_script_func, load_script_dict
from model import load_models, predict_scores


# ── DDL 상수 ─────────────────────────────────────────────────────────────────

_GDNM_TM_DDL = """
    CREATE TABLE M_CRM_REC_GDNM_TM (
        GDCD VARCHAR2(100), SL_NDDT DATE, SL_STRDT DATE,
        INP_USR_ID VARCHAR2(100), INP_DTHMS DATE,
        MDF_USR_ID VARCHAR2(100), MDF_DTHMS DATE,
        GD_TYPE VARCHAR2(10), GDNM VARCHAR2(100),
        SL_CHNCD VARCHAR2(10), GDNM_CLEAN VARCHAR2(100)
    )
"""
_GDNM_TM_INSERT = (
    'INSERT INTO M_CRM_REC_GDNM_TM VALUES '
    '(:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11)'
)

_REC_RLT_DDL = """
    CREATE TABLE M_CRM_REC_RLT_BIZ (
        CTMNO VARCHAR2(9), REC_CD VARCHAR2(2), REC_RANK VARCHAR2(2),
        AP_SEQ VARCHAR2(2), AP_STRDT DATE, AP_NDDT DATE,
        REC_GDCD VARCHAR2(10), REC_GDNM VARCHAR2(100),
        REC_POCT NUMBER, REC_RS1 VARCHAR2(1000),
        CUSTID VARCHAR2(10), FIN_YN VARCHAR2(2)
    )
"""
_REC_RLT_INSERT = (
    'INSERT INTO M_CRM_REC_RLT_BIZ VALUES '
    '(:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12)'
)

_CVR_COLS = [
    'CANCR_DASCS_AMT', 'ISMC_HEART_DSAS_DASCS_AMT', 'CRLR_DSAS_DASCS_AMT',
    'BDIN_CCA_SUAMT_AMT', 'LWR_SNRT_CS_AMT', 'DRV_PNLTY_AMT',
    'DSAS_HSP_RLPMI_AMT', 'DSAS_OTP_RLPMI_AMT', 'SERI_DEMEN_AMT',
    'LTRM_RCPR_DGN_RANK4_AMT', 'FIRE_PNLTY_AMT', 'USLLF_LBTRS_AMT',
]


# ── Step 1: Oracle 학습 데이터 생성 ──────────────────────────────────────────

def step_data_generation(conn) -> None:
    for path in SQL_FILES:
        print(f'\n=== {path.name} ===')
        run_sql_file(conn, path)


# ── Step 2: 예측 데이터 로딩 ─────────────────────────────────────────────────

def step_load_predict_data(conn) -> pd.DataFrame:
    sql = """
        SELECT * FROM (
            SELECT A.*,
                ROW_NUMBER() OVER (
                    PARTITION BY CRT_CTMNO, MN_NRDPS_CTMNO
                    ORDER BY (SELECT 1 FROM DUAL)
                ) AS RN
            FROM GDREC_ORIGIN_MAIN_FIN_PRED A
            WHERE MN_NRDPS_CTMNO IS NOT NULL
        ) WHERE RN = 1
    """
    return pd.read_sql(sql, con=conn)


# ── Step 3: 모델 예측 ─────────────────────────────────────────────────────────

def step_predict(df: pd.DataFrame) -> pd.DataFrame:
    with open(VAR_CONFIG, 'r', encoding='utf-8') as f:
        config = json.load(f)

    predictors = load_models()
    df_scores = predict_scores(
        df,
        predictors,
        cvr_vars=config['cvr_var_list'],
        ins_vars=config['ins_var_list'],
        other_vars=config['other_var_list'],
    )
    # CLS_YYMM / 식별자 붙이기
    id_cols = df[['CLS_YYMM', 'CRT_CTMNO', 'MN_NRDPS_CTMNO']]
    return pd.concat([id_cols.reset_index(drop=True), df_scores], axis=1)


# ── Step 4: 필터링 + 상품명 결정 ─────────────────────────────────────────────

def step_filter_and_name(df: pd.DataFrame, df_scores: pd.DataFrame, conn) -> pd.DataFrame:
    fdata = load_filter_data(conn)
    df_gd       = fdata['df_gd']
    type_names  = fdata['type_to_names']
    block_dict  = fdata['block_dict']

    # 상품명 마스터 Oracle 저장
    recreate_and_insert(
        conn, 'M_CRM_REC_GDNM_TM', _GDNM_TM_DDL,
        df_gd, _GDNM_TM_INSERT, grant_public=True,
    )

    # wide → long
    merged = (
        df_scores.drop(columns=['CLS_YYMM'])
        .melt(id_vars=['CRT_CTMNO', 'MN_NRDPS_CTMNO'], var_name='상품', value_name='확률')
        .merge(df[['CRT_CTMNO', 'CTM_AGE', 'CTM_SEX']], on='CRT_CTMNO', how='left')
        .merge(
            df[['MN_NRDPS_CTMNO', '입원청구', '입원고지', '중대질환고지', '중대질환청구'] + _CVR_COLS],
            on='MN_NRDPS_CTMNO', how='right',
        )
    )

    # 가입 가능 상품 목록 (블록 제외)
    merged['gd_list'] = merged.apply(
        lambda r: [
            p for p in type_names.get(r['상품'], [])
            if p not in block_dict.get((r['MN_NRDPS_CTMNO'], r['상품']), set())
        ],
        axis=1,
    )

    # 나이/성별 결측 제거
    merged = merged[merged['CTM_AGE'].notna() & merged['CTM_SEX'].notna()].reset_index(drop=True)

    # 추천 상품명
    merged['pred_gdnm'] = merged.apply(
        lambda r: gd_filter_func(r['상품'], r['CTM_AGE'], r['CTM_SEX'], r), axis=1
    )

    # gd_list 없는 행 제거 후 상위 3개 선택
    merged = merged[merged['gd_list'].map(len) > 0].reset_index(drop=True)
    merged['RANK'] = (
        merged.groupby('CRT_CTMNO')['확률']
        .rank(method='first', ascending=False)
        .astype(int)
    )
    merged = merged[merged['RANK'] <= 3].reset_index(drop=True)

    # GDCD 매핑
    gdcd_dict = df_gd.groupby('GDNM_CLEAN')['GDCD'].apply(list).to_dict()
    merged['상품코드'] = merged['pred_gdnm'].map(
        lambda prod: random.choice(gdcd_dict[prod]) if prod and prod in gdcd_dict else None
    )

    return merged, df_gd


# ── Step 5: 스크립트 생성 ─────────────────────────────────────────────────────

def step_scripts(merged: pd.DataFrame) -> pd.DataFrame:
    script_dict = load_script_dict()
    merged['script']     = merged['pred_gdnm'].map(lambda x: script_dict.get(x, ''))
    merged['cus_script'] = merged.apply(cus_script_func, axis=1)
    merged['fin_script'] = merged['script'] + ' ' + merged['cus_script']
    return merged


# ── Step 6: 최종 테이블 생성 및 Oracle 적재 ──────────────────────────────────

def step_insert(merged: pd.DataFrame, df_gd: pd.DataFrame, conn) -> None:
    rec = (
        merged[['MN_NRDPS_CTMNO', '상품코드', 'pred_gdnm', '확률', 'fin_script', 'RANK']]
        .rename(columns={
            'MN_NRDPS_CTMNO': 'CTMNO',
            '상품코드': 'REC_GDCD',
            'pred_gdnm': 'REC_GDNM',
            '확률': 'REC_POCT',
            'fin_script': 'REC_RS1',
        })
        .drop_duplicates(subset=['CTMNO', 'RANK'], keep='first')
        .dropna()
    )
    rec['RANK'] = rec.groupby('CTMNO')['RANK'].rank(method='first', ascending=True).astype(int)

    # wide pivot (1행 → 3열)
    wide = rec.pivot(index='CTMNO', columns='RANK', values=['REC_GDCD', 'REC_GDNM', 'REC_POCT', 'REC_RS1'])
    wide.columns = [f'추천{rank}_{col}' for col, rank in wide.columns]
    wide = wide.reset_index()

    # CUSTID 조인
    df_custid = pd.read_sql(
        """
        SELECT A.CUSTID, B.CTMNO
        FROM TB_CUSTOMER A
        LEFT JOIN CUS_CTM B ON A.CUST_DSCNO = B.CTM_DSCNO
        WHERE B.CTMNO IN (SELECT DISTINCT CTMNO FROM GDREC_ORIGIN_INS_PRMCNT_PRED)
        """,
        con=conn,
    )
    wide = wide.merge(df_custid[['CTMNO', 'CUSTID']], on='CTMNO', how='inner')

    # 메타 컬럼
    wide['REC_CD']   = '01'
    wide['AP_SEQ']   = '1'
    wide['AP_STRDT'] = datetime.now()
    wide['AP_NDDT']  = datetime(9999, 12, 31)
    wide['FIN_YN']   = '1'

    cols = ['CTMNO', 'REC_CD', 'REC_RANK', 'AP_SEQ', 'AP_STRDT', 'AP_NDDT',
            'REC_GDCD', 'REC_GDNM', 'REC_POCT', 'REC_RS1', 'CUSTID', 'FIN_YN']

    frames = []
    for rank in (1, 2, 3):
        tmp = wide[['CTMNO', 'REC_CD', 'AP_SEQ', 'AP_STRDT', 'AP_NDDT',
                    f'추천{rank}_REC_GDCD', f'추천{rank}_REC_GDNM',
                    f'추천{rank}_REC_POCT', f'추천{rank}_REC_RS1',
                    'CUSTID', 'FIN_YN']].copy()
        tmp.insert(2, 'REC_RANK', rank)
        tmp.columns = cols
        frames.append(tmp)

    df_fin = pd.concat(frames, ignore_index=True).dropna()
    df_fin = df_fin[cols]

    recreate_and_insert(
        conn, 'M_CRM_REC_RLT_BIZ', _REC_RLT_DDL,
        df_fin, _REC_RLT_INSERT, grant_public=True,
    )


# ── 메인 실행 ─────────────────────────────────────────────────────────────────

def run():
    conn = connect()

    print('=== Step 1: 학습 데이터 생성 ===')
    step_data_generation(conn)

    print('\n=== Step 2: 예측 데이터 로딩 ===')
    df = step_load_predict_data(conn)
    print(f'  로딩 완료: {len(df):,}건')

    print('\n=== Step 3: 모델 예측 ===')
    df_scores = step_predict(df)

    print('\n=== Step 4: 필터링 + 상품명 결정 ===')
    merged, df_gd = step_filter_and_name(df, df_scores, conn)

    print('\n=== Step 5: 스크립트 생성 ===')
    merged = step_scripts(merged)

    print('\n=== Step 6: 결과 적재 ===')
    step_insert(merged, df_gd, conn)

    conn.close()
    print('\n=== 완료 ===')


if __name__ == '__main__':
    run()
