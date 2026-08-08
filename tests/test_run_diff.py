"""Tests for g3o.report.diff — the cross-run determinism report (``run-diff``).

Fixtures build minimal-but-realistic run directories in a temp path, mirroring
the artifact shapes the pipeline actually writes:

  • 2_official_site.json : {"url": <str|null>, ...}
  • 3_triage.json        : {"decisions": [{"url": ..., "decision": "keep"|"drop"}]}
  • scrape/<h>.json       : {"url": ..., "text": ...}
  • extract/<h>.json      : dumped BatchResponse {"data": [{"source_url": ...,
                            "has_genai_activity": ...}]}
  • 6_validate.json       : {"institution": {"has_genai_activity": ...}}

Institutions get staggered artifacts so every stage has an agree and a diverge
path, and Jaccard scores are asserted against known set overlaps.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from g3o.report import compute_run_diff, render_run_diff_text
from g3o.report.diff import _run_institutions
from tests._layout import (
    inst_dir as inst_dir_of,
)
from tests._layout import (
    write_manifest,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _inst_id(n: int) -> str:
    return f"INST-{n:07d}"


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_institution(
    inst_dir: Path,
    *,
    official_site: str | None = None,
    kept_urls: list[str] | None = None,
    scraped_urls: list[str] | None = None,
    extract_pairs: list[tuple[str, str]] | None = None,
    final_status: str | None = None,
) -> None:
    """Write whichever stage artifacts are supplied; skip the rest.

    Every keyword defaults to *absent* so a caller can exercise the
    independent-stage guarantee (a missing artifact at one stage must not block
    another).
    """
    if official_site is not None:
        _write(inst_dir / "2_official_site.json", {"url": official_site, "rationale": "ok"})
    if kept_urls is not None:
        _write(
            inst_dir / "3_triage.json",
            {"decisions": [{"url": u, "decision": "keep"} for u in kept_urls]},
        )
    if scraped_urls is not None:
        for i, u in enumerate(scraped_urls):
            _write(inst_dir / "scrape" / f"page{i}.json", {"url": u, "text": "genai text"})
    if extract_pairs is not None:
        # One extract file per source URL; the file is a dumped BatchResponse.
        for i, (u, hga) in enumerate(extract_pairs):
            _write(
                inst_dir / "extract" / f"page{i}.json",
                {"data": [{"source_url": u, "has_genai_activity": hga}]},
            )
    if final_status is not None:
        _write(
            inst_dir / "6_validate.json",
            {"institution": {"institution_id": inst_dir.name, "has_genai_activity": final_status}},
        )


def _build_run(root: Path, run_id: str, institutions: dict[str, dict[str, Any]]) -> Path:
    """Build ``root/<run_id>/`` with a manifest and the given per-inst specs."""
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(run_dir, {"run_id": run_id, "institutions": sorted(institutions)})
    for inst_id, spec in institutions.items():
        _write_institution(inst_dir_of(run_dir, inst_id), **spec)
    return run_dir


def _identical_spec() -> dict[str, dict[str, Any]]:
    """Three institutions, fully specified — reused to build identical runs."""
    return {
        _inst_id(1): dict(
            official_site="https://inst1.gov",
            kept_urls=["https://inst1.gov/a", "https://inst1.gov/b"],
            scraped_urls=["https://inst1.gov/a", "https://inst1.gov/b"],
            extract_pairs=[("https://inst1.gov/a", "yes")],
            final_status="yes",
        ),
        _inst_id(2): dict(
            official_site="https://inst2.gov",
            kept_urls=["https://inst2.gov/x"],
            scraped_urls=["https://inst2.gov/x"],
            extract_pairs=[("https://inst2.gov/x", "no")],
            final_status="no",
        ),
        _inst_id(3): dict(
            official_site="https://inst3.gov",
            kept_urls=["https://inst3.gov/p", "https://inst3.gov/q"],
            scraped_urls=["https://inst3.gov/p"],
            extract_pairs=[("https://inst3.gov/p", "unclear")],
            final_status="unclear",
        ),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_two_identical_runs_full_agreement(tmp_path: Path) -> None:
    spec = _identical_spec()
    a = _build_run(tmp_path, "run-a", spec)
    b = _build_run(tmp_path, "run-b", spec)

    report = compute_run_diff([a, b])

    assert report["n_institutions"] == 3
    assert report["n_runs"] == 2
    assert report["run_ids"] == ["run-a", "run-b"]
    for s in (
        "official_site_pick",
        "triage_keep_set",
        "scraped_pages",
        "extract_outcomes",
        "final_status",
    ):
        st = report["stages"][s]
        assert st["n_diverged"] == 0, s
        assert st["pct_agree"] == pytest.approx(1.0), s
        assert st["diverged"] == [], s
    assert report["stages"]["triage_keep_set"]["avg_overlap"] is None
    assert report["most_divergent_stage"] is None
    assert report["n_full_agreement"] == 3
    assert sorted(report["full_agreement"]) == [_inst_id(1), _inst_id(2), _inst_id(3)]


def test_known_triage_divergence_jaccard(tmp_path: Path) -> None:
    """Diverge INST-1's kept set; assert the exact Jaccard and delta lines."""
    spec_a = _identical_spec()
    spec_b = _identical_spec()
    # A: {a, b, c}  B: {a, b, d}  →  Jaccard = |{a,b}| / |{a,b,c,d}| = 2/4 = 0.5
    spec_a[_inst_id(1)]["kept_urls"] = ["u-a", "u-b", "u-c"]
    spec_b[_inst_id(1)]["kept_urls"] = ["u-a", "u-b", "u-d"]

    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)

    report = compute_run_diff([a, b])
    triage = report["stages"]["triage_keep_set"]

    assert triage["n_diverged"] == 1
    assert triage["pct_agree"] == pytest.approx(2 / 3, abs=1e-4)  # 2 of 3 insts agree
    entry = triage["diverged"][0]
    assert entry["institution_id"] == _inst_id(1)
    assert entry["overlap"] == pytest.approx(0.5)
    assert triage["avg_overlap"] == pytest.approx(0.5)
    # Deltas are relative to the baseline (first) run: B has u-d, lacks u-c.
    assert entry["deltas"]["run-b"] == {"only": ["u-d"], "missing": ["u-c"]}

    # No other stage diverged.
    for s in ("official_site_pick", "scraped_pages", "extract_outcomes", "final_status"):
        assert report["stages"][s]["n_diverged"] == 0, s
    assert report["most_divergent_stage"] == "triage_keep_set"


