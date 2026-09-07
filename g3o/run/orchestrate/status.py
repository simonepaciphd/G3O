"""What a run is doing, read off the disk it already writes (Item 3, leg 2).

The brief's requirement is precise: *"status derivable from manifest + events +
``_state/`` at any moment"*. Those three are the run's own record and they are
authoritative here — nothing in this module infers an outcome the run did not
itself write down.

They do not, however, answer one question a monitor must answer: **is this run
still alive?** §4.3 of the Run API spec says a crashed run's event log "simply
ends early", which on disk is indistinguishable from a run that is mid-stage and
perfectly healthy. A monitor that cannot tell those apart either declares dead
runs healthy (the operator waits forever) or declares live runs dead (the
operator resumes a run that is still spending). So the orchestrator writes one
more thing — a supervisor record under ``runs/<run_id>/_orchestrator/`` naming
the process it started — and this module combines the two:

    outcome  ← manifest + events + _state/   (authoritative, the run's own record)
    liveness ← the supervisor record          (additive, and never overrides an
                                               outcome the run actually recorded)

Everything under ``_orchestrator/`` is orchestrator bookkeeping and is
underscore-prefixed for the same reason ``_state/`` and ``_attrition.jsonl`` are:
it is run-scoped metadata, not collected data. Nothing in the pipeline reads it,
so a run launched by a bare ``g3o presweep`` is missing only its liveness — it
still reports its stages, its chunks, and its outcome, with liveness stated as
``unknown`` rather than guessed.

**The state vocabulary**, and the one that matters most:

===============  ==========================================================
``missing``      no run directory
``launching``    a run directory, but no manifest — nothing has been planned
``running``      no terminal event, and the process is alive (or unknowable)
``interrupted``  no terminal event, and the process is **gone**
``completed``    ``run_completed``
``stopped``      ``run_stopped`` — a dry run, or ``--stop-after`` short of the end
``failed``       ``run_failed``, or a pre-manifest launch failure
===============  ==========================================================

``interrupted`` is the named failed state the Item 3 brief requires of the
induced-failure test. A killed run cannot write ``run_failed`` — that is what
being killed means — so a monitor that only recognised the events the run writes
would report it as ``running`` forever. It is grouped with ``failed`` by
:attr:`RunStatus.is_failed`, and both block the ingest leg (:mod:`.ingest`),
which is the mechanism by which a failed run publishes nothing.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from g3o.common.run_state import done_dir, iter_chunks, load_state, state_dir
from g3o.run.presweep.config import STAGES

logger = logging.getLogger(__name__)

#: Orchestrator bookkeeping, run-scoped. Underscore-prefixed like ``_state/``.
ORCHESTRATOR_DIRNAME = "_orchestrator"

MANIFEST_FILENAME = "manifest.json"
EVENTS_FILENAME = "events.jsonl"

#: One record per leg. ``submit`` additionally carries the supervised process.
LEGS: tuple[str, ...] = ("submit", "ingest", "archive", "publish")

#: Events that end a run. Their presence is the authoritative outcome.
TERMINAL_EVENTS: dict[str, str] = {
    "run_completed": "completed",
    "run_stopped": "stopped",
    "run_failed": "failed",
}

RunState = Literal[
    "missing", "launching", "running", "interrupted", "completed", "stopped", "failed"
]
Liveness = Literal["alive", "dead", "unknown"]


# ---------------------------------------------------------------------------
# Paths and small IO
# ---------------------------------------------------------------------------


def orchestrator_dir(run_dir: Path) -> Path:
    return run_dir / ORCHESTRATOR_DIRNAME


def leg_record_path(run_dir: Path, leg: str) -> Path:
    return orchestrator_dir(run_dir) / f"{leg}.json"


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Temp-file + :func:`os.replace`, the pattern ``_state/`` established.

    Duplicated rather than imported from :mod:`g3o.common.run_state` (where it is
    private) on purpose: ``_state/`` is the recovery mechanism and its writer must
    not grow orchestrator callers. Same four lines, same guarantee — an
    interrupted write never leaves a half-parsed record for the next status read.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any] | None:
    """Parse a JSON object, or ``None`` for absent/unreadable/not-an-object.

    Status is a read-only report over files other processes are actively writing,
    so every read here tolerates garbage: a monitor that raises on a truncated
    manifest is a monitor that stops working exactly when something has gone
    wrong and someone is looking.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def read_events(path: Path) -> list[dict[str, Any]]:
    """Every parseable event, in file order. Skips a torn last line (§4.3).

    Appends are line-atomic but a killed process can still leave a partial line,
    and that line is the *most interesting* moment of the run — so it is dropped
    from the list and everything before it is kept, rather than the read failing.
    """
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


