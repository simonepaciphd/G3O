"""Anthropic Messages client for the X35 entailment check (PI ruling 139 a).

PI ruling 139 a: the X35 binding is Claude Haiku 5.5 (``claude-haiku-5-5``), wired
behind the instrument's pinned ``x35_model`` field (``RuntimeSettings.x35_model``,
RC-D-033 C1 a). The model sent is always the one the caller passes (the pinned
field); this module names no model of its own.

Call contract: ``client(question, text) -> Entailment`` (``support_check.Entailment``),
one synchronous ``messages.create`` per (question, window). The question is sent
exactly as given (the signed ``support_check.entailment_question`` output); the text is
the RC-D-019 E3 window, sent whole (never truncated). :meth:`AnthropicX35Client.entail_with_usage`
also returns the response's own ``usage``, which the request journal stores per
request so the call can be priced (``RequestJournal.x35_usages``).

Two points are NOT ruled yet and are gated here by single constants:

- :data:`X35_PROBABILITY_SOURCE` (None = unruled). Claude returns no token
  probabilities, but the X35 check compares a chosen-answer probability with the 0.8
  bar (SPEC R-081, R-040). The one implemented candidate, ``"stated"``, asks the model
  for ``{"answer": "true"|"false", "probability": <0..1>}`` in its structured output
  and takes that number. While the constant is None, ``v27_entry.x35_entail_fn`` keeps
  returning the refusing ``support_check.run_entailment`` and no X35 call can be made.
- :data:`X35_SYSTEM_DRAFT` / :data:`X35_USER_TEMPLATE_DRAFT`: the instrument wording,
  DRAFT, not approved (needs PI approval).

Key material: the SDK client is injected (``v27_entry.anthropic_sdk_client``,
``max_retries=0``); this module never reads, logs or stores a key. ``anthropic`` is
never imported here.
"""

from __future__ import annotations

import json
import math
from typing import Any

from g3o.common.support_check import Entailment
from g3o.extract.anthropic_client import build_params, result_from_message

#: UNRULED (new PI question: the X35 probability source). None: no X35 call is wired
#: (``v27_entry.x35_entail_fn`` returns the refusing ``support_check.run_entailment``).
#: The one implemented candidate is ``"stated"``: the probability the model states in
#: its structured output. Ruling it is this one line.
X35_PROBABILITY_SOURCE: str | None = None
#: The probability sources this module implements.
X35_PROBABILITY_SOURCES: frozenset[str] = frozenset({"stated"})

#: Effort of an X35 request (mirrors the extractor's ``EXTRACTOR_EFFORT``).
X35_EFFORT = "medium"
#: Output budget of one X35 request (non-streaming; includes adaptive thinking).
X35_MAX_TOKENS = 4_000

#: DRAFT — not approved (needs PI approval). The system text of an X35 request.
X35_SYSTEM_DRAFT = (
    "You check whether a text supports a statement. Read the text, then answer the "
    "question about it. Answer \"true\" if the text supports it and \"false\" if it does "
    "not. Give \"probability\" as your probability, from 0 to 1, that your answer is correct."
)
#: DRAFT — not approved (needs PI approval). The user message of an X35 request; the
#: question is inserted exactly as given, the text whole.
X35_USER_TEMPLATE_DRAFT = "<text>\n{text}\n</text>\n\n{question}"

#: The structured output of an X35 request (``"stated"`` probability source).
X35_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "enum": ["true", "false"]},
        "probability": {"type": "number"},
    },
    "required": ["answer", "probability"],
    "additionalProperties": False,
}


