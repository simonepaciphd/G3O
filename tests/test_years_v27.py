"""T-064 year candidates: RC-D-017 9a-e, "3 a"; PI 2026-11-04 "7", "8 a"; PI 2026-11-05 items 1-4.

Synthetic strings only (DP-064e)."""

from __future__ import annotations

import pytest

from g3o.extract import years as Y
from g3o.extract.years import (
    BUDDHIST_ERA,
    ERA_JP,
    FISCAL_LOWER,
    FISCAL_ONE,
    FISCAL_TWO,
    FISCAL_UPPER,
    LITERAL,
    RANGE,
    RANGE_LOWER,
    RANGE_UPPER,
    ROC,
    all_labels,
    extract_year_candidates,
    fiscal_labels,
    year_ranges,
)

REF = 2026  # explicit reference year for the two-digit pivot (PI 2026-11-05 "B1c"); never the call-time default


def years(text: str) -> list[int]:
    return [c.year for c in extract_year_candidates(text, reference_year=REF)]


def forms_of(text: str, year: int) -> set[str]:
    return {s.form for c in extract_year_candidates(text, reference_year=REF) if c.year == year for s in c.sources}


def test_no_lower_year_switch_left():
    assert not hasattr(Y, "RANGES_LOWER_YEAR_ONLY")


def test_every_source_is_verbatim():
    text = "FY 2022-2026, 令和元年, พ.ศ. ๒๕๖๗, 民國113年, ２０２４, 2014-2020."
    for c in extract_year_candidates(text, reference_year=REF):
        for s in c.sources:
            assert text[s.start:s.end] == s.text


# ---- PI 2026-11-05 spot cases ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("2014-2020", [2014, 2020]),
    ("FY 2022-2026", [2022, 2026]),
    ("2010-2020", [2010, 2020]),
    ("FY2024/25", [2024, 2025]),
    ("FY2024-26", [2024, 2026]),
    ("2024-25", [2024]),
    ("2020 to 2022", [2020, 2022]),
    ("pp. 1998-2020", [2020]),
    ("FY25", [2025]),
])
def test_spot_cases(text, expected):
    assert years(text) == expected


# ---- literal --------------------------------------------------------------------------------------------

def test_literal_positive_and_spans():
    text = "Announced in 2019, piloted 2021."
    cands = extract_year_candidates(text, reference_year=REF)
    assert [c.year for c in cands] == [2019, 2021]
    for c in cands:
        (s,) = c.sources
        assert s.form == LITERAL and s.text == str(c.year)


def test_literal_negative():
    assert years("Population 120150, code 20251, ref 1999 and 2031.") == []


@pytest.mark.parametrize("text,expected", [("2014", []), ("2015", [2015]), ("2030", [2030]), ("2031", [])])
def test_literal_range_edges(text, expected):
    assert years(text) == expected


def test_standalone_years_keep_window():
    assert years("in 2010, then 2014 and 2031") == []


@pytest.mark.parametrize("text,expected", [
    ("٢٠٢٤", [2024]),          # Arabic-Indic
    ("۲۰۲۴", [2024]),          # Persian
    ("２０２４年", [2024]),     # full-width
    ("๒๐๒๔", [2024]),          # Thai digits, Gregorian value
    ("२०२४", [2024]),          # Devanagari
    ("٢٠١٤", []),              # window kept
    ("۱۴۰۳", []),              # Solar Hijri value read as 1403: outside both windows
])
def test_unicode_digits_are_literal_years(text, expected):
    assert years(text) == expected
    for c in extract_year_candidates(text, reference_year=REF):
        assert all(s.text == text[s.start:s.end] for s in c.sources)


def test_unicode_digit_range():
    assert years("٢٠١٤-٢٠٢٠") == [2014, 2020]


# ---- English fiscal labels ------------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["FY2025", "FY 2025", "FY-2025", "F.Y. 2025", "FY25", "FY'25", "fy25",
                                   "fiscal year 2025", "Fiscal 2025", "financial year 2025", "2025 fiscal year"])
def test_fiscal_one_positive(label):
    text = f"Budget for {label} approved."
    assert years(text) == [2025]
    assert FISCAL_ONE in forms_of(text, 2025)


