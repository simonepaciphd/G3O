"""v2.7 Stage 6 executor (T-026): relation requests, support checks, pooled reclassification.

Pure apart from the two injected calls: ``ask_fn`` (the jev call, the same
``AskFn`` shape as T-023, wrapping :func:`g3o.common.jev_client.ask`) and
``quote_fn`` (the Stage 6 quote step). Tests pass fakes; nothing here opens a
network connection. The legacy ``g3o.validate.jev_validate`` path is not used.

Rules, as the signed codebook r15 and SPEC v001.28 state them:

- **X30 relations (R-005, R-017; ``core.activity_relation_cross_page``).**
  Every pair of activity observations on different pages is asked, including
  identical names (rules/0; the RC-D-002 H Q2 defect). The deterministic
  pre-filter "only to skip obviously distinct pairs (different activity_type
  and tool), never to merge" is applied only when both activity types are real
  signed codes that differ AND both tool lists are real and share no name
  (:func:`prefilter_distinct`); such a pair stores ``distinct_action`` set by
  rule (rules/5 "Store the distinct value with a rule note"). Within-page pairs
  are T-023's ``core.activity_segment`` pair outcomes, passed in. The request
  state is the approved ``relation.state`` of ``institution.json`` (fields in
  order; plain-word labels; missing values left out).
- **Support (R-041, R-081, X35).** Each relation and pooled answer goes through
  T-024 :func:`~g3o.common.support_check.check_code`. A quote counts only when
  it was copied from an input supporting quote shown in that request part, and
  it is matched on that input's stored page part (R-044; the storage pooled
  passage, T-028). The Stage 6 quote step itself has no producer on this branch
  (no card builds it): with ``quote_fn=None`` every check that needs a quote
  stays PENDING, and pending work is never published (PI question, report).
- **Merging (R-005).** Only explicit, supported ``same_activity`` /
  ``shared_participation`` relations at >= 0.8 merge
  (:func:`~g3o.validate.consolidate_v27.relation_plan`). A pending relation is
  a missing decision; the institution is held, never published with the pair
  silently unmerged.
- **X31 pooling (``core.pooled_activity_fields``).** For a merged activity, each
  activity.json question is asked once over the union of the supported quotes
  of its confirmed observations (non-confirmed observations: relations only,
  r2#51), in round order. Gates are evaluated on the support-checked pooled
  answers of earlier rounds (R-008; round-5 gates "after downgrades").
  Too-long pools are split by T-020
  :func:`~g3o.common.page_chunks.prepare_pool_requests` and combined by each
  item's own rule (RC-D-005 10 a).
- **Source confidence (RC-D-025 A1, C7 a, P10-P12).** Which support records
  belong to a source claim is T-026's call (P12):
  :func:`source_claim_records` - the page-level records of the source's page
  plus the records of the observations on that page that belong to the
  source row's activity. Scored by T-015 ``source_confidence_rule``;
  aggregated per activity by ``consolidate_v27.activity_confidence`` (C8 b).

Open points are held explicitly (``Held``), never filled; see the T-026 report.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Any

from g3o.classify.jev_activity_code import (
    GATE_RULE,
    NOT_COVERED,
    UNKNOWN,
    ItemOutcome,
    PartCombiner,
    PartVote,
    _gate_kind,
    default_labels,
    gate_open,
    gated_out_value,
    value_label,
)
from g3o.classify.questions.v27 import choice_request, load_set
from g3o.common.jev_client import JevAccountError, JevResult
from g3o.common.jev_record import ClassifierRule, CoderRecord
from g3o.common.page_chunks import (
    JEV_STATE_TOKEN_LIMIT,
    PoolEntry,
    PoolPart,
    TokenEstimator,
    prepare_pool_requests,
)
from g3o.common.source_fields import PendingCheck, SourceConfidence, source_confidence_rule
from g3o.common.support_check import (
    NO_QUOTE,
    SET_BY_RULE,
    CodeEvidence,
    Entailment,
    PageSources,
    SupportResult,
    check_code,
)
from g3o.extract.years import extract_year_candidates
from g3o.validate.consolidate_v27 import (
    MISSING,
    ActivityObservation,
    ConsolidationError,
    RelationDecision,
    ReviewedPage,
    _positive,
    relation_plan,
)

CODER_VERSION = "g3o.validate.stage6_v27.v1"
RELATION_ITEM = "core.activity_relation_cross_page"
WITHIN_PAGE_ITEM = "core.activity_segment"
PREFILTER_RULE = "relation_prefilter:different_activity_type_and_tool"

# Hold reasons (pending work; never published, never turned into a value).
QUOTE_STEP_ABSENT = "stage6_quote_step_absent"
RELATION_OVER_BUDGET = "relation_request_over_budget_split_marker_unapproved"
POOLED_NANO_GATE = "pooled_nano_gate_unruled"
POOLED_STATED_NUMBERS_DIFFER = "pooled_stated_numbers_differ_form_unruled"
REQUEST_FAILED = "jev_request_failed"
MISSING_REQUEST_ID = "jev_missing_request_id"
ANSWER_MISSING = "jev_answer_missing"

#: The extracted number the ``deployment_scale_unit`` gate reads (``any stated``).
NUMBER_ITEM = "core.deployment_scale_number"

#: Part count used when measuring a pooled payload (upper bound on the marker width).
MEASURE_PARTS = 999_999

AskFn = Callable[[dict[str, Any], dict[str, dict[str, Any]]], JevResult]

#: relation.state.record_fields -> the codebook item each one shows (``None``: record attribute).
RECORD_ITEMS: Mapping[str, str | None] = {
    "activity_name": "core.activity_name",
    "activity_type": "core.activity_type",
    "action_type": "core.action_type",
    "tool_name": "core.tool_name",
    "contracting_party": "core.contracting_party",
    "developer": "core.developer",
    "year_announced": "core.year_announced",
    "page_url": None,
    "source_type": "core.source_type",
    "supporting_quotes": None,
}
#: record fields shown as their signed plain-word label (W7 (ii) b).
LABELLED_FIELDS = frozenset({"activity_type", "action_type", "source_type"})


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputQuote:
    """One supported quote of an observation, located on its stored page.

    ``producing_chunk_id`` is the part that produced the code (R-044);
    ``quote_chunk_id`` is where the quote was matched (that part, or chrome).
    ``source_type_label`` is the signed label of the source's type, or None when
    the type has no label (automatically typed, missing).
    """

    support_id: str
    observation_id: str
    source_id: str
    sources: PageSources
    producing_chunk_id: str
    quote_chunk_id: str
    quote_text: str
    source_type_label: str | None
    source_publication_date: str | None
    stage_as_of: str
    page_url: str
    page_order: int
    passage_order: int

    @property
    def pool_date(self) -> str:
        """R-044 (RC-D-005 T-020 readings): source date, else the ``stage_as_of`` fallback."""
        return self.source_publication_date or self.stage_as_of


@dataclass(frozen=True)
class ObservationRecord:
    """What a relation request shows of one observation (``relation.state.record_fields``)."""

    observation_id: str
    page_id: str
    values: Mapping[str, Any]  # final per-page values by item id (T-023 FinalActivity projection)
    page_url: str
    quotes: tuple[InputQuote, ...]


@dataclass(frozen=True)
class Stage6QuoteRequest:
    kind: str  # "relation" / "pooled"
    key: str  # pair key or pool id
    part_id: str
    question_id: str
    item_id: str
    value: str
    candidates: tuple[InputQuote, ...]  # the input quotes shown in this request part


@dataclass(frozen=True)
class Stage6Quote:
    """The quote step's answer: a verbatim copy of one candidate (or none) and its X35 answer."""

    quote: str | None
    input_support_id: str | None
    entailment: Entailment | None = None


