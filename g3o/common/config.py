"""Centralized configuration for the G3O pipeline.

Reads from environment variables (with optional .env support via python-dotenv).
Defaults are chosen so that running without a configured .env produces sensible
behavior in development and in CI: search calls return mock data, scrape calls
work against any reachable URL.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    val = os.getenv(key, default)
    if required and val is None:
        raise ValueError(f"Missing required environment variable: {key}")
    return val


SERPER_API_KEY: str | None = _env("SERPER_API_KEY")
SERPER_ENDPOINT: str = _env("SERPER_ENDPOINT", "https://google.serper.dev/search") or ""

OPENAI_API_KEY: str | None = _env("OPENAI_API_KEY")
# Pipeline-wide default model id for every LLM stage. Wired into
# ``batch_client.DEFAULT_MODEL`` (review F9, 2026-06-10), so setting
# ``OPENAI_MODEL`` in the environment / .env overrides the default everywhere;
# the per-invocation ``--model`` CLI flag overrides this in turn.
OPENAI_MODEL: str = _env("OPENAI_MODEL", "gpt-5-nano") or "gpt-5-nano"

REQUEST_TIMEOUT: int = int(_env("REQUEST_TIMEOUT", "30") or "30")
USER_AGENT: str = _env("USER_AGENT", "G3O-Observatory/0.1") or "G3O-Observatory/0.1"

LOG_LEVEL: str = _env("LOG_LEVEL", "INFO") or "INFO"

BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
CACHE_DIR: Path = Path(_env("G3O_CACHE_DIR", str(BASE_DIR / "cache")) or str(BASE_DIR / "cache"))
RUNS_DIR: Path = Path(_env("G3O_RUNS_DIR", str(BASE_DIR / "runs")) or str(BASE_DIR / "runs"))

# Cost circuit breaker: abort the pipeline if projected spend exceeds this limit.
# Read from G3O_BUDGET_LIMIT_USD environment variable. None means no limit is set.
BUDGET_LIMIT_USD: float | None = (
    float(_env("G3O_BUDGET_LIMIT_USD")) if _env("G3O_BUDGET_LIMIT_USD") else None
)
