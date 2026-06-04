import re
import random
import pandas as pd

# ── 상품 스크립트: 상품명 → 보여줄 담보 필드 목록 ─────────────────────────────
# (컬럼명, 한글명, 제수, 단위)
_FIELD_META = {
    'CANCR_DASCS_AMT':            ('암진단비',         10_000,     '만원'),
    'ISMC_HEART_DSAS_DASCS_AMT':  ('허혈성진단비',      10_000,     '만원'),
    'CRLR_DSAS_DASCS_AMT':        ('뇌혈관질환진단비',  10_000,     '만원'),
    'FIRE_PNLTY_AMT':             ('화재벌금',          10_000,     '만원'),
    'USLLF_LBTRS_AMT':            ('일상생활배상책임',   100_000_000, '억원'),
    'SERI_DEMEN_AMT':             ('중증치매',          10_000,     '만원'),
    'LTRM_RCPR_DGN_RANK4_AMT':    ('장기요양진단4급',   10_000,     '만원'),
    'BDIN_CCA_SUAMT_AMT':         ('대인형사',          100_000_000, '억원'),
    'LWR_SNRT_CS_AMT':            ('변호사선임',         10_000,     '만원'),
    'DRV_PNLTY_AMT':              ('운전자벌금',         10_000,     '만원'),
    'DSAS_HSP_RLPMI_AMT':         ('질병입원실손',       10_000,     '만원'),
    'DSAS_OTP_RLPMI_AMT':         ('질병통원실손',       10_000,     '만원'),
}

_CANCER3    = ['CANCR_DASCS_AMT', 'ISMC_HEART_DSAS_DASCS_AMT', 'CRLR_DSAS_DASCS_AMT']
_CANCER2    = ['CANCR_DASCS_AMT', 'ISMC_HEART_DSAS_DASCS_AMT']
_CARE       = ['SERI_DEMEN_AMT', 'LTRM_RCPR_DGN_RANK4_AMT']
_DRIVER     = ['BDIN_CCA_SUAMT_AMT', 'LWR_SNRT_CS_AMT', 'DRV_PNLTY_AMT']
_LOSS       = ['DSAS_HSP_RLPMI_AMT', 'DSAS_OTP_RLPMI_AMT']

PRODUCT_SCRIPT_FIELDS: dict[str, list[str]] = {
    '성공하는 Owner 재산종합보험':      ['FIRE_PNLTY_AMT'],
    '한화 100세 암치료보장보험':         ['CANCR_DASCS_AMT'],
    '한화 311 간편건강보험':             _CANCER3,
    '한화 3N5 더간편건강보험':           _CANCER2,
    '한화 Big Plus 재산종합보험':        ['FIRE_PNLTY_AMT', 'USLLF_LBTRS_AMT'],
    '한화 NEW RICH 간병보험':            _CARE,
    '한화 프리미엄 RICH 간병보험':       _CARE,
    '한화 치매간병보험':                 _CARE,
    '한화 건강쑥쑥 어린이보험':          _CANCER3,
    '한화 굿밸런스종합보험':             _CANCER2,
    '한화 더 경증 간편건강보험':         _CANCER3,
    '한화 더 경증 간편건강보험Ⅱ':       _CANCER3,
    '한화 더건강한 1040 종합보험':       _CANCER3,
    '한화 더건강한 한아름종합보험':      _CANCER3,
    '한화 시그니처 여성 간편건강보험4.0': _CANCER3,
    '한화 시그니처 여성 건강보험4.0':    _CANCER3,
    '한화 운전자상해보험':               _DRIVER,
    '한화간편실손의료보험':              _LOSS,
    '한화실손의료보험':                  _LOSS,
}


# ── 상품명 클렌징 ─────────────────────────────────────────────────────────────

_CLEAN_KEYWORDS = [
    '무배당', '무배', '순수보장형',
    '2504','2508','2507','2510','2511','2512','2509',
    '2601','2602','2603','2604','2605','2606','2607','2608','2609','2610','2611','2612',
]

def clean_product_name(name: str) -> str:
    if pd.isna(name):
        return ''
    name = re.sub(r'\([^)]*\)', '', name)
    for kw in _CLEAN_KEYWORDS:
        name = name.replace(kw, '')
    return name.strip()


