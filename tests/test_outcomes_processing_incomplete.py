"""Whole-run-abort misattribution — ``g3o.report.outcomes`` (report side).

A run that dies mid-flight used to leave queued institutions classified
``NO_EVIDENCE_FOUND``: a substantive claim about the institution, produced by
a fact about the run. These tests pin the fix and its boundaries.

The disk signal is :func:`g3o.common.run_state.mark_done`'s
``_state/.done/{stage}.json`` marker — written when, and only when, a stage
completes for the whole run. Every one of the eight stages writes one, so its
absence is a positive record that the run did not finish that stage.

Scope, asserted below as much as the fix itself: this is the *report* side.
It catches a loud abort (no marker). It does not catch silent loss inside a
stage that completed and wrote its marker — that needs run-time reconciliation
in ``run_state`` / ``batch_client``, which is separate, unimplemented work.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from g3o.common import attrition as _attrition
from g3o.common.contract import NA, ConsolidatedInstitutionResponse
from g3o.common.run_state import mark_done
from g3o.report.outcomes import _STAGE_ORDER, compute_institution_report
from g3o.report.run_summary import _FINAL_STATUSES

INST_A = "INST-0000001"
INST_B = "INST-0000002"


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _no_evidence_verdict(institution_id: str) -> dict[str, Any]:
    """A contract-valid ``6_validate.json`` payload with a substantive "no"."""
    return ConsolidatedInstitutionResponse.model_validate(
        {
            "consolidation_metadata": {
                "institution_id": institution_id,
                "n_input_pages": 1,
                "n_input_rows": 1,
                "response_timestamp": "2026-08-02T12:00:00Z",
                "model_label": "gpt-5-nano",
                "notes": "none",
            },
            "institution": {
                "institution_id": institution_id,
                "institution_name": "Test Ministry",
                "country": "Testland",
                "branch_of_government": "executive",
                "level_of_government": "national",
                "has_genai_activity": "no",
                "institution_summary": "No GenAI evidence in supplied texts.",
                "institution_search_languages": "en",
            },
            "activities": [],
            "sources": [
                {
                    "source_id": "S1",
                    "activity_id": NA,
                    "source_url": "https://example.gov/",
                    "source_title": "Home",
                    "source_publication_date": "2025-01",
                    "source_access_date": "2026-08-02",
                    "source_type": "official_gov",
                    "source_language": "en",
                    "source_credibility": "high",
                    "genai_evidence": "confirms_absence",
                    "source_snippet": "Page contains no GenAI mention.",
                }
            ],
        }
    ).model_dump()


def _build_run(
    run_dir: Path,
    *,
    institutions: list[str],
    stop_after: str = "validate",
    stages_done: tuple[str, ...] = (),
) -> None:
    """Manifest + per-institution dirs + the given stages' ``.done`` markers."""
    _write(
        run_dir / "manifest.json",
        {
            "run_id": run_dir.name,
            "institutions": institutions,
            "config": {"stop_after": stop_after},
        },
    )
    for inst_id in institutions:
        (run_dir / inst_id).mkdir(parents=True, exist_ok=True)
    for stage in stages_done:
        mark_done(run_dir, stage, no_batch=True)


def _fully_processed(inst_dir: Path, *, kept: int = 0) -> None:
    """Artifacts of an institution that genuinely ran out of upstream input:
    discovery returned URLs, triage kept ``kept`` of them, nothing downstream."""
    _write(
        inst_dir / "1a_discovery_general.json",
        {"records": [{"url": "https://example.gov/a"}]},
    )
    _write(
        inst_dir / "3_triage.json",
        {
            "decisions": [
                {"url": "https://example.gov/a", "decision": "keep" if kept else "drop"}
            ]
        },
    )


def _by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["institution_id"]: r for r in records}


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------


def test_whole_run_abort_is_not_read_as_no_evidence(tmp_path: Path):
    """The regression case: a run that died at Stage 1a. The institution has
    no artifacts, no attrition record, and no verdict — the exact shape that
    used to read as ``NO_EVIDENCE_FOUND``."""
    run_dir = tmp_path / "aborted-run"
    _build_run(run_dir, institutions=[INST_A], stages_done=())

    record = compute_institution_report(run_dir)[0]

    assert record["final_status"] != "NO_EVIDENCE_FOUND"
    assert record["final_status"] == "PROCESSING_INCOMPLETE"
    assert "discovery_general" in record["reason"]
    assert "never got a turn" in record["reason"]
    assert record["stage_reached"] is None


def test_abort_after_a_turn_names_the_stage_the_run_did_not_finish(tmp_path: Path):
    """An institution that *did* get a turn but sat behind a stage the run never
    finished is equally unprocessed — and the reason says which stage."""
    run_dir = tmp_path / "abort-midway"
    _build_run(
        run_dir,
        institutions=[INST_A],
        stages_done=("discovery_general", "classify_official_site"),
    )
    _write(
        run_dir / INST_A / "1a_discovery_general.json",
        {"records": [{"url": "https://example.gov/a"}]},
    )

    record = compute_institution_report(run_dir)[0]

    assert record["final_status"] == "PROCESSING_INCOMPLETE"
    assert "discovery_site_restricted" in record["reason"]
    assert "never got a turn" not in record["reason"]
    assert record["stage_reached"] == "discovery_general"


