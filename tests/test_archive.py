"""Retention/archival tests (storage layout v2 Phase 3, spec §6).

Covers the five behaviours the spec names for ``g3o archive``:

- a dry run deletes nothing (and writes nothing);
- ``--apply`` deletes a source shard only after its tar verifies;
- a verification failure aborts, leaves a ``.FAILED`` tar, and leaves the
  source intact;
- a re-run is idempotent — already-archived shards are skipped;
- each precondition (Stage-7 CSVs, ``.done`` markers, run-level reports)
  refuses loudly.

The delete path is the only one in the codebase that removes collected data,
so the tests here assert on the *filesystem* after each call rather than on
return values alone.
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

import pytest

from g3o.common import run_state
from g3o.common.paths import institution_shard, institutions_root
from g3o.run.archive import (
    FAILED_SUFFIX,
    ArchiveError,
    DeleteFailedError,
    IncompleteSourceError,
    PreconditionError,
    VerificationError,
    archive_root,
    archive_run,
    plan_archive,
    read_tar_stat,
    shard_tar_path,
    walk_shard,
)
from g3o.run.presweep.config import STAGES
from tests._layout import make_inst_dir, write_manifest

# Institution ids chosen only for readability; the shard is md5-derived, so the
# tests never assume which shard an id lands in.
INSTS = ("INST-0000001", "INST-0000002", "INST-0000003")


def _write_final_csvs(run_dir: Path) -> None:
    final = run_dir / "final"
    final.mkdir(parents=True, exist_ok=True)
    for name in (
        "g3o_activities_v1.csv",
        "g3o_activity_sources_v1.csv",
        "g3o_institution_summary_v1.csv",
    ):
        (final / name).write_text("institution_id\n", encoding="utf-8")


def _mark_all_stages_done(run_dir: Path) -> None:
    for stage in STAGES:
        run_state.mark_done(run_dir, stage, no_batch=True)


def _write_reports(run_dir: Path) -> None:
    (run_dir / "run_summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "_health_report.json").write_text("{}", encoding="utf-8")


def _populate_institution(run_dir: Path, inst_id: str, *, n_pages: int = 2) -> Path:
    d = make_inst_dir(run_dir, inst_id)
    (d / "institution.json").write_text(
        f'{{"institution_id": "{inst_id}"}}', encoding="utf-8"
    )
    (d / "_timing.json").write_text("{}", encoding="utf-8")
    for sub in ("scrape", "extract"):
        (d / sub).mkdir(exist_ok=True)
        for i in range(n_pages):
            # Content deliberately varies in length so a byte-total comparison
            # is a real check rather than count x constant.
            (d / sub / f"page{i}.json.gz").write_bytes(b"x" * (17 + i * 5))
    return d


def make_complete_run(tmp_path: Path, insts: tuple[str, ...] = INSTS) -> Path:
    """A run tree that satisfies every archive precondition."""
    run_dir = tmp_path / "runs" / "run_archive_test"
    write_manifest(run_dir, run_id="run_archive_test")
    for inst_id in insts:
        _populate_institution(run_dir, inst_id)
    _write_final_csvs(run_dir)
    _mark_all_stages_done(run_dir)
    _write_reports(run_dir)
    # Run-level files that must survive archival untouched.
    (run_dir / "attrition.jsonl").write_text('{"event": "test"}\n', encoding="utf-8")
    return run_dir


@pytest.fixture()
def complete_run(tmp_path: Path) -> Path:
    return make_complete_run(tmp_path)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_deletes_nothing_and_writes_nothing(complete_run: Path):
    before = sorted(p.relative_to(complete_run).as_posix() for p in complete_run.rglob("*"))

    result = archive_run(complete_run, apply=False)

    assert result.applied is False
    assert result.outcomes == ()
    after = sorted(p.relative_to(complete_run).as_posix() for p in complete_run.rglob("*"))
    assert after == before, "a dry run must not create, move, or delete anything"
    assert not archive_root(complete_run).exists()
    for inst_id in INSTS:
        assert (institutions_root(complete_run) / institution_shard(inst_id) / inst_id).is_dir()


def test_plan_reports_shard_file_and_byte_totals(complete_run: Path):
    plan = plan_archive(complete_run)

    shards = {institution_shard(i) for i in INSTS}
    assert {s.shard for s in plan.shards} == shards
    assert all(s.state == "pending" for s in plan.shards)

    # 6 files per institution: institution.json, _timing.json, 2 scrape, 2 extract.
    assert plan.n_files == 6 * len(INSTS)
    expected_bytes = sum(
        walk_shard(institutions_root(complete_run) / s).n_bytes for s in shards
    )
    assert plan.n_bytes == expected_bytes
    assert plan.projected_tar_bytes > plan.n_bytes


def test_projected_tar_size_is_close_to_actual(complete_run: Path):
    """The dry-run size estimate is what an operator sizes a disk against.

    Pins two things at once: the estimate's accuracy, and — because the model
    assumes 512 bytes of header per member — the GNU tar format that makes that
    assumption true. Under tarfile's PAX default this fails at 2x.
    """
    projected = {s.shard: s.projected_tar_bytes for s in plan_archive(complete_run).shards}

    archive_run(complete_run, apply=True)

    for shard, estimate in projected.items():
        actual = shard_tar_path(complete_run, shard).stat().st_size
        assert abs(actual - estimate) <= 10_240, (
            f"shard {shard}: projected {estimate}, actual {actual} — the dry-run "
            f"estimate has drifted more than one tar record from reality"
        )


def test_tar_format_is_pinned_to_gnu():
    """Guards the size model and the long-path headroom; see TAR_FORMAT."""
    import tarfile as _tarfile

    from g3o.run.archive import TAR_FORMAT

    assert TAR_FORMAT == _tarfile.GNU_FORMAT


# ---------------------------------------------------------------------------
# --apply
# ---------------------------------------------------------------------------


def test_apply_tars_verifies_then_deletes_sources(complete_run: Path):
    expected = {
        institution_shard(i): walk_shard(
            institutions_root(complete_run) / institution_shard(i)
        )
        for i in INSTS
    }

    result = archive_run(complete_run, apply=True)

    assert result.applied is True
    assert result.n_deleted == len(expected)
    assert all(o.action == "archived" for o in result.outcomes)

    for shard, src_stat in expected.items():
        tar_path = shard_tar_path(complete_run, shard)
        assert tar_path.is_file(), f"shard {shard} has no tar"
        tar_stat = read_tar_stat(tar_path)
        assert tar_stat.n_files == src_stat.n_files
        assert tar_stat.n_bytes == src_stat.n_bytes
        assert not (institutions_root(complete_run) / shard).exists()


def test_apply_leaves_run_level_files_live(complete_run: Path):
    archive_run(complete_run, apply=True)

    assert (complete_run / "manifest.json").is_file()
    assert (complete_run / "attrition.jsonl").is_file()
    assert (complete_run / "run_summary.json").is_file()
    assert (complete_run / "_health_report.json").is_file()
    assert (complete_run / "final" / "g3o_activities_v1.csv").is_file()
    assert run_state.done_path(complete_run, STAGES[0]).is_file()


def test_tar_members_restore_under_the_institutions_root(complete_run: Path, tmp_path: Path):
    """The documented restore command must land files back where they were."""
    shard = institution_shard(INSTS[0])
    original = sorted(
        p.relative_to(institutions_root(complete_run)).as_posix()
        for p in (institutions_root(complete_run) / shard).rglob("*")
        if p.is_file()
    )

    archive_run(complete_run, apply=True)

    restore_into = tmp_path / "restored"
    restore_into.mkdir()
    with tarfile.open(shard_tar_path(complete_run, shard), mode="r:") as tar:
        tar.extractall(restore_into)  # noqa: S202 - fixture tar built in-test
    restored = sorted(
        p.relative_to(restore_into).as_posix()
        for p in restore_into.rglob("*")
        if p.is_file()
    )
    assert restored == original


# ---------------------------------------------------------------------------
# Verification failure
# ---------------------------------------------------------------------------


def test_verification_failure_aborts_keeps_failed_tar_and_intact_source(
    complete_run: Path, monkeypatch: pytest.MonkeyPatch
):
    import g3o.run.archive as archive_mod

    real_write_tar = archive_mod._write_tar
    target_shard = sorted(institution_shard(i) for i in INSTS)[0]

    def truncating_write_tar(source: Path, tar_path: Path, shard: str) -> None:
        """Write a tar that is missing one member — a silent-corruption stand-in."""
        if shard != target_shard:
            return real_write_tar(source, tar_path, shard)
        tar_path.parent.mkdir(parents=True, exist_ok=True)
        files = sorted(p for p in source.rglob("*") if p.is_file())
        with tarfile.open(tar_path, mode="w:") as tar:
            for p in files[:-1]:  # drop one file
                tar.add(p, arcname=f"{shard}/{p.relative_to(source).as_posix()}")

    monkeypatch.setattr(archive_mod, "_write_tar", truncating_write_tar)

    with pytest.raises(VerificationError) as excinfo:
        archive_run(complete_run, apply=True)

    message = str(excinfo.value)
    assert "does not match its source" in message
    # The message says what this pass did, not what state the source is in: the
    # tar was written this pass, so "not touched by this pass" is checkable,
    # where a flat claim of intactness would be a guess (see
    # test_partial_delete_keeps_the_good_tar_under_its_own_name, where the same
    # claim would have been false).
    assert "not touched by this pass" in message
    assert "deleted nothing" in message

    source = institutions_root(complete_run) / target_shard
    assert source.is_dir(), "the source shard must survive a failed verification"
    assert sorted(p.name for p in source.rglob("*") if p.is_file())

    good_tar = shard_tar_path(complete_run, target_shard)
    failed_tar = good_tar.with_name(good_tar.name + FAILED_SUFFIX)
    assert not good_tar.exists(), "a bad tar must not remain under its valid name"
    assert failed_tar.is_file(), "the bad tar must be kept for inspection"


def test_verification_failure_does_not_delete_later_shards(
    complete_run: Path, monkeypatch: pytest.MonkeyPatch
):
    """Abort means abort: shards after the failure are untouched."""
    import g3o.run.archive as archive_mod

    shards = sorted(institution_shard(i) for i in INSTS)
    target_shard = shards[0]

    def bad_write_tar(source: Path, tar_path: Path, shard: str) -> None:
        tar_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tar_path, mode="w:"):
            pass  # empty tar for every shard

    monkeypatch.setattr(archive_mod, "_write_tar", bad_write_tar)

    with pytest.raises(VerificationError):
        archive_run(complete_run, apply=True)

    for shard in shards:
        assert (institutions_root(complete_run) / shard).is_dir()
    assert not shard_tar_path(complete_run, target_shard).exists()
    # Only the first shard was reached; the rest never got a tar at all.
    for shard in shards[1:]:
        assert not shard_tar_path(complete_run, shard).exists()
        assert not shard_tar_path(complete_run, shard).with_name(
            f"{shard}.tar{FAILED_SUFFIX}"
        ).exists()


def test_existing_tar_that_does_not_match_source_aborts(complete_run: Path):
    """A complete-but-wrong tar is an anomaly, not resumable work."""
    shard = sorted(institution_shard(i) for i in INSTS)[0]
    tar_path = shard_tar_path(complete_run, shard)
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, mode="w:"):
        pass  # exists, verifies against nothing

    with pytest.raises(VerificationError):
        archive_run(complete_run, apply=True)

    assert (institutions_root(complete_run) / shard).is_dir()
    assert tar_path.with_name(tar_path.name + FAILED_SUFFIX).is_file()


# ---------------------------------------------------------------------------
# Idempotence / resume
# ---------------------------------------------------------------------------


def test_rerun_after_full_archive_is_a_noop(complete_run: Path):
    first = archive_run(complete_run, apply=True)
    tar_bytes = {
        o.shard: shard_tar_path(complete_run, o.shard).read_bytes() for o in first.outcomes
    }

    second = archive_run(complete_run, apply=True)

    assert second.n_deleted == 0
    assert all(o.action == "skipped" for o in second.outcomes)
    for shard, payload in tar_bytes.items():
        assert shard_tar_path(complete_run, shard).read_bytes() == payload, (
            "an already-archived shard must not be rewritten"
        )


def test_interrupted_apply_resumes(complete_run: Path):
    """A shard tarred but not yet deleted verifies and finishes on the next pass."""
    shard = sorted(institution_shard(i) for i in INSTS)[0]
    source = institutions_root(complete_run) / shard
    from g3o.run.archive import _write_tar

    _write_tar(source, shard_tar_path(complete_run, shard), shard)
    assert source.is_dir()

    plan = plan_archive(complete_run)
    assert {s.shard: s.state for s in plan.shards}[shard] == "tarred"

    result = archive_run(complete_run, apply=True)

    by_shard = {o.shard: o for o in result.outcomes}
    assert by_shard[shard].action == "verified", "an existing good tar is not rewritten"
    assert by_shard[shard].deleted is True
    assert not source.exists()
    for other in (institution_shard(i) for i in INSTS):
        assert not (institutions_root(complete_run) / other).exists()


def test_dry_run_after_partial_archive_reports_remaining_work(complete_run: Path):
    shard = sorted(institution_shard(i) for i in INSTS)[0]
    from g3o.run.archive import _write_tar

    source = institutions_root(complete_run) / shard
    _write_tar(source, shard_tar_path(complete_run, shard), shard)
    import shutil

    shutil.rmtree(source)

    plan = plan_archive(complete_run)
    by_shard = {s.shard: s for s in plan.shards}
    assert by_shard[shard].state == "archived"
    assert len(plan.pending) == len(plan.shards) - 1


# ---------------------------------------------------------------------------
# Preconditions
# ---------------------------------------------------------------------------


def test_missing_final_csvs_refuses(tmp_path: Path):
    run_dir = make_complete_run(tmp_path)
    (run_dir / "final" / "g3o_activities_v1.csv").unlink()

    with pytest.raises(PreconditionError, match="final/ is missing Stage-7 output"):
        archive_run(run_dir, apply=True)

    assert institutions_root(run_dir).is_dir()


def test_missing_final_dir_entirely_refuses(tmp_path: Path):
    run_dir = make_complete_run(tmp_path)
    import shutil

    shutil.rmtree(run_dir / "final")

    with pytest.raises(PreconditionError, match="Stage-7 output"):
        archive_run(run_dir, apply=False)


def test_missing_done_marker_refuses(tmp_path: Path):
    run_dir = make_complete_run(tmp_path)
    run_state.done_path(run_dir, STAGES[-1]).unlink()

    with pytest.raises(PreconditionError, match="no _state/.done marker"):
        archive_run(run_dir, apply=True)

    assert institutions_root(run_dir).is_dir()


def test_missing_reports_refuse(tmp_path: Path):
    run_dir = make_complete_run(tmp_path)
    (run_dir / "run_summary.json").unlink()

    with pytest.raises(PreconditionError, match="run-level report"):
        archive_run(run_dir, apply=True)


def test_all_precondition_failures_are_reported_together(tmp_path: Path):
    run_dir = make_complete_run(tmp_path)
    import shutil

    shutil.rmtree(run_dir / "final")
    run_state.done_path(run_dir, STAGES[0]).unlink()
    (run_dir / "_health_report.json").unlink()

    with pytest.raises(PreconditionError) as excinfo:
        archive_run(run_dir, apply=True)

    message = str(excinfo.value)
    assert "Stage-7 output" in message
    assert "_state/.done" in message
    assert "run-level report" in message


def test_non_v2_layout_refuses(tmp_path: Path):
    run_dir = make_complete_run(tmp_path)
    (run_dir / "manifest.json").unlink()

    with pytest.raises(RuntimeError, match="layout"):
        archive_run(run_dir, apply=False)


def test_dry_run_refuses_on_unfinished_run(tmp_path: Path):
    """The gate is on the operation, not on the flag — a dry run refuses too."""
    run_dir = make_complete_run(tmp_path)
    run_state.done_path(run_dir, STAGES[0]).unlink()

    with pytest.raises(PreconditionError):
        archive_run(run_dir, apply=False)


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_dry_run_prints_plan_and_deletes_nothing(complete_run: Path, capsys):
    from g3o.cli import main

    code = main(["archive", "--run-dir", str(complete_run)])

    assert code == 0
    out = capsys.readouterr().out
    assert "dry run" in out
    assert "Shards to archive" in out
    assert institutions_root(complete_run).is_dir()
    assert not archive_root(complete_run).exists()


def test_cli_apply_archives(complete_run: Path, capsys):
    from g3o.cli import main

    code = main(["archive", "--run-dir", str(complete_run), "--apply"])

    assert code == 0
    assert "Source shards deleted" in capsys.readouterr().out
    assert not any(institutions_root(complete_run).iterdir())


def test_cli_precondition_failure_exits_2_without_traceback(tmp_path: Path, capsys):
    from g3o.cli import main

    run_dir = make_complete_run(tmp_path)
    (run_dir / "run_summary.json").unlink()

    code = main(["archive", "--run-dir", str(run_dir)])

    assert code == 2
    assert "run-level report" in capsys.readouterr().err
    assert institutions_root(run_dir).is_dir()


# ---------------------------------------------------------------------------
# Interrupted delete: the tar outlives a half-removed source
# ---------------------------------------------------------------------------


def _tar_one_shard(run_dir: Path) -> tuple[str, Path, Path]:
    """Write and verify a tar for one shard, leaving its source in place."""
    from g3o.run.archive import _write_tar

    shard = sorted(institution_shard(i) for i in INSTS)[0]
    source = institutions_root(run_dir) / shard
    tar_path = shard_tar_path(run_dir, shard)
    _write_tar(source, tar_path, shard)
    return shard, source, tar_path


def test_partial_delete_keeps_the_good_tar_under_its_own_name(complete_run: Path):
    """A tar that outlives a half-removed source is the complete copy.

    Reproduces the state an ``rmtree`` that dies partway leaves behind. Treating
    it as a bad tar would file the shard's only intact copy under ``.FAILED``
    and tell the operator the source is intact, which it is not.
    """
    _shard, source, tar_path = _tar_one_shard(complete_run)
    good = read_tar_stat(tar_path)
    victim = next(p for p in sorted(source.rglob("*")) if p.is_file())
    victim.unlink()

    with pytest.raises(IncompleteSourceError) as exc:
        archive_run(complete_run, apply=True)

    assert tar_path.is_file(), "the complete tar must keep its own name"
    assert not tar_path.with_name(tar_path.name + FAILED_SUFFIX).exists()
    assert read_tar_stat(tar_path) == good, "the tar must not be rewritten"
    assert source.is_dir(), "the residual source is left for the operator"
    assert not victim.exists()
    message = str(exc.value)
    assert "strict superset" in message
    assert "NOT been renamed" in message
    assert "is intact" not in message, "must not claim an incomplete source is intact"


def test_partial_delete_does_not_delete_anything(complete_run: Path):
    _shard, source, _tar = _tar_one_shard(complete_run)
    next(p for p in sorted(source.rglob("*")) if p.is_file()).unlink()
    before = {p for p in complete_run.rglob("*") if p.is_file()}

    with pytest.raises(IncompleteSourceError):
        archive_run(complete_run, apply=True)

    assert {p for p in complete_run.rglob("*") if p.is_file()} == before


def test_documented_recovery_finishes_the_shard(complete_run: Path):
    """The recovery the error prescribes: drop the residual source, re-run."""
    shard, source, tar_path = _tar_one_shard(complete_run)
    next(p for p in sorted(source.rglob("*")) if p.is_file()).unlink()
    with pytest.raises(IncompleteSourceError):
        archive_run(complete_run, apply=True)

    shutil.rmtree(source)  # the operator's one manual step
    result = archive_run(complete_run, apply=True)

    by_shard = {o.shard: o for o in result.outcomes}
    assert by_shard[shard].action == "skipped"
    assert tar_path.is_file()
    assert not any(institutions_root(complete_run).iterdir())


def test_modified_source_file_is_still_a_failed_tar(complete_run: Path):
    """Same names, different bytes is a real anomaly, not an interrupted delete."""
    _shard, source, tar_path = _tar_one_shard(complete_run)
    victim = next(p for p in sorted(source.rglob("*")) if p.is_file())
    victim.write_bytes(victim.read_bytes() + b"tampered")

    with pytest.raises(VerificationError):
        archive_run(complete_run, apply=True)

    assert tar_path.with_name(tar_path.name + FAILED_SUFFIX).is_file()
    assert not tar_path.exists()


def test_extra_source_file_is_still_a_failed_tar(complete_run: Path):
    """A source with a file the tar lacks is not a subset — .FAILED applies."""
    _shard, source, tar_path = _tar_one_shard(complete_run)
    (next(d for d in sorted(source.iterdir()) if d.is_dir()) / "stray.json").write_text(
        "{}", encoding="utf-8"
    )

    with pytest.raises(VerificationError):
        archive_run(complete_run, apply=True)

    assert tar_path.with_name(tar_path.name + FAILED_SUFFIX).is_file()


def test_freshly_written_tar_that_mismatches_still_fails_closed(complete_run: Path):
    """The superset exemption is for pre-existing tars only.

    A tar written this pass that does not match was produced against a source
    mutating underneath it; it earns no trust, and the .FAILED path applies.
    """
    import g3o.run.archive as archive_mod

    real_walk = archive_mod.walk_shard
    calls = {"n": 0}

    def _shrinking_walk(shard_dir: Path):
        # First call is _write_tar's plan walk; the verification walk that
        # follows sees one fewer file, as a concurrent deleter would produce.
        calls["n"] += 1
        stat = real_walk(shard_dir)
        if calls["n"] > 1 and stat.n_files:
            return type(stat)(
                n_files=stat.n_files - 1, n_bytes=stat.n_bytes, n_dirs=stat.n_dirs
            )
        return stat

    shard = sorted(institution_shard(i) for i in INSTS)[0]
    tar_path = shard_tar_path(complete_run, shard)
    archive_mod.walk_shard = _shrinking_walk
    try:
        with pytest.raises(VerificationError):
            archive_run(complete_run, apply=True)
    finally:
        archive_mod.walk_shard = real_walk

    assert tar_path.with_name(tar_path.name + FAILED_SUFFIX).is_file()


def test_delete_failure_reports_the_recovery_path(complete_run: Path, monkeypatch):
    """rmtree blowing up gives an actionable ArchiveError, not a traceback."""
    import g3o.run.archive as archive_mod

    def _boom(path):
        raise PermissionError("file in use")

    monkeypatch.setattr(archive_mod.shutil, "rmtree", _boom)

    with pytest.raises(DeleteFailedError) as exc:
        archive_run(complete_run, apply=True)

    message = str(exc.value)
    assert "NOT renamed" in message
    assert "re-run" in message
    assert isinstance(exc.value, ArchiveError), "the CLI catches ArchiveError"


def test_cli_reports_an_interrupted_delete_as_exit_2(complete_run: Path, capsys):
    from g3o.cli import main

    _shard, source, _tar = _tar_one_shard(complete_run)
    next(p for p in sorted(source.rglob("*")) if p.is_file()).unlink()

    code = main(["archive", "--run-dir", str(complete_run), "--apply"])

    assert code == 2
    assert "strict superset" in capsys.readouterr().err
