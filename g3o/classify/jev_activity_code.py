"""jev pass-2 activity coder (T-023). Pure: the jev call and the part combiner are injected.

One page (the T-021 record, here :class:`g3o.extract.request_v27.Pass1Page`) with
its activity spans (T-022 :class:`g3o.extract.parser_v27.ActivitySpan`) is coded
per (page x activity) with the v2.7 activity question set (T-011 ``activity.json``):

1. **Unit (DEC-010 a, W-04 a).** Each activity with a resolved span on the page is
   labelled ``A1``, ``A2`` ... in input order (the same labels as the P-2 extractor,
   :func:`g3o.extract.pass2_support.select_requests`). Every part (T-020 chunk) that
   holds part of the span gets one request per round; the part text carries
   ``[[Ak]]`` / ``[[/Ak]]`` at the span ends that fall in it ("every part holding a
   linked passage votes", combining convention ``activity_level``). An activity whose
   span is unresolved or off the page is not coded (``activity_span_unresolved``).
2. **State (W-01 / W-02 / W-03 a / W-06 a; RC-D-022 W3-1 a, W3-2 a; RC-D-023 A-1..A-3).**
   The page state of pass 1 (no chrome field), then ``activity_name`` and
   ``tool_name``, then ``stated_number`` when a question of the request shows it,
   then each earlier-round answer of this activity: field = the question's column
   (``searched_institution_role`` for the role part), value = its signed plain-word
   label (a year as four ASCII digits; a multi answer as a list of labels in codebook
   value order); missing answers are left out; fields in ``activity.json`` question
   order. The earlier-round answer is the activity's provisional combined answer.
   The only extractor (nano) text that enters a request is the span offsets (as
   marks) and the three extracted values the signed state names
   (:data:`NANO_STATE_FIELDS`); the span anchors and supporting texts never do.
3. **Rounds and gates (R-008).** Rounds in ascending order. A question whose gate item
   was answered in an earlier round is asked only when the provisional combined answer
   is in its gate list; otherwise it gets its signed ``gated_out_value`` (else
   ``not_asked``) by rule ``gated_out:<gate item>``. The role part's gate (same item,
   same round) is applied after combining. The ``deployment_scale_unit`` gate reads
   the extracted ``deployment_scale_number`` (``any stated``).
4. **Combination (R-044; PI 2026-11-08 Q2 b, 2.1).** After each round each asked
   question is combined over the activity's parts by the injected :class:`PartCombiner`
   on the 0.8 bar only (provisional). :func:`finalize_activities` re-combines with the
   T-024 support results and re-applies the gates; a dependent whose final gate is
   closed gets its gated-out value, and jev's raw answers stay in the records.
5. **Records (T-027).** Every jev answer is a :class:`CoderRecord` with the signed
   0.8 downgrade rule. A reply without a request id is a failed part request
   (``jev_missing_request_id``, PI 2026-11-08 2.17); no placeholder id is recorded.
   A failed part enters combining as a failed answer.
6. **Pairs (PI 2026-11-07 7b/8b).** The separately approved ``pair_questions``
   instrument codes each pair at round 1, before ordinary activity rounds. The
   earlier page span is lhs; equal starts stop only that pair. Every part holding
   either span votes. Raw records name ``linked_activity``; pair support joins
   retain both activity identities. :func:`finalize_pairs` checks pair support.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Protocol

from g3o.classify.questions.v27 import choice_request, load_set
from g3o.common.jev_client import JevAccountError, JevResult
from g3o.common.jev_record import ClassifierRule, CoderRecord
from g3o.common.page_chunks import Chunk
from g3o.extract.parser_v27 import ActivitySpan
from g3o.extract.pass2_support import ActivityCode, Pass2Activity, Pass2Page
from g3o.extract.request_v27 import Pass1Page
from g3o.extract.years import extract_year_candidates

CODER_VERSION = "g3o.classify.jev_activity_code.v1"

NOT_COVERED = "not covered by this part"
NOT_ASKED = "not_asked"
UNKNOWN = "unknown"
#: Missing answers: never shown as earlier-round answers (W3-2 a).
MISSING = frozenset({"not_documented", "unknown", "not_asked", "_NA_"})

GATE_RULE = "gated_out:"
MISSING_REQUEST_ID = "jev_missing_request_id"
REQUEST_FAILED = "jev_request_failed"
ANSWER_MISSING = "jev_answer_missing"
SPAN_UNRESOLVED = "activity_span_unresolved"
PAIR_QUESTION_MISSING = "pair_question_missing"
PAIR_DIRECTION_TIE = "pair_direction_tie"

#: Extracted (nano) values the signed state names: state field -> T-022 field item.
NANO_STATE_FIELDS: Mapping[str, str] = {
    "activity_name": "core.activity_name",
    "tool_name": "core.tool_name",
    "stated_number": "core.deployment_scale_number",
}
#: Pair items: coded per pair of activities, each code naming the other (p2c a).
PAIR_ITEMS = frozenset({"core.activity_segment"})
#: Field of the role part in the earlier-answer state (RC-D-023 A-1 a).
ROLE_PART_FIELD = "searched_institution_role"
#: Year-context width each side of the span (W-05-P1).
YEAR_CONTEXT_CHARS = 200

AskFn = Callable[[dict[str, Any], dict[str, dict[str, Any]]], JevResult]

_GENERATED = Path(__file__).resolve().parents[1] / "codebook" / "generated" / "jev_questions.json"


# ---------------------------------------------------------------------------
# The part-combiner interface (ONE place; lane B's g3o.common.part_combine)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PartVote:
    """One part's answer to one question; field-for-field ``part_combine.PartAnswer``."""

    part_id: str
    part_index: int
    value: Any
    probability: float | None
    failed: bool = False
    cause: str | None = None
    ref: Any = None


