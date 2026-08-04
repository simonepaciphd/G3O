"""Stage 6 driver — per-institution consolidation orchestrator.

Walks ``runs/<run_id>/<inst>/extract/*.json`` for each institution in a run,
flattens the Stage 5 ``ContractRow`` outputs into a single per-institution
input list, submits one consolidation job per institution (chunked into
size-capped OpenAI Batch API batches, Session F.1 2026-06-10), polls to
terminal state, parses the results, and persists
``runs/<run_id>/<inst>/6_validate.json``.

The single owner of OpenAI Batch API access remains
``g3o.common.batch_client``; this module is a thin wrapper around it.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.batch_client import (
    DEFAULT_COMPLETION_WINDOW,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    BatchHandle,
    BatchJob,
    BatchResult,
    BatchStatus,
    fetch_results,
    poll_batch,
    submit_batch,
)
from g3o.common.contract import (
    BatchResponse,
    ConsolidatedInstitutionResponse,
    ContractRow,
)
from g3o.common.run_state import (
    done_path,
    is_done,
    iter_chunks,
    load_state,
    mark_done,
    run_chunked_stage,
)
from g3o.common.timing import llm_stage_timer
from g3o.extract.salvage import (
    REASON_FLAGS_SALVAGED,
    UncertaintyFlagsSalvage,
    salvage_uncertainty_flags_na,
)
from g3o.validate.client import RESPONSE_FORMAT, build_consolidate_job

logger = logging.getLogger(__name__)


def make_consolidate_custom_id(institution_id: str) -> str:
    """Stage 6 ``custom_id`` is just the ``institution_id`` (one job per institution)."""
    if not institution_id:
        raise ValueError("institution_id is required to build a Stage 6 custom_id")
    return institution_id


def build_consolidate_jobs(
    per_institution_inputs: Iterable[
        tuple[dict[str, Any], list[dict[str, Any]], int]
    ],
    *,
    model_label: str | None = None,
    notes: str = "none",
) -> list[BatchJob]:
    """Build one Stage 6 ``BatchJob`` per institution.

    ``per_institution_inputs`` yields ``(institution_row, input_rows, n_input_pages)``
    tuples, where ``input_rows`` is the flattened list of Stage 5 ContractRow
    dicts for that institution and ``n_input_pages`` is the count of distinct
    source pages those rows came from.
    """
    jobs: list[BatchJob] = []
    for institution_row, input_rows, n_input_pages in per_institution_inputs:
        institution_id = institution_row.get("institution_id", "")
        custom_id = make_consolidate_custom_id(institution_id)
        jobs.append(
            build_consolidate_job(
                institution_row,
                input_rows,
                custom_id=custom_id,
                n_input_pages=n_input_pages,
                model_label=model_label,
                notes=notes,
            )
        )
    return jobs


def submit_consolidate_batch(
    jobs: list[BatchJob],
    *,
    model: str = DEFAULT_MODEL,
    completion_window: str = DEFAULT_COMPLETION_WINDOW,
    metadata: dict[str, Any] | None = None,
    client: Any | None = None,
) -> BatchHandle:
    """Submit a Stage 6 batch via the single-owner OpenAI client.

    Convenience wrapper for standalone use. ``run_consolidate`` does not
    route through it — :func:`g3o.common.run_state.run_chunked_stage`
    submits chunked batches with full ``{g3o_run_id, g3o_stage, g3o_chunk}``
    metadata; this wrapper tags only ``g3o_stage`` (same key convention) and
    its batches are never adopted by reconciliation.
    """
    base_metadata = {"g3o_stage": "validate"}
    if metadata:
        base_metadata.update(metadata)
    return submit_batch(
        jobs,
        model=model,
        response_format=RESPONSE_FORMAT,
        completion_window=completion_window,
        endpoint=DEFAULT_ENDPOINT,
        metadata=base_metadata,
        client=client,
    )


def poll_consolidate_batch(batch_id: str, *, client: Any | None = None) -> BatchStatus:
    return poll_batch(batch_id, client=client)


def fetch_consolidate_results(
    batch_id: str,
    *,
    client: Any | None = None,
    status: BatchStatus | None = None,
) -> Iterator[BatchResult]:
    return fetch_results(batch_id, client=client, status=status)


def parse_consolidate_result(
    result: BatchResult,
    *,
    salvage_sink: list[UncertaintyFlagsSalvage] | None = None,
) -> ConsolidatedInstitutionResponse:
    """Parse a Stage 6 ``BatchResult`` into a validated ``ConsolidatedInstitutionResponse``.

    ``uncertainty_flags`` ``_NA_`` salvage runs before validation, for the same
    reason it does at Stage 5: ``ConsolidatedActivity._validate_uncertainty_flags``
    is byte-identical to the Stage 5 rule, and ``model_validate`` is atomic over
    the institution, so one activity carrying the illegal literal would drop the
    whole consolidation. See ``g3o.extract.salvage`` for the reasoning (the module
    is shared rather than duplicated; ``g3o.persist.writer`` already imports its
    reason codes across the same boundary).

    Args:
        salvage_sink: if provided, one ``UncertaintyFlagsSalvage`` per repaired
            activity is appended. Populated before validation, so it is available
            to the caller even when this call raises.

    Raises:
        RuntimeError: if the underlying API call failed or returned no content.
        pydantic.ValidationError: on schema / cross-row validation failure.
    """
    if not result.success:
        raise RuntimeError(
            f"Stage 6 batch result {result.custom_id!r} failed: {result.error}"
        )
    content = result.parsed_content
    if not content:
        raise RuntimeError(
            f"Stage 6 batch result {result.custom_id!r}: empty assistant content"
        )
    payload = json.loads(content)
    if isinstance(payload, dict):
        events = salvage_uncertainty_flags_na(payload.get("activities"))
        if salvage_sink is not None:
            salvage_sink.extend(events)
    return ConsolidatedInstitutionResponse.model_validate(payload)


# ---------------------------------------------------------------------------
# Run-directory I/O
# ---------------------------------------------------------------------------


def load_extract_outputs(institution_dir: Path) -> tuple[list[ContractRow], int]:
    """Load all Stage 5 extract outputs for one institution.

    Walks ``institution_dir/extract/*.json`` (each file holds one validated
    ``BatchResponse``), flattens the ``data`` arrays into a single list of
    ``ContractRow`` objects, and returns the count of distinct source pages.

    Returns:
        (rows, n_pages) where ``rows`` is the concatenated list and
        ``n_pages`` is the count of extract JSON files that produced rows.
    """
    extract_dir = institution_dir / "extract"
    if not extract_dir.exists():
        return [], 0
    rows: list[ContractRow] = []
    n_pages = 0
    for path in sorted(extract_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        response = BatchResponse.model_validate(payload)
        if not response.data:
            continue
        rows.extend(response.data)
        n_pages += 1
    return rows, n_pages


def assemble_per_institution_inputs(
    run_dir: Path, institution_ids: Iterable[str]
) -> list[tuple[dict[str, Any], list[dict[str, Any]], int]]:
    """For each institution_id, load its row + Stage 5 outputs.

    Skips institutions with zero Stage 5 rows (nothing to consolidate). Logs a
    warning and continues; the caller decides whether a missing institution
    is fatal.
    """
    out: list[tuple[dict[str, Any], list[dict[str, Any]], int]] = []
    for inst_id in institution_ids:
        institution_dir = run_dir / inst_id
        institution_path = institution_dir / "institution.json"
        if not institution_path.exists():
            logger.warning(
                "Stage 6: institution.json missing for %s; skipping", inst_id
            )
            continue
        institution_row = json.loads(institution_path.read_text(encoding="utf-8"))
        rows, n_pages = load_extract_outputs(institution_dir)
        if not rows:
            logger.warning(
                "Stage 6: no Stage 5 rows for %s; skipping consolidation", inst_id
            )
            continue
        # Pydantic models are not JSON-serializable per se; emit as dicts.
        row_dicts = [r.model_dump() for r in rows]
        out.append((institution_row, row_dicts, n_pages))
    return out


def write_consolidated_output(
    run_dir: Path,
    institution_id: str,
    response: ConsolidatedInstitutionResponse,
) -> Path:
    """Persist ``runs/<run_id>/<inst>/6_validate.json``."""
    institution_dir = run_dir / institution_id
    institution_dir.mkdir(parents=True, exist_ok=True)
    out_path = institution_dir / "6_validate.json"
    out_path.write_text(
        json.dumps(response.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# End-to-end orchestrator
# ---------------------------------------------------------------------------


def _count_existing_validates(run_dir: Path, institution_ids: Iterable[str]) -> int:
    n = 0
    for inst_id in institution_ids:
        if (run_dir / inst_id / "6_validate.json").exists():
            n += 1
    return n


def run_consolidate(
    run_dir: Path,
    *,
    institution_ids: Iterable[str] | None = None,
    model: str = DEFAULT_MODEL,
    poll_interval: int = 60,
    max_wait: int = 25 * 60 * 60,
    notes: str = "none",
    client: Any | None = None,
) -> dict[str, Any]:
    """End-to-end Stage 6 driver for one run directory.

    Reads ``manifest.json`` if ``institution_ids`` is None, assembles per-
    institution inputs, submits size-capped batch chunks, blocks until
    terminal, persists each ``6_validate.json``, and returns a summary.

    Resume (Session E, 2026-05-09; chunked Session F.1, 2026-06-10):
      - ``.done/validate.json`` present → reconstruct count from disk; skip.
      - Otherwise jobs are rebuilt deterministically and handed to
        :func:`g3o.common.run_state.run_chunked_stage`, which owns chunking,
        metadata reconciliation, polling, and resume.
      - Failed/cancelled/expired terminal → raise; no auto-resubmit (Q3=d).

    The summary's ``batch_ids`` lists every chunk's batch id in chunk order
    (Session F.1 — replaces the single-batch ``batch_id`` key).
    """
    stage = "validate"
    if institution_ids is None:
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"manifest.json not found at {manifest_path}; "
                "supply institution_ids explicitly"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        institution_ids = manifest.get("institutions", [])
    institution_ids = list(institution_ids)
    run_id = _manifest_run_id(run_dir)

    if is_done(run_dir, stage):
        logger.info("Stage 6: .done marker present — skipping (resume from disk)")
        return {
            "run_dir": str(run_dir),
            "n_institutions": len(institution_ids),
            "n_consolidated": _count_existing_validates(run_dir, institution_ids),
            "n_failed": 0,
            "batch_ids": None,
            "skipped": True,
        }

    inputs = assemble_per_institution_inputs(run_dir, institution_ids)
    if not inputs and load_state(run_dir, stage) is None:
        mark_done(run_dir, stage, no_batch=True)
        return {
            "run_dir": str(run_dir),
            "n_institutions": 0,
            "n_consolidated": 0,
            "n_failed": 0,
            "batch_ids": None,
        }
    jobs = build_consolidate_jobs(inputs, model_label=model, notes=notes)

    n_failed = 0

    def _persist(results: Iterator[BatchResult]) -> None:
        nonlocal n_failed
        for result in results:
            flags_salvaged: list[UncertaintyFlagsSalvage] = []
            try:
                response = parse_consolidate_result(
                    result, salvage_sink=flags_salvaged
                )
            except Exception as exc:
                logger.warning(
                    "Stage 6 parse failed for %s: %s", result.custom_id, exc
                )
                attrition.record(
                    run_dir, institution_id=result.custom_id, stage=stage,
                    reason="parse_failed", detail=str(exc),
                )
                n_failed += 1
                continue
            # An illegal whole-value `uncertainty_flags` of `_NA_` was rewritten to
            # the contract's `none` and the consolidation preserved. Recorded on the
            # success path only, mirroring Stage 5: a consolidation that still
            # failed is reported by its actual failure, not as a salvage that did
            # not save it.
            if flags_salvaged:
                refs = sorted(s.ref for s in flags_salvaged)
                attrition.record(
                    run_dir, institution_id=result.custom_id, stage=stage,
                    reason=REASON_FLAGS_SALVAGED, detail=f"activities={refs}",
                )
            write_consolidated_output(run_dir, result.custom_id, response)

    # custom_id == institution_id for this stage (make_consolidate_custom_id),
    # so the identity fallback in llm_stage_timer needs no explicit mapping.
    with llm_stage_timer(run_dir, stage, {}):
        run_chunked_stage(
            run_dir, stage, jobs,
            run_id=run_id, model=model,
            poll_interval=poll_interval, max_wait=max_wait,
            process_chunk_results=_persist,
            client=client,
        )

    done_payload = json.loads(
        done_path(run_dir, stage).read_text(encoding="utf-8")
    )
    batch_ids = [entry["batch_id"] for _, entry in iter_chunks(done_payload)]
    return {
        "run_dir": str(run_dir),
        "n_institutions": len(jobs),
        "n_consolidated": _count_existing_validates(run_dir, institution_ids),
        "n_failed": n_failed,
        "batch_ids": batch_ids,
    }


def _manifest_run_id(run_dir: Path) -> str:
    """Resolve the run_id for batch metadata: manifest first, dirname fallback.

    ``run_dir`` is ``runs/<run_id>/`` by construction, so the fallback only
    differs when ``run_consolidate`` is pointed at a hand-built directory
    with no manifest — still a stable, unique-enough reconciliation key.
    """
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_id = manifest.get("run_id")
        if run_id:
            return str(run_id)
    return run_dir.name


__all__ = [
    "assemble_per_institution_inputs",
    "build_consolidate_jobs",
    "fetch_consolidate_results",
    "load_extract_outputs",
    "make_consolidate_custom_id",
    "parse_consolidate_result",
    "poll_consolidate_batch",
    "run_consolidate",
    "submit_consolidate_batch",
    "write_consolidated_output",
]