QuoteFn = Callable[[Stage6QuoteRequest], Stage6Quote]


@dataclass(frozen=True)
class Stage6Config:
    rules: Mapping[tuple[str, str | None], ClassifierRule]  # jev_record.load_classifier_rules
    setup_pointer: str
    configured_model: str
    combiner: PartCombiner
    reference_year: int
    reserved_tokens: int  # explicit allowance absent from the payload (prepare_pool_requests)
    limit_tokens: int = JEV_STATE_TOKEN_LIMIT
    estimator: TokenEstimator | None = None
    prefilter: bool = True
    coder_version: str = CODER_VERSION
    labels: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class Held:
    """Work that could not finish; it blocks publication of what depends on it."""

    reason: str
    key: str
    detail: str | None = None


# ---------------------------------------------------------------------------
# Relation requests (X30)
# ---------------------------------------------------------------------------


def _real(value: Any) -> bool:
    return isinstance(value, str) and value not in MISSING and bool(value.strip())


def _tools(value: Any) -> set[str] | None:
    items = value if isinstance(value, (list, tuple)) else [value]
    names = {v.strip().casefold() for v in items if _real(v)}
    return names or None


def prefilter_distinct(a: ObservationRecord, b: ObservationRecord) -> bool:
    """rules/0's pre-filter, read conservatively: skip only when BOTH differ on real values.

    A missing activity type or tool never makes a pair "obviously distinct";
    such a pair is asked.
    """
    ta, tb = a.values.get("core.activity_type"), b.values.get("core.activity_type")
    if not (_real(ta) and _real(tb)) or ta == tb:
        return False
    tools_a, tools_b = _tools(a.values.get("core.tool_name")), _tools(b.values.get("core.tool_name"))
    return tools_a is not None and tools_b is not None and not (tools_a & tools_b)


def record_state(rec: ObservationRecord, labels: Mapping[str, Any]) -> dict[str, Any]:
    """One relation record: approved field order, labels for labelled fields, missing left out."""
    out: dict[str, Any] = {}
    for name, item in RECORD_ITEMS.items():
        if name == "page_url":
            value: Any = rec.page_url
        elif name == "supporting_quotes":
            value = [q.quote_text for q in rec.quotes] or None
        else:
            raw = rec.values.get(item)
            if name in LABELLED_FIELDS:
                value = value_label(item, None, raw, labels)
            elif isinstance(raw, (list, tuple)):
                value = [v for v in raw if _real(v)] or None
            elif isinstance(raw, int) and not isinstance(raw, bool):
                value = f"{raw:04d}"
            else:
                value = raw if _real(raw) else None
        if value is not None:
            out[name] = value
    return out


