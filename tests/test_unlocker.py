"""Bright Data Web Unlocker integration (Phase 3, 2026-09-17).

Tests the unlocker client, its dispatch wiring in ``fetcher.scrape_url``, the
telemetry hooks, the credential hygiene (Bearer token never in any artifact),
and the resume guard on the two new ``PresweepConfig`` flags.

The unlocker is a per-URL escalation for refused/blocked fetches, NOT a fourth
always-on egress point. It fires only when the caller opts in via
``PresweepConfig.scrape_unlocker_on_block`` or ``scrape_unlocker_on_empty``,
and only on URLs the default path refused (403/406/401/451) or that stripped
to near-empty text.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from g3o.common import config
from g3o.scrape import fetcher, unlocker

# ---------------------------------------------------------------------------
# The unlocker client itself
# ---------------------------------------------------------------------------


TOKEN = "00000000-1111-4222-8333-444444444444"


@pytest.fixture
def unlocker_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "UNLOCKER_API_TOKEN", TOKEN)
    monkeypatch.setattr(config, "UNLOCKER_ZONE", "web_unlocker1")
    monkeypatch.setattr(
        config, "UNLOCKER_API_URL", "https://api.brightdata.com/request"
    )


@pytest.fixture
def unlocker_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "UNLOCKER_API_TOKEN", None)


def test_enabled_returns_true_when_token_is_set(
    unlocker_configured: None,
) -> None:
    assert unlocker.enabled() is True


def test_enabled_returns_false_when_token_is_absent(
    unlocker_disabled: None,
) -> None:
    assert unlocker.enabled() is False


def test_is_refusal_status_covers_the_four_statuses() -> None:
    # The unlocker should fire on 403/406/401/451 — the statuses the fetcher
    # already refuses to retry, and the ones the unlocker is provisioned to
    # defeat. Every other status (200, 404, 500, None) is not a refusal.
    for status in (403, 406, 401, 451):
        assert unlocker.is_refusal_status(status) is True
    for status in (200, 404, 500, 503, None):
        assert unlocker.is_refusal_status(status) is False


def test_fetch_raises_when_token_is_absent(unlocker_disabled: None) -> None:
    with pytest.raises(RuntimeError, match="G3O_UNLOCKER_API_TOKEN"):
        unlocker.fetch("https://example.com")


def _mock_response(
    *, status_code: int = 200, content: bytes = b"body",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.content = content
    resp.headers = headers or {}
    return resp


def test_fetch_success_gate_all_three_conditions(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A success requires: no x-brd-error, inner status 200, non-empty body.
    mock_resp = _mock_response(
        status_code=200, content=b"<html>content</html>",
        headers={"x-brd-status-code": "200"},
    )
    monkeypatch.setattr(unlocker.requests, "post", lambda *a, **kw: mock_resp)
    result = unlocker.fetch("https://example.com")
    assert result.success is True
    assert result.content == b"<html>content</html>"
    assert result.inner_status == 200
    assert result.error is None


def test_fetch_failure_on_x_brd_error_header(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The measured trap: a policy block arrives as HTTP 200 from the unlocker
    # API with 0 bytes and x-brd-error: policy_20000 in the headers. The
    # transport status code alone is not the success gate.
    mock_resp = _mock_response(
        status_code=200, content=b"",
        headers={"x-brd-error": "policy_20000", "x-brd-error-code": "policy"},
    )
    monkeypatch.setattr(unlocker.requests, "post", lambda *a, **kw: mock_resp)
    result = unlocker.fetch("https://example.com")
    assert result.success is False
    assert result.error == "policy_20000"
    assert result.error_code == "policy"


def test_fetch_failure_on_non_200_inner_status(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A dead target arrives as HTTP 200 from the unlocker API with 0 bytes and
    # x-brd-status-code: 404. The inner status is the truth, not the transport.
    mock_resp = _mock_response(
        status_code=200, content=b"",
        headers={"x-brd-status-code": "404"},
    )
    monkeypatch.setattr(unlocker.requests, "post", lambda *a, **kw: mock_resp)
    result = unlocker.fetch("https://example.com")
    assert result.success is False
    assert result.inner_status == 404


def test_fetch_failure_on_empty_body(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 200 with no error header but 0 bytes is still a failure.
    mock_resp = _mock_response(
        status_code=200, content=b"",
        headers={"x-brd-status-code": "200"},
    )
    monkeypatch.setattr(unlocker.requests, "post", lambda *a, **kw: mock_resp)
    result = unlocker.fetch("https://example.com")
    assert result.success is False


def test_redact_scrubs_the_token(unlocker_configured: None) -> None:
    # The Bearer token is a secret and must never appear in any artifact.
    text = f"GET failed with token {TOKEN} rejected"
    redacted = unlocker.redact(text)
    assert TOKEN not in redacted
    assert "<unlocker-token redacted>" in redacted


def test_redact_is_passthrough_when_token_is_absent(
    unlocker_disabled: None,
) -> None:
    # No token set means nothing to redact; the text passes through unchanged.
    text = "nothing to redact here"
    assert unlocker.redact(text) == text


def test_redact_leaves_a_short_token_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Same floor as the proxy-password redactor: below 8 characters a "token"
    # is a substring of ordinary English and blanking it damages the log more
    # than it protects.
    monkeypatch.setattr(config, "UNLOCKER_API_TOKEN", "short")
    assert unlocker.redact("please pass the report") == "please pass the report"


# ---------------------------------------------------------------------------
# Dispatch wiring in fetcher.scrape_url
# ---------------------------------------------------------------------------


def _download_raising_403() -> Any:
    """A ``_download`` that raises an ``HTTPError`` with status 403."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = 403
    exc = requests.HTTPError(response=resp)
    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise exc
    return _raise


