"""Leg 1 goes multilingual — the flag, the gate, and the bypass.

Card 2 of ``agent-workspace/2026-09-01-discovery-legs/``, implementing the PI's
ruling of 2026-09-01, verbatim: *"For leg 1: i'd just use each of the country's
languages / multiple serper calls. This is a step that we likely won't reuse much
as the database self-populates with websites."*

That ruling reverses the 2026-08-02 decision which left ``DOMAIN_QUERY_SUFFIX``
un-localized, and it reverses only half of it. What was ruled is that leg 1 issues
one query per language the institution's policy row names, **additive** to the
English one. What was *not* ruled is any particular suffix — the 2026-08-02
decision's own words were "settling it needs its own A/B on the existing harness,
not a default flip", and the localized side has no measurement against leg 1's
82.0% recall on the n=200 truth pool.

So this file pins three things at once, and the middle one is the point:

1. The mechanism works — one query per policy language, each tagged with the
   language whose suffix produced it, English always among them.
2. **It cannot be turned on.** ``DOMAIN_SUFFIX_BY_LANG`` holds one English row,
   and the pre-spend choke point refuses a multilingual run for every policy tag
   that has no signed suffix. Production is byte-identical to what it was.
3. Leg 1 no longer runs when the master already carries the answer (card §4).

**No non-English suffix ships in the repo**, here included. The tests that need a
complete roster patch synthetic placeholders in place — ``<fr suffix>`` is not a
translation and could never be mistaken for one, which is exactly why it is safe
to write in a test file. The 89 real rows arrive through a PI-signed roster on
probe evidence, the way the 90 evidence terms did.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from g3o.common.languages import load_signed_policy
from g3o.discovery.query_builder import (
    DOMAIN_QUERY_LANG,
    DOMAIN_QUERY_SUFFIX,
    DOMAIN_SUFFIX_BY_LANG,
    UnknownLanguageError,
    build_domain_queries,
    build_domain_query,
    domain_suffix_roster_hash,
)
from g3o.run import presweep as ps
from g3o.run.presweep import PresweepConfig, plan_run
from g3o.run.presweep.planning import (
    _ABSENT_TOLERATED_CONFIG_KEYS,
    _GUARDED_CONFIG_KEYS,
    build_manifest,
)
from tests._layout import inst_dir as inst_dir_of
from tests.test_discovery_chain import _patch_search, _Recorder

_POLICY_ID = "2026-08-30"

_COLUMNS = [
    "institution_uid", "master_row_id", "country", "country_iso3",
    "government_level", "institution_type", "branch", "institution_name",
    "website", "disambiguation", "official_site_url",
]


def _master(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "master.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        for i, r in enumerate(rows, start=1):
            base = {c: "" for c in _COLUMNS}
            base.update({
                "institution_uid": f"G3O-I-{i:08d}",
                "master_row_id": str(i),
                "branch": "executive",
                "government_level": "national",
                "institution_type": "ministry",
            })
            base.update(r)
            w.writerow(base)
    return path


def _france(**extra: str) -> list[dict[str, str]]:
    """One institution in a country whose signed policy row is ``['fr']``.

    France is the worked example the policy's own docstring uses for the
    ``always_include`` layer: the row does not name English, because the rule
    admits a language only where it was *observed* published and France published
    English on 0 of 10 sampled sites. So the policy's answer is ``('en', 'fr')``
    with the policy layer applied — English prepended, not written into the row.
    """
    row = {
        "country": "France",
        "country_iso3": "FRA",
        "institution_name": "Ministry of Things",
    }
    row.update(extra)
    return [row]


def _config(tmp_path: Path, rows: list[dict[str, str]] | None = None, **kw: Any):
    kw.setdefault("discovery_mode", "chain")
    return PresweepConfig(
        run_id="leg1-ml-test",
        runs_dir=tmp_path / "runs",
        master_csv=_master(tmp_path, rows if rows is not None else _france()),
        sample_size=1,
        seed=22294,
        dry_run=True,
        **kw,
    )


def _sign_placeholder_suffixes(monkeypatch) -> None:
    """Give every policy tag a placeholder suffix, in place, for one test.

    ``monkeypatch.setitem`` mutates the one dict object rather than rebinding a
    name, which matters: ``config.py`` imported ``DOMAIN_SUFFIX_BY_LANG`` by name
    at module load, so rebinding the attribute on ``query_builder`` would leave
    the config gate reading the unpatched roster and the test would pass against
    half the change.
    """
    policy = load_signed_policy(_POLICY_ID)
    for tag in policy.selectable_languages:
        if tag not in DOMAIN_SUFFIX_BY_LANG:
            monkeypatch.setitem(DOMAIN_SUFFIX_BY_LANG, tag, f"<{tag} suffix>")


# ---------------------------------------------------------------------------
# The roster is the gate
# ---------------------------------------------------------------------------


def test_the_suffix_roster_ships_english_only():
    """One row, and it is the suffix production has always issued.

    The tripwire for the signature that has not happened yet. It is the leg-1
    counterpart of ``test_evidence_roster_is_the_signed_roster_of_2026_08_31``,
    at the stage that test was at before 2026-08-31: pinned to English-only, and
    it should go red exactly once — in the commit carrying the PI's sign-off on
    the suffix table, which then re-points it at a fingerprint the way the
    evidence-roster test was re-pointed.
    """
    assert DOMAIN_SUFFIX_BY_LANG == {"en": DOMAIN_QUERY_SUFFIX}
    assert DOMAIN_SUFFIX_BY_LANG["en"] == "official website"


def test_leg1_multilingual_cannot_be_turned_on_before_the_roster_is_signed(tmp_path):
    """The pre-spend choke point, doing the only job it has today.

    Raised at *config construction*, not on institution 3,000 of 20,293 — the A7
    discipline, and the reason ``assert_policy_rostered`` exists at all. The
    message must name the card rather than the multilingual subproject: leg 1's
    suffixes are signed in a different place than leg 2's terms, and sending the
    one person who ever reads this error to the wrong signature table is the
    whole cost of getting it wrong.
    """
    with pytest.raises(UnknownLanguageError) as exc:
        _config(tmp_path, language_policy=_POLICY_ID, discovery_leg1_multilingual=True)
    msg = str(exc.value)
    assert "2-legs-leg1-multilingual.txt" in msg
    # Named, not counted: the operator needs to see which tags are missing.
    assert "'fr'" in msg
    assert "subprojects/multilingual-pipeline" not in msg


def test_leg1_multilingual_requires_a_language_policy(tmp_path, monkeypatch):
    """Additive is a property of the signed policy, not of this code.

    ``always_include: ['en']`` is what puts English in every institution's tuple.
    A run-level ``discovery_languages`` carries no such guarantee, so allowing
    the flag without a policy would let ``discovery_languages=('fr',)`` *replace*
    the English arm and then report a within-institution comparison that was
    never run. Refused rather than silently repaired.
    """
    _sign_placeholder_suffixes(monkeypatch)
    with pytest.raises(ValueError, match="requires language_policy"):
        _config(tmp_path, discovery_leg1_multilingual=True)


def test_leg1_multilingual_requires_chain_mode(tmp_path, monkeypatch):
    """Legacy's leg 1 *is* the language roster, so the flag would mean nothing."""
    _sign_placeholder_suffixes(monkeypatch)
    with pytest.raises(ValueError, match="requires discovery_mode="):
        _config(
            tmp_path,
            discovery_mode="legacy",
            language_policy=_POLICY_ID,
            discovery_leg1_multilingual=True,
        )


