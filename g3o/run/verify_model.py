"""Q4 (2026-05-09) — one-job submit to confirm a model id.

Used as a preflight before any large-scale submission. Routes to the right
API based on the model id:

- OpenAI models (``gpt-5-nano``, etc.): one Batch API job (``"Reply OK."``),
  blocks until the batch reaches a terminal state.
- TypeSafe jev models (``jev-1.13.0``, etc.): one Noul probe through the jev
  client (typed, no free text), reporting the answering ``response.model``.

Raises if the submission or polling fails.

This is the only place in the codebase that submits a live API call
deliberately for verification rather than for production data; gate on a
resolvable API key before invoking.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import typesafe_sdk as ts

from g3o.common.batch_client import (
    DEFAULT_MODEL,
    BatchJob,
    client_from_credentials,
    fetch_results,
    poll_batch,
    submit_batch,
)
from g3o.common.credentials import ResolvedCredentials
from g3o.common.jev_client import (
    DEFAULT_JEV_MODEL,
    client_from_credentials as jev_client_from_credentials,
)

logger = logging.getLogger(__name__)


def _is_jev_model(model: str) -> bool:
    """True if ``model`` is a TypeSafe jev model id."""
    return model.startswith("jev-")


def _verify_openai(
    model: str,
    *,
    poll_interval: int,
    max_wait: int,
    client: Any | None,
    credentials: ResolvedCredentials | None,
) -> dict[str, object]:
    """OpenAI Batch API verification: one trivial job, poll to terminal."""
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
        "response_model": results[0].response_model if results else None,
        "provider": "openai",
    }


def _verify_jev(
    model: str,
    *,
    client: Any | None,
    credentials: ResolvedCredentials | None,
) -> dict[str, object]:
    """TypeSafe jev verification: one Noul probe, typed response.

    Jev is a decision model, not a text generator: it takes a state plus typed
    questions and returns typed answers. The probe asks one Noul question
    ("Is 1+1=2?") with a trivial state; the answer's ``noul`` should be close
    to 1.0. The key verification is that the request succeeds and the
    ``response.model`` matches the requested model.
    """
    cli = client
    if cli is None and credentials is not None:
        cli = jev_client_from_credentials(credentials, model=model)
    if cli is None:
        raise RuntimeError(
            "jev verify_model requires either a client or credentials"
        )
    # One Noul question: "Is 1+1=2?" with a trivial state.
    state = {"question": "Is 1+1=2?"}
    questions = {
        "is_correct": ts.Noul(
            instructions="Is the statement in the state correct?",
            criteria=ts.NoulCriteria(
                true="The statement is mathematically correct",
                false="The statement is mathematically incorrect",
            ),
        ),
    }
    response = cli.system_one(state=state, questions=questions, model=model)
    answer = response.answers.get("is_correct")
    return {
        "model": model,
        "status": "completed",
        "n_results": 1,
        "response_model": response.model,
        "request_id": response.request_id,
        "noul": answer.noul if answer else None,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "provider": "typesafe",
    }


def verify_model(
    model: str = DEFAULT_MODEL,
    *,
    poll_interval: int = 30,
    max_wait: int = 1800,
    client: Any | None = None,
    credentials: ResolvedCredentials | None = None,
) -> dict[str, object]:
    """Submit a verification probe to confirm ``model`` is accepted by the API.

    Routes to the right API based on the model id:
    - OpenAI models: one Batch API job, poll to terminal.
    - TypeSafe jev models: one Noul probe, typed response.

    Returns a summary dict with the requested ``model``, the terminal
    ``status``, the ``response_model`` the server answered with, and the
    ``provider`` (``"openai"`` or ``"typesafe"``). Raises ``RuntimeError`` if
    the submission times out or ends non-completed.

    ``credentials`` (Run API spec §3.2) is the key this verification spends on.
    ``client`` wins when given (test injection); with neither, behaviour is
    unchanged and each call resolves from the environment as before.
    """
    if _is_jev_model(model):
        return _verify_jev(model, client=client, credentials=credentials)
    return _verify_openai(
        model,
        poll_interval=poll_interval,
        max_wait=max_wait,
        client=client,
        credentials=credentials,
    )


__all__ = ["verify_model"]
