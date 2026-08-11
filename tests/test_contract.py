"""Tests for `g3o.common.contract` — Pydantic models for Output Contract v2.0."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from g3o.common.contract import (
    BatchMetadata,
    BatchResponse,
    ContractRow,
    PersistedRow,
    RunProvenance,
    ValidationProvenance,
)
from g3o.common.schema import DATA_COLUMNS

# ---------------------------------------------------------------------------
# Builders — keep test fixtures readable.
# ---------------------------------------------------------------------------


def absent_row(**overrides: Any) -> dict[str, Any]:
    """A `confirms_absence` row with all Group D set to `_NA_`."""
    base: dict[str, Any] = {
        "row_id": 1,
        "batch_id": "test-batch",
        "institution_id": "INST-0001",
        "institution_name": "Test Ministry",
        "country": "Testland",
        "branch_of_government": "executive",
        "level_of_government": "national",
        "has_genai_activity": "no",
        "institution_summary": "No GenAI evidence in supplied texts.",
        "institution_search_languages": "en",
        # Group D all _NA_
        "activity_name": "_NA_",
        "activity_type": "_NA_",
        "adoption_stage": "_NA_",
        "access_type": "_NA_",
        "interaction_type": "_NA_",
        "tool_name": "_NA_",
        "vendor": "_NA_",
        "deployment_mode": "_NA_",
        "target_users": "_NA_",
        "year_announced": "_NA_",
        "year_deployed": "_NA_",
        "has_human_oversight": "_NA_",
        "has_transparency_notice": "_NA_",
        "has_data_classification": "_NA_",
        "has_risk_assessment": "_NA_",
        "reported_outcomes": "_NA_",
        "reported_incidents": "_NA_",
        "scope_notes": "_NA_",
        # Group E
        "source_url": "https://example.gov/",
        "source_title": "Test page",
        "source_publication_date": "2026",
        "source_access_date": "2026-05-08",
        "source_type": "official_gov",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": "confirms_absence",
        "source_snippet": "Supplied page contains no GenAI mention.",
        # Group F
        "confidence": "high",
        "uncertainty_flags": "none",
    }
    base.update(overrides)
    return base


def active_row(**overrides: Any) -> dict[str, Any]:
    """A `confirms_activity` row with full Group D filled."""
    base = absent_row()
    base.update(
        {
            "has_genai_activity": "yes",
            "institution_summary": "Internal Copilot pilot underway.",
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
            "source_url": "https://example.gov/procurement/123",
            "source_publication_date": "2025-01",
            "source_type": "procurement_tender",
            "genai_evidence": "confirms_activity",
            "source_snippet": "Contract award: 100 Copilot licenses.",
        }
    )
    base.update(overrides)
    return base


def metadata(
    *, n_institutions_in_batch: int = 1, n_institutions_with_genai: int = 0,
    n_data_rows: int = 1, **overrides: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "batch_id": "test-batch",
        "chat_type": "web",
        "model_label": "gpt-5-nano",
        "response_timestamp": "2026-05-08T14:30:00Z",
        "n_institutions_in_batch": n_institutions_in_batch,
        "n_institutions_with_genai": n_institutions_with_genai,
        "n_data_rows": n_data_rows,
        "search_languages": "en",
        "search_strategy_summary": "Test batch.",
        "notes": "none",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Valid payloads
# ---------------------------------------------------------------------------


def test_valid_no_genai_two_sources():
    """Edge case A: institution with 0 GenAI activity, 2 supplied pages."""
    rows = [
        absent_row(row_id=1, source_url="https://example.gov/"),
        absent_row(row_id=2, source_url="https://example.gov/news/"),
    ]
    BatchResponse.model_validate(
        {"batch_metadata": metadata(n_data_rows=2), "data": rows}
    )


def test_valid_multi_activity():
    """Edge case D-style: one institution, two activities, three rows."""
    a1_src1 = active_row(row_id=1, source_url="https://example.gov/release1")
    a1_src2 = active_row(row_id=2, source_url="https://example.gov/release2")
    a2 = active_row(
        row_id=3,
        activity_name="Public chatbot launch",
        activity_type="public_facing_service",
        interaction_type="chatbot",
        target_users="public",
        tool_name="Internal chatbot",
        vendor="In-house team",
        source_url="https://example.gov/chatbot",
    )
    BatchResponse.model_validate(
        {
            "batch_metadata": metadata(
                n_institutions_with_genai=1, n_data_rows=3
            ),
            "data": [a1_src1, a1_src2, a2],
        }
    )


def test_valid_uncertainty_flags_combinations():
    ContractRow.model_validate(absent_row(uncertainty_flags="none"))
    ContractRow.model_validate(absent_row(uncertainty_flags="stage_ambiguous"))
    ContractRow.model_validate(
        absent_row(uncertainty_flags="stage_ambiguous;vendor_undisclosed")
    )


def test_valid_year_formats():
    ContractRow.model_validate(active_row(year_announced="2024", year_deployed="unknown"))


# ---------------------------------------------------------------------------
# Invalid payloads — one per validator
# ---------------------------------------------------------------------------


def test_invalid_enum_rejected():
    with pytest.raises(ValidationError):
        ContractRow.model_validate(absent_row(source_type="not_a_real_type"))


def test_invalid_na_when_confirms_activity():
    """Group D _NA_ is illegal when genai_evidence == confirms_activity."""
    with pytest.raises(ValidationError) as exc:
        ContractRow.model_validate(active_row(tool_name="_NA_"))
    assert "Group D" in str(exc.value) or "tool_name" in str(exc.value)


def test_invalid_non_na_when_confirms_absence():
    """Group D non-_NA_ is illegal when genai_evidence != confirms_activity."""
    with pytest.raises(ValidationError) as exc:
        ContractRow.model_validate(absent_row(activity_type="pilot_experiment"))
    assert "Group D" in str(exc.value) or "_NA_" in str(exc.value)


def test_invalid_uncertainty_flags_with_space():
    with pytest.raises(ValidationError) as exc:
        ContractRow.model_validate(
            absent_row(uncertainty_flags="stage_ambiguous; vendor_undisclosed")
        )
    assert "spaces" in str(exc.value)


def test_invalid_uncertainty_flag_unknown_token():
    with pytest.raises(ValidationError) as exc:
        ContractRow.model_validate(absent_row(uncertainty_flags="not_a_real_flag"))
    assert "uncertainty flag" in str(exc.value)


def test_invalid_year_format():
    with pytest.raises(ValidationError):
        ContractRow.model_validate(active_row(year_announced="20XX"))


def test_invalid_languages_regex():
    with pytest.raises(ValidationError):
        ContractRow.model_validate(absent_row(institution_search_languages="EN"))


def test_invalid_source_language_regex():
    with pytest.raises(ValidationError):
        ContractRow.model_validate(absent_row(source_language="eng"))


def test_invalid_source_access_date_format():
    with pytest.raises(ValidationError):
        ContractRow.model_validate(absent_row(source_access_date="2026/05/08"))


def test_invalid_institution_fields_disagree():
    """Consistency check #4: institution-level fields must match across rows."""
    a = absent_row(row_id=1)
    b = absent_row(
        row_id=2, institution_summary="A different summary disagreeing with row 1."
    )
    with pytest.raises(ValidationError) as exc:
        BatchResponse.model_validate(
            {"batch_metadata": metadata(n_data_rows=2), "data": [a, b]}
        )
    assert "institution_summary" in str(exc.value)


