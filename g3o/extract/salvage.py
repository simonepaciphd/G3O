"""Stage 5 Group-D ``_NA_`` salvage (issue: Group-D _NA_ on positive findings).

Background. A ``confirms_activity`` row whose Group-D activity fields carry the
literal ``_NA_`` violates the Output Contract (§3.2 / consistency-check #2 say a
``confirms_activity`` row must use ``unknown`` / ``none_reported`` / ``none`` /
``not_documented`` *instead* of ``_NA_``). ``ContractRow._validate_na_vs_group_d``
rejects such a row, and because ``BatchResponse`` validation is atomic over the
whole page, the entire page's extraction is dropped by the Stage 5 runner. That
selectively suppresses confirmed GenAI adopters whose evidence is real but whose
schema conformance is imperfect (the Qatar MCIT failure).

This module implements **parser-side salvage**: before validation, it conforms
those rows to the contract by substituting each ``_NA_`` Group-D field with the
contract's own prescribed "could-not-determine" default, and reports what it did
so the caller can write one attrition/telemetry record per salvaged page.

Scope and boundaries (deliberate, not accidental):

- **Repair, not relaxation.** The substituted values are exactly the defaults the
  contract already mandates for ``confirms_activity`` rows. Salvage conforms the
  row *to* the contract; it does not change contract semantics, the extraction
  prompt, or what ``has_genai_activity`` / ``genai_evidence`` mean. No rows are
  added or removed, so the batch-level metadata-count invariants are unaffected.
- **Targeted, not blanket.** Salvage touches Group-D ``_NA_`` on
  ``confirms_activity`` rows only. ``_NA_`` in Group C/E/F, out-of-enum values,
  missing fields, the Q1=a access-date contract, and the reverse Group-D rule
  (non-``confirms_activity`` rows carrying non-``_NA_`` Group D) all still
  hard-fail, untouched.
- **Two fields cannot be salvaged.** ``activity_type`` is an enum with no
  ``unknown`` member, and ``activity_name`` has no sanctioned sentinel; supplying
  a value for either would be a typology/naming decision (researcher-control) or
  a schema change. A ``confirms_activity`` row whose Group-D ``_NA_`` includes
  one of these is left untouched (it still fails validation, and the page still
  drops) and reported as *unsalvageable* so the escalation rate is measurable.
- **Marker lives in the attrition ledger, not in the row.** Marking a salvaged
  row in-band (a new ``uncertainty_flags`` value or a new column) would edit the
  schema-of-record — held for PI sign-off (see the ``group_d_incomplete``
  tracking issue). The ledger reason code ``group_d_incomplete_salvaged`` (keyed
  by institution + source_url) is the auditable marker.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from g3o.common.contract import GROUP_D_FIELDS, NA

# Per-field "could-not-determine" default for each Group-D field, taken verbatim
# from the value the Output Contract prescribes for a confirms_activity row that
# cannot code the field. Every key is a member of GROUP_D_FIELDS; the two fields
# absent here (activity_type, activity_name) have no sanctioned default and are
# listed in GROUP_D_UNSALVAGEABLE instead.
GROUP_D_SALVAGE_DEFAULTS: dict[str, str] = {
    "adoption_stage": "unknown",
    "access_type": "unknown",
    "interaction_type": "unknown",
    "tool_name": "unknown",
    "vendor": "unknown",
    "deployment_mode": "unknown",
    "target_users": "unknown",
    "year_announced": "unknown",
    "year_deployed": "unknown",
    "has_human_oversight": "not_documented",
    "has_transparency_notice": "not_documented",
    "has_data_classification": "not_documented",
    "has_risk_assessment": "not_documented",
    "reported_outcomes": "none_reported",
    "reported_incidents": "none_reported",
    "scope_notes": "none",
}

# Group-D fields with no contract-sanctioned "could-not-determine" value:
# activity_type (enum, no `unknown` member) and activity_name (free string, no
# sentinel). Salvaging either would require a substantive coding decision or a
# schema change, so a row that needs it is escalated, not repaired.
GROUP_D_UNSALVAGEABLE: frozenset[str] = frozenset({"activity_type", "activity_name"})

# Stable attrition reason codes (see attrition.py). Kept here so callers and
# tests reference one definition.
REASON_SALVAGED = "group_d_incomplete_salvaged"
REASON_UNSALVAGEABLE = "group_d_incomplete_unsalvageable"

# Invariant: the two partitions exactly cover the Group-D fields, disjointly.
# Explicit raises (not asserts): asserts are stripped under `python -O`, which
# would let a drifted GROUP_D_FIELDS silently disable salvage for a field.
if set(GROUP_D_SALVAGE_DEFAULTS) | GROUP_D_UNSALVAGEABLE != set(GROUP_D_FIELDS):
    raise RuntimeError(
        "Group-D salvage partition does not cover GROUP_D_FIELDS: "
        f"missing={set(GROUP_D_FIELDS) - set(GROUP_D_SALVAGE_DEFAULTS) - GROUP_D_UNSALVAGEABLE}, "
        f"unknown={(set(GROUP_D_SALVAGE_DEFAULTS) | GROUP_D_UNSALVAGEABLE) - set(GROUP_D_FIELDS)}"
    )
if set(GROUP_D_SALVAGE_DEFAULTS) & GROUP_D_UNSALVAGEABLE:
    raise RuntimeError(
        "Group-D salvage partitions overlap: "
        f"{set(GROUP_D_SALVAGE_DEFAULTS) & GROUP_D_UNSALVAGEABLE}"
    )


@dataclass(frozen=True)
class GroupDSalvage:
    """One salvage decision for one ``confirms_activity`` row.

    ``salvaged_fields`` names the Group-D fields whose ``_NA_`` was repaired to a
    contract default (populated only when ``unsalvageable_fields`` is empty; a row
    that needs any unsalvageable repair is left untouched so it fails validation).
    ``unsalvageable_fields`` names Group-D ``_NA_`` fields that could not be
    repaired (``activity_type`` / ``activity_name``).
    """

    row_id: int | None
    source_url: str
    salvaged_fields: tuple[str, ...] = ()
    unsalvageable_fields: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_salvageable(self) -> bool:
        """True when the row was (or could be) repaired to a contract-valid state."""
        return not self.unsalvageable_fields


def salvage_group_d_na(payload: object) -> list[GroupDSalvage]:
    """Repair salvageable Group-D ``_NA_`` on ``confirms_activity`` rows in place.

    Mutates ``payload["data"]`` rows directly (so a subsequent
    ``BatchResponse.model_validate(payload)`` sees the repaired values) and returns
    one :class:`GroupDSalvage` per affected row. Structurally malformed payloads
    are left for the validator to reject: this function is defensive and simply
    returns ``[]`` for anything that is not the expected ``{"data": [ {...} ]}``
    shape.

    A row is affected only when ``genai_evidence == "confirms_activity"`` and it
    carries at least one Group-D ``_NA_``. If any such ``_NA_`` is in an
    unsalvageable field, the row is left untouched and reported with
    ``unsalvageable_fields`` set; otherwise every ``_NA_`` Group-D field is
    rewritten to its contract default and reported with ``salvaged_fields`` set.
    """
    events: list[GroupDSalvage] = []
    if not isinstance(payload, dict):
        return events
    data = payload.get("data")
    if not isinstance(data, list):
        return events

    for row in data:
        if not isinstance(row, dict):
            continue
        if row.get("genai_evidence") != "confirms_activity":
            continue
        na_fields = [f for f in GROUP_D_FIELDS if row.get(f) == NA]
        if not na_fields:
            continue

        rid = row.get("row_id")
        row_id = rid if isinstance(rid, int) else None
        src = row.get("source_url")
        source_url = src if isinstance(src, str) else ""

        unsalvageable = tuple(f for f in na_fields if f in GROUP_D_UNSALVAGEABLE)
        if unsalvageable:
            # Leave the row untouched — it will (correctly) fail validation and the
            # page will drop; repairing only the salvageable subset would mutate a
            # doomed row for no gain. Report it so the escalation rate is visible.
            events.append(
                GroupDSalvage(
                    row_id=row_id,
                    source_url=source_url,
                    unsalvageable_fields=unsalvageable,
                )
            )
            continue

        for f in na_fields:
            row[f] = GROUP_D_SALVAGE_DEFAULTS[f]
        events.append(
            GroupDSalvage(
                row_id=row_id,
                source_url=source_url,
                salvaged_fields=tuple(na_fields),
            )
        )

    return events


__all__ = [
    "GROUP_D_SALVAGE_DEFAULTS",
    "GROUP_D_UNSALVAGEABLE",
    "REASON_SALVAGED",
    "REASON_UNSALVAGEABLE",
    "GroupDSalvage",
    "salvage_group_d_na",
]
