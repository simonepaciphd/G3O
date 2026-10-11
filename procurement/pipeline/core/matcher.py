"""Institution matcher (spec §5) — resolve a procurement buyer to the G3O
institution master. Read-only consumer of the master and its key ledger; never
writes to either (that is the Master Database Team's job, not this
subproject's — see CLAUDE.md's read-only paths).

Tiers implemented here, per spec §5's table:

  Tier 0 — block on country_iso3. Non-negotiable precondition for every tier.
  Tier 1 — registrable-domain match of the buyer's URL/email domain against
           the master's `website`. Deterministic (spec: match_score null).
  Tier 2 — national registry id. CONFIRMED UNREACHABLE (PI, Q5b, 2026-08-04):
           the master carries no such column (17 columns, none a registry id).
           Always skipped; traffic falls through to tiers 3-5.
  Tier 3 — normalized exact name, sub-blocked on government_level +
           institution_type. Deterministic (spec: match_score null).
  Tier 4 — fuzzy name, same sub-blocking. Requires a corroborating signal for
           any SUBNATIONAL match (spec §5 — the master is ~719k rows,
           overwhelmingly subnational, and same-named municipalities are
           normal). NEVER AUTO-ACCEPTS in this module: the auto-accept
           threshold is explicitly a PI item, "set from the validation sample,
           not from a default" (implementation-roadmap.md, Phase 1). Every
           fuzzy candidate is surfaced to institution_review with its score
           instead, so a human decides and the eventual threshold can be set
           by measuring against real reviewer decisions — not guessed here.
  Tier 5 — human review queue (institution_review.schema.json). Everything
           that does not clear tier 1 or tier 3 lands here: no candidate,
           multiple candidates, every tier-4 fuzzy hit, and a resolved uid the
           ledger cannot currently stand behind.

Auto-accept is restricted to tiers 1 and 3 ONLY, and only when exactly one
candidate survives country + sub-block filtering. A tie (more than one
candidate) is never guessed at — it goes to review with every candidate
listed, per spec §5's own caution about subnational collisions and the
master's `duplicate` column.

LEDGER RESOLUTION (spec §5, CLAUDE.md, the PI's 2026-08-04 reply memo): a
match is resolved THROUGH THE LEDGER at read time, never from a uid alone.
'absent' is a LIVE status — the institution keeps its uid and may reactivate
in a later build; only 'retired' is terminal, and a retired uid's
`merged_into_uid` chain is followed to whatever live uid it resolves to,
depth-guarded at 16 to match `institution_keys.py`'s own guard (the ledger's
own invariants already forbid a longer chain or a cycle, but this module does
not trust that blindly — see `InstitutionIndex.resolve_ledger`). If the chain
cannot reach a live uid, the match is NOT written as a link; it goes to review
instead (reason `ledger_status_not_active`).
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlsplit

from .models import InstitutionLink, InstitutionReview

MATCHER_VERSION = "matcher/tiers-0-1-3-4-5@0.1"

MERGE_CHAIN_MAX_DEPTH = 16   # matches inputs/G3O_Institution_Master/scripts/python/institution_keys.py
_LIVE_STATUSES = {"active", "absent"}

# Tier-3/4 name normalization (spec §5: "casefold, strip diacritics, strip
# legal/administrative boilerplate"). Latin-script only by construction: NFKD
# decomposition + combining-mark strip is a no-op on non-Latin scripts, so a
# native-script name (spec's own example: row 1 is Arabic-script) passes through
# unchanged rather than being corrupted by a Latin-oriented transform.
_LEGAL_BOILERPLATE = (
    "ministerio de", "ministerio del", "ministerio para",
    "ministry of", "ministère de", "ministério de", "ministério do",
    "municipio de", "municipalidad de", "município de", "municipality of",
    "gobierno de", "government of", "governo de", "governo do",
    "república de", "republic of", "república federativa de",
    "office of the", "oficina de",
)

_WS_RE = re.compile(r"\s+")

# Below this, a fuzzy candidate is noise, not a candidate worth putting in
# front of a reviewer. This is a relevance FLOOR, not an accept threshold — it
# never causes an auto-accept; see the module docstring.
_FUZZY_REVIEW_FLOOR = 0.60
_FUZZY_MAX_CANDIDATES = 5


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    """Spec §5 tier 3: casefold, fold accents, collapse whitespace, strip one
    leading legal/administrative boilerplate phrase."""
    if not name:
        return ""
    s = _strip_accents(name).casefold()
    s = _WS_RE.sub(" ", s).strip()
    for prefix in _LEGAL_BOILERPLATE:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    return s


def registrable_domain(url_or_domain: str) -> str:
    """Registrable domain, so 'https://www.example.gov.ar/foo?x=1' and
    'example.gov.ar' compare equal. No public-suffix-list lookup (out of scope
    for this pilot) — this is host normalization, not eTLD+1 computation."""
    if not url_or_domain:
        return ""
    s = url_or_domain.strip().casefold()
    if "://" not in s:
        s = "//" + s
    parts = urlsplit(s)
    host = (parts.netloc or parts.path).split(":")[0].strip("/")
    if host.startswith("www."):
        host = host[4:]
    return host


@dataclass(frozen=True)
class MasterRow:
    """One institution master row, pre-normalized once at load time (the
    master is ~719k rows; normalizing per-comparison would be wasteful)."""
    institution_uid: str
    country_iso3: str
    government_level: str
    branch: str
    institution_type: str
    institution_name: str
    website_domain: str
    normalized_name: str
    duplicate: str
    disambiguation: str


@dataclass(frozen=True)
class LedgerEntry:
    status: str
    merged_into_uid: str


def _master_row_from_csv(r: dict) -> MasterRow:
    name = r.get("institution_name") or ""
    return MasterRow(
        institution_uid=r["institution_uid"],
        country_iso3=(r.get("country_iso3") or "").strip().upper(),
        government_level=(r.get("government_level") or "").strip(),
        branch=(r.get("branch") or "").strip(),
        institution_type=(r.get("institution_type") or "").strip(),
        institution_name=name,
        website_domain=registrable_domain(r.get("website") or ""),
        normalized_name=normalize_name(name),
        duplicate=(r.get("duplicate") or "").strip(),
        disambiguation=(r.get("disambiguation") or "").strip(),
    )


class InstitutionIndex:
    """Read-only in-memory index over the institution master + key ledger.

    Build once per run (the master is large) and reuse across every record.
    Never mutates either source file.
    """

    def __init__(self, master_rows: Iterable[MasterRow], ledger: dict[str, LedgerEntry],
                 master_build_id: str):
        self.master_build_id = master_build_id
        self._ledger = ledger
        self._by_country: dict[str, list[MasterRow]] = {}
        for row in master_rows:
            self._by_country.setdefault(row.country_iso3, []).append(row)

    @classmethod
    def load(cls, master_csv: Path, ledger_csv: Path) -> "InstitutionIndex":
        """Read the real files. Read-only: opens with mode 'r' only, never 'w'/'a'."""
        master_rows: list[MasterRow] = []
        build_id = ""
        with open(master_csv, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                build_id = r.get("master_build_id") or build_id
                master_rows.append(_master_row_from_csv(r))

        ledger: dict[str, LedgerEntry] = {}
        with open(ledger_csv, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                ledger[r["institution_uid"]] = LedgerEntry(
                    status=(r.get("status") or "").strip(),
                    merged_into_uid=(r.get("merged_into_uid") or "").strip(),
                )
        return cls(master_rows, ledger, build_id)

    def candidates_for_country(self, country_iso3: str) -> list[MasterRow]:
        """Tier 0."""
        return self._by_country.get((country_iso3 or "").strip().upper(), [])

    def resolve_ledger(self, uid: str) -> tuple[Optional[str], str, Optional[str]]:
        """Follow `uid` through the ledger to a live identity.

        Returns (resolved_uid_or_None, status_at_original_uid, resolved_from_uid).
        `resolved_from_uid` is set only when a merge chain was actually followed.
        None in the first slot means the ledger cannot currently stand behind
        this uid (unknown uid, or a chain that does not terminate live within
        the depth guard) — the caller must not write a link for it.
        """
        entry = self._ledger.get(uid)
        if entry is None:
            return None, "unknown", None
        if entry.status in _LIVE_STATUSES:
            return uid, entry.status, None
        if entry.status != "retired":
            return None, entry.status, None

        seen = {uid}
        cur = uid
        for _ in range(MERGE_CHAIN_MAX_DEPTH):
            step = self._ledger.get(cur)
            if step is None or not step.merged_into_uid:
                return None, entry.status, None
            cur = step.merged_into_uid
            if cur in seen:
                return None, entry.status, None   # cycle guard — should not happen on a valid ledger
            seen.add(cur)
            tgt = self._ledger.get(cur)
            if tgt is None:
                return None, entry.status, None
            if tgt.status in _LIVE_STATUSES:
                return cur, tgt.status, uid
            if tgt.status != "retired":
                return None, entry.status, None
        return None, entry.status, None   # exceeded depth guard


def _fuzzy_score(a: str, b: str) -> float:
    """stdlib difflib similarity in [0, 1]. Used only to RANK and SURFACE
    candidates for human review (module docstring) — never to auto-accept."""
    return SequenceMatcher(None, a, b).ratio()


def _corroborating_signal(record_fields: dict, candidate: MasterRow) -> Optional[str]:
    """A second signal beyond name similarity, required for any subnational
    tier-4 match (spec §5). The only signal this pipeline can compute today is
    a buyer domain that overlaps the candidate's website domain — there is no
    national-registry id to check (tier 2 is unreachable)."""
    buyer_domain = registrable_domain(
        record_fields.get("buyer_url") or record_fields.get("buyer_email_domain") or "")
    if buyer_domain and candidate.website_domain and (
            buyer_domain == candidate.website_domain
            or buyer_domain.endswith("." + candidate.website_domain)
            or candidate.website_domain.endswith("." + buyer_domain)):
        return f"domain:{buyer_domain}"
    return None


def _candidate_dict(row: MasterRow, method: str, score: Optional[float] = None) -> dict:
    return {
        "institution_uid": row.institution_uid,
        "institution_name": row.institution_name,
        "match_method": method,
        "match_score": round(score, 4) if score is not None else None,
        "matched_on": row.normalized_name or row.website_domain or None,
        "ledger_status": None,   # filled by the caller if/when it looks it up
        "key_level": None,
    }


def match_institution(record_fields: dict, index: InstitutionIndex) -> tuple[
        Optional[InstitutionLink], Optional[InstitutionReview]]:
    """Resolve one procurement record's buyer to a G3O institution.

    Returns exactly one of (InstitutionLink, None) — a resolved, ledger-live
    match — or (None, InstitutionReview) — everything else. `role` is always
    `contracting_authority`: spec §6.3's framework attribution
    (central_purchasing_body vs. calling-off institution) is an activity-level
    decision made downstream of staging, not decided per-record here.

    `record_fields` reads: record_id, country_iso3, buyer_name, buyer_url,
    buyer_national_id, buyer_email_domain, fetched_at.
    """
    country_iso3 = (record_fields.get("country_iso3") or "").strip().upper()
    buyer_name_raw = record_fields.get("buyer_name") or ""
    review_common = dict(
        record_id=record_fields.get("record_id", ""),
        country_iso3=country_iso3,
        buyer_name_raw=buyer_name_raw,
        buyer_url=record_fields.get("buyer_url"),
        buyer_national_id=record_fields.get("buyer_national_id"),
        buyer_email_domain=record_fields.get("buyer_email_domain"),
        status="open",
        opened_at=record_fields.get("fetched_at") or "",
        master_build_id=index.master_build_id,
        matcher_version=MATCHER_VERSION,
    )

    if not country_iso3:
        return None, InstitutionReview(reason="no_candidate", candidates=[], **review_common)

    pool = index.candidates_for_country(country_iso3)   # Tier 0
    if not pool:
        return None, InstitutionReview(reason="no_candidate", candidates=[], **review_common)

    # Never auto-accept onto a row the master itself flags as a duplicate
    # (spec §5: "a matcher that ignores [duplicate] will resolve to rows
    # already flagged as dupes"). Such rows can still surface in a
    # multiple-candidate or fuzzy review listing — a human decides.
    clean_pool = [c for c in pool if not c.duplicate]

    # Tier 1 — registrable-domain match.
    buyer_domain = registrable_domain(
        record_fields.get("buyer_url") or record_fields.get("buyer_email_domain") or "")
    if buyer_domain:
        hits = [c for c in clean_pool if c.website_domain and c.website_domain == buyer_domain]
        if len(hits) == 1:
            link, fallback = _try_link(hits[0], "tier1_domain", "auto_accepted",
                                        buyer_domain, record_fields, index, review_common)
            if link is not None:
                return link, None
            return None, fallback
        if len(hits) > 1:
            return None, InstitutionReview(
                reason="multiple_candidates",
                candidates=[_candidate_dict(c, "tier1_domain") for c in hits],
                **review_common)

    # Tier 2 — national registry id: confirmed unreachable (module docstring). Skipped.

    norm_name = normalize_name(buyer_name_raw)

    # Tier 3 — normalized exact name.
    if norm_name:
        hits = [c for c in clean_pool if c.normalized_name == norm_name]
        if len(hits) == 1:
            link, fallback = _try_link(hits[0], "tier3_exact_name", "auto_accepted",
                                        norm_name, record_fields, index, review_common)
            if link is not None:
                return link, None
            return None, fallback
        if len(hits) > 1:
            return None, InstitutionReview(
                reason="multiple_candidates",
                candidates=[_candidate_dict(c, "tier3_exact_name") for c in hits],
                **review_common)

    # Tier 4 — fuzzy name. NEVER auto-accepts (module docstring).
    if norm_name:
        scored = sorted(
            ((c, _fuzzy_score(norm_name, c.normalized_name))
             for c in pool if c.normalized_name),
            key=lambda pair: pair[1], reverse=True,
        )
        scored = [(c, s) for c, s in scored if s >= _FUZZY_REVIEW_FLOOR][:_FUZZY_MAX_CANDIDATES]
        if scored:
            best_candidate, _best_score = scored[0]
            is_subnational = best_candidate.government_level not in ("national", "")
            signal = _corroborating_signal(record_fields, best_candidate) if is_subnational else None
            reason = ("subnational_without_corroboration"
                      if is_subnational and not signal else "below_threshold")
            return None, InstitutionReview(
                reason=reason,
                candidates=[_candidate_dict(c, "tier4_fuzzy_name", s) for c, s in scored],
                **review_common)

    # Tier 5 — nothing matched at all.
    return None, InstitutionReview(reason="no_candidate", candidates=[], **review_common)


def _try_link(candidate: MasterRow, match_method: str, confidence: str, matched_on: str,
              record_fields: dict, index: InstitutionIndex,
              review_common: dict) -> tuple[Optional[InstitutionLink], Optional[InstitutionReview]]:
    """Resolve `candidate` THROUGH THE LEDGER before writing a link (module
    docstring). Falls back to a review row (never a link) if the ledger cannot
    currently stand behind this uid."""
    resolved_uid, ledger_status, resolved_from = index.resolve_ledger(candidate.institution_uid)
    if resolved_uid is None:
        return None, InstitutionReview(
            reason="ledger_status_not_active",
            candidates=[{**_candidate_dict(candidate, match_method), "ledger_status": ledger_status}],
            **review_common)
    link = InstitutionLink(
        record_id=record_fields.get("record_id", ""),
        role="contracting_authority",
        match_method=match_method,
        confidence=confidence,
        institution_uid=resolved_uid,
        matched_on=matched_on,
        ledger_status=ledger_status,
        resolved_from_uid=resolved_from,
        master_build_id=index.master_build_id,
        country_iso3=candidate.country_iso3,
        matcher_version=MATCHER_VERSION,
    )
    return link, None
