"""Stage 6 quote step (T-026; RC-D-028 1 a): builds the ``quote_fn`` that ``stage6_v27`` injects.

For each Stage 6 request part (a relation answer, or a pooled answer), the C-001
extractor (Claude Haiku 5.5, :mod:`g3o.extract.anthropic_client`) copies verbatim
from the input quotes shown in that part and names the one it copied from; the
X35 entailment check then runs on the copy (R-040; window RC-D-019 E3, on the
input quote's stored page part). The answer goes back to
:func:`g3o.validate.stage6_v27._support`, which runs the T-024 check.

Two seams, both injected; this module makes no call of its own:

- ``extract_fn(job) -> ExtractorResult`` - the extractor call. Tests pass fakes.
- ``entail_fn(question, text) -> Entailment`` - the X35 call (the jev binding is
  T-030/T-035; :func:`g3o.common.support_check.run_entailment` still refuses).

The instruction text is substantive and owed to the PI (RC-D-028 1 a: "wording
to be approved"). It sits in ONE constant, :data:`STAGE6_QUOTE_INSTRUCTION`,
whose first line is :data:`STAGE6_QUOTE_DRAFT_MARKER`. While the marker is in
the instruction, :func:`anthropic_quote_fn` (the paid path) and
:func:`make_quote_fn` refuse with :class:`Stage6QuoteNotApproved` before any
client exists; only ``allow_draft=True`` (fakes, in tests) gets past it.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from g3o.codebook.loader import Codebook, load_codebook
from g3o.common.support_check import (
    QUOTE_MAX_CHARS,
    Entailment,
    SupportRules,
    default_rules,
    entailment_question,
    entailment_window,
    match_quote,
)
from g3o.extract.anthropic_client import ExtractorJob, ExtractorResult, build_params, make_custom_id
from g3o.validate.stage6_v27 import (
    InputQuote,
    QuoteFn,
    Stage6Quote,
    Stage6QuoteNotApproved,
    Stage6QuoteRequest,
)

STAGE6_QUOTE_DRAFT_MARKER = "DRAFT — NOT PI-APPROVED"

#: The Stage 6 quote-step instruction (RC-D-028 1 a). DRAFT — NOT PI-APPROVED: the PI
#: approves or rewrites this text; remove the marker line only on that approval.
STAGE6_QUOTE_INSTRUCTION = STAGE6_QUOTE_DRAFT_MARKER + """

# Stage 6 supporting text

You are the copying step of the G3O coding pipeline. Another model has already read quotes about an institution's activities, gathered from one or more pages, and answered a coding question about them. Your job is to copy exact words from those quotes so that the answer can be checked. You do not answer the coding question yourself, and nothing you write is taken as an answer.

## How to copy

- Copy text exactly as it appears in one of the quotes you are given: same language, same spelling, same punctuation. Do not translate, summarise, correct or reword.
- Copy from one quote only, and give its `quote_id`. Do not join words from two quotes.
- You may leave out words inside a passage to keep it short, but every word you write must appear in that quote.
- Keep the copy to at most {{QUOTE_MAX_CHARS}} characters. Copy the words that matter most; do not pad it to reach the limit.
- If no quote bears on the task, give `null` rather than a guess.

## The task

The message lists the quotes under `QUOTES`, each with its `quote_id`, and one task under `TASK`. The task gives a coding question and the `answer` the coder gave to it. When the quotes come from two records, each quote names its record (`first` or `second`), and the question is about how the activity in the first record relates to the activity in the second. Copy the passage that supports the answer: the shortest passage that contains what the question asks about. The answer is shown so that you can find its support; do not judge or change it, and do not repeat it in your output. If no quote supports the answer, return `quote_id` and `quote` as `null`.

## Output

