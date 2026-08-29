"""Tests for the wave frame sampler (`g3o frame`).

Three properties carry the module and each has its own section below:

* **determinism** — same master + same snapshot + same seed reproduces the frame
  byte-for-byte, and a different seed does not;
* **refusal** — an unfillable request raises instead of short-drawing, which is
  the failure class the module was written to close;
* **timestamp precedence** — `run_id` beats `loaded_at`, because `loaded_at`
  misdates every back-load and would make a stale institution look fresh.

Tier 2 (`draw_recency_weighted`) is exercised only here. In production the
never-inspected pool covers roughly the next 71 waves at n=10,000, so its tests
are the only evidence it works.
"""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from g3o.run.frame.build import (
    build_frame,
    classify_master,
    sha256_file,
    sidecar_path_for,
    subset_frame,
)
from g3o.run.frame.inspection import (
    InspectionSnapshot,
    empty_snapshot,
    last_inspected_at,
    read_snapshot_csv,
    snapshot_from_rows,
    write_snapshot_csv,
)
from g3o.run.frame.sampler import (
    FrameError,
    draw,
    draw_recency_weighted,
    draw_uniform,
    is_duplicate,
    is_eligible,
)

MASTER_FIELDS = [
    "institution_uid",
    "country",
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
            writer.writerow({k: row.get(k, "") for k in MASTER_FIELDS})
    return path


def _row(i: int, **over: str) -> dict[str, str]:
    base = {
        "institution_uid": f"G3O-I-{i:08d}",
        "country": "India" if i % 3 else "Uganda",
        "government_level": "local",
        "institution_type": "municipality",
        "institution_name": f"Institution {i}",
        "website": "",
        "source_dataset_id": "subnational_RAs",
        "duplicate": "0",
    }
    base.update(over)
    return base


def _snapshot(uids: dict[str, datetime]) -> InspectionSnapshot:
    return snapshot_from_rows(
        [(uid, "", moment) for uid, moment in uids.items()],
        snapshot_at=NOW,
        source="test",
    )


# --- eligibility -----------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [("1", True), ("true", True), ("TRUE", True), ("y", True), ("0", False),
     ("", False), ("  ", False), ("false", False), ("2", False)],
)
def test_duplicate_column_reads_all_three_shapes_the_master_carries(value, expected):
    assert is_duplicate({"duplicate": value}) is expected


def test_missing_duplicate_column_is_not_a_duplicate():
    # 19,766 master rows carry NULL here. A truthiness test would drop them all.
    assert is_duplicate({}) is False
    assert is_eligible({}) is True


def test_an_empty_website_is_still_eligible():
    """97.7% of the never-inspected pool has no website; excluding them would
    silently restrict every wave to 11,579 rows, 10,811 of them US districts."""
    assert is_eligible(_row(1, website="")) is True
    assert is_eligible(_row(1, website="https://example.gov")) is True


# --- timestamp precedence --------------------------------------------------


def test_run_id_stamp_beats_loaded_at():
    ran = datetime(2026, 8, 24, 21, 56, 23, tzinfo=timezone.utc)
    loaded = datetime(2026, 8, 26, 8, 38, 6, tzinfo=timezone.utc)
    moment, source = last_inspected_at("r20260824T215623Z-bb4e", loaded)
    assert (moment, source) == (ran, "run_id")


def test_loaded_at_is_the_fallback_for_a_legacy_id():
    loaded = datetime(2026, 8, 26, 8, 38, 6, tzinfo=timezone.utc)
    moment, source = last_inspected_at("20260509-presweep", loaded)
    assert (moment, source) == (loaded, "loaded_at")


def test_a_row_with_neither_is_dropped_not_dated_to_now():
    snapshot = snapshot_from_rows(
        [("G3O-I-00000001", "legacy", None)], snapshot_at=NOW, source="test"
    )
    assert len(snapshot) == 0
    assert snapshot.n_undated == 1