@pytest.mark.parametrize("text", ["FYI 2025", "fiscal policy 2025", "MFY25", "fiscal 25 states", "FY"])
def test_fiscal_one_negative(text):
    assert all(f.kind != FISCAL_ONE for f in fiscal_labels(text, reference_year=REF))


@pytest.mark.parametrize("text,expected", [("FY14", [2014]), ("FY15", [2015]), ("FY30", [2030]), ("FY31", [2031]),
                                           ("FY 2014", [2014]), ("FY2012", [2012]), ("FY 1900", [1900]),
                                           ("fiscal year 2099", [2099]), ("FY98", [1998])])
def test_fiscal_one_lifted_window_c2b(text, expected):
    # PI 2026-11-05 "C2b": one-year labels are lifted to 1900-2099 like two-year labels. Two-digit "FY98" pivots to
    # 1998 at REF 2026 ("B1c").
    assert years(text) == expected
    assert FISCAL_ONE in forms_of(text, expected[0])


@pytest.mark.parametrize("text", ["FY 1899", "fiscal year 2100", "Rechnungsjahr 1850", "1899年度"])
def test_fiscal_one_outside_guard_dropped(text):
    assert years(text) == []
    assert [f.kind for f in fiscal_labels(text, reference_year=REF)] == [FISCAL_ONE]


def test_c2b_leaves_literal_window_unchanged():
    assert years("In 2012 and 2031, then FY2012.") == [2012]
    assert forms_of("In 2012 and 2031, then FY2012.", 2012) == {FISCAL_ONE}


@pytest.mark.parametrize("label", ["FY2024/25", "FY 2024-25", "FY2024-2025", "FY 2024/2025", "FY24/25",
                                   "FY 2024–25", "fiscal year 2024-25", "financial year 2024/2025",
                                   "2024-25 financial year", "2024/25 fiscal year", "FY 2024-25 fiscal year"])
def test_fiscal_two_positive(label):
    text = f"Plan for {label}."
    assert years(text) == [2024, 2025]
    assert FISCAL_LOWER in forms_of(text, 2024) and FISCAL_UPPER in forms_of(text, 2025)
    (lab,) = fiscal_labels(text, reference_year=REF)
    assert lab.kind == FISCAL_TWO and lab.years == (2024, 2025)


def test_fiscal_two_nonconsecutive_gives_both():
    (lab,) = fiscal_labels("FY2024-26 programme", reference_year=REF)
    assert lab.kind == FISCAL_TWO and lab.years == (2024, 2026)
    assert years("FY 2022-2026 Consolidated Plan") == [2022, 2026]


@pytest.mark.parametrize("text,expected", [
    ("FY2014/15", [2014, 2015]),    # four-digit end lifted
    ("FY2010-2020", [2010, 2020]),
    ("FY2030/31", [2030, 2031]),    # two-digit end lifted too
    ("FY13/14", [2013, 2014]),      # D2: two-digit start expands to 20xx, lifted
    ("FY 1899-1900", [1900]),       # D1 guard
    ("FY2099/00", [2000, 2099]),    # r13: "00" is 2000 by the pivot, no carry-over
    ("FY1999/00", [1999, 2000]),
    ("FY 2024-06", [2006, 2024]),   # r13: "06" is 2006 (before the start year; both kept)
])
def test_fiscal_two_windows(text, expected):
    assert years(text) == expected


def test_fiscal_two_negative():
    assert fiscal_labels("2024/25", reference_year=REF) == []


# ---- unmarked ranges ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("2019-2021", [2019, 2021]),
    ("2019 - 2021", [2019, 2021]),
    ("2020–2022", [2020, 2022]),      # en dash
    ("2020—2022", [2020, 2022]),      # em dash
    ("2020/2022", [2020, 2022]),
    ("1998-2020", [1998, 2020]),
    ("1900-1950", [1900, 1950]),
    ("2014-2016 and 2031", [2014, 2016]),
])
def test_range_both_ends_lifted(text, expected):
    assert years(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("1899-2020", [2020]),       # D1 bound per end (PI R-3 b): 1899 dropped, 2020 kept
    ("2020-2100", [2020]),       # 2100 dropped
    ("1900-2099", [1900, 2099]),
    ("1850-2010", [2010]),       # PI R-3 b: the in-bound end is lifted on its own
    ("1899-1905", [1905]),
    ("2095-2100", [2095]),
    ("1850-1899", []),           # neither end in the bound: no range
])
def test_range_guard(text, expected):
    assert years(text) == expected


