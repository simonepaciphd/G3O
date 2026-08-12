"""Manifest + event log — Run API spec v0.1 §4 (PR C).

The published fixtures (``tests/fixtures/run_contract/``) are the contract the
backend loader was written against, so most of this file asserts *their* stated
invariants rather than this implementation's conveniences:

* the manifest carries every §4.1 field, with no key material anywhere;
* ``config_hash`` follows the pinned canonicalization and ignores the three
  recorded exclusions;
* the event envelope is the six keys plus optional ``stage``, payload nested;
* ``seq`` starts at 1 and stays contiguous **across a resume**;
* ``ts`` never decreases, even if the clock steps backwards;
* the log's last line is terminal, and ``run_stopped`` appears mid-file only when
  a ``resume`` follows it;
* telemetry never aborts a run (§4.4) — the one property that has to hold when
  everything else here fails.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from g3o.common.contract_pin import contract_surface
from g3o.common.credentials import Credentials, resolve
from g3o.run import telemetry as tel_mod
from g3o.run.api import GitMetadata, launch
from g3o.run.presweep import PresweepConfig, run_presweep
from g3o.run.presweep.planning import config_snapshot
from g3o.run.telemetry import (
    CONFIG_HASH_EXCLUDES,
    MANIFEST_SCHEMA_VERSION,
    RunTelemetry,
    build_manifest_block,
    config_hash,
    master_build_id,
    preserve_identity,
    prompt_hashes,
    read_last_seq,
)

ENVELOPE_KEYS = {"ts", "run_id", "session_id", "git_sha", "seq", "event"}
TERMINAL_EVENTS = {"run_completed", "run_stopped", "run_failed"}
FAKE_KEY = "sk-telemetry-QQQ-must-not-appear"


def _write_master(path: Path, n: int = 3, *, build_id: str | None = None) -> Path:
    extra = ",master_build_id" if build_id else ""
    header = (
        "master_row_id,institution_name,country,branch,government_level,"
        f"institution_type,website,official_site_url,official_site_confidence{extra}\n"
    )
    rows = "".join(
        f"{i},Ministry {i},Atlantis,executive,national,ministry,,,"
        + (f",{build_id}\n" if build_id else "\n")
        for i in range(n)
    )
    path.write_text(header + rows, encoding="utf-8")
    return path


def _config(tmp_path: Path, **kw) -> PresweepConfig:
    defaults = dict(
        run_id="",
        runs_dir=tmp_path / "runs",
        master_csv=_write_master(tmp_path / "master.csv"),
        sample_size=3,
        seed=22294,
    )
    defaults.update(kw)
    return PresweepConfig(**defaults)


def _events(run_dir: Path) -> list[dict]:
    path = run_dir / "events.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _launch_dry(tmp_path: Path, **kw) -> tuple[Path, dict]:
    receipt = launch(_config(tmp_path, **kw), session_id="sess-1", invocation="cli")
    manifest = json.loads(receipt.manifest_path.read_text(encoding="utf-8"))
    return receipt.runs_dir, manifest


# ---------------------------------------------------------------------------
# §4.1 — the manifest
# ---------------------------------------------------------------------------


def test_manifest_carries_every_documented_field(tmp_path: Path) -> None:
    _, manifest = _launch_dry(tmp_path)
    for key in (
        "manifest_schema_version", "run_id", "run_started_at", "session_id",
        "operator", "hostname", "invocation", "code", "frame", "contract",
        "prompts", "config", "config_hash", "config_hash_excludes",
        "credentials", "model_ids",
    ):
        assert key in manifest, f"§4.1 field {key!r} missing"
    assert manifest["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["invocation"] == "cli"
    assert manifest["session_id"] == "sess-1"
    assert set(manifest["code"]) == {
        "git_sha", "git_dirty", "package_version", "install_path"
    }
    assert set(manifest["frame"]) == {"frame_id", "master_build_id"}
    assert manifest["model_ids"]["requested"]["batch_stages"] == "gpt-5-nano"


def test_manifest_keeps_the_planning_half(tmp_path: Path) -> None:
    """One file, two readers: the resume guard's keys must survive the merge."""
    _, manifest = _launch_dry(tmp_path)
    for key in (
        "run_kind", "layout_version", "run_date", "run_timestamp", "run_model",
        "stages_planned", "institutions", "config",
    ):
        assert key in manifest, f"planning field {key!r} lost to the telemetry merge"
    # The two values the resume guard compares are inside the config snapshot.
    assert "genai_terms_roster_hash" in manifest["config"]
    assert "institution_search_languages" in manifest["config"]


