"""Per-run extractor batch modes of the v2.7 per-page stage (PI rulings 134, 143 a; priced per 130 a).

Three modes (:data:`EXTRACTOR_MODES`), chosen per run; the default is :data:`MIX` (134 default):

- :data:`ALL_BATCH`: every extractor call of the per-page stage goes through the Anthropic
  Message Batches API, in waves;
- :data:`MIX`: the first-round T-022 pass-1 and T-032 pass-2 page requests (their ``custom_id``
  is the page's first-round one, :func:`is_first_round`) go through Batches; every follow-up
  (extra rounds, the 87 c activity-only request, pass-2 extra rounds) is live;
- :data:`NO_BATCH`: every call is live (the code before this module).

A PI-released re-ask (rulings 104 b / 113 b / 114 b) is always live, whatever the mode: its
``reask_spent`` marker is journaled just before the call, so it cannot wait for a batch.
The Stage 6 quote step is not part of the per-page stage and stays live.

How a batched call runs (no stage logic changes). The per-page stage is run in *waves*
(:func:`run_waves`). In a wave, a batchable request with no stored result is *deferred*: it is
queued (a ``queued`` line in the run's batch journal, fsynced) and :class:`BatchDeferred` is raised
instead of a call, which holds that institution (:data:`BATCH_PENDING`) exactly like any other
pending hold; the stage goes on with the next institution. After the wave the queued requests are
submitted as one or more batches, polled until they end, and their results stored. The next wave
resumes every held institution from its checkpoints; the request journal
(:class:`~g3o.run.presweep.stage_validate_v27.RequestJournal`) takes the stored result in place of
a live call and journals it exactly as it journals a live response (``extract`` /
``extract_failed``), with the result's ``batch_id``, so it is replayed on every later resume and
priced at batch rates (130 a). The waves end when a wave queues nothing, or after
:data:`DEFAULT_MAX_WAVES` waves (the institutions still waiting stay held and resume on the next run).
A deferred page does not stop the other pages of its institution in that wave. A request over the
per-request byte guard is never batched: it is sent live (:func:`too_big_for_batch`).

Bounded chunks. The requests queued in a wave are not all held until its end: once the requests held in
memory reach :data:`DEFAULT_CHUNK_MAX_BYTES` or :data:`DEFAULT_CHUNK_MAX_REQUESTS` (constructor
``chunk_max_bytes`` / ``chunk_max_requests``), they are submitted as a batch mid-wave, journaled exactly
as at the end of a wave, and their bodies are dropped from memory once the ``submit_intent`` is written
(this process never sends them again). The end of the wave submits the remainder. Both budgets stay well
below the Message Batches limits (:data:`~g3o.extract.anthropic_client.BATCH_MAX_REQUESTS`,
:data:`~g3o.extract.anthropic_client.BATCH_MAX_BYTES`). A mid-wave submission that fails is not raised
into the stage (the stage would take it for an extractor failure): the rest of the wave journals its
requests as queued without holding their bodies or submitting anything, and :func:`run_waves` raises the
failure after the stage pass, where an end-of-wave failure is raised; an unacknowledged intent then stops
the next run (:class:`BatchSubmitUnacknowledged`), as before.

Durability (a crash at any point neither double-spends nor loses a result). The run-level batch
journal ``<run>/perpage_v27_batches/batches.jsonl`` is append-only and fsynced:

1. ``queued`` (request hash, ``custom_id``): written when a request is deferred. A resumed page whose
   pass-1 / pass-2 request was recorded (PI rulings 98 b / 105 b) but never sent is therefore known
   not sent, and is deferred again rather than held as not journaled.
2. ``submit_intent`` (sequence number, every ``[custom_id, request hash]``): written BEFORE the batch
   is created. ``submitted`` (sequence number, ``batch_id``): written right after. A crash between the
   two leaves an intent with no batch id: the batch may exist and be billed, so nothing is ever
   resubmitted automatically; the next run stops (:class:`BatchSubmitUnacknowledged`) until the
   operator records the outcome (:func:`record_submit_outcome`: the batch id found in the console,
   or that none was created).
3. ``result`` (``batch_id``, ``custom_id``, request hash, the result): one fsynced line per result,
   read from the ended batch. The result keeps its request id, ``batch:<batch_id>/<message_id>`` (PI ruling
   Q178 a; :func:`~g3o.extract.anthropic_client.batch_request_id`), which the request journal journals and
   replays like a live one, so a batched page's quote-step records carry it (D-007). ``collected`` (``batch_id``): after the last one, only once every
   request submitted in that batch has a result (:class:`BatchResultsIncomplete` otherwise). A crash mid-poll
   polls the same batch id again; a crash mid-collection reads the results again (free) and stores
   only those not stored yet. A batch that will never return the missing results is ended by the operator
   (PI ruling Q175 a, :func:`record_batch_abandoned`, never called automatically): an ``abandoned`` line
   counts as ``collected``; its submitted requests with no stored result go back to ``queued`` and are asked
   (and paid) again on the next run; the results already stored stay.
4. A stored result is consumed when the request journal journals it (its ``batch_id`` on the
   entry): a crash before that leaves the result in the store for the next wave; after it, the
   per-institution journal replays it. A result already consumed is never journaled twice
   (the journal checks the ``batch_id`` of its own entries).

Errored, expired and canceled results are stored and journaled like any failed response
(``extract_failed``; priced $0 when they report no usage, 67 a); the institution is held (C3 a) and
the request is not resubmitted in the same run (:func:`run_waves` sends each request at most once
per invocation); the next run asks it again, as for a failed live call.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

ALL_BATCH = "all_batch"
MIX = "mix"
NO_BATCH = "no_batch"
#: PI ruling 134: the per-run extractor modes (all batch, mix, no batch)
EXTRACTOR_MODES = (ALL_BATCH, MIX, NO_BATCH)
#: PI ruling 134 (default): mix, "for best tradeoff"
DEFAULT_EXTRACTOR_MODE = MIX

BATCH_DIR = "perpage_v27_batches"
BATCH_JOURNAL = "batches.jsonl"
#: the hold stage of an institution whose extractor request waits for a batch
BATCH_PENDING = "extract_batch_pending"
#: seconds between two status polls of a batch in flight (procedural default)
DEFAULT_POLL_SECONDS = 60.0
#: waves of one invocation before :func:`run_waves` stops (procedural default; each wave sends a
#: request at most once, so a run needs one wave per sequential batched step of a page, plus one)
DEFAULT_MAX_WAVES = 50
#: mid-wave chunk budget: queued request bytes (serialized ``params``, as ``split_for_batches`` counts
#: them) held in memory before they are submitted as one batch. Procedural default, well below the
#: Message Batches limit of 256 MB per batch (``BATCH_MAX_BYTES`` keeps 200 MB; Anthropic docs:
#: https://docs.claude.com/en/docs/build-with-claude/batch-processing): a wave of ~81,000 ~60 KB page
#: requests becomes ~75 batches of ~1,100 requests instead of one batch held whole in memory.
DEFAULT_CHUNK_MAX_BYTES = 64 * 1024 * 1024
#: mid-wave chunk budget: queued requests per batch (procedural default, well below the 100,000
#: requests per batch of the same docs, ``BATCH_MAX_REQUESTS``)
DEFAULT_CHUNK_MAX_REQUESTS = 10_000

#: first-round custom ids: the T-022 pass-1 page request (``x27-`` + 48 hex) and the T-032
#: pass-2 page request (``x27s-`` + 48 hex); follow-ups carry a ``-x`` / ``-a`` suffix (46 a, 49 a, 87 c)
_FIRST_ROUND = re.compile(r"^x27s?-[0-9a-f]{48}$")


def too_big_for_batch(job: Any) -> bool:
    """Whether ``job`` is over the per-request byte guard of ``split_for_batches`` (it is sent live instead)."""
    from g3o.extract.anthropic_client import split_for_batches

    return bool(split_for_batches([job])[1])


def is_first_round(custom_id: str) -> bool:
    """Whether ``custom_id`` is a page's first-round pass-1 or pass-2 page request (mix batches these)."""
    return bool(_FIRST_ROUND.match(custom_id))


