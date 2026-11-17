"""A8 producers of an activity's derived values (PI A8 rulings 2026-11-11; rulings 66 a, 76 b, 77 a,
78 a, 88 a, 89 a, 90 c).

Unit tests drive :mod:`g3o.validate.merged_activity_v27` with declared observation
and source rows; the envelope tests run the mocked Stage 6 path of
``tests/test_e2e_stage6_v27.py`` (no network, every provider answer a fake).
"""
from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from g3o.common import source_fields as sf
from g3o.common.paths import institution_dir
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import SET_BY_RULE
from g3o.persist.stage6_adapters import MissingUpstreamError
from g3o.run.presweep import source_row_v27 as srow
from g3o.run.presweep import stage_validate_v27 as rt
from g3o.validate import merged_activity_v27 as ma
from tests import test_e2e_stage6_v27 as e
from tests import test_stage6_runtime_qa as qa


def _obs(**over):
    base = {"core.year_announced": "not_documented", "core.year_pilot_start": "not_documented",
            "core.year_production_start": "not_asked",
            "core.observed_actor_relationship": {"relationship": "this_institution",
                                                 "searched_institution_role": "contracting_authority"}}
    return {**base, **over}


def _src(**over):
    # date_upper_bound: no beside a real publication date (no producer stores yes, A8.12 a), not_asked
    # beside a missing one (source_fields.date_upper_bound).
    base = {"core.source_publication_date": "not_documented", "core.source_access_date": "2026-11-01",
            "core.date_upper_bound": "not_asked", "core.source_type": "news_major"}
    out = {**base, **over}
    if "core.date_upper_bound" not in over and out["core.source_publication_date"] not in FIELDS[
            "core.source_publication_date"]["missing_tokens"]:
        out["core.date_upper_bound"] = "no"
    return out


def _typed_node(rule, value="not_asked"):
    """A stored source_type support node as ``stage6_adapters.support_nodes`` writes a set_by_rule code."""
    return {"item_id": "core.source_type", "item_part": None, "value_json": value, "support_status": SET_BY_RULE,
            "support_rule_name": rule, "support_id": f"n-{rule}"}


def _inst(obs, srcs, source_of=None, support=None):
    """``obs``: oid -> activity row values; ``srcs``: sid -> source row values; ``source_of``: oid -> sid;
    ``support``: sid -> stored support nodes of the source row."""
    source_of = source_of or {k: f"S-{k}" for k in obs}
    support = support or {}
    inputs = {k: rt.ObservationInput(k, source_of[k], {"values": v}) for k, v in obs.items()}
    return SimpleNamespace(observation_inputs=inputs,
                           sources={s: {"values": v, "item_support": list(support.get(s, ()))}
                                    for s, v in srcs.items()})


# --- module split ---------------------------------------------------------------------------------


def test_a8_split_produced_and_refused_items():
    # Codebook r16: stage_as_of_basis is produced here (A8.5 a); cx_display_rollup since ruling 77 a.
    assert set(rt.MERGE_PRODUCED_A8) == {"core.stage_as_of", "core.date_upper_bound", "core.unit_credit",
                                         "core.vendor_claim_only", "core.cx_display_rollup",
                                         "core.stage_as_of_basis"}
    # Codebook r16 (A8.1 a, PI ruling Q166 a): developer is an R3 item and developer_basis follows it,
    # so no X1 a R1 item is an explicit merge input any more.
    assert rt.MERGE_REFUSED_R1 == ()
    assert "core.developer" in rt.MERGE_CREDIBLE and rt.MERGE_BASIS == ("core.developer_basis",)
    assert not set(rt.MERGE_PRODUCED_A8) & rt.MERGE_INPUT_ITEMS
    # PI ruling Q166 a: MERGE_BASIS (developer_basis) joins the split under r16
    assert rt._non_pooled_items() == (rt.MERGE_INPUT_ITEMS | set(rt.MERGE_UNION) | set(rt.MERGE_CREDIBLE)
                                      | set(rt.MERGE_DERIVED) | set(rt.MERGE_PRODUCED_A8) | set(rt.MERGE_BASIS))


# --- stage_as_of (A8.3 a, A8.4 a, A8.6 a; 76 b, 90 c) -----------------------------------------------


def test_stage_as_of_steps_publication_then_latest_year_then_access():
    inst = _inst({"o1": _obs(**{"core.year_announced": "2023"}),
                  "o2": _obs(**{"core.year_announced": "2022", "core.year_production_start": "2024"}),
                  "o3": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2025-02-03"}),
                  "S-o2": _src(**{"core.source_publication_date": "unknown"}),  # failed R-042: not supported
                  "S-o3": _src()})
    assert ma.observation_stage_as_of(inst, "o1") == ma.DatedObservation("o1", "S-o1", "2025-02-03", "publication")
    assert ma.observation_stage_as_of(inst, "o2") == ma.DatedObservation("o2", "S-o2", "2024", "stated")
    assert ma.observation_stage_as_of(inst, "o3") == ma.DatedObservation("o3", "S-o3", "2026-11-01", "access")


