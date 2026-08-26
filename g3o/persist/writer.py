"""Stage 7 — Deterministic CSV writer.

Walks ``runs/<run_id>/institutions/<shard>/<institution_id>/6_validate.json``
for every institution in a run (storage layout v2 — see
``docs/storage-layout-v2.md``), validates each payload against
``g3o.common.contract.ConsolidatedInstitutionResponse``, and writes three
canonical CSVs to ``runs/<run_id>/final/``:

- ``g3o_activities_v{N}.csv``         (one row per ``(institution × activity)``)
- ``g3o_activity_sources_v{N}.csv``   (one row per source page; ``activity_id``
                                       FK or ``_NA_``)
- ``g3o_institution_summary_v{N}.csv``(one row per institution per run)

Column orders are pinned in ``g3o.common.schema``:
``ACTIVITY_COLUMNS`` / ``ACTIVITY_SOURCE_COLUMNS`` / ``SUMMARY_COLUMNS``.

No LLM calls. No silent imputation; any divergence between the consolidated
payload and the ``ConsolidatedInstitutionResponse`` schema is surfaced as a
``ValidationError`` from the caller's perspective.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.contract import (
    INSTITUTION_UID_PATTERN,
    ConsolidatedInstitutionResponse,
    PersistedActivity,
    PersistedSource,
    ValidationProvenance,
)
from g3o.common.paths import institution_uid_map, iter_institution_dirs, require_layout
from g3o.common.schema import (
    ACTIVITY_COLUMNS,
    ACTIVITY_SOURCE_COLUMNS,
    SUMMARY_COLUMNS,
)
from g3o.extract.salvage import REASON_SALVAGED

logger = logging.getLogger(__name__)

DEFAULT_RUN_TOOL_ACTIVITY = "g3o.persist.writer"
DEFAULT_RUN_TOOL_SOURCE = "g3o.persist.writer"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def _activity_global_row_id(run_id: str, institution_id: str, activity_id: str) -> str:
    return f"{run_id}::{institution_id}::{activity_id}"


def _source_global_row_id(run_id: str, institution_id: str, source_id: str) -> str:
    return f"{run_id}::{institution_id}::{source_id}"


def _summary_global_row_id(run_id: str, institution_id: str) -> str:
    return f"{run_id}::{institution_id}::summary"


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def sweep_uid_for(institution_uid: str) -> str:
    """``"G3O-S-" + <the 8-digit tail of institution_uid>`` (PI ruling 2026-08-14 §2).

    Deterministic, stateless, no lookup and no counter: re-running institution
    X in a later run produces the same ``sweep_uid`` and a different
    ``(sweep_uid, run_id)`` pair, and it is the composite key — not the string
    — that carries the distinction. Minted here, at Stage 7 persist, and never
    at Stage 6: that is an LLM boundary and a load-bearing key must not be
    model-produced (§3).

    Raises:
        ValueError: on an institution_uid that is not ``G3O-I-<8 digits>``. The
            8-digit tail is the whole of the derivation, so a malformed input
            has no defensible output.
    """
    if not re.match(INSTITUTION_UID_PATTERN, institution_uid):
        raise ValueError(
            f"cannot derive a sweep_uid from institution_uid={institution_uid!r}: "
            f"expected {INSTITUTION_UID_PATTERN}"
        )
    return f"G3O-S-{institution_uid[-8:]}"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


@dataclass
class LoadedInstitution:
    """One institution's consolidated payload + the on-disk path it came from."""

    institution_id: str
    response: ConsolidatedInstitutionResponse
    source_path: Path
    #: The master's permanent key for this institution, off the run manifest.
    #: Not on ``response``: that object is parsed from Stage 6 model output.
    institution_uid: str


