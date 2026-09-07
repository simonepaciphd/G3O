"""The whole chain, with nobody watching: submit → wait → Stage 7 → load → verify.

Every leg this composes already existed and already reported honestly. What did
not exist was the composition, and the four things that go wrong in it were all
measured on 2026-08-26 against run ``r20260824T215623Z-bb4e`` rather than
imagined:

1. **Stage 7 is not a stage.** ``stop_after: validate`` — every run to date —
   finishes ``COMPLETED 8/8`` with no ``final/``. A chain that goes submit →
   ingest skips it and finds nothing to load. :mod:`.persist_leg` is the missing
   step, and it is a leg here, not a footnote in a runbook.
2. **A missing artifact used to publish rather than stop.** ``g3o-api``'s
   ``load_search_verdicts`` prints its missing-summary warning and *continues*,
   writing NULL ``search_verdict`` for every institution and falling through to
   the pre-#17 inference. On that run it was 717 ``(no, PROCESSING_FAILED)``
   institutions that would have published as earned negatives. Only a human
   reading the log stood between the warning and a bad publish, and this module
   exists precisely for the case where there is no such human. The refusal now
   happens in :func:`~g3o.run.orchestrate.ingest.find_stage7_csvs`, before the
   transaction — and this chain runs :mod:`.persist_leg`, which proves the tree
   is loadable *before* the loader is ever invoked.
3. **The loader pin needed a source of truth.** ``--expect-loader-sha`` is
   optional, so an omitted flag silently skips the only check that the droplet's
   checkout is current. Here it is not optional: :data:`REQUIRED_SHA_SENTINEL`
   resolves from :mod:`.loader_pin`, in the repo, under review.
4. **Publication cannot be undone.** The refresh runs inside the loader's
   transaction, before its commit, so every gate in this chain is placed *before*
   ``ingest``. Nothing after the load can un-publish, and nothing in this module
   pretends otherwise: the last leg, ``publish-verify``, is a read-only check that
   the thing which already happened is what was wanted. **That leg is mandatory
   for the same reason the sha is** (2026-08-30): an absent ``--api-base`` used to
   record ``publish-verify`` as a green step whose own message said nothing had
   been checked, so a chain that published and then verified nothing returned the
   same verdict as one that verified. A flag that can disagree with the thing it
   describes is not a weaker check, it is a wrong answer. The base is now required
   before the wait, where a refusal is still free.

**Two traps that cost a session real time, encoded here so nobody rediscovers
them.**

``~/run-<id>.done`` is **not** a terminal-state signal. ``watch-run.sh`` writes it
once and exits, so the file goes stale: on 2026-08-26 the file present at 07:10
described a run that had already been superseded, and a monitor keyed on its
existence fired a false completion. This module never looks at it. It polls
:func:`~g3o.run.orchestrate.status.run_status` and breaks on
:attr:`~g3o.run.orchestrate.status.RunStatus.is_terminal`, which is derived from
the event log *and* the supervisor's liveness — so a run whose process died
without writing a terminal event reports ``interrupted`` and stops the chain,
instead of being polled forever.

``--smoke`` must never reach ``ingest.py``. Its ``smoke_report()`` raises
``IndeterminateDatatype``, the exception escapes the connection context manager,
``conn.commit()`` is never reached, and the whole load rolls back *after* the
console has printed "upserted N" (``g3o-api/README.md:195``). This module refuses
to pass it through rather than trusting a runbook footnote.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from g3o.run.orchestrate.ingest import IngestError, IngestResult, ingest_run
from g3o.run.orchestrate.loader_pin import PINNED_SENTINEL, resolve_expected_sha
from g3o.run.orchestrate.persist_leg import PersistError, PersistResult, persist_run
from g3o.run.orchestrate.publish import API_BASE_ENV_VAR
from g3o.run.orchestrate.status import RunStatus, run_status

logger = logging.getLogger(__name__)

#: What ``--expect-loader-sha`` defaults to here, unlike on the bare ingest verb.
REQUIRED_SHA_SENTINEL = PINNED_SENTINEL

#: Loader flags this chain will not forward, and why. ``--smoke`` rolls the load
#: back after printing success; ``--institutions-only`` exits 0 having loaded no
#: findings at all, which an automated caller would read as a green publish.
REFUSED_LOADER_ARGS = {
    "--smoke": (
        "smoke_report() raises IndeterminateDatatype inside the connection "
        "context manager, so conn.commit() is never reached and the whole load "
        "rolls back AFTER the console prints 'upserted N' (g3o-api/README.md:195). "
        "Use scripts/validate_wave.py — read-only, same checks and more."
    ),
    "--institutions-only": (
        "loads the registry and none of the findings, and exits 0 doing it. A "
        "chain that reports that as green has published nothing and said it "
        "published everything."
    ),
}


class E2EError(RuntimeError):
    """The chain stopped. The step that stopped it says why."""


@dataclass
class StepOutcome:
    """One leg's result, flattened so a monitor can read the chain as a list."""

    step: str
    green: bool
    detail: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "green": self.green,
            "message": self.message,
            **({"detail": self.detail} if self.detail else {}),
        }


