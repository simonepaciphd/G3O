"""A8 producers of a merged activity's derived values (PI A8 rulings 2026-11-11, ruling 66 a).

Unit tests drive :mod:`g3o.validate.merged_activity_v27` with declared observation
and source rows; the envelope tests run the mocked Stage 6 path of
``tests/test_e2e_stage6_v27.py`` (no network, every provider answer a fake).
"""
from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from g3o.common.paths import institution_dir
from g3o.common.storage_fields import FIELDS
from g3o.persist.stage6_adapters import MissingUpstreamError
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
    base = {"core.source_publication_date": "not_documented", "core.source_access_date": "2026-11-01",
            "core.date_upper_bound": "not_asked", "core.source_type": "news_major",
            "core.source_on_official_domain": "not_official", "core.source_url": "https://news.example.com/a"}
    return {**base, **over}


def _inst(obs, srcs, source_of=None):
    """``obs``: oid -> activity row values; ``srcs``: sid -> source row values; ``source_of``: oid -> sid."""
    source_of = source_of or {k: f"S-{k}" for k in obs}
    inputs = {k: rt.ObservationInput(k, source_of[k], {"values": v}) for k, v in obs.items()}
    return SimpleNamespace(observation_inputs=inputs, sources={s: {"values": v} for s, v in srcs.items()})


# --- module split ---------------------------------------------------------------------------------


def test_a8_split_produced_and_refused_items():
    assert set(rt.MERGE_PRODUCED_A8) == {"core.stage_as_of", "core.date_upper_bound", "core.unit_credit",
                                         "core.vendor_claim_only"}
    # A8.1 a / A8.5 a need codebook r16; A8.10 a awaits the PI's approval of the positive table.
    assert set(rt.MERGE_REFUSED_R1) == {"core.developer", "core.developer_basis", "core.stage_as_of_basis",
                                        "core.cx_display_rollup"}
    assert not set(rt.MERGE_PRODUCED_A8) & rt.MERGE_INPUT_ITEMS
    assert rt._non_pooled_items() == (rt.MERGE_INPUT_ITEMS | set(rt.MERGE_UNION) | set(rt.MERGE_CREDIBLE)
                                      | set(rt.MERGE_DERIVED) | set(rt.MERGE_PRODUCED_A8))


# --- stage_as_of (A8.3 a, A8.4 a, A8.6 a) -----------------------------------------------------------


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
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2024"}), "S-o2": _src()})
    date, chosen = ma.merged_stage_as_of(inst, ["o1", "o2"])
    assert date == "2026-11-01" and [c.observation_id for c in chosen] == ["o2"]


def test_merged_stage_as_of_refuses_an_undetermined_latest():
    inst = _inst({"o1": _obs(), "o2": _obs(**{"core.year_announced": "2024"})},
                 {"S-o1": _src(**{"core.source_publication_date": "2024-03-12"}), "S-o2": _src()})
    with pytest.raises(ma.UnruledMergeError, match="not determined"):
        ma.merged_stage_as_of(inst, ["o1", "o2"])
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2024-03"}),
                  "S-o2": _src(**{"core.source_publication_date": "2024-03-01"})})
    with pytest.raises(ma.UnruledMergeError):
        ma.merged_stage_as_of(inst, ["o1", "o2"])


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


def test_stage_as_of_refuses_a_missing_access_date_and_malformed_values():
    inst = _inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_access_date": "not_documented"})})
    with pytest.raises(MissingUpstreamError):
        ma.observation_stage_as_of(inst, "o1")
    inst = _inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_publication_date": "March 2024"})})
    with pytest.raises(ValueError, match="neither a date"):
        ma.observation_stage_as_of(inst, "o1")
    inst = _inst({"o1": _obs(**{"core.year_announced": "FY24"})}, {"S-o1": _src()})
    with pytest.raises(ValueError, match="neither a year code"):
        ma.observation_stage_as_of(inst, "o1")
    inst = _inst({"o1": _obs()}, {})
    with pytest.raises(MissingUpstreamError):
        ma.observation_stage_as_of(inst, "o1")


# --- date_upper_bound (A8.11 a, A8.12 a) ------------------------------------------------------------