def load_consolidated_outputs(run_dir: Path) -> tuple[list[LoadedInstitution], list[str]]:
    """Walk ``institutions/<shard>/<inst>/6_validate.json``; validate each.

    Institution discovery goes through :func:`g3o.common.paths.iter_institution_dirs`
    (storage layout v2), which yields only institution directories in ``inst_id``
    order — so no run-level entry (``_state``, ``final``, reports) can reach this
    loop and the pre-v2 name filtering is gone.

    The manifest's ``institution_uids`` block is joined on here rather than
    read from ``institution.json``: that file is the Stage 2/3/5/6 prompt
    payload, and the uid is bookkeeping that must not reach a model (PI ruling
    2026-08-14 §3). A missing uid raises rather than defaulting — an empty
    stamp is quarantined row by row at ingest, which is the failure this whole
    change exists to remove.

    Returns:
        (loaded, failures) where ``loaded`` is a list of ``LoadedInstitution``
        and ``failures`` is a list of institution_ids whose payload failed to
        parse / validate. Failures are logged at WARNING; the caller decides
        whether to abort.

    Raises:
        RuntimeError: when the manifest carries no ``institution_uids`` block,
            or carries no entry for an institution that reached Stage 6.
    """
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir does not exist: {run_dir}")

    uid_by_inst = institution_uid_map(run_dir)

    loaded: list[LoadedInstitution] = []
    failures: list[str] = []
    unstamped: list[str] = []
    for inst_dir in iter_institution_dirs(run_dir):
        path = inst_dir / "6_validate.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            response = ConsolidatedInstitutionResponse.model_validate(payload)
        except Exception as exc:
            logger.warning("Stage 7: %s failed to load: %s", inst_dir.name, exc)
            failures.append(inst_dir.name)
            continue
        institution_id = response.institution.institution_id
        institution_uid = uid_by_inst.get(institution_id, "")
        if not institution_uid:
            unstamped.append(institution_id)
            continue
        loaded.append(
            LoadedInstitution(
                institution_id=institution_id,
                response=response,
                source_path=path,
                institution_uid=institution_uid,
            )
        )
    if unstamped:
        raise RuntimeError(
            f"{len(unstamped)} institution(s) reached Stage 6 but carry no "
            "institution_uid in the run manifest, so their rows cannot be stamped: "
            + ", ".join(unstamped[:5])
            + ("…" if len(unstamped) > 5 else "")
        )
    return loaded, failures


def salvaged_fields_by_source(run_dir: Path) -> dict[tuple[str, str], str]:
    """Map ``(institution_id, source_url) -> ';'-joined salvaged Group-D fields``.

    Deterministic: reads the attrition ledger (not the LLM) for Stage-5
    ``group_d_incomplete_salvaged`` records — each recorded against the scraped
    page URL with ``detail='rows=[...];fields=f1,f2'`` — and returns the salvaged
    field names per source page. Absent ledger → empty map.

    The value is **page-level**, not per-record or per-event: it is the
    deduplicated set of field names for which *at least one record* on the page
    was salvaged. This function does not compute that dedup — it only reads it.
    Stage-5 (``run.presweep.stage_extract``) does the work: for each page it
    unions the field names across every salvaged record via a sorted set
    (``sorted({f for s in salvaged for f in s.salvaged_fields})``) and writes
    exactly one ``group_d_incomplete_salvaged`` ledger record per page. Because
    that single record already carries the collapsed set, this map does not —
    and cannot — distinguish which record salvaged which field, or how many
    times a field was salvaged; all of that is folded in upstream.

    Join caveat (documented, conservative): the key is the source URL. If Stage-6
    consolidation altered a source_url, its salvage annotation will not attach
    (the row is treated as un-salvaged) — an under-mark, never an over-mark. A
    salvaged page always remains fully accounted for in the ledger itself.
    """
    out: dict[tuple[str, str], str] = {}
    for rec in attrition.read_records(run_dir):
        if rec.get("reason") != REASON_SALVAGED:
            continue
        url = rec.get("url")
        detail = rec.get("detail", "")
        if not url or ";fields=" not in detail:
            continue
        raw = detail.split(";fields=", 1)[1]
        fields = sorted(f for f in raw.split(",") if f)
        out[(rec.get("institution_id", ""), url)] = ";".join(fields)
    return out


# ---------------------------------------------------------------------------
# Per-row builders
# ---------------------------------------------------------------------------


_CONFIDENCE_ORDER = {"high": 3, "medium": 2, "low": 1}


def _aggregate_uncertainty_flags(activities: Iterable[Any]) -> str:
    seen: set[str] = set()
    for a in activities:
        flags = a.uncertainty_flags
        if flags == "none" or not flags:
            continue
        for tok in flags.split(";"):
            tok = tok.strip()
            if tok and tok != "none":
                seen.add(tok)
    if not seen:
        return "none"
    return ";".join(sorted(seen))


def _best_confidence(activities: Iterable[Any]) -> str:
    best_rank = 0
    best = "_NA_"
    for a in activities:
        rank = _CONFIDENCE_ORDER.get(a.confidence, 0)
        if rank > best_rank:
            best_rank = rank
            best = a.confidence
    return best


def _pipe_join(values: Iterable[str]) -> str:
    return " | ".join(values)


