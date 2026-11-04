"""v2.7 pass-1 extraction: request selection and request assembly (T-022).

One extractor request per page after jev pass 1 (T-021), scoped per item
(PLAN T-022 Objective):

1. **Quotes** for every positive / substantive pass-1 page code, on every page
   whatever its verdict (R-040, R-041; Q-010 a), one task per (item, part) so
   each quote comes from the part that produced the code (R-044, PF-002).
2. **Follow-up links** for every page pass 1 marks incomplete
   (``core.page_complete`` = ``yes``; the codebook note: ``yes`` means the page
   refers the reader onward), chosen among the page's stored links (T-014;
   R-031, C-001), whatever the verdict.
3. **Activity spans** only on the 5 R-003 verdicts (DEC-010 a). The extractor
   returns start/end anchor text; :mod:`g3o.extract.parser_v27` turns them into
   character offsets from the start of the whole page (DP-008, PI P5 a).
4. **Residual free-text activity fields** per the codebook coder column
   (``coder: quote_step``; R-006, r2#28), each value with its supporting text
   (R-040). Fields whose gate is a pass-2 answer are not asked here (see
   :data:`DEFERRED_FIELDS`).
5. **Publication date** (X26) when the page carries no deterministic date.

A page with no task gets no request. A quote task carries the item's signed
question AND the answer jev chose for it in that part (PI 2026-11-04, "show
answer -- confirmatory test & biased, it's fine"; reverses r2#18's blindness
rule, RC-D-017). The answer is input only: no task asks the extractor for a
code and its output schema has no code field (C-001).

Each supporting quote is to be at most :data:`QUOTE_MAX_CHARS` characters
(PI 2026-11-04, "200 (put in prompt as cap too)"; reverses X19 / r2#17). The
cap is an instruction in the prompt; the parser flags a longer quote and never
truncates it.

Nothing here truncates page text: the v2.5 60,000-character head+tail cap
(``g3o.extract.batch.DEFAULT_TEXT_CAP_CHARS``) does not apply on this path.

The pass-1 page artifact (T-021) is not built yet; :class:`Pass1Page` is the
mocked shape this module needs (card T-022 Inputs: "merged or mocked").
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
from g3o.common.page_chunks import Chunk
from g3o.extract.anthropic_client import ExtractorJob, build_params, make_custom_id

PROMPT_VERSION = "extract_v27-draft-2"

#: Prompt-side length cap for every supporting quote (display cap, PI 2026-11-04).
QUOTE_MAX_CHARS = 200

_PROMPTS_DIR = Path(__file__).parent / "prompts"
EXTRACT_V27_PROMPT_PATH = _PROMPTS_DIR / "extract_v27.md"
_GENERATED_DIR = Path(__file__).resolve().parents[1] / "codebook" / "generated"
GENERATED_SECTIONS_PATH = _GENERATED_DIR / "extractor_prompt_sections.md"

#: The 5 R-003 verdicts that carry activities (spans, free-text fields).
R003_VERDICTS = (
    "confirms_activity",
    "ambiguous_genai",
    "ambiguous_attribution",
    "other_body",
    "event_only",
)

#: Activity-level quote-step fields whose gate is a pass-2 classifier answer
#: (CX-61: outcome_kind / incident_kind not none_reported). Moved to the
#: pass-2 quote job, T-032 (RC-D-017; PI 2026-11-04 "5 a"); not asked here.
DEFERRED_FIELDS = ("core.reported_outcomes", "core.reported_incidents")

#: Shared codebook rules shown with the activity task.
ACTIVITY_RULE_IDS = ("core.rule.activity_unit", "core.rule.genai_boundary")

#: Page-level quote-step item asked through the date task.
DATE_ITEM = "core.source_publication_date"


# ---------------------------------------------------------------------------
# Codebook-derived rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pass1Rules:
    """What request selection reads from the codebook."""

    support_items: dict[str, dict[str, Any]]  # pass-1 classifier items needing support
    no_support_values: frozenset[str]  # values that need no quote, on any item
    negative_verdicts: frozenset[str]
    activity_fields: tuple[str, ...]  # quote-step activity fields asked in pass 1
    questions: dict[str, str]  # item id -> signed question text
    chrome_items: frozenset[str]  # items whose input text includes chrome
    temporary_answer: str  # R-044 "not covered by this part"

    def needs_quote(self, item_id: str, value: str) -> bool:
        if value in self.no_support_values or value == self.temporary_answer:
            return False
        if item_id == "core.page_verdict" and value in self.negative_verdicts:
            return False
        return True


def rules_from_codebook(cb: Codebook) -> Pass1Rules:
    items = cb.build_items()
    support_items = {
        k: v for k, v in items.items()
        if v.get("pass") == 1 and v.get("coder") == "classifier" and v.get("support_required") is True
    }
    status = cb.vocabularies["support_status"]
    # Plain answer tokens only; the "negative page verdicts (R-041)" key is a label.
    no_support = frozenset(k for k in status["status_by_answer"] if re.fullmatch(r"[A-Za-z_]+", k))
    negative = frozenset(status["negative_page_verdicts"]["values"])

    fields: list[str] = []
    for k, v in items.items():
        if v.get("coder") != "quote_step" or "activity" not in v.get("level", []):
            continue
        gate = v.get("gate")
        if gate == "none" or (isinstance(gate, dict) and "table" in gate):
            fields.append(k)
    questions = {}
    for k in support_items:
        slot = cb.instruction(k)
        if slot is None:
            raise ValueError(f"pass-1 item {k} has no question text")
        questions[k] = slot.text
    chrome = frozenset(k for k, v in support_items.items() if v.get("input_text") == "main_plus_chrome")
    temp = cb.data["shared"]["part_prompt"]["temporary_answer"]["label"]["text"]
    return Pass1Rules(support_items, no_support, negative, tuple(fields), questions, chrome, temp)


@lru_cache(maxsize=1)
def default_rules() -> Pass1Rules:
    return rules_from_codebook(load_codebook())


# ---------------------------------------------------------------------------
# Inputs (mocked T-021 artifact shape)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageCode:
    """One pass-1 answer from one part of a page (one record per selected code)."""

    item_id: str
    chunk_id: str
    value: str


@dataclass(frozen=True)
class Pass1Page:
    page_id: str
    institution_id: str
    institution_name: str
    url: str
    title: str | None
    text: str
    chunks: tuple[Chunk, ...]
    codes: tuple[PageCode, ...]
    verdict: str  # combined page verdict
    page_complete: str | None  # combined core.page_complete answer, None if not asked
    chrome_text: str | None = None  # T-014; None = not measured
    links: tuple[dict[str, Any], ...] | None = None  # T-014; None = not measured
    has_metadata_date: bool = False  # a deterministic publication date was found

    def __post_init__(self) -> None:
        if not self.chunks:
            raise ValueError("a page needs at least one part (T-020 chunk_page)")
        pos = 0
        for c in self.chunks:
            if c.page_id != self.page_id or c.start != pos or self.text[c.start:c.end] != c.text:
                raise ValueError(f"part {c.chunk_id} does not tile the page text")
            pos = c.end
        if pos != len(self.text):
            raise ValueError("parts do not cover the whole page text")
        ids = {c.chunk_id for c in self.chunks}
        for code in self.codes:
            if code.chunk_id not in ids:
                raise ValueError(f"code {code.item_id} names unknown part {code.chunk_id}")

    @property
    def chrome_id(self) -> str:
        return f"{self.page_id}#chrome"

    def chunk(self, chunk_id: str) -> Chunk:
        for c in self.chunks:
            if c.chunk_id == chunk_id:
                return c
        raise KeyError(chunk_id)


# ---------------------------------------------------------------------------
# Tasks and selection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuoteTask:
    task_id: str
    item_id: str
    chunk_id: str
    question: str
    answer: str  # jev's chosen pass-1 answer in this part (input only; RC-D-017)
    allow_chrome: bool


@dataclass(frozen=True)
class StoredLink:
    link_id: str
    url: str
    anchor_text: str
    context: str


@dataclass(frozen=True)
class RequestPlan:
    page_id: str
    quote_tasks: tuple[QuoteTask, ...] = ()
    links: tuple[StoredLink, ...] = ()
    link_task: bool = False
    activity_fields: tuple[str, ...] = ()
    activity_task: bool = False
    date_task: bool = False
    #: Why no link task ran on an incomplete page: "not_measured" (T-014
    #: fields absent, C2 a) or "no_stored_links". None otherwise.
    link_status: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def needs_request(self) -> bool:
        return bool(self.quote_tasks) or self.link_task or self.activity_task


def select_requests(page: Pass1Page, rules: Pass1Rules | None = None) -> RequestPlan:
    """Decide which extraction tasks a page needs (pure; no I/O)."""
    rules = rules or default_rules()
    verdicts = rules.support_items["core.page_verdict"]
    allowed_verdicts = {v["code"] for v in verdicts["values"]} | {"not_assessable"}
    if page.verdict not in allowed_verdicts:
        raise ValueError(f"unknown page verdict {page.verdict!r}")

    quote_tasks: list[QuoteTask] = []
    seen: set[tuple[str, str]] = set()
    for code in page.codes:
        item = rules.support_items.get(code.item_id)
        if item is None:
            raise ValueError(f"{code.item_id} is not a pass-1 item that needs support")
        offered = {v["code"] for v in item["values"]} if isinstance(item["values"], list) else set()
        if code.value not in offered and code.value not in rules.no_support_values \
                and code.value != rules.temporary_answer:
            raise ValueError(f"{code.item_id}: value {code.value!r} is not in the codebook")
        if not rules.needs_quote(code.item_id, code.value):
            continue
        key = (code.item_id, code.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        quote_tasks.append(QuoteTask(
            task_id=f"q{len(quote_tasks) + 1:03d}",
            item_id=code.item_id,
            chunk_id=code.chunk_id,
            question=rules.questions[code.item_id],
            answer=code.value,
            allow_chrome=code.item_id in rules.chrome_items and bool(page.chrome_text),
        ))

    links: tuple[StoredLink, ...] = ()
    link_task = False
    link_status = None
    if page.page_complete == "yes":
        if page.links is None:
            link_status = "not_measured"
        elif not page.links:
            link_status = "no_stored_links"
        else:
            links = tuple(
                StoredLink(f"L{n:03d}", str(ln["url"]), str(ln.get("anchor_text") or ""),
                           str(ln.get("context") or ""))
                for n, ln in enumerate(page.links, start=1)
            )
            link_task = True

    activity_task = page.verdict in R003_VERDICTS
    plan = RequestPlan(
        page_id=page.page_id,
        quote_tasks=tuple(quote_tasks),
        links=links,
        link_task=link_task,
        activity_fields=rules.activity_fields if activity_task else (),
        activity_task=activity_task,
        link_status=link_status,
    )
    if plan.needs_request and not page.has_metadata_date:
        plan = RequestPlan(**{**plan.__dict__, "date_task": True})
    return plan


# ---------------------------------------------------------------------------
# Prompt and request assembly
# ---------------------------------------------------------------------------


def _generated_sections(path: Path = GENERATED_SECTIONS_PATH) -> dict[str, str]:
    """Split T-013's generated extractor sections into item id -> section text."""
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in re.finditer(r"^## `([a-z]+\.[a-z0-9_]+)`\n(.*?)(?=^## `|\Z)", text, re.S | re.M):
        out[m.group(1)] = f"## `{m.group(1)}`\n{m.group(2)}".rstrip() + "\n"
    return out


