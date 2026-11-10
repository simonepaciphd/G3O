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
  requests are not repeated; failed requests are not recorded and are asked
  again. A torn final journal line (an interruption while writing) is dropped.
  An interruption inside a provider call cannot be exactly once.
- **Accounting.** Token counts of every recorded jev response are kept in the
  journal, so a partial (interrupted) run's usage is recoverable from disk.
- **Storage nodes.** Per-page supports come from the caller (the T-023/T-028
  per-page producers). Stage 6 answers get nodes from
  :func:`g3o.persist.stage6_adapters.combined_support_nodes` (pooled and
  relation answers name the stored input supports they were built from);
  rule-set values (gate closed, relation pre-filter, permanent_pilot
  override) get ``set_by_rule`` nodes with their mechanical coder records.
- **Values with no producer here** are explicit inputs and refuse when absent
  (:class:`~g3o.persist.stage6_adapters.MissingUpstreamError`): merged
  activities' non-pooled values (quote-step and derived items; no signed
  merge rule), source independence groups, and uncertainty flags.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.classify.jev_activity_code import NOT_COVERED
from g3o.classify.permanent_pilot import PERMANENT_PILOT_RULE
from g3o.common import attrition
from g3o.common.instrument import canonical_json
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import CoderRecord
from g3o.common.paths import institution_dir
from g3o.common.storage import table_fields
from g3o.common.support_check import (
    CodeEvidence,
    Entailment,
    PageSources,
    SupportResult,
    check_code,
)
from g3o.persist.stage6_adapters import (
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
)
from g3o.validate.consolidate_v27 import (
    ActivityObservation,
    ConsolidationError,
    RelationDecision,
    ReviewedPage,
    _positive,
    outcome_values,
    summary_values,
)
from g3o.validate.stage6_v27 import (
    AskFn,
    InputQuote,
    ObservationRecord,
    PooledActivity,
    QuoteFn,
    Stage6Config,
    Stage6Quote,
    Stage6QuoteRequest,
    Stage6Result,
    run_stage6,
    write_stage6_outputs,
)

STAGE = "validate"
WORK_DIR = "stage6_v27"
JOURNAL = "journal.jsonl"
HELD_FILE = "held.json"
HELD_REASON = "stage6_held"
EVIDENCE_CHANNEL = "web_extract"
ACTIVITY_ITEMS = frozenset(table_fields("activities"))

MERGED_VALUES_PRODUCER = ("merge rule for a merged activity's non-pooled values (quote-step and derived "
                          "items; no signed rule)")
INDEPENDENCE_PRODUCER = "near-duplicate / syndication grouping (P15) for source independence groups"
UNCERTAINTY_PRODUCER = "T-024 derived-field producer (core.uncertainty_flags for Stage 6 answers)"


# ---------------------------------------------------------------------------
# Durable request journal
# ---------------------------------------------------------------------------


