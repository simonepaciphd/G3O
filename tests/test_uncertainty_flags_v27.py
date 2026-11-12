"""v2.7 per-code uncertainty flags (T-024 derived field; PI A6.1-A6.4 a, 2026-11-11)."""
from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from g3o.common.part_combine import NOT_COVERED
from g3o.common.paths import institution_dir
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import SupportResult
from g3o.persist.stage6_adapters import MissingUpstreamError
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.validate import uncertainty_flags_v27 as uf
from tests import test_e2e_perpage_v27 as ep
from tests import test_e2e_stage6_v27 as e

_paragraph_layout = ep._paragraph_layout  # the per-page e2e's autouse paragraph layout

NC = NOT_COVERED


def _sr(item, value):
    return SupportResult(item_id=item, part=None, activity_id="a1", chunk_id="c0", original_value=value,
                         value=value, support_status="not_required", support_status_second_reason=None,
                         support_rule_name=None, supporting_text=None, quote_chunk_id=None, match=None,
                         chosen_answer_probability=0.9, entailment=None)


def _rec(item, value, coder_type="classifier"):
    return SimpleNamespace(item_id=item, chosen_value=value, coder_type=coder_type)


# --- the producer (pure) ----------------------------------------------------------------------------


def test_signed_list_is_the_two_kept_flags_alphabetical():
    assert uf.SIGNED_FLAGS == ("identity_unresolved", "stage_ambiguous")
    assert list(uf.SIGNED_FLAGS) == sorted(uf.SIGNED_FLAGS)


def test_a61_stage_ambiguous_when_answers_differ_before_combining():
    assert uf.stage_ambiguous(["pilot", "production"])
    # Ruling 1 b (2026-11-11): missing answers are ignored; only conflicting stated stages flag.
    assert uf.STAGE_MISSING == {"not_asked", "not_documented", "unknown", "_NA_"}
    for missing in sorted(uf.STAGE_MISSING):
        assert not uf.stage_ambiguous(["pilot", missing])
    assert not uf.stage_ambiguous(["not_documented", "unknown"])
    assert uf.stage_ambiguous(["pilot", "unknown", "production"])
    assert not uf.stage_ambiguous(["pilot", "pilot"])
    assert not uf.stage_ambiguous(["pilot", NC, NC])  # the temporary part answer never votes
    assert not uf.stage_ambiguous(["pilot"]) and not uf.stage_ambiguous([])


def test_a61_answers_are_classifier_records_of_the_stage_item_without_not_covered():
    records = [_rec(uf.STAGE_ITEM, "pilot"), _rec(uf.STAGE_ITEM, NC), _rec("core.activity_type", "x"),
               _rec(uf.STAGE_ITEM, "production", coder_type="mechanical")]
    assert uf.classifier_answers(records) == ["pilot"]


def test_a62_identity_unresolved_only_for_an_unresolved_stage6_relation():
    assert uf.code_flags(_sr(uf.STAGE6_RELATION_ITEM, "unresolved")) == ["identity_unresolved"]
    assert uf.code_flags(_sr(uf.STAGE6_RELATION_ITEM, "same_activity")) == []
    # the within-page relation is a pass-2 per-page item, not a Stage 6 relation
    assert uf.code_flags(_sr("core.activity_segment", "unresolved")) == []


def test_a63_a_node_carries_only_its_own_codes_flags():
    differ = ["pilot", "production"]
    assert uf.code_flags(_sr(uf.STAGE_ITEM, "pilot"), stage_answers=differ) == ["stage_ambiguous"]
    assert uf.code_flags(_sr(uf.STAGE_ITEM, "pilot"), stage_answers=["pilot"]) == []
    # another item of the same ambiguous activity carries nothing
    assert uf.code_flags(_sr("core.activity_type", "internal_operational"), stage_answers=differ) == []
    assert uf.code_flags(_sr("core.observed_actor_relationship", "unresolved"), stage_answers=differ) == []


def test_a64_union_alphabetical_and_outside_flags_refused():
    assert uf.union_flags([["stage_ambiguous"], [], ["identity_unresolved", "stage_ambiguous"]]) == [
        "identity_unresolved", "stage_ambiguous"]
    assert uf.union_flags([]) == []
    nodes = [{"uncertainty_flags": ["stage_ambiguous"]}, {"uncertainty_flags": []}]
    assert uf.row_flags(nodes) == uf.row_flags(list(reversed(nodes))) == ["stage_ambiguous"]
    with pytest.raises(ValueError, match="outside the signed"):
        uf.union_flags([["vendor_undisclosed"]])  # a v2.5 flag is not in the v2.7 list


