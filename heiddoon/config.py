"""Configuration, from environment or a local `.env`.

Kept deliberately small and in one file: the two things that change constantly
during a build like this are which backend serves the model and what the model is
called there, and both should be changeable without editing code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def load_env_file(path: Path = DEFAULT_ENV_FILE) -> None:
    """Load KEY=value lines, without adding a dependency for it.

    Existing environment variables always win, so an inline
    `GEMMA_API_KEY=… python -m heiddoon.cli` overrides the file.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Settings:
    provider: str = "google"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma4:12b"
    #: Seconds between watcher check-ins. A rhythm of check-ins, not millisecond
    #: policing — and also an honest budget for local inference.
    cadence_s: int = 20
    #: How long a file must be unchanged before we judge the delta.
    artifact_settle_s: int = 5
    db_path: Path = PROJECT_ROOT / "heiddoon.db"
    timeout_s: float = 180.0

    @classmethod
    def from_env(cls, load_file: bool = True) -> Settings:
        if load_file:
            load_env_file()
        env = os.environ
        return cls(
            provider=env.get("HEIDDOON_PROVIDER", "google").strip().lower(),
            model=env.get("HEIDDOON_MODEL", "").strip(),
            api_key=env.get("GEMMA_API_KEY", env.get("GOOGLE_API_KEY", "")).strip(),
            base_url=env.get("HEIDDOON_BASE_URL", "").strip(),
            ollama_host=env.get("HEIDDOON_OLLAMA_HOST", "http://localhost:11434").strip(),
            ollama_model=env.get("HEIDDOON_OLLAMA_MODEL", "gemma4:12b").strip(),
            cadence_s=int(env.get("HEIDDOON_CADENCE_S", "20")),
            artifact_settle_s=int(env.get("HEIDDOON_ARTIFACT_SETTLE_S", "5")),
            db_path=Path(env.get("HEIDDOON_DB", str(PROJECT_ROOT / "heiddoon.db"))),
            timeout_s=float(env.get("HEIDDOON_TIMEOUT_S", "180")),
        )


settings = Settings.from_env()
