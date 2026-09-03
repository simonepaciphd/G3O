"""Tests for the experiment-only parent-chain file join.

Two of these tests are the reason the module was allowed into the repo at all.
**PI ruling, 2026-09-02:** *the parent chain enters the repo as an opt-in path the
6b A/B uses and nothing else; production frame builds untouched* — and the ruling
noted explicitly that someone has to keep it experiment-only, because a comment
saying "experiment only" is not enforcement. So:

* :func:`test_no_production_module_imports_the_experiment_package` walks the
  import graph of every module under ``g3o/`` and fails if anything outside
  ``g3o/experiments`` names it. This is the structural half.
* :func:`test_default_frame_build_does_not_read_the_crosswalk_csvs` and its
  stratified twin trace **every file open** during a real frame build and assert
  the build touched the master, the frame and the frame's sidecar and nothing
  else. This is the behavioural half, and it is written as an allowlist rather
  than a blocklist on purpose: it fails on *any* new data dependency in the
  production frame path, not only on the four files named today.

The rest assert the join itself — the three-level walk, and that every way the
crosswalk can be absent or misshapen raises instead of returning a chain that is
quietly missing parents.
"""

from __future__ import annotations

import ast
import builtins
import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from g3o.experiments.parent_chain import (
    CROSSWALK_FILES,
    ParentChainUnavailable,
    load_parent_chain,
)
from g3o.run.frame.build import (
    build_frame,
    build_stratified_frame,
    sidecar_path_for,
)
from g3o.run.frame.inspection import empty_snapshot
from g3o.run.frame.quota import StratumSpec

REPO_ROOT = Path(__file__).resolve().parent.parent
PKG_ROOT = REPO_ROOT / "g3o"
EXPERIMENTS = PKG_ROOT / "experiments"

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)

MASTER_FIELDS = [
    "institution_uid",
    "country",
    "country_iso3",
    "government_level",
    "institution_type",
    "institution_name",
    "website",
    "source_dataset_id",
    "duplicate",
]


# --- fixtures: a four-node tree and three institutions on it ---------------
#
# USA (depth 0) -> KS (depth 1, ADM1) -> Pottawatomie County (depth 2)
# and a second ADM1 with no children, so `adm1_of` is not trivially total.
#
# The institutions mirror the three real shapes WS9 found:
#   I1  a township whose primary edge is the COUNTY (no township node exists),
#       so own = the county and parent = the state. This is the shape that
#       produced the one published misattribution Stage 8 found.
#   I2  an edge onto the ADM1 itself, whose depth-1 ancestor is the country.
#   I3  an unattributed sentinel: it has an edge and no usable parent.

JURISDICTIONS = [
    {
        "jurisdiction_uid": "J-USA", "parent_uid": "", "country_iso3": "USA",
        "admin_depth": "0", "level_local": "country", "name_official": "United States",
        "name_norm": "unitedstates",
    },
    {
        "jurisdiction_uid": "J-KS", "parent_uid": "J-USA", "country_iso3": "USA",
        "admin_depth": "1", "level_local": "state", "name_official": "KS",
        "name_norm": "ks",
    },
    {
        "jurisdiction_uid": "J-POTT", "parent_uid": "J-KS", "country_iso3": "USA",
        "admin_depth": "2", "level_local": "county",
        "name_official": "Pottawatomie County", "name_norm": "pottawatomiecounty",
    },
    {
        "jurisdiction_uid": "J-ND", "parent_uid": "J-USA", "country_iso3": "USA",
        "admin_depth": "1", "level_local": "state", "name_official": "ND",
        "name_norm": "nd",
    },
]

CLOSURE = [
    ("J-USA", "J-USA", 0),
    ("J-KS", "J-KS", 0),
    ("J-KS", "J-USA", 1),
    ("J-POTT", "J-POTT", 0),
    ("J-POTT", "J-KS", 1),
    ("J-POTT", "J-USA", 2),
    ("J-ND", "J-ND", 0),
    ("J-ND", "J-USA", 1),
]