def test_merged_stage_as_of_is_the_latest_pooled_date():
    inst = _inst({"o1": _obs(), "o2": _obs(**{"core.year_announced": "2023"})},
                 {"S-o1": _src(**{"core.source_publication_date": "2025-05"}),
                  "S-o2": _src(**{"core.source_access_date": "2026-01-01"})})
    assert ma.merged_stage_as_of(inst, ["o1", "o2"])[0] == "2025-05"  # 2025-05 after year 2023
    inst = _inst({"o1": _obs(**{"core.year_announced": "2022"}), "o2": _obs(**{"core.year_announced": "2024"})},
                 {"S-o1": _src(), "S-o2": _src()})
    date, chosen = ma.merged_stage_as_of(inst, ["o1", "o2"])
    assert date == "2024" and [c.observation_id for c in chosen] == ["o2"]


def test_access_date_counts_only_when_no_observation_has_a_real_date_ruling_90c():
    # Literal A8.4 a / A8.6 a would take o2's access date 2026-11-01 over o1's real date 2024.
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2024"}), "S-o2": _src()})
    date, chosen = ma.merged_stage_as_of(inst, ["o1", "o2"])
    assert date == "2024" and [c.observation_id for c in chosen] == ["o1"]
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_access_date": "2026-10-01"}), "S-o2": _src()})
    date, chosen = ma.merged_stage_as_of(inst, ["o1", "o2"])  # no real date anywhere: latest access date
    assert date == "2026-11-01" and [c.step for c in chosen] == ["access"]


@pytest.mark.parametrize("access", ["not_documented", "unknown", None])
def test_an_unused_access_date_does_not_hold_ruling_90c(access):
    # o1 has a real date (2024), so o2's access date is never used: no hold, whatever it is.
    o2_src = _src(**{"core.source_access_date": access})
    if access is None:
        o2_src.pop("core.source_access_date")
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2024"}), "S-o2": o2_src})
    date, chosen = ma.merged_stage_as_of(inst, ["o1", "o2"])
    assert date == "2024" and [c.observation_id for c in chosen] == ["o1"]
    inst = _inst({"o1": _obs(**{"core.year_announced": "2024"}), "o2": _obs()}, {"S-o1": _src(), "S-o2": o2_src})
    assert ma.merged_stage_as_of(inst, ["o1", "o2"])[0] == "2024"  # a stated year is a real date too
    # used: no pooled real date, so o2's access date is needed and its absence holds
    inst = _inst({"o1": _obs(), "o2": _obs()}, {"S-o1": _src(), "S-o2": o2_src})
    with pytest.raises(MissingUpstreamError, match="S-o2"):
        ma.merged_stage_as_of(inst, ["o1", "o2"])
    with pytest.raises(MissingUpstreamError):  # alone, an observation falls to its access date
        ma.observation_stage_as_of(inst, "o2")


def test_an_access_date_is_required_for_the_future_test_of_a_stated_year_ruling_90c():
    # o2 states a year: is_future_year needs its access year even though o1 has a real date.
    inst = _inst({"o1": _obs(), "o2": _obs(**{"core.year_announced": "2023"})},
                 {"S-o1": _src(**{"core.source_publication_date": "2024"}),
                  "S-o2": _src(**{"core.source_access_date": "not_documented"})})
    with pytest.raises(MissingUpstreamError, match="S-o2"):
        ma.merged_stage_as_of(inst, ["o1", "o2"])
    # an unused access date is still checked for its signed form (wiring error)
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2024"}),
                  "S-o2": _src(**{"core.source_access_date": "Nov 2026"})})
    with pytest.raises(ma.MalformedA8Value, match="neither a date"):
        ma.merged_stage_as_of(inst, ["o1", "o2"])


def test_future_year_codes_are_excluded_ruling_90c():
    # PROVISIONAL definition (pending PI confirmation): later than the observation's access-date year.
    assert ma.is_future_year("2027", "2026-11-01") and not ma.is_future_year("2026", "2026-11-01")
    inst = _inst({"o1": _obs(**{"core.year_announced": "2025", "core.year_production_start": "2028"})},
                 {"S-o1": _src()})
    assert ma.observation_stage_as_of(inst, "o1") == ma.DatedObservation("o1", "S-o1", "2025", "stated", ("2028",))
    inst = _inst({"o1": _obs(**{"core.year_production_start": "2028"}), "o2": _obs()},
                 {"S-o1": _src(), "S-o2": _src(**{"core.source_access_date": "2026-03-01"})})
    dated = ma.observation_stage_as_of(inst, "o1")
    assert dated.step == "access" and dated.future_years == ("2028",)  # only a future year: no real date
    assert ma.merged_stage_as_of(inst, ["o1", "o2"])[0] == "2026-11-01"


