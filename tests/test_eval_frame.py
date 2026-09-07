"""Tests for the evaluation sampling frame.

The four `pins_*` cases below are the real institutions the pre-2026-08-02
bare-substring `n/a` rule silently dropped. They are the regression this
module exists to prevent.
"""

from __future__ import annotations

import csv

import pytest

from g3o.run.presweep.eval_frame import (
    build,
    filter_master,
    is_eligible,
    is_placeholder,
    website_host,
)


def _row(website: str, **over: str) -> dict[str, str]:
    base = {
        "institution_name": "Some Agency",
        "country": "Someplace",
        "website": website,
        "duplicate": "",
    }
    base.update(over)
    return base


# --- host parsing ----------------------------------------------------------


@pytest.mark.parametrize(
    "website,expected",
    [
        ("https://asfromania.ro/en/about-asf", "asfromania.ro"),
        ("www.mfin.hr/en/anti-money-laundering-office", "www.mfin.hr"),
        ("http://example.gov.uk", "example.gov.uk"),
    ],
)
def test_website_host_parses(website: str, expected: str) -> None:
    assert website_host(website) == expected


@pytest.mark.parametrize("website", ["localhost", "no-dot-here", "", "http://"])
def test_website_host_rejects_hostless(website: str) -> None:
    assert website_host(website) is None


# --- the n/a token rule ----------------------------------------------------


@pytest.mark.parametrize(
    "website",
    [
        "http://www.sipa.gov.ba/en/about-us/structure/financial-intelligence-department",
        "http://www.mfin.hr/en/anti-money-laundering-office",
        "http://www.economie.gouv.fr/tracfin/accueil-tracfin",
        "https://asfromania.ro/en/about-asf",
    ],
)
def test_pins_real_institutions_the_substring_rule_dropped(website: str) -> None:
    """`n/a` inside `en/about`, `en/anti`, `fin/accueil` is not a placeholder."""
    assert "n/a" in website.lower(), "fixture must contain the raw substring"
    assert not is_placeholder(website)
    assert is_eligible(_row(website))


@pytest.mark.parametrize("website", ["n/a", "N/A", "n/a ", " n/a", "-n/a-", "(n/a)"])
def test_delimited_na_is_still_a_placeholder(website: str) -> None:
    assert is_placeholder(website.strip() or website)


def test_na_as_a_whole_path_segment_is_a_placeholder() -> None:
    assert is_placeholder("http://example.gov/n/a")


@pytest.mark.parametrize(
    "website", ["http://example.gov/tbd", "http://none.example.gov", "TBD"]
)
def test_other_markers_stay_substring_matches(website: str) -> None:
    assert is_placeholder(website)


@pytest.mark.parametrize(
    "website",
    [
        "https://en.wikipedia.org/wiki/Ministry",
        "https://data.ipu.org/parliament/XX",
        "https://commons.wikimedia.org/wiki/Thing",
    ],
)
def test_aggregator_hosts_are_placeholders(website: str) -> None:
    assert is_placeholder(website)


# --- eligibility -----------------------------------------------------------


def test_the_name_collision_flag_no_longer_rejects() -> None:
    """Was `test_duplicates_are_excluded`. Removed 2026-08-30 with the sampler
    defect: `duplicate=1` flags a NAME collision, not a repeated row.

    No published figure moves — 0 of the master's 719,588 rows carry both
    `duplicate=1` and a website, so this branch could never fire behind the
    website requirement below. It was dead code that read as policy.
    """
    assert is_eligible(_row("https://example.gov.uk", duplicate="1"))
    assert is_eligible(_row("https://example.gov.uk", duplicate="0"))
    # …and the website requirement, which does the real work, is untouched.
    assert not is_eligible(_row("", duplicate="1"))
    assert not is_eligible(_row("n/a", duplicate="1"))


def test_short_websites_are_excluded() -> None:
    assert not is_eligible(_row("a.io"))


def test_missing_website_is_excluded() -> None:
    assert not is_eligible(_row(""))
    assert not is_eligible({"duplicate": "", "institution_name": "X"})


def test_filter_master_preserves_input_order() -> None:
    rows = [
        _row("https://a.gov.uk"),
        _row("n/a"),
        _row("https://b.gov.uk"),
        _row("https://c.gov.uk", duplicate="1"),
        _row("https://d.gov.uk/en/about-us"),
    ]
    kept = [r["website"] for r in filter_master(rows)]
    assert kept == [
        "https://a.gov.uk",
        "https://b.gov.uk",
        "https://c.gov.uk",  # name collision: kept since 2026-08-30
        "https://d.gov.uk/en/about-us",
    ]


def test_build_round_trips_through_csv(tmp_path) -> None:
    master = tmp_path / "master.csv"
    fields = ["institution_name", "country", "website", "duplicate"]
    with open(master, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(
            [
                _row("https://keep.gov.uk/en/about"),
                _row("n/a"),
                _row("https://collides.gov.uk", duplicate="1"),
            ]
        )
    out = tmp_path / "sub" / "frame.csv"
    assert build(master, out) == 2
    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["website"] for r in rows] == [
        "https://keep.gov.uk/en/about",
        "https://collides.gov.uk",
    ]
