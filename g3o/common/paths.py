"""Single owner of run-tree layout knowledge (storage layout v2).

Spec: ``docs/storage-layout-v2.md`` §B1/§B2 (Phase 1).

The run tree fans institution directories out 256 ways under an
``institutions/`` level::

    runs/<run_id>/institutions/<shard>/<inst_id>/...

Two properties matter, and both are why this module exists at all:

- **The ``institutions/`` level is structural, not conventional.** Before v2
  every walker filtered run-level entries out of ``run_dir.iterdir()`` by
  name (``startswith("_")``, ``== ".done"``, ``== "final"``). That filtering
  was quietly wrong: ``.done`` lives at ``_state/.done`` and was never a
  direct child of ``run_dir`` (so the check was dead code), while ``final/``
  *is* a direct child and :mod:`g3o.report.diff` had no guard for it at all.
  Under v2 nothing but institution directories lives under
  ``institutions/``, so :func:`iter_institution_dirs` cannot pick up a
  run-level entry and no name filter is needed anywhere.
- **The shard is derived from ``inst_id`` alone.** No master-CSV row, no
  ``master_row_id``, no ordering assumption about the ID's internal
  structure — the pending institution-key spec may change how ``inst_id`` is
  derived, and md5-of-string survives that untouched (spec §7, risk 2).

No module outside this one may build an institution path by hand;
``tests/test_paths.py`` enforces that with a grep guard.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

LAYOUT_VERSION = 2

#: Name of the level that separates institution dirs from run-level entries.
INSTITUTIONS_DIRNAME = "institutions"

#: Hex chars of the md5 digest used as the shard name → 16**2 = 256 shards.
SHARD_HEX_CHARS = 2

MANIFEST_NAME = "manifest.json"

_SPEC_REF = "docs/storage-layout-v2.md"


def institution_shard(inst_id: str) -> str:
    """Shard name for one institution: ``md5(inst_id)[:2]`` (hex).

    Deterministic from ``inst_id`` alone and agnostic to the ID scheme, so
    every constructor site computes it without touching the master row.
    """
    digest = hashlib.md5(inst_id.encode("utf-8")).hexdigest()
    return digest[:SHARD_HEX_CHARS]


def institutions_root(run_dir: Path) -> Path:
    """The ``institutions/`` level of a run tree."""
    return run_dir / INSTITUTIONS_DIRNAME


def institution_dir(run_dir: Path, inst_id: str) -> Path:
    """``runs/<run_id>/institutions/<shard>/<inst_id>``.

    Pure path construction — creates nothing.
    """
    return institutions_root(run_dir) / institution_shard(inst_id) / inst_id


def iter_institution_dirs(run_dir: Path) -> Iterator[Path]:
    """Every institution directory in the run, ordered by ``inst_id``.

    Two-level walk (shard, then institution). Yields nothing when the
    ``institutions/`` level is absent — callers that need a *loud* failure on a
    non-v2 tree call :func:`require_layout` first; this function stays quiet so
    a legitimately empty run (planned, no stages run) reads as empty rather
    than as an error.

    Ordering is by ``inst_id``, **not** by ``(shard, inst_id)``. The shard is
    an md5 prefix, so shard order is unrelated to ID order, and the walk order
    of :func:`g3o.persist.writer.load_consolidated_outputs` is what fixes row
    order in the Stage-7 CSVs. Sorting on the institution id keeps those rows
    in exactly the order the pre-v2 flat ``sorted(run_dir.iterdir())`` walk
    produced, so the layout change moves files without reordering delivered
    data. The cost is materializing the directory list instead of streaming it;
    at the full-frame envelope (~720k entries) that is a bounded, one-per-report
    cost and worth paying for output stability.
    """
    root = institutions_root(run_dir)
    if not root.is_dir():
        return
    found: list[Path] = []
    for shard_dir in sorted(root.iterdir()):
        if not shard_dir.is_dir():
            continue
        found.extend(d for d in shard_dir.iterdir() if d.is_dir())
    yield from sorted(found, key=lambda d: d.name)


def institution_ids(run_dir: Path) -> list[str]:
    """Institution ids present on disk, ordered by id."""
    return [d.name for d in iter_institution_dirs(run_dir)]


def require_layout(run_dir: Path) -> None:
    """Refuse a run tree that is not storage layout v2.

    Raises:
        RuntimeError: when ``manifest.json`` is missing, unreadable, or
            carries a ``layout_version`` other than :data:`LAYOUT_VERSION`.

    There is deliberately no dual-layout read support (spec §B2): a pre-v2 run
    is read by checking out a pre-v2 commit, which keeps every reader in the
    codebase single-path. The error names the spec so the reader knows why.
    """
    manifest_path = run_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise RuntimeError(
            f"{run_dir} carries no {MANIFEST_NAME}, so its storage layout cannot be "
            f"verified as v{LAYOUT_VERSION}. Storage layout v2 ({_SPEC_REF}) requires "
            "a manifest with a 'layout_version' field. There is no dual-layout read "
            "support: read a pre-v2 run by checking out a pre-v2 commit."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"{manifest_path} could not be read as JSON, so the storage layout "
            f"cannot be verified as v{LAYOUT_VERSION} ({_SPEC_REF}): {exc}"
        ) from exc
    found = manifest.get("layout_version")
    if found != LAYOUT_VERSION:
        raise RuntimeError(
            f"{run_dir} declares layout_version={found!r}, but this code reads only "
            f"layout_version={LAYOUT_VERSION} (storage layout v2, {_SPEC_REF}). "
            "There is no dual-layout read support: read a pre-v2 run by checking "
            "out a pre-v2 commit."
        )


__all__ = [
    "INSTITUTIONS_DIRNAME",
    "LAYOUT_VERSION",
    "MANIFEST_NAME",
    "SHARD_HEX_CHARS",
    "institution_dir",
    "institution_ids",
    "institution_shard",
    "institutions_root",
    "iter_institution_dirs",
    "require_layout",
]
