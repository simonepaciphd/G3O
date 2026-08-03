"""Tests for ``g3o.scrape.politeness`` — robots.txt compliance + per-host
throttle (review F14 / Decision D4).

No network and no real sleeping: ``RobotsCache`` takes an injected fetch and
``HostThrottle`` takes an injected clock/sleep.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlsplit

import requests

from g3o.common import config
from g3o.scrape import fetcher
from g3o.scrape.politeness import (
    DEFAULT_HOST_DELAY_SECONDS,
    HostThrottle,
    RobotsCache,
    _robots_cache_key,
    _throttle_key,
)

ROBOTS_TXT = """\
User-agent: *
Disallow: /private
Crawl-delay: 2
"""


# ---------------------------------------------------------------------------
# Key split: robots cache key vs throttle key (SCHEME-SPLIT follow-up)
#
# Two single-purpose keys with one caller each, on purpose:
#   - robots cache keys on scheme+netloc (RFC 9309: http/https robots.txt are
#     distinct resources) and is also the robots.txt URL prefix;
#   - the throttle keys on the bare hostname (one physical host = one courtesy-
#     delay bucket), deliberately collapsing scheme AND port.
# ---------------------------------------------------------------------------


def test_robots_cache_key_is_scheme_and_netloc():
    assert _robots_cache_key("https://x.gov/a/b?c=d#e") == "https://x.gov"
    assert _robots_cache_key("http://sub.x.gov:8080/p") == "http://sub.x.gov:8080"


def test_throttle_key_is_bare_hostname():
    assert _throttle_key("https://x.gov/a/b?c=d#e") == "x.gov"
    # port collapsed on purpose: :8080 and (implicit) :443 share one bucket
    assert _throttle_key("http://sub.x.gov:8080/p") == "sub.x.gov"


def test_keys_diverge_on_scheme():
    """The whole point of the split: same physical host reached over http vs
    https is ONE throttle bucket but TWO robots-cache resources."""
    http, https = "http://x.gov/a", "https://x.gov/a"
    # throttle: scheme-agnostic -> identical key -> same courtesy-delay bucket
    assert _throttle_key(http) == _throttle_key(https) == "x.gov"
    # robots: scheme-preserving -> distinct keys -> cached separately (RFC 9309)
    assert _robots_cache_key(http) != _robots_cache_key(https)


def test_keys_diverge_on_port():
    """Throttle collapses ports (one host = one bucket); the robots cache key,
    being a URL prefix, keeps the port so the fetch URL stays well-formed."""
    assert _throttle_key("http://x.gov:8080/p") == _throttle_key("https://x.gov/p")
    assert _robots_cache_key("http://x.gov:8080/p") == "http://x.gov:8080"


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
# Regression: two politeness findings, now fixed (formerly xfail repros).
#
#   Finding 2 — the one-per-host robots.txt GET must count toward the per-host
#               delay, so the page GET that follows it is spaced, not fired
#               back-to-back.
#   Finding 3 — a request that redirects to another host must wait on THAT
#               host's throttle before the hop's GET (manual hop-following),
#               so a redirect landing on a host another worker is throttled
#               against takes its turn instead of racing in.
# ---------------------------------------------------------------------------


def test_robots_fetch_is_spaced_against_the_following_page_fetch():
    """Finding 2: the Stage-4 runner handles each uncached URL as
    ``robots.allowed(url)`` (robots.txt GET) → ``throttle.wait(url)`` → page
    GET. With the shared throttle injected into ``RobotsCache``, the one-per-
    host robots GET registers against the host throttle, so the following page
    GET is held the full 1.0s after it rather than firing immediately."""
    clock = _FakeClock()
    host_hits: list[tuple[str, float]] = []

    def _robots_fetch(robots_url, **_kw):
        host_hits.append(("robots.txt", clock.t))
        return ""  # empty robots.txt -> allow-all, no Crawl-delay

    throttle = HostThrottle(1.0, sleep=clock.sleep, monotonic=clock.monotonic)
    robots = RobotsCache("G3O/1", fetch=_robots_fetch, throttle=throttle)

    url = "https://agency.gov/page"
    assert robots.allowed(url)  # triggers the (throttled) robots.txt GET
    throttle.wait(url, extra_delay=robots.crawl_delay(url))
    host_hits.append(("page", clock.t))

    robots_t = next(t for name, t in host_hits if name == "robots.txt")
    page_t = next(t for name, t in host_hits if name == "page")
    assert page_t - robots_t >= 1.0


class _FakeResp:
    """Minimal ``requests.Response`` stand-in for the manual-redirect path."""

    def __init__(self, status_code, headers, *, content=b"", url=""):
        self.status_code = status_code
        self.headers = headers  # lowercase keys; dict.get / `in` suffice
        self.content = content
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


class _FakeSession:
    def __init__(self, responder):
        self._responder = responder

    def get(self, url, *, timeout=None, allow_redirects=None):
        # _download must drive redirects itself, not delegate to the session.
        assert allow_redirects is False
        return self._responder(url)


def _redirect_responder(gets, clock):
    """old.example → 302 → agency.gov/landing; everything else → 200 html."""

    def _responder(url):
        gets.append((urlsplit(url).hostname, clock.t))
        if urlsplit(url).netloc == "old.example":
            return _FakeResp(302, {"location": "https://agency.gov/landing"}, url=url)
        return _FakeResp(
            200, {"content-type": "text/html"}, content=b"<html>ok</html>", url=url
        )

    return _responder


def test_download_waits_on_cross_host_redirect_before_the_hop(monkeypatch):
    """Finding 3 (core): ``_download`` follows redirects manually and waits on a
    cross-host destination's throttle BEFORE issuing that hop's GET. With
    ``agency.gov`` already hit by another worker at t=0, the redirect from
    ``old.example`` must sleep the full 1.0s before the GET to ``agency.gov``
    fires — not just record after the fact."""
    clock = _FakeClock()
    throttle = HostThrottle(1.0, sleep=clock.sleep, monotonic=clock.monotonic)
    throttle.wait("https://agency.gov/seed")  # concurrent worker: records t=0

    gets: list[tuple[str, float]] = []
    monkeypatch.setattr(
        fetcher, "_get_session", lambda: _FakeSession(_redirect_responder(gets, clock))
    )

    _, _, status, final_url, _ = fetcher._download(
        "https://old.example/start", on_redirect_hop=throttle.wait
    )

    old_get = next(t for host, t in gets if host == "old.example")
    agency_get = next(t for host, t in gets if host == "agency.gov")
    assert old_get == 0.0  # origin GET is not delayed by _download itself
    assert agency_get >= 1.0  # destination GET waited its per-host turn
    assert clock.slept == [1.0]  # exactly one wait, on the cross-host hop
    assert final_url == "https://agency.gov/landing"
    assert status == 200


def test_download_same_host_redirect_does_not_re_throttle(monkeypatch):
    """A same-host redirect (path-only) is one logical request already spaced by
    the origin's throttle entry, so the hop must NOT incur an extra delay."""
    clock = _FakeClock()
    throttle = HostThrottle(1.0, sleep=clock.sleep, monotonic=clock.monotonic)
    throttle.wait("https://x.gov/a")  # origin already spaced by the caller

    def _responder(url):
        if url == "https://x.gov/a":
            return _FakeResp(302, {"location": "https://x.gov/b"}, url=url)
        return _FakeResp(
            200, {"content-type": "text/html"}, content=b"<html>ok</html>", url=url
        )

    monkeypatch.setattr(fetcher, "_get_session", lambda: _FakeSession(_responder))

    fetcher._download("https://x.gov/a", on_redirect_hop=throttle.wait)
    assert clock.slept == []  # no extra courtesy wait on a same-host hop