# ---------------------------------------------------------------------------
# Process liveness
# ---------------------------------------------------------------------------


def pid_identity(pid: int) -> str | None:
    """A value that changes when a pid is reused, or ``None`` where unavailable.

    Linux only, via ``/proc/<pid>/stat`` field 22 (``starttime``, in clock ticks
    since boot). Pid reuse is not a theoretical concern for this orchestrator: a
    live sweep runs for hours to days on a droplet whose default ``pid_max`` is
    32768, so a recycled pid belonging to some unrelated process is exactly how a
    monitor comes to report a dead run as healthy for the rest of the week.

    ``comm`` (field 2) can itself contain spaces and parentheses, so the split is
    on the **last** ``)`` rather than on whitespace.
    """
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    tail = raw.rsplit(")", 1)[-1].split()
    # Fields after ``comm`` start at (3) state, so field N is at index N-3.
    return tail[19] if len(tail) >= 20 else None


def _alive_posix(pid: int) -> Liveness:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return "dead"
    except PermissionError:
        # It exists; it just is not ours to signal.
        return "alive"
    except OSError:
        return "unknown"
    return "alive"


def _alive_windows(pid: int) -> Liveness:
    """Liveness on Windows **without** :func:`os.kill`.

    ``os.kill(pid, 0)`` is the POSIX idiom and it is actively dangerous here: on
    Windows, Python maps any signal that is not ``CTRL_C_EVENT`` /
    ``CTRL_BREAK_EVENT`` onto ``TerminateProcess(pid, sig)`` — so the portable-
    looking liveness probe *kills the run it was asked about*. This uses
    ``OpenProcess`` + ``GetExitCodeProcess`` instead.

    One documented ambiguity: a process that exited with code 259 is
    indistinguishable from a running one (259 is ``STILL_ACTIVE``). Nothing this
    orchestrator starts exits 259 — the CLI returns 0/1/2/3 — and reporting a
    dead run as alive is the safe direction of that error anyway: it delays a
    resume rather than triggering one against a live run.
    """
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:  # pragma: no cover - Windows only
        return "unknown"
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "alive" if ctypes.get_last_error() == ERROR_ACCESS_DENIED else "dead"
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return "unknown"
        return "alive" if code.value == STILL_ACTIVE else "dead"
    finally:
        kernel32.CloseHandle(handle)


