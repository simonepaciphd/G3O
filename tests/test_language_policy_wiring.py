"""The PI-signed language policy, wired into presweep (lane a, 2026-08-30).

`g3o/common/languages.py` shipped on 2026-08-29 as a mechanism with no mapping
and no caller — its own docstring said "not wired in", and the decision to route
the orchestrator through it was the PI's. He took it: 225 rows signed row by row,
0 deferred (`SIGNED-LANGUAGE-POLICY-2026-08-30.md`). This file pins what the
wiring does and, more to the point, what it must never stop doing.

**The load-bearing test is `test_a_country_that_does_not_name_english_still_gets`
`_its_english_evidence_query`, and its twin below it.** Ruling R1 in one
sentence: leg 1 issues a hardcoded English *domain* query for every institution,
but leg 2 issues one query per *configured* language, so adopting the signed
mapping without a policy layer would have deleted the English *evidence* query —
the query production runs today — from the 120 signed rows that do not name
`en`. The twin removes `always_include` from an otherwise identical policy and
asserts the English query disappears, so the pair fails loudly rather than
quietly if someone decides `always_include` is redundant.

Why `en` is not simply written into those 120 rows: the signed `rule` says a
language enters a row when it was *observed* published, and those rows never
observed English (France 0/10 sites, Indonesia 0/5). Writing it in would make
the table contradict its own method — the mapping is an evidence artifact, and
the policy layer is the place for a decision that is not an observation.

Nothing here runs a real query. `EVIDENCE_TERMS_BY_LANG` ships English-only and
the signed policy cannot be configured against it at all — pinned below — so the
end-to-end tests supply their own terms through `discovery_evidence_terms` and
their own policy through a redirected `POLICIES_DIR`.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import pytest

from g3o.common import languages as lang_mod
from g3o.common.contract import LANGS_PATTERN
from g3o.common.languages import (
    SIGNED_POLICY_2026_08_30,
    LanguagePolicy,
    UnknownPolicyError,
    assert_policy_rostered,
    available_policies,
    language_policy_hash,
    load_signed_policy,
)
from g3o.common.paths import institution_dir
from g3o.discovery.query_builder import (
    EVIDENCE_TERMS_BY_LANG,
    UnknownLanguageError,
)
from g3o.extract.batch import build_extract_jobs
from g3o.run import presweep as ps
from g3o.run.presweep import PresweepConfig, plan_run
from g3o.run.presweep.planning import _GUARDED_CONFIG_KEYS, config_snapshot
from g3o.run.presweep.stage_discovery import _run_discovery_site_restricted
from tests.test_discovery_chain import _patch_search, _Recorder

_COLUMNS = [
    "institution_uid", "master_row_id", "country", "country_iso3",
    "government_level", "institution_type", "branch", "institution_name",
    "website", "disambiguation",
]

# A two-country test policy. `Ruritania` names no English — the 120-row case
# ruling R1 is about. `Borduria` names it second — the case that must keep the
# query order it was signed with.
_TEST_MAPPING = {
    "Ruritania": ("xx",),
    "Borduria": ("yy", "en"),
}
_TEST_TERMS = {"en": "AI", "xx": "KI", "yy": "IA"}
_TEST_RULE = "language of government publication (de facto), with English always included"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _master(tmp_path: Path, countries: list[str]) -> Path:
    path = tmp_path / "master.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        for i, country in enumerate(countries, start=1):
            row = {c: "" for c in _COLUMNS}
            row.update({
                "institution_uid": f"G3O-I-{i:08d}",
                "master_row_id": str(i),
                "branch": "executive",
                "country": country,
                "country_iso3": f"C{i:02d}",
                "government_level": "national",
                "institution_type": "ministry",
                "institution_name": f"Ministry of Things {i}",
            })
            w.writerow(row)
    return path


def _write_policy(dir_: Path, policy_id: str, **overrides: Any) -> None:
    payload = {
        "policy_id": policy_id,
        "rule": _TEST_RULE,
        "key": "country",
        "always_include": ["en"],
        "mapping": {k: list(v) for k, v in _TEST_MAPPING.items()},
    }
    payload.update(overrides)
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"language_policy_{policy_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


@pytest.fixture
def policies(tmp_path, monkeypatch):
    """Redirect ``POLICIES_DIR`` at a tmp dir and write the default test policy.

    Safe against cache bleed because ``load_signed_policy`` keys its cache on the
    directory as well as the id — two policies both called ``test`` in two tmp
    dirs are two entries, which is what lets the ``always_include`` twin below
    exist at all.
    """
    dir_ = tmp_path / "policies"
    monkeypatch.setattr(lang_mod, "POLICIES_DIR", dir_)
    _write_policy(dir_, "test")
    return dir_


def _config(tmp_path: Path, countries: list[str], **kw: Any) -> PresweepConfig:
    kw.setdefault("discovery_evidence_terms", dict(_TEST_TERMS))
    return PresweepConfig(
        run_id="policy-test",
        runs_dir=tmp_path / "runs",
        master_csv=_master(tmp_path, countries),
        sample_size=len(countries),
        seed=22294,
        dry_run=True,
        **kw,
    )


def _leg2_queries(tmp_path, monkeypatch, config: PresweepConfig) -> list[tuple[str, str]]:
    """Run Stage 1b against a recorder and return its ``(query, language)`` pairs."""
    plan = plan_run(config)
    recorder = _Recorder()
    _patch_search(monkeypatch, recorder)
    official = {
        ps.records.synth_institution_id(row): "https://example.gov"
        for row in plan.sample
    }
    uses_policy = config.language_policy is not None
    _run_discovery_site_restricted(
        plan.run_dir,
        plan.sample,
        official,
        languages=config.discovery_languages,
        num_results=10,
        mode=config.discovery_mode,
        evidence_terms=config.evidence_terms,
        evidence_terms_for=config.evidence_terms_for if uses_policy else None,
        languages_for=config.languages_for if uses_policy else None,
    )
    issued: list[tuple[str, str]] = []
    for row in plan.sample:
        inst_id = ps.records.synth_institution_id(row)
        payload = json.loads(
            (institution_dir(plan.run_dir, inst_id) / "1b_discovery_site_restricted.json")
            .read_text(encoding="utf-8")
        )
        for entry in payload["queries"]:
            issued.append((entry["query"], entry["language"]))
    return issued


# ---------------------------------------------------------------------------
# R1 — the English evidence query, and the test that fails without it
# ---------------------------------------------------------------------------


def test_a_country_that_does_not_name_english_still_gets_its_english_evidence_query(
    tmp_path, monkeypatch, policies
):
    """Ruling R1, end to end through the leg it is about.

    `Ruritania`'s signed row is `("xx",)` — no English, like France, Indonesia
    and 118 other signed rows. Leg 2 issues one query per configured language,
    so without the policy layer this institution would receive `site:X KI` and
    nothing else, and the English evidence query production has been running
    since the chain shipped would simply be gone for it. Silently: the run would
    complete, the funnel would look normal, and the loss would show up only as a
    per-country yield nobody could explain.
    """
    config = _config(tmp_path, ["Ruritania"], language_policy="test")
    issued = _leg2_queries(tmp_path, monkeypatch, config)

    assert ("site:example.gov AI", "en") in issued, (
        "the English evidence query is gone for a country whose signed row does "
        "not name English — this is ruling R1's silent recall regression"
    )
    assert ("site:example.gov KI", "xx") in issued
    assert len(issued) == 2


def test_the_same_country_loses_that_query_without_always_include(
    tmp_path, monkeypatch, policies
):
    """The twin: the identical policy with the policy layer removed.

    Not a redundant restatement of the test above. That one passes for two
    different reasons — because `always_include` works, or because something
    else put `en` in the set — and this one separates them. It is also the
    failing half of the pair: if someone concludes `always_include` is
    unnecessary and deletes it, the test above goes red and this one stays
    green, which says exactly what broke.
    """
    _write_policy(policies, "no-policy-layer", always_include=[])
    config = _config(tmp_path, ["Ruritania"], language_policy="no-policy-layer")
    issued = _leg2_queries(tmp_path, monkeypatch, config)

    assert issued == [("site:example.gov KI", "xx")]
    assert not any(lang == "en" for _, lang in issued)


def test_a_row_that_already_names_english_keeps_its_signed_query_order(
    tmp_path, monkeypatch, policies
):
    """`Borduria` is signed `yy, en` — Bangladesh's shape (`bn, en`).

    Query order is part of the instrument: leg-2 results are unioned in issue
    order and the earlier query's URLs win the dedup. Making the policy layer
    uniform by hoisting `en` to the front everywhere would reorder 105 signed
    rows that nobody amended, so `always_include` moves only the tags a row does
    not already name.
    """
    config = _config(tmp_path, ["Borduria"], language_policy="test")
    issued = _leg2_queries(tmp_path, monkeypatch, config)

    assert [lang for _, lang in issued] == ["yy", "en"]


def test_always_include_is_prepended_when_the_row_does_not_name_it():
    """R1's signed mechanism table issues the English evidence query first."""
    policy = LanguagePolicy(
        rule=_TEST_RULE, mapping={"X": ("ar", "fr")}, always_include=("en",)
    )
    assert policy.languages_for({"country": "X"})[0] == ("en", "ar", "fr")


