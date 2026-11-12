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
from g3o.common.independence import group_id as independence_group_id
from g3o.common.instrument import canonical_json, sha256_text
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


def _unbound(quote_fn):
    """Offline fakes opt out of the bound-quote-step check; a bound step is checked for real."""
    return not getattr(quote_fn, "bound_instrument_id", None)


def _run(run_dir, bound, instrument, insts, quote_fn, *, config=None, jev=None):
    jev = jev or e.FakeJev(e.RELATIONS, e._pooled_answers())
    return rt.run_stage6_v27(run_dir, insts, ask_fn=jev, quote_fn=quote_fn, config=config or bound.stage6_config(),
                             instrument=instrument, now=e.CLOCK, test_only_unbound_quote_fn=_unbound(quote_fn))


def _held(run_dir, inst=A):
    return json.loads((institution_dir(run_dir, inst) / rt.WORK_DIR / rt.HELD_FILE).read_text(encoding="utf-8"))


def _ledger(run_dir, inst=A):
    return [r["reason"] for r in attrition.read_records(run_dir) if r["institution_id"] == inst]


def _merge_input(obs_input):
    """Declared fixture: the merged values with no rule computable from the merged row (RC-D-030 X1)."""
    return {k: v for k, v in obs_input.row["values"].items() if k in rt.MERGE_INPUT_ITEMS}


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
    return a, a.institution({("o1", "o2"): _merge_input(a.inputs["o1"])})


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
    first = _run(run_dir, bound, instrument, insts[:1], bound.stage6_quote_fn(ext1, ent1, x35_model="fake-x35"))
    assert first.held == [A] and len(ext1.jobs) == 1
    ext2, ent2 = FakeExtractor(), FakeEntail()
    second = _run(run_dir, bound, instrument, insts[:1], bound.stage6_quote_fn(ext2, ent2, x35_model="fake-x35"))
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
                bound.stage6_quote_fn(ext, FakeEntail(), x35_model="fake-x35")).written == [A]
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
    inst = extra.institution({("o1", "o2"): _merge_input(extra.inputs["o1"])})
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


@pytest.mark.parametrize("same, expected", [(False, "high"), (True, "medium")])
def test_independence_groups_produced_from_source_rows_when_not_injected(tmp_path, same, expected):
    # PI A7.1 b / A7.2 a: no injected groups -> produced from syndication group + normalised URL
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    for sid in a.sources:
        a.sources[sid]["values"]["core.syndication_group"] = f"sg-{sid}"
    for sid in ("S1", "S2"):
        a.sources[sid]["values"]["core.confidence"] = "medium"
    if same:
        a.sources["S2"]["values"]["core.syndication_group"] = "sg-S1"
    a = replace(a, independence_groups=None)
    assert _run(run_dir, bound, instrument, [a], e.FakeQuotes()).written == [A]
    merged = next(x for x in _storage(run_dir)["activities"].values() if x["observation_ids"] == ["o1", "o2"])
    assert merged["values"]["core.n_sources"] == 2 and merged["values"]["core.confidence"] == expected


def test_independence_groups_refused_when_a_syndication_group_is_missing(tmp_path):
    # A7.2 a: no URL-only fallback; the fixture rows' syndication group is a missing token
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    assert a.sources["S1"]["values"]["core.syndication_group"] == "not_documented"
    metrics = _run(run_dir, bound, instrument, [replace(a, independence_groups=None)], e.FakeQuotes())
    assert metrics.failed == [A] and not metrics.written
    held = _held(run_dir)
    assert "MissingUpstreamError" in held["error"] and "core.syndication_group" in held["error"]


