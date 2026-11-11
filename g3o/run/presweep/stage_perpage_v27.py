"""v2.7 per-page runtime (T-030): T-021/T-023 coding -> support re-gating rounds -> Stage 6 inputs.

Per institution this module drives every stored rendered page through

1. T-021 :func:`g3o.run.presweep.stage_page_code.run_page_code_stage` (the
   ``page_code_v27`` artifact; a page that cannot be coded, e.g. at least 75%
   of its verdict-request parts failed BY COUNT, writes no artifact and is
   recorded in the attrition ledger by that stage);
2. :func:`g3o.classify.question_rounds.complete_page_rounds` (support check,
   recombination, re-gating and the extra rounds of newly eligible questions);
3. T-023 :func:`g3o.run.presweep.stage_activity_code.run_stage` (the
   ``activity_code_v27`` artifact) and
   :func:`~g3o.classify.question_rounds.complete_activity_rounds`;
4. pair support and :func:`g3o.classify.jev_activity_code.finalize_pairs`;
5. the per-page producer (:func:`produce_page`): final per-page values and
   their T-024 support -> T-028 support/coder nodes -> the
   :class:`~g3o.run.presweep.stage_validate_v27.Stage6Institution` inputs
   (reviewed pages, observations, relation records, input quotes, within-page
   decisions, observation fragments, source rows, page artifacts).

Rules carried here, not decided here:

- **Durable resume.** Every jev response is journaled (fsynced) in
  ``<inst>/perpage_v27/journal.jsonl`` before it is used
  (:class:`~g3o.run.presweep.stage_validate_v27.RequestJournal`); the round
  helpers' checkpoints (result plus checked support) are written atomically
  to ``<inst>/perpage_v27/<url_hash>/{page,activity,pairs}.json``. The
  journal key binds the coder setup (setup pointer, configured models, coder
  versions). A re-run loads the checkpoint and asks only what is missing;
  failed requests are never replayed and are asked again (an unidentified,
  billed jev response is kept for accounting only). A response with a request id
  that lacks an asked answer is a completed response here and is replayed on
  resume: its missing answer is a failed part vote, exactly as in an uninterrupted
  run (the Stage 6 Z1 b no-replay rule is not applied to this stage). Support results are serialized whole
  (:func:`support_to_dict`), so a resumed check is never re-run.
- **Publication.** A page with any pending or stopped question (an extra
  round that failed, a gate awaiting it) holds its whole institution: the
  holds go to ``perpage_v27/held.json`` and the attrition ledger, nothing is
  passed to Stage 6, and pending values are never published or turned into
  negatives. A per-page producer error for one page (:data:`PRODUCER_FAILED`:
  a refusal, a page with neither a page-code artifact nor a recorded failure)
  holds that institution the same way and the stage goes on; stage stops
  (:data:`STAGE_STOPS`) still propagate. An absent upstream value
  (``MissingUpstreamError``) is a wiring gap, not institution data: it stops
  the stage loudly (RC-D-033 C2 a). When a
  held institution is later ready, :data:`HELD_RELEASED` is recorded.
- **Provider seams.** The support check (T-022 pass-1 quotes, T-032 pass-2
  quotes, X35 entailment and the T-024 check) and the T-022 activity spans are
  injected (:class:`PerPageProviders`); this module does not call them itself.
  :func:`g3o.run.presweep.perpage_providers_v27.build_perpage_providers` builds
  them over injected extractor and X35 calls, bound to the instrument's pinned
  models (refused otherwise); those calls are journaled per institution.
- **Values with no producer here** are explicit inputs (:class:`PageUpstream`,
  :class:`InstitutionUpstream`) and refuse when absent
  (:class:`~g3o.persist.stage6_adapters.MissingUpstreamError`): the
  non-classifier row values (T-015 source fields, T-022 quote-step values,
  T-024 derived values) and the quote-step codes' support, the stored page
  artifact layout (T-014/T-020), T-025 follow provenance, uncertainty
  flags, independence groups and the merged-activity values RC-D-030 X1 a
  leaves without a rule computable from the merged row
  (:data:`~g3o.run.presweep.stage_validate_v27.MERGE_INPUT_ITEMS`).
- **Reviewed page with no activity (RC-D-030 Y2 a).** It gets one page-level
  source row: ``activity_id`` ``_NA_``, empty ``observation_ids``, its
  page-level values and nodes (support nodes with no observation), the
  upstream source values and codes keyed :data:`NO_ACTIVITY`, and ``_NA_``
  set by rule (``vocabularies/missing/na_label``) on the activity-question
  items the sources table holds.
- **Supported observation (RC-D-030 Y1 b).** ``ActivityObservation.supported`` is
  derived here (:func:`observation_supported`): the observation's final
  ``core.activity_type`` and ``core.action_type`` are both supported (support
  status ``supported`` at the deciding part).
- **Within-page decisions (RC-D-030 Y5 a).** A finalized T-023 pair whose
  combined value is one relation decides that relation, with the lowest
  chosen probability among the parts that chose it, supported only if all of
  those parts are (:func:`within_page_decision`); more than one value, or none
  a part chose, gives no decision and Stage 6 holds the pair.
- **Combined values.** A final classifier value must be carried by a support
  node of one of its parts (the original code or its downgrade replacement);
  gate and rule values get ``set_by_rule`` nodes with mechanical records. A
  combined value no part node carries (e.g. ``unknown`` from failed votes) is
  refused as a per-institution hold (RC-D-030 Y3 b): ``perpage_v27/held.json``
  names the page and values (stage ``combined_value_uncarried``), the
  attrition ledger records it, and nothing of the institution reaches Stage 6.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from g3o.classify import jev_activity_code as jac
from g3o.classify import jev_page_code as jpc
from g3o.classify.jev_activity_code import (
    ActivityCoderConfig,
    ActivityPageInput,
    PageActivityResult,
    PairResult,
    finalize_pairs,
    nano_values,
    value_label,
)
from g3o.classify.jev_page_code import PageCoderConfig, PageCodeResult, PageInput, contact_text
from g3o.classify.permanent_pilot import PERMANENT_PILOT_RULE
from g3o.classify.question_rounds import (
    ActivityRoundResult,
    PageRoundResult,
    complete_activity_rounds,
    complete_page_rounds,
)
from g3o.common import attrition
from g3o.common.artifact_io import artifact_exists, read_artifact
from g3o.common.cost_monitor import BudgetExceededError, UnpricedModelError
from g3o.common.instrument import canonical_json, sha256_text
from g3o.common.jev_client import JevAccountError
from g3o.common.jev_record import CoderRecord
from g3o.common.part_combine import NOT_COVERED
from g3o.common.paths import institution_dir
from g3o.common.source_fields import MissingUpstreamError as SourceFieldsMissingUpstreamError
from g3o.common.storage import METADATA_ITEMS, table_fields
from g3o.common.storage_fields import FIELDS
from g3o.common.support_check import (
    CodeEvidence,
    Entailment,
    PageSources,
    QuoteMatch,
    SupportGateError,
    SupportResult,
    _locate,
    _locate_by_words,
    check_code,
)
from g3o.extract.batch import url_hash
from g3o.persist.stage6_adapters import (
    MissingUpstreamError,
    PageArtifact,
    SupportContext,
    coder_nodes,
    replace_with_retry,
    support_nodes,
)
from g3o.run.presweep import stage_activity_code, stage_page_code
from g3o.run.presweep.stage_validate_v27 import ObservationInput, RequestJournal, Stage6Institution
from g3o.validate.consolidate_v27 import (
    MISSING,
    RELATIONS,
    ActivityObservation,
    ConsolidationError,
    RelationDecision,
    ReviewedPage,
    outcome_values,
)
from g3o.validate.stage6_v27 import InputQuote, ObservationRecord, Stage6QuoteNotApproved

STAGE = "perpage_v27"
WORK_DIR = "perpage_v27"
JOURNAL = "journal.jsonl"
HELD_FILE = "held.json"
HELD_REASON = "perpage_held"
HELD_RELEASED = "perpage_held_released"  # appended when a held institution's per-page hold clears
ACTIVITY_DIR = "activity_code_v27"
CHECKPOINT_FORMAT = "g3o-perpage-checkpoint-v1"
PIPELINE = "web_extract"
FAILED_PAGE_VERDICT = "not_assessable"  # an unreviewed page keeps a signed verdict code; never counted
FAILED_PAGE_SUPPORT = "not_asked"  # R-045: no support check ran on a page that was not coded
ACTIVITY_ITEMS = frozenset(table_fields("activities")) - {"core.n_sources", "core.confidence"} - set(METADATA_ITEMS)
SOURCE_ITEMS = frozenset(table_fields("sources")) - set(METADATA_ITEMS)
PRODUCED_CODERS = frozenset({"classifier"})
T015_CLASSIFIER = "core.source_type"  # a classifier item T-015 owns: an upstream value and code

#: RC-D-030 Y1 b: an observation is supported when both of these final values are supported.
SUPPORTED_ITEMS = ("core.activity_type", "core.action_type")
#: RC-D-030 Y2 a: upstream key (source values, codes) of a no-activity page's page-level source row.
NO_ACTIVITY = "_NA_"
#: Signed slot of the rule "store `_NA_` on items of a row that has no activity" (R-045, all-01 b).
NA_RULE = "vocabularies/missing/na_label"
VALUES_PRODUCER = "T-015 / T-022 / T-024 row values with no producer on this branch"
ARTIFACT_PRODUCER = "T-014/T-020 stored page artifact and its segment layout"
FOLLOW_PRODUCER = "T-025 follow provenance (followed / attempted page)"
UNCARRIED_STAGE = "combined_value_uncarried"  # RC-D-030 Y3 b: per-institution hold
#: a per-page producer refused or failed for one page (held.json names the error): per-institution hold
PRODUCER_FAILED = "page_producer_failed"
#: Errors that stop the whole stage; every other producer error holds its institution only.
#: Both ``MissingUpstreamError`` classes subclass ``ValueError``; they are listed here so the
#: per-institution ``ValueError`` handlers never swallow a wiring gap (RC-D-033 C2 a).
STAGE_STOPS = (JevAccountError, stage_page_code.StageStopped, SupportGateError, Stage6QuoteNotApproved,
               BudgetExceededError, UnpricedModelError, MissingUpstreamError, SourceFieldsMissingUpstreamError)


class UncarriedCombinedValue(ConsolidationError):
    """A final value no part support node carries (RC-D-030 Y3 b): the institution is held."""

    def __init__(self, page_id: str, values: Sequence[str]) -> None:
        super().__init__(f"no part support node carries {list(values)} on page {page_id}")
        self.page_id, self.values = page_id, list(values)


# ---------------------------------------------------------------------------
# SupportResult (de)serialization
# ---------------------------------------------------------------------------


def support_to_dict(sr: SupportResult) -> dict[str, Any]:
    """Whole T-024 result, JSON-safe; :func:`support_from_dict` restores an equal object."""
    out = asdict(sr)
    out["flags"] = list(sr.flags)
    return out


def support_from_dict(doc: Mapping[str, Any]) -> SupportResult:
    data = dict(doc)
    if data.get("match") is not None:
        data["match"] = QuoteMatch(**data["match"])
    if data.get("entailment") is not None:
        data["entailment"] = Entailment(**data["entailment"])
    data["flags"] = tuple(data.get("flags") or ())
    return SupportResult(**data)


# ---------------------------------------------------------------------------
# Durable checkpoints
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as stream:
        stream.write(text.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    replace_with_retry(tmp, path)


class Checkpoint:
    """One round helper's durable state: its result and the support checked so far."""

    def __init__(self, path: Path, kind: str) -> None:
        self.path, self.kind = path, kind
        self.writes = 0

    def save(self, result: Any, support: Sequence[SupportResult]) -> None:
        doc = {"format": CHECKPOINT_FORMAT, "kind": self.kind, "result": result.to_dict(),
               "support": [support_to_dict(s) for s in support]}
        _atomic_write(self.path, canonical_json(doc))
        self.writes += 1

    def load(self) -> tuple[Any, tuple[SupportResult, ...]] | None:
        if not self.path.exists():
            return None
        doc = json.loads(self.path.read_bytes().decode("utf-8"))
        if doc.get("format") != CHECKPOINT_FORMAT or doc.get("kind") != self.kind:
            raise ValueError(f"unsupported per-page checkpoint: {self.path}")
        cls = PageCodeResult if self.kind == "page" else PageActivityResult
        return cls.from_dict(doc["result"]), tuple(support_from_dict(s) for s in doc["support"])


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageUpstream:
    """Explicit per-page inputs whose producers are absent here (refuse when missing).

    ``artifact_path`` (run-relative) and ``segments`` locate the stored page
    artifact (each part ``chunk_id`` and ``<page>#chrome``). ``activity_values``
    / ``source_values`` hold, per T-022 activity id, the non-classifier items of
    the activities / sources table rows; ``codes`` the support results and
    coder records of the quote-step values among them. A page with no activity
    keys its page-level source row's values and codes :data:`NO_ACTIVITY`. ``ActivityObservation.supported``
    is derived by the producer (RC-D-030 Y1 b), not an input.
    """

    artifact_path: str | None = None
    segments: Mapping[str, tuple[int, int]] | None = None
    followed: bool | None = None
    activity_values: Mapping[str, Mapping[str, Any]] | None = None
    source_values: Mapping[str, Mapping[str, Any]] | None = None
    codes: Mapping[str, Sequence[tuple[SupportResult, CoderRecord]]] | None = None


