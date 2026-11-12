"""v2.7 pass-2 supporting-text call (T-032).

After jev pass 2 (T-023), one extractor request per page covering all its
activities (DP-009, PI P6 a) asks for:

1. **Quotes** for every positive / substantive activity-level code (R-040,
   R-041; Q-010 a), one task per (activity, item, part, answer), each from the
   part that produced the code (R-044, PF-001). A ``core.activity_segment`` code is
   coded per pair of passages, so it names the other activity of its pair and gets
   one task per pair; the task names that activity (PI 2026-11-05 "p2c a"). As in pass 1, the task shows
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
any the extractor copies (and near-variants such as ``[A1]``
that are not page text) and flags the quote ``marks_removed``.

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
from g3o.extract.parser_v27 import (
    ExtractContractError,
    _array,
    _check_keys,
    _flags,
    _id_or_none,
    _text_or_none,
)
from g3o.extract.request_v27 import (
    DEFERRED_FIELDS,
    QUOTE_MAX_CHARS,
    Pass1Page,
    SkippedCode,
    _generated_sections,
    field_name,
)

PROMPT_VERSION = "pass2_support_v27-p2c-approved"
PASS2_PROMPT_PATH = Path(__file__).parent / "prompts" / "pass2_support_v27.md"

#: Builder-side question slot: wording shown in a pass-2 quote task in place of
#: the item's codebook instruction, for items whose instruction is a method note
#: rather than a question (PI 2026-11-05 "D2c"). Not a codebook edit: the signed
#: instruction is unchanged and still drives jev. Wording approved by the PI through the
#: wording packet (RC-D-014 S3 b; PI 2026-11-05 "p2c draft ok").
QUESTION_OVERRIDES: dict[str, str] = {
    "core.activity_segment": (
        "How does this activity relate to the linked activity named in this task: is it the "
        "same activity described again, part of the linked programme, a programme the linked "
        "activity is part of, a joint activity with it, a rule that governs it or one governed "
        "by it, or a separate activity?"
    ),
}

#: Items coded per pair of passages (codebook ``core.activity_segment`` "Each pair of passages
#: gets a link."; storage lhs/rhs observation ids). Each code names the other activity of its
#: pair (``ActivityCode.linked_activity``); the code's activity is the first passage (lhs),
#: the linked activity the second (rhs), as the codebook value definitions read.
PAIR_ITEMS: frozenset[str] = frozenset({"core.activity_segment"})

#: Flag on a quote from which activity marks were removed.
MARKS_REMOVED_FLAG = "marks_removed"
_MARK_RE = re.compile(r"\[\[/?A\d+\]\]")
#: Near-variants of a mark as an extractor may copy them (lane B F5): one or two opening
#: brackets, optional spaces and slash, the label, then up to two closing brackets
#: (``[A1]``, ``[[ A1 ]]``, unclosed ``[[/A1``). Removed only when the label is one this
#: request marked and the matched string is not on the page (so page text such as an annex
#: reference "[A1]" is kept).
_MARK_VARIANT_RE = re.compile(r"\[\[?\s*/?\s*A(\d+)(?!\d)\s*\]?\]?")


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
    #: items whose quote-task question comes from QUESTION_OVERRIDES (provenance)
    overridden: frozenset[str] = frozenset()
    #: parts items (amendment A6): item -> part names in codebook order
    parts: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: (item, part) -> the part's signed question (part 0: the item's instruction; later parts:
    #: ``values.part_instructions.<part>``), as the T-011 question ``<item>#<part>`` asks it
    part_questions: dict[tuple[str, str], str] = field(default_factory=dict)
    #: (item, part) -> the part's value codes
    part_codes: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict)
    #: computed-year items (amendment A2) -> the missing labels jev is offered beside the years
    year_items: dict[str, frozenset[str]] = field(default_factory=dict)

    def needs_quote(self, value: str) -> bool:
        return value not in self.no_support_values and value != self.temporary_answer


def rules_from_codebook(cb: Codebook,
                        overrides: dict[str, str] | None = None) -> Pass2Rules:
    """Rules read from the codebook. ``no_support_values`` is the codebook's
    ``support_status.status_by_answer`` keys, never a list kept here (so a
    value the codebook exempts gets no quote task). ``overrides`` defaults to
    :data:`QUESTION_OVERRIDES`."""
    overrides = QUESTION_OVERRIDES if overrides is None else overrides
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
    unknown = sorted(set(overrides) - set(support))
    if unknown:
        raise ValueError(f"question override for items that are not pass-2 quote items: {unknown}")
    questions.update(overrides)
    parts: dict[str, tuple[str, ...]] = {}
    part_questions: dict[tuple[str, str], str] = {}
    part_codes: dict[tuple[str, str], frozenset[str]] = {}
    year_items: dict[str, frozenset[str]] = {}
    for k in support:
        item_parts = cb.parts(k)
        if item_parts is not None:
            parts[k] = tuple(name for name, _ in item_parts)
            for n, (name, values) in enumerate(item_parts):
                slot = cb.part_instruction(k, n)
                if slot is None:
                    raise ValueError(f"pass-2 item {k} part {name} has no question text")
                part_questions[(k, name)] = questions[k] if n == 0 else slot.text
                part_codes[(k, name)] = frozenset(str(v["code"]) for v in values)
        elif cb.computed_values(k) is not None:
            year_items[k] = frozenset(code for code, _ in cb.missing_choices(k))
    gated: dict[str, tuple[str, frozenset[str]]] = {}
    for k in DEFERRED_FIELDS:
        gate = items[k].get("gate")
        if not (isinstance(gate, dict) and isinstance(gate.get("values"), list)):
            raise ValueError(f"{k} has no gate value list in the codebook")
        if gate["item"] not in support:
            raise ValueError(f"{k}: gate item {gate['item']} is not a pass-2 classifier item")
        gated[k] = (gate["item"], frozenset(gate["values"]))
    temp = cb.data["shared"]["part_prompt"]["temporary_answer"]["label"]["text"]
    return Pass2Rules(support, no_support, temp, questions, gated, frozenset(overrides),
                      parts, part_questions, part_codes, year_items)


@lru_cache(maxsize=1)
def default_rules() -> Pass2Rules:
    return rules_from_codebook(load_codebook())


# ---------------------------------------------------------------------------
# Inputs (mocked T-023 activity record shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityCode:
    """One pass-2 answer for one activity from one part (one per selected value).

    ``part`` names the item part for a parts item (e.g. ``relationship`` or
    ``searched_institution_role`` of ``core.observed_actor_relationship``; T-011 asks each as
    its own question) and is None for every other item, as in the support check's evidence.

    ``linked_activity`` is the ``activity_id`` of the other activity of the pair for a pair
    item (:data:`PAIR_ITEMS`): required there, refused on every other item. It must be another
    activity of the same page request."""

    item_id: str
    chunk_id: str
    value: str
    part: str | None = None
    linked_activity: str | None = None


@dataclass(frozen=True)
class Pass2Activity:
    activity_id: str
    start: int | None  # full-page offsets (DP-008); None when pass 1 left the span unresolved
    end: int | None
    codes: tuple[ActivityCode, ...]


@dataclass(frozen=True)
class Pass2Page:
    page: Pass1Page  # page text, parts, institution (T-021 / T-022 inputs)
    activities: tuple[Pass2Activity, ...]

    def __post_init__(self) -> None:
        # A span off the page (or empty, or unresolved) and a code from an unknown part are
        # left out by select_requests and recorded there, so they do not stop the page (lane B
        # F3, F6); duplicate ids make the labels ambiguous and still raise.
        ids = [a.activity_id for a in self.activities]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate activity_id")

    def span_ok(self, act: Pass2Activity) -> bool:
        return (isinstance(act.start, int) and isinstance(act.end, int)
                and 0 <= act.start < act.end <= len(self.page.text))

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
    part: str | None = None  # the item part, for a parts item (T-011 question <item>#<part>)
    linked_activity: str | None = None  # pair item: the other activity's activity_id
    linked_label: str | None = None  # ... and its label in the message (e.g. A2)


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
    labels: dict[str, str]  # activity_id -> label (activities with a usable span only)
    quote_tasks: tuple[ActivityQuoteTask, ...] = ()
    field_tasks: tuple[ActivityFieldTask, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
    #: codes left out of the request, with the reason (lane B F6); the runner records them
    skipped_codes: tuple[SkippedCode, ...] = ()
    #: activities left out because their span is missing, empty or not on the page (lane B F3)
    skipped_activities: tuple[str, ...] = ()

    @property
    def needs_request(self) -> bool:
        return bool(self.quote_tasks) or bool(self.field_tasks)


_YEAR_RE = re.compile(r"[0-9]{4}")  # ASCII digits only (``\d`` would take any script's digits)


def _value_problem(item: dict[str, Any], code: ActivityCode, rules: Pass2Rules) -> str | None:
    """Why ``code`` cannot be used, or None. Mirrors pass 1 (``request_v27.select_requests``):
    a value must be one the item offers, an exempt value or the temporary part answer. The
    offered values are the value list; for a parts item, the named part's values; for a year
    item, a calendar year in four ASCII digits (T-011 ``candidate_code``) or one of the item's
    offered missing labels."""
    item_parts = rules.parts.get(code.item_id)
    if item_parts is not None:
        if code.part is None:
            return "part_not_named"
        if code.part not in item_parts:
            return "unknown_item_part"
    elif code.part is not None:
        return "not_a_parts_item"
    value = code.value
    if value in rules.no_support_values or value == rules.temporary_answer:
        return None
    values = item.get("values")
    if item_parts is not None:
        offered: set[str] | frozenset[str] = rules.part_codes[(code.item_id, code.part)]
    elif code.item_id in rules.year_items:
        if isinstance(value, str) and _YEAR_RE.fullmatch(value) and int(value) >= 1000:
            return None
        offered = rules.year_items[code.item_id]
    elif isinstance(values, list):
        offered = {v["code"] for v in values}
    else:
        offered = set()
    return None if value in offered else "value_not_in_codebook"


def _link_problem(act: Pass2Activity, code: ActivityCode, page_ids: set[str],
                  labels: dict[str, str]) -> str | None:
    """Why the code's linked activity cannot be used, or None (p2c a). A pair item needs the
    other activity of its pair: another activity of this page request with a marked span;
    any other item takes none."""
    linked = code.linked_activity
    if code.item_id not in PAIR_ITEMS:
        return None if linked is None else "linked_activity_not_allowed"
    if linked is None:
        return "linked_activity_missing"
    if linked == act.activity_id:
        return "self_linked_activity"
    if linked not in page_ids:
        return "unknown_linked_activity"
    if linked not in labels:  # on the page but left out (no usable span): nothing to name
        return "linked_activity_unmarked"
    return None


def _question_key(item_id: str, part: str | None, rules: Pass2Rules) -> str:
    """Key of the question under QUESTIONS: the field name, and for a later part of a parts
    item ``<field>#<part>``, as T-011 names its question (``<item>#<part>``)."""
    name = field_name(item_id)
    item_parts = rules.parts.get(item_id)
    if part is None or item_parts is None or part == item_parts[0]:
        return name
    return f"{name}#{part}"


