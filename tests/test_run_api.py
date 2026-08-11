"""``launch()`` and minted run identity — Run API spec v0.1 §1–§2 (PR B).

Grouped by the guarantee under test:

* **§2 identity** — the format, the round-trip, and the two refusals that keep it
  honest (a naive clock, a non-minted id);
* **§2 collision armor** — a minted id never names an existing run directory, so
  fresh-vs-resume is never ambiguous;
* **§1 launch** — minting, pre-spend validation, resume detection, the receipt;
* **§3.5 resume under a changed key** — the double-spend this refuses.

The stage machinery itself is not re-tested here: ``run_presweep`` is covered by
``test_presweep`` and ``test_e2e_presweep_smoke``, so these tests stub it and
assert only what ``launch()`` decides around it.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from g3o.common import run_state
from g3o.common.credentials import Credentials, fingerprint, resolve
from g3o.run import api
from g3o.run import run_id as run_id_mod
from g3o.run.api import (
    LaunchValidationError,
    RunReceipt,
    capture_git_metadata,
    launch,
    resolve_session_id,
)
from g3o.run.presweep import PresweepConfig
from g3o.run.run_id import (
    RUN_ID_FORMAT,
    is_minted_run_id,
    mint_run_id,
    run_started_at,
)

MINTED_RE = re.compile(r"^r\d{8}T\d{6}Z-[0-9a-f]{4}$")
MOMENT = datetime(2026, 8, 9, 14, 30, 12, tzinfo=timezone.utc)


def _write_master(path: Path, n: int = 3) -> Path:
    header = (
        "master_row_id,institution_name,country,branch,government_level,"
        "institution_type,website,official_site_url,official_site_confidence\n"
    )
    rows = "".join(
        f"{i},Ministry {i},Atlantis,executive,national,ministry,,,\n" for i in range(n)
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


# ---------------------------------------------------------------------------
# §2 — the date key
# ---------------------------------------------------------------------------


def test_minted_id_has_the_specified_shape() -> None:
    minted = mint_run_id(MOMENT)
    assert MINTED_RE.match(minted), f"{minted!r} is not {RUN_ID_FORMAT}"
    assert minted.startswith("r20260809T143012Z-")


def test_minting_round_trips_through_run_started_at() -> None:
    assert run_started_at(mint_run_id(MOMENT)) == MOMENT


def test_minting_truncates_to_whole_seconds() -> None:
    """The format has no sub-second field, so the round-trip must not claim one."""
    precise = MOMENT.replace(microsecond=987654)
    assert run_started_at(mint_run_id(precise)) == MOMENT


def test_minting_converts_an_aware_non_utc_moment() -> None:
    """UTC always (§2) — an aware moment in another zone is converted, not stamped."""
    berlin = MOMENT.astimezone(timezone(timedelta(hours=2)))
    assert berlin.hour == 16  # same instant, different wall clock
    assert mint_run_id(berlin).startswith("r20260809T143012Z-")


def test_minting_refuses_a_naive_datetime() -> None:
    """A local-time moment stamped ``Z`` would misfile the run into a neighbouring
    wave window silently — the one error mode a fallback here could not undo."""
    with pytest.raises(ValueError, match="aware datetime"):
        mint_run_id(datetime(2026, 8, 9, 14, 30, 12))


def test_suffix_is_collision_armor_not_identity() -> None:
    """Same second, many mints: the ids differ, and only in the suffix."""
    ids = {mint_run_id(MOMENT) for _ in range(200)}
    assert len(ids) > 1
    assert {i.split("-")[0] for i in ids} == {"r20260809T143012Z"}
    assert all(re.fullmatch(r"[0-9a-f]{4}", i.split("-")[1]) for i in ids)


@pytest.mark.parametrize(
    "legacy",
    [
        "20260509-presweep",  # the real legacy id shape
        "smoke-1",
        "baseline-smoke-1",
        "",
        "r20260809T143012Z",  # no suffix
        "r20260809T143012Z-ABCD",  # uppercase hex
        "r20260809T143012Z-zzzz",  # not hex
        "xr20260809T143012Z-a3f1",  # not anchored at the start
        "r20260809T143012Z-a3f1x",  # not anchored at the end
    ],
)
def test_run_started_at_raises_for_non_minted_ids(legacy: str) -> None:
    """A fallback here would classify a legacy run into whatever window is open."""
    with pytest.raises(ValueError):
        run_started_at(legacy)
    assert is_minted_run_id(legacy) is False


def test_run_started_at_raises_on_a_well_shaped_impossible_moment() -> None:
    with pytest.raises(ValueError, match="not a real"):
        run_started_at("r20261301T143012Z-a3f1")


def test_is_minted_run_id_accepts_what_mint_produces() -> None:
    assert is_minted_run_id(mint_run_id(MOMENT)) is True


# ---------------------------------------------------------------------------
# §2 — collision armor: a minted id never names an existing run directory
# ---------------------------------------------------------------------------


def _fixed_suffixes(monkeypatch, *values: str) -> list[str]:
    """Pin ``secrets.token_hex`` to a scripted sequence, then repeat the last."""
    remaining = list(values)
    handed: list[str] = []

    def _token_hex(_n: int) -> str:
        value = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        handed.append(value)
        return value

    monkeypatch.setattr(run_id_mod.secrets, "token_hex", _token_hex)
    return handed


def test_a_colliding_mint_is_re_minted(tmp_path: Path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    # The directory the first mint will land on, written directly rather than by
    # minting it — so the scripted suffix sequence below is consumed only by the
    # code under test and the collision is genuinely the first attempt's.
    taken = "r20260809T143012Z-aaaa"
    (runs_dir / taken).mkdir(parents=True)
    handed = _fixed_suffixes(monkeypatch, "aaaa", "bbbb")
    monkeypatch.setattr(run_id_mod, "datetime", _FrozenDatetime)

    minted = api._mint_unused_run_id(runs_dir)

    assert minted != taken
    assert minted == "r20260809T143012Z-bbbb"
    assert handed == ["aaaa", "bbbb"], "the colliding attempt was not re-minted"


def test_minting_gives_up_rather_than_looping(tmp_path: Path, monkeypatch) -> None:
    """Three collisions in a row is a stopped clock or a wrong runs_dir, not luck."""
    runs_dir = tmp_path / "runs"
    _fixed_suffixes(monkeypatch, "cccc")
    monkeypatch.setattr(run_id_mod, "datetime", _FrozenDatetime)
    (runs_dir / mint_run_id(MOMENT)).mkdir(parents=True)

    with pytest.raises(LaunchValidationError, match="could not mint an unused run id"):
        api._mint_unused_run_id(runs_dir)


class _FrozenDatetime(datetime):
    """Pins ``datetime.now`` inside :mod:`g3o.run.run_id` for the tests above."""

    @classmethod
    def now(cls, tz=None):  # noqa: D102 - stdlib signature
        return MOMENT if tz else MOMENT.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# §1 — launch()
# ---------------------------------------------------------------------------


def _stub_run_presweep(monkeypatch, summary: dict | None = None) -> list[tuple]:
    """Replace the stage dispatcher; record how ``launch`` called it."""
    from g3o.run import presweep as presweep_pkg

    calls: list[tuple] = []

    def _fake(config, *, credentials=None):
        calls.append((config, credentials))
        return dict(summary) if summary is not None else {
            "run_id": config.run_id,
            "run_dir": str(config.runs_dir / config.run_id),
            "n_institutions": 3,
            "dry_run": config.dry_run,
        }

    monkeypatch.setattr(presweep_pkg, "run_presweep", _fake)
    return calls


def test_launch_mints_an_id_when_the_config_has_none(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _stub_run_presweep(monkeypatch)
    receipt = launch(_config(tmp_path))

    assert isinstance(receipt, RunReceipt)
    assert MINTED_RE.match(receipt.run_id)
    assert receipt.runs_dir == tmp_path / "runs" / receipt.run_id
    assert receipt.manifest_path == receipt.runs_dir / "manifest.json"
    assert receipt.events_path == receipt.runs_dir / "events.jsonl"
    # The id reaches the operator immediately, not when the run returns (§2).
    assert f"run_id={receipt.run_id}" in capsys.readouterr().err


def test_launch_mints_for_a_none_run_id_too(tmp_path: Path, monkeypatch) -> None:
    """§1.2 says "empty/None"; ``None`` reaches here from any programmatic caller."""
    _stub_run_presweep(monkeypatch)
    receipt = launch(_config(tmp_path, run_id=None))
    assert MINTED_RE.match(receipt.run_id)


def test_launch_honours_an_explicit_id_verbatim(tmp_path: Path, monkeypatch) -> None:
    """The replication and resume path: no normalisation, no minting, no suffix."""
    _stub_run_presweep(monkeypatch)
    receipt = launch(_config(tmp_path, run_id="20260509-presweep"))
    assert receipt.run_id == "20260509-presweep"


def test_launch_receipt_start_time_comes_from_a_minted_id(
    tmp_path: Path, monkeypatch
) -> None:
    _stub_run_presweep(monkeypatch)
    monkeypatch.setattr(run_id_mod, "datetime", _FrozenDatetime)
    receipt = launch(_config(tmp_path))
    assert receipt.run_started_at == "2026-08-09T14:30:12Z"
    assert run_started_at(receipt.run_id).isoformat() == "2026-08-09T14:30:12+00:00"


def test_launch_start_time_for_a_legacy_id_is_this_launch(
    tmp_path: Path, monkeypatch
) -> None:
    """A legacy id carries no timestamp, so the receipt times the launch itself."""
    _stub_run_presweep(monkeypatch)
    receipt = launch(_config(tmp_path, run_id="20260509-presweep"))
    assert receipt.run_started_at.endswith("Z")
    parsed = datetime.strptime(receipt.run_started_at, "%Y-%m-%dT%H:%M:%SZ")
    assert abs((parsed.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()) < 120


def test_launch_threads_credentials_into_the_run(tmp_path: Path, monkeypatch) -> None:
    calls = _stub_run_presweep(monkeypatch)
    creds = Credentials(openai_api_key="sk-launch-test", label="key-B")
    launch(_config(tmp_path), credentials=creds)
    assert calls[0][1] is creds


def test_launch_is_reachable_through_the_patch_target_the_cli_tests_use(
    tmp_path: Path, monkeypatch
) -> None:
    """``launch`` must resolve ``run_presweep`` at call time, not at import.

    The cost-gate tests patch ``g3o.run.presweep.run_presweep``. A module-level
    ``from ... import run_presweep`` in api.py would bind the real function and
    those tests would silently run the pipeline instead of their double.
    """
    calls = _stub_run_presweep(monkeypatch)
    launch(_config(tmp_path))
    assert len(calls) == 1


def test_launch_defaults_to_a_dry_run(tmp_path: Path, monkeypatch) -> None:
    """§1.6 — live spend stays opt-in through the new entry point too."""
    calls = _stub_run_presweep(monkeypatch)
    launch(_config(tmp_path))
    assert calls[0][0].dry_run is True


def test_launch_re_validates_the_config_it_rebuilds(tmp_path: Path, monkeypatch) -> None:
    """Minting rebuilds the config, so ``__post_init__`` must run again (§1.2).

    Mutated after construction — which the dataclass permits — so the invalid
    state can only be caught by the rebuild. Without it, a run could reach Serper
    with a language its roster cannot query (the A7 guarantee).
    """
    _stub_run_presweep(monkeypatch)
    config = _config(tmp_path)
    config.discovery_languages = ("xx",)
    with pytest.raises(ValueError):
        launch(config)


# --- resume detection (§1.3) ------------------------------------------------


def test_fresh_run_is_not_a_resume(tmp_path: Path, monkeypatch) -> None:
    _stub_run_presweep(monkeypatch)
    assert launch(_config(tmp_path)).resumed is False


def test_existing_state_makes_it_a_resume(tmp_path: Path, monkeypatch) -> None:
    _stub_run_presweep(monkeypatch)
    run_state.state_dir(tmp_path / "runs" / "rerun-1").mkdir(parents=True)
    assert launch(_config(tmp_path, run_id="rerun-1")).resumed is True


def test_a_run_directory_without_state_is_not_a_resume(
    tmp_path: Path, monkeypatch
) -> None:
    """Planning artifacts alone are a re-plan, not a rejoin — matching the stage
    runners' own inference (Q7=c), which keys on ``_state/`` and nothing else."""
    _stub_run_presweep(monkeypatch)
    (tmp_path / "runs" / "replan-1").mkdir(parents=True)
    assert launch(_config(tmp_path, run_id="replan-1")).resumed is False