def test_missing_institution_counted_as_diverged(tmp_path: Path) -> None:
    spec_full = _identical_spec()
    spec_partial = _identical_spec()
    del spec_partial[_inst_id(2)]  # INST-2 absent from run-b entirely

    a = _build_run(tmp_path, "run-a", spec_full)
    b = _build_run(tmp_path, "run-b", spec_partial)

    report = compute_run_diff([a, b])

    # Union of institutions is still 3.
    assert report["n_institutions"] == 3

    # INST-2 diverges on every stage; run-b is flagged missing.
    for s in (
        "official_site_pick",
        "triage_keep_set",
        "scraped_pages",
        "extract_outcomes",
        "final_status",
    ):
        st = report["stages"][s]
        diverged_ids = {e["institution_id"] for e in st["diverged"]}
        assert _inst_id(2) in diverged_ids, s
        entry = next(e for e in st["diverged"] if e["institution_id"] == _inst_id(2))
        assert entry["missing_in"] == ["run-b"], s

    # Scalar stage: run-a has a value, run-b is missing.
    fs_entry = next(
        e
        for e in report["stages"]["final_status"]["diverged"]
        if e["institution_id"] == _inst_id(2)
    )
    assert fs_entry["values"]["run-a"] == "no"
    assert fs_entry["values"]["run-b"] is None

    assert _inst_id(2) not in report["full_agreement"]
    assert report["n_full_agreement"] == 2