def _part_index(item_id: str, part: str | None, rules: Pass2Rules) -> int:
    item_parts = rules.parts.get(item_id)
    return 0 if part is None or item_parts is None else item_parts.index(part)


def select_requests(page: Pass2Page, rules: Pass2Rules | None = None) -> Pass2Plan:
    """Decide which pass-2 support tasks a page needs (pure; no I/O).

    A code that cannot be used (item without pass-2 support, value or part the codebook does
    not offer, unknown page part) is left out and recorded in ``skipped_codes``; an activity
    whose span is missing, empty or off the page is left out (unlabelled, unmarked) and
    recorded in ``skipped_activities``. The rest of the page goes on (lane B F3, F6)."""
    rules = rules or default_rules()
    usable = [a for a in page.activities if page.span_ok(a)]
    labels = {a.activity_id: f"A{n}" for n, a in enumerate(usable, start=1)}
    skipped_acts = tuple(a.activity_id for a in page.activities if a.activity_id not in labels)
    page_parts = {c.chunk_id for c in page.page.chunks}
    quotes: list[ActivityQuoteTask] = []
    fields: list[ActivityFieldTask] = []
    skipped: list[SkippedCode] = []
    all_ids = {a.activity_id for a in page.activities}
    for act in usable:
        seen: set[tuple[str, str | None, str, str, str | None]] = set()
        gate_parts: dict[str, list[str]] = {}
        for code in act.codes:
            item = rules.support_items.get(code.item_id)
            if item is None:
                reason: str | None = "not_a_support_item"
            elif code.chunk_id not in page_parts:
                reason = "unknown_part"
            else:
                reason = (_link_problem(act, code, all_ids, labels)
                          or _value_problem(item, code, rules))
            if reason is not None:
                skipped.append(SkippedCode(code.item_id, code.chunk_id, code.value, reason,
                                           act.activity_id, code.part, code.linked_activity))
                continue
            for fid, (gate_item, open_values) in rules.gated_fields.items():
                if code.item_id == gate_item and code.value in open_values:
                    parts = gate_parts.setdefault(fid, [])
                    if code.chunk_id not in parts:
                        parts.append(code.chunk_id)
            if not rules.needs_quote(code.value):
                continue
            key = (code.item_id, code.part, code.chunk_id, code.value, code.linked_activity)
            if key in seen:
                continue
            seen.add(key)
            question = (rules.part_questions[(code.item_id, code.part)] if code.part is not None
                        else rules.questions[code.item_id])
            quotes.append(ActivityQuoteTask(
                task_id=f"q{len(quotes) + 1:03d}", activity_id=act.activity_id,
                label=labels[act.activity_id], item_id=code.item_id, chunk_id=code.chunk_id,
                question=question, answer=code.value, part=code.part,
                linked_activity=code.linked_activity,
                linked_label=labels.get(code.linked_activity) if code.linked_activity else None,
            ))
        for fid in rules.gated_fields:  # codebook order, stable
            if fid in gate_parts:
                fields.append(ActivityFieldTask(
                    task_id=f"f{len(fields) + 1:03d}", activity_id=act.activity_id,
                    label=labels[act.activity_id], item_id=fid,
                    chunk_ids=tuple(gate_parts[fid]),
                ))
    return Pass2Plan(page.page_id, labels, tuple(quotes), tuple(fields),
                     skipped_codes=tuple(skipped), skipped_activities=skipped_acts)


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
        label = plan.labels.get(act.activity_id)
        if label is None:  # left out by select_requests: no usable span
            continue
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


