"""Stage 3 — URL triage via TypeSafe jev.

Converts the Stage 3 task (per-URL keep/drop decision) into jev Noul questions:

- One Noul per URL in a single request — the parallel fan-out the API is
  built for: ``keep_u{i}`` with the URL/title embedded in the instructions
  (no indirection) and keep/drop descriptions in ``criteria``, lifted from
  the current rubric including "be inclusive at the margins".

- Parse: ``keep iff noul >= KEEP_THRESHOLD`` (default 0.5; the inclusive
  margin argues for 0.4 — decide from the replay eval). Persist per-URL
  probabilities in ``3_triage.json``; re-thresholding becomes an offline
  code change with zero re-calls.

- The URL echo-back failure class (fabricated/rewritten/duplicate URLs;
  ``missing_decision`` / ``url_mismatch`` salvage) becomes structurally
  impossible: code owns the URL list. ``match_triage_decisions`` remains for
  the legacy nano path only.

See jev-integration-plan.md §3 for the full design.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

import typesafe_sdk as ts

from g3o.common.jev_client import JevAnswer, JevResult

# Question-set version (jev-integration-plan.md §3). Pin in goldens.
JEV_QUESTION_SET_VERSION = "g3o.classify.url_triage.jev.v1"

# Keep threshold (jev-integration-plan.md §3). Default 0.5 (symmetric); the
# inclusive margin argues for 0.4 — decide from the replay eval. Named
# constant so it can be re-tuned offline without re-calling the API.
KEEP_THRESHOLD = 0.5


@dataclass(frozen=True)
class JevURLDecision:
    """One keep/drop decision for one candidate URL, from jev."""

    url: str
    decision: Literal["keep", "drop"]
    noul: float  # P(keep), 0–1


@dataclass(frozen=True)
class JevURLTriageResult:
    """Stage 3 jev output: one decision per input URL, plus metadata."""

    decisions: list[JevURLDecision]
    kept_urls: list[str]
    response_model: str
    request_id: str | None


def build_triage_state(
    institution_row: dict[str, Any],
    candidate_urls: list[str],
    official_site: str | None,
    search_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the jev state for Stage 3.

    ``search_results`` is optional; if provided, it carries url/title/snippet
    for each candidate. If not provided, the state carries only the URLs.
    """
    if search_results is None:
        search_results = [{"url": u, "title": "", "snippet": ""} for u in candidate_urls]
    return {
        "institution": institution_row,
        "official_site": official_site,
        "candidate_urls": [
            {
                "url": r.get("link", r.get("url", u)),
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
            }
            for r, u in zip(search_results, candidate_urls)
        ],
    }


def build_triage_questions(
    candidate_urls: list[str],
) -> dict[str, ts.Noul]:
    """Build the jev questions for Stage 3.

    One Noul per URL: ``keep_u{i}`` with the URL embedded in the instructions.
    """
    questions: dict[str, ts.Noul] = {}
    for i, url in enumerate(candidate_urls):
        questions[f"keep_u{i}"] = ts.Noul(
            instructions=(
                f"Should the URL '{url}' be kept for further analysis? "
                f"Keep if the URL is likely to contain or link to evidence of "
                f"generative AI adoption, pilots, policies, procurement, or "
                f"deployment at THIS specific institution. Examples: pages on "
                f"the institution's official domain mentioning AI, news/press "
                f"releases, procurement notices, official statements, vendor "
                f"case studies that name the institution, parliamentary records "
                f"about the institution. Drop if the URL is clearly off-topic "
                f"for this institution: pages about a different entity, generic "
                f"encyclopedia entries that lack institution-specific GenAI "
                f"signal, social-media profile pages, login pages, search-results "
                f"pages, URL shorteners, and pages whose URL pattern indicates "
                f"non-content (sitemaps, robots.txt, login/auth, calendar feeds). "
                f"Be inclusive at the margins: when uncertain, prefer keep."
            ),
            criteria=ts.NoulCriteria(
                true="The URL should be kept for further analysis",
                false="The URL should be dropped",
            ),
        )
    return questions


def parse_triage_result(
    result: JevResult,
    candidate_urls: list[str],
    *,
    keep_threshold: float = KEEP_THRESHOLD,
) -> JevURLTriageResult:
    """Parse a JevResult from Stage 3 into a JevURLTriageResult.

    For each candidate URL, the corresponding Noul answer's ``noul`` value is
    P(keep). Keep iff ``noul >= keep_threshold``.
    """
    decisions: list[JevURLDecision] = []
    kept_urls: list[str] = []

    for i, url in enumerate(candidate_urls):
        question_id = f"keep_u{i}"
        answer = result.answers.get(question_id)
        if not isinstance(answer, JevAnswer) or answer.type != "noul":
            raise RuntimeError(
                f"Stage 3 jev result missing or invalid '{question_id}' answer"
            )
        noul = answer.noul or 0.0
        decision = "keep" if noul >= keep_threshold else "drop"
        decisions.append(JevURLDecision(url=url, decision=decision, noul=noul))
        if decision == "keep":
            kept_urls.append(url)

    return JevURLTriageResult(
        decisions=decisions,
        kept_urls=kept_urls,
        response_model=result.response_model,
        request_id=result.request_id,
    )


__all__ = [
    "JEV_QUESTION_SET_VERSION",
    "KEEP_THRESHOLD",
    "JevURLDecision",
    "JevURLTriageResult",
    "build_triage_questions",
    "build_triage_state",
    "parse_triage_result",
]