def test_r1a_identity_unresolved_row_flag_follows_the_filed_relation_not_the_node():
    """R1 a: a stored relation node's identity_unresolved is not a row flag by itself; the row
    holding the unresolved cross-page relation (its lhs) carries it, with or without the node."""
    rel = {"uncertainty_flags": ["identity_unresolved"]}
    stage = {"uncertainty_flags": ["stage_ambiguous"]}
    assert uf.row_flags([rel]) == []  # node stored here, relation filed elsewhere
    assert uf.row_flags([rel, stage]) == ["stage_ambiguous"]
    assert uf.row_flags([], unresolved_relation=True) == ["identity_unresolved"]  # node stored elsewhere
    assert uf.row_flags([rel, stage], unresolved_relation=True) == ["identity_unresolved", "stage_ambiguous"]


def test_unruled_ai_text_flags_stay_refused():
    with pytest.raises(MissingUpstreamError, match="AI-text"):
        uf.check_pipeline("ai_text")
    uf.check_pipeline(pp.PIPELINE)  # web_extract: both signed flags are ruled


def test_pooled_answers_are_the_observations_values_then_the_pool_parts():
    inst = SimpleNamespace(observation_inputs={
        "o1": SimpleNamespace(row={"values": {uf.STAGE_ITEM: "pilot"}}),
        "o2": SimpleNamespace(row={"values": {uf.STAGE_ITEM: "production"}})})
    pooled = SimpleNamespace(observation_ids=("o1", "o2"), records=(_rec(uf.STAGE_ITEM, "pilot"),
                                                                    _rec(uf.STAGE_ITEM, NC)))
    assert rt.pooled_stage_answers(inst, pooled) == ["pilot", "production", "pilot"]


def test_merge_split_derives_the_flags_and_no_longer_takes_them_as_input():
    assert rt.MERGE_DERIVED == ("core.uncertainty_flags",) and rt.MERGE_UNRULED == ()
    assert "core.uncertainty_flags" not in rt.MERGE_INPUT_ITEMS
    assert not hasattr(pp.InstitutionUpstream(), "uncertainty_flags")


# --- per page (A6.1 parts, A6.3) --------------------------------------------------------------------


def _perpage_b2(tmp_path, stage):
    run_dir, bound, instrument, world, insts = ep._setup(tmp_path)
    answers = {**ep.ANSWERS, "core.adoption_stage": ep._by_name({"Copilot drafting": "pilot", "Eval bot": stage})}
    b = [i for i in insts if i.institution_id == "INST-0000002"]
    ready, metrics = ep._perpage(run_dir, bound, instrument, world, b, ep.FakeJev(answers, ep.RELATIONS))
    assert metrics.ready == ["INST-0000002"], metrics
    return ready[0].observation_inputs[pp.observation_id("b2", "a1")].row


def _stage_nodes(row):
    return [n for n in row["item_support"] if n["item_id"] == uf.STAGE_ITEM]


def test_perpage_parts_that_differ_flag_the_stage_nodes_and_the_row(tmp_path):
    row = _perpage_b2(tmp_path, {"1": "pilot", "2": "production", "3": NC})
    assert row["values"]["core.uncertainty_flags"] == ["stage_ambiguous"]
    stage = _stage_nodes(row)
    assert len(stage) >= 2 and all(n["uncertainty_flags"] == ["stage_ambiguous"] for n in stage)
    assert all(n["uncertainty_flags"] == [] for n in row["item_support"] if n["item_id"] != uf.STAGE_ITEM)


def test_perpage_same_answer_and_not_covered_parts_set_no_flag(tmp_path):
    row = _perpage_b2(tmp_path, {"1": "pilot", "2": "pilot", "3": NC})
    assert row["values"]["core.uncertainty_flags"] == []
    assert all(n["uncertainty_flags"] == [] for n in row["item_support"])


