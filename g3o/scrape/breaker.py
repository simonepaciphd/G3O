"""Per-host circuit breaker for Stage 4 (PI-approved 2026-09-06).

Measured on ``r20260903T120740Z-362c`` (20,293 institutions, 12 workers, scrape
51.3 h of a 56.1 h run): 15,462 fetches ended in ``ConnectTimeout``, each after
three 30 s attempts, and only 57 of them were on a host that returned a page
anywhere in the run. 28,212 of the run's 46,487 failures were the second or
later failure on a host that had already failed for the same institution. The
fetcher learned nothing from a dead host; every URL on it paid the full price.

This class is the memory. It is run-scoped and shared across worker threads
like :class:`~g3o.scrape.politeness.HostThrottle`: after ``threshold``
connect-level failures on a host, :meth:`is_open` answers True and the runner
skips the host's remaining URLs, recording each under
``stage_scrape.REASON_HOST_UNREACHABLE`` — a member of
``g3o.report.outcomes._FAILURE_REASONS``, so the institution reports
PROCESSING_FAILED rather than publishing "could not reach" as "searched and
found nothing".

Only connect-level failures count. A refusal (``HTTPError``), a TLS failure
(``SSLError``) or a slow body (``ReadTimeout``) all mean the host answered; the
breaker is for hosts that do not.
"""

from __future__ import annotations

import threading

from g3o.scrape.politeness import host_key

#: ``error_class_of`` names that mean "no connection was established". Exact
#: names, not an isinstance test: ``SSLError`` and ``ProxyError`` subclass
#: ``ConnectionError`` in ``requests`` and are deliberately *not* here — the
#: first is a per-host certificate fact, the second is about our egress.
TRIPPING_ERROR_CLASSES: frozenset[str] = frozenset({"ConnectTimeout", "ConnectionError"})


class HostBreaker:
    """Count connect-level failures per host; open after ``threshold``.

    Thread-safe under one lock: every operation is a dict read-modify-write of
    microseconds, so unlike the throttle there is nothing to gain from per-host
    locks. A success resets the host's count (a host that answered is not
    dead) but never closes an open host — an open host is not fetched, so the
    only way a success reaches one is a request that was already in flight
    when it tripped, and 57 of 15,462 is not a reason to re-arm.
    """

    def __init__(self, threshold: int) -> None:
        if threshold < 1:
            raise ValueError(f"threshold must be >= 1, got {threshold}")
        self.threshold = threshold
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._open: set[str] = set()

    def is_open(self, url: str) -> bool:
        """True when ``url``'s host has tripped and must not be fetched."""
        host = host_key(url)
        with self._lock:
            return host in self._open

    def failures(self, url: str) -> int:
        """Connect-level failures recorded so far for ``url``'s host."""
        with self._lock:
            return self._failures.get(host_key(url), 0)

    def record_failure(self, url: str, error_class: str | None) -> bool:
        """Count one failure; return True iff this one tripped the host.

        ``error_class`` is ``g3o.scrape.fetcher.error_class_of``'s answer; a
        class outside :data:`TRIPPING_ERROR_CLASSES` is ignored and never trips.
        """
        if error_class not in TRIPPING_ERROR_CLASSES:
            return False
        host = host_key(url)
        with self._lock:
            n = self._failures.get(host, 0) + 1
            self._failures[host] = n
            if n >= self.threshold and host not in self._open:
                self._open.add(host)
                return True
            return False

    def record_success(self, url: str) -> None:
        """A page came back: the host is alive, forget its earlier failures."""
        with self._lock:
            self._failures.pop(host_key(url), None)

    def open_hosts(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._open)


__all__ = ["HostBreaker", "TRIPPING_ERROR_CLASSES"]
