"""T-026 Stage 6 executor: relation requests, support checks, pooling (mocked jev, fake quote step).

Every jev answer and quote below is a declared fake; nothing is a provider
result. Expectations come from the signed rules (R-005, R-017, R-041, R-044,
R-081; codebook r15 ``core.activity_relation_cross_page``,
``core.pooled_activity_fields``, ``core.confidence``), not from the executor.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from g3o.classify.jev_activity_code import ItemOutcome, part_combine_adapter
from g3o.classify.questions.v27 import load_set
from g3o.codebook.loader import default_codebook_path
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import load_classifier_rules
from g3o.common.source_fields import PendingCheck
from g3o.common.support_check import CodeEvidence, Entailment, PageSources, check_code
from g3o.validate import stage6_v27 as s6
from g3o.validate.consolidate_v27 import (
    ActivityObservation,
    RelationDecision,
    ReviewedPage,
    activity_confidence,
    summary_values,
)

INST = load_set("institution")
RULES = load_classifier_rules(default_codebook_path().read_bytes(), expected_sha256=INST["codebook_sha256"])
CONFIG = s6.Stage6Config(rules=RULES, setup_pointer="a" * 64, configured_model="fake-jev",
                         combiner=part_combine_adapter(), reference_year=2026, reserved_tokens=0)
REL_Q = s6.RELATION_ITEM
TRUE = Entailment("true", 0.95)


# --- fixtures ----------------------------------------------------------------


def page(pid, verdict="confirms_activity", status="supported", prob=.95, pipeline="web_extract"):
    return ReviewedPage(pid, pipeline, verdict, prob, status, True, False, False, (pid + "-s",),
                        ({"fake": "coder"},), ({"fake": "support"},))


def observation(oid, pid, supported=True, number=None):
    o = ItemOutcome("core.action_type", "core.action_type", None, "combined", "deployment")
    fields = {"core.activity_name": "Copilot pilot"}
    if number is not None:
        fields[s6.NUMBER_ITEM] = number
    return ActivityObservation(oid, pid, {o.question_id: o}, fields, supported, ({"fake": "coder"},),
                               ({"fake": "support"},))


def quote(oid, pid, text, n=0, label="a news report", date="2026-01-01"):
    return s6.InputQuote(f"sup-{oid}-{n}", oid, pid + "-s", PageSources(pid, {pid + "#c1": "Intro. " + text + " End."}),
                         pid + "#c1", pid + "#c1", text, label, date, "2026-03-01", f"https://example.gov/{pid}",
                         0, n)


def record(oid, pid, name="Copilot pilot", activity_type="internal_operational", tools=("Copilot",), quotes=()):
    values = {"core.activity_name": name, "core.activity_type": activity_type, "core.action_type": "deployment",
              "core.tool_name": list(tools), "core.year_announced": "2025", "core.developer": "not_documented"}
    return s6.ObservationRecord(oid, pid, values, f"https://example.gov/{pid}", tuple(quotes))


class FakeJev:
    """Answers relation requests from ``relations`` (keyed by the two activity names) and every
    other question from ``answers`` or a missing value. Records every request."""

    def __init__(self, relations=None, answers=None, prob=.95):
        self.relations, self.answers, self.prob, self.calls = relations or {}, answers or {}, prob, []

    def __call__(self, state, questions):
        self.calls.append((state, questions))
        out = {}
        for qid, q in questions.items():
            if qid == REL_Q:
                key = (state["first_record"].get("activity_name"), state["second_record"].get("activity_name"))
                value, p = self.relations.get(key, ("unresolved", self.prob))
            else:
                codes = list(q["criteria"])
                value = self.answers.get(qid) or next((c for c in ("not_documented", "unknown", "no") if c in codes),
                                                      codes[0])
                p = self.prob
            out[qid] = JevAnswer(qid, "choice", choice=value, confidence=p, probabilities={value: p})
        return JevResult(out, "fake-response-model", f"fake-{len(self.calls)}", 1, 1)


class FakeQuotes:
    """The Stage 6 quote step: copies the first candidate verbatim (or a set text) with X35 true."""

    def __init__(self, text=None, source=None):
        self.text, self.source, self.calls = text, source, []

    def __call__(self, req):
        self.calls.append(req)
        first = req.candidates[0]
        return s6.Stage6Quote(self.text or first.quote_text, self.source or first.support_id, TRUE)


def two_pages(name_b="Copilot pilot", **rec_b):
    pages = [page("p1"), page("p2")]
    obs = [observation("o1", "p1"), observation("o2", "p2")]
    quotes = [quote("o1", "p1", "The council uses Copilot for drafting."),
              quote("o2", "p2", "Council staff draft letters with Copilot.")]
    recs = [record("o1", "p1", quotes=quotes[:1]), record("o2", "p2", name=name_b, quotes=quotes[1:], **rec_b)]
    return pages, obs, recs, quotes


def run(pages, obs, recs, quotes, jev, quote_fn, within=()):
    return s6.run_stage6(institution="Example Council", country="AU", pages=pages, observations=obs,
                         records=recs, within_page=list(within), quotes=quotes, ask_fn=jev, quote_fn=quote_fn,
                         config=CONFIG)


# --- X30 relation requests ----------------------------------------------------


def test_identical_names_are_asked_and_merge_only_on_supported_same_activity():
    pages, obs, recs, quotes = two_pages()
    jev = FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)})
    result = run(pages, obs, recs, quotes, jev, FakeQuotes())
    rel_calls = [c for c in jev.calls if REL_Q in c[1]]
    assert len(rel_calls) == 1  # identical names: asked, not skipped (RC-D-002 H Q2)
    state = rel_calls[0][0]
    assert list(state) == ["coder_instructions", "institution", "country", "first_record", "second_record"]
    assert state["first_record"]["activity_type"] != "internal_operational"  # plain-word label, not the code
    assert "developer" not in state["first_record"]  # missing value left out
    assert state["first_record"]["supporting_quotes"] == ["The council uses Copilot for drafting."]
    assert result.groups == (("o1", "o2"),)
    decision = result.relations[0]
    assert (decision.relation, decision.support_status, decision.scope) == ("same_activity", "supported", "cross_page")
    assert set(result.pooled) == {("o1", "o2")}


@pytest.mark.parametrize("value", ["unresolved", "distinct_action", "component_of_program", "governs"])
def test_non_merge_relations_keep_activities_separate(value):
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev({("Copilot pilot", "Copilot pilot"): (value, .95)}), FakeQuotes())
    assert result.groups == (("o1",), ("o2",))
    assert result.relations[0].relation == value
    assert not result.pooled


def test_low_probability_same_activity_is_downgraded_and_never_merges():
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .7)}),
                 FakeQuotes())
    decision = result.relations[0]
    assert decision.relation == "unknown"  # downgrade_target (R-041, R-081)
    assert decision.support_status == "downgraded_low_confidence"
    assert result.groups == (("o1",), ("o2",)) and result.ready


def test_quote_from_outside_the_request_part_is_no_supporting_text():
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)}),
                 FakeQuotes(source="sup-elsewhere"))
    support = result.relation_outcomes[0].support[0]
    assert support.support_status == "downgraded_no_quote"
    assert result.groups == (("o1",), ("o2",))


def test_absent_quote_step_holds_positive_relations_and_never_publishes_them_unmerged():
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)}),
                 None)
    assert [h.reason for h in result.held] == [s6.QUOTE_STEP_ABSENT]
    assert result.missing_pairs == (("o1", "o2"),)
    assert not result.ready and not result.pooled


def test_exempt_relation_needs_no_quote_step():
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev({("Copilot pilot", "Copilot pilot"): ("unresolved", .95)}), None)
    assert result.relations[0].support_status == "not_required"  # `unresolved` exempt globally (RC-D-019 F1 a)
    assert result.ready and result.groups == (("o1",), ("o2",))


def test_prefilter_skips_only_pairs_differing_in_real_type_and_tool():
    pages, obs, recs, quotes = two_pages(name_b="Translation service", activity_type="public_facing_service",
                                         tools=("DeepL",))
    jev = FakeJev()
    result = run(pages, obs, recs, quotes, jev, None)
    assert not jev.calls
    decision = result.relations[0]
    assert (decision.relation, decision.support_status) == ("distinct_action", "set_by_rule")
    assert result.relation_outcomes[0].support[0].support_rule_name == s6.PREFILTER_RULE
    # a missing tool (or type) never makes a pair "obviously distinct": asked
    pages, obs, recs, quotes = two_pages(name_b="Translation service", activity_type="public_facing_service",
                                         tools=("not_documented",))
    jev = FakeJev()
    run(pages, obs, recs, quotes, jev, None)
    assert len(jev.calls) == 1


def test_within_page_pairs_come_from_t023_and_are_not_reasked():
    pages = [page("p1")]
    obs = [observation("o1", "p1"), observation("o2", "p1")]
    recs = [record("o1", "p1"), record("o2", "p1")]
    within = RelationDecision("o1", "o2", "distinct_action", .95, "not_required", ({"t023": "pair"},), (),
                              "within_page")
    jev = FakeJev()
    result = run(pages, obs, recs, [], jev, None, within=[within])
    assert not jev.calls and result.groups == (("o1",), ("o2",)) and result.ready
    with pytest.raises(Exception, match="within-page"):
        run(pages, obs, recs, [], jev, None, within=[replace(within, scope="cross_page")])


def test_failed_relation_request_is_held_not_a_decision():
    pages, obs, recs, quotes = two_pages()

    def broken(state, questions):
        raise RuntimeError("boom")

    result = run(pages, obs, recs, quotes, broken, None)
    assert [h.reason for h in result.held] == [s6.REQUEST_FAILED]
    assert not result.ready


# --- X31 pooling ----------------------------------------------------------------


def merged():
    pages, obs, recs, quotes = two_pages()
    return pages, obs, recs, quotes, FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)},
                                             {"core.action_type": "deployment",
                                              "core.activity_type": "internal_operational"})


def test_pooled_request_uses_the_approved_state_in_pool_order():
    pages, obs, recs, quotes, jev = merged()
    quotes = [replace(quotes[0], source_publication_date=None, stage_as_of="2025-06-01"), quotes[1]]
    run(pages, obs, recs, quotes, jev, FakeQuotes())
    pooled_calls = [c for c in jev.calls if REL_Q not in c[1]]
    state = pooled_calls[0][0]
    assert state["pool_note"] == INST["pooled"]["instruction"]
    assert state["page_part"] == "1 of 1" and "part_note" not in state
    rows = state["supporting_quotes"]
    # ordered by source date, the undated quote by its stage_as_of fallback (R-044)
    assert [r["quote_text"] for r in rows] == [quotes[0].quote_text, quotes[1].quote_text]
    assert "source_publication_date" not in rows[0] and rows[1]["source_publication_date"] == "2026-01-01"


def test_pooled_gates_use_support_checked_pooled_answers():
    pages, obs, recs, quotes, jev = merged()
    result = run(pages, obs, recs, quotes, jev, FakeQuotes())
    pooled = result.pooled[("o1", "o2")]
    out = pooled.outcomes
    assert out["core.action_type"].value == "deployment"
    assert all(out[q].state == "gated_out" for q in ("core.governance_form", "core.governance_direction"))
    asked_rounds = [set(c[1]) for c in jev.calls if REL_Q not in c[1]]
    assert all("core.governance_form" not in r for r in asked_rounds)
    assert all(s.support_status in ("supported", "not_required", "set_by_rule") for s in pooled.support)


UNIT_Q = "core.deployment_scale_unit"


def _unit_states(jev):
    return [c[0] for c in jev.calls if UNIT_Q in c[1]]


def test_pooled_scale_unit_gated_out_when_no_merged_observation_states_a_number():
    # RC-D-028 2 a: the `any stated` gate reads the merged observations' stated numbers
    pages, obs, recs, quotes, jev = merged()
    result = run(pages, obs, recs, quotes, jev, FakeQuotes())
    pooled = result.pooled[("o1", "o2")]
    unit = pooled.outcomes[UNIT_Q]
    assert unit.state == "gated_out" and unit.rule_reference == "gated_out:" + s6.NUMBER_ITEM
    assert not _unit_states(jev) and all("stated_number" not in c[0] for c in jev.calls)
    assert pooled.finished and result.ready


def test_pooled_scale_unit_asked_with_stated_number_when_any_observation_states_one():
    pages, obs, recs, quotes, jev = merged()
    obs = [obs[0], observation("o2", "p2", number="1,200")]  # one page states it: gate open
    result = run(pages, obs, recs, quotes, jev, FakeQuotes())
    states = _unit_states(jev)
    assert len(states) == 1 and states[0]["stated_number"] == "1,200"
    assert list(states[0])[-1] == "stated_number"
    # shown only in the request whose question shows it (as the per-page state, W-06 a)
    assert all("stated_number" not in c[0] for c in jev.calls if UNIT_Q not in c[1])
    assert result.pooled[("o1", "o2")].outcomes[UNIT_Q].state == "combined"
    # the same number words on two pages: one value
    obs = [observation("o1", "p1", number="1,200"), observation("o2", "p2", number="1,200")]
    jev2 = merged()[4]
    run(pages, obs, recs, quotes, jev2, FakeQuotes())
    assert [s["stated_number"] for s in _unit_states(jev2)] == ["1,200"]


def test_pooled_different_stated_numbers_are_shown_as_a_list_in_pool_order():
    # RC-D-029 W1 a: the distinct number words as a list, pool order; W2 a: last field
    pages, obs, recs, quotes, jev = merged()
    obs = [observation("o1", "p1", number="1,200"), observation("o2", "p2", number="300")]
    result = run(pages, obs, recs, quotes, jev, FakeQuotes())
    pooled = result.pooled[("o1", "o2")]
    states = _unit_states(jev)
    assert len(states) == 1 and states[0]["stated_number"] == ["1,200", "300"]
    assert list(states[0])[-1] == "stated_number"
    assert all("stated_number" not in c[0] for c in jev.calls if UNIT_Q not in c[1])
    assert not pooled.held and pooled.outcomes[UNIT_Q].state == "combined" and result.ready
    # pool order is source date, not group order: o2's quote dated earlier comes first
    quotes = [quotes[0], replace(quotes[1], source_publication_date="2025-01-01")]
    jev2 = merged()[4]
    run(pages, obs, recs, quotes, jev2, FakeQuotes())
    assert [s["stated_number"] for s in _unit_states(jev2)] == [["300", "1,200"]]
    # a repeated number word appears once
    obs3 = [observation("o1", "p1", number="300"), observation("o2", "p2", number="1,200"),
            observation("o3", "p3", number="300")]
    assert s6.stated_numbers(["o1", "o2", "o3"], {o.observation_id: o for o in obs3}) == ("300", "1,200")


def test_pooled_stated_number_list_is_in_the_token_measure(monkeypatch):
    # the request measure serializes the state with the list form (upper bound, W1 a)
    pages, obs, recs, quotes, jev = merged()
    obs = [observation("o1", "p1", number="1,200"), observation("o2", "p2", number="300")]
    seen = []
    real = s6.prepare_pool_requests

    def spy(pool_id, entries, *, serialize_request, **kw):
        def wrapped(part):
            text = serialize_request(part)
            seen.append(json.loads(text))
            return text
        return real(pool_id, entries, serialize_request=wrapped, **kw)

    monkeypatch.setattr(s6, "prepare_pool_requests", spy)
    run(pages, obs, recs, quotes, jev, FakeQuotes())
    assert seen and all(s["stated_number"] == ["1,200", "300"] for s in seen)


def test_pooled_stated_number_of_unconfirmed_observation_is_not_used():
    pages, obs, recs, quotes, jev = merged()
    pages = [pages[0], page("p2", "ambiguous_attribution", "not_required")]
    obs = [obs[0], observation("o2", "p2", supported=False, number="1,200")]
    result = run(pages, obs, recs, quotes, jev, FakeQuotes())
    pooled = result.pooled[("o1", "o2")]
    assert pooled.observation_ids == ("o1",)  # relations only (r2#51)
    assert pooled.outcomes[UNIT_Q].state == "gated_out"


@pytest.mark.parametrize("label", [None, ""])
def test_pooled_quote_without_signed_source_type_label_leaves_the_field_out(label):
    # RC-D-028 3 a: an auto-typed official / archive page, or no type: left out, as a missing value
    pages, obs, recs, quotes, jev = merged()
    quotes = [replace(quotes[0], source_type_label=label), quotes[1]]
    recs = [replace(recs[0], quotes=(quotes[0],)), recs[1]]
    result = run(pages, obs, recs, quotes, jev, FakeQuotes())
    rows = [c[0]["supporting_quotes"] for c in jev.calls if REL_Q not in c[1]]
    assert rows and all("source_type" not in r[0] and r[1]["source_type"] == "a news report" for r in rows)
    assert all(list(r[0]) == ["quote_text", "source_publication_date", "page_url"] for r in rows)
    # the merge involving the official page is no longer blocked
    pooled = result.pooled[("o1", "o2")]
    assert not pooled.held and pooled.finished and result.ready


def test_pooled_positive_answer_without_quote_step_is_pending():
    pages, obs, recs, quotes, jev = merged()
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, jev, None, CONFIG)
    assert pooled.outcomes["core.action_type"].state == "pending"
    assert s6.QUOTE_STEP_ABSENT in {h.reason for h in pooled.held}


def test_long_pool_is_split_and_every_part_is_marked():
    pages, obs, recs, quotes, jev = merged()
    long = [quote("o1", "p1", (f"Copilot drafting evidence sentence {i}. ") * 40, n=i) for i in range(40)]
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, [*long, quotes[1]], jev, FakeQuotes(),
                              replace(CONFIG, limit_tokens=6000))
    first_round = min(pooled.parts)
    assert len(pooled.parts[first_round]) > 1
    states = [c[0] for c in jev.calls]
    n = len(pooled.parts[first_round])
    assert {s["page_part"] for s in states[:n]} == {f"{i} of {n}" for i in range(1, n + 1)}
    assert all(s["part_note"] == INST["part_prompt"]["sentence"] for s in states[:n])


# --- source confidence association (RC-D-025 A1, C7 a, C8 b, P12) ----------------


def _sr(item, value, prob=.95, activity=None, quote_text=None):
    src = PageSources("p1", {"p1#c1": "Council uses Copilot for drafting letters."})
    return check_code(CodeEvidence(item, value, "p1#c1", probability=prob, quote=quote_text,
                                   quote_chunk_id="p1#c1" if quote_text else None,
                                   entailment=TRUE if quote_text else None, activity_id=activity), src)


def test_source_claim_records_take_page_level_and_own_activity_on_this_page():
    page_level = [_sr("core.page_verdict", "confirms_activity", quote_text="Council uses Copilot")]
    own = [_sr("core.action_type", "deployment", activity="o1", quote_text="uses Copilot")]
    other = [_sr("core.action_type", "deployment", prob=.5, activity="o9", quote_text="uses Copilot")]
    recs = s6.source_claim_records("p1", ["o1"], page_level, {"o1": own, "o9": other},
                                   {"o1": "p1", "o9": "p1"})
    assert recs == [*page_level, *own]
    assert s6.source_claim_confidence("S1", "medium", recs).value == "medium"


def test_downgraded_negative_on_associated_code_makes_source_low_c7a():
    page_level = [_sr("core.page_verdict", "no_genai", prob=.6)]
    conf = s6.source_claim_confidence("S1", "high", s6.source_claim_records("p1", [], page_level, {}, {}))
    assert conf.value == "low"
    pending = s6.source_claim_confidence("S2", "high", [PendingCheck("core.action_type", "deployment", "quote")])
    assert not pending.finished
    # unknown source confidence counts as low in activity aggregation (C8 b)
    assert activity_confidence({"S1": "unknown", "S3": "medium"}, {"S1": "g1", "S3": "g3"}) == "medium"


# --- RS-011 exval cases, adapted (A-010) ----------------------------------------

CASES = json.loads((Path(__file__).parent / "fixtures" / "t026_exval_cases.json").read_text(encoding="utf-8"))["cases"]
#: Test adaptation of the v2.6 dispositions to v2.7 page verdicts (R-015 names); not a runtime map.
VERDICT = {"qualifying": "confirms_activity", "excluded_event": "event_only", "other_actor": "other_body",
           "unresolved": "ambiguous_attribution"}
EXPECTED = {"confirms_activity": "yes", "event_only": "no", "other_body": "no", "ambiguous_attribution": "unclear"}


def _institutions():
    by_inst: dict[str, list[dict]] = {}
    for c in CASES:
        if c["original_observation"] is None:
            continue
        by_inst.setdefault(c["original_observation"].split("::")[1], []).append(c)
    return by_inst


def test_exval_cases_all_thirty_present():
    assert len(CASES) == 30


@pytest.mark.parametrize("inst", sorted(_institutions()))
def test_exval_institution_verdicts(inst):
    cases = _institutions()[inst]
    urls = list(dict.fromkeys(c["source_url"] for c in cases))
    pages = []
    for n, url in enumerate(urls):
        verdicts = [VERDICT[c["expected_disposition"]] for c in cases if c["source_url"] == url]
        best = "confirms_activity" if "confirms_activity" in verdicts else verdicts[0]
        pages.append(page(f"{inst}-p{n}", best, "supported" if best == "confirms_activity" else "not_required"))
    obs = [observation(f"{inst}-o{i}", f"{inst}-p{urls.index(c['source_url'])}")
           for i, c in enumerate(cases) if c["expected_disposition"] == "qualifying"]
    values = [{"core.action_type": "deployment", "core.adoption_stage": "pilot",
               "core.procurement_status": "none_documented", "core.activity_type": "internal_operational"}
              for _ in obs]
    verdicts = {VERDICT[c["expected_disposition"]] for c in cases}
    expected = "yes" if "confirms_activity" in verdicts else "unclear" if "ambiguous_attribution" in verdicts else "no"
    got = summary_values(pages, obs, published_activity_values=values)["core.has_genai_activity"]
    assert got == expected


def test_exval_clay_cohorts_stay_three_activities():
    clay = [c for c in CASES if c["case"].startswith("Clay")]
    assert len({c["source_url"] for c in clay}) == 1
    pages = [page("clay")]
    obs = [observation(f"o{i}", "clay") for i in range(3)]
    recs = [record(f"o{i}", "clay", name=c["case"]) for i, c in enumerate(clay)]
    within = [RelationDecision(f"o{a}", f"o{b}", "distinct_action", .95, "not_required", ({"t023": "pair"},), (),
                               "within_page") for a, b in ((0, 1), (0, 2), (1, 2))]
    result = run(pages, obs, recs, [], FakeJev(), None, within=within)
    assert result.groups == (("o0",), ("o1",), ("o2",)) and result.ready


def test_exval_cumberland_component_and_unresolved_links_never_merge():
    by = {c["case"]: c for c in CASES}
    pages = [page("prog"), page("ask", "ambiguous_attribution", "not_required"),
             page("lib", "ambiguous_attribution", "not_required")]
    obs = [observation("program", "prog"), observation("chatbot", "prog"), observation("askccnc", "ask", False),
           observation("library", "lib", False)]
    q = [quote("program", "prog", by["Cumberland program"]["source_excerpt"][:120]),
         quote("chatbot", "prog", by["Cumberland chatbot"]["source_excerpt"][120:240], n=1)]
    recs = [record("program", "prog", "County LLM integration", quotes=q[:1]),
            record("chatbot", "prog", "Public chatbot", quotes=q[1:]),
            record("askccnc", "ask", "Ask CCNC"), record("library", "lib", "Library AI materials policy",
                                                         activity_type="policy_guidance", tools=("not_documented",))]
    within = [RelationDecision("program", "chatbot", "has_component", .95, "supported", ({"t023": "pair"},),
                               ("t023-support",), "within_page")]
    jev = FakeJev({("Public chatbot", "Ask CCNC"): ("unresolved", .95),
                   ("County LLM integration", "Ask CCNC"): ("unresolved", .95),
                   ("County LLM integration", "Library AI materials policy"): ("distinct_action", .95),
                   ("Public chatbot", "Library AI materials policy"): ("distinct_action", .95),
                   ("Ask CCNC", "Library AI materials policy"): ("distinct_action", .95)})
    result = run(pages, obs, recs, q, jev, FakeQuotes(), within=within)
    assert len([c for c in jev.calls if REL_Q in c[1]]) == 5  # every cross-page pair asked
    assert result.groups == (("program",), ("chatbot",), ("askccnc",), ("library",))
    assert result.ready
    values = [{"core.action_type": "deployment", "core.adoption_stage": "production",
               "core.procurement_status": "none_documented", "core.activity_type": "public_facing_service"}] * 2
    assert summary_values(pages, obs, published_activity_values=values)["core.has_genai_activity"] == "yes"


# --- permanent_pilot override after the cross-page combination (RC-D-025 B2 a; PI 2026-11-10 6 a) ----


class ItemQuotes(FakeQuotes):
    """Quote step that copies, for named items, a given candidate (e.g. page B's quote)."""

    def __init__(self, by_item):
        super().__init__()
        self.by_item = by_item

    def __call__(self, req):
        self.calls.append(req)
        if req.item_id in self.by_item:
            sid, text = self.by_item[req.item_id]
            return s6.Stage6Quote(text, sid, TRUE)
        first = req.candidates[0]
        return s6.Stage6Quote(first.quote_text, first.support_id, TRUE)


def _pp(stage="pilot", pp="yes", pp_source="sup-o2-0", pp_text="Council staff draft letters with Copilot.", prob=.95):
    pages, obs, recs, quotes = two_pages()
    jev = FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)},
                  {"core.action_type": "deployment", "core.activity_type": "internal_operational",
                   "core.adoption_stage": stage, "core.permanent_pilot": pp})
    if prob != .95:
        base = jev.__call__

        def low(state, questions):
            res = base(state, questions)
            if "core.permanent_pilot" in res.answers:
                res.answers["core.permanent_pilot"] = JevAnswer("core.permanent_pilot", "choice", choice=pp,
                                                                confidence=prob, probabilities={pp: prob})
            return res
        ask = low
    else:
        ask = jev
    quote_fn = ItemQuotes({"core.permanent_pilot": (pp_source, pp_text),
                           "core.adoption_stage": ("sup-o1-0", "The council uses Copilot for drafting.")})
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, ask, quote_fn, CONFIG)
    return pooled.outcomes["core.adoption_stage"], pooled.outcomes["core.permanent_pilot"]


