"""Leg 3 — load a finished run into the database, and say honestly what happened.

The failure mode this leg exists to prevent is named in the Item 3 brief: *"a
green print over a rolled-back load is the failure mode that burned us in
``--smoke``"*. So nothing here summarises the loader. ``scripts/ingest.py`` in the
``g3o-api`` checkout is the authority on whether a load is green — it has a
policy for that (v4: *strict by default, explicitly overridable, never silent*)
and it encodes it in an exit code:

===  ===================================================================
 0   loaded, and every strict check passed
 1   loaded + committed + reported, and a strict check FAILED — "not green",
     not "not run": the rows and the quarantine reports are in the database
 2   aborted on a contract violation; **nothing committed**
===  ===================================================================

This leg passes that exit code through unchanged, parses the counts the loader
prints, and independently counts the quarantine CSVs the loader wrote. Three
rules keep the report honest:

* **A failed parse is reported as a failed parse.** If the loader's output shape
  changes, :attr:`IngestCounts.parsed` goes False and the counts read "unknown".
  Reporting zero quarantined because the regex missed is the exact defect this
  module is written against, and zero is the most dangerous possible default.
* **Green requires three things**, not one: exit 0, *and* rows actually loaded,
  *and* nothing quarantined. A load that inserts nothing exits 0 under
  ``--institutions-only``; that is a registry load, not a findings load, and it
  is not green.
* **The gate is the run's state, not the operator's intent.** A run that failed
  or was killed is refused before the loader is invoked
  (:attr:`g3o.run.orchestrate.status.RunStatus.publishable`). That refusal is the
  mechanism behind the joint gate's "an induced failure publishes nothing" — it
  is a property of this function, not a step someone remembers.

**Seam CLOSED, 2026-08-17.** This leg was written against the wave-keyed loader
(``--wave-id``, schema v0.4), with a note that schema v0.5 would replace it and
that the change would land in one place. That schema landed as **v0.6** —
run-keyed facts and ex-post wave windows — in ``g3o-api`` PR #3, and the change
did land in one place, :func:`build_argv`, plus the repo the loader is fetched
from. Two things moved:

* ``--wave-id`` is **gone from the loader** and is replaced by ``--run-dir``
  (which the loader reads ``manifest.json`` and ``events.jsonl`` from) and
  ``--frame-id`` (the master build the run sampled from). ``--frame-id`` is
  required while the manifest's ``frame`` block is null, which it is on every
  run the pipeline emits today, so it is required here too rather than being
  inferred from a manifest field that is reliably ``None``.
* The loader's canonical home is **``g3o-api``**, not ``g3o-website``. It was
  never in ``g3o-website``; this leg was written before the split settled.

Wave membership is no longer an argument to the load at all. A run belongs to a
wave iff its ``run_started_at`` falls inside a ``g3o.wave_windows`` span, which
is a property of the database and a PI act, not of the invocation. That is why
nothing here takes a wave any more.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from g3o.common.credentials import fingerprint
from g3o.run.orchestrate.status import (
    RunStatus,
    orchestrator_dir,
    record_leg,
    run_status,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

#: Where the pinned ``g3o-api`` checkout is, if not passed explicitly. This was
#: ``G3O_WEBSITE_REPO`` until 2026-08-17; the loader has always lived in
#: ``g3o-api`` and the old name pointed this leg at a repo that does not contain
#: it. No alias is kept: the leg had never completed a load under the old name,
#: so there is nothing in the field to stay compatible with.
LOADER_REPO_ENV_VAR = "G3O_API_REPO"
DSN_ENV_VAR = "DATABASE_URL"

INGEST_SCRIPT_RELPATH = Path("scripts") / "ingest.py"
INGEST_LOG_FILENAME = "ingest.log"
INGEST_REPORTS_DIRNAME = "ingest_reports"

#: Stage-7 outputs, by glob. Versioned ``v{N}`` by ``g3o.persist.writer``, so the
#: highest version present wins rather than a pinned filename.
ACTIVITIES_GLOB = "g3o_activities_v*.csv"
SOURCES_GLOB = "g3o_activity_sources_v*.csv"

EXIT_OK = 0
EXIT_STRICT_FAILURE = 1
EXIT_ABORT = 2

#: Shortest bare password :func:`redact_dsn` will search a log for. Below this a
#: "password" is a substring of ordinary English, and replacing it does more
#: damage to the log than it does good to the secret.
MIN_REDACTABLE_SECRET = 8

_N = r"([\d,]+)"
_RE_INSTITUTIONS = re.compile(rf"upserted {_N} institutions")
_RE_FINDINGS = re.compile(
    rf"upserted {_N} findings \({_N} quarantined, {_N} sweep_uid derived\)"
)
_RE_EVIDENCE = re.compile(
    rf"upserted {_N} evidence \({_N} quarantined, {_N} sweep_uid derived\)"
)
_RE_NSOURCES_OK = re.compile(r"n_sources check:\s*OK")
_RE_NSOURCES_BAD = re.compile(rf"n_sources check:\s*{_N} mismatched findings")
_RE_STRICT_FAIL = re.compile(r"^\s*FAIL \d+\.\s*(.+)$", re.MULTILINE)


class IngestError(RuntimeError):
    """The load could not be attempted. Nothing was sent to the database."""


def _int(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw.replace(",", ""))
    except ValueError:
        return None


@dataclass(frozen=True)
class IngestCounts:
    """What the loader reported, or an explicit admission that we could not tell.

    Every count is ``None`` when the corresponding line was not found. ``None``
    and ``0`` mean different things here and the difference is the whole point:
    ``0`` is "the loader said zero", ``None`` is "the loader did not say".
    """

    institutions: int | None = None
    findings_loaded: int | None = None
    findings_quarantined: int | None = None
    findings_derived: int | None = None
    evidence_loaded: int | None = None
    evidence_quarantined: int | None = None
    evidence_derived: int | None = None
    n_sources_mismatched: int | None = None
    strict_failures: tuple[str, ...] = ()

    @property
    def parsed(self) -> bool:
        """Did the findings-side lines parse at all?

        The findings pair is what makes a load a *data* load; the institutions
        line alone is a registry load. If neither findings line was found, this
        report knows nothing about the thing that matters.
        """
        return self.findings_loaded is not None and self.evidence_loaded is not None

    @property
    def total_loaded(self) -> int | None:
        if self.findings_loaded is None or self.evidence_loaded is None:
            return None
        return self.findings_loaded + self.evidence_loaded

    @property
    def total_quarantined(self) -> int | None:
        if self.findings_quarantined is None or self.evidence_quarantined is None:
            return None
        return self.findings_quarantined + self.evidence_quarantined

    def to_dict(self) -> dict[str, Any]:
        return {
            "parsed": self.parsed,
            "institutions": self.institutions,
            "findings_loaded": self.findings_loaded,
            "findings_quarantined": self.findings_quarantined,
            "findings_derived": self.findings_derived,
            "evidence_loaded": self.evidence_loaded,
            "evidence_quarantined": self.evidence_quarantined,
            "evidence_derived": self.evidence_derived,
            "n_sources_mismatched": self.n_sources_mismatched,
            "total_loaded": self.total_loaded,
            "total_quarantined": self.total_quarantined,
            "strict_failures": list(self.strict_failures),
        }


def parse_ingest_output(text: str) -> IngestCounts:
    """Read the loader's own printed report. Never guesses a missing number."""
    inst = _RE_INSTITUTIONS.search(text)
    find = _RE_FINDINGS.search(text)
    evid = _RE_EVIDENCE.search(text)
    bad = _RE_NSOURCES_BAD.search(text)
    mismatched = _int(bad.group(1)) if bad else (0 if _RE_NSOURCES_OK.search(text) else None)
    return IngestCounts(
        institutions=_int(inst.group(1)) if inst else None,
        findings_loaded=_int(find.group(1)) if find else None,
        findings_quarantined=_int(find.group(2)) if find else None,
        findings_derived=_int(find.group(3)) if find else None,
        evidence_loaded=_int(evid.group(1)) if evid else None,
        evidence_quarantined=_int(evid.group(2)) if evid else None,
        evidence_derived=_int(evid.group(3)) if evid else None,
        n_sources_mismatched=mismatched,
        strict_failures=tuple(m.strip() for m in _RE_STRICT_FAIL.findall(text)),
    )