@pytest.mark.parametrize("dates,expect", [
    (("2024-03", "2024-03-12"), "2024-03-12"),
    (("2024", "2024-03-12"), "2024-03-12"),
    (("2024", "2024-03", "2024-03-01"), "2024-03-01"),
    (("2024", "2024-03", "2024-05"), "2024-05"),  # 2024 agrees with both; 2024-05 after 2024-03
    (("2023-12-31", "2024"), "2024"),
])
def test_dates_agreeing_on_their_shared_prefix_are_one_date_ruling_76b(dates, expect):
    oids = [f"o{n}" for n in range(len(dates))]
    inst = _inst({k: _obs() for k in oids},
                 {f"S-{k}": _src(**{"core.source_publication_date": d}) for k, d in zip(oids, dates, strict=True)})
    date, chosen = ma.merged_stage_as_of(inst, oids)
    assert date == expect and [c.date for c in chosen] == [expect]


def test_a_year_code_and_a_publication_date_with_the_same_prefix_ruling_76b():
    inst = _inst({"o1": _obs(), "o2": _obs(**{"core.year_announced": "2024"})},
                 {"S-o1": _src(**{"core.source_publication_date": "2024-03-12"}), "S-o2": _src()})
    date, chosen = ma.merged_stage_as_of(inst, ["o1", "o2"])
    assert date == "2024-03-12" and [c.observation_id for c in chosen] == ["o1"]


def test_identical_latest_dates_are_one_date():
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2025-01"}),
                  "S-o2": _src(**{"core.source_publication_date": "2025-01"})})
    date, chosen = ma.merged_stage_as_of(inst, ["o1", "o2"])
    assert date == "2025-01" and len(chosen) == 2


@pytest.mark.parametrize("where,item", [("source", "core.source_publication_date"),
                                        ("obs", "core.year_announced")])
def test_stage_as_of_refuses_an_absent_input(where, item):
    obs, src = _obs(), _src()
    (src if where == "source" else obs).pop(item)
    with pytest.raises(MissingUpstreamError):
        ma.observation_stage_as_of(_inst({"o1": obs}, {"S-o1": src}), "o1")


def test_stage_as_of_absent_inputs_hold_and_malformed_values_are_wiring_errors():
    inst = _inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_access_date": "not_documented"})})
    with pytest.raises(MissingUpstreamError):
        ma.observation_stage_as_of(inst, "o1")
    # 90 c reads the access year whenever a year code is stated
    inst = _inst({"o1": _obs(**{"core.year_announced": "2024"})},
                 {"S-o1": _src(**{"core.source_access_date": "unknown"})})
    with pytest.raises(MissingUpstreamError):
        ma.observation_stage_as_of(inst, "o1")
    inst = _inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_publication_date": "March 2024",
                                                  "core.date_upper_bound": "no"})})
    with pytest.raises(ma.MalformedA8Value, match="neither a date"):
        ma.observation_stage_as_of(inst, "o1")
    inst = _inst({"o1": _obs(**{"core.year_announced": "FY24"})}, {"S-o1": _src()})
    with pytest.raises(ma.MalformedA8Value, match="neither a year code"):
        ma.observation_stage_as_of(inst, "o1")
    inst = _inst({"o1": _obs()}, {})
    with pytest.raises(MissingUpstreamError):
        ma.observation_stage_as_of(inst, "o1")
    assert not issubclass(ma.MalformedA8Value, ValueError)  # no per-institution hold catches it


# --- date_upper_bound (A8.11 a, A8.12 a) ------------------------------------------------------------


def test_date_upper_bound_follows_stage_as_of():
    # merged_values_a8 also builds cx_display_rollup, which reads every CX item: _cx_src rows.
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _cx_src(**{"core.source_publication_date": "2025-06"}),
                  "S-o2": _cx_src(**{"core.source_publication_date": "2024"})})
    assert ma.merged_values_a8(inst, ["o1", "o2"])["core.date_upper_bound"] == "no"
    # a year code or an access date has no archive origin: no
    inst = _inst({"o1": _obs(**{"core.year_announced": "2025"})}, {"S-o1": _cx_src()})
    assert ma.merged_values_a8(inst, ["o1"])["core.date_upper_bound"] == "no"
    inst = _inst({"o1": _obs()}, {"S-o1": _cx_src()})
    assert ma.merged_values_a8(inst, ["o1"])["core.date_upper_bound"] == "no"
    inst = _inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_publication_date": "2025-06"})})
    assert ma.merged_date_upper_bound(inst, ma.merged_stage_as_of(inst, ["o1"])[1]) == "no"