# ── 필터 데이터 로딩 ──────────────────────────────────────────────────────────

def load_filter_data(conn) -> dict:
    df_filter1 = pd.read_sql(
        "SELECT CTMNO, GDCD FROM GDREC_CTM_FILTER_1 WHERE CTMNO IS NOT NULL",
        con=conn,
    )

    df_f2 = pd.read_sql(
        "SELECT CTMNO, GDCD, CV_CNT2 / CV_CNT AS RATIO FROM GDREC_CTM_FILTER_2",
        con=conn,
    )
    df_filter2  = df_f2.loc[df_f2['RATIO'] >= 0.4, ['CTMNO', 'GDCD']]
    df_penalty  = df_f2.loc[df_f2['RATIO'] <  0.4, ['CTMNO', 'GDCD', 'RATIO']].reset_index(drop=True)

    df_gd = pd.read_sql(
        "SELECT * FROM GDREC_TMGD_LIST "
        "WHERE GDCD IN (SELECT GDCD FROM TB_LNG_BJONG_MASTER WHERE SALE_END_YN = 'Y')",
        con=conn,
    )
    df_gd['GDNM_CLEAN'] = df_gd['GDNM'].apply(clean_product_name)

    df_filter = (
        pd.concat([df_filter1, df_filter2], ignore_index=True)
        .merge(df_gd[['GDCD', 'GD_TYPE', 'GDNM_CLEAN']], on='GDCD', how='left')
        .rename(columns={'CTMNO': 'MN_NRDPS_CTMNO', 'GD_TYPE': 'product'})
    )
    block_dict = df_filter.groupby(['MN_NRDPS_CTMNO', 'product'])['GDNM_CLEAN'].apply(set).to_dict()

    return {
        'df_gd':          df_gd,
        'df_penalty':     df_penalty,
        'type_to_gdcds':  df_gd.groupby('GD_TYPE')['GDCD'].apply(list).to_dict(),
        'type_to_names':  df_gd.groupby('GD_TYPE')['GDNM_CLEAN'].apply(lambda x: list(set(x))).to_dict(),
        'block_dict':     block_dict,
    }


# ── 추천 상품명 결정 ──────────────────────────────────────────────────────────

def gd_filter_func(product: str, age: int, sex: str, row) -> str | None:
    if product == 'L01':
        if sex == '1.M':
            if age >= 60:   return '한화 굿밸런스종합보험'
            elif age >= 40: return '한화 더건강한 한아름종합보험'
            else:           return '한화 더건강한 1040 종합보험'
        else:  # '2.F'
            if age >= 20:   return '한화 시그니처 여성 건강보험4.0'
            else:           return '한화 더건강한 1040 종합보험'

    elif product == 'L04':
        return '한화 더건강한 1040 종합보험' if age >= 15 else '한화 건강쑥쑥 어린이보험'

    elif product == 'L03':
        return '한화 운전자상해보험'

    elif product == '유병자':
        si_min = int(
            row[['입원청구', '입원고지', '중대질환고지', '중대질환청구']]
            .replace('X', 99).astype(float).min()
        )
        if si_min in (0, 99):
            return random.choice(['한화 3N5 더간편건강보험', '한화 더 경증 간편건강보험Ⅱ'])
        elif si_min < 3:
            return '한화 311 간편건강보험'
        elif si_min > 5:
            return '한화 더 경증 간편건강보험Ⅱ'
        elif sex == '1.M':
            return '한화 3N5 더간편건강보험'
        else:
            return '한화 시그니처 여성 간편건강보험4.0'

    elif product == 'SS':
        return '한화간편실손의료보험' if age >= 50 else '한화실손의료보험'

    else:
        gd_list = row.get('gd_list', [])
        return random.choice(gd_list) if gd_list else None


# ── 고객별 담보 현황 스크립트 생성 ───────────────────────────────────────────

def cus_script_func(row) -> str:
    fields = PRODUCT_SCRIPT_FIELDS.get(row['pred_gdnm'], [])
    if not fields:
        return ''
    parts = []
    for col in fields:
        label, divisor, unit = _FIELD_META[col]
        value = round(row[col] / divisor, 1)
        value = int(value) if value == int(value) else value
        parts.append(f'{label} {value}{unit}')
    return f'현재 고객은 {", ".join(parts)} 가입했습니다.'