def relation_state(first: ObservationRecord, second: ObservationRecord, *, institution: str,
                   country: str | None, qset: Mapping[str, Any], labels: Mapping[str, Any]) -> dict[str, Any]:
    """``relation.state.fields`` in order (coder_instructions, institution, country, records)."""
    fields = [f["name"] for f in qset["relation"]["state"]["fields"]]
    if fields != ["coder_instructions", "institution", "country", "first_record", "second_record"]:
        raise ValueError(f"relation state fields changed: {fields}")
    if [f["name"] for f in qset["relation"]["state"]["record_fields"]] != list(RECORD_ITEMS):
        raise ValueError("relation record fields changed")
    state: dict[str, Any] = {"coder_instructions": qset["system_prompt"], "institution": institution}
    if country:
        state["country"] = country
    state["first_record"] = record_state(first, labels)
    state["second_record"] = record_state(second, labels)
    return state


@dataclass(frozen=True)
class RelationOutcome:
    lhs: str
    rhs: str
    decision: RelationDecision | None  # None: held
    records: tuple[CoderRecord, ...]
    support: tuple[SupportResult, ...]
    held: tuple[Held, ...] = ()


def _request(ask_fn: AskFn, state: dict[str, Any], questions: dict[str, dict[str, Any]]
             ) -> tuple[JevResult | None, str | None, str | None]:
    try:
        result = ask_fn(state, questions)
    except JevAccountError:
        raise
    except Exception as exc:  # noqa: BLE001 - a failed request fails this part only
        return None, REQUEST_FAILED, f"{type(exc).__name__}: {exc}"
    if not (isinstance(result.request_id, str) and result.request_id.strip()):
        return None, MISSING_REQUEST_ID, None
    return result, None, None


def _support(kind: str, key: str, part_id: str, q: Mapping[str, Any], rec: CoderRecord,
             candidates: Sequence[InputQuote], quote_fn: QuoteFn | None, *,
             activity_id: str | None, linked: str | None) -> SupportResult | Held:
    """T-024 check of one Stage 6 answer; the quote must come from a candidate of this part."""
    value = str(rec.chosen_value)
    placeholder = PageSources(part_id, {part_id: ""})
    base = dict(item_id=q["item_id"], value=value, probability=rec.chosen_answer_probability,
                activity_id=activity_id, linked_activity=linked)
    probe = check_code(CodeEvidence(chunk_id=part_id, **base), placeholder)
    if probe.support_status != NO_QUOTE:
        return probe  # no quote needed (exempt value): the check is complete without the quote step
    if not candidates:
        return probe  # nothing shown in this part to copy from: no supporting text
    if quote_fn is None:
        return Held(QUOTE_STEP_ABSENT, f"{kind}:{key}:{part_id}:{q['question_id']}")
    answer = quote_fn(Stage6QuoteRequest(kind, key, part_id, q["question_id"], q["item_id"], value,
                                         tuple(candidates)))
    if answer.quote is None or not answer.quote.strip():
        return probe  # the quote step found no supporting text: downgraded_no_quote
    source = next((c for c in candidates if c.support_id == answer.input_support_id), None)
    if source is None:  # copied from outside this part: no supporting text (R-044)
        return check_code(CodeEvidence(chunk_id=part_id, quote=answer.quote, quote_chunk_id=part_id + "#outside",
                                       entailment=answer.entailment, **base), placeholder)
    return check_code(CodeEvidence(chunk_id=source.producing_chunk_id, quote=answer.quote,
                                   quote_chunk_id=source.quote_chunk_id, entailment=answer.entailment, **base),
                      source.sources)


def _record(result: JevResult, q: Mapping[str, Any], part_id: str, config: Stage6Config, qsv: str,
            observation_id: str | None) -> CoderRecord:
    return CoderRecord.from_jev(
        result, question_id=q["question_id"], item_id=q["item_id"], item_part=q.get("part"),
        support_id=None, observation_id=observation_id, chunk_id=part_id,
        coder_version=config.coder_version, configured_model=config.configured_model,
        question_set_version=qsv, setup_pointer=config.setup_pointer,
        classifier_rule=config.rules[(q["item_id"], q.get("part"))])


def _mechanical(item_id: str, question_id: str | None, value: str, rule: str, config: Stage6Config,
                qsv: str, observation_id: str | None = None) -> CoderRecord:
    return CoderRecord(
        item_id=item_id, item_part=None, question_id=question_id, support_id=None,
        observation_id=observation_id, chunk_id=None, coder_type="mechanical",
        coder_version=config.coder_version, configured_model=None, actual_response_model=None,
        request_id=None, question_set_version=qsv, setup_pointer=config.setup_pointer,
        answer_type="rule", chosen_value=value, confidence=None, probability_distribution=None,
        rule_reference=rule)


def _support_key(sr: SupportResult) -> str:
    return "|".join(str(x) for x in (sr.activity_id, sr.linked_activity, sr.item_id, sr.part, sr.chunk_id))


