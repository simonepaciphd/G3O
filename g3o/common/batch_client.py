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
import os
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

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "gpt-5-nano"
DEFAULT_COMPLETION_WINDOW = "24h"
DEFAULT_ENDPOINT = "/v1/chat/completions"

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


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


def _default_client() -> OpenAI:
    """Build an OpenAI client. The SDK's own retry is disabled in favor of
    tenacity at the function level (see _retryable)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set; pass an OpenAI client explicitly or "
            "configure the env var."
        )
    return OpenAI(api_key=api_key, max_retries=0)


# Tenacity wrapper applied to each network call. Retries on rate limits,
# transient connection issues, and 5xxs; not on 4xx auth/validation errors.
_retryable = retry(
    retry=retry_if_exception_type(
        (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
    ),
    wait=wait_random_exponential(multiplier=1, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


def _build_jsonl_payload(
    jobs: list[BatchJob],
    *,
    model: str,
    response_format: dict[str, Any] | None,
    endpoint: str,
) -> bytes:
    """Serialize jobs to the OpenAI Batch API JSONL format."""
    if not jobs:
        raise ValueError("submit_batch: jobs list is empty")
    seen: set[str] = set()
    buf = io.StringIO()
    for job in jobs:
        if job.custom_id in seen:
            raise ValueError(f"duplicate custom_id in batch: {job.custom_id!r}")
        seen.add(job.custom_id)
        body: dict[str, Any] = {"model": model, "messages": job.messages}
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
        buf.write(json.dumps(record, ensure_ascii=False))
        buf.write("\n")
    return buf.getvalue().encode("utf-8")


@_retryable
def submit_batch(
    jobs: list[BatchJob],
    *,
    model: str = DEFAULT_MODEL,
    response_format: dict[str, Any] | None = None,
    completion_window: str = DEFAULT_COMPLETION_WINDOW,
    endpoint: str = DEFAULT_ENDPOINT,
    metadata: dict[str, Any] | None = None,
    client: OpenAI | None = None,
) -> BatchHandle:
    """Upload a JSONL of jobs and create a Batch API job.

    `response_format` (a JSON schema dict) applies to every job unless the
    individual `BatchJob.response_format` overrides it.
    """
    cli = client or _default_client()
    payload = _build_jsonl_payload(
        jobs, model=model, response_format=response_format, endpoint=endpoint
    )
    file_obj = cli.files.create(
        file=("g3o_batch.jsonl", io.BytesIO(payload), "application/jsonl"),
        purpose="batch",
    )
    batch = cli.batches.create(
        input_file_id=file_obj.id,
        endpoint=endpoint,
        completion_window=completion_window,
        metadata=metadata,
    )
    logger.info(
        "submitted batch_id=%s input_file_id=%s n_jobs=%d", batch.id, file_obj.id,
        len(jobs),
    )
    return BatchHandle(
        batch_id=batch.id,
        input_file_id=file_obj.id,
        submitted_at=datetime.now(timezone.utc),
        n_jobs=len(jobs),
    )


# ---------------------------------------------------------------------------
# Poll
# ---------------------------------------------------------------------------


@_retryable
def poll_batch(
    batch_id: str, *, client: OpenAI | None = None
) -> BatchStatus:
    cli = client or _default_client()
    batch = cli.batches.retrieve(batch_id)
    counts = batch.request_counts
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
    "DEFAULT_MODEL",
    "DEFAULT_COMPLETION_WINDOW",
    "DEFAULT_ENDPOINT",
    "TERMINAL_STATUSES",
    "submit_batch",
    "poll_batch",
    "fetch_results",
]