# ---------------------------------------------------------------------------
# The builder
# ---------------------------------------------------------------------------


def test_build_domain_queries_is_additive_and_english_is_byte_identical(monkeypatch):
    """The English arm is not merely present — it is the query production issues.

    A localized leg that rephrased the English query while adding others would
    make the paired comparison meaningless: the control arm has to be the
    instrument whose 82.0% recall the treatment is read against.
    """
    monkeypatch.setitem(DOMAIN_SUFFIX_BY_LANG, "fr", "<fr suffix>")
    out = build_domain_queries(
        "Ministry of Things", ("en", "fr"), "France", "Ile-de-France — region",
    )
    assert [lang for _, lang in out] == ["en", "fr"]
    assert out[0][0] == build_domain_query(
        "Ministry of Things", "France", "Ile-de-France — region",
    )
    assert out[1][0].endswith("<fr suffix>")
    # Same slots, same order, only the suffix differs.
    assert out[0][0].removesuffix(DOMAIN_QUERY_SUFFIX) == out[1][0].removesuffix(
        "<fr suffix>"
    )


def test_build_domain_queries_fails_loud_on_an_unrostered_tag():
    """No silent English fallback — the defect line A7 closed on leg 2.

    A fallback would issue the English query, tag it ``fr``, and make the
    misattribution unrecoverable from the artifact onward. Asserted for the whole
    list before any query is built, so an institution is never half-issued.
    """
    with pytest.raises(UnknownLanguageError):
        build_domain_queries("Ministry of Things", ("en", "fr"), "France")


