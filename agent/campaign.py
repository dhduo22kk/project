"""
Tab2: 캠페인 추천 대상 생성

get_campaign_list()           → pd.DataFrame  (CAMPAIGN_NM, CAMPAIGN_TYPE)
get_prev_campaign_stats(nm)   → dict           (체결율, 배정수 등)
build_campaign_query(cond)    → str            (DuckDB SQL)
extract_campaign_list(cond)   → pd.DataFrame  (CTMNO 컬럼)
to_excel_tempfile(df)         → str            (임시 파일 경로)

conditions dict 구조:
    campaign_nm    : str
    is_new_campaign: bool
    product_types  : list[str]   # ['건강보험', '암보험', ...]  — 현재 필터 미사용 (상품유형은 레거시 코드에만 있음)
    channel        : list[str]   # ['TM', 'CM', ...]
    gender         : str | None  # '1.M' | '2.F' | None
    age_range      : tuple[int,int] | None
    target_count   : int
    strategy       : str         # 'past_performance' | 'activity_based'
"""
import sys
import logging
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config.settings import (
    TBL_CUSTOMER, TBL_CAMPAIGN_HISTORY, TBL_CALL_DETAIL,
    TBL_CONTACT_EXCLUSION, TBL_CMPG_RESULT, TBL_INELIGIBLE,
    CAMPAIGN_SUCCESS_DAYS,
)
from db.manager import query_df, query_one

log = logging.getLogger(__name__)

AGE_RANGE_MAP = {
    "20대": (20, 29),
    "30대": (30, 39),
    "40대": (40, 49),
    "50대": (50, 59),
    "60대+": (60, 99),
}


def parse_age_ranges(age_chips: list[str]) -> tuple[int, int] | None:
    if not age_chips:
        return None
    mins, maxs = [], []
    for chip in age_chips:
        r = AGE_RANGE_MAP.get(chip)
        if r:
            mins.append(r[0])
            maxs.append(r[1])
    if not mins:
        return None
    return (min(mins), max(maxs))


# ── 캠페인 목록 ───────────────────────────────────────────────────────────────

def get_campaign_list() -> pd.DataFrame:
    """DISTINCT 캠페인명 + 채널. 캠페인 리스트 패널용."""
    try:
        return query_df(
            f"""
            SELECT CAMPAIGN_NM, CAMPAIGN_TYPE,
                   COUNT(*) AS assign_cnt
            FROM {TBL_CAMPAIGN_HISTORY}
            WHERE CAMPAIGN_NM IS NOT NULL
            GROUP BY CAMPAIGN_NM, CAMPAIGN_TYPE
            ORDER BY MAX(ASSIGN_DT) DESC
            """
        )
    except Exception as e:
        log.warning(f"캠페인 목록 조회 실패: {e}")
        return pd.DataFrame(columns=["CAMPAIGN_NM", "CAMPAIGN_TYPE", "assign_cnt"])


# ── 직전 캠페인 통계 ──────────────────────────────────────────────────────────

def get_prev_campaign_stats(campaign_nm: str) -> dict:
    """Step 4 직전 캠페인 비교 카드용. 이력 없으면 빈 dict."""
    try:
        row = query_one(
            f"""
            SELECT
                COUNT(*)                                        AS total,
                SUM(CONTRACT_YN)                               AS success,
                ROUND(AVG(CONTRACT_YN) * 100, 1)              AS success_rate,
                ROUND(AVG(CASE WHEN CONTRACT_YN = 1 THEN CONTRACT_PRM END), 0) AS avg_prm
            FROM {TBL_CMPG_RESULT}
            WHERE CAMPAIGN_NM = ?
            """,
            [campaign_nm],
        )
        if row is None or row[0] == 0:
            return {}
        return {
            "total":        int(row[0]),
            "success":      int(row[1] or 0),
            "success_rate": float(row[2] or 0),
            "avg_prm":      int(row[3] or 0),
        }
    except Exception as e:
        log.debug(f"과거 캠페인 통계 조회 실패: {e}")
        return {}


def has_past_performance_data(campaign_nm: str) -> bool:
    try:
        row = query_one(
            f"SELECT COUNT(*) FROM {TBL_CMPG_RESULT} WHERE CAMPAIGN_NM = ? AND CONTRACT_YN = 1",
            [campaign_nm],
        )
        return bool(row and row[0] > 0)
    except Exception:
        return False


