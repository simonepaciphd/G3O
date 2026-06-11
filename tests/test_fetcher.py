"""Stage 4 fetcher dispatch tests (review F19, Opus-side mechanical backfill).

``scrape_url`` is the single scrape entrypoint; its dispatch policy — cache
short-circuit, force-render, HTML/PDF content-type routing, render fallback on
download failure or empty text, and the F17 "don't cache empty pages" rule —
was previously exercised only by a single live ``@network`` test. These tests
mock ``_download`` and ``render_url`` so the routing logic is covered without
the network. Extraction internals (``html``/``pdf`` parsing) are mocked to
sentinels so each test isolates *dispatch*, not parsing.
"""

from __future__ import annotations

import os

import pytest

from g3o.common import config
from g3o.scrape import fetcher
from g3o.scrape.render import FetchMetadata, RenderedPage, utc_today_iso

HTML_BYTES = b"<html><head><title>T</title></head><body>hi</body></html>"


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the on-disk cache at a tmp dir so tests never read/write the real
    ``cache/`` and can assert on cache-file presence."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    yield


def _download_returning(
    *, content=HTML_BYTES, ctype="text/html", status=200, final_url="https://x.gov", ms=5
):
    def _f(url):
        return (content, ctype, status, final_url, ms)

    return _f


def _download_raising():
    def _f(url):
        raise RuntimeError("simulated download failure")

    return _f


def _rendered_page(url, text="RENDERED"):
    return RenderedPage(
        url=url,
        text=text,
        title="r",
        content_type="html",
        fetch_metadata=FetchMetadata(
            access_date=utc_today_iso(),
            http_status=200,
            final_url=url,
            fetch_method="render",
            elapsed_ms=1,
            wait_for=None,
        ),
    )


def _boom(*_a, **_k):
    raise AssertionError("should not be called on this path")


# ---------------------------------------------------------------------------
# Cache short-circuit + force flags
# ---------------------------------------------------------------------------


def test_cache_hit_short_circuits_download(monkeypatch):
    url = "https://cached.gov/p"
    fetcher._save(_rendered_page(url, text="FROM_CACHE"))
    monkeypatch.setattr(fetcher, "_download", _boom)

    page = fetcher.scrape_url(url)

    assert page.text == "FROM_CACHE"


def test_force_refresh_bypasses_cache(monkeypatch):
    url = "https://cached.gov/p"
    fetcher._save(_rendered_page(url, text="FROM_CACHE"))
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "FRESH")

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert page.text == "FRESH"


def test_force_render_uses_renderer_not_download(monkeypatch):
    url = "https://js.gov/p"
    monkeypatch.setattr(fetcher, "_download", _boom)
    monkeypatch.setattr(
        fetcher, "render_url", lambda u, timeout, session=None: _rendered_page(u)
    )

    page = fetcher.scrape_url(url, force_refresh=True, force_render=True)

    assert page.text == "RENDERED"
    assert page.fetch_metadata.fetch_method == "render"


# ---------------------------------------------------------------------------
# Content-type routing
# ---------------------------------------------------------------------------


def test_html_routing(monkeypatch):
    monkeypatch.setattr(fetcher, "_download", _download_returning(ctype="text/html"))
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "HTMLTEXT")
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", _boom)

    page = fetcher.scrape_url("https://x.gov", force_refresh=True, prefer_render_on_empty=False)

    assert page.content_type == "html"
    assert page.fetch_metadata.fetch_method == "html"
    assert page.text == "HTMLTEXT"


def test_pdf_routing_by_content_type(monkeypatch):
    monkeypatch.setattr(
        fetcher, "_download", _download_returning(content=b"%PDF-1.4", ctype="application/pdf")
    )
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda content: "PDFTEXT")
    monkeypatch.setattr(fetcher.html_mod, "extract_text", _boom)

    page = fetcher.scrape_url("https://x.gov/doc", force_refresh=True, prefer_render_on_empty=False)

    assert page.content_type == "pdf"
    assert page.fetch_metadata.fetch_method == "pdf"
    assert page.text == "PDFTEXT"


