"""One spend ceiling over every paid API (PI ruling 2026-10-02).

Until 2026-10-02 ``G3O_BUDGET_LIMIT_USD`` capped LLM token spend only: Serper
credits (Stage 1) and Bright Data Web Unlocker bytes (Stage 4) were neither
projected, counted nor capped, and the preflight priced the jev stages at
OpenAI rates. These tests pin the four halves of the fix — prices, metering at
the client choke points, enforcement at safe points, and the projection — plus
the deployment/services report that makes a missing key or a stale checkout
visible.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import requests

from g3o.common import attrition, config, deployment, scrape_telemetry, spend_meter
from g3o.common.cost_monitor import BudgetExceededError, CostMonitor
from g3o.common.credentials import Credentials
from g3o.common.pricing import JEV_1_13_0_PRICING, serper_usd, unlocker_usd
from g3o.discovery import serper_client
from g3o.scrape import unlocker
from tests.test_presweep import _build_master, _f14b_page, _make_config, _write_master_csv

# Captured at import, before conftest's autouse fixture swaps in the offline
# wrapper, so the staleness tests below can drive the real function.
_REAL_DEPLOYMENT_STATUS = deployment.deployment_status


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    attrition._reset_cache()
    scrape_telemetry._reset_cache()
    yield
    attrition._reset_cache()
    scrape_telemetry._reset_cache()


def _monitor(budget: float | None = None) -> CostMonitor:
    return CostMonitor(budget_usd=budget, model="gpt-5-nano")


# --------------------------------------------------------------------------
# Prices
# --------------------------------------------------------------------------


def test_serper_rate_defaults_to_the_ruled_value_and_env_overrides_it(monkeypatch):
    monkeypatch.setattr(config, "SERPER_USD_PER_CREDIT", None)
    assert serper_usd(1000) == pytest.approx(1.0)  # $0.001/credit
    monkeypatch.setattr(config, "SERPER_USD_PER_CREDIT", 0.00056)
    assert serper_usd(1000) == pytest.approx(0.56)


def test_unlocker_is_eight_dollars_per_decimal_gigabyte():
    assert unlocker_usd(1_000_000_000) == pytest.approx(8.0)
    assert unlocker_usd(250_000) == pytest.approx(0.002)


# --------------------------------------------------------------------------
# The meter
# --------------------------------------------------------------------------


def test_record_is_a_noop_without_a_sink_and_never_raises():
    spend_meter.record(spend_meter.SERPER, credits=1)  # nothing installed
    spend_meter.enforce("discovery_general")  # no guard: no-op

    def bad_sink(api, units):
        raise ValueError("sink bug")

    spend_meter.install(bad_sink)
    spend_meter.record(spend_meter.SERPER, credits=1)  # swallowed, logged


def test_monitor_counts_metered_spend_in_the_running_total_and_the_budget():
    mon = _monitor(budget=1.0)
    mon.record_metered(spend_meter.SERPER, {"credits": 400, "live_queries": 400})
    mon.record_metered(
        spend_meter.UNLOCKER, {"billable_bytes": 50_000_000, "success": True}
    )
    assert mon.running_total_usd == pytest.approx(0.4 + 0.4)
    assert mon.check_budget() is True
    mon.record_metered(spend_meter.SERPER, {"credits": 300, "live_queries": 300})
    assert mon.running_total_usd == pytest.approx(1.1)
    assert mon.check_budget() is False


def test_cost_report_breaks_spend_down_by_api():
    mon = CostMonitor(
        budget_usd=None, model="gpt-5-nano",
        stage_models={"classify_triage": "jev-1.13.0"},
    )
    mon.record_metered(spend_meter.SERPER, {"credits": 10, "live_queries": 10})
    mon.record_metered(spend_meter.UNLOCKER, {"billable_bytes": 1000, "success": True})
    mon.record_metered(spend_meter.UNLOCKER, {"billable_bytes": 0, "success": False})
    report = mon.cost_report()
    by_api = report["by_api"]
    assert by_api["serper"]["credits"] == 10
    assert by_api["serper"]["usd"] == pytest.approx(0.01)
    assert by_api["brightdata_unlocker"]["requests"] == 2
    assert by_api["brightdata_unlocker"]["requests_succeeded"] == 1
    assert by_api["brightdata_unlocker"]["billable_bytes"] == 1000
    assert report["metered_total_usd"] == pytest.approx(0.01 + unlocker_usd(1000), abs=1e-6)
    assert report["total_usd"] == pytest.approx(
        report["llm_total_usd"] + report["metered_total_usd"], abs=1e-6
    )


def test_projection_ratio_ignores_metered_spend():
    """The preflight stage estimates are LLM-only; Serper spend in the numerator
    would project a false overrun."""
    mon = _monitor(budget=10.0)
    mon.preflight_stage_estimates = {"a": 1.0, "b": 1.0, "c": 1.0}
    from g3o.common.cost_monitor import StageCost

    for name in ("a", "b"):
        mon.stages.append(StageCost(name, 0, 0, 0, 0.5, 0.5, 1.0, 1, 1))
    mon.record_metered(spend_meter.SERPER, {"credits": 5000})  # $5
    within, projected, _ = mon.check_projection(safety_factor=1.0)
    assert projected == pytest.approx(3.0)  # 2 actual + 1 remaining at ratio 1
    assert within is True


# --------------------------------------------------------------------------
# Client choke points
# --------------------------------------------------------------------------


def _capture() -> list[tuple[str, dict[str, Any]]]:
    seen: list[tuple[str, dict[str, Any]]] = []
    spend_meter.install(lambda api, units: seen.append((api, units)))
    return seen


def test_serper_meters_live_calls_from_the_credits_field_and_not_cache_hits(monkeypatch):
    seen = _capture()
    monkeypatch.setattr(
        serper_client, "_execute",
        lambda payload, *, api_key: {"credits": 2, "organic": [], "searchParameters": {}},
    )
    from g3o.common.credentials import resolve

    creds = resolve(Credentials(serper_api_key="k"))
    serper_client.search_google_detailed("q", num_results=20, credentials=creds)
    assert seen == [(spend_meter.SERPER, {"credits": 2, "live_queries": 1})]
    serper_client.search_google_detailed("q", num_results=20, credentials=creds)  # cached
    assert len(seen) == 1


def test_serper_assumes_one_credit_when_the_field_is_missing(monkeypatch):
    seen = _capture()
    monkeypatch.setattr(
        serper_client, "_execute", lambda payload, *, api_key: {"organic": []}
    )
    from g3o.common.credentials import resolve

    serper_client.search_google_detailed(
        "q2", credentials=resolve(Credentials(serper_api_key="k"))
    )
    assert seen == [(spend_meter.SERPER, {"credits": 1, "live_queries": 1})]


def test_serper_mock_path_is_not_metered(monkeypatch):
    seen = _capture()
    from g3o.common.credentials import resolve

    serper_client.search_google_detailed("q3", credentials=resolve(Credentials()))
    assert seen == []


def _unlocker_response(status: int, body: bytes, headers: dict[str, str]):
    resp = requests.Response()
    resp.status_code = status
    resp._content = body
    resp.headers.update(headers)
    return resp


@pytest.mark.parametrize(
    "headers, body, success, billable",
    [
        ({"x-brd-status-code": "200"}, b"<html>ok</html>", True, 15),
        ({"x-brd-error": "policy_20000"}, b"", False, 0),
        # A delivered inner 404 is billed (conservative) though the gate fails it.
        ({"x-brd-status-code": "404"}, b"not found page", False, 14),
    ],
)
def test_unlocker_meters_billable_bytes(monkeypatch, headers, body, success, billable):
    seen = _capture()
    monkeypatch.setattr(config, "UNLOCKER_API_TOKEN", "tok-123456789")
    monkeypatch.setattr(
        unlocker.requests, "post",
        lambda *a, **k: _unlocker_response(200, body, headers),
    )
    result = unlocker.fetch("https://example.gov/x")
    assert result.success is success
    assert result.billable_bytes == billable
    assert seen == [
        (spend_meter.UNLOCKER, {"billable_bytes": billable, "success": success})
    ]


# --------------------------------------------------------------------------
# Enforcement at safe points
# --------------------------------------------------------------------------


def _install_raising_guard(mon: CostMonitor) -> None:
    def guard(stage: str) -> None:
        if not mon.check_budget():
            raise BudgetExceededError(mon.running_total_usd, mon.budget_usd, stage)

    spend_meter.install(mon.record_metered, guard)


def test_scrape_stops_before_the_next_fetch_once_the_ceiling_is_crossed(tmp_path):
    """The abort must not be swallowed by Stage 4's per-URL ``except Exception``."""
    from g3o.run import presweep as ps

    rows = _build_master(n_strata=1, rows_per_stratum=1)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    plan = ps.plan_run(_make_config(tmp_path=tmp_path, master_csv=master, sample_size=1))
    inst_id = plan.manifest["institutions"][0]
    urls = [f"https://x.example/{i}" for i in range(3)]
    mon = _monitor(budget=1.0)
    _install_raising_guard(mon)
    fetched: list[str] = []

    def _fake_scrape(url: str, **kwargs: Any):
        fetched.append(url)
        spend_meter.record(spend_meter.UNLOCKER, billable_bytes=1_000_000_000, success=True)
        return _f14b_page(url)

    class _Robots:
        def allowed(self, url: str) -> bool:
            return True

        def crawl_delay(self, url: str):
            return None

    with patch.object(ps.stage_scrape, "scrape_url", _fake_scrape):
        with pytest.raises(BudgetExceededError) as exc:
            ps._run_scrape(
                plan.run_dir, plan.sample, {inst_id: urls},
                respect_robots=True, robots=_Robots(), host_delay_seconds=0.0,
            )
    assert fetched == urls[:1]
    assert exc.value.stage == "scrape"