def test_latest_inspection_wins_regardless_of_row_order():
    rows = [
        ("G3O-I-00000001", "r20260824T215623Z-bb4e", None),
        ("G3O-I-00000001", "r20260817T134319Z-3356", None),
    ]
    snapshot = snapshot_from_rows(rows, snapshot_at=NOW, source="test")
    record = snapshot.records["G3O-I-00000001"]
    assert record.last_run_id == "r20260824T215623Z-bb4e"
    assert record.n_sweeps == 2


def test_snapshot_csv_round_trips_with_its_moment(tmp_path):
    snapshot = _snapshot({"G3O-I-00000001": NOW - timedelta(days=10)})
    path = tmp_path / "snap.csv"
    assert write_snapshot_csv(snapshot, path) == 1
    back = read_snapshot_csv(path)
    assert back.snapshot_at == NOW
    assert back.records["G3O-I-00000001"].last_inspected_at == NOW - timedelta(days=10)


def test_a_snapshot_without_its_moment_is_refused(tmp_path):
    path = tmp_path / "snap.csv"
    path.write_text("institution_uid,last_inspected_at\nG3O-I-1,2026-08-01T00:00:00+00:00\n")
    with pytest.raises(ValueError, match="snapshot_at"):
        read_snapshot_csv(path)


# --- the draw --------------------------------------------------------------


def test_uniform_draw_is_deterministic_and_distinct():
    a = draw_uniform(random.Random(7), 1000, 50)
    b = draw_uniform(random.Random(7), 1000, 50)
    c = draw_uniform(random.Random(8), 1000, 50)
    assert a == b
    assert a != c
    assert len(set(a)) == 50


def test_uniform_draw_of_the_whole_pool_is_a_permutation():
    assert sorted(draw_uniform(random.Random(1), 25, 25)) == list(range(25))


def test_recency_weighting_prefers_the_longest_uninspected():
    """Weight is seconds since last inspection, so a 1000x older institution
    should dominate a small draw. Asserted as a rate over seeds, not once:
    a weighted draw is random, and a single seed proves nothing."""
    weights = [1.0] * 50 + [1_000_000.0] * 5
    wins = 0
    for seed in range(60):
        picked = draw_recency_weighted(random.Random(seed), weights, 5)
        wins += sum(1 for i in picked if i >= 50)
    assert wins > 60 * 5 * 0.8


def test_recency_weighting_is_deterministic():
    weights = [float(i + 1) for i in range(100)]
    assert draw_recency_weighted(random.Random(3), weights, 10) == draw_recency_weighted(
        random.Random(3), weights, 10
    )


def test_tier2_only_fires_for_the_shortfall():
    rng = random.Random(0)
    tier1, tier2 = draw(
        rng, size=8, never_inspected=list(range(5)),
        reinspectable=list(range(5, 15)), reinspectable_ages=[100.0] * 10,
    )
    assert len(tier1) == 5
    assert len(tier2) == 3
    assert not set(tier1) & set(tier2)


def test_tier2_stays_dormant_while_tier1_can_fill():
    tier1, tier2 = draw(
        random.Random(0), size=4, never_inspected=list(range(100)),
        reinspectable=[200], reinspectable_ages=[1.0],
    )
    assert len(tier1) == 4
    assert tier2 == []


def test_an_unfillable_request_refuses_rather_than_short_drawing():
    with pytest.raises(FrameError, match="short-drawing"):
        draw(
            random.Random(0), size=10, never_inspected=[1, 2],
            reinspectable=[3], reinspectable_ages=[1.0],
        )


# --- build_frame end to end ------------------------------------------------


