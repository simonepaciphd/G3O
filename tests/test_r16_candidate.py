"""The UNSIGNED codebook r16 candidate switch (RC-D-034 A8.1 a / A8.5 a; PI ruling 140: built against the draft).

Under the signed r15 pin the switch is off and every refusal list keeps its r15 contents; the r16 producers
are pure and tested on fake data; with the active SHA patched to the candidate the refusals lift.
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


def _with_developer(monkeypatch):
    """The pass-1 fields a regenerated r16 codebook asks: the r15 ones plus core.developer (quote_step)."""
    fields = (*srow.pass1_activity_fields(), "core.developer")
    monkeypatch.setattr(srow, "pass1_activity_fields", lambda: fields)


def test_candidate_fixture_bytes_match_the_pin():
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == r16.R16_CANDIDATE_SHA256


def test_candidate_codes_and_coder_match_the_producers():
    items = yaml.safe_load(FIXTURE.read_bytes())["items"]
    assert tuple(v["code"] for v in items["core.stage_as_of_basis"]["values"]) == r16.STAGE_AS_OF_BASIS_CODES
    assert r16.STAGE_AS_OF_BASIS_CODES == (ma.STEP_PUBLICATION, ma.STEP_STATED, ma.STEP_ACCESS)
    dev = items["core.developer"]
    assert (dev["coder"], dev["linkage"]) == ("quote_step", "extractor")
    assert "`developer_basis` = stated" in dev["rules"][3]["text"]


def test_r15_pin_keeps_r16_off_and_the_refusals_unchanged():
    assert enums.CODEBOOK_SHA256 != r16.R16_CANDIDATE_SHA256
    assert r16.r16_active() is False
    assert set(srow.REFUSED_ACTIVITY_ITEMS) == R15_REFUSED and srow.REFUSED_ACTIVITY_ITEMS == srow.REFUSED_ACTIVITY_ITEMS_R15
    assert set(srow.STAGE6_ACTIVITY_ITEMS) == R15_STAGE6
    assert srow.CONDITIONAL_ITEMS == srow.CONDITIONAL_ITEMS_R15 and "core.content_vendor" in srow.CONDITIONAL_ITEMS
    assert srow.WIRING_ONLY_ITEMS == srow.WIRING_ONLY_ITEMS_R15
    assert dict(srow.EXTRACTED_FIELDS) == dict(srow.EXTRACTED_FIELDS_R15)
    assert "core.developer_basis" not in srow.PRODUCED_ACTIVITY_ITEMS
    assert rt.MERGE_REFUSED_R1 == ("core.developer", "core.developer_basis", "core.stage_as_of_basis")
    assert ma.PRODUCED == ma.PRODUCED_R15 and ma.STAGE_AS_OF_BASIS not in rt.MERGE_PRODUCED_A8


def test_patched_active_sha_lifts_the_refusals(monkeypatch):
    monkeypatch.setattr(r16, "active_codebook_sha256", lambda: r16.R16_CANDIDATE_SHA256)
    assert r16.r16_active() is True
    # Stage 6: stage_as_of_basis is produced; developer / developer_basis stay explicit merge inputs.
    assert ma.STAGE_AS_OF_BASIS in ma.produced_items()
    assert rt.merge_refused_r1() == ("core.developer", "core.developer_basis")
    assert "core.stage_as_of_basis" in srow.stage6_activity_items()
    # Per page: without a developer quote task in the codebook in use, both developer items stay refused and
    # content_vendor does not read a developer (review O2-r16 M1: same gate as the refusals).
    assert set(srow.refused_activity_items()) == {"core.developer", "core.developer_basis"}
    assert "core.developer" not in srow.extracted_fields()["core.content_vendor"]
    _with_developer(monkeypatch)
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
    assert ma.STAGE_AS_OF_BASIS not in ma.merged_values_a8(a, order)  # r15 pin
    on = ma.merged_values_a8(a, order, r16_on=True)
    _, chosen = ma.merged_stage_as_of(a, order)
    assert on[ma.STAGE_AS_OF_BASIS] == ma.stage_as_of_basis(chosen) == chosen[0].step


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
