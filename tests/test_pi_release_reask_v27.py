"""PI ruling 104 b (2026-11-14): the 41 a ``pi_release.json`` also authorises ONE live re-ask of a request key
held under 98 b (stage ``pass2_request_not_journaled``). PI ruling 103 b: a 97 b page-data hold stays
unreleasable by ``pi_release.json``. PI ruling 113 b: the 105 b pass-1 and activity-only holds are releasable the
same way, and the page's activity-level state is archived before that live re-ask.

No network: every extractor / jev / X35 answer is a fake. Covers the journal's re-ask authorisation (used up by
the one live call it allows, also across a reload), the per-page stage end to end (98 b hold -> release -> one
live call), a second re-ask refused (also when the same release bytes are dropped again, ruling 47.2 a), unknown
keys refused loudly, and the 97 b hold that no release key names.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from g3o.common.paths import institution_dir
from g3o.extract.anthropic_client import ExtractorJob, ExtractorResult
from g3o.extract.request_v27 import field_name
from g3o.run.presweep import perpage_providers_v27 as ppv
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from tests.test_e2e_perpage_v27 import (  # noqa: F401 - _paragraph_layout is an autouse fixture
    ANSWERS,
    RELATIONS,
    FakeJev,
    _paragraph_layout,
)
from tests.test_perpage_providers_v27 import (
    PASS1,
    PASS2,
    USAGE,
    BadResponse,
    FakeEntail,
    FakeExtractor,
    NoFirstRoundActivities,
    _flip_world,
    _flipped_round,
    _held,
    _is_activity_only,
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


class Crash(BaseException):
    """The process dies inside the extractor call (after the journal's re-ask marker)."""


@pytest.mark.parametrize("error", [Crash("killed"), TimeoutError("read timed out")])
def test_reask_is_spent_by_a_marker_written_before_the_call_114b(tmp_path, error):
    """PI ruling 114 b: the re-ask is used up by a ``reask_spent`` entry journaled BEFORE the call. A crash
    after it, or a timeout raised by the call, records no response, yet the reloaded journal no longer
    authorises a live call (peek says not recorded: the adapter holds again, no second live call). Only a
    new release (other bytes) authorises one more."""
    job = ExtractorJob("cid-114b", {"model": "m", "messages": [{"p": 4}]}, {})
    path = tmp_path / "journal.jsonl"
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(PROMPT)
    calls = []

    def raising(j):
        calls.append(j.custom_id)
        raise error
    fn = wrap(raising)
    key = fn.peek(job)[0]
    journal.record_release({**_release_doc([key]), "all": False, "file_sha256": "e" * 64, "reask_keys": [key]})
    assert fn.reask_live(job) and fn.peek(job) == (key, True)
    with pytest.raises(type(error)):
        fn(job)
    assert calls == ["cid-114b"] and not journal.reask_authorised(key)
    kinds = [json.loads(x)["kind"] for x in path.read_text(encoding="utf-8").splitlines()]
    assert kinds == [rt.PI_RELEASED, rt.REASK_SPENT]  # the marker, and no response
    reloaded = rt.RequestJournal(path, {"s": 1})
    wrap2, _ = reloaded.seams(PROMPT)
    fn2 = wrap2(lambda j: pytest.fail("no second live call"))
    assert not reloaded.reask_authorised(key) and fn2.peek(job) == (key, False) and not fn2.reask_live(job)
    assert reloaded.usage()["extractor_calls"] == 0  # the marker is not a call
    # a new release file (other bytes) is a new PI decision: one more re-ask
    reloaded.record_release({**_release_doc([key], date="2026-11-15"), "all": False, "file_sha256": "f" * 64,
                             "reask_keys": [key]})
    assert rt.RequestJournal(path, {"s": 1}).reask_authorised(key)


def test_marker_write_failure_leaves_the_reask_unspent_114b(tmp_path, monkeypatch):
    """An OSError writing the ``reask_spent`` marker propagates before the call: nothing was sent, so the
    authorisation stands."""
    job = ExtractorJob("cid-114b", {"model": "m", "messages": [{"p": 5}]}, {})
    path = tmp_path / "journal.jsonl"
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(PROMPT)
    fn = wrap(lambda j: pytest.fail("no call without the marker"))
    key = fn.peek(job)[0]
    journal.record_release({**_release_doc([key]), "all": False, "file_sha256": "e" * 64, "reask_keys": [key]})
    real = journal._write

    def failing(entry):
        if entry["kind"] == rt.REASK_SPENT:
            raise PermissionError(13, "Access is denied", str(path))
        return real(entry)
    monkeypatch.setattr(journal, "_write", failing)
    with pytest.raises(PermissionError):
        fn(job)
    assert journal.reask_authorised(key) and rt.RequestJournal(path, {"s": 1}).reask_authorised(key)


def test_identical_release_file_after_a_spent_reask_is_only_archived_114b(tmp_path):
    """Ruling 47.2 a still holds with the 114 b marker: the same release bytes dropped again after the re-ask
    was spent (here by a timeout) are only archived and authorise nothing; other bytes authorise one more."""
    job = ExtractorJob("cid-114b", {"model": "m", "messages": [{"p": 6}]}, {})
    inst_dir = tmp_path / "inst"
    (inst_dir / pp.WORK_DIR).mkdir(parents=True)
    journal = rt.RequestJournal(inst_dir / pp.WORK_DIR / pp.JOURNAL, {"s": 1})
    wrap, _ = journal.seams(PROMPT)

    def timeout(j):
        raise TimeoutError("read timed out")
    fn = wrap(timeout)
    key = fn.peek(job)[0]
    (inst_dir / pp.WORK_DIR / pp.HELD_FILE).write_text(json.dumps({"institution_id": INST, "held": [
        {"page_id": "p1", "stage": pp.PASS1_NOT_JOURNALED, "pass": "pass1", "custom_id": job.custom_id,
         "request_key": key, "error": "x"}]}), encoding="utf-8")
    doc = _release_doc([key])
    raw = json.dumps(doc).encode("utf-8")
    (inst_dir / pp.PI_RELEASE_FILE).write_bytes(raw)
    assert pp._apply_pi_release(inst_dir, journal) is None and journal.reask_authorised(key)
    with pytest.raises(TimeoutError):
        fn(job)
    assert not journal.reask_authorised(key)
    (inst_dir / pp.PI_RELEASE_FILE).write_bytes(raw)  # the same bytes again
    assert pp._apply_pi_release(inst_dir, journal) is None and not (inst_dir / pp.PI_RELEASE_FILE).exists()
    assert not journal.reask_authorised(key)
    assert not rt.RequestJournal(inst_dir / pp.WORK_DIR / pp.JOURNAL, {"s": 1}).reask_authorised(key)
    (inst_dir / pp.PI_RELEASE_FILE).write_bytes(json.dumps(_release_doc([key], date="2026-11-15")).encode("utf-8"))
    assert pp._apply_pi_release(inst_dir, journal) is None and journal.reask_authorised(key)


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
    assert KEY in hold["error"] and all(stage in hold["error"] for stage in pp.REASK_RELEASABLE)  # review L-4
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
    # PI ruling 113 b: the 105 b pass-1 and activity-only holds are releasable for one re-ask too
    assert pp.REASK_RELEASABLE == frozenset({pp.PASS2_NOT_JOURNALED, pp.PASS1_NOT_JOURNALED,
                                             pp.ACTIVITY_ONLY_NOT_JOURNALED})
    assert pp.ROW_VALUE_REFUSED not in pp.REASK_RELEASABLE


# ---------------------------------------------------------------------------
# PI ruling 113 b: a released pass-1 / activity-only re-ask archives the activity-level state first
# ---------------------------------------------------------------------------


class Renamed(FakeExtractor):
    """Pass-1 answers on ``page`` name its activities ``name``: the re-asked response's spans differ from the
    ones the stale activity state was built on."""

    def __init__(self, world, page, name):
        super().__init__(world)
        self.page, self.name = page, name

    def __call__(self, job):
        result = super().__call__(job)
        if job.metadata["stage"] != PASS1 or job.metadata["page_id"] != self.page:
            return result
        payload = json.loads(result.text)
        for act in payload["activities"]:
            for f in act["fields"]:
                if f["field"] == field_name("core.activity_name"):
                    f["value"] = self.name
        return replace(result, text=json.dumps(payload))


def _held_105b(tmp_path, page="p1"):
    """A first full run, then the page's first pass-1 (T-022 page request) response dropped from the journal:
    the resumed run holds the institution under 105 b (no pass-1 call). Returns the run pieces and that hold."""
    run_dir, bound, instrument, world, insts = _world(tmp_path)
    one = [i for i in insts if i.institution_id == INST]

    def run(extract):
        return _run(run_dir, bound, instrument, one, _providers(run_dir, bound, instrument, extract, FakeEntail()),
                    FakeJev(ANSWERS, RELATIONS))

    ex1 = FakeExtractor(world)
    ready, _ = run(ex1)
    assert [i.institution_id for i in ready] == [INST]
    first = next(j for j in ex1.jobs if j.metadata["stage"] == PASS1 and j.metadata["page_id"] == page)
    journal = institution_dir(run_dir, INST) / pp.WORK_DIR / pp.JOURNAL
    lines = journal.read_text(encoding="utf-8").splitlines()
    kept = [x for x in lines if not (json.loads(x)["kind"] == "extract"
                                     and json.loads(x)["response"]["custom_id"] == first.custom_id)]
    assert len(kept) == len(lines) - 1
    journal.write_text("".join(x + "\n" for x in kept), encoding="utf-8")
    ex2 = FakeExtractor(world)
    ready, metrics = run(ex2)
    assert ready == [] and metrics.held == [INST] and ex2.jobs == []
    (hold,) = _held(run_dir, INST)["held"]
    assert (hold["page_id"], hold["stage"], hold["pass"]) == (page, pp.PASS1_NOT_JOURNALED, "pass1")
    assert hold["custom_id"] == first.custom_id
    # review L-4: the hint names the re-ask a release of this key authorises (no longer "pass-2 only")
    assert "authorises one live re-ask" in hold["error"] and "113 b" in hold["error"]
    assert "only a pass-2" not in hold["error"]
    spec = next(s for s in one[0].pages if s.page.page_id == page)
    return run_dir, world, run, hold, spec.page


def _spy_coded(monkeypatch):
    """The T-023 inputs coded from now on (``stage_activity_code.run_stage``)."""
    from g3o.run.presweep import stage_activity_code

    coded = []
    real = stage_activity_code.run_stage

    def spy(pages, *a, **kw):
        pages = list(pages)
        coded.extend(pages)
        return real(pages, *a, **kw)
    monkeypatch.setattr(stage_activity_code, "run_stage", spy)
    return coded


def test_released_pass1_reask_archives_the_activity_state_and_codes_it_afresh_113b(tmp_path, monkeypatch):
    """PI ruling 113 b: a pi_release.json key naming a 105 b pass-1 hold authorises one live re-ask; before
    that call the page's activity-level state (activity.json, pass1_requests.json, the T-023 artifact) is moved
    to ``<page dir>/archive/001/``, so T-023 codes the page again on the new response's spans instead of
    resuming from state built on the old ones. page.json stays at its live path (activity-level state only)."""
    from g3o.common.artifact_io import artifact_exists
    from g3o.run.presweep import stage_activity_code

    run_dir, world, run, hold, page = _held_105b(tmp_path)
    key, cid = hold["request_key"], hold["custom_id"]
    pdir = pp.page_state_dir(run_dir, page)
    inst_dir = institution_dir(run_dir, INST)
    art = stage_activity_code.artifact_path(inst_dir / pp.ACTIVITY_DIR, page.page_id)
    stale_activity = (pdir / "activity.json").read_bytes()
    assert (pdir / pp.PASS1_FILE).exists() and artifact_exists(art) and (pdir / "page.json").exists()

    _write_release(run_dir, _release_doc([key]))
    coded = _spy_coded(monkeypatch)
    ex3 = Renamed(world, page.page_id, "Renamed drafting")
    run(ex3)
    assert len([j for j in ex3.jobs if j.metadata["stage"] == PASS1 and j.custom_id == cid]) == 1  # the re-ask
    archive = pdir / pp.PAGE_ARCHIVE_DIR / "001"
    assert (archive / "activity.json").read_bytes() == stale_activity  # archived, never deleted
    assert (archive / pp.PASS1_FILE).exists() and len(list((archive / pp.ACTIVITY_DIR).iterdir())) == 1
    assert not (archive / "page.json").exists() and (pdir / "page.json").exists()
    assert not (pdir / pp.PAGE_ARCHIVE_PENDING).exists()  # the archive is complete
    # T-023 ran again for the page, on the re-asked response's spans; fresh state is written at the live paths
    (inp,) = [p for p in coded if p.page.page_id == page.page_id]
    assert [f.value for s in inp.spans for f in s.fields if f.item_id == "core.activity_name"] == ["Renamed drafting"]
    assert (pdir / "activity.json").exists() and artifact_exists(art) and (pdir / pp.PASS1_FILE).exists()
    assert not rt.RequestJournal(inst_dir / pp.WORK_DIR / pp.JOURNAL, {}).reask_authorised(key)
    assert not (pdir / pp.PAGE_ARCHIVE_DIR / "002").exists()


class CrashOn(FakeExtractor):
    """The process dies inside the extractor call for ``custom_id``."""

    def __init__(self, world, custom_id):
        super().__init__(world)
        self.custom_id = custom_id

    def __call__(self, job):
        if job.custom_id == self.custom_id:
            self.jobs.append(job)
            raise Crash("killed while sending the re-ask")
        return super().__call__(job)


def test_crash_during_the_released_reask_spends_it_and_the_next_run_holds_114b(tmp_path):
    """PI ruling 114 b at the stage: the process dies during the authorised re-ask (after the activity state
    was archived, 113 b, and the reask_spent marker journaled). The next run makes no live call of that
    request: it holds under 105 b again, and the archive is not repeated (no second folder)."""
    run_dir, world, run, hold, page = _held_105b(tmp_path)
    key, cid = hold["request_key"], hold["custom_id"]
    _write_release(run_dir, _release_doc([key]))
    crash = CrashOn(world, cid)
    with pytest.raises(Crash):
        run(crash)
    assert [j.custom_id for j in crash.jobs] == [cid]
    kinds = [(e["kind"], e["key"]) for e in _entries(run_dir)]
    assert (rt.REASK_SPENT, key) in kinds and ("extract", key) not in kinds
    pdir = pp.page_state_dir(run_dir, page)
    assert (pdir / pp.PAGE_ARCHIVE_DIR / "001" / "activity.json").exists()

    again = FakeExtractor(world)
    ready, metrics = run(again)
    assert ready == [] and metrics.held == [INST] and [j for j in again.jobs if j.custom_id == cid] == []
    (held,) = _held(run_dir, INST)["held"]
    assert (held["stage"], held["request_key"]) == (pp.PASS1_NOT_JOURNALED, key)
    assert not (pdir / pp.PAGE_ARCHIVE_DIR / "002").exists()


def test_released_activity_only_reask_archives_the_activity_state_first_113b(tmp_path):
    """PI ruling 113 b, the 87 c activity-only request: a release of its 105 b hold lets the one live re-ask
    through, after the page's activity-level state (activity.json, pairs.json, pass1_requests.json, the T-023
    artifact) is moved to ``archive/001/``; page.json and the residual source_type answers stay."""
    from g3o.classify.jev_page_code import to_pass1_page
    from g3o.common.artifact_io import artifact_exists, write_artifact
    from g3o.extract import request_v27
    from g3o.run.presweep import stage_activity_code

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, started, records, page_round_of = _flipped_round(run_dir, bound, page)
    page_cid = request_v27.make_custom_id(page.institution_id, page.url)
    only_cid = ppv.activity_only_custom_id(page_cid, to_pass1_page(started, page))
    path, pdir = tmp_path / "journal113b.jsonl", pp.page_state_dir(run_dir, page)
    art = stage_activity_code.artifact_path(institution_dir(run_dir, page.institution_id) / pp.ACTIVITY_DIR,
                                            page.page_id)

    def journaled(extract):
        journal = rt.RequestJournal(path, {"s": 1})
        base = _providers(run_dir, bound, instrument, extract, FakeEntail())
        providers = base.with_seams(*journal.seams(base.journal_prompt))
        return journal, providers, page_round_of(providers.page_support(page, result, records))

    pp._record_pass1_requests(pdir, SimpleNamespace(custom_id=page_cid), SimpleNamespace(custom_id=only_cid))
    ex1 = NoFirstRoundActivities(world)
    _, providers, page_round = journaled(ex1)
    with pytest.raises(pp.Pass1RequestNotJournaled) as exc:
        providers.activity_input(page, page_round)
    assert exc.value.stage == pp.ACTIVITY_ONLY_NOT_JOURNALED and not any(_is_activity_only(j) for j in ex1.jobs)
    key = exc.value.key
    # stale activity-level state built on the old spans, and the state that must stay
    stale = ("activity.json", pp.PAIRS_FILE)
    for name in (*stale, "page.json", pp.SOURCE_TYPE_FILE):
        (pdir / name).write_text(f"stale {name}", encoding="utf-8")
    art.parent.mkdir(parents=True, exist_ok=True)
    write_artifact(art, json.dumps({"stale": True}))

    rt.RequestJournal(path, {"s": 1}).record_release({**_release_doc([key]), "all": False, "file_sha256": "a" * 64,
                                                      "reask_keys": [key]})
    ex2 = NoFirstRoundActivities(world)
    journal, providers, page_round = journaled(ex2)
    assert providers.activity_input(page, page_round) is not None
    assert [j.custom_id for j in ex2.jobs if _is_activity_only(j)] == [only_cid]  # the one live re-ask
    archive = pdir / pp.PAGE_ARCHIVE_DIR / "001"
    for name in stale:
        assert not (pdir / name).exists() and (archive / name).exists()
    # review H-1: the old record is archived and a fresh one names the request sent (the other field kept)
    assert (archive / pp.PASS1_FILE).exists()
    assert pp.read_pass1_requests(run_dir, page) == {"format": pp.CHECKPOINT_FORMAT, "kind": "pass1_requests",
                                                     "page_request": page_cid, "activity_only": only_cid}
    assert (archive / "activity.json").read_text(encoding="utf-8") == "stale activity.json"
    assert not artifact_exists(art) and len(list((archive / pp.ACTIVITY_DIR).iterdir())) == 1
    for name in ("page.json", pp.SOURCE_TYPE_FILE):  # not activity-level state (113 b; review M-1)
        assert (pdir / name).read_text(encoding="utf-8") == f"stale {name}" and not (archive / name).exists()
    assert not (pdir / pp.PAGE_ARCHIVE_PENDING).exists() and not journal.reask_authorised(key)


def test_activity_state_archive_finishes_its_own_file_set_113b(tmp_path):
    """Unit: the 113 b archive moves only the activity-level files and the T-023 artifact; an incomplete one
    is finished with the file set its pending marker records (never page.json), into the same folder."""
    from g3o.classify.jev_page_code import PageInput
    from g3o.common.artifact_io import write_artifact
    from g3o.run.presweep import stage_activity_code

    run_dir = tmp_path / "run"
    page = PageInput(page_id="z1", institution_id="INST-0000009", institution="Z", country=None,
                     level_of_government=None, url="https://example.gov/z1", title=None, text="z")
    assert pp.archive_activity_state(run_dir, page) == []  # nothing saved: no folder taken
    pdir = pp.page_state_dir(run_dir, page)
    inst_dir = institution_dir(run_dir, page.institution_id)
    art = stage_activity_code.artifact_path(inst_dir / pp.ACTIVITY_DIR, page.page_id)
    pdir.mkdir(parents=True)
    for name in (*pp.PAGE_STATE_FILES, pp.SOURCE_TYPE_FILE):
        (pdir / name).write_text(name, encoding="utf-8")
    art.parent.mkdir(parents=True, exist_ok=True)
    write_artifact(art, json.dumps({"n": 1}))
    # an earlier 113 b archive left incomplete: its marker names folder 001 and the activity-level files
    (pdir / pp.PAGE_ARCHIVE_PENDING).write_text(json.dumps({
        "format": pp.CHECKPOINT_FORMAT, "kind": "archive_pending", "archive": "001",
        "files": list(pp.ACTIVITY_STATE_FILES)}), encoding="utf-8")
    moved = pp._archive_page_state(run_dir, page)  # the default file set is overridden by the marker's
    dest = pdir / pp.PAGE_ARCHIVE_DIR / "001"
    assert len(moved) == len(pp.ACTIVITY_STATE_FILES) + 1
    assert all((dest / name).exists() for name in pp.ACTIVITY_STATE_FILES)
    assert (pdir / "page.json").exists() and (pdir / pp.SOURCE_TYPE_FILE).exists()
    assert not (dest / "page.json").exists() and (dest / pp.PAGE_ARCHIVE_PENDING).exists()
    assert pp.archive_activity_state(run_dir, page) == [] and not (pdir / pp.PAGE_ARCHIVE_DIR / "002").exists()


# ---------------------------------------------------------------------------
# Review H-1 (PI ruling 114 b): a spent re-ask with no answer never goes live again without a new release
# ---------------------------------------------------------------------------


class FailOn(FakeExtractor):
    """The extractor call for ``custom_id`` ends with ``outcome``: the process dies while sending (``crash``),
    the call times out (``timeout``), a failed result (``extract_failed``) or an unparsable one (``rejected``)."""

    def __init__(self, world, custom_id, outcome):
        super().__init__(world)
        self.custom_id, self.outcome = custom_id, outcome

    def __call__(self, job):
        if job.custom_id != self.custom_id:
            return super().__call__(job)
        self.jobs.append(job)
        if self.outcome == "crash":
            raise Crash("killed while sending the re-ask")
        if self.outcome == "timeout":
            raise TimeoutError("read timed out")
        if self.outcome == "extract_failed":
            return ExtractorResult(job.custom_id, False, None, {"type": "errored"}, usage=dict(USAGE))
        return ExtractorResult(job.custom_id, True, "not json {", None, "fake-extractor-response", "msg-bad",
                               "x-bad", "end_turn", dict(USAGE))


OUTCOMES = ["crash", "timeout", "extract_failed", "rejected"]


def _failed_reask(providers, journal, call, outcome):
    """``call()`` (the released re-ask) ends with ``outcome``; a rejected response is rejected in the journal,
    as the per-page stage does with every ``ExtractorResponseFailed`` (C3 a)."""
    with pytest.raises((Crash, TimeoutError, pp.ExtractorResponseFailed)) as exc:
        call()
    if outcome == "rejected":
        assert journal.reject_extract(exc.value.request, providers.journal_prompt, exc.value.detail)
    elif outcome == "extract_failed":
        assert isinstance(exc.value, pp.ExtractorResponseFailed)


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_spent_reask_with_no_answer_is_refused_by_the_journal_h1(tmp_path, outcome):
    """Review H-1, the journal (fix a): after the ``reask_spent`` marker, a crash while sending, a timeout, an
    ``extract_failed`` result or a rejected response leaves no answer to replay; the journal then refuses a live
    call of that key (``ReaskSpentUnanswered``, no extractor call), in this process and on every later load, and
    ``peek`` / ``reask_live`` agree (not recorded, not a live re-ask). A NEW release authorises exactly one more."""
    job = ExtractorJob("cid-h1", {"model": "m", "messages": [{"p": 7}]}, {})
    request = {"custom_id": job.custom_id, "params": job.params}
    path = tmp_path / "journal.jsonl"
    ok = ExtractorResult("cid-h1", True, "{}", None, "fake-extractor-response", "msg-1", "x-1", "end_turn",
                         dict(USAGE))
    failed = ExtractorResult("cid-h1", False, None, {"type": "errored"}, usage=dict(USAGE))
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(PROMPT)
    calls = []

    def call(j):
        calls.append(j.custom_id)
        if outcome == "crash":
            raise Crash("killed")
        if outcome == "timeout":
            raise TimeoutError("read timed out")
        return failed if outcome == "extract_failed" else ok
    fn = wrap(call)
    key = fn.peek(job)[0]
    journal.record_release({**_release_doc([key]), "all": False, "file_sha256": "e" * 64, "reask_keys": [key]})
    if outcome in ("crash", "timeout"):
        with pytest.raises((Crash, TimeoutError)):
            fn(job)
    else:
        fn(job)
    if outcome == "rejected":
        assert journal.reject_extract(request, PROMPT, "ExtractContractError: bad")
    assert calls == ["cid-h1"]
    for j in (journal, rt.RequestJournal(path, {"s": 1})):  # this process, and a later load
        w, _ = j.seams(PROMPT)
        again = w(lambda _: pytest.fail("no unauthorised live re-ask"))
        assert j.reask_spent_unanswered(key) and again.peek(job) == (key, False) and not again.reask_live(job)
        with pytest.raises(rt.ReaskSpentUnanswered) as exc:
            again(job)
        assert (exc.value.key, exc.value.custom_id) == (key, "cid-h1")
    # a NEW release (other bytes) authorises exactly one more live re-ask
    later = rt.RequestJournal(path, {"s": 1})
    later.record_release({**_release_doc([key], date="2026-11-15"), "all": False, "file_sha256": "f" * 64,
                          "reask_keys": [key]})
    w, _ = later.seams(PROMPT)
    more = []
    once = w(lambda j: more.append(j.custom_id) or failed)
    assert once.peek(job) == (key, True) and once.reask_live(job)
    once(job)
    with pytest.raises(rt.ReaskSpentUnanswered):
        once(job)
    assert more == ["cid-h1"]


def test_spent_reask_that_was_answered_replays_and_is_never_refused_h1(tmp_path):
    """The refusal needs a missing answer: a spent re-ask whose response is recorded is replayed (no call)."""
    job = ExtractorJob("cid-h1", {"model": "m", "messages": [{"p": 8}]}, {})
    path = tmp_path / "journal.jsonl"
    ok = ExtractorResult("cid-h1", True, "{}", None, "fake-extractor-response", "msg-1", "x-1", "end_turn",
                         dict(USAGE))
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(PROMPT)
    fn = wrap(lambda j: ok)
    key = fn.peek(job)[0]
    journal.record_release({**_release_doc([key]), "all": False, "file_sha256": "e" * 64, "reask_keys": [key]})
    fn(job)
    reloaded = rt.RequestJournal(path, {"s": 1})
    w, _ = reloaded.seams(PROMPT)
    replay = w(lambda _: pytest.fail("replayed, never called"))
    assert not reloaded.reask_spent_unanswered(key) and replay.peek(job) == (key, True)
    assert replay(job).success and reloaded.replayed == 1


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_activity_only_reask_that_fails_holds_the_next_run_with_no_live_call_h1(tmp_path, outcome):
    """Review H-1 at the provider adapter, the 87 c activity-only request (pass1_requests.json is its only 105 b
    trigger, and the 113 b re-ask archives it). The released re-ask dies while sending, times out, fails or is
    rejected; the next run holds (activity_only_request_not_journaled, its request_key) with no second live call:
    first by the fresh record (fix b), and, with that record gone (as before the fix), by the journal itself (fix
    a). A NEW release authorises exactly one more re-ask."""
    from g3o.classify.jev_page_code import to_pass1_page
    from g3o.extract import request_v27

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    result, started, records, page_round_of = _flipped_round(run_dir, bound, page)
    page_cid = request_v27.make_custom_id(page.institution_id, page.url)
    only_cid = ppv.activity_only_custom_id(page_cid, to_pass1_page(started, page))
    path, pdir = tmp_path / "journalh1.jsonl", pp.page_state_dir(run_dir, page)

    def journaled(extract):
        journal = rt.RequestJournal(path, {"s": 1})
        base = _providers(run_dir, bound, instrument, extract, FakeEntail())
        providers = base.with_seams(*journal.seams(base.journal_prompt))
        return journal, providers, page_round_of(providers.page_support(page, result, records))

    pp._record_pass1_requests(pdir, SimpleNamespace(custom_id=page_cid), SimpleNamespace(custom_id=only_cid))
    _, providers, page_round = journaled(NoFirstRoundActivities(world))
    with pytest.raises(pp.Pass1RequestNotJournaled) as exc:
        providers.activity_input(page, page_round)
    key = exc.value.key
    rt.RequestJournal(path, {"s": 1}).record_release({**_release_doc([key]), "all": False, "file_sha256": "a" * 64,
                                                      "reask_keys": [key]})
    bad = FailOn(world, only_cid, outcome)
    journal, providers, page_round = journaled(bad)
    _failed_reask(providers, journal, lambda: providers.activity_input(page, page_round), outcome)
    assert [j.custom_id for j in bad.jobs] == [only_cid]  # the one live re-ask (the page request replayed)
    assert (pdir / pp.PAGE_ARCHIVE_DIR / "001" / pp.PASS1_FILE).exists()  # 113 b: the old record archived
    assert pp.read_pass1_requests(run_dir, page)["activity_only"] == only_cid  # fix b: a fresh one names it

    def held_again():
        again = NoFirstRoundActivities(world)
        _, providers, page_round = journaled(again)
        with pytest.raises(pp.Pass1RequestNotJournaled) as held:
            providers.activity_input(page, page_round)
        assert (held.value.stage, held.value.key, held.value.custom_id) == (pp.ACTIVITY_ONLY_NOT_JOURNALED, key,
                                                                            only_cid)
        assert again.jobs == []  # no second live call
        return held.value

    assert not held_again().spent  # the provider-level 105 b check, on the fresh record (fix b)
    assert not (pdir / pp.PAGE_ARCHIVE_DIR / "002").exists()
    aside = tmp_path / "pass1_requests.aside"
    (pdir / pp.PASS1_FILE).replace(aside)  # no record, as before review H-1: the journal refuses it (fix a)
    refused = held_again()
    assert refused.spent and "H-1" in str(refused) and "114 b" in str(refused)
    aside.replace(pdir / pp.PASS1_FILE)
    # a NEW release (other bytes) authorises exactly one more re-ask; its answer then replays
    rt.RequestJournal(path, {"s": 1}).record_release({**_release_doc([key], date="2026-11-15"), "all": False,
                                                      "file_sha256": "b" * 64, "reask_keys": [key]})
    ex = NoFirstRoundActivities(world)
    _, providers, page_round = journaled(ex)
    assert providers.activity_input(page, page_round) is not None
    assert [j.custom_id for j in ex.jobs] == [only_cid]
    replayed = NoFirstRoundActivities(world)
    _, providers, page_round = journaled(replayed)
    assert providers.activity_input(page, page_round) is not None and replayed.jobs == []


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_no_codes_page_reask_that_fails_holds_the_next_run_with_no_live_call_h1(tmp_path, monkeypatch, outcome):
    """Review H-1, a first pass-1 request whose rebuilt page has no pass-1 codes (pass1_requests.json is its only
    105 b trigger, archived by the 113 b re-ask). Variant of
    ``test_crash_during_the_released_reask_spends_it_and_the_next_run_holds_114b``, whose page has codes: the
    released re-ask dies while sending, times out, fails or is rejected; the next run holds
    (pass1_request_not_journaled, its request_key) with no second live call, by the fresh record (fix b) and,
    with that record gone, by the journal (fix a). A NEW release authorises exactly one more re-ask."""
    from g3o.extract import request_v27

    run_dir, bound, instrument, world, page = _flip_world(tmp_path)
    # ambiguous_genai: the first-round plan has the activity task, so a page with no codes still needs a request
    result, _, records, page_round_of = _flipped_round(run_dir, bound, page, flipped=False,
                                                       first_verdict="ambiguous_genai")
    page_round = page_round_of(_providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail())
                               .page_support(page, result, records))
    real = ppv.to_pass1_page
    monkeypatch.setattr(ppv, "to_pass1_page", lambda *a, **kw: replace(real(*a, **kw), codes=()))
    page_cid = request_v27.make_custom_id(page.institution_id, page.url)
    path, pdir = tmp_path / "journalh1nc.jsonl", pp.page_state_dir(run_dir, page)

    def journaled(extract):
        journal = rt.RequestJournal(path, {"s": 1})
        base = _providers(run_dir, bound, instrument, extract, FakeEntail())
        return journal, base.with_seams(*journal.seams(base.journal_prompt))

    pp._record_pass1_requests(pdir, SimpleNamespace(custom_id=page_cid), None)  # an earlier process made it
    first = FakeExtractor(world)
    _, providers = journaled(first)
    with pytest.raises(pp.Pass1RequestNotJournaled) as exc:
        providers.activity_input(page, page_round)
    assert exc.value.stage == pp.PASS1_NOT_JOURNALED and first.jobs == []
    key = exc.value.key
    rt.RequestJournal(path, {"s": 1}).record_release({**_release_doc([key]), "all": False, "file_sha256": "a" * 64,
                                                      "reask_keys": [key]})
    bad = FailOn(world, page_cid, outcome)
    journal, providers = journaled(bad)
    _failed_reask(providers, journal, lambda: providers.activity_input(page, page_round), outcome)
    assert [j.custom_id for j in bad.jobs] == [page_cid]
    assert (pdir / pp.PAGE_ARCHIVE_DIR / "001" / pp.PASS1_FILE).exists()
    assert pp.read_pass1_requests(run_dir, page)["page_request"] == page_cid  # fix b

    def held_again():
        again = FakeExtractor(world)
        _, providers = journaled(again)
        with pytest.raises(pp.Pass1RequestNotJournaled) as held:
            providers.activity_input(page, page_round)
        assert (held.value.stage, held.value.key, held.value.custom_id) == (pp.PASS1_NOT_JOURNALED, key, page_cid)
        assert again.jobs == []  # no second live call
        return held.value

    assert not held_again().spent
    assert not (pdir / pp.PAGE_ARCHIVE_DIR / "002").exists()
    aside = tmp_path / "pass1_requests.aside"
    (pdir / pp.PASS1_FILE).replace(aside)  # no record and no codes: before review H-1 this was sent live
    assert held_again().spent
    aside.replace(pdir / pp.PASS1_FILE)
    rt.RequestJournal(path, {"s": 1}).record_release({**_release_doc([key], date="2026-11-15"), "all": False,
                                                      "file_sha256": "b" * 64, "reask_keys": [key]})
    ex = FakeExtractor(world)
    _, providers = journaled(ex)
    assert providers.activity_input(page, page_round) is not None
    assert [j.custom_id for j in ex.jobs] == [page_cid]
    replayed = FakeExtractor(world)
    _, providers = journaled(replayed)
    assert providers.activity_input(page, page_round) is not None and replayed.jobs == []


