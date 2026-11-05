"""R-015 readability check on extracted page text (F4 c; RC-D-018 "1 c"; T-065).

A page whose stored text is unreadable is set ``not_assessable`` with a
readability failure reason. As ruled, the text is unreadable when it carries a
binary-content marker, or when fewer than 10% of its non-whitespace characters
are letters (any script). The markers and the letter share are the
measures of ``scripts/spikes/f4/readability.py`` (the evidence the cut was set
on), reproduced here so the production check and the spike agree; the
test module pins that agreement.

The check reads text only. It applies equally to a page just fetched and to a
page stored before T-065 (no fetched bytes are kept anywhere, RC-D-018 droplet
finding, so the ~287 stored binary-as-text pages are caught here; DP-065b).
It sets nothing itself: the caller that writes the page verdict records the
reason. Empty text is not a readability failure; the empty-page floor
(``g3o.extract.batch.is_near_empty``) owns it.
"""

from __future__ import annotations

import re
import unicodedata

#: RC-D-018 "1 c": unreadable when letters are < 10% of non-whitespace chars.
LETTER_SHARE_CUT = 0.10

REASON_BINARY_MARKER = "binary_marker"
REASON_LOW_LETTER_SHARE = "low_letter_share"

_HEAD_CHARS = 1024
_PDF_OBJECT_SCAN_CHARS = 200_000
_PDF_OBJECT_MIN_TOKENS = 3
_PDF_OBJ = re.compile(r"\b(?:\d+ \d+ obj|endobj|endstream|stream)\b")
_IMAGE = ("\x89PNG", "JFIF", "Exif\x00", "GIF87a", "GIF89a")


def binary_markers(text: str) -> list[str]:
    """Binary-content markers found in ``text``, in a fixed order.

    ``pdf_header`` (``%PDF-`` in the first 1024 chars), ``pdf_objects`` (at
    least 3 PDF object tokens in the first 200,000 chars), ``zip``
    (``PK\\x03\\x04`` in the first 1024 chars), ``null`` (U+0000 anywhere),
    ``image`` (PNG, JFIF/Exif or GIF magic in the first 1024 chars).
    """
    head = text[:_HEAD_CHARS]
    out: list[str] = []
    if "%PDF-" in head:
        out.append("pdf_header")
    if len(_PDF_OBJ.findall(text[:_PDF_OBJECT_SCAN_CHARS])) >= _PDF_OBJECT_MIN_TOKENS:
        out.append("pdf_objects")
    if "PK\x03\x04" in head:
        out.append("zip")
    if "\x00" in text:
        out.append("null")
    if any(m in head for m in _IMAGE):
        out.append("image")
    return out


def letter_share(text: str) -> float | None:
    """Letters or combining marks (Unicode L*, M*) / non-whitespace characters.

    ``None`` when the text has no non-whitespace character.
    """
    letters = nonspace = 0
    for ch in text:
        if not ch.isspace():
            nonspace += 1
            if unicodedata.category(ch)[0] in "LM":
                letters += 1
    return None if nonspace == 0 else letters / nonspace


def readability_failure(text: str) -> str | None:
    """The R-015 readability failure reason for ``text``, or ``None`` if readable.

    Returns ``"binary_marker:<m1>,<m2>"`` (markers as in :func:`binary_markers`)
    when any marker is present, else ``"low_letter_share"`` when the letter
    share is below :data:`LETTER_SHARE_CUT`. Empty or whitespace-only text
    returns ``None`` (not a readability case).
    """
    if not text.strip():
        return None
    markers = binary_markers(text)
    if markers:
        return f"{REASON_BINARY_MARKER}:{','.join(markers)}"
    share = letter_share(text)
    if share is not None and share < LETTER_SHARE_CUT:
        return REASON_LOW_LETTER_SHARE
    return None