# --- outcome (§1) -----------------------------------------------------------


def test_dry_run_outcome_is_stopped_not_completed(tmp_path: Path, monkeypatch) -> None:
    """A monitor must never read a planning-only run as a finished sweep."""
    _stub_run_presweep(monkeypatch)
    assert launch(_config(tmp_path)).outcome == "stopped"


def test_live_run_short_of_the_roster_is_stopped(tmp_path: Path, monkeypatch) -> None:
    _stub_run_presweep(monkeypatch)
    receipt = launch(
        _config(tmp_path, dry_run=False, stop_after="extract"),
        credentials=Credentials(openai_api_key="sk-x", serper_api_key="s"),
    )
    assert (receipt.outcome, receipt.stop_after) == ("stopped", "extract")


def test_live_run_through_the_whole_roster_is_completed(
    tmp_path: Path, monkeypatch
) -> None:
    _stub_run_presweep(monkeypatch)
    receipt = launch(
        _config(tmp_path, dry_run=False, stop_after="validate"),
        credentials=Credentials(openai_api_key="sk-x", serper_api_key="s"),
    )
    assert receipt.outcome == "completed"


def test_launch_never_returns_a_failed_receipt(tmp_path: Path, monkeypatch) -> None:
    """§1.5 — it raises instead, so an exception cannot be mistaken for a result."""
    from g3o.run import presweep as presweep_pkg

    def _boom(config, *, credentials=None):
        raise RuntimeError("stage exploded")

    monkeypatch.setattr(presweep_pkg, "run_presweep", _boom)
    with pytest.raises(RuntimeError, match="stage exploded"):
        launch(_config(tmp_path))


