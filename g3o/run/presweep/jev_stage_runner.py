"""Synchronous driver for jev stages (Stage 2, Stage 3).

Replaces ``run_chunked_stage``'s batch submit/poll machinery for jev stages
with a synchronous driver:

- Iterate institutions; bounded-concurrency requests (ThreadPool over the
  sync client; start conservative, e.g. 20–50 in flight, tune against 429s).

- Resume = artifact presence (skip institutions with an existing
  ``2_official_site.json`` / ``3_triage.json``), exactly the discovery/scrape
  idempotency model — strictly simpler than batch chunk-state.

- Budget breaker: cost check per response (or every N) against the ceiling —
  per-call rather than per-wave, which is the right place for a sync API.

- Attrition ledger reasons for the new failure modes
  (``jev_request_failed``, ``jev_low_confidence``, …).

- Throughput check: full universe 675k institutions at 1,200 req/min ≈ 9.4 h
  per stage — comparable to the 24h batch window; no ``max_wait`` semantics
  change beyond per-stage wiring.

See jev-integration-plan.md §3 for the full design.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.cost_monitor import BudgetExceededError
from g3o.common.credentials import ResolvedCredentials
from g3o.common.jev_client import (
    JevAccountError,
    JevResult,
    ask,
    client_from_credentials,
)
from g3o.common.paths import institution_dir
from g3o.common.timing import record_stage_timing

logger = logging.getLogger(__name__)


# Default concurrency for jev stages. Conservative; tune against 429s.
DEFAULT_JEV_CONCURRENCY = 20


@dataclass
class JevStageMetrics:
    """Metrics from a jev stage run."""

    n_institutions: int
    n_success: int = 0
    n_failed: int = 0
    n_skipped: int = 0  # resume: artifact already exists
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    stopped_early: bool = False  # budget or other early stop
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)


def run_jev_stage(
    run_dir: Path,
    stage: str,
    institutions: list[dict[str, Any]],
    build_request: Callable[[dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]],
    process_result: Callable[[str, JevResult, dict[str, Any]], None],
    *,
    credentials: ResolvedCredentials,
    model: str,
    concurrency: int = DEFAULT_JEV_CONCURRENCY,
    cost_check_callback: Callable[[str, dict[str, int]], bool] | None = None,
    artifact_filename: str = "jev_result.json",
    request_fallback: Callable[
        [dict[str, Any], Exception, Callable[[Any, Any], JevResult]], Any
    ] | None = None,
) -> JevStageMetrics:
    """Run a jev stage synchronously over a list of institutions.

    ``build_request`` takes an institution row and returns ``(state, questions)``
    for the jev API.

    ``process_result`` takes ``(institution_id, result, institution_row)`` and
    persists the result (writes artifact, updates output dict, etc.).

    ``artifact_filename`` is the per-institution artifact name. If the artifact
    already exists, the institution is skipped (resume).

    ``request_fallback`` (optional) is called with ``(institution_row, exc,
    send)`` when the request fails with a non-account error; ``send(state,
    questions)`` submits one more request through the same client. It returns
    a result object exposing ``input_tokens``/``output_tokens`` (handed to
    ``process_result`` in place of the failed result), or ``None`` to record
    the original failure as usual. An exception it raises is recorded as
    ``jev_request_failed``; if that exception carries ``partial_usage``
    ``(input_tokens, output_tokens)`` — requests that succeeded before it —
    those tokens still count toward the stage totals. Stage 6 uses this to
    split an over-long validate request (PI ruling E1=b, 2026-10-17).

    Returns metrics: n_institutions, n_success, n_failed, n_skipped, token usage.
    """
    metrics = JevStageMetrics(n_institutions=len(institutions))
    stop_event = threading.Event()

    client = client_from_credentials(credentials, model=model)

    def _process_one(institution: dict[str, Any]) -> None:
        # Check stop event before starting work
        if stop_event.is_set():
            return

        inst_id = institution.get("institution_id", "")
        if not inst_id:
            logger.warning("jev stage %s: institution row missing institution_id", stage)
            return

        # Resume: skip if artifact already exists.
        inst_dir = institution_dir(run_dir, inst_id)
        artifact_path = inst_dir / artifact_filename
        if artifact_path.exists():
            with metrics._lock:
                metrics.n_skipped += 1
            return

        import time
        from datetime import datetime, timezone
        start = time.time()
        start_time = datetime.fromtimestamp(start, tz=timezone.utc).isoformat()
        try:
            state, questions = build_request(institution)
            try:
                result = ask(state, questions, client=client, model=model)
            except JevAccountError:
                raise
            except Exception as exc:
                if request_fallback is None:
                    raise
                fallback_result = request_fallback(
                    institution,
                    exc,
                    lambda s, q: ask(s, q, client=client, model=model),
                )
                if fallback_result is None:
                    raise
                result = fallback_result
        except JevAccountError:
            # Every remaining request would fail the same way: stop the stage.
            stop_event.set()
            with metrics._lock:
                metrics.stopped_early = True
            raise
        except Exception as exc:
            logger.warning("jev stage %s: request failed for %s: %s", stage, inst_id, exc)
            attrition.record(
                run_dir,
                institution_id=inst_id,
                stage=stage,
                reason="jev_request_failed",
                detail=str(exc),
            )
            partial_in, partial_out = getattr(exc, "partial_usage", (0, 0))
            with metrics._lock:
                metrics.n_failed += 1
                metrics.total_input_tokens += partial_in
                metrics.total_output_tokens += partial_out
            return

        try:
            process_result(inst_id, result, institution)
            duration = time.time() - start
            end_time = datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat()
            record_stage_timing(
                run_dir, inst_id, stage,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                status="success",
                timing_type="per_institution",
            )
            with metrics._lock:
                metrics.n_success += 1
                metrics.total_input_tokens += result.input_tokens
                metrics.total_output_tokens += result.output_tokens
        except Exception as exc:
            logger.warning("jev stage %s: result processing failed for %s: %s", stage, inst_id, exc)
            attrition.record(
                run_dir,
                institution_id=inst_id,
                stage=stage,
                reason="jev_result_processing_failed",
                detail=str(exc),
            )
            with metrics._lock:
                metrics.n_failed += 1
            return

        # Cost check callback (per-response) — OUTSIDE the try/except so
        # BudgetExceededError propagates correctly (blocker #1 fix).
        if cost_check_callback is not None and not stop_event.is_set():
            try:
                usage = {
                    "prompt_tokens": result.input_tokens,
                    "completion_tokens": result.output_tokens,
                    "cached_tokens": 0,
                }
                should_continue = cost_check_callback(stage, usage)
                if not should_continue:
                    logger.warning(
                        "jev stage %s: cost check callback returned False — stopping",
                        stage,
                    )
                    stop_event.set()
                    with metrics._lock:
                        metrics.stopped_early = True
            except BudgetExceededError:
                # Re-raise budget errors so they propagate to the orchestrator
                stop_event.set()
                with metrics._lock:
                    metrics.stopped_early = True
                raise

    # Bounded-concurrency ThreadPool.
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(_process_one, inst): inst for inst in institutions}
            for future in as_completed(futures):
                # Exceptions are caught inside _process_one; this is just to surface
                # unexpected errors (including BudgetExceededError).
                try:
                    future.result()
                except (BudgetExceededError, JevAccountError):
                    # Re-raise budget and account errors immediately
                    raise
                except Exception as exc:
                    logger.error("jev stage %s: unexpected error: %s", stage, exc)
    except BudgetExceededError:
        # Propagate to caller
        raise

    return metrics


__all__ = [
    "DEFAULT_JEV_CONCURRENCY",
    "JevStageMetrics",
    "run_jev_stage",
]
