"""PI rulings 134 / 143 a: per-run extractor batch modes of the v2.7 per-page stage.

Fake clients only (no SDK, no network). Covers submit, poll and collect, partial failure,
expiry, resume after a crash at each point (after submit before the acknowledgement,
mid-poll, mid-collection, after collection before the request journal saved the result),
mix routing (follow-ups live) and the 130 a pricing basis.
"""
from __future__ import annotations

import json

import pytest

from g3o.common.cost_monitor import EXTRACTOR_BATCH_KEY, price_extractor_requests
from g3o.common.pricing import PRICING, anthropic_request_usd
from g3o.extract.anthropic_client import ExtractorJob, ExtractorResult, make_custom_id
from g3o.run.presweep import perpage_batch_v27 as pb
from g3o.run.presweep.stage_validate_v27 import RequestJournal

PROMPT = {"extractor_model": "claude-haiku-5-5", "x35_model": "claude-haiku-5-5"}
SETUP = {"setup_pointer": "instr-test"}
USAGE = {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 0,
         "cache_creation_input_tokens": 0}


class Crash(BaseException):
    """A process death at a chosen point (not an Exception: nothing in the code under test catches it)."""


def job(url: str, *, suffix: str = "") -> ExtractorJob:
    cid = make_custom_id("inst-1", url) + suffix
    return ExtractorJob(custom_id=cid, params={"model": "claude-haiku-5-5", "messages": [{"role": "user",
                                                                                          "content": url}]})


class FakeBatchClient:
    def __init__(self, *, statuses=("in_progress", "ended"), outcome=None, crash_after_create=False,
                 crash_on_poll=0, crash_after_results=None, drop=()) -> None:
        self.created: list[list[str]] = []
        self.drop = set(drop)  # custom ids the results stream leaves out (a short stream)
        self.statuses = list(statuses)
        self.polls = 0
        self.outcome = outcome or {}  # custom_id -> "succeeded" | "errored" | "expired" | "canceled"
        self.crash_after_create = crash_after_create
        self.crash_on_poll = crash_on_poll
        self.crash_after_results = crash_after_results
        self.result_reads = 0

    def submit_batch(self, jobs):
        self.created.append([j.custom_id for j in jobs])
        if self.crash_after_create:
            self.crash_after_create = False
            raise Crash("died after the batch was created, before its id was journaled")
        return f"msgbatch_{len(self.created)}"

    def batch_status(self, batch_id):
        self.polls += 1
        if self.crash_on_poll and self.polls == self.crash_on_poll:
            raise Crash("died mid-poll")
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]

    def batch_results(self, batch_id):
        self.result_reads += 1
        n = int(batch_id.rsplit("_", 1)[1])
        for i, cid in enumerate(self.created[n - 1]):
            if self.crash_after_results is not None and i == self.crash_after_results:
                self.crash_after_results = None
                raise Crash("died mid-collection")
            if cid in self.drop:
                continue
            kind = self.outcome.get(cid, "succeeded")
            if kind == "succeeded":
                yield ExtractorResult(cid, True, json.dumps({"answer": cid}), None, usage=dict(USAGE))
            elif kind == "errored":
                yield ExtractorResult(cid, False, None, {"type": "errored", "error_type": "api_error",
                                                         "message": "x"})
            else:
                yield ExtractorResult(cid, False, None, {"type": kind})


class LiveFn:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, j):
        self.calls.append(j.custom_id)
        return ExtractorResult(j.custom_id, True, "{}", None, usage=dict(USAGE))


def journaled(tmp_path, extractor, inst="inst-1"):
    journal = RequestJournal(tmp_path / inst / "journal.jsonl", SETUP)
    return journal, journal.seams(PROMPT)[0](extractor)


def extractor(tmp_path, client, mode=pb.MIX, live=None):
    return pb.BatchExtractor(tmp_path, live or LiveFn(), client, mode, sleep=lambda s: None)


# --- modes -----------------------------------------------------------------------