# --- pre-spend validation (§1.4) -------------------------------------------


def test_unwritable_runs_dir_fails_before_anything_runs(
    tmp_path: Path, monkeypatch
) -> None:
    calls = _stub_run_presweep(monkeypatch)
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("", encoding="utf-8")
    with pytest.raises(LaunchValidationError, match="not writable"):
        launch(_config(tmp_path, runs_dir=blocker / "runs"))
    assert calls == [], "validation must precede dispatch"


def test_live_run_without_keys_fails_as_a_launch_validation_error(
    tmp_path: Path, monkeypatch
) -> None:
    calls = _stub_run_presweep(monkeypatch)
    with pytest.raises(LaunchValidationError, match="SERPER_API_KEY"):
        launch(_config(tmp_path, dry_run=False, stop_after="discovery_general"))
    assert calls == []


def test_launch_validation_error_is_still_a_runtime_error() -> None:
    """Callers and tests that predate the spec catch ``RuntimeError`` (§1.5)."""
    assert issubclass(LaunchValidationError, RuntimeError)


def test_dry_run_tolerates_uncapturable_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    calls = _stub_run_presweep(monkeypatch)
    monkeypatch.setattr(
        api, "capture_git_metadata",
        lambda *a, **k: api.GitMetadata(available=False, error="not a git checkout"),
    )
    launch(_config(tmp_path))
    assert len(calls) == 1, "a dry run spends nothing; it must not be blocked"


