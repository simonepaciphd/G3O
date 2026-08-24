"""Tests for `g3o.persist.integrity` — post-persist FK validation.

Tests cover all foreign key constraints:
- Hard constraints (violations): source→activity links, activity→source coverage,
  institution consistency, summary counts, run_id consistency, metadata consistency
- Soft constraints (warnings): global_row_id uniqueness, activity/source sequences
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from g3o.common.contract import NA, ConsolidatedInstitutionResponse
from g3o.persist import write_run_csvs
from g3o.persist.integrity import (
    FKViolation,
    IntegrityError,
    IntegrityReport,
    validate_run_csvs,
)
from tests._layout import make_inst_dir, write_manifest

# ---------------------------------------------------------------------------
# Fixture builders (reuse from test_persist.py patterns)
# ---------------------------------------------------------------------------


def _meta(**overrides: Any) -> dict[str, Any]:
    base = {
        "institution_id": "INST-0001",
        "n_input_pages": 2,
        "n_input_rows": 3,
        "response_timestamp": "2026-05-09T12:00:00Z",
        "model_label": "gpt-5-nano",
        "notes": "none",
    }
    base.update(overrides)
    return base


def _institution(**overrides: Any) -> dict[str, Any]:
    base = {
        "institution_id": "INST-0001",
        "institution_name": "Test Ministry",
        "country": "Testland",
        "branch_of_government": "executive",
        "level_of_government": "national",
        "has_genai_activity": "yes",
        "institution_summary": "Internal Copilot pilot underway.",
        "institution_search_languages": "en",
    }
    base.update(overrides)
    return base


def _activity(activity_id: str = "A1", **overrides: Any) -> dict[str, Any]:
    base = {
        "activity_id": activity_id,
        "activity_name": "Internal Copilot pilot",
        "activity_type": "internal_operational",
        "adoption_stage": "pilot",
        "access_type": "proprietary_vendor",
        "interaction_type": "document_processing",
        "tool_name": "Microsoft 365 Copilot",
        "vendor": "Microsoft",
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
        "scope_notes": "Pilot for 100 staff members.",
        "n_sources": 1,
        "confidence": "high",
        "uncertainty_flags": "none",
    }
    base.update(overrides)
    return base


def _source(
    source_id: str = "S1", activity_id: str = "A1", **overrides: Any
) -> dict[str, Any]:
    base = {
        "source_id": source_id,
        "activity_id": activity_id,
        "source_url": "https://example.gov/procurement/123",
        "source_title": "Test procurement",
        "source_publication_date": "2025-01",
        "source_access_date": "2026-05-08",
        "source_type": "procurement_tender",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": "confirms_activity",
        "source_snippet": "Procurement of 100 Microsoft 365 Copilot licenses.",
    }
    base.update(overrides)
    return base


def _yes_response(**overrides: Any) -> ConsolidatedInstitutionResponse:
    payload = {
        "consolidation_metadata": _meta(),
        "institution": _institution(),
        "activities": [_activity()],
        "sources": [_source()],
    }
    payload.update(overrides)
    return ConsolidatedInstitutionResponse.model_validate(payload)


def _no_response(institution_id: str = "INST-0002") -> ConsolidatedInstitutionResponse:
    return ConsolidatedInstitutionResponse.model_validate(
        {
            "consolidation_metadata": _meta(institution_id=institution_id),
            "institution": _institution(
                institution_id=institution_id,
                institution_name="Other Ministry",
                has_genai_activity="no",
                institution_summary="No GenAI evidence in supplied texts.",
            ),
            "activities": [],
            "sources": [
                _source(
                    source_id="S1",
                    activity_id=NA,
                    source_url="https://other.gov/",
                    source_type="official_gov",
                    genai_evidence="confirms_absence",
                    source_snippet="Page contains no GenAI mention.",
                ),
            ],
        }
    )


def _stage_run_dir(
    tmp_path: Path, responses: dict[str, ConsolidatedInstitutionResponse]
) -> Path:
    """Create a layout-v2 run tree with one 6_validate.json per entry."""
    write_manifest(tmp_path, {"run_id": "R1", "institutions": sorted(responses)})
    for inst_id, response in responses.items():
        d = make_inst_dir(tmp_path, inst_id)
        (d / "6_validate.json").write_text(
            json.dumps(response.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return tmp_path


def _write_csv(
    path: Path, columns: list[str], rows: list[dict[str, str]]
) -> None:
    """Write rows to CSV with given columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Test valid run passes validation
# ---------------------------------------------------------------------------


