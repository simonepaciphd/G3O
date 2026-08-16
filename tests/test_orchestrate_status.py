"""Status derivation — the leg every other leg gates on (Item 3, leg 2).

The properties asserted here are the ones the rest of the orchestrator relies on
being true:

- a terminal event is authoritative, and the **last** one wins across a resume;
- a run whose process is gone and which wrote no terminal event is
  ``interrupted``, not ``running`` — the named failed state the induced-failure
  gate needs, since a killed run cannot write ``run_failed`` about itself;
- ``publishable`` is narrow: completed, and never a dry run;
- every reader tolerates a file being written underneath it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from g3o.common import run_state
from g3o.run.orchestrate import status as st
from tests._orchestrate import event, make_run, write_submit_record


def _running_events() -> list[dict]:
    return [
        event(1, "run_launched", invocation="api", config_hash="c" * 64),
        event(2, "stage_started", stage="discovery_general", counts_in=3),
        event(3, "stage_completed", stage="discovery_general", counts_in=3, counts_out=3),
        event(4, "stage_started", stage="scrape", counts_in=3),
    ]


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------


def test_missing_run_reports_missing(tmp_path: Path) -> None:
    status = st.run_status(tmp_path, "r20260813T100000Z-aaaa")
    assert status.state == "missing"
    assert not status.publishable
    assert "no run directory" in status.one_line()


def test_run_dir_without_manifest_is_launching(tmp_path: Path) -> None:
    make_run(tmp_path, no_manifest=True)
    assert st.run_status(tmp_path, "r20260813T100000Z-aaaa").state == "launching"


def test_running_run_reports_its_in_flight_stage(tmp_path: Path, monkeypatch) -> None:
    run_dir = make_run(tmp_path, events=_running_events(), stages_done=["discovery_general"])
    write_submit_record(run_dir, pid=os.getpid(), outcome="running")
    monkeypatch.setattr(st, "process_liveness", lambda *a, **k: "alive")

    status = st.run_status(tmp_path, run_dir.name)

    assert status.state == "running"
    assert status.stage_in_flight == "scrape"
    assert status.stages_done == ("discovery_general",)
    assert status.last_event["seq"] == 4
    assert not status.publishable


def test_killed_run_is_interrupted_not_running(tmp_path: Path, monkeypatch) -> None:
    """The induced-failure case that no event can describe.

    A ``SIGKILL`` mid-stage leaves a manifest, a log that stops, and ``_state/``
    intact. Without liveness this is indistinguishable from a healthy run waiting
    on a 25-hour batch, and a monitor would report it green forever.
    """
    run_dir = make_run(tmp_path, events=_running_events(), stages_done=["discovery_general"])
    write_submit_record(run_dir, pid=424242, outcome="running")
    monkeypatch.setattr(st, "process_liveness", lambda *a, **k: "dead")

    status = st.run_status(tmp_path, run_dir.name)

    assert status.state == "interrupted"
    assert status.is_failed
    assert not status.publishable
    assert "process is gone" in status.failure["error_message"]
    assert "the process is gone" in status.one_line()


def test_terminal_events_win_over_liveness(tmp_path: Path, monkeypatch) -> None:
    """A finished run stays finished even though its process is (correctly) gone."""
    run_dir = make_run(
        tmp_path,
        events=[*_running_events(), event(5, "run_completed", outcome="completed", stop_after="validate")],
    )
    write_submit_record(run_dir, pid=424242, outcome="completed", finished_at="2026-08-13T12:00:00Z")
    monkeypatch.setattr(st, "process_liveness", lambda *a, **k: "dead")

    status = st.run_status(tmp_path, run_dir.name)

    assert status.state == "completed"
    assert status.publishable


def test_run_failed_carries_its_cause(tmp_path: Path) -> None:
    run_dir = make_run(
        tmp_path,
        events=[
            *_running_events(),
            event(
                5, "run_failed", outcome="failed", stop_after="validate",
                error_class="RuntimeError",
                error_message="Stage scrape: batch chunk 1 (expired) ended in a terminal state",
            ),
        ],
    )
    status = st.run_status(tmp_path, run_dir.name)

    assert status.state == "failed"
    assert status.is_failed
    assert not status.publishable
    assert status.failure["error_class"] == "RuntimeError"
    assert "chunk 1" in status.failure["error_message"]
    assert "RuntimeError" in status.one_line()


def test_last_terminal_event_wins_across_a_resume(tmp_path: Path) -> None:
    """One log per run, so a resumed run's file holds the earlier outcome too."""
    run_dir = make_run(
        tmp_path,
        events=[
            event(1, "run_launched"),
            event(2, "run_failed", error_class="RuntimeError", error_message="died"),
            event(3, "resume", stages_done=["discovery_general"]),
            event(4, "run_completed", outcome="completed", stop_after="validate"),
        ],
    )
    status = st.run_status(tmp_path, run_dir.name)
    assert status.state == "completed"
    assert status.resumed is True


def test_dry_run_is_never_publishable(tmp_path: Path) -> None:
    """`stopped` for a dry run means "planned nothing", not "finished early"."""
    run_dir = make_run(
        tmp_path,
        config={"dry_run": True},
        events=[event(1, "run_launched"), event(2, "run_stopped", outcome="stopped", reason="dry_run")],
    )
    status = st.run_status(tmp_path, run_dir.name)
    assert status.state == "stopped"
    assert status.dry_run is True
    assert not status.publishable


