import os
import numpy as np
import pandas as pd
from autogluon.tabular import TabularPredictor
from config import MODEL_DIR, PRODUCT_CODES, PREDICTOR_PREFIXES, ZERO_SCORE_CODES


def load_models() -> dict:
    """BASE_DIR/AutogluonModels/{prefix}_{code}.txt 경로 파일에서 모델 경로를 읽어 로딩."""
    predictors = {}
    for prefix in PREDICTOR_PREFIXES:
        for code in PRODUCT_CODES:
            path_file = MODEL_DIR / f'{prefix}_{code}.txt'
            if not path_file.exists():
                continue
            model_path = path_file.read_text(encoding='utf-8').strip()
            try:
                predictors[(prefix, code)] = TabularPredictor.load(model_path)
            except Exception as e:
                print(f'[WARN] 모델 로딩 실패 {prefix}_{code}: {e}')
    return predictors


def predict_scores(
    df: pd.DataFrame,
    predictors: dict,
    cvr_vars: list[str],
    ins_vars: list[str],
    other_vars: list[str],
) -> pd.DataFrame:
    """각 상품 코드별 예측 확률을 계산하여 DataFrame으로 반환."""
    data_dict = {
        'predictor':  df[cvr_vars],
        'predictor2': df[ins_vars],
        'predictor3': df[other_vars],
    }

    scores = {}
    for code in PRODUCT_CODES:
        if code in ZERO_SCORE_CODES:
            n = len(df)
            scores[code] = np.zeros(n)
            continue

        probs = []
        for prefix in PREDICTOR_PREFIXES:
            model = predictors.get((prefix, code))
            if model is None:
                continue
            probs.append(model.predict_proba(data_dict[prefix])[1].values)

        scores[code] = np.mean(probs, axis=0) if probs else np.zeros(len(df))

    return pd.DataFrame(scores)