def test_perpage_stated_and_missing_parts_set_no_flag(tmp_path):
    """Ruling 1 b: a stated stage beside a missing answer is not a conflict."""
    row = _perpage_b2(tmp_path, {"1": "pilot", "2": "not_documented", "3": NC})
    assert row["values"]["core.uncertainty_flags"] == []
    assert all(n["uncertainty_flags"] == [] for n in row["item_support"])


def test_perpage_refuses_an_upstream_flag_value(tmp_path):
    run_dir, bound, instrument, world, insts = ep._setup(tmp_path)
    a = next(i for i in insts if i.institution_id == "INST-0000001")
    up = a.pages[0].upstream
    vals = {k: {**v, "core.uncertainty_flags": []} for k, v in up.activity_values.items()}
    spec = replace(a.pages[0], upstream=replace(up, activity_values=vals))
    ready, metrics = ep._perpage(run_dir, bound, instrument, world, [replace(a, pages=[spec, *a.pages[1:]])],
                                 ep.FakeJev(ep.ANSWERS, ep.RELATIONS))
    assert metrics.held == ["INST-0000001"] and not ready
    held = json.loads((institution_dir(run_dir, "INST-0000001") / pp.WORK_DIR / pp.HELD_FILE)
                      .read_text(encoding="utf-8"))
    assert "core.uncertainty_flags" in held["held"][0]["error"]


# --- Stage 6 (A6.1 pooled, A6.2, A6.4) ----------------------------------------------------------------


def _storage(run_dir, inst="INST-0000001"):
    return json.loads((institution_dir(run_dir, inst) / "6_storage.json").read_text(encoding="utf-8"))


def _pooled_run(tmp_path, pooled_stage):
    run_dir, bound, instrument = e._setup(tmp_path)
    insts = e._institutions(run_dir, bound, instrument)
    answers = e._pooled_answers()
    qid = next(q for q, v in answers.items() if v == e.POOLED["core.adoption_stage"])
    jev = e.FakeJev(e.RELATIONS, {**answers, qid: pooled_stage})
    _, metrics = e._run(run_dir, bound, instrument, insts, e.FakeQuotes(), jev=jev)
    assert metrics.written == ["INST-0000001", "INST-0000002"]
    acts = _storage(run_dir)["activities"]
    return next(a for a in acts.values() if a["observation_ids"] == ["o1", "o2"]), acts


def test_stage6_pooled_answer_differing_from_the_observations_flags_the_merged_row(tmp_path):
    obs_stage = FIELDS[uf.STAGE_ITEM]["codes"][0]  # the declared fixture value of o1 and o2
    other = next(c for c in FIELDS[uf.STAGE_ITEM]["codes"] if c != obs_stage)
    merged, acts = _pooled_run(tmp_path, other)
    pooled_stage = [n for n in merged["item_support"] if n["item_id"] == uf.STAGE_ITEM and n["observation_id"] is None]
    assert pooled_stage and all(n["uncertainty_flags"] == ["stage_ambiguous"] for n in pooled_stage)
    assert merged["values"]["core.uncertainty_flags"] == ["stage_ambiguous"]  # A6.4: union of its nodes
    assert all(a["values"]["core.uncertainty_flags"] == [] for a in acts.values() if a is not merged)


def test_stage6_pooled_answer_equal_to_the_observations_sets_no_flag(tmp_path):
    merged, acts = _pooled_run(tmp_path, FIELDS[uf.STAGE_ITEM]["codes"][0])
    assert all(n["uncertainty_flags"] == [] for n in merged["item_support"])
    assert all(a["values"]["core.uncertainty_flags"] == [] for a in acts.values())


