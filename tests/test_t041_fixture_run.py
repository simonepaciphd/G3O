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
    assert fr.existing_live_outputs(tmp_path) == []  # review M2: a dry run never writes live files
    assert fr.QUOTE_MATCH_LIMITS and all(limit in report for limit in fr.QUOTE_MATCH_LIMITS)  # review LOW-1


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
    # PI ruling Q202 c: with exactly one activity in the run, it is compared whatever its name
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity:Other"}, urls) == (True, "pilot")
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity"}, urls) == (True, "pilot")
    # review L1: the page URL must be the source URL field, not any string value of the row
    decoy = {"sources": {"S1": {"values": {"core.source_snippet": "https://x/p0", "core.page_verdict": "no_genai"}}}}
    assert fr.locate_got(decoy, {"item": "core.page_verdict", "scope": "page:p0"}, urls) == (False, None)
    assert fr.locate_got(storage, {"item": "core.page_verdict", "scope": "page"}, urls) == (False, None)
    assert fr.locate_got(storage, {"item": "x", "scope": "pair:1"}, urls) == (False, None)
    assert fr.locate_got(None, {"item": "x", "scope": "institution"}, urls) == (False, None)


def _activities(*rows):
    return {"summary": {"values": {}}, "sources": {},
            "activities": {f"A{k}": {"values": values, "activity_relations": []} for k, values in enumerate(rows, 1)}}


def test_q202c_several_activities_match_names_exactly():
    storage = _activities({"core.activity_name": "Chatbot", "core.adoption_stage": "pilot"},
                          {"core.activity_name": "Copilot", "core.adoption_stage": "in_use"})
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity:Copilot"}, {}) == (True, "in_use")
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity:chatbot"}, {}) == (False, None)
    assert fr.locate_got(storage, {"item": "core.adoption_stage", "scope": "activity"}, {}) == (False, None)
    assert fr.locate_got(_activities(), {"item": "core.adoption_stage", "scope": "activity:X"}, {}) == (False, None)


def test_q202c_name_is_checked_as_its_own_value():
    fixture = _fixture([{"item": "core.adoption_stage", "scope": "activity:AI chatbot", "value": "pilot"},
                        {"item": "core.target_users", "scope": "activity:AI chatbot", "value": "staff"},
                        {"item": "core.page_verdict", "scope": "page:p0", "value": "confirms_activity"}])
    values = fr.expected_values(fixture)
    assert len(values) == 4 and values[:3] == fixture["expected"]  # one name value per named activity scope
    assert values[3] == {"item": "core.activity_name", "scope": "activity:AI chatbot", "value": "AI chatbot",
                         "derived": fr.NAME_CHECK_RULE}
    urls = {"p0": "https://synthetic.example/syn-9001/p0"}
    sources = {"S1": {"values": {"core.source_url": urls["p0"], "core.page_verdict": "confirms_activity"}}}

    def run(name):
        storage = {**_activities({"core.activity_name": name, "core.adoption_stage": "pilot",
                                  "core.target_users": "staff"}), "sources": sources}
        return fr.compare_fixture(fixture, lambda e: fr.locate_got(storage, e, urls))

    same = run("AI chatbot")
    assert [e["status"] for e in same["expected"]] == [fr.PASS] * 4 and same["status"] == fr.PASS
    other = run("Ask Kira chatbot")  # the one activity is compared; only the name value fails
    assert [e["status"] for e in other["expected"]] == [fr.PASS, fr.PASS, fr.PASS, fr.FAIL]
    assert other["status"] == fr.FAIL
    name_row = other["expected"][3]
    assert name_row["index"] is None and name_row["derived"] == fr.NAME_CHECK_RULE
    assert name_row["got"] == "Ask Kira chatbot"


def test_q202c_no_duplicate_name_value_and_none_for_pairs_or_bare_scope():
    fixture = _fixture([{"item": "core.activity_name", "scope": "activity:Bot", "value": "Bot"},
                        {"item": "core.adoption_stage", "scope": "activity:Bot", "value": "pilot"},
                        {"item": "core.adoption_stage", "scope": "activity", "value": "pilot"},
                        {"item": "core.activity_segment", "scope": "pair:Bot|Policy", "value": "governed_by"}])
    assert fr.expected_values(fixture) == fixture["expected"]


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


