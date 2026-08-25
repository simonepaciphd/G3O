"""Leg 4 — the archive bundle, its checksums, and verification after upload.

The claim an archive makes is "the copy over there is the copy that was here".
These tests are about the evidence for that claim: that the bundle contains the
whole run record, that ``SHA256SUMS`` is the file the PI can check with coreutils
on a machine with no G3O checkout, and that a store which corrupts what it is
given is caught rather than reported as uploaded.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from g3o.common import run_state
from g3o.common.paths import institutions_root
from g3o.run.archive import archive_root
from g3o.run.orchestrate import archive_leg as al
from g3o.run.orchestrate.objectstore import LocalObjectStore, store_from_uri
from g3o.run.orchestrate.status import run_status
from g3o.run.presweep.config import STAGES
from tests._layout import make_inst_dir
from tests._orchestrate import event, make_run, write_final_csvs

INSTS = ("INST-0000001", "INST-0000002")


@pytest.fixture()
def finished_run(tmp_path: Path) -> tuple[Path, str]:
    """A run in exactly the state ``g3o archive`` requires: complete, reported."""
    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir,
        config={"dry_run": False},
        events=[event(1, "run_launched"), event(2, "run_completed", outcome="completed")],
    )
    write_final_csvs(run_dir, institutions=list(INSTS))
    for stage in STAGES:
        run_state.mark_done(run_dir, stage, no_batch=True)
    (run_dir / "run_summary.json").write_text('{"ok": true}', encoding="utf-8")
    (run_dir / "_health_report.json").write_text('{"overall_flag": "green"}', encoding="utf-8")
    (run_dir / "_attrition.jsonl").write_text(
        '{"institution_id": "INST-0000001", "stage": "scrape", "reason": "http_404"}\n',
        encoding="utf-8",
    )
    for inst in INSTS:
        d = make_inst_dir(run_dir, inst)
        (d / "institution.json").write_text(f'{{"institution_id": "{inst}"}}', encoding="utf-8")
        (d / "scrape").mkdir()
        (d / "scrape" / "page.json").write_text('{"text": "hello"}' * 5, encoding="utf-8")
    return runs_dir, run_dir.name


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------


def test_the_bundle_is_the_whole_run_record_minus_the_live_tree(
    finished_run: tuple[Path, str]
) -> None:
    runs_dir, run_id = finished_run
    al.archive_and_upload(runs_dir, run_id, apply=True)
    members = {m.relpath for m in al.collect_bundle(runs_dir / run_id)}

    assert "manifest.json" in members
    assert "_attrition.jsonl" in members
    assert "run_summary.json" in members
    assert any(m.startswith("final/") for m in members)
    assert any(m.startswith("_state/") for m in members)
    assert any(m.startswith("archive/institutions/") and m.endswith(".tar") for m in members)
    # The live tree is gone (archive --apply removed it) and would be excluded anyway.
    assert not any(m.startswith("institutions/") for m in members)
    # Generated bundle files cannot be members of the set they describe.
    assert not any(m.endswith(al.SHA256SUMS_FILENAME) for m in members)


def test_bundle_excludes_half_written_temp_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (run_dir / "manifest.json.tmp.9999").write_text("{", encoding="utf-8")

    members = {m.relpath for m in al.collect_bundle(run_dir)}

    assert members == {"manifest.json"}


def test_sha256sums_is_coreutils_checkable(finished_run: tuple[Path, str]) -> None:
    """The format is the point: ``cd <run_id> && sha256sum -c SHA256SUMS``."""
    runs_dir, run_id = finished_run
    result = al.archive_and_upload(runs_dir, run_id, apply=True)
    run_dir = runs_dir / run_id

    lines = result.sha256sums_path.read_text(encoding="utf-8").splitlines()
    assert lines, "SHA256SUMS is empty"
    for line in lines:
        digest, _, relpath = line.partition("  ")
        assert len(digest) == 64 and int(digest, 16) >= 0
        assert "\\" not in relpath
        # Every listed path resolves against the run dir, except the ledger,
        # which is uploaded at the bundle root beside SHA256SUMS itself.
        if relpath != al.LEDGER_FILENAME:
            assert (run_dir / relpath).is_file()
            assert al.sha256_file(run_dir / relpath) == digest
    assert any(line.endswith(al.LEDGER_FILENAME) for line in lines)


def test_the_ledger_lists_the_files_inside_the_tars(finished_run: tuple[Path, str]) -> None:
    """Uncompressed, and browsable: that is why it exists."""
    runs_dir, run_id = finished_run
    result = al.archive_and_upload(runs_dir, run_id, apply=True)

    rows = [
        json.loads(line)
        for line in result.ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kinds = [r["kind"] for r in rows]
    assert kinds[0] == "bundle"
    assert rows[0]["run_id"] == run_id
    assert "member" in kinds
    tar_members = [r for r in rows if r["kind"] == "tar_member"]
    assert tar_members, "no tar members listed — the archive would not be browsable"
    assert any("institution.json" in r["path"] for r in tar_members)
    assert all("bytes" in r for r in tar_members)


def test_the_bundle_is_reproducible_for_an_unchanged_run(
    finished_run: tuple[Path, str]
) -> None:
    """Two passes over a finished run produce the same sums file, byte for byte."""
    runs_dir, run_id = finished_run
    first = al.archive_and_upload(runs_dir, run_id, apply=True)
    first_bytes = first.sha256sums_path.read_bytes()
    second = al.archive_and_upload(runs_dir, run_id, apply=True)

    assert second.sha256sums_path.read_bytes() == first_bytes


def test_the_bundle_is_reproducible_across_a_change_of_clock(
    finished_run: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same assertion, with the wall clock moved between the two passes.

    The test above passed by luck until 2026-08-23: the ledger's ``bundle`` line
    carried a ``created_at`` of *now* at one-second precision, so two passes
    agreed only when both landed inside the same second. It reddened CI at random,
    including on documentation-only pull requests (#85).

    Forcing the clock forward is what makes the property testable rather than
    probable. Every hash in ``SHA256SUMS`` must be a function of the run, so a
    field that moves with the clock cannot be inside the hashed surface — if this
    fails, something reintroduced one, and the failure it causes in CI will look
    like flake rather than like this.
    """
    runs_dir, run_id = finished_run

    stamps = iter(
        ["2026-08-23T00:00:00Z", "2026-08-23T00:00:01Z", "2027-01-01T12:34:56Z"] * 20
    )
    monkeypatch.setattr(al, "utc_now_iso", lambda: next(stamps))

    first = al.archive_and_upload(runs_dir, run_id, apply=True)
    first_sums = first.sha256sums_path.read_bytes()
    first_ledger = first.ledger_path.read_bytes()
    second = al.archive_and_upload(runs_dir, run_id, apply=True)

    assert second.ledger_path.read_bytes() == first_ledger
    assert second.sha256sums_path.read_bytes() == first_sums


