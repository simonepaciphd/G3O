"""Tests for ``g3o.scrape.politeness`` — robots.txt compliance + per-host
throttle (review F14 / Decision D4).

No network and no real sleeping: ``RobotsCache`` takes an injected fetch and
``HostThrottle`` takes an injected clock/sleep.
"""

from __future__ import annotations

import threading
import time

from g3o.scrape.politeness import HostThrottle, RobotsCache, host_key

ROBOTS_TXT = """\
User-agent: *
Disallow: /private
Crawl-delay: 2
"""


# ---------------------------------------------------------------------------
# host_key
# ---------------------------------------------------------------------------


def test_host_key_strips_path_and_query():
    assert host_key("https://x.gov/a/b?c=d#e") == "https://x.gov"
    assert host_key("http://sub.x.gov:8080/p") == "http://sub.x.gov:8080"


# ---------------------------------------------------------------------------
# RobotsCache
# ---------------------------------------------------------------------------


def _fixed_fetch(body):
    def _f(robots_url, *, user_agent, timeout):
        return body
    return _f


def test_robots_allows_unlisted_path():
    rc = RobotsCache("G3O-Observatory/0.1", fetch=_fixed_fetch(ROBOTS_TXT))
    assert rc.allowed("https://x.gov/public/page") is True


def test_robots_disallows_listed_path():
    rc = RobotsCache("G3O-Observatory/0.1", fetch=_fixed_fetch(ROBOTS_TXT))
    assert rc.allowed("https://x.gov/private/secret") is False


def test_robots_crawl_delay_parsed():
    rc = RobotsCache("G3O-Observatory/0.1", fetch=_fixed_fetch(ROBOTS_TXT))
    assert rc.crawl_delay("https://x.gov/anything") == 2.0


def test_robots_unfetchable_is_allow_all():
    # fetch returns None (network error / non-200 / no file) → allow everything.
    rc = RobotsCache("G3O-Observatory/0.1", fetch=_fixed_fetch(None))
    assert rc.allowed("https://x.gov/private/secret") is True
    assert rc.crawl_delay("https://x.gov/private/secret") is None


def test_robots_fetched_once_per_host():
    calls: list[str] = []

    def _counting(robots_url, *, user_agent, timeout):
        calls.append(robots_url)
        return ROBOTS_TXT

    rc = RobotsCache("G3O-Observatory/0.1", fetch=_counting)
    rc.allowed("https://x.gov/a")
    rc.allowed("https://x.gov/b")
    rc.crawl_delay("https://x.gov/c")
    rc.allowed("https://other.gov/a")

    assert calls == ["https://x.gov/robots.txt", "https://other.gov/robots.txt"]


def test_robots_passes_user_agent_to_fetch():
    captured: dict[str, str] = {}

    def _f(robots_url, *, user_agent, timeout):
        captured["ua"] = user_agent
        return ROBOTS_TXT

    RobotsCache("MyUA/9", fetch=_f).allowed("https://x.gov/a")
    assert captured["ua"] == "MyUA/9"


# ---------------------------------------------------------------------------
# HostThrottle
# ---------------------------------------------------------------------------


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


def _throttle(delay):
    clock = _FakeClock()
    return HostThrottle(delay, sleep=clock.sleep, monotonic=clock.monotonic), clock


def test_throttle_first_request_no_sleep():
    th, clock = _throttle(2.0)
    th.wait("https://x.gov/a")
    assert clock.slept == []


def test_throttle_back_to_back_same_host_sleeps_full_delay():
    th, clock = _throttle(2.0)
    th.wait("https://x.gov/a")  # t=0, no sleep
    th.wait("https://x.gov/b")  # same host, elapsed 0 → sleep 2.0
    assert clock.slept == [2.0]


def test_throttle_different_hosts_no_sleep():
    th, clock = _throttle(2.0)
    th.wait("https://x.gov/a")
    th.wait("https://y.gov/a")
    assert clock.slept == []


def test_throttle_no_sleep_when_enough_time_elapsed():
    th, clock = _throttle(2.0)
    th.wait("https://x.gov/a")  # records t=0
    clock.t = 5.0  # plenty of time passes
    th.wait("https://x.gov/b")
    assert clock.slept == []


def test_throttle_extra_delay_raises_floor():
    th, clock = _throttle(1.0)
    th.wait("https://x.gov/a")
    th.wait("https://x.gov/b", extra_delay=4.0)  # max(1.0, 4.0) = 4.0
    assert clock.slept == [4.0]


def test_throttle_zero_delay_is_noop():
    th, clock = _throttle(0.0)
    th.wait("https://x.gov/a")
    th.wait("https://x.gov/b")
    assert clock.slept == []


# ---------------------------------------------------------------------------
# HostThrottle under real concurrency (Stage 4 parallelization, 2026-07)
#
# Uses real time.sleep/time.monotonic (not the injected _FakeClock, which is
# a plain object with no synchronization of its own) because these tests
# assert on actual wall-clock interleaving across real threads.
# ---------------------------------------------------------------------------


def test_throttle_same_host_serializes_across_threads():
    """N threads hitting the same host must not all pass through at once —
    the per-host lock has to serialize them, not just avoid corrupting the
    dict. A pre-fix race would let every thread read a stale ``last`` and
    skip sleeping entirely."""
    delay = 0.05
    th = HostThrottle(delay)
    n = 6

    def worker():
        th.wait("https://x.gov/a")

    threads = [threading.Thread(target=worker) for _ in range(n)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start
    # n calls to one host: the first is free, the remaining (n-1) each incur
    # at least `delay` serialized against each other. Generous margin for
    # scheduling jitter.
    assert elapsed >= delay * (n - 1) * 0.6


def test_throttle_different_hosts_run_concurrently():
    """Threads hitting different hosts must not block on each other's delay —
    a single stage-wide lock (instead of per-host) would serialize all of
    them regardless of host, which is exactly what per-host locking avoids."""
    delay = 0.3
    th = HostThrottle(delay)
    hosts = [f"https://host{i}.gov/a" for i in range(6)]

    def worker(host: str) -> None:
        th.wait(host)

    threads = [threading.Thread(target=worker, args=(h,)) for h in hosts]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start
    # Each host's first call never sleeps; with true per-host concurrency this
    # finishes almost immediately regardless of `delay`.
    assert elapsed < delay
