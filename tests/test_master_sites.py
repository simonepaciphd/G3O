"""The overlay against the master: the per-run join, and the fold proposal it can emit.

A fold proposal is the one artifact in this pipeline whose sha256 a PI signs, so the
tests are weighted towards what decides a row's action (fill / replace / nothing),
towards the eligibility rule being the presweep's and not a copy of it, and towards
the bytes being a pure function of the inputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from g3o.report.master_sites import (
    JOIN_COLUMNS,
    PROPOSAL_COLUMNS,
    MasterSitesError,
    build_master_sites,
    website_blank,
)
from g3o.run.orchestrate.harvest import MASTER_SITES_DIRNAME, refresh_master_sites
from g3o.run.presweep.official_sites import load_bypass_map
from tests.test_official_sites import overlay_row, write_overlay_csv

MASTER_COLUMNS = [
    "institution_uid", "master_row_id", "master_build_id", "country_iso3",
    "government_level", "institution_type", "institution_name", "website",
    "source_dataset_id",
    # what a folded master carries; must pass through untouched
    "website_source", "website_source_value", "website_fold_id", "website_fold_run_id",
]


def master_row(uid, website, *, source="src_a", level="local", n=1):
    return {
        "institution_uid": uid, "master_row_id": str(n), "master_build_id": "mb-2026-07-30",
        "country_iso3": "GBR", "government_level": level, "institution_type": "council",
        "institution_name": f"Institution {uid[-2:]}", "website": website,
        "source_dataset_id": source,
        "website_source": "source_dataset", "website_source_value": website,
        "website_fold_id": "", "website_fold_run_id": "",
    }


MASTER_ROWS = [
    master_row("G3O-I-00000001", "", n=1),                                  # fill
    master_row("G3O-I-00000002", "https://www.beta.gov/about", n=2),        # same host
    master_row("G3O-I-00000003", "https://old.gamma.org/", source="src_b", n=3),  # replace
    master_row("G3O-I-00000004", "", n=4),                                  # medium
    master_row("G3O-I-00000005", "", n=5),                                  # shared host
    master_row("G3O-I-00000006", "TBD", n=6),                               # placeholder
    master_row("G3O-I-00000007", "", n=7),                                  # no pick
]


def write_master(path: Path, rows: list[dict], columns=MASTER_COLUMNS) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _overlay_row(uid, root, **kw):
    row = overlay_row(uid, root, **kw)
    row.update(run_id="r20261001T000000Z-aaaa", git_sha="abc1234", stage2_model="m-1")
    return row


@pytest.fixture
def overlay(tmp_path: Path) -> Path:
    return write_overlay_csv(
        tmp_path / "official_sites.csv",
        [
            _overlay_row("G3O-I-00000001", "https://alpha.gov/"),
            _overlay_row("G3O-I-00000002", "https://beta.gov/"),
            _overlay_row("G3O-I-00000003", "https://gamma.gov/"),
            _overlay_row("G3O-I-00000004", "https://delta.gov/", confidence="medium"),
            _overlay_row("G3O-I-00000005", "https://nsw.gov.au/", site_share="2"),
            _overlay_row("G3O-I-00000006", "https://zeta.gov/"),
            _overlay_row("G3O-I-00000099", "https://orphan.gov/"),
            _overlay_row("__NOUID__INST-0000001", "https://nouid.gov/"),
        ],
    )


@pytest.fixture
def master(tmp_path: Path) -> Path:
    return write_master(tmp_path / "master_institutions.csv", MASTER_ROWS)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# ----------------------------------------------------------------------------------
# the join
# ----------------------------------------------------------------------------------


def test_the_join_counts_every_margin(master: Path, overlay: Path, tmp_path: Path):
    report = build_master_sites(master, overlay, tmp_path / "out").report

    assert report["master_rows"] == 7
    assert report["status_counts"] == {
        "eligible": 4, "below_confidence": 1, "shared_site_host": 1, "no_pick": 1,
    }
    # TBD has no parseable host, so the join calls it master_empty.
    assert report["eligible_vs_master"] == {
        "master_empty": 2, "same_host": 1, "different_host": 1,
    }
    # The no-uid pick is never eligible and never joins; it is an orphan, as is 99.
    assert report["overlay_uids_not_in_master"] == 2
    assert report["bypass_manifest"] == load_bypass_map(overlay).manifest_block()
    assert report["master_build_id"] == "mb-2026-07-30"


def test_master_columns_pass_through_verbatim_and_in_order(
    master: Path, overlay: Path, tmp_path: Path
):
    out = tmp_path / "out"
    build_master_sites(master, overlay, out)
    with (out / "master_with_official_sites.csv").open(encoding="utf-8", newline="") as h:
        reader = csv.DictReader(h)
        assert reader.fieldnames == [*MASTER_COLUMNS, *JOIN_COLUMNS]
        rows = list(reader)
    for before, after in zip(MASTER_ROWS, rows, strict=True):
        assert {k: after[k] for k in MASTER_COLUMNS} == before
    assert rows[0]["official_site_url"] == "https://alpha.gov/"
    assert rows[3]["official_site_status"] == "below_confidence"
    assert rows[3]["official_site_url"] == ""


def test_conflicts_hold_only_different_host_picks(
    master: Path, overlay: Path, tmp_path: Path
):
    out = tmp_path / "out"
    build_master_sites(master, overlay, out)
    conflicts = _read(out / "conflicts.csv")
    assert [r["institution_uid"] for r in conflicts] == ["G3O-I-00000003"]
    assert conflicts[0]["website"] == "https://old.gamma.org/"


def test_a_master_already_carrying_join_columns_is_refused(overlay: Path, tmp_path: Path):
    columns = [*MASTER_COLUMNS, "official_site_url"]
    master = write_master(
        tmp_path / "m.csv", [{**r, "official_site_url": ""} for r in MASTER_ROWS], columns
    )
    with pytest.raises(MasterSitesError, match="already has columns"):
        build_master_sites(master, overlay, tmp_path / "out")


def test_without_a_fold_dir_no_proposal_is_written(
    master: Path, overlay: Path, tmp_path: Path
):
    result = build_master_sites(master, overlay, tmp_path / "out")
    assert result.proposal is None
    assert not list((tmp_path / "out").glob("proposal*"))


# ----------------------------------------------------------------------------------
# the proposal — FOLD-CONTRACT v1
# ----------------------------------------------------------------------------------


def _propose(master: Path, overlay: Path, tmp_path: Path, name="fold"):
    fold = tmp_path / name
    result = build_master_sites(
        master, overlay, tmp_path / f"out-{name}",
        fold_proposal_dir=fold, fold_id="fold-20261021-w001",
    )
    return fold, result.proposal


def test_fill_replace_and_nothing(master: Path, overlay: Path, tmp_path: Path):
    """Blank → fill; different host → replace; same host, medium, shared → no row.

    ``TBD`` counts as blank (PI ruling 2026-10-21), so it is a fill with an empty
    expected current value.
    """
    fold, meta = _propose(master, overlay, tmp_path)
    rows = _read(fold / "proposal.csv")

    assert [(r["institution_uid"], r["action"]) for r in rows] == [
        ("G3O-I-00000001", "fill"),
        ("G3O-I-00000003", "replace"),
        ("G3O-I-00000006", "fill"),
    ]
    by_uid = {r["institution_uid"]: r for r in rows}
    assert by_uid["G3O-I-00000001"]["expected_current_website"] == ""
    assert by_uid["G3O-I-00000003"]["expected_current_website"] == "https://old.gamma.org/"
    assert by_uid["G3O-I-00000006"]["expected_current_website"] == ""
    assert by_uid["G3O-I-00000003"]["proposed_website"] == "https://gamma.gov/"
    assert by_uid["G3O-I-00000003"]["official_site_run_id"] == "r20261001T000000Z-aaaa"
    assert by_uid["G3O-I-00000003"]["source_dataset_id"] == "src_b"
    assert meta["counts"] == {
        "fill": 2, "replace": 1,
        "replace_by_source_dataset_id": {"src_b": 1},
    }


def test_proposal_bytes_follow_the_contract(master: Path, overlay: Path, tmp_path: Path):
    fold, meta = _propose(master, overlay, tmp_path)
    payload = (fold / "proposal.csv").read_bytes()

    assert payload.split(b"\n", 1)[0].decode() == ",".join(PROPOSAL_COLUMNS)
    assert b"\r" not in payload
    assert meta["proposal_csv_sha256"] == hashlib.sha256(payload).hexdigest()
    on_disk = json.loads((fold / "proposal.json").read_text(encoding="utf-8"))
    assert on_disk == meta
    assert meta["format"] == "g3o-site-fold-proposal-v1"
    assert meta["fold_id"] == "fold-20261021-w001"
    assert meta["rule"] == {"min_confidence": "high", "require_unshared_site_host": True}
    assert meta["bypass_content_hash"] == load_bypass_map(overlay).content_hash
    assert meta["master_sha256"] == hashlib.sha256(master.read_bytes()).hexdigest()
    assert meta["overlay_sha256"] == hashlib.sha256(overlay.read_bytes()).hexdigest()
    assert meta["master_build_id"] == "mb-2026-07-30"


def test_same_inputs_same_proposal_sha(master: Path, overlay: Path, tmp_path: Path):
    """And master row order does not matter: the proposal is sorted by uid."""
    _, first = _propose(master, overlay, tmp_path, "a")
    _, second = _propose(master, overlay, tmp_path, "b")
    shuffled = write_master(tmp_path / "shuffled.csv", list(reversed(MASTER_ROWS)))
    _, third = _propose(shuffled, overlay, tmp_path, "c")

    assert first["proposal_csv_sha256"] == second["proposal_csv_sha256"]
    assert first["proposal_csv_sha256"] == third["proposal_csv_sha256"]
    assert (tmp_path / "a" / "proposal.csv").read_bytes() == (
        tmp_path / "c" / "proposal.csv"
    ).read_bytes()


@pytest.mark.parametrize("fold_id", [None, "", "fold-2026-10-21-w1", "w001", "fold-20261021-"])
def test_a_malformed_fold_id_is_refused(master, overlay, tmp_path, fold_id):
    with pytest.raises(MasterSitesError, match="fold_id"):
        build_master_sites(
            master, overlay, tmp_path / "out",
            fold_proposal_dir=tmp_path / "fold", fold_id=fold_id,
        )


def test_a_fold_dir_with_an_approval_is_never_rewritten(master, overlay, tmp_path):
    fold = tmp_path / "fold"
    fold.mkdir()
    (fold / "approval.json").write_text("{}", encoding="utf-8")
    with pytest.raises(MasterSitesError, match="approval"):
        build_master_sites(
            master, overlay, tmp_path / "out",
            fold_proposal_dir=fold, fold_id="fold-20261021-w001",
        )
    assert not (fold / "proposal.csv").exists()


def test_a_uid_on_two_master_rows_refuses_the_proposal(overlay, tmp_path):
    rows = [*MASTER_ROWS, master_row("G3O-I-00000001", "", n=8)]
    master = write_master(tmp_path / "dupes.csv", rows)
    with pytest.raises(MasterSitesError, match="more than one master row"):
        build_master_sites(
            master, overlay, tmp_path / "out",
            fold_proposal_dir=tmp_path / "fold", fold_id="fold-20261021-w001",
        )


# ----------------------------------------------------------------------------------
# the e2e leg
# ----------------------------------------------------------------------------------


def _runs_with_overlay(tmp_path: Path, overlay: Path) -> Path:
    runs = tmp_path / "runs"
    (runs / "_site_overlay").mkdir(parents=True)
    (runs / "_site_overlay" / "official_sites.csv").write_bytes(overlay.read_bytes())
    return runs


def test_the_leg_writes_the_latest_copy_and_never_a_proposal(master, overlay, tmp_path):
    runs = _runs_with_overlay(tmp_path, overlay)
    first = refresh_master_sites(runs, master_csv=master)
    second = refresh_master_sites(runs, master_csv=master)

    out = runs / "_site_overlay" / MASTER_SITES_DIRNAME
    assert first.green and second.green and not second.skipped
    assert sorted(p.name for p in out.iterdir()) == [
        "conflicts.csv", "master_with_official_sites.csv", "report.json",
    ]
    assert second.to_dict()["out_sha256"] == first.to_dict()["out_sha256"]
    assert "refreshed" in second.message


def test_the_leg_skips_cleanly_without_a_master(overlay, tmp_path):
    runs = _runs_with_overlay(tmp_path, overlay)

    none = refresh_master_sites(runs, master_csv=None)
    missing = refresh_master_sites(runs, master_csv=tmp_path / "nope.csv")

    for result in (none, missing):
        assert result.green and result.skipped
        assert result.message.startswith("skipped:")
    assert not (runs / "_site_overlay" / MASTER_SITES_DIRNAME).exists()


def test_the_leg_never_raises(master, tmp_path):
    runs = tmp_path / "runs"
    (runs / "_site_overlay").mkdir(parents=True)
    (runs / "_site_overlay" / "official_sites.csv").write_text("not,an,overlay\n")

    result = refresh_master_sites(runs, master_csv=master)

    assert not result.green
    assert "NOT refreshed" in result.message


# ----------------------------------------------------------------------------------
# the CLI
# ----------------------------------------------------------------------------------


def test_report_master_sites_cli(master, overlay, tmp_path, capsys):
    from g3o.cli import main

    code = main([
        "report", "master-sites", "--overlay", str(overlay), "--master-csv", str(master),
        "--out-dir", str(tmp_path / "out"),
        "--fold-proposal-dir", str(tmp_path / "fold"), "--fold-id", "fold-20261021-w001",
    ])
    summary = json.loads(capsys.readouterr().out)

    assert code == 0
    assert summary["status_counts"]["eligible"] == 4
    assert summary["proposal_counts"]["fill"] == 2
    assert (tmp_path / "fold" / "proposal.csv").is_file()


def test_report_master_sites_cli_wants_both_fold_flags(master, overlay, tmp_path):
    from g3o.cli import main

    code = main([
        "report", "master-sites", "--overlay", str(overlay), "--master-csv", str(master),
        "--out-dir", str(tmp_path / "out"), "--fold-proposal-dir", str(tmp_path / "fold"),
    ])
    assert code == 2
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    ("value", "blank"),
    [("", True), ("  ", True), ("TBD", True), (" TBD ", True),
     ("tbd", False), ("http:///www.x.gov", False), ("http://N/A", False),
     ("https://a.gov/", False)],
)
def test_only_empty_and_tbd_count_as_blank(value, blank):
    assert website_blank(value) is blank