Return only the JSON object the output format describes."""

PROMPT_VERSION = "stage6_quote_v27-draft"

ExtractFn = Callable[[ExtractorJob], ExtractorResult]
EntailFn = Callable[[str, str], Entailment]

_KEYS = {"quote_id", "quote"}


class Stage6QuoteFailed(RuntimeError):
    """One quote request failed (no result, refusal, malformed answer); that answer is held."""


def require_approved(instruction: str) -> None:
    if STAGE6_QUOTE_DRAFT_MARKER in instruction:
        raise Stage6QuoteNotApproved(
            "Stage 6 quote-step instruction is marked 'DRAFT — NOT PI-APPROVED' (RC-D-028 1 a): "
            "no extractor call is made until the PI approves the wording")


def build_system_prompt(instruction: str = STAGE6_QUOTE_INSTRUCTION, cb: Codebook | None = None) -> str:
    """Shared system prompt + the Stage 6 instruction, as pass 2 composes its prompt."""
    cb = cb or load_codebook()
    shared = cb.shared_slot("system_prompt")
    if shared is None:
        raise ValueError("codebook has no shared system prompt")
    body = instruction.replace("{{QUOTE_MAX_CHARS}}", str(QUOTE_MAX_CHARS))
    if "{{" in body:
        raise ValueError("unfilled placeholder in the Stage 6 quote instruction")
    return f"{shared.text}\n\n---\n\n{body}"


def output_schema() -> dict[str, Any]:
    """The extractor's answer: which quote it copied from and the copy. No code field (C-001)."""
    nullable = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {"type": "object", "properties": {"quote_id": nullable, "quote": nullable},
            "required": ["quote_id", "quote"], "additionalProperties": False}


def quote_ids(req: Stage6QuoteRequest) -> dict[str, InputQuote]:
    """``Q1``, ``Q2`` ... in the order the request part showed the candidates."""
    return {f"Q{n}": c for n, c in enumerate(req.candidates, start=1)}


def build_user_message(req: Stage6QuoteRequest, ids: Mapping[str, InputQuote]) -> str:
    rows = []
    for qid, c in ids.items():
        row: dict[str, Any] = {"quote_id": qid}
        if req.kind == "relation":
            row["record"] = "first" if c.observation_id == req.first_observation_id else "second"
        row["text"] = c.quote_text
        rows.append(row)
    task = {"question": req.question_text, "answer": req.value}
    return "\n".join(["QUOTES:", json.dumps(rows, ensure_ascii=False, indent=1), "",
                      "TASK:", json.dumps(task, ensure_ascii=False, indent=1)])


def build_job(req: Stage6QuoteRequest, *, system: str) -> ExtractorJob:
    if not req.question_text:
        raise ValueError(f"{req.question_id}: the quote task needs the question as asked")
    if not req.candidates:
        raise ValueError("no input quotes to copy from")
    ids = quote_ids(req)
    params = build_params(system=system, user=build_user_message(req, ids), output_schema=output_schema())
    return ExtractorJob(
        custom_id=make_custom_id(req.kind, req.key, req.part_id, req.question_id, req.value, prefix="x27q6"),
        params=params,
        metadata={"stage": "6_quote_v27", "kind": req.kind, "key": req.key, "part_id": req.part_id,
                  "question_id": req.question_id, "prompt_version": PROMPT_VERSION},
    )


def parse_answer(result: ExtractorResult, ids: Mapping[str, InputQuote]) -> tuple[str | None, InputQuote | None]:
    """(copy, the input quote it names). A copy naming no shown quote keeps ``None`` as its
    source, so the T-024 check counts it as no supporting text (R-044)."""
    if not result.success or not result.text:
        raise Stage6QuoteFailed(f"quote request {result.custom_id!r} failed: {result.error}")
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise Stage6QuoteFailed(f"quote request {result.custom_id!r}: answer is not JSON") from exc
    if not isinstance(payload, dict):
        raise Stage6QuoteFailed(f"quote request {result.custom_id!r}: answer is not a JSON object")
    if set(payload) != _KEYS:
        raise Stage6QuoteFailed(f"quote request {result.custom_id!r}: answer keys {sorted(payload)!r}")
    quote, qid = payload["quote"], payload["quote_id"]
    if quote is not None and not isinstance(quote, str) or qid is not None and not isinstance(qid, str):
        raise Stage6QuoteFailed(f"quote request {result.custom_id!r}: non-string answer")
    if quote is None or not quote.strip():
        return None, None
    return quote, ids.get(qid) if qid is not None else None


def _source_text(item: Mapping[str, Any], source: InputQuote) -> str | None:
    """The stored text the copy is matched on: the input quote's page part, or its chrome."""
    if source.quote_chunk_id == source.producing_chunk_id:
        return source.sources.parts.get(source.quote_chunk_id)
    if (source.quote_chunk_id == source.sources.chrome_id and item.get("input_text") == "main_plus_chrome"):
        return source.sources.chrome_text
    return None


