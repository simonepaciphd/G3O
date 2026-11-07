"""jev pass-1 page coder (T-021). Pure: the jev call is injected; no I/O.

One page, chunked into parts (T-020 ``page_chunks``), is coded with the v2.7
page question set (T-011) in round and gate order (R-008):

1. **Readability.** A page whose stored text fails the R-015 readability check
   (``g3o.scrape.readability``) is not sent: its verdict is ``not_assessable``,
   set by rule ``readability_failure:<reason>`` (C1 a; RC-D-021 D-1 a), and every
   other page item gets its gated-out value (closed gate) or ``not_asked``.
2. **Part layout (PI Q6).** Measured once against the largest request of any
   round, with the part extras (part sentence, temporary answers) counted, by
   ``prepare_page_requests``. A part jev rejects as over-limit
   (``max_tokens_exceeded``) in any round is halved, and the earlier rounds are
   re-asked on the halves; other parts keep their answers. The halved part's
   records are kept as ``superseded`` (they were billed).
3. **Rounds.** Each round's questions go to every part; a question whose gate is
   closed on the combined answers of earlier rounds is not asked and gets its
   signed ``gated_out_value`` (else ``not_asked``), set by rule
   ``gated_out:<gate item>``. After each round, part answers are combined by the
   item's codebook rule (:mod:`g3o.common.part_combine`), on the 0.8 bar only:
   the support check runs once after pass 1 (RC-D-021 D-3 a). This is the
   *provisional* combination; :func:`finalize_page` re-combines with the support
   results and re-applies the gates (PI Q2 b).
4. **Records.** Every jev answer is a T-027 :class:`CoderRecord` (probability
   distribution, confidence, configured and response model, request id, chunk
   id, signed downgrade rule: the 0.8 threshold flags). Set-by-rule values are
   mechanical records with typed-null provider fields.

Ruled specifics:
- ``core.source_type`` is not asked here (T-015 asks it; RC-D-002 O2, PI
  2026-11-08 Q3 a). The approved page set omits it.
- The two contact items read main + chrome text (codebook ``main_plus_chrome``,
  r2#48; PI Q4 b). jev shares one state across a request's questions, so they go
  in their own request per part whose state adds the chrome text under
  :data:`CHROME_STATE_FIELD` (PI 2026-11-07 item 1a). When the
  page's chrome was not measured or is empty, they join the main request
  (``chrome_status`` says which).
- A part request with no request id is a failed part request
  (``jev_missing_request_id``; PI Q5); no placeholder id is ever recorded.
- A failed part request enters combining as a failed answer (``unknown``,
  all-03 a). Failed verdict requests have no vote: successful parts combine.
  At least 75% failed verdict parts, counted on the current leaf layout, fail
  the page (PI 2026-11-07 item 5). Low-confidence answers remain tag-only votes.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from g3o.classify.questions.v27 import choice_request, load_set
from g3o.codebook.loader import Codebook, load_codebook
from g3o.common import part_combine as pc
from g3o.common.jev_client import JevAccountError, JevResult
from g3o.common.jev_record import ClassifierRule, CoderRecord
from g3o.common.page_chunks import (
    DEFAULT_MAX_SPLIT_DEPTH,
    JEV_STATE_TOKEN_LIMIT,
    Chunk,
    TokenEstimator,
    halve_chunk,
    prepare_page_requests,
)
from g3o.scrape.readability import readability_failure
from g3o.validate.jev_validate import is_max_tokens_exceeded

CODER_VERSION = "g3o.classify.jev_page_code.v1"
VERDICT = "core.page_verdict"
COMPLETE = "core.page_complete"

#: Questions of the page set this stage does not ask, with the reason.
SKIPPED_QUESTIONS: Mapping[str, str] = {}

#: PI 2026-11-07 item 1a: stored chrome verbatim, followed by stored email links.
CHROME_STATE_FIELD = "chrome_text"
CHROME_INPUT = "main_plus_chrome"
GROUP_MAIN = "main"
GROUP_CHROME = "chrome"

READABILITY_RULE = "readability_failure:"
GATE_RULE = "gated_out:"

MISSING_REQUEST_ID = "jev_missing_request_id"
REQUEST_FAILED = "jev_request_failed"
ANSWER_MISSING = "jev_answer_missing"
OVER_LIMIT = "jev_part_over_limit"

AskFn = Callable[[dict[str, Any], dict[str, dict[str, Any]]], JevResult]


# ---------------------------------------------------------------------------
# Inputs and configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PageInput:
    page_id: str
    institution_id: str
    institution: str
    country: str | None
    level_of_government: str | None
    url: str
    title: str | None
    text: str
    chrome_text: str | None = None  # T-014 RenderedPage.chrome_text; None = not measured
    links: tuple[dict[str, Any], ...] | None = None  # passed to T-022 unchanged
    has_metadata_date: bool = False  # passed to T-022 unchanged
    email_links: tuple[str, ...] | None = None  # T-014 addresses, already normalized


@dataclass(frozen=True)
class PageCoderConfig:
    """Run binding (T-030/T-035 supply the real values; tests use fixtures)."""

    rules: Mapping[tuple[str, str | None], ClassifierRule]  # jev_record.load_classifier_rules
    setup_pointer: str  # instrument payload SHA256
    configured_model: str
    reserved_tokens: int  # explicit known overhead absent from the payload (0 must be explicit)
    coder_version: str = CODER_VERSION
    limit_tokens: int = JEV_STATE_TOKEN_LIMIT
    max_split_depth: int = DEFAULT_MAX_SPLIT_DEPTH
    estimator: TokenEstimator = field(default_factory=TokenEstimator)
    question_set: Mapping[str, Any] | None = None  # default: load_set("page")
    codebook: Codebook | None = None  # default: load_codebook()


@dataclass(frozen=True)
class _Setup:
    qset: Mapping[str, Any]
    questions: tuple[dict[str, Any], ...]  # asked questions, set order
    by_id: Mapping[str, dict[str, Any]]
    rounds: tuple[int, ...]
    chrome_ids: frozenset[str]
    combine_rules: Mapping[str, pc.ItemRule]


def _setup(config: PageCoderConfig) -> _Setup:
    qset = config.question_set if config.question_set is not None else load_set("page")
    cb = config.codebook if config.codebook is not None else load_codebook()
    if qset["codebook_sha256"] != cb.sha256:
        raise ValueError("question set and codebook differ")
    qs = tuple(q for q in qset["questions"] if q["question_id"] not in SKIPPED_QUESTIONS)
    by_id = {q["question_id"]: q for q in qs}
    for q in qs:
        gate = q.get("gate")
        if isinstance(gate, Mapping):
            g = by_id.get(gate["item"])
            if g is None or g["round"] >= q["round"]:
                raise ValueError(f"{q['question_id']}: gate {gate['item']} is not asked in an earlier round")
        if (q["item_id"], None) not in config.rules:
            raise ValueError(f"{q['item_id']}: no signed classifier rule")
    rules = pc.rules_from_codebook(cb)
    missing = [q["item_id"] for q in qs if q["item_id"] not in rules]
    if missing:
        raise ValueError(f"no long_page_rule for {missing}")
    chrome = frozenset(q["question_id"] for q in qs if cb.items[q["item_id"]].get("input_text") == CHROME_INPUT)
    return _Setup(qset, qs, by_id, tuple(sorted({q["round"] for q in qs})), chrome,
                  {q["item_id"]: rules[q["item_id"]] for q in qs})


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------


def build_state(page: PageInput, chunk: Chunk, index: int, n_parts: int, qset: Mapping[str, Any],
                *, chrome: bool) -> dict[str, Any]:
    """The approved W-01 / W-02 state; the chrome field only for the chrome request."""
    state: dict[str, Any] = {
        "coder_instructions": qset["system_prompt"],
        "institution": page.institution,
        "country": page.country,
        "level_of_government": page.level_of_government,
        "page_url": page.url,
        "page_title": page.title,
        "page_part": f"{index} of {n_parts}",
    }
    if n_parts > 1:
        state["part_note"] = qset["part_prompt"]["sentence"]
    state["page_text"] = chunk.text
    if chrome:
        state[CHROME_STATE_FIELD] = contact_text(page)
    return state


def build_questions(questions: Sequence[dict[str, Any]], *, part: bool) -> dict[str, dict[str, Any]]:
    """``{question_id: {instructions, criteria}}`` (jev Choice fields)."""
    return {q["question_id"]: choice_request(q, part=part) for q in questions}


def serialize_request(state: Mapping[str, Any], questions: Mapping[str, Any]) -> str:
    return json.dumps({"state": state, "questions": questions}, ensure_ascii=False)


def contact_text(page: PageInput) -> str | None:
    """Preserve stored chrome exactly; append T-014 addresses in their stored order."""
    if page.chrome_text is None:
        return None  # pre-T-014 page: omit the field, per the existing ruling
    emails = "\n".join(page.email_links or ())
    return page.chrome_text + ("\n" + emails if emails else "")


def _chrome_sent(page: PageInput) -> bool:
    text = contact_text(page)
    return bool(text and text.strip())


def _groups(questions: Sequence[dict[str, Any]], s: _Setup, page: PageInput) -> list[tuple[str, list[dict[str, Any]]]]:
    if not _chrome_sent(page):
        return [(GROUP_MAIN, list(questions))] if questions else []
    main = [q for q in questions if q["question_id"] not in s.chrome_ids]
    chrome = [q for q in questions if q["question_id"] in s.chrome_ids]
    return [(g, qs) for g, qs in ((GROUP_MAIN, main), (GROUP_CHROME, chrome)) if qs]


def plan_layout(page: PageInput, config: PageCoderConfig, s: _Setup) -> list[Chunk]:
    """Parts measured once against the largest request of any round (PI Q6)."""
    probes = [qs for r in s.rounds for _, qs in _groups([q for q in s.questions if q["round"] == r], s, page)]

    def largest(chunk: Chunk) -> str:
        payloads = [serialize_request(build_state(page, chunk, 999, 999, s.qset, chrome=_chrome_sent(page)
                                                  and any(q["question_id"] in s.chrome_ids for q in qs)),
                                      build_questions(qs, part=True)) for qs in probes]
        return max(payloads, key=config.estimator.tokens)

    prepared = prepare_page_requests(page.page_id, page.text, serialize_request=largest,
                                     estimator=config.estimator, limit_tokens=config.limit_tokens,
                                     reserved_tokens=config.reserved_tokens)
    return [p.chunk for p in prepared]


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemOutcome:
    """The page's answer to one item.

    ``state``: ``combined`` (from the parts), ``gated_out`` / ``set_by_rule``
    (a rule fixed the value; ``rule_reference`` names it) or ``stopped`` (the
    combiner could not place an answer, or its gate item stopped; ``error``).
    ``failed``: the producing part failed its checks (a ``tag_only`` verdict keeps
    its value with this tag; other items then hold ``unknown``).
    """

    item_id: str
    state: str
    value: Any
    failed: bool = False
    cause: str | None = None
    part_id: str | None = None
    probability: float | None = None
    contributors: tuple[str, ...] = ()
    mapped_from: tuple[Any, ...] = ()
    elements: tuple[dict[str, Any], ...] = ()
    note: str | None = None
    rule_reference: str | None = None
    error: str | None = None


def _outcome(c: pc.CombinedAnswer) -> ItemOutcome:
    return ItemOutcome(
        c.item_id, "combined", c.value, c.failed, c.cause, c.part_id, c.probability,
        c.contributors, c.mapped_from,
        tuple({"value": e.value, "part_id": e.part_id, "probability": e.probability} for e in c.elements),
        c.note)


@dataclass(frozen=True)
class PageCodeResult:
    page_id: str
    institution_id: str
    url: str
    status: str  # "coded" | "not_assessable" | "failed"
    chunks: tuple[Chunk, ...]
    records: tuple[CoderRecord, ...]
    items: Mapping[str, ItemOutcome]
    superseded: tuple[CoderRecord, ...] = ()
    requests: tuple[dict[str, Any], ...] = ()
    failures: tuple[dict[str, Any], ...] = ()
    skipped_questions: Mapping[str, str] = field(default_factory=lambda: dict(SKIPPED_QUESTIONS))
    chrome_status: str = "not_measured"
    question_set_version: str = ""
    codebook_sha256: str = ""
    coder_version: str = CODER_VERSION

    @property
    def verdict(self) -> ItemOutcome | None:
        return self.items.get(VERDICT)

    @property
    def page_complete(self) -> ItemOutcome | None:
        return self.items.get(COMPLETE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "g3o-page-code-v1",
            "page_id": self.page_id, "institution_id": self.institution_id, "url": self.url,
            "status": self.status,
            "chunks": [asdict(c) for c in self.chunks],
            "records": [r.to_dict() for r in self.records],
            "superseded": [r.to_dict() for r in self.superseded],
            "items": {k: asdict(v) for k, v in self.items.items()},
            "requests": list(self.requests), "failures": list(self.failures),
            "skipped_questions": dict(self.skipped_questions), "chrome_status": self.chrome_status,
            "question_set_version": self.question_set_version,
            "codebook_sha256": self.codebook_sha256, "coder_version": self.coder_version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, allow_nan=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PageCodeResult:
        if data.get("format") != "g3o-page-code-v1":
            raise ValueError("unsupported page-code artifact format")

        def item(d: Mapping[str, Any]) -> ItemOutcome:
            d = dict(d)
            for k in ("contributors", "mapped_from", "elements"):
                d[k] = tuple(_tuples(x) for x in d[k])
            d["value"] = _tuples(d["value"])
            return ItemOutcome(**d)

        return cls(
            page_id=data["page_id"], institution_id=data["institution_id"], url=data["url"],
            status=data["status"], chunks=tuple(Chunk(**c) for c in data["chunks"]),
            records=tuple(CoderRecord.from_dict(r) for r in data["records"]),
            items={k: item(v) for k, v in data["items"].items()},
            superseded=tuple(CoderRecord.from_dict(r) for r in data["superseded"]),
            requests=tuple(data["requests"]), failures=tuple(data["failures"]),
            skipped_questions=dict(data["skipped_questions"]), chrome_status=data["chrome_status"],
            question_set_version=data["question_set_version"], codebook_sha256=data["codebook_sha256"],
            coder_version=data["coder_version"],
        )

    @classmethod
    def from_json(cls, text: str) -> PageCodeResult:
        return cls.from_dict(json.loads(text))


def _tuples(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(_tuples(x) for x in v)
    return v


# ---------------------------------------------------------------------------
# Coding
# ---------------------------------------------------------------------------


class PageFailed(RuntimeError):
    """The page cannot be coded (no verdict); ``reason`` is the attrition reason."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class _OverLimit(Exception):
    def __init__(self, chunk: Chunk) -> None:
        self.chunk = chunk


