"""Leg 4 — archive a finished run and put it somewhere it will survive.

Four steps, in an order where each one's failure is cheap:

1. **Tar the institution tree** — ``g3o.run.archive.archive_run(apply=True)``,
   unchanged and not reimplemented. It owns the preconditions (Stage-7 CSVs,
   every ``.done`` marker, the run-level reports), the per-shard verification,
   and the only delete path in the codebase.
2. **Hash and inventory** — a ``SHA256SUMS`` over every file that will be
   uploaded, and an uncompressed ledger dump listing them plus the members
   *inside* each tar.
3. **Upload** — one object per file, under ``<prefix>/<run_id>/<run-relative path>``.
4. **Verify after upload** — every object is streamed back out of the store and
   re-hashed against ``SHA256SUMS``.

Step 4 is the one worth defending. A ``PutObject`` that returns 200 tells you the
service accepted the request, and the storage-v2 archive module already settled
the house rule for this class of check: verify against a fresh read, never
against numbers remembered from the write. So the bytes come back over the wire
and get hashed again. On a run archive this costs one extra download and buys the
only evidence that the copy in the bucket is the copy on the disk — which is the
entire claim the archive is making.

**Why the ledger is uncompressed.** Everything else in the bundle is opaque: the
tars hold gzipped page artifacts, so "what is in this archive?" cannot be
answered without extracting it. ``archive_ledger.jsonl`` is plain text, one JSON
object per line, listing every uploaded file with its size and hash *and* every
member inside every tar with its size. It is the index that makes the archive
browsable from a Drive folder — and it is the file a replication reader opens
first. Compressing the one file whose job is to be readable would be a small
self-defeating economy.

**What is in the bundle.** Everything the run directory holds, minus two things:
the live ``institutions/`` tree (which step 1 has just replaced with tars) and
this leg's own generated files (which cannot contain their own hashes). That is
an exclusion list, not an inclusion list, on purpose — an allowlist of run-level
filenames would silently stop archiving the next artifact anyone adds, and the
failure would be invisible until someone needed the file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from g3o.common.paths import INSTITUTIONS_DIRNAME
from g3o.run.archive import ARCHIVE_DIRNAME, ArchiveError, archive_run, render_result
from g3o.run.orchestrate.objectstore import (
    CHUNK_BYTES,
    ObjectStore,
    ObjectStoreError,
    describe_store,
    store_from_uri,
)
from g3o.run.orchestrate.status import (
    ORCHESTRATOR_DIRNAME,
    RunStatus,
    orchestrator_dir,
    read_json,
    record_leg,
    run_status,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

SHA256SUMS_FILENAME = "SHA256SUMS"
LEDGER_FILENAME = "archive_ledger.jsonl"

#: Generated bundle artifacts live here, under the run's orchestrator dir. They
#: are uploaded to the *root* of the run's prefix so that a downloaded bundle
#: verifies with a plain ``cd <run_id> && sha256sum -c SHA256SUMS``.
BUNDLE_DIRNAME = "bundle"

#: Never uploaded. ``institutions/`` is the live tree the tars replace; the
#: bundle directory holds files that cannot hash themselves; ``.tmp.`` is an
#: atomic write caught mid-flight.
_EXCLUDED_TOP_LEVEL = (INSTITUTIONS_DIRNAME,)
_EXCLUDED_SUFFIX_MARKERS = (".tmp.",)

#: This leg's own record, for the same reason ``SHA256SUMS`` cannot list itself:
#: a description of the archive cannot be a member of the archive it describes.
#: It is written after the bundle is assembled, so a *first* pass never sees it —
#: excluding it is what keeps a second pass over an unchanged run byte-identical
#: to the first, which is how an interrupted upload can be compared and resumed.
#: The other leg records (submit, ingest, publish) stay in: they are provenance
#: about the run, not about the bundle.
_EXCLUDED_ORCHESTRATOR_FILES = ("archive.json",)


class ArchiveLegError(RuntimeError):
    """The archive could not be produced, uploaded, or verified."""


def sha256_file(path: Path) -> str:
    """Streaming sha256 of a file. Never loads a shard tar into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(chunks: Any) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class BundleMember:
    """One file in the upload set, addressed by its run-relative path."""

    relpath: str
    path: Path
    n_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.relpath, "bytes": self.n_bytes, "sha256": self.sha256}


@dataclass(frozen=True)
class ObjectOutcome:
    """One object's upload and its post-upload verification."""

    relpath: str
    key: str
    uploaded: bool
    verified: bool
    expected_sha256: str
    observed_sha256: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.relpath,
            "key": self.key,
            "uploaded": self.uploaded,
            "verified": self.verified,
            "expected_sha256": self.expected_sha256,
            "observed_sha256": self.observed_sha256,
            "error": self.error,
        }