def entailment_for(req: Stage6QuoteRequest, quote: str, source: InputQuote, entail_fn: EntailFn,
                   rules: SupportRules | None = None) -> tuple[Entailment | None, dict[str, Any]]:
    """X35 on the copy, only where T-024 needs it: a labelled item whose copy matches the
    stored text (R-042). Window: the copy plus 200 characters each side (RC-D-019 E3)."""
    rules = rules or default_rules()
    if req.item_id not in rules.entailment_labels:
        return None, {}
    text = _source_text(rules.items[req.item_id], source)
    if text is None or not match_quote(quote, text).matched:
        return None, {}
    question = entailment_question(req.item_id, req.value, part=req.part, activity_name=req.activity_name,
                                   rules=rules)
    window, located = entailment_window(quote, text)
    return entail_fn(question, window), {"x35_question": question, "x35_window_located": located}


@dataclass(frozen=True)
class Stage6QuoteStep:
    """The Stage 6 ``quote_fn``: extractor copy, then X35, through two replaceable seams.

    :meth:`with_seams` lets the T-030 request journal record each paid call on its
    own (an extractor answer survives an X35 failure); ``configure_job`` lets the
    bound runtime set the extractor model/effort/max tokens and ``setup_pointer``.
    """

    extract_fn: ExtractFn
    entail_fn: EntailFn
    system: str
    rules: SupportRules | None = None
    configure_job: Callable[[ExtractorJob], ExtractorJob] | None = None
    prompt_version: str = PROMPT_VERSION

    def with_seams(self, wrap_extract: Callable[[ExtractFn], ExtractFn],
                   wrap_entail: Callable[[EntailFn], EntailFn]) -> Stage6QuoteStep:
        return replace(self, extract_fn=wrap_extract(self.extract_fn), entail_fn=wrap_entail(self.entail_fn))

    def __call__(self, req: Stage6QuoteRequest) -> Stage6Quote:
        ids = quote_ids(req)
        job = build_job(req, system=self.system)
        if self.configure_job is not None:
            job = self.configure_job(job)
        result = self.extract_fn(job)
        quote, source = parse_answer(result, ids)
        prov: dict[str, Any] = {"custom_id": job.custom_id, "prompt_version": self.prompt_version,
                                "response_model": result.response_model, "message_id": result.message_id,
                                "request_id": result.request_id, "usage": result.usage}
        if quote is None:
            return Stage6Quote(None, None, None, prov)
        if source is None:
            return Stage6Quote(quote, None, None, prov)
        ent, x35 = entailment_for(req, quote, source, self.entail_fn, self.rules)
        return Stage6Quote(quote, source.support_id, ent, {**prov, **x35})


def make_quote_fn(extract_fn: ExtractFn, entail_fn: EntailFn, *, instruction: str = STAGE6_QUOTE_INSTRUCTION,
                  allow_draft: bool = False, cb: Codebook | None = None,
                  rules: SupportRules | None = None,
                  configure_job: Callable[[ExtractorJob], ExtractorJob] | None = None) -> Stage6QuoteStep:
    """The Stage 6 ``quote_fn``. Refuses a DRAFT instruction unless ``allow_draft`` (fakes only)."""
    if not allow_draft:
        require_approved(instruction)
    return Stage6QuoteStep(extract_fn, entail_fn, build_system_prompt(instruction, cb), rules, configure_job)


def anthropic_quote_fn(entail_fn: EntailFn, *, client: Any | None = None,
                       instruction: str = STAGE6_QUOTE_INSTRUCTION) -> QuoteFn:
    """The paid path: the extractor over the Anthropic Messages API (sync). Refuses while the
    instruction carries the DRAFT marker, before any client is created."""
    require_approved(instruction)
    from g3o.extract.anthropic_client import AnthropicExtractorClient

    return make_quote_fn(AnthropicExtractorClient(client).create, entail_fn, instruction=instruction)


__all__ = [
    "PROMPT_VERSION", "STAGE6_QUOTE_DRAFT_MARKER", "STAGE6_QUOTE_INSTRUCTION", "EntailFn", "ExtractFn",
    "Stage6QuoteFailed", "Stage6QuoteNotApproved", "Stage6QuoteStep", "anthropic_quote_fn", "build_job", "build_system_prompt",
    "build_user_message", "entailment_for", "make_quote_fn", "output_schema", "parse_answer", "quote_ids",
    "require_approved",
]
