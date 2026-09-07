"""The jurisdictional parent chain, read by FILE JOIN. Experiment-only, opt-in.

WS9 Stage 6 measured that a Stage-2 pick is sometimes the institution's *parent
unit*'s website rather than its own, and Stage 6b is the A/B that would test
whether putting the parent unit's name into the leg-1 discovery query helps
(retrieval gain) or hurts (parent contamination). That experiment needs, for a
given ``institution_uid``, the name of the unit its primary jurisdiction edge
sits under. This module is the only thing in the repo that can answer that.

**PI ruling, 2026-09-02, verbatim:** *the parent chain enters the repo as an
opt-in path the 6b A/B uses and nothing else; production frame builds
untouched.*

So read this file as bounded by three things, in order of how much they matter:

1. **Production does not read it, and cannot start to by accident.** There is no
   seam into ``g3o.run.frame.build``, no default path, no environment variable,
   and no CLI subcommand — a caller must import this module and hand it a
   directory. ``tests/test_parent_chain_experiment.py`` asserts both halves: that
   no module outside ``g3o/experiments`` imports this package, and that a default
   frame build (proportional and stratified) opens no file but the master, the
   frame and the frame's sidecar. **A comment saying "experiment only" is not
   enforcement**; the ruling said so explicitly, and those two tests are what the
   ruling bought.
2. **It fails loudly rather than degrading.** A missing directory, a missing
   crosswalk CSV or a missing column raises :class:`ParentChainUnavailable`
   naming the path. There is no "parent unknown, carry on" branch: an experiment
   that silently loses its treatment variable measures nothing and says it
   measured something.
3. **It settles nothing about production.** Stage 5's decision 4 and Stage 6's
   decision 1 — file join, database query after rehearsing the migration, or the
   deferred Shape B master rebuild — are **still open**. The file join is correct
   for measurement and is a second source of truth for production, because the
   four CSVs it reads live in the WS9 workspace and in no repo. Nothing here is
   an argument that it should be promoted.

**The port.** The join is
``agent-workspace/2026-08-30-jurisdictional-relations/code/stage6_parentkey.py``,
whose logic is reproduced rather than re-derived: ``own`` is the primary edge's
target; ``parent`` is that node's ``depth = 1`` ancestor in the closure, which is
cross-checked against ``jurisdictions.parent_uid`` and disagreements are counted;
``adm1`` is the ancestor at ``admin_depth = 1``, which is what ``mv_agg_by_admin1``
groups on. The measured shape on the WS9 artifacts is 713,228 parent keys in
about seven minutes with no database. Two deliberate differences from the script:

- **The master is not read here.** Stage 6's script streamed the master to emit
  one output row per institution; a caller already holding master rows (a frame,
  a probe's draw) needs a lookup, not a second pass over 178 MB.
- **``publishable_at_adm1`` is keyed on the block, not the institution.** The
  block table's key is ``(master_source_file, country_iso3, government_level)``,
  all three of which come from the master row rather than the crosswalk, so it is
  exposed as :meth:`ParentChain.block_for` and the caller supplies them. Stage 6's
  own comment on that flag is preserved at the call site: ``publishable`` is a
  *subset* of ``attributed`` — a sentinel row inside a publishable block is still
  unattributed and is not publishable — and counting the block flag alone reads
  545,197, which is 648 rows too many.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

#: The crosswalk artifacts the join reads, and the columns it needs from each.
#: Checked up front so a missing column is one error naming the file, not a
#: ``KeyError`` forty seconds into a read.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "jurisdictions.csv": (
        "jurisdiction_uid",
        "parent_uid",
        "country_iso3",
        "admin_depth",
        "level_local",
        "name_official",
        "name_norm",
    ),
    "jurisdiction_closure.csv": ("ancestor_uid", "descendant_uid", "depth"),
    "institution_jurisdiction.csv": (
        "institution_uid",
        "jurisdiction_uid",
        "is_primary",
        "relation",
        "confidence",
        "unattributed_reason",
        "method",
    ),
    "jurisdiction_block.csv": (
        "master_source_file",
        "country_iso3",
        "government_level",
        "publishable_at_adm1",
    ),
}

#: In file order, for error messages that list what is missing in a stable order.
CROSSWALK_FILES: tuple[str, ...] = tuple(REQUIRED_COLUMNS)

#: The master's ``notes`` column carries free text past ``csv``'s 128 kB default,
#: and so does the crosswalk's. Raised locally on the reader rather than
#: globally at import, so importing this module changes nothing about a process
#: that did not ask for it.
_CSV_FIELD_LIMIT = 10 * 1024 * 1024

#: ``is_primary`` and ``publishable_at_adm1`` are CSV text, written by different
#: producers across the WS9 stages. Accepted spellings of true, lowercased.
_TRUE = frozenset({"true", "1", "yes", "t"})


class ParentChainUnavailable(RuntimeError):
    """The crosswalk artifacts are absent, unreadable, or the wrong shape.

    Raised instead of returning an empty or partial chain. An experiment that
    quietly loses its treatment variable reports a null result it did not earn.
    """


@dataclass(frozen=True)
class ParentKey:
    """One institution's place in the jurisdiction tree.

    ``own`` is the primary edge's target — **not** necessarily a node for the
    institution itself. Where the crosswalk has no node at the institution's own
    tier (US townships are the standing case) the primary edge is
    ``contained_in`` the county, so ``own_name`` is the county and ``parent_name``
    is the state. A caller comparing a Stage-2 pick against ``own_name`` and
    against ``parent_name`` is asking two different questions, and neither bounds
    the other (STAGE7-FINDINGS.md §6).
    """

    institution_uid: str
    own_uid: str
    own_name: str
    own_depth: int | None
    own_level_local: str
    parent_uid: str | None
    parent_name: str
    parent_depth: int | None
    parent_level_local: str
    adm1_uid: str | None
    adm1_name: str
    is_unattributed: bool
    edge_relation: str
    edge_confidence: str
    edge_method: str

    @property
    def has_attributed_parent(self) -> bool:
        """A usable parent name: a real depth-1 ancestor, not a sentinel edge.

        The 6b strata are defined on this (STAGE6-FINDINGS.md §5.2): 84,471
        subnational rows are unattributed sentinels and have no parent to give.
        """
        return bool(self.parent_uid) and bool(self.parent_name) and not self.is_unattributed


class ParentChain:
    """An in-memory jurisdiction tree plus the institution edges into it.

    Built by :func:`load_parent_chain`. Read-only; holds roughly one dict entry
    per jurisdiction node and one per institution with a primary edge.
    """

    __slots__ = ("_keys", "_blocks", "counts", "crosswalk_dir")

    def __init__(
        self,
        crosswalk_dir: Path,
        keys: dict[str, ParentKey],
        blocks: dict[tuple[str, str, str], dict[str, str]],
        counts: dict[str, int],
    ) -> None:
        self.crosswalk_dir = crosswalk_dir
        self._keys = keys
        self._blocks = blocks
        self.counts = counts

    def __len__(self) -> int:
        return len(self._keys)

    def __contains__(self, institution_uid: str) -> bool:
        return institution_uid in self._keys

    def for_uid(self, institution_uid: str) -> ParentKey | None:
        """The institution's parent key, or ``None`` if it has no primary edge.

        ``None`` is a real answer and not a failure: 6,360 of the master's rows
        are national, which have no jurisdiction edge by construction. Callers
        must distinguish it from ``has_attributed_parent`` being false.
        """
        return self._keys.get(institution_uid)

    def block_for(
        self, master_source_file: str, country_iso3: str, government_level: str
    ) -> dict[str, str] | None:
        """The S6 block row for a master row's ``(source_file, country, level)``."""
        return self._blocks.get((master_source_file, country_iso3, government_level))

    def publishable_at_adm1(
        self,
        institution_uid: str,
        master_source_file: str,
        country_iso3: str,
        government_level: str,
    ) -> bool:
        """Whether this row is publishable at ADM1, block flag **and** attribution.

        ``publishable`` is a subset of ``attributed`` (Stage 5,
        ``stage5_denominator.py``): a sentinel row inside a publishable block is
        still unattributed and is not publishable. Counting the block flag alone
        reads 545,197 — 648 rows too many.
        """
        block = self.block_for(master_source_file, country_iso3, government_level)
        if block is None:
            return False
        if (block.get("publishable_at_adm1") or "").strip().lower() not in _TRUE:
            return False
        key = self._keys.get(institution_uid)
        return key is not None and not key.is_unattributed


