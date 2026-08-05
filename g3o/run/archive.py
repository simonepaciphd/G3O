"""Retention: tar a completed run's institution shards (storage layout v2).

Spec: ``docs/storage-layout-v2.md`` §A2 (Phase 3).

A finished run's institution tree is the storage overhang — at the full frame
roughly 20M files across 256 shards. Once the run is *complete* (Stage-7 CSVs
written, every stage marked done, run-level reports generated) nothing reads
that tree again, so it is tarred one shard at a time::

    runs/<run_id>/archive/institutions/<shard>.tar

Plain tar, no outer compression: the bytes that matter are already gzipped by
:mod:`g3o.common.artifact_io`, and a second pass costs CPU for ~0 gain
(spec §A2).

Three properties make the delete path safe, and each is why this module is
shaped the way it is:

- **Verification precedes every delete.** A shard's tar is re-opened and its
  member count and total member bytes compared against a *fresh* walk of the
  source — not against numbers remembered from the write. A mismatch aborts
  the whole run, deletes nothing, and leaves the bad tar renamed
  ``<shard>.tar.FAILED`` so it is never mistaken for a good archive on the
  next pass.
- **Dry-run is the default.** Without ``apply=True`` nothing is written and
  nothing is deleted; the caller gets the plan and exits. Deleting data
  requires saying so.
- **Tars are written atomically.** A tar lands on a same-directory temp file
  and swaps in via :func:`os.replace`, mirroring
  :func:`g3o.common.artifact_io.write_artifact`. An interrupted archive
  therefore never leaves a truncated ``<shard>.tar`` behind, which is what
  lets :func:`archive_run` treat an *existing* tar that fails verification as
  a real anomaly (abort) rather than as expected partial work (silently
  rebuild).

Run-level files — ``manifest.json``, ``_state/``, ``_attrition.jsonl``,
``final/``, the reports — are never archived. They stay live, and a completed
run's live tree is those files plus at most 256 tars.

Restore is deliberately not implemented (spec §A2); it is one documented
``tar -xf`` in ``docs/operations.md``.
"""

from __future__ import annotations

import os
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path

from g3o.common.paths import institutions_root, require_layout
from g3o.common.run_state import done_path

# Imported from the config module rather than the ``g3o.run.presweep`` package
# root: it is the same tuple object, but the package ``__init__`` pulls in the
# whole orchestrator (and through it every stage runner and API client), which
# an archive of an already-finished run has no use for.
from g3o.run.presweep.config import STAGES

ARCHIVE_DIRNAME = "archive"
INSTITUTIONS_DIRNAME = "institutions"
TAR_SUFFIX = ".tar"

#: Suffix a tar that failed verification is renamed to. Matches neither the
#: ``<shard>.tar`` lookup nor the shard glob, so a failed tar cannot be picked
#: up as a valid archive on a later pass — it has to be looked at by a human.
FAILED_SUFFIX = ".FAILED"

#: Stage-7 CSVs, by filename glob. Versioned (``v{N}``) by
#: :func:`g3o.persist.writer.write_run_csvs`, so the precondition matches on
#: the pattern rather than pinning a contract version this module does not own.
FINAL_CSV_GLOBS = (
    "g3o_activities_v*.csv",
    "g3o_activity_sources_v*.csv",
    "g3o_institution_summary_v*.csv",
)

#: Run-level reports that must exist before archival. ``run_summary.json`` is
#: written by :func:`g3o.report.run_summary.write_run_summary`;
#: ``_health_report.json`` by the ``presweep-report`` subcommand. Both read the
#: live institution tree, so archiving before they run would silently produce
#: an empty report against an archived run.
REQUIRED_REPORTS = ("run_summary.json", "_health_report.json")

#: Tar format, pinned rather than left at :mod:`tarfile`'s default.
#:
#: The default is ``PAX_FORMAT``, which emits a *per-member* extended header
#: (an extra 1024 bytes: one header block plus one data block) in order to
#: record sub-second mtimes. Measured on a 6-file fixture shard: 20480 bytes
#: under PAX against 10240 under GNU. At the full-frame envelope of ~20M
#: members that is roughly 20 GB of pure padding — in the phase whose entire
#: purpose is cutting the storage overhang.
#:
#: ``GNU_FORMAT`` rather than ``USTAR_FORMAT`` because ustar caps a member path
#: at 100 characters (256 with the prefix split) and the institution-key spec
#: may lengthen ``inst_id``; GNU has no practical path limit. GNU tar, bsdtar
#: (which is what ``tar.exe`` is on Windows), Python, and 7-zip all read it, so
#: the documented restore command is unaffected.
#:
#: Sub-second mtime precision is the only thing given up, and nothing reads it:
#: verification compares member count and bytes, never timestamps.
TAR_FORMAT = tarfile.GNU_FORMAT

