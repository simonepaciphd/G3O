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
    _write(
        run_dir / "manifest.json",
        {"run_id": run_id, "institutions": sorted(institutions)},
    )
    for inst_id, spec in institutions.items():
        _write_institution(run_dir / inst_id, **spec)
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
    """Three-run scenario pinned to the exact agreed text shape."""
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
    assert text == expected


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


def test_manifest_absent_falls_back_to_dirs(tmp_path: Path) -> None:
    a = _build_run(tmp_path, "run-a", _identical_spec())
    b = _build_run(tmp_path, "run-b", _identical_spec())
    (a / "manifest.json").unlink()
    (b / "manifest.json").unlink()
    report = compute_run_diff([a, b])
    # run_id falls back to the directory name; institutions inferred from subdirs.
    assert report["run_ids"] == ["run-a", "run-b"]
    assert report["n_institutions"] == 3


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
