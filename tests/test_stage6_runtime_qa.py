"""T-030 Stage 6 runtime: regressions for the independent-QA findings (offline, fakes only).

Every jev answer, extractor reply and X35 answer below is a declared fake; no
client is built and no network is opened. Each test reproduces one confirmed
finding (HIGH-2, HIGH-3, MEDIUM-4..7, LOW-10, and the held-reason / per-
institution parts of HIGH-1) and pins the repaired behaviour.
"""
from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from g3o.classify.jev_activity_code import GATE_RULE
from g3o.common import attrition
from g3o.common.instrument import sha256_text
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.paths import institution_dir
from g3o.common.support_check import CodeEvidence, PageSources, check_code
from g3o.extract.anthropic_client import ExtractorResult
from g3o.persist import stage6_adapters as adapters
from g3o.persist.stage6_adapters import InputSupport, PageArtifact, combined_support_nodes
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.validate import stage6_quote as sq
from g3o.validate import stage6_v27 as s6
from tests import test_e2e_stage6_v27 as e
from tests.test_stage6_quote import FakeEntail, FakeExtractor

A, B = "INST-0000001", "INST-0000002"


def _answer(state, questions):
    return JevResult({"Q": JevAnswer("Q", "choice", choice="yes", confidence=0.9, probabilities={"yes": 0.9})},
                     "m", "rid-1", 5, 1)


def _run(run_dir, bound, instrument, insts, quote_fn, *, config=None, jev=None):
    jev = jev or e.FakeJev(e.RELATIONS, e._pooled_answers())
    return rt.run_stage6_v27(run_dir, insts, ask_fn=jev, quote_fn=quote_fn, config=config or bound.stage6_config(),
                             instrument=instrument, now=e.CLOCK)


def _held(run_dir, inst=A):
    return json.loads((institution_dir(run_dir, inst) / rt.WORK_DIR / rt.HELD_FILE).read_text(encoding="utf-8"))


def _ledger(run_dir, inst=A):
    return [r["reason"] for r in attrition.read_records(run_dir) if r["institution_id"] == inst]


class LastQuotes(e.FakeQuotes):
    """Copies the LAST shown input verbatim (a quote copied from a non-first candidate)."""

    def __call__(self, req):
        self.calls += 1
        last = req.candidates[-1]
        return s6.Stage6Quote(last.quote_text, last.support_id, e.TRUE, {"fake": True})


# --- HIGH-1: accurate hold reasons; one institution's envelope error does not stop the stage ------


class RefusingCombiner:
    def __init__(self, inner, item):
        self.inner, self.item = inner, item

    def combine(self, item_id, answers, *, reference=None):
        if item_id == self.item:
            raise ValueError("simulated combiner refusal")
        return self.inner.combine(item_id, answers, reference=reference)

    def same_part_as(self, item_id):
        return self.inner.same_part_as(item_id)


