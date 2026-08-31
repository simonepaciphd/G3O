"""Per-institution language selection (``g3o.common.languages``).

The module supplies the selector the pipeline has never had — discovery chooses
its query languages per *run*, not per institution — and it is deliberately
inert until a caller supplies a mapping. These tests pin the four properties
that make it safe to wire in later, rather than merely present:

1. **No default mapping, and no default rule.** The instrument cannot ship
   itself: a policy that names no rule, or carries no table, does not construct.
2. **Fail-loud on an unmapped country**, never a silent English fallback. This
   is the A7 decision (2026-08-02) carried one grain down; a fallback exists but
   only when explicitly asked for, and the caller is told when it fired.
3. **The roster guarantee survives the finer grain.** Under a run-level tuple,
   ``assert_languages_rostered`` rejected an unqueryable language before a
   credit was spent. Per-institution selection must check every language the
   policy *could* select, up front — not the ones it happened to select, which
   is only knowable after the run is paid for.
4. **Provenance stays honest.** The per-row string must satisfy
   ``contract.LANGS_PATTERN`` and must include chain mode's always-English
   leg 1, or a ``kk``-selected row claims a language half its queries were not
   issued in.

The GenAI-term roster is untouched by any of this; the last test pins that.
"""

from __future__ import annotations

import re

import pytest

from g3o.common.contract import LANGS_PATTERN
from g3o.common.languages import (
    EmptyPolicyError,
    LanguagePolicy,
    LanguagePolicyError,
    UnmappedCountryError,
    assert_policy_rostered,
    language_policy_hash,
    search_languages_string,
)
from g3o.discovery.query_builder import (
    EVIDENCE_TERMS_BY_LANG,
    GENAI_TERMS_BY_LANG,
    UnknownLanguageError,
    build_queries,
    genai_terms_roster_hash,
)

# The twelve-country wave-2 mix, used as a shape rather than as a proposal: the
# tags here are ISO 639-1 codes chosen to exercise the machinery, and no row of
# this table is a signed mapping. The real mapping is tabled for the PI.
_SHAPE_ONLY = {
    "Czechia": ("cs",),
    "Rwanda": ("rw", "en", "fr"),
    "France": ("fr",),
}


def _policy(**overrides):
    kwargs = {
        "rule": "official language(s) of the state, as named in its constitution",
        "mapping": dict(_SHAPE_ONLY),
    }
    kwargs.update(overrides)
    return LanguagePolicy(**kwargs)


# ---------------------------------------------------------------------------
# 1. The instrument cannot ship itself
# ---------------------------------------------------------------------------


def test_mapping_is_required_and_has_no_default():
    """``LanguagePolicy()`` must not construct — there is no default mapping."""
    with pytest.raises(TypeError):
        LanguagePolicy()  # type: ignore[call-arg]


def test_empty_mapping_rejected():
    with pytest.raises(EmptyPolicyError, match="no default mapping"):
        _policy(mapping={})


def test_rule_is_required_and_non_blank():
    """A table without its rule does not say what it measured."""
    with pytest.raises(EmptyPolicyError, match="rule is required"):
        _policy(rule="   ")


def test_empty_language_tuple_rejected():
    """Searching an institution in zero languages would read as absence of activity."""
    with pytest.raises(EmptyPolicyError):
        _policy(mapping={"Czechia": ()})


def test_bare_string_is_not_a_language_sequence():
    """``"cs"`` would iterate as ``("c", "s")`` — two one-letter languages."""
    with pytest.raises(LanguagePolicyError, match="iterate as characters"):
        _policy(mapping={"Czechia": "cs"})


@pytest.mark.parametrize(
    "bad", ["CS", "c", "uz-Latn", "uz-LATN", "", "kk1", "abcd", "uz-lat", "uz-latn-cyrl"]
)
def test_non_contract_storable_tag_rejected_at_construction(bad):
    """A tag the contract cannot store must fail here, not at Stage 5.

    ``contract.LANGS_PATTERN`` admits lowercase ``language[-script]`` tags only
    (PI ruling 2026-08-29). Mixed case is rejected deliberately: BCP 47 is
    case-insensitive, so admitting ``uz-Latn`` alongside ``uz-latn`` would let
    one instrument write two provenance strings.
    """
    with pytest.raises(LanguagePolicyError, match="LANGS_PATTERN"):
        _policy(mapping={"Uzbekistan": (bad,)})


