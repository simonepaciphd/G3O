"""Per-row projection + small pure helpers (ids, timestamps, URL keys)."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from g3o.common.urlnorm import site_host


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

    ``disambiguation`` is here by PI ruling (`G3O ADJ`, 2026-08-31, ruling 2:
    *"``duplicate = 1`` stays in quota-bearing strata AND ``disambiguation`` is
    passed to Stage 2"*), and it closes a gap that was measured rather than
    argued. The master carries the column on **100% of the 718 name-collided
    rows** in the 15k frame, and this projection dropped it, so the *query* was
    disambiguated (``stage_discovery`` reads the raw row) and the *classifier*
    was not — while ``g3o.classify.official_site``'s system prompt already tells
    the model it will receive *"any known aliases or domain hints"*. The prompt
    advertised a slot the projection never filled, and the cost of the empty
    slot is `G3O ADJ`'s 58.3% collided-pick error.

    **This dict is model input, not telemetry**, and that has two consequences
    worth stating where the change is:

    * It is serialised to ``institution.json`` and embedded verbatim in the
      Stage 2/3/5/6 user messages, so the key reaches all four stages, not only
      the Stage 2 the ruling names. Stage 3/5/6 prompts do not advertise it; an
      extra, accurate key is additional context there rather than a
      re-specification, but it *is* a change to their input and is recorded as
      such (Stage 7 closeout, decision 2a).
    * The key is present on every row, ``None`` when the master cell is blank or
      the column absent, matching ``website`` and ``official_site_url``. That
      keeps ``institution.json`` one fixed key set — the property Stage 6 audited
      the 15k run against — at the price of changing the prompt for every
      institution rather than only for collided ones. The reproducibility
      goldens (``tests/goldens/reproducibility.json``) move accordingly, which is
      the intended signal, not a nuisance.
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
        "disambiguation": row.get("disambiguation") or None,
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
    """Domain extractor for ``site:`` query construction. ``None`` if unparseable.

    Delegates to :func:`g3o.common.urlnorm.site_host` so that Stage 1b's
    ``site:`` domain and the Stage 2 official-site root are derived from one
    definition and cannot drift apart.
    """
    return site_host(url)