@dataclass(frozen=True)
class PageSpec:
    page: PageInput
    upstream: PageUpstream


@dataclass(frozen=True)
class InstitutionUpstream:
    independence_groups: Mapping[str, str] | None = None  # source id -> group (P15 producer absent)
    merged_values: Mapping[tuple[str, ...], Mapping[str, Any]] | None = None
    uncertainty_flags: Callable[[SupportResult], Sequence[str] | None] | None = None


@dataclass(frozen=True)
class PerPageInstitution:
    run_id: str
    institution_uid: str
    institution: Mapping[str, Any]  # the six master identity columns
    country: str | None
    pages: Sequence[PageSpec]  # attempted order (page order of the pooled quotes)
    upstream: InstitutionUpstream

    @property
    def institution_id(self) -> str:
        return str(self.institution["institution_id"])


PageSupportFn = Callable[[PageInput, PageCodeResult, Sequence[CoderRecord]], Sequence[SupportResult]]
ActivityInputFn = Callable[[PageInput, PageRoundResult], ActivityPageInput | None]
ActivitySupportFn = Callable[[ActivityPageInput, PageActivityResult, Sequence[tuple[str, CoderRecord]]],
                             Sequence[SupportResult]]
PairSupportFn = Callable[[ActivityPageInput, PageActivityResult], Sequence[SupportResult]]


