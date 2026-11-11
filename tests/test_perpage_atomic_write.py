"""stage_perpage_v27._atomic_write: bounded retry of a transient Windows PermissionError (offline)."""
from __future__ import annotations

import os

import pytest

from g3o.run.presweep import stage_perpage_v27 as pp


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(pp.time, "sleep", lambda s: None)


def test_replace_that_fails_once_is_retried_and_lands(tmp_path, monkeypatch):
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 1:
            raise PermissionError(5, "Access is denied")
        return real(src, dst)
    monkeypatch.setattr(pp.os, "replace", flaky)
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
    monkeypatch.setattr(pp.os, "replace", denied)
    with pytest.raises(PermissionError, match=rf"\({pp.REPLACE_ATTEMPTS}\)"):
        pp._atomic_write(tmp_path / "ckpt.json", "{}")
    assert len(calls) == pp.REPLACE_ATTEMPTS
    assert not (tmp_path / "ckpt.json").exists()


def test_other_os_errors_are_not_retried(tmp_path, monkeypatch):
    calls = []

    def missing(src, dst):
        calls.append(dst)
        raise FileNotFoundError(2, "gone")
    monkeypatch.setattr(pp.os, "replace", missing)
    with pytest.raises(FileNotFoundError):
        pp._atomic_write(tmp_path / "ckpt.json", "{}")
    assert len(calls) == 1
