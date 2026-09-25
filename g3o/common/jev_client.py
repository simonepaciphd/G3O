"""TypeSafe jev decision-model client for the G3O pipeline.

Single-owner client for the TypeSafe System One API, used by the decision-shaped
LLM stages (Stage 2 classify_official_site, Stage 3 classify_url_triage, and
eventually Stage 6 validate). Forks of this client are not allowed: every jev
stage submits through :func:`ask`.

jev is a decision model, not a text generator: it takes a ``state`` plus typed
questions (Choice, Score, Noul) and returns typed answers with probability
distributions and confidence. See ``jev-integration-plan.md`` for the full
design.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import typesafe_sdk as ts

from g3o.common import config
from g3o.common.credentials import ResolvedCredentials

logger = logging.getLogger(__name__)

# Default model id for jev stages. Pinned to a versioned id (not the
# ``jev-latest`` alias) so thresholds tuned against a version stay reproducible
# (T1 reproducibility floor). Sourced from ``config.TYPESAFE_MODEL`` so a
# single ``TYPESAFE_MODEL`` env var overrides the pipeline-wide default.
DEFAULT_JEV_MODEL: str = config.TYPESAFE_MODEL

# Documented TypeSafe limits (docs.typesafe.ai/models, verified 2026-09-20).
# 64k tokens per request (32k state + longest question); 250k tokens/s;
# 1,200 requests/min — "adjusting dynamically", so 429-handling is mandatory.
JEV_MAX_TOKENS_PER_REQUEST = 64_000
JEV_RATE_LIMIT_RPM = 1_200

# Default retry policy. The SDK's RetryPolicy handles 429/retry-after by
# default; these parameters set the envelope.
DEFAULT_JEV_MAX_RETRIES = 5
DEFAULT_JEV_BACKOFF_INITIAL = 1.0
DEFAULT_JEV_BACKOFF_MAX = 30.0


@dataclass(frozen=True)
class JevAnswer:
    """One typed answer from a jev request.

    Exactly one of ``choice``, ``noul``, or ``score`` is set; the others are
    ``None``. ``confidence`` is set for Choice and Score answers (derived from
    the probability distribution); Noul answers do not carry confidence.
    """

    question_id: str
    type: str  # "choice" | "noul" | "score"
    choice: str | None = None
    noul: float | None = None
    score: float | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | dict[int, float] | None = None


@dataclass(frozen=True)
class JevResult:
    """The outcome of one jev request.

    ``answers`` is keyed by question id. ``response_model`` is the versioned
    model id the server answered with (the provenance anchor for T1).
    ``request_id`` is the server-assigned request id.
    """

    answers: dict[str, JevAnswer]
    response_model: str
    request_id: str | None
    input_tokens: int
    output_tokens: int


def _parse_answer(question_id: str, answer: Any) -> JevAnswer:
    """Parse one SDK answer into a :class:`JevAnswer`."""
    if isinstance(answer, ts.ChoiceAnswer):
        return JevAnswer(
            question_id=question_id,
            type="choice",
            choice=answer.choice,
            confidence=answer.confidence,
            probabilities=dict(answer.probabilities),
        )
    if isinstance(answer, ts.NoulAnswer):
        return JevAnswer(
            question_id=question_id,
            type="noul",
            noul=answer.noul,
        )
    if isinstance(answer, ts.ScoreAnswer):
        return JevAnswer(
            question_id=question_id,
            type="score",
            score=answer.score,
            confidence=answer.confidence,
            probabilities=dict(answer.probabilities),
        )
    raise TypeError(f"unknown jev answer type: {type(answer)}")


def client_from_credentials(
    credentials: ResolvedCredentials,
    *,
    model: str | None = None,
    max_retries: int = DEFAULT_JEV_MAX_RETRIES,
) -> ts.TypeSafeClient:
    """Build a :class:`typesafe_sdk.TypeSafeClient` from resolved credentials.

    ``credentials.typesafe_api_key`` is the Bearer token. Raises
    :class:`RuntimeError` if the key is unset — a jev stage without a key is
    a configuration error, not a missing-feature fallback.
    """
    if not credentials.typesafe_api_key:
        raise RuntimeError(
            "TypeSafe API key is not set. Set TYPESAFE_API_KEY in the "
            "environment or pass it via Credentials(typesafe_api_key=...)."
        )
    retry = ts.RetryPolicy(
        max_retries=max_retries,
        backoff_initial=DEFAULT_JEV_BACKOFF_INITIAL,
        backoff_max=DEFAULT_JEV_BACKOFF_MAX,
    )
    return ts.TypeSafeClient(
        api_key=credentials.typesafe_api_key,
        model=model or DEFAULT_JEV_MODEL,
        retry=retry,
    )


def ask(
    state: Any,
    questions: Mapping[str, ts.Choice | ts.Noul | ts.Score],
    *,
    client: ts.TypeSafeClient,
    model: str | None = None,
) -> JevResult:
    """Submit one jev request and return a :class:`JevResult`.

    ``state`` is the decision context (string or JSON-serialisable); ``questions``
    is a mapping of question id to typed question. All questions are evaluated
    in parallel against the same state by the API.

    ``model`` overrides the client's default for this request only.

    Raises :class:`typesafe_sdk.TypeSafeError` on API failure; the client's
    retry policy handles transient errors (429, timeouts) automatically.
    """
    response = client.system_one(
        state=state,
        questions=dict(questions),
        model=model,
    )
    answers = {
        qid: _parse_answer(qid, ans) for qid, ans in response.answers.items()
    }
    return JevResult(
        answers=answers,
        response_model=response.model,
        request_id=response.request_id,
        input_tokens=response.usage.input_tokens or 0,
        output_tokens=response.usage.output_tokens or 0,
    )


def serialize_state(state: Any) -> str:
    """Serialize a state to canonical JSON for hashing/reproducibility.

    Used by the reproducibility goldens (§6 of jev-integration-plan.md) to
    hash the deterministic jev request payload.
    """
    return json.dumps(state, sort_keys=True, ensure_ascii=False)


__all__ = [
    "DEFAULT_JEV_MAX_RETRIES",
    "DEFAULT_JEV_BACKOFF_INITIAL",
    "DEFAULT_JEV_BACKOFF_MAX",
    "DEFAULT_JEV_MODEL",
    "JEV_MAX_TOKENS_PER_REQUEST",
    "JEV_RATE_LIMIT_RPM",
    "JevAnswer",
    "JevResult",
    "ask",
    "client_from_credentials",
    "serialize_state",
]
