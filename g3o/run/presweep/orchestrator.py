"""End-to-end pre-sweep orchestration: live-key gate + stage dispatch."""

from __future__ import annotations

import logging
from typing import Any

from g3o.common import attrition
from g3o.common import config as _config
from g3o.common.institution_report import write_institution_report
from g3o.common.paths import require_layout
from g3o.discovery.serper_client import SerperOptions, set_live_mode
from g3o.report.run_summary import render_run_summary_text, write_run_summary
from g3o.run.presweep.config import PresweepConfig
from g3o.run.presweep.planning import plan_run, update_manifest_llm_provenance
from g3o.run.presweep.records import institution_record
from g3o.run.presweep.stage_classify import (
    _run_classify_official_site,
    _run_classify_triage,
)
from g3o.run.presweep.stage_discovery import (
    _run_discovery_general,
    _run_discovery_site_restricted,
)
from g3o.run.presweep.stage_extract import _run_extract
from g3o.run.presweep.stage_filter import _run_filter_eligibility
from g3o.run.presweep.stage_scrape import _run_scrape
from g3o.run.presweep.stage_validate import _run_validate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resume semantics (Session E, 2026-05-09; chunked Session F.1, 2026-06-10):
#
# Each ``_run_*`` runner is state-aware (Q7=c — auto-inferred from disk):
#
# 1. ``is_done(run_dir, stage)`` → reconstruct the runner's return dict from
#    per-institution artifacts on disk and skip the stage entirely (Q3=e2).
# 2. Active state file present (LLM stages only) → the chunk plan in the
#    state file is canonical (Q4=ii): fetched chunks are skipped, in-flight
#    chunks rejoin polling, not-yet-submitted chunks reconcile-then-submit.
#    All of this lives in ``g3o.common.run_state.run_chunked_stage``; the
#    runners just build the deterministic job list and a persist callback.
# 3. No state, no done marker → fresh run; deterministic stages also support
#    per-artifact skip-if-exists for partial-recovery without a ``.done`` marker.
#
# Failed/cancelled/expired batches do NOT auto-resubmit (Q3=d). The active
# state file remains and the orchestrator raises with the path to the file.
# ---------------------------------------------------------------------------


def _assert_live_keys(config: PresweepConfig) -> None:
    """Hard-fail before a live run if a required API key is unset (review F1).

    Stage 1 discovery always needs Serper; Stages 2/3/5/6 need OpenAI. Failing
    fast at startup beats discovering a missing key after Serper spend (or, worse
    for Serper, silently returning mock results). The OpenAI check is skipped
    when ``--stop-after discovery_general`` means no LLM stage will run.
    """
    if not _config.SERPER_API_KEY:
        raise RuntimeError(
            "SERPER_API_KEY is not set, but --execute requires a live Serper key "
            "for Stage 1 discovery. Refusing to run with mock discovery. Set the "
            "key, or run without --execute (dry run)."
        )
    if config.stop_after != "discovery_general" and not _config.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set, but --execute beyond Stage 1a requires a "
            "live OpenAI key (Stages 2/3/5/6). Set the key, pass "
            "--stop-after discovery_general, or run a dry run."
        )


