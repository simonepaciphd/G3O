"""API adapter TEMPLATE — copy to <source_id>.py and fill in.

Steps to make a new API source:
  1. Copy this file to pipeline/adapters/api/<source_id>.py.
  2. Keep the class named `Adapter` — that is what the CLI imports.
  3. Implement search() and fetch(). If the source is OCDS, leave extract()
     alone (the core OCDS extractor handles it); if not, override extract()
     with a per-source field map.
  4. Verify the source's row in config/sources.yaml — endpoint, auth,
     pagination, rate limit — and change `verification_status` off
     `unverified_snapshot`. The CLI refuses to run an unverified row.
  5. Validate on a small sample via tests/ before any full pull
     (`python -m pipeline.cli run <source_id> --limit 5`).

The intermediate dict that extract() returns uses ProcurementRecord's own field
names, plus the extension keys in core.standardize.EXTENSION_KEYS. Omit anything
the source does not evidence — never fill a gap with a placeholder value.

For OCDS-API sources, this is mostly: base URL + pagination + (optional) auth.
Most of the 67 OCDS sources differ only in those three things.
"""

from __future__ import annotations

from typing import Iterable

from ...core.base import SourceAdapter
from ...core.models import GenAIQuerySet, Hit, RawRecord


class Adapter(SourceAdapter):
    access_mode = "api"

    def search(self, queries: GenAIQuerySet) -> Iterable[Hit]:
        """Query the source API for GenAI-related notices.

        Prefer pushing query terms to the API (q= / keyword param) so only
        candidates come back. Handle pagination to enumerate all matches and
        yield a Hit per candidate. Respect rate limits from self.config.
        """
        raise NotImplementedError("Implement API search with query pushdown + pagination.")

    def fetch(self, hits: Iterable[Hit]) -> Iterable[RawRecord]:
        """Fetch full records for the hits.

        If search() already returned full payloads you may pass them through;
        otherwise GET each record. Cache raw payloads under data_cache/<source_id>/
        and set fetched_at + raw_payload_ref on each RawRecord.
        """
        raise NotImplementedError("Implement API fetch (+ raw payload caching).")

    # Non-OCDS only: uncomment and map source fields -> intermediate keys.
    # def extract(self, raw: RawRecord) -> dict:
    #     p = raw.payload
    #     return {
    #         "native_id": p["id"],
    #         "title": p.get("title"),
    #         "description": p.get("description"),
    #         "notice_type": ...,   # tender | award
    #         # ... map the rest per this API's schema
    #     }
