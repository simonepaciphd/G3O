"""Stage 6 runner — per-institution LLM consolidation.

Routes to jev (TypeSafe decision model) when the model id starts with
``jev-``; otherwise routes to the OpenAI Batch API path. See
jev-integration-plan.md §4 for the design.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from g3o.common.credentials import ResolvedCredentials
from g3o.run.presweep.records import synth_institution_id


def _is_jev_model(model: str) -> bool:
    """True if ``model`` is a TypeSafe jev model id."""
    return model.startswith("jev-")


def _run_validate_jev(
    run_dir: Path,
    sample: list[dict[str, Any]],
    *,
    model: str,
    credentials: ResolvedCredentials,
    cost_check_callback: Callable[[str, dict[str, int]], bool] | None = None,
) -> dict[str, Any]:
    """Stage 6 — per-institution consolidation via jev decision model.

    Converts the consolidation task into jev typed questions (Noul for activity
    dedup, Choice for conflict resolution and summary selection), drives them
    synchronously, and assembles the ConsolidatedInstitutionResponse with
    deterministic bookkeeping. See jev-integration-plan.md §4 for the design.
    """
    from g3o.validate.consolidate import (
        assemble_per_institution_inputs,
        load_extract_outputs,
        write_consolidated_output,
    )
    from g3o.validate.jev_validate import (
        build_validate_questions,
        build_validate_state,
        parse_validate_result,
    )
    from g3o.common.jev_client import ask, client_from_credentials
    from g3o.common.paths import institution_dir
    from g3o.common.run_state import is_done, mark_done
    import json
    import logging

    logger = logging.getLogger(__name__)

    stage = "validate"
    if is_done(run_dir, stage):
        logger.info("Stage 6: .done marker present — skipping (resume from disk)")
        return {}

    # Load all institution inputs
    institution_ids = [synth_institution_id(row) for row in sample]
    per_inst_inputs = assemble_per_institution_inputs(run_dir, institution_ids)

    client = client_from_credentials(credentials, model=model)

    results: dict[str, Any] = {}
    n_success = 0
    n_failed = 0
    n_skipped = 0
    total_input_tokens = 0
    total_output_tokens = 0

    for institution_row, input_rows, n_input_pages in per_inst_inputs:
        institution_id = institution_row.get("institution_id", "")
        inst_dir = institution_dir(run_dir, institution_id)

        # Resume: skip if artifact already exists
        artifact_path = inst_dir / "6_validate.json"
        if artifact_path.exists():
            n_skipped += 1
            continue

        try:
            # Build state and questions
            state = build_validate_state(institution_row, input_rows, n_input_pages)
            questions = build_validate_questions(input_rows)

            # Call jev API
            result = ask(state, questions, client=client, model=model)

            # Parse and assemble response
            jev_result = parse_validate_result(
                result, institution_row, input_rows, n_input_pages
            )

            # Write artifact
            write_consolidated_output(run_dir, institution_id, jev_result.response)

            results[institution_id] = jev_result.response.model_dump()
            n_success += 1
            total_input_tokens += result.input_tokens
            total_output_tokens += result.output_tokens

            # Cost check callback
            if cost_check_callback is not None:
                usage = {
                    "prompt_tokens": result.input_tokens,
                    "completion_tokens": result.output_tokens,
                    "cached_tokens": 0,
                }
                should_continue = cost_check_callback(stage, usage)
                if not should_continue:
                    logger.warning(
                        "Stage 6 jev: cost check callback returned False — stopping"
                    )
                    break

        except Exception as exc:
            logger.warning(
                "Stage 6 jev: failed for %s: %s", institution_id, exc
            )
            n_failed += 1

    logger.info(
        "Stage 6 jev: %d institutions, %d success, %d failed, %d skipped, "
        "%d input tokens",
        len(per_inst_inputs),
        n_success,
        n_failed,
        n_skipped,
        total_input_tokens,
    )

    if n_success > 0 or n_skipped > 0:
        mark_done(run_dir, stage)

    return results


def _run_validate(
    run_dir: Path,
    sample: list[dict[str, Any]],
    *,
    model: str,
    poll_interval: int,
    max_wait: int,
    cost_check_callback: Callable[[str, dict[str, int]], bool] | None = None,
    credentials: ResolvedCredentials | None = None,
    telemetry: Any | None = None,
) -> dict[str, Any]:
    """Stage 6 — per-institution LLM consolidation (Session E fold, Q8=ii).

    Thin wrapper around :func:`g3o.validate.consolidate.run_consolidate`. The
    consolidate driver is itself state-aware (same ``_state/{stage}.json`` +
    ``.done/{stage}.json`` machinery as Stages 2/3/5), so resume semantics are
    uniform across all four LLM stages.
    """
    # ── jev routing ──────────────────────────────────────────────────────────
    # When the model is jev, route to the jev path instead of the Batch API path.
    if _is_jev_model(model):
        if credentials is None:
            raise RuntimeError("Stage 6 jev: credentials are required")
        return _run_validate_jev(
            run_dir, sample,
            model=model, credentials=credentials,
            cost_check_callback=cost_check_callback,
        )
    # ── end jev routing ──────────────────────────────────────────────────────

    from g3o.validate.consolidate import run_consolidate

    institution_ids = [synth_institution_id(row) for row in sample]
    return run_consolidate(
        run_dir,
        institution_ids=institution_ids,
        model=model,
        poll_interval=poll_interval,
        max_wait=max_wait,
        cost_check_callback=cost_check_callback,
        credentials=credentials,
        telemetry=telemetry,
    )