@pytest.mark.parametrize("text,form", [("1850-2010", RANGE_UPPER), ("1899-1905", RANGE_UPPER),
                                       ("2095-2100", RANGE_LOWER)])
def test_range_guard_each_end_keeps_its_form(text, form):
    (c,) = extract_year_candidates(text, reference_year=REF)
    assert [s.form for s in c.sources] == [form]
    assert c.sources[0].text == text


@pytest.mark.parametrize("text", ["Strategy 2010-15", "Plan 2014-20", "2010-15"])
def test_unmarked_two_digit_end_gives_no_range(text):
    """PI R-2 a: a four-digit start with an unmarked two-digit end is no range; outside 2015-2030 nothing counts."""
    assert year_ranges(text, reference_year=REF) == []
    assert years(text) == []


@pytest.mark.parametrize("text,expected", [
    ("2010 to 2020", [2010, 2020]),
    ("2014 through 2020", [2014, 2020]),
    ("2014 until 2020", [2014, 2020]),
    ("2014 TO 2020", [2014, 2020]),
    ("2014 Through 2020", [2014, 2020]),
    ("2020 to 2022", [2020, 2022]),
    ("2010  to 2020", [2010, 2020]),         # lane A C-3: doubled spaces
    ("2010 to  2020", [2010, 2020]),
    ("2014\u00a0to 2020", [2014, 2020]),     # no-break space
    ("2014 through\u00a0\u00a02020", [2014, 2020]),
])
def test_range_words_d9(text, expected):
    assert years(text) == expected
    (r,) = year_ranges(text, reference_year=REF)
    assert r.kind == RANGE


@pytest.mark.parametrize("text,expected", [
    ("2010to2020", [2020]),          # a space or no-break space is required each side
    ("2010 into 2020", [2020]),      # whole words only
    ("2010 top 2020", [2020]),
    ("2010 till 2020", [2020]),      # not in the list
    ("2010 and 2020", [2020]),
])
def test_range_words_negative(text, expected):
    assert year_ranges(text, reference_year=REF) == []
    assert years(text) == expected


@pytest.mark.parametrize("text", ["pp. 1998 to 2020", "No. 1998 through 2020", "page 1998 until 2020"])
def test_numbering_word_applies_to_word_ranges(text):
    assert years(text) == [2020]


def test_word_range_starting_inside_a_fiscal_label():
    # "FY 2010" is a one-year label (lifted, C2b); the range "2010 to 2020" starts inside it and is still a range.
    assert years("FY 2010 to 2020") == [2010, 2020]


def test_range_forms_mark_the_end():
    cands = extract_year_candidates("Plan 2014-2020.", reference_year=REF)
    assert [(c.year, c.forms) for c in cands] == [(2014, (RANGE_LOWER,)), (2020, (LITERAL, RANGE_UPPER))]
    (r,) = year_ranges("Plan 2014-2020.", reference_year=REF)
    assert r.kind == RANGE and r.text == "2014-2020" and not r.numbered


@pytest.mark.parametrize("prefix", ["p.", "pp.", "page", "ID", "No.", "#", "art.", "§", "PP.", "Page", "id", "no.",
                                    "Art."])
def test_numbering_word_keeps_window(prefix):
    text = f"{prefix} 1998-2020"
    assert years(text) == [2020]
    (r,) = year_ranges(text, reference_year=REF)
    assert r.numbered


def test_numbering_word_needs_to_be_just_before():
    assert years("page one covers 1998-2020") == [1998, 2020]
    assert years("homepage 1998-2020") == [1998, 2020]


@pytest.mark.parametrize("text,expected", [
    ("2024-25", [2024]),                      # unmarked two-digit end is not a range end
    ("2014-25", []),
    ("2024-06-30", [2024]),                    # ISO date
    ("2025-2019", [2019, 2025]),               # descending
    ("2566-2567", []),                         # outside the 1900-2099 guard (unmarked BE)
    ("1402-1403", []),
])
def test_not_ranges(text, expected):
    assert year_ranges(text, reference_year=REF) == []
    assert years(text) == expected