@pytest.mark.parametrize("joined, expected", [(False, "high"), (True, "medium")])
def test_independence_groups_join_through_a_source_the_activity_does_not_cite(tmp_path, joined, expected):
    # PI ruling A7 12 a: groups span all of the institution's source rows. The merged activity
    # (o1, o2) cites S1 and S2, which share no key; S3 and S4 (cited by o3 / o4) share the p3 URL.
    # With S3 sharing S1's syndication group and S4 sharing S2's, S1..S4 are one group.
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    syn = {"S1": "sg-A", "S2": "sg-B", "S3": "sg-A", "S4": "sg-B"} if joined else         {"S1": "sg-A", "S2": "sg-B", "S3": "sg-C", "S4": "sg-D"}
    for sid, gid in syn.items():
        a.sources[sid]["values"]["core.syndication_group"] = gid
    for sid in ("S1", "S2"):
        a.sources[sid]["values"]["core.confidence"] = "medium"
    a = replace(a, independence_groups=None)
    groups = rt.independence_groups_of(a)
    assert (groups["S1"] == groups["S2"]) is joined
    assert groups["S3"] == groups["S4"]
    # PI ruling A7 27 (2026-11-12): the producer hashes this institution's id into the ig- id
    members = ["S1", "S2", "S3", "S4"] if joined else ["S3", "S4"]
    assert groups["S3"] == independence_group_id(a.institution_id, members)
    assert _run(run_dir, bound, instrument, [a], e.FakeQuotes()).written == [A]
    merged = next(x for x in _storage(run_dir)["activities"].values() if x["observation_ids"] == ["o1", "o2"])
    assert merged["values"]["core.n_sources"] == 2 and merged["values"]["core.confidence"] == expected


def test_injected_independence_groups_win_over_the_producer(tmp_path):
    # PI ruling A7 14: an injected mapping is used as given. The producer would put S1 and S2 in
    # different groups (-> high); the injected mapping joins them (-> medium).
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    for sid in a.sources:
        a.sources[sid]["values"]["core.syndication_group"] = f"sg-{sid}"
    for sid in ("S1", "S2"):
        a.sources[sid]["values"]["core.confidence"] = "medium"
    produced = rt.independence_groups_of(replace(a, independence_groups=None))
    assert produced["S1"] != produced["S2"]
    a = replace(a, independence_groups={sid: "g-same" for sid in a.sources})
    assert _run(run_dir, bound, instrument, [a], e.FakeQuotes()).written == [A]
    merged = next(x for x in _storage(run_dir)["activities"].values() if x["observation_ids"] == ["o1", "o2"])
    assert merged["values"]["core.confidence"] == "medium"


def test_independence_groups_refused_when_no_activity_is_published(tmp_path):
    # PI ruling A7 13 a: one source with no syndication group holds the whole institution, even
    # when the institution has source rows but no publishable activity.
    run_dir, bound, instrument = e._setup(tmp_path)
    b = e.Builder(run_dir, bound, instrument, B)
    b.page("q9", ["A vendor mentions an unnamed assistant."])
    sid = b.observation("n9", "q9", name="Unnamed assistant", activity_type="pilot_experiment", tool="Gizmo",
                        quote="A vendor mentions an unnamed assistant.", verdict="ambiguous_attribution")
    assert b.sources[sid]["values"]["core.syndication_group"] == "not_documented"
    injected = b.institution()
    metrics = _run(run_dir, bound, instrument, [replace(injected, independence_groups=None)], e.FakeQuotes())
    assert metrics.failed == [B] and not metrics.written
    held = _held(run_dir, B)
    assert held["reasons"] == [rt.ENVELOPE_FAILED]
    assert "MissingUpstreamError" in held["error"] and "core.syndication_group" in held["error"]
    # Control (ruling 14): with the injected mapping the same institution publishes, with no activity row.
    assert _run(run_dir, bound, instrument, [injected], e.FakeQuotes()).written == [B]
    assert not _storage(run_dir, B)["activities"]


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


@pytest.mark.parametrize("field, match", [("independence_groups", "independence")])
def test_absent_independence_groups_refuse(tmp_path, field, match):
    # X4 a: explicit inputs, refused when absent (no producer yet); uncertainty flags are produced (A6)
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


# --- RC-D-030 X1 a: merge rule for a merged activity's non-pooled values ------------------------