def test_valid_run_passes_validation(tmp_path: Path) -> None:
    """Happy path: a valid run with no violations should pass validation."""
    run_dir = _stage_run_dir(
        tmp_path,
        {
            "INST-0001": _yes_response(),
            "INST-0002": _no_response(),
        },
    )
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    report = validate_run_csvs(run_dir, version=1)

    assert report.is_valid
    assert len(report.violations) == 0
    assert report.n_institutions == 2
    assert report.n_activities == 1
    assert report.n_sources == 2  # 1 from INST-0001 + 1 from INST-0002


# ---------------------------------------------------------------------------
# Constraint 1: Source → Activity link validation
# ---------------------------------------------------------------------------


def test_orphaned_source_detected(tmp_path: Path) -> None:
    """Source references non-existent activity_id should be detected."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Corrupt the sources CSV: add a source with invalid activity_id
    sources_csv = run_dir / "final" / "g3o_activity_sources_v1.csv"
    rows = list(csv.DictReader(sources_csv.open(encoding="utf-8")))
    rows.append(
        {
            "global_row_id": "R1::INST-0001::S99",
            "run_id": "R1",
            "run_model": "gpt-5-nano",
            "run_tool": "g3o.persist.writer",
            "run_date": "2026-05-09",
            "institution_id": "INST-0001",
            "activity_id": "A999",  # Does not exist
            "source_id": "S99",
            "source_url": "https://orphan.gov/",
            "source_title": "Orphan source",
            "source_publication_date": "2025-01",
            "source_access_date": "2026-05-08",
            "source_type": "official_gov",
            "source_language": "en",
            "source_credibility": "high",
            "genai_evidence": "confirms_absence",
            "source_snippet": "This source has no matching activity",
            "group_d_salvaged_fields": "",
        }
    )
    _write_csv(sources_csv, list(rows[0].keys()), rows)

    report = validate_run_csvs(run_dir, version=1)

    assert not report.is_valid
    assert len(report.violations) >= 1
    orphan_violations = [
        v for v in report.violations if v.constraint == "source_activity_link"
    ]
    assert len(orphan_violations) == 1
    assert orphan_violations[0].entity_id == "S99"
    assert "A999" in orphan_violations[0].detail


# ---------------------------------------------------------------------------
# Constraint 2: Activity → Source coverage validation
# ---------------------------------------------------------------------------


def test_activity_without_sources_detected(tmp_path: Path) -> None:
    """Activity with no supporting sources should be detected."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Remove all sources for A1
    sources_csv = run_dir / "final" / "g3o_activity_sources_v1.csv"
    rows = list(csv.DictReader(sources_csv.open(encoding="utf-8")))
    rows = [r for r in rows if r["activity_id"] != "A1"]
    _write_csv(sources_csv, list(rows[0].keys()) if rows else [], rows)

    report = validate_run_csvs(run_dir, version=1)

    assert not report.is_valid

    # Expect both activity_source_coverage AND summary_count_integrity violations
    coverage_violations = [
        v for v in report.violations if v.constraint == "activity_source_coverage"
    ]
    assert len(coverage_violations) == 1
    assert coverage_violations[0].entity_id == "A1"

    count_violations = [
        v for v in report.violations if v.constraint == "summary_count_integrity"
    ]
    assert len(count_violations) >= 1
    source_count_violations = [
        v for v in count_violations if "n_sources" in v.detail
    ]
    assert len(source_count_violations) == 1


# ---------------------------------------------------------------------------
# Constraint 3: Institution consistency validation
# ---------------------------------------------------------------------------


def test_institution_without_summary_detected(tmp_path: Path) -> None:
    """Institution in activities/sources but missing from summary should be detected."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Remove INST-0001 from summary
    summary_csv = run_dir / "final" / "g3o_institution_summary_v1.csv"
    rows = list(csv.DictReader(summary_csv.open(encoding="utf-8")))
    rows = [r for r in rows if r["institution_id"] != "INST-0001"]
    _write_csv(summary_csv, list(rows[0].keys()) if rows else [], rows)

    report = validate_run_csvs(run_dir, version=1)

    assert not report.is_valid
    inst_violations = [
        v for v in report.violations if v.constraint == "institution_consistency"
    ]
    assert len(inst_violations) == 1
    assert inst_violations[0].entity_id == "INST-0001"


# ---------------------------------------------------------------------------
# Constraint 4: Summary count integrity validation
# ---------------------------------------------------------------------------


def test_mismatched_summary_counts_detected(tmp_path: Path) -> None:
    """Summary n_activities != actual count should be detected."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Corrupt summary count
    summary_csv = run_dir / "final" / "g3o_institution_summary_v1.csv"
    rows = list(csv.DictReader(summary_csv.open(encoding="utf-8")))
    for row in rows:
        if row["institution_id"] == "INST-0001":
            row["n_activities"] = "99"  # Wrong count
    _write_csv(summary_csv, list(rows[0].keys()), rows)

    report = validate_run_csvs(run_dir, version=1)

    assert not report.is_valid
    count_violations = [
        v for v in report.violations if v.constraint == "summary_count_integrity"
    ]
    assert len(count_violations) >= 1
    activity_count_violations = [v for v in count_violations if "n_activities" in v.detail]
    assert len(activity_count_violations) == 1


