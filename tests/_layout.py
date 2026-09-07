"""Shared helpers for building storage-layout-v2 run trees in tests.

Fixtures that hand-build a run tree need two things that layout v2 introduced
(``docs/storage-layout-v2.md``):

- institution directories live at ``institutions/<shard>/<inst_id>/``, so they
  must be constructed via :func:`g3o.common.paths.institution_dir` rather than
  ``run_dir / inst_id``;
- ``manifest.json`` must declare ``layout_version``, or every reader's
  :func:`g3o.common.paths.require_layout` gate refuses the tree;
- ``manifest.json`` must carry an ``institution_uids`` block (PI ruling
  2026-08-14), or :func:`g3o.common.paths.institution_uid_map` refuses to let
  Stage 7 stamp the run. Defaulted here from the manifest's own
  ``institutions`` list so a fixture that already names its institutions needs
  no change.

Keeping all three in one place means a future layout bump touches this module
and ``g3o/common/paths.py``, not sixty fixtures.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from g3o.common.paths import LAYOUT_VERSION, institution_dir

__all__ = [
    "LAYOUT_VERSION",
    "inst_dir",
    "layout_manifest",
    "make_inst_dir",
    "uid_for",
    "write_manifest",
]


def uid_for(inst_id: str) -> str:
    """A deterministic synthetic ``institution_uid`` for a test institution.

    Real uids come off the master CSV; fixtures have no master, so derive one
    that satisfies ``G3O-I-<8 digits>``. Numeric ``INST-%07d`` ids keep their
    number (so ``INST-0000001`` → ``G3O-I-00000001``, matching the real
    master's first row and keeping fixture output readable); anything else
    falls back to md5, never :func:`hash`, which varies per interpreter run.
    """
    tail = inst_id.rsplit("-", 1)[-1]
    if tail.isdigit():
        return f"G3O-I-{int(tail):08d}"
    digest = int(hashlib.md5(inst_id.encode("utf-8")).hexdigest()[:8], 16)
    return f"G3O-I-{digest % 10**8:08d}"


def inst_dir(run_dir: Path, inst_id: str) -> Path:
    """Institution directory path (creates nothing)."""
    return institution_dir(run_dir, inst_id)


def make_inst_dir(run_dir: Path, inst_id: str) -> Path:
    """Institution directory, created (with its shard parent)."""
    d = institution_dir(run_dir, inst_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def layout_manifest(payload: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
    """A manifest dict carrying the current ``layout_version``.

    ``layout_version`` and ``institution_uids`` are only defaulted, never
    overridden, so a test can still assert either refusal path by passing an
    explicit wrong version or an empty/partial uid map.
    """
    out: dict[str, Any] = dict(payload or {})
    out.update(kw)
    out.setdefault("layout_version", LAYOUT_VERSION)
    out.setdefault(
        "institution_uids",
        {i: uid_for(i) for i in out.get("institutions", [])},
    )
    return out


def write_manifest(run_dir: Path, payload: dict[str, Any] | None = None, **kw: Any) -> Path:
    """Write ``run_dir/manifest.json`` with a valid ``layout_version``."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "manifest.json"
    path.write_text(
        json.dumps(layout_manifest(payload, **kw), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