def test_output_format_matches_exact_shape(tmp_path: Path) -> None:
    """Three-run scenario pinned to the exact agreed text shape.

    The agreed shape is asserted as an exact *prefix*: the DIAGNOSTICS block
    (2026-07-30) is strictly additive, so everything through the FULL AGREEMENT
    line must still match byte-for-byte.
    """
    base = _identical_spec()
    spec_a = _identical_spec()
    spec_b = _identical_spec()
    spec_c = _identical_spec()
    # INST-1 triage diverges only on run-c: a,b = {urlA, urlC}; c = {urlA, urlD}.
    for spec in (spec_a, spec_b):
        spec[_inst_id(1)]["kept_urls"] = ["https://x/urlA", "https://x/urlC"]
    spec_c[_inst_id(1)]["kept_urls"] = ["https://x/urlA", "https://x/urlD"]
    _ = base

    a = _build_run(tmp_path, "ladder-30-a", spec_a)
    b = _build_run(tmp_path, "ladder-30-b", spec_b)
    c = _build_run(tmp_path, "ladder-30-c", spec_c)

    report = compute_run_diff([a, b, c])
    text = render_run_diff_text(report)

    # N-way Jaccard: ∩ = {urlA}, ∪ = {urlA, urlC, urlD} → 1/3 = 33%.
    expected = (
        "Run-diff: ladder-30-a, ladder-30-b, ladder-30-c (n=3 institutions)\n"
        "\n"
        "DIVERGENCE BY STAGE\n"
        "official_site_pick     100% agree (0/3 diverged)\n"
        "triage_keep_set        67% agree (1/3 diverged, avg overlap 33%)\n"
        "scraped_pages          100% agree (0/3 diverged)\n"
        "extract_outcomes       100% agree (0/3 diverged)\n"
        "final_status           100% agree (0/3 diverged)\n"
        "→ Most divergence concentrates at triage_keep_set.\n"
        "\n"
        "DIVERGED INSTITUTIONS (triage_keep_set)\n"
        "INST-0000001: 33% overlap\n"
        "  ladder-30-c only: https://x/urlD\n"
        "  ladder-30-c missing: https://x/urlC\n"
        "\n"
        "FULL AGREEMENT: 2/3 institutions matched on every stage"
    )
    assert text.startswith(expected)
    # Nothing but the diagnostics block may follow the agreed shape.
    assert text[len(expected) :].lstrip("\n").startswith("=" * 72 + "\nDIAGNOSTICS")


def test_scalar_stage_divergence_renders_per_run_values(tmp_path: Path) -> None:
    spec_a = _identical_spec()
    spec_b = _identical_spec()
    spec_a[_inst_id(1)]["final_status"] = "yes"
    spec_b[_inst_id(1)]["final_status"] = "no"

    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)
    text = render_run_diff_text(compute_run_diff([a, b]))

    assert "DIVERGED INSTITUTIONS (final_status)" in text
    assert "INST-0000001:" in text
    assert "  run-a: yes" in text
    assert "  run-b: no" in text


def test_extract_outcomes_pair_divergence(tmp_path: Path) -> None:
    """A flipped has_genai_activity on the same URL diverges extract_outcomes."""
    spec_a = _identical_spec()
    spec_b = _identical_spec()
    spec_a[_inst_id(1)]["extract_pairs"] = [("https://inst1.gov/a", "yes")]
    spec_b[_inst_id(1)]["extract_pairs"] = [("https://inst1.gov/a", "no")]

    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)

    report = compute_run_diff([a, b])
    extract = report["stages"]["extract_outcomes"]
    assert extract["n_diverged"] == 1
    entry = extract["diverged"][0]
    # ∩ = {} (pairs differ on hga), ∪ = both pairs → 0/2 overlap.
    assert entry["overlap"] == pytest.approx(0.0)
    assert entry["deltas"]["run-b"]["only"] == ["https://inst1.gov/a (no)"]
    assert entry["deltas"]["run-b"]["missing"] == ["https://inst1.gov/a (yes)"]


def test_independent_stage_missing_artifact_does_not_block_others(tmp_path: Path) -> None:
    """A run with no triage artifact still compares every other stage."""
    spec_a = _identical_spec()
    spec_b = _identical_spec()
    # run-b's INST-1 never wrote 3_triage.json → empty kept set vs run-a's two.
    spec_b[_inst_id(1)].pop("kept_urls")

    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)

    report = compute_run_diff([a, b])
    # Triage diverges (2 kept vs empty); overlap 0.
    assert report["stages"]["triage_keep_set"]["n_diverged"] == 1
    assert report["stages"]["triage_keep_set"]["diverged"][0]["overlap"] == pytest.approx(0.0)
    # But official-site / scrape / extract / final still agree.
    for s in ("official_site_pick", "scraped_pages", "extract_outcomes", "final_status"):
        assert report["stages"][s]["n_diverged"] == 0, s


