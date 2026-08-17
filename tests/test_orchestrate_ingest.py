"""Leg 3 — loading a run, and reporting the loader without flattering it.

The brief names the failure mode this leg is written against: *"a green print
over a rolled-back load"*. So the assertions here are mostly about what the
report refuses to claim — that an unparseable output is not zero rows, that
exit 0 with nothing loaded is not green, and that a run which did not complete
is not loaded at all.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from g3o.run.orchestrate import ingest as ing
from tests._orchestrate import event, make_run, write_final_csvs

GREEN_OUTPUT = textwrap.dedent(
    """\
      wave 1 left as-is; currency unchanged (pass --make-current to set it).
    Loading institutions from master.csv …
      upserted 1,234 institutions (wave 1)
    Pass 1 — activities from acts.csv …
      upserted 56 findings (0 quarantined, 0 sweep_uid derived)
    Pass 2 — sources from srcs.csv …
      upserted 78 evidence (0 quarantined, 0 sweep_uid derived)
      n_sources check: OK
    Committed. Re-running is safe — upserts are idempotent.

    === STRICT CHECKS ==============================================
      PASS — nothing quarantined beyond the threshold, no dangling FKs,
             no n_sources mismatch. Exit 0.
    ================================================================
    """
)

QUARANTINED_OUTPUT = textwrap.dedent(
    """\
      upserted 1,234 institutions (wave 1)
      upserted 40 findings (16 quarantined, 0 sweep_uid derived)
      ! 16 activities quarantined -> reports/quarantine_activities_w1_x.csv
      upserted 70 evidence (8 quarantined, 0 sweep_uid derived)
      n_sources check: 3 mismatched findings
    Committed. Re-running is safe — upserts are idempotent.

    === STRICT CHECKS ==============================================
      FAIL 1. 24 row(s) quarantined (rate 0.100) exceeds --max-quarantine-rate 0.0
      FAIL 2. 3 findings whose n_sources does not match the evidence layer
    ================================================================
    """
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parses_a_green_transcript() -> None:
    counts = ing.parse_ingest_output(GREEN_OUTPUT)

    assert counts.parsed
    assert counts.institutions == 1234
    assert counts.findings_loaded == 56
    assert counts.evidence_loaded == 78
    assert counts.total_quarantined == 0
    assert counts.n_sources_mismatched == 0
    assert counts.strict_failures == ()


def test_parses_quarantine_counts_and_strict_failures() -> None:
    counts = ing.parse_ingest_output(QUARANTINED_OUTPUT)

    assert counts.findings_quarantined == 16
    assert counts.evidence_quarantined == 8
    assert counts.total_quarantined == 24
    assert counts.n_sources_mismatched == 3
    assert len(counts.strict_failures) == 2
    assert "max-quarantine-rate" in counts.strict_failures[0]


def test_an_unrecognised_transcript_reports_unknown_not_zero() -> None:
    """The defect this module exists to prevent, asserted directly."""
    counts = ing.parse_ingest_output("the loader was rewritten and prints differently now")

    assert not counts.parsed
    assert counts.findings_quarantined is None
    assert counts.total_quarantined is None


def test_a_missing_n_sources_line_is_none_not_zero() -> None:
    assert ing.parse_ingest_output("upserted 1 institutions (wave 1)").n_sources_mismatched is None


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------


def _result(exit_code: int, output: str, **kwargs) -> ing.IngestResult:
    return ing.IngestResult(
        run_id="r1", exit_code=exit_code, argv=(), counts=ing.parse_ingest_output(output), **kwargs
    )


def test_green_needs_exit_zero_rows_loaded_and_nothing_quarantined() -> None:
    assert _result(0, GREEN_OUTPUT).green
    assert not _result(1, GREEN_OUTPUT).green
    assert not _result(0, QUARANTINED_OUTPUT).green


def test_exit_zero_with_nothing_loaded_is_not_green() -> None:
    empty = "upserted 500 institutions (wave 1)\n" \
            "  upserted 0 findings (0 quarantined, 0 sweep_uid derived)\n" \
            "  upserted 0 evidence (0 quarantined, 0 sweep_uid derived)\n"
    result = _result(0, empty)
    assert not result.green
    assert "NOTHING LOADED" in result.verdict


def test_exit_zero_with_unparseable_counts_is_not_green() -> None:
    result = _result(0, "unrecognised")
    assert not result.green
    assert "COUNTS UNKNOWN" in result.verdict


def test_abort_says_nothing_was_committed() -> None:
    assert "Nothing was written" in _result(2, "").verdict


def test_strict_failure_says_the_data_is_in_the_database() -> None:
    verdict = _result(1, QUARANTINED_OUTPUT).verdict
    assert "NOT GREEN" in verdict
    assert "completed and did not pass" in verdict


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def test_a_loader_that_echoes_the_dsn_does_not_get_it_archived(
    tmp_path: Path, master: Path, monkeypatch
) -> None:
    """The ingest log is uploaded to Spaces and pulled to Drive. It stays clean.

    A secret that reaches an archived file has to be rotated, not edited out, so
    the redaction happens on the way to disk rather than being assumed away.
    """
    dsn = "postgresql://neon_user:sup3r-s3cret@ep-cool-1.neon.tech/g3o"
    runs_dir, run_id = _completed_run(tmp_path, master)
    leaky = "psycopg.OperationalError: could not connect: " + dsn
    repo = _fake_loader_repo(tmp_path, exit_code=2, output=leaky)
    monkeypatch.setenv(ing.DSN_ENV_VAR, dsn)

    result = ing.ingest_run(runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo)

    log = result.log_path.read_text(encoding="utf-8")
    assert "sup3r-s3cret" not in log
    assert "redacted" in log
    # And nothing else in the run tree carries it either — this is what the
    # archive leg will upload.
    for path in (runs_dir / run_id).rglob("*"):
        if path.is_file():
            assert "sup3r-s3cret" not in path.read_text(encoding="utf-8", errors="replace")


def test_a_short_password_does_not_shred_the_log() -> None:
    """``upserted`` must not become ``u<redacted>serted`` to protect the letter p."""
    text = "  upserted 56 findings (0 quarantined, 0 sweep_uid derived)"

    redacted = ing.redact_dsn(text, "postgresql://u:p@host/db")

    assert redacted == text
    assert ing.parse_ingest_output(redacted).findings_loaded == 56


def test_a_real_password_is_removed() -> None:
    dsn = "postgresql://neon:correct-horse-battery@h/db"
    assert "correct-horse-battery" not in ing.redact_dsn(f"connect failed: {dsn}", dsn)
    assert "correct-horse-battery" not in ing.redact_dsn("pw=correct-horse-battery", dsn)


def test_the_dsn_is_described_without_its_password() -> None:
    dsn = "postgresql://neon_user:sup3r-s3cret@ep-cool-1.eu-central-1.aws.neon.tech/g3o?sslmode=require"
    described = ing.describe_dsn(dsn)

    assert described["host"] == "ep-cool-1.eu-central-1.aws.neon.tech"
    assert described["database"] == "g3o"
    assert described["fingerprint"] and len(described["fingerprint"]) == 8
    assert "sup3r-s3cret" not in repr(described)
    assert "neon_user" not in repr(described)


# ---------------------------------------------------------------------------
# The leg
# ---------------------------------------------------------------------------


def _fake_loader_repo(tmp_path: Path, *, exit_code: int, output: str, quarantine_rows: int = 0) -> Path:
    """A stand-in ``g3o-website`` checkout whose loader prints a fixed transcript."""
    repo = tmp_path / "g3o-website"
    (repo / "scripts").mkdir(parents=True)
    script = repo / "scripts" / "ingest.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import sys, pathlib
            print({output!r})
            args = sys.argv
            report_dir = pathlib.Path(args[args.index("--report-dir") + 1])
            rows = {quarantine_rows}
            if rows:
                report_dir.mkdir(parents=True, exist_ok=True)
                out = report_dir / "quarantine_activities_w1_20260813T100000Z.csv"
                out.write_text("reason,institution_id\\n" + "".join(
                    f"missing_institution_uid,INST-{{i:07d}}\\n" for i in range(rows)
                ), encoding="utf-8")
            sys.exit({exit_code})
            """
        ),
        encoding="utf-8",
    )
    return repo


