"""Follow-up link following for the v2.7 leg after pass 1 (T-025): pure rules, no I/O.

What this module fixes, each as SPEC v001.25 states it (RC-D-023 included):

- **Candidates (R-031, R-033; RC-D-002 row 13).** A page's follow-up links are the stored links
  (T-014) the quote step selected (T-022, :class:`~g3o.extract.parser_v27.SelectedLink`), on a page
  pass 1 marks as referring onward (``core.page_complete`` = ``yes``, the same test
  :func:`g3o.extract.request_v27.select_requests` uses). Any cited link is eligible (R-033).
- **Hop limit (R-032).** A page scraped in the original leg is hop 0. A link on a hop-``h`` page is a
  hop ``h + 1`` candidate; it is followed only when ``h + 1 <= MAX_HOPS`` (3), else it is recorded
  as not followed with ``link_not_followed_hops`` (codebook ``core.page_review_state``).
- **URL cap (R-032; RC-D-014 S4).** At most ``URL_CAP`` (10) followed URLs per institution per run,
  counted over all hops. When the count reaches the cap, following stops and "cap reached" is
  recorded on the institution; every candidate left is recorded with ``link_not_followed_cap``.
- **Ranking (R-032 F1 b, RC-D-015; RC-D-017 10a; RC-D-023 Q2 a, Q3 b (i), Q4 a, Q6).** Candidates
  are taken nearest first (:func:`quote_nearness`); ties go to page order: input page order (the
  caller's (institution_id, url) order), then stored-link order. Links with no located position,
  or on pages with no located supported quote, rank after every located link, in page order, and
  are followed if the cap allows.
- **Once per URL (R-034; RC-D-023 Q1 b).** A URL is fetched at most once per institution per run,
  the original leg's pages included; "the same URL" is the discovery dedup key
  (:func:`same_url_key`). A URL linked from several pages records as parent the page that first
  queued it, in traversal (rank) order (R-034 F2 a, RC-D-015). A URL tried and not fetched is
  never tried again.
- **What counts against the cap (RC-D-023 Q5 b).** Every URL tried: fetched, failed and
  robots-refused alike.
- **Provenance (R-034, R-036).** Every followed URL records its origin page, hop, fetch date and the
  release id, and whether it was fetched in the back-fill (R-036 tags).
- **Procurement (r2#54).** Link following does not apply to procurement; a procurement state is
  refused at construction.

Order (RC-D-023 C-1 a): the extractor runs once per page after that page's pass 1 and before
following; each followed page gets its own call. The supported quotes (T-024 results) are an input
of each round, supplied by the caller (T-030).

The T-021 page artifact is not built yet. This module consumes only the mocked
:class:`~g3o.extract.request_v27.Pass1Page` that T-022 already defines, and of it only
``page_id``, ``institution_id``, ``url``, ``text``, ``page_complete`` and ``links`` (the T-014 stored
list, for page order); see :data:`PASS1_PAGE_FIELDS`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from g3o.common.support_check import _locate, _locate_by_words

#: Supported quotes per page: ``page_id`` -> the quote texts that passed the T-024 support check
#: (R-042) on that page. Supplied by the caller (RC-D-023 Q3 b).
SupportedQuotes = Mapping[str, Sequence[str]]

#: Nearness of a link with no located position, or on a page with no located supported quote
#: (RC-D-023 Q4 a): after every located link.
UNLOCATED = math.inf


def same_url_key(url: str) -> str:
    """RC-D-023 Q1 b: "the same URL" is the discovery dedup key (Q3=c, 2026-05-09).

    Reuses :func:`g3o.run.presweep.records._dedupe_key`. The import is deferred to the call:
    importing ``g3o.run.presweep`` runs the package ``__init__`` chain (presweep config ->
    jev client -> ``typesafe_sdk``), which this otherwise pure module must not need at import.
    """
    from g3o.run.presweep.records import _dedupe_key

    return _dedupe_key(url)


def locate(text_snippet: str, text: str) -> tuple[int, int] | None:
    """Span of ``text_snippet`` in ``text``: exact (up to case and whitespace) first, then first to
    last matched word (RC-D-023 Q2 a; the T-024 locators, E3 ruling b). None when not found."""
    if not text_snippet or not text_snippet.strip():
        return None
    return _locate(text_snippet, text) or _locate_by_words(text_snippet, text)


def span_gap(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Characters between two spans, 0 when they overlap or touch (RC-D-023 Q3 b (i))."""
    return max(0, b[0] - a[1], a[0] - b[1])


