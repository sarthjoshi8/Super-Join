"""Application configuration — loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR.parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_DIR = DATA_DIR / "db"

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

# ── Database ───────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{DB_DIR / 'fact_layer.db'}",
)

# ── ChromaDB ───────────────────────────────────────────────────────────
CHROMA_PERSIST_DIR = str(DB_DIR / "chroma")

# ── Gemini ─────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

# ── Processing ─────────────────────────────────────────────────────────
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "20000"))
CANDIDATE_TOP_K = int(os.getenv("CANDIDATE_TOP_K", "20"))
# New settings for concurrency and embedding cache
MAX_CONCURRENT_GEMINI = int(os.getenv("MAX_CONCURRENT_GEMINI", "6"))
USE_EMBEDDING_CACHE = os.getenv("USE_EMBEDDING_CACHE", "false").lower() == "true"