@pytest.mark.parametrize("good", ["ces", "uz-latn", "uz-cyrl", "zh-hant", "lo"])
def test_widened_tags_accepted_and_storable(good):
    """The three cases the 2026-08-29 widening exists for: an ISO 639-3 code
    with no two-letter equivalent, and a script variant — each must construct
    AND satisfy the widened ``contract.LANGS_PATTERN`` end to end."""
    policy = _policy(mapping={"Uzbekistan": (good,)})
    langs, used_fallback = policy.languages_for({"country": "Uzbekistan"})
    assert langs == (good,)
    assert not used_fallback
    recorded = search_languages_string(langs, mode="chain")
    assert re.match(LANGS_PATTERN, recorded), recorded
    assert recorded == f"en,{good}"


def test_duplicate_country_key_after_normalization_rejected():
    """Two keys that normalize to one country would resolve by dict order."""
    with pytest.raises(LanguagePolicyError, match="duplicate country key"):
        _policy(mapping={"Czechia": ("cs",), " czechia ": ("en",)})


def test_blank_country_key_rejected():
    with pytest.raises(EmptyPolicyError, match="empty country key"):
        _policy(mapping={"  ": ("cs",)})


# ---------------------------------------------------------------------------
# 2. Fail-loud, not fall-back
# ---------------------------------------------------------------------------


def test_unmapped_country_raises_rather_than_falling_back_to_english():
    """The A7 defect, one grain down: a silent English fallback would issue
    English queries for Laos and file them under a Laos readiness figure."""
    policy = _policy()
    with pytest.raises(UnmappedCountryError) as exc:
        policy.languages_for({"country": "Lao People's Democratic Republic"})
    # The message must name the PI route, not offer a config workaround.
    assert "PI-signed row" in str(exc.value)


def test_fallback_is_opt_in_and_reports_that_it_fired():
    policy = _policy(fallback=("en",))
    langs, used_fallback = policy.languages_for({"country": "Laos"})
    assert langs == ("en",)
    assert used_fallback is True, (
        "a run in which 40% of rows fell back is a different measurement from "
        "one in which none did, and the tags alone cannot show it"
    )


def test_mapped_country_does_not_report_a_fallback():
    """A fallback being *set* must not make a mapped country report one."""
    langs, used_fallback = _policy(fallback=("en",)).languages_for(
        {"country": "Czechia"}
    )
    assert langs == ("cs",)
    assert used_fallback is False


def test_country_key_matching_is_normalized_on_both_sides():
    """Master ``country`` values are free text; casing and padding must not
    make ``"Czechia"`` and ``"czechia "`` two countries."""
    policy = _policy()
    assert policy.languages_for({"country": "  CZECHIA  "})[0] == ("cs",)


def test_missing_country_field_is_unmapped_not_silently_empty():
    policy = _policy()
    with pytest.raises(UnmappedCountryError):
        policy.languages_for({})


def test_alternate_key_is_honoured():
    """The wave-2 frame carries ``country_iso3``, the stabler join key."""
    policy = LanguagePolicy(
        rule="official language(s) of the state",
        mapping={"CZE": ("cs",)},
        key="country_iso3",
    )
    assert policy.languages_for({"country_iso3": "cze", "country": "Czechia"})[0] == (
        "cs",
    )


# ---------------------------------------------------------------------------
# 3. The roster guarantee survives the finer grain
# ---------------------------------------------------------------------------


def test_selectable_languages_is_the_whole_reachable_set_including_fallback():
    policy = _policy(fallback=("de",))
    assert policy.selectable_languages == ("cs", "de", "en", "fr", "rw")


def test_assert_policy_rostered_rejects_a_policy_the_run_cannot_query():
    """``rw`` is in no shipped roster, so a policy that can select it must be
    rejected before the first credit — not on institution 3,000 of 10,000."""
    policy = _policy()
    assert "rw" not in GENAI_TERMS_BY_LANG
    with pytest.raises(UnknownLanguageError):
        assert_policy_rostered(policy, GENAI_TERMS_BY_LANG)


def test_assert_policy_rostered_passes_when_every_selectable_language_is_rostered():
    policy = LanguagePolicy(
        rule="official language(s) of the state",
        mapping={"France": ("fr",), "Germany": ("de",)},
    )
    assert_policy_rostered(policy, GENAI_TERMS_BY_LANG)  # does not raise


def test_assert_policy_rostered_is_mode_specific():
    """A language rostered for ``legacy`` is not thereby runnable under ``chain``.

    ``fr`` has four four-slot terms but no leg-2 evidence token, so the same
    policy must pass against ``GENAI_TERMS_BY_LANG`` and fail against
    ``EVIDENCE_TERMS_BY_LANG``.
    """
    policy = LanguagePolicy(
        rule="official language(s) of the state", mapping={"France": ("fr",)}
    )
    assert_policy_rostered(policy, GENAI_TERMS_BY_LANG)
    with pytest.raises(UnknownLanguageError):
        assert_policy_rostered(policy, EVIDENCE_TERMS_BY_LANG)


