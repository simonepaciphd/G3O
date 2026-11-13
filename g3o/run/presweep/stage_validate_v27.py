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
- **Values with no producer here** are explicit inputs and refuse when absent
  (:class:`~g3o.persist.stage6_adapters.MissingUpstreamError`): the merged
  values R1 asks to re-derive but whose signed rule needs inputs the merged
  row does not hold (:data:`MERGE_REFUSED_R1`; ``evidence_channel`` is the
  row metadata :data:`EVIDENCE_CHANNEL`, not a row value), the merged values
  no ruling covers (:data:`MERGE_UNRULED`, now empty). RC-D-032 B1 a keeps the
  R1 refusal until per-source producers exist.
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
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.classify.jev_activity_code import NOT_COVERED
from g3o.classify.permanent_pilot import PERMANENT_PILOT_RULE
from g3o.classify.questions.v27 import load_set
from g3o.common import attrition
from g3o.common.independence import independence_groups_for_sources
from g3o.common.instrument import canonical_json
from g3o.common.jev_client import JevAnswer, JevResult
from g3o.common.jev_record import CoderRecord
from g3o.common.paths import institution_dir
from g3o.common.source_fields import MissingUpstreamError as SourceFieldsMissingUpstreamError
from g3o.common.source_fields import aggregation_value, default_vocab
from g3o.common.storage import METADATA_ITEMS, table_fields
from g3o.common.storage_fields import FIELDS
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
    write_stage6_outputs,
)

STAGE = "validate"
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
#: X1 a R1 items whose signed rule reads inputs the merged row does not hold (refused, explicit input):
#: developer/developer_basis (the page's stated vendor or a product lookup), stage_as_of/_basis (the
#: source's supported publication date, the page's latest stated date, the access date), unit_credit
#: (no derivation rule text beyond the column's purpose), vendor_claim_only (the sources' type),
#: cx_display_rollup (supported positives with their support, source and observation ids; no item list),
#: date_upper_bound (the source date's origin). evidence_channel is row metadata, not a value.
MERGE_REFUSED_R1 = ("core.developer", "core.developer_basis", "core.stage_as_of", "core.stage_as_of_basis",
                    "core.unit_credit", "core.vendor_claim_only", "core.cx_display_rollup", "core.date_upper_bound")
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


if _non_pooled_items() != (MERGE_INPUT_ITEMS | set(MERGE_UNION) | set(MERGE_CREDIBLE)
                           | set(MERGE_DERIVED)):  # pragma: no cover
    raise RuntimeError("the merged-activity item split no longer matches the activities table")
INDEPENDENCE_PRODUCER = "near-duplicate / syndication grouping (P15) for source independence groups"


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
#: ``jev_incomplete``: a response with a request id that lacks the answer to a question it was
#: asked (RC-D-030 Z1 b, a pooled Stage 6 rule: the question is held and asked again on the next
#: run, never replayed). Only a journal built with ``retry_incomplete=True`` (Stage 6) writes it.
#: ``extract_rejected`` (per-page stage, C3 a): a recorded extractor response the caller could not
#: parse (:meth:`RequestJournal.reject_extract`); it cancels that ``extract`` entry, so the request
#: is asked again on the next run, and carries the response so its tokens are counted once.
EXTRACT_REJECTED = "extract_rejected"
ACCOUNTING_KINDS = frozenset({"jev_unidentified", "jev_incomplete", "extract_failed", "x35_failed",
                              EXTRACT_REJECTED})