def test_stage6_unresolved_relation_flags_its_node_and_the_activity_holding_it(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    b = e.Builder(run_dir, bound, instrument, "INST-0000001")
    b.page("p1", [e.Q1])
    b.page("p2", [e.Q2])
    b.observation("o1", "p1", name="Copilot drafting", activity_type="internal_operational", tool="Copilot", quote=e.Q1)
    b.observation("o2", "p2", name="Copilot letters", activity_type="internal_operational", tool="Copilot", quote=e.Q2)
    jev = e.FakeJev({("Copilot drafting", "Copilot letters"): "unresolved"}, {})
    _, metrics = e._run(run_dir, bound, instrument, [b.institution()], e.FakeQuotes(), jev=jev)
    assert metrics.written == ["INST-0000001"], metrics
    acts = {tuple(a["observation_ids"]): a for a in _storage(run_dir)["activities"].values()}
    assert set(acts) == {("o1",), ("o2",)}  # unresolved never merges
    rel = [n for n in acts[("o1",)]["item_support"] if n["item_id"] == uf.STAGE6_RELATION_ITEM]
    assert rel and all(n["uncertainty_flags"] == ["identity_unresolved"] for n in rel)
    assert all(n["input_support_ids"] == [] for n in rel)  # signed: unresolved needs no quote
    assert acts[("o1",)]["values"]["core.uncertainty_flags"] == ["identity_unresolved"]
    assert all(n["uncertainty_flags"] == [] for n in acts[("o1",)]["item_support"]
               if n["item_id"] != uf.STAGE6_RELATION_ITEM)
    assert acts[("o2",)]["values"]["core.uncertainty_flags"] == []  # the node lives on the lhs row only


class _LastQuotes(e.FakeQuotes):
    """Copies the LAST shown input verbatim: a relation quote copied from the right-hand record."""

    def __call__(self, req):
        self.calls += 1
        last = req.candidates[-1]
        return e.s6.Stage6Quote(last.quote_text, last.support_id, e.TRUE, {"fake": True})


def _quoted_unresolved(monkeypatch):
    """Make an ``unresolved`` relation answer go through the quote step.

    Under the signed codebook ``unresolved`` needs no quote (support ``not_required``; the quote step
    is never called), so its node always sits on the lhs. To exercise R1 a for a quoted relation, the
    check runs as for a quoted relation value (``governs``) and keeps the answer ``unresolved``.
    """
    real = e.s6.check_code

    def check(ev, sources):
        if ev.item_id == uf.STAGE6_RELATION_ITEM and ev.value == uf.UNRESOLVED:
            sr = real(replace(ev, value="governs"), sources)
            return replace(sr, value=uf.UNRESOLVED, original_value=uf.UNRESOLVED)
        return real(ev, sources)

    monkeypatch.setattr(e.s6, "check_code", check)


def test_stage6_r1a_flag_on_the_lhs_row_when_the_relation_quote_comes_from_the_rhs(tmp_path, monkeypatch):
    """R1 a: the quote is copied from o2 (rhs), so W4 b stores the relation node on o2's row with its
    own flag (A6.3 a); the row flag goes on o1's row, where the relation is filed, and only there."""
    _quoted_unresolved(monkeypatch)
    run_dir, bound, instrument = e._setup(tmp_path)
    b = e.Builder(run_dir, bound, instrument, "INST-0000001")
    b.page("p1", [e.Q1])
    b.page("p2", [e.Q2])
    b.observation("o1", "p1", name="Copilot drafting", activity_type="internal_operational", tool="Copilot", quote=e.Q1)
    b.observation("o2", "p2", name="Copilot letters", activity_type="internal_operational", tool="Copilot", quote=e.Q2)
    jev = e.FakeJev({("Copilot drafting", "Copilot letters"): "unresolved"}, {})
    quotes = _LastQuotes()
    _, metrics = e._run(run_dir, bound, instrument, [b.institution()], quotes, jev=jev)
    assert metrics.written == ["INST-0000001"], metrics
    assert quotes.calls == 1
    acts = {tuple(a["observation_ids"]): a for a in _storage(run_dir)["activities"].values()}
    assert set(acts) == {("o1",), ("o2",)}
    lhs, rhs = acts[("o1",)], acts[("o2",)]
    rel = [n for n in rhs["item_support"] if n["item_id"] == uf.STAGE6_RELATION_ITEM]
    assert rel and any(n["supporting_text"] == e.Q2 for n in rel)  # W4 b: stored with the copied record
    assert all(n["uncertainty_flags"] == ["identity_unresolved"] for n in rel)  # the node keeps its flag
    assert not [n for n in lhs["item_support"] if n["item_id"] == uf.STAGE6_RELATION_ITEM]
    assert [r["relation"] for r in lhs["activity_relations"]] == ["unresolved"] and not rhs["activity_relations"]
    assert lhs["values"]["core.uncertainty_flags"] == ["identity_unresolved"]  # filed here (R1 a)
    assert rhs["values"]["core.uncertainty_flags"] == []