def test_mode_names_and_default_follow_ruling_134():
    assert pb.EXTRACTOR_MODES == ("all_batch", "mix", "no_batch")
    assert pb.DEFAULT_EXTRACTOR_MODE == "mix"
    with pytest.raises(ValueError, match="134"):
        pb.require_mode("batch")


def test_a_batched_mode_needs_a_batch_client(tmp_path):
    with pytest.raises(pb.BatchClientMissing):
        pb.BatchExtractor(tmp_path, LiveFn(), None, pb.MIX)
    pb.BatchExtractor(tmp_path, LiveFn(), None, pb.NO_BATCH)  # no_batch needs none


def test_mix_defers_first_round_requests_and_sends_follow_ups_live(tmp_path):
    live = LiveFn()
    ex = extractor(tmp_path, FakeBatchClient(), live=live)
    _, call = journaled(tmp_path, ex)
    first, pass2 = job("https://a.example/1"), job("https://a.example/2")
    pass2 = ExtractorJob("x27s-" + first.custom_id[4:], first.params)
    for j in (first, pass2):
        with pytest.raises(pb.BatchDeferred):
            call(j)
    follow = job("https://a.example/1", suffix="-x0123abcd")  # 46 a extra round
    activity_only = job("https://a.example/1", suffix="-a0123abcd")  # 87 c
    assert call(follow).success and call(activity_only).success
    assert live.calls == [follow.custom_id, activity_only.custom_id]
    assert ex.pending() == 2


def test_all_batch_defers_follow_ups_and_no_batch_sends_everything_live(tmp_path):
    ex = extractor(tmp_path / "a", FakeBatchClient(), pb.ALL_BATCH)
    _, call = journaled(tmp_path / "a", ex)
    with pytest.raises(pb.BatchDeferred):
        call(job("https://a.example/1", suffix="-x0123abcd"))
    live = LiveFn()
    ex = extractor(tmp_path / "n", None, pb.NO_BATCH, live=live)
    _, call = journaled(tmp_path / "n", ex)
    assert call(job("https://a.example/1")).success and len(live.calls) == 1


def test_a_pi_released_reask_is_live_in_every_mode(tmp_path):
    live = LiveFn()
    ex = extractor(tmp_path, FakeBatchClient(), pb.ALL_BATCH, live=live)
    j = job("https://a.example/1")
    assert ex.live_call(j).success and live.calls == [j.custom_id]
    assert not ex.pending()


# --- submit, poll and collect -------------------------------------------------------


def test_submit_poll_collect_and_the_result_is_journaled_once_at_batch_rates(tmp_path):
    client = FakeBatchClient(statuses=("in_progress", "in_progress", "ended"))
    live = LiveFn()
    ex = extractor(tmp_path, client, live=live)
    journal, call = journaled(tmp_path, ex)
    j = job("https://a.example/1")
    with pytest.raises(pb.BatchDeferred):
        call(j)
    assert ex.submit() == ["msgbatch_1"]
    ex.settle()
    assert client.polls == 3 and client.created == [[j.custom_id]]
    journal, call = journaled(tmp_path, ex)  # the next wave: a fresh journal over the same file
    result = call(j)
    assert result.success and result.batch_id == "msgbatch_1" and live.calls == []
    assert journal.batched == 1
    # replayed from the per-institution journal on every later load; the store is never used twice
    journal, call = journaled(tmp_path, ex)
    assert call(j).batch_id == "msgbatch_1" and journal.replayed == 1 and journal.batched == 0
    usages = journal.extractor_usages()
    assert usages == [{**USAGE, EXTRACTOR_BATCH_KEY: True}]
    priced = price_extractor_requests(usages, model="claude-haiku-5-5")
    row = PRICING["claude-haiku-5-5"]
    assert priced["rates"] == "batch" and priced["batch_calls"] == 1
    assert priced["usd"] == pytest.approx(round(anthropic_request_usd(USAGE, row, batch=True), 6), abs=1e-6)


