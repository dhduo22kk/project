import os
import shutil
import duckdb
import pandas as pd
from pathlib import Path
from contextlib import contextmanager

from config.settings import DUCKDB_PATH, DUCKDB_NEW_PATH

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _ensure_dirs():
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_db(db_path: Path = DUCKDB_PATH):
    """스키마 적용. 서비스 시작 시 1회 호출."""
    _ensure_dirs()
    conn = duckdb.connect(str(db_path))
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.close()


@contextmanager
def get_conn(db_path: Path = DUCKDB_PATH):
    """읽기 전용 연결 컨텍스트 매니저."""
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_write_conn(db_path: Path = DUCKDB_PATH):
    """쓰기 연결 컨텍스트 매니저 (pipeline_c 적재용)."""
    conn = duckdb.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()


def query_df(sql: str, params: list = None, db_path: Path = DUCKDB_PATH) -> pd.DataFrame:
    """SQL 실행 후 DataFrame 반환. 에이전트 전 범위에서 사용."""
    with get_conn(db_path) as conn:
        if params:
            return conn.execute(sql, params).fetchdf()
        return conn.execute(sql).fetchdf()


def query_one(sql: str, params: list = None, db_path: Path = DUCKDB_PATH):
    """단일 행 반환. 없으면 None."""
    with get_conn(db_path) as conn:
        result = conn.execute(sql, params or []).fetchone()
        return result


def atomic_replace(new_db_path: Path = DUCKDB_NEW_PATH, target_path: Path = DUCKDB_PATH):
    """mart_new.db → mart.db 원자적 교체. 갱신 완료 후 호출."""
    shutil.move(str(new_db_path), str(target_path))
