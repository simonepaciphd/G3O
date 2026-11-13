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
from dataclasses import replace

import pytest

from g3o.classify import jev_page_code as jpc
from g3o.common import attrition, support_check
from g3o.common.cost_monitor import BudgetExceededError
from g3o.common.jev_client import JevAccountError
from g3o.common.part_combine import NOT_COVERED
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
    # ruling 49 a: the pass-2 extra round has its own custom_id; the first round's is the page's
    from g3o.extract.anthropic_client import make_custom_id

    page = world.pages["b1"].input
    page_cid = make_custom_id(page.institution_id, page.url, prefix="x27s")
    first, second = b1_pass2
    assert first.custom_id == page_cid
    assert second.custom_id != page_cid and second.custom_id.startswith(page_cid + ppv.EXTRA_ROUND_MARK)
    assert len(second.custom_id) <= 64 and first.params != second.params
    # deterministic: the same run in another folder builds the same two ids
    run2, bound2, instrument2, world2, insts2 = _world(tmp_path, "run2")
    extract2 = FakeExtractor(world2)
    _run(run2, bound2, instrument2, [i for i in insts2 if i.institution_id == "INST-0000002"],
         _providers(run2, bound2, instrument2, extract2, FakeEntail()), FakeJev(answers, RELATIONS))
    assert [j.custom_id for j in extract2.jobs if j.metadata["stage"] == PASS2 and j.metadata["page_id"] == "b1"] \
        == [first.custom_id, second.custom_id]


def test_pass2_extra_round_custom_id_is_order_free_and_set_bound():
    """Ruling 49 a: the suffix hashes the round's code set (activity included), not its order."""
    from types import SimpleNamespace as NS

    def code(item, value, part=None, linked=None):
        return NS(item_id=item, part=part, chunk_id="b1#p0", value=value, linked_activity=linked)

    a1 = NS(activity_id="b1#a001", codes=(code("core.model_origin", "commercial"), code("core.tool_type", "x", "p")))
    a2 = NS(activity_id="b1#a002", codes=(code("core.model_origin", "commercial"),))
    cid = ppv.pass2_extra_round_custom_id("x27s-" + "0" * 48, NS(activities=(a1, a2)))
    rev = NS(activities=(NS(activity_id=a2.activity_id, codes=a2.codes),
                         NS(activity_id=a1.activity_id, codes=a1.codes[::-1])))
    assert ppv.pass2_extra_round_custom_id("x27s-" + "0" * 48, rev) == cid
    assert ppv.pass2_extra_round_custom_id("x27s-" + "0" * 48, NS(activities=(a1,))) != cid
    moved = NS(activities=(NS(activity_id="b1#a003", codes=a1.codes), a2))
    assert ppv.pass2_extra_round_custom_id("x27s-" + "0" * 48, moved) != cid  # activity-bound
    assert cid.startswith("x27s-" + "0" * 48 + ppv.EXTRA_ROUND_MARK) and len(cid) == 63


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


def _assert_not_archived(run_dir, insts, inst, page, hold):
    """A C3 hold leaves the page's saved state in place: no archive folder, no pending marker, no
    ``archived`` (or archive-failure) entry in the hold."""
    spec = next(s for i in insts if i.institution_id == inst for s in i.pages if s.page.page_id == page)
    pdir = pp._page_dir(run_dir, spec.page)
    assert not (pdir / pp.PAGE_ARCHIVE_DIR).exists() and not (pdir / pp.PAGE_ARCHIVE_PENDING).exists()
    assert "archived" not in hold and "archive_error" not in hold


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
    _assert_not_archived(run_dir, insts, inst, page, hold)  # ruling 33 a is for C4 holds only


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


class WrongShape(FakeExtractor):
    """The first pass job of ``stage`` on ``page`` answers one array field with ``5`` (ruling 30 a):
    a top-level field, or ``activity fields`` (every activity's ``fields``)."""

    def __init__(self, world, stage, page, where):
        super().__init__(world)
        self.stage, self.page, self.where, self.left = stage, page, where, 1

    def __call__(self, job):
        result = super().__call__(job)
        if job.metadata["stage"] != self.stage or job.metadata["page_id"] != self.page or not self.left:
            return result
        self.left -= 1
        payload = json.loads(result.text)
        if self.where == "activity fields":
            assert payload["activities"]
            for act in payload["activities"]:
                act["fields"] = 5
        else:
            payload[self.where] = 5
        return replace(result, text=json.dumps(payload))


@pytest.mark.parametrize(("stage", "where"), [(PASS1, "quotes"), (PASS1, "links"), (PASS1, "activities"),
                                              (PASS1, "activity fields"), (PASS2, "quotes"), (PASS2, "fields")])
