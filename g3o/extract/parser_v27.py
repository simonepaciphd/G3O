"""Parse a v2.7 pass-1 extraction answer (T-022).

Input: the :class:`~g3o.extract.anthropic_client.ExtractorResult` for one page,
the page and its :class:`~g3o.extract.request_v27.RequestPlan`. Output: a
:class:`Pass1Extraction` holding only copied text, stored-link selections and
character spans. The parser never reads a code from the extractor's answer
(C-001): the answer schema has no code field, any key outside the schema is a
contract error, and nothing here maps extractor text onto an item's values.

Rules applied:

- **Quotes carry their part id** (R-044). Every quote task gets exactly one
  :class:`QuoteSupport`; a missing, empty or misplaced quote is recorded as an
  empty result with its reason, so the R-041 downgrade (T-024) sees it.
  Whether a quote matches the page (R-042) is T-024's check, not this one.
- **Links come from the stored list only** (R-031, C-001): the extractor
  names a link id, the address is taken from the page's stored links.
- **Spans are full-page character offsets** (DP-008, PI P5 a), found by
  locating the extractor's verbatim start and end anchors in the page text.
  An anchor that cannot be found, or is empty or whitespace only, leaves the
  span unresolved; no offset is guessed. An anchor or id of the wrong JSON
  type is a contract error, never a ``TypeError``; so is an array field that is
  not a list (ruling 30 a; null reads as empty).
- **Quote length** (PI 2026-11-04, display cap 200, also stated in the prompt):
  a quote, link passage or supporting text longer than ``QUOTE_MAX_CHARS`` is
  kept whole and flagged ``quote_over_cap``; code never truncates it.
- **Every free-text value has supporting text** (R-006, R-040). A value
  without it is not emitted as a value; it goes to ``rejected`` with its
  reason, so nothing the extractor said is lost.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from g3o.extract.anthropic_client import ExtractorResult
from g3o.extract.request_v27 import (
    DATE_ITEM,
    QUOTE_MAX_CHARS,
    Pass1Page,
    RequestPlan,
    field_name,
)

_TOP_KEYS = {"quotes", "links", "activities", "publication_date"}
_QUOTE_KEYS = {"task_id", "part_id", "quote"}
_LINK_KEYS = {"link_id", "part_id", "quote"}
_ACTIVITY_KEYS = {"part_id", "start_text", "end_text", "fields"}
_FIELD_KEYS = {"field", "value", "part_id", "supporting_text"}
_DATE_KEYS = {"value", "part_id", "supporting_text"}


class ExtractContractError(ValueError):
    """The extractor's answer is outside the v2.7 answer schema."""


@dataclass(frozen=True)
class QuoteSupport:
    task_id: str
    item_id: str
    chunk_id: str  # the part the quote was copied from (the producing part, or chrome)
    quote: str | None
    status: str  # "quoted" | "empty" | "no_entry" | "wrong_part"
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectedLink:
    link_id: str
    url: str
    chunk_id: str
    quote: str
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FieldValue:
    item_id: str
    value: str
    chunk_id: str
    supporting_text: str
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActivitySpan:
    activity_id: str
    chunk_id: str
    start: int | None  # offset from the start of the whole page
    end: int | None
    status: str  # "resolved" | "unresolved_start" | "unresolved_end"
    start_text: str
    end_text: str
    fields: tuple[FieldValue, ...] = ()


@dataclass(frozen=True)
class Rejected:
    kind: str
    reason: str
    raw: Any


@dataclass(frozen=True)
class Pass1Extraction:
    page_id: str
    custom_id: str
    quotes: tuple[QuoteSupport, ...]
    links: tuple[SelectedLink, ...]
    activities: tuple[ActivitySpan, ...]
    publication_date: FieldValue | None
    link_status: str | None
    rejected: tuple[Rejected, ...] = field(default_factory=tuple)
    response_model: str | None = None
    message_id: str | None = None
    request_id: str | None = None
    usage: dict[str, Any] | None = None


