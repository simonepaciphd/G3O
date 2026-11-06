"""Tests for the T-021 jev pass-1 page coder (mocked jev; RS-019 pattern)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from g3o.classify import jev_page_code as jpc
from g3o.classify.questions.v27 import SIGNED_CODEBOOK_SHA256, load_set
from g3o.codebook.loader import default_codebook_path
from g3o.common.jev_client import JevAccountError, JevAnswer, JevResult
from g3o.common.jev_record import load_classifier_rules
from g3o.common.part_combine import NOT_COVERED

SETUP = "a" * 64
GENAI = "confirms_activity"
CONTACT = ("core.content_contact_named", "core.content_contact_details")


@pytest.fixture(scope="module")
def rules():
    return load_classifier_rules(default_codebook_path().read_bytes(), expected_sha256=SIGNED_CODEBOOK_SHA256)


def cfg(rules, **kw):
    return jpc.PageCoderConfig(rules=rules, setup_pointer=SETUP, configured_model="jev-test-1",
                               reserved_tokens=0, **kw)


def page(text="The council launched a ChatGPT pilot for staff.", chrome="Contact: ai@city.example", **kw):
    return jpc.PageInput(page_id="inst1:u1", institution_id="inst1", institution="City", country="X",
                         level_of_government="local", url="https://city.example/ai", title="AI",
                         text=text, chrome_text=chrome, **kw)


DEFAULTS = {
    "core.page_verdict": (GENAI, 0.95),
    "core.disclosure_form": ("mandated_report", 0.9),
    "core.page_complete": ("no", 0.9),
    "core.content_contact_named": ("yes", 0.9),
    "core.content_contact_details": ("no", 0.9),
    "core.content_data": ("no", 0.9),
    "core.disclosure_scope": ("single_institution", 0.9),
}


@dataclass
class FakeJev:
    """Answers by question id; ``by_marker`` overrides when a marker is in the part text."""

    answers: dict
    by_marker: dict | None = None
    request_id: str | None = "req"
    fail: object = None  # callable(state, questions) -> exception or None

    def __post_init__(self):
        self.calls = []

    def __call__(self, state, questions):
        self.calls.append((state, questions))
        if self.fail is not None:
            exc = self.fail(state, questions)
            if exc is not None:
                raise exc
        out = {}
        for qid, q in questions.items():
            choice, p = self.answers[qid]
            for marker, ans in (self.by_marker or {}).items():
                if marker in state["page_text"] and qid in ans:
                    choice, p = ans[qid]
            assert choice in q["criteria"], (qid, choice)
            rest = [c for c in q["criteria"] if c != choice]
            probs = {choice: p, **{c: (1 - p) / len(rest) for c in rest}}
            out[qid] = JevAnswer(qid, "choice", choice=choice, confidence=p, probabilities=probs)
        return JevResult(out, "jev-test-1-20261101", self.request_id and f"{self.request_id}{len(self.calls)}", 100, 5)


class OverLimit(Exception):
    status = 400
    body = {"error": {"type": "max_tokens_exceeded"}}


def long_text(markers):
    para = "Background text about digital services in the city administration. " * 120
    return "\n\n".join(f"{m} {para}" for m in markers)


# -- single part ------------------------------------------------------------------------


def test_single_part_state_rounds_and_chrome(rules):
    fake = FakeJev(dict(DEFAULTS))
    res = jpc.code_page(page(), fake, cfg(rules))
    assert res.status == "coded" and len(res.chunks) == 1 and res.chunks[0].chunk_id == "inst1:u1#p001"
    rounds = [sorted(q) for _, q in fake.calls]
    assert rounds[0] == ["core.page_verdict"]
    st0 = fake.calls[0][0]
    assert list(st0) == ["coder_instructions", "institution", "country", "level_of_government",
                         "page_url", "page_title", "page_part", "page_text"]
    assert st0["page_part"] == "1 of 1" and st0["coder_instructions"] == load_set("page")["system_prompt"]
    assert all(NOT_COVERED not in q["criteria"] for _, qs in fake.calls for q in qs.values())
    # the chrome field reaches only the two contact questions
    for state, qs in fake.calls:
        if jpc.CHROME_STATE_FIELD in state:
            assert sorted(qs) == sorted(CONTACT) and state[jpc.CHROME_STATE_FIELD] == "Contact: ai@city.example"
        else:
            assert not set(qs) & set(CONTACT)
    asked = {qid for _, qs in fake.calls for qid in qs}
    assert "core.source_type" not in asked and "core.source_type" in res.skipped_questions
    assert asked == set(DEFAULTS)
    assert res.chrome_status == "sent"
    assert res.verdict.value == GENAI and res.items["core.disclosure_scope"].value == "single_institution"
    r = next(r for r in res.records if r.item_id == "core.page_verdict")
    assert r.request_id == "req1" and r.actual_response_model == "jev-test-1-20261101"
    assert r.configured_model == "jev-test-1" and r.chunk_id == "inst1:u1#p001" and r.downgraded is False


def test_round_order_follows_gates(rules):
    fake = FakeJev(dict(DEFAULTS))
    jpc.code_page(page(), fake, cfg(rules))
    qs = load_set("page")["questions"]
    rnd = {q["question_id"]: q["round"] for q in qs}
    seen = [max(rnd[q] for q in call) for _, call in fake.calls]
    assert seen == sorted(seen)


def test_chrome_not_measured_joins_main_request(rules):
    fake = FakeJev(dict(DEFAULTS))
    res = jpc.code_page(page(chrome=None), fake, cfg(rules))
    assert res.chrome_status == "not_measured"
    assert all(jpc.CHROME_STATE_FIELD not in s for s, _ in fake.calls)
    assert any(set(CONTACT) <= set(q) for _, q in fake.calls)


def test_non_genai_page_gates_out_dependents(rules):
    fake = FakeJev({**DEFAULTS, "core.page_verdict": ("no_genai", 0.9),
                    "core.disclosure_form": ("informal_official", 0.9)})
    res = jpc.code_page(page(), fake, cfg(rules))
    it = res.items
    for k in ("core.content_contact_named", "core.content_contact_details", "core.content_data"):
        assert it[k].state == "gated_out" and it[k].value == "no"
        assert it[k].rule_reference == "gated_out:core.page_verdict"
    assert it["core.page_complete"].value == "not_asked"
    assert it["core.disclosure_form"].state == "combined"
    assert it["core.disclosure_scope"].value == "not_asked"
    asked = {qid for _, qs in fake.calls for qid in qs}
    assert asked == {"core.page_verdict", "core.disclosure_form"}
    mech = [r for r in res.records if r.coder_type == "mechanical"]
    assert {r.item_id for r in mech} == {"core.content_contact_named", "core.content_contact_details",
                                         "core.content_data", "core.page_complete", "core.disclosure_scope"}
    assert all(r.request_id is None and r.configured_model is None for r in mech)


def test_threshold_flags(rules):
    fake = FakeJev({**DEFAULTS, "core.page_verdict": (GENAI, 0.6), "core.disclosure_form": ("mandated_report", 0.5)})
    res = jpc.code_page(page(), fake, cfg(rules))
    v = res.verdict
    assert v.value == GENAI and v.failed and v.cause == "below_threshold"  # tag_only keeps the value
    rec = next(r for r in res.records if r.item_id == "core.page_verdict")
    assert rec.downgraded and rec.final_value == GENAI
    form = res.items["core.disclosure_form"]
    assert form.value == "unknown" and form.failed
    assert res.items["core.disclosure_scope"].state == "gated_out"  # unknown is outside the gate list


def test_readability_failure_is_mechanical(rules):
    fake = FakeJev(dict(DEFAULTS))
    res = jpc.code_page(page(text="%PDF-1.7 " + "x" * 50), fake, cfg(rules))
    assert fake.calls == []
    assert res.status == "not_assessable" and res.verdict.value == "not_assessable"
    assert res.verdict.rule_reference.startswith("readability_failure:") and "pdf_header" in res.verdict.rule_reference
    assert res.items["core.content_data"].value == "no"
    assert res.items["core.disclosure_form"].value == "not_asked"
    assert all(r.coder_type == "mechanical" for r in res.records)


# -- long pages -------------------------------------------------------------------------


def test_multi_part_combination_and_part_prompt(rules):
    text = long_text(["AAA", "BBB", "CCC"])
    fake = FakeJev({**DEFAULTS, "core.page_verdict": (NOT_COVERED, 0.9)},
                   by_marker={"BBB": {"core.page_verdict": (GENAI, 0.85), "core.page_complete": ("yes", 0.9)}})
    res = jpc.code_page(page(text=text), fake, cfg(rules, limit_tokens=20000))
    n = len(res.chunks)
    assert n >= 2
    assert "".join(c.text for c in res.chunks) == text
    st = fake.calls[0][0]
    assert st["page_part"] == f"1 of {n}" and st["part_note"] == load_set("page")["part_prompt"]["sentence"]
    assert all(NOT_COVERED in q["criteria"] for _, qs in fake.calls for q in qs.values())
    v = res.verdict
    assert v.value == GENAI and "BBB" in next(c.text for c in res.chunks if c.chunk_id == v.part_id)
    assert res.page_complete.value == "yes"
    assert {r.chunk_id for r in res.records if r.coder_type == "classifier"} == {c.chunk_id for c in res.chunks}


def test_every_part_not_covered_gives_not_assessable(rules):
    fake = FakeJev({**DEFAULTS, "core.page_verdict": (NOT_COVERED, 0.9), "core.disclosure_form": (NOT_COVERED, 0.9)})
    res = jpc.code_page(page(text=long_text(["A", "B"])), fake, cfg(rules, limit_tokens=20000))
    assert res.verdict.value == "not_assessable"
    assert res.items["core.disclosure_form"].value == "not_documented"


def test_over_limit_halves_and_reasks_earlier_rounds(rules):
    text = long_text(["AAA", "BBB"])
    hit = {"n": 0}

    def fail(state, questions):
        if "core.disclosure_form" in questions and state["page_text"].startswith("AAA") and hit["n"] == 0:
            hit["n"] += 1
            return OverLimit("max_tokens_exceeded")
        return None

    fake = FakeJev(dict(DEFAULTS), fail=fail)
    res = jpc.code_page(page(text=text), fake, cfg(rules, limit_tokens=20000))
    ids = [c.chunk_id for c in res.chunks]
    assert any(i.endswith(".1") for i in ids) and any(i.endswith(".2") for i in ids)
    assert "".join(c.text for c in res.chunks) == text
    assert res.superseded  # the halved part's round-1 answer was billed and kept
    halves = [c for c in res.chunks if c.depth == 1]
    for h in halves:  # round 1 re-asked on each half
        assert any(r.chunk_id == h.chunk_id and r.item_id == "core.page_verdict" for r in res.records)
    assert any(r["outcome"] == "over_limit" for r in res.requests)


def test_over_limit_past_depth_fails_page(rules):
    fake = FakeJev(dict(DEFAULTS), fail=lambda s, q: OverLimit("max_tokens_exceeded"))
    with pytest.raises(jpc.PageFailed) as e:
        jpc.code_page(page(), fake, cfg(rules, max_split_depth=1))
    assert e.value.reason == jpc.OVER_LIMIT


# -- failures ---------------------------------------------------------------------------


def test_missing_request_id_on_verdict_fails_page(rules):
    with pytest.raises(jpc.PageFailed) as e:
        jpc.code_page(page(), FakeJev(dict(DEFAULTS), request_id=None), cfg(rules))
    assert e.value.reason == jpc.MISSING_REQUEST_ID


def test_missing_request_id_later_enters_as_failed(rules):
    fake = FakeJev(dict(DEFAULTS))
    orig = fake.__call__

    def ask(state, questions):
        res = orig(state, questions)
        if "core.disclosure_form" in questions:
            return JevResult(res.answers, res.response_model, None, 1, 1)
        return res

    out = jpc.code_page(page(), ask, cfg(rules))
    assert out.items["core.disclosure_form"].value == "unknown" and out.items["core.disclosure_form"].failed
    f = [f for f in out.failures if f["reason"] == jpc.MISSING_REQUEST_ID]
    assert f and "core.disclosure_form" in f[0]["question_ids"]
    assert not any(r.request_id is None for r in out.records if r.coder_type == "classifier")


def test_account_error_propagates(rules):
    fake = FakeJev(dict(DEFAULTS), fail=lambda s, q: JevAccountError("402"))
    with pytest.raises(JevAccountError):
        jpc.code_page(page(), fake, cfg(rules))


def test_other_request_error_recorded(rules):
    def fail(state, questions):
        return RuntimeError("boom") if "core.content_data" in questions else None

    res = jpc.code_page(page(), FakeJev(dict(DEFAULTS), fail=fail), cfg(rules))
    assert res.items["core.content_data"].value == "unknown"
    assert any(f["reason"] == jpc.REQUEST_FAILED for f in res.failures)


# -- serialisation and adapters ---------------------------------------------------------


def test_json_round_trip(rules):
    res = jpc.code_page(page(text=long_text(["A", "B"])), FakeJev(dict(DEFAULTS)), cfg(rules, limit_tokens=20000))
    back = jpc.PageCodeResult.from_json(res.to_json())
    assert back.to_json() == res.to_json()


def test_pass1_page_adapter(rules):
    p = page(text=long_text(["A", "B"]))
    res = jpc.code_page(p, FakeJev(dict(DEFAULTS)), cfg(rules, limit_tokens=20000))
    p1 = jpc.to_pass1_page(res, p)
    assert p1.verdict == GENAI and p1.page_complete == "no"
    assert {c.chunk_id for c in p1.codes} == {c.chunk_id for c in res.chunks}
    assert all(c.value != NOT_COVERED for c in p1.codes)


# -- after the support check (PI Q2 b) -----------------------------------------------------


@dataclass
class SR:
    item_id: str
    chunk_id: str
    support_status: str
    activity_id: str | None = None


def _support(res, downgrade=()):
    return [SR(r.item_id, r.chunk_id,
               "downgraded_no_quote" if (r.item_id, r.chunk_id) in downgrade else "supported")
            for r in res.records if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED]


def test_finalize_recombines_and_regates(rules):
    text = long_text(["AAA", "BBB"])
    fake = FakeJev({**DEFAULTS, "core.page_verdict": ("background_only", 0.9)},
                   by_marker={"AAA": {"core.page_verdict": (GENAI, 0.9)}})
    c = cfg(rules, limit_tokens=20000)
    res = jpc.code_page(page(text=text), fake, c)
    assert res.verdict.value == GENAI
    first = res.chunks[0].chunk_id
    fin = jpc.finalize_page(res, _support(res, {("core.page_verdict", first)}), c)
    assert fin.items["core.page_verdict"].value == "background_only"
    assert fin.items["core.content_data"].value == "no" and fin.items["core.content_data"].state == "gated_out"
    assert fin.items["core.page_complete"].value == "not_asked"
    assert set(fin.regated) == {"core.page_complete", *CONTACT, "core.content_data"}
    # jev's raw answers stay in the records
    assert any(r.item_id == "core.content_data" for r in res.records if r.coder_type == "classifier")


def test_finalize_without_downgrades_keeps_values(rules):
    c = cfg(rules)
    res = jpc.code_page(page(), FakeJev(dict(DEFAULTS)), c)
    fin = jpc.finalize_page(res, _support(res), c)
    assert {k: v.value for k, v in fin.items.items()} == {k: v.value for k, v in res.items.items()}
    assert fin.regated == ()


def test_finalize_requires_every_support_result(rules):
    c = cfg(rules)
    res = jpc.code_page(page(), FakeJev(dict(DEFAULTS)), c)
    with pytest.raises(ValueError):
        jpc.finalize_page(res, _support(res)[1:], c)