# ---- table A fiscal markers (one test each) -------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Haushaltsjahr 2025/2026", [2025, 2026]),
    ("Geschäftsjahr 2024/25", [2024, 2025]),
    ("Rechnungsjahr 2014", [2014]),   # C2b: lifted
    ("Rechnungsjahr 2024", [2024]),
    ("Wirtschaftsjahr 2023/24", [2023, 2024]),
    ("Doppelhaushalt 2025/26", [2025, 2026]),
    ("exercice budgétaire 2024", [2024]),
    ("exercice financier 2024-2025", [2024, 2025]),
    ("exercice fiscal 2023-24", [2023, 2024]),
    ("année fiscale 2022", [2022]),
    ("année budgétaire 2021-22", [2021, 2022]),
    ("ejercicio fiscal 2024", [2024]),
    ("ejercicio presupuestario 2025-26", [2025, 2026]),
    ("año fiscal 2023/24", [2023, 2024]),
    ("anno fiscale 2022/23", [2022, 2023]),
    ("esercizio finanziario 2024", [2024]),
    ("exercício financeiro 2024/25", [2024, 2025]),
    ("exercício fiscal 2019-20", [2019, 2020]),
    ("ano fiscal 2018/19", [2018, 2019]),
    ("begrotingsjaar 2024-25", [2024, 2025]),
    ("boekjaar 2023/24", [2023, 2024]),
    ("회계연도 2024-25", [2024, 2025]),
    ("2024-25 회계연도", [2024, 2025]),
    ("2024-25年度", [2024, 2025]),
    ("2024年度", [2024]),
    ("2024/25财年", [2024, 2025]),
    ("2024-25財年", [2024, 2025]),
    ("2023-24财政年度", [2023, 2024]),
    ("2023/24 財政年度", [2023, 2024]),
    ("2022-23会计年度", [2022, 2023]),
    ("2022-23會計年度", [2022, 2023]),
])
def test_table_a_marker(text, expected):
    assert years(text) == expected
    labs = fiscal_labels(text, reference_year=REF)
    assert len(labs) == 1 and labs[0].kind in (FISCAL_ONE, FISCAL_TWO)


def test_table_a_two_digit_end_differs_from_unmarked():
    # The same written pair: unmarked gives the four-digit year only; with a marker, both.
    assert years("2024/25") == [2024] and years("Haushaltsjahr 2024/25") == [2024, 2025]


@pytest.mark.parametrize("text", ["Haushaltsjahres 2024/25", "Geschaeftsjahr 2024/25", "exercice 2024/25",
                                  "Doppelhaushaltsplan 2025/26"])
def test_table_a_negative_spellings_not_markers(text):
    assert fiscal_labels(text, reference_year=REF) == []


@pytest.mark.parametrize("text,expected", [
    ("ปีงบประมาณ 2568", [2025]),
    ("ปีงบประมาณ พ.ศ. 2567-2568", [2024, 2025]),
    ("ปีงบประมาณ ๒๕๖๘", [2025]),
    ("ปีงบประมาณ 2025", [2025]),
    ("ปีงบประมาณ 2557", [2014]),    # C2b: lifted
    ("ปีงบประมาณ 2442", []),        # BE 2442 = 1899: below the guard
])
def test_table_a_thai_fiscal(text, expected):
    assert years(text) == expected


# ---- table B calendars (one test each) ------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("令和6年", [2024]),
    ("令和元年", [2019]),
    ("令和６年度", [2024]),
    ("令和六年", [2024]),
    ("令和十二年", [2030]),
    ("令和13年", [2031]),      # C2b: lifted
    ("平成27年", [2015]),
    ("平成31年", [2019]),
    ("平成二十六年", [2014]),
    ("平成元年", [1989]),
])
def test_table_b_japanese_era(text, expected):
    assert years(text) == expected
    if expected:
        assert ERA_JP in forms_of(text, expected[0])


