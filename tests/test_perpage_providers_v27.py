"""T-030 per-page provider adapters (``perpage_providers_v27``) on the mocked e2e world.

The providers are built by ``build_perpage_providers`` over a FAKE extractor
(canned T-022 pass-1 / T-032 pass-2 answers, read off the task list in the
built job) and a fake X35 ``true``; no client is constructed. The run is the
``test_e2e_perpage_v27`` world with its activities renamed to the ids the
pass-1 parser assigns (``<page>#a001`` ...), so its explicit upstream values
key on the same activities.
"""
from __future__ import annotations

import importlib
import json

import pytest

from g3o.classify import jev_page_code as jpc
from g3o.common import attrition, support_check
from g3o.common.cost_monitor import BudgetExceededError
from g3o.common.jev_client import JevAccountError
from g3o.common.paths import institution_dir
from g3o.common.support_check import SupportGateError
from g3o.extract.anthropic_client import ExtractorResult
from g3o.extract.request_v27 import field_name
from g3o.run.presweep import perpage_providers_v27 as ppv
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from tests.test_e2e_perpage_v27 import (  # noqa: F401 - _paragraph_layout is an autouse fixture
    ANSWERS,
    CLOCK,
    RELATIONS,
    SETTINGS,
    TRUE,
    FakeJev,
    FakeQuotes,
    _chunks,
    _csvs,
    _fail_verdict,
    _paragraph_layout,
    _setup,
    _storage,
)

PASS1, PASS2 = "5_extract_v27", "5b_pass2_support_v27"
USAGE = {"input_tokens": 100, "output_tokens": 10}
#: pass-2 quotes withheld: (page, activity label, field, part) - the e2e WITHHOLD set
WITHHOLD2 = {("b1", "A1", "activity_type", "b1#p0"), ("b2", "A1", "evaluation_documented", "b2#p0")}


def aid(page_id, n=1):
    return f"{page_id}#a{n:03d}"


def _renamed(world):
    for page in world.pages.values():
        page.activities = [(aid(page.pid, n), *rest) for n, (_, *rest) in enumerate(page.activities, start=1)]


class FakeExtractor:
    """Answers a built job from its task list: each quote task gets its part's text."""

    def __init__(self, world, withhold=WITHHOLD2):
        self.world, self.withhold = world, set(withhold)
        self.jobs = []

    def __call__(self, job):
        self.jobs.append(job)
        user = job.params["messages"][0]["content"]
        tasks = json.loads(user.split("\nTASKS:\n", 1)[1])
        page = self.world.pages[job.metadata["page_id"]]
        parts = {c.chunk_id: c.text for c in _chunks(page.pid, page.text)}
        if job.metadata["stage"] == PASS1:
            payload = {"quotes": [{"task_id": t["task_id"], "part_id": t["part_id"],
                                   "quote": parts[t["part_id"]].strip()} for t in tasks["quote_tasks"]],
                       "links": [], "activities": [], "publication_date": None}
            if tasks["activity_task"] is not None:
                wanted = set(tasks["activity_task"]["fields"])
                for _, name, tool, first, last in page.activities:
                    chunk = next(c for c, text in parts.items() if first in text)
                    fields = [{"field": f, "value": v, "part_id": chunk, "supporting_text": first}
                              for f, v in ((field_name("core.activity_name"), name),
                                           (field_name("core.tool_name"), tool)) if f in wanted]
                    payload["activities"].append({"part_id": chunk, "start_text": first,
                                                  "end_text": last or first, "fields": fields})
        else:
            assert job.metadata["stage"] == PASS2
            payload = {"quotes": [{"task_id": t["task_id"], "part_id": t["part_id"],
                                   "quote": None if (page.pid, t["activity"], t["question"].split("#")[0],
                                                     t["part_id"]) in self.withhold
                                   else parts[t["part_id"]].strip()} for t in tasks["quote_tasks"]],
                       "fields": [{"task_id": t["task_id"], "value": None, "part_id": None, "supporting_text": None}
                                  for t in tasks["field_tasks"]]}
        n = len(self.jobs)
        return ExtractorResult(job.custom_id, True, json.dumps(payload), None, "fake-extractor-response",
                               f"msg-{n}", f"x-{n}", "end_turn", dict(USAGE))

    def stages(self):
        return [j.metadata["stage"] for j in self.jobs]


class FakeEntail:
    def __init__(self):
        self.calls = []

    def __call__(self, question, text):
        self.calls.append((question, text))
        return TRUE


