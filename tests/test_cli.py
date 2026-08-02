"""CLI argument-wiring tests (review F19, Opus-side mechanical backfill).

Covers the parser-level guards (``_existing_file`` / ``_existing_dir``) and the
``build_parser`` wiring: subcommand → handler routing, defaults that encode
launch behavior (dry-run by default, ``--stop-after extract`` default, model
default), ``choices`` enforcement, and required-arg failures. These never call
a subcommand body, so no network/Batch-API calls occur.
"""

from __future__ import annotations

import argparse
import io

import pytest

from g3o import cli
from g3o.common.batch_client import DEFAULT_MODEL

# ---------------------------------------------------------------------------
# type= guards
# ---------------------------------------------------------------------------


def test_existing_file_accepts_existing(tmp_path):
    f = tmp_path / "master.csv"
    f.write_text("x", encoding="utf-8")
    assert cli._existing_file(str(f)) == f


def test_existing_file_rejects_missing(tmp_path):
    with pytest.raises(argparse.ArgumentTypeError):
        cli._existing_file(str(tmp_path / "nope.csv"))


def test_existing_file_rejects_directory(tmp_path):
    # A directory is not a file.
    with pytest.raises(argparse.ArgumentTypeError):
        cli._existing_file(str(tmp_path))


def test_existing_dir_accepts_existing(tmp_path):
    assert cli._existing_dir(str(tmp_path)) == tmp_path


def test_existing_dir_rejects_missing(tmp_path):
    with pytest.raises(argparse.ArgumentTypeError):
        cli._existing_dir(str(tmp_path / "nope"))


def test_existing_dir_rejects_file(tmp_path):
    f = tmp_path / "f.json"
    f.write_text("{}", encoding="utf-8")
    with pytest.raises(argparse.ArgumentTypeError):
        cli._existing_dir(str(f))


# ---------------------------------------------------------------------------
# _run_date_from_manifest (review F18b — persist provenance date)
# ---------------------------------------------------------------------------


def _write_manifest(run_dir, content):
    import json

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(content), encoding="utf-8")


def test_run_date_from_manifest_reads_date(tmp_path):
    _write_manifest(tmp_path, {"run_date": "2026-05-09", "run_id": "R1"})
    assert cli._run_date_from_manifest(tmp_path) == "2026-05-09"


def test_run_date_from_manifest_missing_manifest_returns_none(tmp_path):
    assert cli._run_date_from_manifest(tmp_path) is None


def test_run_date_from_manifest_no_date_key_returns_none(tmp_path):
    _write_manifest(tmp_path, {"run_id": "R1"})
    assert cli._run_date_from_manifest(tmp_path) is None


def test_run_date_from_manifest_malformed_returns_none(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    assert cli._run_date_from_manifest(tmp_path) is None


# ---------------------------------------------------------------------------
# Subcommand routing
# ---------------------------------------------------------------------------


def test_no_subcommand_errors():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_discover_routing():
    args = cli.build_parser().parse_args(["discover", "--institution", "City of X"])
    assert args.func is cli._cmd_discover
    assert args.languages == "en"
    assert args.limit == 5


def test_scrape_routing_and_flags():
    args = cli.build_parser().parse_args(
        ["scrape", "--url", "https://x.gov", "--force-render", "--text-only"]
    )
    assert args.func is cli._cmd_scrape
    assert args.force_render is True
    assert args.text_only is True
    assert args.force_refresh is False


def test_classify_official_site_routing_and_required_args(tmp_path):
    row = tmp_path / "row.json"
    row.write_text("{}", encoding="utf-8")
    urls = tmp_path / "urls.json"
    urls.write_text("[]", encoding="utf-8")
    args = cli.build_parser().parse_args(
        [
            "classify", "official-site",
            "--institution-id", "INST-1",
            "--institution-row", str(row),
            "--candidate-urls", str(urls),
        ]
    )
    assert args.func is cli._cmd_classify_official_site
    assert args.model == DEFAULT_MODEL


def test_classify_requires_institution_id():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["classify", "official-site"])


# ---------------------------------------------------------------------------
# presweep defaults + flags
# ---------------------------------------------------------------------------


