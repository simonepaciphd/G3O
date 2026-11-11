"""Deterministic publication-date signals (P15 A1; T-014 capture scope).

Codebook r15 ``core.source_publication_date`` rules/0: "Take dates from HTML
metadata / PDF properties / URL patterns deterministically; if absent, the
extractor returns a date with its verbatim quote, validated by R-042."

PI rulings 2026-11-11 (``agent-workspace/2026-11-10-build/QUESTIONS-overnight.md``
A1, ``RULINGS-builds-2026-11-11.md``):

- A1.1 a: published-date signals only -- ``citation_publication_date``,
  schema.org ``datePublished``, ``article:published_time``,
  ``DC.date.issued``, PDF ``CreationDate``, plus the URL ``/YYYY/MM(/DD)/``.
- A1.2 a (signed tag order): 1 ``citation_publication_date``; 2 schema.org
  ``datePublished`` (JSON-LD or microdata); 3 ``article:published_time``
  (OpenGraph); 4 ``DC.date.issued`` / ``dcterms.issued``; 5 PDF
  ``CreationDate`` (PDF pages only). Same tag, several disagreeing values, no
  higher tag settling it: treated as absent, fall through to the URL step,
  then the quote step. URL: one match used; several distinct: treated as
  absent, fall through to the quote step.
- A1.3 a: stored pages with no measured metadata: URL test, then the quote
  step; the metadata is recorded as ``not_measured``.

This module only measures and normalises. The signed selection lives with
the consumer, :func:`g3o.common.source_fields.publication_date`.

Stored candidate shape (``RenderedPage.metadata_dates``): a list of
``{"tag", "found_as", "raw", "value"}`` dicts in document order. ``tag`` is
one of :data:`TAG_ORDER`; ``raw`` is the verbatim attribute / JSON / PDF
string; ``value`` is the normalised ``YYYY-MM-DD`` / ``YYYY-MM`` / ``YYYY``
date, or ``None`` when ``raw`` is not an accepted date form (kept for the
record, never a candidate).

Normalisation (conservative; no locale or free-text dates):

- HTML tags: ISO 8601 extended calendar forms only -- ``YYYY``, ``YYYY-MM``,
  ``YYYY-MM-DD``, and ``YYYY-MM-DD`` + ``T`` or one space + ``hh:mm[:ss[.f]]``
  + optional ``Z`` / ``+hh`` / ``+hh:mm`` / ``+hhmm``.
- PDF ``CreationDate``: the PDF date string ``[D:]YYYY[MM[DD[HH[mm[SS]]]]]``
  + optional ``Z`` / ``Z00'00'`` / ``+HH['[mm[']]]``.

The date is taken as written, in the stated offset; it is never converted to
UTC. Time and offset are validated (ranges) and dropped. The calendar date
must exist (``datetime.date``); the precision is the precision written.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

#: Version of the measurement + normalisation + URL test (pinned; bump on any change).
PRODUCER_VERSION = "g3o.common.date_signals.v1"

TAG_CITATION = "citation_publication_date"
TAG_SCHEMA = "schema.org datePublished"
TAG_OPENGRAPH = "article:published_time"
TAG_DC = "DC.date.issued / dcterms.issued"
TAG_PDF = "PDF CreationDate"
#: A1.2 a, the signed tag-priority order (highest first).
TAG_ORDER: tuple[str, ...] = (TAG_CITATION, TAG_SCHEMA, TAG_OPENGRAPH, TAG_DC, TAG_PDF)

#: The ``detail`` spelling for metadata that was not measured (reused from the
#: T-014 ``chrome_status`` / ``link_status`` "not_measured").
NOT_MEASURED = "not_measured"

_META_NAMES = {
    "citation_publication_date": TAG_CITATION,
    "article:published_time": TAG_OPENGRAPH,
    "dc.date.issued": TAG_DC,
    "dcterms.issued": TAG_DC,
}

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_ISO = re.compile(
    r"(?P<y>[0-9]{4})(?:-(?P<m>[0-9]{2})(?:-(?P<d>[0-9]{2})"
    r"(?:[T ](?P<hh>[0-9]{2}):(?P<mi>[0-9]{2})(?::(?P<ss>[0-9]{2})(?:[.,][0-9]+)?)?"
    r"(?:Z|[+-](?P<oh>[0-9]{2})(?::?(?P<om>[0-9]{2}))?)?)?)?)?"
)
_PDF = re.compile(
    r"(?:D:)?(?P<y>[0-9]{4})(?:(?P<m>[0-9]{2})(?:(?P<d>[0-9]{2})(?:(?P<hh>[0-9]{2})"
    r"(?:(?P<mi>[0-9]{2})(?:(?P<ss>[0-9]{2}))?)?)?)?)?"
    r"(?:Z(?:00'?(?:00'?)?)?|[+-](?P<oh>[0-9]{2})(?:'?(?P<om>[0-9]{2})'?)?|[+-](?P<oh2>[0-9]{2})')?"
)


def _from_match(m: re.Match[str]) -> str | None:
    g = m.groupdict()
    y, mo, d = g["y"], g["m"], g["d"]
    limits = (("hh", 23), ("mi", 59), ("ss", 60), ("oh", 23), ("om", 59), ("oh2", 23))
    for key, top in limits:
        val = g.get(key)
        if val is not None and int(val) > top:
            return None
    try:
        if d is not None:
            date(int(y), int(mo), int(d))
            return f"{y}-{mo}-{d}"
        if mo is not None:
            date(int(y), int(mo), 1)
            return f"{y}-{mo}"
        date(int(y), 1, 1)
        return y
    except ValueError:
        return None


def normalise_iso(raw: str | None) -> str | None:
    """An accepted ISO 8601 form -> ``YYYY-MM-DD`` / ``YYYY-MM`` / ``YYYY``; else None."""
    if not isinstance(raw, str):
        return None
    m = _ISO.fullmatch(raw.strip())
    return _from_match(m) if m else None


def normalise_pdf(raw: str | None) -> str | None:
    """A PDF date string -> ``YYYY-MM-DD`` / ``YYYY-MM`` / ``YYYY``; else None."""
    if not isinstance(raw, str):
        return None
    m = _PDF.fullmatch(raw.strip())
    return _from_match(m) if m else None


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def _candidate(tag: str, found_as: str, raw: Any) -> dict[str, Any]:
    raw_s = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
    norm = normalise_pdf(raw_s) if tag == TAG_PDF else normalise_iso(raw_s)
    return {"tag": tag, "found_as": found_as, "raw": raw_s, "value": norm}


def _attr(tag: Any, name: str) -> str | None:
    val = tag.get(name)
    if isinstance(val, list):  # bs4 multi-valued attributes
        val = " ".join(val)
    return val


def _jsonld_values(node: Any) -> Iterator[Any]:
    """Every ``datePublished`` value in a JSON-LD document, depth-first, in order."""
    if isinstance(node, Mapping):
        for key, val in node.items():
            if key == "datePublished":
                vals = val if isinstance(val, list) else [val]
                for v in vals:
                    yield v.get("@value") if isinstance(v, Mapping) else v
            else:
                yield from _jsonld_values(val)
    elif isinstance(node, list):
        for item in node:
            yield from _jsonld_values(item)


_SCHEMA_TYPE = re.compile(r"^https?://(www\.)?schema\.org/", re.IGNORECASE)


def _microdata_scope_is_schema_org(el: Any) -> bool:
    scope = el.find_parent(attrs={"itemscope": True})
    if scope is None:
        return False
    itemtype = _attr(scope, "itemtype") or ""
    return any(_SCHEMA_TYPE.match(t) for t in itemtype.split())


def html_date_candidates(soup: Any) -> list[dict[str, Any]]:
    """The A1.1 a HTML signals of a parsed page, in document order (never mutates ``soup``).

    ``<meta name|property>`` for ``citation_publication_date``,
    ``article:published_time``, ``DC.date.issued`` / ``dcterms.issued`` (names
    compared case-insensitively); schema.org ``datePublished`` from JSON-LD
    (``<script type="application/ld+json">``, every node) and from microdata
    (``itemprop`` token ``datePublished`` inside an ``itemscope`` whose
    ``itemtype`` is on schema.org; value from ``content``, else a ``<time>``
    ``datetime``, else the element text). Must run before
    :func:`g3o.scrape.html.extract_text`, which removes ``<script>`` tags.
    """
    out: list[dict[str, Any]] = []
    for el in soup.find_all(True):
        name = el.name
        if name == "meta":
            seen: set[str] = set()
            for attr in ("name", "property"):
                key = (_attr(el, attr) or "").strip().lower()
                tag = _META_NAMES.get(key)
                if tag is not None and tag not in seen:
                    seen.add(tag)
                    out.append(_candidate(tag, f"meta {attr}={_attr(el, attr)}", _attr(el, "content")))
        if name == "script" and (_attr(el, "type") or "").split(";")[0].strip().lower() == "application/ld+json":
            try:
                doc = json.loads(el.string if el.string is not None else el.get_text())
            except (TypeError, ValueError):
                continue
            for v in _jsonld_values(doc):
                out.append(_candidate(TAG_SCHEMA, "json-ld", v))
            continue
        itemprop = _attr(el, "itemprop")
        if itemprop and "datePublished" in itemprop.split() and _microdata_scope_is_schema_org(el):
            if name == "meta":
                raw = _attr(el, "content")
            elif name == "time" and _attr(el, "datetime") is not None:
                raw = _attr(el, "datetime")
            else:
                raw = el.get_text(strip=True)
            out.append(_candidate(TAG_SCHEMA, "microdata", raw))
    return out


def pdf_date_candidates(metadata: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The PDF ``CreationDate`` of a PDF document-info dictionary (pdfplumber ``pdf.metadata``)."""
    if not metadata or metadata.get("CreationDate") is None:
        return []
    raw = metadata["CreationDate"]
    if isinstance(raw, bytes):
        raw = raw.decode("latin-1")
    return [_candidate(TAG_PDF, "pdf info", raw)]


