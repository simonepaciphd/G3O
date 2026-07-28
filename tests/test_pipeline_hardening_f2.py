"""Pipeline-hardening Session F.2 tests (2026-06-10, review F1/F3/F5/F7/F4/F15 + P0-8).

Covers: Serper execute-mode hard-fail and honest failure vs empty-result, the
mock-never-cached guard, the page-text cap rule, the empty-page filter, the
attrition ledger shapes/idempotence, the manifest guard on resume, and the
--preflight projection (mocked, no network).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import requests

from g3o.common import attrition
from g3o.common import config as g3o_config
from g3o.discovery import serper_client
from g3o.extract.batch import cap_page_text, is_near_empty
from g3o.run import preflight as pf
from g3o.run import presweep as ps
from g3o.run.presweep import PresweepConfig, plan_run, run_presweep, synth_institution_id
from g3o.scrape.render import FetchMetadata, RenderedPage

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_attrition_cache():
    attrition._reset_cache()
    yield
    attrition._reset_cache()


@pytest.fixture(autouse=True)
def _reset_live_mode(monkeypatch):
    # Ensure Serper live mode never leaks between tests.
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)


def _write_master(path: Path, n: int = 3) -> Path:
    fieldnames = [
        "master_row_id", "country", "government_level", "branch",
        "institution_type", "institution_name", "website",
    ]
    rows = [
        {
            "master_row_id": str(i + 1),
            "country": f"COUNTRY-{i}",
            "government_level": "national",
            "branch": "executive",
            "institution_type": "ministry",
            "institution_name": f"Ministry {i}",
            "website": "",
        }
        for i in range(n)
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return path


def _make_page(url: str, text: str) -> RenderedPage:
    return RenderedPage(
        url=url, text=text, title="t", content_type="html",
        fetch_metadata=FetchMetadata(
            access_date="2026-06-10", http_status=200, final_url=url,
            fetch_method="html", elapsed_ms=1, wait_for=None,
        ),
    )


def _config(tmp_path: Path, master: Path, **kw) -> PresweepConfig:
    return PresweepConfig(
        run_id=kw.pop("run_id", "hard-1"),
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=kw.pop("sample_size", 3),
        seed=kw.pop("seed", 22294),
        **kw,
    )


# ---------------------------------------------------------------------------
# Item A — Serper hard-fail, honest failure vs empty, mock-never-cached
# ---------------------------------------------------------------------------


def test_execute_hard_fails_without_serper_key(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv")
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", None)
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-test")
    config = _config(tmp_path, master, dry_run=False, stop_after="discovery_general")
    with pytest.raises(RuntimeError, match="SERPER_API_KEY"):
        run_presweep(config)


def test_execute_hard_fails_without_openai_key_when_llm_stage_runs(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv")
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", None)
    config = _config(tmp_path, master, dry_run=False, stop_after="extract")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        run_presweep(config)


def test_dry_run_does_not_require_keys(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv")
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", None)
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", None)
    config = _config(tmp_path, master, dry_run=True)
    summary = run_presweep(config)
    assert summary["dry_run"] is True
    assert serper_client._live_mode is False  # dry run resets live mode


def test_search_empty_result_means_searched_found_nothing(monkeypatch):
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "k")
    monkeypatch.setattr(serper_client, "_cached", lambda q, n: None)
    monkeypatch.setattr(serper_client, "_save_cache", lambda *a, **k: None)
    monkeypatch.setattr(serper_client, "_execute", lambda q, n=10: {"organic": []})
    assert serper_client.search_google("q", num_results=3) == []


def test_search_request_failure_raises_in_live_mode(monkeypatch):
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "k")
    serper_client.set_live_mode(True)
    monkeypatch.setattr(serper_client, "_cached", lambda q, n: None)

    def _boom(q, n=10):
        raise requests.HTTPError("403 quota")

    monkeypatch.setattr(serper_client, "_execute", _boom)
    with pytest.raises(serper_client.SerperRequestError, match="403 quota"):
        serper_client.search_google("q", num_results=3)


def test_search_request_failure_swallowed_in_dev_mode(monkeypatch):
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "k")
    # live mode False (autouse fixture)
    monkeypatch.setattr(serper_client, "_cached", lambda q, n: None)

    def _boom(q, n=10):
        raise requests.HTTPError("timeout")

    monkeypatch.setattr(serper_client, "_execute", _boom)
    assert serper_client.search_google("q") == []


def test_missing_key_in_live_mode_is_config_error(monkeypatch):
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", None)
    serper_client.set_live_mode(True)
    monkeypatch.setattr(serper_client, "_cached", lambda q, n: None)
    with pytest.raises(serper_client.SerperConfigError):
        serper_client.search_google("q")


def test_mock_results_are_never_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", None)  # dev mock path
    monkeypatch.setattr(g3o_config, "CACHE_DIR", tmp_path / "cache")
    # live mode False → mock returned in dev
    results = serper_client.search_google("anything", num_results=2, force_refresh=True)
    assert results and all("g3o-mock" in r["link"] for r in results)
    # Nothing written to the cache.
    assert not (tmp_path / "cache").exists() or not list((tmp_path / "cache").glob("serp_*.json"))


def test_save_cache_refuses_mock_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(g3o_config, "CACHE_DIR", tmp_path / "cache")
    serper_client._save_cache("q", 5, [{"link": "https://x.test/g3o-mock"}])
    assert not list((tmp_path / "cache").glob("serp_*.json")) if (tmp_path / "cache").exists() else True
    # A real payload IS cached, under a num_results-aware key.
    serper_client._save_cache("q", 5, [{"link": "https://real.gov/a"}])
    assert len(list((tmp_path / "cache").glob("serp_*.json"))) == 1


def test_serp_cache_key_includes_num_results():
    assert serper_client._cache_key("q", 5) != serper_client._cache_key("q", 10)


# ---------------------------------------------------------------------------
# Item B — page-text cap rule (boundary cases per D3)
# ---------------------------------------------------------------------------


def test_cap_no_truncation_at_or_below_cap():
    assert cap_page_text("abcdefghij", max_chars=10, rule="head_tail") == ("abcdefghij", False)
    assert cap_page_text("abc", max_chars=10, rule="head") == ("abc", False)


def test_cap_head_rule_keeps_first_n_original_chars():
    text = "abcdefghijZZZZ"  # 14 chars, cap 10
    capped, truncated = cap_page_text(text, max_chars=10, rule="head")
    assert truncated is True
    assert capped.startswith("abcdefghij")  # first 10 original chars
    assert "ZZZZ" not in capped.split("omitted")[0]  # tail dropped before marker
    assert "omitted" in capped  # marker names the omission


def test_cap_head_tail_keeps_first_and_last_halves():
    text = "ABCDEFGHIJKLMNOPQRST"  # 20 chars
    capped, truncated = cap_page_text(text, max_chars=10, rule="head_tail")
    assert truncated is True
    # head = 5 (10//2), tail = 5 → "ABCDE" + marker + "PQRST"
    assert capped.startswith("ABCDE")
    assert capped.endswith("PQRST")
    assert "FGHIJKLMNO" not in capped  # middle dropped
    omitted_kept = len("ABCDE") + len("PQRST")
    assert omitted_kept == 10  # exactly max_chars of the original retained


def test_cap_unknown_rule_raises():
    with pytest.raises(ValueError, match="unknown truncation rule"):
        cap_page_text("x" * 100, max_chars=10, rule="middle")


def test_is_near_empty():
    assert is_near_empty("   \n  ", min_chars=50) is True
    assert is_near_empty("short", min_chars=50) is True
    assert is_near_empty("y" * 60, min_chars=50) is False


# ---------------------------------------------------------------------------
# Item D — attrition ledger shapes + idempotence
# ---------------------------------------------------------------------------


def test_attrition_record_and_read(tmp_path):
    run_dir = tmp_path / "runs" / "r1"
    assert attrition.record(run_dir, institution_id="INST-1", stage="scrape",
                            reason="scrape_failed", url="https://x", detail="boom") is True
    recs = attrition.read_records(run_dir)
    assert len(recs) == 1
    r = recs[0]
    assert r["institution_id"] == "INST-1"
    assert r["stage"] == "scrape"
    assert r["reason"] == "scrape_failed"
    assert r["url"] == "https://x"
    assert r["detail"] == "boom"
    assert "ts" in r


def test_attrition_dedups_on_resume_key(tmp_path):
    run_dir = tmp_path / "runs" / "r2"
    assert attrition.record(run_dir, institution_id="I", stage="extract",
                            reason="page_text_truncated", url="u", original_length=99) is True
    # Same (inst, stage, reason, url) → deduped even with different detail.
    assert attrition.record(run_dir, institution_id="I", stage="extract",
                            reason="page_text_truncated", url="u", original_length=12345) is False
    assert len(attrition.read_records(run_dir)) == 1


def test_attrition_dedup_survives_cache_reset(tmp_path):
    run_dir = tmp_path / "runs" / "r3"
    attrition.record(run_dir, institution_id="I", stage="extract", reason="parse_failed", url="u")
    attrition._reset_cache()  # simulate process restart (resume)
    assert attrition.record(run_dir, institution_id="I", stage="extract",
                            reason="parse_failed", url="u") is False
    assert len(attrition.read_records(run_dir)) == 1


def test_ensure_ledger_creates_empty_file(tmp_path):
    run_dir = tmp_path / "runs" / "r4"
    p = attrition.ensure_ledger(run_dir)
    assert p.exists()
    assert attrition.read_records(run_dir) == []


# ---------------------------------------------------------------------------
# Item D — empty-page filter drops page + records ledger + builds no job
# ---------------------------------------------------------------------------


def test_empty_page_filtered_before_stage5(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv", n=1)
    rows = list(csv.DictReader(open(master, encoding="utf-8")))
    inst_id = synth_institution_id(rows[0])
    run_dir = tmp_path / "runs" / "ext"
    (run_dir / inst_id).mkdir(parents=True)

    captured = {}

    def _fake_chunked(rd, stage, jobs, **kw):
        captured["jobs"] = jobs  # don't submit anything

    monkeypatch.setattr(ps.stage_extract, "run_chunked_stage", _fake_chunked)

    scraped = {
        inst_id: [
            _make_page("https://good.gov/a", "y" * 100),   # kept
            _make_page("https://empty.gov/b", "  "),         # dropped (near-empty)
        ]
    }
    ps._run_extract(
        run_dir, rows, scraped,
        institution_search_languages="en", model="gpt-5-nano",
        poll_interval=0, max_wait=1, run_id="ext",
    )
    jobs = captured["jobs"]
    assert len(jobs) == 1  # only the good page built a job
    recs = attrition.read_records(run_dir)
    drops = [r for r in recs if r["reason"] == "empty_page_dropped"]
    assert len(drops) == 1
    assert drops[0]["url"] == "https://empty.gov/b"


def test_oversized_page_truncated_and_ledgered(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv", n=1)
    rows = list(csv.DictReader(open(master, encoding="utf-8")))
    inst_id = synth_institution_id(rows[0])
    run_dir = tmp_path / "runs" / "ext2"
    (run_dir / inst_id).mkdir(parents=True)

    captured = {}
    monkeypatch.setattr(ps.stage_extract, "run_chunked_stage",
                        lambda rd, stage, jobs, **kw: captured.update(jobs=jobs))

    big = "z" * 200_000
    scraped = {inst_id: [_make_page("https://big.gov/doc", big)]}
    ps._run_extract(
        run_dir, rows, scraped,
        institution_search_languages="en", model="gpt-5-nano",
        poll_interval=0, max_wait=1, run_id="ext2",
        text_cap_chars=60_000, text_cap_rule="head_tail",
    )
    recs = attrition.read_records(run_dir)
    trunc = [r for r in recs if r["reason"] == "page_text_truncated"]
    assert len(trunc) == 1
    assert trunc[0]["original_length"] == 200_000


# ---------------------------------------------------------------------------
# Item C — manifest guard on resume
# ---------------------------------------------------------------------------


def _seed_resume_state(run_dir: Path) -> None:
    """Create a _state/ dir so plan_run treats the next call as a resume."""
    (run_dir / "_state").mkdir(parents=True, exist_ok=True)
    (run_dir / "_state" / "discovery_general.json").write_text("{}", encoding="utf-8")


def test_manifest_guard_aborts_on_drifted_master(tmp_path):
    master = _write_master(tmp_path / "m.csv", n=6)
    config = _config(tmp_path, master, sample_size=4, run_id="g1")
    plan_run(config)  # writes manifest, no _state
    _seed_resume_state(config.runs_dir / "g1")
    # Master drifts: append rows (WS3 round-2 behavior) → sample changes.
    _write_master(tmp_path / "m.csv", n=20)
    with pytest.raises(RuntimeError, match="Resume aborted"):
        plan_run(config)


def test_manifest_guard_aborts_on_changed_args(tmp_path):
    master = _write_master(tmp_path / "m.csv", n=6)
    config = _config(tmp_path, master, sample_size=4, run_id="g2")
    plan_run(config)
    _seed_resume_state(config.runs_dir / "g2")
    drifted = _config(tmp_path, master, sample_size=4, run_id="g2", model="gpt-4.1")
    with pytest.raises(RuntimeError, match="config.model"):
        plan_run(drifted)


def test_manifest_guard_passes_clean_resume(tmp_path):
    master = _write_master(tmp_path / "m.csv", n=6)
    config = _config(tmp_path, master, sample_size=4, run_id="g3")
    plan_run(config)
    _seed_resume_state(config.runs_dir / "g3")
    # Same args, same master → no raise.
    plan = plan_run(config)
    assert plan.run_dir == config.runs_dir / "g3"


def test_manifest_guard_noop_without_state(tmp_path):
    # The seeded dry-run layout has manifest but no _state/: guard must not trip.
    master = _write_master(tmp_path / "m.csv", n=6)
    config = _config(tmp_path, master, sample_size=4, run_id="g4")
    plan_run(config)
    _write_master(tmp_path / "m.csv", n=20)  # drift, but no _state present
    plan_run(config)  # no raise — fresh projection, just overwrites manifest


# ---------------------------------------------------------------------------
# Item E — preflight projection (mocked, no network)
# ---------------------------------------------------------------------------


def test_preflight_reports_keys_sample_chunks_cost(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv", n=5)
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-openai")
    config = _config(tmp_path, master, sample_size=5, run_id="pf1")
    summary = pf.run_preflight(config, verify_model_live=False)

    assert summary["keys_ok"] is True
    assert summary["sample"]["n_institutions"] == 5
    s5 = summary["stage5_projection"]
    assert s5["n_jobs"] == 5 * 12  # default 12 pages/institution
    assert s5["n_chunks"] >= 1
    assert s5["single_job_exceeds_cap"] is False
    assert summary["cost_preview"]["est_openai_batch_total_usd"] >= 0
    assert summary["cost_preview"]["pricing"]["model"] == "gpt-5-nano"
    assert summary["verify_model"]["skipped"] is True  # no network


def test_preflight_flags_missing_keys(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv", n=3)
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", None)
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "bad-prefix")
    config = _config(tmp_path, master, sample_size=3, run_id="pf2")
    summary = pf.run_preflight(config, verify_model_live=False)
    assert summary["keys_ok"] is False
    by_name = {k["name"]: k for k in summary["keys"]}
    assert by_name["SERPER_API_KEY"]["present"] is False
    assert by_name["OPENAI_API_KEY"]["well_formed"] is False  # missing sk- prefix


def test_preflight_cost_ceiling_is_informational(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv", n=3)
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "k")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-x")
    config = _config(tmp_path, master, sample_size=3, run_id="pf3")
    summary = pf.run_preflight(config, verify_model_live=False, cost_ceiling_usd=0.0)
    assert summary["cost_ceiling_usd"] == 0.0
    assert summary["cost_ceiling_exceeded"] in (True, False)


def test_preflight_cost_preview_by_stage_sums_to_aggregate(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv", n=5)
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "k")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-x")
    config = _config(tmp_path, master, sample_size=5, run_id="pf4")
    summary = pf.run_preflight(config, verify_model_live=False)
    cost_preview = summary["cost_preview"]
    by_stage = cost_preview["by_stage"]
    assert sorted(by_stage) == [
        "classify_official_site", "classify_triage", "extract", "validate",
    ]
    # The four per-stage estimates must reconcile with the existing aggregate
    # fields (additive breakdown, not a second independent estimate).
    assert sum(s["est_input_tokens"] for s in by_stage.values()) == cost_preview["est_input_tokens"]
    assert sum(s["est_output_tokens"] for s in by_stage.values()) == cost_preview["est_output_tokens"]
    # extract dominates (12 jobs/institution vs 1 for the other three stages).
    assert by_stage["extract"]["n_jobs"] == 5 * 12
    assert by_stage["classify_official_site"]["n_jobs"] == 5
    assert by_stage["extract"]["est_usd"] > by_stage["classify_official_site"]["est_usd"]


def test_write_preflight_estimate_persists_estimate_file(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv", n=3)
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "k")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-x")
    config = _config(tmp_path, master, sample_size=3, run_id="pf5")
    run_dir = tmp_path / "runs" / "pf5"
    estimate = pf.write_preflight_estimate(run_dir, config)

    path = run_dir / pf.PREFLIGHT_ESTIMATE_NAME
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == estimate
    assert estimate["run_id"] == "pf5"
    assert estimate["sample"]["n_institutions"] == 3
    assert estimate["cost_preview"]["est_openai_batch_total_usd"] >= 0
    assert "by_stage" in estimate["cost_preview"]
    # No key-presence/verify_model noise leaks into the persisted estimate.
    assert "keys" not in estimate
    assert "verify_model" not in estimate


def test_write_preflight_estimate_honors_config_assumptions(tmp_path, monkeypatch):
    master = _write_master(tmp_path / "m.csv", n=2)
    monkeypatch.setattr(g3o_config, "SERPER_API_KEY", "k")
    monkeypatch.setattr(g3o_config, "OPENAI_API_KEY", "sk-x")
    config = _config(
        tmp_path, master, sample_size=2, run_id="pf6",
        assume_pages_per_institution=1,
    )
    run_dir = tmp_path / "runs" / "pf6"
    estimate = pf.write_preflight_estimate(run_dir, config)
    assert estimate["stage5_projection"]["n_jobs"] == 2 * 1
