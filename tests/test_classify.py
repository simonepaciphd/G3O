"""Tests for `g3o.classify.{official_site,url_triage}` (Stages 2 + 3)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from g3o.classify.official_site import (
    RESPONSE_FORMAT as OFFICIAL_SITE_FORMAT,
)
from g3o.classify.official_site import (
    OfficialSiteResult,
    build_official_site_job,
    parse_official_site_result,
)
from g3o.classify.url_triage import (
    RESPONSE_FORMAT as TRIAGE_FORMAT,
)
from g3o.classify.url_triage import (
    URLDecision,
    URLTriageResult,
    build_triage_job,
    match_triage_decisions,
    parse_triage_result,
)
from g3o.common.batch_client import BatchResult

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

CANDIDATE_URLS = [
    "https://www.mpa.gov.tl/",
    "https://en.wikipedia.org/wiki/Ministry_of_Public_Affairs_(Testland)",
    "https://www.mpa.gov.tl/news/2025/ai-pilot",
    "https://news.example.com/testland-ministry-ai",
]


def _make_result(custom_id: str, content: dict | str) -> BatchResult:
    """Build a successful BatchResult whose assistant content is `content`."""
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
# Stage 2 — OfficialSiteResult model
# ---------------------------------------------------------------------------


def test_official_site_result_with_url():
    r = OfficialSiteResult.model_validate(
        {
            "url": "https://www.mpa.gov.tl/",
            "confidence": "high",
            "rationale": "Official .gov.tl domain landing page naming the ministry.",
        }
    )
    assert r.url == "https://www.mpa.gov.tl/"
    assert r.confidence == "high"


def test_official_site_result_with_null_url():
    r = OfficialSiteResult.model_validate(
        {
            "url": None,
            "confidence": "none",
            "rationale": "No candidate is on a government-controlled domain.",
        }
    )
    assert r.url is None
    assert r.confidence == "none"


def test_official_site_result_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        OfficialSiteResult.model_validate(
            {"url": None, "confidence": "very_high", "rationale": "x"}
        )


def test_official_site_result_rejects_long_rationale():
    with pytest.raises(ValidationError):
        OfficialSiteResult.model_validate(
            {"url": None, "confidence": "none", "rationale": "x" * 300}
        )


def test_official_site_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        OfficialSiteResult.model_validate(
            {
                "url": None,
                "confidence": "none",
                "rationale": "x",
                "extra_invented": "y",
            }
        )


# ---------------------------------------------------------------------------
# Stage 2 — build_official_site_job
# ---------------------------------------------------------------------------


def test_build_official_site_job_shape():
    job = build_official_site_job(
        INSTITUTION, CANDIDATE_URLS, custom_id="inst-0042-stage2"
    )
    assert job.custom_id == "inst-0042-stage2"
    assert len(job.messages) == 2
    assert job.messages[0]["role"] == "system"
    assert job.messages[1]["role"] == "user"
    assert job.response_format == OFFICIAL_SITE_FORMAT
    assert job.prompt_cache_key.startswith("g3o.classify.official_site")
    assert job.metadata["stage"] == "2_official_site"
    assert job.metadata["institution_id"] == "INST-0042"
    # User prompt must embed the candidate URLs and the institution name.
    user_content = job.messages[1]["content"]
    assert INSTITUTION["institution_name"] in user_content
    for url in CANDIDATE_URLS:
        assert url in user_content


def test_build_official_site_job_requires_custom_id():
    with pytest.raises(ValueError, match="custom_id"):
        build_official_site_job(INSTITUTION, CANDIDATE_URLS, custom_id="")


# ---------------------------------------------------------------------------
# Stage 2 — parse_official_site_result
# ---------------------------------------------------------------------------


def test_parse_official_site_success():
    payload = {
        "url": "https://www.mpa.gov.tl/",
        "confidence": "high",
        "rationale": "Official domain landing page naming the ministry.",
    }
    result = _make_result("inst-0042-stage2", payload)
    parsed = parse_official_site_result(result)
    assert parsed.url == "https://www.mpa.gov.tl/"
    assert parsed.confidence == "high"


def test_parse_official_site_failure_raises():
    bad = BatchResult(
        custom_id="inst-0042-stage2",
        success=False,
        response=None,
        error={"code": "rate_limited", "message": "boom"},
    )
    with pytest.raises(RuntimeError, match="Stage 2"):
        parse_official_site_result(bad)


def test_parse_official_site_invalid_payload_raises():
    bad_payload = {"url": "x", "confidence": "not_a_real_value", "rationale": "y"}
    result = _make_result("inst-0042-stage2", bad_payload)
    with pytest.raises(ValidationError):
        parse_official_site_result(result)


def test_parse_official_site_malformed_json_raises_descriptive_runtime_error():
    """Malformed assistant JSON must surface stage + custom_id in the error
    so consolidate.py / presweep/ logs identify which institution failed."""
    result = _make_result("inst-0042-stage2", "{not valid json at all")
    with pytest.raises(RuntimeError, match=r"Stage 2 parse failed for custom_id=inst-0042-stage2"):
        parse_official_site_result(result)


# ---------------------------------------------------------------------------
# Stage 3 — URLDecision / URLTriageResult models
# ---------------------------------------------------------------------------


def test_url_triage_result_valid():
    r = URLTriageResult.model_validate(
        {
            "decisions": [
                {"url": CANDIDATE_URLS[0], "decision": "keep", "rationale": "official site"},
                {"url": CANDIDATE_URLS[1], "decision": "drop", "rationale": "wikipedia"},
            ]
        }
    )
    assert len(r.decisions) == 2
    assert r.decisions[0].decision == "keep"


def test_url_triage_empty_decisions_allowed():
    """Empty list is structurally valid; callers using expected_urls can detect it."""
    r = URLTriageResult.model_validate({"decisions": []})
    assert r.decisions == []


def test_url_triage_rejects_bad_decision_enum():
    with pytest.raises(ValidationError):
        URLDecision.model_validate(
            {"url": "https://x.gov/", "decision": "maybe", "rationale": "ambiguous"}
        )


def test_url_triage_duplicate_urls_allowed_and_salvaged():
    """Duplicates are no longer a fatal model-level error. The structural model
    accepts them; index matching salvages the clean position and records the
    duplicate as one per-URL ``duplicate_url`` casualty."""
    triage = URLTriageResult.model_validate(
        {
            "decisions": [
                {"url": "https://x.gov/", "decision": "keep", "rationale": "a"},
                {"url": "https://x.gov/", "decision": "drop", "rationale": "b"},
            ]
        }
    )
    assert len(triage.decisions) == 2  # model no longer rejects the dupe

    match = match_triage_decisions(["https://x.gov/", "https://y.gov/"], triage)
    # Position 0 (x.gov) matches its candidate and is salvaged.
    assert [d.url for d in match.decisions] == ["https://x.gov/"]
    # Position 1 echoes x.gov again where y.gov was expected → duplicate_url.
    assert len(match.attrition) == 1
    cas = match.attrition[0]
    assert (cas.url, cas.reason) == ("https://y.gov/", "duplicate_url")


# ---------------------------------------------------------------------------
# Stage 3 — build_triage_job
# ---------------------------------------------------------------------------


def test_build_triage_job_shape():
    job = build_triage_job(
        INSTITUTION,
        CANDIDATE_URLS,
        official_site="https://www.mpa.gov.tl/",
        custom_id="inst-0042-stage3",
    )
    assert job.custom_id == "inst-0042-stage3"
    assert job.response_format == TRIAGE_FORMAT
    assert job.prompt_cache_key.startswith("g3o.classify.url_triage")
    assert job.metadata["stage"] == "3_url_triage"
    assert job.metadata["n_candidate_urls"] == len(CANDIDATE_URLS)
    user_content = job.messages[1]["content"]
    for url in CANDIDATE_URLS:
        assert url in user_content
    assert "https://www.mpa.gov.tl/" in user_content


def test_build_triage_job_with_null_official_site():
    job = build_triage_job(
        INSTITUTION,
        CANDIDATE_URLS,
        official_site=None,
        custom_id="inst-0042-stage3",
    )
    assert "null" in job.messages[1]["content"]


def test_build_triage_job_rejects_empty_urls():
    with pytest.raises(ValueError, match="non-empty"):
        build_triage_job(
            INSTITUTION, [], official_site=None, custom_id="inst-0042-stage3"
        )


# ---------------------------------------------------------------------------
# Stage 3 — parse_triage_result
# ---------------------------------------------------------------------------


def test_parse_triage_success():
    payload = {
        "decisions": [
            {"url": u, "decision": "keep" if i < 3 else "drop", "rationale": "r"}
            for i, u in enumerate(CANDIDATE_URLS)
        ]
    }
    result = _make_result("inst-0042-stage3", payload)
    parsed = parse_triage_result(result, expected_urls=CANDIDATE_URLS)
    assert len(parsed.decisions) == len(CANDIDATE_URLS)
    assert sum(d.decision == "keep" for d in parsed.decisions) == 3


def test_parse_triage_detects_missing_url():
    """A short response (1 decision for 4 candidates) is salvaged, not raised:
    the one matching decision is kept and the three unmatched candidates each
    get a ``missing_decision`` casualty."""
    payload = {
        "decisions": [
            {"url": CANDIDATE_URLS[0], "decision": "keep", "rationale": "r"}
        ]
    }
    result = _make_result("inst-0042-stage3", payload)
    match = match_triage_decisions(CANDIDATE_URLS, parse_triage_result(result))

    assert [d.url for d in match.decisions] == [CANDIDATE_URLS[0]]
    assert [(c.url, c.reason) for c in match.attrition] == [
        (u, "missing_decision") for u in CANDIDATE_URLS[1:]
    ]


def test_parse_triage_detects_invented_url():
    """An invented URL at position 0 mismatches its candidate and is dropped
    (never salvaged, so never scraped); the remaining candidates have no
    decision at all. Nothing is kept and the invented string never surfaces as
    a candidate — it lives only in the mismatch casualty's detail."""
    payload = {
        "decisions": [
            {"url": "https://invented.gov/", "decision": "keep", "rationale": "r"}
        ]
    }
    result = _make_result("inst-0042-stage3", payload)
    match = match_triage_decisions(CANDIDATE_URLS, parse_triage_result(result))

    assert match.decisions == []
    assert match.kept_urls == []
    assert "https://invented.gov/" not in match.kept_urls
    assert [(c.url, c.reason) for c in match.attrition] == [
        (CANDIDATE_URLS[0], "url_mismatch"),
        (CANDIDATE_URLS[1], "missing_decision"),
        (CANDIDATE_URLS[2], "missing_decision"),
        (CANDIDATE_URLS[3], "missing_decision"),
    ]
    assert "corruption_or_fabrication" in match.attrition[0].detail


def test_parse_triage_failure_raises():
    bad = BatchResult(
        custom_id="inst-0042-stage3",
        success=False,
        response=None,
        error={"code": "x", "message": "y"},
    )
    with pytest.raises(RuntimeError, match="Stage 3"):
        parse_triage_result(bad)


def test_parse_triage_malformed_json_raises_descriptive_runtime_error():
    """Malformed assistant JSON must surface stage + custom_id in the error
    so consolidate.py / presweep/ logs identify which institution failed."""
    result = _make_result("inst-0042-stage3", "{not valid json at all")
    with pytest.raises(RuntimeError, match=r"Stage 3 parse failed for custom_id=inst-0042-stage3"):
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)


# ---------------------------------------------------------------------------
# Response-format payloads — check the JSON-schema strict envelope shape.
# ---------------------------------------------------------------------------


def test_response_format_is_strict_json_schema():
    for fmt in (OFFICIAL_SITE_FORMAT, TRIAGE_FORMAT):
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["strict"] is True
        assert fmt["json_schema"]["schema"].get("additionalProperties") is False
