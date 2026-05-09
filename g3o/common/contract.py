"""Pydantic v2 models for the G3O Output Contract v2.0 + Stage 6 consolidation.

Two layers:

1. **Stage 5 row-level surface** — ``BatchMetadata`` / ``ContractRow`` /
   ``BatchResponse`` / ``RunProvenance`` / ``PersistedRow``. Mirrors
   ``g3o/extract/prompts/output_contract.md`` §5 (39 contract fields per row,
   plus 10 batch-metadata fields). Used by Stage 5 (extract) parsing and the
   legacy ``DATA_COLUMNS`` debug-CSV path.

2. **Stage 6 consolidated surface** (Session C, Push #2) — the validator's
   per-institution output:
   - ``ConsolidationMetadata`` — analogue of ``BatchMetadata`` scoped to one
     institution.
   - ``ConsolidatedInstitution`` — institution-level metadata block.
   - ``ConsolidatedActivity`` — one row per ``(institution × activity)``;
     Group D fields are guaranteed non-``_NA_`` (defaults are ``unknown`` /
     ``none_reported`` / ``not_documented`` / ``none``).
   - ``SourceRecord`` — one row per source page, FK-linked to an activity
     via ``activity_id`` (or ``"_NA_"`` for absence/ambiguous/background_only
     sources).
   - ``ConsolidatedInstitutionResponse`` — top-level envelope.
   - ``ValidationProvenance`` / ``PersistedActivity`` / ``PersistedSource`` —
     CSV-ready envelopes for ``ACTIVITY_COLUMNS`` /
     ``ACTIVITY_SOURCE_COLUMNS``.

Stage 5 validators (per ``output_contract.md`` consistency-check numbers):

- Enum compliance — free via ``Literal[...]`` types (#8).
- ``_NA_`` vs Group D vs ``genai_evidence`` (#2), per row.
- ``uncertainty_flags`` semicolon syntax (§4.10), per row.
- Repeated institution fields across rows (#4), batch level.
- Repeated activity fields across rows (#5), batch level.
- ``has_genai_activity`` consistency vs ``genai_evidence`` (#3), batch level.
- Metadata counts vs row counts (#6), batch level.

Stage 6 validators:

- ``has_genai_activity`` ↔ activities ↔ source-evidence invariants.
- ``activity_id`` sequence is ``A1, A2, ...`` (gapless, ordered).
- ``source_id`` sequence is ``S1, S2, ...`` (gapless, ordered).
- Every ``SourceRecord.activity_id`` either ``"_NA_"`` (and not a
  ``confirms_activity`` source) or matches a ``ConsolidatedActivity``.
- ``ConsolidatedActivity.n_sources`` matches actual back-link count.
- Every ``ConsolidatedActivity`` has ≥1 supporting source.
- ``ConsolidatedActivity`` Group D fields are non-``_NA_``.
- ``consolidation_metadata.institution_id`` matches
  ``institution.institution_id``.

Consistency checks for Stage 5 #1 (institution coverage), #7 (no fabricated
URLs), and #9 (at least one source per institution) require external context
and are left to the caller.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# ---------------------------------------------------------------------------
# Tokens, vocabularies, and regex patterns
# ---------------------------------------------------------------------------

NA = "_NA_"

UNCERTAINTY_FLAG_VOCAB: frozenset[str] = frozenset(
    {
        "stage_ambiguous",
        "genai_vs_traditional_ai",
        "institution_attribution",
        "date_uncertain",
        "source_language_barrier",
        "vendor_undisclosed",
        "discontinued_uncertain",
        "scope_unclear",
    }
)

YEAR_PATTERN = r"^(\d{4}|unknown|_NA_)$"
SOURCE_PUB_DATE_PATTERN = r"^(\d{4}(-\d{2}(-\d{2})?)?|unknown)$"
ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
ISO_DATETIME_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$"
)
LANG_PATTERN = r"^[a-z]{2}$"
LANGS_PATTERN = r"^[a-z]{2}(,[a-z]{2})*$"

# Enum aliases keep the model definition close to the contract document.
ChatType = Literal["web", "deep"]
HasGenAI = Literal["yes", "no", "unclear"]
ActivityType = Literal[
    "policy_guidance",
    "pilot_experiment",
    "program_initiative",
    "internal_operational",
    "public_facing_service",
    "_NA_",
]
AdoptionStage = Literal[
    "announced", "pilot", "production", "discontinued", "unknown", "_NA_"
]
AccessType = Literal[
    "proprietary_vendor",
    "open_source",
    "sovereign_model",
    "in_house",
    "mixed",
    "unknown",
    "_NA_",
]
InteractionType = Literal[
    "chatbot",
    "document_processing",
    "code_generation",
    "decision_support",
    "translation",
    "content_creation",
    "search_retrieval",
    "multiple",
    "not_applicable",
    "unknown",
    "_NA_",
]
DeploymentMode = Literal["standalone", "integrated", "unknown", "_NA_"]
TargetUsers = Literal["internal_staff", "public", "both", "unknown", "_NA_"]
GovernanceFlag = Literal["yes", "no", "unclear", "not_documented", "_NA_"]
SourceType = Literal[
    "official_gov",
    "procurement_tender",
    "news_major",
    "news_trade",
    "vendor",
    "academic",
    "policy_org",
    "social_media",
    "archive",
    "other",
]
SourceCredibility = Literal["high", "medium", "low"]
GenAIEvidence = Literal[
    "confirms_activity", "confirms_absence", "ambiguous", "background_only"
]
Confidence = Literal["high", "medium", "low"]


# Group D field names, used by the row-level _NA_ consistency validator and by
# the batch-level repeated-activity-fields validator (#5).
GROUP_D_FIELDS: tuple[str, ...] = (
    "activity_name",
    "activity_type",
    "adoption_stage",
    "access_type",
    "interaction_type",
    "tool_name",
    "vendor",
    "deployment_mode",
    "target_users",
    "year_announced",
    "year_deployed",
    "has_human_oversight",
    "has_transparency_notice",
    "has_data_classification",
    "has_risk_assessment",
    "reported_outcomes",
    "reported_incidents",
    "scope_notes",
)

# Institution-level fields that must be identical across all rows for a single
# institution_id (consistency check #4).
INSTITUTION_SHARED_FIELDS: tuple[str, ...] = (
    "institution_name",
    "country",
    "branch_of_government",
    "level_of_government",
    "has_genai_activity",
    "institution_summary",
    "institution_search_languages",
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class BatchMetadata(BaseModel):
    """The `# batch_metadata` section of an Output Contract response."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str
    chat_type: ChatType
    model_label: str
    response_timestamp: Annotated[str, StringConstraints(pattern=ISO_DATETIME_PATTERN)]
    n_institutions_in_batch: int = Field(ge=1)
    n_institutions_with_genai: int = Field(ge=0)
    n_data_rows: int = Field(ge=1)
    search_languages: Annotated[str, StringConstraints(pattern=LANGS_PATTERN)]
    search_strategy_summary: Annotated[str, StringConstraints(max_length=300)]
    notes: str