def test_report_json_serialisable(tmp_path: Path) -> None:
    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())
    report = compute_run_diff([a, b])
    loaded = json.loads(json.dumps(report))
    assert loaded["run_ids"] == report["run_ids"]


def test_fewer_than_two_dirs_raises(tmp_path: Path) -> None:
    a = _build_run(tmp_path, "run-a", _identical_spec())
    with pytest.raises(ValueError):
        compute_run_diff([a])


def test_institution_list_absent_falls_back_to_dirs(tmp_path: Path) -> None:
    """Institutions are inferred from disk when the manifest omits the list.

    Under storage layout v2 the manifest itself cannot be absent (it carries
    ``layout_version``; see
    :func:`test_run_diff_refuses_a_tree_without_a_layout_marker`), so this
    covers the surviving half of the old behaviour: a manifest with no
    ``run_id`` and no ``institutions`` list.
    """
    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())
    for d in (a, b):
        write_manifest(d, {})
    report = compute_run_diff([a, b])
    # run_id falls back to the directory name; institutions inferred from disk.
    assert report["run_ids"] == ["run-a", "run-b"]
    assert report["n_institutions"] == 3


def test_run_diff_refuses_a_tree_without_a_layout_marker(tmp_path: Path) -> None:
    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())
    (a / "manifest.json").unlink()
    with pytest.raises(RuntimeError, match="storage-layout-v2"):
        compute_run_diff([a, b])


def test_shared_run_id_disambiguated_by_directory(tmp_path: Path) -> None:
    """Two dirs with the SAME run_id (the determinism-test workflow) must not
    collapse into one report key — each run keeps a distinct, dir-labeled key."""
    spec = _identical_spec()
    a = _build_run(tmp_path / "x", "presweep-repro", spec)
    b = _build_run(tmp_path / "y", "presweep-repro", spec)

    report = compute_run_diff([a, b])

    # Both runs survive as distinct labels, each carrying its directory.
    assert len(report["run_ids"]) == 2
    assert len(set(report["run_ids"])) == 2
    assert all("presweep-repro [" in rid for rid in report["run_ids"])
    # Per-run breakdown dicts key off the labels, so a diverging scalar stage
    # must still show both runs rather than one overwriting the other.
    b_spec = _identical_spec()
    b_spec[_inst_id(1)]["final_status"] = "no"  # force a scalar divergence
    b2 = _build_run(tmp_path / "z", "presweep-repro", b_spec)
    report2 = compute_run_diff([a, b2])
    diverged = report2["stages"]["final_status"]["diverged"]
    assert diverged, "expected a final_status divergence"
    assert len(diverged[0]["values"]) == 2  # both runs represented, none dropped


def test_same_directory_twice_raises(tmp_path: Path) -> None:
    """The degenerate case — the same directory passed twice — is a hard error
    (nothing to compare), distinct from the legitimate shared-run_id case."""
    a = _build_run(tmp_path, "run-a", _identical_spec())
    with pytest.raises(ValueError, match="distinct run directories"):
        compute_run_diff([a, a])


# ---------------------------------------------------------------------------
# Diagnostics block (2026-07-30) — localisation, classifier stability, reason
# codes, pairwise overlap. Additive to the five agreed stages.
# ---------------------------------------------------------------------------


def _write_discovery(inst_dir: Path, links: list[str]) -> None:
    _write(
        inst_dir / "1a_discovery_general.json",
        {"queries": [{"query": "q", "language": "en"}],
         "records": [{"link": u, "title": "t"} for u in links]},
    )


def _write_decisions(inst_dir: Path, decisions: dict[str, str]) -> None:
    """Write a full triage artifact (keeps *and* drops)."""
    _write(
        inst_dir / "3_triage.json",
        {"decisions": [{"url": u, "decision": d} for u, d in decisions.items()]},
    )


