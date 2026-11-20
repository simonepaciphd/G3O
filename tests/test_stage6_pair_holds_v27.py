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
passage by actor). T-023 stops that pair (RC-D-024 row 8: "Equal-start case not resolved; stop affected
pair rather than pick direction"), so no within-page decision exists and Stage 6 holds the institution
on ``missing_relation_decision``. That is the ruled behaviour; the test pins it until a ruling says
what Stage 6 should do with a stopped pair.
"""
from __future__ import annotations

import json
from dataclasses import replace

from g3o.common.jev_client import JevAnswer
from g3o.common.paths import institution_dir
from g3o.common.instrument import load_instrument
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


def test_defect3_two_pairs_sharing_an_lhs_collide_on_one_support_key(tmp_path):
    """Root cause, from records (cal-0271 probe): the two pairs' A1-part nodes have one support_id.
    Characterises the current key; whatever the fix, this documents what collides."""
    page = _shared_lhs_page()
    jev = PairJev({"A2": 0.91, "A3": 0.88})
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev, _no_pair_quotes("q", 3))
    assert metrics.ready == [INST]
    inst = ready[0]
    oid = pp.observation_id("q", "a1")
    seg = [c for c in inst.observation_inputs[oid].row["coder_records"]
           if c["item_id"] == SEGMENT and c["chunk_id"] == "q#p0" and c["chosen_value"] == "distinct_action"]
    assert sorted(c["chosen_answer_probability"] for c in seg) == [0.88, 0.91]  # two coder records ...
    assert len({c["support_id"] for c in seg}) == 1  # ... naming one stored node


def test_defect3_two_pairs_sharing_an_lhs_do_not_hold_the_institution(tmp_path):
    """cal-0271: Stage 6 must publish the institution; today it raises ConsolidationError
    'conflicting provenance for support ...' and holds it (stage6_envelope_failed)."""
    page = _shared_lhs_page()
    jev = PairJev({"A2": 0.91, "A3": 0.88})
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev, _no_pair_quotes("q", 3))
    assert metrics.ready == [INST]
    assert _held(run_dir) is None, _held(run_dir)
    assert s6m.written == [INST] and not s6m.held


def test_defect3_equal_probabilities_already_publish(tmp_path):
    """Control: with equal probabilities the two companions are identical and Stage 6 publishes, so the
    hold in the test above depends only on the probability difference (as the trace found)."""
    page = _shared_lhs_page()
    jev = PairJev({"A2": 0.9, "A3": 0.9})
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev, _no_pair_quotes("q", 3))
    assert _held(run_dir) is None
    assert s6m.written == [INST]


def test_defect4_equal_span_start_pair_is_stopped_and_stage6_holds(tmp_path):
    """cal-0311 (ruled behaviour, RC-D-024 row 8): two activities on the same passage (split by actor)
    tie on span start; T-023 notes pair_direction_tie and codes no pair, and Stage 6 holds the
    institution on missing_relation_decision. A re-run reproduces the same tie, so the hold is
    permanent unless a ruling decides what a stopped pair becomes."""
    page = Page(INST, "t", [S1, S2], [("a1", "Copilot drafting", "Copilot", S1, None),
                                      ("a2", "Copilot drafting", "Copilot", S1, None)])
    jev = FakeJev({**ANSWERS, SEGMENT: "distinct_action"}, RELATIONS)
    run_dir, ready, metrics, s6m = _run(tmp_path, page, jev)
    doc = json.loads((institution_dir(run_dir, INST) / pp.WORK_DIR / pp.url_hash(page.url) / "activity.json")
                     .read_text(encoding="utf-8"))
    assert doc["result"]["notes"] == ["pair_direction_tie:a1:a2"]
    assert doc["result"]["pairs"] == []
    assert not [c for c in jev.calls if SEGMENT in c[1]]  # the stopped pair is never asked
    held = _held(run_dir)
    assert held is not None and held["reasons"] == [rt.MISSING_RELATION]
    assert held["missing_pairs"] == [[pp.observation_id("t", "a1"), pp.observation_id("t", "a2")]]
    assert s6m.held == [INST]
