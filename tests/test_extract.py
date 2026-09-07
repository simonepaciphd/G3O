"""Tests for ``g3o.extract`` (Stage 5)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from g3o.common.batch_client import BatchResult
from g3o.extract import (
    OUTPUT_CONTRACT_TEXT,
    PROMPT_CACHE_KEY,
    RESPONSE_FORMAT,
    SYSTEM_MESSAGE,
    SYSTEM_PROMPT_TEXT,
    build_extract_job,
    build_extract_jobs,
    make_custom_id,
    parse_extract_result,
    url_hash,
)
from g3o.scrape.render import FetchMetadata, RenderedPage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


INSTITUTION = {
    "institution_id": "INST-0042",
    "institution_name": "Ministry of Public Affairs",
    "country": "Testland",
    "branch_of_government": "executive",
    "level_of_government": "national",
}


def _make_page(
    *,
    url: str = "https://www.mpa.gov.tl/",
    access_date: str = "2026-05-09",
    text: str = "Welcome to the ministry. Nothing about generative AI here.",
    title: str = "Home",
) -> RenderedPage:
    return RenderedPage(
        url=url,
        text=text,
        title=title,
        content_type="html",
        fetch_metadata=FetchMetadata(
            access_date=access_date,
            http_status=200,
            final_url=url,
            fetch_method="html",
            elapsed_ms=10,
            wait_for=None,
        ),
    )


def _row_no_genai(
    *,
    institution: dict[str, Any] = INSTITUTION,
    source_url: str = "https://www.mpa.gov.tl/",
    source_access_date: str = "2026-05-09",
    row_id: int = 1,
    batch_id: str = "b1",
) -> dict[str, Any]:
    """A minimal valid 'no GenAI' contract row — every Group D field is _NA_."""
    return {
        "row_id": row_id,
        "batch_id": batch_id,
        "institution_id": institution["institution_id"],
        "institution_name": institution["institution_name"],
        "country": institution["country"],
        "branch_of_government": institution["branch_of_government"],
        "level_of_government": institution["level_of_government"],
        "has_genai_activity": "no",
        "institution_summary": "All supplied pages reviewed; no GenAI evidence found.",
        "institution_search_languages": "en",
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
        "source_url": source_url,
        "source_title": "Home",
        "source_publication_date": "2026-01-15",
        "source_access_date": source_access_date,
        "source_type": "official_gov",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": "confirms_absence",
        "source_snippet": "Page contains no mention of generative AI.",
        "confidence": "high",
        "uncertainty_flags": "none",
    }


def _meta(*, batch_id: str = "b1", n_data_rows: int = 1) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "chat_type": "web",
        "model_label": "gpt-5-nano",
        "response_timestamp": "2026-05-09T10:00:00Z",
        "n_institutions_in_batch": 1,
        "n_institutions_with_genai": 0,
        "n_data_rows": n_data_rows,
        "search_languages": "en",
        "search_strategy_summary": "URLs supplied by the pipeline.",
        "notes": "none",
    }


def _valid_batch_response_payload() -> dict[str, Any]:
    return {"batch_metadata": _meta(), "data": [_row_no_genai()]}


def _make_result(custom_id: str, content: dict[str, Any] | str) -> BatchResult:
    content_str = content if isinstance(content, str) else json.dumps(content)
    return BatchResult(
        custom_id=custom_id,
        success=True,
        response={
            "status_code": 200,
            "body": {"choices": [{"message": {"content": content_str}}]},
        },
        error=None,
        status_code=200,
    )


# ---------------------------------------------------------------------------
# Prompt-loading round-trip
# ---------------------------------------------------------------------------


def test_system_prompt_loaded_from_disk():
    assert "Global Government GenAI Observatory" in SYSTEM_PROMPT_TEXT
    assert "scrape-then-extract" in SYSTEM_PROMPT_TEXT.lower() or (
        "supplied page" in SYSTEM_PROMPT_TEXT
    )
    # Q6 (2026-05-09): JSON-output framing is in place; no Markdown framing left.
    assert "JSON object" in SYSTEM_PROMPT_TEXT
    assert "Markdown document" not in SYSTEM_PROMPT_TEXT


def test_output_contract_loaded_from_disk():
    # Q5 (2026-05-09): the Edge case A worked example is present. v2.3 re-scoped it
    # from two supplied pages to one, because the pipeline sends one page per job
    # (#55) — the institution and the phrasing are what this assertion is for.
    assert "supplied page is the Parliament of Belize" in OUTPUT_CONTRACT_TEXT
    # Q6: JSON-output framing in §1 of the contract.
    assert "ONE JSON object" in OUTPUT_CONTRACT_TEXT


def test_system_message_concatenates_both():
    assert SYSTEM_PROMPT_TEXT in SYSTEM_MESSAGE
    assert OUTPUT_CONTRACT_TEXT in SYSTEM_MESSAGE


# ---------------------------------------------------------------------------
# RESPONSE_FORMAT shape
# ---------------------------------------------------------------------------


def test_response_format_strict_json_schema():
    assert RESPONSE_FORMAT["type"] == "json_schema"
    assert RESPONSE_FORMAT["json_schema"]["strict"] is True
    schema = RESPONSE_FORMAT["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    # $defs must be inlined for OpenAI strict-mode robustness.
    assert "$defs" not in schema
    # Top-level batch_metadata + data both present.
    props = schema["properties"]
    assert "batch_metadata" in props
    assert "data" in props
    # The 'data' array minItems=1 mirrors BatchResponse's Field(min_length=1).
    assert props["data"]["minItems"] == 1


def test_response_format_no_dangling_refs():
    """No raw $ref strings should remain after _inline_defs."""
    payload = json.dumps(RESPONSE_FORMAT)
    assert "$ref" not in payload


# ---------------------------------------------------------------------------
# build_extract_job — JSONL job shape
# ---------------------------------------------------------------------------


def test_build_extract_job_shape():
    page = _make_page()
    job = build_extract_job(
        INSTITUTION,
        page,
        custom_id="inst-0042::abcdef",
        batch_id="b1",
        institution_search_languages="en,fr",
    )
    assert job.custom_id == "inst-0042::abcdef"
    assert len(job.messages) == 2
    assert job.messages[0]["role"] == "system"
    assert job.messages[1]["role"] == "user"
    user_content = job.messages[1]["content"]
    assert page.url in user_content
    assert page.title in user_content
    assert "2026-05-09" in user_content  # access_date injected per Q1=a
    assert INSTITUTION["institution_name"] in user_content
    assert "en,fr" in user_content
    assert job.response_format == RESPONSE_FORMAT
    assert job.prompt_cache_key == PROMPT_CACHE_KEY
    assert job.metadata["stage"] == "5_extract"
    assert job.metadata["institution_id"] == "INST-0042"
    assert job.metadata["source_url"] == page.url


def test_build_extract_job_requires_custom_id():
    with pytest.raises(ValueError, match="custom_id"):
        build_extract_job(
            INSTITUTION,
            _make_page(),
            custom_id="",
            batch_id="b1",
            institution_search_languages="en",
        )


def test_build_extract_job_requires_search_languages():
    with pytest.raises(ValueError, match="institution_search_languages"):
        build_extract_job(
            INSTITUTION,
            _make_page(),
            custom_id="x::y",
            batch_id="b1",
            institution_search_languages="",
        )


# ---------------------------------------------------------------------------
# build_extract_jobs — custom_id format
# ---------------------------------------------------------------------------


def test_url_hash_is_md5():
    import hashlib

    assert url_hash("https://x.gov/") == hashlib.md5(b"https://x.gov/").hexdigest()


def test_make_custom_id_format():
    cid = make_custom_id("INST-0042", "https://www.mpa.gov.tl/")
    assert cid.startswith("INST-0042::")
    parts = cid.split("::")
    assert len(parts) == 2
    assert len(parts[1]) == 32  # md5 hex length


def test_make_custom_id_rejects_empty():
    with pytest.raises(ValueError):
        make_custom_id("", "https://x/")
    with pytest.raises(ValueError):
        make_custom_id("INST-1", "")


def test_build_extract_jobs_yields_one_per_pair():
    pages = [
        _make_page(url="https://www.mpa.gov.tl/"),
        _make_page(url="https://www.mpa.gov.tl/news/2025/ai-pilot"),
    ]
    pairs = [(INSTITUTION, p) for p in pages]
    jobs = build_extract_jobs(
        pairs, batch_id="b1", institution_search_languages="en"
    )
    assert len(jobs) == 2
    assert all(j.custom_id.startswith("INST-0042::") for j in jobs)
    assert jobs[0].custom_id != jobs[1].custom_id  # url_hash differs


# ---------------------------------------------------------------------------
# parse_extract_result — happy path
# ---------------------------------------------------------------------------


def test_parse_extract_result_happy_path():
    payload = _valid_batch_response_payload()
    result = _make_result("INST-0042::abc", payload)
    parsed = parse_extract_result(result, scrape_access_date="2026-05-09")
    assert parsed.batch_metadata.batch_id == "b1"
    assert len(parsed.data) == 1
    assert parsed.data[0].source_access_date == "2026-05-09"


def test_parse_extract_result_failure_raises():
    bad = BatchResult(
        custom_id="INST-0042::abc",
        success=False,
        response=None,
        error={"code": "rate_limited", "message": "boom"},
    )
    with pytest.raises(RuntimeError, match="Stage 5"):
        parse_extract_result(bad, scrape_access_date="2026-05-09")


def test_parse_extract_result_empty_content_raises():
    result = BatchResult(
        custom_id="INST-0042::abc",
        success=True,
        response={"status_code": 200, "body": {"choices": [{"message": {"content": ""}}]}},
        error=None,
    )
    with pytest.raises(RuntimeError, match="empty assistant content"):
        parse_extract_result(result, scrape_access_date="2026-05-09")


# ---------------------------------------------------------------------------
# parse_extract_result — invalid payloads
# ---------------------------------------------------------------------------


def test_parse_extract_result_invalid_enum_raises():
    payload = _valid_batch_response_payload()
    payload["data"][0]["has_genai_activity"] = "maybe"  # not in Literal
    result = _make_result("INST-0042::abc", payload)
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date="2026-05-09")


def test_parse_extract_result_missing_rows_raises():
    payload = _valid_batch_response_payload()
    payload["data"] = []  # BatchResponse requires min_length=1
    result = _make_result("INST-0042::abc", payload)
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date="2026-05-09")


def test_parse_extract_result_group_d_inconsistency_raises():
    payload = _valid_batch_response_payload()
    # Activity field non-_NA_ on a confirms_absence row.
    payload["data"][0]["activity_name"] = "Some pilot"
    result = _make_result("INST-0042::abc", payload)
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date="2026-05-09")


# ---------------------------------------------------------------------------
# parse_extract_result — access-date contract (Q1=a)
# ---------------------------------------------------------------------------


def test_parse_extract_result_access_date_mismatch_raises():
    """Q1=a contract: LLM must copy scrape_access_date verbatim; mismatch → ValueError."""
    payload = _valid_batch_response_payload()
    payload["data"][0]["source_access_date"] = "2026-05-08"  # one day off
    result = _make_result("INST-0042::abc", payload)
    with pytest.raises(ValueError, match="source_access_date"):
        parse_extract_result(result, scrape_access_date="2026-05-09")


def test_parse_extract_result_access_date_match_passes():
    payload = _valid_batch_response_payload()
    result = _make_result("INST-0042::abc", payload)
    parsed = parse_extract_result(result, scrape_access_date="2026-05-09")
    assert all(r.source_access_date == "2026-05-09" for r in parsed.data)
