"""Shared helpers for building storage-layout-v2 run trees in tests.

Fixtures that hand-build a run tree need two things that layout v2 introduced
(``docs/storage-layout-v2.md``):

- institution directories live at ``institutions/<shard>/<inst_id>/``, so they
  must be constructed via :func:`g3o.common.paths.institution_dir` rather than
  ``run_dir / inst_id``;
- ``manifest.json`` must declare ``layout_version``, or every reader's
  :func:`g3o.common.paths.require_layout` gate refuses the tree.

Keeping both in one place means a future layout bump touches this module and
``g3o/common/paths.py``, not sixty fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from g3o.common.paths import LAYOUT_VERSION, institution_dir

__all__ = [
    "LAYOUT_VERSION",
    "inst_dir",
    "layout_manifest",
    "make_inst_dir",
    "write_manifest",
]


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

    ``layout_version`` is only defaulted, never overridden, so a test can still
    assert the refusal path by passing an explicit wrong version.
    """
    out: dict[str, Any] = dict(payload or {})
    out.update(kw)
    out.setdefault("layout_version", LAYOUT_VERSION)
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
