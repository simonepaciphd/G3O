"""The official-site overlay: harvest, sharing margins, precedence, idempotence.

The properties under test are the ones that make "rebuild after every run" safe:
determinism (so a repeat is a no-op, not an append), order-independence (so the scan
order of a runs directory cannot change the answer), and a sharing flag that predicts
what Stage 1b will actually do rather than what a naive host comparison suggests.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from g3o.report.site_overlay import (
    OVERLAY_COLUMNS,
    build_overlay,
    harvest_run,
    is_run_dir,
    iter_run_dirs,
    read_overlay,
    write_overlay,
)


def make_run(
    root: Path,
    run_id: str,
    run_date: str,
    institutions: list[dict],
    *,
    git_sha: str = "deadbee",
) -> Path:
    """A minimal layout-v2 run directory carrying only what the harvest reads."""
    run_dir = root / run_id
    (run_dir / "institutions").mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": run_id, "run_date": run_date, "run_model": "gpt-5-nano"}),
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text(
        json.dumps(
            {"event": "run_completed", "ts": f"{run_date}T02:00:00Z", "git_sha": git_sha}
        )
        + "\n",
        encoding="utf-8",
    )
    with (run_dir / "institution_report.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["institution_uid", "institution_id"])
        for spec in institutions:
            writer.writerow([spec.get("uid", ""), spec["iid"]])
    for index, spec in enumerate(institutions):
        inst_dir = run_dir / "institutions" / f"{index:02d}" / spec["iid"]
        inst_dir.mkdir(parents=True, exist_ok=True)
        (inst_dir / "institution.json").write_text(
            json.dumps(
                {
                    "institution_id": spec["iid"],
                    "institution_name": spec.get("name", spec["iid"]),
                    "country": spec.get("country", "Testland"),
                    "level_of_government": "local",
                    "institution_type": "municipality",
                    "website": spec.get("master_website"),
                    "master_row_id": spec["iid"].rsplit("-", 1)[-1],
                }
            ),
            encoding="utf-8",
        )
        (inst_dir / "2_official_site.json").write_text(
            json.dumps(spec.get("site", {"url": None, "confidence": "none"})),
            encoding="utf-8",
        )
    return run_dir


def site(url, confidence="high"):
    return {"url": url, "confidence": confidence, "rationale": "fixture"}


@pytest.fixture
def one_run(tmp_path: Path) -> Path:
    return make_run(
        tmp_path,
        "r20260101T000000Z-aaaa",
        "2026-01-01",
        [
            {"uid": "G3O-I-00000001", "iid": "INST-0000001", "site": site("https://a.nsw.gov.au/")},
            {"uid": "G3O-I-00000002", "iid": "INST-0000002", "site": site("https://nsw.gov.au/council/two")},
            {"uid": "G3O-I-00000003", "iid": "INST-0000003", "site": site("https://nsw.gov.au/council/three")},
            {"uid": "G3O-I-00000004", "iid": "INST-0000004"},  # no site at all
            {"uid": "G3O-I-00000005", "iid": "INST-0000005", "site": site("https://unique.example.org/")},
            {"uid": "G3O-I-00000006", "iid": "INST-0000006", "site": site("https://www.shared.gov.bw/")},
            {"uid": "G3O-I-00000007", "iid": "INST-0000007", "site": site("https://shared.gov.bw/dept")},
        ],
    )


# ----------------------------------------------------------------------------------
# harvest
# ----------------------------------------------------------------------------------


def test_institutions_without_a_site_are_absent_not_blank(one_run: Path):
    """The overlay states what was found; it never carries an empty finding."""
    rows, _ = build_overlay([one_run])
    assert len(rows) == 6
    assert "G3O-I-00000004" not in {r["institution_uid"] for r in rows}


def test_a_bypassed_pick_is_not_harvested(tmp_path: Path):
    """Harvesting a bypass envelope would launder a stored value into an observation.

    The envelope's URL came *from* a master column. Re-harvesting it would stamp this
    run's ``run_id`` and ``git_sha`` on a value this run never discovered, and the next
    round would read it as fresh evidence.
    """
    run = make_run(tmp_path, "r20260101T000000Z-bbbb", "2026-01-01", [
        {"uid": "G3O-I-00000001", "iid": "INST-0000001"},
    ])
    envelope = {"bypassed": True, "source": "master_csv", "url": "https://from-master.gov/"}
    (run / "institutions" / "00" / "INST-0000001" / "2_official_site.json").write_text(
        json.dumps(envelope), encoding="utf-8"
    )
    assert harvest_run(run) == []


def test_provenance_travels_with_every_value(one_run: Path):
    rows, _ = build_overlay([one_run])
    row = {r["institution_uid"]: r for r in rows}["G3O-I-00000005"]
    assert row["run_id"] == "r20260101T000000Z-aaaa"
    assert row["run_date"] == "2026-01-01"
    assert row["run_completed_at"] == "2026-01-01T02:00:00Z"
    assert row["git_sha"] == "deadbee"
    assert row["stage2_model"] == "gpt-5-nano"
    assert row["confidence"] == "high"


def test_a_missing_uid_is_keyed_so_it_can_never_silently_join(tmp_path: Path):
    run = make_run(tmp_path, "r20260101T000000Z-cccc", "2026-01-01", [
        {"uid": "", "iid": "INST-0000009", "site": site("https://orphan.example.gov/")},
    ])
    rows, stats = build_overlay([run])
    assert stats["records_without_uid"] == 1
    assert rows[0]["institution_uid"] == "__NOUID__INST-0000009"


def test_run_dir_detection_needs_both_markers(tmp_path: Path):
    (tmp_path / "half").mkdir()
    (tmp_path / "half" / "institutions").mkdir()
    assert not is_run_dir(tmp_path / "half")
    run = make_run(tmp_path, "r20260101T000000Z-dddd", "2026-01-01", [])
    assert is_run_dir(run)


def test_the_overlays_own_output_directory_is_not_scanned_as_a_run(tmp_path: Path):
    """``_site_overlay`` lives under ``runs_dir``; scanning it as a run would recurse."""
    make_run(tmp_path, "r20260101T000000Z-eeee", "2026-01-01", [])
    overlay_dir = tmp_path / "_site_overlay"
    (overlay_dir / "institutions").mkdir(parents=True)
    (overlay_dir / "manifest.json").write_text("{}", encoding="utf-8")
    assert [d.name for d in iter_run_dirs(tmp_path)] == ["r20260101T000000Z-eeee"]


# ----------------------------------------------------------------------------------
# the three sharing margins
# ----------------------------------------------------------------------------------


def test_exact_host_sharing_is_heuristic_free(one_run: Path):
    rows = {r["institution_uid"]: r for r in build_overlay([one_run])[0]}
    assert rows["G3O-I-00000002"]["host_share_count"] == "2"
    # a subdomain is not the bare domain
    assert rows["G3O-I-00000001"]["host_share_count"] == "1"


def test_site_host_folds_www_because_stage_1b_does(one_run: Path):
    """The margin that predicts Stage 1b, and the one an exact-host flag gets wrong.

    ``www.shared.gov.bw`` and ``shared.gov.bw`` are two exact hosts and one ``site:``
    target. A flag keyed on the exact host promises a uniqueness the query does not have.
    """
    rows = {r["institution_uid"]: r for r in build_overlay([one_run])[0]}
    assert rows["G3O-I-00000006"]["host_share_count"] == "1"
    assert rows["G3O-I-00000007"]["host_share_count"] == "1"
    assert rows["G3O-I-00000006"]["site_host_share_count"] == "2"
    assert rows["G3O-I-00000007"]["site_host_share_count"] == "2"


def test_registrable_domain_uses_the_real_public_suffix_list(one_run: Path):
    """All three NSW rows share a registrable domain; the subdomain still counts."""
    rows = {r["institution_uid"]: r for r in build_overlay([one_run])[0]}
    for uid in ("G3O-I-00000001", "G3O-I-00000002", "G3O-I-00000003"):
        assert rows[uid]["registrable_domain"] == "nsw.gov.au"
        assert rows[uid]["domain_share_count"] == "3"


def test_the_path_is_kept_but_the_site_root_drops_it(one_run: Path):
    """Stage 1b never sees a path. It is stored for a human adjudicating a pick."""
    row = {r["institution_uid"]: r for r in build_overlay([one_run])[0]}["G3O-I-00000002"]
    assert row["url_path"] == "/council/two"
    assert row["site_root"] == "https://nsw.gov.au/"
    assert row["discovered_url_raw"] == "https://nsw.gov.au/council/two"


# ----------------------------------------------------------------------------------
# idempotence — the property that makes "after every run" safe
# ----------------------------------------------------------------------------------


def test_rebuilding_over_the_same_inputs_is_byte_identical(one_run: Path, tmp_path: Path):
    first = write_overlay(build_overlay([one_run])[0], tmp_path / "a.csv")
    second = write_overlay(build_overlay([one_run])[0], tmp_path / "b.csv")
    assert first == second
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()


def test_run_dir_order_does_not_change_the_output(one_run: Path, tmp_path: Path):
    other = make_run(tmp_path, "r20260202T000000Z-ffff", "2026-02-02", [
        {"uid": "G3O-I-00000010", "iid": "INST-0000010", "site": site("https://z.example.net/")},
    ])
    forward = write_overlay(build_overlay([one_run, other])[0], tmp_path / "f.csv")
    backward = write_overlay(build_overlay([other, one_run])[0], tmp_path / "b.csv")
    assert forward == backward


def test_read_overlay_refuses_a_csv_that_is_not_one(tmp_path: Path):
    path = tmp_path / "not-an-overlay.csv"
    path.write_text("institution_uid,website\nG3O-I-1,https://x.gov/\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        read_overlay(path)


def test_written_overlay_round_trips(one_run: Path, tmp_path: Path):
    rows, _ = build_overlay([one_run])
    write_overlay(rows, tmp_path / "o.csv")
    back = read_overlay(tmp_path / "o.csv")
    assert len(back) == len(rows)
    assert set(back[0]) == set(OVERLAY_COLUMNS)


# ----------------------------------------------------------------------------------
# cross-run conflict
# ----------------------------------------------------------------------------------


@pytest.fixture
def disagreeing_runs(one_run: Path, tmp_path: Path) -> tuple[Path, Path]:
    newer = make_run(tmp_path, "r20260303T000000Z-gggg", "2026-03-03", [
        {
            "uid": "G3O-I-00000005",
            "iid": "INST-0000005",
            "site": site("https://newer-but-medium.example.com/", "medium"),
        },
    ])
    return one_run, newer


def test_confidence_then_recency_keeps_the_better_pick(disagreeing_runs):
    older, newer = disagreeing_runs
    rows = {r["institution_uid"]: r for r in build_overlay([older, newer])[0]}
    row = rows["G3O-I-00000005"]
    assert row["site_host"] == "unique.example.org"
    assert row["n_run_observations"] == "2"
    assert row["superseded_run_ids"] == "r20260303T000000Z-gggg"
    assert row["conflicting_hosts"] == "newer-but-medium.example.com"


def test_recency_then_confidence_takes_the_newer_pick(disagreeing_runs):
    older, newer = disagreeing_runs
    rows = {
        r["institution_uid"]: r
        for r in build_overlay([older, newer], precedence="recency-then-confidence")[0]
    }
    assert rows["G3O-I-00000005"]["site_host"] == "newer-but-medium.example.com"


def test_an_unknown_precedence_is_refused(one_run: Path):
    with pytest.raises(ValueError, match="unknown precedence"):
        build_overlay([one_run], precedence="whatever-is-newest")
