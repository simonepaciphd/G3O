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

Exception (RC-D-024 item 9, lane D reading 5): an activity part rejected as
over the token limit in an extra round is not halved and not retried. It is
recorded as a failed part vote (``PartFailure`` reason ``jev_request_failed``,
over-limit detail), exactly as the first-round activity coder records a
failed request, and the question is combined from its votes. A resume never
sends that part again.

Page halving in extra rounds (RC-D-023 B-Q6, RC-D-024 item 6). A page part
over the token limit for an extra question (by the request estimate, or
jev's ``max_tokens_exceeded``) is halved, as in first rounds: its records
move to ``superseded`` and every request the part had answered before (first
rounds and earlier extra rounds, same question groups) is asked again on each
half before the extra question. Halves get new i-of-n labels; untouched parts
keep their answers and are not asked again. A part at the depth limit (or too
short to halve) records ``jev_part_over_limit`` for the request, a failed part
vote, never resent. The halving and its re-ask plan are logged in
``requests`` (``outcome: halved``), so a resume finishes the owed re-asks.
Any other failure of a re-ask holds the question pending, as above.

After a halving, the re-asked items are re-combined provisionally (0.8 bar,
as in first rounds) and the final gates are re-applied by
:func:`~g3o.classify.jev_page_code.finalize_page` (PI Q2 b / item 4 b). When
this changes the provisional verdict or ``core.page_complete``, the page
continues on the re-combined values while the stored first-round extractor
request (planned on the earlier value: its activity and link tasks) is kept
and never asked again (PI ruling 68 b); the change is logged in ``requests``
(``outcome`` :data:`PLAN_KEPT`). One case the signed rules do not settle stops
the page instead (``stopped``, error :data:`HALVING_STOP`; open PI question,
no further request): failed verdict parts reach 75% of the new leaf layout
after the page was coded.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from g3o.classify import jev_activity_code as activity
from g3o.classify import jev_page_code as page_code
from g3o.common import part_combine as pcomb
from g3o.common.cost_monitor import BudgetExceededError
from g3o.common.jev_client import JevAccountError
from g3o.common.jev_record import CoderRecord
from g3o.common.page_chunks import halve_chunk
from g3o.common.part_combine import NOT_COVERED
from g3o.validate.jev_validate import is_max_tokens_exceeded

_PENDING = "extra_round_in_progress"
_HELD = "extra_round_failed:"
_OVER_LIMIT = "over_limit, not halved (RC-D-024 item 9): "
#: Error prefix of an extra page question stopped after a halving (open PI question).
HALVING_STOP = "halving_stopped (open PI question): "
HALVED = "halved"
HALVING_STOPPED = "extra_round_halving_stopped"
#: ``requests`` log outcome: a halving changed the provisional verdict or ``core.page_complete``
#: and the stored first-round extractor plan was kept (PI ruling 68 b; no request is made).
PLAN_KEPT = "provisional_changed_first_round_plan_kept"
#: Page part failures that are a final failed vote (first-round reasons and the depth limit).
_FINAL_FAILURES = frozenset({page_code.REQUEST_FAILED, page_code.MISSING_REQUEST_ID,
                             page_code.ANSWER_MISSING, page_code.OVER_LIMIT})
_GROUP_ORDER = {page_code.GROUP_MAIN: 0, page_code.GROUP_CHROME: 1, "extra": 2}
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
    historical gated-out mechanical records, remain byte-for-byte unchanged,
    except that a halved part's records move to ``superseded`` (module docstring).
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
        if _halving_stopped(result):  # open PI question: nothing more is asked
            return PageRoundResult(result, _final(result, support, config), support, rounds)
        partial = [q for q in setup.questions if _retryable(result.items[q["item_id"]].note)]
        if not partial:
            support = _checked(result, support, [(None, r) for r in result.records],
                               check_support, checkpoint, is_activity=False)
        final = _final(result, support, config)
        candidates = partial or [q for q in setup.questions
                                 if q["item_id"] in final.gate_opened]
        if not candidates:
            return PageRoundResult(result, final, support, rounds)
        q = min(candidates, key=lambda q: q["round"])
        iid = q["item_id"]
        items = dict(result.items)
        items[iid] = page_code.ItemOutcome(iid, "pending", None, note=_PENDING)
        result = replace(result, items=items)
        own: _Group = (q["round"], "extra", (q["question_id"],))
        pos = 0
        while pos < len(result.chunks):  # the layout grows when a part is halved
            chunk = result.chunks[pos]
            sent = None
            for group in [*_owed(result, chunk.chunk_id, setup), own]:
                outcome, result = _send_group(page, result, pos, group, own, setup, ask_fn, config,
                                              checkpoint, support)
                if outcome == "held":
                    return PageRoundResult(result, _final(result, support, config),
                                           support, rounds)
                if outcome == HALVED:
                    sent = HALVED
                    break
            if sent != HALVED:
                pos += 1  # a halved part is replaced in place: its first half is at ``pos``
        items = dict(result.items)
        items[iid] = _provisional(result, setup, iid)
        if _halvings(result):
            items, stop = _recombine_after_halving(result, setup, items, iid)
            if stop is not None:
                items = dict(result.items)
                items[iid] = page_code.ItemOutcome(iid, "stopped", None, error=HALVING_STOP + stop)
                result = replace(result, items=items, failures=result.failures + ({
                    "chunk_id": None, "round": q["round"], "group": "extra",
                    "question_ids": [q["question_id"]], "reason": HALVING_STOPPED, "detail": stop,
                },))
                _save(checkpoint, result, support)
                return PageRoundResult(result, _final(result, support, config), support, rounds)
            result = replace(result, requests=result.requests + _first_round_plan_kept(result, items, q))
        result = replace(result, items=items)
        _save(checkpoint, result, support)
        rounds += 1
    raise ValueError("question graph did not make finite progress")


# ---------------------------------------------------------------------------
# Page halving in extra rounds (RC-D-023 B-Q6, RC-D-024 item 6)
# ---------------------------------------------------------------------------

#: One request on one part: (round, group, question ids in set order).
_Group = tuple[int, str, tuple[str, ...]]


def _final(result: page_code.PageCodeResult, support: Sequence[Any],
           config: page_code.PageCoderConfig) -> page_code.FinalPage:
    """:func:`~g3o.classify.jev_page_code.finalize_page`, with any combined item whose new part
    answers (re-asked on halves) are not support-checked yet shown as pending.

    Only an unfinished page (held, stopped, or mid-question) has such answers; the
    support check runs once the question in progress is combined. Identical to
    ``finalize_page`` when every answer is checked."""
    checked = {(sr.item_id, sr.chunk_id) for sr in support if getattr(sr, "activity_id", None) is None}
    unchecked = {r.item_id for r in result.records if r.coder_type == "classifier"
                 and r.chosen_value != NOT_COVERED and (r.item_id, r.chunk_id) not in checked}
    owed = {k for k in unchecked if result.items[k].state == "combined"}
    if owed:
        items = dict(result.items)
        for k in owed:
            items[k] = page_code.ItemOutcome(k, "pending", None, note="support check owed after halving")
        result = replace(result, items=items)
    return page_code.finalize_page(result, support, config)


def extra_round_started(result: page_code.PageCodeResult) -> bool:
    """Whether any RC-D-024 extra-round request was made or attempted on this page.

    Before that, a support check of the page's codes is its first round (the T-022
    page request); after it, every support check is an extra round (C1 a, ruling 46 a),
    even when halving left every live answer unchecked."""
    return any(e.get("group") == "extra" for e in (*result.requests, *result.failures))


def _halving_stopped(result: page_code.PageCodeResult) -> bool:
    return any(o.state == "stopped" and (o.error or "").startswith(HALVING_STOP) for o in result.items.values())


def _halvings(result: page_code.PageCodeResult) -> list[dict[str, Any]]:
    return [e for e in result.requests if e.get("outcome") == HALVED]


def _has_record(result: page_code.PageCodeResult, chunk_id: str, qid: str) -> bool:
    return any(r.coder_type == "classifier" and r.question_id == qid and r.chunk_id == chunk_id
               for r in result.records)


def _over_limit_final(result: page_code.PageCodeResult, chunk_id: str, qid: str) -> bool:
    return any(f["reason"] == page_code.OVER_LIMIT and f["chunk_id"] == chunk_id and qid in f["question_ids"]
               for f in result.failures)


def _done(result: page_code.PageCodeResult, chunk_id: str, group: _Group) -> bool:
    return all(_has_record(result, chunk_id, qid) or _over_limit_final(result, chunk_id, qid)
               for qid in group[2])


def _owed(result: page_code.PageCodeResult, chunk_id: str, setup: Any) -> list[_Group]:
    """Re-asks still owed on a half: its parent's request groups not yet answered on it."""
    plan: list[_Group] = []
    for e in _halvings(result):
        if chunk_id in e["halves"]:
            plan.extend((g["round"], g["group"], tuple(g["question_ids"])) for g in e["reask"])
    return [g for g in _ordered(plan, setup) if not _done(result, chunk_id, g)]


def _ordered(groups: Sequence[_Group], setup: Any) -> list[_Group]:
    order = {q["question_id"]: i for i, q in enumerate(setup.questions)}
    unique = {(r, g, tuple(sorted(qids, key=order.__getitem__))) for r, g, qids in groups}
    return sorted(unique, key=lambda x: (x[0], _GROUP_ORDER[x[1]], [order[qid] for qid in x[2]]))


def _part_plan(result: page_code.PageCodeResult, chunk_id: str, page: page_code.PageInput,
               setup: Any, own: _Group) -> list[_Group]:
    """Every request the part answered (or still owes), in the groups it was asked in.

    First-round questions go in their round's main or chrome request (the same
    question set went to every part, ``_groups``); extra-round questions each
    have their own request. Transient holds (``extra_round_failed``) are not
    answers. ``own`` (the current extra question) is left out: the caller asks
    it on every part after the re-asks.
    """
    extra = {qid for e in result.requests if e.get("group") == "extra" for qid in e["question_ids"]}
    extra |= {qid for f in result.failures if f.get("group") == "extra" for qid in f["question_ids"]}
    asked = {r.question_id for r in result.records if r.coder_type == "classifier" and r.chunk_id == chunk_id}
    asked |= {qid for f in result.failures if f["chunk_id"] == chunk_id and f["reason"] in _FINAL_FAILURES
              for qid in f["question_ids"]}
    chrome = page_code._chrome_sent(page)
    first: dict[tuple[int, str], list[str]] = {}
    plan: list[_Group] = []
    for qid in asked:
        rnd = setup.by_id[qid]["round"]
        if qid in extra:
            plan.append((rnd, "extra", (qid,)))
        else:
            group = page_code.GROUP_CHROME if chrome and qid in setup.chrome_ids else page_code.GROUP_MAIN
            first.setdefault((rnd, group), []).append(qid)
    plan.extend((rnd, group, tuple(qids)) for (rnd, group), qids in first.items())
    plan.extend(_owed(result, chunk_id, setup))
    return [g for g in _ordered(plan, setup) if g != own]


def _send_group(page: page_code.PageInput, result: page_code.PageCodeResult, pos: int, group: _Group,
                own: _Group, setup: Any, ask_fn: page_code.AskFn, config: page_code.PageCoderConfig,
                checkpoint: Checkpoint | None, support: tuple[Any, ...]
                ) -> tuple[str, page_code.PageCodeResult]:
    """Ask one request on ``result.chunks[pos]``: ``"ok"`` (answered, or already final),
    ``"halved"`` (the part was replaced by its halves) or ``"held"`` (pending).

    ``own`` is the current extra question's request; any other ``group`` is a re-ask."""
    chunk = result.chunks[pos]
    rnd, gname, qids = group
    if _done(result, chunk.chunk_id, group):
        return "ok", result
    qs = [setup.by_id[qid] for qid in qids]
    n = len(result.chunks)
    state = page_code.build_state(page, chunk, pos + 1, n, setup.qset,
                                  chrome=page_code._chrome_sent(page) and any(q in setup.chrome_ids for q in qids))
    questions = page_code.build_questions(qs, part=n > 1)
    log = {"chunk_id": chunk.chunk_id, "round": rnd, "group": gname, "question_ids": list(qids),
           "page_part": state["page_part"]}
    if group != own:
        log["reasked"] = True
    size = config.estimator.tokens(page_code.serialize_request(state, questions))
    if size > config.limit_tokens - config.reserved_tokens:
        return _over_limit(page, result, pos, group, own, setup, config, checkpoint, support,
                           {**log, "outcome": "over_limit", "estimated_tokens": size})
    over: str | None = None
    response = None
    try:
        response = ask_fn(state, questions)
        recs = [_answer(response, q, chunk.chunk_id, config, setup.qset["question_set_version"]) for q in qs]
    except (JevAccountError, BudgetExceededError):
        raise
    except Exception as exc:
        if not is_max_tokens_exceeded(exc):
            if response is not None:  # billed but unusable (no answer / no request id): logged, then held
                result = replace(result, requests=result.requests + ({
                    **log, "request_id": response.request_id, "response_model": response.response_model,
                    "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
                    "outcome": "extra_round_failed",
                },))
            return "held", _hold(result, setup, own, group, chunk.chunk_id, exc, checkpoint, support)
        over = f"{type(exc).__name__}: {exc}"
    if over is not None:
        return _over_limit(page, result, pos, group, own, setup, config, checkpoint, support,
                           {**log, "outcome": "over_limit", "detail": over})
    result = replace(result, records=result.records + tuple(recs), requests=result.requests + ({
        **log, "request_id": response.request_id, "response_model": response.response_model,
        "input_tokens": response.input_tokens, "output_tokens": response.output_tokens, "outcome": "ok",
    },))
    _save(checkpoint, result, support)
    return "ok", result


def _hold(result: page_code.PageCodeResult, setup: Any, own: _Group, group: _Group, chunk_id: str,
          exc: Exception, checkpoint: Checkpoint | None, support: tuple[Any, ...]) -> page_code.PageCodeResult:
    """Any non-over-limit failure (re-asks included) holds the current question pending."""
    rnd, gname, qids = group
    items = dict(result.items)
    iid = setup.by_id[own[2][0]]["item_id"]
    items[iid] = replace(items[iid], note=_HELD + str(exc))
    result = replace(result, items=items, failures=result.failures + ({
        "chunk_id": chunk_id, "round": rnd, "group": gname, "question_ids": list(qids),
        "reason": "extra_round_failed", "detail": f"{type(exc).__name__}: {exc}",
    },))
    _save(checkpoint, result, support)
    return result


def _over_limit(page: page_code.PageInput, result: page_code.PageCodeResult, pos: int, group: _Group,
                own: _Group, setup: Any, config: page_code.PageCoderConfig, checkpoint: Checkpoint | None,
                support: tuple[Any, ...], log: dict[str, Any]) -> tuple[str, page_code.PageCodeResult]:
    """Halve the part (B-Q6) or, at the depth limit, record ``jev_part_over_limit`` (never resent).

    The halves owe every request the part answered or still owed (a re-ask that was
    itself over the limit included); the current extra question follows on each."""
    chunk = result.chunks[pos]
    rnd, gname, qids = group
    halves = None if chunk.depth >= config.max_split_depth else halve_chunk(chunk, estimator=config.estimator)
    requests = result.requests + (log,)
    if halves is None:
        # as the first round logs an exhausted part: the request outcome ``jev_part_over_limit``
        requests += ({**{k: v for k, v in log.items() if k != "detail"}, "outcome": page_code.OVER_LIMIT},)
        result = replace(result, requests=requests, failures=result.failures + ({
            "chunk_id": chunk.chunk_id, "round": rnd, "group": gname, "question_ids": list(qids),
            "reason": page_code.OVER_LIMIT, "detail": "part cannot be halved further",
        },))
        _save(checkpoint, result, support)
        return "ok", result
    plan = _part_plan(result, chunk.chunk_id, page, setup, own)
    chunks = list(result.chunks)
    chunks[pos:pos + 1] = list(halves)
    moved = tuple(r for r in result.records if r.coder_type == "classifier" and r.chunk_id == chunk.chunk_id)
    kept = tuple(r for r in result.records if not (r.coder_type == "classifier" and r.chunk_id == chunk.chunk_id))
    result = replace(result, chunks=tuple(chunks), records=kept, superseded=result.superseded + moved,
                     requests=requests + ({
                         "chunk_id": chunk.chunk_id, "round": rnd, "group": gname, "question_ids": list(qids),
                         "outcome": HALVED, "halves": [h.chunk_id for h in halves],
                         "reask": [{"round": r, "group": g, "question_ids": list(x)} for r, g, x in plan],
                     },))
    _save(checkpoint, result, support)
    return HALVED, result


def _provisional(result: page_code.PageCodeResult, setup: Any, iid: str) -> page_code.ItemOutcome:
    """The item's combination over the live parts, as the first-round coder combines a round:
    records on the 0.8 bar, final part failures as failed votes (none for the verdict)."""
    index = {c.chunk_id: i for i, c in enumerate(result.chunks, 1)}
    answers = [page_code.part_answer(r, index[r.chunk_id]) for r in result.records
               if r.coder_type == "classifier" and r.item_id == iid]
    seen = {a.part_id for a in answers}
    if iid != page_code.VERDICT:
        for f in result.failures:
            cid = f["chunk_id"]
            if (f["reason"] in _FINAL_FAILURES and cid in index and cid not in seen
                    and any(setup.by_id[qid]["item_id"] == iid for qid in f["question_ids"])):
                answers.append(pcomb.PartAnswer(cid, index[cid], pcomb.UNKNOWN, None, failed=True,
                                                cause=f["reason"]))
                seen.add(cid)
    answers.sort(key=lambda a: a.part_index)
    return page_code._combine(setup.combine_rules[iid], answers)


def _recombine_after_halving(result: page_code.PageCodeResult, setup: Any,
                             items: dict[str, page_code.ItemOutcome], iid: str
                             ) -> tuple[dict[str, page_code.ItemOutcome], str | None]:
    """Re-combine every re-asked item; return the stop reason for the unruled cases."""
    n = len(result.chunks)
    live = {c.chunk_id for c in result.chunks}
    verdict_records = {r.chunk_id for r in result.records
                       if r.coder_type == "classifier" and r.item_id == page_code.VERDICT}
    failed = {f["chunk_id"] for f in result.failures
              if f["reason"] in _FINAL_FAILURES and f["chunk_id"] in live and f["chunk_id"] not in verdict_records
              and page_code.VERDICT in f["question_ids"]}
    if 4 * len(failed) >= 3 * n:
        return items, (f"{len(failed)}/{n} verdict parts failed (at least 75%) on the layout halved in an "
                       "extra round, after the page was coded")
    reasked = {setup.by_id[qid]["item_id"] for e in _halvings(result) for g in e["reask"]
               for qid in g["question_ids"]}
    out = dict(items)
    for item in sorted(reasked - {iid}):
        before = result.items[item]
        if before.state not in ("combined", "stopped"):
            continue
        out[item] = _provisional(result, setup, item)
    return out, None


def _first_round_plan_kept(result: page_code.PageCodeResult, items: dict[str, page_code.ItemOutcome],
                           q: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Log entries for a provisional verdict or ``core.page_complete`` that a halving changed.

    PI ruling 68 b: the page continues on the re-combined items (finalize_page re-gates);
    the stored first-round extractor request (its activity and link tasks), planned on the
    earlier value, is kept and not asked again. The entries record the change; no request
    is made for them (``outcome`` :data:`PLAN_KEPT`, no ``group``)."""
    out = []
    for item in (page_code.VERDICT, page_code.COMPLETE):
        before, after = result.items.get(item), items.get(item)
        if before is None or after is None or (before.state, before.value) == (after.state, after.value):
            continue
        out.append({"chunk_id": None, "round": q["round"], "question_ids": [q["question_id"]],
                    "outcome": PLAN_KEPT, "item_id": item,
                    "before": {"state": before.state, "value": before.value},
                    "after": {"state": after.state, "value": after.value}})
    return tuple(out)


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
            if any(_failed_vote(f, aid, qid, chunk.chunk_id) for f in result.failures):
                continue  # over-limit failed part vote: final, never resent
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
                if is_max_tokens_exceeded(exc):
                    result = replace(result, failures=result.failures + (
                        activity.PartFailure(activity.REQUEST_FAILED, aid, chunk.chunk_id, q["round"],
                                             (qid,), f"{_OVER_LIMIT}{type(exc).__name__}: {exc}"),))
                    _save(checkpoint, result, support)
                    continue
                outcomes[qid] = replace(outcomes[qid], note=_HELD + str(exc))
                act = replace(act, outcomes=dict(outcomes))
                result = replace(_put_activity(result, pos, act), failures=result.failures + (
                    activity.PartFailure(activity.EXTRA_ROUND_FAILED, aid, chunk.chunk_id, q["round"],
                                         (qid,), f"{type(exc).__name__}: {exc}"),))
                _save(checkpoint, result, support)
                return ActivityRoundResult(result, activity.finalize_activities(result, support, config, nano),
                                           support, rounds)
            act = replace(act, records=act.records + (rec,))
            result = _put_activity(result, pos, act)
            _save(checkpoint, result, support)
        indices = dict(zip(act.chunk_ids, act.part_indices, strict=True))
        records = [r for r in act.records if r.coder_type == "classifier" and r.question_id == qid]
        votes = [activity._vote(r, indices[r.chunk_id]) for r in records]
        # Failed part votes, built as the first-round coder and finalize_activities build them,
        # from the over-limit REQUEST_FAILED failures only: an earlier extra_round_failed hold on
        # the same part (a transient failure before a resume) is history, not this part's vote.
        seen = {v.part_id for v in votes}
        for f in result.failures:
            if _failed_vote(f, aid, qid, f.chunk_id) and f.chunk_id not in seen:
                votes.append(activity.PartVote(f.chunk_id, indices[f.chunk_id], activity.UNKNOWN,
                                               None, True, f.reason))
                seen.add(f.chunk_id)
        outcomes[qid] = activity._combine(q, votes, config.combiner, final_outcomes, setup.by_id)
        result = _put_activity(result, pos, replace(act, outcomes=dict(outcomes)))
        _save(checkpoint, result, support)
        rounds += 1
    raise ValueError("question graph did not make finite progress")


def _failed_vote(f: activity.PartFailure, aid: str, qid: str, chunk_id: str) -> bool:
    return (f.reason == activity.REQUEST_FAILED and f.activity_id == aid and f.chunk_id == chunk_id
            and f.linked_activity is None and qid in f.question_ids)


def _put_activity(result: activity.PageActivityResult, pos: int,
                  act: activity.ActivityResult) -> activity.PageActivityResult:
    activities = list(result.activities)
    activities[pos] = act
    return replace(result, activities=tuple(activities))
