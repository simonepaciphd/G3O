"""PI-ruled coding rules for procurement evidence.

Separate from `contract.py` (which is a verbatim copy of the instrument) and from
`classify.py` (which decides relevance). This module holds the rules the PI has
*ruled on* for turning a procurement document into contract values, each with the
ruling that authorises it. Nothing here may be invented: if a case is not covered
by a ruling, the code must refuse to code it rather than guess.

Rulings implemented:

  D2/D3, 2026-08-04 — a tender-only record DOES create an activity row, coded
      `adoption_stage: proposed`. This overrides the recommended default in spec
      §6.2, which the PI is rewriting. An award keeps `announced` per §6.1.

  Q1a, 2026-08-04 — the contract's §4.2 "Typical evidence" column already names
      procurement records for `pilot_experiment`, `internal_operational` and
      `public_facing_service`, so those may be applied directly from a notice.

  D1, 2026-08-04 — when a record confirms GenAI but cannot be typed, `unknown` is
      the ruled answer BUT is not yet a legal enum member; contract v2.2 has not
      landed. Until it does, such a record is REPORTED, not coded. See
      `CANNOT_TYPE`.
"""

from __future__ import annotations

from .contract import ACTIVITY_TYPE, ADOPTION_STAGE
from .search import find_terms

# Sentinel for D1. Deliberately not a contract value: it must never reach output.
CANNOT_TYPE = "__cannot_type__"

# --------------------------------------------------------------------------- #
# adoption_stage (D2/D3 + spec §6.1)
# --------------------------------------------------------------------------- #

NOTICE_TYPE_TO_ADOPTION_STAGE = {
    "award": "announced",    # spec §6.1 — dated by the contract/award date
    "tender": "proposed",    # ruling D2/D3, 2026-08-04
}


def adoption_stage_for(notice_type: str, genai_evidence_type: str) -> str | None:
    """Contract `adoption_stage` (column 13) for a procurement notice.

    BUG FIX 2026-08-08 (caught reviewing the first live sample, where all 5
    `confirms_absence` records were staged `proposed`): this function used to
    ignore relevance entirely and stage a value for every tender/award,
    GenAI-relevant or not. The ruling's own text says otherwise — D2/D3,
    2026-08-04: "For a row to carry `proposed` rather than `_NA_`, section 6
    check 2 forces `genai_evidence: confirms_activity`". So a stage is only
    ever assigned when the source's own evidence confirms activity; everything
    else (`confirms_absence`, `ambiguous`, `background_only`) gets no staged
    value here — the eventual contract-output mapper is what turns that into
    `_NA_`, not this function.

    Returns None when:
      - `genai_evidence_type` is not `confirms_activity`, or
      - `notice_type` is `unknown` — a record whose own source cannot say
        whether it is a tender or an award has no ruled stage, and inventing
        one would be exactly the guess the rulings exist to prevent.

    A purchase is never a deployment: `production` is unreachable from this
    function by construction (spec §6.1).
    """
    if genai_evidence_type != "confirms_activity":
        return None
    stage = NOTICE_TYPE_TO_ADOPTION_STAGE.get(notice_type)
    assert stage is None or stage in ADOPTION_STAGE, stage
    return stage


def stage_dating_field(notice_type: str) -> str | None:
    """Which extracted date the stage is dated by.

    `announced` is dated by the contract/award date (§6.1). A tender has no
    contract date, which is the whole reason D2/D3 was needed; `proposed` is
    dated by publication.
    """
    return {"award": "award_date", "tender": "publication_date"}.get(notice_type)


# --------------------------------------------------------------------------- #
# activity_type (Q1a)
# --------------------------------------------------------------------------- #

# Signals drawn from the contract's own §4.2 definitions, NOT invented here:
#   pilot_experiment      "Limited trials, sandboxes, proof-of-concept
#                          deployments, or time-bounded experiments."
#   public_facing_service "Citizen- or business-facing chatbots, service
#                          navigation, translation, complaint handling, case
#                          triage."
#   internal_operational  "Routine internal use for drafting, summarization,
#                          knowledge search, translation, internal helpdesks, or
#                          developer tooling."
#
# Multilingual coverage is deliberately thin: per-language rosters are owned by
# subprojects/multilingual-pipeline/ (PI, 2026-08-04), so this table stays
# English-only until that subproject supplies the rest. A non-English notice that
# carries no signal therefore lands in CANNOT_TYPE and is reported, which is the
# correct failure — it is visible, not silent.
ACTIVITY_TYPE_SIGNALS: dict[str, tuple[str, ...]] = {
    # Checked first: a trial is a trial even when it is also internal.
    "pilot_experiment": (
        "pilot", "proof of concept", "proof-of-concept", "sandbox",
        "trial", "pilot project", "prototype", "experiment",
    ),
    "public_facing_service": (
        "citizen", "citizens", "public-facing", "public facing", "resident",
        "residents", "complaint handling", "service navigation", "case triage",
        "contact centre", "contact center", "helpline",
    ),
    "internal_operational": (
        "internal", "staff", "employees", "civil servants", "officials",
        "back office", "back-office", "helpdesk", "internal helpdesk",
        "drafting", "summarisation", "summarization", "knowledge search",
        "developer tooling", "licences for staff", "licenses for staff",
    ),
}

# Order matters: the first match wins, so this encodes the precedence above.
_SIGNAL_ORDER = ("pilot_experiment", "public_facing_service", "internal_operational")


def activity_type_for(fields: dict) -> tuple[str, list[str]]:
    """Contract `activity_type` (column 12) from a procurement notice.

    Returns `(value, matched_signals)`. `value` is a contract enum member, or
    `CANNOT_TYPE` when the document gives no basis for choosing — which under
    ruling D1 means the record is reported rather than coded, because `unknown`
    is not a legal member until contract v2.2 lands.

    Only applied to records the classifier has already judged GenAI-relevant;
    typing an irrelevant record would be meaningless.
    """
    text = " \n".join(
        str(fields[k]) for k in ("title", "description") if fields.get(k)
    )
    if not text.strip():
        return CANNOT_TYPE, []

    for activity_type in _SIGNAL_ORDER:
        hits = find_terms(text, list(ACTIVITY_TYPE_SIGNALS[activity_type]))
        if hits:
            assert activity_type in ACTIVITY_TYPE, activity_type
            return activity_type, hits
    return CANNOT_TYPE, []


# --------------------------------------------------------------------------- #
# vendor when one release has several suppliers (D6)
# --------------------------------------------------------------------------- #

VENDOR_MULTIPLE = "multiple"


def vendor_for(supplier_names: list[str]) -> str | None:
    """Contract `vendor` (column 17) for an activity collapsed from one release.

    Interim rule (PI, 2026-08-04, held for the checkpoint): where awards under
    one release go to different suppliers, write `multiple` and keep the full
    list in the extension table. Picking one supplier would discard information;
    `multiple` does not.
    """
    distinct = [n for i, n in enumerate(supplier_names) if n and n not in supplier_names[:i]]
    if not distinct:
        return None
    return distinct[0] if len(distinct) == 1 else VENDOR_MULTIPLE
