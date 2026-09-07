"""Stage 5 / Stage 6 pre-validation salvage.

Three independent repairs, each applied to the raw payload before Pydantic
validation, so that neither a page (Stage 5) nor an institution's consolidation
(Stage 6) is dropped whole over a value the contract itself invited the model to
write. They share the philosophy set out below and nothing else: different
fields, different trigger conditions, different reason codes.

Group-D ``_NA_`` on positive findings
-------------------------------------

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
- **Targeted, not blanket.** This repair touches Group-D ``_NA_`` on
  ``confirms_activity`` rows only. ``_NA_`` in Group C/E, out-of-enum values,
  missing fields and the Q1=a access-date contract all still hard-fail,
  untouched. (Group F and the reverse Group-D rule have their own repairs below,
  added later and on their own terms; neither is an extension of this one.)
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

``uncertainty_flags`` ``_NA_``
------------------------------

Background. ``uncertainty_flags`` (column 39) is a Group-F field with its own
closed vocabulary whose prescribed empty value is ``none``; ``_NA_`` is not in
that vocabulary and never has been. But §3.2 of the contract instructs the model
to set "every field in Group D" to ``_NA_``, and column 39 sits in the same
row-shape as the eighteen Group-D columns that genuinely do take ``_NA_``.
Nothing marks it as an exception, so a model generalising the surrounding rule
writes ``_NA_`` here — which ``ContractRow._validate_uncertainty_flags`` rejects,
taking the whole page down (observed: ``INST-0000580`` / windowsforum.com in run
``digitalocean-010-dry``). ``ConsolidatedActivity`` carries byte-identical
validation logic, so Stage 6 has the same exposure.

From v2.3 the primary fix is the JSON Schema, which declares the field an array of
vocabulary members and so makes ``_NA_``, ``""`` and space-bearing values
unrepresentable during generation (#59). This module is the defence in depth
behind it: rewrite a blank-or-``_NA_`` value to ``none``, which is the value the
contract already prescribes, and normalise stray whitespace around the separators
without discarding any flag the model actually supplied.

- **Evidence-agnostic.** Unlike Group-D salvage, this fires on every row
  regardless of ``genai_evidence``. ``none`` is the field's only legal empty
  value in *every* branch of the contract, and ``_NA_`` and ``none`` both mean
  "no flags apply" — so the substitution is faithful on a ``confirms_activity``
  row too. It encodes no coding decision, so nothing here is unsalvageable and
  there is no counterpart to ``GROUP_D_UNSALVAGEABLE``.
- **Two repairs, and they are different in kind.**

  *Blank means none.* The exact literal ``_NA_``, the empty string ``""``, and
  whitespace-only values are whole-value statements of "no flags here", which the
  contract spells ``none``. Substituting ``none`` is faithful: nothing the model
  coded is lost, because it coded nothing.

  *Separator whitespace is formatting, not content.* ``"a; b"`` is the contract's
  own vocabulary with a stray space after the semicolon. The repair strips
  whitespace around the separators and keeps every flag
  (``"genai_vs_traditional_ai; date_uncertain"`` →
  ``"genai_vs_traditional_ai;date_uncertain"``). This one matters most in what it
  refuses to do: the single spaces-class failure in the n=100 run carried **two
  real flags**, so coercing it to ``none`` — the obvious reading of "repair the
  blank cases too" — would have destroyed a finding in order to save a page.

  Still left to hard-fail, unchanged: ``"NA"``, ``"n/a"``, ``"_na_"`` (case
  matters) and mixed values such as ``"stage_ambiguous;_NA_"``. The first three
  are genuine vocabulary drift; in the mixed case the model supplied real flags,
  so the stray ``_NA_`` stays visible rather than being silently dropped.

  The blank and separator cases were both excluded until v2.3. That was
  defensible while the field was an unconstrained string and ``""`` might have
  signalled a confused row; it stopped being defensible once the run telemetry
  showed ``""`` was the *largest* live failure class (27 of 46 page failures at
  n=100, #17). From v2.3 the schema makes all of these unrepresentable at
  generation time, so this widening is a backstop for a non-strict path or a
  future model regression, not the primary fix.
- **Ledger, not row.** As above — ``uncertainty_flags_na_salvaged``. No new
  column, and emphatically no new flag value: adding ``_NA_`` to
  ``UNCERTAINTY_FLAG_VOCAB`` would relax the contract rather than repair the row,
  and would leave two synonymous empty values in the published vocabulary.

Group D filled on a negative-evidence row (the inverse direction)
----------------------------------------------------------------

Background. The Group-D repair above handles ``_NA_`` where a value belongs. The
mirror error also occurs: ``genai_evidence`` is ``confirms_absence`` /
``ambiguous`` / ``background_only``, where §3.2 requires every Group-D column to
be ``_NA_``, but the model filled one in anyway — 8 records across 6 institutions
in the n=100 run, with ``scope_notes`` implicated in every one of them (the model
adding a remark on a page it had just declared negative).

The repair blanks the offending fields to ``_NA_``. Unlike the two above, this one
*discards* model output rather than rewriting it to a synonym, so the escalation
rule matters more than the repair does:

- **Existence-asserting fields are never blanked.** If ``activity_name``,
  ``activity_type``, ``tool_name`` or ``vendor`` is filled on a negative row, the
  model contradicted itself about whether a finding exists. Blanking would resolve
  that contradiction silently in favour of "no activity" — a substantive coding
  decision, and exactly the kind this module refuses to make. The row is left to
  fail, reported as ``group_d_negative_row_contradictory``. (One of the 8 observed
  records is this case: ``tool_name`` and ``vendor`` both filled.)
- **Everything else is stray annotation** on a row whose negative status the model
  itself asserted, so blanking loses no finding. Reported as
  ``group_d_negative_row_blanked``, with the discarded values recorded in the
  ledger ``detail`` — the point is that a blanking is reconstructible from the
  record, not merely counted.

The asymmetry with ``GROUP_D_UNSALVAGEABLE`` is deliberate and the two sets are
not interchangeable: that set is about fields with no sanctioned
"could-not-determine" value, this one about fields whose content is evidence of a
finding. ``activity_name`` and ``activity_type`` happen to be in both, for
different reasons.

Note what none of this addresses: page-level validation atomicity, which is why
one bad cell costs a whole page in the first place. Tracked as issue #44 and
deliberately deferred — every repair here is a patch on a symptom whose cause is
architectural.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from g3o.common.contract import GROUP_D_FIELDS, NA, UNCERTAINTY_FLAG_VOCAB

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

# The contract's prescribed empty value for `uncertainty_flags` (§3.2 column 39 /
# §4.10). Not a member of UNCERTAINTY_FLAG_VOCAB — it is the alternative *to*
# supplying flags, which is why the vocabulary check short-circuits on it.
UNCERTAINTY_FLAGS_EMPTY = "none"

# Group-D fields whose presence on a *negative-evidence* row asserts that an
# activity exists. If one of these is filled where the model also said
# confirms_absence / ambiguous / background_only, the model contradicted itself
# about the thing that matters most — whether there is a finding at all — and
# blanking it would silently resolve that contradiction in favour of "no". Such a
# row is escalated, not repaired. Everything else in Group D is descriptive of an
# activity already asserted, so on a negative row it is stray annotation.
GROUP_D_EXISTENCE_ASSERTING: frozenset[str] = frozenset(
    {"activity_name", "activity_type", "tool_name", "vendor"}
)

# Stable attrition reason codes (see attrition.py). Kept here so callers and
# tests reference one definition.
REASON_SALVAGED = "group_d_incomplete_salvaged"
REASON_UNSALVAGEABLE = "group_d_incomplete_unsalvageable"
REASON_FLAGS_SALVAGED = "uncertainty_flags_na_salvaged"
REASON_NEGATIVE_ROW_BLANKED = "group_d_negative_row_blanked"
REASON_NEGATIVE_ROW_CONTRADICTORY = "group_d_negative_row_contradictory"

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
# Invariant: the uncertainty_flags repair only makes sense while `_NA_` is illegal
# and `none` is not itself a flag. If either drifts, the repair is either dead
# code (`_NA_` became legal — relaxation, which this module rejects) or actively
# wrong (`none` became a flag, so substituting it would assert a flag).
if NA in UNCERTAINTY_FLAG_VOCAB:
    raise RuntimeError(
        f"{NA!r} is in UNCERTAINTY_FLAG_VOCAB; the uncertainty_flags salvage in "
        "this module exists because it is not, and adding it relaxes the contract"
    )
if UNCERTAINTY_FLAGS_EMPTY in UNCERTAINTY_FLAG_VOCAB:
    raise RuntimeError(
        f"{UNCERTAINTY_FLAGS_EMPTY!r} is in UNCERTAINTY_FLAG_VOCAB; it is the "
        "contract's *empty* value, not a flag, and salvage substitutes it as such"
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


@dataclass(frozen=True)
class UncertaintyFlagsSalvage:
    """One ``uncertainty_flags`` ``_NA_`` → ``none`` repair on one row.

    There is deliberately no ``unsalvageable`` counterpart: ``none`` is the
    contract's prescribed value for this field on every row, so the repair never
    requires a coding decision and never has to give up.

    The identity fields differ by stage and only one is ever populated:
    ``row_id`` + ``source_url`` at Stage 5 (``ContractRow``), ``activity_id`` at
    Stage 6 (``ConsolidatedActivity`` aggregates across pages, so it has neither
    a row number nor a single source URL).
    """

    row_id: int | None = None
    activity_id: str | None = None
    source_url: str = ""

    @property
    def ref(self) -> str:
        """Short identity for the ledger ``detail`` field."""
        if self.row_id is not None:
            return f"row_id={self.row_id}"
        if self.activity_id:
            return f"activity_id={self.activity_id}"
        return "row_ref=?"


@dataclass(frozen=True)
class NegativeRowSalvage:
    """One Group-D-on-a-negative-row decision for one row.

    ``blanked_fields`` names the Group-D fields rewritten to ``_NA_``;
    ``contradictory_fields`` names existence-asserting fields that were filled,
    in which case nothing was rewritten and the row is left to fail. Exactly one
    of the two is ever non-empty.

    ``discarded`` maps each blanked field to the value that was thrown away, so
    the ledger can carry what a blanking actually cost.
    """

    row_id: int | None
    source_url: str
    blanked_fields: tuple[str, ...] = ()
    contradictory_fields: tuple[str, ...] = ()
    discarded: tuple[tuple[str, str], ...] = ()

    @property
    def is_salvageable(self) -> bool:
        """True when the row was repaired rather than escalated."""
        return not self.contradictory_fields

    @property
    def reason(self) -> str:
        """The ledger reason code for this decision."""
        return (
            REASON_NEGATIVE_ROW_BLANKED
            if self.is_salvageable
            else REASON_NEGATIVE_ROW_CONTRADICTORY
        )


def salvage_negative_row_group_d(payload: object) -> list[NegativeRowSalvage]:
    """Blank stray Group-D values on negative-evidence rows in place.

    The mirror of :func:`salvage_group_d_na`: that one fills ``_NA_`` where a
    value belongs, this one blanks a value where ``_NA_`` belongs. Mutates
    ``payload["data"]`` rows directly and returns one :class:`NegativeRowSalvage`
    per affected row. Structurally malformed payloads yield ``[]``.

    A row is affected only when ``genai_evidence`` is *not* ``confirms_activity``
    and at least one Group-D field is not ``_NA_``. If any offender is
    existence-asserting (``GROUP_D_EXISTENCE_ASSERTING``) the row is left untouched
    and reported as contradictory; otherwise every offender is rewritten to ``_NA_``
    and the discarded values are carried on the event. See the module docstring for
    why that line is drawn there.
    """
    events: list[NegativeRowSalvage] = []
    if not isinstance(payload, dict):
        return events
    data = payload.get("data")
    if not isinstance(data, list):
        return events

    for row in data:
        if not isinstance(row, dict):
            continue
        evidence = row.get("genai_evidence")
        if not isinstance(evidence, str) or evidence == "confirms_activity":
            continue
        # A field absent from the row is a schema failure, not a salvage case —
        # only a field that is present and not `_NA_` counts as an offender.
        offenders = [f for f in GROUP_D_FIELDS if f in row and row.get(f) != NA]
        if not offenders:
            continue

        rid = row.get("row_id")
        row_id = rid if isinstance(rid, int) else None
        src = row.get("source_url")
        source_url = src if isinstance(src, str) else ""

        contradictory = tuple(f for f in offenders if f in GROUP_D_EXISTENCE_ASSERTING)
        if contradictory:
            events.append(
                NegativeRowSalvage(
                    row_id=row_id,
                    source_url=source_url,
                    contradictory_fields=contradictory,
                )
            )
            continue

        discarded = tuple((f, str(row[f])) for f in offenders)
        for f in offenders:
            row[f] = NA
        events.append(
            NegativeRowSalvage(
                row_id=row_id,
                source_url=source_url,
                blanked_fields=tuple(offenders),
                discarded=discarded,
            )
        )

    return events


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


def salvage_uncertainty_flags_na(rows: object) -> list[UncertaintyFlagsSalvage]:
    """Rewrite a blank-or-``_NA_`` ``uncertainty_flags`` to ``none``, in place.

    Takes the row list rather than the enclosing payload so each stage can pass
    its own container: ``payload["data"]`` at Stage 5, ``payload["activities"]``
    at Stage 6. Structurally malformed input is left for the validator to reject —
    anything that is not a list of dicts yields ``[]``.

    Two repairs, applied in order: whitespace around the semicolon separators is
    stripped, then a value that is blank or the whole-value literal ``_NA_``
    becomes ``none``. So ``"a; b"`` keeps both flags, while ``""``, ``"   "`` and
    ``" _NA_ "`` all become ``none``. ``"NA"``, ``"n/a"``, ``"_na_"`` and mixed
    values such as ``"stage_ambiguous;_NA_"`` are deliberately left to hard-fail;
    see the module docstring.

    A non-string is never touched — from v2.3 the model emits an array, which
    ``contract._coerce_uncertainty_flags`` normalises on the way in, and an empty
    array is already the legal way to say "no flags apply".
    """
    events: list[UncertaintyFlagsSalvage] = []
    if not isinstance(rows, list):
        return events

    for row in rows:
        if not isinstance(row, dict):
            continue
        value = row.get("uncertainty_flags")
        if not isinstance(value, str):
            continue
        repaired = ";".join(token.strip() for token in value.split(";"))
        if repaired == NA or repaired.strip() == "":
            repaired = UNCERTAINTY_FLAGS_EMPTY
        if repaired == value:
            continue
        row["uncertainty_flags"] = repaired
        rid = row.get("row_id")
        aid = row.get("activity_id")
        src = row.get("source_url")
        events.append(
            UncertaintyFlagsSalvage(
                row_id=rid if isinstance(rid, int) else None,
                activity_id=aid if isinstance(aid, str) else None,
                source_url=src if isinstance(src, str) else "",
            )
        )

    return events


__all__ = [
    "GROUP_D_SALVAGE_DEFAULTS",
    "GROUP_D_UNSALVAGEABLE",
    "GROUP_D_EXISTENCE_ASSERTING",
    "UNCERTAINTY_FLAGS_EMPTY",
    "REASON_SALVAGED",
    "REASON_UNSALVAGEABLE",
    "REASON_FLAGS_SALVAGED",
    "REASON_NEGATIVE_ROW_BLANKED",
    "REASON_NEGATIVE_ROW_CONTRADICTORY",
    "GroupDSalvage",
    "NegativeRowSalvage",
    "UncertaintyFlagsSalvage",
    "salvage_group_d_na",
    "salvage_uncertainty_flags_na",
    "salvage_negative_row_group_d",
]