def test_the_signed_row_is_readable_without_the_policy_layer():
    """The evidence artifact stays legible on its own — R1's whole point."""
    policy = LanguagePolicy(
        rule=_TEST_RULE, mapping={"X": ("ar", "fr")}, always_include=("en",)
    )
    assert policy.mapped_languages_for({"country": "X"})[0] == ("ar", "fr")


def test_always_include_applies_to_the_fallback_too():
    """An unmapped country measured under a fallback is still searched in English.

    Otherwise the policy layer would have a hole exactly where the mapping is
    least trustworthy.
    """
    policy = LanguagePolicy(
        rule=_TEST_RULE,
        mapping={"X": ("ar",)},
        fallback=("fr",),
        always_include=("en",),
    )
    langs, used_fallback = policy.languages_for({"country": "elsewhere"})
    assert langs == ("en", "fr")
    assert used_fallback is True


# ---------------------------------------------------------------------------
# The pre-spend choke point (A7)
# ---------------------------------------------------------------------------


def test_an_unrostered_policy_tag_is_refused_at_config_construction(tmp_path, policies):
    """Before a Serper credit, not on institution 3,000 of 10,000.

    `assert_policy_rostered` checks every tag the policy *could* select, on any
    institution, rather than the ones the drawn sample happens to reach — a
    sample-dependent check would pass on Monday's draw and fail mid-run on
    Tuesday's, having already spent Monday's money again.
    """
    _write_policy(policies, "unrostered", mapping={"Ruritania": ["zz"]})
    with pytest.raises(UnknownLanguageError) as exc:
        _config(tmp_path, ["Ruritania"], language_policy="unrostered")
    assert "zz" in str(exc.value)


