"""v2.7 Stage 6 runtime (T-030): T-026 executor -> T-028 storage envelope -> Stage 6 artifacts.

Per institution this module runs :func:`g3o.validate.stage6_v27.run_stage6`
with its two injected calls (the jev call and the Stage 6 quote step) routed
through a durable request journal, then builds the D-007 storage envelope
through the T-028 adapters and writes ``6_validate.json``, ``6_storage.json``
and the internal ``6_support_provenance.json`` with
:func:`~g3o.validate.stage6_v27.write_stage6_outputs`. Stage 7
(:func:`g3o.persist.writer.write_run_csvs`) turns those into the final CSVs.

Rules carried here, not decided here:

- **Publication.** An institution whose Stage 6 result is not ``ready``
  (pending relation, held pooled answer, missing or contradictory relation
  decision) writes no Stage 6 artifact: its holds go to
  ``stage6_v27/held.json`` and the attrition ledger, and a later run retries
  it. Pending work is never published and never turned into a negative.
- **Durable resume.** Each provider response (jev answer, quote-step answer)
  is appended and fsynced to ``stage6_v27/journal.jsonl`` before it is used,
  keyed by the SHA256 of the canonical request and its occurrence number. A
  re-run replays recorded responses instead of calling again, so completed
  requests are not repeated. Failed requests are never replayed and are asked
  again: an exception is not recorded; a billed response with no request id, or
  with a request id but without the answer to a question it was asked
  (RC-D-030 Z1 b, ``jev_answer_missing`` / ``pooled_request_part_failed``; a
  Stage 6 rule, ``RequestJournal(retry_incomplete=True)``), is journaled for
  accounting only. A torn final journal line (an interruption while writing) is dropped.
  An interruption inside a provider call cannot be exactly once.
- **Accounting.** Token counts of every recorded jev response are kept in the
  journal, so a partial (interrupted) run's usage is recoverable from disk.
- **Storage nodes.** Per-page supports come from the caller (the T-023/T-028
  per-page producers). Stage 6 answers get nodes from
  :func:`g3o.persist.stage6_adapters.combined_support_nodes` (pooled and
  relation answers name the stored input supports they were built from);
  rule-set values (gate closed, relation pre-filter, permanent_pilot
  override) get ``set_by_rule`` nodes with their mechanical coder records.
- **Merged activities' non-pooled values (RC-D-030 X1 a; :func:`merge_values`).**
  Over the pooled (confirmed) observations in pool order: the list quote-step
  items (R2: ``tool_name``, ``model_name``, ``reported_outcomes``,
  ``reported_incidents``) are the union of the observations' entries, exact
  duplicates dropped after whitespace trim and case fold (the first-seen
  spelling kept, so its own support node carries it); the single-text
  quote-step items (R3: ``activity_name``, ``contracting_party``,
  ``observed_actor_name``; and ``deployment_scale_number``, RC-D-032 B2 a) come
  from the observation whose source has the
  highest T-015 source confidence (high > medium > low; ``unknown`` counts as
  low, C8 b), ties by pool order, a missing token never winning over a real
  value. An R2 item with no entry in any observation takes the value of the
  first observation in that R3 order (RC-D-032 B3 a; e.g. ``[]`` beside
  ``not_documented``). Every observation's nodes stay on the merged row.
- **A8 values of every published activity (PI A8 rulings 2026-11-11, 66 a,
  76 b, 77 a, 78 a, 88 a, 89 a, 90 c;** :mod:`g3o.validate.merged_activity_v27`**).**
  ``stage_as_of`` (the latest among the pooled observations' publication date /
  latest non-future supported year code, the access date only when none has a
  real date), ``date_upper_bound`` (of that date), ``unit_credit`` (any pooled
  observation's relationship ``unit_of_institution``), ``vendor_claim_only``
  (every supporting source ``vendor``; a missing type gives ``unknown``; an
  automatically typed page is typed, not vendor) and ``cx_display_rollup`` are
  produced from the pooled observations' rows and their source rows
  (:data:`MERGE_PRODUCED_A8`), for a single-observation activity too (78 a). An
  absent input holds the institution (B1 a); a latest date or upper bound the
  signed rule does not determine holds it (a PI question); a malformed stored
  value stops the stage (ruling 32 b, :class:`UpstreamRowMalformed`).
- **Values with no producer here** are explicit inputs and refuse when absent
  (:class:`~g3o.persist.stage6_adapters.MissingUpstreamError`): the merged
  values R1 asks to re-derive whose rule awaits codebook r16
  (:data:`MERGE_REFUSED_R1`: developer, developer_basis, stage_as_of_basis;
  under the UNSIGNED r16 candidate stage_as_of_basis is produced instead,
  :func:`merge_refused_r1`;
  ``evidence_channel`` is the row metadata
  :data:`EVIDENCE_CHANNEL`, not a row value), the merged values no ruling
  covers (:data:`MERGE_UNRULED`, now empty).
- **Uncertainty flags (PI A6.1-A6.4 a, 2026-11-11;**
  :mod:`g3o.validate.uncertainty_flags_v27`**).** Each Stage 6 node carries its
  own code's flags: a pooled ``core.adoption_stage`` node ``stage_ambiguous``
  when the pool parts' answers and the pooled observations' values differ, a
  cross-page relation node ``identity_unresolved`` when it is ``unresolved``.
  Every published activity's ``core.uncertainty_flags`` (:data:`MERGE_DERIVED`)
  is the union, alphabetical, of the flags its stored nodes carry (ruling 11),
  except ``identity_unresolved`` (PI ruling R1 a, 2026-11-12): that row flag
  goes on the left-hand activity of an unresolved cross-page relation, where
  the relation is filed, and only there, wherever the relation's node is stored
  (W4 b placement unchanged; the node keeps its own flag, A6.3 a).
- **Source independence groups** (PI A7.1 b, A7.2 a, 2026-11-11) are injected
  or else produced from the source rows (:func:`independence_groups_of`: same
  syndication group or same normalised URL, transitive closure); a source with
  no syndication group or URL is refused (no URL-only fallback).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.classify.jev_activity_code import NOT_COVERED, PAIR_ITEMS
from g3o.classify.permanent_pilot import PERMANENT_PILOT_RULE
from g3o.classify.questions.v27 import load_set
from g3o.common import attrition
from g3o.common.contract import LANGS_PATTERN
from g3o.common.independence import independence_groups_for_sources
from g3o.common.instrument import canonical_json
from g3o.common.jev_client import JevAnswer, JevResult, has_request_id
from g3o.common.jev_record import CoderRecord
from g3o.common.paths import institution_dir
from g3o.common.response_v27 import InstitutionIdentityV27
from g3o.common.run_state import clear_done, mark_done
from g3o.common.source_fields import MissingUpstreamError as SourceFieldsMissingUpstreamError
from g3o.common.source_fields import aggregation_value, confidence_field, default_vocab
from g3o.common.storage import METADATA_ITEMS, table_fields, unreviewed_source
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import (
    X35_NON_ANSWER,
    CodeEvidence,
    Entailment,
    PageSources,
    SupportResult,
    check_code,
)
from g3o.extract.anthropic_client import ExtractorResult
from g3o.extract.x35_client import X35ResponseError
from g3o.persist.stage6_adapters import (
    EMPTY_COMPANION,
    PROVENANCE_ARTIFACT,
    STORAGE_ARTIFACT,
    VALIDATE_ARTIFACT,
    InputSupport,
    MissingUpstreamError,
    PageArtifact,
    activity_confidence_value,
    assemble_storage,
    coder_nodes,
    combined_support_nodes,
    load_support_provenance,
    write_atomic,
)
from g3o.validate import merged_activity_v27 as ma
from g3o.validate import uncertainty_flags_v27 as uf
from g3o.validate.consolidate_v27 import (
    ActivityObservation,
    ConsolidationError,
    RelationDecision,
    ReviewedPage,
    outcome_values,
    summary_values,
)
from g3o.validate.stage6_quote import Stage6QuoteStep
from g3o.validate.stage6_v27 import (
    MISSING_UPSTREAM,
    STAGE6_STOPS,
    AskFn,
    InputQuote,
    ObservationRecord,
    PooledActivity,
    QuoteFn,
    Stage6Config,
    Stage6Quote,
    Stage6QuoteRequest,
    Stage6Result,
    observation_pool_order,
    pool_eligible,
    run_stage6,
    source_claim_confidence,
    source_claim_records,
    write_stage6_outputs,
)

STAGE = "validate"
#: ruling 48.3 a: ``_state/.done/<DONE_MARKER>.json``, written once the whole pass finished (no stage
#: stop); named apart from v2.5's ``validate`` marker. The run report reads it for an unheld institution
#: as v2.5 reads its validate marker.
DONE_MARKER = "stage6_v27"
WORK_DIR = "stage6_v27"
JOURNAL = "journal.jsonl"
HELD_FILE = "held.json"
HELD_REASON = "stage6_held"  # attrition reason ``stage6_held:<hold reason>``, one record per hold reason
HELD_RELEASED = "stage6_held_released"  # appended when a held institution is later published
ENVELOPE_FAILED = "stage6_envelope_failed"  # the storage envelope / artifacts of one institution failed
EXECUTOR_FAILED = "stage6_executor_failed"  # the T-026 executor refused or failed for one institution
#: Errors that stop the whole stage (an account stop, an unapproved quote prompt, a support-gate
#: refusal, a spend stop), in the executor and in the envelope build alike. One tuple with the
#: executor's (:data:`g3o.validate.stage6_v27.STAGE6_STOPS`), which re-raises it inside
#: ``ask_fn``, ``quote_fn`` and the combiner.
STAGE_STOPS = STAGE6_STOPS
#: :data:`MISSING_UPSTREAM` (from :mod:`g3o.validate.stage6_v27`): both ``MissingUpstreamError``
#: classes. Raised inside the executor (``ask_fn``, ``quote_fn``, the combiner, or here around it)
#: they stop the stage, as in the per-page stage (B1 a, RC-D-033 C2 a); raised while building
#: the envelope they hold that institution only (:data:`ENVELOPE_FAILED`).
#: Per-institution outcomes of the envelope build and artifact writes (B3): refusals
#: (``ConsolidationError``, ``ValueError`` including both ``MissingUpstreamError`` classes, the
#: R1 refusals among them, and pydantic validation errors), ``RuntimeError``, and ``OSError`` from
#: the artifact writes (held as before B3). Stage stops and programming errors propagate.
ENVELOPE_HOLDS = (ConsolidationError, ValueError, RuntimeError, OSError)


class UpstreamRowMalformed(Exception):  # noqa: N818 - names the wiring defect, as MissingUpstreamError does
    """Ruling 32 b: a malformed upstream row reached Stage 6 (a wiring error, not institution data).

    Raised for an institution row missing one of the master identity columns
    (checked before the executor, so nothing is asked for it) and for a
    ``KeyError`` while building the storage envelope (e.g. a source row without
    ``core.source_credibility``, which Stage 6 reads to produce ``core.confidence``, PI ruling 140). It stops the stage (:data:`WIRING_STOPS`); it is never a
    per-institution hold. ``institution_id`` and ``field`` name what is missing
    (or, with ``problem``, what is malformed, e.g. a language value outside the schema pattern).
    """

    def __init__(self, institution_id: str, field: str, where: str, problem: str = "is missing") -> None:
        super().__init__(f"malformed upstream row for {institution_id}: {field} {problem} ({where}); a wiring "
                         "or programming error, the stage stops (ruling 32 b)")
        self.institution_id, self.field, self.where, self.problem = institution_id, field, where, problem


#: Ruling 32 b: wiring errors that stop the stage here, beside :data:`STAGE_STOPS`.
WIRING_STOPS = (UpstreamRowMalformed,)
IDENTITY_COLUMNS = tuple(InstitutionIdentityV27.model_fields)
#: identity columns the schema requires non-empty (``min_length=1``): an empty string there is missing
NON_EMPTY_IDENTITY_COLUMNS = ("institution_id",)
#: the schema's own constraint on ``institution_search_languages`` (``InstitutionIdentityV27``)
_LANGS = re.compile(LANGS_PATTERN)


def require_identity(inst: Stage6Institution) -> None:
    """Ruling 32 b: refuse (stage stop) an institution row missing a master identity column, or with
    a null (``None``) value in one, or an empty ``institution_id`` (``InstitutionIdentityV27`` requires
    ``min_length=1``), or an ``institution_search_languages`` value outside the schema's
    ``LANGS_PATTERN``; :func:`run_stage6_v27` checks every row before its first call."""
    row = inst.institution
    missing = [c for c in IDENTITY_COLUMNS
               if row.get(c) is None or (c in NON_EMPTY_IDENTITY_COLUMNS and row.get(c) == "")]
    ident = row.get("institution_id")
    label = str(ident) if ident not in (None, "") else "<no institution_id>"
    if missing:
        raise UpstreamRowMalformed(label, ", ".join(missing), "institution identity columns")
    langs = row["institution_search_languages"]
    if not isinstance(langs, str) or _LANGS.fullmatch(langs) is None:
        raise UpstreamRowMalformed(label, "institution_search_languages", "institution identity columns",
                                   problem=f"is malformed ({langs!r} does not match LANGS_PATTERN)")


def require_a8_form(inst: Stage6Institution) -> None:
    """Ruling 32 b (A8 review L1): refuse (stage stop) an institution whose stored A8 inputs are outside
    their signed form (:func:`g3o.validate.merged_activity_v27.check_a8_inputs`), before any paid call.
    Absent A8 inputs are not checked here: the producers hold the institution in the envelope build
    (B1 a)."""
    try:
        ma.check_a8_inputs(inst)
    except ma.MalformedA8Value as exc:
        raise UpstreamRowMalformed(inst.institution_id, exc.item, f"A8 inputs, {exc.where}",
                                   problem=f"is malformed ({exc.detail})") from exc


ARTIFACTS_UNREADABLE = "stage6_artifacts_unreadable"  # existing Stage 6 artifacts fail to reload
MISSING_RELATION = "missing_relation_decision"
CONFLICTING_GROUPS = "conflicting_relation_groups"
POOLED_STOPPED = "pooled_question_stopped"  # combiner refused, or its gate item stopped
POOLED_PENDING = "pooled_question_pending"  # e.g. its gate item is pending
NOT_READY = "stage6_not_ready"  # defensive: not ready for no reason named above
EVIDENCE_CHANNEL = "web_extract"
ACTIVITY_ITEMS = frozenset(table_fields("activities"))

#: RC-D-030 X1 a R2 / R3 (RC-D-032 B2 a adds the scale number to R3): merged by rule here.
MERGE_UNION = ("core.tool_name", "core.model_name", "core.reported_outcomes", "core.reported_incidents")
MERGE_CREDIBLE = ("core.activity_name", "core.contracting_party", "core.observed_actor_name",
                  "core.deployment_scale_number")
#: X1 a R1 items produced here from the pooled observations and their source rows (PI A8 rulings,
#: 2026-11-11, and 66 a; :mod:`g3o.validate.merged_activity_v27`): stage_as_of (A8.3/A8.4/A8.6 a,
#: 76 b, 90 c), date_upper_bound (A8.11/A8.12 a), unit_credit (A8.7/A8.8 a), vendor_claim_only
#: (A8.9 a, 88 a, 89 a), cx_display_rollup (A8.10 a, table approved by 77 a). Ruling 78 a: for every
#: published activity, single-observation ones included.
MERGE_PRODUCED_A8 = ma.PRODUCED
#: X1 a R1 items refused under the signed r15 codebook (explicit input): developer/developer_basis (A8.1 a:
#: a developer quote item, codebook r16 and a re-signature first; A8.2 a: no lookup table),
#: stage_as_of_basis (A8.5 a: three step codes, codebook r16). evidence_channel is row metadata, not a value.
MERGE_REFUSED_R1_R15 = ("core.developer", "core.developer_basis", "core.stage_as_of_basis")


def merge_refused_r1(r16_on: bool | None = None) -> tuple[str, ...]:
    """X1 a R1 items still refused (explicit input) for the codebook in use (``r16_on`` None: read
    :func:`g3o.codebook.r16_candidate.r16_active` now). Under the UNSIGNED r16 candidate (PI ruling 140:
    built against the draft) stage_as_of_basis is produced here (:func:`ma.produced_items`); developer and
    developer_basis stay explicit inputs for a multi-observation activity: the candidate gives no merge rule
    for them (a PI question)."""
    produced = set(ma.produced_items(r16_on))
    return tuple(i for i in MERGE_REFUSED_R1_R15 if i not in produced)


MERGE_REFUSED_R1 = merge_refused_r1()
#: Whether the envelope adds the r16 A8 value (stage_as_of_basis): fixed with the item split above at import.
_R16_A8 = ma.STAGE_AS_OF_BASIS in MERGE_PRODUCED_A8
#: Keyword passed to ``ma.merged_values_a8``: none under r15, so the r15 call is unchanged (review O2-r16 H1).
_A8_KW: dict[str, bool] = {"r16_on": True} if _R16_A8 else {}
#: Non-pooled activity items no merge rule covers (explicit input). Empty since A6 (2026-11-11).
MERGE_UNRULED: tuple[str, ...] = ()
#: Derived here from the row's stored nodes (A6.4 a: union, alphabetical).
MERGE_DERIVED = (uf.ITEM,)
MERGE_INPUT_ITEMS = frozenset(MERGE_REFUSED_R1 + MERGE_UNRULED)
MERGED_VALUES_PRODUCER = ("merged-activity values with no rule computable from the merged row (RC-D-030 X1 a "
                          "R1 refused, or unruled): " + ", ".join(MERGE_REFUSED_R1 + MERGE_UNRULED))


def _non_pooled_items() -> frozenset[str]:
    pooled = {q["item_id"] for q in load_set("activity")["questions"]}
    return ACTIVITY_ITEMS - pooled - set(METADATA_ITEMS) - {"core.n_sources", "core.confidence"}


if (_non_pooled_items() != (MERGE_INPUT_ITEMS | set(MERGE_UNION) | set(MERGE_CREDIBLE) | set(MERGE_DERIVED)
                            | set(MERGE_PRODUCED_A8))
        or len(MERGE_INPUT_ITEMS) + len(MERGE_UNION) + len(MERGE_CREDIBLE) + len(MERGE_DERIVED)
        + len(MERGE_PRODUCED_A8) != len(_non_pooled_items())):  # pragma: no cover - overlap or gap
    raise RuntimeError("the merged-activity item split no longer matches the activities table")
INDEPENDENCE_PRODUCER = "near-duplicate / syndication grouping (P15) for source independence groups"


# ---------------------------------------------------------------------------
# Durable request journal
# ---------------------------------------------------------------------------


def _answer_to_json(answer: JevAnswer) -> dict[str, Any]:
    # The probabilities go in as ordered [key, value] pairs: the journal line is written with
    # sort_keys and JSON object keys are strings, so a mapping would come back re-ordered (and a
    # score's int keys as strings). A CoderRecord keeps the provider's order and stores it as
    # pairs (jev_record), so a replayed response must give the same bytes as the live one.
    doc = asdict(answer)
    if isinstance(answer.probabilities, Mapping):
        doc["probabilities"] = [[k, v] for k, v in answer.probabilities.items()]
    return doc


def _answer_from_json(doc: Mapping[str, Any]) -> JevAnswer:
    probabilities = doc.get("probabilities")
    if isinstance(probabilities, list):
        doc = {**doc, "probabilities": {k: v for k, v in probabilities}}
    return JevAnswer(**doc)


def _jev_to_json(result: JevResult) -> dict[str, Any]:
    return {"answers": {k: _answer_to_json(v) for k, v in result.answers.items()},
            "response_model": result.response_model, "request_id": result.request_id,
            "input_tokens": result.input_tokens, "output_tokens": result.output_tokens}


def _jev_from_json(doc: Mapping[str, Any]) -> JevResult:
    answers = {k: _answer_from_json(v) for k, v in doc["answers"].items()}
    return JevResult(answers, doc["response_model"], doc["request_id"], doc["input_tokens"], doc["output_tokens"])


def _quote_to_json(answer: Stage6Quote) -> dict[str, Any]:
    return {"quote": answer.quote, "input_support_id": answer.input_support_id,
            "entailment": None if answer.entailment is None else asdict(answer.entailment),
            "provenance": None if answer.provenance is None else dict(answer.provenance)}


def _quote_from_json(doc: Mapping[str, Any]) -> Stage6Quote:
    ent = doc["entailment"]
    return Stage6Quote(doc["quote"], doc["input_support_id"], None if ent is None else Entailment(**ent),
                       doc["provenance"])


#: Entry kinds replayed on resume (a completed provider answer).
REPLAYED_KINDS = frozenset({"jev", "quote", "extract", "x35"})
#: Entry kinds kept for accounting only: billed or attempted calls that did not complete.
#: They are never replayed; the request is asked again (a failed request, PI 2026-11-08 2.17).
#: One exception: :data:`JEV_UNIDENTIFIED` for a re-ask after a page halving (ruling 75 a).
#: ``jev_incomplete``: a response with a request id that lacks the answer to a question it was
#: asked (RC-D-030 Z1 b, a pooled Stage 6 rule: the question is held and asked again on the next
#: run, never replayed). Only a journal built with ``retry_incomplete=True`` (Stage 6) writes it.
#: ``extract_rejected`` (per-page stage, C3 a): a recorded extractor response the caller could not
#: parse (:meth:`RequestJournal.reject_extract`); it cancels that ``extract`` entry, so the request
#: is asked again on the next run, and carries the response so its tokens are counted once.
EXTRACT_REJECTED = "extract_rejected"
#: A billed jev response without a request id. Accounting only, except that a re-ask after a page
#: halving replays it as its final failure (PI ruling 75 a; :meth:`RequestJournal.ask`, ``reask``).
JEV_UNIDENTIFIED = "jev_unidentified"
ACCOUNTING_KINDS = frozenset({JEV_UNIDENTIFIED, "jev_incomplete", "extract_failed", "x35_failed",
                              EXTRACT_REJECTED})
#: The marker on an ``x35_failed`` entry whose exception came with no response at all
#: (``response[X35_USAGE_ABSENT] == X35_NO_RESPONSE``): counted, never priced (PI ruling 131.1 b).
X35_USAGE_ABSENT = "usage_absent"
X35_NO_RESPONSE = "no_response"


def _x35_no_response(response: Mapping[str, Any]) -> bool:
    """Whether an ``x35_failed`` entry's response is the PI ruling 131.1 b no-response marker."""
    return response.get(X35_USAGE_ABSENT) == X35_NO_RESPONSE