@dataclass
class E2EResult:
    """What the chain did, step by step, and where it stopped if it did."""

    run_id: str | None = None
    steps: list[StepOutcome] = field(default_factory=list)
    stopped_at: str | None = None
    published: bool = False

    @property
    def green(self) -> bool:
        """Every step ran and every step was green. No partial credit.

        An empty chain is not green: a chain that stopped before its first step
        must not read the same as one that completed.
        """
        return bool(self.steps) and all(s.green for s in self.steps) and not self.stopped_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "green": self.green,
            "published": self.published,
            "stopped_at": self.stopped_at,
            "steps": [s.to_dict() for s in self.steps],
        }

    def _record(self, outcome: StepOutcome) -> StepOutcome:
        self.steps.append(outcome)
        if not outcome.green:
            self.stopped_at = outcome.step
        return outcome


def assert_loader_args_allowed(extra_args: tuple[str, ...]) -> None:
    """Refuse loader flags that make a rolled-back or empty load look green.

    Checked before the run is even submitted, not before the load: a chain that
    spends hours of compute and then refuses at the last leg has burned the
    compute to find out something knowable at second zero.
    """
    for arg in extra_args:
        # Match the flag itself, not `--smoke-something`: `=` is the only other
        # shape argparse accepts for a flag with a value.
        flag = arg.split("=", 1)[0]
        if flag in REFUSED_LOADER_ARGS:
            raise E2EError(
                f"refusing to run the chain with loader argument {flag!r}: "
                f"{REFUSED_LOADER_ARGS[flag]}"
            )


def wait_for_terminal(
    runs_dir: Path,
    run_id: str,
    *,
    poll_interval: float = 60.0,
    max_wait_seconds: float = 30 * 60 * 60,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    on_poll: Callable[[RunStatus], None] | None = None,
) -> RunStatus:
    """Poll ``orchestrate status`` until the run is terminal, or give up.

    The signal is :attr:`RunStatus.is_terminal`, and nothing else. Not
    ``~/run-<id>.done``, which ``watch-run.sh`` writes once and then leaves to go
    stale — the file present on the droplet at 07:10 on 2026-08-26 described a
    run that had already been superseded, and a monitor keyed on it fired a false
    completion.

    ``max_wait_seconds`` defaults above the 25 h ``max_wait_per_stage`` a single
    stage may take, so this timeout is a backstop against a wedged chain rather
    than a second, tighter deadline that would kill legitimate long runs. It is a
    refusal to *wait*, never a kill: the run keeps going, and the chain simply
    stops driving it.
    """
    started = now()
    while True:
        state = run_status(Path(runs_dir), run_id)
        if on_poll is not None:
            on_poll(state)
        if state.state == "missing":
            raise E2EError(
                f"no run directory for {run_id} under {runs_dir}. The submit "
                f"reported a run id that is not on disk; nothing to wait for."
            )
        if state.is_terminal:
            return state
        waited = now() - started
        if waited >= max_wait_seconds:
            raise E2EError(
                f"gave up waiting for {run_id} after {waited / 3600:.1f}h: it is "
                f"still {state.state!r} (liveness {state.liveness!r}, "
                f"{len(state.stages_done)} stages done"
                + (f", in flight {state.stage_in_flight}" if state.stage_in_flight else "")
                + "). The run has NOT been stopped — this chain has only stopped "
                "driving it. Check `orchestrate status` before doing anything else."
            )
        sleep(poll_interval)


