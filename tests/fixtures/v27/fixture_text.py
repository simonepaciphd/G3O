"""Deterministic page-text assembly for the v2.7 (T-040) synthetic fixtures.

A synthetic page carries either ``text`` or ``text_parts``. ``text_parts`` is a list of
``{"text": "..."}`` and ``{"filler_tokens": N}`` items; filler is neutral municipal prose
with no AI content, sized at about 4 characters per token, so a long-page fixture exceeds
the 32k-token chunk threshold (C-004) without storing the filler in git.

Real-page fixtures carry no text: they point at a stored scrape record by path and hash,
and ``load_real_text`` resolves and verifies it.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

DRIVE_ENV = "G3O_DRIVE_ROOT"


def drive_root() -> Path:
    """The G3O Drive root (holds agent-workspace/), read from the G3O_DRIVE_ROOT setting.

    Real-page stores are referenced relative to this root, so no machine path lives in git.
    Raises RuntimeError with a clear message when the setting is unset or does not exist.
    """
    v = os.environ.get(DRIVE_ENV)
    if not v:
        raise RuntimeError(
            f"{DRIVE_ENV} is not set: point it at the G3O Drive root (the folder holding agent-workspace/)"
        )
    p = Path(v)
    if not (p / "agent-workspace").is_dir():
        raise RuntimeError(f"{DRIVE_ENV}={v} has no agent-workspace/ folder")
    return p


CHARS_PER_TOKEN = 4

_FILLER = (
    "The committee noted the minutes of the previous meeting and approved them as a correct record. "
    "Members discussed the maintenance schedule for the community hall, the resurfacing of the car park "
    "and the timetable for the summer litter collection. The clerk reported on correspondence received "
    "about street lighting, hedge cutting along the footpath and the allotment waiting list. "
    "The finance report for the quarter was received; payments listed in the schedule were approved. "
)


def label_key(fixture_id: str, k: int, expected: dict) -> str:
    """Key of one expected value: <fixture_id>#<index>, plus @v<n> once a label is relabelled (n >= 2)."""
    v = expected.get("label_version", 1)
    return f"{fixture_id}#{k}" + (f"@v{v}" if v > 1 else "")


def filler(tokens: int, seed: int = 0) -> str:
    """Return about ``tokens`` tokens of neutral prose, numbered so no two paragraphs repeat."""
    target = tokens * CHARS_PER_TOKEN
    out, n = [], seed * 100000
    size = 0
    while size < target:
        para = f"Item {n}. " + _FILLER
        out.append(para)
        size += len(para) + 2
        n += 1
    return "\n\n".join(out)


def page_text(page: dict) -> str:
    """Assemble a synthetic page's main text."""
    if "text" in page:
        return page["text"]
    chunks = []
    for i, part in enumerate(page["text_parts"]):
        if "text" in part:
            chunks.append(part["text"])
        else:
            chunks.append(filler(part["filler_tokens"], seed=part.get("seed", i)))
    return "\n\n".join(chunks)


def load_real_text(ref: dict, drive_root: str | Path) -> str:
    """Resolve a real-page fixture's text from its stored record and verify the text hash.

    ``ref`` is a fixture's ``page_ref``: ``store`` (path relative to the G3O Drive root),
    ``line_1based`` and ``text_sha256``. Raises ValueError on a hash mismatch.
    """
    path = Path(drive_root) / ref["store"]
    if (
        "member" in ref
    ):  # stored scrape inside a pulled tar (RS-009); read in memory, never extracted
        import gzip
        import tarfile

        with tarfile.open(path) as tf:
            raw = tf.extractfile(ref["member"]).read()
        if hashlib.sha256(raw).hexdigest() != ref["member_sha256"]:
            raise ValueError(f"member hash mismatch for {ref['member']}")
        data = gzip.decompress(raw) if ref["member"].endswith(".gz") else raw
        text = json.loads(data.decode("utf-8", errors="replace")).get("text") or ""
    else:
        lines = path.read_text(encoding="utf-8").split("\n")
        rec = json.loads(lines[ref["line_1based"] - 1])
        text = rec["source_record"]["text"]
    got = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if got != ref["text_sha256"]:
        raise ValueError(f"text hash mismatch for {ref.get('page_id')}: {got}")
    return text