class X35ResponseError(RuntimeError):
    """An X35 response that gives no usable answer (refusal, cut, empty or unparseable).

    ``usage`` is the response's own usage (it was billed), so the request journal can
    keep it on the ``x35_failed`` entry.
    """

    def __init__(self, message: str, *, usage: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.usage = usage


def stated_probability(value: Any) -> float | None:
    """The stated probability, or None when it is missing, not a number, not finite or outside 0..1.

    None makes the X35 check fail with ``ENTAILMENT_PROBABILITY_UNAVAILABLE``
    (``support_check._entailment_fails``); a bad number is never clipped or guessed.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    p = float(value)
    if not math.isfinite(p) or p < 0.0 or p > 1.0:
        return None
    return p


def parse_entailment(text: str, *, probability_source: str) -> Entailment:
    """An :class:`Entailment` from the structured output text; raises ``ValueError`` on no answer."""
    if probability_source not in X35_PROBABILITY_SOURCES:
        raise ValueError(f"X35 probability source {probability_source!r} is not implemented")
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"X35 output is not JSON: {exc.msg}") from None
    if not isinstance(doc, dict):
        raise ValueError("X35 output is not a JSON object")
    answer = doc.get("answer")
    if answer not in ("true", "false"):
        raise ValueError(f"X35 answer must be 'true' or 'false', got {answer!r}")
    return Entailment(answer, stated_probability(doc.get("probability")))


class AnthropicX35Client:
    """The X35 ``entail_fn`` over an injected ``anthropic.Anthropic`` client (sync Messages)."""

    def __init__(self, client: Any, *, model: str, probability_source: str,
                 effort: str = X35_EFFORT, max_tokens: int = X35_MAX_TOKENS) -> None:
        if client is None:
            raise ValueError("an SDK client must be injected (v27_entry.anthropic_sdk_client: max_retries=0)")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("x35 model must be explicitly supplied (the instrument's pinned x35_model)")
        if probability_source not in X35_PROBABILITY_SOURCES:
            raise ValueError(f"X35 probability source {probability_source!r} is not implemented")
        self._client = client
        self.model = model
        self.probability_source = probability_source
        self.effort = effort
        self.max_tokens = max_tokens

    def params(self, question: str, text: str) -> dict[str, Any]:
        """Messages API params for one (question, window); the question exactly as given, the text whole."""
        if not isinstance(question, str) or not question:
            raise ValueError("X35 question is required")
        if not isinstance(text, str) or not text:
            raise ValueError("X35 text is required")
        user = X35_USER_TEMPLATE_DRAFT.format(text=text, question=question)
        return build_params(system=X35_SYSTEM_DRAFT, user=user, output_schema=X35_OUTPUT_SCHEMA,
                            model=self.model, effort=self.effort, max_tokens=self.max_tokens)

    def entail_with_usage(self, question: str, text: str) -> tuple[Entailment, dict[str, Any] | None]:
        """One X35 call: the answer and the response's own ``usage`` (journaled per request)."""
        message = self._client.messages.create(**self.params(question, text))
        result = result_from_message("x35", message, request_id=getattr(message, "_request_id", None))
        if not result.success or result.text is None:
            kind = (result.error or {}).get("type")
            raise X35ResponseError(f"X35 response gave no answer ({kind})", usage=result.usage)
        try:
            answer = parse_entailment(result.text, probability_source=self.probability_source)
        except ValueError as exc:
            raise X35ResponseError(str(exc), usage=result.usage) from None
        return answer, result.usage

    def __call__(self, question: str, text: str) -> Entailment:
        return self.entail_with_usage(question, text)[0]

    def __repr__(self) -> str:  # never render key material
        return f"AnthropicX35Client(model={self.model!r}, probability_source={self.probability_source!r})"


__all__ = [
    "X35_EFFORT",
    "X35_MAX_TOKENS",
    "X35_OUTPUT_SCHEMA",
    "X35_PROBABILITY_SOURCE",
    "X35_PROBABILITY_SOURCES",
    "X35_SYSTEM_DRAFT",
    "X35_USER_TEMPLATE_DRAFT",
    "AnthropicX35Client",
    "X35ResponseError",
    "parse_entailment",
    "stated_probability",
]