def code_relation(first: ObservationRecord, second: ObservationRecord, ask_fn: AskFn,
                  quote_fn: QuoteFn | None, config: Stage6Config, *, institution: str,
                  country: str | None, qset: Mapping[str, Any] | None = None) -> RelationOutcome:
    """Ask (or pre-filter) one cross-page pair; return its support-checked decision or a hold."""
    qset = qset or load_set("institution")
    qsv = qset["question_set_version"]
    if first.page_id == second.page_id:
        raise ConsolidationError("within-page pairs are T-023 pair outcomes, not Stage 6 requests")
    key = f"{first.observation_id}|{second.observation_id}"
    if config.prefilter and prefilter_distinct(first, second):
        rec = _mechanical(RELATION_ITEM, RELATION_ITEM, "distinct_action", PREFILTER_RULE, config, qsv,
                          first.observation_id)
        sr = check_code(CodeEvidence(RELATION_ITEM, "distinct_action", key, rule_name=PREFILTER_RULE,
                                     activity_id=first.observation_id, linked_activity=second.observation_id),
                        PageSources(key, {key: ""}))
        decision = RelationDecision(first.observation_id, second.observation_id, "distinct_action", None,
                                    SET_BY_RULE, (rec,), (), "cross_page")
        return RelationOutcome(first.observation_id, second.observation_id, decision, (rec,), (sr,))
    labels = config.labels if config.labels is not None else default_labels()
    q = next(x for x in qset["relation"]["questions"] if x["item_id"] == RELATION_ITEM)
    state = relation_state(first, second, institution=institution, country=country, qset=qset, labels=labels)
    questions = {q["question_id"]: choice_request(q, part=False)}
    estimator = config.estimator or TokenEstimator()
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True)  # state measure (RC-D-005, C-004)
    if estimator.tokens(payload) > config.limit_tokens - config.reserved_tokens:
        return RelationOutcome(first.observation_id, second.observation_id, None, (), (),
                               (Held(RELATION_OVER_BUDGET, key),))
    part_id = f"{key}#p001"
    result, reason, detail = _request(ask_fn, state, questions)
    if result is None or q["question_id"] not in result.answers:
        return RelationOutcome(first.observation_id, second.observation_id, None, (), (),
                               (Held(reason or ANSWER_MISSING, key, detail),))
    rec = _record(result, q, part_id, config, qsv, first.observation_id)
    if rec.chosen_value == NOT_COVERED:
        raise ConsolidationError("a single-part relation request returned the temporary part answer")
    checked = _support("relation", key, part_id, q, rec, (*first.quotes, *second.quotes), quote_fn,
                       activity_id=first.observation_id, linked=second.observation_id)
    if isinstance(checked, Held):
        return RelationOutcome(first.observation_id, second.observation_id, None, (rec,), (), (checked,))
    vote = PartVote(part_id, 1, rec.chosen_value, rec.chosen_answer_probability,
                    failed=bool(rec.downgraded) or checked.downgraded,
                    cause=rec.downgrade_cause or (checked.support_status if checked.downgraded else None))
    combined = config.combiner.combine(RELATION_ITEM, [vote])
    value = UNKNOWN if combined.failed else combined.value
    decision = RelationDecision(first.observation_id, second.observation_id, str(value),
                                rec.chosen_answer_probability, checked.support_status, (rec,),
                                (_support_key(checked),) if checked.support_status == "supported" else (),
                                "cross_page")
    return RelationOutcome(first.observation_id, second.observation_id, decision, (rec,), (checked,))


def cross_page_pairs(records: Sequence[ObservationRecord]) -> tuple[tuple[ObservationRecord, ObservationRecord], ...]:
    """Every pair of observations on different pages, input order (lhs = earlier input)."""
    return tuple((a, b) for a, b in combinations(records, 2) if a.page_id != b.page_id)


# ---------------------------------------------------------------------------
# Pooled reclassification (X31)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PooledActivity:
    pool_id: str
    observation_ids: tuple[str, ...]
    outcomes: Mapping[str, ItemOutcome]  # question_id -> final (support-checked) outcome
    records: tuple[CoderRecord, ...]
    support: tuple[SupportResult, ...]
    parts: Mapping[int, tuple[str, ...]]  # round -> part ids
    held: tuple[Held, ...] = ()
    question_set_version: str = ""

    @property
    def finished(self) -> bool:
        return not self.held and all(o.state in ("combined", "gated_out") for o in self.outcomes.values())


def _quote_row(q: InputQuote) -> dict[str, Any]:
    """One pooled quote row; a missing value (an undated source, or a source type with no
    signed label: automatically typed official / archive, or no type) is left out (RC-D-028 3 a)."""
    row: dict[str, Any] = {"quote_text": q.quote_text}
    if q.source_type_label:
        row["source_type"] = q.source_type_label
    if q.source_publication_date is not None:
        row["source_publication_date"] = q.source_publication_date
    row["page_url"] = q.page_url
    return row


def pooled_state(part: PoolPart, n_parts: int, by_entry: Mapping[str, InputQuote],
                 qset: Mapping[str, Any], *, stated_number: str | None = None) -> dict[str, Any]:
    """``pooled.state``: pool_note, supporting quotes (pool order), page_part marker, then
    ``stated_number`` (RC-D-028 2 a; RC-D-021 W-06 name) when a question of the request shows it."""
    st = qset["pooled"]["state"]
    if [f["name"] for f in st["quote_fields"]] != ["quote_text", "source_type", "source_publication_date",
                                                   "page_url"]:
        raise ValueError("pooled quote fields changed")
    state: dict[str, Any] = {"coder_instructions": qset["system_prompt"],
                             st["instruction_field"]: qset["pooled"]["instruction"],
                             "supporting_quotes": [_quote_row(by_entry[e.entry_id]) for e in part.entries],
                             st["split_marker"]["name"]: f"{part.index} of {n_parts}"}
    if n_parts > 1:
        state["part_note"] = qset["part_prompt"]["sentence"]
    if stated_number is not None:
        state["stated_number"] = stated_number
    return state