def test_unfinished_pooled_question_is_held_under_its_own_reason(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    insts = e._institutions(run_dir, bound, instrument)
    config = bound.stage6_config()
    config = replace(config, combiner=RefusingCombiner(config.combiner, "core.activity_type"))
    metrics = _run(run_dir, bound, instrument, insts[:1], e.FakeQuotes(), config=config)
    assert metrics.held == [A] and not metrics.written
    held = _held(run_dir)
    # not the "conflicting relation groups" fallback: the stopped question and the questions gated on it
    assert held["reasons"] == [rt.POOLED_PENDING, rt.POOLED_STOPPED]
    assert not held["conflicting_groups"]
    states = {(u["item_id"], u["state"]) for u in held["unfinished"]}
    assert ("core.activity_type", "stopped") in states and ("core.adoption_stage", "pending") in states
    assert _ledger(run_dir) == [f"{rt.HELD_REASON}:{rt.POOLED_PENDING}", f"{rt.HELD_REASON}:{rt.POOLED_STOPPED}"]


def test_envelope_error_for_one_institution_does_not_stop_later_institutions(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)
    metrics = _run(run_dir, bound, instrument, [replace(a, merged_values=None), b], e.FakeQuotes())
    assert metrics.failed == [A] and metrics.written == [B]
    assert not (institution_dir(run_dir, A) / "6_storage.json").exists()
    held = _held(run_dir)
    assert held["reasons"] == [rt.ENVELOPE_FAILED] and "MissingUpstreamError" in held["error"]
    assert _ledger(run_dir) == [rt.ENVELOPE_FAILED]


# --- HIGH-2: journal tail repair ------------------------------------------------------------


def test_journal_record_missing_only_its_newline_is_terminated_before_the_next_append(tmp_path):
    path = tmp_path / "journal.jsonl"
    rt.RequestJournal(path).ask(_answer)({"s": 1}, {"Q": {}})
    path.write_bytes(path.read_bytes().rstrip(b"\n"))  # interruption lost only the newline
    journal = rt.RequestJournal(path)
    assert journal.usage()["jev_responses"] == 1 and path.read_bytes().endswith(b"\n")
    journal.ask(_answer)({"s": 2}, {"Q": {}})
    assert rt.RequestJournal(path).usage()["jev_responses"] == 2  # third load still reads both


def test_journal_torn_tail_is_dropped_with_an_atomic_replace(tmp_path, monkeypatch):
    path = tmp_path / "journal.jsonl"
    rt.RequestJournal(path).ask(_answer)({"s": 1}, {"Q": {}})
    path.write_bytes(path.read_bytes() + b'{"kind": "jev", "key": "\xe2\x82')  # torn inside a UTF-8 character
    replaced, real = [], os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (replaced.append(Path(dst)), real(src, dst))[1])
    journal = rt.RequestJournal(path)
    assert replaced == [path]
    assert path.read_bytes().count(b"\n") == 1 and path.read_bytes().endswith(b"\n")
    assert journal.usage()["jev_responses"] == 1
    assert [p.name for p in tmp_path.iterdir()] == ["journal.jsonl"]  # no temp file left behind


