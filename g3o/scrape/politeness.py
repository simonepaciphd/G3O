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
from collections.abc import Callable
from urllib import robotparser
from urllib.parse import urlsplit

import requests

from g3o.common import config
from g3o.scrape import egress

# Per-host courtesy delay between successive requests to the same host. An
# engineering parameter (not a methodology surface); surfaced on PresweepConfig
# as ``scrape_host_delay_seconds`` so it is documented and overridable.
DEFAULT_HOST_DELAY_SECONDS = 1.0
_ROBOTS_TIMEOUT_SECONDS = 10


def _robots_cache_key(url: str) -> str:
    """``scheme://netloc`` for ``url`` — the granularity for the robots cache.

    Scheme- and port-preserving on purpose (SCHEME-SPLIT follow-up, 2026-08):
    RFC 9309 §2.3 treats ``http://x.gov/robots.txt`` and
    ``https://x.gov/robots.txt`` as **distinct resources** (different scheme →
    different origin → potentially different rules), so the two must cache under
    separate keys. The project's public posture is to crawl politely, so we do
    not deviate from that reading. This is the *only* key that is also a URL
    prefix: :meth:`RobotsCache._parser_for` reconstructs the fetch URL as
    ``f"{_robots_cache_key(url)}/robots.txt"``. Single caller: ``RobotsCache``.
    """
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def host_key(url: str) -> str:
    """Host and port key retained for the per-host failure circuit breaker."""
    return urlsplit(url).netloc


def _throttle_key(url: str) -> str:
    """The bare hostname of ``url`` — the granularity for the per-host throttle.

    Deliberately coarser than :func:`_robots_cache_key` (SCHEME-SPLIT fix,
    2026-07/08): the courtesy delay protects a **physical host**, so every
    request that lands on one host shares one throttle bucket regardless of how
    the URL is spelled. Concretely this key intentionally collapses:

    - **scheme** — ``http://x.gov`` and ``https://x.gov`` are one server; keying
      on scheme let two workers hit it over http and https with no spacing.
    - **port** — ``x.gov:8080`` and ``x.gov`` (i.e. ``:443``) share one throttle
      bucket. This is a *deliberate* choice, not an oversight: a courtesy delay
      is a per-host social contract with the operator, and ports are cheap to
      vary. Collapsing them is the conservative (more-throttling) reading; if a
      future case needs per-port spacing this is the line to revisit.

    Single caller: ``HostThrottle.wait``.
    """
    parts = urlsplit(url)
    return parts.hostname or parts.netloc


