"""Legs 2.5 and the chain: Stage 7 as a leg, the loader pin, and unattended flow.

The four defects these cover were all measured on 2026-08-26 against run
``r20260824T215623Z-bb4e``, which completed 8/8 and published, and could not have
done either without a human in the loop:

1. Stage 7 is not a member of ``STAGES``, so ``stop_after: validate`` finishes
   with no ``final/``.
2. ``g3o-api``'s ``load_search_verdicts`` warns about a missing summary and
   *continues*, writing NULL verdicts that publish through the pre-#17 inference.
3. ``--expect-loader-sha`` is optional, so an omitted flag means the only check on
   the loader's identity silently does not happen.
4. The refresh is inside the loader's transaction, so nothing after the load can
   un-publish — every gate has to sit before it.

Plus the two traps that cost a session real time: ``~/run-<id>.done`` goes stale
and is not a terminal signal, and ``--smoke`` rolls the whole load back after
printing success.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from g3o.run.orchestrate import e2e as e2e_mod
from g3o.run.orchestrate import loader_pin
from g3o.run.orchestrate import persist_leg as pl
from g3o.run.orchestrate.status import RunStatus
from tests._orchestrate import event, make_run, write_final_csvs

# ---------------------------------------------------------------------------
# The pin — gap 3
# ---------------------------------------------------------------------------


def test_the_pin_is_a_full_sha() -> None:
    # An abbreviated sha would compare unequal against the 40-char value
    # ``loader_provenance`` reads out of git, and the refusal message would
    # read as a stale checkout rather than as a malformed pin.
    assert len(loader_pin.EXPECTED_LOADER_SHA) == 40
    assert loader_pin.EXPECTED_LOADER_SHA.startswith("14e37cc")


def test_the_sentinel_resolves_and_everything_else_passes_through() -> None:
    assert loader_pin.resolve_expected_sha("pinned") == loader_pin.EXPECTED_LOADER_SHA
    assert loader_pin.resolve_expected_sha("deadbeef") == "deadbeef"
    # None stays None: this resolver does not decide the check is mandatory, it
    # only gives the check somewhere to read its answer from.
    assert loader_pin.resolve_expected_sha(None) is None


def test_the_chain_refuses_to_run_without_a_sha(tmp_path: Path) -> None:
    with pytest.raises(e2e_mod.E2EError, match="expected loader sha"):
        e2e_mod.run_e2e(
            tmp_path / "runs", "r1", frame_id="mb-TEST", expect_loader_sha=None
        )


def test_the_ingest_verb_resolves_the_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    """`orchestrate ingest --expect-loader-sha pinned` must not compare literally."""
    from g3o.run.orchestrate import cli

    seen: dict[str, Any] = {}

    def fake_ingest_run(*_args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        raise SystemExit(0)

    monkeypatch.setattr(
        "g3o.run.orchestrate.ingest.ingest_run", fake_ingest_run, raising=True
    )
    args = cli.build_parser().parse_args([
        "ingest", "--run-id", "r1", "--frame-id", "mb-TEST",
        "--expect-loader-sha", "pinned",
    ])
    with pytest.raises(SystemExit):
        args.func(args)
    assert seen["expect_loader_sha"] == loader_pin.EXPECTED_LOADER_SHA


# ---------------------------------------------------------------------------
# Refused loader arguments — the --smoke trap
# ---------------------------------------------------------------------------


def test_smoke_is_refused_before_anything_runs() -> None:
    """``smoke_report()`` rolls the load back after printing 'upserted N'."""
    with pytest.raises(e2e_mod.E2EError, match="rolls back"):
        e2e_mod.assert_loader_args_allowed(("--smoke",))


def test_institutions_only_is_refused() -> None:
    """Exits 0 having loaded no findings — green to a caller, empty in fact."""
    with pytest.raises(e2e_mod.E2EError, match="published nothing"):
        e2e_mod.assert_loader_args_allowed(("--institutions-only",))


def test_a_refused_flag_with_a_value_is_still_caught() -> None:
    with pytest.raises(e2e_mod.E2EError):
        e2e_mod.assert_loader_args_allowed(("--smoke=1",))


def test_an_ordinary_loader_arg_passes() -> None:
    e2e_mod.assert_loader_args_allowed(("--make-current", "--limit", "10"))


def test_refusal_happens_before_the_chain_waits(tmp_path: Path) -> None:
    """Knowable at second zero, so it must not cost a run's worth of compute."""
    def explode(*_a: Any, **_k: Any) -> None:
        raise AssertionError("the chain must refuse before it polls anything")

    with pytest.raises(e2e_mod.E2EError):
        e2e_mod.run_e2e(
            tmp_path / "runs", "r1", frame_id="mb-TEST",
            extra_args=("--smoke",), sleep=explode, now=explode,
        )