def test_two_tags_sharing_a_suffix_both_keep_their_row(monkeypatch):
    """Identical query strings are not deduped, and the reason is attribution.

    Dropping the second would save no credit — ``search_google_detailed`` keys its
    cache on the whole payload, so the repeat is served from disk — and it would
    lose that language's claim on whatever the query surfaced.
    """
    monkeypatch.setitem(DOMAIN_SUFFIX_BY_LANG, "fr", "official website")
    out = build_domain_queries("Ministry of Things", ("en", "fr"), "France")
    assert [lang for _, lang in out] == ["en", "fr"]
    assert out[0][0] == out[1][0]


# ---------------------------------------------------------------------------
# End to end through Stage 1a
# ---------------------------------------------------------------------------


def test_stage_1a_default_is_one_english_query_even_under_a_policy(
    tmp_path, monkeypatch
):
    """Production behaviour, pinned on the far side of a configured policy.

    A policy-configured run — which is what production runs now — must still
    issue exactly one leg-1 query, in English, while the flag is off. This is the
    test that would catch the change leaking into every run by default.
    """
    cfg = _config(tmp_path, language_policy=_POLICY_ID)
    plan = plan_run(cfg)
    inst_id = ps.synth_institution_id(plan.sample[0])
    rec = _Recorder()
    _patch_search(monkeypatch, rec)

    ps._run_discovery_general(
        plan.run_dir, plan.sample,
        languages=cfg.discovery_languages, num_results=10, mode="chain",
        leg1_languages_for=None,
    )

    assert len(rec.queries) == 1
    assert rec.queries[0].endswith(DOMAIN_QUERY_SUFFIX)
    artifact = json.loads(
        (inst_dir_of(plan.run_dir, inst_id) / "1a_discovery_general.json").read_text(
            encoding="utf-8"
        )
    )
    assert [q["language"] for q in artifact["queries"]] == [DOMAIN_QUERY_LANG]


def test_stage_1a_issues_one_query_per_policy_language_when_the_flag_is_on(
    tmp_path, monkeypatch
):
    """The mechanism, end to end, with per-URL language attribution.

    France's signed row is ``['fr']`` and the policy layer prepends ``en``, so
    the institution gets two leg-1 queries in that order. Both are recorded in
    the artifact's ``queries`` provenance with their own language, and the URL
    both queries returned carries ``found_by`` naming both — the attribution
    ``report.health`` and ``report.filter_eligibility`` read to answer "which
    language surfaced this URL", which on a merged pile would only ever be able
    to answer "whichever ran first".
    """
    _sign_placeholder_suffixes(monkeypatch)
    cfg = _config(
        tmp_path, language_policy=_POLICY_ID, discovery_leg1_multilingual=True
    )
    assert cfg.leg1_languages_for({"country": "France"}) == ("en", "fr")
    plan = plan_run(cfg)
    inst_id = ps.synth_institution_id(plan.sample[0])
    rec = _Recorder()
    _patch_search(monkeypatch, rec)

    ps._run_discovery_general(
        plan.run_dir, plan.sample,
        languages=cfg.discovery_languages, num_results=10, mode="chain",
        leg1_languages_for=cfg.leg1_languages_for,
    )

    assert len(rec.queries) == 2
    assert rec.queries[0].endswith(DOMAIN_QUERY_SUFFIX)
    assert rec.queries[1].endswith("<fr suffix>")

    artifact = json.loads(
        (inst_dir_of(plan.run_dir, inst_id) / "1a_discovery_general.json").read_text(
            encoding="utf-8"
        )
    )
    assert [q["language"] for q in artifact["queries"]] == ["en", "fr"]
    # One URL, found by both legs, and both are named.
    assert len(artifact["records"]) == 1
    found_by = artifact["records"][0]["found_by"]
    assert [f["language"] for f in found_by] == ["en", "fr"]
    # First-finder meaning is preserved on ``language``/``query``.
    assert artifact["records"][0]["language"] == "en"


