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
from types import SimpleNamespace

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
    """With the refusing stub ``run_entailment`` as the entry (a wording off the Q160 pin) every
    X35 call refuses, and that stops the stage."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    providers = _providers(run_dir, bound, instrument, FakeExtractor(world), support_check.run_entailment)
    with pytest.raises(SupportGateError):
        _run(run_dir, bound, instrument, insts[:1], providers, FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert not any(r["reason"] == pp.HELD_REASON for r in attrition.read_records(run_dir))
    journal = (institution_dir(run_dir, "INST-0000001") / pp.WORK_DIR / pp.JOURNAL).read_text(encoding="utf-8")
    # PI ruling Q163 c: the refusing stub raises before any response (no ``usage``), so the call is not
    # journaled (as the extractor under 131.1 b) and is asked again on resume
    assert not any(json.loads(line)["kind"] == "x35_failed" for line in journal.splitlines())


def test_x35_non_answer_is_journaled_and_does_not_hold_q169b(tmp_path):
    """PI ruling Q169 b: an X35 non-answer (X35ResponseError with its billed usage) is an answer with no
    probability: the institutions go on (none held), each call is journaled as a replayed ``x35`` entry
    with its usage (no ``x35_failed``). The downgrade itself is pinned in test_support_check."""
    from g3o.extract.x35_client import X35ResponseError

    usage = {"input_tokens": 50, "output_tokens": 5, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0}

    class NonAnswer:
        def __init__(self):
            self.calls = []

        def entail_with_usage(self, question, text):
            self.calls.append((question, text))
            raise X35ResponseError("X35 response gave no answer (refusal)", usage=dict(usage))

        def __call__(self, question, text):
            return self.entail_with_usage(question, text)[0]

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    entail = NonAnswer()
    ready, metrics = _run(run_dir, bound, instrument, insts,
                          _providers(run_dir, bound, instrument, FakeExtractor(world), entail),
                          FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert entail.calls and not metrics.held
    assert [i.institution_id for i in ready] == ["INST-0000001", "INST-0000002", "INST-0000003"]
    assert not any(r["reason"] == pp.HELD_REASON for r in attrition.read_records(run_dir))
    assert sum(u["x35_calls"] for u in metrics.usage.values()) == len(entail.calls)
    assert sum(u["x35_failed"] for u in metrics.usage.values()) == 0
    for inst in ("INST-0000001", "INST-0000002", "INST-0000003"):
        path = institution_dir(run_dir, inst) / pp.WORK_DIR / pp.JOURNAL
        x35 = [e for e in map(json.loads, path.read_text(encoding="utf-8").splitlines())
               if e["kind"].startswith("x35")]
        assert all(e["kind"] == "x35" and e["response"]["value"] == support_check.X35_NON_ANSWER
                   and e["response"]["probability"] is None and e["response"]["usage"] == usage for e in x35)


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
        assert len(moved) == len(pp.PAGE_STATE_FILES) + 1 and all((inst_dir / p).exists() for p in moved)
        assert all((dest / name).read_text(encoding="utf-8") == f"{name} {n}" for name in pp.PAGE_STATE_FILES)
        assert len(list((dest / pp.ACTIVITY_DIR).iterdir())) == 1
        assert not any((pdir / name).exists() for name in pp.PAGE_STATE_FILES)


def test_c4_archive_keeps_the_residual_source_type_answers_m1(tmp_path):
    """Review M-1 (PI ruling 105 b with 33 a): the C4 archive moves the page's other saved state but leaves
    the residual source_type answers at their live path, untouched, so the next run loads them instead of
    asking again (they depend on no pass-1 answer). A second archive leaves them too."""
    from g3o.classify.jev_page_code import PageInput

    run_dir = tmp_path / "run"
    page = PageInput(page_id="z1", institution_id="INST-0000009", institution="Z", country=None,
                     level_of_government=None, url="https://example.gov/z1", title=None, text="z")
    assert pp.SOURCE_TYPE_FILE not in pp.PAGE_STATE_FILES
    pdir = pp._page_dir(run_dir, page)
    pdir.mkdir(parents=True)
    kept = pdir / pp.SOURCE_TYPE_FILE
    kept.write_text("saved residual answers", encoding="utf-8")
    for n in (1, 2):
        for name in pp.PAGE_STATE_FILES:
            (pdir / name).write_text(f"{name} {n}", encoding="utf-8")
        moved = pp._archive_page_state(run_dir, page)
        dest = pdir / pp.PAGE_ARCHIVE_DIR / f"{n:03d}"
        assert len(moved) == len(pp.PAGE_STATE_FILES) and not any(pp.SOURCE_TYPE_FILE in p for p in moved)
        assert not (dest / pp.SOURCE_TYPE_FILE).exists()
        assert kept.read_text(encoding="utf-8") == "saved residual answers"
    # only the residual answers left: nothing to archive (no empty NNN folder is taken)
    assert pp._archive_page_state(run_dir, page) == [] and not (pdir / pp.PAGE_ARCHIVE_DIR / "003").exists()


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


def test_page_support_after_an_extra_round_with_every_code_unchecked_stays_an_extra_round(tmp_path):
    """M1 (review of 5b9d8fd): after a halving in an extra round every live code can be unchecked,
    so a support call holds all the page's pass-1 codes. It is still an extra round: its own
    custom_id (ruling 46 a), quote tasks only (C1 a), never stored as the page request; and the
    activity spans are the first-round ones whether or not the adapter is fresh (a resume).

    The halving is marked synthetically (an extra-round ``halved`` log entry on the coded page);
    question_rounds tests cover the real halving reaching this call."""
    from g3o.classify.jev_page_code import PageCodeResult, to_pass1_page
    from g3o.classify.question_rounds import PageRoundResult, extra_round_started
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
    records = [r for r in result.records if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED]
    started = replace(result, requests=result.requests + ({
        "chunk_id": result.chunks[0].chunk_id, "round": 3, "group": "extra",
        "question_ids": ["core.disclosure_scope"], "outcome": "halved", "halves": [], "reask": []},))
    assert not extra_round_started(result) and extra_round_started(started)
    full = to_pass1_page(result, page)
    page_cid = request_v27.make_custom_id(page.institution_id, page.url)
    extra_cid = ppv.extra_round_custom_id(page_cid, full.codes)

    extract = FakeExtractor(world)
    providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
    first = providers.page_support(page, result, records)
    providers.page_support(page, started, records)  # every code, all unchecked
    assert [j.custom_id for j in extract.jobs] == [page_cid, extra_cid]
    t2 = _tasks(extract.jobs[1])
    assert t2["activity_task"] is None and t2["link_task"] is False and t2["date_task"] is False
    page_round = PageRoundResult(started, jpc.finalize_page(result, first, bound.page_config), tuple(first), 1)
    spans = [s.activity_id for s in providers.activity_input(page, page_round).spans]
    assert spans == [aid("p1")] and len(extract.jobs) == 2

    resumed = FakeExtractor(world)  # a fresh adapter whose first call is the post-halving one
    fresh = _providers(run_dir, bound, instrument, resumed, FakeEntail())
    fresh.page_support(page, started, records)
    assert [j.custom_id for j in resumed.jobs] == [extra_cid]
    assert [s.activity_id for s in fresh.activity_input(page, page_round).spans] == spans
    assert [j.custom_id for j in resumed.jobs] == [extra_cid, page_cid]  # page request rebuilt from T-021


class NoFirstRoundActivities(FakeExtractor):
    """The first-round pass-1 request returns no activity; the activity-only request (87 c) does."""

    def __call__(self, job):
        result = super().__call__(job)
        if job.metadata["stage"] == PASS1 and ppv.ACTIVITY_ONLY_MARK not in job.custom_id[len("x27-") + 48:]:
            payload = json.loads(result.text)
            payload["activities"] = []
            result = replace(result, text=json.dumps(payload))
        return result


def _flipped_round(run_dir, bound, page, *, flipped=True, first_verdict="background_only", log_before=None):
    """p1's coded result with a 68 b PLAN_KEPT verdict entry (``first_verdict`` -> confirms_activity)
    and a final verdict ``confirms_activity``; ``flipped=False``: no such entry.

    The stored T-021 artifact's provisional verdict is rewritten to ``first_verdict``, so the first-round
    plan (built from it, also on a resume) is planned on it (PI ruling 100 b: ``background_only`` has no
    activity task). ``log_before``: extra PLAN_KEPT ``before`` values logged ahead of the final flip
    (intermediate values between halvings), the first being ``first_verdict``."""
    from g3o.classify.jev_page_code import PageCodeResult
    from g3o.classify.question_rounds import PLAN_KEPT, PageRoundResult
    from g3o.common.artifact_io import read_artifact, write_artifact
    from g3o.run.presweep import stage_page_code

    path = stage_page_code.artifact_path(run_dir, page.institution_id, page.url)
    result = PageCodeResult.from_json(read_artifact(path))
    result = replace(result, items={**result.items, jpc.VERDICT: replace(result.items[jpc.VERDICT],
                                                                          value=first_verdict)})
    write_artifact(path, result.to_json())
    records = [r for r in result.records if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED]
    befores = log_before or [first_verdict]
    afters = [*befores[1:], "confirms_activity"]
    log = tuple({"chunk_id": None, "round": 3, "question_ids": ["core.disclosure_scope"], "outcome": PLAN_KEPT,
                 "item_id": jpc.VERDICT, "before": {"state": "combined", "value": b},
                 "after": {"state": "combined", "value": a}} for b, a in zip(befores, afters, strict=True)) if flipped else ()
    started = replace(result, requests=result.requests + ({
        "chunk_id": result.chunks[0].chunk_id, "round": 3, "group": "extra",
        "question_ids": ["core.disclosure_scope"], "outcome": "halved", "halves": [], "reask": []},) + log)
    return result, started, records, lambda first: PageRoundResult(
        started, (lambda f: replace(f, items={**f.items, jpc.VERDICT: replace(
            f.items[jpc.VERDICT], state="combined", value="confirms_activity")}))(
            jpc.finalize_page(result, first, bound.page_config)), tuple(first), 1)


def test_verdict_flipped_to_confirms_gets_one_activity_only_request_87c(tmp_path):
    """PI ruling 87 c: a page a halving flipped to confirms_activity, whose first-round request returned
    no activity, gets ONE activity-only pass-1 request: the signed activity task alone (no quote, link
    or date task; the pinned system prompt), its own custom_id, the spans activity_input uses; a fresh
    adapter (a resume) rebuilds the same request. Without the flip no such request is made."""
    from g3o.classify.jev_page_code import to_pass1_page
    from g3o.classify.question_rounds import verdict_flipped_to_confirms
    from g3o.extract import request_v27

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    a = [i for i in insts if i.institution_id == "INST-0000001"]
    _run(run_dir, bound, instrument, a, _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
         FakeJev(ANSWERS, RELATIONS))
    page = world.pages["p1"].input
    result, started, records, page_round_of = _flipped_round(run_dir, bound, page)
    page_cid = request_v27.make_custom_id(page.institution_id, page.url)

    extract = NoFirstRoundActivities(world)
    providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
    first = providers.page_support(page, result, records)
    page_round = page_round_of(first)
    assert verdict_flipped_to_confirms(page_round)
    inp = providers.activity_input(page, page_round)
    assert [j.custom_id for j in extract.jobs][0] == page_cid and len(extract.jobs) == 2
    only = extract.jobs[1]
    p1 = to_pass1_page(started, page)
    assert only.custom_id == ppv.activity_only_custom_id(page_cid, p1) and len(only.custom_id) <= 64
    assert only.custom_id not in (page_cid, ppv.extra_round_custom_id(page_cid, p1.codes))
    fields = [request_v27.field_name(i) for i in request_v27.default_rules().activity_fields]
    assert _tasks(only) == {"quote_tasks": [], "link_task": False, "activity_task": {"fields": fields},
                            "date_task": False}
    assert only.params["system"] == bound.pass1_system  # no new wording
    assert [s.activity_id for s in inp.spans] == [aid("p1")]  # the spans of the activity-only request
    ext = providers.activity_extraction(page.page_id)
    assert ext is not None and ext.custom_id == only.custom_id and ext.request_id
    assert providers.page_extraction(page.page_id).activities == ()  # the first-round request is kept
    providers.activity_input(page, page_round)  # asked once
    assert len(extract.jobs) == 2

    resumed = NoFirstRoundActivities(world)  # a fresh adapter: the same two requests, same params
    fresh = _providers(run_dir, bound, instrument, resumed, FakeEntail())
    assert [s.activity_id for s in fresh.activity_input(page, page_round).spans] == [aid("p1")]
    assert [(j.custom_id, j.params) for j in resumed.jobs] == [(j.custom_id, j.params) for j in extract.jobs]

    plain = NoFirstRoundActivities(world)  # no flip: no activity-only request, no activity
    _, _, _, unflipped_of = _flipped_round(run_dir, bound, page, flipped=False)
    other = _providers(run_dir, bound, instrument, plain, FakeEntail())
    unflipped = unflipped_of(other.page_support(page, result, records))
    assert not verdict_flipped_to_confirms(unflipped)
    assert other.activity_input(page, unflipped) is None and other.activity_extraction(page.page_id) is None
    assert [j.custom_id for j in plain.jobs] == [page_cid]


def test_activity_only_request_is_journaled_priced_and_replayed_87c(tmp_path):
    """PI ruling 87 c with 130 a / 58 a / 67 a: the activity-only request goes through the request journal
    like every extractor call: counted with its own usage, and replayed (no new call) on a resume."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    a = [i for i in insts if i.institution_id == "INST-0000001"]
    _run(run_dir, bound, instrument, a, _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
         FakeJev(ANSWERS, RELATIONS))
    page = world.pages["p1"].input
    result, _, records, page_round_of = _flipped_round(run_dir, bound, page)
    path = tmp_path / "journal87c.jsonl"

    def journaled(extract):
        journal = rt.RequestJournal(path, {"s": 1})
        base = _providers(run_dir, bound, instrument, extract, FakeEntail())
        return journal, base.with_seams(*journal.seams(base.journal_prompt))

    extract = NoFirstRoundActivities(world)
    journal, providers = journaled(extract)
    page_round = page_round_of(providers.page_support(page, result, records))
    providers.activity_input(page, page_round)
    assert len(extract.jobs) == 2
    assert _agree(journal) == [USAGE, USAGE]  # each request its own usage, priced per request (58 a)

    again = NoFirstRoundActivities(world)
    journal2, resumed = journaled(again)
    page_round2 = page_round_of(resumed.page_support(page, result, records))
    assert [s.activity_id for s in resumed.activity_input(page, page_round2).spans] == [aid("p1")]
    assert again.jobs == [] and journal2.replayed >= 2 and journal2.live == 0
    assert len(_agree(journal2)) == 2


