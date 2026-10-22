"""Runtime settings from environment variables. Secrets are never hard-coded."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

BASE = pathlib.Path(__file__).resolve().parents[1]


def _load_dotenv() -> None:
    """Read KEY=VALUE lines from backend/.env or the repo-root .env (first found) into the
    environment, without overriding variables that are already set. No extra dependency."""
    for path in (BASE / ".env", BASE.parent / ".env"):
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip().removeprefix("export ").strip(), val.split(" #")[0].strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        break


if not os.environ.get("DNA_TWIN_SKIP_DOTENV"):
    _load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class Settings:
    data_dir: pathlib.Path = field(default_factory=lambda: pathlib.Path(_env("DATA_DIR", str(BASE / "data"))))
    database_url: str | None = field(default_factory=lambda: _env("DATABASE_URL"))
    qdrant_url: str | None = field(default_factory=lambda: _env("QDRANT_URL"))
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "auto"))  # auto|anthropic|gemini|ollama|extractive
    anthropic_api_key: str | None = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    gemini_api_key: str | None = field(default_factory=lambda: _env("GEMINI_API_KEY") or _env("GOOGLE_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.1"))
    embedding_provider: str = field(default_factory=lambda: _env("EMBEDDING_PROVIDER", "auto"))  # auto|hashing|sentence-transformers|ollama
    st_model: str = field(default_factory=lambda: _env("ST_MODEL", "all-MiniLM-L6-v2"))
    ollama_embed_model: str = field(default_factory=lambda: _env("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    max_upload_mb: float = field(default_factory=lambda: float(_env("MAX_UPLOAD_MB", "2")))
    cors_origins: list[str] = field(default_factory=lambda: (_env("CORS_ORIGINS", "http://localhost:3000") or "").split(","))

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("uploads", "containers", "reads", "recovered", "reports", "benchmarks"):
            (self.data_dir / sub).mkdir(exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'dnatwin.db'}"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