def test_date_upper_bound_token_beside_a_real_date_is_malformed():
    inst = _inst({"o1": _obs()}, {"S-o1": _cx_src(**{"core.source_publication_date": "2025",
                                                     "core.date_upper_bound": "not_asked"})})
    with pytest.raises(ma.MalformedA8Value, match="is not yes/no"):
        ma.merged_values_a8(inst, ["o1"])
    src = _cx_src(**{"core.source_publication_date": "2025"})
    src.pop("core.date_upper_bound")
    with pytest.raises(MissingUpstreamError, match="core.date_upper_bound"):
        ma.merged_values_a8(_inst({"o1": _obs()}, {"S-o1": src}), ["o1"])


# --- unit_credit (A8.7 a, A8.8 a, 66 a) -------------------------------------------------------------


def _rel(value):
    return _obs(**{"core.observed_actor_relationship": value})


@pytest.mark.parametrize("value,expect", [
    ({"relationship": "unit_of_institution", "searched_institution_role": "unit"}, "yes"),
    ({"relationship": "this_institution", "searched_institution_role": "contracting_authority"}, "no"),
    ({"relationship": "unresolved", "searched_institution_role": "not_asked"}, "no"),
    ({"relationship": "unknown", "searched_institution_role": "not_asked"}, "no"),  # 66 a: read literally
])
def test_unit_credit_reads_the_relationship_literally(value, expect):
    inst = _inst({"o1": _rel(value)}, {"S-o1": _src()})
    assert ma.observation_unit_credit(inst, "o1") == expect


def test_merged_unit_credit_is_yes_if_any_pooled_observation_is():
    unit = {"relationship": "unit_of_institution", "searched_institution_role": "unit"}
    inst = _inst({"o1": _obs(), "o2": _rel(unit)}, {"S-o1": _src(), "S-o2": _src()})
    assert ma.merged_unit_credit(inst, ["o1", "o2"]) == "yes"
    assert ma.merged_unit_credit(inst, ["o1"]) == "no"


def test_unit_credit_absent_part_holds_and_malformed_relationship_is_a_wiring_error():
    inst = _inst({"o1": _rel({"searched_institution_role": "unit"})}, {"S-o1": _src()})
    with pytest.raises(MissingUpstreamError):
        ma.observation_unit_credit(inst, "o1")
    obs = _obs()
    obs.pop("core.observed_actor_relationship")
    with pytest.raises(MissingUpstreamError):
        ma.observation_unit_credit(_inst({"o1": obs}, {"S-o1": _src()}), "o1")
    # storage holds the two-part object (storage.validate_value); a bare token is not that shape
    with pytest.raises(ma.MalformedA8Value, match="two-part object"):
        ma.observation_unit_credit(_inst({"o1": _rel("not_asked")}, {"S-o1": _src()}), "o1")
    with pytest.raises(ma.MalformedA8Value, match="not a signed code"):
        ma.observation_unit_credit(_inst({"o1": _rel({"relationship": "subsidiary",
                                                      "searched_institution_role": "unit"})},
                                         {"S-o1": _src()}), "o1")


# --- vendor_claim_only (A8.9 a, 88 a, 89 a) ---------------------------------------------------------


def test_vendor_claim_only_every_supporting_source_vendor():
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_type": "vendor"}), "S-o2": _src(**{"core.source_type": "vendor"})})
    assert ma.merged_vendor_claim_only(inst, ["o1", "o2"]) == "yes"
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_type": "vendor"}), "S-o2": _src()})
    assert ma.merged_vendor_claim_only(inst, ["o1", "o2"]) == "no"


@pytest.mark.parametrize("missing", ["not_documented", "unknown"])
def test_vendor_claim_only_any_missing_type_gives_unknown(missing):
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_type": "vendor"}), "S-o2": _src(**{"core.source_type": missing})})
    assert ma.merged_vendor_claim_only(inst, ["o1", "o2"]) == "unknown"
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(), "S-o2": _src(**{"core.source_type": missing})})
    assert ma.merged_vendor_claim_only(inst, ["o1", "o2"]) == "unknown"  # A8.9 a read literally


def test_vendor_claim_only_reads_the_stored_typing_rule_ruling_88a():
    not_asked = _src(**{"core.source_type": "not_asked"})
    vendor = _src(**{"core.source_type": "vendor"})
    official = [_typed_node(sf.AUTO_RULE + sf.AUTO_OFFICIAL)]
    archive = [_typed_node(sf.AUTO_RULE + sf.AUTO_ARCHIVE)]
    unreadable = [_typed_node(sf.READABILITY_RULE + "too_short")]
    one = {"o1": _obs()}
    assert ma.source_type_of(_inst(one, {"S-o1": not_asked}, support={"S-o1": official}), "S-o1") == "official_domain"
    assert ma.source_type_of(_inst(one, {"S-o1": not_asked}, support={"S-o1": archive}), "S-o1") == "archive_address"
    assert ma.source_type_of(_inst(one, {"S-o1": not_asked}, support={"S-o1": unreadable}), "S-o1") is None
    for nodes, expect in ((official, "no"), (archive, "no"), (unreadable, "unknown")):
        inst = _inst({"o1": _obs(), "o2": _obs()}, {"S-o1": vendor, "S-o2": not_asked}, support={"S-o2": nodes})
        assert ma.merged_vendor_claim_only(inst, ["o1", "o2"]) == expect


