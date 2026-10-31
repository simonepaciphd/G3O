"""HTML extraction helpers."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
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


def extract_chrome_text(soup: BeautifulSoup) -> str:
    """Extract the structural chrome text that :func:`extract_text` strips.

    RC-D-002 F (PI ruling N1 a, 2026-10-29): the header / footer / nav / aside
    text is kept as its own field rather than discarded, so the contact item
    and CX-53 e-mail extraction can read it. Main text is not affected: this
    function never mutates ``soup`` (it works on copies of the chrome
    elements), so calling it before :func:`extract_text` on the same soup
    leaves the main-text output byte-identical.

    Only outermost chrome elements are read (a ``nav`` inside a ``header`` is
    counted once, with its header). Noise tags inside a chrome element are
    dropped, as :func:`extract_text` drops them. Chrome elements nested inside
    a noise tag (e.g. a ``nav`` in a ``form``) are skipped, since
    :func:`extract_text` removes them as noise, not as chrome. Every non-empty
    stripped line is kept: the main-text short-line filter is NOT applied, so
    short chrome lines such as "Contact" survive. Elements are joined in
    document order with a newline.
    """
    parts: list[str] = []
    for tag in soup.find_all(STRUCTURAL_TAGS):
        if tag.find_parent(STRUCTURAL_TAGS) is not None:
            continue
        if tag.find_parent(NOISE_TAGS) is not None:
            continue
        clone = copy.copy(tag)
        for noise in clone(NOISE_TAGS):
            noise.decompose()
        text = clone.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if lines:
            parts.append("\n".join(lines))
    return "\n".join(parts)


@dataclass(frozen=True)
class HtmlParts:
    """Main text, chrome text and links of one HTML page (RC-D-002 F)."""

    text: str
    chrome_text: str
    links: list[dict] = field(default_factory=list)


def extract_parts(soup: BeautifulSoup, base_url: str) -> HtmlParts:
    """Main text, chrome text and links of a parsed page, in one call.

    Order matters: :func:`extract_text` decomposes the chrome and noise tags
    in place, so the chrome text and the links (which include nav and footer
    links) are read first, from the intact soup. ``text`` is exactly what
    :func:`extract_text` returns for the page.
    """
    chrome_text = extract_chrome_text(soup)
    links = extract_links(soup, base_url)
    text = extract_text(soup)
    return HtmlParts(text=text, chrome_text=chrome_text, links=links)


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