def _read(path: Path, required: tuple[str, ...]) -> Iterator[dict[str, str]]:
    """Stream ``path`` as dicts, after checking it has the columns we need."""
    try:
        handle = open(path, encoding="utf-8", newline="")
    except OSError as exc:  # unreadable, not merely absent
        raise ParentChainUnavailable(f"cannot read {path}: {exc}") from exc
    with handle as fh:
        reader = csv.DictReader(fh)
        fieldnames = tuple(reader.fieldnames or ())
        missing = [column for column in required if column not in fieldnames]
        if missing:
            raise ParentChainUnavailable(
                f"{path} is missing {missing}; it has {list(fieldnames[:8])}... "
                f"This is not a WS9 crosswalk {path.name}."
            )
        yield from reader


def _check_dir(crosswalk_dir: Path) -> None:
    """Refuse up front, naming every file that is absent, not just the first."""
    if not crosswalk_dir.is_dir():
        raise ParentChainUnavailable(
            f"crosswalk directory {crosswalk_dir} does not exist. The parent chain "
            f"is an experiment-only file join over the WS9 artifacts "
            f"({', '.join(CROSSWALK_FILES)}); point --crosswalk-dir at the "
            f"`outputs/` directory that holds them."
        )
    absent = [name for name in CROSSWALK_FILES if not (crosswalk_dir / name).is_file()]
    if absent:
        raise ParentChainUnavailable(
            f"{crosswalk_dir} is missing {absent}. All {len(CROSSWALK_FILES)} "
            f"crosswalk CSVs are required; a partial join would return a parent "
            f"for some institutions and silently none for others."
        )


