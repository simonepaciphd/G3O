"""Tests for the two ground-truth accuracy canaries (status doc §5.1 / §6.8).

Before these, the health report had no way to detect a leg-1 accuracy
regression: every Stage 1a/2 gauge measures whether the pipeline produced
*something*, and ``pct_institutions_with_domain`` reads ~100% because leg 1
nearly always returns some non-aggregator host — just not the right one.

Two signals are recorded at run time (which is what keeps g3o.report.health
disk-only) and aggregated by the report:

- **Leg-1 recall** — did leg 1 surface the master's own domain? Model-free,
  and therefore the one gauge that cannot be inflated by prompt contents.
- **Stage 2 pick vs master** — deliberately kept, but a liveness check rather
  than an accuracy measurement, because institution_record() puts the master's
  `website` into the Stage 2 prompt. A test below pins that contamination so
  it cannot be quietly forgotten.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest import mock

from g3o.classify.official_site import build_official_site_job
from g3o.common import attrition as _attrition
from g3o.report import HealthThresholds, compute_health_report, render_text_report
from g3o.run.presweep import stage_discovery
from g3o.run.presweep.records import institution_record, synth_institution_id
from g3o.run.presweep.stage_classify import ground_truth_block
from g3o.run.presweep.stage_discovery import leg1_recall_block


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# leg1_recall_block — the uncontaminated signal
# ---------------------------------------------------------------------------


def _rec(url: str, position: int | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {"link": url}
    if position is not None:
        r["position"] = position
    return r


def test_leg1_recall_none_without_ground_truth():
    assert leg1_recall_block(None, [_rec("https://x.gov/")]) is None
    assert leg1_recall_block("", [_rec("https://x.gov/")]) is None


def test_leg1_recall_none_when_master_website_unparseable():
    assert leg1_recall_block("not a url", []) is None


def test_leg1_recall_finds_domain_and_rank():
    block = leg1_recall_block(
        "https://www.bancaditalia.it/",
        [_rec("https://other.org/", 1), _rec("https://www.bancaditalia.it/en/", 2)],
    )
    assert block["leg1_surfaced_domain"] is True
    assert block["leg1_rank"] == 2
    assert block["master_domain"] == "bancaditalia.it"


def test_leg1_recall_matches_on_registrable_domain_not_exact_host():
    # A subdomain hit is still the institution's own domain.
    block = leg1_recall_block(
        "bancaditalia.it", [_rec("https://data.bancaditalia.it/reports/x.pdf", 1)]
    )
    assert block["leg1_surfaced_domain"] is True


def test_leg1_recall_records_a_miss():
    block = leg1_recall_block(
        "https://www.bancaditalia.it/", [_rec("https://wikipedia.org/x", 1)]
    )
    assert block["leg1_surfaced_domain"] is False
    assert block["leg1_rank"] is None


def test_leg1_recall_handles_a_hit_with_no_position():
    block = leg1_recall_block("bancaditalia.it", [_rec("https://bancaditalia.it/")])
    assert block["leg1_surfaced_domain"] is True
    assert block["leg1_rank"] is None


# ---------------------------------------------------------------------------
# ground_truth_block — the Stage 2 comparison
# ---------------------------------------------------------------------------


def test_ground_truth_block_none_without_master_website():
    assert ground_truth_block(None, "https://x.gov/") is None


def test_ground_truth_block_match_and_mismatch():
    hit = ground_truth_block("https://www.scb.se/", "https://scb.se/en/")
    assert hit["domain_match"] is True
    miss = ground_truth_block("https://www.scb.se/", "https://wipo.int/")
    assert miss["domain_match"] is False
    assert miss["picked_domain"] == "wipo.int"


def test_ground_truth_block_handles_no_pick():
    block = ground_truth_block("https://www.scb.se/", None)
    assert block["domain_match"] is False
    assert block["picked_domain"] is None


def test_stage2_prompt_contains_the_master_website():
    """Pins the contamination the Stage 2 canary is labelled for.

    institution_record() carries `website`, and _user_prompt serialises the
    whole record into the Stage 2 message — so the classifier can read the
    exact value `ground_truth_block` scores it against. Removing it changes
    model input and breaks comparability with the 2026-08-01 measurement, so
    it is a PI decision, not a cleanup. If this test ever fails, the Stage 2
    canary has become a real accuracy metric and its CONTAMINATED label and
    threshold caveat should be removed.
    """
    row = {
        "institution_name": "Banca d Italia",
        "country": "Italy",
        "website": "https://www.bancaditalia.it/",
        "master_row_id": "1",
    }
    job = build_official_site_job(
        institution_record(row), ["https://www.bancaditalia.it/"], custom_id="INST-0000001"
    )
    assert "https://www.bancaditalia.it/" in job.messages[1]["content"]


# ---------------------------------------------------------------------------
# Producer side — the block must actually reach disk, not just aggregate well
# ---------------------------------------------------------------------------


def test_stage_1a_chain_writes_the_ground_truth_block(tmp_path: Path) -> None:
    class _Result:
        results = [
            {"link": "https://www.bancaditalia.it/en/", "position": 1,
             "title": "t", "snippet": "s"}
        ]
        search_parameters = {"q": "x", "num": 10}
        from_cache = False

    row = {
        "master_row_id": "1",
        "institution_name": "Banca d Italia",
        "country": "Italy",
        "government_level": "national",
        "branch": "bureaucratic",
        "website": "https://www.bancaditalia.it/",
    }
    inst_id = synth_institution_id(row)
    (tmp_path / inst_id).mkdir(parents=True)
    with mock.patch.object(stage_discovery, "search_google_detailed", return_value=_Result()):
        stage_discovery._discover_general_one(
            tmp_path, row, stage="discovery_general",
            languages=("en",), num_results=10, mode="chain",
        )

    artifact = json.loads(
        (tmp_path / inst_id / "1a_discovery_general.json").read_text(encoding="utf-8")
    )
    assert artifact["ground_truth"] == {
        "master_website": "https://www.bancaditalia.it/",
        "master_domain": "bancaditalia.it",
        "leg1_surfaced_domain": True,
        "leg1_rank": 1,
    }


def test_stage_1a_omits_the_block_without_ground_truth(tmp_path: Path) -> None:
    class _Result:
        results = [{"link": "https://x.gov/", "position": 1}]
        search_parameters = {"q": "x", "num": 10}
        from_cache = False

    row = {
        "master_row_id": "2",
        "institution_name": "No Website Body",
        "country": "Testland",
        "government_level": "local",
        "branch": "bureaucratic",
        "website": "",
    }
    inst_id = synth_institution_id(row)
    (tmp_path / inst_id).mkdir(parents=True)
    with mock.patch.object(stage_discovery, "search_google_detailed", return_value=_Result()):
        stage_discovery._discover_general_one(
            tmp_path, row, stage="discovery_general",
            languages=("en",), num_results=10, mode="chain",
        )

    artifact = json.loads(
        (tmp_path / inst_id / "1a_discovery_general.json").read_text(encoding="utf-8")
    )
    assert "ground_truth" not in artifact


# ---------------------------------------------------------------------------
# Health-report aggregation
# ---------------------------------------------------------------------------


def _build_run(
    run_dir: Path,
    *,
    n: int,
    n_with_truth: int,
    n_leg1_hit: int,
    n_stage2_match: int,
) -> None:
    """A chain-mode run where the first `n_with_truth` institutions carry
    ground truth; of those, `n_leg1_hit` had the true domain surfaced by leg 1
    and `n_stage2_match` had Stage 2 pick it."""
    _attrition._reset_cache()
    ids = [f"INST-{i:07d}" for i in range(1, n + 1)]
    _write(
        run_dir / "manifest.json",
        {
            "run_id": "canary-run",
            "run_date": "2026-08-02",
            "institutions": ids,
            "config": {"stop_after": "validate"},
        },
    )
    for i, inst_id in enumerate(ids):
        d = run_dir / inst_id
        true_dom = f"inst{i}.gov"
        has_truth = i < n_with_truth
        leg1_hit = i < n_leg1_hit
        s2_match = i < n_stage2_match

        artifact: dict[str, Any] = {
            "mode": "chain",
            "queries": [{"query": "q", "language": "en", "leg": "domain"}],
            "records": [{"link": f"https://{true_dom if leg1_hit else 'other.org'}/"}],
            "naive_domain": {"domain": true_dom, "rank": 1},
        }
        if has_truth:
            artifact["ground_truth"] = {
                "master_website": f"https://{true_dom}/",
                "master_domain": true_dom,
                "leg1_surfaced_domain": leg1_hit,
                "leg1_rank": 1 if leg1_hit else None,
            }
        _write(d / "1a_discovery_general.json", artifact)

        stage2: dict[str, Any] = {
            "url": f"https://{true_dom if s2_match else 'wrong.org'}/",
            "confidence": "high",
            "rationale": "ok",
        }
        if has_truth:
            stage2["ground_truth"] = {
                "master_website": f"https://{true_dom}/",
                "master_domain": true_dom,
                "picked_domain": true_dom if s2_match else "wrong.org",
                "domain_match": s2_match,
            }
        _write(d / "2_official_site.json", stage2)


def test_leg1_recall_aggregates_and_flags(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _build_run(run_dir, n=20, n_with_truth=20, n_leg1_hit=16, n_stage2_match=18)
    s = compute_health_report(run_dir)["stages"]["1a_discovery_general"]

    assert s["n_ground_truth_available"] == 20
    assert s["n_leg1_surfaced_true_domain"] == 16
    assert s["pct_leg1_recall"] == 0.8
    # 80% is above the 72% warn band -> green.
    assert s["leg1_recall_flag"] == "green"


def test_leg1_recall_goes_red_while_the_volume_gauge_stays_green(tmp_path: Path) -> None:
    """The whole point of §5.1: volume can read fine while accuracy collapses."""
    run_dir = tmp_path / "run"
    _build_run(run_dir, n=20, n_with_truth=20, n_leg1_hit=4, n_stage2_match=4)
    s = compute_health_report(run_dir)["stages"]["1a_discovery_general"]

    # Every institution still returned a usable domain...
    assert s["pct_institutions_with_domain"] == 1.0
    assert s["flag"] == "green"
    # ...but only 20% of them were the RIGHT domain.
    assert s["pct_leg1_recall"] == 0.2
    assert s["leg1_recall_flag"] == "fail"


def test_canaries_stay_unflagged_below_the_minimum_sample(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _build_run(run_dir, n=8, n_with_truth=3, n_leg1_hit=0, n_stage2_match=0)
    stages = compute_health_report(run_dir)["stages"]

    assert stages["1a_discovery_general"]["n_ground_truth_available"] == 3
    assert stages["1a_discovery_general"]["leg1_recall_flag"] == "insufficient_ground_truth"
    assert stages["2_classify_official_site"]["ground_truth_flag"] == (
        "insufficient_ground_truth"
    )


def test_institutions_without_ground_truth_leave_the_denominator_alone(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    _build_run(run_dir, n=30, n_with_truth=10, n_leg1_hit=10, n_stage2_match=10)
    stages = compute_health_report(run_dir)["stages"]

    # 30 institutions, only 10 scoreable — the other 20 must not count as misses.
    assert stages["1a_discovery_general"]["n_ground_truth_available"] == 10
    assert stages["1a_discovery_general"]["pct_leg1_recall"] == 1.0
    assert stages["2_classify_official_site"]["n_ground_truth_available"] == 10
    assert stages["2_classify_official_site"]["pct_official_site_matches_master"] == 1.0


def test_stage2_canary_aggregates(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _build_run(run_dir, n=20, n_with_truth=20, n_leg1_hit=20, n_stage2_match=13)
    s = compute_health_report(run_dir)["stages"]["2_classify_official_site"]

    assert s["n_official_site_matches_master"] == 13
    assert s["pct_official_site_matches_master"] == 0.65
    assert s["ground_truth_flag"] == "fail"


def test_thresholds_are_pi_tunable(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _build_run(run_dir, n=20, n_with_truth=20, n_leg1_hit=16, n_stage2_match=16)
    loosened = HealthThresholds(leg1_recall_warn_pct=0.5, leg1_recall_fail_pct=0.3)
    tightened = HealthThresholds(leg1_recall_warn_pct=0.95, leg1_recall_fail_pct=0.9)

    assert (
        compute_health_report(run_dir, loosened)["stages"]["1a_discovery_general"][
            "leg1_recall_flag"
        ]
        == "green"
    )
    assert (
        compute_health_report(run_dir, tightened)["stages"]["1a_discovery_general"][
            "leg1_recall_flag"
        ]
        == "fail"
    )


def test_text_report_surfaces_both_canaries(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _build_run(run_dir, n=20, n_with_truth=20, n_leg1_hit=16, n_stage2_match=13)
    text = render_text_report(compute_health_report(run_dir))

    assert "Leg-1 recall:  16/20 (80.0%)" in text
    assert "Matches master:   13/20 (65.0%)" in text
    # The caveat must travel with the number, not live only in a doc.
    assert "CONTAMINATED" in text


def test_legacy_run_reports_no_canary(tmp_path: Path) -> None:
    """Leg-1 recall is chain-only; a legacy run must not grow a phantom gauge."""
    run_dir = tmp_path / "run"
    _attrition._reset_cache()
    _write(
        run_dir / "manifest.json",
        {
            "run_id": "legacy-run",
            "run_date": "2026-08-02",
            "institutions": ["INST-0000001"],
            "config": {"stop_after": "validate"},
        },
    )
    _write(
        run_dir / "INST-0000001" / "1a_discovery_general.json",
        {"mode": "legacy", "queries": [], "records": [{"link": "https://x.gov/"}]},
    )
    s = compute_health_report(run_dir)["stages"]["1a_discovery_general"]
    assert "pct_leg1_recall" not in s
