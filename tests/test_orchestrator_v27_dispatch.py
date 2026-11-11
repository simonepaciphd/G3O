"""T-030 orchestrator v2.7 run-mode dispatch (off by default; not production ready).

Covers: the v2.5 default (config snapshot unchanged, no v2.7 dispatch); the
config refusals (v2.7 without the opt-in, the opt-in on v2.5, a v2.7
``stop_after`` naming a v2.5-only stage); the dispatch refusals (no injected
calls); the dispatch on the mocked e2e world (``test_e2e_perpage_v27`` /
``test_perpage_providers_v27``) through Stage 6 to the Stage 6 artifacts; the
stage stops it must not swallow (the refusing X35 entry, a missing upstream
value); the run manifest's run mode and instrument id; the whole
``run_presweep`` path with Stages 1-4 stubbed and every client constructor
monkeypatched to raise.

Every provider call is a fake. The scraped-pages -> ``PerPageInstitution``
hand-off has no producer in the pipeline; the fixture world supplies it.
"""
from __future__ import annotations

import csv
import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from g3o.common import attrition, support_check
from g3o.common.credentials import Credentials
from g3o.common.paths import institution_dir
from g3o.common.run_state import state_dir
from g3o.common.support_check import SupportGateError
from g3o.discovery import serper_client
from g3o.extract.anthropic_client import ExtractorResult
from g3o.run.presweep import orchestrator as orch
from g3o.run.presweep import planning
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.run.presweep.config import PIPELINE_V25, PIPELINE_V27, PresweepConfig
from g3o.run.presweep.records import synth_institution_id
from tests._layout import write_manifest
from tests.test_e2e_perpage_v27 import (  # noqa: F401 - _paragraph_layout is an autouse fixture
    ANSWERS,
    RELATIONS,
    SETTINGS,
    FakeJev,
    _fail_verdict,
    _paragraph_layout,
)
from tests.test_perpage_providers_v27 import USAGE, FakeEntail, FakeExtractor, _world, aid

INSTS = ("INST-0000001", "INST-0000002", "INST-0000003")
STAGE6_QUOTE = "6_quote_v27"


class FakeExtractorS6(FakeExtractor):
    """The providers-test fake extractor, also answering the Stage 6 quote step (first shown quote)."""

    def __call__(self, job):
        if job.metadata["stage"] != STAGE6_QUOTE:
            return super().__call__(job)
        self.jobs.append(job)
        user = job.params["messages"][0]["content"]
        rows = json.loads(user.split("QUOTES:\n", 1)[1].split("\n\nTASK:\n", 1)[0])
        payload = {"quote_id": rows[0]["quote_id"], "quote": rows[0]["text"]}
        n = len(self.jobs)
        return ExtractorResult(job.custom_id, True, json.dumps(payload), None, "fake-extractor-response",
                               f"msg-{n}", f"x-{n}", "end_turn", dict(USAGE))


def _merged_for(world):
    """Declared fixture (as ``pp_ready_with_merged``): INST-0000001's merged p1/p2 activity values
    that no rule computes from the merged row (RC-D-030 X1 a), taken from the p1 upstream values."""
    values = world.upstream("p1").activity_values[aid("p1")]
    key = (pp.observation_id("p1", aid("p1")), pp.observation_id("p2", aid("p2")))
    return {key: {k: v for k, v in values.items() if k in rt.MERGE_INPUT_ITEMS}}


class WorldInputs:
    """The fixture's ``perpage_inputs``: the e2e world's institutions (records what it was given)."""

    def __init__(self, world, *, merged=True, edit=None):
        self.world, self.merged, self.edit = world, merged, edit
        self.calls = []

    def __call__(self, run_dir, sample, scraped, bound, instrument):
        self.calls.append((run_dir, sample, scraped, bound.instrument_id, instrument["instrument_id"]))
        merged = _merged_for(self.world) if self.merged else None
        insts = [self.world.institution(INSTS[0], merged), self.world.institution(INSTS[1]),
                 self.world.institution(INSTS[2])]
        return self.edit(insts) if self.edit is not None else insts