def test_official_site_pick_compares_roots_not_subpages(tmp_path: Path) -> None:
    """Two runs picking different subpages of one host must not count as diverged."""
    spec_a, spec_b = _identical_spec(), _identical_spec()
    spec_a[_inst_id(1)]["official_site"] = "https://www.mcit.gov.qa/en/about-us"
    spec_b[_inst_id(1)]["official_site"] = "http://mcit.gov.qa/en/news"

    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)

    report = compute_run_diff([a, b])
    assert report["stages"]["official_site_pick"]["n_diverged"] == 0

    # A genuinely different host still diverges, and reports the canonical root.
    spec_b[_inst_id(1)]["official_site"] = "https://other.gov.qa/en/about-us"
    c = _build_run(tmp_path / "c", "run-c", spec_b)
    report2 = compute_run_diff([a, c])
    entry = report2["stages"]["official_site_pick"]["diverged"][0]
    assert entry["values"]["run-a"] == "https://mcit.gov.qa/"
    assert entry["values"]["run-c"] == "https://other.gov.qa/"


def test_a_pick_of_none_still_diverges_from_a_real_pick(tmp_path: Path) -> None:
    """Root normalisation must not turn a missing pick into agreement."""
    spec_a, spec_b = _identical_spec(), _identical_spec()
    spec_a[_inst_id(1)]["official_site"] = "https://mcit.gov.qa/en/about-us"
    spec_b[_inst_id(1)]["official_site"] = None

    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)
    assert compute_run_diff([a, b])["stages"]["official_site_pick"]["n_diverged"] == 1


def test_diagnostics_localises_churn_to_discovery(tmp_path: Path) -> None:
    """Identical triage decisions + different candidates → search is the source."""
    spec_a, spec_b = _identical_spec(), _identical_spec()
    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)

    # Same verdict on the one shared URL; run-b saw an extra candidate and kept it.
    _write_discovery(inst_dir_of(a, _inst_id(1)), ["u-shared"])
    _write_discovery(inst_dir_of(b, _inst_id(1)), ["u-shared", "u-extra"])
    _write_decisions(inst_dir_of(a, _inst_id(1)), {"u-shared": "keep"})
    _write_decisions(inst_dir_of(b, _inst_id(1)), {"u-shared": "keep", "u-extra": "keep"})

    diag = compute_run_diff([a, b])["diagnostics"]

    assert diag["discovery_candidates"]["n_diverged"] == 1
    assert diag["triage_candidate_set"]["n_diverged"] == 1
    # The classifier never changed its mind about a URL it saw in both runs.
    assert diag["triage_decision_flips"]["n_flipped_urls"] == 0
    assert diag["triage_decision_flips"]["n_institutions_with_flips"] == 0


def test_diagnostics_localises_churn_to_classifier(tmp_path: Path) -> None:
    """Identical candidates + flipped decision → the classifier is the source."""
    spec_a, spec_b = _identical_spec(), _identical_spec()
    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)

    _write_discovery(inst_dir_of(a, _inst_id(1)), ["u-1", "u-2"])
    _write_discovery(inst_dir_of(b, _inst_id(1)), ["u-1", "u-2"])
    _write_decisions(inst_dir_of(a, _inst_id(1)), {"u-1": "keep", "u-2": "drop"})
    _write_decisions(inst_dir_of(b, _inst_id(1)), {"u-1": "keep", "u-2": "keep"})

    diag = compute_run_diff([a, b])["diagnostics"]

    assert diag["discovery_candidates"]["n_diverged"] == 0
    assert diag["triage_candidate_set"]["n_diverged"] == 0  # same URLs offered
    flips = diag["triage_decision_flips"]
    assert flips["n_flipped_urls"] == 1
    # Pooled over all three institutions: INST-1's 2 URLs plus the 1 and 2 kept
    # URLs the shared fixture writes for INST-2 and INST-3.
    assert flips["n_common_urls"] == 5
    assert flips["flip_rate"] == pytest.approx(1 / 5)
    entry = next(e for e in flips["institutions"] if e["institution_id"] == _inst_id(1))
    assert entry["n_common"] == 2
    assert entry["flip_rate"] == pytest.approx(0.5)
    assert entry["flips"]["u-2"] == {"run-a": "drop", "run-b": "keep"}


