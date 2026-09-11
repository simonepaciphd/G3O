"""URL normalization for triage matching.

Tests the normalize_url function and its integration with match_triage_decisions.
Normalization salvages decisions where the LLM echoed a cosmetically different
but resource-identical URL (trailing slash, percent-encoding case, query order,
default port) while still rejecting genuine rewrites or fabrications.
"""

from __future__ import annotations

from g3o.classify.url_triage import (
    URLDecision,
    URLTriageResult,
    match_triage_decisions,
    normalize_url,
)

# ---------------------------------------------------------------------------
# normalize_url unit tests
# ---------------------------------------------------------------------------


def test_normalize_trailing_slash() -> None:
    """Trailing slash is stripped (except root)."""
    assert normalize_url("https://example.gov/page/") == "https://example.gov/page"
    assert normalize_url("https://example.gov/page") == "https://example.gov/page"
    assert normalize_url("https://example.gov/") == "https://example.gov/"


def test_normalize_percent_encoding_case() -> None:
    """Percent-encoding hex digits are uppercased without decoding."""
    assert (
        normalize_url("https://example.gov/search?q=%e0%a6%ac")
        == "https://example.gov/search?q=%E0%A6%AC"
    )
    # %2F is preserved (not decoded to /) to maintain path segment semantics
    assert (
        normalize_url("https://example.gov/path/%2f%2F")
        == "https://example.gov/path/%2F%2F"
    )





def test_normalize_default_ports() -> None:
    """Default ports (:443 for https, :80 for http) are removed."""
    assert normalize_url("https://example.gov:443/page") == "https://example.gov/page"
    assert normalize_url("http://example.gov:80/page") == "http://example.gov/page"
    # Non-default ports are preserved
    assert normalize_url("https://example.gov:8080/page") == "https://example.gov:8080/page"
    assert normalize_url("http://example.gov:8443/page") == "http://example.gov:8443/page"


def test_normalize_scheme_and_host_case() -> None:
    """Scheme and host are lowercased."""
    assert normalize_url("HTTPS://EXAMPLE.GOV/page") == "https://example.gov/page"
    assert normalize_url("HTTP://Example.Gov/Page") == "http://example.gov/Page"


def test_normalize_query_parameter_order() -> None:
    """Query parameters are sorted alphabetically."""
    assert (
        normalize_url("https://example.gov/search?b=2&a=1&c=3")
        == "https://example.gov/search?a=1&b=2&c=3"
    )
    assert (
        normalize_url("https://example.gov/search?z=last&a=first")
        == "https://example.gov/search?a=first&z=last"
    )


def test_normalize_unicode_encoding() -> None:
    """Unicode characters are normalized to consistent percent-encoding."""
    # Québec with different encodings should normalize the same
    url1 = "https://example.gov/wiki/Sainte-Monique,Qu%C3%A9bec"
    url2 = "https://example.gov/wiki/Sainte-Monique,Qu%c3%a9bec"
    assert normalize_url(url1) == normalize_url(url2)


def test_normalize_preserves_path_segments() -> None:
    """Path segments are NOT changed — genuine rewrites are rejected."""
    # /az/news/ is different from /news/ — normalization should NOT make them equal
    url1 = "http://pirallahi-ih.gov.az/az/news/1324.html"
    url2 = "http://pirallahi-ih.gov.az/news/1324.html"
    assert normalize_url(url1) != normalize_url(url2)


def test_normalize_preserves_domain() -> None:
    """Domain changes are NOT normalized — fabrications are rejected."""
    url1 = "https://example.gov/page"
    url2 = "https://example.com/page"
    assert normalize_url(url1) != normalize_url(url2)


def test_normalize_drops_fragment() -> None:
    """Fragments are dropped (different resource)."""
    assert normalize_url("https://example.gov/page#section") == "https://example.gov/page"
    assert normalize_url("https://example.gov/page") == "https://example.gov/page"


def test_normalize_empty_path() -> None:
    """URLs with no path normalize correctly."""
    assert normalize_url("https://example.gov") == "https://example.gov"
    assert normalize_url("https://example.gov/") == "https://example.gov/"


def test_normalize_preserves_encoded_slashes() -> None:
    """%2F (encoded slash) is preserved, not decoded to /."""
    # %2F in a path segment is semantically different from /
    url = "https://example.gov/api%2Fv1%2Fendpoint"
    normalized = normalize_url(url)
    assert "%2F" in normalized
    assert normalized == "https://example.gov/api%2Fv1%2Fendpoint"





# ---------------------------------------------------------------------------
# Integration tests: match_triage_decisions with normalization
# ---------------------------------------------------------------------------


def test_match_salvages_trailing_slash_difference() -> None:
    """A decision with a trailing slash difference is salvaged."""
    candidates = ["https://example.gov/page"]
    triage = URLTriageResult(
        decisions=[
            URLDecision(url="https://example.gov/page/", decision="keep", rationale="relevant")
        ]
    )
    result = match_triage_decisions(candidates, triage)
    assert len(result.decisions) == 1
    assert result.decisions[0].url == "https://example.gov/page/"
    assert result.decisions[0].decision == "keep"
    assert result.kept_urls == ["https://example.gov/page"]
    assert len(result.attrition) == 0


