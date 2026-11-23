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


# RC-D-029 Q1 a / RC-D-027 1 a, 2 a, O2 b: the v2.7 yes/no/unclear consistency lives here (V3 a).
def test_no_needs_a_negative_verdict_not_assessable_alone_is_unclear():
    unreadable = page("u", "not_assessable", chosen_probability=None, support_status="set_by_rule")
    assert summary_values([unreadable, replace(unreadable, page_id="u2")], [],
                          published_activity_values=[])["core.has_genai_activity"] == "unclear"


@pytest.mark.parametrize("status", ["downgraded_no_quote", "downgraded_low_confidence",
                                    "downgraded_quote_not_stating_value"])
def test_downgraded_confirms_activity_alone_gives_unclear(status):
    down = page("d", "confirms_activity", support_status=status)
    assert summary_values([page(), down], [observation(page_id="d", supported=False)],
                          published_activity_values=[])["core.has_genai_activity"] == "unclear"


@pytest.mark.parametrize("status", ["supported", "not_required", "set_by_rule"])
def test_undowngraded_confirms_activity_off_yes_is_refused(status):
    # supported but below the 0.8 probability bar, with a supported observation
    confirmed = page("c", "confirms_activity", chosen_probability=.5, support_status=status)
    with pytest.raises(ConsolidationError, match="did not fail their support check"):
        summary_values([page(), confirmed], [observation(page_id="c")], published_activity_values=[])


@pytest.mark.parametrize("status", ["supported", "not_required", "set_by_rule"])
def test_confirms_activity_with_no_supported_observation_is_unclear(status):
    # PI R4 a (2026-11-18): a confirming page that passed its check, none of whose observations is
    # supported (Y1), sits on an unclear institution (was refused under RC-D-027 2 a)
    confirmed = page("c", "confirms_activity", support_status=status)
    result = summary_values([page(), confirmed], [observation(page_id="c", supported=False)],
                            published_activity_values=[])
    assert result["core.has_genai_activity"] == "unclear"


def test_yes_with_supported_plus_downgraded_confirms_activity():
    supported = page("s", "confirms_activity", support_status="supported")
    down = page("d", "confirms_activity", support_status="downgraded_no_quote")
    result = summary_values([supported, down], [observation(page_id="s"), observation("b", "d", supported=False)],
                            published_activity_values=[activity_values()])
    assert result["core.has_genai_activity"] == "yes"


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


def test_links_not_followed_are_unreviewed_but_not_failed_115b():
    """PI ruling 115 b: an unread follow page whose link was not followed (cap or hop limit) is reviewed=False,
    failed=False with its reason (a valid page here); only fetch failures and robots refusals count in
    ``n_pages_failed`` and the summary's "failed: N". Every unread page still keeps the verdict off "no"."""
    def unread(key, reason, failed, followed):
        return page(key, verdict="not_assessable", support_status="set_by_rule", chosen_probability=None,
                    reviewed=False, failed=failed, followed=followed, failure_reason=reason)
    pages = [page("p"), unread("f", "fetch_failed", True, True), unread("r", "robots_disallowed", True, True),
             unread("c", "link_not_followed_cap", False, False), unread("h", "link_not_followed_hops", False, False)]
    result = summary_values(pages, [], published_activity_values=[])
    depth = result["core.review_depth"]["web_extract"]
    assert (depth["n_pages_reviewed"], depth["n_pages_failed"], depth["n_followed_links"]) == (1, 2, 2)
    assert result["core.institution_summary"].endswith("Pages reviewed: 1; failed: 2.")
    assert result["core.has_genai_activity"] == "unclear"
    with pytest.raises(ConsolidationError, match="attempted/unfollowed reason"):
        summary_values([unread("c", None, False, False)], [], published_activity_values=[])


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
        activity_confidence({"a": "certain"}, {"a": "one"})
    with pytest.raises(ConsolidationError, match="independence"):
        activity_confidence({"a": "medium"}, {})


