"""Institution matcher tests — offline, on small synthetic master/ledger data.

Never reads the real 719,588-row master or the 720k-row key ledger (both are
read-only inputs/ data anyway, per CLAUDE.md) — InstitutionIndex is built
directly from a handful of MasterRow/LedgerEntry objects so these run in
milliseconds and exercise every tier and ledger-resolution edge case
deliberately, not whatever happens to be in the real data today.

Run:  .venv/bin/pytest -q
"""

from __future__ import annotations

import pytest

from pipeline.core.matcher import (
    InstitutionIndex, LedgerEntry, MasterRow, match_institution,
    normalize_name, registrable_domain,
)
from pipeline.core.models import InstitutionLink, InstitutionReview


def _row(uid, country="ESP", level="national", branch="bureaucratic", itype="ministry",
         name="Ministerio de Ejemplo", website="https://example.gob.es", duplicate="",
         disambiguation=""):
    return MasterRow(
        institution_uid=uid, country_iso3=country, government_level=level, branch=branch,
        institution_type=itype, institution_name=name,
        website_domain=registrable_domain(website), normalized_name=normalize_name(name),
        duplicate=duplicate, disambiguation=disambiguation,
    )


def _ledger(**entries) -> dict[str, LedgerEntry]:
    return {uid: LedgerEntry(status=status, merged_into_uid=merged)
            for uid, (status, merged) in entries.items()}


def _fields(record_id="r1", country_iso3="ESP", buyer_name="Ejemplo", buyer_url=None,
            buyer_national_id=None, buyer_email_domain=None, fetched_at="2026-08-29T00:00:00Z"):
    return dict(record_id=record_id, country_iso3=country_iso3, buyer_name=buyer_name,
                buyer_url=buyer_url, buyer_national_id=buyer_national_id,
                buyer_email_domain=buyer_email_domain, fetched_at=fetched_at)


# --------------------------------------------------------------------------- #
# normalization helpers
# --------------------------------------------------------------------------- #

def test_normalize_name_strips_boilerplate_accents_and_case():
    assert normalize_name("Ministerio de Educación") == "educacion"
    assert normalize_name("MINISTRY OF HEALTH") == "health"
    assert normalize_name("  Ayuntamiento  de   Ejemplo ") == "ayuntamiento de ejemplo"


def test_normalize_name_leaves_non_latin_script_untouched():
    """Spec §5's own example: the master's row 1 is Arabic-script. Routing it
    through a Latin-oriented transform must not corrupt it."""
    name = "د افغانستان بانک"
    assert normalize_name(name) == name.casefold()


def test_registrable_domain_normalizes_scheme_www_and_path():
    assert registrable_domain("https://www.example.gob.es/portal?x=1") == "example.gob.es"
    assert registrable_domain("example.gob.es") == "example.gob.es"
    assert registrable_domain("") == ""


# --------------------------------------------------------------------------- #
# tier 0 — country blocking
# --------------------------------------------------------------------------- #

