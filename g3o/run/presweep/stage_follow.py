"""Follow-up leg runner (T-025): one round of link following after a pass-1 round.

The leg runs after pass 1 as its own leg (DEC-003 b). One call of :func:`run_follow_round` takes one
round's pass-1 pages with their quote-step extractions, picks each institution's follow-up links by
the rules of :mod:`g3o.scrape.follow`, fetches them, and returns the fetched pages for the next
pass-1 round. The caller (orchestrator wiring, T-030) repeats rounds until none returns a page;
the hop limit ends the leg after at most 3 rounds.

Per institution it writes, under ``<inst>/follow/``:

- ``<url_hash>.json`` (gzip by :mod:`g3o.common.artifact_io`): each page fetched, as the
  ``RenderedPage`` JSON the scrape stage writes;
- ``state.json``: the provenance records, the links not followed and the cap record, rewritten
  after every round.

A link not followed is also written to the attrition ledger under its ``core.page_review_state``
reason. No network here beyond the ``fetch`` callable the caller passes; :func:`polite_fetch`
binds the existing fetcher with the robots and per-host throttle settings of Stage 4.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.artifact_io import write_artifact
from g3o.common.paths import institution_dir
from g3o.scrape.follow import FETCH_FAILED, FETCHED, FollowRecord, InstitutionFollow
from g3o.scrape.render import RenderedPage

STAGE = "follow"
ROBOTS_DISALLOWED = "robots_disallowed"


@dataclass(frozen=True)
class FetchResult:
    outcome: str  # FETCHED | FETCH_FAILED | ROBOTS_DISALLOWED
    page: RenderedPage | None = None


@dataclass(frozen=True)
class FollowedPage:
    """A page fetched in this round, for the next pass-1 round."""

    page: RenderedPage
    record: FollowRecord
    artifact: Path


def polite_fetch(robots: Any, throttle: Any, **scrape_kwargs: Any) -> Callable[[str], FetchResult]:
    """The existing fetcher (``scrape_url``) behind the Stage 4 robots check and host throttle."""
    from g3o.scrape.fetcher import scrape_url

    def fetch(url: str) -> FetchResult:
        if robots is not None and not robots.allowed(url):
            return FetchResult(ROBOTS_DISALLOWED)
        delay = robots.crawl_delay(url) if robots is not None else None
        throttle.wait(url, extra_delay=delay)
        failed: list[bool] = []
        page = scrape_url(url, on_redirect_hop=throttle.wait,
                          on_scrape_failure=lambda **_: failed.append(True), **scrape_kwargs)
        return FetchResult(FETCH_FAILED) if failed else FetchResult(FETCHED, page)

    return fetch


def _state_payload(state: InstitutionFollow) -> dict[str, Any]:
    return {
        "institution_id": state.institution_id,
        "release_id": state.release_id,
        "backfill": state.backfill,
        "records": [asdict(r) for r in state.records],
        "not_followed": [asdict(n) for n in state.not_followed],
        "cap": asdict(state.cap_record()),
    }


def run_follow_round(
    run_dir: Path,
    states: Mapping[str, InstitutionFollow],
    pages: Sequence[tuple[Any, Any]],
    *,
    fetch: Callable[[str], FetchResult],
) -> list[FollowedPage]:
    """Run one follow round over ``pages`` (``(Pass1Page, Pass1Extraction)`` pairs).

    Every institution with a page must have a state in ``states`` (its original pages registered
    with :meth:`InstitutionFollow.register_original`). Institutions are handled in sorted id order
    and pages in input order, so the round is deterministic for a given input.
    """
    from g3o.extract.batch import url_hash

    by_inst: dict[str, list[tuple[Any, Any]]] = {}
    for page, extraction in pages:
        if page.institution_id not in states:
            raise KeyError(f"no follow state for institution {page.institution_id}")
        by_inst.setdefault(page.institution_id, []).append((page, extraction))

    out: list[FollowedPage] = []
    for inst_id in sorted(by_inst):
        state = states[inst_id]
        follow_dir = institution_dir(run_dir, inst_id) / "follow"
        n_before = len(state.not_followed)
        for cand in state.candidates(by_inst[inst_id]):
            if not state.take(cand):
                continue
            result = fetch(cand.url)
            fetch_date = result.page.fetch_metadata.access_date if result.page else None
            rec = state.record(cand, result.outcome, fetch_date)
            if result.outcome == FETCHED:
                assert result.page is not None
                path = follow_dir / f"{url_hash(cand.url)}.json"
                write_artifact(path, result.page.model_dump_json())
                out.append(FollowedPage(result.page, rec, path))
            else:
                attrition.record(run_dir, institution_id=inst_id, stage=STAGE,
                                 reason=result.outcome, url=cand.url)
        for nf in state.not_followed[n_before:]:
            attrition.record(run_dir, institution_id=inst_id, stage=STAGE, reason=nf.reason,
                             url=nf.url, detail=f"hop {nf.hop} from {nf.parent_url}")
        follow_dir.mkdir(parents=True, exist_ok=True)
        (follow_dir / "state.json").write_text(
            json.dumps(_state_payload(state), indent=2, sort_keys=True), encoding="utf-8")
    return out


__all__ = ["FetchResult", "FollowedPage", "ROBOTS_DISALLOWED", "STAGE", "polite_fetch",
           "run_follow_round"]
