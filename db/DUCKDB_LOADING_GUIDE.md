# DuckDB 적재 가이드

## DuckDB가 뭔가요?

PostgreSQL, MySQL처럼 서버를 띄울 필요가 없습니다.  
SQLite처럼 **파일 하나** (`mart.db`)가 전체 DB입니다.  
Python 코드 안에서 `duckdb.connect("mart.db")` 한 줄로 열립니다.

```
Oracle DB  →  Python (cx_Oracle)  →  pandas DataFrame  →  DuckDB 파일
              SELECT 쿼리 실행        메모리에 올림        mart.db에 저장
```

별도 설치/배포 없음. `pip install duckdb`만 하면 끝.

---

## 전제 조건

서버에 이미 설치되어 있어야 하는 것:
- `cx_Oracle` (기설치 확인됨)
- Oracle Instant Client (서버 기설치 확인 필요)
- `duckdb` → `pip install duckdb` (번들에 포함)
- `pandas` (기설치 확인됨)

---

## 1단계: Oracle 연결 테스트 (Jupyter에서 먼저)

```python
import cx_Oracle
import pandas as pd

# Oracle 접속 정보 (config/settings.py에서 관리)
DSN = cx_Oracle.makedsn("HOST", PORT, service_name="SERVICE_NAME")
conn = cx_Oracle.connect(user="USER", password="PW", dsn=DSN)

# 테스트: 고객 1건 조회
df = pd.read_sql("SELECT * FROM CUS_DS_CTM WHERE ROWNUM <= 5", conn)
print(df)
conn.close()
```

> 접속 안 되면 Oracle Instant Client 경로 확인:  
> `cx_Oracle.init_oracle_client(lib_dir="/path/to/instantclient")`

---

## 2단계: DuckDB 적재 (테이블 1개 테스트)

```python
import os
import duckdb
import cx_Oracle
import pandas as pd

os.makedirs("data/duckdb", exist_ok=True)  # 폴더 없으면 자동 생성

# Oracle에서 데이터 가져오기
ora_conn = cx_Oracle.connect(user="USER", password="PW", dsn=DSN)
df = pd.read_sql("""
    SELECT
        CTMNO,
        CTM_AGE,
        CTM_SEX,
        REGION,
        REG_DT
    FROM CUS_DS_CTM
""", ora_conn)
ora_conn.close()

print(f"조회 완료: {len(df):,}건")

# DuckDB에 저장
duck = duckdb.connect("data/duckdb/mart.db")
duck.execute("DROP TABLE IF EXISTS tbl_customer")
duck.execute("CREATE TABLE tbl_customer AS SELECT * FROM df")
duck.close()

print("DuckDB 적재 완료")
```

---

## 3단계: 전체 테이블 일괄 적재 (터미널)

개발 완료 후 실제 적재는 터미널에서:

```bash
python pipelines/pipeline_c_duckdb.py
```

내부 동작:
1. `mart_new.db` 파일에 모든 테이블 적재
2. 적재 완료 후 `mart_new.db` → `mart.db` rename
3. 에이전트가 읽던 `mart.db`는 rename 완료 후에만 교체됨 (블로킹 없음)

---

## 4단계: 적재 결과 확인

```python
import duckdb

duck = duckdb.connect("data/duckdb/mart.db")

# 테이블 목록
print(duck.execute("SHOW TABLES").fetchdf())

# 행 수 확인
for table in ["tbl_customer", "tbl_coverage", "tbl_call_detail",
              "tbl_contract_history", "tbl_campaign_history",
              "tbl_design_history", "tbl_new_coverage",
              "tbl_recommendation", "tbl_campaign_score"]:
    count = duck.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}: {count:,}건")

duck.close()
```

---

## 개발 순서 권장

> **컨테이너 구조 주의**: Jupyter 컨테이너와 LLM(VS Code) 컨테이너는 파일시스템이 분리됨.
> DuckDB 파일은 **LLM 컨테이너에서만** 생성·관리. Jupyter는 Oracle 쿼리 검증 전용.

| 단계 | 실행 위치 | 목적 |
|------|---------|------|
| Oracle 접속 확인, 컬럼명·행수 확인 | **Jupyter** | 쿼리 초안 작성 |
| 검증된 쿼리 → oracle_queries.py 붙여넣기 | **LLM 컨테이너** | 코드에 반영 |
| pipeline_c_duckdb.py 실행 | **LLM 컨테이너 터미널** | mart.db 생성 |
| 초기 전체 적재 | **LLM 컨테이너 터미널** | 서비스 시작 전 1회 |
| 이후 매일 갱신 | **LLM 컨테이너 cron** | `0 6 * * * python pipelines/pipeline_c_duckdb.py` |

---

## 자주 쓰는 DuckDB 명령

```python
duck = duckdb.connect("data/duckdb/mart.db")

# 특정 고객 조회 (에이전트 동작 테스트용)
duck.execute("SELECT * FROM tbl_customer WHERE CTMNO = '1234567'").fetchdf()

# 캠페인별 통화 건수
duck.execute("""
    SELECT CAMPAIGN_NM, RESULT_CD, COUNT(*) as cnt
    FROM tbl_call_detail
    GROUP BY 1, 2
    ORDER BY 1, 3 DESC
""").fetchdf()

duck.close()
```

---

## 주의사항

- `mart.db`는 **git 제외** (`.gitignore`에 `data/` 추가)
- 30만 건 전체 적재 시 테이블당 수십 초 ~ 수분 소요
- 적재 중 에이전트가 `mart.db`를 읽어도 괜찮음 (rename 패턴 덕분)
- Oracle 접속 정보는 `config/settings.py`에서 환경변수로 관리, 코드에 하드코딩 금지
