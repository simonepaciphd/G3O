"""Tests for g3o.report — pipeline health report on a fixture smoke run.

The fixture builds a minimal but realistic 10-institution run directory in a
temp path.  Institutions are assigned staggered outcomes so every stage has at
least one green and one attrition path; flags are asserted against known
thresholds so we catch regressions in the computation logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from g3o.common import attrition as _attrition
from g3o.report import HealthThresholds, compute_health_report, render_text_report

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _inst_id(n: int) -> str:
    return f"INST-{n:07d}"


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_fixture_run(run_dir: Path, n: int = 10) -> None:
    """Build a minimal smoke-run directory for *n* institutions.

    Scenario (designed to produce a mix of flags):
      • All 10 institutions get Stage 1a artifacts.
      • 8 / 10 have ≥1 URL in 1a (2 returned empty).
      • 7 / 10 get Stage 2 official-site artifacts; 1 is bypassed from master.
      • 6 / 10 get Stage 1b artifacts (those with official site, minus 1 skip).
      • 8 / 10 get Stage 3 triage artifacts; 7 have ≥1 kept URL.
      • Stage 4: 7 institutions × 2 pages each = 14 scraped;
                 1 institution has 1 robots-blocked URL.
      • Stage 5: 1 page empty-dropped; 2 pages truncated; 12 extracts.
      • Stage 6: 7 institutions consolidated; 2 yes / 3 no / 2 unclear.
    """
    manifest = {
        "run_id": "test-smoke-run",
        "run_date": "2026-06-30",
        "run_kind": "pre-sweep",
        "n_institutions_drawn": n,
        "stages_planned": [
            "discovery_general",
            "classify_official_site",
            "discovery_site_restricted",
            "classify_triage",
            "scrape",
            "extract",
            "validate",
        ],
        "institutions": [_inst_id(i) for i in range(1, n + 1)],
    }
    _write(run_dir / "manifest.json", manifest)

    # ── attrition ledger ──────────────────────────────────────────────────────
    # Reset the in-process dedup cache so repeated test calls don't collide.
    _attrition._reset_cache()
    # Stage 1a: 0 of 10 serper failures (all complete; 2 just return 0 records)
    # Stage 2: 1 parse failure
    _attrition.record(
        run_dir, institution_id=_inst_id(9), stage="classify_official_site",
        reason="parse_failed", detail="json decode error",
    )
    # Stage 4: 1 robots-disallowed, 1 scrape-failed
    _attrition.record(
        run_dir, institution_id=_inst_id(7), stage="scrape",
        reason="robots_disallowed", url="https://inst7.gov/blocked",
    )
    _attrition.record(
        run_dir, institution_id=_inst_id(8), stage="scrape",
        reason="scrape_failed", url="https://inst8.gov/down",
        detail="connection timeout",
    )
    # Stage 5: 1 empty-drop, 2 truncations
    _attrition.record(
        run_dir, institution_id=_inst_id(1), stage="extract",
        reason="empty_page_dropped", url="https://inst1.gov/empty",
        detail="stripped_len=3",
    )
    _attrition.record(
        run_dir, institution_id=_inst_id(2), stage="extract",
        reason="page_text_truncated", url="https://inst2.gov/long",
        detail="rule=head_tail",
    )
    _attrition.record(
        run_dir, institution_id=_inst_id(3), stage="extract",
        reason="page_text_truncated", url="https://inst3.gov/long",
        detail="rule=head_tail",
    )

    # ── per-institution artifacts ─────────────────────────────────────────────
    for i in range(1, n + 1):
        inst_id = _inst_id(i)
        inst_dir = run_dir / inst_id
        inst_dir.mkdir(parents=True, exist_ok=True)

        # Stage 1a: all 10 get artifacts; institutions 9, 10 return 0 records.
        n_1a_records = 0 if i >= 9 else 5
        _write(
            inst_dir / "1a_discovery_general.json",
            {
                "queries": [{"query": f"GenAI {inst_id}", "language": "en"}],
                "records": [{"link": f"https://inst{i}.gov/p{j}"} for j in range(n_1a_records)],
            },
        )

        # Stage 2: institutions 1–7 get artifacts; 8 is bypassed; 9+ skipped.
        if i == 8:
            _write(
                inst_dir / "2_official_site.json",
                {"bypassed": True, "source": "master_csv", "url": "https://inst8.gov"},
            )
        elif i <= 7:
            url = f"https://inst{i}.gov" if i <= 6 else None  # inst7: LLM found nothing
            _write(
                inst_dir / "2_official_site.json",
                {"url": url, "confidence": "high" if url else None, "rationale": "ok"},
            )

        # Stage 1b: institutions 1–6 get 1b artifacts (those with official site from 2).
        if i <= 6:
            _write(
                inst_dir / "1b_discovery_site_restricted.json",
                {
                    "site_domain": f"inst{i}.gov",
                    "queries": [],
                    "records": [{"link": f"https://inst{i}.gov/ai-{j}"} for j in range(3)],
                },
            )

        # Stage 3 triage: institutions 1–8 get triage; 1–7 have ≥1 kept URL.
        # Institution 8 gets all-drop results.
        if i <= 8:
            kept_count = 2 if i <= 7 else 0
            decisions = [
                {"url": f"https://inst{i}.gov/p{j}", "decision": "keep" if j < kept_count else "drop", "rationale": "ok"}
                for j in range(4)
            ]
            _write(inst_dir / "3_triage.json", {"decisions": decisions})

        # Stage 4 scrape: institutions 1–7 each get 2 scrape files.
        # (institution 7 had robots-blocked URL — the scrape dir still has 2 files
        #  from other URLs; institution 8 had one scrape_failed so 0 files.)
        if i <= 7:
            scrape_dir = inst_dir / "scrape"
            scrape_dir.mkdir(exist_ok=True)
            for j in range(2):
                _write(
                    scrape_dir / f"hash{i}{j}.json",
                    {
                        "url": f"https://inst{i}.gov/p{j}",
                        "text": f"GenAI deployment text for institution {i} page {j}. " * 20,
                        "fetch_metadata": {"access_date": "2026-06-30", "status_code": 200},
                    },
                )

        # Stage 5 extract: institutions 1–7 each get 2 extract files, except
        # institution 1 which lost one page to empty-drop → 1 extract.
        if i <= 7:
            n_extracts = 1 if i == 1 else 2
            extract_dir = inst_dir / "extract"
            extract_dir.mkdir(exist_ok=True)
            for j in range(n_extracts):
                _write(
                    extract_dir / f"hash{i}{j}.json",
                    {"institution_id": inst_id, "page_url": f"https://inst{i}.gov/p{j}"},
                )

        # Stage 6 validate: institutions 1–7 get consolidated outputs.
        # has_genai_activity distribution: i<=2 → yes, i<=5 → no, else → unclear
        if i <= 7:
            if i <= 2:
                hga = "yes"
            elif i <= 5:
                hga = "no"
            else:
                hga = "unclear"
            _write(
                inst_dir / "6_validate.json",
                {
                    "consolidation_metadata": {
                        "institution_id": inst_id,
                        "n_input_pages": 2,
                        "n_input_rows": 2,
                        "model_label": "test-model",
                        "notes": "fixture",
                    },
                    "institution": {
                        "institution_id": inst_id,
                        "institution_name": f"Institution {i}",
                        "country": "TESTLAND",
                        "branch_of_government": "executive",
                        "level_of_government": "national",
                        "has_genai_activity": hga,
                        "institution_summary": "summary",
                        "institution_search_languages": "en",
                    },
                    "activities": [],
                    "sources": [
                        {
                            "source_id": "S1",
                            "activity_id": "_NA_",
                            "source_url": f"https://inst{i}.gov/p0",
                            "source_credibility": "official",
                            "source_type": "webpage",
                            "genai_evidence": "confirms_absence",
                            "source_snippet": "no genai",
                        }
                    ],
                },
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def fixture_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "test-smoke-run"
    run_dir.mkdir()
    _build_fixture_run(run_dir)
    return run_dir


def test_report_returns_expected_keys(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    assert report["run_id"] == "test-smoke-run"
    assert report["n_institutions"] == 10
    assert "stages" in report
    assert "overall_flag" in report
    for key in (
        "1a_discovery_general",
        "2_classify_official_site",
        "1b_discovery_site_restricted",
        "3_classify_triage",
        "4_scrape",
        "5_extract",
        "6_validate",
    ):
        assert key in report["stages"], f"missing stage key: {key}"


def test_stage_1a_counts(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    s = report["stages"]["1a_discovery_general"]
    assert s["n_institutions_in"] == 10
    # institutions 9 and 10 have 0 records
    assert s["n_institutions_with_urls"] == 8
    assert s["total_candidate_urls"] == 8 * 5  # 8 institutions × 5 URLs each
    # 80% pass-rate is exactly at the warn threshold default; flag should be warn or green
    assert s["flag"] in ("green", "warn")
    assert s["pct_institutions_with_urls"] == pytest.approx(0.8, abs=0.01)


def test_stage_2_counts(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    s = report["stages"]["2_classify_official_site"]
    # Institutions 1–6 have official site; 7 got None from LLM; 8 bypassed
    assert s["n_official_site_found"] == 7  # insts 1–6 (non-None url) + inst 8 (bypassed)
    assert s["n_bypassed_from_master"] == 1
    assert s["n_parse_failed"] == 1  # inst 9 attrition record


def test_stage_1b_counts(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    s = report["stages"]["1b_discovery_site_restricted"]
    # n_1b_eligible = n_official_site = 7 (insts 1-6 + 8)
    assert s["n_institutions_eligible"] == 7
    # Only insts 1–6 got 1b artifacts (inst 8 bypassed but no 1b written in fixture)
    assert s["n_institutions_with_1b_urls"] == 6
    assert s["total_1b_urls"] == 6 * 3  # 6 institutions × 3 URLs each


def test_stage_3_triage(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    s = report["stages"]["3_classify_triage"]
    # 8 institutions got triage artifacts; each has 4 URLs
    assert s["n_total_candidate_urls"] == 8 * 4
    # inst 8: all-drop; insts 1–7: 2 kept each = 14 kept
    assert s["n_urls_kept"] == 7 * 2
    assert s["n_urls_dropped"] == 8 * 4 - 7 * 2
    assert s["n_institutions_with_kept_url"] == 7
    assert s["pct_institutions_with_kept_url"] == pytest.approx(7 / 8, abs=0.01)


def test_stage_4_scrape(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    s = report["stages"]["4_scrape"]
    # attempted = total_urls_kept = 7 × 2 = 14
    assert s["n_urls_attempted"] == 14
    # scraped = insts 1–7 × 2 pages each = 14
    assert s["n_pages_scraped"] == 14
    assert s["n_robots_disallowed"] == 1
    assert s["n_scrape_failed"] == 1
    assert s["n_institutions_with_pages"] == 7


def test_stage_5_extract(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    s = report["stages"]["5_extract"]
    assert s["n_pages_in"] == 14  # all scraped pages
    assert s["n_empty_dropped"] == 1
    assert s["n_pages_eligible"] == 13
    assert s["n_pages_truncated"] == 2
    # insts 1 → 1 extract; insts 2–7 → 2 each = 1 + 6*2 = 13
    assert s["n_extracts"] == 13
    assert s["pct_extracted_of_eligible"] == pytest.approx(13 / 13, abs=0.01)
    assert s["n_institutions_with_extracts"] == 7


def test_stage_6_validate(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    s = report["stages"]["6_validate"]
    assert s["n_institutions_in"] == 7
    assert s["n_consolidated"] == 7
    assert s["pct_consolidated"] == pytest.approx(1.0)
    # Fixture: i<=2 → yes, 3<=i<=5 → no, 6<=i<=7 → unclear.
    hga = s["has_genai_activity"]
    assert hga["yes"] == 2
    assert hga["no"] == 3
    assert hga["unclear"] == 2


def test_overall_flag_is_string(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    assert report["overall_flag"] in ("green", "warn", "fail", "not_run")


def test_attrition_summary_present(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    top = report["attrition_top_reasons"]
    assert isinstance(top, list)
    reasons = {(r["stage"], r["reason"]) for r in top}
    assert ("scrape", "robots_disallowed") in reasons
    assert ("scrape", "scrape_failed") in reasons
    assert ("extract", "empty_page_dropped") in reasons
    assert ("extract", "page_text_truncated") in reasons


def test_thresholds_used_present(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    th = report["thresholds_used"]
    assert "discovery_general_warn_pct" in th
    assert "validate_unclear_warn_pct" in th


def test_custom_thresholds_change_flag(fixture_run: Path) -> None:
    # Lower the 1a warn threshold to 0.5 → should be green (8/10 = 80%)
    tight = HealthThresholds(
        discovery_general_warn_pct=0.95,  # demand 95% → 80% triggers warn
        discovery_general_fail_pct=0.70,
    )
    report = compute_health_report(fixture_run, thresholds=tight)
    assert report["stages"]["1a_discovery_general"]["flag"] == "warn"

    loose = HealthThresholds(
        discovery_general_warn_pct=0.50,
        discovery_general_fail_pct=0.30,
    )
    report2 = compute_health_report(fixture_run, thresholds=loose)
    assert report2["stages"]["1a_discovery_general"]["flag"] == "green"


def test_thresholds_from_json(tmp_path: Path, fixture_run: Path) -> None:
    th_file = tmp_path / "thresholds.json"
    th_file.write_text(
        json.dumps({"discovery_general_warn_pct": 0.99, "discovery_general_fail_pct": 0.90}),
        encoding="utf-8",
    )
    th = HealthThresholds.from_json(th_file)
    assert th.discovery_general_warn_pct == 0.99
    assert th.discovery_general_fail_pct == 0.90
    # Other fields keep defaults
    assert th.scrape_success_warn_pct == HealthThresholds().scrape_success_warn_pct


def test_render_text_contains_key_lines(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    text = render_text_report(report)
    assert "Stage 1a" in text
    assert "Stage 2" in text
    assert "Stage 3" in text
    assert "Stage 4" in text
    assert "Stage 5" in text
    assert "Stage 6" in text
    assert "has_genai_activity" in text
    assert "PI-tunable" in text


def test_render_text_shows_overall_flag(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    text = render_text_report(report)
    overall = report["overall_flag"].upper()
    assert overall in text


def test_manifest_absent_falls_back_to_dirs(tmp_path: Path) -> None:
    """compute_health_report should work even without manifest.json."""
    run_dir = tmp_path / "no-manifest-run"
    run_dir.mkdir()
    _attrition._reset_cache()
    # Create two institution dirs without a manifest
    for i in (1, 2):
        inst_dir = run_dir / _inst_id(i)
        inst_dir.mkdir()
        _write(
            inst_dir / "1a_discovery_general.json",
            {"queries": [], "records": [{"link": f"https://inst{i}.gov"}]},
        )
    report = compute_health_report(run_dir)
    assert report["n_institutions"] == 2
    assert report["stages"]["1a_discovery_general"]["n_institutions_with_urls"] == 2


def test_report_json_serialisable(fixture_run: Path) -> None:
    report = compute_health_report(fixture_run)
    dumped = json.dumps(report)
    loaded = json.loads(dumped)
    assert loaded["run_id"] == report["run_id"]


def test_cli_presweep_report(fixture_run: Path) -> None:
    """CLI wiring: _cmd_presweep_report writes JSON and returns exit-code."""
    from g3o.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["presweep-report", "--run-dir", str(fixture_run)])
    # Just verify the func attribute is wired (actual invocation would write to stdout).
    assert callable(args.func)
    assert args.run_dir == fixture_run
    assert args.json is False
    assert args.thresholds is None
