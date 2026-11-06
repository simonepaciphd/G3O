"""Follow-up link following for the v2.7 leg after pass 1 (T-025): pure rules, no I/O.

What this module fixes, each as SPEC v001.24 states it:

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
- **Ranking (R-032 F1 b, RC-D-015; RC-D-017 10a).** Candidates are taken nearest first; ties go to
  page order. The nearness value itself is supplied by the caller (see OPEN below).
- **Once per URL (R-034).** A URL is fetched at most once per institution per run, the original
  leg's pages included; a URL linked from several pages records as parent the page that first
  queued it, in traversal (rank) order (R-034 F2 a, RC-D-015).
- **Provenance (R-034, R-036).** Every followed URL records its origin page, hop, fetch date and the
  release id, and whether it was fetched in the back-fill (R-036 tags).
- **Procurement (r2#54).** Link following does not apply to procurement; a procurement state is
  refused at construction.

OPEN (QUESTION block in the T-025 lane report; not chosen here, so each is a required input with no
default): what counts as the same URL (``url_key``); the nearness value, i.e. where a link and a
supporting quote sit in the stored page text, which quotes count and what a page without a
locatable quote gives (``nearness``); and whether a URL that was tried but not fetched counts
against the cap (``count_unfetched``).

The T-021 page artifact is not built yet. This module consumes only the mocked
:class:`~g3o.extract.request_v27.Pass1Page` that T-022 already defines, and of it only
``page_id``, ``institution_id``, ``url``, ``text``, ``page_complete`` and ``links`` (the T-014 stored
list, for page order); see :data:`PASS1_PAGE_FIELDS`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

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
    """The rules the signed text does not fix (OPEN; see the module docstring)."""

    #: Same-URL identity for R-034 and the cap.
    url_key: Callable[[str], str]
    #: Nearness of a selected link to the page's supporting quotes; smaller is nearer.
    #: Called as ``nearness(page, extraction, link)``.
    nearness: Callable[[Any, Any, Any], float]
    #: Whether a URL tried but not fetched (failed download, robots refusal) counts against the cap.
    count_unfetched: bool
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
    rules: FollowRules
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

    def candidates(self, pages: Sequence[tuple[Any, Any]]) -> list[Candidate]:
        """Rank the follow-up candidates of one round's pass-1 pages.

        ``pages`` are ``(Pass1Page, Pass1Extraction)`` pairs of this institution, each page already
        fetched (original or followed). Returns the candidates to try, nearest first, ties in page
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
                    nearness=float(self.rules.nearness(page, extraction, link)),
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
    "URL_CAP",
]