def process_liveness(pid: int | None, identity: str | None = None) -> Liveness:
    """Is ``pid`` still running? ``unknown`` when the platform cannot say.

    ``identity`` is the :func:`pid_identity` value recorded when the process was
    started. When both the recorded and the current identity are known and they
    disagree, the pid has been reused and the answer is ``dead`` — the process
    the orchestrator started is gone, whatever is answering to its number now.
    """
    if not pid or pid <= 0:
        return "unknown"
    alive = _alive_windows(pid) if os.name == "nt" else _alive_posix(pid)
    if alive != "alive" or not identity:
        return alive
    current = pid_identity(pid)
    if current is not None and current != identity:
        return "dead"
    return alive


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunStatus:
    """One moment's answer to "what is this run doing?".

    Read-only and cheap: a handful of small file reads, no network, no locks. It
    is safe to call against a run that is actively being written — every reader
    here tolerates a partial line or a half-written file (see :func:`read_json`).
    """

    run_id: str
    run_dir: Path
    state: RunState
    liveness: Liveness = "unknown"
    dry_run: bool | None = None
    resumed: bool = False
    run_started_at: str | None = None
    session_id: str | None = None
    operator: str | None = None
    git_sha: str | None = None
    config_hash: str | None = None
    stop_after: str | None = None
    stages_done: tuple[str, ...] = ()
    stage_in_flight: str | None = None
    chunks_in_flight: tuple[str, ...] = ()
    n_events: int = 0
    last_event: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    pid: int | None = None
    legs: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.state in ("completed", "stopped", "failed", "interrupted")

    @property
    def is_failed(self) -> bool:
        """A run that ended badly — including one that was killed.

        ``interrupted`` belongs here even though the run never said so itself:
        the process is gone and the stages it had left are not going to run. The
        ingest leg refuses both, which is what makes "an induced failure
        publishes nothing" a property of the code rather than of the operator.
        """
        return self.state in ("failed", "interrupted")

    @property
    def publishable(self) -> bool:
        """May this run's output be loaded into the database?

        Deliberately narrow: a **completed** run, and never a dry run. Dry runs
        plan and spend nothing, so their tree has no findings to load — and
        ``launch()`` reports them as ``stopped`` precisely so a monitor cannot
        read "it finished" as "it gathered data" (``g3o.run.api._outcome``).
        ``stopped`` for a genuine ``--stop-after`` short of Stage 6 is excluded
        for the same reason: there is no Stage-7 output to ingest.
        """
        return self.state == "completed" and self.dry_run is not True

    def one_line(self) -> str:
        """The status one-liner the brief asks for. One run, one line, no colour."""
        bits = [f"{self.run_id}", f"{self.state.upper():<11}"]
        if self.state == "missing":
            return f"{self.run_id}  MISSING      no run directory at {self.run_dir}"
        bits.append(f"stages={len(self.stages_done)}/{len(STAGES)}")
        if self.stage_in_flight:
            bits.append(f"in-flight={self.stage_in_flight}")
        if self.chunks_in_flight:
            bits.append(f"chunks={len(self.chunks_in_flight)}")
        if self.dry_run:
            bits.append("dry-run")
        if self.state == "running":
            bits.append(f"pid={self.pid or '?'}/{self.liveness}")
        if self.failure:
            cause = str(self.failure.get("error_message") or "").splitlines()
            bits.append(
                f"cause={self.failure.get('error_class')}: "
                f"{cause[0][:80] if cause else '(no message)'}"
            )
        if self.state == "interrupted":
            bits.append("no terminal event — the process is gone")
        last = self.last_event or {}
        if last:
            bits.append(f"last={last.get('event')}@{last.get('ts')}(seq {last.get('seq')})")
        for leg in ("ingest", "archive", "publish"):
            record = self.legs.get(leg)
            if record:
                bits.append(f"{leg}={record.get('outcome', '?')}")
        return "  ".join(bits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "state": self.state,
            "liveness": self.liveness,
            "dry_run": self.dry_run,
            "resumed": self.resumed,
            "run_started_at": self.run_started_at,
            "session_id": self.session_id,
            "operator": self.operator,
            "git_sha": self.git_sha,
            "config_hash": self.config_hash,
            "stop_after": self.stop_after,
            "stages_done": list(self.stages_done),
            "stage_in_flight": self.stage_in_flight,
            "chunks_in_flight": list(self.chunks_in_flight),
            "n_events": self.n_events,
            "last_event": self.last_event,
            "failure": self.failure,
            "pid": self.pid,
            "publishable": self.publishable,
            "legs": self.legs,
        }


