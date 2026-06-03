from pathlib import Path
import os

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# DuckDB
DUCKDB_PATH     = DATA_DIR / "duckdb" / "mart.db"
DUCKDB_NEW_PATH = DATA_DIR / "duckdb" / "mart_new.db"
CHECKPOINT_PATH = DATA_DIR / "duckdb" / "checkpoints.sqlite"

# Chroma
CHROMA_PATH = DATA_DIR / "chroma"

# Pipeline 데이터 경로
WAV_DIR  = DATA_DIR / "wav"
DOCS_DIR = DATA_DIR / "docs"

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL       = os.getenv("LLM_MODEL",   "mymodel")
EMBED_MODEL     = os.getenv("EMBED_MODEL", "nomic-embed-text")

# faster-whisper
WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH", "/opt/models/faster-whisper-large-v3")

# Oracle
ORA_HOST     = os.getenv("ORA_HOST",     "")
ORA_PORT     = int(os.getenv("ORA_PORT", "1521"))
ORA_SERVICE  = os.getenv("ORA_SERVICE",  "")
ORA_USER     = os.getenv("ORA_USER",     "")
ORA_PASSWORD = os.getenv("ORA_PASSWORD", "")

# UI
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 7860

# 캠페인 성공 기준: 배정일 기준 +N일 이내 계약 체결
CAMPAIGN_SUCCESS_DAYS = 90

# DuckDB 테이블명 상수
TBL_CUSTOMER          = "tbl_ds_customer"
TBL_COVERAGE          = "tbl_ds_coverage"
TBL_CALL_DETAIL       = "tbl_ds_call_detail"
TBL_CONTRACT_HISTORY  = "tbl_ds_contract_history"
TBL_CAMPAIGN_HISTORY  = "tbl_ds_campaign_history"
TBL_DESIGN_HISTORY    = "tbl_ds_design_history"
TBL_NEW_COVERAGE      = "tbl_ds_new_coverage"
TBL_RECOMMENDATION    = "tbl_ds_recommendation"
TBL_INELIGIBLE        = "tbl_ds_ineligible"
TBL_PRODUCT_MASTER    = "tbl_ds_product_master"
TBL_SALES_FOCUS       = "tbl_ds_sales_focus"
TBL_MSG_HISTORY       = "tbl_ds_msg_history"