def build_activity_rows(
    response: ConsolidatedInstitutionResponse,
    *,
    run_id: str,
    run_model: str,
    institution_uid: str,
    run_tool: str = DEFAULT_RUN_TOOL_ACTIVITY,
    run_date: str | None = None,
) -> list[dict[str, Any]]:
    """Build one CSV-shaped dict per ``ConsolidatedActivity``.

    ``institution_uid`` is keyword-required with no default: the loader
    quarantines an unstamped fact row, so there is no safe fallback to offer.
    """
    run_date = run_date or _utc_today()
    sweep_uid = sweep_uid_for(institution_uid)
    rows: list[dict[str, Any]] = []
    institution = response.institution
    for activity in response.activities:
        provenance = ValidationProvenance(
            global_row_id=_activity_global_row_id(
                run_id, institution.institution_id, activity.activity_id
            ),
            run_id=run_id,
            run_model=run_model,
            run_tool=run_tool,
            run_date=run_date,
            institution_uid=institution_uid,
            sweep_uid=sweep_uid,
        )
        pa = PersistedActivity(
            provenance=provenance, institution=institution, activity=activity
        )
        rows.append(pa.to_csv_dict())
    return rows


def build_source_rows(
    response: ConsolidatedInstitutionResponse,
    *,
    run_id: str,
    run_model: str,
    institution_uid: str,
    run_tool: str = DEFAULT_RUN_TOOL_SOURCE,
    run_date: str | None = None,
    salvaged_by_source: dict[tuple[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    """Build one CSV-shaped dict per ``SourceRecord``.

    ``salvaged_by_source`` (from :func:`salvaged_fields_by_source`) annotates
    each row's ``group_d_salvaged_fields`` from the attrition ledger keyed by
    ``(institution_id, source_url)``; defaults to no annotation.

    ``institution_uid`` is keyword-required for the same reason as in
    :func:`build_activity_rows`.
    """
    run_date = run_date or _utc_today()
    sweep_uid = sweep_uid_for(institution_uid)
    salvaged_by_source = salvaged_by_source or {}
    rows: list[dict[str, Any]] = []
    institution_id = response.institution.institution_id
    for source in response.sources:
        provenance = ValidationProvenance(
            global_row_id=_source_global_row_id(
                run_id, institution_id, source.source_id
            ),
            run_id=run_id,
            run_model=run_model,
            run_tool=run_tool,
            run_date=run_date,
            institution_uid=institution_uid,
            sweep_uid=sweep_uid,
        )
        ps = PersistedSource(
            provenance=provenance,
            institution_id=institution_id,
            source=source,
            group_d_salvaged_fields=salvaged_by_source.get(
                (institution_id, source.source_url), ""
            ),
        )
        rows.append(ps.to_csv_dict())
    return rows


def build_summary_row(
    response: ConsolidatedInstitutionResponse,
    *,
    run_id: str,
    institution_uid: str,
    run_date: str | None = None,
) -> dict[str, Any]:
    """Build one CSV-shaped dict matching ``SUMMARY_COLUMNS``.

    Carries ``institution_uid`` but not ``sweep_uid``. The reason changed on
    2026-08-25 while the column list did not: this CSV *is* now a loader input —
    ``g3o-api``'s ``load_search_verdicts`` reads it off ``--run-dir`` to carry the
    institution-level verdict to the database (PI ruling, g3o-api #17) — but it
    keys on ``institution_uid``, and at institution grain ``sweep_uid`` is a
    deterministic restatement of the uid.
    """
    run_date = run_date or _utc_today()
    institution = response.institution
    activities = response.activities
    sources = response.sources

    cred_counts = {"high": 0, "medium": 0, "low": 0}
    for s in sources:
        cred_counts[s.source_credibility] = cred_counts.get(s.source_credibility, 0) + 1

    distinct_tools = sorted({a.tool_name for a in activities if a.tool_name != "unknown"})
    distinct_vendors = sorted({a.vendor for a in activities if a.vendor != "unknown"})
    activities_found = [a.activity_name for a in activities]

    row = {
        "institution_uid": institution_uid,
        "institution_id": institution.institution_id,
        "institution_name": institution.institution_name,
        "country": institution.country,
        "branch_of_government": institution.branch_of_government,
        "level_of_government": institution.level_of_government,
        "run_id": run_id,
        "run_date": run_date,
        "has_genai_activity": institution.has_genai_activity,
        "institution_summary": institution.institution_summary,
        "institution_search_languages": institution.institution_search_languages,
        "n_pages_extracted": response.consolidation_metadata.n_input_pages,
        "n_activities": len(activities),
        "n_sources": len(sources),
        "n_high_credibility_sources": cred_counts["high"],
        "n_medium_credibility_sources": cred_counts["medium"],
        "n_low_credibility_sources": cred_counts["low"],
        "activities_found": _pipe_join(activities_found),
        "tools_found": _pipe_join(distinct_tools),
        "vendors_found": _pipe_join(distinct_vendors),
        "best_confidence": _best_confidence(activities),
        "consolidated_uncertainty_flags": _aggregate_uncertainty_flags(activities),
    }

    missing = [c for c in SUMMARY_COLUMNS if c not in row]
    if missing:
        raise RuntimeError(f"summary row missing required columns: {missing}")
    return {col: row[col] for col in SUMMARY_COLUMNS}


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> int:
    """Write ``rows`` to ``path`` with header ``columns``. Returns row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def write_run_csvs(
    run_dir: Path,
    *,
    run_id: str,
    run_model: str,
    version: int = 1,
    overwrite: bool = False,
    run_date: str | None = None,
    activities_tool: str = DEFAULT_RUN_TOOL_ACTIVITY,
    sources_tool: str = DEFAULT_RUN_TOOL_SOURCE,
) -> dict[str, Any]:
    """Persist all consolidated outputs in ``run_dir`` to three CSVs at
    ``run_dir / "final"``.

    Args:
        run_dir: ``runs/<run_id>/`` directory.
        run_id: pinned into the provenance + summary rows.
        run_model: pinned into provenance.
        version: ``v{N}`` suffix on output filenames; ``1`` is the default.
        overwrite: when False, refuse to clobber existing outputs.
        run_date: ISO date for provenance; defaults to UTC today.
        activities_tool / sources_tool: ``run_tool`` provenance value for each CSV.

    Returns:
        Summary dict with output paths and row counts.
    """
    require_layout(run_dir)
    final_dir = run_dir / "final"
    activities_path = final_dir / f"g3o_activities_v{version}.csv"
    sources_path = final_dir / f"g3o_activity_sources_v{version}.csv"
    summary_path = final_dir / f"g3o_institution_summary_v{version}.csv"

    if not overwrite:
        existing = [p for p in (activities_path, sources_path, summary_path) if p.exists()]
        if existing:
            raise FileExistsError(
                "Refusing to overwrite existing CSVs (pass overwrite=True): "
                + ", ".join(str(p) for p in existing)
            )

    loaded, failures = load_consolidated_outputs(run_dir)
    salvaged_by_source = salvaged_fields_by_source(run_dir)

    activity_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for li in loaded:
        activity_rows.extend(
            build_activity_rows(
                li.response,
                run_id=run_id,
                run_model=run_model,
                institution_uid=li.institution_uid,
                run_tool=activities_tool,
                run_date=run_date,
            )
        )
        source_rows.extend(
            build_source_rows(
                li.response,
                run_id=run_id,
                run_model=run_model,
                institution_uid=li.institution_uid,
                run_tool=sources_tool,
                run_date=run_date,
                salvaged_by_source=salvaged_by_source,
            )
        )
        summary_rows.append(
            build_summary_row(
                li.response,
                run_id=run_id,
                institution_uid=li.institution_uid,
                run_date=run_date,
            )
        )

    n_activities = _write_csv(activities_path, ACTIVITY_COLUMNS, activity_rows)
    n_sources = _write_csv(sources_path, ACTIVITY_SOURCE_COLUMNS, source_rows)
    n_summary = _write_csv(summary_path, SUMMARY_COLUMNS, summary_rows)

    return {
        "run_dir": str(run_dir),
        "run_id": run_id,
        "version": version,
        "n_institutions": len(loaded),
        "n_load_failures": len(failures),
        "load_failures": failures,
        "outputs": {
            "activities": {"path": str(activities_path), "n_rows": n_activities},
            "activity_sources": {"path": str(sources_path), "n_rows": n_sources},
            "institution_summary": {"path": str(summary_path), "n_rows": n_summary},
        },
    }


__all__ = [
    "DEFAULT_RUN_TOOL_ACTIVITY",
    "DEFAULT_RUN_TOOL_SOURCE",
    "LoadedInstitution",
    "build_activity_rows",
    "build_source_rows",
    "build_summary_row",
    "load_consolidated_outputs",
    "sweep_uid_for",
    "write_run_csvs",
]
