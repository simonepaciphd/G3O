"""Institution-level final outcome determination — read-only from disk.

Walks a presweep run and assigns each institution exactly one of four final
statuses:

- ``EVIDENCE_FOUND``    — reached Stage 6; ``has_genai_activity == "yes"``
                          with >=1 consolidated activity.
- ``NO_EVIDENCE_FOUND`` — the run was configured to reach Stage 6 and this
                          institution was genuinely evaluated that far (or ran
                          out of legitimate upstream input, e.g. zero URLs
                          kept by triage) but no qualifying evidence surfaced.
                          Requires positive on-disk proof that the stage which
                          would have produced the missing artifact actually
                          completed — see "Whole-run aborts" below.
- ``PROCESSING_FAILED`` — a technical failure (an attrition-recorded parse /
                          scrape failure for this institution, or an
                          unreadable ``6_validate.json``) prevented a
                          conclusion.
- ``RUN_TRUNCATED``     — the run itself was configured to stop before Stage 6
                          (``--stop-after``); this institution was never
                          evaluated for evidence, independent of what its
                          partial artifacts look like.

Whole-run aborts
----------------

An institution that never gets its turn because the *whole run* aborts
mid-flight on an unrelated fatal error (e.g. a ``SerperRequestError`` that
aborts Stage 1a for every institution still queued behind the one that hit
it) has no attrition record of its own and no ``6_validate.json``. It used to
be reported as ``NO_EVIDENCE_FOUND`` — an assertion that the pipeline looked
and found nothing, when in fact it never looked.

Something on disk *does* distinguish the two cases: the resume machinery's
``_state/.done/{stage}.json`` markers, written by every stage on completion.
So an empty result is only read as a finding when the stage that would have
produced the missing artifact is marked done; otherwise the institution's
absence is unexplained and it is reported ``PROCESSING_FAILED``.

Note this is per-institution, not run-wide. An institution whose triage
completed and kept zero URLs is a genuine ``NO_EVIDENCE_FOUND`` even if the
run later died during scrape — it got its turn and legitimately produced
nothing. Only institutions still waiting on a stage the run never finished
are reclassified.

Two limits remain, deliberately:

- If ``_state/`` is absent entirely (a run predating the state machinery, or
  a hand-built fixture), there is no evidence either way and the permissive
  reading is kept rather than inventing a failure.
- A run configured with ``--stop-after`` short of ``validate`` reports
  ``RUN_TRUNCATED`` whether or not it also aborted. That status already says
  the institution was never evaluated, so it asserts nothing false; splitting
  it further was not worth a fifth status.

**Scope of the guarantee.** This is the *report-side* half: it stops a loudly
aborted run — one that left a stage without its marker — from being read off
disk as a substantive no-evidence finding. It does **not** detect silent loss
*inside* a stage that completed and wrote its marker (Batch results lost
between fetch and persistence, say). Catching that needs run-time
reconciliation at the ``run_state`` / ``batch_client`` layer and is a separate,
unimplemented work item. So a clean report here means "no abort was visible on
disk", not "nothing was lost".

No network calls. Mirrors :mod:`g3o.report.health`'s disk-only-read
convention.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common import attrition as _attrition
from g3o.common.artifact_io import glob_artifacts, read_artifact
from g3o.common.contract import BatchResponse
from g3o.common.paths import institution_dir, require_layout
from g3o.common.run_state import is_done, state_dir
from g3o.common.timing import read_timing
from g3o.persist.writer import load_consolidated_outputs

# Attrition reasons that represent a genuine technical failure, as opposed to
# expected/normal filtering (robots_disallowed, empty_page_dropped,
# page_text_truncated, official_site_unparseable).
_FAILURE_REASONS: frozenset[str] = frozenset(
    {"serper_request_failed", "scrape_failed", "parse_failed"}
)


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# Stages whose completion marker gates an "empty result" reading. Mirrors the
# tail of g3o.run.presweep.config.STAGES; only the stages that can leave an
# institution with nothing to show are listed.
_STAGES_WITH_MARKERS: tuple[str, ...] = (
    "classify_triage",
    "scrape",
    "extract",
    "validate",
)


def _stage_completion(run_dir: Path) -> dict[str, bool] | None:
    """Which stages the *run* finished, per ``_state/.done/`` (Q3=e2).

    Returns ``None`` when the run carries no ``_state/`` directory at all —
    a run predating the state machinery, or a hand-built fixture. That is an
    absence of evidence, not evidence of an abort, so callers fall back to the
    permissive reading rather than manufacturing a failure.
    """
    if not state_dir(run_dir).exists():
        return None
    return {stage: is_done(run_dir, stage) for stage in _STAGES_WITH_MARKERS}


def _extracted_row_count(extract_dir: Path) -> int:
    """Flattened ContractRow count across every Stage 5 extract file.

    Deliberately a row count, not a file count (g3o.report.health's
    n_extracts is the file count; this is a different, complementary metric
    named extracted_row_count to avoid confusion between the two).
    """
    total = 0
    for path in glob_artifacts(extract_dir):
        try:
            payload = json.loads(read_artifact(path))
            total += len(BatchResponse.model_validate(payload).data)
        except Exception:
            # An unreadable extract file doesn't inflate the count; the
            # institution's failure status is decided from the attrition
            # ledger / 6_validate.json outcome, not from this helper.
            continue
    return total


def _stage_reached(inst_dir: Path) -> str | None:
    """Last stage that left on-disk output for this institution, or None."""
    reached: str | None = None
    if (inst_dir / "1a_discovery_general.json").exists():
        reached = "discovery_general"
    if (inst_dir / "2_official_site.json").exists():
        reached = "classify_official_site"
    if (inst_dir / "1b_discovery_site_restricted.json").exists():
        reached = "discovery_site_restricted"
    if (inst_dir / "1c_filter_eligibility.json").exists():
        reached = "filter_eligibility"
    if (inst_dir / "3_triage.json").exists():
        reached = "classify_triage"
    if glob_artifacts(inst_dir / "scrape"):
        reached = "scrape"
    if glob_artifacts(inst_dir / "extract"):
        reached = "extract"
    if (inst_dir / "6_validate.json").exists():
        reached = "validate"
    return reached


def _urls_discovered(inst_dir: Path) -> int:
    total = 0
    for fname in ("1a_discovery_general.json", "1b_discovery_site_restricted.json"):
        p = inst_dir / fname
        if p.exists():
            payload = json.loads(p.read_text(encoding="utf-8"))
            total += len(payload.get("records", []))
    return total


def _urls_kept(inst_dir: Path) -> int:
    p = inst_dir / "3_triage.json"
    if not p.exists():
        return 0
    payload = json.loads(p.read_text(encoding="utf-8"))
    return sum(1 for d in payload.get("decisions", []) if d.get("decision") == "keep")


def _pages_scraped(inst_dir: Path) -> int:
    return len(glob_artifacts(inst_dir / "scrape"))


def compute_institution_report(run_dir: str | Path) -> list[dict[str, Any]]:
    """Compute one final-outcome record per institution in the run's sample."""
    run_dir = Path(run_dir)
    require_layout(run_dir)
    manifest = _load_manifest(run_dir)
    institution_ids: list[str] = manifest.get("institutions", [])
    stopped_after_stage = manifest.get("config", {}).get("stop_after")

    ledger = _attrition.read_records(run_dir)
    failures_by_inst: dict[str, list[dict[str, Any]]] = {}
    for rec in ledger:
        if rec.get("reason") in _FAILURE_REASONS:
            failures_by_inst.setdefault(rec.get("institution_id", ""), []).append(rec)

    _, validate_parse_failures = load_consolidated_outputs(run_dir)
    validate_parse_failures = set(validate_parse_failures)

    stage_completion = _stage_completion(run_dir)

    records: list[dict[str, Any]] = []
    for inst_id in institution_ids:
        inst_dir = institution_dir(run_dir, inst_id)
        stage_reached = _stage_reached(inst_dir)
        urls_discovered = _urls_discovered(inst_dir)
        urls_kept = _urls_kept(inst_dir)
        pages_scraped = _pages_scraped(inst_dir)
        extracted_row_count = _extracted_row_count(inst_dir / "extract")

        validate_path = inst_dir / "6_validate.json"
        has_genai_activity: str | None = None
        consolidated_row_count = 0
        if validate_path.exists() and inst_id not in validate_parse_failures:
            payload = json.loads(validate_path.read_text(encoding="utf-8"))
            has_genai_activity = payload.get("institution", {}).get("has_genai_activity")
            consolidated_row_count = len(payload.get("activities", []))
            validation_status = "consolidated"
        elif validate_path.exists():
            validation_status = "failed_to_parse"
        else:
            validation_status = "not_run"

        failures = failures_by_inst.get(inst_id, [])
        attrition_detail = "; ".join(
            f"{f['stage']}:{f['reason']}" + (f" ({f['detail']})" if f.get("detail") else "")
            for f in failures
        ) or None

        error: str | None = None
        if failures or validation_status == "failed_to_parse":
            final_status = "PROCESSING_FAILED"
            if failures:
                reason = attrition_detail
                error = attrition_detail
            else:
                reason = "6_validate.json present but failed schema/contract validation"
                error = reason
        elif stopped_after_stage != "validate":
            final_status = "RUN_TRUNCATED"
            reason = (
                f"run configured with --stop-after {stopped_after_stage!r}; "
                "institution not evaluated past that point"
            )
        elif validation_status == "consolidated":
            if has_genai_activity == "yes" and consolidated_row_count > 0:
                final_status = "EVIDENCE_FOUND"
                reason = (
                    f"has_genai_activity=yes with {consolidated_row_count} "
                    "consolidated activity(ies)"
                )
            else:
                final_status = "NO_EVIDENCE_FOUND"
                reason = f"has_genai_activity={has_genai_activity!r}, 0 qualifying activities"
        else:
            # stop_after == "validate" but nothing reached Stage 6 for this
            # institution, and no failure was recorded. Either it ran out of
            # legitimate upstream input, or the whole run died before the
            # stage that owed it an artifact ever finished. Which one is
            # decided by that stage's .done marker, not assumed.
            if urls_kept == 0:
                blocking_stage, reason = (
                    "classify_triage",
                    "zero URLs passed triage",
                )
            elif pages_scraped == 0:
                blocking_stage, reason = (
                    "scrape",
                    "no pages scraped from kept URLs",
                )
            elif extracted_row_count == 0:
                blocking_stage, reason = (
                    "extract",
                    "pages scraped but nothing extracted",
                )
            else:
                blocking_stage, reason = (
                    "validate",
                    "extracted rows present but nothing reached Stage 6 consolidation",
                )

            if stage_completion is not None and not stage_completion[blocking_stage]:
                final_status = "PROCESSING_FAILED"
                reason = (
                    f"run aborted before stage {blocking_stage!r} completed; this "
                    "institution was still queued and was never evaluated "
                    "(no attrition record of its own)"
                )
                error = reason
            else:
                final_status = "NO_EVIDENCE_FOUND"

        timing = read_timing(run_dir, inst_id) or {}
        stages_timing = timing.get("stages", {})
        start_timestamp = min(
            (s["start_time"] for s in stages_timing.values()), default=None
        )
        end_timestamp = max(
            (s["end_time"] for s in stages_timing.values()), default=None
        )

        records.append(
            {
                "institution_id": inst_id,
                "final_status": final_status,
                "stage_reached": stage_reached,
                "stopped_after_stage": stopped_after_stage,
                "reason": reason,
                "error": error,
                "urls_discovered": urls_discovered,
                "urls_kept": urls_kept,
                "pages_scraped": pages_scraped,
                "extracted_row_count": extracted_row_count,
                "consolidated_row_count": consolidated_row_count,
                "validation_status": validation_status,
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
                "total_runtime_seconds": timing.get("total_duration_seconds"),
            }
        )
    return records


__all__ = ["compute_institution_report"]