def test_triage_decisions_prefer_keep_on_duplicate_rows(tmp_path: Path) -> None:
    """Duplicate rows for one URL must agree with _triage_keep_set (any keep wins).

    Otherwise the keep-set reader and the decision reader disagree about the same
    file and a flip is reported where none exists.
    """
    spec_a, spec_b = _identical_spec(), _identical_spec()
    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)
    # Same content, opposite row order — must not read as a flip.
    _write(inst_dir_of(a, _inst_id(1)) / "3_triage.json",
           {"decisions": [{"url": "u", "decision": "keep"},
                          {"url": "u", "decision": "drop"}]})
    _write(inst_dir_of(b, _inst_id(1)) / "3_triage.json",
           {"decisions": [{"url": "u", "decision": "drop"},
                          {"url": "u", "decision": "keep"}]})

    report = compute_run_diff([a, b])
    assert report["stages"]["triage_keep_set"]["n_diverged"] == 0
    assert report["diagnostics"]["triage_decision_flips"]["n_flipped_urls"] == 0


def test_final_status_reason_codes_separate_unfinished_from_flip(tmp_path: Path) -> None:
    """An absent validate artifact must not read the same as a null verdict."""
    spec_absent, spec_null, spec_ok = (
        _identical_spec(), _identical_spec(), _identical_spec()
    )
    spec_absent[_inst_id(1)].pop("final_status")  # never written
    a = _build_run(tmp_path, "run-a", spec_absent)
    b = _build_run(tmp_path, "run-b", spec_null)
    c = _build_run(tmp_path, "run-c", spec_ok)
    # run-b wrote the artifact but declined to decide.
    _write(inst_dir_of(b, _inst_id(1)) / "6_validate.json",
           {"institution": {"has_genai_activity": None}})

    reasons = compute_run_diff([a, b, c])["diagnostics"]["final_status_reasons"]
    codes = reasons["divergent_institutions"][_inst_id(1)]
    assert codes["run-a"] == "artifact_absent"
    assert codes["run-b"] == "verdict_null"
    assert codes["run-c"] == "ok"
    assert reasons["tallies"]["run-a"]["artifact_absent"] == 1


def test_corrupt_validate_artifact_reported_as_unreadable(tmp_path: Path) -> None:
    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())
    (inst_dir_of(b, _inst_id(1)) / "6_validate.json").write_text("{not json", encoding="utf-8")

    reasons = compute_run_diff([a, b])["diagnostics"]["final_status_reasons"]
    assert reasons["divergent_institutions"][_inst_id(1)]["run-b"] == "artifact_unreadable"


def test_mean_pairwise_overlap_beats_nway_on_two_of_three(tmp_path: Path) -> None:
    """Two runs agreeing perfectly and a third lacking the URL: N-way says 0%."""
    spec_a, spec_b, spec_c = _identical_spec(), _identical_spec(), _identical_spec()
    spec_a[_inst_id(1)]["kept_urls"] = ["u-only"]
    spec_b[_inst_id(1)]["kept_urls"] = ["u-only"]
    spec_c[_inst_id(1)]["kept_urls"] = []

    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)
    c = _build_run(tmp_path, "run-c", spec_c)

    report = compute_run_diff([a, b, c])
    entry = report["stages"]["triage_keep_set"]["diverged"][0]
    assert entry["overlap"] == pytest.approx(0.0)  # N-way: intersection empty

    stats = report["diagnostics"]["set_stage_stats"]["triage_keep_set"]
    # Pairs: a-b = 1.0, a-c = 0.0, b-c = 0.0 → 1/3 for this institution.
    # The other two institutions agree, so the pooled mean is (1/3 + 1 + 1)/3.
    assert stats["mean_pairwise_overlap_all"] == pytest.approx((1 / 3 + 2) / 3, abs=1e-3)
    # And the histogram says the URL was held by 2 of 3 runs.
    assert stats["presence_histogram"]["2"] >= 1


def test_presence_histogram_does_not_conflate_urls_across_institutions(
    tmp_path: Path,
) -> None:
    """The same URL under two institutions is two members, not one seen twice."""
    spec = _identical_spec()
    for i in (1, 2):
        spec[_inst_id(i)]["kept_urls"] = ["u-dup"]
    a = _build_run(tmp_path, "run-a", spec)
    b = _build_run(tmp_path, "run-b", spec)

    hist = compute_run_diff([a, b])["diagnostics"]["set_stage_stats"][
        "triage_keep_set"
    ]["presence_histogram"]
    # Unanimous members: INST-1's u-dup, INST-2's u-dup (distinct members, not
    # one URL seen four times), plus the two kept URLs the fixture gives INST-3.
    assert hist["2"] == 4


