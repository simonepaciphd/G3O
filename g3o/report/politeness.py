"""Per-host politeness verification — real request spacing vs. the courtesy
delay a run was configured with (``scrape_host_delay_seconds``).

:class:`g3o.scrape.politeness.HostThrottle` enforces the delay purely
in-memory (``time.monotonic()``, discarded once the wait is computed) — it
never wrote a record of when a request actually happened. :mod:`g3o.common.
scrape_telemetry` closes that gap by logging one timestamped record per real
outbound request to ``runs/<run_id>/_scrape_telemetry.jsonl``. This module is
the audit that reads that ledger back: group by host, sort chronologically,
compute consecutive spacing, and check the configured floor actually held
under concurrency.

- :func:`compute_politeness_report` -> the report dict
- :func:`write_politeness_report`   -> persists it to
  ``runs/<run_id>/politeness_verification.json``
- :func:`render_politeness_report_text` -- the stdout renderer, following
  :mod:`g3o.report.render`'s text-renderer convention.

Read-only from disk except for the ``politeness_verification.json`` write. No
network calls.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from g3o.common.scrape_telemetry import read_records
from g3o.scrape.politeness import DEFAULT_HOST_DELAY_SECONDS


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")


def _host_stats(records: list[dict[str, Any]], *, min_spacing_required: float) -> dict[str, Any]:
    times = sorted(_parse_ts(r["ts"]) for r in records)
    n = len(times)
    if n < 2:
        return {
            "n_requests": n,
            "min_spacing_seconds": None,
            "median_spacing_seconds": None,
            "mean_spacing_seconds": None,
            "violations": 0,
            "pass": True,
            "note": "fewer than 2 requests — no spacing to violate" if n == 1 else "no requests",
        }
    spacings = [
        (times[i + 1] - times[i]).total_seconds() for i in range(n - 1)
    ]
    violations = sum(1 for s in spacings if s < min_spacing_required)
    min_spacing = min(spacings)
    return {
        "n_requests": n,
        "min_spacing_seconds": round(min_spacing, 3),
        "median_spacing_seconds": round(statistics.median(spacings), 3),
        "mean_spacing_seconds": round(statistics.mean(spacings), 3),
        "violations": violations,
        "pass": min_spacing >= min_spacing_required,
    }


def compute_politeness_report(run_dir: str | Path) -> dict[str, Any]:
    """Build the per-host politeness verification report.

    ``min_spacing_required`` defaults to the run's own configured
    ``scrape_host_delay_seconds`` (falling back to
    :data:`g3o.scrape.politeness.DEFAULT_HOST_DELAY_SECONDS`) so the audit
    checks the run against the policy it was actually configured with.
    """
    run_dir = Path(run_dir)
    manifest = _load_manifest(run_dir)
    run_id = manifest.get("run_id", run_dir.name)
    config = manifest.get("config", {})
    max_workers = config.get("max_workers")
    min_spacing_required = config.get("scrape_host_delay_seconds", DEFAULT_HOST_DELAY_SECONDS)

    records = read_records(run_dir)
    if not records:
        return {
            "run_id": run_id,
            "max_workers": max_workers,
            "min_spacing_required_seconds": min_spacing_required,
            "available": False,
            "reason": "no _scrape_telemetry.jsonl records found for this run "
            "(either the run predates request-level telemetry, or Stage 4 "
            "never made a real outbound request)",
            "hosts": {},
            "overall_result": "UNAVAILABLE",
        }

    by_host: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_host.setdefault(r["hostname"], []).append(r)

    hosts = {
        host: _host_stats(recs, min_spacing_required=min_spacing_required)
        for host, recs in sorted(by_host.items())
    }
    hosts_passing = [h for h, s in hosts.items() if s["pass"]]
    hosts_failing = [h for h, s in hosts.items() if not s["pass"]]
    observed_mins = [s["min_spacing_seconds"] for s in hosts.values() if s["min_spacing_seconds"] is not None]

    return {
        "run_id": run_id,
        "max_workers": max_workers,
        "min_spacing_required_seconds": min_spacing_required,
        "available": True,
        "hosts_checked": len(hosts),
        "total_requests": len(records),
        "minimum_observed_spacing_seconds": min(observed_mins) if observed_mins else None,
        "hosts": hosts,
        "hosts_passing": hosts_passing,
        "hosts_failing": hosts_failing,
        "overall_result": "PASS" if not hosts_failing else "FAIL",
    }


def render_politeness_report_text(report: dict[str, Any]) -> str:
    """Render a politeness report dict as the human-readable summary block."""
    lines: list[str] = []
    w = lines.append
    w("=" * 78)
    w("  G3O Per-Host Politeness Verification")
    w("=" * 78)
    w(f"  Run ID  : {report.get('run_id', '?')}")
    w(f"  Workers : {report.get('max_workers')}")
    w(f"  Required min spacing per host: {report.get('min_spacing_required_seconds')}s")
    w("")

    if not report.get("available"):
        w(f"  UNAVAILABLE — {report.get('reason')}")
        return "\n".join(lines)

    header = (
        f"  {'Host':<40} {'Requests':>8} {'Min':>8} {'Median':>8} "
        f"{'Mean':>8} {'Violations':>10}  PASS/FAIL"
    )
    w(header)
    w("  " + "-" * (len(header) - 2))
    for host, s in report["hosts"].items():
        min_s = f"{s['min_spacing_seconds']:.3f}" if s["min_spacing_seconds"] is not None else "n/a"
        med_s = f"{s['median_spacing_seconds']:.3f}" if s["median_spacing_seconds"] is not None else "n/a"
        mean_s = f"{s['mean_spacing_seconds']:.3f}" if s["mean_spacing_seconds"] is not None else "n/a"
        verdict = "PASS" if s["pass"] else "FAIL"
        w(
            f"  {host:<40} {s['n_requests']:>8} {min_s:>8} {med_s:>8} "
            f"{mean_s:>8} {s['violations']:>10}  {verdict}"
        )
    w("")
    w("PER-HOST POLITENESS VERIFICATION")
    w("-" * 33)
    w(f"Run ID: {report.get('run_id')}")
    w(f"Workers: {report.get('max_workers')}")
    w(f"Hosts checked: {report.get('hosts_checked')}")
    w(f"Total requests: {report.get('total_requests')}")
    w(f"Minimum observed spacing: {report.get('minimum_observed_spacing_seconds')}")
    w(f"Hosts passing: {len(report.get('hosts_passing', []))}")
    w(f"Hosts failing: {len(report.get('hosts_failing', []))}")
    if report.get("hosts_failing"):
        w(f"  Failing hosts: {', '.join(report['hosts_failing'])}")
    w(f"Overall result: {report.get('overall_result')}")
    return "\n".join(lines)


def write_politeness_report(run_dir: str | Path) -> dict[str, Any]:
    """Compute the politeness report and persist it to
    ``politeness_verification.json``."""
    run_dir = Path(run_dir)
    report = compute_politeness_report(run_dir)
    (run_dir / "politeness_verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


__all__ = [
    "compute_politeness_report",
    "render_politeness_report_text",
    "write_politeness_report",
]