def load_parent_chain(crosswalk_dir: Path | str) -> ParentChain:
    """Join the four WS9 crosswalk CSVs into an ``institution_uid`` -> parent lookup.

    ``crosswalk_dir`` is required and has no default, deliberately: there is no
    configured location for these files, so there is no way for a caller to read
    them without naming them. Raises :class:`ParentChainUnavailable` if the
    directory or any file is absent, unreadable, or the wrong shape.

    On the WS9 artifacts this reads about 175 MB and takes a few minutes; it is
    a batch load, not something to call per row.
    """
    crosswalk_dir = Path(crosswalk_dir)
    _check_dir(crosswalk_dir)
    limit_before = csv.field_size_limit()
    try:
        csv.field_size_limit(_CSV_FIELD_LIMIT)
        return _load(crosswalk_dir)
    finally:
        csv.field_size_limit(limit_before)


def _load(crosswalk_dir: Path) -> ParentChain:
    counts: Counter[str] = Counter()

    # --- nodes -------------------------------------------------------------
    nodes: dict[str, dict[str, object]] = {}
    for row in _read(
        crosswalk_dir / "jurisdictions.csv", REQUIRED_COLUMNS["jurisdictions.csv"]
    ):
        depth = row["admin_depth"]
        nodes[row["jurisdiction_uid"]] = {
            "parent_uid": row["parent_uid"] or None,
            "name_official": row["name_official"],
            "admin_depth": int(depth) if depth else None,
            "level_local": row["level_local"],
        }
    counts["jurisdiction_nodes"] = len(nodes)

    # --- closure: descendant -> depth-1 ancestor, and -> ADM1 ancestor -----
    parent_d1: dict[str, str] = {}
    adm1_of: dict[str, str] = {}
    for row in _read(
        crosswalk_dir / "jurisdiction_closure.csv",
        REQUIRED_COLUMNS["jurisdiction_closure.csv"],
    ):
        descendant, ancestor = row["descendant_uid"], row["ancestor_uid"]
        if int(row["depth"]) == 1:
            parent_d1[descendant] = ancestor
        node = nodes.get(ancestor)
        if node is not None and node["admin_depth"] == 1:
            adm1_of[descendant] = ancestor
    counts["nodes_with_depth1_parent"] = len(parent_d1)
    counts["nodes_with_adm1_ancestor"] = len(adm1_of)

    # --- institution edges: first primary wins, extras counted -------------
    keys: dict[str, ParentKey] = {}
    for row in _read(
        crosswalk_dir / "institution_jurisdiction.csv",
        REQUIRED_COLUMNS["institution_jurisdiction.csv"],
    ):
        if (row["is_primary"] or "").strip().lower() not in _TRUE:
            continue
        uid = row["institution_uid"]
        if uid in keys:
            # Stage 6's behaviour, preserved: the first primary edge wins and
            # the rest are counted. A non-zero count is a defect in the
            # crosswalk build, not in this reader, and it must stay visible.
            counts["extra_primary_edges_ignored"] += 1
            continue
        own_uid = row["jurisdiction_uid"]
        own = nodes.get(own_uid, {})
        parent_uid = parent_d1.get(own_uid)
        if parent_uid is None:
            counts["no_parent_is_root"] += 1
        else:
            counts["with_parent"] += 1
            own_parent = own.get("parent_uid")
            if own_parent and own_parent != parent_uid:
                counts["parent_disagrees_with_closure"] += 1
        parent = nodes.get(parent_uid, {}) if parent_uid else {}
        adm1_uid = adm1_of.get(own_uid)
        adm1 = nodes.get(adm1_uid, {}) if adm1_uid else {}
        if adm1_uid:
            counts["with_adm1"] += 1
        is_unattributed = bool(row["unattributed_reason"])
        if is_unattributed:
            counts["unattributed_sentinel"] += 1
        keys[uid] = ParentKey(
            institution_uid=uid,
            own_uid=own_uid,
            own_name=str(own.get("name_official", "")),
            own_depth=own.get("admin_depth"),  # type: ignore[arg-type]
            own_level_local=str(own.get("level_local", "")),
            parent_uid=parent_uid,
            parent_name=str(parent.get("name_official", "")),
            parent_depth=parent.get("admin_depth"),  # type: ignore[arg-type]
            parent_level_local=str(parent.get("level_local", "")),
            adm1_uid=adm1_uid,
            adm1_name=str(adm1.get("name_official", "")),
            is_unattributed=is_unattributed,
            edge_relation=row["relation"],
            edge_confidence=row["confidence"],
            edge_method=row["method"],
        )
    counts["institutions_with_primary_edge"] = len(keys)
    counts["with_attributed_parent"] = sum(
        1 for key in keys.values() if key.has_attributed_parent
    )

    # --- blocks ------------------------------------------------------------
    blocks: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in _read(
        crosswalk_dir / "jurisdiction_block.csv",
        REQUIRED_COLUMNS["jurisdiction_block.csv"],
    ):
        blocks[
            (row["master_source_file"], row["country_iso3"], row["government_level"])
        ] = row
    counts["blocks"] = len(blocks)

    if not keys:
        raise ParentChainUnavailable(
            f"{crosswalk_dir}/institution_jurisdiction.csv yielded no primary edges. "
            f"An empty chain is refused rather than returned: every caller would "
            f"read it as 'no institution has a parent'."
        )
    return ParentChain(crosswalk_dir, keys, blocks, dict(counts))