def test_invalid_activity_fields_disagree():
    """Consistency check #5: rows for same (institution, activity) must match."""
    a = active_row(row_id=1)
    b = active_row(row_id=2, vendor="Different Vendor", source_url="https://x.gov/")
    with pytest.raises(ValidationError) as exc:
        BatchResponse.model_validate(
            {
                "batch_metadata": metadata(
                    n_institutions_with_genai=1, n_data_rows=2
                ),
                "data": [a, b],
            }
        )
    assert "vendor" in str(exc.value)


def test_invalid_metadata_data_row_count_mismatch():
    """Consistency check #6: n_data_rows must match len(data)."""
    rows = [absent_row(row_id=1), absent_row(row_id=2, source_url="https://x.gov/2")]
    with pytest.raises(ValidationError) as exc:
        BatchResponse.model_validate(
            {"batch_metadata": metadata(n_data_rows=99), "data": rows}
        )
    assert "n_data_rows" in str(exc.value)


def test_invalid_metadata_n_institutions_with_genai_mismatch():
    rows = [absent_row(row_id=1)]
    with pytest.raises(ValidationError) as exc:
        BatchResponse.model_validate(
            {
                "batch_metadata": metadata(
                    n_institutions_with_genai=5, n_data_rows=1
                ),
                "data": rows,
            }
        )
    assert "n_institutions_with_genai" in str(exc.value)


def test_invalid_has_genai_no_but_row_confirms_activity():
    """Consistency check #3: has_genai_activity=no rules out confirms_activity rows."""
    bad = active_row(has_genai_activity="no")
    # The Group D fields are filled, so set genai_evidence -> confirms_absence to
    # isolate the cross-row check; but we want to test the institution-level rule,
    # so we keep confirms_activity and accept that the row-level _NA_ rule passes
    # (Group D non-_NA_ requires confirms_activity).
    with pytest.raises(ValidationError) as exc:
        BatchResponse.model_validate(
            {
                "batch_metadata": metadata(n_data_rows=1),
                "data": [bad],
            }
        )
    assert "has_genai_activity" in str(exc.value) or "confirms_activity" in str(
        exc.value
    )