EDGES = [
    {
        "institution_uid": "G3O-I-1", "jurisdiction_uid": "J-POTT", "is_primary": "True",
        "relation": "contained_in", "confidence": "high", "unattributed_reason": "",
        "method": "exact",
    },
    {
        "institution_uid": "G3O-I-2", "jurisdiction_uid": "J-KS", "is_primary": "True",
        "relation": "is_unit", "confidence": "high", "unattributed_reason": "",
        "method": "exact",
    },
    {
        "institution_uid": "G3O-I-3", "jurisdiction_uid": "J-POTT", "is_primary": "true",
        "relation": "contained_in", "confidence": "low",
        "unattributed_reason": "no_grammar", "method": "sentinel",
    },
    # not primary: must be skipped, not treated as a second edge for I-1
    {
        "institution_uid": "G3O-I-1", "jurisdiction_uid": "J-KS", "is_primary": "False",
        "relation": "contained_in", "confidence": "medium", "unattributed_reason": "",
        "method": "exact",
    },
]

BLOCKS = [
    {
        "master_source_file": "us_townships.xlsx", "country_iso3": "USA",
        "government_level": "local", "publishable_at_adm1": "True",
    },
    {
        "master_source_file": "us_counties.xlsx", "country_iso3": "USA",
        "government_level": "second_subnational", "publishable_at_adm1": "False",
    },
]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _crosswalk(tmp_path: Path, *, edges: list[dict[str, str]] | None = None) -> Path:
    out = tmp_path / "outputs"
    _write_csv(
        out / "jurisdictions.csv",
        [
            "jurisdiction_uid", "master_build_id", "parent_uid", "country_iso3",
            "admin_depth", "level_local", "name_official", "name_norm",
        ],
        [{**row, "master_build_id": "mb-test"} for row in JURISDICTIONS],
    )
    _write_csv(
        out / "jurisdiction_closure.csv",
        ["ancestor_uid", "descendant_uid", "master_build_id", "depth"],
        [
            {
                "ancestor_uid": a, "descendant_uid": d,
                "master_build_id": "mb-test", "depth": str(depth),
            }
            for d, a, depth in CLOSURE
        ],
    )
    _write_csv(
        out / "institution_jurisdiction.csv",
        [
            "institution_uid", "jurisdiction_uid", "master_build_id", "is_primary",
            "relation", "confidence", "unattributed_reason", "method",
        ],
        [{**row, "master_build_id": "mb-test"} for row in (edges or EDGES)],
    )
    _write_csv(
        out / "jurisdiction_block.csv",
        [
            "master_build_id", "master_source_file", "country_iso3",
            "government_level", "publishable_at_adm1",
        ],
        [{**row, "master_build_id": "mb-test"} for row in BLOCKS],
    )
    return out


# --- the join --------------------------------------------------------------


def test_the_join_walks_own_then_depth1_parent_then_adm1(tmp_path):
    chain = load_parent_chain(_crosswalk(tmp_path))
    assert len(chain) == 3

    township = chain.for_uid("G3O-I-1")
    assert township is not None
    # own is the COUNTY, because no township node exists in the crosswalk.
    assert (township.own_uid, township.own_name, township.own_depth) == (
        "J-POTT", "Pottawatomie County", 2,
    )
    assert (township.parent_uid, township.parent_name, township.parent_depth) == (
        "J-KS", "KS", 1,
    )
    assert (township.adm1_uid, township.adm1_name) == ("J-KS", "KS")
    assert township.has_attributed_parent is True
    assert township.edge_relation == "contained_in"

    # An edge onto the ADM1 itself: its depth-1 ancestor is the country, and the
    # ADM1 ancestor is the node itself (closure depth 0 counts).
    state = chain.for_uid("G3O-I-2")
    assert state is not None
    assert (state.own_uid, state.parent_uid, state.parent_name) == ("J-KS", "J-USA", "United States")
    assert state.adm1_uid == "J-KS"