class Combined(Protocol):
    """What this module reads from a combined answer (``part_combine.CombinedAnswer``)."""

    value: Any
    part_id: str | None
    probability: float | None
    failed: bool
    cause: str | None


class PartCombiner(Protocol):
    """The R-044 combiner T-023 calls. ``item_id`` is the codebook item; ``reference``
    is the combined answer of :meth:`same_part_as` (``observed_actor_role``). Raises
    ``ValueError`` (``part_combine.CombineError`` is one) when it cannot place a value."""

    def combine(self, item_id: str, answers: Sequence[PartVote], *,
                reference: Combined | None = None) -> Combined: ...

    def same_part_as(self, item_id: str) -> str | None: ...


def part_combine_adapter(codebook: Any = None) -> PartCombiner:
    """Bind :class:`PartCombiner` to ``g3o.common.part_combine`` (lane B, RULINGS 2.14).
    Imported lazily: the module is not on this branch's base."""
    from g3o.codebook.loader import load_codebook
    from g3o.common import part_combine as pc  # type: ignore[attr-defined]

    rules = pc.rules_from_codebook(codebook or load_codebook())

    class _Adapter:
        def combine(self, item_id, answers, *, reference=None):
            return pc.combine(rules[item_id], [pc.PartAnswer(**asdict(a)) for a in answers],
                              reference=reference)

        def same_part_as(self, item_id):
            return rules[item_id].same_part_as

    return _Adapter()


# ---------------------------------------------------------------------------
# Inputs, configuration, outcomes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityPageInput:
    """Mock of the T-021 page record plus the T-022 spans of the page."""

    page: Pass1Page
    country: str | None
    level_of_government: str | None
    spans: tuple[ActivitySpan, ...]


@dataclass(frozen=True)
class ActivityCoderConfig:
    rules: Mapping[tuple[str, str | None], ClassifierRule]  # jev_record.load_classifier_rules
    setup_pointer: str
    configured_model: str
    combiner: PartCombiner
    reference_year: int  # the calendar year of the run (year candidates; B1 c)
    coder_version: str = CODER_VERSION
    question_set: Mapping[str, Any] | None = None  # default: load_set("activity")
    labels: Mapping[str, Any] | None = None  # default: generated X35 label map


@dataclass(frozen=True)
class ItemOutcome:
    """An activity's answer to one question. ``state``: ``combined`` / ``gated_out`` /
    ``stopped`` (combiner refused, every part failed to answer, or its gate item stopped)."""

    question_id: str
    item_id: str
    part: str | None
    state: str
    value: Any
    failed: bool = False
    cause: str | None = None
    part_id: str | None = None
    probability: float | None = None
    rule_reference: str | None = None
    error: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class PartFailure:
    reason: str
    activity_id: str
    chunk_id: str
    round: int
    question_ids: tuple[str, ...]
    detail: str | None = None
    linked_activity: str | None = None