def _world(tmp_path, name="run"):
    run_dir, bound, instrument, world, _ = _setup(tmp_path, name)
    _renamed(world)
    insts = [world.institution(i) for i in ("INST-0000001", "INST-0000002", "INST-0000003")]
    return run_dir, bound, instrument, world, insts


def _providers(run_dir, bound, instrument, extract, entail, **models):
    kw = {"extractor_model": SETTINGS.extractor_model, "x35_model": SETTINGS.x35_model, **models}
    return ppv.build_perpage_providers(bound, instrument, run_dir, extract_fn=extract, entail_fn=entail, **kw)


def _run(run_dir, bound, instrument, insts, providers, jev):
    return pp.run_perpage_v27(run_dir, insts, ask_fn=jev, providers=providers, page_config=bound.page_config,
                              activity_config=bound.activity_config, instrument=instrument)


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


def test_adapters_e2e_to_final_csvs(tmp_path):
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    extract, entail = FakeExtractor(world), FakeEntail()
    jev = FakeJev(ANSWERS, RELATIONS, _fail_verdict)
    ready, metrics = _run(run_dir, bound, instrument, insts, _providers(run_dir, bound, instrument, extract, entail),
                          jev)
    assert metrics.ready == ["INST-0000001", "INST-0000002", "INST-0000003"] and not metrics.held
    assert metrics.failed_pages == ["c2"]

    # Every extractor job is bound to the instrument's settings and setup pointer.
    assert extract.jobs and all(j.params["model"] == SETTINGS.extractor_model
                                and j.metadata["setup_pointer"] == bound.instrument_id for j in extract.jobs)
    assert {j.params["system"] for j in extract.jobs if j.metadata["stage"] == PASS1} == {bound.pass1_system}
    assert {j.params["system"] for j in extract.jobs if j.metadata["stage"] == PASS2} == {bound.pass2_system}
    assert entail.calls  # X35 asked where T-024 needs it
    # Usage telemetry of the injected calls reaches the per-page metrics (through the journal).
    for inst in ("INST-0000001", "INST-0000002", "INST-0000003"):
        u = metrics.usage[inst]
        assert u["extractor_calls"] > 0
        assert u["extractor_input_tokens"] == 100 * u["extractor_calls"]
        assert u["extractor_output_tokens"] == 10 * u["extractor_calls"]
    assert sum(u["extractor_calls"] for u in metrics.usage.values()) == len(extract.jobs)
    assert sum(u["x35_calls"] for u in metrics.usage.values()) == len(entail.calls)

    # A021-16: the withheld pass-2 quote downgrades activity_type and opens model_origin (extra round).
    b_inst = next(i for i in ready if i.institution_id == "INST-0000002")
    b1 = next(o for o in b_inst.observations if o.observation_id == pp.observation_id("b1", aid("b1")))
    values = {o.item_id: o.value for o in b1.final_outcomes.values()}
    assert values["core.activity_type"] == "unknown" and values["core.model_origin"] == "not_documented"
    # A021-15: the withheld evaluation quote closes the evaluation types (set by rule).
    b2 = next(o for o in b_inst.observations if o.observation_id == pp.observation_id("b2", aid("b2")))
    b2_values = {o.item_id: o.value for o in b2.final_outcomes.values()}
    assert b2_values["core.evaluation_documented"] == "not_documented"
    assert b2_values["core.evaluation_type_user_feedback"] == "not_asked"

    # One pass-2 page request carries the pair codes (DP-009); their support finalizes the pair.
    s6m = rt.run_stage6_v27(run_dir, pp_ready_with_merged(ready), ask_fn=jev, quote_fn=FakeQuotes(),
                            config=bound.stage6_config(), instrument=instrument, now=CLOCK,
                            test_only_unbound_quote_fn=True)
    assert s6m.written == ["INST-0000001", "INST-0000002", "INST-0000003"] and not s6m.held
    acts = _storage(run_dir, "INST-0000001")["activities"]
    relations = {(r["lhs_observation_id"], r["rhs_observation_id"]): r for a in acts.values()
                 for r in a["activity_relations"]}
    p3a, p3b = pp.observation_id("p3", aid("p3")), pp.observation_id("p3", aid("p3", 2))
    assert relations[(p3a, p3b)]["relation"] == "governs"
    assert relations[(p3a, p3b)]["relation_scope"] == "within_page"
    p3_pass2 = [j for j in extract.jobs if j.metadata["stage"] == PASS2 and j.metadata["page_id"] == "p3"]
    assert len(p3_pass2) == 1  # no extra round on p3: the page request alone
    result, rows = _csvs(run_dir, insts)
    assert result["integrity"]["is_valid"]


