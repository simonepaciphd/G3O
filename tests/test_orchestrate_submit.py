"""Leg 1 — submitting a run, and surviving the shell that submitted it.

Two things are being pinned here. First, the config round-trip: a detached run is
configured by a file, and a file that silently drops a key is a run that spends
money on a configuration nobody chose. Second, the submit record: it is the only
witness to a failure that happens *before* the manifest exists, and the only
source of liveness afterwards.
"""

from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import replace
from pathlib import Path

import pytest

from g3o.run.api import LaunchValidationError, RunReceipt
from g3o.run.orchestrate import status as st
from g3o.run.orchestrate import submit as sub
from g3o.run.presweep.config import PresweepConfig

# institution_uid is required as of a7bca03: plan time refuses a sampled row
# without a well-formed one rather than emitting an empty column downstream.
MASTER_FIELDS = [
    "institution_uid",
    "master_row_id", "country", "government_level", "branch", "institution_type",
    "institution_name", "website", "source_dataset_id", "source_url",
    "source_file", "retrieval_date", "notes",
]


def _write_master(path: Path, n: int = 3) -> Path:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MASTER_FIELDS)
        writer.writeheader()
        for i in range(n):
            writer.writerow(
                {
                    "institution_uid": f"G3O-I-{i + 1:08d}",
                    "master_row_id": str(i + 1),
                    "country": f"COUNTRY-{i}",
                    "government_level": "national",
                    "branch": "executive",
                    "institution_type": "ministry",
                    "institution_name": f"Ministry {i}",
                    "website": "",
                    "source_dataset_id": "synth",
                    "source_url": "",
                    "source_file": "synth.csv",
                    "retrieval_date": "",
                    "notes": "synth",
                }
            )
    return path


@pytest.fixture()
def config(tmp_path: Path) -> PresweepConfig:
    return PresweepConfig(
        run_id="",
        runs_dir=tmp_path / "runs",
        master_csv=_write_master(tmp_path / "master.csv"),
        sample_size=2,
        seed=1,
        dry_run=True,
    )


# ---------------------------------------------------------------------------
# Config round-trip
# ---------------------------------------------------------------------------


def test_config_round_trips_through_json(config: PresweepConfig) -> None:
    payload = json.loads(json.dumps(sub.config_to_mapping(config)))
    rebuilt = sub.config_from_mapping(payload)

    assert rebuilt.sample_size == config.sample_size
    assert rebuilt.discovery_languages == config.discovery_languages
    assert isinstance(rebuilt.discovery_languages, tuple)
    assert isinstance(rebuilt.runs_dir, Path)
    assert rebuilt.master_csv.resolve() == config.master_csv.resolve()


