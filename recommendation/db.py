import cx_Oracle as orcl
import pandas as pd
from config import ORA_HOST, ORA_PORT, ORA_SID, ORA_USER, ORA_PWD


def connect() -> orcl.Connection:
    dsn = orcl.makedsn(ORA_HOST, ORA_PORT, sid=ORA_SID)
    return orcl.connect(ORA_USER, ORA_PWD, dsn=dsn)


def run_sql_file(conn: orcl.Connection, path) -> None:
    """SQL 파일을 ';' 구분으로 분할하여 순차 실행. DROP 실패는 무시."""
    with open(path, 'r', encoding='utf-8') as f:
        statements = [s.strip() for s in f.read().split(';') if s.strip()]

    with conn.cursor() as cur:
        for sql in statements:
            ddl = sql.split()[0].upper()
            if ddl == 'DROP':
                try:
                    cur.execute(sql)
                except Exception:
                    pass
            elif ddl in ('CREATE', 'INSERT', 'GRANT'):
                cur.execute(sql)
            else:
                continue
            conn.commit()
            tbl = sql.split()[2] if len(sql.split()) > 2 else ''
            print(f'[{ddl}] {tbl}')


def recreate_and_insert(
    conn: orcl.Connection,
    table: str,
    create_ddl: str,
    df: pd.DataFrame,
    insert_sql: str,
    grant_public: bool = False,
) -> None:
    """테이블을 DROP-CREATE 후 executemany로 일괄 INSERT."""
    with conn.cursor() as cur:
        try:
            cur.execute(f'DROP TABLE {table} PURGE')
        except Exception:
            pass
        cur.execute(create_ddl)
        rows = [tuple(row) for row in df.itertuples(index=False, name=None)]
        cur.executemany(insert_sql, rows)
        if grant_public:
            cur.execute(f'GRANT SELECT ON SDADAM.{table} TO PUBLIC')
        conn.commit()
    print(f'[{table}] {len(df)}건 적재')