def _jev_to_json(result: JevResult) -> dict[str, Any]:
    return {"answers": {k: asdict(v) for k, v in result.answers.items()}, "response_model": result.response_model,
            "request_id": result.request_id, "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens}


def _jev_from_json(doc: Mapping[str, Any]) -> JevResult:
    answers = {k: JevAnswer(**v) for k, v in doc["answers"].items()}
    return JevResult(answers, doc["response_model"], doc["request_id"], doc["input_tokens"], doc["output_tokens"])


def _quote_to_json(answer: Stage6Quote) -> dict[str, Any]:
    return {"quote": answer.quote, "input_support_id": answer.input_support_id,
            "entailment": None if answer.entailment is None else asdict(answer.entailment),
            "provenance": None if answer.provenance is None else dict(answer.provenance)}


def _quote_from_json(doc: Mapping[str, Any]) -> Stage6Quote:
    ent = doc["entailment"]
    return Stage6Quote(doc["quote"], doc["input_support_id"], None if ent is None else Entailment(**ent),
                       doc["provenance"])


class RequestJournal:
    """Append-only, fsynced record of Stage 6 provider responses for one institution."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._recorded: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._seen: dict[tuple[str, str], int] = {}
        self.live = 0
        self.replayed = 0
        if path.exists():
            lines = path.read_bytes().decode("utf-8").split("\n")
            for n, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    if n == len(lines) - 1:  # torn final line: the write was interrupted
                        break
                    raise ValueError(f"corrupt Stage 6 journal line {n + 1}: {path}") from None
                self._recorded[(entry["kind"], entry["key"], entry["n"])] = entry["response"]
            if lines and lines[-1].strip():  # drop a torn tail so the next append starts a clean line
                try:
                    json.loads(lines[-1])
                except json.JSONDecodeError:
                    path.write_bytes("\n".join(lines[:-1]).encode("utf-8") + (b"\n" if len(lines) > 1 else b""))

    def _slot(self, kind: str, request: Any) -> tuple[str, str, int]:
        key = hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()
        n = self._seen.get((kind, key), 0)
        self._seen[(kind, key)] = n + 1
        return kind, key, n

    def _append(self, slot: tuple[str, str, int], response: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"kind": slot[0], "key": slot[1], "n": slot[2], "response": response},
                          ensure_ascii=False, sort_keys=True)
        with self.path.open("ab") as stream:
            stream.write(line.encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._recorded[slot] = response

    def ask(self, ask_fn: AskFn) -> AskFn:
        def wrapped(state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> JevResult:
            slot = self._slot("jev", {"state": state, "questions": questions})
            if slot in self._recorded:
                self.replayed += 1
                return _jev_from_json(self._recorded[slot])
            result = ask_fn(state, questions)  # an exception is not recorded: asked again on resume
            self.live += 1
            if isinstance(result.request_id, str) and result.request_id.strip():
                self._append(slot, _jev_to_json(result))
            return result
        return wrapped

    def quote(self, quote_fn: QuoteFn | None) -> QuoteFn | None:
        if quote_fn is None:
            return None

        def wrapped(request: Stage6QuoteRequest) -> Stage6Quote:
            slot = self._slot("quote", asdict(request))
            if slot in self._recorded:
                self.replayed += 1
                return _quote_from_json(self._recorded[slot])
            answer = quote_fn(request)
            self.live += 1
            self._append(slot, _quote_to_json(answer))
            return answer
        return wrapped

    def usage(self) -> dict[str, int]:
        """Token totals of every recorded jev response (this and earlier, interrupted runs)."""
        jev = [r for (kind, _, _), r in self._recorded.items() if kind == "jev"]
        return {"jev_responses": len(jev), "quote_responses": len(self._recorded) - len(jev),
                "input_tokens": sum(r["input_tokens"] for r in jev),
                "output_tokens": sum(r["output_tokens"] for r in jev)}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservationInput:
    """One observation's per-page storage fragment (T-023 final values with T-028 nodes).

    ``row`` has ``values`` (every activities-table item except ``core.n_sources``
    and ``core.confidence``, which Stage 6 computes), ``item_support`` and
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
    uncertainty_flags: Callable[[SupportResult], Sequence[str] | None] | None = None

    @property
    def institution_id(self) -> str:
        return str(self.institution["institution_id"])


@dataclass
class Stage6Metrics:
    written: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
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


def _flags(inst: Stage6Institution, sr: SupportResult) -> Sequence[str] | None:
    return None if inst.uncertainty_flags is None else inst.uncertainty_flags(sr)


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
    answered = [r for r in pooled.records if r.coder_type == "classifier" and r.chosen_value != NOT_COVERED]
    if len(answered) != len(pooled.support):
        raise ConsolidationError("pooled answers and support checks do not pair one to one")
    for rec, sr in zip(answered, pooled.support, strict=True):
        nodes = combined_support_nodes(sr, run_id=inst.run_id, institution_uid=inst.institution_uid,
                                       chunk_id=rec.chunk_id, shown=shown(pooled.part_inputs[rec.chunk_id]),
                                       observation_id=None, uncertainty_flags=_flags(inst, sr),
                                       instrument=instrument)
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
                                       shown=shown(every), observation_id=None, uncertainty_flags=_flags(inst, sr),
                                       instrument=instrument)
        out.add(aid, nodes, rec, instrument)


