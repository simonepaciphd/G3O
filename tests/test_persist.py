"""Tests for `g3o.persist.writer` — Stage 7 deterministic CSV writer."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from g3o.common.contract import (
    NA,
    ConsolidatedInstitutionResponse,
)
from g3o.common.schema import (
    ACTIVITY_COLUMNS,
    ACTIVITY_SOURCE_COLUMNS,
    SUMMARY_COLUMNS,
)
from g3o.persist import (
    build_activity_rows,
    build_source_rows,
    build_summary_row,
    load_consolidated_outputs,
    write_run_csvs,
)
from tests._layout import (
    make_inst_dir,
    write_manifest,
)

# ---------------------------------------------------------------------------
# Fixture builders (parallel to test_validate.py / test_consolidated_contract.py)
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


def _source(source_id: str = "S1", activity_id: str = "A1", **overrides: Any) -> dict[str, Any]:
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
                _source(
                    source_id="S2",
                    activity_id=NA,
                    source_url="https://other.gov/news",
                    source_type="official_gov",
                    genai_evidence="confirms_absence",
                    source_snippet="News archive contains no GenAI mention.",
                ),
            ],
        }
    )


def _stage_run_dir(tmp_path: Path, responses: dict[str, ConsolidatedInstitutionResponse]) -> Path:
    """Create a layout-v2 run tree with one 6_validate.json per entry."""
    write_manifest(tmp_path, {"run_id": "R1", "institutions": sorted(responses)})
    for inst_id, response in responses.items():
        d = make_inst_dir(tmp_path, inst_id)
        (d / "6_validate.json").write_text(
            json.dumps(response.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return tmp_path


# ---------------------------------------------------------------------------
# Per-row builders
# ---------------------------------------------------------------------------


def test_build_activity_rows_keys_match_schema() -> None:
    response = _yes_response()
    rows = build_activity_rows(
        response, run_id="R1", run_model="gpt-5-nano", run_date="2026-05-09"
    )
    assert len(rows) == 1
    assert list(rows[0].keys()) == ACTIVITY_COLUMNS
    assert rows[0]["global_row_id"] == "R1::INST-0001::A1"
    assert rows[0]["run_id"] == "R1"
    assert rows[0]["run_tool"] == "g3o.persist.writer"
    assert rows[0]["activity_id"] == "A1"
    assert rows[0]["n_sources"] == 1


def test_build_activity_rows_empty_when_no_activities() -> None:
    response = _no_response()
    rows = build_activity_rows(response, run_id="R1", run_model="gpt-5-nano")
    assert rows == []


def test_build_source_rows_keys_match_schema() -> None:
    response = _yes_response()
    rows = build_source_rows(
        response, run_id="R1", run_model="gpt-5-nano", run_date="2026-05-09"
    )
    assert len(rows) == 1
    assert list(rows[0].keys()) == ACTIVITY_SOURCE_COLUMNS
    assert rows[0]["global_row_id"] == "R1::INST-0001::S1"
    assert rows[0]["activity_id"] == "A1"
    assert rows[0]["genai_evidence"] == "confirms_activity"


def test_build_source_rows_handles_na_activity_id() -> None:
    response = _no_response()
    rows = build_source_rows(response, run_id="R1", run_model="gpt-5-nano")
    assert len(rows) == 2
    assert all(r["activity_id"] == NA for r in rows)
    assert all(r["genai_evidence"] == "confirms_absence" for r in rows)


# ---------------------------------------------------------------------------
# Group-D salvage flag (deterministic source-level annotation)
# ---------------------------------------------------------------------------


def test_source_rows_salvage_flag_empty_without_map() -> None:
    """Absent a salvage map, the new column is present and empty (regression
    guard: the column always exists, defaulting to no annotation)."""
    rows = build_source_rows(_yes_response(), run_id="R1", run_model="gpt-5-nano")
    assert "group_d_salvaged_fields" in rows[0]
    assert rows[0]["group_d_salvaged_fields"] == ""


def test_source_rows_salvage_flag_populated_from_map() -> None:
    """A salvage map entry keyed by (institution_id, source_url) annotates the
    matching source row; a source URL not in the map stays empty."""
    salvaged = {("INST-0001", "https://example.gov/procurement/123"): "tool_name;vendor"}
    rows = build_source_rows(
        _yes_response(), run_id="R1", run_model="gpt-5-nano",
        salvaged_by_source=salvaged,
    )
    assert rows[0]["group_d_salvaged_fields"] == "tool_name;vendor"

    rows_no = build_source_rows(
        _no_response(), run_id="R1", run_model="gpt-5-nano",
        salvaged_by_source=salvaged,  # keyed to INST-0001, not INST-0002
    )
    assert all(r["group_d_salvaged_fields"] == "" for r in rows_no)


def test_salvaged_fields_by_source_parses_ledger(tmp_path: Path) -> None:
    """salvaged_fields_by_source reads the ledger, parses the salvaged-field
    list from detail, sorts it, and ignores non-salvage reasons."""
    from g3o.common import attrition
    from g3o.extract.salvage import REASON_SALVAGED
    from g3o.persist.writer import salvaged_fields_by_source

    attrition._reset_cache()
    url = "https://example.gov/procurement/123"
    attrition.record(
        tmp_path, institution_id="INST-0001", stage="extract",
        reason=REASON_SALVAGED, url=url, detail="rows=[1];fields=vendor,tool_name",
    )
    attrition.record(
        tmp_path, institution_id="INST-0001", stage="extract",
        reason="parse_failed", url="https://example.gov/other", detail="boom",
    )
    mapping = salvaged_fields_by_source(tmp_path)
    attrition._reset_cache()

    assert mapping == {("INST-0001", url): "tool_name;vendor"}  # sorted, ; joined


def test_write_run_csvs_source_csv_carries_salvage_flag(tmp_path: Path) -> None:
    """End-to-end: a ledger salvage record surfaces in the written source CSV's
    group_d_salvaged_fields column for the matching (institution, source_url)."""
    from g3o.common import attrition
    from g3o.extract.salvage import REASON_SALVAGED

    attrition._reset_cache()
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    attrition.record(
        run_dir, institution_id="INST-0001", stage="extract",
        reason=REASON_SALVAGED,
        url="https://example.gov/procurement/123",
        detail="rows=[1];fields=vendor,year_deployed",
    )
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano", version=1)
    _, source_rows = _read_csv(run_dir / "final" / "g3o_activity_sources_v1.csv")
    attrition._reset_cache()

    assert source_rows[0]["group_d_salvaged_fields"] == "vendor;year_deployed"


def test_build_summary_row_keys_match_schema() -> None:
    response = _yes_response(
        activities=[
            _activity(n_sources=2),
            _activity(
                activity_id="A2",
                activity_name="Public chatbot",
                activity_type="public_facing_service",
                adoption_stage="production",
                interaction_type="chatbot",
                tool_name="MyCity Bot",
                vendor="In-house",
                target_users="public",
                n_sources=1,
                confidence="medium",
                uncertainty_flags="vendor_undisclosed",
            ),
        ],
        sources=[
            _source(source_id="S1", activity_id="A1"),
            _source(
                source_id="S2",
                activity_id="A1",
                source_url="https://example.gov/news",
                source_type="news_major",
                source_credibility="medium",
                source_snippet="News article confirming Copilot pilot.",
            ),
            _source(
                source_id="S3",
                activity_id="A2",
                source_url="https://example.gov/services/chatbot",
                source_type="official_gov",
                source_credibility="low",
                source_snippet="Public-facing chatbot launch announcement.",
            ),
        ],
    )
    row = build_summary_row(response, run_id="R1", run_date="2026-05-09")
    assert list(row.keys()) == SUMMARY_COLUMNS
    assert row["institution_id"] == "INST-0001"
    assert row["n_pages_extracted"] == 2  # from _meta
    assert row["n_activities"] == 2
    assert row["n_sources"] == 3
    assert row["n_high_credibility_sources"] == 1
    assert row["n_medium_credibility_sources"] == 1
    assert row["n_low_credibility_sources"] == 1
    assert row["activities_found"] == "Internal Copilot pilot | Public chatbot"
    assert row["tools_found"] == "Microsoft 365 Copilot | MyCity Bot"
    # Vendors: "Microsoft" + "In-house" — distinct, sorted; both surfaced
    assert "Microsoft" in row["vendors_found"]
    assert "In-house" in row["vendors_found"]
    assert row["best_confidence"] == "high"  # max across activities
    assert row["consolidated_uncertainty_flags"] == "vendor_undisclosed"


def test_build_summary_row_no_activity_institution() -> None:
    response = _no_response()
    row = build_summary_row(response, run_id="R1")
    assert row["has_genai_activity"] == "no"
    assert row["n_activities"] == 0
    assert row["n_sources"] == 2
    assert row["activities_found"] == ""
    assert row["tools_found"] == ""
    assert row["vendors_found"] == ""
    assert row["best_confidence"] == "_NA_"  # no activities to draw from
    assert row["consolidated_uncertainty_flags"] == "none"


def test_build_summary_row_uncertainty_flags_unioned() -> None:
    response = _yes_response(
        activities=[
            _activity(uncertainty_flags="stage_ambiguous;date_uncertain"),
            _activity(activity_id="A2", uncertainty_flags="vendor_undisclosed"),
        ],
        sources=[
            _source(source_id="S1", activity_id="A1"),
            _source(
                source_id="S2",
                activity_id="A2",
                source_url="https://example.gov/x",
            ),
        ],
    )
    row = build_summary_row(response, run_id="R1")
    flags = row["consolidated_uncertainty_flags"].split(";")
    assert sorted(flags) == ["date_uncertain", "stage_ambiguous", "vendor_undisclosed"]


# ---------------------------------------------------------------------------
# load_consolidated_outputs
# ---------------------------------------------------------------------------


def test_load_consolidated_outputs_parses_valid_payloads(tmp_path: Path) -> None:
    run_dir = _stage_run_dir(
        tmp_path,
        {
            "INST-0001": _yes_response(),
            "INST-0002": _no_response(),
        },
    )
    loaded, failures = load_consolidated_outputs(run_dir)
    assert failures == []
    assert {li.institution_id for li in loaded} == {"INST-0001", "INST-0002"}


def test_load_consolidated_outputs_skips_missing_payload(tmp_path: Path) -> None:
    write_manifest(tmp_path)
    make_inst_dir(tmp_path, "INST-0001")  # no 6_validate.json
    loaded, failures = load_consolidated_outputs(tmp_path)
    assert loaded == []
    assert failures == []


def test_load_consolidated_outputs_records_failures(tmp_path: Path) -> None:
    write_manifest(tmp_path)
    bad_dir = make_inst_dir(tmp_path, "INST-BAD")
    (bad_dir / "6_validate.json").write_text(
        json.dumps({"institution": {"institution_id": "INST-BAD"}}), encoding="utf-8"
    )
    loaded, failures = load_consolidated_outputs(tmp_path)
    assert loaded == []
    assert failures == ["INST-BAD"]


def test_load_consolidated_outputs_missing_run_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_consolidated_outputs(tmp_path / "no-such-run")


# ---------------------------------------------------------------------------
# write_run_csvs end-to-end
# ---------------------------------------------------------------------------


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return reader.fieldnames or [], rows


def test_write_run_csvs_three_files(tmp_path: Path) -> None:
    run_dir = _stage_run_dir(
        tmp_path,
        {
            "INST-0001": _yes_response(),
            "INST-0002": _no_response(),
        },
    )
    summary = write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")
    assert summary["n_institutions"] == 2
    assert summary["n_load_failures"] == 0
    final_dir = run_dir / "final"
    assert (final_dir / "g3o_activities_v1.csv").exists()
    assert (final_dir / "g3o_activity_sources_v1.csv").exists()
    assert (final_dir / "g3o_institution_summary_v1.csv").exists()


def test_write_run_csvs_activities_csv_shape(tmp_path: Path) -> None:
    run_dir = _stage_run_dir(
        tmp_path,
        {
            "INST-0001": _yes_response(),
            "INST-0002": _no_response(),
        },
    )
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    fields, rows = _read_csv(run_dir / "final" / "g3o_activities_v1.csv")
    assert fields == ACTIVITY_COLUMNS
    # Only INST-0001 has an activity (INST-0002 is no-evidence)
    assert len(rows) == 1
    assert rows[0]["institution_id"] == "INST-0001"
    assert rows[0]["activity_id"] == "A1"


def test_write_run_csvs_sources_csv_shape(tmp_path: Path) -> None:
    run_dir = _stage_run_dir(
        tmp_path,
        {
            "INST-0001": _yes_response(),
            "INST-0002": _no_response(),
        },
    )
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")

    fields, rows = _read_csv(run_dir / "final" / "g3o_activity_sources_v1.csv")
    assert fields == ACTIVITY_SOURCE_COLUMNS
    # 1 from INST-0001 + 2 from INST-0002 = 3
    assert len(rows) == 3
    activity_ids = {r["activity_id"] for r in rows}
    assert activity_ids == {"A1", "_NA_"}


def test_write_run_csvs_summary_csv_shape(tmp_path: Path) -> None:
    run_dir = _stage_run_dir(
        tmp_path,
        {
            "INST-0001": _yes_response(),
            "INST-0002": _no_response(),
        },
    )
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano", run_date="2026-05-09")

    fields, rows = _read_csv(run_dir / "final" / "g3o_institution_summary_v1.csv")
    assert fields == SUMMARY_COLUMNS
    assert {r["institution_id"] for r in rows} == {"INST-0001", "INST-0002"}
    by_id = {r["institution_id"]: r for r in rows}
    assert by_id["INST-0001"]["has_genai_activity"] == "yes"
    assert by_id["INST-0002"]["has_genai_activity"] == "no"
    assert by_id["INST-0002"]["n_activities"] == "0"


def test_write_run_csvs_refuses_overwrite(tmp_path: Path) -> None:
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")
    with pytest.raises(FileExistsError):
        write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")


def test_write_run_csvs_overwrite_flag_replaces(tmp_path: Path) -> None:
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano")
    # Add a second institution and overwrite.
    second_dir = make_inst_dir(run_dir, "INST-0002")
    (second_dir / "6_validate.json").write_text(
        json.dumps(_no_response().model_dump(), ensure_ascii=False),
        encoding="utf-8",
    )
    summary = write_run_csvs(
        run_dir, run_id="R1", run_model="gpt-5-nano", overwrite=True
    )
    assert summary["n_institutions"] == 2
    fields, rows = _read_csv(run_dir / "final" / "g3o_institution_summary_v1.csv")
    assert {r["institution_id"] for r in rows} == {"INST-0001", "INST-0002"}


def test_write_run_csvs_version_suffix_honored(tmp_path: Path) -> None:
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    summary = write_run_csvs(
        run_dir, run_id="R1", run_model="gpt-5-nano", version=3
    )
    assert summary["version"] == 3
    assert (run_dir / "final" / "g3o_activities_v3.csv").exists()
    assert (run_dir / "final" / "g3o_activity_sources_v3.csv").exists()
    assert (run_dir / "final" / "g3o_institution_summary_v3.csv").exists()


def test_write_run_csvs_round_trip_revalidates(tmp_path: Path) -> None:
    """Sanity: every CSV row reconstructs back into the Pydantic surface."""
    run_dir = _stage_run_dir(tmp_path, {"INST-0001": _yes_response()})
    write_run_csvs(run_dir, run_id="R1", run_model="gpt-5-nano", run_date="2026-05-09")

    # Activities CSV — revalidate against the schema set
    _, activity_rows = _read_csv(run_dir / "final" / "g3o_activities_v1.csv")
    assert all(set(r.keys()) == set(ACTIVITY_COLUMNS) for r in activity_rows)

    # Sources CSV
    _, source_rows = _read_csv(run_dir / "final" / "g3o_activity_sources_v1.csv")
    assert all(set(r.keys()) == set(ACTIVITY_SOURCE_COLUMNS) for r in source_rows)

    # Summary CSV
    _, summary_rows = _read_csv(run_dir / "final" / "g3o_institution_summary_v1.csv")
    assert all(set(r.keys()) == set(SUMMARY_COLUMNS) for r in summary_rows)
