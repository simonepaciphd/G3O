"""Tests for ``g3o.scrape.render`` and the fetcher's render dispatch.

playwright is monkeypatched out via ``_import_sync_playwright`` so these
tests run without the browser binary or any network.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from g3o.scrape import fetcher, render
from g3o.scrape.render import (
    FetchMetadata,
    RenderedPage,
    render_url,
    utc_today_iso,
)

# ---------------------------------------------------------------------------
# Stub playwright graph
# ---------------------------------------------------------------------------


class _StubResponse:
    def __init__(self, status: int) -> None:
        self.status = status


class _StubPage:
    def __init__(
        self,
        *,
        status: int = 200,
        text: str = "rendered body text",
        title: str = "Rendered Page",
        final_url: str = "https://example.com/",
    ) -> None:
        self._status = status
        self._text = text
        self._title = title
        self.url = final_url
        self.goto_calls: list[dict[str, Any]] = []
        self.wait_for_selector_calls: list[str] = []
        self.wait_for_load_state_calls: list[str] = []

    def goto(self, url: str, *, timeout: int, wait_until: str) -> _StubResponse:
        self.goto_calls.append(
            {"url": url, "timeout": timeout, "wait_until": wait_until}
        )
        return _StubResponse(self._status)

    def wait_for_selector(self, selector: str, *, timeout: int) -> None:
        self.wait_for_selector_calls.append(selector)

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        self.wait_for_load_state_calls.append(state)

    def inner_text(self, _selector: str) -> str:
        return self._text

    def title(self) -> str:
        return self._title


class _StubContext:
    def __init__(self, page: _StubPage) -> None:
        self._page = page

    def new_page(self) -> _StubPage:
        return self._page


class _StubBrowser:
    def __init__(self, context: _StubContext) -> None:
        self._context = context
        self.closed = False

    def new_context(self) -> _StubContext:
        return self._context

    def close(self) -> None:
        self.closed = True


class _StubChromium:
    def __init__(self, browser: _StubBrowser) -> None:
        self._browser = browser
        self.launch_kwargs: list[dict[str, Any]] = []

    def launch(self, **kwargs: Any) -> _StubBrowser:
        self.launch_kwargs.append(kwargs)
        return self._browser


class _StubPlaywright:
    def __init__(self, chromium: _StubChromium) -> None:
        self.chromium = chromium


class _StubPlaywrightCM:
    def __init__(self, stub: _StubPlaywright) -> None:
        self._stub = stub

    def __enter__(self) -> _StubPlaywright:
        return self._stub

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def _build_stub(
    *,
    status: int = 200,
    text: str = "rendered body text",
    title: str = "Rendered Page",
    final_url: str = "https://example.com/",
) -> tuple[Any, _StubPage, _StubBrowser, _StubChromium]:
    page = _StubPage(status=status, text=text, title=title, final_url=final_url)
    context = _StubContext(page)
    browser = _StubBrowser(context)
    chromium = _StubChromium(browser)
    pw = _StubPlaywright(chromium)

    def factory() -> _StubPlaywrightCM:
        return _StubPlaywrightCM(pw)

    return factory, page, browser, chromium


def _patch_playwright(monkeypatch: pytest.MonkeyPatch, factory: Any) -> None:
    monkeypatch.setattr(render, "_import_sync_playwright", lambda: factory)


# ---------------------------------------------------------------------------
# utc_today_iso
# ---------------------------------------------------------------------------


def test_utc_today_iso_format():
    s = utc_today_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s)


# ---------------------------------------------------------------------------
# RenderedPage / FetchMetadata models
# ---------------------------------------------------------------------------


def test_rendered_page_round_trip():
    page = RenderedPage(
        url="https://x.gov/",
        text="hello",
        title="Hello",
        content_type="render",
        fetch_metadata=FetchMetadata(
            access_date="2026-05-09",
            http_status=200,
            final_url="https://x.gov/",
            fetch_method="render",
            elapsed_ms=42,
            wait_for=None,
        ),
    )
    rt = RenderedPage.model_validate_json(page.model_dump_json())
    assert rt == page


def test_rendered_page_rejects_extra_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RenderedPage.model_validate(
            {
                "url": "https://x.gov/",
                "text": "",
                "title": "",
                "content_type": "html",
                "fetch_metadata": {
                    "access_date": "2026-05-09",
                    "http_status": 200,
                    "final_url": None,
                    "fetch_method": "html",
                },
                "extra_invented": True,
            }
        )


def test_fetch_metadata_rejects_bad_method():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        FetchMetadata.model_validate(
            {
                "access_date": "2026-05-09",
                "http_status": 200,
                "final_url": None,
                "fetch_method": "ftp",  # not in the Literal
            }
        )


# ---------------------------------------------------------------------------
# render_url happy path
# ---------------------------------------------------------------------------


def test_render_url_happy_path(monkeypatch: pytest.MonkeyPatch):
    factory, page_stub, browser_stub, chromium_stub = _build_stub(
        status=200,
        text="visible body",
        title="Welcome",
        final_url="https://www.example.com/",
    )
    _patch_playwright(monkeypatch, factory)

    result = render_url("https://example.com/", timeout=5000)

    assert isinstance(result, RenderedPage)
    assert result.url == "https://example.com/"  # supplied URL preserved
    assert result.text == "visible body"
    assert result.title == "Welcome"
    assert result.content_type == "render"
    assert result.fetch_metadata.fetch_method == "render"
    assert result.fetch_metadata.http_status == 200
    assert result.fetch_metadata.final_url == "https://www.example.com/"
    assert result.fetch_metadata.access_date == utc_today_iso()
    assert result.fetch_metadata.wait_for is None
    assert browser_stub.closed is True
    assert chromium_stub.launch_kwargs == [{"headless": True}]
    assert page_stub.wait_for_load_state_calls == ["networkidle"]


def test_render_url_with_wait_for_selector(monkeypatch: pytest.MonkeyPatch):
    factory, page_stub, _, _ = _build_stub()
    _patch_playwright(monkeypatch, factory)

    result = render_url(
        "https://example.com/", timeout=5000, wait_for="div.content"
    )

    assert result.fetch_metadata.wait_for == "div.content"
    assert page_stub.wait_for_selector_calls == ["div.content"]
    # When wait_for is given, networkidle is NOT used.
    assert page_stub.wait_for_load_state_calls == []


def test_render_url_preserves_supplied_url_through_redirect(
    monkeypatch: pytest.MonkeyPatch,
):
    factory, _, _, _ = _build_stub(final_url="https://en.example.com/landing")
    _patch_playwright(monkeypatch, factory)

    result = render_url("https://example.com/")

    assert result.url == "https://example.com/"
    assert result.fetch_metadata.final_url == "https://en.example.com/landing"


def test_render_url_records_non_200_without_raising(
    monkeypatch: pytest.MonkeyPatch,
):
    factory, _, _, _ = _build_stub(status=403, text="", title="Forbidden")
    _patch_playwright(monkeypatch, factory)

    result = render_url("https://example.com/")
    assert result.fetch_metadata.http_status == 403
    assert result.text == ""


def test_render_url_networkidle_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch,
):
    """Long-poll connections sometimes never reach networkidle; that must not raise."""
    factory, page_stub, _, _ = _build_stub()

    def _raise(*_: Any, **__: Any) -> None:
        raise TimeoutError("networkidle never reached")

    page_stub.wait_for_load_state = _raise  # type: ignore[method-assign]
    _patch_playwright(monkeypatch, factory)

    result = render_url("https://example.com/")
    assert result.text == "rendered body text"


# ---------------------------------------------------------------------------
# fetcher dispatch — force_render and empty-html fallback
# ---------------------------------------------------------------------------


def test_scrape_url_force_render_dispatches_to_render(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
):
    """force_render bypasses html/pdf paths entirely."""
    monkeypatch.setattr(fetcher.config, "CACHE_DIR", str(tmp_path))

    captured: dict[str, Any] = {}

    def _stub_render(
        url: str, *, timeout: int, wait_for: str | None = None, session: object = None
    ) -> RenderedPage:
        captured["url"] = url
        captured["timeout"] = timeout
        return RenderedPage(
            url=url,
            text="rendered",
            title="R",
            content_type="render",
            fetch_metadata=FetchMetadata(
                access_date=utc_today_iso(),
                http_status=200,
                final_url=url,
                fetch_method="render",
                elapsed_ms=1,
                wait_for=wait_for,
            ),
        )

    monkeypatch.setattr(fetcher, "render_url", _stub_render)

    def _fail_download(_url: str) -> Any:
        raise AssertionError("force_render should bypass _download")

    monkeypatch.setattr(fetcher, "_download", _fail_download)

    result = fetcher.scrape_url("https://x.gov/", force_render=True, force_refresh=True)
    assert result.text == "rendered"
    assert result.content_type == "render"
    assert captured["url"] == "https://x.gov/"


def test_scrape_url_falls_back_to_render_on_empty_html(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
):
    """When html parse yields no text, render_url is invoked as a fallback."""
    monkeypatch.setattr(fetcher.config, "CACHE_DIR", str(tmp_path))

    def _stub_download(_url: str) -> tuple[bytes, str, int, str, int]:
        return (b"<html><body></body></html>", "text/html", 200, "https://x.gov/", 12)

    monkeypatch.setattr(fetcher, "_download", _stub_download)

    rendered_called: dict[str, Any] = {"count": 0}

    def _stub_render(
        url: str, *, timeout: int, wait_for: str | None = None, session: object = None
    ) -> RenderedPage:
        rendered_called["count"] += 1
        return RenderedPage(
            url=url,
            text="rendered text",
            title="X",
            content_type="render",
            fetch_metadata=FetchMetadata(
                access_date=utc_today_iso(),
                http_status=200,
                final_url=url,
                fetch_method="render",
                elapsed_ms=5,
                wait_for=wait_for,
            ),
        )

    monkeypatch.setattr(fetcher, "render_url", _stub_render)

    result = fetcher.scrape_url("https://x.gov/", force_refresh=True)
    assert rendered_called["count"] == 1
    assert result.text == "rendered text"
    assert result.content_type == "render"


def test_scrape_url_html_path_emits_fetch_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
):
    """The deterministic html path must emit fetch_metadata with the access date (Q10)."""
    monkeypatch.setattr(fetcher.config, "CACHE_DIR", str(tmp_path))

    def _stub_download(_url: str) -> tuple[bytes, str, int, str, int]:
        body = (
            b"<html><head><title>Hi</title></head>"
            b"<body><main>" + b"x" * 100 + b" word word word</main></body></html>"
        )
        return (body, "text/html", 200, "https://x.gov/page", 21)

    monkeypatch.setattr(fetcher, "_download", _stub_download)

    def _no_render(*_: Any, **__: Any) -> None:
        raise AssertionError("html path returned text; render must not run")

    monkeypatch.setattr(fetcher, "render_url", _no_render)

    result = fetcher.scrape_url("https://x.gov/page", force_refresh=True)
    assert result.fetch_metadata.fetch_method == "html"
    assert result.fetch_metadata.http_status == 200
    assert result.fetch_metadata.final_url == "https://x.gov/page"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", result.fetch_metadata.access_date)
    assert result.title == "Hi"


def test_scrape_url_caches_rendered_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
):
    """Successful scrapes round-trip through the on-disk RenderedPage cache."""
    monkeypatch.setattr(fetcher.config, "CACHE_DIR", str(tmp_path))

    call_count = {"n": 0}

    def _stub_download(_url: str) -> tuple[bytes, str, int, str, int]:
        call_count["n"] += 1
        body = (
            b"<html><head><title>Cache Me</title></head>"
            b"<body><main>" + b"x" * 100 + b" word word word</main></body></html>"
        )
        return (body, "text/html", 200, "https://x.gov/", 7)

    monkeypatch.setattr(fetcher, "_download", _stub_download)
    monkeypatch.setattr(
        fetcher, "render_url", lambda *_a, **_k: pytest.fail("should not render")
    )

    first = fetcher.scrape_url("https://x.gov/", force_refresh=True)
    second = fetcher.scrape_url("https://x.gov/")
    assert call_count["n"] == 1
    assert first == second
    assert isinstance(second, RenderedPage)


# ---------------------------------------------------------------------------
# RenderSession — reusable browser across renders (review F14)
# ---------------------------------------------------------------------------


class _SessionStubPage:
    def __init__(self, status=200, text="sess body", title="Sess", final_url="https://e/"):
        self._status = status
        self._text = text
        self._title = title
        self.url = final_url
        self.closed = False

    def goto(self, url, *, timeout, wait_until):
        return _StubResponse(self._status)

    def wait_for_selector(self, selector, *, timeout):
        pass

    def wait_for_load_state(self, state, *, timeout):
        pass

    def inner_text(self, _selector):
        return self._text

    def title(self):
        return self._title

    def close(self):
        self.closed = True


class _SessionStubContext:
    def __init__(self):
        self.pages: list[_SessionStubPage] = []
        self.closed = False

    def new_page(self):
        page = _SessionStubPage()
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class _SessionStubBrowser:
    def __init__(self, context):
        self._context = context
        self.closed = False

    def new_context(self):
        return self._context

    def close(self):
        self.closed = True


class _SessionStubChromium:
    def __init__(self, browser):
        self._browser = browser
        self.launch_count = 0

    def launch(self, **_kwargs):
        self.launch_count += 1
        return self._browser


class _SessionStubPlaywright:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stopped = False

    def stop(self):
        self.stopped = True


class _SessionStarter:
    """Object returned by ``sync_playwright()``; ``.start()`` yields the
    persistent Playwright (mirrors playwright's manual start/stop API)."""

    def __init__(self, pw):
        self._pw = pw

    def start(self):
        return self._pw


def _build_session_stub():
    context = _SessionStubContext()
    browser = _SessionStubBrowser(context)
    chromium = _SessionStubChromium(browser)
    pw = _SessionStubPlaywright(chromium)

    def factory():
        return _SessionStarter(pw)

    return factory, pw, browser, context, chromium


def test_render_session_reuses_one_browser_across_calls(
    monkeypatch: pytest.MonkeyPatch,
):
    factory, pw, browser, context, chromium = _build_session_stub()
    monkeypatch.setattr(render, "_import_sync_playwright", lambda: factory)

    from g3o.scrape.render import RenderSession, render_url

    with RenderSession() as session:
        r1 = render_url("https://a.gov/", session=session)
        r2 = render_url("https://b.gov/", session=session)
        # One browser launched for both renders; not yet torn down.
        assert chromium.launch_count == 1
        assert browser.closed is False

    assert r1.content_type == "render"
    assert r2.text == "sess body"
    # One page opened + closed per render.
    assert len(context.pages) == 2
    assert all(p.closed for p in context.pages)
    # Session teardown closes context + browser and stops playwright.
    assert context.closed is True
    assert browser.closed is True
    assert pw.stopped is True


def test_render_session_lazy_no_launch_without_render(
    monkeypatch: pytest.MonkeyPatch,
):
    factory, _pw, _browser, _context, chromium = _build_session_stub()
    monkeypatch.setattr(render, "_import_sync_playwright", lambda: factory)

    from g3o.scrape.render import RenderSession

    with RenderSession():
        pass  # no render_url call → Chromium must never launch

    assert chromium.launch_count == 0
