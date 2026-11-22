"""The codebook r16 switch (RC-D-034 A8.1 a / A8.5 a; PI ruling 140: built against the draft, then signed).

Under the r16 pin (``codebook/codebook.yaml`` and the generated files are the r16 bytes) the switch is on and
the r16 refusals are lifted; an explicit ``r16_on=False`` still gives every r15 list unchanged. The r16
producers are pure and tested on fake data.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from g3o.codebook import r16_candidate as r16
from g3o.codebook.generated import enums
from g3o.common import source_fields as sf
from g3o.run.presweep import source_row_v27 as srow
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.validate import merged_activity_v27 as ma

FIXTURE = Path(__file__).parent / "fixtures" / "codebook_r16_candidate" / "codebook.yaml"
R15_REFUSED = {"core.developer", "core.developer_basis", "core.stage_as_of_basis"}
R15_STAGE6 = {"core.stage_as_of", "core.date_upper_bound", "core.vendor_claim_only", "core.cx_display_rollup"}


CODEBOOK = Path(__file__).resolve().parents[1] / "codebook" / "codebook.yaml"


def _with_developer(monkeypatch):
    """The pass-1 fields the r16 codebook asks: the r15 ones plus core.developer (quote_step)."""
    fields = (*(f for f in srow.pass1_activity_fields() if f != "core.developer"), "core.developer")
    monkeypatch.setattr(srow, "pass1_activity_fields", lambda: fields)


def _without_developer(monkeypatch):
    """A codebook in use that asks no developer quote task (the gate of review O2-r16 M1)."""
    fields = tuple(f for f in srow.pass1_activity_fields() if f != "core.developer")
    monkeypatch.setattr(srow, "pass1_activity_fields", lambda: fields)


def test_candidate_fixture_bytes_match_the_pin():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == r16.R16_CANDIDATE_SHA256


def test_the_codebook_in_use_is_the_r18_candidate_built_on_r16():
    """The r18 candidate (byte edits to the signed r17 file, itself built on r16) is in use; the r16 fixture
    stays as r16."""
    assert hashlib.sha256(CODEBOOK.read_bytes()).hexdigest() == r16.R18_CANDIDATE_SHA256
    assert r16.R16_FIELD_RELEASES == (r16.R16_CANDIDATE_SHA256, r16.R17_CANDIDATE_SHA256, r16.R18_CANDIDATE_SHA256)
    live, base = yaml.safe_load(CODEBOOK.read_bytes())["items"], yaml.safe_load(FIXTURE.read_bytes())["items"]
    for item in ("core.developer", "core.developer_basis", "core.stage_as_of_basis"):  # the r16 fields keep their shape
        for key in ("coder", "linkage", "pass", "round", "gate", "answer_type"):
            assert live[item][key] == base[item][key], (item, key)
        codes = lambda it: [v["code"] for v in it["values"]] if isinstance(it.get("values"), list) else it.get("values")  # noqa: E731
        assert codes(live[item]) == codes(base[item]), item


def test_candidate_codes_and_coder_match_the_producers():
    items = yaml.safe_load(FIXTURE.read_bytes())["items"]
    assert tuple(v["code"] for v in items["core.stage_as_of_basis"]["values"]) == r16.STAGE_AS_OF_BASIS_CODES
    assert r16.STAGE_AS_OF_BASIS_CODES == (ma.STEP_PUBLICATION, ma.STEP_STATED, ma.STEP_ACCESS)
    dev = items["core.developer"]
    assert (dev["coder"], dev["linkage"]) == ("quote_step", "extractor")
    assert "`developer_basis` = stated" in dev["rules"][3]["text"]


def test_r16_pin_turns_r16_on_and_lifts_the_refusals():
    """Codebook r16 in use (signing commit): the generated pins are the r16 SHA, pass 1 asks the developer
    (``items/core.developer``: quote_step, every applicability cell ``ask``), and every r16 list is active
    at import."""
    assert enums.CODEBOOK_SHA256 == r16.R18_CANDIDATE_SHA256  # r18 candidate: carries the r16 fields
    assert r16.r16_active() is True
    assert "core.developer" in srow.pass1_activity_fields()
    assert srow.REFUSED_ACTIVITY_ITEMS == {}
    assert set(srow.STAGE6_ACTIVITY_ITEMS) == R15_STAGE6 | {"core.stage_as_of_basis"}
    assert srow.CONDITIONAL_ITEMS == srow.conditional_items(True)
    assert "core.content_vendor" not in srow.CONDITIONAL_ITEMS and "core.developer_basis" in srow.CONDITIONAL_ITEMS
    assert srow.WIRING_ONLY_ITEMS == srow.WIRING_ONLY_ITEMS_R15 | {"core.content_vendor"}
    assert srow.EXTRACTED_FIELDS["core.content_vendor"] == ("core.contracting_party", "core.developer")
    assert srow.PRODUCED_ACTIVITY_ITEMS[-1] == "core.developer_basis"
    assert rt.MERGE_REFUSED_R1 == ()
    assert rt.MERGE_CREDIBLE == (*rt.MERGE_CREDIBLE_R15, "core.developer")
    assert rt.MERGE_BASIS == ("core.developer_basis",)
    assert ma.PRODUCED == (*ma.PRODUCED_R15, ma.STAGE_AS_OF_BASIS) and ma.STAGE_AS_OF_BASIS in rt.MERGE_PRODUCED_A8


def test_r16_without_a_developer_quote_task_keeps_both_developer_items_refused(monkeypatch):
    """Review O2-r16 M1 / review of 59ab80e: the developer items follow the per-page gate. A codebook in use
    that asks no developer quote task keeps both refused per page and both explicit merge inputs, and
    content_vendor does not read a developer; stage_as_of_basis is Stage 6's either way."""
    assert r16.r16_active() is True
    assert ma.STAGE_AS_OF_BASIS in ma.produced_items()
    assert "core.stage_as_of_basis" in srow.stage6_activity_items()
    with monkeypatch.context() as m:
        _without_developer(m)
        assert rt.merge_refused_r1() == ("core.developer", "core.developer_basis")
        assert rt.merge_credible() == rt.MERGE_CREDIBLE_R15 and rt.merge_basis() == ()
        assert set(srow.refused_activity_items()) == {"core.developer", "core.developer_basis"}
        assert "core.developer" not in srow.extracted_fields()["core.content_vendor"]
    _with_developer(monkeypatch)
    assert rt.merge_refused_r1() == ()
    assert rt.merge_credible() == (*rt.MERGE_CREDIBLE_R15, "core.developer")
    assert rt.merge_basis() == ("core.developer_basis",)
    assert "core.developer" in srow.extracted_fields()["core.content_vendor"]
    assert srow.refused_activity_items() == {}
    assert srow.produced_activity_items()[-1] == "core.developer_basis"
    cond = srow.conditional_items()
    assert "core.content_vendor" not in cond and "core.developer_basis" in cond and "core.developer" in cond
    assert "core.content_vendor" in srow.wiring_only_items()