def _mechanical(item_id: str, value: Any, rule: str, config: PageCoderConfig, qsv: str) -> CoderRecord:
    return CoderRecord(
        item_id=item_id, item_part=None, question_id=item_id, support_id=None, observation_id=None,
        chunk_id=None, coder_type="mechanical", coder_version=config.coder_version,
        configured_model=None, actual_response_model=None, request_id=None,
        question_set_version=qsv, setup_pointer=config.setup_pointer, answer_type="rule",
        chosen_value=value, confidence=None, probability_distribution=None, rule_reference=rule)


def gated_out_value(question: Mapping[str, Any]) -> str:
    gate = question.get("gate")
    if isinstance(gate, Mapping) and isinstance(gate.get("gated_out_value"), str):
        return gate["gated_out_value"]
    return pc.NOT_ASKED


def gate_open(question: Mapping[str, Any], items: Mapping[str, ItemOutcome]) -> bool | None:
    """True / False, or None when the gate item was stopped."""
    gate = question.get("gate")
    if not isinstance(gate, Mapping):
        return True
    g = items[gate["item"]]
    if g.state in ("stopped", "pending"):
        return None
    return g.value in gate["values"]


def _single_chunk(page: PageInput, est: TokenEstimator) -> Chunk:
    return Chunk(f"{page.page_id}#p001", page.page_id, 0, len(page.text), page.text, est.tokens(page.text))