def test_unknown_source_confidence_counts_as_low_in_aggregation():
    # codebook r15 items/core.confidence/rules/2 (RC-D-025 C8 b)
    assert activity_confidence({"a": "unknown"}, {"a": "one"}) == "low"
    assert activity_confidence({"a": "unknown", "b": "medium"}, {"a": "one", "b": "two"}) == "medium"
    # an unknown source counts as low, so it is never the second agreeing medium
    assert activity_confidence({"a": "unknown", "b": "medium", "c": "unknown"},
                               {"a": "one", "b": "two", "c": "three"}) == "medium"
    assert activity_confidence({"a": "unknown", "b": "high"}, {"a": "one", "b": "two"}) == "high"


def test_unfinished_source_confidence_is_refused():
    with pytest.raises(ConsolidationError, match="unfinished"):
        activity_confidence({"a": "unfinished"}, {"a": "one"})


# ---------------------------------------------------------------------------
# Page-verdict roll-up (RC-D-049; PI rulings 2026-11-22, R1 b and R3 to R6)
# ---------------------------------------------------------------------------

ROLLUP_STATUSES = ["downgraded_quote_not_stating_value", "downgraded_no_quote"]


def failed_verdict(status="downgraded_no_quote", **changes):
    """A confirms_activity page whose verdict failed its own support check on the quote."""
    return page("r", "confirms_activity", support_status=status, **changes)


@pytest.mark.parametrize("status", ROLLUP_STATUSES)
def test_rollup_applies_to_a_quote_failure_with_a_supported_observation(status):
    from g3o.validate import consolidate_v27 as cv

    assert cv.ROLLUP_STATUSES == frozenset(ROLLUP_STATUSES)
    assert cv.rollup_applies(failed_verdict(status), [observation(page_id="r")]) is True


@pytest.mark.parametrize("candidate, observations, why", [
    (failed_verdict("downgraded_low_confidence"), [observation(page_id="r")], "the classifier bar is never rescued"),
    (failed_verdict(chosen_probability=.799), [observation(page_id="r")], "under the classifier verdict bar"),
    (failed_verdict(chosen_probability=None), [observation(page_id="r")], "no probability"),
    (failed_verdict(), [observation(page_id="r", supported=False)], "no supported observation"),
    (failed_verdict(), [], "no observation"),
    (failed_verdict(), [observation(page_id="other")], "the supported observation is on another page"),
    (failed_verdict("supported"), [observation(page_id="r")], "the verdict is already supported"),
    (failed_verdict("set_by_rule"), [observation(page_id="r")], "a rule-set verdict"),
    (failed_verdict("not_required"), [observation(page_id="r")], "no check was required"),
    (failed_verdict(failed=True, failure_reason="page_failed"), [observation(page_id="r")], "a failed page"),
    (failed_verdict(reviewed=False, failure_reason="unfollowed_link"), [observation(page_id="r")],
     "an unreviewed page"),
    (failed_verdict(pipeline="ai_text"), [observation(page_id="r")], "AI-text evidence never counts"),
    (failed_verdict(pipeline="procurement"), [observation(page_id="r")],
     "a procurement page is not a web page (PI ruling 2026-11-22)"),
    *[(replace(failed_verdict(), page_verdict=v), [observation(page_id="r")], f"verdict {v}")
      for v in sorted(set(VERDICTS) - {"confirms_activity"})],
])
def test_rollup_does_not_apply(candidate, observations, why):
    from g3o.validate.consolidate_v27 import rollup_applies

    assert rollup_applies(candidate, observations) is False, why


def test_rollup_reads_the_bar_in_force_not_a_value_of_its_own(monkeypatch):
    """R4: the classifier verdict bar is the one the institution rule uses (no setting value in the rule)."""
    from g3o.validate import consolidate_v27 as cv

    low = failed_verdict(chosen_probability=.72)
    assert cv.rollup_applies(low, [observation(page_id="r")]) is False
    monkeypatch.setattr(cv, "_probability", lambda value: value is not None and value >= .7)
    assert cv.rollup_applies(low, [observation(page_id="r")]) is True