def _merge_inst(rows, confidence):
    from types import SimpleNamespace
    inputs = {k: rt.ObservationInput(k, f"S-{k}", {"values": v}) for k, v in rows.items()}
    sources = {f"S-{k}": {"values": {"core.confidence": confidence[k]}} for k in rows}
    return SimpleNamespace(observation_inputs=inputs, sources=sources)


def _row(**over):
    base = {"core.tool_name": [], "core.model_name": "not_documented", "core.reported_outcomes": [],
            "core.reported_incidents": "not_asked", "core.activity_name": "not_documented",
            "core.contracting_party": "not_documented", "core.observed_actor_name": "not_documented",
            "core.deployment_scale_number": "not_documented"}
    return {**base, **over}


def test_x1_r2_union_drops_trim_casefold_duplicates_keeping_first_spelling_in_pool_order():
    inst = _merge_inst({"o1": _row(**{"core.tool_name": ["Copilot ", "ChatGPT"]}),
                        "o2": _row(**{"core.tool_name": ["copilot", "Gemini", "chatgpt"]})},
                       {"o1": "low", "o2": "high"})
    out = rt.merge_values(inst, ["o2", "o1"])
    assert out["core.tool_name"] == ["copilot", "Gemini", "chatgpt"]
    out = rt.merge_values(inst, ["o1", "o2"])
    assert out["core.tool_name"] == ["Copilot ", "ChatGPT", "Gemini"]
    assert out["core.model_name"] == "not_documented"  # no entries, same token everywhere
    assert out["core.reported_outcomes"] == []


def test_rcd032_b3_r2_no_entries_and_differing_values_take_the_most_credible_observations_value():
    rows = {"o1": _row(), "o2": _row(**{"core.reported_outcomes": "not_documented"})}
    assert rt.merge_values(_merge_inst(rows, {"o1": "low", "o2": "high"}), ["o1", "o2"])[
        "core.reported_outcomes"] == "not_documented"
    assert rt.merge_values(_merge_inst(rows, {"o1": "high", "o2": "unknown"}), ["o1", "o2"])[
        "core.reported_outcomes"] == []
    tie = _merge_inst(rows, {"o1": "medium", "o2": "medium"})  # tie: pool order
    assert rt.merge_values(tie, ["o2", "o1"])["core.reported_outcomes"] == "not_documented"
    assert rt.merge_values(tie, ["o1", "o2"])["core.reported_outcomes"] == []


def test_rcd032_b2_scale_number_follows_r3():
    from g3o.common.storage_fields import FIELDS
    schema = FIELDS["core.deployment_scale_number"]["schema"]  # signed: a number or a missing token
    assert schema["anyOf"][0] == {"type": "number"}
    tokens = schema["anyOf"][1]["enum"]
    inst = _merge_inst({"o1": _row(), "o2": _row(**{"core.deployment_scale_number": 200}),
                        "o3": _row(**{"core.deployment_scale_number": 50})},
                       {"o1": "high", "o2": "low", "o3": "medium"})
    for row in inst.observation_inputs.values():
        v = row.row["values"]["core.deployment_scale_number"]
        assert (isinstance(v, int | float) and not isinstance(v, bool)) or v in tokens
    assert rt.merge_values(inst, ["o1", "o2", "o3"])["core.deployment_scale_number"] == 50  # medium > low
    # a higher-credibility missing token never wins over a lower-credibility number
    inst = _merge_inst({"o1": _row(), "o2": _row(**{"core.deployment_scale_number": 200})},
                       {"o1": "high", "o2": "low"})
    assert rt.merge_values(inst, ["o1", "o2"])["core.deployment_scale_number"] == 200
    inst = _merge_inst({"o1": _row(**{"core.deployment_scale_number": 0}),
                        "o2": _row(**{"core.deployment_scale_number": 7.5})}, {"o1": "low", "o2": "high"})
    assert rt.merge_values(inst, ["o1", "o2"])["core.deployment_scale_number"] == 7.5  # both real: credibility
    inst = _merge_inst({"o1": _row(), "o2": _row(**{"core.deployment_scale_number": "unknown"})},
                       {"o1": "low", "o2": "high"})
    assert rt.merge_values(inst, ["o1", "o2"])["core.deployment_scale_number"] == "unknown"  # all missing: R3 first
    inst = _merge_inst({"o1": _row(), "o2": _row(**{"core.deployment_scale_number": "about 200"})},
                       {"o1": "high", "o2": "low"})  # lexical number text (what storage validates) is real too
    assert rt.merge_values(inst, ["o1", "o2"])["core.deployment_scale_number"] == "about 200"
    assert "core.deployment_scale_number" in rt.MERGE_CREDIBLE
    assert rt.MERGE_UNRULED == () and rt.MERGE_DERIVED == ("core.uncertainty_flags",)


