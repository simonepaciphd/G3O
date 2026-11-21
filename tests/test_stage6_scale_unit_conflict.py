"""Def5b: several distinct units for the one-value ``core.deployment_scale_unit`` hold under their own reason.

Calibration defect 5 (rest), PI ruling 2026-11-20 ("all accepted"): when the parts of a long page give several
distinct units for one activity, the signed long-page rule (``combined_list``, ruling activity-24 b) yields a list,
while the item is ``single`` (D-007: one enum code). No single-value form is ruled, so the institution stays held;
but it is held under its own countable reason (``scale_unit_conflict``, attrition ``stage6_held:scale_unit_conflict``)
instead of the generic storage refusal (``stage6_envelope_failed``), so the case shows in hold and attrition
counts and can be revisited on first occurrence. No codebook value changes. Offline fakes only.
"""
from __future__ import annotations

from dataclasses import replace

from g3o.common.paths import institution_dir
from g3o.run.presweep import stage_validate_v27 as rt
from tests import test_e2e_stage6_v27 as e
from tests.test_stage6_runtime_qa import A, B, _held, _ledger, _run

UNIT = "core.deployment_scale_unit"


def _with_unit(inst, oid, unit):
    obs = inst.observation_inputs[oid]
    row = {**obs.row, "values": {**obs.row["values"], UNIT: unit}}
    return replace(inst, observation_inputs={**inst.observation_inputs, oid: replace(obs, row=row)})


def test_several_distinct_units_hold_under_their_own_countable_reason(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)
    conflicted = _with_unit(b, "n1", ["users", "licences_or_seats"])
    metrics = _run(run_dir, bound, instrument, [a, conflicted], e.FakeQuotes())
    assert metrics.written == [A]
    assert metrics.held == [B] and B not in metrics.failed  # a ruled hold, not an envelope failure
    assert not (institution_dir(run_dir, B) / "6_storage.json").exists()
    held = _held(run_dir, B)
    assert held["reasons"] == [rt.SCALE_UNIT_CONFLICT] == ["scale_unit_conflict"]
    assert held["item_id"] == UNIT
    assert held["conflicts"] == [{"observation_ids": ["n1"], "units": ["users", "licences_or_seats"]}]
    assert _ledger(run_dir, B) == [f"{rt.HELD_REASON}:{rt.SCALE_UNIT_CONFLICT}"]


def test_scale_unit_conflict_hold_is_released_when_a_later_pass_publishes(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    _, b = e._institutions(run_dir, bound, instrument)
    _run(run_dir, bound, instrument, [_with_unit(b, "n1", ["users", "licences_or_seats"])], e.FakeQuotes())
    assert _run(run_dir, bound, instrument, [b], e.FakeQuotes()).written == [B]
    assert _ledger(run_dir, B) == [f"{rt.HELD_REASON}:{rt.SCALE_UNIT_CONFLICT}", rt.HELD_RELEASED]
    assert not (institution_dir(run_dir, B) / rt.WORK_DIR / rt.HELD_FILE).exists()


def test_other_malformed_unit_values_keep_the_generic_storage_refusal(tmp_path):
    # Only several distinct unit codes are the Def5b case; any other non-string value is not reclassified.
    run_dir, bound, instrument = e._setup(tmp_path)
    _, b = e._institutions(run_dir, bound, instrument)
    metrics = _run(run_dir, bound, instrument, [_with_unit(b, "n1", ["users", 3])], e.FakeQuotes())
    assert metrics.failed == [B]
    assert _held(run_dir, B)["reasons"] == [rt.ENVELOPE_FAILED]