def test_explicit_r16_off_matches_r15_even_when_patched(monkeypatch):
    monkeypatch.setattr(r16, "active_codebook_sha256", lambda: r16.R16_CANDIDATE_SHA256)
    assert srow.refused_activity_items(False) == srow.REFUSED_ACTIVITY_ITEMS_R15
    assert rt.merge_refused_r1(False) == rt.MERGE_REFUSED_R1_R15
    assert rt.merge_credible(False) == rt.MERGE_CREDIBLE_R15 and rt.merge_basis(False) == ()
    assert ma.produced_items(False) == ma.PRODUCED_R15


def _dated(step, date="2024-03-12", oid="o1"):
    return ma.DatedObservation(oid, "s1", date, step)


@pytest.mark.parametrize("step", [ma.STEP_PUBLICATION, ma.STEP_STATED, ma.STEP_ACCESS])
def test_stage_as_of_basis_is_the_chosen_step(step):
    assert ma.stage_as_of_basis([_dated(step), _dated(step, oid="o2")]) == step


# PI ruling Q168 a (2026-11-16): mixed steps on one date take the first step in the rule order
# publication, then stated, then access (was: held as unruled).
@pytest.mark.parametrize(("steps", "expect"), [
    ((ma.STEP_PUBLICATION, ma.STEP_STATED), ma.STEP_PUBLICATION),
    ((ma.STEP_STATED, ma.STEP_PUBLICATION), ma.STEP_PUBLICATION),
    ((ma.STEP_ACCESS, ma.STEP_STATED), ma.STEP_STATED),
    ((ma.STEP_ACCESS, ma.STEP_PUBLICATION), ma.STEP_PUBLICATION),
    ((ma.STEP_ACCESS, ma.STEP_STATED, ma.STEP_PUBLICATION), ma.STEP_PUBLICATION),
])
def test_stage_as_of_basis_with_mixed_steps_takes_the_first_in_rule_order_q168a(steps, expect):
    chosen = [_dated(step, "2024", f"o{n}") for n, step in enumerate(steps)]
    assert ma.stage_as_of_basis(chosen) == expect


