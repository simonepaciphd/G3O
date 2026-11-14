"""PI ruling 104 b (2026-11-14): the 41 a ``pi_release.json`` also authorises ONE live re-ask of a request key
held under 98 b (stage ``pass2_request_not_journaled``). PI ruling 103 b: a 97 b page-data hold stays
unreleasable by ``pi_release.json``.

No network: every extractor / jev / X35 answer is a fake. Covers the journal's re-ask authorisation (used up by
the one live call it allows, also across a reload), the per-page stage end to end (98 b hold -> release -> one
live call), a second re-ask refused (also when the same release bytes are dropped again, ruling 47.2 a), unknown
keys refused loudly, and the 97 b hold that no release key names.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from g3o.common.paths import institution_dir
from g3o.extract.anthropic_client import ExtractorJob, ExtractorResult
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from tests.test_e2e_perpage_v27 import (  # noqa: F401 - _paragraph_layout is an autouse fixture
    ANSWERS,
    RELATIONS,
    FakeJev,
    _paragraph_layout,
)
from tests.test_perpage_providers_v27 import (
    PASS2,
    USAGE,
    BadResponse,
    FakeEntail,
    FakeExtractor,
    _held,
    _providers,
    _run,
    _world,
)

INST = "INST-0000001"
PROMPT = {"extractor_model": "m"}


def _release_doc(keys, date="2026-11-14"):
    return {"released_by": "PI", "date": date, "keys": keys}


def _write_release(run_dir, doc):
    path = institution_dir(run_dir, INST) / pp.PI_RELEASE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _entries(run_dir):
    text = (institution_dir(run_dir, INST) / pp.WORK_DIR / pp.JOURNAL).read_text(encoding="utf-8")
    return [json.loads(x) for x in text.splitlines()]


# ---------------------------------------------------------------------------
# The journal: one re-ask per release entry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("success", [True, False])
def test_release_entry_authorises_exactly_one_live_call_of_its_key(tmp_path, success):
    job = ExtractorJob("cid-98b", {"model": "m", "messages": [{"p": 2}]}, {})
    other = ExtractorJob("cid-other", {"model": "m", "messages": [{"p": 3}]}, {})
    path = tmp_path / "journal.jsonl"
    result = (ExtractorResult("cid-98b", True, "{}", None, "fake-extractor-response", "msg-1", "x-1", "end_turn",
                              dict(USAGE)) if success
              else ExtractorResult("cid-98b", False, None, {"type": "errored"}, usage=dict(USAGE)))
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(PROMPT)
    calls = []
    fn = wrap(lambda j: calls.append(j.custom_id) or result)
    key, recorded = fn.peek(job)
    other_key = fn.peek(other)[0]
    assert not recorded and not journal.reask_authorised(key)
    journal.record_release({**_release_doc([key]), "all": False, "file_sha256": "e" * 64, "reask_keys": [key]})
    assert journal.reask_authorised(key) and fn.peek(job) == (key, True)
    assert fn.peek(other) == (other_key, False)  # only the named key
    assert rt.RequestJournal(path, {"s": 1}).reask_authorised(key)  # recorded: survives a reload unused
    fn(job)  # the one live re-ask
    assert calls == ["cid-98b"] and not journal.reask_authorised(key)
    reloaded = rt.RequestJournal(path, {"s": 1})
    assert not reloaded.reask_authorised(key) and reloaded.release_applied("e" * 64)
    wrap2, _ = reloaded.seams(PROMPT)
    fn2 = wrap2(lambda j: calls.append(j.custom_id) or result)
    # a recorded answer replays; a failed one leaves no authorisation for a second live call
    assert fn2.peek(job) == (key, success)


def test_release_without_reask_keys_authorises_nothing(tmp_path):
    """A 41 a release (rejection keys or ``all``), and an entry written before 104 b, authorise no re-ask."""
    path = tmp_path / "journal.jsonl"
    journal = rt.RequestJournal(path, {"s": 1})
    journal.record_release({"keys": None, "all": True, "released_by": "PI", "date": "2026-11-14",
                            "file_sha256": "a" * 64})
    journal.record_release({**_release_doc(["b" * 64]), "all": False, "file_sha256": "c" * 64})
    reloaded = rt.RequestJournal(path, {"s": 1})
    assert not reloaded.reask_authorised("b" * 64) and not reloaded._reask


# ---------------------------------------------------------------------------
# The per-page stage end to end
# ---------------------------------------------------------------------------


def _held_98b(tmp_path):
    """A first full run, then its pass-2 page responses dropped from the journal: the resumed run holds
    the institution under 98 b (no pass-2 call). Returns the run pieces and that hold."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    one = [i for i in insts if i.institution_id == INST]

    def run(extract):
        return _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, extract, FakeEntail()),
                    FakeJev(ANSWERS, RELATIONS))

    ex1 = FakeExtractor(world)
    ready, _ = run(ex1)
    assert [i.institution_id for i in ready] == [INST]
    pass2 = {j.custom_id for j in ex1.jobs if j.metadata["stage"] == PASS2}
    journal = institution_dir(run_dir, INST) / pp.WORK_DIR / pp.JOURNAL
    lines = journal.read_text(encoding="utf-8").splitlines()
    kept = [x for x in lines if not (json.loads(x)["kind"] == "extract"
                                     and json.loads(x)["response"]["custom_id"] in pass2)]
    assert len(kept) < len(lines)
    journal.write_text("".join(x + "\n" for x in kept), encoding="utf-8")
    ex2 = FakeExtractor(world)
    ready, metrics = run(ex2)
    assert ready == [] and metrics.held == [INST] and PASS2 not in ex2.stages()
    (hold,) = _held(run_dir, INST)["held"]
    assert hold["stage"] == pp.PASS2_NOT_JOURNALED and "104 b" in hold["error"]
    return run_dir, world, run, hold


