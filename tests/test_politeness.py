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


def test_host_key_strips_path_query_and_scheme():
    # host_key is hostname-level and scheme-agnostic (Finding 1 fix): http:// and
    # https:// to the same physical host share one key so the throttle and robots
    # cache treat them as one host. Port is retained (a distinct service).
    assert host_key("https://x.gov/a/b?c=d#e") == "x.gov"
    assert host_key("http://x.gov/other") == "x.gov"
    assert host_key("http://sub.x.gov:8080/p") == "sub.x.gov:8080"


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


def test_throttle_same_host_different_scheme_shares_one_entry():
    """Finding 1 (SCHEME-SPLIT): http:// and https:// to the *same physical host*
    must share one throttle entry. A request to http://x.gov followed by one to
    https://x.gov has to be spaced by the full per-host delay — otherwise two
    workers reaching the same host over different schemes both fire immediately
    and defeat the >=1.0s per-host floor. Keying on ``scheme://netloc`` splits
    them into two entries, so the second call sees no prior timestamp and does
    not sleep."""
    th, clock = _throttle(1.0)
    th.wait("http://x.gov/a")   # t=0, first hit to this physical host
    th.wait("https://x.gov/b")  # SAME host over https — must sleep the full delay
    assert clock.slept == [1.0]


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


def test_robots_cache_fetches_once_per_host_under_concurrency():
    """Per-host double-checked populate: many worker threads hitting the same
    uncached host trigger exactly one robots.txt fetch, not one per thread —
    and no thread is convoyed behind another host's fetch."""
    calls: list[str] = []
    calls_lock = threading.Lock()

    def _counting_fetch(robots_url, *, user_agent, timeout):
        with calls_lock:
            calls.append(robots_url)
        return ROBOTS_TXT

    rc = RobotsCache("G3O-Observatory/0.1", fetch=_counting_fetch)

    def worker():
        for _ in range(20):
            rc.allowed("https://same.gov/public/page")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls.count("https://same.gov/robots.txt") == 1


def test_throttle_default_delay_is_one_second_D4():
    """Decision D4: the default per-host courtesy delay is the research-ethics
    1.0s floor, and it is a floor on the gap between same-host request *starts*
    (PI ruling 2026-08-01: spacing, not serialization). Two back-to-back
    same-host requests sleep exactly 1.0s."""
    clock = _FakeClock()
    th = HostThrottle(sleep=clock.sleep, monotonic=clock.monotonic)
    assert th.delay_seconds == DEFAULT_HOST_DELAY_SECONDS == 1.0
    th.wait("https://x.gov/a")  # t=0, no sleep
    th.wait("https://x.gov/b")  # elapsed 0 -> sleep the full 1.0s
    assert clock.slept == [1.0]


# ---------------------------------------------------------------------------
# HostThrottle — max_wait ceiling (issue #96)
# ---------------------------------------------------------------------------


def _instrumented_throttle(delay: float = 1.0):
    """A throttle on a fake clock that advances only when it sleeps."""
    clock = [0.0]
    slept: list[float] = []

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    return (
        HostThrottle(delay, sleep=_sleep, monotonic=lambda: clock[0]),
        clock,
        slept,
    )


def test_throttle_now_reads_the_injected_clock():
    # The budget in Stage 4 is measured on this, so it has to be the same clock
    # the waits are computed against — not time.monotonic.
    t, clock, _ = _instrumented_throttle()
    assert t.now() == 0.0
    clock[0] = 41.5
    assert t.now() == 41.5


def test_throttle_first_request_to_a_host_never_waits_whatever_the_ceiling():
    # Nothing has been fetched from this host, so there is no courtesy debt to
    # pay and max_wait has nothing to refuse. This is why the host that
    # motivated #96 still costs exactly one fetch rather than zero.
    t, _, slept = _instrumented_throttle()
    assert t.wait("https://x.gov/a", extra_delay=8640.0, max_wait=0.0) is True
    assert slept == []


def test_throttle_refuses_a_wait_that_exceeds_max_wait_without_sleeping():
    # The riigikohus.ee case: Crawl-delay 8640 against a 3600 s budget.
    t, _, slept = _instrumented_throttle()
    assert t.wait("https://x.gov/a", extra_delay=8640.0) is True
    assert t.wait("https://x.gov/b", extra_delay=8640.0, max_wait=3600.0) is False
    assert slept == []  # refused *before* the sleep, not after it


def test_throttle_takes_a_wait_that_fits_under_max_wait():
    t, _, slept = _instrumented_throttle()
    assert t.wait("https://x.gov/a", extra_delay=120.0) is True
    assert t.wait("https://x.gov/b", extra_delay=120.0, max_wait=3600.0) is True
    assert slept == [120.0]


def test_throttle_refusal_leaves_the_host_stamp_untouched():
    """No request was made, so the host's courtesy clock must not advance.

    Otherwise a refusal would silently buy the *next* caller a shorter wait
    than the site asked for — a partial reversal of D4 through the back door,
    which is exactly what the chosen fix avoids.
    """
    t, clock, slept = _instrumented_throttle()
    assert t.wait("https://x.gov/a", extra_delay=100.0) is True  # stamp = 0.0
    clock[0] = 10.0
    assert t.wait("https://x.gov/b", extra_delay=100.0, max_wait=5.0) is False
    # Had the refusal re-stamped at t=10, this call would still owe 10 s.
    clock[0] = 100.0
    assert t.wait("https://x.gov/c", extra_delay=100.0) is True
    assert slept == []


def test_throttle_without_max_wait_is_unbounded():
    # Every pre-#96 caller: no ceiling, always proceeds, sleeps the full delay.
    t, _, slept = _instrumented_throttle()
    assert t.wait("https://x.gov/a", extra_delay=8640.0) is True
    assert t.wait("https://x.gov/b", extra_delay=8640.0) is True
    assert slept == [8640.0]


def test_throttle_zero_delay_is_still_a_no_op_under_a_ceiling():
    t, _, slept = _instrumented_throttle(delay=0.0)
    assert t.wait("https://x.gov/a", max_wait=0.0) is True
    assert t.wait("https://x.gov/b", max_wait=0.0) is True
    assert slept == []