def field_name(item_id: str) -> str:
    return item_id.split(".", 1)[1]


def build_system_prompt(cb: Codebook | None = None, rules: Pass1Rules | None = None) -> str:
    """Shared system prompt + the pass-1 extraction prompt, with generated sections.

    Identical for every request of a release (prompt-cache friendly). The
    item sections are T-013's generated text, copied as generated.
    """
    cb = cb or load_codebook()
    rules = rules or rules_from_codebook(cb)
    shared = cb.shared_slot("system_prompt")
    if shared is None:
        raise ValueError("codebook has no shared system prompt")
    template = EXTRACT_V27_PROMPT_PATH.read_text(encoding="utf-8")
    sections = _generated_sections()
    wanted = (*rules.activity_fields, DATE_ITEM)
    missing = [i for i in wanted if i not in sections]
    if missing:
        raise ValueError(f"no generated extractor section for {missing}")
    activity_rules = "\n".join(
        f"- {r.text}" for rid in ACTIVITY_RULE_IDS for r in cb.shared_rule_texts(rid)
    )
    body = (template
            .replace("{{ACTIVITY_RULES}}", activity_rules)
            .replace("{{FIELD_SECTIONS}}", "\n".join(sections[i] for i in wanted).rstrip())
            .replace("{{QUOTE_MAX_CHARS}}", str(QUOTE_MAX_CHARS)))
    if "{{" in body:
        raise ValueError("unfilled placeholder in extract_v27.md")
    return f"{shared.text}\n\n---\n\n{body}"


