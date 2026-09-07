"""Tests for the stratified draw (`build_stratified_frame` and `g3o.run.frame.quota`).

The quota builder exists because the proportional one cannot express the PI's
2026-08-26 ruling — 5,000 Anglophone + 5,000 mix, no country over 10%, and floors
on the three non-local tiers. Four properties carry it:

* **the allocation is rng-free and exact** — it hits the ruled size, respects
  every cap, and meets every floor, or it raises;
* **scarcest-first ordering is load-bearing** — allocating the abundant tier
  first spends the cap budget and makes the floors unfillable;
* **capped-proportional, not equalising** — shares track the uncapped pool and
  the cap clips only the top, which is the ruled reading and not the one the
  first draft implemented;
* **refusal, not short-drawing** — the failure class the whole module exists to
  close, inherited from `sampler.draw`;
* **determinism** — same master, snapshot, strata and seed reproduce the frame
  byte-for-byte.

The regression that motivated the cap being *across* levels rather than per level
has its own test: at a 10% per-level cap the real wave-2 mix cannot fill its
650-row second-subnational floor, because two of its twelve countries hold no
second-subnational rows at all.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from g3o.run.frame.build import (
    build_stratified_frame,
    classify_master_cells,
    sha256_file,
    sidecar_path_for,
    subset_stratified,
)
from g3o.run.frame.inspection import InspectionSnapshot, empty_snapshot, snapshot_from_rows
from g3o.run.frame.quota import (
    StratumSpec,
    allocate_level,
    allocate_stratum,
    level_targets,
)
from g3o.run.frame.sampler import FrameError

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

NOW = datetime(2026, 8, 26, 16, 0, tzinfo=timezone.utc)


def _master(tmp_path: Path, rows: list[dict[str, str]], name: str = "master.csv") -> Path:
    path = tmp_path / name
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _row(i: int, iso3: str, level: str = "local", **over: str) -> dict[str, str]:
    base = {
        "institution_uid": f"G3O-I-{i:08d}",
        "country": iso3,
        "country_iso3": iso3,
        "government_level": level,
        "institution_type": "municipality",
        "institution_name": f"Institution {i}",
        "website": "",
        "source_dataset_id": "subnational_RAs",
        "duplicate": "0",
    }
    base.update(over)
    return base


def _population(counts: dict[tuple[str, str], int]) -> list[dict[str, str]]:
    """One master's worth of rows: ``{(iso3, level): n}`` in a fixed order."""
    rows: list[dict[str, str]] = []
    i = 0
    for (iso3, level), n in counts.items():
        for _ in range(n):
            i += 1
            rows.append(_row(i, iso3, level))
    return rows


def _snapshot(uids: dict[str, datetime]) -> InspectionSnapshot:
    return snapshot_from_rows(
        [(uid, "", moment) for uid, moment in uids.items()],
        snapshot_at=NOW,
        source="test",
    )


# --- StratumSpec validation ------------------------------------------------


def test_a_cap_that_cannot_reach_the_size_is_refused_at_construction():
    with pytest.raises(FrameError, match="can supply at most 300"):
        StratumSpec(name="mix", countries=("IND", "IDN", "FRA"), size=500, country_cap=100)


def test_floors_that_exceed_the_size_are_refused_at_construction():
    with pytest.raises(FrameError, match="exceed"):
        StratumSpec(
            name="mix",
            countries=("IND", "IDN"),
            size=100,
            country_cap=100,
            level_floors={"national": 60, "local": 60},
        )


def test_a_duplicated_country_is_refused():
    with pytest.raises(FrameError, match="duplicate country"):
        StratumSpec(name="mix", countries=("IND", "IND"), size=10, country_cap=10)


# --- level_targets ---------------------------------------------------------


def test_floors_are_exact_quotas_and_the_residual_goes_to_the_rest():
    targets = level_targets(
        {"national": 500, "local": 9000},
        size=1000,
        level_floors={"national": 200},
    )
    assert targets == {"national": 200, "local": 800}


