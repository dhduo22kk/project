"""
Pipeline C: Oracle AI_* → DuckDB 마트 갱신

실행 전 조건:
  1. 레거시 배치 완료 (M_CRM_REC_RLT_BIZ, GDREC_CTM_FILTER_1/2 최신)
  2. Oracle에서 oracle_queries.sql 실행 완료 (AI_* 테이블 생성)

실행:
  python pipelines/pipeline_c_duckdb.py

갱신 방식: mart_new.db에 전체 적재 → atomic rename → mart.db 교체
장애 복구: 시작 시 mart_new.db 존재하면 무조건 삭제 후 재시작
"""

import sys
import shutil
import logging
from pathlib import Path
from datetime import datetime

import cx_Oracle
import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    ORA_HOST, ORA_PORT, ORA_SERVICE, ORA_USER, ORA_PASSWORD,
    DUCKDB_PATH, DUCKDB_NEW_PATH,
)
from db.oracle_queries import QUERIES
from db.manager import atomic_replace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"
CHUNK_SIZE  = 50_000  # Oracle fetchmany 청크 크기


def get_oracle_conn():
    dsn = cx_Oracle.makedsn(ORA_HOST, ORA_PORT, service_name=ORA_SERVICE)
    return cx_Oracle.connect(ORA_USER, ORA_PASSWORD, dsn)


def init_new_db() -> duckdb.DuckDBPyConnection:
    """mart_new.db 초기화 (기존 파일 삭제 후 스키마 적용)."""
    DUCKDB_NEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DUCKDB_NEW_PATH.exists():
        DUCKDB_NEW_PATH.unlink()
        log.warning("기존 mart_new.db 삭제 후 재시작")

    conn = duckdb.connect(str(DUCKDB_NEW_PATH))
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def load_table(ora_conn, duck_conn, table_name: str, query: str) -> int:
    """Oracle 쿼리 결과를 DuckDB 테이블에 청크 단위로 적재. 적재 행 수 반환."""
    cursor = ora_conn.cursor()
    cursor.execute(query)
    columns = [col[0] for col in cursor.description]

    total = 0
    while True:
        rows = cursor.fetchmany(CHUNK_SIZE)
        if not rows:
            break
        df = pd.DataFrame(rows, columns=columns)
        duck_conn.execute(
            f"INSERT INTO {table_name} SELECT * FROM df"
        )
        total += len(df)

    cursor.close()
    return total


def run():
    start = datetime.now()
    log.info("=== Pipeline C 시작 ===")

    ora_conn  = get_oracle_conn()
    duck_conn = init_new_db()

    try:
        for table_name, query in QUERIES.items():
            if query is None:
                log.info(f"  SKIP  {table_name} (쿼리 미작성)")
                continue

            log.info(f"  LOAD  {table_name} ...")
            t0 = datetime.now()
            count = load_table(ora_conn, duck_conn, table_name, query)
            elapsed = (datetime.now() - t0).total_seconds()
            log.info(f"        {count:,}행  ({elapsed:.1f}s)")

        duck_conn.close()
        atomic_replace(DUCKDB_NEW_PATH, DUCKDB_PATH)
        log.info(f"mart.db 교체 완료")

    except Exception as e:
        duck_conn.close()
        if DUCKDB_NEW_PATH.exists():
            DUCKDB_NEW_PATH.unlink()
        log.error(f"적재 실패: {e}")
        raise

    finally:
        ora_conn.close()

    elapsed_total = (datetime.now() - start).total_seconds()
    log.info(f"=== Pipeline C 완료 ({elapsed_total:.0f}s) ===")


if __name__ == "__main__":
    run()