class ContractRow(BaseModel):
    """One row of the `## data` table — an (institution × activity × source) triple."""

    model_config = ConfigDict(extra="forbid")

    # Group A — Row identity
    row_id: int = Field(ge=1)
    batch_id: str

    # Group B — Institution identity
    institution_id: str
    institution_name: str
    country: str
    branch_of_government: str
    level_of_government: str

    # Group C — Institution-level assessment
    has_genai_activity: HasGenAI
    institution_summary: Annotated[str, StringConstraints(max_length=300)]
    institution_search_languages: Annotated[
        str, StringConstraints(pattern=LANGS_PATTERN)
    ]

    # Group D — Activity fields (all `_NA_` unless genai_evidence == confirms_activity)
    activity_name: Annotated[str, StringConstraints(max_length=120)]
    activity_type: ActivityType
    adoption_stage: AdoptionStage
    access_type: AccessType
    interaction_type: InteractionType
    tool_name: Annotated[str, StringConstraints(max_length=100)]
    vendor: Annotated[str, StringConstraints(max_length=100)]
    deployment_mode: DeploymentMode
    target_users: TargetUsers
    year_announced: Annotated[str, StringConstraints(pattern=YEAR_PATTERN)]
    year_deployed: Annotated[str, StringConstraints(pattern=YEAR_PATTERN)]
    has_human_oversight: GovernanceFlag
    has_transparency_notice: GovernanceFlag
    has_data_classification: GovernanceFlag
    has_risk_assessment: GovernanceFlag
    reported_outcomes: Annotated[str, StringConstraints(max_length=200)]
    reported_incidents: Annotated[str, StringConstraints(max_length=200)]
    scope_notes: Annotated[str, StringConstraints(max_length=300)]

    # Group E — Source fields (always filled)
    source_url: str
    source_title: Annotated[str, StringConstraints(max_length=200)]
    source_publication_date: Annotated[
        str, StringConstraints(pattern=SOURCE_PUB_DATE_PATTERN)
    ]
    source_access_date: Annotated[str, StringConstraints(pattern=ISO_DATE_PATTERN)]
    source_type: SourceType
    source_language: Annotated[str, StringConstraints(pattern=LANG_PATTERN)]
    source_credibility: SourceCredibility
    genai_evidence: GenAIEvidence
    source_snippet: Annotated[str, StringConstraints(max_length=300)]

    # Group F — Row-level confidence and provenance metadata
    confidence: Confidence
    uncertainty_flags: str

    @model_validator(mode="after")
    def _validate_na_vs_group_d(self) -> ContractRow:
        if self.genai_evidence == "confirms_activity":
            offenders = [f for f in GROUP_D_FIELDS if getattr(self, f) == NA]
            if offenders:
                raise ValueError(
                    f"genai_evidence=confirms_activity but Group D fields are _NA_: "
                    f"{offenders}; use unknown/none_reported/none/not_documented instead"
                )
        else:
            non_na = [f for f in GROUP_D_FIELDS if getattr(self, f) != NA]
            if non_na:
                raise ValueError(
                    f"genai_evidence={self.genai_evidence!r} requires every Group D "
                    f"field to be _NA_; non-_NA_ fields: {non_na}"
                )
        return self

    @model_validator(mode="after")
    def _validate_uncertainty_flags(self) -> ContractRow:
        flags = self.uncertainty_flags
        if flags == "none":
            return self
        if flags == "":
            raise ValueError(
                "uncertainty_flags must be 'none' or one+ semicolon-separated flags"
            )
        if " " in flags:
            raise ValueError(
                "uncertainty_flags must not contain spaces (use semicolons)"
            )
        unknown = [tok for tok in flags.split(";") if tok not in UNCERTAINTY_FLAG_VOCAB]
        if unknown:
            raise ValueError(
                f"unknown uncertainty flag(s): {unknown}; "
                f"allowed: {sorted(UNCERTAINTY_FLAG_VOCAB)}"
            )
        return self


