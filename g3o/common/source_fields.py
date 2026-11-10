"""Source-level field coder (T-015; RC-D-002 H Q3, N25, O2; RC-D-023 B-Q3 a).

One producer per source-level item of the signed codebook (r15, sha256
``ca1bf616…fc73d3a``, PI-signed 2026-11-10, ``planning/t010/signoff-record.md``): every item whose ``level`` includes ``source``. Values,
codes, missing tokens, support statuses and the date-origin map are read from
the codebook through :mod:`g3o.codebook`; nothing here restates an enum the
loader provides. Where a signed slot states its codes only inside rule text
(``source_on_official_domain``, ``page_review_state``), the backticked codes of
that slot are read verbatim.

Producers and their signed rules:

- ``core.source_type`` (X21; r2#25, r2#30). Rule 0: official pages are typed
  from the web domain and archive copies from the address, and "pages typed
  that way are not asked"; such a page stores ``not_asked`` (R-045, set by rule
  ``source_type_auto:<basis>``). Every other page is asked the residual
  classifier question (:func:`code_source_type`): the signed question, as
  generated from the codebook, in the approved pass-1 page state (W-01 / W-02,
  T-011 page set), combined across parts by the item's ``first_section`` rule
  (T-021 machinery, :func:`g3o.classify.jev_page_code.code_page`).
- ``core.source_credibility`` (X22; RC-D-025 C5, C6 a): rules/0 "fixed map
  from ``source_type`` plus ``low`` when ``source_publication_date`` = unknown
  or not_documented"; rules/1 and the structured
  ``items/core.source_credibility/credibility_map`` hold the cells, including
  the automatic keys ``official_domain`` / ``archive_address`` and the missing
  keys (``not_documented``, ``unknown`` -> ``low``, PI "5f low"). Read by
  :func:`signed_credibility_map`; no copy of the cells lives here.
- ``core.confidence`` at source level (X23, r2#27; RC-D-025 A1, C7 a):
  :func:`source_confidence_rule`, ``items/core.confidence/rules/1``.
  Aggregation of an ``unknown`` source (C8 b, ``items/core.confidence/rules/2``)
  belongs to consolidation (T-026); :func:`aggregation_value` gives T-026 the
  value to use.
- ``core.source_publication_date`` (X26, r2#31) and ``core.date_upper_bound``:
  metadata first, then the quote step's date checked by T-024 (R-042), with
  the date origin and its provenance from ``vocabularies.provenance.date_origin_map``.
- ``core.source_snippet`` (X25, r2#35): the page verdict's supporting quote,
  verbatim, checked by T-024. Stored whole (R-043, RC-D-017 "2 whole"; RC-D-025 P14);
  :func:`g3o.common.support_check.display_cap` gives the displayed prefix.
- ``core.source_url`` / ``core.source_title`` / ``core.source_access_date`` (X28).
- ``core.source_on_official_domain`` (X37): URL host vs the master
  official-site overlay, hosts compared with :func:`g3o.common.urlnorm.site_host`,
  exact host equality (RC-D-025 P13).
- ``core.page_review_state`` (X39): the caller's fetch/follow state, checked
  against the signed codes.
- ``core.source_language`` (X27), ``core.syndication_group`` (X38),
  ``core.discovery_path``, ``core.text_source``: no producer or no signed
  spelling/parameter exists; each refuses explicitly (RC-D-025 P15). So do the
  metadata/URL date producer and the archive-host list.

Source confidence: the signed r14 rule ``items/core.confidence/rules/1``
(RC-D-025 A1, from the PI rule of 2026-11-07, widened by C7 a), plus the
PI-approved procedural points P10-P12 (2026-11-10 "approve all"). The whole
rule lives in :func:`source_confidence_rule`. Activity-level aggregation is
consolidation's (T-026, ``g3o/common/consolidate_v27.py``) and is not
repeated here; C8 b is exposed to it only as :func:`aggregation_value`.

Missing inputs raise :class:`MissingUpstreamError` naming the producer; open
codebook questions raise :class:`UnruledError`. No value is ever filled from a
fixture default or a guess.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from g3o.codebook.loader import Codebook, load_codebook
from g3o.common.support_check import (
    PAGE_VERDICT,
    SET_BY_RULE,
    CodeEvidence,
    Entailment,
    PageSources,
    SupportResult,
    check_code,
)
from g3o.common.support_check import (
    SIGNED_CODEBOOK_SHA256 as SUPPORT_CHECK_CODEBOOK_SHA256,
)
from g3o.common.urlnorm import site_host

#: Codebook r15, PI-signed 2026-11-10 (planning/t010/signoff-record.md).
SIGNED_CODEBOOK_SHA256 = "ca1bf616d596213dad7064bd24921928186bce42d912a7b54e5723f41fc73d3a"
if SIGNED_CODEBOOK_SHA256 != SUPPORT_CHECK_CODEBOOK_SHA256:  # pragma: no cover - pin drift guard
    raise ImportError("source_fields and support_check pin different codebook releases")

CODER_VERSION = "g3o.common.source_fields.v2"
#: The residual source_type request is not part of a T-011 set (EXCLUDED there); its
#: own version names the composition: signed codebook question + approved page state.
RESIDUAL_SET_VERSION = "g3o.common.source_fields.source_type_residual.v1"

CONFIDENCE_DECISION = (
    "codebook r14 items/core.confidence/rules/1 (RC-D-025 A1, C7 a; PI-signed 2026-11-10); "
    "procedural RC-D-025 P10-P12 (PI 2026-11-10 'approve all')"
)
#: The role of the C8 b slot in items/core.confidence/rules (r14).
AGGREGATION_ROLE = "aggregation of unknown"

SOURCE_TYPE = "core.source_type"
CREDIBILITY = "core.source_credibility"
CONFIDENCE = "core.confidence"
DATE = "core.source_publication_date"
UPPER_BOUND = "core.date_upper_bound"
SNIPPET = "core.source_snippet"
URL = "core.source_url"
TITLE = "core.source_title"
ACCESS_DATE = "core.source_access_date"
LANGUAGE = "core.source_language"
OFFICIAL = "core.source_on_official_domain"
SYNDICATION = "core.syndication_group"
REVIEW_STATE = "core.page_review_state"
DISCOVERY = "core.discovery_path"
TEXT_SOURCE = "core.text_source"

AUTO_OFFICIAL = "official_domain"
AUTO_ARCHIVE = "archive_address"
AUTO_RULE = "source_type_auto:"
READABILITY_RULE = "readability_failure:"

#: Explicit not-scored state of source confidence (confidence.missing). Never stored as a grade.
UNFINISHED = "unfinished"

#: v2.5 contract §X26 forms (YYYY-MM-DD / YYYY-MM / YYYY), the stored date grammar.
_DATE_RE = re.compile(r"^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$")
_ISO_DAY = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
_BACKTICK = re.compile(r"`([A-Za-z_]+)`")


class MissingUpstreamError(ValueError):
    """An input whose producer is absent; never replaced by a default.

    Same shape as ``g3o.persist.stage6_adapters.MissingUpstreamError`` (T-028).
    """

    def __init__(self, producer: str, missing: Sequence[str] = ()) -> None:
        self.producer = producer
        self.missing = tuple(missing)
        detail = f": {', '.join(self.missing)}" if self.missing else ""
        super().__init__(f"missing upstream input from {producer}{detail}")


class UnruledError(ValueError):
    """The signed codebook (or the PI confidence decision) leaves this case open.

    Stop the field and report the question to the plan integrator; do not guess.
    """

    def __init__(self, item_id: str, question: str) -> None:
        self.item_id = item_id
        self.question = question
        super().__init__(f"{item_id}: unruled: {question}")


class UnfinishedConfidenceError(ValueError):
    """A source's confidence is ``unfinished`` (pending checks) and cannot be scored."""

    def __init__(self, source_ids: Sequence[str]) -> None:
        self.source_ids = tuple(source_ids)
        super().__init__(f"source confidence unfinished (pending checks): {', '.join(self.source_ids)}")


