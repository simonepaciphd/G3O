"""Shared-cache write safety under concurrency — Run API spec §3.4 gate.

§3.4 makes concurrent ``launch()`` support conditional on a check, not an
assumption: the ``discovery`` and ``scrape`` caches are content-hash-keyed and
shared *across* runs by design, so two runs launched in one process (or two
processes) can write the same cache key at the same moment. Both writers use the
``run_state`` pattern — per-writer temp file plus ``os.replace`` — and the
existing suite already covers the same-payload race
(``test_discovery.py::test_save_cache_atomic_write_survives_concurrent_readers``,
``test_fetcher.py::test_save_atomic_write_survives_concurrent_readers``).

What those two cannot see is the case concurrent *launches* actually produce:
two writers with **different** content under one key. Interleaving two identical
payloads is indistinguishable from an atomic write, so a torn write can hide in a
same-payload test; interleaving two different ones cannot. That is the gap these
tests close, and it is the gate the spec asks to pass before concurrent launches
are documented as supported.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from g3o.common import config
from g3o.discovery import serper_client
from g3o.scrape import fetcher
from g3o.scrape.render import FetchMetadata, RenderedPage, utc_today_iso

# Same key, two payloads that share no bytes at the position where a torn write
# would splice them: a hybrid file is therefore detectably neither payload.
PAYLOAD_A_URL = "https://a.example.gov/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
PAYLOAD_B_URL = "https://b.example.gov/bb"
WRITES_PER_THREAD = 40


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    return tmp_path / "cache"


def _run_threads(targets: list) -> None:
    threads = [threading.Thread(target=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_serper_cache_two_writers_different_payloads_same_key(_isolated_cache) -> None:
    """A reader sees payload A or payload B, whole — never a splice of the two."""
    payload = serper_client.build_request_payload("same key, two writers", 5)
    entry_a = {
        "results": [{"title": "A", "link": PAYLOAD_A_URL, "snippet": "a" * 400}],
        "searchParameters": {"writer": "A"},
    }
    entry_b = {
        "results": [{"title": "B", "link": PAYLOAD_B_URL, "snippet": "b"}],
        "searchParameters": {"writer": "B"},
    }
    errors: list[Exception] = []
    observed: set[str] = set()

    def writer(entry: dict):
        def _write() -> None:
            for _ in range(WRITES_PER_THREAD):
                serper_client._save_cache(payload, entry)

        return _write

    def reader() -> None:
        for _ in range(WRITES_PER_THREAD):
            try:
                cached = serper_client._cached(payload)
            except Exception as exc:  # noqa: BLE001 — a torn read is the failure
                errors.append(exc)
                continue
            if cached is None:
                continue
            try:
                writer_tag = cached["searchParameters"]["writer"]
                assert cached == (entry_a if writer_tag == "A" else entry_b), (
                    "cache entry is a splice of two writers' payloads"
                )
                observed.add(writer_tag)
            except (AssertionError, KeyError, TypeError) as exc:
                errors.append(exc)

    _run_threads(
        [writer(entry_a), writer(entry_b), writer(entry_a), reader, reader, reader]
    )

    assert errors == []
    assert observed, "no read ever landed — the assertion never ran"
    # The file left behind is one writer's payload in full.
    final = serper_client._cached(payload)
    assert final in (entry_a, entry_b)
    assert list(Path(config.CACHE_DIR).rglob("*.tmp.*")) == []


def _page(url: str, text: str) -> RenderedPage:
    return RenderedPage(
        url=url,
        text=text,
        title="t",
        content_type="html",
        fetch_metadata=FetchMetadata(
            access_date=utc_today_iso(),
            http_status=200,
            final_url=url,
            fetch_method="render",
            elapsed_ms=1,
            wait_for=None,
        ),
    )


def test_page_cache_two_writers_different_payloads_same_key(_isolated_cache) -> None:
    """Same race against the gzipped page cache (storage-layout-v2 §B3).

    A torn gzip stream usually fails to decompress rather than decoding to
    something plausible, so this also covers the compressed-write path — which
    the flat, uncompressed legacy layout's test never exercised.
    """
    url = "https://x.gov/concurrent-different-payloads"
    text_a = "A" * 5000
    text_b = "B" * 37
    page_a, page_b = _page(url, text_a), _page(url, text_b)
    errors: list[Exception] = []
    observed: set[str] = set()

    def writer(page: RenderedPage):
        def _write() -> None:
            for _ in range(WRITES_PER_THREAD):
                fetcher._save(page)

        return _write

    def reader() -> None:
        for _ in range(WRITES_PER_THREAD):
            try:
                cached = fetcher._load(url)
            except Exception as exc:  # noqa: BLE001 — a torn read is the failure
                errors.append(exc)
                continue
            if cached is None:
                continue
            if cached.text not in (text_a, text_b):
                errors.append(
                    AssertionError(
                        f"page cache holds neither payload whole "
                        f"({len(cached.text)} chars)"
                    )
                )
                continue
            observed.add(cached.text[0])

    _run_threads([writer(page_a), writer(page_b), writer(page_a), reader, reader, reader])

    assert errors == []
    assert observed, "no read ever landed — the assertion never ran"
    final = fetcher._load(url)
    assert final is not None and final.text in (text_a, text_b)
    assert list(Path(config.CACHE_DIR).rglob("*.tmp.*")) == []


def test_serper_cache_write_is_not_a_plain_open(_isolated_cache, monkeypatch) -> None:
    """The mechanism itself: the destination is only ever reached via os.replace.

    Behavioural, not source-grep: with ``os.replace`` neutered, the destination
    must not exist at all. A plain ``open(path, "w")`` writer would leave a file
    there, which is precisely the state a concurrent reader can catch mid-write.
    """
    payload = serper_client.build_request_payload("replace is the only path", 5)
    entry = {"results": [], "searchParameters": {}}
    calls: list[tuple[str, str]] = []

    def _no_replace(src, dst):
        calls.append((str(src), str(dst)))

    monkeypatch.setattr(serper_client.os, "replace", _no_replace)
    serper_client._save_cache(payload, entry)

    assert len(calls) == 1, "cache write did not go through os.replace"
    src, dst = calls[0]
    assert ".tmp." in src, "temp file name carries no writer identity"
    assert not Path(dst).exists(), "destination was written before the atomic swap"
    assert json.loads(Path(src).read_text(encoding="utf-8")) == entry