# ---------------------------------------------------------------------------
# The wait — trap 1: ~/run-<id>.done goes stale
# ---------------------------------------------------------------------------


def _status(state: str, **kw: Any) -> RunStatus:
    return RunStatus(run_id="r1", run_dir=Path("runs/r1"), state=state, **kw)  # type: ignore[arg-type]


def _fake_clock() -> Any:
    """A monotonic clock the test drives, so no test ever really sleeps."""
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)

    def now() -> float:
        return sum(slept)

    return sleep, now, slept


def test_the_wait_polls_status_until_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter(["launching", "running", "running", "completed"])
    monkeypatch.setattr(
        e2e_mod, "run_status", lambda *_a, **_k: _status(next(states))
    )
    sleep, now, slept = _fake_clock()

    state = e2e_mod.wait_for_terminal(
        Path("runs"), "r1", poll_interval=30.0, sleep=sleep, now=now
    )

    assert state.state == "completed"
    assert slept == [30.0, 30.0, 30.0]


def test_the_wait_stops_on_a_run_that_died_without_saying_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``interrupted`` is terminal: the process is gone and the stages will not run.

    This is the property that makes ``~/run-<id>.done`` unnecessary — and the file
    is worse than unnecessary, because ``watch-run.sh`` writes it once and leaves
    it to go stale. The one on the droplet at 07:10 on 2026-08-26 described a run
    that had already been superseded, and a monitor keyed on it fired a false
    completion.
    """
    monkeypatch.setattr(
        e2e_mod, "run_status", lambda *_a, **_k: _status("interrupted")
    )
    sleep, now, slept = _fake_clock()

    state = e2e_mod.wait_for_terminal(Path("runs"), "r1", sleep=sleep, now=now)

    assert state.is_terminal and state.is_failed
    assert slept == []  # terminal on the first poll; never slept


def test_the_wait_gives_up_without_stopping_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(e2e_mod, "run_status", lambda *_a, **_k: _status("running"))
    sleep, now, _ = _fake_clock()

    with pytest.raises(e2e_mod.E2EError, match="has NOT been stopped"):
        e2e_mod.wait_for_terminal(
            Path("runs"), "r1", poll_interval=60.0, max_wait_seconds=120.0,
            sleep=sleep, now=now,
        )


def test_the_wait_refuses_a_run_that_is_not_on_disk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(e2e_mod, "run_status", lambda *_a, **_k: _status("missing"))
    sleep, now, _ = _fake_clock()

    with pytest.raises(e2e_mod.E2EError, match="no run directory"):
        e2e_mod.wait_for_terminal(Path("runs"), "r1", sleep=sleep, now=now)


# ---------------------------------------------------------------------------
# Stage 7 as a leg — gap 1
# ---------------------------------------------------------------------------


def _completed_run(tmp_path: Path, *, final: bool = False) -> tuple[Path, str]:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir,
        events=[event(1, "run_launched"), event(2, "run_completed", outcome="completed")],
    )
    if final:
        write_final_csvs(run_dir)
    return runs_dir, run_dir.name


def test_the_loader_version_is_read_off_the_loader_path() -> None:
    """Restating it as a literal is how the two drift."""
    assert pl.LOADER_VERSION == 1


def test_persist_refuses_a_run_that_did_not_complete(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    make_run(runs_dir, events=[event(1, "run_launched")])

    with pytest.raises(pl.PersistError, match="incomplete sweep"):
        pl.persist_run(runs_dir, "r20260813T100000Z-aaaa")


def test_persist_is_a_no_op_over_an_already_loadable_tree(tmp_path: Path) -> None:
    """An automated retry re-running the chain must not be a conflict."""
    runs_dir, run_id = _completed_run(tmp_path, final=True)
    before = (runs_dir / run_id / "final" / "g3o_activities_v1.csv").read_text(
        encoding="utf-8"
    )

    result = pl.persist_run(runs_dir, run_id)

    assert result.green
    assert result.summary["skipped"]
    assert result.n_load_failures is None  # not asked, which is not zero
    assert (runs_dir / run_id / "final" / "g3o_activities_v1.csv").read_text(
        encoding="utf-8"
    ) == before


def test_persist_records_a_leg(tmp_path: Path) -> None:
    runs_dir, run_id = _completed_run(tmp_path, final=True)

    pl.persist_run(runs_dir, run_id)

    record = json.loads(
        (runs_dir / run_id / "_orchestrator" / "persist.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["leg"] == "persist"
    assert record["outcome"] == "green"
    assert record["rewrote"] is False


def test_persist_fails_when_what_it_wrote_is_not_loadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The leg's success criterion is leg 3's precondition.

    Writing a ``final/`` the loader cannot read has to fail here, where the fix is
    one re-run, rather than two legs later — or, before the guard existed, publish
    silently through the pre-#17 inference.
    """
    runs_dir, run_id = _completed_run(tmp_path)

    def write_v2(run_dir: Path, **kwargs: Any) -> dict[str, Any]:
        write_final_csvs(run_dir)
        final = run_dir / "final"
        for name in ("g3o_activities", "g3o_activity_sources", "g3o_institution_summary"):
            (final / f"{name}_v1.csv").rename(final / f"{name}_v2.csv")
        return {"n_load_failures": 0, "outputs": {}}

    monkeypatch.setattr(pl, "_write", lambda run_dir, rid, **kw: write_v2(run_dir))

    with pytest.raises(pl.PersistError, match="will not load it"):
        pl.persist_run(runs_dir, run_id, version=2)

    record = json.loads(
        (runs_dir / run_id / "_orchestrator" / "persist.json").read_text(
            encoding="utf-8"
        )
    )
    assert record["outcome"] == "not-green"


