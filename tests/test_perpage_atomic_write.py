"""Bounded retry of a transient Windows PermissionError (offline): the per-page checkpoint write
(stage_perpage_v27._atomic_write) and the shared stage6_adapters.write_atomic."""
from __future__ import annotations

import os

import pytest

from g3o.persist import stage6_adapters as adapters
from g3o.run.presweep import stage_perpage_v27 as pp


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
