"""Tests for g3o.report.outcomes — per-institution final status from disk.

Focus is the whole-run-abort attribution (status doc §5.3 / §6 item 10): an
institution still queued when the run died must not be reported as
``NO_EVIDENCE_FOUND``, which asserts the pipeline looked and found nothing.
The discriminator is the resume machinery's ``_state/.done/{stage}.json``
marker, so most of these tests differ only in which markers exist.

Disk-only; no network, no Batch API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from g3o.common import attrition as _attrition
from g3o.common.run_state import done_path, state_dir
from g3o.report import outcomes
from tests._layout import (
    inst_dir as inst_dir_of,
)
from tests._layout import (
    write_manifest,
)

ALL_STAGES = ("classify_triage", "scrape", "extract", "validate")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_run(
    run_dir: Path,
    *,
    institutions: list[str],
    stop_after: str = "validate",
    done: tuple[str, ...] = (),
    with_state_dir: bool = True,
) -> None:
    """Build a run directory carrying only what outcomes.py reads."""
    _attrition._reset_cache()
    write_manifest(
        run_dir,
        {
            "run_id": "test-outcomes",
            "run_date": "2026-08-02",
            "institutions": institutions,
            "config": {"stop_after": stop_after},
        },
    )
    if with_state_dir:
        state_dir(run_dir).mkdir(parents=True, exist_ok=True)
    for stage in done:
        _write(done_path(run_dir, stage), {"stage": stage, "no_batch": True})


def _discovery(run_dir: Path, inst_id: str, n_urls: int = 3) -> None:
    _write(
        inst_dir_of(run_dir, inst_id) / "1a_discovery_general.json",
        {"records": [{"link": f"https://x{i}.gov/"} for i in range(n_urls)]},
    )


def _triage(run_dir: Path, inst_id: str, *, keeps: int, drops: int = 2) -> None:
    decisions = [{"decision": "keep", "url": f"https://x{i}.gov/"} for i in range(keeps)]
    decisions += [{"decision": "drop", "url": f"https://y{i}.gov/"} for i in range(drops)]
    _write(inst_dir_of(run_dir, inst_id) / "3_triage.json", {"decisions": decisions})


def _scraped(run_dir: Path, inst_id: str, n_pages: int = 2) -> None:
    for i in range(n_pages):
        _write(
            inst_dir_of(run_dir, inst_id) / "scrape" / f"hash{i}.json",
            {"url": f"https://x{i}.gov/"},
        )


def _validated(run_dir: Path, inst_id: str, *, has_genai: str, n_activities: int) -> None:
    """A Stage 6 artifact that really validates as a ConsolidatedInstitutionResponse.

    A stub does not do: load_consolidated_outputs would reject it and the
    institution would come back PROCESSING_FAILED for the wrong reason,
    passing the abort tests vacuously.
    """
    _write(
        inst_dir_of(run_dir, inst_id) / "6_validate.json",
        {
            "consolidation_metadata": {
                "institution_id": inst_id,
                "n_input_pages": 2,
                "n_input_rows": 2,
                "response_timestamp": "2026-08-02T12:00:00Z",
                "model_label": "gpt-5-nano",
                "notes": "fixture",
            },
            "institution": {
                "institution_id": inst_id,
                "institution_name": f"Institution {inst_id}",
                "country": "TESTLAND",
                "branch_of_government": "executive",
                "level_of_government": "national",
                "has_genai_activity": has_genai,
                "institution_summary": "summary",
                "institution_search_languages": "en",
            },
            "activities": [
                {
                    "activity_id": f"A{i + 1}",
                    "activity_name": f"Activity {i + 1}",
                    "activity_type": "internal_operational",
                    "adoption_stage": "pilot",
                    "access_type": "proprietary_vendor",
                    "interaction_type": "document_processing",
                    "tool_name": "Tool",
                    "vendor": "Vendor",
                    "deployment_mode": "integrated",
                    "target_users": "internal_staff",
                    "year_announced": "2025",
                    "year_deployed": "2025",
                    "has_human_oversight": "yes",
                    "has_transparency_notice": "no",
                    "has_data_classification": "yes",
                    "has_risk_assessment": "yes",
                    "reported_outcomes": "none_reported",
                    "reported_incidents": "none_reported",
                    "scope_notes": "fixture",
                    "n_sources": 1,
                    "confidence": "high",
                    "uncertainty_flags": "none",
                }
                for i in range(n_activities)
            ],
            # Every ConsolidatedActivity must be backed by >=1 source, so this
            # is one source per activity, or a single _NA_ source when there
            # are none.
            "sources": [
                {
                    "source_id": f"S{i + 1}",
                    "activity_id": f"A{i + 1}" if n_activities else "_NA_",
                    "source_url": f"https://x{i}.gov/",
                    "source_title": "Fixture page",
                    "source_publication_date": "2025-01",
                    "source_access_date": "2026-08-02",
                    "source_type": "official_gov",
                    "source_language": "en",
                    "source_credibility": "high",
                    "genai_evidence": (
                        "confirms_activity" if n_activities else "confirms_absence"
                    ),
                    "source_snippet": "fixture",
                }
                for i in range(max(n_activities, 1))
            ],
        },
    )


def _only(run_dir: Path) -> dict[str, Any]:
    records = outcomes.compute_institution_report(run_dir)
    assert len(records) == 1
    return records[0]


# ---------------------------------------------------------------------------
# The defect: a queued institution in an aborted run
# ---------------------------------------------------------------------------


def test_run_aborted_before_triage_is_processing_failed(tmp_path: Path) -> None:
    """Died during discovery. The institution never got a turn at triage."""
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=())
    _discovery(run_dir, "INST-0000001")

    rec = _only(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"
    assert "run aborted" in rec["reason"]
    assert "classify_triage" in rec["reason"]
    assert rec["error"] == rec["reason"]


def test_kept_urls_but_scrape_never_finished_is_processing_failed(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=("classify_triage",))
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=4)

    rec = _only(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"
    assert "'scrape'" in rec["reason"]


def test_scraped_but_extract_never_finished_is_processing_failed(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=("classify_triage", "scrape"))
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=4)
    _scraped(run_dir, "INST-0000001")

    rec = _only(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"
    assert "'extract'" in rec["reason"]


def test_extracted_but_validate_never_finished_is_processing_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "run"
    _make_run(
        run_dir,
        institutions=["INST-0000001"],
        done=("classify_triage", "scrape", "extract"),
    )
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=4)
    _scraped(run_dir, "INST-0000001")
    # A real extract file has to be a full Output Contract BatchResponse, whose
    # builder lives in test_contract.py; this repo has no cross-test imports and
    # the branch under test does not care how the row count was derived.
    monkeypatch.setattr(outcomes, "_extracted_row_count", lambda _dir: 5)

    rec = _only(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"
    assert "'validate'" in rec["reason"]


# ---------------------------------------------------------------------------
# Precision: completed stages still yield genuine findings
# ---------------------------------------------------------------------------


def test_completed_run_zero_keeps_is_no_evidence(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=0)

    rec = _only(run_dir)
    assert rec["final_status"] == "NO_EVIDENCE_FOUND"
    assert rec["reason"] == "zero URLs passed triage"
    assert rec["error"] is None


def test_zero_keeps_survives_a_later_abort(tmp_path: Path) -> None:
    """The precision case the fix must not over-claim.

    Triage completed and kept nothing for this institution. The run then died
    during scrape. This institution genuinely got its turn and genuinely found
    nothing — the later abort is irrelevant to it, and reclassifying it would
    trade one misattribution for another.
    """
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=("classify_triage",))
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=0)

    rec = _only(run_dir)
    assert rec["final_status"] == "NO_EVIDENCE_FOUND"
    assert rec["reason"] == "zero URLs passed triage"


def test_evidence_found_unaffected_by_a_run_that_aborted_for_others(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001", "INST-0000002"], done=("classify_triage",))
    # 1 finished all the way through before the run died.
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=2)
    _scraped(run_dir, "INST-0000001")
    _validated(run_dir, "INST-0000001", has_genai="yes", n_activities=2)
    # 2 was still queued.
    _discovery(run_dir, "INST-0000002")
    _triage(run_dir, "INST-0000002", keeps=2)

    by_id = {r["institution_id"]: r for r in outcomes.compute_institution_report(run_dir)}
    assert by_id["INST-0000001"]["final_status"] == "EVIDENCE_FOUND"
    assert by_id["INST-0000002"]["final_status"] == "PROCESSING_FAILED"


def test_consolidated_no_is_still_no_evidence_in_an_aborted_run(tmp_path: Path) -> None:
    """Reaching Stage 6 with has_genai_activity=no is a finding, not an abort."""
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=("classify_triage",))
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=2)
    _scraped(run_dir, "INST-0000001")
    _validated(run_dir, "INST-0000001", has_genai="no", n_activities=0)

    rec = _only(run_dir)
    assert rec["final_status"] == "NO_EVIDENCE_FOUND"
    assert "has_genai_activity='no'" in rec["reason"]


# ---------------------------------------------------------------------------
# Precedence and back-compatibility
# ---------------------------------------------------------------------------


def test_recorded_attrition_failure_still_wins_over_the_abort_reason(tmp_path: Path) -> None:
    """A failure scoped to this institution is the more specific explanation."""
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=("classify_triage",))
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=2)
    _attrition.record(
        run_dir,
        institution_id="INST-0000001",
        stage="scrape",
        reason="scrape_failed",
        url="https://x0.gov/",
        detail="connection timeout",
    )

    rec = _only(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"
    assert "scrape:scrape_failed" in rec["reason"]
    assert "run aborted" not in rec["reason"]


def test_truncated_run_still_reports_run_truncated(tmp_path: Path) -> None:
    """--stop-after short of validate keeps its own status; scope note in the
    module docstring says this deliberately is not split further."""
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], stop_after="extract", done=())
    _discovery(run_dir, "INST-0000001")

    rec = _only(run_dir)
    assert rec["final_status"] == "RUN_TRUNCATED"


def test_missing_state_dir_keeps_the_permissive_reading(tmp_path: Path) -> None:
    """A run predating the state machinery, or a hand-built fixture: absence of
    evidence must not be read as evidence of an abort."""
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=(), with_state_dir=False)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=0)
    assert not state_dir(run_dir).exists()

    rec = _only(run_dir)
    assert rec["final_status"] == "NO_EVIDENCE_FOUND"
    assert rec["reason"] == "zero URLs passed triage"


def test_stage_completion_returns_none_without_a_state_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert outcomes._stage_completion(run_dir) is None


def test_stage_completion_reads_markers(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=[], done=("classify_triage", "scrape"))
    completion = outcomes._stage_completion(run_dir)
    assert completion == {
        "classify_triage": True,
        "scrape": True,
        "extract": False,
        "validate": False,
    }


# ---------------------------------------------------------------------------
# The Stage 4 wall-clock budget (issue #96, PI ruling 2026-08-26)
# ---------------------------------------------------------------------------


def test_budget_expired_institution_is_processing_failed_not_no_evidence(
    tmp_path: Path,
) -> None:
    """The ruling's whole point, and the test that would have caught the
    rejected option.

    The run completed cleanly — every stage marker is present — so nothing
    about the *run* explains this institution's empty result. It kept URLs,
    scraped nothing, and reached Stage 6 with no verdict. On the pre-#96
    reading that is a textbook ``NO_EVIDENCE_FOUND``: the pipeline looked and
    found nothing. It is not. Stage 4 ran out of its per-institution budget and
    never fetched those URLs, and ``crawl_delay_exceeded``'s membership in
    ``_FAILURE_REASONS`` is the only thing standing between that and publishing
    "could not reach" as "searched and found nothing" — the #17 defect class,
    made *more* convincing by the post-#17 tightening of ``none``.

    Budget-then-skip **without** this membership is precisely the silent option
    the PI rejected, and deleting ``crawl_delay_exceeded`` from the frozenset
    is what would fail here.
    """
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=3)
    for i in range(3):
        _attrition.record(
            run_dir,
            institution_id="INST-0000001",
            stage="scrape",
            reason="crawl_delay_exceeded",
            url=f"https://x{i}.gov/",
            detail="budget=3600s;elapsed=1.5s;crawl_delay=8640s",
        )

    rec = _only(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"
    assert rec["final_status"] != "NO_EVIDENCE_FOUND"
    assert "scrape:crawl_delay_exceeded" in rec["reason"]
    # An operator reading the report can see why, without opening the ledger.
    assert "crawl_delay=8640s" in rec["reason"]
    assert rec["error"] == rec["reason"]


def test_crawl_delay_exceeded_is_a_failure_reason() -> None:
    """Pinned directly, not only through the report.

    The membership is load-bearing policy rather than an implementation detail:
    a reason outside this frozenset is on the ledger and invisible to the
    report's failure tally, which is the outcome the ruling exists to prevent.
    """
    assert "crawl_delay_exceeded" in outcomes._FAILURE_REASONS


def test_a_budget_expiry_alongside_real_evidence_still_reports_the_failure(
    tmp_path: Path,
) -> None:
    """The accepted cost, stated so it is not mistaken for a defect later.

    An institution that reached Stage 6 with a genuine positive verdict but also
    lost URLs to the budget is **flagged as incompletely searched rather than
    published as a clean result** — which is what the #96 ruling requires and
    what this test has always been about.

    **Revised 2026-08-31: the status is now EVIDENCE_FOUND_PARTIAL, not
    PROCESSING_FAILED.** The ruling's substance is unchanged and is still
    asserted below — the failure reason is named in the record, and the row does
    not read as a clean result. What changed is that the old label discarded a
    second true fact while asserting the first: it erased that the institution
    was a positive at all. Measured across five runs, that cost 23.8%-33.3% of
    every run's positives (104 of 437 on ``r20260830T114940Z-32ea``), and
    ``g3o-api`` had already declined to follow the report here —
    ``sql/001_aggregates.sql`` computes ``documented`` from ``yes_count``, not
    ``outcome_status``, because "an incomplete search does not un-find it".

    So this is a relabelling that keeps both facts, not a relaxation of the
    ruling. The larger-bucket cost the PI accepted was accepted *for negatives*,
    where reporting failure is the cautious direction; for a positive it is not
    cautious, it is lossy.
    """
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=4)
    _scraped(run_dir, "INST-0000001", n_pages=2)
    _validated(run_dir, "INST-0000001", has_genai="yes", n_activities=1)
    _attrition.record(
        run_dir,
        institution_id="INST-0000001",
        stage="scrape",
        reason="crawl_delay_exceeded",
        url="https://x3.gov/",
        detail="budget=3600s;elapsed=3600.2s",
    )

    rec = _only(run_dir)
    assert rec["final_status"] == "EVIDENCE_FOUND_PARTIAL"
    # The ruling's requirement, unchanged: the skip is named, in the record, not
    # merely on the ledger where the report cannot see it.
    assert "crawl_delay_exceeded" in rec["reason"]
    assert "crawl_delay_exceeded" in (rec["error"] or "")
    # And it does not read as a clean result: a consumer filtering for
    # EVIDENCE_FOUND does not pick this row up.
    assert rec["final_status"] != "EVIDENCE_FOUND"
    assert rec["consolidated_row_count"] == 1  # the evidence is not discarded


# ---------------------------------------------------------------------------
# EVIDENCE_FOUND_PARTIAL (2026-08-31)
#
# Measured cause: 104 of 437 positives on r20260830T114940Z-32ea, 439 across
# five runs, all previously PROCESSING_FAILED. The tests below pin the boundary
# in both directions — the new status must not swallow real failures, and must
# not leak into the clean bucket.
# ---------------------------------------------------------------------------


def test_a_positive_with_one_failed_url_is_partial_not_failed(
    tmp_path: Path,
) -> None:
    """The measured case, reduced to its minimum.

    INST-0703416 on the 15k run: nine URLs, one ``download_error``, one
    consolidated activity, reported PROCESSING_FAILED. One failed fetch out of
    several was enough to erase a positive.
    """
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=9)
    _scraped(run_dir, "INST-0000001", n_pages=8)
    _validated(run_dir, "INST-0000001", has_genai="yes", n_activities=3)
    _attrition.record(
        run_dir,
        institution_id="INST-0000001",
        stage="scrape",
        reason="scrape_failed",
        url="https://x9.gov/",
        detail="download_error=HTTPError",
    )

    rec = _only(run_dir)
    assert rec["final_status"] == "EVIDENCE_FOUND_PARTIAL"
    assert rec["consolidated_row_count"] == 3
    assert rec["validation_status"] == "consolidated"


def test_a_positive_with_no_failures_is_still_plain_evidence_found(
    tmp_path: Path,
) -> None:
    """The new status must not annex the clean case.

    Without this, a regression that set the partial status unconditionally would
    pass every other test in this block.
    """
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=4)
    _scraped(run_dir, "INST-0000001", n_pages=4)
    _validated(run_dir, "INST-0000001", has_genai="yes", n_activities=1)

    assert _only(run_dir)["final_status"] == "EVIDENCE_FOUND"


def test_a_negative_with_a_failed_url_is_still_processing_failed(
    tmp_path: Path,
) -> None:
    """The #17 defence is untouched, and this is the test that proves it.

    The whole argument for the new status is that reporting failure is cautious
    for a negative and lossy for a positive. If the change had leaked into the
    negative branch it would have re-opened #17 — "could not reach" published as
    "searched and found nothing" — which is the defect this module exists to
    prevent.
    """
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=4)
    _scraped(run_dir, "INST-0000001", n_pages=2)
    _validated(run_dir, "INST-0000001", has_genai="no", n_activities=0)
    _attrition.record(
        run_dir,
        institution_id="INST-0000001",
        stage="scrape",
        reason="scrape_failed",
        url="https://x1.gov/",
        detail="download_error=HTTPError",
    )

    assert _only(run_dir)["final_status"] == "PROCESSING_FAILED"


def test_an_unclear_verdict_with_a_failed_url_is_still_processing_failed(
    tmp_path: Path,
) -> None:
    """``unclear`` is the pipeline declining to conclude, not a positive.

    1,173 of 7,947 consolidations on the 15k run were ``unclear``; none of them
    may reach the partial status, which asserts that evidence *was* found.
    """
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=4)
    _scraped(run_dir, "INST-0000001", n_pages=2)
    _validated(run_dir, "INST-0000001", has_genai="unclear", n_activities=0)
    _attrition.record(
        run_dir,
        institution_id="INST-0000001",
        stage="scrape",
        reason="scrape_failed",
        url="https://x1.gov/",
        detail="download_error=HTTPError",
    )

    assert _only(run_dir)["final_status"] == "PROCESSING_FAILED"


def test_a_validate_parse_failure_is_never_partial(tmp_path: Path) -> None:
    """A rejected consolidation has no verdict to be partial about.

    ``failed_to_parse`` must stay PROCESSING_FAILED, and the partial branch tests
    ``validation_status`` explicitly rather than trusting ``has_genai_activity``
    to be ``None``, so this holds even for an artifact whose ``institution``
    object reads ``yes``.

    The fixture writes a *contract-invalid* artifact rather than adding a ledger
    row, because that is the only way ``failed_to_parse`` actually arises:
    ``validate_parse_failures`` comes from re-parsing the artifact in
    ``load_consolidated_outputs``, not from the attrition ledger. (In production
    a Stage 6 rejection leaves no ``6_validate.json`` at all — verified on all
    126 rejected institutions of ``r20260830T114940Z-32ea`` — so it lands in the
    ``not_run`` branch instead. Both are covered: this test and
    ``test_a_negative_with_a_failed_url_is_still_processing_failed``.)
    """
    run_dir = tmp_path / "run"
    _make_run(run_dir, institutions=["INST-0000001"], done=ALL_STAGES)
    _discovery(run_dir, "INST-0000001")
    _triage(run_dir, "INST-0000001", keeps=4)
    _scraped(run_dir, "INST-0000001", n_pages=2)
    _validated(run_dir, "INST-0000001", has_genai="yes", n_activities=1)
    # has_genai_activity=yes with an empty activities list: the contract rejects
    # it, so load_consolidated_outputs books it as a parse failure.
    path = inst_dir_of(run_dir, "INST-0000001") / "6_validate.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["activities"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")
    _attrition.record(
        run_dir,
        institution_id="INST-0000001",
        stage="scrape",
        reason="scrape_failed",
        url="https://x1.gov/",
        detail="download_error=HTTPError",
    )

    rec = _only(run_dir)
    assert rec["validation_status"] == "failed_to_parse"
    assert rec["final_status"] == "PROCESSING_FAILED"


def test_the_new_status_is_counted_in_the_run_summary(tmp_path: Path) -> None:
    """``_FINAL_STATUSES`` gates the counter, so an unlisted status is dropped.

    ``final_status_counts`` is pre-seeded from that tuple and increments only
    ``if status in final_status_counts``. A status emitted by ``outcomes`` and
    missing from ``run_summary`` would therefore vanish, and the counts would
    stop summing to ``n_institutions`` — an identity the e2e check asserts.
    """
    from g3o.report import run_summary as _run_summary

    assert "EVIDENCE_FOUND_PARTIAL" in _run_summary._FINAL_STATUSES
