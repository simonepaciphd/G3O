"""F19 — adversarial-LLM-output suite (Session F.7, 2026-06-12).

Feeds each of the four LLM parse boundaries deliberately hostile model
output — truncated JSON, prose refusals, wrong JSON envelopes, fabricated
URLs, out-of-enum values, implausible access dates, missing required fields,
and oversized free text — and asserts each is **caught** (an exception
reaches the caller), not silently accepted into a downstream artifact.

"Caught" is sufficient for pipeline safety because every presweep call site
wraps its parse in ``try/except Exception`` and records a ``parse_failed``
attrition entry (``g3o/run/presweep.py`` Stages 2/3/5;
``g3o/validate/consolidate.py`` Stage 6) — any raise here means flagged,
skipped, and auditable rather than persisted.

Boundaries covered:

- Stage 2 ``parse_official_site_result`` — the fabricated-URL case is a
  **documented gap** (review F13): no membership check exists pending
  Decision D6, so it is marked ``xfail(strict=True)``. When D6 is decided
  and F13 lands, the strict marker forces this test to be rewritten.
- Stage 3 ``parse_triage_result`` — the ``expected_urls`` round-trip is the
  enforcement point; adversarial cases exercise URL-rewriting drift the
  happy-path tests don't.
- Stage 5 ``parse_extract_result`` — the Q1=a access-date contract is the
  enforcement point for date drift. Note the asymmetry: Stages 2/3 wrap
  malformed JSON in ``RuntimeError`` with stage + custom_id; Stages 5/6
  raise bare ``json.JSONDecodeError`` (still caught at the call sites).
- Stage 6 ``parse_consolidate_result`` — the contract's FK/sequence/
  back-link validators are the enforcement point.

Complements (does not duplicate) the happy-path and single-fault coverage
in ``test_classify.py``, ``test_extract.py``, ``test_validate.py``,
``test_contract.py``, and ``test_consolidated_contract.py``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from g3o.classify.official_site import parse_official_site_result
from g3o.classify.url_triage import parse_triage_result
from g3o.common.batch_client import BatchResult
from g3o.extract.parser import parse_extract_result
from g3o.validate.consolidate import parse_consolidate_result

# ---------------------------------------------------------------------------
# Builders (mirror the fixture shapes in test_extract.py /
# test_consolidated_contract.py; kept local so each test module stays
# self-contained, per suite convention)
# ---------------------------------------------------------------------------


CANDIDATE_URLS = [
    "https://www.mpa.gov.tl/",
    "https://en.wikipedia.org/wiki/Ministry_of_Public_Affairs_(Testland)",
    "https://www.mpa.gov.tl/news/2025/ai-pilot",
    "https://news.example.com/testland-ministry-ai",
]

SCRAPE_ACCESS_DATE = "2026-05-09"


def _make_result(custom_id: str, content: dict[str, Any] | list[Any] | str) -> BatchResult:
    """A successful BatchResult whose assistant content is `content`."""
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


def _official_site_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "url": CANDIDATE_URLS[0],
        "confidence": "high",
        "rationale": "Official domain landing page naming the ministry.",
    }
    base.update(overrides)
    return base


def _triage_payload(urls: list[str] | None = None) -> dict[str, Any]:
    return {
        "decisions": [
            {"url": u, "decision": "keep", "rationale": "r"}
            for u in (CANDIDATE_URLS if urls is None else urls)
        ]
    }


def _extract_row(**overrides: Any) -> dict[str, Any]:
    """A minimal valid 'no GenAI' contract row — every Group D field is _NA_."""
    base: dict[str, Any] = {
        "row_id": 1,
        "batch_id": "b1",
        "institution_id": "INST-0042",
        "institution_name": "Ministry of Public Affairs",
        "country": "Testland",
        "branch_of_government": "executive",
        "level_of_government": "national",
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
        "source_url": "https://www.mpa.gov.tl/",
        "source_title": "Home",
        "source_publication_date": "2026-01-15",
        "source_access_date": SCRAPE_ACCESS_DATE,
        "source_type": "official_gov",
        "source_language": "en",
        "source_credibility": "high",
        "genai_evidence": "confirms_absence",
        "source_snippet": "Page contains no mention of generative AI.",
        "confidence": "high",
        "uncertainty_flags": "none",
    }
    base.update(overrides)
    return base


def _extract_payload(**row_overrides: Any) -> dict[str, Any]:
    return {
        "batch_metadata": {
            "batch_id": "b1",
            "chat_type": "web",
            "model_label": "gpt-5-nano",
            "response_timestamp": "2026-05-09T10:00:00Z",
            "n_institutions_in_batch": 1,
            "n_institutions_with_genai": 0,
            "n_data_rows": 1,
            "search_languages": "en",
            "search_strategy_summary": "URLs supplied by the pipeline.",
            "notes": "none",
        },
        "data": [_extract_row(**row_overrides)],
    }


def _consolidate_activity(activity_id: str = "A1", **overrides: Any) -> dict[str, Any]:
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


def _consolidate_source(
    source_id: str = "S1", activity_id: str = "A1", **overrides: Any
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


def _consolidate_payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "consolidation_metadata": {
            "institution_id": "INST-0042",
            "n_input_pages": 3,
            "n_input_rows": 5,
            "response_timestamp": "2026-05-09T12:00:00Z",
            "model_label": "gpt-5-nano",
            "notes": "none",
        },
        "institution": {
            "institution_id": "INST-0042",
            "institution_name": "Ministry of Public Affairs",
            "country": "Testland",
            "branch_of_government": "executive",
            "level_of_government": "national",
            "has_genai_activity": "yes",
            "institution_summary": "Internal Copilot pilot underway.",
            "institution_search_languages": "en",
        },
        "activities": [_consolidate_activity()],
        "sources": [_consolidate_source()],
    }
    base.update(overrides)
    return base


def _truncate(payload: dict[str, Any]) -> str:
    """Serialize and cut mid-document — the shape a token-limit cutoff produces."""
    s = json.dumps(payload)
    return s[: int(len(s) * 0.6)]


PROSE_REFUSAL = (
    "I'm sorry, but I can't determine the official website from the "
    "information provided. Could you share more candidate URLs?"
)


# ---------------------------------------------------------------------------
# Stage 2 — parse_official_site_result
# ---------------------------------------------------------------------------


def test_stage2_truncated_json_caught():
    result = _make_result("INST-0042", _truncate(_official_site_payload()))
    with pytest.raises(RuntimeError, match=r"Stage 2 parse failed for custom_id=INST-0042"):
        parse_official_site_result(result)


def test_stage2_prose_refusal_caught():
    result = _make_result("INST-0042", PROSE_REFUSAL)
    with pytest.raises(RuntimeError, match="Stage 2 parse failed"):
        parse_official_site_result(result)


@pytest.mark.parametrize("envelope", ["null", "[]", '"https://www.mpa.gov.tl/"'])
def test_stage2_wrong_json_envelope_caught(envelope: str):
    """Valid JSON that is not the expected object (null / array / bare string)."""
    result = _make_result("INST-0042", envelope)
    with pytest.raises(ValidationError):
        parse_official_site_result(result)


def test_stage2_missing_required_field_caught():
    payload = _official_site_payload()
    del payload["confidence"]
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError):
        parse_official_site_result(result)


def test_stage2_plausible_out_of_enum_confidence_caught():
    """'very_high' is the kind of near-miss an LLM invents, not gibberish."""
    result = _make_result(
        "INST-0042", _official_site_payload(confidence="very_high")
    )
    with pytest.raises(ValidationError):
        parse_official_site_result(result)


@pytest.mark.xfail(
    reason=(
        "Documented gap — review F13, pending Decision D6: Stage 2 has no "
        "check that the returned url is among the candidate URLs, so a "
        "fabricated homepage is accepted and seeds every Stage 1b site: "
        "query for the institution. parse_official_site_result currently "
        "has no candidate-set parameter. Rewrite this test when D6 is "
        "decided and F13 lands (strict=True will force it)."
    ),
    strict=True,
)
def test_stage2_fabricated_url_outside_candidate_set_rejected():
    fabricated = "https://www.rnpa-gov-t1.com/"  # plausible look-alike domain
    assert fabricated not in CANDIDATE_URLS
    result = _make_result(
        "INST-0042",
        _official_site_payload(url=fabricated, confidence="high"),
    )
    with pytest.raises((RuntimeError, ValidationError)):
        parse_official_site_result(result)


# ---------------------------------------------------------------------------
# Stage 3 — parse_triage_result
# ---------------------------------------------------------------------------


def test_stage3_truncated_json_caught():
    result = _make_result("INST-0042", _truncate(_triage_payload()))
    with pytest.raises(RuntimeError, match=r"Stage 3 parse failed for custom_id=INST-0042"):
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)


def test_stage3_prose_refusal_caught():
    result = _make_result("INST-0042", PROSE_REFUSAL)
    with pytest.raises(RuntimeError, match="Stage 3 parse failed"):
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)


def test_stage3_rewritten_url_variant_caught():
    """LLMs silently normalize URLs (here: added trailing slash). The
    round-trip check must flag the variant as both missing and unexpected."""
    urls = list(CANDIDATE_URLS)
    urls[2] = urls[2] + "/"
    result = _make_result("INST-0042", _triage_payload(urls))
    with pytest.raises(RuntimeError) as exc_info:
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)
    assert "missing decisions" in str(exc_info.value)
    assert "unexpected URLs" in str(exc_info.value)


def test_stage3_fabricated_extra_url_with_full_coverage_caught():
    """All expected URLs decided AND one invented extra — distinct from the
    single-decision invented-URL case in test_classify.py."""
    urls = [*CANDIDATE_URLS, "https://invented.example.gov/ai-strategy"]
    result = _make_result("INST-0042", _triage_payload(urls))
    with pytest.raises(RuntimeError, match="unexpected URLs"):
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)


def test_stage3_empty_decisions_with_expected_urls_caught():
    """{"decisions": []} is structurally valid but must fail the round-trip."""
    result = _make_result("INST-0042", {"decisions": []})
    with pytest.raises(RuntimeError, match="missing decisions"):
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)


def test_stage3_plausible_out_of_enum_decision_caught():
    payload = _triage_payload()
    payload["decisions"][0]["decision"] = "maybe"
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError):
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)


def test_stage3_oversized_rationale_caught():
    payload = _triage_payload()
    payload["decisions"][0]["rationale"] = "x" * 161
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError):
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)


def test_stage3_decision_entry_missing_field_caught():
    payload = _triage_payload()
    del payload["decisions"][0]["decision"]
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError):
        parse_triage_result(result, expected_urls=CANDIDATE_URLS)


# ---------------------------------------------------------------------------
# Stage 5 — parse_extract_result
# ---------------------------------------------------------------------------


def test_stage5_truncated_json_caught():
    """Stage 5 does not wrap json.loads (unlike Stages 2/3) — the bare
    JSONDecodeError is still an exception, so the presweep call site records
    parse_failed attrition rather than persisting anything."""
    result = _make_result("INST-0042::abc123", _truncate(_extract_payload()))
    with pytest.raises(json.JSONDecodeError):
        parse_extract_result(result, scrape_access_date=SCRAPE_ACCESS_DATE)


def test_stage5_prose_refusal_caught():
    result = _make_result("INST-0042::abc123", PROSE_REFUSAL)
    with pytest.raises(json.JSONDecodeError):
        parse_extract_result(result, scrape_access_date=SCRAPE_ACCESS_DATE)


def test_stage5_wrong_json_envelope_caught():
    """A bare rows array without the batch_metadata envelope."""
    result = _make_result("INST-0042::abc123", [_extract_row()])
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date=SCRAPE_ACCESS_DATE)


def test_stage5_missing_batch_metadata_caught():
    payload = _extract_payload()
    del payload["batch_metadata"]
    result = _make_result("INST-0042::abc123", payload)
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date=SCRAPE_ACCESS_DATE)


def test_stage5_row_missing_required_field_caught():
    payload = _extract_payload()
    del payload["data"][0]["source_url"]
    result = _make_result("INST-0042::abc123", payload)
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date=SCRAPE_ACCESS_DATE)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_type", "blog"),
        ("source_credibility", "very_high"),
        ("genai_evidence", "confirms"),
        ("confidence", "certain"),
        ("has_genai_activity", "n"),
    ],
)
def test_stage5_plausible_out_of_enum_value_caught(field: str, value: str):
    """Near-miss enum drift on Group C/E/F fields of a no-GenAI row."""
    result = _make_result("INST-0042::abc123", _extract_payload(**{field: value}))
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date=SCRAPE_ACCESS_DATE)


@pytest.mark.parametrize(
    "field",
    ["institution_summary", "source_snippet", "source_title"],
)
def test_stage5_oversized_free_text_caught(field: str):
    caps = {"institution_summary": 300, "source_snippet": 300, "source_title": 200}
    result = _make_result(
        "INST-0042::abc123", _extract_payload(**{field: "x" * (caps[field] + 1)})
    )
    with pytest.raises(ValidationError):
        parse_extract_result(result, scrape_access_date=SCRAPE_ACCESS_DATE)


@pytest.mark.parametrize(
    "bad_date",
    [
        "2026-13-45",  # regex-valid but not a calendar date
        "2031-01-01",  # future date
        "2025-05-09",  # plausible off-by-a-year drift
    ],
)
def test_stage5_implausible_access_date_caught_by_q1_contract(bad_date: str):
    """All three pass the ISO_DATE_PATTERN regex; the Q1=a verbatim-match
    against the scrape-supplied date is what catches them."""
    result = _make_result(
        "INST-0042::abc123", _extract_payload(source_access_date=bad_date)
    )
    with pytest.raises(ValueError, match="source_access_date"):
        parse_extract_result(result, scrape_access_date=SCRAPE_ACCESS_DATE)


# ---------------------------------------------------------------------------
# Stage 6 — parse_consolidate_result
# ---------------------------------------------------------------------------


def test_stage6_truncated_json_caught():
    """Same bare-JSONDecodeError asymmetry as Stage 5; consolidate's
    _persist catches Exception and counts the institution as failed."""
    result = _make_result("INST-0042", _truncate(_consolidate_payload()))
    with pytest.raises(json.JSONDecodeError):
        parse_consolidate_result(result)


def test_stage6_prose_refusal_caught():
    result = _make_result("INST-0042", PROSE_REFUSAL)
    with pytest.raises(json.JSONDecodeError):
        parse_consolidate_result(result)


def test_stage6_wrong_json_envelope_caught():
    """A bare activities array without the response envelope."""
    result = _make_result("INST-0042", [_consolidate_activity()])
    with pytest.raises(ValidationError):
        parse_consolidate_result(result)


def test_stage6_missing_consolidation_metadata_caught():
    payload = _consolidate_payload()
    del payload["consolidation_metadata"]
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError):
        parse_consolidate_result(result)


def test_stage6_plausible_out_of_enum_adoption_stage_caught():
    payload = _consolidate_payload(
        activities=[_consolidate_activity(adoption_stage="deployed")]
    )
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError):
        parse_consolidate_result(result)


def test_stage6_duplicate_activity_ids_caught():
    """Two activities both labelled A1 — the gapless-sequence validator
    rejects the duplicate (expected A1, A2)."""
    payload = _consolidate_payload(
        activities=[
            _consolidate_activity("A1"),
            _consolidate_activity("A1", activity_name="Second pilot"),
        ],
        sources=[
            _consolidate_source("S1", "A1"),
            _consolidate_source("S2", "A1"),
        ],
    )
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError, match="activity_id sequence"):
        parse_consolidate_result(result)


def test_stage6_fabricated_fk_target_caught():
    """A source back-linking to an activity that does not exist."""
    payload = _consolidate_payload(
        sources=[
            _consolidate_source("S1", "A1"),
            _consolidate_source("S2", "A7"),
        ]
    )
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError, match="does not match any"):
        parse_consolidate_result(result)


def test_stage6_oversized_free_text_caught():
    payload = _consolidate_payload(
        sources=[_consolidate_source(source_snippet="x" * 301)]
    )
    result = _make_result("INST-0042", payload)
    with pytest.raises(ValidationError):
        parse_consolidate_result(result)
