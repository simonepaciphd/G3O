"""T-041 fixture runner (PI Q184 a): dry run, live refusals, sync mode, comparison, report skeleton.

Offline: no network and no paid call. The live path is exercised with fakes only (a fake
``run_fn`` stands in for ``orchestrator.run_v27_dispatch``, a fake cost function for the
journal pricing, a fake X35 callable for the client).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from g3o.common import support_check
from g3o.common.support_check import Entailment
from g3o.run import fixture_run_t041 as fr

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "v27"


def _script():
    spec = importlib.util.spec_from_file_location("t041_fixture_run_script", ROOT / "scripts" / "t041_fixture_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic(fixture_id):
    return next(f for f in fr.load_fixtures(FIX) if f["fixture_id"] == fixture_id)


def _fixture(expected, a_ids=("A-011",), fixture_id="F-1"):
    return {"fixture_id": fixture_id, "kind": "synthetic", "mode": "pipeline", "a_ids": list(a_ids),
            "institution": {"institution_id": "SYN-9001", "name": "Test Council", "country": "United Kingdom",
                            "level": "local"},
            "pages": [{"page_key": "p0", "url": "https://synthetic.example/syn-9001/p0", "title": "",
                       "fetch_status": "ok", "chrome_text": "", "links": [], "text": "The council uses Copilot."}],
            "expected": list(expected)}


@pytest.fixture(autouse=True)
def _no_seeds(monkeypatch):
    monkeypatch.delenv("G3O_PROJECTION_SEEDS", raising=False)
    monkeypatch.delenv(fr.DRIVE_ENV, raising=False)


# ---------------------------------------------------------------------------
# Selection and plan
# ---------------------------------------------------------------------------


def test_selection_never_includes_transfers_and_rejects_unknown_groups():
    fixtures = fr.load_fixtures(FIX) + [{"fixture_id": "T", "kind": "real_transfer", "a_ids": ["A-022"]}]
    chosen = fr.select_fixtures(fixtures)
    assert chosen and all(f["kind"] != "real_transfer" for f in chosen)
    assert {fr.fixture_group(f) for f in chosen} <= set(fr.GROUPS)
    with pytest.raises(ValueError):
        fr.select_fixtures(fixtures, ["transfer"])
    with pytest.raises(ValueError):
        fr.select_fixtures(fixtures, [fr.GROUP_PIPELINE], ids=["no-such-fixture"])


def test_every_synthetic_fixture_validates():
    synthetic = fr.select_fixtures(fr.load_fixtures(FIX), [fr.GROUP_PIPELINE, fr.GROUP_INJECTED])
    assert len(synthetic) == 66
    assert {f["fixture_id"]: fr.validate_fixture(f) for f in synthetic if fr.validate_fixture(f)} == {}


def test_plan_counts_lower_bound_calls_and_injected_plan_none():
    ft = fr.load_fixture_text_module(FIX)
    pipe = _synthetic("v27-syn-A011-01")
    plan = fr.plan_fixture(pipe, fr.fixture_pages(pipe, fixture_text=ft))
    assert plan["runnable"] and plan["coded_pages"] == 1
    assert plan["calls_lower_bound"] == {"jev_page_round": 1, "extractor_pass1": 1, "extractor_pass2": 1}
    assert plan["page_text_tokens"] > 0
    inj = _synthetic("v27-syn-A011-09")
    iplan = fr.plan_fixture(inj, fr.fixture_pages(inj, fixture_text=ft))
    assert not iplan["runnable"] and iplan["not_run_reason"]
    assert sum(iplan["calls_lower_bound"].values()) == 0


def test_linked_page_is_followed_not_searched_by_default():
    ft = fr.load_fixture_text_module(FIX)
    fixture = _synthetic("v27-syn-A004-05")
    pages = fr.fixture_pages(fixture, fixture_text=ft)
    assert fr.searched_page_keys(pages) == ["p0"]
    assert fr.searched_page_keys(pages, fr.SEARCHED_ALL) == ["p0", "p1"]
    with pytest.raises(ValueError):
        fr.searched_page_keys(pages, "bogus")


def test_estimate_cites_rate_rows_and_gives_no_usd_without_seeds():
    ft = fr.load_fixture_text_module(FIX)
    fixtures = fr.select_fixtures(fr.load_fixtures(FIX), [fr.GROUP_PIPELINE])
    plans = [fr.plan_fixture(f, fr.fixture_pages(f, fixture_text=ft)) for f in fixtures]
    est = fr.estimate(plans, jev_model="jev-1.13.0", extractor_model="claude-haiku-5-5", x35_model="claude-haiku-5-5")
    assert est["seed_usd"] is None
    rows = {r["model"]: r for r in est["pricing_rows"]}
    assert rows["jev-1.13.0"]["priced"] and rows["jev-1.13.0"]["source"]
    assert rows["claude-haiku-5-5"]["standard_input_per_1m_usd"] == 0.10
    text = fr.format_estimate(est)
    assert "USD estimate: none" in text and "g3o/common/pricing.py" in text
    assert fr.CAP_NOTE in text and fr.SEED_CHECK_NOTE in text  # review M1
    unpriced = fr.estimate(plans, jev_model="no-such-model", extractor_model="claude-haiku-5-5",
                           x35_model="claude-haiku-5-5")
    assert unpriced["page_text_input_floor_usd"] is None
    assert "NOT PRICED" in fr.format_estimate(unpriced)


def test_estimate_with_seeds_shows_formula_and_citations():
    seed = lambda v, s: SimpleNamespace(value=v, source=s)  # noqa: E731
    seeds = {"spike_pages": seed(50, "S:24"), "spike_h_span_usd": seed(0.1, "S:35"),
             "spike_h_pq_usd": seed(0.15, "S:36"), "spike_h_aq_usd": seed(0.05, "S:37"),
             "spike_jev_usd": seed(0.025, "S:30-34")}
    plans = [{"fixture_id": "F", "runnable": True, "coded_pages": 10, "page_text_tokens": 1000,
              "calls_lower_bound": {"jev_page_round": 10, "extractor_pass1": 10, "extractor_pass2": 10},
              "pages_text_unavailable": []}]
    est = fr.estimate(plans, jev_model="jev-1.13.0", extractor_model="claude-haiku-5-5",
                      x35_model="claude-haiku-5-5", seeds=seeds)
    assert est["seed_usd"]["extractor_sync_usd"] == pytest.approx(10 * 0.3 / 50)
    assert est["seed_usd"]["jev_usd"] == pytest.approx(10 * 0.025 / 50)
    assert est["seed_usd"]["x35_usd"] is None and est["seed_usd"]["stage6_quote_step_usd"] is None
    assert est["seed_usd"]["citations"]["spike_h_pq_usd"] == "S:36"


# ---------------------------------------------------------------------------
# Dry run and refusals (script)
# ---------------------------------------------------------------------------


def _forbid_live(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a live path was reached")

    monkeypatch.setattr(fr, "run_live", boom)
    monkeypatch.setattr(fr, "require_live_gates", boom)
    import g3o.run.presweep.v27_entry as entry

    monkeypatch.setattr(entry, "build_v27_dispatch", boom)


def test_dry_run_is_the_default_and_makes_no_call(tmp_path, monkeypatch, capsys):
    _forbid_live(monkeypatch)
    rc = _script().main(["--group", "pipeline", "--group", "injected", "--out-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry run: no call made" in out and "USD estimate: none" in out
    doc = json.loads((tmp_path / fr.RESULTS_FILE).read_text(encoding="utf-8"))
    assert doc["mode"] == "dry-run" and doc["options"]["extractor_mode"] == "no_batch"
    assert len(doc["results"]) == 66 and {r["status"] for r in doc["results"]} == {fr.NOT_RUN}
    plan = json.loads((tmp_path / fr.PLAN_FILE).read_text(encoding="utf-8"))
    assert len(plan["plans"]) == 66 and plan["estimate"]["fixtures_runnable"] == 32
    report = (tmp_path / fr.REPORT_FILE).read_text(encoding="utf-8")
    assert fr.F6C_LINE in report and all(limit in report for limit in fr.QUOTE_MATCH_LIMITS)


@pytest.mark.parametrize("extra", [[], ["--max-usd", "5"], ["--runtime", "rt.json"], ["--max-usd", "0", "--runtime",
                                                                                         "rt.json"]])
def test_live_without_cap_and_runtime_is_refused_before_any_work(tmp_path, monkeypatch, extra):
    _forbid_live(monkeypatch)
    rc = _script().main(["--live", "--out-dir", str(tmp_path), *extra])
    assert rc == 2
    assert not (tmp_path / fr.RESULTS_FILE).exists()


def test_live_without_drive_root_is_refused(tmp_path, monkeypatch):
    _forbid_live(monkeypatch)
    rt = tmp_path / "rt.json"
    rt.write_text("{}", encoding="utf-8")
    rc = _script().main(["--live", "--max-usd", "5", "--runtime", str(rt), "--out-dir", str(tmp_path)])
    assert rc == 2


# ---------------------------------------------------------------------------
# Gates and sync mode
# ---------------------------------------------------------------------------


def test_x35_stub_is_refused_before_the_dispatch_check():
    with pytest.raises(fr.RunRefused):
        fr.require_live_gates(SimpleNamespace(entail_fn=support_check.run_entailment))


def test_force_sync_sets_no_batch_on_a_batched_dispatch():
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode="mix",
                           batch_client=object())
    assert fr.force_sync(dispatch).extractor_mode == NO_BATCH


def test_run_live_refuses_a_dispatch_that_is_not_sync(tmp_path):
    with pytest.raises(fr.RunRefused):
        fr.run_live([], dispatch=SimpleNamespace(extractor_mode="mix"), out_dir=tmp_path, max_usd=1.0,
                    page_loader=lambda f: [], searched_policy=fr.SEARCHED_UNLINKED,
                    official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17")


def test_run_live_with_fakes_compares_records_x35_and_stops_at_the_cap(tmp_path):
    from g3o.common.paths import institution_dir
    from g3o.persist.stage6_adapters import STORAGE_ARTIFACT
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    x35 = lambda q, t: Entailment("true", 0.9)  # noqa: E731
    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=x35, extractor_mode=NO_BATCH)
    url = "https://synthetic.example/syn-9001/p0"
    first = _fixture([{"item": "core.page_verdict", "scope": "page:p0", "value": "confirms_activity"},
                      {"item": "core.has_genai_activity", "scope": "institution", "value": "yes"},
                      {"item": "followed_urls", "scope": "institution", "value": []}])
    second = _fixture([{"item": "core.page_verdict", "scope": "page:p0", "value": "no_genai"}], fixture_id="F-2")
    seen = []

    def run_fn(run_dir, sample, scraped, live):
        seen.append(live)
        assert live.extractor_mode == NO_BATCH
        (inst_id, pages), = scraped.items()
        assert [p.url for p in pages] == [url]
        assert live.follow_fetch(url).outcome == "FETCHED"
        assert live.follow_fetch("https://elsewhere.example/").outcome == "FETCH_FAILED"
        live.entail_fn("question", "text")
        live.entail_fn("question", "text")
        storage = {"summary": {"values": {"core.has_genai_activity": "no"}},
                   "sources": {"S1": {"values": {"core.source_url": url, "core.page_verdict": "confirms_activity"}}},
                   "activities": {}}
        path = institution_dir(run_dir, inst_id) / STORAGE_ARTIFACT
        path.write_text(json.dumps(storage), encoding="utf-8")
        return {"n_stage6_written": 1}

    run = fr.run_live([first, second], dispatch=dispatch, out_dir=tmp_path, max_usd=0.5,
                      page_loader=lambda f: fr.fixture_pages(f), searched_policy=fr.SEARCHED_UNLINKED,
                      official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17",
                      run_fn=run_fn, cost_fn=lambda run_dir: 0.5)
    assert len(seen) == 1  # the cap was reached after the first fixture
    r1, r2 = run["results"]
    assert [e["status"] for e in r1["expected"]] == [fr.PASS, fr.FAIL, fr.NOT_LOCATED]
    assert r1["status"] == fr.FAIL and r1["a_ids"] == {"A-011": fr.FAIL}
    assert r1["x35"]["n_calls"] == 2 and r1["x35"]["agreement"] == 1.0 and r1["x35"]["probability_min"] == 0.9
    assert r1["cost_usd"] == 0.5 and run["spent_usd"] == 0.5
    assert r2["status"] == fr.NOT_RUN and "cap" in r2["reason"]
    assert run["stopped"]


def test_run_live_stops_when_a_fixture_cannot_be_priced(tmp_path):
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode=NO_BATCH)
    calls = []

    def run_fn(run_dir, sample, scraped, live):
        calls.append(run_dir)
        raise RuntimeError("stage stop")

    run = fr.run_live([_fixture([]), _fixture([], fixture_id="F-2")], dispatch=dispatch, out_dir=tmp_path,
                      max_usd=10.0, page_loader=lambda f: fr.fixture_pages(f), searched_policy=fr.SEARCHED_UNLINKED,
                      official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17",
                      run_fn=run_fn, cost_fn=lambda run_dir: None)
    assert len(calls) == 1
    assert run["results"][0]["error"] == "RuntimeError: stage stop"
    assert run["results"][1]["status"] == fr.NOT_RUN


def _erroring_run(tmp_path, cost, **kwargs):
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode=NO_BATCH)
    calls = []

    def run_fn(run_dir, sample, scraped, live):
        calls.append(run_dir)
        raise RuntimeError("MissingUpstreamError: assembler refused")

    run = fr.run_live([_fixture([]), _fixture([], fixture_id="F-2"), _fixture([], fixture_id="F-3")],
                      dispatch=dispatch, out_dir=tmp_path, max_usd=10.0, page_loader=lambda f: fr.fixture_pages(f),
                      searched_policy=fr.SEARCHED_UNLINKED, official_policy=fr.OFFICIAL_PAGE_HOST,
                      unlocated=fr.UNRESOLVED, access_date="2026-11-17", run_fn=run_fn,
                      cost_fn=lambda run_dir: cost, **kwargs)
    return run, calls


def test_run_live_stops_on_the_first_error_after_spend(tmp_path):
    run, calls = _erroring_run(tmp_path, 0.25)
    assert len(calls) == 1
    first, *rest = run["results"]
    assert first["error"] and first["cost_usd"] == 0.25
    assert all(r["status"] == fr.NOT_RUN for r in rest)
    assert "with an error" in run["stopped"] and "--continue-on-error" in run["stopped"]
    assert run["spent_usd"] == 0.25


def test_run_live_goes_on_after_a_zero_cost_refusal(tmp_path):
    run, calls = _erroring_run(tmp_path, 0.0)
    assert len(calls) == 3 and run["stopped"] is None
    assert all(r["error"] for r in run["results"])


def test_continue_on_error_goes_on_after_a_paid_error(tmp_path):
    run, calls = _erroring_run(tmp_path, 0.25, continue_on_error=True)
    assert len(calls) == 3 and run["stopped"] is None
    assert run["spent_usd"] == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def test_compare_statuses_and_unlocated_policy():
    fixture = _fixture([{"item": "a", "scope": "institution", "value": "yes"},
                        {"item": "b", "scope": "institution", "value": "x"}], a_ids=("A-010", "A-011"))
    got = {"a": (True, " yes "), "b": (False, None)}
    default = fr.compare_fixture(fixture, lambda e: got[e["item"]])
    assert [e["status"] for e in default["expected"]] == [fr.PASS, fr.NOT_LOCATED]
    assert default["status"] == fr.PASS and default["a_ids"] == {"A-010": fr.PASS, "A-011": fr.PASS}
    strict = fr.compare_fixture(fixture, lambda e: got[e["item"]], unlocated=fr.FAIL)
    assert strict["status"] == fr.FAIL
    nothing = fr.compare_fixture(fixture, lambda e: (False, None))
    assert nothing["status"] == fr.UNRESOLVED
    with pytest.raises(ValueError):
        fr.compare_fixture(fixture, lambda e: (False, None), unlocated="bogus")


def test_locate_got_by_scope():
    storage = {"summary": {"values": {"core.has_genai_activity": "unclear"}},
               "sources": {"S1": {"values": {"core.source_url": "https://x/p0", "core.page_verdict": "no_genai"}},
                           "S2": {"values": {"core.source_url": "https://x/p1", "core.page_verdict": "event_only"}}},
               "activities": {"A1": {"values": {"core.activity_name": "Chatbot", "core.adoption_stage": "pilot"}}}}
    urls = {"p0": "https://x/p0", "p1": "https://x/p1"}
    assert fr.locate_got(storage, {"item": "core.has_genai_activity", "scope": "institution"}, urls) == (True, "unclear")
    assert fr.locate_got(storage, {"item": "core.page_verdict", "scope": "page:p1"}, urls) == (True, "event_only")
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity:Chatbot"}, urls) == (True, "pilot")
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity:Other"}, urls) == (True, "pilot")
    assert fr.locate_got(storage, {"item": "core.page_verdict", "scope": "page"}, urls) == (False, None)
    assert fr.locate_got(storage, {"item": "x", "scope": "pair:1"}, urls) == (False, None)
    assert fr.locate_got(None, {"item": "x", "scope": "institution"}, urls) == (False, None)


def test_x35_summary_spread_and_agreement():
    calls = [{"answer": "true", "probability": 0.95}, {"answer": "false", "probability": 0.6},
             {"answer": "true", "probability": None}]
    s = fr.x35_summary(calls)
    assert s["n_calls"] == 3 and s["n_true"] == 2 and s["n_false"] == 1 and s["n_other"] == 0
    assert s["agreement"] == pytest.approx(2 / 3)
    assert s["n_probability_missing"] == 1 and s["probability_min"] == 0.6 and s["probability_max"] == 0.95
    assert s["n_below_0_8"] == 1
    assert fr.x35_summary([])["agreement"] is None


def test_report_skeleton_carries_limits_untested_line_and_per_fixture_rows(tmp_path):
    fixture = _fixture([{"item": "core.page_verdict", "scope": "page:p0", "value": "no_genai"}])
    result = fr.compare_fixture(fixture, lambda e: (True, "confirms_activity"))
    paths = fr.write_outputs(tmp_path, mode="live", plans=[], est={"seed_usd": None}, results=[result],
                             options={"unlocated": fr.UNRESOLVED}, spent_usd=0.12, stopped=None)
    report = paths["report"].read_text(encoding="utf-8")
    assert "curly apostrophe" in report and "CJK or Thai" in report
    assert "calendar years untested" in report
    assert "overshoot it by its own cost" in report and "excludes X35" in report  # review M1
    assert "| A-011 | 0 | 1 | 0 | 0 |" in report
    assert "expected 'no_genai', got 'confirms_activity'" in report
    assert "$0.1200" in report
    doc = json.loads(paths["results"].read_text(encoding="utf-8"))
    assert doc["a_id_summary"] == {"A-011": {fr.FAIL: 1}}