def _calls(extract, custom_id):
    return [j for j in extract.jobs if j.metadata["stage"] == PASS2 and j.custom_id == custom_id]


def test_pi_release_authorises_one_live_reask_of_a_98b_hold(tmp_path):
    run_dir, world, run, hold = _held_98b(tmp_path)
    key, cid = hold["request_key"], hold["custom_id"]
    release = _write_release(run_dir, _release_doc([key]))
    ex3 = FakeExtractor(world)
    ready, metrics = run(ex3)
    assert len(_calls(ex3, cid)) == 1  # the one live re-ask
    assert not release.exists()
    archived = institution_dir(run_dir, INST) / "archive" / pp.PI_RELEASE_ARCHIVE / "001" / pp.PI_RELEASE_FILE
    assert json.loads(archived.read_text(encoding="utf-8"))["keys"] == [key]
    (entry,) = [e for e in _entries(run_dir) if e["kind"] == rt.PI_RELEASED]
    assert entry["response"]["reask_keys"] == [key]
    assert not rt.RequestJournal(institution_dir(run_dir, INST) / pp.WORK_DIR / pp.JOURNAL, {}).reask_authorised(key)
    if metrics.held:  # another page's pass-2 request may be held next; never this key again
        assert all(h.get("request_key") != key for h in _held(run_dir, INST)["held"])
    # the re-asked answer is journaled: a later run replays it, no further call
    ex4 = FakeExtractor(world)
    run(ex4)
    assert _calls(ex4, cid) == []


def test_second_reask_is_refused_after_the_one_release_is_used(tmp_path):
    """The re-ask is used up by its call even when that call's answer is rejected: the next run holds under
    98 b again with no call; the same release bytes dropped again are only archived (ruling 47.2 a)."""
    run_dir, world, run, hold = _held_98b(tmp_path)
    key, cid, page = hold["request_key"], hold["custom_id"], hold["page_id"]
    doc = _release_doc([key])
    _write_release(run_dir, doc)
    bad = BadResponse(world, PASS2, page, "not_json", times=1)
    ready, metrics = run(bad)
    assert len(_calls(bad, cid)) == 1 and ready == [] and metrics.held == [INST]
    assert _held(run_dir, INST)["held"][0]["stage"] == pp.EXTRACT_RESPONSE_FAILED
    for _ in range(2):
        again = FakeExtractor(world)
        ready, metrics = run(again)
        assert _calls(again, cid) == [] and ready == [] and metrics.held == [INST]
        (held,) = _held(run_dir, INST)["held"]
        assert (held["stage"], held["request_key"]) == (pp.PASS2_NOT_JOURNALED, key)
        _write_release(run_dir, doc)  # the same bytes: recorded already, so only archived next run
    assert [e["kind"] for e in _entries(run_dir)].count(rt.PI_RELEASED) == 1
    # a NEW release (other bytes) is a new PI decision: one more re-ask
    _write_release(run_dir, _release_doc([key], date="2026-11-15"))
    ex = FakeExtractor(world)
    run(ex)
    assert len(_calls(ex, cid)) == 1


