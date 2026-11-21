"""Calibration FN-TRACE defects 3 and 4: within-page pairs that make Stage 6 hold an institution.

Both are distilled from journal-only replays of real calibration units (synthetic pages; no page text
from the units). The mocked path is the T-030 e2e path of ``test_e2e_perpage_v27``.

Defect 3 (cal-0271): two within-page pairs that share their lhs activity, e.g. (A1, A2) and (A1, A3),
both choose the same relation in the same page part with no quote. Their stored support nodes have
the same complete support key (item, part, value, observation, source, chunk, passage; the linked
activity is not part of it), so the per-page producer keeps one node but emits two provenance
companions, which differ in ``chosen_answer_probability``. ``build_envelope`` then refuses with
"conflicting provenance for support ...", and the institution is held on every later run.

Defect 4 (cal-0311): two activities whose spans start at the same character (the extractor split one
passage by actor). T-023 used to stop that pair (RC-D-024 row 8), so no within-page decision existed and
Stage 6 held the institution on ``missing_relation_decision`` on every run.

PI rulings on the session-3 defect report (chat 2026-11-20, "all accepted"): Def3 D3-A (the pair partner
is part of the stored pair node, so each pair has its own support id) and Def4 D4-C (a deterministic
tie-break, then the pair question is asked once, as for any other pair; the order is recorded as coming
from the tie-break).
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from g3o.classify import jev_activity_code as jac
from g3o.common.jev_client import JevAnswer
from g3o.common.paths import institution_dir
from g3o.common.instrument import load_instrument
from g3o.common.storage import StorageEnvelope
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.run.presweep.instrument_binding import bind_runtime
from tests.test_e2e_perpage_v27 import (  # noqa: F401 - _paragraph_layout is an autouse fixture
    ANSWERS,
    CLOCK,
    RELATIONS,
    SETTINGS,
    FakeJev,
    FakeQuotes,
    Page,
    World,
    _paragraph_layout,
)

INST = "INST-0000009"
S1 = "The council deployed Copilot for drafting letters in 2025."
S2 = "A public chatbot answers resident questions about bins."
S3 = "The council adopted a policy that governs chatbot use."
SEGMENT = "core.activity_segment"
LINKED_OBSERVATION = "linked_observation_id"  # passage member of a stored pair node (D3-A)


class PairJev(FakeJev):
    """FakeJev whose pair answer is ``distinct_action`` with a probability that depends on the linked
    activity (as cal-0271: 0.91 and 0.88 for two pairs of the same lhs)."""

    def __init__(self, probability_by_linked):
        super().__init__({**ANSWERS, SEGMENT: "distinct_action"}, RELATIONS)
        self.probability_by_linked = probability_by_linked

    def __call__(self, state, questions):
        res = super().__call__(state, questions)
        if SEGMENT in res.answers:
            p = self.probability_by_linked[state["linked_activity"]]
            answers = dict(res.answers)
            answers[SEGMENT] = JevAnswer(SEGMENT, "choice", choice="distinct_action", confidence=p,
                                         probabilities={"distinct_action": p})
            res = replace(res, answers=answers)
        return res


def _run(tmp_path, page, jev, withhold=()):
    run_dir = tmp_path / "run"
    bound = bind_runtime(run_dir, SETTINGS)
    instrument = load_instrument(run_dir / "final" / "instruments", bound.instrument_id)
    world = World(run_dir, bound, instrument, [page], withhold=set(withhold))
    insts = [world.institution(INST)]
    jev.log = world.log
    ready, metrics = pp.run_perpage_v27(run_dir, insts, ask_fn=jev, providers=world.providers(),
                                        page_config=bound.page_config, activity_config=bound.activity_config,
                                        instrument=instrument, test_only_unbound_providers=True)
    s6m = rt.run_stage6_v27(run_dir, ready, ask_fn=jev, quote_fn=FakeQuotes(), config=bound.stage6_config(),
                            instrument=instrument, now=CLOCK, test_only_unbound_quote_fn=True)
    return run_dir, ready, metrics, s6m


def _held(run_dir):
    path = institution_dir(run_dir, INST) / rt.WORK_DIR / rt.HELD_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _shared_lhs_page():
    # One paragraph per activity, so (A1, A2) and (A1, A3) are both asked in A1's part q#p0.
    return Page(INST, "q", [S1, S2, S3], [("a1", "Copilot drafting", "Copilot", S1, None),
                                          ("a2", "Resident chatbot", "Binbot", S2, None),
                                          ("a3", "Chatbot policy", "Policy", S3, None)])


def _no_pair_quotes(page_id, parts):
    return {(page_id, aid, SEGMENT, f"{page_id}#p{i}") for aid in ("a1", "a2", "a3") for i in range(parts)}


def _storage(run_dir):
    return json.loads((institution_dir(run_dir, INST) / "6_storage.json").read_text(encoding="utf-8"))


def _reload(run_dir, data):
    instrument = load_instrument(run_dir / "final" / "instruments", data["setup_pointer"])
    return StorageEnvelope(data, instrument, artifact_root=run_dir)


def _pair_nodes(data):
    return [s for row in data["activities"].values() for s in row["item_support"]
            if s["item_id"] == SEGMENT and LINKED_OBSERVATION in s["passage"]]


def test_defect3_two_pairs_sharing_an_lhs_get_distinct_support_ids(tmp_path):
    """D3-A: each pair's A1-part node names its partner observation, so the two pairs' nodes have
    different support ids, and each coder record names the node of its own pair (cal-0271 had one id)."""
    page = _shared_lhs_page()
    jev = PairJev({"A2": 0.91, "A3": 0.88})
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev, _no_pair_quotes("q", 3))
    assert metrics.ready == [INST]
    inst = ready[0]
    oid = pp.observation_id("q", "a1")
    row = inst.observation_inputs[oid].row
    seg = [c for c in row["coder_records"]
           if c["item_id"] == SEGMENT and c["chunk_id"] == "q#p0" and c["chosen_value"] == "distinct_action"]
    assert sorted(c["chosen_answer_probability"] for c in seg) == [0.88, 0.91]  # two coder records ...
    assert len({c["support_id"] for c in seg}) == 2  # ... naming two stored nodes
    nodes = {s["support_id"]: s for s in row["item_support"]}
    linked = {nodes[c["support_id"]]["passage"][LINKED_OBSERVATION]: c["chosen_answer_probability"] for c in seg}
    assert linked == {pp.observation_id("q", "a2"): 0.91, pp.observation_id("q", "a3"): 0.88}
    ids = [s["support_id"] for s in row["item_support"]]
    assert len(ids) == len(set(ids))


def test_defect3_two_pairs_sharing_an_lhs_do_not_hold_the_institution(tmp_path):
    """cal-0271: Stage 6 must publish the institution; today it raises ConsolidationError
    'conflicting provenance for support ...' and holds it (stage6_envelope_failed)."""
    page = _shared_lhs_page()
    jev = PairJev({"A2": 0.91, "A3": 0.88})
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev, _no_pair_quotes("q", 3))
    assert metrics.ready == [INST]
    assert _held(run_dir) is None, _held(run_dir)
    assert s6m.written == [INST] and not s6m.held
    data = _storage(run_dir)
    relations = [r for row in data["activities"].values() for r in row["activity_relations"]
                 if r["relation_scope"] == "within_page"]
    assert len(relations) == 3
    supports = {s["support_id"]: s for row in data["activities"].values() for s in row["item_support"]}
    for rel in relations:  # every pair node a relation names belongs to that relation's pair
        for sid in rel["support_ids"]:
            passage = supports[sid]["passage"]
            if LINKED_OBSERVATION in passage:
                assert {supports[sid]["observation_id"], passage[LINKED_OBSERVATION]} == {
                    rel["lhs_observation_id"], rel["rhs_observation_id"]}


def test_defect3_storage_refuses_a_relation_naming_another_pairs_node(tmp_path):
    """The stored pair node is pair-keyed: a within-page relation may name only its own pair's nodes."""
    page = _shared_lhs_page()
    run_dir, *_ = _run(tmp_path, page, PairJev({"A2": 0.91, "A3": 0.88}), _no_pair_quotes("q", 3))
    data = _storage(run_dir)
    _reload(run_dir, data)  # the stored envelope validates as written
    rels = {(r["lhs_observation_id"], r["rhs_observation_id"]): r
            for row in data["activities"].values() for r in row["activity_relations"]}
    a1, a2, a3 = (pp.observation_id("q", a) for a in ("a1", "a2", "a3"))
    rels[(a1, a2)]["support_ids"] = list(rels[(a1, a3)]["support_ids"])
    with pytest.raises(ValueError, match="pair support names another pair"):
        _reload(run_dir, data)


