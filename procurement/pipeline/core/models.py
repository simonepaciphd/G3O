"""Data models shared across the pipeline.

Three record types, mirroring the three schemas in config/schema/ — keep each
dataclass in sync with its schema file:

  ProcurementRecord  -> procurement_record.schema.json    (extraction intermediate)
  ExtensionRecord    -> procurement_extension.schema.json (spec §4)
  InstitutionLink    -> institution_link.schema.json      (spec §5)

The emitted artifact is contract-conformant rows + the extension table; this
module is the staging shape those are built from (spec §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class GenAIQuerySet:
    """Parsed form of config/genai_queries.yaml.

    Consumed by both source-side search (query pushdown) and the local NLP
    classifier. The terms themselves are PI-defined; the default config file is
    a placeholder and the RA draft at genai_queries.DRAFT-v0.1.yaml is parked.

    `context_required_terms` is the quarantine list: a product name that is a
    good retrieval signal but cannot establish relevance on its own (codebook
    §3.2). Matching only these yields `unclear`, not `yes`.
    """
    version: str
    terms: dict[str, list[str]] = field(default_factory=dict)   # lang -> terms
    regex: list[str] = field(default_factory=list)
    codes: dict[str, list[str]] = field(default_factory=dict)
    exclude_terms: list[str] = field(default_factory=list)
    context_required_terms: list[str] = field(default_factory=list)

    def all_terms(self) -> list[str]:
        return [t for terms in self.terms.values() for t in terms]


@dataclass
class Hit:
    """A lightweight handle to a candidate record returned by adapter.search()."""
    source_id: str
    native_id: str
    ref: Any = None          # adapter-specific locator (url, offset, file+rowno)


@dataclass
class RawRecord:
    """Raw payload for one record as returned by adapter.fetch(), plus provenance."""
    source_id: str
    native_id: str
    payload: Any             # dict/json/html/row — whatever the source returned
    fetched_at: str = ""     # ISO-8601; set by the pipeline at fetch time
    raw_payload_ref: Optional[str] = None   # path/key in data_cache


@dataclass
class Classification:
    """Output of a Classifier backend.

    `relevance` is this ONE SOURCE's provisional three-value disposition. It is
    not contract column 8: `has_genai_activity` is institution-level ("same
    value on every row for the same institution"), so it is settled only by
    aggregating every source for an institution, and the contract's `yes` also
    requires review confirmation. That aggregation step is still pending.

    `genai_evidence_type` IS a contract column-36 value and is assessable per
    source — contract Edge Case A codes a supplied page carrying no GenAI
    mention as `confirms_absence` on that row. Allowed members are in
    core.contract.GENAI_EVIDENCE.

    `genai_relevant` stays the boolean the extraction-intermediate schema
    declares: True only for a provisional `yes`.
    """
    genai_relevant: bool
    relevance: str = "no"                            # yes | no | unclear | not_assessable (per source, NOT contract C8)
    genai_evidence_type: Optional[str] = "confirms_absence"    # contract column 36; None when not_assessable
    genai_relevance_score: Optional[float] = None
    genai_category: Optional[str] = None       # contract activity_type (D12); enum not yet available
    genai_evidence: Optional[str] = None       # matched terms / snippet (transparency trail)
    review_flags: list[str] = field(default_factory=list)   # e.g. genai_vs_traditional_ai
    classifier_version: Optional[str] = None


@dataclass
class ProcurementRecord:
    """One standardized intermediate record. Mirrors procurement_record.schema.json."""
    record_id: str
    source_id: str
    country_iso3: str
    native_id: str
    notice_type: str                 # tender | award | unknown
    genai_relevant: bool
    fetched_at: str
    pipeline_version: str

    source_repo_name: Optional[str] = None
    country_name: Optional[str] = None
    ocds_ocid: Optional[str] = None
    coverage_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_url: Optional[str] = None            # spec §4.4 — matcher tier 1
    buyer_national_id: Optional[str] = None    # spec §4.4 — matcher tier 2
    buyer_email_domain: Optional[str] = None   # spec §4.4 — derived fallback
    supplier_name: Optional[str] = None
    value_amount: Optional[float] = None
    value_currency: Optional[str] = None
    publication_date: Optional[str] = None
    award_date: Optional[str] = None
    url: Optional[str] = None

    genai_relevance_score: Optional[float] = None
    genai_category: Optional[str] = None
    genai_evidence: Optional[str] = None
    genai_evidence_type: Optional[str] = None   # contract column 36, per source
    adoption_stage: Optional[str] = None        # contract column 13; ruling D2/D3 + spec §6.1
    review_flags: list[str] = field(default_factory=list)
    review_status: str = "not_required"       # not_required | pending
    classifier_version: Optional[str] = None
    raw_payload_ref: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtensionRecord:
    """Procurement extension row (spec §4). Mirrors procurement_extension.schema.json.

    Only what the 39-field contract cannot hold. Never carries the relevance
    verdict, the activity typology, or the institution link.

    Enum defaults are the documented "no evidence" members, never null: an
    unpopulated `procedure_type` means the document did not state one, which is
    `unknown` — not missing data.
    """
    record_id: str
    pipeline_version: str

    value_amount: Optional[float] = None
    value_currency: Optional[str] = None
    value_is_estimated: Optional[bool] = None
    value_covers: str = "unknown"

    procedure_type: str = "unknown"
    bidder_count: Optional[int] = None
    supplier_role: str = "unknown"
    supplier_national_id: Optional[str] = None
    contract_start_date: Optional[str] = None
    contract_end_date: Optional[str] = None
    lot_identifier: Optional[str] = None

    has_audit_rights: str = "not_documented"
    ip_ownership: str = "not_documented"
    liability_terms: Optional[str] = None
    data_residency_clause: str = "not_documented"
    exit_lockin_provision: Optional[str] = None
    penalty_clause: Optional[str] = None
    human_oversight_requirement: str = "not_documented"

    source_id: Optional[str] = None
    source_repo_name: Optional[str] = None
    native_id: Optional[str] = None
    ocds_ocid: Optional[str] = None
    classifier_version: Optional[str] = None
    raw_payload_ref: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InstitutionLink:
    """Record-to-institution link (spec §5). Mirrors institution_link.schema.json.

    Several links per record are normal — a central purchasing body buying on
    behalf of a department is the usual case. `institution_uid` is the master's
    PERSISTENT key; never `master_row_id`, which is positional.
    """
    record_id: str
    role: str                  # contracting_authority | beneficiary | central_purchasing_body
    match_method: str          # tier1_domain | tier2_national_id | tier3_exact_name | tier4_fuzzy_name | tier5_human_review
    confidence: str            # auto_accepted | human_confirmed — resolved links only (ruling Q5c); unresolved/rejected candidates live in InstitutionReview instead

    institution_uid: str
    match_score: Optional[float] = None
    matched_on: Optional[str] = None
    corroborating_signal: Optional[str] = None
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    key_level: Optional[int] = None
    country_iso3: Optional[str] = None
    matcher_version: Optional[str] = None
    ledger_status: Optional[str] = None       # active | absent | retired
    resolved_from_uid: Optional[str] = None   # set when a merge chain was followed
    master_build_id: Optional[str] = None     # e.g. mb-2026-07-30

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InstitutionReview:
    """A record waiting for a human to resolve its institution (PI ruling Q5c,
    2026-08-04). Mirrors institution_review.schema.json.

    `institution_link` holds confirmed links only, so everything short of a
    confirmed match waits here. Rows are closed, never deleted.
    """
    record_id: str
    country_iso3: str
    buyer_name_raw: str          # original script, never transliterated
    status: str                  # open | confirmed | rejected
    opened_at: str

    reason: Optional[str] = None
    buyer_url: Optional[str] = None
    buyer_national_id: Optional[str] = None
    buyer_email_domain: Optional[str] = None
    candidates: list = field(default_factory=list)
    chosen_institution_uid: Optional[str] = None
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    reviewer_notes: Optional[str] = None
    master_build_id: Optional[str] = None
    matcher_version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