@dataclass(frozen=True)
class ArchiveLegResult:
    run_id: str
    run_dir: Path
    applied: bool
    uploaded: bool
    members: tuple[BundleMember, ...] = ()
    objects: tuple[ObjectOutcome, ...] = ()
    sha256sums_path: Path | None = None
    ledger_path: Path | None = None
    destination: dict[str, Any] = field(default_factory=dict)
    archive_summary: str = ""

    @property
    def n_bytes(self) -> int:
        return sum(m.n_bytes for m in self.members)

    @property
    def n_failed(self) -> int:
        return sum(1 for o in self.objects if not (o.uploaded and o.verified))

    @property
    def verified(self) -> bool:
        """Every object uploaded **and** re-read **and** matched. Or not verified."""
        return bool(self.objects) and self.n_failed == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "applied": self.applied,
            "uploaded": self.uploaded,
            "verified": self.verified,
            "n_members": len(self.members),
            "n_bytes": self.n_bytes,
            "n_failed": self.n_failed,
            "sha256sums": str(self.sha256sums_path) if self.sha256sums_path else None,
            "ledger": str(self.ledger_path) if self.ledger_path else None,
            "destination": self.destination,
            "objects": [o.to_dict() for o in self.objects],
        }


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------


def bundle_dir(run_dir: Path) -> Path:
    return orchestrator_dir(run_dir) / BUNDLE_DIRNAME


def _is_excluded(rel: Path) -> bool:
    parts = rel.parts
    if parts and parts[0] in _EXCLUDED_TOP_LEVEL:
        return True
    if len(parts) >= 2 and parts[0] == ORCHESTRATOR_DIRNAME:
        if parts[1] == BUNDLE_DIRNAME or parts[1] in _EXCLUDED_ORCHESTRATOR_FILES:
            return True
    return any(marker in rel.name for marker in _EXCLUDED_SUFFIX_MARKERS)


