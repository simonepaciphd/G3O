"""Map extracted fields onto the standardized records.

Three responsibilities:
  - extract_ocds():     shared OCDS extractor (raw OCDS payload -> field dict).
                        Written once, reused by all 67 OCDS sources.
  - standardize():      intermediate field dict + classification -> ProcurementRecord.
  - build_extension():  the same inputs -> ExtensionRecord (spec §4).

All three must stay in sync with config/schema/*.schema.json.

The intermediate field dict is the contract between adapter.extract() and this
module. Its keys are exactly the ProcurementRecord field names, plus the
extension keys listed in EXTENSION_KEYS. A non-OCDS adapter's field map only has
to produce those keys; anything it cannot evidence it simply omits.
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from .. import __version__ as PIPELINE_VERSION
from .classify import needs_review
from .coding import adoption_stage_for
from .models import Classification, ExtensionRecord, ProcurementRecord, RawRecord

# Keys build_extension() reads out of the intermediate dict (spec §4).
EXTENSION_KEYS = (
    "value_amount", "value_currency", "value_is_estimated", "value_covers",
    "procedure_type", "bidder_count", "supplier_role", "supplier_national_id",
    "contract_start_date", "contract_end_date", "lot_identifier",
    "has_audit_rights", "ip_ownership", "liability_terms",
    "data_residency_clause", "exit_lockin_provision", "penalty_clause",
    "human_oversight_requirement",
)

# OCDS procurementMethod codelist -> extension procedure_type (spec §4.2).
# A codelist translation, not an inference. Anything unlisted stays "unknown".
OCDS_METHOD_TO_PROCEDURE = {
    "open": "open",
    "selective": "restricted",
    "direct": "direct_award",
}


def make_record_id(source_id: str, native_id: str) -> str:
    """Stable dedup/upsert key, and the join key across the three tables."""
    return hashlib.sha1(f"{source_id}|{native_id}".encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def _as_date(value: Any) -> Optional[str]:
    """OCDS carries full ISO-8601 datetimes; the schemas want a date. Truncate,
    never reformat — a date we cannot read is dropped, not guessed."""
    if not value or not isinstance(value, str):
        return None
    head = value.strip()[:10]
    return head if len(head) == 10 and head[4] == "-" and head[7] == "-" else None


def _email_domain(email: Any) -> Optional[str]:
    if not email or not isinstance(email, str) or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip().lower()
    return domain or None


def _party_by_role(parties: Any, role: str) -> dict:
    """First party carrying `role` in its roles list. OCDS parties[] is the
    richer description of the same organization referenced in buyer/suppliers."""
    if not isinstance(parties, list):
        return {}
    for party in parties:
        if isinstance(party, dict) and role in (party.get("roles") or []):
            return party
    return {}


def _merge_org(ref: Any, parties: Any, role: str) -> dict:
    """Combine an OCDS organization reference (buyer / supplier) with its fuller
    entry in parties[], matched on id then on role."""
    ref = ref if isinstance(ref, dict) else {}
    full: dict = {}
    if isinstance(parties, list) and ref.get("id") is not None:
        for party in parties:
            if isinstance(party, dict) and party.get("id") == ref["id"]:
                full = party
                break
    if not full:
        full = _party_by_role(parties, role)
    merged = dict(full)
    merged.update({k: v for k, v in ref.items() if v is not None})
    return merged


# --------------------------------------------------------------------------- #
# OCDS item lines (rules R1-R5, agent-workspace/2026-10-07-item-level-rules-PROPOSAL.md)
# --------------------------------------------------------------------------- #

# Provenance flags: informational, they never put a record in the review queue.
DESCRIPTION_FROM_ITEMS_FLAG = "internal_description_from_items"
VALUE_FROM_ITEMS_FLAG = "internal_value_from_items"
VALUE_PARTIAL_FLAG = "internal_value_partial_items_unpriced"
VALUE_MIXED_CURRENCY_FLAG = "internal_value_mixed_currency"
VALUE_CURRENCY_MISSING_FLAG = "internal_value_currency_missing"


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _item_lines(items: Any) -> list[dict]:
    return [i for i in (items or []) if isinstance(i, dict)] if isinstance(items, list) else []


def _item_text(items: list[dict]) -> Optional[str]:
    """R1: item and item-classification descriptions, de-duplicated, in item order."""
    seen: list[str] = []
    for item in items:
        for text in (item.get("description"), (item.get("classification") or {}).get("description")):
            text = " ".join(str(text).split()) if text else ""
            if text and text not in seen:
                seen.append(text)
    return "; ".join(seen) or None


def _item_value(items: list[dict]) -> tuple[dict, list[str]]:
    """R3-R5: sum quantity x unit price within ONE currency.

    Unpriced lines are left out and flagged partial (never imputed). Mixed or
    missing currencies yield no amount at all: amounts in different currencies
    are never added together.
    """
    priced: list[tuple[float, Any]] = []
    unpriced = 0
    for item in items:
        price = ((item.get("unit") or {}).get("value") or {})
        amount, quantity = _number(price.get("amount")), _number(item.get("quantity"))
        if amount is None or quantity is None:
            unpriced += 1
        else:
            priced.append((amount * quantity, price.get("currency")))
    if not priced:
        return {}, []
    currencies = {c for _, c in priced}
    if None in currencies or "" in currencies:
        return {}, [VALUE_CURRENCY_MISSING_FLAG]
    if len(currencies) > 1:
        return {}, [VALUE_MIXED_CURRENCY_FLAG]
    flags = [VALUE_FROM_ITEMS_FLAG] + ([VALUE_PARTIAL_FLAG] if unpriced else [])
    return {"amount": round(sum(v for v, _ in priced), 2), "currency": currencies.pop()}, flags


# --------------------------------------------------------------------------- #
# OCDS extraction
# --------------------------------------------------------------------------- #

def extract_ocds(raw: RawRecord) -> list[dict]:
    """Shared OCDS extractor: an OCDS release -> one intermediate dict PER AWARD.

    Accepts a release, or a record/package wrapper around one (`releases[0]`,
    `compiledRelease`). Reads only paths the standard defines; a source that
    puts data somewhere else needs its own extract() override, not a guess here.

    **Returns a list** (ruling D6, 2026-08-04): a release carrying several awards
    or lots produces one staged record each, never silently the first. The
    collapse back to one activity per release happens downstream of staging, so
    nothing is lost on the way in. A tender-only release yields exactly one
    record.

    This is the highest-leverage function in the codebase: it unlocks all 67
    OCDS sources, API and bulk alike.
    """
    payload = raw.payload if isinstance(raw.payload, dict) else {}

    release = payload
    if "compiledRelease" in payload and isinstance(payload["compiledRelease"], dict):
        release = payload["compiledRelease"]
    elif isinstance(payload.get("releases"), list) and payload["releases"]:
        first = payload["releases"][0]
        if isinstance(first, dict):
            release = first

    tender = release.get("tender") or {}
    parties = release.get("parties")
    awards = [a for a in (release.get("awards") or []) if isinstance(a, dict)]
    contracts = [c for c in (release.get("contracts") or []) if isinstance(c, dict)]
    tags = [str(t) for t in (release.get("tag") or [])]

    # An award block present in the payload is stronger evidence of an award
    # than the tag list, which sources populate inconsistently.
    if awards or any(t in ("award", "contract", "implementation") for t in tags):
        notice_type = "award"
    elif tender or any(t in ("tender", "tenderUpdate", "planning") for t in tags):
        notice_type = "tender"
    else:
        notice_type = "unknown"

    buyer = _merge_org(release.get("buyer"), parties, "buyer")
    buyer_contact = buyer.get("contactPoint") or {}
    buyer_identifier = buyer.get("identifier") or {}

    # release.id is the source observation id. Using ocid first would collapse
    # tender and award releases from the same contracting process on upsert.
    release_id = str(release.get("id") or release.get("ocid") or raw.native_id)

    related_processes = [
        item for item in (release.get("relatedProcesses") or [])
        if isinstance(item, dict)
    ]
    is_framework_calloff = any(
        "framework" in (
            [str(value) for value in relationship]
            if isinstance((relationship := item.get("relationship")), list)
            else [str(relationship)]
        )
        for item in related_processes
    )
    techniques = tender.get("techniques") or {}

    tender_value = tender.get("value") or {}
    tender_bidders = tender.get("numberOfTenderers")
    lots = tender.get("lots") or []

    common: dict[str, Any] = {
        "ocds_ocid": release.get("ocid"),
        "notice_type": notice_type,
        "url": (tender.get("url") or release.get("url") or None),
        "title": tender.get("title"),
        "description": tender.get("description"),
        "buyer_name": buyer.get("name"),
        "buyer_url": buyer_contact.get("url") or buyer.get("url") or None,
        "buyer_national_id": buyer_identifier.get("id"),
        "buyer_email_domain": _email_domain(buyer_contact.get("email")),
        "publication_date": _as_date(tender.get("datePublished") or release.get("date")),
        "value_covers": "unknown",
        "procedure_type": OCDS_METHOD_TO_PROCEDURE.get(
            str(tender.get("procurementMethod") or "").lower(), "unknown"),
    }

    # Frameworks (spec §6.3) are coded only from explicit OCDS relationships.
    # hasFrameworkAgreement alone supports establishment, but it does not prove
    # that a tender value is a framework ceiling; value_covers therefore stays
    # unknown unless a source-specific extractor has direct evidence.
    if is_framework_calloff:
        common["procedure_type"] = "framework_calloff"
    elif techniques.get("hasFrameworkAgreement") is True:
        common["procedure_type"] = "framework_establishment"

    # Contracts are matched to their award by awardID where the source states it.
    contracts_by_award: dict[str, dict] = {}
    for c in contracts:
        key = str(c.get("awardID") or "")
        contracts_by_award.setdefault(key, c)

    def _one(award: dict, index: int) -> dict:
        fields = dict(common)
        award_id = str(award.get("id") or index) if award else ""

        # A release with awards keys each record to its award, always - not only
        # when there are several - so an id never changes if a second award
        # appears in a later release of the same process.
        fields["native_id"] = f"{release_id}#{award_id}" if award else release_id

        contract = (contracts_by_award.get(award_id)
                    or (contracts[0] if contracts and len(awards) <= 1 else {}))

        suppliers = [s for s in (award.get("suppliers") or []) if isinstance(s, dict)]
        supplier = _merge_org(suppliers[0] if suppliers else None, parties, "supplier")
        supplier_identifier = supplier.get("identifier") or {}

        flags: list[str] = []
        # R1: item text from this award's own lines; a tender-only release (or
        # an award without lines) reads the tender's lines. Text only.
        text_items = _item_lines(award.get("items")) or _item_lines(tender.get("items"))
        title = common["title"] or award.get("title")
        description = common["description"] or award.get("description")
        if not title and not description:
            description = _item_text(text_items)
            if description:
                flags.append(DESCRIPTION_FROM_ITEMS_FLAG)

        # R2 value order: award.value -> this award's priced item lines ->
        # tender estimate. Tender item lines are never summed (R6: the award
        # repeats them, and they carry no price on the sources seen so far).
        award_value = award.get("value") or {}
        value_covers = common["value_covers"]
        if award_value.get("amount") is not None:
            value, value_is_estimated = award_value, False
        else:
            item_value, item_flags = _item_value(_item_lines(award.get("items")))
            flags.extend(item_flags)
            if item_value:
                value, value_is_estimated, value_covers = item_value, False, "single_award"
            elif tender_value.get("amount") is not None:
                value, value_is_estimated = tender_value, True
            else:
                value, value_is_estimated = {}, None

        contract_period = contract.get("period") or award.get("contractPeriod") or {}

        lot_identifier = None
        related_lots = award.get("relatedLots") or []
        if related_lots:
            lot_identifier = str(related_lots[0])
        elif isinstance(lots, list) and len(lots) == 1 and isinstance(lots[0], dict):
            lot_identifier = lots[0].get("id")

        bidder_count = tender_bidders
        if bidder_count is None:
            bidder_count = award.get("numberOfTenderers")

        fields.update({
            "title": title,
            "description": description,
            "value_covers": value_covers,
            "extraction_flags": flags or None,
            "supplier_name": supplier.get("name"),
            "award_date": _as_date(award.get("date") or contract.get("dateSigned")),
            "value_amount": value.get("amount"),
            "value_currency": value.get("currency"),
            "value_is_estimated": value_is_estimated,
            "bidder_count": bidder_count if isinstance(bidder_count, int)
            and not isinstance(bidder_count, bool) else None,
            "supplier_national_id": supplier_identifier.get("id"),
            "contract_start_date": _as_date(contract_period.get("startDate")),
            "contract_end_date": _as_date(contract_period.get("endDate")),
            "lot_identifier": lot_identifier,
            # D6: every supplier on the release, so the downstream collapse can
            # write vendor=multiple without going back to the raw payload.
            "release_supplier_names": [
                s.get("name") for a in awards
                for s in (a.get("suppliers") or [])
                if isinstance(s, dict) and s.get("name")
            ] or None,
            "release_award_count": len(awards) or None,
        })
        return {k: v for k, v in fields.items() if v is not None}

    if not awards:
        return [_one({}, 0)]
    return [_one(a, i) for i, a in enumerate(awards)]


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

def standardize(adapter, raw: RawRecord, fields: dict,
                clf: Classification) -> ProcurementRecord:
    """Assemble the intermediate record from adapter metadata + extracted fields
    + classification, and fill provenance.

    Source-level metadata (country, repo name, coverage) comes from the adapter's
    config row in sources.yaml; record-level data comes from `fields`. The
    classifier's verdict is copied, never recomputed here.
    """
    config = getattr(adapter, "config", {}) or {}
    native_id = str(fields.get("native_id") or raw.native_id)

    return ProcurementRecord(
        record_id=make_record_id(adapter.source_id, native_id),
        source_id=adapter.source_id,
        country_iso3=config.get("country_iso3", ""),
        native_id=native_id,
        notice_type=fields.get("notice_type", "unknown"),
        genai_relevant=clf.genai_relevant,
        fetched_at=raw.fetched_at,
        pipeline_version=PIPELINE_VERSION,

        source_repo_name=config.get("repo_name"),
        country_name=config.get("country_name"),
        ocds_ocid=fields.get("ocds_ocid"),
        coverage_type=config.get("coverage_type"),
        title=fields.get("title"),
        description=fields.get("description"),
        buyer_name=fields.get("buyer_name"),
        buyer_url=fields.get("buyer_url"),
        buyer_national_id=fields.get("buyer_national_id"),
        buyer_email_domain=fields.get("buyer_email_domain"),
        supplier_name=fields.get("supplier_name"),
        value_amount=fields.get("value_amount"),
        value_currency=fields.get("value_currency"),
        publication_date=fields.get("publication_date"),
        award_date=fields.get("award_date"),
        url=fields.get("url"),

        genai_relevance_score=clf.genai_relevance_score,
        genai_category=clf.genai_category,
        genai_evidence=clf.genai_evidence,
        genai_evidence_type=clf.genai_evidence_type,
        # Ruling D2/D3 + spec §6.1: award -> announced, tender -> proposed —
        # but only when the source's own evidence confirms activity; a
        # confirms_absence/ambiguous/background_only record gets no staged
        # stage (bug fix 2026-08-08, see coding.adoption_stage_for docstring).
        adoption_stage=adoption_stage_for(
            fields.get("notice_type", "unknown"), clf.genai_evidence_type),
        review_flags=list(dict.fromkeys(list(clf.review_flags) + list(fields.get("extraction_flags") or []))),
        review_status="pending" if needs_review(clf.review_flags) else "not_required",
        classifier_version=clf.classifier_version,
        raw_payload_ref=raw.raw_payload_ref,
    )


def build_extension(adapter, raw: RawRecord, fields: dict,
                    clf: Classification) -> ExtensionRecord:
    """Assemble the procurement extension row (spec §4), joined 1:1 on record_id.

    Only fields the document evidenced: absent enum fields keep their documented
    `unknown` / `not_documented` member; absent numeric, identifier, date, or
    verbatim-excerpt fields remain null where the extension schema permits it.

    §4.3 governance terms come from contract text, which OCDS does not carry —
    they stay at `not_documented` until a document-text extractor exists.
    """
    config = getattr(adapter, "config", {}) or {}
    native_id = str(fields.get("native_id") or raw.native_id)

    present = {k: fields[k] for k in EXTENSION_KEYS
               if k in fields and fields[k] is not None}

    return ExtensionRecord(
        record_id=make_record_id(adapter.source_id, native_id),
        pipeline_version=PIPELINE_VERSION,
        source_id=adapter.source_id,
        source_repo_name=config.get("repo_name"),
        native_id=native_id,
        ocds_ocid=fields.get("ocds_ocid"),
        classifier_version=clf.classifier_version,
        raw_payload_ref=raw.raw_payload_ref,
        **present,
    )
