"""Evaluation sampling frame: which master rows a measured run may sample from.

`presweep --master-csv` samples from whatever CSV it is handed. This module
builds that CSV from the read-only institution master, so the frame every
measured rate is computed against is reproducible rather than re-derived by
hand each session.

A row is eligible when it is not a duplicate and carries a website that could
plausibly be an institution's own site: at least `MIN_WEBSITE_LEN` characters,
parsing to a host with a dot, and free of the placeholder and aggregator
markers below.

`n/a` is matched as a **delimited token**, not a bare substring (PI sign-off,
2026-08-02). The bare-substring rule silently dropped four real institutions
whose URL *paths* contain the letters `n/a` across a segment boundary —
`.../en/about-us/...`, `.../en/anti-money-laundering-office`,
`.../tracfin/accueil-tracfin`, `.../en/about-asf`. `tbd` and `none` were
checked against the full master at the same time and have no such collisions,
so they stay substring matches.
"""

from __future__ import annotations

import csv
import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MIN_WEBSITE_LEN = 5

# Aggregator and reference hosts: never an institution's own site.
JUNK_DOMAINS = ("data.ipu.org", "wikipedia.org", "wikimedia.org")

# Placeholder markers safe to match anywhere in the value.
JUNK_MARKERS = ("tbd", "none")

# `n/a` only counts when it is not glued to surrounding alphanumerics.
NA_MARKER_RE = re.compile(r"(?<![a-z0-9])n/a(?![a-z0-9])")


def website_host(website: str) -> str | None:
    """Return the host of `website`, or None if it does not parse to one."""
    candidate = website if "//" in website else f"//{website}"
    try:
        host = urlparse(candidate).hostname
    except ValueError:
        return None
    return host if host and "." in host else None


def is_placeholder(website: str) -> bool:
    """True when the website value is a placeholder or an aggregator host."""
    value = website.lower()
    if any(domain in value for domain in JUNK_DOMAINS):
        return True
    if any(marker in value for marker in JUNK_MARKERS):
        return True
    return bool(NA_MARKER_RE.search(value))


def is_eligible(row: dict[str, Any]) -> bool:
    """True when `row` belongs in the evaluation frame."""
    if (row.get("duplicate") or "").strip() == "1":
        return False
    website = (row.get("website") or "").strip()
    if len(website) < MIN_WEBSITE_LEN:
        return False
    if website_host(website) is None:
        return False
    return not is_placeholder(website)


def filter_master(rows: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield the eligible rows of `rows`, in input order."""
    return (row for row in rows if is_eligible(row))


def build(master_csv: Path, out_csv: Path) -> int:
    """Write the evaluation frame of `master_csv` to `out_csv`; return its size."""
    with open(master_csv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        kept = list(filter_master(reader))
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)
    return len(kept)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m g3o.run.presweep.eval_frame <master_csv> <out_csv>")
        return 2
    n = build(Path(argv[0]), Path(argv[1]))
    print(f"eval frame rows: {n:,} -> {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
