"""The stored per-page text artifact (v2.7, T-014/T-020; PI ruling A5.1 a, 2026-11-11).

One new text file per coded page holds the page's main text, a fixed
separator, then the page's chrome. ``page_content_sha256`` (D-007) is the
SHA256 of the whole file's bytes. The segment layout that
:meth:`g3o.persist.stage6_adapters.PageArtifact.verify` checks is:

- each part ``chunk_id`` (``{page_id}#p{nnn}``) -> ``(chunk.start, chunk.end)``:
  the main text opens the file at offset 0, so a part's span in the artifact
  is its span in the page text (``Chunk.text == page_text[start:end]``);
- ``{page_id}#chrome`` -> ``(len(main) + len(CHROME_SEPARATOR), len(file text))``.

Offsets are Python ``str`` (code point) offsets into the decoded file text,
which is how every reader in the pipeline uses them
(``path.read_bytes().decode("utf-8")``).

Pinned layout (:data:`PAGE_ARTIFACT_FORMAT`):

- **Encoding.** UTF-8, strict, no BOM. A text that cannot be encoded (a lone
  surrogate) is refused, never replaced.
- **Newlines.** The bytes are ``text.encode("utf-8")`` written in binary
  mode: no platform newline translation and no normalisation. A ``\\r\\n``,
  ``\\r`` or ``\\n`` in the page text is stored exactly as it was consumed, so
  the hash depends on the consumed text only, never on the writing platform.
- **Chrome.** The chrome segment is the chrome text the support check sees
  (:func:`g3o.classify.jev_page_code.contact_text`: stored ``chrome_text``
  verbatim, then the stored e-mails, PI 2026-11-07 item 1a). Not measured
  (``None``): the file is the main text alone, with no separator and no
  ``#chrome`` segment. Measured but empty (``""``): main text, separator, and
  an empty ``#chrome`` segment at the end of the file. The two cases are
  distinct files with distinct hashes.
- **Location.** ``<institution_dir>/page_artifact_v27/<url_hash(url)>.txt``,
  stored in ``6_storage.json`` as a POSIX path relative to the run directory
  (the same per-page key as ``stage_page_code.artifact_path``).
- **Writes.** Atomic (:func:`g3o.persist.stage6_adapters.write_atomic`). A
  re-run that would write identical bytes leaves the file as it is (resume);
  different bytes at the same path are refused (:class:`PageArtifactConflict`),
  never overwritten.
- **Known ambiguity (accepted; PI ruling 9 on the build questions,
  2026-11-11).** A main text that itself ends with :data:`CHROME_SEPARATOR`
  and has no measured chrome writes the same bytes, and so the same
  ``page_content_sha256``, as the main text without it plus measured, empty
  chrome. The segments still tell them apart (no ``#chrome`` segment vs an
  empty one at the end of the file). The case is theoretical: the separator
  is a fixed marker string no scraped page is expected to end with. It is
  documented here and pinned by a test, not escaped.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from g3o.common.paths import institution_dir
from g3o.extract.batch import url_hash
from g3o.persist.stage6_adapters import write_atomic

PAGE_ARTIFACT_FORMAT = "g3o-page-artifact-v1"
PAGE_ARTIFACT_DIR = "page_artifact_v27"
PAGE_ARTIFACT_SUFFIX = ".txt"
PAGE_ARTIFACT_ENCODING = "utf-8"
#: Between the main text and the chrome; ASCII, so its UTF-8 bytes equal its characters.
CHROME_SEPARATOR = "\n\n----- g3o-page-artifact-v1 chrome -----\n\n"
CHROME_SUFFIX = "#chrome"


class PageArtifactConflict(ValueError):
    """A stored page artifact differs from the one this run would write; it is never overwritten."""


@dataclass(frozen=True)
class StoredPageArtifact:
    path: str  # POSIX, relative to the run directory
    text: str  # the decoded file text
    segments: Mapping[str, tuple[int, int]]
    sha256: str  # of the file's bytes
    chrome_measured: bool
    written: bool  # False when an identical file was already there


def chrome_id(page_id: str) -> str:
    return f"{page_id}{CHROME_SUFFIX}"


def page_artifact_relpath(institution_id: str, url: str) -> str:
    rel = institution_dir(Path(), institution_id) / PAGE_ARTIFACT_DIR / f"{url_hash(url)}{PAGE_ARTIFACT_SUFFIX}"
    return rel.as_posix()


def build_page_artifact(page_id: str, main_text: str, chunks: Sequence[Any],
                        chrome_text: str | None) -> tuple[str, dict[str, tuple[int, int]]]:
    """The artifact text and its segments; refuses parts that are not spans of ``main_text``."""
    if not isinstance(main_text, str) or (chrome_text is not None and not isinstance(chrome_text, str)):
        raise TypeError("page artifact texts must be str (chrome may be None: not measured)")
    segments: dict[str, tuple[int, int]] = {}
    for c in chunks:
        if c.page_id != page_id:
            raise ValueError(f"part {c.chunk_id!r} belongs to page {c.page_id!r}, not {page_id!r}")
        if c.chunk_id in segments or c.chunk_id == chrome_id(page_id):
            raise ValueError(f"duplicate or reserved part id {c.chunk_id!r}")
        if not (type(c.start) is int and type(c.end) is int and 0 <= c.start <= c.end <= len(main_text)) \
                or main_text[c.start:c.end] != c.text:
            raise ValueError(f"part {c.chunk_id!r} is not the page text at [{c.start}:{c.end}]")
        segments[c.chunk_id] = (c.start, c.end)
    if chrome_text is None:
        return main_text, segments
    text = main_text + CHROME_SEPARATOR + chrome_text
    segments[chrome_id(page_id)] = (len(main_text) + len(CHROME_SEPARATOR), len(text))
    return text, segments


def encode_page_artifact(text: str) -> bytes:
    return text.encode(PAGE_ARTIFACT_ENCODING)  # strict: a lone surrogate raises


def write_page_artifact(run_dir: Path, *, institution_id: str, url: str, page_id: str, main_text: str,
                        chunks: Sequence[Any], chrome_text: str | None) -> StoredPageArtifact:
    """Write (or, on resume, find identical) the page's artifact and return its layout and hash."""
    text, segments = build_page_artifact(page_id, main_text, chunks, chrome_text)
    data = encode_page_artifact(text)
    rel = page_artifact_relpath(institution_id, url)
    path = Path(run_dir) / rel
    written = False
    if path.exists():
        if path.read_bytes() != data:
            raise PageArtifactConflict(f"stored page artifact {rel} differs from page {page_id}'s text")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, data)
        written = True
    return StoredPageArtifact(rel, text, segments, hashlib.sha256(data).hexdigest(), chrome_text is not None,
                              written)


__all__ = [
    "CHROME_SEPARATOR", "PAGE_ARTIFACT_DIR", "PAGE_ARTIFACT_ENCODING", "PAGE_ARTIFACT_FORMAT",
    "PAGE_ARTIFACT_SUFFIX", "PageArtifactConflict", "StoredPageArtifact", "build_page_artifact", "chrome_id",
    "encode_page_artifact", "page_artifact_relpath", "write_page_artifact",
]
