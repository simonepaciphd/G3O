"""Institution-level final outcome determination — read-only from disk.

Walks a presweep run and assigns each institution exactly one of five final
statuses:

- ``EVIDENCE_FOUND``    — reached Stage 6; ``has_genai_activity == "yes"``
                          with >=1 consolidated activity, and no technical
                          failure on the way.
- ``EVIDENCE_FOUND_PARTIAL``
                          — the same conclusion, reached over an incomplete
                          search: >=1 URL for this institution failed to fetch
                          or parse. The evidence is real; the count is a floor.
                          Added 2026-08-31, and it is not a new category so much
                          as the recovery of one that was being discarded — see
                          the branch comment in
                          :func:`compute_institution_outcomes`. Measured at
                          23.8%-33.3% of every run's positives, all of which
                          previously reported ``PROCESSING_FAILED``.
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
                          conclusion. Also carries a v2.7 institution held as
                          pending by the per-page stage or Stage 6 (ruling
                          45 a): not concluded, and the reason names the hold
                          — see :func:`_v27_hold_reason`. Also a v2.7
                          institution whose verdict is ``unclear`` (ruling
                          48.1 b) or whose ``6_validate.json`` has no
                          ``6_storage.json`` (ruling 48.2 a).
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

v2.7 runs
---------

A run is v2.7 when its manifest records ``config.pipeline_version == "v2.7"``
or ``storage_contract.codebook_release == "2.7"`` (:func:`_is_v27_run`). An
institution's ``6_validate.json`` is v2.7 when it parses as the v2.7 response
(identity and row keys only); its verdict is then read from the
``6_storage.json`` summary row, ``core.has_genai_activity`` (ruling 48.1 b).
The v2.7 per-page stage and v2.7 Stage 6 replace Stages 5/6 and write their own
markers (ruling 48.3 a), which stand in for ``extract`` and ``validate``.

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
from g3o.common.paths import institution_dir, institution_uid_map, require_layout
from g3o.common.response_v27 import ConsolidatedInstitutionResponseV27
from g3o.common.run_state import is_done, state_dir
from g3o.common.timing import read_timing
from g3o.persist.writer import load_consolidated_outputs

# Attrition reasons that represent a genuine technical failure, as opposed to
# expected/normal filtering (robots_disallowed, empty_page_dropped,
# page_text_truncated, official_site_unparseable).
#
# ``crawl_delay_exceeded`` (issue #96, PI ruling 2026-08-26) is a technical
# failure by that test and joins the set. Stage 4 gives each institution a
# wall-clock budget and skips the URLs it cannot reach inside it, so one host
# declaring ``Crawl-delay: 8640`` can no longer hold the stage open; the ruling
# was that the skip must be *named*, and this membership is what makes the name
# mean something. Without it the institution would carry ledger rows saying "we
# never fetched these" and still report NO_EVIDENCE_FOUND — "could not reach"
# published as "searched and found nothing", the #17 defect class, made more
# convincing by the post-#17 tightening of ``none``. The accepted cost, named
# and ruled on: a larger PROCESSING_FAILED bucket.
#
# Note this is deliberately sticky across a resume, exactly as ``scrape_failed``
# already is. An institution that hits the budget, then reaches every URL on a
# later pass, keeps its rows (the ledger is append-only and never rewritten) and
# still reads PROCESSING_FAILED. That errs toward reporting failure, which is
# the safe direction here, and it is the ledger's existing semantics rather than
# a new behaviour introduced with this reason.
_FAILURE_REASONS: frozenset[str] = frozenset(
    {
        "serper_request_failed",
        "scrape_failed",
        "parse_failed",
        "crawl_delay_exceeded",
        # Per-host circuit breaker (PI-approved 2026-09-06). A URL skipped
        # because its host already failed at connect level N times this run
        # is "could not reach" exactly as a budget expiry is, and for the same
        # reason it must be a member here: outside this frozenset the skip is
        # on the ledger and the institution publishes as NO_EVIDENCE_FOUND.
        "host_unreachable",
        # PI ruling E2=a (2026-10-17). A jev request that failed at triage or
        # validate left the institution without a conclusion; outside this
        # set it published as NO_EVIDENCE_FOUND. Scoped to those two stages
        # (Stage 2 jev failures keep their prior meaning) and NOT sticky
        # across a resume: see _JEV_STAGE_ARTIFACTS.
        "jev_request_failed",
    }
)

# Stages whose jev_request_failed rows count as failures, each with the
# artifact that supersedes the row once written (a resumed run that
# succeeded): the later success wins over the stale failure row.
_JEV_STAGE_ARTIFACTS: dict[str, str] = {
    "classify_triage": "3_triage.json",
    "validate": "6_validate.json",
}


def _is_ignored_jev_failure(rec: dict[str, Any], inst_dir: Path) -> bool:
    """True for a jev_request_failed row that must not count as a failure:
    from a stage outside E2's scope, or superseded by that stage's artifact."""
    if rec.get("reason") != "jev_request_failed":
        return False
    artifact = _JEV_STAGE_ARTIFACTS.get(rec.get("stage", ""))
    return artifact is None or (inst_dir / artifact).exists()


# v2.7 holds (ruling 45 a). The per-page stage and v2.7 Stage 6 hold an
# institution as pending by writing ``<work dir>/held.json`` and delete that file
# when the hold clears (after appending a ``*_held_released`` ledger record).
# The file, not the ledger, is the authoritative signal: the ledger dedups on
# (institution, stage, reason, url), so a second hold after a release is never
# appended and the ledger's last word would read "released" for an institution
# that is held again. Mirrors ``stage_perpage_v27.WORK_DIR`` / ``HELD_FILE`` and
# ``stage_validate_v27.WORK_DIR`` / ``HELD_FILE`` (pinned by a test; not imported,
# so this disk-only reader does not load the run stages).
_V27_HOLDS: tuple[tuple[str, str], ...] = (
    ("perpage_v27", "the v2.7 per-page stage"),
    ("stage6_v27", "v2.7 Stage 6"),
)
_V27_HELD_FILE = "held.json"


def _v27_hold_labels(work_dir: str, payload: dict[str, Any]) -> list[str]:
    if work_dir == "perpage_v27":
        return [
            f"{h.get('page_id')}:{h.get('stage')}"
            for h in payload.get("held", [])
            if isinstance(h, dict)
        ]
    return [str(r) for r in payload.get("reasons", [])]


def _v27_hold_reason(inst_dir: Path) -> str | None:
    """Why a v2.7 institution is held as pending (ruling 45 a), or None if it is not.

    One clause per stage whose ``held.json`` exists, naming the stage and the
    hold labels it records (per-page: ``page_id:stage``; Stage 6: its hold
    reasons). An unreadable ``held.json`` still holds the institution.
    """
    clauses: list[str] = []
    for work_dir, stage_label in _V27_HOLDS:
        path = inst_dir / work_dir / _V27_HELD_FILE
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_bytes().decode("utf-8"))
            labels = _v27_hold_labels(work_dir, payload) if isinstance(payload, dict) else []
            detail = ", ".join(labels) or "no hold label recorded"
        except (OSError, ValueError) as exc:  # UnicodeDecodeError is a ValueError
            detail = f"{work_dir}/{_V27_HELD_FILE} unreadable: {type(exc).__name__}"
        clauses.append(f"held as pending at {stage_label} ({work_dir}: {detail})")
    if not clauses:
        return None
    return "; ".join(clauses) + "; not concluded, a later run retries it"


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


# Ruling 48.3 a: the v2.7 per-page stage and v2.7 Stage 6 write their own
# completion markers, named apart from v2.5's (v2.7 Stage 6's attrition stage is
# ``validate``, so its marker could not reuse that name). In a v2.7 run they
# stand in for ``extract`` and ``validate``. Mirrors
# ``stage_perpage_v27.DONE_MARKER`` / ``stage_validate_v27.DONE_MARKER`` (pinned
# by a test; not imported, as for the hold paths above).
_V27_MARKERS: dict[str, str] = {
    "extract": "perpage_v27",
    "validate": "stage6_v27",
}


def _is_v27_run(manifest: dict[str, Any]) -> bool:
    """True when the run folder's manifest records a v2.7 run.

    ``config.pipeline_version`` is written when the run is planned;
    ``storage_contract.codebook_release`` once the v2.7 stages bind the
    instrument. Either is enough, so a v2.7 run that stopped before the
    per-page stage still reads its (absent) v2.7 markers.
    """
    config = manifest.get("config") or {}
    contract = manifest.get("storage_contract") or {}
    return config.get("pipeline_version") == "v2.7" or contract.get("codebook_release") == "2.7"


def _stage_completion(run_dir: Path, *, v27: bool = False) -> dict[str, bool] | None:
    """Which stages the *run* finished, per ``_state/.done/`` (Q3=e2).

    Returns ``None`` when the run carries no ``_state/`` directory at all —
    a run predating the state machinery, or a hand-built fixture. That is an
    absence of evidence, not evidence of an abort, so callers fall back to the
    permissive reading rather than manufacturing a failure.

    With ``v27`` the ``extract`` and ``validate`` entries read the v2.7 stages'
    markers (:data:`_V27_MARKERS`, ruling 48.3 a).
    """
    if not state_dir(run_dir).exists():
        return None
    markers = _V27_MARKERS if v27 else {}
    return {stage: is_done(run_dir, markers.get(stage, stage)) for stage in _STAGES_WITH_MARKERS}


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
    for fname in (
        "1a_discovery_general.json",
        "1b_discovery_site_restricted.json",
        "1d_discovery_evidence_open.json",
    ):
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
    # institution_report.csv is written by a generic
    # ``{col: r.get(col) for col in INSTITUTION_REPORT_COLUMNS}`` comprehension,
    # so a column the records never carry ships as an empty cell and no error.
    # Read the uid map through the raising accessor for that reason: this is
    # the one stamped surface with no structural guard behind it.
    uid_by_inst = institution_uid_map(run_dir)

    ledger = _attrition.read_records(run_dir)
    failures_by_inst: dict[str, list[dict[str, Any]]] = {}
    for rec in ledger:
        if rec.get("reason") in _FAILURE_REASONS:
            failures_by_inst.setdefault(rec.get("institution_id", ""), []).append(rec)

    # Ruling 48.2 a: a v2.7 6_validate.json without its 6_storage.json is
    # collected here (nothing recorded) and decided for that institution alone;
    # Stage 7 passes no list and still refuses it.
    missing_storage: list[str] = []
    loaded, validate_parse_failures = load_consolidated_outputs(
        run_dir, missing_storage=missing_storage
    )
    validate_parse_failures = set(validate_parse_failures)
    missing_storage_ids = set(missing_storage)
    # Ruling 48.1 b: a v2.7 6_validate.json carries no verdict; it is the
    # storage summary row's core.has_genai_activity. Only the verdicts are kept.
    v27_verdicts: dict[str, str] = {
        li.institution_id: li.storage.data["summary"]["values"]["core.has_genai_activity"]
        for li in loaded
        if isinstance(li.response, ConsolidatedInstitutionResponseV27) and li.storage is not None
    }
    del loaded

    v27_run = _is_v27_run(manifest)
    stage_completion = _stage_completion(run_dir, v27=v27_run)

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
        if validate_path.exists() and inst_id in missing_storage_ids:
            validation_status = "storage_missing"  # ruling 48.2 a
        elif validate_path.exists() and inst_id not in validate_parse_failures:
            payload = json.loads(validate_path.read_text(encoding="utf-8"))
            if inst_id in v27_verdicts:  # ruling 48.1 b
                has_genai_activity = v27_verdicts[inst_id]
            else:
                has_genai_activity = payload.get("institution", {}).get("has_genai_activity")
            consolidated_row_count = len(payload.get("activities", []))
            validation_status = "consolidated"
        elif validate_path.exists():
            validation_status = "failed_to_parse"
        else:
            validation_status = "not_run"

        failures = [
            f
            for f in failures_by_inst.get(inst_id, [])
            if not _is_ignored_jev_failure(f, inst_dir)
        ]
        attrition_detail = "; ".join(
            f"{f['stage']}:{f['reason']}" + (f" ({f['detail']})" if f.get("detail") else "")
            for f in failures
        ) or None

        error: str | None = None
        concluded_positive = (
            validation_status == "consolidated"
            and has_genai_activity == "yes"
            and consolidated_row_count > 0
        )
        # A v2.7 institution that reached Stage 6 output but is not concluded.
        v27_open: str | None = None
        if validation_status == "storage_missing":  # ruling 48.2 a
            v27_open = (
                "v2.7 6_validate.json present but its 6_storage.json is missing; "
                "verdict not read, not concluded"
            )
        elif inst_id in v27_verdicts and has_genai_activity == "unclear":  # ruling 48.1 b
            v27_open = "has_genai_activity='unclear' (v2.7 verdict unclear; not concluded)"
        held_reason = _v27_hold_reason(inst_dir)
        if held_reason is not None:
            # Ruling 45 a: a v2.7 institution held as pending is not concluded.
            # Checked first: v2.7 writes no extract/ folder, and its stages write
            # their .done markers once the whole pass finishes, held
            # institutions included (ruling 48.3 a), so below it would read as
            # finished with nothing found and publish as NO_EVIDENCE_FOUND, or
            # as PROCESSING_FAILED with a false "run aborted" reason.
            final_status = "PROCESSING_FAILED"
            reason = held_reason + (f"; {attrition_detail}" if attrition_detail else "")
            error = reason
        elif failures and concluded_positive:
            # EVIDENCE_FOUND_PARTIAL, 2026-08-31. Measured on five runs: this
            # branch is 23.8%–33.3% of every run's positives — 104 of 437 on
            # ``r20260830T114940Z-32ea``, 439 institutions across the five —
            # and before it existed all of them reported PROCESSING_FAILED.
            #
            # The precedence below (any failure row wins) is right for negatives
            # and wrong for positives, and the asymmetry is the whole argument.
            # For a negative it stops "could not reach" being published as
            # "searched and found nothing" — the #17 defect class. For an
            # institution that consolidated ``yes`` with N activities it does
            # the opposite: that institution was, definitionally, reached, and
            # calling it a processing failure suppresses a positive rather than
            # guarding against a false negative. One failed URL out of nine was
            # enough (INST-0703416: one ``download_error``, one consolidated
            # activity, reported PROCESSING_FAILED).
            #
            # ``g3o-api`` already resolved this the other way and has all
            # along: ``sql/001_aggregates.sql`` computes ``documented`` from
            # ``yes_count``, not from ``outcome_status``, reasoning that "an
            # incomplete search does not un-find it". So this is a
            # reconciliation of the report to the database, not a new policy —
            # the two repos disagreed and the database was right.
            #
            # The partial status is kept distinct from EVIDENCE_FOUND rather
            # than merged into it because the distinction is real: this
            # institution's evidence is a floor, not a measurement. Anything
            # counting positives should count both; anything reasoning about
            # completeness of search must not.
            final_status = "EVIDENCE_FOUND_PARTIAL"
            reason = (
                f"has_genai_activity=yes with {consolidated_row_count} "
                f"consolidated activity(ies), but the search was incomplete: "
                f"{attrition_detail}"
            )
            error = attrition_detail
        elif failures or validation_status == "failed_to_parse" or v27_open is not None:
            final_status = "PROCESSING_FAILED"
            if v27_open is not None:
                # Rulings 48.1 b / 48.2 a: v2.7 only; an unclear verdict is not
                # NO_EVIDENCE_FOUND as in v2.5. Attrition failures are kept.
                reason = v27_open + (f"; {attrition_detail}" if attrition_detail else "")
                error = reason
            elif failures:
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
            elif v27_run:
                # Ruling 48.3 a with 37 a: v2.7 leaves no extract rows, so the
                # per-page marker stands in for extract and Stage 6's for
                # validate. An unheld institution with pages is concluded only
                # once both stages finished: one the per-page stage passed on
                # can still be queued behind a Stage 6 stop.
                if stage_completion is not None and not stage_completion["extract"]:
                    blocking_stage, reason = (
                        "extract",
                        "pages scraped but the v2.7 per-page stage did not finish",
                    )
                else:
                    blocking_stage, reason = (
                        "validate",
                        "pages scraped but no v2.7 Stage 6 output or hold for this institution",
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
                if v27_run:  # name the v2.7 stage whose marker is missing
                    blocking_stage = _V27_MARKERS.get(blocking_stage, blocking_stage)
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

        institution_uid = uid_by_inst.get(inst_id, "")
        if not institution_uid:
            raise RuntimeError(
                f"{inst_id} is in the manifest's institution list but carries no "
                "institution_uid, so its report row cannot be stamped"
            )

        records.append(
            {
                "institution_uid": institution_uid,
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