# ---------------------------------------------------------------------------
# Refusals: unknown keys, 97 b page-data holds (103 b)
# ---------------------------------------------------------------------------


def _apply(tmp_path, held, doc):
    inst_dir = tmp_path / "inst"
    (inst_dir / pp.WORK_DIR).mkdir(parents=True)
    if held is not None:
        (inst_dir / pp.WORK_DIR / pp.HELD_FILE).write_text(json.dumps({"institution_id": INST, "held": held}),
                                                           encoding="utf-8")
    raw = json.dumps(doc).encode("utf-8")
    (inst_dir / pp.PI_RELEASE_FILE).write_bytes(raw)
    journal = rt.RequestJournal(inst_dir / pp.WORK_DIR / pp.JOURNAL, {"s": 1})
    return inst_dir, journal, pp._apply_pi_release(inst_dir, journal), hashlib.sha256(raw).hexdigest()


KEY = "d" * 64


@pytest.mark.parametrize("held", [
    None,  # no held.json
    [],  # nothing held
    [{"page_id": "p1", "stage": pp.EXTRACT_RESPONSE_FAILED, "pass": "pass2", "custom_id": "c", "error": "x"}],
    # PI ruling 103 b: a 97 b page-data hold names no request key and is never releasable
    [{"page_id": "p1", "stage": pp.ROW_VALUE_REFUSED, "items": ["core.source_type"],
      "refusals": {"core.source_type": "x"}, "error": "x"}],
    # even if such an entry carried a request key, its stage is not releasable
    [{"page_id": "p1", "stage": pp.ROW_VALUE_REFUSED, "request_key": KEY, "items": [], "error": "x"}],
    [{"page_id": "p1", "stage": pp.PASS2_NOT_JOURNALED, "request_key": "e" * 64, "custom_id": "c", "error": "x"}],
])
def test_unknown_or_unreleasable_key_is_refused_loudly(tmp_path, held):
    inst_dir, journal, hold, sha = _apply(tmp_path, held, _release_doc([KEY]))
    assert hold["stage"] == pp.PI_RELEASE_MALFORMED and hold["error"].startswith("refused")
    assert KEY in hold["error"] and pp.PASS2_NOT_JOURNALED in hold["error"]
    assert (inst_dir / pp.PI_RELEASE_FILE).exists() and not journal.release_applied(sha)
    assert not journal.reask_authorised(KEY)


def test_98b_hold_key_is_accepted_and_all_authorises_no_reask(tmp_path):
    held = [{"page_id": "p1", "stage": pp.PASS2_NOT_JOURNALED, "request_key": KEY, "custom_id": "c", "error": "x"}]
    inst_dir, journal, hold, sha = _apply(tmp_path, held, _release_doc([KEY]))
    assert hold is None and journal.release_applied(sha) and journal.reask_authorised(KEY)
    assert not (inst_dir / pp.PI_RELEASE_FILE).exists()
    every = tmp_path / "every"
    every.mkdir()
    _, journal, hold, sha = _apply(every, held, {"released_by": "PI", "date": "2026-11-14", "all": True})
    assert hold is None and journal.release_applied(sha) and not journal.reask_authorised(KEY)


def test_page_data_hold_stays_outside_the_releasable_stages_103b():
    assert pp.REASK_RELEASABLE == frozenset({pp.PASS2_NOT_JOURNALED})
    assert pp.ROW_VALUE_REFUSED not in pp.REASK_RELEASABLE