def test_match_salvages_percent_encoding_case_difference() -> None:
    """A decision with percent-encoding case difference is salvaged."""
    candidates = ["https://example.gov/search?q=%E0%A6%AC"]
    triage = URLTriageResult(
        decisions=[
            URLDecision(
                url="https://example.gov/search?q=%e0%a6%ac",
                decision="keep",
                rationale="relevant",
            )
        ]
    )
    result = match_triage_decisions(candidates, triage)
    assert len(result.decisions) == 1
    assert result.kept_urls == ["https://example.gov/search?q=%E0%A6%AC"]
    assert len(result.attrition) == 0


def test_match_salvages_query_parameter_order_difference() -> None:
    """A decision with query parameter order difference is salvaged."""
    candidates = ["https://example.gov/search?a=1&b=2"]
    triage = URLTriageResult(
        decisions=[
            URLDecision(
                url="https://example.gov/search?b=2&a=1", decision="keep", rationale="relevant"
            )
        ]
    )
    result = match_triage_decisions(candidates, triage)
    assert len(result.decisions) == 1
    assert result.kept_urls == ["https://example.gov/search?a=1&b=2"]
    assert len(result.attrition) == 0


def test_match_salvages_default_port_difference() -> None:
    """A decision with default port difference is salvaged."""
    candidates = ["https://example.gov/page"]
    triage = URLTriageResult(
        decisions=[
            URLDecision(
                url="https://example.gov:443/page", decision="keep", rationale="relevant"
            )
        ]
    )
    result = match_triage_decisions(candidates, triage)
    assert len(result.decisions) == 1
    assert result.kept_urls == ["https://example.gov/page"]
    assert len(result.attrition) == 0


def test_match_rejects_path_segment_rewrite() -> None:
    """A decision with path segment rewrite is rejected (not salvaged)."""
    candidates = ["http://pirallahi-ih.gov.az/az/news/1324.html"]
    triage = URLTriageResult(
        decisions=[
            URLDecision(
                url="http://pirallahi-ih.gov.az/news/1324.html",
                decision="keep",
                rationale="relevant",
            )
        ]
    )
    result = match_triage_decisions(candidates, triage)
    assert len(result.decisions) == 0
    assert result.kept_urls == []
    # Should have 2 attrition records: 1 missing_decision + 1 url_mismatch
    assert len(result.attrition) == 2
    reasons = {a.reason for a in result.attrition}
    assert "missing_decision" in reasons
    assert "url_mismatch" in reasons


def test_match_rejects_domain_change() -> None:
    """A decision with domain change is rejected (fabrication)."""
    candidates = ["https://example.gov/page"]
    triage = URLTriageResult(
        decisions=[
            URLDecision(url="https://example.com/page", decision="keep", rationale="relevant")
        ]
    )
    result = match_triage_decisions(candidates, triage)
    assert len(result.decisions) == 0
    assert result.kept_urls == []
    assert len(result.attrition) == 2
    reasons = {a.reason for a in result.attrition}
    assert "missing_decision" in reasons
    assert "url_mismatch" in reasons


def test_match_multiple_normalization_differences() -> None:
    """Multiple candidates with various normalization differences are salvaged."""
    candidates = [
        "https://example.gov/page1",
        "https://example.gov/page2",
        "https://example.gov/search?a=1&b=2",
    ]
    triage = URLTriageResult(
        decisions=[
            URLDecision(url="https://example.gov/page1/", decision="keep", rationale="r1"),
            URLDecision(
                url="https://example.gov/page2/", decision="drop", rationale="irrelevant"
            ),
            URLDecision(
                url="https://example.gov/search?b=2&a=1", decision="keep", rationale="r3"
            ),
        ]
    )
    result = match_triage_decisions(candidates, triage)
    assert len(result.decisions) == 3
    assert result.kept_urls == [
        "https://example.gov/page1",
        "https://example.gov/search?a=1&b=2",
    ]
    assert len(result.attrition) == 0


def test_match_preserves_exact_match_behavior() -> None:
    """Exact matches still work (regression guard)."""
    candidates = ["https://example.gov/page1", "https://example.gov/page2"]
    triage = URLTriageResult(
        decisions=[
            URLDecision(url="https://example.gov/page1", decision="keep", rationale="r1"),
            URLDecision(url="https://example.gov/page2", decision="drop", rationale="r2"),
        ]
    )
    result = match_triage_decisions(candidates, triage)
    assert len(result.decisions) == 2
    assert result.kept_urls == ["https://example.gov/page1"]
    assert len(result.attrition) == 0


def test_match_candidate_collision() -> None:
    """Two candidates normalizing to the same URL: both match the decision."""
    # Both normalize to https://example.gov/page
    candidates = ["https://example.gov/page/", "https://example.gov/page"]
    triage = URLTriageResult(
        decisions=[
            URLDecision(url="https://example.gov/page", decision="keep", rationale="r1")
        ]
    )
    result = match_triage_decisions(candidates, triage)
    # Both candidates match the same decision (both point to same resource)
    assert len(result.decisions) == 2
    assert result.kept_urls == ["https://example.gov/page/", "https://example.gov/page"]
    # No attrition since both candidates were matched
    assert len(result.attrition) == 0