def _dispatch(world, *, extract=None, entail=None, jev=None, inputs=None, **overrides):
    fields = dict(settings=SETTINGS, jev_ask_fn=jev or FakeJev(ANSWERS, RELATIONS, _fail_verdict),
                  extract_fn=extract or FakeExtractorS6(world), entail_fn=entail or FakeEntail(),
                  perpage_inputs=inputs or WorldInputs(world))
    fields.update(overrides)
    return orch.V27Dispatch(**fields)


def _world_run(tmp_path):
    run_dir, bound, instrument, world, _ = _world(tmp_path)
    write_manifest(run_dir, {"run_id": "R-T030-PP", "institutions": list(INSTS)})
    return run_dir, bound, instrument, world


def _v27_config(tmp_path, **kw):
    fields = dict(run_id="v27", runs_dir=tmp_path / "runs", master_csv=tmp_path / "master.csv",
                  pipeline_version=PIPELINE_V27, v27_not_production_ready_opt_in=True, stop_after="validate")
    fields.update(kw)
    return PresweepConfig(**fields)


# ---------------------------------------------------------------------------
# Config: off by default, explicit opt-in
# ---------------------------------------------------------------------------


def test_default_is_v25_and_the_snapshot_is_unchanged(tmp_path):
    config = PresweepConfig(run_id="r", runs_dir=tmp_path, master_csv=tmp_path / "m.csv")
    assert config.pipeline_version == PIPELINE_V25 and config.v27_not_production_ready_opt_in is False
    snap = planning.config_snapshot(config)
    assert "pipeline_version" not in snap and "v27_not_production_ready_opt_in" not in snap
    v27 = planning.config_snapshot(_v27_config(tmp_path))
    assert v27["pipeline_version"] == PIPELINE_V27 and v27["v27_not_production_ready_opt_in"] is True
    # Apart from the two run-mode keys (and the stop_after v2.7 needs), the snapshots agree.
    assert {k: v for k, v in v27.items() if k not in ("pipeline_version", "v27_not_production_ready_opt_in",
                                                      "stop_after", "run_id", "runs_dir", "master_csv")} == \
        {k: v for k, v in snap.items() if k not in ("stop_after", "run_id", "runs_dir", "master_csv")}


def test_v27_without_opt_in_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not production ready"):
        _v27_config(tmp_path, v27_not_production_ready_opt_in=False)


def test_opt_in_on_v25_and_unknown_mode_are_refused(tmp_path):
    with pytest.raises(ValueError, match="only opts in"):
        PresweepConfig(run_id="r", runs_dir=tmp_path, master_csv=tmp_path / "m.csv",
                       v27_not_production_ready_opt_in=True)
    with pytest.raises(ValueError, match="pipeline_version must be one of"):
        PresweepConfig(run_id="r", runs_dir=tmp_path, master_csv=tmp_path / "m.csv", pipeline_version="v2.6")


@pytest.mark.parametrize("stop_after", ["extract"])
def test_v27_refuses_a_v25_only_stop_after(tmp_path, stop_after):
    with pytest.raises(ValueError, match="has no 'extract' stage"):
        _v27_config(tmp_path, stop_after=stop_after)
    assert _v27_config(tmp_path, stop_after="scrape").stop_after == "scrape"


def test_resume_across_run_modes_is_refused(tmp_path):
    run_dir = tmp_path / "run"
    state_dir(run_dir).mkdir(parents=True)
    old = planning.build_manifest(PresweepConfig(run_id="run", runs_dir=tmp_path, master_csv=tmp_path / "m.csv"), [])
    (run_dir / "manifest.json").write_text(json.dumps(old), encoding="utf-8")
    new = planning.build_manifest(_v27_config(tmp_path, run_id="run", runs_dir=tmp_path), [])
    with pytest.raises(RuntimeError, match="config.pipeline_version: 'v2.5' \\(manifest\\) != 'v2.7'"):
        planning._assert_manifest_matches_on_resume(run_dir, new)
    planning._assert_manifest_matches_on_resume(run_dir, old)  # same mode: no diff from the mode


# ---------------------------------------------------------------------------
# Dispatch refusals: no injected calls, no work
# ---------------------------------------------------------------------------


