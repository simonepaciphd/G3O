"""SERP cache-key backend/engine namespacing.

The SERP cache key is derived from the request *payload* (``_cache_key`` hashes
the whole dict POSTed to Serper — see the payload-derived-key redesign,
2026-08-01). Today Serper is the sole search backend, so the ``engine`` tag is
inert. The moment a second backend exists, two backends issuing the *same*
request payload (same query + num_results + options) would hash to the *same*
cache key and share one on-disk entry — whichever ran first would silently
serve its results to the other backend's caller (silent-wrong-results).

``engine`` is a cache-partition tag, not a request parameter: it is prefixed
onto the hashed blob rather than folded into ``payload``, so it never reaches
the wire or the stored ``searchParameters`` provenance (which keeps ``payload``
byte-faithful to what Serper received). This mirrors the way ``num_results``
and every option field are already covered by the key; these tests assert the
analogous invariant for the backend identifier.
"""

from __future__ import annotations

from g3o.common import config
from g3o.discovery import serper_client


def test_cache_key_namespaced_by_engine():
    """Same payload, different backend identifier -> different key."""
    payload = serper_client.build_request_payload("genai policy ministry", 10)
    key_a = serper_client._cache_key(payload, engine="serper")
    key_b = serper_client._cache_key(payload, engine="bing")
    assert key_a != key_b, (
        "cache key must be namespaced by backend/engine: two backends issuing "
        "the same payload must not collide"
    )


def test_cache_key_default_engine_is_serper():
    """The default (no engine arg) is the ``serper`` namespace, so existing
    call sites keep hitting the same entries after the fix."""
    payload = serper_client.build_request_payload("genai policy ministry", 10)
    assert serper_client._cache_key(payload) == serper_client._cache_key(
        payload, engine="serper"
    )


def test_cache_path_namespaced_by_engine():
    """The on-disk path differs by engine (namespacing lives in the hash, not
    a per-engine filename prefix)."""
    payload = serper_client.build_request_payload("some query", 10)
    path_a = serper_client._cache_path(payload, engine="serper")
    path_b = serper_client._cache_path(payload, engine="bing")
    assert path_a != path_b


def test_cache_entries_isolated_by_engine(tmp_path, monkeypatch):
    """A cache entry written under one backend must not be served to another.

    Exercises the full on-disk path (_save_cache -> _cached), which is what a
    caller actually hits — key inequality alone is necessary but not sufficient.
    """
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))
    payload = serper_client.build_request_payload("identical query string", 5)
    entry_a = {
        "results": [{"title": "from serper", "link": "https://a.gov/x", "snippet": "s"}],
        "searchParameters": {"q": "identical query string", "num": 5},
    }

    serper_client._save_cache(payload, entry_a, engine="serper")

    # A different backend asking for the same payload must miss — never receive
    # serper's cached entry.
    assert serper_client._cached(payload, engine="bing") is None, (
        "a second backend must not read the first backend's cache entry"
    )
    # The originating backend still gets its own entry back — including via the
    # default engine, which is what the pipeline's own call sites use.
    assert serper_client._cached(payload, engine="serper") == entry_a
    assert serper_client._cached(payload) == entry_a
