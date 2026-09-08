"""Spending the overlay: the confidence floor, the shared-host filter, and the guard.

Everything here is about a run *changing what it does* because of a file, so the tests
are weighted towards the refusals and towards what the manifest records — the two things
that make the change auditable after the fact.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from g3o.report.site_overlay import OVERLAY_COLUMNS
from g3o.run.presweep.official_sites import (
    OfficialSitesError,
    apply_to_rows,
    load_bypass_map,
)


def write_overlay_csv(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(OVERLAY_COLUMNS), lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in OVERLAY_COLUMNS})
    return path


def overlay_row(uid, root, *, confidence="high", site_share="1", host=None):
    return {
        "institution_uid": uid,
        "site_root": root,
        "site_host": host or root.split("//", 1)[1].rstrip("/"),
        "confidence": confidence,
        "site_host_share_count": site_share,
        "host_share_count": "1",
        "domain_share_count": "1",
    }


@pytest.fixture
def overlay(tmp_path: Path) -> Path:
    return write_overlay_csv(
        tmp_path / "official_sites.csv",
        [
            overlay_row("G3O-I-00000001", "https://alpha.gov/"),
            overlay_row("G3O-I-00000002", "https://beta.gov/", confidence="medium"),
            overlay_row("G3O-I-00000003", "https://gamma.gov/", confidence="low"),
            overlay_row("G3O-I-00000004", "https://nsw.gov.au/", site_share="95"),
            overlay_row("G3O-I-00000005", "https://delta.gov/"),
        ],
    )


# ----------------------------------------------------------------------------------
# the two filters
# ----------------------------------------------------------------------------------


def test_the_default_floor_is_high_only(overlay: Path):
    """PI ruling, 2026-08-30. Medium and low are held back, and counted."""
    bypass = load_bypass_map(overlay)
    assert set(bypass.sites) == {"G3O-I-00000001", "G3O-I-00000005"}
    assert bypass.skipped_below_confidence == 2
    assert bypass.skipped_shared_site_host == 1


def test_lowering_the_floor_admits_medium(overlay: Path):
    bypass = load_bypass_map(overlay, min_confidence="medium")
    assert "G3O-I-00000002" in bypass.sites
    assert "G3O-I-00000003" not in bypass.sites


def test_a_shared_site_host_is_skipped_by_default(overlay: Path):
    """95 councils on one domain would become 95 identical ``site:`` queries."""
    assert "G3O-I-00000004" not in load_bypass_map(overlay).sites


def test_allowing_shared_hosts_admits_it(overlay: Path):
    bypass = load_bypass_map(overlay, require_unshared_site_host=False)
    assert "G3O-I-00000004" in bypass.sites
    assert bypass.skipped_shared_site_host == 0


def test_a_row_with_no_parseable_root_is_skipped_not_stored_empty(tmp_path: Path):
    path = write_overlay_csv(
        tmp_path / "o.csv", [dict(overlay_row("G3O-I-00000001", "https://x.gov/"), site_root="")]
    )
    bypass = load_bypass_map(path)
    assert bypass.sites == {}
    assert bypass.skipped_unparseable == 1


def test_a_nouid_row_can_never_be_spent(tmp_path: Path):
    path = write_overlay_csv(
        tmp_path / "o.csv", [overlay_row("__NOUID__INST-0000001", "https://x.gov/")]
    )
    assert load_bypass_map(path).sites == {}


# ----------------------------------------------------------------------------------
# refusals — a silently empty map is a run that quietly did not do the thing
# ----------------------------------------------------------------------------------


def test_a_missing_overlay_is_a_refusal_not_an_empty_map(tmp_path: Path):
    with pytest.raises(OfficialSitesError, match="not found"):
        load_bypass_map(tmp_path / "nope.csv")


def test_a_csv_that_is_not_an_overlay_is_a_refusal(tmp_path: Path):
    path = tmp_path / "wrong.csv"
    path.write_text("institution_uid,website\nG3O-I-1,https://x.gov/\n", encoding="utf-8")
    with pytest.raises(OfficialSitesError, match="missing columns"):
        load_bypass_map(path)


def test_an_unknown_confidence_floor_is_a_refusal(overlay: Path):
    with pytest.raises(OfficialSitesError, match="unknown confidence floor"):
        load_bypass_map(overlay, min_confidence="quite-sure")


# ----------------------------------------------------------------------------------
# applying it
# ----------------------------------------------------------------------------------


def test_apply_decorates_only_matching_rows(overlay: Path):
    rows = [
        {"institution_uid": "G3O-I-00000001"},
        {"institution_uid": "G3O-I-00000004"},  # shared host — filtered out upstream
        {"institution_uid": "G3O-I-99999999"},  # not in the overlay
    ]
    applied = apply_to_rows(rows, load_bypass_map(overlay))
    assert applied == 1
    assert rows[0]["official_site_url"] == "https://alpha.gov/"
    assert rows[0]["official_site_confidence"] == "high"
    assert "official_site_url" not in rows[1]
    assert "official_site_url" not in rows[2]


def test_an_existing_official_site_url_is_never_overwritten(overlay: Path):
    """The column is the master's to own. The overlay fills a gap, it does not argue."""
    rows = [{"institution_uid": "G3O-I-00000001", "official_site_url": "https://hand-set.gov/"}]
    assert apply_to_rows(rows, load_bypass_map(overlay)) == 0
    assert rows[0]["official_site_url"] == "https://hand-set.gov/"


# ----------------------------------------------------------------------------------
# identity: the hash is over what would be spent, not over the file
# ----------------------------------------------------------------------------------


def test_the_hash_ignores_rows_the_floor_excludes(tmp_path: Path, overlay: Path):
    """Two overlays differing only below the floor are the same instrument."""
    extended = write_overlay_csv(
        tmp_path / "extended.csv",
        [
            overlay_row("G3O-I-00000001", "https://alpha.gov/"),
            overlay_row("G3O-I-00000002", "https://beta.gov/", confidence="medium"),
            overlay_row("G3O-I-00000003", "https://gamma.gov/", confidence="low"),
            overlay_row("G3O-I-00000004", "https://nsw.gov.au/", site_share="95"),
            overlay_row("G3O-I-00000005", "https://delta.gov/"),
            overlay_row("G3O-I-00000006", "https://epsilon.gov/", confidence="low"),
        ],
    )
    assert load_bypass_map(extended).content_hash == load_bypass_map(overlay).content_hash


def test_the_hash_moves_when_a_spent_site_changes(tmp_path: Path, overlay: Path):
    changed = write_overlay_csv(
        tmp_path / "changed.csv",
        [
            overlay_row("G3O-I-00000001", "https://alpha-two.gov/"),
            overlay_row("G3O-I-00000005", "https://delta.gov/"),
        ],
    )
    assert load_bypass_map(changed).content_hash != load_bypass_map(overlay).content_hash


def test_the_manifest_block_accounts_for_every_excluded_row(overlay: Path):
    block = load_bypass_map(overlay).manifest_block()
    assert block["overlay_rows"] == 5
    assert block["eligible_sites"] == 2
    assert (
        block["eligible_sites"]
        + block["skipped_below_confidence"]
        + block["skipped_shared_site_host"]
        + block["skipped_unparseable"]
        == block["overlay_rows"]
    )
    assert block["min_confidence"] == "high"
    assert block["require_unshared_site_host"] is True
    assert len(block["content_hash"]) == 64
