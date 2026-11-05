"""v2.7 pass-2 supporting-text call (T-032).

After jev pass 2 (T-023), one extractor request per page covering all its
activities (DP-009, PI P6 a) asks for:

1. **Quotes** for every positive / substantive activity-level code (R-040,
   R-041; Q-010 a), one task per (activity, item, part, answer), each from the
   part that produced the code (R-044, PF-001). As in pass 1, the task shows
   the item's signed question and the answer jev chose (RC-D-017 "6"; reverses
   r2#18). The answer is input only (C-001).
2. **The two CX-61-gated free-text fields** moved here from pass 1 (RC-D-017,
   PI 2026-11-04 "5 a"): ``reported_outcomes`` and ``reported_incidents``,
   asked for an activity only when its gate item (``outcome_kind`` /
   ``incident_kind``) has a value in the codebook gate list (r2#9), and only
   from the parts that gave that value. The task says that the gate is open,
   not what the gate's answer was (r2#18 gate clause).

Every quote and supporting text is to be at most ``QUOTE_MAX_CHARS`` (200)
characters (RC-D-017 "3", "5a"); a longer one is kept whole and flagged
``quote_over_cap`` ("2 whole").

The activity passages reach the extractor as character spans only (DEC-010 a):
the page text is sent with ``[[A1]]`` / ``[[/A1]]`` marks at the span offsets
(full-page offsets, DP-008). The marks are not page text; the parser removes
any the extractor copies and flags the quote ``marks_removed``.

The T-023 activity record is not built yet; :class:`Pass2Page` is the mocked
shape this module needs (card T-032 Inputs). The extractor client and the
generated prompt sections are T-022's, reused read-only.

Prompt wording (``prompts/pass2_support_v27.md``) is a DRAFT: the PI approves
it in the single wording packet before the T-030 merge (RC-D-014 S3 b).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from g3o.codebook.loader import Codebook, load_codebook
from g3o.extract.anthropic_client import (
    ExtractorJob,
    ExtractorResult,
    build_params,
    make_custom_id,
)
from g3o.extract.parser_v27 import ExtractContractError, _check_keys, _flags, _text_or_none
from g3o.extract.request_v27 import (
    DEFERRED_FIELDS,
    QUOTE_MAX_CHARS,
    Pass1Page,
    _generated_sections,
    field_name,
)

PROMPT_VERSION = "pass2_support_v27-draft-1"
PASS2_PROMPT_PATH = Path(__file__).parent / "prompts" / "pass2_support_v27.md"

#: Flag on a quote from which activity marks were removed.
MARKS_REMOVED_FLAG = "marks_removed"
_MARK_RE = re.compile(r"\[\[/?A\d+\]\]")


# ---------------------------------------------------------------------------
# Codebook-derived rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pass2Rules:
    support_items: dict[str, dict[str, Any]]  # pass-2 classifier items needing support
    no_support_values: frozenset[str]
    temporary_answer: str
    questions: dict[str, str]
    #: gated quote-step field -> (gate item, values that open it)
    gated_fields: dict[str, tuple[str, frozenset[str]]]

    def needs_quote(self, value: str) -> bool:
        return value not in self.no_support_values and value != self.temporary_answer


def rules_from_codebook(cb: Codebook) -> Pass2Rules:
    items = cb.build_items()
    support = {
        k: v for k, v in items.items()
        if v.get("pass") == 2 and v.get("coder") == "classifier" and v.get("support_required") is True
    }
    status = cb.vocabularies["support_status"]
    no_support = frozenset(k for k in status["status_by_answer"] if re.fullmatch(r"[A-Za-z_]+", k))
    questions = {}
    for k in support:
        slot = cb.instruction(k)
        if slot is None:
            raise ValueError(f"pass-2 item {k} has no question text")
        questions[k] = slot.text
    gated: dict[str, tuple[str, frozenset[str]]] = {}
    for k in DEFERRED_FIELDS:
        gate = items[k].get("gate")
        if not (isinstance(gate, dict) and isinstance(gate.get("values"), list)):
            raise ValueError(f"{k} has no gate value list in the codebook")
        if gate["item"] not in support:
            raise ValueError(f"{k}: gate item {gate['item']} is not a pass-2 classifier item")
        gated[k] = (gate["item"], frozenset(gate["values"]))
    temp = cb.data["shared"]["part_prompt"]["temporary_answer"]["label"]["text"]
    return Pass2Rules(support, no_support, temp, questions, gated)


@lru_cache(maxsize=1)
def default_rules() -> Pass2Rules:
    return rules_from_codebook(load_codebook())


# ---------------------------------------------------------------------------
# Inputs (mocked T-023 activity record shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityCode:
    """One pass-2 answer for one activity from one part (one per selected value)."""

    item_id: str
    chunk_id: str
    value: str


@dataclass(frozen=True)
class Pass2Activity:
    activity_id: str
    start: int  # full-page offsets (DP-008)
    end: int
    codes: tuple[ActivityCode, ...]


@dataclass(frozen=True)
class Pass2Page:
    page: Pass1Page  # page text, parts, institution (T-021 / T-022 inputs)
    activities: tuple[Pass2Activity, ...]

    def __post_init__(self) -> None:
        ids = [a.activity_id for a in self.activities]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate activity_id")
        parts = {c.chunk_id for c in self.page.chunks}
        n = len(self.page.text)
        for a in self.activities:
            if not (0 <= a.start < a.end <= n):
                raise ValueError(f"activity {a.activity_id}: span {a.start}..{a.end} is not on the page")
            for code in a.codes:
                if code.chunk_id not in parts:
                    raise ValueError(f"activity {a.activity_id}: unknown part {code.chunk_id}")

    @property
    def page_id(self) -> str:
        return self.page.page_id


# ---------------------------------------------------------------------------
# Tasks and selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityQuoteTask:
    task_id: str
    activity_id: str
    label: str  # A1, A2, ... as marked in the message
    item_id: str
    chunk_id: str
    question: str
    answer: str  # jev's chosen answer (input only; RC-D-017)


@dataclass(frozen=True)
class ActivityFieldTask:
    task_id: str
    activity_id: str
    label: str
    item_id: str
    chunk_ids: tuple[str, ...]  # the parts that opened the gate


@dataclass(frozen=True)
class Pass2Plan:
    page_id: str
    labels: dict[str, str]  # activity_id -> label
    quote_tasks: tuple[ActivityQuoteTask, ...] = ()
    field_tasks: tuple[ActivityFieldTask, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def needs_request(self) -> bool:
        return bool(self.quote_tasks) or bool(self.field_tasks)


def _check_value(item: dict[str, Any], item_id: str, value: str, rules: Pass2Rules) -> None:
    if value in rules.no_support_values or value == rules.temporary_answer:
        return
    values = item.get("values")
    if isinstance(values, list):
        if value not in {v["code"] for v in values}:
            raise ValueError(f"{item_id}: value {value!r} is not in the codebook")
    elif not value.strip():
        raise ValueError(f"{item_id}: empty value")


def select_requests(page: Pass2Page, rules: Pass2Rules | None = None) -> Pass2Plan:
    """Decide which pass-2 support tasks a page needs (pure; no I/O)."""
    rules = rules or default_rules()
    labels = {a.activity_id: f"A{n}" for n, a in enumerate(page.activities, start=1)}
    quotes: list[ActivityQuoteTask] = []
    fields: list[ActivityFieldTask] = []
    for act in page.activities:
        seen: set[tuple[str, str, str]] = set()
        gate_parts: dict[str, list[str]] = {}
        for code in act.codes:
            item = rules.support_items.get(code.item_id)
            if item is None:
                raise ValueError(f"{code.item_id} is not a pass-2 item that needs support")
            _check_value(item, code.item_id, code.value, rules)
            for fid, (gate_item, open_values) in rules.gated_fields.items():
                if code.item_id == gate_item and code.value in open_values:
                    parts = gate_parts.setdefault(fid, [])
                    if code.chunk_id not in parts:
                        parts.append(code.chunk_id)
            if not rules.needs_quote(code.value):
                continue
            key = (code.item_id, code.chunk_id, code.value)
            if key in seen:
                continue
            seen.add(key)
            quotes.append(ActivityQuoteTask(
                task_id=f"q{len(quotes) + 1:03d}", activity_id=act.activity_id,
                label=labels[act.activity_id], item_id=code.item_id, chunk_id=code.chunk_id,
                question=rules.questions[code.item_id], answer=code.value,
            ))
        for fid in rules.gated_fields:  # codebook order, stable
            if fid in gate_parts:
                fields.append(ActivityFieldTask(
                    task_id=f"f{len(fields) + 1:03d}", activity_id=act.activity_id,
                    label=labels[act.activity_id], item_id=fid,
                    chunk_ids=tuple(gate_parts[fid]),
                ))
    return Pass2Plan(page.page_id, labels, tuple(quotes), tuple(fields))


# ---------------------------------------------------------------------------
# Prompt and request assembly
# ---------------------------------------------------------------------------


def build_system_prompt(cb: Codebook | None = None, rules: Pass2Rules | None = None) -> str:
    """Shared system prompt + the pass-2 prompt with the generated field sections."""
    cb = cb or load_codebook()
    rules = rules or rules_from_codebook(cb)
    shared = cb.shared_slot("system_prompt")
    if shared is None:
        raise ValueError("codebook has no shared system prompt")
    sections = _generated_sections()
    missing = [i for i in rules.gated_fields if i not in sections]
    if missing:
        raise ValueError(f"no generated extractor section for {missing}")
    body = (PASS2_PROMPT_PATH.read_text(encoding="utf-8")
            .replace("{{FIELD_SECTIONS}}",
                     "\n".join(sections[i] for i in rules.gated_fields).rstrip())
            .replace("{{QUOTE_MAX_CHARS}}", str(QUOTE_MAX_CHARS)))
    if "{{" in body:
        raise ValueError("unfilled placeholder in pass2_support_v27.md")
    return f"{shared.text}\n\n---\n\n{body}"


def output_schema(rules: Pass2Rules | None = None) -> dict[str, Any]:
    """JSON schema of the extractor's answer. It has no code field (C-001)."""
    nullable = {"anyOf": [{"type": "string"}, {"type": "null"}]}

    def obj(props: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": props, "required": list(props),
                "additionalProperties": False}

    return obj({
        "quotes": {"type": "array", "items": obj({
            "task_id": {"type": "string"}, "part_id": {"type": "string"}, "quote": nullable})},
        "fields": {"type": "array", "items": obj({
            "task_id": {"type": "string"}, "value": nullable, "part_id": nullable,
            "supporting_text": nullable})},
    })