def stated_numbers(eligible: Sequence[str], observations: Mapping[str, ActivityObservation]) -> tuple[str, ...]:
    """The extractor's number words of the pooled (confirmed) observations, distinct, group order.

    Read from each observation's extracted fields (``core.deployment_scale_number``, the
    T-022 field the per-page state shows as ``stated_number``); missing values left out.
    """
    out: list[str] = []
    for k in eligible:
        v = observations[k].fields.get(NUMBER_ITEM)
        if _real(v) and v not in out:
            out.append(v)
    return tuple(out)


def pool_activity(pool_id: str, group: Sequence[str], observations: Sequence[ActivityObservation],
                  pages: Sequence[ReviewedPage], quotes: Sequence[InputQuote], ask_fn: AskFn,
                  quote_fn: QuoteFn | None, config: Stage6Config, *,
                  activity_set: Mapping[str, Any] | None = None,
                  qset: Mapping[str, Any] | None = None) -> PooledActivity:
    """Ask every activity.json question once over the merged activity's pooled quotes."""
    qset = qset or load_set("institution")
    aset = activity_set or load_set("activity")
    qsv = qset["question_set_version"]
    if qset["pooled"]["question_ids"] != [q["question_id"] for q in aset["questions"]]:
        raise ValueError("pooled membership differs from the activity set")
    page_map = {p.page_id: p for p in pages}
    obs = {o.observation_id: o for o in observations}
    eligible = tuple(k for k in group if obs[k].supported and _positive(page_map[obs[k].page_id]))
    selected = [q for q in quotes if q.observation_id in eligible]
    if not eligible or any(not any(q.observation_id == k for q in selected) for k in eligible):
        raise ConsolidationError("eligible pooled observation has no actual support quote")
    if len({q.support_id for q in selected}) != len(selected):
        raise ConsolidationError("duplicate pooled support identity")
    numbers = stated_numbers(eligible, obs)
    shown_number = numbers[0] if len(numbers) == 1 else None
    by_entry = {q.support_id: q for q in selected}
    entries = [PoolEntry(q.support_id, json.dumps(_quote_row(q), ensure_ascii=False, sort_keys=True),
                         q.pool_date, q.page_order * 100_000 + q.passage_order) for q in selected]
    questions = [q for q in aset["questions"]]
    by_id = {q["question_id"]: q for q in questions}
    final: dict[str, ItemOutcome] = {}
    records: list[CoderRecord] = []
    support: list[SupportResult] = []
    held: list[Held] = []
    parts_by_round: dict[int, tuple[str, ...]] = {}
    part_status: dict[tuple[str, str], str] = {}
    # One layout for every round (the pooled state carries no earlier-round answers).
    # Measured on the request STATE (RC-D-005: "32k = 32,000 tokens of request
    # state"; C-004), in the multi-part form with a wide marker, so the state sent
    # ("i of n", part note only when n > 1) is never larger. The activity-set
    # questions are not in the measure: round 3 alone estimates above 32k.

    def serialize(part: PoolPart) -> str:  # with the stated number when one exists (upper bound)
        return json.dumps(pooled_state(part, MEASURE_PARTS, by_entry, qset, stated_number=shown_number),
                          ensure_ascii=False, sort_keys=True)

    prepared = prepare_pool_requests(pool_id, entries, serialize_request=serialize,
                                     estimator=config.estimator, limit_tokens=config.limit_tokens,
                                     reserved_tokens=config.reserved_tokens)
    for rnd in sorted({q["round"] for q in questions}):
        asked = []
        for q in (q for q in questions if q["round"] == rnd):
            kind = _gate_kind(q, by_id)
            if kind == "nano" and q["gate"]["item"] != NUMBER_ITEM:
                held.append(Held(POOLED_NANO_GATE, f"{pool_id}:{q['question_id']}"))
                final[q["question_id"]] = ItemOutcome(q["question_id"], q["item_id"], q.get("part"), "pending",
                                                      None, note=POOLED_NANO_GATE)
                continue
            if kind == "nano":  # RC-D-028 2 a: open when any merged observation states a number
                if not numbers:
                    value = gated_out_value(q)
                    final[q["question_id"]] = ItemOutcome(q["question_id"], q["item_id"], q.get("part"),
                                                          "gated_out", value, rule_reference=GATE_RULE + NUMBER_ITEM)
                    records.append(_mechanical(q["item_id"], q["question_id"], value, GATE_RULE + NUMBER_ITEM,
                                               config, qsv))
                    continue
                if NUMBER_ITEM in (q.get("shows_value_of") or ()) and shown_number is None:
                    # several different stated numbers: the form of stated_number is not ruled (report)
                    held.append(Held(POOLED_STATED_NUMBERS_DIFFER, f"{pool_id}:{q['question_id']}",
                                     " | ".join(numbers)))
                    final[q["question_id"]] = ItemOutcome(q["question_id"], q["item_id"], q.get("part"), "pending",
                                                          None, note=POOLED_STATED_NUMBERS_DIFFER)
                    continue
            if kind == "item":
                open_ = gate_open(q, final, {}, by_id)
                if open_ is None:
                    final[q["question_id"]] = ItemOutcome(q["question_id"], q["item_id"], q.get("part"),
                                                          "pending", None, note="gate item pending")
                    continue
                if not open_:
                    value = gated_out_value(q)
                    final[q["question_id"]] = ItemOutcome(q["question_id"], q["item_id"], q.get("part"),
                                                          "gated_out", value,
                                                          rule_reference=GATE_RULE + q["gate"]["item"])
                    records.append(_mechanical(q["item_id"], q["question_id"], value,
                                               GATE_RULE + q["gate"]["item"], config, qsv))
                    continue
            asked.append(q)
        if not asked:
            continue
        years = any(q.get("dynamic_choices") == "year" for q in asked)
        show_number = any(NUMBER_ITEM in (q.get("shows_value_of") or ()) for q in asked)
        n = len(prepared)
        parts_by_round[rnd] = tuple(p.part.part_id for p in prepared)
        votes: dict[str, list[PartVote]] = {q["question_id"]: [] for q in asked}
        pending: set[str] = set()
        for prep in prepared:
            part = prep.part
            text = " ".join(by_entry[e.entry_id].quote_text for e in part.entries)
            cands = ([c.year for c in extract_year_candidates(text, config.reference_year)] if years else None)
            qs = {q["question_id"]: choice_request(q, part=n > 1, years=cands
                                                   if q.get("dynamic_choices") == "year" else None)
                  for q in asked}
            state = pooled_state(part, n, by_entry, qset, stated_number=shown_number if show_number else None)
            result, reason, detail = _request(ask_fn, state, qs)
            shown = tuple(by_entry[e.entry_id] for e in part.entries)
            for q in asked:
                qid = q["question_id"]
                if result is None or qid not in result.answers:
                    votes[qid].append(PartVote(part.part_id, part.index, UNKNOWN, None, True,
                                               reason or ANSWER_MISSING))
                    continue
                rec = _record(result, q, part.part_id, config, qsv, None)
                records.append(rec)
                if rec.chosen_value == NOT_COVERED:
                    votes[qid].append(PartVote(part.part_id, part.index, rec.chosen_value,
                                               rec.chosen_answer_probability))
                    continue
                checked = _support("pooled", pool_id, part.part_id, q, rec, shown, quote_fn,
                                   activity_id=pool_id, linked=None)
                if isinstance(checked, Held):
                    held.append(checked)
                    pending.add(qid)
                    continue
                support.append(checked)
                part_status[(qid, part.part_id)] = checked.support_status
                down = checked.downgraded
                votes[qid].append(PartVote(part.part_id, part.index, rec.chosen_value,
                                           rec.chosen_answer_probability, failed=bool(rec.downgraded) or down,
                                           cause=rec.downgrade_cause or (checked.support_status if down else None)))
        for q in asked:
            qid = q["question_id"]
            if qid in pending:
                final[qid] = ItemOutcome(qid, q["item_id"], q.get("part"), "pending", None,
                                         note=QUOTE_STEP_ABSENT)
                continue
            try:
                c = config.combiner.combine(q["item_id"], votes[qid])
            except ValueError as exc:
                final[qid] = ItemOutcome(qid, q["item_id"], q.get("part"), "stopped", None, error=str(exc))
                continue
            final[qid] = ItemOutcome(qid, q["item_id"], q.get("part"), "combined", c.value, bool(c.failed),
                                     c.cause, c.part_id, c.probability)
    permanent_pilot_override(final, by_id, part_status)
    return PooledActivity(pool_id, eligible, final, tuple(records), tuple(support), parts_by_round,
                          tuple(held), qsv)


