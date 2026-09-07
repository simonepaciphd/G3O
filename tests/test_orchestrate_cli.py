"""The orchestrator CLI — mostly about exit codes, because scripts read them.

0 = green, 1 = it ran and is not green, 2 = it refused or could not run. The
distinction between 1 and 2 is what a shell script (and the joint gate) branches
on: 1 means "look at the result", 2 means "the thing you asked for did not
happen".
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from g3o.run.orchestrate import submit as sub
from g3o.run.orchestrate.cli import EXIT_NOT_GREEN, EXIT_OK, EXIT_REFUSED, main
from tests._orchestrate import event, make_run, write_final_csvs
from tests.test_orchestrate_submit import _fake_launch, _write_master


def _completed(runs_dir: Path, run_id: str = "r20260813T100000Z-aaaa") -> Path:
    return make_run(
        runs_dir,
        run_id,
        config={"dry_run": False},
        events=[event(1, "run_launched"), event(2, "run_completed", outcome="completed")],
    )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_of_a_completed_run_exits_zero(tmp_path: Path, capsys) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _completed(runs_dir)

    code = main(["status", "--run-id", run_dir.name, "--runs-dir", str(runs_dir)])

    assert code == EXIT_OK
    assert run_dir.name in capsys.readouterr().out


def test_status_of_a_failed_run_exits_one(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(
        runs_dir,
        events=[event(1, "run_launched"), event(2, "run_failed", error_class="RuntimeError")],
    )
    assert main(["status", "--run-id", run_dir.name, "--runs-dir", str(runs_dir)]) == EXIT_NOT_GREEN


def test_status_of_a_run_that_is_not_there_exits_two(tmp_path: Path) -> None:
    assert main(["status", "--run-id", "nope", "--runs-dir", str(tmp_path)]) == EXIT_REFUSED


def test_status_json_is_a_single_document(tmp_path: Path, capsys) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = _completed(runs_dir)

    main(["status", "--run-id", run_dir.name, "--runs-dir", str(runs_dir), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "completed"
    assert payload["publishable"] is True


def test_latest_picks_the_newest_run(tmp_path: Path, capsys) -> None:
    """Minted ids sort chronologically, so newest-by-name is exact (§2)."""
    runs_dir = tmp_path / "runs"
    _completed(runs_dir, "r20260810T090000Z-1111")
    _completed(runs_dir, "r20260813T101500Z-2222")

    main(["status", "--latest", "--runs-dir", str(runs_dir), "--json"])

    assert json.loads(capsys.readouterr().out)["run_id"] == "r20260813T101500Z-2222"


def test_naming_no_run_at_all_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="--run-id"):
        main(["status", "--runs-dir", str(tmp_path)])


def test_latest_on_an_empty_runs_dir_says_so(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no run directories"):
        main(["status", "--latest", "--runs-dir", str(tmp_path)])


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


def _config_file(tmp_path: Path) -> Path:
    master = _write_master(tmp_path / "master.csv")
    path = tmp_path / "run.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "",
                "runs_dir": str(tmp_path / "runs"),
                "master_csv": str(master),
                "sample_size": 2,
                "seed": 1,
                "dry_run": True,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_submit_prints_the_run_id_first(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sub, "launch", _fake_launch())

    code = main(["submit", "--config", str(_config_file(tmp_path))])

    assert code == EXIT_OK
    assert capsys.readouterr().out.startswith("run_id=")


def test_submit_overrides_apply_on_top_of_the_file(tmp_path: Path, monkeypatch, capsys) -> None:
    seen: dict = {}

    def _launch(config, **_kwargs):
        seen["sample_size"] = config.sample_size
        seen["dry_run"] = config.dry_run
        return _fake_launch()(config)

    monkeypatch.setattr(sub, "launch", _launch)

    main(["submit", "--config", str(_config_file(tmp_path)), "--sample-size", "20", "--execute"])

    assert seen == {"sample_size": 20, "dry_run": False}


def test_a_typo_in_the_config_file_refuses(tmp_path: Path, capsys) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"sampel_size": 20}), encoding="utf-8")

    code = main(["submit", "--config", str(path)])

    assert code == EXIT_REFUSED
    assert "unknown config key" in capsys.readouterr().err


def test_an_unknown_stage_is_refused_in_the_shell(tmp_path: Path) -> None:
    """Not deep inside the orchestrator, hours later, on a detached run.

    ``PresweepConfig.stop_after`` is a ``Literal`` that ``__post_init__`` does not
    check, so an unconstrained flag would carry ``"not_a_stage"`` all the way to
    ``STAGES.index()`` and fail there with ``tuple.index(x): x not in tuple``.
    """
    with pytest.raises(SystemExit):
        main(["submit", "--config", str(_config_file(tmp_path)), "--stop-after", "not_a_stage"])


def test_a_failing_run_exits_not_green(tmp_path: Path, monkeypatch, capsys) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("Stage scrape died")

    monkeypatch.setattr(sub, "launch", _boom)

    code = main(["submit", "--config", str(_config_file(tmp_path))])

    assert code == EXIT_NOT_GREEN
    assert "Stage scrape died" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# submit --json — stdout is the JSON document and nothing else
# ---------------------------------------------------------------------------

_BANNER = "====== G3O Run Summary ======"


def _launch_that_talks_to_a_human(receipt_outcome: str = "stopped"):
    """A launch that prints, the way the real one does.

    ``g3o.run.presweep.orchestrator``'s ``finally`` block calls
    ``print(render_run_summary_text(...))`` on every exit path, so a foreground
    submit emits a human summary on stdout before the CLI writes any JSON. The
    fake reproduces that and nothing else.
    """
    inner = _fake_launch(receipt_outcome)

    def _launch(config, **kwargs):
        receipt = inner(config, **kwargs)
        print(_BANNER)
        print("  institutions: 2")
        return receipt

    return _launch


def test_submit_json_stdout_is_parseable_even_though_the_run_printed(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The eba5 regression: ``json.load`` on this stdout must not die.

    On ``r20260831T123415Z-eba5`` it did — ``Expecting value: line 1 column 1
    (char 0)`` — because the run summary landed on stdout ahead of the JSON.
    ``set -euo pipefail`` then aborted the launch script before its publish step,
    so a 15.9 h run that finished cleanly published nothing.
    """
    monkeypatch.setattr(sub, "launch", _launch_that_talks_to_a_human())

    code = main(["submit", "--config", str(_config_file(tmp_path)), "--json"])
    captured = capsys.readouterr()

    assert code == EXIT_OK
    payload = json.loads(captured.out)  # the assertion; a raise here is the bug
    assert payload["run_id"].startswith("r")
    assert _BANNER not in captured.out