def test_r3_blank_text_is_missing_and_a_zero_number_is_real():
    inst = _merge_inst({"o1": _row(**{"core.activity_name": "  ", "core.deployment_scale_number": "_NA_"}),
                        "o2": _row(**{"core.activity_name": "Copilot", "core.deployment_scale_number": 0})},
                       {"o1": "high", "o2": "low"})
    out = rt.merge_values(inst, ["o1", "o2"])
    assert out["core.activity_name"] == "Copilot" and out["core.deployment_scale_number"] == 0


def test_x1_r3_most_credible_source_wins_ties_by_pool_order_empty_never_wins():
    rows = {"o1": _row(**{"core.activity_name": "Drafting pilot", "core.contracting_party": "Acme"}),
            "o2": _row(**{"core.activity_name": "Copilot drafting"}),
            "o3": _row(**{"core.activity_name": "Copilot rollout", "core.observed_actor_name": "IT unit"})}
    inst = _merge_inst(rows, {"o1": "unknown", "o2": "medium", "o3": "medium"})
    out = rt.merge_values(inst, ["o1", "o2", "o3"])
    assert out["core.activity_name"] == "Copilot drafting"  # medium beats unknown (= low); o2 before o3
    assert out["core.contracting_party"] == "Acme"  # only real value, though least credible
    assert out["core.observed_actor_name"] == "IT unit"
    out = rt.merge_values(inst, ["o3", "o2", "o1"])
    assert out["core.activity_name"] == "Copilot rollout"  # tie at medium: pool order decides


def test_x1_merged_input_is_narrowed_to_the_refused_and_unruled_items(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)
    group = next(iter(a.merged_values))
    full = dict(a.observation_inputs["o1"].row["values"])  # names items merged by rule: refused
    metrics = _run(run_dir, bound, instrument, [replace(a, merged_values={group: full})], e.FakeQuotes())
    assert metrics.failed == [A] and "merged by rule or pooled" in _held(run_dir)["error"]
    assert set(rt.MERGE_INPUT_ITEMS) == {*rt.MERGE_REFUSED_R1, *rt.MERGE_UNRULED}
    assert "core.evidence_channel" not in rt.MERGE_INPUT_ITEMS