def has_activity_data() -> bool:
    try:
        row = query_one(f"SELECT COUNT(*) FROM {TBL_CALL_DETAIL} LIMIT 1")
        return bool(row and row[0] > 0)
    except Exception:
        return False


# ── 쿼리 빌더 ─────────────────────────────────────────────────────────────────

def _base_where(conditions: dict, alias: str = "c") -> str:
    """공통 필터: 연락불가 제외 + 최근 동일 캠페인 배정 제외 + 인구통계."""
    campaign_nm = conditions.get("campaign_nm", "").replace("'", "''")
    gender      = conditions.get("gender")
    age_range   = conditions.get("age_range")

    clauses = [
        f"{alias}.CTMNO NOT IN (SELECT CTMNO FROM {TBL_CONTACT_EXCLUSION})",
        f"""{alias}.CTMNO NOT IN (
            SELECT CTMNO FROM {TBL_CAMPAIGN_HISTORY}
            WHERE CAMPAIGN_NM = '{campaign_nm}'
              AND ASSIGN_DT >= CURRENT_DATE - INTERVAL '{CAMPAIGN_SUCCESS_DAYS} days'
        )""",
    ]

    if gender:
        safe = gender.replace("'", "''")
        clauses.append(f"{alias}.CTM_SEX = '{safe}'")

    if age_range:
        clauses.append(f"{alias}.CTM_AGE BETWEEN {age_range[0]} AND {age_range[1]}")

    return " AND ".join(clauses)


def build_campaign_query(conditions: dict) -> str:
    strategy     = conditions.get("strategy", "activity_based")
    target_count = int(conditions.get("target_count", 1000))
    campaign_nm  = conditions.get("campaign_nm", "").replace("'", "''")
    where        = _base_where(conditions, "c")

    if strategy == "past_performance":
        return f"""
WITH past_success AS (
    SELECT cr.CTMNO, cu.CTM_AGE, cu.CTM_SEX
    FROM {TBL_CMPG_RESULT} cr
    JOIN {TBL_CUSTOMER} cu ON cr.CTMNO = cu.CTMNO
    WHERE cr.CAMPAIGN_NM = '{campaign_nm}'
      AND cr.CONTRACT_YN = 1
),
profile AS (
    SELECT
        CAST(PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY CTM_AGE) AS INTEGER) AS age_min,
        CAST(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY CTM_AGE) AS INTEGER) AS age_max
    FROM past_success
)
SELECT c.CTMNO
FROM {TBL_CUSTOMER} c
CROSS JOIN profile p
WHERE {where}
  AND c.CTM_AGE BETWEEN p.age_min AND p.age_max
  AND c.CTMNO NOT IN (SELECT CTMNO FROM {TBL_INELIGIBLE})
ORDER BY RANDOM()
LIMIT {target_count}
"""
    else:  # activity_based
        return f"""
SELECT c.CTMNO
FROM {TBL_CUSTOMER} c
WHERE {where}
  AND c.CTMNO NOT IN (SELECT CTMNO FROM {TBL_INELIGIBLE})
  AND (
      c.CTMNO IN (
          SELECT CTMNO FROM {TBL_CALL_DETAIL}
          WHERE RESULT_CD = '연결성공'
            AND CALL_DT >= CURRENT_DATE - INTERVAL '6 months'
      )
      OR c.CTMNO IN (
          SELECT CTMNO FROM {TBL_CAMPAIGN_HISTORY}
          WHERE ASSIGN_DT >= CURRENT_DATE - INTERVAL '6 months'
      )
  )
ORDER BY RANDOM()
LIMIT {target_count}
"""


# ── 추출 실행 ─────────────────────────────────────────────────────────────────

def extract_campaign_list(conditions: dict) -> pd.DataFrame:
    sql = build_campaign_query(conditions)
    log.info(f"캠페인 추출 쿼리 실행: strategy={conditions.get('strategy')}, target={conditions.get('target_count')}")
    try:
        return query_df(sql)
    except Exception as e:
        log.error(f"캠페인 추출 실패: {e}")
        raise


def to_excel_tempfile(df: pd.DataFrame) -> str:
    """CTMNO만 포함한 Excel 임시 파일 경로 반환."""
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False, prefix="campaign_list_")
    out = df[["CTMNO"]].copy() if "CTMNO" in df.columns else df
    out.to_excel(tmp.name, index=False)
    tmp.close()
    return tmp.name
