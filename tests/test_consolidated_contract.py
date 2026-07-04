"""Tests for the Stage 6 consolidated-institution surface in `g3o.common.contract`."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from g3o.common.contract import (
    NA,
    ConsolidatedActivity,
    ConsolidatedInstitution,
    ConsolidatedInstitutionResponse,
    ConsolidationMetadata,
    PersistedActivity,
    PersistedSource,
    SourceRecord,
    ValidationProvenance,
)
from g3o.common.schema import ACTIVITY_COLUMNS, ACTIVITY_SOURCE_COLUMNS

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _meta(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "institution_id": "INST-0001",
        "n_input_pages": 3,
        "n_input_rows": 5,
        "response_timestamp": "2026-05-09T12:00:00Z",
        "model_label": "gpt-5-nano",
        "notes": "none",
    }
    base.update(overrides)
    return base


def _institution(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
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
    base: dict[str, Any] = {
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
    source_id: str = "S1",
    activity_id: str = "A1",
    **overrides: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
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


def _provenance(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "global_row_id": "20260509-presweep::INST-0001::A1",
        "run_id": "20260509-presweep",
        "run_model": "gpt-5-nano",
        "run_tool": "g3o.validate.consolidate",
        "run_date": "2026-05-09",
    }
    base.update(overrides)
    return base


def _yes_response(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "consolidation_metadata": _meta(),
        "institution": _institution(),
        "activities": [_activity()],
        "sources": [_source()],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_yes_response_minimal_valid() -> None:
    r = ConsolidatedInstitutionResponse.model_validate(_yes_response())
    assert r.institution.has_genai_activity == "yes"
    assert len(r.activities) == 1
    assert len(r.sources) == 1
    assert r.activities[0].activity_id == "A1"
    assert r.sources[0].activity_id == "A1"


def test_no_response_valid() -> None:
    r = ConsolidatedInstitutionResponse.model_validate(
        {
            "consolidation_metadata": _meta(),
            "institution": _institution(
                has_genai_activity="no",
                institution_summary="No GenAI evidence in supplied texts.",
            ),
            "activities": [],
            "sources": [
                _source(
                    source_id="S1",
                    activity_id=NA,
                    source_url="https://example.gov/",
                    source_type="official_gov",
                    genai_evidence="confirms_absence",
                    source_snippet="Page contains no mention of generative AI.",
                ),
                _source(
                    source_id="S2",
                    activity_id=NA,
                    source_url="https://example.gov/news/",
                    source_type="official_gov",
                    genai_evidence="confirms_absence",
                    source_snippet="News archive contains no GenAI mention.",
                ),
            ],
        }
    )
    assert r.institution.has_genai_activity == "no"
    assert r.activities == []
    assert all(s.activity_id == NA for s in r.sources)


def test_unclear_response_valid() -> None:
    r = ConsolidatedInstitutionResponse.model_validate(
        {
            "consolidation_metadata": _meta(),
            "institution": _institution(
                has_genai_activity="unclear",
                institution_summary="Mentions of AI but unclear if GenAI specifically.",
            ),
            "activities": [],
            "sources": [
                _source(
                    source_id="S1",
                    activity_id=NA,
                    genai_evidence="ambiguous",
                    source_snippet="Mentions 'AI tools' without specifying GenAI.",
                )
            ],
        }
    )
    assert r.institution.has_genai_activity == "unclear"


def test_two_activities_three_sources() -> None:
    r = ConsolidatedInstitutionResponse.model_validate(
        _yes_response(
            activities=[
                _activity(activity_id="A1", n_sources=2),
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
                ),
            ],
            sources=[
                _source(source_id="S1", activity_id="A1"),
                _source(
                    source_id="S2",
                    activity_id="A1",
                    source_url="https://example.gov/news/copilot",
                    source_type="news_major",
                    source_credibility="medium",
                ),
                _source(
                    source_id="S3",
                    activity_id="A2",
                    source_url="https://example.gov/services/chatbot",
                    source_type="official_gov",
                ),
            ],
        )
    )
    assert len(r.activities) == 2
    assert len(r.sources) == 3


# ---------------------------------------------------------------------------
# Cross-row invariants
# ---------------------------------------------------------------------------


def test_yes_with_no_activities_rejected() -> None:
    with pytest.raises(ValidationError, match="has_genai_activity=yes but activities is empty"):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(activities=[], sources=[_source(genai_evidence="confirms_activity")])
        )


def test_no_with_activity_rejected() -> None:
    with pytest.raises(
        ValidationError, match="has_genai_activity=no but activities is non-empty"
    ):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(institution=_institution(has_genai_activity="no"))
        )


def test_no_with_non_absence_source_rejected() -> None:
    with pytest.raises(ValidationError, match="confirms_absence; offenders"):
        ConsolidatedInstitutionResponse.model_validate(
            {
                "consolidation_metadata": _meta(),
                "institution": _institution(has_genai_activity="no"),
                "activities": [],
                "sources": [
                    _source(
                        source_id="S1",
                        activity_id=NA,
                        genai_evidence="ambiguous",
                    )
                ],
            }
        )


def test_unclear_with_confirms_activity_rejected() -> None:
    with pytest.raises(
        ValidationError, match="unclear but a source has genai_evidence=confirms_activity"
    ):
        ConsolidatedInstitutionResponse.model_validate(
            {
                "consolidation_metadata": _meta(),
                "institution": _institution(has_genai_activity="unclear"),
                "activities": [],
                "sources": [_source(source_id="S1", activity_id=NA)],
            }
        )


def test_yes_without_confirms_activity_source_rejected() -> None:
    # All sources are confirms_absence, but has_genai_activity=yes — invalid.
    with pytest.raises(
        ValidationError,
        match="yes but no source has genai_evidence=confirms_activity",
    ):
        ConsolidatedInstitutionResponse.model_validate(
            {
                "consolidation_metadata": _meta(),
                "institution": _institution(has_genai_activity="yes"),
                "activities": [_activity()],
                "sources": [
                    _source(
                        source_id="S1",
                        activity_id=NA,
                        genai_evidence="confirms_absence",
                    )
                ],
            }
        )


# ---------------------------------------------------------------------------
# ID sequencing
# ---------------------------------------------------------------------------


def test_activity_id_sequence_must_start_at_a1() -> None:
    with pytest.raises(ValidationError, match="activity_id sequence must be"):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(
                activities=[_activity(activity_id="A2")],
                sources=[_source(activity_id="A2")],
            )
        )


def test_activity_id_sequence_must_be_gapless() -> None:
    with pytest.raises(ValidationError, match="activity_id sequence must be"):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(
                activities=[_activity(activity_id="A1"), _activity(activity_id="A3")],
                sources=[_source(activity_id="A1"), _source(source_id="S2", activity_id="A3")],
            )
        )


def test_source_id_sequence_must_be_gapless() -> None:
    with pytest.raises(ValidationError, match="source_id sequence must be"):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(
                sources=[
                    _source(source_id="S1"),
                    _source(source_id="S3", source_url="https://example.gov/x"),
                ],
            )
        )


def test_activity_id_pattern_rejects_lowercase() -> None:
    with pytest.raises(ValidationError):
        ConsolidatedActivity.model_validate(_activity(activity_id="a1"))


def test_source_activity_id_pattern_accepts_na() -> None:
    SourceRecord.model_validate(_source(source_id="S1", activity_id=NA))


# ---------------------------------------------------------------------------
# Source ↔ Activity linkage
# ---------------------------------------------------------------------------


def test_source_activity_id_must_match_real_activity() -> None:
    with pytest.raises(
        ValidationError, match="does not match any ConsolidatedActivity"
    ):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(sources=[_source(activity_id="A2")])
        )


def test_source_with_activity_must_be_confirms_activity() -> None:
    # yes/no/unclear passes (S1 supplies confirms_activity); source-link fires
    # on S2 because it links to A1 but is ambiguous, not confirms_activity.
    with pytest.raises(
        ValidationError, match="requires genai_evidence=confirms_activity"
    ):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(
                sources=[
                    _source(source_id="S1", activity_id="A1"),
                    _source(
                        source_id="S2",
                        activity_id="A1",
                        source_url="https://example.gov/news",
                        genai_evidence="ambiguous",
                    ),
                ],
            )
        )


def test_na_activity_id_with_confirms_activity_rejected() -> None:
    # The validator that owns this check is the source/activity-link validator;
    # the message is specific about the _NA_ case.
    with pytest.raises(
        ValidationError, match="activity_id=_NA_ but genai_evidence=confirms_activity"
    ):
        ConsolidatedInstitutionResponse.model_validate(
            {
                "consolidation_metadata": _meta(),
                "institution": _institution(has_genai_activity="yes"),
                "activities": [_activity()],
                "sources": [
                    _source(activity_id="A1"),
                    _source(
                        source_id="S2",
                        activity_id=NA,
                        source_url="https://example.gov/orphan",
                        genai_evidence="confirms_activity",
                    ),
                ],
            }
        )


# ---------------------------------------------------------------------------
# n_sources / activity-coverage
# ---------------------------------------------------------------------------


def test_n_sources_must_match_actual_count() -> None:
    with pytest.raises(ValidationError, match="n_sources=2 but 1 sources reference it"):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(activities=[_activity(n_sources=2)])
        )


def test_activity_with_no_sources_rejected() -> None:
    # yes/no/unclear passes (A1 is covered by S1), then coverage fires for A2.
    with pytest.raises(ValidationError, match="A2 has no supporting sources"):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(
                activities=[
                    _activity(activity_id="A1", n_sources=1),
                    _activity(
                        activity_id="A2",
                        activity_name="Other activity",
                        n_sources=1,
                    ),
                ],
                sources=[_source(source_id="S1", activity_id="A1")],
            )
        )


# ---------------------------------------------------------------------------
# Group D no-_NA_ rule on ConsolidatedActivity
# ---------------------------------------------------------------------------


def test_consolidated_activity_rejects_na_in_free_string_field() -> None:
    with pytest.raises(ValidationError, match=r"tool_name='_NA_' not permitted"):
        ConsolidatedActivity.model_validate(_activity(tool_name="_NA_"))


def test_consolidated_activity_rejects_na_in_enum_field() -> None:
    # Literal enums reject _NA_ before the model_validator runs; Pydantic
    # raises a Literal-mismatch error.
    with pytest.raises(ValidationError):
        ConsolidatedActivity.model_validate(_activity(activity_type="_NA_"))


# ---------------------------------------------------------------------------
# uncertainty_flags
# ---------------------------------------------------------------------------


def test_uncertainty_flags_none_accepted() -> None:
    ConsolidatedActivity.model_validate(_activity(uncertainty_flags="none"))


def test_uncertainty_flags_multi_accepted() -> None:
    ConsolidatedActivity.model_validate(
        _activity(uncertainty_flags="stage_ambiguous;vendor_undisclosed")
    )


def test_uncertainty_flags_with_space_rejected() -> None:
    with pytest.raises(ValidationError, match="must not contain spaces"):
        ConsolidatedActivity.model_validate(
            _activity(uncertainty_flags="stage_ambiguous; vendor_undisclosed")
        )


def test_uncertainty_flags_unknown_token_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown uncertainty flag"):
        ConsolidatedActivity.model_validate(
            _activity(uncertainty_flags="not_in_vocab")
        )


# ---------------------------------------------------------------------------
# Metadata link
# ---------------------------------------------------------------------------


def test_metadata_institution_id_must_match_institution() -> None:
    with pytest.raises(ValidationError, match="does not match institution.institution_id"):
        ConsolidatedInstitutionResponse.model_validate(
            _yes_response(consolidation_metadata=_meta(institution_id="INST-OTHER"))
        )


def test_metadata_response_timestamp_pattern() -> None:
    # Bad timestamp format must be rejected.
    with pytest.raises(ValidationError):
        ConsolidationMetadata.model_validate(
            _meta(response_timestamp="2026-05-09 12:00:00")
        )


# ---------------------------------------------------------------------------
# CSV envelopes
# ---------------------------------------------------------------------------


def test_persisted_activity_to_csv_dict_matches_columns() -> None:
    pa = PersistedActivity(
        provenance=ValidationProvenance.model_validate(_provenance()),
        institution=ConsolidatedInstitution.model_validate(_institution()),
        activity=ConsolidatedActivity.model_validate(_activity()),
    )
    row = pa.to_csv_dict()
    assert list(row.keys()) == ACTIVITY_COLUMNS
    assert row["institution_id"] == "INST-0001"
    assert row["activity_id"] == "A1"
    assert row["n_sources"] == 1
    assert row["confidence"] == "high"
    assert row["run_tool"] == "g3o.validate.consolidate"


def test_persisted_source_to_csv_dict_matches_columns() -> None:
    ps = PersistedSource(
        provenance=ValidationProvenance.model_validate(
            _provenance(global_row_id="20260509-presweep::INST-0001::S1")
        ),
        institution_id="INST-0001",
        source=SourceRecord.model_validate(_source()),
    )
    row = ps.to_csv_dict()
    assert list(row.keys()) == ACTIVITY_SOURCE_COLUMNS
    assert row["institution_id"] == "INST-0001"
    assert row["activity_id"] == "A1"
    assert row["source_id"] == "S1"
    assert row["genai_evidence"] == "confirms_activity"


def test_persisted_source_handles_na_activity_id() -> None:
    ps = PersistedSource(
        provenance=ValidationProvenance.model_validate(
            _provenance(global_row_id="20260509-presweep::INST-0001::S1")
        ),
        institution_id="INST-0001",
        source=SourceRecord.model_validate(
            _source(activity_id=NA, genai_evidence="confirms_absence")
        ),
    )
    row = ps.to_csv_dict()
    assert row["activity_id"] == NA
    assert row["genai_evidence"] == "confirms_absence"


def test_proposed_adoption_stage_validates_consolidated() -> None:
    """`proposed` is a valid consolidated stage (introduced 2026-07, PI decision)."""
    ConsolidatedInstitutionResponse.model_validate(
        _yes_response(activities=[_activity(adoption_stage="proposed")])
    )