def test_defect3_storage_requires_the_partner_on_a_pair_node_only(tmp_path):
    page = _shared_lhs_page()
    run_dir, *_ = _run(tmp_path, page, PairJev({"A2": 0.91, "A3": 0.88}), _no_pair_quotes("q", 3))
    data = _storage(run_dir)
    node = _pair_nodes(data)[0]
    del node["passage"][LINKED_OBSERVATION]
    with pytest.raises(ValueError, match="names its linked observation"):
        _reload(run_dir, data)
    data = _storage(run_dir)
    node = _pair_nodes(data)[0]
    node["passage"][LINKED_OBSERVATION] = node["observation_id"]
    with pytest.raises(ValueError, match="cannot link its own observation"):
        _reload(run_dir, data)
    data = _storage(run_dir)
    other = next(s for row in data["activities"].values() for s in row["item_support"]
                 if s["item_id"] != SEGMENT and "quote_segment" in s["passage"])
    other["passage"][LINKED_OBSERVATION] = pp.observation_id("q", "a2")
    with pytest.raises(ValueError, match="only a within-page pair support"):
        _reload(run_dir, data)


def test_defect3_equal_probabilities_already_publish(tmp_path):
    """Control: with equal probabilities the two companions are identical and Stage 6 publishes, so the
    hold in the test above depends only on the probability difference (as the trace found)."""
    page = _shared_lhs_page()
    jev = PairJev({"A2": 0.9, "A3": 0.9})
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev, _no_pair_quotes("q", 3))
    assert _held(run_dir) is None
    assert s6m.written == [INST]