def run_presweep(config: PresweepConfig) -> dict[str, Any]:
    """End-to-end pre-sweep runner.

    Default ``config.dry_run=True`` writes the planning artifacts and returns;
    the per-stage ``--execute`` path runs Stages 1a/2/1b/3/4/5 (and 6 when
    ``stop_after="validate"``) live, blocking on each Batch API stage's
    terminal state via :func:`g3o.common.run_state.run_chunked_stage`.

    Resume (Session E, Q7=c): if ``--execute`` is invoked against an existing
    ``runs/<run_id>/`` with state files present, each stage runner auto-detects
    them and rejoins polling without re-submitting. Per-URL scrape idempotency
    (Q5=a) covers Stage 4 partial recovery.

    Live-mode gate (review F1, 2026-06-10): ``--execute`` hard-fails at startup
    if the required API keys are unset (no silent mock discovery), and switches
    the Serper client into live mode (no mock results, request failures raise
    rather than degrade to an empty artifact). The key assertion runs before the
    mode switch so a failed gate leaves global state untouched.
    """
    if not config.dry_run:
        _assert_live_keys(config)
    set_live_mode(not config.dry_run)
    plan = plan_run(config)
    # Storage layout v2 gate (docs/storage-layout-v2.md §B2). plan_run has just
    # written the manifest, so this asserts the tree this process is about to
    # write into is the layout this code knows how to read.
    require_layout(plan.run_dir)
    summary: dict[str, Any] = {
        "run_id": config.run_id,
        "run_dir": str(plan.run_dir),
        "n_institutions": len(plan.sample),
        "dry_run": config.dry_run,
    }
    if config.dry_run:
        summary["next_step"] = (
            f"g3o presweep --execute --run-id {config.run_id} "
            f"--sample-size {config.sample_size} --seed {config.seed}"
        )
        return summary

    # Guarantee the attrition ledger exists for a live run (empty ⇒ nothing
    # dropped/degraded, a stronger signal than a missing file). Review F4/F15.
    attrition.ensure_ledger(plan.run_dir)

    # The finally-clause folds response-side LLM provenance into the manifest
    # (T1) on success, on every --stop-after early return, and best-effort on
    # a crash; the state files it reads remain the ground truth either way.
    try:
        serper_options = SerperOptions(autocorrect=config.serper_autocorrect)
        discovery_general = _run_discovery_general(
            plan.run_dir,
            plan.sample,
            languages=config.discovery_languages,
            num_results=config.discovery_results_per_query,
            max_workers=config.max_workers,
            mode=config.discovery_mode,
            options=serper_options,
            domain_quote_name=config.discovery_domain_quote_name,
        )
        summary["n_discovery_general"] = sum(
            len(v) for v in discovery_general.values()
        )
        if config.stop_after == "discovery_general":
            return summary

        official_sites = _run_classify_official_site(
            plan.run_dir,
            plan.sample,
            discovery_general,
            run_id=config.run_id,
            model=config.model,
            poll_interval=config.poll_interval,
            max_wait=config.max_wait_per_stage,
        )
        summary["n_official_sites"] = sum(1 for v in official_sites.values() if v)
        summary["n_official_sites_bypassed"] = sum(
            1
            for row in plan.sample
            if institution_record(row).get("official_site_url")
        )
        if config.stop_after == "classify_official_site":
            return summary

        discovery_site_restricted = _run_discovery_site_restricted(
            plan.run_dir,
            plan.sample,
            official_sites,
            languages=config.discovery_languages,
            num_results=config.discovery_results_per_query,
            max_workers=config.max_workers,
            mode=config.discovery_mode,
            evidence_terms=config.evidence_terms,
            options=serper_options,
        )
        summary["n_discovery_site_restricted"] = sum(
            len(v) for v in discovery_site_restricted.values()
        )
        if config.stop_after == "discovery_site_restricted":
            return summary

        # Stage 1c — deterministic eligibility pre-filter (design memo
        # 2026-07-06). Screens the 1a+1b union and, under ``enforce``, hands
        # Stage 3 only the ``pass`` URLs; ``shadow`` (default) writes the
        # would-drop artifact but leaves the union intact. The 1a/1b artifacts
        # are never mutated — pruning is applied to in-memory copies only.
        filter_general, filter_site_restricted, filter_stats = _run_filter_eligibility(
            plan.run_dir,
            plan.sample,
            discovery_general,
            discovery_site_restricted,
            mode=config.filter_mode,
        )
        summary["filter_mode"] = filter_stats["mode"]
        summary["n_filter_would_drop"] = filter_stats["n_would_drop"]
        summary["n_filter_enforced_drop"] = filter_stats["n_enforced_drop"]
        if config.stop_after == "filter_eligibility":
            return summary

        triaged = _run_classify_triage(
            plan.run_dir,
            plan.sample,
            filter_general,
            filter_site_restricted,
            official_sites,
            run_id=config.run_id,
            model=config.model,
            poll_interval=config.poll_interval,
            max_wait=config.max_wait_per_stage,
        )
        summary["n_triaged_kept"] = sum(len(v) for v in triaged.values())
        if config.stop_after == "classify_triage":
            return summary

        scraped = _run_scrape(
            plan.run_dir,
            plan.sample,
            triaged,
            respect_robots=config.scrape_respect_robots,
            host_delay_seconds=config.scrape_host_delay_seconds,
            render_on_download_failure=config.scrape_render_on_download_failure,
            empty_page_min_chars=config.empty_page_min_chars,
            max_workers=config.max_workers,
        )
        summary["n_pages_scraped"] = sum(len(v) for v in scraped.values())
        if config.stop_after == "scrape":
            return summary

        n_extracted = _run_extract(
            plan.run_dir,
            plan.sample,
            scraped,
            institution_search_languages=config.institution_search_languages,
            model=config.model,
            poll_interval=config.poll_interval,
            max_wait=config.max_wait_per_stage,
            run_id=config.run_id,
            text_cap_chars=config.extract_text_cap_chars,
            text_cap_rule=config.extract_text_cap_rule,
            empty_page_min_chars=config.empty_page_min_chars,
        )
        summary["n_extracted"] = n_extracted
        if config.stop_after == "extract":
            return summary

        validate_summary = _run_validate(
            plan.run_dir,
            plan.sample,
            model=config.model,
            poll_interval=config.poll_interval,
            max_wait=config.max_wait_per_stage,
        )
        summary["n_consolidated"] = validate_summary.get("n_consolidated", 0)
        summary["n_validate_failed"] = validate_summary.get("n_failed", 0)
        summary["validate_batch_ids"] = validate_summary.get("batch_ids")
        return summary
    finally:
        update_manifest_llm_provenance(plan.run_dir)
        # Best-effort (Feature 1): compute + persist institution_report.{jsonl,csv}
        # on every stop_after early return and on a crash, same as the
        # provenance fold above. Guarded so a bug here can never mask the
        # stage exception this finally block is already propagating.
        try:
            write_institution_report(plan.run_dir)
        except Exception:
            logger.exception(
                "institution_report generation failed for %s (non-fatal)",
                plan.run_dir,
            )
        # Feature 3: human-readable run summary, stdout + persisted JSON.
        # Depends on institution_report.jsonl above; same best-effort guard.
        try:
            run_summary = write_run_summary(plan.run_dir)
            print(render_run_summary_text(run_summary))
        except Exception:
            logger.exception(
                "run_summary generation failed for %s (non-fatal)", plan.run_dir
            )