def _relation_nodes(inst: Stage6Institution, result: Stage6Result, final_of: Mapping[str, str],
                    quotes: Mapping[str, InputQuote], instrument: dict[str, Any], out: _Nodes
                    ) -> dict[tuple[str, str], list[str]]:
    by_obs = {r.observation_id: r for r in inst.records}
    ids: dict[tuple[str, str], list[str]] = {}
    for outcome in result.relation_outcomes:
        if outcome.decision is None or not (outcome.lhs in final_of and outcome.rhs in final_of):
            continue
        rec, sr = outcome.records[0], outcome.support[0]
        candidates = [*by_obs[outcome.lhs].quotes, *by_obs[outcome.rhs].quotes]
        shown = [InputSupport(q.support_id, q.source_id, q.sources, inst.artifacts[q.source_id]) for q in candidates]
        quoted = sr.supporting_text is not None
        nodes = combined_support_nodes(sr, run_id=inst.run_id, institution_uid=inst.institution_uid,
                                       chunk_id=rec.chunk_id, shown=shown,
                                       observation_id=None if quoted else outcome.lhs,
                                       uncertainty_flags=_flags(inst, sr), instrument=instrument)
        inputs = nodes.original["input_support_ids"]
        home = quotes[inputs[0]].observation_id if inputs else outcome.lhs
        out.add(final_of[home], nodes, rec, instrument)
        ids[(outcome.lhs, outcome.rhs)] = [n["support_id"] for n in (nodes.original, nodes.final) if n is not None]
    return ids


def build_envelope(inst: Stage6Institution, result: Stage6Result, config: Stage6Config, instrument: dict[str, Any],
                   artifact_root: Path) -> tuple[Any, list[dict[str, Any]]]:
    """The storage envelope and provenance records of one ready Stage 6 result."""
    if not result.ready:
        raise ConsolidationError("Stage 6 result is not ready; nothing is published")
    pages = {p.page_id: p for p in inst.pages}
    obs = {o.observation_id: o for o in inst.observations}
    quotes = {q.support_id: q for q in inst.quotes}
    # Published activities: groups with at least one supported observation on a confirmed page
    # (the pooled-eligibility rule of T-026); other observations keep their relations only.
    published = [g for g in result.groups if any(obs[k].supported and _positive(pages[obs[k].page_id]) for k in g)]
    final_of = {oid: f"A{n + 1}" for n, g in enumerate(published) for oid in g}
    out = _Nodes()
    for group in published:
        if group in result.pooled:
            _pool_nodes(inst, final_of[group[0]], result.pooled[group], quotes, config, instrument, out)
    relation_ids = _relation_nodes(inst, result, final_of, quotes, instrument, out)

    sources: dict[str, dict[str, Any]] = {}
    for sid, row in inst.sources.items():
        finals = {final_of[o] for o in row["observation_ids"] if o in final_of}
        if len(finals) > 1:
            raise ConsolidationError(f"source claim {sid} spans several final activities")
        sources[sid] = {**dict(row), "activity_id": finals.pop() if finals else "_NA_"}
    activities: dict[str, dict[str, Any]] = {}
    for group in published:
        aid = final_of[group[0]]
        fragments = [inst.observation_inputs[k].row for k in group]
        if len(group) == 1:
            values = dict(fragments[0]["values"])
        else:
            if inst.merged_values is None or group not in inst.merged_values:
                raise MissingUpstreamError(MERGED_VALUES_PRODUCER, [aid])
            pooled_values = outcome_values(result.pooled[group].outcomes)
            # Pooled answers to items the activities table does not hold (the evaluation items,
            # stored per source claim in D-007) stay in the row's support/coder provenance only.
            values = {**inst.merged_values[group],
                      **{k: v for k, v in pooled_values.items() if k in ACTIVITY_ITEMS}}
        support: dict[str, dict[str, Any]] = {}
        for node in [*(s for f in fragments for s in f["item_support"]), *out.supports.get(aid, [])]:
            support.setdefault(node["support_id"], node)
        coders = [*(c for f in fragments for c in f["coder_records"]), *out.coders.get(aid, [])]
        claims = sorted(s for s, row in sources.items() if row["activity_id"] == aid)
        values["core.n_sources"] = len(claims)
        if inst.independence_groups is None:
            raise MissingUpstreamError(INDEPENDENCE_PRODUCER, claims)
        values["core.confidence"] = activity_confidence_value(
            claims, {s: sources[s]["values"]["core.confidence"] for s in claims}, inst.independence_groups)
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
    provenance: dict[str, dict[str, Any]] = {}
    for record in [*map(dict, inst.provenance), *out.provenance]:
        if provenance.setdefault(record["support_id"], record) != record:  # one node, one companion
            raise ConsolidationError(f"conflicting provenance for support {record['support_id']}")
    return envelope, list(provenance.values())