def _fetch_robots_txt(
    robots_url: str, *, user_agent: str, timeout: int
) -> str | None:
    """GET a robots.txt with the G3O user-agent.

    Returns the body text, or ``None`` on any failure / non-200 (the caller
    treats ``None`` as allow-all).
    """
    try:
        resp = requests.get(
            robots_url,
            headers={"user-agent": user_agent},
            timeout=timeout,
            # Egress (#90): the same proxy the page fetches use, or None for
            # direct. Deciding politeness from one identity and then fetching
            # from another would make the D4 respect-robots decision answer a
            # question nobody asked — robots.txt is a per-requester contract.
            proxies=egress.requests_proxies(),
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

    Thread safety (Stage 4 concurrency, 2026-07): ``_parser_for`` is called from
    multiple worker threads. Locking is per-host, not a single cache-wide lock —
    a cache-wide lock held across the (up to ``_ROBOTS_TIMEOUT_SECONDS``)
    robots.txt GET would convoy every thread behind whichever host is slow or
    dead. Instead a per-host lock serializes only threads fetching the *same*
    uncached host, with a double-checked populate so each host is fetched once;
    different hosts never block each other.
    """

    def __init__(
        self,
        user_agent: str | None = None,
        *,
        fetch: Callable[..., str | None] = _fetch_robots_txt,
        timeout: int = _ROBOTS_TIMEOUT_SECONDS,
        throttle: HostThrottle | None = None,
    ) -> None:
        self.user_agent = user_agent or config.USER_AGENT
        self._fetch = fetch
        self._timeout = timeout
        # The robots.txt GET is itself a physical hit to the host (finding: an
        # uncached host's robots fetch preceded the page fetch with no per-host
        # spacing between them). When a shared throttle is injected, the (one-
        # per-host) robots fetch registers with / respects it exactly as a page
        # fetch does, so the following page GET is spaced the full delay after
        # the robots GET — not fired back-to-back.
        self._throttle = throttle
        self._parsers: dict[str, robotparser.RobotFileParser | None] = {}
        self._map_lock = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}

    def _lock_for(self, host: str) -> threading.Lock:
        with self._map_lock:
            lock = self._host_locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._host_locks[host] = lock
            return lock

    def _parser_for(self, url: str) -> robotparser.RobotFileParser | None:
        host = _robots_cache_key(url)
        # Fast path: already populated (a single set-once dict read is safe under
        # the GIL). Avoids taking a lock once the host's robots.txt is cached.
        if host in self._parsers:
            return self._parsers[host]
        with self._lock_for(host):
            if host in self._parsers:  # double-check: another thread populated it
                return self._parsers[host]
            robots_url = f"{host}/robots.txt"
            # This is the one-and-only physical robots.txt GET for this host.
            # Space/register it against the host throttle (when one is injected)
            # so it counts toward the per-host courtesy delay like any page GET
            # would; a cached host never reaches here, so no extra delay is paid
            # once robots is known.
            if self._throttle is not None:
                self._throttle.wait(robots_url)
            body = self._fetch(
                robots_url,
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

    Thread safety (Stage 4 concurrency, 2026-07): ``wait()`` is called from
    multiple worker threads processing different institutions. Locking is
    per-host, not a single lock around the whole call — a single lock would
    serialize every institution's throttle check behind whichever host
    happens to be sleeping, defeating the point of running institutions on
    different hosts concurrently. Two threads targeting the *same* host
    serialize through the full read-sleep-record sequence (correct courtesy-
    delay enforcement); two threads targeting different hosts never block
    each other. Per-host locks are created lazily under a small map lock.
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
        self._map_lock = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}

    def _lock_for(self, host: str) -> threading.Lock:
        with self._map_lock:
            lock = self._host_locks.get(host)
            if lock is None:
                lock = threading.Lock()
                self._host_locks[host] = lock
            return lock

    def now(self) -> float:
        """This throttle's clock reading — the same clock its waits are measured on.

        Exposed (issue #96) so a caller enforcing a wall-clock budget across
        several waits measures elapsed time against one source of truth. The
        budget arithmetic in :func:`g3o.run.presweep.stage_scrape._scrape_one`
        is ``elapsed + next_wait <= budget``; that comparison is only sound if
        both terms come from this clock, and injecting a fake clock into the
        throttle then measuring elapsed time with ``time.monotonic`` would make
        the budget untestable without really sleeping.
        """
        return self._monotonic()

    def wait(
        self,
        url: str,
        *,
        extra_delay: float | None = None,
        max_wait: float | None = None,
    ) -> bool:
        """Block until ``delay`` has elapsed since the last request to this host.

        ``extra_delay`` (e.g. a robots ``Crawl-delay``) raises the floor for
        this call: the effective wait is ``max(self.delay_seconds, extra_delay)``.

        ``max_wait`` (issue #96) is a ceiling on how long *this call* may sleep.
        Returns True when the wait was taken and the caller may fetch; False
        when the required sleep exceeds ``max_wait``, in which case **nothing
        is slept and the host's last-request stamp is left untouched** — no
        request is made, so the courtesy clock must not advance. ``None`` (the
        default) is no ceiling, which is every pre-#96 caller's behaviour.

        The ceiling is enforced *inside* the per-host lock and *before* the
        sleep, deliberately. Checking a budget after the sleep would still pay
        one full ``Crawl-delay`` — 2h24m on the host that motivated #96 —
        before giving up, which is the whole cost the budget exists to avoid.
        Deciding inside the lock also makes the check race-free against another
        worker on the same host: the decision and the sleep are one atomic step,
        so a refusal can never be based on a stamp another thread has already
        moved.
        """
        delay = self.delay_seconds
        if extra_delay is not None:
            delay = max(delay, extra_delay)
        host = _throttle_key(url)
        with self._lock_for(host):
            if delay <= 0:
                self._last[host] = self._monotonic()
                return True
            last = self._last.get(host)
            now = self._monotonic()
            if last is not None and (now - last) < delay:
                remaining = delay - (now - last)
                if max_wait is not None and remaining > max_wait:
                    return False
                self._sleep(remaining)
            self._last[host] = self._monotonic()
            return True


__all__ = [
    "DEFAULT_HOST_DELAY_SECONDS",
    "HostThrottle",
    "RobotsCache",
]
