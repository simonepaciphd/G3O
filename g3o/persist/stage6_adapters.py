"""Producer adapters from v2.7 Stage 6 outputs to the Stage 7 artifacts (T-028).

Builds the per-institution ``6_storage.json`` (a :class:`StorageEnvelope`) and
``6_validate.json`` (a ``ConsolidatedInstitutionResponse``) that
:mod:`g3o.persist.writer` consumes, from the outputs that exist on this branch:
T-024 :class:`~g3o.common.support_check.SupportResult`, T-027
:class:`~g3o.common.jev_record.CoderRecord` and the consolidate_v27 reductions.

Rules (SPEC R-026, R-041, R-042, R-081; D-007 interface spec section 3):

- **Original and final nodes.** Every checked value yields an ORIGINAL support
  node keyed on the code the coder actually chose (``SupportResult.original_value``)
  with the T-024 status. When T-024 replaced the value (``downgrade_target``
  ``unknown``), a separate FINAL node carries the replacement, links to the
  original through ``input_support_ids`` and has a mechanical coder record. The
  original classifier record is projected unchanged, so a downgrade never
  overwrites the original ``chosen_value``. ``tag_only`` items (the page
  verdict) are never rewritten and get no final node.
- **Quotes.** ``supporting_text`` is the quote exactly as the quote step
  returned it. It is never replaced with page text. The final node of a
  downgrade carries no quote of its own (``""``); its evidence is the link.
- **Matcher provenance (R-042).** The T-024 matcher is re-run on the stored
  page artifact's segment the quote came from (the producing part, or the
  page's chrome text) and must reproduce the ``SupportResult`` exactly; any
  disagreement refuses. The passage records the segment and its span in the
  artifact; the full match result travels in a companion provenance record
  (the D-007 support record has no member for it).
- **Missing upstream.** Inputs whose producer is absent on this branch are
  explicit parameters; ``None`` raises :class:`MissingUpstreamError` naming the
  producer. Nothing is filled with a fixture default or a guessed value.
- **Companion "empty".** ``support_rule_name`` (filled only for
  ``set_by_rule``) and ``support_status_second_reason`` (filled only when two
  checks fail) take ``not_asked`` otherwise: R-045's token for a value a rule
  skipped, as in the T-012 storage fixtures.

Source confidence (PI 2026-11-07) is not yet in the signed codebook. This
module does not map credibility/support to a confidence level; it consumes a
T-015 source-level value through :func:`source_confidence` and combines
already-coded values only through ``consolidate_v27.activity_confidence``.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from g3o.common.contract import ConsolidatedInstitutionResponse
from g3o.common.instrument import canonical_json, sha256_text, validate_instrument
from g3o.common.jev_record import _PROVIDER_FIELDS, _STORAGE_FIELDS, NOT_APPLICABLE, CoderRecord
from g3o.common.storage import CHANNELS, METADATA_ITEMS, StorageEnvelope, support_id, table_fields
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import (
    LOW_CONFIDENCE,
    MATCH_DECISION,
    MATCH_METRIC,
    MATCH_THRESHOLD,
    PINNED_RAPIDFUZZ,
    SET_BY_RULE,
    WORD_RULE_CUTOFF,
    PageSources,
    SupportResult,
    match_quote,
)
from g3o.validate.consolidate_v27 import activity_confidence

PROVENANCE_FORMAT = "g3o-support-provenance-v1"
EMPTY_COMPANION = "not_asked"  # R-045: a rule skipped the companion item
MATCHER_LIBRARY = "rapidfuzz"
STORAGE_ARTIFACT = "6_storage.json"
VALIDATE_ARTIFACT = "6_validate.json"

# Producers that do not exist on this branch (HANDOFF 2026-11-07; PLAN cards).
UNCERTAINTY_FLAGS_PRODUCER = "T-024 derived-field producer (core.uncertainty_flags per observation/code)"
SOURCE_FIELDS_PRODUCER = "T-015 source_fields.py"
SOURCE_CONFIDENCE_PRODUCER = ("T-015 source-level confidence (PI 2026-11-07 mapping, "
                              "not yet in the signed codebook)")
STAGE6_EXECUTOR = "T-026 relation/pool executor (final activities, source claims, relations)"
SUMMARY_PRODUCER = "consolidate_v27.summary_values over T-026 final pooled values"


class MissingUpstreamError(ValueError):
    """An input whose producer is absent; never replaced by a default."""

    def __init__(self, producer: str, missing: Sequence[str] = ()) -> None:
        self.producer = producer
        self.missing = tuple(missing)
        detail = f": {', '.join(self.missing)}" if self.missing else ""
        super().__init__(f"missing upstream input from {producer}{detail}")


@dataclass(frozen=True)
class PageArtifact:
    """The stored page artifact a source row points at, with its segment layout.

    ``segments`` maps each part ``chunk_id`` and ``<page>#chrome`` to its
    ``(start, end)`` span in ``text``; the span must reproduce the part/chrome
    text the support check saw. The layout comes from the page artifact's
    producer (T-014/T-020); the adapter refuses a layout it cannot verify.
    """

    source_id: str
    path: str  # as stored in 6_storage.json, relative to the run directory
    text: str  # the actual stored artifact text
    segments: Mapping[str, tuple[int, int]]

    @property
    def sha256(self) -> str:
        return sha256_text(self.text)

    def span(self, segment: str) -> tuple[int, int]:
        if segment not in self.segments:
            raise ValueError(f"segment {segment!r} is not located in page artifact {self.path}")
        start, end = self.segments[segment]
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(self.text):
            raise ValueError(f"invalid span for segment {segment!r}")
        return start, end

    def segment_text(self, segment: str) -> str:
        start, end = self.span(segment)
        return self.text[start:end]

    def verify(self, sources: PageSources) -> None:
        expected = dict(sources.parts)
        if sources.chrome_text is not None:
            expected[sources.chrome_id] = sources.chrome_text
        for segment, text in expected.items():
            if self.segment_text(segment) != text:
                raise ValueError(f"page artifact segment {segment!r} differs from the checked text")


@dataclass(frozen=True)
class SupportContext:
    run_id: str
    institution_uid: str
    observation_id: str | None
    source_id: str | None
    # Scoped to this observation/code; None = the derived-flag producer has not run.
    uncertainty_flags: Sequence[str] | None


@dataclass(frozen=True)
class SupportNodes:
    original: dict[str, Any]
    final: dict[str, Any] | None
    provenance: dict[str, Any]  # companion of ``original``: channel, span, matcher result


def _instrument_matcher(instrument: dict[str, Any]) -> dict[str, Any]:
    payload = validate_instrument(instrument)["payload"]
    actual = (payload["matcher_library"], payload["matcher_version"], payload["matcher_threshold"])
    if actual != (MATCHER_LIBRARY, PINNED_RAPIDFUZZ, MATCH_THRESHOLD):
        raise ValueError(f"instrument matcher {actual} is not the T-024 matcher "
                         f"{(MATCHER_LIBRARY, PINNED_RAPIDFUZZ, MATCH_THRESHOLD)}")
    return payload


def support_nodes(result: SupportResult, sources: PageSources, artifact: PageArtifact,
                  ctx: SupportContext, instrument: dict[str, Any]) -> SupportNodes:
    """Original (and, after a value downgrade, final) support nodes for one T-024 result."""
    if ctx.uncertainty_flags is None:
        raise MissingUpstreamError(UNCERTAINTY_FLAGS_PRODUCER, [f"{result.item_id}/{result.part}"])
    _instrument_matcher(instrument)
    if ctx.source_id is not None and artifact.source_id != ctx.source_id:
        raise ValueError("page artifact belongs to another source claim")
    artifact.verify(sources)
    quote = result.supporting_text
    segment = span = match = None
    if quote is not None:
        segment = result.quote_chunk_id
        if segment is None:
            raise ValueError("a quote without its source segment cannot be verified")
        span = artifact.span(segment)
        if result.match is not None:
            match = match_quote(quote, artifact.segment_text(segment))
            if match != result.match:
                raise ValueError("T-024 match result is not reproduced on the stored artifact")
    elif result.match is not None:
        raise ValueError("a match result without a quote")
    if result.support_status == "supported" and (match is None or not match.matched):
        raise ValueError("supported value lacks a reproduced R-042 match")
    second = result.support_status_second_reason or EMPTY_COMPANION
    rule = result.support_rule_name if result.support_status == SET_BY_RULE else EMPTY_COMPANION
    base = {"item_id": result.item_id, "item_part": result.part,
            "observation_id": ctx.observation_id, "source_id": ctx.source_id,
            "chunk_id": result.chunk_id, "support_rule_name": rule,
            "support_status_second_reason": second,
            "uncertainty_flags": list(ctx.uncertainty_flags),
            "page_content_sha256": artifact.sha256}
    original = {**base, "value_json": result.original_value, "supporting_text": quote or "",
                "support_status": result.support_status, "input_support_ids": [],
                "support_text_sha256": sha256_text(quote or ""),
                "passage": {"quote_segment": segment, "segment_span": None if span is None else list(span)}}
    original["support_id"] = support_id(ctx.run_id, ctx.institution_uid, original)
    final = None
    if result.value != result.original_value:
        final = {**base, "value_json": result.value, "supporting_text": "",
                 "support_status": result.support_status,
                 "input_support_ids": [original["support_id"]],
                 "support_text_sha256": sha256_text(""),
                 "passage": {"downgrade_of": original["support_id"]}}
        final["support_id"] = support_id(ctx.run_id, ctx.institution_uid, final)
    provenance = {
        "format": PROVENANCE_FORMAT, "support_id": original["support_id"],
        "quote_segment": segment,
        "channel": None if segment is None else "chrome" if segment == sources.chrome_id else "main",
        "segment_span": None if span is None else list(span),
        "match": None if match is None else asdict(match),
        "matcher": {"library": MATCHER_LIBRARY, "version": PINNED_RAPIDFUZZ, "metric": MATCH_METRIC,
                    "threshold": MATCH_THRESHOLD, "word_rule_cutoff": WORD_RULE_CUTOFF,
                    "decision": MATCH_DECISION},
        "check_flags": list(result.flags),
        "chosen_answer_probability": result.chosen_answer_probability,
        "final_support_id": None if final is None else final["support_id"],
    }
    return SupportNodes(original, final, provenance)


def downgrade_rule_reference(final: dict[str, Any]) -> str:
    return f"T-024 support_check: {final['support_status']} -> downgrade_target {final['value_json']}"


def coder_nodes(record: CoderRecord, nodes: SupportNodes, instrument: dict[str, Any]
                ) -> tuple[dict[str, Any], dict[str, Any] | None, CoderRecord | None]:
    """Storage coder records: the ORIGINAL projection, plus the linked mechanical final record.

    Returns ``(original_projection, final_projection, final_companion)``; the
    caller keeps ``record`` and ``final_companion`` as the complete companions.
    """
    original = nodes.original
    if record.support_id != original["support_id"]:
        raise ValueError("coder record is bound to another support")
    if record.downgrade_cause is not None and LOW_CONFIDENCE not in (
            original["support_status"], original["support_status_second_reason"]):
        raise ValueError("coder record is below the bar but the support check did not downgrade it")
    projection = record.storage_projection(support=original, instrument=instrument)
    if nodes.final is None:
        return projection, None, None
    final = nodes.final
    payload = validate_instrument(instrument)["payload"]
    companion = CoderRecord(
        item_id=final["item_id"], item_part=final["item_part"], question_id=None,
        support_id=final["support_id"], observation_id=final["observation_id"],
        chunk_id=final["chunk_id"], coder_type="mechanical",
        coder_version=payload["producer_code_revision"], configured_model=None,
        actual_response_model=None, request_id=None,
        question_set_version=payload["question_set_version"], setup_pointer=instrument["instrument_id"],
        answer_type="rule", chosen_value=final["value_json"], confidence=None,
        probability_distribution=None, rule_reference=downgrade_rule_reference(final))
    final_projection = {k: getattr(companion, k) for k in _STORAGE_FIELDS}
    final_projection.update(chosen_answer_probability=None, probability_distribution=None,
                            field_availability={k: NOT_APPLICABLE for k in (
                                *_PROVIDER_FIELDS, "chosen_answer_probability", "probability_distribution")})
    return projection, final_projection, companion


# ---------------------------------------------------------------------------
# Source confidence seam (T-015)
# ---------------------------------------------------------------------------


def source_confidence(source_id: str, t015_confidence: Mapping[str, str] | None) -> str:
    """The source-level confidence T-015 coded; this module never derives it."""
    if t015_confidence is None or source_id not in t015_confidence:
        raise MissingUpstreamError(SOURCE_CONFIDENCE_PRODUCER, [source_id])
    return t015_confidence[source_id]


def activity_confidence_value(source_ids: Sequence[str], t015_confidence: Mapping[str, str] | None,
                              independence_groups: Mapping[str, str]) -> str:
    """``core.confidence`` from already-coded source values (signed aggregation rule)."""
    return activity_confidence({s: source_confidence(s, t015_confidence) for s in source_ids},
                               {s: independence_groups[s] for s in source_ids})


# ---------------------------------------------------------------------------
# Envelope and artifacts
# ---------------------------------------------------------------------------


def _missing_values(table: str, key: str, values: Mapping[str, Any]) -> list[str]:
    expected = set(table_fields(table)) - METADATA_ITEMS
    return [f"{table}[{key}].{item} ({FIELDS[item]['coder']})" for item in sorted(expected - set(values))]


def assemble_storage(*, run_id: str, institution_uid: str, institution_id: str,
                     instrument: dict[str, Any], evidence_channel: str,
                     activities: Mapping[str, dict[str, Any]] | None,
                     sources: Mapping[str, dict[str, Any]] | None,
                     summary: dict[str, Any] | None, artifact_root: Path) -> StorageEnvelope:
    """Assemble and fully validate one institution's storage envelope.

    ``activities`` / ``sources`` rows come from the T-026 executor (final rows
    with ``observation_ids``, relations and keyed support/coder nodes built by
    :func:`support_nodes` / :func:`coder_nodes`); source values also need the
    T-015 fields. ``summary`` comes from ``consolidate_v27.summary_values``.
    """
    if evidence_channel not in CHANNELS:
        raise ValueError("invalid canonical evidence channel")
    if activities is None:
        raise MissingUpstreamError(STAGE6_EXECUTOR, ["activities"])
    if sources is None:
        raise MissingUpstreamError(STAGE6_EXECUTOR, ["sources"])
    if summary is None:
        raise MissingUpstreamError(SUMMARY_PRODUCER, ["summary"])
    missing: list[str] = []
    for table, rows in (("activities", activities), ("sources", sources)):
        for key, row in rows.items():
            missing += _missing_values(table, key, row.get("values", {}))
    missing += _missing_values("summary", "-", summary.get("values", {}))
    if missing:
        source_missing = [m for m in missing if m.startswith("sources[")]
        producer = f"{SOURCE_FIELDS_PRODUCER} / {STAGE6_EXECUTOR}" if source_missing else STAGE6_EXECUTOR
        raise MissingUpstreamError(producer, missing)
    data = {"format": "g3o-storage-v1", "run_id": run_id, "institution_uid": institution_uid,
            "institution_id": institution_id, "codebook_release": "2.7",
            "setup_pointer": instrument["instrument_id"], "evidence_channel": evidence_channel,
            "activities": dict(activities), "sources": dict(sources), "summary": summary}
    return StorageEnvelope(data, instrument, artifact_root=artifact_root)


def write_stage6_artifacts(inst_dir: Path, envelope: StorageEnvelope,
                           response: ConsolidatedInstitutionResponse | None) -> tuple[Path, Path]:
    """Write ``6_validate.json`` and ``6_storage.json`` for one institution, bound to each other."""
    if response is None:
        raise MissingUpstreamError(STAGE6_EXECUTOR, [VALIDATE_ARTIFACT])
    response = ConsolidatedInstitutionResponse.model_validate(response.model_dump(mode="json"))
    data = envelope.data
    if response.institution.institution_id != data["institution_id"]:
        raise ValueError("Stage 6 response and storage envelope name different institutions")
    if (set(data["activities"]) != {a.activity_id for a in response.activities}
            or set(data["sources"]) != {s.source_id for s in response.sources}):
        raise ValueError("storage row identifiers differ from consolidated rows")
    for table in ("activities", "sources", "summary"):
        rows = [data[table]] if table == "summary" else data[table].values()
        for row in rows:
            for private in ("_page_text", "_page_path"):
                row.pop(private, None)
    inst_dir.mkdir(parents=True, exist_ok=True)
    validate_path, storage_path = inst_dir / VALIDATE_ARTIFACT, inst_dir / STORAGE_ARTIFACT
    validate_path.write_bytes(canonical_json(response.model_dump(mode="json")).encode("utf-8"))
    storage_path.write_bytes(canonical_json(data).encode("utf-8"))
    return validate_path, storage_path
