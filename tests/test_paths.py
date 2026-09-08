"""Storage layout v2 — :mod:`g3o.common.paths` (spec ``docs/storage-layout-v2.md`` §6).

Covers the four things Phase 1 has to get right:

1. the shard function is deterministic, stable, and spreads;
2. :func:`iter_institution_dirs` yields institution dirs only, in id order,
   and cannot pick up a run-level entry (``_state``, ``final``, reports);
3. :func:`require_layout` refuses a tree that does not declare ``layout_version: 2``;
4. no module outside ``paths.py`` builds an institution path by hand — the
   grep guard, which is what surfaces a site missed during migration.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from g3o.common.paths import (
    INSTITUTIONS_DIRNAME,
    LAYOUT_VERSION,
    institution_dir,
    institution_ids,
    institution_shard,
    institutions_root,
    iter_institution_dirs,
    require_layout,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "g3o"


# ---------------------------------------------------------------------------
# Shard function
# ---------------------------------------------------------------------------


def test_shard_is_two_lowercase_hex_chars() -> None:
    for inst_id in ("INST-0000001", "INST-0719588", "INST-abc", ""):
        shard = institution_shard(inst_id)
        assert re.fullmatch(r"[0-9a-f]{2}", shard), (inst_id, shard)


def test_shard_is_deterministic_across_calls() -> None:
    assert institution_shard("INST-0000042") == institution_shard("INST-0000042")


def test_shard_matches_the_documented_md5_prefix() -> None:
    """Pin the mechanism, not just the property.

    The spec commits to ``md5(inst_id)[:2]`` so that shard assignment survives
    the pending institution-key change; a future refactor that silently swapped
    the digest would relocate every institution directory on disk.
    """
    inst_id = "INST-0000042"
    expected = hashlib.md5(inst_id.encode("utf-8")).hexdigest()[:2]
    assert institution_shard(inst_id) == expected


def test_shard_is_independent_of_master_row_id_numeric_structure() -> None:
    """A non-numeric id shards fine — nothing keys on ``master_row_id``."""
    assert re.fullmatch(r"[0-9a-f]{2}", institution_shard("INST-not-a-number"))


def test_shard_spreads_across_the_full_256_space() -> None:
    shards = {institution_shard(f"INST-{i:07d}") for i in range(20_000)}
    assert len(shards) == 256, len(shards)


def test_shard_spread_is_roughly_even_over_the_frame_envelope() -> None:
    """No shard should dominate; the spec's per-shard estimate assumes evenness."""
    counts: dict[str, int] = {}
    n = 25_600
    for i in range(n):
        shard = institution_shard(f"INST-{i:07d}")
        counts[shard] = counts.get(shard, 0) + 1
    expected = n / 256
    assert max(counts.values()) < expected * 1.5
    assert min(counts.values()) > expected * 0.5


# ---------------------------------------------------------------------------
# Path construction
# ---------------------------------------------------------------------------