def _live_script_fakes(tmp_path, monkeypatch, run_fn):
    """Fakes for a script-level live run: gates pass, ``run_fn`` stands in for the pipeline, and
    the journal pricing reads ``spend.json`` the fake writes into each fixture run directory."""
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode=NO_BATCH)
    real_run_live = fr.run_live

    def priced(run_dir):
        spend = Path(run_dir) / "spend.json"
        return json.loads(spend.read_text(encoding="utf-8"))["usd"] if spend.exists() else 0.0

    monkeypatch.setattr(fr, "journal_cost", lambda d: priced)
    monkeypatch.setattr(fr, "run_live", lambda fixtures, **kwargs: real_run_live(fixtures, run_fn=run_fn, **kwargs))
    monkeypatch.setattr(fr, "require_live_gates", lambda d: dispatch)
    import g3o.common.credentials as creds
    import g3o.run.presweep.v27_entry as entry

    monkeypatch.setattr(entry, "build_v27_dispatch", lambda config, c: dispatch)
    monkeypatch.setattr(creds, "resolve", lambda: None)
    rt = tmp_path / "rt.json"
    rt.write_text("{}", encoding="utf-8")
    return ["--live", "--max-usd", "5", "--runtime", str(rt), "--drive", str(tmp_path), "--out-dir",
            str(tmp_path / "out"), "--run-root", str(tmp_path / "runs"), "--group", "pipeline",
            "--fixture", "v27-syn-A011-01", "--fixture", "v27-syn-A004-05", "--fixture", "v27-syn-A004-04"]


def _interrupting_run_fn():
    """First fixture: $0.01 journaled, then finishes. Second: $0.02 journaled, then Ctrl-C."""
    def run_fn(run_dir, sample, scraped, live):
        usd = 0.01 if run_fn.n == 0 else 0.02
        (Path(run_dir) / "spend.json").write_text(json.dumps({"usd": usd}), encoding="utf-8")
        run_fn.n += 1
        if run_fn.n == 2:
            raise KeyboardInterrupt
    run_fn.n = 0
    return run_fn