# ---------------------------------------------------------------------------
# Upload and verification
# ---------------------------------------------------------------------------


def test_every_object_is_read_back_and_matched(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    runs_dir, run_id = finished_run
    dest = tmp_path / "bucket"

    result = al.archive_and_upload(runs_dir, run_id, apply=True, destination=str(dest))

    assert result.uploaded and result.verified
    assert result.n_failed == 0
    assert all(o.observed_sha256 == o.expected_sha256 for o in result.objects)
    keys = {o.relpath for o in result.objects}
    assert al.SHA256SUMS_FILENAME in keys and al.LEDGER_FILENAME in keys
    # And the bytes really are on the far side, addressed by run id.
    assert (dest / run_id / al.SHA256SUMS_FILENAME).is_file()
    assert "read back out of the store" in al.render_archive(result)


def test_a_store_that_corrupts_an_object_fails_verification(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    """The whole argument for streaming the bytes back instead of trusting a 200."""

    class CorruptingStore(LocalObjectStore):
        def put(self, key: str, path: Path) -> None:
            super().put(key, path)
            if key.endswith("manifest.json"):
                self._path(key).write_bytes(b"{}")

    runs_dir, run_id = finished_run
    store = CorruptingStore(tmp_path / "bucket")

    result = al.archive_and_upload(runs_dir, run_id, apply=True, destination=store)

    assert result.uploaded
    assert not result.verified
    assert result.n_failed == 1
    bad = next(o for o in result.objects if not o.verified)
    assert bad.relpath == "manifest.json"
    assert "mismatch" in bad.error
    # One bad object does not stop the rest: a partial upload must be finishable.
    assert sum(1 for o in result.objects if o.verified) == len(result.objects) - 1
    assert "did NOT verify" in al.render_archive(result)


def test_an_unwritable_store_reports_per_object_and_continues(tmp_path: Path) -> None:
    from g3o.run.orchestrate.objectstore import ObjectStoreError

    class RefusingStore(LocalObjectStore):
        def put(self, key: str, path: Path) -> None:
            if key.endswith("b.txt"):
                raise ObjectStoreError("no space left on device")
            super().put(key, path)

    a, b, c = (tmp_path / n for n in ("a.txt", "b.txt", "c.txt"))
    for path in (a, b, c):
        path.write_text(path.name, encoding="utf-8")
    store = RefusingStore(tmp_path / "bucket")

    outcomes = al.upload_and_verify(
        store, "r1", [(p.name, p, al.sha256_file(p)) for p in (a, b, c)]
    )

    assert [o.uploaded for o in outcomes] == [True, False, True]
    assert outcomes[1].error and "no space" in outcomes[1].error


def test_local_and_s3_uris_resolve_to_stores(tmp_path: Path) -> None:
    assert isinstance(store_from_uri(str(tmp_path)), LocalObjectStore)
    assert isinstance(store_from_uri(tmp_path.as_uri()), LocalObjectStore)
    with pytest.raises(Exception, match="unsupported destination scheme"):
        store_from_uri("ftp://example.org/x")


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def test_a_dry_pass_writes_and_deletes_nothing(finished_run: tuple[Path, str]) -> None:
    runs_dir, run_id = finished_run
    run_dir = runs_dir / run_id

    result = al.archive_and_upload(runs_dir, run_id, apply=False)

    assert not result.applied and not result.uploaded
    assert not archive_root(run_dir).exists()
    assert institutions_root(run_dir).is_dir()
    assert "dry run" in al.render_archive(result)


def test_an_unfinished_run_is_refused(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(runs_dir, events=[event(1, "run_launched"), event(2, "stage_started", stage="scrape")])
    write_final_csvs(run_dir)

    with pytest.raises(al.ArchiveLegError, match="refusing to archive"):
        al.archive_and_upload(runs_dir, run_dir.name, apply=True)


def test_an_incomplete_run_refuses_at_the_archive_preconditions(
    tmp_path: Path
) -> None:
    """`g3o.run.archive` owns this refusal; the leg passes it through unchanged."""
    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir, config={"dry_run": False},
        events=[event(1, "run_launched"), event(2, "run_completed", outcome="completed")],
    )
    # No Stage-7 CSVs, no .done markers, no reports.
    with pytest.raises(al.ArchiveLegError, match="not a completed run"):
        al.archive_and_upload(runs_dir, run_dir.name, apply=True)
    assert run_status(runs_dir, run_dir.name).legs["archive"]["outcome"] == "refused"


def test_a_surviving_live_tree_blocks_the_upload(
    finished_run: tuple[Path, str], tmp_path: Path, monkeypatch
) -> None:
    """Uploading with the tree still present would archive an incomplete run."""
    runs_dir, run_id = finished_run

    def _no_op_archive(run_dir, *, apply=False):
        from g3o.run.archive import ArchiveResult

        return ArchiveResult(run_dir=run_dir, applied=apply, outcomes=())

    monkeypatch.setattr(al, "archive_run", _no_op_archive)

    with pytest.raises(al.ArchiveLegError, match="still holds files"):
        al.archive_and_upload(runs_dir, run_id, apply=True, destination=str(tmp_path / "b"))


def test_the_leg_record_names_the_destination_without_secrets(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    runs_dir, run_id = finished_run
    al.archive_and_upload(runs_dir, run_id, apply=True, destination=str(tmp_path / "bucket"))

    record = run_status(runs_dir, run_id).legs["archive"]
    assert record["outcome"] == "verified"
    assert record["n_members"] > 0
    assert record["destination"]["kind"] == "local"


# ---------------------------------------------------------------------------
# The other end: the PI's machine
# ---------------------------------------------------------------------------

PULL_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "orchestrator" / "pull_run_archive.py"


def _pull_verify(dest: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PULL_SCRIPT), "--run-id", dest.name, "--dest", str(dest.parent),
         "--verify-only"],
        capture_output=True, text=True, check=False,
    )


def test_the_pull_script_verifies_what_this_leg_wrote(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    """The two programs share a format, not code — so the format is what is tested.

    ``pull_run_archive.py`` is standalone by design (it runs on a machine with no
    G3O checkout), which means its ``SHA256SUMS`` reader is a second
    implementation. This is the test that keeps the two from drifting apart.
    """
    runs_dir, run_id = finished_run
    bucket = tmp_path / "bucket"
    al.archive_and_upload(runs_dir, run_id, apply=True, destination=str(bucket))

    proc = _pull_verify(bucket / run_id)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "verified by sha256" in proc.stdout


def test_the_pull_script_catches_a_corrupted_copy(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    """What a sync client truncating a file in Drive would look like."""
    runs_dir, run_id = finished_run
    bucket = tmp_path / "bucket"
    al.archive_and_upload(runs_dir, run_id, apply=True, destination=str(bucket))
    (bucket / run_id / "manifest.json").write_text("{}", encoding="utf-8")

    proc = _pull_verify(bucket / run_id)

    assert proc.returncode == 1
    assert "MISMATCH manifest.json" in proc.stdout


def test_the_pull_script_notices_a_missing_file(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    runs_dir, run_id = finished_run
    bucket = tmp_path / "bucket"
    al.archive_and_upload(runs_dir, run_id, apply=True, destination=str(bucket))
    (bucket / run_id / al.LEDGER_FILENAME).unlink()

    proc = _pull_verify(bucket / run_id)

    assert proc.returncode == 1
    assert f"MISSING  {al.LEDGER_FILENAME}" in proc.stdout


def test_tars_hold_what_the_ledger_says_they_hold(finished_run: tuple[Path, str]) -> None:
    """Cross-check the inventory against the tar itself, not against the writer."""
    runs_dir, run_id = finished_run
    result = al.archive_and_upload(runs_dir, run_id, apply=True)
    run_dir = runs_dir / run_id

    listed: dict[str, set[str]] = {}
    for line in result.ledger_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["kind"] == "tar_member":
            listed.setdefault(row["tar"], set()).add(row["path"])

    for relpath, names in listed.items():
        with tarfile.open(run_dir / relpath, mode="r:") as tar:
            actual = {m.name for m in tar if m.isfile()}
        assert actual == names


# ---------------------------------------------------------------------------
# The destination is proved reachable BEFORE the delete (#78)
# ---------------------------------------------------------------------------


class _UnreachableStore(LocalObjectStore):
    """A store whose every operation fails, as a wrong endpoint or key would.

    `S3ObjectStore.__init__` validates only local config — `boto3.client()` makes
    no network call — so DNS, TLS, credentials, bucket existence and region are
    all deferred to the first real request. This models that first request
    failing.
    """

    def list_keys(self, prefix: str = "") -> list[str]:
        from g3o.run.orchestrate.objectstore import ObjectStoreError

        raise ObjectStoreError("could not resolve endpoint")

    def put(self, key: str, path: Path) -> None:  # pragma: no cover - never reached
        raise AssertionError("put must not be attempted on an unreachable store")


def test_an_unreachable_destination_refuses_with_every_shard_intact(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    """#78: the endpoint used to be first contacted *after* the tree was deleted.

    The bytes were never lost — they were in the local tars — but the archive was
    half-complete and the only copy of a finished run sat on the droplet it was
    being archived away from. The assertion that matters here is the last one.
    """
    from g3o.common.paths import institutions_root

    runs_dir, run_id = finished_run
    run_dir = runs_dir / run_id
    before = sorted(p.name for p in institutions_root(run_dir).iterdir())
    assert before, "fixture should start with a live institution tree"

    with pytest.raises(al.ArchiveLegError) as exc:
        al.archive_and_upload(
            runs_dir, run_id, apply=True, destination=_UnreachableStore(tmp_path / "b")
        )

    assert "not reachable" in str(exc.value)
    assert "nothing was deleted" in str(exc.value).lower()
    after = sorted(p.name for p in institutions_root(run_dir).iterdir())
    assert after == before, "the institution tree must survive an unreachable store"
    assert not (run_dir / al.ARCHIVE_DIRNAME).exists(), "nothing should have been tarred"


def test_the_dry_pass_also_probes_the_destination(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    """`archive --destination` without `--apply` is now a real upload preflight.

    It previously returned before the store was constructed at all, so it could
    not tell an operator their endpoint was wrong — which is what made the
    fra1/sfo3 question load-bearing rather than merely a docs detail.
    """
    runs_dir, run_id = finished_run

    with pytest.raises(al.ArchiveLegError) as exc:
        al.archive_and_upload(
            runs_dir, run_id, apply=False, destination=_UnreachableStore(tmp_path / "b")
        )
    assert "not reachable" in str(exc.value)


def test_a_reachable_destination_dry_pass_reports_it(
    finished_run: tuple[Path, str], tmp_path: Path
) -> None:
    runs_dir, run_id = finished_run
    store = LocalObjectStore(tmp_path / "bucket")

    result = al.archive_and_upload(runs_dir, run_id, apply=False, destination=store)

    assert result.applied is False
    assert result.destination, "the dry pass should name the destination it probed"
