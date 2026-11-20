"""An institution whose every attempted page failed T-021 coding reaches no source row.

Before this fix the per-page stage counted such an institution as ready, and v2.7 Stage 6
then held it with a pydantic error from ``ConsolidatedInstitutionResponseV27`` ("sources:
List should have at least 1 item", reason ``stage6_envelope_failed``): a hold by accident,
with a reason that names the envelope instead of the failed pages. The per-page stage now
holds it itself as pending (:data:`g3o.run.presweep.stage_perpage_v27.NO_PAGE_CODED`),
naming each failed page and its reason; the next pass codes the pages again and releases it.
Synthetic pages and fake answers only (no network).
"""
from __future__ import annotations

import json

from g3o.classify import jev_page_code as jpc
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
    _fail_verdict,
    _pages,
    _paragraph_layout,  # noqa: F401 - autouse fixture: the per-paragraph layout of that module
    _perpage,
)

INST = "INST-0000004"


def _setup(tmp_path):
    run_dir = tmp_path / "run"
    bound = bind_runtime(run_dir, SETTINGS)
    instrument = load_instrument(run_dir / "final" / "instruments", bound.instrument_id)
    # one page whose only verdict part fails (1/1, at least 75%): T-021 writes no artifact
    world = World(run_dir, bound, instrument, [*_pages(), Page(INST, "d1", ["FAIL only."])])
    return run_dir, bound, instrument, world, [world.institution(INST)]


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


def test_every_page_failed_is_a_typed_perpage_hold_not_an_envelope_error(tmp_path):
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    assert metrics.failed_pages == ["d1"]
    assert metrics.held == [INST] and not metrics.ready and not ready

    held = json.loads((institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE).read_text(encoding="utf-8"))
    (hold,) = held["held"]
    assert hold["stage"] == pp.NO_PAGE_CODED and hold["page_id"] == INST
    assert hold["failed_pages"] == [{"page_id": "d1", "reason": jpc.REQUEST_FAILED}]

    ledger = [(r["stage"], r["reason"], r.get("detail")) for r in attrition.read_records(run_dir)
              if r["institution_id"] == INST]
    assert (pp.STAGE, pp.HELD_REASON, f"{INST}:{pp.NO_PAGE_CODED}") in ledger

    # Stage 6 never sees it, so no envelope validation error is raised for it.
    s6m = rt.run_stage6_v27(run_dir, ready, ask_fn=FakeJev(ANSWERS, RELATIONS), quote_fn=FakeQuotes(),
                            config=bound.stage6_config(), instrument=instrument, now=CLOCK,
                            test_only_unbound_quote_fn=True)
    assert not s6m.written and not s6m.held
    assert not any(r["reason"] == rt.ENVELOPE_FAILED for r in attrition.read_records(run_dir))

    # The run report: not concluded (never NO_EVIDENCE_FOUND), the hold named.
    rec = _report(run_dir)
    assert rec["final_status"] == "PROCESSING_FAILED"
    assert pp.NO_PAGE_CODED in rec["reason"]


def test_all_pages_failed_hold_is_released_when_a_later_pass_codes_the_page(tmp_path):
    run_dir, bound, instrument, world, insts = _setup(tmp_path)
    _perpage(run_dir, bound, instrument, world, insts, FakeJev(ANSWERS, RELATIONS, _fail_verdict))
    held_path = institution_dir(run_dir, INST) / pp.WORK_DIR / pp.HELD_FILE
    assert held_path.exists()

    ready, metrics = _perpage(run_dir, bound, instrument, world, insts, FakeJev(ANSWERS, RELATIONS))
    assert [i.institution_id for i in ready] == [INST] and not metrics.held and not metrics.failed_pages
    assert not held_path.exists()
    reasons = [r["reason"] for r in attrition.read_records(run_dir) if r["institution_id"] == INST
               and r["stage"] == pp.STAGE]
    assert reasons == [pp.HELD_REASON, pp.HELD_RELEASED]