# RC-D-025 B2 a / PI 2026-11-10 item 6 a: the T-023 override, re-applied after the
# cross-page (pooled) combination. Same constants and logic as T-023
# (reclass/t023-ppilot-20261110 53e6b02, ``_permanent_pilot_override``); reconcile
# to one shared helper when both branches land.
PERMANENT_PILOT_ITEM = "core.permanent_pilot"
ADOPTION_STAGE_ITEM = "core.adoption_stage"
PERMANENT_PILOT_RULE = "permanent_pilot_override:" + PERMANENT_PILOT_ITEM
PERMANENT_PILOT_STAGES = frozenset({"pilot", "production"})
PERMANENT_PILOT_TARGET = "production"


def permanent_pilot_override(final: dict[str, ItemOutcome], by_id: Mapping[str, Mapping[str, Any]],
                             part_status: Mapping[tuple[str, str], str]) -> None:
    """In place, on the final pooled outcomes (codebook r15 ``core.permanent_pilot`` rules/0).

    A SUPPORTED combined ``yes`` (the T-024 status of the pooled part that produced
    it) sets ``adoption_stage`` to ``production`` only when the combined stage is
    ``pilot``; ``production`` stays; every other stage and the flag are unchanged.
    The rule is recorded only when the value changes (item 4 a); the stage keeps its
    original part and probability (item 5 a).
    """
    pp_qid = next((q for q, d in by_id.items() if d["item_id"] == PERMANENT_PILOT_ITEM and d.get("part") is None),
                  None)
    st_qid = next((q for q, d in by_id.items() if d["item_id"] == ADOPTION_STAGE_ITEM and d.get("part") is None),
                  None)
    pp, stage = final.get(pp_qid), final.get(st_qid)
    if pp is None or stage is None:
        return
    if pp.state != "combined" or pp.value != "yes" or pp.failed or pp.part_id is None:
        return
    if part_status.get((pp_qid, pp.part_id)) != "supported":
        return
    if stage.state != "combined" or stage.failed or stage.value not in PERMANENT_PILOT_STAGES:
        return
    if stage.value == PERMANENT_PILOT_TARGET:
        return
    final[st_qid] = replace(
        stage, value=PERMANENT_PILOT_TARGET, rule_reference=PERMANENT_PILOT_RULE,
        note=(f"RC-D-025 B2 a: pooled stage {stage.value!r} -> {PERMANENT_PILOT_TARGET!r} by a supported "
              f"permanent_pilot 'yes' (part {pp.part_id}); codebook core.permanent_pilot rules/0"))