_TAR_BLOCK = 512
_TAR_RECORD = 10240  # tarfile pads the archive out to this multiple on close.
_SPEC_REF = "docs/storage-layout-v2.md"


class ArchiveError(RuntimeError):
    """Base for every refusal this module raises."""


class PreconditionError(ArchiveError):
    """A run is not in a state where archival is the correct next operation."""


class VerificationError(ArchiveError):
    """A tar did not match its source; nothing was deleted."""


@dataclass(frozen=True)
class SourceStat:
    """A fresh walk of one shard directory."""

    n_files: int
    n_bytes: int
    n_dirs: int


@dataclass(frozen=True)
class TarStat:
    """What a tar actually contains, read back from the tar itself."""

    n_files: int
    n_bytes: int


@dataclass(frozen=True)
class ShardPlan:
    """One shard's planned disposition."""

    shard: str
    source: Path
    tar_path: Path
    source_stat: SourceStat | None
    projected_tar_bytes: int
    #: ``"pending"``  — source present, no tar yet: tar it, verify, delete.
    #: ``"tarred"``   — source and tar both present (an interrupted apply, or a
    #:                  dry-run that already produced tars): verify, delete.
    #: ``"archived"`` — tar present, source gone: nothing left to do.
    state: str


@dataclass(frozen=True)
class ArchivePlan:
    run_dir: Path
    shards: tuple[ShardPlan, ...]

    @property
    def pending(self) -> tuple[ShardPlan, ...]:
        return tuple(s for s in self.shards if s.state != "archived")

    @property
    def n_files(self) -> int:
        return sum(s.source_stat.n_files for s in self.shards if s.source_stat)

    @property
    def n_bytes(self) -> int:
        return sum(s.source_stat.n_bytes for s in self.shards if s.source_stat)

    @property
    def projected_tar_bytes(self) -> int:
        return sum(s.projected_tar_bytes for s in self.shards)


@dataclass(frozen=True)
class ShardOutcome:
    shard: str
    tar_path: Path
    #: ``"archived"``  — tar written and verified this pass.
    #: ``"verified"``  — tar already existed and verified; not rewritten.
    #: ``"skipped"``   — already archived on an earlier pass; source gone.
    action: str
    deleted: bool
    tar_stat: TarStat | None


@dataclass(frozen=True)
class ArchiveResult:
    run_dir: Path
    applied: bool
    outcomes: tuple[ShardOutcome, ...]

    @property
    def n_deleted(self) -> int:
        return sum(1 for o in self.outcomes if o.deleted)


# --- Paths --------------------------------------------------------------------


def archive_root(run_dir: Path) -> Path:
    """``runs/<run_id>/archive/institutions`` — where the tars live."""
    return run_dir / ARCHIVE_DIRNAME / INSTITUTIONS_DIRNAME


def shard_tar_path(run_dir: Path, shard: str) -> Path:
    return archive_root(run_dir) / f"{shard}{TAR_SUFFIX}"


# --- Preconditions ------------------------------------------------------------


def _missing_final_csvs(run_dir: Path) -> list[str]:
    final_dir = run_dir / "final"
    if not final_dir.is_dir():
        return list(FINAL_CSV_GLOBS)
    return [g for g in FINAL_CSV_GLOBS if not any(final_dir.glob(g))]


def _missing_done_markers(run_dir: Path) -> list[str]:
    return [stage for stage in STAGES if not done_path(run_dir, stage).exists()]


def _missing_reports(run_dir: Path) -> list[str]:
    return [name for name in REQUIRED_REPORTS if not (run_dir / name).exists()]