def test_manifest_contract_block_is_the_enforced_pin(tmp_path: Path) -> None:
    """§4.1's "same pin PR #29 enforces" — asserted, not asserted-in-prose."""
    _, manifest = _launch_dry(tmp_path)
    assert manifest["contract"] == contract_surface()
    golden = json.loads(
        Path("tests/goldens/contract_version_pin.json").read_text(encoding="utf-8")
    )
    assert manifest["contract"] == golden


def test_manifest_prompt_hashes_are_whole_file_hashes(tmp_path: Path) -> None:
    _, manifest = _launch_dry(tmp_path)
    assert manifest["prompts"] == prompt_hashes()
    assert len(manifest["prompts"]) == 4
    # The same path appears in both blocks with *different* hashes, by design: the
    # contract pin covers the machine-readable surface, this covers file bytes.
    path = "g3o/extract/prompts/output_contract.md"
    assert manifest["prompts"][path] != manifest["contract"]["extract"]["sha256"]


def test_config_hash_matches_the_pinned_canonicalization(tmp_path: Path) -> None:
    _, manifest = _launch_dry(tmp_path)
    import hashlib

    hashed = {
        k: v for k, v in manifest["config"].items()
        if k not in manifest["config_hash_excludes"]
    }
    canonical = json.dumps(
        hashed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert manifest["config_hash"] == hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    assert manifest["config_hash_excludes"] == list(CONFIG_HASH_EXCLUDES)


def test_config_hash_ignores_where_the_run_ran(tmp_path: Path) -> None:
    """Two runs differing only in id, runs_dir and master path are one instrument."""
    base = {"sample_size": 1000, "seed": 22294}
    a = {**base, "run_id": "r1", "runs_dir": "/a", "master_csv": "/m1.csv"}
    b = {**base, "run_id": "r2", "runs_dir": "/b", "master_csv": "/m2.csv"}
    assert config_hash(a) == config_hash(b) == config_hash(base)
    assert config_hash({**base, "seed": 1}) != config_hash(base)


def test_manifest_is_written_before_any_stage_could_spend(tmp_path: Path) -> None:
    """§4.1: written by launch() before any spend, so a crash still leaves a record.

    Asserted by making the first stage raise: the manifest and the launch event
    must already be on disk when it does.
    """
    from g3o.run.presweep import orchestrator

    def _boom(*a, **kw):
        raise RuntimeError("stage 1a exploded")

    run_dir = tmp_path / "runs" / "spend-1"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(orchestrator, "_run_discovery_general", _boom)
        with pytest.raises(RuntimeError, match="exploded"):
            launch(
                _config(
                    tmp_path, run_id="spend-1", dry_run=False, stop_after="extract",
                ),
                credentials=Credentials(openai_api_key="sk-x", serper_api_key="s"),
            )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION
    assert [e["event"] for e in _events(run_dir)][0] == "run_launched"


def test_manifest_write_is_atomic(tmp_path: Path) -> None:
    """No temp file survives, and nothing reaches the destination un-swapped."""
    run_dir, _ = _launch_dry(tmp_path)
    assert list(run_dir.glob("manifest.json.tmp*")) == []


def test_direct_run_presweep_writes_no_telemetry(tmp_path: Path) -> None:
    """Telemetry arrives only through launch() (§4.1), so the old path is unchanged.

    This is what keeps the byte-identical guarantee for every caller and test that
    predates the Run API — and what makes the manifest merge safe to review.
    """
    summary = run_presweep(_config(tmp_path, run_id="direct-1"))
    run_dir = Path(summary["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "manifest_schema_version" not in manifest
    assert not (run_dir / "events.jsonl").exists()


# --- frame block ------------------------------------------------------------


def test_frame_records_a_master_build_id_when_the_master_has_one(
    tmp_path: Path,
) -> None:
    master = _write_master(tmp_path / "m.csv", build_id="mb-2026-07-30")
    _, manifest = _launch_dry(tmp_path, master_csv=master)
    assert manifest["frame"]["master_build_id"] == "mb-2026-07-30"
    # frame_id stays null until §5.1's frames design is signed off.
    assert manifest["frame"]["frame_id"] is None


def test_frame_is_null_when_the_master_declares_no_build(tmp_path: Path) -> None:
    _, manifest = _launch_dry(tmp_path)
    assert manifest["frame"] == {"frame_id": None, "master_build_id": None}


def test_disagreeing_build_ids_record_null_rather_than_a_guess() -> None:
    rows = [{"master_build_id": "mb-2026-07-30"}, {"master_build_id": "mb-2026-08-01"}]
    assert master_build_id(rows) is None
    assert master_build_id([{"master_build_id": " mb-2026-07-30 "}]) == "mb-2026-07-30"
    assert master_build_id([{}, {"master_build_id": ""}]) is None


# --- resume preserves identity ---------------------------------------------


def test_resume_preserves_the_launching_runs_identity(tmp_path: Path) -> None:
    """``run_started_at`` is authoritative for wave classification (§5.5).

    Before this, every invocation refreshed the planning timestamp, so a resumed
    run reported the *resume* moment as its start — and would have been filed into
    whichever wave window that fell in.
    """
    first = launch(
        _config(tmp_path, run_id="resume-1"), session_id="sess-first",
        invocation="cli",
    )
    manifest_a = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    tel_mod.state_dir(first.runs_dir).mkdir(parents=True, exist_ok=True)

    launch(
        _config(tmp_path, run_id="resume-1"), session_id="sess-second",
        invocation="api",
    )
    manifest_b = json.loads(first.manifest_path.read_text(encoding="utf-8"))

    assert manifest_b["run_started_at"] == manifest_a["run_started_at"]
    assert manifest_b["session_id"] == "sess-first"
    assert manifest_b["invocation"] == "cli"
    assert manifest_b["config_hash"] == manifest_a["config_hash"]
    # The planning half still refreshes — it describes this invocation's plan.
    assert "run_timestamp" in manifest_b


def test_preserve_identity_only_keeps_identity_keys() -> None:
    existing = {"run_started_at": "old", "run_timestamp": "old", "session_id": "old"}
    fresh = {"run_started_at": "new", "run_timestamp": "new", "session_id": "new"}
    merged = preserve_identity(existing, fresh)
    assert merged["run_started_at"] == "old"
    assert merged["session_id"] == "old"
    assert merged["run_timestamp"] == "new"


def test_preserve_identity_tolerates_a_manifest_without_a_block() -> None:
    """A run planned before PR C, resumed after it, must not lose its planning half."""
    merged = preserve_identity({"run_kind": "pre-sweep"}, {"run_started_at": "new"})
    assert merged == {"run_started_at": "new"}


# ---------------------------------------------------------------------------
# §4.3 — the event log and the published loader invariants
# ---------------------------------------------------------------------------


def test_envelope_is_the_six_keys_plus_payload(tmp_path: Path) -> None:
    run_dir, _ = _launch_dry(tmp_path)
    for event in _events(run_dir):
        assert ENVELOPE_KEYS <= set(event)
        assert set(event) <= ENVELOPE_KEYS | {"stage", "payload"}
        assert isinstance(event["payload"], dict)


def test_one_file_one_run_id(tmp_path: Path) -> None:
    """Loader invariant 1."""
    run_dir, manifest = _launch_dry(tmp_path)
    assert {e["run_id"] for e in _events(run_dir)} == {manifest["run_id"]}


def test_seq_starts_at_one_and_is_contiguous_across_a_resume(tmp_path: Path) -> None:
    """Loader invariant 2 — the PK is ``(run_id, seq)``, so a gap is a lost row."""
    receipt = launch(_config(tmp_path, run_id="seq-1"), session_id="s1")
    tel_mod.state_dir(receipt.runs_dir).mkdir(parents=True, exist_ok=True)
    launch(_config(tmp_path, run_id="seq-1"), session_id="s2")
    launch(_config(tmp_path, run_id="seq-1"), session_id="s3")

    seqs = [e["seq"] for e in _events(receipt.runs_dir)]
    assert seqs == list(range(1, len(seqs) + 1))
    assert len(seqs) >= 6


def test_session_id_varies_across_invocations_within_one_run(tmp_path: Path) -> None:
    """Loader invariant 6 — join on run_id; session_id is per-event provenance."""
    receipt = launch(_config(tmp_path, run_id="sess-vary"), session_id="s1")
    tel_mod.state_dir(receipt.runs_dir).mkdir(parents=True, exist_ok=True)
    launch(_config(tmp_path, run_id="sess-vary"), session_id="s2")
    assert {e["session_id"] for e in _events(receipt.runs_dir)} == {"s1", "s2"}


def test_last_line_is_terminal(tmp_path: Path) -> None:
    """Loader invariant 4."""
    run_dir, _ = _launch_dry(tmp_path)
    assert _events(run_dir)[-1]["event"] in TERMINAL_EVENTS


def test_run_stopped_mid_file_is_followed_by_resume(tmp_path: Path) -> None:
    """Loader invariant 4's second half, which is what makes a resume readable."""
    receipt = launch(_config(tmp_path, run_id="mid-1"), session_id="s1")
    tel_mod.state_dir(receipt.runs_dir).mkdir(parents=True, exist_ok=True)
    launch(_config(tmp_path, run_id="mid-1"), session_id="s2")

    events = _events(receipt.runs_dir)
    for i, event in enumerate(events[:-1]):
        if event["event"] == "run_stopped":
            assert events[i + 1]["event"] == "resume"


def test_resume_event_reports_what_it_rejoined(tmp_path: Path) -> None:
    receipt = launch(_config(tmp_path, run_id="rejoin-1"), session_id="s1")
    tel_mod.state_dir(receipt.runs_dir).mkdir(parents=True, exist_ok=True)
    launch(
        _config(tmp_path, run_id="rejoin-1"), session_id="s2",
        credentials=Credentials(openai_api_key=FAKE_KEY),
    )
    resume = [e for e in _events(receipt.runs_dir) if e["event"] == "resume"]
    assert len(resume) == 1
    assert set(resume[0]["payload"]) == {
        "stages_done", "chunks_rejoined", "key_fingerprint"
    }


def test_dry_run_closes_the_log_out_as_stopped(tmp_path: Path) -> None:
    """A planning-only run must not read as a finished sweep — same rule as the
    receipt's ``outcome`` (PR B), so a monitor cannot print green over no data."""
    run_dir, _ = _launch_dry(tmp_path)
    last = _events(run_dir)[-1]
    assert last["event"] == "run_stopped"
    assert last["payload"]["reason"] == "dry_run"


def test_ts_is_non_decreasing_even_if_the_clock_steps_back(tmp_path: Path) -> None:
    """Loader invariant 3 — an NTP correction must not break a published guarantee."""
    telemetry = RunTelemetry(session_id="s", git=GitMetadata(available=False))
    moments = iter([
        datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc),  # run_launched
        datetime(2026, 8, 11, 12, 0, 5, tzinfo=timezone.utc),
        datetime(2026, 8, 11, 12, 0, 1, tzinfo=timezone.utc),  # clock steps back
        datetime(2026, 8, 11, 12, 0, 9, tzinfo=timezone.utc),
    ])
    with pytest.MonkeyPatch.context() as mp:
        # Patched before open(), so the run_launched event uses the scripted clock
        # too — otherwise every scripted moment lands below the real one and the
        # clamp is asserted vacuously.
        mp.setattr(tel_mod, "_utc_now", lambda: next(moments))
        telemetry.open(tmp_path, "r1", resumed=False)
        telemetry.emit("stage_started", stage="scrape", counts_in=1)
        telemetry.emit("stage_started", stage="extract", counts_in=1)
        telemetry.emit("stage_started", stage="validate", counts_in=1)
    stamps = [e["ts"] for e in _events(tmp_path)]
    assert stamps == sorted(stamps)
    assert stamps == [
        "2026-08-11T12:00:00Z",
        "2026-08-11T12:00:05Z",
        "2026-08-11T12:00:05Z",  # the backwards step, clamped rather than rewound
        "2026-08-11T12:00:09Z",
    ]


def test_read_last_seq_tolerates_a_torn_final_line(tmp_path: Path) -> None:
    """A crashed run's log can end mid-line; a resume still must not reuse a seq."""
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"seq": 1, "event": "run_launched"}\n'
        '{"seq": 2, "event": "stage_started"}\n'
        '{"seq": 3, "even',
        encoding="utf-8",
    )
    assert read_last_seq(path) == 2
    assert read_last_seq(tmp_path / "absent.jsonl") == 0