def _completed_run(tmp_path: Path, master: Path) -> tuple[Path, str]:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir,
        config={"master_csv": str(master), "dry_run": False},
        events=[event(1, "run_launched"), event(2, "run_completed", outcome="completed")],
    )
    write_final_csvs(run_dir)
    return runs_dir, run_dir.name


@pytest.fixture()
def master(tmp_path: Path) -> Path:
    path = tmp_path / "master_institutions.csv"
    path.write_text("institution_uid,institution_name\nG3O-I-00000001,A\n", encoding="utf-8")
    return path


def test_a_green_load_is_reported_green(tmp_path: Path, master: Path, monkeypatch) -> None:
    runs_dir, run_id = _completed_run(tmp_path, master)
    repo = _fake_loader_repo(tmp_path, exit_code=0, output=GREEN_OUTPUT)
    monkeypatch.setenv(ing.DSN_ENV_VAR, "postgresql://u:p@host/db")

    result = ing.ingest_run(runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo)

    assert result.exit_code == 0
    assert result.green
    assert result.counts.findings_loaded == 56
    assert result.log_path.is_file()
    assert "GREEN" in ing.render_ingest(result)


def test_a_strict_failure_surfaces_its_exit_code_and_reports(
    tmp_path: Path, master: Path, monkeypatch
) -> None:
    runs_dir, run_id = _completed_run(tmp_path, master)
    repo = _fake_loader_repo(
        tmp_path, exit_code=1, output=QUARANTINED_OUTPUT, quarantine_rows=16
    )
    monkeypatch.setenv(ing.DSN_ENV_VAR, "postgresql://u:p@host/db")

    result = ing.ingest_run(runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo)

    assert result.exit_code == 1
    assert not result.green
    assert len(result.quarantine_reports) == 1
    assert result.quarantine_rows_on_disk == 16
    rendered = ing.render_ingest(result)
    assert "NOT GREEN" in rendered
    # The loader said 24 quarantined; 16 rows landed on disk. Disagreement is
    # reported, never averaged away.
    assert "should match" in rendered


