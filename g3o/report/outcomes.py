"""Institution-level final outcome determination — read-only from disk.

Walks a presweep run and assigns each institution exactly one of five final
statuses:

- ``EVIDENCE_FOUND``    — reached Stage 6; ``has_genai_activity == "yes"``
                          with >=1 consolidated activity.
- ``NO_EVIDENCE_FOUND`` — the run was configured to reach Stage 6, **every
                          configured stage completed**, and this institution
                          was genuinely evaluated that far (or ran out of
                          legitimate upstream input, e.g. zero URLs kept by
                          triage) but no qualifying evidence surfaced.
- ``PROCESSING_FAILED`` — a technical failure (an attrition-recorded parse /
                          scrape failure for this institution, or an
                          unreadable ``6_validate.json``) prevented a
                          conclusion.
- ``PROCESSING_INCOMPLETE`` — the run was configured to reach Stage 6 but
                          died before completing it, and this institution has
                          no verdict of its own: it may never have got a turn
                          at all, or got one and was still queued behind a
                          stage the run never finished. Distinct from
                          ``NO_EVIDENCE_FOUND``, which is a substantive
                          result about the institution, and from
                          ``PROCESSING_FAILED``, which names a failure
                          attributed to *this* institution.
- ``RUN_TRUNCATED``     — the run itself was configured to stop before Stage 6
                          (``--stop-after``); this institution was never
                          evaluated for evidence, independent of what its
                          partial artifacts look like.

Whole-run aborts (fixed here). A run that dies mid-flight on an error not
scoped to any one institution — e.g. a ``SerperRequestError`` that aborts
Stage 1a for every institution still queued behind the one that hit it —
leaves those institutions with no attrition record and no ``6_validate.json``.
They used to fall through to ``NO_EVIDENCE_FOUND``. The disk *does* carry a
positive completion record: :func:`g3o.common.run_state.mark_done` writes
``_state/.done/{stage}.json`` when — and only when — a stage finishes for the
whole run, and every one of the eight stages writes one. So a
``NO_EVIDENCE_FOUND`` verdict is only issued when every configured stage
carries its marker; otherwise the institution is ``PROCESSING_INCOMPLETE``,
naming the first stage that never completed.

Scope of the guarantee. This is the *report-side* half: it prevents a
loudly-aborted run from being read off disk as substantive no-evidence. It
does **not** detect silent loss inside a stage that completed and wrote its
marker (e.g. Batch results lost between fetch and persistence) — that needs
run-time reconciliation at the ``run_state`` / ``batch_client`` layer, which
is a separate, unimplemented work item. An institution that *does* carry a
readable ``6_validate.json`` keeps its substantive verdict even in an aborted
run: it was evaluated, and the abort happened elsewhere.

No network calls. Mirrors :mod:`g3o.report.health`'s disk-only-read
convention.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common import attrition as _attrition
from g3o.common.contract import BatchResponse
from g3o.common.run_state import is_done
from g3o.common.timing import read_timing
from g3o.persist.writer import load_consolidated_outputs

# Canonical stage order. Duplicated from g3o.run.presweep.config.STAGES for the
# same reason g3o.report.run_summary._STAGE_ORDER duplicates it: the report
# layer reads runs off disk and must not import the orchestrator.
_STAGE_ORDER: tuple[str, ...] = (
    "discovery_general",
    "classify_official_site",
    "discovery_site_restricted",
    "filter_eligibility",
    "classify_triage",
    "scrape",
    "extract",
    "validate",
)

# Attrition reasons that represent a genuine technical failure, as opposed to
# expected/normal filtering (robots_disallowed, empty_page_dropped,
# page_text_truncated, official_site_unparseable).
_FAILURE_REASONS: frozenset[str] = frozenset(
    {"serper_request_failed", "scrape_failed", "parse_failed"}
)


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _extracted_row_count(extract_dir: Path) -> int:
    """Flattened ContractRow count across every Stage 5 extract file.

    Deliberately a row count, not a file count (g3o.report.health's
    n_extracts is the file count; this is a different, complementary metric
    named extracted_row_count to avoid confusion between the two).
    """
    if not extract_dir.is_dir():
        return 0
    total = 0
    for path in extract_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
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
    scrape_dir = inst_dir / "scrape"
    if scrape_dir.is_dir() and any(scrape_dir.glob("*.json")):
        reached = "scrape"
    extract_dir = inst_dir / "extract"
    if extract_dir.is_dir() and any(extract_dir.glob("*.json")):
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
    scrape_dir = inst_dir / "scrape"
    return sum(1 for _ in scrape_dir.glob("*.json")) if scrape_dir.is_dir() else 0


def _first_incomplete_stage(run_dir: Path, stopped_after_stage: str | None) -> str | None:
    """First configured stage with no ``.done`` marker, or None if all completed.

    The configured set is ``_STAGE_ORDER`` up to and including
    ``stopped_after_stage``; an unrecognised (or missing) value is treated as
    the full ladder, which is the conservative reading — an unknown
    ``stop_after`` must not license a substantive no-evidence verdict.
    """
    if stopped_after_stage in _STAGE_ORDER:
        configured = _STAGE_ORDER[: _STAGE_ORDER.index(stopped_after_stage) + 1]
    else:
        configured = _STAGE_ORDER
    for stage in configured:
        if not is_done(run_dir, stage):
            return stage
    return None


def compute_institution_report(run_dir: str | Path) -> list[dict[str, Any]]:
    """Compute one final-outcome record per institution in the run's sample."""
    run_dir = Path(run_dir)
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

    # Run-level, institution-independent: the first configured stage the run
    # never finished. None ⇒ the run completed everything it was configured to
    # do, so an empty result is a substantive one.
    incomplete_stage = _first_incomplete_stage(run_dir, stopped_after_stage)

    records: list[dict[str, Any]] = []
    for inst_id in institution_ids:
        inst_dir = run_dir / inst_id
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
        elif incomplete_stage is not None:
            # The run was configured to reach Stage 6 but never completed
            # every configured stage, and this institution produced no verdict
            # of its own. Nothing here is a statement about the institution;
            # it is a statement about the run.
            final_status = "PROCESSING_INCOMPLETE"
            never_started = stage_reached is None
            reason = (
                f"run did not complete stage {incomplete_stage!r} (no "
                f"'_state/.done/{incomplete_stage}.json' marker); institution "
                + (
                    "left no artifacts at all — never got a turn"
                    if never_started
                    else f"reached {stage_reached!r} and has no Stage 6 verdict"
                )
            )
        else:
            # stop_after == "validate", every configured stage completed, but
            # nothing reached Stage 6 for this institution and no failure was
            # recorded — a legitimate empty result (ran out of upstream input),
            # not a technical failure.
            final_status = "NO_EVIDENCE_FOUND"
            if urls_kept == 0:
                reason = "zero URLs passed triage"
            elif pages_scraped == 0:
                reason = "no pages scraped from kept URLs"
            elif extracted_row_count == 0:
                reason = "pages scraped but nothing extracted"
            else:
                reason = "extracted rows present but nothing reached Stage 6 consolidation"

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