def test_run_presweep_v27_without_injected_calls_is_refused_before_any_work(tmp_path):
    config = _v27_config(tmp_path)
    with pytest.raises(ValueError, match="no default client"):
        orch.run_presweep(config)
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("missing", ["jev_ask_fn", "extract_fn", "entail_fn", "perpage_inputs"])
def test_v27_dispatch_missing_one_call_is_refused_before_any_work(tmp_path, missing):
    config = _v27_config(tmp_path)
    v27 = orch.V27Dispatch(settings=SETTINGS, jev_ask_fn=FakeJev(), extract_fn=lambda j: None,
                           entail_fn=FakeEntail(), perpage_inputs=lambda *a: [])
    with pytest.raises(ValueError, match=f"{missing} must be supplied"):
        orch.run_presweep(config, v27=replace(v27, **{missing: None}))
    with pytest.raises(ValueError, match="explicit RuntimeSettings"):
        orch.run_presweep(config, v27=replace(v27, settings=None))
    assert not (tmp_path / "runs").exists()
    # run_v27_dispatch itself refuses the same way, before binding anything.
    with pytest.raises(ValueError, match=f"{missing} must be supplied"):
        orch.run_v27_dispatch(tmp_path / "x", [], None, replace(v27, **{missing: None}))
    assert not (tmp_path / "x").exists()


def test_v27_inputs_on_a_v25_run_are_refused(tmp_path):
    config = PresweepConfig(run_id="r", runs_dir=tmp_path / "runs", master_csv=tmp_path / "m.csv")
    v27 = orch.V27Dispatch(SETTINGS, FakeJev(), lambda j: None, FakeEntail(), lambda *a: [])
    with pytest.raises(ValueError, match="pipeline_version is 'v2.5'"):
        orch.run_presweep(config, v27=v27)
    assert not (tmp_path / "runs").exists()


# ---------------------------------------------------------------------------
# The dispatch on the mocked e2e world
# ---------------------------------------------------------------------------


def test_v27_dispatch_runs_through_stage6_and_writes_the_outputs(tmp_path):
    run_dir, bound, instrument, world = _world_run(tmp_path)
    extract, entail = FakeExtractorS6(world), FakeEntail()
    inputs = WorldInputs(world)
    out = orch.run_v27_dispatch(run_dir, ["sample"], "scraped", _dispatch(world, extract=extract, entail=entail,
                                                                          inputs=inputs))
    assert out == {"pipeline_version": PIPELINE_V27, "instrument_id": bound.instrument_id,
                   "n_perpage_ready": 3, "n_perpage_held": 0, "n_perpage_failed_pages": 1,
                   "n_stage6_written": 3, "n_stage6_held": 0, "n_stage6_failed": 0, "n_stage6_skipped": 0}
    # The hand-off got the run's sample, scraped pages and the bound instrument.
    assert inputs.calls == [(run_dir, ["sample"], "scraped", bound.instrument_id, bound.instrument_id)]
    for inst in INSTS:
        for name in ("6_validate.json", "6_storage.json", "6_support_provenance.json"):
            assert (institution_dir(run_dir, inst) / name).is_file()
    stages = extract.stages()
    assert {"5_extract_v27", "5b_pass2_support_v27", STAGE6_QUOTE} <= set(stages)
    assert stages.index(STAGE6_QUOTE) > max(i for i, s in enumerate(stages) if s != STAGE6_QUOTE)
    assert all(j.metadata["setup_pointer"] == bound.instrument_id for j in extract.jobs)
    assert entail.calls
    # The run manifest records the run mode and the bound instrument (and the 2.7 storage contract).
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest[planning.RUN_PIPELINE_KEY] == {"pipeline_version": PIPELINE_V27,
                                                   "instrument_id": bound.instrument_id}
    assert manifest["storage_contract"] == {"codebook_release": "2.7"}
    # Stage 7 accepts the outputs as 2.7 storage.
    from g3o.persist.writer import write_run_csvs

    result = write_run_csvs(run_dir, run_id="R-T030-PP", run_model="fake-jev", run_date="2026-11-10")
    assert result["integrity"]["is_valid"]
    with Path(result["outputs"]["activities"]["path"]).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows and all(r["setup_pointer"] == bound.instrument_id for r in rows)

    # A re-run resumes: committed Stage 6 artifacts are skipped, nothing is asked again.
    extract2 = FakeExtractorS6(world)
    again = orch.run_v27_dispatch(run_dir, ["sample"], "scraped", _dispatch(world, extract=extract2))
    assert again["n_stage6_skipped"] == 3 and again["n_stage6_written"] == 0
    assert extract2.jobs == []