def test_paths_are_absolute_so_a_detached_child_is_cwd_independent(
    config: PresweepConfig, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    relative = PresweepConfig(
        run_id="", runs_dir=Path("runs"), master_csv=Path("master.csv"), sample_size=1
    )
    mapping = sub.config_to_mapping(relative)
    assert Path(mapping["runs_dir"]).is_absolute()
    assert Path(mapping["master_csv"]).is_absolute()


def test_an_unknown_config_key_is_refused_not_ignored(config: PresweepConfig) -> None:
    mapping = sub.config_to_mapping(config)
    mapping["sampel_size"] = 999
    with pytest.raises(sub.SubmitError, match="unknown config key"):
        sub.config_from_mapping(mapping)


def test_underscore_keys_are_comments(config: PresweepConfig) -> None:
    """JSON has no comments, and the config file is meant to be read by people."""
    mapping = sub.config_to_mapping(config)
    mapping["_comment"] = "why this sample size"
    assert sub.config_from_mapping(mapping).sample_size == config.sample_size


def test_the_shipped_example_config_loads(config: PresweepConfig) -> None:
    """A worked example that does not load is worse than none at all."""
    example = Path(__file__).resolve().parent.parent / "scripts" / "orchestrator" / "run-config.example.json"
    loaded = sub.load_config_file(example)
    assert loaded.sample_size == 20
    assert loaded.dry_run is True


def test_a_config_the_pipeline_would_refuse_fails_at_load(config: PresweepConfig) -> None:
    """``__post_init__``'s language roster check (A7) stays a load-time refusal."""
    mapping = sub.config_to_mapping(config)
    mapping["discovery_languages"] = ["qq"]
    with pytest.raises(sub.SubmitError, match="invalid run config"):
        sub.config_from_mapping(mapping)


def test_load_config_file_rejects_non_objects(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(sub.SubmitError, match="not a readable JSON object"):
        sub.load_config_file(path)


# ---------------------------------------------------------------------------
# Foreground submit
# ---------------------------------------------------------------------------


def _fake_launch(receipt_outcome: str = "stopped"):
    def _launch(config, **_kwargs):
        run_dir = config.runs_dir / config.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return RunReceipt(
            run_id=config.run_id,
            run_started_at="2026-08-13T10:00:00Z",
            runs_dir=run_dir,
            manifest_path=run_dir / "manifest.json",
            events_path=run_dir / "events.jsonl",
            resumed=False,
            outcome=receipt_outcome,
            stop_after=config.stop_after,
            summary={"n_institutions": 2},
        )

    return _launch


def test_submit_mints_an_id_before_launching(config: PresweepConfig, monkeypatch) -> None:
    """The id exists before the fork, so it can be reported and monitored at once."""
    monkeypatch.setattr(sub, "launch", _fake_launch())

    receipt = sub.submit(config)

    assert receipt.run_id.startswith("r")
    assert receipt.run_dir.name == receipt.run_id
    assert (receipt.run_dir / st.ORCHESTRATOR_DIRNAME).is_dir()


def test_foreground_submit_records_the_supervising_process(
    config: PresweepConfig, monkeypatch
) -> None:
    monkeypatch.setattr(sub, "launch", _fake_launch())

    receipt = sub.submit(config)
    record = st.read_json(sub.submit_record_path(receipt.run_dir))

    assert record["pid"] == os.getpid()
    assert record["outcome"] == "stopped"
    assert record["finished_at"]
    # No `detached` key: the process that ran the launch does not claim to know
    # how it was started. Only a spawning parent writes that.
    assert "detached" not in record


def test_a_pre_manifest_failure_is_recorded_and_re_raised(
    config: PresweepConfig, monkeypatch
) -> None:
    """§1.5's window: no manifest, no events, so the record is the only witness."""

    def _boom(*_args, **_kwargs):
        raise LaunchValidationError("runs_dir is not writable")

    monkeypatch.setattr(sub, "launch", _boom)

    with pytest.raises(LaunchValidationError):
        sub.submit(config)

    runs = sorted((config.runs_dir).iterdir())
    record = st.read_json(sub.submit_record_path(runs[-1]))
    assert record["outcome"] == "failed"
    assert record["error_class"] == "LaunchValidationError"
    assert st.run_status(config.runs_dir, runs[-1].name).state == "failed"


def test_an_explicit_run_id_is_honoured_verbatim(config: PresweepConfig, monkeypatch) -> None:
    """Resume is not a mode: pass the id and re-invoke (spec §1.3)."""
    monkeypatch.setattr(sub, "launch", _fake_launch())
    from dataclasses import replace

    receipt = sub.submit(replace(config, run_id="20260509-presweep"))
    assert receipt.run_id == "20260509-presweep"


# ---------------------------------------------------------------------------
# The submit record's merge rule
# ---------------------------------------------------------------------------


def test_a_finished_record_is_not_downgraded_to_running(tmp_path: Path) -> None:
    """The race a fast run creates: the parent's post-spawn write lands last.

    Without the rule, a run that completed in less time than it took its parent
    to write the record would report "running" against a dead pid forever.
    """
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    sub.update_submit_record(run_dir, outcome="completed", finished_at="2026-08-13T10:05:00Z")
    sub.update_submit_record(run_dir, outcome="running", started_at="2026-08-13T10:00:00Z", pid=17)

    record = st.read_json(sub.submit_record_path(run_dir))
    assert record["outcome"] == "completed"
    assert record["finished_at"] == "2026-08-13T10:05:00Z"
    assert record["pid"] == 17  # the spawn facts still merge in


# ---------------------------------------------------------------------------
# Detached submit
# ---------------------------------------------------------------------------


def test_detached_submit_spawns_a_new_session(config: PresweepConfig, monkeypatch) -> None:
    """The mechanics: argv, the config file, the log, and the detach flags."""
    spawned: dict = {}

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            spawned["argv"] = argv
            spawned["kwargs"] = kwargs
            self.pid = 4242

    monkeypatch.setattr(sub.subprocess, "Popen", _FakePopen)

    receipt = sub.submit(config, detach=True, session_id="sess-1")

    assert receipt.detached and receipt.pid == 4242
    assert "--config" in spawned["argv"] and "--run-id" in spawned["argv"]
    assert receipt.run_id in spawned["argv"]
    assert "--session-id" in spawned["argv"]
    # No controlling terminal ⇒ the SIGHUP from a closing SSH session never lands.
    assert spawned["kwargs"].get("start_new_session") or spawned["kwargs"].get("creationflags")
    assert (receipt.run_dir / st.ORCHESTRATOR_DIRNAME / sub.SUBMIT_CONFIG_FILENAME).is_file()

    record = st.read_json(sub.submit_record_path(receipt.run_dir))
    assert record["pid"] == 4242 and record["detached"] is True


def test_no_key_material_travels_to_the_child(config: PresweepConfig, monkeypatch) -> None:
    """Keys stay in the environment (§3.1); only the operator's label crosses."""
    from g3o.common.credentials import Credentials

    spawned: dict = {}

    class _FakePopen:
        def __init__(self, argv, **kwargs):
            spawned["argv"] = argv
            self.pid = 1

    monkeypatch.setattr(sub.subprocess, "Popen", _FakePopen)
    secret = "sk-super-secret-value"  # noqa: S105 - a fixture, not a credential

    receipt = sub.submit(
        config,
        detach=True,
        credentials=Credentials(openai_api_key=secret, serper_api_key=secret, label="key-B"),
    )

    assert secret not in " ".join(spawned["argv"])
    assert "--key-label" in spawned["argv"] and "key-B" in spawned["argv"]
    config_text = (
        receipt.run_dir / st.ORCHESTRATOR_DIRNAME / sub.SUBMIT_CONFIG_FILENAME
    ).read_text(encoding="utf-8")
    assert secret not in config_text


def test_detached_dry_run_completes_without_the_parent(config: PresweepConfig) -> None:
    """End to end: a real child process, a real dry run, a real status read.

    Deliberately a dry run — the point is the supervision, not the sweep — and it
    exercises the one path that cannot be stubbed: this Python really can
    ``python -m g3o.run.orchestrate submit`` itself.
    """
    receipt = sub.submit(config, detach=True)

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        status = st.run_status(config.runs_dir, receipt.run_id)
        if status.is_terminal:
            break
        time.sleep(1)
    else:  # pragma: no cover - only on a machine too slow to import g3o in 3min
        pytest.fail(f"detached run did not finish; last state: {status.state}")

    assert status.state == "stopped"  # dry run: planned, spent nothing
    assert status.dry_run is True
    assert not status.publishable
    assert (receipt.log_path or Path()).is_file()


# ---------------------------------------------------------------------------
# The cost circuit breaker (2026-08-17)
# ---------------------------------------------------------------------------


def test_no_ceiling_means_no_preflight(config, monkeypatch) -> None:
    """The gate is opt-in. Absent a ceiling it must not run a projection at all."""
    called = False

    def _boom(*a, **k):  # pragma: no cover - asserted by `called`
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("g3o.run.preflight.run_preflight", _boom)
    assert sub.cost_gate(config, credentials=None, cost_ceiling_usd=None) is None
    assert not called


def test_a_dry_run_is_never_gated(config, monkeypatch) -> None:
    """A dry run spends nothing by construction, so a projection is noise."""
    monkeypatch.setattr(
        "g3o.run.preflight.run_preflight",
        lambda *a, **k: pytest.fail("a dry run must not be projected"),
    )
    dry = replace(config, dry_run=True)
    assert sub.cost_gate(dry, credentials=None, cost_ceiling_usd=25.0) is None


def test_a_projection_over_the_ceiling_refuses_before_launch(config, monkeypatch) -> None:
    """The refusal is the point: nothing is submitted and the message says so."""
    monkeypatch.setattr(
        "g3o.run.preflight.run_preflight",
        lambda *a, **k: {
            "cost_ceiling_exceeded": True,
            "cost_preview": {"est_openai_batch_total_usd": 99.5},
        },
    )
    live = replace(config, dry_run=False)

    with pytest.raises(sub.SubmitError, match="COST CIRCUIT BREAKER"):
        sub.cost_gate(live, credentials=None, cost_ceiling_usd=25.0)


def test_a_projection_under_the_ceiling_is_returned_for_the_record(config, monkeypatch) -> None:
    """The projection that CLEARED spend is evidence too, not only the one that blocks."""
    summary = {
        "cost_ceiling_exceeded": False,
        "cost_preview": {"est_openai_batch_total_usd": 0.14},
    }
    monkeypatch.setattr("g3o.run.preflight.run_preflight", lambda *a, **k: summary)
    live = replace(config, dry_run=False)

    assert sub.cost_gate(live, credentials=None, cost_ceiling_usd=25.0) == summary


# ---------------------------------------------------------------------------
# The run-id collision guard (PI ruling 2026-08-14 §5)
# ---------------------------------------------------------------------------
#
# A reused run id currently collides at ingest, after the compute is spent.
# ``psycopg`` is an optional droplet-only dependency, so every test here injects
# a fake one: the guard's behaviour must be pinned on machines that will never
# have a driver, which includes CI and the PI's laptop.


class _FakeCursor:
    def __init__(self, rows, recorder):
        self._rows, self._recorder = rows, recorder

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._recorder.append((sql, params))

    def fetchone(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows, recorder):
        self._rows, self._recorder = rows, recorder

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return _FakeCursor(self._rows, self._recorder)


class _FakePsycopg:
    """Minimal stand-in: ``connect`` → context manager → ``cursor`` → ``fetchone``."""

    def __init__(self, rows, *, error: Exception | None = None):
        self.rows, self.error, self.executed = rows, error, []

    def connect(self, dsn, connect_timeout=None):
        if self.error:
            raise self.error
        return _FakeConn(self.rows, self.executed)


@pytest.fixture()
def live(config: PresweepConfig) -> PresweepConfig:
    """A live, explicitly-named run — the only shape the guard applies to."""
    return replace(config, dry_run=False, run_id="r20260817T120000Z-abcd")


def _install(monkeypatch, fake) -> None:
    monkeypatch.setitem(__import__("sys").modules, "psycopg", fake)
    monkeypatch.setenv(sub.DSN_ENV_VAR, "postgresql://u:p@h/db")


def test_a_dry_run_never_queries_the_registry(config, monkeypatch) -> None:
    """A dry run spends nothing, so a collision costs nothing to discover later."""
    fake = _FakePsycopg(rows=(1,))
    _install(monkeypatch, fake)

    verdict = sub.run_id_collision_gate(replace(config, run_id="x", dry_run=True))

    assert verdict["verdict"] == "skipped"
    assert fake.executed == []


def test_an_unset_dsn_skips_loudly_rather_than_refusing(live, monkeypatch, caplog) -> None:
    """Fails open — but the record says the guard did not run, not that it passed."""
    monkeypatch.delenv(sub.DSN_ENV_VAR, raising=False)

    with caplog.at_level("WARNING"):
        verdict = sub.run_id_collision_gate(live)

    assert verdict == {"verdict": "skipped", "reason": f"{sub.DSN_ENV_VAR} unset"}
    assert "DID NOT RUN" in caplog.text


def test_a_missing_driver_skips_loudly_with_an_install_instruction(
    live, monkeypatch, caplog
) -> None:
    monkeypatch.setenv(sub.DSN_ENV_VAR, "postgresql://u:p@h/db")
    monkeypatch.setitem(__import__("sys").modules, "psycopg", None)

    with caplog.at_level("WARNING"):
        verdict = sub.run_id_collision_gate(live)

    assert verdict["verdict"] == "skipped"
    assert "psycopg[binary]" in caplog.text


def test_an_unreachable_database_skips_rather_than_blocking_the_run(
    live, monkeypatch, caplog
) -> None:
    """A briefly unreachable registry must not cost a run its start."""
    _install(monkeypatch, _FakePsycopg(rows=None, error=OSError("connection refused")))

    with caplog.at_level("WARNING"):
        verdict = sub.run_id_collision_gate(live)

    assert verdict["verdict"] == "skipped"
    assert "connection refused" in verdict["reason"]
    assert "DID NOT RUN" in caplog.text


def test_an_unused_run_id_is_clear(live, monkeypatch) -> None:
    fake = _FakePsycopg(rows=None)
    _install(monkeypatch, fake)

    assert sub.run_id_collision_gate(live)["verdict"] == "clear"
    sql, params = fake.executed[0]
    assert "g3o.runs" in sql and params == (live.run_id,)


def test_a_loaded_run_id_refuses_before_any_spend(live, monkeypatch) -> None:
    """The whole point: fail before the run, not at ingest after it."""
    _install(monkeypatch, _FakePsycopg(rows=(1,)))

    with pytest.raises(sub.SubmitError, match="RUN ID ALREADY LOADED"):
        sub.run_id_collision_gate(live, resuming=False)


def test_a_loaded_run_id_being_resumed_is_not_a_collision(live, monkeypatch, caplog) -> None:
    """Re-ingesting the same run is an idempotent upsert (spec §5.3), not a clash."""
    _install(monkeypatch, _FakePsycopg(rows=(1,)))

    with caplog.at_level("WARNING"):
        verdict = sub.run_id_collision_gate(live, resuming=True)

    assert verdict["verdict"] == "resume"
    assert "resume" in caplog.text


def test_resuming_is_inferred_from_the_run_directory(live, monkeypatch) -> None:
    """Absent an explicit answer, an existing runs/<id>/ IS the resume signal."""
    _install(monkeypatch, _FakePsycopg(rows=(1,)))
    (live.runs_dir / live.run_id).mkdir(parents=True)

    assert sub.run_id_collision_gate(live)["verdict"] == "resume"


def test_a_minted_id_is_not_checked_and_the_record_says_why(config, monkeypatch) -> None:
    """A minted id cannot name a loaded run, so the round trip is pure cost."""
    fake = _FakePsycopg(rows=(1,))
    _install(monkeypatch, fake)

    receipt = sub.submit(config)  # run_id="" ⇒ minted

    record = st.read_json(sub.submit_record_path(receipt.run_dir))
    assert record["run_id_check"]["verdict"] == "skipped"
    assert "minted" in record["run_id_check"]["reason"]
    assert fake.executed == []  # never opened a connection
