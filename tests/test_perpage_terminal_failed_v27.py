"""An institution whose every page failed after an extra-round halving is a terminal failure (C189).

PI ruling 69 b: a page whose failed verdict parts reach 75% of the layout halved in an extra round fails
and is never asked again, on any resume. The C189 ``no_page_coded`` hold (pending, "a later run retries
it") would therefore never clear for an institution whose every page failed that way. Such an institution
is instead a terminal failure: no hold, no Stage 6 input, one attrition row
(:data:`g3o.run.presweep.stage_perpage_v27.NO_PAGE_CODED_FAILED`) that the run report counts as a
failure, so it is PROCESSING_FAILED and never NO_EVIDENCE_FOUND (rulings 45 a, E2 a). An institution
with any page still retryable (a T-021 failure, which the next pass codes again) keeps the
``no_page_coded`` hold. Synthetic pages and fake answers only (no network).
"""
from __future__ import annotations

import json
from dataclasses import replace

from g3o.classify import question_rounds as qr
from g3o.common import attrition
from g3o.common.instrument import load_instrument
from g3o.common.paths import institution_dir
from g3o.common.run_state import done_path
from g3o.report.outcomes import compute_institution_report
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.run.presweep.instrument_binding import bind_runtime
from tests._layout import write_manifest
from tests.test_e2e_perpage_v27 import (
    ANSWERS,
    CLOCK,
    RELATIONS,
    RUN_ID,
    SETTINGS,
    FakeJev,
    FakeQuotes,
    Page,
    World,
    _pages,
    _paragraph_layout,  # noqa: F401 - autouse fixture: the per-paragraph layout of that module
    _perpage,
)

INST = "INST-0000004"
DETAIL = "1/1 verdict parts failed (at least 75%) on the layout halved in an extra round, after the page was coded"


def _setup(tmp_path, pages):
    run_dir = tmp_path / "run"
    bound = bind_runtime(run_dir, SETTINGS)
    instrument = load_instrument(run_dir / "final" / "instruments", bound.instrument_id)
    world = World(run_dir, bound, instrument, [*_pages(), *pages])
    return run_dir, bound, instrument, world, [world.institution(INST)]


def _halving_fails(monkeypatch, page_ids):
    """The named pages fail after an extra-round halving (ruling 69 b); the halving itself is covered
    in test_question_rounds, as in test_e2e_perpage_v27."""
    real = pp.complete_page_rounds

    def failing(page, result, support, **kw):
        if page.page_id not in page_ids or result.status == "failed":
            return real(page, result, support, **kw)
        failed = replace(result, status="failed", failures=result.failures + (
            {"chunk_id": None, "round": 3, "group": "extra", "question_ids": [],
             "reason": qr.HALVING_PAGE_FAILED, "detail": DETAIL},))
        kw["checkpoint"](failed, tuple(support))
        return real(page, failed, support, **kw)

    monkeypatch.setattr(pp, "complete_page_rounds", failing)
    return real


def _stage6(run_dir, bound, instrument, ready):
    return rt.run_stage6_v27(run_dir, ready, ask_fn=FakeJev(ANSWERS, RELATIONS), quote_fn=FakeQuotes(),
                             config=bound.stage6_config(), instrument=instrument, now=CLOCK,
                             test_only_unbound_quote_fn=True)


def _report(run_dir):
    write_manifest(run_dir, {"run_id": RUN_ID, "institutions": [INST],
                             "config": {"stop_after": "validate", "pipeline_version": "v2.7"},
                             "storage_contract": {"codebook_release": "2.7"}})
    d = institution_dir(run_dir, INST)
    (d / "3_triage.json").write_text(json.dumps({"decisions": [{"decision": "keep", "url": "u"}]}),
                                     encoding="utf-8")
    (d / "scrape").mkdir(parents=True, exist_ok=True)
    (d / "scrape" / "page.json").write_text(json.dumps({"url": "u"}), encoding="utf-8")
    for stage in ("classify_triage", "scrape"):
        done_path(run_dir, stage).parent.mkdir(parents=True, exist_ok=True)
        done_path(run_dir, stage).write_text(json.dumps({"stage": stage, "no_batch": True}), encoding="utf-8")
    (rec,) = compute_institution_report(run_dir)
    return rec