def test_tier0_blocks_on_country_no_candidate_pool():
    index = InstitutionIndex([_row("G3O-I-00000001", country="ESP")],
                              _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, review = match_institution(_fields(country_iso3="FRA", buyer_name="Ejemplo"), index)
    assert link is None
    assert isinstance(review, InstitutionReview)
    assert review.reason == "no_candidate"


# --------------------------------------------------------------------------- #
# tier 1 — domain match
# --------------------------------------------------------------------------- #

def test_tier1_unique_domain_match_auto_accepts():
    index = InstitutionIndex(
        [_row("G3O-I-00000001", website="https://example.gob.es")],
        _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, review = match_institution(
        _fields(buyer_url="https://www.example.gob.es/tenders/1"), index)
    assert review is None
    assert isinstance(link, InstitutionLink)
    assert link.institution_uid == "G3O-I-00000001"
    assert link.match_method == "tier1_domain"
    assert link.confidence == "auto_accepted"
    assert link.match_score is None   # spec §5: deterministic tiers score null


def test_tier1_multiple_domain_hits_go_to_review():
    index = InstitutionIndex(
        [_row("G3O-I-00000001", name="A", website="https://dup.gob.es"),
         _row("G3O-I-00000002", name="B", website="https://dup.gob.es")],
        _ledger(**{"G3O-I-00000001": ("active", ""), "G3O-I-00000002": ("active", "")}),
        "mb-test")
    link, review = match_institution(_fields(buyer_url="https://dup.gob.es", buyer_name="Z"), index)
    assert link is None
    assert review.reason == "multiple_candidates"
    assert {c["institution_uid"] for c in review.candidates} == {
        "G3O-I-00000001", "G3O-I-00000002"}


# --------------------------------------------------------------------------- #
# tier 3 — exact normalized name
# --------------------------------------------------------------------------- #

def test_tier3_unique_exact_name_auto_accepts():
    index = InstitutionIndex(
        [_row("G3O-I-00000001", name="Ministerio de Educación")],
        _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, review = match_institution(_fields(buyer_name="MINISTERIO DE EDUCACIÓN"), index)
    assert review is None
    assert link.match_method == "tier3_exact_name"
    assert link.confidence == "auto_accepted"
    assert link.institution_uid == "G3O-I-00000001"


def test_tier3_multiple_exact_name_hits_go_to_review_not_a_guess():
    """The 'five Clay Counties' case (spec §5 / institution_keys.py docstring):
    identical normalized names must never be auto-resolved to one of them."""
    index = InstitutionIndex(
        [_row("G3O-I-00000001", country="USA", level="subnational", name="Clay County",
              disambiguation="KS"),
         _row("G3O-I-00000002", country="USA", level="subnational", name="Clay County",
              disambiguation="AL")],
        _ledger(**{"G3O-I-00000001": ("active", ""), "G3O-I-00000002": ("active", "")}),
        "mb-test")
    link, review = match_institution(_fields(country_iso3="USA", buyer_name="Clay County"), index)
    assert link is None
    assert review.reason == "multiple_candidates"
    assert len(review.candidates) == 2


def test_duplicate_flagged_row_never_auto_accepted():
    """spec §5: 'a matcher that ignores duplicate will resolve to rows already
    flagged as dupes.' A flagged row must not be the sole basis for auto-accept."""
    index = InstitutionIndex(
        [_row("G3O-I-00000001", name="Ministerio de Ejemplo", duplicate="true")],
        _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, review = match_institution(_fields(buyer_name="Ministerio de Ejemplo"), index)
    assert link is None
    # Falls through tiers 1/3 (excluded), picked up as a fuzzy (score 1.0) review candidate.
    assert review is not None
    assert review.candidates and review.candidates[0]["institution_uid"] == "G3O-I-00000001"


# --------------------------------------------------------------------------- #
# tier 4 — fuzzy, never auto-accepts
# --------------------------------------------------------------------------- #

def test_tier4_fuzzy_national_never_auto_accepts():
    index = InstitutionIndex(
        [_row("G3O-I-00000001", level="national", name="Ministerio de Educacion y Ciencia")],
        _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, review = match_institution(
        _fields(buyer_name="Ministerio de Educacion y Cencia"), index)   # typo'd
    assert link is None
    assert review.reason == "below_threshold"
    assert review.candidates[0]["match_method"] == "tier4_fuzzy_name"
    assert review.candidates[0]["match_score"] > 0


def test_tier4_fuzzy_subnational_without_corroboration_flagged_distinctly():
    index = InstitutionIndex(
        [_row("G3O-I-00000001", level="subnational", name="Municipio de San Miguel")],
        _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, review = match_institution(_fields(buyer_name="Municipio de San Migel"), index)
    assert link is None
    assert review.reason == "subnational_without_corroboration"


def test_tier4_fuzzy_subnational_with_domain_corroboration_still_does_not_auto_accept():
    """A corroborating signal changes the REASON recorded for review, but this
    module never auto-accepts on tier 4 regardless — the threshold is the PI's,
    not this code's, to set (see module docstring). The buyer's domain here is
    a genuine subdomain of the candidate's (not merely a sibling subdomain,
    which the matcher deliberately does NOT treat as corroboration)."""
    index = InstitutionIndex(
        [_row("G3O-I-00000001", level="subnational", name="Municipio de San Miguel",
              website="https://sanmiguel.gob.es")],
        _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, review = match_institution(
        _fields(buyer_name="Municipio de San Migel",
                buyer_url="https://tramites.sanmiguel.gob.es"), index)
    assert link is None
    assert review.reason == "below_threshold"   # corroborated, but still not auto-accepted


def test_no_name_or_domain_at_all_is_no_candidate():
    index = InstitutionIndex([_row("G3O-I-00000001")],
                              _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, review = match_institution(_fields(buyer_name=""), index)
    assert link is None
    assert review.reason == "no_candidate"


# --------------------------------------------------------------------------- #
# ledger resolution — never key off a uid alone
# --------------------------------------------------------------------------- #

def test_ledger_absent_status_is_still_live():
    """spec / PI reply memo: 'absent' is NOT dead — the institution keeps its
    uid and may reactivate. A match against an absent uid still resolves."""
    index = InstitutionIndex(
        [_row("G3O-I-00000001", website="https://example.gob.es")],
        _ledger(**{"G3O-I-00000001": ("absent", "")}), "mb-test")
    link, review = match_institution(_fields(buyer_url="https://example.gob.es"), index)
    assert review is None
    assert link.institution_uid == "G3O-I-00000001"
    assert link.ledger_status == "absent"
    assert link.resolved_from_uid is None


def test_ledger_follows_a_single_merge_to_the_live_target():
    index = InstitutionIndex(
        [_row("G3O-I-00000001", website="https://example.gob.es")],
        _ledger(**{
            "G3O-I-00000001": ("retired", "G3O-I-00000002"),
            "G3O-I-00000002": ("active", ""),
        }), "mb-test")
    link, review = match_institution(_fields(buyer_url="https://example.gob.es"), index)
    assert review is None
    assert link.institution_uid == "G3O-I-00000002"        # the LIVE target, not the retired original
    assert link.resolved_from_uid == "G3O-I-00000001"       # audit trail of what was actually matched
    assert link.ledger_status == "active"


def test_ledger_follows_a_multi_hop_merge_chain():
    index = InstitutionIndex(
        [_row("G3O-I-00000001", website="https://example.gob.es")],
        _ledger(**{
            "G3O-I-00000001": ("retired", "G3O-I-00000002"),
            "G3O-I-00000002": ("retired", "G3O-I-00000003"),
            "G3O-I-00000003": ("active", ""),
        }), "mb-test")
    link, _ = match_institution(_fields(buyer_url="https://example.gob.es"), index)
    assert link.institution_uid == "G3O-I-00000003"
    assert link.resolved_from_uid == "G3O-I-00000001"


def test_ledger_chain_that_never_reaches_live_goes_to_review_not_a_link():
    """A retired uid whose merge target is itself retired with no further
    pointer (a broken/incomplete chain) must never be silently written as a
    link — spec's own emphasis: never key to a uid the ledger cannot stand
    behind."""
    index = InstitutionIndex(
        [_row("G3O-I-00000001", website="https://example.gob.es")],
        _ledger(**{
            "G3O-I-00000001": ("retired", "G3O-I-00000002"),
            "G3O-I-00000002": ("retired", ""),   # dead end
        }), "mb-test")
    link, review = match_institution(_fields(buyer_url="https://example.gob.es"), index)
    assert link is None
    assert review.reason == "ledger_status_not_active"


def test_ledger_cycle_guard_never_hangs_or_links():
    index = InstitutionIndex(
        [_row("G3O-I-00000001", website="https://example.gob.es")],
        _ledger(**{
            "G3O-I-00000001": ("retired", "G3O-I-00000002"),
            "G3O-I-00000002": ("retired", "G3O-I-00000001"),   # cycle
        }), "mb-test")
    link, review = match_institution(_fields(buyer_url="https://example.gob.es"), index)
    assert link is None
    assert review.reason == "ledger_status_not_active"


def test_uid_missing_from_ledger_entirely_goes_to_review():
    index = InstitutionIndex([_row("G3O-I-00000001", website="https://example.gob.es")],
                              {}, "mb-test")   # empty ledger
    link, review = match_institution(_fields(buyer_url="https://example.gob.es"), index)
    assert link is None
    assert review.reason == "ledger_status_not_active"


# --------------------------------------------------------------------------- #
# every returned object is schema-shaped (so upsert_link/upsert_review would accept it)
# --------------------------------------------------------------------------- #

def test_resolved_link_has_every_field_upsert_link_needs():
    from pipeline.core.store import StagingStore
    index = InstitutionIndex(
        [_row("G3O-I-00000001", website="https://example.gob.es")],
        _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    link, _ = match_institution(_fields(buyer_url="https://example.gob.es"), index)

    store = StagingStore("outputs/staging")   # not connected; validate() only reads schema
    store.validate("links", link.to_dict())   # raises ValidationError on any mismatch


def test_review_row_has_every_field_upsert_review_needs():
    from pipeline.core.store import StagingStore
    index = InstitutionIndex([_row("G3O-I-00000001")],
                              _ledger(**{"G3O-I-00000001": ("active", "")}), "mb-test")
    _, review = match_institution(_fields(country_iso3="FRA"), index)

    store = StagingStore("outputs/staging")
    store.validate("review", review.to_dict())
