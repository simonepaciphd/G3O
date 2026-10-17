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
from g3o.run.presweep.jev_stage_runner import DEFAULT_JEV_CONCURRENCY, run_jev_stage
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
    concurrency: int = DEFAULT_JEV_CONCURRENCY,
) -> dict[str, Any]:
    """Stage 6 — per-institution consolidation via jev decision model.

    Converts the consolidation task into jev typed questions (Noul for activity
    dedup, Choice for conflict resolution and summary selection), drives them
    synchronously, and assembles the ConsolidatedInstitutionResponse with
    deterministic bookkeeping. See jev-integration-plan.md §4 for the design.
    """
    import logging
    import threading

    from g3o.common import attrition
    from g3o.common.jev_client import JevAccountError
    from g3o.common.run_state import is_done, mark_done
    from g3o.validate import jev_validate
    from g3o.validate.consolidate import (
        assemble_per_institution_inputs,
        write_consolidated_output,
    )
    from g3o.validate.jev_validate import (
        MAX_SPLIT_DEPTH,
        ChunkedJevResult,
        build_validate_questions,
        build_validate_state,
        chunk_input_rows,
        estimate_request_bytes,
        is_max_tokens_exceeded,
        parse_chunked_validate_result,
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

    inputs_by_id = {
        row.get("institution_id", ""): (row, input_rows, n_input_pages)
        for row, input_rows, n_input_pages in per_inst_inputs
    }

    def build_request(institution_row: dict[str, Any]) -> tuple[Any, Any]:
        _, input_rows, n_input_pages = inputs_by_id[institution_row["institution_id"]]
        state = build_validate_state(institution_row, input_rows, n_input_pages)
        return state, build_validate_questions(input_rows)

    split_lock = threading.Lock()
    n_oversize_split = 0

    def oversize_fallback(
        institution_row: dict[str, Any],
        exc: Exception,
        send: Callable[[Any, Any], Any],
    ) -> ChunkedJevResult | None:
        """PI ruling E1=b (2026-10-17): on a 400 max_tokens_exceeded, validate
        the institution in page-whole chunks and merge (see
        ``merge_chunk_responses``).

        The first split uses ``min(CHUNK_BUDGET_BYTES, full_estimate // 2)``,
        so an institution with 2+ pages always yields 2+ chunks even when its
        byte estimate is under the budget (bytes are only a proxy for tokens).
        A chunk that itself gets max_tokens_exceeded is re-split with half its
        own estimate as budget, recursively, to at most
        ``MAX_SPLIT_DEPTH`` split levels counting the first. A chunk that
        cannot be split further (one page, or the depth cap) fails the
        institution as today. Any other error, or a one-page institution,
        keeps today's failure path."""
        nonlocal n_oversize_split
        if not is_max_tokens_exceeded(exc):
            return None
        inst_id = institution_row["institution_id"]
        _, input_rows, n_input_pages = inputs_by_id[inst_id]
        full_bytes = estimate_request_bytes(
            build_validate_state(institution_row, input_rows, n_input_pages),
            build_validate_questions(input_rows),
        )
        chunks = chunk_input_rows(
            institution_row,
            input_rows,
            budget_bytes=min(jev_validate.CHUNK_BUDGET_BYTES, full_bytes // 2),
        )
        if len(chunks) < 2:
            return None
        with split_lock:
            n_oversize_split += 1
        done: list[tuple[Any, Any]] = []
        usage = [0, 0]
        max_depth = 1
        n_chunks = len(chunks)  # leaf chunks planned so far

        def run_chunk(chunk: Any, depth: int) -> None:
            nonlocal max_depth, n_chunks
            max_depth = max(max_depth, depth)
            state = build_validate_state(
                institution_row, chunk.input_rows, chunk.n_input_pages
            )
            try:
                res = send(state, build_validate_questions(chunk.input_rows))
            except JevAccountError:
                raise
            except Exception as chunk_exc:
                if (
                    is_max_tokens_exceeded(chunk_exc)
                    and depth < MAX_SPLIT_DEPTH
                    and chunk.n_input_pages >= 2
                ):
                    sub = chunk_input_rows(
                        institution_row,
                        chunk.input_rows,
                        budget_bytes=chunk.request_bytes // 2,
                    )
                    if len(sub) >= 2:
                        n_chunks += len(sub) - 1
                        for sub_chunk in sub:
                            run_chunk(sub_chunk, depth + 1)
                        return
                raise
            usage[0] += res.input_tokens
            usage[1] += res.output_tokens
            done.append((chunk, res))

        try:
            for chunk in chunks:
                run_chunk(chunk, 1)
        except Exception as chunk_exc:
            # Chunks already answered were still spent.
            chunk_exc.partial_usage = (usage[0], usage[1])  # type: ignore[attr-defined]
            raise
        finally:
            attrition.record(
                run_dir,
                institution_id=inst_id,
                stage=stage,
                reason="validate_oversize_split",
                detail=(
                    f"n_chunks={n_chunks}; depth={max_depth}; "
                    f"chunk_bytes={[c.request_bytes for c, _ in done]}"
                ),
            )
        return ChunkedJevResult(
            chunks=done,
            input_tokens=usage[0],
            output_tokens=usage[1],
            response_model=done[0][1].response_model,
            request_id=done[0][1].request_id,
        )

    def process_result(
        institution_id: str, result: Any, institution_row: dict[str, Any]
    ) -> None:
        _, input_rows, n_input_pages = inputs_by_id[institution_id]
        if isinstance(result, ChunkedJevResult):
            response = parse_chunked_validate_result(
                result, institution_row, n_input_pages, len(input_rows)
            )
            write_consolidated_output(run_dir, institution_id, response)
            return
        jev_result = parse_validate_result(
            result, institution_row, input_rows, n_input_pages
        )
        write_consolidated_output(run_dir, institution_id, jev_result.response)

    # Same bounded-concurrency driver as Stages 2/3: resume by artifact
    # presence, per-response cost check, JevAccountError and
    # BudgetExceededError propagate. Was a sequential loop until 2026-10-17.
    metrics = run_jev_stage(
        run_dir,
        stage,
        [row for row, _, _ in per_inst_inputs],
        build_request,
        process_result,
        credentials=credentials,
        model=model,
        concurrency=concurrency,
        cost_check_callback=cost_check_callback,
        artifact_filename="6_validate.json",
        request_fallback=oversize_fallback,
    )
    n_success = metrics.n_success
    n_failed = metrics.n_failed
    n_skipped = metrics.n_skipped
    total_input_tokens = metrics.total_input_tokens
    total_output_tokens = metrics.total_output_tokens
    stopped_early = metrics.stopped_early

    logger.info(
        "Stage 6 jev: %d institutions, %d success, %d failed, %d skipped, "
        "%d oversize-split, %d input tokens%s",
        len(per_inst_inputs),
        n_success,
        n_failed,
        n_skipped,
        n_oversize_split,
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
        "n_oversize_split": n_oversize_split,
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