# ---------------------------------------------------------------------------
# Constraint 5: Run ID consistency validation
# ---------------------------------------------------------------------------


def test_inconsistent_run_id_detected(tmp_path: Path) -> None:
    """Multiple run_ids in CSVs should be detected."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Corrupt run_id in activities CSV
    activities_csv = run_dir / "final" / "g3o_activities_v1.csv"
    rows = list(csv.DictReader(activities_csv.open(encoding="utf-8")))
    for row in rows:
        row["run_id"] = "R2"  # Different run_id
    _write_csv(activities_csv, list(rows[0].keys()), rows)

    report = validate_run_csvs(run_dir, version=1)

    assert not report.is_valid
    run_id_violations = [
        v for v in report.violations if v.constraint == "run_id_consistency"
    ]
    assert len(run_id_violations) == 1
    assert "multiple" in run_id_violations[0].entity_id


# ---------------------------------------------------------------------------
# Soft constraints (warnings)
# ---------------------------------------------------------------------------


def test_duplicate_global_row_id_warning(tmp_path: Path) -> None:
    """Duplicate global_row_id should generate a warning."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Add duplicate activity row
    activities_csv = run_dir / "final" / "g3o_activities_v1.csv"
    rows = list(csv.DictReader(activities_csv.open(encoding="utf-8")))
    rows.append(rows[0].copy())  # Duplicate first row
    _write_csv(activities_csv, list(rows[0].keys()), rows)

    # Also update summary CSV to match new activity count (otherwise summary_count_integrity violation)
    summary_csv = run_dir / "final" / "g3o_institution_summary_v1.csv"
    summary_rows = list(csv.DictReader(summary_csv.open(encoding="utf-8")))
    for row in summary_rows:
        if row["institution_id"] == "INST-0001":
            row["n_activities"] = "2"  # Was 1, now 2 after duplication
    _write_csv(summary_csv, list(summary_rows[0].keys()), summary_rows)

    report = validate_run_csvs(run_dir, version=1)

    assert report.is_valid  # Still valid (no hard violations)
    assert len(report.warnings) >= 1
    assert any("global_row_id" in w for w in report.warnings)


def test_gapless_activity_sequence_warning(tmp_path: Path) -> None:
    """Activity IDs with gaps should generate a warning."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Add A3 activity to create a gap (A1, A3 instead of A1, A2)
    activities_csv = run_dir / "final" / "g3o_activities_v1.csv"
    rows = list(csv.DictReader(activities_csv.open(encoding="utf-8")))
    row_with_a3 = rows[0].copy()
    row_with_a3["activity_id"] = "A3"
    row_with_a3["global_row_id"] = "R1::INST-0001::A3"
    rows.append(row_with_a3)
    _write_csv(activities_csv, list(rows[0].keys()), rows)

    # Add a source for A3 (otherwise activity_source_coverage violation)
    sources_csv = run_dir / "final" / "g3o_activity_sources_v1.csv"
    source_rows = list(csv.DictReader(sources_csv.open(encoding="utf-8")))
    source_for_a3 = source_rows[0].copy()
    source_for_a3["activity_id"] = "A3"
    source_for_a3["source_id"] = "S2"
    source_for_a3["global_row_id"] = "R1::INST-0001::S2"
    source_for_a3["source_url"] = "https://example.gov/a3-source"
    source_rows.append(source_for_a3)
    _write_csv(sources_csv, list(source_rows[0].keys()), source_rows)

    # Update summary CSV counts to match (2 activities, 2 sources)
    summary_csv = run_dir / "final" / "g3o_institution_summary_v1.csv"
    summary_rows = list(csv.DictReader(summary_csv.open(encoding="utf-8")))
    for row in summary_rows:
        if row["institution_id"] == "INST-0001":
            row["n_activities"] = "2"
            row["n_sources"] = "2"
    _write_csv(summary_csv, list(summary_rows[0].keys()), summary_rows)

    report = validate_run_csvs(run_dir, version=1)

    assert report.is_valid  # Still valid (no hard violations)
    assert len(report.warnings) >= 1
    assert any("sequence" in w for w in report.warnings)


# ---------------------------------------------------------------------------
# Phase 2: Institution metadata consistency
# ---------------------------------------------------------------------------


def test_institution_metadata_mismatch_detected(tmp_path: Path) -> None:
    """Mismatched institution.json vs 6_validate.json should be detected."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})

    # Add institution.json with mismatched metadata
    inst_dir = make_inst_dir(run_dir, "INST-0001")
    institution_json = {
        "institution_id": "INST-0001",
        "institution_name": "Wrong Name",  # Mismatch
        "country": "Wrong Country",  # Mismatch
        "branch_of_government": "executive",
        "level_of_government": "national",
    }
    (inst_dir / "institution.json").write_text(
        json.dumps(institution_json, ensure_ascii=False), encoding="utf-8"
    )

    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")
    report = validate_run_csvs(run_dir, version=1, check_metadata=True)

    assert not report.is_valid
    metadata_violations = [
        v for v in report.violations if v.constraint == "institution_metadata_consistency"
    ]
    assert len(metadata_violations) >= 2  # At least name and country


