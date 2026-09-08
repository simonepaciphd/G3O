"""The overlay end to end: harvested by the chain, spent by the next plan, guarded.

Three seams are worth an integration test rather than a unit one, because each is a
place where a local change would look correct and be wrong globally:

* the harvest leg must never turn a published run into a stopped one;
* ``plan_run`` must decorate the *sample* and leave the master file alone;
* the resume guard must refuse a run that would classify half its institutions with
  Stage 2 and bypass it for the other half.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from g3o.run.orchestrate.harvest import (
    DEFAULT_OVERLAY_DIRNAME,
    OVERLAY_FILENAME,
    harvest_official_sites,
)
from g3o.run.presweep import PresweepConfig, plan_run
from g3o.run.presweep.planning import build_manifest, config_snapshot
from tests.test_site_overlay import make_run, site

MASTER_FIELDS = [
    "institution_uid", "master_row_id", "country", "government_level", "branch",
    "institution_type", "institution_name", "website", "source_dataset_id",
    "source_url", "source_file", "retrieval_date", "notes", "duplicate",
    "disambiguation",
]


def master_row(n: int, **overrides: Any) -> dict[str, Any]:
    row = {
        "institution_uid": f"G3O-I-{n:08d}",
        "master_row_id": str(n),
        "country": "Testland",
        "government_level": "local",
        "branch": "executive",
        "institution_type": f"type-{n}",
        "institution_name": f"Institution {n}",
        "website": "",
        "source_dataset_id": "synth",
        "source_url": "",
        "source_file": "synth.csv",
        "retrieval_date": "",
        "notes": "",
        "duplicate": "0",
        "disambiguation": "",
    }
    row.update(overrides)
    return row


def write_master(path: Path, rows: list[dict[str, Any]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MASTER_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


# ----------------------------------------------------------------------------------
# the harvest leg
# ----------------------------------------------------------------------------------


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    root = tmp_path / "runs"
    root.mkdir()
    make_run(root, "r20260101T000000Z-aaaa", "2026-01-01", [
        {"uid": "G3O-I-00000001", "iid": "INST-0000001", "site": site("https://alpha.gov/")},
        {"uid": "G3O-I-00000002", "iid": "INST-0000002", "site": site("https://beta.gov/", "medium")},
    ])
    return root


def test_harvest_writes_the_overlay_where_presweep_expects_it(runs_dir: Path):
    result = harvest_official_sites(runs_dir)
    assert result.green
    expected = runs_dir / DEFAULT_OVERLAY_DIRNAME / OVERLAY_FILENAME
    assert Path(result.overlay_path) == expected
    assert expected.is_file()
    assert result.overlay_rows == 2
    assert result.changed is True


def test_a_second_harvest_over_an_unchanged_corpus_changes_nothing(runs_dir: Path):
    """The property that makes 'after every run' cheap: a repeat is a no-op."""
    first = harvest_official_sites(runs_dir)
    second = harvest_official_sites(runs_dir)
    assert second.sha256 == first.sha256
    assert second.changed is False
    assert "unchanged" in second.message


def test_harvesting_again_after_a_new_run_picks_it_up(runs_dir: Path):
    first = harvest_official_sites(runs_dir)
    make_run(runs_dir, "r20260202T000000Z-bbbb", "2026-02-02", [
        {"uid": "G3O-I-00000003", "iid": "INST-0000003", "site": site("https://gamma.gov/")},
    ])
    second = harvest_official_sites(runs_dir)
    assert second.changed is True
    assert second.overlay_rows == first.overlay_rows + 1
    assert second.runs_scanned == 2


def test_the_harvest_never_raises_and_reports_its_failure(tmp_path: Path):
    """The caller may already have published. An exception here would look like a load
    that failed, which is a different and much worse thing to report."""
    result = harvest_official_sites(tmp_path / "does-not-exist")
    assert result.error
    assert "NOT rebuilt" in result.message
    assert result.overlay_rows == 0


def test_history_records_one_line_per_harvest(runs_dir: Path):
    harvest_official_sites(runs_dir)
    harvest_official_sites(runs_dir)
    history = (runs_dir / DEFAULT_OVERLAY_DIRNAME / "history.jsonl").read_text(encoding="utf-8")
    entries = [json.loads(line) for line in history.strip().splitlines()]
    assert len(entries) == 2
    assert [e["changed"] for e in entries] == [True, False]


# ----------------------------------------------------------------------------------
# spending it in plan_run
# ----------------------------------------------------------------------------------


@pytest.fixture
def planned(tmp_path: Path, runs_dir: Path):
    """A master of two institutions, one of which the overlay covers at ``high``."""
    harvest_official_sites(runs_dir)
    overlay = runs_dir / DEFAULT_OVERLAY_DIRNAME / OVERLAY_FILENAME
    master = write_master(tmp_path / "master.csv", [master_row(1), master_row(2)])
    config = PresweepConfig(
        run_id="20260830-test",
        runs_dir=tmp_path / "planned-runs",
        master_csv=master,
        sample_size=2,
        seed=1,
        dry_run=True,
        official_sites_csv=overlay,
    )
    return config, plan_run(config), master


def test_the_sample_is_decorated_at_the_configured_floor(planned):
    _, plan, _ = planned
    by_uid = {row["institution_uid"]: row for row in plan.sample}
    assert by_uid["G3O-I-00000001"]["official_site_url"] == "https://alpha.gov/"
    assert by_uid["G3O-I-00000001"]["official_site_confidence"] == "high"
    # the medium pick is below the default floor and must not appear
    assert not by_uid["G3O-I-00000002"].get("official_site_url")


def test_the_decoration_reaches_the_stage_2_bypass_surface(planned):
    """``institution.json`` is what Stage 2 reads; the bypass keys on this exact field."""
    _, plan, _ = planned
    from g3o.common.paths import institution_dir
    from g3o.run.presweep.records import institution_record, synth_institution_id

    row = next(r for r in plan.sample if r["institution_uid"] == "G3O-I-00000001")
    assert institution_record(row)["official_site_url"] == "https://alpha.gov/"
    written = json.loads(
        (institution_dir(plan.run_dir, synth_institution_id(row)) / "institution.json")
        .read_text(encoding="utf-8")
    )
    assert written["official_site_url"] == "https://alpha.gov/"


def test_the_master_file_is_never_written(planned):
    """The registry is read-only. The decoration lives in memory, after the draw."""
    _, _, master = planned
    rows = list(csv.DictReader(master.open(encoding="utf-8", newline="")))
    assert "official_site_url" not in rows[0]
    assert all(not r["website"] for r in rows)


def test_the_manifest_accounts_for_what_was_spent(planned):
    _, plan, _ = planned
    block = plan.manifest["run_official_sites"]
    assert block["eligible_sites"] == 1
    assert block["skipped_below_confidence"] == 1
    assert block["applied_to_sample"] == 1
    assert block["sample_size"] == 2
    assert plan.manifest["config"]["official_sites_hash"] == block["content_hash"]


def test_no_overlay_configured_leaves_the_manifest_exactly_as_before(tmp_path: Path):
    master = write_master(tmp_path / "master.csv", [master_row(1)])
    config = PresweepConfig(
        run_id="20260830-plain", runs_dir=tmp_path / "runs2", master_csv=master,
        sample_size=1, seed=1, dry_run=True,
    )
    plan = plan_run(config)
    assert "run_official_sites" not in plan.manifest
    assert plan.manifest["config"]["official_sites_csv"] is None
    assert plan.manifest["config"]["official_sites_hash"] is None
    assert not plan.sample[0].get("official_site_url")


# ----------------------------------------------------------------------------------
# the resume guard
# ----------------------------------------------------------------------------------


def test_resuming_into_an_overlay_is_refused(planned, tmp_path: Path):
    """A run that classified with Stage 2 and resumes bypassing it is two instruments.

    The tolerance for a manifest that predates the overlay keys must not extend to a
    resume that has *started* spending one — that is precisely the mixed measurement
    the guard exists to prevent.
    """
    from g3o.common.run_state import state_dir

    config, plan, _ = planned
    # The plan above already recorded an overlay. Rewrite its manifest to the shape a
    # pre-2026-08-30 run would have left, then mark it resumable.
    manifest_path = plan.run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("run_official_sites", None)
    for key in list(manifest["config"]):
        if key.startswith("official_sites"):
            manifest["config"].pop(key)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)

    with pytest.raises(RuntimeError, match="official_sites"):
        plan_run(config)


def test_an_old_manifest_still_resumes_when_no_overlay_is_configured(tmp_path: Path):
    """The tolerance that makes r20260829T121145Z-233a resumable on this code."""
    from g3o.common.run_state import state_dir

    master = write_master(tmp_path / "master.csv", [master_row(1)])
    config = PresweepConfig(
        run_id="20260830-old", runs_dir=tmp_path / "runs3", master_csv=master,
        sample_size=1, seed=1, dry_run=True,
    )
    plan = plan_run(config)
    manifest_path = plan.run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in list(manifest["config"]):
        if key.startswith("official_sites"):
            manifest["config"].pop(key)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    state_dir(plan.run_dir).mkdir(parents=True, exist_ok=True)

    plan_run(config)  # must not raise


def test_the_config_hash_moves_with_the_overlay_but_not_with_its_path(planned):
    """Identity is what the overlay contributed, not where the file sits."""
    from g3o.run.telemetry import config_hash

    config, plan, _ = planned
    block = plan.manifest["run_official_sites"]
    here = config_hash(config_snapshot(config, official_sites_block=block))
    moved = dict(block)
    elsewhere_config = config_snapshot(config, official_sites_block=moved)
    elsewhere_config["official_sites_csv"] = "/somewhere/else/official_sites.csv"
    assert config_hash(elsewhere_config) == here

    different = dict(block, content_hash="0" * 64)
    assert config_hash(config_snapshot(config, official_sites_block=different)) != here


def test_build_manifest_without_a_block_is_the_pre_change_shape(tmp_path: Path):
    master = write_master(tmp_path / "master.csv", [master_row(1)])
    config = PresweepConfig(
        run_id="20260830-shape", runs_dir=tmp_path / "runs4", master_csv=master,
        sample_size=1, seed=1, dry_run=True,
    )
    manifest = build_manifest(config, [master_row(1)])
    assert "run_official_sites" not in manifest
    assert manifest["config"]["official_sites_hash"] is None
