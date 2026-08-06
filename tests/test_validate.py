"""Tests for `g3o.validate` — Stage 6 consolidation client / driver / QC.

Mocks the OpenAI Batch API at the ``g3o.common.batch_client`` boundary so no
real-time API calls occur. Real-data smoke tests are reserved for the
network-marked tier.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from g3o.common.batch_client import BatchJob, BatchResult
from g3o.common.contract import (
    NA,
    ConsolidatedInstitutionResponse,
    SourceRecord,
)
from g3o.validate import (
    OUTPUT_CONTRACT_TEXT,
    PROMPT_CACHE_KEY,
    RESPONSE_FORMAT,
    SYSTEM_MESSAGE,
    SYSTEM_PROMPT_TEXT,
    build_consolidate_job,
    build_consolidate_jobs,
    load_extract_outputs,
    make_consolidate_custom_id,
    parse_consolidate_result,
    qc_per_institution,
    qc_per_run,
    write_consolidated_output,
)

# ---------------------------------------------------------------------------
# Fixture builders (re-use the same shape conventions as
# tests/test_consolidated_contract.py)
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


def _yes_response(**overrides: Any) -> dict[str, Any]:
    base = {
        "consolidation_metadata": _meta(),
        "institution": _institution(),
        "activities": [_activity()],
        "sources": [_source()],
    }
    base.update(overrides)
    return base


def _stage5_row(**overrides: Any) -> dict[str, Any]:
    """A single Stage 5 ContractRow dict (one (institution × activity × source) triple)."""
    base = {
        "row_id": 1,
        "batch_id": "stage5-test",
        "institution_id": "INST-0001",
        "institution_name": "Test Ministry",
        "country": "Testland",
        "branch_of_government": "executive",
        "level_of_government": "national",
        "has_genai_activity": "yes",
        "institution_summary": "Internal Copilot pilot underway.",
        "institution_search_languages": "en",
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
        "source_title": "Test procurement",
        "source_publication_date": "2025-01",
        "source_access_date": "2026-05-08",
        "source_type": "procurement_tender",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": "confirms_activity",
        "source_snippet": "Procurement of 100 Microsoft 365 Copilot licenses.",
        "confidence": "high",
        "uncertainty_flags": "none",
    }
    base.update(overrides)
    return base


def _stage5_batch_response(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap rows in a valid ``BatchResponse`` envelope (Stage 5 shape)."""
    n_yes = sum(1 for r in rows if r.get("has_genai_activity") == "yes")
    return {
        "batch_metadata": {
            "batch_id": rows[0]["batch_id"],
            "chat_type": "web",
            "model_label": "gpt-5-nano",
            "response_timestamp": "2026-05-09T11:00:00Z",
            "n_institutions_in_batch": 1,
            "n_institutions_with_genai": 1 if n_yes else 0,
            "n_data_rows": len(rows),
            "search_languages": "en",
            "search_strategy_summary": "Test fixture",
            "notes": "none",
        },
        "data": rows,
    }


# ---------------------------------------------------------------------------
# Prompt loading + RESPONSE_FORMAT shape
# ---------------------------------------------------------------------------


def test_prompt_assets_loaded() -> None:
    assert "G3O Validation Agent" in SYSTEM_PROMPT_TEXT
    assert "Consolidation rules" in SYSTEM_PROMPT_TEXT
    # Markers from output_contract.md
    # Version-agnostic on purpose: this asserts the contract text is LOADED, and
    # the version is pinned properly by tests/test_contract_version_pin.py. A
    # literal "v1.0" here just fails every legitimate bump (it failed on v1.1).
    assert "G3O Validation Contract v" in OUTPUT_CONTRACT_TEXT
    assert "consolidation_metadata" in OUTPUT_CONTRACT_TEXT
    # System message concatenation worked
    assert SYSTEM_PROMPT_TEXT in SYSTEM_MESSAGE
    assert OUTPUT_CONTRACT_TEXT in SYSTEM_MESSAGE


def test_response_format_strict_no_refs() -> None:
    rf = RESPONSE_FORMAT
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    schema = rf["json_schema"]["schema"]
    assert schema.get("additionalProperties") is False

    def _has_ref(node: Any) -> bool:
        if isinstance(node, dict):
            if "$ref" in node or "$defs" in node:
                return True
            return any(_has_ref(v) for v in node.values())
        if isinstance(node, list):
            return any(_has_ref(v) for v in node)
        return False

    assert not _has_ref(schema)


# ---------------------------------------------------------------------------
# build_consolidate_job
# ---------------------------------------------------------------------------


