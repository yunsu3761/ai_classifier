"""
Core configuration for the TaxoAdapt backend API.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Project root is 3 levels up from this file: web/backend/core/config.py -> ai_classifier/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH, override=False)

# Directories
DATASETS_DIR = PROJECT_ROOT / "datasets"
CONFIGS_DIR = PROJECT_ROOT / "configs"
SAVE_OUTPUT_DIR = PROJECT_ROOT / "save_output"
SAVE_RESULT_DIR = PROJECT_ROOT / "save_result"
USER_DATA_DIR = PROJECT_ROOT / "user_data"
UPLOAD_DIR = PROJECT_ROOT / "web" / "uploads"
CONVERTED_DIR = PROJECT_ROOT / "web" / "converted"  # Converted files

# Ensure directories exist
for d in [DATASETS_DIR, CONFIGS_DIR, SAVE_OUTPUT_DIR, SAVE_RESULT_DIR, UPLOAD_DIR, CONVERTED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-2025-08-07")

# API settings
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

# Concurrency settings
MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "3"))

# Time estimation constants (seconds per document per dimension)
# Based on ~11s per LLM call observed in testing
EST_SECONDS_PER_DOC_TYPE_CLS = 11.0   # type classification
EST_SECONDS_PER_DOC_EXPANSION = 15.0  # BFS expansion per node
