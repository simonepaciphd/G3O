"""Tests for g3o.common.part_combine (R-044 long-page combination; PI 2026-11-08 Q1 b)."""

from __future__ import annotations

import pytest

from g3o.codebook.loader import load_codebook
from g3o.common.part_combine import (
    NOT_COVERED,
    RULE_TYPES,
    CombineError,
    ItemRule,
    PartAnswer,
    combine,
    rule_from_item,
    rules_from_codebook,
)


@pytest.fixture(scope="module")
def rules():
    return rules_from_codebook(load_codebook())


def pa(i, value, p=0.9, failed=False, **kw):
    return PartAnswer(part_id=f"pg#p{i:03d}", part_index=i, value=value, probability=p, failed=failed, **kw)


# -- configuration from the signed codebook ---------------------------------------------


def test_every_codebook_rule_parses_and_covers_all_types(rules):
    assert {r.rule for r in rules.values()} == RULE_TYPES
    assert len(rules) == 59


def test_page_item_rules_read_from_codebook(rules):
    v = rules["core.page_verdict"]
    assert v.rule == "priority_order" and v.two_tier and v.all_not_covered == "not_assessable"
    assert v.order[:3] == ("confirms_activity", "ambiguous_attribution", "ambiguous_genai")
    assert v.order[-1] == "not_assessable" and "unknown" not in v.order
    assert rules["core.disclosure_form"].rule == "first_section"
    assert rules["core.disclosure_scope"].rule == "first_section"
    assert rules["core.page_complete"].rule == "any_yes"
    assert rules["core.content_data"].order == ("yes", "no", "not_documented", "unknown")


def test_missing_rank_appended_in_order(rules):
    # signed order lists only `unknown`; not_documented must still rank above it (all-04 b)
    assert rules["core.activity_relation_cross_page"].order[-2:] == ("not_documented", "unknown")


def test_order_with_missing_before_real_refused():
    with pytest.raises(CombineError):
        ItemRule("x", "priority_order", order=("a", "not_documented", "b"))
    with pytest.raises(CombineError):
        ItemRule("x", "priority_order", order=("a", "unknown", "not_documented"))
    with pytest.raises(CombineError):
        ItemRule("x", "priority_order", order=("a", "not_asked"))


def test_unknown_rule_key_and_type_refused():
    with pytest.raises(CombineError):
        rule_from_item("x", {"long_page_rule": {"rule": "first_section", "surprise": 1}})
    with pytest.raises(CombineError):
        rule_from_item("x", {"long_page_rule": "majority"})
    assert rule_from_item("x", {"long_page_rule": "none"}) is None
    assert rule_from_item("x", {}) is None


def test_order_must_place_every_value():
    with pytest.raises(CombineError):
        rule_from_item("x", {"long_page_rule": {"rule": "priority_order", "order": ["a"]}}, codes=["a", "b"])


# -- conventions ----------------------------------------------------------------------


def test_not_covered_never_votes(rules):
    r = rules["core.page_complete"]
    out = combine(r, [pa(1, NOT_COVERED, 0.99), pa(2, "no", 0.85)])
    assert out.value == "no" and out.part_id == "pg#p002"


def test_all_not_covered_gives_not_documented_or_verdict_override(rules):
    out = combine(rules["core.disclosure_form"], [pa(1, NOT_COVERED), pa(2, NOT_COVERED)])
    assert out.value == "not_documented" and out.part_id is None
    out = combine(rules["core.page_verdict"], [pa(1, NOT_COVERED), pa(2, NOT_COVERED)])
    assert out.value == "not_assessable"


def test_failed_enters_as_unknown(rules):
    r = rules["core.page_complete"]
    out = combine(r, [pa(1, "yes", 0.5, failed=True), pa(2, "no", 0.9)])
    assert out.value == "no"
    out = combine(r, [pa(1, "yes", 0.5, failed=True)])
    assert out.value == "unknown" and out.failed


def test_missing_rank_not_documented_beats_unknown(rules):
    r = rules["core.disclosure_form"]
    out = combine(r, [pa(1, "yes_x", 0.5, failed=True), pa(2, "not_documented", 0.9)])
    assert out.value == "not_documented"


def test_not_asked_refused(rules):
    with pytest.raises(ValueError):
        combine(rules["core.page_complete"], [pa(1, "not_asked")])
    with pytest.raises(ValueError):
        combine(rules["core.page_complete"], [pa(1, "_NA_")])


def test_value_outside_item_refused(rules):
    with pytest.raises(CombineError):
        combine(rules["core.page_complete"], [pa(1, "maybe")])


def test_one_answer_per_part_except_lists(rules):
    with pytest.raises(ValueError):
        combine(rules["core.page_complete"], [pa(1, "yes"), pa(1, "no")])


def test_producing_part_most_sure_then_earliest(rules):
    r = rules["core.page_complete"]
    out = combine(r, [pa(1, "yes", 0.85), pa(2, "yes", 0.95), pa(3, "yes", 0.95)])
    assert out.part_id == "pg#p002" and out.probability == 0.95
    assert out.contributors == ("pg#p001", "pg#p002", "pg#p003")
    out = combine(r, [pa(1, "yes", None), pa(2, "yes", 0.81)])
    assert out.part_id == "pg#p002"


def test_ref_carried(rules):
    out = combine(rules["core.page_complete"], [pa(1, "yes", ref=7)])
    assert out.ref == 7


# -- rule types -----------------------------------------------------------------------


