"""Deterministic publication-date signals (P15 A1; T-014 capture scope).

Codebook r15 ``core.source_publication_date`` rules/0: "Take dates from HTML
metadata / PDF properties / URL patterns deterministically; if absent, the
extractor returns a date with its verbatim quote, validated by R-042."

PI rulings 2026-11-11 (A1 build questions, rulings A1.1-A1.3):

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

v2 (PI rulings 16-20 on the A1 build questions, 2026-11-11):

- 17 b: JSON-LD ``datePublished`` only from top-level nodes and nodes directly
  under ``@graph`` (:func:`_jsonld_values`); nested nodes (comments, the
  containing site, related items) are not read.
- 18 b (kept strict, PI ruling R4 a, 2026-11-12): a date before
  :data:`EARLIEST_DATE` or strictly after the page's access date (the UTC
  ``fetch_metadata.access_date``) is not a candidate (:func:`in_window`); the
  stored candidate keeps its raw and normalised value, and
  :func:`page_date_inputs` leaves it out of selection and lists it in
  ``PageDateInputs.out_of_window``, which the result's ``detail`` carries as
  ``out_of_window`` (procedural ruling, 2026-11-12). A partial date is out of
  window only if its whole period is (``2024`` is in window on 2024-05-01).
- 20: the URL date is matched on the path only (:func:`url_dates`); ``D:``
  stays optional on PDF dates.
- 16 b (selection, :func:`g3o.common.source_fields.select_deterministic_date`):
  within one tag, a date that is a prefix of a more precise one is consistent;
  the most precise is taken.

v3 (PI ruling R3 b, 2026-11-12): rendered pages are measured too. The render
path reads the rendered DOM HTML from the same page load and runs
:func:`html_date_candidates` on it (:mod:`g3o.scrape.render`); before v3 a
rendered page was not measured.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlsplit

#: Version of the measurement + normalisation + URL test (pinned; bump on any change).
PRODUCER_VERSION = "g3o.common.date_signals.v3"  # v3: R3 b render pages measured (2026-11-12)

#: Ruling 18 b: no candidate date before this day (before the web and PDF existed).
EARLIEST_DATE = date(1990, 1, 1)

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


def _jsonld_values(doc: Any) -> Iterator[Any]:
    """``datePublished`` values of a JSON-LD document's top-level nodes and the nodes directly
    under their ``@graph`` (ruling 17 b), in document order. Nested nodes are not read."""
    tops = doc if isinstance(doc, list) else [doc]
    nodes: list[Any] = []
    for top in tops:
        if not isinstance(top, Mapping):
            continue
        nodes.append(top)
        graph = top.get("@graph")
        if isinstance(graph, list):
            nodes.extend(g for g in graph if isinstance(g, Mapping))
        elif isinstance(graph, Mapping):
            nodes.append(graph)
    for node in nodes:
        if "datePublished" not in node:
            continue
        val = node["datePublished"]
        for v in val if isinstance(val, list) else [val]:
            yield v.get("@value") if isinstance(v, Mapping) else v


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
    """Every valid ``/YYYY/MM(/DD)/`` date in the URL's path, in order (duplicates kept).

    Only the path is searched (ruling 20): a date in the query or fragment is
    usually a filter or cache-buster. A match whose month or day is not a real
    calendar date is not a match.
    """
    try:
        path = urlsplit(url).path
    except ValueError:
        return []
    out: list[str] = []
    for m in _URL_DATE.finditer(path):
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


def _period(value: str) -> tuple[date, date]:
    """First and last day of a ``YYYY`` / ``YYYY-MM`` / ``YYYY-MM-DD`` value."""
    parts = [int(p) for p in value.split("-")]
    if len(parts) == 3:
        d = date(*parts)
        return d, d
    if len(parts) == 2:
        y, m = parts
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        return date(y, m, 1), nxt - timedelta(days=1)
    return date(parts[0], 1, 1), date(parts[0], 12, 31)


def in_window(value: str, access_date: date) -> bool:
    """Ruling 18 b (strict, R4 a): the date's period overlaps [:data:`EARLIEST_DATE`, ``access_date``].

    ``access_date`` is the page's UTC access date (``fetch_metadata.access_date``,
    :func:`g3o.scrape.render.utc_today_iso`). The upper bound is strict: a
    period that starts after the access date is out of window; no grace day
    is added for time zones ahead of UTC.
    """
    first, last = _period(value)
    return last >= EARLIEST_DATE and first <= access_date


def _access(access_date: Any) -> date:
    if isinstance(access_date, date):
        return access_date
    if isinstance(access_date, str):
        try:
            return date.fromisoformat(access_date.strip()[:10])
        except ValueError:
            pass
    raise ValueError(f"access_date must be the page's YYYY-MM-DD access date, got {access_date!r}")


@dataclass(frozen=True)
class PageDateInputs:
    """What :func:`g3o.common.source_fields.publication_date` takes for one page.

    ``metadata_dates`` is None only when neither the metadata measurement nor
    the URL test could run. ``metadata_measured`` False = A1.3 a (stored page,
    metadata not measured; only the URL test ran).
    """

    metadata_dates: tuple[Any, ...] | None  # MetadataDate entries
    metadata_measured: bool
    out_of_window: tuple[str, ...] = ()  # ruling 18 b: candidate values left out of selection


def page_date_inputs(candidates: Sequence[Mapping[str, Any]] | None, url: str | None, *,
                     access_date: Any) -> PageDateInputs:
    """Stored candidates (``RenderedPage.metadata_dates``) + supplied URL -> MetadataDate entries.

    ``access_date``: the page's UTC ``fetch_metadata.access_date``
    (``YYYY-MM-DD``), the strict upper bound of ruling 18 b's window.
    """
    from g3o.common.source_fields import MetadataDate  # local: source_fields imports this module

    accessed = _access(access_date)
    out: list[str] = []

    has_url = isinstance(url, str) and bool(url.strip())
    if candidates is None and not has_url:
        return PageDateInputs(None, False)
    dates: list[Any] = []
    for c in candidates or ():
        if c.get("tag") not in TAG_ORDER:
            raise ValueError(f"stored date candidate tag {c.get('tag')!r} is not a signed A1.1 a signal")
        if c.get("value") is None:
            continue
        if not in_window(c["value"], accessed):
            out.append(c["value"])
            continue
        dates.append(MetadataDate(c["value"], "metadata", f"{c['found_as']}: {c['raw']}", tag=c["tag"]))
    if has_url:
        for value in url_dates(url):  # type: ignore[arg-type]
            if not in_window(value, accessed):
                out.append(value)
                continue
            dates.append(MetadataDate(value, "web_address", f"URL pattern /YYYY/MM(/DD)/ -> {value}"))
    return PageDateInputs(tuple(dates), candidates is not None, tuple(out))


__all__ = [
    "EARLIEST_DATE", "NOT_MEASURED", "in_window", "PRODUCER_VERSION", "TAG_CITATION", "TAG_DC", "TAG_OPENGRAPH", "TAG_ORDER", "TAG_PDF",
    "TAG_SCHEMA", "PageDateInputs", "html_date_candidates", "normalise_iso", "normalise_pdf",
    "page_date_inputs", "pdf_date_candidates", "url_dates",
]