# ---------------------------------------------------------------------------
# Codebook vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceVocab:
    """What this module reads from the signed codebook."""

    codebook_sha256: str
    source_items: tuple[str, ...]  # every item with level `source`
    items: Mapping[str, Mapping[str, Any]]
    missing: frozenset[str]  # vocabularies.missing
    not_required_values: frozenset[str]  # status_by_answer -> not_required
    rule_values: frozenset[str]  # status_by_answer -> set_by_rule
    negative_verdicts: frozenset[str]
    downgrades: frozenset[str]  # the three downgraded_* support statuses
    support_statuses: frozenset[str]
    source_type_codes: tuple[str, ...]
    source_type_labels: Mapping[str, str]  # entailment_label per code (signed)
    credibility_values: tuple[str, ...]
    date_origin_map: Mapping[str, str]  # date origin -> provenance value
    official_values: tuple[str, ...]
    review_states: tuple[str, ...]
    aggregation_rule: tuple[str, str]  # (path, text) of the C8 b slot of core.confidence
    aggregation_map: Mapping[str, str]  # C8 b: source value -> value it counts as in aggregation

    def missing_tokens(self, item_id: str) -> tuple[str, ...]:
        return tuple(self.items[item_id].get("missing_tokens") or ())

    def coder(self, item_id: str) -> str:
        return str(self.items[item_id]["coder"])


def _rule_codes(cb: Codebook, item_id: str, index: int = 0) -> tuple[str, ...]:
    text = cb.rule_texts(item_id)[index].text
    return tuple(dict.fromkeys(_BACKTICK.findall(text)))


def _aggregation_rule(cb: Codebook) -> tuple[tuple[str, str], dict[str, str]]:
    """The C8 b slot of ``core.confidence`` (role ``aggregation of unknown``) and its codes.

    The text names two codes, "a source whose confidence is `unknown` counts as
    `low`", read in order as (counted-from, counted-as).
    """
    rules = cb.items[CONFIDENCE].get("rules") or []
    slots = [n for n, r in enumerate(rules) if isinstance(r, Mapping) and r.get("role") == AGGREGATION_ROLE]
    if len(slots) != 1:
        raise ValueError(f"codebook has {len(slots)} core.confidence rules with role {AGGREGATION_ROLE!r}")
    path = f"items/{CONFIDENCE}/rules/{slots[0]}"
    text = next(r.text for r in cb.rule_texts(CONFIDENCE) if r.path == path)
    codes = tuple(dict.fromkeys(_BACKTICK.findall(text)))
    if len(codes) != 2:
        raise ValueError(f"{path}: expected two backticked codes, found {codes}")
    return (path, text), {codes[0]: codes[1]}