def code_page(page: PageInput, ask_fn: AskFn, config: PageCoderConfig, *,
              on_response: Callable[[JevResult], None] | None = None) -> PageCodeResult:
    """Code one page (pass 1). Raises :class:`PageFailed` when no verdict can be made.

    ``ask_fn(state, questions)`` sends one jev request (``questions`` as
    ``{id: {instructions, criteria}}``). ``on_response`` sees every response (cost
    meter; it may raise to stop). :class:`JevAccountError` propagates.
    """
    s = _setup(config)
    qsv = s.qset["question_set_version"]
    common = dict(page_id=page.page_id, institution_id=page.institution_id, url=page.url,
                  question_set_version=qsv, codebook_sha256=s.qset["codebook_sha256"],
                  coder_version=config.coder_version)
    chrome_status = ("sent" if _chrome_sent(page) else
                     "not_measured" if page.chrome_text is None else "empty")

    reason = readability_failure(page.text)
    if reason is not None:
        rule = READABILITY_RULE + reason
        items: dict[str, ItemOutcome] = {VERDICT: ItemOutcome(VERDICT, "set_by_rule", "not_assessable",
                                                              rule_reference=rule)}
        records = [_mechanical(VERDICT, "not_assessable", rule, config, qsv)]
        for q in s.questions:
            if q["item_id"] == VERDICT:
                continue
            gated = gate_open(q, items) is False
            v = gated_out_value(q) if gated else pc.NOT_ASKED
            ref = GATE_RULE + q["gate"]["item"] if gated else rule
            items[q["item_id"]] = ItemOutcome(q["item_id"], "gated_out" if gated else "set_by_rule", v,
                                              rule_reference=ref)
            records.append(_mechanical(q["item_id"], v, ref, config, qsv))
        return PageCodeResult(status="not_assessable", chunks=(_single_chunk(page, config.estimator),),
                              records=tuple(records), items=items, chrome_status=chrome_status, **common)

    layout = plan_layout(page, config, s)
    cache: dict[tuple[str, int, str], dict[str, Any]] = {}
    requests: list[dict[str, Any]] = []
    exhausted: set[str] = set()

    def send(chunk: Chunk, index: int, n: int, rnd: int, group: str,
             qs: list[dict[str, Any]]) -> dict[str, Any]:
        qids = tuple(q["question_id"] for q in qs)
        key = (chunk.chunk_id, rnd, group)
        hit = cache.get(key)
        if hit is not None and hit["qids"] == qids:
            return hit
        state = build_state(page, chunk, index, n, s.qset, chrome=group == GROUP_CHROME)
        questions = build_questions(qs, part=n > 1)
        payload = serialize_request(state, questions)
        log = {"chunk_id": chunk.chunk_id, "round": rnd, "group": group, "page_part": state["page_part"],
               "question_ids": list(qids), "estimated_tokens": config.estimator.tokens(payload)}
        if chunk.chunk_id in exhausted:
            entry = {"qids": qids, "records": {}, "failure": {
                "reason": OVER_LIMIT, "detail": "part cannot be halved further"}}
            cache[key] = entry
            requests.append({**log, "outcome": OVER_LIMIT})
            return entry
        if log["estimated_tokens"] > config.limit_tokens - config.reserved_tokens:
            raise _OverLimit(chunk)
        entry: dict[str, Any] = {"qids": qids, "records": {}, "failure": None}
        try:
            result = ask_fn(state, questions)
        except JevAccountError:
            raise
        except Exception as exc:
            if is_max_tokens_exceeded(exc):
                requests.append({**log, "outcome": "over_limit"})
                raise _OverLimit(chunk) from exc
            entry["failure"] = {"reason": REQUEST_FAILED, "detail": f"{type(exc).__name__}: {exc}"}
            requests.append({**log, "outcome": REQUEST_FAILED})
            cache[key] = entry
            return entry
        if on_response is not None:
            on_response(result)
        log.update(response_model=result.response_model, request_id=result.request_id,
                   input_tokens=result.input_tokens, output_tokens=result.output_tokens)
        if not result.request_id:
            entry["failure"] = {"reason": MISSING_REQUEST_ID, "detail": "jev returned no request id"}
            requests.append({**log, "outcome": MISSING_REQUEST_ID})
            cache[key] = entry
            return entry
        requests.append({**log, "outcome": "ok"})
        for q in qs:
            qid = q["question_id"]
            if qid not in result.answers:
                entry["records"][qid] = {"reason": ANSWER_MISSING, "detail": "no answer returned"}
                continue
            entry["records"][qid] = CoderRecord.from_jev(
                result, question_id=qid, item_id=q["item_id"], item_part=None, support_id=None,
                observation_id=None, chunk_id=chunk.chunk_id, coder_version=config.coder_version,
                configured_model=config.configured_model, question_set_version=qsv,
                setup_pointer=config.setup_pointer, classifier_rule=config.rules[(q["item_id"], None)])
        cache[key] = entry
        return entry

    while True:
        try:
            items, part_entries = _rounds(layout, s, page, config, qsv, send)
            break
        except _OverLimit as ol:
            pos = next(i for i, c in enumerate(layout) if c.chunk_id == ol.chunk.chunk_id)
            halves = halve_chunk(ol.chunk, estimator=config.estimator)
            if halves is None or ol.chunk.depth >= config.max_split_depth:
                exhausted.add(ol.chunk.chunk_id)
            else:
                layout[pos:pos + 1] = list(halves)

    live = {c.chunk_id for c in layout}
    records: list[CoderRecord] = []
    superseded: list[CoderRecord] = []
    failures: list[dict[str, Any]] = []
    used = {id(e) for e in part_entries}
    for (cid, rnd, group), entry in cache.items():
        recs = [r for r in entry["records"].values() if isinstance(r, CoderRecord)]
        if cid in live and id(entry) in used:
            records.extend(recs)
            if entry["failure"]:
                failures.append({"chunk_id": cid, "round": rnd, "group": group,
                                 "question_ids": list(entry["qids"]), **entry["failure"]})
            for qid, r in entry["records"].items():
                if not isinstance(r, CoderRecord):
                    failures.append({"chunk_id": cid, "round": rnd, "group": group,
                                     "question_ids": [qid], **r})
        else:
            superseded.extend(recs)
    for it in items.values():
        if it.state in ("gated_out", "set_by_rule"):
            records.append(_mechanical(it.item_id, it.value, it.rule_reference, config, qsv))
    return PageCodeResult(status="coded", chunks=tuple(layout), records=tuple(records), items=items,
                          superseded=tuple(superseded), requests=tuple(requests), failures=tuple(failures),
                          chrome_status=chrome_status, **common)


