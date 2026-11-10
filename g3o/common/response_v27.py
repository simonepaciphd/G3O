"""The v2.7 ``6_validate.json`` response: identity and row keys only (RC-D-028 4 a).

PI ruling 2026-11-10 (RC-D-028 item 4 a): "T-012 adds a 2.7 response model
carrying identity and row keys only, values only from 6_storage.json".

A v2.7 ``6_validate.json`` therefore names the institution (master identity
columns, pipeline data), the Stage 6 run bookkeeping (``ConsolidationMetadata``)
and the final row keys: ``activity_id`` per activity and ``(source_id,
activity_id)`` per source claim. It carries no questionnaire value at all;
every model is ``extra="forbid"``, so a value field (``has_genai_activity``,
``tool_name``, ``genai_evidence``, ...) is refused rather than ignored. Every
value Stage 7 writes for a v2.7 row is read from the validated
``6_storage.json`` (:class:`g3o.common.storage.StorageEnvelope`).

The legacy ``ConsolidatedInstitutionResponse`` (v2.5/2.6) is unchanged; the
two are told apart by the explicit ``format`` member, which the legacy model
forbids (:func:`parse_validate_payload`).

Legacy-only columns of the three CSVs (``g3o.common.schema`` v2.5 columns that
no D-007 storage item maps to) are filled for v2.7 rows only by a signed rule
(:func:`retired_legacy_cells`): the codebook ``retired`` ``legacy_fill`` or the
signed ``year_deployed`` translation (R-051). A retired column without a signed
fill (``access_type``, ``vendor``) is left empty, never filled.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from g3o.common.contract import (
    ACTIVITY_ID_PATTERN,
    ACTIVITY_OR_NA_PATTERN,
    LANGS_PATTERN,
    NA,
    SOURCE_ID_PATTERN,
    ConsolidatedInstitutionResponse,
    ConsolidationMetadata,
)

VALIDATE_FORMAT_V27 = "g3o-validate-v27"
CODEBOOK_RELEASE = "2.7"


class InstitutionIdentityV27(BaseModel):
    """Master identity columns only (pipeline data, not codes)."""

    model_config = ConfigDict(extra="forbid")

    institution_id: str = Field(min_length=1)
    institution_name: str
    country: str
    branch_of_government: str
    level_of_government: str
    institution_search_languages: Annotated[str, StringConstraints(pattern=LANGS_PATTERN)]


class ActivityKeyV27(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: Annotated[str, StringConstraints(pattern=ACTIVITY_ID_PATTERN)]


class SourceKeyV27(BaseModel):
    """One evidence claim's key and its activity link (``_NA_`` when unlinked)."""

    model_config = ConfigDict(extra="forbid")

    source_id: Annotated[str, StringConstraints(pattern=SOURCE_ID_PATTERN)]
    activity_id: Annotated[str, StringConstraints(pattern=ACTIVITY_OR_NA_PATTERN)]


class ConsolidatedInstitutionResponseV27(BaseModel):
    """``6_validate.json`` for a v2.7 institution: identity and row keys only."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["g3o-validate-v27"]
    codebook_release: Literal["2.7"]
    consolidation_metadata: ConsolidationMetadata
    institution: InstitutionIdentityV27
    activities: list[ActivityKeyV27]
    sources: list[SourceKeyV27] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_keys(self) -> ConsolidatedInstitutionResponseV27:
        if self.consolidation_metadata.institution_id != self.institution.institution_id:
            raise ValueError("consolidation_metadata.institution_id does not match institution.institution_id")
        acts = [a.activity_id for a in self.activities]
        if acts != [f"A{i + 1}" for i in range(len(acts))]:
            raise ValueError(f"activity_id sequence must be A1, A2, ... in order; got {acts}")
        srcs = [s.source_id for s in self.sources]
        if srcs != [f"S{i + 1}" for i in range(len(srcs))]:
            raise ValueError(f"source_id sequence must be S1, S2, ... in order; got {srcs}")
        for s in self.sources:
            if s.activity_id != NA and s.activity_id not in acts:
                raise ValueError(f"source {s.source_id}: activity_id={s.activity_id!r} does not match any activity")
        return self


AnyValidateResponse = ConsolidatedInstitutionResponse | ConsolidatedInstitutionResponseV27


def is_v27_payload(payload: Any) -> bool:
    return isinstance(payload, Mapping) and "format" in payload


def parse_validate_payload(payload: Any) -> AnyValidateResponse:
    """Validate a ``6_validate.json`` payload against the model its ``format`` names.

    A payload with a ``format`` member is a v2.7 payload and is validated only
    against :class:`ConsolidatedInstitutionResponseV27`; anything else is a
    legacy payload and keeps the legacy model (and its refusals) unchanged.
    """
    if is_v27_payload(payload):
        if payload["format"] != VALIDATE_FORMAT_V27:
            raise ValueError(f"unsupported 6_validate.json format {payload['format']!r}")
        return ConsolidatedInstitutionResponseV27.model_validate(payload)
    return ConsolidatedInstitutionResponse.model_validate(payload)


def _ordered(keys: Iterable[str], prefix: str) -> list[str]:
    keys = list(keys)
    if any(not k.startswith(prefix) or not k[1:].isdigit() for k in keys):
        raise ValueError(f"storage row keys are not {prefix}<n> identifiers: {sorted(keys)}")
    return sorted(keys, key=lambda k: int(k[1:]))


def build_response_v27(*, institution: Mapping[str, Any], metadata: Mapping[str, Any],
                       activity_ids: Sequence[str], sources: Sequence[tuple[str, str]]
                       ) -> ConsolidatedInstitutionResponseV27:
    """Build and validate the v2.7 response from identity, metadata and row keys.

    ``institution`` holds the master identity columns only; ``sources`` is
    ``(source_id, activity_id)`` per claim. No value is accepted here.
    """
    return ConsolidatedInstitutionResponseV27.model_validate({
        "format": VALIDATE_FORMAT_V27, "codebook_release": CODEBOOK_RELEASE,
        "consolidation_metadata": dict(metadata), "institution": dict(institution),
        "activities": [{"activity_id": a} for a in activity_ids],
        "sources": [{"source_id": s, "activity_id": a} for s, a in sources],
    })


def response_from_storage(*, institution: Mapping[str, Any], metadata: Mapping[str, Any],
                          storage: Mapping[str, Any]) -> ConsolidatedInstitutionResponseV27:
    """The v2.7 response whose row keys are exactly those of a storage envelope's data."""
    acts = _ordered(storage["activities"], "A")
    srcs = _ordered(storage["sources"], "S")
    return build_response_v27(institution=institution, metadata=metadata, activity_ids=acts,
                              sources=[(s, storage["sources"][s]["activity_id"]) for s in srcs])