def vocab_from_codebook(cb: Codebook) -> SourceVocab:
    if cb.sha256 != SIGNED_CODEBOOK_SHA256:
        raise ValueError(f"codebook sha256 {cb.sha256} is not the signed r15 release")
    agg_rule, agg_map = _aggregation_rule(cb)
    items = cb.build_items()
    status = cb.vocabularies["support_status"]
    by_answer = {k: v for k, v in status["status_by_answer"].items() if re.fullmatch(r"[A-Za-z_]+", k)}
    statuses = frozenset(cb.vocab_values("support_status"))
    st_values = cb.value_list(SOURCE_TYPE) or []
    cred_map = (items[CREDIBILITY].get("translation_v25") or {}).get("map") or {}
    origin_map = cb.vocabularies["provenance"]["date_origin_map"]["map"]
    return SourceVocab(
        codebook_sha256=cb.sha256,
        source_items=tuple(k for k, v in items.items() if "source" in (v.get("level") or ())),
        items=items,
        missing=frozenset(cb.vocab_values("missing")),
        not_required_values=frozenset(k for k, v in by_answer.items() if v == "not_required"),
        rule_values=frozenset(k for k, v in by_answer.items() if v == SET_BY_RULE),
        negative_verdicts=frozenset(status["negative_page_verdicts"]["values"]),
        downgrades=frozenset(s for s in statuses if s.startswith("downgraded_")),
        support_statuses=statuses,
        source_type_codes=tuple(cb.codes(SOURCE_TYPE) or ()),
        source_type_labels={str(v["code"]): v["entailment_label"]["text"] for v in st_values},
        # The signed v2.5 translation map of the item lists its values (high, medium, low).
        credibility_values=tuple(str(k) for k in cred_map),
        date_origin_map={str(k): str(v) for k, v in origin_map.items()},
        official_values=_rule_codes(cb, OFFICIAL),
        review_states=_rule_codes(cb, REVIEW_STATE),
        aggregation_rule=agg_rule,
        aggregation_map=agg_map,
    )


@lru_cache(maxsize=1)
def default_vocab() -> SourceVocab:
    return vocab_from_codebook(load_codebook())


# ---------------------------------------------------------------------------
# Output record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldValue:
    """One coded source-level value with its coder and basis (PLAN T-015 output contract)."""

    item_id: str
    value: str
    coder: str  # the codebook coder of the item
    basis: str  # the rule / input that fixed the value
    rule_name: str | None = None  # set when a rule fixed the value (support status set_by_rule)
    provenance: str | None = None  # vocabularies.provenance value, where the item records one
    date_origin: str | None = None  # date items only (date_origin_map key)
    support: SupportResult | None = None  # the T-024 record, for quote-step items
    detail: Mapping[str, Any] = field(default_factory=dict)


def _fv(item_id: str, value: str, basis: str, v: SourceVocab, **kw: Any) -> FieldValue:
    return FieldValue(item_id, value, v.coder(item_id), basis, **kw)


# ---------------------------------------------------------------------------
# X28: url, title, access date
# ---------------------------------------------------------------------------


def source_url(input_url: str | None, *, vocab: SourceVocab | None = None) -> FieldValue:
    """The supplied page's URL, verbatim from the input; never altered."""
    v = vocab or default_vocab()
    if input_url is None or not input_url.strip():
        raise MissingUpstreamError("scraper page input (supplied URL)", [URL])
    return _fv(URL, input_url, "items/core.source_url/rules/0: verbatim input URL", v)


def source_title(rendered_title: str | None, first_heading: str | None, *,
                 vocab: SourceVocab | None = None) -> FieldValue:
    """RenderedPage.title, else the first heading; never from a model.

    Both absent (measured and empty): ``not_documented`` (R-045, the page is silent).
    """
    v = vocab or default_vocab()
    if rendered_title is not None and rendered_title.strip():
        return _fv(TITLE, rendered_title, "RenderedPage.title", v)
    if first_heading is not None and first_heading.strip():
        return _fv(TITLE, first_heading, "first heading (title empty)", v)
    return _fv(TITLE, "not_documented", "no title and no heading on the page", v)


def source_access_date(scrape_date: str | None, *, vocab: SourceVocab | None = None) -> FieldValue:
    """The scrape date from the input metadata (ISO ``YYYY-MM-DD``)."""
    v = vocab or default_vocab()
    if scrape_date is None:
        raise MissingUpstreamError("scraper page metadata (scrape date)", [ACCESS_DATE])
    if not _ISO_DAY.fullmatch(scrape_date):
        raise ValueError(f"scrape date {scrape_date!r} is not an ISO day")
    return _fv(ACCESS_DATE, scrape_date, "input metadata scrape date", v,
               provenance=v.date_origin_map["access_date"], date_origin="access_date")