def test_run_live_flushes_each_result_and_the_script_keeps_them_on_interrupt(tmp_path, monkeypatch, capsys):
    argv = _live_script_fakes(tmp_path, monkeypatch, _interrupting_run_fn())
    with pytest.raises(KeyboardInterrupt):
        _script().main(argv)
    paths = fr.output_paths(tmp_path / "out", fr.MODE_LIVE)
    lines = paths["jsonl"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1  # only the finished fixture is flushed
    first = json.loads(lines[0])["fixture_id"]
    doc = json.loads(paths["results"].read_text(encoding="utf-8"))
    # review MEDIUM-1: the in-flight fixture's journaled spend is counted and it is labelled partial
    assert doc["stopped"].startswith("interrupted") and doc["spent_usd"] == pytest.approx(0.03)
    by_id = {r["fixture_id"]: r for r in doc["results"]}
    assert set(by_id) == {"v27-syn-A011-01", "v27-syn-A004-05", "v27-syn-A004-04"}
    assert by_id[first]["cost_usd"] == pytest.approx(0.01)
    reasons = sorted(r["reason"] for fid, r in by_id.items() if fid != first)
    assert reasons == ["interrupted while running (partial spend $0.0200)",
                       "interrupted: the run ended before this fixture"]
    assert all(r["status"] == fr.NOT_RUN for fid, r in by_id.items() if fid != first)
    assert "journaled spend $0.0300" in capsys.readouterr().err


def test_a_failing_output_write_does_not_mask_the_interrupt(tmp_path, monkeypatch, capsys):
    argv = _live_script_fakes(tmp_path, monkeypatch, _interrupting_run_fn())

    def broken_write(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(fr, "write_outputs", broken_write)
    with pytest.raises(KeyboardInterrupt):  # review LOW-4: the original exception, not the write error
        _script().main(argv)
    assert "could not write the live outputs: RuntimeError: disk full" in capsys.readouterr().err


def test_price_run_root_records_a_pricing_failure_instead_of_raising(tmp_path):
    (tmp_path / "F-1").mkdir()
    (tmp_path / "F-2").mkdir()

    def cost(run_dir):
        if run_dir.name == "F-2":
            raise KeyError("x35_model")
        return 0.5

    priced = fr.price_run_root(tmp_path, cost)
    assert priced["F-1"] == {"cost_usd": 0.5, "error": None}
    assert priced["F-2"]["cost_usd"] is None and "KeyError" in priced["F-2"]["error"]
    run = fr.interrupted_run([_fixture([]), _fixture([], fixture_id="F-2")], [], priced, "x.jsonl")
    assert run["spent_usd"] is None and "pricing failed for ['F-2']" in run["stopped"]
    assert run["results"][1]["reason"].startswith("interrupted while running (partial spend unpriced); pricing failed")
    assert fr.price_run_root(tmp_path / "absent", cost) == {}


def test_run_live_records_post_run_errors_and_stops_after_spend(tmp_path, monkeypatch):
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode=NO_BATCH)

    def bad_storage(run_dir):
        raise json.JSONDecodeError("bad", "", 0)

    def bad_journal(run_dir):
        raise OSError("locked")

    monkeypatch.setattr(fr, "_read_storage", bad_storage)
    monkeypatch.setattr(fr, "journal_x35_calls", bad_journal)
    run = fr.run_live([_fixture([]), _fixture([], fixture_id="F-2")], dispatch=dispatch, run_root=tmp_path,
                      max_usd=10.0, page_loader=lambda f: fr.fixture_pages(f), searched_policy=fr.SEARCHED_UNLINKED,
                      official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17",
                      run_fn=lambda *a: None, cost_fn=lambda run_dir: 0.25)
    first = run["results"][0]
    assert "storage artifact unreadable: JSONDecodeError" in first["error"]
    assert "X35 journals unreadable: OSError: locked" in first["error"] and first["x35"]["journal_error"]
    assert first["cost_usd"] == 0.25 and run["results"][1]["status"] == fr.NOT_RUN
    assert "with an error" in run["stopped"]

    def bad_cost(run_dir):
        raise KeyError("x35_model")

    run = fr.run_live([_fixture([], fixture_id="F-3")], dispatch=dispatch, run_root=tmp_path / "r2",
                      max_usd=10.0, page_loader=lambda f: fr.fixture_pages(f), searched_policy=fr.SEARCHED_UNLINKED,
                      official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17",
                      run_fn=lambda *a: None, cost_fn=bad_cost)
    assert run["results"][0]["cost_usd"] is None and "pricing failed: KeyError" in run["results"][0]["error"]
    assert "could not be priced" in run["stopped"]


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
# Run telemetry readers (PI ruling Q194 c)
# ---------------------------------------------------------------------------


def _write_follow_state(run_dir, inst_id, tried, *, cap_reached=False):
    """A v2.7 follow state written by the follow leg's own payload function; ``tried`` is
    ``[(url, outcome), ...]`` in record order."""
    from g3o.common.paths import institution_dir
    from g3o.run.presweep import follow_v27 as fv
    from g3o.scrape import follow as fl

    state = fl.InstitutionFollow(inst_id, "T041-run")
    state.records = [fl.FollowRecord(institution_id=inst_id, url=url, url_key=url, parent_page_id="P0",
                                     parent_url="https://synthetic.example/parent", hop=1, link_id=f"L{k}",
                                     link_quote="", outcome=outcome, fetch_date=None, release_id="T041-run",
                                     backfill=False, counted=True)
                     for k, (url, outcome) in enumerate(tried)]
    state.followed, state.cap_reached = len(state.records), cap_reached
    path = institution_dir(run_dir, inst_id) / fv.FOLLOW_DIR / fv.STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fv.state_payload(state)), encoding="utf-8")
    return path


