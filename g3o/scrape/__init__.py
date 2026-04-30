"""Scrape layer: HTTP fetch + content extraction for HTML and PDF sources."""

from g3o.scrape.fetcher import scrape_url
from g3o.scrape.html import check_keyword_proximity

__all__ = ["scrape_url", "check_keyword_proximity"]