@dataclass(frozen=True)
class PerPageProviders:
    """Injected seams: T-024 support for page codes, T-022 spans, T-032/T-024 activity and pair support."""

    page_support: PageSupportFn
    activity_input: ActivityInputFn
    activity_support: ActivitySupportFn
    pair_support: PairSupportFn


@dataclass
class PerPageMetrics:
    ready: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    failed_pages: list[str] = field(default_factory=list)
    live_requests: int = 0
    replayed_requests: int = 0
    checkpoint_writes: int = 0
    usage: dict[str, dict[str, int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# The per-page producer (T-028 per-page fragments)
# ---------------------------------------------------------------------------


def _support_key(sr: SupportResult) -> tuple[Any, ...]:
    return (sr.activity_id, sr.item_id, sr.part, sr.chunk_id, sr.linked_activity)


def _index(support: Iterable[SupportResult]) -> dict[tuple[Any, ...], SupportResult]:
    out: dict[tuple[Any, ...], SupportResult] = {}
    for sr in support:
        if out.setdefault(_support_key(sr), sr) is not sr:
            raise ValueError(f"duplicate support identity {_support_key(sr)}")
    return out


def _rule_support(rec: CoderRecord, activity_id: str | None, sources: PageSources) -> SupportResult:
    if not rec.rule_reference:
        raise ValueError(f"mechanical record for {rec.item_id} names no rule")
    return check_code(CodeEvidence(rec.item_id, str(rec.chosen_value), rec.chunk_id, part=rec.item_part,
                                   rule_name=rec.rule_reference, activity_id=activity_id), sources)


def _mechanical(item: str, part: str | None, qid: str | None, value: Any, rule: str, *, coder_version: str,
                qsv: str, setup_pointer: str) -> CoderRecord:
    return CoderRecord(item_id=item, item_part=part, question_id=qid, support_id=None, observation_id=None,
                       chunk_id=None, coder_type="mechanical", coder_version=coder_version,
                       configured_model=None, actual_response_model=None, request_id=None,
                       question_set_version=qsv, setup_pointer=setup_pointer, answer_type="rule",
                       chosen_value=value, confidence=None, probability_distribution=None, rule_reference=rule)


def _listify(values: Mapping[str, Any]) -> dict[str, Any]:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in values.items()}


def _carried(row: Mapping[str, Any]) -> list[str]:
    """Classifier/quote-step values of a row that no support node carries."""
    missing = []
    for item, value in row["values"].items():
        f = FIELDS[item]
        if f["coder"] not in {"classifier", "quote_step"}:
            continue
        pairs = (list(value.items()) if "parts" in f else [(None, v) for v in value]
                 if isinstance(value, list) else [(None, value)])
        for part, selected in pairs:
            if not any(s["item_id"] == item and s["item_part"] == part and s["value_json"] == selected
                       for s in row["item_support"]):
                missing.append(f"{item}/{part}={selected!r}")
    return missing


class _Row:
    def __init__(self, emit: Callable[..., Any]) -> None:
        self.values: dict[str, Any] = {}
        self.item_support: list[dict[str, Any]] = []
        self.coder_records: list[dict[str, Any]] = []
        self._emit = emit
        self._ids: set[str] = set()

    def add(self, sr: SupportResult, rec: CoderRecord, ctx: SupportContext) -> dict[str, Any]:
        nodes, projections, provenance = self._emit(sr, rec, ctx)
        for node in nodes:
            if node["support_id"] not in self._ids:
                self._ids.add(node["support_id"])
                self.item_support.append(node)
        self.coder_records.extend(projections)
        return {"nodes": nodes, "provenance": provenance}

    def doc(self) -> dict[str, Any]:
        return {"values": _listify(self.values), "item_support": self.item_support,
                "coder_records": self.coder_records}


@dataclass
class PageProduct:
    page: ReviewedPage
    observations: list[ActivityObservation] = field(default_factory=list)
    records: list[ObservationRecord] = field(default_factory=list)
    quotes: list[InputQuote] = field(default_factory=list)
    within: list[RelationDecision] = field(default_factory=list)
    observation_inputs: dict[str, ObservationInput] = field(default_factory=dict)
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifacts: dict[str, PageArtifact] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)