def test_pooled_pilot_with_supported_permanent_pilot_from_other_page_becomes_production():
    stage, pp = _pp()
    assert (stage.value, stage.rule_reference) == ("production", s6.PERMANENT_PILOT_RULE)
    assert stage.note and "pilot" in stage.note
    assert stage.probability == .95 and stage.part_id == "pool001#p001"  # original evidence kept (5 a)
    assert pp.value == "yes"  # flag unchanged


def test_unsupported_permanent_pilot_yes_leaves_stage_unchanged():
    stage, _ = _pp(pp_source="sup-elsewhere")  # quote not from the part: downgraded_no_quote
    assert stage.value == "pilot" and stage.rule_reference is None
    stage, _ = _pp(prob=.6)  # below the 0.8 bar
    assert stage.value == "pilot" and stage.rule_reference is None


@pytest.mark.parametrize("value", ["production", "proposed", "announced", "discontinued"])
def test_permanent_pilot_override_touches_only_pilot(value):
    stage, pp = _pp(stage=value)
    assert stage.value == value and stage.rule_reference is None  # rule recorded only on change (4 a)
    assert pp.value == "yes"


# --- 6_validate.json content --------------------------------------------------------


def _identity():
    return {"institution_id": "INST-0001", "institution_name": "Example Council", "country": "Australia",
            "branch_of_government": "executive", "level_of_government": "local",
            "institution_search_languages": "en"}


