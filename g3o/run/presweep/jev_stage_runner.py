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

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typesafe_sdk as ts

from g3o.common import attrition
from g3o.common.credentials import ResolvedCredentials
from g3o.common.jev_client import (
    JevResult,
    ask,
    client_from_credentials,
)
from g3o.common.paths import institution_dir

logger = logging.getLogger(__name__)


# Default concurrency for jev stages. Conservative; tune against 429s.
DEFAULT_JEV_CONCURRENCY = 20


@dataclass
class JevStageMetrics:
    """Metrics from a jev stage run."""

    n_institutions: int
    n_success: int
    n_failed: int
    n_skipped: int  # resume: artifact already exists
    total_input_tokens: int
    total_output_tokens: int


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
) -> JevStageMetrics:
    """Run a jev stage synchronously over a list of institutions.

    ``build_request`` takes an institution row and returns ``(state, questions)``
    for the jev API.

    ``process_result`` takes ``(institution_id, result, institution_row)`` and
    persists the result (writes artifact, updates output dict, etc.).

    ``artifact_filename`` is the per-institution artifact name. If the artifact
    already exists, the institution is skipped (resume).

    Returns metrics: n_institutions, n_success, n_failed, n_skipped, token usage.
    """
    metrics = JevStageMetrics(
        n_institutions=len(institutions),
        n_success=0,
        n_failed=0,
        n_skipped=0,
        total_input_tokens=0,
        total_output_tokens=0,
    )

    client = client_from_credentials(credentials, model=model)

    def _process_one(institution: dict[str, Any]) -> None:
        inst_id = institution.get("institution_id", "")
        if not inst_id:
            logger.warning("jev stage %s: institution row missing institution_id", stage)
            return

        # Resume: skip if artifact already exists.
        inst_dir = institution_dir(run_dir, inst_id)
        artifact_path = inst_dir / artifact_filename
        if artifact_path.exists():
            metrics.n_skipped += 1
            return

        try:
            state, questions = build_request(institution)
            result = ask(state, questions, client=client, model=model)
        except Exception as exc:
            logger.warning("jev stage %s: request failed for %s: %s", stage, inst_id, exc)
            attrition.record(
                run_dir,
                institution_id=inst_id,
                stage=stage,
                reason="jev_request_failed",
                detail=str(exc),
            )
            metrics.n_failed += 1
            return

        try:
            process_result(inst_id, result, institution)
            metrics.n_success += 1
            metrics.total_input_tokens += result.input_tokens
            metrics.total_output_tokens += result.output_tokens

            # Cost check callback (per-response).
            if cost_check_callback is not None:
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
                    # TODO: propagate stop signal to caller
        except Exception as exc:
            logger.warning("jev stage %s: result processing failed for %s: %s", stage, inst_id, exc)
            attrition.record(
                run_dir,
                institution_id=inst_id,
                stage=stage,
                reason="jev_result_processing_failed",
                detail=str(exc),
            )
            metrics.n_failed += 1

    # Bounded-concurrency ThreadPool.
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_process_one, inst): inst for inst in institutions}
        for future in as_completed(futures):
            # Exceptions are caught inside _process_one; this is just to surface
            # unexpected errors.
            try:
                future.result()
            except Exception as exc:
                logger.error("jev stage %s: unexpected error: %s", stage, exc)

    return metrics


__all__ = [
    "DEFAULT_JEV_CONCURRENCY",
    "JevStageMetrics",
    "run_jev_stage",
]
