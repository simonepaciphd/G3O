"""Tests for scripts/build_codebook_html.py — the HTML coverage codebook.

The generator is master-side tooling (WS7 landing), not pipeline code, so it
is imported by path rather than through the g3o package.
"""

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "build_codebook_html",
    Path(__file__).resolve().parent.parent / "scripts" / "build_codebook_html.py",
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules["build_codebook_html"] = mod
_SPEC.loader.exec_module(mod)

HEADER = [
    "institution_uid", "master_row_id", "master_build_id", "country",
    "country_iso3", "government_level", "branch", "institution_type",
    "institution_name", "website", "source_dataset_id", "source_url",
    "source_file", "retrieval_date", "notes", "duplicate", "disambiguation",
]


def write_master(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in HEADER})
    return path


def row(country, level, itype, sid, surl="", build="mb-2026-07-30", iso="XXX"):
    return {
        "country": country, "country_iso3": iso, "government_level": level,
        "institution_type": itype, "source_dataset_id": sid, "source_url": surl,
        "master_build_id": build,
    }


@pytest.fixture()
def tiny_master(tmp_path):
    return write_master(tmp_path / "master.csv", [
        row("Atlantis", "national", "central_bank", "bis_central_banks"),
        row("Atlantis", "local", "municipality", "subnational_RAs",
            "https://registry.example.gov (the national directory)"),
        row("Atlantis", "local", "municipality", "subnational_RAs",
            "https://registry.example.gov (the national directory)"),
        row("Borduria", "local", "municipality", "subnational_RAs",
            "https://stats.borduria.example"),
        row("Borduria", "national", "school_district", "nces_district_websites"),
    ])


def test_aggregate_counts_and_sources(tiny_master):
    counts, refs, summaries, build_id = mod.aggregate(tiny_master)
    assert build_id == "mb-2026-07-30"
    assert summaries["n_rows"] == 5
    assert summaries["n_countries"] == 2
    assert summaries["n_levels"] == 2
    assert summaries["n_types"] == 3
    # Distinct ACTUAL sources: BIS + NCES (org-level) + two distinct register
    # URLs — the two identical Atlantis URLs dedupe to one.
    assert summaries["n_sources"] == 4
    assert counts[("Atlantis", "local", "municipality")] == 2
    ref_map = refs[("Atlantis", "local", "municipality")]
    assert list(ref_map) == ["https://registry.example.gov"]
    assert "the national directory" in next(iter(ref_map.values()))


def test_mixed_build_refused(tmp_path):
    master = write_master(tmp_path / "mixed.csv", [
        row("Atlantis", "national", "central_bank", "bis_central_banks"),
        row("Atlantis", "national", "ministry",
            "cross_country_executive_national_whogov", build="mb-2026-07-13"),
    ])
    with pytest.raises(SystemExit, match="mixed build"):
        mod.aggregate(master)


def test_vintage_derived_from_build_id():
    assert (
        mod.vintage_from_build_id("mb-2026-07-30")
        == "As of 2026-07-30, from master build mb-2026-07-30."
    )
    with pytest.raises(SystemExit):
        mod.vintage_from_build_id("build-42")


def test_html_document_shape(tiny_master):
    counts, refs, summaries, build_id = mod.aggregate(tiny_master)
    doc = mod.build_html(counts, refs, summaries, mod.vintage_from_build_id(build_id))
    assert doc.startswith("<!doctype html>")
    # Self-contained: no external stylesheet/script/font/image requests.
    for marker in ("<link", "<script", "<img", "@import", "url("):
        assert marker not in doc
    assert "As of 2026-07-30, from master build mb-2026-07-30." in doc
    assert doc.count("<h3") == summaries["n_countries"]
    assert doc.count("<table") == doc.count("</table>")
    # NCES legend entry (PI-signed 2026-08-08) resolves to its org link.
    assert "NCES Common Core of Data — US school districts" in doc
    assert "https://nces.ed.gov/ccd/" in doc
    # No reliability vocabulary of any kind (staging A3/A7).
    lowered = doc.lower()
    for word in ("accuracy", "agreement", "precision", "recall", "error rate", "reliab"):
        assert word not in lowered


def test_html_escapes_content(tmp_path):
    master = write_master(tmp_path / "esc.csv", [
        row("A&B <Land>", "national", "central_bank", "bis_central_banks"),
    ])
    counts, refs, summaries, build_id = mod.aggregate(master)
    doc = mod.build_html(counts, refs, summaries, mod.vintage_from_build_id(build_id))
    assert "A&amp;B &lt;Land&gt;" in doc
    assert "<Land>" not in doc