#: Ruling 34 b / 41 a: after this many ``extract_rejected`` entries for one exact extractor request
#: key (``extract_failed`` entries do not count) the request is a permanent hold: the journal makes
#: no further live call for it (:class:`ExtractRejectCapReached`) until the PI releases it.
EXTRACT_REJECT_CAP = 3
#: Ruling 34 b / 41 a: a PI release applied to this journal (written by
#: :meth:`RequestJournal.record_release`); ``extract_rejected`` entries for the released keys that
#: come before it no longer count towards :data:`EXTRACT_REJECT_CAP`. Never replayed or accounted.
PI_RELEASED = "pi_released"


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
    """

    def __init__(self, path: Path, setup: Mapping[str, Any] | None = None, *,
                 retry_incomplete: bool = False) -> None:
        self.path = path
        self.setup = dict(setup or {})
        self.retry_incomplete = retry_incomplete
        self._recorded: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._accounting: list[dict[str, Any]] = []
        self._elapsed: list[int] = []
        self._seen: dict[tuple[str, str], int] = {}
        #: ruling 34 b / 41 a: request key -> ``extract_rejected`` entries since its last PI release
        self._rejections: dict[str, int] = {}
        self._releases: set[str] = set()  # file_sha256 of every PI release applied to this journal
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
            if entry["kind"] == PI_RELEASED:
                self._apply_release(entry["response"])
            elif entry["kind"] in ACCOUNTING_KINDS:
                self._accounting.append(entry)
                if entry["kind"] == EXTRACT_REJECTED:
                    self._recorded.pop(("extract", entry["key"], entry["n"]), None)
                    self._rejections[entry["key"]] = self._rejections.get(entry["key"], 0) + 1
            else:
                self._recorded[(entry["kind"], entry["key"], entry["n"])] = entry["response"]
        if not complete:  # unterminated or torn tail: repair before the next append
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with self.path.open("ab") as stream:
            stream.write(line.encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _append(self, slot: tuple[str, str, int], response: dict[str, Any], elapsed_ms: int) -> None:
        entry = {"kind": slot[0], "key": slot[1], "n": slot[2], "response": response, "elapsed_ms": elapsed_ms}
        self._write(entry)
        self._elapsed.append(elapsed_ms)
        if slot[0] in ACCOUNTING_KINDS:
            self._accounting.append(entry)
            if slot[0] == EXTRACT_REJECTED:
                self._recorded.pop(("extract", slot[1], slot[2]), None)
                self._rejections[slot[1]] = self._rejections.get(slot[1], 0) + 1
        else:
            self._recorded[slot] = response

    # --- ruling 34 b / 41 a: the rejection cap and its PI release ------------

    def _apply_release(self, release: Mapping[str, Any]) -> None:
        if release.get("all") is True:
            self._rejections.clear()
        else:
            for key in release["keys"]:
                self._rejections.pop(key, None)
        self._releases.add(release["file_sha256"])

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
        def wrapped(state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> JevResult:
            request = {"state": state, "questions": questions}
            slot = self._slot("jev", request)
            if slot in self._recorded:
                self.replayed += 1
                return _jev_from_json(self._recorded[slot])
            start = time.monotonic()
            result = ask_fn(state, questions)  # an exception is not recorded: asked again on resume
            self.live += 1
            if not (isinstance(result.request_id, str) and result.request_id.strip()):
                # billed but unidentified: a failed request (asked again), still accounted
                self._append(self._slot("jev_unidentified", request), _jev_to_json(result), _elapsed_ms(start))
            elif self.retry_incomplete and set(questions) - set(result.answers):
                # an asked answer is missing: that question is held and asked again next run (Z1 b)
                self._append(self._slot("jev_incomplete", request), _jev_to_json(result), _elapsed_ms(start))
            else:
                self._append(slot, _jev_to_json(result), _elapsed_ms(start))
            return result
        return wrapped

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

    def usage(self) -> dict[str, int]:
        """Totals of every journaled call (this and earlier, interrupted runs).

        ``input_tokens`` / ``output_tokens`` are jev tokens (complete, unidentified
        and incomplete responses); ``extractor_*`` are the quote step's extractor
        calls (successful, failed and rejected results); ``x35_calls`` / ``x35_failed``
        count X35 calls (their client reports no tokens here); ``request_ms`` is
        the summed call time. A quote step without seams is counted only as
        ``quote_responses``.
        """
        def recorded(kind: str) -> list[dict[str, Any]]:
            return [r for (k, _, _), r in self._recorded.items() if k == kind]

        def accounted(kind: str) -> list[dict[str, Any]]:
            return [e["response"] for e in self._accounting if e["kind"] == kind]

        jev, unidentified, incomplete = recorded("jev"), accounted("jev_unidentified"), accounted("jev_incomplete")
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
    """
    if inst.independence_groups is not None:
        return inst.independence_groups
    try:
        return independence_groups_for_sources(inst.sources, institution_id=inst.institution_id)
    except SourceFieldsMissingUpstreamError as exc:
        raise MissingUpstreamError(f"{INDEPENDENCE_PRODUCER}; {exc.producer}", exc.missing) from exc


def build_envelope(inst: Stage6Institution, result: Stage6Result, config: Stage6Config, instrument: dict[str, Any],
                   artifact_root: Path) -> tuple[Any, list[dict[str, Any]]]:
    """The storage envelope and provenance records of one ready Stage 6 result."""
    if not result.ready:
        raise ConsolidationError("Stage 6 result is not ready; nothing is published")
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
        if len(group) == 1:
            values = dict(fragments[0]["values"])
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
            values = {**given, **merge_values(inst, observation_pool_order(inst.quotes, pooled.observation_ids)),
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
    return metrics


__all__ = [
    "ENVELOPE_FAILED", "ENVELOPE_HOLDS", "EXECUTOR_FAILED", "MISSING_UPSTREAM", "HELD_REASON", "STAGE_STOPS", "HELD_RELEASED", "ObservationInput", "RequestJournal", "Stage6Institution",
    "MERGE_CREDIBLE", "MERGE_INPUT_ITEMS", "MERGE_REFUSED_R1", "MERGE_UNION", "MERGE_UNRULED",
    "Stage6Metrics", "build_envelope", "hold_reasons", "independence_groups_of", "merge_values", "run_stage6_v27",
]
