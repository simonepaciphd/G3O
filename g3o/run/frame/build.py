"""Building a wave frame from the master CSV, and the sidecar that records it.

The master is 719,588 rows and 178 MB, so it is read twice rather than held in
memory: pass 1 classifies every row into a pool by index, pass 2 collects only
the drawn rows. Peak memory is one index list plus ``size`` rows.

**The frame CSV carries the master's column layout exactly.** Nothing is added,
dropped or reordered: ``master_csv_from_manifest`` reads the frame back at ingest
time to pair a run's findings with the population it sampled from, and the
loader keys on the master's own columns.

The sidecar sits beside the frame as ``<name>.frame.json`` and is the thing that
makes a wave reproducible: method, seed, both file hashes, the inspection
snapshot moment, and the composition the draw actually produced. It travels with
the frame rather than living in whatever folder the session that built it was
using, which is the one thing the published wave's otherwise-complete provenance
does not do.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.run.frame.inspection import InspectionSnapshot
from g3o.run.frame.quota import (
    QUOTA_SCHEMA_VERSION,
    StratumSpec,
    allocate_stratum,
    draw_plan,
)
from g3o.run.frame.sampler import FrameError, draw, draw_uniform, is_duplicate

#: Sidecar shape version. Bump when a field changes meaning, not when one is added.
SIDECAR_SCHEMA_VERSION = 1

#: Named in the sidecar so a reader knows which draw produced the file.
METHOD = "never-inspected-first, then weighted by distance from last inspection"

#: The stratified draw's own method string. Deliberately says what it is *not*:
#: a quota frame is not a sample of the master, and every reader of the sidecar
#: should have to notice that before quoting a composition off it.
METHOD_STRATIFIED = (
    "never-inspected only, allocated to ruled strata under per-country caps and "
    "per-level floors — NOT proportional to the master"
)

#: Master columns the stratified draw partitions on.
COUNTRY_KEY = "country_iso3"
LEVEL_KEY = "government_level"

#: Columns whose per-value counts go into the sidecar's composition block, plus
#: the full stratum triple. ``STRATIFY_KEYS`` is the presweep sampler's
#: vocabulary; the frame is proportional rather than stratified, so these are
#: reported, not enforced.
COMPOSITION_KEYS: tuple[str, ...] = (
    "country",
    "government_level",
    "institution_type",
    "source_dataset_id",
)
STRATUM_KEYS: tuple[str, ...] = ("country", "government_level", "institution_type")

_CSV_FIELD_LIMIT = 10 * 1024 * 1024


@dataclass(frozen=True)
class FrameBuildResult:
    """What :func:`build_frame` wrote, and what the sidecar says about it."""

    frame_csv: Path
    sidecar_json: Path
    size: int
    n_tier1: int
    n_tier2: int
    sidecar: dict[str, Any]


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    """Streaming sha256 of ``path``, hex."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _raise_field_limit() -> None:
    """Let the reader survive the master's longest ``notes`` cell.

    ``csv`` defaults to a 128 kB field limit and the master carries free-text
    notes; a frame build that dies two thirds of the way through a 719k-row file
    wastes the read rather than producing a wrong answer, but it wastes it every
    time.
    """
    try:
        csv.field_size_limit(_CSV_FIELD_LIMIT)
    except OverflowError:  # pragma: no cover - 32-bit interpreters only
        csv.field_size_limit(sys.maxsize)


