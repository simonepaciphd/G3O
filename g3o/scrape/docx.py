"""DOCX text extraction, standard library only (T-065, DP-065a).

A DOCX file is a ZIP (OOXML) package whose body is ``word/document.xml``.
This module reads that one part with :mod:`zipfile` and
:mod:`xml.etree.ElementTree`: no new dependency, no network.

Scope (T-065 card): the main document text only. Headers, footers, footnotes,
comments and deleted tracked-change text (``w:delText``) are not read.
Paragraphs (body and table cells alike) become lines; ``w:tab`` becomes a tab
and ``w:br`` / ``w:cr`` a line break, so the result reads like the PDF path's
plain text.

Defensive limits, because the bytes come from the open web: the decompressed
part is capped at :data:`MAX_XML_BYTES`, and a part carrying a DTD
(``<!DOCTYPE``, never present in a real DOCX) is refused rather than parsed,
which closes entity-expansion inputs. Every failure returns ``""`` with a
warning, like ``g3o.scrape.pdf.extract_text``.
"""

from __future__ import annotations

import io
import logging
import xml.etree.ElementTree as ET
import zipfile

logger = logging.getLogger(__name__)

DOCUMENT_PART = "word/document.xml"
CORE_PROPS_PART = "docProps/core.xml"

#: Ceiling on one decompressed XML part. The response body is already capped
#: at 32 MB compressed (``fetcher.MAX_RESPONSE_BYTES``); this bounds what a
#: high-ratio deflate stream can inflate to in memory.
MAX_XML_BYTES = 64 * 1024 * 1024

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_DC_TITLE ="{http://purl.org/dc/elements/1.1/}title"


def is_docx(content: bytes) -> bool:
    """True when ``content`` is a ZIP package holding ``word/document.xml``.

    The ZIP local-file signature ``PK\\x03\\x04`` is checked first, so HTML and
    other bodies cost one prefix comparison. Other OOXML packages (XLSX, PPTX)
    and plain ZIPs are not DOCX and return False.
    """
    if not content.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return DOCUMENT_PART in zf.namelist()
    except (zipfile.BadZipFile, ValueError, OSError):
        return False


def _read_part(zf: zipfile.ZipFile, name: str) -> bytes | None:
    with zf.open(name) as fh:
        data = fh.read(MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        logger.warning("DOCX part %s exceeds %d bytes; not read", name, MAX_XML_BYTES)
        return None
    if b"<!DOCTYPE" in data[:4096] or b"<!ENTITY" in data:
        logger.warning("DOCX part %s carries a DTD; not parsed", name)
        return None
    return data


def _collect(el: ET.Element, lines: list[str], buf: list[str] | None) -> None:
    """Append one line per ``w:p`` to ``lines``, in document order.

    A paragraph nested inside another (a text box) becomes its own line rather
    than being read twice; ``mc:Fallback`` (the legacy copy of the same text
    box) is skipped for the same reason.
    """
    for child in el:
        tag = child.tag
        if tag == f"{_MC}Fallback":
            continue
        if tag == f"{_W}p":
            own: list[str] = []
            lines.append("")
            idx = len(lines) - 1
            _collect(child, lines, own)
            lines[idx] = "".join(own).rstrip()
            continue
        if buf is not None:
            if tag == f"{_W}t":
                buf.append(child.text or "")
            elif tag == f"{_W}tab":
                buf.append("\t")
            elif tag in (f"{_W}br", f"{_W}cr"):
                buf.append("\n")
        _collect(child, lines, buf)


def extract_text(content: bytes) -> str:
    """Return the text of ``word/document.xml``, one line per paragraph.

    Returns ``""`` when the package or the part cannot be read. Empty
    paragraphs are kept as empty lines and trailing whitespace is stripped.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            data = _read_part(zf, DOCUMENT_PART)
        if data is None:
            return ""
        lines: list[str] = []
        _collect(ET.fromstring(data), lines, None)
    except (
        zipfile.BadZipFile, KeyError, ValueError, OSError, ET.ParseError, RecursionError,
    ) as exc:
        logger.warning("DOCX extraction error: %s", exc)
        return ""
    return "\n".join(lines).strip()


def extract_title(content: bytes) -> str:
    """Best-effort title from ``docProps/core.xml`` (``dc:title``); else ``""``."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            if CORE_PROPS_PART not in zf.namelist():
                return ""
            data = _read_part(zf, CORE_PROPS_PART)
        if data is None:
            return ""
        el = ET.fromstring(data).find(_DC_TITLE)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError, ET.ParseError):
        return ""
    return (el.text or "").strip() if el is not None else ""