def test_vendor_claim_only_typing_node_absent_unknown_or_ambiguous_rule_is_malformed():
    # A not_asked type is always stored with its set_by_rule node: without it (or without any
    # support list) the row is structurally broken, a wiring error (32 b), never re-derived.
    not_asked = {"S-o1": _src(**{"core.source_type": "not_asked"})}
    with pytest.raises(ma.MalformedA8Value, match="set_by_rule support node"):
        ma.merged_vendor_claim_only(_inst({"o1": _obs()}, not_asked), ["o1"])
    inst = _inst({"o1": _obs()}, not_asked)
    del inst.sources["S-o1"]["item_support"]
    with pytest.raises(ma.MalformedA8Value, match="no item_support list"):
        ma.merged_vendor_claim_only(inst, ["o1"])
    for nodes in ([_typed_node("source_type_auto:somewhere")],
                  [_typed_node(sf.AUTO_RULE + sf.AUTO_OFFICIAL), _typed_node(sf.AUTO_RULE + sf.AUTO_ARCHIVE)]):
        with pytest.raises(ma.MalformedA8Value):
            ma.merged_vendor_claim_only(_inst({"o1": _obs()}, not_asked, support={"S-o1": nodes}), ["o1"])


def test_vendor_claim_only_counts_a_shared_source_once_and_refuses_absent_or_malformed_type():
    inst = _inst({"o1": _obs(), "o2": _obs()}, {"S1": _src(**{"core.source_type": "vendor"})},
                 source_of={"o1": "S1", "o2": "S1"})
    assert ma.supporting_sources(inst, ["o2", "o1"]) == ["S1"]
    assert ma.merged_vendor_claim_only(inst, ["o1", "o2"]) == "yes"
    src = _src()
    src.pop("core.source_type")
    with pytest.raises(MissingUpstreamError):
        ma.merged_vendor_claim_only(_inst({"o1": _obs()}, {"S-o1": src}), ["o1"])
    with pytest.raises(ma.MalformedA8Value, match="not a signed code"):
        ma.merged_vendor_claim_only(_inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_type": "blog"})}), ["o1"])


def test_supporting_sources_are_the_pooled_observations_sources_only_ruling_89a():
    # S-x is one of the institution's source rows (e.g. counted in n_sources elsewhere) but no pooled
    # observation's claim: it does not count, whatever its type.
    inst = _inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_type": "vendor"}),
                                  "S-x": _src(**{"core.source_type": "news_major"})})
    assert ma.supporting_sources(inst, ["o1"]) == ["S-o1"]
    assert ma.merged_vendor_claim_only(inst, ["o1"]) == "yes"
    inst.sources["S-x"]["values"]["core.source_type"] = "not_documented"
    assert ma.merged_vendor_claim_only(inst, ["o1"]) == "yes"


# --- contract with the T-015 assembler's stored shapes ----------------------------------------------


@pytest.mark.parametrize("relationship", [
    {"relationship": "unit_of_institution", "searched_institution_role": "unit"},
    {"relationship": "this_institution", "searched_institution_role": "contracting_authority"},
    {"relationship": "unknown", "searched_institution_role": "not_asked"},
])
def test_unit_credit_agrees_with_the_t015_assembler(relationship):
    per_page = srow.unit_credit({"core.observed_actor_relationship": relationship}).value
    stage6 = ma.observation_unit_credit(_inst({"o1": _rel(relationship)}, {"S-o1": _src()}), "o1")
    assert stage6 == per_page and isinstance(stage6, str) and stage6 in FIELDS["core.unit_credit"]["codes"]


