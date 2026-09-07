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

- **Verification precedes every delete, and it checks content.** A shard's tar
  is re-opened and every member streamed through sha256, compared against a
  *fresh* read of the source — not against numbers remembered from the write.
  Until 2026-08-24 this compared only member count and total member bytes,
  which are both preserved by a transposition or by corruption that keeps a
  file's length: the check could not fail on the damage it existed to catch,
  in front of the only irreversible operation in the codebase (review F1). A
  mismatch aborts the whole run, deletes nothing, and leaves the bad tar
  renamed ``<shard>.tar.FAILED`` so it is never mistaken for a good archive on
  the next pass.
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

import hashlib
import os
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
#: verification compares member names and content digests, never timestamps.
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


class IncompleteSourceError(ArchiveError):
    """A pre-existing tar is a strict superset of its source.

    The signature of a delete that died partway: an earlier pass wrote and
    verified the tar, then removal of the source tree stopped in the middle.
    The tar — not the residual source — is the complete copy, so it is left
    under its own name and the operator is told to restore from it. Renaming it
    ``.FAILED`` (the treatment every other mismatch gets) would put the only
    intact copy of the shard behind a name that means "do not trust this".
    """


class DeleteFailedError(ArchiveError):
    """``rmtree`` failed after a tar verified; the source may be half-removed.

    Raised in place of the bare ``OSError`` so the operator gets the recovery
    path rather than a traceback: this is the exact state
    :class:`IncompleteSourceError` exists to recognise on the next pass.
    """


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


def tar_member_names(tar_path: Path) -> set[str]:
    """Relative paths of the regular-file members, with the shard root stripped.

    Only read on the *failure* path, where the count/byte comparison has already
    mismatched and the question is which side lost files. Comparable to
    :func:`source_member_names` on the same shard.

    Raises:
        VerificationError: when the tar cannot be opened or read as a tar.
    """
    names: set[str] = set()
    try:
        with tarfile.open(tar_path, mode="r:") as tar:
            for member in tar:
                if member.isfile():
                    # Members are stored as ``<shard>/<inst_id>/...`` (see
                    # _write_tar's arcname); drop the shard component so both
                    # sides speak in shard-relative paths.
                    names.add(member.name.split("/", 1)[-1])
    except (tarfile.TarError, OSError) as exc:
        raise VerificationError(f"{tar_path} could not be read as a tar: {exc}") from exc
    return names


def source_member_names(shard_dir: Path) -> set[str]:
    """Shard-relative paths of every file under ``shard_dir``, POSIX-separated."""
    return {
        p.relative_to(shard_dir).as_posix()
        for p in shard_dir.rglob("*")
        if p.is_file()
    }


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


def _refuse_on_incomplete_source(tar_path: Path, source: Path, n_done: int) -> None:
    """Raise :class:`IncompleteSourceError` when the source, not the tar, is short.

    Called only when a *pre-existing* tar fails verification. Two things can
    produce that, and they want opposite handling:

    - the tar is wrong (truncated, stale, hand-placed) — the normal case, and
      ``.FAILED`` is right;
    - the **source** is wrong, because an earlier ``--apply`` verified this tar
      and then died partway through ``rmtree`` — in which case the tar is the
      only complete copy of the shard, and renaming it ``.FAILED`` files the
      good data under a name that means "do not trust this", while the abort
      message tells the operator the source is intact when it is not.

    The second is recognised by containment: every remaining source file also
    lives in the tar, at the same size, and the tar holds strictly more. Names
    and sizes are compared rather than counts, because equal counts are exactly
    what the caller already found unequal — the question here is *which side*
    lost files.

    Returns normally when the tar is not a strict superset, leaving the caller
    to take the ``.FAILED`` path.
    """
    tar_names = tar_member_names(tar_path)
    src_names = source_member_names(source)
    if not src_names < tar_names:  # not a strict subset -> not a partial delete
        return

    sizes = {m: s for m, s in _tar_member_sizes(tar_path).items()}
    divergent = sorted(
        name for name in src_names
        if sizes.get(name) != (source / name).stat().st_size
    )
    if divergent:
        # Same names, different bytes: the source was modified, not truncated.
        # That is a real anomaly and the tar earns no special treatment.
        return

    missing = len(tar_names) - len(src_names)
    raise IncompleteSourceError(
        f"{tar_path} verifies as a strict superset of its source {source}: every "
        f"one of the {len(src_names)} remaining source file(s) is in the tar at "
        f"the same size, and the tar holds {missing} more.\n"
        f"This is a delete that stopped partway, not a bad tar. The tar is the "
        f"complete copy and has deliberately NOT been renamed .FAILED — the "
        f"source tree is the incomplete side.\n"
        f"To finish: confirm the tar reads "
        f"(`tar -tf {tar_path} | Measure-Object -Line`), remove the residual "
        f"{source}, then re-run `archive --apply` — the shard will read as "
        f"already archived. Nothing was deleted by this pass; {n_done} shard(s) "
        f"archived before this one stay archived."
    )