def test_institution_dir_shape(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "r1"
    got = institution_dir(run_dir, "INST-0000042")
    assert got.parent.parent == institutions_root(run_dir)
    assert got.name == "INST-0000042"
    assert got.parent.name == institution_shard("INST-0000042")
    assert got.relative_to(run_dir).parts[0] == INSTITUTIONS_DIRNAME


def test_institution_dir_creates_nothing(tmp_path: Path) -> None:
    institution_dir(tmp_path, "INST-0000001")
    assert not (tmp_path / INSTITUTIONS_DIRNAME).exists()


# ---------------------------------------------------------------------------
# iter_institution_dirs
# ---------------------------------------------------------------------------


def _make_run(run_dir: Path, inst_ids: list[str], *, layout_version: int | None = 2) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    if layout_version is not None:
        (run_dir / "manifest.json").write_text(
            json.dumps({"run_id": run_dir.name, "layout_version": layout_version}),
            encoding="utf-8",
        )
    for inst_id in inst_ids:
        institution_dir(run_dir, inst_id).mkdir(parents=True, exist_ok=True)


def test_iter_institution_dirs_is_ordered_by_institution_id(tmp_path: Path) -> None:
    ids = [f"INST-{i:07d}" for i in (7, 1, 30, 2, 19)]
    _make_run(tmp_path, ids)
    assert institution_ids(tmp_path) == sorted(ids)


def test_iter_institution_dirs_ordering_is_not_shard_order(tmp_path: Path) -> None:
    """Guard the ordering choice itself.

    Stage-7 CSV row order is fixed by this walk order, so ``inst_id`` ordering
    is load-bearing: it keeps rows in the order the pre-v2 flat walk produced.
    This test fails if someone "simplifies" the walk to shard-then-id.
    """
    ids = [f"INST-{i:07d}" for i in range(40)]
    _make_run(tmp_path, ids)
    shard_order = sorted(ids, key=lambda i: (institution_shard(i), i))
    assert shard_order != sorted(ids), "fixture too weak to distinguish the orders"
    assert institution_ids(tmp_path) == sorted(ids)


def test_iter_institution_dirs_skips_run_level_entries(tmp_path: Path) -> None:
    """The whole point of the ``institutions/`` level.

    ``_state``, ``final`` and the run-level report files sit beside
    ``institutions/``, so the walk cannot see them and no name filter is
    needed. Before v2, ``final/`` in particular slipped through
    ``report/diff.py``'s filter and was counted as an institution.
    """
    _make_run(tmp_path, ["INST-0000001", "INST-0000002"])
    (tmp_path / "_state" / ".done").mkdir(parents=True)
    (tmp_path / "_state" / ".done" / "scrape.json").write_text("{}", encoding="utf-8")
    (tmp_path / "final").mkdir()
    (tmp_path / "final" / "g3o_activities_v1.csv").write_text("x\n", encoding="utf-8")
    (tmp_path / "attrition.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "_health_report.json").write_text("{}", encoding="utf-8")

    found = institution_ids(tmp_path)
    assert found == ["INST-0000001", "INST-0000002"]
    for leaked in ("_state", "final", ".done", "attrition.jsonl", "_health_report.json"):
        assert leaked not in found


def test_iter_institution_dirs_ignores_stray_files_under_institutions(tmp_path: Path) -> None:
    _make_run(tmp_path, ["INST-0000001"])
    (institutions_root(tmp_path) / "README.txt").write_text("x", encoding="utf-8")
    shard = institutions_root(tmp_path) / institution_shard("INST-0000001")
    (shard / "stray.json").write_text("{}", encoding="utf-8")
    assert institution_ids(tmp_path) == ["INST-0000001"]


def test_iter_institution_dirs_empty_when_level_absent(tmp_path: Path) -> None:
    """A planned-but-empty run reads as empty, not as an error."""
    (tmp_path / "manifest.json").write_text(
        json.dumps({"layout_version": LAYOUT_VERSION}), encoding="utf-8"
    )
    assert list(iter_institution_dirs(tmp_path)) == []


# ---------------------------------------------------------------------------
# require_layout
# ---------------------------------------------------------------------------


def test_require_layout_accepts_a_v2_tree(tmp_path: Path) -> None:
    _make_run(tmp_path, ["INST-0000001"])
    require_layout(tmp_path)  # must not raise


def test_require_layout_refuses_missing_manifest(tmp_path: Path) -> None:
    _make_run(tmp_path, ["INST-0000001"], layout_version=None)
    with pytest.raises(RuntimeError, match="storage-layout-v2"):
        require_layout(tmp_path)


def test_require_layout_refuses_pre_v2_tree(tmp_path: Path) -> None:
    """A pre-v2 run (no marker at all) fails loudly rather than reading as empty."""
    tmp_path.joinpath("manifest.json").write_text(
        json.dumps({"run_id": "old", "institutions": ["INST-0000001"]}), encoding="utf-8"
    )
    (tmp_path / "INST-0000001").mkdir()
    with pytest.raises(RuntimeError, match="layout_version=None"):
        require_layout(tmp_path)


def test_require_layout_refuses_wrong_version(tmp_path: Path) -> None:
    _make_run(tmp_path, ["INST-0000001"], layout_version=1)
    with pytest.raises(RuntimeError, match="layout_version=1"):
        require_layout(tmp_path)


def test_require_layout_refuses_unreadable_manifest(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="could not be read as JSON"):
        require_layout(tmp_path)


def test_require_layout_error_names_the_spec(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError) as excinfo:
        require_layout(tmp_path)
    assert "docs/storage-layout-v2.md" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Grep guard — the net that catches a missed migration site
# ---------------------------------------------------------------------------


#: Hand-built institution paths: ``<something> / <inst-ish name>`` where the
#: right-hand side is an institution identifier rather than a literal filename.
#: Deliberately broad on the left (``run_dir``, ``run_path``, ``out_dir``, ...)
#: and on the right (``inst``, ``inst_id``, ``institution_id``, ``iid``,
#: ``result.custom_id`` -- Stage 2/3 build the directory from the batch
#: ``custom_id``, which a grep for ``inst_id`` alone would miss).
_HAND_BUILT_PATH = re.compile(
    r"""
    (?:run_dir|run_path|runs_dir|out_dir|base_dir|root)   # a run-level dir...
    \s*/\s*                                              # ...joined to...
    (?:                                                  # ...an institution id
        inst\b | inst_id\b | institution_id\b | iid\b
      | institution\[ | result\.custom_id\b | custom_id\b
    )
    """,
    re.VERBOSE,
)

#: ``paths.py`` owns the layout; the spec text quotes the old shape on purpose.
_GUARD_EXEMPT = {Path("g3o/common/paths.py")}


def _python_sources() -> list[Path]:
    return sorted(p for p in PACKAGE_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_module_builds_an_institution_path_by_hand() -> None:
    """Only :mod:`g3o.common.paths` may join a run dir to an institution id.

    This is the guard the spec asks for (§B1): it is what turns "we think we
    found every site" into "a missed site fails the suite". It caught three
    stage modules and three report sites that were not in the spec's own
    migration inventory.
    """
    offenders: list[str] = []
    for path in _python_sources():
        rel = path.relative_to(REPO_ROOT)
        if rel in _GUARD_EXEMPT:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            code = line.split("#", 1)[0]
            if _HAND_BUILT_PATH.search(code):
                offenders.append(f"{rel.as_posix()}:{lineno}: {line.strip()}")
    assert not offenders, (
        "institution paths must be built via g3o.common.paths.institution_dir() "
        "(storage layout v2, docs/storage-layout-v2.md):\n  " + "\n  ".join(offenders)
    )


def test_grep_guard_actually_matches_the_patterns_it_claims_to() -> None:
    """A guard that matches nothing would pass silently forever."""
    for snippet in (
        'path = run_dir / inst_id / "2_official_site.json"',
        "inst_dir = run_dir / result.custom_id",
        "p = run_dir / inst / name",
        "_collect_institution(run_dir / iid, iid)",
        'inst_dir = run_dir / institution["institution_id"]',
    ):
        assert _HAND_BUILT_PATH.search(snippet), snippet
    for ok in (
        'manifest_path = run_dir / "manifest.json"',
        'final_dir = run_dir / "final"',
        "institution_dir(run_dir, inst_id) / 'scrape'",
    ):
        assert not _HAND_BUILT_PATH.search(ok), ok


def test_only_paths_module_is_exempt_from_the_guard() -> None:
    """Keep the exemption list from quietly growing."""
    assert _GUARD_EXEMPT == {Path("g3o/common/paths.py")}
    for rel in _GUARD_EXEMPT:
        assert (REPO_ROOT / rel).is_file()


# ---------------------------------------------------------------------------
# The same guard, for the _state layout (review F4, 2026-08-24)
#
# `run_state` owns `_state/` and `.done/` the way `paths` owns the institution
# tree, and exposes state_dir/done_dir/state_path/done_path. Two consumers had
# rebuilt those paths from string literals anyway. That guard is the whole
# reason `paths.py` has no equivalent drift, so it is worth having twice: an
# invariant that is only remembered is the one that drifts.
# ---------------------------------------------------------------------------


#: A hand-built state path: some run-level dir joined to the ``_state`` or
#: ``.done`` literal. Requires the join expression rather than matching the bare
#: string, because both names appear legitimately in prose all over the package
#: (``run_state``'s own module docstring, ``report/outcomes``, the runbook
#: references in ``cli``) and a guard that fires on documentation is a guard
#: people delete.
_HAND_BUILT_STATE_PATH = re.compile(
    r"""
    (?:run_dir|run_path|runs_dir|out_dir|base_dir|root|state_dir)  # a run-level dir...
    \s*/\s*                                                        # ...joined to...
    (?:"_state"|'_state'|"\.done"|'\.done')                        # ...the layout literal
    """,
    re.VERBOSE,
)

#: ``run_state.py`` owns the layout and is the one module allowed to name it.
_STATE_GUARD_EXEMPT = {Path("g3o/common/run_state.py")}


def test_no_module_builds_a_state_path_by_hand() -> None:
    """Only :mod:`g3o.common.run_state` may join a run dir to ``_state``.

    Caught two real sites when it was written: ``cost_monitor.record_stage``
    (whose sibling ``record_partial_stage``, 240 lines away, used the accessor
    correctly) and ``report.health._stage_ran``. Both failure modes are silent —
    a renamed state dir would have made every stage read as never-run, and made
    every stage's cost read as an accounting failure.
    """
    offenders: list[str] = []
    for path in _python_sources():
        rel = path.relative_to(REPO_ROOT)
        if rel in _STATE_GUARD_EXEMPT:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            code = line.split("#", 1)[0]
            if _HAND_BUILT_STATE_PATH.search(code):
                offenders.append(f"{rel.as_posix()}:{lineno}: {line.strip()}")
    assert not offenders, (
        "state paths must be built via g3o.common.run_state.state_path() / "
        "done_path():\n  " + "\n  ".join(offenders)
    )


def test_state_grep_guard_actually_matches_the_patterns_it_claims_to() -> None:
    """A guard that matches nothing would pass silently forever."""
    for snippet in (
        'done_file = run_dir / "_state" / ".done" / f"{stage}.json"',
        'state_dir = run_dir / "_state"',
        "p = runs_dir / '_state'",
        'return (state_dir / ".done" / f"{stage}.json").exists()',
    ):
        assert _HAND_BUILT_STATE_PATH.search(snippet), snippet
    for ok in (
        "done_path(run_dir, stage).exists()",
        "state_path(run_dir, stage)",
        'manifest_path = run_dir / "manifest.json"',
        # Prose, which is where `_state` legitimately appears everywhere else.
        '    ``_state/{stage}.json`` (active) or ``_state/.done/{stage}.json``',
        '"""Layout under ``runs/<run_id>/_state/``::"""',
    ):
        assert not _HAND_BUILT_STATE_PATH.search(ok), ok


def test_only_run_state_is_exempt_from_the_state_guard() -> None:
    """Keep the exemption list from quietly growing."""
    assert _STATE_GUARD_EXEMPT == {Path("g3o/common/run_state.py")}
    for rel in _STATE_GUARD_EXEMPT:
        assert (REPO_ROOT / rel).is_file()