def test_q194c_follow_state_reads_followed_urls_and_cap_reached(tmp_path):
    fixture = _synthetic("v27-syn-A004-05")
    urls = {p["page_key"]: p["url"] for p in fixture["pages"]}
    assert fr.load_run_telemetry(tmp_path) == {"follow_state": None}
    _write_follow_state(tmp_path, "INST-SYN-0034", [(urls["p1"], "fetch_failed"),
                                                    ("https://elsewhere.example/x", "fetched")], cap_reached=True)
    telemetry = fr.load_run_telemetry(tmp_path)
    followed = {"item": "followed_urls", "scope": "institution", "value": ["p1"]}
    # every URL tried, any outcome (A004-05: a failed fetch is followed), as page keys; unknown URL kept as is
    assert fr.locate_got(None, followed, urls, telemetry) == (True, ["p1", "https://elsewhere.example/x"])
    assert fr.locate_got(None, {"item": "cap_reached", "scope": "institution"}, urls, telemetry) == (True, True)
    assert fr.locate_got(None, {"item": "cap_reached", "scope": "page:p0"}, urls, telemetry) == (False, None)
    assert fr.locate_got(None, followed, urls) == (False, None)  # no run records: behaviour a
    assert fr.locate_got(None, followed, urls, {"follow_state": None}) == (False, None)

    only_p1 = tmp_path / "only"
    _write_follow_state(only_p1, "INST-SYN-0034", [(urls["p1"], "fetch_failed")])
    t = fr.load_run_telemetry(only_p1)
    rows = {e["item"]: e for e in fr.compare_fixture(fixture, lambda e: fr.locate_got(None, e, urls, t))["expected"]}
    assert rows["followed_urls"]["status"] == fr.PASS and rows["followed_urls"]["got"] == ["p1"]


def test_q194c_malformed_follow_state_is_a_value_error(tmp_path):
    path = _write_follow_state(tmp_path, "INST-SYN-0034", [])
    path.write_text(json.dumps({"format": "other"}), encoding="utf-8")
    with pytest.raises(ValueError, match="not of format"):
        fr.load_run_telemetry(tmp_path)
    path.write_bytes(b'{"format": ')
    with pytest.raises(ValueError):
        fr.load_run_telemetry(tmp_path)
    _write_follow_state(tmp_path / "two", "INST-SYN-0001", [])
    _write_follow_state(tmp_path / "two", "INST-SYN-0002", [])
    with pytest.raises(ValueError, match="2 institutions"):
        fr.load_run_telemetry(tmp_path / "two")


def _relation(lhs, rhs, relation, scope="within_page"):
    return {"relation_id": f"REL-{lhs}{rhs}{relation}", "lhs_observation_id": f"O-{lhs}", "rhs_observation_id": f"O-{rhs}",
            "relation": relation, "source_refs": [], "support_ids": [], "lhs_final_activity_id": lhs,
            "rhs_final_activity_id": rhs, "relation_scope": scope}


def test_q194c_pair_relations_from_activity_relations():
    storage = _activities({"core.activity_name": "Ask Kira"}, {"core.activity_name": "Smart Kingsford AI Programme"},
                          {"core.activity_name": "Copilot finance pilot"})
    acts = storage["activities"]
    acts["A1"]["activity_relations"] = [_relation("A1", "A2", "component_of_program"),
                                        _relation("A1", "A3", "distinct_action", scope="cross_page")]
    seg = "core.activity_segment"
    assert fr.locate_got(storage, {"item": seg, "scope": "pair:Ask Kira|Smart Kingsford AI Programme"}, {}) == (
        True, "component_of_program")
    # direction as stored: the reverse pair is not read as the inverse relation
    assert fr.locate_got(storage, {"item": seg, "scope": "pair:Smart Kingsford AI Programme|Ask Kira"}, {}) == (
        False, None)
    # the relation scope follows the item: a cross-page relation is not a core.activity_segment value
    assert fr.locate_got(storage, {"item": seg, "scope": "pair:Ask Kira|Copilot finance pilot"}, {}) == (False, None)
    cross = {"item": "core.activity_relation_cross_page", "scope": "pair:Ask Kira|Copilot finance pilot"}
    assert fr.locate_got(storage, cross, {}) == (True, "distinct_action")
    assert fr.locate_got(storage, {"item": seg, "scope": "pair:Ask Kira|Nobody"}, {}) == (False, None)
    assert fr.locate_got(storage, {"item": seg, "scope": "pair:Ask Kira"}, {}) == (False, None)
    acts["A2"]["activity_relations"] = [_relation("A1", "A2", "governs")]  # two stored relations disagree
    assert fr.locate_got(storage, {"item": seg, "scope": "pair:Ask Kira|Smart Kingsford AI Programme"}, {}) == (
        True, ["component_of_program", "governs"])


