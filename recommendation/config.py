from pathlib import Path

# Oracle
ORA_HOST = '10.1.4.166'
ORA_PORT = 1621
ORA_SID  = 'HWEDWP3'
ORA_USER = 'SDADAM'
ORA_PWD  = 'SDADAM!2022'

# Paths
BASE_DIR  = Path('/notebooks/datajeonpart/상품추천시스템_V2')
MODEL_DIR = BASE_DIR / 'AutogluonModels'
VAR_CONFIG = BASE_DIR / 'variables_config.json'

SQL_FILES = [
    BASE_DIR / 'query' / '가입상품생성쿼리.txt',
    BASE_DIR / 'query' / '필터링조건쿼리.txt',
    BASE_DIR / 'query' / '추천상품예측모델_학습데이터생성.txt',
    BASE_DIR / 'query' / '상품가입현황통계.txt',
]

# Model
PRODUCT_CODES      = ['L01', 'L03', 'L04', 'L06', 'L08', 'SS', 'SI', 'L11']
PREDICTOR_PREFIXES = ['predictor', 'predictor2', 'predictor3']

# L03는 점수 없이 rule-base로만 추천 (gd_filter_func 직접 반환)
ZERO_SCORE_CODES = ['L03']
