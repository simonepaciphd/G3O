"""Stage-by-stage funnel health report for a finished (or partial) presweep run.

Reads only from disk: manifest.json, per-institution stage artifacts, and the
attrition ledger (_attrition.jsonl).  No network or API calls.

Usage::

    from g3o.report.health import compute_health_report
    report = compute_health_report(Path("runs/my-run-id"))

The returned dict is JSON-serialisable and mirrors the schema documented in
``render.py``'s text renderer.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from g3o.common import attrition as _attrition
from g3o.report.thresholds import HealthThresholds

# Flag literals: green = within normal bounds, warn = below warn threshold,
# fail = below fail threshold, not_run = stage was not executed.
_Flag = str  # "green" | "warn" | "fail" | "not_run"


def _flag_low_is_bad(value: float | None, *, warn: float, fail: float) -> _Flag:
    """Flag when a rate is unexpectedly *low* (high is good)."""
    if value is None:
        return "not_run"
    if value <= fail:
        return "fail"
    if value <= warn:
        return "warn"
    return "green"


def _flag_high_is_bad(value: float | None, *, warn: float, fail: float) -> _Flag:
    """Flag when a rate is unexpectedly *high* (low is good, e.g. empty-page drop)."""
    if value is None:
        return "not_run"
    if value >= fail:
        return "fail"
    if value >= warn:
        return "warn"
    return "green"


def _worst(*flags: _Flag) -> _Flag:
    for level in ("fail", "warn"):
        if level in flags:
            return level
    if all(f == "not_run" for f in flags):
        return "not_run"
    return "green"


def _pct(num: int, denom: int) -> float | None:
    if denom == 0:
        return None
    return round(num / denom, 4)


def _top_reasons(
    att: dict[tuple[str, str], int], stage: str
) -> list[dict[str, Any]]:
    return sorted(
        [{"reason": r, "count": c} for (s, r), c in att.items() if s == stage],
        key=lambda x: -x["count"],
    )


def _attrition_counters(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str], int]:
    c: Counter[tuple[str, str]] = Counter()
    for rec in records:
        stage = rec.get("stage", "")
        reason = rec.get("reason", "")
        if stage and reason:
            c[(stage, reason)] += 1
    return dict(c)


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _collect_institution(inst_dir: Path, inst_id: str) -> dict[str, Any]:
    """Read disk artifacts for one institution; return a metrics dict."""
    d: dict[str, Any] = {"institution_id": inst_id}

    # Stage 1a
    p = inst_dir / "1a_discovery_general.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        d["has_1a"] = True
        d["n_urls_1a"] = len(payload.get("records", []))
    else:
        d["has_1a"] = False
        d["n_urls_1a"] = 0

    # Stage 2
    p = inst_dir / "2_official_site.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        d["has_2"] = True
        d["official_site"] = payload.get("url")  # None if LLM found nothing
        d["stage2_bypassed"] = bool(payload.get("bypassed"))
    else:
        d["has_2"] = False
        d["official_site"] = None
        d["stage2_bypassed"] = False

    # Stage 1b
    p = inst_dir / "1b_discovery_site_restricted.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        d["has_1b"] = True
        d["n_urls_1b"] = len(payload.get("records", []))
    else:
        d["has_1b"] = False
        d["n_urls_1b"] = 0

    # Stage 3
    p = inst_dir / "3_triage.json"
    if p.exists():
        payload = json.loads(p.read_text(encoding="utf-8"))
        decisions = payload.get("decisions", [])
        d["has_3"] = True
        d["n_urls_triaged"] = len(decisions)
        d["n_urls_kept"] = sum(1 for dec in decisions if dec.get("decision") == "keep")
    else:
        d["has_3"] = False
        d["n_urls_triaged"] = 0
        d["n_urls_kept"] = 0

    # Stage 4: scrape/*.json files
    scrape_dir = inst_dir / "scrape"
    d["n_pages_scraped"] = (
        sum(1 for _ in scrape_dir.glob("*.json")) if scrape_dir.is_dir() else 0
    )

    # Stage 5: extract/*.json files
    extract_dir = inst_dir / "extract"
    d["n_extracts"] = (
        sum(1 for _ in extract_dir.glob("*.json")) if extract_dir.is_dir() else 0
    )

    # Stage 6
    p = inst_dir / "6_validate.json"
    if p.exists():
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            d["has_6"] = True
            d["has_genai_activity"] = payload.get("institution", {}).get(
                "has_genai_activity"
            )
        except (json.JSONDecodeError, KeyError, AttributeError):
            d["has_6"] = False
            d["has_genai_activity"] = None
    else:
        d["has_6"] = False
        d["has_genai_activity"] = None

    return d


def compute_health_report(
    run_dir: str | Path,
    thresholds: HealthThresholds | None = None,
) -> dict[str, Any]:
    """Compute a stage-by-stage funnel health report.

    Parameters
    ----------
    run_dir:
        Path to ``runs/<run_id>/`` produced by ``g3o presweep --execute``.
    thresholds:
        PI-tunable thresholds.  Defaults to :class:`HealthThresholds` defaults.

    Returns
    -------
    dict
        JSON-serialisable report with per-stage KPIs, green/warn/fail flags,
        attrition breakdown, and the thresholds used.  Suitable for both
        machine consumption (write as JSON) and human rendering via
        :func:`g3o.report.render.render_text_report`.
    """
    run_dir = Path(run_dir)
    thresholds = thresholds or HealthThresholds()

    manifest = _load_manifest(run_dir)
    institution_ids: list[str] = manifest.get("institutions", [])

    # Fallback if manifest absent: infer from non-underscore subdirs.
    if not institution_ids:
        institution_ids = [
            d.name
            for d in sorted(run_dir.iterdir())
            if d.is_dir() and not d.name.startswith("_") and d.name != ".done"
        ]

    n_institutions = len(institution_ids)

    # Attrition ledger
    ledger = _attrition.read_records(run_dir)
    att = _attrition_counters(ledger)

    # Per-institution artifact pass
    inst_data = [
        _collect_institution(run_dir / iid, iid) for iid in institution_ids
    ]

    # ── Stage 1a ──────────────────────────────────────────────────────────────
    n_1a_with_urls = sum(1 for d in inst_data if d["n_urls_1a"] > 0)
    total_urls_1a = sum(d["n_urls_1a"] for d in inst_data)
    pct_1a = _pct(n_1a_with_urls, n_institutions)

    stage_1a: dict[str, Any] = {
        "n_institutions_in": n_institutions,
        "n_institutions_with_urls": n_1a_with_urls,
        "pct_institutions_with_urls": pct_1a,
        "total_candidate_urls": total_urls_1a,
        "mean_urls_per_institution": (
            round(total_urls_1a / n_institutions, 2) if n_institutions else None
        ),
        "n_serper_failed": att.get(("discovery_general", "serper_request_failed"), 0),
        "top_drop_reasons": _top_reasons(att, "discovery_general"),
        "flag": _flag_low_is_bad(
            pct_1a,
            warn=thresholds.discovery_general_warn_pct,
            fail=thresholds.discovery_general_fail_pct,
        ),
    }

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    n_2_in = n_1a_with_urls or n_institutions  # only institutions with URLs get jobs
    n_official_site = sum(1 for d in inst_data if d["official_site"])
    n_bypassed = sum(1 for d in inst_data if d["stage2_bypassed"])
    pct_official = _pct(n_official_site, n_2_in)

    stage_2: dict[str, Any] = {
        "n_institutions_in": n_2_in,
        "n_official_site_found": n_official_site,
        "n_bypassed_from_master": n_bypassed,
        "pct_official_site_found": pct_official,
        "n_parse_failed": att.get(("classify_official_site", "parse_failed"), 0),
        "top_drop_reasons": _top_reasons(att, "classify_official_site"),
        "flag": _flag_low_is_bad(
            pct_official,
            warn=thresholds.official_site_warn_pct,
            fail=thresholds.official_site_fail_pct,
        ),
    }

    # ── Stage 1b ──────────────────────────────────────────────────────────────
    n_1b_eligible = n_official_site  # only those with an official site get 1b queries
    n_1b_with_urls = sum(1 for d in inst_data if d["n_urls_1b"] > 0)
    total_urls_1b = sum(d["n_urls_1b"] for d in inst_data)
    pct_1b = _pct(n_1b_with_urls, n_1b_eligible)

    stage_1b: dict[str, Any] = {
        "n_institutions_eligible": n_1b_eligible,
        "n_institutions_with_1b_urls": n_1b_with_urls,
        "pct_institutions_with_1b_urls": pct_1b,
        "total_1b_urls": total_urls_1b,
        "mean_1b_urls_per_eligible": (
            round(total_urls_1b / n_1b_eligible, 2) if n_1b_eligible else None
        ),
        "n_official_site_unparseable": att.get(
            ("discovery_site_restricted", "official_site_unparseable"), 0
        ),
        "n_serper_failed": att.get(
            ("discovery_site_restricted", "serper_request_failed"), 0
        ),
        "top_drop_reasons": _top_reasons(att, "discovery_site_restricted"),
        "flag": (
            _flag_low_is_bad(
                pct_1b,
                warn=thresholds.discovery_site_restricted_warn_pct,
                fail=thresholds.discovery_site_restricted_fail_pct,
            )
            if n_1b_eligible
            else "not_run"
        ),
    }

    # ── Stage 3 ───────────────────────────────────────────────────────────────
    n_3_eligible = sum(
        1 for d in inst_data if d["n_urls_1a"] > 0 or d["n_urls_1b"] > 0
    )
    n_institutions_with_kept = sum(1 for d in inst_data if d["n_urls_kept"] > 0)
    total_urls_triaged = sum(d["n_urls_triaged"] for d in inst_data)
    total_urls_kept = sum(d["n_urls_kept"] for d in inst_data)
    pct_inst_kept = _pct(n_institutions_with_kept, n_3_eligible)
    pct_url_keep = _pct(total_urls_kept, total_urls_triaged)

    flag_3_inst = _flag_low_is_bad(
        pct_inst_kept,
        warn=thresholds.triage_institutions_warn_pct,
        fail=thresholds.triage_institutions_fail_pct,
    )
    flag_3_url = _flag_low_is_bad(
        pct_url_keep,
        warn=thresholds.triage_url_keep_warn_pct,
        fail=thresholds.triage_url_keep_fail_pct,
    )

    stage_3: dict[str, Any] = {
        "n_institutions_in": n_3_eligible,
        "n_total_candidate_urls": total_urls_triaged,
        "n_urls_kept": total_urls_kept,
        "n_urls_dropped": total_urls_triaged - total_urls_kept,
        "pct_urls_kept": pct_url_keep,
        "n_institutions_with_kept_url": n_institutions_with_kept,
        "pct_institutions_with_kept_url": pct_inst_kept,
        "n_parse_failed": att.get(("classify_triage", "parse_failed"), 0),
        "top_drop_reasons": _top_reasons(att, "classify_triage"),
        "flag": _worst(flag_3_inst, flag_3_url),
        "_flag_institution_coverage": flag_3_inst,
        "_flag_url_keep_rate": flag_3_url,
    }

    # ── Stage 4 ───────────────────────────────────────────────────────────────
    n_urls_attempted = total_urls_kept
    n_scraped = sum(d["n_pages_scraped"] for d in inst_data)
    n_institutions_with_pages = sum(1 for d in inst_data if d["n_pages_scraped"] > 0)
    pct_scrape = _pct(n_scraped, n_urls_attempted)

    stage_4: dict[str, Any] = {
        "n_urls_attempted": n_urls_attempted,
        "n_pages_scraped": n_scraped,
        "n_robots_disallowed": att.get(("scrape", "robots_disallowed"), 0),
        "n_scrape_failed": att.get(("scrape", "scrape_failed"), 0),
        "pct_scrape_success": pct_scrape,
        "n_institutions_with_pages": n_institutions_with_pages,
        "top_drop_reasons": _top_reasons(att, "scrape"),
        "flag": (
            _flag_low_is_bad(
                pct_scrape,
                warn=thresholds.scrape_success_warn_pct,
                fail=thresholds.scrape_success_fail_pct,
            )
            if n_urls_attempted
            else "not_run"
        ),
    }

    # ── Stage 5 ───────────────────────────────────────────────────────────────
    n_empty_dropped = att.get(("extract", "empty_page_dropped"), 0)
    n_page_truncated = att.get(("extract", "page_text_truncated"), 0)
    n_extract_eligible = max(0, n_scraped - n_empty_dropped)
    total_extracts = sum(d["n_extracts"] for d in inst_data)
    n_institutions_with_extracts = sum(1 for d in inst_data if d["n_extracts"] > 0)
    pct_empty = _pct(n_empty_dropped, n_scraped)
    pct_extracted = _pct(total_extracts, n_extract_eligible)

    flag_5_extract = _flag_low_is_bad(
        pct_extracted,
        warn=thresholds.extract_success_warn_pct,
        fail=thresholds.extract_success_fail_pct,
    )
    flag_5_empty = _flag_high_is_bad(
        pct_empty,
        warn=thresholds.extract_empty_warn_pct,
        fail=thresholds.extract_empty_fail_pct,
    )

    stage_5: dict[str, Any] = {
        "n_pages_in": n_scraped,
        "n_empty_dropped": n_empty_dropped,
        "n_pages_eligible": n_extract_eligible,
        "n_pages_truncated": n_page_truncated,
        "n_extracts": total_extracts,
        "n_parse_failed": att.get(("extract", "parse_failed"), 0),
        "pct_empty_dropped": pct_empty,
        "pct_extracted_of_eligible": pct_extracted,
        "n_institutions_with_extracts": n_institutions_with_extracts,
        "top_drop_reasons": _top_reasons(att, "extract"),
        "flag": (
            _worst(flag_5_extract, flag_5_empty) if n_scraped else "not_run"
        ),
        "_flag_extract_success": flag_5_extract,
        "_flag_empty_rate": flag_5_empty,
    }

    # ── Stage 6 ───────────────────────────────────────────────────────────────
    n_6_eligible = n_institutions_with_extracts
    n_6_consolidated = sum(1 for d in inst_data if d["has_6"])
    hga: Counter[str] = Counter(
        d["has_genai_activity"] for d in inst_data if d["has_genai_activity"]
    )
    n_6_yes = hga.get("yes", 0)
    n_6_no = hga.get("no", 0)
    n_6_unclear = hga.get("unclear", 0)
    pct_consolidated = _pct(n_6_consolidated, n_6_eligible)
    pct_unclear = _pct(n_6_unclear, n_6_consolidated)

    flag_6_consol = _flag_low_is_bad(
        pct_consolidated,
        warn=thresholds.validate_consolidated_warn_pct,
        fail=thresholds.validate_consolidated_fail_pct,
    )
    flag_6_unclear = _flag_high_is_bad(
        pct_unclear,
        warn=thresholds.validate_unclear_warn_pct,
        fail=thresholds.validate_unclear_fail_pct,
    )

    stage_6: dict[str, Any] = {
        "n_institutions_in": n_6_eligible,
        "n_consolidated": n_6_consolidated,
        "n_missing_validate_json": max(0, n_6_eligible - n_6_consolidated),
        "pct_consolidated": pct_consolidated,
        "has_genai_activity": {"yes": n_6_yes, "no": n_6_no, "unclear": n_6_unclear},
        "pct_unclear": pct_unclear,
        "top_drop_reasons": _top_reasons(att, "validate"),
        "flag": (
            _worst(flag_6_consol, flag_6_unclear) if n_6_eligible else "not_run"
        ),
        "_flag_consolidated_rate": flag_6_consol,
        "_flag_unclear_rate": flag_6_unclear,
    }

    # ── Overall ───────────────────────────────────────────────────────────────
    stages = {
        "1a_discovery_general": stage_1a,
        "2_classify_official_site": stage_2,
        "1b_discovery_site_restricted": stage_1b,
        "3_classify_triage": stage_3,
        "4_scrape": stage_4,
        "5_extract": stage_5,
        "6_validate": stage_6,
    }
    run_flags = [s["flag"] for s in stages.values() if s["flag"] != "not_run"]
    overall = _worst(*run_flags) if run_flags else "not_run"

    top_reasons = sorted(
        [{"stage": s, "reason": r, "count": c} for (s, r), c in att.items()],
        key=lambda x: -x["count"],
    )[:15]

    return {
        "run_id": manifest.get("run_id", run_dir.name),
        "run_dir": str(run_dir),
        "run_date": manifest.get("run_date"),
        "n_institutions": n_institutions,
        "stages_planned": manifest.get("stages_planned", []),
        "overall_flag": overall,
        "stages": stages,
        "attrition_top_reasons": top_reasons,
        "thresholds_used": asdict(thresholds),
        "thresholds_note": (
            "All thresholds are PI-tunable. Defaults target a smoke run "
            "(~10 institutions). Pass a custom HealthThresholds instance or "
            "--thresholds <json-file> to override."
        ),
    }


__all__ = ["compute_health_report"]
