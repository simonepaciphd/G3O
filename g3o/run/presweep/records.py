"""Per-row projection + small pure helpers (ids, timestamps, URL keys)."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


def synth_institution_id(row: dict[str, Any]) -> str:
    """Stable institution_id derived from ``master_row_id``."""
    raw = row.get("master_row_id", "")
    try:
        return f"INST-{int(raw):07d}"
    except (TypeError, ValueError):
        return f"INST-{raw}"


def institution_record(row: dict[str, Any]) -> dict[str, Any]:
    """Project a master CSV row into the institution-row shape Stages 2/3/5 expect.

    ``official_site_url`` (and the optional ``official_site_confidence``) is the
    Stage 2 bypass column owned by WS3 round-2 (spec §6 master-schema dependency,
    2026-05-09). Pre-rollout the column is missing and the projection records
    ``None``; the runner's bypass guard treats ``None`` as "Stage 2 LLM path runs
    as before."
    """
    return {
        "institution_id": synth_institution_id(row),
        "institution_name": row.get("institution_name", ""),
        "country": row.get("country", ""),
        "branch_of_government": row.get("branch", ""),
        "level_of_government": row.get("government_level", ""),
        "institution_type": row.get("institution_type", ""),
        "website": row.get("website") or None,
        "official_site_url": row.get("official_site_url") or None,
        "official_site_confidence": row.get("official_site_confidence") or None,
        "master_row_id": row.get("master_row_id", ""),
    }


def _read_master(path: Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        yield from csv.DictReader(f)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _dedupe_key(url: str) -> str:
    """Path-aware dedup key for the Stage 1a + 1b URL union (Q3=c, 2026-05-09).

    Folds scheme/netloc casing, drops a leading ``www.``, strips a trailing slash
    from non-root paths, and removes the fragment. Query string and ``;params``
    are left intact (Q3=c rejected aggressive query-param normalization).
    Falls back to the raw URL if parsing fails.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path
    if path.endswith("/"):
        path = path[:-1]  # strip uniformly; root "/" → "" for consistency
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def _site_domain(url: str) -> str | None:
    """Domain extractor for ``site:`` query construction. ``None`` if unparseable."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    netloc = parsed.netloc.lower().removeprefix("www.")
    return netloc or None