def _rounds(layout: list[Chunk], s: _Setup, page: PageInput, config: PageCoderConfig, qsv: str,
            send: Callable[..., dict[str, Any]]) -> tuple[dict[str, ItemOutcome], list[dict[str, Any]]]:
    items: dict[str, ItemOutcome] = {}
    used: list[dict[str, Any]] = []
    n = len(layout)
    for rnd in s.rounds:
        asked: list[dict[str, Any]] = []
        for q in (q for q in s.questions if q["round"] == rnd):
            open_ = gate_open(q, items)
            if open_ is None:
                items[q["item_id"]] = ItemOutcome(q["item_id"], "stopped", None,
                                                  error=f"gate item {q['gate']['item']} stopped")
            elif open_:
                asked.append(q)
            else:
                items[q["item_id"]] = ItemOutcome(q["item_id"], "gated_out", gated_out_value(q),
                                                  rule_reference=GATE_RULE + q["gate"]["item"])
        if not asked:
            continue
        answers: dict[str, list[pc.PartAnswer]] = {q["item_id"]: [] for q in asked}
        verdict_failures: list[tuple[str, str]] = []
        for index, chunk in enumerate(layout, start=1):
            for group, qs in _groups(asked, s, page):
                entry = send(chunk, index, n, rnd, group, qs)
                used.append(entry)
                for q in qs:
                    rec = entry["records"].get(q["question_id"])
                    if isinstance(rec, CoderRecord):
                        answers[q["item_id"]].append(part_answer(rec, index))
                        continue
                    cause = (entry["failure"] or rec or {}).get("reason", REQUEST_FAILED)
                    if q["item_id"] == VERDICT:
                        verdict_failures.append((chunk.chunk_id, cause))
                        continue
                    answers[q["item_id"]].append(pc.PartAnswer(chunk.chunk_id, index, pc.UNKNOWN, None,
                                                               failed=True, cause=cause))
        if 4 * len(verdict_failures) >= 3 * n:
            raise PageFailed(verdict_failures[0][1],
                             f"{len(verdict_failures)}/{n} verdict parts failed (at least 75%)")
        for q in asked:
            items[q["item_id"]] = _combine(s.combine_rules[q["item_id"]], answers[q["item_id"]])
    return items, used


