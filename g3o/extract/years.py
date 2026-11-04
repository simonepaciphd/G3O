"""Year candidates for the three v2.7 year items (T-064; RC-D-017 9a-e and "3 a"; PI chat 2026-11-04 "6 a", "7", "8 a").

Single candidate source for `core.year_announced`, `core.year_pilot_start` and `core.year_production_start`.
Pure and deterministic: text in, candidates out; no network, no state, no country or language input.

Forms (form id -> rule):
  literal       a four-digit ASCII year 2015-2030 not adjacent to another ASCII digit (the signed literal rule).
  fiscal_one    a fiscal-year label that names one year ("FY2025", "FY 25", "FY'25", "fiscal year 2025",
                "fiscal 2025", "financial year 2025", "2025 fiscal year"): that year only ("3 a"; "FY25" -> 2025
                confirmed "8 a"). A bare trailing "FY" ("2025 FY") is not read as a marker.
  fiscal_two    a fiscal-year label that names two consecutive calendar years ("FY2024/25", "FY 2024-2025",
                "fiscal year 2024-25", "2024/25 financial year"): both years ("biii").
  fiscal_range  a fiscal-year label whose two years are not consecutive ("FY2024-26", "FY 2022-2026"): the lower
                year only ("7 lower year").
  range_lower   an unmarked year range ("2024-25", "2019-2021", "2024/2025"): the lower year ("6 a just give the
                lower year"). The lower year is four-digit, so it is also a literal candidate; this form adds the
                range span as a source.

Upper years of ranges (PI chat 2026-11-04 "1b"): a range gives its lower year only, and the written upper
four-digit year ("2021" in "2019-2021", "2026" in "FY 2022-2026") is dropped: RANGES_LOWER_YEAR_ONLY = True drops
the literal source at the upper-year position of every unmarked range and every fiscal_range label (the year
survives if it is written elsewhere on the page). False restores the plain literal rule (every four-digit year). Consecutive fiscal labels
(fiscal_two) always give both years.

Range detection (unmarked): a four-digit first year 1900-2099, a separator (hyphen, slash, Unicode dashes U+2010 to
U+2015 incl. en and em dash, one optional space or NBSP each side; words such as "to" are not separators), then a four-digit or two-digit second year (two digits take the first year's
century) greater than the first, with no further "-digits" or "/digits" on either side (dates and chains such as
"2019-2020-2021" are not ranges). Text inside a fiscal label is not re-read as an unmarked range.

Other calendars and non-English fiscal markers are not converted (proposal pending, PI "9 b").
Converted years outside 2015-2030 are dropped exactly like literal ones. Years are de-duplicated; every source
span is kept. Choosing among candidates, the no-publication-year-fallback rule and the earliest-year rule across
chunks belong to the caller (T-023/T-024), not to this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

YEAR_MIN = 2015
YEAR_MAX = 2030

# PI chat 2026-11-04 "1b": a range gives its lower year only; its written upper year is dropped.
RANGES_LOWER_YEAR_ONLY = True

LITERAL = "literal"
FISCAL_ONE = "fiscal_one"
FISCAL_TWO = "fiscal_two"
FISCAL_RANGE = "fiscal_range"
RANGE_LOWER = "range_lower"
FORMS = (LITERAL, FISCAL_ONE, FISCAL_TWO, FISCAL_RANGE, RANGE_LOWER)
FISCAL_KINDS = (FISCAL_ONE, FISCAL_TWO, FISCAL_RANGE)


@dataclass(frozen=True, order=True)
class YearSource:
    start: int  # offset into the input text (Python str index)
    end: int  # exclusive
    text: str  # verbatim text[start:end]
    form: str  # one of FORMS


@dataclass(frozen=True)
class YearCandidate:
    year: int
    sources: tuple[YearSource, ...]  # sorted by (start, end, text, form)

    @property
    def forms(self) -> tuple[str, ...]:
        return tuple(sorted({s.form for s in self.sources}))


@dataclass(frozen=True)
class YearLabel:
    """A fiscal-year label (kind in FISCAL_KINDS) or an unmarked range (kind RANGE_LOWER)."""

    start: int
    end: int
    text: str
    kind: str
    years: tuple[int, ...]  # calendar years the label names, before the 2015-2030 filter
    upper_span: tuple[int, int] | None = None  # offsets of a four-digit upper-year token, if any

    @property
    def candidate_years(self) -> tuple[int, ...]:
        """Years this label contributes, before the 2015-2030 filter."""
        return self.years if self.kind in (FISCAL_ONE, FISCAL_TWO) else self.years[:1]


FiscalLabel = YearLabel  # name used by the first T-064 commit

# ---- patterns -------------------------------------------------------------------------------------------
# ASCII digits only: Python's \d also matches Arabic-Indic, Persian and full-width digits, which the literal
# rule does not name (proposal pending, PI "9 b"). Non-ASCII characters are built with chr() so the source
# stays ASCII.

_NBSP = chr(0x00A0)
_RSQUO = chr(0x2019)
_DASH = "[-/" + chr(0x2010) + "-" + chr(0x2015) + "]"
_SP = "[ " + _NBSP + "]"

_LITERAL = re.compile(r"(?<![0-9])([0-9]{4})(?![0-9])")

_SEP = rf"{_SP}?{_DASH}{_SP}?"
_Y4 = r"[0-9]{4}"
_Y2 = r"[0-9]{2}"
# A label must not run on into a further "/digits" or "-digits" (dates such as "FY 06/30/2024").
_END = rf"(?![0-9])(?!{_SEP}[0-9])"
# FY / F.Y. abbreviation: first year may be two digits ("FY25"); optional apostrophe ("FY'25").
_FY = r"\bF\.?Y\.?(?![A-Za-z])"
_YEARWORD = rf"\b(?:fiscal|financial){_SP}+year(?![A-Za-z])"
_WORD = rf"{_YEARWORD}|\bfiscal(?={_SP}+[0-9]{{4}}(?![0-9]))"

_PREFIX = re.compile(
    rf"(?:(?P<fy>{_FY})[ {_NBSP}\-]?['{_RSQUO}]?|(?P<word>{_WORD}){_SP}+)"
    rf"(?P<y1>{_Y4}|{_Y2})(?![0-9])(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?{_END}",
    re.IGNORECASE,
)
# Year(s) before a word marker ("2024-25 financial year", "2025 fiscal year"); four-digit first year. A bare
# trailing "FY" ("2024 FY") is not a marker: in tables such as "FY 2024 FY 2025" it belongs to the next year.
_POSTFIX = re.compile(
    rf"(?<![0-9])(?P<y1>{_Y4})(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?(?![0-9]){_SP}+{_YEARWORD}",
    re.IGNORECASE,
)
_RANGE = re.compile(
    rf"(?<![0-9])(?<![0-9]{_DASH})(?<![0-9]{_SP}{_DASH})(?P<y1>{_Y4}){_SEP}(?P<y2>{_Y4}|{_Y2}){_END}"
)


def _full_year(digits: str, base: int | None = None) -> int:
    if len(digits) == 4:
        return int(digits)
    yy = int(digits)
    century = (base // 100) * 100 if base is not None else 2000
    return century + yy


def in_range(year: int) -> bool:
    return YEAR_MIN <= year <= YEAR_MAX


def _upper(m: re.Match) -> tuple[int, int] | None:
    return m.span("y2") if m.group("y2") is not None and len(m.group("y2")) == 4 else None


def fiscal_labels(text: str) -> list[YearLabel]:
    """Every marked fiscal-year label in `text`, in text order, classified."""
    found: list[YearLabel] = []
    for rx in (_PREFIX, _POSTFIX):
        for m in rx.finditer(text):
            y1 = _full_year(m.group("y1"))
            y2s = m.group("y2")
            if y2s is None:
                kind, years = FISCAL_ONE, (y1,)
            else:
                y2 = _full_year(y2s, base=y1)
                kind = FISCAL_TWO if y2 == y1 + 1 else FISCAL_RANGE
                years = (y1, y2)
            found.append(YearLabel(m.start(), m.end(), m.group(0), kind, years, _upper(m)))
    found.sort(key=lambda f: (f.start, -(f.end - f.start)))
    out: list[YearLabel] = []
    for f in found:
        prev = out[-1] if out else None
        if prev and f.start < prev.end and f.kind == prev.kind and f.years == prev.years:
            # the same label read from both sides ("FY 2024-25 fiscal year"): one label, widest span
            if f.end > prev.end:
                out[-1] = YearLabel(prev.start, f.end, text[prev.start:f.end], f.kind, f.years,
                                    prev.upper_span or f.upper_span)
            continue
        out.append(f)  # overlapping labels naming different years are both kept
    return out


def year_ranges(text: str, fiscal: list[YearLabel] | None = None) -> list[YearLabel]:
    """Unmarked year ranges (kind RANGE_LOWER) that overlap no fiscal label, in text order."""
    if fiscal is None:
        fiscal = fiscal_labels(text)
    spans = [(f.start, f.end) for f in fiscal]
    out: list[YearLabel] = []
    for m in _RANGE.finditer(text):
        y1 = int(m.group("y1"))
        y2 = _full_year(m.group("y2"), base=y1)
        if not (1900 <= y1 <= 2099 and y2 > y1):
            continue
        if any(a < m.end() and m.start() < b for a, b in spans):
            continue
        out.append(YearLabel(m.start(), m.end(), m.group(0), RANGE_LOWER, (y1, y2), _upper(m)))
    return out


def year_sources(text: str, ranges_lower_year_only: bool | None = None) -> list[tuple[int, YearSource]]:
    """Every (year, span, form) pair before de-duplication; years outside 2015-2030 already dropped."""
    lower_only = RANGES_LOWER_YEAR_ONLY if ranges_lower_year_only is None else ranges_lower_year_only
    fiscal = fiscal_labels(text)
    labels = fiscal + year_ranges(text, fiscal)
    suppressed = set()
    if lower_only:
        suppressed = {lab.upper_span for lab in labels if lab.kind in (FISCAL_RANGE, RANGE_LOWER) and lab.upper_span}
    pairs: set[tuple[int, YearSource]] = set()
    for m in _LITERAL.finditer(text):
        y = int(m.group(1))
        if in_range(y) and m.span(1) not in suppressed:
            pairs.add((y, YearSource(m.start(1), m.end(1), m.group(1), LITERAL)))
    for lab in labels:
        for y in lab.candidate_years:
            if in_range(y):
                pairs.add((y, YearSource(lab.start, lab.end, lab.text, lab.kind)))
    return sorted(pairs)


def extract_year_candidates(text: str, ranges_lower_year_only: bool | None = None) -> list[YearCandidate]:
    """Year candidates for `text`, one per distinct year (ascending), each with every source span.

    `ranges_lower_year_only` overrides RANGES_LOWER_YEAR_ONLY for this call (None = use the module constant).
    """
    by_year: dict[int, list[YearSource]] = {}
    for y, src in year_sources(text, ranges_lower_year_only):
        by_year.setdefault(y, []).append(src)
    return [YearCandidate(y, tuple(sorted(by_year[y]))) for y in sorted(by_year)]