def marked_part_text(page: Pass2Page, plan: Pass2Plan, chunk_id: str) -> str:
    """The part's text with ``[[Ak]]`` / ``[[/Ak]]`` at each activity's span ends."""
    chunk = page.page.chunk(chunk_id)
    marks: list[tuple[int, int, str]] = []  # (offset, order, mark); ends sort before starts
    for act in page.activities:
        label = plan.labels[act.activity_id]
        if chunk.start <= act.start < chunk.end:
            marks.append((act.start, 1, f"[[{label}]]"))
        if chunk.start < act.end <= chunk.end:
            marks.append((act.end, 0, f"[[/{label}]]"))
    out: list[str] = []
    pos = chunk.start
    for off, _order, mark in sorted(marks):
        out += [page.page.text[pos:off], mark]
        pos = off
    out.append(page.page.text[pos:chunk.end])
    return "".join(out)


def build_user_message(page: Pass2Page, plan: Pass2Plan, rules: Pass2Rules | None = None) -> str:
    rules = rules or default_rules()
    p = page.page
    out = [
        f"INSTITUTION: {p.institution_name}",
        f"PAGE ADDRESS: {p.url}",
        f"PAGE TITLE: {p.title or ''}",
        f"PAGE PARTS: {len(p.chunks)}",
        f"ACTIVITIES: {', '.join(plan.labels[a.activity_id] for a in page.activities)}",
        "",
    ]
    for c in p.chunks:
        out += [f'<part id="{c.chunk_id}">', marked_part_text(page, plan, c.chunk_id), "</part>"]
    asked = sorted({t.item_id for t in plan.quote_tasks})
    questions = {field_name(i): rules.questions[i] for i in asked}
    tasks = {
        "quote_tasks": [
            {"task_id": t.task_id, "activity": t.label, "question": field_name(t.item_id),
             "answer": t.answer, "part_id": t.chunk_id}
            for t in plan.quote_tasks
        ],
        "field_tasks": [
            {"task_id": t.task_id, "activity": t.label, "field": field_name(t.item_id),
             "part_ids": list(t.chunk_ids)}
            for t in plan.field_tasks
        ],
    }
    out += ["", "QUESTIONS:", json.dumps(questions, ensure_ascii=False, indent=1),
            "", "TASKS:", json.dumps(tasks, ensure_ascii=False, indent=1)]
    return "\n".join(out)