def classify_master(
    master_csv: Path, snapshot: InspectionSnapshot
) -> tuple[list[str], list[int], list[int], list[float], dict[str, int]]:
    """Pass 1: split the master into the two draw pools, by row index.

    Returns ``(fieldnames, never_inspected, reinspectable, ages, counts)``.
    ``ages`` is parallel to ``reinspectable`` and holds seconds since each
    institution's last inspection, measured from ``snapshot.snapshot_at``.
    """
    _raise_field_limit()
    never: list[int] = []
    again: list[int] = []
    ages: list[float] = []
    counts = Counter()
    with open(master_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if "institution_uid" not in fieldnames:
            raise FrameError(
                f"{master_csv} has no institution_uid column (found "
                f"{fieldnames[:6]}...). This is not the institution master."
            )
        for index, row in enumerate(reader):
            counts["master_rows"] += 1
            if is_duplicate(row):
                counts["excluded_duplicate"] += 1
                continue
            counts["eligible"] += 1
            if not (row.get("website") or "").strip():
                counts["eligible_without_website"] += 1
            uid = (row.get("institution_uid") or "").strip()
            age = snapshot.age_seconds(uid)
            if age is None:
                never.append(index)
            else:
                again.append(index)
                ages.append(age)
    counts["never_inspected_eligible"] = len(never)
    counts["previously_inspected_eligible"] = len(again)
    counts["inspected_uids_not_in_eligible_pool"] = len(snapshot) - len(again)
    return fieldnames, never, again, ages, dict(counts)


def collect_rows(master_csv: Path, wanted: list[int]) -> list[dict[str, str]]:
    """Pass 2: read back exactly the rows at ``wanted``, returned in that order."""
    _raise_field_limit()
    positions = {index: slot for slot, index in enumerate(wanted)}
    out: list[dict[str, str] | None] = [None] * len(wanted)
    remaining = len(positions)
    with open(master_csv, encoding="utf-8", newline="") as f:
        for index, row in enumerate(csv.DictReader(f)):
            slot = positions.get(index)
            if slot is None:
                continue
            out[slot] = row
            remaining -= 1
            if remaining == 0:
                break
    missing = [i for i, row in enumerate(out) if row is None]
    if missing:  # pragma: no cover - only reachable if the master changed mid-build
        raise FrameError(
            f"{len(missing)} drawn rows were not found on the second pass of "
            f"{master_csv}. The file changed between passes; nothing was written."
        )
    return [row for row in out if row is not None]


def _write_frame_csv(rows: list[dict[str, str]], fieldnames: list[str], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _composition(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_key = {
        key: dict(Counter((row.get(key) or "").strip() for row in rows).most_common())
        for key in COMPOSITION_KEYS
    }
    strata = Counter(
        "|".join((row.get(key) or "").strip() for key in STRATUM_KEYS) for row in rows
    )
    without_website = sum(1 for row in rows if not (row.get("website") or "").strip())
    return {
        "by": by_key,
        "stratum_keys": list(STRATUM_KEYS),
        "n_strata": len(strata),
        "by_stratum": dict(sorted(strata.items())),
        "n_without_website": without_website,
        "n_with_website": len(rows) - without_website,
    }


def build_frame(
    master_csv: Path,
    out_csv: Path,
    *,
    size: int,
    seed: int,
    snapshot: InspectionSnapshot,
    label: str | None = None,
    built_at: datetime | None = None,
) -> FrameBuildResult:
    """Draw a frame of ``size`` rows from ``master_csv`` and write it with its sidecar.

    Deterministic: the same ``(master_csv, snapshot, size, seed)`` produces the
    same bytes. The sidecar records the sha256 of both the master it read and the
    frame it wrote, so that claim is checkable rather than asserted.
    """
    if size <= 0:
        raise FrameError(f"frame size must be positive, got {size}")
    moment = built_at or datetime.now(timezone.utc)
    fieldnames, never, again, ages, counts = classify_master(master_csv, snapshot)
    rng = random.Random(seed)
    tier1, tier2 = draw(
        rng,
        size=size,
        never_inspected=never,
        reinspectable=again,
        reinspectable_ages=ages,
    )
    drawn = tier1 + tier2
    rows = collect_rows(master_csv, drawn)
    _write_frame_csv(rows, fieldnames, out_csv)

    sidecar_path = sidecar_path_for(out_csv)
    sidecar: dict[str, Any] = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "label": label or out_csv.stem,
        "built_at": moment.astimezone(timezone.utc).isoformat(),
        "method": METHOD,
        "seed": seed,
        "n_requested": size,
        "n_written": len(rows),
        "row_order": "draw order (any prefix is itself an unbiased sample)",
        "master": {
            "path": str(master_csv),
            "sha256": sha256_file(master_csv),
            "rows": counts.get("master_rows", 0),
            "columns": fieldnames,
        },
        "frame": {
            "path": str(out_csv),
            "sha256": sha256_file(out_csv),
            "rows": len(rows),
        },
        "inspection_snapshot": {
            "source": snapshot.source,
            "snapshot_at": snapshot.snapshot_at.isoformat(),
            "n_institutions": len(snapshot),
            "n_undated_sweeps_dropped": snapshot.n_undated,
        },
        "pool": counts,
        "tiers": {
            "tier1_never_inspected": len(tier1),
            "tier2_recency_weighted": len(tier2),
        },
        "composition": _composition(rows),
    }
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return FrameBuildResult(
        frame_csv=out_csv,
        sidecar_json=sidecar_path,
        size=len(rows),
        n_tier1=len(tier1),
        n_tier2=len(tier2),
        sidecar=sidecar,
    )


def classify_master_cells(
    master_csv: Path,
    snapshot: InspectionSnapshot,
    strata: Sequence[StratumSpec],
) -> tuple[list[str], dict[str, dict[tuple[str, str], list[int]]], dict[str, int]]:
    """Pass 1 for the stratified draw: never-inspected row indices per cell.

    A cell is ``(country_iso3, government_level)`` inside one stratum. Rows whose
    country belongs to no stratum are counted and dropped — that is the normal
    case, not an error, because a stratum list names the countries a wave is
    about and the master holds 225.

    Previously-inspected rows are counted and **never drawn**. The proportional
    builder falls back to a recency-weighted second tier; this one does not, and
    refuses instead. Re-inspecting under a quota would make the stratum a mix of
    new coverage and re-measurement with nothing in the frame recording which row
    is which, and 499,338 of 502,946 eligible institutions have never been looked
    at, so the fallback would buy nothing it could not be asked for explicitly.
    """
    _raise_field_limit()
    claimed: dict[str, str] = {}
    for spec in strata:
        for iso3 in spec.countries:
            if iso3 in claimed:
                raise FrameError(
                    f"country {iso3} is listed by both {claimed[iso3]!r} and "
                    f"{spec.name!r}; a country belongs to exactly one stratum."
                )
            claimed[iso3] = spec.name
    cells: dict[str, dict[tuple[str, str], list[int]]] = {s.name: {} for s in strata}
    counts: Counter[str] = Counter()
    with open(master_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for required in ("institution_uid", COUNTRY_KEY, LEVEL_KEY):
            if required not in fieldnames:
                raise FrameError(
                    f"{master_csv} has no {required} column (found {fieldnames[:6]}...). "
                    f"This is not the institution master."
                )
        for index, row in enumerate(reader):
            counts["master_rows"] += 1
            if is_duplicate(row):
                counts["excluded_duplicate"] += 1
                continue
            counts["eligible"] += 1
            stratum = claimed.get((row.get(COUNTRY_KEY) or "").strip())
            if stratum is None:
                counts["outside_every_stratum"] += 1
                continue
            counts["inside_a_stratum"] += 1
            if snapshot.age_seconds((row.get("institution_uid") or "").strip()) is not None:
                counts["previously_inspected_not_drawable"] += 1
                continue
            counts["never_inspected_drawable"] += 1
            if not (row.get("website") or "").strip():
                counts["never_inspected_without_website"] += 1
            cell = (
                (row.get(COUNTRY_KEY) or "").strip(),
                (row.get(LEVEL_KEY) or "").strip(),
            )
            cells[stratum].setdefault(cell, []).append(index)
    return fieldnames, cells, dict(counts)


def build_stratified_frame(
    master_csv: Path,
    out_csv: Path,
    *,
    strata: Sequence[StratumSpec],
    seed: int,
    snapshot: InspectionSnapshot,
    label: str | None = None,
    ruling: str | None = None,
    built_at: datetime | None = None,
) -> FrameBuildResult:
    """Draw a frame under ruled per-stratum quotas. Refuses rather than short-drawing.

    Deterministic in the same sense as :func:`build_frame`: the same
    ``(master_csv, snapshot, strata, seed)`` produces the same bytes. The
    allocation itself is rng-free — only the within-cell draw and the final
    shuffle consume the seed — so a plan can be reviewed before it is drawn.
    """
    if not strata:
        raise FrameError("a stratified frame needs at least one stratum")
    moment = built_at or datetime.now(timezone.utc)
    fieldnames, cells, counts = classify_master_cells(master_csv, snapshot, strata)

    plans: dict[str, dict[tuple[str, str], int]] = {}
    for spec in strata:
        availability = {cell: len(rows) for cell, rows in cells[spec.name].items()}
        plans[spec.name] = allocate_stratum(spec, availability)

    rng = random.Random(seed)
    drawn: list[int] = []
    stratum_sizes: dict[str, int] = {}
    for spec in strata:  # fixed order: the spec list, not dict iteration
        picked = draw_plan(rng, plans[spec.name], cells[spec.name])
        stratum_sizes[spec.name] = len(picked)
        drawn.extend(picked)
    # One more shuffle across strata, so a truncated run is not all Anglophone.
    order = draw_uniform(rng, len(drawn), len(drawn))
    drawn = [drawn[i] for i in order]

    rows = collect_rows(master_csv, drawn)
    _write_frame_csv(rows, fieldnames, out_csv)

    sidecar_path = sidecar_path_for(out_csv)
    sidecar: dict[str, Any] = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "quota_schema_version": QUOTA_SCHEMA_VERSION,
        "label": label or out_csv.stem,
        "built_at": moment.astimezone(timezone.utc).isoformat(),
        "method": METHOD_STRATIFIED,
        "ruling": ruling,
        "seed": seed,
        "n_requested": sum(s.size for s in strata),
        "n_written": len(rows),
        "row_order": (
            "shuffled across strata (any prefix is an unbiased sample OF THE FRAME, "
            "which under a quota is not a sample of the master)"
        ),
        "master": {
            "path": str(master_csv),
            "sha256": sha256_file(master_csv),
            "rows": counts.get("master_rows", 0),
            "columns": fieldnames,
        },
        "frame": {
            "path": str(out_csv),
            "sha256": sha256_file(out_csv),
            "rows": len(rows),
        },
        "inspection_snapshot": {
            "source": snapshot.source,
            "snapshot_at": snapshot.snapshot_at.isoformat(),
            "n_institutions": len(snapshot),
            "n_undated_sweeps_dropped": snapshot.n_undated,
        },
        "pool": counts,
        "strata": [
            {
                **spec.as_dict(),
                "n_drawn": stratum_sizes[spec.name],
                "pool_available": sum(len(r) for r in cells[spec.name].values()),
                "plan": {
                    f"{country}|{level}": n
                    for (country, level), n in sorted(plans[spec.name].items())
                },
            }
            for spec in strata
        ],
        "tiers": {
            "tier1_never_inspected": len(rows),
            "tier2_recency_weighted": 0,
        },
        "composition": _composition(rows),
    }
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return FrameBuildResult(
        frame_csv=out_csv,
        sidecar_json=sidecar_path,
        size=len(rows),
        n_tier1=len(rows),
        n_tier2=0,
        sidecar=sidecar,
    )


def sidecar_path_for(frame_csv: Path) -> Path:
    """``run-frame-n10000.csv`` -> ``run-frame-n10000.frame.json``, beside it."""
    return frame_csv.with_suffix(".frame.json")


def subset_frame(
    frame_csv: Path,
    out_csv: Path,
    *,
    size: int,
    seed: int,
    built_at: datetime | None = None,
) -> FrameBuildResult:
    """Draw ``size`` rows out of an existing frame — the smoke draw.

    A smoke run has to exercise the *population* the wave will run against, not
    just the code: ``smoke-frame-n6.csv`` is six US school districts and would
    have told us nothing about a frame that is 97% non-Anglophone municipalities.
    The subset carries its own sidecar naming the parent frame's sha256.
    """
    _raise_field_limit()
    with open(frame_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if size > len(rows):
        raise FrameError(
            f"cannot draw {size} rows from {frame_csv}, which holds {len(rows)}."
        )
    rng = random.Random(seed)
    picked = [rows[i] for i in draw_uniform(rng, len(rows), size)]
    _write_frame_csv(picked, fieldnames, out_csv)
    moment = built_at or datetime.now(timezone.utc)
    sidecar_path = sidecar_path_for(out_csv)
    sidecar: dict[str, Any] = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "label": out_csv.stem,
        "built_at": moment.astimezone(timezone.utc).isoformat(),
        "method": "uniform subset of an existing frame",
        "seed": seed,
        "n_requested": size,
        "n_written": len(picked),
        "parent_frame": {
            "path": str(frame_csv),
            "sha256": sha256_file(frame_csv),
            "rows": len(rows),
        },
        "frame": {
            "path": str(out_csv),
            "sha256": sha256_file(out_csv),
            "rows": len(picked),
        },
        "composition": _composition(picked),
    }
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return FrameBuildResult(
        frame_csv=out_csv,
        sidecar_json=sidecar_path,
        size=len(picked),
        n_tier1=len(picked),
        n_tier2=0,
        sidecar=sidecar,
    )


def subset_stratified(
    frame_csv: Path,
    out_csv: Path,
    *,
    per_stratum: Mapping[str, int],
    stratum_countries: Mapping[str, Sequence[str]],
    seed: int,
    built_at: datetime | None = None,
) -> FrameBuildResult:
    """Draw a per-stratum subset of a wave frame — the probe draw.

    Uniform *within* each stratum, deliberately: the parent frame already carries
    the ruled country and level composition, so a uniform draw inside a stratum
    reproduces it in expectation without re-imposing quotas on a sample too small
    to fill them. Re-running the allocator at n=300 would fill a 650-row floor
    with nothing and refuse.

    The subset sizes are **not** proportional to the strata, and that is the
    design rather than an oversight. The probe over-samples the stratum whose
    Stage-2 behaviour is unmeasured, because that is the quantity it exists to
    estimate; a balanced draw would buy precision where precision is already
    cheap. The sidecar records the split so nothing downstream can pool the two.
    """
    _raise_field_limit()
    with open(frame_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if COUNTRY_KEY not in fieldnames:
        raise FrameError(f"{frame_csv} has no {COUNTRY_KEY} column; it is not a wave frame.")
    claimed: dict[str, str] = {}
    for name, countries in stratum_countries.items():
        for iso3 in countries:
            if iso3 in claimed:
                raise FrameError(
                    f"country {iso3} is listed by both {claimed[iso3]!r} and {name!r}."
                )
            claimed[iso3] = name
    buckets: dict[str, list[int]] = {name: [] for name in per_stratum}
    unclaimed = 0
    for index, row in enumerate(rows):
        name = claimed.get((row.get(COUNTRY_KEY) or "").strip())
        if name is None or name not in buckets:
            unclaimed += 1
            continue
        buckets[name].append(index)
    rng = random.Random(seed)
    picked_index: list[int] = []
    drawn_per_stratum: dict[str, int] = {}
    for name in per_stratum:  # spec order, not dict-iteration order
        want = per_stratum[name]
        pool = buckets[name]
        if want > len(pool):
            raise FrameError(
                f"cannot draw {want:,} from stratum {name!r}, which holds "
                f"{len(pool):,} rows in {frame_csv}. Refusing rather than "
                f"short-drawing."
            )
        picked_index.extend(pool[i] for i in draw_uniform(rng, len(pool), want))
        drawn_per_stratum[name] = want
    order = draw_uniform(rng, len(picked_index), len(picked_index))
    picked = [rows[picked_index[i]] for i in order]
    _write_frame_csv(picked, fieldnames, out_csv)

    moment = built_at or datetime.now(timezone.utc)
    sidecar_path = sidecar_path_for(out_csv)
    sidecar: dict[str, Any] = {
        "schema_version": SIDECAR_SCHEMA_VERSION,
        "label": out_csv.stem,
        "built_at": moment.astimezone(timezone.utc).isoformat(),
        "method": "per-stratum uniform subset of a stratified frame",
        "seed": seed,
        "n_requested": sum(per_stratum.values()),
        "n_written": len(picked),
        "row_order": "shuffled across strata",
        "parent_frame": {
            "path": str(frame_csv),
            "sha256": sha256_file(frame_csv),
            "rows": len(rows),
        },
        "frame": {
            "path": str(out_csv),
            "sha256": sha256_file(out_csv),
            "rows": len(picked),
        },
        "strata": [
            {
                "name": name,
                "n_drawn": drawn_per_stratum[name],
                "parent_rows": len(buckets[name]),
                "countries": list(stratum_countries[name]),
            }
            for name in per_stratum
        ],
        "parent_rows_in_no_named_stratum": unclaimed,
        "composition": _composition(picked),
    }
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return FrameBuildResult(
        frame_csv=out_csv,
        sidecar_json=sidecar_path,
        size=len(picked),
        n_tier1=len(picked),
        n_tier2=0,
        sidecar=sidecar,
    )


__all__ = [
    "COMPOSITION_KEYS",
    "COUNTRY_KEY",
    "LEVEL_KEY",
    "METHOD",
    "METHOD_STRATIFIED",
    "SIDECAR_SCHEMA_VERSION",
    "STRATUM_KEYS",
    "FrameBuildResult",
    "build_frame",
    "build_stratified_frame",
    "classify_master",
    "classify_master_cells",
    "collect_rows",
    "sha256_file",
    "sidecar_path_for",
    "subset_frame",
    "subset_stratified",
]