def collect_bundle(run_dir: Path) -> list[BundleMember]:
    """Hash every file that will be uploaded, in stable path order.

    Ordering is sorted-by-path so that ``SHA256SUMS`` and the ledger are
    byte-reproducible for an unchanged run — two archive passes over the same
    finished run produce identical files, which is what makes re-running this leg
    after a network failure safe to compare.
    """
    members: list[BundleMember] = []
    for path in sorted(p for p in run_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(run_dir)
        if _is_excluded(rel):
            continue
        members.append(
            BundleMember(
                relpath=rel.as_posix(),
                path=path,
                n_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return members


def _tar_inventory(tar_path: Path) -> list[dict[str, Any]]:
    """``(member, bytes)`` for every regular file inside one shard tar.

    Read once, here, so the ledger can answer "is institution X in this archive?"
    without extracting anything. A tar that cannot be opened yields an explicit
    error line rather than nothing: a silent gap in an inventory is worse than a
    recorded failure, because the inventory is what a reader trusts instead of
    looking.
    """
    rows: list[dict[str, Any]] = []
    try:
        with tarfile.open(tar_path, mode="r:") as tar:
            for member in tar:
                if member.isfile():
                    rows.append({"path": member.name, "bytes": member.size})
    except (tarfile.TarError, OSError) as exc:
        return [{"error": f"{type(exc).__name__}: {exc}"}]
    return rows


def write_ledger(run_dir: Path, members: list[BundleMember]) -> Path:
    """The uncompressed inventory. One JSON object per line, three kinds of line.

    ``bundle`` (once, first) — the run's identity and the totals.
    ``member`` — one per uploaded file, with size and sha256.
    ``tar_member`` — one per file *inside* a shard tar, with its size.
    """
    path = bundle_dir(run_dir) / LEDGER_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = read_json(run_dir / "manifest.json") or {}
    lines: list[str] = [
        json.dumps(
            {
                "kind": "bundle",
                "run_id": manifest.get("run_id") or run_dir.name,
                "run_started_at": manifest.get("run_started_at"),
                "created_at": utc_now_iso(),
                "git_sha": (manifest.get("code") or {}).get("git_sha"),
                "config_hash": manifest.get("config_hash"),
                "n_members": len(members),
                "total_bytes": sum(m.n_bytes for m in members),
                "note": (
                    "Uncompressed inventory of this run's archive. 'member' lines "
                    "are the uploaded files; 'tar_member' lines are the files "
                    "inside each shard tar, so the archive can be browsed without "
                    "extracting it. Restore one shard with: tar -xf "
                    "archive/institutions/<shard>.tar -C <run_dir>/institutions/"
                ),
            },
            ensure_ascii=False,
        )
    ]
    for member in members:
        lines.append(json.dumps({"kind": "member", **member.to_dict()}, ensure_ascii=False))
    tar_root = f"{ARCHIVE_DIRNAME}/{INSTITUTIONS_DIRNAME}/"
    for member in members:
        if not (member.relpath.startswith(tar_root) and member.relpath.endswith(".tar")):
            continue
        shard = Path(member.relpath).stem
        for row in _tar_inventory(member.path):
            lines.append(
                json.dumps(
                    {"kind": "tar_member", "tar": member.relpath, "shard": shard, **row},
                    ensure_ascii=False,
                )
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_sha256sums(run_dir: Path, members: list[BundleMember], ledger: Path) -> Path:
    """``SHA256SUMS`` in ``sha256sum -c`` format, covering members + the ledger.

    Two spaces between hash and path, forward slashes always: the point of this
    file is that the PI can verify a Drive copy with the coreutils command they
    already know, on a machine that has no G3O checkout at all. It cannot list
    itself, which is why the post-upload verification hashes it separately.
    """
    path = bundle_dir(run_dir) / SHA256SUMS_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [(m.sha256, m.relpath) for m in members]
    rows.append((sha256_file(ledger), LEDGER_FILENAME))
    rows.sort(key=lambda r: r[1])
    path.write_text("".join(f"{h}  {p}\n" for h, p in rows), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Upload and verify
# ---------------------------------------------------------------------------


def upload_and_verify(
    store: ObjectStore,
    run_id: str,
    upload_set: list[tuple[str, Path, str]],
) -> list[ObjectOutcome]:
    """Upload each ``(relpath, path, sha256)``, then read it back and re-hash.

    Verification is per object and immediately after its own upload, not in a
    second pass at the end: a mismatch is then attributable to one transfer, and
    an interrupted leg leaves every object it reports as verified genuinely
    verified.

    A failure never aborts the remaining objects. The caller gets the whole
    picture — "3 of 240 failed, here they are" is actionable; "it failed" after
    the fourth object is not, and a partial upload has to be finished either way.
    """
    outcomes: list[ObjectOutcome] = []
    for relpath, path, expected in upload_set:
        key = f"{run_id}/{relpath}"
        try:
            store.put(key, path)
        except ObjectStoreError as exc:
            outcomes.append(
                ObjectOutcome(
                    relpath=relpath, key=key, uploaded=False, verified=False,
                    expected_sha256=expected, error=str(exc),
                )
            )
            continue
        try:
            observed = sha256_stream(store.read_stream(key))
        except ObjectStoreError as exc:
            outcomes.append(
                ObjectOutcome(
                    relpath=relpath, key=key, uploaded=True, verified=False,
                    expected_sha256=expected, error=f"read-back failed: {exc}",
                )
            )
            continue
        outcomes.append(
            ObjectOutcome(
                relpath=relpath,
                key=key,
                uploaded=True,
                verified=observed == expected,
                expected_sha256=expected,
                observed_sha256=observed,
                error=None if observed == expected else "sha256 mismatch after upload",
            )
        )
    return outcomes


def _live_tree_remains(run_dir: Path) -> bool:
    root = run_dir / INSTITUTIONS_DIRNAME
    return root.is_dir() and any(root.iterdir())


def archive_and_upload(
    runs_dir: Path,
    run_id: str,
    *,
    destination: str | ObjectStore | None = None,
    apply: bool = False,
    status: RunStatus | None = None,
    force: bool = False,
) -> ArchiveLegResult:
    """Tar, hash, inventory, upload, verify. Without ``apply``, plan only.

    ``apply=False`` is the default for the same reason it is the default in
    :mod:`g3o.run.archive`: this leg deletes the institution tree. The dry pass
    runs the preconditions and prints the plan, so an operator can see what would
    be removed before anything is.

    Refuses a run that did not finish, unless ``force``: archiving is the *last*
    operation on a run, and applying it to a run that is merely paused mid-stage
    destroys the tree a resume was going to write into.
    """
    run_dir = Path(runs_dir) / run_id
    state = status or run_status(Path(runs_dir), run_id)
    if state.state not in ("completed", "stopped") and not force:
        raise ArchiveLegError(
            f"refusing to archive run {run_id}: its state is {state.state!r}. "
            f"Archival removes the institution tree, and a run that has not "
            f"finished may still need it — a resume writes into that tree. "
            f"Pass --force only when the run is known to be over for good."
        )

    started_at = utc_now_iso()
    try:
        archive_result = archive_run(run_dir, apply=apply)
    except ArchiveError as exc:
        record_leg(
            run_dir, "archive", outcome="refused", started_at=started_at,
            error_class=type(exc).__name__, error_message=str(exc),
        )
        raise ArchiveLegError(str(exc)) from exc

    if not apply:
        from g3o.run.archive import plan_archive, render_plan

        return ArchiveLegResult(
            run_id=run_id, run_dir=run_dir, applied=False, uploaded=False,
            archive_summary=render_plan(plan_archive(run_dir)),
        )

    if _live_tree_remains(run_dir):
        raise ArchiveLegError(
            f"{run_dir / INSTITUTIONS_DIRNAME} still holds files after "
            f"`archive --apply`. The bundle excludes the live tree by design, so "
            f"uploading now would archive an incomplete run. Investigate before "
            f"retrying — the archive module reports every shard it could not "
            f"complete."
        )

    members = collect_bundle(run_dir)
    ledger = write_ledger(run_dir, members)
    sums = write_sha256sums(run_dir, members, ledger)

    if destination is None:
        record_leg(
            run_dir, "archive", outcome="archived-not-uploaded", started_at=started_at,
            n_members=len(members), n_bytes=sum(m.n_bytes for m in members),
            sha256sums=str(sums), ledger=str(ledger),
        )
        return ArchiveLegResult(
            run_id=run_id, run_dir=run_dir, applied=True, uploaded=False,
            members=tuple(members), sha256sums_path=sums, ledger_path=ledger,
            archive_summary=render_result(archive_result),
        )

    store = store_from_uri(destination) if isinstance(destination, str) else destination
    upload_set = [(m.relpath, m.path, m.sha256) for m in members]
    upload_set.append((LEDGER_FILENAME, ledger, sha256_file(ledger)))
    upload_set.append((SHA256SUMS_FILENAME, sums, sha256_file(sums)))
    outcomes = upload_and_verify(store, run_id, upload_set)

    result = ArchiveLegResult(
        run_id=run_id,
        run_dir=run_dir,
        applied=True,
        uploaded=True,
        members=tuple(members),
        objects=tuple(outcomes),
        sha256sums_path=sums,
        ledger_path=ledger,
        destination=describe_store(store),
        archive_summary=render_result(archive_result),
    )
    # `run_dir` is dropped from the payload: it is the positional argument, and
    # the record lives inside that directory anyway.
    detail = {k: v for k, v in result.to_dict().items() if k != "run_dir"}
    record_leg(
        run_dir,
        "archive",
        outcome="verified" if result.verified else "unverified",
        started_at=started_at,
        **detail,
    )
    return result


def render_archive(result: ArchiveLegResult) -> str:
    lines = [result.archive_summary, ""] if result.archive_summary else []
    lines.append(f"Archive bundle — run {result.run_id}")
    if not result.applied:
        lines.append("  (dry run — nothing tarred, nothing deleted, nothing uploaded)")
        return "\n".join(lines)
    lines += [
        f"  Files in the bundle : {len(result.members)}",
        f"  Bytes               : {result.n_bytes} ({result.n_bytes / 1_048_576:.1f} MB)",
        f"  SHA256SUMS          : {result.sha256sums_path}",
        f"  Ledger (plain text) : {result.ledger_path}",
    ]
    if not result.uploaded:
        lines.append("  Upload              : not requested (no --destination)")
        return "\n".join(lines)
    failed = [o for o in result.objects if not (o.uploaded and o.verified)]
    lines += [
        f"  Destination         : {result.destination.get('uri') or result.destination.get('bucket')}",
        f"  Objects uploaded    : {sum(1 for o in result.objects if o.uploaded)}/{len(result.objects)}",
        f"  Objects verified    : {sum(1 for o in result.objects if o.verified)}/{len(result.objects)}"
        + "  (streamed back and re-hashed)",
    ]
    if failed:
        lines.append(f"  ! {len(failed)} object(s) did NOT verify:")
        for outcome in failed[:20]:
            lines.append(f"      {outcome.relpath}: {outcome.error}")
        if len(failed) > 20:
            lines.append(f"      … and {len(failed) - 20} more")
        lines.append(
            "  The local run directory is untouched by the upload. Re-run the "
            "archive leg; objects that already verify are re-uploaded harmlessly."
        )
    else:
        lines.append("  Every object was read back out of the store and matched its hash.")
    return "\n".join(lines)


__all__ = [
    "BUNDLE_DIRNAME",
    "LEDGER_FILENAME",
    "SHA256SUMS_FILENAME",
    "ArchiveLegError",
    "ArchiveLegResult",
    "BundleMember",
    "ObjectOutcome",
    "archive_and_upload",
    "bundle_dir",
    "collect_bundle",
    "render_archive",
    "sha256_file",
    "sha256_stream",
    "upload_and_verify",
    "write_ledger",
    "write_sha256sums",
]