def test_a_floor_larger_than_the_pool_is_refused_with_the_number():
    with pytest.raises(FrameError, match="exceeds the 40 rows"):
        level_targets({"national": 40, "local": 900}, size=500, level_floors={"national": 200})


def test_the_residual_splits_by_largest_remainder_across_unfloored_levels():
    targets = level_targets(
        {"national": 100, "local": 700, "second_subnational": 300},
        size=110,
        level_floors={"national": 10},
    )
    assert sum(targets.values()) == 110
    assert targets["national"] == 10
    # 100 residual over a 700/300 split
    assert targets["local"] == 70
    assert targets["second_subnational"] == 30


# --- allocate_level --------------------------------------------------------


def test_allocation_respects_headroom_and_places_everything():
    headroom = {"A": 10, "B": 10, "C": 1}
    got = allocate_level(headroom, headroom, 15)
    assert sum(got.values()) == 15
    assert all(got[c] <= h for c, h in headroom.items())


def test_headroom_is_never_exceeded_at_any_target():
    headroom = {"A": 100, "B": 7, "C": 1, "D": 43}
    weights = {"A": 90_000, "B": 7, "C": 1, "D": 43}  # A is capped hard
    total = sum(headroom.values())
    for target in range(0, total + 1):
        got = allocate_level(headroom, weights, target)
        assert sum(got.values()) == target
        assert all(got[c] <= h for c, h in headroom.items()), (target, got)


def test_the_clip_is_redistributed_to_countries_with_room():
    """The loop the balanced allocator did not need, and this one does.

    A holds 90,000 of the 90,051 weight, so its proportional share of 40 is
    nearly all of it — but its cap leaves headroom of 5. The 35 it cannot take
    must land on B, C and D rather than going missing.
    """
    headroom = {"A": 5, "B": 40, "C": 40, "D": 40}
    weights = {"A": 90_000, "B": 17, "C": 17, "D": 17}
    got = allocate_level(headroom, weights, 40)
    assert got["A"] == 5
    assert sum(got.values()) == 40
    assert got["B"] + got["C"] + got["D"] == 35


def test_shares_track_the_pool_not_the_headroom():
    """The ruled reading: a big country stays big until the cap bites."""
    headroom = {"BIG": 500, "SMALL": 500}
    weights = {"BIG": 9_000, "SMALL": 1_000}
    got = allocate_level(headroom, weights, 100)
    assert got["BIG"] == 90 and got["SMALL"] == 10


def test_a_tiny_country_is_rounded_out_rather_than_over_drawn():
    headroom = {"A": 100, "B": 100, "C": 1}
    got = allocate_level(headroom, headroom, 15)
    assert got["C"] == 0
    assert got["A"] + got["B"] == 15


def test_allocation_is_a_pure_function_of_its_inputs():
    headroom = {"A": 7, "B": 11, "C": 13}
    first = allocate_level(headroom, headroom, 17)
    for _ in range(5):
        assert allocate_level(headroom, headroom, 17) == first


def test_ties_break_on_the_country_code_not_on_dict_order():
    forward = allocate_level({"A": 10, "B": 10}, {"A": 10, "B": 10}, 3)
    backward = allocate_level({"B": 10, "A": 10}, {"B": 10, "A": 10}, 3)
    assert forward == backward
    assert forward["A"] == 2 and forward["B"] == 1


def test_more_wanted_than_placeable_refuses():
    with pytest.raises(FrameError, match="cannot place"):
        allocate_level({"A": 2, "B": 2}, {"A": 2, "B": 2}, 10)


# --- allocate_stratum ------------------------------------------------------


