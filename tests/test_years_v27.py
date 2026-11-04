"""T-064: year candidates (literal, fiscal-year labels, ranges): RC-D-017 9a-e, "3 a"; PI 2026-11-04 "6 a", "7", "8 a", "1b".

Synthetic strings only (DP-064e)."""

from __future__ import annotations

import pytest

from g3o.extract import years as Y
from g3o.extract.years import (
    FISCAL_ONE,
    FISCAL_RANGE,
    FISCAL_TWO,
    LITERAL,
    RANGE_LOWER,
    extract_year_candidates,
    fiscal_labels,
    year_ranges,
)


def years(text: str, lower_only: bool | None = None) -> list[int]:
    return [c.year for c in extract_year_candidates(text, lower_only)]


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


def test_fiscal_two_negative_nonconsecutive_is_range():
    text = "FY2024-26 programme"
    (lab,) = fiscal_labels(text)
    assert lab.kind == FISCAL_RANGE and lab.years == (2024, 2026)
    assert years(text) == [2024]


@pytest.mark.parametrize("text,expected", [("FY2014/15", [2015]), ("FY2030/31", [2030]),
                                           ("FY2013/14", []), ("FY2031/32", [])])
def test_fiscal_two_range_edges(text, expected):
    assert years(text) == expected


# ---- ranges: lower year only ("6 a", "7", "1b") --------------------------------------------------------

def test_module_default_is_lower_year_only():
    assert Y.RANGES_LOWER_YEAR_ONLY is True


@pytest.mark.parametrize("text,lower_only,literal_only", [
    ("2019-2021", [2019], [2019, 2021]),
    ("2024-25", [2024], [2024]),
    ("2024/2025", [2024], [2024, 2025]),
    ("2019-21", [2019], [2019]),
    ("2020–2022", [2020], [2020, 2022]),   # en dash
    ("2020—2022", [2020], [2020, 2022]),   # em dash
    ("2020 - 2022", [2020], [2020, 2022]),
    ("2020 / 2022", [2020], [2020, 2022]),
    ("FY 2022-2026", [2022], [2022, 2026]),       # marked, not consecutive ("7")
    ("FY2024-26", [2024], [2024]),
    ("2022-2026 fiscal year", [2022], [2022, 2026]),
])
def test_ranges_both_settings(text, lower_only, literal_only):
    assert years(text, True) == lower_only
    assert years(text, False) == literal_only
    assert years(text) == lower_only  # module default


@pytest.mark.parametrize("text", ["FY2024/25", "FY 2024-2025", "2024-25 financial year"])
def test_consecutive_fiscal_keeps_both_under_either_setting(text):
    assert years(text, True) == [2024, 2025] and years(text, False) == [2024, 2025]


def test_unmarked_range_source_form():
    (c,) = extract_year_candidates("Plan 2019-2021.")
    assert c.year == 2019 and c.forms == (LITERAL, RANGE_LOWER)
    (r,) = year_ranges("Plan 2019-2021.")
    assert r.text == "2019-2021" and r.years == (2019, 2021)


def test_standalone_upper_year_still_counts():
    assert years("2019-2021 and 2021", True) == [2019, 2021]
    (_, c21) = extract_year_candidates("2019-2021 and 2021", True)
    assert [s.start for s in c21.sources] == [14]  # only the standalone mention, not the range's upper year


def test_upper_year_does_not_leak_through_literal_path():
    for text, lower in (("2019-2021", 2019), ("FY 2022-2026", 2022), ("2020 – 2022", 2020)):
        (c,) = extract_year_candidates(text, True)
        assert c.year == lower
        literal_starts = [s.start for s in c.sources if s.form == LITERAL]
        assert literal_starts == [text.index(str(lower))]


def test_lower_year_out_of_range_drops_whole_range():
    # "2010-2020": lower year outside 2015-2030, upper year dropped by "1b": no candidate at all.
    assert years("2010-2020", True) == [] and years("2010-2020", False) == [2020]


@pytest.mark.parametrize("text,expected", [
    ("2020 to 2022", [2020, 2022]),        # words are not separators (open question)
    ("2019-2020-2021", [2019, 2020, 2021]),  # chains are not ranges
    ("2024-06-30", [2024]),                # ISO date
    ("2025-2019", [2019, 2025]),           # descending: not a range
    ("2020-2020", [2020]),
])
def test_not_ranges(text, expected):
    assert year_ranges(text) == []
    assert years(text, True) == expected


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
