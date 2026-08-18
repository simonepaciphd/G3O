"""Single-owner OpenAI Batch API client for the G3O LLM stages.

Used by `g3o.classify` (Stages 2, 3), `g3o.extract` (Stage 5), and
`g3o.validate` (Stage 6). Forks of this client are not allowed: every LLM
stage in the pipeline submits through `submit_batch`, polls through
`poll_batch`, and parses results through `fetch_results`.

Prompt caching is automatic on the OpenAI side for prompts ≥1024 tokens with
matching prefixes; callers should keep the system message identical across
jobs in a batch. An optional `prompt_cache_key` per job pins cache locality.
"""

from __future__ import annotations

import io
import json
import logging
import math
import random
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from g3o.common import config
from g3o.common.credentials import ResolvedCredentials, resolve

logger = logging.getLogger(__name__)


# Default model id for every LLM stage. Sourced from ``config.OPENAI_MODEL`` so
# a single ``OPENAI_MODEL`` env var (or .env entry) overrides the pipeline-wide
# default; falls back to ``gpt-5-nano`` when unset (review F9, 2026-06-10).
DEFAULT_MODEL = config.OPENAI_MODEL
DEFAULT_COMPLETION_WINDOW = "24h"
DEFAULT_ENDPOINT = "/v1/chat/completions"

# Pinned generation parameter for every LLM stage (T1 reproducibility floor,
# researcher sign-off 2026-06-11). The GPT-5 reasoning family rejects any
# non-default ``temperature`` with a 400 ("Only the default (1) value is
# supported" — verified 2026-06-11 against OpenAI community/integration
# reports), so the one generation parameter available to pin is
# ``reasoning_effort``. It is pinned at the documented current default
# ("medium") so a server-side default change cannot silently alter outputs —
# OpenAI has drifted this default across model versions (gpt-5.1 changed it
# to "none"). Live acceptance by the Batch endpoint is confirmed by the
# ``verify-model`` preflight, which submits through this same serializer.
DEFAULT_REASONING_EFFORT = "medium"

# Documented OpenAI Batch API limits, verified 2026-06-10 against
# https://developers.openai.com/api/docs/guides/batch ("A single batch may
# include up to 50,000 requests, and a batch input file can be up to 200 MB
# in size"). The docs do not state whether "200 MB" means 10^6 or 2^20 bytes.
BATCH_MAX_INPUT_FILE_BYTES = 200 * 1000 * 1000
BATCH_MAX_REQUESTS = 50_000

# Per-chunk submission caps (engineering parameters, Session F.1 2026-06-10).
# ~50% headroom under the documented limits: the payload bytes computed at
# split time are exactly the bytes uploaded, so headroom only has to absorb
# the MB-vs-MiB ambiguity above and undocumented server-side overhead, while
# keeping the chunk count low (a 1,000-institution Stage 5 run at a few
# hundred MB splits into single-digit chunks).
CHUNK_MAX_BYTES = 100 * 1024 * 1024
CHUNK_MAX_REQUESTS = 25_000

# Enqueued-token ceiling (2026-08-03). Distinct from the two caps above, and
# the binding one in practice: OpenAI limits the tokens an organization may
# have *enqueued at once* per model, counting the full prompt of every queued
# request whether or not it prompt-caches. Stage 5 at n=100 first hit this —
# 681 jobs needing ~10.6M enqueued against a 2M ceiling — because the ~10.4k-
# token output contract is re-sent per page, so the ceiling binds on
# (job count x shared prefix), not on page content.
#
# ENQUEUED_TOKEN_LIMIT is the org/model ceiling as reported by the API's
# `token_limit_exceeded` error. It is a property of the account tier, not of
# this code: raise it here only to match a raised account limit.
ENQUEUED_TOKEN_LIMIT = 2_000_000