def check_preconditions(run_dir: Path) -> None:
    """Refuse a run that is not finished (spec §A2).

    Archival is strictly the *last* operation on a run: it removes the tree
    that Stage 7 and every report read. All three conditions are checked and
    reported together rather than one at a time, so an operator fixing a
    half-finished run sees the whole gap in one pass.

    Raises:
        PreconditionError: on a missing Stage-7 CSV, a missing stage ``.done``
            marker, or a missing run-level report.
    """
    require_layout(run_dir)
    problems: list[str] = []

    missing_csvs = _missing_final_csvs(run_dir)
    if missing_csvs:
        problems.append(
            f"final/ is missing Stage-7 output(s): {', '.join(missing_csvs)}. "
            f"Run `python -m g3o persist --run-dir {run_dir}` first."
        )

    missing_done = _missing_done_markers(run_dir)
    if missing_done:
        problems.append(
            f"{len(missing_done)} of {len(STAGES)} stage(s) carry no _state/.done "
            f"marker: {', '.join(missing_done)}. The run is not complete; "
            f"archiving now would tar a partial tree."
        )

    missing_reports = _missing_reports(run_dir)
    if missing_reports:
        problems.append(
            f"run-level report(s) not written: {', '.join(missing_reports)}. "
            f"Reports read the live institution tree, so they must run before "
            f"archival, not after."
        )

    if problems:
        detail = "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, start=1))
        raise PreconditionError(
            f"Refusing to archive {run_dir} — it is not a completed run "
            f"({_SPEC_REF} §A2):\n{detail}"
        )


# --- Measurement --------------------------------------------------------------


def walk_shard(shard_dir: Path) -> SourceStat:
    """Fresh count of files, bytes, and directories under one shard.

    Deliberately re-walked at verification time rather than reused from the
    write: comparing a tar against numbers gathered while producing it would
    verify the bookkeeping, not the archive.
    """
    n_files = n_bytes = n_dirs = 0
    for dirpath, _dirnames, filenames in os.walk(shard_dir):
        n_dirs += 1  # os.walk visits every directory exactly once, root included
        for name in filenames:
            try:
                n_bytes += os.stat(os.path.join(dirpath, name)).st_size
            except OSError:
                # A file that vanished mid-walk is a mismatch, not a crash --
                # verification compares counts and will catch it.
                continue
            n_files += 1
    return SourceStat(n_files=n_files, n_bytes=n_bytes, n_dirs=n_dirs)


def read_tar_stat(tar_path: Path) -> TarStat:
    """Count regular-file members and their total size, from the tar itself.

    Directory members are excluded on both sides of the comparison (a
    directory entry carries no bytes, so including them would compare
    filesystem bookkeeping rather than archived content).

    Raises:
        VerificationError: when the tar cannot be opened or read as a tar.
    """
    n_files = n_bytes = 0
    try:
        with tarfile.open(tar_path, mode="r:") as tar:
            for member in tar:
                if member.isfile():
                    n_files += 1
                    n_bytes += member.size
    except (tarfile.TarError, OSError) as exc:
        raise VerificationError(f"{tar_path} could not be read as a tar: {exc}") from exc
    return TarStat(n_files=n_files, n_bytes=n_bytes)