def _quote_task_entry(t: ActivityQuoteTask, rules: Pass2Rules) -> dict[str, str]:
    entry = {"task_id": t.task_id, "activity": t.label}
    if t.linked_label is not None:  # pair item only (p2c a)
        entry["linked_activity"] = t.linked_label
    entry.update({"question": _question_key(t.item_id, t.part, rules),
                  "answer": t.answer, "part_id": t.chunk_id})
    return entry


def build_user_message(page: Pass2Page, plan: Pass2Plan, rules: Pass2Rules | None = None) -> str:
    rules = rules or default_rules()
    p = page.page
    out = [
        f"INSTITUTION: {p.institution_name}",
        f"PAGE ADDRESS: {p.url}",
        f"PAGE TITLE: {p.title or ''}",
        f"PAGE PARTS: {len(p.chunks)}",
        f"ACTIVITIES: {', '.join(plan.labels.values())}",
        "",
    ]
    for c in p.chunks:
        out += [f'<part id="{c.chunk_id}">', marked_part_text(page, plan, c.chunk_id), "</part>"]
    asked = sorted({(t.item_id, _part_index(t.item_id, t.part, rules), t.part, t.question)
                    for t in plan.quote_tasks})
    questions = {_question_key(i, part, rules): q for i, _n, part, q in asked}
    tasks = {
        "quote_tasks": [_quote_task_entry(t, rules) for t in plan.quote_tasks],
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
                  "prompt_version": PROMPT_VERSION,
                  "question_overrides": sorted(
                      {t.item_id for t in plan.quote_tasks} & (rules or default_rules()).overridden)},
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
    part: str | None = None  # the item part of a parts item (for the X35 question, T-024)
    #: pair item: the other activity of the pair (lhs = ``activity_id``, rhs = this; p2c a)
    linked_activity: str | None = None


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