def test_pdf_routing_by_url_suffix(monkeypatch):
    # Empty content-type but a .pdf URL still routes to the PDF path.
    monkeypatch.setattr(
        fetcher, "_download", _download_returning(content=b"%PDF-1.4", ctype="")
    )
    monkeypatch.setattr(fetcher.pdf_mod, "extract_text", lambda content: "PDFTEXT")
    monkeypatch.setattr(fetcher.html_mod, "extract_text", _boom)

    page = fetcher.scrape_url(
        "https://x.gov/report.PDF", force_refresh=True, prefer_render_on_empty=False
    )

    assert page.content_type == "pdf"
    assert page.text == "PDFTEXT"


# ---------------------------------------------------------------------------
# Render fallback
# ---------------------------------------------------------------------------


def test_download_failure_falls_back_to_render(monkeypatch):
    # Review F14: render-on-download-failure is now opt-in via
    # prefer_render_on_download_failure (default off). With it enabled, a failed
    # GET still falls back to a render.
    url = "https://blocked.gov"
    monkeypatch.setattr(fetcher, "_download", _download_raising())
    monkeypatch.setattr(
        fetcher, "render_url", lambda u, timeout, session=None: _rendered_page(u)
    )

    page = fetcher.scrape_url(
        url, force_refresh=True, prefer_render_on_download_failure=True
    )

    assert page.text == "RENDERED"
    assert page.fetch_metadata.fetch_method == "render"


def test_download_failure_no_render_by_default(monkeypatch):
    # Review F14: with the default (prefer_render_on_download_failure=False), a
    # failed GET must NOT launch a render — it returns the failure page even
    # when prefer_render_on_empty is True.
    url = "https://blocked.gov"
    monkeypatch.setattr(fetcher, "_download", _download_raising())
    monkeypatch.setattr(fetcher, "render_url", _boom)

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=True)

    assert page.text == ""
    assert page.content_type == "unknown"
    assert page.fetch_metadata.fetch_method == "html"


def test_download_failure_returns_failure_page_when_render_disabled(monkeypatch):
    url = "https://blocked.gov"
    monkeypatch.setattr(fetcher, "_download", _download_raising())
    monkeypatch.setattr(fetcher, "render_url", _boom)

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert page.text == ""
    assert page.content_type == "unknown"
    assert page.fetch_metadata.fetch_method == "html"
    assert page.fetch_metadata.http_status is None


def test_empty_text_triggers_render_fallback(monkeypatch):
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "")
    monkeypatch.setattr(
        fetcher, "render_url", lambda u, timeout, session=None: _rendered_page(u)
    )

    page = fetcher.scrape_url("https://x.gov", force_refresh=True, prefer_render_on_empty=True)

    assert page.text == "RENDERED"


def test_empty_text_render_failure_surfaces_deterministic_empty(monkeypatch):
    # Deterministic path empty + render fallback itself fails → surface the
    # deterministic empty result (not a failure page).
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "")
    monkeypatch.setattr(fetcher, "render_url", _boom)

    page = fetcher.scrape_url("https://x.gov", force_refresh=True, prefer_render_on_empty=True)

    assert page.text == ""
    assert page.content_type == "html"
    assert page.fetch_metadata.fetch_method == "html"


# ---------------------------------------------------------------------------
# Caching policy (F17) + redirect attribution
# ---------------------------------------------------------------------------


def test_successful_page_is_cached(monkeypatch):
    url = "https://x.gov/keep"
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "TEXT")

    fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert os.path.exists(fetcher._cache_path(url))


def test_empty_text_page_is_not_cached(monkeypatch):
    # Review F17: an empty-text page must not be frozen into the shared cache.
    url = "https://x.gov/empty"
    monkeypatch.setattr(fetcher, "_download", _download_returning())
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "")

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert page.text == ""
    assert not os.path.exists(fetcher._cache_path(url))


def test_url_preserved_despite_redirect(monkeypatch):
    # pipeline-spec §1: "do not silently redirect-and-attribute".
    url = "https://x.gov/start"
    monkeypatch.setattr(
        fetcher, "_download", _download_returning(final_url="https://x.gov/redirected")
    )
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "TEXT")

    page = fetcher.scrape_url(url, force_refresh=True, prefer_render_on_empty=False)

    assert page.url == url
    assert page.fetch_metadata.final_url == "https://x.gov/redirected"