# ---------------------------------------------------------------------------
# Source confidence (RC-D-025 A1, P12)
# ---------------------------------------------------------------------------


def source_claim_records(page_id: str, activity_observation_ids: Sequence[str],
                         page_support: Sequence[SupportResult | PendingCheck],
                         observation_support: Mapping[str, Sequence[SupportResult | PendingCheck]],
                         observation_pages: Mapping[str, str]) -> list[SupportResult | PendingCheck]:
    """The support records associated with one source claim (P12, decided here).

    The source's page-level records (page verdict and the source-level items:
    every record with no activity identity) plus the records of the
    observations ON THIS PAGE that belong to the source row's activity. Records
    of other activities on the same page are not associated. A source row with
    no activity (``_NA_``) has its page-level records only.
    """
    out: list[SupportResult | PendingCheck] = []
    for rec in page_support:
        if isinstance(rec, SupportResult) and rec.activity_id is not None:
            raise ConsolidationError("page-level support record carries an activity identity")
        out.append(rec)
    for oid in activity_observation_ids:
        if observation_pages.get(oid) != page_id:
            continue
        out.extend(observation_support.get(oid, ()))
    return out


def source_claim_confidence(source_id: str, credibility: str | None,
                            records: Sequence[SupportResult | PendingCheck]) -> SourceConfidence:
    return source_confidence_rule(source_id, credibility, records)


# ---------------------------------------------------------------------------
# Institution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage6Result:
    groups: tuple[tuple[str, ...], ...]
    relations: tuple[RelationDecision, ...]
    relation_outcomes: tuple[RelationOutcome, ...]
    pooled: Mapping[tuple[str, ...], PooledActivity]
    held: tuple[Held, ...]
    question_set_version: str
    missing_pairs: tuple[tuple[str, str], ...] = ()
    conflicting_groups: tuple[tuple[str, ...], ...] = ()

    @property
    def ready(self) -> bool:
        return (not self.held and not self.missing_pairs and not self.conflicting_groups
                and all(p.finished for p in self.pooled.values()))


def run_stage6(*, institution: str, country: str | None, pages: Sequence[ReviewedPage],
               observations: Sequence[ActivityObservation], records: Sequence[ObservationRecord],
               within_page: Sequence[RelationDecision], quotes: Sequence[InputQuote],
               ask_fn: AskFn, quote_fn: QuoteFn | None, config: Stage6Config) -> Stage6Result:
    """Relations, then the merge plan, then pooled reclassification of each merged group."""
    qset = load_set("institution")
    by_obs = {r.observation_id: r for r in records}
    if set(by_obs) != {o.observation_id for o in observations} or len(by_obs) != len(records):
        raise ConsolidationError("relation records must match the observations one to one")
    for o in observations:
        if by_obs[o.observation_id].page_id != o.page_id:
            raise ConsolidationError("relation record and observation disagree on the page")
    if any(d.scope != "within_page" for d in within_page):
        raise ConsolidationError("within-page decisions must come from T-023 pair outcomes")
    ordered = [by_obs[o.observation_id] for o in observations]
    outcomes = [code_relation(a, b, ask_fn, quote_fn, config, institution=institution, country=country,
                              qset=qset) for a, b in cross_page_pairs(ordered)]
    held = [h for o in outcomes for h in o.held]
    decisions = [*within_page, *(o.decision for o in outcomes if o.decision is not None)]
    plan = relation_plan(observations, pages, decisions)
    pooled: dict[tuple[str, ...], PooledActivity] = {}
    if plan.ready and not held:
        for n, group in enumerate(g for g in plan.groups if len(g) > 1):
            pooled[group] = pool_activity(f"pool{n + 1:03d}", group, observations, pages, quotes, ask_fn,
                                          quote_fn, config, qset=qset)
            held.extend(pooled[group].held)
    return Stage6Result(plan.groups, tuple(decisions), tuple(outcomes), pooled, tuple(held),
                        qset["question_set_version"], plan.missing_pairs, plan.conflicting_groups)


