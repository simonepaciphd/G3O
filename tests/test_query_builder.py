"""Tests for g3o.discovery.query_builder."""

from __future__ import annotations

import pytest

from g3o.discovery.query_builder import (
    GENAI_TERMS_BY_LANG,
    UnknownLanguageError,
    build_queries,
)


def test_build_queries_one_per_term() -> None:
    queries = build_queries("City of Helsinki", ["en"])
    assert len(queries) == len(GENAI_TERMS_BY_LANG["en"])
    assert all(lang == "en" for _, lang in queries)
    assert all('"City of Helsinki"' in q for q, _ in queries)


def test_build_queries_unknown_language_raises() -> None:
    """A7 (PI decision 2026-08-02): fail loud, never fall back to English.

    The old behaviour issued English queries and labelled them ``xx``, so a
    run configured for an unrostered language produced English results under
    that language's name — invisible from the artifact all the way to a
    published per-country figure.
    """
    with pytest.raises(UnknownLanguageError) as exc:
        build_queries("Test Institution", ["xx"])
    assert "xx" in str(exc.value)


def test_build_queries_rejects_the_whole_call_not_just_the_bad_language() -> None:
    """One unrostered code fails the call; it does not silently emit the rest.

    A partial result would be worse than either alternative: the run would
    proceed, under-searched, with nothing on disk saying so.
    """
    with pytest.raises(UnknownLanguageError):
        build_queries("Test Institution", ["en", "xx"])


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


def test_build_queries_includes_country_as_unquoted_hint() -> None:
    """Country is present but NOT a binding phrase (decided 2026-07-30,
    reversing the quoted slot shipped in 6878d1a)."""
    queries = build_queries("House of Representatives", ["en"], country="Belize")
    assert len(queries) == len(GENAI_TERMS_BY_LANG["en"])
    assert all('"House of Representatives"' in q for q, _ in queries)
    assert all("Belize" in q for q, _ in queries)
    assert all('"Belize"' not in q for q, _ in queries)


def test_build_queries_omits_country_when_not_given() -> None:
    """No country (default None, or the empty string a CSV row yields) must
    reproduce the original two-term query — no regression for institutions
    with no known jurisdiction."""
    no_country = build_queries("City of Helsinki", ["en"])
    empty_country = build_queries("City of Helsinki", ["en"], country="")
    assert no_country == empty_country
    for q, _ in no_country:
        assert q.count('"') == 4  # exactly two quoted phrases: name + term


def test_build_queries_slot_order_and_exact_shape() -> None:
    """Name and term quoted, both qualifiers bare, in name → country →
    disambiguation → term order."""
    (query, _) = build_queries(
        "Ain Beida", ["en"], country="Algeria", disambiguation="Oum El Bouaghi — commune"
    )[0]
    assert query == '"Ain Beida" Algeria Oum El Bouaghi — commune "generative AI"'


def test_only_name_and_term_are_ever_binding() -> None:
    """The core invariant: exactly four `"` characters — the name and the term —
    no matter what the qualifier slots contain. Catches quote leakage, stray
    phrase opening, and accidental re-quoting in one assertion."""
    awkward = [
        "Oum El Bouaghi — commune",
        'Departamento Pellegrini, Santiago del Estero — Comisión Municipal "B"',
        "Pece Parish, Palabek Nyimur Subcounty, Lamwo District — village (LC1)",
        "Kunkavav -Vadia, Amreli, Gujarat — gram panchayat",
        "Division No.  4, Manitoba",
        "M'Sila — commune",
    ]
    for value in awkward:
        for q, _ in build_queries("Test Unit", ["en"], country="Testland", disambiguation=value):
            assert q.count('"') == 4, (value, q)