def test_wrong_shape_array_field_holds_that_institution(tmp_path, stage, where):
    """Ruling 30 a: an array field of the wrong shape (``"quotes": 5``) is an ExtractContractError, so
    the institution is held under C3 a (never a TypeError stage stop); the others complete."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst, page = "INST-0000002", "b1"
    bad = WrongShape(world, stage, page, where)
    ready, metrics = _run(run_dir, bound, instrument, insts, _providers(run_dir, bound, instrument, bad, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert metrics.held == [inst]
    assert [i.institution_id for i in ready] == ["INST-0000001", "INST-0000003"] == metrics.ready
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["stage"] == pp.EXTRACT_RESPONSE_FAILED and hold["page_id"] == page
    assert hold["pass"] == ("pass1" if stage == PASS1 else "pass2")
    assert hold["custom_id"] == _bad_job(bad, stage, page).custom_id
    assert "ExtractContractError" in hold["error"] and "must be an array" in hold["error"]
    assert _kinds(run_dir, inst).count("extract_rejected") == 1
    _assert_not_archived(run_dir, insts, inst, page, hold)  # a C3 hold: the page state is not archived


def test_response_failure_is_not_a_stage_stop():
    assert not issubclass(pp.ExtractorResponseFailed, pp.STAGE_STOPS)
    assert not issubclass(pp.ExtractorResponseFailed, (ValueError, RuntimeError))


# ---------------------------------------------------------------------------
# C4 a: a pass-1 activity with no activity_name, where an activity-form X35 question needs it
# ---------------------------------------------------------------------------


class NamelessActivity(FakeExtractor):
    """The first ``times`` pass-1 jobs on ``page`` give its activities no ``activity_name``: the field
    left out (``absent``), null, or whitespace only (the parser records both as an empty result)."""

    def __init__(self, world, page, kind="absent", times=1):
        super().__init__(world)
        self.page, self.kind, self.left = page, kind, times

    def __call__(self, job):
        result = super().__call__(job)
        if job.metadata["stage"] != PASS1 or job.metadata["page_id"] != self.page or not self.left:
            return result
        self.left -= 1
        payload = json.loads(result.text)
        name = field_name("core.activity_name")
        for act in payload["activities"]:
            if self.kind == "absent":
                act["fields"] = [f for f in act["fields"] if f["field"] != name]
            else:
                for f in act["fields"]:
                    if f["field"] == name:
                        f["value"] = None if self.kind == "null" else "   "
        return replace(result, text=json.dumps(payload))


def _activity_form(questions):
    """X35 questions in the activity form (the page form never names an activity)."""
    rules = support_check.default_rules()
    before = rules.entailment_activity_form.split("<activity name>", 1)[0].rsplit(">", 1)[-1]
    assert before and before not in rules.entailment_page_form
    return [q for q in questions if before in q]


@pytest.mark.parametrize("kind", ["absent", "null", "blank"])
def test_nameless_activity_holds_that_institution_and_the_stage_goes_on(tmp_path, kind):
    """C4 a: an activity-form X35 question for an activity pass 1 gave no name holds that
    institution as pending (the hold names the page's pass-1 request); the others complete."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst, page = "INST-0000002", "b1"
    extract, entail = NamelessActivity(world, page, kind), FakeEntail()
    ready, metrics = _run(run_dir, bound, instrument, insts, _providers(run_dir, bound, instrument, extract, entail),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert metrics.held == [inst]
    assert [i.institution_id for i in ready] == ["INST-0000001", "INST-0000003"] == metrics.ready
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["stage"] == pp.EXTRACT_RESPONSE_FAILED and hold["page_id"] == page and hold["pass"] == "pass1"
    assert hold["custom_id"] == _bad_job(extract, PASS1, page).custom_id
    assert "activity_name" in hold["error"] and "C4 a" in hold["error"]
    assert any(r["institution_id"] == inst and r["reason"] == pp.HELD_REASON
               and r["detail"] == f"{page}:{pp.EXTRACT_RESPONSE_FAILED}" for r in attrition.read_records(run_dir))
    kinds = _kinds(run_dir, inst)
    assert kinds.count("extract_rejected") == 1 and "extract_failed" not in kinds
    assert metrics.usage[inst]["extractor_calls"] == kinds.count("extract")
    # page-form X35 questions (no name needed) still ran; none was asked with an empty name
    questions = [q for q, _ in entail.calls]
    assert len(_activity_form(questions)) < len(questions)
    assert not any("  " in q for q in _activity_form(questions))


def test_nameless_activity_is_asked_again_on_the_next_run(tmp_path):
    """The held institution's pass-1 request is asked again live (its nameless response is rejected,
    never replayed); with a named activity it completes, and a third run replays only."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst, page = "INST-0000002", "b1"
    one = [i for i in insts if i.institution_id == inst]
    bad = NamelessActivity(world, page)
    ready, metrics = _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, bad, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not ready and metrics.held == [inst]
    failed_job = _bad_job(bad, PASS1, page)

    extract, entail = FakeExtractor(world), FakeEntail()
    ready, metrics = _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, extract, entail),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert [i.institution_id for i in ready] == [inst] and not metrics.held
    assert any(j.params == failed_job.params for j in extract.jobs)  # asked again, live
    assert any("Bin rules" in q for q in _activity_form(q for q, _ in entail.calls))  # now named
    assert not (institution_dir(run_dir, inst) / pp.WORK_DIR / pp.HELD_FILE).exists()
    assert any(r["institution_id"] == inst and r["reason"] == pp.HELD_RELEASED
               for r in attrition.read_records(run_dir))

    again = FakeExtractor(world)
    ready, _ = _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, again, FakeEntail()),
                    FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert [i.institution_id for i in ready] == [inst] and again.jobs == []


def test_c4_hold_archives_the_page_state_and_the_next_run_codes_it_from_the_new_answer(tmp_path, monkeypatch):
    """Ruling 33 a: on a C4 hold the page's saved state (page.json, activity.json, pairs.json, T-023
    activity artifact) is moved to ``<page dir>/archive/001/``; the next run codes the page again from
    the new pass-1 answer (T-023 runs on the new spans), using none of the archived state."""
    from g3o.common.artifact_io import artifact_exists
    from g3o.run.presweep import stage_activity_code

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst, page = "INST-0000002", "b1"
    one = [i for i in insts if i.institution_id == inst]
    spec = next(s for s in one[0].pages if s.page.page_id == page)
    pdir = pp._page_dir(run_dir, spec.page)
    inst_dir = institution_dir(run_dir, inst)
    art = stage_activity_code.artifact_path(inst_dir / pp.ACTIVITY_DIR, page)

    ready, metrics = _run(run_dir, bound, instrument, one,
                          _providers(run_dir, bound, instrument, NamelessActivity(world, page), FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not ready and metrics.held == [inst]
    (hold,) = _held(run_dir, inst)["held"]
    archive = pdir / pp.PAGE_ARCHIVE_DIR / "001"
    # nothing is left at the live paths; everything that was saved is in the archive folder
    assert not any((pdir / n).exists() for n in pp.PAGE_STATE_FILES) and not artifact_exists(art)
    assert (archive / "page.json").exists() and (archive / "activity.json").exists()
    assert list((archive / pp.ACTIVITY_DIR).iterdir())
    assert hold["archived"] and all((inst_dir / p).exists() for p in hold["archived"])
    archived_activity = json.loads((archive / "activity.json").read_text(encoding="utf-8"))

    coded = []
    real = stage_activity_code.run_stage

    def spy(pages, *a, **kw):
        pages = list(pages)
        coded.extend(pages)
        return real(pages, *a, **kw)
    monkeypatch.setattr(stage_activity_code, "run_stage", spy)
    extract, entail = FakeExtractor(world), FakeEntail()
    ready, metrics = _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, extract, entail),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert [i.institution_id for i in ready] == [inst] and not metrics.held
    # T-023 ran again for b1, on the spans of the new pass-1 answer (the activity is named now)
    (b1_input,) = [p for p in coded if p.page.page_id == page]
    names = [f.value for s in b1_input.spans for f in s.fields if f.item_id == "core.activity_name"]
    assert names == ["Bin rules"]
    # the stale state stays archived (never deleted); fresh state is written at the live paths
    assert (pdir / "page.json").exists() and (pdir / "activity.json").exists() and artifact_exists(art)
    assert json.loads((archive / "activity.json").read_text(encoding="utf-8")) == archived_activity
    assert not (pdir / pp.PAGE_ARCHIVE_DIR / "002").exists()


def test_c4_hold_after_an_extra_round_names_the_first_round_request(tmp_path, monkeypatch):
    """C1 a + C4 a: a first-round ``page_support`` call (the page request), then an RC-D-024 extra
    round on a strict subset of its codes (a second, quote-only pass-1 request), then a pass-1
    activity with no ``activity_name``: the C4 hold names the FIRST round's request (whose spans
    ``activity_input`` used), not the extra round's, and the page state is archived (ruling 33 a)."""
    from g3o.extract import request_v27

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst, page = "INST-0000002", "b1"
    one = [i for i in insts if i.institution_id == inst]
    real = ppv._Adapter.page_support
    rules = request_v27.default_rules()
    extra_rounds = []

    def with_extra_round(self, pg, result, records):
        out = real(self, pg, result, records)
        if pg.page_id == page and not extra_rounds:
            sub = [r for r in records if rules.needs_quote(r.item_id, r.chosen_value)][:1]
            assert sub and len(sub) < len(records)  # a strict subset: the extra-round path
            extra_rounds.append(real(self, pg, result, sub))
        return out
    monkeypatch.setattr(ppv._Adapter, "page_support", with_extra_round)
    extract = NamelessActivity(world, page)  # the first pass-1 answer on b1 names no activity
    ready, metrics = _run(run_dir, bound, instrument, one,
                          _providers(run_dir, bound, instrument, extract, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert extra_rounds and not ready and metrics.held == [inst]
    first, extra = [j for j in extract.jobs if j.metadata["stage"] == PASS1 and j.metadata["page_id"] == page]
    assert _tasks(extra)["activity_task"] is None and _tasks(first)["activity_task"] is not None
    # Ruling 46 a: the extra round has its own custom_id, the first-round one with a round suffix
    # derived from its code set; the first round's is the page's unchanged id.
    assert first.custom_id == request_v27.make_custom_id(inst, first.metadata["source_url"])
    assert extra.custom_id != first.custom_id and extra.custom_id.startswith(first.custom_id + ppv.EXTRA_ROUND_MARK)
    assert first.params != extra.params
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["stage"] == pp.EXTRACT_RESPONSE_FAILED and hold["pass"] == "pass1" and "C4 a" in hold["error"]
    assert hold["custom_id"] == first.custom_id and hold["custom_id"] != extra.custom_id
    # the first round's request (not the extra round's) is the one rejected in the journal: its
    # recorded response is the page request's answer, with the (nameless) activities
    entries = [json.loads(x) for x in (institution_dir(run_dir, inst) / pp.WORK_DIR / pp.JOURNAL)
               .read_text(encoding="utf-8").splitlines()]
    (rejected,) = [e for e in entries if e["kind"] == "extract_rejected"]
    assert json.loads(rejected["response"]["text"])["activities"]
    extract_keys = [e["key"] for e in entries if e["kind"] == "extract"]
    assert len(set(extract_keys)) == len(extract_keys) and rejected["key"] == extract_keys[0]
    # ruling 33 a: the page's saved state is archived
    spec = next(s for s in one[0].pages if s.page.page_id == page)
    pdir = pp._page_dir(run_dir, spec.page)
    assert hold["archived"] and (pdir / pp.PAGE_ARCHIVE_DIR / "001" / "page.json").exists()
    assert not any((pdir / n).exists() for n in pp.PAGE_STATE_FILES)


def test_archive_page_state_moves_every_state_file_and_numbers_each_archive(tmp_path):
    """Unit: all four kinds of saved state are moved (none deleted), each call into the next ``NNN``;
    a page with no saved state archives nothing."""
    from g3o.classify.jev_page_code import PageInput
    from g3o.common.artifact_io import write_artifact
    from g3o.run.presweep import stage_activity_code

    run_dir = tmp_path / "run"
    page = PageInput(page_id="z1", institution_id="INST-0000009", institution="Z", country=None,
                     level_of_government=None, url="https://example.gov/z1", title=None, text="z")
    assert pp._archive_page_state(run_dir, page) == []
    pdir = pp._page_dir(run_dir, page)
    inst_dir = institution_dir(run_dir, page.institution_id)
    art = stage_activity_code.artifact_path(inst_dir / pp.ACTIVITY_DIR, page.page_id)
    for n in (1, 2):
        pdir.mkdir(parents=True, exist_ok=True)
        for name in pp.PAGE_STATE_FILES:
            (pdir / name).write_text(f"{name} {n}", encoding="utf-8")
        art.parent.mkdir(parents=True, exist_ok=True)
        write_artifact(art, json.dumps({"n": n}))
        moved = pp._archive_page_state(run_dir, page)
        dest = pdir / pp.PAGE_ARCHIVE_DIR / f"{n:03d}"
        assert len(moved) == 4 and all((inst_dir / p).exists() for p in moved)
        assert all((dest / name).read_text(encoding="utf-8") == f"{name} {n}" for name in pp.PAGE_STATE_FILES)
        assert len(list((dest / pp.ACTIVITY_DIR).iterdir())) == 1
        assert not any((pdir / name).exists() for name in pp.PAGE_STATE_FILES)


def _failing_moves(monkeypatch, fail):
    """Patch the stage's ``replace_with_retry`` so the archive moves (target under an ``archive`` folder)
    or the pending-marker writes for which ``fail(kind, n)`` is true raise ``PermissionError``, as after
    exhausted retries; ``n`` counts the calls of that kind (1-based)."""
    real = pp.replace_with_retry
    seen = {"move": 0, "marker": 0}

    def fake(src, dst):
        kind = ("move" if pp.PAGE_ARCHIVE_DIR in dst.parts else
                "marker" if dst.name == pp.PAGE_ARCHIVE_PENDING else None)
        if kind is not None:
            seen[kind] += 1
            if fail(kind, seen[kind]):
                raise PermissionError(13, "Access is denied", str(dst))
        return real(src, dst)
    monkeypatch.setattr(pp, "replace_with_retry", fake)


def _spy_activity_code(monkeypatch):
    from g3o.run.presweep import stage_activity_code
    coded = []
    real = stage_activity_code.run_stage

    def spy(pages, *a, **kw):
        pages = list(pages)
        coded.extend(p.page.page_id for p in pages)
        return real(pages, *a, **kw)
    monkeypatch.setattr(stage_activity_code, "run_stage", spy)
    return coded


def test_c4_archive_failing_midway_holds_and_no_run_resumes_from_the_partial_state(tmp_path, monkeypatch):
    """Ruling 33 a with 28 a: a PermissionError on the 2nd archive move is a hold, not a crash. The page's
    pending marker stays, so the stale activity.json left at its live path is never loaded: a run whose
    archive fails again holds again (ARCHIVE_FAILED) without coding the page, and the next run finishes the
    same ``archive/001`` (no second folder) and codes the page again from the new pass-1 answer."""
    from g3o.common.artifact_io import artifact_exists
    from g3o.run.presweep import stage_activity_code

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst, page = "INST-0000002", "b1"
    one = [i for i in insts if i.institution_id == inst]
    spec = next(s for s in one[0].pages if s.page.page_id == page)
    pdir = pp._page_dir(run_dir, spec.page)
    inst_dir = institution_dir(run_dir, inst)
    art = stage_activity_code.artifact_path(inst_dir / pp.ACTIVITY_DIR, page)
    archive = pdir / pp.PAGE_ARCHIVE_DIR / "001"
    marker = pdir / pp.PAGE_ARCHIVE_PENDING

    with monkeypatch.context() as m:
        _failing_moves(m, lambda kind, n: kind == "move" and n == 2)
        ready, metrics = _run(run_dir, bound, instrument, one,
                              _providers(run_dir, bound, instrument, NamelessActivity(world, page), FakeEntail()),
                              FakeJev(ANSWERS, RELATIONS, _fail_verdict))  # no exception escapes
    assert not ready and metrics.held == [inst]
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["stage"] == pp.EXTRACT_RESPONSE_FAILED and hold["page_id"] == page
    assert hold["archive_error"].startswith("PermissionError")
    rel = pdir.relative_to(inst_dir).as_posix()
    assert hold["archived"] == [f"{rel}/{pp.PAGE_ARCHIVE_DIR}/001/page.json"]
    assert f"{rel}/activity.json" in hold["archive_left"]
    assert f"{rel}/{pp.PAGE_ARCHIVE_PENDING}" in hold["archive_left"]
    assert any(r["institution_id"] == inst and r["reason"] == pp.HELD_REASON
               and r["detail"] == f"{page}:{pp.EXTRACT_RESPONSE_FAILED}:{pp.ARCHIVE_FAILED}"
               for r in attrition.read_records(run_dir))
    # documented state: page.json archived, the rest still at the live paths behind the pending marker
    assert marker.exists() and (archive / "page.json").exists() and not (pdir / "page.json").exists()
    assert (pdir / "activity.json").exists() and artifact_exists(art)
    stale_activity = json.loads((pdir / "activity.json").read_text(encoding="utf-8"))

    coded = _spy_activity_code(monkeypatch)
    with monkeypatch.context() as m:  # the archive still fails: held again, nothing of the page is loaded
        _failing_moves(m, lambda kind, n: kind == "move")
        loaded = []
        real_load = pp.Checkpoint.load
        m.setattr(pp.Checkpoint, "load", lambda self: loaded.append(self.path) or real_load(self))
        ready, metrics = _run(run_dir, bound, instrument, one,
                              _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
                              FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not ready and metrics.held == [inst]
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["stage"] == pp.ARCHIVE_FAILED and hold["archive_error"].startswith("PermissionError")
    assert not any(p.parent == pdir for p in loaded) and page not in coded and marker.exists()

    ready, metrics = _run(run_dir, bound, instrument, one,
                          _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert [i.institution_id for i in ready] == [inst] and not metrics.held
    assert page in coded  # T-023 ran again on the new spans, not resumed from the stale activity.json
    # the same archive folder was finished (marker moved in last); no second folder was taken
    assert not marker.exists() and (archive / pp.PAGE_ARCHIVE_PENDING).exists()
    assert json.loads((archive / "activity.json").read_text(encoding="utf-8")) == stale_activity
    assert list((archive / pp.ACTIVITY_DIR).iterdir())
    assert not (pdir / pp.PAGE_ARCHIVE_DIR / "002").exists()
    assert json.loads((pdir / "activity.json").read_text(encoding="utf-8")) != stale_activity


def test_c4_archive_failing_before_its_marker_is_finished_from_held_json(tmp_path, monkeypatch):
    """The pending-marker write itself fails: nothing is moved and no marker exists, so the hold in
    held.json (``archive_error``) is what the next run reads to archive the stale state before coding."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst, page = "INST-0000002", "b1"
    one = [i for i in insts if i.institution_id == inst]
    spec = next(s for s in one[0].pages if s.page.page_id == page)
    pdir = pp._page_dir(run_dir, spec.page)

    with monkeypatch.context() as m:
        _failing_moves(m, lambda kind, n: kind == "marker")
        ready, metrics = _run(run_dir, bound, instrument, one,
                              _providers(run_dir, bound, instrument, NamelessActivity(world, page), FakeEntail()),
                              FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not ready and metrics.held == [inst]
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["archived"] == [] and hold["archive_error"].startswith("PermissionError")
    assert not (pdir / pp.PAGE_ARCHIVE_PENDING).exists() and not (pdir / pp.PAGE_ARCHIVE_DIR).exists()
    stale_activity = json.loads((pdir / "activity.json").read_text(encoding="utf-8"))

    coded = _spy_activity_code(monkeypatch)
    ready, metrics = _run(run_dir, bound, instrument, one,
                          _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert [i.institution_id for i in ready] == [inst] and not metrics.held
    assert page in coded
    archive = pdir / pp.PAGE_ARCHIVE_DIR / "001"
    assert json.loads((archive / "activity.json").read_text(encoding="utf-8")) == stale_activity
    assert not (pdir / pp.PAGE_ARCHIVE_PENDING).exists()


def test_missing_name_check_covers_the_activity_form_only(tmp_path, monkeypatch):
    """Unit: a page-form X35 question needs no name; an activity-form one without a name raises
    ``ExtractorResponseFailed`` for the given pass-1 request before ``entailment_question`` is called;
    with no activity id (the page seam) the check does not apply and ``entailment_question``'s own
    ``ValueError`` is left alone."""
    adapter = ppv._Adapter(None, tmp_path, lambda job: pytest.fail("no extractor call"), FakeEntail())
    monkeypatch.setattr(support_check, "_needs_quote", lambda *a: True)
    monkeypatch.setattr(support_check, "_quote_source", lambda *a: "The council pilots a chatbot.")
    monkeypatch.setattr(support_check, "match_quote", lambda q, s: type("M", (), {"matched": True})())
    monkeypatch.setattr(support_check, "entailment_window", lambda q, s: (s, True))
    request = {"custom_id": "cid-b1", "params": {"p": 1}}

    def ev(item, value, activity_id="b1#a001"):
        return support_check.CodeEvidence(item, value, "b1#p0", quote="chatbot", activity_id=activity_id)

    assert adapter._entailment(ev("core.page_verdict", "confirms_activity"), None, None, request) is TRUE
    for name in (None, "", "  "):
        with pytest.raises(pp.ExtractorResponseFailed) as info:
            adapter._entailment(ev("core.activity_type", "pilot_experiment"), None, name, request)
        assert info.value.pass_name == "pass1" and info.value.request == request
    assert adapter._entailment(ev("core.activity_type", "pilot_experiment"), None, "Bin rules", request) is TRUE
    assert any("Bin rules" in q for q, _ in adapter.entail_fn.calls)
    with pytest.raises(ValueError, match="activity form needs the activity name"):
        adapter._entailment(ev("core.activity_type", "pilot_experiment", activity_id=None), None, None, request)


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


def _tasks(job):
    return json.loads(job.params["messages"][0]["content"].split("\nTASKS:\n", 1)[1])


def test_extra_round_pass1_request_asks_only_the_new_quote_tasks(tmp_path):
    """C1 a (PI 2026-11-11): an RC-D-024 extra round on an R-003 page sends only the quote tasks of
    the newly eligible codes (no link, span or date task); its quote-only answer is consumed, and
    the spans ``activity_input`` reads are the first-round page request's. The first-round request
    is the one the unchanged T-022 plan builds."""
    from dataclasses import replace as dc_replace

    from g3o.classify.jev_page_code import PageCodeResult, to_pass1_page
    from g3o.classify.question_rounds import PageRoundResult
    from g3o.common.artifact_io import read_artifact
    from g3o.extract import request_v27
    from g3o.run.presweep import stage_page_code

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    a = [i for i in insts if i.institution_id == "INST-0000001"]
    _run(run_dir, bound, instrument, a, _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
         FakeJev(ANSWERS, RELATIONS))
    page = world.pages["p1"].input
    result = PageCodeResult.from_json(read_artifact(stage_page_code.artifact_path(run_dir, page.institution_id,
                                                                                  page.url)))
    assert result.verdict.value in request_v27.R003_VERDICTS and not page.has_metadata_date
    records = [r for r in result.records if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED]
    new = [r for r in records if r.item_id == "core.disclosure_form"]
    assert new and len(new) < len(records)

    extract = FakeExtractor(world)
    providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
    first = providers.page_support(page, result, records)
    assert len(extract.jobs) == 1
    full = to_pass1_page(result, page)
    assert extract.jobs[0].params == bound.pass1_job(full, request_v27.select_requests(full)).params
    t1 = _tasks(extract.jobs[0])
    assert t1["activity_task"] is not None and t1["date_task"] is True
    assert len(t1["quote_tasks"]) > len(new)
    assert len(first) == len(records)

    extra = providers.page_support(page, result, new)  # the extra round's newly eligible codes
    assert len(extract.jobs) == 2
    t2 = _tasks(extract.jobs[1])
    assert t2 == {"quote_tasks": [{"task_id": f"q{n:03d}", "part_id": r.chunk_id,
                                   "question": request_v27.default_rules().questions[r.item_id],
                                   "answer": r.chosen_value, "chrome_allowed": False}
                                  for n, r in enumerate(new, start=1)],
                  "link_task": False, "activity_task": None, "date_task": False}
    assert extract.jobs[1].params["system"] == bound.pass1_system  # the pinned system prompt, unchanged
    assert [(s.item_id, s.chunk_id) for s in extra] == [(r.item_id, r.chunk_id) for r in new]
    assert all(s.supporting_text for s in extra)  # the quote-only answer was consumed
    # ruling 46 a: the extra round's custom_id is its own, and a fresh adapter (a resume) builds the
    # same one, so the journal replays the same request; the first round's id is the page's
    page_cid = request_v27.make_custom_id(page.institution_id, page.url)
    assert extract.jobs[0].custom_id == page_cid
    wanted = {(r.item_id, r.chunk_id, r.chosen_value) for r in new}
    extra_codes = [c for c in full.codes if (c.item_id, c.chunk_id, c.value) in wanted]
    assert extract.jobs[1].custom_id == ppv.extra_round_custom_id(page_cid, extra_codes)
    assert ppv.extra_round_custom_id(page_cid, extra_codes[::-1]) == extract.jobs[1].custom_id  # order-free
    assert ppv.extra_round_custom_id(page_cid, full.codes) != extract.jobs[1].custom_id  # set-bound
    assert extract.jobs[1].custom_id != page_cid and len(extract.jobs[1].custom_id) <= 64
    resumed = FakeExtractor(world)
    _providers(run_dir, bound, instrument, resumed, FakeEntail()).page_support(page, result, new)
    assert [j.custom_id for j in resumed.jobs] == [extract.jobs[1].custom_id]

    inp = providers.activity_input(page, PageRoundResult(result, jpc.finalize_page(result, first + extra,
                                                                                   bound.page_config),
                                                         tuple(first) + tuple(extra), 1))
    assert [s.activity_id for s in inp.spans] == [aid("p1")]  # the first-round spans
    assert len(extract.jobs) == 2

    # An extra round whose new codes need no quote makes no call (an R-003 page used to ask spans
    # again). The no-quote code is one of the page's pass-1 codes, so the round is a strict subset
    # of ``full.codes``: the extra-round path, where quote_tasks_only leaves no task.
    from g3o.common import support_check

    rules = request_v27.default_rules()
    # a no-quote value that is not set by a rule (those need a rule name, which a jev record lacks)
    no_quote_value = sorted(rules.no_support_values - support_check.default_rules().rule_values)[0]
    no_quote = dc_replace(new[0], chosen_value=no_quote_value)
    nq_result = dc_replace(result, records=tuple(no_quote if r is new[0] else r for r in result.records))
    nq_full = to_pass1_page(nq_result, page)
    nq_code = (no_quote.item_id, no_quote.chunk_id, no_quote.chosen_value)
    assert nq_code in {(c.item_id, c.chunk_id, c.value) for c in nq_full.codes} and len(nq_full.codes) > 1
    assert not rules.needs_quote(no_quote.item_id, no_quote.chosen_value)
    nq_plan = request_v27.select_requests(dc_replace(nq_full, codes=tuple(
        c for c in nq_full.codes if (c.item_id, c.chunk_id, c.value) == nq_code)))
    assert nq_plan.needs_request and not request_v27.quote_tasks_only(nq_plan).needs_request
    providers.page_support(page, nq_result, [no_quote])
    assert len(extract.jobs) == 2

    # Separately, the empty-codes path: a record that is not among the page's pass-1 codes leaves the
    # round with no code at all, which also makes no call.
    providers.page_support(page, result, [no_quote])
    assert len(extract.jobs) == 2


def test_pass2_later_round_takes_the_same_request_uninterrupted_and_resumed(tmp_path, monkeypatch):
    """Ruling 49 a with 41 a: a later activity round (a strict subset of the page's ordinary codes,
    the earlier ones already supported) takes the extra-round request whether the adapter made the
    page request in this process or is fresh (a resume, ``_pair_quotes`` empty); the resumed call is
    replayed from the journal (no extractor call), and ``pair_support`` then rebuilds the page
    request from the T-023 artifact, also replayed."""
    from g3o.classify.jev_activity_code import PAIR_ITEMS, to_pass2_page
    from g3o.extract import pass2_support

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    calls = []
    real = ppv._Adapter.activity_support

    def spy(self, inp, result, records):
        calls.append((inp, result, tuple(records)))
        return real(self, inp, result, records)
    monkeypatch.setattr(ppv._Adapter, "activity_support", spy)
    _run(run_dir, bound, instrument, insts, _providers(run_dir, bound, instrument, FakeExtractor(world),
                                                         FakeEntail()), FakeJev(ANSWERS, RELATIONS))
    monkeypatch.setattr(ppv._Adapter, "activity_support", real)  # not undo(): keeps the layout fixture
    inp, result, records = calls[0]  # a page's first activity call: every ordinary code
    full = to_pass2_page(result, inp)

    def sub_needing_a_quote():
        for a, r in records:
            key = (a, r.item_id, r.item_part, r.chunk_id, str(r.chosen_value), None)
            acts = tuple(replace(x, codes=tuple(c for c in x.codes if ppv._Adapter._code_key(x.activity_id, c) == key))
                         for x in full.activities)
            if pass2_support.select_requests(replace(full, activities=acts)).quote_tasks:
                return [(a, r)]
        return []
    later = sub_needing_a_quote()
    assert later and len(later) < len(records)
    assert all(r.item_id not in PAIR_ITEMS for _, r in records)

    path = tmp_path / "journal.jsonl"

    def journaled(extract, seen):
        journal = rt.RequestJournal(path, {"s": 1})
        providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
        wrap_extract, wrap_entail = journal.seams(providers.journal_prompt)

        def spying(fn):
            inner = wrap_extract(fn)

            def call(job):
                seen.append(job.custom_id)
                return inner(job)
            return call
        return journal, providers.with_seams(spying, wrap_entail)

    # uninterrupted: the page request, then the later round in the same process
    seen1, ex1 = [], FakeExtractor(world)
    _, p1 = journaled(ex1, seen1)
    p1.activity_support(inp, result, records)
    later1 = p1.activity_support(inp, result, later)
    first_cid, extra_cid = seen1
    assert ppv.EXTRA_ROUND_MARK not in first_cid and extra_cid.startswith(first_cid + ppv.EXTRA_ROUND_MARK)
    assert [j.custom_id for j in ex1.jobs] == seen1
    # resumed: a fresh adapter (no _pair_quotes) on the same journal reaches the later round first
    seen2, ex2 = [], FakeExtractor(world)
    journal2, p2 = journaled(ex2, seen2)
    later2 = p2.activity_support(inp, result, later)
    assert seen2 == [extra_cid] and ex2.jobs == [] and journal2.live == 0
    assert [pp.support_to_dict(s) for s in later2] == [pp.support_to_dict(s) for s in later1]
    # pair_support rebuilds the page request from the T-023 artifact: replayed, no extractor call
    # (its X35 questions on pair codes were never asked by p1, so only the extractor is checked)
    p2.pair_support(inp, result)
    assert seen2 == [extra_cid, first_cid] and ex2.jobs == []


# ---------------------------------------------------------------------------
# Ruling 34 b / 41 a: 3-attempt cap on rejected extractor requests, PI release
# ---------------------------------------------------------------------------


def _release_path(run_dir, inst):
    return institution_dir(run_dir, inst) / pp.PI_RELEASE_FILE


def _write_release(run_dir, inst, doc):
    _release_path(run_dir, inst).parent.mkdir(parents=True, exist_ok=True)
    _release_path(run_dir, inst).write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")


def test_third_rejection_is_a_permanent_hold_until_the_pi_releases_it(tmp_path):
    """Ruling 34 b / 41 a: attempts 1 and 2 are called and held as C3; the 3rd rejection holds with the
    cap stage; the next run holds without calling the extractor for that request; a PI release file lets
    the next run call it again with the count restarted, and the file is archived, never re-applied."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst = "INST-0000001"
    one = [i for i in insts if i.institution_id == inst]

    def run(extract):
        return _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, extract, FakeEntail()),
                    FakeJev(ANSWERS, RELATIONS, _fail_verdict))

    failed_params = None
    for attempt in (1, 2, 3):
        bad = BadResponse(world, PASS1, "p1", "not_json", times=99)
        ready, metrics = run(bad)
        job = _bad_job(bad, PASS1, "p1")  # called live every attempt
        failed_params = failed_params or job.params
        assert job.params == failed_params and not ready and metrics.held == [inst]
        (hold,) = _held(run_dir, inst)["held"]
        assert _kinds(run_dir, inst).count("extract_rejected") == attempt
        if attempt < 3:
            assert hold["stage"] == pp.EXTRACT_RESPONSE_FAILED
    assert hold["stage"] == pp.EXTRACT_REJECTED_CAP and hold["rejections"] == 3 and hold["pass"] == "pass1"
    assert hold["page_id"] == "p1" and hold["custom_id"] == job.custom_id
    key = hold["request_key"]
    assert len(key) == 64 and "ExtractContractError" in hold["error"]

    # Resume (twice): held without calling the extractor for that request; the hold persists.
    for _ in range(2):
        extract = FakeExtractor(world)
        ready, metrics = run(extract)
        assert not ready and metrics.held == [inst]
        assert not any(j.params == failed_params for j in extract.jobs)
        (hold,) = _held(run_dir, inst)["held"]
        assert hold["stage"] == pp.EXTRACT_REJECTED_CAP and hold["request_key"] == key
        assert hold["rejections"] == 3 and hold["pass"] == "pass1" and "no extractor call made" in hold["error"]
        assert _kinds(run_dir, inst).count("extract_rejected") == 3

    # PI release: the next run calls it again, and the count restarts (one rejection is a C3 hold again).
    _write_release(run_dir, inst, {"released_by": "PI", "date": "2026-11-12", "keys": [key]})
    bad = BadResponse(world, PASS1, "p1", "not_json", times=99)
    ready, metrics = run(bad)
    assert _bad_job(bad, PASS1, "p1").params == failed_params
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["stage"] == pp.EXTRACT_RESPONSE_FAILED
    assert not _release_path(run_dir, inst).exists()
    archived = institution_dir(run_dir, inst) / "archive" / pp.PI_RELEASE_ARCHIVE / "001" / pp.PI_RELEASE_FILE
    assert json.loads(archived.read_text(encoding="utf-8"))["keys"] == [key]
    kinds = _kinds(run_dir, inst)
    assert kinds.count("pi_released") == 1 and kinds.count("extract_rejected") == 4
    journal = rt.RequestJournal(institution_dir(run_dir, inst) / pp.WORK_DIR / pp.JOURNAL, {})
    assert journal.rejections(key) == 1

    # A good answer now completes the institution.
    ready, metrics = run(FakeExtractor(world))
    assert [i.institution_id for i in ready] == [inst] and not metrics.held
    assert _kinds(run_dir, inst).count("pi_released") == 1  # the archived file is not re-applied


@pytest.mark.parametrize("doc", [
    "not json {",
    {"released_by": "PI", "date": "2026-11-12"},  # neither keys nor all
    {"released_by": "PI", "date": "2026-11-12", "keys": ["a" * 64], "all": True},  # both
    {"released_by": "PI", "date": "12/11/2026", "all": True},
    {"released_by": "", "date": "2026-11-12", "all": True},
    {"released_by": "PI", "date": "2026-11-12", "all": "yes"},
    {"released_by": "PI", "date": "2026-11-12", "keys": ["not-a-key"]},
    {"released_by": "PI", "date": "2026-11-12", "key": ["a" * 64]},  # unknown field
    ["a" * 64],
])
def test_malformed_release_is_an_explicit_hold(tmp_path, doc):
    """Ruling 34 b / 41 a: a malformed release file is refused, never ignored: the institution is held
    with a clear detail, no call is made, and the file stays in place."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    inst = "INST-0000001"
    one = [i for i in insts if i.institution_id == inst]
    _write_release(run_dir, inst, doc)
    extract = FakeExtractor(world)
    ready, metrics = _run(run_dir, bound, instrument, one,
                          _providers(run_dir, bound, instrument, extract, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not ready and metrics.held == [inst] and extract.jobs == []
    (hold,) = _held(run_dir, inst)["held"]
    assert hold["stage"] == pp.PI_RELEASE_MALFORMED and hold["error"].startswith("refused")
    assert _release_path(run_dir, inst).exists()
    journal = institution_dir(run_dir, inst) / pp.WORK_DIR / pp.JOURNAL
    assert not journal.exists() or "pi_released" not in _kinds(run_dir, inst)


def _journal_call(path, job, prompt, result, *, reject):
    """One run's call of ``job`` through a freshly loaded journal; ``reject`` rejects the answer."""
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(prompt)
    out = wrap(lambda j: result)(job)
    if reject:
        assert journal.reject_extract({"custom_id": job.custom_id, "params": job.params}, prompt, "bad")
    return out


def test_cap_counts_rejections_per_request_key_only(tmp_path):
    """Ruling 41 a: ``extract_failed`` entries do not count; each request key has its own count;
    ``"all": true`` releases every key."""
    from g3o.extract.anthropic_client import ExtractorJob

    path, prompt = tmp_path / "journal.jsonl", {"extractor_model": "m"}
    job_a = ExtractorJob("cid-a", {"model": "m", "messages": [{"a": 1}]}, {})
    job_b = ExtractorJob("cid-b", {"model": "m", "messages": [{"b": 1}]}, {})
    failed = ExtractorResult("cid-a", False, None, {"type": "errored"}, usage=dict(USAGE))
    bad = ExtractorResult("cid-a", True, "bad", None, usage=dict(USAGE))
    for _ in range(4):  # failed responses: always asked again, never capped
        assert not _journal_call(path, job_a, prompt, failed, reject=False).success
    for _ in range(3):
        _journal_call(path, job_a, prompt, bad, reject=True)
    journal = rt.RequestJournal(path, {"s": 1})
    key_a = journal.extract_key({"custom_id": "cid-a", "params": job_a.params}, prompt)
    assert journal.rejections(key_a) == 3
    wrap, _ = journal.seams(prompt)
    with pytest.raises(rt.ExtractRejectCapReached) as info:
        wrap(lambda j: pytest.fail("called past the cap"))(job_a)
    assert info.value.key == key_a and info.value.rejections == 3 and info.value.custom_id == "cid-a"
    # another request key is still called (its own count)
    for _ in range(2):
        _journal_call(path, job_b, prompt, replace(bad, custom_id="cid-b"), reject=True)
    journal = rt.RequestJournal(path, {"s": 1})
    key_b = journal.extract_key({"custom_id": "cid-b", "params": job_b.params}, prompt)
    assert journal.rejections(key_b) == 2 and journal.rejections(key_a) == 3
    # "all": true releases both
    journal.record_release({"keys": None, "all": True, "released_by": "PI", "date": "2026-11-12",
                            "file_sha256": "f" * 64})
    reloaded = rt.RequestJournal(path, {"s": 1})
    assert reloaded.rejections(key_a) == reloaded.rejections(key_b) == 0 and reloaded.release_applied("f" * 64)
    wrap, _ = reloaded.seams(prompt)
    assert wrap(lambda j: bad)(job_a).text == "bad" and reloaded.live == 1


@pytest.mark.parametrize("which", ["pass1", "pass2"])
def test_cap_counts_an_extra_round_apart_from_the_first_round(tmp_path, which):
    """Rulings 46 a / 49 a with 41 a: an extra round's own custom_id is its own request key, so its
    rejections never count toward the page's first-round request (even with equal params)."""
    from types import SimpleNamespace as NS

    from g3o.extract.anthropic_client import ExtractorJob, make_custom_id

    path, prompt = tmp_path / "journal.jsonl", {"extractor_model": "m"}
    params = {"model": "m", "messages": [{"same": 1}]}
    code = NS(item_id="core.model_origin", part=None, chunk_id="b1#p0", value="commercial", linked_activity=None)
    if which == "pass1":
        first_cid = make_custom_id("INST-0000002", "https://example.org/b1")
        extra_cid = ppv.extra_round_custom_id(first_cid, [code])
    else:
        first_cid = make_custom_id("INST-0000002", "https://example.org/b1", prefix="x27s")
        extra_cid = ppv.pass2_extra_round_custom_id(first_cid, NS(activities=(NS(activity_id="b1#a001",
                                                                                 codes=(code,)),)))
    first, extra = ExtractorJob(first_cid, params, {}), ExtractorJob(extra_cid, params, {})
    bad = ExtractorResult(extra_cid, True, "bad", None, usage=dict(USAGE))
    for _ in range(3):
        _journal_call(path, extra, prompt, bad, reject=True)
    journal = rt.RequestJournal(path, {"s": 1})
    key_first = journal.extract_key({"custom_id": first_cid, "params": params}, prompt)
    key_extra = journal.extract_key({"custom_id": extra_cid, "params": params}, prompt)
    assert key_first != key_extra and journal.rejections(key_extra) == 3 and journal.rejections(key_first) == 0
    wrap, _ = journal.seams(prompt)
    with pytest.raises(rt.ExtractRejectCapReached) as info:
        wrap(lambda j: pytest.fail("called past the cap"))(extra)
    assert info.value.key == key_extra and info.value.custom_id == extra_cid
    good = ExtractorResult(first_cid, True, "ok", None, usage=dict(USAGE))
    assert wrap(lambda j: good)(first).text == "ok" and journal.live == 1  # the first round is still asked


def test_cap_error_is_not_a_stage_stop():
    assert not issubclass(rt.ExtractRejectCapReached, pp.STAGE_STOPS)
    assert not issubclass(rt.ExtractRejectCapReached, (ValueError, RuntimeError, pp.ExtractorResponseFailed))