def test_submit_json_moves_the_human_summary_to_stderr_rather_than_dropping_it(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Reserved, not suppressed — an operator watching a terminal still sees it."""
    monkeypatch.setattr(sub, "launch", _launch_that_talks_to_a_human())

    main(["submit", "--config", str(_config_file(tmp_path)), "--json"])

    assert _BANNER in capsys.readouterr().err


def test_submit_without_json_still_prints_the_summary_on_stdout(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The guard binds only under ``--json``.

    Anyone redirecting ``submit > summary.txt`` today captures the run summary,
    and this fix is not allowed to quietly empty that file.
    """
    monkeypatch.setattr(sub, "launch", _launch_that_talks_to_a_human())

    main(["submit", "--config", str(_config_file(tmp_path))])
    captured = capsys.readouterr()

    # Both halves on stdout, in the order they were written: the run's own
    # summary first, then this module's receipt.
    assert _BANNER in captured.out
    assert captured.out.index(_BANNER) < captured.out.index("run_id=")
    assert captured.err == ""


# ---------------------------------------------------------------------------
# archive / ingest / publish-verify
# ---------------------------------------------------------------------------


def test_archive_dry_run_reports_the_plan(tmp_path: Path, capsys) -> None:
    from g3o.common import run_state
    from g3o.run.presweep.config import STAGES

    runs_dir = tmp_path / "runs"
    run_dir = _completed(runs_dir)
    write_final_csvs(run_dir)
    for stage in STAGES:
        run_state.mark_done(run_dir, stage, no_batch=True)
    (run_dir / "run_summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "_health_report.json").write_text("{}", encoding="utf-8")

    code = main(["archive", "--run-id", run_dir.name, "--runs-dir", str(runs_dir)])

    assert code == EXIT_OK
    assert "dry run" in capsys.readouterr().out


def test_archive_refuses_an_unfinished_run(tmp_path: Path, capsys) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = make_run(runs_dir, events=[event(1, "run_launched")])

    code = main(["archive", "--run-id", run_dir.name, "--runs-dir", str(runs_dir), "--apply"])

    assert code == EXIT_REFUSED
    assert "refusing to archive" in capsys.readouterr().err


def test_ingest_requires_a_frame_id(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["ingest", "--run-id", "r1", "--runs-dir", str(tmp_path)])


def test_ingest_without_a_checkout_refuses(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("G3O_API_REPO", raising=False)
    runs_dir = tmp_path / "runs"
    run_dir = _completed(runs_dir)
    write_final_csvs(run_dir)

    code = main(
        ["ingest", "--run-id", run_dir.name, "--runs-dir", str(runs_dir), "--frame-id", "mb-TEST"]
    )

    assert code == EXIT_REFUSED
    assert "G3O_API_REPO" in capsys.readouterr().err


def test_publish_verify_without_an_api_base_refuses(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv("G3O_API_BASE", raising=False)
    runs_dir = tmp_path / "runs"
    run_dir = _completed(runs_dir)

    code = main(["publish-verify", "--run-id", run_dir.name, "--runs-dir", str(runs_dir)])

    assert code == EXIT_REFUSED
    assert "G3O_API_BASE" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# persist
# ---------------------------------------------------------------------------


def test_persist_with_no_version_flag_writes_v1(tmp_path: Path, monkeypatch) -> None:
    """The verb's own default path. It used to write `g3o_activities_vNone.csv`.

    `--version` is declared `default=None` and was forwarded unconditionally, so
    `persist_run`'s signature default never applied and Stage 7 formatted None
    into all three filenames. Nothing downstream caught it: the activities and
    sources globs are `_v*`, and the version-skew refusal is guarded on a parsed
    version being `not None`, which `vNone` is not. Exercised through `main` and
    not through `persist_run`, because the defect lived entirely in the wiring
    between them.
    """
    from g3o.run.orchestrate import persist_leg as pl

    runs_dir = tmp_path / "runs"
    run_dir = _completed(runs_dir)

    def fake_write(rd: Path, run_id: str, **kw) -> dict:
        write_final_csvs(rd, version=kw["version"])
        return {"n_load_failures": 0, "outputs": {}}

    monkeypatch.setattr(pl, "_write", fake_write)

    code = main(["persist", "--run-id", run_dir.name, "--runs-dir", str(runs_dir)])

    assert code == EXIT_OK
    written = sorted(p.name for p in (run_dir / "final").glob("g3o_*_v*.csv"))
    assert written == [
        "g3o_activities_v1.csv",
        "g3o_activity_sources_v1.csv",
        "g3o_institution_summary_v1.csv",
    ]


def test_every_verb_is_reachable() -> None:
    from g3o.run.orchestrate.cli import build_parser

    parser = build_parser()
    for verb in ("submit", "status", "ingest", "persist", "archive", "publish-verify"):
        assert parser.parse_args([verb, "--help"] if False else _minimal_args(verb))


def _minimal_args(verb: str) -> list[str]:
    if verb == "submit":
        return ["submit", "--config", "x.json"]
    if verb == "ingest":
        return ["ingest", "--run-id", "r", "--frame-id", "mb-TEST"]
    return [verb, "--run-id", "r"]