def build_job(page: Pass2Page, plan: Pass2Plan, *, system: str,
              schema: dict[str, Any] | None = None, rules: Pass2Rules | None = None) -> ExtractorJob:
    if not plan.needs_request:
        raise ValueError(f"page {page.page_id} needs no pass-2 support request")
    p = page.page
    params = build_params(system=system, user=build_user_message(page, plan, rules),
                          output_schema=schema or output_schema())
    return ExtractorJob(
        custom_id=make_custom_id(p.institution_id, p.url, prefix="x27s"),
        params=params,
        metadata={"stage": "5b_pass2_support_v27", "page_id": p.page_id,
                  "institution_id": p.institution_id, "source_url": p.url,
                  "prompt_version": PROMPT_VERSION},
    )


def build_jobs(pages: Sequence[Pass2Page], rules: Pass2Rules | None = None,
               cb: Codebook | None = None) -> tuple[list[ExtractorJob], dict[str, Pass2Plan]]:
    """Plans for every page and one job per page that needs one (DP-009 P6 a)."""
    rules = rules or default_rules()
    system = build_system_prompt(cb, rules)
    schema = output_schema(rules)
    plans: dict[str, Pass2Plan] = {}
    jobs: list[ExtractorJob] = []
    for page in pages:
        plan = select_requests(page, rules)
        plans[page.page_id] = plan
        if plan.needs_request:
            jobs.append(build_job(page, plan, system=system, schema=schema, rules=rules))
    return jobs, plans


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_TOP_KEYS = {"quotes", "fields"}
_QUOTE_KEYS = {"task_id", "part_id", "quote"}
_FIELD_KEYS = {"task_id", "value", "part_id", "supporting_text"}