@pytest.mark.parametrize("relationship,kind", [
    ("not_asked", "malformed"),  # not the stored two-part object
    ({"relationship": "subsidiary", "searched_institution_role": "unit"}, "malformed"),  # unsigned part
    ({"searched_institution_role": "unit"}, "missing"),  # absent part
    (None, "missing"),  # absent value
])
def test_unit_credit_error_inputs_agree_with_the_t015_assembler(relationship, kind):
    # Both sides: an absent input is missing (Stage 6 holds; T-015 refuses); a value outside its signed
    # form is malformed (Stage 6 MalformedA8Value, a stage stop; T-015 its wiring ValueError).
    values = {} if relationship is None else {"core.observed_actor_relationship": relationship}
    obs = _obs()
    obs.pop("core.observed_actor_relationship")
    inst = _inst({"o1": {**obs, **values}}, {"S-o1": _src()})
    if kind == "missing":
        with pytest.raises(sf.MissingUpstreamError):
            srow.unit_credit(values)
        with pytest.raises(MissingUpstreamError):
            ma.observation_unit_credit(inst, "o1")
    else:
        with pytest.raises(ValueError) as info:
            srow.unit_credit(values)
        assert not isinstance(info.value, sf.MissingUpstreamError)
        with pytest.raises(ma.MalformedA8Value):
            ma.observation_unit_credit(inst, "o1")


@pytest.mark.parametrize("typing", ["official", "archive", "unreadable", "vendor", "news_major", "unknown"])
def test_vendor_claim_only_agrees_with_the_t015_assembler_ruling_88a(typing):
    # The stored shapes T-015 writes: source_type_value stores the typing field's value, and its
    # set_by_rule support node names the typing field's rule (rule_code -> support_nodes).
    if typing in ("official", "archive"):
        fv = sf.auto_source_type(sf.AUTO_OFFICIAL if typing == "official" else sf.AUTO_ARCHIVE).field
        value, rule = fv.value, fv.rule_name
    elif typing == "unreadable":
        value, rule = "not_asked", sf.READABILITY_RULE + "too_short"
    else:
        value, rule = typing, None
    per_page = srow.vendor_claim_only(value, rule).value
    support = {"S-o1": [_typed_node(rule)]} if rule else None
    stage6 = ma.merged_vendor_claim_only(_inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_type": value})},
                                               support=support), ["o1"])
    assert stage6 == per_page
    assert stage6 == {"official": "no", "archive": "no", "unreadable": "unknown", "vendor": "yes",
                      "news_major": "no", "unknown": "unknown"}[typing]


# --- cx_display_rollup (A8.10 a; table approved as drafted, 77 a) -----------------------------------


def _cx_src(**over):
    values = {item: ("no" if kind == ma.CX_YES else [] if kind == ma.CX_NON_EMPTY else "not_documented")
              for item, (kind, _) in ma.CX_POSITIVE.items()}
    return {**values, **_src(**over)}  # _src(**over): date_upper_bound follows an overridden publication date


def test_cx_table_covers_every_cx_item_stored_per_source_claim():
    from g3o.common.storage import table_fields
    sources = table_fields("sources")
    cx = {i for i in sources if i.startswith(("core.content_", "core.disclosure_", "core.evaluation_"))}
    assert set(ma.CX_POSITIVE) == cx
    for item, (kind, codes) in ma.CX_POSITIVE.items():
        if kind == ma.CX_CODES:
            assert [c for c in FIELDS[item]["codes"] if c in codes] == list(codes)
    assert "unclear" not in ma.CX_POSITIVE["core.evaluation_documented"][1]


def test_cx_rollup_is_approved_and_produced_ruling_77a():
    assert ma.CX_POSITIVE_APPROVED is True and "core.cx_display_rollup" not in rt.MERGE_REFUSED_R1
    inst = _inst({"o1": _obs()}, {"S-o1": _cx_src(**{"core.content_data": "yes"})})
    out = ma.cx_display_rollup(inst, ["o1"])
    assert out == ma._cx_rollup(inst, ["o1"]) and list(out) == ["core.content_data"]
    assert ma.merged_values_a8(inst, ["o1"])["core.cx_display_rollup"] == out
    assert out["core.content_data"]["combining_rule_ref"] == ma.CX_RULE_REF and "77 a" in ma.CX_RULE_REF