def test_build_frame_is_byte_identical_under_the_same_seed(tmp_path):
    master = _master(tmp_path, [_row(i) for i in range(1, 201)])
    snapshot = empty_snapshot(snapshot_at=NOW)
    first = build_frame(
        master, tmp_path / "a.csv", size=40, seed=11, snapshot=snapshot, built_at=NOW
    )
    second = build_frame(
        master, tmp_path / "b.csv", size=40, seed=11, snapshot=snapshot, built_at=NOW
    )
    third = build_frame(
        master, tmp_path / "c.csv", size=40, seed=12, snapshot=snapshot, built_at=NOW
    )
    assert sha256_file(first.frame_csv) == sha256_file(second.frame_csv)
    assert sha256_file(first.frame_csv) != sha256_file(third.frame_csv)
    assert first.sidecar["frame"]["sha256"] == sha256_file(first.frame_csv)


def test_the_frame_carries_the_master_column_layout_exactly(tmp_path):
    master = _master(tmp_path, [_row(i) for i in range(1, 51)])
    result = build_frame(
        master, tmp_path / "f.csv", size=10, seed=1,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
    )
    with open(result.frame_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == MASTER_FIELDS
        assert len(list(reader)) == 10


def test_duplicates_are_excluded_and_counted(tmp_path):
    rows = [_row(i) for i in range(1, 21)] + [
        _row(i, duplicate="1") for i in range(21, 31)
    ]
    master = _master(tmp_path, rows)
    result = build_frame(
        master, tmp_path / "f.csv", size=20, seed=1,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
    )
    assert result.sidecar["pool"]["excluded_duplicate"] == 10
    assert result.sidecar["pool"]["eligible"] == 20
    with open(result.frame_csv, encoding="utf-8", newline="") as f:
        drawn = {r["institution_uid"] for r in csv.DictReader(f)}
    assert all(int(uid.rsplit("-", 1)[1]) <= 20 for uid in drawn)


def test_never_inspected_is_drawn_before_anything_previously_inspected(tmp_path):
    master = _master(tmp_path, [_row(i) for i in range(1, 21)])
    seen = {f"G3O-I-{i:08d}": NOW - timedelta(days=30) for i in range(1, 16)}
    result = build_frame(
        master, tmp_path / "f.csv", size=5, seed=4, snapshot=_snapshot(seen), built_at=NOW
    )
    assert result.n_tier1 == 5
    assert result.n_tier2 == 0
    with open(result.frame_csv, encoding="utf-8", newline="") as f:
        drawn = {r["institution_uid"] for r in csv.DictReader(f)}
    assert not drawn & set(seen)


def test_build_refuses_a_frame_larger_than_the_eligible_pool(tmp_path):
    master = _master(tmp_path, [_row(i) for i in range(1, 11)])
    with pytest.raises(FrameError, match="cannot build a frame"):
        build_frame(
            master, tmp_path / "f.csv", size=25, seed=1,
            snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
        )
    assert not (tmp_path / "f.csv").exists()


def test_the_sidecar_records_every_input_the_frame_depends_on(tmp_path):
    master = _master(tmp_path, [_row(i, website="https://x.gov" if i % 4 else "")
                                for i in range(1, 101)])
    result = build_frame(
        master, tmp_path / "wave.csv", size=20, seed=99,
        snapshot=empty_snapshot(snapshot_at=NOW), label="wave-2", built_at=NOW,
    )
    sidecar = json.loads(sidecar_path_for(result.frame_csv).read_text(encoding="utf-8"))
    assert sidecar["label"] == "wave-2"
    assert sidecar["seed"] == 99
    assert sidecar["master"]["sha256"] == sha256_file(master)
    assert sidecar["master"]["columns"] == MASTER_FIELDS
    assert sidecar["inspection_snapshot"]["snapshot_at"] == NOW.isoformat()
    assert sidecar["tiers"] == {"tier1_never_inspected": 20, "tier2_recency_weighted": 0}
    comp = sidecar["composition"]
    assert comp["n_with_website"] + comp["n_without_website"] == 20
    assert sum(comp["by"]["country"].values()) == 20
    assert sum(comp["by_stratum"].values()) == 20


def test_classify_master_refuses_a_csv_that_is_not_the_master(tmp_path):
    path = tmp_path / "not-master.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(FrameError, match="institution_uid"):
        classify_master(path, empty_snapshot(snapshot_at=NOW))


# --- subset (the smoke draw) ----------------------------------------------


def test_subset_draws_from_the_frame_and_names_its_parent(tmp_path):
    master = _master(tmp_path, [_row(i) for i in range(1, 101)])
    parent = build_frame(
        master, tmp_path / "wave.csv", size=50, seed=5,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
    )
    smoke = subset_frame(parent.frame_csv, tmp_path / "smoke.csv", size=6, seed=5,
                         built_at=NOW)
    with open(parent.frame_csv, encoding="utf-8", newline="") as f:
        wave_uids = {r["institution_uid"] for r in csv.DictReader(f)}
    with open(smoke.frame_csv, encoding="utf-8", newline="") as f:
        smoke_rows = list(csv.DictReader(f))
    assert len(smoke_rows) == 6
    assert {r["institution_uid"] for r in smoke_rows} <= wave_uids
    assert smoke.sidecar["parent_frame"]["sha256"] == sha256_file(parent.frame_csv)


def test_subset_refuses_to_draw_more_than_the_frame_holds(tmp_path):
    master = _master(tmp_path, [_row(i) for i in range(1, 21)])
    parent = build_frame(
        master, tmp_path / "wave.csv", size=5, seed=1,
        snapshot=empty_snapshot(snapshot_at=NOW), built_at=NOW,
    )
    with pytest.raises(FrameError, match="cannot draw"):
        subset_frame(parent.frame_csv, tmp_path / "smoke.csv", size=9, seed=1)


# --- the CLI surface -------------------------------------------------------


def _cli(*argv: str) -> int:
    from g3o.cli import main

    return main(list(argv))


def test_cli_build_writes_the_frame_and_its_sidecar(tmp_path, capsys):
    master = _master(tmp_path, [_row(i) for i in range(1, 101)])
    out = tmp_path / "wave.csv"
    code = _cli(
        "frame", "build", "--master-csv", str(master), "--out", str(out),
        "--size", "10", "--seed", "3", "--assume-none-inspected",
    )
    assert code == 0
    assert out.exists() and sidecar_path_for(out).exists()
    printed = capsys.readouterr().out
    assert "rows       : 10" in printed
    assert "country" in printed


def test_cli_build_refuses_when_no_inspection_source_is_named(tmp_path, capsys):
    master = _master(tmp_path, [_row(i) for i in range(1, 21)])
    code = _cli(
        "frame", "build", "--master-csv", str(master),
        "--out", str(tmp_path / "wave.csv"), "--size", "5", "--seed", "1",
    )
    assert code == 2
    assert "exactly one inspection source" in capsys.readouterr().err
    assert not (tmp_path / "wave.csv").exists()


def test_cli_build_refuses_two_inspection_sources(tmp_path, capsys):
    master = _master(tmp_path, [_row(i) for i in range(1, 21)])
    snap = tmp_path / "snap.csv"
    write_snapshot_csv(empty_snapshot(snapshot_at=NOW), snap)
    code = _cli(
        "frame", "build", "--master-csv", str(master),
        "--out", str(tmp_path / "wave.csv"), "--size", "5", "--seed", "1",
        "--inspected-csv", str(snap), "--assume-none-inspected",
    )
    assert code == 2
    assert "exactly one inspection source" in capsys.readouterr().err


def test_cli_build_exits_2_on_an_unfillable_request(tmp_path, capsys):
    master = _master(tmp_path, [_row(i) for i in range(1, 6)])
    code = _cli(
        "frame", "build", "--master-csv", str(master),
        "--out", str(tmp_path / "wave.csv"), "--size", "50", "--seed", "1",
        "--assume-none-inspected",
    )
    assert code == 2
    assert "cannot build a frame" in capsys.readouterr().err


def test_cli_subset_draws_the_smoke_frame(tmp_path):
    master = _master(tmp_path, [_row(i) for i in range(1, 51)])
    wave = tmp_path / "wave.csv"
    assert _cli(
        "frame", "build", "--master-csv", str(master), "--out", str(wave),
        "--size", "20", "--seed", "2", "--assume-none-inspected",
    ) == 0
    smoke = tmp_path / "smoke.csv"
    assert _cli(
        "frame", "subset", "--frame", str(wave), "--out", str(smoke),
        "--size", "6", "--seed", "2",
    ) == 0
    with open(smoke, encoding="utf-8", newline="") as f:
        assert len(list(csv.DictReader(f))) == 6


def test_cli_snapshot_folds_a_raw_sweeps_dump(tmp_path, capsys):
    """The SELECT runs on the droplet and the folding runs here, so the dump path
    has to make the same decisions the live path does — run id over loaded_at."""
    dump = tmp_path / "sweeps.csv"
    dump.write_text(
        "institution_uid,run_id,loaded_at\n"
        "G3O-I-00000001,r20260824T215623Z-bb4e,2026-08-26T08:38:06+00:00\n"
        "G3O-I-00000001,r20260817T134319Z-3356,2026-08-17T15:04:38+00:00\n"
        "G3O-I-00000002,legacy-run,2026-08-01T00:00:00+00:00\n",
        encoding="utf-8",
    )
    out = tmp_path / "snap.csv"
    code = _cli(
        "frame", "snapshot", "--sweeps-csv", str(dump), "--out", str(out),
        "--snapshot-at", NOW.isoformat(),
    )
    assert code == 0
    snapshot = read_snapshot_csv(out)
    assert snapshot.snapshot_at == NOW
    first = snapshot.records["G3O-I-00000001"]
    assert first.last_inspected_at == datetime(2026, 8, 24, 21, 56, 23, tzinfo=timezone.utc)
    assert first.timestamp_source == "run_id"
    assert first.n_sweeps == 2
    assert snapshot.records["G3O-I-00000002"].timestamp_source == "loaded_at"
    assert "2 institutions" in capsys.readouterr().out


def test_cli_snapshot_refuses_a_dump_without_its_moment(tmp_path, capsys):
    dump = tmp_path / "sweeps.csv"
    dump.write_text("institution_uid,run_id,loaded_at\n", encoding="utf-8")
    code = _cli("frame", "snapshot", "--sweeps-csv", str(dump), "--out", str(tmp_path / "s.csv"))
    assert code == 2
    assert "--snapshot-at" in capsys.readouterr().err


def test_a_snapshot_from_a_dump_drives_a_frame_build(tmp_path):
    """End to end over the seam: dump -> snapshot -> frame, with the inspected
    institutions held out of tier 1."""
    master = _master(tmp_path, [_row(i) for i in range(1, 31)])
    dump = tmp_path / "sweeps.csv"
    dump.write_text(
        "institution_uid,run_id,loaded_at\n"
        + "".join(
            f"G3O-I-{i:08d},r20260824T215623Z-bb4e,2026-08-26T08:38:06+00:00\n"
            for i in range(1, 26)
        ),
        encoding="utf-8",
    )
    snap = tmp_path / "snap.csv"
    assert _cli(
        "frame", "snapshot", "--sweeps-csv", str(dump), "--out", str(snap),
        "--snapshot-at", NOW.isoformat(),
    ) == 0
    out = tmp_path / "wave.csv"
    assert _cli(
        "frame", "build", "--master-csv", str(master), "--out", str(out),
        "--size", "5", "--seed", "1", "--inspected-csv", str(snap),
    ) == 0
    with open(out, encoding="utf-8", newline="") as f:
        drawn = {r["institution_uid"] for r in csv.DictReader(f)}
    assert all(int(uid.rsplit("-", 1)[1]) > 25 for uid in drawn)