def test_journal_refusal_maps_to_the_hold_of_the_request_kind_h1(tmp_path):
    """Review H-1: the adapter turns the journal's refusal into the not-journaled hold of the request's kind
    (pass 2 here; pass 1 and activity-only above), carrying the request key, so held.json lists a releasable
    stage (REASK_RELEASABLE) that a new release file can name."""
    run_dir, bound, instrument, world, _ = _world(tmp_path)
    adapter = _providers(run_dir, bound, instrument, FakeExtractor(world), FakeEntail()).adapter
    job = ExtractorJob("cid-h1", {"model": "m"}, {})

    def refused(j):
        raise rt.ReaskSpentUnanswered("k" * 64, j.custom_id)
    adapter.extract_fn = refused
    with pytest.raises(pp.Pass2RequestNotJournaled) as exc:
        adapter._parsed("pass2", job, lambda r: r, page_id="b1", hold_stage=pp.PASS2_NOT_JOURNALED)
    assert (exc.value.page_id, exc.value.custom_id, exc.value.key, exc.value.spent) == ("b1", "cid-h1", "k" * 64,
                                                                                         True)
    for stage in (pp.PASS1_NOT_JOURNALED, pp.ACTIVITY_ONLY_NOT_JOURNALED):
        with pytest.raises(pp.Pass1RequestNotJournaled) as exc1:
            adapter._parsed("pass1", job, lambda r: r, page_id="p1", hold_stage=stage)
        assert (exc1.value.stage, exc1.value.key, exc1.value.spent) == (stage, "k" * 64, True)
        assert exc1.value.stage in pp.REASK_RELEASABLE


