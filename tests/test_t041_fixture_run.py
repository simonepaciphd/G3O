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
    out = fr.output_paths(tmp_path, fr.MODE_DRY)
    doc = json.loads(out["results"].read_text(encoding="utf-8"))
    assert doc["mode"] == "dry-run" and doc["options"]["extractor_mode"] == "no_batch"
    assert len(doc["results"]) == 66 and {r["status"] for r in doc["results"]} == {fr.NOT_RUN}
    plan = json.loads(out["plan"].read_text(encoding="utf-8"))
    assert len(plan["plans"]) == 66 and plan["estimate"]["fixtures_runnable"] == 32
    report = out["report"].read_text(encoding="utf-8")
    assert fr.F6C_LINE in report
    assert fr.existing_live_outputs(tmp_path) == []  # review M2: a dry run never writes live files and all(limit in report for limit in fr.QUOTE_MATCH_LIMITS)


@pytest.mark.parametrize("extra", [[], ["--max-usd", "5"], ["--runtime", "rt.json"], ["--max-usd", "0", "--runtime",
                                                                                         "rt.json"]])
def test_live_without_cap_and_runtime_is_refused_before_any_work(tmp_path, monkeypatch, extra):
    _forbid_live(monkeypatch)
    rc = _script().main(["--live", "--out-dir", str(tmp_path), *extra])
    assert rc == 2
    assert not any(tmp_path.iterdir())


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
        fr.run_live([], dispatch=SimpleNamespace(extractor_mode="mix"), run_root=tmp_path, max_usd=1.0,
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
    from g3o.run.presweep import stage_validate_v27 as svv
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
        assert live.entail_fn is x35  # review M4: the X35 client is passed through unwrapped
        journal = svv.RequestJournal(institution_dir(run_dir, inst_id) / svv.WORK_DIR / svv.JOURNAL)
        entail = journal.seams({"x35_model": "m"})[1](live.entail_fn)
        entail("question", "text")
        entail("question", "text")
        storage = {"summary": {"values": {"core.has_genai_activity": "no"}},
                   "sources": {"S1": {"values": {"core.source_url": url, "core.page_verdict": "confirms_activity"}}},
                   "activities": {}}
        path = institution_dir(run_dir, inst_id) / STORAGE_ARTIFACT
        path.write_text(json.dumps(storage), encoding="utf-8")
        return {"n_stage6_written": 1}

    run = fr.run_live([first, second], dispatch=dispatch, run_root=tmp_path, max_usd=0.5,
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

    run = fr.run_live([_fixture([]), _fixture([], fixture_id="F-2")], dispatch=dispatch, run_root=tmp_path,
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
                      dispatch=dispatch, run_root=tmp_path, max_usd=10.0, page_loader=lambda f: fr.fixture_pages(f),
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
    assert default["status"] == fr.PARTIAL and default["a_ids"] == {"A-010": fr.PARTIAL, "A-011": fr.PARTIAL}
    every = fr.compare_fixture(fixture, lambda e: (True, {"a": "yes", "b": "x"}[e["item"]]))
    assert every["status"] == fr.PASS and every["a_ids"] == {"A-010": fr.PASS, "A-011": fr.PASS}
    failing = fr.compare_fixture(fixture, lambda e: (True, "no") if e["item"] == "a" else (False, None))
    assert failing["status"] == fr.FAIL
    assert fr.compare_fixture(_fixture([]), lambda e: (True, None))["status"] == fr.UNRESOLVED
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
    # review L2: a named activity that is absent is not located; only a bare scope takes the only activity
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity:Other"}, urls) == (False, None)
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity"}, urls) == (True, "pilot")
    # review L1: the page URL must be the source URL field, not any string value of the row
    decoy = {"sources": {"S1": {"values": {"core.source_snippet": "https://x/p0", "core.page_verdict": "no_genai"}}}}
    assert fr.locate_got(decoy, {"item": "core.page_verdict", "scope": "page:p0"}, urls) == (False, None)
    assert fr.locate_got(storage, {"item": "core.page_verdict", "scope": "page"}, urls) == (False, None)
    assert fr.locate_got(storage, {"item": "x", "scope": "pair:1"}, urls) == (False, None)
    assert fr.locate_got(None, {"item": "x", "scope": "institution"}, urls) == (False, None)


def test_x35_summary_spread_and_agreement():
    calls = [{"answer": "true", "probability": 0.95}, {"answer": "false", "probability": 0.6},
             {"answer": "true", "probability": None}]
    s = fr.x35_summary(calls)
    assert s["n_calls"] == 3 and s["n_true"] == 2 and s["n_false"] == 1 and s["n_other"] == 0
    assert s["agreement"] == pytest.approx(2 / 3) and s["agreement_answered"] == pytest.approx(2 / 3)
    assert s["n_probability_missing"] == 1 and s["probability_min"] == 0.6 and s["probability_max"] == 0.95
    assert s["n_below_0_8"] == 1
    assert fr.x35_summary([])["agreement"] is None
    assert fr.x35_summary([{"answer": None, "non_answer": True}])["agreement_answered"] is None  # review LOW-3


def test_report_skeleton_carries_limits_untested_line_and_per_fixture_rows(tmp_path):
    fixture = _fixture([{"item": "core.page_verdict", "scope": "page:p0", "value": "no_genai"}])
    result = fr.compare_fixture(fixture, lambda e: (True, "confirms_activity"))
    result["x35"] = fr.x35_summary([{"answer": "true", "probability": 0.9}, {"answer": None, "non_answer": True}])
    paths = fr.write_outputs(tmp_path, mode="live", plans=[], est={"seed_usd": None}, results=[result],
                             options={"unlocated": fr.UNRESOLVED}, spent_usd=0.12, stopped=None)
    report = paths["report"].read_text(encoding="utf-8")
    assert "curly apostrophe" in report and "CJK or Thai" in report
    assert "calendar years untested" in report
    assert "overshoot it by its own cost" in report and "excludes X35" in report  # review M1
    assert "| A-011 | 0 | 0 | 1 | 0 | 0 |" in report and fr.A_ID_ROLLUP_NOTE in report  # review M5
    assert "expected 'no_genai', got 'confirms_activity'" in report
    assert "$0.1200" in report
    assert "agreement 0.5 (answered only: 1.0)" in report  # review LOW-3
    doc = json.loads(paths["results"].read_text(encoding="utf-8"))
    assert doc["a_id_summary"] == {"A-011": {fr.FAIL: 1}}


# ---------------------------------------------------------------------------
# Run roots (review M3 / L4)
# ---------------------------------------------------------------------------


def test_fresh_run_root_is_new_per_invocation_and_refuses_reuse(tmp_path):
    root = fr.fresh_run_root(tmp_path, "20261117T000000Z")
    assert root == tmp_path / "20261117T000000Z" and root.is_dir()
    with pytest.raises(fr.RunRefused):
        fr.fresh_run_root(tmp_path, "20261117T000000Z")
    assert fr.utc_stamp().endswith("Z") and len(fr.utc_stamp()) == 16
    assert fr.default_run_base() == Path.home() / ".g3o" / "t041-runs"


def test_run_live_refuses_an_existing_fixture_run_dir_before_any_call(tmp_path):
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode=NO_BATCH)
    (tmp_path / "F-1").mkdir()

    def run_fn(*a):
        raise AssertionError("a fixture ran")

    with pytest.raises(fr.RunRefused):
        fr.run_live([_fixture([])], dispatch=dispatch, run_root=tmp_path, max_usd=1.0,
                    page_loader=lambda f: fr.fixture_pages(f), searched_policy=fr.SEARCHED_UNLINKED,
                    official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17",
                    run_fn=run_fn, cost_fn=lambda run_dir: 0.0)


# ---------------------------------------------------------------------------
# Outputs: mode-specific, never overwritten, flushed per fixture (review M2)
# ---------------------------------------------------------------------------


def test_live_refuses_to_start_over_existing_live_results(tmp_path, monkeypatch, capsys):
    _forbid_live(monkeypatch)
    rt = tmp_path / "rt.json"
    rt.write_text("{}", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    fr.output_paths(out, fr.MODE_LIVE)["results"].write_text("{}", encoding="utf-8")
    rc = _script().main(["--live", "--max-usd", "5", "--runtime", str(rt), "--drive", str(tmp_path),
                         "--out-dir", str(out), "--run-root", str(tmp_path / "runs")])
    assert rc == 2 and "never overwritten" in capsys.readouterr().err
    assert fr.output_paths(out, fr.MODE_LIVE)["results"].read_text(encoding="utf-8") == "{}"


def test_write_outputs_live_never_overwrites_and_dry_never_touches_live(tmp_path):
    kwargs = {"plans": [], "est": {"seed_usd": None}, "results": [], "options": {}}
    paths = fr.write_outputs(tmp_path, mode=fr.MODE_LIVE, spent_usd=0.0, **kwargs)
    assert paths["results"].name == "t041-live-results.json" and paths["report"].name == "T041-REPORT-live.md"
    with pytest.raises(fr.RunRefused):
        fr.write_outputs(tmp_path, mode=fr.MODE_LIVE, spent_usd=0.0, **kwargs)
    before = paths["results"].read_bytes()
    dry = fr.write_outputs(tmp_path, mode=fr.MODE_DRY, **kwargs)
    assert dry["results"].name == "t041-dry-results.json" and paths["results"].read_bytes() == before


def test_run_live_flushes_each_result_and_the_script_keeps_them_on_interrupt(tmp_path, monkeypatch):
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode=NO_BATCH)
    real_run_live = fr.run_live

    def interrupted_run_live(fixtures, **kwargs):
        def run_fn(run_dir, sample, scraped, live):
            if run_fn.n:
                raise KeyboardInterrupt
            run_fn.n += 1
        run_fn.n = 0
        return real_run_live(fixtures, run_fn=run_fn, cost_fn=lambda run_dir: 0.01, **kwargs)

    monkeypatch.setattr(fr, "run_live", interrupted_run_live)
    monkeypatch.setattr(fr, "require_live_gates", lambda d: dispatch)
    import g3o.common.credentials as creds
    import g3o.run.presweep.v27_entry as entry

    monkeypatch.setattr(entry, "build_v27_dispatch", lambda config, c: dispatch)
    monkeypatch.setattr(creds, "resolve", lambda: None)
    rt = tmp_path / "rt.json"
    rt.write_text("{}", encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(KeyboardInterrupt):
        _script().main(["--live", "--max-usd", "5", "--runtime", str(rt), "--drive", str(tmp_path),
                        "--out-dir", str(out), "--run-root", str(tmp_path / "runs"), "--group", "pipeline",
                        "--fixture", "v27-syn-A011-01", "--fixture", "v27-syn-A004-05"])
    paths = fr.output_paths(out, fr.MODE_LIVE)
    lines = paths["jsonl"].read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["fixture_id"] for x in lines] == ["v27-syn-A011-01"]  # file order
    doc = json.loads(paths["results"].read_text(encoding="utf-8"))
    assert doc["stopped"].startswith("interrupted") and doc["spent_usd"] == pytest.approx(0.01)
    assert [r["fixture_id"] for r in doc["results"]] == ["v27-syn-A011-01", "v27-syn-A004-05"]
    assert doc["results"][1]["status"] == fr.NOT_RUN


# ---------------------------------------------------------------------------
# X35 from the request journals (review M4)
# ---------------------------------------------------------------------------


def test_x35_summary_from_journals_counts_non_answers_and_failed_calls(tmp_path):
    from g3o.common.paths import institution_dir
    from g3o.extract.x35_client import X35ResponseError
    from g3o.run.presweep import stage_validate_v27 as svv

    inst_dir = institution_dir(tmp_path, "INST-SYN-9001")
    journal = svv.RequestJournal(inst_dir / svv.WORK_DIR / svv.JOURNAL)
    answers = iter([Entailment("true", 0.95), Entailment("false", 0.7)])

    def x35(question, text):
        if question == "refused":
            raise X35ResponseError("refusal", usage={"input_tokens": 10, "output_tokens": 1})
        return next(answers)

    entail = journal.seams({"x35_model": "m"})[1](x35)
    assert entail("q1", "t").value == "true"
    assert entail("q2", "t").value == "false"
    assert entail("refused", "t").value == support_check.X35_NON_ANSWER  # journaled, not raised (Q169 b)
    path = inst_dir / svv.WORK_DIR / svv.JOURNAL
    with path.open("ab") as stream:  # a billed failed call, an old no-response marker, a torn tail
        stream.write(json.dumps({"kind": "x35_failed", "key": "k1", "n": 0, "elapsed_ms": 1,
                                 "response": {"error": "E", "usage": {"input_tokens": 1}}}).encode() + b"\n")
        stream.write(json.dumps({"kind": "x35_failed", "key": "k2", "n": 0, "elapsed_ms": 1,
                                 "response": {svv.X35_USAGE_ABSENT: svv.X35_NO_RESPONSE}}).encode() + b"\n")
        stream.write(b'{"kind": "x35", "torn')
    calls = fr.journal_x35_calls(tmp_path)
    assert len(calls) == 4
    s = fr.x35_summary(calls)
    assert (s["n_calls"], s["n_true"], s["n_false"], s["n_other"]) == (4, 1, 1, 2)
    assert s["n_non_answer"] == 1 and s["n_failed"] == 1
    assert s["agreement"] == pytest.approx(1 / 4) and s["agreement_answered"] == pytest.approx(1 / 2)
    assert s["n_probability_missing"] == 2 and s["probability_min"] == 0.7
    # the summary counts the same calls the cost report prices (RequestJournal.x35_usages)
    assert len(svv.RequestJournal(path, read_only=True).x35_usages()) == len(calls)


# ---------------------------------------------------------------------------
# Typed matching (review M6)
# ---------------------------------------------------------------------------


def test_a021_04_expected_int_year_matches_the_stored_string():
    fixture = _synthetic("v27-syn-A021-04")
    (exp,) = fixture["expected"]
    assert exp["item"] == "core.year_announced" and exp["value"] == 2023
    assert fr.item_value_type("core.year_announced") == ("string", False)
    assert fr.compare_fixture(fixture, lambda e: (True, "2023"))["status"] == fr.PASS
    assert fr.compare_fixture(fixture, lambda e: (True, " 2023 "))["status"] == fr.PASS
    assert fr.compare_fixture(fixture, lambda e: (True, "2024"))["status"] == fr.FAIL
    assert fr.compare_fixture(fixture, lambda e: (True, "not_documented"))["status"] == fr.FAIL


def test_values_equal_by_schema_type_and_lists_as_multisets():
    assert fr.item_value_type("core.deployment_scale_number") == ("number", False)
    assert fr.values_equal("core.deployment_scale_number", 5, "5")
    assert fr.values_equal("core.deployment_scale_number", "not_documented", "not_documented")
    assert not fr.values_equal("core.deployment_scale_number", 5, "not_documented")
    assert fr.item_value_type("core.tool_name") == ("string", True)
    assert fr.values_equal("core.tool_name", ["Copilot", "ChatGPT"], ["ChatGPT", "Copilot"])
    assert fr.values_equal("core.tool_name", ["Copilot", "ChatGPT"], '["ChatGPT", "Copilot"]')
    assert not fr.values_equal("core.tool_name", ["Copilot", "Copilot"], ["Copilot"])
    assert not fr.values_equal("core.tool_name", ["Copilot"], "not_documented")
    assert fr.item_value_type("core.governance_form")[1] is True
    assert fr.item_value_type("core.page_verdict") == ("string", False)
    assert fr.item_value_type("followed_urls") == (None, False)
    assert fr.values_equal("followed_urls", ["b", "a"], ["a", "b"])  # unknown order: multiset
    assert not fr.values_equal("followed_urls", 1, "1")  # no schema: no type conversion


# ---------------------------------------------------------------------------
# Official site record (review M7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("policy", [fr.OFFICIAL_NONE, fr.OFFICIAL_PAGE_HOST])
def test_materialise_writes_an_official_site_record_the_loader_accepts(tmp_path, policy):
    from g3o.run.presweep.official_site_v27 import load_run_official_sites

    fixture = _fixture([])
    _, scraped, _ = fr.materialise(tmp_path, fixture, fr.fixture_pages(fixture), searched_policy=fr.SEARCHED_UNLINKED,
                                   official_policy=policy, access_date="2026-11-17")
    (inst_id,) = scraped
    sites = load_run_official_sites(tmp_path)
    assert inst_id not in sites.unresolved
    if policy == fr.OFFICIAL_NONE:
        assert inst_id in sites.no_site
    else:
        assert sites.hosts[inst_id] == "synthetic.example"


def test_page_host_warning_is_printed_for_real_fixtures(tmp_path, monkeypatch, capsys):
    _forbid_live(monkeypatch)
    assert _script().main(["--group", "real", "--out-dir", str(tmp_path)]) == 0
    assert fr.PAGE_HOST_NOTE in capsys.readouterr().out
    assert _script().main(["--group", "pipeline", "--out-dir", str(tmp_path)]) == 0
    assert fr.PAGE_HOST_NOTE not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Seeds file errors (review L5)
# ---------------------------------------------------------------------------


def test_seeds_file_without_chunk_target_is_a_clean_error(tmp_path, monkeypatch, capsys):
    _forbid_live(monkeypatch)
    seeds = tmp_path / "seeds.json"
    seeds.write_text(json.dumps({"seeds": {"spike_pages": {"value": 50, "source": "S:24"}}}), encoding="utf-8")
    rc = _script().main(["--group", "pipeline", "--seeds", str(seeds), "--out-dir", str(tmp_path / "out")])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("error: seeds file") and "spike_chunk_target_bytes" in err
    assert not (tmp_path / "out").exists()
    assert fr.missing_seeds({"spike_pages": object()}) == [n for n in fr.T041_SEEDS if n != "spike_pages"]
    assert fr.missing_seeds(None) == []
