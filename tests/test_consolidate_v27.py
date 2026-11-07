"""Local T-026 reduction tests, not a replacement for the pending runtime e2e.

The small records below deliberately mock upstream evidence. No fixture values
are exposed as runtime defaults or claimed to be actual provider results.
"""
from dataclasses import replace

import pytest

from g3o.classify.jev_activity_code import ItemOutcome
from g3o.classify.questions.v27 import load_set
from g3o.common.storage import validate_value
from g3o.validate.consolidate_v27 import (
    VERDICTS,
    ActivityObservation,
    ConsolidationError,
    RelationDecision,
    ReviewedPage,
    SupportingQuote,
    activity_confidence,
    outcome_values,
    pool_plan,
    relation_plan,
    summary_values,
)


def page(key="p", verdict="no_genai", **changes):
    original = ReviewedPage(key, "web_extract", verdict, .9, "not_required", True,
                            False, False, (key + "-s",), ({"fixture": "coder"},),
                            ({"fixture": "support"},))
    return replace(original, **changes)


def observation(key="a", page_id="p", **changes):
    outcome = ItemOutcome("core.action_type", "core.action_type", None, "combined", "deployment")
    original = ActivityObservation(key, page_id, {outcome.question_id: outcome},
                                   {"core.activity_name": "Same name"}, True,
                                   ({"fixture": "coder"},), ({"fixture": "support"},))
    return replace(original, **changes)


def relation(lhs, rhs, value="same_activity", **changes):
    original = RelationDecision(lhs, rhs, value, .9, "supported", ({"fixture": "coder"},),
                                (lhs + ":" + rhs,), "cross_page")
    return replace(original, **changes)


def activity_values(**changes):
    result = {"core.action_type": "deployment", "core.adoption_stage": "production",
              "core.procurement_status": "none_documented", "core.activity_type": "internal_operational"}
    result.update(changes)
    return result


@pytest.mark.parametrize("verdict", ["no_genai", "confirms_absence", "background_only", "event_only", "other_body"])
def test_supported_web_negatives_give_no(verdict):
    values = summary_values([page(verdict=verdict)], [], published_activity_values=[])
    assert values["core.has_genai_activity"] == "no"
    assert values["core.evidence_tier"] == "none_found"
    depth = values["core.review_depth"]["web_extract"]
    assert depth["n_pages_by_verdict"][verdict] == 1
    assert set(depth["n_pages_by_verdict"]) == set(VERDICTS)


@pytest.mark.parametrize("signal", [
    page("signal", "ambiguous_genai"), page("signal", "ambiguous_attribution"),
    page("signal", chosen_probability=.799),
    page("signal", support_status="downgraded_no_quote"),
    page("signal", "not_assessable", reviewed=False, failed=True, failure_reason="fetch_failed"),
    page("signal", "not_assessable", reviewed=False, failure_reason="unfollowed_link"),
])
def test_open_signals_block_no(signal):
    values = summary_values([page(), signal], [], published_activity_values=[])
    assert values["core.has_genai_activity"] == "unclear"


def test_mechanical_not_assessable_does_not_block_no_but_is_not_negative_evidence():
    unreadable = page("unreadable", "not_assessable", chosen_probability=None, support_status="set_by_rule")
    assert summary_values([page(), unreadable], [], published_activity_values=[])["core.has_genai_activity"] == "no"
    assert summary_values([unreadable], [], published_activity_values=[])["core.has_genai_activity"] == "unclear"


def test_no_requires_web_evidence_and_ai_text_does_not_change_verdict():
    procurement = page(pipeline="procurement")
    ai = page("ai", "ambiguous_genai", pipeline="ai_text")
    assert summary_values([procurement], [], published_activity_values=[])["core.has_genai_activity"] == "unclear"
    assert summary_values([page(), ai], [], published_activity_values=[])["core.has_genai_activity"] == "no"


def test_supported_purchase_positive_has_commitment_tier():
    purchase = page(verdict="confirms_activity", pipeline="procurement", support_status="supported")
    values = activity_values(**{"core.adoption_stage": "unknown", "core.procurement_status": "payment_or_subscription"})
    result = summary_values([purchase], [observation()], published_activity_values=[values])
    assert result["core.has_genai_activity"] == "yes"
    assert result["core.evidence_tier"] == "documented_commitment"


def test_ai_text_positive_cannot_establish_yes():
    ai = page(verdict="confirms_activity", pipeline="ai_text", support_status="supported")
    result = summary_values([ai], [observation()], published_activity_values=[])
    assert result["core.has_genai_activity"] == "unclear"
    with pytest.raises(ConsolidationError, match="presence"):
        summary_values([ai], [observation()], published_activity_values=[activity_values()])


@pytest.mark.parametrize("kwargs, tier", [
    ({}, "documented_use"),
    ({"core.action_type": "staff_training", "core.adoption_stage": "unknown"}, "governance_or_training_only"),
    ({"core.adoption_stage": "proposed"}, "proposal_only"),
])
def test_tiers_use_final_activity_codes(kwargs, tier):
    positive = page(verdict="confirms_activity", support_status="supported")
    result = summary_values([positive], [observation()], published_activity_values=[activity_values(**kwargs)])
    assert result["core.evidence_tier"] == tier


