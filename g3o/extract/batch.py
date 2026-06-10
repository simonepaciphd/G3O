"""Stage 5 batch assembly + submission helpers.

Thin convenience layer over ``g3o.common.batch_client`` that builds one
``BatchJob`` per (institution × scraped page) pair and exposes
submit/poll/fetch with the right metadata. The single owner of OpenAI
Batch API access remains ``batch_client``.

custom_id format: ``{institution_id}::{md5(url)}`` so a result row can be
matched back to the input page deterministically.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from typing import Any

from g3o.common.batch_client import (
    DEFAULT_COMPLETION_WINDOW,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    BatchHandle,
    BatchJob,
    BatchResult,
    BatchStatus,
    fetch_results,
    poll_batch,
    submit_batch,
)
from g3o.extract.client import RESPONSE_FORMAT, build_extract_job
from g3o.scrape.render import RenderedPage

# Page-text handling at the Stage 5 LLM boundary (Session F.2, 2026-06-10).
#
# DEFAULT_TEXT_CAP_CHARS / DEFAULT_TEXT_CAP_RULE: the D3 methodology decision
# (researcher, 2026-06-10) — cap each page's text at 60,000 chars, head+tail
# (first 30k + last 30k). The cap is applied here, at job construction, NOT at
# scrape time: the on-disk scrape artifacts keep full text (audit /
# reproducibility) and only the LLM input is bounded. This is the single point
# that covers html/pdf/render uniformly because every path produces a
# RenderedPage whose .text feeds build_extract_jobs. After this cap, Session 1's
# oversized-job refusal in split_jobs_into_chunks (which names F3) is unreachable
# in practice but stays as a backstop.
#
# EMPTY_PAGE_MIN_CHARS: pages with fewer than this many non-whitespace chars are
# dropped before job construction (review F5) — an engineering parameter, not a
# methodology surface (cf. D3). The contract's data:min_length=1 would otherwise
# pressure the model to fabricate a row from an empty page.
DEFAULT_TEXT_CAP_CHARS = 60_000
DEFAULT_TEXT_CAP_RULE = "head_tail"
EMPTY_PAGE_MIN_CHARS = 50

_TRUNC_MARKER = (
    "\n\n[... G3O: {omitted:,} chars of page text omitted to fit the "
    "{cap:,}-char Stage 5 extraction cap ...]\n\n"
)


def url_hash(url: str) -> str:
    """Stable per-URL hash used in the Stage 5 ``custom_id`` and the on-disk artifact tree."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def is_near_empty(text: str, *, min_chars: int = EMPTY_PAGE_MIN_CHARS) -> bool:
    """True if ``text`` has fewer than ``min_chars`` non-whitespace characters."""
    return len(text.strip()) < min_chars


def cap_page_text(
    text: str,
    *,
    max_chars: int = DEFAULT_TEXT_CAP_CHARS,
    rule: str = DEFAULT_TEXT_CAP_RULE,
) -> tuple[str, bool]:
    """Cap ``text`` at ``max_chars`` original characters (review F3 / D3).

    Returns ``(capped_text, was_truncated)``. When truncation occurs, exactly
    ``max_chars`` characters of the original are kept (plus a short, fixed
    omission marker that names how many chars were dropped):

    - ``rule="head"``: the first ``max_chars`` chars.
    - ``rule="head_tail"``: the first ``max_chars // 2`` and the last
      ``max_chars - max_chars // 2`` chars, marker between them.

    Deterministic: identical input always yields identical output.
    """
    n = len(text)
    if n <= max_chars:
        return text, False
    omitted = n - max_chars
    marker = _TRUNC_MARKER.format(omitted=omitted, cap=max_chars)
    if rule == "head":
        return text[:max_chars] + marker, True
    if rule == "head_tail":
        head = max_chars // 2
        tail = max_chars - head
        return text[:head] + marker + text[n - tail:], True
    raise ValueError(f"unknown truncation rule {rule!r}; expected 'head' or 'head_tail'")


def make_custom_id(institution_id: str, url: str) -> str:
    """Compose ``{institution_id}::{md5(url)}`` per pipeline-spec §4."""
    if not institution_id:
        raise ValueError("institution_id is required to build a Stage 5 custom_id")
    if not url:
        raise ValueError("url is required to build a Stage 5 custom_id")
    return f"{institution_id}::{url_hash(url)}"


def build_extract_jobs(
    institution_pages: Iterable[tuple[dict[str, Any], RenderedPage]],
    *,
    batch_id: str,
    institution_search_languages: str,
    chat_type: str = "web",
    model_label: str | None = None,
) -> list[BatchJob]:
    """Build one Stage 5 ``BatchJob`` per (institution_row, scraped_page) pair.

    ``institution_search_languages`` is the comma-separated ISO 639-1 string
    used during discovery for that institution; it lands in
    ``ContractRow.institution_search_languages`` (consistency check #4 keeps
    it identical across rows for the same institution).
    """
    jobs: list[BatchJob] = []
    for institution_row, page in institution_pages:
        institution_id = institution_row.get("institution_id", "")
        custom_id = make_custom_id(institution_id, page.url)
        jobs.append(
            build_extract_job(
                institution_row,
                page,
                custom_id=custom_id,
                batch_id=batch_id,
                institution_search_languages=institution_search_languages,
                chat_type=chat_type,
                model_label=model_label,
            )
        )
    return jobs


def submit_extract_batch(
    jobs: list[BatchJob],
    *,
    model: str = DEFAULT_MODEL,
    completion_window: str = DEFAULT_COMPLETION_WINDOW,
    metadata: dict[str, Any] | None = None,
    client: Any | None = None,
) -> BatchHandle:
    """Submit a Stage 5 batch via the single-owner OpenAI client.

    Convenience wrapper for standalone use. The presweep orchestrator does
    not route through it — :func:`g3o.common.run_state.run_chunked_stage`
    submits chunked batches with full ``{g3o_run_id, g3o_stage, g3o_chunk}``
    metadata; this wrapper tags only ``g3o_stage`` (same key convention) and
    its batches are never adopted by reconciliation.
    """
    base_metadata = {"g3o_stage": "extract"}
    if metadata:
        base_metadata.update(metadata)
    return submit_batch(
        jobs,
        model=model,
        response_format=RESPONSE_FORMAT,
        completion_window=completion_window,
        endpoint=DEFAULT_ENDPOINT,
        metadata=base_metadata,
        client=client,
    )


def poll_extract_batch(batch_id: str, *, client: Any | None = None) -> BatchStatus:
    return poll_batch(batch_id, client=client)


def fetch_extract_results(
    batch_id: str,
    *,
    client: Any | None = None,
    status: BatchStatus | None = None,
) -> Iterator[BatchResult]:
    return fetch_results(batch_id, client=client, status=status)


__all__ = [
    "DEFAULT_TEXT_CAP_CHARS",
    "DEFAULT_TEXT_CAP_RULE",
    "EMPTY_PAGE_MIN_CHARS",
    "build_extract_jobs",
    "cap_page_text",
    "fetch_extract_results",
    "is_near_empty",
    "make_custom_id",
    "poll_extract_batch",
    "submit_extract_batch",
    "url_hash",
]