def _unmark(text: str | None, labels: frozenset[str] = frozenset(),
            page_text: str = "") -> tuple[str | None, tuple[str, ...]]:
    """Remove the activity marks the extractor copied: the exact marks always, and their
    near-variants (lane B F5) when the label is one of ``labels`` (the numbers this request
    marked) and the variant does not occur in ``page_text`` (so it cannot be page text)."""
    if text is None:
        return text, ()
    cleaned = _MARK_RE.sub("", text)

    def variant(m: re.Match[str]) -> str:
        return "" if m.group(1) in labels and m.group(0) not in page_text else m.group(0)

    cleaned = _MARK_VARIANT_RE.sub(variant, cleaned)
    if cleaned == text:
        return text, ()
    cleaned = cleaned.strip()
    return (cleaned or None), (MARKS_REMOVED_FLAG,)


def parse_pass2_result(result: ExtractorResult, page: Pass2Page, plan: Pass2Plan) -> Pass2Support:
    if not result.success or not result.text:
        raise RuntimeError(f"pass-2 support {result.custom_id!r} failed: {result.error}")
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise ExtractContractError(f"answer is not JSON: {exc}") from exc
    _check_keys(payload, _TOP_KEYS, "answer")
    rejected: list[Rejected] = []
    marked = frozenset(label[1:] for label in plan.labels.values())  # "A3" -> "3"

    def unmark(text: str | None) -> tuple[str | None, tuple[str, ...]]:
        return _unmark(text, marked, page.page.text)

    qtasks = {t.task_id: t for t in plan.quote_tasks}
    got_q: dict[str, ActivityQuote] = {}
    for raw in _array(payload["quotes"], "quotes"):  # ruling 30 a: a wrong shape is a contract error
        _check_keys(raw, _QUOTE_KEYS, "quote")
        _id_or_none(raw["part_id"], "quote part_id")
        task = qtasks.get(_id_or_none(raw["task_id"], "quote task_id"))
        if task is None:
            rejected.append(Rejected("quote", "unknown_task", raw))
            continue
        if task.task_id in got_q:
            rejected.append(Rejected("quote", "duplicate_task", raw))
            continue
        quote, mflags = unmark(_text_or_none(raw["quote"]))
        base = (task.task_id, task.activity_id, task.item_id, task.chunk_id)
        if quote is not None and raw["part_id"] != task.chunk_id:
            rejected.append(Rejected("quote", "wrong_part", raw))
            got_q[task.task_id] = ActivityQuote(*base, None, "wrong_part", part=task.part,
                                                linked_activity=task.linked_activity)
            continue
        got_q[task.task_id] = ActivityQuote(
            *base, quote, "quoted" if quote is not None else "empty", _flags(quote) + mflags,
            part=task.part, linked_activity=task.linked_activity)
    quotes = tuple(
        got_q.get(t.task_id) or ActivityQuote(t.task_id, t.activity_id, t.item_id, t.chunk_id,
                                              None, "no_entry", part=t.part,
                                              linked_activity=t.linked_activity)
        for t in plan.quote_tasks
    )

    ftasks = {t.task_id: t for t in plan.field_tasks}
    got_f: dict[str, ActivityField] = {}
    for raw in _array(payload["fields"], "fields"):
        _check_keys(raw, _FIELD_KEYS, "field")
        _id_or_none(raw["part_id"], "field part_id")
        task = ftasks.get(_id_or_none(raw["task_id"], "field task_id"))
        if task is None:
            rejected.append(Rejected("field", "unknown_task", raw))
            continue
        if task.task_id in got_f:
            rejected.append(Rejected("field", "duplicate_task", raw))
            continue
        value, vflags = unmark(_text_or_none(raw["value"]))
        support, sflags = unmark(_text_or_none(raw["supporting_text"]))
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
    "PAIR_ITEMS",
    "PROMPT_VERSION",
    "QUESTION_OVERRIDES",
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
