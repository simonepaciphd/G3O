"""v2.7 follow leg (T-025) inside the per-page stage: the ``followed`` / hop producer.

Order (RC-D-023 C-1 a): every page gets its pass 1 and its own extractor call
(the T-022 page request, whose link task selects the follow-up links) before
anything is followed; each followed page then goes through the per-page stage
like a searched page, with its own pass 1 and its own extractor call. The
per-page stage (:func:`g3o.run.presweep.stage_perpage_v27.run_perpage_v27`)
drives the rounds; this module holds the per-institution follow state and does
the fetching, through the injected ``fetch`` callable only
(:func:`g3o.run.presweep.stage_follow.polite_fetch` binds the existing scrape
path; tests pass fakes).

The rules are :mod:`g3o.scrape.follow` (RC-D-014 S4 cap 10, R-032 hop limit 3,
RC-D-023 C-Q1 b same URL = discovery dedup key, C-Q2 a / C-Q3 b (i) / C-Q4 a
nearness, C-Q5 b every URL tried counts, readings 1-5 and Q6). What this
module adds, each from signed text:

- **Which pages refer onward (R-031).** A page's own final
  ``core.page_complete`` (after the R-044 re-combination and re-gating, B-Q2 b)
  must be ``yes``; the candidates are the links its T-022 page request selected
  (RC-D-002 row 13). A page whose final answer is not ``yes`` is not followed
  from, even if its first-round answer asked for links. A page whose final
  answer is ``yes`` only after an extra round (its first request had no link
  task), or whose links were not measured, is recorded as "complete, links not
  collected" (:data:`LINKS_NOT_COLLECTED`) and not followed (PI ruling 82 c).
- **Supporting quotes (C-Q3 b (i)).** The page's pass-1 quotes that passed the
  T-024 check (``support_status`` ``supported``) at the end of its rounds; the
  option put to the PI was framed on pass-1 quotes (lane C report, Q3).
- **Round order (Q6).** A round's pages are taken in (institution id, URL)
  order; the searched pages are round 0, the pages a round fetched are the next
  round's pages (one hop further).
- **Provenance (R-034, R-036).** ``release_id`` is the run id (reading 5:
  opaque, set by T-030); ``backfill`` is False (this is the new-run path; the
  back-fill leg is T-029). A followed page is ``PageUpstream(followed=True,
  hop=n)``; ``core.discovery_path`` is then ``followed_hop_<n>`` (ruling 61 a).
- **Page fields of a followed page (D1 a).** As a searched page's
  (:func:`g3o.run.presweep.perpage_inputs_v27.page_source_fields`), with
  ``text_source`` ``new_run`` (ruling 62 a: fetched by this run). The A4
  near-duplicate grouping is over all of the institution's pages, searched and
  followed (A4.2 a: the scope is one institution), so a searched page's
  ``syndication_group`` is recomputed once followed pages join. A followed page is
  coded before these exist; PI ruling 112 a: it still gets the residual
  ``source_type`` question at coding time, its archive test worked out from its URL
  (:func:`g3o.run.presweep.stage_perpage_v27.followed_archive_address`, equal to the
  ``archive_address`` :meth:`InstitutionLeg.finish` stores).

Resume (no duplicate fetch, no duplicate paid call). ``<inst>/follow/state_v27.json``
is rewritten atomically after every URL tried; each fetched page is stored as
``<inst>/follow/<url_hash>.json.gz`` before its record is written, and a stored
page is reused instead of fetched again. The jev and extractor calls of a
followed page go through the institution's request journal like any page's.
An exception raised by ``fetch`` itself is not an outcome: it leaves the stage
with the state written so far, and the URL is tried again on the next run.

Follow attempts not reviewed (PI rulings 79 b, 96 a, 102 a, 2026-11-13/14). A URL
tried and not fetched (``fetch_failed``; a robots refusal enters as ``fetch_failed``,
79 b) and a link not followed (cap or hop limit) are recorded in the follow state and
the attrition ledger, and each enters Stage 6 (:func:`unread_products`) as an
unreviewed page (``ReviewedPage`` ``reviewed`` False, failure reason the recorded
outcome; ``failed`` True only for a fetch failure or robots refusal, PI ruling 115 b:
a link not followed is not counted as failed) plus one page-level source row: ``core.page_review_state`` the
review state, ``core.source_url`` the attempt's URL, ``core.page_verdict``
``not_assessable`` and every other item ``not_asked``, the coded ones set by the
named rule :data:`FOLLOW_NOT_REVIEWED`; no observation and no page artifact (path and
hash null, the storage relaxation of 102 a). Such a row is exempt from the A7
syndication grouping (a named exception to 13 a), the single-row-per-page check, the
review-depth count and the Stage 6 A8 pre-check
(:func:`g3o.common.storage.unreviewed_source`). Non-``reviewed`` states count as
unresolved signals in Stage 6 (codebook ``items/core.page_review_state/rules/0``):
such an institution is never ``no``.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, get_args, get_type_hints

from g3o.classify.jev_page_code import PageInput
from g3o.common import attrition
from g3o.common import source_fields as sf
from g3o.common.artifact_io import artifact_exists, read_artifact, write_artifact
from g3o.common.paths import institution_dir
from g3o.common.syndication import group_pages
from g3o.extract.batch import url_hash
from g3o.persist.stage6_adapters import replace_with_retry
from g3o.run.presweep import perpage_inputs_v27 as pin
from g3o.run.presweep import stage_perpage_v27 as pp
from g3o.run.presweep.stage_follow import ROBOTS_DISALLOWED, FetchResult
from g3o.scrape import follow as fl
from g3o.scrape.render import RenderedPage

STAGE = "follow_v27"
FOLLOW_DIR = "follow"
STATE_FILE = "state_v27.json"
STATE_FORMAT = "g3o-follow-state-v27-1"
#: ``core.page_complete`` ``yes``: the page refers the reader onward (the signed note: the name reads the other way)
YES = "yes"
CAP_REACHED = "follow_cap_reached"
#: PI ruling 102 a (building 96 a / 79 b): the named rule that sets an unread follow attempt's
#: ``core.page_verdict`` (``not_assessable``) and its other coded items (``not_asked``)
FOLLOW_NOT_REVIEWED = "follow_not_reviewed"
NOT_ASSESSABLE = "not_assessable"
NOT_ASKED = "not_asked"
#: PI ruling 79 b: the ``core.page_review_state`` of each recorded attempt outcome (a robots refusal is
#: ``fetch_failed``); the values are signed codes (``items/core.page_review_state/rules/0``)
REVIEW_STATE_OF = {fl.FETCH_FAILED: fl.FETCH_FAILED, ROBOTS_DISALLOWED: fl.FETCH_FAILED,
                   fl.LINK_NOT_FOLLOWED_CAP: fl.LINK_NOT_FOLLOWED_CAP,
                   fl.LINK_NOT_FOLLOWED_HOPS: fl.LINK_NOT_FOLLOWED_HOPS}
#: the outcomes of a URL actually tried (``ReviewedPage.followed`` True: it counts in ``n_followed_links``)
TRIED_OUTCOMES = frozenset({fl.FETCH_FAILED, ROBOTS_DISALLOWED})
#: PI ruling 115 b (2026-11-14): the outcomes that count as failed (``ReviewedPage.failed`` True: counted in
#: ``core.review_depth`` ``n_pages_failed`` and the summary's "failed: N"): fetch failures and robots refusals
#: only. A link not followed (cap or hop limit) keeps its unread row (102 a) but is not failed.
FAILED_OUTCOMES = frozenset({fl.FETCH_FAILED, ROBOTS_DISALLOWED})
#: PI ruling 82 c (2026-11-13): a page whose final ``core.page_complete`` is ``yes`` but whose links were not
#: collected (it became ``yes`` only in an extra round, so its first pass-1 request had no link task, or its
#: links were not measured) is recorded as "complete, links not collected" (attrition reason) and not followed.
LINKS_NOT_COLLECTED = "page_complete_links_not_collected"

FetchFn = Callable[[str], FetchResult]


@dataclass(frozen=True)
class FollowPage:
    """The fields of a coded page :meth:`g3o.scrape.follow.InstitutionFollow.candidates` reads."""

    page_id: str
    institution_id: str
    url: str
    text: str
    page_complete: str | None  # the page's final core.page_complete (None: not combined)
    links: tuple[Any, ...] | None


@dataclass(frozen=True)
class RoundPage:
    """One coded page of a round: its final completeness, T-022 page request and supported quotes.

    ``links_collected`` (PI ruling 82 c): the page's first pass-1 request was built on ``page_complete``
    ``yes`` with measured links, so its link task could select links (:func:`round_page`)."""

    page: PageInput
    page_complete: str | None
    extraction: Any  # Pass1Extraction (``page_id``, ``links``) or None (no request was needed)
    supported: tuple[str, ...]
    links_collected: bool = True


def _atomic_write(path: Path, text: str) -> None:
    """The follow state write: a sibling temp file, then ``os.replace`` retried on a transient
    ``PermissionError`` like the per-page checkpoints (:func:`g3o.persist.stage6_adapters.replace_with_retry`).
    An ``OSError`` that survives is not caught here: as for a searched page's checkpoint write, it leaves
    the stage, and the next run resumes from the state written so far (review L4)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_bytes(text.encode("utf-8"))
    replace_with_retry(tmp, path)


