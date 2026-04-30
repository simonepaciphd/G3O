"""PDF extraction helpers, optional dependency on pdfplumber."""

from __future__ import annotations

import io
import re

try:
    import pdfplumber  # type: ignore[import-untyped]

    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


def extract_text(content: bytes) -> str:
    """Concatenate per-page extracted text. Returns '' if pdfplumber is missing."""
    if not PDF_SUPPORT:
        return ""

    parts: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
    except Exception as exc:
        print(f"PDF extraction error: {exc}")
    return "\n\n".join(parts)


def extract_links(content: bytes) -> list[dict]:
    """Extract clickable annotation URIs and plain-text URLs.

    Each result dict carries `url`, `anchor_text`, `context`, `source`.
    `source` is 'pdf_annotation' for embedded clickables and 'pdf_text'
    for regex-recovered URLs.
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
    except Exception as exc:
        print(f"PDF link extraction error: {exc}")
    return out
