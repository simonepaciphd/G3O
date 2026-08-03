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
import logging
import os
import threading
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

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

logger = logging.getLogger(__name__)

_SESSION_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": config.USER_AGENT,
}

# Thread-local requests.Session (Stage-4 concurrency thread-safety, 2026-07):
# a single shared Session is not thread-safe — its connection pool, cookie jar,
# and redirect handling race across worker threads. Each thread gets its own
# Session (with identical headers), created lazily on first use.
_thread_local = threading.local()


def _get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers = dict(_SESSION_HEADERS)
        _thread_local.session = session
    return session

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
    path = _cache_path(page.url)
    # Atomic write (Stage-4 concurrency thread-safety, 2026-07): the page cache
    # is shared cross-run and cross-institution — two worker threads scraping the
    # same URL race on the same cache file. A plain open(path, "w") lets a
    # concurrent reader observe a torn/partial file, whose model_validate_json
    # then raises and is swallowed upstream as a scrape_failed attrition (silent
    # evidence loss). A per-writer temp file + os.replace makes the swap atomic;
    # the temp name carries pid + thread id so two writers never collide.
    # Mirrors serper_client._save_cache.
    tmp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(page.model_dump_json())
    # Windows can transiently deny os.replace while a concurrent _load() read
    # holds the destination (no FILE_SHARE_DELETE); a bounded capped-backoff
    # retry clears it, a no-op first-try on POSIX. A cache write is best-effort:
    # if it never lands, log, drop the temp file, and give up rather than raise —
    # a missed cache write costs a re-fetch, never a crashed scrape.
    for attempt in range(12):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == 11:
                logger.warning("page cache write gave up after contention on %s", path)
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                return
            time.sleep(min(0.01 * (2**attempt), 0.25))


def _load(url: str, *, min_chars: int = 1) -> RenderedPage | None:
    path = _cache_path(url)
    if not os.path.exists(path):
        return None
    # Windows can transiently deny the read open while a concurrent writer's
    # os.replace swaps the destination (Stage-4 concurrency). A bounded
    # capped-backoff retry clears it; a persistent denial degrades to a cache
    # miss (the caller re-fetches), never a spurious scrape_failed. No-op
    # first-try on POSIX.
    raw: str | None = None
    for attempt in range(12):
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
            break
        except PermissionError:
            if attempt == 11:
                logger.warning("page cache read gave up after contention on %s", path)
                return None
            time.sleep(min(0.01 * (2**attempt), 0.25))
        except FileNotFoundError:
            return None  # replaced away between the exists() check and the open
    if raw is None:
        return None
    cached = RenderedPage.model_validate_json(raw)
    # Treat a cached below-floor page as a miss so the deterministic + render
    # path re-runs (F17: near-empty pages retry next run). Without this, a page
    # cached before this floor existed — or any short page — would short-circuit
    # here and never re-render. Pairs with _save's floor: below-floor pages are
    # neither stored nor served.
    if len(cached.text.strip()) < min_chars:
        return None
    return cached


# HTTP redirect statuses that carry a Location (per RFC 9110 / requests'
# REDIRECT_STATI). Followed manually below so each cross-host hop can be
# throttled at the boundary it crosses.
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 20  # loop guard; mirrors requests' default ceiling


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _download(
    url: str, *, on_redirect_hop: Callable[[str], None] | None = None
) -> tuple[bytes, str, int, str, int]:
    """Return ``(content, content_type, http_status, final_url, elapsed_ms)``.

    Redirects are followed **manually** (``allow_redirects=False``) rather than
    inside the session, so a cross-host redirect can be throttled at the point
    it crosses hosts: *before* issuing the GET for a hop that lands on a
    different host, ``on_redirect_hop`` is called with that destination URL.
    Stage 4 wires it to :meth:`HostThrottle.wait`, so a hop onto a host another
    worker is currently throttled against **waits its turn** — the same per-host
    contract a direct request to that host would get — instead of racing in
    (the redirect-destination finding). A same-host redirect (path-only, or
    ``http``->``https`` on one host) does not re-throttle: it is one logical
    request already covered by the origin's throttle entry. ``on_redirect_hop``
    defaults to None, so standalone/CLI fetches and the unit suite follow
    redirects with no throttle coupling.
    """
    started = time.monotonic()
    session = _get_session()
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        r = session.get(
            current, timeout=config.REQUEST_TIMEOUT, allow_redirects=False
        )
        location = (
            r.headers.get("location")
            if r.status_code in _REDIRECT_STATUSES
            else None
        )
        if location:
            destination = urljoin(current, location)
            # Throttle the destination host BEFORE the hop's GET, but only when
            # the host actually changes — a same-host hop is the same physical
            # server the origin request already spaced against.
            if on_redirect_hop is not None and (
                urlsplit(destination).hostname != urlsplit(current).hostname
            ):
                on_redirect_hop(destination)
            current = destination
            continue
        r.raise_for_status()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return (
            r.content,
            r.headers.get("content-type", "").lower(),
            r.status_code,
            r.url,
            elapsed_ms,
        )
    raise requests.TooManyRedirects(
        f"Exceeded {_MAX_REDIRECTS} redirects starting from {url}"
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
    on_redirect_hop: Callable[[str], None] | None = None,
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

    ``on_redirect_hop`` keeps this fetcher robots/throttle-agnostic while still
    letting a polite caller (Stage 4) close the redirect-throttle gap. It is
    forwarded to ``_download``, which follows redirects manually and calls it
    with each cross-host destination *before* issuing that hop's GET — so a
    redirect landing on a host another worker is throttled against waits its
    turn instead of racing in. Defaults to None (standalone/CLI fetches and the
    unit suite follow redirects with no throttle coupling).
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
        # Only pass the hop callback through when set, so callers/tests that
        # monkeypatch a url-only ``_download`` stay compatible.
        content, ctype, status, final_url, elapsed_ms = (
            _download(url, on_redirect_hop=on_redirect_hop)
            if on_redirect_hop is not None
            else _download(url)
        )
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
