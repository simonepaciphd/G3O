"""Stage 6 quote step (RC-D-028 1 a): mocked extractor and mocked X35 only.

Every extractor reply and X35 answer below is a declared fake; no client is
built and no network is opened (run under ``.github/scripts/offline.py``). The
instruction is pinned by SHA256 (RC-D-029 Q3 a): any other text must refuse.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from g3o.common.support_check import Entailment
from g3o.extract.anthropic_client import ExtractorResult
from g3o.validate import stage6_quote as sq
from g3o.validate import stage6_v27 as s6
from tests.test_stage6_v27 import REL_Q, FakeJev, merged, run, two_pages

TRUE = Entailment("true", 0.95)
SAME = {("Copilot pilot", "Copilot pilot"): ("same_activity", .95)}


class FakeExtractor:
    """Copies the candidate named by ``pick`` (default Q1) verbatim, or returns a set reply."""

    def __init__(self, pick="Q1", reply=None, fail=False):
        self.pick, self.reply, self.fail, self.jobs = pick, reply, fail, []

    def __call__(self, job):
        self.jobs.append(job)
        if self.fail:
            return ExtractorResult(job.custom_id, False, None, {"type": "refusal"})
        if self.reply is not None:
            text = json.dumps(self.reply)
        else:
            rows = json.loads(job.params["messages"][0]["content"].split("QUOTES:\n", 1)[1].split("\n\nTASK:", 1)[0])
            row = next(r for r in rows if r["quote_id"] == self.pick)
            text = json.dumps({"quote_id": self.pick, "quote": row["text"]})
        return ExtractorResult(job.custom_id, True, text, None, "fake-extractor", "msg-1", "req-1", "end_turn",
                               {"input_tokens": 1, "output_tokens": 1})


class FakeEntail:
    def __init__(self, answer=TRUE):
        self.answer, self.calls = answer, []

    def __call__(self, question, text):
        self.calls.append((question, text))
        return self.answer


def quote_fn(extractor=None, entail=None):
    return sq.make_quote_fn(extractor or FakeExtractor(), entail or FakeEntail())


# --- the approval pin (RC-D-029 O3 b, Q3 a) ------------------------------------------

APPROVED_SHA256 = "898194903d3a0c733bb4f59d9b420423388afda48eb740e666de578320f04483"
DELETED_BULLET = ("- You may leave out words inside a passage to keep it short, but every word you write "
                  "must appear in that quote.")


def test_instruction_is_the_approved_text_pinned_by_sha256():
    text = sq.STAGE6_QUOTE_INSTRUCTION
    assert sq.STAGE6_QUOTE_SHA256 == APPROVED_SHA256
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == APPROVED_SHA256
    assert text.startswith("# Stage 6 supporting text\n") and "\r" not in text
    assert "DRAFT" not in text and DELETED_BULLET not in text
    assert not hasattr(sq, "STAGE6_QUOTE_DRAFT_MARKER")
    sq.require_approved(text)


class Untouchable:
    def __getattr__(self, name):
        raise AssertionError(f"client used: {name}")


@pytest.mark.parametrize("other", [
    "DRAFT — NOT PI-APPROVED\n\n" + sq.STAGE6_QUOTE_INSTRUCTION,  # the draft marker back
    sq.STAGE6_QUOTE_INSTRUCTION.replace("- Keep the copy", DELETED_BULLET + "\n- Keep the copy"),  # bullet back
    sq.STAGE6_QUOTE_INSTRUCTION.replace("\n", "\r\n"),  # CRLF bytes
    sq.STAGE6_QUOTE_INSTRUCTION + "\n",  # one byte more
    "Approved text.",
])
def test_any_other_instruction_text_is_refused_before_a_client_exists(other):
    with pytest.raises(s6.Stage6QuoteNotApproved):
        sq.anthropic_quote_fn(FakeEntail(), client=Untouchable(), instruction=other)
    with pytest.raises(s6.Stage6QuoteNotApproved):
        sq.make_quote_fn(FakeExtractor(), FakeEntail(), instruction=other)
    sq.make_quote_fn(FakeExtractor(), FakeEntail(), instruction=other, allow_unpinned=True)  # fakes only


class FakeMessages:
    def __init__(self):
        self.params = []

    def create(self, **params):
        self.params.append(params)
        rows = json.loads(params["messages"][0]["content"].split("QUOTES:\n", 1)[1].split("\n\nTASK:", 1)[0])
        return {"stop_reason": "end_turn", "model": "fake-haiku", "id": "msg-x",
                "content": [{"type": "text", "text": json.dumps({"quote_id": "Q1", "quote": rows[0]["text"]})}]}


class FakeAnthropic:
    def __init__(self):
        self.messages = FakeMessages()


def test_paid_path_shape_with_an_approved_text_and_a_fake_client():
    client = FakeAnthropic()
    fn = sq.anthropic_quote_fn(FakeEntail(), client=client)  # the approved text, a fake client
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev(SAME), fn)
    assert result.groups == (("o1", "o2"),)
    params = client.messages.params[0]
    assert params["model"] == "claude-haiku-5-5" and params["output_config"]["effort"] == "medium"
    assert params["system"] == sq.build_system_prompt()


# --- relation answers -------------------------------------------------------------


def test_relation_quote_copied_verbatim_then_x35_merges():
    extractor, entail = FakeExtractor(), FakeEntail()
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev(SAME), quote_fn(extractor, entail))
    assert result.groups == (("o1", "o2"),)
    support = result.relation_outcomes[0].support[0]
    assert support.support_status == "supported" and support.supporting_text == quotes[0].quote_text
    user = extractor.jobs[0].params["messages"][0]["content"]
    rows = json.loads(user.split("QUOTES:\n", 1)[1].split("\n\nTASK:", 1)[0])
    assert [(r["quote_id"], r["record"]) for r in rows] == [("Q1", "first"), ("Q2", "second")]
    task = json.loads(user.split("TASK:\n", 1)[1])
    assert task == {"question": "How is the activity in the first record related to the activity in the second "
                                "record?", "answer": "same_activity"}  # the chosen answer is shown (RC-D-017 6)
    question, window = entail.calls[0]
    assert '"Copilot pilot"' in question and "the same activity" in question
    assert window == "Intro. " + quotes[0].quote_text + " End."  # quote +/- 200 chars, clipped to the part


def test_relation_copy_naming_no_shown_quote_is_no_supporting_text():
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev(SAME),
                 quote_fn(FakeExtractor(reply={"quote_id": "Q9", "quote": quotes[0].quote_text})))
    assert result.relation_outcomes[0].support[0].support_status == "downgraded_no_quote"
    assert result.groups == (("o1",), ("o2",))


def test_relation_null_copy_and_x35_false_downgrade():
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev(SAME),
                 quote_fn(FakeExtractor(reply={"quote_id": None, "quote": None})))
    assert result.relation_outcomes[0].support[0].support_status == "downgraded_no_quote"
    result = run(pages, obs, recs, quotes, FakeJev(SAME), quote_fn(entail=FakeEntail(Entailment("false", .95))))
    assert result.relation_outcomes[0].support[0].support_status == "downgraded_quote_not_stating_value"
    assert result.groups == (("o1",), ("o2",))


def test_copy_not_in_the_stored_part_skips_x35():
    entail = FakeEntail()
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev(SAME),
                 quote_fn(FakeExtractor(reply={"quote_id": "Q1", "quote": "Wholly invented sentence about robots."}),
                          entail))
    assert result.relation_outcomes[0].support[0].support_status == "downgraded_no_quote"
    assert not entail.calls  # no X35 call where T-024 does not need it


def test_failed_quote_request_holds_the_answer():
    pages, obs, recs, quotes = two_pages()
    result = run(pages, obs, recs, quotes, FakeJev(SAME), quote_fn(FakeExtractor(fail=True)))
    assert [h.reason for h in result.held] == [s6.QUOTE_STEP_FAILED]
    assert not result.ready and not result.pooled
    bad = run(pages, obs, recs, quotes, FakeJev(SAME), quote_fn(FakeExtractor(reply={"quote": "x"})))
    assert [h.reason for h in bad.held] == [s6.QUOTE_STEP_FAILED]


def test_x35_gate_error_is_not_swallowed():
    from g3o.common.support_check import run_entailment

    pages, obs, recs, quotes = two_pages()
    with pytest.raises(Exception, match="X35 entailment call not wired"):
        run(pages, obs, recs, quotes, FakeJev(SAME), quote_fn(entail=lambda q, t: run_entailment()))


# --- pooled answers -----------------------------------------------------------------


def test_pooled_answers_quoted_from_the_pool_part_and_finished():
    pages, obs, recs, quotes, jev = merged()
    extractor = FakeExtractor(pick="Q2")
    result = run(pages, obs, recs, quotes, jev, quote_fn(extractor))
    pooled = result.pooled[("o1", "o2")]
    assert pooled.finished and result.ready
    assert pooled.outcomes["core.action_type"].value == "deployment"
    supported = [sr for sr in pooled.support if sr.item_id == "core.action_type"]
    assert supported[0].support_status == "supported" and supported[0].supporting_text == quotes[1].quote_text
    pooled_jobs = [j for j in extractor.jobs if j.metadata["kind"] == "pooled"]
    rows = json.loads(pooled_jobs[0].params["messages"][0]["content"].split("QUOTES:\n", 1)[1]
                      .split("\n\nTASK:", 1)[0])
    assert all("record" not in r for r in rows) and len(rows) == 2


def test_pooled_merge_with_unlabelled_official_page_finishes_with_the_quote_step():
    pages, obs, recs, quotes, jev = merged()
    quotes = [replace(quotes[0], source_type_label=None), quotes[1]]
    recs = [replace(recs[0], quotes=(quotes[0],)), recs[1]]
    result = run(pages, obs, recs, quotes, jev, quote_fn())
    assert result.pooled[("o1", "o2")].finished and result.ready
    assert all(REL_Q in c[1] or "source_type" not in c[0]["supporting_quotes"][0] for c in jev.calls)
