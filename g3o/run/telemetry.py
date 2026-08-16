"""Run telemetry — the manifest block and the event log (Run API spec §4).

Two files, two jobs, and the split matters: ``_state/`` is the **recovery
mechanism** and is untouched by anything here; telemetry is the **record**.
Nothing in the pipeline reads what this module writes, which is what lets §4.4
hold — a telemetry failure after launch warns and the run continues. The one
exception is the manifest write itself: a run that cannot record its identity does
not start.

The on-disk shape is not free to drift. ``tests/fixtures/run_contract/`` was
published to the backend before this module existed precisely so the loader could
be written against a fixed target, so the fixture — not this implementation — is
the contract, down to the envelope's six keys and the payload of every event. The
loader invariants it documents are asserted in ``tests/test_run_telemetry.py``:
one file per run, ``seq`` contiguous from 1 across resumes, ``ts``
non-decreasing, the last line terminal, and no key material anywhere.

One deliberate omission: ``spend_snapshot``. It is optional in the spec (§4.3,
open item 4) and the fixture's loader invariant 12 already tells the backend its
absence means nothing, so it is the sprint's pre-agreed droppable event and is not
emitted. Adding it later needs no loader change — which was the point of writing
the invariant that way.

**Disposition of ``feature/actual-cost-report-&-telemetry``** (branch commit
``3492d97``, 2026-07-27), which the sprint brief required be folded in or
superseded explicitly. This module **supersedes** it for the §4 surface, and only
that surface: the branch writes no manifest and no event log, so there is no
double-emit to reconcile. What it *does* contain — ``g3o/common/pricing.py``,
``g3o/report/cost_report.py``, ``g3o/report/politeness.py``,
``g3o/common/scrape_telemetry.py``, and per-chunk token-usage capture in
``_state/`` — is a separate cost-reporting feature that is **not** superseded and
is not folded in here: it predates storage-layout-v2 and contract v2.3, so it
needs its own rebase and its own PR rather than being smuggled into this one.
Nothing on that branch is lost by this PR; nothing on it is claimed by it either.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import logging
import os
import socket
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.common.contract_pin import contract_surface
from g3o.common.credentials import ResolvedCredentials
from g3o.common.run_state import done_dir, iter_chunks, load_state, state_dir

logger = logging.getLogger(__name__)

#: Bumped only on a breaking change to the manifest's telemetry surface (§4.1).
MANIFEST_SCHEMA_VERSION = 1

EVENTS_FILENAME = "events.jsonl"
MANIFEST_FILENAME = "manifest.json"

#: Excluded from ``config_hash`` and recorded in-band as ``config_hash_excludes``
#: so the hash is reproducible without out-of-band knowledge (fixture decision 1,
#: PI-accepted 2026-08-11). These three are *where a run ran*, not *what it ran*:
#: two runs differing only in these are the same measurement instrument.
CONFIG_HASH_EXCLUDES: tuple[str, ...] = ("master_csv", "run_id", "runs_dir")

#: Prompt assets hashed whole, keyed by repo-relative path (§4.1 ``prompts``).
#: File *content*, unlike ``contract.*.sha256`` which pins the machine-readable
#: surface — so a prose-only edit moves these and leaves those fixed.
PROMPT_ASSETS: tuple[str, ...] = (
    "g3o/extract/prompts/system_prompt.md",
    "g3o/extract/prompts/output_contract.md",
    "g3o/validate/prompts/system_prompt.md",
    "g3o/validate/prompts/output_contract.md",
)

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PACKAGE_ROOT.parent

OPERATOR_ENV_VAR = "G3O_OPERATOR"


# ---------------------------------------------------------------------------
# Hashing and provenance inputs
# ---------------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    """sha256 of a file's content, with line endings normalised to LF.

    Normalisation is not cosmetic here. These hashes are provenance: two runs at
    the same commit must record the same value, or a reader comparing them
    concludes the prompts changed when only the checkout did. The repository has
    no ``.gitattributes``, so a text asset is CRLF in a Windows working tree and
    LF in a Linux one — the droplet and this machine would disagree about
    identical content, while ``contract.*.sha256`` (which hashes Python objects,
    not bytes) agreed. A manifest asserting "contract unchanged, prompts changed"
    for one commit is precisely the false signal this block exists to prevent.

    Collapsing ``\\r\\n`` -> ``\\n`` makes the value a property of the content and
    equal to the git blob's hash on every platform. Found 2026-08-12 while
    re-verifying the published fixture's own verification recipe; the fixture's
    ``prompts.*`` values are CRLF-derived and marked superseded there.
    """
    return hashlib.sha256(
        path.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()


def prompt_hashes() -> dict[str, str]:
    """``{repo-relative path: sha256(LF-normalised content)}`` for the four assets.

    Resolved against the installed package, not the repo, so a wheel-installed run
    hashes the assets it will actually send. A missing asset is a broken install
    and raises here rather than producing a manifest that quietly omits it.
    """
    out: dict[str, str] = {}
    for rel in PROMPT_ASSETS:
        path = _PACKAGE_ROOT / Path(rel).relative_to("g3o")
        out[rel] = file_sha256(path)
    return out


def config_hash(
    config: Mapping[str, Any], *, excludes: Iterable[str] = CONFIG_HASH_EXCLUDES
) -> str:
    """sha256 over the canonical JSON of ``config`` minus ``excludes``.

    Canonicalization is pinned by the fixture because the value lands in
    ``g3o.runs.config_hash`` (§5.2) and may be re-verified server-side: sorted
    keys, no whitespace, ``ensure_ascii=False``. An unstated canonicalization is a
    hash only its writer agrees with.
    """
    skip = set(excludes)
    hashed = {k: v for k, v in config.items() if k not in skip}
    canonical = json.dumps(
        hashed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def master_build_id(sample: list[dict[str, Any]]) -> str | None:
    """The master build the run sampled from, if the master declares one.

    ``scripts/build_codebook_html.py`` already established this contract on the
    master side: a ``master_build_id`` column, one distinct value per build,
    shaped ``mb-YYYY-MM-DD``. The 2026-07-17 master carries no such column, so
    this returns ``None`` there and the manifest records null — which is exactly
    how the published fixture documents the field.

    Disagreement across sampled rows returns ``None`` rather than picking one: a
    master with two build ids is not a build this function can name, and guessing
    would put a wrong provenance value somewhere it is hard to notice.
    """
    values = {
        (row.get("master_build_id") or "").strip()
        for row in sample
        if (row.get("master_build_id") or "").strip()
    }
    if len(values) != 1:
        if len(values) > 1:
            logger.warning(
                "master declares %d distinct master_build_id values %r; recording "
                "null rather than choosing one",
                len(values), sorted(values),
            )
        return None
    return values.pop()


def operator() -> str:
    """Who is accountable for the run. ``G3O_OPERATOR``, else the OS user."""
    from_env = os.environ.get(OPERATOR_ENV_VAR)
    if from_env:
        return from_env
    try:
        return getpass.getuser()
    except Exception:  # no passwd entry / no LOGNAME on a bare container
        return "unknown"


# ---------------------------------------------------------------------------
# The manifest block (§4.1)
# ---------------------------------------------------------------------------


def build_manifest_block(
    *,
    run_id: str,
    run_started_at: str,
    session_id: str,
    invocation: str,
    git: Any,
    config_snapshot: Mapping[str, Any],
    credentials: ResolvedCredentials,
    model: str,
    sample: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The §4.1 telemetry keys, in the order the published fixture lists them.

    ``git`` is a :class:`g3o.run.api.GitMetadata`; taken as ``Any`` to keep this
    module importable from ``api`` without a cycle.

    ``frame.frame_id`` stays null even when a build id is known: §5.1's frames
    design is still an open item awaiting Katon's and the PI's explicit OK, and
    ``frame_id`` is the FK target of a table that does not exist yet. Recording
    the build id we *can* attest (``master_build_id``) while leaving the key we
    cannot is the honest split, and it is what the fixture already tells the
    loader to expect.
    """
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        # Repeated from the planning half of the merged manifest, with the same
        # value, so this block stays a complete §4.1 document on its own — a
        # reader handed only the telemetry keys can still say which run it has.
        "run_id": run_id,
        "run_started_at": run_started_at,
        "session_id": session_id,
        "operator": operator(),
        "hostname": socket.gethostname(),
        "invocation": invocation,
        "code": {
            "git_sha": git.sha,
            "git_dirty": git.dirty,
            "package_version": git.package_version,
            "install_path": git.install_path,
        },
        "frame": {
            "frame_id": None,
            "master_build_id": master_build_id(sample or []),
        },
        "contract": contract_surface(),
        "prompts": prompt_hashes(),
        "config_hash": config_hash(config_snapshot),
        "config_hash_excludes": list(CONFIG_HASH_EXCLUDES),
        "credentials": credentials.telemetry(),
        "model_ids": {"requested": {"batch_stages": model}},
    }