def test_x1_merged_row_values_reach_storage(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    rows = {k: dict(a.observation_inputs[k].row) for k in ("o1", "o2")}
    metrics = _run(run_dir, bound, instrument, [a], e.FakeQuotes())
    assert metrics.written == [A]
    storage = json.loads((institution_dir(run_dir, A) / "6_storage.json").read_text(encoding="utf-8"))
    merged = next(x for x in storage["activities"].values() if x["observation_ids"] == ["o1", "o2"])
    order = s6.observation_pool_order(a.quotes, ["o1", "o2"])
    expect = rt.merge_values(a, order)
    assert {k: merged["values"][k] for k in expect} == expect
    for item in rt.MERGE_UNION:  # each entry keeps its own observation's support node
        for entry in merged["values"][item] if isinstance(merged["values"][item], list) else ():
            assert any(n["item_id"] == item and n["value_json"] == entry and n["observation_id"] in rows
                       for n in merged["item_support"])


# --- QA round 2, HIGH-A: an unconfirmed merged group follows X3 a (i); executor errors are per institution


def _unconfirmed_merged(run_dir, bound, instrument):
    x = e.Builder(run_dir, bound, instrument, A)
    x.page("p1", [e.Q1])
    x.page("p2", [e.Q2])
    sids = [x.observation(oid, pid, name="Copilot drafting", activity_type="internal_operational", tool="Copilot",
                          quote=q, verdict="ambiguous_attribution")
            for oid, pid, q in (("o1", "p1", e.Q1), ("o2", "p2", e.Q2))]
    return x.institution({("o1", "o2"): _merge_input(x.inputs["o1"])}), sids


def test_unconfirmed_merged_group_is_no_activity_row_and_publishes(tmp_path):
    # X3 a (i): a merged group with no supported observation on a confirmed page is not pooled,
    # gets no activity row, its source claims are `_NA_` (observation ids kept), its relations unstored
    run_dir, bound, instrument = e._setup(tmp_path)
    inst, sids = _unconfirmed_merged(run_dir, bound, instrument)
    jev = e.FakeJev(e.RELATIONS, e._pooled_answers())
    metrics = _run(run_dir, bound, instrument, [inst], e.FakeQuotes(), jev=jev)
    assert metrics.written == [A] and not metrics.failed and not metrics.held
    assert all(s6.RELATION_ITEM in q for q in jev.calls)  # relations asked; nothing pooled
    storage = _storage(run_dir)
    assert storage["activities"] == {}
    for sid, oid in zip(sids, ("o1", "o2"), strict=True):
        assert storage["sources"][sid]["activity_id"] == "_NA_"
        assert storage["sources"][sid]["observation_ids"] == [oid]


def test_executor_error_holds_that_institution_and_later_institutions_continue(tmp_path, monkeypatch):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)
    real = rt.run_stage6

    def flaky(**kw):
        if kw["institution"].endswith(A):
            raise rt.ConsolidationError("simulated executor refusal")
        return real(**kw)
    monkeypatch.setattr(rt, "run_stage6", flaky)
    metrics = _run(run_dir, bound, instrument, [a, b], e.FakeQuotes())
    assert metrics.failed == [A] and metrics.written == [B]
    held = _held(run_dir)
    assert held["reasons"] == [rt.EXECUTOR_FAILED]
    assert "ConsolidationError: simulated executor refusal" in held["error"]
    assert _ledger(run_dir) == [rt.EXECUTOR_FAILED]
    assert A in metrics.usage  # the journal is still accounted


def test_executor_stop_errors_still_stop_the_stage(tmp_path, monkeypatch):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)

    def stopped(**kw):
        raise rt.JevAccountError("account stopped")
    monkeypatch.setattr(rt, "run_stage6", stopped)
    with pytest.raises(rt.JevAccountError):
        _run(run_dir, bound, instrument, [a, b], e.FakeQuotes())


@pytest.mark.parametrize("error", [TypeError, KeyError, AttributeError])
def test_executor_programming_error_stops_the_stage_and_is_not_held(tmp_path, monkeypatch, error):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)

    def broken(**kw):
        raise error("simulated programming error")
    monkeypatch.setattr(rt, "run_stage6", broken)
    with pytest.raises(error):
        _run(run_dir, bound, instrument, [a, b], e.FakeQuotes())
    assert not (institution_dir(run_dir, A) / rt.WORK_DIR / rt.HELD_FILE).exists()


def test_executor_missing_upstream_is_still_held_per_institution(tmp_path, monkeypatch):
    # Stage 6 keeps holding MissingUpstreamError per institution; its treatment awaits a PI ruling.
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)
    real = rt.run_stage6

    def missing(**kw):
        if kw["institution"].endswith(A):
            raise rt.MissingUpstreamError("simulated producer", ["x"])
        return real(**kw)
    monkeypatch.setattr(rt, "run_stage6", missing)
    assert rt.MissingUpstreamError not in rt.STAGE_STOPS
    metrics = _run(run_dir, bound, instrument, [a, b], e.FakeQuotes())
    assert metrics.failed == [A] and metrics.written == [B]
    held = _held(run_dir)
    assert held["reasons"] == [rt.EXECUTOR_FAILED] and "MissingUpstreamError" in held["error"]


