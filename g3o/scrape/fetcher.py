"""HTTP fetch + content-type routing.

Single entrypoint `scrape_url()` that downloads a URL once, decides whether
the response is HTML or PDF, and delegates extraction to the corresponding
sibling module.
"""

from __future__ import annotations

import hashlib
import json
import os

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from g3o.common import config
from g3o.scrape import html as html_mod
from g3o.scrape import pdf as pdf_mod

_session = requests.Session()
_session.headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": config.USER_AGENT,
}


def _cache_key(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def _save(url: str, data: dict) -> None:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, f"page_{_cache_key(url)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _load(url: str) -> dict | None:
    path = os.path.join(config.CACHE_DIR, f"page_{_cache_key(url)}.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _download(url: str) -> tuple[bytes, str]:
    r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.content, r.headers.get("content-type", "").lower()


def scrape_url(url: str, force_refresh: bool = False) -> dict:
    """Fetch a URL and return a normalized result dict.

    Result keys: text, links, url, content_type ('html' | 'pdf' | None), success.
    Caches successful scrapes on disk under `config.CACHE_DIR` keyed by URL hash.
    """
    if not force_refresh:
        cached = _load(url)
        if cached is not None:
            return cached

    try:
        content, ctype = _download(url)
    except Exception:
        return {"text": "", "links": [], "url": url, "content_type": None, "success": False}

    if "pdf" in ctype or url.lower().endswith(".pdf"):
        text = pdf_mod.extract_text(content)
        links = pdf_mod.extract_links(content)
        content_type = "pdf"
    else:
        soup = BeautifulSoup(content, "html.parser")
        text = html_mod.extract_text(soup)
        links = html_mod.extract_links(soup, url)
        content_type = "html"

    result = {
        "text": text,
        "links": links,
        "url": url,
        "content_type": content_type,
        "success": bool(text),
    }
    _save(url, result)
    return result
