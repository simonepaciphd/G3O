"""Offline execution of post-support questions, including interruption recovery."""

import json
from copy import deepcopy
from dataclasses import dataclass, replace

import pytest

from g3o.classify import jev_activity_code as ac
from g3o.classify import jev_page_code as pc
from g3o.classify.question_rounds import (
    HALVING_STOP,
    HALVING_STOPPED,
    complete_activity_rounds,
    complete_page_rounds,
)
from g3o.classify.questions.v27 import load_set
from g3o.codebook.loader import default_codebook_path
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import load_classifier_rules
from g3o.common.page_chunks import Chunk, halve_chunk
from g3o.common.part_combine import NOT_COVERED
from g3o.extract.parser_v27 import ActivitySpan
from g3o.extract.request_v27 import Pass1Page


@dataclass(frozen=True)
class Support:
    item_id: str
    chunk_id: str
    support_status: str = "supported"
    part: str | None = None
    activity_id: str | None = None
    linked_activity: str | None = None


@pytest.fixture(scope="module")
def rules():
    return load_classifier_rules(default_codebook_path().read_bytes(),
                                 expected_sha256=load_set("page")["codebook_sha256"])


class Jev:
    def __init__(self, choices=None):
        self.choices = choices or {}
        self.calls = []

    def __call__(self, state, questions):
        self.calls.append((deepcopy(state), deepcopy(questions)))
        answers = {}
        for qid, q in questions.items():
            value = self.choices.get(qid, next(iter(q["criteria"])))
            if callable(value):
                value = value(state)
            assert value in q["criteria"]
            probabilities = {v: (0.95 if v == value else 0.05 / (len(q["criteria"]) - 1))
                             for v in q["criteria"]}
            answers[qid] = JevAnswer(qid, "choice", choice=value, confidence=0.95,
                                     probabilities=probabilities)
        return JevResult(answers, "jev-fixture", f"request-{len(self.calls)}", 10, 1)


def page_case(monkeypatch, rules, *, descendant=False, closing=False):
    texts = ("FIRST: City information. ", "SECOND: City activity. ")
    chunks = tuple(Chunk(f"p:{i}", "p", sum(map(len, texts[:i])), sum(map(len, texts[:i + 1])), t, 20)
                   for i, t in enumerate(texts))
    monkeypatch.setattr(pc, "plan_layout", lambda *args: list(chunks))
    page = pc.PageInput("p", "i", "City", "X", "local", "https://city.example", "City",
                        "".join(texts), "Header\nFooter", email_links=("ai@city.example",))
    qset = deepcopy(load_set("page"))
    if descendant:
        # Structural graph test, not an amendment to the production instrument.
        q = next(q for q in qset["questions"] if q["question_id"] == "core.content_data")
        q["round"] = 4
        q["gate"] = {"item": "core.disclosure_scope", "values": ["single_institution"],
                     "gated_out_value": "no"}
    config = pc.PageCoderConfig(rules, "a" * 64, "jev-fixture", 0, question_set=qset)
    choices = {"core.page_verdict": "confirms_activity", "core.disclosure_scope": "single_institution",
               "core.disclosure_form": lambda s: "informal_official" if "FIRST" in s["page_text"] else "mandated_report"}
    if closing:
        choices["core.page_verdict"] = lambda s: "confirms_activity" if "FIRST" in s["page_text"] else "background_only"
    fake = Jev(choices)
    result = pc.code_page(page, fake, config)
    failed = "core.page_verdict" if closing else "core.disclosure_form"
    support = tuple(Support(r.item_id, r.chunk_id,
                            "downgraded_no_quote" if r.item_id == failed and r.chunk_id == "p:0" else "supported")
                    for r in result.records if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED)
    fake.calls.clear()
    return page, result, support, config, fake