def _is_activity_only(job):
    return job.metadata["stage"] == PASS1 and ppv.ACTIVITY_ONLY_MARK in job.custom_id[len("x27-") + 48:]


class NoActivitiesAnywhere(FakeExtractor):
    """Every pass-1 request, the activity-only one included, returns no activity (PI ruling 99.2)."""

    def __call__(self, job):
        result = super().__call__(job)
        if job.metadata["stage"] == PASS1:
            payload = json.loads(result.text)
            payload["activities"] = []
            result = replace(result, text=json.dumps(payload))
        return result


def _flip_world(tmp_path):
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    a = [i for i in insts if i.institution_id == "INST-0000001"]
    _run(run_dir, bound, instrument, a, _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
         FakeJev(ANSWERS, RELATIONS))
    return run_dir, bound, instrument, world, world.pages["p1"].input


@pytest.mark.parametrize("first_verdict,log_before,sent", [
    ("ambiguous_genai", None, False),  # first-round plan had the activity task: no 87 c request (100 b)
    ("confirms_activity", ["confirms_activity", "background_only"], False),  # restored, not flipped (101 a)
    ("background_only", ["background_only", "ambiguous_genai"], True),  # intermediate R-003 value ignored
])
def test_activity_only_request_compares_the_first_round_plan_100b(tmp_path, first_verdict, log_before, sent):
    """PI ruling 100 b / 101 a: the 87 c activity-only request is sent only when the stored first-round
    plan had no activity task and the verdict flipped to confirms_activity from its first-round value; an
    intermediate value between halvings is never compared. Also on a fresh adapter (a resume)."""
    from g3o.classify.question_rounds import first_round_verdict, verdict_flipped_to_confirms

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, started, records, page_round_of = _flipped_round(run_dir, bound, page, first_verdict=first_verdict,
                                                             log_before=log_before)
    for fresh in (False, True):
        extract = NoFirstRoundActivities(world)
        providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
        page_round = page_round_of(providers.page_support(page, result, records))
        if fresh:  # a resume: the first-round plan is rebuilt from the stored T-021 artifact
            extract = NoFirstRoundActivities(world)
            providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
        assert first_round_verdict(started)["value"] == first_verdict
        assert verdict_flipped_to_confirms(page_round) is (first_verdict != "confirms_activity")
        inp = providers.activity_input(page, page_round)
        assert any(_is_activity_only(j) for j in extract.jobs) is sent
        assert (inp is not None) is sent
        # PI ruling 109 a: not sent because the first plan had the activity task, which gave no activity, while
        # the final verdict is confirms_activity: the 99.2 downgrade
        assert providers.verdict_downgrade(page.page_id) == (None if sent else ppv.FIRST_PLAN_NO_ACTIVITY)


def test_activity_only_request_with_no_activity_downgrades_the_verdict_support_99_2(tmp_path):
    """PI ruling 99.2: the activity-only request succeeds with zero activities: no activity, and the final
    verdict's support at its deciding part is downgraded ``downgraded_no_quote`` (verdict value kept, no
    quote), every other support unchanged, so the page never counts as positive."""
    from g3o.validate.consolidate_v27 import _positive

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, _, records, page_round_of = _flipped_round(run_dir, bound, page)
    extract = NoActivitiesAnywhere(world)
    providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
    page_round = page_round_of(providers.page_support(page, result, records))
    assert providers.activity_input(page, page_round) is None
    assert sum(_is_activity_only(j) for j in extract.jobs) == 1  # asked once, no new call for the downgrade
    assert providers.verdict_downgrade(page.page_id) == ppv.ACTIVITY_ONLY_EMPTY

    verdict = page_round.final.items[jpc.VERDICT]
    down = pp.downgrade_verdict_support(page, page_round)
    key = (None, jpc.VERDICT, None, verdict.part_id, None)
    old = {pp._support_key(s): s for s in page_round.support}
    new = {pp._support_key(s): s for s in down.support}
    assert set(old) == set(new) and all(new[k] == old[k] for k in old if k != key)
    sr = new[key]
    assert sr.support_status == support_check.NO_QUOTE and sr.supporting_text is None
    assert sr.original_value == sr.value == "confirms_activity"  # tag_only: the verdict is kept (R-041)
    assert down.final == page_round.final and down.result == page_round.result  # not re-combined
    page_doc = SimpleNamespace(pipeline=pp.PIPELINE, reviewed=True, failed=False, page_verdict="confirms_activity",
                               support_status=sr.support_status, chosen_probability=verdict.probability)
    assert not _positive(page_doc)  # consolidate_v27: never positive; and not an "open positive" (downgraded_)
    assert sr.support_status.startswith("downgraded_")


