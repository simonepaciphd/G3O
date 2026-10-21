"""Official sites against the master — the join every run refreshes, and the fold proposal.

:mod:`g3o.report.site_overlay` harvests what Stage 2 found; :mod:`g3o.run.presweep.
official_sites` spends it on a later run's drawn sample, in memory. Neither says what
the overlay would do to the *registry*. This module does, in two products with two very
different audiences (PI rulings 2026-10-21, D1 b / D2 a / D5 a / D6 a; file contract in
``agent-workspace/2026-10-21-site-import/FOLD-CONTRACT.md``):

``master_with_official_sites.csv`` + ``report.json`` + ``conflicts.csv``
    Step (a), refreshed by ``orchestrate e2e`` after every harvest. The master, every
    column passed through verbatim and in order — including any trailing columns a
    folded master carries (``website_source``, ``website_fold_id``, …) — with seven
    ``official_site_*`` columns appended. Derived and advisory: nothing reads it, it
    is how a human sees what the overlay says about the master *today*.

``proposal.csv`` + ``proposal.json``
    The wave-close step, run by hand and **never by the chain**. One row per action a
    fold would take: ``fill`` where the master's ``website`` is empty, ``replace``
    where it is not and :func:`g3o.common.urlnorm.site_host` disagrees. Same-host picks
    produce no row — they would change nothing. The proposal is inert until the PI
    signs an ``approval.json`` naming its sha256; ``build_master.py`` applies it, and
    refuses a proposal that has no valid approval.

**Eligibility is not reimplemented here.** It is exactly
:func:`~g3o.run.presweep.official_sites.load_bypass_map` with its defaults (ruling
D2 a): ``high`` confidence, unshared ``site:`` host, a parseable root, a real
``institution_uid``. A pick the presweep would not spend is a pick the master is not
offered — one rule, one implementation, one ``content_hash`` recorded on both sides.

**Two definitions of "empty", on purpose.** The join's ``official_site_vs_master``
calls a master website ``master_empty`` when ``site_host`` cannot parse it — the
question there is "does the master give Stage 1b a host?". The proposal's ``fill`` is
stricter: the cell must be blank, because the fold applies a fill only to a blank cell
and anything else would arrive stale. On the 2026-10-21 master that moves 136 rows
(135 ``TBD`` placeholders and one ``http:///www.…``) from fill to replace — where they
need the PI's explicit approval rather than riding on ``approve_fill``.

**Deterministic.** ``proposal.csv`` is a pure function of (master, overlay): sorted by
``institution_uid``, ``\\n`` line endings, the csv module's default quoting, no clock or
path in a row. Its sha256 is what an approval binds to, so the same inputs must give
the same bytes. ``proposal.json`` carries ``created_at`` and is not hashed.

Read-only on its inputs; every output is written to a temporary name and renamed, so a
reader of the e2e copy never sees a half-written file.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.common.urlnorm import site_host
from g3o.report.site_overlay import CONFIDENCE_RANK, read_overlay
from g3o.run.presweep.official_sites import load_bypass_map

logger = logging.getLogger(__name__)

__all__ = [
    "CONFLICT_COLUMNS",
    "FOLD_ID_PATTERN",
    "JOIN_COLUMNS",
    "PROPOSAL_COLUMNS",
    "PROPOSAL_FORMAT",
    "MasterSitesError",
    "MasterSitesResult",
    "build_master_sites",
]

#: Appended to the master's own columns, in this order.
JOIN_COLUMNS: tuple[str, ...] = (
    "official_site_url",
    "official_site_status",
    "official_site_confidence",
    "official_site_vs_master",
    "official_site_run_id",
    "official_site_git_sha",
    "official_site_stage2_model",
)

#: ``conflicts.csv`` — the eligible picks whose host differs from the master's.
CONFLICT_COLUMNS: tuple[str, ...] = (
    "institution_uid",
    "country_iso3",
    "government_level",
    "institution_type",
    "institution_name",
    "website",
    "official_site_url",
    "official_site_run_id",
    "source_dataset_id",
)

#: FOLD-CONTRACT.md v1, ``proposal.csv``. The order is part of the contract.
PROPOSAL_COLUMNS: tuple[str, ...] = (
    "institution_uid",
    "action",
    "proposed_website",
    "expected_current_website",
    "official_site_run_id",
    "official_site_confidence",
    "official_site_git_sha",
    "official_site_stage2_model",
    "source_dataset_id",
    "country_iso3",
    "government_level",
    "institution_type",
    "institution_name",
)

PROPOSAL_FORMAT = "g3o-site-fold-proposal-v1"
REPORT_FORMAT = "g3o-master-sites-report-v1"

#: ``fold-YYYYMMDD-<wave>``; fold dirs are applied in ``fold_id`` sort order.
FOLD_ID_PATTERN = re.compile(r"^fold-\d{8}-[A-Za-z0-9][A-Za-z0-9._-]*$")

JOINED_FILENAME = "master_with_official_sites.csv"
REPORT_FILENAME = "report.json"
CONFLICTS_FILENAME = "conflicts.csv"
PROPOSAL_CSV = "proposal.csv"
PROPOSAL_JSON = "proposal.json"
APPROVAL_JSON = "approval.json"


class MasterSitesError(RuntimeError):
    """The join or the proposal could not be produced as asked. Nothing was written."""


@dataclass
class MasterSitesResult:
    """What the join wrote, and the proposal if one was asked for."""

    report: dict[str, Any] = field(default_factory=dict)
    out_dir: str = ""
    proposal: dict[str, Any] | None = None
    proposal_dir: str = ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_atomic(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)
    return hashlib.sha256(payload).hexdigest()


def _status(pick: dict[str, str] | None, site: str, floor: int) -> str:
    """Why a master row did or did not get a site.

    The order follows the 2026-10-21 reference join (an empty root is reported as
    ``unparseable`` before its confidence is looked at), so the counts reproduce its
    ``join-report.json``. ``load_bypass_map`` checks confidence first, which is why its
    ``skipped_below_confidence`` can exceed ``below_confidence`` here by the rows that
    are both low and rootless. Eligibility itself — ``site`` — is the bypass map's.
    """
    if pick is None:
        return "no_pick"
    if site:
        return "eligible"
    if not (pick.get("site_root") or "").strip():
        return "unparseable"
    if CONFIDENCE_RANK.get((pick.get("confidence") or "").strip().lower(), 0) < floor:
        return "below_confidence"
    return "shared_site_host"


def _vs_master(master_website: str, site: str) -> str:
    master_host = site_host(master_website or "")
    if not master_host:
        return "master_empty"
    return "same_host" if master_host == site_host(site) else "different_host"


def _proposal_action(master_website: str, site: str) -> str | None:
    """``fill``, ``replace`` or ``None`` (same host: nothing to do). Contract v1."""
    if not (master_website or "").strip():
        return "fill"
    if site_host(master_website) != site_host(site):
        return "replace"
    return None


def _csv_bytes(fieldnames: list[str] | tuple[str, ...], rows) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(fieldnames), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _git_sha() -> str:
    try:
        from g3o.run.api import capture_git_metadata

        return capture_git_metadata().sha or ""
    except Exception:  # noqa: BLE001 — provenance is best-effort, as in run records
        return ""


def _master_build_id(values: set[str]) -> str | None:
    from g3o.run.telemetry import master_build_id

    return master_build_id([{"master_build_id": v} for v in sorted(values)])


def build_master_sites(
    master_csv: Path,
    overlay_csv: Path,
    out_dir: Path,
    *,
    fold_proposal_dir: Path | None = None,
    fold_id: str | None = None,
) -> MasterSitesResult:
    """Join ``overlay_csv`` onto ``master_csv`` under ``out_dir``; optionally propose a fold.

    One streaming pass over the master. ``out_dir`` holds the latest copy only: each
    file is replaced, never versioned, so a chain that runs this after every run keeps
    disk bounded. The proposal is written only when ``fold_proposal_dir`` is given, and
    then ``fold_id`` is required.

    Raises :class:`MasterSitesError` (or the bypass map's own
    :class:`~g3o.run.presweep.official_sites.OfficialSitesError`) rather than writing
    something partial: a missing master, a master that already carries the join's
    columns, a malformed ``fold_id``, a proposal dir that already holds an approval, or
    a uid that appears twice among the actions.
    """
    master_csv = Path(master_csv)
    overlay_csv = Path(overlay_csv)
    out_dir = Path(out_dir)
    if fold_proposal_dir is not None:
        fold_proposal_dir = Path(fold_proposal_dir)
        if not fold_id or not FOLD_ID_PATTERN.match(fold_id):
            raise MasterSitesError(
                f"fold proposal needs a fold_id shaped fold-YYYYMMDD-<wave>, got {fold_id!r}"
            )
        if (fold_proposal_dir / APPROVAL_JSON).exists():
            raise MasterSitesError(
                f"{fold_proposal_dir} already holds {APPROVAL_JSON}; rewriting its "
                "proposal would orphan a signed approval. Use a new fold dir."
            )
    if not master_csv.is_file():
        raise MasterSitesError(f"master CSV not found: {master_csv}")

    bypass = load_bypass_map(overlay_csv)
    floor = CONFIDENCE_RANK[bypass.min_confidence]
    picks = {(r.get("institution_uid") or "").strip(): r for r in read_overlay(overlay_csv)}

    status_n: Counter[str] = Counter()
    vs_n: Counter[str] = Counter()
    by_level: Counter[tuple[str, str]] = Counter()
    seen: set[str] = set()
    build_ids: set[str] = set()
    proposal_rows: list[dict[str, str]] = []
    master_rows = 0

    out_dir.mkdir(parents=True, exist_ok=True)
    joined_path = out_dir / JOINED_FILENAME
    joined_tmp = joined_path.with_name(joined_path.name + ".tmp")
    conflicts_buffer = io.StringIO(newline="")
    conflicts_writer = csv.DictWriter(
        conflicts_buffer, fieldnames=list(CONFLICT_COLUMNS), lineterminator="\n",
        extrasaction="ignore",
    )
    conflicts_writer.writeheader()

    with master_csv.open(encoding="utf-8-sig", newline="") as fin:
        fieldnames = list(csv.DictReader(fin).fieldnames or ())
    clash = set(JOIN_COLUMNS) & set(fieldnames)
    if clash:
        raise MasterSitesError(
            f"master already has columns {sorted(clash)}; refusing to shadow them"
        )

    with master_csv.open(encoding="utf-8-sig", newline="") as fin, \
            joined_tmp.open("w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(
            fout, fieldnames=[*fieldnames, *JOIN_COLUMNS], lineterminator="\n"
        )
        writer.writeheader()
        for row in reader:
            master_rows += 1
            uid = (row.get("institution_uid") or "").strip()
            build_id = (row.get("master_build_id") or "").strip()
            if build_id:
                build_ids.add(build_id)
            pick = picks.get(uid) if uid else None
            site = bypass.sites.get(uid, "") if uid else ""
            status = _status(pick, site, floor)
            status_n[status] += 1
            if pick is not None:
                seen.add(uid)

            vs = ""
            website = row.get("website") or ""
            if site:
                vs = _vs_master(website, site)
                vs_n[vs] += 1
                by_level[(row.get("government_level") or "", vs)] += 1
                action = _proposal_action(website, site)
                if action is not None:
                    proposal_rows.append({
                        "institution_uid": uid,
                        "action": action,
                        "proposed_website": site,
                        "expected_current_website": website if action == "replace" else "",
                        "official_site_run_id": pick.get("run_id", ""),
                        "official_site_confidence": pick.get("confidence", ""),
                        "official_site_git_sha": pick.get("git_sha", ""),
                        "official_site_stage2_model": pick.get("stage2_model", ""),
                        "source_dataset_id": row.get("source_dataset_id") or "",
                        "country_iso3": row.get("country_iso3") or "",
                        "government_level": row.get("government_level") or "",
                        "institution_type": row.get("institution_type") or "",
                        "institution_name": row.get("institution_name") or "",
                    })

            extra = {
                "official_site_url": site,
                "official_site_status": status,
                "official_site_confidence": (pick or {}).get("confidence", ""),
                "official_site_vs_master": vs,
                "official_site_run_id": (pick or {}).get("run_id", ""),
                "official_site_git_sha": (pick or {}).get("git_sha", ""),
                "official_site_stage2_model": (pick or {}).get("stage2_model", ""),
            }
            writer.writerow({**row, **extra})
            if vs == "different_host":
                conflicts_writer.writerow({**row, **extra})
    os.replace(joined_tmp, joined_path)

    conflicts_sha = _write_atomic(
        out_dir / CONFLICTS_FILENAME, conflicts_buffer.getvalue().encode("utf-8")
    )
    master_sha = _sha256_file(master_csv)
    overlay_sha = _sha256_file(overlay_csv)
    git_sha = _git_sha()
    orphans = sorted(set(picks) - seen)
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    report: dict[str, Any] = {
        "format": REPORT_FORMAT,
        "created_at": created_at,
        "git_sha": git_sha,
        "master": str(master_csv),
        "master_sha256": master_sha,
        "master_build_id": _master_build_id(build_ids),
        "overlay": str(overlay_csv),
        "overlay_sha256": overlay_sha,
        "out": str(joined_path),
        "out_sha256": _sha256_file(joined_path),
        "conflicts": str(out_dir / CONFLICTS_FILENAME),
        "conflicts_sha256": conflicts_sha,
        "master_rows": master_rows,
        "bypass_manifest": bypass.manifest_block(),
        "status_counts": dict(status_n),
        "eligible_vs_master": dict(vs_n),
        "eligible_vs_master_by_level": {
            f"{k[0]}|{k[1]}": v for k, v in sorted(by_level.items())
        },
        "overlay_uids_not_in_master": len(orphans),
        "overlay_uids_not_in_master_sample": orphans[:20],
    }
    _write_atomic(
        out_dir / REPORT_FILENAME,
        json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    result = MasterSitesResult(report=report, out_dir=str(out_dir))

    if fold_proposal_dir is not None:
        result.proposal = _write_proposal(
            proposal_rows,
            fold_proposal_dir,
            fold_id=str(fold_id),
            created_at=created_at,
            master_csv=master_csv,
            master_sha=master_sha,
            master_build=report["master_build_id"],
            overlay_csv=overlay_csv,
            overlay_sha=overlay_sha,
            bypass=bypass,
            git_sha=git_sha,
        )
        result.proposal_dir = str(fold_proposal_dir)
    logger.info(
        "master sites: %d master rows, %d eligible (%s)",
        master_rows, status_n.get("eligible", 0), dict(vs_n),
    )
    return result


def _write_proposal(
    rows: list[dict[str, str]],
    proposal_dir: Path,
    *,
    fold_id: str,
    created_at: str,
    master_csv: Path,
    master_sha: str,
    master_build: str | None,
    overlay_csv: Path,
    overlay_sha: str,
    bypass: Any,
    git_sha: str,
) -> dict[str, Any]:
    rows = sorted(rows, key=lambda r: r["institution_uid"])
    uids = Counter(r["institution_uid"] for r in rows)
    dupes = sorted(u for u, n in uids.items() if n > 1)
    if dupes:
        # A fold is keyed on uid; two actions for one uid is not a proposal anyone
        # could approve row by row.
        raise MasterSitesError(
            f"{len(dupes)} institution_uid(s) appear on more than one master row: "
            f"{dupes[:5]}. Refusing to propose an ambiguous fold."
        )
    payload = _csv_bytes(PROPOSAL_COLUMNS, rows)
    by_source = Counter(
        r["source_dataset_id"] for r in rows if r["action"] == "replace"
    )
    meta = {
        "format": PROPOSAL_FORMAT,
        "fold_id": fold_id,
        "created_at": created_at,
        "proposal_csv_sha256": hashlib.sha256(payload).hexdigest(),
        "overlay_path": str(overlay_csv),
        "overlay_sha256": overlay_sha,
        "master_path": str(master_csv),
        "master_sha256": master_sha,
        "master_build_id": master_build,
        "rule": {
            "min_confidence": bypass.min_confidence,
            "require_unshared_site_host": bypass.require_unshared_site_host,
        },
        "bypass_content_hash": bypass.content_hash,
        "counts": {
            "fill": sum(1 for r in rows if r["action"] == "fill"),
            "replace": sum(1 for r in rows if r["action"] == "replace"),
            "replace_by_source_dataset_id": dict(sorted(by_source.items())),
        },
        "git_sha": git_sha,
    }
    _write_atomic(proposal_dir / PROPOSAL_CSV, payload)
    _write_atomic(
        proposal_dir / PROPOSAL_JSON,
        json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    return meta
