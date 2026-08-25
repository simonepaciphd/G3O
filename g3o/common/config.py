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


# --- API keys: DEPRECATED SHIM (Run API spec §3.2, 2026-08-11) -------------
# These two constants resolve their key **at import time**, which is exactly the
# defect §3 removes: a value frozen at first import cannot be a per-call key, so
# two runs in one process could never use two different grants' keys. They are
# kept for one release, still env-populated, for out-of-repo callers only.
#
# Nothing in this repository may read them — resolve keys through
# :func:`g3o.common.credentials.resolve` and pass the resulting
# ``ResolvedCredentials`` down explicitly. ``tests/test_credentials.py``
# greps the package and fails if a consumer reappears here, because a
# re-introduced read would silently re-freeze key resolution at import time.
# Removing these two names is a follow-up PR.
SERPER_API_KEY: str | None = _env("SERPER_API_KEY")
OPENAI_API_KEY: str | None = _env("OPENAI_API_KEY")
# ---------------------------------------------------------------------------

SERPER_ENDPOINT: str = _env("SERPER_ENDPOINT", "https://google.serper.dev/search") or ""
# Pipeline-wide default model id for every LLM stage. Wired into
# ``batch_client.DEFAULT_MODEL`` (review F9, 2026-06-10), so setting
# ``OPENAI_MODEL`` in the environment / .env overrides the default everywhere;
# the per-invocation ``--model`` CLI flag overrides this in turn.
OPENAI_MODEL: str = _env("OPENAI_MODEL", "gpt-5-nano") or "gpt-5-nano"

REQUEST_TIMEOUT: int = int(_env("REQUEST_TIMEOUT", "30") or "30")

# Stage 4 headless-render browser recycling (2026-08-25). Each scrape worker
# thread holds one Chromium for the whole stage (``RenderSession``), so its
# memory grows monotonically with the renders that thread serves. Run
# ``r20260824T215623Z-bb4e`` (n=4,000, ``max_workers 8``) was OOM-killed 69
# minutes into Stage 4 on a 7.9 GB box with no swap: memory climbed 4.2% ->
# 90.7% over 439 renders while the process table grew 402 -> 787. Closing and
# relaunching the browser every N renders bounds that growth at N pages per
# worker instead of the whole stage. Set to 0 to disable recycling.
RENDER_RECYCLE_AFTER: int = int(_env("RENDER_RECYCLE_AFTER", "25") or "25")
USER_AGENT: str = _env("USER_AGENT", "G3O-Observatory/0.1") or "G3O-Observatory/0.1"

LOG_LEVEL: str = _env("LOG_LEVEL", "INFO") or "INFO"

BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
CACHE_DIR: Path = Path(_env("G3O_CACHE_DIR", str(BASE_DIR / "cache")) or str(BASE_DIR / "cache"))
RUNS_DIR: Path = Path(_env("G3O_RUNS_DIR", str(BASE_DIR / "runs")) or str(BASE_DIR / "runs"))

# Cost circuit breaker: abort the pipeline if projected spend exceeds this limit.
# Read from G3O_BUDGET_LIMIT_USD environment variable. Stored as string; parsed
# to float at use time (cli.py) to avoid import-time failures on malformed values.
BUDGET_LIMIT_USD: str | None = _env("G3O_BUDGET_LIMIT_USD")

# Projection safety factor: abort mid-run if projected total spend exceeds
# budget × this factor. There is NO default — unset means the mid-run projection
# abort is DISABLED, not that it runs at 1.2 (_parse_projection_safety_factor
# returns None). It is off by default because the projection scales the two
# classify stages' actual-vs-estimate ratio onto the dominant extract estimate,
# and those stages are not comparable enough for that ratio to kill a live run
# uninvited. Set it, per run, when you want the guard.
# Read from G3O_PROJECTION_SAFETY_FACTOR env var. Stored as string; parsed to
# float at use time (cli.py) with validation.
PROJECTION_SAFETY_FACTOR: str | None = _env("G3O_PROJECTION_SAFETY_FACTOR")

# Cost monitor dry run mode: when True, log warnings instead of aborting when
# budget is exceeded. Read from G3O_COST_MONITOR_DRY_RUN env var. Stored as string;
# parsed to bool at use time (cli.py). Follows the same pattern as PROJECTION_SAFETY_FACTOR.
COST_MONITOR_DRY_RUN: str | None = _env("G3O_COST_MONITOR_DRY_RUN")