def test_v27_dispatch_without_merged_values_holds_that_institution_at_stage6(tmp_path):
    """The merged-activity values have no producer (RC-D-030 X1 a): absent, Stage 6 holds the merging
    institution (MissingUpstreamError is per-institution in Stage 6) and writes the others."""
    run_dir, bound, instrument, world = _world_run(tmp_path)
    out = orch.run_v27_dispatch(run_dir, [], None, _dispatch(world, inputs=WorldInputs(world, merged=False)))
    assert (out["n_stage6_written"], out["n_stage6_failed"]) == (2, 1)
    held = json.loads((institution_dir(run_dir, INSTS[0]) / rt.WORK_DIR / rt.HELD_FILE).read_text(encoding="utf-8"))
    assert "MissingUpstreamError" in held["error"]
    assert not (institution_dir(run_dir, INSTS[0]) / "6_storage.json").exists()


def test_v27_dispatch_stops_at_the_first_x35_check_with_the_real_entry(tmp_path):
    run_dir, bound, instrument, world = _world_run(tmp_path)
    with pytest.raises(SupportGateError):
        orch.run_v27_dispatch(run_dir, [], None, _dispatch(world, entail=support_check.run_entailment))
    assert not any((institution_dir(run_dir, i) / "6_storage.json").exists() for i in INSTS)
    assert not any(r["reason"] == pp.HELD_REASON for r in attrition.read_records(run_dir))


def test_v27_dispatch_stops_on_a_missing_upstream_producer(tmp_path):
    run_dir, bound, instrument, world = _world_run(tmp_path)

    def drop_follow(insts):
        a = insts[0]
        spec = replace(a.pages[0], upstream=replace(a.pages[0].upstream, followed=None))
        return [replace(a, pages=[spec, *a.pages[1:]]), *insts[1:]]
    with pytest.raises(pp.MissingUpstreamError, match="follow"):
        orch.run_v27_dispatch(run_dir, [], None, _dispatch(world, inputs=WorldInputs(world, edit=drop_follow)))
    assert not any((institution_dir(run_dir, i) / "6_storage.json").exists() for i in INSTS)


# ---------------------------------------------------------------------------
# The whole run_presweep path (Stages 1-4 stubbed), no client constructed
# ---------------------------------------------------------------------------


