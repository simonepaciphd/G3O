import io
import os
import re
import hashlib
import json
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup as BS
from tenacity import retry, stop_after_attempt, wait_exponential

from . import config

# --- Session Setup ---
_session = requests.Session()
_session.headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'user-agent': config.USER_AGENT,
}

# --- Caching ---
def _get_cache_key(url):
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def _save_to_cache(url, text, links):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    key = _get_cache_key(url)
    data = {"url": url, "text": text, "links": links}
    path = os.path.join(config.CACHE_DIR, f"page_{key}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def _load_from_cache(url):
    key = _get_cache_key(url)
    path = os.path.join(config.CACHE_DIR, f"page_{key}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

# --- Download ---
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _download(url):
    r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.content, r.headers.get("content-type", "").lower()

# --- Extraction ---
def _extract_html_text(soup):
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    
    # Simple strategy: get clean text
    text = soup.get_text(separator="\n", strip=True)
    return text

def scrape_url(url, force_refresh=False):
    """
    Scrapes a URL and returns extracted text.
    """
    # Check cache
    if not force_refresh:
        cached = _load_from_cache(url)
        if cached:
            return cached
    
    print(f"Scraping: {url}")
    
    try:
        content, ctype = _download(url)
    except Exception as e:
        print(f"Download failed for {url}: {e}")
        return {"text": "", "url": url}
    
    text = ""
    # Assume HTML for MVP
    try:
        soup = BS(content, "html.parser")
        text = _extract_html_text(soup)
    except Exception:
        text = ""

    _save_to_cache(url, text, [])
    return {"text": text, "url": url}
