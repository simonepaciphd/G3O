"""v2.7 jev pass-1 page coding stage (T-021). Orchestrator wiring is T-030's.

For each stored page, :func:`g3o.classify.jev_page_code.code_page` runs the
pass-1 rounds (several requests per page: rounds x parts), so this stage has
its own driver rather than :func:`g3o.run.presweep.jev_stage_runner.run_jev_stage`
(one request per institution). Requests go through :func:`g3o.common.jev_client.ask`.

- Artifact: ``<inst>/page_code_v27/<url_hash>.json`` (the
  :class:`~g3o.classify.jev_page_code.PageCodeResult`, provisional combination).
  Resume = artifact presence.
- A page that cannot be coded (no verdict: verdict request failed, no request
  id, part over the limit past the halving depth) writes no artifact and is
  recorded in the attrition ledger with the reason; a re-run retries it.
- Part-level failures inside a coded page are recorded once per page as
  ``jev_part_failures`` (detail lists them); the artifact carries them too.
- :class:`JevAccountError` stops the stage (every later request would fail the
  same way); so does :class:`BudgetExceededError` or a ``False`` from
  ``cost_check_callback(stage, usage)``, called after every response.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.classify.jev_page_code import (
    AskFn,
    PageCoderConfig,
    PageFailed,
    PageInput,
    code_page,
)
from g3o.common import attrition
from g3o.common.artifact_io import artifact_exists, write_artifact
from g3o.common.cost_monitor import BudgetExceededError
from g3o.common.jev_client import JevAccountError, JevResult
from g3o.common.paths import institution_dir
from g3o.common.timing import record_stage_timing
from g3o.extract.batch import url_hash

logger = logging.getLogger(__name__)

STAGE = "page_code_v27"
ARTIFACT_DIR = "page_code_v27"
DEFAULT_CONCURRENCY = 8
PART_FAILURES = "jev_part_failures"


class StageStopped(RuntimeError):
    """The cost check returned False."""


def artifact_path(run_dir: Path, institution_id: str, url: str) -> Path:
    return institution_dir(run_dir, institution_id) / ARTIFACT_DIR / f"{url_hash(url)}.json"


def jev_ask(client: Any) -> AskFn:
    """Adapt :func:`g3o.common.jev_client.ask` to the page coder's ``ask_fn``."""
    import typesafe_sdk as ts

    from g3o.common.jev_client import ask

    def _ask(state: dict[str, Any], questions: dict[str, dict[str, Any]]) -> JevResult:
        return ask(state, {k: ts.Choice(**v) for k, v in questions.items()}, client=client)

    return _ask


@dataclass
class PageCodeMetrics:
    n_pages: int = 0
    n_skipped: int = 0
    n_coded: int = 0
    n_not_assessable: int = 0
    n_failed: int = 0
    n_requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stopped_early: bool = False


def run_page_code_stage(
    run_dir: Path,
    pages: Sequence[PageInput],
    *,
    ask_fn: AskFn,
    config: PageCoderConfig,
    concurrency: int = DEFAULT_CONCURRENCY,
    cost_check_callback: Callable[[str, dict[str, int]], bool] | None = None,
) -> PageCodeMetrics:
    ids = [p.page_id for p in pages]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate page_id in the page-code input")
    metrics = PageCodeMetrics(n_pages=len(pages))
    lock = threading.Lock()
    stop = threading.Event()

    def on_response(result: JevResult) -> None:
        with lock:
            metrics.n_requests += 1
            metrics.input_tokens += result.input_tokens
            metrics.output_tokens += result.output_tokens
        if cost_check_callback is not None and not cost_check_callback(
                STAGE, {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens}):
            stop.set()
            raise StageStopped("cost check callback returned False")

    def work(page: PageInput) -> None:
        if stop.is_set():
            return
        path = artifact_path(run_dir, page.institution_id, page.url)
        if artifact_exists(path):
            with lock:
                metrics.n_skipped += 1
            return
        try:
            result = code_page(page, ask_fn, config, on_response=on_response)
        except PageFailed as exc:
            attrition.record(run_dir, institution_id=page.institution_id, stage=STAGE,
                             reason=exc.reason, url=page.url, detail=exc.detail)
            with lock:
                metrics.n_failed += 1
            return
        write_artifact(path, result.to_json())
        if result.failures:
            attrition.record(run_dir, institution_id=page.institution_id, stage=STAGE,
                             reason=PART_FAILURES, url=page.url,
                             detail=json.dumps(list(result.failures), ensure_ascii=False))
        with lock:
            if result.status == "not_assessable":
                metrics.n_not_assessable += 1
            else:
                metrics.n_coded += 1

    windows: dict[str, list[tuple[float, float, str, str, str | None]]] = {}

    def timed_work(page: PageInput) -> None:
        if stop.is_set() or artifact_exists(artifact_path(run_dir, page.institution_id, page.url)):
            work(page)
            return  # resume must preserve the original timing
        start = time.monotonic()
        start_time = datetime.now(timezone.utc).isoformat()
        failure = None
        try:
            work(page)
            if not artifact_exists(artifact_path(run_dir, page.institution_id, page.url)):
                failure = "page coding did not produce an artifact"
        except BaseException as exc:
            failure = str(exc)
            raise
        finally:
            entry = (start, time.monotonic(), start_time,
                     datetime.now(timezone.utc).isoformat(), failure)
            with lock:
                windows.setdefault(page.institution_id, []).append(entry)

    error: BaseException | None = None
    try:
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
            futures = [ex.submit(timed_work, p) for p in pages]
            for f in futures:
                try:
                    f.result()
                except (JevAccountError, BudgetExceededError, StageStopped) as exc:
                    stop.set()
                    metrics.stopped_early = True
                    if error is None:
                        error = exc
    finally:
        # One write per institution: parallel pages cannot overwrite each other.
        for institution_id, entries in windows.items():
            first = min(entries, key=lambda e: e[0])
            last = max(entries, key=lambda e: e[1])
            failures = [e[4] for e in entries if e[4] is not None]
            record_stage_timing(
                run_dir, institution_id, STAGE, start_time=first[2], end_time=last[3],
                duration_seconds=last[1] - first[0], timing_type="per_institution",
                status="failed" if failures else "completed",
                error="; ".join(failures) if failures else None)
    if isinstance(error, (JevAccountError, BudgetExceededError)):
        raise error
    if metrics.stopped_early:
        logger.warning("page_code_v27: stopped by the cost check")
    return metrics


__all__ = ["ARTIFACT_DIR", "STAGE", "PageCodeMetrics", "artifact_path", "jev_ask", "run_page_code_stage"]