def main(argv: list[str] | None = None) -> int:
    """``python -m g3o.experiments.parent_chain --crosswalk-dir DIR`` — the smoke check.

    Deliberately not a ``g3o`` CLI subcommand: the production CLI is not the
    place to put a switch that reads files production must not read.
    """
    parser = argparse.ArgumentParser(
        prog="python -m g3o.experiments.parent_chain",
        description=(
            "Load the WS9 jurisdiction crosswalk by file join and report the "
            "join's shape. Experiment-only; reads nothing else and writes nothing."
        ),
    )
    parser.add_argument(
        "--crosswalk-dir",
        required=True,
        help="directory holding " + ", ".join(CROSSWALK_FILES),
    )
    parser.add_argument("--uid", action="append", default=[], help="print this uid's parent key")
    args = parser.parse_args(argv)

    try:
        chain = load_parent_chain(args.crosswalk_dir)
    except ParentChainUnavailable as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    sys.stdout.write(json.dumps(chain.counts, indent=2) + "\n")
    for uid in args.uid:
        key = chain.for_uid(uid)
        sys.stdout.write(
            f"\n{uid}: "
            + (json.dumps(dataclasses.asdict(key), indent=2) if key else "no primary edge")
            + "\n"
        )
    return 0


__all__ = [
    "CROSSWALK_FILES",
    "REQUIRED_COLUMNS",
    "ParentChain",
    "ParentChainUnavailable",
    "ParentKey",
    "load_parent_chain",
    "main",
]


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