def test_record_pass1_reask_names_the_request_and_keeps_the_other_field_h1(tmp_path):
    """Review H-1 (fix b): the fresh record names the request in the field of its kind and keeps the archived
    record's other field; another hold stage is a wiring error."""
    from g3o.classify.jev_page_code import PageInput

    run_dir = tmp_path / "run"
    page = PageInput(page_id="z1", institution_id="INST-0000009", institution="Z", country=None,
                     level_of_government=None, url="https://example.gov/z1", title=None, text="z")
    pp.record_pass1_reask(run_dir, page, None, pp.PASS1_NOT_JOURNALED, "c-page")
    assert pp.read_pass1_requests(run_dir, page) == {"format": pp.CHECKPOINT_FORMAT, "kind": "pass1_requests",
                                                     "page_request": "c-page", "activity_only": None}
    previous = pp.read_pass1_requests(run_dir, page)
    pp.record_pass1_reask(run_dir, page, previous, pp.ACTIVITY_ONLY_NOT_JOURNALED, "c-only")
    assert pp.read_pass1_requests(run_dir, page)["page_request"] == "c-page"
    assert pp.read_pass1_requests(run_dir, page)["activity_only"] == "c-only"
    # the stage's own record of the same requests is byte-equal: nothing is rewritten
    assert not pp._record_pass1_requests(pp.page_state_dir(run_dir, page), SimpleNamespace(custom_id="c-page"),
                                         SimpleNamespace(custom_id="c-only"))
    with pytest.raises(TypeError):
        pp.record_pass1_reask(run_dir, page, previous, pp.PASS2_NOT_JOURNALED, "c-2")