def _presweep_args(tmp_path, *extra):
    master = tmp_path / "master_institutions.csv"
    master.write_text("institution_id\nINST-1\n", encoding="utf-8")
    return cli.build_parser().parse_args(
        ["presweep", "--run-id", "r1", "--master-csv", str(master), *extra]
    )


def test_presweep_defaults(tmp_path):
    args = _presweep_args(tmp_path)
    assert args.func is cli._cmd_presweep
    assert args.execute is False  # dry-run by default (Session B Q8)
    assert args.stop_after == "extract"  # preserves Session B/D launch behavior
    assert args.preflight is False
    assert args.sample_size == 1000
    assert args.seed == 22294
    assert args.stratification == "equal"
    assert args.model == DEFAULT_MODEL


def test_presweep_execute_and_stop_after(tmp_path):
    args = _presweep_args(tmp_path, "--execute", "--stop-after", "validate")
    assert args.execute is True
    assert args.stop_after == "validate"


def test_presweep_preflight_flag(tmp_path):
    args = _presweep_args(tmp_path, "--preflight", "--cost-ceiling", "50")
    assert args.preflight is True
    assert args.cost_ceiling == 50.0


def test_presweep_rejects_missing_master_csv(tmp_path):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["presweep", "--run-id", "r1", "--master-csv", str(tmp_path / "absent.csv")]
        )


def test_presweep_rejects_bad_stop_after(tmp_path):
    with pytest.raises(SystemExit):
        _presweep_args(tmp_path, "--stop-after", "not-a-stage")


def test_presweep_rejects_bad_stratification(tmp_path):
    with pytest.raises(SystemExit):
        _presweep_args(tmp_path, "--stratification", "proportional")


# ---------------------------------------------------------------------------
# validate / persist run-dir guard
# ---------------------------------------------------------------------------


def test_validate_routing_and_run_dir_guard(tmp_path):
    args = cli.build_parser().parse_args(["validate", "--run-dir", str(tmp_path)])
    assert args.func is cli._cmd_validate
    assert args.run_dir == tmp_path  # type=_existing_dir resolved it
    assert args.model == DEFAULT_MODEL


def test_validate_rejects_missing_run_dir(tmp_path):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["validate", "--run-dir", str(tmp_path / "absent")])


def test_persist_routing_and_required_args(tmp_path):
    args = cli.build_parser().parse_args(
        ["persist", "--run-dir", str(tmp_path), "--run-id", "r1", "--version", "2"]
    )
    assert args.func is cli._cmd_persist
    assert args.run_dir == tmp_path
    assert args.run_id == "r1"
    assert args.version == 2
    assert args.overwrite is False


def test_persist_requires_run_id(tmp_path):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["persist", "--run-dir", str(tmp_path)])


def test_verify_model_routing():
    args = cli.build_parser().parse_args(["verify-model"])
    assert args.func is cli._cmd_verify_model
    assert args.model == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# stdout encoding (the cp1252 crash: work succeeds, only the print dies)
# ---------------------------------------------------------------------------


def _cp1252_stream():
    """A stdout that behaves like a Windows console at the default codepage."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def test_non_ascii_output_would_crash_a_cp1252_stream():
    """Pins the failure mode the fix exists for; if this stops raising, the
    encoding fix below is no longer testing anything."""
    stream = _cp1252_stream()
    with pytest.raises(UnicodeEncodeError):
        stream.write("Ministerstvo pro místní rozvoj — 数字政府")
        stream.flush()


def test_main_reconfigures_stdout_and_stderr_to_utf8(monkeypatch):
    out, err = _cp1252_stream(), _cp1252_stream()
    monkeypatch.setattr(cli.sys, "stdout", out)
    monkeypatch.setattr(cli.sys, "stderr", err)

    cli._force_utf8_streams()

    assert out.encoding == "utf-8"
    assert err.encoding == "utf-8"
    out.write("Ministerstvo pro místní rozvoj — 数字政府")
    out.flush()  # would raise UnicodeEncodeError before the reconfigure


def test_force_utf8_streams_tolerates_streams_without_reconfigure(monkeypatch):
    """pytest's own capture buffers do not expose ``reconfigure``; the guard
    must not turn a working stream into an AttributeError at CLI entry."""
    monkeypatch.setattr(cli.sys, "stdout", io.StringIO())
    monkeypatch.setattr(cli.sys, "stderr", io.StringIO())

    cli._force_utf8_streams()  # must not raise