def _meta():
    return {"institution_id": "INST-0001", "n_input_pages": 1, "n_input_rows": 1,
            "response_timestamp": "2026-11-10T12:00:00Z", "model_label": "fake-jev", "notes": "none"}


def test_consolidated_response_is_the_v27_model_with_keys_from_storage(tmp_path):
    """RC-D-028 4 a: identity and row keys only; every value stays in 6_storage.json."""
    from g3o.common.response_v27 import ConsolidatedInstitutionResponseV27, parse_validate_payload
    from tests._storage_fixture import fixture_bundle

    data, _, _, envelope = fixture_bundle(tmp_path)
    master_row = {**_identity(), "has_genai_activity": "yes", "tool_name": "Copilot"}  # non-identity: not read
    response = s6.consolidated_response(institution=master_row, metadata=_meta(), storage=envelope)
    assert isinstance(response, ConsolidatedInstitutionResponseV27)
    payload = response.model_dump(mode="json")
    assert payload["institution"] == _identity()
    assert payload["activities"] == [{"activity_id": "A1"}, {"activity_id": "A2"}]
    assert payload["sources"] == [{"source_id": "S1", "activity_id": "A1"}, {"source_id": "S2", "activity_id": "A2"}]
    assert s6.consolidated_response(institution=_identity(), metadata=_meta(), storage=data) == response
    keyed = s6.consolidated_response(institution=_identity(), metadata=_meta(), activity_ids=["A1", "A2"],
                                     sources=[("S1", "A1"), ("S2", "A2")])
    assert keyed == response
    with pytest.raises(ValueError, match="not both"):
        s6.consolidated_response(institution=_identity(), metadata=_meta(), storage=envelope,
                                 activity_ids=["A1", "A2"], sources=[("S1", "A1"), ("S2", "A2")])
    with pytest.raises(ValueError, match="are required"):
        s6.consolidated_response(institution=_identity(), metadata=_meta(), activity_ids=["A1"])

    paths = s6.write_stage6_outputs(tmp_path / "inst", envelope=envelope, institution=_identity(),
                                    metadata=_meta(), provenance=[])
    written = json.loads(paths[0].read_text(encoding="utf-8"))
    assert parse_validate_payload(written) == response
    for value_field in ("has_genai_activity", "tool_name", "genai_evidence", "source_url", "values"):
        assert value_field not in json.dumps(written)
    assert json.loads(paths[1].read_text(encoding="utf-8"))["activities"].keys() == data["activities"].keys()