def test_live_calls_stay_at_standard_rates_and_a_mix_is_reported(tmp_path):
    usages = [dict(USAGE), {**USAGE, EXTRACTOR_BATCH_KEY: True}]
    priced = price_extractor_requests(usages, model="claude-haiku-5-5")
    row = PRICING["claude-haiku-5-5"]
    expected = anthropic_request_usd(USAGE, row, batch=False) + anthropic_request_usd(USAGE, row, batch=True)
    assert priced["rates"] == "standard+batch" and priced["batch_calls"] == 1
    assert priced["usd"] == pytest.approx(expected, abs=1e-6)
    assert price_extractor_requests([dict(USAGE)], model="claude-haiku-5-5")["rates"] == "standard"


def test_partial_failure_errored_results_are_journaled_failed_and_priced_zero(tmp_path):
    a, b = job("https://a.example/1"), job("https://a.example/2")
    client = FakeBatchClient(outcome={b.custom_id: "errored"})
    ex = extractor(tmp_path, client)
    journal, call = journaled(tmp_path, ex)
    for j in (a, b):
        with pytest.raises(pb.BatchDeferred):
            call(j)
    ex.submit()
    ex.settle()
    journal, call = journaled(tmp_path, ex)
    assert call(a).success
    failed = call(b)
    assert not failed.success and failed.batch_id == "msgbatch_1"
    priced = price_extractor_requests(journal.extractor_usages(), model="claude-haiku-5-5")
    assert priced["unbilled_failed_calls"] == 1 and priced["calls"] == 2 and priced["usd"] is not None
    # asked again in this invocation: not resubmitted (one send per request per run)
    with pytest.raises(pb.BatchDeferred, match="next run"):
        call(b)
    assert len(client.created) == 1


def test_expired_results_are_failed_and_asked_again_on_the_next_run(tmp_path):
    j = job("https://a.example/1")
    client = FakeBatchClient(outcome={j.custom_id: "expired"})
    ex = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex)
    with pytest.raises(pb.BatchDeferred):
        call(j)
    ex.submit()
    ex.settle()
    journal, call = journaled(tmp_path, ex)
    assert call(j).error == {"type": "expired"}
    assert price_extractor_requests(journal.extractor_usages(), model="claude-haiku-5-5")["usd"] == 0
    # the next run (a new process): queued again, never replayed as final
    ex2 = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex2)
    with pytest.raises(pb.BatchDeferred, match="queued"):
        call(j)
    assert ex2.pending() == 1


# --- crash and resume -----------------------------------------------------------------


def test_crash_after_submit_before_the_ack_never_resubmits(tmp_path):
    j = job("https://a.example/1")
    client = FakeBatchClient(crash_after_create=True)
    ex = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex)
    with pytest.raises(pb.BatchDeferred):
        call(j)
    with pytest.raises(Crash):
        ex.submit()
    ex2 = extractor(tmp_path, client)  # resume
    with pytest.raises(pb.BatchSubmitUnacknowledged) as info:
        ex2.settle()
    assert info.value.custom_ids == [j.custom_id] and len(client.created) == 1
    _, call = journaled(tmp_path, ex2)
    with pytest.raises(pb.BatchDeferred, match="in flight"):  # never queued or sent again meanwhile
        call(j)
    pb.record_submit_outcome(tmp_path, info.value.seq, "msgbatch_1")  # operator: found in the console
    ex3 = extractor(tmp_path, client)
    ex3.settle()
    _, call = journaled(tmp_path, ex3)
    assert call(j).batch_id == "msgbatch_1" and len(client.created) == 1


def test_an_operator_none_outcome_requeues_the_requests(tmp_path):
    j = job("https://a.example/1")
    client = FakeBatchClient(crash_after_create=True)
    ex = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex)
    with pytest.raises(pb.BatchDeferred):
        call(j)
    with pytest.raises(Crash):
        ex.submit()
    pb.record_submit_outcome(tmp_path, 1, None)
    ex2 = extractor(tmp_path, client)
    ex2.settle()
    assert ex2.batch_owns(j)  # PI ruling 98 b / 105 b guards: known not sent live
    _, call = journaled(tmp_path, ex2)
    with pytest.raises(pb.BatchDeferred, match="queued"):
        call(j)
    assert ex2.submit() == ["msgbatch_2"]