class BatchResponse(BaseModel):
    """Full response envelope: batch_metadata + a non-empty list of rows."""

    model_config = ConfigDict(extra="forbid")

    batch_metadata: BatchMetadata
    data: list[ContractRow] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_cross_row_consistency(self) -> BatchResponse:
        by_inst: dict[str, list[ContractRow]] = {}
        for row in self.data:
            by_inst.setdefault(row.institution_id, []).append(row)

        # #4 Repeated institution fields
        for inst_id, rows in by_inst.items():
            for fname in INSTITUTION_SHARED_FIELDS:
                vals = {getattr(r, fname) for r in rows}
                if len(vals) > 1:
                    raise ValueError(
                        f"institution {inst_id!r}: rows disagree on {fname}: "
                        f"{sorted(vals)}"
                    )

        # #5 Repeated activity fields (only rows with confirms_activity have a real
        # activity_name; rows with activity_name == _NA_ are skipped).
        by_act: dict[tuple[str, str], list[ContractRow]] = {}
        for row in self.data:
            if row.activity_name == NA:
                continue
            by_act.setdefault((row.institution_id, row.activity_name), []).append(row)
        for (inst_id, act), rows in by_act.items():
            for fname in GROUP_D_FIELDS:
                vals = {getattr(r, fname) for r in rows}
                if len(vals) > 1:
                    raise ValueError(
                        f"institution {inst_id!r} activity {act!r}: rows disagree on "
                        f"{fname}: {sorted(vals)}"
                    )

        # #3 has_genai_activity consistency
        for inst_id, rows in by_inst.items():
            hga = rows[0].has_genai_activity
            has_confirm = any(r.genai_evidence == "confirms_activity" for r in rows)
            if hga == "no" and has_confirm:
                raise ValueError(
                    f"institution {inst_id!r}: has_genai_activity=no but a row has "
                    f"genai_evidence=confirms_activity"
                )
            if hga == "yes" and not has_confirm:
                raise ValueError(
                    f"institution {inst_id!r}: has_genai_activity=yes but no row has "
                    f"genai_evidence=confirms_activity"
                )

        # #6 Metadata counts
        meta = self.batch_metadata
        n_inst = len(by_inst)
        if meta.n_institutions_in_batch != n_inst:
            raise ValueError(
                f"n_institutions_in_batch={meta.n_institutions_in_batch} but data "
                f"has {n_inst} distinct institutions"
            )
        n_yes = sum(
            1 for rows in by_inst.values() if rows[0].has_genai_activity == "yes"
        )
        if meta.n_institutions_with_genai != n_yes:
            raise ValueError(
                f"n_institutions_with_genai={meta.n_institutions_with_genai} but "
                f"data has {n_yes}"
            )
        if meta.n_data_rows != len(self.data):
            raise ValueError(
                f"n_data_rows={meta.n_data_rows} but data has {len(self.data)} rows"
            )

        return self