def test_journal_corrupt_middle_line_still_refuses(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = rt.RequestJournal(path)
    journal.ask(_answer)({"s": 1}, {"Q": {}})
    journal.ask(_answer)({"s": 2}, {"Q": {}})
    lines = path.read_bytes().split(b"\n")
    path.write_bytes(b"\n".join([lines[0], b"{not json", *lines[1:]]))
    with pytest.raises(ValueError, match="corrupt Stage 6 journal line 2"):
        rt.RequestJournal(path)


# --- HIGH-3: the quote step's actual input carries through to the node ------------------------


def _bound_instrument(tmp_path):
    _, bound, instrument = e._setup(tmp_path)
    return instrument


def test_node_names_the_input_the_quote_step_copied_from_not_the_first_segment_match(tmp_path):
    instrument = _bound_instrument(tmp_path)
    qa = "The council deployed Copilot for drafting letters in 2025."
    qb = "Staff use the Binbot chatbot to answer resident questions."
    text = "Page p1. " + qa + " " + qb
    ps = PageSources("p1", {"p1#c1": text})
    shown = [InputSupport("supA", "S1", ps, PageArtifact("S1", "pages/p1.txt", text, {"p1#c1": (0, len(text))})),
             InputSupport("supB", "S2", ps, PageArtifact("S2", "pages/p1.txt", text, {"p1#c1": (0, len(text))}))]
    sr = check_code(CodeEvidence("core.tool_name", "Binbot", "p1#c1", probability=0.95, quote=qb,
                                 quote_chunk_id="p1#c1", entailment=e.TRUE, activity_id="POOL"), ps)
    kw = dict(run_id="R", institution_uid="U", chunk_id="POOL#part1", shown=shown, observation_id=None,
              uncertainty_flags=[], instrument=instrument)
    nodes = combined_support_nodes(sr, input_support_id="supB", **kw)
    assert nodes.original["input_support_ids"] == ["supB"]
    assert nodes.original["passage"]["quote_source_id"] == "S2"
    with pytest.raises(ValueError, match="ambiguous"):
        combined_support_nodes(sr, **kw)  # two inputs hold the segment: first-match is not evidence
    with pytest.raises(ValueError, match="not shown"):
        combined_support_nodes(sr, input_support_id="supX", **kw)


def _same_page_pool(run_dir, bound, instrument):
    a = e.Builder(run_dir, bound, instrument, "INST-0000003")
    a.page("p1", [e.Q3, e.Q4])
    a.observation("o1", "p1", name="Resident chatbot", activity_type="public_facing_service", tool="Binbot",
                  quote=e.Q3)
    a.observation("o2", "p1", name="Resident chatbot", activity_type="public_facing_service", tool="Binbot",
                  quote=e.Q4)
    a.within_pair("o1", "o2", "same_activity", "p1", e.Q4)
    return a, a.institution({("o1", "o2"): dict(a.inputs["o1"].row["values"])})


def test_pooled_quote_copied_from_a_non_first_candidate_names_that_candidate(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    builder, inst = _same_page_pool(run_dir, bound, instrument)
    metrics = _run(run_dir, bound, instrument, [inst], LastQuotes())
    assert metrics.written == ["INST-0000003"]
    storage = json.loads((institution_dir(run_dir, "INST-0000003") / "6_storage.json").read_text(encoding="utf-8"))
    act, = storage["activities"].values()
    o2_quote = next(q for q in builder.quotes if q.observation_id == "o2")
    quoted = [s for s in act["item_support"] if s["source_id"] is None and s["observation_id"] is None
              and s["supporting_text"]]
    assert quoted and all(s["input_support_ids"] == [o2_quote.support_id] for s in quoted)
    assert all(s["passage"]["quote_source_id"] == o2_quote.source_id for s in quoted)


def test_relation_node_is_placed_with_the_record_the_quote_was_copied_from(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a = e.Builder(run_dir, bound, instrument, "INST-0000004")
    a.page("p1", [e.Q1])
    a.page("p2", [e.Q2])
    a.observation("o1", "p1", name="Copilot drafting", activity_type="internal_operational", tool="Copilot",
                  quote=e.Q1)
    a.observation("o2", "p2", name="Copilot helpdesk", activity_type="internal_operational", tool="Copilot",
                  quote=e.Q2)
    jev = e.FakeJev({("Copilot drafting", "Copilot helpdesk"): "governs"}, e._pooled_answers())
    metrics = _run(run_dir, bound, instrument, [a.institution()], LastQuotes(), jev=jev)
    assert metrics.written == ["INST-0000004"]
    storage = json.loads((institution_dir(run_dir, "INST-0000004") / "6_storage.json").read_text(encoding="utf-8"))
    home = {oid: aid for aid, act in storage["activities"].items() for oid in act["observation_ids"]}
    rel = next(s for act in storage["activities"].values() for s in act["item_support"]
               if s["item_id"] == s6.RELATION_ITEM and s["supporting_text"])
    owner = next(aid for aid, act in storage["activities"].items() if rel in act["item_support"])
    assert rel["supporting_text"] == e.Q2 and owner == home["o2"]  # copied from the second record


# --- MEDIUM-4: accounting, X35 failure after a paid extractor call, timing ---------------------


class FlakyEntail(FakeEntail):
    def __init__(self, fail_at):
        super().__init__()
        self.fail_at = fail_at

    def __call__(self, question, text):
        self.calls.append((question, text))
        if len(self.calls) == self.fail_at:
            raise RuntimeError("simulated X35 503")
        return self.answer


def test_extractor_success_then_x35_failure_is_journaled_and_not_repaid_on_resume(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    insts = e._institutions(run_dir, bound, instrument)
    ext1, ent1 = FakeExtractor(), FlakyEntail(fail_at=1)
    first = _run(run_dir, bound, instrument, insts[:1], bound.stage6_quote_fn(ext1, ent1))
    assert first.held == [A] and len(ext1.jobs) == 1
    ext2, ent2 = FakeExtractor(), FakeEntail()
    second = _run(run_dir, bound, instrument, insts[:1], bound.stage6_quote_fn(ext2, ent2))
    assert second.written == [A]
    assert ext1.jobs[0].custom_id not in {j.custom_id for j in ext2.jobs}  # the paid copy was replayed
    usage = second.usage[A]
    assert usage["extractor_calls"] == len(ext1.jobs) + len(ext2.jobs)
    assert usage["extractor_input_tokens"] == usage["extractor_output_tokens"] == usage["extractor_calls"]
    assert usage["x35_calls"] == len(ent2.calls) and usage["x35_failed"] == 1
    lines = [json.loads(x) for x in (institution_dir(run_dir, A) / rt.WORK_DIR / rt.JOURNAL).read_text(
        encoding="utf-8").splitlines()]
    assert lines and all(isinstance(x["elapsed_ms"], int) and x["elapsed_ms"] >= 0 for x in lines)
    assert usage["request_ms"] == sum(x["elapsed_ms"] for x in lines)


def test_billed_jev_response_without_request_id_is_journaled_and_counted(tmp_path):
    path = tmp_path / "journal.jsonl"
    calls = []

    def unidentified(state, questions):
        calls.append(state)
        return replace(_answer(state, questions), request_id=None, input_tokens=7, output_tokens=3)

    assert rt.RequestJournal(path).ask(unidentified)({"s": 1}, {"Q": {}}).request_id is None
    usage = rt.RequestJournal(path).usage()
    assert usage["jev_unidentified"] == 1 and usage["jev_responses"] == 0
    assert (usage["input_tokens"], usage["output_tokens"]) == (7, 3)
    rt.RequestJournal(path).ask(unidentified)({"s": 1}, {"Q": {}})  # a failed request: asked again, counted
    assert len(calls) == 2 and rt.RequestJournal(path).usage()["jev_unidentified"] == 2


# --- MEDIUM-5: the Stage 6 quote job is bound to the instrument -------------------------------


def test_stage6_quote_job_is_configured_by_the_bound_instrument(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    payload = instrument["payload"]
    assert payload["prompt_hashes"]["stage6_quote"] == sha256_text(bound.stage6_quote_system)
    assert bound.stage6_quote_system == sq.build_system_prompt(sq.STAGE6_QUOTE_INSTRUCTION)  # the pinned text
    ext = FakeExtractor()
    insts = e._institutions(run_dir, bound, instrument)
    assert _run(run_dir, bound, instrument, insts[:1],
                bound.stage6_quote_fn(ext, FakeEntail())).written == [A]
    assert ext.jobs
    for job in ext.jobs:
        assert job.params["model"] == payload["extractor_model_id"] == e.SETTINGS.extractor_model
        assert job.params["max_tokens"] == e.SETTINGS.extractor_max_tokens
        assert job.params["output_config"]["effort"] == e.SETTINGS.extractor_effort
        assert sha256_text(job.params["system"]) == payload["prompt_hashes"]["stage6_quote"]
        assert job.metadata["setup_pointer"] == bound.instrument_id


# --- MEDIUM-6: no replay across setups -------------------------------------------------------


def test_journal_does_not_replay_a_response_recorded_under_another_setup(tmp_path):
    path, calls = tmp_path / "journal.jsonl", []

    def ask(state, questions):
        calls.append(state)
        return _answer(state, questions)

    rt.RequestJournal(path, setup={"setup_pointer": "a"}).ask(ask)({"s": 1}, {"Q": {}})
    rt.RequestJournal(path, setup={"setup_pointer": "b"}).ask(ask)({"s": 1}, {"Q": {}})
    assert len(calls) == 2  # another setup: asked, not replayed
    replayed = rt.RequestJournal(path, setup={"setup_pointer": "a"})
    replayed.ask(ask)({"s": 1}, {"Q": {}})
    assert len(calls) == 2 and replayed.replayed == 1


# --- MEDIUM-7: atomic artifacts, validate written last, Stage 7 holds a truncated storage ------


def test_stage6_artifacts_are_replaced_atomically_with_the_validate_file_last(tmp_path, monkeypatch):
    run_dir, bound, instrument = e._setup(tmp_path)
    insts = e._institutions(run_dir, bound, instrument)
    replaced, real = [], os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (replaced.append(Path(dst).name), real(src, dst))[1])
    _run(run_dir, bound, instrument, insts[:1], e.FakeQuotes())
    trio = [n for n in replaced if n.startswith("6_")]
    assert trio == [adapters.PROVENANCE_ARTIFACT, adapters.STORAGE_ARTIFACT, adapters.VALIDATE_ARTIFACT]
    assert not [p for p in institution_dir(run_dir, A).iterdir() if p.name.endswith(".tmp")]


def test_stage7_holds_one_truncated_storage_and_publishes_the_rest(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    insts = e._institutions(run_dir, bound, instrument)
    _run(run_dir, bound, instrument, insts, e.FakeQuotes())
    storage = institution_dir(run_dir, A) / "6_storage.json"
    storage.write_bytes(storage.read_bytes()[:100])
    result, rows = e._csvs(run_dir, insts)
    assert result["held_institutions"] == [A]
    assert {r["institution_id"] for r in rows["institution_summary"]} == {B}
    assert "stage7_storage_unreadable" in _ledger(run_dir)
    again = _run(run_dir, bound, instrument, insts, e.FakeQuotes())  # Stage 6 does not abort on it either
    assert again.failed == [A] and again.skipped == [B]


# --- LOW-10 ----------------------------------------------------------------------------------


def test_held_attrition_is_keyed_by_reason_and_released_on_publication(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    insts = e._institutions(run_dir, bound, instrument)

    def failing(req):
        raise RuntimeError("simulated quote failure")

    _run(run_dir, bound, instrument, insts[:1], None)
    _run(run_dir, bound, instrument, insts[:1], failing)
    assert _run(run_dir, bound, instrument, insts[:1], e.FakeQuotes()).written == [A]
    # the held relation is also a missing relation decision (once, deduplicated on the reason)
    assert _ledger(run_dir) == [f"{rt.HELD_REASON}:{rt.MISSING_RELATION}", f"{rt.HELD_REASON}:{s6.QUOTE_STEP_ABSENT}",
                                f"{rt.HELD_REASON}:{s6.QUOTE_STEP_FAILED}", rt.HELD_RELEASED]
    assert not (institution_dir(run_dir, A) / rt.WORK_DIR / rt.HELD_FILE).exists()


@pytest.mark.parametrize("text", ["[1, 2]", "5", '"quote"', "null"])
def test_quote_answer_that_is_not_an_object_is_a_failed_quote_request(text):
    with pytest.raises(sq.Stage6QuoteFailed):
        sq.parse_answer(ExtractorResult("x27q6-1", True, text, None), {})


def test_gated_out_mechanical_records_carry_the_item_part_of_their_rule_node(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    inst = e._institutions(run_dir, bound, instrument)[0]
    result = s6.run_stage6(institution="x", country="AU", pages=inst.pages, observations=inst.observations,
                           records=inst.records, within_page=inst.within_page, quotes=inst.quotes,
                           ask_fn=e.FakeJev(e.RELATIONS, e._pooled_answers()), quote_fn=e.FakeQuotes(),
                           config=bound.stage6_config())
    pooled, = result.pooled.values()
    gated = {r.question_id: r for r in pooled.records if r.rule_reference and r.rule_reference.startswith(GATE_RULE)}
    outs = [o for o in pooled.outcomes.values() if o.state == "gated_out"]
    assert outs and all(gated[o.question_id].item_part == o.part for o in outs)
    # No pooled parts question is item-gated in r15; the record builder itself must keep the part.
    rec = s6._mechanical("core.observed_actor_relationship", "q", "not_asked", "r", bound.stage6_config(), "qsv",
                         part="searched_institution_role")
    assert rec.item_part == "searched_institution_role"


# --- RC-D-029 item 7: X2-X4 coverage (already as built; pinned here) ---------------------------


def _storage(run_dir, inst=A):
    return json.loads((institution_dir(run_dir, inst) / "6_storage.json").read_text(encoding="utf-8"))


def test_pooled_evaluation_answers_stay_in_provenance_only(tmp_path):
    # X2 a: pooled answers to items the activities table does not hold stay in coder/support provenance
    run_dir, bound, instrument = e._setup(tmp_path)
    insts = e._institutions(run_dir, bound, instrument)
    assert _run(run_dir, bound, instrument, insts[:1], e.FakeQuotes()).written == [A]
    merged = next(a for a in _storage(run_dir)["activities"].values() if a["observation_ids"] == ["o1", "o2"])
    pooled_eval = {c["item_id"] for c in merged["coder_records"] if c["item_id"].startswith("core.evaluation_")}
    assert "core.evaluation_documented" in pooled_eval
    assert not [k for k in merged["values"] if k.startswith("core.evaluation_")]


def test_unconfirmed_group_is_not_an_activity_row_and_its_relations_are_not_stored(tmp_path):
    # X3 a (i): activity rows only for groups with >=1 supported observation on a confirmed page;
    # the others' source claims are `_NA_` and relations touching them are not stored
    run_dir, bound, instrument = e._setup(tmp_path)
    extra = e.Builder(run_dir, bound, instrument, A)
    extra.page("p1", [e.Q1])
    extra.page("p2", [e.Q2])
    for oid, pid, quote in (("o1", "p1", e.Q1), ("o2", "p2", e.Q2)):
        extra.observation(oid, pid, name="Copilot drafting", activity_type="internal_operational", tool="Copilot",
                          quote=quote)
    extra.page("p9", ["A vendor mentions an unnamed assistant."])
    sid = extra.observation("o9", "p9", name="Unnamed assistant", activity_type="pilot_experiment", tool="Gizmo",
                            quote="A vendor mentions an unnamed assistant.", verdict="ambiguous_attribution")
    inst = extra.institution({("o1", "o2"): dict(extra.inputs["o1"].row["values"])})
    assert _run(run_dir, bound, instrument, [inst], e.FakeQuotes()).written == [A]
    storage = _storage(run_dir)
    acts = storage["activities"]
    assert all("o9" not in act["observation_ids"] for act in acts.values())
    assert storage["sources"][sid]["activity_id"] == "_NA_"
    rels = [r for act in acts.values() for r in act["activity_relations"]]
    assert rels and all("o9" not in (r["lhs_observation_id"], r["rhs_observation_id"]) for r in rels)


@pytest.mark.parametrize("groups, expected", [({"S1": "g1", "S2": "g2"}, "high"), ({"S1": "g1", "S2": "g1"}, "medium")])
def test_activity_confidence_reads_every_source_claim_of_the_activity(tmp_path, groups, expected):
    # X3 a (ii): two medium claims; independent -> high, one group -> medium (both claims counted)
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    for sid in ("S1", "S2"):
        a.sources[sid]["values"]["core.confidence"] = "medium"
    a = replace(a, independence_groups={**a.independence_groups, **groups})
    assert _run(run_dir, bound, instrument, [a], e.FakeQuotes()).written == [A]
    merged = next(x for x in _storage(run_dir)["activities"].values() if x["observation_ids"] == ["o1", "o2"])
    assert merged["values"]["core.n_sources"] == 2 and merged["values"]["core.confidence"] == expected


class OutsideQuotes(e.FakeQuotes):
    """Copies a shown quote's words but names an input that was not shown in the request part."""

    def __call__(self, req):
        self.calls += 1
        return s6.Stage6Quote(req.candidates[0].quote_text, "not-shown-here", e.TRUE, {"fake": True})


def test_quote_copied_from_outside_its_part_is_stored_without_text_and_kept_in_provenance(tmp_path):
    # X3 a (iii)
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    assert _run(run_dir, bound, instrument, [a], OutsideQuotes()).written == [A]
    storage = _storage(run_dir)
    assert sorted(tuple(x["observation_ids"]) for x in storage["activities"].values()) == [("o1",), ("o2",), ("o3",),
                                                                                              ("o4",)]
    prov = json.loads((institution_dir(run_dir, A) / adapters.PROVENANCE_ARTIFACT).read_text(encoding="utf-8"))
    rejected = [r for r in prov["records"] if r.get("rejected_quote")]
    assert rejected and all(r["rejected_quote"] == e.Q1 for r in rejected)
    nodes = {n["support_id"]: n for x in storage["activities"].values() for n in x["item_support"]}
    for r in rejected:
        assert nodes[r["support_id"]]["supporting_text"] == ""


@pytest.mark.parametrize("field, match", [("independence_groups", "independence"),
                                          ("uncertainty_flags", "uncertainty")])
def test_absent_independence_groups_or_uncertainty_flags_refuse(tmp_path, field, match):
    # X4 a: explicit inputs, refused when absent (no producer yet)
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    metrics = _run(run_dir, bound, instrument, [replace(a, **{field: None})], e.FakeQuotes())
    assert metrics.failed == [A] and not metrics.written
    held = _held(run_dir)
    assert held["reasons"] == [rt.ENVELOPE_FAILED] and "MissingUpstreamError" in held["error"]
    assert match in held["error"].lower()


# --- RC-D-030 Z1 b: a failed pooled request part holds the question; the next run retries ----------


def test_z1_failed_pooled_request_holds_institution_then_retry_publishes(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)
    inner = e.FakeJev(e.RELATIONS, e._pooled_answers())

    def failing(state, questions):
        if s6.RELATION_ITEM not in questions and "core.action_type" in questions:
            raise RuntimeError("simulated pooled request failure")
        return inner(state, questions)
    metrics = _run(run_dir, bound, instrument, [a], e.FakeQuotes(), jev=failing)
    assert metrics.held == [A] and not metrics.written
    held = _held(run_dir)
    assert s6.POOLED_REQUEST_FAILED in held["reasons"]
    assert any(h["reason"] == s6.POOLED_REQUEST_FAILED for h in held["held"])
    assert f"{rt.HELD_REASON}:{s6.POOLED_REQUEST_FAILED}" in _ledger(run_dir)
    assert not (institution_dir(run_dir, A) / "6_storage.json").exists()  # never published
    metrics = _run(run_dir, bound, instrument, [a], e.FakeQuotes())
    assert metrics.written == [A]
    assert rt.HELD_RELEASED in _ledger(run_dir)


# --- RC-D-030 Z2 a: pooled role-part gate reaches storage --------------------------------------


@pytest.mark.parametrize("relationship,role", [("unresolved", "not_asked"), ("other", "beneficiary")])
def test_z2_pooled_role_part_gate_stores(tmp_path, relationship, role):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    answers = {**e._pooled_answers(), "core.observed_actor_relationship": relationship,
               "core.observed_actor_relationship#searched_institution_role": "beneficiary"}
    metrics = _run(run_dir, bound, instrument, [a], e.FakeQuotes(), jev=e.FakeJev(e.RELATIONS, answers))
    assert metrics.written == [A], _held(run_dir) if metrics.held or metrics.failed else None
    storage = json.loads((institution_dir(run_dir, A) / "6_storage.json").read_text(encoding="utf-8"))
    merged = next(x for x in storage["activities"].values() if x["observation_ids"] == ["o1", "o2"])
    value = merged["values"]["core.observed_actor_relationship"]
    assert value["relationship"] == relationship and value["searched_institution_role"] == role
