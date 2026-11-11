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
    write_manifest(run_dir, {"run_id": "R-T030-PP", "institutions": list(INSTS),
                             "config": {"pipeline_version": PIPELINE_V27}})
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


@pytest.mark.parametrize("setting", [{"budget_usd": 5.0}, {"budget_usd": 5.0, "projection_safety_factor": 1.5},
                                     {"preflight_estimate_usd": 2.0}, {"cost_monitor_dry_run": True},
                                     {"preflight_stage_estimates": {"classify_official_site": 1.0,
                                                                    "classify_triage": 1.0}}])
def test_v27_keeps_the_stage_1_to_4_budget_settings(tmp_path, setting):
    """PI ruling 1 a (2026-11-11): budget settings acting on Stages 1-4 stay valid on v2.7."""
    config = _v27_config(tmp_path, **setting)
    for name, value in setting.items():
        assert getattr(config, name) == value


@pytest.mark.parametrize("stage", ["extract", "validate", orch.V27_PERPAGE_SPAN, orch.V27_STAGE6_SPAN])
def test_v27_refuses_a_stage_estimate_outside_stages_1_to_4(tmp_path, stage):
    """Ruling 1 a: only the v2.7-stage budget figures are refused, until v2.7 stage pricing exists."""
    setting = {"preflight_stage_estimates": {"classify_triage": 1.0, stage: 1.0}}
    with pytest.raises(ValueError, match="v2.7 has no stage pricing yet") as err:
        _v27_config(tmp_path, **setting)
    assert f"preflight_stage_estimates for {stage}:" in str(err.value) and "RC-D-021" in str(err.value)
    # The same estimates stay valid on v2.5.
    PresweepConfig(run_id="r", runs_dir=tmp_path, master_csv=tmp_path / "m.csv", **setting)


def test_run_presweep_rechecks_stage_estimates_set_after_construction(tmp_path):
    config = _v27_config(tmp_path, budget_usd=5.0)
    config.preflight_estimate_usd = 3.0  # as the CLI sets it, after construction: still valid
    config.preflight_stage_estimates = {"classify_triage": 1.0, "extract": 2.0}
    with pytest.raises(ValueError, match="v2.7 has no stage pricing yet"):
        orch.run_presweep(config, v27=orch.V27Dispatch(SETTINGS, FakeJev(), lambda j: None, FakeEntail(),
                                                   lambda *a: []))
    assert not (tmp_path / "runs").exists()


def test_v27_preflight_prices_stages_2_and_3_only(tmp_path):
    """Ruling 1 a: the v2.7 preflight (and the ceiling compared with it) covers Stages 1-4; its stage
    estimates are exactly the ones the v2.7 config accepts, so the CLI can thread them in."""
    from g3o.run.preflight import run_preflight

    master = _write_master(tmp_path / "master.csv")
    creds = Credentials(openai_api_key="sk-test", serper_api_key="s", typesafe_api_key="t")
    v25 = run_preflight(PresweepConfig(run_id="r", runs_dir=tmp_path / "runs", master_csv=master, sample_size=1),
                        cost_ceiling_usd=10.0, credentials=creds)
    v27 = run_preflight(_v27_config(tmp_path, master_csv=master, sample_size=1, budget_usd=10.0),
                        cost_ceiling_usd=10.0, credentials=creds)
    p25, p27 = v25["cost_preview"], v27["cost_preview"]
    assert set(p27["stage_estimates"]) == {"classify_official_site", "classify_triage"}
    assert {k: p27["stage_estimates"][k] for k in p27["stage_estimates"]} ==         {k: p25["stage_estimates"][k] for k in p27["stage_estimates"]}
    assert p27["v27_unpriced_stages"] == [orch.V27_PERPAGE_SPAN, orch.V27_STAGE6_SPAN]
    assert "v27_unpriced_stages" not in p25 and "ruling 1 a" not in p25["note"]
    assert p27["est_total_usd"] < p25["est_total_usd"] and p27["est_input_tokens"] < p25["est_input_tokens"]
    assert p27["est_by_api"]["serper"] == p25["est_by_api"]["serper"]
    assert v27["cost_ceiling_exceeded"] is False
    # What the CLI threads into the config after the preflight is accepted.
    config = _v27_config(tmp_path, budget_usd=10.0)
    config.preflight_estimate_usd = p27["est_total_usd"]
    config.preflight_stage_estimates = p27["stage_estimates"]
    from g3o.run.presweep.config import refuse_v27_budget_settings
    refuse_v27_budget_settings(config)


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