# --- QA round 2, MEDIUM-B: Z1 b retry is live; a response missing an asked answer is never replayed


class MissingOnce(e.FakeJev):
    """Omits the answer to ``omit`` (the request id is still returned): a billed, incomplete response."""

    def __init__(self, relations, answers, omit):
        super().__init__(relations, answers)
        self.omit = omit

    def __call__(self, state, questions):
        r = super().__call__(state, questions)
        if self.omit in r.answers:
            answers = {k: v for k, v in r.answers.items() if k != self.omit}
            return JevResult(answers, r.response_model, r.request_id, r.input_tokens, r.output_tokens)
        return r


def _qid(item):
    from g3o.classify.questions.v27 import load_set
    return next(q["question_id"] for q in load_set("activity")["questions"] if q["item_id"] == item)


@pytest.mark.parametrize("omit", ["pooled", "relation"])
def test_z1_answer_missing_is_retried_live_on_the_next_run_and_publishes(tmp_path, omit):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    qid = _qid("core.adoption_stage") if omit == "pooled" else s6.RELATION_ITEM
    first = _run(run_dir, bound, instrument, [a], e.FakeQuotes(),
                 jev=MissingOnce(e.RELATIONS, e._pooled_answers(), qid))
    assert first.held == [A] and not first.written
    reason = s6.POOLED_REQUEST_FAILED if omit == "pooled" else s6.ANSWER_MISSING
    assert reason in _held(run_dir)["reasons"]
    usage = rt.RequestJournal(institution_dir(run_dir, A) / rt.WORK_DIR / rt.JOURNAL).usage()
    assert usage["jev_incomplete"] >= 1 and usage["input_tokens"] > 0  # billed: accounted, not replayable
    jev2 = e.FakeJev(e.RELATIONS, e._pooled_answers())
    second = _run(run_dir, bound, instrument, [a], e.FakeQuotes(), jev=jev2)
    assert second.written == [A], _held(run_dir)
    assert any(qid in q for q in jev2.calls)  # the held question was asked again, live
    assert rt.HELD_RELEASED in _ledger(run_dir)


def test_journal_never_replays_a_response_missing_an_asked_answer(tmp_path):
    path, calls = tmp_path / "journal.jsonl", []

    def partial(state, questions):
        calls.append(state)
        return _answer(state, {})  # answers "Q" only

    journal = rt.RequestJournal(path, retry_incomplete=True)
    journal.ask(partial)({"s": 1}, {"Q": {}, "R": {}})
    again = rt.RequestJournal(path, retry_incomplete=True)
    again.ask(partial)({"s": 1}, {"Q": {}, "R": {}})
    assert len(calls) == 2 and again.replayed == 0
    assert again.usage()["jev_incomplete"] == 2 and again.usage()["jev_responses"] == 0


def test_journal_replays_a_response_missing_an_asked_answer_unless_opted_in(tmp_path):
    # The Z1 b no-replay rule is Stage 6's; the shared journal's default (per-page) replays it.
    path, calls = tmp_path / "journal.jsonl", []

    def partial(state, questions):
        calls.append(state)
        return _answer(state, {})  # answers "Q" only

    first = rt.RequestJournal(path).ask(partial)({"s": 1}, {"Q": {}, "R": {}})
    again = rt.RequestJournal(path)
    replayed = again.ask(partial)({"s": 1}, {"Q": {}, "R": {}})
    assert len(calls) == 1 and again.replayed == 1 and replayed == first
    assert again.usage()["jev_incomplete"] == 0 and again.usage()["jev_responses"] == 1


# --- QA round 2, LOW-F: the quote step is bound to the instrument; schema pinned; X35 model keyed