@pytest.mark.parametrize("text,expected", [
    ("พ.ศ. 2567", [2024]),
    ("พ.ศ.2558", [2015]),
    ("พ.ศ. ๒๕๖๗", [2024]),
    ("B.E. 2573", [2030]),
    ("B.E. 2557", [2014]),     # C2b: lifted
    ("B.E. 2442", []),        # 1899: below the guard
    ("BE 2567", []),          # bare BE is not a marker
    ("2567", []),             # unmarked: outside the window, no conversion
    ("2567 B.E.", [2024]),    # D6: marker after the year
    ("2567 พ.ศ.", [2024]),
    ("พ.ศ. 2566-2567", [2023, 2024]),   # D6: marked BE range, both years
    ("2566-2567 พ.ศ.", [2023, 2024]),
    ("B.E. 2566/67", [2023, 2024]),     # "b3-2 b": BE end keeps the start's BE century
    ("พ.ศ. 2450-2460", [1907, 1917]),   # range ends lifted within the guard
    ("พ.ศ. 2567 B.E.", [2024]),
])
def test_table_b_buddhist_era(text, expected):
    assert years(text) == expected
    if expected:
        assert BUDDHIST_ERA in forms_of(text, expected[0])


@pytest.mark.parametrize("text,expected", [
    ("民國113年", [2024]),
    ("民国104年", [2015]),
    ("中華民國一百一十三年", [2024]),
    ("民國一一三年", [2024]),
    ("民國103年", [2014]),     # C2b: lifted
    ("民國1年", [1912]),
    ("民國189年", []),        # 2100: above the guard
    ("113年", []),
])
def test_table_b_roc(text, expected):
    assert years(text) == expected
    if expected:
        assert ROC in forms_of(text, expected[0])


@pytest.mark.parametrize("text", ["R6.4.1", "H30年", "1446 هـ", "AH 1446", "1403 ه.ش", "昭和64年"])
def test_table_b_out_of_scope_not_converted(text):
    assert years(text) == []
    assert all(lab.kind == RANGE for lab in all_labels(text, reference_year=REF)) or all_labels(text, reference_year=REF) == []


# ---- de-duplication, ties, determinism, regressions -----------------------------------------------------

def test_dedup_keeps_every_span():
    text = "In 2025 (FY2025) and again 2025."
    (c,) = extract_year_candidates(text, reference_year=REF)
    assert [(s.form, s.text) for s in c.sources] == [
        (LITERAL, "2025"), (FISCAL_ONE, "FY2025"), (LITERAL, "2025"), (LITERAL, "2025")]


def test_two_fy_tokens_each_one_year():
    assert years("FY2024-FY2025") == [2024, 2025]
    assert [f.kind for f in fiscal_labels("FY2024-FY2025", reference_year=REF)] == [FISCAL_ONE, FISCAL_ONE]


def test_table_header_keeps_every_label():
    text = "FY 2024 FY 2025 FY26 FY27"
    assert [f.years for f in fiscal_labels(text, reference_year=REF)] == [(2024,), (2025,), (2026,), (2027,)]


def test_bare_trailing_fy_is_not_a_marker():
    assert fiscal_labels("Budget 2025 FY", reference_year=REF) == []


@pytest.mark.parametrize("text", ["Audit FY 06/30/2024", "FY 2024-06-30 close", "FY24/25/26", "FY 2024/06/30",
                                  "FY 2014-2019/20", "FY 2014/15-2019/20-2024/25"])
def test_date_like_runs_are_not_labels(text):
    assert fiscal_labels(text, reference_year=REF) == []


@pytest.mark.parametrize("text", ["FY 2014/15-2019/20", "FY 2014/15\u20132019/20", "FY2014/15-2019/20",
                                  "FY2014/15-FY2019/20", "Haushaltsjahr 2014/15-2019/20"])
def test_chained_fiscal_label_gives_two_labels(text):
    """PI R-4 a (lane A C-2): "FY 2014/15-2019/20" reads as two labels: 2014, 2015, 2019, 2020."""
    labels = fiscal_labels(text, reference_year=REF)
    assert [(f.kind, f.years) for f in labels] == [(FISCAL_TWO, (2014, 2015)), (FISCAL_TWO, (2019, 2020))]
    assert labels[1].text.lstrip("FY") == "2019/20"
    assert all(text[f.start:f.end] == f.text for f in labels)
    assert years(text) == [2014, 2015, 2019, 2020]
    assert forms_of(text, 2014) == {FISCAL_LOWER}
    assert forms_of(text, 2020) == {FISCAL_UPPER}


def test_chained_thai_fiscal_label_converts_both_spans():
    text = "\u0e1b\u0e35\u0e07\u0e1a\u0e1b\u0e23\u0e30\u0e21\u0e32\u0e13 2557/58-2562/63"  # pi ngop praman
    assert [f.years for f in fiscal_labels(text, reference_year=REF)] == [(2014, 2015), (2019, 2020)]


