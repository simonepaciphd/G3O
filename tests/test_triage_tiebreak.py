"""Stage 3 tie-break — order-invariant 'keep wins' (work order item 4, decision 2).

When the model echoes conflicting keep/drop decisions for the *same* candidate
URL, ``keep`` must always win, and the salvaged ``kept_urls`` must be identical
no matter what order those decisions arrive in. Every such conflict must be
recorded in the attrition ledger (as a ``duplicate_url`` casualty whose
``detail`` marks it a keep/drop conflict).

The first test below (:func:`test_conflict_tiebreak_is_order_invariant`) is the
red test: it reproduces the current *order-dependent* positional-winner
behaviour and fails until the keep-wins fix lands.

Also covers the Inclusion #3/#4 input guards at ``build_triage_job``: empty or
whitespace-only candidate URLs are rejected.

Unit-level fixtures (operating on :func:`match_triage_decisions` directly)
because the tie-break lives in the matcher, not the persistence path already
covered by ``tests/test_triage_salvage.py``.
"""

from __future__ import annotations

import itertools

import pytest

from g3o.classify.url_triage import (
    URLDecision,
    URLTriageResult,
    build_triage_job,
    match_triage_decisions,
)

P0 = "https://inst.gov/p0"
P1 = "https://inst.gov/p1"
P2 = "https://inst.gov/p2"


def _dec(url: str, decision: str, rationale: str = "r") -> URLDecision:
    return URLDecision(url=url, decision=decision, rationale=rationale)


def _match(candidates: list[str], decisions: list[URLDecision]):
    return match_triage_decisions(candidates, URLTriageResult(decisions=decisions))


# ---------------------------------------------------------------------------
# Tie-break: keep wins, order-invariant
# ---------------------------------------------------------------------------


def test_conflict_tiebreak_is_order_invariant() -> None:
    """RED under positional logic: a keep/drop conflict for one URL resolves to
    whichever decision the positional winner happens to be, so swapping the two
    decisions flips ``kept_urls``. After the fix, keep wins in both orders."""
    candidates = [P0]
    keep_first = _match(candidates, [_dec(P0, "keep"), _dec(P0, "drop")])
    drop_first = _match(candidates, [_dec(P0, "drop"), _dec(P0, "keep")])

    assert keep_first.kept_urls == drop_first.kept_urls == [P0]


def test_kept_urls_identical_under_all_permutations() -> None:
    """The core permutation invariant: for a fixed multiset of decisions, every
    processing order yields the *same* ``kept_urls``.

    Multiset: p0 has a keep/drop conflict (keep must win), p1 is a lone drop,
    p2 is a keep echoed twice (a plain repeat). Expected keep set: {p0, p2}."""
    candidates = [P0, P1, P2]
    multiset = [
        _dec(P0, "keep", "k0"),
        _dec(P0, "drop", "d0"),
        _dec(P1, "drop", "d1"),
        _dec(P2, "keep", "k2a"),
        _dec(P2, "keep", "k2b"),
    ]

    kept_by_order = {
        tuple(_match(candidates, list(perm)).kept_urls)
        for perm in itertools.permutations(multiset)
    }

    assert len(kept_by_order) == 1, f"kept_urls varied by order: {kept_by_order}"
    assert set(kept_by_order.pop()) == {P0, P2}


def test_keep_wins_even_when_drop_echoed_at_candidate_index() -> None:
    """The positional winner would pick the drop when it sits at the candidate's
    own index; keep-wins must override that regardless of position."""
    candidates = [P0]
    # drop at index 0 (== candidate index), keep at index 1.
    match = _match(candidates, [_dec(P0, "drop"), _dec(P0, "keep")])
    assert match.kept_urls == [P0]
    assert match.decisions[0].decision == "keep"


def test_keep_drop_conflict_recorded_in_attrition() -> None:
    """Every keep/drop conflict is recorded — as a ``duplicate_url`` casualty
    whose detail identifies it as a conflict (no new reason-code vocabulary)."""
    candidates = [P0]
    match = _match(candidates, [_dec(P0, "keep"), _dec(P0, "drop")])

    conflicts = [a for a in match.attrition if a.url == P0]
    assert len(conflicts) == 1
    assert conflicts[0].reason == "duplicate_url"
    assert "conflict" in (conflicts[0].detail or "").lower()


def test_plain_repeat_still_recorded_but_not_labelled_conflict() -> None:
    """A duplicate with no keep/drop disagreement is still a ``duplicate_url``
    casualty, but its detail must NOT claim a conflict (regression guard on the
    detail-based distinction)."""
    candidates = [P0]
    match = _match(candidates, [_dec(P0, "keep"), _dec(P0, "keep")])

    dups = [a for a in match.attrition if a.url == P0]
    assert len(dups) == 1
    assert dups[0].reason == "duplicate_url"
    assert "conflict" not in (dups[0].detail or "").lower()


# ---------------------------------------------------------------------------
# Inclusion #3/#4: reject empty / whitespace-only candidate URLs
# ---------------------------------------------------------------------------

_INST = {"institution_id": "INST-0000001"}


def test_build_triage_job_rejects_empty_url() -> None:
    with pytest.raises(ValueError):
        build_triage_job(_INST, ["https://inst.gov/p0", ""], None, custom_id="c1")


def test_build_triage_job_rejects_whitespace_only_url() -> None:
    with pytest.raises(ValueError):
        build_triage_job(_INST, ["   \t "], None, custom_id="c1")


def test_build_triage_job_accepts_valid_urls() -> None:
    job = build_triage_job(_INST, ["https://inst.gov/p0"], None, custom_id="c1")
    assert job.custom_id == "c1"