def test_discovery_stops_before_the_next_query_once_the_ceiling_is_crossed(tmp_path, monkeypatch):
    from g3o.run.presweep import stage_discovery

    mon = _monitor(budget=0.0015)
    _install_raising_guard(mon)
    issued: list[str] = []

    def _fake_search(query, **kwargs):
        issued.append(query)
        spend_meter.record(spend_meter.SERPER, credits=1, live_queries=1)
        return serper_client.SerperResult(
            results=[], search_parameters={}, from_cache=False, payload={"q": query}
        )

    monkeypatch.setattr(stage_discovery, "search_google_detailed", _fake_search)
    with pytest.raises(BudgetExceededError):
        stage_discovery._issue_queries(
            tmp_path, "inst", "discovery_general",
            [("q1", "en"), ("q2", "en"), ("q3", "en")],
            leg="1a", num_results=10, options=None, credentials=None,
            index={}, records=[], provenance=[],
        )
    assert issued == ["q1", "q2"]  # $0.001 is within, $0.002 is not


def test_run_presweep_reports_metered_spend_and_uninstalls_the_meter(tmp_path, monkeypatch):
    from g3o.run.presweep import PresweepConfig, run_presweep

    monkeypatch.setenv("SERPER_API_KEY", "serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    master = tmp_path / "master.csv"
    master.write_text(
        "institution_uid,institution_id,name,country,government_level,institution_type,url\n"
        "G3O-I-00000001,inst-0001,Test Inst,TestCountry,national,university,https://example.edu\n",
        encoding="utf-8",
    )
    cfg = PresweepConfig(
        run_id="metered", runs_dir=tmp_path / "runs", master_csv=master,
        sample_size=1, seed=22294, dry_run=False, stop_after="discovery_general",
        model="gpt-5-nano", classify_official_site_model="gpt-5-nano",
        classify_triage_model="gpt-5-nano", validate_model="gpt-5-nano",
        budget_usd=0.0005,
    )

    def _fake_discovery(*args, **kwargs):
        spend_meter.record(spend_meter.SERPER, credits=3, live_queries=3)
        return {}

    with patch("g3o.run.presweep.orchestrator._run_discovery_general", _fake_discovery):
        with pytest.raises(BudgetExceededError):
            run_presweep(cfg)
    report = json.loads((cfg.runs_dir / cfg.run_id / "_cost_report.json").read_text("utf-8"))
    assert report["by_api"]["serper"]["credits"] == 3
    assert report["total_usd"] == pytest.approx(0.003)
    assert report["abort_stage"] == "discovery_general"
    assert report["budget_exceeded"] is True
    assert spend_meter._sink is None  # uninstalled in finally


# --------------------------------------------------------------------------
# Preflight: every API projected, jev at jev rates, warnings
# --------------------------------------------------------------------------


def _preflight(tmp_path: Path, monkeypatch, *, token: str | None, ceiling: float | None = None):
    from g3o.run.preflight import run_preflight

    monkeypatch.setattr(config, "UNLOCKER_API_TOKEN", token)
    rows = _build_master(n_strata=2, rows_per_stratum=5)
    master = _write_master_csv(tmp_path / "master.csv", rows)
    cfg = _make_config(tmp_path=tmp_path, master_csv=master, sample_size=10)
    return run_preflight(
        cfg, cost_ceiling_usd=ceiling,
        credentials=Credentials(
            serper_api_key="s", openai_api_key="sk-o", typesafe_api_key="t"
        ),
    )


def test_preflight_projects_every_api_and_prices_jev_stages_at_jev_rates(tmp_path, monkeypatch):
    summary = _preflight(tmp_path, monkeypatch, token="tok-123456789")
    cp = summary["cost_preview"]
    by_api = cp["est_by_api"]
    assert set(by_api) == {"openai", "typesafe", "serper", "brightdata_unlocker"}
    assert by_api["typesafe"] > 0 and by_api["serper"] > 0 and by_api["brightdata_unlocker"] > 0
    assert cp["est_total_usd"] == pytest.approx(sum(by_api.values()), abs=0.02)
    assert cp["stage_models"]["classify_triage"].startswith("jev-")
    assert cp["stage_pricing"]["classify_triage"]["batch_input_per_1m_usd"] == (
        JEV_1_13_0_PRICING["batch_input_per_1m_usd"]
    )
    assert summary["keys_ok"] is True
    assert {k["name"] for k in summary["keys"]} == {
        "SERPER_API_KEY", "OPENAI_API_KEY", "TYPESAFE_API_KEY",
    }


def test_preflight_warns_and_projects_zero_when_the_unlocker_token_is_missing(tmp_path, monkeypatch):
    summary = _preflight(tmp_path, monkeypatch, token=None)
    assert summary["cost_preview"]["est_by_api"]["brightdata_unlocker"] == 0
    assert summary["services"]["brightdata_unlocker"]["active"] is False
    assert any("brightdata_unlocker: OFF" in w for w in summary["warnings"])


def test_preflight_ceiling_is_compared_against_the_all_api_total(tmp_path, monkeypatch):
    summary = _preflight(tmp_path, monkeypatch, token="tok-123456789")
    by_api = summary["cost_preview"]["est_by_api"]
    llm_only = by_api["openai"] + by_api["typesafe"]
    between = (llm_only + summary["cost_preview"]["est_total_usd"]) / 2
    over = _preflight(tmp_path, monkeypatch, token="tok-123456789", ceiling=between)
    assert over["cost_ceiling_exceeded"] is True


# --------------------------------------------------------------------------
# Deployment / services report
# --------------------------------------------------------------------------


def _fake_git(answers: dict[str, str | None]):
    def _git(*args: str, timeout: float = 10.0):
        return answers.get(args[0])
    return _git


def test_deployment_status_detects_a_checkout_behind_origin_main(monkeypatch, tmp_path):
    monkeypatch.setattr(deployment, "DEPLOY_RECORD", tmp_path / "none.json")
    monkeypatch.setattr(deployment, "_git", _fake_git({
        "rev-parse": "aaa", "status": "", "ls-remote": "bbb	refs/heads/main",
        "cat-file": "", "merge-base": None, "rev-list": "9",
    }))
    status = _REAL_DEPLOYMENT_STATUS()
    assert status["commit"] == "aaa" and status["origin_main"] == "bbb"
    assert status["stale"] is True and status["behind"] == 9
    assert status["dirty"] is False


def test_deployment_status_flags_unfetched_commits_and_unknowns(monkeypatch, tmp_path):
    record = tmp_path / "DEPLOYED.json"
    record.write_text('{"commit": "aaa", "by": "simone"}', encoding="utf-8")
    monkeypatch.setattr(deployment, "DEPLOY_RECORD", record)
    monkeypatch.setattr(deployment, "_git", _fake_git({
        "rev-parse": "aaa", "status": " M x.py", "ls-remote": "ccc	refs/heads/main",
        "cat-file": None,
    }))
    status = _REAL_DEPLOYMENT_STATUS()
    assert status["stale"] is True and status["behind"] is None
    assert status["dirty"] is True
    assert status["deploy_record"] == {"commit": "aaa", "by": "simone"}

    monkeypatch.setattr(deployment, "_git", _fake_git({"rev-parse": "aaa", "status": ""}))
    assert _REAL_DEPLOYMENT_STATUS()["stale"] is None  # origin unreachable
    monkeypatch.setattr(deployment, "_git", _fake_git({}))
    assert _REAL_DEPLOYMENT_STATUS()["commit"] is None  # not a git checkout


def test_warnings_name_a_stale_or_dirty_checkout():
    services = deployment.services_status(
        credentials=_resolved(serper="s", openai="sk-o", typesafe="t")
    )
    warnings = deployment.warnings_for(
        services, {"stale": True, "behind": 9, "dirty": True}
    )
    assert any("behind origin/main by 9 commit(s)" in w for w in warnings)
    assert any("uncommitted changes" in w for w in warnings)


def test_doctor_exits_nonzero_when_a_needed_key_is_missing(monkeypatch, capsys):
    from g3o import cli

    monkeypatch.setenv("SERPER_API_KEY", "s")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-o")
    assert cli.main(["doctor", "--no-remote"]) == 1  # TYPESAFE_API_KEY missing
    capsys.readouterr()
    monkeypatch.setenv("TYPESAFE_API_KEY", "t")
    assert cli.main(["doctor", "--no-remote"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"deployment", "services", "warnings"}


def _resolved(**keys: str):
    from g3o.common.credentials import resolve

    return resolve(Credentials(
        serper_api_key=keys.get("serper"),
        openai_api_key=keys.get("openai"),
        typesafe_api_key=keys.get("typesafe"),
    ))
