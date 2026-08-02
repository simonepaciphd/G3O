"""PI-tunable health thresholds for the presweep pipeline.

All values are engineering parameters, not substantive quality judgments.
They flag pipeline mechanics (stage attrition, parse failures, scrape yield)
but say nothing about whether the collected data is analytically useful — that
is the PI's domain.

Change them by passing a custom instance to ``compute_health_report()``, or by
loading a JSON file with ``HealthThresholds.from_json(path)``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HealthThresholds:
    """Per-stage warn/fail thresholds.  **All values are PI-tunable.**

    Defaults target a smoke run of ~10 institutions.  For a production sweep
    (hundreds of institutions) you may want to tighten the warn levels; for a
    very small pilot (3–5 institutions) you may want to loosen them.

    ``high_is_bad`` fields (empty-drop rate, unclear rate) fire warn/fail when
    the value *exceeds* the threshold; all others fire when the value *falls
    below* it.
    """

    # ── Stage 1a: discovery_general ──────────────────────────────────────────
    # % of institutions with ≥1 candidate URL returned by Serper.
    # Applies to ``discovery_mode="legacy"`` only — see below.
    discovery_general_warn_pct: float = 0.80   # PI-tunable
    discovery_general_fail_pct: float = 0.60   # PI-tunable

    # ── Stage 1a under the two-query chain (2026-08-01) ──────────────────────
    # % of institutions where leg 1 (``<name> <country> official website``)
    # produced a usable non-aggregator domain for Stage 2 to adjudicate.
    #
    # The gauge above cannot serve here: leg 1 returns results for essentially
    # every institution, so "≥1 candidate URL" is trivially satisfied and would
    # read green whatever the query does. Calibrated against the findings'
    # evaluation set, which reached 21/24 = 87.5%; warn a little under that,
    # fail where the chain is clearly not delivering domains.
    discovery_domain_warn_pct: float = 0.80    # PI-tunable
    discovery_domain_fail_pct: float = 0.60    # PI-tunable

    # ── Stage 2: classify_official_site ──────────────────────────────────────
    # % of institutions (with ≥1 candidate URL) where an official site was found.
    official_site_warn_pct: float = 0.70       # PI-tunable
    official_site_fail_pct: float = 0.40       # PI-tunable

    # ── Accuracy canaries against the master (2026-08-02) ────────────────────
    # Two gauges scored only where the master supplies a `website`. Unlike most
    # defaults in this file they are NOT smoke-run guesses — both are set from
    # the 2026-08-01 n=200 measurement.
    #
    # Shared minimum sample. Ground truth covers ~2% of the registry, so a
    # 10-institution smoke run typically yields 0-1 comparisons. A canary that
    # fires on n=1 is noise, and noise trains you to ignore the gauge. Below
    # this the report emits ``insufficient_ground_truth`` rather than a colour.
    ground_truth_min_n: int = 10               # PI-tunable

    # Leg-1 recall: % of institutions where leg 1 surfaced the master's own
    # domain at any rank. Measured 82.0%. THIS is the leg-1 regression signal
    # (§5.1) — model-free, so nothing in a prompt can inflate it.
    leg1_recall_warn_pct: float = 0.72         # PI-tunable
    leg1_recall_fail_pct: float = 0.55         # PI-tunable

    # Stage 2 pick vs the master, at the registrable domain. Measured 86.9%
    # (153/176).
    #
    # CAVEAT, 2026-08-02: `institution_record()` puts the master's `website`
    # into the Stage 2 prompt, so the classifier can read the value this gauge
    # scores it against. Until that is resolved (a PI call — removing it
    # changes model input and breaks comparability with the 2026-08-01
    # numbers), read this as a liveness check, not an accuracy measurement,
    # and rely on the leg-1 gauge above for regression detection.
    official_site_accuracy_warn_pct: float = 0.80   # PI-tunable
    official_site_accuracy_fail_pct: float = 0.65   # PI-tunable

    # ── Stage 1b: discovery_site_restricted ──────────────────────────────────
    # % of institutions (with an official site) that got ≥1 site-restricted URL.
    discovery_site_restricted_warn_pct: float = 0.60  # PI-tunable
    discovery_site_restricted_fail_pct: float = 0.30  # PI-tunable

    # ── Stage 3: classify_triage ──────────────────────────────────────────────
    # % of institutions with ≥1 kept URL after triage.
    triage_institutions_warn_pct: float = 0.70  # PI-tunable
    triage_institutions_fail_pct: float = 0.40  # PI-tunable
    # Overall URL keep rate (kept / total triaged).
    triage_url_keep_warn_pct: float = 0.30      # PI-tunable
    triage_url_keep_fail_pct: float = 0.15      # PI-tunable

    # ── Stage 4: scrape ───────────────────────────────────────────────────────
    # % of attempted URLs (kept by triage) successfully scraped.
    scrape_success_warn_pct: float = 0.70       # PI-tunable
    scrape_success_fail_pct: float = 0.40       # PI-tunable

    # ── Stage 5: extract ──────────────────────────────────────────────────────
    # % of eligible (non-empty) pages that produced an extract row.
    extract_success_warn_pct: float = 0.70      # PI-tunable
    extract_success_fail_pct: float = 0.40      # PI-tunable
    # % of scraped pages dropped as near-empty (high = concern, high_is_bad).
    extract_empty_warn_pct: float = 0.30        # PI-tunable
    extract_empty_fail_pct: float = 0.60        # PI-tunable

    # ── Stage 6: validate ─────────────────────────────────────────────────────
    # % of institutions (with ≥1 extract) that were successfully consolidated.
    validate_consolidated_warn_pct: float = 0.80  # PI-tunable
    validate_consolidated_fail_pct: float = 0.60  # PI-tunable
    # % of consolidated institutions with has_genai_activity=unclear (high_is_bad).
    # NOTE: a high unclear rate may be honest (thin evidence) rather than a
    # pipeline failure — the PI decides whether to treat it as a concern.
    validate_unclear_warn_pct: float = 0.40       # PI-tunable
    validate_unclear_fail_pct: float = 0.70       # PI-tunable

    @classmethod
    def from_json(cls, path: str | Path) -> HealthThresholds:
        """Load threshold overrides from a JSON file.  Partial overrides OK."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        valid = {k for k in data if k in cls.__dataclass_fields__}
        return cls(**{k: data[k] for k in valid})


__all__ = ["HealthThresholds"]
