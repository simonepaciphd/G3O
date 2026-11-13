"""Bounded retry of a transient Windows PermissionError (offline): the per-page checkpoint write
(stage_perpage_v27._atomic_write) and the shared stage6_adapters.write_atomic."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from g3o.persist import stage6_adapters as adapters
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep import stage_validate_v27 as rt


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(adapters.time, "sleep", lambda s: None)


def test_replace_that_fails_once_is_retried_and_lands(tmp_path, monkeypatch):
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 1:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)
    monkeypatch.setattr(adapters.os, "replace", flaky)
    target = tmp_path / "sub" / "ckpt.json"
    pp._atomic_write(target, '{"a":1}')
    assert len(calls) == 2
    assert target.read_text(encoding="utf-8") == '{"a":1}'
    assert not (tmp_path / "sub" / "ckpt.json.tmp").exists()


def test_replace_that_always_fails_raises_the_last_error(tmp_path, monkeypatch):
    calls = []

    def denied(src, dst):
        calls.append(dst)
        raise PermissionError(5, f"Access is denied ({len(calls)})")
    monkeypatch.setattr(adapters.os, "replace", denied)
    with pytest.raises(PermissionError, match=rf"\({adapters.REPLACE_ATTEMPTS}\)"):
        pp._atomic_write(tmp_path / "ckpt.json", "{}")
    assert len(calls) == adapters.REPLACE_ATTEMPTS
    assert not (tmp_path / "ckpt.json").exists()


def test_other_os_errors_are_not_retried(tmp_path, monkeypatch):
    calls = []

    def missing(src, dst):
        calls.append(dst)
        raise FileNotFoundError(2, "gone")
    monkeypatch.setattr(adapters.os, "replace", missing)
    with pytest.raises(FileNotFoundError):
        pp._atomic_write(tmp_path / "ckpt.json", "{}")
    assert len(calls) == 1


# --- QA round 3, F6 a: the shared Stage 6 artifact / journal-repair write uses the same retry


def test_write_atomic_retries_a_transient_permission_error(tmp_path, monkeypatch):
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) < 3:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)
    monkeypatch.setattr(adapters.os, "replace", flaky)
    target = tmp_path / "6_storage.json"
    adapters.write_atomic(target, b'{"a":1}')
    assert len(calls) == 3 and target.read_bytes() == b'{"a":1}'
    assert not (tmp_path / "6_storage.json.tmp").exists()


def test_write_atomic_gives_up_after_the_bound_and_leaves_no_temp_file(tmp_path, monkeypatch):
    calls = []

    def denied(src, dst):
        calls.append(dst)
        raise PermissionError(5, f"Access is denied ({len(calls)})")
    monkeypatch.setattr(adapters.os, "replace", denied)
    with pytest.raises(PermissionError, match=rf"\({adapters.REPLACE_ATTEMPTS}\)"):
        adapters.write_atomic(tmp_path / "6_storage.json", b"{}")
    assert len(calls) == adapters.REPLACE_ATTEMPTS
    assert not (tmp_path / "6_storage.json").exists() and not (tmp_path / "6_storage.json.tmp").exists()


def test_write_atomic_does_not_retry_other_os_errors(tmp_path, monkeypatch):
    calls = []

    def missing(src, dst):
        calls.append(dst)
        raise FileNotFoundError(2, "gone")
    monkeypatch.setattr(adapters.os, "replace", missing)
    with pytest.raises(FileNotFoundError):
        adapters.write_atomic(tmp_path / "6_storage.json", b"{}")
    assert len(calls) == 1 and not (tmp_path / "6_storage.json.tmp").exists()


# --- ruling 34 b / 41 a / 47.2 a / 28 a: PI release edge cases (_apply_pi_release, offline) ---

KEY, OTHER = "a" * 64, "b" * 64


def _journal(inst_dir, rejected=(KEY,)):
    path = inst_dir / pp.WORK_DIR / pp.JOURNAL
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"kind": rt.EXTRACT_REJECTED, "key": k, "n": n, "response": {}, "elapsed_ms": 0})
             for n, k in enumerate(rejected)]
    path.write_bytes("".join(line + "\n" for line in lines).encode("utf-8"))
    return rt.RequestJournal(path, {})


def _release(inst_dir, doc):
    raw = json.dumps(doc).encode("utf-8")
    (inst_dir / pp.PI_RELEASE_FILE).write_bytes(raw)
    return raw


def _kinds(inst_dir):
    path = inst_dir / pp.WORK_DIR / pp.JOURNAL
    return [json.loads(line)["kind"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _archive(inst_dir):
    return inst_dir / pp.PAGE_ARCHIVE_DIR / pp.PI_RELEASE_ARCHIVE


def test_release_naming_a_key_with_no_rejection_is_malformed(tmp_path):
    journal = _journal(tmp_path)
    _release(tmp_path, {"released_by": "PI", "date": "2026-11-12", "keys": [KEY, OTHER]})
    hold = pp._apply_pi_release(tmp_path, journal)
    assert hold["stage"] == pp.PI_RELEASE_MALFORMED and hold["error"].startswith("refused")
    assert OTHER in hold["error"] and KEY not in hold["error"]
    assert (tmp_path / pp.PI_RELEASE_FILE).exists() and not _archive(tmp_path).exists()
    assert "pi_released" not in _kinds(tmp_path) and journal.rejections(KEY) == 1


@pytest.mark.parametrize("date", ["20261112", "2026-W46-4", "2026-11-12T00:00", "2026-1-12", " 2026-11-12",
                                  "2026-11-12\n", "2026-13-01"])
def test_release_date_must_be_exactly_yyyy_mm_dd(tmp_path, date):
    with pytest.raises(ValueError, match="date"):
        pp.parse_pi_release(json.dumps({"released_by": "PI", "date": date, "all": True}).encode("utf-8"))
    journal = _journal(tmp_path)
    _release(tmp_path, {"released_by": "PI", "date": date, "all": True})
    hold = pp._apply_pi_release(tmp_path, journal)
    assert hold["stage"] == pp.PI_RELEASE_MALFORMED and "date" in hold["error"]
    assert (tmp_path / pp.PI_RELEASE_FILE).exists()


def test_release_file_is_read_once_and_those_bytes_hashed(tmp_path, monkeypatch):
    journal = _journal(tmp_path)
    raw = _release(tmp_path, {"released_by": "PI", "date": "2026-11-12", "keys": [KEY]})
    real, reads = Path.read_bytes, []

    def counting(self):
        if self.name == pp.PI_RELEASE_FILE:
            reads.append(self)
        return real(self)
    monkeypatch.setattr(Path, "read_bytes", counting)
    assert pp._apply_pi_release(tmp_path, journal) is None
    assert len(reads) == 1
    assert journal.release_applied(hashlib.sha256(raw).hexdigest())


def test_byte_identical_release_is_only_archived(tmp_path):
    # Ruling 47.2 a: the same bytes again are archived, not re-applied (the count is not reset again)
    journal = _journal(tmp_path)
    doc = {"released_by": "PI", "date": "2026-11-12", "keys": [KEY]}
    _release(tmp_path, doc)
    assert pp._apply_pi_release(tmp_path, journal) is None and journal.rejections(KEY) == 0
    with journal.path.open("ab") as stream:  # one new rejection after the release
        stream.write(json.dumps({"kind": rt.EXTRACT_REJECTED, "key": KEY, "n": 9, "response": {},
                                 "elapsed_ms": 0}).encode("utf-8") + b"\n")
    journal = rt.RequestJournal(journal.path, {})
    assert journal.rejections(KEY) == 1
    _release(tmp_path, doc)
    assert pp._apply_pi_release(tmp_path, journal) is None
    assert journal.rejections(KEY) == 1 and _kinds(tmp_path).count("pi_released") == 1
    assert not (tmp_path / pp.PI_RELEASE_FILE).exists()
    assert sorted(p.name for p in _archive(tmp_path).iterdir()) == ["001", "002"]
    assert pp._cap_hold("p1", "pass1", "c1", KEY, 3, "d")["error"].count("byte-identical") == 1


def test_release_journal_write_error_holds_the_institution(tmp_path, monkeypatch):
    # Ruling 28 a: an OSError recording the release holds this institution; it is not a stage stop
    journal = _journal(tmp_path)
    _release(tmp_path, {"released_by": "PI", "date": "2026-11-12", "keys": [KEY]})

    def denied(release):
        raise PermissionError(5, "Access is denied")
    monkeypatch.setattr(journal, "record_release", denied)
    hold = pp._apply_pi_release(tmp_path, journal)
    assert hold["stage"] == pp.PI_RELEASE_RECORD_FAILED and "PermissionError" in hold["error"]
    assert (tmp_path / pp.PI_RELEASE_FILE).exists() and not _archive(tmp_path).exists()
    assert journal.rejections(KEY) == 1 and "pi_released" not in _kinds(tmp_path)


def test_failed_archive_move_leaves_no_empty_folder(tmp_path, monkeypatch):
    journal = _journal(tmp_path)
    _release(tmp_path, {"released_by": "PI", "date": "2026-11-12", "keys": [KEY]})

    def denied(src, dst):
        raise PermissionError(5, "Access is denied")
    monkeypatch.setattr(pp, "replace_with_retry", denied)
    hold = pp._apply_pi_release(tmp_path, journal)
    assert hold["stage"] == pp.PI_RELEASE_ARCHIVE_FAILED and hold["error"].startswith("release recorded")
    assert (tmp_path / pp.PI_RELEASE_FILE).exists()
    assert list(_archive(tmp_path).iterdir()) == []  # no empty <NNN> folder
    assert _kinds(tmp_path).count("pi_released") == 1
    monkeypatch.undo()
    # the next run only finishes the move: the same bytes are not re-applied, and land in 001
    assert pp._apply_pi_release(tmp_path, rt.RequestJournal(journal.path, {})) is None
    assert [p.name for p in _archive(tmp_path).iterdir()] == ["001"]
    assert _kinds(tmp_path).count("pi_released") == 1