def check_storage_binding(response: ConsolidatedInstitutionResponseV27, storage: Mapping[str, Any]) -> None:
    """Refuse a v2.7 response whose identity or row keys differ from its ``6_storage.json``."""
    if storage.get("codebook_release") != CODEBOOK_RELEASE:
        raise ValueError("v2.7 6_validate.json is bound to a non-2.7 storage envelope")
    if response.institution.institution_id != storage["institution_id"]:
        raise ValueError("6_validate.json and 6_storage.json name different institutions")
    if [a.activity_id for a in response.activities] != _ordered(storage["activities"], "A"):
        raise ValueError("storage activity keys differ from the v2.7 response")
    if [s.source_id for s in response.sources] != _ordered(storage["sources"], "S"):
        raise ValueError("storage source keys differ from the v2.7 response")
    for s in response.sources:
        if storage["sources"][s.source_id]["activity_id"] != s.activity_id:
            raise ValueError(f"source {s.source_id}: activity link differs between 6_validate.json and 6_storage.json")


# ---------------------------------------------------------------------------
# Legacy-only CSV cells for v2.7 rows (signed rules only)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _retired_fills() -> dict[str, str | None]:
    from g3o.codebook.loader import load_codebook

    return {r["name"]: r.get("legacy_fill") for r in load_codebook().data["retired"] if "kind" not in r}


def year_deployed(values: Mapping[str, Any]) -> str:
    """Signed translation (R-051; ``core.year_pilot_start`` translation_v25): the earlier of
    the two start years; if only one is a year, that year; if neither, ``unknown``."""
    years = [v for v in (values.get("core.year_pilot_start"), values.get("core.year_production_start"))
             if isinstance(v, str) and len(v) == 4 and v.isdigit()]
    return min(years) if years else "unknown"


def retired_legacy_cells(columns: Iterable[str], values: Mapping[str, Any]) -> dict[str, str | None]:
    """Cells for retired legacy columns: signed ``legacy_fill`` / translation, else ``None``.

    ``None`` (an empty CSV cell) marks a retired column with no signed fill; it
    is never replaced by a guessed value.
    """
    fills = _retired_fills()
    out: dict[str, str | None] = {}
    for column in columns:
        if column == "year_deployed":
            out[column] = year_deployed(values)
        elif column in fills:
            fill = fills[column]
            out[column] = fill if isinstance(fill, str) else None
    return out


def list_members(value: Any) -> list[str]:
    """Collected members of a list/multi storage value; a signed missing token has none."""
    if isinstance(value, list):
        return list(value)
    return []


__all__ = [
    "AnyValidateResponse", "CODEBOOK_RELEASE", "ActivityKeyV27", "ConsolidatedInstitutionResponseV27",
    "InstitutionIdentityV27", "SourceKeyV27", "VALIDATE_FORMAT_V27", "build_response_v27",
    "check_storage_binding", "is_v27_payload", "list_members", "parse_validate_payload",
    "response_from_storage", "retired_legacy_cells", "year_deployed",
]