def test_crash_mid_poll_polls_the_same_batch(tmp_path):
    j = job("https://a.example/1")
    client = FakeBatchClient(statuses=("in_progress", "in_progress", "ended"), crash_on_poll=2)
    ex = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex)
    with pytest.raises(pb.BatchDeferred):
        call(j)
    ex.submit()
    with pytest.raises(Crash):
        ex.settle()
    ex2 = extractor(tmp_path, client)
    ex2.settle()
    assert len(client.created) == 1
    _, call = journaled(tmp_path, ex2)
    assert call(j).batch_id == "msgbatch_1"


def test_crash_mid_collection_stores_each_result_once(tmp_path):
    a, b = job("https://a.example/1"), job("https://a.example/2")
    client = FakeBatchClient(crash_after_results=1)
    ex = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex)
    for j in (a, b):
        with pytest.raises(pb.BatchDeferred):
            call(j)
    ex.submit()
    with pytest.raises(Crash):
        ex.settle()
    ex2 = extractor(tmp_path, client)
    ex2.settle()
    assert client.result_reads == 2 and len(client.created) == 1
    lines = [json.loads(x) for x in pb.batch_journal_path(tmp_path).read_text(encoding="utf-8").splitlines()]
    assert sorted(e["custom_id"] for e in lines if e["kind"] == "result") == sorted([a.custom_id, b.custom_id])
    assert len(ex2.stored_batch_results(a)) == 1


def test_crash_after_collection_before_the_journal_saved_it(tmp_path):
    j = job("https://a.example/1")
    client = FakeBatchClient()
    live = LiveFn()
    ex = extractor(tmp_path, client, live=live)
    _, call = journaled(tmp_path, ex)
    with pytest.raises(pb.BatchDeferred):
        call(j)
    ex.submit()
    ex.settle()  # results stored; the process dies before the next wave journals them
    ex2 = extractor(tmp_path, client, live=live)
    ex2.settle()
    journal, call = journaled(tmp_path, ex2)
    assert call(j).batch_id == "msgbatch_1"
    assert live.calls == [] and len(client.created) == 1 and journal.batched == 1


def test_a_torn_last_batch_journal_line_is_dropped(tmp_path):
    j = job("https://a.example/1")
    ex = extractor(tmp_path, FakeBatchClient())
    _, call = journaled(tmp_path, ex)
    with pytest.raises(pb.BatchDeferred):
        call(j)
    with pb.batch_journal_path(tmp_path).open("ab") as stream:
        stream.write(b'{"kind": "submit_int')
    ex2 = extractor(tmp_path, FakeBatchClient())
    assert ex2.store.unacknowledged() == [] and ex2.batch_owns(j)


def test_a_torn_tail_is_dropped_durably_so_later_appends_reload(tmp_path):
    """Review H1: the torn tail is removed from the file (not closed off with a newline), so an append
    after it never leaves a corrupt line mid-file; every acknowledged entry survives the reloads."""
    a, b = job("https://a.example/1"), job("https://a.example/2")
    client = FakeBatchClient()
    ex = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex)
    with pytest.raises(pb.BatchDeferred):
        call(a)
    path = pb.batch_journal_path(tmp_path)
    acknowledged = path.read_bytes()
    with path.open("ab") as stream:
        stream.write(b'{"kind": "submit_int')
    ex2 = extractor(tmp_path, client)  # load: the torn tail is dropped from the file itself
    assert path.read_bytes() == acknowledged
    _, call = journaled(tmp_path, ex2)
    with pytest.raises(pb.BatchDeferred):
        call(b)  # an append after the repaired tail
    assert ex2.submit() == ["msgbatch_1"]
    ex3 = extractor(tmp_path, client)  # reload: no "corrupt batch journal line"
    assert ex3.store.in_flight() == [(1, "msgbatch_1")]
    assert sorted(cid for cid, _ in ex3.store.intents[1]) == sorted([a.custom_id, b.custom_id])
    ex3.settle()
    _, call = journaled(tmp_path, ex3)
    assert call(a).batch_id == call(b).batch_id == "msgbatch_1"


