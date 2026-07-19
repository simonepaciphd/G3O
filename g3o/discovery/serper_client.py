"""Serper.dev Google Search API client.

Ported from the pre-restructure `src/search_serper.py`. The pipeline calls
`search_google()` with institution-scoped queries from `query_builder`; the
multi-strategy and entity helpers below cover the cases where we need to
identify an institution's homepage or scope a query to a known domain.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from g3o.common import config

logger = logging.getLogger(__name__)

# One-shot flag: warn the operator the first time we silently fall back to
# mock results because SERPER_API_KEY is unset. Repeats would just spam logs.
_warned_mock = False

# Sentinel substring embedded in the mock-result URLs. The cache guard refuses
# to write any payload containing it so a mock result can never poison the
# shared on-disk cache again (review F1c, 2026-06-10).
_MOCK_LINK_SENTINEL = "g3o-mock"

# Live (``--execute``) mode. When True, the mock fallback is disabled and a
# missing key or a failed request is a hard error rather than a silent mock or
# empty-result — an empty artifact must mean the search actually ran and found
# nothing (review F1, 2026-06-10). The presweep orchestrator sets this at
# ``--execute`` startup; it stays False for dev/CLI use and dry runs.
_live_mode = False


class SerperConfigError(RuntimeError):
    """SERPER_API_KEY is unset while live (``--execute``) mode is active."""


class SerperRequestError(RuntimeError):
    """A Serper request failed (quota/403/network) after retries in live mode.

    Distinct from "searched, found nothing": callers persist this as an
    explicit failure (attrition ledger + error marker), never as an empty
    result artifact.
    """


def set_live_mode(enabled: bool) -> None:
    """Enable/disable live mode (no mock, honest failures). Set by presweep."""
    global _live_mode
    _live_mode = enabled


def _contains_mock(data: list[dict]) -> bool:
    return any(_MOCK_LINK_SENTINEL in (r.get("link") or "") for r in data)


def _cache_key(query: str, num_results: int) -> str:
    # num_results is part of the key: two queries differing only in result count
    # are not interchangeable cache hits (review F17, 2026-06-10).
    return hashlib.md5(f"{num_results}:{query}".encode()).hexdigest()


def _cached(query: str, num_results: int) -> list[dict] | None:
    path = os.path.join(config.CACHE_DIR, f"serp_{_cache_key(query, num_results)}.json")
    # Concurrent-read retry (Stage 1a/1b concurrency, 2026-07): a reader's
    # open() can transiently lose a Windows sharing-violation race against
    # another thread's os.replace() landing on this exact path (the atomic
    # write itself is still correct — the reader only ever sees a torn file
    # or this transient error, never partial content). Bounded retry clears
    # it; a no-op on POSIX, which doesn't raise for this reason.
    for attempt in range(5):
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (PermissionError, FileNotFoundError):
            if attempt == 4:
                raise
            time.sleep(0.01 * (attempt + 1))
    return None


def _save_cache(query: str, num_results: int, data: list[dict]) -> None:
    if _contains_mock(data):
        # Belt-and-suspenders: in live mode mock is never produced, but a dev
        # session must not seed the shared cache with mock URLs (review F1c).
        logger.debug("Refusing to cache mock SERP results for query %r", query)
        return
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, f"serp_{_cache_key(query, num_results)}.json")
    # Atomic write (Stage 1a/1b concurrency, 2026-07): two worker threads can
    # race on the same cache key (identical query + num_results). A plain
    # open(path, "w") lets a concurrent reader observe a torn/partial file; a
    # per-writer temp file + os.replace makes the swap atomic. The temp name
    # includes pid + thread id so two concurrent writers never collide on the
    # same temp path before either replace() lands.
    tmp_path = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    # Windows can transiently deny os.replace with PermissionError while
    # another thread's open(path) (a concurrent _cached() read) still holds
    # the destination — Windows files aren't opened with FILE_SHARE_DELETE by
    # default, unlike POSIX rename which never raises for this reason. The
    # reader's open/read/close window is brief, so a short bounded retry
    # clears it; this loop is a no-op (succeeds first try) on POSIX.
    for attempt in range(5):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * (attempt + 1))


def _mock_response() -> dict:
    """Dev-mode mock payload (one-shot warning). Never cached (see _save_cache)."""
    global _warned_mock
    if not _warned_mock:
        logger.warning(
            "SERPER_API_KEY unset — returning MOCK results; live discovery is OFF"
        )
        _warned_mock = True
    return {
        "organic": [
            {"title": "Mock Result 1", "link": "https://example.com/g3o-mock", "snippet": "Mock GenAI policy."},
            {"title": "Mock Result 2", "link": "https://example.org/g3o-mock.pdf", "snippet": "Mock guidelines."},
        ]
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _execute(query: str, num_results: int = 10) -> dict:
    """POST to Serper with retry. Assumes a key is present (callers gate on it).

    The retry wraps only the network call — the missing-key / mock decision
    lives in :func:`search_google`, so a config error is never retried or
    wrapped in a tenacity ``RetryError``.
    """
    headers = {"X-API-KEY": config.SERPER_API_KEY, "Content-Type": "application/json"}
    payload = json.dumps({"q": query, "num": num_results})
    response = requests.post(
        config.SERPER_ENDPOINT, headers=headers, data=payload, timeout=config.REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def search_google(query: str, num_results: int = 10, force_refresh: bool = False) -> list[dict]:
    """Run a Serper query and return normalized organic results.

    Each result dict has keys: title, link, snippet, domain, position, date, sitelinks.
    """
    if not force_refresh:
        cached = _cached(query, num_results)
        if cached is not None:
            return cached

    if not config.SERPER_API_KEY:
        if _live_mode:
            # Missing key in live mode is a hard error — never degrade to mock.
            raise SerperConfigError(
                "SERPER_API_KEY is unset but live (--execute) discovery is active. "
                "Refusing to return mock results. Set SERPER_API_KEY before running "
                "--execute, or run a dry run."
            )
        data = _mock_response()
    else:
        try:
            data = _execute(query, num_results)
        except Exception as exc:  # network / Serper error (quota, 403, timeout)
            if _live_mode:
                # Honest failure: an empty artifact must mean "searched, found
                # nothing", so a failed request raises rather than returning [].
                raise SerperRequestError(
                    f"Serper request failed for query {query!r}: {exc}"
                ) from exc
            logger.warning("Search failed: %s", exc)
            return []

    results: list[dict] = []
    for idx, item in enumerate(data.get("organic", [])):
        results.append(
            {
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet"),
                "domain": _domain(item.get("link", "")),
                "position": item.get("position", idx + 1),
                "date": item.get("date"),
                "sitelinks": item.get("sitelinks", []),
            }
        )

    _save_cache(query, num_results, results)
    return results


def build_site_query(query: str, site_domain: str) -> str:
    """Wrap a query with Google's `site:` operator."""
    return f"site:{site_domain} {query}"