def test_summary_uses_actual_release_label_and_only_x33_facts():
    positive = page(verdict="confirms_activity", support_status="supported")
    result = summary_values([positive], [observation()], published_activity_values=[activity_values()])
    assert result["core.verdict_rule"] == load_set("institution")["codebook_release"] == "2.7"
    validate_value("core.verdict_rule", result["core.verdict_rule"])
    validate_value("core.evidence_tier", result["core.evidence_tier"])
    assert result["core.institution_summary"] == (
        "GenAI activity: yes. Activities: 1. Types: internal_operational. "
        "Stages: production. Pages reviewed: 1; failed: 0.")


@pytest.mark.parametrize("action", ["training", "proposal"])
def test_tier_refuses_action_names_absent_from_signed_enum(action):
    positive = page(verdict="confirms_activity", support_status="supported")
    with pytest.raises(ConsolidationError, match="unsigned value"):
        summary_values([positive], [observation()], published_activity_values=[
            activity_values(**{"core.action_type": action})])


def test_identical_names_always_need_explicit_relation():
    observations = [observation("a", "p1"), observation("b", "p2")]
    pages = [page("p1"), page("p2")]
    result = relation_plan(observations, pages, [])
    assert result.groups == (("a",), ("b",))
    assert result.missing_pairs == (("a", "b"),)
    assert not result.ready
    supported = relation_plan(observations, pages, [relation("a", "b")])
    assert supported.groups == (("a", "b"),)
    assert supported.ready


@pytest.mark.parametrize("decision", [
    relation("a", "b", "unresolved"), relation("a", "b", "distinct_action"),
    relation("a", "b", "component_of_program"), relation("a", "b", "governs"),
    relation("a", "b", chosen_probability=.79),
    relation("a", "b", support_status="downgraded_no_quote", support_ids=()),
])
def test_unsupported_or_nonmerge_relations_preserved_without_merging(decision):
    result = relation_plan([observation("a", "p1"), observation("b", "p2")],
                           [page("p1"), page("p2")], [decision])
    assert result.groups == (("a",), ("b",))
    assert result.relations == (decision,)


def test_transitive_merge_cannot_erase_distinct_or_unresolved_relation():
    obs = [observation(key, "p" + key) for key in "abc"]
    pages = [page("p" + key) for key in "abc"]
    result = relation_plan(obs, pages, [relation("a", "b"), relation("b", "c"),
                                        relation("a", "c", "distinct_action")])
    assert result.groups == (("a",), ("b",), ("c",))
    assert result.conflicting_groups == (("a", "b", "c"),)
    assert not result.ready


def test_pool_orders_real_support_and_omits_missing_date_and_nonconfirmed_evidence():
    pages = [page("p1", "confirms_activity", support_status="supported"),
             page("p2", "confirms_activity", support_status="supported"), page("p3", "other_body")]
    obs = [observation(key, "p" + str(i)) for i, key in enumerate("abc", 1)]
    quotes = [SupportingQuote("a", "s1", "first source quote", "c1", "an official government source",
                              "2026-02-01", "2026-02-01", "https://example.gov/1", 0, 0),
              SupportingQuote("b", "s2", "second source quote", "c2", "a news report",
                              None, "2026-01-01", "https://example.org/2", 1, 0),
              SupportingQuote("c", "s3", "not eligible", "c3", "a news report",
                              None, "2020-01-01", "https://example.org/3", 2, 0)]
    result = pool_plan(tuple("abc"), obs, pages, quotes)
    assert result.observation_ids == ("a", "b")
    assert [q.support_id for q in result.quotes] == ["s2", "s1"]
    assert "source_publication_date" not in result.state["supporting_quotes"][0]
    assert result.state["supporting_quotes"][1]["source_publication_date"] == "2026-02-01"
    assert result.state["pool_note"].startswith("The text below is a set of quotes")
    assert result.question_set_version == "g3o.classify.questions.v27.jev.1"


def test_refuse_missing_provenance_unfinished_outcomes_and_duplicate_pages():
    with pytest.raises(ConsolidationError, match="provenance"):
        summary_values([page(raw_records=())], [], published_activity_values=[])
    with pytest.raises(ConsolidationError, match="duplicate actual page"):
        summary_values([page(), page()], [], published_activity_values=[])
    pending = ItemOutcome("q", "core.action_type", None, "pending", None)
    with pytest.raises(ConsolidationError, match="unfinished"):
        outcome_values({"q": pending})
    with pytest.raises(ConsolidationError, match="no actual support"):
        pool_plan(["a"], [observation()], [page(verdict="confirms_activity", support_status="supported")], [])


def test_confidence_uses_genuine_source_values_and_independence_groups():
    assert activity_confidence({"a": "medium", "b": "medium"}, {"a": "one", "b": "two"}) == "high"
    assert activity_confidence({"a": "medium", "b": "medium"}, {"a": "one", "b": "one"}) == "medium"
    assert activity_confidence({"a": "high", "b": "low"}, {"a": "one", "b": "two"}) == "high"
    with pytest.raises(ConsolidationError, match="unruled"):
        activity_confidence({"a": "unknown"}, {"a": "one"})
    with pytest.raises(ConsolidationError, match="independence"):
        activity_confidence({"a": "medium"}, {})
