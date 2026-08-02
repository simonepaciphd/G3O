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
)
from g3o.run import presweep as ps
from g3o.run.presweep import PresweepConfig, plan_run
from g3o.run.presweep.planning import _GUARDED_CONFIG_KEYS
from tests.test_discovery_chain import _patch_search, _Recorder, _rows

_COLUMNS = [
    "master_row_id", "country", "country_iso3", "government_level",
    "institution_type", "branch", "institution_name", "website",
    "disambiguation",
]


def _master(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "master.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        for i, r in enumerate(rows, start=1):
            base = {c: "" for c in _COLUMNS}
            base.update({"master_row_id": str(i), "branch": "executive"})
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


def test_evidence_roster_is_english_only():
    """A non-English row is a signed-off roster decision, not a code change.

    This test is the tripwire: it fails the moment someone adds a term without
    going through subprojects/multilingual-pipeline/. Update it in the same
    commit that carries the PI's row-by-row sign-off, never before.
    """
    assert EVIDENCE_TERMS_BY_LANG == {"en": "AI"}


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
    """A language rostered for legacy is not thereby runnable under chain."""
    lang = "fr"
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
    """Leg 1 is not localized, so English is always among the searched languages.

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
        (plan.run_dir / inst_id / "1b_discovery_site_restricted.json").read_text(
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
        (plan.run_dir / inst_id / "1b_discovery_site_restricted.json").read_text(
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
    """H3: leg 1's suffix is not localized, and its tag says so honestly."""
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
        (plan.run_dir / inst_id / "1a_discovery_general.json").read_text(
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