def observation_id(page_id: str, activity_id: str) -> str:
    return f"{page_id}.{activity_id}"


def source_id(number: int) -> str:
    """Source claims are ``S<n>`` per institution (response_v27), numbered in page then activity order."""
    return f"S{number}"


def _passage_order(artifact: PageArtifact, sr: SupportResult) -> int:
    start, _ = artifact.span(sr.quote_chunk_id)
    text = artifact.segment_text(sr.quote_chunk_id)
    found = _locate(sr.supporting_text, text) or _locate_by_words(sr.supporting_text, text)
    if found is None:
        raise ConsolidationError(f"supported quote of {sr.item_id} is not located on its stored segment")
    return start + found[0]


def observation_supported(aid: str, outcomes: Mapping[str, Any],
                          support: Mapping[tuple[Any, ...], SupportResult]) -> bool:
    """RC-D-030 Y1 b: the final ``activity_type`` and ``action_type`` are both supported.

    A value is supported when its final outcome was combined from the parts without
    failing and the support result at its deciding part has status ``supported``; a
    gated, rule-set, failed (downgraded) or missing value is not.
    """
    for item in SUPPORTED_ITEMS:
        o = next((o for o in outcomes.values() if o.item_id == item and o.part is None), None)
        if o is None or o.state != "combined" or o.failed or o.part_id is None:
            return False
        sr = support.get((aid, item, None, o.part_id, None))
        if sr is None or sr.support_status != "supported" or sr.value != o.value:
            return False
    return True


def within_page_decision(pair: PairResult, answered: Sequence[tuple[CoderRecord, SupportResult]]
                         ) -> tuple[str, float | None, str] | None:
    """RC-D-030 Y5 a: a finalized T-023 pair -> ``(relation, probability, support status)`` or None.

    ``answered`` pairs each answered part record (not the temporary part answer)
    with its checked support, in part order. One relation in the combined value:
    that relation, the lowest chosen probability among the parts that chose it
    (None when one of them has none), ``supported`` only if all of those parts
    are (else the first other status). More than one value, a value outside the
    relation vocabulary, an unfinished outcome, or a value no part chose (e.g.
    ``unknown`` from failed votes): None, so the pair is held.
    """
    if pair.outcome.state != "combined":
        return None
    raw = pair.outcome.value
    values = list(dict.fromkeys(raw if isinstance(raw, (list, tuple)) else [raw]))
    if len(values) != 1 or values[0] not in RELATIONS:
        return None
    relation = values[0]
    chose = [(rec, sr) for rec, sr in answered if rec.chosen_value == relation]
    if not chose:
        return None
    probs = [rec.chosen_answer_probability for rec, _ in chose]
    probability = None if any(p is None for p in probs) else min(probs)
    status = next((sr.support_status for _, sr in chose if sr.support_status != "supported"), "supported")
    return relation, probability, status


def _activity_source_items(config: ActivityCoderConfig) -> list[str]:
    """Sources-table items asked by the activity question set (the evaluation items), in set order."""
    qset = config.question_set if config.question_set is not None else jac.load_set("activity")
    return list(dict.fromkeys(q["item_id"] for q in qset["questions"] if q["item_id"] in SOURCE_ITEMS))


def failed_page(spec: PageSpec, reason: str) -> ReviewedPage:
    """An attempted page T-021 could not code (no artifact): unreviewed, failed, reason kept."""
    if spec.upstream.followed is None:
        raise MissingUpstreamError(FOLLOW_PRODUCER, [spec.page.page_id])
    return ReviewedPage(spec.page.page_id, PIPELINE, FAILED_PAGE_VERDICT, None, FAILED_PAGE_SUPPORT, False, True,
                        spec.upstream.followed, (), (), (), failure_reason=reason)


