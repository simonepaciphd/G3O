"""Process-wide meter for per-unit (non-token) API spend (2026-10-02).

Serper (Stage 1) and the Bright Data Web Unlocker (Stage 4) bill per credit and
per byte, and both are called from deep inside worker threads, far below the
orchestrator that owns the :class:`~g3o.common.cost_monitor.CostMonitor`. This
module is the narrow channel between the two: the clients call :func:`record`
at the point a billable response arrives, and the orchestrator installs a sink
that folds each record into the run's monitor.

**Recording never raises.** The unlocker is called from inside
``fetcher.scrape_url``, whose caller catches ``Exception`` per URL and records
it as a scrape failure. A budget abort raised from the hook would be swallowed
there and the run would carry on spending. So :func:`record` only accounts, and
enforcement happens at explicit safe points through :func:`enforce`, which the
stage loops call outside their per-URL error handling.

With no sink installed (CLI subcommands, probes, tests) :func:`record` is a
no-op and :func:`enforce` never raises, so nothing outside a live run changes.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

#: Metered API names. One vocabulary for the clients, the monitor and the report.
SERPER = "serper"
UNLOCKER = "brightdata_unlocker"

_lock = threading.Lock()
_sink: Callable[[str, dict[str, Any]], None] | None = None
_guard: Callable[[str], None] | None = None


def install(
    sink: Callable[[str, dict[str, Any]], None],
    guard: Callable[[str], None] | None = None,
) -> None:
    """Route records to ``sink`` and enforcement to ``guard`` for this process."""
    global _sink, _guard
    with _lock:
        _sink = sink
        _guard = guard


def uninstall() -> None:
    """Remove the sink and guard; recording becomes a no-op again."""
    global _sink, _guard
    with _lock:
        _sink = None
        _guard = None


def record(api: str, **units: Any) -> None:
    """Account one billable call. Never raises (see the module docstring)."""
    sink = _sink
    if sink is None:
        return
    try:
        sink(api, units)
    except Exception:  # accounting must not break the call it accounts for
        logger.exception("spend_meter: recording %s usage failed", api)


def enforce(stage: str) -> None:
    """Raise the installed guard's budget error if the run is over its ceiling.

    ``stage`` names the stage for the abort record. Call only where an exception
    is allowed to end the stage — never from inside a per-URL
    ``try/except Exception``.
    """
    guard = _guard
    if guard is not None:
        guard(stage)


__all__ = ["SERPER", "UNLOCKER", "enforce", "install", "record", "uninstall"]
