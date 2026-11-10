"""T-023 pass-2 activity coder: mocked jev, mocked part combiner (RULINGS 2.14)."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

import pytest

from g3o.classify import jev_activity_code as jac
from g3o.classify.questions.v27 import load_set
from g3o.codebook.loader import default_codebook_path
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import load_classifier_rules
from g3o.common.page_chunks import Chunk
from g3o.extract.parser_v27 import ActivitySpan, FieldValue
from g3o.extract.pass2_support import select_requests
from g3o.extract.request_v27 import Pass1Page

SHA = "7972b8c1989af5e182c19d9d73c4ab20cb2440b06c7be33dff1701071658123b"
SETUP = "a" * 64
QSET = load_set("activity")
RULES = load_classifier_rules(default_codebook_path().read_bytes(), expected_sha256=QSET["codebook_sha256"])
QS = {q["question_id"]: q for q in QSET["questions"]}
ROLE = "core.observed_actor_relationship#searched_institution_role"
REL = "core.observed_actor_relationship"


# --- mocks -----------------------------------------------------------------


@dataclass(frozen=True)
class FakeCombined:
    value: object
    part_id: str | None
    probability: float | None
    failed: bool = False
    cause: str | None = None


class FakeCombiner:
    """Stand-in for part_combine: highest-probability passing answer; failed -> unknown."""

    def __init__(self):
        self.calls = []

    def same_part_as(self, item_id):
        return None

    def combine(self, item_id, answers, *, reference=None):
        self.calls.append((item_id, tuple(answers)))
        real = [a for a in answers if a.value != jac.NOT_COVERED]
        ok = [a for a in real if not a.failed]
        if ok:
            best = max(ok, key=lambda a: (a.probability or 0, -a.part_index))
            return FakeCombined(best.value, best.part_id, best.probability)
        if real:
            return FakeCombined("unknown", real[0].part_id, None, True, real[0].cause)
        return FakeCombined("not_documented", None, None)


class FakeJev:
    """Answers every question: ``choices[qid]`` (default: the first offered code)."""

    def __init__(self, choices=None, prob=0.95, request_id="req", fail_parts=()):
        self.choices = choices or {}
        self.prob = prob
        self.request_id = request_id
        self.fail_parts = fail_parts
        self.requests = []
        self.n = 0

    def __call__(self, state, questions):
        self.requests.append((json.loads(json.dumps(state)), questions))
        self.n += 1
        if state["page_part"].split(" of ")[0] in self.fail_parts:
            return JevResult({}, "jev-x", None, 1, 1)
        answers = {}
        for qid, q in questions.items():
            pick = self.choices.get(qid)
            if callable(pick):
                pick = pick(state)
            pick = pick or next(iter(q["criteria"]))
            p = self.prob[qid] if isinstance(self.prob, dict) and qid in self.prob else (
                self.prob if not isinstance(self.prob, dict) else 0.95)
            probs = {c: (p if c == pick else (1 - p) / (len(q["criteria"]) - 1 or 1)) for c in q["criteria"]}
            answers[qid] = JevAnswer(qid, "choice", choice=pick, confidence=p, probabilities=probs)
        return JevResult(answers, "jev-x", f"{self.request_id}-{self.n}", 1, 1)


def make_page(text, cuts=None, spans=()):
    cuts = cuts or [len(text)]
    chunks, s = [], 0
    for i, e in enumerate(cuts):
        chunks.append(Chunk(f"p1:c{i}", "p1", s, e, text[s:e], 10))
        s = e
    page = Pass1Page("p1", "inst1", "City of Example", "https://ex.gov/a", "AI page", text,
                     tuple(chunks), (), "confirms_activity", None)
    return jac.ActivityPageInput(page, "Freedonia", "local", tuple(spans))


def span(aid, start, end, name="Chatbot", tool="ChatGPT", number=None):
    fields = [FieldValue("core.activity_name", name, "p1:c0", "NANO-SUPPORT-NAME"),
              FieldValue("core.tool_name", tool, "p1:c0", "NANO-SUPPORT-TOOL")]
    if number:
        fields.append(FieldValue("core.deployment_scale_number", number, "p1:c0", "NANO-SUPPORT-NUM"))
    return ActivitySpan(aid, "p1:c0", start, end, "resolved", "NANO-START-ANCHOR", "NANO-END-ANCHOR",
                        tuple(fields))


def config(combiner=None):
    return jac.ActivityCoderConfig(RULES, SETUP, "jev-configured", combiner or FakeCombiner(), 2026,
                                   question_set={**QSET, "pair_questions": []})


TEXT = ("Intro text. The city launched a chatbot pilot in 2024 for residents. "
        "Middle filler words here. The council adopted an AI policy in 2023. Outro.")
A1 = (TEXT.index("The city"), TEXT.index("residents.") + len("residents."))
A2 = (TEXT.index("The council"), TEXT.index("2023.") + len("2023."))

BASE = {"core.activity_type": "pilot_experiment", "core.action_type": "deployment",
        REL: "this_institution", ROLE: "contracting_authority"}


# --- tests -------------------------------------------------------------------


def test_setup_reads_v27_question_set():
    assert QSET["codebook_sha256"] == SHA
    s = jac._setup(config())
    assert s.rounds == (2, 3, 4, 5)
    assert all(q["item_id"] not in jac.PAIR_ITEMS for q in s.questions)


def test_two_activities_rounds_marks_and_no_nano_text():
    inp = make_page(TEXT, spans=[span("x1", *A1), span("x2", *A2, name="AI policy", tool="")])
    jev = FakeJev(BASE)
    res = jac.code_page(inp, jev, config())
    assert [a.label for a in res.activities] == ["A1", "A2"]
    assert len(jev.requests) == 8  # 2 activities x rounds 2..5, one part
    for state, _ in jev.requests:
        blob = json.dumps(state)
        for nano in ("NANO-START-ANCHOR", "NANO-END-ANCHOR", "NANO-SUPPORT"):
            assert nano not in blob  # card self-check: only span offsets + signed state fields
        extra = set(state) - {"coder_instructions", "institution", "country", "level_of_government",
                              "page_url", "page_title", "page_part", "page_text", "activity_name",
                              "tool_name", "stated_number"}
        names = {("searched_institution_role" if q.get("part") == "searched_institution_role"
                  else q["column"]) for q in QSET["questions"]}
        assert extra <= names  # every other field is an earlier-round answer
    first = jev.requests[0][0]
    assert first["page_text"].count("[[A1]]") == 1 and "[[/A1]]" in first["page_text"]
    assert "[[A2]]" not in first["page_text"]
    assert first["page_text"].replace("[[A1]]", "").replace("[[/A1]]", "") == TEXT
    assert "part_note" not in first and first["page_part"] == "1 of 1"
    a2_state = jev.requests[4][0]
    assert "[[A2]]" in a2_state["page_text"] and "[[A1]]" not in a2_state["page_text"]


def test_prior_answers_labels_order_and_missing_left_out():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    jev = FakeJev({**BASE, "core.genai_mechanism_basis": "not_documented"})
    jac.code_page(inp, jev, config())
    r3 = jev.requests[1][0]
    labels = jac.default_labels()
    assert r3["activity_type"] == labels["core.activity_type"]["values"]["pilot_experiment"]["text"]
    assert r3["searched_institution_role"] == (
        labels[REL]["parts"]["searched_institution_role"]["values"]["contracting_authority"]["text"])
    assert r3["observed_actor_relationship"] == (
        labels[REL]["parts"]["relationship"]["values"]["this_institution"]["text"])
    assert "genai_mechanism_basis" not in r3  # W3-2 a
    assert "activity_type" not in jev.requests[0][0]  # round 2 shows no earlier answers
    prior = [k for k in r3 if k in {"observed_actor_relationship", "searched_institution_role",
                                    "activity_type", "action_type", "observed_actor_role"}]
    assert prior == ["observed_actor_relationship", "searched_institution_role", "activity_type",
                     "action_type", "observed_actor_role"]  # activity.json order (A-3 a)


def test_multi_answer_label_list_in_codebook_order():
    labels = jac.default_labels()
    vals = list(labels["core.service_domain"]["values"])
    got = jac.value_label("core.service_domain", None, (vals[3], vals[0], "not_documented"), labels)
    assert got == [labels["core.service_domain"]["values"][vals[0]]["text"],
                   labels["core.service_domain"]["values"][vals[3]]["text"]]
    assert jac.value_label("core.year_announced", None, "2024", labels) == "2024"
    assert jac.value_label("core.activity_type", None, "unknown", labels) is None


def test_applicability_and_governance_gates():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    jev = FakeJev({**BASE, "core.activity_type": "policy_guidance"})
    res = jac.code_page(inp, jev, config())
    o = res.activities[0].outcomes
    assert o["core.model_origin"].state == "gated_out" and o["core.model_origin"].value == "not_asked"
    assert o["core.model_origin"].rule_reference == "gated_out:core.activity_type"
    assert o["core.governance_form"].state == "gated_out"  # action_type is not governance
    assert o["core.adoption_stage"].state == "combined"
    asked3 = set(jev.requests[1][1])
    assert "core.model_origin" not in asked3 and "core.governance_form" not in asked3
    mech = [r for r in res.activities[0].records if r.coder_type == "mechanical"]
    assert {r.item_id for r in mech} >= {"core.model_origin", "core.governance_form"}
    assert all(r.request_id is None and r.rule_reference.startswith("gated_out:") for r in mech)


def test_scale_unit_needs_stated_number():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, FakeJev(BASE), config())
    assert res.activities[0].outcomes["core.deployment_scale_unit"].state == "gated_out"
    inp = make_page(TEXT, spans=[span("x1", *A1, number="500 licences")])
    jev = FakeJev(BASE)
    res = jac.code_page(inp, jev, config())
    assert res.activities[0].outcomes["core.deployment_scale_unit"].state == "combined"
    r4 = jev.requests[2]
    assert "core.deployment_scale_unit" in r4[1] and r4[0]["stated_number"] == "500 licences"
    assert "stated_number" not in jev.requests[1][0]


def test_role_gate_after_combining():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, FakeJev({**BASE, REL: "unresolved"}), config())
    o = res.activities[0].outcomes[ROLE]
    assert o.state == "gated_out" and o.value == "not_asked"
    assert o.rule_reference == "gated_out:core.observed_actor_relationship"


def test_threshold_flags_through_coder_record():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, FakeJev(BASE, prob={"core.activity_type": 0.5}), config())
    recs = {r.question_id: r for r in res.activities[0].records if r.coder_type == "classifier"}
    assert recs["core.activity_type"].downgraded is True
    assert recs["core.activity_type"].downgrade_cause == "below_threshold"
    assert recs["core.action_type"].downgraded is False
    assert res.activities[0].outcomes["core.activity_type"].value == "unknown"  # failed vote
    assert all(r.configured_model == "jev-configured" and r.actual_response_model == "jev-x"
               for r in recs.values())


def test_multi_part_span_and_missing_request_id():
    cut = TEXT.index("pilot")
    inp = make_page(TEXT, cuts=[cut, len(TEXT)], spans=[span("x1", *A1)])
    jev = FakeJev(BASE, fail_parts=("2",))
    comb = FakeCombiner()
    res = jac.code_page(inp, jev, config(comb))
    a = res.activities[0]
    assert a.chunk_ids == ("p1:c0", "p1:c1") and a.part_indices == (1, 2)
    s1, s2 = jev.requests[0][0], jev.requests[1][0]
    assert s1["page_part"] == "1 of 2" and "part_note" in s1
    assert "[[A1]]" in s1["page_text"] and "[[/A1]]" not in s1["page_text"]
    assert "[[/A1]]" in s2["page_text"] and "[[A1]]" not in s2["page_text"]
    assert jac.NOT_COVERED in next(iter(jev.requests[0][1].values()))["criteria"]
    fails = [f for f in res.failures if f.reason == jac.MISSING_REQUEST_ID]
    assert fails and all(f.chunk_id == "p1:c1" for f in fails)
    assert all(r.request_id for r in a.records if r.coder_type == "classifier")
    assert all(r.chunk_id == "p1:c0" for r in a.records if r.coder_type == "classifier")
    item, votes = next(c for c in comb.calls if c[0] == "core.activity_type")
    assert [(v.part_id, v.failed, v.cause) for v in votes] == [
        ("p1:c0", False, None), ("p1:c1", True, jac.MISSING_REQUEST_ID)]


def test_request_exception_fails_part_only():
    def boom(state, questions):
        raise RuntimeError("timeout")
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, boom, config())
    assert {f.reason for f in res.failures} == {jac.REQUEST_FAILED}
    assert res.activities[0].outcomes["core.activity_type"].value == "unknown"


def test_unresolved_span_skipped_and_pair_note():
    bad = replace(span("x0", None, None), status="unresolved_start")
    inp = make_page(TEXT, spans=[bad, span("x1", *A1), span("x2", *A2)])
    res = jac.code_page(inp, FakeJev(BASE), config())
    assert res.skipped_activities == (("x0", jac.SPAN_UNRESOLVED),)
    assert [a.label for a in res.activities] == ["A1", "A2"]
    assert jac.PAIR_QUESTION_MISSING in res.notes


def test_year_candidates_window():
    page = make_page(TEXT).page
    years = jac.year_candidates(page, page.chunks[0], *A1, 2026)
    assert 2024 in years
    far = "x" * 300
    t = TEXT + far + " In 2019 something else."
    page = make_page(t).page
    assert 2019 not in jac.year_candidates(page, page.chunks[0], *A1, 2026)


@dataclass(frozen=True)
class Sup:
    item_id: str
    part: str | None
    activity_id: str | None
    chunk_id: str
    support_status: str


def _support(res, overrides=None):
    out = []
    for a in res.activities:
        for r in a.records:
            if r.coder_type == "classifier":
                st = (overrides or {}).get(r.question_id, "supported")
                out.append(Sup(r.item_id, r.item_part, a.activity_id, r.chunk_id, st))
    return out


def test_finalize_regates_after_support_downgrade():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, FakeJev({**BASE, "core.action_type": "governance"}), config())
    assert res.activities[0].outcomes["core.governance_form"].state == "combined"
    final = jac.finalize_activities(res, _support(res), config())
    assert final[0].outcomes["core.governance_form"].state == "combined"
    final = jac.finalize_activities(res, _support(res, {"core.action_type": "downgraded_no_quote"}),
                                    config())
    f = final[0]
    assert f.outcomes["core.action_type"].value == "unknown"
    assert f.outcomes["core.governance_form"].state == "gated_out"
    assert "core.governance_form" in f.regated
    assert any(r.question_id == "core.governance_form" for r in res.activities[0].records)  # raw kept


def test_finalize_flags_gate_opened():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, FakeJev({**BASE, "core.activity_type": "policy_guidance"}), config())
    f = jac.finalize_activities(res, _support(res, {"core.activity_type": "downgraded_no_quote"}),
                                config())[0]
    assert f.outcomes["core.activity_type"].value == "unknown"
    assert "core.model_origin" in f.gate_opened
    assert f.outcomes["core.model_origin"].state == "pending"
    assert f.outcomes["core.model_origin"].value is None


def test_finalize_requires_support_for_every_code():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, FakeJev(BASE), config())
    with pytest.raises(ValueError, match="no support result"):
        jac.finalize_activities(res, [], config())


def test_to_pass2_page_parts_and_links():
    inp = make_page(TEXT, spans=[span("x1", *A1), span("x2", *A2)])
    res = jac.code_page(inp, FakeJev(BASE), config())
    p2 = jac.to_pass2_page(res, inp)
    rel = [c for a in p2.activities for c in a.codes if c.item_id == REL]
    assert {c.part for c in rel} == {"relationship", "searched_institution_role"}
    plan = select_requests(p2)
    assert not [s for s in plan.skipped_codes if s.reason == "part_not_named"]
    # a pair record (p2c a) carries the other activity of its pair
    a1 = res.activities[0]
    linked = replace(a1, record_links={0: "x2"})
    res2 = replace(res, activities=(linked, res.activities[1]))
    codes = jac.to_pass2_page(res2, inp).activities[0].codes
    assert codes[0].linked_activity == "x2" and all(c.linked_activity is None for c in codes[1:])


def test_result_serialises():
    inp = make_page(TEXT, spans=[span("x1", *A1)])
    res = jac.code_page(inp, FakeJev(BASE), config())
    d = json.loads(json.dumps(res.to_dict()))
    assert d["activities"][0]["label"] == "A1" and d["question_set_version"] == QSET["question_set_version"]


def test_pair_direction_follows_span_not_input_label():
    inp = make_page(TEXT, spans=[span("later", *A2), span("earlier", *A1)])
    pairs, ties = jac.plan_pairs(inp)
    assert not ties and len(pairs) == 1
    pair = pairs[0]
    assert (pair.lhs.activity_id, pair.rhs.activity_id) == ("earlier", "later")
    assert (pair.lhs_label, pair.rhs_label) == ("A2", "A1")
    marked = jac.marked_pair_text(inp.page, inp.page.chunks[0], pair)
    assert marked.index("[[A2]]") < marked.index("[[A1]]")
    for mark in ("[[A1]]", "[[/A1]]", "[[A2]]", "[[/A2]]"):
        assert marked.count(mark) == 1
        marked = marked.replace(mark, "")
    assert marked == TEXT


def test_pair_parts_union_without_duplicates():
    cuts = [A1[1], A2[0], len(TEXT)]
    inp = make_page(TEXT, cuts=cuts, spans=[span("one", *A1), span("two", *A2)])
    pairs, _ = jac.plan_pairs(inp)
    assert [i for i, _ in pairs[0].parts] == [1, 3]
    first, last = (jac.marked_pair_text(inp.page, c, pairs[0]) for _, c in pairs[0].parts)
    assert "[[A1]]" in first and "[[A2]]" not in first
    assert "[[A2]]" in last and "[[A1]]" not in last


def test_pair_same_start_is_unresolved_and_other_pairs_continue():
    inp = make_page(TEXT, spans=[span("one", *A1), span("two", A1[0], A1[1]-1), span("three", *A2)])
    pairs, ties = jac.plan_pairs(inp)
    assert ties == (("one", "two"),)
    assert {(p.lhs.activity_id, p.rhs.activity_id) for p in pairs} == {("one", "three"), ("two", "three")}


def pair_config():
    return replace(config(), question_set=QSET)


def test_three_pair_records_keep_identity_through_support_adapter_and_finalizer():
    from types import SimpleNamespace as NS
    text = TEXT + " A third activity starts here."
    inp = make_page(text, spans=[span("later", *A2), span("earlier", *A1),
                                span("third", len(TEXT)+1, len(text))])
    fake = FakeJev({**BASE, "core.activity_segment": "distinct_action"})
    res = jac.code_page(inp, fake, pair_config())
    assert {(p.activity_id, p.linked_activity) for p in res.pairs} == {
        ("earlier", "later"), ("earlier", "third"), ("later", "third")}
    requests = [(s, q) for s, q in fake.requests if "core.activity_segment" in q]
    assert len(requests) == 3
    assert requests[0][0]["activity"] == "A2" and requests[0][0]["linked_activity"] == "A1"
    p2 = jac.to_pass2_page(res, inp)
    pairs = [(a.activity_id, c.linked_activity) for a in p2.activities for c in a.codes
             if c.item_id == "core.activity_segment"]
    assert set(pairs) == {(p.activity_id, p.linked_activity) for p in res.pairs}
    assert len(pairs) == 3
    plan = select_requests(p2)
    assert len([t for t in plan.quote_tasks if t.item_id == "core.activity_segment"]) == 3
    assert not [t for t in plan.skipped_codes if t.item_id == "core.activity_segment"]
    assert "core.activity_segment" in fake.requests[0][1]  # round 1 before round 2
    support = [NS(item_id=r.item_id, activity_id=p.activity_id, linked_activity=p.linked_activity,
                  chunk_id=r.chunk_id, support_status=("downgraded_no_quote" if
                  (p.activity_id, p.linked_activity) == ("earlier", "third") else "supported"))
               for p in res.pairs for r in p.records]
    final = jac.finalize_pairs(res, support, pair_config())
    assert {(p.activity_id, p.linked_activity): p.outcome.value for p in final} == {
        ("earlier", "later"): "distinct_action", ("earlier", "third"): "unknown",
        ("later", "third"): "distinct_action"}
    support[0].linked_activity = None
    with pytest.raises(ValueError, match="lacks linked_activity"):
        jac.finalize_pairs(res, support, pair_config())


def test_pair_failure_and_tie_remain_local():
    inp = make_page(TEXT, spans=[span("one", *A1), span("same_start", A1[0], A1[1]-1), span("two", *A2)])
    fake = FakeJev(BASE)
    def ask(state, questions):
        if "core.activity_segment" in questions:
            return JevResult({}, "jev", None, 1, 1)
        return fake(state, questions)
    res = jac.code_page(inp, ask, pair_config())
    assert jac.PAIR_DIRECTION_TIE + ":one:same_start" in res.notes
    assert len(res.pairs) == 2
    assert all(p.outcome.failed for p in res.pairs)
    assert all(f.linked_activity == "two" for f in res.failures)
    assert all(a.outcomes["core.activity_type"].state == "combined" for a in res.activities)


def test_pair_record_serialization_preserves_request_and_link_identity():
    from g3o.common.jev_record import CoderRecord
    inp = make_page(TEXT, spans=[span("one", *A1), span("two", *A2)])
    result = jac.code_page(inp, FakeJev({**BASE, "core.activity_segment": "governs"}), pair_config())
    doc = json.loads(json.dumps(result.to_dict()))
    pair, = doc["pairs"]
    assert (pair["activity_id"], pair["linked_activity"]) == ("one", "two")
    raw, = pair["records"]
    rec = CoderRecord.from_dict(raw)
    assert rec.request_id and rec.question_id == "core.activity_segment" and rec.chosen_value == "governs"
    act = doc["activities"][0]
    idx, = act["record_links"]
    assert act["record_links"][idx] == "two"
    assert act["records"][int(idx)] == raw


def test_unapproved_pair_instrument_is_refused_before_provider_call():
    qset = {**QSET, "pair_questions": [{**QSET["pair_questions"][0], "approval": "pending"}]}
    fake = FakeJev(BASE)
    inp = make_page(TEXT, spans=[span("one", *A1), span("two", *A2)])
    with pytest.raises(ValueError, match="wording approval"):
        jac.code_page(inp, fake, replace(pair_config(), question_set=qset))
    assert fake.requests == []


def test_pending_gate_cannot_publish_a_transitive_gated_out_value():
    import copy
    qset = copy.deepcopy(QSET)
    qset["pair_questions"] = []
    dependent = next(q for q in qset["questions"] if q["question_id"] == "core.deployment_scale_unit")
    dependent["gate"] = {"item": "core.model_origin", "values": ["open_source"], "gated_out_value": "not_asked"}
    cfg = replace(config(), question_set=qset)
    inp = make_page(TEXT, spans=[span("one", *A1)])
    result = jac.code_page(inp, FakeJev({**BASE, "core.activity_type": "policy_guidance"}), cfg)
    final, = jac.finalize_activities(result, _support(result, {"core.activity_type": "downgraded_no_quote"}), cfg)
    assert final.outcomes["core.model_origin"].state == "pending"
    assert final.outcomes["core.deployment_scale_unit"].state == "stopped"
    assert final.outcomes["core.deployment_scale_unit"].value is None
