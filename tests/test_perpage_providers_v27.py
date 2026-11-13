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


def test_failed_extractor_response_raises_and_is_asked_again(tmp_path):
    """A failed response is not a missing quote: the parser's error leaves the stage; the journal
    keeps it for accounting only, so the next run asks it again."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    b = [i for i in insts if i.institution_id == "INST-0000002"]

    class Failing(FakeExtractor):
        def __call__(self, job):
            self.jobs.append(job)
            return ExtractorResult(job.custom_id, False, None, {"type": "errored"}, usage=dict(USAGE))
    failing = Failing(world)
    with pytest.raises(RuntimeError, match="failed"):
        _run(run_dir, bound, instrument, b, _providers(run_dir, bound, instrument, failing, FakeEntail()),
             FakeJev(ANSWERS, RELATIONS))
    assert len(failing.jobs) == 1
    journal = (institution_dir(run_dir, "INST-0000002") / pp.WORK_DIR / pp.JOURNAL).read_text(encoding="utf-8")
    assert [json.loads(x)["kind"] for x in journal.splitlines()].count("extract_failed") == 1
    extract = FakeExtractor(world)
    ready, metrics = _run(run_dir, bound, instrument, b, _providers(run_dir, bound, instrument, extract, FakeEntail()),
                          FakeJev(ANSWERS, RELATIONS))
    assert [i.institution_id for i in ready] == ["INST-0000002"]
    assert extract.jobs[0].params == failing.jobs[0].params  # asked again, live
    assert metrics.usage["INST-0000002"]["extractor_calls"] == len(extract.jobs) + 1  # the failed one counted


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