def part_answer(rec: CoderRecord, index: int, *, failed: bool | None = None,
                cause: str | None = None) -> pc.PartAnswer:
    """A combiner input from one part's record; ``failed`` defaults to the 0.8-bar check."""
    return pc.PartAnswer(rec.chunk_id, index, rec.chosen_value, rec.chosen_answer_probability,
                         failed=bool(rec.downgraded) if failed is None else failed,
                         cause=(rec.downgrade_cause if cause is None else cause))


def _combine(rule: pc.ItemRule, answers: list[pc.PartAnswer]) -> ItemOutcome:
    try:
        return _outcome(pc.combine(rule, answers))
    except pc.CombineError as exc:
        return ItemOutcome(rule.item_id, "stopped", None, error=str(exc))


# ---------------------------------------------------------------------------
# After the support check (PI Q2 b): re-combine and re-apply the gates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinalPage:
    """Final page items after T-024.

    ``regated``: items asked on the provisional gate whose final gate is closed;
    they take their signed gated-out value and jev's raw answers stay in the
    records, unpublished. ``gate_opened``: items not asked because the provisional
    gate was closed, whose final gate is open. These items are pending the
    extra round required in T-030 (PI 2026-11-07 item 4b), not final negatives.
    """

    items: Mapping[str, ItemOutcome]
    regated: tuple[str, ...] = ()
    gate_opened: tuple[str, ...] = ()