def test_consolidated_response_is_bound_to_its_storage(tmp_path):
    from tests._storage_fixture import fixture_bundle

    data, _, _, envelope = fixture_bundle(tmp_path)
    relinked = s6.consolidated_response(institution=_identity(), metadata=_meta(), activity_ids=["A1", "A2"],
                                        sources=[("S1", "A2"), ("S2", "A1")])
    with pytest.raises(ValueError, match="activity link differs"):
        s6.write_stage6_artifacts(tmp_path / "inst", envelope, relinked, [])
    with pytest.raises(ValueError, match="different institutions"):
        s6.consolidated_response(institution=_identity(), metadata=_meta(),
                                 storage={**data, "institution_id": "INST-0002"})
    with pytest.raises(ValueError, match="non-2.7 storage"):
        s6.consolidated_response(institution=_identity(), metadata=_meta(),
                                 storage={**data, "codebook_release": "2.6"})
    with pytest.raises(KeyError):  # an identity column is required, never defaulted
        s6.consolidated_response(institution={k: v for k, v in _identity().items() if k != "country"},
                                 metadata=_meta(), storage=envelope)


# --- RC-D-028 5a-5f (confirmed by the PI; pinned) ------------------------------------


def test_5a_missing_activity_type_means_the_pair_is_asked():
    pages, obs, recs, quotes = two_pages(name_b="Translation service", activity_type="not_documented",
                                         tools=("DeepL",))
    jev = FakeJev()
    run(pages, obs, recs, quotes, jev, None)
    assert len(jev.calls) == 1


