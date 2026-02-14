import io
import os
import re
import hashlib
import json
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup as BS
from tenacity import retry, stop_after_attempt, wait_exponential
import config

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

_session = requests.Session()
_session.headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'accept-language': 'en-US,en;q=0.9',
    'user-agent': config.USER_AGENT,
}

def _get_cache_key(url):
    """
    Generates an MD5 hash for a URL to use as a cache key.
    This ensures consistent, filesystem-safe cache filenames.
    """
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def _save_to_cache(url, data):
    """
    Saves scraped page data to the local cache directory.
    Creates cache directory if it doesn't exist.
    """
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    key = _get_cache_key(url)
    path = os.path.join(config.CACHE_DIR, f"page_{key}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def _load_from_cache(url):
    """
    Retrieves previously scraped page data from the local cache.
    Returns None if the URL has not been cached.
    """
    key = _get_cache_key(url)
    path = os.path.join(config.CACHE_DIR, f"page_{key}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _download(url):
    """
    Downloads content from a URL with automatic retry logic.
    Uses exponential backoff to handle temporary network failures.
    Returns the raw content bytes and the content-type header.
    """
    r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.content, r.headers.get("content-type", "").lower()

def _extract_pdf_text(content):
    """
    Extracts all text content from a PDF document.
    Processes each page separately and combines the results.
    Returns empty string if pdfplumber is not available or extraction fails.
    """
    if not PDF_SUPPORT: return ""
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text: text_parts.append(page_text)
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return "\n\n".join(text_parts)

def _extract_pdf_links(content):
    """
    Extracts hyperlinks embedded within PDF documents.
    Uses two methods:
    1. Extracts clickable annotation links from PDF metadata
    2. Finds plain-text URLs using regex pattern matching
    Returns list of link objects with URL, anchor text, context, and source type.
    """
    if not PDF_SUPPORT: return []
    links = []
    seen = set()
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                # Extract annotated hyperlinks (clickable links)
                if page.annots:
                    for annot in page.annots:
                        if annot.get("uri"):
                            url = annot["uri"]
                            if url not in seen:
                                seen.add(url)
                                links.append({"url": url, "anchor_text": url, "context": f"PDF page {page_idx + 1}", "source": "pdf_annotation"})
                
                # Extract plain-text URLs using regex
                page_text = page.extract_text() or ""
                found = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', page_text)
                for u in found:
                    if u not in seen:
                        seen.add(u)
                        links.append({"url": u, "anchor_text": u, "context": "", "source": "pdf_text"})
    except Exception as e:
        print(f"PDF link extraction error: {e}")
    return links

def _extract_html_text(soup):
    """
    Extracts clean text from HTML with aggressive boilerplate removal.
    Removes navigation, scripts, styles, and other non-content elements.
    Prioritizes main content areas (main, article, role=main).
    Filters out short lines that are likely navigation or formatting artifacts.
    """
    # Remove noise elements that don't contain useful content
    noise_tags = ["script", "style", "noscript", "svg", "canvas", "iframe", "form"]
    structural_tags = ["header", "footer", "nav", "aside"]
    for tag in soup(noise_tags + structural_tags): tag.decompose()
    
    # Prioritize main content area if it exists
    main = soup.find("main") or soup.find("article") or soup.find(role="main")
    body = main if main else (soup.body or soup)
    
    # Extract text and filter lines
    text = body.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip() and (len(line) > 20 or not line.replace(' ', '').isalpha())]
    return "\n".join(lines)

def _extract_html_links(soup, base_url):
    """
    Task 2: Extracts links with surrounding anchor text and context.
    Converts relative URLs to absolute URLs for consistent handling.
    Captures anchor text and surrounding paragraph/list context.
    Filters out non-navigational links (javascript, anchors, mailto, tel).
    """
    links = []
    seen = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        
        # Skip non-navigational links
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")): continue
        
        # Convert to absolute URL
        url = urljoin(base_url, href)
        if url in seen: continue
        seen.add(url)
        
        # Extract surrounding context from parent element
        context = ""
        parent = a.find_parent(['p', 'li', 'div', 'td'])
        if parent:
            context = parent.get_text(strip=True)[:300]
        
        links.append({"url": url, "anchor_text": a.get_text(strip=True), "context": context, "source": "html"})
    return links

def check_keyword_proximity(text, keywords, max_distance=50):
    """
    Task 1: Validates if specified keywords appear within a set word distance.
    Algorithm:
    1. Split text into words and build position index for each keyword
    2. Track all positions where each keyword appears
    3. Check if any pair of keywords appears within max_distance words
    Returns True if at least two keywords are found within the distance threshold.
    """
    if not text: return False
    words = text.split()
    keyword_positions = {}
    
    # Build position index for each keyword
    for i, word in enumerate(words):
        clean_word = re.sub(r'\W+', '', word).lower()
        for kw in keywords:
            if kw in clean_word:
                if kw not in keyword_positions: keyword_positions[kw] = []
                keyword_positions[kw].append(i)
                break
    
    # Check if we found at least 2 different keywords
    found_keywords = list(keyword_positions.keys())
    if len(found_keywords) < 2: return False
    
    # Check all pairs of keywords for proximity
    for i in range(len(found_keywords)):
        for j in range(i + 1, len(found_keywords)):
            for pos1 in keyword_positions[found_keywords[i]]:
                for pos2 in keyword_positions[found_keywords[j]]:
                    if abs(pos1 - pos2) <= max_distance: return True
    return False

def scrape_url(url, force_refresh=False):
    """
    Fetches content from a URL and extracts text/links. Supports HTML and PDF.
    Returns a dict with:
    - text: extracted content
    - links: list of hyperlinks found
    - url: the scraped URL
    - content_type: 'html' or 'pdf'
    - success: True if content was successfully extracted
    Uses caching to avoid re-downloading the same URL unless force_refresh=True.
    """
    # Check cache first unless force refresh is requested
    if not force_refresh:
        cached = _load_from_cache(url)
        if cached: return cached
    
    print(f"Scraping: {url}")
    try:
        content, ctype = _download(url)
    except Exception as e:
        return {"text": "", "links": [], "url": url, "content_type": None, "success": False}
    
    # Route to appropriate extraction method based on content type
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        text = _extract_pdf_text(content)
        links = _extract_pdf_links(content)
        content_type = "pdf"
    else:
        soup = BS(content, "html.parser")
        text = _extract_html_text(soup)
        links = _extract_html_links(soup, url)
        content_type = "html"
    
    # Build result and save to cache
    result = {"text": text, "links": links, "url": url, "content_type": content_type, "success": bool(text)}
    _save_to_cache(url, result)
    return result