class RunProvenance(BaseModel):
    """Run-level metadata attached to every persisted row."""

    model_config = ConfigDict(extra="forbid")

    global_row_id: str
    run_id: str
    run_model: str
    run_tool: str
    run_date: Annotated[str, StringConstraints(pattern=ISO_DATE_PATTERN)]


class PersistedRow(BaseModel):
    """A `ContractRow` plus its `RunProvenance`, used at CSV write time."""

    model_config = ConfigDict(extra="forbid")

    provenance: RunProvenance
    row: ContractRow

    def to_csv_dict(self) -> dict[str, object]:
        """Return a dict ordered to match `g3o.common.schema.DATA_COLUMNS`."""
        from g3o.common.schema import DATA_COLUMNS

        merged: dict[str, object] = {
            **self.provenance.model_dump(),
            **self.row.model_dump(),
        }
        missing = [c for c in DATA_COLUMNS if c not in merged]
        if missing:
            raise RuntimeError(
                f"PersistedRow is missing columns required by DATA_COLUMNS: {missing}"
            )
        return {col: merged[col] for col in DATA_COLUMNS}


# ---------------------------------------------------------------------------
# Stage 6 — Consolidated-institution surface
# ---------------------------------------------------------------------------

# ID patterns: per-institution-scoped, gapless sequence starting at 1.
ACTIVITY_ID_PATTERN = r"^A[1-9]\d*$"
SOURCE_ID_PATTERN = r"^S[1-9]\d*$"
ACTIVITY_OR_NA_PATTERN = r"^(A[1-9]\d*|_NA_)$"

# Year fields in the consolidated surface drop _NA_ (every ConsolidatedActivity
# row IS an activity, so the row-level _NA_ semantics no longer apply).
YEAR_PATTERN_NO_NA = r"^(\d{4}|unknown)$"

# No-_NA_ enum aliases. Mirror the Stage 5 enums but exclude `_NA_`.
ActivityTypeNoNA = Literal[
    "policy_guidance",
    "pilot_experiment",
    "program_initiative",
    "internal_operational",
    "public_facing_service",
]
AdoptionStageNoNA = Literal[
    "announced", "pilot", "production", "discontinued", "unknown"
]
AccessTypeNoNA = Literal[
    "proprietary_vendor",
    "open_source",
    "sovereign_model",
    "in_house",
    "mixed",
    "unknown",
]
InteractionTypeNoNA = Literal[
    "chatbot",
    "document_processing",
    "code_generation",
    "decision_support",
    "translation",
    "content_creation",
    "search_retrieval",
    "multiple",
    "not_applicable",
    "unknown",
]
DeploymentModeNoNA = Literal["standalone", "integrated", "unknown"]
TargetUsersNoNA = Literal["internal_staff", "public", "both", "unknown"]
GovernanceFlagNoNA = Literal["yes", "no", "unclear", "not_documented"]