def test_live_run_refuses_uncapturable_provenance(tmp_path: Path, monkeypatch) -> None:
    """Artifacts that cannot be tied to a commit are unreplicable (§1.4, §4.4)."""
    calls = _stub_run_presweep(monkeypatch)
    monkeypatch.setattr(
        api, "capture_git_metadata",
        lambda *a, **k: api.GitMetadata(available=False, error="git exploded"),
    )
    with pytest.raises(LaunchValidationError, match="provenance is not capturable"):
        launch(
            _config(tmp_path, dry_run=False, stop_after="discovery_general"),
            credentials=Credentials(serper_api_key="s"),
        )
    assert calls == []


def test_capture_git_metadata_reports_a_non_checkout_without_raising(
    tmp_path: Path,
) -> None:
    meta = capture_git_metadata(tmp_path)
    assert meta.available is False
    assert meta.error == "not a git checkout"
    assert meta.install_path == str(tmp_path)


def test_capture_git_metadata_reads_this_repo() -> None:
    meta = capture_git_metadata()
    assert meta.available is True
    assert re.fullmatch(r"[0-9a-f]{40}", meta.sha or "")
    assert isinstance(meta.dirty, bool)  # recorded, never blocking (§4.1)


# --- session id (§4.2) ------------------------------------------------------


