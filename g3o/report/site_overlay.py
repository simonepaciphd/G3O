"""Official-site overlay — Stage 2's picks, harvested across runs, keyed on institution.

Stage 2 finds an official site for institutions the master has none for: 6,684 of
12,000 on the anglophone round ``r20260829T121145Z-233a``, of which 6,639 belong to
master rows whose ``website`` is empty. That is a **+45.3%** lift on the registry's
entire website column from one round, and it compounds — Stage 2 hits 90.0% on
website-present institutions against 51.0% on website-free local ones, both measured
inside that run. This module is what turns those picks into something a later run can
spend, without any run rewriting the registry.

**Derived, never canonical.** The overlay is a projection of completed run directories.
It is rebuilt from scratch, never appended to, and nothing here writes to the master —
:mod:`g3o.run.presweep.official_sites` reads it at plan time and decorates the *drawn
sample* in memory. The read-only master stays the master.

**Provenance travels with the value or the value is worthless.** Every row carries
``run_id``, ``run_date``, ``git_sha``, the Stage-2 model, and the model's own
``confidence`` — so a consumer can always say which run, which code and which model
produced the site it is about to search.

Three sharing margins, because a shared domain is not an institution identifier
-------------------------------------------------------------------------------
A third of a government estate can sit on one domain: 95 New South Wales councils under
``nsw.gov.au``, 45 Maltese institutions under ``gov.mt``, 33 Lincolnshire parishes under
``lincolnshire.gov.uk``. Writing one of those into 95 institutions and then issuing
``site:nsw.gov.au`` for each of them is *worse than no site at all* — the website-free
path at least searches the institution's own name. So each row records:

``host_share_count``
    Exact host. Heuristic-free, depends on no list: 1,173 of 6,684 (17.5%) on that run.

``site_host_share_count``
    Host as :func:`g3o.common.urlnorm.site_host` renders it — a leading ``www.``
    stripped, port preserved. **This is the string the ``site:`` operator actually
    receives**, so it is the margin that predicts Stage 1b: 1,192 (17.8%). Keying on the
    exact host instead reads ``www.gov.bw`` and ``gov.bw`` as two targets when Stage 1b
    would issue one identical query for both.

``domain_share_count``
    Registrable domain under the real public suffix list, via
    :func:`g3o.report.discovery_yield.registrable_domain`: 1,660 (24.8%). Useful as
    description, poor as a control — the PSL's own coverage is uneven. ``wa.gov.au``,
    ``vic.gov.au`` and ``qld.gov.au`` are public suffixes and ``nsw.gov.au`` is not, so
    88 Western Australian councils read as unshared and 95 NSW ones as shared, for no
    reason having to do with those councils.

Read-only from disk; no network. Mirrors :mod:`g3o.report.health`'s convention.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from g3o.common.urlnorm import site_host, site_root
from g3o.report.discovery_yield import registrable_domain

logger = logging.getLogger(__name__)

__all__ = [
    "OVERLAY_COLUMNS",
    "OVERLAY_SCHEMA_VERSION",
    "PRECEDENCE_MODES",
    "OverlayRow",
    "build_overlay",
    "harvest_run",
    "is_run_dir",
    "iter_run_dirs",
    "read_overlay",
    "write_overlay",
]

#: Bump when a column changes meaning, not when one is added.
OVERLAY_SCHEMA_VERSION = 1

#: Stage-2 confidence, best first. ``none`` only ever accompanies a null URL.
CONFIDENCE_RANK: dict[str, int] = {"high": 3, "medium": 2, "low": 1}

#: Cross-run precedence. Two runs *will* disagree about one institution: across the ten
#: completed runs on ``g3o-run-01`` as of 2026-08-30, 21,722 observations collapse to
#: 21,025 institutions, so 697 were seen more than once.
#:
#: ``confidence-then-recency`` is the default because Stage-2 confidence is the only
#: quality signal on the row, and a later run drawn on a worse frame should not
#: overwrite a better pick. ``run_id`` is the final tiebreak in both modes, so the
#: winner never depends on filesystem enumeration order.
PRECEDENCE_MODES: tuple[str, ...] = ("confidence-then-recency", "recency-then-confidence")

OVERLAY_COLUMNS: tuple[str, ...] = (
    # identity
    "institution_uid",
    "institution_id",
    "master_row_id",
    "institution_name",
    "country",
    "government_level",
    "institution_type",
    # the value, as returned and as derived
    "discovered_url_raw",
    "site_root",
    "site_host",
    "url_host",
    "url_path",
    "registrable_domain",
    # sharing, computed over the finished overlay
    "host_share_count",
    "site_host_share_count",
    "domain_share_count",
    # what the master carried when the run drew its frame
    "master_website_at_run",
    # provenance
    "confidence",
    "run_id",
    "run_date",
    "run_completed_at",
    "git_sha",
    "stage2_model",
    # conflict bookkeeping
    "n_run_observations",
    "superseded_run_ids",
    "conflicting_hosts",
    # adjudication aid
    "stage2_rationale",
)


@dataclass(frozen=True)
class OverlayRow:
    """One institution's winning Stage-2 pick. Immutable; the CSV is the interchange."""

    values: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