def require_mode(mode: Any) -> str:
    if mode not in EXTRACTOR_MODES:
        raise ValueError(f"extractor mode must be one of {EXTRACTOR_MODES} (PI ruling 134), got {mode!r}")
    return mode


def request_hash(job: Any) -> str:
    """SHA256 of the request (``custom_id`` and ``params``): what a stored result answers."""
    doc = json.dumps({"custom_id": job.custom_id, "params": job.params}, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(doc.encode("utf-8")).hexdigest()


class BatchDeferred(Exception):  # noqa: N818 - names the hold, as Pass2RequestNotJournaled does
    """The request waits for a batch (queued now, in flight, or to be sent on the next run).

    Raised by :class:`BatchExtractor` instead of a call. Not a stage stop: the per-page stage holds the
    institution (:data:`BATCH_PENDING`) and goes on; the next wave (or run) resumes it."""

    def __init__(self, custom_id: str, key: str, state: str) -> None:
        super().__init__(f"extractor request {custom_id!r} waits for a Message Batch ({state})")
        self.custom_id, self.key, self.state = custom_id, key, state


class BatchSubmitUnacknowledged(RuntimeError):
    """A ``submit_intent`` has no ``submitted`` line: the batch may exist and be billed.

    A stage stop. Nothing is resubmitted until the operator records the outcome with
    :func:`record_submit_outcome` (the batch id, or None when no batch was created)."""

    def __init__(self, seq: int, custom_ids: list[str]) -> None:
        super().__init__(f"Message Batch submission #{seq} ({len(custom_ids)} request(s)) was not acknowledged: "
                         "it may have been created and billed. Find it in the Anthropic console and record it "
                         "with record_submit_outcome(run_dir, seq, batch_id) (batch_id None if none was "
                         "created); nothing is resubmitted until then")
        self.seq, self.custom_ids = seq, custom_ids


class BatchResultsIncomplete(RuntimeError):
    """An ended batch returned no result for some submitted request. A stage stop: the batch is not marked
    collected (the results stored are kept), so the next run reads its results again (free); nothing is
    resubmitted until the operator abandons the batch (:func:`record_batch_abandoned`, PI ruling Q175 a)."""

    def __init__(self, batch_id: str, custom_ids: list[str]) -> None:
        super().__init__(f"Message Batch {batch_id} ended without a result for {len(custom_ids)} submitted "
                         f"request(s) (first: {custom_ids[:3]}); not marked collected, read again on the next run. "
                         "If the batch will never return them, the operator records it with "
                         f"record_batch_abandoned(run_dir, {batch_id!r}): the missing requests are queued and "
                         "asked (and paid) again on the next run; the results stored are kept")
        self.batch_id, self.custom_ids = batch_id, custom_ids


class BatchClientMissing(RuntimeError):
    """A batched mode, or batches in flight, with no batch client to submit or poll them."""


def _write_line(path: Path, entry: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with path.open("ab") as stream:
        stream.write(line.encode("utf-8") + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def batch_journal_path(run_dir: Path) -> Path:
    return Path(run_dir) / BATCH_DIR / BATCH_JOURNAL


def record_submit_outcome(run_dir: Path, seq: int, batch_id: str | None) -> None:
    """Operator step after :class:`BatchSubmitUnacknowledged`: the batch of submission ``seq`` is
    ``batch_id`` (then it is polled and collected), or None: no batch was created (its requests are
    sent again on the next wave)."""
    _Store.load(batch_journal_path(run_dir))  # drops a torn tail first, so this line is never merged into it
    _write_line(batch_journal_path(run_dir), {"kind": "submitted", "seq": seq, "batch_id": batch_id,
                                              "operator": True})


def record_batch_abandoned(run_dir: Path, batch_id: str) -> list[str]:
    """Operator step after :class:`BatchResultsIncomplete` (PI ruling Q175 a; explicit, never called by the
    stage): batch ``batch_id`` is abandoned. It counts as collected (never polled or read again); its
    submitted requests with no stored result go back to ``queued`` and are asked again on the next run (a
    second charge only if Anthropic billed the lost ones); the results already stored stay. Returns the
    custom ids queued again. Refuses a batch the journal does not hold as submitted, or one already
    collected or abandoned."""
    path = batch_journal_path(run_dir)
    store = _Store.load(path)  # drops a torn tail first, so this line is never merged into it
    seq = store._seq_of_batch.get(batch_id)
    if seq is None:
        raise ValueError(f"batch {batch_id!r} is not a submitted batch of this run's batch journal: {path}")
    if batch_id in store.collected:
        raise ValueError(f"batch {batch_id!r} is already collected or abandoned; nothing to abandon")
    if batch_id not in store.incomplete:
        raise ValueError(f"batch {batch_id!r} has not ended with a short results stream (no BatchResultsIncomplete "
                         "recorded): a batch still running is never abandoned. Run only with no run in progress.")
    missing = store.missing_results(batch_id)
    _write_line(path, {"kind": "abandoned", "batch_id": batch_id, "operator": True})
    return [cid for cid, _key in missing]


@dataclass
class _Store:
    """The batch journal, loaded. A torn last line (an interrupted write) is dropped."""

    path: Path
    queued: dict[str, str] = field(default_factory=dict)  # request hash -> custom_id (not yet submitted)
    intents: dict[int, list[list[str]]] = field(default_factory=dict)  # seq -> [[custom_id, hash], ...]
    submitted: dict[int, str | None] = field(default_factory=dict)  # seq -> batch id (None: none created)
    collected: set[str] = field(default_factory=set)  # collected or abandoned (PI ruling Q175 a)
    abandoned: set[str] = field(default_factory=set)  # batch ids the operator abandoned (PI ruling Q175 a)
    #: batch ids that ENDED with a short results stream (:class:`BatchResultsIncomplete` was raised); only
    #: these may be abandoned, so a batch still running is never abandoned and paid again (review of 9e0d824, M)
    incomplete: set[str] = field(default_factory=set)
    #: request hash -> stored results, in collection order (each with its ``batch_id``)
    results: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _seen_results: set[tuple[str, str]] = field(default_factory=set)  # (batch_id, custom_id)
    #: keys of every unacknowledged or in-flight submission, kept up to date by :meth:`apply` (review of
    #: c9f2356, M: rebuilding it on every call was quadratic in the wave once chunks go out mid-wave)
    _flying: set[str] = field(default_factory=set)
    _seq_of_batch: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> _Store:
        store = cls(path)
        if not path.exists():
            return store
        raw = path.read_bytes()
        lines = raw.split(b"\n")
        keep: list[bytes] = []
        for n, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                if n == len(lines) - 1:
                    break  # torn final record: dropped (never acknowledged, so never relied on)
                raise ValueError(f"corrupt batch journal line {n + 1}: {path}") from None
            keep.append(line)
            store.apply(entry)
        if raw and not raw.endswith(b"\n"):
            # unterminated or torn tail: the file is rewritten without it (atomically, as
            # RequestJournal._load does) before the next append, so it never ends up mid-file
            from g3o.persist.stage6_adapters import write_atomic

            write_atomic(path, b"".join(line + b"\n" for line in keep))
        return store

    def apply(self, entry: Mapping[str, Any]) -> None:
        kind = entry["kind"]
        if kind == "queued":
            self.queued[entry["key"]] = entry["custom_id"]
        elif kind == "submit_intent":
            self.intents[entry["seq"]] = [list(p) for p in entry["requests"]]
            for _cid, key in entry["requests"]:
                self.queued.pop(key, None)
                self._flying.add(key)
        elif kind == "submitted":
            self.submitted[entry["seq"]] = entry["batch_id"]
            if entry["batch_id"] is None:  # none created: its requests may be queued again
                for cid, key in self.intents.get(entry["seq"], []):
                    self.queued.setdefault(key, cid)
                    self._flying.discard(key)
            else:
                self._seq_of_batch[entry["batch_id"]] = entry["seq"]
                if entry["batch_id"] in self.abandoned:  # never in journal order; kept consistent anyway
                    self._requeue_missing(entry["batch_id"])
                if entry["batch_id"] in self.collected:
                    self._land(entry["batch_id"])
        elif kind == "result":
            pair = (entry["batch_id"], entry["custom_id"])
            if pair not in self._seen_results:
                self._seen_results.add(pair)
                self.results.setdefault(entry["key"], []).append(entry["result"])
        elif kind == "collected":
            self.collected.add(entry["batch_id"])
            self._land(entry["batch_id"])
        elif kind == "incomplete":
            self.incomplete.add(entry["batch_id"])
        elif kind == "abandoned":  # PI ruling Q175 a: counts as collected; the missing requests queue again
            self.abandoned.add(entry["batch_id"])
            self.collected.add(entry["batch_id"])
            self._requeue_missing(entry["batch_id"])
            self._land(entry["batch_id"])

    def missing_results(self, batch_id: str) -> list[tuple[str, str]]:
        """``(custom_id, key)`` of every request submitted in ``batch_id`` with no stored result from it."""
        seq = self._seq_of_batch.get(batch_id)
        if seq is None:
            return []
        return [(cid, key) for cid, key in self.intents.get(seq, [])
                if not self.has_result(key, batch_id, cid)]

    def _requeue_missing(self, batch_id: str) -> None:
        """An abandoned batch's requests with no stored result are queued again (asked on the next run)."""
        for cid, key in self.missing_results(batch_id):
            self.queued.setdefault(key, cid)

    def _land(self, batch_id: str) -> None:
        """A collected batch's requests are no longer in flight."""
        seq = self._seq_of_batch.get(batch_id)
        if seq is not None:
            for _cid, key in self.intents.get(seq, []):
                self._flying.discard(key)

    def append(self, entry: Mapping[str, Any]) -> None:
        _write_line(self.path, entry)
        self.apply(entry)

    def unacknowledged(self) -> list[int]:
        return sorted(seq for seq in self.intents if seq not in self.submitted)

    def in_flight(self) -> list[tuple[int, str]]:
        return sorted((seq, bid) for seq, bid in self.submitted.items() if bid is not None
                      and bid not in self.collected)

    def in_flight_keys(self) -> set[str]:
        """Keys of every unacknowledged or in-flight (submitted, not collected) submission, kept by
        :meth:`apply` (O(1) per call); :meth:`in_flight_keys_rebuilt` is the definition it must equal."""
        return self._flying

    def in_flight_keys_rebuilt(self) -> set[str]:
        flying = {seq for seq, _ in self.in_flight()} | set(self.unacknowledged())
        return {key for seq in flying for _cid, key in self.intents.get(seq, [])}

    def has_result(self, key: str, batch_id: str, custom_id: str) -> bool:
        return (batch_id, custom_id) in self._seen_results


class BatchExtractor:
    """The per-page stage's ``extract_fn`` in a batch mode; journaled by the request journal.

    ``live_fn(job) -> ExtractorResult`` is the live extractor call (follow-ups in :data:`MIX`, every
    call in :data:`NO_BATCH`, a PI-released re-ask in every mode: :meth:`live_call`).
    ``batch_client`` has ``submit_batch(jobs) -> batch_id``, ``batch_status(batch_id) -> str`` and
    ``batch_results(batch_id) -> Iterable[ExtractorResult]``
    (:class:`~g3o.extract.anthropic_client.AnthropicExtractorClient`)."""

    def __init__(self, run_dir: Path, live_fn: Callable[[Any], Any], batch_client: Any, mode: str = MIX, *,
                 poll_seconds: float = DEFAULT_POLL_SECONDS, sleep: Callable[[float], None] = time.sleep,
                 chunk_max_bytes: int = DEFAULT_CHUNK_MAX_BYTES,
                 chunk_max_requests: int = DEFAULT_CHUNK_MAX_REQUESTS) -> None:
        from g3o.extract.anthropic_client import (
            BATCH_MAX_BYTES,
            BATCH_MAX_REQUESTS,
            DEFAULT_MAX_REQUEST_BYTES,
        )

        self.mode = require_mode(mode)
        if mode != NO_BATCH and batch_client is None:
            raise BatchClientMissing(f"extractor mode {mode!r} needs a batch client (submit, poll, results)")
        if not DEFAULT_MAX_REQUEST_BYTES <= chunk_max_bytes <= BATCH_MAX_BYTES:
            raise ValueError(f"chunk_max_bytes must lie between the per-request guard ({DEFAULT_MAX_REQUEST_BYTES})"
                             f" and the per-batch limit ({BATCH_MAX_BYTES}), got {chunk_max_bytes}")
        if not 1 <= chunk_max_requests <= BATCH_MAX_REQUESTS:
            raise ValueError(f"chunk_max_requests must lie between 1 and {BATCH_MAX_REQUESTS}, "
                             f"got {chunk_max_requests}")
        self.run_dir, self.live_fn, self.batch_client = Path(run_dir), live_fn, batch_client
        self.poll_seconds, self.sleep = poll_seconds, sleep
        self.chunk_max_bytes, self.chunk_max_requests = chunk_max_bytes, chunk_max_requests
        self.store = _Store.load(batch_journal_path(run_dir))
        self._jobs: dict[str, Any] = {}  # request hash -> job held for the next chunk (params kept in memory)
        self._jobs_bytes = 0  # serialized params bytes held in ``_jobs`` (the chunk budget)
        self._wave_cids: dict[str, str] = {}  # custom_id -> request hash queued this wave (no bodies)
        self._sent: set[str] = set()  # request hashes submitted by this process (once per invocation)
        self._mid_wave_batches = 0  # batches submitted mid-wave since the last end-of-wave submit()
        self._submit_error: Exception | None = None  # a failed mid-wave submission, raised by run_waves
        self.batches_submitted = 0
        self.results_collected = 0

    # --- the extract_fn seam --------------------------------------------------

    def batchable(self, job: Any) -> bool:
        if self.mode == ALL_BATCH:
            return True
        return self.mode == MIX and is_first_round(job.custom_id)

    def stored_batch_results(self, job: Any) -> list[Any]:
        """Every stored result for ``job`` (an :class:`ExtractorResult` with its ``batch_id``), oldest first;
        the request journal takes the first it has not journaled yet."""
        from g3o.extract.anthropic_client import ExtractorResult

        return [ExtractorResult(**r) for r in self.store.results.get(request_hash(job), [])]

    def batch_owns(self, job: Any) -> bool:
        """Whether ``job`` waits for a batch and was never sent live: queued or in flight. The PI ruling
        98 b / 105 b guards accept it. A stored result counts only while the request journal has not
        journaled it, which the journal checks itself (its ``peek``): a result already consumed never
        lets the request go live a second time."""
        key = request_hash(job)
        return key in self.store.queued or key in self.store.in_flight_keys()

    def __call__(self, job: Any) -> Any:
        """Called by the request journal only when it holds no unconsumed stored result for ``job``."""
        key = request_hash(job)
        if key in self.store.in_flight_keys():
            raise BatchDeferred(job.custom_id, key, "in flight")
        if not self.batchable(job) or too_big_for_batch(job):
            # a request over the per-request byte guard is never cut: it is sent live, as before. It is
            # never queued, so the 98 b / 105 b guards treat it as any live call.
            return self.live_fn(job)
        if key in self._sent:  # sent once by this invocation and answered: asked again on the next run
            raise BatchDeferred(job.custom_id, key, "sent this run; asked again on the next run")
        clash = self._wave_cids.get(job.custom_id)
        if clash is not None and clash != key:  # one custom_id per wave: the second request waits for the next
            raise BatchDeferred(job.custom_id, key, "custom_id already queued in this wave")
        if key in self._jobs:
            raise BatchDeferred(job.custom_id, key, "queued")
        from g3o.extract.anthropic_client import params_bytes

        size = params_bytes(job.params)
        if self._jobs and self._submit_error is None and (
                len(self._jobs) >= self.chunk_max_requests or self._jobs_bytes + size > self.chunk_max_bytes):
            self._flush_chunk()  # the held chunk is full: submitted now, its bodies dropped
        if key not in self.store.queued:
            self.store.append({"kind": "queued", "key": key, "custom_id": job.custom_id})
        self._wave_cids[job.custom_id] = key
        if self._submit_error is not None:
            # a mid-wave submission failed: journaled as queued (known not sent) but neither held nor sent;
            # run_waves raises the failure after this pass and the next run asks it again
            raise BatchDeferred(job.custom_id, key, "queued; a submission failed this wave")
        self._jobs[key] = job
        self._jobs_bytes += size
        raise BatchDeferred(job.custom_id, key, "queued")

    def _flush_chunk(self) -> None:
        """Submit the held chunk mid-wave. A failure is kept for :func:`run_waves` (never raised into the
        stage, which would take it for an extractor failure); a process death (BaseException) propagates."""
        try:
            self._mid_wave_batches += len(self._submit_queued())
        except Exception as exc:  # noqa: BLE001 - re-raised by run_waves after the stage pass
            _log.error("per-page stage: a mid-wave Message Batch submission failed (%s); the rest of the wave "
                       "is journaled as queued and not sent", exc)
            self._submit_error = exc

    def live_call(self, job: Any) -> Any:
        """A PI-released re-ask: always live (its ``reask_spent`` marker is already journaled)."""
        return self.live_fn(job)

    # --- waves ----------------------------------------------------------------

    def pending(self) -> int:
        """Requests queued by this process and not yet submitted."""
        return sum(1 for k in self._jobs if k in self.store.queued)

    def queued_this_wave(self) -> bool:
        """Whether this wave queued anything: requests still held, or chunks already submitted mid-wave."""
        return bool(self.pending() or self._mid_wave_batches)

    def raise_submit_error(self) -> None:
        """Raise a failed mid-wave submission (after the stage pass, where an end-of-wave failure is raised)."""
        if self._submit_error is not None:
            exc, self._submit_error = self._submit_error, None
            raise exc

    def settle(self) -> None:
        """Before a wave: stop on an unacknowledged submission, then poll and collect every batch in flight."""
        open_seqs = self.store.unacknowledged()
        if open_seqs:
            seq = open_seqs[0]
            raise BatchSubmitUnacknowledged(seq, [cid for cid, _ in self.store.intents[seq]])
        for seq, batch_id in self.store.in_flight():
            if self.batch_client is None:
                raise BatchClientMissing(f"batch {batch_id} (submission #{seq}) is in flight and there is no "
                                         "batch client to poll it")
            self._collect(seq, batch_id)

    def _collect(self, seq: int, batch_id: str) -> None:
        while self.batch_client.batch_status(batch_id) != "ended":
            self.sleep(self.poll_seconds)
        keys = {cid: key for cid, key in self.store.intents.get(seq, [])}
        for result in self.batch_client.batch_results(batch_id):
            key = keys.get(result.custom_id)
            if key is None or self.store.has_result(key, batch_id, result.custom_id):
                continue  # not ours, or stored before a crash
            self.store.append({"kind": "result", "batch_id": batch_id, "custom_id": result.custom_id, "key": key,
                               "result": asdict(replace(result, batch_id=batch_id))})
            self.results_collected += 1
        missing = [cid for cid, key in self.store.intents.get(seq, [])
                   if not self.store.has_result(key, batch_id, cid)]
        if missing:  # a short results stream: not marked collected, so nothing is asked again (no double spend)
            if batch_id not in self.store.incomplete:  # the ended batch may now be abandoned by the operator
                self.store.append({"kind": "incomplete", "batch_id": batch_id, "missing": missing})
            raise BatchResultsIncomplete(batch_id, missing)
        self.store.append({"kind": "collected", "batch_id": batch_id})

    def submit(self, max_requests: int | None = None) -> list[str]:
        """End of a wave: submit the requests still held (intent first, then the batch, then its id)."""
        try:
            return self._submit_queued(max_requests)
        finally:
            self._wave_cids.clear()
            self._mid_wave_batches = 0

    def _submit_queued(self, max_requests: int | None = None) -> list[str]:
        from g3o.extract.anthropic_client import split_for_batches

        jobs = [j for k, j in self._jobs.items() if k in self.store.queued]
        if not jobs:
            return []
        cap = self.chunk_max_requests if max_requests is None else min(max_requests, self.chunk_max_requests)
        groups, refused = split_for_batches(jobs, max_requests=cap, max_bytes=self.chunk_max_bytes)
        if refused:  # never queued (__call__ sends such a request live): a wiring error, before any batch
            raise ValueError(f"{len(refused)} extractor request(s) exceed the batch byte guard: "
                             f"{[j.custom_id for j in refused]}")
        ids: list[str] = []
        for group in groups:
            seq = max([*self.store.intents, 0]) + 1
            pairs = [[j.custom_id, request_hash(j)] for j in group]
            self.store.append({"kind": "submit_intent", "seq": seq, "requests": pairs})
            try:
                batch_id = self.batch_client.submit_batch(list(group))
            finally:
                # once the intent is journaled this process never sends these again (an unacknowledged
                # intent stops the next run): their bodies are dropped from memory, sent or not
                self._release(pairs)
            self.store.append({"kind": "submitted", "seq": seq, "batch_id": batch_id})
            self._sent.update(key for _cid, key in pairs)
            self.batches_submitted += 1
            ids.append(batch_id)
        return ids

    def _release(self, pairs: list[list[str]]) -> None:
        from g3o.extract.anthropic_client import params_bytes

        for _cid, key in pairs:
            job = self._jobs.pop(key, None)
            if job is not None:
                self._jobs_bytes -= params_bytes(job.params)


def run_waves(extractor: BatchExtractor | None, stage_pass: Callable[[], Any], *,
              max_waves: int = DEFAULT_MAX_WAVES) -> Any:
    """Run the per-page stage (``stage_pass``) in waves until a wave queues no batched request.

    Each wave: settle the batches in flight (:meth:`BatchExtractor.settle`), run the stage, submit what it
    queued. Returns the last wave's result. ``extractor`` None: one pass (no batch mode, nothing stored).

    After ``max_waves`` waves the stage ends as after any pass: the institutions still waiting stay held
    (:data:`BATCH_PENDING`) and the batches submitted last stay in the batch journal, so the next run
    collects them and resumes those institutions."""
    if extractor is None:
        return stage_pass()
    if max_waves < 1:
        raise ValueError(f"max_waves must be at least 1, got {max_waves}")
    for _ in range(max_waves):
        extractor.settle()
        out = stage_pass()
        extractor.raise_submit_error()  # a mid-wave submission failed: the run stops, as at the end of a wave
        if not extractor.queued_this_wave():
            return out
        extractor.submit()
    _log.warning("per-page stage: wave cap (%d) reached with batched extractor requests pending; their "
                 "institutions stay held (%s) and resume on the next run", max_waves, BATCH_PENDING)
    return out


def has_batch_journal(run_dir: Path) -> bool:
    return batch_journal_path(run_dir).exists()


__all__ = ["ALL_BATCH", "BATCH_DIR", "BATCH_JOURNAL", "BATCH_PENDING", "DEFAULT_EXTRACTOR_MODE",
           "DEFAULT_CHUNK_MAX_BYTES", "DEFAULT_CHUNK_MAX_REQUESTS", "DEFAULT_MAX_WAVES", "DEFAULT_POLL_SECONDS", "EXTRACTOR_MODES", "MIX", "NO_BATCH", "BatchClientMissing",
           "BatchDeferred", "BatchExtractor", "BatchResultsIncomplete", "BatchSubmitUnacknowledged",
           "batch_journal_path", "has_batch_journal", "is_first_round", "record_batch_abandoned", "record_submit_outcome", "request_hash",
           "require_mode", "run_waves", "too_big_for_batch"]
