"""Scrape layer: HTTP fetch + content extraction for HTML, PDF, and headless render."""

from g3o.scrape.fetcher import scrape_url
from g3o.scrape.html import check_keyword_proximity
from g3o.scrape.politeness import HostThrottle, RobotsCache
from g3o.scrape.render import (
    FetchMetadata,
    RenderedPage,
    RenderSession,
    render_url,
    utc_today_iso,
)

__all__ = [
    "FetchMetadata",
    "HostThrottle",
    "RenderSession",
    "RenderedPage",
    "RobotsCache",
    "check_keyword_proximity",
    "render_url",
    "scrape_url",
    "utc_today_iso",
]