@pytest.mark.parametrize("status", ROLLUP_STATUSES)
def test_rolled_up_page_keeps_its_failed_status_and_gives_yes(status):
    """R1 b: the verdict keeps its failed support status; the rescue is the separate ``verdict_rollup`` mark.
    R5: the page counts for the institution outcome and its supported observations are pooled."""
    from g3o.validate import consolidate_v27 as cv
    from g3o.validate.stage6_v27 import pool_eligible

    down, obs = failed_verdict(status), [observation(page_id="r")]
    assert down.verdict_rollup is False
    assert cv._positive(down) is False and pool_eligible(["a"], obs, [down]) == ()
    assert summary_values([down], [], published_activity_values=[])["core.has_genai_activity"] == "unclear"
    rescued = replace(down, verdict_rollup=True)
    assert rescued.support_status == status and replace(rescued, verdict_rollup=False) == down
    assert cv._positive(rescued) is True and pool_eligible(["a"], obs, [rescued]) == ("a",)
    result = summary_values([rescued], obs, published_activity_values=[activity_values()])
    assert result["core.has_genai_activity"] == "yes"
    assert result["core.review_depth"]["web_extract"]["n_pages_by_verdict"]["confirms_activity"] == 1
    with pytest.raises(ConsolidationError, match="presence"):
        summary_values([rescued], obs, published_activity_values=[])


def test_rolled_up_page_pools_its_supported_observations_only():
    rescued = replace(failed_verdict(), verdict_rollup=True)
    obs = [observation("a", "r"), observation("b", "r", supported=False)]
    quotes = [SupportingQuote("a", "s1", "the quote", "c1", "an official government source", None, "2025",
                              "https://example.gov/r", 0, 0)]
    assert pool_plan(["a", "b"], obs, [rescued], quotes).observation_ids == ("a",)
    assert pool_plan(["a", "b"], obs, [replace(rescued, verdict_rollup=False)], []).observation_ids == ()


@pytest.mark.parametrize("bad, why", [
    (failed_verdict("downgraded_low_confidence"), "low confidence is never rescued"),
    (failed_verdict("supported"), "an already supported verdict is not a rescue"),
    (failed_verdict("set_by_rule"), "a rule-set verdict is not a rescue"),
    (failed_verdict(chosen_probability=.5), "under the bar"),
    (replace(failed_verdict(), page_verdict="ambiguous_genai"), "not a confirming verdict"),
    (failed_verdict(pipeline="ai_text"), "AI-text"),
    (failed_verdict(pipeline="procurement"), "a procurement page is not a web page"),
    (failed_verdict(failed=True, failure_reason="page_failed"), "failed page"),
    (failed_verdict(reviewed=False, failure_reason="unfollowed_link"), "unreviewed page"),
])
def test_roll_up_mark_on_a_page_the_rule_does_not_cover_is_refused(bad, why):
    with pytest.raises(ConsolidationError, match="roll-up"):
        summary_values([page(), replace(bad, verdict_rollup=True)], [observation(page_id="r")],
                       published_activity_values=[activity_values()])


def test_roll_up_mark_without_a_supported_observation_on_the_page_is_refused():
    rescued = replace(failed_verdict(), verdict_rollup=True)
    for obs in ([], [observation(page_id="r", supported=False)]):
        with pytest.raises(ConsolidationError, match="roll-up"):
            summary_values([page(), rescued], obs, published_activity_values=[])
    other = page("s", "confirms_activity", support_status="supported")
    with pytest.raises(ConsolidationError, match="roll-up"):
        summary_values([other, rescued], [observation(page_id="s")], published_activity_values=[activity_values()])


def test_rollup_covers_web_pages_only():
    """PI ruling 2026-11-22: the roll-up names the web page. A procurement page that meets every other
    condition is never rescued and stays out of the positive set; the same page from the web is rescued."""
    from g3o.validate import consolidate_v27 as cv

    obs = [observation(page_id="r")]
    web, purchase = failed_verdict(), failed_verdict(pipeline="procurement")
    assert web.pipeline == "web_extract" and replace(purchase, pipeline="web_extract") == web
    assert cv.rollup_applies(web, obs) is True
    assert cv.rollup_applies(purchase, obs) is False
    assert summary_values([purchase], [], published_activity_values=[])["core.has_genai_activity"] == "unclear"
    assert {p for p in cv.CHANNELS if cv.rollup_applies(replace(web, pipeline=p), obs)} == {"web_extract"}