def test_duplicate_institution_id_detected(tmp_path: Path) -> None:
    """Duplicate institution_id in summary should be detected."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Add duplicate institution row to summary
    summary_csv = run_dir / "final" / "g3o_institution_summary_v1.csv"
    rows = list(csv.DictReader(summary_csv.open(encoding="utf-8")))
    rows.append(rows[0].copy())  # Duplicate first row
    _write_csv(summary_csv, list(rows[0].keys()), rows)

    report = validate_run_csvs(run_dir, version=1)

    assert not report.is_valid
    dup_violations = [
        v for v in report.violations if v.constraint == "institution_id_uniqueness"
    ]
    assert len(dup_violations) == 1
    assert dup_violations[0].entity_id == "INST-0001"


# ---------------------------------------------------------------------------
# IntegrityError exception
# ---------------------------------------------------------------------------


def test_integrity_error_on_violations(tmp_path: Path) -> None:
    """IntegrityError should be raised when violations exist."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    # Corrupt the CSV by adding an orphan source
    sources_csv = run_dir / "final" / "g3o_activity_sources_v1.csv"
    rows = list(csv.DictReader(sources_csv.open(encoding="utf-8")))
    rows.append(
        {
            "global_row_id": "R1::INST-0001::S99",
            "run_id": "R1",
            "run_model": "gpt-5-nano",
            "run_tool": "g3o.persist.writer",
            "run_date": "2026-05-09",
            "institution_id": "INST-0001",
            "activity_id": "A999",
            "source_id": "S99",
            "source_url": "https://orphan.gov/",
            "source_title": "Orphan source",
            "source_publication_date": "2025-01",
            "source_access_date": "2026-05-08",
            "source_type": "official_gov",
            "source_language": "en",
            "source_credibility": "high",
            "genai_evidence": "confirms_absence",
            "source_snippet": "Orphan",
            "group_d_salvaged_fields": "",
        }
    )
    _write_csv(sources_csv, list(rows[0].keys()), rows)

    # Call validate_run_csvs directly to verify it detects violations
    report = validate_run_csvs(run_dir, version=1)
    assert not report.is_valid
    assert len(report.violations) >= 1
    
    # Verify IntegrityError can be constructed with the report
    error = IntegrityError(report)
    assert error.report is report
    assert "Referential integrity validation failed" in str(error)


# ---------------------------------------------------------------------------
# Report summary
# ---------------------------------------------------------------------------


def test_report_summary_format() -> None:
    """IntegrityReport.summary() should return a formatted string."""
    report = IntegrityReport(
        n_institutions=10,
        n_activities=50,
        n_sources=150,
        violations=[],
        warnings=["warning1", "warning2"],
    )

    summary = report.summary()

    assert "VALID" in summary
    assert "10 institutions" in summary
    assert "50 activities" in summary
    assert "150 sources" in summary
    assert "0 violations" in summary
    assert "2 warnings" in summary


def test_fk_violation_str() -> None:
    """FKViolation should have a readable string representation."""
    violation = FKViolation(
        constraint="source_activity_link",
        entity_type="source",
        entity_id="S99",
        detail="activity_id='A999' does not exist",
    )

    text = str(violation)

    assert "source_activity_link" in text
    assert "source" in text
    assert "S99" in text
    assert "A999" in text


# ---------------------------------------------------------------------------
# Integration: write_run_csvs includes integrity report
# ---------------------------------------------------------------------------


def test_write_run_csvs_includes_integrity_summary(tmp_path: Path) -> None:
    """write_run_csvs return value should include integrity summary."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    result = write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    assert "integrity" in result
    assert result["integrity"]["is_valid"] is True
    assert result["integrity"]["n_violations"] == 0
    assert "n_warnings" in result["integrity"]


def test_write_run_csvs_skip_integrity_check(tmp_path: Path) -> None:
    """skip_integrity_check=True bypasses validation and returns None."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    result = write_run_csvs(
        run_dir, run_id="R1", run_model="gpt-5-nano", skip_integrity_check=True
    )

    assert "integrity" in result
    assert result["integrity"] is None
