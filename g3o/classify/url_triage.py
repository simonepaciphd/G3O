"""Stage 3 — URL triage.

Given an institution row, the candidate URLs from Stage 1, and the official
homepage from Stage 2, classify each candidate URL as `keep` (worth scraping)
or `drop` (clearly irrelevant). Reduces ~40 candidates per institution to a
tractable subset (~12) before Stage 4 scrape and Stage 5 extraction, where
per-page cost dominates the budget.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

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

    # NOTE: keep the docstring above byte-identical — pydantic emits it as the
    # JSON-schema ``description`` inside RESPONSE_FORMAT, which is sent to the
    # model and pinned by the reproducibility golden. Structural container only:
    # duplicate URLs are NOT rejected here — a duplicate is an LLM-drift failure
    # mode that Stage 3 salvages per-URL (see :func:`match_triage_decisions`)
    # rather than failing the whole institution.
    model_config = ConfigDict(extra="forbid")

    decisions: list[URLDecision]


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
    # Inclusion #3/#4: an empty or whitespace-only candidate URL is not a
    # scrapable target and must never be triaged. Reject at the boundary rather
    # than emit a decision request the model cannot meaningfully act on.
    for idx, url in enumerate(candidate_urls):
        if not url or not url.strip():
            raise ValueError(
                f"candidate_urls[{idx}] is empty or whitespace-only; "
                "empty candidate URLs are rejected (Inclusion #3/#4)"
            )
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
    """Parse a `BatchResult` from Stage 3 into a structurally-valid result.

    This does **structural** parsing only — it raises for the genuinely
    unrecoverable cases (batch-level failure, empty content, malformed JSON,
    and per-decision schema violations such as a bad ``decision`` enum or an
    oversized ``rationale``). It does **not** enforce a URL round-trip: the
    submitted candidate list is matched to the returned decisions by URL in
    :func:`match_triage_decisions`, which salvages the clean decisions and
    records the drifted/duplicate/missing ones per-URL instead of discarding
    the whole institution.

    ``expected_urls`` is accepted for backward compatibility (older callers and
    the ``triage`` debug CLI still pass it) but is now ignored here; URL-keyed
    matching lives in :func:`match_triage_decisions`.
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
    return URLTriageResult.model_validate(payload)


@dataclass(frozen=True)
class TriageAttrition:
    """One per-URL Stage 3 salvage casualty (feeds the attrition ledger).

    ``reason`` is a stable short code; ``detail`` is free text (outside the
    ledger dedup key) carrying the diagnostic sub-classification.
    """

    url: str
    reason: str
    detail: str | None = None


@dataclass(frozen=True)
class TriageMatch:
    """Result of matching submitted candidates against returned decisions.

    ``decisions`` are the salvaged decisions in candidate order — each concerns
    a candidate whose exact URL the model echoed, so a salvaged decision
    provably concerns its candidate URL. ``kept_urls`` is the ``keep`` subset of
    those. ``attrition`` names the casualties.
    """

    decisions: list[URLDecision]
    kept_urls: list[str]
    attrition: list[TriageAttrition]


def match_triage_decisions(
    candidate_urls: list[str], triage: URLTriageResult
) -> TriageMatch:
    """Match returned triage decisions to submitted candidates by **URL**.

    The submitted ``candidate_urls`` list (the path-aware deduped 1a+1b union,
    so entries are pairwise-distinct) is the stable identity. Each candidate is
    matched to the returned decision(s) whose echoed ``url`` *exactly equals*
    that candidate — the echoed URL is the model's own claim of identity, and
    because candidates are distinct an exact URL match uniquely identifies its
    candidate. A decision is salvaged only on an exact URL match, so a drifted,
    rewritten, or fabricated URL is never mis-attributed and never scraped —
    identical safety to strict positional matching.

    URL-keyed matching salvages *strictly more* than positional matching: a
    same-URL reorder (every candidate decided, but out of input order) is
    salvaged in full here, whereas positional matching would drop every
    displaced decision. The order the model emits its decisions in carries no
    weight: conflicts are broken by the order-invariant keep-wins rule below,
    so ``kept_urls`` depends only on the candidates and the decision multiset.

    Casualties (each a per-URL attrition record; the institution is never
    discarded wholesale):

    - ``missing_decision`` — a candidate no returned decision echoed.
    - ``duplicate_url`` — a candidate echoed by two or more decisions
      (a keep/drop conflict, or a plain repeat). The winner is resolved by an
      **order-invariant keep-wins** rule (decision 2): if any occurrence is a
      ``keep`` the candidate is kept, otherwise dropped — independent of the
      order the model emitted its decisions in. The candidate keeps a decision
      ("keep the data"); the surplus occurrences are recorded, and the
      ``detail`` distinguishes a genuine keep/drop conflict from a plain repeat.
    - ``url_mismatch`` — a returned decision whose echoed URL is not any
      candidate (a rewritten or fabricated URL). Recorded against the echoed URL
      and never salvaged.
    """
    decisions = triage.decisions
    candidate_index = {url: i for i, url in enumerate(candidate_urls)}

    # Decision indices grouped by the URL each decision echoed, preserving
    # emission order within a group so the tie-break below is deterministic.
    by_url: dict[str, list[int]] = {}
    for j, d in enumerate(decisions):
        by_url.setdefault(d.url, []).append(j)

    matched: list[URLDecision] = []
    kept_urls: list[str] = []
    attrition: list[TriageAttrition] = []

    for cand in candidate_urls:
        occ = by_url.get(cand)
        if not occ:
            attrition.append(
                TriageAttrition(cand, "missing_decision", "no returned decision echoed this URL")
            )
            continue
        occ_decisions = [decisions[j] for j in occ]
        keeps = [d for d in occ_decisions if d.decision == "keep"]
        # Order-invariant tie-break (decision 2): keep always wins. The winner
        # is drawn only from the winning class (a keep if any keep was echoed,
        # else a drop), so the salvaged decision's keep/drop value — and hence
        # ``kept_urls`` — is a pure function of the submitted candidates and the
        # *multiset* of returned decisions, never of the order the model emitted
        # them in. Within a class the lowest-index occurrence is taken so the
        # chosen decision object (and its rationale) is deterministic.
        winner = keeps[0] if keeps else occ_decisions[0]
        matched.append(winner)
        if winner.decision == "keep":
            kept_urls.append(cand)
        if len(occ) > 1:
            n_drop = len(occ_decisions) - len(keeps)
            if keeps and n_drop:
                detail = (
                    f"echoed {len(occ)}x with conflicting decisions "
                    f"({len(keeps)} keep / {n_drop} drop): keep/drop conflict, keep wins"
                )
            else:
                verdict = "keep" if keeps else "drop"
                detail = f"echoed {len(occ)}x (all {verdict}); first occurrence accepted"
            attrition.append(TriageAttrition(cand, "duplicate_url", detail))

    # Decisions whose echoed URL is not any candidate: rewritten or fabricated.
    for d in decisions:
        if d.url not in candidate_index:
            attrition.append(
                TriageAttrition(
                    d.url,
                    "url_mismatch",
                    "echoed URL not in candidate set (rewrite or fabrication)",
                )
            )

    return TriageMatch(decisions=matched, kept_urls=kept_urls, attrition=attrition)


__all__ = [
    "PROMPT_CACHE_KEY",
    "SYSTEM_PROMPT",
    "RESPONSE_FORMAT",
    "URLDecision",
    "URLTriageResult",
    "TriageAttrition",
    "TriageMatch",
    "build_triage_job",
    "parse_triage_result",
    "match_triage_decisions",
]
