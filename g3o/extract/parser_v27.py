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
  An anchor is looked for exactly, then up to whitespace, then up to Unicode
  form (NFKC, the quote check's form), then by the quote check's word rule
  (R-042: 80% of its words, here in the same order and place, and only when
  one place on the page qualifies). Every offset is an offset in the stored
  page text. An anchor that cannot be found, that fits two places under the
  word rule, or is empty or whitespace only, leaves the
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
import unicodedata
from bisect import bisect_left
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from g3o.common.support_check import _WORD, WORD_RULE_CUTOFF, word_tokens
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


def _joins_under(ch: str) -> bool:
    return unicodedata.category(ch)[0] == "M" or "ᅠ" <= ch <= "ᇿ"


def _joins_previous(ch: str) -> bool:
    """Can ``ch`` combine with the character before it under normalisation? Combining marks and
    the conjoining Hangul vowels and finals, and a character whose own NFKC form begins with one
    (the half-width kana voiced marks, the compatibility jamo vowels)."""
    return _joins_under(ch) or _joins_under(unicodedata.normalize("NFKC", ch)[:1] or ch)


def _nfkc_index(text: str) -> tuple[str, list[int], list[int]] | None:
    """NFKC copy of ``text`` and, for each of its characters, the start and the end in ``text`` of
    the original characters it stands for (a base character with what combines with it).

    None when the copy built piece by piece is not the NFKC form of the whole text: then no
    offset can be trusted and none is given."""
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    i, n = 0, len(text)
    while i < n:
        j = i + 1
        while j < n and _joins_previous(text[j]):
            j += 1
        piece = unicodedata.normalize("NFKC", text[i:j])
        out.append(piece)
        starts.extend([i] * len(piece))
        ends.extend([j] * len(piece))
        i = j
    norm = "".join(out)
    if norm != unicodedata.normalize("NFKC", text):
        return None
    return norm, starts, ends


@dataclass(frozen=True)
class _PageIndex:
    """What the Unicode-form and word steps read of one page text, built once per page."""
    norm: str  # NFKC copy of the page
    starts: list[int]  # per character of ``norm``: start in the page of the characters it stands for
    ends: list[int]  # ... and their end
    collapsed: str  # ``norm`` with whitespace runs as one space
    cidx: list[int]  # per character of ``collapsed``: its index in ``norm``
    cstarts: list[int]  # per character of ``collapsed``: its start in the page
    words: list[tuple[str, int, int]]  # the quote check's word tokens: (token, start, end in the page)
    wstarts: list[int]  # start in the page of each word


@lru_cache(maxsize=2)
def _page_index(text: str) -> _PageIndex | None:
    """The index of one page text; None when :func:`_nfkc_index` gives none. Kept for the last two
    page texts, so a page's anchors share one build."""
    built = _nfkc_index(text)
    if built is None:
        return None
    norm, starts, ends = built
    collapsed, cidx = _ws_index(norm)
    words = [(m.group().casefold(), starts[m.start()], ends[m.end() - 1]) for m in _WORD.finditer(norm)]
    return _PageIndex(norm, starts, ends, collapsed, cidx, [starts[o] for o in cidx], words, [w[1] for w in words])


_page_ws_index = lru_cache(maxsize=2)(_ws_index)


def _find_unicode_form(text: str, needle: str, lo: int, hi: int) -> tuple[int, int] | None:
    """``needle`` in ``text`` up to Unicode form (NFKC, as the quote check normalises, R-042) and
    whitespace. The offsets returned are offsets in ``text``; the match starts and ends at whole
    original characters, so ``text[start:end]`` is the needle under NFKC and whitespace."""
    n = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", needle).strip())
    index = _page_index(text) if n else None
    if index is None or not n:
        return None
    norm, starts, ends, idx = index.norm, index.starts, index.ends, index.cidx
    j = index.collapsed.find(n, bisect_left(index.cstarts, lo))
    while j != -1:
        a, b = idx[j], idx[j + len(n) - 1]
        if starts[a] >= hi:
            return None
        if (a == 0 or starts[a - 1] != starts[a]) and (b == len(norm) - 1 or starts[b + 1] != starts[b]):
            return starts[a], ends[b]
        j = index.collapsed.find(n, j + 1)
    return None


def _stands_on_page(text: str, needle: str) -> bool:
    """Does ``needle`` stand anywhere on the page as the first three steps of :func:`_find` read it:
    exactly, up to whitespace, or up to Unicode form?"""
    n = re.sub(r"\s+", " ", needle.strip())
    return (needle in text or (bool(n) and n in _page_ws_index(text)[0])
            or _find_unicode_form(text, needle, 0, len(text)) is not None)


def _find_by_words(text: str, needle: str, lo: int, hi: int, edge: str) -> tuple[int, int] | None:
    """``needle`` located by the quote check's word rule (R-042, RC-D-014 S1), made positional.

    The quote check accepts a quote when at least ``WORD_RULE_CUTOFF`` (80%) of its words are on
    the page. Here a place is a run of as many page words as the needle has (the quote check's
    word tokens: NFKC, casefold, punctuation dropped), and it qualifies when at least 80% of the
    words are equal position by position. That is narrower than the quote check, never wider.
    The place is returned only when it is the one qualifying place starting in [lo, hi) and the
    word whose offset is used is itself equal: the first word of a start anchor (``edge``
    "start"), the last word of an end anchor ("end"). Two qualifying places, or a differing edge
    word: None; no offset is guessed. The offsets are those of the first and the last word in
    ``text`` (punctuation around them is outside).

    The rule is for an anchor that stands nowhere on the page as written. When the anchor stands
    on the page outside [lo, hi), exactly, up to whitespace or up to Unicode form, no near copy
    inside the range is taken for it: None."""
    q = word_tokens(needle)
    index = _page_index(text) if q else None
    if index is None or not q or _stands_on_page(text, needle):
        return None
    words = index.words
    n = len(q)
    found: int | None = None
    for i in range(bisect_left(index.wstarts, lo), len(words) - n + 1):
        if words[i][1] >= hi:
            break
        if sum(words[i + k][0] == q[k] for k in range(n)) / n < WORD_RULE_CUTOFF:
            continue
        if found is not None:
            return None
        found = i
    if found is None:
        return None
    first, last = words[found], words[found + n - 1]
    if (first[0] != q[0]) if edge == "start" else (last[0] != q[-1]):
        return None
    return first[1], last[2]


def _find(text: str, needle: str, lo: int, hi: int | None = None, *, edge: str = "start"
          ) -> tuple[int, int] | None:
    """Find ``needle`` in ``text`` starting in [lo, hi): exact first, then whitespace-insensitive,
    then up to Unicode form (:func:`_find_unicode_form`), then by the quote check's word rule where
    one place qualifies and the anchor stands nowhere else on the page (:func:`_find_by_words`;
    ``edge`` names the offset the caller uses).
    Returns (start, end) offsets in ``text``. The first two steps are those of every earlier
    release, so an anchor they find keeps its offsets."""
    hi = len(text) if hi is None else hi
    i = text.find(needle, lo)
    if i != -1 and i < hi:
        return i, i + len(needle)
    collapsed, idx = _page_ws_index(text)
    n = re.sub(r"\s+", " ", needle.strip())
    if not n:
        return None
    # first collapsed position whose original index is >= lo
    j = collapsed.find(n, bisect_left(idx, lo))
    if j != -1 and idx[j] < hi:
        return idx[j], idx[j + len(n) - 1] + 1
    return _find_unicode_form(text, needle, lo, hi) or _find_by_words(text, needle, lo, hi, edge)


def resolve_span(page: Pass1Page, chunk_id: str, start_text: str, end_text: str
                 ) -> tuple[int | None, int | None, str]:
    """Full-page offsets for a span whose start anchor lies in ``chunk_id``."""
    chunk = page.chunk(chunk_id)
    # An empty or whitespace anchor names no place on the page: unresolved, never offset 0
    # or the first space (lane B F3).
    s = _find(page.text, start_text, chunk.start, chunk.end) if start_text.strip() else None
    if s is None:
        return None, None, "unresolved_start"
    e = _find(page.text, end_text, s[0], edge="end") if end_text.strip() else None
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