def test_session_id_precedence(monkeypatch) -> None:
    monkeypatch.setenv("G3O_SESSION_ID", "from-env")
    assert resolve_session_id("explicit") == "explicit"
    assert resolve_session_id(None) == "from-env"
    monkeypatch.delenv("G3O_SESSION_ID")
    assert resolve_session_id(None) == "unattended"


def test_unattended_is_an_admission_not_an_id(monkeypatch) -> None:
    monkeypatch.delenv("G3O_SESSION_ID", raising=False)
    assert resolve_session_id("") == "unattended"


# ---------------------------------------------------------------------------
# §1.1 — the CLI is a thin wrapper over launch()
# ---------------------------------------------------------------------------


def test_cli_dry_run_prints_the_receipt_and_the_summary(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """One JSON document on stdout, ``run_id`` first, every old key still present."""
    from g3o import cli

    master = _write_master(tmp_path / "master.csv")
    exit_code = cli.main(
        [
            "presweep",
            "--master-csv", str(master),
            "--runs-dir", str(tmp_path / "runs"),
            "--sample-size", "3",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)  # exactly one document
    assert list(payload)[0] == "run_id"
    assert MINTED_RE.match(payload["run_id"])
    # Receipt fields...
    assert payload["outcome"] == "stopped" and payload["resumed"] is False
    assert payload["stop_after"] == "extract"
    # ...and the pre-existing summary keys, unchanged in name.
    assert payload["dry_run"] is True
    assert payload["n_institutions"] == 3
    assert "g3o presweep --execute" in payload["next_step"]
    # The minted id reached the operator immediately, on stderr (§2).
    assert f"run_id={payload['run_id']}" in captured.err
    assert (tmp_path / "runs" / payload["run_id"] / "manifest.json").exists()


def test_cli_honours_an_explicit_run_id(tmp_path: Path, capsys) -> None:
    from g3o import cli

    master = _write_master(tmp_path / "master.csv")
    cli.main(
        [
            "presweep",
            "--run-id", "20260509-presweep",
            "--master-csv", str(master),
            "--runs-dir", str(tmp_path / "runs"),
            "--sample-size", "3",
        ]
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)["run_id"] == "20260509-presweep"
    assert "run_id=" not in captured.err, "nothing was minted, so nothing to announce"


def test_cli_builds_credentials_and_labels_them(tmp_path: Path, monkeypatch) -> None:
    """§1.1 — the adapter builds ``Credentials`` from argv/env, not just a config.

    The label is the operator's note about *which* key paid for a run, and it is a
    recorded telemetry field (§4.1). Without this wiring it would be unreachable
    from the command line — settable only by a programmatic caller — so a
    CLI-launched run could never say which grant it spent.
    """
    from g3o import cli

    seen: list[Credentials | None] = []
    real_launch = api.launch

    def _spy(config, *, credentials=None, session_id=None):
        seen.append(credentials)
        return real_launch(config, credentials=credentials, session_id=session_id)

    monkeypatch.setattr(api, "launch", _spy)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    master = _write_master(tmp_path / "master.csv")
    cli.main(
        [
            "presweep",
            "--master-csv", str(master),
            "--runs-dir", str(tmp_path / "runs"),
            "--sample-size", "3",
            "--key-label", "key-B-grant",
        ]
    )

    assert len(seen) == 1 and seen[0] is not None
    assert seen[0].label == "key-B-grant"
    # Keys are not accepted on argv (shell history, `ps`), so they arrive by env
    # and the label rides alongside them into telemetry.
    assert seen[0].openai_api_key is None
    block = resolve(seen[0]).telemetry()
    assert block["openai"] == {
        "source": "env",
        "fingerprint": fingerprint("sk-from-env"),
        "label": "key-B-grant",
    }


def test_cli_session_id_reaches_launch(tmp_path: Path, monkeypatch) -> None:
    from g3o import cli

    seen: list[str | None] = []
    real_launch = api.launch

    def _spy(config, *, credentials=None, session_id=None):
        seen.append(session_id)
        return real_launch(config, credentials=credentials, session_id=session_id)

    monkeypatch.setattr(api, "launch", _spy)
    master = _write_master(tmp_path / "master.csv")
    cli.main(
        [
            "presweep",
            "--master-csv", str(master),
            "--runs-dir", str(tmp_path / "runs"),
            "--sample-size", "3",
            "--session-id", "sess-xyz",
        ]
    )
    assert seen == ["sess-xyz"]


# ---------------------------------------------------------------------------
# §3.5 — resume under a changed key
# ---------------------------------------------------------------------------


def test_resume_with_a_changed_key_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="Resume with the original key"):
        run_state.assert_resume_key_matches(
            {"key_fingerprint": "aaaaaaaa"},
            "bbbbbbbb",
            run_dir=Path("runs/r1"),
            stage="extract",
        )


def test_resume_with_the_same_key_proceeds() -> None:
    run_state.assert_resume_key_matches(
        {"key_fingerprint": "aaaaaaaa"},
        "aaaaaaaa",
        run_dir=Path("runs/r1"),
        stage="extract",
    )


@pytest.mark.parametrize(
    "state, current",
    [
        ({}, "aaaaaaaa"),  # state predates the field
        ({"key_fingerprint": None}, "aaaaaaaa"),
        ({"key_fingerprint": "aaaaaaaa"}, None),  # caller threaded no credentials
    ],
)
def test_unknown_fingerprints_are_not_a_mismatch(state: dict, current) -> None:
    """Older state files and credential-less callers must resume exactly as before."""
    run_state.assert_resume_key_matches(
        state, current, run_dir=Path("runs/r1"), stage="extract"
    )


def test_state_file_records_the_submitting_key(tmp_path: Path) -> None:
    run_state.write_active_chunked(
        tmp_path, "extract",
        run_id="r1", model="gpt-5-nano",
        chunk_custom_ids=[["J1", "J2"]],
        key_fingerprint=fingerprint("sk-original"),
    )
    payload = json.loads(
        run_state.state_path(tmp_path, "extract").read_text(encoding="utf-8")
    )
    assert payload["key_fingerprint"] == fingerprint("sk-original")
    assert "sk-original" not in json.dumps(payload)  # §3.3


def test_state_file_omits_the_field_when_no_key_is_known(tmp_path: Path) -> None:
    run_state.write_active_chunked(
        tmp_path, "extract",
        run_id="r1", model="gpt-5-nano",
        chunk_custom_ids=[["J1"]],
    )
    payload = json.loads(
        run_state.state_path(tmp_path, "extract").read_text(encoding="utf-8")
    )
    assert "key_fingerprint" not in payload


def test_a_resumed_stage_checks_the_key_before_submitting_anything(
    tmp_path: Path, monkeypatch
) -> None:
    """The whole point: the refusal lands before the first spend-bearing call.

    Without it, reconciliation under the new key finds none of key A's batches,
    resubmits every unfetched chunk, and both sets bill.
    """
    submitted: list = []
    monkeypatch.setattr(
        run_state.batch_client, "submit_batch",
        lambda *a, **k: submitted.append(a) or pytest.fail("submitted under a new key"),
    )
    monkeypatch.setattr(
        run_state.batch_client, "find_batches_by_metadata", lambda *a, **k: []
    )
    run_state.write_active_chunked(
        tmp_path, "extract",
        run_id="r1", model="gpt-5-nano",
        chunk_custom_ids=[["J1"]],
        key_fingerprint=fingerprint("sk-original"),
    )

    with pytest.raises(RuntimeError, match="Resume with the original key"):
        run_state.run_chunked_stage(
            tmp_path, "extract",
            [run_state.BatchJob(custom_id="J1", messages=[{"role": "user", "content": "x"}])],
            run_id="r1", model="gpt-5-nano",
            poll_interval=0, max_wait=1,
            process_chunk_results=lambda results: None,
            credentials=resolve(Credentials(openai_api_key="sk-rotated")),
        )
    assert submitted == []