@dataclass(frozen=True)
class ActivityResult:
    activity_id: str
    label: str
    start: int
    end: int
    chunk_ids: tuple[str, ...]  # the parts holding the span, page order
    part_indices: tuple[int, ...]  # their 1-based page-wide part indices (combiner order)
    outcomes: Mapping[str, ItemOutcome]  # question_id -> outcome
    records: tuple[CoderRecord, ...]
    #: pair item records (p2c a): index into ``records`` -> the other activity of the pair
    record_links: Mapping[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PairResult:
    activity_id: str
    linked_activity: str
    chunk_ids: tuple[str, ...]
    part_indices: tuple[int, ...]
    outcome: ItemOutcome
    records: tuple[CoderRecord, ...]


@dataclass(frozen=True)
class PageActivityResult:
    page_id: str
    institution_id: str
    activities: tuple[ActivityResult, ...]
    skipped_activities: tuple[tuple[str, str], ...]  # (activity_id, reason)
    failures: tuple[PartFailure, ...]
    notes: tuple[str, ...]
    question_set_version: str
    codebook_sha256: str
    coder_version: str = CODER_VERSION
    pairs: tuple[PairResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "g3o-activity-code-v1",
            "page_id": self.page_id, "institution_id": self.institution_id,
            "question_set_version": self.question_set_version,
            "codebook_sha256": self.codebook_sha256, "coder_version": self.coder_version,
            "activities": [{
                "activity_id": a.activity_id, "label": a.label, "start": a.start, "end": a.end,
                "chunk_ids": list(a.chunk_ids), "part_indices": list(a.part_indices),
                "outcomes": {k: _jsonable(asdict(o)) for k, o in a.outcomes.items()},
                "records": [r.to_dict() for r in a.records],
                "record_links": {str(k): v for k, v in a.record_links.items()},
            } for a in self.activities],
            "skipped_activities": [list(s) for s in self.skipped_activities],
            "pairs": [{"activity_id": p.activity_id, "linked_activity": p.linked_activity,
                       "chunk_ids": list(p.chunk_ids), "part_indices": list(p.part_indices),
                       "outcome": asdict(p.outcome), "records": [r.to_dict() for r in p.records]}
                      for p in self.pairs],
            "failures": [asdict(f) for f in self.failures],
            "notes": list(self.notes),
        }


    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PageActivityResult:
        """Restore a durable checkpoint without inventing omitted part indices.

        Older v1 artifacts omitted activity part_indices and cannot safely
        resume. Refuse those artifacts explicitly; do not guess page positions.
        """
        if data.get("format") != "g3o-activity-code-v1":
            raise ValueError("unsupported activity-code artifact format")

        def outcome(raw: Mapping[str, Any]) -> ItemOutcome:
            def tuples(value: Any) -> Any:
                return tuple(tuples(v) for v in value) if isinstance(value, list) else value
            return ItemOutcome(**{**raw, "value": tuples(raw["value"])})

        def parts(raw: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[int, ...]]:
            if "part_indices" not in raw:
                raise ValueError("activity checkpoint lacks original part_indices; cannot resume")
            chunks, indices = tuple(raw["chunk_ids"]), tuple(raw["part_indices"])
            if (len(chunks) != len(indices) or len(set(chunks)) != len(chunks)
                    or any(type(i) is not int or i < 1 for i in indices)
                    or list(indices) != sorted(set(indices))):
                raise ValueError("invalid original activity part indices")
            return chunks, indices

        activities = []
        for raw in data["activities"]:
            chunks, indices = parts(raw)
            records = tuple(CoderRecord.from_dict(r) for r in raw["records"])
            links = {int(k): v for k, v in raw["record_links"].items()}
            if any(not 0 <= k < len(records) for k in links):
                raise ValueError("activity checkpoint has invalid pair record index")
            activities.append(ActivityResult(
                raw["activity_id"], raw["label"], raw["start"], raw["end"], chunks, indices,
                {k: outcome(v) for k, v in raw["outcomes"].items()}, records, links))
        pairs = []
        for raw in data["pairs"]:
            chunks, indices = parts(raw)
            pairs.append(PairResult(raw["activity_id"], raw["linked_activity"], chunks, indices,
                                    outcome(raw["outcome"]),
                                    tuple(CoderRecord.from_dict(r) for r in raw["records"])))
        return cls(
            page_id=data["page_id"], institution_id=data["institution_id"], activities=tuple(activities),
            skipped_activities=tuple(tuple(s) for s in data["skipped_activities"]),
            failures=tuple(PartFailure(**{**f, "question_ids": tuple(f["question_ids"])})
                           for f in data["failures"]),
            notes=tuple(data["notes"]), question_set_version=data["question_set_version"],
            codebook_sha256=data["codebook_sha256"], coder_version=data["coder_version"], pairs=tuple(pairs),
        )

    @classmethod
    def from_json(cls, text: str) -> PageActivityResult:
        return cls.from_dict(json.loads(text))

def _jsonable(v: Any) -> Any:
    if isinstance(v, tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


# ---------------------------------------------------------------------------
# Question-set setup
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def default_labels() -> Mapping[str, Any]:
    gen = json.loads(_GENERATED.read_text(encoding="utf-8"))
    ent = next(q for q in gen["questions"] if q["question_id"] == "core.support_entailment")
    return ent["labels"]


@dataclass(frozen=True)
class _Setup:
    qset: Mapping[str, Any]
    questions: tuple[dict[str, Any], ...]
    by_id: Mapping[str, dict[str, Any]]
    rounds: tuple[int, ...]
    labels: Mapping[str, Any]


def _gate_kind(q: Mapping[str, Any], by_id: Mapping[str, dict[str, Any]]) -> str:
    gate = q.get("gate")
    if not isinstance(gate, Mapping):
        return "none"
    if "part" in gate:
        return "part"
    if gate.get("item") in by_id:
        if by_id[gate["item"]]["round"] >= q["round"]:
            raise ValueError(f"{q['question_id']}: gate {gate['item']} is not asked in an earlier round")
        return "item"
    if gate.get("item") in NANO_STATE_FIELDS.values() and gate.get("values") == "any":
        return "nano"
    raise ValueError(f"{q['question_id']}: gate {gate!r} cannot be evaluated by pass 2")


def _setup(config: ActivityCoderConfig) -> _Setup:
    qset = config.question_set if config.question_set is not None else load_set("activity")
    qs = tuple(q for q in qset["questions"] if q["item_id"] not in PAIR_ITEMS)
    by_id = {q["question_id"]: q for q in qs}
    for q in qs:
        _gate_kind(q, by_id)
        if (q["item_id"], q.get("part")) not in config.rules:
            raise ValueError(f"{q['question_id']}: no signed classifier rule")
    return _Setup(qset, qs, by_id, tuple(sorted({q["round"] for q in qs})),
                  config.labels if config.labels is not None else default_labels())


def gated_out_value(question: Mapping[str, Any]) -> str:
    gate = question.get("gate")
    if isinstance(gate, Mapping) and isinstance(gate.get("gated_out_value"), str):
        return gate["gated_out_value"]
    return NOT_ASKED


def _first_part_id(q: Mapping[str, Any], by_id: Mapping[str, dict[str, Any]]) -> str:
    return next(o["question_id"] for o in by_id.values()
                if o["item_id"] == q["item_id"] and o["question_id"] != q["question_id"])


def gate_open(q: Mapping[str, Any], outcomes: Mapping[str, ItemOutcome],
              nano: Mapping[str, str], by_id: Mapping[str, dict[str, Any]]) -> bool | None:
    """True / False, or None when the gate item stopped. ``outcomes`` by question id."""
    kind = _gate_kind(q, by_id)
    gate = q.get("gate")
    if kind == "none":
        return True
    if kind == "nano":
        return bool(nano.get(gate["item"]))
    key = _first_part_id(q, by_id) if kind == "part" else gate["item"]
    g = outcomes.get(key)
    if g is None or g.state in ("stopped", "pending"):
        return None
    if kind == "part":
        return g.value not in gate["not_asked_when_relationship"]
    return g.value in gate["values"]


# ---------------------------------------------------------------------------
# Request building
# ---------------------------------------------------------------------------


def span_ok(page: Pass1Page, s: ActivitySpan) -> bool:
    return (isinstance(s.start, int) and isinstance(s.end, int)
            and 0 <= s.start < s.end <= len(page.text))


def parts_holding(page: Pass1Page, start: int, end: int) -> list[tuple[int, Chunk]]:
    """(1-based part index, chunk) of every part overlapping ``[start, end)``."""
    return [(i, c) for i, c in enumerate(page.chunks, start=1) if c.start < end and start < c.end]


@dataclass(frozen=True)
class ActivityPair:
    """Direction is page-span order; labels retain their existing input order."""

    lhs: ActivitySpan
    rhs: ActivitySpan
    lhs_label: str
    rhs_label: str
    parts: tuple[tuple[int, Chunk], ...]


def plan_pairs(inp: ActivityPageInput) -> tuple[tuple[ActivityPair, ...], tuple[tuple[str, str], ...]]:
    """Plan unique pairs; equal starts are explicitly unresolved, never tie-broken."""
    usable = [sp for sp in inp.spans if span_ok(inp.page, sp)]
    if len({sp.activity_id for sp in inp.spans}) != len(inp.spans):
        raise ValueError("duplicate activity_id")
    labels = {sp.activity_id: f"A{i}" for i, sp in enumerate(usable, start=1)}
    pairs, ties = [], []
    for first, second in combinations(usable, 2):
        if first.start == second.start:
            ties.append((first.activity_id, second.activity_id))
            continue
        lhs, rhs = sorted((first, second), key=lambda sp: sp.start)
        parts = tuple((i, c) for i, c in enumerate(inp.page.chunks, start=1)
                      if (c.start < lhs.end and lhs.start < c.end)
                      or (c.start < rhs.end and rhs.start < c.end))
        pairs.append(ActivityPair(lhs, rhs, labels[lhs.activity_id], labels[rhs.activity_id], parts))
    return tuple(pairs), tuple(ties)


def marked_pair_text(page: Pass1Page, chunk: Chunk, pair: ActivityPair) -> str:
    """Insert both labels at original offsets; never insert into already marked text."""
    marks: list[tuple[int, int, str]] = []
    for sp, label in ((pair.lhs, pair.lhs_label), (pair.rhs, pair.rhs_label)):
        if chunk.start <= sp.start < chunk.end:
            marks.append((sp.start, 1, f"[[{label}]]"))
        if chunk.start < sp.end <= chunk.end:
            marks.append((sp.end, 0, f"[[/{label}]]"))
    out, cursor = [], chunk.start
    for pos, _, marker in sorted(marks):
        out.extend((page.text[cursor:pos], marker))
        cursor = pos
    out.append(page.text[cursor:chunk.end])
    return "".join(out)


def marked_part_text(page: Pass1Page, chunk: Chunk, start: int, end: int, label: str) -> str:
    """The part's text with ``[[label]]`` / ``[[/label]]`` at the span ends inside it."""
    text = page.text
    out: list[str] = []
    pos = chunk.start
    if chunk.start <= start < chunk.end:
        out += [text[chunk.start:start], f"[[{label}]]"]
        pos = start
    if chunk.start < end <= chunk.end:
        out += [text[pos:end], f"[[/{label}]]", text[end:chunk.end]]
    else:
        out.append(text[pos:chunk.end])
    return "".join(out)


def nano_values(span: ActivitySpan) -> dict[str, str]:
    """The extracted values the state may show, by T-022 field item id."""
    wanted = set(NANO_STATE_FIELDS.values())
    out: dict[str, str] = {}
    for f in span.fields:
        if f.item_id in wanted and isinstance(f.value, str) and f.value.strip() and f.item_id not in out:
            out[f.item_id] = f.value
    return out


def value_label(item_id: str, part: str | None, value: Any, labels: Mapping[str, Any]) -> Any:
    """Signed plain-word label of an earlier answer (W-03 a), or None when it is left out."""
    if isinstance(value, (tuple, list)):
        lab = _label_values(item_id, part, labels)
        chosen = {v for v in value if v not in MISSING}
        out = [lab[v]["text"] for v in lab if v in chosen]  # codebook value order (A-2 a)
        if len(out) != len(chosen):
            raise ValueError(f"{item_id}: no signed label for {sorted(chosen - set(lab))}")
        return out or None
    entry = labels.get(item_id)
    if entry is not None and entry.get("value_label") == "year" and isinstance(value, int):
        value = f"{value:04d}"
    if not isinstance(value, str) or value in MISSING or value == NOT_COVERED:
        return None
    if entry is not None and entry.get("value_label") == "year":
        return value
    lab = _label_values(item_id, part, labels)
    if value not in lab:
        raise ValueError(f"{item_id}: no signed label for {value!r}")
    return lab[value]["text"]


def _label_values(item_id: str, part: str | None, labels: Mapping[str, Any]) -> Mapping[str, Any]:
    entry = labels.get(item_id)
    if entry is None:
        raise ValueError(f"{item_id}: no signed label map")
    if "parts" in entry and part is not None:
        return entry["parts"][part]["values"]
    return entry["values"]


def prior_fields(outcomes: Mapping[str, ItemOutcome], before_round: int, s: _Setup) -> dict[str, Any]:
    """Earlier-round answers of the activity, ``activity.json`` question order (A-3 a)."""
    out: dict[str, Any] = {}
    for q in s.questions:
        if q["round"] >= before_round:
            continue
        o = outcomes.get(q["question_id"])
        if o is None or o.state != "combined":
            continue
        lab = value_label(q["item_id"], q.get("part"), o.value, s.labels)
        if lab is None:
            continue
        name = ROLE_PART_FIELD if q.get("part") == ROLE_PART_FIELD else q["column"]
        out[name] = lab
    return out


def build_state(inp: ActivityPageInput, chunk: Chunk, index: int, span: ActivitySpan, label: str,
                nano: Mapping[str, str], prior: Mapping[str, Any], qset: Mapping[str, Any],
                *, show_number: bool) -> dict[str, Any]:
    page = inp.page
    n = len(page.chunks)
    state: dict[str, Any] = {
        "coder_instructions": qset["system_prompt"],
        "institution": page.institution_name,
        "country": inp.country,
        "level_of_government": inp.level_of_government,
        "page_url": page.url,
        "page_title": page.title,
        "page_part": f"{index} of {n}",
    }
    if n > 1:
        state["part_note"] = qset["part_prompt"]["sentence"]
    state["page_text"] = marked_part_text(page, chunk, span.start, span.end, label)
    state["activity_name"] = nano.get(NANO_STATE_FIELDS["activity_name"])
    state["tool_name"] = nano.get(NANO_STATE_FIELDS["tool_name"])
    if show_number:
        state["stated_number"] = nano.get(NANO_STATE_FIELDS["stated_number"])
    state.update(prior)
    return state


def year_candidates(page: Pass1Page, chunk: Chunk, start: int, end: int, reference_year: int) -> list[int]:
    """Years read on the whole part; sources overlapping the span +/- 200 chars kept (W-05-P1)."""
    lo, hi = start - YEAR_CONTEXT_CHARS - chunk.start, end + YEAR_CONTEXT_CHARS - chunk.start
    return [c.year for c in extract_year_candidates(chunk.text, reference_year)
            if any(src.start < hi and lo < src.end for src in c.sources)]


def build_questions(questions: Sequence[dict[str, Any]], *, part: bool,
                    years: Sequence[int] | None = None) -> dict[str, dict[str, Any]]:
    return {q["question_id"]: choice_request(q, part=part, years=years
                                             if q.get("dynamic_choices") == "year" else None)
            for q in questions}


# ---------------------------------------------------------------------------
# Coding
# ---------------------------------------------------------------------------


def _mechanical(q: Mapping[str, Any], value: str, rule: str, config: ActivityCoderConfig,
                qsv: str) -> CoderRecord:
    return CoderRecord(
        item_id=q["item_id"], item_part=q.get("part"), question_id=q["question_id"], support_id=None,
        observation_id=None, chunk_id=None, coder_type="mechanical",
        coder_version=config.coder_version, configured_model=None, actual_response_model=None,
        request_id=None, question_set_version=qsv, setup_pointer=config.setup_pointer,
        answer_type="rule", chosen_value=value, confidence=None, probability_distribution=None,
        rule_reference=rule)


def _gated(q: Mapping[str, Any], note: str | None = None) -> ItemOutcome:
    gate = q["gate"]
    ref = q["item_id"] if "part" in gate else gate["item"]
    return ItemOutcome(q["question_id"], q["item_id"], q.get("part"), "gated_out",
                       gated_out_value(q), rule_reference=GATE_RULE + ref, note=note)


def _stopped(q: Mapping[str, Any], error: str) -> ItemOutcome:
    return ItemOutcome(q["question_id"], q["item_id"], q.get("part"), "stopped", None, error=error)


def _vote(rec: CoderRecord, index: int, *, failed: bool | None = None,
          cause: str | None = None) -> PartVote:
    return PartVote(rec.chunk_id, index, rec.chosen_value, rec.chosen_answer_probability,
                    failed=bool(rec.downgraded) if failed is None else failed,
                    cause=rec.downgrade_cause if cause is None else cause)


def _combine(q: Mapping[str, Any], votes: Sequence[PartVote], combiner: PartCombiner,
             outcomes: Mapping[str, ItemOutcome], by_id: Mapping[str, dict[str, Any]]) -> ItemOutcome:
    qid, item, part = q["question_id"], q["item_id"], q.get("part")
    if not votes:
        return _stopped(q, "no part answered")
    if part == ROLE_PART_FIELD:
        # codebook long_page_rule role_part: the role comes from the part that produced
        # the relationship.
        rel = outcomes.get(_first_part_id(q, by_id))
        if rel is None or rel.state != "combined" or rel.part_id is None:
            return _stopped(q, "relationship not combined")
        v = next((x for x in votes if x.part_id == rel.part_id), None)
        if v is None:
            return _stopped(q, "no role answer from the relationship's part")
        if v.failed:
            return ItemOutcome(qid, item, part, "combined", UNKNOWN, True, v.cause, v.part_id,
                               v.probability)
        return ItemOutcome(qid, item, part, "combined", v.value, False, None, v.part_id, v.probability)
    ref_item = combiner.same_part_as(item)
    reference = None
    if ref_item is not None:
        ref_q = next((o for o in by_id.values() if o["item_id"] == ref_item), None)
        ro = outcomes.get(ref_q["question_id"]) if ref_q else None
        reference = ro if ro is not None and ro.state == "combined" else None
    try:
        c = combiner.combine(item, votes, reference=reference)
    except ValueError as exc:
        return _stopped(q, str(exc))
    return ItemOutcome(qid, item, part, "combined", c.value, bool(c.failed), c.cause, c.part_id,
                       c.probability)


def code_page(inp: ActivityPageInput, ask_fn: AskFn, config: ActivityCoderConfig) -> PageActivityResult:
    """Code every activity of one page, in round and gate order (provisional combination)."""
    s = _setup(config)
    page = inp.page
    qsv = s.qset["question_set_version"]
    usable = [sp for sp in inp.spans if span_ok(page, sp)]
    skipped = tuple((sp.activity_id, SPAN_UNRESOLVED) for sp in inp.spans if not span_ok(page, sp))
    if len({sp.activity_id for sp in inp.spans}) != len(inp.spans):
        raise ValueError("duplicate activity_id")
    notes: list[str] = []
    if len(usable) > 1 and not s.qset.get("pair_questions"):
        notes.append(PAIR_QUESTION_MISSING)
    failures: list[PartFailure] = []
    results: list[ActivityResult] = []
    pair_results = []
    pair_questions = list(s.qset.get("pair_questions", []))
    if pair_questions:
        if len(pair_questions) != 1 or pair_questions[0].get("approval") != "approved":
            raise ValueError("activity pair question requires explicit wording approval")
        pq = pair_questions[0]
        planned, ties = plan_pairs(inp)
        notes.extend(f"{PAIR_DIRECTION_TIE}:{a}:{b}" for a, b in ties)
        for pair in planned:
            pr, pf = _code_pair(inp, pair, pq, ask_fn, config, s)
            pair_results.append(pr)
            failures.extend(pf)
    for n, sp in enumerate(usable, start=1):
        label = f"A{n}"
        parts = parts_holding(page, sp.start, sp.end)
        nano = nano_values(sp)
        outcomes: dict[str, ItemOutcome] = {}
        records: list[CoderRecord] = []
        for rnd in s.rounds:
            asked: list[dict[str, Any]] = []
            for q in (q for q in s.questions if q["round"] == rnd):
                kind = _gate_kind(q, s.by_id)
                if kind in ("item", "nano"):
                    open_ = gate_open(q, outcomes, nano, s.by_id)
                    if open_ is None:
                        outcomes[q["question_id"]] = _stopped(q, f"gate item {q['gate']['item']} stopped")
                        continue
                    if not open_:
                        o = _gated(q)
                        outcomes[q["question_id"]] = o
                        records.append(_mechanical(q, o.value, o.rule_reference, config, qsv))
                        continue
                asked.append(q)
            if not asked:
                continue
            show_number = any(NANO_STATE_FIELDS["stated_number"] in (q.get("shows_value_of") or ())
                              for q in asked)
            prior = prior_fields(outcomes, rnd, s)
            votes: dict[str, list[PartVote]] = {q["question_id"]: [] for q in asked}
            for index, chunk in parts:
                state = build_state(inp, chunk, index, sp, label, nano, prior, s.qset,
                                    show_number=show_number)
                years = (year_candidates(page, chunk, sp.start, sp.end, config.reference_year)
                         if any(q.get("dynamic_choices") == "year" for q in asked) else None)
                questions = build_questions(asked, part=len(page.chunks) > 1, years=years)
                qids = tuple(questions)
                reason, detail, result = None, None, None
                try:
                    result = ask_fn(state, questions)
                except JevAccountError:
                    raise
                except Exception as exc:  # noqa: BLE001 - any other failure fails this part only
                    reason, detail = REQUEST_FAILED, f"{type(exc).__name__}: {exc}"
                if result is not None and not (isinstance(result.request_id, str) and result.request_id.strip()):
                    reason, result = MISSING_REQUEST_ID, None
                if result is None:
                    failures.append(PartFailure(reason, sp.activity_id, chunk.chunk_id, rnd, qids, detail))
                    for qid in qids:
                        votes[qid].append(PartVote(chunk.chunk_id, index, UNKNOWN, None, True, reason))
                    continue
                for q in asked:
                    qid = q["question_id"]
                    if qid not in result.answers:
                        failures.append(PartFailure(ANSWER_MISSING, sp.activity_id, chunk.chunk_id, rnd, (qid,)))
                        votes[qid].append(PartVote(chunk.chunk_id, index, UNKNOWN, None, True, ANSWER_MISSING))
                        continue
                    rec = CoderRecord.from_jev(
                        result, question_id=qid, item_id=q["item_id"], item_part=q.get("part"),
                        support_id=None, observation_id=None, chunk_id=chunk.chunk_id,
                        coder_version=config.coder_version, configured_model=config.configured_model,
                        question_set_version=qsv, setup_pointer=config.setup_pointer,
                        classifier_rule=config.rules[(q["item_id"], q.get("part"))])
                    records.append(rec)
                    votes[qid].append(_vote(rec, index))
            for q in asked:
                outcomes[q["question_id"]] = _combine(q, votes[q["question_id"]], config.combiner,
                                                      outcomes, s.by_id)
            for q in asked:  # same-round part gates, after combining
                if _gate_kind(q, s.by_id) == "part":
                    open_ = gate_open(q, outcomes, nano, s.by_id)
                    if open_ is None:
                        outcomes[q["question_id"]] = _stopped(q, "relationship stopped")
                    elif not open_:
                        o = _gated(q)
                        outcomes[q["question_id"]] = o
                        records.append(_mechanical(q, o.value, o.rule_reference, config, qsv))
        results.append(ActivityResult(sp.activity_id, label, sp.start, sp.end,
                                      tuple(c.chunk_id for _, c in parts), tuple(i for i, _ in parts),
                                      outcomes, tuple(records)))
    for pr in pair_results:
        pos = next(i for i, a in enumerate(results) if a.activity_id == pr.activity_id)
        act = results[pos]
        links = dict(act.record_links)
        links.update({len(act.records) + i: pr.linked_activity for i in range(len(pr.records))})
        results[pos] = replace(act, records=act.records + pr.records, record_links=links)
    return PageActivityResult(page.page_id, page.institution_id, tuple(results), skipped,
                              tuple(failures), tuple(notes), qsv, s.qset["codebook_sha256"],
                              config.coder_version, tuple(pair_results))


def _code_pair(inp: ActivityPageInput, pair: ActivityPair, q: dict[str, Any], ask_fn: AskFn,
               config: ActivityCoderConfig, setup: _Setup) -> tuple[PairResult, list[PartFailure]]:
    qid, iid = q["question_id"], q["item_id"]
    if (iid, None) not in config.rules:
        raise ValueError(f"{iid}: no signed classifier rule")
    records, votes, failures = [], [], []
    for index, chunk in pair.parts:
        state = build_state(inp, chunk, index, pair.lhs, pair.lhs_label, nano_values(pair.lhs), {},
                            setup.qset, show_number=False)
        state["page_text"] = marked_pair_text(inp.page, chunk, pair)
        state["activity"] = pair.lhs_label
        state["linked_activity"] = pair.rhs_label
        reason, detail, result = None, None, None
        try:
            result = ask_fn(state, build_questions([q], part=len(inp.page.chunks) > 1))
        except JevAccountError:
            raise
        except Exception as exc:  # noqa: BLE001 - a request failure is a failed part vote
            reason, detail = REQUEST_FAILED, f"{type(exc).__name__}: {exc}"
        if result is not None:
            if not isinstance(result.request_id, str) or not result.request_id.strip():
                reason = MISSING_REQUEST_ID
            elif qid not in result.answers:
                reason = ANSWER_MISSING
        if reason is not None or result is None:
            reason = reason or REQUEST_FAILED
            failures.append(PartFailure(reason, pair.lhs.activity_id, chunk.chunk_id, q["round"],
                                        (qid,), detail, pair.rhs.activity_id))
            votes.append(PartVote(chunk.chunk_id, index, UNKNOWN, None, True, reason))
            continue
        rec = CoderRecord.from_jev(
            result, question_id=qid, item_id=iid, item_part=None, support_id=None,
            observation_id=None, chunk_id=chunk.chunk_id, coder_version=config.coder_version,
            configured_model=config.configured_model,
            question_set_version=setup.qset["question_set_version"], setup_pointer=config.setup_pointer,
            classifier_rule=config.rules[(iid, None)])
        records.append(rec)
        votes.append(_vote(rec, index))
    outcome = _combine(q, votes, config.combiner, {}, {qid: q})
    return PairResult(pair.lhs.activity_id, pair.rhs.activity_id,
                      tuple(c.chunk_id for _, c in pair.parts), tuple(i for i, _ in pair.parts),
                      outcome, tuple(records)), failures


def finalize_pairs(result: PageActivityResult, support: Sequence[Any],
                   config: ActivityCoderConfig) -> tuple[PairResult, ...]:
    """Re-combine pair records after support checks, joining on BOTH activity identities."""
    questions = {q["question_id"]: q for q in _setup(config).qset.get("pair_questions", [])}
    statuses = {}
    for sr in support:
        if sr.item_id not in PAIR_ITEMS:
            continue
        linked = getattr(sr, "linked_activity", None)
        if not linked:
            raise ValueError("pair support result lacks linked_activity")
        key = (sr.activity_id, linked, sr.item_id, sr.chunk_id)
        if key in statuses:
            raise ValueError(f"duplicate pair support result: {key}")
        statuses[key] = sr.support_status
    final = []
    for pair in result.pairs:
        q = questions[pair.outcome.question_id]
        indices = dict(zip(pair.chunk_ids, pair.part_indices, strict=True))
        votes = []
        for rec in pair.records:
            if rec.chosen_value == NOT_COVERED:
                votes.append(_vote(rec, indices[rec.chunk_id]))
                continue
            key = (pair.activity_id, pair.linked_activity, rec.item_id, rec.chunk_id)
            if key not in statuses:
                raise ValueError(f"no support result for pair {key}")
            status = statuses[key]
            down = status.startswith("downgraded_")
            votes.append(_vote(rec, indices[rec.chunk_id], failed=bool(rec.downgraded) or down,
                               cause=rec.downgrade_cause if rec.downgraded else (status if down else None)))
        for failure in result.failures:
            if (failure.activity_id == pair.activity_id and failure.linked_activity == pair.linked_activity
                    and q["question_id"] in failure.question_ids):
                votes.append(PartVote(failure.chunk_id, indices[failure.chunk_id], UNKNOWN, None,
                                      True, failure.reason))
        final.append(replace(pair, outcome=_combine(q, votes, config.combiner, {}, {q["question_id"]: q})))
    return tuple(final)


# ---------------------------------------------------------------------------
# After the support check (PI 2026-11-08 Q2 b): re-combine and re-gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinalActivity:
    """``regated``: asked on the provisional gate, final gate closed (signed gated-out value;
    raw answers stay in the records, unpublished). ``gate_opened``: not asked because the
    provisional gate was closed, final gate open; pending a T-030 extra round."""

    activity_id: str
    outcomes: Mapping[str, ItemOutcome]
    regated: tuple[str, ...] = ()
    gate_opened: tuple[str, ...] = ()


def finalize_activities(result: PageActivityResult, support: Sequence[Any], config: ActivityCoderConfig,
                        nano: Mapping[str, Mapping[str, str]] | None = None) -> tuple[FinalActivity, ...]:
    """Pure: re-combine each activity with the T-024 support results, then re-apply the gates.

    ``support`` items carry ``item_id``, ``part``, ``activity_id``, ``chunk_id`` and
    ``support_status`` (:class:`g3o.common.support_check.SupportResult`). Every jev part
    code other than the temporary answer must have one. A part fails when its record
    failed the 0.8 bar or its status is ``downgraded_*``. ``nano`` gives the extracted
    values per activity id (for the ``any stated`` gate; unchanged by the support check)."""
    s = _setup(config)
    nano = nano or {}
    status: dict[tuple[str, str, str | None, str], str] = {}
    for sr in support:
        if getattr(sr, "activity_id", None) is None:
            continue
        status[(sr.activity_id, sr.item_id, sr.part, sr.chunk_id)] = sr.support_status
    out: list[FinalActivity] = []
    for act in result.activities:
        index = dict(zip(act.chunk_ids, act.part_indices, strict=True))
        fails = [f for f in result.failures if f.activity_id == act.activity_id]
        final: dict[str, ItemOutcome] = {}
        regated: list[str] = []
        opened: list[str] = []
        act_nano = nano.get(act.activity_id, {})
        for rnd in s.rounds:
            rq = [q for q in s.questions if q["round"] == rnd]
            for q in rq:
                qid = q["question_id"]
                prov = act.outcomes.get(qid)
                kind = _gate_kind(q, s.by_id)
                open_ = gate_open(q, final, act_nano, s.by_id) if kind in ("item", "nano") else True
                if prov is None or prov.state != "combined":
                    if prov is not None and prov.state == "gated_out" and open_ is None:
                        final[qid] = _stopped(q, "gate item is pending or stopped after support check")
                        continue
                    if prov is not None and prov.state == "gated_out" and kind != "part" and open_:
                        opened.append(qid)
                        final[qid] = ItemOutcome(qid, q["item_id"], q.get("part"), "pending", None,
                                                 note="requires T-030 extra round after support check")
                        continue
                    if prov is not None:
                        final[qid] = prov
                    continue
                if open_ is None:
                    final[qid] = _stopped(q, f"gate item {q['gate']['item']} stopped")
                    continue
                if not open_:
                    final[qid] = _gated(q, "gate closed after the support check (PI Q2 b)")
                    regated.append(qid)
                    continue
                votes: list[PartVote] = []
                for rec in act.records:
                    if rec.coder_type != "classifier" or rec.question_id != qid:
                        continue
                    if rec.chosen_value == NOT_COVERED:
                        votes.append(_vote(rec, index[rec.chunk_id]))
                        continue
                    st = status.get((act.activity_id, q["item_id"], q.get("part"), rec.chunk_id))
                    if st is None:
                        raise ValueError(f"no support result for {act.activity_id} {qid} in {rec.chunk_id}")
                    bar = bool(rec.downgraded)
                    down = st.startswith("downgraded_")
                    votes.append(_vote(rec, index[rec.chunk_id], failed=bar or down,
                                       cause=rec.downgrade_cause if bar else (st if down else None)))
                # Retain the failure history, but a resumed answer replaces its
                # failed vote. Each current part contributes at most one vote.
                seen = {vote.part_id for vote in votes}
                for f in fails:
                    if qid in f.question_ids and f.chunk_id not in seen:
                        votes.append(PartVote(f.chunk_id, index[f.chunk_id], UNKNOWN, None, True, f.reason))
                        seen.add(f.chunk_id)
                final[qid] = _combine(q, votes, config.combiner, final, s.by_id)
            for q in rq:
                if _gate_kind(q, s.by_id) == "part" and final.get(q["question_id"], None) is not None \
                        and final[q["question_id"]].state == "combined":
                    open_ = gate_open(q, final, act_nano, s.by_id)
                    if open_ is None:
                        final[q["question_id"]] = _stopped(q, "relationship stopped")
                    elif not open_:
                        final[q["question_id"]] = _gated(q, "gate closed after the support check (PI Q2 b)")
                        regated.append(q["question_id"])
        out.append(FinalActivity(act.activity_id, final, tuple(regated), tuple(opened)))
    return tuple(out)


# ---------------------------------------------------------------------------
# T-032 adapter
# ---------------------------------------------------------------------------


def to_pass2_page(result: PageActivityResult, inp: ActivityPageInput) -> Pass2Page:
    """Pass-2 input of the supporting-text call: every part answer of every activity
    (each part's answers are checked before combining, R-044), with ``part`` set on a
    parts item and ``linked_activity`` on a pair item. Unresolved spans pass through
    with no codes (T-032 records them)."""
    by_id = {a.activity_id: a for a in result.activities}
    acts: list[Pass2Activity] = []
    for sp in inp.spans:
        a = by_id.get(sp.activity_id)
        if a is None:
            acts.append(Pass2Activity(sp.activity_id, sp.start, sp.end, ()))
            continue
        codes: list[ActivityCode] = []
        for k, rec in enumerate(a.records):
            if rec.coder_type != "classifier" or rec.chosen_value == NOT_COVERED:
                continue
            codes.append(ActivityCode(rec.item_id, rec.chunk_id, rec.chosen_value, rec.item_part,
                                      a.record_links.get(k)))
        acts.append(Pass2Activity(a.activity_id, a.start, a.end, tuple(codes)))
    return Pass2Page(inp.page, tuple(acts))


__all__ = [
    "ANSWER_MISSING", "CODER_VERSION", "MISSING_REQUEST_ID", "NANO_STATE_FIELDS",
    "PAIR_DIRECTION_TIE", "PAIR_QUESTION_MISSING", "REQUEST_FAILED", "SPAN_UNRESOLVED", "ActivityCoderConfig",
    "ActivityPageInput", "ActivityPair", "ActivityResult", "PairResult", "Combined", "FinalActivity", "ItemOutcome",
    "PageActivityResult", "PartCombiner", "PartFailure", "PartVote", "build_questions",
    "build_state", "code_page", "finalize_activities", "finalize_pairs", "plan_pairs", "marked_pair_text", "gate_open", "marked_part_text",
    "part_combine_adapter", "to_pass2_page", "year_candidates",
]