def test_the_leg_record_survives_the_run(tmp_path: Path, master: Path, monkeypatch) -> None:
    from g3o.run.orchestrate.status import run_status

    runs_dir, run_id = _completed_run(tmp_path, master)
    repo = _fake_loader_repo(tmp_path, exit_code=0, output=GREEN_OUTPUT)
    monkeypatch.setenv(ing.DSN_ENV_VAR, "postgresql://u:p@host/db")

    ing.ingest_run(runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo)

    status = run_status(runs_dir, run_id)
    assert status.legs["ingest"]["outcome"] == "green"
    assert status.legs["ingest"]["exit_code"] == 0
    # The DSN is in the record only as host + fingerprint.
    assert "p@host" not in str(status.legs["ingest"])


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_run_that_did_not_complete_is_refused(tmp_path: Path, master: Path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir,
        config={"master_csv": str(master), "dry_run": False},
        events=[
            event(1, "run_launched"),
            event(2, "run_failed", error_class="RuntimeError", error_message="scrape died"),
        ],
    )
    write_final_csvs(run_dir)
    repo = _fake_loader_repo(tmp_path, exit_code=0, output=GREEN_OUTPUT)
    monkeypatch.setenv(ing.DSN_ENV_VAR, "postgresql://u:p@host/db")

    with pytest.raises(ing.IngestError, match="refusing to ingest"):
        ing.ingest_run(runs_dir, run_dir.name, frame_id='mb-TEST', loader_repo=repo)


def test_force_loads_a_partial_run_and_records_that_it_did(
    tmp_path: Path, master: Path, monkeypatch
) -> None:
    from g3o.run.orchestrate.status import run_status

    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir,
        config={"master_csv": str(master), "dry_run": False},
        events=[event(1, "run_launched"), event(2, "run_failed", error_class="RuntimeError")],
    )
    write_final_csvs(run_dir)
    repo = _fake_loader_repo(tmp_path, exit_code=0, output=GREEN_OUTPUT)
    monkeypatch.setenv(ing.DSN_ENV_VAR, "postgresql://u:p@host/db")

    ing.ingest_run(runs_dir, run_dir.name, frame_id='mb-TEST', loader_repo=repo, force=True)

    assert run_status(runs_dir, run_dir.name).legs["ingest"]["forced"] is True


