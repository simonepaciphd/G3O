"""Tests for g3o.common.page_chunks (T-020; R-044, R-045, C-004, A-021).

Fixture rules are configuration built in the test, except the codebook tests
at the end, which build every rule from the signed ``codebook/codebook.yaml``.
Where a fixture needs a value the SPEC does not fix (the negative page
verdicts, below), the test says so; it is test data, not a ruling.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from g3o.common import page_chunks as pc
from g3o.common.page_chunks import (
    NOT_COVERED,
    ItemRule,
    PartAnswer,
    PoolEntry,
    TokenEstimator,
    UnresolvedCombineCase,
)

REPO = Path(__file__).resolve().parents[1]
CODEBOOK = REPO / "codebook" / "codebook.yaml"

# Test-only stand-in: SPEC/codebook do not list the "negative page verdicts"
# that need no quote (R-041). Reported to the integrator; not a ruling.
TEST_NEGATIVE_VERDICTS = frozenset({"background_only", "confirms_absence", "no_genai"})


def A(part: int, value, p: float = 0.95, quote: str | None = "q", **kw) -> PartAnswer:
    return PartAnswer(f"pg#p{part:03d}", part, value, p, quote, **kw)


# ---------------------------------------------------------------------------
# Estimator
# ---------------------------------------------------------------------------


def test_estimator_constants_are_marked_placeholder():
    est = TokenEstimator()
    assert est.placeholder is True
    with pytest.raises(RuntimeError, match="PLACEHOLDER"):
        est.assert_calibrated()
    TokenEstimator(
        chars_per_token={"latin": 4.2, "cjk": 1.1, "thai": 2.2},
        safety_margin={"latin": 0.05, "cjk": 0.05, "thai": 0.05},
        placeholder=False,
    ).assert_calibrated()


def test_estimator_per_script_constants_and_additivity():
    est = TokenEstimator(chars_per_token={"latin": 4.0, "cjk": 1.0, "thai": 2.0})
    assert est.tokens("abcd" * 10) == 10
    assert est.tokens("政府" * 5) == 10
    assert est.tokens("ภาษาไทย!") == 4  # 7 Thai chars / 2 + 1 latin / 4
    a, b = "hello world ", "政府のAI"
    assert est.raw(a + b) == pytest.approx(est.raw(a) + est.raw(b))
    assert pc.script_of("a") == "latin" and pc.script_of("ж") == "latin"
    assert pc.script_of("한") == "cjk" and pc.script_of("ก") == "thai"


def test_safety_margin_inflates_the_estimate():
    base = TokenEstimator(chars_per_token={"latin": 4.0, "cjk": 1.0, "thai": 2.0})
    margin = TokenEstimator(
        chars_per_token={"latin": 4.0, "cjk": 1.0, "thai": 2.0},
        safety_margin={"latin": 0.5, "cjk": 0.0, "thai": 0.0},
    )
    assert base.tokens("a" * 40) == 10
    assert margin.tokens("a" * 40) == 15
    assert margin.tokens("政" * 10) == 10


def test_estimator_rejects_bad_constants():
    with pytest.raises(ValueError):
        TokenEstimator(chars_per_token={"latin": 0, "cjk": 1, "thai": 1})
    with pytest.raises(ValueError):
        TokenEstimator(safety_margin={"latin": -0.1})


# ---------------------------------------------------------------------------
# Page chunking
# ---------------------------------------------------------------------------

EST = TokenEstimator(chars_per_token={"latin": 1.0, "cjk": 1.0, "thai": 1.0})


def _page(n_paras: int = 6, para_len: int = 30) -> str:
    return "\n\n".join(" ".join(f"w{i}x{j}" for j in range(para_len // 5)) for i in range(n_paras))


def test_short_page_is_one_part_with_id():
    chunks = pc.chunk_page("pg", "short text", estimator=EST, limit_tokens=100)
    assert [c.chunk_id for c in chunks] == ["pg#p001"]
    assert chunks[0].start == 0 and chunks[0].end == 10


def test_chunks_fit_budget_are_lossless_and_ordered():
    text = _page(20, 60)
    chunks = pc.chunk_page("pg", text, estimator=EST, limit_tokens=150, overhead_tokens=30)
    assert len(chunks) > 1
    assert "".join(c.text for c in chunks) == text
    assert all(c.estimated_tokens <= 120 for c in chunks)
    assert [c.chunk_id for c in chunks] == [f"pg#p{i:03d}" for i in range(1, len(chunks) + 1)]
    for c in chunks:
        assert text[c.start : c.end] == c.text
    # Paragraph boundaries are preferred: every chunk but the last ends at one.
    assert all(c.text.endswith("\n\n") for c in chunks[:-1])


def test_chunking_is_deterministic():
    text = _page(15, 80) + "\n" + "政府" * 200
    a = pc.chunk_page("pg", text, estimator=EST, limit_tokens=90)
    b = pc.chunk_page("pg", text, estimator=EST, limit_tokens=90)
    assert a == b


def test_unbroken_text_falls_back_to_character_cuts():
    text = "x" * 250
    chunks = pc.chunk_page("pg", text, estimator=EST, limit_tokens=100)
    assert [len(c.text) for c in chunks] == [100, 100, 50]


def test_cjk_text_splits_on_sentence_marks():
    text = "政府はAIを導入した。" * 30
    chunks = pc.chunk_page("pg", text, estimator=EST, limit_tokens=50)
    assert "".join(c.text for c in chunks) == text
    assert all(c.text.endswith("。") for c in chunks)
    assert all(c.estimated_tokens <= 50 for c in chunks)


def test_no_budget_raises():
    with pytest.raises(ValueError):
        pc.chunk_page("pg", "abc", estimator=EST, limit_tokens=10, overhead_tokens=10)


# ---------------------------------------------------------------------------
# Halve-and-retry (DEC-008 c)
# ---------------------------------------------------------------------------


class OverLimit(Exception):
    pass


def test_over_limit_chunk_triggers_halve_and_retry():
    text = _page(8, 40)
    chunks = pc.chunk_page("pg", text, estimator=EST, limit_tokens=10_000)
    assert len(chunks) == 1
    real_limit = 90  # what "jev" really accepts: the estimate was too low

    def send(c):
        if len(c.text) > real_limit:
            raise OverLimit("max_tokens_exceeded")
        return c.chunk_id

    out = pc.run_with_halving(
        chunks,
        send,
        is_over_limit=lambda e: isinstance(e, OverLimit),
        halve=lambda c: pc.halve_chunk(c, estimator=EST),
    )
    parts = [c for c, _ in out.results]
    assert out.n_halvings >= 1
    assert "".join(c.text for c in parts) == text  # halves stay in page order
    assert all(len(c.text) <= real_limit for c in parts)
    assert parts[0].chunk_id.startswith("pg#p001.1")
    assert all(c.depth >= 1 for c in parts)


def test_halving_stops_at_max_depth():
    chunks = pc.chunk_page("pg", "y" * 64, estimator=EST, limit_tokens=1_000)

    def send(c):
        raise OverLimit()

    with pytest.raises(OverLimit):
        pc.run_with_halving(
            chunks,
            send,
            is_over_limit=lambda e: isinstance(e, OverLimit),
            halve=lambda c: pc.halve_chunk(c, estimator=EST),
            max_depth=3,
        )
    calls: list[int] = []

    def send2(c):
        calls.append(c.depth)
        raise OverLimit()

    with pytest.raises(OverLimit):
        pc.run_with_halving(
            chunks,
            send2,
            is_over_limit=lambda e: isinstance(e, OverLimit),
            halve=lambda c: pc.halve_chunk(c, estimator=EST),
            max_depth=2,
        )
    assert max(calls) == 2


def test_other_errors_are_not_retried():
    chunks = pc.chunk_page("pg", "abc def", estimator=EST, limit_tokens=100)

    def send(c):
        raise KeyError("boom")

    with pytest.raises(KeyError):
        pc.run_with_halving(
            chunks, send, is_over_limit=lambda e: isinstance(e, OverLimit), halve=pc.halve_chunk
        )


def test_halve_prefers_boundary_near_middle():
    c = pc.chunk_page("pg", "aaaa\n\nbbbb\n\ncccc dddd", estimator=EST, limit_tokens=100)[0]
    h1, h2 = pc.halve_chunk(c, estimator=EST)
    assert h1.text == "aaaa\n\nbbbb\n\n" and h2.text == "cccc dddd"
    assert (h1.end, h2.start) == (12, 12)
    assert pc.halve_chunk(pc.Chunk("x", "pg", 0, 1, "x", 1)) is None


# ---------------------------------------------------------------------------
# Pooled Stage 6 split (C-004, r2#6; reused by T-026)
# ---------------------------------------------------------------------------


def _entries():
    return [
        PoolEntry("e3", "c" * 30, "2024-05-01", 1),
        PoolEntry("e1", "a" * 30, "2023-01-01", 2),
        PoolEntry("e2", "b" * 30, "2023-01-01", 1),
        PoolEntry("e4", "d" * 30, "2025", 0),
    ]


def test_pool_split_orders_by_source_date_then_page_order():
    parts = pc.split_pool("inst", _entries(), estimator=EST, limit_tokens=60)
    assert [[e.entry_id for e in p.entries] for p in parts] == [["e2", "e1"], ["e3", "e4"]]
    assert [p.part_id for p in parts] == ["inst#p001", "inst#p002"]
    assert all(p.estimated_tokens <= 60 for p in parts)


def test_pool_split_pins_entries_into_every_part():
    pins = [PoolEntry("actA", "A" * 10, "2020", 0), PoolEntry("actB", "B" * 10, "2020", 0)]
    parts = pc.split_pool("pair", _entries(), estimator=EST, limit_tokens=80, pinned=pins)
    assert len(parts) == 2
    for p in parts:
        assert [e.entry_id for e in p.entries[:2]] == ["actA", "actB"]
        assert p.estimated_tokens <= 80
    h = pc.halve_pool_part(parts[0], n_pinned=2, estimator=EST)
    assert [[e.entry_id for e in x.entries] for x in h] == [
        ["actA", "actB", "e2"],
        ["actA", "actB", "e1"],
    ]


def test_pool_undated_entries_need_an_explicit_policy():
    es = [*_entries(), PoolEntry("e0", "z", None, 0)]
    with pytest.raises(ValueError, match="undated"):
        pc.split_pool("inst", es, estimator=EST, limit_tokens=1000)
    last = pc.split_pool("inst", es, estimator=EST, limit_tokens=1000, undated="last")
    assert last[0].entries[-1].entry_id == "e0"
    first = pc.split_pool("inst", es, estimator=EST, limit_tokens=1000, undated="first")
    assert first[0].entries[0].entry_id == "e0"


def test_pool_entry_too_large_raises():
    with pytest.raises(ValueError, match="does not fit"):
        pc.split_pool(
            "inst", [PoolEntry("big", "x" * 100, "2020", 0)], estimator=EST, limit_tokens=50
        )


# ---------------------------------------------------------------------------
# Check-then-combine (all-03 a; R-041; R-081)
# ---------------------------------------------------------------------------

YN = ItemRule(
    "core.function_code",
    pc.ANY_YES,
    values=frozenset({"yes", "no"}),
    no_support_values=frozenset({"no"}),
)


def test_check_supported_and_not_required():
    assert pc.check_part_answer(YN, A(1, "yes")).status == pc.SUPPORTED
    assert pc.check_part_answer(YN, A(1, "no", quote=None)).status == pc.NOT_REQUIRED
    assert pc.check_part_answer(YN, A(1, "not_documented", quote=None)).status == pc.NOT_REQUIRED


def test_check_failures_enter_as_unknown_with_ordered_reasons():
    c = pc.check_part_answer(YN, A(1, "yes", quote=None))
    assert (c.entered, c.status, c.second_reason, c.failed) == (
        "unknown",
        pc.DOWNGRADED_NO_QUOTE,
        None,
        True,
    )
    c = pc.check_part_answer(YN, A(1, "yes", p=0.5))
    assert (c.entered, c.status) == ("unknown", pc.DOWNGRADED_LOW_CONFIDENCE)
    c = pc.check_part_answer(YN, A(1, "yes", p=0.5, quote=None))
    assert (c.status, c.second_reason) == (pc.DOWNGRADED_NO_QUOTE, pc.DOWNGRADED_LOW_CONFIDENCE)
    c = pc.check_part_answer(YN, A(1, "yes", quote_not_stating_value=True))
    assert c.status == pc.DOWNGRADED_QUOTE_NOT_STATING_VALUE
    # R-081: negative codes face the bar too.
    c = pc.check_part_answer(YN, A(1, "no", p=0.6, quote=None))
    assert (c.entered, c.status) == ("unknown", pc.DOWNGRADED_LOW_CONFIDENCE)


def test_check_quote_must_occur_in_its_part():
    ok = pc.check_part_answer(YN, A(1, "yes", quote="uses ChatGPT"), part_text="We uses ChatGPT.")
    assert ok.status == pc.SUPPORTED
    bad = pc.check_part_answer(YN, A(1, "yes", quote="uses ChatGPT"), part_text="other part")
    assert bad.status == pc.DOWNGRADED_NO_QUOTE


def test_check_rejects_not_asked_na_and_unknown_codes():
    for v in ("not_asked", "_NA_", "maybe"):
        with pytest.raises(ValueError):
            pc.check_part_answer(YN, A(1, v))


def test_not_covered_does_not_vote():
    c = pc.check_part_answer(YN, A(1, NOT_COVERED, quote=None))
    assert not c.votes and c.entered == NOT_COVERED


# ---------------------------------------------------------------------------
# Temporary part answer "not covered by this part" (all-03 a, PI comment)
# ---------------------------------------------------------------------------


def test_all_parts_not_covered_gives_not_documented():
    out = pc.combine_item(YN, [A(1, NOT_COVERED, quote=None), A(2, NOT_COVERED, quote=None)])
    assert out.value == "not_documented" and out.part_id is None
    first = ItemRule("core.source_type", pc.FIRST_SECTION)
    assert pc.combine_item(first, [A(1, NOT_COVERED)]).value == "not_documented"
    lst = ItemRule("core.tool_name", pc.COMBINED_LIST)
    assert pc.combine_item(lst, [A(1, NOT_COVERED)]).value == "not_documented"


def test_not_covered_never_outvotes_a_real_or_missing_answer():
    out = pc.combine_item(YN, [A(1, NOT_COVERED, quote=None), A(2, "no", quote=None)])
    assert out.value == "no" and out.part_id == "pg#p002"
    out = pc.combine_item(YN, [A(1, NOT_COVERED, quote=None), A(2, "unknown", quote=None)])
    assert out.value == "unknown"  # not_covered is not not_documented


# ---------------------------------------------------------------------------
# One test per combining-rule type (RC-D-002 row 41)
# ---------------------------------------------------------------------------


def test_rule_any_yes_yes_no_item():
    out = pc.combine_item(YN, [A(1, "no", quote=None), A(2, "yes", p=0.85), A(3, "yes", p=0.9)])
    assert out.value == "yes" and out.part_id == "pg#p003"  # most sure (all-05 a)
    assert out.contributors == ("pg#p002", "pg#p003")
    out = pc.combine_item(YN, [A(1, "not_documented", quote=None), A(2, "no", quote=None)])
    assert out.value == "no"
    # A failed yes does not count; it enters as unknown, below no.
    out = pc.combine_item(YN, [A(1, "yes", quote=None), A(2, "no", quote=None)])
    assert out.value == "no"


def test_rule_priority_order_ordered_vocabulary():
    r = ItemRule(
        "core.evaluation_documented",
        pc.PRIORITY_ORDER,
        order=(
            "results_reported",
            "conducted_no_results",
            "required_or_planned",
            "unclear",
            "not_documented",
            "unknown",
        ),
        values=frozenset(
            {"results_reported", "conducted_no_results", "required_or_planned", "unclear"}
        ),
        no_support_values=frozenset(),
    )
    out = pc.combine_item(
        r, [A(1, "required_or_planned"), A(2, "conducted_no_results"), A(3, "unclear")]
    )
    assert out.value == "conducted_no_results" and out.part_id == "pg#p002"


def test_rule_first_section_page_field():
    r = ItemRule(
        "core.disclosure_form",
        pc.FIRST_SECTION,
        values=frozenset({"formal_record", "informal_official"}),
        no_support_values=frozenset(),
    )
    out = pc.combine_item(r, [A(1, "formal_record"), A(2, "informal_official")])
    assert out.value == "formal_record" and out.part_id == "pg#p001"


def test_rule_earliest_year():
    r = ItemRule("core.year_announced", pc.EARLIEST_YEAR, no_support_values=frozenset())
    out = pc.combine_item(r, [A(1, "2024"), A(2, 2022), A(3, "2023")])
    assert out.value == 2022 and out.part_id == "pg#p002"
    with pytest.raises(ValueError):
        pc.combine_item(r, [A(1, "last year")])
    out = pc.combine_item(r, [A(1, "not_documented", quote=None), A(2, "unknown", quote=None)])
    assert out.value == "not_documented"


def test_rule_highest_probability():
    r = ItemRule(
        "core.activity_type",
        pc.HIGHEST_PROBABILITY,
        values=frozenset({"policy_guidance", "pilot_experiment"}),
        no_support_values=frozenset(),
    )
    out = pc.combine_item(r, [A(1, "policy_guidance", p=0.85), A(2, "pilot_experiment", p=0.97)])
    assert out.value == "pilot_experiment" and out.probability == 0.97
    out = pc.combine_item(r, [A(1, "policy_guidance", p=0.9), A(2, "pilot_experiment", p=0.9)])
    assert out.value == "policy_guidance"  # tie: earliest part


def test_rule_combined_list():
    r = ItemRule("core.tool_name", pc.COMBINED_LIST, no_support_values=frozenset())
    out = pc.combine_item(
        r,
        [
            A(1, "ChatGPT", p=0.85, quote="q1"),
            A(1, "Copilot", quote="q2"),
            A(2, "ChatGPT", p=0.99, quote="q3"),
            A(3, "Gemini", quote=None),
        ],
    )
    assert out.value == ("ChatGPT", "Copilot")  # Gemini failed (no quote)
    chatgpt = out.elements[0]
    assert (chatgpt.part_id, chatgpt.quote, chatgpt.probability) == ("pg#p002", "q3", 0.99)


def test_rule_combined_list_multi_select_service_domain():
    r = ItemRule(
        "core.service_domain",
        pc.COMBINED_LIST,
        values=frozenset({"health", "education", "defence"}),
        no_support_values=frozenset(),
    )
    out = pc.combine_item(r, [A(1, "health", p=0.82), A(2, "education"), A(2, "health", p=0.9)])
    assert out.value == ("health", "education")
    assert [(e.value, e.part_id) for e in out.elements] == [
        ("health", "pg#p002"),
        ("education", "pg#p002"),
    ]
    out = pc.combine_item(r, [A(1, "not_documented", quote=None), A(2, "unknown", quote=None)])
    assert out.value == "not_documented"


def test_rule_same_part_as_observed_actor_role():
    rel = ItemRule(
        "core.observed_actor_relationship",
        pc.PRIORITY_ORDER,
        order=("this_institution", "unit_of_institution", "other"),
        no_support_values=frozenset(),
    )
    role = ItemRule(
        "core.observed_actor_role",
        pc.SAME_PART_AS,
        same_part_as="core.observed_actor_relationship",
        fallback=pc.HIGHEST_PROBABILITY,
        no_support_values=frozenset(),
    )
    rel_out = pc.combine_item(rel, [A(1, "other"), A(2, "this_institution")])
    assert rel_out.part_id == "pg#p002"
    out = pc.combine_item(
        role, [A(1, "issuer", p=0.99), A(2, "participant", p=0.85)], reference=rel_out
    )
    assert out.value == "participant" and out.part_id == "pg#p002"
    # Producing part has no real role: most-sure real role elsewhere (O6).
    out = pc.combine_item(
        role,
        [A(1, "issuer", p=0.9), A(2, NOT_COVERED), A(3, "participant", p=0.95)],
        reference=rel_out,
    )
    assert out.value == "participant" and out.part_id == "pg#p003"


# ---------------------------------------------------------------------------
# RC-D-003 additions: first part skipping, missing rank, most-sure quote,
# mapping steps, two-tier verdict order
# ---------------------------------------------------------------------------


def test_first_part_skips_silent_and_failed_parts():
    r = ItemRule(
        "core.source_type",
        pc.FIRST_SECTION,
        values=frozenset({"vendor", "academic"}),
        no_support_values=frozenset(),
    )
    out = pc.combine_item(
        r,
        [
            A(1, NOT_COVERED),
            A(2, "not_documented", quote=None),
            A(3, "vendor", quote=None),
            A(4, "academic", p=0.81),
            A(5, "vendor"),
        ],
    )
    assert out.value == "academic" and out.part_id == "pg#p004"


def test_missing_rank_real_then_not_documented_then_unknown():
    r = ItemRule(
        "core.interface",
        pc.PRIORITY_ORDER,
        order=("conversational", "backend_or_api"),
        no_support_values=frozenset(),
    )
    assert r.order == ("conversational", "backend_or_api", "not_documented", "unknown")
    out = pc.combine_item(r, [A(1, "unknown", quote=None), A(2, "not_documented", quote=None)])
    assert out.value == "not_documented"
    out = pc.combine_item(r, [A(1, "not_documented", quote=None), A(2, "backend_or_api")])
    assert out.value == "backend_or_api"
    # A failed real answer becomes unknown and ranks below not_documented.
    out = pc.combine_item(r, [A(1, "conversational", p=0.5), A(2, "not_documented", quote=None)])
    assert out.value == "not_documented"


def test_missing_rank_violations_are_spec_conflicts():
    with pytest.raises(pc.SpecConflict):
        pc.normalise_order("x", ("a", "not_documented", "b"))
    with pytest.raises(pc.SpecConflict):
        pc.normalise_order("x", ("a", "unknown", "not_documented"))
    with pytest.raises(pc.SpecConflict):
        pc.normalise_order("x", ("a", "not_asked"))


def test_most_sure_quote_ties_to_earliest():
    r = ItemRule(
        "core.interface",
        pc.PRIORITY_ORDER,
        order=("conversational",),
        no_support_values=frozenset(),
    )
    texts = {
        "pg#p001": "a chatbot here",
        "pg#p002": "the chatbot answers",
        "pg#p003": "chatbot again",
    }
    answers = [
        A(1, "conversational", p=0.9, quote="a chatbot"),
        A(2, "conversational", p=0.97, quote="the chatbot"),
        A(3, "conversational", p=0.97, quote="chatbot again"),
    ]
    out = pc.combine_item(r, answers, part_texts=texts)
    assert (out.part_id, out.quote, out.probability) == ("pg#p002", "the chatbot", 0.97)
    assert out.quote in texts[out.part_id]  # A-021: the quote occurs in the producing chunk


def test_mapping_step_governance_direction():
    r = ItemRule(
        "core.governance_direction",
        pc.PRIORITY_ORDER,
        order=("restricts_with_conditions", "prohibits", "permits", "requires", "promotes"),
        set_maps=((frozenset({"prohibits", "permits"}), "restricts_with_conditions"),),
        no_support_values=frozenset(),
    )
    out = pc.combine_item(r, [A(1, "permits"), A(2, "prohibits"), A(3, "promotes")])
    assert out.value == "restricts_with_conditions"
    assert out.mapped_from == ("prohibits", "permits") and out.part_id is None
    assert [e.part_id for e in out.elements] == ["pg#p002", "pg#p001"]
    out = pc.combine_item(r, [A(1, "permits"), A(2, "requires")])
    assert out.value == "permits"  # no mix: plain priority order
    out = pc.combine_item(r, [A(1, "permits"), A(2, "prohibits", p=0.4)])
    assert out.value == "permits"  # the failed ban does not enter the mapping
    out = pc.combine_item(
        r, [A(1, "restricts_with_conditions"), A(2, "prohibits"), A(3, "permits")]
    )
    assert out.part_id == "pg#p001"  # stated directly: that part produces it


@pytest.mark.parametrize(
    "answers,expected",
    [
        ([("internal_staff", 1), ("public", 2)], "both"),
        ([("internal_staff", 1), ("internal_staff", 2)], "internal_staff"),
        ([("both", 1), ("public", 2)], "both"),
        ([("not_documented", 1), ("unknown", 2)], "not_documented"),
        ([("unknown", 1), (NOT_COVERED, 2)], "unknown"),
        ([(NOT_COVERED, 1), (NOT_COVERED, 2)], "not_documented"),
        ([("public", 1), ("not_documented", 2)], "public"),
    ],
)
def test_mapping_step_audience_lists(answers, expected):
    r = ItemRule(
        "core.target_users",
        pc.COMBINED_LIST,
        values=frozenset({"internal_staff", "public", "both"}),
        pair_to_both=("internal_staff", "public", "both"),
        no_support_values=frozenset(),
    )
    q = {"internal_staff": "staff", "public": "public", "both": "all"}
    out = pc.combine_item(r, [A(p, v, quote=q.get(v)) for v, p in answers])
    assert out.value == expected


def test_two_tier_verdict_order_s3a():
    r = ItemRule(
        "core.page_verdict",
        pc.PRIORITY_ORDER,
        order=pc.S3A_VERDICT_ORDER,
        two_tier=True,
        downgrade_target=pc.DOWNGRADE_TAG_ONLY,
        values=frozenset(pc.S3A_VERDICT_ORDER),
        no_support_values=TEST_NEGATIVE_VERDICTS,
    )
    # S3 a: ambiguous_attribution outranks ambiguous_genai (unlike the value list).
    out = pc.combine_item(
        r, [A(1, "ambiguous_genai"), A(2, "ambiguous_attribution"), A(3, "no_genai", quote=None)]
    )
    assert out.value == "ambiguous_attribution"
    # Tier 2: a failed confirms_activity ranks below a supported no_genai ...
    out = pc.combine_item(r, [A(1, "confirms_activity", quote=None), A(2, "no_genai", quote=None)])
    assert out.value == "no_genai" and not out.failed
    # ... but the verdict is never rewritten: alone, it keeps its value plus the note.
    out = pc.combine_item(r, [A(1, "confirms_activity", p=0.6), A(2, "event_only", p=0.5)])
    assert (out.value, out.failed, out.status) == (
        "confirms_activity",
        True,
        pc.DOWNGRADED_LOW_CONFIDENCE,
    )
    # Not-covered parts do not vote.
    out = pc.combine_item(r, [A(1, NOT_COVERED, quote=None), A(2, "background_only", quote=None)])
    assert out.value == "background_only"


def test_verdict_all_not_covered_stops_the_field():
    r = ItemRule(
        "core.page_verdict",
        pc.PRIORITY_ORDER,
        order=pc.S3A_VERDICT_ORDER,
        two_tier=True,
        downgrade_target=pc.DOWNGRADE_TAG_ONLY,
        no_support_values=TEST_NEGATIVE_VERDICTS,
    )
    with pytest.raises(UnresolvedCombineCase, match="not a verdict value"):
        pc.combine_item(r, [A(1, NOT_COVERED), A(2, NOT_COVERED)])


def test_verdict_without_negative_list_stops_the_field():
    r = ItemRule(
        "core.page_verdict",
        pc.PRIORITY_ORDER,
        order=pc.S3A_VERDICT_ORDER,
        two_tier=True,
        downgrade_target=pc.DOWNGRADE_TAG_ONLY,
    )
    with pytest.raises(UnresolvedCombineCase, match="negative page verdicts"):
        pc.combine_item(r, [A(1, "no_genai")])


def test_combine_page_stops_one_field_and_continues():
    rules = {
        "core.function_code": YN,
        "core.page_verdict": ItemRule(
            "core.page_verdict",
            pc.PRIORITY_ORDER,
            order=pc.S3A_VERDICT_ORDER,
            two_tier=True,
            downgrade_target=pc.DOWNGRADE_TAG_ONLY,
        ),
        "core.observed_actor_relationship": ItemRule(
            "core.observed_actor_relationship",
            pc.PRIORITY_ORDER,
            order=("this_institution", "other"),
            no_support_values=frozenset(),
        ),
        "core.observed_actor_role": ItemRule(
            "core.observed_actor_role",
            pc.SAME_PART_AS,
            same_part_as="core.observed_actor_relationship",
            fallback=pc.HIGHEST_PROBABILITY,
            no_support_values=frozenset(),
        ),
    }
    answers = {
        "core.observed_actor_role": [A(1, "issuer"), A(2, "participant")],
        "core.function_code": [A(1, "yes")],
        "core.page_verdict": [A(1, "confirms_activity")],
        "core.observed_actor_relationship": [A(1, "other"), A(2, "this_institution")],
        "core.unruled": [A(1, "x")],
    }
    res = pc.combine_page(rules, answers)
    assert res.combined["core.function_code"].value == "yes"
    assert res.combined["core.observed_actor_role"].value == "participant"
    assert set(res.stopped) == {"core.page_verdict", "core.unruled"}


# ---------------------------------------------------------------------------
# Rules read from the signed codebook (interface for the T-013 loader)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def codebook_items():
    with CODEBOOK.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["items"]


def test_every_codebook_long_page_rule_builds_or_is_reported(codebook_items):
    built: dict[str, ItemRule] = {}
    unresolved: dict[str, str] = {}
    for item_id, item in codebook_items.items():
        try:
            rule = pc.rule_from_codebook_item(item_id, item)
        except UnresolvedCombineCase as exc:
            unresolved[item_id] = exc.reason
            continue
        if rule is not None:
            built[item_id] = rule
    # The one rule type outside the R-044 list (reported to the integrator).
    assert set(unresolved) == {"core.pooled_activity_fields"}
    assert {r.rule for r in built.values()} == pc.RULE_TYPES
    gaps = {i: r.order_gaps for i, r in built.items() if r.order_gaps}
    assert gaps == {"core.activity_relation_cross_page": ("governed_by", "has_component")}
    tu = built["core.target_users"]
    assert tu.pair_to_both == ("internal_staff", "public", "both")
    assert built["core.governed_population"].pair_to_both == (
        "internal_personnel",
        "external_users",
        "both",
    )
    gd = built["core.governance_direction"]
    assert gd.set_maps == ((frozenset({"prohibits", "permits"}), "restricts_with_conditions"),)
    assert built["core.content_data"].order == ("yes", "no", "not_documented", "unknown")
    assert built["core.function_code"].order == ("yes", "no", "not_documented", "unknown")
    pv = built["core.page_verdict"]
    assert pv.two_tier and pv.order == pc.S3A_VERDICT_ORDER and pv.no_support_values is None
    role = built["core.observed_actor_role"]
    assert role.same_part_as == "core.observed_actor_relationship"


def test_s3a_constant_matches_codebook_text(codebook_items):
    text = codebook_items["core.page_verdict"]["long_page_rule"]["text"]["text"]
    listed = text.split("The S3 a order is:")[1].split("(")[0]
    assert tuple(v.strip(" .") for v in listed.split(",")) == pc.S3A_VERDICT_ORDER


def test_not_covered_constant_matches_codebook():
    with CODEBOOK.open(encoding="utf-8") as fh:
        conv = yaml.safe_load(fh)["combining_conventions"]
    assert conv["not_covered_by_this_part"]["temporary_value"] == NOT_COVERED
    assert conv["missing_rank"]["order"][1:] == list(pc.MISSING_RANK)
