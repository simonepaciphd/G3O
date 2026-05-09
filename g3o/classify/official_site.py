"""Stage 2 — Official-site classification.

Given an institution row and the candidate URLs from Stage 1 Discovery, pick
the URL that is the institution's official primary homepage (or null if no
candidate is confidently the homepage), with a confidence score and a short
rationale.

The output schema lives in this module (`OfficialSiteResult`) rather than in
`g3o.common.contract`, because the contract module is reserved for Output
Contract v2.0 (the final-row schema). Stage-2 / Stage-3 schemas are
intermediate and stage-local.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from g3o.common.batch_client import BatchJob, BatchResult

PROMPT_CACHE_KEY = "g3o.classify.official_site.v1"

SYSTEM_PROMPT = """\
You are an institutional homepage classifier for the Global Government GenAI \
Observatory (G3O).

You will receive:
- one institution record (id, name, country, branch and level of government, \
plus any known aliases or domain hints)
- a list of candidate URLs that an upstream search step returned for this \
institution

Your task: identify the URL that is the institution's official primary \
homepage. If no candidate is confidently the official homepage, return null.

Definition of "official primary homepage":
- A government-controlled domain page that serves as the institution's main \
public-facing entry point.
- Subpages, news pages, third-party mirrors, encyclopedia entries, and pages \
about the institution (rather than from it) do NOT qualify.
- Prefer .gov / .gouv / national equivalents and the institution's own \
domain over Wikipedia, news, social media, or vendor pages.

Confidence scale:
- "high"   — official-domain landing page that unambiguously names this \
institution.
- "medium" — likely-official page with one minor concern (subpage rather than \
landing, language ambiguity, similar-name disambiguation).
- "low"    — plausible candidate but with real concerns (third-party mirror, \
weak signals).
- "none"   — used only when `url` is null.

Output JSON matching the supplied schema. The rationale is one short sentence \
(<=240 chars) explaining the decision.
"""


class OfficialSiteResult(BaseModel):
    """Stage 2 output: one URL (or null) plus confidence and rationale."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(
        description="Official institutional homepage URL, or null if no confident match."
    )
    confidence: Literal["high", "medium", "low", "none"]
    rationale: str = Field(max_length=240)


def _response_format() -> dict[str, Any]:
    """OpenAI `response_format=json_schema` payload for `OfficialSiteResult`."""
    schema = OfficialSiteResult.model_json_schema()
    schema["additionalProperties"] = False
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "official_site_result",
            "strict": True,
            "schema": schema,
        },
    }


RESPONSE_FORMAT: dict[str, Any] = _response_format()


def _user_prompt(institution_row: dict[str, Any], candidate_urls: list[str]) -> str:
    """Build the user message embedding institution metadata and candidate URLs."""
    payload = {
        "institution": institution_row,
        "candidate_urls": list(candidate_urls),
    }
    return (
        "Identify this institution's official primary homepage from the candidate "
        "URLs. Output JSON matching the schema.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_official_site_job(
    institution_row: dict[str, Any],
    candidate_urls: list[str],
    *,
    custom_id: str,
) -> BatchJob:
    """Build a `BatchJob` for Stage 2 classification of one institution."""
    if not custom_id:
        raise ValueError("custom_id is required and must be non-empty")
    return BatchJob(
        custom_id=custom_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(institution_row, candidate_urls)},
        ],
        response_format=RESPONSE_FORMAT,
        prompt_cache_key=PROMPT_CACHE_KEY,
        metadata={
            "stage": "2_official_site",
            "institution_id": institution_row.get("institution_id", ""),
        },
    )


def parse_official_site_result(result: BatchResult) -> OfficialSiteResult:
    """Parse a `BatchResult` from Stage 2 into a validated `OfficialSiteResult`."""
    if not result.success:
        raise RuntimeError(
            f"Stage 2 batch result {result.custom_id!r} failed: {result.error}"
        )
    content = result.parsed_content
    if not content:
        raise RuntimeError(
            f"Stage 2 batch result {result.custom_id!r}: empty assistant content"
        )
    payload = json.loads(content)
    return OfficialSiteResult.model_validate(payload)


__all__ = [
    "PROMPT_CACHE_KEY",
    "SYSTEM_PROMPT",
    "RESPONSE_FORMAT",
    "OfficialSiteResult",
    "build_official_site_job",
    "parse_official_site_result",
]