def test_cx_rollup_mechanism_any_positive_first_in_table_order():
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _cx_src(**{"core.content_data": "yes", "core.disclosure_form": "formal_record",
                                     "core.evaluation_documented": "unclear"}),
                  "S-o2": _cx_src(**{"core.disclosure_form": "mandated_report",
                                     "core.content_contact_emails": ["a@example.gov"],
                                     "core.evaluation_documented": "required_or_planned"})})
    out = ma.cx_display_rollup(inst, ["o1", "o2"])
    assert list(out) == ["core.content_contact_emails", "core.content_data", "core.disclosure_form",
                         "core.evaluation_documented"]  # CX_POSITIVE order
    assert {k: v["value"] for k, v in out.items()} == {
        "core.content_contact_emails": ["a@example.gov"], "core.content_data": "yes",
        "core.disclosure_form": "mandated_report", "core.evaluation_documented": "required_or_planned"}
    assert out["core.disclosure_form"]["source_ids"] == ["S-o2"]
    assert out["core.disclosure_form"]["observation_ids"] == ["o2"]
    assert out["core.content_data"]["source_ids"] == ["S-o1"]
    for entry in out.values():  # the D-007 named object shape storage validates
        assert set(entry) == {"value", "input_support_ids", "source_ids", "observation_ids", "combining_rule_ref"}
    assert ma.cx_display_rollup(_inst({"o1": _obs()}, {"S-o1": _cx_src()}), ["o1"]) == {}
    nodes = {"S-o1": {"values": _cx_src(**{"core.content_data": "yes"}),
                      "item_support": [{"item_id": "core.content_data", "support_id": "n1"},
                                       {"item_id": "core.page_verdict", "support_id": "n2"}]}}
    inst = SimpleNamespace(observation_inputs={"o1": rt.ObservationInput("o1", "S-o1", {"values": _obs()})},
                           sources=nodes)
    assert ma.cx_display_rollup(inst, ["o1"])["core.content_data"]["input_support_ids"] == ["n1"]
    src = _cx_src()
    src.pop("core.content_data")
    with pytest.raises(MissingUpstreamError):
        ma.cx_display_rollup(_inst({"o1": _obs()}, {"S-o1": src}), ["o1"])


# --- Stage 6 envelope -------------------------------------------------------------------------------


def _storage(run_dir):
    return json.loads((institution_dir(run_dir, qa.A) / "6_storage.json").read_text(encoding="utf-8"))


