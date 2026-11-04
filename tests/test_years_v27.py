"""T-064: year candidates (literal + fiscal-year labels), RC-D-017 9a-e and "3 a". Synthetic strings only (DP-064e)."""

from __future__ import annotations

import pytest

from g3o.extract.years import (
    FISCAL_ONE,
    FISCAL_TWO,
    FISCAL_UNRULED,
    LITERAL,
    extract_year_candidates,
    fiscal_labels,
)


def years(text: str) -> list[int]:
    return [c.year for c in extract_year_candidates(text)]


def forms_of(text: str, year: int) -> set[str]:
    return {s.form for c in extract_year_candidates(text) if c.year == year for s in c.sources}


# ---- literal (unchanged rule) -------------------------------------------------------------------------

def test_literal_positive_and_spans():
    text = "Announced in 2019, piloted 2021."
    cands = extract_year_candidates(text)
    assert [c.year for c in cands] == [2019, 2021]
    for c in cands:
        (s,) = c.sources
        assert s.form == LITERAL and text[s.start:s.end] == s.text == str(c.year)


def test_literal_negative():
    assert years("Population 120150, code 20251, ref 1999 and 2031.") == []


@pytest.mark.parametrize("text,expected", [("2014", []), ("2015", [2015]), ("2030", [2030]), ("2031", [])])
def test_literal_range_edges(text, expected):
    assert years(text) == expected


def test_non_ascii_digits_not_literal():
    # Arabic-Indic and full-width digits are not read by the literal rule (open question in SPIKE-T064).
    assert years("٢٠٢٤ ２０２４") == []


# ---- fiscal_one -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["FY2025", "FY 2025", "FY-2025", "F.Y. 2025", "FY25", "FY'25", "fy25",
                                   "fiscal year 2025", "Fiscal 2025", "financial year 2025", "2025 fiscal year"])
def test_fiscal_one_positive(label):
    text = f"Budget for {label} approved."
    assert years(text) == [2025]
    assert FISCAL_ONE in forms_of(text, 2025)
    (lab,) = fiscal_labels(text)
    assert lab.kind == FISCAL_ONE and text[lab.start:lab.end] == lab.text


@pytest.mark.parametrize("text", ["FYI 2025", "fiscal policy 2025", "MFY25", "fiscal 25 states", "FY"])
def test_fiscal_one_negative(text):
    assert all(f.kind != FISCAL_ONE for f in fiscal_labels(text))


def test_fiscal_one_gives_one_year_only():
    # "3 a": a one-year label never adds the neighbouring calendar year.
    assert years("FY25 results") == [2025]


@pytest.mark.parametrize("text,expected", [("FY14", []), ("FY15", [2015]), ("FY30", [2030]), ("FY31", [])])
def test_fiscal_one_range_edges(text, expected):
    assert years(text) == expected


# ---- fiscal_two -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["FY2024/25", "FY 2024-25", "FY2024-2025", "FY 2024/2025", "FY24/25",
                                   "FY 2024–25", "fiscal year 2024-25", "financial year 2024/2025",
                                   "2024-25 financial year", "2024/25 fiscal year", "FY 2024-25 fiscal year"])
def test_fiscal_two_positive(label):
    text = f"Plan for {label}."
    assert years(text) == [2024, 2025]
    assert FISCAL_TWO in forms_of(text, 2024) and FISCAL_TWO in forms_of(text, 2025)
    (lab,) = fiscal_labels(text)
    assert lab.kind == FISCAL_TWO and lab.years == (2024, 2025) and text[lab.start:lab.end] == lab.text


def test_fiscal_two_two_digit_second_year():
    text = "FY2024/25"
    cands = extract_year_candidates(text)
    assert [c.year for c in cands] == [2024, 2025]
    # 2025 comes only from the fiscal label; 2024 from both the label and the literal rule.
    assert {s.form for s in cands[1].sources} == {FISCAL_TWO}
    assert {s.form for s in cands[0].sources} == {FISCAL_TWO, LITERAL}


def test_fiscal_two_negative_nonconsecutive_is_unruled():
    text = "FY2024-26 programme"
    (lab,) = fiscal_labels(text)
    assert lab.kind == FISCAL_UNRULED and lab.years == (2024, 2026)
    assert years(text) == [2024]  # literal only; "26" gives nothing until ruled


@pytest.mark.parametrize("text,expected", [("FY2014/15", [2015]), ("FY2030/31", [2030]),
                                           ("FY2013/14", []), ("FY2031/32", [])])
def test_fiscal_two_range_edges(text, expected):
    assert years(text) == expected


# ---- unmarked ranges: no decision taken (open PI question) ---------------------------------------------

@pytest.mark.parametrize("text,expected", [("2019-2021", [2019, 2021]), ("2024/25", [2024]),
                                           ("2024-2025", [2024, 2025]), ("2019-21", [2019])])
def test_unmarked_ranges_literal_only(text, expected):
    assert fiscal_labels(text) == []
    assert years(text) == expected
    assert all(s.form == LITERAL for c in extract_year_candidates(text) for s in c.sources)


# ---- de-duplication, ties, determinism -----------------------------------------------------------------

def test_dedup_keeps_every_span():
    text = "In 2025 (FY2025) and again 2025."
    (c,) = extract_year_candidates(text)
    assert c.year == 2025
    assert [(s.form, s.text) for s in c.sources] == [
        (LITERAL, "2025"), (FISCAL_ONE, "FY2025"), (LITERAL, "2025"), (LITERAL, "2025")]
    assert [s.start for s in c.sources] == sorted(s.start for s in c.sources)
    for s in c.sources:
        assert text[s.start:s.end] == s.text


def test_two_fy_tokens_each_one_year():
    assert years("FY2024-FY2025") == [2024, 2025]
    assert [f.kind for f in fiscal_labels("FY2024-FY2025")] == [FISCAL_ONE, FISCAL_ONE]


def test_candidates_ascending_and_deterministic():
    text = "FY2027/28 then 2016, fiscal 2020, FY19."
    a, b = extract_year_candidates(text), extract_year_candidates(text)
    assert a == b
    assert [c.year for c in a] == [2016, 2019, 2020, 2027, 2028]


def test_empty_text():
    assert extract_year_candidates("") == []


# ---- regressions from the RS-008/RS-009 scan ------------------------------------------------------------

def test_table_header_keeps_every_label():
    text = "FY 2024 FY 2025 FY26 FY27"
    assert [f.years for f in fiscal_labels(text)] == [(2024,), (2025,), (2026,), (2027,)]
    assert years(text) == [2024, 2025, 2026, 2027]


def test_bare_trailing_fy_is_not_a_marker():
    assert fiscal_labels("Budget 2025 FY") == []


@pytest.mark.parametrize("text", ["Audit FY 06/30/2024", "FY 2024-06-30 close", "FY24/25/26"])
def test_date_like_runs_are_not_labels(text):
    assert fiscal_labels(text) == []


def test_plural_fiscal_years_is_not_a_label():
    assert fiscal_labels("for the 2026-2028 fiscal years") == []