# ----------------------------------------------------------------------------------
# run-directory discovery
# ----------------------------------------------------------------------------------


def is_run_dir(path: Path) -> bool:
    """True when ``path`` looks like a completed layout-v2 run directory.

    Both markers are required. ``institutions/`` alone would match a half-written
    tree, and ``manifest.json`` alone matches a planned-but-never-run layout.
    """
    return (path / "manifest.json").is_file() and (path / "institutions").is_dir()


def iter_run_dirs(runs_dir: Path):
    """Yield every run directory under ``runs_dir``, sorted, skipping ``_``-prefixed.

    The underscore skip is what keeps the overlay's own output directory
    (``runs_dir / "_site_overlay"``) from being scanned as a run.
    """
    if not runs_dir.is_dir():
        return
    for child in sorted(runs_dir.iterdir()):
        if child.name.startswith("_") or not child.is_dir():
            continue
        if is_run_dir(child):
            yield child


# ----------------------------------------------------------------------------------
# harvest
# ----------------------------------------------------------------------------------


def _run_meta(run_dir: Path) -> dict[str, str]:
    """``run_id``, ``run_date``, ``git_sha``, Stage-2 model, completion timestamp."""
    meta = {
        "run_id": run_dir.name,
        "run_date": "",
        "run_completed_at": "",
        "git_sha": "",
        "stage2_model": "",
    }
    manifest_path = run_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    meta["run_id"] = manifest.get("run_id") or meta["run_id"]
    meta["run_date"] = manifest.get("run_date") or ""
    meta["stage2_model"] = manifest.get("run_model") or ""

    events = run_dir / "events.jsonl"
    if events.is_file():
        with events.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not meta["git_sha"] and event.get("git_sha"):
                    meta["git_sha"] = str(event["git_sha"])
                if str(event.get("event") or event.get("event_type") or "") == "run_completed":
                    meta["run_completed_at"] = str(
                        event.get("ts") or event.get("timestamp") or ""
                    )
    return meta


def _uid_by_institution_id(run_dir: Path) -> dict[str, str]:
    """``institution_id`` → ``institution_uid``, from ``institution_report.csv``.

    ``institution.json`` carries the institution's identity but not its uid; the report
    is the only per-run file that pairs the two.
    """
    report = run_dir / "institution_report.csv"
    out: dict[str, str] = {}
    if not report.is_file():
        return out
    with report.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            inst_id = (row.get("institution_id") or "").strip()
            if inst_id:
                out[inst_id] = (row.get("institution_uid") or "").strip()
    return out


def harvest_run(run_dir: Path) -> list[dict[str, Any]]:
    """One record per institution in ``run_dir`` for which Stage 2 returned a URL.

    Institutions with no site are **absent**, not blank: the overlay states what was
    found and never what was not. Bypass envelopes are skipped — a bypassed pick came
    *from* a master column, so harvesting it back would launder a stored value into a
    fresh observation with a new run's provenance on it.
    """
    meta = _run_meta(run_dir)
    uids = _uid_by_institution_id(run_dir)
    records: list[dict[str, Any]] = []
    institutions = run_dir / "institutions"
    for bucket in sorted(institutions.iterdir()):
        if not bucket.is_dir():
            continue
        for inst_dir in sorted(bucket.iterdir()):
            record = _harvest_institution(inst_dir, meta, uids)
            if record is not None:
                records.append(record)
    return records