# Fraction of the ceiling this pipeline will occupy. Headroom matters because
# the estimator below is approximate and because other work in the same org
# competes for the same ceiling.
ENQUEUED_BUDGET_UTILISATION = 0.8

# Serialized JSONL bytes per token, for the offline estimate in
# `estimate_job_tokens`. Deliberately *below* the measured ratio so the
# estimate runs high: an overestimate costs an extra wave, an underestimate
# costs a failed submit. Calibrated 2026-08-03 against tiktoken `o200k_base`
# over the 681 real Stage-5 jobs of run 20260802-e2e-100 — aggregate 4.54
# bytes/token, per-job p05 3.83, per-job min 2.55. tiktoken is not a declared
# runtime dependency, which is why this is a calibrated constant rather than a
# live tokenizer call.
BYTES_PER_TOKEN = 4.0

# Metadata keys that uniquely identify a pipeline batch chunk. When all three
# are present on a submit, lost-response retries and resume paths can
# reconcile against the server instead of double-creating (review F6).
CHUNK_METADATA_KEYS: frozenset[str] = frozenset(
    {"g3o_run_id", "g3o_stage", "g3o_chunk"}
)

# OpenAI batch terminal statuses — once reached, the batch will not change.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "expired", "cancelled"}
)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BatchJob:
    """One LLM call inside a batch.

    `custom_id` must be unique within the batch and round-trips back to the
    caller in `BatchResult.custom_id` so results can be matched to inputs.
    """

    custom_id: str
    messages: list[dict[str, Any]]
    response_format: dict[str, Any] | None = None
    prompt_cache_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchHandle:
    batch_id: str
    input_file_id: str
    submitted_at: datetime
    n_jobs: int


@dataclass
class BatchStatus:
    batch_id: str
    status: str
    request_counts: dict[str, int]
    output_file_id: str | None
    error_file_id: str | None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"


@dataclass
class BatchResult:
    custom_id: str
    success: bool
    response: dict[str, Any] | None
    error: dict[str, Any] | None
    status_code: int | None = None

    @property
    def parsed_content(self) -> str | None:
        """The assistant message content, if the call succeeded."""
        if not self.success or self.response is None:
            return None
        choices = self.response.get("body", {}).get("choices", [])
        if not choices:
            return None
        return choices[0].get("message", {}).get("content")

    @property
    def response_model(self) -> str | None:
        """The versioned model id the server answered with (e.g.
        ``gpt-5-nano-2025-08-07``) — the provenance anchor for T1."""
        if self.response is None:
            return None
        return self.response.get("body", {}).get("model")

    @property
    def system_fingerprint(self) -> str | None:
        """The response ``system_fingerprint``, when the server returns one.

        Newer models often return null/omit it; callers must treat absence as
        normal and record it honestly rather than fabricate a value.
        """
        if self.response is None:
            return None
        return self.response.get("body", {}).get("system_fingerprint")

    @property
    def usage(self) -> dict[str, int] | None:
        """Token usage from the response body, if successful.

        Returns dict with keys: prompt_tokens, completion_tokens, total_tokens,
        and cached_tokens (for cached prompt tokens, may be 0).
        Returns None if the job failed or response is absent.
        """
        if not self.success or self.response is None:
            return None
        body = self.response.get("body", {})
        usage = body.get("usage")
        if usage is None:
            return None
        return {
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            # Fix: compute total_tokens from components when API returns 0 or omits it.
            # This prevents silent understatement of cost if a future consumer uses total_tokens.
            "total_tokens": (
                int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))
            ),
            # OpenAI may include cached_tokens in prompt_tokens_details
            "cached_tokens": int(
                (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            ),
        }


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def client_from_credentials(
    credentials: ResolvedCredentials | None = None,
) -> OpenAI | None:
    """Build an OpenAI client for ``credentials``, or ``None`` if no key resolves.

    The credential-aware constructor of Run API spec §3.2: the orchestrator
    resolves once and threads the bundle down, so a per-call key is possible for
    the first time. ``None`` for ``credentials`` resolves from the environment at
    call time (never at import — that was the defect §3 removes).

    Returning ``None`` rather than raising on a missing key is deliberate: it
    keeps client construction *lazy* at every call site that merely forwards a
    client. A stage that never reaches a live call must not die because a key was
    absent, and a caller that does reach one gets today's error from
    :func:`_default_client` at exactly the moment it always did.
    """
    resolved = credentials if credentials is not None else resolve()
    if not resolved.openai_api_key:
        return None
    return OpenAI(api_key=resolved.openai_api_key, max_retries=0)