def test_an_institution_with_no_primary_edge_is_none_not_an_empty_key(tmp_path):
    chain = load_parent_chain(_crosswalk(tmp_path))
    assert chain.for_uid("G3O-I-NOT-THERE") is None
    assert "G3O-I-NOT-THERE" not in chain
    assert "G3O-I-1" in chain


def test_an_unattributed_sentinel_has_no_attributed_parent(tmp_path):
    """It has an edge and a parent *name*, and must still be excluded.

    The 6b strata are defined on ``has_attributed_parent``; 84,471 subnational
    rows are sentinels. A stratum that counted them would put institutions with
    no usable treatment value into the treatment arm.
    """
    chain = load_parent_chain(_crosswalk(tmp_path))
    sentinel = chain.for_uid("G3O-I-3")
    assert sentinel is not None
    assert sentinel.is_unattributed is True
    assert sentinel.parent_name == "KS"  # a name exists ...
    assert sentinel.has_attributed_parent is False  # ... and is still not usable
    assert chain.counts["unattributed_sentinel"] == 1
    assert chain.counts["with_attributed_parent"] == 2


def test_a_second_primary_edge_is_counted_not_silently_taken(tmp_path):
    """First primary wins, extras are counted — Stage 6's behaviour, preserved.

    A non-zero count is a defect in the crosswalk build rather than in the
    reader, so it has to stay visible in ``counts``.
    """
    edges = [
        *EDGES,
        {
            "institution_uid": "G3O-I-1", "jurisdiction_uid": "J-ND",
            "is_primary": "True", "relation": "contained_in", "confidence": "low",
            "unattributed_reason": "", "method": "fuzzy",
        },
    ]
    chain = load_parent_chain(_crosswalk(tmp_path, edges=edges))
    key = chain.for_uid("G3O-I-1")
    assert key is not None
    assert key.own_uid == "J-POTT"  # the first one, not the last
    assert chain.counts["extra_primary_edges_ignored"] == 1


def test_publishable_at_adm1_needs_the_block_flag_and_attribution(tmp_path):
    """The flag is a block property; ``publishable`` is a subset of ``attributed``.

    Counting the block flag alone reads 545,197 on the real frame — 648 rows too
    many — because a sentinel row inside a publishable block is still
    unattributed.
    """
    chain = load_parent_chain(_crosswalk(tmp_path))
    assert chain.publishable_at_adm1("G3O-I-1", "us_townships.xlsx", "USA", "local") is True
    # same publishable block, but the row is a sentinel
    assert chain.publishable_at_adm1("G3O-I-3", "us_townships.xlsx", "USA", "local") is False
    # attributed row, but the block is not publishable
    assert (
        chain.publishable_at_adm1("G3O-I-1", "us_counties.xlsx", "USA", "second_subnational")
        is False
    )
    # a block that does not exist is not publishable, and does not raise
    assert chain.publishable_at_adm1("G3O-I-1", "nope.xlsx", "USA", "local") is False
    assert chain.block_for("nope.xlsx", "USA", "local") is None


def test_the_counts_report_the_shape_of_the_join(tmp_path):
    chain = load_parent_chain(_crosswalk(tmp_path))
    assert chain.counts["jurisdiction_nodes"] == 4
    assert chain.counts["nodes_with_depth1_parent"] == 3
    assert chain.counts["institutions_with_primary_edge"] == 3
    assert chain.counts["blocks"] == 2
    assert chain.counts.get("parent_disagrees_with_closure", 0) == 0


# --- failing loudly -------------------------------------------------------


def test_a_missing_crosswalk_directory_raises_naming_the_files(tmp_path):
    with pytest.raises(ParentChainUnavailable) as excinfo:
        load_parent_chain(tmp_path / "not-here")
    message = str(excinfo.value)
    assert "does not exist" in message
    for name in CROSSWALK_FILES:
        assert name in message


