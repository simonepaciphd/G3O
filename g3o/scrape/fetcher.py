"""HTTP fetch + content-type routing.

Single entrypoint ``scrape_url()`` that downloads a URL once, decides whether
the response is HTML or PDF, and delegates extraction to the corresponding
sibling module. When the deterministic path returns no text and the caller
opts in (default), dispatches to ``g3o.scrape.render.render_url`` for a
headless render.

All paths return a ``RenderedPage`` so Stage 5 reads
``fetch_metadata.access_date`` regardless of how the page was fetched
(decision Q10, 2026-05-09).
"""

from __future__ import annotations

import hashlib
import os
import time

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from g3o.common import config
from g3o.scrape import html as html_mod
from g3o.scrape import pdf as pdf_mod
from g3o.scrape.render import (
    FetchMetadata,
    RenderedPage,
    render_url,
    utc_today_iso,
)

_session = requests.Session()
_session.headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": config.USER_AGENT,
}

# Cache file prefix; bumped from `page_` when RenderedPage replaced the legacy
# {text, links, url, content_type, success} dict shape (Session B, 2026-05-09).
_CACHE_PREFIX = "page_v2_"


def _cache_key(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def _cache_path(url: str) -> str:
    return os.path.join(config.CACHE_DIR, f"{_CACHE_PREFIX}{_cache_key(url)}.json")


def _save(page: RenderedPage) -> None:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(_cache_path(page.url), "w", encoding="utf-8") as f:
        f.write(page.model_dump_json())


def _load(url: str) -> RenderedPage | None:
    path = _cache_path(url)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return RenderedPage.model_validate_json(f.read())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _download(url: str) -> tuple[bytes, str, int, str, int]:
    """Return ``(content, content_type, http_status, final_url, elapsed_ms)``."""
    started = time.monotonic()
    r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return (
        r.content,
        r.headers.get("content-type", "").lower(),
        r.status_code,
        r.url,
        elapsed_ms,
    )


def _extract_html_title(soup: BeautifulSoup) -> str:
    """Best-effort HTML title: ``<title>`` then ``<h1>`` then empty."""
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return ""


def _extract_pdf_title(content: bytes) -> str:
    """Best-effort PDF title from document metadata; empty if pdfplumber missing."""
    if not pdf_mod.PDF_SUPPORT:
        return ""
    try:
        import io

        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return (pdf.metadata.get("Title") or "").strip()
    except Exception:
        return ""


def _failure_page(url: str, *, attempted_method: str) -> RenderedPage:
    """Build a no-text RenderedPage for download failures. Not cached."""
    return RenderedPage(
        url=url,
        text="",
        title="",
        content_type="unknown",
        fetch_metadata=FetchMetadata(
            access_date=utc_today_iso(),
            http_status=None,
            final_url=None,
            fetch_method=attempted_method,  # type: ignore[arg-type]
            elapsed_ms=None,
            wait_for=None,
        ),
    )


def scrape_url(
    url: str,
    *,
    force_refresh: bool = False,
    force_render: bool = False,
    prefer_render_on_empty: bool = True,
) -> RenderedPage:
    """Fetch a URL and return a ``RenderedPage``.

    Dispatch policy:

    - ``force_render=True`` always uses ``render_url``.
    - Otherwise the deterministic path (HTML or PDF) runs first; if it returns
      empty text and ``prefer_render_on_empty`` is True, ``render_url`` is
      invoked as a fallback.

    The supplied ``url`` is preserved as ``RenderedPage.url`` regardless of
    redirects (pipeline-spec §1: "do not silently redirect-and-attribute").
    Successful fetches are cached on disk under ``config.CACHE_DIR``.
    """
    if not force_refresh:
        cached = _load(url)
        if cached is not None:
            return cached

    if force_render:
        page = render_url(url, timeout=config.REQUEST_TIMEOUT * 1000)
        _save(page)
        return page

    try:
        content, ctype, status, final_url, elapsed_ms = _download(url)
    except Exception:
        # Optional render fallback when even the HTTP GET failed (e.g., 403 bot block).
        if prefer_render_on_empty:
            try:
                page = render_url(url, timeout=config.REQUEST_TIMEOUT * 1000)
                _save(page)
                return page
            except Exception:
                return _failure_page(url, attempted_method="html")
        return _failure_page(url, attempted_method="html")

    if "pdf" in ctype or url.lower().endswith(".pdf"):
        text = pdf_mod.extract_text(content)
        title = _extract_pdf_title(content)
        method = "pdf"
        content_type = "pdf"
    else:
        soup = BeautifulSoup(content, "html.parser")
        title = _extract_html_title(soup)
        text = html_mod.extract_text(soup)
        method = "html"
        content_type = "html"

    if not text and prefer_render_on_empty:
        try:
            page = render_url(url, timeout=config.REQUEST_TIMEOUT * 1000)
            _save(page)
            return page
        except Exception:
            # Render fallback failed; surface the deterministic-path empty result.
            pass

    page = RenderedPage(
        url=url,
        text=text,
        title=title,
        content_type=content_type,  # type: ignore[arg-type]
        fetch_metadata=FetchMetadata(
            access_date=utc_today_iso(),
            http_status=status,
            final_url=final_url,
            fetch_method=method,  # type: ignore[arg-type]
            elapsed_ms=elapsed_ms,
            wait_for=None,
        ),
    )
    _save(page)
    return page