def produce_page(*, run_dir: Path, run_id: str, institution_uid: str, spec: PageSpec, page_order: int,
                 first_source: int,
                 page_round: PageRoundResult, activity_input: ActivityPageInput | None,
                 activity_round: ActivityRoundResult | None, pairs: Sequence[PairResult],
                 pair_support: Sequence[SupportResult], page_config: PageCoderConfig,
                 activity_config: ActivityCoderConfig, instrument: dict[str, Any],
                 uncertainty_flags: Callable[[SupportResult], Sequence[str] | None] | None) -> PageProduct:
    """Final per-page values and their support -> the Stage 6 per-page inputs of one coded page."""
    page, up = spec.page, spec.upstream
    if not (page_round.complete and (activity_round is None or activity_round.complete)):
        raise ConsolidationError("page has pending questions; nothing is produced")
    if up.followed is None:
        raise MissingUpstreamError(FOLLOW_PRODUCER, [page.page_id])
    if up.artifact_path is None or up.segments is None:
        raise MissingUpstreamError(ARTIFACT_PRODUCER, [page.page_id])
    text = (run_dir / up.artifact_path).read_bytes().decode("utf-8")
    result = page_round.result
    sources = PageSources(page.page_id, {c.chunk_id: c.text for c in result.chunks}, contact_text(page))
    acts = {} if activity_round is None else {a.activity_id: a for a in activity_round.result.activities}
    finals = {} if activity_round is None else {f.activity_id: f for f in activity_round.final}
    keys = list(acts) or [NO_ACTIVITY]  # source-row units: one per activity, or the page (Y2 a)
    for name, value, need in (("activity_values", up.activity_values, list(acts)),
                              ("source_values", up.source_values, keys), ("codes", up.codes, keys)):
        if need and (value is None or set(need) - set(value)):
            raise MissingUpstreamError(f"{VALUES_PRODUCER} ({name})",
                                       sorted(set(need) - set(value or {})) or [page.page_id])
    if uncertainty_flags is None:
        raise MissingUpstreamError("T-024 derived-field producer (core.uncertainty_flags)", [page.page_id])
    labels = activity_config.labels if activity_config.labels is not None else jac.default_labels()
    qsv_page = result.question_set_version
    qsv_act = None if activity_round is None else activity_round.result.question_set_version
    out = PageProduct(page=None)  # type: ignore[arg-type]

    def emit(sr: SupportResult, rec: CoderRecord, ctx: SupportContext, artifact: PageArtifact) -> Any:
        flags = uncertainty_flags(sr)
        nodes = support_nodes(sr, sources, artifact, replace(ctx, uncertainty_flags=flags), instrument)
        rec = replace(rec, support_id=nodes.original["support_id"], observation_id=nodes.original["observation_id"])
        projection, final_projection, _ = coder_nodes(rec, nodes, instrument)
        out.provenance.append(nodes.provenance)
        return ([n for n in (nodes.original, nodes.final) if n is not None],
                [c for c in (projection, final_projection) if c is not None], nodes.provenance)

    page_support = _index(page_round.support)
    act_support = _index(() if activity_round is None else activity_round.support)
    pair_index = _index(pair_support)

    def page_codes() -> list[tuple[SupportResult, CoderRecord]]:
        codes = []
        for rec in result.records:
            if rec.coder_type == "classifier":
                if rec.chosen_value == NOT_COVERED:
                    continue  # the temporary part answer is never checked or stored (R-044)
                codes.append((page_support[(None, rec.item_id, rec.item_part, rec.chunk_id, None)], rec))
            else:
                codes.append((_rule_support(rec, None, sources), rec))
        for iid in page_round.final.regated:
            o = page_round.final.items[iid]
            rec = _mechanical(iid, None, None, o.value, o.rule_reference, coder_version=page_config.coder_version,
                              qsv=qsv_page, setup_pointer=page_config.setup_pointer)
            codes.append((_rule_support(rec, None, sources), rec))
        return codes

    def activity_codes(aid: str) -> list[tuple[SupportResult, CoderRecord]]:
        act, fin = acts[aid], finals[aid]
        codes = []
        for rec in act.records:
            if rec.item_id in jac.PAIR_ITEMS:
                continue  # pair records come from the finalized pairs
            if rec.coder_type == "classifier":
                if rec.chosen_value == NOT_COVERED:
                    continue
                codes.append((act_support[(aid, rec.item_id, rec.item_part, rec.chunk_id, None)], rec))
            else:
                codes.append((_rule_support(rec, aid, sources), rec))
        rule_set = [(qid, o) for qid, o in fin.outcomes.items()
                    if qid in fin.regated or o.rule_reference == PERMANENT_PILOT_RULE]
        for qid, o in rule_set:
            rec = _mechanical(o.item_id, o.part, qid, o.value, o.rule_reference,
                              coder_version=activity_config.coder_version, qsv=qsv_act,
                              setup_pointer=activity_config.setup_pointer)
            codes.append((_rule_support(rec, aid, sources), rec))
        return codes

    page_values = outcome_values(page_round.final.items)
    page_list = page_codes()
    page_nodes: list[dict[str, Any]] = []
    page_coders: list[dict[str, Any]] = []
    oids = {aid: observation_id(page.page_id, aid) for aid in acts}
    sids = {aid: source_id(first_source + n) for n, aid in enumerate(keys)}
    artifacts = {aid: PageArtifact(sids[aid], up.artifact_path, text, dict(up.segments)) for aid in keys}
    spans = {} if activity_input is None else {s.activity_id: s for s in activity_input.spans}
    for aid in keys:
        oid, sid, artifact = oids.get(aid), sids[aid], artifacts[aid]
        ctx = SupportContext(run_id, institution_uid, oid, sid, None)
        a_row = _Row(lambda sr, rec, c, a=artifact: emit(sr, rec, c, a))
        s_row = _Row(lambda sr, rec, c, a=artifact: emit(sr, rec, c, a))
        if oid is None:  # Y2 a: activity-question items of the sources table take _NA_ by rule
            act_values = {i: NO_ACTIVITY for i in _activity_source_items(activity_config)}
        else:
            act_values = outcome_values(finals[aid].outcomes)
        produced_a = {k: v for k, v in act_values.items() if k in ACTIVITY_ITEMS}
        produced_s = {**{k: v for k, v in page_values.items() if k in SOURCE_ITEMS},
                      **{k: v for k, v in act_values.items() if k in SOURCE_ITEMS}}
        units = [(produced_s, up.source_values[aid], SOURCE_ITEMS, s_row)]
        if oid is not None:
            units.insert(0, (produced_a, up.activity_values[aid], ACTIVITY_ITEMS, a_row))
        for produced, given, table, row in units:
            clash = sorted(set(produced) & set(given))
            if clash:
                raise ValueError(f"upstream values overwrite produced classifier values: {clash}")
            given_classifier = sorted(k for k in given if FIELDS[k]["coder"] in PRODUCED_CODERS
                                      and k != T015_CLASSIFIER)
            if given_classifier:
                raise ValueError(f"classifier values must come from the coders: {given_classifier}")
            row.values.update({**given, **produced})
            missing = sorted(table - set(row.values))
            if missing:
                raise MissingUpstreamError(VALUES_PRODUCER, missing)
        for sr, rec in page_list:
            added = s_row.add(sr, rec, ctx)
            if aid == keys[0]:
                page_nodes.extend(added["nodes"])
        if oid is not None:
            for sr, rec in activity_codes(aid):
                (s_row if rec.item_id in SOURCE_ITEMS else a_row).add(sr, rec, ctx)
        else:
            for item, value in act_values.items():
                rec = _mechanical(item, None, None, value, NA_RULE, coder_version=page_config.coder_version,
                                  qsv=qsv_page, setup_pointer=page_config.setup_pointer)
                s_row.add(_rule_support(rec, None, sources), rec, ctx)
        for sr, rec in up.codes[aid]:
            if FIELDS[rec.item_id]["coder"] != "quote_step" and rec.item_id != T015_CLASSIFIER:
                raise ValueError(f"upstream code for {rec.item_id} is not a quote-step or T-015 value")
            if oid is None and rec.item_id not in SOURCE_ITEMS:
                raise ValueError(f"upstream code for {rec.item_id} on a page with no activity")
            (a_row if rec.item_id in ACTIVITY_ITEMS else s_row).add(sr, rec, ctx)
        if aid == keys[0]:
            page_ids = {n["support_id"] for n in page_nodes}
            page_coders = [c for c in s_row.coder_records if c["support_id"] in page_ids]
        out.artifacts[sid] = artifact
        src = s_row.doc()
        src.update(observation_ids=[] if oid is None else [oid], page_artifact_path=up.artifact_path,
                   page_content_sha256=sha256_text(text))
        out.sources[sid] = src
        docs = [src]
        if oid is not None:
            out.observation_inputs[oid] = ObservationInput(oid, sid, a_row.doc())
            docs.insert(0, a_row.doc())
        for doc in docs:
            missing = _carried(doc)
            if missing:
                raise UncarriedCombinedValue(page.page_id, missing)
    for pair in pairs:  # within-page decisions; nodes on the earlier (lhs) observation's row
        lhs, rhs = pair.activity_id, pair.linked_activity
        if lhs not in acts or rhs not in acts:
            raise ConsolidationError("pair names an activity that was not coded")
        frag = out.observation_inputs[oids[lhs]].row
        ctx = SupportContext(run_id, institution_uid, oids[lhs], sids[lhs], None)
        checked: list[tuple[SupportResult, list[str]]] = []
        answered: list[tuple[CoderRecord, SupportResult]] = []
        records: list[dict[str, Any]] = []
        for rec in pair.records:
            if rec.chosen_value == NOT_COVERED:
                continue
            sr = pair_index[(lhs, rec.item_id, rec.item_part, rec.chunk_id, rhs)]
            nodes, projections, _ = emit(sr, rec, ctx, artifacts[lhs])
            known = {s["support_id"] for s in frag["item_support"]}
            frag["item_support"].extend(n for n in nodes if n["support_id"] not in known)
            frag["coder_records"].extend(projections)
            records.extend(projections)
            checked.append((sr, [n["support_id"] for n in nodes]))
            answered.append((rec, sr))
        decided = within_page_decision(pair, answered)
        if decided is None:
            continue  # no decision: Stage 6 holds the institution on the missing pair
        relation, probability, status = decided
        if relation not in RELATIONS:
            raise ConsolidationError(f"within-page relation {relation!r} is outside the signed vocabulary")
        ids = tuple(i for sr, node_ids in checked if relation in (sr.original_value, sr.value) for i in node_ids)
        out.within.append(RelationDecision(oids[lhs], oids[rhs], relation, probability, status, tuple(records),
                                           ids, "within_page"))
    verdict = page_round.final.items[jpc.VERDICT]
    if verdict.state == "combined":
        vsr = page_support.get((None, jpc.VERDICT, None, verdict.part_id, None))
        if vsr is None:
            raise ConsolidationError("final page verdict has no support result at its deciding part")
        verdict_status = vsr.support_status
    else:
        verdict_status = "set_by_rule"
    out.page = ReviewedPage(page.page_id, PIPELINE, verdict.value, verdict.probability, verdict_status, True, False,
                            up.followed, tuple(sids[a] for a in keys), tuple(page_coders), tuple(page_nodes))
    for aid in acts:
        oid, sid, artifact = oids[aid], sids[aid], artifacts[aid]
        frag = out.observation_inputs[oid].row
        src_values = out.sources[sid]["values"]
        date = src_values.get("core.source_publication_date")
        date = date if isinstance(date, str) and date not in MISSING else None
        type_label = value_label("core.source_type", None, src_values.get("core.source_type"), labels)
        quotes = []
        by_id = {n["support_id"]: n for n in frag["item_support"]}
        all_sr = [*(sr for sr, rec in activity_codes(aid)), *(sr for sr, _ in up.codes[aid])]
        for sr in all_sr:
            if sr.support_status != "supported" or sr.supporting_text is None or sr.item_id not in ACTIVITY_ITEMS:
                continue
            node = next(n for n in by_id.values() if n["item_id"] == sr.item_id and n["item_part"] == sr.part
                        and n["chunk_id"] == sr.chunk_id and n["value_json"] == sr.original_value
                        and n["input_support_ids"] == [])
            quotes.append(InputQuote(node["support_id"], oid, sid, sources, sr.chunk_id, sr.quote_chunk_id,
                                     sr.supporting_text, type_label, date, str(frag["values"]["core.stage_as_of"]),
                                     page.url, page_order, _passage_order(artifact, sr)))
        quotes.sort(key=lambda q: (q.passage_order, q.support_id))
        out.quotes.extend(quotes)
        out.records.append(ObservationRecord(oid, page.page_id, dict(frag["values"]), page.url, tuple(quotes)))
        out.observations.append(ActivityObservation(
            oid, page.page_id, finals[aid].outcomes, nano_values(spans[aid]),
            observation_supported(aid, finals[aid].outcomes, act_support),
            tuple(frag["coder_records"]), tuple(frag["item_support"])))
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _page_dir(run_dir: Path, page: PageInput) -> Path:
    return institution_dir(run_dir, page.institution_id) / WORK_DIR / url_hash(page.url)