# ---------------------------------------------------------------------------
# Stage driver
# ---------------------------------------------------------------------------


def _done(inst_dir: Path) -> bool:
    paths = [inst_dir / n for n in (VALIDATE_ARTIFACT, STORAGE_ARTIFACT, PROVENANCE_ARTIFACT)]
    if not all(p.exists() for p in paths):
        return False
    load_support_provenance(paths[2], paths[1])  # bound to this storage file, or it refuses
    return True


def run_stage6_v27(run_dir: Path, institutions: Iterable[Stage6Institution], *, ask_fn: AskFn,
                   quote_fn: QuoteFn | None, config: Stage6Config, instrument: dict[str, Any],
                   now: Callable[[], datetime] | None = None) -> Stage6Metrics:
    """Run v2.7 Stage 6 for each institution; write artifacts for the ready ones only.

    Provider exceptions that stop the stage (``JevAccountError``,
    ``Stage6QuoteNotApproved``, budget stops) propagate; what was recorded
    before them is replayed by the next run.
    """
    if config.setup_pointer != instrument["instrument_id"]:
        raise ValueError("Stage 6 configuration is bound to a different instrument")
    clock = now or (lambda: datetime.now(timezone.utc))
    metrics = Stage6Metrics()
    for inst in institutions:
        inst_dir = institution_dir(run_dir, inst.institution_id)
        if _done(inst_dir):
            metrics.skipped.append(inst.institution_id)
            continue
        journal = RequestJournal(inst_dir / WORK_DIR / JOURNAL)
        try:
            result = run_stage6(institution=str(inst.institution["institution_name"]), country=inst.country,
                                pages=inst.pages, observations=inst.observations, records=inst.records,
                                within_page=inst.within_page, quotes=inst.quotes, ask_fn=journal.ask(ask_fn),
                                quote_fn=journal.quote(quote_fn), config=config)
        finally:
            metrics.live_requests += journal.live
            metrics.replayed_requests += journal.replayed
            metrics.usage[inst.institution_id] = journal.usage()
        held_path = inst_dir / WORK_DIR / HELD_FILE
        if not result.ready:
            holds = [asdict(h) for h in result.held]
            doc = {"institution_id": inst.institution_id, "held": holds,
                   "missing_pairs": [list(p) for p in result.missing_pairs],
                   "conflicting_groups": [list(g) for g in result.conflicting_groups]}
            held_path.parent.mkdir(parents=True, exist_ok=True)
            held_path.write_bytes(canonical_json(doc).encode("utf-8"))
            reasons = sorted({h["reason"] for h in holds} | ({"missing_relation_decision"} if result.missing_pairs
                                                              else set()))
            attrition.record(run_dir, institution_id=inst.institution_id, stage=STAGE, reason=HELD_REASON,
                             detail=", ".join(reasons) or "conflicting relation groups")
            metrics.held.append(inst.institution_id)
            continue
        envelope, provenance = build_envelope(inst, result, config, instrument, run_dir)
        metadata = {"institution_id": inst.institution_id, "n_input_pages": len(inst.pages),
                    "n_input_rows": len(inst.observations),
                    "response_timestamp": clock().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "model_label": config.configured_model, "notes": "v2.7 Stage 6 (T-026 executor)"}
        write_stage6_outputs(inst_dir, envelope=envelope, institution=inst.institution, metadata=metadata,
                             provenance=provenance)
        if held_path.exists():
            held_path.unlink()
        metrics.written.append(inst.institution_id)
    return metrics


__all__ = [
    "HELD_REASON", "ObservationInput", "RequestJournal", "Stage6Institution", "Stage6Metrics", "build_envelope",
    "run_stage6_v27",
]
