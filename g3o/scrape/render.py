"""Stage 4 headless render adapter — playwright Chromium.

Used by ``g3o.scrape.fetcher`` when the deterministic ``html`` / ``pdf`` paths
fall short: JS-heavy pages, lazy-loaded content, login-walled or bot-detected
sites. Determines the canonical fetch shape (``RenderedPage``) that every
scrape path emits, so Stage 5 (extract) can read ``fetch_metadata.access_date``
without caring how the page was retrieved (decision Q10, 2026-05-09).

playwright is imported lazily inside ``render_url`` so the rest of the
codebase (and the unit tests) does not require the runtime browser binary.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from g3o.common import config
from g3o.scrape import egress

logger = logging.getLogger(__name__)

ContentType = Literal["html", "pdf", "render", "unknown"]
FetchMethod = Literal["html", "pdf", "render"]


def utc_today_iso() -> str:
    """ISO ``YYYY-MM-DD`` in UTC for ``FetchMetadata.access_date``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class FetchMetadata(BaseModel):
    """Per-page fetch provenance, owned by the scrape layer.

    ``access_date`` is the field Stage 5 copies into Output Contract column 32
    (``source_access_date``) per Q1 (2026-05-09): inject into the per-page
    user message, LLM copies verbatim. ``final_url`` records redirects but
    never replaces the supplied ``RenderedPage.url``.
    """

    model_config = ConfigDict(extra="forbid")

    access_date: str = Field(
        ..., description="ISO YYYY-MM-DD UTC date the page was retrieved."
    )
    http_status: int | None = Field(
        default=None, description="HTTP status code, when available."
    )
    final_url: str | None = Field(
        default=None,
        description="Post-redirect URL recorded for provenance; not used as source_url.",
    )
    fetch_method: FetchMethod
    elapsed_ms: int | None = None
    wait_for: str | None = Field(
        default=None,
        description="Selector or load-state used to gate the render, if any.",
    )


class RenderedPage(BaseModel):
    """The canonical scrape-layer output shape for Stage 5 extract.

    Every scrape path (``html``, ``pdf``, ``render``) returns this shape so
    the extractor can read ``fetch_metadata.access_date`` uniformly.
    """

    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        ...,
        description="The URL supplied to the scrape layer; preserved verbatim "
        "as Stage 5 source_url.",
    )
    text: str
    title: str
    content_type: ContentType
    fetch_metadata: FetchMetadata


def _import_sync_playwright():
    """Lazy import so unit tests can monkeypatch this without installing playwright."""
    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]

    return sync_playwright


def _drive_page(
    page: object, url: str, *, timeout: int, wait_for: str | None
) -> tuple[str, str, str | None, int | None]:
    """Navigate ``page`` to ``url`` and read out (text, title, final_url, status).

    The single point that drives a playwright page, shared by the ephemeral
    per-call browser path and the reusable :class:`RenderSession` path so both
    behave identically.
    """
    response = page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    if wait_for:
        page.wait_for_selector(wait_for, timeout=timeout)
    else:
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            # networkidle is best-effort; some pages keep long-poll connections open.
            pass
    text = page.inner_text("body")
    title = page.title()
    final_url = page.url
    status = response.status if response is not None else None
    return text, title, final_url, status