@pytest.mark.parametrize("first_verdict,flipped", [
    ("ambiguous_genai", True),  # the R-003 flip ambiguous_genai -> confirms_activity, zero spans
    ("confirms_activity", False),  # confirms_activity from the first round, zero spans
])
def test_confirms_page_whose_first_plan_gave_no_activity_is_downgraded_109a(tmp_path, first_verdict, flipped):
    """PI ruling 109 a: a confirms_activity page whose first-round plan had an activity task but whose page
    request gave zero activity spans gets the 99.2 downgrade (FIRST_PLAN_NO_ACTIVITY): no activity-only
    request (ruling 100 b), the verdict support at its deciding part downgraded_no_quote, never positive. With
    spans, nothing is downgraded."""
    from g3o.validate.consolidate_v27 import _positive

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, _, records, page_round_of = _flipped_round(run_dir, bound, page, first_verdict=first_verdict,
                                                       flipped=flipped)
    extract = NoActivitiesAnywhere(world)
    providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
    page_round = page_round_of(providers.page_support(page, result, records))
    assert page_round.final.items[jpc.VERDICT].value == "confirms_activity"
    assert providers.activity_input(page, page_round) is None
    assert not any(_is_activity_only(j) for j in extract.jobs)
    assert providers.verdict_downgrade(page.page_id) == ppv.FIRST_PLAN_NO_ACTIVITY
    down = pp.downgrade_verdict_support(page, page_round)
    verdict = page_round.final.items[jpc.VERDICT]
    (sr,) = [s for s in down.support if pp._support_key(s) == (None, jpc.VERDICT, None, verdict.part_id, None)]
    assert sr.support_status == support_check.NO_QUOTE and sr.value == "confirms_activity"
    page_doc = SimpleNamespace(pipeline=pp.PIPELINE, reviewed=True, failed=False, page_verdict="confirms_activity",
                               support_status=sr.support_status, chosen_probability=verdict.probability)
    assert not _positive(page_doc)

    spans = FakeExtractor(world)  # the first request returns the page's activity: no downgrade
    with_spans = _providers(run_dir, bound, instrument, spans, FakeEntail())
    page_round = page_round_of(with_spans.page_support(page, result, records))
    assert with_spans.activity_input(page, page_round) is not None
    assert with_spans.verdict_downgrade(page.page_id) is None


def test_activity_only_request_at_the_rejection_cap_downgrades_the_verdict_support_99_1(tmp_path):
    """PI ruling 99.1 a: the activity-only request at the journal's rejection cap (ruling 34 b / 41 a: three
    unparsable responses; the journal makes no call) gives no activity and the verdict support downgrade,
    instead of the permanent hold. Before the cap, a failed or unparsable response still holds the
    institution (``ExtractorResponseFailed``, asked again on the next run): no downgrade."""
    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, _, records, page_round_of = _flipped_round(run_dir, bound, page)

    class Capped(NoFirstRoundActivities):
        def __call__(self, job):
            if _is_activity_only(job):
                raise rt.ExtractRejectCapReached("k" * 64, rt.EXTRACT_REJECT_CAP, job.custom_id)
            return super().__call__(job)

    class Failing(NoFirstRoundActivities):
        def __call__(self, job):
            if _is_activity_only(job):
                self.jobs.append(job)
                return ExtractorResult(job.custom_id, False, None, {"type": "expired"})
            return super().__call__(job)

    providers = _providers(run_dir, bound, instrument, Capped(world), FakeEntail())
    page_round = page_round_of(providers.page_support(page, result, records))
    assert providers.activity_input(page, page_round) is None
    reason = providers.verdict_downgrade(page.page_id)
    assert reason.startswith(ppv.ACTIVITY_ONLY_CAP)
    assert pp.downgrade_verdict_support(page, page_round).support != page_round.support

    failing = _providers(run_dir, bound, instrument, Failing(world), FakeEntail())
    page_round = page_round_of(failing.page_support(page, result, records))
    with pytest.raises(pp.ExtractorResponseFailed):  # transient: held and asked again first
        failing.activity_input(page, page_round)
    assert failing.verdict_downgrade(page.page_id) is None


def _type_ask(choice="vendor", p=0.95):
    """A jev fake answering the residual source_type question (PI ruling 95 a)."""
    from g3o.common.jev_client import JevAnswer, JevResult

    calls = []

    def ask(state, questions):
        calls.append(state["page_part"])
        out = {}
        for qid, q in questions.items():
            rest = [c for c in q["criteria"] if c != choice]
            out[qid] = JevAnswer(qid, "choice", choice=choice, confidence=p,
                                 probabilities={choice: p, **{c: (1 - p) / len(rest) for c in rest}})
        return JevResult(out, "jev-fixture", f"req-type-{len(calls)}", 10, 1)

    ask.calls = calls
    return ask


def _never_asked(state, questions):
    """A jev call that must not be made (``pytest.fail`` is not an ``Exception``, so no coder swallows it)."""
    pytest.fail(f"jev asked {sorted(questions)} on {state.get('page_part')}")


def _bare_spec(page):
    """A spec of ``page`` whose rows the T-015 assembler builds: declared page fields, nothing injected."""
    return SimpleNamespace(page=page, upstream=SimpleNamespace(page_fields=_page_fields(page), activity_values=None,
                                                               source_values=None, codes=None))


def test_residual_source_type_quote_rides_in_the_first_pass1_request_95a(tmp_path):
    """PI ruling 95 a: the residual source_type answers (asked on the page's T-021 parts) join the page's
    FIRST pass-1 request as quote tasks (the signed question and jev's answer); each answer is checked by
    T-024 on that request's quote; a resume rebuilds the same request. The resumed typing is a fresh object,
    obtained as the per-page stage obtains it on a resume (review M3 / H2, PI ruling 105 b: loaded from the
    page's saved answers, never asked again)."""
    from g3o.classify.question_rounds import PageRoundResult
    from g3o.common import source_fields as sf
    from g3o.extract import request_v27

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, _, records, _ = _flipped_round(run_dir, bound, page, flipped=False)
    ask = _type_ask()
    spec = _bare_spec(page)
    typing = pp._residual_source_type(run_dir, spec, ask, bound.page_config, _elsewhere())
    assert ask.calls and typing.typed_by == "classifier"
    assert typing.result.question_set_version == sf.RESIDUAL_SET_VERSION
    assert [c.chunk_id for c in typing.result.chunks] == [c.chunk_id for c in result.chunks]

    extract = FakeExtractor(world)
    providers = _providers(run_dir, bound, instrument, extract, FakeEntail())
    providers.set_source_typing(page.page_id, typing)
    providers.page_support(page, result, records)
    first = extract.jobs[0]
    tasks = [t for t in _tasks(first)["quote_tasks"] if t["answer"] == "vendor"]
    question = request_v27.default_rules().questions[sf.SOURCE_TYPE]
    assert tasks and all(t["question"] == question for t in tasks)
    page_round = PageRoundResult(result, jpc.finalize_page(result, providers.page_support(page, result, records),
                                                           bound.page_config), (), 0)
    providers.activity_input(page, page_round)
    codes = providers.source_type_codes(page.page_id)
    assert {rec.chunk_id for _, rec in codes} == {t["part_id"] for t in tasks}
    assert all(sr.item_id == sf.SOURCE_TYPE and sr.supporting_text for sr, _ in codes)

    # a resume: the stage loads the saved answers (a fresh object, equal; no jev call) for a fresh adapter,
    # which rebuilds the first request from T-021 with the same params
    reloaded = pp._residual_source_type(run_dir, spec, _never_asked, bound.page_config, _elsewhere())
    assert reloaded == typing and reloaded is not typing
    resumed = FakeExtractor(world)
    fresh = _providers(run_dir, bound, instrument, resumed, FakeEntail())
    fresh.set_source_typing(page.page_id, reloaded)
    fresh.activity_input(page, page_round)
    assert (resumed.jobs[0].custom_id, resumed.jobs[0].params) == (first.custom_id, first.params)
    assert [sr for sr, _ in fresh.source_type_codes(page.page_id)] == [sr for sr, _ in codes]

    plain = _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail())
    assert plain.source_type_codes(page.page_id) is None  # no residual typing: none


def test_residual_source_type_with_no_first_request_is_downgraded_without_a_call_95a(tmp_path):
    """PI ruling 95 a: a page whose T-021 codes need no pass-1 request gets no request for the source_type
    quote: each answer is checked with no quote (``downgraded_no_quote``) and no extractor or X35 call is
    made for it."""
    from g3o.classify.jev_page_code import to_pass1_page
    from g3o.common import source_fields as sf

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, _, _, _ = _flipped_round(run_dir, bound, page, flipped=False)
    typing = sf.code_source_type(page, _type_ask(), bound.page_config, layout=result.chunks)
    extract, entail = FakeExtractor(world), FakeEntail()
    adapter = _providers(run_dir, bound, instrument, extract, entail).adapter
    adapter.set_source_typing(page.page_id, typing)
    bare = replace(to_pass1_page(result, page), codes=(), verdict="no_genai", page_complete=None)
    assert adapter._with_source_type(bare) is bare  # no first request to join
    plan, ext, request = adapter._pass1(bare)
    assert ext is None and request is None and extract.jobs == []
    adapter._type_support(page.page_id, bare, plan, ext)
    codes = adapter.source_type_codes(page.page_id)
    assert codes and all(sr.support_status == support_check.NO_QUOTE for sr, _ in codes)
    assert extract.jobs == [] and entail.calls == []