def _stages_done(run_dir: Path) -> tuple[str, ...]:
    """Stages carrying a ``.done`` marker, in roster order.

    Read from ``_state/.done`` rather than from ``stage_completed`` events: the
    markers are the pipeline's own resume signal (Q3=e2), so they stay correct
    for a run whose telemetry was disabled, and they cannot disagree with what a
    resume will actually skip.
    """
    marker_dir = done_dir(run_dir)
    if not marker_dir.exists():
        return ()
    present = {p.stem for p in marker_dir.glob("*.json")}
    return tuple(stage for stage in STAGES if stage in present)


def _chunks_in_flight(run_dir: Path) -> tuple[str, ...]:
    """``"<stage>:<chunk>"`` for every chunk submitted and not yet fetched.

    The same read :func:`g3o.run.telemetry.chunks_rejoined` performs for the
    ``resume`` event, over the stages that still have an *active* state file —
    which is exactly the set a resume would rejoin.
    """
    active = state_dir(run_dir)
    if not active.exists():
        return ()
    out: list[str] = []
    for path in sorted(active.glob("*.json")):
        state = load_state(run_dir, path.stem)
        if not state:
            continue
        for key, entry in iter_chunks(state):
            if entry.get("batch_id") and not entry.get("fetched_at"):
                out.append(f"{path.stem}:{key}")
    return tuple(out)


def _stage_in_flight(events: list[dict[str, Any]], stages_done: tuple[str, ...]) -> str | None:
    """The stage that started and has not reported completion.

    Events, not markers, because this is the question markers cannot answer: a
    stage with no ``.done`` marker may be running or may simply not have been
    reached, and only the event log distinguishes them.
    """
    started: list[str] = []
    for record in events:
        event = record.get("event")
        stage = record.get("stage")
        if not stage:
            continue
        if event == "stage_started":
            started.append(stage)
        elif event == "stage_completed" and stage in started:
            started.remove(stage)
    for stage in reversed(started):
        if stage not in stages_done:
            return stage
    return None


def _terminal(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The last terminal event, or ``None``.

    Scanned from the end: a resumed run's log carries the *previous*
    invocation's terminal event too (one file per run, seq contiguous across
    resumes — fixture loader invariants 1 and 2), and the run's current outcome
    is the last one written, not the first.
    """
    for record in reversed(events):
        if record.get("event") in TERMINAL_EVENTS:
            return record
    return None


def read_leg_records(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Every ``_orchestrator/<leg>.json`` that parses, keyed by leg."""
    out: dict[str, dict[str, Any]] = {}
    for leg in LEGS:
        record = read_json(leg_record_path(run_dir, leg))
        if record is not None:
            out[leg] = record
    return out