def test_quote_output_schema_is_pinned_in_the_instrument(tmp_path):
    _, _, instrument = e._setup(tmp_path)
    conf = instrument["payload"]["extractor_configuration"]
    assert conf["stage6_quote_schema_sha256"] == sha256_text(canonical_json(sq.output_schema()))


def test_unbound_quote_fn_is_refused_unless_the_test_only_flag_is_set(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    jev = e.FakeJev(e.RELATIONS, e._pooled_answers())
    other = replace(bound.stage6_quote_fn(FakeExtractor(), FakeEntail(), x35_model="fake-x35"),
                    bound_instrument_id="0" * 64)
    unbound = sq.make_quote_fn(FakeExtractor(), FakeEntail())  # pinned text, but not bound
    for fn in (e.FakeQuotes(), unbound, other):
        with pytest.raises(ValueError, match="not bound to this instrument"):
            rt.run_stage6_v27(run_dir, [a], ask_fn=jev, quote_fn=fn, config=bound.stage6_config(),
                              instrument=instrument, now=e.CLOCK)
    assert not jev.calls
    with pytest.raises(ValueError, match="x35_model"):
        bound.stage6_quote_fn(FakeExtractor(), FakeEntail(), x35_model=" ")
    metrics = rt.run_stage6_v27(run_dir, [a], ask_fn=jev, config=bound.stage6_config(), instrument=instrument,
                                now=e.CLOCK, quote_fn=bound.stage6_quote_fn(FakeExtractor(), FakeEntail(),
                                                                           x35_model="fake-x35"))
    assert metrics.written == [A]


def test_x35_answers_are_not_replayed_under_another_x35_model(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    first = FakeEntail()
    _run(run_dir, bound, instrument, [a], bound.stage6_quote_fn(FakeExtractor(), first, x35_model="fake-x35"),
         jev=e.FakeJev(e.RELATIONS, {}))  # held or written: the X35 answers are journaled
    assert first.calls
    for name in ("6_validate.json", "6_storage.json", "6_support_provenance.json"):
        (institution_dir(run_dir, A) / name).unlink(missing_ok=True)
    same, other = FakeEntail(), FakeEntail()
    _run(run_dir, bound, instrument, [a], bound.stage6_quote_fn(FakeExtractor(), same, x35_model="fake-x35"),
         jev=e.FakeJev(e.RELATIONS, {}))
    assert not same.calls  # replayed under the same X35 model
    for name in ("6_validate.json", "6_storage.json", "6_support_provenance.json"):
        (institution_dir(run_dir, A) / name).unlink(missing_ok=True)
    with pytest.raises(ValueError, match="pinned in the instrument"):  # RC-D-033 C1 a
        bound.stage6_quote_fn(FakeExtractor(), other, x35_model="x35-b")
    swapped = replace(bound.stage6_quote_fn(FakeExtractor(), other, x35_model="fake-x35"), x35_model="x35-b")
    with pytest.raises(ValueError, match="X35 model differs"):
        rt.run_stage6_v27(run_dir, [a], ask_fn=e.FakeJev(e.RELATIONS, {}), quote_fn=swapped,
                          config=bound.stage6_config(), instrument=instrument, now=e.CLOCK)
    assert not other.calls
    # the journal still keys on the X35 model (defence in depth): a test-only step on another model asks again
    rt.run_stage6_v27(run_dir, [a], ask_fn=e.FakeJev(e.RELATIONS, {}), quote_fn=swapped,
                      config=bound.stage6_config(), instrument=instrument, now=e.CLOCK,
                      test_only_unbound_quote_fn=True)
    assert len(other.calls) == len(first.calls)  # another X35 model: asked again


# --- RC-D-032 B5 a: a copied relation (X30) original may source a final downgrade node ------------


class LowRelation(e.FakeJev):
    """The cross-page relation is answered below the 0.8 bar (downgraded for low confidence)."""

    def __call__(self, state, questions):
        r = super().__call__(state, questions)
        if s6.RELATION_ITEM not in r.answers:
            return r
        a = r.answers[s6.RELATION_ITEM]
        low = JevAnswer(a.question_id, "choice", choice=a.choice, confidence=0.5, probabilities={a.choice: 0.5})
        return JevResult({**r.answers, s6.RELATION_ITEM: low}, r.response_model, r.request_id, r.input_tokens,
                         r.output_tokens)


def test_rcd032_b5_relation_quote_copied_then_downgraded_for_low_confidence_stores(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    metrics = _run(run_dir, bound, instrument, [a], e.FakeQuotes(), jev=LowRelation(e.RELATIONS, e._pooled_answers()))
    assert metrics.written == [A], _held(run_dir)
    storage = _storage(run_dir)
    nodes = {n["support_id"]: n for x in storage["activities"].values() for n in x["item_support"]}
    finals = [n for n in nodes.values() if n["item_id"] == s6.RELATION_ITEM
              and n["support_status"] == "downgraded_low_confidence" and n["passage"].get("downgrade_of")]
    assert finals
    for final in finals:
        (original_id,) = final["input_support_ids"]
        original = nodes[original_id]
        assert original["supporting_text"] and len(original["input_support_ids"]) == 1  # names its copied input
    assert sorted(tuple(x["observation_ids"]) for x in storage["activities"].values()) == [("o1",), ("o2",), ("o3",),
                                                                                              ("o4",)]


def test_rcd032_b5_only_copied_relation_originals_may_name_inputs():
    from g3o.common.jev_record import downgrade_source_original
    rel = {"source_id": None, "observation_id": None, "item_id": s6.RELATION_ITEM, "input_support_ids": ["x"],
           "supporting_text": "copied words", "passage": {"quote_source_id": "S1"}}
    assert downgrade_source_original(rel)
    assert not downgrade_source_original({**rel, "input_support_ids": ["x", "y"]})  # not one copied input
    assert not downgrade_source_original({**rel, "supporting_text": ""})
    assert not downgrade_source_original({**rel, "passage": {"quote_source_id": None}})
    assert not downgrade_source_original({**rel, "observation_id": "o1"})
    assert not downgrade_source_original({**rel, "source_id": "S1"})


# --- QA round 3, F5: a relation quote whose segment is not in the named input (RC-D-029 X3 a iii)


def _segment_outside_input(inst, oid):
    """The named input's quote segment is held by none of its stored parts (the quote step names
    the input, but the segment it was matched on is outside it)."""
    def moved(q):
        return replace(q, quote_chunk_id=q.producing_chunk_id + "#outside") if q.observation_id == oid else q
    records = [replace(r, quotes=tuple(moved(q) for q in r.quotes)) for r in inst.records]
    return replace(inst, quotes=[moved(q) for q in inst.quotes], records=records)


def test_f5_relation_quote_outside_its_named_input_is_stored_with_no_supporting_text(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    a = _segment_outside_input(a, "o1")  # FakeQuotes copies o1's quote for the (o1, o2) relation
    metrics = _run(run_dir, bound, instrument, [a], e.FakeQuotes())
    assert metrics.written == [A], _held(run_dir)
    storage = _storage(run_dir)
    nodes = {n["support_id"]: n for x in storage["activities"].values() for n in x["item_support"]}
    rel = [n for n in nodes.values() if n["item_id"] == s6.RELATION_ITEM and not n["passage"].get("downgrade_of")]
    assert rel
    original = next(n for n in rel if n["observation_id"] == "o1")
    # X3 a iii: no supporting text, placed as an unquoted relation's original (names no inputs)
    assert original["supporting_text"] == "" and original["input_support_ids"] == []
    assert original["support_status"] != "supported"
    finals = [n for n in nodes.values() if n["passage"].get("downgrade_of") == original["support_id"]]
    assert finals  # the downgrade final is stored from it
    provenance = json.loads((institution_dir(run_dir, A) / "6_support_provenance.json").read_text(encoding="utf-8"))
    records = provenance["records"] if isinstance(provenance, dict) else provenance
    companion = next(r for r in records if r["support_id"] == original["support_id"])
    assert companion["rejected_quote"]  # the rejected copy is kept in provenance only