def test_priority_two_tiers(rules):
    r = rules["core.page_verdict"]
    # a failed confirms_activity ranks after a supported background_only (page-02 b)
    out = combine(r, [pa(1, "confirms_activity", 0.6, failed=True), pa(2, "background_only", 0.9)])
    assert out.value == "background_only" and not out.failed
    # all failed: same order in the failed tier, tag kept
    out = combine(r, [pa(1, "no_genai", 0.5, failed=True, cause="below_threshold"),
                      pa(2, "ambiguous_genai", 0.6, failed=True)])
    assert out.value == "ambiguous_genai" and out.failed
    out = combine(r, [pa(1, "no_genai", 0.9), pa(2, "confirms_activity", 0.85)])
    assert out.value == "confirms_activity"


def test_any_yes(rules):
    r = rules["core.content_contact_named"]
    assert combine(r, [pa(1, "no"), pa(2, "yes", 0.81)]).value == "yes"
    assert combine(r, [pa(1, "no"), pa(2, "no")]).value == "no"
    r = rules["core.content_data"]
    assert combine(r, [pa(1, "not_documented"), pa(2, "no")]).value == "no"


def test_first_section_skips_silent_and_failed(rules):
    r = rules["core.disclosure_form"]
    out = combine(r, [pa(1, NOT_COVERED), pa(2, "formal_record", 0.5, failed=True),
                      pa(3, "mandated_report", 0.85), pa(4, "third_party", 0.99)])
    assert out.value == "mandated_report" and out.part_id == "pg#p003"


def test_earliest_year(rules):
    r = rules["core.year_announced"]
    out = combine(r, [pa(1, "2021"), pa(2, "2019", 0.82), pa(3, "2020")])
    assert out.value == "2019" and out.part_id == "pg#p002"
    with pytest.raises(CombineError):
        combine(r, [pa(1, "19")])
    assert combine(r, [pa(1, "not_documented")]).value == "not_documented"


def test_highest_probability(rules):
    r = rules["core.activity_type"]
    values = sorted(r.values)
    out = combine(r, [pa(1, values[0], 0.81), pa(2, values[1], 0.97)])
    assert out.value == values[1]


def test_highest_probability_same_part_first_step(rules):
    rel = rules["core.observed_actor_relationship"]
    role = rules["core.observed_actor_role"]
    ref = combine(rel, [pa(1, "joint_participant", 0.9), pa(2, "this_institution", 0.85)])
    assert ref.part_id == "pg#p002"
    out = combine(role, [pa(1, "issuer", 0.99), pa(2, "participant", 0.82)], reference=ref)
    assert out.value == "participant" and out.part_id == "pg#p002"
    # producing part gives no real role: most-sure real role from the others
    out = combine(role, [pa(1, "issuer", 0.99), pa(2, "not_documented", 0.9)], reference=ref)
    assert out.value == "issuer"
    with pytest.raises(CombineError):
        combine(role, [pa(1, "issuer")])


def test_combined_list_several_values_per_part(rules):
    r = rules["core.service_domain"]
    out = combine(r, [pa(1, "health", 0.85), pa(1, "education", 0.9), pa(2, "health", 0.95),
                      pa(3, "defence", 0.4, failed=True)])
    assert out.value == ("health", "education")
    assert [(e.value, e.part_id) for e in out.elements] == [("health", "pg#p002"), ("education", "pg#p001")]
    assert combine(r, [pa(1, "defence", 0.4, failed=True)]).value == "unknown"


def test_combined_list_pairs_as_tuples():
    r = ItemRule("core.deployment_scale_number", "combined_list")
    out = combine(r, [pa(1, ["12", "staff"]), pa(2, ["12", "staff"]), pa(2, ["3", "sites"])])
    assert out.value == (("12", "staff"), ("3", "sites"))


def test_combined_list_mapping_step(rules):
    r = rules["core.target_users"]
    assert combine(r, [pa(1, "internal_staff"), pa(2, "public")]).value == "both"
    assert combine(r, [pa(1, "internal_staff"), pa(2, "both", 0.82)]).value == "both"
    assert combine(r, [pa(1, "public"), pa(2, NOT_COVERED)]).value == "public"
    assert combine(r, [pa(1, "not_documented"), pa(2, "unknown")]).value == "not_documented"
    assert combine(r, [pa(1, NOT_COVERED)]).value == "not_documented"
    m = combine(rules["core.governed_population"], [pa(1, "internal_personnel"), pa(2, "external_users")])
    assert m.value == "both" and m.mapped_from == ("internal_personnel", "external_users") and m.part_id is None


def test_priority_mapping_step(rules):
    r = rules["core.governance_direction"]
    out = combine(r, [pa(1, "prohibits", 0.9), pa(2, "permits", 0.95)])
    assert out.value == "restricts_with_conditions" and out.mapped_from == ("prohibits", "permits")
    assert [e.part_id for e in out.elements] == ["pg#p001", "pg#p002"]
    # a failed permission does not trigger the mapping
    out = combine(r, [pa(1, "prohibits", 0.9), pa(2, "permits", 0.5, failed=True)])
    assert out.value == "prohibits"
    # a direct answer wins by the order
    out = combine(r, [pa(1, "restricts_with_conditions", 0.9), pa(2, "permits")])
    assert out.value == "restricts_with_conditions" and out.part_id == "pg#p001"


def test_single_part_passes_through(rules):
    out = combine(rules["core.page_verdict"], [pa(1, "no_genai", 0.7, failed=True)])
    assert out.value == "no_genai" and out.failed
