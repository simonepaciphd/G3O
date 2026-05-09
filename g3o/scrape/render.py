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

import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


def render_url(
    url: str,
    *,
    timeout: int = 30000,
    wait_for: str | None = None,
) -> RenderedPage:
    """Headless-Chromium fetch.

    ``timeout`` is in milliseconds (playwright convention). ``wait_for`` is an
    optional CSS selector that must appear before the page is considered
    rendered; if ``None``, waits for ``networkidle`` (best-effort).

    Redirects are recorded in ``fetch_metadata.final_url`` only — the supplied
    ``url`` is the canonical ``RenderedPage.url`` per pipeline-spec §1.
    """
    sync_playwright = _import_sync_playwright()
    started = time.monotonic()
    status: int | None = None
    final_url: str | None = None
    text = ""
    title = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
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
    "RenderedPage",
    "render_url",
    "utc_today_iso",
]