@dataclass(frozen=True)
class IngestResult:
    """One invocation of the loader, reported without interpretation."""

    run_id: str
    exit_code: int
    argv: tuple[str, ...]
    counts: IngestCounts
    quarantine_reports: tuple[Path, ...] = ()
    quarantine_rows_on_disk: int | None = None
    log_path: Path | None = None
    loader: dict[str, Any] = field(default_factory=dict)
    database: dict[str, Any] = field(default_factory=dict)

    @property
    def green(self) -> bool:
        """Exit 0, rows loaded, nothing quarantined — all three, or not green."""
        return (
            self.exit_code == EXIT_OK
            and self.counts.parsed
            and bool(self.counts.total_loaded)
            and self.counts.total_quarantined == 0
        )

    @property
    def verdict(self) -> str:
        """One sentence an operator can act on, and never a flattering one."""
        if self.exit_code == EXIT_ABORT:
            return (
                "ABORTED — the loader refused a contract violation before "
                "committing. Nothing was written to the database."
            )
        if self.exit_code == EXIT_STRICT_FAILURE:
            detail = "; ".join(self.counts.strict_failures) or "see the log"
            return (
                f"NOT GREEN — the load committed and a strict check failed: {detail}. "
                f"The rows and the quarantine reports are in the database; this is a "
                f"run that completed and did not pass."
            )
        if self.exit_code != EXIT_OK:
            return f"UNKNOWN — the loader exited {self.exit_code}, which is not a documented code."
        if not self.counts.parsed:
            return (
                "EXIT 0, COUNTS UNKNOWN — the loader's output did not match the "
                "expected shape, so this report cannot say how many rows loaded or "
                "quarantined. Read the log before treating this as green."
            )
        if not self.counts.total_loaded:
            return (
                "EXIT 0, NOTHING LOADED — zero findings and zero evidence rows were "
                "inserted. A registry-only or empty load is not a findings load."
            )
        if self.counts.total_quarantined:
            return (
                f"EXIT 0 with {self.counts.total_quarantined} quarantined row(s) — the "
                f"loader's threshold allowed them. Read the quarantine reports."
            )
        return (
            f"GREEN — {self.counts.findings_loaded} findings and "
            f"{self.counts.evidence_loaded} evidence rows loaded, none quarantined."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "exit_code": self.exit_code,
            "green": self.green,
            "verdict": self.verdict,
            "argv": list(self.argv),
            "counts": self.counts.to_dict(),
            "quarantine_reports": [str(p) for p in self.quarantine_reports],
            "quarantine_rows_on_disk": self.quarantine_rows_on_disk,
            "log_path": str(self.log_path) if self.log_path else None,
            "loader": self.loader,
            "database": self.database,
        }