def test_a_short_results_stream_is_not_marked_collected(tmp_path):
    """Review L7: an ended batch missing a submitted result stops before ``collected``; the next run reads
    the batch again and nothing is resubmitted (no double spend)."""
    a, b = job("https://a.example/1"), job("https://a.example/2")
    client = FakeBatchClient(drop={b.custom_id})
    ex = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex)
    for j in (a, b):
        with pytest.raises(pb.BatchDeferred):
            call(j)
    ex.submit()
    with pytest.raises(pb.BatchResultsIncomplete) as info:
        ex.settle()
    assert info.value.custom_ids == [b.custom_id] and "msgbatch_1" not in ex.store.collected
    client.drop.clear()
    ex2 = extractor(tmp_path, client)
    assert ex2.batch_owns(b)  # still in flight: deferred again, never sent live
    ex2.settle()
    assert "msgbatch_1" in ex2.store.collected and len(client.created) == 1 and client.result_reads == 2
    _, call = journaled(tmp_path, ex2)
    assert call(a).batch_id == call(b).batch_id == "msgbatch_1"


def test_a_request_over_the_byte_guard_is_sent_live(tmp_path):
    """Review M3: never queued (so submit never refuses it), sent live in the same wave as before."""
    live = LiveFn()
    ex = extractor(tmp_path, FakeBatchClient(), pb.ALL_BATCH, live=live)
    _, call = journaled(tmp_path, ex)
    big = ExtractorJob(job("https://a.example/1").custom_id,
                       {"model": "claude-haiku-5-5", "messages": [{"role": "user", "content": "x" * 2_600_000}]})
    assert pb.too_big_for_batch(big)
    assert call(big).success and live.calls == [big.custom_id]
    assert ex.pending() == 0 and not ex.batch_owns(big) and ex.submit() == []


def test_batch_owns_ends_once_the_stored_result_is_journaled(tmp_path):
    """Review M5: after the request journal consumed the stored result, neither ``batch_owns`` nor ``peek``
    vouches for the request any more, so the 98 b / 105 b guards cannot let a second (live) call through."""
    j = job("https://a.example/1")
    client = FakeBatchClient(outcome={j.custom_id: "errored"})
    ex = extractor(tmp_path, client)
    _, call = journaled(tmp_path, ex)
    with pytest.raises(pb.BatchDeferred):
        call(j)
    ex.submit()
    assert ex.batch_owns(j)  # in flight
    ex.settle()
    _, call = journaled(tmp_path, ex)
    assert not ex.batch_owns(j) and call.peek(j)[1] is True  # an unused stored result: answered from the store
    assert not call(j).success  # consumed (journaled extract_failed)
    _, call = journaled(tmp_path, extractor(tmp_path, client))  # the next run
    assert call.peek(j)[1] is False


def test_peek_accepts_a_request_the_batch_journal_owns(tmp_path):
    j = job("https://a.example/1")
    ex = extractor(tmp_path, FakeBatchClient())
    journal, call = journaled(tmp_path, ex)
    assert call.peek(j)[1] is False
    with pytest.raises(pb.BatchDeferred):
        call(j)
    journal, call = journaled(tmp_path, extractor(tmp_path, FakeBatchClient()))
    assert call.peek(j)[1] is True  # queued, never sent live: not a PI ruling 98 b / 105 b hold


# --- waves ----------------------------------------------------------------------