@pytest.mark.parametrize("absent", CROSSWALK_FILES)
def test_one_missing_crosswalk_csv_raises_rather_than_joining_partially(tmp_path, absent):
    out = _crosswalk(tmp_path)
    (out / absent).unlink()
    with pytest.raises(ParentChainUnavailable, match=absent):
        load_parent_chain(out)


def test_a_crosswalk_csv_with_the_wrong_columns_raises_naming_them(tmp_path):
    out = _crosswalk(tmp_path)
    _write_csv(out / "jurisdictions.csv", ["uid", "name"], [{"uid": "x", "name": "y"}])
    with pytest.raises(ParentChainUnavailable) as excinfo:
        load_parent_chain(out)
    assert "jurisdiction_uid" in str(excinfo.value)
    assert "not a WS9 crosswalk" in str(excinfo.value)


def test_a_crosswalk_with_no_primary_edges_raises_rather_than_returning_empty(tmp_path):
    """An empty chain reads as "no institution has a parent", which is a wrong answer."""
    out = _crosswalk(tmp_path, edges=[{**EDGES[3]}])  # the one non-primary edge
    with pytest.raises(ParentChainUnavailable, match="no primary edges"):
        load_parent_chain(out)


def test_load_parent_chain_restores_the_csv_field_limit(tmp_path):
    """Importing or calling this must not change global csv state for the caller."""
    before = csv.field_size_limit()
    load_parent_chain(_crosswalk(tmp_path))
    assert csv.field_size_limit() == before


# --- THE ENFORCEMENT TESTS ------------------------------------------------
#
# These two are what the PI ruling bought. See the module docstring.


def _python_modules() -> list[Path]:
    return sorted(p for p in PKG_ROOT.rglob("*.py") if EXPERIMENTS not in p.parents)


def test_no_production_module_imports_the_experiment_package():
    """Nothing outside ``g3o/experiments`` may name ``g3o.experiments``.

    Parsed rather than grepped so a string mention in a docstring or a comment
    (this file's own siblings do mention it) is not a failure, and an
    ``import`` genuinely is.
    """
    offenders: list[str] = []
    for path in _python_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name == "g3o.experiments" or name.startswith("g3o.experiments."):
                    rel = path.relative_to(REPO_ROOT)
                    offenders.append(f"{rel}:{node.lineno} imports {name}")
    assert not offenders, (
        "the parent chain is experiment-only by PI ruling (2026-09-02) and "
        "production must not reach it:\n  " + "\n  ".join(offenders)
    )


def test_the_experiment_package_is_importable_on_its_own():
    """The other side of the same coin: opt-in means reachable when asked for."""
    import importlib

    module = importlib.import_module("g3o.experiments.parent_chain")
    assert module.load_parent_chain is load_parent_chain


class _OpenTracer:
    """Record every path :func:`open` is called with, then restore it."""

    def __init__(self) -> None:
        self.paths: list[Path] = []
        self._real = builtins.open

    def __enter__(self) -> _OpenTracer:
        real = self._real
        paths = self.paths

        def traced(file, *args, **kwargs):  # noqa: ANN001, ANN202
            if isinstance(file, (str, Path)):
                paths.append(Path(file))
            return real(file, *args, **kwargs)

        builtins.open = traced
        return self

    def __exit__(self, *exc: object) -> None:
        builtins.open = self._real


