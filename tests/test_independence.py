"""Tests for source independence groups (PI A7.1 b, A7.2 a, 2026-11-11).

Copies = same syndication group or same normalised URL (same_url_key), transitive
closure; a source without a syndication group is refused. No network.
"""

from __future__ import annotations

import pytest

from g3o.common import independence as ind
from g3o.common.source_fields import MissingUpstreamError
from g3o.validate.consolidate_v27 import activity_confidence

INST = "inst-1"


def test_syndication_match_is_one_group():
    g = ind.independence_groups({"S1": ("sg-a", "https://a.gov/x"), "S2": ("sg-a", "https://b.gov/y")},
                                institution_id=INST)
    assert g["S1"] == g["S2"]


def test_normalised_url_match_is_one_group():
    # same_url_key: case of scheme/host, leading www., trailing slash, fragment
    g = ind.independence_groups({"S1": ("sg-a", "HTTPS://WWW.A.gov/x/#top"), "S2": ("sg-b", "https://a.gov/x")},
                                institution_id=INST)
    assert g["S1"] == g["S2"]


def test_query_string_is_kept_by_the_url_key():
    g = ind.independence_groups({"S1": ("sg-a", "https://a.gov/x?id=1"), "S2": ("sg-b", "https://a.gov/x?id=2")},
                                institution_id=INST)
    assert g["S1"] != g["S2"]


def test_transitive_closure():
    g = ind.independence_groups({"S1": ("sg-a", "https://a.gov/1"), "S2": ("sg-a", "https://a.gov/2"),
                                 "S3": ("sg-c", "https://a.gov/2/"), "S4": ("sg-d", "https://a.gov/4")},
                                institution_id=INST)
    assert g["S1"] == g["S2"] == g["S3"] != g["S4"]
    assert g["S1"] == ind.group_id(INST, ["S1", "S2", "S3"])


def test_distinct_sources_are_independent():
    g = ind.independence_groups({"S1": ("sg-a", "https://a.gov/1"), "S2": ("sg-b", "https://a.gov/2")},
                                institution_id=INST)
    assert g["S1"] != g["S2"]
    assert g == {"S1": ind.group_id(INST, ["S1"]), "S2": ind.group_id(INST, ["S2"])}


@pytest.mark.parametrize("group", [None, "", "  ", "not_documented", "unknown", "_NA_"])
def test_missing_syndication_group_is_refused(group):
    with pytest.raises(MissingUpstreamError) as exc:
        ind.independence_groups({"S1": (group, "https://a.gov/1"), "S2": ("sg-b", "https://a.gov/2")},
                                institution_id=INST)
    assert exc.value.missing == ("S1.core.syndication_group",)


def test_no_url_only_fallback_even_when_urls_match():
    with pytest.raises(MissingUpstreamError):
        ind.independence_groups({"S1": (None, "https://a.gov/1"), "S2": ("sg-b", "https://a.gov/1")},
                                institution_id=INST)


def test_missing_url_is_refused():
    with pytest.raises(MissingUpstreamError) as exc:
        ind.independence_groups({"S1": ("sg-a", None)},
                                institution_id=INST)
    assert exc.value.missing == ("S1.core.source_url",)


def test_determinism_and_resume_stability():
    keys = {"S3": ("sg-c", "https://a.gov/2/"), "S1": ("sg-a", "https://a.gov/1"),
            "S2": ("sg-a", "https://a.gov/2"), "S4": ("sg-d", "https://a.gov/4")}
    first = ind.independence_groups(keys, institution_id=INST)
    again = ind.independence_groups(dict(reversed(list(keys.items()))), institution_id=INST)
    assert first == again
    assert all(v.startswith(ind.GROUP_ID_PREFIX) and len(v) == 3 + 20 for v in first.values())
    assert ind.group_id(INST, ["S2", "S1"]) == ind.group_id(INST, ["S1", "S2"])
    assert ind.INDEPENDENCE_VERSION == "g3o.common.independence.v2"


def test_from_source_rows_and_consumer():
    rows = {"S1": {"values": {"core.syndication_group": "sg-a", "core.source_url": "https://a.gov/1"}},
            "S2": {"values": {"core.syndication_group": "sg-a", "core.source_url": "https://b.gov/1"}},
            "S3": {"values": {"core.syndication_group": "sg-c", "core.source_url": "https://c.gov/1"}}}
    g = ind.independence_groups_for_sources(rows, institution_id=INST)
    # two medium copies stay medium; a medium from an independent source makes it high
    assert activity_confidence({"S1": "medium", "S2": "medium"}, {s: g[s] for s in ("S1", "S2")}) == "medium"
    assert activity_confidence({"S1": "medium", "S3": "medium"}, {s: g[s] for s in ("S1", "S3")}) == "high"


def test_institution_id_is_part_of_the_group_id():
    """PI ruling A7 27 (2026-11-12): ig- ids hash the institution id, as A4's sg- ids do."""
    keys = {"S1": ("sg-a", "https://a.gov/1"), "S2": ("sg-a", "https://a.gov/2"), "S3": ("sg-c", "https://c.gov/3")}
    one = ind.independence_groups(keys, institution_id="inst-1")
    two = ind.independence_groups(keys, institution_id="inst-2")
    assert set(one.values()).isdisjoint(two.values())
    assert ind.independence_groups(dict(keys), institution_id="inst-1") == one
    assert ind.group_id("inst-1", ["S1"]) != ind.group_id("inst-2", ["S1"])
    assert ind.group_id("inst-1", ["S1"]) == ind.group_id("inst-1", ["S1"])


@pytest.mark.parametrize("bad", ["", "   ", None, 7])
def test_blank_institution_id_is_refused(bad):
    with pytest.raises(ValueError, match="institution_id"):
        ind.independence_groups({"S1": ("sg-a", "https://a.gov/1")}, institution_id=bad)
    with pytest.raises(ValueError, match="institution_id"):
        ind.group_id(bad, ["S1"])
