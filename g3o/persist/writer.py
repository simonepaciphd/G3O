"""Stage 7 — Deterministic CSV writer.

Walks ``runs/<run_id>/institutions/<shard>/<institution_id>/6_validate.json``
for every institution in a run (storage layout v2 — see
``docs/storage-layout-v2.md``), validates each payload against
``g3o.common.contract.ConsolidatedInstitutionResponse`` (legacy v2.5/2.6) or,
for a payload whose ``format`` names it, the v2.7 identity-and-keys model
``g3o.common.response_v27.ConsolidatedInstitutionResponseV27`` (RC-D-028 4 a:
every v2.7 value is read from ``6_storage.json``), and writes three
canonical CSVs to ``runs/<run_id>/final/``:

- ``g3o_activities_v{N}.csv``         (one row per ``(institution × activity)``)
- ``g3o_activity_sources_v{N}.csv``   (one row per page/activity evidence claim; ``activity_id``
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
    PersistedActivity,
    PersistedSource,
    ValidationProvenance,
)
from g3o.common.paths import institution_uid_map, iter_institution_dirs, require_layout
from g3o.common.response_v27 import (
    AnyValidateResponse,
    ConsolidatedInstitutionResponseV27,
    check_storage_binding,
    list_members,
    parse_validate_payload,
    retired_legacy_cells,
)
from g3o.common.schema import (
    ACTIVITY_COLUMNS,
    ACTIVITY_COLUMNS_V25,
    ACTIVITY_SOURCE_COLUMNS,
    ACTIVITY_SOURCE_COLUMNS_V25,
    SUMMARY_COLUMNS,
    SUMMARY_COLUMNS_V25,
)
from g3o.common.storage import StorageEnvelope, legacy_row
from g3o.extract.salvage import REASON_SALVAGED
from g3o.persist.integrity import IntegrityError, validate_run_csvs

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
    #: Legacy response, or the v2.7 identity/keys response (values in ``storage``).
    response: AnyValidateResponse
    source_path: Path
    #: The master's permanent key for this institution, off the run manifest.
    #: Not on ``response``: that object is parsed from Stage 6 model output.
    institution_uid: str
    storage: StorageEnvelope | None = None


STORAGE_UNREADABLE = "stage7_storage_unreadable"


def load_consolidated_outputs(run_dir: Path, *, held: list[str] | None = None
                              ) -> tuple[list[LoadedInstitution], list[str]]:
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
        whether to abort. With ``held`` (a list), an institution whose
        ``6_storage.json`` does not load is appended there and recorded in the
        attrition ledger (``stage7_storage_unreadable``) instead of raising.

    Raises:
        RuntimeError: when the manifest carries no ``institution_uids`` block,
            or carries no entry for an institution that reached Stage 6.
    """
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir does not exist: {run_dir}")

    uid_by_inst = institution_uid_map(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    declared_release = manifest.get("storage_contract", {}).get("codebook_release")
    if declared_release not in (None, "v2.5", "2.7"):
        raise ValueError("unsupported storage codebook release")

    loaded: list[LoadedInstitution] = []
    failures: list[str] = []
    unstamped: list[str] = []
    for inst_dir in iter_institution_dirs(run_dir):
        path = inst_dir / "6_validate.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            response = parse_validate_payload(payload)
        except Exception as exc:
            logger.warning("Stage 7: %s failed to load: %s", inst_dir.name, exc)
            failures.append(inst_dir.name)
            continue
        institution_id = response.institution.institution_id
        institution_uid = uid_by_inst.get(institution_id, "")
        if not institution_uid:
            unstamped.append(institution_id)
            continue
        storage_path = inst_dir / "6_storage.json"
        storage = None
        is_v27 = isinstance(response, ConsolidatedInstitutionResponseV27)
        if is_v27 and declared_release not in (None, "2.7"):
            raise ValueError(f"{institution_id}: v2.7 6_validate.json in a {declared_release} run")
        if is_v27 and not storage_path.exists():
            raise ValueError(f"{institution_id}: v2.7 6_validate.json lacks its 6_storage.json")
        if storage_path.exists():
            try:
                storage = StorageEnvelope.load(storage_path, run_dir / "final" / "instruments",
                                               artifact_root=run_dir)
            except (ValueError, UnicodeDecodeError) as exc:
                if held is None:
                    raise
                # One unreadable (e.g. truncated) storage file holds that institution only:
                # recorded, never published, never a silent omission.
                attrition.record(run_dir, institution_id=institution_id, stage="persist",
                                 reason=STORAGE_UNREADABLE, detail=f"{type(exc).__name__}: {exc}")
                held.append(institution_id)
                continue
            if declared_release is not None and declared_release != storage.data["codebook_release"]:
                raise ValueError("manifest/envelope codebook release mismatch")
            if storage.data["institution_uid"] != institution_uid or storage.data["institution_id"] != institution_id:
                raise ValueError("storage envelope is bound to another institution")
            if set(storage.data["activities"]) != {a.activity_id for a in response.activities} or set(storage.data["sources"]) != {v.source_id for v in response.sources}:
                raise ValueError("storage row identifiers differ from consolidated rows")
            if is_v27:
                check_storage_binding(response, storage.data)
        elif declared_release == "2.7":
            raise ValueError(f"{institution_id}: 2.7 run lacks explicit 6_storage.json")
        loaded.append(
            LoadedInstitution(
                institution_id=institution_id,
                response=response,
                source_path=path,
                institution_uid=institution_uid,
                storage=storage,
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
    response: AnyValidateResponse,
    *,
    run_id: str,
    run_model: str,
    institution_uid: str,
    run_tool: str = DEFAULT_RUN_TOOL_ACTIVITY,
    run_date: str | None = None,
    storage: StorageEnvelope | None = None,
    storage_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build one CSV-shaped dict per ``ConsolidatedActivity``.

    ``institution_uid`` is keyword-required with no default: the loader
    quarantines an unstamped fact row, so there is no safe fallback to offer.
    """
    run_date = run_date or _utc_today()
    sweep_uid = sweep_uid_for(institution_uid)
    rows: list[dict[str, Any]] = []
    institution = response.institution
    if isinstance(response, ConsolidatedInstitutionResponseV27):
        data = _v27_storage(response, storage)
        inst_cells = _v27_institution_cells(response, data)
        for activity in response.activities:
            provenance = ValidationProvenance(
                global_row_id=_activity_global_row_id(run_id, institution.institution_id, activity.activity_id),
                run_id=run_id, run_model=run_model, run_tool=run_tool, run_date=run_date,
                institution_uid=institution_uid, sweep_uid=sweep_uid,
            )
            values = data["activities"][activity.activity_id]["values"]
            base = {**provenance.model_dump(), **inst_cells, "activity_id": activity.activity_id,
                    **retired_legacy_cells(_V25_ONLY["activities"], values)}
            rows.append(storage.row("activities", activity.activity_id, base, run_id=run_id,
                                    institution_uid=institution_uid))
        return rows
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
        base = pa.to_csv_dict()
        rows.append(storage.row("activities", activity.activity_id, base, run_id=run_id, institution_uid=institution_uid)
                    if storage is not None else legacy_row("activities", base, storage_metadata))
    return rows


def build_source_rows(
    response: AnyValidateResponse,
    *,
    run_id: str,
    run_model: str,
    institution_uid: str,
    run_tool: str = DEFAULT_RUN_TOOL_SOURCE,
    run_date: str | None = None,
    salvaged_by_source: dict[tuple[str, str], str] | None = None,
    storage: StorageEnvelope | None = None,
    storage_metadata: dict[str, Any] | None = None,
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
    if isinstance(response, ConsolidatedInstitutionResponseV27):
        data = _v27_storage(response, storage)
        for source in response.sources:
            provenance = ValidationProvenance(
                global_row_id=_source_global_row_id(run_id, institution_id, source.source_id),
                run_id=run_id, run_model=run_model, run_tool=run_tool, run_date=run_date,
                institution_uid=institution_uid, sweep_uid=sweep_uid,
            )
            values = data["sources"][source.source_id]["values"]
            base = {**provenance.model_dump(), "institution_id": institution_id,
                    "source_id": source.source_id, "activity_id": source.activity_id,
                    "source_url": values["core.source_url"],
                    "group_d_salvaged_fields": salvaged_by_source.get(
                        (institution_id, values["core.source_url"]), ""),
                    **retired_legacy_cells(_V25_ONLY["sources"], values)}
            rows.append(storage.row("sources", source.source_id, base, run_id=run_id,
                                    institution_uid=institution_uid))
        return rows
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
        base = ps.to_csv_dict()
        rows.append(storage.row("sources", source.source_id, base, run_id=run_id, institution_uid=institution_uid)
                    if storage is not None else legacy_row("sources", base, storage_metadata))
    return rows


def build_summary_row(
    response: AnyValidateResponse,
    *,
    run_id: str,
    institution_uid: str,
    run_date: str | None = None,
    storage: StorageEnvelope | None = None,
    storage_metadata: dict[str, Any] | None = None,
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
    if isinstance(response, ConsolidatedInstitutionResponseV27):
        return _v27_summary_row(response, storage, run_id=run_id, institution_uid=institution_uid,
                                run_date=run_date)
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

    missing = [c for c in SUMMARY_COLUMNS_V25 if c not in row]
    if missing:
        raise RuntimeError(f"summary row missing required columns: {missing}")
    return (storage.row("summary", None, row, run_id=run_id, institution_uid=institution_uid)
            if storage is not None else legacy_row("summary", row, storage_metadata))


# ---------------------------------------------------------------------------
# v2.7 rows: identity/keys from 6_validate.json, every value from 6_storage.json
# ---------------------------------------------------------------------------

_IDENTITY_COLUMNS = ("institution_id", "institution_name", "country", "branch_of_government",
                     "level_of_government", "institution_search_languages")


def _v25_only(table: str, legacy: list[str]) -> tuple[str, ...]:
    from g3o.common.storage import table_fields

    mapped = {f["column_or_member"] for f in table_fields(table).values()}
    return tuple(c for c in legacy if c not in mapped)


_V25_ONLY = {"activities": _v25_only("activities", ACTIVITY_COLUMNS_V25),
             "sources": _v25_only("sources", ACTIVITY_SOURCE_COLUMNS_V25)}


def _v27_storage(response: ConsolidatedInstitutionResponseV27, storage: StorageEnvelope | None) -> dict[str, Any]:
    if storage is None:
        raise ValueError(f"{response.institution.institution_id}: v2.7 rows are written only from 6_storage.json")
    data = storage.data
    check_storage_binding(response, data)
    return data


def _v27_institution_cells(response: ConsolidatedInstitutionResponseV27, data: dict[str, Any]) -> dict[str, Any]:
    """Identity from the response; the institution values from storage ``summary``."""
    summary = data["summary"]["values"]
    return {**{c: getattr(response.institution, c) for c in _IDENTITY_COLUMNS},
            "has_genai_activity": summary["core.has_genai_activity"],
            "institution_summary": summary["core.institution_summary"]}


def _v27_summary_row(response: ConsolidatedInstitutionResponseV27, storage: StorageEnvelope | None, *,
                     run_id: str, institution_uid: str, run_date: str) -> dict[str, Any]:
    """Legacy summary columns for a v2.7 institution, computed from storage values.

    The counts and lists restate storage values by the legacy rules
    (:func:`build_summary_row`); ``vendors_found`` stays empty because the
    retired ``vendor`` has no v2.7 value and no signed fill.
    """
    data = _v27_storage(response, storage)
    acts = [data["activities"][a.activity_id]["values"] for a in response.activities]
    srcs = [data["sources"][s.source_id]["values"] for s in response.sources]
    cred = {"high": 0, "medium": 0, "low": 0}
    for s in srcs:
        if s["core.source_credibility"] in cred:
            cred[s["core.source_credibility"]] += 1
    flags = sorted({f for a in acts for f in list_members(a["core.uncertainty_flags"]) if f != "none"})
    best, rank = "_NA_", 0
    for a in acts:
        if _CONFIDENCE_ORDER.get(a["core.confidence"], 0) > rank:
            best, rank = a["core.confidence"], _CONFIDENCE_ORDER[a["core.confidence"]]
    row = {
        "institution_uid": institution_uid,
        **_v27_institution_cells(response, data),
        "run_id": run_id,
        "run_date": run_date,
        "n_pages_extracted": response.consolidation_metadata.n_input_pages,
        "n_activities": len(acts),
        "n_sources": len(srcs),
        "n_high_credibility_sources": cred["high"],
        "n_medium_credibility_sources": cred["medium"],
        "n_low_credibility_sources": cred["low"],
        "activities_found": _pipe_join(a["core.activity_name"] for a in acts),
        "tools_found": _pipe_join(sorted({t for a in acts for t in list_members(a["core.tool_name"])
                                          if t != "unknown"})),
        "vendors_found": None,
        "best_confidence": best,
        "consolidated_uncertainty_flags": ";".join(flags) if flags else "none",
    }
    missing = [c for c in SUMMARY_COLUMNS_V25 if c not in row]
    if missing:
        raise RuntimeError(f"summary row missing required columns: {missing}")
    assert storage is not None
    return storage.row("summary", None, row, run_id=run_id, institution_uid=institution_uid)


# ---------------------------------------------------------------------------
# CSV writers
# ---------------------------------------------------------------------------


def _strip_nul(rows: list[dict[str, Any]], *, path: Path) -> list[dict[str, Any]]:
    """Remove NUL (0x00) from string values, loudly. Returns rows unchanged if clean.

    PostgreSQL text columns cannot hold a NUL byte, and the component that
    discovers that is the *loader*, three stages downstream. Measured 2026-08-24:
    a single NUL in **5 of 3,633** source rows aborted the ingest of a
    1,000-institution run with ``psycopg.DataError: PostgreSQL text fields cannot
    contain NUL (0x00) bytes`` — after institutions and findings had already been
    staged. The one-long-transaction design rolled it all back, so nothing partial
    landed, but the run had to be re-persisted and re-ingested.

    NUL is not data. It cannot occur in valid text content: it arrives from
    scraped PDFs and from HTML served under a mislabelled encoding, and it rides
    through Stage 4 → Stage 5 → here inside ``source_snippet`` and
    ``source_title``. Removing it is lossless in the only sense that matters —
    no character is lost, only a byte no text pipeline can represent.

    Stripped at the CSV boundary rather than at scrape time on purpose: this is
    the single choke point every Stage-7 table passes through, so one guard covers
    every column, including ones added later. A scrape-time strip would be better
    hygiene and is worth doing as well, but it would not protect a field
    introduced after it.

    The count is logged rather than silent: this mutates a published artifact, and
    an artifact that differs from what the model emitted must say so.
    """
    n_values = 0
    n_bytes = 0
    fields: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        new_row = row
        for key, value in row.items():
            if isinstance(value, str) and "\x00" in value:
                if new_row is row:
                    new_row = dict(row)
                n_values += 1
                n_bytes += value.count("\x00")
                fields.add(key)
                new_row[key] = value.replace("\x00", "")
        cleaned.append(new_row)
    if n_values:
        logger.warning(
            "%s: stripped %d NUL byte(s) from %d value(s) across field(s) %s — "
            "NUL cannot be stored in a PostgreSQL text column and is not valid "
            "text content; it originates in scraped PDF/HTML upstream",
            path.name, n_bytes, n_values, ", ".join(sorted(fields)),
        )
    return cleaned


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> int:
    """Write ``rows`` to ``path`` with header ``columns``. Returns row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if row.get("codebook_release") == "2.7" and any(isinstance(v, str) and "\x00" in v for v in row.values()):
            raise ValueError("2.7 storage cannot alter NUL-bearing text after provenance hashing")
    rows = _strip_nul(rows, path=path)
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
    skip_integrity_check: bool = False,
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
        skip_integrity_check: bypass post-persist FK validation (escape hatch).
        When False (default), validates all FK constraints after writing. Note:
        ``check_metadata=False`` is used during write for performance; use the
        ``validate-integrity`` CLI command for full metadata validation.

    Returns:
        Summary dict with output paths and row counts.

    Raises:
        FileExistsError: if ``overwrite=False`` and any CSV already exists.
        ValidationError: if any ``6_validate.json`` fails schema validation.
        IntegrityError: if post-persist FK validation fails (when ``skip_integrity_check=False``).
            Import from ``g3o.persist.integrity.IntegrityError`` or ``g3o.persist.IntegrityError``.
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

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    storage_metadata = manifest.get("storage_contract", {})
    if storage_metadata and not isinstance(storage_metadata, dict):
        raise ValueError("storage_contract must be explicit metadata")
    is_27 = storage_metadata.get("codebook_release") == "2.7"
    held: list[str] | None = [] if is_27 else None  # 2.7: an unreadable storage holds that institution
    loaded, failures = load_consolidated_outputs(run_dir, held=held)
    if failures and is_27:
        raise ValueError("2.7 output cannot silently omit failed institution payloads")
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
                storage=li.storage,
                storage_metadata=storage_metadata,
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
                storage=li.storage,
                storage_metadata=storage_metadata,
            )
        )
        summary_rows.append(
            build_summary_row(
                li.response,
                run_id=run_id,
                institution_uid=li.institution_uid,
                run_date=run_date,
                storage=li.storage,
                storage_metadata=storage_metadata,
            )
        )

    n_activities = _write_csv(activities_path, ACTIVITY_COLUMNS, activity_rows)
    n_sources = _write_csv(sources_path, ACTIVITY_SOURCE_COLUMNS, source_rows)
    n_summary = _write_csv(summary_path, SUMMARY_COLUMNS, summary_rows)

    # Post-persist referential integrity validation (Phase 1 of FK integrity plan).
    if skip_integrity_check:
        integrity_report = None
    else:
        integrity_report = validate_run_csvs(run_dir, version=version, check_metadata=False)
        if not integrity_report.is_valid:
            logger.error(
                "Stage 7: integrity validation failed after CSV write: %s",
                integrity_report.summary(),
            )
            raise IntegrityError(integrity_report)
        logger.info("Stage 7: integrity validation passed: %s", integrity_report.summary())
        if integrity_report.warnings:
            for w in integrity_report.warnings:
                logger.warning("Stage 7: integrity warning: %s", w)

    return {
        "run_dir": str(run_dir),
        "run_id": run_id,
        "version": version,
        "n_institutions": len(loaded),
        "n_load_failures": len(failures),
        "load_failures": failures,
        "held_institutions": held or [],
        "integrity": (
            {
                "is_valid": integrity_report.is_valid,
                "n_violations": len(integrity_report.violations),
                "n_warnings": len(integrity_report.warnings),
            }
            if integrity_report is not None
            else None
        ),
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