def projected_tar_bytes(stat: SourceStat) -> int:
    """Estimated on-disk size of the tar for a shard with ``stat``.

    Every member costs a 512-byte header plus its data padded to a 512-byte
    boundary; the archive ends with a 1024-byte trailer and is padded out to a
    10240-byte record. This models :data:`TAR_FORMAT` (GNU) exactly, which is
    the other half of why that format is pinned — under the ``PAX_FORMAT``
    default the same model runs 2x under, and the dry-run number an operator
    uses to decide whether there is disk room would be worse than useless.

    Still an *estimate*, and labelled as one wherever it is printed: the
    per-file padding term is an average (half a block per file) rather than a
    per-file computation, since the caller has aggregate byte totals rather
    than a size list. ``test_projected_tar_size_is_close_to_actual`` pins the
    error at under one record per shard on a realistic tree.
    """
    # Data members, each header + padded payload. Byte totals are aggregate, so
    # per-file padding is approximated at half a block per file on average.
    payload = stat.n_bytes + (stat.n_files * _TAR_BLOCK // 2)
    headers = (stat.n_files + stat.n_dirs) * _TAR_BLOCK
    total = headers + payload + 2 * _TAR_BLOCK
    return -(-total // _TAR_RECORD) * _TAR_RECORD


# --- Planning -----------------------------------------------------------------


def _shard_names(run_dir: Path) -> list[str]:
    """Every shard the run knows about — on disk, already tarred, or both."""
    names: set[str] = set()
    root = institutions_root(run_dir)
    if root.is_dir():
        names.update(d.name for d in root.iterdir() if d.is_dir())
    tar_dir = archive_root(run_dir)
    if tar_dir.is_dir():
        names.update(p.name[: -len(TAR_SUFFIX)] for p in tar_dir.glob(f"*{TAR_SUFFIX}"))
    return sorted(names)


def plan_archive(run_dir: Path) -> ArchivePlan:
    """What archiving this run would do. Reads only; writes and deletes nothing."""
    shards: list[ShardPlan] = []
    for shard in _shard_names(run_dir):
        source = institutions_root(run_dir) / shard
        tar_path = shard_tar_path(run_dir, shard)
        if not source.is_dir():
            shards.append(
                ShardPlan(
                    shard=shard, source=source, tar_path=tar_path,
                    source_stat=None, projected_tar_bytes=0, state="archived",
                )
            )
            continue
        stat = walk_shard(source)
        shards.append(
            ShardPlan(
                shard=shard,
                source=source,
                tar_path=tar_path,
                source_stat=stat,
                projected_tar_bytes=projected_tar_bytes(stat),
                state="tarred" if tar_path.exists() else "pending",
            )
        )
    return ArchivePlan(run_dir=run_dir, shards=tuple(shards))


# --- Execution ----------------------------------------------------------------


def _write_tar(source: Path, tar_path: Path, shard: str) -> None:
    """Tar ``source`` to ``tar_path`` atomically, rooted at ``<shard>/``.

    The arcname root is the shard name, so the documented restore —
    ``tar -xf archive/institutions/<shard>.tar -C <run_dir>/institutions/`` —
    recreates ``institutions/<shard>/<inst_id>/...`` exactly where it was.
    """
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tar_path.with_name(f"{tar_path.name}.tmp.{os.getpid()}")
    try:
        with tarfile.open(tmp, mode="w:", format=TAR_FORMAT) as tar:
            tar.add(source, arcname=shard, recursive=True)
        os.replace(tmp, tar_path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _fail_tar(tar_path: Path) -> Path:
    """Rename a tar that failed verification aside, and say where it went."""
    dest = tar_path.with_name(tar_path.name + FAILED_SUFFIX)
    try:
        os.replace(tar_path, dest)
    except OSError:
        pass
    return dest


def verify_tar(tar_path: Path, source: Path) -> TarStat:
    """Compare a tar against a fresh walk of its source.

    Raises:
        VerificationError: on any mismatch in member count or total member
            bytes. The caller renames the tar aside and aborts; nothing is
            deleted on this path.
    """
    tar_stat = read_tar_stat(tar_path)
    src_stat = walk_shard(source)
    if (tar_stat.n_files, tar_stat.n_bytes) != (src_stat.n_files, src_stat.n_bytes):
        raise VerificationError(
            f"{tar_path} does not match its source {source}: tar holds "
            f"{tar_stat.n_files} file(s) / {tar_stat.n_bytes} byte(s), source walk "
            f"found {src_stat.n_files} file(s) / {src_stat.n_bytes} byte(s)."
        )
    return tar_stat


def archive_run(run_dir: Path, *, apply: bool = False) -> ArchiveResult:
    """Tar every institution shard; with ``apply``, delete each verified source.

    Preconditions are checked first and refuse loudly (:func:`check_preconditions`).

    Without ``apply`` this is a pure read: no tar is written, no directory is
    removed. The caller renders :func:`plan_archive` instead.

    With ``apply``, shards are processed one at a time and a source is removed
    only after its own tar has been re-opened and verified. The first
    verification failure aborts the whole run — shards already archived stay
    archived (they verified), the failing tar is renamed ``.FAILED``, and its
    source is left intact.

    Idempotent: a shard whose tar exists and verifies is not rewritten, and a
    shard whose source is already gone is skipped, so re-running after an
    interruption finishes the remainder.
    """
    check_preconditions(run_dir)
    plan = plan_archive(run_dir)
    if not apply:
        return ArchiveResult(run_dir=run_dir, applied=False, outcomes=())

    outcomes: list[ShardOutcome] = []
    for shard_plan in plan.shards:
        shard, source, tar_path = shard_plan.shard, shard_plan.source, shard_plan.tar_path
        if shard_plan.state == "archived":
            outcomes.append(
                ShardOutcome(
                    shard=shard, tar_path=tar_path, action="skipped",
                    deleted=False, tar_stat=None,
                )
            )
            continue

        rewritten = shard_plan.state == "pending"
        if rewritten:
            _write_tar(source, tar_path, shard)

        try:
            tar_stat = verify_tar(tar_path, source)
        except VerificationError as exc:
            failed_path = _fail_tar(tar_path)
            raise VerificationError(
                f"{exc}\n"
                f"Aborting: nothing was deleted for this shard and no further "
                f"shard is processed. The unverified tar is kept at "
                f"{failed_path} and the source tree at {source} is intact. "
                f"{len(outcomes)} shard(s) were archived before this one and "
                f"stay archived — each verified against its own source."
            ) from exc

        shutil.rmtree(source)
        outcomes.append(
            ShardOutcome(
                shard=shard,
                tar_path=tar_path,
                action="archived" if rewritten else "verified",
                deleted=True,
                tar_stat=tar_stat,
            )
        )
    return ArchiveResult(run_dir=run_dir, applied=True, outcomes=tuple(outcomes))


# --- Rendering ----------------------------------------------------------------


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


def render_plan(plan: ArchivePlan) -> str:
    """Human-readable dry-run plan (spec §A2: shards, files, bytes, projected tars)."""
    lines = [
        f"Archive plan for {plan.run_dir}",
        "  (dry run — nothing written, nothing deleted; re-run with --apply)",
        "",
    ]
    pending = plan.pending
    already = len(plan.shards) - len(pending)
    lines.append(f"  Shards to archive      : {len(pending)}")
    if already:
        lines.append(f"  Shards already archived: {already} (skipped)")
    lines.append(f"  Files to archive       : {plan.n_files}")
    lines.append(f"  Bytes to archive       : {plan.n_bytes} ({_mb(plan.n_bytes)})")
    lines.append(
        f"  Projected tar size     : ~{plan.projected_tar_bytes} "
        f"(~{_mb(plan.projected_tar_bytes)}, estimate)"
    )
    if pending:
        lines.append("")
        lines.append("  shard    files        bytes   projected tar")
        for s in pending:
            stat = s.source_stat
            if stat is None:
                continue
            lines.append(
                f"  {s.shard:<5} {stat.n_files:>8} {stat.n_bytes:>12} "
                f"{s.projected_tar_bytes:>15}"
            )
    if not pending:
        lines.append("")
        lines.append("  Nothing to do — every shard is already archived.")
    return "\n".join(lines)


def render_result(result: ArchiveResult) -> str:
    archived = [o for o in result.outcomes if o.action == "archived"]
    verified = [o for o in result.outcomes if o.action == "verified"]
    skipped = [o for o in result.outcomes if o.action == "skipped"]
    lines = [
        f"Archived {result.run_dir}",
        f"  Shards tarred + verified : {len(archived)}",
    ]
    if verified:
        lines.append(f"  Shards already tarred    : {len(verified)} (re-verified)")
    if skipped:
        lines.append(f"  Shards already archived  : {len(skipped)} (skipped)")
    lines.append(f"  Source shards deleted    : {result.n_deleted}")
    total = sum(o.tar_stat.n_bytes for o in result.outcomes if o.tar_stat)
    lines.append(f"  Member bytes verified    : {total} ({_mb(total)})")
    lines.append(f"  Tars at                  : {archive_root(result.run_dir)}")
    return "\n".join(lines)


__all__ = [
    "ARCHIVE_DIRNAME",
    "FAILED_SUFFIX",
    "FINAL_CSV_GLOBS",
    "REQUIRED_REPORTS",
    "TAR_SUFFIX",
    "ArchiveError",
    "ArchivePlan",
    "ArchiveResult",
    "PreconditionError",
    "ShardOutcome",
    "ShardPlan",
    "SourceStat",
    "TarStat",
    "VerificationError",
    "archive_root",
    "archive_run",
    "check_preconditions",
    "plan_archive",
    "projected_tar_bytes",
    "read_tar_stat",
    "render_plan",
    "render_result",
    "shard_tar_path",
    "verify_tar",
    "walk_shard",
]