def test_the_cap_binds_and_the_floor_is_met():
    spec = StratumSpec(
        name="mix",
        countries=("IND", "IDN", "FRA", "DEU"),
        size=100,
        country_cap=30,
        level_floors={"national": 20},
    )
    availability = {
        ("IND", "local"): 5000, ("IND", "national"): 40,
        ("IDN", "local"): 800, ("IDN", "national"): 30,
        ("FRA", "local"): 400, ("FRA", "national"): 20,
        ("DEU", "local"): 200, ("DEU", "national"): 10,
    }
    plan = allocate_stratum(spec, availability)
    assert sum(plan.values()) == 100
    by_country: dict[str, int] = {}
    for (country, _level), n in plan.items():
        by_country[country] = by_country.get(country, 0) + n
    assert max(by_country.values()) <= 30, by_country
    assert sum(n for (_c, level), n in plan.items() if level == "national") == 20


def test_the_scarce_level_claims_its_cap_budget_before_the_abundant_one():
    """Ordering regression: `local` first would leave nothing for the floor.

    Every country here can supply the whole stratum out of `local` alone, so an
    allocator that visited levels in dict order — `local` first — would spend the
    entire cap budget there and then have no headroom left for the 20 national
    rows the floor demands.
    """
    spec = StratumSpec(
        name="mix",
        countries=("AAA", "BBB"),
        size=40,
        country_cap=20,
        level_floors={"national": 20},
    )
    availability = {
        ("AAA", "local"): 10_000, ("AAA", "national"): 10,
        ("BBB", "local"): 10_000, ("BBB", "national"): 10,
    }
    plan = allocate_stratum(spec, availability)
    assert sum(n for (_c, level), n in plan.items() if level == "national") == 20
    assert sum(plan.values()) == 40


def test_a_stratum_larger_than_its_countries_hold_refuses_with_both_numbers():
    spec = StratumSpec(name="mix", countries=("IND", "IDN"), size=500, country_cap=500)
    with pytest.raises(FrameError, match="short of the 500"):
        allocate_stratum(spec, {("IND", "local"): 100, ("IDN", "local"): 50})


def test_a_per_level_cap_would_break_the_real_wave2_mix_floor():
    """Why `country_cap` is a total, not a per-level bound.

    These are the measured second-subnational pools of the twelve ruled mix
    countries. A 10% *per-level* cap allows 65 from each, and ITA and CZE hold
    none at all, so the ceiling is 596 against a floor of 650 — the frame would
    be refused for a reason that has nothing to do with the ruling.
    """
    second_sub = {
        "IND": 6187, "IDN": 517, "FRA": 101, "DEU": 399, "ESP": 49, "ITA": 0,
        "KAZ": 209, "LAO": 142, "BRA": 27, "RWA": 4891, "CZE": 0, "UZB": 291,
    }
    per_level_cap = 65
    placeable = sum(min(per_level_cap, n) for n in second_sub.values())
    assert placeable == 596
    assert placeable < 650
    capped = {c: min(per_level_cap, n) for c, n in second_sub.items()}
    with pytest.raises(FrameError, match="cannot place"):
        allocate_level(capped, second_sub, 650)


# --- the builder end to end ------------------------------------------------


def _two_stratum_master(tmp_path: Path) -> Path:
    return _master(
        tmp_path,
        _population(
            {
                ("USA", "local"): 300, ("USA", "national"): 20,
                ("GBR", "local"): 200, ("GBR", "national"): 20,
                ("IND", "local"): 400, ("IND", "national"): 20,
                ("IDN", "local"): 150, ("IDN", "national"): 20,
                ("ZZZ", "local"): 500,
            }
        ),
    )


def _two_strata() -> list[StratumSpec]:
    return [
        StratumSpec(
            name="anglophone",
            countries=("USA", "GBR"),
            size=100,
            country_cap=60,
            level_floors={"national": 20},
        ),
        StratumSpec(
            name="mix",
            countries=("IND", "IDN"),
            size=100,
            country_cap=60,
            level_floors={"national": 20},
        ),
    ]