def test_run_waves_until_nothing_is_queued(tmp_path):
    a = job("https://a.example/1")
    b = ExtractorJob("x27s-" + a.custom_id[4:], a.params)  # its pass-2 request, asked after pass 1
    client = FakeBatchClient()
    ex = extractor(tmp_path, client)
    passes: list[list[str]] = []

    def stage_pass():
        _, call = journaled(tmp_path, ex)
        done = []
        for j in (a, b):
            try:
                done.append(call(j).custom_id)
            except pb.BatchDeferred:
                break  # the institution is held; the stage goes on
        passes.append(done)
        return done

    assert pb.run_waves(ex, stage_pass) == [a.custom_id, b.custom_id]
    assert passes == [[], [a.custom_id], [a.custom_id, b.custom_id]]
    assert client.created == [[a.custom_id], [b.custom_id]]


def test_the_wave_cap_ends_the_stage_with_the_institution_held(tmp_path):
    """Review H2: reaching the cap is not an error; the institution stays held (batch pending), its last
    batch is in the journal, and the next run collects it and goes on."""
    a = job("https://a.example/1")
    b = ExtractorJob("x27s-" + a.custom_id[4:], a.params)
    client = FakeBatchClient()

    def stage_pass(ex):
        def run():
            _, call = journaled(tmp_path, ex)
            for j in (a, b):
                try:
                    call(j)
                except pb.BatchDeferred:
                    return pb.BATCH_PENDING
            return "ready"
        return run

    ex = extractor(tmp_path, client)
    assert pb.run_waves(ex, stage_pass(ex), max_waves=1) == pb.BATCH_PENDING  # held, not raised
    assert client.created == [[a.custom_id]] and ex.store.in_flight() == [(1, "msgbatch_1")]
    ex2 = extractor(tmp_path, client)  # the next run
    assert pb.run_waves(ex2, stage_pass(ex2)) == "ready"
    assert client.created == [[a.custom_id], [b.custom_id]]


def test_a_multi_page_institution_queues_every_first_round_request_in_one_wave(tmp_path, monkeypatch):
    """Review H2: a deferred page does not stop the institution's other pages; it is held (batch pending)
    once every page had its turn, naming every deferred page."""
    from types import SimpleNamespace

    from g3o.run.presweep import stage_perpage_v27 as sp

    ex = extractor(tmp_path, FakeBatchClient())
    _, call = journaled(tmp_path, ex)
    urls = [f"https://a.example/{n}" for n in range(30)]
    states = [sp._PageState(SimpleNamespace(page=SimpleNamespace(page_id=f"p{n}", institution_id="inst-1",
                                                                   url=url)))
              for n, url in enumerate(urls)]
    monkeypatch.setattr(sp.stage_page_code, "run_page_code_stage",
                        lambda *a, **k: SimpleNamespace(stopped_early=False))
    monkeypatch.setattr(sp, "artifact_exists", lambda path: True)
    monkeypatch.setattr(sp, "_rounds_for_page", lambda run_dir, st, *a, **k: call(job(st.spec.page.url)))
    hold = sp._code_states(tmp_path, states, None, ask=None, providers=None, inst_providers=None, journal=None,
                           page_config=None, activity_config=None, metrics=sp.PerPageMetrics(),
                           cost_check_callback=None)
    assert hold["stage"] == pb.BATCH_PENDING and hold["page_id"] == "p0"
    assert hold["deferred_pages"] == [f"p{n}" for n in range(30)]
    assert ex.pending() == 30
    ex.submit()
    assert ex.batches_submitted == 1


def test_run_waves_without_a_batch_extractor_is_one_pass():
    assert pb.run_waves(None, lambda: "once") == "once"


def test_the_journal_never_reads_stored_results_from_the_live_client(tmp_path):
    """Review: the live LazyExtractor's ``batch_results(batch_id)`` is the Batches API call; the journal
    reads stored results only through ``stored_batch_results``, so a no_batch run never calls it."""
    from g3o.run.presweep.v27_entry import LazyExtractor

    assert not hasattr(LazyExtractor, "stored_batch_results") and hasattr(pb.BatchExtractor, "stored_batch_results")