def test_stage_as_of_basis_with_mixed_steps_still_refuses_an_unknown_step_q168a():
    with pytest.raises(ma.MalformedA8Value):
        ma.stage_as_of_basis([_dated(ma.STEP_PUBLICATION, "2024"), _dated("metadata", "2024", "o2")])


def test_stage_as_of_basis_refuses_an_empty_choice_and_an_unknown_step():
    with pytest.raises(ma.MalformedA8Value):
        ma.stage_as_of_basis([])
    with pytest.raises(ma.MalformedA8Value):
        ma.stage_as_of_basis([_dated("metadata")])


def test_merged_values_carry_the_basis_only_under_r16(tmp_path):
    from tests import test_e2e_stage6_v27 as e

    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    order = e.s6.observation_pool_order(a.quotes, ["o1", "o2"])
    assert ma.STAGE_AS_OF_BASIS not in ma.merged_values_a8(a, order, r16_on=False)  # r15 split
    on = ma.merged_values_a8(a, order, r16_on=True)
    _, chosen = ma.merged_stage_as_of(a, order)
    assert on[ma.STAGE_AS_OF_BASIS] == ma.stage_as_of_basis(chosen) == chosen[0].step
    assert ma.merged_values_a8(a, order) == on  # r16 pin: the default is the r16 split


def test_developer_basis_is_stated_for_a_stated_developer():
    row = srow.developer_basis_value("OpenAI")
    assert (row.item_id, row.value) == ("core.developer_basis", "stated")


# PI ruling Q165 a (2026-11-16): a missing-token developer gives the basis the same token (was: unruled, held).
@pytest.mark.parametrize("token", ["not_documented", "unknown", "not_asked", "_NA_"])
def test_developer_basis_of_a_missing_token_takes_the_same_token_q165a(token):
    row = srow.developer_basis_value(token)
    assert (row.item_id, row.value) == ("core.developer_basis", token)
    assert "Q165 a" in row.basis


def test_developer_basis_tokens_are_the_developer_tokens_in_the_candidate():
    """Q165 a relies on every developer missing token being a developer_basis missing token."""
    items = yaml.safe_load(FIXTURE.read_bytes())["items"]
    assert set(items["core.developer"]["missing_tokens"]) <= set(items["core.developer_basis"]["missing_tokens"])


def test_developer_basis_is_no_longer_conditional_on_a_missing_token_q165a(monkeypatch):
    _with_developer(monkeypatch)
    note = srow.conditional_items(True)["core.developer_basis"]
    assert "missing token" not in note and "refused when core.developer is refused" in note