def _master(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "master.csv"
    _write_csv(path, MASTER_FIELDS, rows)
    return path


def _master_row(i: int, iso3: str = "USA", level: str = "local") -> dict[str, str]:
    return {
        "institution_uid": f"G3O-I-{i:08d}",
        "country": iso3,
        "country_iso3": iso3,
        "government_level": level,
        "institution_type": "municipality",
        "institution_name": f"Township {i}",
        "website": "",
        "source_dataset_id": "us_townships.xlsx",
        "duplicate": "",
    }


def _assert_touched_nothing_but(traced: list[Path], allowed: set[Path], crosswalk: Path) -> None:
    """The allowlist assertion, stated once for both builders.

    Deliberately an allowlist and not "did it open one of the four CSVs": a new
    data dependency in the production frame path is the thing this test exists to
    catch, whatever its filename. Paths under the interpreter's own tree
    (encodings, importlib, the stdlib) are excluded — they are not data.
    """
    import sysconfig

    stdlib = {
        Path(p).resolve()
        for p in (sysconfig.get_paths().get("stdlib"), sysconfig.get_paths().get("purelib"))
        if p
    }

    def is_interpreter_internal(path: Path) -> bool:
        resolved = path.resolve()
        return any(root in resolved.parents for root in stdlib)

    unexpected = [
        path
        for path in traced
        if path.resolve() not in allowed and not is_interpreter_internal(path)
    ]
    assert not unexpected, (
        "a default frame build opened files it should not have. Production frame "
        "builds must read the master and write the frame and its sidecar, and "
        "nothing else — the parent chain is experiment-only (PI ruling "
        f"2026-09-02). Unexpected: {[str(p) for p in unexpected]}"
    )
    # And say the specific thing out loud too, so a failure names the ruling.
    for name in CROSSWALK_FILES:
        assert not any(path.name == name for path in traced), (
            f"a default frame build read {name}; the parent chain is opt-in only."
        )
    assert not any(crosswalk in path.resolve().parents for path in traced)


def test_default_frame_build_does_not_read_the_crosswalk_csvs(tmp_path):
    """The proportional draw: trace every open and allowlist the three real files."""
    crosswalk = _crosswalk(tmp_path).resolve()
    master = _master(tmp_path, [_master_row(i) for i in range(1, 61)])
    out_csv = tmp_path / "frame.csv"
    snapshot = empty_snapshot(snapshot_at=NOW)

    with _OpenTracer() as tracer:
        result = build_frame(
            master, out_csv, size=20, seed=3, snapshot=snapshot, built_at=NOW
        )

    assert result.size == 20
    _assert_touched_nothing_but(
        tracer.paths,
        {master.resolve(), out_csv.resolve(), sidecar_path_for(out_csv).resolve()},
        crosswalk,
    )


def test_default_stratified_frame_build_does_not_read_the_crosswalk_csvs(tmp_path):
    """The stratified draw is the one a wave actually uses, so it gets the same test."""
    crosswalk = _crosswalk(tmp_path).resolve()
    rows = [_master_row(i, "USA") for i in range(1, 41)]
    rows += [_master_row(i, "UGA") for i in range(41, 81)]
    master = _master(tmp_path, rows)
    out_csv = tmp_path / "wave.csv"

    with _OpenTracer() as tracer:
        result = build_stratified_frame(
            master,
            out_csv,
            strata=[
                StratumSpec(name="anglophone", countries=("USA",), size=10, country_cap=10),
                StratumSpec(name="mix", countries=("UGA",), size=10, country_cap=10),
            ],
            seed=5,
            snapshot=empty_snapshot(snapshot_at=NOW),
            built_at=NOW,
        )

    assert result.size == 20
    _assert_touched_nothing_but(
        tracer.paths,
        {master.resolve(), out_csv.resolve(), sidecar_path_for(out_csv).resolve()},
        crosswalk,
    )


def test_the_tracer_would_actually_catch_a_read(tmp_path):
    """A guard on the guard: an assertion that cannot fail is not enforcement."""
    crosswalk = _crosswalk(tmp_path).resolve()
    master = _master(tmp_path, [_master_row(i) for i in range(1, 11)])
    with _OpenTracer() as tracer:
        load_parent_chain(crosswalk)
    with pytest.raises(AssertionError, match="jurisdictions.csv"):
        _assert_touched_nothing_but(tracer.paths, {master.resolve()}, crosswalk)