def test_the_check_covers_countries_outside_the_drawn_sample(tmp_path, policies):
    """The sample is one country; the policy names two. Both are checked."""
    _write_policy(policies, "wide", mapping={"Ruritania": ["xx"], "Borduria": ["zz"]})
    with pytest.raises(UnknownLanguageError) as exc:
        _config(tmp_path, ["Ruritania"], language_policy="wide")
    assert "zz" in str(exc.value)


def test_always_include_is_itself_rostered_before_spend():
    """A policy layer that adds an unrostered tag fails on *every* institution."""
    policy = LanguagePolicy(
        rule=_TEST_RULE, mapping={"X": ("en",)}, always_include=("zz",)
    )
    assert "zz" in policy.selectable_languages
    with pytest.raises(UnknownLanguageError):
        assert_policy_rostered(policy, {"en": "AI"})


def test_there_is_no_english_fallback_for_an_unmapped_country(tmp_path, policies):
    """A7 one level down: silently searching English is the failure, not the fix."""
    config = _config(tmp_path, ["Syldavia"], language_policy="test")
    with pytest.raises(lang_mod.UnmappedCountryError):
        config.languages_for({"country": "Syldavia"})


def test_a_policy_and_a_run_level_language_tuple_are_refused_together(
    tmp_path, policies
):
    """Not a precedence rule — it would decide every leg-2 query of the run."""
    with pytest.raises(ValueError, match="not both"):
        _config(
            tmp_path,
            ["Ruritania"],
            language_policy="test",
            discovery_languages=("xx",),
        )