# ---------------------------------------------------------------------------
# URL test
# ---------------------------------------------------------------------------

#: ``/YYYY/MM/`` or ``/YYYY/MM/DD/`` (the trailing slash is part of the signed pattern).
_URL_DATE = re.compile(r"/(?P<y>[0-9]{4})/(?P<m>[0-9]{2})(?:/(?P<d>[0-9]{2}))?(?=/)")


def url_dates(url: str) -> list[str]:
    """Every valid ``/YYYY/MM(/DD)/`` date in the URL, in order (duplicates kept).

    A match whose month or day is not a real calendar date is not a match.
    """
    out: list[str] = []
    for m in _URL_DATE.finditer(url):
        y, mo, d = m.group("y"), m.group("m"), m.group("d")
        try:
            if d is not None:
                date(int(y), int(mo), int(d))
                out.append(f"{y}-{mo}-{d}")
            else:
                date(int(y), int(mo), 1)
                out.append(f"{y}-{mo}")
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------------
# Page inputs for publication_date
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageDateInputs:
    """What :func:`g3o.common.source_fields.publication_date` takes for one page.

    ``metadata_dates`` is None only when neither the metadata measurement nor
    the URL test could run. ``metadata_measured`` False = A1.3 a (stored page,
    metadata not measured; only the URL test ran).
    """

    metadata_dates: tuple[Any, ...] | None  # MetadataDate entries
    metadata_measured: bool