def pp_ready_with_merged(ready):
    """Merged values with no rule computable from the merged row (as in the e2e fixture)."""
    from dataclasses import replace

    st = next(i for i in ready if i.institution_id == "INST-0000001")
    o1, o2 = pp.observation_id("p1", aid("p1")), pp.observation_id("p2", aid("p2"))
    merged = {(o1, o2): {k: v for k, v in st.observation_inputs[o1].row["values"].items()
                         if k in rt.MERGE_INPUT_ITEMS}}
    return [replace(i, merged_values=merged) if i.institution_id == "INST-0000001" else i for i in ready]


def test_adapters_pending_extra_round_holds_then_resume_replays_extractor(tmp_path):
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    b = [i for i in insts if i.institution_id == "INST-0000002"]

    def fail_origin(state, questions, n):
        return RuntimeError("extra round down") if list(questions) == ["core.model_origin"] else None
    extract = FakeExtractor(world)
    ready, metrics = _run(run_dir, bound, instrument, b, _providers(run_dir, bound, instrument, extract, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, fail_origin))
    assert not ready and metrics.held == ["INST-0000002"]
    held = json.loads((institution_dir(run_dir, "INST-0000002") / pp.WORK_DIR / pp.HELD_FILE)
                      .read_text(encoding="utf-8"))
    assert held["held"][0]["stage"] == "activity_rounds"

    # Resume in a new process: page checkpoints hold the page support, so the T-022 page request
    # (its spans) is rebuilt from the T-021 artifact and replayed from the journal, never re-sent.
    extract2 = FakeExtractor(world)
    ready, metrics = _run(run_dir, bound, instrument, b,
                          _providers(run_dir, bound, instrument, extract2, FakeEntail()), FakeJev(ANSWERS, RELATIONS))
    assert [i.institution_id for i in ready] == ["INST-0000002"]
    # model_origin answers not_documented (no quote task): nothing is sent live on resume
    assert extract2.jobs == []
    assert metrics.replayed_requests > 0


# ---------------------------------------------------------------------------
# Binding and refusals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["extractor_model", "x35_model"])
def test_model_mismatch_is_refused(tmp_path, field):
    run_dir, bound, instrument, world, _ = _world(tmp_path)
    with pytest.raises(ValueError, match=field):
        _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail(), **{field: "another-model"})
    with pytest.raises(ValueError, match=field):
        _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail(), **{field: " "})


def test_unbound_or_other_instrument_providers_are_refused_by_the_stage(tmp_path):
    from dataclasses import replace

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    plain = world.providers()  # declares no extractor / X35 model
    with pytest.raises(ValueError, match="not bound"):
        _run(run_dir, bound, instrument, insts[:1], plain, FakeJev(ANSWERS, RELATIONS))
    good = _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail())
    for bad in (replace(good, x35_model="another-model"), replace(good, extractor_model="another-model"),
                replace(good, bound_instrument_id="0" * 64)):
        with pytest.raises(ValueError, match="not bound"):
            _run(run_dir, bound, instrument, insts[:1], bad, FakeJev(ANSWERS, RELATIONS))
    with pytest.raises(ValueError, match="instrument differ"):
        ppv.build_perpage_providers(bound, {**instrument, "instrument_id": "0" * 64}, run_dir,
                                    extract_fn=FakeExtractor(world), entail_fn=FakeEntail(),
                                    extractor_model=SETTINGS.extractor_model, x35_model=SETTINGS.x35_model)
    with pytest.raises(ValueError, match="pass1 prompt"):
        _providers(run_dir, replace(bound, pass1_system=bound.pass1_system + " "), instrument,
                   FakeExtractor(world), FakeEntail())
    with pytest.raises(ValueError, match="must be supplied"):
        _providers(run_dir, bound, instrument, None, FakeEntail())


