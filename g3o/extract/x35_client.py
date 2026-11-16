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

Two gates, each a single constant; ``v27_entry.x35_entail_fn`` returns the refusing
``support_check.run_entailment`` (no X35 call) unless both are open:

- :data:`X35_PROBABILITY_SOURCE`: RULED ``"stated"`` (PI ruling Q159 a, 2026-11-16).
  Claude returns no token probabilities, so the X35 request's structured output is
  ``{"answer": "true"|"false", "probability": <0..1>}`` and the 0.8 bar of SPEC R-081 /
  R-040 applies to that stated number; one call per (code, quote).
- :data:`X35_SYSTEM_DRAFT` / :data:`X35_USER_TEMPLATE_DRAFT`: the instrument wording,
  APPROVED (PI Q160, 2026-11-16; the names are kept). Pinned by SHA256 (review O2 M2,
  as the Stage 6 quote step pins its approved wording) in
  :data:`X35_INSTRUCTION_APPROVED_SHA256`: a changed wording no longer matches the pin,
  and X35 is refused at entry again until the PI approves the new one.

Key material: the SDK client is injected (``v27_entry.anthropic_sdk_client``,
``max_retries=0``); this module never reads, logs or stores a key. ``anthropic`` is
never imported here.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from g3o.common.support_check import Entailment
from g3o.extract.anthropic_client import build_params, result_from_message

#: RULED (PI ruling Q159 a, 2026-11-16): ``"stated"``, the probability the model states in
#: its structured output (:data:`X35_OUTPUT_SCHEMA`); R-081's 0.8 bar applies to it. None
#: would wire no X35 call (``v27_entry.x35_entail_fn`` returns the refusing stub).
X35_PROBABILITY_SOURCE: str | None = "stated"
#: The probability sources this module implements.
X35_PROBABILITY_SOURCES: frozenset[str] = frozenset({"stated"})

#: Effort of an X35 request (mirrors the extractor's ``EXTRACTOR_EFFORT``).
X35_EFFORT = "medium"
#: Output budget of one X35 request (non-streaming; includes adaptive thinking).
X35_MAX_TOKENS = 4_000

#: APPROVED (PI Q160, 2026-11-16; name kept). The system text of an X35 request.
X35_SYSTEM_DRAFT = (
    "You check whether a text supports a statement. Read the text, then answer the "
    "question about it. Answer \"true\" if the text supports it and \"false\" if it does "
    "not. Give \"probability\" as your probability, from 0 to 1, that your answer is correct."
)
#: APPROVED (PI Q160, 2026-11-16; name kept). The user message of an X35 request; the
#: question is inserted exactly as given, the text whole.
X35_USER_TEMPLATE_DRAFT = "<text>\n{text}\n</text>\n\n{question}"

#: RULED (PI Q160, 2026-11-16: "I accept x35 wordings"): the SHA256 of the approved X35 wording
#: (:func:`x35_instruction_sha256` of :data:`X35_SYSTEM_DRAFT` / :data:`X35_USER_TEMPLATE_DRAFT`;
#: review O2 M2). Any change to that wording moves its hash off this pin, and
#: ``v27_entry.x35_entail_fn`` then returns the refusing stub again until a new wording is approved.
X35_INSTRUCTION_APPROVED_SHA256: str | None = "6f048d6018bba9cb8ebc9027a45ece29a80b8b9de5ae19173d3f67580900861c"


def x35_instruction_sha256(system: str = X35_SYSTEM_DRAFT, user_template: str = X35_USER_TEMPLATE_DRAFT) -> str:
    """SHA256 (hex) of the X35 wording: ``system + "\\0" + user_template``, UTF-8 encoded."""
    return hashlib.sha256((system + "\0" + user_template).encode("utf-8")).hexdigest()


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

    ``usage`` is the response's own usage (it was billed). PI ruling Q169 b: the request
    journal (``RequestJournal`` X35 seam) records it as an answer with no probability
    (``support_check.X35_NON_ANSWER``) on a replayed ``x35`` entry carrying that usage, so
    only that one check fails and a resume replays it instead of asking (and billing) again.
    Raised to a caller that calls this client without the journal.
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
    "X35_INSTRUCTION_APPROVED_SHA256",
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
    "x35_instruction_sha256",
]