# ---------------------------------------------------------------------------
# Card §4 — leg 1 does not rediscover a known answer
# ---------------------------------------------------------------------------


def test_leg1_is_skipped_when_the_master_already_carries_the_site(
    tmp_path, monkeypatch
):
    """No credit spent, and the skip is written down rather than left blank.

    ``official_site_url`` has bypassed Stage 2 since 2026-05-09 while Stage 1a
    ran on the full sample regardless. The artifact still has to be written: both
    ``report.health`` and ``report.outcomes`` test that file's existence, so a
    missing file would make a deliberate skip read as an institution whose
    queries came back empty.
    """
    rows = _france(official_site_url="https://ministere.gouv.fr/")
    cfg = _config(tmp_path, rows=rows, language_policy=_POLICY_ID)
    plan = plan_run(cfg)
    inst_id = ps.synth_institution_id(plan.sample[0])
    rec = _Recorder()
    _patch_search(monkeypatch, rec)

    out = ps._run_discovery_general(
        plan.run_dir, plan.sample,
        languages=cfg.discovery_languages, num_results=10, mode="chain",
    )

    assert rec.queries == []
    assert out[inst_id] == []
    artifact = json.loads(
        (inst_dir_of(plan.run_dir, inst_id) / "1a_discovery_general.json").read_text(
            encoding="utf-8"
        )
    )
    assert artifact["bypassed"] is True
    assert artifact["source"] == "master_csv"
    assert artifact["url"] == "https://ministere.gouv.fr/"
    assert artifact["records"] == []
    assert artifact["queries"] == []


def test_a_blank_official_site_url_is_not_a_bypass(tmp_path, monkeypatch):
    """An empty cell must not silently skip leg 1.

    ``institution_record`` maps a blank cell to ``None``, and this pins that the
    bypass tests the projected value rather than the raw one — a master where the
    column exists but is empty (which is every master today) has to run leg 1.
    """
    cfg = _config(tmp_path, rows=_france(official_site_url=""))
    plan = plan_run(cfg)
    rec = _Recorder()
    _patch_search(monkeypatch, rec)

    ps._run_discovery_general(
        plan.run_dir, plan.sample,
        languages=cfg.discovery_languages, num_results=10, mode="chain",
    )
    assert len(rec.queries) == 1


# ---------------------------------------------------------------------------
# The fingerprint
# ---------------------------------------------------------------------------


def test_the_roster_hash_is_recorded_and_guarded(tmp_path):
    """Recorded while the roster is one row, so the first signed row moves it.

    The evidence roster is the precedent in the negative: while it held one
    English row the manifest fingerprinted ``GENAI_TERMS_BY_LANG``, a roster a
    chain run never reads, and the gap only became visible once 90 rows arrived.
    """
    cfg = _config(tmp_path)
    plan = plan_run(cfg)
    manifest = build_manifest(cfg, plan.sample)
    assert (
        manifest["config"]["domain_suffix_roster_hash"] == domain_suffix_roster_hash()
    )
    assert "domain_suffix_roster_hash" in _GUARDED_CONFIG_KEYS
    # Absent-tolerated: every manifest written before 2026-09-01 lacks the key,
    # and every one of those runs issued the English suffix by construction.
    assert "domain_suffix_roster_hash" in _ABSENT_TOLERATED_CONFIG_KEYS


def test_the_roster_hash_moves_when_a_row_is_added(monkeypatch):
    """A row edit is a different instrument, and the resume guard must see it."""
    before = domain_suffix_roster_hash()
    monkeypatch.setitem(DOMAIN_SUFFIX_BY_LANG, "fr", "<fr suffix>")
    assert domain_suffix_roster_hash() != before
