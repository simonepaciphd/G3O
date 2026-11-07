"""Finish newly eligible questions after support re-gating (RC-D-024).

These helpers execute only previously unasked questions. They do not replace
the signed coders, combiners, or support check. ``check_support(result, records)``
must obtain and check evidence for exactly those records and return its results.
For activities, records are ``(activity_id, CoderRecord)`` pairs.

``checkpoint(result, support)`` runs after each successful classifier response,
before evidence work, and after checked evidence. Persist both arguments; pass
them back on resume. Already recorded part answers and checked support are not
requested again. The callback owns durable I/O and provider request recovery;
an interruption inside a provider call cannot provide an exactly-once guarantee.

A request failure holds the question pending. ``complete`` is false whenever
any question is pending or stopped: callers MUST refuse final publication.
No new stopping policy or final negative is inferred from an exhausted request.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from g3o.classify import jev_activity_code as activity
from g3o.classify import jev_page_code as page_code
from g3o.common.cost_monitor import BudgetExceededError
from g3o.common.jev_client import JevAccountError
from g3o.common.jev_record import CoderRecord
from g3o.common.part_combine import NOT_COVERED

_PENDING = "extra_round_in_progress"
_HELD = "extra_round_failed:"
Checkpoint = Callable[[Any, tuple[Any, ...]], None]


@dataclass(frozen=True)
class PageRoundResult:
    result: page_code.PageCodeResult
    final: page_code.FinalPage
    support: tuple[Any, ...]
    rounds: int

    @property
    def complete(self) -> bool:
        return all(o.state not in ("pending", "stopped") for o in self.final.items.values())


@dataclass(frozen=True)
class ActivityRoundResult:
    result: activity.PageActivityResult
    final: tuple[activity.FinalActivity, ...]
    support: tuple[Any, ...]
    rounds: int

    @property
    def complete(self) -> bool:
        return all(o.state not in ("pending", "stopped")
                   for a in self.final for o in a.outcomes.values())


def _retryable(note: str | None) -> bool:
    # A recorded failure is still unfinished work, including on a later resume.
    return note == _PENDING or (isinstance(note, str) and note.startswith(_HELD))

def _save(checkpoint: Checkpoint | None, result: Any, support: tuple[Any, ...]) -> None:
    if checkpoint is not None:
        checkpoint(result, support)


def _key(sr: Any) -> tuple[Any, ...]:
    return (getattr(sr, "activity_id", None), sr.item_id,
            getattr(sr, "part", None), sr.chunk_id, getattr(sr, "linked_activity", None))


def _record_key(aid: str | None, rec: CoderRecord) -> tuple[Any, ...]:
    return (aid, rec.item_id, rec.item_part, rec.chunk_id, None)


def _checked(result: Any, support: tuple[Any, ...], records: Sequence[tuple[str | None, CoderRecord]],
             check_support: Callable[..., Sequence[Any]], checkpoint: Checkpoint | None,
             *, is_activity: bool) -> tuple[Any, ...]:
    keys = [_key(sr) for sr in support]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate support identity")
    present = set(keys)
    missing = tuple((aid, rec) for aid, rec in records
                    if rec.coder_type == "classifier" and rec.chosen_value != NOT_COVERED
                    and _record_key(aid, rec) not in present)
    if not missing:
        return support
    supplied = tuple(check_support(result, missing if is_activity else tuple(r for _, r in missing)))
    got = [_key(sr) for sr in supplied]
    expected = {_record_key(aid, rec) for aid, rec in missing}
    if len(got) != len(set(got)) or set(got) != expected:
        raise ValueError("support callback must return exactly the requested answer identities")
    support += supplied
    _save(checkpoint, result, support)
    return support


def complete_page_rounds(page: page_code.PageInput, result: page_code.PageCodeResult,
                         support: Sequence[Any], *, ask_fn: page_code.AskFn,
                         config: page_code.PageCoderConfig,
                         check_support: Callable[..., Sequence[Any]],
                         checkpoint: Checkpoint | None = None) -> PageRoundResult:
    """Ask/check newly opened page questions, bounded by the signed question graph.

    A partial extra question is identified by its pending outcome and retained
    records. Resume sends only missing chunk answers. Earlier answers, including
    historical gated-out mechanical records, remain byte-for-byte unchanged.
    """
    if (page.page_id, page.institution_id, page.url) != (result.page_id, result.institution_id, result.url):
        raise ValueError("page identity differs from coding result")
    setup = page_code._setup(config)
    if result.codebook_sha256 != setup.qset["codebook_sha256"]:
        raise ValueError("page result and question set differ")
    _binding(result.records, config.setup_pointer)
    support = tuple(support)
    rounds = 0
    # Each pass adds one formerly unasked question; ancestors are immutable.
    for _ in range(len(setup.questions) + 1):
        partial = [q for q in setup.questions if _retryable(result.items[q["item_id"]].note)]
        if not partial:
            support = _checked(result, support, [(None, r) for r in result.records],
                               check_support, checkpoint, is_activity=False)
        final = page_code.finalize_page(result, support, config)
        candidates = partial or [q for q in setup.questions
                                 if q["item_id"] in final.gate_opened]
        if not candidates:
            return PageRoundResult(result, final, support, rounds)
        q = min(candidates, key=lambda q: q["round"])
        iid = q["item_id"]
        items = dict(result.items)
        items[iid] = page_code.ItemOutcome(iid, "pending", None, note=_PENDING)
        result = replace(result, items=items)
        for index, chunk in enumerate(result.chunks, start=1):
            if any(r.coder_type == "classifier" and r.item_id == iid and r.chunk_id == chunk.chunk_id
                   for r in result.records):
                continue
            state = page_code.build_state(page, chunk, index, len(result.chunks), setup.qset,
                                          chrome=iid in setup.chrome_ids and page_code._chrome_sent(page))
            questions = page_code.build_questions([q], part=len(result.chunks) > 1)
            try:
                size = config.estimator.tokens(page_code.serialize_request(state, questions))
                if size > config.limit_tokens - config.reserved_tokens:
                    raise ValueError("extra question exceeds existing part layout")
                response = ask_fn(state, questions)
                rec = _answer(response, q, chunk.chunk_id, config, setup.qset["question_set_version"])
            except (JevAccountError, BudgetExceededError):
                raise
            except Exception as exc:
                items[iid] = replace(items[iid], note=_HELD + str(exc))
                result = replace(result, items=dict(items), failures=result.failures + ({
                    "chunk_id": chunk.chunk_id, "round": q["round"], "group": "extra",
                    "question_ids": [q["question_id"]], "reason": "extra_round_failed",
                    "detail": f"{type(exc).__name__}: {exc}",
                },))
                _save(checkpoint, result, support)
                return PageRoundResult(result, page_code.finalize_page(result, support, config), support, rounds)
            result = replace(result, records=result.records + (rec,), requests=result.requests + ({
                "chunk_id": chunk.chunk_id, "round": q["round"], "group": "extra",
                "question_ids": [q["question_id"]], "page_part": state["page_part"],
                "request_id": response.request_id, "response_model": response.response_model,
                "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
                "outcome": "ok",
            },))
            _save(checkpoint, result, support)
        indices = {c.chunk_id: i for i, c in enumerate(result.chunks, 1)}
        records = [r for r in result.records if r.coder_type == "classifier" and r.item_id == iid]
        items[iid] = page_code._combine(setup.combine_rules[iid],
                                        [page_code.part_answer(r, indices[r.chunk_id]) for r in records])
        result = replace(result, items=dict(items))
        _save(checkpoint, result, support)
        rounds += 1
    raise ValueError("question graph did not make finite progress")


def _binding(records: Sequence[CoderRecord], setup_pointer: str) -> None:
    if any(r.setup_pointer != setup_pointer for r in records):
        raise ValueError("coding result belongs to a different instrument")


def _answer(response: Any, q: dict[str, Any], chunk_id: str, config: Any, qsv: str) -> CoderRecord:
    if not isinstance(response.request_id, str) or not response.request_id.strip():
        raise ValueError("extra question response lacks request id")
    if q["question_id"] not in response.answers:
        raise ValueError("extra question response lacks answer")
    return CoderRecord.from_jev(
        response, question_id=q["question_id"], item_id=q["item_id"], item_part=q.get("part"),
        support_id=None, observation_id=None, chunk_id=chunk_id, coder_version=config.coder_version,
        configured_model=config.configured_model, question_set_version=qsv,
        setup_pointer=config.setup_pointer, classifier_rule=config.rules[(q["item_id"], q.get("part"))])


def complete_activity_rounds(inp: activity.ActivityPageInput, result: activity.PageActivityResult,
                             support: Sequence[Any], *, ask_fn: activity.AskFn,
                             config: activity.ActivityCoderConfig,
                             check_support: Callable[..., Sequence[Any]],
                             checkpoint: Checkpoint | None = None) -> ActivityRoundResult:
    """Activity counterpart; pair requests/records are retained, never reissued.

    Pair support/finalization remains the caller's responsibility through
    ``finalize_pairs``. This helper returns only ordinary activity finalization.
    """
    if (inp.page.page_id, inp.page.institution_id) != (result.page_id, result.institution_id):
        raise ValueError("activity page identity differs from coding result")
    setup = activity._setup(config)
    if result.codebook_sha256 != setup.qset["codebook_sha256"]:
        raise ValueError("activity result and question set differ")
    for act in result.activities:
        _binding(act.records, config.setup_pointer)
    spans = {s.activity_id: s for s in inp.spans}
    nano = {aid: activity.nano_values(sp) for aid, sp in spans.items()}
    support = tuple(support)
    rounds = 0
    for _ in range(len(setup.questions) * len(result.activities) + 1):
        partial = [(a.activity_id, q) for a in result.activities for q in setup.questions
                   if a.outcomes.get(q["question_id"]) is not None
                   and _retryable(a.outcomes[q["question_id"]].note)]
        if not partial:
            records = [(a.activity_id, r) for a in result.activities for r in a.records
                       if r.item_id not in activity.PAIR_ITEMS]
            support = _checked(result, support, records, check_support, checkpoint, is_activity=True)
        final = activity.finalize_activities(result, support, config, nano)
        candidates = partial or [(a.activity_id, q) for a in final for q in setup.questions
                                 if q["question_id"] in a.gate_opened]
        if not candidates:
            return ActivityRoundResult(result, final, support, rounds)
        aid, q = min(candidates, key=lambda pair: pair[1]["round"])
        pos = next(i for i, a in enumerate(result.activities) if a.activity_id == aid)
        act = result.activities[pos]
        qid = q["question_id"]
        outcomes = dict(act.outcomes)
        outcomes[qid] = activity.ItemOutcome(qid, q["item_id"], q.get("part"), "pending", None, note=_PENDING)
        act = replace(act, outcomes=outcomes)
        result = _put_activity(result, pos, act)
        final_outcomes = next(a.outcomes for a in final if a.activity_id == aid)
        prior = activity.prior_fields(final_outcomes, q["round"], setup)
        sp = spans[aid]
        for index, chunk in activity.parts_holding(inp.page, sp.start, sp.end):
            if any(r.coder_type == "classifier" and r.question_id == qid and r.chunk_id == chunk.chunk_id
                   for r in act.records):
                continue
            show_number = activity.NANO_STATE_FIELDS["stated_number"] in (q.get("shows_value_of") or ())
            state = activity.build_state(inp, chunk, index, sp, act.label, nano[aid], prior,
                                         setup.qset, show_number=show_number)
            years = (activity.year_candidates(inp.page, chunk, sp.start, sp.end, config.reference_year)
                     if q.get("dynamic_choices") == "year" else None)
            questions = activity.build_questions([q], part=len(inp.page.chunks) > 1, years=years)
            try:
                response = ask_fn(state, questions)
                rec = _answer(response, q, chunk.chunk_id, config, setup.qset["question_set_version"])
            except (JevAccountError, BudgetExceededError):
                raise
            except Exception as exc:
                outcomes[qid] = replace(outcomes[qid], note=_HELD + str(exc))
                act = replace(act, outcomes=dict(outcomes))
                result = replace(_put_activity(result, pos, act), failures=result.failures + (
                    activity.PartFailure("extra_round_failed", aid, chunk.chunk_id, q["round"],
                                         (qid,), f"{type(exc).__name__}: {exc}"),))
                _save(checkpoint, result, support)
                return ActivityRoundResult(result, activity.finalize_activities(result, support, config, nano),
                                           support, rounds)
            act = replace(act, records=act.records + (rec,))
            result = _put_activity(result, pos, act)
            _save(checkpoint, result, support)
        indices = dict(zip(act.chunk_ids, act.part_indices, strict=True))
        records = [r for r in act.records if r.coder_type == "classifier" and r.question_id == qid]
        outcomes[qid] = activity._combine(q, [activity._vote(r, indices[r.chunk_id]) for r in records],
                                           config.combiner, final_outcomes, setup.by_id)
        result = _put_activity(result, pos, replace(act, outcomes=dict(outcomes)))
        _save(checkpoint, result, support)
        rounds += 1
    raise ValueError("question graph did not make finite progress")


def _put_activity(result: activity.PageActivityResult, pos: int,
                  act: activity.ActivityResult) -> activity.PageActivityResult:
    activities = list(result.activities)
    activities[pos] = act
    return replace(result, activities=tuple(activities))