def test_policy_hash_is_stable_and_moves_on_every_instrument_edit():
    base = _policy()
    assert language_policy_hash(base) == language_policy_hash(_policy())

    # A different rule over an identical table is a different measurement.
    assert language_policy_hash(_policy(rule="most-spoken language")) != (
        language_policy_hash(base)
    )
    # Query order within a country is part of the instrument.
    reordered = _policy(mapping={**_SHAPE_ONLY, "Rwanda": ("en", "rw", "fr")})
    assert language_policy_hash(reordered) != language_policy_hash(base)
    # A fallback changes what unmapped countries measure.
    assert language_policy_hash(_policy(fallback=("en",))) != language_policy_hash(base)
    # The join key changes which rows match.
    assert language_policy_hash(
        LanguagePolicy(rule=base.rule, mapping=dict(_SHAPE_ONLY), key="country_iso3")
    ) != language_policy_hash(base)


def test_policy_hash_ignores_source_literal_order_of_countries():
    """Reordering the *table* is not an instrument change; reordering a
    country's languages is. Keys are sorted, tuples are not."""
    shuffled = {
        "France": ("fr",),
        "Rwanda": ("rw", "en", "fr"),
        "Czechia": ("cs",),
    }
    assert language_policy_hash(_policy(mapping=shuffled)) == language_policy_hash(
        _policy()
    )


def test_policy_hash_ignores_the_subnational_note():
    """The note documents the policy's limits; it does not change a query."""
    noted = _policy(subnational_note="country-level only; an Indian block is wrong")
    assert language_policy_hash(noted) == language_policy_hash(_policy())


# ---------------------------------------------------------------------------
# 4. Per-row provenance
# ---------------------------------------------------------------------------


def test_chain_mode_provenance_always_names_english_leg_1():
    """Leg 1's ``official website`` suffix is English by PI decision, so a
    chain row searched in ``kk`` was searched in ``en`` too."""
    assert search_languages_string(("kk",), mode="chain") == "en,kk"


def test_chain_mode_provenance_does_not_duplicate_english():
    assert search_languages_string(("en", "fr"), mode="chain") == "en,fr"


def test_legacy_mode_provenance_records_only_the_selected_languages():
    assert search_languages_string(("cs",), mode="legacy") == "cs"


def test_provenance_preserves_query_order():
    assert search_languages_string(("rw", "fr"), mode="legacy") == "rw,fr"


def test_empty_provenance_is_an_error_not_an_empty_string():
    with pytest.raises(EmptyPolicyError):
        search_languages_string((), mode="legacy")


@pytest.mark.parametrize("mode", ["chain", "legacy"])
def test_provenance_satisfies_the_extraction_contract_pattern(mode):
    """Whatever a policy accepts must be storable in
    ``ContractRow.institution_search_languages``."""
    policy = _policy(fallback=("en",))
    for country in list(policy.countries) + ["not-in-the-table"]:
        langs, _ = policy.languages_for({"country": country})
        recorded = search_languages_string(langs, mode=mode)
        assert re.match(LANGS_PATTERN, recorded), recorded


# ---------------------------------------------------------------------------
# 5. This module does not move the GenAI roster
# ---------------------------------------------------------------------------


def test_importing_and_using_a_policy_does_not_move_the_roster_hash():
    """The roster is the PI's; per-institution *selection* must not touch it."""
    before = genai_terms_roster_hash()
    policy = _policy(fallback=("en",))
    for country in policy.countries:
        policy.languages_for({"country": country})
    language_policy_hash(policy)
    assert genai_terms_roster_hash() == before


def test_build_queries_already_accepts_a_per_institution_language_tuple():
    """The seam exists: ``build_queries`` takes ``languages`` per call, so
    per-institution selection needs no change to the query builders.

    This is what keeps the roster hash frozen — the wiring is a caller change,
    not a query-builder change.
    """
    policy = LanguagePolicy(
        rule="official language(s) of the state",
        mapping={"France": ("fr",), "Germany": ("de",)},
    )
    langs_fr, _ = policy.languages_for({"country": "France"})
    langs_de, _ = policy.languages_for({"country": "Germany"})

    fr_queries = build_queries("Villegongis", list(langs_fr), country="France")
    de_queries = build_queries("Langenberg", list(langs_de), country="Germany")

    assert {lang for _, lang in fr_queries} == {"fr"}
    assert {lang for _, lang in de_queries} == {"de"}
    # Two institutions in one run, searched in different languages — the thing
    # a run-level ``discovery_languages`` tuple cannot express.
    assert len(fr_queries) == len(GENAI_TERMS_BY_LANG["fr"])
    assert len(de_queries) == len(GENAI_TERMS_BY_LANG["de"])
