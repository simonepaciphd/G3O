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
from g3o.common.timing import record_stage_timing
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
    import logging

    from g3o.common.cost_monitor import BudgetExceededError
    from g3o.common.jev_client import ask, client_from_credentials
    from g3o.common.paths import institution_dir
    from g3o.common.run_state import is_done, mark_done
    from g3o.validate.consolidate import (
        assemble_per_institution_inputs,
        write_consolidated_output,
    )
    from g3o.validate.jev_validate import (
        build_validate_questions,
        build_validate_state,
        parse_validate_result,
    )

    logger = logging.getLogger(__name__)

    stage = "validate"
    if is_done(run_dir, stage):
        logger.info("Stage 6: .done marker present — skipping (resume from disk)")
        return {}

    # Load all institution inputs
    institution_ids = [synth_institution_id(row) for row in sample]
    per_inst_inputs = assemble_per_institution_inputs(run_dir, institution_ids)

    client = client_from_credentials(credentials, model=model)

    n_success = 0
    n_failed = 0
    n_skipped = 0
    total_input_tokens = 0
    total_output_tokens = 0
    stopped_early = False

    for institution_row, input_rows, n_input_pages in per_inst_inputs:
        if stopped_early:
            break

        institution_id = institution_row.get("institution_id", "")
        inst_dir = institution_dir(run_dir, institution_id)

        # Resume: skip if artifact already exists
        artifact_path = inst_dir / "6_validate.json"
        if artifact_path.exists():
            n_skipped += 1
            continue

        import time
        from datetime import datetime, timezone
        start = time.time()
        start_time = datetime.fromtimestamp(start, tz=timezone.utc).isoformat()

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

            duration = time.time() - start
            end_time = datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat()
            # Blocker #2 fix: pass all required keyword arguments
            record_stage_timing(
                run_dir, institution_id, "validate",
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                status="success",
                timing_type="per_institution",
            )

            n_success += 1
            total_input_tokens += result.input_tokens
            total_output_tokens += result.output_tokens

        except Exception as exc:
            logger.warning(
                "Stage 6 jev: failed for %s: %s", institution_id, exc
            )
            n_failed += 1
            continue

        # Cost check callback — OUTSIDE the try/except so BudgetExceededError
        # propagates correctly (blocker #1 fix).
        if cost_check_callback is not None:
            try:
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
                    stopped_early = True
            except BudgetExceededError:
                # Re-raise budget errors so they propagate to the orchestrator
                stopped_early = True
                raise

    logger.info(
        "Stage 6 jev: %d institutions, %d success, %d failed, %d skipped, "
        "%d input tokens%s",
        len(per_inst_inputs),
        n_success,
        n_failed,
        n_skipped,
        total_input_tokens,
        " (stopped early)" if stopped_early else "",
    )

    # Blocker #1 fix: only mark_done when the loop completed without early stop.
    # A partially-run stage should NOT be marked done, or unprocessed institutions
    # would be permanently skipped on resume.
    if not stopped_early and (n_success > 0 or n_skipped > 0):
        mark_done(
            run_dir, stage, no_batch=True,
            usage={
                "prompt_tokens": total_input_tokens,
                "completion_tokens": total_output_tokens,
                "cached_tokens": 0,
            },
            n_jobs=n_success,
            model=model,
        )

    return {
        "run_dir": str(run_dir),
        "n_institutions": len(per_inst_inputs),
        "n_consolidated": n_success + n_skipped,
        "n_failed": n_failed,
        "batch_ids": [],  # jev is sync, no batch API
        "stopped_early": stopped_early,
    }


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