def test_the_stratified_frame_is_byte_identical_under_the_same_seed(tmp_path):
    master = _two_stratum_master(tmp_path)
    snapshot = empty_snapshot(snapshot_at=NOW)
    first = build_stratified_frame(
        master, tmp_path / "a.csv", strata=_two_strata(), seed=7,
        snapshot=snapshot, built_at=NOW,
    )
    second = build_stratified_frame(
        master, tmp_path / "b.csv", strata=_two_strata(), seed=7,
        snapshot=snapshot, built_at=NOW,
    )
    assert sha256_file(first.frame_csv) == sha256_file(second.frame_csv)
    third = build_stratified_frame(
        master, tmp_path / "c.csv", strata=_two_strata(), seed=8,
        snapshot=snapshot, built_at=NOW,
    )
    assert sha256_file(third.frame_csv) != sha256_file(first.frame_csv)


def test_the_frame_holds_exactly_the_ruled_composition(tmp_path):
    master = _two_stratum_master(tmp_path)
    result = build_stratified_frame(
        master, tmp_path / "f.csv", strata=_two_strata(), seed=7,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
    )
    with open(result.frame_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 200
    iso = [r["country_iso3"] for r in rows]
    assert set(iso) == {"USA", "GBR", "IND", "IDN"}  # ZZZ is in no stratum
    assert sum(1 for r in rows if r["country_iso3"] in {"USA", "GBR"}) == 100
    assert sum(1 for r in rows if r["government_level"] == "national") == 40
    for iso3 in ("USA", "GBR", "IND", "IDN"):
        assert iso.count(iso3) <= 60


def test_countries_outside_every_stratum_are_counted_not_drawn(tmp_path):
    master = _two_stratum_master(tmp_path)
    result = build_stratified_frame(
        master, tmp_path / "f.csv", strata=_two_strata(), seed=7,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
    )
    assert result.sidecar["pool"]["outside_every_stratum"] == 500


def test_a_country_claimed_by_two_strata_is_refused(tmp_path):
    master = _two_stratum_master(tmp_path)
    strata = [
        StratumSpec(name="a", countries=("USA", "IND"), size=10, country_cap=10),
        StratumSpec(name="b", countries=("IND",), size=10, country_cap=10),
    ]
    with pytest.raises(FrameError, match="belongs to exactly one stratum"):
        classify_master_cells(master, empty_snapshot(snapshot_at=NOW), strata)


def test_previously_inspected_rows_are_never_drawn_and_are_counted(tmp_path):
    master = _two_stratum_master(tmp_path)
    # Retire the first 30 rows, which are USA/local by construction.
    seen = {f"G3O-I-{i:08d}": NOW for i in range(1, 31)}
    result = build_stratified_frame(
        master, tmp_path / "f.csv", strata=_two_strata(), seed=7,
        snapshot=_snapshot(seen), built_at=NOW,
    )
    with open(result.frame_csv, encoding="utf-8", newline="") as f:
        uids = {r["institution_uid"] for r in csv.DictReader(f)}
    assert not (uids & set(seen))
    assert result.sidecar["pool"]["previously_inspected_not_drawable"] == 30
    assert result.sidecar["tiers"]["tier2_recency_weighted"] == 0


def test_the_sidecar_records_the_spec_the_plan_and_both_hashes(tmp_path):
    master = _two_stratum_master(tmp_path)
    result = build_stratified_frame(
        master, tmp_path / "f.csv", strata=_two_strata(), seed=7,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
        ruling="PI 2026-08-26",
    )
    side = result.sidecar
    assert side["ruling"] == "PI 2026-08-26"
    assert side["master"]["sha256"] == sha256_file(master)
    assert side["frame"]["sha256"] == sha256_file(result.frame_csv)
    assert sidecar_path_for(result.frame_csv).exists()
    names = [s["name"] for s in side["strata"]]
    assert names == ["anglophone", "mix"]
    for stratum in side["strata"]:
        assert stratum["n_drawn"] == stratum["size"]
        assert sum(stratum["plan"].values()) == stratum["size"]
    assert "NOT proportional to the master" in side["method"]


def test_the_frame_is_shuffled_across_strata_so_a_prefix_is_not_one_stratum(tmp_path):
    master = _two_stratum_master(tmp_path)
    result = build_stratified_frame(
        master, tmp_path / "f.csv", strata=_two_strata(), seed=7,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
    )
    with open(result.frame_csv, encoding="utf-8", newline="") as f:
        head = [r["country_iso3"] for r in csv.DictReader(f)][:40]
    assert {"USA", "GBR"} & set(head)
    assert {"IND", "IDN"} & set(head)


def test_the_builder_refuses_when_a_stratum_cannot_be_filled(tmp_path):
    master = _two_stratum_master(tmp_path)
    strata = [
        StratumSpec(name="mix", countries=("IDN",), size=500, country_cap=500),
    ]
    with pytest.raises(FrameError, match="Refusing rather than short-drawing"):
        build_stratified_frame(
            master, tmp_path / "f.csv", strata=strata, seed=7,
            snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
        )
    assert not (tmp_path / "f.csv").exists()


def test_a_master_without_country_iso3_is_refused(tmp_path):
    path = tmp_path / "not-master.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["institution_uid", "government_level"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerow({"institution_uid": "G3O-I-1", "government_level": "local"})
    with pytest.raises(FrameError, match="no country_iso3 column"):
        classify_master_cells(
            path, empty_snapshot(snapshot_at=NOW),
            [StratumSpec(name="a", countries=("USA",), size=1, country_cap=1)],
        )


# --- the probe draw --------------------------------------------------------


def _stratified_frame(tmp_path: Path):
    master = _two_stratum_master(tmp_path)
    return build_stratified_frame(
        master, tmp_path / "wave.csv", strata=_two_strata(), seed=7,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
    )


def test_the_probe_draw_is_unbalanced_on_purpose_and_says_so(tmp_path):
    parent = _stratified_frame(tmp_path)
    result = subset_stratified(
        parent.frame_csv, tmp_path / "probe.csv",
        per_stratum={"anglophone": 20, "mix": 30},
        stratum_countries={"anglophone": ("USA", "GBR"), "mix": ("IND", "IDN")},
        seed=11, built_at=NOW,
    )
    with open(result.frame_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 50
    assert sum(1 for r in rows if r["country_iso3"] in {"USA", "GBR"}) == 20
    assert sum(1 for r in rows if r["country_iso3"] in {"IND", "IDN"}) == 30
    assert {s["name"]: s["n_drawn"] for s in result.sidecar["strata"]} == {
        "anglophone": 20, "mix": 30
    }
    assert result.sidecar["parent_frame"]["sha256"] == sha256_file(parent.frame_csv)


def test_the_probe_draw_is_deterministic_under_its_seed(tmp_path):
    parent = _stratified_frame(tmp_path)
    args = dict(
        per_stratum={"anglophone": 20, "mix": 30},
        stratum_countries={"anglophone": ("USA", "GBR"), "mix": ("IND", "IDN")},
        built_at=NOW,
    )
    a = subset_stratified(parent.frame_csv, tmp_path / "a.csv", seed=11, **args)
    b = subset_stratified(parent.frame_csv, tmp_path / "b.csv", seed=11, **args)
    c = subset_stratified(parent.frame_csv, tmp_path / "c.csv", seed=12, **args)
    assert sha256_file(a.frame_csv) == sha256_file(b.frame_csv)
    assert sha256_file(c.frame_csv) != sha256_file(a.frame_csv)


def test_the_probe_draw_refuses_a_stratum_larger_than_the_frame_holds(tmp_path):
    parent = _stratified_frame(tmp_path)
    with pytest.raises(FrameError, match="Refusing rather than short-drawing"):
        subset_stratified(
            parent.frame_csv, tmp_path / "probe.csv",
            per_stratum={"anglophone": 5000},
            stratum_countries={"anglophone": ("USA", "GBR")},
            seed=11, built_at=NOW,
        )