def test_scrape_url_throttles_redirect_destination_end_to_end(tmp_path, monkeypatch):
    """Finding 3 (wiring): ``scrape_url`` forwards ``on_redirect_hop`` into the
    real manual-redirect ``_download``, so an end-to-end fetch that redirects
    cross-host waits on the destination before the hop — and still reports the
    destination as ``final_url`` while preserving the requested ``url``."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(fetcher.html_mod, "extract_text", lambda soup: "TEXT")

    clock = _FakeClock()
    throttle = HostThrottle(1.0, sleep=clock.sleep, monotonic=clock.monotonic)
    throttle.wait("https://agency.gov/seed")  # concurrent worker: records t=0

    gets: list[tuple[str, float]] = []
    monkeypatch.setattr(
        fetcher, "_get_session", lambda: _FakeSession(_redirect_responder(gets, clock))
    )

    page = fetcher.scrape_url(
        "https://old.example/start",
        force_refresh=True,
        prefer_render_on_empty=False,
        on_redirect_hop=throttle.wait,
    )

    agency_get = next(t for host, t in gets if host == "agency.gov")
    assert agency_get >= 1.0  # destination waited its per-host turn
    assert page.fetch_metadata.final_url == "https://agency.gov/landing"
    assert page.url == "https://old.example/start"  # requested url preserved