_DOWNGRADED = re.compile(r"^downgraded_")


def finalize_page(result: PageCodeResult, support: Sequence[Any], config: PageCoderConfig) -> FinalPage:
    """Re-combine the provisional page with the T-024 support results, then re-gate.

    ``support`` items carry ``item_id``, ``chunk_id`` and ``support_status``
    (:class:`g3o.common.support_check.SupportResult`). Every jev part code (other
    than the temporary answer) must have one. A part fails when its record failed
    the 0.8 bar or its support status is a ``downgraded_*`` status.
    """
    if result.status != "coded":
        return FinalPage(dict(result.items))
    s = _setup(config)
    status: dict[tuple[str, str], str] = {}
    for sr in support:
        if getattr(sr, "activity_id", None) is not None:
            continue
        status[(sr.item_id, sr.chunk_id)] = sr.support_status
    index = {c.chunk_id: i for i, c in enumerate(result.chunks, start=1)}
    by_item: dict[str, list[CoderRecord]] = {}
    for rec in result.records:
        if rec.coder_type == "classifier":
            by_item.setdefault(rec.item_id, []).append(rec)
    provisional = result.items
    final: dict[str, ItemOutcome] = {}
    regated: list[str] = []
    opened: list[str] = []
    for rnd in s.rounds:
        for q in (q for q in s.questions if q["round"] == rnd):
            iid = q["item_id"]
            prov = provisional[iid]
            open_ = gate_open(q, final)
            gate = q.get("gate")
            if isinstance(gate, Mapping) and final[gate["item"]].state == "pending":
                final[iid] = ItemOutcome(iid, "pending", None,
                                         note="gate awaits extra round after support check")
                continue
            if prov.state != "combined":
                if prov.state == "gated_out" and open_:
                    opened.append(iid)
                    final[iid] = ItemOutcome(iid, "pending", None,
                                             note="requires extra round after support check")
                    continue
                final[iid] = prov
                continue
            if open_ is None:
                final[iid] = ItemOutcome(iid, "stopped", None, error=f"gate item {q['gate']['item']} stopped")
                continue
            if not open_:
                final[iid] = ItemOutcome(iid, "gated_out", gated_out_value(q),
                                         rule_reference=GATE_RULE + q["gate"]["item"],
                                         note="gate closed after the support check (PI Q2 b)")
                regated.append(iid)
                continue
            answers = []
            seen = set()
            for rec in by_item.get(iid, []):
                seen.add(rec.chunk_id)
                if rec.chosen_value == pc.NOT_COVERED:
                    answers.append(part_answer(rec, index[rec.chunk_id]))
                    continue
                st = status.get((iid, rec.chunk_id))
                if st is None:
                    raise ValueError(f"no support result for {iid} in {rec.chunk_id}")
                bar_failed = bool(rec.downgraded)
                answers.append(part_answer(rec, index[rec.chunk_id],
                                           failed=bar_failed or bool(_DOWNGRADED.match(st)),
                                           cause=rec.downgrade_cause if bar_failed else
                                           (st if _DOWNGRADED.match(st) else None)))
            for f in result.failures:
                if iid == VERDICT:
                    continue  # request failure is not a tag-only verdict vote
                if f["chunk_id"] in index and f["chunk_id"] not in seen and iid in f["question_ids"]:
                    answers.append(pc.PartAnswer(f["chunk_id"], index[f["chunk_id"]], pc.UNKNOWN, None,
                                                 failed=True, cause=f["reason"]))
                    seen.add(f["chunk_id"])
            final[iid] = _combine(s.combine_rules[iid], answers)
    return FinalPage(final, tuple(regated), tuple(opened))