@dataclass(frozen=True)
class ActivityQuote:
    """One quote record per (activity, code) task. Carries no code value (C-001);
    the answer it supports is the plan task's, joined on ``task_id``."""

    task_id: str
    activity_id: str
    item_id: str
    chunk_id: str  # the part that produced the code (R-044)
    quote: str | None
    status: str  # "quoted" | "empty" | "no_entry" | "wrong_part"
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActivityField:
    task_id: str
    activity_id: str
    item_id: str
    value: str | None
    chunk_id: str | None
    supporting_text: str | None
    #: "stated" | "not_stated" | "no_entry" | "no_supporting_text" | "wrong_part"
    status: str
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rejected:
    kind: str
    reason: str
    raw: Any


@dataclass(frozen=True)
class Pass2Support:
    page_id: str
    custom_id: str
    quotes: tuple[ActivityQuote, ...]
    fields: tuple[ActivityField, ...]
    rejected: tuple[Rejected, ...] = ()
    response_model: str | None = None
    message_id: str | None = None
    request_id: str | None = None
    usage: dict[str, Any] | None = None


def _unmark(text: str | None) -> tuple[str | None, tuple[str, ...]]:
    if text is None or not _MARK_RE.search(text):
        return text, ()
    cleaned = _MARK_RE.sub("", text)
    return (cleaned if cleaned.strip() else None), (MARKS_REMOVED_FLAG,)