def test_residual_typing_is_refused_after_the_first_request_was_built(tmp_path):
    """The residual answers must be set before the page's first pass-1 request is built (wiring)."""
    from g3o.common import source_fields as sf

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, _, records, _ = _flipped_round(run_dir, bound, page, flipped=False)
    providers = _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail())
    providers.page_support(page, result, records)
    typing = sf.code_source_type(page, _type_ask(), bound.page_config, layout=result.chunks)
    with pytest.raises(TypeError):
        providers.set_source_typing(page.page_id, typing)
    with pytest.raises(TypeError):
        providers.set_source_typing(page.page_id, sf.auto_source_type(sf.AUTO_OFFICIAL))


def _elsewhere():
    """The run's official sites, declared: INST-0000001's site is another host, so its pages are not official
    (PI ruling 70 b) and a readable one is left to the residual source_type question (PI ruling 95 a)."""
    from g3o.run.presweep import official_site_v27 as osv

    return osv.RunOfficialSites("fixture: 2_official_site.json", {"INST-0000001": "council-one.gov.au"},
                                frozenset())


def _page_fields(page):
    """Declared D1 a page fields (not an archive address): the T-015 assembler builds the page's rows."""
    from g3o.common import source_fields as sf
    from g3o.common.storage_fields import FIELDS
    from g3o.run.presweep import perpage_inputs_v27 as pin

    def fv(item, value):
        return sf.FieldValue(item, value, FIELDS[item]["coder"], "declared fixture")
    return pin.PageSourceFields(fv("core.source_url", page.url), fv("core.source_access_date", "2026-11-10"),
                                None, False, fv("core.source_language", "en"),
                                fv("core.syndication_group", "sg-fixture"), sf.text_source("new_run"))


def _residual_spec(insts, page_id="p1"):
    """INST-0000001's spec of ``page_id`` with page fields and no injected row values (PI ruling 35 a)."""
    a = next(i for i in insts if i.institution_id == "INST-0000001")
    spec = next(s for s in a.pages if s.page.page_id == page_id)
    return replace(spec, upstream=replace(spec.upstream, activity_values=None, source_values=None, codes=None,
                                          page_fields=_page_fields(spec.page)))


def _residual_inst(insts, page_id="p1"):
    """INST-0000001 with only ``page_id``, whose rows the T-015 assembler builds (:func:`_residual_spec`)."""
    a = next(i for i in insts if i.institution_id == "INST-0000001")
    return replace(a, pages=[_residual_spec(insts, page_id)])


def _source_type_calls(jev):
    """The residual source_type requests jev was sent (one per part asked)."""
    from g3o.common import source_fields as sf

    return [state["page_part"] for state, qids in jev.calls if sf.SOURCE_TYPE in qids]


def test_residual_source_type_page_reaches_its_row_through_the_stage_95a(tmp_path, monkeypatch):
    """Review H1: a readable residual page run through the per-page stage on the real providers. The
    residual answers (asked on the page's T-021 parts) ride in the page's first pass-1 request; they and
    their T-024 checks reach the T-015 assembler by name (``source_typing`` / ``source_type_codes``) and
    become the row's source_type and its codes. The stage then stops on what the assembler still refuses
    (a wiring gap, RC-D-033 C2 a), never on a TypeError, and source_type is not among them."""
    from g3o.common import source_fields as sf
    from g3o.extract import request_v27
    from g3o.run.presweep import source_row_v27 as srow
    from tests.test_e2e_perpage_v27 import stop_after_assemble

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    monkeypatch.setattr(pp, "load_run_official_sites", lambda run_dir: _elsewhere())
    seen = []
    monkeypatch.setattr(srow, "assemble", stop_after_assemble(srow.assemble, lambda page, rows, kw: seen.append((rows, kw))))
    extract = FakeExtractor(world)
    jev = FakeJev({**ANSWERS, sf.SOURCE_TYPE: "vendor"}, RELATIONS)
    with pytest.raises(pp.MissingUpstreamError, match="source-row assembler") as exc:
        _run(run_dir, bound, instrument, [_residual_inst(insts)],
             _providers(run_dir, bound, instrument, extract, FakeEntail()), jev)
    assert sf.SOURCE_TYPE not in exc.value.missing
    assert _source_type_calls(jev)  # the residual question was asked
    (rows, kw), = seen
    typing, codes = kw["source_typing"], kw["source_type_codes"]
    assert typing is not None and typing.typed_by == "classifier" and codes
    # the quote tasks of the residual answers rode in the page's first pass-1 request
    first = next(j for j in extract.jobs if j.metadata["stage"] == PASS1 and j.metadata["page_id"] == "p1")
    question = request_v27.default_rules().questions[sf.SOURCE_TYPE]
    tasks = [t for t in _tasks(first)["quote_tasks"] if t["question"] == question]
    assert tasks and {t["part_id"] for t in tasks} == {rec.chunk_id for _, rec in codes}
    # the row value is the deciding part's checked answer, and every check is a code of the row
    (sr,) = [sr for sr, rec in codes if rec.chunk_id == typing.outcome.part_id]
    assert sr.original_value == "vendor" and sr.supporting_text
    assert sf.SOURCE_TYPE not in rows.refused and rows.source[sf.SOURCE_TYPE].value == sr.value
    assert all(pair in rows.source_codes for pair in codes)


def test_residual_answers_are_saved_and_never_asked_again_on_a_resume_105b(tmp_path, monkeypatch):
    """Review H2 with PI ruling 105 b. Run 1: every part of the residual source_type question after the first
    (deciding) part fails (an exception: the journal does not record it as final), the page's first pass-1
    request carries the first part's quote task, and the stage stops after T-022 (on the assembler's refusals). Run 2: the answers
    saved before that request are loaded, so nothing is asked again and the first request is rebuilt with the
    same parameters and replayed (no extractor call). Run 3, the saved answers moved aside: the failed part is
    asked again live and answers, the rebuilt first request's parameters change, and the institution is held
    (pass1_request_not_journaled) before any extractor call."""
    from g3o.common import source_fields as sf
    from g3o.run.presweep import source_row_v27 as srow
    from tests.test_e2e_perpage_v27 import stop_after_assemble

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    monkeypatch.setattr(pp, "load_run_official_sites", lambda run_dir: _elsewhere())
    seen = []
    monkeypatch.setattr(srow, "assemble", stop_after_assemble(srow.assemble, lambda page, rows, kw: seen.append(kw)))
    inst = [_residual_inst(insts)]
    spec = inst[0].pages[0]
    saved = pp.page_state_dir(run_dir, spec.page) / pp.SOURCE_TYPE_FILE
    answers = {**ANSWERS, sf.SOURCE_TYPE: "vendor"}

    # The failed part must NOT be the deciding part. A deciding part with no answer is held before T-022 and
    # never saved (PI ruling 110 b; test_residual_deciding_part_failed_holds_then_only_that_part_is_asked_again_
    # 110b), which this test is not about. source_type combines by first_section (the
    # first part with a real, not failed answer), so part 1 answering pins it as the deciding part; every later
    # part fails. Matched on the exact part index ("1 of n"), never a prefix ("10 of 12" starts with "1").
    def later_parts_fail(state, questions, n):
        if sf.SOURCE_TYPE in questions and state["page_part"].split(" of ")[0] != "1":
            return RuntimeError("simulated residual part failure")
        return None

    jev1, ex1 = FakeJev(answers, RELATIONS, later_parts_fail), FakeExtractor(world)
    with pytest.raises(pp.MissingUpstreamError, match="source-row assembler"):
        _run(run_dir, bound, instrument, inst, _providers(run_dir, bound, instrument, ex1, FakeEntail()), jev1)
    assert len(_source_type_calls(jev1)) > 1 and saved.exists()
    typing1 = seen[-1]["source_typing"]
    failed_parts = {f["chunk_id"] for f in typing1.result.failures if f.get("reason") == jpc.REQUEST_FAILED}
    deciding = typing1.outcome.part_id
    assert failed_parts  # the failed part(s)
    assert deciding == typing1.result.chunks[0].chunk_id and deciding not in failed_parts  # pinned non-deciding

    jev2, ex2 = FakeJev(answers, RELATIONS), FakeExtractor(world)  # every part would answer now
    with pytest.raises(pp.MissingUpstreamError, match="source-row assembler"):
        _run(run_dir, bound, instrument, inst, _providers(run_dir, bound, instrument, ex2, FakeEntail()), jev2)
    assert _source_type_calls(jev2) == [] and ex2.jobs == []  # loaded, not asked; replayed, no call
    typing2 = seen[-1]["source_typing"]
    assert typing2 == typing1 and typing2 is not typing1

    saved.rename(saved.with_name("source_type-moved-aside.json"))
    jev3, ex3 = FakeJev(answers, RELATIONS), FakeExtractor(world)
    ready, metrics = _run(run_dir, bound, instrument, inst, _providers(run_dir, bound, instrument, ex3, FakeEntail()),
                          jev3)
    assert _source_type_calls(jev3)  # the failed part is asked again live
    assert ready == [] and metrics.held == ["INST-0000001"] and ex3.jobs == []
    (hold,) = _held(run_dir, "INST-0000001")["held"]
    assert (hold["page_id"], hold["stage"], hold["pass"]) == ("p1", pp.PASS1_NOT_JOURNALED, "pass1")
    assert len(hold["request_key"]) == 64


