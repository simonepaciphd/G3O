"""Offline execution of post-support questions, including interruption recovery."""

import json
from copy import deepcopy
from dataclasses import dataclass, replace

import pytest

from g3o.classify import jev_activity_code as ac
from g3o.classify import jev_page_code as pc
from g3o.classify.question_rounds import complete_activity_rounds, complete_page_rounds
from g3o.classify.questions.v27 import load_set
from g3o.codebook.loader import default_codebook_path
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import load_classifier_rules
from g3o.common.page_chunks import Chunk
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