"""
G3O Scraper Module
==================
Handles fetching and text extraction from URLs.
Supports: HTML, PDF, DOCX.
Includes: caching, retry logic, flexible text extraction, link extraction with context.
"""

import io
import os
import re
import hashlib
import json
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup as BS
from tenacity import retry, stop_after_attempt, wait_exponential

from . import config

# Optional imports (graceful degradation)
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    print("Warning: pdfplumber not installed. PDF extraction disabled.")

try:
    import docx
    DOCX_SUPPORT = True
except ImportError:
    DOCX_SUPPORT = False

# --- Session Setup ---
_session = requests.Session()
_session.headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'accept-language': 'en-US,en;q=0.9',
    'user-agent': config.USER_AGENT,
}

# --- Caching ---
def _get_cache_key(url):
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def _save_to_cache(url, data):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    key = _get_cache_key(url)
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
    """Downloads URL content with retry logic."""
    r = _session.get(url, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.content, r.headers.get("content-type", "").lower()

# --- PDF Extraction ---
def _extract_pdf_text(content):
    """Extract text from PDF content."""
    if not PDF_SUPPORT:
        return ""
    
    text_parts = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return "\n\n".join(text_parts)

def _extract_pdf_links(content):
    """Extract links from PDF."""
    if not PDF_SUPPORT:
        return []
    
    links = []
    seen = set()
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                # Check annotations for links
                if page.annots:
                    for annot in page.annots:
                        if annot.get("uri"):
                            url = annot["uri"]
                            if url not in seen:
                                seen.add(url)
                                links.append({
                                    "url": url,
                                    "anchor_text": url,
                                    "context": f"PDF page {page_idx + 1}",
                                    "source": "pdf_annotation"
                                })
                # Regex find URLs in text
                page_text = page.extract_text() or ""
                found = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', page_text)
                for u in found:
                    if u not in seen:
                        seen.add(u)
                        links.append({
                            "url": u,
                            "anchor_text": u,
                            "context": "",
                            "source": "pdf_text"
                        })
    except Exception as e:
        print(f"PDF link extraction error: {e}")
    return links

# --- DOCX Extraction ---
def _extract_docx_text(content):
    """Extract text from DOCX content."""
    if not DOCX_SUPPORT:
        return ""
    try:
        doc = docx.Document(io.BytesIO(content))
        return "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
    except Exception as e:
        print(f"DOCX extraction error: {e}")
        return ""

# --- HTML Extraction ---

# Elements to remove completely
NOISE_TAGS = ["script", "style", "noscript", "svg", "canvas", "iframe", "form"]
STRUCTURAL_TAGS = ["header", "footer", "nav", "aside"]

# Common boilerplate class/id patterns
BOILERPLATE_PATTERNS = [
    r'cookie', r'consent', r'gdpr', r'banner', r'popup', r'modal',
    r'sidebar', r'widget', r'advert', r'sponsor', r'promo',
    r'newsletter', r'subscribe', r'social', r'share', r'comment',
    r'related', r'recommended', r'footer', r'header', r'menu', r'nav'
]

def _is_boilerplate(element):
    """Check if element is likely boilerplate based on class/id."""
    classes = ' '.join(element.get('class', []))
    element_id = element.get('id', '')
    combined = f"{classes} {element_id}".lower()
    
    for pattern in BOILERPLATE_PATTERNS:
        if re.search(pattern, combined):
            return True
    return False

def _extract_html_text(soup):
    """
    Extracts clean text from HTML with aggressive boilerplate removal.
    """
    # Remove noise elements
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    
    # Remove structural elements that rarely contain main content
    for tag in soup(STRUCTURAL_TAGS):
        tag.decompose()
    
    # Remove elements with boilerplate class/id patterns
    for element in soup.find_all(True):  # All elements
        if _is_boilerplate(element):
            element.decompose()
    
    # Try semantic containers first
    main = soup.find("main") or soup.find("article") or soup.find(role="main")
    
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        # Fallback: get all text from body
        body = soup.body or soup
        text = body.get_text(separator="\n", strip=True)
    
    # Clean up excessive whitespace
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Remove very short lines that are often menu items
    lines = [line for line in lines if len(line) > 20 or not line.replace(' ', '').isalpha()]
    
    return "\n".join(lines)

def _extract_html_links(soup, base_url):
    """
    Extract links with surrounding context (anchor text + nearby text).
    """
    links = []
    seen = set()
    
    for a in soup.select("a[href]"):
        anchor_text = a.get_text(strip=True)
        href = a.get("href", "")
        
        # Skip empty/invalid links
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        
        # Resolve relative URLs
        url = urljoin(base_url, href)
        
        if url in seen:
            continue
        seen.add(url)
        
        # Get context: surrounding text (parent paragraph or nearby text)
        context = ""
        parent = a.find_parent(['p', 'li', 'div', 'td'])
        if parent:
            parent_text = parent.get_text(strip=True)
            # Limit context length
            if len(parent_text) > 300:
                parent_text = parent_text[:300] + "..."
            context = parent_text
        
        links.append({
            "url": url,
            "anchor_text": anchor_text,
            "context": context,
            "source": "html"
        })
    
    return links

# --- Main Scrape Function ---
def scrape_url(url, force_refresh=False):
    """
    Scrapes a URL and returns extracted text, links, and metadata.
    
    Returns dict with:
    - text: Cleaned main content
    - links: List of {url, anchor_text, context}
    - url: Original URL
    - content_type: Detected content type
    - success: Boolean
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
        return {"text": "", "links": [], "url": url, "content_type": None, "success": False}
    
    text = ""
    links = []
    
    # Determine content type and extract
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        text = _extract_pdf_text(content)
        links = _extract_pdf_links(content)
        content_type = "pdf"
    elif "word" in ctype or "docx" in ctype or url.lower().endswith(".docx"):
        text = _extract_docx_text(content)
        links = []
        content_type = "docx"
    else:
        # HTML
        soup = BS(content, "html.parser")
        text = _extract_html_text(soup)
        links = _extract_html_links(soup, url)
        content_type = "html"
    
    result = {
        "text": text,
        "links": links,
        "url": url,
        "content_type": content_type,
        "success": bool(text)
    }
    
    # Cache result
    _save_to_cache(url, result)
    
    return result


def scrape_urls_batch(urls, force_refresh=False):
    """
    Scrape multiple URLs. Returns list of results.
    """
    results = []
    for url in urls:
        result = scrape_url(url, force_refresh=force_refresh)
        results.append(result)
    return results