def test_an_unknown_policy_id_is_refused_rather_than_guessed(tmp_path, policies):
    with pytest.raises(UnknownPolicyError) as exc:
        _config(tmp_path, ["Ruritania"], language_policy="2027-01-01")
    assert "2027-01-01" in str(exc.value)


# ---------------------------------------------------------------------------
# Per-row provenance
# ---------------------------------------------------------------------------


def test_chain_provenance_names_leg_1_english_once_not_twice(tmp_path, policies):
    """`Borduria` names `en` in leg 2; chain mode also issues English in leg 1.

    Two queries, two jobs, one tag — the column has one slot and a duplicated
    `en` would fail `LANGS_PATTERN`'s intent even where the regex tolerates it.
    """
    config = _config(tmp_path, ["Borduria"], language_policy="test")
    got = config.institution_search_languages_for({"country": "Borduria"})
    assert got == "en,yy"
    assert re.match(LANGS_PATTERN, got)


def test_chain_provenance_records_leg_1_english_for_a_row_without_it(
    tmp_path, policies
):
    config = _config(tmp_path, ["Ruritania"], language_policy="test")
    got = config.institution_search_languages_for({"country": "Ruritania"})
    assert got == "en,xx"
    assert re.match(LANGS_PATTERN, got)


def test_legacy_provenance_records_only_the_selected_languages(tmp_path, policies):
    """Legacy mode has no hardcoded English leg 1, so nothing is added for it.

    The `en` here is the policy layer's, carried in the language tuple itself —
    a language legacy mode really does issue queries in. The chain-mode
    prepending is a *different* `en`, recording a query the tuple never named.

    The policy's tags have to be in ``GENAI_TERMS_BY_LANG`` here rather than in
    the chain roster — the mode-specific check is the same one
    ``assert_policy_rostered`` delegates to.
    """
    _write_policy(policies, "legacy", mapping={"Ruritania": ["fr"]})
    config = _config(
        tmp_path, ["Ruritania"], language_policy="legacy", discovery_mode="legacy",
        discovery_evidence_terms=None,
    )
    assert config.institution_search_languages_for({"country": "Ruritania"}) == "en,fr"


def _page(url: str = "https://example.gov/a"):
    from g3o.scrape.render import FetchMetadata, RenderedPage

    return RenderedPage(
        url=url,
        text="Nothing about generative AI here.",
        title="Home",
        content_type="html",
        fetch_metadata=FetchMetadata(
            access_date="2026-08-30", http_status=200, final_url=url,
            fetch_method="html", elapsed_ms=10, wait_for=None,
        ),
    )


def test_stage_5_writes_each_institution_its_own_search_languages():
    """The per-row string reaches the extraction job, keyed by institution."""
    page = _page()
    pairs = [
        ({"institution_id": "G3O-I-00000001", "institution_name": "A"}, page),
        ({"institution_id": "G3O-I-00000002", "institution_name": "B"}, page),
    ]
    jobs = build_extract_jobs(
        pairs,
        batch_id="b",
        institution_search_languages={
            "G3O-I-00000001": "en,xx",
            "G3O-I-00000002": "en,yy",
        },
    )
    got = [j.messages[-1]["content"] for j in jobs]
    assert "en,xx" in got[0]
    assert "en,yy" in got[1]


