"""Provider adapters behind :class:`~g3o.run.presweep.stage_perpage_v27.PerPageProviders` (T-030).

:func:`build_perpage_providers` composes the four per-page seams from the
existing builders around two INJECTED calls; this module creates no client and
makes no call of its own:

- ``extract_fn(job) -> ExtractorResult`` - the C-001 extractor call for a
  T-022 pass-1 job (:meth:`BoundRuntime.pass1_job`) or a T-032 pass-2 job
  (:meth:`BoundRuntime.pass2_job`). Tests pass fakes.
- ``entail_fn(question, text) -> Entailment`` - the X35 call. Its question is
  :func:`~g3o.common.support_check.entailment_question` and its text the
  RC-D-019 E3 window (:func:`~g3o.common.support_check.entailment_window`) on
  the text the quote is matched against. The only non-fake entry today is
  :func:`~g3o.common.support_check.run_entailment`, which still refuses with
  :class:`~g3o.common.support_check.SupportGateError` (a per-page stage stop).

The seams:

- ``page_support`` - T-022 pass 1 for the page codes asked to be checked:
  :func:`~g3o.classify.jev_page_code.to_pass1_page` (codes limited to those
  records), :func:`~g3o.extract.request_v27.select_requests`,
  ``pass1_job``, :func:`~g3o.extract.parser_v27.parse_pass1_result`,
  :func:`~g3o.common.support_check.pass1_quotes`, X35 where T-024 needs it, and
  :func:`~g3o.common.support_check.check_code`. The first call for a page asks
  every pass-1 code: that is T-022's one page request, whose activity spans
  ``activity_input`` uses. A later call (an RC-D-024 extra round) asks only the
  new codes, with the plan ``select_requests`` builds for them (unchanged: on
  an R-003 page it asks spans again; they are not used).
- ``activity_input`` - the spans of that page request. On resume (the page
  checkpoint holds the support, so ``page_support`` is not called again) the
  page request is rebuilt from the stored T-021 artifact; the per-page journal
  replays its response.
- ``activity_support`` / ``pair_support`` - T-032 pass 2:
  :func:`~g3o.classify.jev_activity_code.to_pass2_page`,
  :func:`~g3o.extract.pass2_support.select_requests`, ``pass2_job``,
  :func:`~g3o.extract.pass2_support.parse_pass2_result`, X35, ``check_code``.
  The first activity call sends every pass-2 code of the page, pair codes
  included (DP-009: one request per page); the pair quotes are kept for
  ``pair_support``, which on resume rebuilds that request from the stored T-023
  artifact (journal replay).

Failure semantics are the builders' own. A quote task with no usable quote
(missing, empty, wrong part) is a record with no quote, so T-024 downgrades it
(``downgraded_no_quote``) exactly as a fake that withholds a quote; a quote
over the 200-character cap is kept whole and flagged by T-024. A failed
extractor response (``success`` false, or no text) or an unparsable one (the
parser's :class:`~g3o.extract.parser_v27.ExtractContractError`) raises
:class:`~g3o.run.presweep.stage_perpage_v27.ExtractorResponseFailed` (C3 a, QA4
M3): the per-page stage holds that institution as pending and goes on. The
journal keeps a failed result (``extract_failed``) and rejects an unparsable one
(``extract_rejected``) for accounting only, so the next run asks it again. An
exception raised by the injected call itself is not a response and still leaves
the stage.

Binding (QA3 F3). The adapter declares the extractor model and the X35 model it
runs on; both must equal the instrument's ``extractor_configuration``
(``model``, ``x35_model``; RC-D-033 C1 a) and the bound runtime's settings, and
the pass-1/pass-2 system prompts must hash to the instrument's
``prompt_hashes`` and to the PI-approved pins :data:`PASS1_SYSTEM_SHA256` /
:data:`PASS2_SYSTEM_SHA256` (RC-D-021 P-1 a, P-2 a); any other text is refused,
as the Stage 6 quote step refuses unapproved wording (RC-D-029 Q3 a). :func:`~g3o.run.presweep.stage_perpage_v27.run_perpage_v27`
refuses providers not bound to its instrument, and per institution wraps both
calls in its request journal (:meth:`ExtractorPerPageProviders.with_seams`), so
extractor tokens and X35 calls reach ``PerPageMetrics.usage`` and a resumed run
replays recorded responses.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from g3o.classify.jev_activity_code import (
    PAIR_ITEMS,
    ActivityPageInput,
    PageActivityResult,
    to_pass2_page,
)
from g3o.classify.jev_page_code import PageCodeResult, PageInput, to_pass1_page
from g3o.classify.question_rounds import PageRoundResult
from g3o.common import support_check as sc
from g3o.common.artifact_io import read_artifact
from g3o.common.instrument import canonical_json, sha256_text
from g3o.common.jev_record import CoderRecord
from g3o.common.part_combine import NOT_COVERED
from g3o.common.paths import institution_dir
from g3o.common.support_check import CodeEvidence, Entailment, PageSources, SupportResult
from g3o.extract import pass2_support, request_v27
from g3o.extract.anthropic_client import ExtractorJob, ExtractorResult
from g3o.extract.parser_v27 import ExtractContractError, Pass1Extraction, parse_pass1_result
from g3o.run.presweep import stage_activity_code, stage_page_code
from g3o.run.presweep.stage_perpage_v27 import (
    ACTIVITY_DIR,
    ExtractorResponseFailed,
    PerPageProviders,
)

ExtractFn = Callable[[ExtractorJob], ExtractorResult]
EntailFn = Callable[[str, str], Entailment]
ACTIVITY_NAME = "core.activity_name"

#: SHA256 (UTF-8) of the PI-approved pass-1 system prompt,
#: ``request_v27.build_system_prompt()`` (RC-D-021 P-1 a).
PASS1_SYSTEM_SHA256 = "2ce40a562672a2079204bc57047fa52a6604bf5c6fddc4e5e4622d29e5741ab7"
#: SHA256 (UTF-8) of the PI-approved pass-2 system prompt,
#: ``pass2_support.build_system_prompt()`` (RC-D-021 P-2 a).
PASS2_SYSTEM_SHA256 = "fdcd47f2fee649bd82de4a664bd5af4b28c3a73b481a036a50fb52bd1525d044"
_APPROVED = {"pass1": ("P-1", PASS1_SYSTEM_SHA256), "pass2": ("P-2", PASS2_SYSTEM_SHA256)}


def require_approved_system(name: str, system: str) -> None:
    """Refuse a pass-1/pass-2 system prompt whose UTF-8 SHA256 is not the approved pin."""
    row, pinned = _APPROVED[name]
    if not isinstance(system, str) or sha256_text(system) != pinned:
        raise ValueError(f"{name} prompt differs from the PI-approved text (RC-D-021 {row}, SHA256 "
                         f"{pinned}): no extractor call is made with unapproved wording")


def _job_key(job: ExtractorJob) -> str:
    return hashlib.sha256(canonical_json({"custom_id": job.custom_id, "params": job.params})
                          .encode("utf-8")).hexdigest()


class _Adapter:
    """The four seams over one pair of calls. Caches are per institution (see ``with_seams``)."""

    def __init__(self, bound: Any, run_dir: Path, extract_fn: ExtractFn, entail_fn: EntailFn) -> None:
        self.bound, self.run_dir = bound, Path(run_dir)
        self.extract_fn, self.entail_fn = extract_fn, entail_fn
        self.rules = sc.default_rules()
        self._responses: dict[str, ExtractorResult] = {}
        self._page_request: dict[str, Pass1Extraction | None] = {}  # page id -> T-022 page request
        self._pair_quotes: dict[str, dict[tuple[Any, ...], Any]] = {}  # page id -> pair quotes
        #: every parsed extractor answer, in call order (pass-1 links/date and pass-2 fields have
        #: consumers outside the per-page stage; nothing here stores them)
        self.extractions: list[Any] = []

    # --- calls ---------------------------------------------------------------

    def _call(self, job: ExtractorJob) -> ExtractorResult:
        key = _job_key(job)
        if key in self._responses:  # the same request in this process (e.g. a rebuilt page request)
            return self._responses[key]
        result = self.extract_fn(job)
        if result.success:
            self._responses[key] = result
        return result

    def _parsed(self, name: str, job: ExtractorJob, parse: Callable[[ExtractorResult], Any]) -> Any:
        """The parsed answer to ``job``; a failed or unparsable response raises
        :class:`ExtractorResponseFailed` (C3 a), never a bare parser error."""
        result = self._call(job)
        request = {"custom_id": job.custom_id, "params": job.params}
        if not result.success or not result.text:
            self._responses.pop(_job_key(job), None)
            raise ExtractorResponseFailed(name, request, f"response {result.custom_id!r} failed: {result.error}")
        try:
            return parse(result)
        except ExtractContractError as exc:
            self._responses.pop(_job_key(job), None)  # never reused as an answer
            raise ExtractorResponseFailed(name, request, f"ExtractContractError: {exc}") from exc

    def _entailment(self, ev: CodeEvidence, sources: PageSources, activity_name: str | None) -> Entailment | None:
        """X35 only where :func:`check_code` reads it: a labelled item whose value needs a quote and
        whose quote matches the text it may come from (R-042)."""
        if ev.quote is None or not ev.quote.strip() or ev.item_id not in self.rules.entailment_labels:
            return None
        item = self.rules.items[ev.item_id]
        if not sc._needs_quote(ev, item, self.rules):
            return None
        src = sc._quote_source(ev, item, sources)
        if src is None or not sc.match_quote(ev.quote, src).matched:
            return None
        question = sc.entailment_question(ev.item_id, ev.value, part=ev.part, activity_name=activity_name,
                                          rules=self.rules)
        window, _located = sc.entailment_window(ev.quote, src)
        return self.entail_fn(question, window)

    def _check(self, rec: CoderRecord, quote: Any, sources: PageSources, *, activity_id: str | None = None,
               linked: str | None = None, activity_name: str | None = None) -> SupportResult:
        text = quote.quote if quote is not None and quote.quote and quote.quote.strip() else None
        ev = CodeEvidence(rec.item_id, str(rec.chosen_value), rec.chunk_id, part=rec.item_part,
                          probability=rec.chosen_answer_probability, quote=text,
                          quote_chunk_id=quote.chunk_id if text is not None else None,
                          activity_id=activity_id, linked_activity=linked)
        ent = self._entailment(ev, sources, activity_name)
        return sc.check_code(replace(ev, entailment=ent) if ent is not None else ev, sources, self.rules)

    # --- pass 1 --------------------------------------------------------------

    def _pass1(self, p1: Any) -> tuple[Any, Pass1Extraction | None]:
        plan = request_v27.select_requests(p1)
        if not plan.needs_request:
            return plan, None
        ext = self._parsed("pass1", self.bound.pass1_job(p1, plan), lambda r: parse_pass1_result(r, p1, plan))
        self.extractions.append(ext)
        return plan, ext

    def page_support(self, page: PageInput, result: PageCodeResult,
                     records: Sequence[CoderRecord]) -> list[SupportResult]:
        full = to_pass1_page(result, page)
        wanted = {(r.item_id, r.chunk_id, r.chosen_value) for r in records}
        codes = tuple(c for c in full.codes if (c.item_id, c.chunk_id, c.value) in wanted)
        p1 = replace(full, codes=codes)
        plan, ext = self._pass1(p1)
        if codes == full.codes:  # every pass-1 code: T-022's page request (its spans feed activity_input)
            self._page_request.setdefault(page.page_id, ext)
        quotes = sc.pass1_quotes(plan, ext) if ext is not None else {}
        sources = PageSources.from_page(p1)
        return [self._check(r, quotes.get((r.item_id, r.chunk_id)), sources) for r in records]

    def activity_input(self, page: PageInput, page_round: PageRoundResult) -> ActivityPageInput | None:
        if page.page_id not in self._page_request:  # resume: rebuild the page request from T-021
            first = PageCodeResult.from_json(read_artifact(stage_page_code.artifact_path(
                self.run_dir, page.institution_id, page.url)))
            self._page_request[page.page_id] = self._pass1(to_pass1_page(first, page))[1]
        ext = self._page_request[page.page_id]
        if ext is None or not ext.activities:
            return None
        return ActivityPageInput(to_pass1_page(page_round.result, page), page.country,
                                 page.level_of_government, ext.activities)

    # --- pass 2 --------------------------------------------------------------

    @staticmethod
    def _code_key(aid: str, code: Any) -> tuple[Any, ...]:
        return (aid, code.item_id, code.part, code.chunk_id, code.value, code.linked_activity)

    def _pass2(self, p2: Any) -> dict[tuple[Any, ...], Any]:
        plan = pass2_support.select_requests(p2)
        if not plan.needs_request:
            return {}
        sup = self._parsed("pass2", self.bound.pass2_job(p2, plan),
                           lambda r: pass2_support.parse_pass2_result(r, p2, plan))
        self.extractions.append(sup)
        tasks = {t.task_id: t for t in plan.quote_tasks}
        out: dict[tuple[Any, ...], Any] = {}
        for q in sup.quotes:
            t = tasks[q.task_id]
            out[(t.activity_id, t.item_id, t.part, t.chunk_id, t.answer, t.linked_activity)] = q
        return out

    @staticmethod
    def _names(inp: ActivityPageInput) -> dict[str, str]:
        return {sp.activity_id: f.value for sp in inp.spans for f in sp.fields if f.item_id == ACTIVITY_NAME}

    def activity_support(self, inp: ActivityPageInput, result: PageActivityResult,
                         records: Sequence[tuple[str, CoderRecord]]) -> list[SupportResult]:
        full = to_pass2_page(result, inp)
        wanted = {(a, r.item_id, r.item_part, r.chunk_id, str(r.chosen_value), None) for a, r in records}
        ordinary = {self._code_key(a.activity_id, c) for a in full.activities for c in a.codes
                    if c.item_id not in PAIR_ITEMS}
        if wanted == ordinary and inp.page.page_id not in self._pair_quotes:
            # every ordinary code: the page request, pair codes included (DP-009)
            quotes = self._pass2(full)
            self._pair_quotes[inp.page.page_id] = {k: q for k, q in quotes.items() if k[1] in PAIR_ITEMS}
        else:
            acts = tuple(replace(a, codes=tuple(c for c in a.codes if self._code_key(a.activity_id, c) in wanted))
                         for a in full.activities)
            quotes = self._pass2(replace(full, activities=acts))
        sources = PageSources.from_page(inp.page)
        names = self._names(inp)
        return [self._check(r, quotes.get((a, r.item_id, r.item_part, r.chunk_id, str(r.chosen_value), None)),
                            sources, activity_id=a, activity_name=names.get(a)) for a, r in records]

    def pair_support(self, inp: ActivityPageInput, result: PageActivityResult) -> list[SupportResult]:
        pid = inp.page.page_id
        if pid not in self._pair_quotes:  # resume: rebuild the page request from the T-023 artifact
            art = stage_activity_code.artifact_path(
                institution_dir(self.run_dir, inp.page.institution_id) / ACTIVITY_DIR, pid)
            first = PageActivityResult.from_json(read_artifact(art))
            self._pair_quotes[pid] = {k: q for k, q in self._pass2(to_pass2_page(first, inp)).items()
                                      if k[1] in PAIR_ITEMS}
        quotes = self._pair_quotes[pid]
        sources = PageSources.from_page(inp.page)
        names = self._names(inp)
        out = []
        for pair in result.pairs:
            for rec in pair.records:
                if rec.chosen_value == NOT_COVERED:
                    continue
                key = (pair.activity_id, rec.item_id, rec.item_part, rec.chunk_id, str(rec.chosen_value),
                       pair.linked_activity)
                # the X35 activity form names the activity the pair code belongs to (its lhs)
                out.append(self._check(rec, quotes.get(key), sources, activity_id=pair.activity_id,
                                       linked=pair.linked_activity, activity_name=names.get(pair.activity_id)))
        return out


@dataclass(frozen=True)
class ExtractorPerPageProviders(PerPageProviders):
    """:class:`PerPageProviders` bound to one instrument, its extractor model and its X35 model."""

    bound_instrument_id: str = ""
    extractor_model: str = ""
    x35_model: str = ""
    adapter: Any = None

    @property
    def journal_prompt(self) -> dict[str, Any]:
        """Extra journal key of the extractor and X35 calls (a response under other models is not replayed)."""
        return {"extractor_model": self.extractor_model, "x35_model": self.x35_model,
                "pass1_prompt_version": request_v27.PROMPT_VERSION,
                "pass2_prompt_version": pass2_support.PROMPT_VERSION}

    def with_seams(self, wrap_extract: Callable[[ExtractFn], ExtractFn],
                   wrap_entail: Callable[[EntailFn], EntailFn]) -> ExtractorPerPageProviders:
        """The same providers with both calls wrapped (the per-institution request journal) and fresh caches."""
        a = self.adapter
        return _providers(_Adapter(a.bound, a.run_dir, wrap_extract(a.extract_fn), wrap_entail(a.entail_fn)),
                          self.bound_instrument_id, self.extractor_model, self.x35_model)


def _providers(adapter: _Adapter, instrument_id: str, extractor_model: str,
               x35_model: str) -> ExtractorPerPageProviders:
    return ExtractorPerPageProviders(adapter.page_support, adapter.activity_input, adapter.activity_support,
                                     adapter.pair_support, instrument_id, extractor_model, x35_model, adapter)


def check_binding(bound: Any, instrument: Mapping[str, Any], *, extractor_model: str,
                  x35_model: str) -> None:
    """Refuse a per-page binding :func:`build_perpage_providers` would refuse; builds nothing.

    ``extractor_model`` and ``x35_model`` must equal the instrument's pinned
    ``extractor_configuration`` and the bound settings; the pass-1/pass-2 system
    prompts must hash to the PI-approved pins (RC-D-021 P-1 a, P-2 a) and to the
    instrument's ``prompt_hashes``. Needs no run directory, so a run can call it on
    :func:`~g3o.run.presweep.instrument_binding.check_runtime`'s record before any
    work (T-030 QA4 M2); :func:`build_perpage_providers` calls it again.
    """
    if instrument.get("instrument_id") != bound.instrument_id:
        raise ValueError("bound runtime and instrument differ")
    payload = instrument["payload"]
    cfg = payload["extractor_configuration"]
    for name, declared, pinned, setting in (
            ("extractor_model", extractor_model, cfg.get("model"), bound.settings.extractor_model),
            ("x35_model", x35_model, cfg.get("x35_model"), bound.settings.x35_model)):
        if not isinstance(declared, str) or not declared.strip():
            raise ValueError(f"{name} must be explicitly supplied")
        if declared != pinned or declared != setting:
            raise ValueError(f"{name} differs from the one pinned in the instrument")
    hashes = payload.get("prompt_hashes", {})
    for name, system in (("pass1", bound.pass1_system), ("pass2", bound.pass2_system)):
        require_approved_system(name, system)
        if not system or sha256_text(system) != hashes.get(name):
            raise ValueError(f"{name} prompt differs from the one pinned in the instrument")


def build_perpage_providers(bound: Any, instrument: Mapping[str, Any], run_dir: Path, *,
                            extract_fn: ExtractFn, entail_fn: EntailFn, extractor_model: str,
                            x35_model: str) -> ExtractorPerPageProviders:
    """Per-page providers over the injected ``extract_fn`` / ``entail_fn``, bound to ``instrument``.

    Every argument is required; nothing defaults to a client. ``extractor_model`` and
    ``x35_model`` name the models the two calls run on and must equal the instrument's
    pinned ``extractor_configuration`` (and the bound settings); any other is refused, as
    are system prompts that differ from the instrument's ``prompt_hashes`` or from the
    PI-approved pins (RC-D-021 P-1 a, P-2 a). See :func:`check_binding`.
    """
    if not callable(extract_fn) or not callable(entail_fn):
        raise ValueError("extract_fn and entail_fn must be supplied")
    check_binding(bound, instrument, extractor_model=extractor_model, x35_model=x35_model)
    return _providers(_Adapter(bound, run_dir, extract_fn, entail_fn), bound.instrument_id, extractor_model,
                      x35_model)


__all__ = ["PASS1_SYSTEM_SHA256", "PASS2_SYSTEM_SHA256", "ExtractorPerPageProviders",
           "build_perpage_providers", "check_binding", "require_approved_system"]