def quote_nearness(page: Any, link: Any, supported: Sequence[str]) -> float:
    """R-032 nearness (RC-D-017 10a; RC-D-023 Q2 a, Q3 b (i), Q4 a).

    Character distance in the stored page text between the link, located by its quote-step link
    passage (``SelectedLink.quote``), and the nearest supported quote, as the gap between the two
    spans. :data:`UNLOCATED` when the link passage or every supported quote cannot be located.
    """
    link_span = locate(link.quote, page.text)
    if link_span is None:
        return UNLOCATED
    gaps = [span_gap(link_span, s) for q in supported if (s := locate(q, page.text)) is not None]
    return float(min(gaps)) if gaps else UNLOCATED

#: R-032 v001.16 / RC-D-014 S4: followed URLs per institution per run.
URL_CAP = 10
#: R-032: hops from the originally scraped page.
MAX_HOPS = 3

#: ``core.page_review_state`` values this leg sets (codebook r13).
LINK_NOT_FOLLOWED_CAP = "link_not_followed_cap"
LINK_NOT_FOLLOWED_HOPS = "link_not_followed_hops"
FETCH_FAILED = "fetch_failed"

#: Fetch outcomes of a followed URL.
FETCHED = "fetched"
OUTCOMES = (FETCHED, FETCH_FAILED, "robots_disallowed")

#: The one place listing what this leg reads from the T-021 pass-1 page artifact (mocked as
#: ``Pass1Page``, T-022). The integrator reconciles this list with T-021 (lane B).
PASS1_PAGE_FIELDS = ("page_id", "institution_id", "url", "text", "page_complete", "links")

#: ``core.page_complete`` answer meaning "the page refers the reader onward" (codebook note).
REFERS_ONWARD = "yes"

PROCUREMENT = "procurement"


@dataclass(frozen=True)
class Candidate:
    """One eligible follow-up link on one page, before ranking."""

    institution_id: str
    url: str
    url_key: str
    parent_page_id: str
    parent_url: str
    hop: int  # hop the followed page would have
    link_id: str
    link_order: int  # position of the link in the page's stored links (page order)
    page_order: int  # position of the parent page in the round's input
    link_quote: str  # the quote step's link passage
    nearness: float


@dataclass(frozen=True)
class FollowRecord:
    """Provenance of one followed URL (R-034, R-036)."""

    institution_id: str
    url: str
    url_key: str
    parent_page_id: str
    parent_url: str
    hop: int
    link_id: str
    link_quote: str
    outcome: str  # one of OUTCOMES
    fetch_date: str | None  # ISO date of the fetch; None when nothing was fetched
    release_id: str
    backfill: bool
    counted: bool  # counted against the URL cap


@dataclass(frozen=True)
class NotFollowed:
    """A candidate link that was not followed, with its ``core.page_review_state`` reason."""

    institution_id: str
    url: str
    url_key: str
    parent_page_id: str
    parent_url: str
    hop: int
    link_id: str
    reason: str  # LINK_NOT_FOLLOWED_CAP | LINK_NOT_FOLLOWED_HOPS


@dataclass(frozen=True)
class CapRecord:
    """The per-institution cap record (R-032, SC-03, PF-027)."""

    institution_id: str
    url_cap: int
    followed: int
    cap_reached: bool
    not_followed_cap: int
    not_followed_hops: int