def build_filetype_query(query: str, filetype: str = "pdf") -> str:
    """Wrap a query with Google's `filetype:` operator."""
    return f"{query} filetype:{filetype}"


def search_entity_homepage(entity_name: str, entity_type: str = "government institution") -> dict:
    """Best-effort homepage discovery for a named entity."""
    query = f'"{entity_name}" official website {entity_type}'
    results = search_google(query, num_results=5)
    if not results:
        results = search_google(f"{entity_name} {entity_type}", num_results=5)
    if results:
        return {
            "homepage": results[0].get("link"),
            "domain": results[0].get("domain"),
            "confidence": "high",
        }
    return {"homepage": None, "domain": None, "confidence": "none"}


def search_entity_with_site_scope(
    entity_name: str, topic: str, homepage_domain: str | None = None
) -> list[dict]:
    """Scope a topic search to an entity's known (or discoverable) homepage."""
    if not homepage_domain:
        homepage_domain = search_entity_homepage(entity_name).get("domain")

    if homepage_domain:
        return search_google(build_site_query(topic, homepage_domain), num_results=10)
    return search_google(f"{entity_name} {topic}", num_results=10)


def multi_strategy_search(
    entity_name: str, topic: str, num_results_per_strategy: int = 5
) -> list[dict]:
    """Run several query patterns against Serper and dedupe by URL.

    Each result carries a `search_strategy` field naming the query that found it,
    which downstream layers use for provenance and ranking.
    """
    strategies = [
        f'"{entity_name}" "{topic}"',
        f"{entity_name} {topic}",
        f"{entity_name} {topic} policy",
        f"{entity_name} {topic} announcement",
        build_filetype_query(f"{entity_name} {topic}", "pdf"),
    ]

    seen: set[str] = set()
    out: list[dict] = []
    for query in strategies:
        for r in search_google(query, num_results=num_results_per_strategy):
            url = r.get("link", "")
            if url and url not in seen:
                seen.add(url)
                r["search_strategy"] = query
                out.append(r)
    return out