class ConsolidationMetadata(BaseModel):
    """The Stage 6 analogue of ``BatchMetadata``, scoped to one institution."""

    model_config = ConfigDict(extra="forbid")

    institution_id: str
    n_input_pages: int = Field(ge=1)
    n_input_rows: int = Field(ge=1)
    response_timestamp: Annotated[str, StringConstraints(pattern=ISO_DATETIME_PATTERN)]
    model_label: str
    notes: str


class ConsolidatedInstitution(BaseModel):
    """The institution-level metadata block (one per response)."""

    model_config = ConfigDict(extra="forbid")

    institution_id: str
    institution_name: str
    country: str
    branch_of_government: str
    level_of_government: str
    has_genai_activity: HasGenAI
    institution_summary: Annotated[str, StringConstraints(max_length=300)]
    institution_search_languages: Annotated[
        str, StringConstraints(pattern=LANGS_PATTERN)
    ]


class ConsolidatedActivity(BaseModel):
    """One canonical activity at one institution; aggregates across pages."""

    model_config = ConfigDict(extra="forbid")

    activity_id: Annotated[str, StringConstraints(pattern=ACTIVITY_ID_PATTERN)]

    # Group D — every field is non-`_NA_` (the row IS an activity by definition).
    activity_name: Annotated[str, StringConstraints(max_length=120)]
    activity_type: ActivityTypeNoNA
    adoption_stage: AdoptionStageNoNA
    access_type: AccessTypeNoNA
    interaction_type: InteractionTypeNoNA
    tool_name: Annotated[str, StringConstraints(max_length=100)]
    vendor: Annotated[str, StringConstraints(max_length=100)]
    deployment_mode: DeploymentModeNoNA
    target_users: TargetUsersNoNA
    year_announced: Annotated[str, StringConstraints(pattern=YEAR_PATTERN_NO_NA)]
    year_deployed: Annotated[str, StringConstraints(pattern=YEAR_PATTERN_NO_NA)]
    has_human_oversight: GovernanceFlagNoNA
    has_transparency_notice: GovernanceFlagNoNA
    has_data_classification: GovernanceFlagNoNA
    has_risk_assessment: GovernanceFlagNoNA
    reported_outcomes: Annotated[str, StringConstraints(max_length=200)]
    reported_incidents: Annotated[str, StringConstraints(max_length=200)]
    scope_notes: Annotated[str, StringConstraints(max_length=300)]

    # Aggregates.
    n_sources: int = Field(ge=1)
    confidence: Confidence
    uncertainty_flags: str

    @model_validator(mode="after")
    def _validate_no_na_in_group_d(self) -> ConsolidatedActivity:
        # Catches free-string fields (activity_name, tool_name, vendor,
        # reported_outcomes, reported_incidents, scope_notes) where a literal
        # `_NA_` would slip past Pydantic's max-length / Literal checks.
        for fname in GROUP_D_FIELDS:
            v = getattr(self, fname)
            if v == NA:
                raise ValueError(
                    f"ConsolidatedActivity.{fname}={NA!r} not permitted "
                    "(use 'unknown' / 'none_reported' / 'not_documented' / 'none')"
                )
        return self

    @model_validator(mode="after")
    def _validate_uncertainty_flags(self) -> ConsolidatedActivity:
        flags = self.uncertainty_flags
        if flags == "none":
            return self
        if flags == "":
            raise ValueError(
                "uncertainty_flags must be 'none' or one+ semicolon-separated flags"
            )
        if " " in flags:
            raise ValueError(
                "uncertainty_flags must not contain spaces (use semicolons)"
            )
        unknown = [tok for tok in flags.split(";") if tok not in UNCERTAINTY_FLAG_VOCAB]
        if unknown:
            raise ValueError(
                f"unknown uncertainty flag(s): {unknown}; "
                f"allowed: {sorted(UNCERTAINTY_FLAG_VOCAB)}"
            )
        return self


