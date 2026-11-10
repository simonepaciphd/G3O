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
import time
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
from g3o.extract.anthropic_client import ExtractorResult
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
    write_atomic,
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
HELD_REASON = "stage6_held"  # attrition reason ``stage6_held:<hold reason>``, one record per hold reason
HELD_RELEASED = "stage6_held_released"  # appended when a held institution is later published
ENVELOPE_FAILED = "stage6_envelope_failed"  # the storage envelope / artifacts of one institution failed
ARTIFACTS_UNREADABLE = "stage6_artifacts_unreadable"  # existing Stage 6 artifacts fail to reload
MISSING_RELATION = "missing_relation_decision"
CONFLICTING_GROUPS = "conflicting_relation_groups"
POOLED_STOPPED = "pooled_question_stopped"  # combiner refused, or its gate item stopped
POOLED_PENDING = "pooled_question_pending"  # e.g. its gate item is pending
NOT_READY = "stage6_not_ready"  # defensive: not ready for no reason named above
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


#: Entry kinds replayed on resume (a completed provider answer).
REPLAYED_KINDS = frozenset({"jev", "quote", "extract", "x35"})
#: Entry kinds kept for accounting only: billed or attempted calls that did not complete.
#: They are never replayed; the request is asked again (a failed request, PI 2026-11-08 2.17).
ACCOUNTING_KINDS = frozenset({"jev_unidentified", "extract_failed", "x35_failed"})


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
    """

    def __init__(self, path: Path, setup: Mapping[str, Any] | None = None) -> None:
        self.path = path
        self.setup = dict(setup or {})
        self._recorded: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._accounting: list[dict[str, Any]] = []
        self._elapsed: list[int] = []
        self._seen: dict[tuple[str, str], int] = {}
        self.live = 0
        self.replayed = 0
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
                if last:  # torn final record: the write was interrupted; drop it
                    break
                raise ValueError(f"corrupt Stage 6 journal line {n + 1}: {self.path}") from None
            keep.append(line)
            self._elapsed.append(int(entry.get("elapsed_ms", 0)))
            if entry["kind"] in ACCOUNTING_KINDS:
                self._accounting.append(entry)
            else:
                self._recorded[(entry["kind"], entry["key"], entry["n"])] = entry["response"]
        if not complete:  # unterminated or torn tail: repair before the next append
            write_atomic(self.path, b"".join(line + b"\n" for line in keep))

    def _slot(self, kind: str, request: Any, extra: Mapping[str, Any] | None = None) -> tuple[str, str, int]:
        doc = {"setup": {**self.setup, **(extra or {})}, "request": request}
        key = hashlib.sha256(canonical_json(doc).encode("utf-8")).hexdigest()
        n = self._seen.get((kind, key), 0)
        self._seen[(kind, key)] = n + 1
        return kind, key, n

    def _append(self, slot: tuple[str, str, int], response: dict[str, Any], elapsed_ms: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"kind": slot[0], "key": slot[1], "n": slot[2], "response": response, "elapsed_ms": elapsed_ms}
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with self.path.open("ab") as stream:
            stream.write(line.encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._elapsed.append(elapsed_ms)
        if slot[0] in ACCOUNTING_KINDS:
            self._accounting.append(entry)
        else:
            self._recorded[slot] = response

    def ask(self, ask_fn: AskFn) -> AskFn:
        def wrapped(state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> JevResult:
            request = {"state": state, "questions": questions}
            slot = self._slot("jev", request)
            if slot in self._recorded:
                self.replayed += 1
                return _jev_from_json(self._recorded[slot])
            start = time.monotonic()
            result = ask_fn(state, questions)  # an exception is not recorded: asked again on resume
            self.live += 1
            if isinstance(result.request_id, str) and result.request_id.strip():
                self._append(slot, _jev_to_json(result), _elapsed_ms(start))
            else:  # billed but unidentified: a failed request (asked again), still accounted
                self._append(self._slot("jev_unidentified", request), _jev_to_json(result), _elapsed_ms(start))
            return result
        return wrapped

    def _extract(self, extract_fn: Any, prompt: Mapping[str, Any]) -> Any:
        def wrapped(job: Any) -> ExtractorResult:
            request = {"custom_id": job.custom_id, "params": job.params}
            slot = self._slot("extract", request, prompt)
            if slot in self._recorded:
                self.replayed += 1
                return ExtractorResult(**self._recorded[slot])
            start = time.monotonic()
            result = extract_fn(job)  # an exception is not recorded: asked again on resume
            self.live += 1
            if result.success:
                self._append(slot, asdict(result), _elapsed_ms(start))
            else:
                self._append(self._slot("extract_failed", request, prompt), asdict(result), _elapsed_ms(start))
            return result
        return wrapped

    def _entail(self, entail_fn: Any, prompt: Mapping[str, Any]) -> Any:
        def wrapped(question: str, text: str) -> Entailment:
            request = {"question": question, "text": text}
            slot = self._slot("x35", request, prompt)
            if slot in self._recorded:
                self.replayed += 1
                return Entailment(**self._recorded[slot])
            start = time.monotonic()
            try:
                answer = entail_fn(question, text)
            except Exception as exc:
                self._append(self._slot("x35_failed", request, prompt), {"error": f"{type(exc).__name__}: {exc}"},
                             _elapsed_ms(start))
                raise
            self.live += 1
            self._append(slot, asdict(answer), _elapsed_ms(start))
            return answer
        return wrapped

    def quote(self, quote_fn: QuoteFn | None) -> QuoteFn | None:
        if quote_fn is None:
            return None
        prompt = {"quote_prompt_version": getattr(quote_fn, "prompt_version", None)}
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

    def usage(self) -> dict[str, int]:
        """Totals of every journaled call (this and earlier, interrupted runs).

        ``input_tokens`` / ``output_tokens`` are jev tokens (identified and
        unidentified responses); ``extractor_*`` are the quote step's extractor
        calls (successful and failed results); ``x35_calls`` / ``x35_failed``
        count X35 calls (their client reports no tokens here); ``request_ms`` is
        the summed call time. A quote step without seams is counted only as
        ``quote_responses``.
        """
        def recorded(kind: str) -> list[dict[str, Any]]:
            return [r for (k, _, _), r in self._recorded.items() if k == kind]

        def accounted(kind: str) -> list[dict[str, Any]]:
            return [e["response"] for e in self._accounting if e["kind"] == kind]

        jev, unidentified = recorded("jev"), accounted("jev_unidentified")
        extract = [*recorded("extract"), *accounted("extract_failed")]
        return {"jev_responses": len(jev), "jev_unidentified": len(unidentified),
                "quote_responses": len(recorded("quote")),
                "input_tokens": sum(r["input_tokens"] for r in (*jev, *unidentified)),
                "output_tokens": sum(r["output_tokens"] for r in (*jev, *unidentified)),
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
    if len(pooled.support_inputs) != len(pooled.support):
        raise ConsolidationError("pooled support checks lack the quote step's copied inputs")
    for rec, sr, copied in zip(answered, pooled.support, pooled.support_inputs, strict=True):
        nodes = combined_support_nodes(sr, run_id=inst.run_id, institution_uid=inst.institution_uid,
                                       chunk_id=rec.chunk_id, shown=shown(pooled.part_inputs[rec.chunk_id]),
                                       observation_id=None, uncertainty_flags=_flags(inst, sr),
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
        copied = outcome.support_inputs[0] if outcome.support_inputs else None
        candidates = [*by_obs[outcome.lhs].quotes, *by_obs[outcome.rhs].quotes]
        shown = [InputSupport(q.support_id, q.source_id, q.sources, inst.artifacts[q.source_id]) for q in candidates]
        quoted = sr.supporting_text is not None
        nodes = combined_support_nodes(sr, run_id=inst.run_id, institution_uid=inst.institution_uid,
                                       chunk_id=rec.chunk_id, shown=shown,
                                       observation_id=None if quoted else outcome.lhs,
                                       uncertainty_flags=_flags(inst, sr), instrument=instrument,
                                       input_support_id=copied)
        # The node lives with the record whose quote was copied (the quote step's own answer).
        inputs = nodes.original["input_support_ids"]
        home = quotes[copied].observation_id if copied is not None and inputs == [copied] else outcome.lhs
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
        code = reason if reason in (ENVELOPE_FAILED, ARTIFACTS_UNREADABLE) else f"{HELD_REASON}:{reason}"
        attrition.record(run_dir, institution_id=institution_id, stage=STAGE, reason=code,
                         detail=(detail or {}).get(reason))


def run_stage6_v27(run_dir: Path, institutions: Iterable[Stage6Institution], *, ask_fn: AskFn,
                   quote_fn: QuoteFn | None, config: Stage6Config, instrument: dict[str, Any],
                   now: Callable[[], datetime] | None = None) -> Stage6Metrics:
    """Run v2.7 Stage 6 for each institution; write artifacts for the ready ones only.

    Provider exceptions that stop the stage (``JevAccountError``,
    ``Stage6QuoteNotApproved``, budget stops) propagate; what was recorded
    before them is replayed by the next run. An error building or writing one
    institution's artifacts, or existing artifacts that fail to reload, is
    recorded for that institution (``held.json``, attrition, ``metrics.failed``)
    and the stage continues with the next one.
    """
    if config.setup_pointer != instrument["instrument_id"]:
        raise ValueError("Stage 6 configuration is bound to a different instrument")
    clock = now or (lambda: datetime.now(timezone.utc))
    metrics = Stage6Metrics()
    setup = {"setup_pointer": config.setup_pointer, "configured_model": config.configured_model,
             "coder_version": config.coder_version}
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
        journal = RequestJournal(inst_dir / WORK_DIR / JOURNAL, setup)
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
        except Exception as exc:  # noqa: BLE001 - one institution's envelope error stops that institution only
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
    return metrics


__all__ = [
    "ENVELOPE_FAILED", "HELD_REASON", "HELD_RELEASED", "ObservationInput", "RequestJournal", "Stage6Institution",
    "Stage6Metrics", "build_envelope", "hold_reasons", "run_stage6_v27",
]