def test_q194c_items_without_a_reader_stay_not_located(tmp_path):
    _write_follow_state(tmp_path, "INST-SYN-0034", [("https://synthetic.example/p1", "fetched")])
    telemetry = fr.load_run_telemetry(tmp_path)
    storage = _activities({"core.activity_name": "a0"})
    for item in fr.NO_READER:
        for scope in ("institution", "activity:a0"):
            assert fr.locate_got(storage, {"item": item, "scope": scope}, {}, telemetry) == (False, None)
    assert set(fr.NO_READER) == {"event_order", "extractor_calls"}


def test_q194c_run_live_reads_telemetry_and_keeps_a_malformed_state_out_of_errors(tmp_path):
    from g3o.common.paths import institution_dir
    from g3o.persist.stage6_adapters import STORAGE_ARTIFACT
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    dispatch = V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode=NO_BATCH)
    url = "https://synthetic.example/syn-9001/p0"
    expected = [{"item": "followed_urls", "scope": "institution", "value": ["https://synthetic.example/x1"]},
                {"item": "cap_reached", "scope": "institution", "value": False},
                {"item": "event_order", "scope": "institution", "value": ["pass1:p0"]}]
    good, bad = _fixture(expected), _fixture(expected, fixture_id="F-2")

    def run_fn(run_dir, sample, scraped, live):
        (inst_id, _), = scraped.items()
        path = _write_follow_state(run_dir, inst_id, [("https://synthetic.example/x1", "fetch_failed")])
        if run_dir.name == "F-2":
            path.write_bytes(b"not json")
        storage = {"summary": {"values": {}}, "sources": {"S1": {"values": {"core.source_url": url}}}, "activities": {}}
        (institution_dir(run_dir, inst_id) / STORAGE_ARTIFACT).write_text(json.dumps(storage), encoding="utf-8")

    run = fr.run_live([good, bad], dispatch=dispatch, run_root=tmp_path, max_usd=10.0,
                      page_loader=lambda f: fr.fixture_pages(f), searched_policy=fr.SEARCHED_UNLINKED,
                      official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17",
                      run_fn=run_fn, cost_fn=lambda run_dir: 0.1)
    r1, r2 = run["results"]
    assert [e["status"] for e in r1["expected"]] == [fr.PASS, fr.PASS, fr.NOT_LOCATED]
    assert r1["status"] == fr.PARTIAL and r1["error"] is None and "telemetry_error" not in r1
    assert [e["status"] for e in r2["expected"]] == [fr.NOT_LOCATED] * 3
    assert r2["error"] is None and r2["telemetry_error"].startswith(("JSONDecodeError", "UnicodeDecodeError"))
    assert run["stopped"] is None
    paths = fr.write_outputs(tmp_path / "out", mode="live", plans=[], est={"seed_usd": None}, results=run["results"],
                             options={}, spent_usd=run["spent_usd"], stopped=None)
    report = paths["report"].read_text(encoding="utf-8")
    assert fr.TELEMETRY_NOTE in report and "run records unreadable (telemetry values not located)" in report


def _sync_dispatch():
    from g3o.run.presweep.orchestrator import V27Dispatch
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    fake = lambda *a: None  # noqa: E731
    return V27Dispatch(settings=None, jev_ask_fn=fake, extract_fn=fake, entail_fn=fake, extractor_mode=NO_BATCH)