def run_e2e(
    runs_dir: Path,
    run_id: str,
    *,
    frame_id: str,
    loader_repo: Path | None = None,
    master_csv: Path | None = None,
    extra_args: tuple[str, ...] = (),
    expect_loader_sha: str | None = REQUIRED_SHA_SENTINEL,
    api_base: str | None = None,
    publish_sample: int = 10,
    poll_interval: float = 60.0,
    max_wait_seconds: float = 30 * 60 * 60,
    version: int | None = None,
    max_load_failures: int = 0,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = logger.info,
) -> E2EResult:
    """Drive an already-submitted run to published, stopping at the first failure.

    Deliberately takes a ``run_id`` rather than submitting: submitting is
    :func:`g3o.run.orchestrate.submit.submit`'s job, it has its own cost ceiling
    and its own refusals, and a chain that both spends money and publishes is one
    verb with two irreversible acts in it. Point this at a run that is already
    running — or already finished, in which case the wait returns immediately and
    the chain becomes "finish what was started".

    Returns an :class:`E2EResult` in every non-exceptional case. The chain stops
    at the first non-green step and says which one; it does not raise for a
    leg that ran and came back not-green, because "the load ran and quarantined
    rows" and "the load never happened" need to be distinguishable by a caller
    that is not reading a traceback.
    """
    assert_loader_args_allowed(extra_args)
    resolved_sha = resolve_expected_sha(expect_loader_sha)
    if not resolved_sha:
        raise E2EError(
            "the chain requires an expected loader sha: without one, "
            "--expect-loader-sha is a check that silently does not happen, and "
            f"which loader published a run is part of its record. Pass "
            f"{PINNED_SENTINEL!r} to use the reviewed pin in "
            "g3o/run/orchestrate/loader_pin.py."
        )
    base = api_base or os.environ.get(API_BASE_ENV_VAR)
    if not base:
        raise E2EError(
            f"the chain requires an API base: pass --api-base or set "
            f"{API_BASE_ENV_VAR} (e.g. https://api.g3observatory.org). Until "
            f"2026-08-30 an absent one skipped publish-verify and recorded that "
            f"skip as a GREEN step, so a chain that committed a publication and "
            f"then checked nothing about it reported the same verdict as one "
            f"that verified. Refused here, at second zero, because the leg it "
            f"guards runs after the only irreversible act in the chain: a "
            f"refusal at the end would arrive too late to be a gate."
        )

    result = E2EResult(run_id=run_id)

    # --- 1. wait ----------------------------------------------------------
    log(f"e2e: waiting for {run_id} to reach a terminal state")
    try:
        state = wait_for_terminal(
            runs_dir, run_id,
            poll_interval=poll_interval, max_wait_seconds=max_wait_seconds,
            sleep=sleep, now=now,
        )
    except E2EError as exc:
        result._record(StepOutcome("wait", False, message=str(exc)))
        return result
    result._record(
        StepOutcome(
            "wait", True,
            detail={"state": state.state, "stages_done": len(state.stages_done)},
            message=state.one_line(),
        )
    )

    # --- 2. gate ----------------------------------------------------------
    # Before Stage 7, not after: Stage 7 over a partial run writes real CSVs from
    # an incomplete sweep, and by the time they exist nothing can tell them apart.
    if not state.publishable:
        result._record(
            StepOutcome(
                "gate", False,
                detail={"state": state.state, "dry_run": state.dry_run},
                message=(
                    f"run {run_id} ended {state.state!r} and is not publishable"
                    + (f": {state.failure.get('error_message')}" if state.failure else "")
                    + ". Nothing was written and nothing was loaded."
                ),
            )
        )
        return result
    result._record(StepOutcome("gate", True, message=f"{run_id} is publishable"))

    # --- 3. Stage 7 -------------------------------------------------------
    log(f"e2e: Stage 7 for {run_id}")
    persist_kwargs: dict[str, Any] = {
        "max_load_failures": max_load_failures, "status": state,
    }
    if version is not None:
        persist_kwargs["version"] = version
    try:
        persisted: PersistResult = persist_run(runs_dir, run_id, **persist_kwargs)
    except PersistError as exc:
        result._record(StepOutcome("persist", False, message=str(exc)))
        return result
    result._record(
        StepOutcome(
            "persist", persisted.green,
            detail=persisted.to_dict(),
            message=f"final/ written and loadable (v{persisted.version})",
        )
    )

    # --- 4. load ----------------------------------------------------------
    # Everything above this line is reversible. Nothing below it is.
    log(f"e2e: loading {run_id} with loader pinned at {resolved_sha[:7]}")
    try:
        ingested: IngestResult = ingest_run(
            runs_dir, run_id,
            frame_id=frame_id,
            loader_repo=loader_repo,
            master_csv=master_csv,
            extra_args=extra_args,
            expect_loader_sha=resolved_sha,
            status=state,
        )
    except IngestError as exc:
        result._record(StepOutcome("ingest", False, message=str(exc)))
        return result
    result._record(
        StepOutcome("ingest", ingested.green, detail=ingested.to_dict(),
                    message=ingested.verdict)
    )
    # The refresh is inside the loader's transaction, so a load that reached
    # commit has published. Recorded on the result whether or not the strict
    # checks passed: "published and not green" is a real state and the operator
    # needs to know they are looking at one.
    result.published = ingested.exit_code != 2
    if not ingested.green:
        return result

    # --- 5. verify --------------------------------------------------------
    # Read-only, and last on purpose: it cannot cause a publish and cannot undo
    # one. It answers "is what happened what was wanted", which is a different
    # question from every gate above it.
    from g3o.run.orchestrate.publish import PublishVerifyError, verify_published

    log(f"e2e: asking {base} what it can see of {run_id}")
    try:
        published = verify_published(
            runs_dir, run_id, api_base=base, sample=publish_sample,
            expect_visible=True,
        )
    except PublishVerifyError as exc:
        result._record(StepOutcome("publish-verify", False, message=str(exc)))
        return result
    result._record(
        StepOutcome(
            "publish-verify", published.verdict == "pass",
            detail=published.to_dict(),
            message=f"verdict {published.verdict}",
        )
    )
    return result


def render_e2e(result: E2EResult) -> str:
    """The chain as a list, verdict first. One line per leg, no colour."""
    verdict = "GREEN" if result.green else "NOT GREEN"
    lines = [
        f"End-to-end — run {result.run_id}",
        f"  {verdict}"
        + ("" if not result.stopped_at else f" — stopped at {result.stopped_at}"),
        f"  published          : {'yes' if result.published else 'no'}",
        "",
    ]
    for step in result.steps:
        mark = "ok  " if step.green else "FAIL"
        lines.append(f"  {mark} {step.step:<15} {step.message}")
    return "\n".join(lines)


__all__ = [
    "E2EError",
    "E2EResult",
    "REFUSED_LOADER_ARGS",
    "REQUIRED_SHA_SENTINEL",
    "StepOutcome",
    "assert_loader_args_allowed",
    "render_e2e",
    "run_e2e",
    "wait_for_terminal",
]
