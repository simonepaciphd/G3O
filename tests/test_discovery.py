"""Discovery-layer tests.

`query_builder` is fully offline. `search_google` is exercised against the
mock-data path that triggers when SERPER_API_KEY is unset, so the test
suite runs in CI without secrets.
"""

from __future__ import annotations

import os
import threading

import pytest

from g3o.discovery import query_builder, serper_client


def test_build_queries_emits_known_languages():
    queries = query_builder.build_queries("City of Helsinki", ["en", "fi"])
    langs = {lang for _, lang in queries}
    assert langs == {"en", "fi"}
    assert all(institution_in_query(q) for q, _ in queries)


def test_build_queries_falls_back_to_english_for_unknown_language():
    queries = query_builder.build_queries("Some Ministry", ["xx"])
    assert all(lang == "xx" for _, lang in queries)
    assert all(institution_in_query(q) for q, _ in queries)
    en_queries = query_builder.build_queries("Some Ministry", ["en"])
    assert len(queries) == len(en_queries)


def test_build_queries_appends_extra_terms():
    queries = query_builder.build_queries(
        "Some Ministry", ["en"], extra_terms=["custom term"]
    )
    custom = [q for q, _ in queries if "custom term" in q]
    assert len(custom) == 1


def test_build_queries_includes_country_as_unquoted_hint():
    queries = query_builder.build_queries(
        "Ministry of Justice", ["en"], country="Turkmenistan"
    )
    assert all('"Ministry of Justice"' in q and "Turkmenistan" in q for q, _ in queries)
    assert all('"Turkmenistan"' not in q for q, _ in queries)


def institution_in_query(query: str) -> bool:
    return '"' in query and len(query) > 10


@pytest.mark.skipif(
    bool(os.getenv("SERPER_API_KEY")), reason="Mock-path test only runs without a real API key."
)
def test_search_google_returns_mock_when_key_missing():
    results = serper_client.search_google("any query", num_results=2, force_refresh=True)
    assert isinstance(results, list)
    assert len(results) >= 1
    assert "link" in results[0]


# ---------------------------------------------------------------------------
# Serper cache atomic write (Stage 1a/1b parallelization, 2026-07)
# ---------------------------------------------------------------------------


def test_save_cache_atomic_write_survives_concurrent_readers(tmp_path, monkeypatch):
    """Concurrent writers to the same cache key must never let a reader see a
    torn/partial file. Before the temp-file + os.replace fix, a plain
    open(path, "w") + json.dump could be observed mid-write by another thread
    and raise json.JSONDecodeError."""
    from g3o.common import config

    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))
    payload = serper_client.build_request_payload("concurrent atomic-write query", 5)
    data = [{"title": "t", "link": "https://x.gov/a", "snippet": "s"}]
    entry = {"results": data, "searchParameters": {}}

    errors: list[Exception] = []

    def writer() -> None:
        for _ in range(25):
            serper_client._save_cache(payload, entry)

    def reader() -> None:
        for _ in range(25):
            try:
                cached = serper_client._cached(payload)
                if cached is not None:
                    assert isinstance(cached, dict)
                    assert cached["results"] == data
            except Exception as exc:  # noqa: BLE001 - a torn read is exactly what we assert against
                errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(4)] + [
        threading.Thread(target=reader) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # No leftover temp files after every writer finished.
    assert list(tmp_path.glob("*.tmp.*")) == []