def test_c4_archive_at_the_stage_keeps_the_residual_answers_and_the_rejection_count_m1(tmp_path, monkeypatch):
    """Review L-2 (review M-1 at the stage). Run 1: a readable residual page (b1) is typed by the residual
    source_type question, then its first pass-1 answer names no activity: a C4 hold, whose archive moves the
    page's state but not source_type.json. Run 2: the saved answers are loaded, so no source_type call is made;
    the page's first pass-1 request is rebuilt with the same custom_id and params (the same journal key), and
    the 34 b rejection count of that key is kept (1, not reset by a changed key)."""
    from g3o.common import source_fields as sf
    from g3o.run.presweep import official_site_v27 as osv

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    # b1 belongs to INST-0000002: its site is declared too (another host than b1's), so b1 is not official
    # and is left to the residual question (an undeclared institution is refused: no question is asked)
    sites = osv.RunOfficialSites("fixture: 2_official_site.json", {"INST-0000001": "council-one.gov.au",
                                                                   "INST-0000002": "council-two.gov.au"},
                                 frozenset())
    monkeypatch.setattr(pp, "load_run_official_sites", lambda run_dir: sites)
    inst_id, page = "INST-0000002", "b1"
    b = next(i for i in insts if i.institution_id == inst_id)
    spec = next(s for s in b.pages if s.page.page_id == page)
    spec = replace(spec, upstream=replace(spec.upstream, activity_values=None, source_values=None, codes=None,
                                          page_fields=_page_fields(spec.page)))
    one = [replace(b, pages=[spec])]
    saved = pp.page_state_dir(run_dir, spec.page) / pp.SOURCE_TYPE_FILE
    journal = institution_dir(run_dir, inst_id) / pp.WORK_DIR / pp.JOURNAL
    answers = {**ANSWERS, sf.SOURCE_TYPE: "vendor"}

    jev1, ex1 = FakeJev(answers, RELATIONS, _fail_verdict), NamelessActivity(world, page)
    ready, metrics = _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, ex1, FakeEntail()),
                          jev1)
    assert ready == [] and metrics.held == [inst_id]
    (hold,) = _held(run_dir, inst_id)["held"]
    assert hold["stage"] == pp.EXTRACT_RESPONSE_FAILED and "C4 a" in hold["error"] and hold["archived"]
    assert not any(pp.SOURCE_TYPE_FILE in p for p in hold["archived"])
    assert _source_type_calls(jev1) and saved.exists()
    saved_bytes = saved.read_bytes()
    first = _bad_job(ex1, PASS1, page)
    (key,) = [json.loads(x)["key"] for x in journal.read_text(encoding="utf-8").splitlines()
              if json.loads(x)["kind"] == "extract_rejected"]

    jev2, ex2 = FakeJev(answers, RELATIONS, _fail_verdict), FakeExtractor(world)
    try:
        _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, ex2, FakeEntail()), jev2)
    except pp.MissingUpstreamError as exc:  # the assembler's unproduced items (as in the 95 a tests)
        assert sf.SOURCE_TYPE not in exc.missing
    assert _source_type_calls(jev2) == []  # loaded, never asked again
    assert saved.read_bytes() == saved_bytes
    again = next(j for j in ex2.jobs if j.metadata["stage"] == PASS1 and j.metadata["page_id"] == page)
    assert (again.custom_id, again.params) == (first.custom_id, first.params)  # the same first request
    entries = [json.loads(x) for x in journal.read_text(encoding="utf-8").splitlines()]
    assert [e["key"] for e in entries if e["kind"] == "extract_rejected"] == [key]
    assert any(e["kind"] == "extract" and e["key"] == key for e in entries)  # asked again under the same key
    assert rt.RequestJournal(journal, {}).rejections(key) == 1  # the 34 b count is kept


def test_residual_part_over_the_limit_holds_the_institution_m2(tmp_path, monkeypatch):
    """Review M2: a T-021 part over the request limit of the residual source_type question is not halved
    (``Pass1Page`` would refuse the halves' answers inside ``page_support``: a stage crash). The page's own
    data refuses source_type: the page is still coded (T-022 and on, PI ruling 106 a) with no residual
    answers, and the institution is held as a 97 b row-value refusal naming source_type; nothing is
    published and the stage goes on (no exception)."""
    from g3o.common import source_fields as sf

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    monkeypatch.setattr(pp, "load_run_official_sites", lambda run_dir: _elsewhere())
    real = sf.code_source_type

    def tight(page, ask, config, **kw):  # the residual request limit below any part's size
        return real(page, ask, replace(config, limit_tokens=1), **kw)
    monkeypatch.setattr(sf, "code_source_type", tight)
    extract, jev = FakeExtractor(world), FakeJev({**ANSWERS, sf.SOURCE_TYPE: "vendor"}, RELATIONS)
    ready, metrics = _run(run_dir, bound, instrument, [_residual_inst(insts)],
                          _providers(run_dir, bound, instrument, extract, FakeEntail()), jev)
    assert ready == [] and metrics.held == ["INST-0000001"]
    assert _source_type_calls(jev) == []  # refused before any residual call
    assert any(j.metadata["stage"] == PASS1 and j.metadata["page_id"] == "p1" for j in extract.jobs)
    (hold,) = _held(run_dir, "INST-0000001")["held"]
    assert (hold["page_id"], hold["stage"], hold["items"]) == ("p1", pp.ROW_VALUE_REFUSED, [sf.SOURCE_TYPE])
    assert hold["refusals"][sf.SOURCE_TYPE].startswith(pp.RESIDUAL_OVER_LIMIT)
    assert not (pp.page_state_dir(run_dir, _residual_spec(insts).page) / pp.SOURCE_TYPE_FILE).exists()
    details = [r.get("detail") for r in attrition.read_records(run_dir)
               if r.get("stage") == pp.STAGE and r.get("reason") == pp.HELD_REASON]
    assert details == [f"p1:{pp.ROW_VALUE_REFUSED}:{sf.SOURCE_TYPE}"]


def test_residual_deciding_part_failed_is_never_saved_or_coded_110b(tmp_path):
    """PI ruling 110 b: a residual typing whose deciding part failed with no answer (every part's request
    raised, so first_section falls back to the failed part's ``unknown``) is never coded ``unknown``: it is
    not saved, a file holding one (written before this ruling) is refused on load, and the assembler refuses
    it as a wiring error naming the ruling (the stage holds such a page before T-022)."""
    from g3o.common import source_fields as sf
    from g3o.common.instrument import canonical_json
    from g3o.run.presweep import source_row_v27 as srow

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, _, _, _ = _flipped_round(run_dir, bound, page, flipped=False)

    def failing(state, questions):
        raise RuntimeError("simulated residual part failure")

    typing = sf.code_source_type(page, failing, bound.page_config, layout=result.chunks)
    first = result.chunks[0].chunk_id
    assert typing.typed_by == "classifier" and typing.outcome.part_id == first and typing.outcome.failed
    assert srow.residual_deciding_part_failed(typing) == first
    answered = sf.code_source_type(page, _type_ask(), bound.page_config, layout=result.chunks)
    assert srow.residual_deciding_part_failed(answered) is None
    assert srow.residual_deciding_part_failed(sf.auto_source_type(sf.AUTO_OFFICIAL)) is None
    path = tmp_path / "source_type.json"
    with pytest.raises(TypeError, match="110 b"):
        pp.save_source_typing(path, typing)
    assert not path.exists()
    path.write_text(canonical_json({"format": pp.CHECKPOINT_FORMAT, "kind": "source_type",
                                    "result": typing.result.to_dict()}), encoding="utf-8")
    with pytest.raises(ValueError, match="110 b"):
        pp.load_source_typing(path, result.chunks)
    with pytest.raises(TypeError, match="110 b"):
        srow.residual_source_type_value(typing, ())


def test_residual_deciding_part_failed_holds_then_only_that_part_is_asked_again_110b(tmp_path, monkeypatch):
    """PI ruling 110 b through the stage. Run 1: the residual question's part 1 raises and every later part
    answers "not covered", so the failed part 1 decides: the institution is held (source_type_residual_part_
    failed, naming the part and its cause) before the page's first pass-1 request is built (no extractor
    call), nothing is saved, and the stage goes on (no TypeError). Run 2: the question is asked again through
    the journal; the parts answered in run 1 are replayed (no live call), only part 1 is asked live and now
    answers; the answers are saved and ride in the first pass-1 request, sent live (the 105 b journal check is
    not tripped: that request was never built before), and the row's source_type is produced."""
    from g3o.common import source_fields as sf
    from g3o.extract import request_v27
    from g3o.run.presweep import source_row_v27 as srow
    from tests.test_e2e_perpage_v27 import stop_after_assemble

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    monkeypatch.setattr(pp, "load_run_official_sites", lambda run_dir: _elsewhere())
    seen = []
    monkeypatch.setattr(srow, "assemble", stop_after_assemble(srow.assemble, lambda page, rows, kw: seen.append((rows, kw))))
    inst = [_residual_inst(insts)]
    saved = pp.page_state_dir(run_dir, inst[0].pages[0].page) / pp.SOURCE_TYPE_FILE

    def part_one(state):  # the exact part index ("1 of n"), never a prefix ("10 of 12")
        return state["page_part"].split(" of ")[0] == "1"

    answers = {**ANSWERS, sf.SOURCE_TYPE: lambda st: "vendor" if part_one(st) else NOT_COVERED}

    def part_one_fails(state, questions, n):
        if sf.SOURCE_TYPE in questions and part_one(state):
            return RuntimeError("simulated residual part failure")
        return None

    jev1, ex1 = FakeJev(answers, RELATIONS, part_one_fails), FakeExtractor(world)
    ready, metrics = _run(run_dir, bound, instrument, inst, _providers(run_dir, bound, instrument, ex1, FakeEntail()),
                          jev1)
    assert len(_source_type_calls(jev1)) > 1  # every T-021 part asked
    assert ready == [] and metrics.held == ["INST-0000001"]
    assert ex1.jobs == [] and not saved.exists() and seen == []  # held before T-022; nothing saved or produced
    (hold,) = _held(run_dir, "INST-0000001")["held"]
    assert (hold["page_id"], hold["stage"], hold["items"], hold["cause"]) == (
        "p1", pp.RESIDUAL_PART_FAILED, [sf.SOURCE_TYPE], jpc.REQUEST_FAILED)
    details = [r.get("detail") for r in attrition.read_records(run_dir)
               if r.get("stage") == pp.STAGE and r.get("reason") == pp.HELD_REASON]
    assert details == [f"p1:{pp.RESIDUAL_PART_FAILED}"]

    jev2, ex2 = FakeJev(answers, RELATIONS), FakeExtractor(world)
    with pytest.raises(pp.MissingUpstreamError, match="source-row assembler") as exc:
        _run(run_dir, bound, instrument, inst, _providers(run_dir, bound, instrument, ex2, FakeEntail()), jev2)
    asked = _source_type_calls(jev2)
    assert len(asked) == 1 and asked[0].split(" of ")[0] == "1"  # answered parts replayed, never re-asked
    assert saved.exists() and sf.SOURCE_TYPE not in exc.value.missing
    rows, kw = seen[-1]
    typing = kw["source_typing"]
    assert typing.outcome.part_id == hold["part_id"] and typing.field.value == "vendor"
    assert srow.residual_deciding_part_failed(typing) is None
    first = next(j for j in ex2.jobs if j.metadata["stage"] == PASS1 and j.metadata["page_id"] == "p1")
    question = request_v27.default_rules().questions[sf.SOURCE_TYPE]
    assert [t["part_id"] for t in _tasks(first)["quote_tasks"] if t["question"] == question] == [hold["part_id"]]
    assert sf.SOURCE_TYPE in rows.source and sf.SOURCE_TYPE not in rows.refused


