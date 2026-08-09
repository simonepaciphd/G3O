"""Bulk-artifact encoding — :mod:`g3o.common.artifact_io` (spec §6, Phase 2).

Covers the four properties the spec names (``docs/storage-layout-v2.md`` §A1):
round-trip, ``.json``/``.json.gz`` duality with ``.gz`` winning, byte-identical
output for identical input, and ``glob_artifacts`` dedup — plus the two things
Phase 2 folded in: the ``artifact_stem`` trap that ``Path.stem`` walks into, and
the review-F7 atomic-write / quarantine behavior.
"""

from __future__ import annotations

import gzip
import threading
from pathlib import Path

import pytest

from g3o.common.artifact_io import (
    ARTIFACT_SUFFIX,
    CORRUPT_SUFFIX,
    artifact_exists,
    artifact_stem,
    glob_artifacts,
    gz_path,
    plain_path,
    quarantine_artifact,
    read_artifact,
    write_artifact,
)

_HASH = "0123456789abcdef0123456789abcdef"
_TEXT = '{"url": "https://x.example/a", "text": "genai évidence", "n": 1}'


def _artifact(tmp_path: Path, name: str = _HASH) -> Path:
    """The logical (suffix-undecided) artifact path callers pass in."""
    return tmp_path / "scrape" / f"{name}.json"


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_write_artifact_round_trips_through_read_artifact(tmp_path: Path):
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    assert read_artifact(path) == _TEXT


def test_write_artifact_writes_gz_and_only_gz(tmp_path: Path):
    """The writer emits one format; it never leaves a plain twin behind."""
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    assert gz_path(path).exists()
    assert not plain_path(path).exists()
    assert gz_path(path).name.endswith(ARTIFACT_SUFFIX)


def test_written_bytes_are_real_gzip_and_utf8(tmp_path: Path):
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    raw = gz_path(path).read_bytes()
    assert raw[:2] == b"\x1f\x8b"  # gzip magic
    assert gzip.decompress(raw).decode("utf-8") == _TEXT


def test_write_artifact_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "a" / "b" / "c" / f"{_HASH}.json"
    write_artifact(path, _TEXT)
    assert read_artifact(path) == _TEXT


def test_write_artifact_accepts_an_already_gz_path(tmp_path: Path):
    """``gz_path`` is idempotent, so passing the resolved path means the same."""
    path = _artifact(tmp_path)
    write_artifact(gz_path(path), _TEXT)
    assert read_artifact(path) == _TEXT
    assert not plain_path(path).exists()


def test_write_artifact_overwrites_in_place(tmp_path: Path):
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    write_artifact(path, '{"v": 2}')
    assert read_artifact(path) == '{"v": 2}'
    assert len(list(gz_path(path).parent.iterdir())) == 1


# ---------------------------------------------------------------------------
# .json / .json.gz duality — gz wins
# ---------------------------------------------------------------------------