def test_build_consolidate_job_minimal() -> None:
    inst_row = {"institution_id": "INST-0001", "institution_name": "Test Ministry"}
    job = build_consolidate_job(
        inst_row,
        [_stage5_row()],
        custom_id="INST-0001",
        n_input_pages=1,
    )
    assert isinstance(job, BatchJob)
    assert job.custom_id == "INST-0001"
    assert job.prompt_cache_key == PROMPT_CACHE_KEY
    assert job.metadata["stage"] == "6_validate"
    assert job.metadata["institution_id"] == "INST-0001"
    assert job.metadata["n_input_rows"] == 1
    assert job.response_format == RESPONSE_FORMAT
    assert len(job.messages) == 2
    assert job.messages[0]["role"] == "system"
    assert job.messages[1]["role"] == "user"
    user_msg = job.messages[1]["content"]
    assert "INST-0001" in user_msg
    assert "stage5_rows" in user_msg


def test_build_consolidate_job_requires_custom_id() -> None:
    with pytest.raises(ValueError, match="custom_id"):
        build_consolidate_job(
            {"institution_id": "INST-0001"},
            [_stage5_row()],
            custom_id="",
            n_input_pages=1,
        )


def test_build_consolidate_job_requires_input_rows() -> None:
    with pytest.raises(ValueError, match="input_rows"):
        build_consolidate_job(
            {"institution_id": "INST-0001"},
            [],
            custom_id="INST-0001",
            n_input_pages=1,
        )


def test_build_consolidate_job_requires_positive_pages() -> None:
    with pytest.raises(ValueError, match="n_input_pages"):
        build_consolidate_job(
            {"institution_id": "INST-0001"},
            [_stage5_row()],
            custom_id="INST-0001",
            n_input_pages=0,
        )


def test_build_consolidate_jobs_one_per_institution() -> None:
    inputs = [
        ({"institution_id": "INST-0001"}, [_stage5_row()], 1),
        (
            {"institution_id": "INST-0002"},
            [_stage5_row(institution_id="INST-0002", batch_id="b2")],
            1,
        ),
    ]
    jobs = build_consolidate_jobs(inputs)
    assert len(jobs) == 2
    assert {j.custom_id for j in jobs} == {"INST-0001", "INST-0002"}


def test_make_consolidate_custom_id_rejects_empty() -> None:
    with pytest.raises(ValueError, match="institution_id"):
        make_consolidate_custom_id("")


# ---------------------------------------------------------------------------
# parse_consolidate_result
# ---------------------------------------------------------------------------


def _result(
    *,
    success: bool = True,
    parsed_content: str | None = None,
    error: dict[str, Any] | None = None,
    custom_id: str = "INST-0001",
) -> BatchResult:
    """Wrap a content string into the BatchResult.parsed_content path."""
    if success and parsed_content is not None:
        response: dict[str, Any] | None = {
            "body": {"choices": [{"message": {"content": parsed_content}}]}
        }
    else:
        response = None
    return BatchResult(
        custom_id=custom_id,
        success=success,
        response=response,
        error=error,
    )


def test_parse_consolidate_result_happy() -> None:
    payload = _yes_response()
    result = _result(parsed_content=json.dumps(payload))
    response = parse_consolidate_result(result)
    assert isinstance(response, ConsolidatedInstitutionResponse)
    assert response.institution.institution_id == "INST-0001"
    assert len(response.activities) == 1


def test_parse_consolidate_result_failed_call_raises() -> None:
    result = _result(success=False, error={"code": "rate_limited"})
    with pytest.raises(RuntimeError, match="rate_limited"):
        parse_consolidate_result(result)


def test_parse_consolidate_result_empty_content_raises() -> None:
    result = _result(parsed_content="")
    with pytest.raises(RuntimeError, match="empty assistant content"):
        parse_consolidate_result(result)


def test_parse_consolidate_result_invalid_payload_raises() -> None:
    bad_payload = _yes_response()
    bad_payload["activities"][0]["activity_type"] = "_NA_"
    result = _result(parsed_content=json.dumps(bad_payload))
    with pytest.raises(ValidationError):
        parse_consolidate_result(result)


# ---------------------------------------------------------------------------
# Run-directory I/O
# ---------------------------------------------------------------------------


def _write_extract_jsons(institution_dir: Path, n_pages: int) -> None:
    extract_dir = institution_dir / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n_pages):
        rows = [
            _stage5_row(
                row_id=1,
                batch_id=f"page-{i}",
                source_url=f"https://example.gov/p{i}",
                source_snippet=f"Snippet from page {i}.",
            )
        ]
        (extract_dir / f"page-{i}.json").write_text(
            json.dumps(_stage5_batch_response(rows), ensure_ascii=False),
            encoding="utf-8",
        )


def test_load_extract_outputs_walks_directory(tmp_path: Path) -> None:
    institution_dir = tmp_path / "INST-0001"
    institution_dir.mkdir()
    _write_extract_jsons(institution_dir, n_pages=3)
    rows, n_pages = load_extract_outputs(institution_dir)
    assert n_pages == 3
    assert len(rows) == 3
    assert {r.source_url for r in rows} == {
        "https://example.gov/p0",
        "https://example.gov/p1",
        "https://example.gov/p2",
    }


def test_load_extract_outputs_missing_dir_returns_empty(tmp_path: Path) -> None:
    rows, n_pages = load_extract_outputs(tmp_path / "no-such-inst")
    assert rows == []
    assert n_pages == 0


