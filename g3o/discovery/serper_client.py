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
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from g3o.common import config

logger = logging.getLogger(__name__)

# One-shot flag: warn the operator the first time we silently fall back to
# mock results because SERPER_API_KEY is unset. Repeats would just spam logs.
_warned_mock = False


def _cache_key(query: str) -> str:
    return hashlib.md5(query.encode("utf-8")).hexdigest()


def _cached(query: str) -> list[dict] | None:
    path = os.path.join(config.CACHE_DIR, f"serp_{_cache_key(query)}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cache(query: str, data: list[dict]) -> None:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, f"serp_{_cache_key(query)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _execute(query: str, num_results: int = 10) -> dict:
    """POST to Serper with retry. Returns mock data when SERPER_API_KEY is unset."""
    if not config.SERPER_API_KEY:
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
        cached = _cached(query)
        if cached is not None:
            return cached

    try:
        data = _execute(query, num_results)
    except Exception as exc:  # network / Serper error
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

    _save_cache(query, results)
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