def test_read_artifact_reads_a_plain_json_artifact(tmp_path: Path):
    """A pre-Phase-2 or hand-built tree still reads."""
    path = _artifact(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(_TEXT, encoding="utf-8")
    assert read_artifact(path) == _TEXT


def test_gz_wins_when_both_forms_exist(tmp_path: Path):
    path = _artifact(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"which": "plain"}', encoding="utf-8")
    write_artifact(path, '{"which": "gz"}')
    assert read_artifact(path) == '{"which": "gz"}'
    # Asking by either name resolves to the same winner.
    assert read_artifact(gz_path(path)) == '{"which": "gz"}'
    assert read_artifact(plain_path(path)) == '{"which": "gz"}'


def test_artifact_exists_accepts_either_form(tmp_path: Path):
    gz_only = _artifact(tmp_path, "aaa")
    plain_only = _artifact(tmp_path, "bbb")
    absent = _artifact(tmp_path, "ccc")
    write_artifact(gz_only, _TEXT)
    plain_only.write_text(_TEXT, encoding="utf-8")

    assert artifact_exists(gz_only)
    assert artifact_exists(plain_only)
    assert not artifact_exists(absent)
    # Suffix-insensitive: the caller's spelling doesn't change the answer.
    assert artifact_exists(gz_path(plain_only))
    assert artifact_exists(plain_path(gz_only))


def test_read_artifact_raises_when_neither_form_exists(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        read_artifact(_artifact(tmp_path))


# ---------------------------------------------------------------------------
# Byte-identical output for identical input (the mtime=0 / FNAME pins)
# ---------------------------------------------------------------------------


def test_identical_input_produces_identical_bytes(tmp_path: Path):
    """The mtime=0 pin: no wall-clock leaks into the gzip header."""
    a, b = _artifact(tmp_path / "one"), _artifact(tmp_path / "two")
    write_artifact(a, _TEXT)
    write_artifact(b, _TEXT)
    assert gz_path(a).read_bytes() == gz_path(b).read_bytes()


def test_rewriting_the_same_path_produces_identical_bytes(tmp_path: Path):
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    first = gz_path(path).read_bytes()
    write_artifact(path, _TEXT)
    assert gz_path(path).read_bytes() == first


def test_gzip_header_mtime_field_is_zero(tmp_path: Path):
    """States the pin explicitly: header bytes 4:8 are the little-endian MTIME."""
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    assert gz_path(path).read_bytes()[4:8] == b"\x00\x00\x00\x00"


def test_gzip_header_carries_no_filename_field(tmp_path: Path):
    """FLG bit 3 (FNAME) must be clear.

    The writer lands on a temp file whose name carries a pid and a thread id.
    Were the FNAME field populated from it, "identical input" would produce
    different bytes per writer — so this is the other half of determinism, not a
    cosmetic detail.
    """
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    flags = gz_path(path).read_bytes()[3]
    assert flags & 0b1000 == 0


def test_bytes_are_identical_across_writer_threads(tmp_path: Path):
    """Determinism must not depend on which thread (or process) wrote it."""
    main = _artifact(tmp_path / "main")
    other = _artifact(tmp_path / "other")
    write_artifact(main, _TEXT)
    t = threading.Thread(target=write_artifact, args=(other, _TEXT))
    t.start()
    t.join()
    assert gz_path(other).read_bytes() == gz_path(main).read_bytes()


# ---------------------------------------------------------------------------
# glob_artifacts — dedup, ordering, exclusions
# ---------------------------------------------------------------------------


def test_glob_artifacts_dedupes_by_stem_preferring_gz(tmp_path: Path):
    d = tmp_path / "extract"
    d.mkdir()
    (d / "aaa.json").write_text("{}", encoding="utf-8")
    write_artifact(d / "aaa.json", "{}")          # same stem, both forms
    (d / "bbb.json").write_text("{}", encoding="utf-8")  # plain only
    write_artifact(d / "ccc.json", "{}")          # gz only

    found = glob_artifacts(d)
    assert [artifact_stem(p) for p in found] == ["aaa", "bbb", "ccc"]
    assert [p.name for p in found] == ["aaa.json.gz", "bbb.json", "ccc.json.gz"]


def test_glob_artifacts_orders_by_stem_not_by_suffix(tmp_path: Path):
    """A mixed tree walks in the same order as a uniform one.

    Downstream row order (``load_extract_outputs``) depends on this, so it must
    not shift according to which files happen to be compressed.
    """
    d = tmp_path / "extract"
    d.mkdir()
    write_artifact(d / "b.json", "{}")
    (d / "a.json").write_text("{}", encoding="utf-8")
    write_artifact(d / "c.json", "{}")
    assert [artifact_stem(p) for p in glob_artifacts(d)] == ["a", "b", "c"]


def test_glob_artifacts_returns_empty_for_missing_dir(tmp_path: Path):
    assert glob_artifacts(tmp_path / "nope") == []


def test_glob_artifacts_returns_empty_for_empty_dir(tmp_path: Path):
    d = tmp_path / "scrape"
    d.mkdir()
    assert glob_artifacts(d) == []


def test_glob_artifacts_ignores_unrelated_and_quarantined_files(tmp_path: Path):
    d = tmp_path / "scrape"
    d.mkdir()
    write_artifact(d / "keep.json", "{}")
    (d / "notes.txt").write_text("x", encoding="utf-8")
    (d / f"gone.json{CORRUPT_SUFFIX}").write_text("x", encoding="utf-8")
    (d / f"gone2.json.gz{CORRUPT_SUFFIX}").write_text("x", encoding="utf-8")
    assert [artifact_stem(p) for p in glob_artifacts(d)] == ["keep"]


# ---------------------------------------------------------------------------
# artifact_stem — the Path.stem trap
# ---------------------------------------------------------------------------


def test_artifact_stem_strips_both_suffixes(tmp_path: Path):
    assert artifact_stem(Path(f"{_HASH}.json.gz")) == _HASH
    assert artifact_stem(Path(f"{_HASH}.json")) == _HASH


def test_path_stem_is_wrong_for_gz_artifacts():
    """Documents why ``artifact_stem`` exists at all.

    ``Path.stem`` strips one suffix, so a filename→url-hash comparison built on
    it silently matches nothing once artifacts are gzipped — a wrong count, not
    an exception. ``g3o.report.health`` had exactly this shape.
    """
    p = Path(f"{_HASH}.json.gz")
    assert p.stem == f"{_HASH}.json"
    assert p.stem != _HASH
    assert artifact_stem(p) == _HASH


# ---------------------------------------------------------------------------
# Review F7 — atomic write, quarantine
# ---------------------------------------------------------------------------


def test_write_artifact_leaves_no_temp_files(tmp_path: Path):
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    assert [p.name for p in gz_path(path).parent.iterdir()] == [gz_path(path).name]


def test_failed_write_cleans_up_its_temp_file(tmp_path: Path, monkeypatch):
    """A write that dies mid-swap must not leave a temp file behind."""
    import g3o.common.artifact_io as mod

    def _boom(src, dst):
        raise OSError("swap failed")

    monkeypatch.setattr(mod.os, "replace", _boom)
    path = _artifact(tmp_path)
    with pytest.raises(OSError):
        write_artifact(path, _TEXT)
    assert list((tmp_path / "scrape").iterdir()) == []


def test_failed_write_leaves_the_previous_artifact_intact(tmp_path: Path, monkeypatch):
    """Atomicity: a failed rewrite never truncates what was already there."""
    import g3o.common.artifact_io as mod

    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    monkeypatch.setattr(mod.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        write_artifact(path, '{"v": 2}')
    assert read_artifact(path) == _TEXT


def test_quarantine_moves_the_artifact_aside_and_keeps_the_bytes(tmp_path: Path):
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    dest = quarantine_artifact(path)

    assert dest.name == f"{_HASH}.json.gz{CORRUPT_SUFFIX}"
    assert dest.exists()
    assert not artifact_exists(path)
    assert glob_artifacts(path.parent) == []
    assert gzip.decompress(dest.read_bytes()).decode("utf-8") == _TEXT


def test_quarantine_handles_a_plain_artifact(tmp_path: Path):
    path = _artifact(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(_TEXT, encoding="utf-8")
    dest = quarantine_artifact(path)
    assert dest.name == f"{_HASH}.json{CORRUPT_SUFFIX}"
    assert dest.read_text(encoding="utf-8") == _TEXT
    assert not artifact_exists(path)


def test_quarantine_is_idempotent(tmp_path: Path):
    """A second corrupt artifact at the same stem replaces the first quarantine."""
    path = _artifact(tmp_path)
    write_artifact(path, _TEXT)
    first = quarantine_artifact(path)
    write_artifact(path, '{"v": 2}')
    second = quarantine_artifact(path)
    assert second == first
    assert gzip.decompress(second.read_bytes()).decode("utf-8") == '{"v": 2}'


def test_quarantine_of_a_missing_artifact_is_not_fatal(tmp_path: Path):
    """The caller's next step is to redo the work either way, never to abort."""
    path = _artifact(tmp_path)
    path.parent.mkdir(parents=True)
    assert quarantine_artifact(path).name.endswith(CORRUPT_SUFFIX)