def test_unlocker_fires_on_403_when_enabled(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 403 refusal with the unlocker enabled and opted in: the unlocker
    # fires, succeeds, and returns a page with fetch_method="unlocker".
    monkeypatch.setattr(fetcher, "_download", _download_raising_403())
    mock_result = unlocker.UnlockerResult(
        success=True, content=b"<html><body><p>This is some recovered content that is long enough.</p></body></html>",
        inner_status=200, error=None, error_code=None, elapsed_ms=500,
    )
    monkeypatch.setattr(unlocker, "fetch", lambda url: mock_result)

    page = fetcher.scrape_url(
        "https://blocked.gov", force_refresh=True,
        prefer_unlocker_on_block=True,
    )
    assert "recovered" in page.text
    assert page.fetch_metadata.fetch_method == "unlocker"


def test_unlocker_does_not_fire_when_disabled(
    unlocker_disabled: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Token absent: the unlocker is inert, even when opted in. The fetcher
    # falls through to the hard-failure path and returns a no-text page.
    monkeypatch.setattr(fetcher, "_download", _download_raising_403())
    events: list[dict[str, Any]] = []
    page = fetcher.scrape_url(
        "https://blocked.gov", force_refresh=True,
        prefer_unlocker_on_block=True,
        on_unlocker_attempt=lambda **kw: events.append(kw),
    )
    assert page.text == ""
    assert events == []  # no unlocker attempt recorded


def test_unlocker_does_not_fire_when_opted_out(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Token present but opted out: the unlocker is inert. The fetcher falls
    # through to the hard-failure path.
    monkeypatch.setattr(fetcher, "_download", _download_raising_403())
    events: list[dict[str, Any]] = []
    page = fetcher.scrape_url(
        "https://blocked.gov", force_refresh=True,
        prefer_unlocker_on_block=False,  # default
        on_unlocker_attempt=lambda **kw: events.append(kw),
    )
    assert page.text == ""
    assert events == []


def test_unlocker_does_not_fire_on_non_refusal_status(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A connect timeout has no status and is not a refusal — the unlocker
    # cannot defeat a dead host. The fetcher falls through to the
    # hard-failure path.
    def _raise_timeout(*args: Any, **kwargs: Any) -> Any:
        raise requests.ConnectTimeout("connection timed out")
    monkeypatch.setattr(fetcher, "_download", _raise_timeout)
    events: list[dict[str, Any]] = []
    page = fetcher.scrape_url(
        "https://dead.gov", force_refresh=True,
        prefer_unlocker_on_block=True,
        on_unlocker_attempt=lambda **kw: events.append(kw),
    )
    assert page.text == ""
    assert events == []


def test_unlocker_failure_falls_through_to_render(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Unlocker fails, render fallback is enabled: the render fires after the
    # unlocker failure. Both attempts are recorded.
    monkeypatch.setattr(fetcher, "_download", _download_raising_403())
    mock_result = unlocker.UnlockerResult(
        success=False, content=b"", inner_status=403,
        error="policy_20000", error_code="policy", elapsed_ms=300,
    )
    monkeypatch.setattr(unlocker, "fetch", lambda url: mock_result)
    monkeypatch.setattr(
        fetcher, "render_url",
        lambda url, **kw: fetcher.RenderedPage(
            url=url, text="RENDERED", title="", content_type="html",
            fetch_metadata=fetcher.FetchMetadata(
                access_date="2026-09-17", http_status=None, final_url=None,
                fetch_method="render", elapsed_ms=1000, wait_for=None,
            ),
        ),
    )
    events: list[dict[str, Any]] = []
    page = fetcher.scrape_url(
        "https://blocked.gov", force_refresh=True,
        prefer_unlocker_on_block=True,
        prefer_render_on_download_failure=True,
        on_unlocker_attempt=lambda **kw: events.append(kw),
    )
    assert page.text == "RENDERED"
    assert len(events) == 1
    assert events[0]["outcome"] == "unlocker_failed"
    assert events[0]["trigger"] == "block"


def test_unlocker_on_empty_after_strip(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A page that returns 200 but strips to near-empty text: the unlocker
    # fires on the empty-after-strip trigger when opted in.
    def _download_empty(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
        return (b"<html></html>", "text/html", 200, "https://example.com", 100)
    monkeypatch.setattr(fetcher, "_download", _download_empty)
    mock_result = unlocker.UnlockerResult(
        success=True, content=b"<html><body><p>This is full content that is long enough to pass.</p></body></html>",
        inner_status=200, error=None, error_code=None, elapsed_ms=500,
    )
    monkeypatch.setattr(unlocker, "fetch", lambda url: mock_result)
    events: list[dict[str, Any]] = []
    page = fetcher.scrape_url(
        "https://empty.gov", force_refresh=True,
        prefer_render_on_empty=True,
        prefer_unlocker_on_empty=True,
        empty_page_min_chars=50,
        on_unlocker_attempt=lambda **kw: events.append(kw),
    )
    assert "full content" in page.text
    assert page.fetch_metadata.fetch_method == "unlocker"
    assert len(events) == 1
    assert events[0]["trigger"] == "empty_after_strip"


def test_unlocker_carries_raw_bytes_through_to_parse(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UTF-8 non-ASCII unlocker body survives to page.text intact.

    Pins the never-decode contract: the unlocker carries raw bytes, and the
    caller's parser (BeautifulSoup + UnicodeDammit) does the encoding
    detection. Cannot fail pre-fix through a mock (requests' decoder is not
    in the loop), so this pins the contract.
    """
    monkeypatch.setattr(fetcher, "_download", _download_raising_403())
    utf8_body = "<html><body><p>Überflüssige Ämter – Prüfung</p></body></html>".encode()
    mock_result = unlocker.UnlockerResult(
        success=True, content=utf8_body,
        inner_status=200, error=None, error_code=None, elapsed_ms=500,
    )
    monkeypatch.setattr(unlocker, "fetch", lambda url: mock_result)
    page = fetcher.scrape_url(
        "https://blocked.gov", force_refresh=True,
        prefer_unlocker_on_block=True,
    )
    assert "Überflüssige" in page.text
    assert "Ämter" in page.text
    assert "Prüfung" in page.text


def test_unlocker_pdf_routing_uses_suffix_not_substring(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A URL containing "pdf" but not ending in ".pdf" routes to HTML.

    Pre-fix: ``"pdf" in url.lower()`` misroutes ``…/pdf-forms.html`` into
    ``pdf_mod.extract_text``. Post-fix: ``url.lower().endswith(".pdf")``
    routes correctly.
    """
    monkeypatch.setattr(fetcher, "_download", _download_raising_403())
    html_body = b"<html><body><p>PDF forms are here</p></body></html>"
    mock_result = unlocker.UnlockerResult(
        success=True, content=html_body,
        inner_status=200, error=None, error_code=None, elapsed_ms=500,
    )
    monkeypatch.setattr(unlocker, "fetch", lambda url: mock_result)
    page = fetcher.scrape_url(
        "https://x.gov/pdf-forms", force_refresh=True,
        prefer_unlocker_on_block=True,
    )
    assert page.fetch_metadata.fetch_method == "unlocker"


def test_unlocker_pdf_routing_uses_suffix_for_actual_pdf(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A URL ending in ".pdf" routes to PDF extraction.

    The unlocker returns raw bytes; the fetcher must detect PDF by URL suffix
    and route to ``pdf_mod.extract_text``.
    """
    monkeypatch.setattr(fetcher, "_download", _download_raising_403())
    # Minimal PDF body (pdfplumber will fail to parse, but the routing is what
    # matters — the fetch_method will be "unlocker_pdf").
    pdf_body = b"%PDF-1.4\n%fake pdf content"
    mock_result = unlocker.UnlockerResult(
        success=True, content=pdf_body,
        inner_status=200, error=None, error_code=None, elapsed_ms=500,
    )
    monkeypatch.setattr(unlocker, "fetch", lambda url: mock_result)
    page = fetcher.scrape_url(
        "https://example.gov/document.pdf", force_refresh=True,
        prefer_unlocker_on_block=True,
    )
    assert page.fetch_metadata.fetch_method == "unlocker_pdf"



# ---------------------------------------------------------------------------
# Credential hygiene: the token never appears in any artifact
# ---------------------------------------------------------------------------


def test_token_never_in_unlocker_result_error(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A transport failure carries the token in the exception message. The
    # redactor must scrub it before it reaches any artifact.
    monkeypatch.setattr(fetcher, "_download", _download_raising_403())
    def _raise_with_token(*args: Any, **kwargs: Any) -> Any:
        raise requests.RequestException(f"auth failed: {TOKEN}")
    monkeypatch.setattr(unlocker.requests, "post", _raise_with_token)
    events: list[dict[str, Any]] = []
    page = fetcher.scrape_url(
        "https://blocked.gov", force_refresh=True,
        prefer_unlocker_on_block=True,
        on_unlocker_attempt=lambda **kw: events.append(kw),
    )
    assert page.text == ""
    assert len(events) == 1
    assert TOKEN not in json.dumps(events)


# ---------------------------------------------------------------------------
# egress.describe() records the unlocker state
# ---------------------------------------------------------------------------


def test_describe_records_unlocker_configured(
    unlocker_configured: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from g3o.scrape import egress
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "")
    described = egress.describe()
    assert described["unlocker_configured"] is True


def test_describe_records_unlocker_disabled(
    unlocker_disabled: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from g3o.scrape import egress
    monkeypatch.setattr(config, "SCRAPE_PROXY_URL", "")
    described = egress.describe()
    assert described["unlocker_configured"] is False


# ---------------------------------------------------------------------------
# PresweepConfig flags are guarded on resume
# ---------------------------------------------------------------------------


def test_presweep_config_has_unlocker_flags() -> None:
    from dataclasses import fields

    from g3o.run.presweep import PresweepConfig
    field_names = {f.name for f in fields(PresweepConfig)}
    assert "scrape_unlocker_on_block" in field_names
    assert "scrape_unlocker_on_empty" in field_names


def test_presweep_config_unlocker_flags_default_off() -> None:
    from pathlib import Path

    from g3o.run.presweep import PresweepConfig
    cfg = PresweepConfig(
        run_id="test", runs_dir=Path("/tmp"), master_csv=Path("/tmp/m.csv"),
    )
    assert cfg.scrape_unlocker_on_block is False
    assert cfg.scrape_unlocker_on_empty is False


def test_resume_guard_includes_unlocker_flags() -> None:
    from g3o.run.presweep.planning import _GUARDED_CONFIG_KEYS
    assert "scrape_unlocker_on_block" in _GUARDED_CONFIG_KEYS
    assert "scrape_unlocker_on_empty" in _GUARDED_CONFIG_KEYS


def test_resume_guard_tolerates_absent_unlocker_flags() -> None:
    from g3o.run.presweep.planning import _ABSENT_TOLERATED_CONFIG_KEYS
    # Every manifest written before 2026-09-17 lacks these flags; tolerating
    # their absence lets such runs resume.
    assert "scrape_unlocker_on_block" in _ABSENT_TOLERATED_CONFIG_KEYS
    assert "scrape_unlocker_on_empty" in _ABSENT_TOLERATED_CONFIG_KEYS