def state_payload(state: fl.InstitutionFollow) -> dict[str, Any]:
    """The persisted follow state (records, links not followed, cap record, seen URL keys)."""
    return {
        "format": STATE_FORMAT,
        "institution_id": state.institution_id,
        "release_id": state.release_id,
        "backfill": state.backfill,
        "rules": {"url_cap": state.rules.url_cap, "max_hops": state.rules.max_hops,
                  "count_unfetched": state.rules.count_unfetched},
        "hops": dict(sorted(state.hops.items())),
        "followed": state.followed,
        "cap_reached": state.cap_reached,
        "records": [asdict(r) for r in state.records],
        "not_followed": [asdict(n) for n in state.not_followed],
        "cap": asdict(state.cap_record()),
    }


def load_state(doc: Any, *, institution_id: str, release_id: str,
               rules: fl.FollowRules) -> fl.InstitutionFollow:
    """Rebuild a persisted follow state.

    Review M3: every defect of the stored state stops the stage
    (:class:`~g3o.run.presweep.stage_perpage_v27.FollowWiringError`), consistently: not a JSON object, an
    unsupported format, a state written for another institution, release, back-fill flag or follow
    rules, a missing key, a field of the wrong shape, and a follow count that disagrees with its records.
    """
    if not isinstance(doc, Mapping):
        raise pp.FollowWiringError(f"{institution_id}: the stored follow state is not a JSON object")
    if doc.get("format") != STATE_FORMAT:
        raise pp.FollowWiringError(f"unsupported follow state format {doc.get('format')!r}")
    want = {"url_cap": rules.url_cap, "max_hops": rules.max_hops, "count_unfetched": rules.count_unfetched}
    try:
        stored = (doc["institution_id"], doc["release_id"], doc["rules"], doc["backfill"])
        # Review L-1: equality alone lets 0 stand for False and 10.0 for 10; the types must match too.
        same_types = (type(stored[0]) is str and type(stored[1]) is str and type(stored[3]) is bool
                      and type(stored[2]) is dict and set(stored[2]) == set(want)
                      and all(type(stored[2][k]) is type(v) for k, v in want.items()))
        if not same_types or stored != (institution_id, release_id, want, False):
            raise pp.FollowWiringError(f"{institution_id}: the stored follow state was written for another "
                                       "institution, release, back-fill flag or follow rules")
        state = fl.InstitutionFollow(institution_id, release_id, rules=rules)
        # Review L-1: values are checked, never converted (bool("false") is True; int("3") passes).
        hops = _typed(doc["hops"], dict, "hops", institution_id)
        for k, v in hops.items():
            _typed(k, str, "hops key", institution_id)
            _typed(v, int, f"hops[{k!r}]", institution_id)
        state.hops = dict(hops)
        state.records = [_typed_record(fl.FollowRecord, r, "records", institution_id)
                         for r in _typed(doc["records"], list, "records", institution_id)]
        state.not_followed = [_typed_record(fl.NotFollowed, n, "not_followed", institution_id)
                              for n in _typed(doc["not_followed"], list, "not_followed", institution_id)]
        state.followed = _typed(doc["followed"], int, "followed", institution_id)
        state.cap_reached = _typed(doc["cap_reached"], bool, "cap_reached", institution_id)
    except pp.FollowWiringError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise pp.FollowWiringError(f"{institution_id}: the stored follow state is malformed: "
                                   f"{type(exc).__name__}: {exc}") from exc
    if state.followed != sum(r.counted for r in state.records):
        raise pp.FollowWiringError(f"{institution_id}: the stored follow count disagrees with its records")
    return state