#: Telemetry keys that describe *this run's identity* and must survive a resume
#: untouched (§4.1: the manifest is never overwritten on resume). Everything else
#: in the manifest is planning state that a re-plan may legitimately refresh.
IDENTITY_KEYS: tuple[str, ...] = (
    "manifest_schema_version",
    "run_id",
    "run_started_at",
    "session_id",
    "operator",
    "hostname",
    "invocation",
    "code",
    "frame",
    "contract",
    "prompts",
    "config_hash",
    "config_hash_excludes",
    "credentials",
    "model_ids",
)


def preserve_identity(
    existing: Mapping[str, Any], fresh: Mapping[str, Any]
) -> dict[str, Any]:
    """Keep the launching run's identity when a resume rewrites the manifest.

    ``run_started_at`` is the reason this exists: it is authoritative for wave
    classification (§5.5), and before this the planning manifest's timestamp was
    refreshed on every invocation — so a resumed run reported the *resume* moment
    as its start and would have been classified into whichever window that landed
    in. Everything else here follows the same rule for the same reason: it
    describes the launch, and a resume is not a new launch.

    Note what is deliberately *not* done: the resuming config's ``config_hash`` is
    not compared against the stored one. §4.1 asks for config drift to fail
    loudly, but ``dry_run`` and ``stop_after`` are part of the config snapshot and
    legitimately change between the documented dry-run-then-``--execute`` pair on
    one run id — so a literal hash comparison would refuse the flow the runbook
    prescribes. Drift detection stays where it already works, on the guarded key
    set in :func:`g3o.run.presweep.planning._assert_manifest_matches_on_resume`.
    """
    merged = dict(fresh)
    for key in IDENTITY_KEYS:
        if key in existing:
            merged[key] = existing[key]
    return merged


