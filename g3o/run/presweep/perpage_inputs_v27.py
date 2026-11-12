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

Not produced here, and still refused exactly where they were (no value is
invented): ``PageUpstream.followed`` (T-025 follow provenance),
``activity_values`` / ``source_values`` / ``codes`` (T-015 / T-022 / T-024 row
values; ``core.discovery_path`` and ``core.text_source`` have no signed
spelling and raise ``UnruledError``), ``InstitutionUpstream.merged_values``
(A8). :func:`require_complete` raises the per-page stage's own
``MissingUpstreamError`` for the first two before any jev call is made, so a
run on these inputs stops before spending on coding it could never finish.
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
MISSING_PRODUCERS: tuple[str, ...] = (
    pp.FOLLOW_PRODUCER,
    f"{pp.VALUES_PRODUCER} (activity_values, source_values, codes)",
)


@dataclass(frozen=True)
class PageSourceFields:
    """Page-level T-015 values fixed by the stored page before coding (D1 a).

    ``publication_date`` is ``None`` when A1 finds no metadata or URL date: the
    T-022 quote step then asks for the date and T-015 decides it after coding
    (:func:`g3o.common.source_fields.page_publication_date`), so nothing is set here.
    These values are not yet merged into the per-activity ``source_values``.
    """

    url: sf.FieldValue
    access_date: sf.FieldValue
    publication_date: sf.FieldValue | None
    archive_address: bool
    language: sf.FieldValue
    syndication_group: sf.FieldValue


def page_input(page: Any, row: Mapping[str, Any], *, institution_id: str) -> PageInput:
    """``PageInput`` of one stored ``RenderedPage``: its fields verbatim, ``page_id = url_hash(url)``."""
    record = institution_record(dict(row))
    return PageInput(
        page_id=url_hash(page.url),
        institution_id=institution_id,
        institution=record["institution_name"],
        country=record["country"],
        level_of_government=record["level_of_government"],
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
    """The A1-A4 / X28 values of one stored page (access date: its UTC ``fetch_metadata.access_date``)."""
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
            if not pages:
                continue
            if inst_id not in uids:
                raise MissingUpstreamError("run manifest (institution_uids)", [inst_id])
            inputs = [page_input(p, row, institution_id=inst_id) for p in pages]
            ids = [i.page_id for i in inputs]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{inst_id}: two stored pages share a URL (page_id = url_hash(url))")
            grouping = group_rendered_pages(dict(zip(ids, pages, strict=True)), institution_id=inst_id)
            specs = [pp.PageSpec(i, pp.PageUpstream(page_fields=page_source_fields(p, grouping, i.page_id)))
                     for i, p in zip(inputs, pages, strict=True)]
            identity = _identity(run_dir, row, inst_id)
            yield pp.PerPageInstitution(self._run_id, uids[inst_id], identity, identity["country"], specs,
                                        pp.InstitutionUpstream(independence_groups=None, merged_values=None))


def build_perpage_inputs(run_dir: Path, sample: Sequence[Mapping[str, Any]], scraped: Mapping[str, Any],
                         bound: Any = None, instrument: Any = None) -> PerPageInputs:
    """Every scraped institution's :class:`~g3o.run.presweep.stage_perpage_v27.PerPageInstitution`, lazily.

    Builds what D1 a and the A producers settle and leaves every other upstream
    value ``None`` (refused downstream). An institution with no stored page is
    not built (nothing to code). The run manifest (``run_id``, ``institution_uids``)
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


def require_complete(institutions: Iterable[pp.PerPageInstitution]) -> int:
    """Raise the per-page stage's ``MissingUpstreamError`` for values no producer supplies yet.

    The per-page stage refuses these only after coding a page (``failed_page`` /
    ``produce_page``); refusing here keeps the same refusal and spends nothing.
    One pass that keeps only page keys, never page text. Returns the page count.

    A None-only pre-check: ``followed``, ``activity_values``, ``source_values``
    and ``codes`` must not be ``None``. Which keys they must cover (one per coded
    activity, or :data:`~g3o.run.presweep.stage_perpage_v27.NO_ACTIVITY`) is known
    only after coding, so key coverage is still checked by ``produce_page``.
    """
    follow, values = [], []
    n_pages = 0
    for inst in institutions:
        for spec in inst.pages:
            n_pages += 1
            key = f"{inst.institution_id}/{spec.page.page_id}"
            up = spec.upstream
            if up.followed is None:
                follow.append(key)
            if up.activity_values is None or up.source_values is None or up.codes is None:
                values.append(key)
    if follow:
        raise MissingUpstreamError(pp.FOLLOW_PRODUCER, follow)
    if values:
        raise MissingUpstreamError(f"{pp.VALUES_PRODUCER} (activity_values, source_values, codes)", values)
    return n_pages


def default_perpage_inputs(run_dir: Path, sample: Sequence[Mapping[str, Any]], scraped: Mapping[str, Any],
                           bound: Any, instrument: Any) -> PerPageInputs:
    """The v2.7 dispatch's default ``perpage_inputs`` (D1 a): build lazily, then refuse what is still missing.

    The check is a first pass over the lazy inputs (no page text kept), so a
    refusal comes before any paid call; the caller iterates again to code.
    """
    institutions = build_perpage_inputs(run_dir, sample, scraped, bound, instrument)
    require_complete(institutions)
    return institutions


__all__ = ["IDENTITY_COLUMNS", "MISSING_PRODUCERS", "PageSourceFields", "PerPageInputs", "build_perpage_inputs",
           "default_perpage_inputs",
           "page_input", "page_source_fields", "require_complete"]
