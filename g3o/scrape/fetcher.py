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
from collections.abc import Callable

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from g3o.common import config
from g3o.scrape import html as html_mod
from g3o.scrape import pdf as pdf_mod
from g3o.scrape.render import (
    FetchMetadata,
    RenderedPage,
    RenderSession,
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

# A render-attempt telemetry hook. Called once per render attempt with keyword
# args ``url``, ``trigger`` ("download_failure" | "empty_after_strip"),
# ``outcome`` ("rendered" | "render_failed"), and ``result_len`` (non-whitespace
# length of the rendered text, or None when the render itself raised). The
# fetcher stays agnostic of the run context; the Stage 4 runner supplies a hook
# that records the attempt to the attrition ledger.
RenderAttemptCallback = Callable[..., None]


def _cache_key(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def _cache_path(url: str) -> str:
    return os.path.join(config.CACHE_DIR, f"{_CACHE_PREFIX}{_cache_key(url)}.json")


def _save(page: RenderedPage, *, min_chars: int = 1) -> None:
    # Don't cache below-floor pages (review F17, 2026-06-10; render-on-empty
    # fix, 2026-07-21): a page whose stripped text is under the caller's
    # empty-page floor should be re-attempted on the next run rather than frozen
    # into the shared cache and never refetched cross-run. ``min_chars`` defaults
    # to 1 (skip only empty/whitespace-only text) for standalone callers; the
    # Stage 4 path raises it to ``empty_page_min_chars`` so a near-empty JS-shell
    # page — including one whose render fallback failed or still stripped short —
    # cannot freeze cross-run. Download-failure pages already bypass the cache
    # via _failure_page.
    if len(page.text.strip()) < min_chars:
        return
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(_cache_path(page.url), "w", encoding="utf-8") as f:
        f.write(page.model_dump_json())


def _load(url: str, *, min_chars: int = 1) -> RenderedPage | None:
    path = _cache_path(url)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        cached = RenderedPage.model_validate_json(f.read())
    # Treat a cached below-floor page as a miss so the deterministic + render
    # path re-runs (F17: near-empty pages retry next run). Without this, a page
    # cached before this floor existed — or any short page — would short-circuit
    # here and never re-render. Pairs with _save's floor: below-floor pages are
    # neither stored nor served.
    if len(cached.text.strip()) < min_chars:
        return None
    return cached


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


def _notify_render_attempt(
    callback: RenderAttemptCallback | None,
    *,
    url: str,
    trigger: str,
    outcome: str,
    result_len: int | None,
) -> None:
    """Fire the render-attempt telemetry hook, if one was supplied.

    Called on *every* render attempt — download-failure- or empty-after-strip-
    triggered, success or failure — so the caller can account for the render
    rate and its cost without a silent retry. A no-op when ``callback`` is None,
    which keeps the low-level fetcher usable without a run context.
    """
    if callback is not None:
        callback(url=url, trigger=trigger, outcome=outcome, result_len=result_len)


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
    prefer_render_on_download_failure: bool = False,
    empty_page_min_chars: int = 1,
    render_session: RenderSession | None = None,
    on_render_attempt: RenderAttemptCallback | None = None,
) -> RenderedPage:
    """Fetch a URL and return a ``RenderedPage``.

    Dispatch policy:

    - ``force_render=True`` always uses ``render_url``.
    - Otherwise the deterministic path (HTML or PDF) runs first; if its stripped
      text is below ``empty_page_min_chars`` and ``prefer_render_on_empty`` is
      True, ``render_url`` is invoked as a fallback. ``empty_page_min_chars``
      defaults to 1 (render only on empty/whitespace-only text) for standalone
      callers; the Stage 4 runner raises it to ``PresweepConfig.
      empty_page_min_chars`` so a JS-shell page that strips to near-zero chars
      is rendered rather than passed through to Stage 5 as a silent
      ``empty_page_dropped``. The floor mirrors Stage 5's ``is_near_empty`` drop
      test so the render fires for exactly the pages the extractor would discard.
    - If the HTTP GET itself fails (e.g., 403 bot block, network error), a
      render fallback runs **only** when ``prefer_render_on_download_failure``
      is True. This defaults to False (review F14): rendering every dead URL —
      a full headless-browser launch + navigation per failure — is an
      IP-reputation risk on government hosts and a multi-hour wall-clock tax at
      ~12k URLs. The Stage 4 runner leaves it off by default
      (``PresweepConfig.scrape_render_on_download_failure``).

    Every render attempt (either trigger, success or failure) invokes
    ``on_render_attempt`` when supplied, so the caller can account for the
    render rate/cost; the fetcher itself never silently retries.

    When ``render_session`` is supplied, every render reuses that
    :class:`RenderSession`'s browser instead of launching a fresh Chromium per
    call (review F14 browser reuse).

    The supplied ``url`` is preserved as ``RenderedPage.url`` regardless of
    redirects (pipeline-spec §1: "do not silently redirect-and-attribute").
    Successful fetches are cached on disk under ``config.CACHE_DIR``.
    """
    # The disk cache must neither store nor serve a below-floor page when the
    # caller wants empty-page rendering: otherwise a near-empty page freezes
    # cross-run and never re-renders (contradicts F17). When
    # prefer_render_on_empty is off, a short page is legitimate content, so the
    # floor collapses to 1 (skip only empty/whitespace-only).
    cache_floor = empty_page_min_chars if prefer_render_on_empty else 1

    if not force_refresh:
        cached = _load(url, min_chars=cache_floor)
        if cached is not None:
            return cached

    if force_render:
        page = render_url(
            url, timeout=config.REQUEST_TIMEOUT * 1000, session=render_session
        )
        _save(page, min_chars=cache_floor)
        return page

    try:
        content, ctype, status, final_url, elapsed_ms = _download(url)
    except Exception:
        # Render fallback on a failed GET is opt-in (review F14): only when the
        # caller accepts the per-dead-URL browser-launch cost.
        if prefer_render_on_download_failure:
            try:
                page = render_url(
                    url, timeout=config.REQUEST_TIMEOUT * 1000, session=render_session
                )
            except Exception:
                _notify_render_attempt(
                    on_render_attempt, url=url,
                    trigger="download_failure", outcome="render_failed",
                    result_len=None,
                )
                return _failure_page(url, attempted_method="html")
            _notify_render_attempt(
                on_render_attempt, url=url,
                trigger="download_failure", outcome="rendered",
                result_len=len(page.text.strip()),
            )
            _save(page, min_chars=cache_floor)
            return page
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

    # Render fallback when the deterministic path yields text below the empty-
    # page floor. JS-shell government pages return 200 + near-zero stripped text
    # and would otherwise pass through to Stage 5 as a silent empty_page_dropped;
    # ``len(strip) < empty_page_min_chars`` mirrors Stage 5's is_near_empty drop
    # test so the render fires for exactly the pages the extractor would discard.
    if prefer_render_on_empty and len(text.strip()) < empty_page_min_chars:
        try:
            page = render_url(
                url, timeout=config.REQUEST_TIMEOUT * 1000, session=render_session
            )
        except Exception:
            # Render fallback failed; surface the deterministic-path empty result.
            _notify_render_attempt(
                on_render_attempt, url=url,
                trigger="empty_after_strip", outcome="render_failed",
                result_len=None,
            )
        else:
            _notify_render_attempt(
                on_render_attempt, url=url,
                trigger="empty_after_strip", outcome="rendered",
                result_len=len(page.text.strip()),
            )
            _save(page, min_chars=cache_floor)
            return page

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
    _save(page, min_chars=cache_floor)
    return page
