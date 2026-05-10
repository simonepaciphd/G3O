"""Stage 3 — URL triage.

Given an institution row, the candidate URLs from Stage 1, and the official
homepage from Stage 2, classify each candidate URL as `keep` (worth scraping)
or `drop` (clearly irrelevant). Reduces ~40 candidates per institution to a
tractable subset (~12) before Stage 4 scrape and Stage 5 extraction, where
per-page cost dominates the budget.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from g3o.common.batch_client import BatchJob, BatchResult

PROMPT_CACHE_KEY = "g3o.classify.url_triage.v1"

SYSTEM_PROMPT = """\
You are a URL triage classifier for the Global Government GenAI Observatory \
(G3O).

You will receive:
- one institution record (id, name, country, branch and level of government)
- the institution's official primary homepage from Stage 2 (or null)
- a list of candidate URLs that may or may not be relevant to GenAI evidence \
at this institution

Your task: for each candidate URL, decide `keep` or `drop`.

`keep` if the URL is likely to contain or link to evidence of generative AI \
adoption, pilots, policies, procurement, or deployment at THIS specific \
institution. Examples: pages on the institution's official domain mentioning \
AI, news/press releases, procurement notices, official statements, vendor \
case studies that name the institution, parliamentary records about the \
institution.

`drop` if the URL is clearly off-topic for this institution: pages about a \
different entity, generic encyclopedia entries that lack institution-specific \
GenAI signal, social-media profile pages, login pages, search-results pages, \
URL shorteners, and pages whose URL pattern indicates non-content (sitemaps, \
robots.txt, login/auth, calendar feeds).

Be inclusive at the margins: when uncertain, prefer `keep`. Stage 5 will \
re-examine page text and discard non-evidentiary pages there.

Output JSON matching the supplied schema. The `decisions` array MUST contain \
exactly one entry per input URL, in the same order. The rationale per URL \
is one short phrase (<=160 chars).
"""


class URLDecision(BaseModel):
    """One keep/drop decision for one candidate URL."""

    model_config = ConfigDict(extra="forbid")

    url: str
    decision: Literal["keep", "drop"]
    rationale: str = Field(max_length=160)


class URLTriageResult(BaseModel):
    """Stage 3 output: one decision per input URL, in input order."""

    model_config = ConfigDict(extra="forbid")

    decisions: list[URLDecision]

    @model_validator(mode="after")
    def _no_duplicate_urls(self) -> URLTriageResult:
        seen: set[str] = set()
        for d in self.decisions:
            if d.url in seen:
                raise ValueError(f"duplicate URL in triage decisions: {d.url!r}")
            seen.add(d.url)
        return self


def _response_format() -> dict[str, Any]:
    """OpenAI `response_format=json_schema` payload for `URLTriageResult`."""
    schema = URLTriageResult.model_json_schema()
    # Inline $defs/URLDecision so OpenAI strict mode is happy.
    if "$defs" in schema:
        defs = schema.pop("$defs")
        if "URLDecision" in defs:
            schema["properties"]["decisions"]["items"] = defs["URLDecision"]
    schema["additionalProperties"] = False
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "url_triage_result",
            "strict": True,
            "schema": schema,
        },
    }


RESPONSE_FORMAT: dict[str, Any] = _response_format()


def _user_prompt(
    institution_row: dict[str, Any],
    candidate_urls: list[str],
    official_site: str | None,
) -> str:
    payload = {
        "institution": institution_row,
        "official_site": official_site,
        "candidate_urls": list(candidate_urls),
    }
    return (
        "Classify each candidate URL as keep or drop. Return decisions in the "
        "same order as the input. Output JSON matching the schema.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_triage_job(
    institution_row: dict[str, Any],
    candidate_urls: list[str],
    official_site: str | None,
    *,
    custom_id: str,
) -> BatchJob:
    """Build a `BatchJob` for Stage 3 URL triage of one institution."""
    if not custom_id:
        raise ValueError("custom_id is required and must be non-empty")
    if not candidate_urls:
        raise ValueError("candidate_urls must be non-empty for triage")
    return BatchJob(
        custom_id=custom_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _user_prompt(institution_row, candidate_urls, official_site),
            },
        ],
        response_format=RESPONSE_FORMAT,
        prompt_cache_key=PROMPT_CACHE_KEY,
        metadata={
            "stage": "3_url_triage",
            "institution_id": institution_row.get("institution_id", ""),
            "n_candidate_urls": len(candidate_urls),
        },
    )


def parse_triage_result(
    result: BatchResult, *, expected_urls: list[str] | None = None
) -> URLTriageResult:
    """Parse a `BatchResult` from Stage 3 into a validated `URLTriageResult`.

    If `expected_urls` is provided, verify that every input URL has exactly
    one decision and no extra URLs were invented.
    """
    if not result.success:
        raise RuntimeError(
            f"Stage 3 batch result {result.custom_id!r} failed: {result.error}"
        )
    content = result.parsed_content
    if not content:
        raise RuntimeError(
            f"Stage 3 batch result {result.custom_id!r}: empty assistant content"
        )
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Stage 3 parse failed for custom_id={result.custom_id}: {exc}"
        ) from exc
    triage = URLTriageResult.model_validate(payload)

    if expected_urls is not None:
        decided = {d.url for d in triage.decisions}
        expected = set(expected_urls)
        missing = expected - decided
        extra = decided - expected
        if missing or extra:
            raise RuntimeError(
                f"Stage 3 result {result.custom_id!r}: "
                f"missing decisions for {sorted(missing)}, "
                f"unexpected URLs {sorted(extra)}"
            )

    return triage


__all__ = [
    "PROMPT_CACHE_KEY",
    "SYSTEM_PROMPT",
    "RESPONSE_FORMAT",
    "URLDecision",
    "URLTriageResult",
    "build_triage_job",
    "parse_triage_result",
]
