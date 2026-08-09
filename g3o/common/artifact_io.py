"""Single owner of bulk-artifact encoding (storage layout v2, Phase 2).

Spec: ``docs/storage-layout-v2.md`` §A1.

Scope is deliberately narrow — **only** the two page-level artifact classes
that dominate a run's bytes::

    institutions/<shard>/<inst_id>/scrape/<url_hash>.json[.gz]
    institutions/<shard>/<inst_id>/extract/<url_hash>.json[.gz]

Every other per-institution stage file (``institution.json``, ``1a``/``1b``/
``1c``/``2``/``3``, ``6_validate.json``, ``_timing.json``) stays plain,
indented JSON: those are what a human opens during QC, and their bytes are
noise next to page text.

Three properties matter, and each is why a function lives here rather than at
the call site:

- **Deterministic bytes.** ``mtime=0`` *and* an empty gzip ``FNAME`` field are
  pinned in :func:`write_artifact` and nowhere else, so identical input
  produces a byte-identical file on any machine on any day. Output hashing
  (present or future) can therefore treat an artifact tree as content. This
  pin must not be copied to other gzip call sites — it is a property of *these
  two artifact classes*, not a house style, and a reader that assumes it
  everywhere would be wrong.
- **Read-side ``.json``/``.json.gz`` duality.** Writers emit one format
  (gzip); readers accept both, with ``.gz`` winning when both are present. A
  run that crashed mid-upgrade, a dev tree with mixed files, or a hand-built
  test fixture all still read. There is no migration step and no dual *write*
  path.
- **Atomic replacement.** Writes land on a same-directory temp file and swap
  in via :func:`os.replace` (review F7), so a crashed or concurrent writer can
  never leave a truncated artifact that a later resume would read back as
  corrupt evidence. Mirrors :func:`g3o.scrape.fetcher._save`.

``indent=2`` is dropped for both classes — indentation is pointless under gzip
and costs bytes on the decompress side. All other ``indent=2`` sites are
untouched.
"""

from __future__ import annotations

import gzip
import os
import threading
from pathlib import Path

#: Suffix every artifact this module writes carries.
ARTIFACT_SUFFIX = ".json.gz"

#: Legacy/plain suffix still accepted on read (pre-Phase-2 trees, fixtures).
PLAIN_SUFFIX = ".json"

#: Suffix a quarantined (unparseable) artifact is renamed to. Matches neither
#: glob in :func:`glob_artifacts`, so a quarantined file leaves the working set
#: without needing an explicit filter anywhere.
CORRUPT_SUFFIX = ".corrupt"

#: gzip level: default speed/ratio balance. Page text compresses ~5-10x at any
#: level >= 4, so a higher level buys ~nothing for real CPU.
COMPRESS_LEVEL = 6

_SPEC_REF = "docs/storage-layout-v2.md"


def gz_path(path: Path) -> Path:
    """The ``.json.gz`` form of an artifact path (idempotent)."""
    return path if path.name.endswith(".gz") else path.with_name(path.name + ".gz")


def plain_path(path: Path) -> Path:
    """The ``.json`` form of an artifact path (idempotent)."""
    return path.with_name(path.name[:-3]) if path.name.endswith(".gz") else path


def artifact_stem(path: Path) -> str:
    """The artifact's identity — its ``<url_hash>`` — with *both* suffixes off.

    :attr:`pathlib.PurePath.stem` strips exactly one suffix, so on
    ``<hash>.json.gz`` it yields ``<hash>.json`` and any comparison against a
    set of url hashes silently misses. Callers that match a filename against
    hashes must use this instead; that failure mode is a wrong count, not an
    exception, so nothing else catches it.
    """
    name = path.name
    if name.endswith(ARTIFACT_SUFFIX):
        return name[: -len(ARTIFACT_SUFFIX)]
    if name.endswith(PLAIN_SUFFIX):
        return name[: -len(PLAIN_SUFFIX)]
    return path.stem