def test_load_extract_outputs_validates_batch_response(tmp_path: Path) -> None:
    institution_dir = tmp_path / "INST-0001"
    extract_dir = institution_dir / "extract"
    extract_dir.mkdir(parents=True)
    (extract_dir / "bad.json").write_text(
        json.dumps({"batch_metadata": {}, "data": []}), encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_extract_outputs(institution_dir)


def test_write_consolidated_output_writes_canonical_path(tmp_path: Path) -> None:
    response = ConsolidatedInstitutionResponse.model_validate(_yes_response())
    out_path = write_consolidated_output(tmp_path, "INST-0001", response)
    assert out_path == tmp_path / "INST-0001" / "6_validate.json"
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["institution"]["institution_id"] == "INST-0001"
    # Round-trip: the persisted JSON revalidates.
    ConsolidatedInstitutionResponse.model_validate(payload)


# ---------------------------------------------------------------------------
# QC
# ---------------------------------------------------------------------------


def test_qc_per_institution_yes_response() -> None:
    response = ConsolidatedInstitutionResponse.model_validate(
        _yes_response(
            activities=[_activity(n_sources=2)],
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
            ],
        )
    )
    qc = qc_per_institution(response)
    assert qc["institution_id"] == "INST-0001"
    assert qc["has_genai_activity"] == "yes"
    assert qc["n_activities"] == 1
    assert qc["n_sources"] == 2
    assert qc["source_credibility"] == {"high": 1, "medium": 1}
    assert qc["source_type"] == {"procurement_tender": 1, "news_major": 1}
    assert qc["genai_evidence"] == {"confirms_activity": 2}
    assert qc["distinct_tools"] == ["Microsoft 365 Copilot"]
    assert qc["distinct_vendors"] == ["Microsoft"]
    assert qc["activities_with_uncertainty_flags"] == []
    assert qc["high_confidence_activities"] == ["A1"]


def test_qc_per_institution_no_response() -> None:
    response = ConsolidatedInstitutionResponse.model_validate(
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
                    genai_evidence="confirms_absence",
                    source_snippet="No GenAI mention.",
                )
            ],
        }
    )
    qc = qc_per_institution(response)
    assert qc["has_genai_activity"] == "no"
    assert qc["n_activities"] == 0
    assert qc["n_sources"] == 1
    assert qc["genai_evidence"] == {"confirms_absence": 1}
    assert qc["distinct_tools"] == []


def test_qc_per_institution_uncertainty_flags_surfaced() -> None:
    response = ConsolidatedInstitutionResponse.model_validate(
        _yes_response(
            activities=[
                _activity(
                    uncertainty_flags="stage_ambiguous;vendor_undisclosed",
                    confidence="medium",
                )
            ]
        )
    )
    qc = qc_per_institution(response)
    assert qc["activities_with_uncertainty_flags"] == ["A1"]
    assert qc["high_confidence_activities"] == []


def test_qc_per_run_aggregates_across_institutions(tmp_path: Path) -> None:
    # Two institutions with consolidated outputs, one without.
    for inst_id in ("INST-0001", "INST-0002"):
        d = tmp_path / inst_id
        d.mkdir()
        response = ConsolidatedInstitutionResponse.model_validate(
            _yes_response(
                consolidation_metadata=_meta(institution_id=inst_id),
                institution=_institution(institution_id=inst_id),
            )
        )
        write_consolidated_output(tmp_path, inst_id, response)

    # Empty institution — no 6_validate.json
    (tmp_path / "INST-0003").mkdir()
    # Parse-failure institution — invalid 6_validate.json
    bad_dir = tmp_path / "INST-0004"
    bad_dir.mkdir()
    (bad_dir / "6_validate.json").write_text(
        json.dumps({"institution": {"institution_id": "INST-0004"}}),
        encoding="utf-8",
    )

    qc = qc_per_run(tmp_path)
    assert qc["n_institutions_in_dir"] == 4
    assert qc["n_consolidated"] == 2
    assert qc["n_missing_validate_json"] == 1
    assert qc["n_parse_failed"] == 1
    assert qc["parse_failures"] == ["INST-0004"]
    assert qc["has_genai_activity"] == {"yes": 2}
    assert qc["total_activities"] == 2
    assert qc["total_sources"] == 2
    # Top-tools list-of-tuples
    top_tools = dict(qc["top_tools"])
    assert top_tools.get("Microsoft 365 Copilot") == 2


def test_qc_per_run_missing_run_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        qc_per_run(tmp_path / "no-such-run")


# ---------------------------------------------------------------------------
# SourceRecord — sanity round-trip via the validate surface
# ---------------------------------------------------------------------------


def test_source_record_round_trip_via_response() -> None:
    response = ConsolidatedInstitutionResponse.model_validate(_yes_response())
    s = response.sources[0]
    assert isinstance(s, SourceRecord)
    assert s.source_id == "S1"
    assert s.activity_id == "A1"