def _equal_start_page(order=("a1", "a2")):
    acts = {"a1": ("a1", "Copilot drafting", "Copilot", S1, None),
            "a2": ("a2", "Copilot drafting", "Copilot", S1, None)}
    return Page(INST, "t", [S1, S2], [acts[a] for a in order])


def _activity_doc(run_dir, page):
    return json.loads((institution_dir(run_dir, INST) / pp.WORK_DIR / pp.url_hash(page.url) / "activity.json")
                      .read_text(encoding="utf-8"))


def test_defect4_equal_span_start_pair_is_tie_broken_and_asked_once(tmp_path):
    """cal-0311, D4-C: two activities on the same passage (split by actor) tie on span start. T-023
    orders the pair by activity id (the observation ids of one page differ only in it), records that
    the order came from the tie-break, and asks the pair question once; Stage 6 publishes."""
    page = _equal_start_page()
    jev = FakeJev({**ANSWERS, SEGMENT: "distinct_action"}, RELATIONS)
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev)
    doc = _activity_doc(run_dir, page)
    assert doc["result"]["notes"] == [f"{jac.PAIR_DIRECTION_TIE_BREAK}:a1:a2"]
    assert [(p["activity_id"], p["linked_activity"]) for p in doc["result"]["pairs"]] == [("a1", "a2")]
    asked = [c for c in jev.calls if SEGMENT in c[1]]
    assert len(asked) == 1  # one pair, one part, one direction
    assert (asked[0][0]["activity"], asked[0][0]["linked_activity"]) == ("A1", "A2")
    assert _held(run_dir) is None, _held(run_dir)
    assert s6m.written == [INST] and not s6m.held
    rels = [(r["lhs_observation_id"], r["rhs_observation_id"], r["relation"])
            for row in _storage(run_dir)["activities"].values() for r in row["activity_relations"]]
    assert rels == [(pp.observation_id("t", "a1"), pp.observation_id("t", "a2"), "distinct_action")]


def test_defect4_tie_break_does_not_depend_on_input_order(tmp_path):
    page = _equal_start_page(order=("a2", "a1"))
    jev = FakeJev({**ANSWERS, SEGMENT: "distinct_action"}, RELATIONS)
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev)
    doc = _activity_doc(run_dir, page)
    assert doc["result"]["notes"] == [f"{jac.PAIR_DIRECTION_TIE_BREAK}:a1:a2"]
    assert [(p["activity_id"], p["linked_activity"]) for p in doc["result"]["pairs"]] == [("a1", "a2")]
    assert s6m.written == [INST]