def test_plural_fiscal_years_is_not_a_label_but_range_counts():
    text = "for the 2026-2028 fiscal years"
    assert fiscal_labels(text, reference_year=REF) == []
    assert years(text) == [2026, 2028]


def test_candidates_ascending_and_deterministic():
    text = "FY2027/28 then 2016, fiscal 2020, FY19, 令和元年."
    a, b = extract_year_candidates(text, reference_year=REF), extract_year_candidates(text, reference_year=REF)
    assert a == b
    assert [c.year for c in a] == [2016, 2019, 2020, 2027, 2028]


def test_empty_text():
    assert extract_year_candidates("", reference_year=REF) == []


# ---- rule ids (T-064 follow-up F4) ----------------------------------------------------------------------

@pytest.mark.parametrize("text,year,rule", [
    ("2025", 2025, Y.R_LITERAL),
    ("FY2025", 2025, Y.R_FY_EN_PREFIX),
    ("2025 fiscal year", 2025, Y.R_FY_EN_POSTFIX),
    ("Haushaltsjahr 2025", 2025, Y.R_FY_A_PREFIX),
    ("2024年度", 2024, Y.R_FY_A_POSTFIX),
    ("ปีงบประมาณ 2568", 2025, Y.R_FY_A_THAI),
    ("令和6年", 2024, Y.R_ERA_JP),
    ("พ.ศ. 2567", 2024, Y.R_BE_PREFIX),
    ("2567 B.E.", 2024, Y.R_BE_POSTFIX),
    ("民國113年", 2024, Y.R_ROC),
    ("1998-2002", 1998, Y.R_RANGE_SEP),
    ("1998 to 2002", 1998, Y.R_RANGE_WORD),
])
def test_rule_id_positive(text, year, rule):
    srcs = [s for c in extract_year_candidates(text, reference_year=REF) if c.year == year for s in c.sources]
    assert rule in {s.rule for s in srcs}
    assert all(s.rule in Y.RULES for c in extract_year_candidates(text, reference_year=REF) for s in c.sources)


def test_rule_id_negative_every_source_has_one():
    text = "FY 2024-25, 2019 to 2021, 1998 - 2002, 令和元年 and 2026."
    srcs = [s for c in extract_year_candidates(text, reference_year=REF) for s in c.sources]
    assert srcs and all(s.rule in Y.RULES for s in srcs)
    assert {s.rule for s in srcs if s.text == "2019 to 2021"} == {Y.R_RANGE_WORD}
    assert {s.rule for s in srcs if s.text == "1998 - 2002"} == {Y.R_RANGE_SEP}
    assert Y.R_RANGE_WORD not in {s.rule for s in srcs if s.text == "FY 2024-25"}


# ---- two-digit pivot (PI 2026-11-05 "B1c (but current-year+25-99)") -------------------------------------

@pytest.mark.parametrize("text,ref,expected", [
    ("FY50", 2026, [2050]),
    ("FY51", 2026, [1951]),
    ("FY98", 2026, [1998]),
    ("FY24", 2026, [2024]),
    ("FY00", 2026, [2000]),
    ("FY99", 2026, [1999]),
    ("FY54", 2030, [2054]),
    ("FY55", 2030, [1955]),     # (2030 mod 100) + 25 = 55 is the first 19xx year
    ("FY99", 2075, [2099]),     # (2075 mod 100) + 25 = 100: no 19xx years left
])
def test_two_digit_pivot(text, ref, expected):
    assert [c.year for c in extract_year_candidates(text, reference_year=ref)] == expected


@pytest.mark.parametrize("text,ref,expected", [
    ("FY98/99", 2026, [1998, 1999]),
    ("FY99/00", 2026, [1999, 2000]),     # end takes the start's century and rolls over
    ("FY50/51", 2026, [1951, 2050]),     # r13: the end is pivoted on its own
    ("FY 51-52", 2026, [1951, 1952]),
    ("FY13/14", 2026, [2013, 2014]),
])
def test_two_digit_pivot_two_year_labels(text, ref, expected):
    assert [c.year for c in extract_year_candidates(text, reference_year=ref)] == expected


