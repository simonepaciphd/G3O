"""Tests for g3o.discovery.query_builder."""

from __future__ import annotations

from g3o.discovery.query_builder import GENAI_TERMS_BY_LANG, build_queries


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


def test_english_roster_is_the_promoted_expansion() -> None:
    """The Batch-5 term expansion was PI-promoted 2026-07-04. This pins the
    live English roster so any future change to what discovery collects is a
    deliberate, reviewed edit (working-agreement escalation gate), not drift."""
    assert GENAI_TERMS_BY_LANG["en"] == [
        "generative AI",
        "ChatGPT",
        "AI policy",
        "AI pilot",
        "Copilot",
        "AI chatbot",
        "AI assistant",
        "large language model",
    ]


def test_roster_terms_are_well_formed() -> None:
    for lang, terms in GENAI_TERMS_BY_LANG.items():
        assert len(terms) == len(set(terms)), lang  # no duplicates
        assert all(isinstance(t, str) and t.strip() for t in terms), lang


def test_build_queries_includes_country_when_given() -> None:
    queries = build_queries("House of Representatives", ["en"], country="Belize")
    assert len(queries) == len(GENAI_TERMS_BY_LANG["en"])
    assert all('"House of Representatives"' in q for q, _ in queries)
    assert all('"Belize"' in q for q, _ in queries)


def test_build_queries_omits_country_when_not_given() -> None:
    """No country (default None, or the empty string a CSV row yields) must
    reproduce the original two-term query — no regression for institutions
    with no known jurisdiction."""
    no_country = build_queries("City of Helsinki", ["en"])
    empty_country = build_queries("City of Helsinki", ["en"], country="")
    assert no_country == empty_country
    for q, _ in no_country:
        assert q.count('"') == 4  # exactly two quoted phrases: name + term