#: Read granularity for streaming hashes. Large enough that hashing a multi-GB
#: shard is not syscall-bound, small enough that no member is ever held whole in
#: memory.
HASH_CHUNK_BYTES = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Streaming sha256 of a file on disk.

    Lives here rather than in :mod:`g3o.run.orchestrate.archive_leg`, which is
    where it started: the leg imports *from* this module, so the dependency only
    runs one way and the hash helper has to sit at the lower level for
    :func:`verify_tar` to use it. ``archive_leg`` re-exports it, so its own
    callers are unaffected.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_stream(reader: Any) -> str:
    """Streaming sha256 of a file-like object (a tar member, unextracted)."""
    digest = hashlib.sha256()
    while True:
        chunk = reader.read(HASH_CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _tar_member_digests(tar_path: Path) -> dict[str, str]:
    """Shard-relative member path -> sha256, for the regular files in a tar.

    Members are streamed through the hash via :meth:`tarfile.TarFile.extractfile`
    and never written to disk — verification must not need scratch space the size
    of the shard it is checking.
    """
    digests: dict[str, str] = {}
    try:
        with tarfile.open(tar_path, mode="r:") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                reader = tar.extractfile(member)
                if reader is None:  # pragma: no cover - defensive
                    raise VerificationError(
                        f"{tar_path}: member {member.name!r} is a regular file but "
                        f"could not be opened for reading."
                    )
                with reader:
                    digests[member.name.split("/", 1)[-1]] = _sha256_stream(reader)
    except (tarfile.TarError, OSError) as exc:
        raise VerificationError(f"{tar_path} could not be read as a tar: {exc}") from exc
    return digests


def _source_digests(shard_dir: Path) -> dict[str, str]:
    """Shard-relative path -> sha256, from a fresh read of the source tree."""
    return {
        p.relative_to(shard_dir).as_posix(): sha256_file(p)
        for p in shard_dir.rglob("*")
        if p.is_file()
    }


def _tar_member_sizes(tar_path: Path) -> dict[str, int]:
    """Shard-relative member path -> size, for the regular files in a tar."""
    sizes: dict[str, int] = {}
    try:
        with tarfile.open(tar_path, mode="r:") as tar:
            for member in tar:
                if member.isfile():
                    sizes[member.name.split("/", 1)[-1]] = member.size
    except (tarfile.TarError, OSError) as exc:
        raise VerificationError(f"{tar_path} could not be read as a tar: {exc}") from exc
    return sizes


def verify_tar(tar_path: Path, source: Path) -> TarStat:
    """Compare a tar against a fresh read of its source, member by member.

    **Why per-member content and not two totals** (review F1, 2026-08-24). This
    used to compare exactly ``(n_files, n_bytes)`` — member count and *summed*
    bytes — and :func:`archive_run` then ``rmtree``s the source. Under that check
    a tar whose members had been transposed, or corrupted without changing
    length, verified clean and the originals were deleted. Both aggregates are
    preserved by exactly those failures, which is what made them the wrong
    things to compare in front of the only irreversible operation in the
    codebase.

    Every regular member is streamed through sha256 straight out of the tar
    (never extracted to disk) and compared against a fresh hash of the
    corresponding source file, and the two name sets must match exactly. That
    subsumes the old count/bytes comparison rather than sitting beside it: two
    trees with identical per-member digests necessarily have identical counts
    and totals.

    The cost is reading both sides once more. That is the right trade in front
    of a delete: the alternative is a check that cannot fail on the corruption
    it exists to catch. There is deliberately no flag to weaken it.

    Raises:
        VerificationError: on any name-set or content mismatch. The caller
            renames the tar aside and aborts; nothing is deleted on this path.
    """
    tar_digests = _tar_member_digests(tar_path)
    src_digests = _source_digests(source)

    if tar_digests.keys() != src_digests.keys():
        missing = sorted(src_digests.keys() - tar_digests.keys())
        extra = sorted(tar_digests.keys() - src_digests.keys())
        raise VerificationError(
            f"{tar_path} does not match its source {source}: "
            f"{len(missing)} file(s) present in the source but absent from the tar"
            f"{' (first: ' + missing[0] + ')' if missing else ''}, "
            f"{len(extra)} present in the tar but absent from the source"
            f"{' (first: ' + extra[0] + ')' if extra else ''}."
        )

    mismatched = sorted(
        name for name, digest in src_digests.items() if tar_digests[name] != digest
    )
    if mismatched:
        raise VerificationError(
            f"{tar_path} does not match its source {source}: "
            f"{len(mismatched)} member(s) differ in content despite matching names "
            f"(first: {mismatched[0]}). The file count and total byte count may "
            f"well agree — that is exactly the corruption a per-member digest "
            f"check exists to catch, and why nothing here is deleted."
        )
    return read_tar_stat(tar_path)


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

    One mismatch is exempt from the ``.FAILED`` rename: a *pre-existing* tar
    that is a strict superset of its source is a delete that died partway, not
    a bad tar, so it keeps its name and
    :class:`IncompleteSourceError` says how to finish
    (:func:`_refuse_on_incomplete_source`). No path here deletes on a failed
    verification.

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
            if not rewritten:
                # The tar predates this pass, so a mismatch has two possible
                # causes and they call for opposite handling. Ask the members
                # which one it is before touching anything.
                _refuse_on_incomplete_source(tar_path, source, len(outcomes))
            failed_path = _fail_tar(tar_path)
            raise VerificationError(
                f"{exc}\n"
                f"Aborting: this command deleted nothing for this shard and no "
                f"further shard is processed. The unverified tar is kept at "
                f"{failed_path}; the source tree at {source} was not touched by "
                f"this pass. {len(outcomes)} shard(s) were archived before this "
                f"one and stay archived — each verified against its own source."
            ) from exc

        try:
            shutil.rmtree(source)
        except OSError as exc:
            raise DeleteFailedError(
                f"{tar_path} verified, but removing its source {source} failed "
                f"partway: {exc}\n"
                f"The tar is complete and is now the authoritative copy of this "
                f"shard — it is NOT renamed. Clear whatever holds the residual "
                f"files (an open handle, a read-only attribute) and re-run "
                f"`archive --apply`; the next pass recognises the half-removed "
                f"source and resumes. {len(outcomes)} shard(s) archived before "
                f"this one stay archived."
            ) from exc
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
    "DeleteFailedError",
    "IncompleteSourceError",
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
    "source_member_names",
    "tar_member_names",
    "verify_tar",
    "walk_shard",
]