def test_pre_manifest_failure_is_visible_without_telemetry(tmp_path: Path) -> None:
    """A `LaunchValidationError` leaves no events at all (§1.5) — only the record."""
    run_dir = make_run(tmp_path, no_manifest=True)
    write_submit_record(
        run_dir, pid=os.getpid(), outcome="failed", finished_at="2026-08-13T10:00:05Z",
        error_class="LaunchValidationError", error_message="runs_dir is not writable",
    )
    status = st.run_status(tmp_path, run_dir.name)

    assert status.state == "failed"
    assert status.failure["source"].startswith("submit record")
    assert "not writable" in status.failure["error_message"]


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------


def test_chunks_in_flight_come_from_state_files(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, events=_running_events())
    run_state.write_active_chunked(
        run_dir, "extract", run_id=run_dir.name, model="gpt-5-nano",
        chunk_custom_ids=[["a", "b"], ["c"]],
    )
    run_state.update_chunk(run_dir, "extract", 1, batch_id="batch_abc")

    status = st.run_status(tmp_path, run_dir.name)

    # Chunk 1 is in flight; chunk 2 was never submitted, so it is not "in flight".
    assert status.chunks_in_flight == ("extract:1",)


def test_fetched_chunks_are_not_in_flight(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    run_state.write_active_chunked(
        run_dir, "extract", run_id=run_dir.name, model="m", chunk_custom_ids=[["a"]],
    )
    run_state.update_chunk(run_dir, "extract", 1, batch_id="b1", fetched_at="2026-08-13T11:00:00Z")
    assert st.run_status(tmp_path, run_dir.name).chunks_in_flight == ()


def test_a_torn_last_line_does_not_lose_the_log(tmp_path: Path) -> None:
    """A killed process can leave half a line; everything before it still counts."""
    run_dir = make_run(tmp_path, events=_running_events())
    with open(run_dir / st.EVENTS_FILENAME, "a", encoding="utf-8") as handle:
        handle.write('{"ts": "2026-08-13T10:05:00Z", "seq": 5, "eve')

    events = st.read_events(run_dir / st.EVENTS_FILENAME)

    assert [e["seq"] for e in events] == [1, 2, 3, 4]


def test_unreadable_manifest_does_not_raise(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    (run_dir / st.MANIFEST_FILENAME).write_text("{not json", encoding="utf-8")
    # No manifest that parses ⇒ nothing has been planned that we can read.
    assert st.run_status(tmp_path, run_dir.name).state == "launching"


def test_stage_in_flight_is_none_when_every_stage_completed(tmp_path: Path) -> None:
    run_dir = make_run(
        tmp_path,
        events=[
            event(1, "stage_started", stage="scrape", counts_in=1),
            event(2, "stage_completed", stage="scrape", counts_in=1, counts_out=1),
        ],
        stages_done=["scrape"],
    )
    assert st.run_status(tmp_path, run_dir.name).stage_in_flight is None


# ---------------------------------------------------------------------------
# Liveness itself
# ---------------------------------------------------------------------------


def test_this_process_is_alive() -> None:
    assert st.process_liveness(os.getpid()) == "alive"


def test_an_exited_process_is_dead() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert st.process_liveness(proc.pid) == "dead"


def test_a_reused_pid_is_not_our_process(monkeypatch) -> None:
    """Identity mismatch means the number was recycled, whatever answers to it now.

    ``pid_identity`` is patched rather than skipped off Linux: the comparison is
    the portable half of the rule, and it is the half that decides. Where the
    platform cannot supply an identity at all, the recorded one is ``None`` and
    the check correctly does not fire (:func:`test_unknown_identity_does_not_fire`).
    """
    monkeypatch.setattr(st, "pid_identity", lambda _pid: "9999999")
    assert st.process_liveness(os.getpid(), identity="1234") == "dead"
    assert st.process_liveness(os.getpid(), identity="9999999") == "alive"


def test_unknown_identity_does_not_fire(monkeypatch) -> None:
    """No identity available ⇒ fall back to the pid answer, never to "dead"."""
    monkeypatch.setattr(st, "pid_identity", lambda _pid: None)
    assert st.process_liveness(os.getpid(), identity="1234") == "alive"


def test_no_pid_is_unknown_not_dead() -> None:
    """A run started without the orchestrator has no supervisor record to read."""
    assert st.process_liveness(None) == "unknown"


def test_liveness_unknown_keeps_a_run_running(tmp_path: Path) -> None:
    """A bare `g3o presweep` run reports its stages; only liveness is unavailable."""
    run_dir = make_run(tmp_path, events=_running_events())
    status = st.run_status(tmp_path, run_dir.name)
    assert status.liveness == "unknown"
    assert status.state == "running"


@pytest.mark.skipif(not Path("/proc").is_dir(), reason="Linux-only /proc identity")
def test_pid_identity_is_stable_for_a_live_process() -> None:
    assert st.pid_identity(os.getpid()) == st.pid_identity(os.getpid())


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def test_leg_records_are_read_back_into_the_status(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, events=[event(1, "run_completed", outcome="completed")])
    st.record_leg(run_dir, "ingest", outcome="green", exit_code=0)

    status = st.run_status(tmp_path, run_dir.name)

    assert status.legs["ingest"]["outcome"] == "green"
    assert "ingest=green" in status.one_line()


def test_record_leg_never_raises_on_an_unwritable_path(tmp_path: Path, monkeypatch) -> None:
    """Bookkeeping follows telemetry's rule (§4.4): it warns, it never aborts."""
    run_dir = make_run(tmp_path)

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(st, "write_json_atomic", _boom)
    st.record_leg(run_dir, "archive", outcome="verified")  # must not raise


def test_write_json_atomic_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "record.json"
    st.write_json_atomic(path, {"a": 1})
    assert path.read_text(encoding="utf-8").strip().startswith("{")
    assert list(path.parent.glob("*.tmp.*")) == []