def _stub_dispatch(**overrides):
    fields = dict(settings=SETTINGS, jev_ask_fn=FakeJev(), extract_fn=lambda j: None, entail_fn=FakeEntail(),
                  perpage_inputs=lambda *a: [])
    fields.update(overrides)
    return orch.V27Dispatch(**fields)


def _no_planning(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("planning ran before the v2.7 refusal")

    monkeypatch.setattr(orch, "plan_run", refuse)


def test_the_refusing_x35_entry_is_refused_before_the_run_dir_exists(tmp_path, monkeypatch):
    """QA4 M2 a: support_check.run_entailment refuses every real call, so a run naming it is
    refused on entry, before planning and before any Stage 1-4 spend."""
    _no_planning(monkeypatch)
    v27 = _stub_dispatch(entail_fn=support_check.run_entailment)
    with pytest.raises(ValueError, match="no approved X35 binding exists"):
        orch.run_presweep(_v27_config(tmp_path), v27=v27)
    assert not (tmp_path / "runs").exists()
    with pytest.raises(ValueError, match="no approved X35 binding exists"):
        orch.run_v27_dispatch(tmp_path / "x", [], None, v27)
    assert not (tmp_path / "x").exists()


@pytest.mark.parametrize("pin", ["pass1", "pass2"])
def test_a_prompt_pin_mismatch_is_refused_before_planning(tmp_path, monkeypatch, pin):
    """QA4 M2 b: the P-1/P-2 prompt pins are checked before any planning."""
    from g3o.run.presweep import perpage_providers_v27 as ppv

    _no_planning(monkeypatch)
    row = ppv._APPROVED[pin][0]
    monkeypatch.setitem(ppv._APPROVED, pin, (row, "0" * 64))
    with pytest.raises(ValueError, match=f"{pin} prompt differs from the PI-approved text .RC-D-021 {row}"):
        orch.run_presweep(_v27_config(tmp_path), v27=_stub_dispatch())
    assert not (tmp_path / "runs").exists()


def test_runtime_pins_and_models_are_refused_before_planning(tmp_path, monkeypatch):
    """QA4 M2 b: bind_runtime's codebook SHA / matcher pin checks (its non-writing half) and the
    Stage 6 quote step's X35 model check run before planning."""
    from g3o.run.presweep import instrument_binding as binding

    _no_planning(monkeypatch)
    with monkeypatch.context() as m:
        m.setattr(binding, "CODEBOOK_SHA256", "0" * 64)
        with pytest.raises(ValueError, match="signed r15"):
            orch.run_presweep(_v27_config(tmp_path), v27=_stub_dispatch())
    with monkeypatch.context() as m:
        m.setattr(binding, "version", lambda _: "0.0")
        with pytest.raises(ValueError, match="RapidFuzz"):
            orch.run_presweep(_v27_config(tmp_path), v27=_stub_dispatch())
    with monkeypatch.context() as m:
        m.setattr(binding.BoundRuntime, "stage6_quote_fn", lambda self, *a, **k: (_ for _ in ()).throw(
            ValueError("x35_model differs from the X35 model pinned in the instrument")))
        with pytest.raises(ValueError, match="x35_model differs"):
            orch.run_presweep(_v27_config(tmp_path), v27=_stub_dispatch())
    assert not (tmp_path / "runs").exists()


def test_a_refusal_at_provider_build_leaves_no_run_pipeline_block(tmp_path, monkeypatch):
    """QA4 M2 c: run_pipeline (and the 2.7 storage_contract) are recorded only after the per-page
    providers are built, so a run refused there leaves its manifest without them."""
    from g3o.run.presweep import perpage_providers_v27 as ppv

    run_dir, bound, instrument, world = _world_run(tmp_path)

    def refuse(*_a, **_k):
        raise ValueError("refused at provider build")

    monkeypatch.setattr(ppv, "build_perpage_providers", refuse)
    with pytest.raises(ValueError, match="refused at provider build"):
        orch.run_v27_dispatch(run_dir, [], None, _dispatch(world))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert planning.RUN_PIPELINE_KEY not in manifest and "storage_contract" not in manifest


@pytest.mark.parametrize("config", [{}, {"config": {}}, {"config": {"pipeline_version": PIPELINE_V25}}])
def test_record_run_pipeline_is_refused_on_a_v25_run_directory(tmp_path, config):
    """QA4 L2: a direct call on a run directory whose manifest config is not v2.7 is refused and
    leaves the manifest as it was."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_manifest(run_dir, {"run_id": "r", "institutions": [], **config})
    before = (run_dir / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="recorded only on a v2.7 run"):
        planning.record_run_pipeline(run_dir, pipeline_version=PIPELINE_V27, instrument_id="0" * 64)
    assert (run_dir / "manifest.json").read_bytes() == before


def test_record_run_pipeline_is_refused_for_another_mode_on_a_v27_run(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_manifest(run_dir, {"run_id": "r", "institutions": [], "config": {"pipeline_version": PIPELINE_V27}})
    with pytest.raises(ValueError, match="recorded only on a v2.7 run"):
        planning.record_run_pipeline(run_dir, pipeline_version=PIPELINE_V25, instrument_id="0" * 64)
    block = planning.record_run_pipeline(run_dir, pipeline_version=PIPELINE_V27, instrument_id="0" * 64)
    assert block == {"pipeline_version": PIPELINE_V27, "instrument_id": "0" * 64}


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
    usage = out.pop(orch.V27_USAGE_KEY)
    assert out == {"pipeline_version": PIPELINE_V27, "instrument_id": bound.instrument_id,
                   "n_perpage_ready": 3, "n_perpage_held": 0, "n_perpage_failed_pages": 1,
                   "n_stage6_written": 3, "n_stage6_held": 0, "n_stage6_failed": 0, "n_stage6_skipped": 0}
    # Raw usage of both v2.7 stages (QA4 M1): summed journal totals, no prices.
    assert set(usage) == {orch.V27_PERPAGE_SPAN, orch.V27_STAGE6_SPAN}
    perpage, stage6 = usage[orch.V27_PERPAGE_SPAN], usage[orch.V27_STAGE6_SPAN]
    assert perpage["n_institutions"] == 3 and stage6["n_institutions"] == 3
    assert perpage["jev_responses"] > 0 and perpage["input_tokens"] > 0
    n_s6_quote = sum(1 for j in extract.jobs if j.metadata["stage"] == STAGE6_QUOTE)
    assert perpage["extractor_calls"] == len(extract.jobs) - n_s6_quote
    assert perpage["extractor_input_tokens"] == 100 * perpage["extractor_calls"]
    assert stage6["quote_responses"] > 0 and stage6["jev_responses"] > 0
    assert perpage["x35_calls"] + stage6["x35_calls"] == len(entail.calls)
    assert not any("usd" in key for stage in usage.values() for key in stage)
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


def test_v27_dispatch_stops_at_the_first_x35_check_on_a_refusing_entry(tmp_path):
    """The bare support_check.run_entailment is refused on entry (QA4 M2 a); a callable that passes
    through to it still refuses at the stage, and that stage stop propagates unchanged."""
    run_dir, bound, instrument, world = _world_run(tmp_path)

    def through(*a, **k):
        return support_check.run_entailment(*a, **k)

    with pytest.raises(SupportGateError):
        orch.run_v27_dispatch(run_dir, [], None, _dispatch(world, entail=through))
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
    # QA4 M1: the v2.7 stages' raw usage reaches the summary and the persisted cost report,
    # unpriced and outside total_usd.
    usage = summary[orch.V27_USAGE_KEY]
    assert set(usage) == {orch.V27_PERPAGE_SPAN, orch.V27_STAGE6_SPAN}
    assert usage[orch.V27_PERPAGE_SPAN]["input_tokens"] > 0
    report = json.loads((run_dir / "_cost_report.json").read_text(encoding="utf-8"))
    assert report[orch.V27_USAGE_KEY] == usage and summary["_cost_report"][orch.V27_USAGE_KEY] == usage
    assert report["budget_usd"] is None and report["total_prompt_tokens"] == 0
    assert {s["stage"] for s in report["stages"]}.isdisjoint({orch.V27_PERPAGE_SPAN, orch.V27_STAGE6_SPAN})
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
    report = json.loads((tmp_path / "runs" / "v25" / "_cost_report.json").read_text(encoding="utf-8"))
    assert orch.V27_USAGE_KEY not in report and orch.V27_USAGE_KEY not in summary


def _stub_priced_stages_done(monkeypatch):
    """The stubbed Stages 2 and 3 write the zero-usage ``.done`` marker a real no-batch stage writes, so
    the cost monitor reads $0 for them rather than a missing record (which it treats as over budget)."""
    from g3o.common.run_state import mark_done

    for name in ("_run_classify_official_site", "_run_classify_triage"):
        stub, stage = getattr(orch, name), name.removeprefix("_run_")

        def done(run_dir, *a, _stub=stub, _stage=stage, **kw):
            out = _stub(run_dir, *a, **kw)
            mark_done(run_dir, _stage, no_batch=True)
            return out

        monkeypatch.setattr(orch, name, done)


def _v27_presweep_config(tmp_path, **kw):
    return _v27_config(tmp_path, master_csv=_write_master(tmp_path / "master.csv"), sample_size=1,
                       dry_run=False, poll_interval=0, max_wait_per_stage=10,
                       scrape_respect_robots=False, scrape_host_delay_seconds=0, **kw)


def test_run_presweep_v27_enforces_the_budget_on_stages_1_to_4(tmp_path, monkeypatch):
    """Ruling 1 a: budget_usd still aborts a v2.7 run on Stage 1-4 spend, before any v2.7 stage."""
    from g3o.common import spend_meter
    from g3o.common.cost_monitor import BudgetExceededError

    _refuse_clients(monkeypatch)
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)
    seen = {}
    _stub_stages_1_to_4(monkeypatch, seen)
    _stub_priced_stages_done(monkeypatch)
    stub_scrape = orch._run_scrape

    def costly_scrape(*a, **kw):
        spend_meter.record(spend_meter.UNLOCKER, billable_bytes=1_000_000_000, success=True)  # $8
        return stub_scrape(*a, **kw)

    monkeypatch.setattr(orch, "_run_scrape", costly_scrape)
    config = _v27_presweep_config(tmp_path, budget_usd=1.0)
    run_dir = config.runs_dir / config.run_id
    _, _, _, world, _ = _world(run_dir.parent, config.run_id)
    inputs = WorldInputs(world)
    with pytest.raises(BudgetExceededError) as exc:
        orch.run_presweep(
            config, credentials=Credentials(openai_api_key="sk-test", serper_api_key="s", typesafe_api_key="t"),
            v27=_dispatch(world, inputs=inputs))
    assert exc.value.stage == "scrape"  # the metered Unlocker spend, not a missing stage record
    assert inputs.calls == []  # no v2.7 stage ran
    report = json.loads((run_dir / "_cost_report.json").read_text(encoding="utf-8"))
    assert report["data_missing_stages"] == []
    assert report["budget_usd"] == 1.0 and report["budget_exceeded"] is True
    assert report[orch.V27_BUDGET_SCOPE_KEY] == orch.V27_BUDGET_SCOPE and report[orch.V27_USAGE_KEY] is None
    assert not any((institution_dir(run_dir, i) / "6_storage.json").exists() for i in INSTS)


def test_run_presweep_v27_budget_leaves_the_unpriced_v27_stages_outside_it(tmp_path, monkeypatch, caplog):
    _refuse_clients(monkeypatch)
    monkeypatch.setattr(serper_client, "_live_mode", False, raising=False)
    _stub_stages_1_to_4(monkeypatch, {})
    _stub_priced_stages_done(monkeypatch)
    config = _v27_presweep_config(tmp_path, budget_usd=5.0)
    run_dir = config.runs_dir / config.run_id
    _, _, _, world, _ = _world(run_dir.parent, config.run_id)
    with caplog.at_level("WARNING"):
        summary = orch.run_presweep(
            config, credentials=Credentials(openai_api_key="sk-test", serper_api_key="s", typesafe_api_key="t"),
            v27=_dispatch(world, inputs=WorldInputs(world)))
    assert summary["n_stage6_written"] == 3
    assert any("enforced on Stages 1-4 only" in r.getMessage() for r in caplog.records)
    report = json.loads((run_dir / "_cost_report.json").read_text(encoding="utf-8"))
    assert report["budget_usd"] == 5.0 and report["budget_exceeded"] is False
    assert report["data_missing_stages"] == []
    assert report[orch.V27_BUDGET_SCOPE_KEY] == orch.V27_BUDGET_SCOPE
    assert report[orch.V27_USAGE_KEY][orch.V27_PERPAGE_SPAN]["input_tokens"] > 0  # used, and not in total_usd