def _typed(value: Any, kind: Any, name: str, institution_id: str) -> Any:
    """``value`` when its type is exactly one of ``kind`` (a type, ``None`` or a tuple of them); else
    :class:`~g3o.run.presweep.stage_perpage_v27.FollowWiringError`. Exact types: a bool is not an int."""
    kinds = kind if isinstance(kind, tuple) else (kind,)
    if not any(value is None if k is None else type(value) is k for k in kinds):
        raise pp.FollowWiringError(f"{institution_id}: the stored follow state is malformed: {name} is "
                                   f"{type(value).__name__} {value!r}, not "
                                   + " or ".join("null" if k is None else k.__name__ for k in kinds))
    return value


def _typed_record(cls: Any, raw: Any, name: str, institution_id: str) -> Any:
    """A stored ``cls`` record (:class:`g3o.scrape.follow.FollowRecord` / ``NotFollowed``) with its
    keys and the type of every field checked (review L-1); a mismatch is a FollowWiringError."""
    raw = _typed(raw, dict, name, institution_id)
    hints = get_type_hints(cls)
    if set(raw) != set(hints):
        raise pp.FollowWiringError(f"{institution_id}: the stored follow state is malformed: a {name} entry "
                                   f"has keys {sorted(raw)}, not {sorted(hints)}")
    for key, hint in hints.items():
        kinds = tuple(None if a is type(None) else a for a in (get_args(hint) or (hint,)))
        _typed(raw[key], kinds, f"{name}.{key}", institution_id)
    return cls(**raw)