def output_schema(rules: Pass1Rules | None = None) -> dict[str, Any]:
    """JSON schema of the extractor's answer. It has no code field (C-001)."""
    rules = rules or default_rules()
    nullable = {"anyOf": [{"type": "string"}, {"type": "null"}]}

    def obj(props: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": props, "required": list(props),
                "additionalProperties": False}

    field_names = [field_name(i) for i in rules.activity_fields]
    return obj({
        "quotes": {"type": "array", "items": obj({
            "task_id": {"type": "string"}, "part_id": {"type": "string"}, "quote": nullable})},
        "links": {"type": "array", "items": obj({
            "link_id": {"type": "string"}, "part_id": {"type": "string"}, "quote": {"type": "string"}})},
        "activities": {"type": "array", "items": obj({
            "part_id": {"type": "string"},
            "start_text": {"type": "string"},
            "end_text": {"type": "string"},
            "fields": {"type": "array", "items": obj({
                "field": {"type": "string", "enum": field_names},
                "value": nullable, "part_id": nullable, "supporting_text": nullable})},
        })},
        "publication_date": {"anyOf": [{"type": "null"}, obj({
            "value": {"type": "string"}, "part_id": {"type": "string"},
            "supporting_text": {"type": "string"}})]},
    })


def build_user_message(page: Pass1Page, plan: RequestPlan) -> str:
    """The per-page message: institution, page parts, chrome, links, tasks."""
    out = [
        f"INSTITUTION: {page.institution_name}",
        f"PAGE ADDRESS: {page.url}",
        f"PAGE TITLE: {page.title or ''}",
        f"PAGE PARTS: {len(page.chunks)}",
        "",
    ]
    for c in page.chunks:
        out += [f'<part id="{c.chunk_id}">', c.text, "</part>"]
    if page.chrome_text and any(t.allow_chrome for t in plan.quote_tasks):
        out += [f'<chrome id="{page.chrome_id}">', page.chrome_text, "</chrome>"]
    if plan.link_task:
        out += ["", "STORED LINKS:"]
        out += [json.dumps({"link_id": ln.link_id, "address": ln.url, "link_text": ln.anchor_text,
                            "text_around": ln.context}, ensure_ascii=False) for ln in plan.links]
    tasks: dict[str, Any] = {
        "quote_tasks": [
            {"task_id": t.task_id, "part_id": t.chunk_id, "question": t.question,
             "answer": t.answer, "chrome_allowed": t.allow_chrome}
            for t in plan.quote_tasks
        ],
        "link_task": plan.link_task,
        "activity_task": {"fields": [field_name(i) for i in plan.activity_fields]}
        if plan.activity_task else None,
        "date_task": plan.date_task,
    }
    out += ["", "TASKS:", json.dumps(tasks, ensure_ascii=False, indent=1)]
    return "\n".join(out)