def _failure_reason(run_dir: Path, page: PageInput) -> str:
    reasons = [r["reason"] for r in attrition.read_records(run_dir)
               if r.get("stage") == stage_page_code.STAGE and r.get("url") == page.url
               and r.get("reason") != stage_page_code.PART_FAILURES]
    if not reasons:
        raise RuntimeError(f"page {page.page_id} has neither a page-code artifact nor a recorded failure")
    return reasons[-1]


@dataclass
class _PageState:
    spec: PageSpec
    page_round: PageRoundResult | None = None
    activity_input: ActivityPageInput | None = None
    activity_round: ActivityRoundResult | None = None
    pairs: tuple[PairResult, ...] = ()
    pair_support: tuple[SupportResult, ...] = ()
    failure: str | None = None
    holds: list[dict[str, Any]] = field(default_factory=list)


def _rounds_for_page(run_dir: Path, st: _PageState, ask: Any, providers: PerPageProviders,
                     page_config: PageCoderConfig, activity_config: ActivityCoderConfig,
                     metrics: PerPageMetrics) -> None:
    page = st.spec.page
    pdir = _page_dir(run_dir, page)
    page_ckpt = Checkpoint(pdir / "page.json", "page")
    saved = page_ckpt.load()
    if saved is None:
        result = PageCodeResult.from_json(read_artifact(stage_page_code.artifact_path(
            run_dir, page.institution_id, page.url)))
        support: tuple[SupportResult, ...] = ()
    else:
        result, support = saved
    st.page_round = complete_page_rounds(
        page, result, support, ask_fn=ask, config=page_config,
        check_support=lambda r, recs: providers.page_support(page, r, recs), checkpoint=page_ckpt.save)
    metrics.checkpoint_writes += page_ckpt.writes
    if not st.page_round.complete:
        st.holds.append({"page_id": page.page_id, "stage": "page_rounds", "items": sorted(
            k for k, o in st.page_round.final.items.items() if o.state in ("pending", "stopped"))})
        return
    inp = providers.activity_input(page, st.page_round)
    st.activity_input = inp
    if inp is None:
        return
    act_ckpt = Checkpoint(pdir / "activity.json", "activity")
    saved_act = act_ckpt.load()
    if saved_act is None:
        art = stage_activity_code.artifact_path(institution_dir(run_dir, page.institution_id) / ACTIVITY_DIR,
                                                page.page_id)
        if artifact_exists(art):  # coded, then interrupted before the first checkpoint
            act_result = PageActivityResult.from_json(read_artifact(art))
        else:
            act_result = stage_activity_code.run_stage([inp], ask, activity_config, out_dir=art.parent,
                                                       run_dir=run_dir).results[0]
        act_ckpt.save(act_result, ())
        act_support: tuple[SupportResult, ...] = ()
    else:
        act_result, act_support = saved_act
    st.activity_round = complete_activity_rounds(
        inp, act_result, act_support, ask_fn=ask, config=activity_config,
        check_support=lambda r, recs: providers.activity_support(inp, r, recs), checkpoint=act_ckpt.save)
    metrics.checkpoint_writes += act_ckpt.writes
    if not st.activity_round.complete:
        st.holds.append({"page_id": page.page_id, "stage": "activity_rounds", "items": sorted(
            f"{a.activity_id}:{q}" for a in st.activity_round.final for q, o in a.outcomes.items()
            if o.state in ("pending", "stopped"))})
        return
    result_now = st.activity_round.result
    if result_now.pairs:
        pair_path = pdir / "pairs.json"
        if pair_path.exists():
            doc = json.loads(pair_path.read_bytes().decode("utf-8"))
            if doc.get("format") != CHECKPOINT_FORMAT or doc.get("kind") != "pairs":
                raise ValueError(f"unsupported per-page checkpoint: {pair_path}")
            st.pair_support = tuple(support_from_dict(s) for s in doc["support"])
        else:
            st.pair_support = tuple(providers.pair_support(inp, result_now))
            _atomic_write(pair_path, canonical_json({"format": CHECKPOINT_FORMAT, "kind": "pairs",
                                                     "support": [support_to_dict(s) for s in st.pair_support]}))
            metrics.checkpoint_writes += 1
        st.pairs = finalize_pairs(result_now, st.pair_support, activity_config)