def run_status(runs_dir: Path, run_id: str) -> RunStatus:
    """Derive one run's status from manifest + events + ``_state/`` (+ liveness).

    The order of the decision is the order of authority:

    1. a terminal **event** wins outright — the run said what happened;
    2. failing that, a ``failed`` submit record wins, which is the only way to
       learn about a failure that happened *before* the manifest existed and so
       could never have reached the event log (spec §1.5 reserves
       ``LaunchValidationError`` for exactly that window);
    3. failing that, liveness decides between ``running`` and ``interrupted``.
    """
    run_dir = Path(runs_dir) / run_id
    if not run_dir.exists():
        return RunStatus(run_id=run_id, run_dir=run_dir, state="missing")

    legs = read_leg_records(run_dir)
    submit = legs.get("submit") or {}
    pid = submit.get("pid") if isinstance(submit.get("pid"), int) else None
    # A finished supervisor is not a live process, whatever its pid now says.
    liveness: Liveness = (
        "dead"
        if submit.get("finished_at")
        else process_liveness(pid, submit.get("pid_identity"))
    )

    manifest = read_json(run_dir / MANIFEST_FILENAME) or {}
    events = read_events(run_dir / EVENTS_FILENAME)
    stages_done = _stages_done(run_dir)
    config_snapshot = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}

    common: dict[str, Any] = {
        "run_id": run_id,
        "run_dir": run_dir,
        "liveness": liveness,
        "dry_run": config_snapshot.get("dry_run"),
        "resumed": any(r.get("event") == "resume" for r in events),
        "run_started_at": manifest.get("run_started_at"),
        "session_id": manifest.get("session_id"),
        "operator": manifest.get("operator"),
        "git_sha": (manifest.get("code") or {}).get("git_sha"),
        "config_hash": manifest.get("config_hash"),
        "stop_after": config_snapshot.get("stop_after"),
        "stages_done": stages_done,
        "stage_in_flight": _stage_in_flight(events, stages_done),
        "chunks_in_flight": _chunks_in_flight(run_dir),
        "n_events": len(events),
        "last_event": events[-1] if events else None,
        "pid": pid,
        "legs": legs,
    }

    terminal = _terminal(events)
    if terminal is not None:
        state: RunState = TERMINAL_EVENTS[str(terminal.get("event"))]  # type: ignore[assignment]
        failure = None
        if state == "failed":
            payload = terminal.get("payload") or {}
            failure = {
                "error_class": payload.get("error_class"),
                "error_message": payload.get("error_message"),
                "stage": common["stage_in_flight"],
                "source": "run_failed",
            }
        return RunStatus(state=state, failure=failure, **common)

    if submit.get("outcome") == "failed":
        # No terminal event, but the launcher recorded a failure: a pre-manifest
        # refusal (an unwritable runs_dir, a missing live key). Nothing was spent
        # and there is no telemetry to read, so the record is the only witness.
        return RunStatus(
            state="failed",
            failure={
                "error_class": submit.get("error_class"),
                "error_message": submit.get("error_message"),
                "stage": None,
                "source": "submit record (pre-manifest failure)",
            },
            **common,
        )

    if not manifest:
        return RunStatus(state="launching", **common)
    if liveness == "dead":
        return RunStatus(
            state="interrupted",
            failure={
                "error_class": None,
                "error_message": (
                    "the run wrote no terminal event and its process is gone; it was "
                    "killed or the machine died mid-stage. `_state/` is intact — "
                    "re-invoke the same run id to rejoin (spec §1.3)."
                ),
                "stage": common["stage_in_flight"],
                "source": "liveness (no terminal event, process gone)",
            },
            **common,
        )
    return RunStatus(state="running", **common)


def record_leg(
    run_dir: Path,
    leg: str,
    *,
    outcome: str,
    started_at: str | None = None,
    **detail: Any,
) -> Path:
    """Write ``_orchestrator/<leg>.json``. Never raises — this is bookkeeping.

    Same rule telemetry follows (§4.4): a record that cannot be written warns and
    the leg continues. The legs themselves report through their return values and
    exit codes; this file exists so a *later* status read can say what already
    happened, not so the leg can decide anything.
    """
    payload = {
        "leg": leg,
        "outcome": outcome,
        "started_at": started_at,
        "recorded_at": utc_now_iso(),
        **detail,
    }
    path = leg_record_path(run_dir, leg)
    try:
        write_json_atomic(path, payload)
    except OSError:
        logger.warning("could not write %s leg record at %s (non-fatal)", leg, path, exc_info=True)
    return path


def utc_now_iso() -> str:
    """ISO-8601 UTC to the second — the one stamp format this record uses."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "EVENTS_FILENAME",
    "LEGS",
    "MANIFEST_FILENAME",
    "ORCHESTRATOR_DIRNAME",
    "TERMINAL_EVENTS",
    "Liveness",
    "RunState",
    "RunStatus",
    "leg_record_path",
    "orchestrator_dir",
    "pid_identity",
    "process_liveness",
    "read_events",
    "read_json",
    "read_leg_records",
    "record_leg",
    "run_status",
    "utc_now_iso",
    "write_json_atomic",
]
