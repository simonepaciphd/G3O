"""Bulk adapter TEMPLATE — copy to <source_id>.py and fill in.

Bulk sources publish downloadable files (CSV / JSON / XML / ZIP / OCDS release
packages) rather than a live query API. The pattern:
  - search(): download/locate the release files, iterate records, and use the
    shared local filter (core.search.local_filter) to keep GenAI candidates.
  - fetch(): usually a pass-through, since search already has the full records.
For OCDS bulk (OCDS release packages), leave extract() to the core OCDS extractor.
"""

from __future__ import annotations

from typing import Iterable

from ...core.base import SourceAdapter
from ...core.models import GenAIQuerySet, Hit, RawRecord


class Adapter(SourceAdapter):
    access_mode = "bulk"

    def search(self, queries: GenAIQuerySet) -> Iterable[Hit]:
        """Download the bulk release(s), iterate records, keep GenAI candidates.

        Locate files from self.config['bulk']; download to data_cache/<source_id>/;
        stream-parse (don't load huge files fully into memory); apply
        core.search.local_filter to reduce to candidates; yield a Hit each.
        """
        raise NotImplementedError("Implement bulk download + stream parse + local filter.")

    def fetch(self, hits: Iterable[Hit]) -> Iterable[RawRecord]:
        """Usually pass-through: wrap each candidate's parsed payload in a
        RawRecord (set fetched_at + raw_payload_ref to the cached file)."""
        raise NotImplementedError("Implement bulk fetch (typically pass-through).")

    # Non-OCDS only: override extract() with a per-source field map.