# ---------------------------------------------------------------------------
# PI ruling 122 b: a release dropped straight after a failed re-ask is accepted (review M-1 of h1fix)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_release_straight_after_a_failed_reask_authorises_one_more_122b(tmp_path, outcome):
    """PI ruling 122 b at the stage. The released pass-1 re-ask dies while sending, times out, comes back
    ``extract_failed`` or is rejected. A crash or timeout leaves the earlier 105 b hold in held.json; a failed or
    rejected response leaves an ``extract_response_failed`` hold (before 122 b: a new release naming the key was
    refused as malformed and stayed in place for ever, or, after a rejection, consumed with ``reask_keys`` []).
    A NEW release naming the key, dropped straight away, is accepted as a re-ask (the journal reports the key as
    a spent re-ask with no answer): the next run makes exactly one live call of the request, and a further run
    with no new file makes none (the answer is replayed)."""
    run_dir, world, run, hold, _ = _held_105b(tmp_path)
    key, cid = hold["request_key"], hold["custom_id"]
    _write_release(run_dir, _release_doc([key]))
    bad = FailOn(world, cid, outcome)
    if outcome in ("crash", "timeout"):
        with pytest.raises((Crash, TimeoutError)):
            run(bad)
        (held,) = _held(run_dir, INST)["held"]  # the run died: held.json is the earlier 105 b hold
        assert (held["stage"], held["request_key"]) == (pp.PASS1_NOT_JOURNALED, key)
    else:
        ready, metrics = run(bad)
        assert ready == [] and metrics.held == [INST]
        (held,) = _held(run_dir, INST)["held"]
        assert held["stage"] == pp.EXTRACT_RESPONSE_FAILED and held["stage"] not in pp.REASK_RELEASABLE
    assert [j.custom_id for j in bad.jobs] == [cid]  # the one live re-ask, failed
    journal_path = institution_dir(run_dir, INST) / pp.WORK_DIR / pp.JOURNAL
    assert rt.RequestJournal(journal_path, {}).reask_spent_unanswered(key)

    release = _write_release(run_dir, _release_doc([key], date="2026-11-15"))  # a new PI decision
    ex = FakeExtractor(world)
    run(ex)
    assert not release.exists()  # consumed (archived), never left in place as malformed
    assert [e["response"]["reask_keys"] for e in _entries(run_dir) if e["kind"] == rt.PI_RELEASED] == [[key], [key]]
    assert len([j for j in ex.jobs if j.metadata["stage"] == PASS1 and j.custom_id == cid]) == 1
    assert all(h.get("stage") != pp.PI_RELEASE_MALFORMED
               for h in (_held(run_dir, INST)["held"] if (journal_path.parent / pp.HELD_FILE).exists() else []))

    further = FakeExtractor(world)  # no new file: the re-asked answer is replayed, no live call
    run(further)
    assert [j for j in further.jobs if j.metadata["stage"] == PASS1 and j.custom_id == cid] == []
    assert not rt.RequestJournal(journal_path, {}).reask_spent_unanswered(key)


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_spent_unanswered_key_is_reaskable_with_no_releasable_hold_122b(tmp_path, outcome):
    """PI ruling 122 b, ``_apply_pi_release`` alone: a key the journal reports as a spent re-ask with no answer is
    accepted into ``reask_keys`` even when held.json names no releasable hold (here an ``extract_response_failed``
    hold with no request key); a key never released and spent is still refused; the same bytes again are only
    archived (ruling 47.2 a) and authorise nothing."""
    job = ExtractorJob("cid-122b", {"model": "m", "messages": [{"p": 9}]}, {})
    request = {"custom_id": job.custom_id, "params": job.params}
    inst_dir = tmp_path / "inst"
    (inst_dir / pp.WORK_DIR).mkdir(parents=True)
    path = inst_dir / pp.WORK_DIR / pp.JOURNAL
    ok = ExtractorResult("cid-122b", True, "{}", None, "fake-extractor-response", "msg-1", "x-1", "end_turn",
                         dict(USAGE))
    journal = rt.RequestJournal(path, {"s": 1})
    wrap, _ = journal.seams(PROMPT)

    def call(j):
        if outcome == "crash":
            raise Crash("killed")
        if outcome == "timeout":
            raise TimeoutError("read timed out")
        return ExtractorResult(j.custom_id, False, None, {"type": "errored"}, usage=dict(USAGE)) \
            if outcome == "extract_failed" else ok
    fn = wrap(call)
    key = fn.peek(job)[0]
    journal.record_release({**_release_doc([key]), "all": False, "file_sha256": "e" * 64, "reask_keys": [key]})
    if outcome in ("crash", "timeout"):
        with pytest.raises((Crash, TimeoutError)):
            fn(job)
    else:
        fn(job)
    if outcome == "rejected":
        assert journal.reject_extract(request, PROMPT, "ExtractContractError: bad")
    (inst_dir / pp.WORK_DIR / pp.HELD_FILE).write_text(json.dumps({"institution_id": INST, "held": [
        {"page_id": "p1", "stage": pp.EXTRACT_RESPONSE_FAILED, "pass": "pass1", "custom_id": job.custom_id,
         "error": "x"}]}), encoding="utf-8")
    reloaded = rt.RequestJournal(path, {"s": 1})
    raw = json.dumps(_release_doc([key], date="2026-11-15")).encode("utf-8")
    (inst_dir / pp.PI_RELEASE_FILE).write_bytes(raw)
    assert pp._apply_pi_release(inst_dir, reloaded) is None and reloaded.reask_authorised(key)
    assert not (inst_dir / pp.PI_RELEASE_FILE).exists()
    (entry,) = [e for e in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines())
                if e["kind"] == rt.PI_RELEASED and e["key"] == hashlib.sha256(raw).hexdigest()]
    assert entry["response"]["reask_keys"] == [key]
    w, _ = reloaded.seams(PROMPT)
    calls = []
    once = w(lambda j: calls.append(j.custom_id) or ok)
    once(job)  # exactly one live call
    assert calls == ["cid-122b"]
    # the same bytes again: only archived, nothing authorised; the answer replays, no call
    (inst_dir / pp.PI_RELEASE_FILE).write_bytes(raw)
    later = rt.RequestJournal(path, {"s": 1})
    assert pp._apply_pi_release(inst_dir, later) is None and not later.reask_authorised(key)
    w2, _ = later.seams(PROMPT)
    assert w2(lambda _: pytest.fail("replayed, never called"))(job).success
    # a key never released and spent is still refused
    other = "c" * 64
    (inst_dir / pp.PI_RELEASE_FILE).write_bytes(json.dumps(_release_doc([other], date="2026-11-16")).encode("utf-8"))
    hold = pp._apply_pi_release(inst_dir, rt.RequestJournal(path, {"s": 1}))
    assert hold["stage"] == pp.PI_RELEASE_MALFORMED and other in hold["error"]