class SourceRecord(BaseModel):
    """One source page seen at consolidation time, FK-linked to an activity."""

    model_config = ConfigDict(extra="forbid")

    source_id: Annotated[str, StringConstraints(pattern=SOURCE_ID_PATTERN)]
    activity_id: Annotated[str, StringConstraints(pattern=ACTIVITY_OR_NA_PATTERN)]

    source_url: str
    source_title: Annotated[str, StringConstraints(max_length=200)]
    source_publication_date: Annotated[
        str, StringConstraints(pattern=SOURCE_PUB_DATE_PATTERN)
    ]
    source_access_date: Annotated[str, StringConstraints(pattern=ISO_DATE_PATTERN)]
    source_type: SourceType
    source_language: Annotated[str, StringConstraints(pattern=LANG_PATTERN)]
    source_credibility: SourceCredibility
    genai_evidence: GenAIEvidence
    source_snippet: Annotated[str, StringConstraints(max_length=300)]


class ConsolidatedInstitutionResponse(BaseModel):
    """Full Stage 6 response for one institution: metadata + institution + activities + sources."""

    model_config = ConfigDict(extra="forbid")

    consolidation_metadata: ConsolidationMetadata
    institution: ConsolidatedInstitution
    activities: list[ConsolidatedActivity]  # may be empty (has_genai_activity=no/unclear)
    sources: list[SourceRecord] = Field(min_length=1)

    # Validator ordering note: high-level business invariants (yes/no/unclear)
    # run before structural integrity checks (id sequencing, link well-formedness,
    # source-coverage counts), so the most informative error surfaces first.

    @model_validator(mode="after")
    def _validate_metadata_links(self) -> ConsolidatedInstitutionResponse:
        if self.consolidation_metadata.institution_id != self.institution.institution_id:
            raise ValueError(
                f"consolidation_metadata.institution_id="
                f"{self.consolidation_metadata.institution_id!r} does not match "
                f"institution.institution_id={self.institution.institution_id!r}"
            )
        return self

    @model_validator(mode="after")
    def _validate_yes_no_unclear_invariants(self) -> ConsolidatedInstitutionResponse:
        hga = self.institution.has_genai_activity
        confirms = [s for s in self.sources if s.genai_evidence == "confirms_activity"]
        if hga == "yes":
            if not self.activities:
                raise ValueError("has_genai_activity=yes but activities is empty")
            if not confirms:
                raise ValueError(
                    "has_genai_activity=yes but no source has "
                    "genai_evidence=confirms_activity"
                )
        elif hga == "no":
            if self.activities:
                raise ValueError(
                    "has_genai_activity=no but activities is non-empty"
                )
            non_absence = [
                s for s in self.sources if s.genai_evidence != "confirms_absence"
            ]
            if non_absence:
                raise ValueError(
                    f"has_genai_activity=no requires every source to be "
                    f"confirms_absence; offenders: "
                    f"{[s.source_id for s in non_absence]}"
                )
        elif hga == "unclear":
            if self.activities:
                raise ValueError(
                    "has_genai_activity=unclear but activities is non-empty"
                )
            if confirms:
                raise ValueError(
                    "has_genai_activity=unclear but a source has "
                    "genai_evidence=confirms_activity"
                )
        return self

    @model_validator(mode="after")
    def _validate_activity_id_sequence(self) -> ConsolidatedInstitutionResponse:
        seen = [a.activity_id for a in self.activities]
        expected = [f"A{i + 1}" for i in range(len(self.activities))]
        if seen != expected:
            raise ValueError(
                f"activity_id sequence must be A1, A2, ... in order; got {seen}"
            )
        return self

    @model_validator(mode="after")
    def _validate_source_id_sequence(self) -> ConsolidatedInstitutionResponse:
        seen = [s.source_id for s in self.sources]
        expected = [f"S{i + 1}" for i in range(len(self.sources))]
        if seen != expected:
            raise ValueError(
                f"source_id sequence must be S1, S2, ... in order; got {seen}"
            )
        return self

    @model_validator(mode="after")
    def _validate_source_activity_links(self) -> ConsolidatedInstitutionResponse:
        valid_act_ids = {a.activity_id for a in self.activities}
        for s in self.sources:
            if s.activity_id == NA:
                if s.genai_evidence == "confirms_activity":
                    raise ValueError(
                        f"source {s.source_id}: activity_id=_NA_ but "
                        f"genai_evidence=confirms_activity (must link to an activity)"
                    )
            else:
                if s.activity_id not in valid_act_ids:
                    raise ValueError(
                        f"source {s.source_id}: activity_id={s.activity_id!r} "
                        f"does not match any ConsolidatedActivity"
                    )
                if s.genai_evidence != "confirms_activity":
                    raise ValueError(
                        f"source {s.source_id}: activity_id={s.activity_id!r} "
                        f"requires genai_evidence=confirms_activity, got "
                        f"{s.genai_evidence!r}"
                    )
        return self

    @model_validator(mode="after")
    def _validate_n_sources(self) -> ConsolidatedInstitutionResponse:
        counts: dict[str, int] = {}
        for s in self.sources:
            if s.activity_id != NA:
                counts[s.activity_id] = counts.get(s.activity_id, 0) + 1
        for a in self.activities:
            actual = counts.get(a.activity_id, 0)
            if actual == 0:
                raise ValueError(
                    f"activity {a.activity_id} has no supporting sources "
                    "(every ConsolidatedActivity must be backed by ≥1 source)"
                )
            if a.n_sources != actual:
                raise ValueError(
                    f"activity {a.activity_id}: n_sources={a.n_sources} but "
                    f"{actual} sources reference it"
                )
        return self

