"""The induced-failure gate the Item 3 brief requires the joint gate to assert.

    *"An induced failure (kill a stage mid-flight) must end in a named failed
    state with the cause in events and nothing published — build that test, the
    joint gate asserts it."*

Three claims, and each is checked against a **real** run rather than a fixture:
a live-mode run is launched through ``launch()`` with one stage rigged to die.

1. **A named failed state.** ``status.state == "failed"``, and ``is_failed``,
   so no monitor and no downstream leg has to interpret an ambiguity.
2. **The cause in events.** ``run_failed`` carries the exception class and its
   message, per §1.5's rule that every post-manifest raise is preceded by it.
3. **Nothing published.** The ingest leg refuses the run outright, which is the
   mechanism — not a convention — and publish-verify, asked whether the API can
   see it, expects invisibility and passes on finding it.

A killed *process* is the harder half of "mid-flight", because such a run cannot
write ``run_failed`` about itself: the last test takes the real failed run's
directory and reduces it to exactly what a ``SIGKILL`` leaves behind — a log that
stops, ``_state/`` intact, the process gone — and asserts the orchestrator still
reaches a named failed state and still refuses to publish.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from g3o.run.orchestrate import ingest as ing
from g3o.run.orchestrate import publish as pub
from g3o.run.orchestrate import submit as sub
from g3o.run.orchestrate.archive_leg import ArchiveLegError, archive_and_upload
from g3o.run.orchestrate.status import EVENTS_FILENAME, read_events, run_status
from g3o.run.presweep import orchestrator as presweep_orchestrator
from g3o.run.presweep.config import PresweepConfig
from tests._orchestrate import write_submit_record

INDUCED = "induced failure: Stage 1a was killed mid-flight"

# institution_uid is required as of a7bca03: plan time refuses a sampled row
# without a well-formed one rather than emitting an empty column downstream.
MASTER_FIELDS = [
    "institution_uid",
    "master_row_id", "country", "government_level", "branch", "institution_type",
    "institution_name", "website", "source_dataset_id", "source_url",
    "source_file", "retrieval_date", "notes",
]


@pytest.fixture()
def master(tmp_path: Path) -> Path:
    path = tmp_path / "master.csv"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MASTER_FIELDS)
        writer.writeheader()
        for i in range(3):
            writer.writerow(
                {
                    "institution_uid": f"G3O-I-{i + 1:08d}",
                    "master_row_id": str(i + 1), "country": f"COUNTRY-{i}",
                    "government_level": "national", "branch": "executive",
                    "institution_type": "ministry", "institution_name": f"Ministry {i}",
                    "website": "", "source_dataset_id": "synth", "source_url": "",
                    "source_file": "synth.csv", "retrieval_date": "", "notes": "synth",
                }
            )
    return path


@pytest.fixture()
def killed_run(tmp_path: Path, master: Path, monkeypatch) -> tuple[Path, str]:
    """Launch a live run whose first stage dies. Returns ``(runs_dir, run_id)``.

    Live mode (``dry_run=False``) is what makes this a real test of the failure
    path: a dry run returns before any stage is dispatched, so it could never
    exercise the ``run_failed`` emit site. No spend happens — the stage raises
    before it issues a request, and the two keys below are never used.
    """
    monkeypatch.setenv("SERPER_API_KEY", "test-serper-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    def _die(*_args, **_kwargs):
        raise RuntimeError(INDUCED)

    monkeypatch.setattr(presweep_orchestrator, "_run_discovery_general", _die)

    config = PresweepConfig(
        run_id="",
        runs_dir=tmp_path / "runs",
        master_csv=master,
        sample_size=2,
        seed=1,
        dry_run=False,
        stop_after="extract",
    )
    with pytest.raises(RuntimeError, match="induced failure"):
        sub.submit(config)

    runs_dir = tmp_path / "runs"
    run_id = next(p.name for p in runs_dir.iterdir() if p.is_dir())
    return runs_dir, run_id


# ---------------------------------------------------------------------------
# 1 + 2 — a named state, and the cause in the events
# ---------------------------------------------------------------------------


def test_the_run_ends_in_a_named_failed_state(killed_run: tuple[Path, str]) -> None:
    runs_dir, run_id = killed_run
    status = run_status(runs_dir, run_id)

    assert status.state == "failed"
    assert status.is_failed
    assert not status.publishable
    assert status.stage_in_flight == "discovery_general"


def test_the_cause_is_in_the_event_log(killed_run: tuple[Path, str]) -> None:
    runs_dir, run_id = killed_run
    events = read_events(runs_dir / run_id / EVENTS_FILENAME)

    terminal = [e for e in events if e["event"] == "run_failed"]
    assert len(terminal) == 1, "exactly one terminal event, and it names the failure"
    payload = terminal[0]["payload"]
    assert payload["error_class"] == "RuntimeError"
    assert INDUCED in payload["error_message"]
    # §1.5: the terminal event precedes the raise, so it is the last line written.
    assert events[-1]["event"] == "run_failed"


def test_the_status_one_liner_names_the_cause(killed_run: tuple[Path, str]) -> None:
    runs_dir, run_id = killed_run
    line = run_status(runs_dir, run_id).one_line()

    assert "FAILED" in line
    assert "RuntimeError" in line


def test_the_submit_record_agrees_with_the_events(killed_run: tuple[Path, str]) -> None:
    runs_dir, run_id = killed_run
    record = json.loads(sub.submit_record_path(runs_dir / run_id).read_text(encoding="utf-8"))

    assert record["outcome"] == "failed"
    assert record["finished_at"]
    assert INDUCED in record["error_message"]


# ---------------------------------------------------------------------------
# 3 — nothing published
# ---------------------------------------------------------------------------


def test_ingest_refuses_the_failed_run(
    killed_run: tuple[Path, str], tmp_path: Path, monkeypatch
) -> None:
    """The mechanism behind "nothing published": a refusal, before the loader runs."""
    runs_dir, run_id = killed_run
    repo = tmp_path / "g3o-website"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "ingest.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setenv(ing.DSN_ENV_VAR, "postgresql://u:p@host/db")

    with pytest.raises(ing.IngestError, match="refusing to ingest"):
        ing.ingest_run(runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo)

    # And it refused before invoking anything: no ingest leg record, no log.
    assert run_status(runs_dir, run_id).legs.get("ingest") is None


def test_publish_verify_expects_invisibility_and_finds_it(
    killed_run: tuple[Path, str]
) -> None:
    runs_dir, run_id = killed_run

    def _not_found(url: str, _params: dict) -> tuple[int, object]:
        if url.endswith("/aggregate"):
            return 200, {"meta": {"wave": "w001"}}
        return 404, {"error": {"code": "not_found"}}

    result = pub.verify_published(
        runs_dir, run_id, api_base="https://api.example.org", getter=_not_found
    )

    assert result.expect_visible is False
    # A run that died at Stage 1a has no Stage-7 output at all, so there is
    # nothing that could have been published — which is the honest verdict.
    assert result.verdict == "not_verifiable"
    assert result.n_visible == 0


def test_archive_refuses_a_run_that_may_still_be_resumed(
    killed_run: tuple[Path, str]
) -> None:
    """A failed run's institution tree is what a resume writes into."""
    runs_dir, run_id = killed_run

    with pytest.raises(ArchiveLegError, match="refusing to archive"):
        archive_and_upload(runs_dir, run_id, apply=True)