def test_resumed_activity_only_request_missing_from_the_journal_holds_105b(tmp_path):
    """PI ruling 105 b: an activity-only request (87 c) that an earlier process got an answer to (the page's
    pass1_requests.json names it) is replayed from the journal on a resume; with no recorded response it holds
    (activity_only_request_not_journaled) before any call. Not named there (never answered), it is sent."""
    from g3o.classify.jev_page_code import to_pass1_page
    from g3o.extract import request_v27

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, started, records, page_round_of = _flipped_round(run_dir, bound, page)
    page_cid = request_v27.make_custom_id(page.institution_id, page.url)
    only_cid = ppv.activity_only_custom_id(page_cid, to_pass1_page(started, page))
    path, pdir = tmp_path / "journal105b.jsonl", pp.page_state_dir(run_dir, page)
    made = SimpleNamespace(custom_id=page_cid)

    def journaled(extract):
        journal = rt.RequestJournal(path, {"s": 1})
        base = _providers(run_dir, bound, instrument, extract, FakeEntail())
        providers = base.with_seams(*journal.seams(base.journal_prompt))
        return providers, page_round_of(providers.page_support(page, result, records))

    pp._record_pass1_requests(pdir, made, SimpleNamespace(custom_id=only_cid))
    ex1 = NoFirstRoundActivities(world)
    providers, page_round = journaled(ex1)
    with pytest.raises(pp.Pass1RequestNotJournaled) as exc:
        providers.activity_input(page, page_round)
    assert (exc.value.stage, exc.value.custom_id) == (pp.ACTIVITY_ONLY_NOT_JOURNALED, only_cid)
    assert not any(_is_activity_only(j) for j in ex1.jobs)

    pp._record_pass1_requests(pdir, made, None)  # never answered: sent and journaled
    ex2 = NoFirstRoundActivities(world)
    providers, page_round = journaled(ex2)
    assert providers.activity_input(page, page_round) is not None
    assert [j.custom_id for j in ex2.jobs if _is_activity_only(j)] == [only_cid]

    pp._record_pass1_requests(pdir, made, SimpleNamespace(custom_id=only_cid))  # answered: replayed
    ex3 = NoFirstRoundActivities(world)
    providers, page_round = journaled(ex3)
    assert providers.activity_input(page, page_round) is not None and ex3.jobs == []


def test_residual_source_type_step_of_the_stage_95a_105b(tmp_path):
    """Review M3: the stage's residual step (``_residual_source_type``). Not asked for a page with injected
    rows, or one typed by rule (an own official site); asked once on the page's T-021 parts for a readable
    residual page and saved; on a resume loaded (a fresh, equal object) and never asked again; a saved file
    asked on other parts is refused."""
    from g3o.classify.jev_page_code import PageCodeResult
    from g3o.common import source_fields as sf
    from g3o.common.artifact_io import read_artifact
    from g3o.common.urlnorm import site_host
    from g3o.run.presweep import official_site_v27 as osv
    from g3o.run.presweep import stage_page_code

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    spec = _bare_spec(page)
    saved = pp.page_state_dir(run_dir, page) / pp.SOURCE_TYPE_FILE
    injected = SimpleNamespace(page=page, upstream=SimpleNamespace(
        page_fields=spec.upstream.page_fields, activity_values=None, source_values=None, codes={}))
    assert pp._residual_source_type(run_dir, injected, _never_asked, bound.page_config, _elsewhere()) is None
    own = osv.RunOfficialSites("fixture", {page.institution_id: site_host(page.url)}, frozenset())
    assert pp._residual_source_type(run_dir, spec, _never_asked, bound.page_config, own) is None
    assert not saved.exists()

    ask = _type_ask()
    typing = pp._residual_source_type(run_dir, spec, ask, bound.page_config, _elsewhere())
    t021 = PageCodeResult.from_json(read_artifact(stage_page_code.artifact_path(run_dir, page.institution_id,
                                                                                page.url)))
    assert typing.typed_by == "classifier" and saved.exists()
    assert len(ask.calls) >= len(t021.chunks)  # every T-021 part asked
    assert [c.chunk_id for c in typing.result.chunks] == [c.chunk_id for c in t021.chunks]
    assert typing.field.value == "vendor"
    again = pp._residual_source_type(run_dir, spec, _never_asked, bound.page_config, _elsewhere())
    assert again == typing and again is not typing and again.result == typing.result
    assert sf.classifier_source_typing(typing.result) == typing  # the rebuild is deterministic in the result

    with pytest.raises(ValueError, match="T-021 parts"):
        pp.load_source_typing(saved, t021.chunks[:-1] if len(t021.chunks) > 1 else ())


def test_malformed_105b_page_state_is_refused_like_the_page_checkpoints(tmp_path):
    """Malformed ``source_type.json`` / ``pass1_requests.json`` follow the convention of the page checkpoints
    (``Checkpoint.load`` on page.json / activity.json, the pairs.json read): another kind or format raises
    ``ValueError("unsupported per-page checkpoint ...")``, and bytes that are not JSON raise
    ``json.JSONDecodeError`` (a ``ValueError``). None of them is caught on the searched-page path: a stage
    stop (``test_pairs_checkpoint_of_another_kind_or_format_is_refused``)."""
    from g3o.classify.jev_page_code import PageInput

    run_dir = tmp_path / "run"
    page = PageInput(page_id="z1", institution_id="INST-0000009", institution="Z", country=None,
                     level_of_government=None, url="https://example.gov/z1", title=None, text="z")
    pdir = pp.page_state_dir(run_dir, page)
    assert pp.read_pass1_requests(run_dir, page) is None
    assert pp.load_source_typing(pdir / pp.SOURCE_TYPE_FILE, ()) is None
    pp._record_pass1_requests(pdir, SimpleNamespace(custom_id="c-1"), None)
    doc = pp.read_pass1_requests(run_dir, page)
    assert (doc["page_request"], doc["activity_only"]) == ("c-1", None)
    page_ckpt = pp.Checkpoint(pdir / "page.json", "page")
    files = ((pdir / pp.PASS1_FILE, lambda: pp.read_pass1_requests(run_dir, page), "pass1_requests"),
             (pdir / pp.SOURCE_TYPE_FILE, lambda: pp.load_source_typing(pdir / pp.SOURCE_TYPE_FILE, ()),
              "source_type"),
             (page_ckpt.path, page_ckpt.load, "page"))  # the reference convention
    for path, load, kind in files:
        for damage in ({"kind": "other-kind"}, {"format": "another-format"}):
            path.write_text(json.dumps({"format": pp.CHECKPOINT_FORMAT, "kind": kind, **damage}), encoding="utf-8")
            with pytest.raises(ValueError, match="unsupported per-page checkpoint"):
                load()
        path.write_bytes(b"{not json")
        with pytest.raises(json.JSONDecodeError):
            load()


@pytest.mark.parametrize("raw", [b"{not json", b"\xff\xfe", b"[1, 2]",
                                 json.dumps({"format": pp.CHECKPOINT_FORMAT, "kind": "page"}).encode("utf-8")])
def test_record_pass1_requests_refuses_a_malformed_record_118b(tmp_path, raw):
    """PI ruling 118 b: ``_record_pass1_requests`` no longer overwrites a malformed pass1_requests.json silently:
    it raises ``MalformedCheckpoint`` (a stage stop) and leaves the file as it is. A valid record that changes
    is still rewritten."""
    pdir = tmp_path / "page"
    pdir.mkdir()
    path = pdir / pp.PASS1_FILE
    path.write_bytes(raw)
    with pytest.raises(pp.MalformedCheckpoint):
        pp._record_pass1_requests(pdir, SimpleNamespace(custom_id="c-1"), None)
    assert path.read_bytes() == raw
    path.unlink()
    assert pp._record_pass1_requests(pdir, SimpleNamespace(custom_id="c-1"), None)
    assert not pp._record_pass1_requests(pdir, SimpleNamespace(custom_id="c-1"), None)  # unchanged: not written
    assert pp._record_pass1_requests(pdir, SimpleNamespace(custom_id="c-1"), SimpleNamespace(custom_id="c-2"))
    assert json.loads(path.read_text(encoding="utf-8"))["activity_only"] == "c-2"