def test_a_missing_dsn_refuses_before_anything_runs(
    tmp_path: Path, master: Path, monkeypatch
) -> None:
    runs_dir, run_id = _completed_run(tmp_path, master)
    repo = _fake_loader_repo(tmp_path, exit_code=0, output=GREEN_OUTPUT)
    monkeypatch.delenv(ing.DSN_ENV_VAR, raising=False)

    with pytest.raises(ing.IngestError, match="DATABASE_URL"):
        ing.ingest_run(runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo)


def test_a_checkout_at_the_wrong_commit_is_refused(
    tmp_path: Path, master: Path, monkeypatch
) -> None:
    runs_dir, run_id = _completed_run(tmp_path, master)
    repo = _fake_loader_repo(tmp_path, exit_code=0, output=GREEN_OUTPUT)
    monkeypatch.setenv(ing.DSN_ENV_VAR, "postgresql://u:p@host/db")

    with pytest.raises(ing.IngestError, match="pinned"):
        ing.ingest_run(
            runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo, expect_loader_sha="deadbeef",
        )


def test_a_directory_without_the_loader_is_not_a_checkout(tmp_path: Path) -> None:
    with pytest.raises(ing.IngestError, match="not a g3o-api checkout"):
        ing.resolve_loader_repo(tmp_path)


def test_no_repo_at_all_names_the_env_var(monkeypatch) -> None:
    monkeypatch.delenv(ing.LOADER_REPO_ENV_VAR, raising=False)
    with pytest.raises(ing.IngestError, match=ing.LOADER_REPO_ENV_VAR):
        ing.resolve_loader_repo(None)


def test_missing_stage7_output_says_to_run_persist(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "r1"
    (run_dir / "final").mkdir(parents=True)
    with pytest.raises(ing.IngestError, match="persist"):
        ing.find_stage7_csvs(run_dir)


def test_the_highest_csv_version_wins(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "r1"
    final = run_dir / "final"
    final.mkdir(parents=True)
    for version in (1, 2):
        (final / f"g3o_activities_v{version}.csv").write_text("x\n", encoding="utf-8")
        (final / f"g3o_activity_sources_v{version}.csv").write_text("x\n", encoding="utf-8")

    activities, sources = ing.find_stage7_csvs(run_dir)

    assert activities.name.endswith("v2.csv")
    assert sources.name.endswith("v2.csv")


def test_extra_loader_args_are_passed_through(tmp_path: Path) -> None:
    argv = ing.build_argv(
        tmp_path, run_dir=Path("runs/r1"), frame_id="mb-2026-07-30",
        master=Path("m.csv"), activities=Path("a.csv"),
        sources=Path("s.csv"), report_dir=Path("r"), extra_args=("--make-current",),
    )
    assert argv[-1] == "--make-current"
    # v0.6: --run-dir + --frame-id, and no --wave-id anywhere.
    assert "--run-dir" in argv and "--frame-id" in argv
    assert "mb-2026-07-30" in argv
    assert "--wave-id" not in argv


def test_the_master_comes_from_the_run_that_sampled_it(tmp_path: Path, master: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path, master)
    assert ing.master_csv_from_manifest(runs_dir / run_id) == master


def test_environment_is_not_mutated_by_the_leg(tmp_path: Path, master: Path, monkeypatch) -> None:
    """The DSN is handed to the child's environment, not written into ours."""
    runs_dir, run_id = _completed_run(tmp_path, master)
    repo = _fake_loader_repo(tmp_path, exit_code=0, output=GREEN_OUTPUT)
    monkeypatch.delenv(ing.DSN_ENV_VAR, raising=False)

    ing.ingest_run(runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo, dsn="postgresql://u:p@h/d")

    assert ing.DSN_ENV_VAR not in os.environ
