"""Anthropic Messages + Message Batches client for the v2.7 extractor (T-022).

RC-D-001 A: the v2.7 extractor is Claude Haiku 5.5 (``claude-haiku-5-5``) at
medium effort. RC-D-001 B: sync Messages calls for testing (T-002, T-041,
T-072), Message Batches for full runs (T-073 and production). The OpenAI
client in ``g3o.common.batch_client`` stays for the v2.5 path; nothing here
imports it.

Design points:

- **No import-time dependency on the SDK.** ``anthropic`` is imported lazily,
  only when no client is injected, so the test suite and CI run without it and
  every test injects a fake. (The ``anthropic`` pin is T-020's note: it is
  added to ``requirements.txt`` / ``pyproject.toml`` when this path is wired.)
- **Request params are plain dicts** in the Messages API shape; the SDK's
  ``TypedDict`` params are dicts, so the same object goes to
  ``messages.create(**params)`` and into a batch ``Request``.
- **Structured output** through ``output_config.format`` (``json_schema``),
  with ``output_config.effort`` set explicitly (Haiku 5.5's default is medium,
  but the ruling names it, so the request states it).
- **custom_id** must match ``^[a-zA-Z0-9_-]{1,64}$`` on the Batches API, so
  the v2.5 ``{institution_id}::{md5(url)}`` form cannot be reused;
  :func:`make_custom_id` derives a hash id and callers keep the mapping.
- **Usage is recorded from the response** (RC-D-001 F: count tokens from
  response ``usage``, not from vendor dashboards).
- **Never truncates input.** The v2.5 60k head+tail cap does not apply on this
  path (T-022). :func:`split_for_batches` splits a job list across batches by
  count and bytes; a single request over ``max_request_bytes`` is refused,
  never cut.

Key material: the SDK reads ``ANTHROPIC_API_KEY`` itself; this module never
reads, logs or stores a key.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

EXTRACTOR_MODEL = "claude-haiku-5-5"
EXTRACTOR_EFFORT = "medium"
#: Output budget per extraction request (non-streaming; keeps sync calls under
#: the SDK's HTTP timeout).
DEFAULT_MAX_TOKENS = 16_000

#: Message Batches limits (Anthropic docs: up to 100,000 requests or 256 MB
#: per batch). The byte limit used for splitting keeps a margin below 256 MB.
BATCH_MAX_REQUESTS = 100_000
BATCH_MAX_BYTES = 200 * 1024 * 1024

#: Provisional per-request guard. A request whose serialized params exceed this
#: is refused (reported, never truncated). Not calibrated for the Haiku 5.5
#: tokenizer: T-002 records the account tier and token figures.
DEFAULT_MAX_REQUEST_BYTES = 2_500_000

_CUSTOM_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def make_custom_id(*parts: str, prefix: str = "x27") -> str:
    """Deterministic Batches-safe custom id from ``parts`` (e.g. institution id, URL)."""
    if not parts or any(not isinstance(p, str) or not p for p in parts):
        raise ValueError("custom id parts must be non-empty strings")
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:48]
    cid = f"{prefix}-{digest}"
    if not _CUSTOM_ID_RE.match(cid):
        raise ValueError(f"custom id {cid!r} does not match the Batches pattern")
    return cid


def build_params(
    *,
    system: str,
    user: str,
    output_schema: dict[str, Any],
    model: str = EXTRACTOR_MODEL,
    effort: str = EXTRACTOR_EFFORT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict[str, Any]:
    """Messages API params for one extraction request.

    No ``thinking`` key (Haiku 5.5 runs adaptive thinking by default), no
    sampling parameters, no assistant prefill.
    """
    if not system or not user:
        raise ValueError("system and user text are required")
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": output_schema},
        },
    }


def params_bytes(params: dict[str, Any]) -> int:
    return len(json.dumps(params, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


@dataclass(frozen=True)
class ExtractorJob:
    custom_id: str
    params: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _CUSTOM_ID_RE.match(self.custom_id):
            raise ValueError(f"custom_id {self.custom_id!r} does not match ^[a-zA-Z0-9_-]{{1,64}}$")


@dataclass(frozen=True)
class ExtractorResult:
    """One extraction call's outcome, sync or batch."""

    custom_id: str
    success: bool
    text: str | None
    error: dict[str, Any] | None
    response_model: str | None = None
    message_id: str | None = None
    request_id: str | None = None
    stop_reason: str | None = None
    usage: dict[str, Any] | None = None


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _usage_dict(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return dict(usage)
    dump = getattr(usage, "model_dump", None)
    if callable(dump):
        return dump()
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return {k: getattr(usage, k, None) for k in keys}


def result_from_message(custom_id: str, message: Any, *, request_id: str | None = None) -> ExtractorResult:
    """Turn a Messages API response into an :class:`ExtractorResult`.

    Only ``text`` blocks are read (thinking blocks are skipped). A
    ``refusal`` or ``max_tokens`` stop is a failure: the JSON would be absent
    or cut, and a cut answer is never parsed.
    """
    stop = _get(message, "stop_reason")
    base = {
        "custom_id": custom_id,
        "response_model": _get(message, "model"),
        "message_id": _get(message, "id"),
        "request_id": request_id,
        "stop_reason": stop,
        "usage": _usage_dict(_get(message, "usage")),
    }
    if stop == "refusal":
        details = _get(message, "stop_details")
        return ExtractorResult(success=False, text=None, error={
            "type": "refusal",
            "category": _get(details, "category") if details is not None else None,
        }, **base)
    if stop == "max_tokens":
        return ExtractorResult(success=False, text=None, error={"type": "max_tokens"}, **base)
    texts = [_get(b, "text") for b in (_get(message, "content") or []) if _get(b, "type") == "text"]
    text = "".join(t for t in texts if t)
    if not text:
        return ExtractorResult(success=False, text=None, error={"type": "empty_content"}, **base)
    return ExtractorResult(success=True, text=text, error=None, **base)


def split_for_batches(
    jobs: Iterable[ExtractorJob],
    *,
    max_requests: int = BATCH_MAX_REQUESTS,
    max_bytes: int = BATCH_MAX_BYTES,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
) -> tuple[list[list[ExtractorJob]], list[ExtractorJob]]:
    """Split jobs into batches within count and byte limits.

    Returns ``(batches, refused)``. A job larger than ``max_request_bytes`` is
    refused whole and reported to the caller; page text is never truncated.
    Order is preserved.
    """
    batches: list[list[ExtractorJob]] = []
    refused: list[ExtractorJob] = []
    cur: list[ExtractorJob] = []
    cur_bytes = 0
    for job in jobs:
        size = params_bytes(job.params)
        if size > max_request_bytes or size > max_bytes:
            refused.append(job)
            continue
        if cur and (len(cur) >= max_requests or cur_bytes + size > max_bytes):
            batches.append(cur)
            cur, cur_bytes = [], 0
        cur.append(job)
        cur_bytes += size
    if cur:
        batches.append(cur)
    return batches, refused


class AnthropicExtractorClient:
    """Thin wrapper over an ``anthropic.Anthropic`` client (sync + batches)."""

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            import anthropic  # lazy: not a dependency of the test suite

            client = anthropic.Anthropic()
        self._client = client

    # -- sync (testing legs: T-002, T-041, T-072) -------------------------
    def create(self, job: ExtractorJob) -> ExtractorResult:
        message = self._client.messages.create(**job.params)
        return result_from_message(job.custom_id, message, request_id=getattr(message, "_request_id", None))

    # -- batch (full runs) --------------------------------------------------
    def submit_batch(self, jobs: list[ExtractorJob]) -> str:
        if not jobs:
            raise ValueError("no jobs to submit")
        ids = [j.custom_id for j in jobs]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate custom_id in batch")
        requests = [{"custom_id": j.custom_id, "params": j.params} for j in jobs]
        batch = self._client.messages.batches.create(requests=requests)
        return _get(batch, "id")

    def batch_status(self, batch_id: str) -> str:
        return _get(self._client.messages.batches.retrieve(batch_id), "processing_status")

    def batch_results(self, batch_id: str) -> Iterator[ExtractorResult]:
        """Yield one result per request, keyed by custom_id (order is arbitrary)."""
        for entry in self._client.messages.batches.results(batch_id):
            cid = _get(entry, "custom_id")
            res = _get(entry, "result")
            kind = _get(res, "type")
            if kind == "succeeded":
                yield result_from_message(cid, _get(res, "message"))
            elif kind == "errored":
                err = _get(res, "error")
                inner = _get(err, "error", err)
                yield ExtractorResult(cid, False, None, {
                    "type": "errored",
                    "error_type": _get(inner, "type"),
                    "message": _get(inner, "message"),
                })
            else:
                yield ExtractorResult(cid, False, None, {"type": kind or "unknown"})


__all__ = [
    "BATCH_MAX_BYTES",
    "BATCH_MAX_REQUESTS",
    "DEFAULT_MAX_REQUEST_BYTES",
    "DEFAULT_MAX_TOKENS",
    "EXTRACTOR_EFFORT",
    "EXTRACTOR_MODEL",
    "AnthropicExtractorClient",
    "ExtractorJob",
    "ExtractorResult",
    "build_params",
    "make_custom_id",
    "params_bytes",
    "result_from_message",
    "split_for_batches",
]