@pytest.mark.parametrize("damage", [{"kind": "page"}, {"format": "another-format"}])
def test_malformed_source_type_file_stops_the_stage_like_pairs_json(tmp_path, monkeypatch, damage):
    """As a pairs.json of another kind or format (test_e2e_perpage_v27), a saved residual source_type file of
    another kind or format stops the stage (ValueError) on the next run, before anything is asked again."""
    from g3o.common import source_fields as sf

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    monkeypatch.setattr(pp, "load_run_official_sites", lambda run_dir: _elsewhere())
    inst = [_residual_inst(insts)]
    saved = pp.page_state_dir(run_dir, inst[0].pages[0].page) / pp.SOURCE_TYPE_FILE
    answers = {**ANSWERS, sf.SOURCE_TYPE: "vendor"}
    from g3o.run.presweep import source_row_v27 as srow
    from tests.test_e2e_perpage_v27 import stop_after_assemble

    monkeypatch.setattr(srow, "assemble", stop_after_assemble(srow.assemble, lambda page, rows, kw: None))
    with pytest.raises(pp.MissingUpstreamError, match="source-row assembler"):
        _run(run_dir, bound, instrument, inst,
             _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()), FakeJev(answers, RELATIONS))
    doc = json.loads(saved.read_text(encoding="utf-8"))
    saved.write_text(json.dumps({**doc, **damage}), encoding="utf-8")
    jev, extract = FakeJev(answers, RELATIONS), FakeExtractor(world)
    with pytest.raises(ValueError, match="unsupported per-page checkpoint"):
        _run(run_dir, bound, instrument, inst, _providers(run_dir, bound, instrument, extract, FakeEntail()), jev)
    assert _source_type_calls(jev) == [] and extract.jobs == []


def test_rounds_for_page_applies_the_verdict_downgrade_109a(tmp_path):
    """Review M3: ``_rounds_for_page`` applies the adapter's verdict downgrade (here PI ruling 109 a): the
    page's T-022 page request, rebuilt on a resume, gives no activity while its first plan asked for one and
    the saved final verdict is confirms_activity. The page round carries the downgraded verdict support
    (downgraded_no_quote at the deciding part, the value kept), the metrics name the reason, and no activity
    is coded."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    a = [i for i in insts if i.institution_id == "INST-0000001"]
    _run(run_dir, bound, instrument, a, _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
         FakeJev(ANSWERS, RELATIONS))
    spec = next(s for s in a[0].pages if s.page.page_id == "p1")
    ask = rt.RequestJournal(tmp_path / "journal109a.jsonl", {"s": 1}).ask(FakeJev(ANSWERS, RELATIONS))
    providers = _providers(run_dir, bound, instrument, NoActivitiesAnywhere(world), FakeEntail())
    st, metrics = pp._PageState(spec), pp.PerPageMetrics()
    pp._rounds_for_page(run_dir, st, ask, providers, bound.page_config, bound.activity_config, metrics)
    assert metrics.verdict_downgrades == {"p1": ppv.FIRST_PLAN_NO_ACTIVITY}
    assert st.activity_input is None and st.activity_round is None and not st.holds
    verdict = st.page_round.final.items[jpc.VERDICT]
    assert (verdict.state, verdict.value) == ("combined", "confirms_activity")
    sr = {pp._support_key(s): s for s in st.page_round.support}[(None, jpc.VERDICT, None, verdict.part_id, None)]
    assert sr.support_status == support_check.NO_QUOTE and sr.value == "confirms_activity"


def test_downgrade_is_refused_for_a_verdict_other_than_confirms_activity(tmp_path):
    """Only a combined confirms_activity verdict is downgraded; anything else is a wiring error."""
    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, _, records, page_round_of = _flipped_round(run_dir, bound, page)
    providers = _providers(run_dir, bound, instrument, NoFirstRoundActivities(world), FakeEntail())
    page_round = page_round_of(providers.page_support(page, result, records))
    other = replace(page_round, final=replace(page_round.final, items={
        **page_round.final.items, jpc.VERDICT: replace(page_round.final.items[jpc.VERDICT], value="no_genai")}))
    with pytest.raises(TypeError):
        pp.downgrade_verdict_support(page, other)


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


def test_resumed_pass2_page_request_missing_from_the_journal_holds_ruling_98b(tmp_path):
    """PI ruling 98 b: on a resume, the pass-2 page request rebuilt from the stored T-023 artifact is replayed
    from the institution's journal; when the journal holds no response for it the institution is held
    (stage pass2_request_not_journaled, naming the custom_id and request key) and no pass-2 call is made.
    The first, uninterrupted run (the request built in round 1) is unaffected."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    a = [i for i in insts if i.institution_id == "INST-0000001"]

    def run(extract):
        return _run(run_dir, bound, instrument, a, _providers(run_dir, bound, instrument, extract, FakeEntail()),
                    FakeJev(ANSWERS, RELATIONS))
    ex1 = FakeExtractor(world)
    ready, metrics = run(ex1)
    assert metrics.ready == ["INST-0000001"] and PASS2 in ex1.stages()
    # resume with the journal intact: the rebuilt page requests are replayed, nothing is sent
    ex2 = FakeExtractor(world)
    ready, metrics = run(ex2)
    assert metrics.ready == ["INST-0000001"] and PASS2 not in ex2.stages()
    # resume with the pass-2 responses gone from the journal (a copy kept aside): the rebuilt pass-1 page
    # requests are still replayed; the pass-2 one is held before any call
    journal = institution_dir(run_dir, "INST-0000001") / pp.WORK_DIR / pp.JOURNAL
    raw = journal.read_bytes()
    journal.with_name("journal-moved-aside.jsonl").write_bytes(raw)
    kept = [line for line in raw.decode("utf-8").splitlines()
            if not (json.loads(line)["kind"] == "extract"
                    and json.loads(line)["response"]["custom_id"].startswith("x27s-"))]
    assert len(kept) < len(raw.decode("utf-8").splitlines())
    journal.write_bytes("".join(line + "\n" for line in kept).encode("utf-8"))
    ex3 = FakeExtractor(world)
    ready, metrics = run(ex3)
    assert ready == [] and metrics.held == ["INST-0000001"] and ex3.jobs == []
    (hold,) = _held(run_dir, "INST-0000001")["held"]
    assert (hold["stage"], hold["pass"]) == (pp.PASS2_NOT_JOURNALED, "pass2")
    assert hold["custom_id"] and len(hold["request_key"]) == 64 and "98 b" in hold["error"]
    # PI ruling 105 b: with the journal moved aside, the first rebuilt request (the pass-1 page request) holds
    journal.rename(journal.with_name("journal-moved-aside-2.jsonl"))
    ex4 = FakeExtractor(world)
    ready, metrics = run(ex4)
    assert ready == [] and metrics.held == ["INST-0000001"] and ex4.jobs == []
    (hold,) = _held(run_dir, "INST-0000001")["held"]
    assert (hold["stage"], hold["pass"]) == (pp.PASS1_NOT_JOURNALED, "pass1")
    assert hold["custom_id"] and len(hold["request_key"]) == 64 and "105 b" in hold["error"]


def test_pair_only_page_resumed_rebuild_is_checked_first_build_is_not_ruling_98b(tmp_path, monkeypatch):
    """PI ruling 98 b on a pair-only page (no ordinary code, so round 1 never made the page request): its
    request is first built by page_pass2 / pair_support. On a later process the page's pair checkpoint
    (pairs.json) shows that build happened, so a rebuild with no journaled response is held before any call;
    with no pair checkpoint the rebuild is the first build and is sent; once journaled it is replayed."""
    from g3o.classify.jev_activity_code import PAIR_ITEMS

    run_dir, bound, instrument, world, insts = _world(tmp_path)
    a = [i for i in insts if i.institution_id == "INST-0000001"]
    seen = []
    real_pairs = ppv._Adapter.pair_support

    def spy(self, inp, result):
        seen.append(inp)
        return real_pairs(self, inp, result)
    monkeypatch.setattr(ppv._Adapter, "pair_support", spy)
    _run(run_dir, bound, instrument, a, _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()),
         FakeJev(ANSWERS, RELATIONS))
    monkeypatch.setattr(ppv._Adapter, "pair_support", real_pairs)  # not undo(): keeps the layout fixture
    inp = seen[0]  # a page with a within-page pair (its pairs.json written by that run)
    real_p2 = ppv.to_pass2_page

    def pair_only(result, page_input):  # the stored result as a pair-only page's
        full = real_p2(result, page_input)
        return replace(full, activities=tuple(replace(x, codes=tuple(c for c in x.codes if c.item_id in PAIR_ITEMS))
                                              for x in full.activities))
    monkeypatch.setattr(ppv, "to_pass2_page", pair_only)
    pairs = pp.page_state_dir(run_dir, inp.page) / pp.PAIRS_FILE
    aside = pairs.with_name("pairs-moved-aside.json")
    assert pairs.exists()
    path = tmp_path / "pair-only-journal.jsonl"

    def journaled(extract):
        journal = rt.RequestJournal(path, {"s": 1})
        base = _providers(run_dir, bound, instrument, extract, FakeEntail())
        return base.with_seams(*journal.seams(base.journal_prompt))
    # resumed (pairs.json from the earlier process), the journal holds no response: held, no call
    ex1 = FakeExtractor(world)
    with pytest.raises(pp.Pass2RequestNotJournaled):
        journaled(ex1).page_pass2(inp)
    assert ex1.jobs == []
    # first build (no pair checkpoint yet): unaffected, the request is sent and journaled
    pairs.rename(aside)
    ex2 = FakeExtractor(world)
    journaled(ex2).page_pass2(inp)
    assert ex2.stages() == [PASS2]
    # resumed again with that journal: replayed, no call
    aside.rename(pairs)
    ex3 = FakeExtractor(world)
    journaled(ex3).page_pass2(inp)
    assert ex3.jobs == []