def run_perpage_v27(run_dir: Path, institutions: Iterable[PerPageInstitution], *, ask_fn: Any,
                    providers: PerPageProviders, page_config: PageCoderConfig,
                    activity_config: ActivityCoderConfig, instrument: dict[str, Any],
                    cost_check_callback: Callable[[str, dict[str, int]], bool] | None = None,
                    test_only_unbound_providers: bool = False,
                    ) -> tuple[list[Stage6Institution], PerPageMetrics]:
    """Code, re-gate and produce every page; return the institutions ready for Stage 6.

    ``JevAccountError`` / budget stops propagate after the journal and
    checkpoints hold what finished; the next run resumes from them.

    ``providers`` must come from
    :func:`~g3o.run.presweep.perpage_providers_v27.build_perpage_providers` for this
    instrument, declaring its pinned extractor and X35 models (QA3 F3); their extractor
    and X35 calls are journaled per institution. ``test_only_unbound_providers`` lifts
    that check for offline fakes in tests only.
    """
    if page_config.setup_pointer != instrument["instrument_id"] or \
            activity_config.setup_pointer != instrument["instrument_id"]:
        raise ValueError("per-page coder configuration is bound to a different instrument")
    cfg = instrument["payload"]["extractor_configuration"]
    if not test_only_unbound_providers and not (
            getattr(providers, "bound_instrument_id", None) == instrument["instrument_id"]
            and getattr(providers, "extractor_model", None) == cfg.get("model")
            and getattr(providers, "x35_model", None) and providers.x35_model == cfg.get("x35_model")
            and hasattr(providers, "with_seams")):
        raise ValueError("per-page providers are not bound to this instrument (or their extractor / X35 model "
                         "differs from the pinned one): build them with build_perpage_providers")
    metrics = PerPageMetrics()
    ready: list[Stage6Institution] = []
    # The journal key binds the setup: a response recorded under another setup is never replayed.
    setup = {"setup_pointer": page_config.setup_pointer,
             "page": {"configured_model": page_config.configured_model, "coder_version": page_config.coder_version},
             "activity": {"configured_model": activity_config.configured_model,
                          "coder_version": activity_config.coder_version}}
    for inst in institutions:
        inst_dir = institution_dir(run_dir, inst.institution_id)
        journal = RequestJournal(inst_dir / WORK_DIR / JOURNAL, setup)
        ask = journal.ask(ask_fn)
        inst_providers = providers
        if hasattr(providers, "with_seams"):  # extractor and X35 calls journaled (usage, durable resume)
            inst_providers = providers.with_seams(*journal.seams(providers.journal_prompt))
        states = [_PageState(spec) for spec in inst.pages]
        broken: dict[str, Any] | None = None  # a producer error for one page: this institution is held
        try:
            coded = stage_page_code.run_page_code_stage(run_dir, [s.spec.page for s in states], ask_fn=ask,
                                                        config=page_config, concurrency=1,
                                                        cost_check_callback=cost_check_callback)
            if coded.stopped_early:  # the cost check stopped T-021: uncoded pages are not failures
                raise stage_page_code.StageStopped("page coding stopped by the cost check")
            for st in states:
                page = st.spec.page
                if not artifact_exists(stage_page_code.artifact_path(run_dir, page.institution_id, page.url)):
                    try:
                        st.failure = _failure_reason(run_dir, page)
                    except STAGE_STOPS:
                        raise
                    except (ConsolidationError, ValueError, RuntimeError) as exc:
                        broken = _producer_hold(page.page_id, exc)
                        break
                    metrics.failed_pages.append(page.page_id)
                    continue
                _rounds_for_page(run_dir, st, ask, inst_providers, page_config, activity_config, metrics)
        finally:
            metrics.live_requests += journal.live
            metrics.replayed_requests += journal.replayed
            metrics.usage[inst.institution_id] = journal.usage()
        held_path = inst_dir / WORK_DIR / HELD_FILE
        holds = [broken] if broken is not None else [h for st in states for h in st.holds]
        if holds:
            _atomic_write(held_path, canonical_json({"institution_id": inst.institution_id, "held": holds}))
            attrition.record(run_dir, institution_id=inst.institution_id, stage=STAGE, reason=HELD_REASON,
                             detail=", ".join(f"{h['page_id']}:{h['stage']}" for h in holds))
            metrics.held.append(inst.institution_id)
            continue
        products: list[PageProduct | ReviewedPage] = []
        next_source = 1
        uncarried: UncarriedCombinedValue | None = None
        for order, st in enumerate(states):
            try:
                if st.failure is not None:
                    products.append(failed_page(st.spec, st.failure))
                    continue
                products.append(produce_page(
                    run_dir=run_dir, run_id=inst.run_id, institution_uid=inst.institution_uid, spec=st.spec,
                    page_order=order, first_source=next_source, page_round=st.page_round,
                    activity_input=st.activity_input, activity_round=st.activity_round, pairs=st.pairs,
                    pair_support=st.pair_support, page_config=page_config, activity_config=activity_config,
                    instrument=instrument, uncertainty_flags=inst.upstream.uncertainty_flags))
            except UncarriedCombinedValue as exc:  # Y3 b: refused as a per-institution hold
                uncarried = exc
                break
            except STAGE_STOPS:
                raise
            except (ConsolidationError, ValueError, RuntimeError) as exc:  # this institution only
                broken = _producer_hold(st.spec.page.page_id, exc)
                break
            next_source += len(products[-1].sources)
        if uncarried is not None or broken is not None:
            hold = broken if broken is not None else {
                "page_id": uncarried.page_id, "stage": UNCARRIED_STAGE, "items": sorted(uncarried.values)}
            _atomic_write(held_path, canonical_json({"institution_id": inst.institution_id, "held": [hold]}))
            attrition.record(run_dir, institution_id=inst.institution_id, stage=STAGE, reason=HELD_REASON,
                             detail=f"{hold['page_id']}:{hold['stage']}")
            metrics.held.append(inst.institution_id)
            continue
        if held_path.exists():
            previous = json.loads(held_path.read_bytes().decode("utf-8")).get("held", [])
            attrition.record(run_dir, institution_id=inst.institution_id, stage=STAGE, reason=HELD_RELEASED,
                             detail=", ".join(f"{h['page_id']}:{h['stage']}" for h in previous))
            held_path.unlink()
        ready.append(_institution(inst, products))
        metrics.ready.append(inst.institution_id)
    return ready, metrics