# ---------------------------------------------------------------------------
# 6_validate.json content (the shape stage6_adapters.write_stage6_artifacts takes)
# ---------------------------------------------------------------------------


class ContractGapError(ValueError):
    """A v2.7 value the legacy ``ConsolidatedInstitutionResponse`` cannot carry; never filled."""

    def __init__(self, gaps: Sequence[str]) -> None:
        self.gaps = tuple(gaps)
        super().__init__("6_validate.json cannot carry v2.7 values without a contract decision "
                         "(T-012 contract / T-028 writer): " + "; ".join(self.gaps))


def _year_deployed(values: Mapping[str, Any]) -> str:
    """Signed translation (``core.year_pilot_start`` translation_v25, R-051): the earlier of
    the two start years; if only one is a year, that year; if neither, unknown."""
    years = [v for v in (values.get("core.year_pilot_start"), values.get("core.year_production_start"))
             if isinstance(v, str) and len(v) == 4 and v.isdigit()]
    return min(years) if years else "unknown"


def _retired_fills() -> dict[str, Any]:
    from g3o.codebook.loader import load_codebook

    return {r["name"]: r.get("legacy_fill") for r in load_codebook().data["retired"] if "kind" not in r}


def consolidated_response(*, institution: Mapping[str, Any], metadata: Mapping[str, Any],
                          summary: Mapping[str, Any], activities: Sequence[tuple[str, Mapping[str, Any]]],
                          sources: Sequence[tuple[str, str, Mapping[str, Any]]]) -> Any:
    """Build and validate the ``ConsolidatedInstitutionResponse`` for one institution.

    ``institution``: the master identity columns (id, name, country, branch,
    level, search languages) - pipeline data, not codes. ``summary`` /
    ``activities`` (``(activity_id, values)``) / ``sources`` (``(source_id,
    activity_id, values)``) hold the final v2.7 values by item id, the same
    values that go into ``6_storage.json``. Shared columns take the v2.7 value;
    retired columns take only their signed ``legacy_fill`` (codebook
    ``retired``) or signed translation (``year_deployed``). Everything the
    legacy model cannot carry is collected and refused in one
    :class:`ContractGapError`; no value is substituted.
    """
    from pydantic import ValidationError

    from g3o.common.contract import (
        ConsolidatedActivity,
        ConsolidatedInstitution,
        ConsolidatedInstitutionResponse,
        SourceRecord,
    )
    from g3o.common.storage import table_fields

    fills = _retired_fills()
    gaps: list[str] = []

    def project(model: Any, table: str, values: Mapping[str, Any], fixed: Mapping[str, Any], label: str
                ) -> dict[str, Any]:
        by_column = {f["column_or_member"]: k for k, f in table_fields(table).items()}
        row: dict[str, Any] = dict(fixed)
        for name in model.model_fields:
            if name in row:
                continue
            if name in by_column and by_column[name] in values:
                value = values[by_column[name]]
                row[name] = "|".join(value) if isinstance(value, list) else value
            elif name == "year_deployed":
                row[name] = _year_deployed(values)
            elif name == "genai_evidence" and "core.page_verdict" in values:
                row[name] = values["core.page_verdict"]
            elif name in fills and isinstance(fills[name], str):
                row[name] = fills[name]
            else:
                gaps.append(f"{label}.{name}: no v2.7 value and no signed legacy fill")
        try:
            model.model_validate(row)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(x) for x in err["loc"]) or "-"
                shown = f" (value {err['input']!r})" if err["loc"] else ""
                gaps.append(f"{label}.{loc}: {err['msg'][:160]}{shown}")
        return row

    inst = project(ConsolidatedInstitution, "summary", summary, institution, "institution")
    acts = [project(ConsolidatedActivity, "activities", v, {"activity_id": aid}, f"activities[{aid}]")
            for aid, v in activities]
    srcs = [project(SourceRecord, "sources", v, {"source_id": sid, "activity_id": aid}, f"sources[{sid}]")
            for sid, aid, v in sources]
    if gaps:
        raise ContractGapError(gaps)
    try:
        return ConsolidatedInstitutionResponse.model_validate(
            {"consolidation_metadata": dict(metadata), "institution": inst, "activities": acts, "sources": srcs})
    except ValidationError as exc:  # cross-row legacy checks (e.g. RC-D-025 P9, being fixed under T-012)
        raise ContractGapError([f"response: {e['msg'][:240]}" for e in exc.errors()]) from exc


__all__ = [
    "CODER_VERSION", "ContractGapError", "NUMBER_ITEM", "POOLED_NANO_GATE", "POOLED_STATED_NUMBERS_DIFFER",
    "PREFILTER_RULE",
    "QUOTE_STEP_ABSENT", "RELATION_ITEM", "RELATION_OVER_BUDGET", "Held", "InputQuote",
    "ObservationRecord", "PooledActivity", "QuoteFn", "RelationOutcome", "Stage6Config", "Stage6Quote",
    "Stage6QuoteRequest", "Stage6Result", "code_relation", "consolidated_response", "permanent_pilot_override", "cross_page_pairs", "pool_activity",
    "pooled_state", "prefilter_distinct", "record_state", "relation_state", "run_stage6", "stated_numbers",
    "source_claim_confidence", "source_claim_records",
]