class X35FailCapReached(RuntimeError):
    """Review O2 M4: an X35 request came back without a usable answer :data:`EXTRACT_REJECT_CAP` times.

    PI ruling Q169 b (2026-11-16) made this an inert backstop. An X35 non-answer (an
    ``X35ResponseError``: a refusal, a ``max_tokens`` stop, unparseable output) is no longer an
    ``x35_failed`` entry: it is journaled as a replayed ``x35`` answer with no probability
    (:meth:`RequestJournal._entail`), so a resume replays it and never re-bills it, and it never
    counts here. What still counts is an ``x35_failed`` entry that carries a response but is not
    a non-answer: an exception with a ``usage`` attribute other than ``X35ResponseError``, which
    the production client does not raise, or such an entry in a journal written before Q169 b.

    Mirrors :class:`ExtractRejectCapReached` (ruling 34 b / 41 a), with the same cap: after that
    many such entries for one exact X35 request key (NOT the ``no_response`` ones, which are asked
    again), the journaled X35 call raises this *instead of* calling X35, on this run and every
    later load, until a per-page PI release names the key (or releases ``all``); Stage 6 has no
    release path for it (REVIEW-O2-fixes M1). A ``RuntimeError``, so the stages hold exactly
    as they hold the failure it replaces, with no billed call. ``key`` is the journal's request key.
    """

    def __init__(self, key: str, failures: int) -> None:
        super().__init__(f"X35 request {key} came back without a usable answer {failures} times (cap "
                         f"{EXTRACT_REJECT_CAP}): permanent hold, no further X35 call until the PI releases "
                         "the key (mirrors ruling 34 b / 41 a)")
        self.key, self.failures = key, failures