def test_5c_oversize_relation_request_is_held_not_split():
    pages, obs, recs, quotes = two_pages()
    jev = FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)})
    result = s6.run_stage6(institution="Example Council", country="AU", pages=pages, observations=obs,
                           records=recs, within_page=[], quotes=quotes, ask_fn=jev, quote_fn=FakeQuotes(),
                           config=replace(CONFIG, limit_tokens=50))
    assert [h.reason for h in result.held] == [s6.RELATION_OVER_BUDGET] and not jev.calls
    assert not result.ready


def test_5d_pooled_year_candidates_read_from_the_whole_pooled_part():
    pages, obs, recs, quotes, jev = merged()
    quotes = [replace(quotes[0], quote_text="The council began using Copilot in 2023."),
              replace(quotes[1], quote_text="Staff drafted letters with Copilot in 2024.")]
    quotes = [replace(q, sources=PageSources(q.sources.page_id, {q.producing_chunk_id: q.quote_text}))
              for q in quotes]
    recs = [replace(recs[0], quotes=(quotes[0],)), replace(recs[1], quotes=(quotes[1],))]
    run(pages, obs, recs, quotes, jev, FakeQuotes())
    asked = [c[1]["core.year_announced"] for c in jev.calls if "core.year_announced" in c[1]]
    assert len(asked) == 1 and {"2023", "2024"} <= set(asked[0]["criteria"])