# ---------------------------------------------------------------------------
# The harder half — a process that was killed and could not say so
# ---------------------------------------------------------------------------


def test_a_killed_process_still_reaches_a_named_failed_state(
    killed_run: tuple[Path, str], monkeypatch
) -> None:
    """Reduce the real run to exactly what a SIGKILL leaves behind, then ask.

    Removing the ``run_failed`` line is not cosmetic — it is the whole
    difference between a stage that raised (and got to write its cause) and a
    process that was killed (and did not). Everything else is identical: the
    manifest, ``_state/``, and a log that simply stops.
    """
    from g3o.run.orchestrate import status as st

    runs_dir, run_id = killed_run
    run_dir = runs_dir / run_id
    events_path = run_dir / EVENTS_FILENAME
    kept = [
        line
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if '"run_failed"' not in line
    ]
    events_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    write_submit_record(run_dir, pid=424242, outcome="running", detached=True)
    monkeypatch.setattr(st, "process_liveness", lambda *a, **k: "dead")

    status = st.run_status(runs_dir, run_id)

    assert status.state == "interrupted"
    assert status.is_failed
    assert not status.publishable
    assert "re-invoke the same run id to rejoin" in status.failure["error_message"]


def test_a_killed_run_is_also_refused_by_ingest(
    killed_run: tuple[Path, str], tmp_path: Path, monkeypatch
) -> None:
    from g3o.run.orchestrate import status as st

    runs_dir, run_id = killed_run
    run_dir = runs_dir / run_id
    events_path = run_dir / EVENTS_FILENAME
    events_path.write_text(
        "\n".join(
            line
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if '"run_failed"' not in line
        )
        + "\n",
        encoding="utf-8",
    )
    write_submit_record(run_dir, pid=424242, outcome="running")
    monkeypatch.setattr(st, "process_liveness", lambda *a, **k: "dead")
    repo = tmp_path / "g3o-website"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "ingest.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setenv(ing.DSN_ENV_VAR, "postgresql://u:p@host/db")

    with pytest.raises(ing.IngestError, match="interrupted"):
        ing.ingest_run(runs_dir, run_id, frame_id='mb-TEST', loader_repo=repo)