def test_developer_basis_refuses_absent_and_non_text_developer():
    with pytest.raises(sf.MissingUpstreamError):
        srow.developer_basis_value(None)
    with pytest.raises(ValueError):
        srow.developer_basis_value(["OpenAI"])


def test_content_vendor_reads_an_extracted_developer_under_r16(monkeypatch):
    from types import SimpleNamespace

    _with_developer(monkeypatch)
    monkeypatch.setattr(srow, "EXTRACTED_FIELDS", srow.extracted_fields(True))
    verdict = next(iter(srow.genai_verdicts()))
    span = SimpleNamespace(fields=(SimpleNamespace(item_id="core.developer"),))
    assert srow.content_extracted("core.content_vendor", verdict, ["a1"], {"a1": span}).value == "yes"
    empty = SimpleNamespace(fields=())
    assert srow.content_extracted("core.content_vendor", verdict, ["a1"], {"a1": empty}).value == "no"
    monkeypatch.setattr(srow, "EXTRACTED_FIELDS", srow.extracted_fields(False))
    with pytest.raises(sf.MissingUpstreamError):
        srow.content_extracted("core.content_vendor", verdict, ["a1"], {"a1": empty})


# --- PI ruling Q166 a (2026-11-16): Stage 6 merge of developer / developer_basis under r16 ---------------


def _dev_inst(devs, confidence):
    from tests.test_stage6_runtime_qa import _merge_inst, _row

    return _merge_inst({k: _row(**{"core.developer": v}) for k, v in devs.items()}, confidence)


def test_r16_merge_takes_the_most_credible_real_developer_and_states_its_basis_q166a():
    inst = _dev_inst({"o1": "not_documented", "o2": "OpenAI", "o3": "Microsoft"},
                     {"o1": "high", "o2": "low", "o3": "medium"})
    out = rt.merge_values(inst, ["o1", "o2", "o3"], r16_on=True)
    assert out["core.developer"] == "Microsoft"  # medium > low; a missing token never wins over a real value
    assert out["core.developer_basis"] == "stated"
    tie = _dev_inst({"o1": "OpenAI", "o2": "Microsoft"}, {"o1": "medium", "o2": "medium"})
    assert rt.merge_values(tie, ["o2", "o1"], r16_on=True)["core.developer"] == "Microsoft"  # pool order


@pytest.mark.parametrize("token", ["not_documented", "unknown", "not_asked", "_NA_"])
def test_r16_merge_basis_of_a_missing_developer_takes_its_token_q166a_q165a(token):
    inst = _dev_inst({"o1": token, "o2": token}, {"o1": "high", "o2": "low"})
    out = rt.merge_values(inst, ["o1", "o2"], r16_on=True)
    assert out["core.developer"] == token and out["core.developer_basis"] == token


def test_r16_merge_refuses_a_blank_merged_developer_q166a():
    from g3o.validate.consolidate_v27 import ConsolidationError

    inst = _dev_inst({"o1": "  ", "o2": "  "}, {"o1": "high", "o2": "low"})
    with pytest.raises(ConsolidationError):
        rt.merge_values(inst, ["o1", "o2"], r16_on=True)


def test_r15_merge_does_not_touch_developer_q166a():
    inst = _dev_inst({"o1": "OpenAI", "o2": "Microsoft"}, {"o1": "low", "o2": "high"})
    out = rt.merge_values(inst, ["o1", "o2"], r16_on=False)
    assert "core.developer" not in out and "core.developer_basis" not in out


def test_r16_pin_merge_takes_the_developer_by_default_q166a():
    inst = _dev_inst({"o1": "OpenAI", "o2": "Microsoft"}, {"o1": "low", "o2": "high"})
    out = rt.merge_values(inst, ["o1", "o2"])
    assert (out["core.developer"], out["core.developer_basis"]) == ("Microsoft", "stated")
