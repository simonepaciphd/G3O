"""Pre-sweep run configuration: stage roster + :class:`PresweepConfig`."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from g3o.common.batch_client import DEFAULT_MODEL
from g3o.discovery.query_builder import (
    DEFAULT_EVIDENCE_TERM,
    DOMAIN_QUERY_LANG,
    EVIDENCE_TERMS_BY_LANG,
    GENAI_TERMS_BY_LANG,
    assert_languages_rostered,
)
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
    "filter_eligibility",
    "classify_triage",
    "scrape",
    "extract",
    "validate",
)
StageName = Literal[
    "discovery_general",
    "classify_official_site",
    "discovery_site_restricted",
    "filter_eligibility",
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
    # 10, not 5: ``num`` truncates and costs a flat 1 credit either way, so at 5
    # the pipeline paid for ten results and discarded half of them. A waste fix
    # with no measured yield effect. Serper returns 9 in practice.
    discovery_results_per_query: int = 10
    # ── Two-query discovery chain (2026-08-01, PI sign-off) ──────────────────
    # ``legacy``: Stage 1a/1b both issue the four-slot GENAI_TERMS_BY_LANG
    #   roster (8 queries each). Reachable, unchanged, and byte-identical to
    #   pre-2026-08-01 when ``serper_autocorrect`` and
    #   ``discovery_results_per_query`` are also returned to None/5.
    # ``chain``:  Stage 1a issues one domain-discovery query
    #   (``<name> <country> <disambiguation> official website``) and 1b one bare
    #   site-bound evidence query (``site:<domain> AI``) — 2 credits/inst.
    #
    # **Default flipped to ``chain`` on the confirmation run** (PI sign-off,
    # 2026-08-01; report: agent-workspace/2026-08-01-discovery-chain-validation.md).
    # 200 institutions per arm, same sample, GET /account balance deltas:
    #
    #                            legacy    chain
    #   credits / institution      8.52     1.84
    #   >=1 own-domain relevant   20.0%    64.5%
    #   Stage 2 found a site      6.5%     88.0%
    #
    #   paired McNemar 94 gains / 5 losses, exact two-sided p = 2.4e-22.
    #
    # The three defaults below (mode, results-per-query, autocorrect) are set to
    # exactly the configuration that produced those numbers. Keeping the default
    # at a configuration that was never measured is the failure mode this avoids.
    discovery_mode: Literal["legacy", "chain"] = "chain"
    # Leg 2's evidence token. One bare unquoted term by measurement: extra
    # English terms add 0 pp once site-bound and OR-chains are actively harmful
    # (4/24 vs 16/24). Parameterised for the multilingual subproject, which owns
    # native-language legs — do not add English terms here.
    discovery_evidence_term: str = DEFAULT_EVIDENCE_TERM
    # Per-language override of the token above. ``None`` (the default) means
    # "use ``discovery_evidence_term`` for English" — see
    # :attr:`evidence_terms`, which is the single surface the runner reads.
    # Setting both this and a non-default ``discovery_evidence_term`` is an
    # error rather than a silent precedence rule.
    discovery_evidence_terms: Mapping[str, str] | None = None
    # Leg 1: bind the institution name as an exact phrase instead of a hint.
    # Default False. The findings identify the quoted name as the primary
    # failure of the four-slot format (abbreviated master names like
    # "Polson H S" match almost nothing) — but that was measured where a quoted
    # name AND a quoted GenAI term both had to match, so it does not transfer
    # to leg 1 automatically. The flag exists to settle it by measurement.
    discovery_domain_quote_name: bool = False
    # Serper ``autocorrect``. ``None`` omits the key entirely, reproducing the
    # historical request byte-for-byte; ``False`` stops Google silently
    # respelling institution names. A provenance parameter, not a recall lever —
    # but the query recorded in the artifact should be the query Google
    # answered, and ``False`` is what the confirmation run measured. Set None to
    # reproduce a pre-2026-08-01 request exactly.
    serper_autocorrect: bool | None = False
    dry_run: bool = True
    stop_after: StageName = "extract"
    # Stage 1c eligibility pre-filter mode (design memo 2026-07-06, decision 2).
    # ``off``: bypassed. ``shadow``: artifact written, nothing dropped (default
    # for the first smoke run). ``enforce``: only ``pass`` URLs reach Stage 3.
    # Enabling ``enforce`` is a PI decision made on measured shadow recall.
    filter_mode: Literal["off", "shadow", "enforce"] = "shadow"
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
    # Continuous cost monitoring (2026-08): actual-spend budget limit for the
    # live run. When set, the orchestrator tracks token usage after each LLM
    # stage and aborts (raising BudgetExceededError) if the running total
    # exceeds this limit. The pre-flight cost gate (in cli.py) is a separate,
    # earlier check based on projections; this is the runtime enforcement.
    # Sourced from G3O_BUDGET_LIMIT_USD env var or --cost-ceiling CLI flag.
    budget_usd: float | None = None
    # Preflight cost estimate (populated by CLI when --preflight or --execute runs preflight).
    # Used for actual-vs-estimated reconciliation in the cost report.
    preflight_estimate_usd: float | None = None
    # Dry run mode for cost monitoring (2026-08): when True, the cost monitor
    # logs warnings instead of raising BudgetExceededError when budget is exceeded.
    # The run continues and the cost report is still persisted with dry_run: true.
    # Useful for understanding what would happen without actually aborting.
    cost_monitor_dry_run: bool = False
    # Per-stage preflight cost estimates (USD), populated by CLI from preflight output.
    # Used for mid-run projection checking (Gap 2): if actual spend so far scales
    # to a total that exceeds budget × projection_safety_factor, abort early.
    preflight_stage_estimates: dict[str, float] | None = None
    # Projection safety factor (Gap 4): abort when projected_total > budget × this.
    # Default None means projection checking is disabled (off by default).
    # When set, must be >= 1.0 (a factor below 1.0 would abort even when under budget).
    # Non-blocking: stages aren't comparable (extract dominates), so an arbitrary
    # default factor can trigger false aborts. Operators must opt in.
    projection_safety_factor: float | None = None

    def __post_init__(self) -> None:
        """Reject a language this run could not actually query (A7, 2026-08-02).

        The choke point, deliberately at construction rather than only in the
        CLI: a programmatically built config gets the same guarantee, and the
        run fails before it has spent a Serper credit. The roster consulted is
        mode-specific — a language rostered for ``legacy`` is not thereby
        runnable under ``chain``, which needs an evidence term.

        This is also what makes :attr:`institution_search_languages` honest by
        construction: a language that cannot be queried cannot be configured,
        so the provenance column can no longer claim one that never ran.
        """
        # Validate budget_usd is positive (fix: previously accepted zero, which would always abort)
        if self.budget_usd is not None and self.budget_usd <= 0:
            raise ValueError(
                f"budget_usd must be positive, got {self.budget_usd}. "
                f"Use None to disable the budget gate."
            )
        # Validate projection_safety_factor (Gap 4). None means disabled (opt-in).
        if self.projection_safety_factor is not None:
            if math.isnan(self.projection_safety_factor) or math.isinf(self.projection_safety_factor):
                raise ValueError(
                    f"projection_safety_factor must be a finite number >= 1.0, "
                    f"got {self.projection_safety_factor}"
                )
            if self.projection_safety_factor < 1.0:
                raise ValueError(
                    f"projection_safety_factor must be >= 1.0, got {self.projection_safety_factor}. "
                    f"A factor below 1.0 would abort even when under budget."
                )
        if (
            self.discovery_evidence_terms is not None
            and self.discovery_evidence_term != DEFAULT_EVIDENCE_TERM
        ):
            raise ValueError(
                "set discovery_evidence_term or discovery_evidence_terms, not "
                f"both (got {self.discovery_evidence_term!r} and "
                f"{dict(self.discovery_evidence_terms)!r}). The scalar is "
                "shorthand for {'en': <term>}; a silent precedence rule here "
                "would decide which token every leg-2 query carries."
            )
        if self.discovery_mode == "chain":
            assert_languages_rostered(
                self.discovery_languages, self.evidence_term_roster
            )
        else:
            assert_languages_rostered(self.discovery_languages, GENAI_TERMS_BY_LANG)

    @property
    def evidence_term_roster(self) -> dict[str, str]:
        """Every leg-2 token this run *could* use, keyed by language.

        ``discovery_evidence_term`` is kept as CLI/config ergonomics for the
        single-language case and desugars into ``{"en": <term>}``, so the
        n=200 confirmation run stays byte-reproducible while there is still
        only one internal representation to reason about.
        """
        if self.discovery_evidence_terms is not None:
            return dict(self.discovery_evidence_terms)
        return {**EVIDENCE_TERMS_BY_LANG, "en": self.discovery_evidence_term}

    @property
    def evidence_terms(self) -> dict[str, str]:
        """The leg-2 tokens this run *will* issue — the surface the runner reads.

        The roster narrowed to ``discovery_languages`` and ordered by it, so
        the query order in an artifact matches the configured order. Safe to
        index unguarded: ``__post_init__`` has already rejected any language
        absent from the roster.
        """
        roster = self.evidence_term_roster
        return {lang: roster[lang] for lang in self.discovery_languages}

    @property
    def chain_query_languages(self) -> tuple[str, ...]:
        """Languages chain mode actually issues queries in, leg 1 included.

        Leg 1's ``official website`` suffix stays English by PI decision
        (2026-08-02), so **English is always searched under chain mode** even
        when ``discovery_languages`` names only another language. Recording
        that here rather than hiding it keeps the cost of that decision visible
        in the run's own provenance instead of resurfacing as an unexplained
        English result in a non-English readiness assessment.
        """
        ordered = [DOMAIN_QUERY_LANG]
        for lang in self.discovery_languages:
            if lang not in ordered:
                ordered.append(lang)
        return tuple(ordered)

    @property
    def institution_search_languages(self) -> str:
        """Stage 5 provenance string — always the languages Stage 1a/1b actually searched.

        Not independently settable (review, 2026-07-20): a free-standing config
        field let this drift from ``discovery_languages``, so the extraction
        contract's ``institution_search_languages`` column could understate what
        was searched. Deriving it removes that failure mode.

        Mode-aware since 2026-08-02. Chain mode's leg 1 is English whatever
        ``discovery_languages`` says, so deriving this from
        ``discovery_languages`` alone made a ``zh``-configured chain run report
        ``zh`` while every query it issued was English — the chain-mode sibling
        of A7, verified live before the fix. Legacy mode is unchanged.
        """
        if self.discovery_mode == "chain":
            return ",".join(self.chain_query_languages)
        return ",".join(self.discovery_languages)