def test_date_upper_bound_follows_stage_as_of():
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2025-06", "core.date_upper_bound": "no"}),
                  "S-o2": _src(**{"core.source_publication_date": "2024", "core.date_upper_bound": "yes"})})
    assert ma.merged_values_a8(inst, ["o1", "o2"])["core.date_upper_bound"] == "no"
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2023", "core.date_upper_bound": "no"}),
                  "S-o2": _src(**{"core.source_publication_date": "2024", "core.date_upper_bound": "yes"})})
    assert ma.merged_values_a8(inst, ["o1", "o2"])["core.date_upper_bound"] == "yes"
    # a year code or an access date has no archive origin: no
    inst = _inst({"o1": _obs(**{"core.year_announced": "2025"})}, {"S-o1": _src()})
    assert ma.merged_values_a8(inst, ["o1"])["core.date_upper_bound"] == "no"


def test_date_upper_bound_refuses_a_token_beside_a_real_date_and_disagreeing_ties():
    inst = _inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_publication_date": "2025"})})  # bound not_asked
    with pytest.raises(ValueError, match="is not yes/no"):
        ma.merged_values_a8(inst, ["o1"])
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _src(**{"core.source_publication_date": "2025", "core.date_upper_bound": "yes"}),
                  "S-o2": _src(**{"core.source_publication_date": "2025", "core.date_upper_bound": "no"})})
    with pytest.raises(ma.UnruledMergeError, match="disagree"):
        ma.merged_values_a8(inst, ["o1", "o2"])


# --- unit_credit (A8.7 a, A8.8 a, 66 a) -------------------------------------------------------------


def _rel(value):
    return _obs(**{"core.observed_actor_relationship": value})


@pytest.mark.parametrize("value,expect", [
    ({"relationship": "unit_of_institution", "searched_institution_role": "unit"}, "yes"),
    ({"relationship": "this_institution", "searched_institution_role": "contracting_authority"}, "no"),
    ({"relationship": "unresolved", "searched_institution_role": "not_asked"}, "no"),
    ({"relationship": "unknown", "searched_institution_role": "not_asked"}, "no"),  # 66 a: read literally
    ("not_asked", "no"),
])
def test_unit_credit_reads_the_relationship_literally(value, expect):
    inst = _inst({"o1": _rel(value)}, {"S-o1": _src()})
    assert ma.observation_unit_credit(inst, "o1") == expect


def test_merged_unit_credit_is_yes_if_any_pooled_observation_is():
    unit = {"relationship": "unit_of_institution", "searched_institution_role": "unit"}
    inst = _inst({"o1": _obs(), "o2": _rel(unit)}, {"S-o1": _src(), "S-o2": _src()})
    assert ma.merged_unit_credit(inst, ["o1", "o2"]) == "yes"
    assert ma.merged_unit_credit(inst, ["o1"]) == "no"


def test_unit_credit_refuses_an_absent_relationship():
    inst = _inst({"o1": _rel({"searched_institution_role": "unit"})}, {"S-o1": _src()})
    with pytest.raises(MissingUpstreamError):
        ma.observation_unit_credit(inst, "o1")
    obs = _obs()
    obs.pop("core.observed_actor_relationship")
    with pytest.raises(MissingUpstreamError):
        ma.observation_unit_credit(_inst({"o1": obs}, {"S-o1": _src()}), "o1")


# --- vendor_claim_only (A8.9 a) ---------------------------------------------------------------------


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


def test_vendor_claim_only_automatic_type_is_a_type_unreadable_not_asked_is_missing():
    official = _src(**{"core.source_type": "not_asked", "core.source_on_official_domain": "own_official",
                       "core.source_url": "https://www.council.example.gov/ai"})
    archive = _src(**{"core.source_type": "not_asked",
                      "core.source_url": "https://web.archive.org/web/2024/https://vendor.example.com/"})
    unreadable = _src(**{"core.source_type": "not_asked"})
    vendor = _src(**{"core.source_type": "vendor"})
    assert ma.source_type_of(_inst({"o1": _obs()}, {"S-o1": official}), "S-o1") == "official_domain"
    assert ma.source_type_of(_inst({"o1": _obs()}, {"S-o1": archive}), "S-o1") == "archive_address"
    assert ma.source_type_of(_inst({"o1": _obs()}, {"S-o1": unreadable}), "S-o1") is None
    for other, expect in ((official, "no"), (archive, "no"), (unreadable, "unknown")):
        inst = _inst({"o1": _obs(), "o2": _obs()}, {"S-o1": vendor, "S-o2": other})
        assert ma.merged_vendor_claim_only(inst, ["o1", "o2"]) == expect