@dataclass(frozen=True)
class FollowRules:
    """The follow rules; the defaults are the PI's (RC-D-023, "accept all", 2026-11-08)."""

    #: Same-URL identity for R-034 and the cap (RC-D-023 Q1 b).
    url_key: Callable[[str], str] = same_url_key
    #: Nearness of a selected link to the page's supported quotes; smaller is nearer.
    #: Called as ``nearness(page, link, supported_quotes_of_the_page)`` (RC-D-023 Q2 a, Q3 b, Q4 a).
    nearness: Callable[[Any, Any, Sequence[str]], float] = quote_nearness
    #: Whether a URL tried but not fetched (failed download, robots refusal) counts against the
    #: cap: yes (RC-D-023 Q5 b).
    count_unfetched: bool = True
    url_cap: int = URL_CAP
    max_hops: int = MAX_HOPS

    def __post_init__(self) -> None:
        if self.url_cap < 0 or self.max_hops < 0:
            raise ValueError("url_cap and max_hops must be non-negative")


@dataclass
class InstitutionFollow:
    """Follow state of one institution over one run: seen URLs, hops, cap count, records."""

    institution_id: str
    release_id: str
    rules: FollowRules = field(default_factory=FollowRules)
    backfill: bool = False
    pipeline: str = "web_extract"
    hops: dict[str, int] = field(default_factory=dict)  # url_key -> hop of the fetched page
    records: list[FollowRecord] = field(default_factory=list)
    not_followed: list[NotFollowed] = field(default_factory=list)
    followed: int = 0
    cap_reached: bool = False

    def __post_init__(self) -> None:
        if self.pipeline == PROCUREMENT:
            raise ValueError("link following does not apply to procurement (r2#54)")

    # -- original leg ------------------------------------------------------

    def register_original(self, url: str) -> None:
        """A page fetched by the original leg (hop 0). It is never fetched again (R-034)."""
        self.hops.setdefault(self.rules.url_key(url), 0)

    def hop_of(self, url: str) -> int:
        key = self.rules.url_key(url)
        if key not in self.hops:
            raise KeyError(f"{url!r} was not fetched for {self.institution_id}")
        return self.hops[key]

    @property
    def budget(self) -> int:
        return max(0, self.rules.url_cap - self.followed)

    # -- one round ---------------------------------------------------------

    def candidates(self, pages: Sequence[tuple[Any, Any]], *,
                   supported: SupportedQuotes) -> list[Candidate]:
        """Rank the follow-up candidates of one round's pass-1 pages.

        ``pages`` are ``(Pass1Page, Pass1Extraction)`` pairs of this institution, each page already
        fetched (original or followed), in the caller's (institution_id, url) order (RC-D-023 Q6).
        ``supported`` gives each page's quotes that passed the T-024 support check (a page
        missing from it has none). Returns the candidates to try, nearest first, ties in page
        order (input page order, then stored-link order), one per URL (the first in that order is
        the parent, F2 a), excluding URLs already fetched. Links beyond the hop limit are recorded
        here as not followed and not returned.
        """
        raw: list[Candidate] = []
        for page_order, (page, extraction) in enumerate(pages):
            if page.institution_id != self.institution_id:
                raise ValueError(f"page {page.page_id} is not {self.institution_id}'s")
            if extraction.page_id != page.page_id:
                raise ValueError(f"extraction {extraction.page_id} is not page {page.page_id}'s")
            if page.page_complete != REFERS_ONWARD:
                continue
            hop = self.hop_of(page.url) + 1
            order = {f"L{n:03d}": n for n in range(1, len(page.links or ()) + 1)}
            for link in extraction.links:
                if link.link_id not in order:
                    raise ValueError(f"link {link.link_id} is not a stored link of {page.page_id}")
                raw.append(Candidate(
                    institution_id=self.institution_id,
                    url=link.url,
                    url_key=self.rules.url_key(link.url),
                    parent_page_id=page.page_id,
                    parent_url=page.url,
                    hop=hop,
                    link_id=link.link_id,
                    link_order=order[link.link_id],
                    page_order=page_order,
                    link_quote=link.quote,
                    nearness=float(self.rules.nearness(
                        page, link, tuple(supported.get(page.page_id, ())))),
                ))
        raw.sort(key=lambda c: (c.nearness, c.page_order, c.link_order))
        out: list[Candidate] = []
        queued: set[str] = set()
        for c in raw:
            if c.hop <= self.rules.max_hops and c.url_key not in self.hops \
                    and c.url_key not in queued:
                queued.add(c.url_key)
                out.append(c)
        for c in raw:
            if c.hop > self.rules.max_hops and c.url_key not in self.hops \
                    and c.url_key not in queued:
                queued.add(c.url_key)
                self._not_followed(c, LINK_NOT_FOLLOWED_HOPS)
        return out

    def take(self, candidate: Candidate) -> bool:
        """Whether ``candidate`` may be fetched now; records it as not followed for the cap if not."""
        if candidate.url_key in self.hops:
            return False
        if self.budget == 0:
            self.cap_reached = True
            self._not_followed(candidate, LINK_NOT_FOLLOWED_CAP)
            return False
        return True

    def record(self, candidate: Candidate, outcome: str, fetch_date: str | None) -> FollowRecord:
        """Record the fetch of a taken candidate. The URL is never tried again in this run."""
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        if candidate.url_key in self.hops:
            raise ValueError(f"{candidate.url!r} was already fetched for {self.institution_id}")
        if outcome == FETCHED and not fetch_date:
            raise ValueError("a fetched page needs its fetch date")
        counted = outcome == FETCHED or self.rules.count_unfetched
        self.hops[candidate.url_key] = candidate.hop
        if counted:
            self.followed += 1
            if self.followed >= self.rules.url_cap:
                self.cap_reached = True
        rec = FollowRecord(
            institution_id=self.institution_id,
            url=candidate.url,
            url_key=candidate.url_key,
            parent_page_id=candidate.parent_page_id,
            parent_url=candidate.parent_url,
            hop=candidate.hop,
            link_id=candidate.link_id,
            link_quote=candidate.link_quote,
            outcome=outcome,
            fetch_date=fetch_date if outcome == FETCHED else None,
            release_id=self.release_id,
            backfill=self.backfill,
            counted=counted,
        )
        self.records.append(rec)
        return rec

    def cap_record(self) -> CapRecord:
        return CapRecord(
            institution_id=self.institution_id,
            url_cap=self.rules.url_cap,
            followed=self.followed,
            cap_reached=self.cap_reached,
            not_followed_cap=sum(n.reason == LINK_NOT_FOLLOWED_CAP for n in self.not_followed),
            not_followed_hops=sum(n.reason == LINK_NOT_FOLLOWED_HOPS for n in self.not_followed),
        )

    def _not_followed(self, c: Candidate, reason: str) -> None:
        """One record per URL: the first reason and parent stand (F2 a)."""
        if any(n.url_key == c.url_key for n in self.not_followed):
            return
        self.not_followed.append(NotFollowed(
            institution_id=c.institution_id, url=c.url, url_key=c.url_key,
            parent_page_id=c.parent_page_id, parent_url=c.parent_url, hop=c.hop,
            link_id=c.link_id, reason=reason,
        ))


__all__ = [
    "Candidate",
    "CapRecord",
    "FETCHED",
    "FETCH_FAILED",
    "FollowRecord",
    "FollowRules",
    "InstitutionFollow",
    "LINK_NOT_FOLLOWED_CAP",
    "LINK_NOT_FOLLOWED_HOPS",
    "MAX_HOPS",
    "NotFollowed",
    "OUTCOMES",
    "PASS1_PAGE_FIELDS",
    "SupportedQuotes",
    "UNLOCATED",
    "URL_CAP",
    "locate",
    "quote_nearness",
    "same_url_key",
    "span_gap",
]
