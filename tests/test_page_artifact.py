"""The stored per-page text artifact (PI ruling A5.1 a): layout, hash, chrome states, resume (offline)."""
from __future__ import annotations

import hashlib

import pytest

from g3o.common.instrument import sha256_text
from g3o.common.page_chunks import Chunk, chunk_page
from g3o.common.paths import institution_dir
from g3o.common.support_check import PageSources
from g3o.extract.batch import url_hash
from g3o.persist import page_artifact as pa
from g3o.persist.stage6_adapters import PageArtifact

INST, URL, PID = "INST-0000001", "https://a.example.gov/page", "pg1"
MAIN = "First paragraph about the council.\n\nSecond paragraph: a chatbot pilot.\n\nThird one."


def _chunks(text):
    return chunk_page(PID, text, limit_tokens=12)  # small budget: several parts


def _write(run_dir, text=MAIN, chrome="Header\nFooter"):
    return pa.write_page_artifact(run_dir, institution_id=INST, url=URL, page_id=PID, main_text=text,
                                  chunks=_chunks(text), chrome_text=chrome)


def _verify(run_dir, stored, text, chrome):
    disk = (run_dir / stored.path).read_bytes().decode("utf-8")
    sources = PageSources(PID, {c.chunk_id: c.text for c in _chunks(text)}, chrome)
    PageArtifact("S1", stored.path, disk, dict(stored.segments)).verify(sources)
    return disk


def test_pinned_constants():
    assert pa.PAGE_ARTIFACT_FORMAT == "g3o-page-artifact-v1"
    assert pa.PAGE_ARTIFACT_ENCODING == "utf-8"
    assert pa.CHROME_SEPARATOR == "\n\n----- g3o-page-artifact-v1 chrome -----\n\n"
    assert pa.CHROME_SEPARATOR.isascii()


def test_layout_offsets_round_trip_and_verify(tmp_path):
    chunks = _chunks(MAIN)
    assert len(chunks) > 1
    stored = _write(tmp_path)
    disk = _verify(tmp_path, stored, MAIN, "Header\nFooter")
    assert disk == MAIN + pa.CHROME_SEPARATOR + "Header\nFooter"
    for c in chunks:
        assert stored.segments[c.chunk_id] == (c.start, c.end) and disk[c.start:c.end] == c.text
    start, end = stored.segments[f"{PID}#chrome"]
    assert disk[start:end] == "Header\nFooter" and end == len(disk)
    assert disk[len(MAIN):start] == pa.CHROME_SEPARATOR


def test_location_follows_the_per_page_key(tmp_path):
    stored = _write(tmp_path)
    expected = institution_dir(tmp_path, INST) / pa.PAGE_ARTIFACT_DIR / f"{url_hash(URL)}.txt"
    assert (tmp_path / stored.path).resolve() == expected.resolve()
    assert "\\" not in stored.path and not stored.path.startswith("/")


def test_hash_covers_the_whole_file_bytes(tmp_path):
    stored = _write(tmp_path)
    data = (tmp_path / stored.path).read_bytes()
    assert stored.sha256 == hashlib.sha256(data).hexdigest() == sha256_text(data.decode("utf-8"))
    assert not data.startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_bytes_and_hash_follow_the_consumed_text_on_any_platform(tmp_path, newline):
    text = MAIN.replace("\n", newline)
    chrome = f"Header{newline}Footer"
    stored = _write(tmp_path, text, chrome)
    data = (tmp_path / stored.path).read_bytes()
    assert data == (text + pa.CHROME_SEPARATOR + chrome).encode("utf-8")  # no translation either way
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    _verify(tmp_path, stored, text, chrome)  # offsets survive \r\n (no universal-newline read)


def test_newline_styles_give_distinct_stable_hashes(tmp_path):
    lf = _write(tmp_path / "a", MAIN).sha256
    crlf = _write(tmp_path / "b", MAIN.replace("\n", "\r\n")).sha256
    assert lf != crlf  # the hash is of the consumed text, not a normalised one
    assert _write(tmp_path / "c", MAIN).sha256 == lf


def test_chrome_not_measured_vs_measured_empty(tmp_path):
    none = _write(tmp_path / "none", chrome=None)
    empty = _write(tmp_path / "empty", chrome="")
    assert (tmp_path / "none" / none.path).read_bytes() == MAIN.encode("utf-8")
    assert f"{PID}#chrome" not in none.segments and not none.chrome_measured
    assert (tmp_path / "empty" / empty.path).read_bytes() == (MAIN + pa.CHROME_SEPARATOR).encode("utf-8")
    assert empty.segments[f"{PID}#chrome"] == (len(MAIN) + len(pa.CHROME_SEPARATOR),) * 2 and empty.chrome_measured
    assert none.sha256 != empty.sha256
    _verify(tmp_path / "none", none, MAIN, None)
    _verify(tmp_path / "empty", empty, MAIN, "")
    with pytest.raises(ValueError, match="not located"):
        PageArtifact("S1", none.path, MAIN, dict(none.segments)).span(f"{PID}#chrome")


def test_non_ascii_offsets_are_code_points(tmp_path):
    text = "Città di Roma — intelligenza artificiale.\n\nКиев 東京 ✓ chatbot."
    stored = _write(tmp_path, text, "Pié di pagina")
    _verify(tmp_path, stored, text, "Pié di pagina")


def test_resume_identical_artifact_is_not_rewritten(tmp_path):
    first = _write(tmp_path)
    path = tmp_path / first.path
    before = path.stat().st_mtime_ns
    again = _write(tmp_path)
    assert first.written and not again.written
    assert again == pa.StoredPageArtifact(first.path, first.text, first.segments, first.sha256, True, False)
    assert path.stat().st_mtime_ns == before
    assert not path.with_name(path.name + ".tmp").exists()


def test_a_different_artifact_at_the_same_path_is_refused(tmp_path):
    first = _write(tmp_path)
    with pytest.raises(pa.PageArtifactConflict):
        _write(tmp_path, chrome="Another footer")
    assert (tmp_path / first.path).read_bytes() == first.text.encode("utf-8")


def test_parts_that_are_not_page_spans_are_refused():
    good = _chunks(MAIN)
    bad = [Chunk(good[0].chunk_id, PID, 0, 5, "WRONG", 1)]
    with pytest.raises(ValueError, match="is not the page text"):
        pa.build_page_artifact(PID, MAIN, bad, None)
    with pytest.raises(ValueError, match="belongs to page"):
        pa.build_page_artifact("other", MAIN, good, None)
    with pytest.raises(ValueError, match="duplicate"):
        pa.build_page_artifact(PID, MAIN, [good[0], good[0]], None)


def test_unencodable_text_is_refused(tmp_path):
    with pytest.raises(UnicodeEncodeError):
        _write(tmp_path, "bad \ud800 surrogate", None)