#: Ruling 34 b / 41 a: after this many ``extract_rejected`` entries for one exact extractor request
#: key (``extract_failed`` entries do not count) the request is a permanent hold: the journal makes
#: no further live call for it (:class:`ExtractRejectCapReached`) until the PI releases it.
EXTRACT_REJECT_CAP = 3
#: Ruling 34 b / 41 a: a PI release applied to this journal (written by
#: :meth:`RequestJournal.record_release`); ``extract_rejected`` entries for the released keys that
#: come before it no longer count towards :data:`EXTRACT_REJECT_CAP`. Never replayed or accounted.
#: PI ruling 104 b (2026-11-14): its ``reask_keys`` (request keys held under 98 b, named in the release file)
#: each authorise ONE live re-ask, consumed (:meth:`RequestJournal.reask_authorised`) on this run and on every
#: later load by the :data:`REASK_SPENT` entry written before that call (PI ruling 114 b).
PI_RELEASED = "pi_released"
#: PI ruling 114 b (2026-11-14): written (fsynced) just before the live extractor call a PI release authorised,
#: it uses that re-ask up, whatever happens next: a failure before or while sending (an exception, a timeout,
#: a crash) wastes the release, and the PI drops a new file (different bytes; identical bytes are only
#: archived, ruling 47.2 a). Never replayed or accounted: ``response`` is ``{}``. Review H-1: while no response
#: to the key is recorded after it (and no new release authorises the key), the journal refuses a live call of
#: that key (:class:`ReaskSpentUnanswered`).
#: PI ruling 120 c (2026-11-14): also written before the live jev call a release authorised (a residual
#: ``source_type`` deciding part whose response has a request id but no answer, replayed every run); its ``n``
#: is the jev slot re-asked, and from it on the response recorded in that slot before is no longer replayed
#: (it is still counted in :meth:`RequestJournal.usage`, :data:`JEV_SUPERSEDED`). The response the re-ask gets
#: is journaled in the same slot (``jev``) and replayed afterwards.
REASK_SPENT = "reask_spent"
#: PI ruling 120 c: a ``jev`` response displaced by a released jev re-ask (its :data:`REASK_SPENT` entry). In
#: memory only (never written): kept for :meth:`RequestJournal.usage`, so the billed response is still counted.
JEV_SUPERSEDED = "jev_superseded"
#: the journal entry kinds that record a live extractor call; they also consume a 104 b re-ask authorisation
#: (journals written before PI ruling 114 b have no :data:`REASK_SPENT` entry)
_LIVE_EXTRACT_KINDS = frozenset({"extract", "extract_failed"})
#: the replayed kinds a re-ask authorisation can concern (PI rulings 104 b / 120 c)
_REASK_KINDS = ("extract", "jev")


class ExtractRejectCapReached(Exception):  # noqa: N818 - named after the ruling's event, like ExtractorResponseFailed
    """Ruling 34 b / 41 a: an extractor request was rejected :data:`EXTRACT_REJECT_CAP` times.

    Raised by the journaled extractor call *instead of* calling the extractor.
    ``key`` is the journal's request key (SHA256 over setup, prompt and request),
    ``rejections`` the count since the last PI release of that key, ``custom_id``
    the request's id; ``pass_name`` is filled in by the provider adapter when it
    knows the pass. Not a stage stop: the per-page stage holds the institution.
    """

    def __init__(self, key: str, rejections: int, custom_id: Any, pass_name: str | None = None) -> None:
        super().__init__(f"extractor request {key} ({custom_id!r}) was rejected {rejections} times: permanent "
                         f"hold, no further call until the PI releases it (ruling 34 b / 41 a)")
        self.key, self.rejections, self.custom_id, self.pass_name = key, rejections, custom_id, pass_name


class ReaskSpentUnanswered(Exception):  # noqa: N818 - names the hold, as ExtractRejectCapReached does
    """PI ruling 114 b (review H-1): a live extractor call of a key whose PI-released re-ask was used up.

    The key has a :data:`REASK_SPENT` entry, no recorded response to replay (the call died while sending,
    timed out, came back ``extract_failed``, or its response was rejected, ``extract_rejected``) and no
    unused re-ask authorisation: the call would be an unauthorised live re-ask, so the journaled extractor
    call raises this *instead of* calling the extractor, also when no ``pass1_requests.json`` triggers the
    provider-level 105 b check (it was archived by the 113 b re-ask). Not a stage stop: the provider adapter
    turns it into the 98 b / 105 b not-journaled hold of the request's kind (``held.json`` names the
    ``request_key``), which a NEW ``pi_release.json`` (other bytes, ruling 47.2 a) releases for one more re-ask
    (PI ruling 104 b). ``key`` is the journal's request key, ``custom_id`` the request's id.

    PI ruling 120 c: also raised (``kind`` ``"jev"``, ``custom_id`` None) by the journaled jev call of a released
    residual ``source_type`` part whose re-ask was used up with no response recorded since (it raised, timed out
    or came back with no request id); the page coder records it as that part's failed request, so the stage
    holds the institution again (``source_type_residual_part_failed``, naming the ``request_key``)."""

    def __init__(self, key: str, custom_id: Any, kind: str = "extractor") -> None:
        super().__init__(f"{kind} request {key} ({custom_id!r}): its PI-released re-ask was used up (a "
                         f"{REASK_SPENT} entry) and no response to it is recorded; no live call without a new "
                         "release naming this key in its \"keys\" (an \"all\" release authorises no re-ask; PI "
                         "rulings 104 b / 114 b)")
        self.key, self.custom_id, self.kind = key, custom_id, kind


def _tokens(usage: Mapping[str, Any] | None, name: str) -> int:
    value = (usage or {}).get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _elapsed_ms(start: float) -> int:
    return max(0, round((time.monotonic() - start) * 1000))