def test_stage_5_refuses_an_institution_it_has_no_search_languages_for():
    """No run-level fallback: that is the misattribution the column prevents."""
    with pytest.raises(KeyError, match="G3O-I-00000002"):
        build_extract_jobs(
            [({"institution_id": "G3O-I-00000002"}, _page())],
            batch_id="b",
            institution_search_languages={"G3O-I-00000001": "en"},
        )


# ---------------------------------------------------------------------------
# The manifest and the F7 resume guard
# ---------------------------------------------------------------------------


def test_the_manifest_does_not_claim_a_single_language_for_a_policy_run(
    tmp_path, policies
):
    """`institution_search_languages: "en"` on a 91-language run is the A7 lie.

    The derived property still describes the run-level configuration, which for
    a policy run is the untouched default. The manifest is the published
    artifact, so it says per-institution instead — and says it in a form nothing
    can parse as a language tag.
    """
    config = _config(tmp_path, ["Ruritania"], language_policy="test")
    snapshot = config_snapshot(config)
    assert snapshot["institution_search_languages"] == (
        "per-institution: language policy test"
    )
    assert not re.match(LANGS_PATTERN, snapshot["institution_search_languages"])
    assert snapshot["language_policy"] == "test"
    assert snapshot["language_policy_hash"] == language_policy_hash(
        config.signed_language_policy
    )


def test_a_run_without_a_policy_keeps_its_manifest_shape(tmp_path, policies):
    config = _config(tmp_path, ["Ruritania"], discovery_evidence_terms=None)
    snapshot = config_snapshot(config)
    assert snapshot["institution_search_languages"] == "en"
    assert snapshot["language_policy"] is None
    assert snapshot["language_policy_hash"] is None


def test_the_resume_guard_compares_the_policy_and_its_hash():
    assert "language_policy" in _GUARDED_CONFIG_KEYS
    assert "language_policy_hash" in _GUARDED_CONFIG_KEYS


def test_an_edit_to_a_signed_mapping_moves_the_hash_under_an_unchanged_id(
    tmp_path, policies
):
    """Which is why the id alone is not enough for the resume guard."""
    config = _config(tmp_path, ["Ruritania"], language_policy="test")
    before = config_snapshot(config)["language_policy_hash"]

    lang_mod._load_signed_policy.cache_clear()
    _write_policy(policies, "test", mapping={"Ruritania": ["xx", "yy"]})
    second = tmp_path / "b"
    second.mkdir()
    after = config_snapshot(
        _config(second, ["Ruritania"], language_policy="test")
    )["language_policy_hash"]

    assert before != after


def test_the_hash_tells_the_evidence_layer_from_the_policy_layer():
    """Same queries issued, different instrument, different fingerprint.

    A mapping that names `en` outright answered the observation question `yes`;
    a mapping that gets `en` from `always_include` never did. Folding the policy
    layer into the per-country lists would hash the two identically and lose the
    distinction the signature exists to record.
    """
    observed = LanguagePolicy(rule=_TEST_RULE, mapping={"X": ("fr", "en")})
    by_policy = LanguagePolicy(
        rule=_TEST_RULE, mapping={"X": ("fr",)}, always_include=("en",)
    )
    assert observed.languages_for({"country": "X"})[0] == ("fr", "en")
    assert by_policy.languages_for({"country": "X"})[0] == ("en", "fr")
    assert language_policy_hash(observed) != language_policy_hash(by_policy)


# ---------------------------------------------------------------------------
# Non-regression: no policy, nothing changes
# ---------------------------------------------------------------------------


def test_a_run_without_a_policy_issues_exactly_what_it_always_did(
    tmp_path, monkeypatch, policies
):
    """The default path, unchanged — which is every run to date."""
    config = _config(tmp_path, ["Ruritania"], discovery_evidence_terms=None)
    issued = _leg2_queries(tmp_path, monkeypatch, config)
    assert issued == [("site:example.gov AI", "en")]


