"""v2.7 per-page inputs from the stored scrape artifacts (T-030, PI ruling D1 a, 2026-11-11).

D1 a: "T-030 then builds ``PageInput`` from the stored scrape artifact, with
fields copied verbatim from ``RenderedPage`` and the master row, and
``page_id = url_hash(url)`` (the existing per-page key in
``stage_page_code.artifact_path``)." This module is the default
``perpage_inputs`` of :class:`g3o.run.presweep.orchestrator.V27Dispatch`; an
injected callable still wins (the seam is kept for tests and for the values
no producer supplies yet).

Per institution (sample order; pages in the order Stage 4 stored them,
:class:`g3o.run.presweep.stage_scrape.ScrapedPages`):

- ``PageInput``: ``page_id`` = :func:`g3o.extract.batch.url_hash` of
  ``RenderedPage.url``; ``url``, ``title``, ``text``, ``chrome_text``,
  ``links``, ``email_links`` verbatim from the ``RenderedPage`` (lists as
  tuples, ``None`` kept as "not measured"); ``institution_id`` the Stage 4 key
  (:func:`~g3o.run.presweep.records.synth_institution_id`), ``institution``,
  ``country``, ``level_of_government`` the master row's ``institution_name``,
  ``country``, ``government_level`` (through
  :func:`~g3o.run.presweep.records.institution_record`); ``has_metadata_date``
  from A1 (:func:`g3o.common.source_fields.page_has_metadata_date` on
  ``RenderedPage.metadata_dates`` and the URL, with the page's recorded UTC
  ``fetch_metadata.access_date``).
- :class:`PageSourceFields` (carried as ``PageUpstream.page_fields``): the
  page-level T-015 values a stored page fixes before coding: X28
  ``source_url`` / ``source_access_date``, A1 the deterministic publication
  date (only when A1 finds one; otherwise the T-022 quote step owns the date
  and nothing is computed here), A2 the archive-address test, A3
  ``source_language`` (main text only), A4 ``syndication_group`` from
  :func:`g3o.common.syndication.group_rendered_pages` over this institution's
  pages only (``institution_id=``).
- ``PageUpstream.artifact_path`` / ``segments`` ``None``: A5
  (:func:`g3o.persist.page_artifact.write_page_artifact`) writes the page
  artifact in the per-page stage (PI ruling A5.1 a).
- ``InstitutionUpstream.independence_groups`` ``None``: produced in Stage 6
  (A7, :func:`g3o.run.presweep.stage_validate_v27.independence_groups_of`).
- ``PerPageInstitution``: ``run_id`` from the run manifest,
  ``institution_uid`` from the manifest's ``institution_uids`` block
  (:func:`g3o.common.paths.institution_uid_map`), ``institution`` the six
  identity columns of the stored ``institution.json`` (planning writes the
  master-row projection plus ``institution_search_languages`` there; the five
  master columns must equal the sample row's, else refused), ``country`` the
  master row's ``country``.

``PageUpstream.followed`` is ``False`` on every page built here: these are the
searched pages (PI ruling 61 a: ``searched``). The pages the T-025 follow leg
fetches are built in the per-page stage (:mod:`g3o.run.presweep.follow_v27`,
``followed=True`` with their hop), from their stored ``RenderedPage`` by
:func:`rendered_page_input` and :func:`page_source_fields`, as here.

Not produced here, and still refused exactly where they were (no value is
invented): ``InstitutionUpstream.merged_values`` (A8). ``activity_values`` /
``source_values`` / ``codes`` stay ``None``: the T-015 source-row assembler
(:mod:`g3o.run.presweep.source_row_v27`, PI ruling 35 a) builds them in the
per-page stage after coding, and still refuses the row items listed by
:func:`~g3o.run.presweep.source_row_v27.unproduced_items`.
``PageSourceFields.text_source`` is ``new_run`` (PI ruling 62 a: this builder is
the new-run path). :func:`require_complete` raises the per-page
stage's own ``MissingUpstreamError`` for the follow values and the refused row
items before any jev call is made, so a run on these inputs stops before
spending on coding it could never finish.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from g3o.classify.jev_page_code import PageInput
from g3o.common import source_fields as sf
from g3o.common.paths import MANIFEST_NAME, institution_dir, institution_uid_map
from g3o.common.syndication import group_rendered_pages
from g3o.extract.batch import url_hash
from g3o.persist.stage6_adapters import MissingUpstreamError
from g3o.run.presweep import source_row_v27 as srow
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep.records import institution_record

#: The six identity columns ``PerPageInstitution.institution`` carries (response_v27).
IDENTITY_COLUMNS = ("institution_id", "institution_name", "country", "branch_of_government",
                    "level_of_government", "institution_search_languages")
INSTITUTION_FILE = "institution.json"

#: The producers the default builder still lacks (PI ruling 36 a): while this is
#: non-empty, ``orchestrator._require_v27_dispatch`` refuses a v2.7 run on the
#: default builder at entry, before any Stage 1-4 spend. Remove each entry when
#: its producer is wired into :func:`build_perpage_inputs`; once empty, the entry
#: refusal is gone and :func:`require_complete` remains the per-value guard.
#: The row-values entry names the row items the T-015 source-row assembler still refuses (PI ruling 35 a,
#: :func:`g3o.run.presweep.source_row_v27.unproduced_items`); it drops out once that is empty
#: (:func:`~g3o.run.presweep.source_row_v27.entry_refused_items`). PI ruling 97 b: an item refused only on some
#: pages' data (:data:`~g3o.run.presweep.source_row_v27.CONDITIONAL_ITEMS`) holds that institution in the
#: per-page stage and is no longer named here.
VALUES_MISSING = (f"{pp.VALUES_PRODUCER} (activity_values, source_values, codes); {srow.ASSEMBLER} "
                  f"refuses: {', '.join(srow.entry_refused_items())}")
#: The T-025 entry left: ``followed`` / hop are produced (searched pages here, followed pages by
#: :mod:`g3o.run.presweep.follow_v27`), but the Stage 6 entry of a URL tried and not fetched or a
#: link not followed is a PI question; the stage holds such an institution
#: (``follow_v27.FOLLOW_ATTEMPTS_UNRULED``). Drop this entry once that is ruled and built.
FOLLOW_ATTEMPTS_MISSING = ("T-025 attempted pages not reviewed (fetch failed, robots refused, link not "
                           "followed: cap or hops): Stage 6 entry unruled")
MISSING_PRODUCERS: tuple[str, ...] = (
    FOLLOW_ATTEMPTS_MISSING,
    *((VALUES_MISSING,) if srow.entry_refused_items() else ()),
)


@dataclass(frozen=True)
class PageSourceFields:
    """Page-level T-015 values fixed by the stored page before coding (D1 a).

    ``publication_date`` is ``None`` when A1 finds no metadata or URL date: the
    T-022 quote step then asks for the date and T-015 decides it after coding
    (:func:`g3o.common.source_fields.page_publication_date`), so nothing is set here.
    The T-015 source-row assembler (:mod:`g3o.run.presweep.source_row_v27`, PI
    ruling 35 a) reads them after coding when no row values are injected.
    """

    url: sf.FieldValue
    access_date: sf.FieldValue
    publication_date: sf.FieldValue | None
    archive_address: bool
    language: sf.FieldValue
    syndication_group: sf.FieldValue
    #: R-059 ``core.text_source`` (PI ruling 62 a); None: the builder did not say which run path it is.
    text_source: sf.FieldValue | None = None


def page_input(page: Any, row: Mapping[str, Any], *, institution_id: str) -> PageInput:
    """``PageInput`` of one stored ``RenderedPage``: its fields verbatim, ``page_id = url_hash(url)``."""
    record = institution_record(dict(row))
    return rendered_page_input(page, institution_id=institution_id, institution=record["institution_name"],
                               country=record["country"], level_of_government=record["level_of_government"])


def rendered_page_input(page: Any, *, institution_id: str, institution: str, country: str | None,
                        level_of_government: str | None) -> PageInput:
    """``PageInput`` of one ``RenderedPage`` given the master values (D1 a; also the followed pages, T-025)."""
    return PageInput(
        page_id=url_hash(page.url),
        institution_id=institution_id,
        institution=institution,
        country=country,
        level_of_government=level_of_government,
        url=page.url,
        title=page.title,
        text=page.text,
        chrome_text=page.chrome_text,
        links=None if page.links is None else tuple(page.links),
        has_metadata_date=sf.page_has_metadata_date(page.metadata_dates, page.url,
                                                    access_date=page.fetch_metadata.access_date),
        email_links=None if page.email_links is None else tuple(page.email_links),
    )


def page_source_fields(page: Any, grouping: Any, page_id: str) -> PageSourceFields:
    """The A1-A4 / X28 values of one stored page (access date: its UTC ``fetch_metadata.access_date``).

    This builder is the new-run path (pages scraped by this run's Stage 4), so
    ``text_source`` is ``new_run`` (PI ruling 62 a).
    """
    access = page.fetch_metadata.access_date
    date = None
    if sf.page_has_metadata_date(page.metadata_dates, page.url, access_date=access):
        date = sf.page_publication_date(page.metadata_dates, page.url, None, None, access_date=access)
    return PageSourceFields(
        url=sf.source_url(page.url),
        access_date=sf.source_access_date(access),
        publication_date=date,
        archive_address=sf.source_archive_address(page.url),
        language=sf.source_language_of_page(page),
        syndication_group=sf.syndication_group_for(grouping, page_id),
        text_source=sf.text_source(sf.TEXT_SOURCE_NEW_RUN),
    )


def _identity(run_dir: Path, row: Mapping[str, Any], inst_id: str) -> dict[str, Any]:
    path = institution_dir(run_dir, inst_id) / INSTITUTION_FILE
    if not path.exists():
        raise MissingUpstreamError(f"planning {INSTITUTION_FILE} (master identity columns)", [inst_id])
    stored = json.loads(path.read_text(encoding="utf-8"))
    record = institution_record(dict(row))
    drift = sorted(c for c in IDENTITY_COLUMNS[:-1] if stored.get(c) != record[c])
    if drift:
        raise ValueError(f"{inst_id}: {INSTITUTION_FILE} differs from the master row on {drift}")
    if "institution_search_languages" not in stored:
        raise MissingUpstreamError(f"planning {INSTITUTION_FILE} (institution_search_languages)", [inst_id])
    return {c: stored[c] for c in IDENTITY_COLUMNS}


class PerPageInputs(Iterable[pp.PerPageInstitution]):
    """The default builder's output: lazy and re-iterable, one institution at a time.

    Each iteration walks the sample afresh and reads one institution's stored
    pages from ``scraped`` only when that institution is reached, so (as
    :class:`~g3o.run.presweep.stage_scrape.ScrapedPages` intends) only one
    institution's page text is live at a time. Re-iterable so a cheap first pass
    (:func:`require_complete`, which keeps no page text) can refuse incomplete
    inputs, and every builder error, before the per-page stage's first paid call;
    the second pass then feeds the stage. Each pass re-reads the artifacts.
    """

    def __init__(self, run_dir: Path, sample: Sequence[Mapping[str, Any]], scraped: Mapping[str, Any],
                 run_id: str, uids: Mapping[str, str]) -> None:
        self._run_dir, self._sample, self._scraped = run_dir, sample, scraped
        self._run_id, self._uids = run_id, uids

    def __iter__(self) -> Iterator[pp.PerPageInstitution]:
        run_dir, uids = self._run_dir, self._uids
        for row in self._sample:
            inst_id = institution_record(dict(row))["institution_id"]
            pages = list(self._scraped.get(inst_id) or ())  # ScrapedPages parses on access: read once
            if not pages:  # ruling 37 a: skipped here; its outcome is decided from the run folder, as v2.5
                continue
            if inst_id not in uids:
                raise MissingUpstreamError("run manifest (institution_uids)", [inst_id])
            inputs = [page_input(p, row, institution_id=inst_id) for p in pages]
            ids = [i.page_id for i in inputs]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{inst_id}: two stored pages share a URL (page_id = url_hash(url))")
            grouping = group_rendered_pages(dict(zip(ids, pages, strict=True)), institution_id=inst_id)
            specs = [pp.PageSpec(i, pp.PageUpstream(followed=False,  # searched (ruling 61 a)
                                                    page_fields=page_source_fields(p, grouping, i.page_id)))
                     for i, p in zip(inputs, pages, strict=True)]
            identity = _identity(run_dir, row, inst_id)
            yield pp.PerPageInstitution(self._run_id, uids[inst_id], identity, identity["country"], specs,
                                        pp.InstitutionUpstream(independence_groups=None, merged_values=None))


def build_perpage_inputs(run_dir: Path, sample: Sequence[Mapping[str, Any]], scraped: Mapping[str, Any],
                         bound: Any = None, instrument: Any = None) -> PerPageInputs:
    """Every scraped institution's :class:`~g3o.run.presweep.stage_perpage_v27.PerPageInstitution`, lazily.

    Builds what D1 a and the A producers settle and leaves every other upstream
    value ``None`` (refused downstream). An institution with no stored page is
    not built (nothing to code; ruling 37 a: its outcome is decided afterwards
    from the run folder, as v2.5 does). The run manifest (``run_id``, ``institution_uids``)
    is read here; each institution's pages only when :class:`PerPageInputs` is
    iterated. ``bound`` / ``instrument`` are accepted for the ``perpage_inputs``
    signature and not read.
    """
    del bound, instrument
    manifest = json.loads((run_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    run_id = manifest.get("run_id")
    if not run_id:
        raise MissingUpstreamError("run manifest (run_id)", [str(run_dir)])
    return PerPageInputs(run_dir, sample, scraped, str(run_id), institution_uid_map(run_dir))


def require_complete(institutions: Iterable[pp.PerPageInstitution],
                     keys: list[tuple[str, str]] | None = None) -> int:
    """Raise the per-page stage's ``MissingUpstreamError`` for values no producer supplies yet.

    The per-page stage refuses these only after coding a page (``failed_page`` /
    ``produce_page``); refusing here keeps the same refusal and spends nothing.
    One pass that keeps only page keys, never page text. Returns the page count.

    A None-only pre-check: ``followed`` must not be ``None``, and the row values
    must be injected (``activity_values``, ``source_values`` and ``codes`` not
    ``None``) or left wholly to the T-015 source-row assembler (all three ``None``
    with ``page_fields`` set; PI ruling 35 a), which is refused while the assembler
    still refuses an unproduced row item
    (:func:`g3o.run.presweep.source_row_v27.entry_refused_items`, named in the error;
    PI ruling 97 b: an item refused only on some pages' data holds that institution in
    the stage instead). Which keys injected values must cover (one per coded
    activity, or :data:`~g3o.run.presweep.stage_perpage_v27.NO_ACTIVITY`) is known
    only after coding, so key coverage is still checked by ``produce_page``.

    ``keys``, when given, receives ``(institution_id, page_id)`` for every page, in
    the order seen (the dispatch checks the run pass against it).
    """
    follow, values = [], []
    n_pages = 0
    for inst in institutions:
        for spec in inst.pages:
            n_pages += 1
            if keys is not None:
                keys.append((inst.institution_id, spec.page.page_id))
            key = f"{inst.institution_id}/{spec.page.page_id}"
            up = spec.upstream
            if up.followed is None:
                follow.append(key)
            given = (up.activity_values, up.source_values, up.codes)
            assembled = up.page_fields is not None and all(v is None for v in given)  # ruling 35 a path
            if (assembled and srow.entry_refused_items()) or (not assembled and any(v is None for v in given)):
                values.append(key)
    if follow:
        raise MissingUpstreamError(pp.FOLLOW_PRODUCER, follow)
    if values:
        label = VALUES_MISSING if srow.entry_refused_items() else \
            f"{pp.VALUES_PRODUCER} (activity_values, source_values, codes)"
        raise MissingUpstreamError(label, values)
    return n_pages


def default_perpage_inputs(run_dir: Path, sample: Sequence[Mapping[str, Any]], scraped: Mapping[str, Any],
                           bound: Any, instrument: Any) -> PerPageInputs:
    """The v2.7 dispatch's default ``perpage_inputs`` (D1 a): the lazy :class:`PerPageInputs`.

    :func:`require_complete` is not run here: ``run_v27_dispatch`` runs it on the
    output of whichever builder is used (PI ruling 40 a), as a first pass over
    the lazy inputs (no page text kept) before any paid call, then iterates
    again to code.
    """
    return build_perpage_inputs(run_dir, sample, scraped, bound, instrument)


__all__ = ["FOLLOW_ATTEMPTS_MISSING", "IDENTITY_COLUMNS", "MISSING_PRODUCERS", "VALUES_MISSING", "PageSourceFields",
           "PerPageInputs", "build_perpage_inputs", "default_perpage_inputs",
           "page_input", "page_source_fields", "rendered_page_input", "require_complete"]
