"""PDF extraction helpers, optional dependency on pdfplumber."""

from __future__ import annotations

import io
import logging
import re

try:
    import pdfplumber  # type: ignore[import-untyped]

    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

logger = logging.getLogger(__name__)


def extract_text(content: bytes) -> str:
    """Concatenate per-page extracted text. Returns '' if pdfplumber is missing.

    Each page's cache is released as soon as its text has been taken. pdfplumber
    keeps every parsed page object alive for as long as the document is open, so
    without this the resident cost of one document scales with the whole
    document rather than with its largest page: measured 2026-08-25 on the
    n=4,000 corpus, a 0.7 MB PDF cost ~830 MB of RSS, and eight Stage 4 workers
    holding one such document each is the ~6 GB plateau that OOM-killed run
    r20260824T215623Z-bb4e on a 7.9 GB box.

    The two calls are pure cache eviction -- ``flush_cache`` drops the page's
    parsed objects and ``get_textmap.cache_clear`` drops its memoised text map --
    so the extracted text is unchanged. Verified byte-identical across 212 of the
    run's own banked PDFs, including every one of the 18 largest, and ~10%
    faster (the collections being rebuilt were never re-read).
    """
    if not PDF_SUPPORT:
        return ""

    parts: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
                page.flush_cache()
                page.get_textmap.cache_clear()
    except Exception as exc:
        logger.warning("PDF extraction error: %s", exc)
    return "\n\n".join(parts)


def extract_links(content: bytes) -> list[dict]:
    """Extract clickable annotation URIs and plain-text URLs.

    Each result dict carries `url`, `anchor_text`, `context`, `source`.
    `source` is 'pdf_annotation' for embedded clickables and 'pdf_text'
    for regex-recovered URLs.

    Releases each page's cache once that page has been read, for the same
    reason and by the same mechanism as `extract_text` above -- this loop has
    the identical shape and the identical unbounded retention. Unlike
    `extract_text` this function is not on Stage 4's path (`scrape_url` never
    calls it), so it did not contribute to the r20260824T215623Z-bb4e OOM.
    """
    if not PDF_SUPPORT:
        return []

    out: list[dict] = []
    seen: set[str] = set()
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                if page.annots:
                    for annot in page.annots:
                        url = annot.get("uri")
                        if url and url not in seen:
                            seen.add(url)
                            out.append(
                                {
                                    "url": url,
                                    "anchor_text": url,
                                    "context": f"PDF page {page_idx + 1}",
                                    "source": "pdf_annotation",
                                }
                            )

                page_text = page.extract_text() or ""
                for u in re.findall(r"https?://[^\s<>\"{}|\\^`\[\]]+", page_text):
                    if u not in seen:
                        seen.add(u)
                        out.append(
                            {
                                "url": u,
                                "anchor_text": u,
                                "context": "",
                                "source": "pdf_text",
                            }
                        )

                page.flush_cache()
                page.get_textmap.cache_clear()
    except Exception as exc:
        logger.warning("PDF link extraction error: %s", exc)
    return out
