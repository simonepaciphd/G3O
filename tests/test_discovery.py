"""Discovery-layer tests.

`query_builder` is fully offline. `search_google` is exercised against the
mock-data path that triggers when SERPER_API_KEY is unset, so the test
suite runs in CI without secrets.
"""

from __future__ import annotations

import os

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