def test_build_queries_omits_disambiguation_when_not_given() -> None:
    """Absent, None, and the empty string a CSV row yields must all reproduce
    the same query. 70% of master rows have no disambiguation value, so this is
    the common path, not the edge case."""
    baseline = build_queries("City of Helsinki", ["en"], country="Finland")
    explicit_none = build_queries(
        "City of Helsinki", ["en"], country="Finland", disambiguation=None
    )
    empty = build_queries("City of Helsinki", ["en"], country="Finland", disambiguation="")
    assert baseline == explicit_none == empty


def test_build_queries_disambiguation_without_country() -> None:
    """The two hint slots are independent — a disambiguation value must not
    require a country to be present."""
    (query, _) = build_queries("Oran", ["en"], disambiguation="Gujarat")[0]
    assert query == '"Oran" Gujarat "generative AI"'


def test_hint_strips_brackets_but_keeps_unit_type() -> None:
    """Per the 2026-07-30 decision: bracket characters out, inner text and the
    unit-type suffix retained. 35,179 disambiguation rows carry parens."""
    (query, _) = build_queries(
        "Oran",
        ["en"],
        country="Uganda",
        disambiguation="Pece Parish, Lamwo District — village (LC1)",
    )[0]
    assert "village LC1" in query
    assert "(" not in query and ")" not in query


def test_hint_strips_brackets_in_country_too() -> None:
    """7 master rows have a parenthesized country — `Holy See (Vatican City
    State)` — so the sanitizer must cover that slot, not just disambiguation."""
    (query, _) = build_queries("Dicastery", ["en"], country="Holy See (Vatican City State)")[0]
    assert "Holy See Vatican City State" in query
    assert "(" not in query and ")" not in query


def test_hint_drops_inner_quotes_so_no_stray_phrase_opens() -> None:
    """Unquoted, an embedded `"` OPENS a phrase — turning a hint into a binding
    match on the wrong tokens. 17 master rows carry one."""
    (query, _) = build_queries(
        "Campo Grande",
        ["en"],
        country="Argentina",
        disambiguation='Departamento Pellegrini, Santiago del Estero — Comisión Municipal "B"',
    )[0]
    assert "Comisión Municipal B" in query
    assert '"B"' not in query


def test_hint_neutralizes_token_initial_minus() -> None:
    """A token-initial `-` is Google's exclusion operator: bare `-Vadia` would
    suppress the very result we want. 75 master rows carry one."""
    (query, _) = build_queries(
        "Kunkavav", ["en"], country="India",
        disambiguation="Kunkavav -Vadia, Amreli, Gujarat — gram panchayat",
    )[0]
    assert "-Vadia" not in query
    assert "Kunkavav Vadia" in query


def test_hint_keeps_mid_token_hyphens() -> None:
    """Only a token-initial `-` is an operator; `Al-Anbar` is inert and its
    hyphen is part of the name, so it must survive."""
    (query, _) = build_queries("Council", ["en"], country="Iraq", disambiguation="Al-Anbar")[0]
    assert "Al-Anbar" in query


def test_hint_collapses_whitespace() -> None:
    """173 master rows have doubled spaces (`Division No.  4, Manitoba`), and
    bracket removal can leave more behind."""
    (query, _) = build_queries(
        "Division No. 4", ["en"], country="Canada", disambiguation="Division No.  4, Manitoba"
    )[0]
    assert "  " not in query


def test_hint_that_sanitizes_to_nothing_is_skipped() -> None:
    """A value that reduces to empty must not leave a blank slot in the join."""
    (query, _) = build_queries("Test Unit", ["en"], country="Testland", disambiguation="()")[0]
    assert query == '"Test Unit" Testland "generative AI"'


def test_build_queries_passes_compound_value_through_whole() -> None:
    """No component is extracted from a compound value. Choosing one would
    change what discovery collects and is a reviewed decision, so this pins the
    no-parsing contract: future extraction must be deliberate, not drift."""
    (query, _) = build_queries(
        "Oran", ["en"], country="India",
        disambiguation="Prantij, Sabar Kantha, Gujarat — gram panchayat",
    )[0]
    assert "Prantij, Sabar Kantha, Gujarat — gram panchayat" in query
