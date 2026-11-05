"""Year candidates for the three v2.7 year items (T-064).

Rulings: RC-D-017 9a-e and "3 a"; PI chat 2026-11-04 "7", "8 a"; PI 2026-11-05 items 1-4 (ranges give both
ends, table A fiscal markers count like "FY", table B calendars, Unicode digits) and D1-D9 ("all as rec"; RC-D-018).
The 2026-11-05 range ruling reverses the "lower year only" rule of commit fd2ca89.

Single candidate source for `core.year_announced`, `core.year_pilot_start` and `core.year_production_start`.
Pure and deterministic: text in, candidates out; no network, no state, no country or language input.

Digits. Every Unicode decimal digit (category Nd: ASCII, Arabic-Indic, Persian, full-width, Thai, Devanagari, ...)
is read by its decimal value. Matching runs on a copy of the text where each such digit is replaced one-for-one by
its ASCII digit, so offsets are offsets into the original text and `YearSource.text` is the verbatim original.

Window. A year counts when it is in 2015-2030 (YEAR_MIN..YEAR_MAX), except the ends of a range (an unmarked range,
a two-year fiscal label, a marked Buddhist Era range), which count anywhere in LIFT_MIN..LIFT_MAX (1900-2099, D1: a
guard so that codes and other calendars' years are not read as ranges). Two-digit fiscal ends are lifted like
four-digit ones (D2; a two-digit start expands to 20xx).

Forms (YearSource.form):
  literal         a four-digit year 2015-2030 not adjacent to another digit (the signed literal rule).
  fiscal_one      a fiscal-year label naming one year: English "FY2025", "FY 25", "FY'25", "fiscal year 2025",
                  "fiscal 2025", "financial year 2025", "2025 fiscal year" ("8 a": FY25 -> 2025), or a table A
                  marker (below) with one year. Window 2015-2030.
  fiscal_lower    the first year of a fiscal-year label naming two years ("FY2024/25", "FY2024-26",
  fiscal_upper    "FY 2022-2026", "Haushaltsjahr 2025/2026", "2024-25年度"): both years, consecutive or not,
                  window lifted (D2). A two-digit end takes the first year's century ("FY2030/31" -> 2030, 2031;
                  "FY13/14" -> 2013, 2014).
  range_lower     the ends of an unmarked range of two four-digit years 1900-2099, the second greater than the
  range_upper     first ("2014-2020", "2019 - 2021", "2020/2022", en or em dash), or joined by the whole word
                  "to", "through" or "until" with single spaces, case-insensitive (D9: "2010 to 2020"). Lifted
                  window. When a numbering word stands just before the range (p., pp., page, ID, No., #, art., §;
                  case-insensitive), the ends keep the 2015-2030 window. An unmarked two-digit end is not a range
                  end ("2024-25" -> 2024 only, as a literal). A range lying wholly inside a fiscal or calendar
                  label is left to that label; one that only starts inside it ("FY 2010 to 2020") is kept.
  era_jp          Japanese era with its name: 令和N年 (Reiwa N = 2018 + N, 令和元年 = 2019), 平成N年 (Heisei N =
                  1988 + N); ASCII, full-width or kanji numerals; also matches inside 令和6年度. Window 2015-2030.
  buddhist_era    Buddhist Era with an explicit marker, พ.ศ. or B.E., before or after the year (D6: "พ.ศ. 2567",
                  "2567 B.E.", "2567 พ.ศ."): CE = BE - 543, window 2015-2030. A marked BE range
                  ("พ.ศ. 2566-2567") converts both years, lifted like other range ends.
  roc             ROC / Minguo with 民國 or 民国: 民國N年, CE = 1911 + N.

Table A fiscal markers (count exactly like "FY": one year -> that year, two years -> both; no month arithmetic):
  before the year: Haushaltsjahr, Geschäftsjahr, Rechnungsjahr, Wirtschaftsjahr, Doppelhaushalt; exercice
  budgétaire, exercice financier, exercice fiscal, année fiscale, année budgétaire; ejercicio fiscal, ejercicio
  presupuestario, año fiscal; anno fiscale, esercizio finanziario; exercício financeiro, exercício fiscal, ano
  fiscal; begrotingsjaar, boekjaar; 회계연도; ปีงบประมาณ (Thai; a year of 2400 or more is Buddhist Era and is
  converted, CE = BE - 543, before the rules above; an optional พ.ศ. after the marker is allowed).
  after the year: 年度, 财年, 財年, 财政年度, 財政年度, 会计年度, 會計年度, 회계연도.

Out of scope, not converted and untested: Japanese era abbreviations (R6, H30), Hijri (AH, هـ), Solar Hijri
(ه.ش, هجری شمسی), other eras (昭和 ...), bare "BE", the table A row A11 languages (ar, fa, ru, hi, id, vi, tr) and
inflected or unaccented marker spellings. A Solar Hijri or Hijri year written in Persian or Arabic-Indic digits is
read as its digit value and falls outside both windows.

Years are de-duplicated; every source span is kept. Choosing among candidates, the no-publication-year-fallback
rule and the earliest-year rule across chunks belong to the caller (T-023/T-024), not to this module.
Non-ASCII characters in the patterns themselves are built with chr(); only this docstring holds them literally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

YEAR_MIN = 2015
YEAR_MAX = 2030
LIFT_MIN = 1900
LIFT_MAX = 2099
BE_OFFSET = 543
BE_THRESHOLD = 2400  # Thai fiscal-year labels: a written year >= this is Buddhist Era
ROC_OFFSET = 1911
REIWA_OFFSET = 2018
HEISEI_OFFSET = 1988

LITERAL = "literal"
FISCAL_ONE = "fiscal_one"
FISCAL_LOWER = "fiscal_lower"
FISCAL_UPPER = "fiscal_upper"
RANGE_LOWER = "range_lower"
RANGE_UPPER = "range_upper"
ERA_JP = "era_jp"
BUDDHIST_ERA = "buddhist_era"
ROC = "roc"
FORMS = (LITERAL, FISCAL_ONE, FISCAL_LOWER, FISCAL_UPPER, RANGE_LOWER, RANGE_UPPER, ERA_JP, BUDDHIST_ERA, ROC)

# YearLabel kinds
FISCAL_TWO = "fiscal_two"
RANGE = "range"
LABEL_KINDS = (FISCAL_ONE, FISCAL_TWO, RANGE, ERA_JP, BUDDHIST_ERA, ROC)


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
    """A fiscal-year label, an unmarked range, or a calendar-era expression."""

    start: int
    end: int
    text: str  # verbatim original text
    kind: str  # one of LABEL_KINDS
    years: tuple[int, ...]  # converted calendar years named, before any window
    four_digit: tuple[bool, ...]  # per year: written with four digits (recorded only; D2 lifts two-digit ends too)
    marker: str = ""  # the marker matched (FY, a table A marker, era name ...), "" for ranges
    numbered: bool = False  # RANGE only: a numbering word stands just before it

    def sources(self) -> list[tuple[int, YearSource]]:
        """(year, source) pairs this label contributes, windows applied."""
        out = []
        if self.kind in (FISCAL_TWO, RANGE):
            forms = (FISCAL_LOWER, FISCAL_UPPER) if self.kind == FISCAL_TWO else (RANGE_LOWER, RANGE_UPPER)
            for y, form in zip(self.years, forms, strict=False):
                if in_range(y) or (not self.numbered and LIFT_MIN <= y <= LIFT_MAX):
                    out.append((y, YearSource(self.start, self.end, self.text, form)))
        elif len(self.years) == 2:  # marked Buddhist Era range: both years, lifted like range ends
            for y in self.years:
                if in_range(y) or LIFT_MIN <= y <= LIFT_MAX:
                    out.append((y, YearSource(self.start, self.end, self.text, self.kind)))
        else:
            y = self.years[0]
            if in_range(y):
                out.append((y, YearSource(self.start, self.end, self.text, self.kind)))
        return out


# ---- patterns (run on the digit-normalized copy) --------------------------------------------------------

def _u(*cps: int) -> str:
    return "".join(chr(c) for c in cps)


_NBSP = chr(0x00A0)
_IDSP = chr(0x3000)
_RSQUO = chr(0x2019)
_DASH = "[-/" + chr(0x2010) + "-" + chr(0x2015) + "]"
_SP = "[ " + _NBSP + "]"
_CJKSP = "[ " + _NBSP + _IDSP + "]"
_SEP = rf"{_SP}?{_DASH}{_SP}?"
_Y4 = r"[0-9]{4}"
_Y2 = r"[0-9]{2}"
# A label must not run on into a further "/digits" or "-digits" (dates such as "FY 06/30/2024").
_END = rf"(?![0-9])(?!{_SEP}[0-9])"
_TWO = rf"(?P<y1>{_Y4})(?![0-9])(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?{_END}"

_LITERAL = re.compile(r"(?<![0-9])([0-9]{4})(?![0-9])")

# English FY / fiscal / financial (unchanged): first year may be two digits after FY ("FY25").
_FY = r"\bF\.?Y\.?(?![A-Za-z])"
_YEARWORD = rf"\b(?:fiscal|financial){_SP}+year(?![A-Za-z])"
_WORD = rf"{_YEARWORD}|\bfiscal(?={_SP}+[0-9]{{4}}(?![0-9]))"
_EN_PREFIX = re.compile(
    rf"(?:(?P<m>{_FY})[ {_NBSP}\-]?['{_RSQUO}]?|(?P<w>{_WORD}){_SP}+)"
    rf"(?P<y1>{_Y4}|{_Y2})(?![0-9])(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?{_END}",
    re.IGNORECASE,
)
_EN_POSTFIX = re.compile(
    rf"(?<![0-9])(?P<y1>{_Y4})(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?(?![0-9]){_SP}+(?P<m>{_YEARWORD})",
    re.IGNORECASE,
)

# Table A markers. Latin-script markers are word-bounded and need a space before the year.
_a, _e, _i, _ntilde = chr(0xE4), chr(0xE9), chr(0xED), chr(0xF1)
_LATIN_PREFIX = (
    "Haushaltsjahr", f"Gesch{_a}ftsjahr", "Rechnungsjahr", "Wirtschaftsjahr", "Doppelhaushalt",
    f"exercice budg{_e}taire", "exercice financier", "exercice fiscal", f"ann{_e}e fiscale", f"ann{_e}e budg{_e}taire",
    "ejercicio fiscal", "ejercicio presupuestario", f"a{_ntilde}o fiscal",
    "anno fiscale", "esercizio finanziario",
    f"exerc{_i}cio financeiro", f"exerc{_i}cio fiscal", "ano fiscal",
    "begrotingsjaar", "boekjaar",
)
_KO_HOEGYE = _u(0xD68C, 0xACC4, 0xC5F0, 0xB3C4)  # hoegye yeondo
_CJK_POSTFIX = (
    _u(0x5E74, 0x5EA6),  # nendo
    _u(0x8D22, 0x5E74), _u(0x8CA1, 0x5E74),  # cainian (simplified, traditional)
    _u(0x8D22, 0x653F, 0x5E74, 0x5EA6), _u(0x8CA1, 0x653F, 0x5E74, 0x5EA6),  # caizheng niandu
    _u(0x4F1A, 0x8BA1, 0x5E74, 0x5EA6), _u(0x6703, 0x8A08, 0x5E74, 0x5EA6),  # kuaiji niandu
    _KO_HOEGYE,
)


def _alt(words) -> str:
    return "|".join(re.escape(w).replace(r"\ ", f"{_SP}+") for w in sorted(words, key=len, reverse=True))


_A_PREFIX = re.compile(
    rf"(?:\b(?P<m>{_alt(_LATIN_PREFIX)})(?![^\W\d_]){_SP}+|(?P<k>{_KO_HOEGYE}){_CJKSP}*){_TWO}",
    re.IGNORECASE,
)
_A_POSTFIX = re.compile(
    rf"(?<![0-9])(?P<y1>{_Y4})(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?(?![0-9]){_CJKSP}?(?P<m>{_alt(_CJK_POSTFIX)})"
)
_TH_FISCAL = _u(0x0E1B, 0x0E35, 0x0E07, 0x0E1A, 0x0E1B, 0x0E23, 0x0E30, 0x0E21, 0x0E32, 0x0E13)  # pi ngop praman
_TH_BE = _u(0x0E1E) + r"\." + f"{_SP}?" + _u(0x0E28) + r"\."  # pho so (Buddhist Era)
_A_THAI = re.compile(rf"(?P<m>{_TH_FISCAL}){_SP}*(?:{_TH_BE}{_SP}*)?{_TWO}")

# Table B calendars.
_KANJI_DIGITS = {_u(0x3007): 0, _u(0x96F6): 0, _u(0x4E00): 1, _u(0x4E8C): 2, _u(0x4E09): 3, _u(0x56DB): 4,
                 _u(0x4E94): 5, _u(0x516D): 6, _u(0x4E03): 7, _u(0x516B): 8, _u(0x4E5D): 9}
_KANJI_TEN, _KANJI_HUNDRED, _GAN = _u(0x5341), _u(0x767E), _u(0x5143)  # ten, hundred, "first" (gan-nen)
_KANJI = "[" + "".join(_KANJI_DIGITS) + _KANJI_TEN + _KANJI_HUNDRED + "]"
_NEN = _u(0x5E74)  # year
_REIWA, _HEISEI = _u(0x4EE4, 0x548C), _u(0x5E73, 0x6210)
_ERA = re.compile(
    rf"(?P<era>{_REIWA}|{_HEISEI}){_CJKSP}?(?P<n>{_GAN}|[0-9]{{1,2}}(?![0-9])|{_KANJI}{{1,3}}){_CJKSP}?{_NEN}"
)
_MINGUO = _u(0x6C11) + "[" + _u(0x570B, 0x56FD) + "]"  # Minguo, traditional or simplified
_ROC_RX = re.compile(rf"(?P<era>{_MINGUO}){_CJKSP}?(?P<n>[0-9]{{1,3}}(?![0-9])|{_KANJI}{{1,5}}){_CJKSP}?{_NEN}")
_BE_MARK = rf"{_TH_BE}|\bB\.{_SP}?E\."
_BE_PREFIX = re.compile(rf"(?P<era>{_BE_MARK}){_SP}?{_TWO}")
_BE_POSTFIX = re.compile(
    rf"(?<![0-9])(?P<y1>{_Y4})(?:{_SEP}(?P<y2>{_Y4}|{_Y2}))?(?![0-9]){_SP}?(?P<era>{_BE_MARK})"
)

_RANGE_WORD = r" (?i:to|through|until) "
_RANGE_RX = re.compile(
    rf"(?<![0-9])(?<![0-9]{_DASH})(?<![0-9]{_SP}{_DASH})(?P<y1>{_Y4})(?:{_SEP}|{_RANGE_WORD})(?P<y2>{_Y4}){_END}"
)
_NUMBERING = re.compile(r"(?:\bpp?\.|\bpage|\bID|\bNo\.|#|\bart\.|" + chr(0xA7) + rf"){_SP}*$", re.IGNORECASE)


# ---- helpers --------------------------------------------------------------------------------------------

def in_range(year: int) -> bool:
    return YEAR_MIN <= year <= YEAR_MAX


def normalize_digits(text: str) -> str:
    """Replace every non-ASCII Unicode decimal digit by its ASCII digit, one character for one."""
    if text.isascii():
        return text
    return "".join(str(int(ch)) if (not ch.isascii() and ch.isdecimal()) else ch for ch in text)


def _full_year(digits: str, base: int | None = None) -> int:
    if len(digits) == 4:
        return int(digits)
    yy = int(digits)
    if base is None:
        return 2000 + yy
    y = (base // 100) * 100 + yy
    return y + 100 if y < base else y  # "FY1999/00" -> 2000; a lower two-digit end rolls into the next century


def _kanji_number(s: str) -> int:
    if s.isdigit():
        return int(s)
    if s == _GAN:
        return 1
    if _KANJI_TEN in s or _KANJI_HUNDRED in s:
        total = cur = 0
        for ch in s:
            if ch == _KANJI_HUNDRED:
                total, cur = total + (cur or 1) * 100, 0
            elif ch == _KANJI_TEN:
                total, cur = total + (cur or 1) * 10, 0
            else:
                cur = _KANJI_DIGITS[ch]
        return total + cur
    return int("".join(str(_KANJI_DIGITS[ch]) for ch in s))


def _two_year_label(text: str, m: re.Match, marker: str, be: bool = False) -> YearLabel:
    y1s, y2s = m.group("y1"), m.group("y2")
    y1 = _full_year(y1s)
    conv = BE_OFFSET if be and y1 >= BE_THRESHOLD else 0
    span = text[m.start():m.end()]
    if y2s is None:
        return YearLabel(m.start(), m.end(), span, FISCAL_ONE, (y1 - conv,), (len(y1s) == 4,), marker)
    y2 = _full_year(y2s, base=y1)
    return YearLabel(m.start(), m.end(), span, FISCAL_TWO, (y1 - conv, y2 - conv),
                     (len(y1s) == 4, len(y2s) == 4), marker)


def fiscal_labels(text: str, _norm: str | None = None) -> list[YearLabel]:
    """Every marked fiscal-year label (English or table A) in `text`, in text order."""
    norm = normalize_digits(text) if _norm is None else _norm
    found: list[YearLabel] = []
    for rx in (_EN_PREFIX, _EN_POSTFIX, _A_PREFIX, _A_POSTFIX):
        for m in rx.finditer(norm):
            marker = next((g for g in (m.groupdict().get(k) for k in ("m", "w", "k")) if g), "")
            found.append(_two_year_label(text, m, marker))
    for m in _A_THAI.finditer(norm):
        found.append(_two_year_label(text, m, m.group("m"), be=True))
    found.sort(key=lambda f: (f.start, -(f.end - f.start)))
    out: list[YearLabel] = []
    for f in found:
        prev = out[-1] if out else None
        if prev and f.start < prev.end and f.kind == prev.kind and f.years == prev.years:
            # the same label read from both sides ("FY 2024-25 fiscal year"): one label, widest span
            if f.end > prev.end:
                out[-1] = YearLabel(prev.start, f.end, text[prev.start:f.end], f.kind, f.years, f.four_digit,
                                    prev.marker)
            continue
        out.append(f)  # overlapping labels naming different years are both kept
    return out


def calendar_labels(text: str, _norm: str | None = None) -> list[YearLabel]:
    """Japanese era, Buddhist Era and ROC expressions, in text order (table B, one year each)."""
    norm = normalize_digits(text) if _norm is None else _norm
    out: list[YearLabel] = []
    for m in _ERA.finditer(norm):
        y = _kanji_number(m.group("n")) + (REIWA_OFFSET if m.group("era") == _REIWA else HEISEI_OFFSET)
        out.append(YearLabel(m.start(), m.end(), text[m.start():m.end()], ERA_JP, (y,), (False,), m.group("era")))
    be: list[YearLabel] = []
    for rx in (_BE_PREFIX, _BE_POSTFIX):
        for m in rx.finditer(norm):
            y1 = int(m.group("y1"))
            ys = (y1,) if m.group("y2") is None else (y1, _full_year(m.group("y2"), base=y1))
            be.append(YearLabel(m.start(), m.end(), text[m.start():m.end()], BUDDHIST_ERA,
                                tuple(y - BE_OFFSET for y in ys), tuple(True for _ in ys), m.group("era")))
    be.sort(key=lambda f: (f.start, -(f.end - f.start)))
    kept: list[YearLabel] = []
    for f in be:  # the same year read with a marker on both sides: keep one
        if kept and f.start < kept[-1].end and f.years == kept[-1].years:
            continue
        kept.append(f)
    out.extend(kept)
    for m in _ROC_RX.finditer(norm):
        y = _kanji_number(m.group("n")) + ROC_OFFSET
        out.append(YearLabel(m.start(), m.end(), text[m.start():m.end()], ROC, (y,), (False,), m.group("era")))
    return sorted(out, key=lambda f: (f.start, f.end))


def year_ranges(text: str, labels: list[YearLabel] | None = None, _norm: str | None = None) -> list[YearLabel]:
    """Unmarked ranges of two four-digit years (kind RANGE) not wholly inside another label, in text order."""
    norm = normalize_digits(text) if _norm is None else _norm
    if labels is None:
        labels = fiscal_labels(text, norm) + calendar_labels(text, norm)
    spans = [(f.start, f.end) for f in labels]
    out: list[YearLabel] = []
    for m in _RANGE_RX.finditer(norm):
        y1, y2 = int(m.group("y1")), int(m.group("y2"))
        if not (LIFT_MIN <= y1 < y2 <= LIFT_MAX):
            continue
        if any(a <= m.start() and m.end() <= b for a, b in spans):
            continue
        numbered = bool(_NUMBERING.search(norm[max(0, m.start() - 12):m.start()]))
        out.append(YearLabel(m.start(), m.end(), text[m.start():m.end()], RANGE, (y1, y2), (True, True), "", numbered))
    return out


def all_labels(text: str) -> list[YearLabel]:
    """Every fiscal label, calendar expression and unmarked range, in text order."""
    norm = normalize_digits(text)
    labels = fiscal_labels(text, norm) + calendar_labels(text, norm)
    return sorted(labels + year_ranges(text, labels, norm), key=lambda f: (f.start, f.end))


def year_sources(text: str) -> list[tuple[int, YearSource]]:
    """Every (year, span, form) pair before de-duplication, windows applied."""
    norm = normalize_digits(text)
    pairs: set[tuple[int, YearSource]] = set()
    for m in _LITERAL.finditer(norm):
        y = int(m.group(1))
        if in_range(y):
            pairs.add((y, YearSource(m.start(1), m.end(1), text[m.start(1):m.end(1)], LITERAL)))
    labels = fiscal_labels(text, norm) + calendar_labels(text, norm)
    for lab in labels + year_ranges(text, labels, norm):
        pairs.update(lab.sources())
    return sorted(pairs)


def extract_year_candidates(text: str) -> list[YearCandidate]:
    """Year candidates for `text`, one per distinct year (ascending), each with every source span."""
    by_year: dict[int, list[YearSource]] = {}
    for y, src in year_sources(text):
        by_year.setdefault(y, []).append(src)
    return [YearCandidate(y, tuple(sorted(by_year[y]))) for y in sorted(by_year)]
