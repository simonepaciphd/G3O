"""The G3O run API — ``launch()`` (Run API spec v0.1 §1–§2).

One Python-callable entry point for a pre-sweep run. Everything that used to be
assembled in ``cli.py`` — minting an id, resolving keys, validating before spend,
dispatching stages — happens here, so the CLI is a thin argv adapter and the
droplet orchestrator (Item 3) drives the same code path the operator does rather
than a parallel one.

What ``launch()`` guarantees, in the order it establishes them:

1. an id exists (minted if the caller gave none, §2) and cannot collide with an
   existing run directory;
2. the keys this run will spend are resolved once (§3) and reported as ready
   before any of them is used;
3. everything that can be checked without spending money has been checked
   (§1.4) — a writable ``runs_dir``, credentials sufficient for the mode,
   capturable provenance;
4. only then are stages dispatched, and the receipt says what happened.

**Invariant this module must not break** (spec §0): with an explicit ``--run-id``
and env-sourced keys, on-disk artifacts are byte-identical to the pre-spec
pipeline. ``launch()`` adds decisions *around* the run, never inside it.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from g3o.common.credentials import Credentials, ResolvedCredentials, resolve
from g3o.common.run_state import state_dir
from g3o.run.presweep.config import STAGES, PresweepConfig
from g3o.run.run_id import (
    RUN_ID_FORMAT,
    is_minted_run_id,
    mint_run_id,
    run_started_at,
)

logger = logging.getLogger(__name__)

#: Precedence for the harness/session join key (§4.2): explicit -> env -> this.
UNATTENDED_SESSION_ID = "unattended"
SESSION_ID_ENV_VAR = "G3O_SESSION_ID"

#: Re-mint attempts when a minted id improbably collides with an existing dir (§2).
MINT_ATTEMPTS = 3

#: Filenames the receipt names. ``events.jsonl`` is written by PR C; the receipt
#: names where it will live so a caller has one place to look either way.
MANIFEST_FILENAME = "manifest.json"
EVENTS_FILENAME = "events.jsonl"


class LaunchValidationError(RuntimeError):
    """A pre-spend check failed; the run never started (spec §1.5).

    Reserved for **pre-manifest** failures, per §1.5 — reaching this exception
    means nothing was spent, nothing was written that a later run must reconcile
    against, and there is no telemetry to close out. Subclasses ``RuntimeError``
    so the callers and tests that predate the spec keep catching it.
    """


@dataclass(frozen=True)
class GitMetadata:
    """Code provenance for the run record (§4.1 ``code`` block).

    ``available`` is False for a non-git deployment (an installed wheel), which is
    legitimate and not an error. ``dirty`` is recorded, never blocked: §4.1 states
    plainly that ``git_dirty=true`` is allowed, because refusing to run on a dirty
    tree would push operators toward committing junk mid-incident.
    """

    available: bool
    sha: str | None = None
    dirty: bool | None = None
    package_version: str | None = None
    install_path: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RunReceipt:
    """What one ``launch()`` did (spec §1).

    ``summary`` is an addition to the eight fields §1 declares — it carries the
    stage counts ``run_presweep`` already returns, which the CLI prints and the
    orchestrator's status line reads. Additive and last, so a consumer written
    against §1 is unaffected; flagged to the PI rather than treated as settled,
    since §1's receipt is a signed surface.
    """

    run_id: str
    run_started_at: str
    runs_dir: Path
    manifest_path: Path
    resumed: bool
    outcome: Literal["completed", "stopped", "failed"]
    stop_after: str
    events_path: Path
    summary: dict[str, Any] = field(default_factory=dict)


def resolve_session_id(session_id: str | None = None) -> str:
    """The session join key (§4.2): explicit -> ``G3O_SESSION_ID`` -> ``unattended``.

    This is the link from a database row back to the AI-assisted process that
    produced it — the radical-transparency join to ``interaction-log.csv`` — so it
    is the caller's to supply and is never invented here. ``unattended`` is an
    honest admission that nobody claimed the run, not a placeholder id.
    """
    if session_id:
        return session_id
    return os.environ.get(SESSION_ID_ENV_VAR) or UNATTENDED_SESSION_ID


def capture_git_metadata(root: Path | None = None) -> GitMetadata:
    """Best-effort code provenance for ``root`` (default: the installed package).

    Shells out rather than taking a git dependency, and treats "not a git
    checkout" as a fact to record rather than a failure — an installed wheel has
    no ``.git`` and must still be launchable. A checkout whose git *commands*
    fail is different: that is a broken environment, and :func:`launch` refuses to
    spend money from one (see ``_assert_provenance_capturable``).
    """
    base = root or Path(__file__).resolve().parent.parent.parent
    version = _package_version()
    if not (base / ".git").exists():
        return GitMetadata(
            available=False,
            package_version=version,
            install_path=str(base),
            error="not a git checkout",
        )
    try:
        sha = _git(base, "rev-parse", "HEAD")
        dirty = bool(_git(base, "status", "--porcelain"))
    except (OSError, subprocess.SubprocessError) as exc:
        return GitMetadata(
            available=False,
            package_version=version,
            install_path=str(base),
            error=f"{type(exc).__name__}: {exc}",
        )
    return GitMetadata(
        available=True,
        sha=sha,
        dirty=dirty,
        package_version=version,
        install_path=str(base),
    )


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return proc.stdout.strip()


def _package_version() -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("g3o")
    except PackageNotFoundError:
        return None


def _mint_unused_run_id(runs_dir: Path, *, now: datetime | None = None) -> str:
    """Mint an id whose run directory does not already exist (§2).

    Re-mints on the improbable collision (same UTC second *and* same 2 bytes of
    entropy) and gives up after :data:`MINT_ATTEMPTS` rather than looping: if
    three consecutive mints all land on existing directories, the cause is not
    bad luck — it is a clock stuck or a ``runs_dir`` that is not what the caller
    thinks — and spending on that assumption is worse than stopping.

    Because a minted id can never name an existing directory, "fresh run" and
    "resume" stay unambiguous (§1.3): only an explicitly-passed id can rejoin.
    """
    for attempt in range(1, MINT_ATTEMPTS + 1):
        candidate = mint_run_id(now)
        if not (runs_dir / candidate).exists():
            return candidate
        logger.warning(
            "minted run id %s already exists under %s; re-minting (attempt %d/%d)",
            candidate, runs_dir, attempt, MINT_ATTEMPTS,
        )
    raise LaunchValidationError(
        f"could not mint an unused run id under {runs_dir} in {MINT_ATTEMPTS} "
        f"attempts. Every candidate named an existing run directory, which points "
        f"at a wrong runs_dir or a stopped clock rather than at collisions."
    )


def _announce_minted_run_id(run_id: str) -> None:
    """Put a freshly minted id in front of the operator **immediately**.

    §2 asks the CLI to print a minted id "first thing on stdout". Two facts make
    stderr the faithful way to honour that intent:

    * the id is minted inside ``launch()``, so the CLI does not learn it until
      ``launch()`` *returns* — which for a live sweep is hours later. Printing it
      from the CLI would deliver it exactly when it has stopped being useful,
      since its use is to resume or monitor a run already in flight.
    * ``cli.py`` states an invariant that stdout "carries the presweep summary and
      stays a single JSON document" (the cost-gate comment). A bare id line on
      stdout would break every consumer that parses that document.

    So: this line goes to stderr the moment the id exists, and ``run_id`` is also
    the first key of the CLI's stdout JSON. Flagged to the PI as a one-word
    correction to §2 (stdout -> stderr) rather than silently ignored — the spec's
    requirement is that the operator gets the id early, and this is what does that.

    Logging is not used because ``cli.py`` configures none, so an INFO record
    would reach nobody.
    """
    logger.info("minted run_id=%s", run_id)
    print(f"run_id={run_id}", file=sys.stderr, flush=True)


def _assert_runs_dir_writable(runs_dir: Path) -> None:
    """Pre-spend check (§1.4): the run can actually persist what it produces."""
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        probe = runs_dir / ".g3o-write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise LaunchValidationError(
            f"runs_dir {runs_dir} is not writable ({exc}). Checked before spend: a "
            f"run that cannot write its artifacts must not buy any."
        ) from exc


def _assert_credentials_sufficient(
    config: PresweepConfig, resolved: ResolvedCredentials
) -> None:
    """Pre-spend key gate (§1.4), one stage earlier than the orchestrator's.

    Delegates to the orchestrator's existing gate so the rule has exactly one
    implementation, and re-raises as :class:`LaunchValidationError` so a caller can
    tell "never started" from "died mid-run". The orchestrator keeps its own copy
    of the check for callers that still invoke ``run_presweep`` directly.
    """
    from g3o.run.presweep.orchestrator import _assert_live_keys

    if config.dry_run:
        return
    try:
        _assert_live_keys(config, resolved)
    except RuntimeError as exc:
        raise LaunchValidationError(str(exc)) from exc


def _assert_provenance_capturable(config: PresweepConfig, git: GitMetadata) -> None:
    """Pre-spend check (§1.4): a live run must be able to record what produced it.

    Mirrors §4.4's one hard telemetry rule — "a run that can't record its identity
    does not start" — but only where money is involved. A dry run on a
    non-checkout install warns and proceeds; a live run whose git metadata cannot
    be captured refuses, because its artifacts would be unattributable to any
    commit and therefore unreplicable.
    """
    if git.available:
        return
    message = (
        f"code provenance is not capturable ({git.error}); the run's artifacts "
        f"could not be tied to a commit."
    )
    if config.dry_run:
        logger.warning("%s Proceeding: a dry run spends nothing.", message)
        return
    raise LaunchValidationError(
        f"{message} Refusing to spend from an environment whose code state cannot "
        f"be recorded (spec §1.4, §4.4). Run from a git checkout, or run a dry run."
    )


def _outcome(config: PresweepConfig) -> Literal["completed", "stopped"]:
    """Classify a run that returned without raising (§1's ``outcome``).

    ``completed`` means the full stage roster ran; ``stopped`` means the run did
    less than that **by configuration** — a dry run, or ``--stop-after`` short of
    the last stage. ``failed`` is unreachable from here by design: §1.5 has
    ``launch()`` raise rather than return a failed receipt, so a caller cannot
    mistake an exception for a result. (PR C's reader reconstructs a ``failed``
    receipt from a run's events; that is where the third value earns its place.)

    A dry run counts as ``stopped``, not ``completed``: it planned and spent
    nothing. Reporting it as completed is exactly how a monitor comes to print
    green over a run that never gathered any data — the failure mode named in the
    Item 3 brief for the ingest leg.
    """
    if config.dry_run:
        return "stopped"
    return "completed" if config.stop_after == STAGES[-1] else "stopped"


def launch(
    config: PresweepConfig,
    *,
    credentials: Credentials | None = None,
    session_id: str | None = None,
) -> RunReceipt:
    """Run a pre-sweep and return its receipt (spec §1).

    ``config.run_id`` may be empty or ``None``: an id is then minted (§2) and the
    config is rebuilt with it, which re-runs ``PresweepConfig.__post_init__`` so
    every construction-time guarantee (the A7 language roster, the
    evidence-term exclusivity check) still holds for the config that actually
    runs. An explicit id is honoured verbatim — that is the replication and resume
    path, and it is the only way to rejoin an existing run (§1.3).

    ``credentials`` supply this run's keys (§3), each falling back to the
    environment. ``session_id`` is the join key back to the interaction log
    (§4.2). Dry run remains the default, as it must: live spend is opt-in.

    Raises rather than returning a failed receipt (§1.5); every pre-spend failure
    is a :class:`LaunchValidationError`.

    **Concurrency** (§1.7). Two launches with different run ids are safe as far as
    this function is concerned — no key state is process-global any more (§3.2),
    and both shared caches write atomically (§3.4, gated). One caveat found while
    implementing, not in the spec: ``serper_client`` holds live mode in a *module
    global*, so two concurrent launches in one process that disagree about
    ``dry_run`` would fight over it, and the loser could take the mock path in a
    live run. Concurrent same-process launches must therefore agree on ``dry_run``
    until that flag is threaded like the credentials were. Reported to the PI.
    """
    session = resolve_session_id(session_id)
    resolved = resolve(credentials)

    minted = not config.run_id
    if minted:
        config = replace(config, run_id=_mint_unused_run_id(config.runs_dir))
        _announce_minted_run_id(config.run_id)
    started_at = (
        run_started_at(config.run_id)
        if is_minted_run_id(config.run_id)
        else datetime.now(timezone.utc)
    )

    _assert_runs_dir_writable(config.runs_dir)
    _assert_credentials_sufficient(config, resolved)
    _assert_provenance_capturable(config, capture_git_metadata())

    run_dir = config.runs_dir / config.run_id
    # Resume is inferred from disk, exactly as the stage runners infer it (Q7=c):
    # `_state/` exists iff some stage of this run has started or finished, and a
    # minted id can never name an existing directory, so this is False for every
    # fresh run without a special case.
    resumed = state_dir(run_dir).exists()
    if resumed:
        logger.info("run_id=%s has existing state — rejoining", config.run_id)

    # Imported here, from the package rather than the module, so a caller that
    # patches `g3o.run.presweep.run_presweep` (the cost-gate tests do) still sees
    # its double through launch().
    from g3o.run.presweep import run_presweep

    logger.info(
        "launch run_id=%s session_id=%s dry_run=%s stop_after=%s resumed=%s",
        config.run_id, session, config.dry_run, config.stop_after, resumed,
    )
    summary = run_presweep(config, credentials=credentials)

    return RunReceipt(
        run_id=config.run_id,
        run_started_at=started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        runs_dir=run_dir,
        manifest_path=run_dir / MANIFEST_FILENAME,
        events_path=run_dir / EVENTS_FILENAME,
        resumed=resumed,
        outcome=_outcome(config),
        stop_after=config.stop_after,
        summary=summary if isinstance(summary, dict) else {},
    )


__all__ = [
    "EVENTS_FILENAME",
    "MANIFEST_FILENAME",
    "MINT_ATTEMPTS",
    "RUN_ID_FORMAT",
    "SESSION_ID_ENV_VAR",
    "UNATTENDED_SESSION_ID",
    "Credentials",
    "GitMetadata",
    "LaunchValidationError",
    "ResolvedCredentials",
    "RunReceipt",
    "capture_git_metadata",
    "is_minted_run_id",
    "launch",
    "mint_run_id",
    "resolve",
    "resolve_session_id",
    "run_started_at",
]