def test_5e_support_checked_per_round_before_the_next_rounds_gates():
    pages, obs, recs, quotes = two_pages()
    answers = {"core.action_type": "governance", "core.activity_type": "policy_guidance"}
    jev = FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)}, answers)
    # supported governance: the governance-gated round-3 questions are asked
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, jev, FakeQuotes(), CONFIG)
    assert pooled.outcomes["core.governance_form"].state != "gated_out"
    # the same answer failing its quote check is downgraded before round 3: gate closed
    jev = FakeJev({}, answers)
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, jev,
                              ItemQuotes({"core.action_type": ("sup-elsewhere", "no such quote")}), CONFIG)
    assert pooled.outcomes["core.action_type"].value == "unknown"
    assert pooled.outcomes["core.governance_form"].state == "gated_out"
    assert all("core.governance_form" not in c[1] for c in jev.calls)


def test_5f_budget_is_measured_on_the_request_state_not_the_questions():
    from g3o.common.page_chunks import TokenEstimator

    pages, obs, recs, quotes, jev = merged()
    run(pages, obs, recs, quotes, jev, FakeQuotes())
    est = TokenEstimator()
    state, questions = max(((c[0], c[1]) for c in jev.calls if REL_Q not in c[1]),
                           key=lambda c: len(json.dumps(c[1])))
    # the measured form: multi-part, with the part note and a wide marker (never smaller than sent)
    measured = {**state, "page_part": f"1 of {s6.MEASURE_PARTS}", "part_note": INST["part_prompt"]["sentence"]}
    state_tokens = est.tokens(json.dumps(measured, ensure_ascii=False, sort_keys=True))
    question_tokens = est.tokens(json.dumps(questions, ensure_ascii=False, sort_keys=True))
    limit = state_tokens + 40
    assert question_tokens > 40
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, merged()[4], FakeQuotes(),
                              replace(CONFIG, limit_tokens=limit))
    assert all(len(p) == 1 for p in pooled.parts.values())  # state fits: one part, questions not counted