def test_merged_row_carries_the_a8_values(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    assert set(next(iter(a.merged_values.values()))) == rt.MERGE_INPUT_ITEMS  # stage_as_of etc. not given
    metrics = qa._run(run_dir, bound, instrument, [a], e.FakeQuotes())
    assert metrics.written == [qa.A], qa._held(run_dir) if metrics.held or metrics.failed else None
    merged = next(x for x in _storage(run_dir)["activities"].values() if x["observation_ids"] == ["o1", "o2"])
    order = e.s6.observation_pool_order(a.quotes, ["o1", "o2"])
    expect = ma.merged_values_a8(a, order)
    # declared fixture source rows: publication date 2025-01 (upper bound no), news_major, this_institution
    # codebook r16 (A8.5 a): the chosen date is a real publication date, so its step is publication
    assert {k: expect[k] for k in ma.PRODUCED if k != ma.CX_ROLLUP} == {
        "core.stage_as_of": "2025-01", "core.date_upper_bound": "no", "core.unit_credit": "no",
        "core.vendor_claim_only": "no", "core.stage_as_of_basis": "publication"}
    assert expect[ma.CX_ROLLUP]  # the fixture sources hold CX positives
    assert {k: merged["values"][k] for k in expect} == expect


def test_single_observation_row_carries_the_a8_values_ruling_78a(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    metrics = qa._run(run_dir, bound, instrument, [a], e.FakeQuotes())
    assert metrics.written == [qa.A], qa._held(run_dir) if metrics.held or metrics.failed else None
    single = [x for x in _storage(run_dir)["activities"].values() if len(x["observation_ids"]) == 1]
    assert single
    for row in single:
        expect = ma.merged_values_a8(a, row["observation_ids"])
        assert set(expect) == set(ma.PRODUCED)
        assert {k: row["values"][k] for k in expect} == expect


def test_merged_input_naming_a_produced_a8_item_is_refused(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    group = next(iter(a.merged_values))
    given = {**a.merged_values[group], "core.stage_as_of": "2020"}
    metrics = qa._run(run_dir, bound, instrument, [replace(a, merged_values={group: given})], e.FakeQuotes())
    assert metrics.failed == [qa.A] and "merged by rule or pooled" in qa._held(run_dir)["error"]


def test_merged_row_holds_when_a_source_lacks_an_a8_input(tmp_path):
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    sid = a.observation_inputs["o1"].source_id
    row = dict(a.sources[sid])
    row["values"] = {k: v for k, v in row["values"].items() if k != "core.source_publication_date"}
    metrics = qa._run(run_dir, bound, instrument, [replace(a, sources={**a.sources, sid: row})], e.FakeQuotes())
    assert metrics.failed == [qa.A] and "core.source_publication_date" in qa._held(run_dir)["error"]


def test_unruled_a8_value_holds_the_institution(tmp_path, monkeypatch):
    # UnruledMergeError is a PI question: the institution is held (ENVELOPE_FAILED), the stage continues.
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)

    def unruled(inst, order):
        raise ma.UnruledMergeError(ma.STAGE_AS_OF, "declared fixture")

    monkeypatch.setattr(ma, "merged_values_a8", unruled)
    metrics = qa._run(run_dir, bound, instrument, [a, b], e.FakeQuotes())
    assert qa.A in metrics.failed
    held = qa._held(run_dir)
    assert held["reasons"] == [rt.ENVELOPE_FAILED] and "UnruledMergeError" in held["error"]
    assert "PI question" in held["error"]


def test_malformed_a8_input_stops_the_stage(tmp_path):
    # Ruling 32 b (A8 review M1): a stored value outside its signed form is a wiring error, not a hold.
    run_dir, bound, instrument = e._setup(tmp_path)
    a, b = e._institutions(run_dir, bound, instrument)
    sid = a.observation_inputs["o1"].source_id
    row = {**a.sources[sid], "values": {**a.sources[sid]["values"], "core.source_publication_date": "March 2024"}}
    with pytest.raises(rt.UpstreamRowMalformed, match="core.source_publication_date") as info:
        qa._run(run_dir, bound, instrument, [replace(a, sources={**a.sources, sid: row}), b], e.FakeQuotes())
    assert info.value.institution_id == qa.A and isinstance(info.value.__cause__, ma.MalformedA8Value)
    assert "A8 inputs" in str(info.value)  # A8 review L1: caught by the pre-executor scan
    for inst_id in (qa.A, b.institution_id):  # before any call: no request journal for either institution
        assert not (institution_dir(run_dir, inst_id) / rt.WORK_DIR / rt.JOURNAL).exists()
    assert not (institution_dir(run_dir, qa.A) / rt.WORK_DIR / rt.HELD_FILE).exists()
    assert not (institution_dir(run_dir, qa.A) / "6_storage.json").exists()


def test_single_observation_fragment_value_disagreeing_with_a8_stops_the_stage(tmp_path):
    # A8 review L6: a stored fragment value (here T-015's unit_credit) is never silently overwritten.
    run_dir, bound, instrument = e._setup(tmp_path)
    a, _ = e._institutions(run_dir, bound, instrument)
    inp = a.observation_inputs["o3"]  # a single-observation activity (o3 governs o4: distinct)
    assert inp.row["values"]["core.unit_credit"] == "no"  # T-015's value: this_institution
    flipped = rt.ObservationInput("o3", inp.source_id,
                                  {**inp.row, "values": {**inp.row["values"], "core.unit_credit": "yes"}})
    bad = replace(a, observation_inputs={**a.observation_inputs, "o3": flipped})
    with pytest.raises(rt.UpstreamRowMalformed, match="core.unit_credit") as info:
        qa._run(run_dir, bound, instrument, [bad], e.FakeQuotes())
    assert isinstance(info.value.__cause__, ma.MalformedA8Value) and "disagrees" in str(info.value)
    assert not (institution_dir(run_dir, qa.A) / "6_storage.json").exists()
    values = {"core.unit_credit": "no"}
    rt._agree_with_fragment(values, {"core.unit_credit": "no", "core.stage_as_of": "2025"}, "o1")  # agrees/absent
    with pytest.raises(ma.MalformedA8Value):
        rt._agree_with_fragment(values, {"core.unit_credit": "yes"}, "o1")


@pytest.mark.parametrize("where,item,value", [
    ("source", "core.source_publication_date", "March 2024"),
    ("source", "core.source_access_date", "Nov 2026"),
    ("source", "core.date_upper_bound", "not_asked"),  # beside a real publication date
    ("source", "core.source_type", "blog"),
    ("obs", "core.year_pilot_start", "FY24"),
    ("obs", "core.observed_actor_relationship", "not_asked"),
    ("obs", "core.observed_actor_relationship", {"relationship": "subsidiary", "searched_institution_role": "unit"}),
])
def test_pre_executor_scan_stops_on_a_malformed_a8_input(where, item, value):
    obs, src = _obs(), _src(**{"core.source_publication_date": "2025"})
    (src if where == "source" else obs)[item] = value
    inst = _inst({"o1": obs}, {"S-o1": src})
    with pytest.raises(ma.MalformedA8Value):
        ma.check_a8_inputs(inst)
    inst.institution_id = "INST-X"
    with pytest.raises(rt.UpstreamRowMalformed, match="A8 inputs") as info:
        rt.require_a8_form(inst)
    assert isinstance(info.value.__cause__, ma.MalformedA8Value)


def test_pre_executor_scan_leaves_absent_a8_inputs_to_the_producers():
    # Absent inputs are holds (B1 a), decided in the envelope build; the scan passes them.
    obs, src = _obs(), _src()
    obs.pop("core.observed_actor_relationship")
    obs.pop("core.year_announced")
    src.pop("core.source_access_date")
    src.pop("core.source_type")
    ma.check_a8_inputs(_inst({"o1": obs}, {"S-o1": src}))
    ma.check_a8_inputs(_inst({"o1": _rel({"searched_institution_role": "unit"})},
                             {"S-o1": _src(**{"core.source_type": "not_documented"})}))
    ma.check_a8_inputs(_inst({"o1": _obs()}, {"S-o1": _src()}))  # well-formed rows pass
