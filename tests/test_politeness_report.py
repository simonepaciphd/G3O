"""Tests for `g3o.report.politeness` — the per-host politeness verification
built on real `_scrape_telemetry.jsonl` request timestamps.

Covers: the normal all-pass case, a genuine sub-floor violation (FAIL), a run
with no telemetry ledger at all (UNAVAILABLE, not a silent PASS), a host with
only one request (no spacing to violate), and the ``write_politeness_report``
JSON persistence + ``render_politeness_report_text`` summary format.
"""

from __future__ import annotations

import json
from pathlib import Path

from g3o.common import scrape_telemetry
from g3o.report.politeness import (
    compute_politeness_report,
    render_politeness_report_text,
    write_politeness_report,
)

_CONFIG = {"max_workers": 4, "scrape_host_delay_seconds": 1.0}


def _write_manifest(run_dir: Path, *, config: dict = _CONFIG) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_dir.name, "config": config}), encoding="utf-8"
    )


def _record(run_dir: Path, *, host: str, ts: str, inst: str = "INST-0001") -> None:
    # Bypass scrape_telemetry.record's real-clock stamping so tests control ts.
    rec = {
        "ts": ts, "request_id": f"{host}-{ts}", "institution_id": inst,
        "stage": "scrape", "hostname": host, "url": f"https://{host}/p",
    }
    path = scrape_telemetry.ledger_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def test_all_hosts_pass(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir)
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:00.000Z")
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:01.050Z")
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:02.200Z")
    _record(run_dir, host="b.gov", ts="2026-07-27T23:00:00.500Z")
    _record(run_dir, host="b.gov", ts="2026-07-27T23:00:01.600Z")

    report = compute_politeness_report(run_dir)
    assert report["available"] is True
    assert report["run_id"] == "r1"
    assert report["max_workers"] == 4
    assert report["min_spacing_required_seconds"] == 1.0
    assert report["hosts_checked"] == 2
    assert report["total_requests"] == 5
    assert report["overall_result"] == "PASS"
    assert report["hosts_failing"] == []
    assert set(report["hosts_passing"]) == {"a.gov", "b.gov"}

    a = report["hosts"]["a.gov"]
    assert a["n_requests"] == 3
    assert a["min_spacing_seconds"] == 1.05
    assert a["violations"] == 0
    assert a["pass"] is True


def test_violation_fails_that_host_and_overall(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir)
    # 0.4s gap on c.gov — a genuine sub-floor violation.
    _record(run_dir, host="c.gov", ts="2026-07-27T23:00:00.000Z")
    _record(run_dir, host="c.gov", ts="2026-07-27T23:00:00.400Z")
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:00.000Z")
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:01.100Z")

    report = compute_politeness_report(run_dir)
    assert report["overall_result"] == "FAIL"
    assert report["hosts_failing"] == ["c.gov"]
    c = report["hosts"]["c.gov"]
    assert c["min_spacing_seconds"] == 0.4
    assert c["violations"] == 1
    assert c["pass"] is False
    assert report["hosts"]["a.gov"]["pass"] is True


def test_single_request_host_passes_trivially(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir)
    _record(run_dir, host="only-one.gov", ts="2026-07-27T23:00:00.000Z")

    report = compute_politeness_report(run_dir)
    host = report["hosts"]["only-one.gov"]
    assert host["n_requests"] == 1
    assert host["min_spacing_seconds"] is None
    assert host["pass"] is True
    assert report["overall_result"] == "PASS"


def test_no_telemetry_is_unavailable_not_pass(tmp_path: Path):
    """A run with no _scrape_telemetry.jsonl (e.g. it predates this feature,
    or Stage 4 made no real request) must report UNAVAILABLE — never a blind
    PASS, which would misrepresent an unverified run as a verified one."""
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir)

    report = compute_politeness_report(run_dir)
    assert report["available"] is False
    assert report["overall_result"] == "UNAVAILABLE"
    assert "reason" in report


def test_default_threshold_when_config_missing(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir, config={})  # no scrape_host_delay_seconds in config
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:00.000Z")
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:02.000Z")

    report = compute_politeness_report(run_dir)
    assert report["min_spacing_required_seconds"] == 1.0  # DEFAULT_HOST_DELAY_SECONDS


def test_write_persists_json(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir)
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:00.000Z")
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:01.500Z")

    report = write_politeness_report(run_dir)
    on_disk = json.loads((run_dir / "politeness_verification.json").read_text(encoding="utf-8"))
    assert on_disk == report
    assert on_disk["overall_result"] == "PASS"


def test_render_text_includes_summary_fields(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir)
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:00.000Z")
    _record(run_dir, host="a.gov", ts="2026-07-27T23:00:01.500Z")

    text = render_politeness_report_text(compute_politeness_report(run_dir))
    assert "PER-HOST POLITENESS VERIFICATION" in text
    assert "Run ID: r1" in text
    assert "Workers: 4" in text
    assert "Hosts checked: 1" in text
    assert "Total requests: 2" in text
    assert "Overall result: PASS" in text
    assert "a.gov" in text


def test_render_text_unavailable(tmp_path: Path):
    run_dir = tmp_path / "runs" / "r1"
    _write_manifest(run_dir)
    text = render_politeness_report_text(compute_politeness_report(run_dir))
    assert "UNAVAILABLE" in text