# ---------------------------------------------------------------------------
# Locating the pieces
# ---------------------------------------------------------------------------


def resolve_loader_repo(explicit: Path | None = None) -> Path:
    """The pinned ``g3o-api`` checkout that owns ``scripts/ingest.py``."""
    raw = explicit or os.environ.get(LOADER_REPO_ENV_VAR)
    if not raw:
        raise IngestError(
            f"no g3o-api checkout given. Pass --loader-repo or set "
            f"{LOADER_REPO_ENV_VAR}. The loader is deliberately invoked from a "
            f"pinned checkout rather than vendored here: it is the backend's code, "
            f"on the backend's release cadence."
        )
    repo = Path(raw).expanduser().resolve()
    script = repo / INGEST_SCRIPT_RELPATH
    if not script.is_file():
        raise IngestError(f"{script} does not exist — {repo} is not a g3o-api checkout.")
    return repo


def loader_provenance(repo: Path) -> dict[str, Any]:
    """Which loader code ran: commit, dirtiness, path.

    Recorded on every ingest because "which ingest.py?" is otherwise
    unanswerable after the fact, and the loader's behaviour has changed
    materially four times (v1→v4) in the weeks before this sprint.
    """
    out: dict[str, Any] = {"repo": str(repo), "script": str(repo / INGEST_SCRIPT_RELPATH)}
    git = shutil.which("git")
    if not git:
        out["git_sha"] = None
        out["error"] = "git not on PATH"
        return out
    try:
        sha = subprocess.run(
            [git, "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
            timeout=30, check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                [git, "status", "--porcelain"], cwd=repo, capture_output=True,
                text=True, timeout=30, check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError) as exc:
        out["git_sha"] = None
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    out["git_sha"] = sha
    out["git_dirty"] = dirty
    return out


def describe_dsn(dsn: str) -> dict[str, Any]:
    """A recordable description of the database, with no credentials in it.

    A Neon DSN carries a password in its userinfo, so the DSN itself can never be
    logged, recorded, or archived (§3.3's rule, applied to the one secret this
    leg handles). What is recorded is the part that identifies *which* database —
    scheme, host, path — plus ``sha256(dsn)[:8]``, which is enough to tell "the
    branch DSN" from "the production DSN" in a run record and useless for
    reaching either.
    """
    parts = urlsplit(dsn)
    return {
        "scheme": parts.scheme or None,
        "host": parts.hostname,
        "port": parts.port,
        "database": (parts.path or "").lstrip("/") or None,
        "fingerprint": fingerprint(dsn),
    }


def redact_dsn(text: str, dsn: str) -> str:
    """Remove the DSN and its password from captured loader output.

    Defensive, because the log this protects does not stay on the droplet: the
    archive leg uploads ``_orchestrator/ingest.log`` to Spaces and the PI pulls it
    into Drive. Today's loader never echoes the DSN — but it is not this repo's
    code, a psycopg exception can carry a connection string, and a secret that
    reaches an archived file is a secret that has to be rotated rather than
    edited out. Cheap here, expensive to retrofit.

    Both the whole DSN and the bare password are replaced, since an error message
    may quote either — but the bare-password pass only fires for a password long
    enough to be one. A one- or two-character "password" appears inside ordinary
    words, and blanket-replacing it would shred the log (``upserted`` →
    ``u<redacted>serted``) to protect a string that is not a secret. Found by the
    test whose fixture DSN had the password ``p``.

    Redaction is applied on the way to **disk only**. The counts are parsed from
    the raw output, so a password that happens to occur inside a number can never
    change what this leg reports.
    """
    if not dsn:
        return text
    out = text.replace(dsn, "<DATABASE_URL redacted>")
    password = urlsplit(dsn).password
    if password and len(password) >= MIN_REDACTABLE_SECRET:
        out = out.replace(password, "<redacted>")
    return out


def find_stage7_csvs(run_dir: Path) -> tuple[Path, Path]:
    """The run's activities and sources CSVs, highest ``v{N}`` when several exist."""
    final = run_dir / "final"
    found: list[Path] = []
    for glob in (ACTIVITIES_GLOB, SOURCES_GLOB):
        matches = sorted(final.glob(glob))
        if not matches:
            raise IngestError(
                f"{final / glob} matched nothing. Stage 7 has not run for this run "
                f"(`python -m g3o persist --run-dir {run_dir} --run-id <id>`), so "
                f"there is nothing to load."
            )
        found.append(matches[-1])
    return found[0], found[1]


def master_csv_from_manifest(run_dir: Path) -> Path | None:
    """The master the run sampled from, as the run itself recorded it.

    Read from the manifest's config snapshot rather than taken as an argument, so
    the registry loaded alongside a run's findings is the frame that run drew
    from — not whatever master happens to be on the droplet today.
    """
    from g3o.run.orchestrate.status import MANIFEST_FILENAME, read_json

    manifest = read_json(run_dir / MANIFEST_FILENAME) or {}
    raw = (manifest.get("config") or {}).get("master_csv")
    return Path(str(raw)) if raw else None


def build_argv(
    repo: Path,
    *,
    run_dir: Path,
    frame_id: str,
    master: Path,
    activities: Path,
    sources: Path,
    report_dir: Path,
    extra_args: tuple[str, ...] = (),
    python: str | None = None,
) -> tuple[str, ...]:
    """The loader invocation. The one place a schema change moves this leg.

    v0.6 (2026-08-17): ``--wave-id`` is gone. ``--run-dir`` gives the loader the
    manifest and the event log it keys facts by; ``--frame-id`` names the master
    build, and is required while the manifest's ``frame`` block is null.
    """
    return (
        python or sys.executable,
        str(repo / INGEST_SCRIPT_RELPATH),
        "--run-dir", str(run_dir),
        "--frame-id", frame_id,
        "--master", str(master),
        "--activities", str(activities),
        "--sources", str(sources),
        "--report-dir", str(report_dir),
        *extra_args,
    )


def _count_csv_rows(path: Path) -> int:
    """Data rows in a CSV — lines minus the header, or 0 for an unreadable file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    lines = [line for line in text.splitlines() if line.strip()]
    return max(len(lines) - 1, 0)


# ---------------------------------------------------------------------------
# The leg
# ---------------------------------------------------------------------------


def ingest_run(
    runs_dir: Path,
    run_id: str,
    *,
    frame_id: str,
    loader_repo: Path | None = None,
    master_csv: Path | None = None,
    extra_args: tuple[str, ...] = (),
    dsn: str | None = None,
    expect_loader_sha: str | None = None,
    force: bool = False,
    status: RunStatus | None = None,
) -> IngestResult:
    """Load one finished run, and report what the loader actually did.

    Refuses a run that is not :attr:`~g3o.run.orchestrate.status.RunStatus.publishable`
    — a failed, killed, still-running, or dry run — unless ``force`` is set. That
    refusal is deliberately placed *before* the loader is invoked rather than
    after: a partial run's Stage-7 CSVs are real files with real rows, and the
    loader has no way to know they came from a sweep that died at Stage 5.

    ``force`` exists because a human occasionally has to load a known-partial run
    on purpose; it is recorded in the leg record, and it never suppresses any of
    the loader's own checks.
    """
    run_dir = Path(runs_dir) / run_id
    state = status or run_status(Path(runs_dir), run_id)
    if not state.publishable and not force:
        raise IngestError(
            f"refusing to ingest run {run_id}: its state is {state.state!r}"
            + (f" ({state.failure.get('error_message')})" if state.failure else "")
            + ". Only a completed, non-dry run has a full Stage-7 tree to load. "
            "A partial run's CSVs are real rows from an incomplete sweep, and "
            "nothing downstream could tell them apart afterwards. Pass --force to "
            "load one deliberately."
        )

    repo = resolve_loader_repo(loader_repo)
    provenance = loader_provenance(repo)
    if expect_loader_sha and provenance.get("git_sha") != expect_loader_sha:
        raise IngestError(
            f"the g3o-api checkout at {repo} is at "
            f"{provenance.get('git_sha')!r}, not the pinned {expect_loader_sha!r}. "
            f"Refusing: which loader ran is part of the run record."
        )

    resolved_dsn = dsn or os.environ.get(DSN_ENV_VAR)
    if not resolved_dsn:
        raise IngestError(
            f"{DSN_ENV_VAR} is unset. The loader reads it directly; it is never "
            f"passed on the command line, where it would land in `ps` and in the "
            f"shell history along with the database password."
        )

    master = master_csv or master_csv_from_manifest(run_dir)
    if master is None:
        raise IngestError(
            f"no master CSV: {run_dir}/manifest.json records none and none was "
            f"passed. The registry loaded with a run's findings must be the frame "
            f"that run sampled from."
        )
    if not Path(master).is_file():
        raise IngestError(f"master CSV not found: {master}")

    activities, sources = find_stage7_csvs(run_dir)
    odir = orchestrator_dir(run_dir)
    report_dir = odir / INGEST_REPORTS_DIRNAME
    report_dir.mkdir(parents=True, exist_ok=True)
    log_path = odir / INGEST_LOG_FILENAME

    argv = build_argv(
        repo,
        run_dir=run_dir,
        frame_id=frame_id,
        master=Path(master),
        activities=activities,
        sources=sources,
        report_dir=report_dir,
        extra_args=extra_args,
    )
    started_at = utc_now_iso()
    before = {p for p in report_dir.glob("*.csv")}

    env = {**os.environ, DSN_ENV_VAR: resolved_dsn}
    logger.info("ingest: %s", " ".join(argv[:2]))
    proc = subprocess.run(  # noqa: S603 - argv built above, never from user input
        list(argv), cwd=repo, env=env, capture_output=True, text=True, check=False
    )
    # Parsed from the raw output, redacted only on the way to disk: a redaction
    # that ran first could rewrite a count and change what this leg reports.
    output = (proc.stdout or "") + (proc.stderr or "")
    counts = parse_ingest_output(output)
    try:
        log_path.write_text(
            f"$ {' '.join(argv)}\n(exit {proc.returncode})\n\n"
            f"{redact_dsn(output, resolved_dsn)}",
            encoding="utf-8",
        )
    except OSError:
        logger.warning("could not write %s (non-fatal)", log_path, exc_info=True)

    fresh = sorted(p for p in report_dir.glob("*.csv") if p not in before)
    result = IngestResult(
        run_id=run_id,
        exit_code=proc.returncode,
        argv=argv,
        counts=counts,
        quarantine_reports=tuple(fresh),
        quarantine_rows_on_disk=sum(_count_csv_rows(p) for p in fresh) if fresh else 0,
        log_path=log_path,
        loader=provenance,
        database=describe_dsn(resolved_dsn),
    )
    record_leg(
        run_dir,
        "ingest",
        outcome="green" if result.green else "not-green",
        started_at=started_at,
        forced=force,
        frame_id=frame_id,
        **result.to_dict(),
    )
    return result


def render_ingest(result: IngestResult) -> str:
    """Operator-facing rendering. The verdict first, because it is the answer."""
    counts = result.counts
    lines = [
        f"Ingest — run {result.run_id}",
        f"  {result.verdict}",
        "",
        f"  loader exit code   : {result.exit_code}",
        f"  loader commit      : {result.loader.get('git_sha') or 'unknown'}"
        + (" (DIRTY)" if result.loader.get("git_dirty") else ""),
        f"  database           : {result.database.get('host')}/"
        f"{result.database.get('database')} (dsn fp {result.database.get('fingerprint')})",
    ]
    if counts.parsed:
        lines += [
            f"  institutions       : {counts.institutions}",
            f"  findings           : {counts.findings_loaded} loaded, "
            f"{counts.findings_quarantined} quarantined, {counts.findings_derived} derived",
            f"  evidence           : {counts.evidence_loaded} loaded, "
            f"{counts.evidence_quarantined} quarantined, {counts.evidence_derived} derived",
            f"  n_sources mismatch : {counts.n_sources_mismatched}",
        ]
    else:
        lines.append(
            "  counts             : UNPARSEABLE — the loader's output did not match "
            "the expected shape. Read the log; do not read this as zero."
        )
    if result.quarantine_reports:
        lines.append(
            f"  quarantine reports : {len(result.quarantine_reports)} file(s), "
            f"{result.quarantine_rows_on_disk} row(s) on disk"
        )
        for path in result.quarantine_reports:
            lines.append(f"      {path}")
    disk = result.quarantine_rows_on_disk
    parsed_total = counts.total_quarantined
    if parsed_total is not None and disk is not None and parsed_total != disk:
        lines.append(
            f"  ! the loader reported {parsed_total} quarantined row(s) and wrote "
            f"{disk} to disk. They should match; investigate before publishing."
        )
    for failure in counts.strict_failures:
        lines.append(f"  FAIL {failure}")
    lines.append(f"  log                : {result.log_path}")
    return "\n".join(lines)


__all__ = [
    "ACTIVITIES_GLOB",
    "DSN_ENV_VAR",
    "EXIT_ABORT",
    "EXIT_OK",
    "EXIT_STRICT_FAILURE",
    "SOURCES_GLOB",
    "LOADER_REPO_ENV_VAR",
    "IngestCounts",
    "IngestError",
    "IngestResult",
    "build_argv",
    "describe_dsn",
    "find_stage7_csvs",
    "ingest_run",
    "loader_provenance",
    "master_csv_from_manifest",
    "parse_ingest_output",
    "render_ingest",
    "resolve_loader_repo",
]
