"""Arithmetic of the per-mode run projection (PI ruling 134; priced per 130 a). Pure: no network.

Every seed here comes from ``fixtures/projection_seeds_synthetic.json``: SYNTHETIC round
numbers, not any recorded figure (the real seeds are private, PI ruling Q177 a).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from g3o.common import run_projection as rp
from g3o.common.pricing import HAIKU_5_5_PRICING

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "project_run_cost.py"
SYNTHETIC_SEEDS = Path(__file__).resolve().parent / "fixtures" / "projection_seeds_synthetic.json"


@pytest.fixture(scope="module")
def seeds():
    return rp.load_seeds(SYNTHETIC_SEEDS)


def _script():
    spec = importlib.util.spec_from_file_location("project_run_cost", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _assume(**kw):
    base = {"first_round_share": 0.8, "throughput_per_hour": 100.0, "batch_round_hours": 1.0,
            "chunks_per_page": 1.0, "request_bytes": 1e6}
    return rp.ModeAssumptions(**{**base, **kw})


def _per_inst(**kw):
    base = {"pages_per_institution": 1.0, "serper_usd": 0.004, "unlocker_usd": 0.001,
            "typesafe_usd": 0.002, "openai_usd": 0.0, "extractor_standard_usd": 0.01,
            "stage6_extractor_usd": 0.0, "x35_usd": 0.0}
    return {**base, **kw}


def test_mode_names_match_the_stage_module():
    # the stage module does not import here (typesafe_sdk); its names are fixed by ruling 134
    assert rp.MODES == ("all_batch", "mix", "no_batch")


def test_batch_multiplier_comes_from_the_haiku_rate_row(seeds):
    assert _assume().batch_multiplier == HAIKU_5_5_PRICING["batch_discount"] == 0.5
    assert rp.ModeAssumptions.from_seeds(seeds).batch_multiplier == HAIKU_5_5_PRICING["batch_discount"]


def test_the_module_carries_no_seed_figures():
    # Q177 a: the public module holds the model only; no seed table, no Drive citation
    text = (_ROOT / "g3o" / "common" / "run_projection.py").read_text(encoding="utf-8")
    assert not hasattr(rp, "SEEDS") and not hasattr(rp, "ENVELOPE_USD") and not hasattr(rp, "DEFAULT_N")
    assert "agent-" + "workspace" not in text and "STATUS" + ".md" not in text


@pytest.mark.parametrize(("mode", "expected"), [
    ("no_batch", 100.0),
    ("all_batch", 50.0),
    ("mix", 100.0 * (0.8 * 0.5 + 0.2)),
])
def test_extractor_mode_usd(mode, expected):
    assert rp.extractor_mode_usd(100.0, mode, first_round_share=0.8, batch_multiplier=0.5) == pytest.approx(expected)


def test_extractor_mode_usd_rejects_unknown_mode():
    with pytest.raises(ValueError):
        rp.extractor_mode_usd(1.0, "half", first_round_share=0.5, batch_multiplier=0.5)


def test_mix_lies_between_all_batch_and_no_batch():
    rows = {r["mode"]: r for r in rp.project_all(_per_inst(), 1000, _assume())}
    assert (rows["all_batch"]["usd"]["anthropic_perpage"] < rows["mix"]["usd"]["anthropic_perpage"]
            < rows["no_batch"]["usd"]["anthropic_perpage"])


def test_project_mode_scales_linearly_and_sums():
    a = _assume(first_round_share=1.0, batch_multiplier=0.5, mix_rounds=2)
    r = rp.project_mode(_per_inst(), 1000, "mix", a)
    assert r["usd"]["serper"] == pytest.approx(4.0)
    assert r["usd"]["unlocker"] == pytest.approx(1.0)
    assert r["usd"]["typesafe"] == pytest.approx(2.0)
    assert r["usd"]["anthropic_perpage"] == pytest.approx(5.0)
    assert r["total_usd"] == r["total_known_usd"] == pytest.approx(12.0)
    assert r["wall_hours"] == pytest.approx(10.0 + 2.0)
    assert r["wall_is_lower_bound"]  # every batch-mode wall time is a lower bound
    assert r["batch_queue_mb_lower_bound"] == 1000


def test_no_batch_has_no_rounds_and_no_queue():
    r = rp.project_mode(_per_inst(), 1000, "no_batch", _assume())
    assert r["batch_rounds"] == 0 and r["batch_queue_mb_lower_bound"] == 0
    assert r["wall_hours"] == pytest.approx(10.0)
    assert not r["wall_is_lower_bound"]


def test_all_batch_rounds_unknown_is_a_lower_bound():
    rounds, lower = rp.batch_rounds("all_batch", _assume(mix_rounds=2, all_batch_rounds=None))
    assert (rounds, lower) == (2, True)
    assert rp.batch_rounds("all_batch", _assume(all_batch_rounds=5)) == (5, False)


def test_unknown_parts_make_total_none_not_zero():
    r = rp.project_mode(_per_inst(x35_usd=None, stage6_extractor_usd=None), 10, "mix", _assume())
    assert r["total_usd"] is None
    assert set(r["unpriced"]) == {"x35", "anthropic_stage6"}
    assert r["total_known_usd"] > 0


def test_provisional_pages_withhold_the_total_and_mark_the_parts():
    r = rp.project_mode(_per_inst(pages_provisional=True), 10, "mix", _assume())
    assert r["total_withheld"] and r["total_usd"] is None and r["total_known_usd"] is None
    assert r["provisional_parts"] == ["typesafe", "anthropic_perpage"]
    table = rp.format_table([r], 10)
    assert "withheld" in table and f"{r['usd']['anthropic_perpage']:.2f}*" in table


def test_unlocker_factor_applies_to_unlocker_only():
    r1 = rp.project_mode(_per_inst(), 100, "mix", _assume(unlocker_factor=1.0))
    r2 = rp.project_mode(_per_inst(), 100, "mix", _assume(unlocker_factor=1.5))
    assert r2["usd"]["unlocker"] == pytest.approx(1.5 * r1["usd"]["unlocker"])
    assert r2["usd"]["serper"] == r1["usd"]["serper"]


def test_remaining_envelope_needs_both_inputs():
    assert rp.remaining_envelope(None, 10.0, 1000.0) is None
    assert rp.remaining_envelope(10.0, None, 1000.0) is None
    assert rp.remaining_envelope(100.0, 20.0, 1000.0) == pytest.approx(880.0)


def test_seeds_load_and_derived_seeds_follow_them(seeds):
    for name, seed in seeds.items():
        assert seed.source and ":" in seed.source, name
    first = seeds["spike_h_span_usd"].value + seeds["spike_h_pq_usd"].value
    assert rp.seed_first_round_share(seeds) == pytest.approx(first / (first + seeds["spike_h_aq_usd"].value))
    assert rp.seed_throughput_per_hour(seeds) == pytest.approx(100.0)
    assert rp.seed_chunks_per_page(seeds) == pytest.approx(2.0)
    assert rp.seed_pages_per_institution(seeds) == pytest.approx(2.0)
    per = rp.seed_per_institution(seeds)
    assert per["x35_usd"] is None and per["stage6_extractor_usd"] is None
    assert per["serper_usd"] == pytest.approx(0.01)
    assert per["pages_provisional"] and "followed pages not included" in per["pages_basis"]
    assert not rp.seed_per_institution(seeds, 3.0)["pages_provisional"]


def test_seeds_path_resolution(tmp_path):
    assert rp.resolve_seeds_path(None, {}) is None
    assert rp.resolve_seeds_path(None, {rp.SEEDS_ENV: "s.json", rp.DRIVE_ENV: str(tmp_path)}) == tmp_path / "s.json"
    assert rp.resolve_seeds_path("x.json", {rp.SEEDS_ENV: "s.json"}) == Path("x.json")
    with pytest.raises(rp.SeedsUnavailable):
        rp.load_seeds(None, {})
    with pytest.raises(rp.SeedsUnavailable):
        rp.load_seeds(tmp_path / "missing.json")


def test_seeds_file_missing_a_name_is_refused(tmp_path):
    raw = json.loads(SYNTHETIC_SEEDS.read_text(encoding="utf-8"))
    del raw["seeds"]["envelope_usd"]
    path = tmp_path / "s.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="envelope_usd"):
        rp.load_seeds(path)


def test_standard_usd_from_tokens_uses_the_up_to_threshold_standard_rates():
    part = {"model": "claude-haiku-5-5", "input_tokens": 1_000_000, "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000}
    # 0.10 + 0.50 + 0.01 + 0.125 per the rate row's up-to-100k tier, even though the sums exceed 100k
    assert rp.standard_usd_from_tokens(part) == pytest.approx(0.10 + 0.50 + 0.01 + 0.125)


def _report(**over):
    report = {
        "by_api": {"openai": {"usd": 0.0}, "typesafe": {"usd": 0.02}, "serper": {"usd": 0.08},
                   "brightdata_unlocker": {"usd": 0.01}},
        "v27_stage_cost": {
            "perpage_v27": {"parts": {
                "jev": {"usd": 0.004, "calls": 30},
                "extractor": {"model": "claude-haiku-5-5", "calls": 40, "batch_calls": 30,
                              "input_tokens": 200_000, "output_tokens": 20_000,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                              "usd": 0.012},
                "x35": {"calls": 0, "usd": None}}},
            "stage6_v27": {"parts": {
                "jev": {"usd": 0.002, "calls": 20},
                "extractor": {"calls": 5, "usd": 0.003},
                "x35": {"calls": 7, "usd": None}}},
        },
    }
    report.update(over)
    return report


def test_per_institution_from_cost_report():
    per = rp.per_institution_from_cost_report(_report(), 20)
    assert per["serper_usd"] == pytest.approx(0.004)
    assert per["unlocker_usd"] == pytest.approx(0.0005)
    assert per["typesafe_usd"] == pytest.approx((0.02 + 0.004 + 0.002) / 20)
    # all-live price of the tokens, whatever the smoke's mode was: 0.2 M x 0.10 + 0.02 M x 0.50
    assert per["extractor_standard_usd"] == pytest.approx((0.02 + 0.01) / 20)
    assert per["stage6_extractor_usd"] == pytest.approx(0.003 / 20)
    assert per["x35_usd"] is None  # calls, no USD: unknown, never zero
    assert per["extractor_batch_calls"] == 30


def test_per_institution_without_stage6_leaves_it_unknown():
    report = _report()
    del report["v27_stage_cost"]["stage6_v27"]
    per = rp.per_institution_from_cost_report(report, 20)
    assert per["stage6_extractor_usd"] is None and per["x35_usd"] is None


def test_per_institution_x35_without_calls_costs_nothing():
    report = _report()
    report["v27_stage_cost"]["stage6_v27"]["parts"]["x35"] = {"calls": 0, "usd": None}
    assert rp.per_institution_from_cost_report(report, 20)["x35_usd"] == 0.0


def test_per_institution_refuses_a_report_without_v27_cost():
    with pytest.raises(ValueError, match="v27_stage_cost"):
        rp.per_institution_from_cost_report(_report(v27_stage_cost=None), 20)


def test_per_institution_refuses_a_null_serper_and_keeps_the_other_apis():
    report = _report()
    report["by_api"]["serper"]["usd"] = None  # the other by_api entries stay in place
    assert set(report["by_api"]) == {"openai", "typesafe", "serper", "brightdata_unlocker"}
    with pytest.raises(ValueError, match="serper"):
        rp.per_institution_from_cost_report(report, 20)


def test_per_institution_rejects_nonpositive_n():
    with pytest.raises(ValueError):
        rp.per_institution_from_cost_report(_report(), 0)


def _run_dir(tmp_path, events, report=None):
    (tmp_path / "_cost_report.json").write_text(json.dumps(report or _report()), encoding="utf-8")
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return tmp_path


def test_script_reads_a_run_dir_and_prints_the_envelope_line(tmp_path, capsys):
    rd = _run_dir(tmp_path, [
        {"ts": "2026-11-16T00:00:00Z", "event": "run_launched"},
        {"event": "heartbeat"},  # no ts: skipped, not a crash
        {"ts": "2026-11-16T00:01:00Z", "event": "stage_started", "stage": "perpage_v27",
         "payload": {"counts_in": 30}},
        {"ts": "2026-11-16T00:03:00Z", "event": "run_completed"},
    ])
    mod = _script()
    assert mod.main(["--seeds", str(SYNTHETIC_SEEDS), "--run-dir", str(rd),
                     "--recorded-usd", "100", "--wave5-resume-usd", "20"]) == 0
    out = capsys.readouterr().out
    assert "remaining envelope: $1,000.00 - $100.00 - $20.00 = $880.00" in out
    assert "recompute" in out and "Q176 b" in out
    assert "smoke wall time 180 s" in out
    assert "smoke per-page stage, 30 pages in / 20 institutions" in out
    for mode in rp.MODES:
        assert mode in out


def test_script_run_dir_without_a_page_count_names_the_seed_basis(tmp_path, capsys):
    rd = _run_dir(tmp_path, [{"ts": "2026-11-16T00:00:00Z", "event": "run_launched"}])
    _script().main(["--seeds", str(SYNTHETIC_SEEDS), "--run-dir", str(rd)])
    out = capsys.readouterr().out
    assert "no per-page stage page count" in out and "withheld" not in out


def test_script_without_spend_inputs_reports_unknown(capsys):
    assert _script().main(["--seeds", str(SYNTHETIC_SEEDS)]) == 0
    out = capsys.readouterr().out
    assert "remaining envelope: unknown" in out and "$100.00-$120.00" in out


def test_script_without_seeds_exits_2(monkeypatch, capsys):
    monkeypatch.delenv(rp.SEEDS_ENV, raising=False)
    assert _script().main([]) == 2
    assert rp.SEEDS_ENV in capsys.readouterr().err


def test_script_warns_on_a_cache_served_smoke(tmp_path, capsys):
    report = _report()
    report["by_api"]["serper"]["usd"] = 0.0
    rd = _run_dir(tmp_path, [], report)
    _script().main(["--seeds", str(SYNTHETIC_SEEDS), "--run-dir", str(rd)])
    assert "SERP cache" in capsys.readouterr().out


def test_seed_mode_withholds_the_total_without_pages(capsys):
    mod = _script()
    out = mod.run(mod.build_parser().parse_args(["--seeds", str(SYNTHETIC_SEEDS)]), rp.load_seeds(SYNTHETIC_SEEDS))
    assert all(r["total_withheld"] and r["total_known_usd"] is None for r in out["rows"])
    assert "followed pages not included" in out["pages_basis"]


def test_seed_mode_totals_pinned_on_the_synthetic_fixture():
    # regression pin: SYNTHETIC seeds, n = the fixture's 1,000, 2 pages per institution
    mod = _script()
    args = mod.build_parser().parse_args(["--seeds", str(SYNTHETIC_SEEDS), "--pages-per-institution", "2"])
    out = mod.run(args, rp.load_seeds(SYNTHETIC_SEEDS))
    rows = {r["mode"]: r for r in out["rows"]}
    assert out["n"] == 1000
    for r in rows.values():
        assert r["usd"]["serper"] == pytest.approx(10.0)
        assert r["usd"]["unlocker"] == pytest.approx(2.0)
        assert r["usd"]["typesafe"] == pytest.approx(21.0)
        assert r["unpriced"] == ["anthropic_stage6", "x35"] and r["total_usd"] is None
    assert {m: rows[m]["usd"]["anthropic_perpage"] for m in rows} == pytest.approx(
        {"all_batch": 100.0, "mix": 120.0, "no_batch": 200.0})
    assert {m: rows[m]["total_known_usd"] for m in rows} == pytest.approx(
        {"all_batch": 133.0, "mix": 153.0, "no_batch": 233.0})
    assert {m: rows[m]["wall_hours"] for m in rows} == pytest.approx(
        {"all_batch": 12.0, "mix": 12.0, "no_batch": 10.0})
    assert {m: rows[m]["batch_queue_mb_lower_bound"] for m in rows} == {"all_batch": 400, "mix": 400, "no_batch": 0}
    text = mod.render(out, rp.load_seeds(SYNTHETIC_SEEDS))
    assert ">=12.0" in text and "lower bound" in text and "10-request spike round trip" in text


def test_preflight_mode_estimates_show_three_modes_and_zero_an_unused_unlocker():
    from g3o.run.preflight import _extractor_mode_estimates

    est = _extractor_mode_estimates(1000, unlocker_on=False, configured_mode="mix",
                                    seeds_path=str(SYNTHETIC_SEEDS))
    assert est["is_estimate"] and est["seeds_available"]
    assert est["default_mode"] == "mix" and est["configured_mode"] == "mix"
    assert [r["mode"] for r in est["rows"]] == list(rp.MODES)
    assert all(r["usd"]["unlocker"] == 0.0 for r in est["rows"])
    assert "x35" in est["rows"][0]["unpriced"]
    assert "v2.7 followed pages not included" in est["note"]
    assert "withheld" in est["table"] and "lower bound" in est["table"]
    on = _extractor_mode_estimates(1000, unlocker_on=True, configured_mode=None, seeds_path=str(SYNTHETIC_SEEDS))
    assert on["rows"][0]["usd"]["unlocker"] > 0


def test_preflight_without_seeds_says_unavailable_and_never_raises(monkeypatch, tmp_path):
    from g3o.run.preflight import _extractor_mode_estimates

    monkeypatch.delenv(rp.SEEDS_ENV, raising=False)
    est = _extractor_mode_estimates(1000, unlocker_on=True, configured_mode="mix")
    assert est["is_estimate"] and est["seeds_available"] is False and "seeds unavailable" in est["note"]
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert "error" in _extractor_mode_estimates(1000, unlocker_on=True, configured_mode=None, seeds_path=str(bad))