@dataclass
class InstitutionLeg:
    """One institution's follow leg over one run of the per-page stage."""

    run_dir: Path
    institution_id: str
    template: PageInput  # a searched page: institution name, country, level, type and disambiguation
    # for followed PageInputs
    state: fl.InstitutionFollow
    fetch: FetchFn
    leg: FollowLeg
    rendered: dict[str, RenderedPage] = field(default_factory=dict)  # page_id -> followed RenderedPage
    hop_of_page: dict[str, int] = field(default_factory=dict)  # page_id -> hop of a followed page

    @property
    def folder(self) -> Path:
        return institution_dir(self.run_dir, self.institution_id) / FOLLOW_DIR

    def _save(self) -> None:
        """Record the attrition the state implies, then write the state (review L4).

        Every link not followed and a reached cap are recorded before the state that holds them is
        written, so an interruption between the two never loses a record. Re-recording is a no-op: the
        ledger dedups on institution, stage, reason and URL (``attrition.record``).
        """
        for nf in self.state.not_followed:
            attrition.record(self.run_dir, institution_id=self.institution_id, stage=STAGE, reason=nf.reason,
                             url=nf.url, detail=f"hop {nf.hop} from {nf.parent_url}")
        if self.state.cap_reached:
            attrition.record(self.run_dir, institution_id=self.institution_id, stage=STAGE, reason=CAP_REACHED,
                             detail=f"{self.state.followed} URL(s) tried, cap {self.state.rules.url_cap}")
        _atomic_write(self.folder / STATE_FILE, json.dumps(state_payload(self.state), indent=2, sort_keys=True))

    def _artifact(self, url: str) -> Path:
        return self.folder / f"{url_hash(url)}.json"

    def _try(self, cand: fl.Candidate) -> None:
        """Fetch one taken candidate (or reuse its stored page) and record it; the state is saved."""
        art = self._artifact(cand.url)
        if artifact_exists(art):  # fetched before an interruption, record not yet written
            page: RenderedPage | None = RenderedPage.model_validate_json(read_artifact(art))
            outcome = fl.FETCHED
        else:
            result = self.fetch(cand.url)
            outcome, page = result.outcome, result.page
            if outcome not in fl.OUTCOMES:
                raise pp.FollowWiringError(f"follow fetch of {cand.url!r} returned unknown outcome {outcome!r}")
            if (outcome == fl.FETCHED) != (page is not None):
                raise pp.FollowWiringError(f"follow fetch of {cand.url!r}: a page is returned exactly when it is "
                                           "fetched")
            if page is not None:
                write_artifact(art, page.model_dump_json())
        if page is not None and page.url != cand.url:
            raise ValueError(f"followed page {page.url!r} is not the URL tried ({cand.url!r})")
        self.state.record(cand, outcome, page.fetch_metadata.access_date if page is not None else None)
        # Review L4: the attrition record goes first, then the state that says the URL was tried, so an
        # interruption between the two never leaves a tried-and-not-fetched URL unrecorded (idempotent).
        if outcome != fl.FETCHED:
            attrition.record(self.run_dir, institution_id=self.institution_id, stage=STAGE, reason=outcome,
                             url=cand.url, detail=f"hop {cand.hop} from {cand.parent_url}")
        self._save()

    def round(self, pages: Sequence[RoundPage]) -> list[pp.PageSpec]:
        """Follow one round's pages; return the pages one hop further, in record order.

        ``pages`` are the round's coded pages (any order: they are taken in
        (institution id, URL) order, Q6). Pages without a page request, or whose
        final ``core.page_complete`` is not ``yes``, offer no candidates. A URL
        already tried in this run (also by an interrupted earlier run) is not
        tried again (R-034); its stored page is returned again, so the next
        round sees the same pages on a resume.
        """
        ordered = sorted(pages, key=lambda p: p.page.url)
        hop = None
        pairs, supported = [], {}
        for p in ordered:
            if p.page.institution_id != self.institution_id:
                raise pp.FollowWiringError(f"page {p.page.page_id} is not {self.institution_id}'s")
            if p.page_complete == YES and not p.links_collected:  # PI ruling 82 c: recorded, not followed
                attrition.record(self.run_dir, institution_id=self.institution_id, stage=STAGE,
                                 reason=LINKS_NOT_COLLECTED, url=p.page.url,
                                 detail="complete, links not collected (PI ruling 82 c)")
                continue
            if p.extraction is None:
                continue
            fp = FollowPage(p.page.page_id, p.page.institution_id, p.page.url, p.page.text, p.page_complete,
                            p.page.links)
            page_hop = self.state.hop_of(p.page.url)
            if hop is not None and page_hop != hop:
                raise pp.FollowWiringError(f"{self.institution_id}: a follow round mixes hops {hop} and {page_hop}")
            hop = page_hop
            pairs.append((fp, p.extraction))
            supported[p.page.page_id] = tuple(p.supported)
        if hop is None:
            return []
        for cand in self.state.candidates(pairs, supported=supported):
            if self.state.take(cand):
                self._try(cand)
        self._save()  # records the links not followed and a reached cap first (review L4)
        return [self._spec(r) for r in self.state.records if r.hop == hop + 1 and r.outcome == fl.FETCHED]

    def _spec(self, rec: fl.FollowRecord) -> pp.PageSpec:
        page = RenderedPage.model_validate_json(read_artifact(self._artifact(rec.url)))
        t = self.template
        inp = pin.rendered_page_input(page, institution_id=self.institution_id, institution=t.institution,
                                      country=t.country, level_of_government=t.level_of_government,
                                      institution_type=t.institution_type, disambiguation=t.disambiguation)
        self.rendered[inp.page_id] = page
        self.hop_of_page[inp.page_id] = rec.hop
        return pp.PageSpec(inp, pp.PageUpstream(followed=True, hop=rec.hop))

    def unreviewed(self) -> list[dict[str, Any]]:
        """Every URL tried and not fetched and every link not followed, in record order (each enters
        Stage 6 through :func:`unread_products`, PI rulings 79 b / 96 a / 102 a)."""
        out = [{"url": r.url, "state": r.outcome, "hop": r.hop, "parent_page_id": r.parent_page_id}
               for r in self.state.records if r.outcome != fl.FETCHED]
        out += [{"url": n.url, "state": n.reason, "hop": n.hop, "parent_page_id": n.parent_page_id}
                for n in self.state.not_followed]
        return out

    def finish(self, specs: Sequence[pp.PageSpec]) -> list[pp.PageSpec]:
        """The institution's specs with the follow page fields: A4 regrouped over every page (A4.2 a), a
        followed page's ``page_fields`` built (D1 a) through :meth:`FollowLeg.followed_upstream`."""
        if not self.rendered:
            return list(specs)
        grouping = group_pages({s.page.page_id: s.page.text for s in specs}, institution_id=self.institution_id)
        out = []
        for s in specs:
            pid = s.page.page_id
            if pid in self.rendered:
                up = self.leg.followed_upstream(self.rendered[pid], s.page, self.hop_of_page[pid], grouping)
            elif s.upstream.page_fields is not None:
                up = replace(s.upstream, page_fields=replace(
                    s.upstream.page_fields, syndication_group=sf.syndication_group_for(grouping, pid)))
            else:
                up = s.upstream
            out.append(replace(s, upstream=up))
        return out