def write_artifact(path: Path, text: str) -> None:
    """Write ``text`` to ``<path>.gz``, gzipped, atomically, deterministically.

    ``path`` is given *without* a suffix decision — pass the logical
    ``<url_hash>.json`` and this writes ``<url_hash>.json.gz``. Passing an
    already-``.gz`` path is accepted and means the same thing.

    Determinism: ``mtime=0`` zeroes the gzip header timestamp, and
    ``filename=""`` suppresses the ``FNAME`` field that :class:`gzip.GzipFile`
    would otherwise copy from the temp file's name (which carries a pid and a
    thread id, and so would vary per writer). Both are required for
    byte-identical output; neither is the library default.
    """
    target = gz_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomicity (review F7): a plain open() on the destination lets a crash --
    # or a concurrent reader on the resume path -- observe a truncated artifact,
    # which reads back as corrupt evidence rather than as a missing file. The
    # temp name carries pid + thread id so two writers never collide.
    tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    try:
        with open(tmp, "wb") as raw:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, mtime=0,
                compresslevel=COMPRESS_LEVEL,
            ) as gz:
                gz.write(text.encode("utf-8"))
        os.replace(tmp, target)
    except BaseException:
        # Never leave a temp file behind on a failed write.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_artifact(path: Path) -> str:
    """Read an artifact given either suffix; ``.gz`` wins when both exist.

    Raises:
        FileNotFoundError: when neither form is present. Callers that mean
            "read it if it's there" test :func:`artifact_exists` first, or
            iterate :func:`glob_artifacts`, which returns concrete paths.
    """
    gz = gz_path(path)
    if gz.exists():
        return gzip.decompress(gz.read_bytes()).decode("utf-8")
    return plain_path(path).read_text(encoding="utf-8")


def artifact_exists(path: Path) -> bool:
    """True when either the ``.json.gz`` or the ``.json`` form is present.

    This is the resume predicate for Stage 4 (spec §A1): a pre-Phase-2 partial
    run resumes off its plain artifacts instead of re-scraping every URL.
    """
    return gz_path(path).exists() or plain_path(path).exists()


def glob_artifacts(directory: Path) -> list[Path]:
    """Every artifact in ``directory``, deduped by stem, ordered by stem.

    ``*.json`` plus ``*.json.gz``; when a stem has both forms the ``.gz`` one
    is returned, matching :func:`read_artifact`. Ordering is by
    :func:`artifact_stem`, so a mixed tree walks in the same order as a uniform
    one and the row order of downstream consumers (e.g.
    :func:`g3o.validate.consolidate.load_extract_outputs`) does not depend on
    which files happen to be compressed.

    Returns an empty list for a missing directory, so callers keep their
    existing ``is_dir()``-guarded shape without needing the guard.
    """
    if not directory.is_dir():
        return []
    by_stem: dict[str, Path] = {}
    for p in directory.glob(f"*{ARTIFACT_SUFFIX}"):
        by_stem[artifact_stem(p)] = p
    for p in directory.glob(f"*{PLAIN_SUFFIX}"):
        by_stem.setdefault(artifact_stem(p), p)
    return [by_stem[stem] for stem in sorted(by_stem)]


def quarantine_artifact(path: Path) -> Path:
    """Move an unparseable artifact aside and return where it went.

    Review F7: an artifact that exists but will not parse is corrupt evidence,
    not a completed unit of work. Renaming it to ``<name>.corrupt`` takes it
    out of :func:`glob_artifacts` (neither glob matches the suffix) so the
    caller can redo the work, while keeping the bytes on disk for diagnosis —
    the project's archive-don't-delete rule applies to damaged artifacts too.

    Idempotent: an existing ``.corrupt`` file at the destination is replaced.
    Returns the quarantine path even when the rename fails (a locked file on
    Windows), because the caller's next step is to record and redo the work
    either way, not to abort.
    """
    src = gz_path(path) if gz_path(path).exists() else plain_path(path)
    dest = src.with_name(src.name + CORRUPT_SUFFIX)
    try:
        os.replace(src, dest)
    except OSError:
        pass
    return dest


__all__ = [
    "ARTIFACT_SUFFIX",
    "COMPRESS_LEVEL",
    "CORRUPT_SUFFIX",
    "PLAIN_SUFFIX",
    "artifact_exists",
    "artifact_stem",
    "glob_artifacts",
    "gz_path",
    "plain_path",
    "quarantine_artifact",
    "read_artifact",
    "write_artifact",
]