def _check_keys(obj: Any, allowed: set[str], where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ExtractContractError(f"{where}: expected an object")
    extra = set(obj) - allowed
    if extra:
        raise ExtractContractError(f"{where}: keys outside the answer schema: {sorted(extra)}")
    missing = allowed - set(obj)
    if missing:
        raise ExtractContractError(f"{where}: missing keys {sorted(missing)}")
    return obj


def _text_or_none(v: Any) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        raise ExtractContractError("text fields must be strings or null")
    return v if v.strip() else None


def _id_or_none(v: Any, where: str) -> str | None:
    """An id field (task, part, link, field name): a string or null, else a contract error
    (an unhashable value would otherwise raise ``TypeError`` on lookup)."""
    if v is None or isinstance(v, str):
        return v
    raise ExtractContractError(f"{where} must be a string or null")


def _array(v: Any, where: str) -> list[Any]:
    """An answer-schema array field: a JSON list, else a contract error (ruling 30 a), so a
    wrong shape such as ``"quotes": 5`` never leaks as a ``TypeError``. Null reads as empty,
    as before."""
    if v is None:
        return []
    if not isinstance(v, list):
        raise ExtractContractError(f"{where} must be an array, got {type(v).__name__}")
    return v


def _anchor(v: Any) -> str:
    if not isinstance(v, str):
        raise ExtractContractError("span anchors must be strings")
    return v


OVER_CAP_FLAG = "quote_over_cap"


def _flags(text: str | None) -> tuple[str, ...]:
    return (OVER_CAP_FLAG,) if text is not None and len(text) > QUOTE_MAX_CHARS else ()


def _ws_index(text: str) -> tuple[str, list[int]]:
    """Whitespace-collapsed copy of ``text`` and the original index of each char."""
    out: list[str] = []
    idx: list[int] = []
    prev_ws = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_ws:
                continue
            out.append(" ")
            idx.append(i)
            prev_ws = True
        else:
            out.append(ch)
            idx.append(i)
            prev_ws = False
    return "".join(out), idx


def _find(text: str, needle: str, lo: int, hi: int | None = None) -> tuple[int, int] | None:
    """Find ``needle`` in ``text`` starting in [lo, hi): exact first, then
    whitespace-insensitive. Returns (start, end) offsets in ``text``."""
    hi = len(text) if hi is None else hi
    i = text.find(needle, lo)
    if i != -1 and i < hi:
        return i, i + len(needle)
    collapsed, idx = _ws_index(text)
    n = re.sub(r"\s+", " ", needle.strip())
    if not n:
        return None
    # first collapsed position whose original index is >= lo
    start_c = next((k for k, o in enumerate(idx) if o >= lo), len(collapsed))
    j = collapsed.find(n, start_c)
    if j == -1 or idx[j] >= hi:
        return None
    return idx[j], idx[j + len(n) - 1] + 1


def resolve_span(page: Pass1Page, chunk_id: str, start_text: str, end_text: str
                 ) -> tuple[int | None, int | None, str]:
    """Full-page offsets for a span whose start anchor lies in ``chunk_id``."""
    chunk = page.chunk(chunk_id)
    # An empty or whitespace anchor names no place on the page: unresolved, never offset 0
    # or the first space (lane B F3).
    s = _find(page.text, start_text, chunk.start, chunk.end) if start_text.strip() else None
    if s is None:
        return None, None, "unresolved_start"
    e = _find(page.text, end_text, s[0]) if end_text.strip() else None
    if e is None or e[1] <= s[0]:
        return None, None, "unresolved_end"
    return s[0], e[1], "resolved"


def parse_pass1_result(result: ExtractorResult, page: Pass1Page, plan: RequestPlan) -> Pass1Extraction:
    if not result.success or not result.text:
        raise RuntimeError(f"extraction {result.custom_id!r} failed: {result.error}")
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise ExtractContractError(f"answer is not JSON: {exc}") from exc
    _check_keys(payload, _TOP_KEYS, "answer")

    part_ids = {c.chunk_id for c in page.chunks}
    rejected: list[Rejected] = []

    # -- quotes ------------------------------------------------------------
    tasks = {t.task_id: t for t in plan.quote_tasks}
    got: dict[str, QuoteSupport] = {}
    for raw in _array(payload["quotes"], "quotes"):
        _check_keys(raw, _QUOTE_KEYS, "quote")
        _id_or_none(raw["part_id"], "quote part_id")
        task = tasks.get(_id_or_none(raw["task_id"], "quote task_id"))
        if task is None:
            rejected.append(Rejected("quote", "unknown_task", raw))
            continue
        if task.task_id in got:
            rejected.append(Rejected("quote", "duplicate_task", raw))
            continue
        allowed = {task.chunk_id} | ({page.chrome_id} if task.allow_chrome else set())
        quote = _text_or_none(raw["quote"])
        if quote is not None and raw["part_id"] not in allowed:
            rejected.append(Rejected("quote", "wrong_part", raw))
            got[task.task_id] = QuoteSupport(task.task_id, task.item_id, task.chunk_id, None, "wrong_part")
            continue
        got[task.task_id] = QuoteSupport(
            task.task_id, task.item_id,
            raw["part_id"] if quote is not None else task.chunk_id,
            quote, "quoted" if quote is not None else "empty", _flags(quote),
        )
    quotes = tuple(
        got.get(t.task_id) or QuoteSupport(t.task_id, t.item_id, t.chunk_id, None, "no_entry")
        for t in plan.quote_tasks
    )

    # -- links -------------------------------------------------------------
    stored = {ln.link_id: ln for ln in plan.links}
    links: list[SelectedLink] = []
    seen_links: set[str] = set()
    for raw in _array(payload["links"], "links"):
        _check_keys(raw, _LINK_KEYS, "link")
        _id_or_none(raw["link_id"], "link_id")
        _id_or_none(raw["part_id"], "link part_id")
        if not plan.link_task:
            rejected.append(Rejected("link", "not_requested", raw))
            continue
        ln = stored.get(raw["link_id"])
        quote = _text_or_none(raw["quote"])
        if ln is None:
            rejected.append(Rejected("link", "unknown_link_id", raw))
        elif raw["link_id"] in seen_links:
            rejected.append(Rejected("link", "duplicate_link", raw))
        elif quote is None:
            rejected.append(Rejected("link", "no_supporting_text", raw))
        elif raw["part_id"] not in part_ids:
            rejected.append(Rejected("link", "unknown_part", raw))
        else:
            seen_links.add(ln.link_id)
            links.append(SelectedLink(ln.link_id, ln.url, raw["part_id"], quote, _flags(quote)))

    # -- activities --------------------------------------------------------
    wanted = {field_name(i): i for i in plan.activity_fields}
    activities: list[ActivitySpan] = []
    for raw in _array(payload["activities"], "activities"):
        _check_keys(raw, _ACTIVITY_KEYS, "activity")
        _id_or_none(raw["part_id"], "activity part_id")
        _anchor(raw["start_text"])
        _anchor(raw["end_text"])
        raw_fields = _array(raw["fields"], "activity fields")
        if not plan.activity_task:
            rejected.append(Rejected("activity", "not_requested", raw))
            continue
        if raw["part_id"] not in part_ids:
            rejected.append(Rejected("activity", "unknown_part", raw))
            continue
        start, end, status = resolve_span(page, raw["part_id"], raw["start_text"], raw["end_text"])
        values: list[FieldValue] = []
        seen_fields: set[str] = set()
        for fraw in raw_fields:
            _check_keys(fraw, _FIELD_KEYS, "field")
            _id_or_none(fraw["part_id"], "field part_id")
            item_id = wanted.get(_id_or_none(fraw["field"], "field name"))
            value = _text_or_none(fraw["value"])
            support = _text_or_none(fraw["supporting_text"])
            if item_id is None:
                rejected.append(Rejected("field", "not_requested", fraw))
            elif item_id in seen_fields:
                rejected.append(Rejected("field", "duplicate_field", fraw))
            elif value is None:
                seen_fields.add(item_id)  # recorded empty result: page does not state it
            elif support is None:
                rejected.append(Rejected("field", "no_supporting_text", fraw))
            elif fraw["part_id"] not in part_ids:
                rejected.append(Rejected("field", "unknown_part", fraw))
            else:
                seen_fields.add(item_id)
                values.append(FieldValue(item_id, value, fraw["part_id"], support, _flags(support)))
        activities.append(ActivitySpan(
            activity_id=f"{page.page_id}#a{len(activities) + 1:03d}",
            chunk_id=raw["part_id"], start=start, end=end, status=status,
            start_text=raw["start_text"], end_text=raw["end_text"], fields=tuple(values),
        ))

    # -- publication date ----------------------------------------------------
    date: FieldValue | None = None
    draw = payload["publication_date"]
    if draw is not None:
        _check_keys(draw, _DATE_KEYS, "publication_date")
        _id_or_none(draw["part_id"], "publication_date part_id")
        value, support = _text_or_none(draw["value"]), _text_or_none(draw["supporting_text"])
        if not plan.date_task:
            rejected.append(Rejected("publication_date", "not_requested", draw))
        elif value is None:
            pass
        elif support is None:
            rejected.append(Rejected("publication_date", "no_supporting_text", draw))
        elif draw["part_id"] not in part_ids:
            rejected.append(Rejected("publication_date", "unknown_part", draw))
        else:
            date = FieldValue(DATE_ITEM, value, draw["part_id"], support, _flags(support))

    return Pass1Extraction(
        page_id=page.page_id,
        custom_id=result.custom_id,
        quotes=quotes,
        links=tuple(links),
        activities=tuple(activities),
        publication_date=date,
        link_status=plan.link_status,
        rejected=tuple(rejected),
        response_model=result.response_model,
        message_id=result.message_id,
        request_id=result.request_id,
        usage=result.usage,
    )


__all__ = [
    "ActivitySpan",
    "ExtractContractError",
    "FieldValue",
    "OVER_CAP_FLAG",
    "Pass1Extraction",
    "QuoteSupport",
    "Rejected",
    "SelectedLink",
    "parse_pass1_result",
    "resolve_span",
]