def test_vendor_claim_only_counts_a_shared_source_once_and_refuses_absent_or_malformed_type():
    inst = _inst({"o1": _obs(), "o2": _obs()}, {"S1": _src(**{"core.source_type": "vendor"})},
                 source_of={"o1": "S1", "o2": "S1"})
    assert ma.supporting_sources(inst, ["o2", "o1"]) == ["S1"]
    assert ma.merged_vendor_claim_only(inst, ["o1", "o2"]) == "yes"
    src = _src()
    src.pop("core.source_type")
    with pytest.raises(MissingUpstreamError):
        ma.merged_vendor_claim_only(_inst({"o1": _obs()}, {"S-o1": src}), ["o1"])
    with pytest.raises(ValueError, match="not a signed code"):
        ma.merged_vendor_claim_only(_inst({"o1": _obs()}, {"S-o1": _src(**{"core.source_type": "blog"})}), ["o1"])
    unreadable = _src(**{"core.source_type": "not_asked"})
    unreadable.pop("core.source_url")
    with pytest.raises(MissingUpstreamError):
        ma.merged_vendor_claim_only(_inst({"o1": _obs()}, {"S-o1": unreadable}), ["o1"])


# --- cx_display_rollup (A8.10 a): mechanism only, refused until the PI approves the table -----------


def _cx_src(**over):
    values = {item: ("no" if kind == ma.CX_YES else [] if kind == ma.CX_NON_EMPTY else "not_documented")
              for item, (kind, _) in ma.CX_POSITIVE.items()}
    return {**_src(), **values, **over}


def test_cx_table_covers_every_cx_item_stored_per_source_claim():
    from g3o.common.storage import table_fields
    sources = table_fields("sources")
    cx = {i for i in sources if i.startswith(("core.content_", "core.disclosure_", "core.evaluation_"))}
    assert set(ma.CX_POSITIVE) == cx
    for item, (kind, codes) in ma.CX_POSITIVE.items():
        if kind == ma.CX_CODES:
            assert [c for c in FIELDS[item]["codes"] if c in codes] == list(codes)
    assert "unclear" not in ma.CX_POSITIVE["core.evaluation_documented"][1]


def test_cx_rollup_is_refused_until_the_table_is_approved():
    assert ma.CX_POSITIVE_APPROVED is False and "core.cx_display_rollup" in rt.MERGE_REFUSED_R1
    inst = _inst({"o1": _obs()}, {"S-o1": _cx_src()})
    with pytest.raises(ma.UnruledMergeError, match="not approved"):
        ma.cx_display_rollup(inst, ["o1"])


def test_cx_rollup_mechanism_any_positive_first_in_table_order():
    inst = _inst({"o1": _obs(), "o2": _obs()},
                 {"S-o1": _cx_src(**{"core.content_data": "yes", "core.disclosure_form": "formal_record",
                                     "core.evaluation_documented": "unclear"}),
                  "S-o2": _cx_src(**{"core.disclosure_form": "mandated_report",
                                     "core.content_contact_emails": ["a@example.gov"],
                                     "core.evaluation_documented": "required_or_planned"})})
    out = ma._cx_rollup(inst, ["o1", "o2"])
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
    assert ma._cx_rollup(_inst({"o1": _obs()}, {"S-o1": _cx_src()}), ["o1"]) == {}
    nodes = {"S-o1": {"values": _cx_src(**{"core.content_data": "yes"}),
                      "item_support": [{"item_id": "core.content_data", "support_id": "n1"},
                                       {"item_id": "core.page_verdict", "support_id": "n2"}]}}
    inst = SimpleNamespace(observation_inputs={"o1": rt.ObservationInput("o1", "S-o1", {"values": _obs()})},
                           sources=nodes)
    assert ma._cx_rollup(inst, ["o1"])["core.content_data"]["input_support_ids"] == ["n1"]
    src = _cx_src()
    src.pop("core.content_data")
    with pytest.raises(MissingUpstreamError):
        ma._cx_rollup(_inst({"o1": _obs()}, {"S-o1": src}), ["o1"])


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
    # declared fixture source rows: publication date 2025-01 (upper bound yes), news_major, this_institution
    assert expect == {"core.stage_as_of": "2025-01", "core.date_upper_bound": "yes", "core.unit_credit": "no",
                      "core.vendor_claim_only": "no"}
    assert {k: merged["values"][k] for k in expect} == expect


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
