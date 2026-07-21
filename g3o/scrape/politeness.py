"""Scrape-layer politeness — robots.txt compliance + per-host rate limiting.

Added for review F14 / Decision D4 (researcher, 2026-06-10). The production
Stage 4 scrape loop hits same-host government URLs back-to-back and previously
ignored robots.txt entirely; D4 resolved to **respect robots.txt** (the
conservative research-ethics posture). This module owns both policies as
small, injectable, network-light helpers used by the Stage 4 runner
(:func:`g3o.run.presweep.stage_scrape._run_scrape`). The low-level fetcher
(:func:`g3o.scrape.fetcher.scrape_url`) stays a robots-agnostic primitive so
standalone/CLI fetches and the unit suite are unaffected.

Both pieces are deliberately resilient:

- A robots.txt that cannot be fetched (network error, non-200, e.g. no file
  present) is treated as **allow-all** — the standard crawler convention and
  the conservative choice for *coverage*: a missing/unreachable robots file is
  not a ``Disallow``.
- The throttle is a no-op when its delay is ``<= 0``, and its clock/sleep are
  injectable so the suite exercises it without wall-clock sleeping.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from urllib import robotparser
from urllib.parse import urlsplit, urlunsplit

import requests

from g3o.common import config

# Per-host courtesy delay between successive requests to the same host. An
# engineering parameter (not a methodology surface); surfaced on PresweepConfig
# as ``scrape_host_delay_seconds`` so it is documented and overridable.
DEFAULT_HOST_DELAY_SECONDS = 1.0
_ROBOTS_TIMEOUT_SECONDS = 10


def host_key(url: str) -> str:
    """``scheme://netloc`` for ``url`` — the granularity for robots + throttle."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _fetch_robots_txt(
    robots_url: str, *, user_agent: str, timeout: int
) -> str | None:
    """GET a robots.txt with the G3O user-agent.

    Returns the body text, or ``None`` on any failure / non-200 (the caller
    treats ``None`` as allow-all).
    """
    try:
        resp = requests.get(
            robots_url, headers={"user-agent": user_agent}, timeout=timeout
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return resp.text


class RobotsCache:
    """Per-host robots.txt fetch + cache + allow / crawl-delay lookup.

    One robots.txt fetch per host for the life of the cache (a run-scoped
    object). ``fetch`` is injectable for tests so no network is touched.

    Thread-safe (concurrent Stage 4, review F14b): a single lock guards the
    per-host populate-on-miss so each host's robots.txt is fetched exactly once
    even when several worker threads first touch the same host at once, and
    ``allowed`` / ``crawl_delay`` see a consistent parser. The lock is held
    across the (one-time, per-host) fetch; steady-state lookups after warmup
    only re-read the populated dict under the same short critical section.
    """

    def __init__(
        self,
        user_agent: str | None = None,
        *,
        fetch: Callable[..., str | None] = _fetch_robots_txt,
        timeout: int = _ROBOTS_TIMEOUT_SECONDS,
    ) -> None:
        self.user_agent = user_agent or config.USER_AGENT
        self._fetch = fetch
        self._timeout = timeout
        self._parsers: dict[str, robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def _parser_for(self, url: str) -> robotparser.RobotFileParser | None:
        host = host_key(url)
        with self._lock:
            if host not in self._parsers:
                body = self._fetch(
                    f"{host}/robots.txt",
                    user_agent=self.user_agent,
                    timeout=self._timeout,
                )
                if body is None:
                    self._parsers[host] = None  # unreachable / absent → allow-all
                else:
                    parser = robotparser.RobotFileParser()
                    parser.parse(body.splitlines())
                    self._parsers[host] = parser
            return self._parsers[host]

    def allowed(self, url: str) -> bool:
        """True if ``url`` is fetchable for the G3O user-agent per robots.txt."""
        parser = self._parser_for(url)
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        """robots.txt ``Crawl-delay`` for the G3O user-agent, or ``None``."""
        parser = self._parser_for(url)
        if parser is None:
            return None
        try:
            delay = parser.crawl_delay(self.user_agent)
        except Exception:
            return None
        return float(delay) if delay is not None else None


class HostThrottle:
    """Enforce a minimum interval between requests to the same host.

    ``sleep`` and ``monotonic`` are injectable so tests assert the computed
    wait without sleeping for real.

    Thread-safe (concurrent Stage 4, review F14b): an internal lock guards the
    per-host timestamp map so concurrent ``wait`` calls for *different* hosts
    (each releasing the lock before sleeping) cannot corrupt the shared dict.
    The lock is held only for the check-and-record; the actual ``sleep``
    happens outside it, so different hosts throttle independently. The slot is
    reserved at the projected dispatch time (``now + due``) rather than after
    the sleep, so the record is committed before the lock is released and a
    same-host follower spaces off it correctly. With injected fake clocks this
    is identical to recording ``monotonic()`` post-sleep (the fake clock
    advances by exactly ``due`` during the sleep).

    Same-host serialization is *not* this class's job — that is
    :class:`HostScheduler`. Under the scheduler, all same-host ``wait`` calls
    run under that host's serialization lock, so the check-then-sleep sequence
    is additionally atomic per host.
    """

    def __init__(
        self,
        delay_seconds: float = DEFAULT_HOST_DELAY_SECONDS,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.delay_seconds = delay_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, url: str, *, extra_delay: float | None = None) -> None:
        """Block until ``delay`` has elapsed since the last request to this host.

        ``extra_delay`` (e.g. a robots ``Crawl-delay``) raises the floor for
        this call: the effective wait is ``max(self.delay_seconds, extra_delay)``.
        """
        delay = self.delay_seconds
        if extra_delay is not None:
            delay = max(delay, extra_delay)
        host = host_key(url)
        with self._lock:
            if delay <= 0:
                self._last[host] = self._monotonic()
                return
            last = self._last.get(host)
            now = self._monotonic()
            due = 0.0
            if last is not None and (now - last) < delay:
                due = delay - (now - last)
            # Reserve the slot at the projected dispatch time before releasing
            # the lock, so a same-host follower spaces off this request even if
            # it enters wait() before this one finishes sleeping.
            self._last[host] = now + due
        if due > 0:
            self._sleep(due)


class HostScheduler:
    """Thread-safe per-host serialization + spacing gate for concurrent Stage 4.

    Wraps a :class:`HostThrottle` (the spacing source of truth) and adds a
    per-host :class:`threading.Lock`. A worker holds a host's lock across both
    the throttle wait *and* the fetch, which gives two guarantees at once:

    1. **Serialization** — only one request per host is ever in flight, because
       only one thread can hold a given host's lock.
    2. **Spacing correctness** — the throttle's check-then-sleep-then-record for
       that host is atomic (no interleaving same-host waiter).

    Different hosts hold different locks and proceed concurrently. With a single
    worker every lock is uncontended and behavior collapses to the throttle's
    sequential semantics.

    Sharding (700k+ scale): all state is instance-local, so one scheduler per
    shard/process enforces politeness intra-shard with no distributed lock —
    provided the shard partition is keyed by host (every URL for a host in one
    shard). This class does not shard; it is the seam a shard runner plugs into.
    """

    def __init__(self, throttle: HostThrottle) -> None:
        self._throttle = throttle
        self._registry_lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def _lock_for(self, host: str) -> threading.Lock:
        with self._registry_lock:
            lock = self._locks.get(host)
            if lock is None:
                lock = self._locks[host] = threading.Lock()
            return lock

    @contextmanager
    def slot(self, url: str, *, extra_delay: float | None = None) -> Iterator[None]:
        """Hold this host's serialization lock across the throttle wait + fetch.

        Usage::

            with scheduler.slot(url, extra_delay=crawl_delay):
                page = scrape_url(url, ...)
        """
        lock = self._lock_for(host_key(url))
        with lock:
            self._throttle.wait(url, extra_delay=extra_delay)
            yield


__all__ = [
    "DEFAULT_HOST_DELAY_SECONDS",
    "HostScheduler",
    "HostThrottle",
    "RobotsCache",
    "host_key",
]
