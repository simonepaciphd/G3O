"""Year candidates for the three v2.7 year items (T-064; RC-D-017 9a-e, "3 a").

Single candidate source for `core.year_announced`, `core.year_pilot_start` and `core.year_production_start`.
Pure and deterministic: text in, candidates out; no network, no state, no country or language input.

Forms (form id -> rule):
  literal     a four-digit ASCII year 2015-2030 not adjacent to another ASCII digit (the signed literal rule;
              unchanged by T-064).
  fiscal_one  a fiscal-year label that names one year ("FY2025", "FY 25", "FY'25", "fiscal year 2025",
              "fiscal 2025", "financial year 2025", "2025 fiscal year"): that year only (PI "3 a"). A bare
              trailing "FY" ("2025 FY") is not read as a marker.
  fiscal_two  a fiscal-year label that names two consecutive calendar years ("FY2024/25", "FY 2024-2025",
              "fiscal year 2024-25", "2024/25 financial year"): both years (PI "biii").

A label is fiscal only when it carries an English fiscal-year marker (FY, F.Y., fiscal year, fiscal, financial
year). Unmarked year ranges ("2019-2021", "2024/25") get no converted candidates; their four-digit years still
come through the literal rule. A marked label whose two years are not consecutive ("FY2024-26") gets no converted
candidates either (`fiscal_unruled` in `fiscal_labels`); both of these are open PI questions, not decisions.
Other calendars (Buddhist Era, ROC, Japanese era, Hijri, Solar Hijri) are out of scope (PI "9aiii").

Converted years outside 2015-2030 are dropped exactly like literal ones. Years are de-duplicated; every source
span is kept. Choosing among candidates, the no-publication-year-fallback rule and the earliest-year rule across
chunks belong to the caller (T-023/T-024), not to this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

YEAR_MIN = 2015
YEAR_MAX = 2030

LITERAL = "literal"
FISCAL_ONE = "fiscal_one"
FISCAL_TWO = "fiscal_two"
FISCAL_UNRULED = "fiscal_unruled"  # marked label, two years, not consecutive: no candidates until ruled
FORMS = (LITERAL, FISCAL_ONE, FISCAL_TWO)


@dataclass(frozen=True, order=True)
class YearSource:
    start: int  # offset into the input text (Python str index)
    end: int  # exclusive
    text: str  # verbatim text[start:end]
    form: str  # LITERAL | FISCAL_ONE | FISCAL_TWO


@dataclass(frozen=True)
class YearCandidate:
    year: int
    sources: tuple[YearSource, ...]  # sorted by (start, end, form)

    @property
    def forms(self) -> tuple[str, ...]:
        return tuple(sorted({s.form for s in self.sources}))


@dataclass(frozen=True)
class FiscalLabel:
    start: int
    end: int
    text: str
    kind: str  # FISCAL_ONE | FISCAL_TWO | FISCAL_UNRULED
    years: tuple[int, ...]  # calendar years the label names, before the 2015-2030 filter


# ---- patterns -------------------------------------------------------------------------------------------
# ASCII digits only: Python's \d also matches Arabic-Indic, Persian and full-width digits, which the literal
# rule does not name (open question, see SPIKE-T064.md).

_LITERAL = re.compile(r"(?<![0-9])([0-9]{4})(?![0-9])")

_SP = r"[  ]"
_SEP = rf"{_SP}?[-/‐-―]{_SP}?"
_Y4 = r"[0-9]{4}"
_Y2 = r"[0-9]{2}"
# A label must not run on into a further "/digits" or "-digits" (dates such as "FY 06/30/2024").
_END = rf"(?![0-9])(?!{_SEP}[0-9])"
# FY / F.Y. abbreviation: first year may be two digits ("FY25"); optional apostrophe ("FY'25").
_FY = r"\bF\.?Y\.?(?![A-Za-z])"
_YEARWORD = rf"\b(?:fiscal|financial){_SP}+year(?![A-Za-z])"
_WORD = rf"{_YEARWORD}|\bfiscal(?={_SP}+[0-9]{{4}}(?![0-9]))"

_PREFIX = re.compile(
    rf"(?:(?P<fy>{_FY})[  \-]?['’]?|(?P<word>{_WORD}){_SP}+)"
    rf"(?P<y1>{_Y4}|{_Y2})(?![0-9])(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?{_END}",
    re.IGNORECASE,
)
# Year(s) before a word marker ("2024-25 financial year", "2025 fiscal year"); four-digit first year. A bare
# trailing "FY" ("2024 FY") is not a marker: in tables such as "FY 2024 FY 2025" it belongs to the next year.
_POSTFIX = re.compile(
    rf"(?<![0-9])(?P<y1>{_Y4})(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?(?![0-9]){_SP}+{_YEARWORD}",
    re.IGNORECASE,
)


def _full_year(digits: str, base: int | None = None) -> int:
    if len(digits) == 4:
        return int(digits)
    yy = int(digits)
    century = (base // 100) * 100 if base is not None else 2000
    return century + yy


def in_range(year: int) -> bool:
    return YEAR_MIN <= year <= YEAR_MAX


def fiscal_labels(text: str) -> list[FiscalLabel]:
    """Every marked fiscal-year label in `text`, in text order, classified."""
    found: list[FiscalLabel] = []
    for rx in (_PREFIX, _POSTFIX):
        for m in rx.finditer(text):
            y1 = _full_year(m.group("y1"))
            y2s = m.group("y2")
            if y2s is None:
                kind, years = FISCAL_ONE, (y1,)
            else:
                y2 = _full_year(y2s, base=y1)
                kind = FISCAL_TWO if y2 == y1 + 1 else FISCAL_UNRULED
                years = (y1, y2)
            found.append(FiscalLabel(m.start(), m.end(), m.group(0), kind, years))
    found.sort(key=lambda f: (f.start, -(f.end - f.start)))
    out: list[FiscalLabel] = []
    for f in found:
        prev = out[-1] if out else None
        if prev and f.start < prev.end and f.kind == prev.kind and f.years == prev.years:
            # the same label read from both sides ("FY 2024-25 fiscal year"): one label, widest span
            if f.end > prev.end:
                out[-1] = FiscalLabel(prev.start, f.end, text[prev.start:f.end], f.kind, f.years)
            continue
        out.append(f)  # overlapping labels naming different years are both kept
    return out


def year_sources(text: str) -> list[tuple[int, YearSource]]:
    """Every (year, span, form) pair before de-duplication; years outside 2015-2030 already dropped."""
    pairs: set[tuple[int, YearSource]] = set()
    for m in _LITERAL.finditer(text):
        y = int(m.group(1))
        if in_range(y):
            pairs.add((y, YearSource(m.start(1), m.end(1), m.group(1), LITERAL)))
    for f in fiscal_labels(text):
        if f.kind == FISCAL_UNRULED:
            continue
        for y in f.years:
            if in_range(y):
                pairs.add((y, YearSource(f.start, f.end, f.text, f.kind)))
    return sorted(pairs)


def extract_year_candidates(text: str) -> list[YearCandidate]:
    """Year candidates for `text`, one per distinct year (ascending), each with every source span."""
    by_year: dict[int, list[YearSource]] = {}
    for y, src in year_sources(text):
        by_year.setdefault(y, []).append(src)
    return [YearCandidate(y, tuple(sorted(by_year[y]))) for y in sorted(by_year)]