def test_review_m1_a_stage_stop_reads_no_telemetry_and_never_passes(tmp_path):
    from g3o.common.paths import institution_dir
    from g3o.persist.stage6_adapters import STORAGE_ARTIFACT

    url = "https://synthetic.example/syn-9001/p0"
    verdict = {"item": "core.page_verdict", "scope": "page:p0", "value": "confirms_activity"}
    followed = {"item": "followed_urls", "scope": "institution", "value": ["https://synthetic.example/x1"]}
    with_follow, storage_only = _fixture([verdict, followed]), _fixture([verdict], fixture_id="F-2")

    def run_fn(run_dir, sample, scraped, live):  # a partial follow state and storage, then a stage stop
        (inst_id, _), = scraped.items()
        _write_follow_state(run_dir, inst_id, [("https://synthetic.example/x1", "fetch_failed")])
        storage = {"summary": {"values": {}}, "activities": {},
                   "sources": {"S1": {"values": {"core.source_url": url, "core.page_verdict": "confirms_activity"}}}}
        (institution_dir(run_dir, inst_id) / STORAGE_ARTIFACT).write_text(json.dumps(storage), encoding="utf-8")
        raise RuntimeError("stage 6 refused")

    run = fr.run_live([with_follow, storage_only], dispatch=_sync_dispatch(), run_root=tmp_path, max_usd=10.0,
                      page_loader=lambda f: fr.fixture_pages(f), searched_policy=fr.SEARCHED_UNLINKED,
                      official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17",
                      run_fn=run_fn, cost_fn=lambda run_dir: 0.0)
    r1, r2 = run["results"]
    # (a) the follow state left by the stopped run is not read: the telemetry value is not located
    assert [e["status"] for e in r1["expected"]] == [fr.PASS, fr.NOT_LOCATED] and r1["status"] == fr.PARTIAL
    assert "stage 6 refused" in r1["error"]
    # (b) every value passed, but the run stopped: the fixture is partial, never pass
    assert [e["status"] for e in r2["expected"]] == [fr.PASS] and "stage 6 refused" in r2["error"]
    assert r2["status"] == fr.PARTIAL and r2["a_ids"] == {"A-011": fr.PARTIAL}


def test_review_l4_a_comparison_error_is_a_fixture_error_after_spend(tmp_path, monkeypatch):
    def broken(*a, **k):
        raise KeyError("expected")

    monkeypatch.setattr(fr, "compare_fixture", broken)
    fixture = _fixture([{"item": "core.page_verdict", "scope": "page:p0", "value": "no_genai"}])
    run = fr.run_live([fixture, _fixture([], fixture_id="F-2")], dispatch=_sync_dispatch(), run_root=tmp_path,
                      max_usd=10.0, page_loader=lambda f: fr.fixture_pages(f), searched_policy=fr.SEARCHED_UNLINKED,
                      official_policy=fr.OFFICIAL_PAGE_HOST, unlocated=fr.UNRESOLVED, access_date="2026-11-17",
                      run_fn=lambda *a: None, cost_fn=lambda run_dir: 0.3)
    r1, r2 = run["results"]
    assert "comparison failed: KeyError" in r1["error"] and r1["cost_usd"] == 0.3
    assert r1["status"] == fr.UNRESOLVED and r1["a_ids"] == {"A-011": fr.UNRESOLVED}
    assert [e["status"] for e in r1["expected"]] == [fr.NOT_LOCATED]
    assert r2["status"] == fr.NOT_RUN and "with an error" in run["stopped"]


def test_review_l3_same_url_key_fallback_needs_a_single_match():
    pages = {"p0": "https://synthetic.example/info", "p1": "https://synthetic.example/other"}
    assert fr._page_key("https://synthetic.example/info", pages) == "p0"  # exact
    assert fr._page_key("https://WWW.synthetic.example/info/#top", pages) == "p0"  # one same-URL-key match
    ambiguous = {"a": "https://synthetic.example/info/", "b": "https://www.synthetic.example/info"}
    assert fr._page_key("https://synthetic.example/info#x", ambiguous) == "https://synthetic.example/info#x"
    assert fr._page_key("https://www.synthetic.example/info", ambiguous) == "b"  # exact still wins
    assert fr._page_key("https://elsewhere.example/", pages) == "https://elsewhere.example/"


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


def test_explicit_seeds_path_that_does_not_exist_is_an_error_before_any_write(tmp_path, monkeypatch, capsys):
    _forbid_live(monkeypatch)  # review LOW-2: only the env-var / default lookup may be silently absent
    out = tmp_path / "out"
    rc = _script().main(["--group", "pipeline", "--seeds", str(tmp_path / "nope.json"), "--out-dir", str(out)])
    assert rc == 2
    assert capsys.readouterr().err.startswith("error: seeds file unusable")
    assert not out.exists()