def test_entailment_refuses_with_no_approved_binding(tmp_path):
    """The only non-fake X35 entry is ``run_entailment``: it still refuses, and that stops the stage."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    providers = _providers(run_dir, bound, instrument, FakeExtractor(world), support_check.run_entailment)
    with pytest.raises(SupportGateError):
        _run(run_dir, bound, instrument, insts[:1], providers, FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not any(r["reason"] == pp.HELD_REASON for r in attrition.read_records(run_dir))
    journal = (institution_dir(run_dir, "INST-0000001") / pp.WORK_DIR / pp.JOURNAL).read_text(encoding="utf-8")
    assert any(json.loads(line)["kind"] == "x35_failed" for line in journal.splitlines())


def test_module_imports_and_builds_without_any_client(tmp_path, monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("a provider client was constructed")

    from g3o.common import batch_client
    from g3o.extract import anthropic_client

    monkeypatch.setattr(anthropic_client.AnthropicExtractorClient, "__init__", refuse)
    monkeypatch.setattr(batch_client, "OpenAI", refuse)
    monkeypatch.setattr(batch_client, "_default_client", refuse)
    for mod, attr in (("anthropic", "Anthropic"), ("anthropic", "AsyncAnthropic"), ("openai", "OpenAI")):
        try:
            monkeypatch.setattr(importlib.import_module(mod), attr, refuse)
        except (ImportError, AttributeError):
            pass
    module = importlib.reload(ppv)
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    providers = module.build_perpage_providers(bound, instrument, run_dir, extract_fn=FakeExtractor(world),
                                               entail_fn=FakeEntail(), extractor_model=SETTINGS.extractor_model,
                                               x35_model=SETTINGS.x35_model)
    ready, _ = _run(run_dir, bound, instrument, [i for i in insts if i.institution_id == "INST-0000002"],
                    providers, FakeJev(ANSWERS, RELATIONS))
    assert [i.institution_id for i in ready] == ["INST-0000002"]
    assert jpc.VERDICT  # the page coder module is loaded, no client involved


def test_extra_round_asks_only_the_new_codes(tmp_path):
    """An RC-D-024 extra round sends a pass-2 request for the newly asked code only."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    b = [i for i in insts if i.institution_id == "INST-0000002"]
    extract = FakeExtractor(world)
    answers = {**ANSWERS, "core.model_origin": "commercial"}
    ready, _ = _run(run_dir, bound, instrument, b, _providers(run_dir, bound, instrument, extract, FakeEntail()),
                    FakeJev(answers, RELATIONS))
    assert [i.institution_id for i in ready] == ["INST-0000002"]
    b1_pass2 = [j for j in extract.jobs if j.metadata["stage"] == PASS2 and j.metadata["page_id"] == "b1"]
    assert len(b1_pass2) == 2  # the page request, then the extra round
    extra = json.loads(b1_pass2[1].params["messages"][0]["content"].split("\nTASKS:\n", 1)[1])
    assert [(t["question"], t["answer"]) for t in extra["quote_tasks"]] == [("model_origin", "commercial")]
    obs = next(o for o in ready[0].observations if o.observation_id == pp.observation_id("b1", aid("b1")))
    assert {o.item_id: o.value for o in obs.final_outcomes.values()}["core.model_origin"] == "commercial"


def _held(run_dir, inst):
    return json.loads((institution_dir(run_dir, inst) / pp.WORK_DIR / pp.HELD_FILE).read_text(encoding="utf-8"))


def _kinds(run_dir, inst):
    journal = (institution_dir(run_dir, inst) / pp.WORK_DIR / pp.JOURNAL).read_text(encoding="utf-8")
    return [json.loads(x)["kind"] for x in journal.splitlines()]


class BadResponse(FakeExtractor):
    """The first ``times`` jobs of ``stage`` on ``page`` get a bad response: unparsable (not JSON),
    outside the answer schema, or failed (``success`` false)."""

    def __init__(self, world, stage, page, kind="not_json", times=1):
        super().__init__(world)
        self.stage, self.page, self.kind, self.left = stage, page, kind, times

    def __call__(self, job):
        if job.metadata["stage"] != self.stage or job.metadata["page_id"] != self.page or not self.left:
            return super().__call__(job)
        self.left -= 1
        self.jobs.append(job)
        if self.kind == "failed":
            return ExtractorResult(job.custom_id, False, None, {"type": "errored"}, usage=dict(USAGE))
        text = "not json {" if self.kind == "not_json" else json.dumps({"unexpected": []})
        return ExtractorResult(job.custom_id, True, text, None, "fake-extractor-response", "msg-bad", "x-bad",
                               "end_turn", dict(USAGE))


def _bad_job(bad, stage, page):
    return next(j for j in bad.jobs if j.metadata["page_id"] == page and j.metadata["stage"] == stage)


