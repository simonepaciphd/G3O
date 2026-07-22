"""Pre-sweep run configuration: stage roster + :class:`PresweepConfig`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from g3o.common.batch_client import DEFAULT_MODEL
from g3o.extract.batch import (
    DEFAULT_TEXT_CAP_CHARS,
    DEFAULT_TEXT_CAP_RULE,
    EMPTY_PAGE_MIN_CHARS,
)
from g3o.scrape.politeness import DEFAULT_HOST_DELAY_SECONDS

STRATIFY_KEYS: tuple[str, ...] = ("country", "government_level", "institution_type")
STAGES: tuple[str, ...] = (
    "discovery_general",
    "classify_official_site",
    "discovery_site_restricted",
    "classify_triage",
    "scrape",
    "extract",
    "validate",
)
StageName = Literal[
    "discovery_general",
    "classify_official_site",
    "discovery_site_restricted",
    "classify_triage",
    "scrape",
    "extract",
    "validate",
]


@dataclass
class PresweepConfig:
    run_id: str
    runs_dir: Path
    master_csv: Path
    sample_size: int = 1000
    seed: int = 22294
    stratification: Literal["equal"] = "equal"  # only equal in Session B
    stratify_keys: tuple[str, ...] = STRATIFY_KEYS
    discovery_languages: tuple[str, ...] = ("en",)
    discovery_results_per_query: int = 5
    dry_run: bool = True
    stop_after: StageName = "extract"
    poll_interval: int = 60
    max_wait_per_stage: int = 25 * 60 * 60  # 25h: SLA + jitter
    model: str = DEFAULT_MODEL
    # Stage 5 page-text handling (Session F.2, 2026-06-10). The cap is the D3
    # methodology decision (60k chars, head+tail); the empty-page floor is an
    # engineering parameter (review F5). Surfaced as config so both are
    # documented and overridable rather than buried as literals.
    extract_text_cap_chars: int = DEFAULT_TEXT_CAP_CHARS
    extract_text_cap_rule: str = DEFAULT_TEXT_CAP_RULE
    empty_page_min_chars: int = EMPTY_PAGE_MIN_CHARS
    # Stage 4 scrape politeness (review F14 / Decision D4, 2026-06-10).
    # ``scrape_respect_robots`` = D4 (respect robots.txt; Disallow'd URLs are
    # skipped and logged to the attrition ledger). ``scrape_host_delay_seconds``
    # is the per-host courtesy delay (robots Crawl-delay raises it per host).
    # ``scrape_render_on_download_failure`` keeps the dead-URL render fallback
    # off by default (review F14): rendering every failed GET is an
    # IP-reputation + wall-clock cost. All three are engineering parameters,
    # not methodology surfaces.
    scrape_respect_robots: bool = True
    scrape_host_delay_seconds: float = DEFAULT_HOST_DELAY_SECONDS
    scrape_render_on_download_failure: bool = False
    # Concurrency (2026-07): shared worker count for Stages 1a/1b/4 (the
    # deterministic, non-LLM stages). Stages 2/3/5/6 are unaffected — their
    # concurrency is the OpenAI Batch API's, not local threads. A single knob
    # rather than per-stage caps until load-testing shows otherwise.
    max_workers: int = 1

    @property
    def institution_search_languages(self) -> str:
        """Stage 5 provenance string — always the languages Stage 1a/1b actually searched.

        Not independently settable (review, 2026-07-20): a free-standing config
        field let this drift from ``discovery_languages``, so the extraction
        contract's ``institution_search_languages`` column could understate what
        was searched. Deriving it removes that failure mode.
        """
        return ",".join(self.discovery_languages)
