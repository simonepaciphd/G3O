"""Leg 1 — start a run that outlives the shell that started it (Item 3).

The requirement is the PI's: *"runs on the droplet under a supervisor
(nohup/systemd) so my disconnecting changes nothing."* Two things are needed for
that, and only two:

1. the run's process must not die when its terminal does. That is what
   ``start_new_session=True`` buys — a new session has no controlling terminal,
   so the ``SIGHUP`` that a closing SSH connection sends to the foreground
   process group never reaches it. It is precisely what ``nohup`` does, done in
   process rather than by wrapping the command in a shell, so there is no shell
   quoting layer between the operator and the config;
2. whoever reconnects must be able to find the run. That needs the run id to
   exist *before* the child starts, so this module mints it (§2) and passes it
   down explicitly — an id minted inside the child would be knowable only by
   reading the child's log.

``systemd`` is the alternative and is not worse; the runbook carries a unit file
for the operator who wants restart-on-boot. Nothing here depends on which is
used, because the supervision fact this orchestrator relies on is only "the pid
in the submit record is the run" (see :mod:`.status`).

**What this module deliberately does not do:** decide anything about the run.
``launch()`` owns minting policy, key resolution, pre-spend validation, and the
manifest (Run API spec §1–§4); the orchestrator's job is to call it in a process
that survives, and to write down which process that was. The one piece of
``launch()``'s policy reused here is the collision-checked minting helper — see
:func:`_mint`.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from g3o.common.credentials import Credentials
from g3o.run.api import RunReceipt, launch
from g3o.run.orchestrate.status import (
    orchestrator_dir,
    pid_identity,
    read_json,
    utc_now_iso,
    write_json_atomic,
)
from g3o.run.presweep.config import PresweepConfig

logger = logging.getLogger(__name__)

SUBMIT_LOG_FILENAME = "submit.log"
SUBMIT_CONFIG_FILENAME = "submit_config.json"
SUBMIT_RECORD_FILENAME = "submit.json"
#: The preflight projection that cleared a live submit against its cost ceiling.
COST_PROJECTION_FILENAME = "cost_projection.json"

#: ``PresweepConfig`` fields whose JSON form is not their Python form.
_PATH_FIELDS = ("runs_dir", "master_csv")
_TUPLE_FIELDS = ("stratify_keys", "discovery_languages")


class SubmitError(RuntimeError):
    """The run could not be started. Nothing was spent."""


# ---------------------------------------------------------------------------
# Config round-trip
# ---------------------------------------------------------------------------


def config_to_mapping(config: PresweepConfig) -> dict[str, Any]:
    """JSON-ready snapshot of a config, with both paths made absolute.

    Absolute paths are what make a detached child independent of the cwd it was
    spawned from — a relative ``--master-csv`` resolved against the operator's
    shell would resolve against something else entirely under systemd.

    Resolving them is free of provenance consequences, which is worth stating
    because it would not be obvious: ``master_csv``, ``run_id`` and ``runs_dir``
    are the three keys excluded from ``config_hash``
    (:data:`g3o.run.telemetry.CONFIG_HASH_EXCLUDES` — they are *where* a run ran,
    not *what* it ran), so a config submitted by path A and by path B hashes
    identically and the run record cannot drift because of this call.
    """
    out: dict[str, Any] = {}
    for f in fields(config):
        value = getattr(config, f.name)
        if f.name in _PATH_FIELDS:
            out[f.name] = str(Path(value).expanduser().resolve())
        elif isinstance(value, tuple):
            out[f.name] = list(value)
        elif value is not None and f.name == "discovery_evidence_terms":
            out[f.name] = dict(value)
        else:
            out[f.name] = value
    return out


def config_from_mapping(mapping: dict[str, Any]) -> PresweepConfig:
    """Rebuild a :class:`PresweepConfig` from its JSON form.

    Unknown keys raise rather than being dropped. A config file is the record of
    what was submitted for an unattended run, so a typo'd key silently ignored is
    a run that spent money on a configuration nobody chose — the same argument
    that makes ``__post_init__``'s language check a construction-time refusal.

    Keys beginning with ``_`` are ignored as comments. JSON has none, the file is
    meant to be read by people, and no typo of a real field name starts with an
    underscore — so the convention costs the refusal above nothing.
    """
    mapping = {k: v for k, v in mapping.items() if not k.startswith("_")}
    known = {f.name for f in fields(PresweepConfig)}
    unknown = sorted(set(mapping) - known)
    if unknown:
        raise SubmitError(
            f"unknown config key(s) {unknown} — not fields of PresweepConfig. "
            f"Known keys: {sorted(known)}. Refusing rather than ignoring them: an "
            f"ignored key is a run configured differently from the file that "
            f"claims to describe it."
        )
    kwargs = dict(mapping)
    for name in _PATH_FIELDS:
        if name in kwargs and kwargs[name] is not None:
            kwargs[name] = Path(str(kwargs[name])).expanduser()
    for name in _TUPLE_FIELDS:
        if name in kwargs and kwargs[name] is not None:
            kwargs[name] = tuple(kwargs[name])
    if kwargs.get("discovery_evidence_terms") is not None:
        kwargs["discovery_evidence_terms"] = dict(kwargs["discovery_evidence_terms"])
    kwargs.setdefault("run_id", "")
    try:
        return PresweepConfig(**kwargs)
    except (TypeError, ValueError) as exc:
        # ValueError is __post_init__'s refusal (the A7 language roster, the
        # evidence-term exclusivity check) — a genuine operator-facing message.
        raise SubmitError(f"invalid run config: {exc}") from exc


def load_config_file(path: Path) -> PresweepConfig:
    payload = read_json(path)
    if payload is None:
        raise SubmitError(
            f"{path} is not a readable JSON object. The submit config is a single "
            f"JSON object of PresweepConfig fields; see docs/runbook-orchestrator.md."
        )
    return config_from_mapping(payload)


# ---------------------------------------------------------------------------
# The submit record
# ---------------------------------------------------------------------------


def submit_record_path(run_dir: Path) -> Path:
    return orchestrator_dir(run_dir) / SUBMIT_RECORD_FILENAME


def update_submit_record(run_dir: Path, **updates: Any) -> None:
    """Merge ``updates`` into the submit record, never downgrading a finished run.

    Two processes write this file — the parent that spawns a detached child, and
    the child itself — and their writes can land in either order. The merge rule
    that makes that safe is one sentence: **a record that already has
    ``finished_at`` does not go back to running.** Without it, a fast run (a
    dry-run smoke) can finish before its parent's post-spawn write lands, and the
    parent would overwrite the outcome with "running" — leaving a completed run
    reporting a dead process forever.

    Bookkeeping, so it never raises (the same rule telemetry follows, §4.4).
    """
    path = submit_record_path(run_dir)
    existing = read_json(path) or {}
    if existing.get("finished_at") and not updates.get("finished_at"):
        updates = {
            k: v for k, v in updates.items() if k not in ("outcome", "started_at")
        }
    payload = {**existing, **updates, "leg": "submit", "recorded_at": utc_now_iso()}
    try:
        write_json_atomic(path, payload)
    except OSError:
        logger.warning("could not write the submit record at %s (non-fatal)", path, exc_info=True)


# ---------------------------------------------------------------------------
# Submitting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubmitReceipt:
    """What one submit did. ``receipt`` is present only for a foreground run."""

    run_id: str
    run_dir: Path
    detached: bool
    pid: int | None = None
    log_path: Path | None = None
    receipt: RunReceipt | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "detached": self.detached,
            "pid": self.pid,
            "log_path": str(self.log_path) if self.log_path else None,
            "outcome": self.receipt.outcome if self.receipt else None,
            "resumed": self.receipt.resumed if self.receipt else None,
            "summary": self.receipt.summary if self.receipt else None,
        }


def _mint(runs_dir: Path) -> str:
    """Mint a collision-checked run id (spec §2).

    Reuses ``launch()``'s own helper rather than re-deriving the policy. That
    helper is module-private, and importing it anyway is the deliberate choice:
    §2's rule — re-mint on a collision, give up after three attempts rather than
    looping, because three collisions mean a stopped clock or the wrong
    ``runs_dir`` — must have exactly one implementation. A second copy here would
    be free to drift from the spec while still looking correct.
    """
    from g3o.run.api import _mint_unused_run_id

    return _mint_unused_run_id(runs_dir)


def cost_gate(
    config: PresweepConfig,
    *,
    credentials: Credentials | None,
    cost_ceiling_usd: float | None,
) -> dict[str, Any] | None:
    """Refuse a live submit whose projected spend exceeds ``cost_ceiling_usd``.

    Added 2026-08-17. The circuit breaker previously existed only in
    ``g3o.cli._cmd_presweep``, which wraps ``launch()`` for the argv path — so the
    orchestrator, which calls ``launch()`` directly, had no cap at all. The PI's
    signed spend authorisation (PI-Checklist item (d), 2026-08-16) states a cap
    "per run", and the runbook prescribes this verb for the demonstration run, so
    the cap has to bind here or it does not bind on the path that is actually
    used.

    Deliberately the same mechanism as the CLI's, not a second policy: a preflight
    projection, which submits no batch and spends nothing, and a refusal before
    ``launch()`` is reached. Returns the projection so the caller can record it —
    the projection that cleared real spend is part of the run's record, not just
    the one that blocked it. Returns ``None`` when no ceiling is set or the run is
    a dry run, which spends nothing by construction.
    """
    if cost_ceiling_usd is None or config.dry_run:
        return None

    from g3o.run.preflight import run_preflight

    summary = run_preflight(
        config, cost_ceiling_usd=cost_ceiling_usd, credentials=credentials
    )
    if summary.get("cost_ceiling_exceeded"):
        projected = (summary.get("cost_preview") or {}).get(
            "est_openai_batch_total_usd", 0
        )
        raise SubmitError(
            f"COST CIRCUIT BREAKER: projected OpenAI Batch spend "
            f"${projected:.2f} exceeds the ${cost_ceiling_usd:.2f} ceiling. "
            f"Nothing was submitted. Raise --cost-ceiling deliberately, or reduce "
            f"--sample-size."
        )
    return summary


def submit(
    config: PresweepConfig,
    *,
    credentials: Credentials | None = None,
    session_id: str | None = None,
    detach: bool = False,
    log_path: Path | None = None,
    cost_ceiling_usd: float | None = None,
) -> SubmitReceipt:
    """Start a run. With ``detach``, return as soon as it is running.

    The run id is resolved here in **both** modes, minted when the config carries
    none. Doing it before the fork is what lets this function report the id to the
    operator immediately, create ``_orchestrator/`` so a pre-manifest failure has
    somewhere to be recorded, and hand the child an explicit id — and an explicit
    id is also what keeps resume semantics honest: ``launch()`` rejoins an
    existing run only for an id it was given (§1.3), and a minted id can never
    name an existing directory.

    Resume is therefore not a mode: pass the existing run id and re-invoke.
    """
    run_id = config.run_id or _mint(config.runs_dir)
    config = replace(config, run_id=run_id)
    run_dir = config.runs_dir / run_id

    # Before the detach fork, so the cap binds identically in both modes. A
    # detached run that only discovered its ceiling in the child would have
    # already returned "running" to the operator.
    projection = cost_gate(
        config, credentials=credentials, cost_ceiling_usd=cost_ceiling_usd
    )

    try:
        orchestrator_dir(run_dir).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SubmitError(
            f"cannot create {orchestrator_dir(run_dir)} ({exc}). The orchestrator "
            f"records every leg under the run directory; a run it cannot write "
            f"bookkeeping for is a run it cannot monitor."
        ) from exc

    # The projection that CLEARED real spend is part of the run's record, not
    # only the one that blocks it — otherwise the only evidence a cap was in
    # force is that nothing went wrong.
    if projection is not None:
        try:
            write_json_atomic(
                orchestrator_dir(run_dir) / COST_PROJECTION_FILENAME,
                json.loads(json.dumps(projection, default=str)),
            )
        except OSError:
            logger.warning("could not record the cost projection (non-fatal)", exc_info=True)

    if detach:
        return _submit_detached(
            config, session_id=session_id, credentials=credentials, log_path=log_path
        )
    return _submit_foreground(config, credentials=credentials, session_id=session_id)


def _submit_foreground(
    config: PresweepConfig,
    *,
    credentials: Credentials | None,
    session_id: str | None,
) -> SubmitReceipt:
    """Run in this process. The path the smoke gate and the tests take."""
    run_dir = config.runs_dir / config.run_id
    started_at = utc_now_iso()
    # Deliberately narrow: the process running the launch records *itself* — pid,
    # identity, when it started. It does not record `detached` or `invocation`,
    # because it cannot know them: when this function is the spawned child, the
    # parent knows how the run was started and writes those. A record with no
    # `detached` key is a foreground submit. Splitting ownership this way is what
    # keeps the two writers from racing over a field they would both answer.
    update_submit_record(
        run_dir,
        outcome="running",
        started_at=started_at,
        pid=os.getpid(),
        pid_identity=pid_identity(os.getpid()),
    )
    try:
        receipt = launch(config, credentials=credentials, session_id=session_id)
    except BaseException as exc:
        # The run's own `run_failed` event is emitted inside `run_presweep` for
        # anything that happens after the manifest exists. This record is what
        # covers the window *before* it — a LaunchValidationError leaves no
        # telemetry at all (§1.5), so without this a refused launch would be
        # indistinguishable from a run that was never started.
        update_submit_record(
            run_dir,
            outcome="failed",
            finished_at=utc_now_iso(),
            error_class=type(exc).__name__,
            error_message=str(exc),
        )
        raise
    update_submit_record(
        run_dir,
        outcome=receipt.outcome,
        finished_at=utc_now_iso(),
        resumed=receipt.resumed,
        stop_after=receipt.stop_after,
    )
    return SubmitReceipt(
        run_id=receipt.run_id,
        run_dir=run_dir,
        detached=False,
        pid=os.getpid(),
        log_path=None,
        receipt=receipt,
    )


def _detach_kwargs() -> dict[str, Any]:
    """Platform flags that sever the child from this terminal.

    POSIX: ``start_new_session`` puts the child in a new session with no
    controlling terminal, so the ``SIGHUP`` sent when the SSH connection closes
    is never delivered to it. Windows: ``DETACHED_PROCESS`` gives it no console
    and ``CREATE_NEW_PROCESS_GROUP`` keeps a Ctrl-C in the operator's window from
    reaching it. The droplet is Linux; the Windows branch is here because the
    orchestrator is developed and tested on the PI's machine.
    """
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        return {"creationflags": DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _submit_detached(
    config: PresweepConfig,
    *,
    credentials: Credentials | None,
    session_id: str | None,
    log_path: Path | None,
) -> SubmitReceipt:
    """Spawn a supervised child and return once it is running.

    The child is *this* orchestrator in foreground mode, not ``g3o presweep``
    directly, so the run takes one code path whether it was submitted by hand or
    detached — the submit record, the leg bookkeeping, and the failure recording
    all happen in the child exactly as they would in the foreground.

    The config travels as a file rather than as reconstructed argv. Rebuilding
    thirty flags from a dataclass is a class of bug with no upside, and the file
    doubles as the record of what was submitted: ``_orchestrator/submit_config.json``
    is readable next to the manifest it produced.

    Credentials do **not** travel with it. The child inherits this process's
    environment, which is where the keys are (§3.1: explicit → env → unset), and a
    key written into a spawn argument or a config file would land in
    ``/proc/<pid>/cmdline``, in every ``ps`` listing on the box, and in a file that
    the archive leg would then upload. Only the operator's key *label* crosses.
    """
    run_dir = config.runs_dir / config.run_id
    odir = orchestrator_dir(run_dir)
    config_path = odir / SUBMIT_CONFIG_FILENAME
    write_json_atomic(config_path, config_to_mapping(config))
    log = log_path or (odir / SUBMIT_LOG_FILENAME)
    log.parent.mkdir(parents=True, exist_ok=True)

    argv = [
        sys.executable,
        "-m",
        "g3o.run.orchestrate",
        "submit",
        "--config",
        str(config_path),
        "--run-id",
        config.run_id,
    ]
    if session_id:
        argv += ["--session-id", session_id]
    if credentials and credentials.label:
        argv += ["--key-label", credentials.label]

    # Appended, not truncated: a resume of the same run id is a second process
    # writing this log, and the first process's output is part of the run's
    # history. Line-buffered stdio in the child would be nicer still, but that is
    # the child's business (`-u` is not forced: it would change nothing on disk
    # here and would slow every write in a long run).
    handle = open(log, "a", encoding="utf-8", errors="replace")  # noqa: SIM115
    try:
        child = subprocess.Popen(  # noqa: S603 - argv is built here, never from input
            argv,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **_detach_kwargs(),
        )
    except OSError as exc:
        handle.close()
        raise SubmitError(
            f"could not spawn the supervised run process ({exc}). argv[0] was "
            f"{argv[0]!r}; check that this Python can import g3o "
            f"(`{argv[0]} -m g3o.run.orchestrate status --help`)."
        ) from exc
    finally:
        # This process holds no further use for the write end; the child has its
        # own duplicate. Leaving it open would keep the fd alive for the parent's
        # lifetime, which for a shell one-liner is short but for a supervisor
        # loop is not.
        handle.close()

    update_submit_record(
        run_dir,
        outcome="running",
        started_at=utc_now_iso(),
        pid=child.pid,
        pid_identity=pid_identity(child.pid),
        detached=True,
        invocation="orchestrate.submit --detach",
        log_path=str(log),
        config_path=str(config_path),
        argv=argv,
    )
    logger.info("run %s submitted detached as pid %d; log: %s", config.run_id, child.pid, log)
    return SubmitReceipt(
        run_id=config.run_id,
        run_dir=run_dir,
        detached=True,
        pid=child.pid,
        log_path=log,
        receipt=None,
    )


__all__ = [
    "SUBMIT_CONFIG_FILENAME",
    "SUBMIT_LOG_FILENAME",
    "SUBMIT_RECORD_FILENAME",
    "SubmitError",
    "SubmitReceipt",
    "config_from_mapping",
    "config_to_mapping",
    "load_config_file",
    "submit",
    "submit_record_path",
    "update_submit_record",
]
