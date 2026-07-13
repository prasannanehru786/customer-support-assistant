from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local developer convenience
    load_dotenv = None

if load_dotenv:
    load_dotenv()

APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
LOG_DIR = APP_ROOT / "logs"
KNOWLEDGE_DIR = APP_ROOT / "knowledge"
AUDIO_DIR = APP_ROOT / "audio"
IMAGE_UPLOAD_DIR = DATA_DIR / "uploads"
IMAGE_OUTPUT_DIR = DATA_DIR / "generated_images"
CREWAI_STORAGE_DIR = DATA_DIR / "crewai"
ANSWERS_FILE = Path(os.getenv("ANSWERS_FILE_PATH") or str(APP_ROOT / "answers.txt"))
SQLITE_PATH = DATA_DIR / "app.sqlite"
JSONL_LOG_PATH = LOG_DIR / "app.jsonl"
RAG_INDEX_STATE_PATH = DATA_DIR / "rag_index.json"
GOOGLE_SHEETS_STATE_PATH = DATA_DIR / "google_sheets_state.json"
AUTH_USERS_PATH = DATA_DIR / "auth_users.json"

os.environ.setdefault("CREWAI_STORAGE_DIR", str(CREWAI_STORAGE_DIR))
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
os.environ.setdefault("OPENAI_MODEL_NAME", DEFAULT_MODEL)
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "support_knowledge")
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


def ensure_runtime_dirs() -> None:
    for directory in [
        DATA_DIR,
        TRANSCRIPT_DIR,
        LOG_DIR,
        KNOWLEDGE_DIR,
        AUDIO_DIR,
        IMAGE_UPLOAD_DIR,
        IMAGE_OUTPUT_DIR,
        CREWAI_STORAGE_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
    ANSWERS_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_serpapi_key() -> str | None:
    return os.getenv("SERPAPI_KEY") or os.getenv("SERAPI_KEY")