def test_run_completeness_census_counts_artifacts(tmp_path: Path) -> None:
    spec_full = _identical_spec()
    spec_thin = _identical_spec()
    spec_thin[_inst_id(1)].pop("final_status")
    spec_thin[_inst_id(2)].pop("final_status")

    a = _build_run(tmp_path, "run-a", spec_full)
    b = _build_run(tmp_path, "run-b", spec_thin)

    census = compute_run_diff([a, b])["diagnostics"]["run_completeness"]
    assert census["run-a"]["artifacts"]["6_validate.json"] == 3
    assert census["run-b"]["artifacts"]["6_validate.json"] == 1
    assert census["run-a"]["n_institutions"] == 3


def test_empty_histogram_is_not_reported_as_agreement(tmp_path: Path) -> None:
    """No discovery artifacts anywhere must not render as a clean 100%."""
    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())
    text = render_run_diff_text(compute_run_diff([a, b]))
    assert "artifact absent in every run" in text


def test_diagnostics_json_serialisable(tmp_path: Path) -> None:
    """Histogram keys must be strings so the report survives a JSON round-trip."""
    spec_a, spec_b = _identical_spec(), _identical_spec()
    spec_b[_inst_id(1)]["kept_urls"] = ["u-x"]
    a = _build_run(tmp_path, "run-a", spec_a)
    b = _build_run(tmp_path, "run-b", spec_b)

    report = compute_run_diff([a, b])
    loaded = json.loads(json.dumps(report))
    assert loaded["diagnostics"]["set_stage_stats"] == (
        report["diagnostics"]["set_stage_stats"]
    )


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def test_cli_run_diff_parses(tmp_path: Path) -> None:
    from g3o.cli import build_parser

    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())

    parser = build_parser()
    args = parser.parse_args(["run-diff", str(a), str(b)])
    assert callable(args.func)
    assert args.run_dirs == [a, b]


def test_cli_run_diff_writes_json_and_prints(tmp_path: Path, capsys: Any) -> None:
    from g3o.cli import _cmd_run_diff, build_parser

    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())

    parser = build_parser()
    args = parser.parse_args(["run-diff", str(a), str(b)])
    rc = _cmd_run_diff(args)

    assert rc == 0
    json_path = a / "_run_diff_report.json"
    assert json_path.is_file()
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["n_institutions"] == 3
    out = capsys.readouterr().out
    assert "Run-diff: run-a, run-b (n=3 institutions)" in out
    assert "FULL AGREEMENT: 3/3" in out


# ---------------------------------------------------------------------------
# Storage layout v2 — run-level entries are no longer counted as institutions
# ---------------------------------------------------------------------------


def test_run_level_entries_are_not_counted_as_institutions(tmp_path: Path) -> None:
    """Regression: ``final/`` used to be counted as an institution.

    Pre-v2, ``_run_institutions`` filtered ``run_dir.iterdir()`` on
    ``startswith("_")`` and ``!= ".done"`` only. ``final/`` (the Stage-7 CSV
    directory) matched neither, so every run that had reached Stage 7 reported
    one phantom institution and diverged against a run that had not. ``.done``
    never was a direct child of a run dir (it lives at ``_state/.done``), so
    that half of the filter was dead code. Both go away structurally under
    layout v2: the walk only ever descends ``institutions/``.
    """
    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())
    # run-a has completed Stage 7 and been reported on; run-b has not.
    (a / "final").mkdir()
    (a / "final" / "g3o_activities_v1.csv").write_text("global_row_id\n", encoding="utf-8")
    (a / "_state" / ".done").mkdir(parents=True)
    (a / "_state" / ".done" / "validate.json").write_text("{}", encoding="utf-8")
    (a / "_run_diff_report.json").write_text("{}", encoding="utf-8")
    (a / "attrition.jsonl").write_text("", encoding="utf-8")

    report = compute_run_diff([a, b])

    assert report["n_institutions"] == 3
    assert _run_institutions(a) == _run_institutions(b)
    for phantom in ("final", "_state", ".done", "attrition.jsonl"):
        assert phantom not in _run_institutions(a)
    # And Stage 7 completing on one side does not manufacture divergence.
    assert sorted(report["full_agreement"]) == [_inst_id(1), _inst_id(2), _inst_id(3)]