def test_persist_refuses_over_the_load_failure_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Institutions Stage 7 could not read make no published claim — silently."""
    runs_dir, run_id = _completed_run(tmp_path)

    def write_with_failures(run_dir: Path, **kwargs: Any) -> dict[str, Any]:
        write_final_csvs(run_dir)
        return {
            "n_load_failures": 3,
            "load_failures": ["INST-1", "INST-2", "INST-3"],
            "outputs": {},
        }

    monkeypatch.setattr(
        pl, "_write", lambda run_dir, rid, **kw: write_with_failures(run_dir)
    )

    with pytest.raises(pl.PersistError, match="could not read 3"):
        pl.persist_run(runs_dir, run_id)

    # Explicitly overridable, never silent — the loader's own policy.
    result = pl.persist_run(runs_dir, run_id, max_load_failures=3, overwrite=True)
    assert result.green
    assert result.n_load_failures == 3


# ---------------------------------------------------------------------------
# The chain — order of gates, and gap 4
# ---------------------------------------------------------------------------


def _chain(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> Any:
    """Run the chain with every leg stubbed, recording the order they ran in."""
    calls: list[str] = []

    def fake_wait(*_a: Any, **_k: Any) -> RunStatus:
        calls.append("wait")
        return overrides.get("status", _status("completed", dry_run=False))

    def fake_persist(*_a: Any, **_k: Any) -> Any:
        calls.append("persist")
        if "persist_error" in overrides:
            raise pl.PersistError(overrides["persist_error"])
        return pl.PersistResult(
            run_id="r1", run_dir=Path("runs/r1"), version=1, loadable=True,
            summary={"n_load_failures": 0},
        )

    def fake_ingest(*_a: Any, **kwargs: Any) -> Any:
        calls.append("ingest")
        recorded_sha.append(kwargs.get("expect_loader_sha"))
        return overrides.get("ingest_result", _green_ingest())

    def fake_harvest(*_a: Any, **_k: Any) -> Any:
        calls.append("harvest")
        return overrides.get("harvest_result", _green_harvest())

    recorded_sha: list[Any] = []
    monkeypatch.setattr(e2e_mod, "wait_for_terminal", fake_wait)
    monkeypatch.setattr(e2e_mod, "persist_run", fake_persist)
    monkeypatch.setattr(e2e_mod, "ingest_run", fake_ingest)
    monkeypatch.setattr(e2e_mod, "harvest_official_sites", fake_harvest)
    monkeypatch.delenv("G3O_API_BASE", raising=False)

    result = e2e_mod.run_e2e(
        Path("runs"), "r1", frame_id="mb-TEST", **overrides.get("e2e_kwargs", {})
    )
    return result, calls, recorded_sha


def _green_harvest() -> Any:
    from g3o.run.orchestrate.harvest import HarvestResult

    return HarvestResult(
        overlay_path="runs/_site_overlay/official_sites.csv",
        sha256="a" * 64, changed=True, runs_scanned=1, overlay_rows=3,
    )


def _green_ingest() -> Any:
    from g3o.run.orchestrate.ingest import IngestCounts, IngestResult

    return IngestResult(
        run_id="r1", exit_code=0, argv=("x",),
        counts=IngestCounts(
            institutions=10, findings_loaded=5, findings_quarantined=0,
            evidence_loaded=5, evidence_quarantined=0, n_sources_mismatched=0,
        ),
        log_path=Path("ingest.log"),
    )


def test_the_chain_runs_wait_gate_persist_ingest_in_that_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage 7 before the load, and every gate before the irreversible step."""
    result, calls, sha = _chain(monkeypatch)

    assert calls == ["wait", "harvest", "persist", "ingest"]
    assert [s.step for s in result.steps] == [
        "wait", "gate", "harvest", "persist", "ingest", "publish-verify"
    ]
    assert result.green
    assert result.published is True
    # The pin, resolved, without the caller having to know it.
    assert sha == [loader_pin.EXPECTED_LOADER_SHA]


