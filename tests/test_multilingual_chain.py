"""Multilingual chain: fail-loud language validation + per-language leg 2.

Implements roadmap A7 (fail loud on unrostered languages) and its chain-mode
sibling — the divergence where a run configured ``discovery_languages=("zh",)``
issued English queries while ``institution_search_languages`` reported ``zh``.
That divergence was reproduced on a live artifact before this change; the tests
below pin the closed state and the reason it stays closed.

PI decisions this file encodes (2026-08-02):

- **A7 → fail loud, both modes.** Not an opt-in flag: a flag preserves the
  failure mode behind something someone will eventually set.
- **Leg 1 stays English and unparameterized.** So chain mode always searches
  English *in addition to* the configured languages, and the provenance string
  has to say so rather than hide it.

  **Reversed 2026-09-01** — leg 1 now issues one query per language the
  institution's policy row names, behind ``discovery_leg1_multilingual``, which
  defaults False and cannot be enabled until the leg-1 suffix roster is signed.
  The tests in this file pin the *default*, which is unchanged and is what
  production runs; ``tests/test_leg1_multilingual.py`` covers the other side of
  the flag.
- **The scalar ``discovery_evidence_term`` is shorthand**, not a competing
  surface; setting both it and the mapping is an error, not a precedence rule.

Everything here is mocked. No non-English term ships in the repo — the roster
is seeded English-only, and rows are added only through a signed-off proposal
(roadmap A2/B3).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from g3o.discovery.query_builder import (
    DOMAIN_QUERY_LANG,
    DOMAIN_QUERY_SUFFIX,
    EVIDENCE_TERMS_BY_LANG,
    GENAI_TERMS_BY_LANG,
    UnknownLanguageError,
    evidence_terms_roster_hash,
)
from g3o.run import presweep as ps
from g3o.run.presweep import PresweepConfig, plan_run
from g3o.run.presweep.planning import _GUARDED_CONFIG_KEYS
from tests._layout import inst_dir as inst_dir_of
from tests.test_discovery_chain import _patch_search, _Recorder, _rows

_COLUMNS = [
    "institution_uid", "master_row_id", "country", "country_iso3",
    "government_level", "institution_type", "branch", "institution_name",
    "website", "disambiguation",
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
            })
            base.update(r)
            w.writerow(base)
    return path


def _config(tmp_path: Path, **kw: Any) -> PresweepConfig:
    return PresweepConfig(
        run_id="ml-test",
        runs_dir=tmp_path / "runs",
        master_csv=_master(tmp_path, _rows(1)),
        sample_size=1,
        seed=22294,
        dry_run=True,
        **kw,
    )


# ---------------------------------------------------------------------------
# The roster ships English-only
# ---------------------------------------------------------------------------


def test_evidence_roster_is_the_signed_roster_of_2026_08_31():
    """A roster row is a signed decision, not a code change.

    The tripwire this replaces asserted the roster was English-only, and it went
    red exactly when it was supposed to: on 2026-08-31, in the commit carrying
    the PI's sign-off on all 90 rows
    (``agent-workspace/2026-08-31-multilingual-readiness/SIGNABLE-ROSTER-90.md``).
    It is not deleted, it is re-pointed: the fingerprint pins what was signed, so
    editing a signed term still cannot pass as a refactor. Moving this hash is
    the same deliberate act as moving ``language_policy_hash`` was on 2026-08-30,
    and it needs the same paperwork.
    """
    assert evidence_terms_roster_hash() == "a5d45bb1175c03a9"
    assert len(EVIDENCE_TERMS_BY_LANG) == 90
    assert EVIDENCE_TERMS_BY_LANG["en"] == "AI"
    # Three rows that carry the reasoning, one per class.
    # A: the sub-national floor. B1: on probation, measured at zero marginal.
    # C: never reached at sub-national tier, drafted native phrase.
    assert EVIDENCE_TERMS_BY_LANG["id"] == "kecerdasan buatan"
    assert EVIDENCE_TERMS_BY_LANG["hi"] == "कृत्रिम बुद्धिमत्ता"
    assert EVIDENCE_TERMS_BY_LANG["cy"] == "deallusrwydd artiffisial"


def test_no_signed_term_is_a_homograph_token():
    """The construction rule, asserted rather than trusted.

    Every signed term is a native multi-character phrase: whitespace, or length
    >= 4 and not one of the eleven ambiguous tokens. This is what keeps Hungarian
    ``MI`` (the pronoun that outranked the real term on raw volume), ``IA`` (the
    *ia* in *media*/*social*) and bare ``ai`` (the French verb) out of the
    instrument, and it is why ``tr`` carries ``yapay zeka`` rather than the
    measured winner ``YZ``.
    """
    homographs = {"AI", "DI", "IA", "KI", "MI", "SI", "UI", "YZ", "ΤΝ", "ИИ", "ШІ"}
    for lang, term in EVIDENCE_TERMS_BY_LANG.items():
        if lang == "en":
            continue  # the control is deliberately the bare token
        assert " " in term or (len(term) >= 4 and term not in homographs), lang


# ---------------------------------------------------------------------------
# A7 — fail loud, both modes, at construction
# ---------------------------------------------------------------------------


def test_chain_config_rejects_a_language_with_no_evidence_term(tmp_path):
    """`zh` is in the legacy roster but has no evidence term, so chain rejects it.

    This is the divergence closed by construction: the config that produced
    English queries under a `zh` provenance label can no longer be built.
    """
    with pytest.raises(UnknownLanguageError) as exc:
        _config(tmp_path, discovery_mode="chain", discovery_languages=("zh",))
    assert "zh" in str(exc.value)


def test_legacy_config_rejects_a_language_with_no_term_roster(tmp_path):
    with pytest.raises(UnknownLanguageError):
        _config(tmp_path, discovery_mode="legacy", discovery_languages=("xx",))


def test_legacy_config_still_accepts_its_ten_rostered_languages(tmp_path):
    """Fail-loud must not narrow legacy mode: every existing roster key works."""
    cfg = _config(
        tmp_path,
        discovery_mode="legacy",
        discovery_languages=tuple(GENAI_TERMS_BY_LANG),
    )
    assert set(cfg.discovery_languages) == set(GENAI_TERMS_BY_LANG)


def test_the_two_rosters_are_not_interchangeable(tmp_path):
    """A language rostered for legacy is not thereby runnable under chain.

    Carried on ``zh`` since 2026-08-31. It used to be carried on ``fr``, which
    the signed roster now covers -- but the point survives the roster growing,
    because the signed policy expresses Chinese as ``zh-hans``/``zh-hant`` (the
    tag selects the term: 人工智能 and 人工智慧 genuinely differ), while the legacy
    roster still carries bare ``zh``. The two rosters remain different surfaces.
    """
    lang = "zh"
    assert lang in GENAI_TERMS_BY_LANG
    assert lang not in EVIDENCE_TERMS_BY_LANG
    _config(tmp_path, discovery_mode="legacy", discovery_languages=(lang,))
    with pytest.raises(UnknownLanguageError):
        _config(tmp_path, discovery_mode="chain", discovery_languages=(lang,))


def test_a_signed_off_term_makes_the_language_runnable(tmp_path):
    """The intended path once a roster row is signed off.

    Passed as config here rather than by editing the module constant, so the
    test demonstrates the mechanism without shipping a term.
    """
    cfg = _config(
        tmp_path,
        discovery_mode="chain",
        discovery_languages=("en", "zh"),
        discovery_evidence_terms={"en": "AI", "zh": "大模型"},
    )
    assert cfg.evidence_terms == {"en": "AI", "zh": "大模型"}


# ---------------------------------------------------------------------------
# The scalar is shorthand, not a second surface
# ---------------------------------------------------------------------------


def test_scalar_desugars_into_the_mapping(tmp_path):
    cfg = _config(tmp_path, discovery_mode="chain", discovery_evidence_term="IA")
    assert cfg.evidence_terms == {"en": "IA"}


def test_default_config_is_unchanged_by_the_new_surface(tmp_path):
    """The n=200 confirmation run's configuration must still reproduce exactly."""
    cfg = _config(tmp_path)
    assert cfg.discovery_mode == "chain"
    assert cfg.evidence_terms == {"en": "AI"}
    assert cfg.institution_search_languages == "en"


def test_setting_both_surfaces_is_an_error(tmp_path):
    """No silent precedence rule over which token every leg-2 query carries."""
    with pytest.raises(ValueError, match="not\nboth|not both"):
        _config(
            tmp_path,
            discovery_mode="chain",
            discovery_evidence_term="IA",
            discovery_evidence_terms={"en": "AI"},
        )


def test_evidence_terms_follow_configured_language_order(tmp_path):
    cfg = _config(
        tmp_path,
        discovery_mode="chain",
        discovery_languages=("zh", "en"),
        discovery_evidence_terms={"en": "AI", "zh": "大模型"},
    )
    assert list(cfg.evidence_terms) == ["zh", "en"]


# ---------------------------------------------------------------------------
# Provenance — the divergence B0 reproduced live
# ---------------------------------------------------------------------------


def test_chain_provenance_includes_english_because_leg_1_is_english(tmp_path):
    """Leg 1 is English by default, so English is always among the searched languages.

    The alternative — reporting only `zh` — would be the same lie the old
    derivation told, just in the other direction.
    """
    cfg = _config(
        tmp_path,
        discovery_mode="chain",
        discovery_languages=("zh",),
        discovery_evidence_terms={"zh": "大模型"},
    )
    assert cfg.chain_query_languages == ("en", "zh")
    assert cfg.institution_search_languages == "en,zh"


def test_chain_provenance_does_not_duplicate_english(tmp_path):
    cfg = _config(tmp_path, discovery_mode="chain", discovery_languages=("en",))
    assert cfg.chain_query_languages == ("en",)
    assert cfg.institution_search_languages == "en"


def test_legacy_provenance_is_unchanged(tmp_path):
    """Legacy mode issues no English leg of its own, so nothing is added."""
    cfg = _config(
        tmp_path, discovery_mode="legacy", discovery_languages=("fr", "de")
    )
    assert cfg.institution_search_languages == "fr,de"


# ---------------------------------------------------------------------------
# Leg 2 issues one query per language, each tagged with its own code
# ---------------------------------------------------------------------------


def test_leg_2_issues_one_tagged_query_per_language(tmp_path, monkeypatch):
    cfg = _config(
        tmp_path,
        discovery_mode="chain",
        discovery_languages=("en", "zh"),
        discovery_evidence_terms={"en": "AI", "zh": "大模型"},
    )
    plan = plan_run(cfg)
    inst_id = ps.synth_institution_id(plan.sample[0])
    rec = _Recorder()
    _patch_search(monkeypatch, rec)

    ps._run_discovery_site_restricted(
        plan.run_dir, plan.sample, {inst_id: "https://example.gov/"},
        languages=cfg.discovery_languages, num_results=10, mode="chain",
        evidence_terms=cfg.evidence_terms,
    )

    assert rec.queries == ["site:example.gov AI", "site:example.gov 大模型"]

    import json
    artifact = json.loads(
        (inst_dir_of(plan.run_dir, inst_id) / "1b_discovery_site_restricted.json").read_text(
            encoding="utf-8"
        )
    )
    assert [q["language"] for q in artifact["queries"]] == ["en", "zh"]


def test_a_url_found_by_two_languages_is_attributed_to_the_first_only(
    tmp_path, monkeypatch
):
    """KNOWN LIMITATION, pinned rather than fixed. Open for PI decision.

    Leg 2 dedupes records by URL across queries, so a page surfaced by both the
    English and the Chinese query is recorded once, tagged with whichever
    language ran first. ``compute_language_breakdown()`` therefore *undercounts*
    the later language on exactly the overlap — and the Chinese directional
    probe found only 2 of 9 hosts overlapping, so the overlap is real but not
    dominant.

    Not fixed here because every option changes what "URLs found in language X"
    means: keep first-wins (URL counts unchanged, attribution biased), record
    the full language set per URL (schema change, ``health._in_lang`` reads a
    scalar), or stop deduping across languages (inflates the URL count Stage 3
    consumes). That is a measurement-semantics call, not plumbing.

    It cannot bite today: it needs two configured languages, which needs a
    signed-off roster row.
    """
    import json

    cfg = _config(
        tmp_path,
        discovery_mode="chain",
        discovery_languages=("en", "zh"),
        discovery_evidence_terms={"en": "AI", "zh": "大模型"},
    )
    plan = plan_run(cfg)
    inst_id = ps.synth_institution_id(plan.sample[0])
    # Same single link returned to both queries — the full-overlap case.
    _patch_search(monkeypatch, _Recorder(links=["https://example.gov/a"]))

    ps._run_discovery_site_restricted(
        plan.run_dir, plan.sample, {inst_id: "https://example.gov/"},
        languages=cfg.discovery_languages, num_results=10, mode="chain",
        evidence_terms=cfg.evidence_terms,
    )

    artifact = json.loads(
        (inst_dir_of(plan.run_dir, inst_id) / "1b_discovery_site_restricted.json").read_text(
            encoding="utf-8"
        )
    )
    # Both queries were issued and both are recorded in provenance...
    assert len(artifact["queries"]) == 2
    # ...but the shared URL carries only the first language's tag.
    assert [r["language"] for r in artifact["records"]] == ["en"]


def test_leg_2_credit_cost_scales_with_languages(tmp_path, monkeypatch):
    """The cost note the PI needs in every artifact: n languages = n credits."""
    cfg = _config(
        tmp_path,
        discovery_mode="chain",
        discovery_languages=("en", "zh", "ja"),
        discovery_evidence_terms={"en": "AI", "zh": "z", "ja": "j"},
    )
    plan = plan_run(cfg)
    inst_id = ps.synth_institution_id(plan.sample[0])
    rec = _Recorder()
    _patch_search(monkeypatch, rec)
    ps._run_discovery_site_restricted(
        plan.run_dir, plan.sample, {inst_id: "https://example.gov/"},
        languages=cfg.discovery_languages, num_results=10, mode="chain",
        evidence_terms=cfg.evidence_terms,
    )
    assert len(rec.queries) == len(cfg.discovery_languages)


def test_leg_1_stays_one_english_query_whatever_the_languages(tmp_path, monkeypatch):
    """H3: leg 1 issues one English query by default, and tags it honestly.

    The PI reversed the 2026-08-02 un-localized-suffix decision on 2026-09-01, so
    leg 1 *can* now be localized — but only behind
    ``discovery_leg1_multilingual``, which defaults False and cannot be turned on
    until the suffix roster is signed. This test pins the default, which is the
    behaviour production runs: whatever ``discovery_languages`` says, and whatever
    leg 2 does with it, leg 1 issues exactly one query and tags it ``en``.
    ``test_leg_1_localizes_per_policy_language_when_the_flag_is_on`` is its
    counterpart on the other side of the flag.
    """
    cfg = _config(
        tmp_path,
        discovery_mode="chain",
        discovery_languages=("en", "zh"),
        discovery_evidence_terms={"en": "AI", "zh": "大模型"},
    )
    plan = plan_run(cfg)
    inst_id = ps.synth_institution_id(plan.sample[0])
    rec = _Recorder()
    _patch_search(monkeypatch, rec)

    ps._run_discovery_general(
        plan.run_dir, plan.sample,
        languages=cfg.discovery_languages, num_results=10, mode="chain",
    )

    assert len(rec.queries) == 1
    assert rec.queries[0].endswith(DOMAIN_QUERY_SUFFIX)

    import json
    artifact = json.loads(
        (inst_dir_of(plan.run_dir, inst_id) / "1a_discovery_general.json").read_text(
            encoding="utf-8"
        )
    )
    assert [q["language"] for q in artifact["queries"]] == [DOMAIN_QUERY_LANG]


# ---------------------------------------------------------------------------
# Manifest guard (F7 / A4 family)
# ---------------------------------------------------------------------------


def test_chain_query_keys_are_guarded_on_resume():
    """A run started in chain mode must not be resumable in legacy mode.

    These keys were written to manifest.json from the day the chain shipped but
    never compared, so the guard passed clean across a mode flip — a different
    instrument and a different credit cost, silently mixed into one run.
    """
    for key in (
        "discovery_mode",
        "discovery_evidence_term",
        "discovery_evidence_terms",
        "discovery_domain_quote_name",
        "serper_autocorrect",
    ):
        assert key in _GUARDED_CONFIG_KEYS


def test_resume_guard_trips_on_a_mode_flip(tmp_path):
    """Non-vacuous: the guard actually raises, not merely lists the key."""
    import json

    from g3o.common.run_state import state_dir
    from g3o.run.presweep.planning import (
        _assert_manifest_matches_on_resume,
        build_manifest,
    )

    cfg = _config(tmp_path, discovery_mode="chain")
    plan = plan_run(cfg)
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)

    resumed = _config(tmp_path, discovery_mode="legacy")
    fresh = build_manifest(resumed, plan.sample)

    with pytest.raises(RuntimeError, match="discovery_mode"):
        _assert_manifest_matches_on_resume(plan.run_dir, fresh)

    # Sanity: the manifest on disk really did record chain mode.
    on_disk = json.loads((plan.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["config"]["discovery_mode"] == "chain"

    # Negative control — the guard is discriminating, not raising on everything.
    same = build_manifest(_config(tmp_path, discovery_mode="chain"), plan.sample)
    _assert_manifest_matches_on_resume(plan.run_dir, same)


# ---------------------------------------------------------------------------
# Roster provenance — GENAI_TERMS_BY_LANG is a constant, so the manifest has to
# carry a fingerprint of it for the guard to have anything to compare
# ---------------------------------------------------------------------------


def test_roster_hash_is_guarded():
    assert "genai_terms_roster_hash" in _GUARDED_CONFIG_KEYS


def test_roster_hash_is_stable_across_calls():
    from g3o.discovery.query_builder import genai_terms_roster_hash

    assert genai_terms_roster_hash() == genai_terms_roster_hash()


def test_roster_hash_ignores_dict_key_order(monkeypatch):
    """Deterministic key ordering: the source literal's order cannot leak in."""
    from g3o.discovery import query_builder as qb

    before = qb.genai_terms_roster_hash()
    monkeypatch.setattr(
        qb, "GENAI_TERMS_BY_LANG", dict(reversed(list(qb.GENAI_TERMS_BY_LANG.items())))
    )
    assert qb.genai_terms_roster_hash() == before


def test_roster_hash_covers_languages_this_run_never_queries(monkeypatch):
    """The fingerprint is over the whole roster, not this run's language subset.

    A term added to ``fr`` moves the hash even for an English-only run: the
    roster is one instrument, versioned as a whole, and pinning only the
    languages a run happens to query would let the rest drift unrecorded.
    """
    from g3o.discovery import query_builder as qb

    before = qb.genai_terms_roster_hash()
    widened = {lang: list(terms) for lang, terms in qb.GENAI_TERMS_BY_LANG.items()}
    widened["fr"] = [*widened["fr"], "assistant IA"]
    monkeypatch.setattr(qb, "GENAI_TERMS_BY_LANG", widened)
    assert qb.genai_terms_roster_hash() != before


def test_roster_hash_moves_on_a_reordering(monkeypatch):
    """Deliberate: term order is part of the roster's identity.

    Sorting the per-language lists before hashing would make a reorder hash
    identically and slip past the guard. Reordering is still a roster edit, so
    it trips.
    """
    from g3o.discovery import query_builder as qb

    before = qb.genai_terms_roster_hash()
    reordered = {lang: list(terms) for lang, terms in qb.GENAI_TERMS_BY_LANG.items()}
    reordered["en"] = list(reversed(reordered["en"]))
    monkeypatch.setattr(qb, "GENAI_TERMS_BY_LANG", reordered)
    assert qb.genai_terms_roster_hash() != before


def test_resume_guard_trips_on_a_roster_edit(tmp_path, monkeypatch):
    """Non-vacuous: an edited roster aborts the resume it would have changed."""
    import json

    from g3o.common.run_state import state_dir
    from g3o.discovery import query_builder as qb
    from g3o.run.presweep.planning import (
        _assert_manifest_matches_on_resume,
        build_manifest,
    )

    cfg = _config(tmp_path)
    plan = plan_run(cfg)
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)

    on_disk = json.loads((plan.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["config"]["genai_terms_roster_hash"] == qb.genai_terms_roster_hash()

    edited = {lang: list(terms) for lang, terms in qb.GENAI_TERMS_BY_LANG.items()}
    edited["en"] = [*edited["en"], "AI copilot"]
    monkeypatch.setattr(qb, "GENAI_TERMS_BY_LANG", edited)

    with pytest.raises(RuntimeError, match="genai_terms_roster_hash"):
        _assert_manifest_matches_on_resume(plan.run_dir, build_manifest(cfg, plan.sample))


def _drop_config_key(run_dir: Path, key: str) -> None:
    """Rewrite manifest.json as one written before ``key`` existed."""
    import json

    path = run_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["config"][key]
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def test_resume_guard_tolerates_a_manifest_predating_the_roster_hash(tmp_path):
    """Runs launched before the fingerprint shipped stay resumable (PI, 2026-08-04).

    Their manifests cannot carry a key that did not exist yet. Tolerating the
    absence is the concession run_generation_parameters already makes; the
    alternative pressures operators into hand-editing manifests, which defeats
    every other guarded key at once.
    """
    from g3o.common.run_state import state_dir
    from g3o.run.presweep.planning import (
        _assert_manifest_matches_on_resume,
        build_manifest,
    )

    cfg = _config(tmp_path)
    plan = plan_run(cfg)
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)
    _drop_config_key(plan.run_dir, "genai_terms_roster_hash")

    # No raise: absent is not "differs".
    _assert_manifest_matches_on_resume(plan.run_dir, build_manifest(cfg, plan.sample))


def test_absence_tolerance_does_not_leak_to_other_guarded_keys(tmp_path):
    """The exception is enumerated, not open.

    A manifest predating the chain keys must still refuse to resume — otherwise
    tolerating absence would reopen the mode-flip hole the chain guard closed.

    The set is asserted by exact equality so any *new* member has to be added
    here deliberately. It grew from one key to two on 2026-08-26 (issue #96):
    ``scrape_max_institution_seconds`` is the first key to use the mechanism for
    what its own comment describes — a guarded key added to a manifest schema
    that real, resumable runs predate. That is the intended use and does not
    weaken this test; a fourth key still trips it.

    It grew to three on 2026-08-31 for the same documented reason:
    ``evidence_terms_roster_hash`` did not exist until the chain-mode roster did,
    so every manifest ever written lacks it, including the published runs.

    It grew to four on 2026-09-01, once more for that reason:
    ``domain_suffix_roster_hash`` did not exist until leg 1 had a roster, and every
    run that predates it issued the English suffix by construction — there is no
    instrument ambiguity for the guard to protect against on those runs, so
    refusing to resume them would be a cost with no safety gain.
    """
    from g3o.common.run_state import state_dir
    from g3o.run.presweep.planning import (
        _ABSENT_TOLERATED_CONFIG_KEYS,
        _assert_manifest_matches_on_resume,
        build_manifest,
    )

    assert _ABSENT_TOLERATED_CONFIG_KEYS == {
        "genai_terms_roster_hash",
        "scrape_max_institution_seconds",
        "evidence_terms_roster_hash",
        "domain_suffix_roster_hash",
    }

    cfg = _config(tmp_path)
    plan = plan_run(cfg)
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)
    _drop_config_key(plan.run_dir, "discovery_mode")

    with pytest.raises(RuntimeError, match="discovery_mode"):
        _assert_manifest_matches_on_resume(plan.run_dir, build_manifest(cfg, plan.sample))
