"""Stage 2 — Official-site classification via TypeSafe jev.

Converts the Stage 2 task (pick the official homepage from candidates) into
a jev typed question:

- ``official_site``: Choice over positional ids (u0..uN, none). Option keys
  are positional ids, NOT the URLs themselves; each option's criteria carries
  the url/title/snippet. Code maps ``answer.choice`` back to the candidate by
  construction — this closes documented gap F13 (fabricated-URL xfail-strict
  test): a URL that was never a candidate is unrepresentable.

The state carries the institution row plus the search results (url/title/
snippet). Confidence level is derived from the Choice probability:
- max_prob >= 0.8 → "high"
- max_prob >= 0.5 → "medium"
- max_prob >= 0.3 → "low"
- max_prob < 0.3 → "none"

Confidence gate: jev Choice confidence < 0.5 → treat as no-site (url=None) +
attrition record. Thresholds are named code constants; probabilities are
stored so they can be re-tuned offline.

See jev-integration-plan.md §3 for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import typesafe_sdk as ts

from g3o.common.jev_client import JevAnswer, JevResult

# Question-set version (jev-integration-plan.md §3). Pin in goldens.
JEV_QUESTION_SET_VERSION = "g3o.classify.official_site.jev.v1"

# Confidence gate thresholds (jev-integration-plan.md §3). Named constants so
# they can be re-tuned offline without re-calling the API.
CONFIDENCE_THRESHOLD_LOW = 0.5
CONFIDENCE_THRESHOLD_HIGH = 0.8

# Confidence rubric levels (lifted from the nano SYSTEM_PROMPT).
CONFIDENCE_LEVELS = ["none", "low", "medium", "high"]


@dataclass(frozen=True)
class JevOfficialSiteResult:
    """Stage 2 jev output: one URL (or null) plus confidence and probabilities.

    ``rationale`` is dropped — jev cannot generate it, and it is audit-only
    today. Probabilities + confidence are a richer audit signal.
    """

    url: str | None
    confidence: Literal["high", "medium", "low", "none"]
    jev_confidence: float  # 0–1, from jev Choice answer
    choice_probabilities: dict[str, float]  # positional id → probability
    response_model: str
    request_id: str | None


def build_official_site_state(
    institution_row: dict[str, Any],
    search_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the jev state for Stage 2.

    ``search_results`` is a list of dicts with keys ``url``, ``title``,
    ``snippet`` (from Serper). The state is JSON-serialisable and carries
    everything jev needs to evaluate the questions.
    """
    return {
        "institution": institution_row,
        "search_results": [
            {
                "url": r.get("link", r.get("url", "")),
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
            }
            for r in search_results
        ],
    }


def build_official_site_questions(
    candidate_urls: list[str],
) -> dict[str, ts.Choice]:
    """Build the jev questions for Stage 2.

    ``candidate_urls`` is the list of URLs from discovery. One question:
    - ``official_site``: Choice over positional ids (u0..uN, none).
    """
    # Choice: positional ids, not URLs. Each option's criteria carries the
    # url/title/snippet from the state (jev reads the state, not the criteria).
    choice_criteria: dict[str, str] = {}
    for i, url in enumerate(candidate_urls):
        choice_criteria[f"u{i}"] = f"Candidate {i}: {url}"
    choice_criteria["none"] = "No candidate is the official homepage"

    official_site = ts.Choice(
        instructions=(
            "Identify the URL that is the institution's official primary "
            "homepage. A government-controlled domain page that serves as the "
            "institution's main public-facing entry point. Subpages, news "
            "pages, third-party mirrors, encyclopedia entries, and pages about "
            "the institution (rather than from it) do NOT qualify. Prefer "
            ".gov / .gouv / national equivalents and the institution's own "
            "domain over Wikipedia, news, social media, or vendor pages."
        ),
        criteria=choice_criteria,
    )

    return {
        "official_site": official_site,
    }


def parse_official_site_result(
    result: JevResult,
    candidate_urls: list[str],
) -> JevOfficialSiteResult:
    """Parse a JevResult from Stage 2 into a JevOfficialSiteResult.

    Maps the Choice answer's positional id back to the candidate URL. Applies
    the confidence gate: < 0.5 → url=None. Derives confidence level from the
    Choice probability (max_prob):
    - >= 0.8 → "high"
    - >= 0.5 → "medium"
    - >= 0.3 → "low"
    - < 0.3 → "none"
    """
    choice_answer = result.answers.get("official_site")

    if not isinstance(choice_answer, JevAnswer) or choice_answer.type != "choice":
        raise RuntimeError("Stage 2 jev result missing or invalid 'official_site' answer")

    # Map choice back to URL.
    choice = choice_answer.choice
    if choice == "none" or choice is None:
        url = None
    elif choice.startswith("u") and choice[1:].isdigit():
        idx = int(choice[1:])
        if 0 <= idx < len(candidate_urls):
            url = candidate_urls[idx]
        else:
            raise RuntimeError(f"Stage 2 jev choice index {idx} out of range")
    else:
        raise RuntimeError(f"Stage 2 jev choice {choice!r} is not a valid positional id")

    # Confidence gate.
    jev_confidence = choice_answer.confidence or 0.0
    if jev_confidence < CONFIDENCE_THRESHOLD_LOW:
        url = None

    # Derive confidence level from the chosen option's probability, not the max
    # across all options including "none" (Major #7 fix).
    probabilities = choice_answer.probabilities or {}
    # Get the probability for the chosen option, not the max
    choice_prob = probabilities.get(choice, 0.0) if choice else 0.0

    if choice_prob >= CONFIDENCE_THRESHOLD_HIGH:
        confidence_level = "high"
    elif choice_prob >= CONFIDENCE_THRESHOLD_LOW:
        confidence_level = "medium"
    elif choice_prob >= 0.3:
        confidence_level = "low"
    else:
        confidence_level = "none"

    return JevOfficialSiteResult(
        url=url,
        confidence=confidence_level,
        jev_confidence=jev_confidence,
        choice_probabilities=probabilities,
        response_model=result.response_model,
        request_id=result.request_id,
    )


__all__ = [
    "CONFIDENCE_LEVELS",
    "CONFIDENCE_THRESHOLD_HIGH",
    "CONFIDENCE_THRESHOLD_LOW",
    "JEV_QUESTION_SET_VERSION",
    "JevOfficialSiteResult",
    "build_official_site_questions",
    "build_official_site_state",
    "parse_official_site_result",
]