def _write_master(path):
    fields = ["institution_uid", "master_row_id", "country", "government_level", "branch", "institution_type",
              "institution_name", "website", "source_dataset_id", "source_url", "source_file", "retrieval_date",
              "notes"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow({"institution_uid": "G3O-I-00000001", "master_row_id": "1", "country": "Australia",
                    "government_level": "local", "branch": "executive", "institution_type": "council",
                    "institution_name": "Council A", "website": "", "source_dataset_id": "synth", "source_url": "",
                    "source_file": "synth.csv", "retrieval_date": "", "notes": "synth"})
    return path


def _refuse_clients(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("a provider client was constructed")

    from g3o.common import batch_client, jev_client
    from g3o.extract import anthropic_client

    monkeypatch.setattr(anthropic_client.AnthropicExtractorClient, "__init__", refuse)
    monkeypatch.setattr(batch_client, "OpenAI", refuse)
    monkeypatch.setattr(batch_client, "_default_client", refuse)
    monkeypatch.setattr(jev_client, "client_from_credentials", refuse)
    monkeypatch.setattr(jev_client.ts, "TypeSafeClient", refuse)
    for mod, attr in (("anthropic", "Anthropic"), ("anthropic", "AsyncAnthropic"), ("openai", "OpenAI")):
        try:
            monkeypatch.setattr(importlib.import_module(mod), attr, refuse)
        except (ImportError, AttributeError):
            pass


def _stub_stages_1_to_4(monkeypatch, seen):
    def general(run_dir, sample, *a, **kw):
        return {synth_institution_id(r): [] for r in sample}

    monkeypatch.setattr(orch, "_run_discovery_general", general)
    monkeypatch.setattr(orch, "_run_classify_official_site",
                        lambda run_dir, sample, *a, **kw: {synth_institution_id(r): None for r in sample})
    monkeypatch.setattr(orch, "_run_discovery_site_restricted", general)
    monkeypatch.setattr(orch, "_run_filter_eligibility", lambda run_dir, sample, g, s, **kw: (
        g, s, {"mode": "shadow", "n_would_drop": 0, "n_enforced_drop": 0}))
    monkeypatch.setattr(orch, "_run_classify_triage", lambda run_dir, sample, g, s, o, **kw: {k: [] for k in g})

    class Scraped(dict):
        def page_count(self):
            return 0

    def scrape(run_dir, sample, triaged, **kw):
        seen["scraped"] = Scraped()
        return seen["scraped"]

    def v25(*a, **kw):
        raise AssertionError("a v2.5 Stage 5/6 runner was called on a v2.7 run")

    monkeypatch.setattr(orch, "_run_scrape", scrape)
    monkeypatch.setattr(orch, "_run_extract", v25)
    monkeypatch.setattr(orch, "_run_validate", v25)


def test_run_presweep_v27_dispatches_after_scrape_with_no_client(tmp_path, monkeypatch):
    _refuse_clients(monkeypatch)
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)
    seen = {}
    _stub_stages_1_to_4(monkeypatch, seen)
    # The fixture world (its own bound instrument, the same settings) lives in the run directory.
    config = _v27_config(tmp_path, master_csv=_write_master(tmp_path / "master.csv"), sample_size=1,
                         dry_run=False, poll_interval=0, max_wait_per_stage=10,
                         scrape_respect_robots=False, scrape_host_delay_seconds=0)
    run_dir = config.runs_dir / config.run_id
    run_dir2, bound, instrument, world, _ = _world(run_dir.parent, config.run_id)
    assert run_dir2 == run_dir
    inputs = WorldInputs(world)
    summary = orch.run_presweep(
        config, credentials=Credentials(openai_api_key="sk-test", serper_api_key="s", typesafe_api_key="t"),
        v27=_dispatch(world, inputs=inputs))
    assert summary["pipeline_version"] == PIPELINE_V27 and summary["instrument_id"] == bound.instrument_id
    assert summary["n_stage6_written"] == 3 and summary["n_perpage_held"] == 0
    assert "n_extracted" not in summary and "n_consolidated" not in summary
    (_, sample, scraped, _, _), = inputs.calls
    assert scraped is seen["scraped"] and [synth_institution_id(r) for r in sample] == \
        json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["institutions"]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["pipeline_version"] == PIPELINE_V27
    assert manifest["config"]["v27_not_production_ready_opt_in"] is True
    assert manifest[planning.RUN_PIPELINE_KEY]["instrument_id"] == bound.instrument_id
    for inst in INSTS:
        assert (institution_dir(run_dir, inst) / "6_storage.json").is_file()


def test_run_presweep_v25_default_never_reaches_the_v27_dispatch(tmp_path, monkeypatch):
    seen = {}
    _stub_stages_1_to_4(monkeypatch, seen)
    calls = []
    monkeypatch.setattr(orch, "_run_extract", lambda *a, **kw: calls.append("extract") or 0)
    monkeypatch.setattr(orch, "_run_validate", lambda *a, **kw: calls.append("validate") or {})

    def no_v27(*a, **kw):
        raise AssertionError("the v2.7 dispatch ran on a v2.5 run")

    monkeypatch.setattr(orch, "run_v27_dispatch", no_v27)
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)
    config = PresweepConfig(run_id="v25", runs_dir=tmp_path / "runs", master_csv=_write_master(tmp_path / "m.csv"),
                            sample_size=1, dry_run=False, stop_after="validate", poll_interval=0,
                            max_wait_per_stage=10, scrape_respect_robots=False, scrape_host_delay_seconds=0)
    summary = orch.run_presweep(
        config, credentials=Credentials(openai_api_key="sk-test", serper_api_key="s", typesafe_api_key="t"))
    assert calls == ["extract", "validate"] and "pipeline_version" not in summary
    manifest = json.loads((tmp_path / "runs" / "v25" / "manifest.json").read_text(encoding="utf-8"))
    assert planning.RUN_PIPELINE_KEY not in manifest and "storage_contract" not in manifest
    assert "pipeline_version" not in manifest["config"]