# ---------------------------------------------------------------------------
# T-022 adapter
# ---------------------------------------------------------------------------


def to_pass1_page(result: PageCodeResult, page: PageInput) -> Any:
    """The T-022 :class:`~g3o.extract.request_v27.Pass1Page` (provisional verdict, jev's chosen values)."""
    from g3o.extract.request_v27 import PageCode, Pass1Page

    codes = tuple(PageCode(r.item_id, r.chunk_id, r.chosen_value) for r in result.records
                  if r.coder_type == "classifier" and r.chosen_value != pc.NOT_COVERED)
    complete = result.page_complete
    return Pass1Page(
        page_id=page.page_id, institution_id=page.institution_id, institution_name=page.institution,
        url=page.url, title=page.title, text=page.text, chunks=tuple(result.chunks), codes=codes,
        verdict=result.verdict.value,
        page_complete=complete.value if complete is not None and complete.state == "combined" else None,
        chrome_text=contact_text(page), links=page.links, has_metadata_date=page.has_metadata_date)


__all__ = [
    "CHROME_STATE_FIELD", "CODER_VERSION", "SKIPPED_QUESTIONS", "FinalPage", "ItemOutcome",
    "PageCodeResult", "PageCoderConfig", "PageFailed", "PageInput", "build_questions", "build_state",
    "code_page", "finalize_page", "gate_open", "gated_out_value", "part_answer", "plan_layout",
    "serialize_request", "to_pass1_page",
]