# --- RC-D-030 ---------------------------------------------------------------


def test_y4_pooled_quotes_of_identical_text_are_shown_once_per_observation():
    pages, obs, recs, quotes, jev = merged()
    dup_same = replace(quotes[0], support_id="sup-o1-dup", passage_order=5)
    dup_other = replace(quotes[1], support_id="sup-o2-dup", observation_id="o2", quote_text=quotes[0].quote_text,
                        passage_order=6)
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, [*quotes, dup_same, dup_other], jev,
                              FakeQuotes(), CONFIG)
    shown = {i for ids in pooled.part_inputs.values() for i in ids}
    assert "sup-o1-dup" not in shown  # same text, same observation: once
    assert {quotes[0].support_id, quotes[1].support_id, "sup-o2-dup"} <= shown  # other observation: kept
    state = next(c[0] for c in jev.calls if REL_Q not in c[1])
    texts = [r["quote_text"] for r in state["supporting_quotes"]]
    assert texts.count(quotes[0].quote_text) == 2


def test_z1_pooled_question_with_a_failed_request_part_is_held_not_combined():
    pages, obs, recs, quotes, jev = merged()

    def failing(state, questions):
        if REL_Q not in questions and "core.action_type" in questions:
            raise RuntimeError("simulated pooled request failure")
        return jev(state, questions)
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, failing, FakeQuotes(), CONFIG)
    o = pooled.outcomes["core.action_type"]
    assert o.state == "pending" and o.note == s6.POOLED_REQUEST_FAILED and o.value is None
    holds = [h for h in pooled.held if h.reason == s6.POOLED_REQUEST_FAILED]
    assert any(h.key.endswith(":core.action_type") and "RuntimeError" in h.detail for h in holds)
    assert not pooled.finished


