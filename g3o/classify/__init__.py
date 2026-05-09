"""Classify layer (Stages 2 + 3): LLM filtering of discovery output.

Two LLM stages that operate on Stage 1 (Serper) candidate URLs before any page
text is fetched:

- **Stage 2 — official-site classification** (``official_site.py``): given the
  institution row and the candidate URLs, identify the official institutional
  homepage (or null if no confident match). One Batch API call per institution.

- **Stage 3 — URL triage** (``url_triage.py``): given the institution row, the
  candidate URLs, and the official site from Stage 2, classify each URL as
  ``keep`` (worth scraping) or ``drop`` (clearly irrelevant). Reduces the
  candidate set from ~40 URLs to ~12 per institution. One Batch API call per
  institution.

Both stages run on ``gpt-5-nano`` via the Batch API for the 50% pricing tier.
See ``README.md`` and the canonical pipeline spec at
``docs/budget/pipeline-spec-2026-05-08.md``.
"""

from g3o.classify.official_site import (
    OfficialSiteResult,
    build_official_site_job,
    parse_official_site_result,
)
from g3o.classify.url_triage import (
    URLDecision,
    URLTriageResult,
    build_triage_job,
    parse_triage_result,
)

__all__ = [
    "OfficialSiteResult",
    "URLDecision",
    "URLTriageResult",
    "build_official_site_job",
    "parse_official_site_result",
    "build_triage_job",
    "parse_triage_result",
]