def test_pivot_leaves_four_digit_and_unmarked_alone():
    for ref in (2026, 2030, 2075):
        assert [c.year for c in extract_year_candidates("FY1998, FY2051, 2024-25", reference_year=ref)] == [
            1998, 2024, 2051]


def test_reference_year_is_recorded():
    for ref in (2026, 2030):
        cands = extract_year_candidates("FY51 and 2025 and 1998-2002", reference_year=ref)
        assert {s.reference_year for c in cands for s in c.sources} == {ref}
        assert {lab.reference_year for lab in all_labels("FY51 1998-2002", reference_year=ref)} == {ref}


def test_default_reference_year_is_call_time_year():
    import datetime
    assert Y.default_reference_year() == datetime.date.today().year
    (c,) = extract_year_candidates("FY24")
    assert {s.reference_year for s in c.sources} == {Y.default_reference_year()}


def test_two_digit_year_helper():
    assert Y.PIVOT_OFFSET == 25
    assert [Y.two_digit_year(yy, 2026) for yy in (0, 50, 51, 99)] == [2000, 2050, 1951, 1999]


# ---- r13 year rule 1: every two-digit year by the pivot, ends included (r13-Q2 a) -----------------------

@pytest.mark.parametrize("text,ref,expected", [
    ("FY1949/50", 2026, (1949, 2050)),
    ("FY98/99", 2026, (1998, 1999)),
    ("FY99/00", 2026, (1999, 2000)),
    ("FY50/51", 2026, (2050, 1951)),
    ("FY2050/51", 2026, (2050, 1951)),
    ("FY1954/55", 2030, (1954, 1955)),
    ("FY1953/54", 2030, (1953, 2054)),
    ("2024-25年度", 2026, (2024, 2025)),
    ("Haushaltsjahr 1998/99", 2026, (1998, 1999)),
])
def test_r13_end_year_pivot(text, ref, expected):
    (lab,) = fiscal_labels(text, reference_year=ref)
    assert lab.kind == FISCAL_TWO and lab.years == expected  # written order kept
    assert [c.year for c in extract_year_candidates(text, reference_year=ref)] == sorted(expected)


def test_r13_end_before_start_keeps_positional_forms():
    text = "FY50/51"
    assert forms_of_ref(text, 2050, 2026) == {FISCAL_LOWER}
    assert forms_of_ref(text, 1951, 2026) == {FISCAL_UPPER}


@pytest.mark.parametrize("text,ref,expected", [
    ("B.E. 2566/67", 2026, (2023, 2024)),
    ("พ.ศ. 2566-67", 2030, (2023, 2024)),
    ("2599/00 B.E.", 2026, (2056, 2057)),    # BE end rolls into the next BE century
    ("ปีงบประมาณ 2567-68", 2026, (2024, 2025)),
    ("ปีงบประมาณ 2567-68", 2075, (2024, 2025)),  # reference year irrelevant for BE
])
def test_b3_2b_be_two_digit_end_keeps_be_century(text, ref, expected):
    (lab,) = [f for f in all_labels(text, reference_year=ref) if f.kind != RANGE]
    assert lab.years == expected
    assert [c.year for c in extract_year_candidates(text, reference_year=ref)] == sorted(expected)


def test_b3_2b_ce_start_in_thai_fiscal_label_still_pivots():
    # A Thai fiscal label with a CE start (< 2400) is not BE: its two-digit end follows the r13 pivot.
    assert [c.year for c in extract_year_candidates("ปีงบประมาณ 2024-25", reference_year=REF)] == [2024, 2025]
    assert [c.year for c in extract_year_candidates("ปีงบประมาณ 1998-99", reference_year=REF)] == [1998, 1999]


def test_r13_thai_four_digit_end():
    assert [c.year for c in extract_year_candidates("ปีงบประมาณ 2567-2568", reference_year=REF)] == [2024, 2025]


def forms_of_ref(text: str, year: int, ref: int) -> set[str]:
    return {s.form for c in extract_year_candidates(text, reference_year=ref) if c.year == year for s in c.sources}


# ---- PI F-1 b: unruled year forms read like R-4 a ------------------------------------------------------

@pytest.mark.parametrize("text", ["FY 2014-15 to 2019-20", "FY2014-15 to 2019-20", "FY 2014/15 through 2019/20",
                                  "FY 2014-15 to 2019-20", "Haushaltsjahr 2014/15 to 2019/20"])
