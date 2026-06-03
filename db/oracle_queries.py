"""
Oracle → DuckDB ETL 쿼리 매핑

실행 순서:
  1. (선행) 레거시 배치 실행 → M_CRM_REC_RLT_BIZ, GDREC_CTM_FILTER_1/2 갱신
  2. (Oracle) db/oracle_queries.sql → AI_* 추출 테이블 생성
  3. (Python) pipeline_c_duckdb.py → AI_* SELECT * → DuckDB 적재

복잡한 추출 로직은 oracle_queries.sql 에서 관리.
여기서는 DuckDB 테이블명 ↔ Oracle AI_* 테이블명 매핑만 관리.
None 항목은 pipeline_c_duckdb.py가 자동 skip.
"""

# DuckDB 테이블명 → Oracle AI_* SELECT 쿼리
QUERIES: dict[str, str | None] = {
    "tbl_ds_customer":         "SELECT * FROM AI_CUSTOMER",
    "tbl_ds_coverage":         "SELECT * FROM AI_COVERAGE",
    "tbl_ds_contract_history": "SELECT * FROM AI_CONTRACT",
    "tbl_ds_design_history":   "SELECT * FROM AI_DESIGN",
    "tbl_ds_new_coverage":     "SELECT * FROM AI_NEW_CVR",
    "tbl_ds_recommendation":   "SELECT * FROM AI_RECOMM",
    "tbl_ds_ineligible":       "SELECT * FROM AI_INELIGIBLE",
    "tbl_ds_product_master":   "SELECT * FROM AI_PRODUCT",
    "tbl_ds_call_detail":      "SELECT * FROM AI_CALL_DETAIL",
    "tbl_ds_campaign_history": "SELECT * FROM AI_CAMPAIGN",
    "tbl_ds_msg_history":      None,   # TODO: AI_MSG_HISTORY 소스 확인 후 추가
}