def test_z1_returned_answer_failing_checks_still_combines_as_unknown():
    pages, obs, recs, quotes, jev = merged()
    low = FakeJev(answers={"core.action_type": "deployment"}, prob=.5)
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, low, FakeQuotes(), CONFIG)
    o = pooled.outcomes["core.action_type"]
    assert o.state == "combined" and o.value == "unknown" and o.failed
    assert s6.POOLED_REQUEST_FAILED not in {h.reason for h in pooled.held}


ROLE_Q = "core.observed_actor_relationship#searched_institution_role"
REL_PART_Q = "core.observed_actor_relationship"


@pytest.mark.parametrize("relationship,gated", [("unresolved", True), ("other", False)])
def test_z2_role_part_gate_applied_after_the_pooled_relationship_answer(relationship, gated):
    pages, obs, recs, quotes, _ = merged()
    jev = FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)},
                  answers={REL_PART_Q: relationship, ROLE_Q: "beneficiary"})
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, jev, FakeQuotes(), CONFIG)
    role = pooled.outcomes[ROLE_Q]
    assert any(ROLE_Q in c[1] for c in jev.calls if REL_Q not in c[1])  # asked in the same round
    if gated:
        assert (role.state, role.value) == ("gated_out", "not_asked")
        assert role.rule_reference.endswith("core.observed_actor_relationship")
        mech = [r for r in pooled.records if r.coder_type == "mechanical" and r.question_id == ROLE_Q]
        assert len(mech) == 1 and mech[0].chosen_value == "not_asked"
        raw = [r for r in pooled.records if r.coder_type == "classifier" and r.question_id == ROLE_Q]
        assert raw and raw[0].chosen_value == "beneficiary"  # raw answer kept, unpublished
    else:
        assert (role.state, role.value) == ("combined", "beneficiary")


def test_role_part_is_pending_while_its_relationship_part_is_pending():
    # QA round 2 LOW-E: the relationship part's pooled request failed (held, Z1 b) -> the role
    # part waits on it: pending, not stopped
    pages, obs, recs, quotes, _ = merged()
    jev = FakeJev({("Copilot pilot", "Copilot pilot"): ("same_activity", .95)},
                  answers={REL_PART_Q: "other", ROLE_Q: "beneficiary"})

    def failing(state, questions):
        if REL_Q not in questions and REL_PART_Q in questions:
            r = jev(state, questions)
            return JevResult({k: v for k, v in r.answers.items() if k != REL_PART_Q}, r.response_model,
                             r.request_id, r.input_tokens, r.output_tokens)
        return jev(state, questions)
    pooled = s6.pool_activity("pool001", ("o1", "o2"), obs, pages, quotes, failing, FakeQuotes(), CONFIG)
    assert pooled.outcomes[REL_PART_Q].state == "pending"
    role = pooled.outcomes[ROLE_Q]
    assert role.state == "pending" and role.value is None and role.error is None