class ValidationProvenance(BaseModel):
    """Run-level metadata attached at Stage 6/7 CSV write time."""

    model_config = ConfigDict(extra="forbid")

    global_row_id: str
    run_id: str
    run_model: str
    run_tool: str
    run_date: Annotated[str, StringConstraints(pattern=ISO_DATE_PATTERN)]


class PersistedActivity(BaseModel):
    """``ConsolidatedActivity`` + provenance + institution context, ready for CSV."""

    model_config = ConfigDict(extra="forbid")

    provenance: ValidationProvenance
    institution: ConsolidatedInstitution
    activity: ConsolidatedActivity

    def to_csv_dict(self) -> dict[str, object]:
        """Return a dict ordered to match ``g3o.common.schema.ACTIVITY_COLUMNS``."""
        from g3o.common.schema import ACTIVITY_COLUMNS

        merged: dict[str, object] = {
            **self.provenance.model_dump(),
            **self.institution.model_dump(),
            **self.activity.model_dump(),
        }
        missing = [c for c in ACTIVITY_COLUMNS if c not in merged]
        if missing:
            raise RuntimeError(
                f"PersistedActivity missing columns required by ACTIVITY_COLUMNS: {missing}"
            )
        return {col: merged[col] for col in ACTIVITY_COLUMNS}


class PersistedSource(BaseModel):
    """``SourceRecord`` + provenance + ``institution_id``, ready for CSV."""

    model_config = ConfigDict(extra="forbid")

    provenance: ValidationProvenance
    institution_id: str
    source: SourceRecord

    def to_csv_dict(self) -> dict[str, object]:
        """Return a dict ordered to match ``g3o.common.schema.ACTIVITY_SOURCE_COLUMNS``."""
        from g3o.common.schema import ACTIVITY_SOURCE_COLUMNS

        merged: dict[str, object] = {
            **self.provenance.model_dump(),
            "institution_id": self.institution_id,
            **self.source.model_dump(),
        }
        missing = [c for c in ACTIVITY_SOURCE_COLUMNS if c not in merged]
        if missing:
            raise RuntimeError(
                f"PersistedSource missing columns required by "
                f"ACTIVITY_SOURCE_COLUMNS: {missing}"
            )
        return {col: merged[col] for col in ACTIVITY_SOURCE_COLUMNS}


__all__ = [
    "NA",
    "UNCERTAINTY_FLAG_VOCAB",
    "GROUP_D_FIELDS",
    "INSTITUTION_SHARED_FIELDS",
    "ACTIVITY_ID_PATTERN",
    "SOURCE_ID_PATTERN",
    "ACTIVITY_OR_NA_PATTERN",
    "YEAR_PATTERN_NO_NA",
    "BatchMetadata",
    "ContractRow",
    "BatchResponse",
    "RunProvenance",
    "PersistedRow",
    "ConsolidationMetadata",
    "ConsolidatedInstitution",
    "ConsolidatedActivity",
    "SourceRecord",
    "ConsolidatedInstitutionResponse",
    "ValidationProvenance",
    "PersistedActivity",
    "PersistedSource",
]