# ---------------------------------------------------------------------------
# §4.4 — telemetry never aborts a run
# ---------------------------------------------------------------------------


def test_an_unwritable_event_log_does_not_abort_the_run(
    tmp_path: Path, caplog
) -> None:
    """§4.4, the property everything else here depends on.

    Simulated at the write boundary rather than by chmod, which is unreliable on
    Windows: the run has to survive whatever the filesystem does.
    """
    import builtins

    real_open = builtins.open

    def _fail_on_events(path, *a, **kw):
        if str(path).endswith("events.jsonl"):
            raise OSError("disk full")
        return real_open(path, *a, **kw)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(builtins, "open", _fail_on_events)
        receipt = launch(_config(tmp_path, run_id="isolated-1"), session_id="s1")

    assert receipt.run_id == "isolated-1"
    assert receipt.summary["dry_run"] is True
    assert "telemetry" in caplog.text.lower()


def test_emit_never_raises_on_a_bad_payload(tmp_path: Path) -> None:
    telemetry = RunTelemetry(session_id="s", git=GitMetadata(available=False))
    telemetry.open(tmp_path, "r1", resumed=False)
    telemetry.emit("stage_started", stage="scrape", counts_in={1, 2, 3})  # not JSON
    # The bad line is dropped, the log stays parseable, and the run continues.
    telemetry.emit("stage_completed", stage="scrape", counts_in=1, counts_out=1)
    assert [e["event"] for e in _events(tmp_path)] == [
        "run_launched", "stage_completed"
    ]


