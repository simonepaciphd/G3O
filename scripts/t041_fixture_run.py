#!/usr/bin/env python3
"""T-041 fixture run on the v2.7 new-run path (PI Q184 a). Logic: :mod:`g3o.run.fixture_run_t041`.

DRY RUN by default: no network, no paid call, no client built. It loads and validates the
selected fixtures, writes the per-fixture plan, a results file (every fixture ``not_run``)
and the report skeleton (``t041-dry-*.json``, ``T041-REPORT-dry.md``), and prints call and token counts with the cited
rate rows. A USD figure is printed only from the projection seeds (``--seeds`` or
``$G3O_PROJECTION_SEEDS``, PI Q177 a).

``--live`` is PAID and is run by the PI (red line 4). It also needs ``--max-usd`` (a soft
cap, checked between fixtures: a single fixture can overshoot it by its own cost) and
``--runtime FILE`` (a JSON object of every ``RuntimeSettings`` field, as a real v2.7 run's
``v27_runtime``), and is refused unless every gate of a real v2.7 run passes. Extractor
calls are sync (DP-030 / RC-D-001 B).

Output: ``--out-dir``, default ``$G3O_DRIVE_ROOT/agent-workspace/2026-10-27-reclass-plan/fixture-run``.
A live run writes its own files (``t041-live-*.json``, ``T041-REPORT-live.md``) and refuses
to start if any exists; each finished fixture is appended to ``t041-live-fixtures.jsonl`` at
once, and a crash or Ctrl-C still writes the results of the finished fixtures. Live run
directories go to ``--run-root`` (local, default ``~/.g3o/t041-runs``), one fresh
``<UTC stamp>/`` folder per invocation.

Example (dry run):
  python scripts/t041_fixture_run.py --seeds agent-workspace/2026-11-16-overnight/projection/seeds.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from g3o.run import fixture_run_t041 as fr  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "v27"
#: Model ids the dry run prices when no --runtime is given (the v2.7 bindings: jev-1.13.0; the
#: extractor and X35 on claude-haiku-5-5, PI ruling 139 a). --runtime overrides all three.
DEFAULT_MODELS = {"jev_model": "jev-1.13.0", "extractor_model": "claude-haiku-5-5", "x35_model": "claude-haiku-5-5"}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="PAID: make real calls (the PI runs it)")
    ap.add_argument("--max-usd", type=float, default=None, help="live: USD cap. SOFT: checked between fixtures, so a single fixture can "
                         "overshoot it by its own cost")
    ap.add_argument("--runtime", type=Path, default=None,
                    help="JSON object of every RuntimeSettings field (required with --live)")
    ap.add_argument("--continue-on-error", action="store_true",
                    help="live: go on after a fixture that stopped with an error after journaled spend "
                         "(default: stop the run there; a $0 refusal never stops it)")
    ap.add_argument("--group", action="append", choices=fr.GROUPS, default=None,
                    help="fixture group to select (repeatable); default: all three")
    ap.add_argument("--fixture", action="append", default=None, help="only this fixture id (repeatable)")
    ap.add_argument("--drive", default=None, help=f"G3O Drive root; default ${fr.DRIVE_ENV}")
    ap.add_argument("--out-dir", type=Path, default=None, help=f"default <drive>/{fr.OUT_SUBDIR}")
    ap.add_argument("--run-root", type=Path, default=None,
                    help="live: local folder for the fixture run directories (default ~/.g3o/t041-runs); "
                         "each live invocation makes a fresh <run-root>/<UTC stamp>/ and refuses if it exists")
    ap.add_argument("--seeds", default=None, help="projection seeds JSON (absolute, or relative to the Drive root)")
    ap.add_argument("--unlocated", choices=fr.UNLOCATED_POLICIES, default=fr.UNRESOLVED,
                    help="how a not-located expected value counts (default: unresolved; proposed question P3)")
    ap.add_argument("--searched-pages", choices=fr.SEARCHED_POLICIES, default=fr.SEARCHED_UNLINKED,
                    help="which fixture pages are searched pages (default: unlinked; proposed question P4)")
    ap.add_argument("--official-site", choices=fr.OFFICIAL_POLICIES, default=fr.OFFICIAL_PAGE_HOST,
                    help="official site recorded for a fixture run: page-host (the first searched page's host) or "
                         "none (an explicit no-site record); default page-host (proposed question P4)")
    return ap


def _seeds(raw: str | None, drive: Path | None) -> Any:
    """The projection seeds, or None when none is configured. Only the ``$G3O_PROJECTION_SEEDS`` /
    default lookup may be absent: an explicit ``--seeds`` that is unavailable raises (review LOW-2)."""
    from g3o.common import run_projection as rp

    if raw is not None and not Path(raw).is_absolute() and drive is not None:
        raw = str(drive / raw)
    try:
        return rp.load_seeds(raw)
    except rp.SeedsUnavailable:
        if raw is not None:
            raise
        return None


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    drive = fr.drive_root(args.drive)
    out_dir = args.out_dir or fr.default_out_dir(drive)
    if out_dir is None:
        print(f"error: no --out-dir and ${fr.DRIVE_ENV} is not set", file=sys.stderr)
        return 2
    if args.live and (args.max_usd is None or args.max_usd <= 0 or args.runtime is None):
        print("refused: --live needs --max-usd > 0 and --runtime FILE", file=sys.stderr)
        return 2
    if args.live and drive is None:
        print(f"refused: --live needs the Drive root (real fixture pages): set ${fr.DRIVE_ENV}", file=sys.stderr)
        return 2
    if args.live and (existing := fr.existing_live_outputs(out_dir)):
        print(f"refused: live outputs already exist in the output folder: {[p.name for p in existing]} "
              "(never overwritten; move them or pass another --out-dir)", file=sys.stderr)
        return 2
    runtime = json.loads(args.runtime.read_text(encoding="utf-8")) if args.runtime else None
    models = {k: (runtime or {}).get(k, v) for k, v in DEFAULT_MODELS.items()}

    fixtures = fr.select_fixtures(fr.load_fixtures(FIX), args.group or fr.GROUPS, args.fixture)
    problems = {f["fixture_id"]: p for f in fixtures if (p := fr.validate_fixture(f))}
    if problems:
        print(f"error: invalid fixtures: {json.dumps(problems)}", file=sys.stderr)
        return 2
    ft = fr.load_fixture_text_module(FIX)
    try:
        seeds = _seeds(args.seeds, drive)
    except (ValueError, OSError, LookupError) as exc:  # review L5 / LOW-2: malformed or missing --seeds, exit 2
        print(f"error: seeds file unusable: {exc}", file=sys.stderr)
        return 2
    if missing := fr.missing_seeds(seeds):
        print(f"error: seeds file lacks {', '.join(missing)}", file=sys.stderr)
        return 2
    target = seeds["spike_chunk_target_bytes"].value if seeds else None
    pages = {f["fixture_id"]: fr.fixture_pages(f, fixture_text=ft, drive=drive) for f in fixtures}
    plans = [fr.plan_fixture(f, pages[f["fixture_id"]], searched_policy=args.searched_pages,
                             chunk_target_bytes=target) for f in fixtures]
    est = fr.estimate(plans, seeds=seeds, **models)
    options = {"groups": args.group or list(fr.GROUPS), "fixtures": args.fixture, "unlocated": args.unlocated,
               "searched_pages": args.searched_pages, "official_site": args.official_site,
               "extractor_mode": "no_batch", "seeds": bool(seeds), "continue_on_error": args.continue_on_error}
    print(fr.format_estimate(est))
    if args.official_site == fr.OFFICIAL_PAGE_HOST and any(fr.fixture_group(f) == fr.GROUP_REAL for f in fixtures):
        print(f"warning: {fr.PAGE_HOST_NOTE}")

    if not args.live:
        results = [fr.not_run_result(f, "dry run") for f in fixtures]
        paths = fr.write_outputs(out_dir, mode=fr.MODE_DRY, plans=plans, est=est, results=results, options=options)
        print(f"dry run: no call made. wrote {paths['plan'].name}, {paths['results'].name}, {paths['report'].name} "
              f"to the output folder")
        return 0

    if est["seed_usd"] is not None:
        projected = est["seed_usd"]["extractor_sync_usd"] + est["seed_usd"]["jev_usd"]
        if projected > args.max_usd:
            print(f"refused: the seed scale ${projected:.4f} exceeds --max-usd {args.max_usd}", file=sys.stderr)
            return 2
    from g3o.common.credentials import resolve
    from g3o.run.presweep.v27_entry import build_v27_dispatch

    config = SimpleNamespace(v27_runtime=runtime, v27_extractor_mode="no_batch", scrape_host_delay_seconds=1.0,
                             scrape_respect_robots=True, scrape_render_on_download_failure=False,
                             scrape_unlocker_on_block=False, scrape_unlocker_on_empty=False, empty_page_min_chars=0)
    try:
        dispatch = fr.require_live_gates(build_v27_dispatch(config, resolve()))
    except Exception as exc:  # every gate refusal ends the run before any call
        print(f"refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        run_root = fr.fresh_run_root(args.run_root or fr.default_run_base(), fr.utc_stamp())
    except fr.RunRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    print(f"live run directories: {run_root}")
    options["run_root"] = str(run_root)
    jsonl = fr.output_paths(out_dir, fr.MODE_LIVE)["jsonl"]
    finished: list[dict[str, Any]] = []

    def keep(result: dict[str, Any]) -> None:  # review M2: flushed as each fixture completes
        finished.append(result)
        fr.append_result_jsonl(jsonl, result)

    run = None
    try:
        run = fr.run_live(fixtures, dispatch=dispatch, run_root=run_root, max_usd=args.max_usd,
                          page_loader=lambda f: pages[f["fixture_id"]], searched_policy=args.searched_pages,
                          official_policy=args.official_site, unlocated=args.unlocated,
                          continue_on_error=args.continue_on_error, on_result=keep,
                          access_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    finally:  # a crash or Ctrl-C still writes the results of the fixtures that finished
        if run is None:
            done = {r["fixture_id"] for r in finished}
            costs = [r.get("cost_usd") for r in finished if "cost_usd" in r]
            run = {"results": finished + [fr.not_run_result(f, "interrupted: the run ended before this fixture")
                                          for f in fixtures if f["fixture_id"] not in done],
                   "spent_usd": None if any(c is None for c in costs) else float(sum(costs)),
                   "stopped": "interrupted: the run raised or was stopped; finished fixtures are kept "
                              f"(also in {jsonl.name})"}
        paths = fr.write_outputs(out_dir, mode=fr.MODE_LIVE, plans=plans, est=est, results=run["results"],
                                 options=options, spent_usd=run["spent_usd"], stopped=run["stopped"])
    spent = "unpriced" if run["spent_usd"] is None else f"${run['spent_usd']:.4f}"
    print(f"live: spent {spent}; wrote {paths['results'].name}, {paths['report'].name} and {jsonl.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
