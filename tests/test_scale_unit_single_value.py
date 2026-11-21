"""``core.deployment_scale_unit``: a combined-list answer reaches storage as its single lexical value.

Distilled from calibration unit cal-0301 (journal-only replay at the frozen setting, deployed acdc792): the
per-page stage combined the unit over the page's one part by its signed long-page rule (``combined_list``,
ruling activity-24 b), which yields a tuple (``("users",)``); :func:`consolidate_v27.outcome_values` put that
tuple on the activity row, and Stage 6 storage refused it (``core.deployment_scale_unit requires its lexical
text value``: the D-007 field is ``single``, an enum string). The institution was held although the page and
activity were supported. The same projection serves the pooled Stage 6 answer (``pooled_values``).

Expectations come from the signed contract, not from the code: the item's answer type is ``single`` with an
enum schema (``storage_fields.FIELDS``), and its long-page rule is ``combined_list`` of (number, unit) pairs.
"""
from __future__ import annotations

import pytest

from g3o.classify.jev_activity_code import ItemOutcome
from g3o.codebook.loader import load_codebook
from g3o.common import part_combine as pc
from g3o.common.storage import validate_value
from g3o.common.storage_fields import FIELDS
from g3o.validate.consolidate_v27 import outcome_values

UNIT = "core.deployment_scale_unit"


@pytest.fixture(scope="module")
def rules():
    return pc.rules_from_codebook(load_codebook())


def _combined(rules, *answers):
    parts = [pc.PartAnswer(f"page#p{i:03d}", i, v, 1.0) for i, v in enumerate(answers, start=1)]
    return pc.combine(rules[UNIT], parts)


def _project(value):
    return outcome_values({UNIT: ItemOutcome(UNIT, UNIT, None, "combined", value)})[UNIT]


def test_signed_contract_unit_is_single_enum_combined_by_list(rules):
    assert FIELDS[UNIT]["answer_type"] == "single"
    assert "enum" in FIELDS[UNIT]["schema"] and "users" in FIELDS[UNIT]["codes"]
    assert rules[UNIT].rule == pc.COMBINED_LIST


def test_one_part_unit_projects_to_its_lexical_value(rules):
    combined = _combined(rules, "users")
    assert combined.value == ("users",)  # what the combiner returns (the cal-0301 page: one part)
    value = _project(combined.value)
    validate_value(UNIT, value)  # raised "requires its lexical text value" before the fix
    assert value == "users"


def test_json_round_tripped_one_value_list_projects_too():
    # activity.json stores the tuple as a JSON list; a resumed run reloads it as a list
    value = _project(["users"])
    validate_value(UNIT, value)
    assert value == "users"


def test_same_unit_from_two_parts_is_one_value(rules):
    combined = _combined(rules, "users", "users")
    assert combined.value == ("users",)
    assert _project(combined.value) == "users"


def test_different_units_are_not_collapsed_and_storage_still_refuses(rules):
    # Several distinct units (the activity-24 b list) have no single-value form in D-007: not ruled.
    # The projection does not pick one; storage refuses as before (the institution is held).
    combined = _combined(rules, "users", "licences_or_seats")
    value = _project(combined.value)
    assert list(value) == ["users", "licences_or_seats"]
    with pytest.raises(ValueError, match="lexical text value"):
        validate_value(UNIT, value)


def test_missing_fallback_and_multi_items_are_unchanged(rules):
    assert _project("not_documented") == "not_documented"
    multi = "core.service_domain"
    assert FIELDS[multi]["answer_type"] == "multi"
    one = outcome_values({multi: ItemOutcome(multi, multi, None, "combined", ["health"])})[multi]
    assert one == ["health"]  # a one-member multi-select stays a list