def test_journal_peek_reads_the_next_slot_without_using_it_ruling_98b(tmp_path):
    """The journal's ``peek`` (read by the 98 b check) says whether the next call of a job would be replayed,
    without using a slot: the call after it is still replayed."""
    from g3o.extract.anthropic_client import ExtractorJob

    job = ExtractorJob(custom_id="cid-peek", params={"model": "m", "messages": []}, metadata={})
    path, prompt = tmp_path / "journal.jsonl", {"extractor_model": "m"}
    ok = ExtractorResult("cid-peek", True, "{}", None, "fake-extractor-response", "msg-1", "x-1", "end_turn",
                         dict(USAGE))
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(prompt)
    calls = []
    fn = wrap(lambda j: calls.append(j) or ok)
    key, recorded = fn.peek(job)
    assert not recorded and len(key) == 64
    fn(job)
    reloaded = rt.RequestJournal(path, {"s": 1})
    wrap2, _ = reloaded.seams(prompt)
    fn2 = wrap2(lambda j: calls.append(j) or ok)
    assert fn2.peek(job) == (key, True) and fn2.peek(job) == (key, True)  # no slot used
    assert fn2(job).text == "{}" and len(calls) == 1 and reloaded.replayed == 1
    assert fn2.peek(job) == (key, False)  # the next slot of the same job has no response


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


# ---------------------------------------------------------------------------
# PI-approved P-2c quote-task question (RC-D-021 P-2c a): user-message wording pin
# ---------------------------------------------------------------------------


def test_approved_p2c_question_hashes_to_its_pin_and_is_accepted():
    from g3o.common.instrument import sha256_text
    from g3o.extract import pass2_support

    text = pass2_support.QUESTION_OVERRIDES["core.activity_segment"]
    assert sha256_text(text) == ppv.P2C_QUESTION_SHA256
    rules = pass2_support.default_rules()
    assert rules.questions["core.activity_segment"] == text
    ppv.require_approved_quote_questions(rules)


@pytest.mark.parametrize("overrides", [
    {"core.activity_segment": "How does this activity relate to the linked activity?"},  # other text
    {},  # the override dropped: the codebook method note would be shown instead
])
def test_unapproved_p2c_question_is_refused_before_any_extractor_call(tmp_path, monkeypatch, overrides):
    from g3o.codebook.loader import load_codebook
    from g3o.extract import pass2_support

    rules = pass2_support.rules_from_codebook(load_codebook(), overrides)
    with pytest.raises(ValueError, match="PI-approved"):
        ppv.require_approved_quote_questions(rules)
    run_dir, bound, instrument, world, _ = _world(tmp_path)
    monkeypatch.setattr(pass2_support, "default_rules", lambda: rules)
    extract = FakeExtractor(world)
    with pytest.raises(ValueError, match="PI-approved"):
        _providers(run_dir, bound, instrument, extract, FakeEntail())
    assert not extract.jobs


def test_p2c_question_is_checked_again_before_each_pass2_job(tmp_path, monkeypatch):
    """RC-D-021 P-2c a: wording changed after binding is refused at the pass-2 job, with no pass-2
    extractor call made."""
    from g3o.codebook.loader import load_codebook
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
    inp, result, records = calls[0]  # a page's first activity call: the page's pass-2 request
    extract = FakeExtractor(world)
    providers = _providers(run_dir, bound, instrument, extract, FakeEntail())  # bound with the approved text
    altered = pass2_support.rules_from_codebook(
        load_codebook(), {"core.activity_segment": "How does this activity relate to the linked activity?"})
    monkeypatch.setattr(pass2_support, "default_rules", lambda: altered)
    with pytest.raises(ValueError, match="PI-approved"):
        providers.activity_support(inp, result, records)
    assert not [j for j in extract.jobs if j.metadata["stage"] == PASS2]


def _agree(journal):
    usages = journal.extractor_usages()
    assert len(usages) == journal.usage()["extractor_calls"]
    return usages


def test_extractor_usages_agree_with_extractor_calls_across_kinds_and_reloads(tmp_path):
    """Review L5: one per-request usage per counted extractor call: failed, rejected, rejected then
    asked again, an extra round's own request, and after each reload (resume)."""
    from g3o.extract.anthropic_client import ExtractorJob

    path, prompt = tmp_path / "journal.jsonl", {"extractor_model": "m"}
    job = ExtractorJob("cid-1", {"model": "m", "messages": [{"a": 1}]}, {})
    extra = ExtractorJob("cid-1-extra", {"model": "m", "messages": [{"a": 2}]}, {})  # its own request
    failed = ExtractorResult("cid-1", False, None, {"type": "errored"}, usage=None)
    bad = ExtractorResult("cid-1", True, "bad", None, usage={**USAGE, "input_tokens": 1})
    good = ExtractorResult("cid-1", True, "good", None, usage={**USAGE, "input_tokens": 2})
    _journal_call(path, job, prompt, failed, reject=False)  # extract_failed
    assert len(_agree(rt.RequestJournal(path, {"s": 1}))) == 1
    _journal_call(path, job, prompt, bad, reject=True)  # recorded, then extract_rejected
    assert len(_agree(rt.RequestJournal(path, {"s": 1}))) == 2
    _journal_call(path, job, prompt, good, reject=False)  # asked again: a new recorded response
    _journal_call(path, extra, prompt, replace(good, custom_id=extra.custom_id), reject=False)
    reloaded = rt.RequestJournal(path, {"s": 1}, read_only=True)
    usages = _agree(reloaded)
    # Ruling 67 a: the errored result (no usage) comes as its failure type, read from the journal.
    assert len(usages) == 4 and usages.count({"failed_result_type": "errored"}) == 1
    assert sorted(u["input_tokens"] for u in usages if "input_tokens" in u) == [1, 2, 2]
    # A resume that replays everything adds no call and no usage.
    again = rt.RequestJournal(path, {"s": 1})
    wrap, _ = again.seams(prompt)
    assert wrap(lambda j: pytest.fail("asked again"))(job).text == "good"
    assert len(_agree(again)) == 4


def test_failed_extractor_results_without_usage_are_priced_at_zero_after_resume(tmp_path):
    """PI ruling 67 a: errored / expired / canceled batch results that report no usage are priced at
    $0 from the journal on disk (canceled counted on its own: its not-billed premise is unverified);
    an ``unknown`` failure without usage, and a failed result whose type was not recorded, stay
    unpriced; a failed result that does report usage is priced from it."""
    from g3o.common.cost_monitor import price_extractor_requests
    from g3o.extract.anthropic_client import ExtractorJob

    path, prompt = tmp_path / "journal.jsonl", {"extractor_model": "m"}
    full = {**USAGE, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    results = {
        "errored": ExtractorResult("c-e", False, None, {"type": "errored", "error_type": "x"}, usage=None),
        "expired": ExtractorResult("c-x", False, None, {"type": "expired"}, usage=None),
        "canceled": ExtractorResult("c-c", False, None, {"type": "canceled"}, usage=None),
        "max_tokens": ExtractorResult("c-m", False, None, {"type": "max_tokens"}, usage=full),
    }
    for i, result in enumerate(results.values()):
        job = ExtractorJob(result.custom_id, {"model": "m", "messages": [{"a": i}]}, {})
        _journal_call(path, job, prompt, result, reject=False)
    usages = _agree(rt.RequestJournal(path, {"s": 1}, read_only=True))  # a resume reads them from disk
    out = price_extractor_requests(usages, model="claude-haiku-5-5")
    assert out["unbilled_failed_calls"] == 2 and out["unbilled_canceled_calls"] == 1
    assert out["unpriced_calls"] == 0 and out["calls"] == 4 and out["usd"] is not None
    assert out["usd"] == price_extractor_requests([full], model="claude-haiku-5-5")["usd"]
    job = ExtractorJob("c-u", {"model": "m", "messages": [{"a": 9}]}, {})
    _journal_call(path, job, prompt, ExtractorResult("c-u", False, None, {"type": "unknown"}, usage=None),
                  reject=False)
    usages = _agree(rt.RequestJournal(path, {"s": 1}, read_only=True))
    out = price_extractor_requests(usages, model="claude-haiku-5-5")
    assert out["unpriced_calls"] == 1 and out["usd"] is None
    job = ExtractorJob("c-n", {"model": "m", "messages": [{"a": 10}]}, {})
    _journal_call(path, job, prompt, ExtractorResult("c-n", False, None, None, usage=None), reject=False)
    assert None in _agree(rt.RequestJournal(path, {"s": 1}, read_only=True))  # no type: not guessed


@pytest.mark.parametrize(("stage", "kind"), [(PASS1, "not_json"), (PASS2, "failed")])
def test_stage_journals_keep_extractor_usages_in_step_with_extractor_calls(tmp_path, stage, kind):
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    _run(run_dir, bound, instrument, insts,
         _providers(run_dir, bound, instrument, BadResponse(world, stage, "b1", kind), FakeEntail()),
         FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    for inst in insts:
        path = institution_dir(run_dir, inst.institution_id) / pp.WORK_DIR / pp.JOURNAL
        if path.exists():
            _agree(rt.RequestJournal(path, {}, read_only=True))