# ---------------------------------------------------------------------------
# X37: official domain; X39: review state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OfficialSiteOverlay:
    """The master official-site overlay (``g3o.report.site_overlay`` CSV): uid -> official site URL."""

    version: str  # recorded in the run setup (X36)
    sites: Mapping[str, str]

    def hosts(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for uid, url in self.sites.items():
            host = site_host(url)
            if host is None:
                raise ValueError(f"overlay site for {uid!r} has no host: {url!r}")
            out[uid] = host
        return out


def source_on_official_domain(url: str, institution_uid: str, overlay: OfficialSiteOverlay | None, *,
                              vocab: SourceVocab | None = None) -> FieldValue:
    """``own_official`` / ``other_official`` / ``not_official`` from URL host vs the overlay.

    Hosts are compared with :func:`site_host` (lowercase, ``www.`` dropped, port
    kept), exact equality, no subdomain or suffix matching (RC-D-025 P13). When
    the overlay holds no site for this institution and the host matches no
    other institution, own vs not cannot be told: ``unknown`` (P13). A host that
    matches another institution's site is ``other_official`` even when this
    institution is not in the overlay (behaviour kept from v1; see the T-015
    report, open question on P13).
    """
    v = vocab or default_vocab()
    own, other, not_official = v.official_values
    if overlay is None:
        raise MissingUpstreamError("master official-site overlay", [OFFICIAL])
    host = site_host(url)
    if host is None:
        raise ValueError(f"source URL has no host: {url!r}")
    hosts = overlay.hosts()
    basis = f"overlay {overlay.version}; host {host}"
    if hosts.get(institution_uid) == host:
        return _fv(OFFICIAL, own, basis, v, provenance="from_metadata")
    if any(uid != institution_uid and h == host for uid, h in hosts.items()):
        return _fv(OFFICIAL, other, basis, v, provenance="from_metadata")
    if institution_uid not in hosts:
        return _fv(OFFICIAL, "unknown", basis + "; institution not covered by the overlay", v)
    return _fv(OFFICIAL, not_official, basis, v, provenance="from_metadata")


def page_review_state(state: str | None, *, vocab: SourceVocab | None = None) -> FieldValue:
    """The page's review state, as the fetch/follow stage recorded it (signed codes only)."""
    v = vocab or default_vocab()
    if state is None:
        raise MissingUpstreamError("T-025/T-030 fetch and follow outcome", [REVIEW_STATE])
    if state not in v.review_states:
        raise ValueError(f"page review state {state!r} is not a signed code {v.review_states}")
    return _fv(REVIEW_STATE, state, "fetch/follow outcome", v)


# ---------------------------------------------------------------------------
# Items with no producer or no signed parameter
# ---------------------------------------------------------------------------


def source_language(*_: Any, **__: Any) -> FieldValue:
    """X27 needs a pinned local language-ID library and the ``mul`` share; neither exists."""
    raise MissingUpstreamError(
        "pinned local language-ID library (none installed or pinned) and the signed `mul` share "
        "(items/core.source_language/rules/0 says 'a set share'; no value is signed)", [LANGUAGE])


def syndication_group(group_id: str | None, *, vocab: SourceVocab | None = None) -> FieldValue:
    """X38 group id from a near-duplicate grouping; method parameters are unsigned, so only
    an upstream group id is accepted."""
    v = vocab or default_vocab()
    if group_id is None or not group_id.strip():
        raise MissingUpstreamError(
            "near-duplicate grouping (items/core.syndication_group/rules/0: method 'e.g. shingled "
            "MinHash', threshold unsigned)", [SYNDICATION])
    return _fv(SYNDICATION, group_id, "upstream near-duplicate group", v)


def discovery_path(*_: Any, **__: Any) -> FieldValue:
    raise UnruledError(DISCOVERY, "value spellings ('searched / followed hop n / back-fill followed') "
                                  "are not signed as codes")


def text_source(*_: Any, **__: Any) -> FieldValue:
    raise UnruledError(TEXT_SOURCE, "value spellings ('stored / live re-fetch / new run') are not "
                                    "signed as codes")


# ---------------------------------------------------------------------------
# X21: source_type (automatic typing, then the residual classifier question)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceTyping:
    """``source_type`` and how it was decided.

    ``typed_by``: ``official_domain`` / ``archive_address`` (typed automatically,
    value ``not_asked``), ``classifier`` (residual question) or ``readability``
    (page not sent; ``not_asked``).
    """

    field: FieldValue
    typed_by: str
    outcome: Any = None  # jev_page_code.ItemOutcome for the classifier path
    records: tuple[Any, ...] = ()  # CoderRecords (asked and superseded)
    result: Any = None  # the full jev_page_code.PageCodeResult


def route_source_type(official: FieldValue, archive_address: bool | None) -> str | None:
    """The automatic type (``official_domain`` / ``archive_address``) or None (ask the question).

    Rule 0 (items/core.source_type/rules/0): official from the web domain (X37
    ``own_official`` or ``other_official``), archive from the address. The
    archive-address test has no signed host list; the caller supplies it.
    """
    if official.item_id != OFFICIAL:
        raise ValueError("route_source_type needs the core.source_on_official_domain value")
    if archive_address is None:
        raise MissingUpstreamError("archive-address test (no signed archive host list)", [SOURCE_TYPE])
    own, other, _ = default_vocab().official_values
    if official.value in (own, other):
        return AUTO_OFFICIAL
    if archive_address:
        return AUTO_ARCHIVE
    return None


def auto_source_type(basis: str, *, vocab: SourceVocab | None = None) -> SourceTyping:
    """A page typed automatically is not asked: ``not_asked``, set by rule (R-045, rule 0)."""
    v = vocab or default_vocab()
    if basis not in (AUTO_OFFICIAL, AUTO_ARCHIVE):
        raise ValueError(f"unknown automatic source type basis {basis!r}")
    return SourceTyping(_fv(SOURCE_TYPE, "not_asked", "items/core.source_type/rules/0", v,
                            rule_name=AUTO_RULE + basis), typed_by=basis)


@lru_cache(maxsize=1)
def residual_question_set() -> dict[str, Any]:
    """The approved page state (T-011 page set) with the signed generated source_type question."""
    from g3o.classify.questions.v27 import load_set
    from g3o.codebook.generators import gen_jev_questions

    cb = load_codebook()
    if cb.sha256 != SIGNED_CODEBOOK_SHA256:
        raise ValueError("codebook is not the signed release")
    page = load_set("page")
    if page["codebook_sha256"] != cb.sha256:
        raise ValueError("page question set and codebook differ")
    gen = json.loads(gen_jev_questions(cb).content)
    question = next(q for q in gen["questions"] if q["item_id"] == SOURCE_TYPE)
    return {**page, "question_set": "source_type_residual", "question_set_version": RESIDUAL_SET_VERSION,
            "questions": [question], "excluded": []}


def code_source_type(page: Any, ask_fn: Any, config: Any, *, vocab: SourceVocab | None = None,
                     on_response: Any = None) -> SourceTyping:
    """Ask the residual ``source_type`` question of a page not typed automatically.

    ``page`` is a :class:`g3o.classify.jev_page_code.PageInput`, ``config`` a
    ``PageCoderConfig`` (its ``question_set`` is replaced by
    :func:`residual_question_set`); ``ask_fn`` is the injected jev call. A page
    that fails the R-015 readability check is not sent (``not_asked``, set by
    rule ``readability_failure:<reason>``, as T-021).
    """
    from dataclasses import replace

    from g3o.classify import jev_page_code as jpc
    from g3o.scrape.readability import readability_failure

    v = vocab or default_vocab()
    reason = readability_failure(page.text)
    if reason is not None:
        rule = READABILITY_RULE + reason
        return SourceTyping(_fv(SOURCE_TYPE, "not_asked", "R-015 readability failure", v, rule_name=rule),
                            typed_by="readability")
    res = jpc.code_page(page, ask_fn, replace(config, question_set=residual_question_set()),
                        on_response=on_response)
    outcome = res.items[SOURCE_TYPE]
    if outcome.state == "stopped":
        raise UnruledError(SOURCE_TYPE, f"combiner stopped: {outcome.error}")
    value = str(outcome.value)
    if value not in (*v.source_type_codes, *v.missing_tokens(SOURCE_TYPE)):
        raise ValueError(f"source_type answer {value!r} is not a signed code")
    fv = _fv(SOURCE_TYPE, value, f"residual classifier question, first_section, part {outcome.part_id}", v,
             detail={"probability": outcome.probability, "failed": outcome.failed, "cause": outcome.cause})
    return SourceTyping(fv, typed_by="classifier", outcome=outcome,
                        records=(*res.records, *res.superseded), result=res)


def source_type_evidence(typing: SourceTyping, *, quote: str | None, quote_chunk_id: str | None,
                         entailment: Entailment | None) -> CodeEvidence:
    """The T-024 input for the classifier-typed ``source_type``.

    ``quote`` comes from the quote step and ``entailment`` from X35 (the item has
    an entailment label). Neither producer covers ``source_type`` yet: T-022's
    request plan has no source_type quote task.
    """
    if typing.typed_by != "classifier" or typing.outcome is None:
        raise ValueError("only a classifier-typed source_type is support-checked")
    o = typing.outcome
    return CodeEvidence(item_id=SOURCE_TYPE, value=str(o.value), chunk_id=o.part_id, probability=o.probability,
                        quote=quote, quote_chunk_id=quote_chunk_id, entailment=entailment)


def source_type_label(typing: SourceTyping, *, vocab: SourceVocab | None = None) -> str:
    """The signed entailment label consolidate_v27 shows for a pooled quote (RC-D-023 A-5 a)."""
    v = vocab or default_vocab()
    value = typing.field.value
    if value not in v.source_type_labels:
        raise UnruledError(SOURCE_TYPE, f"no signed label for {value!r} (typed by {typing.typed_by}); "
                                        "automatically typed and missing values have none")
    return v.source_type_labels[value]


# ---------------------------------------------------------------------------
# X26: publication date and date_upper_bound
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetadataDate:
    """A deterministic date candidate: ``origin`` ``metadata`` (HTML metadata, PDF
    properties) or ``web_address`` (URL pattern). Producer: not yet built."""

    value: str
    origin: str
    detail: str


def _date_value(value: str) -> str:
    if not _DATE_RE.fullmatch(value):
        raise ValueError(f"date {value!r} is not YYYY-MM-DD / YYYY-MM / YYYY")
    return value


def publication_date(metadata_dates: Sequence[MetadataDate] | None, quote_date: Any, sources: PageSources | None,
                     *, vocab: SourceVocab | None = None) -> FieldValue:
    """Metadata first, then the quote step's date checked under R-042 (items/core.source_publication_date/rules/0).

    ``metadata_dates``: None = the deterministic producer did not run (refused);
    empty = it ran and found none. ``quote_date``: the T-022
    ``Pass1Extraction.publication_date`` (a ``FieldValue`` with ``value``,
    ``chunk_id``, ``supporting_text``) or None. A quote-step date that fails
    the check takes ``unknown`` (``downgrade_target``). Neither: ``not_documented``.
    """
    v = vocab or default_vocab()
    if metadata_dates is None:
        raise MissingUpstreamError("deterministic metadata/URL date producer (none built)", [DATE])
    by_origin: dict[str, set[str]] = {}
    for m in metadata_dates:
        if m.origin not in ("metadata", "web_address"):
            raise ValueError(f"metadata date origin {m.origin!r} is not metadata or web_address")
        by_origin.setdefault(m.origin, set()).add(_date_value(m.value))
    for origin in ("metadata", "web_address"):  # the rule's order: metadata / PDF properties, then URL
        found = by_origin.get(origin)
        if not found:
            continue
        if len(found) > 1:
            raise UnruledError(DATE, f"{origin} candidates disagree {sorted(found)}; no signed tie rule")
        (value,) = found
        return _fv(DATE, value, f"deterministic {origin} date", v,
                   provenance=v.date_origin_map[origin], date_origin=origin)
    if quote_date is None:
        return _fv(DATE, "not_documented", "no metadata date and no quote-step date", v,
                   date_origin="unknown")
    if sources is None:
        raise MissingUpstreamError("stored page texts (PageSources) for the R-042 check", [DATE])
    ev = CodeEvidence(item_id=DATE, value=_date_value(quote_date.value), chunk_id=quote_date.chunk_id,
                      quote=quote_date.supporting_text, quote_chunk_id=quote_date.chunk_id)
    res = check_code(ev, sources)
    if res.value != res.original_value:
        return _fv(DATE, res.value, "quote-step date failed the R-042 check", v, date_origin="unknown",
                   support=res)
    return _fv(DATE, res.value, "quote-step date, supported", v,
               provenance=v.date_origin_map["page_text_quote"], date_origin="page_text_quote", support=res)


def date_upper_bound(date: FieldValue, *, vocab: SourceVocab | None = None) -> FieldValue:
    """The yes/no note "this date is an upper bound": yes only for an archive bound."""
    v = vocab or default_vocab()
    if date.item_id != DATE:
        raise ValueError("date_upper_bound needs the core.source_publication_date value")
    if date.value in v.missing:
        return _fv(UPPER_BOUND, "not_asked", "no date to qualify", v, rule_name="no_publication_date")
    yes, no = default_codebook().codes(UPPER_BOUND) or ()
    value = yes if date.date_origin == "archive_upper_bound" else no
    return _fv(UPPER_BOUND, value, f"date origin {date.date_origin}", v)


@lru_cache(maxsize=1)
def default_codebook() -> Codebook:
    return load_codebook()


# ---------------------------------------------------------------------------
# X25: snippet
# ---------------------------------------------------------------------------


def source_snippet(verdict_support: SupportResult | None, sources: PageSources | None, *,
                   vocab: SourceVocab | None = None) -> FieldValue:
    """The page verdict's supporting quote, verbatim and whole, checked by T-024.

    Stored whole, never truncated (RC-D-025 P14; R-043); the display prefix is
    :func:`g3o.common.support_check.display_cap`.

    No verdict quote, or one that fails the check: ``unknown`` with
    ``downgraded_no_quote`` (R-041; ``downgrade_target`` unknown).
    """
    v = vocab or default_vocab()
    if verdict_support is None:
        raise MissingUpstreamError("T-024 support record of the page verdict", [SNIPPET])
    if verdict_support.item_id != PAGE_VERDICT:
        raise ValueError("source_snippet needs the page verdict's support record")
    quote = verdict_support.supporting_text
    if sources is None:
        raise MissingUpstreamError("stored page texts (PageSources) for the R-042 check", [SNIPPET])
    chunk = verdict_support.quote_chunk_id or verdict_support.chunk_id
    if quote is None:
        res = SupportResult(item_id=SNIPPET, part=None, activity_id=None, chunk_id=chunk, original_value="",
                            value="unknown", support_status="downgraded_no_quote",
                            support_status_second_reason=None, support_rule_name=None, supporting_text=None,
                            quote_chunk_id=None, match=None, chosen_answer_probability=None, entailment=None)
        return _fv(SNIPPET, "unknown", "the page verdict has no supporting quote", v, support=res)
    res = check_code(CodeEvidence(item_id=SNIPPET, value=quote, chunk_id=chunk, quote=quote,
                                  quote_chunk_id=chunk), sources)
    basis = "page verdict quote, supported" if res.value == quote else "page verdict quote failed R-042"
    return _fv(SNIPPET, res.value, basis, v, provenance="quoted_by_quote_step" if res.value == quote else None,
               support=res)


# ---------------------------------------------------------------------------
# X22: credibility
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CredibilityMap:
    """``source_type`` (or automatic basis, or missing token) -> credibility, from a signed release."""

    cells: Mapping[str, str]
    signed_by: str  # codebook path + sha256 of the release holding the cells
    auto_keys: frozenset[str] = frozenset()  # keys for automatically typed pages (not answer codes)
    missing_keys: frozenset[str] = frozenset()  # source_type missing tokens with a cell


def signed_credibility_map(cb: Codebook | None = None) -> CredibilityMap:
    """The X22 cells: ``items/core.source_credibility/credibility_map`` of the signed r15 release.

    RC-D-025 C5 (PI 2026-11-10 "vendor medium, academic high, social media low,
    other medium, archive medium, 5f low"; the five integrator-drafted cells are
    covered by the r14 signature). Includes the automatic keys
    (``auto_keys``: ``official_domain``, ``archive_address``) and the missing
    keys (``missing_keys``: ``not_documented``, ``unknown``, and from r15
    ``not_asked``, RC-D-026 10 a).
    """
    cb = cb or default_codebook()
    if cb.sha256 != SIGNED_CODEBOOK_SHA256:
        raise ValueError(f"codebook sha256 {cb.sha256} is not the pinned signed release")
    block = cb.items[CREDIBILITY].get("credibility_map")
    cells = block.get("map") if isinstance(block, Mapping) else None
    if not isinstance(cells, Mapping) or not cells:
        raise ValueError(f"signed codebook has no items/{CREDIBILITY}/credibility_map/map")
    auto = frozenset(str(k) for k in (block.get("auto_keys") or {}))
    missing = frozenset(str(k) for k in (block.get("missing_keys") or ()))
    if auto != {AUTO_OFFICIAL, AUTO_ARCHIVE}:
        raise ValueError(f"credibility_map auto_keys {sorted(auto)} are not the source_type rules/0 bases")
    codes = set(cb.codes(SOURCE_TYPE) or ())
    expected = codes | auto | missing
    if set(cells) != expected:
        raise ValueError(f"credibility_map keys {sorted(cells)} != source_type codes + auto + missing keys")
    return CredibilityMap({str(k): str(v) for k, v in cells.items()},
                          f"codebook {cb.sha256} items/{CREDIBILITY}/credibility_map", auto, missing)


def _low(v: SourceVocab) -> str:
    """The `low` both signed rules name (X22 date clause; confidence.rule)."""
    if "low" not in v.credibility_values:
        raise ValueError("the signed credibility values do not include `low`")
    return "low"


#: Publication-date values that make credibility `low` (rules/0, C6 a: "unknown or not_documented").
LOW_DATE_VALUES = ("unknown", "not_documented")


def source_credibility(typing: SourceTyping, date: FieldValue, credibility_map: CredibilityMap | None = None, *,
                       vocab: SourceVocab | None = None) -> FieldValue:
    """Fixed map from source_type, plus ``low`` when the publication date is ``unknown`` or ``not_documented``.

    Order: (1) date ``unknown`` / ``not_documented`` -> ``low`` whatever the
    cell (rules/0, RC-D-025 C6 a); (2) automatically typed page -> its auto
    key's cell; (3) otherwise the cell of the ``source_type`` value, a missing
    value (``not_documented`` / ``unknown``) taking its missing-key cell
    ``low`` (5f). A ``source_type`` of ``not_asked`` that was not typed
    automatically (R-015 readability failure) takes the r15 missing-key cell
    ``not_asked`` -> ``low`` (RC-D-026 10 a).
    """
    v = vocab or default_vocab()
    if date.item_id != DATE:
        raise ValueError("source_credibility needs the core.source_publication_date value")
    if credibility_map is None:
        credibility_map = signed_credibility_map()
    low = _low(v)
    if date.value in LOW_DATE_VALUES:
        return _fv(CREDIBILITY, low, f"items/core.source_credibility/rules/0: publication date {date.value}", v)
    if date.value in v.missing:
        raise UnruledError(CREDIBILITY, f"publication date {date.value!r}: rules/0 names only unknown and "
                                        "not_documented")
    key = typing.typed_by if typing.typed_by in credibility_map.auto_keys else typing.field.value
    if key not in credibility_map.cells:
        raise UnruledError(CREDIBILITY, f"no signed map cell for source_type {key!r} (typed by "
                                        f"{typing.typed_by}); the signed missing keys are "
                                        f"{sorted(credibility_map.missing_keys)}")
    value = credibility_map.cells[key]
    if value not in v.credibility_values:
        raise ValueError(f"credibility map cell {value!r} is not one of {v.credibility_values}")
    return _fv(CREDIBILITY, value, f"map cell {key!r} ({credibility_map.signed_by})", v)


# ---------------------------------------------------------------------------
# X23 / r2#27: source confidence (PI 2026-11-07)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PendingCheck:
    """An applicable support check of the evidence claim that has not completed."""

    item_id: str
    value: str
    reason: str


@dataclass(frozen=True)
class SourceConfidence:
    source_id: str
    value: str  # high / medium / low / unknown, or UNFINISHED (never a stored grade)
    basis: str
    failures: tuple[str, ...] = ()
    pending: tuple[str, ...] = ()

    @property
    def finished(self) -> bool:
        return self.value != UNFINISHED


def _substantive(rec: SupportResult, v: SourceVocab) -> bool:
    """A positive original code (used only to sanity-check ``not_required``)."""
    value = rec.original_value  # the ORIGINAL code, never the final (downgraded) value
    if value in v.not_required_values or value in v.rule_values:
        return False
    return not (rec.item_id == PAGE_VERDICT and value in v.negative_verdicts)


def source_confidence_rule(source_id: str, credibility: str | None,
                           records: Sequence[SupportResult | PendingCheck], *,
                           vocab: SourceVocab | None = None) -> SourceConfidence:
    """Source confidence, ``items/core.confidence/rules/1`` of r14 (``CONFIDENCE_DECISION``).

    The only place it is applied.

    Scope: one source's evidence claim. ``records`` are that claim's associated
    support records as T-024 produced them (the ORIGINAL code and its status),
    plus any applicable check not yet run. Which records are associated is the
    caller's (T-026) choice (RC-D-025 P12); this function scores what it is given.
    A claim with no records is refused (P11).

    1. Any ``downgraded_no_quote`` / ``downgraded_quote_not_stating_value`` /
       ``downgraded_low_confidence`` (main status or second reason) on ANY
       associated original code -> ``low``, "including a `no` or negative value
       downgraded below the 0.8 bar" (C7 a). A final ``unknown`` does not erase
       it ("Original failures survive the final-value downgrade"). A failure
       with checks still pending is ``low`` too (P10).
    2. Otherwise any pending/unperformed check -> ``unfinished``: not scored.
    3. Otherwise, credibility unavailable (None or ``unknown``) -> ``unknown``
       ("unavailable credibility stays unknown unless a failed check sets low").
    4. Otherwise (all applicable checks completed, none failed; ``not_required``
       and ``set_by_rule`` neutral) -> the credibility (high/medium/low).
    """
    v = vocab or default_vocab()
    if not records:
        raise ValueError(f"{source_id}: an evidence claim with no support records cannot be scored (P11)")
    if credibility is not None and credibility != "unknown" and credibility not in v.credibility_values:
        raise ValueError(f"{source_id}: credibility {credibility!r} is not a signed value")
    failures: list[str] = []
    pending: list[str] = []
    for rec in records:
        if isinstance(rec, PendingCheck):
            pending.append(f"{rec.item_id}={rec.value} ({rec.reason})")
            continue
        status = rec.support_status
        if status not in v.support_statuses:
            raise ValueError(f"{rec.item_id}: support status {status!r} is not signed")
        reasons = [s for s in (status, rec.support_status_second_reason) if s in v.downgrades]
        if reasons:
            failures.append(f"{rec.item_id}={rec.original_value} {reasons[0]}")
        elif status == "not_required" and _substantive(rec, v):
            raise ValueError(f"{rec.item_id}={rec.original_value!r}: not_required on a substantive code")
        elif status == SET_BY_RULE and not (rec.support_rule_name or "").strip():
            raise ValueError(f"{rec.item_id}: set_by_rule without a rule name")
    low = _low(v)
    if failures:
        basis = "rules/1: failed check on an associated original code (C7 a)"
        if pending:
            basis += "; checks pending (P10)"
        return SourceConfidence(source_id, low, basis, tuple(failures), tuple(pending))
    if pending:
        return SourceConfidence(source_id, UNFINISHED, "rules/1: checks pending, not scored", (), tuple(pending))
    if credibility is None or credibility == "unknown":
        return SourceConfidence(source_id, "unknown", "rules/1: credibility unavailable")
    return SourceConfidence(source_id, credibility, "rules/1: all checks completed, none failed")


def confidence_field(conf: SourceConfidence, *, vocab: SourceVocab | None = None) -> FieldValue:
    """The stored ``core.confidence`` value of the source row; an unfinished one is refused."""
    v = vocab or default_vocab()
    if not conf.finished:
        raise UnfinishedConfidenceError([conf.source_id])
    return _fv(CONFIDENCE, conf.value, conf.basis + "; " + CONFIDENCE_DECISION, v,
               detail={"failures": conf.failures})


def confidence_seam(results: Sequence[SourceConfidence]) -> dict[str, str]:
    """``{source_id: confidence}`` for ``stage6_adapters.source_confidence`` (T-028).

    Values are the stored source grades: ``high`` / ``medium`` / ``low`` /
    ``unknown``. An ``unknown`` is passed on as ``unknown`` (it is the stored
    source value); counting it as ``low`` in activity aggregation is
    consolidation's step (C8 b), see :func:`aggregation_value`. Unfinished
    sources are refused, never passed on as a grade.
    """
    unfinished = [r.source_id for r in results if not r.finished]
    if unfinished:
        raise UnfinishedConfidenceError(unfinished)
    out: dict[str, str] = {}
    for r in results:
        if r.source_id in out:
            raise ValueError(f"duplicate source id {r.source_id}")
        out[r.source_id] = r.value
    return out


def aggregation_value(conf: SourceConfidence | str, *, vocab: SourceVocab | None = None) -> str:
    """The value a source confidence counts as when T-026 aggregates an activity (C8 b).

    ``items/core.confidence/rules/2`` (r14, RC-D-025 C8 b): "At consolidation,
    when an activity's confidence is aggregated from its sources, a source whose
    confidence is `unknown` counts as `low`." The codes are read from that slot
    (``vocab.aggregation_map``). Other grades pass through unchanged. This is a
    helper for the consolidation library (``g3o/common/consolidate_v27.py``,
    T-026), which owns aggregation; this module does not aggregate. Unfinished
    confidence is refused.
    """
    v = vocab or default_vocab()
    if isinstance(conf, SourceConfidence):
        if not conf.finished:
            raise UnfinishedConfidenceError([conf.source_id])
        value = conf.value
    else:
        value = conf
    if value == UNFINISHED:
        raise UnfinishedConfidenceError(["<value>"])
    if value not in (*v.credibility_values, *v.aggregation_map):
        raise ValueError(f"source confidence {value!r} is not a stored source grade")
    return v.aggregation_map.get(value, value)


# ---------------------------------------------------------------------------
# One source row
# ---------------------------------------------------------------------------


def source_values(fields: Sequence[FieldValue], *, vocab: SourceVocab | None = None) -> dict[str, str]:
    """``{item_id: value}`` for a ``sources[<id>].values`` mapping (T-028 envelope)."""
    v = vocab or default_vocab()
    out: dict[str, str] = {}
    for f in fields:
        if f.item_id not in v.source_items:
            raise ValueError(f"{f.item_id} is not a source-level item")
        if f.item_id in out:
            raise ValueError(f"{f.item_id} coded twice")
        out[f.item_id] = f.value
    return out


def missing_source_items(fields: Sequence[FieldValue], *, vocab: SourceVocab | None = None) -> list[str]:
    """Source-level items with no coded value yet, named as T-028 names them."""
    v = vocab or default_vocab()
    have = {f.item_id for f in fields}
    return [f"{i} ({v.coder(i)})" for i in v.source_items if i not in have]


__all__ = [
    "AGGREGATION_ROLE", "CONFIDENCE_DECISION", "LOW_DATE_VALUES", "UNFINISHED", "CredibilityMap", "FieldValue", "MetadataDate", "MissingUpstreamError",
    "OfficialSiteOverlay", "PendingCheck", "SourceConfidence", "SourceTyping", "SourceVocab",
    "UnfinishedConfidenceError", "UnruledError", "aggregation_value", "auto_source_type", "code_source_type", "confidence_field",
    "confidence_seam", "date_upper_bound", "default_vocab", "discovery_path", "missing_source_items",
    "page_review_state", "publication_date", "residual_question_set", "route_source_type", "signed_credibility_map",
    "source_access_date", "source_confidence_rule", "source_credibility", "source_language",
    "source_on_official_domain", "source_snippet", "source_title", "source_type_evidence", "source_type_label",
    "source_url", "source_values", "syndication_group", "text_source", "vocab_from_codebook",
]