class RequestJournal:
    """Append-only, fsynced record of Stage 6 provider responses for one institution.

    Keys are the SHA256 of ``{"setup": setup, "request": request}``, so a response
    recorded under another setup (setup pointer, configured model, coder or
    quote-prompt version) is never replayed. Every entry carries the call's
    ``elapsed_ms``. A record missing only its trailing newline is terminated, and
    a torn final record is dropped, by an atomic rewrite before anything is appended.

    ``retry_incomplete`` (Stage 6 only; RC-D-030 Z1 b): a jev response with a request
    id but without the answer to a question it was asked is journaled ``jev_incomplete``
    (accounting only, never replayed), so the next run asks it again. Off (the per-page
    stage), such a response is a completed response and is replayed on resume, where the
    missing answer is a failed part vote exactly as in an uninterrupted run.

    The function :meth:`ask` returns also has a ``reask`` attribute, used by
    :func:`~g3o.classify.question_rounds.complete_page_rounds` for a re-ask after a page
    halving (PI ruling 75 a). It differs only for a ``jev_unidentified`` entry of that
    exact request key: the recorded response is replayed (no new call, nothing appended),
    so the re-ask is read again as its final ``jev_missing_request_id`` failure on a resume
    interrupted before the page state was saved, or after the page state was archived and
    the page recoded (ruling 33 a). The billed request is sent and accounted once.
    """

    def __init__(self, path: Path, setup: Mapping[str, Any] | None = None, *,
                 retry_incomplete: bool = False, read_only: bool = False) -> None:
        self.path = path
        self.setup = dict(setup or {})
        self.retry_incomplete = retry_incomplete
        #: accounting reads (the cost report): the load skips a torn tail without repairing
        #: it, and any append raises; the file is never written
        self.read_only = read_only
        self._recorded: dict[tuple[str, str, int], dict[str, Any]] = {}
        #: ``jev_unidentified`` responses by (key, n), first written kept: replayed only by ``ask(...).reask``
        self._unidentified: dict[tuple[str, int], dict[str, Any]] = {}
        self._accounting: list[dict[str, Any]] = []
        self._elapsed: list[int] = []
        self._seen: dict[tuple[str, str], int] = {}
        #: ruling 34 b / 41 a: request key -> ``extract_rejected`` entries since its last PI release
        self._rejections: dict[str, int] = {}
        #: review O2 M4: X35 request key -> ``x35_failed`` entries carrying a response since its last PI release
        self._x35_failures: dict[str, int] = {}
        self._releases: set[str] = set()  # file_sha256 of every PI release applied to this journal
        #: PI ruling 104 b: request keys a PI release authorised for one live re-ask, not yet used
        self._reask: set[str] = set()
        #: PI ruling 114 b (review H-1): request keys with a :data:`REASK_SPENT` entry. Such a key is never
        #: called live again unless a new release authorises it (:meth:`reask_spent_unanswered`)
        self._spent: set[str] = set()
        #: PI ruling 134: (request key, batch id) of every extractor result journaled from a Message Batch;
        #: a stored batch result is journaled once (:meth:`_extract`)
        self._batch_used: set[tuple[str, str]] = set()
        self.live = 0
        self.replayed = 0
        self.batched = 0  # PI ruling 134: results journaled from a Message Batch
        if path.exists():
            self._load()

    def _load(self) -> None:
        raw = self.path.read_bytes()
        lines = raw.split(b"\n")
        complete = raw.endswith(b"\n") or not raw
        keep: list[bytes] = []
        for n, line in enumerate(lines):
            if not line.strip():
                continue
            last = n == len(lines) - 1
            try:
                entry = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                if last:  # torn final record: the write was interrupted; drop it (PI ruling 131.2 a:
                    # accepted that this can leave at most one billed call out of every report)
                    break
                raise ValueError(f"corrupt Stage 6 journal line {n + 1}: {self.path}") from None
            keep.append(line)
            self._elapsed.append(int(entry.get("elapsed_ms", 0)))
            self._mark_batch(entry)
            if entry["kind"] in _LIVE_EXTRACT_KINDS:  # ruling 104 b: a live call uses up its re-ask
                self._reask.discard(entry["key"])
            if entry["kind"] == PI_RELEASED:
                self._apply_release(entry["response"])
            elif entry["kind"] == REASK_SPENT:  # PI ruling 114 b: used up before its call
                self._mark_spent(entry["key"], entry.get("n", 0))
            elif entry["kind"] in ACCOUNTING_KINDS:
                self._accounting.append(entry)
                if entry["kind"] == JEV_UNIDENTIFIED:
                    self._unidentified.setdefault((entry["key"], entry["n"]), entry["response"])
                if entry["kind"] == EXTRACT_REJECTED:
                    self._recorded.pop(("extract", entry["key"], entry["n"]), None)
                    self._rejections[entry["key"]] = self._rejections.get(entry["key"], 0) + 1
                self._count_x35_failure(entry["kind"], entry["key"], entry["response"])
            else:
                self._recorded[(entry["kind"], entry["key"], entry["n"])] = entry["response"]
        if not complete and not self.read_only:  # unterminated or torn tail: repair before the next append
            write_atomic(self.path, b"".join(line + b"\n" for line in keep))

    def _key(self, request: Any, extra: Mapping[str, Any] | None = None) -> str:
        doc = {"setup": {**self.setup, **(extra or {})}, "request": request}
        return hashlib.sha256(canonical_json(doc).encode("utf-8")).hexdigest()

    def _slot(self, kind: str, request: Any, extra: Mapping[str, Any] | None = None) -> tuple[str, str, int]:
        key = self._key(request, extra)
        n = self._seen.get((kind, key), 0)
        self._seen[(kind, key)] = n + 1
        return kind, key, n

    def _write(self, entry: Mapping[str, Any]) -> None:
        if self.read_only:
            raise RuntimeError(f"journal opened read-only (accounting): {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with self.path.open("ab") as stream:
            stream.write(line.encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _append(self, slot: tuple[str, str, int], response: dict[str, Any], elapsed_ms: int) -> None:
        entry = {"kind": slot[0], "key": slot[1], "n": slot[2], "response": response, "elapsed_ms": elapsed_ms}
        self._write(entry)
        self._mark_batch(entry)
        self._elapsed.append(elapsed_ms)
        if slot[0] in _LIVE_EXTRACT_KINDS:  # ruling 104 b: a live call uses up its re-ask
            self._reask.discard(slot[1])
        if slot[0] in ACCOUNTING_KINDS:
            self._accounting.append(entry)
            if slot[0] == JEV_UNIDENTIFIED:
                self._unidentified.setdefault((slot[1], slot[2]), response)
            if slot[0] == EXTRACT_REJECTED:
                self._recorded.pop(("extract", slot[1], slot[2]), None)
                self._rejections[slot[1]] = self._rejections.get(slot[1], 0) + 1
            self._count_x35_failure(slot[0], slot[1], response)
        else:
            self._recorded[slot] = response

    def _mark_batch(self, entry: Mapping[str, Any]) -> None:
        """PI ruling 134: an extractor entry carrying a ``batch_id`` consumed that stored batch result."""
        response = entry.get("response")
        batch_id = response.get("batch_id") if isinstance(response, dict) else None
        if entry.get("kind") in (*_LIVE_EXTRACT_KINDS, EXTRACT_REJECTED) and isinstance(batch_id, str):
            self._batch_used.add((entry["key"], batch_id))

    # --- ruling 34 b / 41 a: the rejection cap and its PI release ------------

    def _count_x35_failure(self, kind: str, key: str, response: Mapping[str, Any]) -> None:
        """Review O2 M4: count an ``x35_failed`` entry that carries a response (not ``no_response``)."""
        if kind == "x35_failed" and not _x35_no_response(response):
            self._x35_failures[key] = self._x35_failures.get(key, 0) + 1

    def x35_failures(self, key: str) -> int:
        """``x35_failed`` entries with a response for X35 request ``key`` since its last PI release (O2 M4)."""
        return self._x35_failures.get(key, 0)

    def _apply_release(self, release: Mapping[str, Any]) -> None:
        # review O2 M4: a release clears the X35 failure cap of the keys it names, as it clears rejections
        if release.get("all") is True:
            self._rejections.clear()
            self._x35_failures.clear()
        else:
            for key in release["keys"]:
                self._rejections.pop(key, None)
                self._x35_failures.pop(key, None)
        self._releases.add(release["file_sha256"])
        self._reask.update(release.get("reask_keys") or ())  # ruling 104 b (absent in older entries)

    def reask_authorised(self, key: str) -> bool:
        """PI ruling 104 b: a recorded PI release named ``key`` (a 98 b / 105 b hold; PI ruling 120 c: the jev
        request of a 110 b residual-part hold) for one live re-ask, and since then neither a :data:`REASK_SPENT`
        entry (PI ruling 114 b) nor a live extractor call of ``key`` (``extract`` / ``extract_failed``) has been
        journaled."""
        return key in self._reask

    def _spend_reask(self, key: str, n: int = 0) -> None:
        """PI ruling 114 b: append (fsynced) the :data:`REASK_SPENT` entry of ``key`` before its live call.
        An ``OSError`` writing it propagates before any call, leaving the authorisation unspent. ``n``: the slot
        re-asked (PI ruling 120 c, a jev re-ask; 0 for an extractor re-ask, whose slot holds no response)."""
        self._write({"kind": REASK_SPENT, "key": key, "n": n, "response": {}, "elapsed_ms": 0})
        self._elapsed.append(0)
        self._mark_spent(key, n)

    def _mark_spent(self, key: str, n: int) -> None:
        """A :data:`REASK_SPENT` entry of ``key`` (slot ``n``), written now or loaded: the authorisation is used
        up, and (PI ruling 120 c) a ``jev`` response recorded in that slot before it is no longer replayed; it is
        kept as :data:`JEV_SUPERSEDED` for the usage totals. An extractor key has no ``jev`` slot (the keys hash
        different requests), so nothing is displaced for it."""
        self._reask.discard(key)
        self._spent.add(key)
        displaced = self._recorded.pop(("jev", key, n), None)
        if displaced is not None:
            self._accounting.append({"kind": JEV_SUPERSEDED, "key": key, "n": n, "response": displaced})

    def reask_spent_unanswered(self, key: str, n: int | None = None, kind: str | None = None) -> bool:
        """PI ruling 114 b (review H-1): ``key``'s PI-released re-ask was used up (a :data:`REASK_SPENT` entry),
        no unused authorisation is left, and no response to replay is recorded for its next slot (``n``;
        default: the next one this process would use) of ``kind`` (``"extract"`` or, PI ruling 120 c, ``"jev"``;
        None: either). Then a live call of ``key`` is refused (:class:`ReaskSpentUnanswered`): after the marker,
        a crash while sending, a timeout, an ``extract_failed`` result or an ``extract_rejected`` response (a
        jev call that raised or came back with no request id) all leave the key here, on this run and on every
        later load, until a new release (other bytes) authorises one more re-ask."""
        if key not in self._spent or self.reask_authorised(key):
            return False
        kinds = _REASK_KINDS if kind is None else (kind,)
        return not any((k, key, self._seen.get((k, key), 0) if n is None else n) in self._recorded for k in kinds)

    def extract_key(self, request: Mapping[str, Any], prompt: Mapping[str, Any]) -> str:
        """The journal key of an extractor request (``custom_id``, ``params``) under ``prompt``."""
        return self._key(dict(request), dict(prompt))

    def rejections(self, key: str) -> int:
        """``extract_rejected`` entries for ``key`` since its last PI release (ruling 34 b / 41 a)."""
        return self._rejections.get(key, 0)

    def release_applied(self, file_sha256: str) -> bool:
        """Whether a PI release file with these bytes was already recorded in this journal."""
        return file_sha256 in self._releases

    def record_release(self, release: Mapping[str, Any]) -> None:
        """Append a :data:`PI_RELEASED` entry (ruling 34 b / 41 a); never rewrites earlier lines.

        ``release`` holds ``keys`` (a list, or None with ``all`` true), ``all``,
        ``released_by``, ``date`` and ``file_sha256``. From this entry on, the
        rejections recorded before it no longer count for the released keys.
        """
        doc = dict(release)
        self._write({"kind": PI_RELEASED, "key": doc["file_sha256"], "n": 0, "response": doc, "elapsed_ms": 0})
        self._elapsed.append(0)
        self._apply_release(doc)

    def ask(self, ask_fn: AskFn) -> AskFn:
        """``ask_fn`` journaled; the returned function's ``reask`` attribute is the same call for a
        re-ask after a page halving, which also replays a ``jev_unidentified`` entry (ruling 75 a)."""
        def wrapped(state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> JevResult:
            return self._ask(ask_fn, state, questions, final_unidentified=False)

        def reask(state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> JevResult:
            return self._ask(ask_fn, state, questions, final_unidentified=True)

        def request_key(state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> str:
            """PI ruling 120 c: the journal key of this jev request (what ``held.json`` names in
            ``request_key`` and a ``pi_release.json`` key names). Uses no slot."""
            return self._key({"state": state, "questions": questions})

        def spent_unanswered(key: str) -> bool:
            """PI ruling 120 c: after this process asked jev request ``key``, whether its released re-ask was used
            up with no response recorded in the slot last asked (:meth:`reask_spent_unanswered`)."""
            return self.reask_spent_unanswered(key, max(self._seen.get(("jev", key), 1) - 1, 0), kind="jev")

        wrapped.reask = reask  # type: ignore[attr-defined]
        wrapped.request_key = request_key  # type: ignore[attr-defined]
        wrapped.spent_unanswered = spent_unanswered  # type: ignore[attr-defined]
        return wrapped

    def _ask(self, ask_fn: AskFn, state: dict[str, Any], questions: dict[str, dict[str, Any]], *,
             final_unidentified: bool) -> JevResult:
        """One journaled jev call. PI ruling 120 c: while a PI release authorises a live re-ask of the request's
        key (:meth:`reask_authorised`; the jev request of a residual ``source_type`` deciding part held with a
        request id but no answer), the recorded response is NOT replayed: the :data:`REASK_SPENT` entry is
        written first (it uses the authorisation up and displaces that response, PI ruling 114 b), then the
        call is made live and its response journaled in the same slot, replayed afterwards. A key whose re-ask
        was used up with no response recorded since is refused (:class:`ReaskSpentUnanswered`, no call). PI ruling
        126 a (kept): this holds per slot, so once the key's re-ask is spent, asking the same request again in the
        same process (its next slot, with no response recorded there) is refused too, even when the re-ask
        itself was answered in its own slot."""
        request = {"state": state, "questions": questions}
        slot = self._slot("jev", request)
        authorised = self.reask_authorised(slot[1])
        if slot in self._recorded and not authorised:
            self.replayed += 1
            return _jev_from_json(self._recorded[slot])
        if authorised:  # PI rulings 120 c / 114 b: used up BEFORE the call; never replayed instead
            self._spend_reask(slot[1], slot[2])
        elif self.reask_spent_unanswered(slot[1], slot[2], kind="jev"):  # never an unauthorised re-ask
            raise ReaskSpentUnanswered(slot[1], None, kind="jev")
        elif final_unidentified:
            # ruling 75 a: this exact re-ask was billed and came back without a request id; that is
            # its final failure, so the recorded response is read again instead of a new call
            seen = (JEV_UNIDENTIFIED, slot[1])
            n = self._seen.get(seen, 0)
            recorded = self._unidentified.get((slot[1], n))
            if recorded is not None:
                self._seen[seen] = n + 1
                self.replayed += 1
                return _jev_from_json(recorded)
        start = time.monotonic()
        # An exception is not recorded: asked again on resume. A call sent that died without a
        # response (e.g. a read timeout) is therefore unjournaled and unpriced (PI ruling 131.1 b).
        result = ask_fn(state, questions)
        self.live += 1
        if not has_request_id(result.request_id):
            # billed but unidentified: a failed request (asked again, unless a re-ask), still accounted
            self._append(self._slot(JEV_UNIDENTIFIED, request), _jev_to_json(result), _elapsed_ms(start))
        elif self.retry_incomplete and set(questions) - set(result.answers):
            # an asked answer is missing: that question is held and asked again next run (Z1 b)
            self._append(self._slot("jev_incomplete", request), _jev_to_json(result), _elapsed_ms(start))
        else:
            self._append(slot, _jev_to_json(result), _elapsed_ms(start))
        return result

    def _extract(self, extract_fn: Any, prompt: Mapping[str, Any]) -> Any:
        def wrapped(job: Any) -> ExtractorResult:
            request = {"custom_id": job.custom_id, "params": job.params}
            slot = self._slot("extract", request, prompt)
            if slot in self._recorded:
                self.replayed += 1
                return ExtractorResult(**self._recorded[slot])
            if self.rejections(slot[1]) >= EXTRACT_REJECT_CAP:  # ruling 34 b / 41 a: never called again
                raise ExtractRejectCapReached(slot[1], self.rejections(slot[1]), job.custom_id)
            start = time.monotonic()
            stored = self._stored_batch_result(slot[1], job, extract_fn)
            if stored is not None:  # PI ruling 134: a Message Batch answered it; journaled as a live response
                result = stored
                self.batched += 1
            else:
                call = extract_fn
                if self.reask_authorised(slot[1]):  # PI ruling 114 b: the re-ask is used up BEFORE the call
                    self._spend_reask(slot[1])
                    call = getattr(extract_fn, "live_call", extract_fn)  # PI ruling 134: a re-ask is always live
                elif self.reask_spent_unanswered(slot[1], slot[2], kind="extract"):  # review H-1: never unauthorised
                    raise ReaskSpentUnanswered(slot[1], job.custom_id)
                # An exception is not recorded: asked again on resume. A call sent that died without a
                # response (e.g. a read timeout) is therefore unjournaled and unpriced (PI ruling 131.1 b).
                # A batch-mode extract_fn raises ``BatchDeferred`` instead of a call: nothing is recorded.
                result = call(job)
                self.live += 1
            response = asdict(result)
            if response.get("batch_id") is None:  # a live call: its entry is written as before PI ruling 134
                response.pop("batch_id", None)
            if result.success:
                self._append(slot, response, _elapsed_ms(start))
            else:
                self._append(self._slot("extract_failed", request, prompt), response, _elapsed_ms(start))
            return result

        def peek(job: Any) -> tuple[str, bool]:
            """``(request key, recorded)`` for the next call of ``job``: whether this journal holds a
            response it would replay, without using the slot (PI ruling 98 b reads it before a rebuild).
            PI ruling 104 b: ``recorded`` is also True while a PI release authorises one live re-ask of the
            key (:meth:`reask_authorised`); the :data:`REASK_SPENT` entry written just before that call uses
            the authorisation up (PI ruling 114 b). Review H-1: a key whose re-ask was used up with no response
            to replay since (:meth:`reask_spent_unanswered`) is False here, and the wrapped call refuses it
            (:class:`ReaskSpentUnanswered`), so the two agree: neither lets it go live."""
            key = self._key({"custom_id": job.custom_id, "params": job.params}, prompt)
            recorded = ("extract", key, self._seen.get(("extract", key), 0)) in self._recorded
            # PI ruling 134: a request the batch journal knows was never sent live (queued or in flight) is
            # not a lost live call: it is deferred again. Nor is one a stored batch result answers that this
            # journal has not journaled yet; once journaled, that result no longer counts (one use only)
            owns = getattr(extract_fn, "batch_owns", None)
            return key, (recorded or self.reask_authorised(key) or bool(owns is not None and owns(job))
                         or self._stored_batch_result(key, job, extract_fn) is not None)

        def reask_live(job: Any) -> bool:
            """PI ruling 113 b: whether the next call of ``job`` is the live re-ask a PI release authorised
            (no recorded response to replay, and :meth:`reask_authorised`); the per-page adapter archives the
            page's activity-level state before such a pass-1 / activity-only call. Uses no slot."""
            key = self._key({"custom_id": job.custom_id, "params": job.params}, prompt)
            recorded = ("extract", key, self._seen.get(("extract", key), 0)) in self._recorded
            return not recorded and self.reask_authorised(key)

        def spent_unanswered(job: Any) -> bool:
            """Review L-2: whether the next call of ``job`` is one the journal refuses because its PI-released
            re-ask was used up with no response recorded since (:meth:`reask_spent_unanswered`); the per-page
            adapter's own 98 b / 105 b guards pass it on, so their holds carry the spent note. Uses no slot."""
            key = self._key({"custom_id": job.custom_id, "params": job.params}, prompt)
            return self.reask_spent_unanswered(key, kind="extract")

        wrapped.peek = peek  # type: ignore[attr-defined]
        wrapped.reask_live = reask_live  # type: ignore[attr-defined]
        wrapped.spent_unanswered = spent_unanswered  # type: ignore[attr-defined]
        return wrapped

    def _entail(self, entail_fn: Any, prompt: Mapping[str, Any]) -> Any:
        # An X35 client that reports its response's own usage (``entail_with_usage``, e.g.
        # ``v27_entry.LazyX35``; PI ruling 139 a) has it journaled per request, on the ``x35``
        # entry (a non-answer's too, Q169 b below) or, for another billed exception, on the
        # ``x35_failed`` one (the exception's ``usage``), so :meth:`x35_usages` can price each call. A plain
        # ``entail_fn`` (a fake) journals no usage, exactly as before.
        # An exception that carries no ``usage`` attribute at all (a transport error, a
        # timeout, a 429/529 raised before any response, a refusing stub) is still counted
        # as ``x35_failed`` but marked ``usage_absent: "no_response"``: like an extractor call
        # that died without a response (PI ruling 131.1 b), it is not priced
        # (:meth:`x35_usages` skips it), so it neither guesses a price nor blocks the total.
        # An exception whose ``usage`` attribute is present but not a dict (a response that
        # reported no usage) is not marked: it stays unpriced (``None``), never guessed.
        # PI ruling Q169 b: an X35 non-answer (``X35ResponseError``: a refusal, a ``max_tokens``
        # stop, unparseable output) is an answer with no probability. It is journaled as an
        # ``x35`` entry (replayed on resume, so it is never asked or billed again) with value
        # ``support_check.X35_NON_ANSWER``, probability ``None``, the error under ``non_answer``
        # and the billed response's ``usage`` (priced, Q158 a), and returned, not raised: only
        # that check fails (``entailment_probability_unavailable``) and the institution goes on.
        with_usage = getattr(entail_fn, "entail_with_usage", None)

        def wrapped(question: str, text: str) -> Entailment:
            request = {"question": question, "text": text}
            slot = self._slot("x35", request, prompt)
            if slot in self._recorded:
                self.replayed += 1
                recorded = self._recorded[slot]
                return Entailment(recorded["value"], recorded["probability"])
            if self.x35_failures(slot[1]) >= EXTRACT_REJECT_CAP:  # review O2 M4: never called again
                raise X35FailCapReached(slot[1], self.x35_failures(slot[1]))
            start = time.monotonic()
            usage: dict[str, Any] | None = None
            try:
                if callable(with_usage):
                    answer, usage = with_usage(question, text)
                else:
                    answer = entail_fn(question, text)
            except X35ResponseError as exc:  # PI ruling Q169 b: a non-answer, journaled and replayed
                self.live += 1
                non_answer = Entailment(X35_NON_ANSWER, None)
                response = {**asdict(non_answer), "non_answer": f"{type(exc).__name__}: {exc}"}
                if isinstance(exc.usage, dict):
                    response["usage"] = exc.usage
                self._append(slot, response, _elapsed_ms(start))
                return non_answer
            except Exception as exc:
                failed: dict[str, Any] = {"error": f"{type(exc).__name__}: {exc}"}
                exc_usage = getattr(exc, "usage", None)
                if isinstance(exc_usage, dict):
                    failed["usage"] = exc_usage
                elif not hasattr(exc, "usage"):  # no response came back (PI ruling 131.1 b)
                    failed[X35_USAGE_ABSENT] = X35_NO_RESPONSE
                self._append(self._slot("x35_failed", request, prompt), failed, _elapsed_ms(start))
                raise
            self.live += 1
            response = asdict(answer)
            if usage is not None:
                response["usage"] = usage
            self._append(slot, response, _elapsed_ms(start))
            return answer
        return wrapped

    def _stored_batch_result(self, key: str, job: Any, extract_fn: Any) -> ExtractorResult | None:
        """PI ruling 134: the first stored Message Batch result for ``job`` this journal has not journaled yet
        (the batch-mode ``extract_fn``'s ``stored_batch_results``); None for a live-only ``extract_fn``. Not
        ``batch_results``: the live ``LazyExtractor`` has that name for the Batches API call itself."""
        results = getattr(extract_fn, "stored_batch_results", None)
        if results is None:
            return None
        for result in results(job):
            if result.batch_id is not None and (key, result.batch_id) not in self._batch_used:
                return result
        return None

    def reject_extract(self, request: Mapping[str, Any], prompt: Mapping[str, Any], error: str) -> bool:
        """Cancel the last recorded extractor response to ``request`` (C3 a, QA4 M3).

        The per-page stage calls this when that response (``success`` true) did not
        parse: an ``extract_rejected`` entry (accounting only, carrying the response
        and ``error``) cancels the ``extract`` entry, here and on every later load, so
        it is never replayed as final and the next run asks the request again. A
        request with no recorded response in this process (e.g. a failed one, already
        ``extract_failed``) is left alone: returns False.
        """
        key = self._key(dict(request), dict(prompt))
        n = self._seen.get(("extract", key), 0) - 1
        response = self._recorded.get(("extract", key, n))
        if n < 0 or response is None:
            return False
        self._append((EXTRACT_REJECTED, key, n), {**response, "rejected_error": error}, 0)
        return True

    def seams(self, prompt: Mapping[str, Any]) -> tuple[Any, Any]:
        """Wrappers that journal an extractor call and an X35 call under ``prompt`` (an extra key
        part, e.g. the models they run on): ``(wrap_extract, wrap_entail)``. Used by the per-page
        providers (:meth:`~g3o.run.presweep.perpage_providers_v27.ExtractorPerPageProviders.with_seams`)."""
        prompt = dict(prompt)
        return (lambda f: self._extract(f, prompt)), (lambda f: self._entail(f, prompt))

    def quote(self, quote_fn: QuoteFn | None) -> QuoteFn | None:
        if quote_fn is None:
            return None
        prompt = {"quote_prompt_version": getattr(quote_fn, "prompt_version", None),
                  "x35_model": getattr(quote_fn, "x35_model", None)}
        inner = quote_fn
        if hasattr(quote_fn, "with_seams"):  # the extractor and X35 calls are journaled on their own
            inner = quote_fn.with_seams(lambda f: self._extract(f, prompt), lambda f: self._entail(f, prompt))

        def wrapped(request: Stage6QuoteRequest) -> Stage6Quote:
            slot = self._slot("quote", asdict(request), prompt)
            if slot in self._recorded:
                self.replayed += 1
                return _quote_from_json(self._recorded[slot])
            start = time.monotonic()
            answer = inner(request)
            self.live += 1
            self._append(slot, _quote_to_json(answer), _elapsed_ms(start))
            return answer
        return wrapped

    def extractor_usages(self) -> list[dict[str, Any] | None]:
        """Each journaled extractor response's own ``usage`` (``None`` where it has none), for the
        calls ``usage()["extractor_calls"]`` counts: successful, failed and rejected results.
        Priced per request by :func:`g3o.common.cost_monitor.price_extractor_requests` (rulings 58 a,
        130 a: standard rates for these live calls).

        A failed result (``extract_failed``) that reports no usage gives
        ``{EXTRACTOR_FAILED_RESULT_KEY: <its error type>}`` instead, read from the journaled
        result's ``error["type"]`` (on disk, so the same after a resume): the pricing decides
        what that type costs (PI ruling 67 a). Without a string type it stays ``None``.

        Only journaled calls appear. A call sent that died without a response (e.g. a read
        timeout) is not journaled, so it is neither counted nor priced (PI ruling 131.1 b:
        accepted). A torn last journal line is skipped on a read-only load and dropped on repair,
        so at most one billed call can be missing here (PI ruling 131.2 a: accepted).
        """
        from g3o.common.cost_monitor import EXTRACTOR_BATCH_KEY, EXTRACTOR_FAILED_RESULT_KEY

        def marked(response: Mapping[str, Any], usage: Any) -> Any:
            # PI rulings 134 / 130 a: a result a Message Batch returned is priced at batch rates
            if isinstance(usage, dict) and isinstance(response.get("batch_id"), str):
                return {**usage, EXTRACTOR_BATCH_KEY: True}
            return usage

        out: list[dict[str, Any] | None] = []
        for (kind, _, _), response in self._recorded.items():
            if kind == "extract":
                out.append(marked(response, response.get("usage")))
        for entry in self._accounting:
            if entry["kind"] in ("extract_failed", EXTRACT_REJECTED):
                response = entry["response"]
                usage = response.get("usage")
                error = response.get("error")
                failed_type = error.get("type") if isinstance(error, dict) else None
                if (entry["kind"] == "extract_failed" and usage is None
                        and isinstance(failed_type, str)):
                    out.append({EXTRACTOR_FAILED_RESULT_KEY: failed_type})
                else:
                    out.append(marked(response, usage))
        return out

    def x35_usages(self) -> list[dict[str, Any] | None]:
        """Each journaled X35 response's own ``usage`` (``None`` where it has none), for the calls
        ``usage()["x35_calls"] + usage()["x35_failed"]`` count, in that order: answered calls, then
        failed ones. Priced per request by :func:`g3o.common.cost_monitor.price_x35_requests`
        (PI ruling Q158 a; ``cost_monitor.X35_PRICING_RULED``). An X35 non-answer (PI ruling
        Q169 b) is an answered ``x35`` entry carrying its billed usage, so it is priced once.

        ``None`` is an answer from a client that reports no usage (a fake, or an entry written
        before usage was journaled), a failed response that reported no usage, or a failed call
        journaled before the ``usage_absent`` marker existed; it is never guessed.

        PI ruling 131.1 b, as for the extractor: a call that died without a response is not
        priced. An ``x35_failed`` entry marked ``usage_absent: "no_response"`` (an exception
        raised before any response came back, e.g. a transport error, a timeout or a 429/529)
        is skipped here, so it neither gets a price nor makes the X35 part unpriced; it is
        still counted in ``usage()["x35_failed"]``, so this list can be shorter than that
        count. Nothing is priced at $0. A torn last line (131.2 a) applies too.
        """
        out: list[dict[str, Any] | None] = [
            response.get("usage") for (kind, _, _), response in self._recorded.items() if kind == "x35"
        ]
        out.extend(entry["response"].get("usage") for entry in self._accounting
                   if entry["kind"] == "x35_failed" and not _x35_no_response(entry["response"]))
        return out

    def usage(self) -> dict[str, int]:
        """Totals of every journaled call (this and earlier, interrupted runs).

        ``input_tokens`` / ``output_tokens`` are jev tokens (complete, unidentified
        and incomplete responses); ``extractor_*`` are the quote step's extractor
        calls (successful, failed and rejected results); ``x35_calls`` / ``x35_failed``
        count X35 calls (their tokens are per request, :meth:`x35_usages`); ``request_ms`` is
        the summed call time. A quote step without seams is counted only as
        ``quote_responses``.

        A call sent that died without a response (e.g. a read timeout) is not journaled,
        so it is not in these totals (PI ruling 131.1 b: accepted); a torn last journal
        line, skipped on a read-only load and dropped on repair, leaves out at most one
        billed call (PI ruling 131.2 a: accepted).
        """
        def recorded(kind: str) -> list[dict[str, Any]]:
            return [r for (k, _, _), r in self._recorded.items() if k == kind]

        def accounted(kind: str) -> list[dict[str, Any]]:
            return [e["response"] for e in self._accounting if e["kind"] == kind]

        # PI ruling 120 c: a jev response a released re-ask displaced was billed too: still counted
        jev = [*recorded("jev"), *accounted(JEV_SUPERSEDED)]
        unidentified, incomplete = accounted("jev_unidentified"), accounted("jev_incomplete")
        extract = [*recorded("extract"), *accounted("extract_failed"), *accounted(EXTRACT_REJECTED)]
        return {"jev_responses": len(jev), "jev_unidentified": len(unidentified), "jev_incomplete": len(incomplete),
                "quote_responses": len(recorded("quote")),
                "input_tokens": sum(r["input_tokens"] for r in (*jev, *unidentified, *incomplete)),
                "output_tokens": sum(r["output_tokens"] for r in (*jev, *unidentified, *incomplete)),
                "extractor_calls": len(extract),
                "extractor_input_tokens": sum(_tokens(r.get("usage"), "input_tokens") for r in extract),
                "extractor_output_tokens": sum(_tokens(r.get("usage"), "output_tokens") for r in extract),
                "x35_calls": len(recorded("x35")), "x35_failed": len(accounted("x35_failed")),
                "request_ms": sum(self._elapsed)}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservationInput:
    """One observation's per-page storage fragment (T-023 final values with T-028 nodes).

    ``row`` has ``values`` (every activities-table item except ``core.n_sources``
    and ``core.confidence``, which Stage 6 computes, and, PI ruling 94 a, the
    Stage-6-only A8 items ``stage_as_of``, ``date_upper_bound``, ``vendor_claim_only``
    and ``cx_display_rollup``, produced only in :func:`build_envelope` by
    :func:`g3o.validate.merged_activity_v27.merged_values_a8`), ``item_support`` and
    ``coder_records``. ``source_id`` is the observation's source claim.
    """

    observation_id: str
    source_id: str
    row: Mapping[str, Any]


@dataclass(frozen=True)
class Stage6Institution:
    run_id: str
    institution_uid: str
    institution: Mapping[str, Any]  # the six master identity columns (response_v27)
    country: str | None
    pages: Sequence[ReviewedPage]
    observations: Sequence[ActivityObservation]
    records: Sequence[ObservationRecord]
    within_page: Sequence[RelationDecision]
    quotes: Sequence[InputQuote]
    observation_inputs: Mapping[str, ObservationInput]
    sources: Mapping[str, Mapping[str, Any]]  # source rows (T-015 values, nodes, page artifact); no activity_id
    artifacts: Mapping[str, PageArtifact]  # source_id -> its stored page artifact
    provenance: Sequence[Mapping[str, Any]]  # companions of the per-page quote supports
    independence_groups: Mapping[str, str] | None = None
    merged_values: Mapping[tuple[str, ...], Mapping[str, Any]] | None = None

    @property
    def institution_id(self) -> str:
        return str(self.institution["institution_id"])


@dataclass
class Stage6Metrics:
    written: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # envelope/artifact errors, recorded per institution
    live_requests: int = 0
    replayed_requests: int = 0
    usage: dict[str, dict[str, int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Envelope assembly
# ---------------------------------------------------------------------------


@dataclass
class _Nodes:
    supports: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # activity id -> nodes
    coders: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def add(self, aid: str, nodes: Any, record: CoderRecord, instrument: dict[str, Any]) -> None:
        record = replace(record, support_id=nodes.original["support_id"],
                         observation_id=nodes.original["observation_id"])
        projection, final_projection, _ = coder_nodes(record, nodes, instrument)
        self.supports.setdefault(aid, []).extend(n for n in (nodes.original, nodes.final) if n is not None)
        self.coders.setdefault(aid, []).extend(c for c in (projection, final_projection) if c is not None)
        self.provenance.append(nodes.provenance)


def pooled_stage_answers(inst: Stage6Institution, pooled: PooledActivity) -> list[str]:
    """A6.1 a: the pooled observations' adoption-stage values and the pool parts' answers, before combining."""
    return [*(str(inst.observation_inputs[k].row["values"][uf.STAGE_ITEM]) for k in pooled.observation_ids),
            *uf.classifier_answers(pooled.records)]


def _rule_result(item: str, part: str | None, value: str, rule: str) -> SupportResult:
    return check_code(CodeEvidence(item, value, "stage6-rule", part=part, rule_name=rule),
                      PageSources("stage6-rule", {"stage6-rule": ""}))


def _mechanical(item: str, part: str | None, qid: str | None, value: str, rule: str, config: Stage6Config,
                qsv: str) -> CoderRecord:
    return CoderRecord(item_id=item, item_part=part, question_id=qid, support_id=None, observation_id=None,
                       chunk_id=None, coder_type="mechanical", coder_version=config.coder_version,
                       configured_model=None, actual_response_model=None, request_id=None,
                       question_set_version=qsv, setup_pointer=config.setup_pointer, answer_type="rule",
                       chosen_value=value, confidence=None, probability_distribution=None, rule_reference=rule)


def _pool_nodes(inst: Stage6Institution, aid: str, pooled: PooledActivity, quotes: Mapping[str, InputQuote],
                config: Stage6Config, instrument: dict[str, Any], out: _Nodes) -> None:
    def shown(ids: Iterable[str]) -> list[InputSupport]:
        return [InputSupport(i, quotes[i].source_id, quotes[i].sources, inst.artifacts[quotes[i].source_id])
                for i in ids]

    every = sorted({i for ids in pooled.part_inputs.values() for i in ids})
    stage_answers = pooled_stage_answers(inst, pooled)
    answered = [r for r in pooled.records if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED]
    if len(answered) != len(pooled.support):
        raise ConsolidationError("pooled answers and support checks do not pair one to one")
    if len(pooled.support_inputs) != len(pooled.support):
        raise ConsolidationError("pooled support checks lack the quote step's copied inputs")
    for rec, sr, copied in zip(answered, pooled.support, pooled.support_inputs, strict=True):
        nodes = combined_support_nodes(sr, run_id=inst.run_id, institution_uid=inst.institution_uid,
                                       chunk_id=rec.chunk_id, shown=shown(pooled.part_inputs[rec.chunk_id]),
                                       observation_id=None,
                                       uncertainty_flags=uf.code_flags(sr, stage_answers=stage_answers),
                                       instrument=instrument, input_support_id=copied)
        out.add(aid, nodes, rec, instrument)
    mechanical = {r.question_id: r for r in pooled.records if r.coder_type == "mechanical"}
    for qid, outcome in pooled.outcomes.items():
        if outcome.state == "gated_out":
            rec = mechanical[qid]
        elif outcome.rule_reference == PERMANENT_PILOT_RULE:
            rec = _mechanical(outcome.item_id, outcome.part, qid, str(outcome.value), PERMANENT_PILOT_RULE, config,
                              pooled.question_set_version)
        else:
            continue
        sr = _rule_result(outcome.item_id, outcome.part, str(outcome.value), rec.rule_reference)
        nodes = combined_support_nodes(sr, run_id=inst.run_id, institution_uid=inst.institution_uid, chunk_id=None,
                                       shown=shown(every), observation_id=None,
                                       uncertainty_flags=uf.code_flags(sr, stage_answers=stage_answers),
                                       instrument=instrument)
        out.add(aid, nodes, rec, instrument)


def _relation_nodes(inst: Stage6Institution, result: Stage6Result, final_of: Mapping[str, str],
                    quotes: Mapping[str, InputQuote], instrument: dict[str, Any], out: _Nodes
                    ) -> tuple[dict[tuple[str, str], list[str]], set[tuple[str, str]]]:
    """Store the cross-page relation nodes; return their support ids per (lhs, rhs) and the
    (lhs, rhs) pairs whose node carries ``identity_unresolved`` (for the R1 a row flag)."""
    by_obs = {r.observation_id: r for r in inst.records}
    ids: dict[tuple[str, str], list[str]] = {}
    unresolved: set[tuple[str, str]] = set()
    for outcome in result.relation_outcomes:
        if outcome.decision is None or not (outcome.lhs in final_of and outcome.rhs in final_of):
            continue
        rec, sr = outcome.records[0], outcome.support[0]
        copied = outcome.support_inputs[0] if outcome.support_inputs else None
        candidates = [*by_obs[outcome.lhs].quotes, *by_obs[outcome.rhs].quotes]
        shown = [InputSupport(q.support_id, q.source_id, q.sources, inst.artifacts[q.source_id]) for q in candidates]
        # A quote copied from outside the request part (no copied input) is no supporting text
        # (R-044; RC-D-029 X3 a iii): the node is placed as an unquoted relation's, and the
        # rejected copy is kept in its provenance companion only.
        quoted = sr.supporting_text is not None and copied is not None

        node_args = dict(run_id=inst.run_id, institution_uid=inst.institution_uid, chunk_id=rec.chunk_id,
                         shown=shown, uncertainty_flags=uf.code_flags(sr), instrument=instrument,
                         input_support_id=copied)
        nodes = combined_support_nodes(sr, observation_id=None if quoted else outcome.lhs, **node_args)
        if quoted and not nodes.original["supporting_text"]:
            # The quote step named an input, but the quote's segment is not in it: the adapter
            # rejected the copy (no supporting text). Same placement as above (X3 a iii).
            nodes = combined_support_nodes(sr, observation_id=outcome.lhs, **node_args)
        # The node lives with the record whose quote was copied (the quote step's own answer).
        inputs = nodes.original["input_support_ids"]
        home = quotes[copied].observation_id if copied is not None and inputs == [copied] else outcome.lhs
        out.add(final_of[home], nodes, rec, instrument)
        ids[(outcome.lhs, outcome.rhs)] = [n["support_id"] for n in (nodes.original, nodes.final) if n is not None]
        if uf.IDENTITY_UNRESOLVED in node_args["uncertainty_flags"]:
            unresolved.add((outcome.lhs, outcome.rhs))
    return ids, unresolved


def _real(item: str, value: Any) -> bool:
    """A real value of ``item`` (R3): not one of that item's missing tokens and not a blank string.

    Numbers are real (``core.deployment_scale_number`` is a JSON number or a missing token).
    """
    tokens = FIELDS[item]["missing_tokens"]
    if isinstance(value, str):
        return value not in (tokens if isinstance(tokens, list) else ()) and bool(value.strip())
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _credibility_rank(inst: Stage6Institution, oid: str) -> int:
    """T-015 source confidence of the observation's source claim; ``unknown`` counts as low (C8 b)."""
    row = inst.sources[inst.observation_inputs[oid].source_id]
    grades = default_vocab().credibility_values  # signed order: high, medium, low
    value = aggregation_value(row["values"]["core.confidence"])
    if value not in grades:
        raise ConsolidationError(f"source confidence {value!r} of {oid} has no credibility rank")
    return grades.index(value)


def merge_values(inst: Stage6Institution, order: Sequence[str]) -> dict[str, Any]:
    """RC-D-030 X1 a R2 / R3 values of a merged activity from its pooled observations in pool order."""
    rows = {k: inst.observation_inputs[k].row["values"] for k in order}
    out: dict[str, Any] = {}
    ranked = sorted(order, key=lambda k: _credibility_rank(inst, k))  # stable: ties keep pool order
    for item in MERGE_UNION:  # R2: union, trim + case-fold duplicates dropped, first spelling kept
        entries: list[str] = []
        seen: set[str] = set()
        for k in order:
            value = rows[k][item]
            for entry in value if isinstance(value, list) else ():
                key = entry.strip().casefold() if isinstance(entry, str) else None
                if key and key not in seen:
                    seen.add(key)
                    entries.append(entry)
        if entries:
            out[item] = entries
            continue
        # No entry anywhere: the observations' (missing) values may still differ, e.g. [] beside
        # not_documented; RC-D-032 B3 a: the highest-credibility observation's value, R3 order.
        out[item] = rows[ranked[0]][item]
    for item in MERGE_CREDIBLE:  # R3: most credible source, a real value over a missing token
        pick = next((k for k in ranked if _real(item, rows[k][item])), ranked[0])
        out[item] = rows[pick][item]
    return out


#: PI rulings 96 a / 102 a (2026-11-14): the named exception to A7 13 a. A source row of a page that was not
#: reviewed is not grouped (:func:`independence_groups_of`), so its ``not_asked`` syndication group never
#: holds the institution.
A7_UNREVIEWED_EXCEPTION = "follow_not_reviewed (PI rulings 96 a / 102 a): unreviewed source rows are not grouped"


def independence_groups_of(inst: Stage6Institution) -> Mapping[str, str]:
    """Source independence groups for ``core.confidence`` (PI A7.1 b, A7.2 a, 2026-11-11).

    An injected ``Stage6Institution.independence_groups`` is used as given (the
    seam's contract is unchanged). Otherwise the groups are produced from the
    institution's source rows by :func:`g3o.common.independence.independence_groups_for_sources`
    (same syndication group or same normalised URL, transitive closure), which
    refuses with ``MissingUpstreamError`` when a source's syndication group or
    URL is not available (A7.2 a: no URL-only fallback).

    PI rulings A7 12 a, 13 a, 14 (2026-11-11): the groups span all of the
    institution's source rows, including sources no published activity cites;
    one source without a syndication group holds the whole institution; an
    injected mapping wins over the producer.

    Named exception to 13 a (:data:`A7_UNREVIEWED_EXCEPTION`, PI rulings 96 a / 102 a): the source row of a
    page that was not reviewed (an unread follow attempt, :func:`g3o.common.storage.unreviewed_source`) is
    left out of the grouping: its syndication group is ``not_asked`` by rule and no activity cites it.
    """
    if inst.independence_groups is not None:
        return inst.independence_groups
    grouped = {sid: row for sid, row in inst.sources.items() if not unreviewed_source(row)}
    try:
        return independence_groups_for_sources(grouped, institution_id=inst.institution_id)
    except SourceFieldsMissingUpstreamError as exc:
        raise MissingUpstreamError(f"{INDEPENDENCE_PRODUCER}; {exc.producer}", exc.missing) from exc


#: PI ruling 140 (gate 3, 2026-11-16): Stage 6 is the producer of the source row's ``core.confidence``.
CONFIDENCE_ITEM = "core.confidence"
CREDIBILITY_ITEM = "core.source_credibility"


def _original_records(nodes: Iterable[Mapping[str, Any]]) -> list[SupportResult]:
    """The ORIGINAL support records of stored per-page nodes, as ``source_confidence_rule`` reads them.

    A per-page original node names no input support (a downgrade's final node names its original); the
    within-page relation items (:data:`~g3o.classify.jev_activity_code.PAIR_ITEMS`) concern two activities
    and are not one claim's records (P12: records of other activities are not associated). The rule reads
    the item, the original value, the support status, its second reason and the rule name only.
    """
    out: list[SupportResult] = []
    for n in nodes:
        if n["input_support_ids"] or n["item_id"] in PAIR_ITEMS:
            continue
        value = n["value_json"]
        value = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        second, rule = n["support_status_second_reason"], n["support_rule_name"]
        out.append(SupportResult(
            item_id=n["item_id"], part=n["item_part"], activity_id=None, chunk_id=n["chunk_id"] or "",
            original_value=value, value=value, support_status=n["support_status"],
            support_status_second_reason=None if second == EMPTY_COMPANION else second,
            support_rule_name=None if rule == EMPTY_COMPANION else rule,
            supporting_text=n["supporting_text"] or None, quote_chunk_id=None, match=None,
            chosen_answer_probability=None, entailment=None))
    return out


def source_confidence_of(inst: Stage6Institution, sid: str) -> str:
    """PI ruling 140 (gate 3): the source row's ``core.confidence``, produced here.

    The claim's records are associated by :func:`g3o.validate.stage6_v27.source_claim_records` (RC-D-025
    P12): the source row's own nodes (page level) plus the nodes of the observations on this page that
    belong to the source row's activity; scored by ``source_confidence_rule`` (``items/core.confidence/
    rules/1``) on the row's ``core.source_credibility``. An unfinished score is refused
    (``UnfinishedConfidenceError``) and a claim with no records raises ``ValueError`` (P11).
    """
    row = inst.sources[sid]
    page_id = next((p.page_id for p in inst.pages if sid in p.source_ids), None)
    if page_id is None:
        raise ConsolidationError(f"source claim {sid} belongs to no reviewed page")
    oids = list(row["observation_ids"])
    observation_pages = {r.observation_id: r.page_id for r in inst.records}
    observation_support = {o: _original_records(inst.observation_inputs[o].row["item_support"]) for o in oids}
    records = source_claim_records(page_id, oids, _original_records(row["item_support"]), observation_support,
                                   observation_pages)
    conf = source_claim_confidence(sid, row["values"][CREDIBILITY_ITEM], records)
    return str(confidence_field(conf).value)


def with_source_confidence(inst: Stage6Institution) -> Stage6Institution:
    """``inst`` with each reviewed source row's ``core.confidence`` filled by :func:`source_confidence_of`.

    PI ruling Q162 b (2026-11-16): Stage 6 is the only producer, so a reviewed row that arrives here
    already carrying a value is a wiring error (ruling 32 b, :class:`UpstreamRowMalformed`: the stage
    stops); the per-page assembler refuses such a value too (``source_row_v27.STAGE6_SOURCE_ITEMS``).
    The one exception: an unreviewed follow row (:func:`~g3o.common.storage.unreviewed_source`) carries
    ``not_asked`` by rule (PI rulings 96 a / 102 a) and keeps it; any other value there is refused."""
    sources: dict[str, Mapping[str, Any]] = {}
    for sid, row in inst.sources.items():
        if unreviewed_source(row):
            given = row["values"].get(CONFIDENCE_ITEM)
            if given != ma.NOT_ASKED:
                raise UpstreamRowMalformed(inst.institution_id, CONFIDENCE_ITEM, f"unreviewed source row {sid}",
                                           problem=f"is {given!r}, not the not_asked set by rule (PI 96 a / 102 a)")
            sources[sid] = row
            continue
        if CONFIDENCE_ITEM in row["values"]:
            raise UpstreamRowMalformed(inst.institution_id, CONFIDENCE_ITEM, f"reviewed source row {sid}",
                                       problem="is pre-filled; Stage 6 is its only producer (PI Q162 b, ruling 140)")
        sources[sid] = {**dict(row), "values": {**dict(row["values"]),
                                                CONFIDENCE_ITEM: source_confidence_of(inst, sid)}}
    return replace(inst, sources=sources)


#: The A8 items the per-page T-015 assembler produces (source_row_v27.unit_credit); A8 review L6.
PER_PAGE_A8_ITEMS = frozenset({ma.UNIT_CREDIT})


def _agree_with_fragment(fragment: Mapping[str, Any], a8: Mapping[str, Any], oid: str) -> None:
    """A8 review L6: a single observation's stored fragment value of an A8 item (e.g. the per-page
    ``unit_credit``, T-015) must equal the value Stage 6 produces from the same rule; a disagreement is
    a wiring error (ruling 32 b: :class:`~g3o.validate.merged_activity_v27.MalformedA8Value`, the
    stage stops), never silently overwritten. Only the A8 items the per-page stage itself produces are
    compared (``unit_credit``); the Stage-6-only items (stage_as_of, date_upper_bound,
    vendor_claim_only, cx_display_rollup) carry no per-page producer, so a fragment value there is not
    a rival rule's output."""
    for item, value in a8.items():
        if item in PER_PAGE_A8_ITEMS and item in fragment and fragment[item] != value:
            raise ma.MalformedA8Value(item, f"observation {oid}", f"stored fragment value {fragment[item]!r} "
                                                                  f"disagrees with the A8 value {value!r}")


def build_envelope(inst: Stage6Institution, result: Stage6Result, config: Stage6Config, instrument: dict[str, Any],
                   artifact_root: Path) -> tuple[Any, list[dict[str, Any]]]:
    """The storage envelope and provenance records of one ready Stage 6 result."""
    if not result.ready:
        raise ConsolidationError("Stage 6 result is not ready; nothing is published")
    inst = with_source_confidence(inst)  # PI ruling 140 / Q162 b: Stage 6 is the only producer of it
    quotes = {q.support_id: q for q in inst.quotes}
    # Published activities: groups with at least one supported observation on a confirmed page
    # (the pooled-eligibility rule of T-026); other observations keep their relations only.
    published = [g for g in result.groups if pool_eligible(g, inst.observations, inst.pages)]
    final_of = {oid: f"A{n + 1}" for n, g in enumerate(published) for oid in g}
    out = _Nodes()
    for group in published:
        if group in result.pooled:
            _pool_nodes(inst, final_of[group[0]], result.pooled[group], quotes, config, instrument, out)
    relation_ids, unresolved_pairs = _relation_nodes(inst, result, final_of, quotes, instrument, out)
    # R1 a: the final activities an unresolved cross-page relation is filed on (its lhs; the
    # filing loop below files each cross-page decision under final_of[decision.lhs]).
    unresolved_on = {final_of[d.lhs] for d in result.relations
                     if d.scope == "cross_page" and (d.lhs, d.rhs) in unresolved_pairs}

    sources: dict[str, dict[str, Any]] = {}
    for sid, row in inst.sources.items():
        finals = {final_of[o] for o in row["observation_ids"] if o in final_of}
        if len(finals) > 1:
            raise ConsolidationError(f"source claim {sid} spans several final activities")
        sources[sid] = {**dict(row), "activity_id": finals.pop() if finals else "_NA_"}
    # Independence groups (A7) are computed once, before any activity, over all of the
    # institution's source rows (PI ruling A7 12 a), so one source without a syndication
    # group holds the whole institution (13 a) even when no activity is published.
    # An injected mapping is used as given (14).
    groups = independence_groups_of(inst)
    activities: dict[str, dict[str, Any]] = {}
    for group in published:
        aid = final_of[group[0]]
        fragments = [inst.observation_inputs[k].row for k in group]
        if len(group) == 1:  # ruling 78 a: the A8 producers run for a single observation too
            a8 = ma.merged_values_a8(inst, list(group), **_A8_KW)
            _agree_with_fragment(fragments[0]["values"], a8, group[0])
            values = {**fragments[0]["values"], **a8}
        else:
            if inst.merged_values is None or group not in inst.merged_values:
                raise MissingUpstreamError(MERGED_VALUES_PRODUCER, [aid])
            given = dict(inst.merged_values[group])
            if set(given) != MERGE_INPUT_ITEMS:
                extra, absent = sorted(set(given) - MERGE_INPUT_ITEMS), sorted(MERGE_INPUT_ITEMS - set(given))
                if extra:
                    raise ValueError(f"merged-value input names items merged by rule or pooled: {extra}")
                raise MissingUpstreamError(MERGED_VALUES_PRODUCER, absent)
            pooled = result.pooled[group]
            pooled_values = outcome_values(pooled.outcomes)
            # Pooled answers to items the activities table does not hold (the evaluation items,
            # stored per source claim in D-007) stay in the row's support/coder provenance only.
            order = observation_pool_order(inst.quotes, pooled.observation_ids)
            values = {**given, **merge_values(inst, order), **ma.merged_values_a8(inst, order, **_A8_KW),
                      **{k: v for k, v in pooled_values.items() if k in ACTIVITY_ITEMS}}
        support: dict[str, dict[str, Any]] = {}
        for node in [*(s for f in fragments for s in f["item_support"]), *out.supports.get(aid, [])]:
            support.setdefault(node["support_id"], node)
        coders = [*(c for f in fragments for c in f["coder_records"]), *out.coders.get(aid, [])]
        # Ruling 11 / A6.4 a: union of the row's node flags, except identity_unresolved, which is
        # set iff an unresolved cross-page relation is filed on this row (R1 a), even when that
        # relation's node is stored on the right-hand activity (W4 b).
        values[uf.ITEM] = uf.row_flags(support.values(), unresolved_relation=aid in unresolved_on)
        claims = sorted(s for s, row in sources.items() if row["activity_id"] == aid)
        values["core.n_sources"] = len(claims)
        values["core.confidence"] = activity_confidence_value(
            claims, {s: sources[s]["values"]["core.confidence"] for s in claims}, groups)
        activities[aid] = {"values": values, "item_support": list(support.values()), "coder_records": coders,
                           "observation_ids": list(group), "activity_relations": []}
    obs_sources: dict[str, list[str]] = {}
    for sid, row in sources.items():
        for o in row["observation_ids"]:
            obs_sources.setdefault(o, []).append(sid)
    for decision in result.relations:
        if not (decision.lhs in final_of and decision.rhs in final_of):
            continue
        support_ids = (list(decision.support_ids) if decision.scope == "within_page"
                       else relation_ids[(decision.lhs, decision.rhs)])
        rid = hashlib.sha256(f"{decision.scope}|{decision.lhs}|{decision.rhs}".encode()).hexdigest()[:16]
        activities[final_of[decision.lhs]]["activity_relations"].append({
            "relation_id": f"REL-{rid}", "lhs_observation_id": decision.lhs, "rhs_observation_id": decision.rhs,
            "relation": decision.relation,
            "source_refs": sorted({*obs_sources.get(decision.lhs, ()), *obs_sources.get(decision.rhs, ())}),
            "support_ids": support_ids, "lhs_final_activity_id": final_of[decision.lhs],
            "rhs_final_activity_id": final_of[decision.rhs], "relation_scope": decision.scope})
    summary = {"values": summary_values(inst.pages, inst.observations,
                                        published_activity_values=[a["values"] for a in activities.values()]),
               "item_support": [], "coder_records": []}
    envelope = assemble_storage(run_id=inst.run_id, institution_uid=inst.institution_uid,
                                institution_id=inst.institution_id, instrument=instrument,
                                evidence_channel=EVIDENCE_CHANNEL, activities=activities, sources=sources,
                                summary=summary, artifact_root=artifact_root)
    # Observations of unpublished groups (X3 a i) keep their relations only: their activity
    # fragments are not stored, so neither are those fragments' provenance companions.
    unstored = {n["support_id"] for k, o in inst.observation_inputs.items() if k not in final_of
                for n in o.row["item_support"]}
    provenance: dict[str, dict[str, Any]] = {}
    for record in [*(dict(r) for r in inst.provenance if r["support_id"] not in unstored), *out.provenance]:
        if provenance.setdefault(record["support_id"], record) != record:  # one node, one companion
            raise ConsolidationError(f"conflicting provenance for support {record['support_id']}")
    return envelope, list(provenance.values())


# ---------------------------------------------------------------------------
# Stage driver
# ---------------------------------------------------------------------------


def _done(inst_dir: Path) -> bool:
    """True when the three artifacts are committed (6_validate.json, written last, exists)
    and the provenance file is bound to the storage file; raises when they do not reload."""
    paths = [inst_dir / n for n in (VALIDATE_ARTIFACT, STORAGE_ARTIFACT, PROVENANCE_ARTIFACT)]
    if not all(p.exists() for p in paths):
        return False
    load_support_provenance(paths[2], paths[1])  # bound to this storage file, or it refuses
    return True


def hold_reasons(result: Stage6Result) -> tuple[list[str], list[dict[str, Any]]]:
    """Why a Stage 6 result is not ready: the hold reasons and the unfinished pooled questions."""
    reasons = {h.reason for h in result.held}
    if result.missing_pairs:
        reasons.add(MISSING_RELATION)
    if result.conflicting_groups:
        reasons.add(CONFLICTING_GROUPS)
    unfinished: list[dict[str, Any]] = []
    for group, pooled in result.pooled.items():
        for qid, o in pooled.outcomes.items():
            if o.state in ("combined", "gated_out"):
                continue
            unfinished.append({"observation_ids": list(group), "pool_id": pooled.pool_id, "question_id": qid,
                               "item_id": o.item_id, "part": o.part, "state": o.state, "note": o.note,
                               "error": o.error})
            if o.note not in {h.reason for h in pooled.held}:  # not already named by a hold
                reasons.add(POOLED_STOPPED if o.state == "stopped" else POOLED_PENDING)
    return sorted(reasons) or [NOT_READY], unfinished


def _hold(run_dir: Path, inst_dir: Path, institution_id: str, reasons: Sequence[str],
          doc: Mapping[str, Any], detail: Mapping[str, str] | None = None) -> None:
    """Write ``stage6_v27/held.json`` and one attrition record per hold reason."""
    path = inst_dir / WORK_DIR / HELD_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, canonical_json({"institution_id": institution_id, "reasons": list(reasons), **doc})
                 .encode("utf-8"))
    for reason in reasons:
        code = (reason if reason in (ENVELOPE_FAILED, ARTIFACTS_UNREADABLE, EXECUTOR_FAILED)
                else f"{HELD_REASON}:{reason}")
        attrition.record(run_dir, institution_id=institution_id, stage=STAGE, reason=code,
                         detail=(detail or {}).get(reason))


def run_stage6_v27(run_dir: Path, institutions: Iterable[Stage6Institution], *, ask_fn: AskFn,
                   quote_fn: QuoteFn | None, config: Stage6Config, instrument: dict[str, Any],
                   now: Callable[[], datetime] | None = None,
                   test_only_unbound_quote_fn: bool = False) -> Stage6Metrics:
    """Run v2.7 Stage 6 for each institution; write artifacts for the ready ones only.

    Provider exceptions that stop the stage (``JevAccountError``,
    ``Stage6QuoteNotApproved``, budget stops) propagate; what was recorded
    before them is replayed by the next run. An executor refusal for one
    institution (:data:`EXECUTOR_FAILED`: ``ConsolidationError``, ``ValueError``
    or ``RuntimeError``, as in the per-page stage), an error building or writing
    its artifacts, or existing artifacts that fail to reload, is recorded for
    that institution (``held.json``, attrition, ``metrics.failed``) and the stage
    continues with the next one. Any other executor exception (a programming
    error such as ``TypeError``, ``KeyError`` or ``AttributeError``) stops the
    stage. ``MissingUpstreamError`` (either class, :data:`MISSING_UPSTREAM`)
    raised inside the executor (from ``ask_fn``, ``quote_fn`` or the combiner
    included) is a wiring gap, not institution data: it stops the stage, as in
    the per-page stage (B1 a). Raised while building the
    envelope (the expected R1 refusals, absent independence groups or
    uncertainty flags) it stays a per-institution :data:`ENVELOPE_FAILED` hold.
    The envelope build and artifact writes hold only :data:`ENVELOPE_HOLDS`
    (B3); a stage stop or a programming error there propagates.

    Malformed upstream rows (ruling 32 b) stop the stage with
    :class:`UpstreamRowMalformed`, naming the institution and the missing field:
    an institution row missing a master identity column or holding a null in one
    (every row is checked before the first institution is run, so nothing is asked
    for any institution), and any ``KeyError`` while building the storage
    envelope or writing the artifacts (e.g. a source row without
    ``core.confidence``), and a stored value an A8 producer reads that is outside
    its signed form (:class:`~g3o.validate.merged_activity_v27.MalformedA8Value`;
    every row's A8 inputs are form-checked before the first call,
    :func:`require_a8_form`; an absent one, or one the signed rule does not
    determine, holds the institution in the envelope build). The holds the rulings require are unchanged: a source
    with no syndication group holds the institution (A7 13 a, a
    ``MissingUpstreamError`` from the independence groups), and an ``OSError``
    that survives the write retries holds it (28 a).

    ``quote_fn`` must come from :meth:`~g3o.run.presweep.instrument_binding.BoundRuntime.stage6_quote_fn`
    for this instrument, on its pinned X35 model (or be ``None``: every answer needing a quote is held);
    ``test_only_unbound_quote_fn`` lifts that check for offline fakes in tests only.
    """
    if config.setup_pointer != instrument["instrument_id"]:
        raise ValueError("Stage 6 configuration is bound to a different instrument")
    if quote_fn is not None and not test_only_unbound_quote_fn and not (
            isinstance(quote_fn, Stage6QuoteStep) and quote_fn.bound_instrument_id == instrument["instrument_id"]
            and quote_fn.x35_model
            and quote_fn.x35_model == instrument["payload"]["extractor_configuration"].get("x35_model")):
        raise ValueError("Stage 6 quote step is not bound to this instrument (or its X35 model differs from "
                         "the pinned one): build it with BoundRuntime.stage6_quote_fn")
    # Ruling 48.3 a / 45 a: a marker from an earlier finished pass must not outlive a pass that stops.
    clear_done(run_dir, DONE_MARKER)
    clock = now or (lambda: datetime.now(timezone.utc))
    metrics = Stage6Metrics()
    setup = {"setup_pointer": config.setup_pointer, "configured_model": config.configured_model,
             "coder_version": config.coder_version}
    institutions = list(institutions)
    for inst in institutions:  # ruling 32 b: a malformed row stops the stage before any call is made
        require_identity(inst)
        require_a8_form(inst)
    for inst in institutions:
        inst_dir = institution_dir(run_dir, inst.institution_id)
        try:
            done = _done(inst_dir)
        except (ValueError, UnicodeDecodeError) as exc:  # corrupt committed artifacts: never overwritten here
            _hold(run_dir, inst_dir, inst.institution_id, [ARTIFACTS_UNREADABLE],
                  {"error": f"{type(exc).__name__}: {exc}"}, {ARTIFACTS_UNREADABLE: f"{type(exc).__name__}: {exc}"})
            metrics.failed.append(inst.institution_id)
            continue
        if done:
            metrics.skipped.append(inst.institution_id)
            continue
        journal = RequestJournal(inst_dir / WORK_DIR / JOURNAL, setup, retry_incomplete=True)
        try:
            result = run_stage6(institution=str(inst.institution["institution_name"]), country=inst.country,
                                pages=inst.pages, observations=inst.observations, records=inst.records,
                                within_page=inst.within_page, quotes=inst.quotes, ask_fn=journal.ask(ask_fn),
                                quote_fn=journal.quote(quote_fn), config=config)
        except STAGE_STOPS + MISSING_UPSTREAM:  # B1 a: a missing upstream input stops the stage here
            raise
        except (ConsolidationError, ValueError, RuntimeError) as exc:  # this institution only
            error = f"{type(exc).__name__}: {exc}"
            _hold(run_dir, inst_dir, inst.institution_id, [EXECUTOR_FAILED], {"error": error},
                  {EXECUTOR_FAILED: error})
            metrics.failed.append(inst.institution_id)
            continue
        finally:
            metrics.live_requests += journal.live
            metrics.replayed_requests += journal.replayed
            metrics.usage[inst.institution_id] = journal.usage()
        held_path = inst_dir / WORK_DIR / HELD_FILE
        if not result.ready:
            reasons, unfinished = hold_reasons(result)
            holds = [asdict(h) for h in result.held]
            doc = {"held": holds, "unfinished": unfinished,
                   "missing_pairs": [list(p) for p in result.missing_pairs],
                   "conflicting_groups": [list(g) for g in result.conflicting_groups]}
            detail = {r: ", ".join(sorted({h["key"] for h in holds if h["reason"] == r})) for r in reasons}
            _hold(run_dir, inst_dir, inst.institution_id, reasons, doc, {r: d for r, d in detail.items() if d})
            metrics.held.append(inst.institution_id)
            continue
        try:
            envelope, provenance = build_envelope(inst, result, config, instrument, run_dir)
            metadata = {"institution_id": inst.institution_id, "n_input_pages": len(inst.pages),
                        "n_input_rows": len(inst.observations),
                        "response_timestamp": clock().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "model_label": config.configured_model, "notes": "v2.7 Stage 6 (T-026 executor)"}
            write_stage6_outputs(inst_dir, envelope=envelope, institution=inst.institution, metadata=metadata,
                                 provenance=provenance)
        except STAGE_STOPS:
            raise
        except ma.MalformedA8Value as exc:  # ruling 32 b (A8 review M1): a malformed stored value stops the stage
            raise UpstreamRowMalformed(inst.institution_id, exc.item, f"A8 values, {exc.where}",
                                       problem=f"is malformed ({exc.detail})") from exc
        except KeyError as exc:  # ruling 32 b: a malformed upstream row is a wiring error: the stage stops
            raise UpstreamRowMalformed(inst.institution_id, repr(exc.args[0]) if exc.args else "a key",
                                       "storage envelope build") from exc
        except ENVELOPE_HOLDS as exc:  # B3: this institution only (MissingUpstreamError included, B1 a)
            error = f"{type(exc).__name__}: {exc}"
            _hold(run_dir, inst_dir, inst.institution_id, [ENVELOPE_FAILED], {"error": error},
                  {ENVELOPE_FAILED: error})
            metrics.failed.append(inst.institution_id)
            continue
        if held_path.exists():
            previous = json.loads(held_path.read_text(encoding="utf-8")).get("reasons", [])
            attrition.record(run_dir, institution_id=inst.institution_id, stage=STAGE, reason=HELD_RELEASED,
                             detail=", ".join(previous))
            held_path.unlink()
        metrics.written.append(inst.institution_id)
    # Ruling 48.3 a: the pass finished (a stage stop raised above and never gets here); held and
    # failed institutions stay pending, and the report decides them from held.json first (ruling
    # 45 a). Marker only: the stage does not skip on it (its per-institution _done skip is unchanged).
    mark_done(run_dir, DONE_MARKER, no_batch=True)
    return metrics


__all__ = [
    "ENVELOPE_FAILED", "ENVELOPE_HOLDS", "EXECUTOR_FAILED", "MISSING_UPSTREAM", "HELD_REASON", "STAGE_STOPS", "HELD_RELEASED", "ObservationInput", "RequestJournal", "Stage6Institution",
    "MERGE_CREDIBLE", "MERGE_INPUT_ITEMS", "MERGE_PRODUCED_A8", "MERGE_REFUSED_R1", "MERGE_REFUSED_R1_R15",
    "MERGE_UNION", "MERGE_UNRULED", "merge_refused_r1",
    "Stage6Metrics", "build_envelope", "hold_reasons", "independence_groups_of", "merge_values", "run_stage6_v27",
    "EXTRACT_REJECT_CAP", "IDENTITY_COLUMNS", "PI_RELEASED", "REASK_SPENT", "WIRING_STOPS", "ExtractRejectCapReached",
    "ReaskSpentUnanswered", "UpstreamRowMalformed", "X35FailCapReached", "require_a8_form", "require_identity",
]
