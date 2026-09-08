"""Spending the official-site overlay: Stage-2 picks decorated onto a drawn sample.

:mod:`g3o.report.site_overlay` harvests what Stage 2 found. This is the other half —
handing those sites back to a later run, so a round spends the discoveries of the rounds
before it. The two are deliberately separate modules: harvesting is a read of finished
artifacts and can never affect a run; spending changes what a run *does*, and every
parameter of it is guarded, hashed and recorded in the manifest.

**The registry is never rewritten.** The map is applied to the sample rows in memory,
after the draw, inside :func:`g3o.run.presweep.planning.plan_run`. The canonical master
is read-only by project rule and stays untouched; so does the frame CSV, which
:mod:`g3o.run.frame.build` requires to carry the master's column layout exactly.

What a decorated row does
-------------------------
``official_site_url`` is not a new mechanism — it is the WS3 round-2 bypass column,
wired end to end since 2026-05-09 and null everywhere until now.
:func:`g3o.run.presweep.records.institution_record` projects it, and
``stage_classify`` then **skips the Stage-2 LLM path entirely** for that institution,
writing ``{"bypassed": true, "source": "master_csv", "url": ...}`` and handing the value
straight to Stage 1b's ``site:`` query. Per Q4 (2026-05-09) no plausibility check is
applied: the runner trusts the value.

That is the whole benefit and the whole risk in one sentence. The benefit is a Stage-2
batch job and its tokens saved per decorated institution, and a site-bound Stage 1b for
an institution that would otherwise have had none. The risk is that a wrong site is
never revisited by any model, on this run or any later one — which is why the two
filters below are on by default and why both are recorded in the manifest.

Two filters, on by default
--------------------------
``min_confidence`` (default ``high``)
    Stage 2 self-rates every pick. On ``r20260829T121145Z-233a``: 6,076 high, 564
    medium, 44 low. Only ``high`` is spent by default. **This is the model's opinion of
    its own work, not a validated instrument** — no hand-adjudicated subset exists for
    that run — so the floor is a policy dial, not a measurement.

``require_unshared_site_host`` (default ``True``)
    A shared domain is not an institution identifier. 1,192 of the 6,684 picks (17.8%)
    sit on a ``site:`` host shared with at least one other institution — 95 councils on
    ``nsw.gov.au``, 45 institutions on ``gov.mt``. Decorating those would make Stage 1b
    issue one identical ``site:`` query for all of them, which is *worse than leaving
    the institution website-free*: the website-free path at least searches the
    institution's own name. Those rows are skipped, and the institution keeps the
    behaviour it would have had anyway.

The value stored is :func:`g3o.common.urlnorm.site_root` — the canonical
``https://host/`` form the module docstring names as "the form to store and to compare
picks on". The URL Stage 2 actually returned, path and all, stays in the overlay, which
is where a human adjudicating a pick will look; Stage 1b discards the path regardless.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from g3o.report.site_overlay import CONFIDENCE_RANK, read_overlay

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_MIN_CONFIDENCE",
    "BypassMap",
    "apply_to_rows",
    "load_bypass_map",
]

#: Ruled 2026-08-30 (PI): ``high`` only. Widening it is a data-quality decision.
DEFAULT_MIN_CONFIDENCE = "high"


class OfficialSitesError(RuntimeError):
    """The overlay could not be used. Refusing beats decorating a sample wrongly."""


@dataclass(frozen=True)
class BypassMap:
    """``institution_uid`` → canonical site root, plus why the rest were left out.

    ``content_hash`` is over the pairs that would actually be spent, not over the
    overlay file: two overlays that differ only in rows this floor excludes are the same
    instrument, and a resume guard that aborted on that difference would be reporting
    noise. It is the value the manifest records and the resume guard compares.
    """

    sites: dict[str, str] = field(default_factory=dict)
    source: str = ""
    min_confidence: str = DEFAULT_MIN_CONFIDENCE
    require_unshared_site_host: bool = True
    overlay_rows: int = 0
    skipped_below_confidence: int = 0
    skipped_shared_site_host: int = 0
    skipped_unparseable: int = 0

    @property
    def content_hash(self) -> str:
        digest = hashlib.sha256()
        for uid in sorted(self.sites):
            digest.update(uid.encode("utf-8"))
            digest.update(b"\x00")
            digest.update(self.sites[uid].encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def manifest_block(self) -> dict[str, Any]:
        """What the run records about the instrument it just changed."""
        return {
            "source": self.source,
            "min_confidence": self.min_confidence,
            "require_unshared_site_host": self.require_unshared_site_host,
            "overlay_rows": self.overlay_rows,
            "eligible_sites": len(self.sites),
            "skipped_below_confidence": self.skipped_below_confidence,
            "skipped_shared_site_host": self.skipped_shared_site_host,
            "skipped_unparseable": self.skipped_unparseable,
            "content_hash": self.content_hash,
        }

    def __len__(self) -> int:
        return len(self.sites)


def load_bypass_map(
    overlay_csv: Path,
    *,
    min_confidence: str = DEFAULT_MIN_CONFIDENCE,
    require_unshared_site_host: bool = True,
) -> BypassMap:
    """Read an overlay and reduce it to the sites this run is allowed to spend.

    Raises :class:`OfficialSitesError` rather than returning an empty map when the file
    is missing or is not an overlay: a silently empty map is a run that quietly did not
    do the thing it was configured to do, which is the failure mode that costs a whole
    round to discover.
    """
    if min_confidence not in CONFIDENCE_RANK:
        raise OfficialSitesError(
            f"unknown confidence floor {min_confidence!r}; "
            f"expected one of {sorted(CONFIDENCE_RANK, key=CONFIDENCE_RANK.get, reverse=True)}"
        )
    if not overlay_csv.is_file():
        raise OfficialSitesError(f"official-sites overlay not found: {overlay_csv}")
    try:
        rows = read_overlay(overlay_csv)
    except ValueError as exc:
        raise OfficialSitesError(str(exc)) from exc

    floor = CONFIDENCE_RANK[min_confidence]
    sites: dict[str, str] = {}
    below = shared = unparseable = 0
    for row in rows:
        uid = (row.get("institution_uid") or "").strip()
        if not uid or uid.startswith("__NOUID__"):
            unparseable += 1
            continue
        if CONFIDENCE_RANK.get((row.get("confidence") or "").strip().lower(), 0) < floor:
            below += 1
            continue
        root = (row.get("site_root") or "").strip()
        if not root:
            unparseable += 1
            continue
        if require_unshared_site_host and _int(row.get("site_host_share_count")) > 1:
            shared += 1
            continue
        sites[uid] = root

    bypass = BypassMap(
        sites=sites,
        source=str(overlay_csv),
        min_confidence=min_confidence,
        require_unshared_site_host=require_unshared_site_host,
        overlay_rows=len(rows),
        skipped_below_confidence=below,
        skipped_shared_site_host=shared,
        skipped_unparseable=unparseable,
    )
    logger.info(
        "official sites: %d of %d overlay rows eligible "
        "(floor=%s, unshared-only=%s; skipped %d below floor, %d on a shared host, %d unusable)",
        len(sites), len(rows), min_confidence, require_unshared_site_host,
        below, shared, unparseable,
    )
    return bypass


def _int(value: Any) -> int:
    try:
        return int(str(value).strip() or 0)
    except ValueError:
        return 0


def apply_to_rows(rows: Iterable[dict[str, Any]], bypass: BypassMap) -> int:
    """Decorate ``rows`` in place with ``official_site_url``; return how many.

    **A row that already carries a non-empty ``official_site_url`` is left alone.** The
    column is the master's to own if it ever holds one; the overlay fills a gap, it does
    not overwrite a value someone put there deliberately.

    ``official_site_confidence`` is set alongside, so the bypass envelope's provenance
    survives into the run without a join back to the overlay.
    """
    applied = 0
    for row in rows:
        if (row.get("official_site_url") or "").strip():
            continue
        uid = (row.get("institution_uid") or "").strip()
        site = bypass.sites.get(uid)
        if not site:
            continue
        row["official_site_url"] = site
        row["official_site_confidence"] = bypass.min_confidence
        applied += 1
    return applied