def test_disabled_telemetry_writes_nothing(tmp_path: Path) -> None:
    telemetry = RunTelemetry.disabled()
    telemetry.open(tmp_path, "r1", resumed=False)
    telemetry.emit("run_launched")
    telemetry.run_completed(stop_after="validate")
    assert not (tmp_path / "events.jsonl").exists()


# ---------------------------------------------------------------------------
# §3.3 — secrecy, extended over the new files
# ---------------------------------------------------------------------------


def test_no_key_material_in_the_manifest_or_the_event_log(
    tmp_path: Path, monkeypatch
) -> None:
    """The PR A secrecy grep, re-run now that two more files exist in the tree."""
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("SERPER_API_KEY", "serper-QQQ-secret")
    receipt = launch(
        _config(tmp_path, run_id="secrecy-2"),
        credentials=Credentials(label="key-B-grant"),
        session_id="s1",
    )
    files = [p for p in receipt.runs_dir.rglob("*") if p.is_file()]
    assert any(p.name == "events.jsonl" for p in files)
    assert any(p.name == "manifest.json" for p in files)
    for path in files:
        blob = path.read_bytes()
        assert FAKE_KEY.encode() not in blob, f"key leaked into {path}"
        assert b"serper-QQQ-secret" not in blob, f"key leaked into {path}"
    manifest = json.loads(receipt.manifest_path.read_text(encoding="utf-8"))
    assert manifest["credentials"]["openai"]["fingerprint"]
    assert manifest["credentials"]["openai"]["label"] == "key-B-grant"