def _default_client() -> OpenAI:
    """Build an OpenAI client from the ambient environment, or raise.

    The SDK's own retry is disabled in favor of tenacity at the function level
    (see _retryable). Reached only when a call site was given neither a client
    nor credentials.
    """
    cli = client_from_credentials()
    if cli is None:
        raise RuntimeError(
            "OPENAI_API_KEY is not set; pass an OpenAI client explicitly or "
            "configure the env var."
        )
    return cli


# Exceptions worth retrying: rate limits, transient connection issues, and
# 5xxs; not 4xx auth/validation errors.
_RETRYABLE_EXCEPTIONS = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
)

# Tenacity wrapper applied per network call. Session F.1 (2026-06-10, review
# F6): the retry is per-call, never around a function performing more than
# one server-side mutation — a whole-function retry around upload+create
# could double-create a live batch after a lost response.
_retryable = retry(
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    wait=wait_random_exponential(multiplier=1, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)

_MAX_CREATE_ATTEMPTS = 5


def _retry_sleep(attempt: int) -> None:
    """Jittered exponential backoff between batches.create attempts.

    Module-level so tests can monkeypatch it to a no-op.
    """
    time.sleep(min(60.0, float(2**attempt) + random.random()))


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


def _serialize_job_line(
    job: BatchJob,
    *,
    model: str,
    response_format: dict[str, Any] | None,
    endpoint: str,
    reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
) -> bytes:
    """Serialize one job to its JSONL line (including the trailing newline)."""
    body: dict[str, Any] = {"model": model, "messages": job.messages}
    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort
    rf = job.response_format if job.response_format is not None else response_format
    if rf is not None:
        body["response_format"] = rf
    if job.prompt_cache_key is not None:
        body["prompt_cache_key"] = job.prompt_cache_key
    record = {
        "custom_id": job.custom_id,
        "method": "POST",
        "url": endpoint,
        "body": body,
    }
    return (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")


def _build_jsonl_payload(
    jobs: list[BatchJob],
    *,
    model: str,
    response_format: dict[str, Any] | None,
    endpoint: str,
    reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
) -> bytes:
    """Serialize jobs to the OpenAI Batch API JSONL format."""
    if not jobs:
        raise ValueError("submit_batch: jobs list is empty")
    seen: set[str] = set()
    buf = io.BytesIO()
    for job in jobs:
        if job.custom_id in seen:
            raise ValueError(f"duplicate custom_id in batch: {job.custom_id!r}")
        seen.add(job.custom_id)
        buf.write(
            _serialize_job_line(
                job, model=model, response_format=response_format,
                endpoint=endpoint, reasoning_effort=reasoning_effort,
            )
        )
    return buf.getvalue()


def enqueued_token_budget(
    *,
    limit: int = ENQUEUED_TOKEN_LIMIT,
    utilisation: float = ENQUEUED_BUDGET_UTILISATION,
) -> int:
    """Tokens this pipeline will keep enqueued at once (2026-08-03).

    The usable slice of the org/model enqueued-token ceiling. Doubles as the
    per-chunk token cap, so one chunk can always fill a wave on its own and the
    wave scheduler in :func:`g3o.common.run_state.run_chunked_stage` can never
    deadlock on a chunk too large to submit.
    """
    return max(1, int(limit * utilisation))


def estimate_job_tokens(serialized_bytes: int) -> int:
    """Approximate the enqueued-token cost of one serialized job line.

    Offline and deliberately conservative — see :data:`BYTES_PER_TOKEN`. Used
    only for scheduling against the enqueued-token ceiling; never for billing,
    which is measured from the response's ``usage`` block.
    """
    return math.ceil(serialized_bytes / BYTES_PER_TOKEN)


def job_token_estimates(
    jobs: list[BatchJob],
    *,
    model: str,
    response_format: dict[str, Any] | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
) -> dict[str, int]:
    """Estimated enqueued tokens per ``custom_id``, for wave scheduling.

    Serializes each job exactly as :func:`submit_batch` will upload it, so the
    estimate tracks the same payload the ceiling is charged against.
    """
    return {
        job.custom_id: estimate_job_tokens(
            len(
                _serialize_job_line(
                    job,
                    model=model,
                    response_format=response_format,
                    endpoint=endpoint,
                    reasoning_effort=reasoning_effort,
                )
            )
        )
        for job in jobs
    }


def split_jobs_into_chunks(
    jobs: list[BatchJob],
    *,
    model: str,
    response_format: dict[str, Any] | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    max_bytes: int = CHUNK_MAX_BYTES,
    max_requests: int = CHUNK_MAX_REQUESTS,
    max_tokens: int | None = None,
    reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
) -> list[list[BatchJob]]:
    """Split jobs into size-capped sub-batches for chunked submission (review F2).

    Deterministic greedy packing in input order: a chunk closes when adding
    the next job would exceed ``max_bytes`` of serialized JSONL, ``max_tokens``
    of estimated enqueued tokens, or ``max_requests`` jobs. Sizes are computed
    on the exact bytes ``submit_batch`` will upload.

    ``max_tokens`` defaults to :func:`enqueued_token_budget` and is the cap
    that binds on the LLM-heavy stages (2026-08-03): the byte and request caps
    are orders of magnitude away from a real Stage-5 chunk, while the
    enqueued-token ceiling is reached at a few hundred jobs.

    Raises:
        ValueError: on an empty job list, a duplicate ``custom_id`` anywhere
            in the list, or a single job whose serialized line alone exceeds
            ``max_bytes`` — that job cannot be submitted at any chunking and
            points at missing page-text truncation (review F3, scheduled for
            the next hardening session).
    """
    if not jobs:
        raise ValueError("split_jobs_into_chunks: jobs list is empty")
    if max_tokens is None:
        max_tokens = enqueued_token_budget()
    seen: set[str] = set()
    chunks: list[list[BatchJob]] = []
    current: list[BatchJob] = []
    current_bytes = 0
    current_tokens = 0
    for job in jobs:
        if job.custom_id in seen:
            raise ValueError(f"duplicate custom_id in batch: {job.custom_id!r}")
        seen.add(job.custom_id)
        size = len(
            _serialize_job_line(
                job, model=model, response_format=response_format,
                endpoint=endpoint, reasoning_effort=reasoning_effort,
            )
        )
        if size > max_bytes:
            raise ValueError(
                f"single job {job.custom_id!r} serializes to {size:,} bytes, above "
                f"the per-chunk cap of {max_bytes:,} bytes; it cannot be submitted "
                f"at any chunking. This indicates an uncapped page text (review "
                f"F3 — page-text truncation, scheduled for the next hardening "
                f"session); cap the page feeding this job before resubmitting."
            )
        tokens = estimate_job_tokens(size)
        # A lone job above the token cap still has to go somewhere: it becomes
        # its own chunk (and its own wave) rather than an error. Unlike the byte
        # cap this is not a hard API limit on a single request — the ceiling is
        # on what may be enqueued concurrently, so a solo oversized chunk is
        # submittable, just not alongside anything else.
        if current and (
            current_bytes + size > max_bytes
            or current_tokens + tokens > max_tokens
            or len(current) >= max_requests
        ):
            chunks.append(current)
            current = []
            current_bytes = 0
            current_tokens = 0
        current.append(job)
        current_bytes += size
        current_tokens += tokens
    chunks.append(current)
    return chunks


@_retryable
def _create_input_file(cli: OpenAI, payload: bytes) -> Any:
    """Upload the JSONL input file, with per-call retry.

    A lost response after a server-side success leaves an orphaned uploaded
    file — no batch, no spend — so plain retry is safe here.
    """
    return cli.files.create(
        file=("g3o_batch.jsonl", io.BytesIO(payload), "application/jsonl"),
        purpose="batch",
    )


def _create_batch_with_reconcile(
    cli: OpenAI,
    *,
    input_file_id: str,
    endpoint: str,
    completion_window: str,
    metadata: dict[str, Any] | None,
) -> tuple[str, bool]:
    """Create the batch; reconcile by metadata before any retry (review F6a).

    ``batches.create`` is the spend-bearing mutation: a lost response after a
    server-side success means a live batch exists that the caller never saw,
    and a blind retry double-creates it. When ``metadata`` carries the unique
    chunk identity (``CHUNK_METADATA_KEYS``), every retry attempt is preceded
    by a metadata reconciliation pass — an existing batch is adopted instead
    of re-created. Metadata-less callers (the standalone CLI subcommands and
    ``verify-model``, all single-job batches) fall back to plain per-call
    retry, accepting the residual lost-response ambiguity.

    Reconciliation matches on the identity keys **only**, not on all of
    ``metadata``: since 2026-08-11 a submit also carries ``g3o_key_fingerprint``
    (Run API spec §3.5), which is provenance rather than identity. Matching on a
    superset of identity is how a reconcile pass misses a batch it should have
    adopted, and a missed adoption is a double submit.

    Returns:
        ``(batch_id, adopted)`` where ``adopted`` is True when the batch was
        found by reconciliation rather than created by this call.
    """
    identifying = metadata is not None and CHUNK_METADATA_KEYS <= set(metadata)
    identity = (
        {k: v for k, v in metadata.items() if k in CHUNK_METADATA_KEYS}
        if metadata is not None
        else None
    )
    for attempt in range(_MAX_CREATE_ATTEMPTS):
        if attempt and identifying:
            existing = find_batches_by_metadata(identity, client=cli)
            if len(existing) == 1:
                logger.warning(
                    "batches.create retry reconciled to existing batch %s "
                    "(metadata=%s); adopting instead of re-creating",
                    existing[0].batch_id, identity,
                )
                return existing[0].batch_id, True
            if len(existing) > 1:
                raise RuntimeError(
                    f"batches.create reconciliation found {len(existing)} batches "
                    f"matching metadata {identity}: "
                    f"{[s.batch_id for s in existing]}. A double-submit already "
                    f"exists server-side; cancel the duplicates before retrying."
                )
        try:
            batch = cli.batches.create(
                input_file_id=input_file_id,
                endpoint=endpoint,
                completion_window=completion_window,
                metadata=metadata,
            )
            return batch.id, False
        except _RETRYABLE_EXCEPTIONS as err:
            if attempt + 1 >= _MAX_CREATE_ATTEMPTS:
                logger.error(
                    "Batch API failed after %d retries. Last error: %s. "
                    "Check OpenAI status page at https://status.openai.com/ for service "
                    "outages or rate limit issues.",
                    attempt + 1, err,
                )
                raise RuntimeError(
                    f"Batch API failed after {attempt + 1} retries. Last error: {err}. "
                    f"Check OpenAI status page at https://status.openai.com/ for service "
                    f"outages or rate limit issues."
                ) from err
            _retry_sleep(attempt)
    raise AssertionError("unreachable")  # pragma: no cover


def submit_batch(
    jobs: list[BatchJob],
    *,
    model: str = DEFAULT_MODEL,
    response_format: dict[str, Any] | None = None,
    completion_window: str = DEFAULT_COMPLETION_WINDOW,
    endpoint: str = DEFAULT_ENDPOINT,
    metadata: dict[str, Any] | None = None,
    client: OpenAI | None = None,
    reasoning_effort: str | None = DEFAULT_REASONING_EFFORT,
) -> BatchHandle:
    """Upload a JSONL of jobs and create a Batch API job.

    `response_format` (a JSON schema dict) applies to every job unless the
    individual `BatchJob.response_format` overrides it. Every job body carries
    the pinned `reasoning_effort` (T1; pass None to omit). Retries are per-call
    (`_create_input_file`, `_create_batch_with_reconcile`), never around the
    whole upload+create pair (review F6a).
    """
    cli = client or _default_client()
    payload = _build_jsonl_payload(
        jobs, model=model, response_format=response_format, endpoint=endpoint,
        reasoning_effort=reasoning_effort,
    )
    if len(payload) > BATCH_MAX_INPUT_FILE_BYTES:
        raise ValueError(
            f"batch input file is {len(payload):,} bytes, above the documented "
            f"Batch API limit of {BATCH_MAX_INPUT_FILE_BYTES:,} bytes; split the "
            f"jobs with split_jobs_into_chunks before submitting."
        )
    file_obj = _create_input_file(cli, payload)
    batch_id, adopted = _create_batch_with_reconcile(
        cli,
        input_file_id=file_obj.id,
        endpoint=endpoint,
        completion_window=completion_window,
        metadata=metadata,
    )
    logger.info(
        "%s batch_id=%s input_file_id=%s n_jobs=%d",
        "adopted" if adopted else "submitted", batch_id, file_obj.id, len(jobs),
    )
    return BatchHandle(
        batch_id=batch_id,
        input_file_id=file_obj.id,
        submitted_at=datetime.now(timezone.utc),
        n_jobs=len(jobs),
    )


# ---------------------------------------------------------------------------
# Poll
# ---------------------------------------------------------------------------


def _coerce_batch_status(batch: Any) -> BatchStatus:
    """Coerce an SDK batch object into a :class:`BatchStatus`."""
    counts = getattr(batch, "request_counts", None)
    counts_dict: dict[str, int] = {}
    if counts is not None:
        # OpenAI returns a typed object with total/completed/failed; coerce.
        for k in ("total", "completed", "failed"):
            v = getattr(counts, k, None)
            if v is not None:
                counts_dict[k] = int(v)

    def _ts(epoch: int | None) -> datetime | None:
        return (
            datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch is not None else None
        )

    return BatchStatus(
        batch_id=batch.id,
        status=batch.status,
        request_counts=counts_dict,
        output_file_id=getattr(batch, "output_file_id", None),
        error_file_id=getattr(batch, "error_file_id", None),
        created_at=_ts(getattr(batch, "created_at", None)),
        completed_at=_ts(getattr(batch, "completed_at", None)),
    )


@_retryable
def poll_batch(
    batch_id: str, *, client: OpenAI | None = None
) -> BatchStatus:
    cli = client or _default_client()
    return _coerce_batch_status(cli.batches.retrieve(batch_id))


@_retryable
def _list_batches_page(cli: OpenAI, *, limit: int, after: str | None) -> Any:
    if after is None:
        return cli.batches.list(limit=limit)
    return cli.batches.list(limit=limit, after=after)


def find_batches_by_metadata(
    metadata: dict[str, Any],
    *,
    client: OpenAI | None = None,
    limit: int = 100,
    max_pages: int = 5,
) -> list[BatchStatus]:
    """List recent batches and return those whose metadata matches exactly.

    A batch matches when every key/value pair in ``metadata`` equals the
    batch's metadata (string comparison — the API stores metadata values as
    strings). Pagination is bounded at ``max_pages`` pages of ``limit``
    batches, newest first; pipeline reconciliation only ever looks for
    batches submitted within the current run's lifetime, so a bounded recent
    window is sufficient.
    """
    cli = client or _default_client()
    wanted = {str(k): str(v) for k, v in metadata.items()}
    matches: list[BatchStatus] = []
    after: str | None = None
    for _ in range(max_pages):
        page = _list_batches_page(cli, limit=limit, after=after)
        data = list(getattr(page, "data", None) or [])
        for batch in data:
            md = getattr(batch, "metadata", None) or {}
            if all(md.get(k) == v for k, v in wanted.items()):
                matches.append(_coerce_batch_status(batch))
        if not data or not getattr(page, "has_more", False):
            break
        after = data[-1].id
    return matches


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


def _iter_jsonl_lines(content: bytes | str) -> Iterator[dict[str, Any]]:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        yield json.loads(line)


@_retryable
def _fetch_file_content(file_id: str, *, client: OpenAI) -> bytes:
    resp = client.files.content(file_id)
    # The SDK exposes either .read() (bytes) or .text — accommodate both.
    if hasattr(resp, "read"):
        data = resp.read()
        return data if isinstance(data, bytes) else data.encode("utf-8")
    if hasattr(resp, "content"):
        data = resp.content
        return data if isinstance(data, bytes) else data.encode("utf-8")
    if hasattr(resp, "text"):
        return resp.text.encode("utf-8")
    raise RuntimeError(f"Unexpected file-content response shape: {type(resp).__name__}")


def fetch_results(
    batch_id: str,
    *,
    client: OpenAI | None = None,
    status: BatchStatus | None = None,
) -> Iterator[BatchResult]:
    """Yield one `BatchResult` per job in custom_id order from the API.

    Caller is responsible for ensuring the batch has reached a terminal state.
    Both the output file (successful jobs) and the error file (failed jobs)
    are streamed; jobs missing from both files yield nothing.
    """
    cli = client or _default_client()
    s = status or poll_batch(batch_id, client=cli)
    if not s.is_terminal:
        raise RuntimeError(
            f"batch {batch_id} is not terminal (status={s.status!r}); "
            f"call poll_batch until is_terminal"
        )

    if s.output_file_id is not None:
        for record in _iter_jsonl_lines(
            _fetch_file_content(s.output_file_id, client=cli)
        ):
            yield BatchResult(
                custom_id=record.get("custom_id", ""),
                success=record.get("error") is None,
                response=record.get("response"),
                error=record.get("error"),
                status_code=(record.get("response") or {}).get("status_code"),
            )

    if s.error_file_id is not None:
        for record in _iter_jsonl_lines(
            _fetch_file_content(s.error_file_id, client=cli)
        ):
            yield BatchResult(
                custom_id=record.get("custom_id", ""),
                success=False,
                response=None,
                error=record.get("error") or record,
                status_code=None,
            )


__all__ = [
    "BatchJob",
    "BatchHandle",
    "BatchStatus",
    "BatchResult",
    "BATCH_MAX_INPUT_FILE_BYTES",
    "BATCH_MAX_REQUESTS",
    "BYTES_PER_TOKEN",
    "CHUNK_MAX_BYTES",
    "CHUNK_MAX_REQUESTS",
    "CHUNK_METADATA_KEYS",
    "ENQUEUED_BUDGET_UTILISATION",
    "ENQUEUED_TOKEN_LIMIT",
    "enqueued_token_budget",
    "estimate_job_tokens",
    "job_token_estimates",
    "DEFAULT_MODEL",
    "DEFAULT_COMPLETION_WINDOW",
    "DEFAULT_ENDPOINT",
    "DEFAULT_REASONING_EFFORT",
    "TERMINAL_STATUSES",
    "client_from_credentials",
    "find_batches_by_metadata",
    "split_jobs_into_chunks",
    "submit_batch",
    "poll_batch",
    "fetch_results",
]