@dataclass(frozen=True)
class FollowLeg:
    """The follow leg handed to ``run_perpage_v27`` (``follow=``): the fetch seam and the rules."""

    fetch: FetchFn
    rules: fl.FollowRules = field(default_factory=fl.FollowRules)

    def __post_init__(self) -> None:
        if not callable(self.fetch):
            raise ValueError("the follow leg needs a fetch callable (stage_follow.polite_fetch or a fake)")

    def start(self, run_dir: Path, inst: pp.PerPageInstitution) -> InstitutionLeg:
        """The institution's leg: its stored state (resume) or a new one, searched pages registered (hop 0)."""
        if not inst.pages:  # the per-page stage never starts a leg without pages (review L5): a caller's gap
            raise pp.FollowWiringError(f"{inst.institution_id}: no searched page to follow from")
        path = institution_dir(run_dir, inst.institution_id) / FOLLOW_DIR / STATE_FILE
        if path.exists():
            try:
                doc = json.loads(path.read_bytes().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:  # review M3: a stage stop
                raise pp.FollowWiringError(f"{inst.institution_id}: the stored follow state is not UTF-8 "
                                           f"JSON: {exc}") from exc
            state = load_state(doc, institution_id=inst.institution_id, release_id=inst.run_id, rules=self.rules)
        else:
            state = fl.InstitutionFollow(inst.institution_id, inst.run_id, rules=self.rules)
        for spec in inst.pages:
            if spec.upstream.followed:
                raise pp.FollowWiringError(f"{spec.page.page_id}: an input page is already followed; the leg "
                                           "follows from searched pages only")
            state.register_original(spec.page.url)
        return InstitutionLeg(Path(run_dir), inst.institution_id, inst.pages[0].page, state, self.fetch, self)

    def followed_upstream(self, rendered: RenderedPage, page: PageInput, hop: int, grouping: Any) -> pp.PageUpstream:
        """A followed page's upstream: ``followed``, its hop and its D1 a page fields (row values: T-015)."""
        return pp.PageUpstream(followed=True, hop=hop,
                               page_fields=pin.page_source_fields(rendered, grouping, page.page_id))


def round_page(spec: pp.PageSpec, page_round: Any, extraction: Any, *, first_complete: str | None) -> RoundPage:
    """A coded page as a follow round reads it: final ``core.page_complete`` and its supported pass-1 quotes.

    ``first_complete`` is the combined ``core.page_complete`` the page's first pass-1 request was built on
    (its T-021 result, ``jev_page_code.to_pass1_page``); the links were collected only when it is ``yes``
    and the page's links were measured (PI ruling 82 c)."""
    from g3o.classify.jev_page_code import COMPLETE
    from g3o.common.support_check import SUPPORTED

    outcome = page_round.final.items.get(COMPLETE)
    complete = outcome.value if outcome is not None and outcome.state == "combined" else None
    quotes = tuple(dict.fromkeys(sr.supporting_text for sr in page_round.support
                                 if sr.support_status == SUPPORTED and sr.supporting_text))
    collected = first_complete == YES and spec.page.links is not None
    return RoundPage(spec.page, complete, extraction, quotes, collected)


def unread_products(attempts: Sequence[Mapping[str, Any]], *, run_id: str, institution_uid: str,
                    institution_id: str, first_source: int, coder_version: str, instrument: dict[str, Any],
                    known_pages: Sequence[str] = ()) -> list[pp.PageProduct]:
    """The Stage 6 inputs of an institution's unread follow attempts (PI rulings 79 b, 96 a, 102 a).

    ``attempts`` are :meth:`InstitutionLeg.unreviewed` entries, in that order; source ids continue from
    ``first_source`` (after every coded page's rows). Each attempt gives one
    :class:`~g3o.run.presweep.stage_perpage_v27.PageProduct`:

    - its page: ``ReviewedPage`` with page id ``url_hash(url)`` (as a fetched page would have),
      ``not_assessable``, support ``set_by_rule``, ``reviewed`` False, failure reason the recorded outcome,
      ``failed`` True only for a fetch failure or robots refusal (:data:`FAILED_OUTCOMES`, PI ruling 115 b: a
      link not followed is not counted in ``n_pages_failed`` / "failed: N"), ``followed`` True only for a URL
      actually tried (:data:`TRIED_OUTCOMES`);
    - one page-level source row: ``core.page_review_state`` from :data:`REVIEW_STATE_OF` (a robots refusal
      is ``fetch_failed``, 79 b), ``core.source_url`` the attempt's URL, ``core.page_verdict``
      ``not_assessable`` and every other sources-table item ``not_asked`` (96 a, 102 a); no observation and
      no page artifact (path and hash null). Each coded item's value (classifier and quote-step items, the
      ones storage keys a support record to) gets a ``set_by_rule`` support node naming
      :data:`FOLLOW_NOT_REVIEWED`, with no quote and no artifact hash, and its mechanical coder record.

    An outcome with no signed review state, or a page id repeated (also of ``known_pages``, the coded
    pages), is a wiring error (:class:`~g3o.run.presweep.stage_perpage_v27.FollowWiringError`).
    """
    from g3o.classify.jev_page_code import VERDICT
    from g3o.common.jev_record import CoderRecord
    from g3o.common.storage import METADATA_ITEMS, UNREVIEWED_STATES, table_fields
    from g3o.common.storage_fields import FIELDS
    from g3o.common.support_check import SET_BY_RULE, CodeEvidence, PageSources, check_code
    from g3o.persist.stage6_adapters import PageArtifact, SupportContext, coder_nodes, support_nodes
    from g3o.validate import uncertainty_flags_v27 as uf
    from g3o.validate.consolidate_v27 import ReviewedPage

    items = sorted(set(table_fields("sources")) - set(METADATA_ITEMS))
    coded = [i for i in items if FIELDS[i]["coder"] in ("classifier", "quote_step")]
    qsv = instrument["payload"]["question_set_version"]
    seen = set(known_pages)
    out: list[pp.PageProduct] = []
    for n, attempt in enumerate(attempts):
        url, outcome = attempt["url"], attempt["state"]
        state = REVIEW_STATE_OF.get(outcome)
        if state not in UNREVIEWED_STATES:
            raise pp.FollowWiringError(f"{institution_id}: follow attempt {url!r} has outcome {outcome!r}, "
                                       "which has no signed non-reviewed review state")
        page_id = url_hash(url)
        if page_id in seen:
            raise pp.FollowWiringError(f"{institution_id}: unread follow attempt {url!r} repeats page id {page_id}")
        seen.add(page_id)
        sid = pp.source_id(first_source + n)
        values: dict[str, Any] = {item: NOT_ASKED for item in items}
        values.update({VERDICT: NOT_ASSESSABLE, sf.URL: url, sf.REVIEW_STATE: sf.page_review_state(state).value})
        sources = PageSources(page_id, {}, None)
        no_page = PageArtifact(sid, "", "", {})  # nothing stored: the nodes carry no artifact hash (102 a)
        support: list[dict[str, Any]] = []
        coders: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        for item in coded:
            sr = check_code(CodeEvidence(item, values[item], None, rule_name=FOLLOW_NOT_REVIEWED), sources)
            nodes = support_nodes(sr, sources, no_page, SupportContext(run_id, institution_uid, None, sid,
                                                                       uf.code_flags(sr)), instrument)
            node = {**nodes.original, "page_content_sha256": None}  # not part of the support id
            nodes = replace(nodes, original=node)
            rec = CoderRecord(item_id=item, item_part=None, question_id=None, support_id=node["support_id"],
                              observation_id=None, chunk_id=None, coder_type="mechanical",
                              coder_version=coder_version, configured_model=None, actual_response_model=None,
                              request_id=None, question_set_version=qsv, setup_pointer=instrument["instrument_id"],
                              answer_type="rule", chosen_value=values[item], confidence=None,
                              probability_distribution=None, rule_reference=FOLLOW_NOT_REVIEWED)
            projection, _, _ = coder_nodes(rec, nodes, instrument)
            support.append(node)
            coders.append(projection)
            provenance.append(nodes.provenance)
        verdict = next(s for s in support if s["item_id"] == VERDICT)
        verdict_coder = next(c for c in coders if c["support_id"] == verdict["support_id"])
        page = ReviewedPage(page_id, pp.PIPELINE, NOT_ASSESSABLE, None, SET_BY_RULE, False,
                            outcome in FAILED_OUTCOMES, outcome in TRIED_OUTCOMES, (sid,), (verdict_coder,),
                            (verdict,), failure_reason=outcome)
        row = {"values": values, "item_support": support, "coder_records": coders, "observation_ids": [],
               "page_artifact_path": None, "page_content_sha256": None}
        out.append(pp.PageProduct(page=page, sources={sid: row}, provenance=provenance))
    return out


__all__ = ["CAP_REACHED", "FAILED_OUTCOMES", "FOLLOW_NOT_REVIEWED", "LINKS_NOT_COLLECTED", "FOLLOW_DIR", "NOT_ASKED", "NOT_ASSESSABLE",
           "REVIEW_STATE_OF", "ROBOTS_DISALLOWED", "STAGE", "STATE_FILE", "STATE_FORMAT", "TRIED_OUTCOMES", "FetchFn",
           "FollowLeg", "FollowPage", "InstitutionLeg", "RoundPage", "load_state", "round_page", "state_payload",
           "unread_products"]
