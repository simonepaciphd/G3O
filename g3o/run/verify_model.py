"""Q4 (2026-05-09) — one-job Batch API submit to confirm a model id.

Used as a preflight before any large-scale Batch API submission. Issues a
single trivial job (``"Reply OK."``) and blocks until the batch reaches a
terminal state. Raises if the submission or polling fails.

This is the only place in the codebase that submits a live OpenAI call
deliberately for verification rather than for production data; gate on a
resolvable OpenAI key before invoking.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from g3o.common.batch_client import (
    DEFAULT_MODEL,
    BatchJob,
    client_from_credentials,
    fetch_results,
    poll_batch,
    submit_batch,
)
from g3o.common.credentials import ResolvedCredentials

logger = logging.getLogger(__name__)


def verify_model(
    model: str = DEFAULT_MODEL,
    *,
    poll_interval: int = 30,
    max_wait: int = 1800,
    client: Any | None = None,
    credentials: ResolvedCredentials | None = None,
) -> dict[str, object]:
    """Submit a 1-job batch to confirm ``model`` is accepted by the OpenAI Batch API.

    Returns a summary dict with the ``batch_id`` used, the requested ``model``,
    the terminal ``status`` string, and the number of results returned.
    Raises ``RuntimeError`` if the submission times out or ends non-completed.

    ``credentials`` (Run API spec §3.2) is the key this verification spends on.
    Until 2026-08-11 this function took neither a client nor credentials, so the
    one deliberately spend-bearing check in the preflight always used the ambient
    environment — including when its caller had been handed an explicit key and had
    just reported *that* key as ready. An operator running with in-memory keys (the
    droplet) would have had a readiness report about one key and a live submit on
    another. ``client`` wins when given (test injection); with neither, behaviour is
    unchanged and each call resolves from the environment as before.
    """
    cli = client
    if cli is None and credentials is not None:
        cli = client_from_credentials(credentials)
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
    handle = submit_batch([job], model=model, client=cli)
    logger.info("verify_model submitted batch_id=%s for model=%s", handle.batch_id, model)
    started = time.monotonic()
    status = poll_batch(handle.batch_id, client=cli)
    while not status.is_terminal:
        if time.monotonic() - started >= max_wait:
            raise RuntimeError(
                f"verify_model batch {handle.batch_id} not terminal within {max_wait}s"
            )
        time.sleep(poll_interval)
        status = poll_batch(handle.batch_id, client=cli)
    if not status.is_completed:
        raise RuntimeError(
            f"verify_model batch {handle.batch_id} ended in non-completed state: "
            f"{status.status}"
        )
    results = list(fetch_results(handle.batch_id, status=status, client=cli))
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