def page_date_inputs(candidates: Sequence[Mapping[str, Any]] | None, url: str | None) -> PageDateInputs:
    """Stored candidates (``RenderedPage.metadata_dates``) + supplied URL -> MetadataDate entries."""
    from g3o.common.source_fields import MetadataDate  # local: source_fields imports this module

    has_url = isinstance(url, str) and bool(url.strip())
    if candidates is None and not has_url:
        return PageDateInputs(None, False)
    dates: list[Any] = []
    for c in candidates or ():
        if c.get("tag") not in TAG_ORDER:
            raise ValueError(f"stored date candidate tag {c.get('tag')!r} is not a signed A1.1 a signal")
        if c.get("value") is None:
            continue
        dates.append(MetadataDate(c["value"], "metadata", f"{c['found_as']}: {c['raw']}", tag=c["tag"]))
    if has_url:
        for value in url_dates(url):  # type: ignore[arg-type]
            dates.append(MetadataDate(value, "web_address", f"URL pattern /YYYY/MM(/DD)/ -> {value}"))
    return PageDateInputs(tuple(dates), candidates is not None)


__all__ = [
    "NOT_MEASURED", "PRODUCER_VERSION", "TAG_CITATION", "TAG_DC", "TAG_OPENGRAPH", "TAG_ORDER", "TAG_PDF",
    "TAG_SCHEMA", "PageDateInputs", "html_date_candidates", "normalise_iso", "normalise_pdf",
    "page_date_inputs", "pdf_date_candidates", "url_dates",
]
