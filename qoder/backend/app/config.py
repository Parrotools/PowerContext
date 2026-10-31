"""Application configuration loaded from environment variables."""

import json
import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # SeekDB — SQLite + sqlite-vec fallback (works without external SeekDB server)
    SEEKDB_DATABASE: str = os.getenv("SEEKDB_DATABASE", "zhixu_learning")
    SEEKDB_DATABASE_PATH: str = os.getenv("SEEKDB_DATABASE_PATH", ".seekdb_data")

    # SeekDB self-hosted (optional — set to use real SeekDB instead of SQLite fallback)
    SEEKDB_HOST: str = os.getenv("SEEKDB_HOST", "127.0.0.1")
    SEEKDB_PORT: int = int(os.getenv("SEEKDB_PORT", "2881"))
    SEEKDB_USER: str = os.getenv("SEEKDB_USER", "root")
    SEEKDB_PASSWORD: str = os.getenv("SEEKDB_PASSWORD", "")

    # PowerContext
    POWERCONTEXT_URL: str = os.getenv("POWERCONTEXT_URL", "http://127.0.0.1:8010")
    POWERCONTEXT_SCOPE_ID: str = os.getenv("POWERCONTEXT_SCOPE_ID", "zhixu-default")

    # LLM
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Chunking
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

    CORS_ORIGINS: list[str] = field(default_factory=lambda: _parse_cors())


def _parse_cors() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return [s.strip() for s in raw.split(",") if s.strip()]
    return [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://*.qoder.site",
    ]


settings = Settings()