def _producer_hold(page_id: str, exc: BaseException) -> dict[str, Any]:
    return {"page_id": page_id, "stage": PRODUCER_FAILED, "error": f"{type(exc).__name__}: {exc}"}


def _institution(inst: PerPageInstitution, products: Sequence[PageProduct | ReviewedPage]) -> Stage6Institution:
    pages, observations, records, within, quotes, provenance = [], [], [], [], [], []
    inputs: dict[str, ObservationInput] = {}
    sources: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, PageArtifact] = {}
    for p in products:
        if isinstance(p, ReviewedPage):
            pages.append(p)
            continue
        pages.append(p.page)
        observations += p.observations
        records += p.records
        within += p.within
        quotes += p.quotes
        provenance += p.provenance
        inputs.update(p.observation_inputs)
        sources.update(p.sources)
        artifacts.update(p.artifacts)
    up = inst.upstream
    return Stage6Institution(inst.run_id, inst.institution_uid, inst.institution, inst.country, pages,
                             observations, records, within, quotes, inputs, sources, artifacts, provenance,
                             independence_groups=up.independence_groups, merged_values=up.merged_values,
                             uncertainty_flags=up.uncertainty_flags)


__all__ = [
    "HELD_REASON", "HELD_RELEASED", "NO_ACTIVITY", "PRODUCER_FAILED", "STAGE_STOPS", "UNCARRIED_STAGE", "UncarriedCombinedValue", "InstitutionUpstream", "PageSpec", "PageUpstream", "PerPageInstitution", "PerPageMetrics",
    "PerPageProviders", "failed_page", "observation_id", "observation_supported", "produce_page",
    "run_perpage_v27", "source_id", "support_from_dict", "support_to_dict", "within_page_decision",
]