def test_zero_urls_passed_triage_is_not_claimed_when_triage_never_ran(tmp_path: Path):
    """The old reason string for this shape was 'zero URLs passed triage' — a
    statement about a stage that never executed."""
    run_dir = tmp_path / "abort-before-triage"
    _build_run(run_dir, institutions=[INST_A], stages_done=("discovery_general",))

    record = compute_institution_report(run_dir)[0]

    assert "zero URLs passed triage" not in record["reason"]


# ---------------------------------------------------------------------------
# What must NOT change
# ---------------------------------------------------------------------------


def test_completed_run_still_yields_substantive_no_evidence(tmp_path: Path):
    """Every configured stage completed ⇒ an empty result is a real result."""
    run_dir = tmp_path / "complete-run"
    _build_run(run_dir, institutions=[INST_A], stages_done=_STAGE_ORDER)
    _fully_processed(run_dir / INST_A, kept=0)

    record = compute_institution_report(run_dir)[0]

    assert record["final_status"] == "NO_EVIDENCE_FOUND"
    assert record["reason"] == "zero URLs passed triage"


def test_an_institution_with_a_verdict_keeps_it_in_an_aborted_run(tmp_path: Path):
    """The abort happened elsewhere. This institution was evaluated; its Stage 6
    verdict is a substantive result and survives."""
    run_dir = tmp_path / "abort-after-some-verdicts"
    _build_run(
        run_dir,
        institutions=[INST_A, INST_B],
        stages_done=tuple(s for s in _STAGE_ORDER if s != "validate"),
    )
    _write(run_dir / INST_A / "6_validate.json", _no_evidence_verdict(INST_A))

    records = _by_id(compute_institution_report(run_dir))

    assert records[INST_A]["final_status"] == "NO_EVIDENCE_FOUND"
    assert records[INST_B]["final_status"] == "PROCESSING_INCOMPLETE"


def test_attributed_failure_still_outranks_incomplete(tmp_path: Path):
    """``PROCESSING_FAILED`` names a failure attributed to *this* institution;
    ``PROCESSING_INCOMPLETE`` names one that is not. The attributed one wins."""
    run_dir = tmp_path / "abort-with-attributed-failure"
    _build_run(run_dir, institutions=[INST_A], stages_done=())
    _attrition.record(
        run_dir,
        institution_id=INST_A,
        stage="discovery_general",
        reason="serper_request_failed",
        detail="HTTP 503",
    )

    record = compute_institution_report(run_dir)[0]

    assert record["final_status"] == "PROCESSING_FAILED"


def test_stop_after_still_wins_over_incomplete(tmp_path: Path):
    """A deliberately truncated run is not an incomplete one — the operator
    asked for it, and ``RUN_TRUNCATED`` already says so."""
    run_dir = tmp_path / "truncated-run"
    _build_run(
        run_dir,
        institutions=[INST_A],
        stop_after="classify_triage",
        stages_done=_STAGE_ORDER[:5],
    )

    record = compute_institution_report(run_dir)[0]

    assert record["final_status"] == "RUN_TRUNCATED"


# ---------------------------------------------------------------------------
# Boundaries of the disk signal
# ---------------------------------------------------------------------------


def test_unknown_stop_after_is_read_conservatively(tmp_path: Path):
    """An unrecognised ``stop_after`` must not license a no-evidence verdict.
    (It routes to ``RUN_TRUNCATED`` today; this pins that it never routes to
    ``NO_EVIDENCE_FOUND`` on the strength of an unparseable config.)"""
    run_dir = tmp_path / "odd-stop-after"
    _build_run(
        run_dir, institutions=[INST_A], stop_after="not-a-stage", stages_done=()
    )

    record = compute_institution_report(run_dir)[0]

    assert record["final_status"] != "NO_EVIDENCE_FOUND"


def test_a_completed_stage_marker_is_taken_at_face_value(tmp_path: Path):
    """States the limit explicitly: silent loss inside a stage that finished and
    wrote its marker is invisible to the report side and reads as a substantive
    result. Closing this needs run-time reconciliation, not a disk read."""
    run_dir = tmp_path / "silent-loss"
    _build_run(run_dir, institutions=[INST_A], stages_done=_STAGE_ORDER)
    _fully_processed(run_dir / INST_A, kept=1)
    (run_dir / INST_A / "scrape").mkdir()
    _write(run_dir / INST_A / "scrape" / "page.json", {"url": "https://example.gov/a"})

    record = compute_institution_report(run_dir)[0]

    assert record["final_status"] == "NO_EVIDENCE_FOUND"
    assert record["reason"] == "pages scraped but nothing extracted"


# ---------------------------------------------------------------------------
# Consumer sync
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["PROCESSING_INCOMPLETE"])
def test_run_summary_counts_every_status_outcomes_can_emit(status: str):
    """``compute_run_summary`` drops any status missing from ``_FINAL_STATUSES``
    without a word (``if status in final_status_counts``), so the two must not
    drift."""
    assert status in _FINAL_STATUSES