def test_run_failed_records_the_cause_without_leaking_it(
    tmp_path: Path, monkeypatch
) -> None:
    """§1.5 — run_failed precedes every post-manifest raise, and names the class."""
    from g3o.run.presweep import orchestrator

    monkeypatch.setattr(
        orchestrator, "_run_discovery_general",
        lambda *a, **kw: (_ for _ in ()).throw(ValueError("stage 1a died")),
    )
    with pytest.raises(ValueError, match="stage 1a died"):
        launch(
            _config(tmp_path, run_id="failed-1", dry_run=False, stop_after="extract"),
            credentials=Credentials(openai_api_key=FAKE_KEY, serper_api_key="s"),
        )
    events = _events(tmp_path / "runs" / "failed-1")
    last = events[-1]
    assert last["event"] == "run_failed"
    assert last["payload"]["error_class"] == "ValueError"
    assert last["payload"]["error_message"] == "stage 1a died"
    assert FAKE_KEY not in json.dumps(events)


# ---------------------------------------------------------------------------
# The manifest block builder, in isolation
# ---------------------------------------------------------------------------


def test_build_manifest_block_shape(tmp_path: Path) -> None:
    config = _config(tmp_path, run_id="block-1")
    block = build_manifest_block(
        run_id="block-1",
        run_started_at="2026-08-11T12:00:00Z",
        session_id="s1",
        invocation="api",
        git=GitMetadata(
            available=True, sha="a" * 40, dirty=False,
            package_version="0.1.0", install_path="/srv/G3O",
        ),
        config_snapshot=config_snapshot(config),
        credentials=resolve(Credentials(openai_api_key=FAKE_KEY, label="lbl")),
        model="gpt-5-nano",
        sample=[],
    )
    assert block["code"]["git_sha"] == "a" * 40
    assert block["code"]["git_dirty"] is False
    assert block["credentials"]["openai"]["label"] == "lbl"
    assert FAKE_KEY not in json.dumps(block)


def test_git_dirty_is_recorded_not_blocked(tmp_path: Path) -> None:
    """§4.1 permits a dirty tree and records it; refusing would push operators to
    commit junk mid-incident."""
    block = build_manifest_block(
        run_id="d1", run_started_at="t", session_id="s", invocation="api",
        git=GitMetadata(available=True, sha="b" * 40, dirty=True),
        config_snapshot={}, credentials=resolve(Credentials()),
        model="gpt-5-nano", sample=[],
    )
    assert block["code"]["git_dirty"] is True