def _harvest_institution(
    inst_dir: Path, meta: dict[str, str], uids: dict[str, str]
) -> dict[str, Any] | None:
    site_path = inst_dir / "2_official_site.json"
    if not site_path.is_file():
        return None
    try:
        site = json.loads(site_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("site overlay: unreadable %s", site_path)
        return None
    if site.get("bypassed"):
        return None
    url = site.get("url")
    if not url:
        return None
    institution: dict[str, Any] = {}
    inst_path = inst_dir / "institution.json"
    if inst_path.is_file():
        try:
            institution = json.loads(inst_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            institution = {}
    inst_id = str(institution.get("institution_id") or inst_dir.name)
    record = {
        "institution_uid": uids.get(inst_id, ""),
        "institution_id": inst_id,
        "master_row_id": str(institution.get("master_row_id") or ""),
        "institution_name": institution.get("institution_name") or "",
        "country": institution.get("country") or "",
        "government_level": institution.get("level_of_government") or "",
        "institution_type": institution.get("institution_type") or "",
        "master_website_at_run": institution.get("website") or "",
        "discovered_url_raw": str(url),
        "confidence": str(site.get("confidence") or "").strip().lower(),
        "stage2_rationale": " ".join(str(site.get("rationale") or "").split()),
    }
    record.update(meta)
    return record


# ----------------------------------------------------------------------------------
# build
# ----------------------------------------------------------------------------------


def _precedence_key(record: dict[str, Any], mode: str):
    confidence = CONFIDENCE_RANK.get(record.get("confidence", ""), 0)
    recency = (record.get("run_date", ""), record.get("run_id", ""))
    if mode == "recency-then-confidence":
        return (recency, confidence)
    return (confidence, recency)


def build_overlay(
    run_dirs: list[Path], *, precedence: str = PRECEDENCE_MODES[0]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Harvest ``run_dirs`` into one row per institution, plus a stats block.

    Deterministic and total: rows come out sorted by ``institution_uid``, every derived
    value is a pure function of the inputs, and no wall-clock, path or hostname enters a
    row — so re-running over the same inputs is byte-identical and the order of
    ``run_dirs`` does not matter. That is what makes this safe to run after every run:
    the second build over an unchanged corpus is a no-op, not an append.

    An institution whose ``institution_uid`` is missing from its run's report is keyed
    ``__NOUID__<institution_id>`` rather than dropped or blank-keyed, so it can never
    silently join to a master row.
    """
    if precedence not in PRECEDENCE_MODES:
        raise ValueError(
            f"unknown precedence {precedence!r}; expected one of {PRECEDENCE_MODES}"
        )
    by_uid: dict[str, list[dict[str, Any]]] = {}
    stats: dict[str, Any] = {
        "schema_version": OVERLAY_SCHEMA_VERSION,
        "precedence": precedence,
        "runs": [],
        "records_harvested": 0,
        "records_without_uid": 0,
    }
    for run_dir in run_dirs:
        records = harvest_run(run_dir)
        stats["runs"].append({"run_id": run_dir.name, "sites_found": len(records)})
        stats["records_harvested"] += len(records)
        for record in records:
            uid = record["institution_uid"]
            if not uid:
                stats["records_without_uid"] += 1
                uid = "__NOUID__" + record["institution_id"]
                record["institution_uid"] = uid
            by_uid.setdefault(uid, []).append(record)

    rows = [_winning_row(uid, by_uid[uid], precedence) for uid in sorted(by_uid)]
    _annotate_sharing(rows, stats)
    stats["runs"].sort(key=lambda entry: entry["run_id"])
    return rows, stats


def _winning_row(
    uid: str, observations: list[dict[str, Any]], precedence: str
) -> dict[str, Any]:
    ordered = sorted(observations, key=lambda r: _precedence_key(r, precedence), reverse=True)
    winner, losers = ordered[0], ordered[1:]
    raw = winner["discovered_url_raw"]
    host = site_host(raw) or ""
    conflicting = sorted(
        {h for h in (site_host(loser["discovered_url_raw"]) for loser in losers) if h and h != host}
    )
    return {
        "institution_uid": uid,
        "institution_id": winner["institution_id"],
        "master_row_id": winner["master_row_id"],
        "institution_name": winner["institution_name"],
        "country": winner["country"],
        "government_level": winner["government_level"],
        "institution_type": winner["institution_type"],
        "discovered_url_raw": raw,
        "site_root": site_root(raw) or "",
        "site_host": host,
        "url_host": _exact_host(raw),
        "url_path": _path_of(raw),
        "registrable_domain": registrable_domain(raw),
        "master_website_at_run": winner["master_website_at_run"],
        "confidence": winner["confidence"],
        "run_id": winner["run_id"],
        "run_date": winner["run_date"],
        "run_completed_at": winner["run_completed_at"],
        "git_sha": winner["git_sha"],
        "stage2_model": winner["stage2_model"],
        "n_run_observations": str(len(observations)),
        "superseded_run_ids": "|".join(sorted({loser["run_id"] for loser in losers})),
        "conflicting_hosts": "|".join(conflicting),
        "stage2_rationale": winner["stage2_rationale"],
    }


def _exact_host(url: str) -> str:
    """Host with casing folded but ``www.`` **kept** — the heuristic-free margin."""
    from urllib.parse import urlsplit

    candidate = url if "//" in url else "https://" + url
    try:
        netloc = urlsplit(candidate).netloc.lower().rpartition("@")[2]
    except ValueError:
        return ""
    return netloc


def _path_of(url: str) -> str:
    """Normalised path, ``""`` for a root. Kept for adjudication, not for querying.

    Stage 1b never sees it: :func:`g3o.common.urlnorm.site_host` discards the path, so a
    stored path changes nothing downstream unless that function changes.
    """
    from urllib.parse import urlsplit

    candidate = url if "//" in url else "https://" + url
    try:
        path = urlsplit(candidate).path or ""
    except ValueError:
        return ""
    return "" if path == "/" else path.rstrip("/")


def _annotate_sharing(rows: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    """Count the three sharing margins over the finished overlay, and record them."""
    exact: dict[str, int] = {}
    sites: dict[str, int] = {}
    domains: dict[str, int] = {}
    for row in rows:
        for key, counter in (
            ("url_host", exact),
            ("site_host", sites),
            ("registrable_domain", domains),
        ):
            value = row[key]
            if value:
                counter[value] = counter.get(value, 0) + 1
    for row in rows:
        row["host_share_count"] = str(exact.get(row["url_host"], 0))
        row["site_host_share_count"] = str(sites.get(row["site_host"], 0))
        row["domain_share_count"] = str(domains.get(row["registrable_domain"], 0))

    stats["overlay_rows"] = len(rows)
    stats["distinct_hosts"] = len(exact)
    stats["distinct_site_hosts"] = len(sites)
    stats["distinct_registrable_domains"] = len(domains)
    stats["rows_sharing_host"] = sum(1 for r in rows if int(r["host_share_count"]) > 1)
    stats["rows_sharing_site_host"] = sum(
        1 for r in rows if int(r["site_host_share_count"]) > 1
    )
    stats["rows_sharing_domain"] = sum(1 for r in rows if int(r["domain_share_count"]) > 1)
    stats["rows_unparseable"] = sum(1 for r in rows if not r["site_host"])
    stats["confidence_counts"] = _counts(r["confidence"] for r in rows)
    stats["top_shared_site_hosts"] = [
        {"site_host": host, "institutions": n}
        for host, n in sorted(sites.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
        if n > 1
    ]


def _counts(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


# ----------------------------------------------------------------------------------
# interchange
# ----------------------------------------------------------------------------------


def write_overlay(rows: list[dict[str, Any]], path: Path) -> str:
    """Write ``rows`` to ``path`` and return the sha256 of the bytes written.

    The digest is the idempotence check a caller can act on: an unchanged corpus
    produces an unchanged digest, so a post-run rebuild that reports the same hash did
    nothing and can say so.
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(OVERLAY_COLUMNS), lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in OVERLAY_COLUMNS})
    payload = buffer.getvalue().encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def read_overlay(path: Path) -> list[dict[str, str]]:
    """Read an overlay CSV back. Raises when a required column is missing."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(OVERLAY_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"{path} is not an overlay: missing columns {sorted(missing)}"
            )
        return list(reader)