def test_a_run_that_is_not_publishable_never_reaches_stage_7(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The induced-failure property: nothing is written and nothing is loaded."""
    result, calls, _ = _chain(monkeypatch, status=_status("failed", dry_run=False))

    assert calls == ["wait"]
    assert result.stopped_at == "gate"
    assert result.green is False
    assert result.published is False


def test_a_dry_run_never_reaches_stage_7(monkeypatch: pytest.MonkeyPatch) -> None:
    result, calls, _ = _chain(monkeypatch, status=_status("completed", dry_run=True))

    assert calls == ["wait"]
    assert result.stopped_at == "gate"


def test_a_stage_7_refusal_stops_the_chain_before_the_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, calls, _ = _chain(monkeypatch, persist_error="final/ is not loadable")

    assert calls == ["wait", "harvest", "persist"]
    assert result.stopped_at == "persist"
    assert result.published is False


def test_an_aborted_load_is_reported_as_not_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit 2 is the loader refusing before commit — nothing reached the database."""
    from g3o.run.orchestrate.ingest import IngestCounts, IngestResult

    aborted = IngestResult(
        run_id="r1", exit_code=2, argv=("x",), counts=IngestCounts(),
        log_path=Path("ingest.log"),
    )
    result, calls, _ = _chain(monkeypatch, ingest_result=aborted)

    assert calls == ["wait", "harvest", "persist", "ingest"]
    assert result.stopped_at == "ingest"
    assert result.published is False


def test_a_committed_but_not_green_load_is_reported_as_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit 1 loaded, committed, refreshed, and failed a strict check.

    'Published and not green' is a real state, and the operator has to be able to
    tell it from 'nothing happened' — the refresh runs inside the transaction, so
    by the time exit 1 is printed the public views already moved.
    """
    from g3o.run.orchestrate.ingest import IngestCounts, IngestResult

    not_green = IngestResult(
        run_id="r1", exit_code=1, argv=("x",),
        counts=IngestCounts(
            institutions=10, findings_loaded=5, findings_quarantined=2,
            evidence_loaded=5, evidence_quarantined=0,
        ),
        log_path=Path("ingest.log"),
    )
    result, _, _ = _chain(monkeypatch, ingest_result=not_green)

    assert result.stopped_at == "ingest"
    assert result.published is True
    assert result.green is False


def test_publish_verify_is_skipped_loudly_when_there_is_no_api_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _, _ = _chain(monkeypatch)
    step = [s for s in result.steps if s.step == "publish-verify"][0]
    assert "skipped" in step.message
    assert "committed and published" in step.message


def test_an_empty_chain_is_not_green() -> None:
    """A chain that stopped before its first step must not read as success."""
    assert e2e_mod.E2EResult(run_id="r1").green is False


def test_render_names_the_step_it_stopped_at() -> None:
    result = e2e_mod.E2EResult(run_id="r1")
    result.steps.append(e2e_mod.StepOutcome("wait", True, message="ok"))
    result.steps.append(e2e_mod.StepOutcome("gate", False, message="not publishable"))
    result.stopped_at = "gate"

    text = e2e_mod.render_e2e(result)

    assert "NOT GREEN — stopped at gate" in text
    assert "FAIL gate" in text


# ---------------------------------------------------------------------------
# harvest — the derived leg, and the only one that must never stop the chain
# ---------------------------------------------------------------------------


def _failed_harvest() -> Any:
    from g3o.run.orchestrate.harvest import HarvestResult

    return HarvestResult(error="OSError: read-only file system")


def test_the_harvest_runs_before_the_irreversible_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It depends only on the run being complete, and a run whose load later fails
    still contributed its discoveries: the sites Stage 2 found are real either way."""
    _, calls, _ = _chain(monkeypatch)

    assert calls.index("harvest") < calls.index("ingest")
    assert calls.index("harvest") < calls.index("persist")


def test_a_run_that_is_not_publishable_is_never_harvested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate is upstream of it: a failed run's Stage-2 artifacts are not a corpus."""
    _, calls, _ = _chain(monkeypatch, status=_status("failed", dry_run=False))

    assert "harvest" not in calls


def test_a_failed_harvest_does_not_stop_a_chain_that_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A derived table that could not be rewritten is not a failed publication.

    `_record` sets `stopped_at` on any non-green step, so reporting the failure as
    non-green would make a successful, irreversible publish read as a chain that
    stopped — describing a failure that did not happen.
    """
    result, calls, _ = _chain(monkeypatch, harvest_result=_failed_harvest())

    assert calls == ["wait", "harvest", "persist", "ingest"]
    assert result.stopped_at is None
    assert result.green is True
    assert result.published is True
    step = next(s for s in result.steps if s.step == "harvest")
    assert step.green is True
    assert "NOT rebuilt" in step.message


def test_require_harvest_makes_it_a_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """For a caller who wants one. Note it stops the chain BEFORE the load."""
    result, calls, _ = _chain(
        monkeypatch,
        harvest_result=_failed_harvest(),
        e2e_kwargs={"require_harvest": True},
    )

    assert calls == ["wait", "harvest"]
    assert result.stopped_at == "harvest"
    assert result.published is False


def test_harvest_can_be_skipped_and_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    result, calls, _ = _chain(monkeypatch, e2e_kwargs={"harvest": False})

    assert "harvest" not in calls
    step = next(s for s in result.steps if s.step == "harvest")
    assert step.green is True
    assert "skipped" in step.message
    assert result.green is True