def parse_pass2_result(result: ExtractorResult, page: Pass2Page, plan: Pass2Plan) -> Pass2Support:
    if not result.success or not result.text:
        raise RuntimeError(f"pass-2 support {result.custom_id!r} failed: {result.error}")
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise ExtractContractError(f"answer is not JSON: {exc}") from exc
    _check_keys(payload, _TOP_KEYS, "answer")
    rejected: list[Rejected] = []

    qtasks = {t.task_id: t for t in plan.quote_tasks}
    got_q: dict[str, ActivityQuote] = {}
    for raw in payload["quotes"] or []:
        _check_keys(raw, _QUOTE_KEYS, "quote")
        task = qtasks.get(raw["task_id"])
        if task is None:
            rejected.append(Rejected("quote", "unknown_task", raw))
            continue
        if task.task_id in got_q:
            rejected.append(Rejected("quote", "duplicate_task", raw))
            continue
        quote, mflags = _unmark(_text_or_none(raw["quote"]))
        base = (task.task_id, task.activity_id, task.item_id, task.chunk_id)
        if quote is not None and raw["part_id"] != task.chunk_id:
            rejected.append(Rejected("quote", "wrong_part", raw))
            got_q[task.task_id] = ActivityQuote(*base, None, "wrong_part")
            continue
        got_q[task.task_id] = ActivityQuote(
            *base, quote, "quoted" if quote is not None else "empty", _flags(quote) + mflags)
    quotes = tuple(
        got_q.get(t.task_id) or ActivityQuote(t.task_id, t.activity_id, t.item_id, t.chunk_id,
                                              None, "no_entry")
        for t in plan.quote_tasks
    )

    ftasks = {t.task_id: t for t in plan.field_tasks}
    got_f: dict[str, ActivityField] = {}
    for raw in payload["fields"] or []:
        _check_keys(raw, _FIELD_KEYS, "field")
        task = ftasks.get(raw["task_id"])
        if task is None:
            rejected.append(Rejected("field", "unknown_task", raw))
            continue
        if task.task_id in got_f:
            rejected.append(Rejected("field", "duplicate_task", raw))
            continue
        value, vflags = _unmark(_text_or_none(raw["value"]))
        support, sflags = _unmark(_text_or_none(raw["supporting_text"]))
        base = (task.task_id, task.activity_id, task.item_id)
        if value is None:
            got_f[task.task_id] = ActivityField(*base, None, None, None, "not_stated")
        elif support is None:
            rejected.append(Rejected("field", "no_supporting_text", raw))
            got_f[task.task_id] = ActivityField(*base, None, None, None, "no_supporting_text")
        elif raw["part_id"] not in task.chunk_ids:
            rejected.append(Rejected("field", "wrong_part", raw))
            got_f[task.task_id] = ActivityField(*base, None, None, None, "wrong_part")
        else:
            flags = _flags(support) + tuple(dict.fromkeys(vflags + sflags))
            got_f[task.task_id] = ActivityField(*base, value, raw["part_id"], support, "stated",
                                                flags)
    fields = tuple(
        got_f.get(t.task_id) or ActivityField(t.task_id, t.activity_id, t.item_id,
                                              None, None, None, "no_entry")
        for t in plan.field_tasks
    )
    return Pass2Support(
        page_id=page.page_id, custom_id=result.custom_id, quotes=quotes, fields=fields,
        rejected=tuple(rejected), response_model=result.response_model,
        message_id=result.message_id, request_id=result.request_id, usage=result.usage,
    )


__all__ = [
    "MARKS_REMOVED_FLAG",
    "PROMPT_VERSION",
    "ActivityCode",
    "ActivityField",
    "ActivityFieldTask",
    "ActivityQuote",
    "ActivityQuoteTask",
    "Pass2Activity",
    "Pass2Page",
    "Pass2Plan",
    "Pass2Rules",
    "Pass2Support",
    "Rejected",
    "build_job",
    "build_jobs",
    "build_system_prompt",
    "build_user_message",
    "default_rules",
    "marked_part_text",
    "output_schema",
    "parse_pass2_result",
    "rules_from_codebook",
    "select_requests",
]
