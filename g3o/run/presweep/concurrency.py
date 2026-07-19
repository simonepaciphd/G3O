"""Shared ThreadPoolExecutor driver for Stage 1a/1b/4 per-institution concurrency.

Single-owner helper (2026-07): every deterministic stage that parallelizes
institution-level work drives its ``ThreadPoolExecutor`` through
:func:`run_concurrent` so the failure-propagation contract stays identical
across Stages 1a, 1b, and 4. Stages 2/3/5/6 (OpenAI Batch API) are untouched
and do not use this module.

Failure semantics, chosen to match each stage's existing sequential behavior
as closely as concurrency allows: on the first worker exception, every
not-yet-started task is cancelled, every already-running task is allowed to
finish naturally (Python has no safe way to kill a thread mid network call),
and only the *first* exception raised is re-raised, after every task has
settled. The caller never sees a partial result dict on failure — same as
today's sequential loop, where the exception propagates before the loop's
local ``out`` is ever returned. Institutions that already wrote their
per-institution artifact before the failure keep that file; nothing is
deleted. The stage's ``mark_done`` is never reached when this raises, so the
next run's ``is_done``/skip-if-exists resume logic re-processes exactly the
institutions that never finished — unchanged from the sequential case, just
with a wider (bounded by ``max_workers``) in-flight window at crash time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from typing import TypeVar

_T = TypeVar("_T")
_R = TypeVar("_R")


def run_concurrent(
    items: Iterable[_T],
    worker: Callable[[_T], _R],
    *,
    max_workers: int,
) -> list[_R]:
    """Run ``worker(item)`` for every item, up to ``max_workers`` concurrently.

    Returns the non-``None`` results (order not meaningful; callers needing a
    per-institution key have ``worker`` return it, e.g. ``(inst_id, records)``,
    and index the results themselves). ``worker`` returning ``None`` is
    treated as "nothing to record for this item" (e.g. Stage 1b's Q2=a skip).

    On the first exception from any worker: cancels every not-yet-started
    future, drains every already-running one, then re-raises that first
    exception — no partial results are returned in that case (see module
    docstring for why this matches the sequential stages' existing contract).

    Cancellation is best-effort, not a guarantee: ``Future.cancel()`` only
    succeeds for a task a worker thread hasn't started yet, and there is no
    atomic "stop the world" the instant the first exception surfaces — a free
    worker can dequeue and start the next task before this function's
    exception handler gets scheduled and calls ``cancel()`` on it. That
    institution's file still gets written in that case (harmless: its own
    per-institution artifact is complete and correct, just extra work done
    after the decision to abort was already made). What's guaranteed
    regardless of this race: the institution whose worker actually raised
    never has its own file written, and every result is discarded (not
    returned) once any exception occurs.
    """
    items = list(items)
    if not items:
        return []
    results: list[_R] = []
    first_exc: BaseException | None = None
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, item) for item in items]
        for future in as_completed(futures):
            try:
                result = future.result()
            except CancelledError:
                continue
            except BaseException as exc:
                if first_exc is None:
                    first_exc = exc
                    for f in futures:
                        f.cancel()
                continue
            if result is not None:
                results.append(result)
    if first_exc is not None:
        raise first_exc
    return results


__all__ = ["run_concurrent"]
