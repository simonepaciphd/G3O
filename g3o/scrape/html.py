"""HTML extraction helpers."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

NOISE_TAGS = ["script", "style", "noscript", "svg", "canvas", "iframe", "form"]
STRUCTURAL_TAGS = ["header", "footer", "nav", "aside"]


def extract_text(soup: BeautifulSoup) -> str:
    """Extract main-content text from a parsed HTML document.

    Strips scripts/styles/iframes and structural chrome (header, footer,
    nav, aside), prefers `<main>` / `<article>` / `role=main`, then keeps
    only lines longer than 20 chars or containing non-letter characters.
    """
    for tag in soup(NOISE_TAGS + STRUCTURAL_TAGS):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find(role="main")
    body = main if main else (soup.body or soup)

    text = body.get_text(separator="\n", strip=True)
    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip() and (len(line) > 20 or not line.replace(" ", "").isalpha())
    ]
    return "\n".join(lines)


def extract_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract anchor links with surrounding context.

    Skips javascript/anchor/mailto/tel hrefs, normalizes relative URLs to
    absolute, dedupes by URL, and captures up to 300 characters of parent
    paragraph/list context.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue

        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)

        context = ""
        parent = a.find_parent(["p", "li", "div", "td"])
        if parent:
            context = parent.get_text(strip=True)[:300]

        out.append(
            {
                "url": url,
                "anchor_text": a.get_text(strip=True),
                "context": context,
                "source": "html",
            }
        )
    return out


def check_keyword_proximity(text: str, keywords: list[str], max_distance: int = 50) -> bool:
    """Return True if at least two distinct keywords appear within `max_distance` words.

    Used by the discovery layer as a coarse relevance filter before
    sending a page on to extraction.
    """
    if not text:
        return False

    words = text.split()
    positions: dict[str, list[int]] = {}
    for i, word in enumerate(words):
        clean = re.sub(r"\W+", "", word).lower()
        for kw in keywords:
            if kw in clean:
                positions.setdefault(kw, []).append(i)
                break

    found = list(positions.keys())
    if len(found) < 2:
        return False

    for i in range(len(found)):
        for j in range(i + 1, len(found)):
            for p1 in positions[found[i]]:
                for p2 in positions[found[j]]:
                    if abs(p1 - p2) <= max_distance:
                        return True
    return False