# ── 상품별 상위25% 기준 스크립트 사전 ────────────────────────────────────────

_SCRIPT_DICT: dict[str, str] = {
    '성공하는 Owner 재산종합보험':      '해당 상품 가입 상위 25% 고객은 화재벌금 2000만원 수준으로 가입하며',
    '한화 100세 암치료보장보험':         '해당 상품 가입 상위 25% 고객은 암진단비 450만원 수준으로 가입하며',
    '한화 311 간편건강보험':             '해당 상품 가입 상위 25% 고객은 암진단비 250만원, 허혈성진단비 100만원, 뇌혈관질환진단비 100만원 수준으로 가입하며',
    '한화 3N5 더간편건강보험':           '해당 상품 가입 상위 25% 고객은 암진단비 100만원, 허혈성진단비 150만원 수준으로 가입하며',
    '한화 Big Plus 재산종합보험':        '해당 상품 가입 상위 25% 고객은 화재벌금 2000만원, 일상생활배상책임 1억 수준으로 가입하며',
    '한화 NEW RICH 간병보험':            '해당 상품 가입 상위 25% 고객은 중증치매 25만원, 장기요양진단4급 550만원 수준으로 가입하며',
    '한화 프리미엄 RICH 간병보험':       '해당 상품 가입 상위 25% 고객은 중증치매 25만원, 장기요양진단4급 550만원 수준으로 가입하며',
    '한화 치매간병보험':                 '해당 상품 가입 상위 25% 고객은 중증치매 25만원, 장기요양진단4급 550만원 수준으로 가입하며',
    '한화 건강쑥쑥 어린이보험':          '해당 상품 가입 상위 25% 고객은 암진단비 100만원, 허혈성진단비 500만원, 뇌혈관질환진단비 500만원 수준으로 가입하며',
    '한화 굿밸런스종합보험':             '해당 상품 가입 상위 25% 고객은 암진단비 132.5만원, 허혈성진단비 62.5만원 수준으로 가입하며',
    '한화 더 경증 간편건강보험':         '해당 상품 가입 상위 25% 고객은 암진단비 100만원, 허혈성진단비 350만원, 뇌혈관질환진단비 250만원 수준으로 가입하며',
    '한화 더 경증 간편건강보험Ⅱ':       '해당 상품 가입 상위 25% 고객은 암진단비 100만원, 허혈성진단비 350만원, 뇌혈관질환진단비 250만원 수준으로 가입하며',
    '한화 더건강한 1040 종합보험':       '해당 상품 가입 상위 25% 고객은 암진단비 100만원, 허혈성진단비 500만원, 뇌혈관질환진단비 500만원 수준으로 가입하며',
    '한화 더건강한 한아름종합보험':      '해당 상품 가입 상위 25% 고객은 암진단비 100만원, 허혈성진단비 500만원, 뇌혈관질환진단비 500만원 수준으로 가입하며',
    '한화 시그니처 여성 간편건강보험4.0': '해당 상품 가입 상위 25% 고객은 암진단비 250만원, 허혈성진단비 250만원, 뇌혈관질환진단비 250만원 수준으로 가입하며',
    '한화 시그니처 여성 건강보험4.0':    '해당 상품 가입 상위 25% 고객은 암진단비 250만원, 허혈성진단비 1000만원, 뇌혈관질환진단비 500만원 수준으로 가입하며',
    '한화 운전자상해보험':               '해당 상품 가입 상위 25% 고객은 대인형사 2억, 변호사선임 5000만원, 운전자벌금 3000만원 수준으로 가입하며',
    '한화간편실손의료보험':              '해당 상품 가입 상위 25% 고객은 질병입원실손 5000만원, 질병통원실손 20만원 수준으로 가입하며',
    '한화실손의료보험':                  '해당 상품 가입 상위 25% 고객은 질병입원실손 5000만원, 질병통원실손 20만원 수준으로 가입하며',
}


def load_script_dict() -> dict[str, str]:
    return _SCRIPT_DICT