class RenderSession:
    """Reusable headless-Chromium browser for a batch of renders (review F14).

    Launch the browser once and render many pages through a single shared
    context, instead of launching a fresh Chromium per URL (the prior behavior
    — a multi-hour wall-clock + resource tax across ~12k URLs). Use as a
    context manager around a scrape loop and pass it to ``render_url``::

        with RenderSession() as session:
            page = render_url(url, session=session)

    The browser is launched **lazily** on the first ``new_page`` call, so a
    scrape run that never needs a render never starts Chromium (and an
    environment without the browser binary is unaffected unless a render
    actually fires). One playwright ``page`` is created and closed per render.

    **Recycling (2026-08-25).** The browser + context do *not* persist for the
    session's whole lifetime: they are torn down and relaunched every
    ``recycle_after`` renders. Closing the page per render does not reclaim
    everything Chromium accumulates (cache, service workers, per-origin state),
    so a browser held for an entire stage grows without bound. Run
    ``r20260824T215623Z-bb4e`` was OOM-killed 69 minutes into Stage 4 with
    ``max_workers 8`` on a 7.9 GB box: 4.2% -> 90.7% memory over 439 renders,
    process table 402 -> 787, no swap. Recycling bounds each worker's footprint
    at ``recycle_after`` pages instead of the whole stage, at the cost of one
    browser launch per ``recycle_after`` renders. ``recycle_after=0`` restores
    the previous hold-forever behaviour.
    """

    def __init__(self, *, recycle_after: int | None = None) -> None:
        self._pw: object | None = None
        self._browser: object | None = None
        self._context: object | None = None
        # Resolved per instance, not at import time, so the env var is readable
        # by a process that configures it after importing this module.
        self._recycle_after: int = (
            config.RENDER_RECYCLE_AFTER if recycle_after is None else recycle_after
        )
        self._rendered_since_launch: int = 0

    def __enter__(self) -> RenderSession:
        return self

    def _context_obj(self) -> object:
        if self._context is None:
            sync_playwright = _import_sync_playwright()
            self._pw = sync_playwright().start()
            # Egress (#90): the render is the third of Stage 4's three egress
            # points and has to leave from the same place as the other two — a
            # render that goes out direct would recover exactly the pages the
            # proxy exists to recover, from the identity that was blocked.
            # ``launch_kwargs`` rather than a literal ``proxy=None``: playwright
            # treats the key's presence as configuration, and passing None on
            # every direct launch would change the historical call.
            launch_kwargs: dict[str, object] = {"headless": True}
            proxy = egress.playwright_proxy()
            if proxy:
                launch_kwargs["proxy"] = proxy
            self._browser = self._pw.chromium.launch(**launch_kwargs)
            self._context = self._browser.new_context()
        return self._context

    def new_page(self) -> object:
        """A fresh page, recycling the browser first when the cap is reached.

        Called exactly once per render, which is what makes it the right place
        to count. The session is thread-local (one per scrape worker), so no
        lock is needed here.
        """
        if 0 < self._recycle_after <= self._rendered_since_launch:
            self._recycle()
        self._rendered_since_launch += 1
        return self._context_obj().new_page()

    def _recycle(self) -> None:
        """Tear the browser down so the next render launches a clean one.

        A teardown failure must not abort the scrape: a browser that has already
        died raises on close, and that is precisely the case where relaunching
        matters most. The handles are cleared either way, so ``_context_obj``
        relaunches lazily on the next call.
        """
        served = self._rendered_since_launch
        try:
            self.close()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "RenderSession: recycle teardown failed after %d renders "
                "(relaunching anyway): %s",
                served, exc,
            )
            self._pw = self._browser = self._context = None
        self._rendered_since_launch = 0

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._pw is not None:
                self._pw.stop()
            self._pw = self._browser = self._context = None
            # Keeps the invariant true in both directions: the counter always
            # means "renders served by the browser currently launched".
            self._rendered_since_launch = 0

    def __exit__(self, *_exc: object) -> bool:
        self.close()
        return False


def render_url(
    url: str,
    *,
    timeout: int = 30000,
    wait_for: str | None = None,
    session: RenderSession | None = None,
) -> RenderedPage:
    """Headless-Chromium fetch.

    ``timeout`` is in milliseconds (playwright convention). ``wait_for`` is an
    optional CSS selector that must appear before the page is considered
    rendered; if ``None``, waits for ``networkidle`` (best-effort).

    When ``session`` is supplied (review F14), the render reuses that
    :class:`RenderSession`'s browser context (one page opened + closed per
    call); otherwise a fresh browser is launched and torn down for this call
    alone (the prior behavior, kept for standalone use).

    Redirects are recorded in ``fetch_metadata.final_url`` only — the supplied
    ``url`` is the canonical ``RenderedPage.url`` per pipeline-spec §1.
    """
    started = time.monotonic()
    if session is not None:
        page = session.new_page()
        try:
            text, title, final_url, status = _drive_page(
                page, url, timeout=timeout, wait_for=wait_for
            )
        finally:
            page.close()
    else:
        sync_playwright = _import_sync_playwright()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                text, title, final_url, status = _drive_page(
                    page, url, timeout=timeout, wait_for=wait_for
                )
            finally:
                browser.close()
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return RenderedPage(
        url=url,
        text=text,
        title=title,
        content_type="render",
        fetch_metadata=FetchMetadata(
            access_date=utc_today_iso(),
            http_status=status,
            final_url=final_url,
            fetch_method="render",
            elapsed_ms=elapsed_ms,
            wait_for=wait_for,
        ),
    )


__all__ = [
    "ContentType",
    "FetchMethod",
    "FetchMetadata",
    "RenderSession",
    "RenderedPage",
    "render_url",
    "utc_today_iso",
]