# ---------------------------------------------------------------------------
# The signed asset itself
# ---------------------------------------------------------------------------


def test_the_signed_policy_ships_and_is_the_only_one():
    assert available_policies() == (SIGNED_POLICY_2026_08_30,)


def test_the_signed_policy_carries_225_rows_and_zero_deferred():
    policy = load_signed_policy(SIGNED_POLICY_2026_08_30)
    assert len(policy.countries) == 225


def test_every_signed_tag_is_storable_in_the_extraction_contract():
    """Widened to `language[-script]` on 2026-08-29 for exactly these tags."""
    policy = load_signed_policy(SIGNED_POLICY_2026_08_30)
    assert re.match(LANGS_PATTERN, ",".join(policy.selectable_languages))


def test_the_signed_policy_supplies_english_by_policy_not_by_row():
    """The 120 rows are the artifact of R1; a change to that count is a signature change."""
    policy = load_signed_policy(SIGNED_POLICY_2026_08_30)
    assert policy.always_include == ("en",)
    without = [
        country
        for country in policy.countries
        if "en" not in policy.mapped_languages_for({"country": country})[0]
    ]
    assert len(without) == 120
    assert all(
        "en" in policy.languages_for({"country": country})[0]
        for country in policy.countries
    )


@pytest.mark.parametrize(
    ("country", "expected"),
    [
        ("Morocco", ("ar", "fr", "tzm")),
        ("Ethiopia", ("en", "am", "om")),
        ("Serbia", ("sr-cyrl", "sr-latn", "hu")),
        ("Montenegro", ("cnr-latn", "cnr-cyrl", "sr-cyrl", "sr-latn")),
        ("Timor-Leste", ("tet", "pt", "en")),
        ("Israel", ("he", "en", "ar")),
        ("China", ("zh-hans",)),
        ("Kosovo", ("sq", "sr-latn")),
    ],
)
def test_the_eight_rows_amended_at_signature_are_as_signed(country, expected):
    """Eight rows the PI changed while signing. A silent revert is a silent
    reversal of a ruling, so each one is pinned by name."""
    policy = load_signed_policy(SIGNED_POLICY_2026_08_30)
    assert policy.mapped_languages_for({"country": country})[0] == expected


def test_the_signed_rule_string_is_the_amended_one():
    """The 2026-08-29 string described only the 12-site observation and would
    have misdescribed the 197 guessed rows (ruling R4). It hashes with the
    policy, so restating it is a different instrument."""
    policy = load_signed_policy(SIGNED_POLICY_2026_08_30)
    assert "the remaining 197 countries are graded expert guesses" in policy.rule
    assert "English is included for every country by policy" in policy.rule


def test_the_signed_policy_hash_is_pinned():
    """Any edit to the asset — a row, the rule, the policy layer — moves this.

    Pinned so that editing the checked-in mapping cannot pass as a refactor.
    Amending a row is a PI-signed decision; updating this constant is how a
    change to one gets noticed.
    """
    policy = load_signed_policy(SIGNED_POLICY_2026_08_30)
    assert language_policy_hash(policy) == "b1de14180755c021"


def test_the_signed_policy_cannot_run_against_the_shipped_roster():
    """The hard fence. `EVIDENCE_TERMS_BY_LANG` is seeded English-only and lane
    (b) — a PI-signed leg-2 term for each of the 90 non-English tags — has not
    started. This test is the tripwire on that fence: it goes red the moment the
    roster grows, which is the moment someone should be checking that the terms
    were signed rather than translated."""
    policy = load_signed_policy(SIGNED_POLICY_2026_08_30)
    with pytest.raises(UnknownLanguageError) as exc:
        assert_policy_rostered(policy, EVIDENCE_TERMS_BY_LANG)
    unknown = str(exc.value)
    assert "tzm" in unknown and "zh-hans" in unknown
    assert len(policy.selectable_languages) == 91