# ---------------------------------------------------------------------------
# The event log (§4.3)
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def read_last_seq(path: Path) -> int:
    """Highest ``seq`` already in an event log, or 0. Tolerates a torn last line.

    A crashed run's log can end mid-line (§4.3), and a resume still has to
    continue the sequence without a gap (loader invariant 2). So the file is read
    line by line and unparseable lines are skipped rather than fatal — the log is
    a record, and refusing to append to a damaged one would lose the rest of the
    run's history to protect a byte.
    """
    if not path.exists():
        return 0
    highest = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            seq = int(json.loads(line).get("seq") or 0)
        except (ValueError, AttributeError, TypeError):
            continue
        highest = max(highest, seq)
    return highest


def stages_done(run_dir: Path) -> list[str]:
    """Stage names with a ``.done`` marker, for the ``resume`` event's payload."""
    marker_dir = done_dir(run_dir)
    if not marker_dir.exists():
        return []
    return sorted(p.stem for p in marker_dir.glob("*.json"))


def chunks_rejoined(run_dir: Path, stages: Iterable[str]) -> list[str]:
    """``"<stage>:<chunk>"`` for every chunk in flight but not yet fetched."""
    out: list[str] = []
    for stage in stages:
        state = load_state(run_dir, stage)
        if not state:
            continue
        for key, entry in iter_chunks(state):
            if entry.get("batch_id") and not entry.get("fetched_at"):
                out.append(f"{stage}:{key}")
    return out


