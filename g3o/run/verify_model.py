"""Q4 (2026-05-09) — one-job Batch API submit to confirm a model id.

Used as a preflight before any large-scale Batch API submission. Issues a
single trivial job (``"Reply OK."``) and blocks until the batch reaches a
terminal state. Raises if the submission or polling fails.

This is the only place in the codebase that submits a live OpenAI call
deliberately for verification rather than for production data; gate
on ``OPENAI_API_KEY`` before invoking.
"""

from __future__ import annotations

import logging
import time

from g3o.common.batch_client import (
    DEFAULT_MODEL,
    BatchJob,
    fetch_results,
    poll_batch,
    submit_batch,
)

logger = logging.getLogger(__name__)


def verify_model(
    model: str = DEFAULT_MODEL,
    *,
    poll_interval: int = 30,
    max_wait: int = 1800,
) -> dict[str, object]:
    """Submit a 1-job batch to confirm ``model`` is accepted by the OpenAI Batch API.

    Returns a summary dict with the ``batch_id`` used, the requested ``model``,
    the terminal ``status`` string, and the number of results returned.
    Raises ``RuntimeError`` if the submission times out or ends non-completed.
    """
    job = BatchJob(
        custom_id="verify-model-001",
        messages=[
            {
                "role": "system",
                "content": "You are a model-id verifier. Reply with the exact word OK.",
            },
            {"role": "user", "content": "Reply OK."},
        ],
        prompt_cache_key="g3o.verify_model.v1",
    )
    handle = submit_batch([job], model=model)
    logger.info("verify_model submitted batch_id=%s for model=%s", handle.batch_id, model)
    started = time.monotonic()
    status = poll_batch(handle.batch_id)
    while not status.is_terminal:
        if time.monotonic() - started >= max_wait:
            raise RuntimeError(
                f"verify_model batch {handle.batch_id} not terminal within {max_wait}s"
            )
        time.sleep(poll_interval)
        status = poll_batch(handle.batch_id)
    if not status.is_completed:
        raise RuntimeError(
            f"verify_model batch {handle.batch_id} ended in non-completed state: "
            f"{status.status}"
        )
    results = list(fetch_results(handle.batch_id, status=status))
    return {
        "batch_id": handle.batch_id,
        "model": model,
        "status": status.status,
        "n_results": len(results),
        "first_content": (
            results[0].parsed_content if results and results[0].success else None
        ),
    }


__all__ = ["verify_model"]
