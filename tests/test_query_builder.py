"""Tests for g3o.discovery.query_builder."""

from __future__ import annotations

from g3o.discovery.query_builder import (
    GENAI_TERMS_BY_LANG,
    PROPOSED_GENAI_TERMS_EN,
    build_queries,
)


def test_build_queries_one_per_term() -> None:
    queries = build_queries("City of Helsinki", ["en"])
    assert len(queries) == len(GENAI_TERMS_BY_LANG["en"])
    assert all(lang == "en" for _, lang in queries)
    assert all('"City of Helsinki"' in q for q, _ in queries)


def test_build_queries_unknown_language_falls_back_to_english() -> None:
    queries = build_queries("Test Institution", ["xx"])
    assert len(queries) == len(GENAI_TERMS_BY_LANG["en"])
    assert all(lang == "xx" for _, lang in queries)


def test_build_queries_extra_terms_appended_per_language() -> None:
    queries = build_queries("Test Institution", ["en", "fr"], extra_terms=["AI strategy"])
    en_queries = [q for q, lang in queries if lang == "en"]
    fr_queries = [q for q, lang in queries if lang == "fr"]
    assert len(en_queries) == len(GENAI_TERMS_BY_LANG["en"]) + 1
    assert len(fr_queries) == len(GENAI_TERMS_BY_LANG["fr"]) + 1
    assert any('"AI strategy"' in q for q in en_queries)


def test_proposed_english_terms_are_inert_by_default() -> None:
    """PROPOSED_GENAI_TERMS_EN (Batch 5) must stay out of GENAI_TERMS_BY_LANG
    until Simone signs off -- adding search terms changes what the pipeline
    collects (working-agreement escalation gate). This guards against
    accidentally wiring it in unreviewed."""
    assert GENAI_TERMS_BY_LANG["en"] == ["generative AI", "ChatGPT", "AI policy", "AI pilot"]


def test_proposed_english_terms_are_well_formed_superset() -> None:
    assert len(PROPOSED_GENAI_TERMS_EN) == len(set(PROPOSED_GENAI_TERMS_EN))  # no duplicates
    assert all(isinstance(t, str) and t.strip() for t in PROPOSED_GENAI_TERMS_EN)
    assert set(GENAI_TERMS_BY_LANG["en"]).issubset(set(PROPOSED_GENAI_TERMS_EN))


def test_proposed_english_terms_usable_with_build_queries() -> None:
    """Sanity-check the proposed roster is a drop-in-compatible term list
    (not wired live -- see test_proposed_english_terms_are_inert_by_default)."""
    queries = build_queries("Test Institution", ["en"], extra_terms=[])
    queries_with_proposed = [
        (f'"Test Institution" "{term}"', "en") for term in PROPOSED_GENAI_TERMS_EN
    ]
    assert len(queries_with_proposed) > len(queries)