@dataclass
class StageSpan:
    """Handle for one stage's ``stage_started``/``stage_completed`` pair."""

    stage: str
    counts_in: int
    started: float = field(default_factory=time.monotonic)


class RunTelemetry:
    """One launch's manifest block and event log.

    Constructed by :func:`g3o.run.api.launch` and threaded explicitly to the
    emit sites, for the same reason credentials are (§3.2): a module global would
    make two concurrent launches write each other's telemetry. ``disabled()``
    returns a no-op instance so every call site can emit unconditionally — a
    caller that wants no telemetry (a direct ``run_presweep``, most tests) gets
    identical behaviour to the pre-spec pipeline, including a byte-identical
    manifest.
    """

    def __init__(
        self,
        *,
        session_id: str,
        invocation: str = "api",
        git: Any = None,
        credentials: ResolvedCredentials | None = None,
        run_started_at: str = "",
        enabled: bool = True,
    ) -> None:
        self.session_id = session_id
        self.invocation = invocation
        self.git = git
        self.credentials = credentials
        self.run_started_at = run_started_at
        self.enabled = enabled
        self.git_sha = getattr(git, "sha", None)
        self.manifest_block: dict[str, Any] | None = None
        self.run_id: str | None = None
        self.events_path: Path | None = None
        self._seq = 0
        self._last_ts: datetime | None = None
        self._run_started = time.monotonic()

    @classmethod
    def disabled(cls) -> RunTelemetry:
        return cls(session_id="", enabled=False)

    def manifest_block_for(
        self,
        config: Any,
        sample: list[dict[str, Any]],
        *,
        config_snapshot: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Complete the §4.1 block, which needs the drawn sample and the snapshot.

        Called from ``plan_run``: the launch context (session, git, credentials,
        start time) is fixed when this object is constructed, but the master build
        id comes from the sample and ``config_hash`` from the stored snapshot, so
        the block can only be finished once the sample is drawn. Still before any
        spend, which is the property §4.1 actually requires.
        """
        if self.credentials is None:
            raise RuntimeError(
                "RunTelemetry.manifest_block_for needs resolved credentials; "
                "launch() supplies them (spec §3.2/§4.1)."
            )
        self.manifest_block = build_manifest_block(
            run_id=config.run_id,
            run_started_at=self.run_started_at,
            session_id=self.session_id,
            invocation=self.invocation,
            git=self.git,
            config_snapshot=config_snapshot,
            credentials=self.credentials,
            model=config.model,
            sample=sample,
        )
        return self.manifest_block

    # -- lifecycle ---------------------------------------------------------

    def open(self, run_dir: Path, run_id: str, *, resumed: bool) -> None:
        """Bind to a run directory and emit ``run_launched`` or ``resume``.

        Called after the manifest exists, which is what makes ``run_launched``'s
        position in the log meaningful: every event in the file post-dates a
        readable record of what produced it.
        """
        if not self.enabled:
            return
        self.run_id = run_id
        self.events_path = run_dir / EVENTS_FILENAME
        self._seq = read_last_seq(self.events_path)
        block = self.manifest_block or {}
        if resumed:
            done = stages_done(run_dir)
            self.emit(
                "resume",
                stages_done=done,
                chunks_rejoined=chunks_rejoined(run_dir, _pending_stages(run_dir)),
                key_fingerprint=(
                    (block.get("credentials") or {}).get("openai", {}).get("fingerprint")
                ),
            )
        else:
            self.emit(
                "run_launched",
                invocation=block.get("invocation"),
                config_hash=block.get("config_hash"),
            )

    def emit(self, event: str, *, stage: str | None = None, **payload: Any) -> None:
        """Append one event. Never raises (§4.4).

        A telemetry write that failed loudly would let the *record* abort the
        *measurement*, which is backwards: the run is the thing worth protecting.
        So every failure here becomes a warning, and a run whose log stops early
        is read as abnormally terminated (loader invariant 5) rather than as fine.
        """
        if not self.enabled or self.events_path is None:
            return
        try:
            self._seq += 1
            moment = _utc_now()
            # Non-decreasing ts (loader invariant 3). A backwards clock step —
            # an NTP correction mid-run — would otherwise break an invariant the
            # backend was told it could rely on. Durations are measured from a
            # monotonic clock, so clamping the label cannot distort them.
            if self._last_ts is not None and moment < self._last_ts:
                moment = self._last_ts
            self._last_ts = moment
            record: dict[str, Any] = {
                "ts": _iso(moment),
                "run_id": self.run_id,
                "session_id": self.session_id,
                "git_sha": self.git_sha,
                "seq": self._seq,
                "event": event,
            }
            if stage is not None:
                record["stage"] = stage
            record["payload"] = payload
            line = json.dumps(record, ensure_ascii=False) + "\n"
            with open(self.events_path, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
        except Exception:  # noqa: BLE001 — telemetry never aborts a run (§4.4)
            logger.warning(
                "telemetry: failed to emit %r for run %s (non-fatal)",
                event, self.run_id, exc_info=True,
            )

    # -- stage spans -------------------------------------------------------

    def stage_start(self, name: str, *, counts_in: int) -> StageSpan:
        """Emit ``stage_started`` and return the handle ``stage_end`` needs."""
        self.emit("stage_started", stage=name, counts_in=counts_in)
        return StageSpan(stage=name, counts_in=counts_in)

    def stage_end(
        self, span: StageSpan, *, counts_out: int | None = None, **extras: Any
    ) -> None:
        """Emit ``stage_completed`` for a stage that finished cleanly.

        A start/end pair rather than a context manager, deliberately: wrapping the
        orchestrator's stage calls in ``with`` blocks would reindent the whole
        dispatch body, and a reindent is a poor thing to hide a telemetry change
        inside. The exception path lands in the same place either way — a stage
        that raises never reaches here, so the log shows a stage that started and
        never completed, which is what happened, and ``run_failed`` names the
        cause once.
        """
        self.emit(
            "stage_completed",
            stage=span.stage,
            counts_in=span.counts_in,
            counts_out=counts_out,
            wall_seconds=round(time.monotonic() - span.started, 1),
            **extras,
        )

    # -- terminal events ---------------------------------------------------

    def run_completed(self, *, stop_after: str) -> None:
        self.emit(
            "run_completed",
            outcome="completed",
            stop_after=stop_after,
            wall_seconds=self._wall(),
        )

    def run_stopped(self, *, stop_after: str, reason: str) -> None:
        self.emit(
            "run_stopped",
            outcome="stopped",
            stop_after=stop_after,
            reason=reason,
            wall_seconds=self._wall(),
        )

    def run_failed(self, exc: BaseException, *, stop_after: str) -> None:
        """The event §1.5 requires before every post-manifest raise.

        ``error_message`` is ``str(exc)``. Exceptions in this pipeline are written
        to name variables and paths rather than values — and §3.3 keeps key
        material out of them — so this stays safe to record; the secrecy test
        greps a full run tree, this file included.
        """
        self.emit(
            "run_failed",
            outcome="failed",
            stop_after=stop_after,
            error_class=type(exc).__name__,
            error_message=str(exc),
            wall_seconds=self._wall(),
        )

    def _wall(self) -> float:
        return round(time.monotonic() - self._run_started, 1)


def _pending_stages(run_dir: Path) -> list[str]:
    """Stages with an active state file — the ones a resume could rejoin."""
    active = state_dir(run_dir)
    if not active.exists():
        return []
    return sorted(p.stem for p in active.glob("*.json"))


#: Shared no-op instance for call sites that were given no telemetry.
NO_TELEMETRY = RunTelemetry.disabled()


__all__ = [
    "CONFIG_HASH_EXCLUDES",
    "EVENTS_FILENAME",
    "IDENTITY_KEYS",
    "MANIFEST_FILENAME",
    "MANIFEST_SCHEMA_VERSION",
    "NO_TELEMETRY",
    "PROMPT_ASSETS",
    "RunTelemetry",
    "StageSpan",
    "build_manifest_block",
    "chunks_rejoined",
    "config_hash",
    "file_sha256",
    "master_build_id",
    "operator",
    "preserve_identity",
    "prompt_hashes",
    "read_last_seq",
    "stages_done",
]