def test_invalid_has_genai_yes_but_no_confirms_activity():
    """Consistency check #3: has_genai_activity=yes requires at least one
    confirms_activity row."""
    bad = absent_row(has_genai_activity="yes")
    with pytest.raises(ValidationError) as exc:
        BatchResponse.model_validate(
            {
                "batch_metadata": metadata(
                    n_institutions_with_genai=1, n_data_rows=1
                ),
                "data": [bad],
            }
        )
    assert "has_genai_activity" in str(exc.value) or "confirms_activity" in str(
        exc.value
    )


def test_invalid_extra_field_rejected():
    with pytest.raises(ValidationError):
        ContractRow.model_validate(absent_row(invented_extra_field="x"))


# ---------------------------------------------------------------------------
# BatchMetadata standalone
# ---------------------------------------------------------------------------


def test_batchmetadata_invalid_languages_pattern():
    with pytest.raises(ValidationError):
        BatchMetadata.model_validate(metadata(search_languages="english,french"))


def test_batchmetadata_invalid_timestamp():
    with pytest.raises(ValidationError):
        BatchMetadata.model_validate(metadata(response_timestamp="2026-05-08 14:30"))


# ---------------------------------------------------------------------------
# PersistedRow round-trip
# ---------------------------------------------------------------------------


def test_persistedrow_to_csv_dict_matches_data_columns():
    prov = RunProvenance(
        global_row_id="run-001-row-0001",
        run_id="20260508-test",
        run_model="gpt-5-nano",
        run_tool="g3o.extract",
        run_date="2026-05-08",
    )
    row = ContractRow.model_validate(active_row())
    persisted = PersistedRow(provenance=prov, row=row)

    csv_dict = persisted.to_csv_dict()
    assert list(csv_dict.keys()) == DATA_COLUMNS
    assert csv_dict["global_row_id"] == "run-001-row-0001"
    assert csv_dict["run_model"] == "gpt-5-nano"
    assert csv_dict["activity_name"] == "Internal Copilot pilot"


def test_proposed_adoption_stage_validates():
    """`proposed` (exploratory intent, no concrete commitment) is a valid stage
    — introduced 2026-07 (PI decision) so hedged GenAI intentions are captured
    below `announced` instead of dropped to `unclear`."""
    ContractRow.model_validate(active_row(adoption_stage="proposed"))


# ---------------------------------------------------------------------------
# `run_date` calendar validity on the two provenance blocks
#
# ``ISO_DATE_PATTERN`` only proves the *shape* ``\d{4}-\d{2}-\d{2}``, so
# ``2026-02-30`` and ``2026-13-01`` satisfied it and reached the CSV as
# provenance. These two blocks are the safe place to enforce real calendar
# dates: G3O authors them itself at write time (``g3o/persist/writer.py``,
# from ``utc_today_iso()``), and neither appears in ``BatchResponse`` or
# ``ConsolidatedInstitutionResponse`` — so no LLM-produced value can trip
# them, and a raise here means a G3O bug rather than a discarded finding.
# The equivalent validators on the model-authored date fields were cut from
# this change for exactly that reason; see the PR discussion.
# ---------------------------------------------------------------------------


PROVENANCE_MODELS = (RunProvenance, ValidationProvenance)


def _provenance(run_date: str) -> dict[str, Any]:
    return {
        "global_row_id": "run-001-row-0001",
        "run_id": "20260508-test",
        "run_model": "gpt-5-nano",
        "run_tool": "g3o.extract",
        "run_date": run_date,
    }


@pytest.mark.parametrize("model", PROVENANCE_MODELS)
@pytest.mark.parametrize("run_date", ["2026-02-30", "2026-13-01", "2026-00-10"])
def test_provenance_rejects_shape_valid_but_impossible_run_date(model, run_date):
    with pytest.raises(ValidationError):
        model.model_validate(_provenance(run_date))


@pytest.mark.parametrize("model", PROVENANCE_MODELS)
@pytest.mark.parametrize("run_date", ["2026-05-08", "2024-02-29", "2026-12-31"])
def test_provenance_accepts_real_run_dates(model, run_date):
    """Including a genuine leap day, which a naive month-length check would drop."""
    assert model.model_validate(_provenance(run_date)).run_date == run_date


@pytest.mark.parametrize("model", PROVENANCE_MODELS)
def test_provenance_still_rejects_malformed_run_date_shape(model):
    """The pattern constraint is unchanged and still runs first."""
    with pytest.raises(ValidationError):
        model.model_validate(_provenance("08/05/2026"))