def build_job(page: Pass1Page, plan: RequestPlan, *, system: str,
              schema: dict[str, Any] | None = None) -> ExtractorJob:
    if not plan.needs_request:
        raise ValueError(f"page {page.page_id} needs no extraction request")
    params = build_params(system=system, user=build_user_message(page, plan),
                          output_schema=schema or output_schema())
    return ExtractorJob(
        custom_id=make_custom_id(page.institution_id, page.url),
        params=params,
        metadata={"stage": "5_extract_v27", "page_id": page.page_id,
                  "institution_id": page.institution_id, "source_url": page.url,
                  "prompt_version": PROMPT_VERSION},
    )


def build_jobs(pages: Sequence[Pass1Page], rules: Pass1Rules | None = None,
               cb: Codebook | None = None) -> tuple[list[ExtractorJob], dict[str, RequestPlan]]:
    """Plans for every page and jobs for the pages that need one."""
    rules = rules or default_rules()
    system = build_system_prompt(cb, rules)
    schema = output_schema(rules)
    plans: dict[str, RequestPlan] = {}
    jobs: list[ExtractorJob] = []
    for page in pages:
        plan = select_requests(page, rules)
        plans[page.page_id] = plan
        if plan.needs_request:
            jobs.append(build_job(page, plan, system=system, schema=schema))
    return jobs, plans


__all__ = [
    "ACTIVITY_RULE_IDS",
    "DATE_ITEM",
    "DEFERRED_FIELDS",
    "PROMPT_VERSION",
    "QUOTE_MAX_CHARS",
    "R003_VERDICTS",
    "PageCode",
    "Pass1Page",
    "Pass1Rules",
    "QuoteTask",
    "RequestPlan",
    "StoredLink",
    "build_job",
    "build_jobs",
    "build_system_prompt",
    "build_user_message",
    "default_rules",
    "output_schema",
    "rules_from_codebook",
    "select_requests",
]