@pytest.mark.parametrize(("stage", "page", "inst"), [(PASS1, "p1", "INST-0000001"), (PASS2, "b1", "INST-0000002")])
@pytest.mark.parametrize("kind", ["not_json", "off_schema", "failed"])
def test_bad_extractor_response_holds_that_institution_and_the_stage_goes_on(tmp_path, stage, page, inst, kind):
    """C3 a / QA4 M3: a failed or unparsable pass-1/pass-2 response holds only its institution as
    pending (never published); the later institutions complete."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    bad = BadResponse(world, stage, page, kind)
    ready, metrics = _run(run_dir, bound, instrument, insts,
                          _providers(run_dir, bound, instrument, bad, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    others = [i for i in ("INST-0000001", "INST-0000002", "INST-0000003") if i != inst]
    assert metrics.held == [inst]
    assert [i.institution_id for i in ready] == others == metrics.ready
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["stage"] == pp.EXTRACT_RESPONSE_FAILED and hold["page_id"] == page
    assert hold["pass"] == ("pass1" if stage == PASS1 else "pass2")
    assert hold["custom_id"] == _bad_job(bad, stage, page).custom_id
    assert ("ExtractContractError" in hold["error"]) == (kind != "failed")
    assert any(r["institution_id"] == inst and r["reason"] == pp.HELD_REASON
               and r["detail"] == f"{page}:{pp.EXTRACT_RESPONSE_FAILED}" for r in attrition.read_records(run_dir))
    kinds = _kinds(run_dir, inst)
    if kind == "failed":
        assert kinds.count("extract_failed") == 1 and "extract_rejected" not in kinds
    else:  # recorded, then rejected: kept for accounting only, never replayed as final
        assert kinds.count("extract_rejected") == 1 and "extract_failed" not in kinds
    # every extractor call counted once: a rejection entry cancels its recorded entry, never adds a call
    assert metrics.usage[inst]["extractor_calls"] == kinds.count("extract") + kinds.count("extract_failed")


@pytest.mark.parametrize(("stage", "page", "inst"), [(PASS1, "p1", "INST-0000001"), (PASS2, "b1", "INST-0000002")])
@pytest.mark.parametrize("kind", ["not_json", "failed"])
def test_bad_extractor_response_is_asked_again_on_the_next_run(tmp_path, stage, page, inst, kind):
    """The held institution's bad request is asked again live on resume (not replayed) and, with a
    good response, the institution completes and its hold is released."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    one = [i for i in insts if i.institution_id == inst]
    bad = BadResponse(world, stage, page, kind)
    ready, metrics = _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, bad, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not ready and metrics.held == [inst]
    failed_job = _bad_job(bad, stage, page)

    extract = FakeExtractor(world)
    ready, metrics = _run(run_dir, bound, instrument, one,
                          _providers(run_dir, bound, instrument, extract, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert [i.institution_id for i in ready] == [inst] and not metrics.held
    assert any(j.params == failed_job.params for j in extract.jobs)  # asked again, live
    assert not (institution_dir(run_dir, inst) / pp.WORK_DIR / pp.HELD_FILE).exists()
    assert any(r["institution_id"] == inst and r["reason"] == pp.HELD_RELEASED
               for r in attrition.read_records(run_dir))
    assert metrics.usage[inst]["extractor_calls"] == len(bad.jobs) + len(extract.jobs)

    # A third run replays the good responses only: nothing is sent live.
    again = FakeExtractor(world)
    ready, _ = _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, again, FakeEntail()),
                    FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert [i.institution_id for i in ready] == [inst] and again.jobs == []


def test_rejected_response_is_not_replayed_by_a_reloaded_journal(tmp_path):
    """``reject_extract`` cancels the recorded entry for every later load; a new response to the same
    request is replayed after it."""
    from g3o.extract.anthropic_client import ExtractorJob

    path = tmp_path / "journal.jsonl"
    job = ExtractorJob("cid-1", {"model": "m", "messages": []}, {})
    prompt = {"extractor_model": "m"}
    answers = iter([ExtractorResult("cid-1", True, "bad", None, usage=dict(USAGE)),
                    ExtractorResult("cid-1", True, "good", None, usage=dict(USAGE))])
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(prompt)
    assert wrap(lambda j: next(answers))(job).text == "bad"
    request = {"custom_id": job.custom_id, "params": job.params}
    assert journal.reject_extract(request, prompt, "ExtractContractError: answer is not JSON")
    assert not journal.reject_extract(request, prompt, "twice")  # nothing recorded is left to reject
    reloaded = rt.RequestJournal(path, {"s": 1})
    wrap2, _ = reloaded.seams(prompt)
    assert wrap2(lambda j: next(answers))(job).text == "good" and reloaded.live == 1
    third = rt.RequestJournal(path, {"s": 1})
    wrap3, _ = third.seams(prompt)
    assert wrap3(lambda j: pytest.fail("asked again"))(job).text == "good" and third.replayed == 1
    assert third.usage()["extractor_calls"] == 2 and third.usage()["extractor_input_tokens"] == 200


@pytest.mark.parametrize("error", [JevAccountError("account stopped"), BudgetExceededError(2.0, 1.0, "perpage_v27"),
                                   pp.MissingUpstreamError("simulated absent producer", ["p1"]),
                                   RuntimeError("client connection reset")])
def test_extractor_call_errors_still_stop_the_stage(tmp_path, error):
    """A stage stop raised by the call (or any exception it raises: not a response) still stops."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)

    class Raising(FakeExtractor):
        def __call__(self, job):
            raise error
    with pytest.raises(type(error)):
        _run(run_dir, bound, instrument, insts, _providers(run_dir, bound, instrument, Raising(world), FakeEntail()),
             FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not any(r["reason"] == pp.HELD_REASON for r in attrition.read_records(run_dir))


def test_missing_upstream_after_a_response_hold_still_stops_the_stage(tmp_path, monkeypatch):
    """RC-D-033 C2 a is unchanged: a held bad response does not turn a later wiring gap into a hold."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    real = pp.produce_page

    def missing(**kw):
        if kw["spec"].page.institution_id == "INST-0000002":
            raise pp.MissingUpstreamError("simulated absent producer", [kw["spec"].page.page_id])
        return real(**kw)
    monkeypatch.setattr(pp, "produce_page", missing)
    with pytest.raises(pp.MissingUpstreamError, match="simulated absent"):
        _run(run_dir, bound, instrument, insts,
             _providers(run_dir, bound, instrument, BadResponse(world, PASS1, "p1"), FakeEntail()),
             FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert _held(run_dir, "INST-0000001")["held"][0]["stage"] == pp.EXTRACT_RESPONSE_FAILED


def test_response_failure_is_not_a_stage_stop():
    assert not issubclass(pp.ExtractorResponseFailed, pp.STAGE_STOPS)
    assert not issubclass(pp.ExtractorResponseFailed, (ValueError, RuntimeError))


# ---------------------------------------------------------------------------
# PI-approved pass-1 / pass-2 system prompts (RC-D-021 P-1 a, P-2 a)
# ---------------------------------------------------------------------------


def test_approved_pass_prompts_hash_to_their_pins_and_are_accepted(tmp_path):
    from g3o.common.instrument import sha256_text
    from g3o.extract import pass2_support, request_v27

    assert sha256_text(request_v27.build_system_prompt()) == ppv.PASS1_SYSTEM_SHA256
    assert sha256_text(pass2_support.build_system_prompt()) == ppv.PASS2_SYSTEM_SHA256
    ppv.require_approved_system("pass1", request_v27.build_system_prompt())
    ppv.require_approved_system("pass2", pass2_support.build_system_prompt())
    run_dir, bound, instrument, world, _ = _world(tmp_path)
    assert (sha256_text(bound.pass1_system), sha256_text(bound.pass2_system)) == (
        ppv.PASS1_SYSTEM_SHA256, ppv.PASS2_SYSTEM_SHA256)
    assert _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()) is not None


@pytest.mark.parametrize("name", ["pass1", "pass2"])
def test_altered_pass_prompt_is_refused_even_when_the_instrument_pins_it(tmp_path, name):
    from dataclasses import replace

    from g3o.common.instrument import sha256_text

    run_dir, bound, instrument, world, _ = _world(tmp_path)
    field = f"{name}_system"
    altered = getattr(bound, field).replace("the", "a", 1)
    assert altered != getattr(bound, field)
    with pytest.raises(ValueError, match="PI-approved"):
        ppv.require_approved_system(name, altered)
    # An instrument built over the altered text would pass its own prompt_hashes check.
    payload = {**instrument["payload"],
               "prompt_hashes": {**instrument["payload"]["prompt_hashes"], name: sha256_text(altered)}}
    extract = FakeExtractor(world)
    with pytest.raises(ValueError, match=f"{name} prompt differs from the PI-approved text"):
        _providers(run_dir, replace(bound, **{field: altered}), {**instrument, "payload": payload},
                   extract, FakeEntail())
    assert not extract.jobs
