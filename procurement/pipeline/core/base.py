"""The adapter contract and the pipeline orchestrator.

`SourceAdapter` is what every source implements (this is the thing you clone
per source). `Pipeline` wires an adapter to the shared core and runs the five
stages: search -> fetch -> extract -> classify -> standardize -> store.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import islice
from typing import Iterable

from .classify import CANNOT_TYPE_FLAG, NOT_ASSESSABLE, needs_review
from .models import GenAIQuerySet, Hit, RawRecord, ProcurementRecord
from .standardize import build_extension, standardize

log = logging.getLogger(__name__)


class SourceAdapter(ABC):
    """Per-source transport. Subclass one of the type templates under adapters/.

    Class attributes are set from config/sources.yaml when the adapter is built.
    """

    source_id: str
    access_mode: str          # "api" | "bulk" | "scrape"
    is_ocds: bool = False     # True -> the core OCDS extractor handles extract()

    def __init__(self, config: dict):
        self.config = config
        self.source_id = config["source_id"]
        self.access_mode = config["access_mode"]
        self.is_ocds = bool(config.get("is_ocds", False))
        # Adapters append one dict per hit they gave up on (after retries), so a
        # failed fetch is counted in the run report instead of silently dropped.
        self.fetch_failures: list[dict] = []

    @abstractmethod
    def search(self, queries: GenAIQuerySet) -> Iterable[Hit]:
        """Return candidate hits matching the GenAI queries.

        Push the query to the source where possible (API q= param, portal search);
        otherwise return all records and let the classifier filter downstream.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch(self, hits: Iterable[Hit]) -> Iterable[RawRecord]:
        """Retrieve full raw records for the given hits.

        Handle pagination / download / crawl and per-source rate limits here.
        Cache raw payloads to data_cache/<source_id>/ so re-runs don't re-hit.
        """
        raise NotImplementedError

    def extract(self, raw: RawRecord) -> dict | list[dict]:
        """Raw payload -> intermediate field dict(s) (keys align with standardize()).

        May return one dict, or a list when one payload carries several staged
        records — a release with several awards or lots does (ruling D6). The
        orchestrator normalises either shape, so a simple source can keep
        returning a single dict.

        Default routes OCDS sources to the shared OCDS extractor. Non-OCDS
        adapters override this with a per-source field map (see the scrape/API
        templates). Kept as a method (not abstract) so OCDS sources get it free.
        """
        if self.is_ocds:
            from .standardize import extract_ocds
            return extract_ocds(raw)
        raise NotImplementedError(
            f"{self.source_id}: non-OCDS source must override extract() with a field map."
        )


@dataclass
class RunReport:
    """What a run did. Returned by Pipeline.run() and printed by the CLI.

    Counts are provisional candidate dispositions. They are deliberately not
    labelled as contract C8 values: contract `no` / `confirms_absence` is a
    searched-source result and that primary-output step is still pending.
    """
    source_id: str
    fetched: int = 0          # payloads pulled from the source
    written: int = 0          # staged records (>= fetched when releases carry several awards)
    candidate_yes: int = 0
    candidate_unclear: int = 0
    candidate_no: int = 0
    review_queue: int = 0
    cannot_type: int = 0      # ruling D1 — reported, not coded
    candidate_not_assessable: int = 0   # rule R8 — no descriptive text, not coded
    fetch_failed: int = 0     # hits the adapter could not fetch after retries
    linked: int = 0           # records resolved to an institution_uid
    sent_to_review: int = 0   # records whose buyer went to the institution review queue
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def summary(self) -> str:
        return (f"{self.source_id}: fetched={self.fetched} written={self.written} "
                f"candidate_yes={self.candidate_yes} candidate_unclear={self.candidate_unclear} "
                f"candidate_no={self.candidate_no} "
                f"not_assessable={self.candidate_not_assessable} review={self.review_queue} "
                f"cannot_type={self.cannot_type} fetch_failed={self.fetch_failed} "
                f"linked={self.linked} institution_review={self.sent_to_review} "
                f"errors={len(self.errors)}")


class Pipeline:
    """Runs adapter + shared staging core over one source, end to end."""

    def __init__(self, adapter: SourceAdapter, queries: GenAIQuerySet,
                 classifier, store, institution_index=None):
        self.adapter = adapter
        self.queries = queries
        self.classifier = classifier      # pipeline.core.classify.Classifier
        self.store = store                # pipeline.core.store.StagingStore
        # pipeline.core.matcher.InstitutionIndex; None skips matching.
        self.institution_index = institution_index

    def run(self, limit: int | None = None, strict: bool = False) -> RunReport:
        """Execute search -> fetch -> extract -> classify -> standardize -> store.

        `limit` caps records for the small-sample smoke run (standing lab rule:
        prove the whole path on a few records before a full pull).

        `strict=True` re-raises the first per-record failure. Default collects
        them in the report so one malformed record cannot abort a long pull —
        but every failure is logged and counted, never silently dropped.

        When an `institution_index` is given, every staged record's buyer is
        matched (spec §5: a row without a resolved institution cannot enter the
        primary table, negative evidence included). A resolved, ledger-live
        match is written to `links`; everything else goes to `review` with its
        candidates, so unresolved matches are kept, never dropped. Both carry
        the master build id and matcher version.
        """
        report = RunReport(source_id=self.adapter.source_id)

        hits = self.adapter.search(self.queries)
        # islice stops before pulling payload limit+1; a post-pull check made
        # lazy adapters fetch and cache one extra release (Uruguay n=100: 101 cached).
        for raw in islice(self.adapter.fetch(hits), limit):
            report.fetched += 1

            try:
                extracted = self.adapter.extract(raw)
                # One payload may stage several records (ruling D6).
                for fields in ([extracted] if isinstance(extracted, dict) else extracted):
                    clf = self.classifier.classify(fields)
                    record = standardize(self.adapter, raw, fields, clf)
                    extension = build_extension(self.adapter, raw, fields, clf)

                    self.store.upsert(record)
                    self.store.upsert_extension(extension)
                    report.written += 1

                    if self.institution_index is not None:
                        from .matcher import match_institution
                        link, review = match_institution(record.to_dict(), self.institution_index)
                        if link is not None:
                            self.store.upsert_link(link)
                            report.linked += 1
                        else:
                            self.store.upsert_review(review)
                            report.sent_to_review += 1

                    if clf.relevance == "yes":
                        report.candidate_yes += 1
                    elif clf.relevance == "unclear":
                        report.candidate_unclear += 1
                    elif clf.relevance == NOT_ASSESSABLE:
                        report.candidate_not_assessable += 1
                    else:
                        report.candidate_no += 1
                    if needs_review(clf.review_flags):
                        report.review_queue += 1
                    if CANNOT_TYPE_FLAG in clf.review_flags:
                        report.cannot_type += 1

            except Exception as exc:                      # noqa: BLE001 — reported, not hidden
                message = f"{raw.native_id}: {type(exc).__name__}: {exc}"
                log.error("%s — record failed: %s", self.adapter.source_id, message)
                report.errors.append(message)
                if strict:
                    raise

        report.fetch_failed = len(getattr(self.adapter, "fetch_failures", []) or [])
        return report
