"""Scrape adapter TEMPLATE — copy to <source_id>.py and fill in.

Scrape sources expose only web pages / search results (no API, no bulk). These
are almost always non-OCDS, so you WILL override extract() with a field map.

Before scaling any scraper: check robots.txt, terms of service, and rate limits;
use a polite delay; identify a stable User-Agent. Record findings in the tracker
`notes_RA` column. When a portal blocks or geoblocks, note it and move on — do
not hammer it.
"""

from __future__ import annotations

from typing import Iterable

from ...core.base import SourceAdapter
from ...core.models import GenAIQuerySet, Hit, RawRecord


class Adapter(SourceAdapter):
    access_mode = "scrape"

    def search(self, queries: GenAIQuerySet) -> Iterable[Hit]:
        """Submit the portal's search with GenAI terms (pushdown) and paginate
        result pages; yield a Hit (result URL) per candidate. Respect
        scrape.polite_delay_s and robots rules from self.config."""
        raise NotImplementedError("Implement portal search + result pagination (politely).")

    def fetch(self, hits: Iterable[Hit]) -> Iterable[RawRecord]:
        """GET each result/detail page; cache raw HTML to data_cache/<source_id>/;
        set fetched_at + raw_payload_ref. Do NOT parse here — parsing is extract()."""
        raise NotImplementedError("Implement detail-page fetch + HTML caching.")

    def extract(self, raw: RawRecord) -> dict:
        """Parse cached HTML into the intermediate field dict using the selectors
        in self.config['field_map']. Non-OCDS: this override is required."""
        raise NotImplementedError("Parse HTML per config field_map into intermediate keys.")
