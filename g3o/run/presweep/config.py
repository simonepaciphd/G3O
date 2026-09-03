"""Pre-sweep run configuration: stage roster + :class:`PresweepConfig`."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from g3o.common.batch_client import DEFAULT_MODEL
from g3o.common.languages import (
    LanguagePolicy,
    assert_policy_rostered,
    load_signed_policy,
    search_languages_string,
)
from g3o.discovery.query_builder import (
    DEFAULT_EVIDENCE_TERM,
    DOMAIN_QUERY_LANG,
    DOMAIN_SUFFIX_BY_LANG,
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
#: ``discovery_languages``'s default, named so ``__post_init__`` can tell "the
#: operator left it alone" from "the operator set it", which is what makes the
#: mutual exclusion with ``language_policy`` a refusal rather than a precedence
#: rule.
DEFAULT_DISCOVERY_LANGUAGES: tuple[str, ...] = ("en",)
#: The eight roster stages. ``stop_after``, ``stages_planned``, the archive's
#: completeness check and ``status`` all count in these. Two legs added on
#: 2026-09-03 run as **sub-steps** of roster stages rather than as entries here:
#: the localized leg-1 fallback and its Stage 2 re-run
#: (``discovery_general_fallback`` / ``classify_official_site_fallback``) inside
#: the ``classify_official_site`` phase, and the open evidence leg
#: (``discovery_evidence_open``) inside ``discovery_site_restricted``. Each keeps
#: its own ``_state``/``.done`` file and telemetry span, so resume, cost
#: accounting and the event log see them; the roster stays eight so that every
#: run before them remains readable by the same code.
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
    discovery_languages: tuple[str, ...] = DEFAULT_DISCOVERY_LANGUAGES
    # ── Per-institution language selection (PI-signed 2026-08-30) ────────────
    # The ``policy_id`` of a signed policy in ``g3o/common/policies/``, or
    # ``None`` for the run-level ``discovery_languages`` tuple above — which is
    # every run to date, and stays the default.
    #
    # An id, not a ``LanguagePolicy``: a config round-trips through JSON
    # (``g3o.run.orchestrate.submit``), and a mapping a config file could
    # supply inline would be a 225-row language instrument that nobody signed,
    # arriving through the same door as a batch size. Naming a signed artifact
    # keeps the instrument in the tree and the config a record of which one ran.
    #
    # Setting this **and** ``discovery_languages`` is an error rather than a
    # precedence rule, for the reason the evidence-term pair below is: a silent
    # precedence here would decide which languages every leg-2 query is issued
    # in, on every institution of the run.
    language_policy: str | None = None
    # ── Leg 1 goes multilingual — as an English-first FALLBACK (PI rulings
    #    2026-09-01 and 2026-09-03; card 2 of agent-workspace/2026-09-01-discovery-legs/)
    # When True, Stage 1a still issues the single English domain query it always
    # has, on every institution; then, for each institution Stage 2 came away
    # from with no official site, a second pass issues **one localized query per
    # non-English language the institution's policy row names**, taking each
    # suffix from ``DOMAIN_SUFFIX_BY_LANG``, and Stage 2 runs again on the
    # widened candidates. English first because the card-2 probe measured it
    # cheaper at every k (FINDINGS-ordering.md §1); fallback rather than additive
    # because the same probe measured the localized block adding zero recall
    # where English already succeeds and ~a third where it fails (§2, §4). The
    # 2026-09-01 card specified an additive leg; that delta is recorded in
    # PREREGISTRATION.md §9.4 and ruled on 2026-09-03.
    #
    # **Default False.** Production is byte-identical to every run before the
    # flag existed until a run config sets it. The gate that reads it is the
    # pre-spend choke point below: every tag the policy can emit needs a row in
    # ``DOMAIN_SUFFIX_BY_LANG``, and a missing row refuses the run at construction.
    #
    # A bool rather than a language tuple, deliberately. The languages are not a
    # free parameter: they are the signed policy's answer for the institution's
    # country, and offering a tuple here would be a second country->language
    # instrument arriving through the same door as a batch size. The card says
    # reuse the signed mapping and build no parallel one.
    discovery_leg1_multilingual: bool = False
    # ── The open evidence leg (PI ruling 2026-09-03; measured as card 3) ──────
    # When True, a fourth leg issues ``"<name>" <country> <disambiguation>
    # "<term>"`` — non-site-bound — once per policy language, English included
    # via ``always_include``, with the term from the signed 90-row evidence
    # roster. Its URLs join the 1a+1b union at Stage 1c and triage; they do not
    # reach Stage 2. Card 3 (n=600, real Stages 1c → 3 → 5) measured it adding
    # 45 institutions with confirmed evidence the chain never reaches (+7.5pp)
    # at ~1.08x the marginal-institution cost, 59.5% of its rows non-official
    # against the chain's 8.1% — which is why it is a flag and not a default:
    # the source mix of collected evidence is a codebook-adjacent property.
    #
    # **Default False**, for the same byte-identity reason as the flag above.
    discovery_evidence_open: bool = False
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
    # Per-institution Stage 4 wall-clock budget (issue #96, PI ruling
    # 2026-08-26: budget-then-skip **plus** a named attrition reason). When the
    # budget is spent, the institution completes with the pages it has and every
    # URL it did not reach is recorded under ``crawl_delay_exceeded`` — a member
    # of ``g3o.report.outcomes._FAILURE_REASONS``, so the institution reads
    # PROCESSING_FAILED rather than NO_EVIDENCE_FOUND. The rejected alternative
    # was capping the honoured ``Crawl-delay`` itself, which would partially
    # reverse D4; this leaves D4 intact — G3O never fetches faster than a site
    # asked, it only stops waiting and says so. ``None`` disables the budget and
    # restores the pre-#96 unbounded behaviour.
    #
    # **Default 3600 s (1 h), set from the measured distribution** of run
    # ``r20260824T215623Z-bb4e`` (n=4,000). Per-institution Stage 4 spans, over
    # the 2,045 institutions that ran a cold pass (no cached URLs, not straddling
    # the resume gap), from ``_scrape_telemetry.jsonl``:
    #
    #     p50 8 s · p95 72 s · p99 205 s · p99.9 613 s
    #     slowest legitimate institution   1,324 s  (INST-0015237, 17 URLs on a
    #                                                host declaring Crawl-delay 120)
    #     the host that motivated #96     25,923 s  (INST-0048190, Crawl-delay 8640)
    #
    # The distribution is bimodal with nothing between 22 minutes and 7.2 hours,
    # so the two populations separate cleanly and the only question is where in
    # that gap to sit. 3600 s is chosen from the *structural* ceiling rather
    # than from the observed p99.9: Stage 3 keeps at most 20 URLs per institution
    # (measured max on this run), so the worst legitimate case is 20 URLs against
    # the slowest delay a site plausibly declares, and 20 x 180 s = 3,600 s. A
    # tighter default fitted to the observed tail (say 1,800 s) would truncate a
    # legitimate 20-URL institution behind a 120 s delay, and the observed tail
    # is thin — n=2,045 cold institutions sample far fewer distinct hosts than
    # n=10,000 will.
    #
    # It cuts exactly one of the 2,045 measured institutions, sits 2.7x above the
    # slowest legitimate one and 7.2x below the pathological one, and turns an
    # unbounded stall into a bounded one: before this, a single host could hold
    # Stage 4 open past ``max_wait_per_stage`` (25 h) and fail the whole run.
    scrape_max_institution_seconds: float | None = 3600.0
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
            self.scrape_max_institution_seconds is not None
            and self.scrape_max_institution_seconds <= 0
        ):
            raise ValueError(
                "scrape_max_institution_seconds must be positive, got "
                f"{self.scrape_max_institution_seconds}. Use None to disable "
                "the per-institution scrape budget; a zero or negative budget "
                "would strand every URL of every institution under "
                "crawl_delay_exceeded and report the whole run "
                "PROCESSING_FAILED."
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
        if self.language_policy is not None and (
            tuple(self.discovery_languages) != DEFAULT_DISCOVERY_LANGUAGES
        ):
            raise ValueError(
                f"set language_policy or discovery_languages, not both (got "
                f"{self.language_policy!r} and {tuple(self.discovery_languages)!r}). "
                f"A policy selects a language set per institution; "
                f"discovery_languages selects one for the whole run. A silent "
                f"precedence rule between them would decide which languages every "
                f"leg-2 query of the run is issued in."
            )
        # Leg-1 coherence before any roster check, so a misconfigured flag reports
        # itself rather than surfacing as an unrostered-language error about a
        # roster the operator never meant to consult.
        if self.discovery_leg1_multilingual:
            # Chain-only: under ``legacy`` leg 1 *is* the GenAI-term roster, so
            # there is no un-localized suffix to localize and this flag would
            # silently mean nothing.
            if self.discovery_mode != "chain":
                raise ValueError(
                    "discovery_leg1_multilingual requires discovery_mode="
                    f"'chain' (got {self.discovery_mode!r}). Legacy's leg 1 is "
                    "already the language roster; there is no un-localized "
                    "suffix there for this flag to act on."
                )
            # Policy-only, because the ruling is that the localized leg is
            # **additive**. That property is not a property of this code — it
            # comes from the signed policy's ``always_include: ['en']``, which
            # puts English among every institution's languages. A run-level
            # ``discovery_languages`` tuple carries no such guarantee, so
            # ``discovery_languages=('fr',)`` plus this flag would *replace* the
            # English arm rather than add to it, and report a within-institution
            # comparison that was never run.
            if self.language_policy is None:
                raise ValueError(
                    "discovery_leg1_multilingual requires language_policy to be "
                    "set. The ruling is that the localized leg is additive, and "
                    "what makes it additive is the signed policy's "
                    "always_include=['en'] — a run-level discovery_languages "
                    "tuple can drop English and would turn an additive leg into "
                    "a swap."
                )
        if self.discovery_evidence_open and self.discovery_mode != "chain":
            # Legacy's leg 1 *is* an open GenAI-term leg (eight English terms,
            # not site-bound); adding a second one would double it, and the
            # measurement behind this flag was made against the chain.
            raise ValueError(
                "discovery_evidence_open requires discovery_mode='chain' (got "
                f"{self.discovery_mode!r}). Legacy mode's leg 1 is already a "
                "non-site-bound GenAI-term leg; this flag adds the open evidence "
                "leg to the two-query chain and was measured against it."
            )
        if self.discovery_mode == "chain":
            assert_languages_rostered(
                self.discovery_languages, self.evidence_term_roster
            )
        else:
            assert_languages_rostered(self.discovery_languages, GENAI_TERMS_BY_LANG)
        # The pre-spend choke point for per-institution selection (A7). The
        # run-level checks above cover ``discovery_languages``; this one covers
        # every tag the policy could ever select, on any institution of the
        # sample, *before* the first Serper credit — an UnknownLanguageError
        # raised on institution 3,000 of 10,000 has already spent 3,000
        # institutions' worth of queries, and there is deliberately no English
        # fallback to absorb it.
        policy = self.signed_language_policy
        if policy is not None:
            assert_policy_rostered(
                policy,
                self.evidence_term_roster
                if self.discovery_mode == "chain"
                else GENAI_TERMS_BY_LANG,
            )
        if self.discovery_leg1_multilingual:
            # The same pre-spend choke point, one roster further: every tag the
            # policy could emit on any institution must have a signed leg-1
            # suffix before the first credit. With the roster at one English row
            # this is what refuses to start a multilingual run, and it names the
            # card the suffixes are signed on rather than leg 2's subproject.
            assert_policy_rostered(
                policy,
                DOMAIN_SUFFIX_BY_LANG,
                "agent-workspace/2026-09-01-discovery-legs/cards/"
                "2-legs-leg1-multilingual.txt, not a config change",
            )

    @property
    def signed_language_policy(self) -> LanguagePolicy | None:
        """The loaded policy :attr:`language_policy` names, or ``None``.

        ``None`` is the run-level tuple path — every run to date. Loading is
        cached in :func:`g3o.common.languages.load_signed_policy`, so touching
        this property per institution is a dict lookup, not a 225-row parse.
        """
        if self.language_policy is None:
            return None
        return load_signed_policy(self.language_policy)

    def languages_for(self, institution: Mapping[str, Any]) -> tuple[str, ...]:
        """The languages **this institution's** leg-2 queries are issued in.

        The run-level ``discovery_languages`` when no policy is configured, and
        the policy's answer for the institution's country when one is —
        ``always_include`` already applied, so a caller cannot get the signed
        row and forget the policy layer.
        """
        policy = self.signed_language_policy
        if policy is None:
            return tuple(self.discovery_languages)
        return policy.languages_for(institution)[0]

    def leg1_fallback_languages_for(
        self, institution: Mapping[str, Any]
    ) -> tuple[str, ...]:
        """The languages **this institution's localized leg-1 pass** is issued in.

        The policy's answer for the institution's country **minus English**, in
        the policy's order — English was already issued by the first pass, and
        re-issuing it would be a credit spent on a query whose result is already
        in the artifact. Empty when :attr:`discovery_leg1_multilingual` is off,
        or when the row names English only; the fallback runner records the
        latter as ``fallback_pass.reason``.

        Deliberately a separate method from :meth:`languages_for`, which answers
        for leg 2 and the open leg: the two legs have always been allowed to
        disagree, and collapsing them would make the leg-1 instrument change as
        a side effect of a leg-2 decision.

        Safe to index into :data:`DOMAIN_SUFFIX_BY_LANG` unguarded for the same
        reason :meth:`evidence_terms_for` is: ``__post_init__`` has already
        rejected a policy that could select an unrostered tag on any
        institution, before any spend.
        """
        if not self.discovery_leg1_multilingual:
            return ()
        return tuple(
            lang for lang in self.languages_for(institution) if lang != DOMAIN_QUERY_LANG
        )

    def evidence_terms_for(self, institution: Mapping[str, Any]) -> dict[str, str]:
        """:attr:`evidence_terms`, one institution at a time.

        Safe to index unguarded for the same reason :attr:`evidence_terms` is:
        ``__post_init__`` has already rejected a policy that could select a tag
        absent from the roster, on any institution, before any spend.
        """
        roster = self.evidence_term_roster
        return {lang: roster[lang] for lang in self.languages_for(institution)}

    def institution_search_languages_for(self, institution: Mapping[str, Any]) -> str:
        """:attr:`institution_search_languages`, one institution at a time.

        Mode-aware through the same helper the run-level property is, so chain
        mode's English leg 1 is named once and only once even when the policy
        already put ``en`` in the institution's leg-2 set. The two English
        queries do different jobs; the column has one slot for the tag.
        """
        return search_languages_string(
            self.languages_for(institution), mode=self.discovery_mode
        )

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

        **Not the per-row answer under a language policy** (2026-08-30). When
        :attr:`language_policy` is set the run has no single answer, and this
        property keeps describing the run-level configuration rather than
        inventing one: ``institution_search_languages_for`` is what Stage 5
        writes into each row, and ``planning.config_snapshot`` records the
        policy id and hash so the manifest and the F7 resume guard see the
        instrument that actually ran instead of this string.
        """
        if self.discovery_mode == "chain":
            return ",".join(self.chain_query_languages)
        return ",".join(self.discovery_languages)
