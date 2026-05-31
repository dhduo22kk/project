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
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL          = os.getenv("LLM_MODEL",   "mymodel")       # ollama create mymodel -f Modelfile
EMBED_MODEL        = os.getenv("EMBED_MODEL", "nomic-embed-text")

# faster-whisper 모델 가중치 경로 (폐쇄망 서버 로컬)
WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH", "/opt/models/faster-whisper-large-v3")

# Oracle
ORA_HOST     = os.getenv("ORA_HOST",     "")
ORA_PORT     = int(os.getenv("ORA_PORT", "1521"))
ORA_SERVICE  = os.getenv("ORA_SERVICE",  "")
ORA_USER     = os.getenv("ORA_USER",     "")
ORA_PASSWORD = os.getenv("ORA_PASSWORD", "")

# UI
ALLOWED_IPS_FILE = BASE_DIR / "config" / "allowed_ips.txt"
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 7860

# DuckDB 테이블명
TBL_CUSTOMER          = "tbl_ds_customer"
TBL_COVERAGE          = "tbl_ds_coverage"
TBL_CALL_DETAIL       = "tbl_ds_call_detail"
TBL_CONTRACT_HISTORY  = "tbl_ds_contract_history"
TBL_CAMPAIGN_HISTORY  = "tbl_ds_campaign_history"
TBL_DESIGN_HISTORY    = "tbl_ds_design_history"
TBL_NEW_COVERAGE      = "tbl_ds_new_coverage"
TBL_RECOMMENDATION    = "tbl_ds_recommendation"
TBL_CAMPAIGN_SCORE    = "tbl_ds_campaign_score"
TBL_PRODUCT_MASTER    = "tbl_ds_product_master"
