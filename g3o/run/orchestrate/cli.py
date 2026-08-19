"""The orchestrator's command line — one verb per leg (Item 3).

Separate from ``g3o/cli.py`` on purpose. The pipeline CLI is the *measurement
instrument*: it discovers, classifies, extracts, persists. This one is the
*operations* surface: it starts a run on a droplet, watches it, loads it,
archives it, and asks the public API what it can see. They have different
audiences, different failure modes, and — during this sprint — different lanes,
and the Item 3 brief asks for new files rather than edits to shared ones.

Invoked as ``python -m g3o.run.orchestrate <verb>``. Exit codes are uniform
across every verb, because they are read by shell scripts and by the joint gate:

===  ==============================================================
 0   the leg did what it was asked and the result is green
 1   the leg ran and the result is **not** green (a failed run, a
     strict-check failure, a run the API cannot see when it should)
 2   the leg refused, or could not run at all — nothing was changed
===  ==============================================================

The distinction between 1 and 2 is the one that matters operationally: 1 means
"look at the result", 2 means "the thing you asked for did not happen".
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from g3o.common.credentials import Credentials
from g3o.run.orchestrate.status import RunStatus, run_status
from g3o.run.presweep.config import STAGES

EXIT_OK = 0
EXIT_NOT_GREEN = 1
EXIT_REFUSED = 2


def _runs_dir(args: argparse.Namespace) -> Path:
    from g3o.common.config import RUNS_DIR

    return Path(args.runs_dir) if args.runs_dir else Path(RUNS_DIR)


def _resolve_run_id(args: argparse.Namespace) -> str:
    """The run id, or the newest run directory when ``--latest`` was passed.

    Newest by *name*, which is exact rather than approximate: a minted id is
    ``r<YYYYMMDD>T<HHMMSS>Z-<4hex>`` (§2), so lexical order is chronological
    order. Legacy ids sort before every minted one, which is the right answer for
    "the latest run" on a machine that has both.
    """
    if getattr(args, "run_id", None):
        return str(args.run_id)
    if not getattr(args, "latest", False):
        raise SystemExit("pass --run-id, or --latest to take the newest run directory.")
    runs_dir = _runs_dir(args)
    candidates = sorted(p.name for p in runs_dir.iterdir() if p.is_dir()) if runs_dir.is_dir() else []
    if not candidates:
        raise SystemExit(f"no run directories under {runs_dir}.")
    return candidates[-1]


def _emit(payload: dict[str, Any], text: str, *, as_json: bool) -> None:
    if as_json:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text + "\n")


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


def _effective_ceiling(args: argparse.Namespace) -> float | None:
    """CLI flag > ``G3O_BUDGET_LIMIT_USD`` > none.

    The same precedence ``g3o.cli._effective_budget`` applies, reused rather than
    re-decided: two paths that disagree about which ceiling is in force would be
    worse than neither having one.
    """
    from g3o.cli import _parse_budget_limit
    from g3o.common.config import BUDGET_LIMIT_USD

    if getattr(args, "cost_ceiling", None) is not None:
        return float(args.cost_ceiling)
    return _parse_budget_limit(BUDGET_LIMIT_USD)


def _cmd_submit(args: argparse.Namespace) -> int:
    from g3o.run.orchestrate.submit import SubmitError, load_config_file, submit

    try:
        config = load_config_file(Path(args.config))
    except SubmitError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_REFUSED

    # Overrides, applied after the file so a one-liner can vary the two or three
    # things an operator actually varies between runs without editing the file.
    # Everything else lives in the config file, which is then the record of what
    # was submitted — see docs/runbook-orchestrator.md.
    overrides: dict[str, Any] = {}
    for flag, field_name in (
        ("sample_size", "sample_size"),
        ("seed", "seed"),
        ("stop_after", "stop_after"),
        ("model", "model"),
        ("max_workers", "max_workers"),
        ("filter_mode", "filter_mode"),
    ):
        value = getattr(args, flag, None)
        if value is not None:
            overrides[field_name] = value
    if args.master_csv:
        overrides["master_csv"] = Path(args.master_csv)
    if args.runs_dir:
        overrides["runs_dir"] = Path(args.runs_dir)
    if args.execute:
        overrides["dry_run"] = False
    if args.run_id:
        overrides["run_id"] = args.run_id
    if overrides:
        try:
            config = replace(config, **overrides)
        except ValueError as exc:  # __post_init__ refusals stay operator-facing
            sys.stderr.write(f"invalid run config after overrides: {exc}\n")
            return EXIT_REFUSED

    try:
        receipt = submit(
            config,
            credentials=Credentials(label=args.key_label),
            session_id=args.session_id,
            detach=args.detach,
            cost_ceiling_usd=_effective_ceiling(args),
        )
    except SubmitError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_REFUSED
    except Exception as exc:  # noqa: BLE001 - a foreground run's own failure
        # The failure is already recorded (submit record) and, past the manifest,
        # in the run's own `run_failed` event. Printing the class and message here
        # is what the operator reads; the traceback is in the log.
        sys.stderr.write(f"run failed: {type(exc).__name__}: {exc}\n")
        return EXIT_NOT_GREEN

    payload = receipt.to_dict()
    if receipt.detached:
        text = (
            f"run_id={receipt.run_id}\n"
            f"  detached as pid {receipt.pid}; this shell may now be closed.\n"
            f"  log    : {receipt.log_path}\n"
            f"  status : python -m g3o.run.orchestrate status --run-id {receipt.run_id}"
        )
    else:
        outcome = receipt.receipt.outcome if receipt.receipt else "unknown"
        text = f"run_id={receipt.run_id}\n  outcome: {outcome}\n  run dir: {receipt.run_dir}"
    _emit(payload, text, as_json=args.json)
    if receipt.receipt is not None and receipt.receipt.outcome == "failed":
        return EXIT_NOT_GREEN
    return EXIT_OK


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def _cmd_status(args: argparse.Namespace) -> int:
    status: RunStatus = run_status(_runs_dir(args), _resolve_run_id(args))
    _emit(status.to_dict(), status.one_line(), as_json=args.json)
    if status.state == "missing":
        return EXIT_REFUSED
    return EXIT_NOT_GREEN if status.is_failed else EXIT_OK


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


def _cmd_ingest(args: argparse.Namespace) -> int:
    from g3o.run.orchestrate.ingest import IngestError, ingest_run, render_ingest

    try:
        result = ingest_run(
            _runs_dir(args),
            _resolve_run_id(args),
            frame_id=args.frame_id,
            loader_repo=Path(args.loader_repo) if args.loader_repo else None,
            master_csv=Path(args.master_csv) if args.master_csv else None,
            extra_args=tuple(args.loader_arg or ()),
            expect_loader_sha=args.expect_loader_sha,
            force=args.force,
        )
    except IngestError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_REFUSED
    _emit(result.to_dict(), render_ingest(result), as_json=args.json)
    return EXIT_OK if result.green else EXIT_NOT_GREEN


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------


def _cmd_archive(args: argparse.Namespace) -> int:
    from g3o.run.orchestrate.archive_leg import (
        ArchiveLegError,
        archive_and_upload,
        render_archive,
    )
    from g3o.run.orchestrate.objectstore import ObjectStoreError

    try:
        result = archive_and_upload(
            _runs_dir(args),
            _resolve_run_id(args),
            destination=args.destination,
            apply=args.apply,
            force=args.force,
        )
    except (ArchiveLegError, ObjectStoreError) as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_REFUSED
    _emit(result.to_dict(), render_archive(result), as_json=args.json)
    if result.uploaded and not result.verified:
        return EXIT_NOT_GREEN
    return EXIT_OK


# ---------------------------------------------------------------------------
# publish-verify
# ---------------------------------------------------------------------------


def _cmd_publish_verify(args: argparse.Namespace) -> int:
    import os

    from g3o.run.orchestrate.publish import (
        API_BASE_ENV_VAR,
        PublishVerifyError,
        render_publish,
        verify_published,
    )

    api_base = args.api_base or os.environ.get(API_BASE_ENV_VAR)
    if not api_base:
        sys.stderr.write(
            f"no API base. Pass --api-base or set {API_BASE_ENV_VAR} "
            f"(e.g. https://api.g3observatory.org).\n"
        )
        return EXIT_REFUSED
    expect: bool | None = None
    if args.expect_visible:
        expect = True
    elif args.expect_hidden:
        expect = False
    try:
        result = verify_published(
            _runs_dir(args),
            _resolve_run_id(args),
            api_base=api_base,
            wave=args.wave,
            sample=args.sample,
            expect_visible=expect,
        )
    except PublishVerifyError as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_REFUSED
    _emit(result.to_dict(), render_publish(result), as_json=args.json)
    if result.verdict == "pass":
        return EXIT_OK
    return EXIT_NOT_GREEN if result.verdict == "fail" else EXIT_REFUSED


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _add_run_selector(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", default=None, help="The run to act on.")
    parser.add_argument(
        "--latest", action="store_true",
        help="Use the newest run directory instead of naming one. Minted ids sort "
             "chronologically, so 'newest by name' is exact.",
    )
    parser.add_argument(
        "--runs-dir", default=None,
        help="Where runs/<run_id>/ live. Defaults to G3O_RUNS_DIR or <repo>/runs.",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m g3o.run.orchestrate",
        description=(
            "Operate a G3O run end to end: submit it on a machine you can "
            "disconnect from, watch it, load it, archive it, and verify what the "
            "public API can see."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    submit = sub.add_parser(
        "submit",
        help="Start a run (optionally detached, surviving this shell).",
        description=(
            "Starts a run through g3o.run.api.launch(). The run id is minted here "
            "and printed immediately, so a detached run can be monitored and "
            "resumed while it is still in flight. Resume is not a separate verb: "
            "re-invoke with --run-id and it rejoins (Run API spec §1.3)."
        ),
    )
    _add_run_selector(submit)
    submit.add_argument(
        "--config", required=True,
        help="JSON object of PresweepConfig fields — the record of what was "
             "submitted. See docs/runbook-orchestrator.md for a starting file.",
    )
    submit.add_argument(
        "--detach", action="store_true",
        help="Return as soon as the run is running, in a new session with no "
             "controlling terminal (what nohup does). Off by default: a detached "
             "default would surprise anyone running this locally.",
    )
    submit.add_argument("--execute", action="store_true", help="Live spend (default is a dry run).")
    submit.add_argument(
        "--cost-ceiling", type=float, default=None,
        help=(
            "Refuse the submit if the preflight projects OpenAI Batch spend above "
            "this many USD. Falls back to $G3O_BUDGET_LIMIT_USD. Checked before "
            "the detach fork, so it binds identically detached or not, and the "
            "projection that cleared is recorded at "
            "_orchestrator/cost_projection.json. No ceiling set means no cap — "
            "state one for any run you are not watching."
        ),
    )
    submit.add_argument("--master-csv", default=None)
    submit.add_argument("--sample-size", type=int, default=None)
    submit.add_argument("--seed", type=int, default=None)
    # Constrained rather than free text: `stop_after` is a Literal that
    # ``PresweepConfig`` does not validate at construction, so a typo survives
    # the config and surfaces deep inside the orchestrator as
    # `tuple.index(x): x not in tuple` — an unreadable message, hours later on a
    # detached run. argparse refuses it in the shell instead.
    submit.add_argument("--stop-after", choices=STAGES, default=None)
    submit.add_argument("--model", default=None)
    submit.add_argument("--max-workers", type=int, default=None)
    submit.add_argument("--filter-mode", choices=("off", "shadow", "enforce"), default=None)
    submit.add_argument(
        "--key-label", default=None,
        help="Human tag for the keys this run spends (e.g. 'key-B-grant'). Recorded "
             "next to their fingerprints; the keys themselves stay in the environment.",
    )
    submit.add_argument(
        "--session-id", default=None,
        help="Harness/session join key (spec §4.2): this flag, then G3O_SESSION_ID, "
             "then 'unattended'.",
    )
    submit.set_defaults(func=_cmd_submit)

    status = sub.add_parser(
        "status",
        help="One line: what this run is doing right now.",
        description=(
            "Derived from manifest + events + _state/, plus the supervisor record "
            "for liveness. Exit 1 for a failed or interrupted run, 2 for a run "
            "that is not there."
        ),
    )
    _add_run_selector(status)
    status.set_defaults(func=_cmd_status)

    ingest = sub.add_parser(
        "ingest",
        help="Load a completed run via the pinned g3o-api scripts/ingest.py.",
        description=(
            "Refuses a run that did not complete. Passes the loader's exit code "
            "through and reports its counts without interpretation — including "
            "reporting that they could not be parsed, which is never the same as "
            "reporting zero."
        ),
    )
    _add_run_selector(ingest)
    ingest.add_argument(
        "--frame-id", required=True,
        help=(
            "Loader --frame-id: the master build this run sampled from, e.g. "
            "mb-2026-07-30. Required while the manifest's frame block is null, "
            "which it is on every run the pipeline emits today. There is no "
            "--wave-id any more: under schema v0.6 a run belongs to a wave iff "
            "its run_started_at falls inside a g3o.wave_windows span, which is a "
            "property of the database, not of this invocation."
        ),
    )
    ingest.add_argument(
        "--loader-repo", default=None,
        help="Pinned g3o-api checkout (owns scripts/ingest.py). Defaults to $G3O_API_REPO.",
    )
    ingest.add_argument(
        "--master-csv", default=None,
        help="Override the master. Defaults to the one the run's manifest records.",
    )
    ingest.add_argument(
        "--loader-arg", action="append", default=None, metavar="ARG",
        help="Extra argument passed straight to ingest.py; repeatable "
             "(e.g. --loader-arg --synthetic). Its flag surface is the "
             "backend's, and is deliberately not mirrored here.",
    )
    ingest.add_argument(
        "--expect-loader-sha", default=None,
        help="Refuse unless the g3o-api checkout is at this commit.",
    )
    ingest.add_argument(
        "--force", action="store_true",
        help="Load a run that did not complete. Recorded in the leg record.",
    )
    ingest.set_defaults(func=_cmd_ingest)

    archive = sub.add_parser(
        "archive",
        help="Tar, hash, inventory, upload, and verify a finished run.",
        description=(
            "Without --apply this is a dry run: preconditions are checked and the "
            "plan is printed. With --apply and --destination, every uploaded "
            "object is streamed back out of the store and re-hashed."
        ),
    )
    _add_run_selector(archive)
    archive.add_argument(
        "--apply", action="store_true",
        help="Actually tar and delete the source shards (g3o.run.archive's own gate).",
    )
    archive.add_argument(
        "--destination", default=None, metavar="URI",
        help="s3://bucket/prefix (DigitalOcean Spaces), file:///path, or a plain "
             "directory. Omit to archive locally without uploading.",
    )
    archive.add_argument(
        "--force", action="store_true", help="Archive a run that did not finish.",
    )
    archive.set_defaults(func=_cmd_archive)

    publish = sub.add_parser(
        "publish-verify",
        help="Ask the public API what it can see of this run. Read-only.",
        description=(
            "Checks visibility against an expectation: a completed run should be "
            "visible, a failed or killed one should not. Publishes nothing and "
            "flips nothing — cutting a wave window is the PI's act."
        ),
    )
    _add_run_selector(publish)
    publish.add_argument("--api-base", default=None, help="Defaults to $G3O_API_BASE.")
    publish.add_argument("--wave", default=None, help="Pin the wave (default: the API's current).")
    publish.add_argument(
        "--sample", type=int, default=10,
        help="Institutions to check, deterministically sampled. 0 checks all.",
    )
    publish.add_argument(
        "--expect-visible", action="store_true",
        help="Assert the run IS visible (default: inferred from the run's state).",
    )
    publish.add_argument(
        "--expect-hidden", action="store_true",
        help="Assert the run is NOT visible — the out-of-window and "
             "induced-failure checks.",
    )
    publish.set_defaults(func=_cmd_publish_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    from g3o.cli import _force_utf8_stdio

    _force_utf8_stdio()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


__all__ = ["EXIT_NOT_GREEN", "EXIT_OK", "EXIT_REFUSED", "build_parser", "main"]