def test_fiscal_spans_joined_by_a_range_word_give_two_labels(text):
    labels = fiscal_labels(text, reference_year=REF)
    assert [(f.kind, f.years) for f in labels] == [(FISCAL_TWO, (2014, 2015)), (FISCAL_TWO, (2019, 2020))]
    assert all(text[f.start:f.end] == f.text for f in labels)
    assert years(text) == [2014, 2015, 2019, 2020]
    assert forms_of(text, 2020) == {FISCAL_UPPER}
    assert year_ranges(text, reference_year=REF) == []  # left to the fiscal labels: no second reading


@pytest.mark.parametrize("text", ["2014-15 to 2019-20", "2014/15 to 2019/20", "2014-15 until 2019-20",
                                  "Plan 2014-15 to 2019-20."])
def test_unmarked_spans_joined_by_a_range_word_give_two_labels(text):
    labels = year_ranges(text, reference_year=REF)
    assert [(f.kind, f.years, f.rule) for f in labels] == [(RANGE, (2014, 2015), Y.R_RANGE_SPAN_PAIR),
                                                           (RANGE, (2019, 2020), Y.R_RANGE_SPAN_PAIR)]
    assert [f.text.replace("/", "-") for f in labels] == ["2014-15", "2019-20"]
    assert years(text) == [2014, 2015, 2019, 2020]
    assert forms_of(text, 2014) == {RANGE_LOWER}
    assert forms_of(text, 2020) == {RANGE_UPPER}


def test_span_pair_mixed_four_digit_end_no_double_reading():
    text = "2014-15 to 2019-2020"
    labels = year_ranges(text, reference_year=REF)
    assert [(f.years, f.rule) for f in labels] == [((2014, 2015), Y.R_RANGE_SPAN_PAIR),
                                                   ((2019, 2020), Y.R_RANGE_SEP)]
    assert years(text) == [2014, 2015, 2019, 2020]


@pytest.mark.parametrize("text,expected", [
    ("pp. 2014-15 to 2019-20", [2015, 2019, 2020]),  # numbering word: unmarked ends keep 2015-2030
    ("2019-20 to 2014-15", [2019]),                  # runs backward: no span pair, literal 2019 only
    ("2014-15 and 2019-20", [2019]),                 # not a range word
    ("2014-2015 to 2019-2020", [2014, 2015, 2019, 2020]),  # four-digit spans: two plain ranges, as before
])
def test_span_pair_limits(text, expected):
    assert years(text) == expected


@pytest.mark.parametrize("text", ["Strategy 2010-15", "Plan 2014-20", "2010-15"])
def test_r2a_still_holds_beside_span_pairs(text):
    assert year_ranges(text, reference_year=REF) == [] and years(text) == []


@pytest.mark.parametrize("text,expected", [
    ("2010-2012-2014", [2010, 2012, 2014]),
    ("2010 - 2012 - 2014", [2010, 2012, 2014]),
    ("2010/2012/2014/2016", [2010, 2012, 2014, 2016]),
    ("2019-2020-2021", [2019, 2020, 2021]),
    ("1850-1870-2010", [2010]),       # each year bounded on its own (R-3 b)
])
def test_year_chain_gives_every_year(text, expected):
    assert years(text) == expected
    labels = year_ranges(text, reference_year=REF)
    assert labels and all(f.kind == RANGE and f.rule == Y.R_RANGE_CHAIN for f in labels)
    assert all(text[f.start:f.end] == f.text for f in labels)


def test_year_chain_sources_are_consecutive_pairs():
    labels = year_ranges("2010-2012-2014", reference_year=REF)
    assert [(f.text, f.years) for f in labels] == [("2010-2012", (2010, 2012)), ("2012-2014", (2012, 2014))]
    assert forms_of("2010-2012-2014", 2012) == {RANGE_LOWER, RANGE_UPPER}


@pytest.mark.parametrize("text,expected", [
    ("2014-2012-2010", []),           # does not run forward: no chain
    ("2010-2012-2012", []),
    ("pp. 2010-2012-2014", []),       # numbering word keeps 2015-2030
    ("2010-12-14", []),               # date, not four-digit years
    ("2024-06-30", [2024]),
])
def test_year_chain_limits(text, expected):
    assert years(text) == expected