def test_page_opening_requests_and_checks_before_finalization(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    evidence_calls = []
    def check(updated, records):
        evidence_calls.append(records)
        assert updated.items["core.disclosure_scope"].state == "combined"
        return [Support(r.item_id, r.chunk_id) for r in records]
    done = complete_page_rounds(page, result, support, ask_fn=fake, config=config, check_support=check)
    assert done.complete
    assert done.final.items["core.disclosure_scope"].value == "single_institution"
    assert [set(q) for _, q in fake.calls] == [{"core.disclosure_scope"}] * 2
    assert len(evidence_calls) == 1 and len(evidence_calls[0]) == 2
    assert done.result.records[:len(result.records)] == result.records
    assert done.result.requests[:len(result.requests)] == result.requests


def test_gate_closing_keeps_raw_answers_without_new_questions(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules, closing=True)
    done = complete_page_rounds(page, result, support, ask_fn=fake, config=config,
                                check_support=lambda *_: pytest.fail("unexpected support request"))
    assert done.complete and not fake.calls
    assert done.final.items["core.content_data"].state == "gated_out"
    assert done.final.items["core.content_data"].value == "no"
    assert done.result.records == result.records


def test_new_question_support_can_close_descendant(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules, descendant=True)
    done = complete_page_rounds(page, result, support, ask_fn=fake, config=config,
                                check_support=lambda _, recs: [Support(r.item_id, r.chunk_id,
                                    "downgraded_no_quote") for r in recs])
    assert done.complete
    assert done.final.items["core.disclosure_scope"].value == "unknown"
    assert done.final.items["core.content_data"].state == "gated_out"
    assert not any("core.content_data" in q for _, q in fake.calls)


def test_pending_descendants_are_actually_asked_in_later_round(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules, descendant=True)
    checked = []
    def check(_, records):
        checked.extend(r.item_id for r in records)
        return [Support(r.item_id, r.chunk_id) for r in records]
    done = complete_page_rounds(page, result, support, ask_fn=fake, config=config, check_support=check)
    assert done.complete
    assert [next(iter(q)) for _, q in fake.calls] == ["core.disclosure_scope"] * 2 + ["core.content_data"] * 2
    assert checked == ["core.disclosure_scope"] * 2 + ["core.content_data"] * 2
    assert done.final.items["core.content_data"].state == "combined"


def test_resume_after_one_answer_requests_only_missing_part(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    saved = []
    def checkpoint(updated, checked):
        # Serialization round-trip is the actual persisted page format.
        saved.append((pc.PageCodeResult.from_json(updated.to_json()), checked))
        if len(updated.records) == len(result.records) + 1:
            raise KeyboardInterrupt
    def check(_, records):
        return [Support(r.item_id, r.chunk_id) for r in records]
    with pytest.raises(KeyboardInterrupt):
        complete_page_rounds(page, result, support, ask_fn=fake, config=config,
                             check_support=check, checkpoint=checkpoint)
    assert len(fake.calls) == 1 and saved
    done = complete_page_rounds(page, *saved[-1], ask_fn=fake, config=config, check_support=check)
    assert done.complete and len(fake.calls) == 2
    assert [s["page_part"] for s, _ in fake.calls] == ["1 of 2", "2 of 2"]
    # A fully complete resume issues neither classifier nor support calls.
    complete_page_rounds(page, done.result, done.support, ask_fn=lambda *_: pytest.fail("repeat"),
                         config=config, check_support=lambda *_: pytest.fail("repeat support"))


def test_resume_after_coding_before_support_does_not_reask(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    saved = []
    def checkpoint(updated, checked):
        saved.append((updated, checked))
    with pytest.raises(KeyboardInterrupt):
        complete_page_rounds(page, result, support, ask_fn=fake, config=config,
                             check_support=lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()),
                             checkpoint=checkpoint)
    assert len(fake.calls) == 2
    done = complete_page_rounds(page, *saved[-1], ask_fn=lambda *_: pytest.fail("repeat"), config=config,
                                check_support=lambda _, recs: [Support(r.item_id, r.chunk_id) for r in recs])
    assert done.complete


def test_failed_request_remains_pending_and_cannot_publish_negative(monkeypatch, rules):
    page, result, support, config, _ = page_case(monkeypatch, rules, descendant=True)
    done = complete_page_rounds(page, result, support, config=config,
                                ask_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("offline failure")),
                                check_support=lambda *_: pytest.fail("no answer to check"))
    assert not done.complete
    assert done.final.items["core.disclosure_scope"].state == "pending"
    assert done.final.items["core.content_data"].value is None
    assert done.result.failures[-1]["reason"] == "extra_round_failed"


def activity_case(rules):
    text = "The city adopted an AI policy. It governs the city chatbot deployment."
    chunks = (Chunk("p:0", "p", 0, len(text), text, 20),)
    page = Pass1Page("p", "i", "City", "https://city.example", "City", text, chunks, (), "confirms_activity", None)
    spans = (ActivitySpan("a", "p:0", 0, 30, "resolved", "The", "policy.", ()),
             ActivitySpan("b", "p:0", 31, len(text), "resolved", "It", "deployment.", ()))
    inp = ac.ActivityPageInput(page, "X", "local", spans)
    config = ac.ActivityCoderConfig(rules, "a" * 64, "jev-fixture", ac.part_combine_adapter(), 2026)
    fake = Jev({"core.activity_type": "policy_guidance", "core.activity_segment": "governs",
                "core.action_type": "governance", "core.model_origin": "open_weight"})
    result = ac.code_page(inp, fake, config)
    support = tuple(Support(r.item_id, r.chunk_id,
                            "downgraded_no_quote" if r.item_id == "core.activity_type" else "supported",
                            r.item_part, a.activity_id, a.record_links.get(i))
                    for a in result.activities for i, r in enumerate(a.records)
                    if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED)
    fake.calls.clear()
    return inp, result, support, config, fake


def test_activity_new_questions_keep_pair_identity_and_check_support(rules):
    inp, result, support, config, fake = activity_case(rules)
    checks = []
    def check(_, records):
        checks.extend((aid, r.question_id) for aid, r in records)
        return [Support(r.item_id, r.chunk_id, part=r.item_part, activity_id=aid) for aid, r in records]
    done = complete_activity_rounds(inp, result, support, ask_fn=fake, config=config, check_support=check)
    assert done.complete
    assert {(aid, "core.model_origin") for aid in ("a", "b")} <= set(checks)
    assert all("core.activity_segment" not in q for _, q in fake.calls)
    assert done.result.pairs == result.pairs
    for before, after in zip(result.activities, done.result.activities, strict=True):
        assert after.records[:len(before.records)] == before.records
        assert after.record_links == before.record_links
    assert all(a.outcomes["core.model_origin"].value == "open_weight" for a in done.final)
    final_pairs = ac.finalize_pairs(done.result, done.support, config)
    assert final_pairs[0].activity_id == "a" and final_pairs[0].linked_activity == "b"


def test_instrument_mismatch_refused_before_requests(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    with pytest.raises(ValueError, match="different instrument"):
        complete_page_rounds(page, result, support, config=replace(config, setup_pointer="b" * 64),
                             ask_fn=fake, check_support=lambda *_: ())
    assert not fake.calls


def test_support_callback_cannot_silently_omit_new_answer(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    with pytest.raises(ValueError, match="exactly the requested"):
        complete_page_rounds(page, result, support, ask_fn=fake, config=config, check_support=lambda *_: ())


def test_activity_resume_finishes_new_question_then_its_descendant(rules):
    # Reduced synthetic graph tests traversal; the signed production set is untouched.
    text = "The city adopted an AI policy for its chatbot."
    page = Pass1Page("p", "i", "City", "https://city.example", "City", text,
                     (Chunk("p:0", "p", 0, len(text), text, 20),), (), "confirms_activity", None)
    span = ActivitySpan("a", "p:0", 0, len(text), "resolved", "The", "chatbot.", ())
    inp = ac.ActivityPageInput(page, "X", "local", (span,))
    qset = deepcopy(load_set("activity"))
    keep = {"core.activity_type", "core.model_origin", "core.deployment_scale_unit"}
    qset["questions"] = [q for q in qset["questions"] if q["question_id"] in keep]
    qset["pair_questions"] = []
    child = next(q for q in qset["questions"] if q["question_id"] == "core.deployment_scale_unit")
    child["gate"] = {"item": "core.model_origin", "values": ["open_weight"], "gated_out_value": "not_asked"}
    config = ac.ActivityCoderConfig(rules, "a" * 64, "jev-fixture", ac.part_combine_adapter(), 2026,
                                    question_set=qset)
    fake = Jev({"core.activity_type": "policy_guidance", "core.model_origin": "open_weight"})
    result = ac.code_page(inp, fake, config)
    support = tuple(Support(r.item_id, r.chunk_id, "downgraded_no_quote", r.item_part, "a")
                    for r in result.activities[0].records if r.coder_type == "classifier")
    fake.calls.clear()
    saved = []
    def checkpoint(updated, checked):
        saved.append((ac.PageActivityResult.from_json(json.dumps(updated.to_dict())), checked))
        raise KeyboardInterrupt
    checked_items = []
    def check(_, records):
        checked_items.extend(r.question_id for _, r in records)
        return [Support(r.item_id, r.chunk_id, part=r.item_part, activity_id=aid) for aid, r in records]
    with pytest.raises(KeyboardInterrupt):
        complete_activity_rounds(inp, result, support, ask_fn=fake, config=config,
                                 check_support=check, checkpoint=checkpoint)
    assert [next(iter(q)) for _, q in fake.calls] == ["core.model_origin"]
    done = complete_activity_rounds(inp, *saved[-1], ask_fn=fake, config=config, check_support=check)
    assert done.complete
    assert [next(iter(q)) for _, q in fake.calls] == ["core.model_origin", "core.deployment_scale_unit"]
    assert checked_items == ["core.model_origin", "core.deployment_scale_unit"]
    assert done.final[0].outcomes["core.deployment_scale_unit"].state == "combined"

@pytest.mark.parametrize("kind", ["page", "activity"])
def test_resume_after_recoverable_provider_failure_finishes_without_repeating_saved_answer(monkeypatch, rules, kind):
    if kind == "page":
        inp, result, support, config, fake = page_case(monkeypatch, rules)
        execute = complete_page_rounds
        def check(_, records):
            return [Support(r.item_id, r.chunk_id) for r in records]
    else:
        inp, result, support, config, fake = activity_case(rules)
        execute = complete_activity_rounds
        def check(_, records):
            return [Support(r.item_id, r.chunk_id, part=r.item_part, activity_id=aid) for aid, r in records]
    attempts = []
    def fail_second(state, questions):
        attempts.append((state, questions))
        if len(attempts) == 2:
            raise RuntimeError("temporary offline fixture failure")
        return fake(state, questions)
    held = execute(inp, result, support, ask_fn=fail_second, config=config, check_support=check)
    assert not held.complete
    assert len(fake.calls) == 1
    done = execute(inp, held.result, held.support, ask_fn=fake, config=config, check_support=check)
    assert done.complete
    if kind == "page":
        assert len(fake.calls) == 2
        records = [r for r in done.result.records if r.coder_type == "classifier"]
        keys = [(r.question_id, r.chunk_id) for r in records]
    else:
        keys = [(a.activity_id, r.question_id, r.chunk_id, a.record_links.get(i))
                for a in done.result.activities for i, r in enumerate(a.records)
                if r.coder_type == "classifier"]
    assert len(keys) == len(set(keys))
    assert done.result.failures == held.result.failures

def test_activity_checkpoint_roundtrip_retains_pair_and_refuses_missing_positions(rules):
    _, result, _, _, _ = activity_case(rules)
    raw = json.loads(json.dumps(result.to_dict()))
    assert ac.PageActivityResult.from_dict(raw) == result
    del raw["activities"][0]["part_indices"]
    with pytest.raises(ValueError, match="lacks original part_indices"):
        ac.PageActivityResult.from_dict(raw)

class OverLimit(Exception):
    """Offline stand-in for the provider's 400 ``max_tokens_exceeded`` rejection."""
    status = 400
    body = {"error_type": "max_tokens_exceeded"}


def _over_limit(*_):
    raise OverLimit("part exceeds the token limit")


def _activity_check(_, records):
    return [Support(r.item_id, r.chunk_id, part=r.item_part, activity_id=aid) for aid, r in records]


def test_activity_over_limit_part_is_failed_vote_and_question_combines(rules):
    # RC-D-024 item 9: not halved, recorded as failed part jev_request_failed, then combined.
    inp, result, support, config, _ = activity_case(rules)
    calls = []
    def ask(state, questions):
        calls.append((state["page_text"], tuple(questions)))
        _over_limit()
    done = complete_activity_rounds(inp, result, support, ask_fn=ask, config=config,
                                    check_support=_activity_check)
    assert done.complete
    # One request per (activity part, newly opened question): no halving, no retry.
    assert len(calls) == len(set(calls)) and all(len(q) == 1 for _, q in calls)
    new = done.result.failures[len(result.failures):]
    assert len(new) == len(calls)
    assert {("a", ("core.model_origin",)), ("b", ("core.model_origin",))} <= {
        (f.activity_id, f.question_ids) for f in new}
    assert all(f.reason == ac.REQUEST_FAILED and f.chunk_id == "p:0" and f.linked_activity is None
               and f.detail.startswith("over_limit") and "OverLimit" in f.detail for f in new)
    finals = {a.activity_id: a.outcomes for a in done.final}
    for a in done.result.activities:
        for f in (f for f in new if f.activity_id == a.activity_id):
            (qid,) = f.question_ids
            for o in (a.outcomes[qid], finals[a.activity_id][qid]):
                assert o.state == "combined" and o.failed and o.cause == ac.REQUEST_FAILED
                assert not (o.note or "").startswith("extra_round_failed")


def test_activity_other_extra_round_exception_is_still_held(rules):
    inp, result, support, config, _ = activity_case(rules)
    done = complete_activity_rounds(inp, result, support, config=config,
                                    ask_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("offline failure")),
                                    check_support=_activity_check)
    assert not done.complete
    held = [a.outcomes["core.model_origin"] for a in done.result.activities
            if a.outcomes.get("core.model_origin") is not None]
    assert held and held[0].state == "pending" and held[0].note.startswith("extra_round_failed:")
    assert done.result.failures[-1].reason == "extra_round_failed"


def test_activity_resume_after_over_limit_sends_nothing_again(rules):
    inp, result, support, config, _ = activity_case(rules)
    saved = []
    def checkpoint(updated, checked):
        saved.append((ac.PageActivityResult.from_json(json.dumps(updated.to_dict())), checked))
        raise KeyboardInterrupt  # interrupted right after the first over-limit vote is saved
    calls = []
    def ask(state, questions):
        calls.append((state["page_text"], tuple(questions)))
        _over_limit()
    with pytest.raises(KeyboardInterrupt):
        complete_activity_rounds(inp, result, support, ask_fn=ask, config=config,
                                 check_support=_activity_check, checkpoint=checkpoint)
    assert len(calls) == 1
    first = calls[0]
    resumed = complete_activity_rounds(inp, *saved[-1], ask_fn=ask, config=config,
                                       check_support=_activity_check)
    assert resumed.complete
    assert first not in calls[1:]  # the over-limit part was not resent
    assert len(calls) == len(set(calls))
    uninterrupted = complete_activity_rounds(inp, result, support, ask_fn=_over_limit, config=config,
                                             check_support=_activity_check)
    assert resumed.final == uninterrupted.final
    assert resumed.result == uninterrupted.result
    again = complete_activity_rounds(inp, resumed.result, resumed.support, config=config,
                                     ask_fn=lambda *_: pytest.fail("resume must send nothing"),
                                     check_support=_activity_check)
    assert again.final == resumed.final and again.result == resumed.result and again.rounds == 0


def test_activity_transient_hold_then_over_limit_on_resume_is_a_request_failed_vote(rules):
    """QA4 L3: a part first held by a transient failure (``extra_round_failed``) and rejected as
    over the limit on resume votes with cause ``jev_request_failed``, not the earlier hold's."""
    inp, result, support, config, _ = activity_case(rules)
    held = complete_activity_rounds(inp, result, support, config=config,
                                    ask_fn=lambda *_: (_ for _ in ()).throw(RuntimeError("transient")),
                                    check_support=_activity_check)
    assert not held.complete and held.result.failures[-1].reason == "extra_round_failed"
    held_key = (held.result.failures[-1].activity_id, held.result.failures[-1].question_ids,
                held.result.failures[-1].chunk_id)
    done = complete_activity_rounds(inp, held.result, held.support, ask_fn=_over_limit, config=config,
                                    check_support=_activity_check)
    assert done.complete
    # The transient failure stays in the history; the over-limit one is recorded after it.
    keys = [(f.activity_id, f.question_ids, f.chunk_id, f.reason) for f in done.result.failures]
    assert (*held_key, "extra_round_failed") in keys and (*held_key, ac.REQUEST_FAILED) in keys
    aid, (qid,), _ = held_key
    finals = {a.activity_id: a.outcomes for a in done.final}
    act = next(a for a in done.result.activities if a.activity_id == aid)
    for o in (act.outcomes[qid], finals[aid][qid]):
        assert o.state == "combined" and o.failed and o.cause == ac.REQUEST_FAILED


def test_page_extra_round_over_limit_everywhere_halves_to_depth_then_stops(monkeypatch, rules):
    # RC-D-023 B-Q6: no longer held. Every part is halved to the depth limit, every leaf
    # request records jev_part_over_limit, and all verdict leaves failing stops the page.
    page, result, support, config, _ = page_case(monkeypatch, rules)
    config = replace(config, max_split_depth=1)
    done = complete_page_rounds(page, result, support, config=config, ask_fn=_over_limit,
                                check_support=lambda *_: pytest.fail("no answer to check"))
    assert not done.complete
    assert [c.chunk_id for c in done.result.chunks] == ["p:0.1", "p:0.2", "p:1.1", "p:1.2"]
    assert not [r for r in done.result.records if r.coder_type == "classifier"]
    scope = done.result.items[SCOPE]
    assert scope.state == "stopped" and scope.error.startswith(HALVING_STOP) and "4/4 verdict" in scope.error
    assert done.result.failures[-1]["reason"] == HALVING_STOPPED
    over = {f["chunk_id"] for f in done.result.failures if f["reason"] == pc.OVER_LIMIT and SCOPE in f["question_ids"]}
    assert over == {"p:0.1", "p:0.2", "p:1.1", "p:1.2"}


# --- page halving in extra rounds (RC-D-023 B-Q6, RC-D-024 item 6; tests owed per RC-D-024 l.39) ---

SCOPE = "core.disclosure_scope"  # the extra question page_case opens
VERDICT = "core.page_verdict"


def _page_check(_, records):
    return [Support(r.item_id, r.chunk_id) for r in records]


def _calls(fake):
    return [(s["page_part"], frozenset(q)) for s, q in fake.calls]


def _over_for(fake, test):
    """jev stand-in: over the limit when ``test(state, questions)``, else the fixture's answer."""
    rejected = []

    def ask(state, questions):
        if test(state, questions):
            rejected.append((state["page_part"], state["page_text"], frozenset(questions)))
            raise OverLimit("part exceeds the token limit")
        return fake(state, questions)

    ask.rejected = rejected
    return ask


def _no_calls(page, done, config):
    return complete_page_rounds(page, done.result, done.support, config=config,
                                ask_fn=lambda *_: pytest.fail("resent"),
                                check_support=lambda *_: pytest.fail("rechecked"))


def test_page_over_limit_part_is_halved_and_its_earlier_requests_reasked_on_the_halves(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    second = result.chunks[1]
    ask = _over_for(fake, lambda s, q: set(q) == {SCOPE} and s["page_text"] == second.text)
    checked = []

    def check(_, records):
        checked.extend((r.item_id, r.chunk_id) for r in records)
        return _page_check(_, records)

    done = complete_page_rounds(page, result, support, ask_fn=ask, config=config, check_support=check)
    assert done.complete
    # Leaf layout: the untouched part keeps its id, the halved part becomes two leaves.
    assert [c.chunk_id for c in done.result.chunks] == ["p:0", "p:1.1", "p:1.2"]
    assert done.result.chunks[1:] == halve_chunk(second)
    assert ask.rejected == [("2 of 2", second.text, frozenset({SCOPE}))]
    # Every earlier request of the halved part is asked again on each half, in round order, with
    # the halves' new i-of-n labels; then the extra question. The untouched part is not re-asked.
    first_round = [frozenset(e["question_ids"]) for e in result.requests
                   if e["chunk_id"] == "p:1" and e["outcome"] == "ok"]
    assert first_round
    expected = [("1 of 2", frozenset({SCOPE}))]
    for label in ("2 of 3", "3 of 3"):
        expected += [(label, g) for g in first_round] + [(label, frozenset({SCOPE}))]
    assert _calls(fake) == expected
    # Untouched part retains its answers; the halved part's records are superseded, not deleted.
    before_p0 = [r for r in result.records if r.chunk_id == "p:0"]
    assert [r for r in done.result.records if r.chunk_id == "p:0"][:len(before_p0)] == before_p0
    halved = [r for r in result.records if r.coder_type == "classifier" and r.chunk_id == "p:1"]
    assert list(done.result.superseded[len(result.superseded):]) == halved
    assert not any(r.chunk_id == "p:1" for r in done.result.records)
    log = [e for e in done.result.requests if e.get("outcome") == "halved"]
    assert len(log) == 1 and log[0]["chunk_id"] == "p:1" and log[0]["halves"] == ["p:1.1", "p:1.2"]
    assert [frozenset(g["question_ids"]) for g in log[0]["reask"]] == first_round
    assert {e["page_part"] for e in done.result.requests if e.get("reasked")} == {"2 of 3", "3 of 3"}
    # Every new answer, re-asked or extra, is support-checked before finalization.
    new = {(r.item_id, r.chunk_id) for r in done.result.records
           if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED
           and (r.chunk_id != "p:0" or r.item_id == SCOPE)}
    assert set(checked) == new and len(checked) == len(new)
    assert done.final.items[SCOPE].state == "combined"


@pytest.mark.parametrize("interrupt", ["after_halving", "after_first_reask"])
def test_page_halving_resume_finishes_owed_reasks_without_resending(monkeypatch, rules, interrupt):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    second_text = result.chunks[1].text

    def over(s, q):
        return set(q) == {SCOPE} and s["page_text"] == second_text

    def reached(updated):
        if interrupt == "after_halving":
            return any(e.get("outcome") == "halved" for e in updated.requests)
        return sum(1 for e in updated.requests if e.get("reasked")) == 1

    saved, stops = [], []

    def checkpoint(updated, checked):
        saved.append((pc.PageCodeResult.from_json(updated.to_json()), checked))
        if reached(updated) and not stops:
            stops.append(True)
            raise KeyboardInterrupt

    ask = _over_for(fake, over)
    with pytest.raises(KeyboardInterrupt):
        complete_page_rounds(page, result, support, ask_fn=ask, config=config,
                             check_support=_page_check, checkpoint=checkpoint)
    resumed = complete_page_rounds(page, *saved[-1], ask_fn=ask, config=config, check_support=_page_check)
    assert resumed.complete
    calls = _calls(fake)
    assert len(calls) == len(set(calls))
    assert len(ask.rejected) == 1  # the over-limit part is not sent again after the halving
    ref_page, ref_result, ref_support, ref_config, ref_fake = page_case(monkeypatch, rules)
    ref = complete_page_rounds(ref_page, ref_result, ref_support, ask_fn=_over_for(ref_fake, over),
                               config=ref_config, check_support=_page_check)
    assert calls == _calls(ref_fake)
    assert resumed.result.to_json() == ref.result.to_json()
    assert resumed.final == ref.final
    again = _no_calls(page, resumed, config)
    assert again.complete and again.rounds == 0 and again.final == resumed.final


def test_page_halving_depth_limit_records_over_limit_votes_and_successful_part_combines(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    config = replace(config, max_split_depth=1)
    ask = _over_for(fake, lambda s, q: set(q) == {SCOPE} and "FIRST" not in s["page_text"])
    done = complete_page_rounds(page, result, support, ask_fn=ask, config=config, check_support=_page_check)
    assert done.complete
    assert [c.chunk_id for c in done.result.chunks] == ["p:0", "p:1.1", "p:1.2"]
    assert len(ask.rejected) == 3  # p:1, then each depth-limit half once
    over = [f for f in done.result.failures if f["reason"] == pc.OVER_LIMIT]
    assert [(f["chunk_id"], f["question_ids"]) for f in over] == [("p:1.1", [SCOPE]), ("p:1.2", [SCOPE])]
    # One successful part of three: first_section takes it; the failed leaves vote unknown.
    for o in (done.result.items[SCOPE], done.final.items[SCOPE]):
        assert o.state == "combined" and o.value == "single_institution" and o.part_id == "p:0"
    again = _no_calls(page, done, config)
    assert again.complete and again.rounds == 0 and again.final == done.final


@pytest.mark.parametrize(("failing", "stopped"), [(2, False), (3, True)])
def test_page_halving_verdict_failure_share_counts_leaf_parts(monkeypatch, rules, failing, stopped):
    # RC-D-024 l.39: 2/4 versus 3/4 failed verdict parts on the layout halved in an extra round.
    page, result, support, config, fake = page_case(monkeypatch, rules)
    config = replace(config, max_split_depth=1)
    originals = {c.text for c in result.chunks}
    leaves = [h.text for c in result.chunks for h in halve_chunk(c)]
    assert len(set(leaves)) == 4
    bad = set(leaves[:failing])

    def over(s, q):
        return (set(q) == {SCOPE} and s["page_text"] in originals) or (VERDICT in q and s["page_text"] in bad)

    done = complete_page_rounds(page, result, support, ask_fn=_over_for(fake, over), config=config,
                                check_support=_page_check)
    assert [c.chunk_id for c in done.result.chunks] == ["p:0.1", "p:0.2", "p:1.1", "p:1.2"]
    failed = {f["chunk_id"] for f in done.result.failures
              if f["reason"] == pc.OVER_LIMIT and VERDICT in f["question_ids"]}
    assert len(failed) == failing
    if stopped:
        assert not done.complete
        scope = done.result.items[SCOPE]
        assert scope.state == "stopped" and scope.error.startswith(HALVING_STOP) and "3/4 verdict" in scope.error
        assert done.result.failures[-1]["reason"] == HALVING_STOPPED
        again = _no_calls(page, done, config)
        assert not again.complete and again.result == done.result
    else:
        assert done.complete
        assert done.final.items[VERDICT].value == "confirms_activity"
        assert not any((o.error or "").startswith(HALVING_STOP) for o in done.final.items.values())


def test_page_halving_that_changes_provisional_verdict_stops_with_gates_pending(monkeypatch, rules):
    # Unruled cascade: the stored first-round extractor request was planned on the earlier verdict.
    page, result, support, config, fake = page_case(monkeypatch, rules)
    originals = {c.text for c in result.chunks}
    fake.choices[VERDICT] = lambda s: "confirms_activity" if s["page_text"] in originals else "background_only"
    ask = _over_for(fake, lambda s, q: set(q) == {SCOPE} and s["page_text"] in originals)
    done = complete_page_rounds(page, result, support, ask_fn=ask, config=config,
                                check_support=lambda *_: pytest.fail("no support check on a stopped page"))
    assert not done.complete
    scope = done.result.items[SCOPE]
    assert scope.state == "stopped" and scope.error.startswith(HALVING_STOP) and VERDICT in scope.error
    assert done.result.items[VERDICT] == result.items[VERDICT]  # provisional verdict not rewritten
    assert done.final.items[VERDICT].state == "pending"  # the halves' answers are not support-checked
    gated = [q["item_id"] for q in load_set("page")["questions"]
             if isinstance(q.get("gate"), dict) and q["gate"]["item"] == VERDICT]
    assert gated and all(done.final.items[i].state == "pending" for i in gated)
    again = _no_calls(page, done, config)
    assert not again.complete and again.result == done.result


def test_page_halving_transient_reask_failure_holds_then_resumes(monkeypatch, rules):
    page, result, support, config, fake = page_case(monkeypatch, rules)
    second_text = result.chunks[1].text
    ask = _over_for(fake, lambda s, q: set(q) == {SCOPE} and s["page_text"] == second_text)

    def flaky(state, questions):
        if state["page_part"] == "3 of 3" and VERDICT in questions:
            raise RuntimeError("temporary offline fixture failure")
        return ask(state, questions)

    held = complete_page_rounds(page, result, support, ask_fn=flaky, config=config, check_support=_page_check)
    assert not held.complete
    assert held.result.items[SCOPE].note.startswith("extra_round_failed:")
    f = held.result.failures[-1]
    assert (f["chunk_id"], f["group"], f["question_ids"], f["reason"]) == (
        "p:1.2", "main", [VERDICT], "extra_round_failed")
    assert held.final.items[VERDICT].state == "pending"  # p:1.1's re-asked answers await the check
    sent = len(fake.calls)
    done = complete_page_rounds(page, held.result, held.support, ask_fn=ask, config=config,
                                check_support=_page_check)
    assert done.complete
    calls = _calls(fake)
    assert len(calls) == len(set(calls))
    assert calls[sent:] and all(label == "3 of 3" for label, _ in calls[sent:])