def _ledger(run_dir):
    return [(r["stage"], r["reason"], r.get("detail")) for r in attrition.read_records(run_dir)
            if r["institution_id"] == INST and r["stage"] == pp.STAGE and r.get("url") is None]


def test_every_page_failed_after_halving_is_terminal_processing_failed(tmp_path, monkeypatch):
    run_dir, bound, instrument, world, insts = _setup(tmp_path, [Page(INST, "d1", ["Council text."])])
    real = _halving_fails(monkeypatch, {"d1"})
    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, FakeJev(ANSWERS, RELATIONS))
    assert metrics.failed_pages == ["d1"]
    assert not ready and not metrics.ready and not metrics.held
    assert metrics.failed == [INST]
    held_path = institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE
    assert not held_path.exists()  # not a hold that never clears
    assert _ledger(run_dir) == [(pp.STAGE, pp.NO_PAGE_CODED_FAILED, f"d1:{qr.HALVING_PAGE_FAILED}")]

    s6m = _stage6(run_dir, bound, instrument, ready)  # Stage 6 never sees it (and writes its marker)
    assert not s6m.written and not s6m.held
    rec = _report(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"  # rulings 45 a, E2 a: never NO_EVIDENCE_FOUND
    assert pp.NO_PAGE_CODED_FAILED in rec["reason"] and "retries" not in rec["reason"]

    # Resume: nothing is asked for d1 again, the state stays terminal, no second ledger row.
    monkeypatch.setattr(pp, "complete_page_rounds", real)
    jev = FakeJev(ANSWERS, RELATIONS)
    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, jev)
    assert not ready and not metrics.held and metrics.failed == [INST]
    assert not [s for s, _ in jev.calls if s.get("page_url", "").endswith("/d1")]
    assert not held_path.exists()
    assert _ledger(run_dir) == [(pp.STAGE, pp.NO_PAGE_CODED_FAILED, f"d1:{qr.HALVING_PAGE_FAILED}")]


def test_no_page_coded_hold_becomes_terminal_when_the_retried_page_fails_after_halving(tmp_path, monkeypatch):
    run_dir, bound, instrument, world, insts = _setup(tmp_path, [Page(INST, "d1", ["Council text."])])
    down = {"on": True}

    def fail(state, questions, n):
        return RuntimeError("simulated part failure") if down["on"] else None

    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, FakeJev(ANSWERS, RELATIONS, fail))
    held_path = institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE
    assert metrics.held == [INST] and held_path.exists()  # first failure: retry pending, held

    down["on"] = False
    _halving_fails(monkeypatch, {"d1"})
    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, FakeJev(ANSWERS, RELATIONS))
    assert not ready and not metrics.held and metrics.failed == [INST]
    assert not held_path.exists()
    reasons = [reason for _, reason, _ in _ledger(run_dir)]
    assert reasons == [pp.HELD_REASON, pp.HELD_RELEASED, pp.NO_PAGE_CODED_FAILED]
    _stage6(run_dir, bound, instrument, ready)
    rec = _report(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED" and pp.NO_PAGE_CODED_FAILED in rec["reason"]


def test_a_retryable_page_keeps_the_no_page_coded_hold(tmp_path, monkeypatch):
    """One page failed after halving (terminal), one failed T-021 coding (the next pass codes it again):
    the institution is still pending, so it keeps the C189 hold."""
    run_dir, bound, instrument, world, insts = _setup(
        tmp_path, [Page(INST, "d1", ["Council text."]), Page(INST, "d2", ["FAIL only."])])
    _halving_fails(monkeypatch, {"d1"})

    def fail(state, questions, n):
        return RuntimeError("simulated part failure") if state["page_text"].startswith("FAIL") else None

    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, FakeJev(ANSWERS, RELATIONS, fail))
    assert metrics.held == [INST] and not metrics.failed and not ready
    held = json.loads((institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE).read_text(encoding="utf-8"))
    (hold,) = held["held"]
    assert hold["stage"] == pp.NO_PAGE_CODED
    assert pp.NO_PAGE_CODED_FAILED not in [reason for _, reason, _ in _ledger(run_dir)]
