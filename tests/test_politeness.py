"""Tests for ``g3o.scrape.politeness`` — robots.txt compliance + per-host
throttle (review F14 / Decision D4).

No network and no real sleeping: ``RobotsCache`` takes an injected fetch and
``HostThrottle`` takes an injected clock/sleep.
"""

from __future__ import annotations

import threading
import time

from g3o.scrape.politeness import (
    DEFAULT_HOST_DELAY_SECONDS,
    HostScheduler,
    HostThrottle,
    RobotsCache,
    host_key,
)

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


def test_throttle_default_delay_is_one_second_D4():
    # Decision D4: the default per-host courtesy delay is the research-ethics
    # 1.0s floor. Two back-to-back same-host requests sleep exactly 1.0s.
    clock = _FakeClock()
    th = HostThrottle(sleep=clock.sleep, monotonic=clock.monotonic)
    assert th.delay_seconds == DEFAULT_HOST_DELAY_SECONDS == 1.0
    th.wait("https://x.gov/a")  # t=0, no sleep
    th.wait("https://x.gov/b")  # elapsed 0 → sleep the full 1.0s
    assert clock.slept == [1.0]


# ---------------------------------------------------------------------------
# HostScheduler — per-host serialization + spacing under a thread pool
# (review F14b). These use real threads; barriers/counters avoid dependence on
# wall-clock timing, and the spacing proof uses an injected clock (no real 1s
# sleep) exactly as the sequential HostThrottle tests do.
# ---------------------------------------------------------------------------


class _RecordingClock:
    """Thread-safe fake clock: records requested sleeps, advances virtual time."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        with self._lock:
            return self.t

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.slept.append(seconds)
            self.t += seconds


def test_scheduler_serializes_same_host_never_concurrent():
    """Requirement 1: two same-host requests are never in flight at once."""
    scheduler = HostScheduler(HostThrottle(0.0))  # isolate serialization
    state = {"active": 0, "max": 0}
    state_lock = threading.Lock()
    start = threading.Barrier(2)

    def worker(url: str) -> None:
        start.wait()  # both threads race for the slot at the same instant
        with scheduler.slot(url):
            with state_lock:
                state["active"] += 1
                state["max"] = max(state["max"], state["active"])
            time.sleep(0.05)  # widen the window so a missing lock would overlap
            with state_lock:
                state["active"] -= 1

    threads = [
        threading.Thread(target=worker, args=("https://x.gov/a",)),
        threading.Thread(target=worker, args=("https://x.gov/b",)),  # same host
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["max"] == 1  # never two same-host requests inside a slot at once


def test_scheduler_allows_different_hosts_concurrently():
    """Requirement: two different-host requests CAN run concurrently.

    Both workers must meet inside their slots at a Barrier(2). If the scheduler
    serialized across hosts, only one could be in its slot and the barrier would
    time out (BrokenBarrierError) — so a clean pair of returns proves overlap.
    """
    scheduler = HostScheduler(HostThrottle(0.0))
    meet = threading.Barrier(2, timeout=5)
    reached: list[int] = []
    reached_lock = threading.Lock()

    def worker(url: str) -> None:
        with scheduler.slot(url):
            idx = meet.wait()  # raises if the other thread never arrives in time
            with reached_lock:
                reached.append(idx)

    threads = [
        threading.Thread(target=worker, args=("https://a.gov/x",)),
        threading.Thread(target=worker, args=("https://b.gov/y",)),  # different host
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(reached) == [0, 1]  # both were inside their slots simultaneously


def test_scheduler_enforces_min_spacing_same_host():
    """Requirement 2: >=1.0s elapses between same-host requests.

    Proven deterministically with an injected clock (no real sleeping): the
    same-host slot serializes the two waits, so exactly one 1.0s sleep is
    requested for the second request regardless of which thread wins the race.
    """
    clock = _RecordingClock()
    scheduler = HostScheduler(
        HostThrottle(1.0, sleep=clock.sleep, monotonic=clock.monotonic)
    )

    def worker(url: str) -> None:
        with scheduler.slot(url):
            pass

    threads = [
        threading.Thread(target=worker, args=("https://x.gov/a",)),
        threading.Thread(target=worker, args=("https://x.gov/b",)),  # same host
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert clock.slept == [1.0]


def test_scheduler_single_worker_matches_sequential_throttle():
    """pool_size=1 equivalence: uncontended slots reduce to plain throttle waits."""
    clock = _FakeClock()
    scheduler = HostScheduler(
        HostThrottle(1.0, sleep=clock.sleep, monotonic=clock.monotonic)
    )
    with scheduler.slot("https://x.gov/a"):
        pass
    with scheduler.slot("https://x.gov/b"):  # same host, elapsed 0 → 1.0s
        pass
    with scheduler.slot("https://y.gov/a"):  # different host → no sleep
        pass
    assert clock.slept == [1.0]


# ---------------------------------------------------------------------------
# RobotsCache thread-safety (requirement 3: robots correct under concurrency)
# ---------------------------------------------------------------------------


def test_robots_thread_safe_fetch_once_per_host():
    """Concurrent first-touch of the same host still fetches robots.txt once."""
    calls: list[str] = []
    calls_lock = threading.Lock()
    start = threading.Barrier(8)

    def _counting(robots_url, *, user_agent, timeout):
        with calls_lock:
            calls.append(robots_url)
        return ROBOTS_TXT

    rc = RobotsCache("G3O-Observatory/0.1", fetch=_counting)

    def worker(i: int) -> None:
        start.wait()  # maximize the concurrent-miss race
        rc.allowed(f"https://x.gov/page-{i}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls == ["https://x.gov/robots.txt"]  # exactly once despite 8 threads


def test_robots_concurrent_allow_disallow_correct():
    """allowed() stays correct across threads hitting allowed + disallowed paths."""
    rc = RobotsCache("G3O-Observatory/0.1", fetch=_fixed_fetch(ROBOTS_TXT))
    results: dict[str, bool] = {}
    results_lock = threading.Lock()

    def worker(path: str) -> None:
        allowed = rc.allowed(f"https://x.gov{path}")
        with results_lock:
            results[path] = allowed

    paths = ["/public/a", "/private/b", "/public/c", "/private/d"]
    threads = [threading.Thread(target=worker, args=(p,)) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == {
        "/public/a": True,
        "/private/b": False,
        "/public/c": True,
        "/private/d": False,
    }
