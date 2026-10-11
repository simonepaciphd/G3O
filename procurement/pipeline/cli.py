"""Command-line entry point: run a pipeline for one source.

Usage:
    python -m pipeline.cli run <source_id> [--limit N] [--since YYYY-MM --until YYYY-MM]
                                           [--cache-dir DIR] [--match] [--config config/sources.yaml]
    python -m pipeline.cli export <source_id>          # per-source QC CSV
    python -m pipeline.cli sources [--mode api] [--ocds]

`--limit N` runs the small-sample smoke path (prove the whole flow on a few
records before a full pull — standing lab rule). Run it before every full pull.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .core.base import Pipeline
from .core.classify import NLPClassifier
from .core.search import load_queries
from .core.store import StagingStore

# G3O inputs, read-only (subproject CLAUDE.md). Relative to the subproject root.
_MASTER_DIR = Path("..") / ".." / "inputs" / "G3O_Institution_Master" / "data_final"
MASTER_DEFAULT = _MASTER_DIR / "master_institutions.csv"
LEDGER_DEFAULT = _MASTER_DIR / "institution_key_ledger.csv"


def load_source_config(path: str, source_id: str) -> dict:
    """Pull one source's row out of config/sources.yaml, merged over defaults."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    defaults = data.get("defaults", {}) or {}
    for row in data.get("sources", []) or []:
        if row.get("source_id") == source_id:
            merged = {**defaults, **row}
            return merged
    raise SystemExit(
        f"source_id {source_id!r} not found in {path}. "
        f"List available ids with:  python -m pipeline.cli sources"
    )


def build_adapter(config: dict):
    """Import the per-source adapter module and instantiate its Adapter class.

    Convention: pipeline/adapters/<access_mode>/<source_id>.py defines
    `class Adapter(ApiSourceAdapter)` (or the bulk/scrape base). Cloned from the
    type template — see docs/architecture.md §3.
    """
    source_id = config["source_id"]
    mode = config["access_mode"]
    if mode == "manual":
        raise SystemExit(
            f"{source_id}: access_mode 'manual' is out of automation scope "
            "(41 sources, flagged for human collection)."
        )
    module_path = f"pipeline.adapters.{mode}.{source_id}"
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError:
        raise SystemExit(
            f"No adapter built yet for {source_id!r}. Expected {module_path.replace('.', '/')}.py — "
            f"clone pipeline/adapters/{mode}/_template.py and implement search()/fetch()."
        )
    adapter_cls = getattr(module, "Adapter", None)
    if adapter_cls is None:
        raise SystemExit(f"{module_path} defines no `Adapter` class.")
    return adapter_cls(config)


def cmd_run(args) -> int:
    config = load_source_config(args.config, args.source_id)
    if (config.get("verification_status") == "unverified_snapshot"
            and args.allow_unverified and args.limit is None):
        raise SystemExit(
            "--allow-unverified is restricted to a bounded smoke run. Add --limit 5; "
            "a full pull from an unverified source is prohibited by the standing lab rule."
        )
    if config.get("verification_status") == "unverified_snapshot" and not args.allow_unverified:
        raise SystemExit(
            f"{args.source_id}: verification_status is 'unverified_snapshot' — the endpoint, "
            "auth, pagination and rate limits in sources.yaml were generated mechanically from "
            "the tracker and have not been checked. Verify them, update the row, and re-run "
            "(or pass --allow-unverified for a deliberate probe)."
        )

    if args.limit is None:
        print("NOTE: no --limit given, this is a full pull. The standing lab rule "
              "is a small-sample smoke run first (e.g. --limit 5).", file=sys.stderr)
    if bool(args.since) != bool(args.until):
        raise SystemExit("--since and --until must be given together (YYYY-MM).")
    if args.since:
        config["window_since"], config["window_until"] = args.since, args.until
    if args.cache_dir:
        config["cache_dir"] = args.cache_dir

    queries = load_queries(args.queries)
    if queries.version.endswith("placeholder"):
        print(f"NOTE: query set {args.queries} is version {queries.version} — a PI placeholder. "
              "Output is a plumbing test, not evidence.", file=sys.stderr)

    index = None
    if args.match:
        from .core.matcher import InstitutionIndex
        index = InstitutionIndex.load(Path(args.master), Path(args.ledger))

    started = datetime.now(timezone.utc)
    adapter = build_adapter(config)
    store = StagingStore(args.out_dir)
    classifier = NLPClassifier(queries, threshold=args.threshold)

    report = Pipeline(adapter, queries, classifier, store, institution_index=index).run(
        limit=args.limit, strict=args.strict)
    store.export_csv("records")
    store.export_csv("extensions")
    store.export_per_source(args.source_id)
    store.close()

    manifest = write_manifest(args, adapter, report, classifier, queries, index, started)
    print(report.summary())
    print(f"manifest: {manifest}")
    for err in report.errors:
        print(f"  error: {err}", file=sys.stderr)
    return 1 if report.errors and args.strict else 0


def code_hash() -> str:
    """sha256 over every pipeline/*.py file, path-sorted: identifies the code a run used."""
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        # as_posix(): the same code must hash the same on Windows and macOS/Linux.
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_manifest(args, adapter, report, classifier, queries, index, started) -> Path:
    """One JSON record per run: what was asked, which versions ran, what happened."""
    from . import __version__
    from .core.matcher import MATCHER_VERSION
    fetch_failures = list(getattr(adapter, "fetch_failures", []) or [])
    search_failures = list(getattr(adapter, "search_failures", []) or [])
    finished = datetime.now(timezone.utc)
    manifest = {
        "source_id": args.source_id,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "command": sys.argv,
        "window": {"since": args.since, "until": args.until,
                   "months_read": getattr(adapter, "window_months", None)},
        "limit": args.limit,
        "out_dir": args.out_dir,
        "cache_dir": adapter.config.get("cache_dir"),
        "versions": {
            "pipeline": __version__,
            "code_sha256": code_hash(),
            "classifier": classifier.version,
            "query_set": queries.version,
            "matcher": MATCHER_VERSION if index is not None else None,
            "master_build_id": index.master_build_id if index is not None else None,
            "python": platform.python_version(),
        },
        "counts": {
            "fetched": report.fetched, "written": report.written,
            "candidate_yes": report.candidate_yes, "candidate_unclear": report.candidate_unclear,
            "candidate_no": report.candidate_no,
            "candidate_not_assessable": report.candidate_not_assessable,
            "review_queue": report.review_queue, "cannot_type": report.cannot_type,
            "linked": report.linked, "institution_review": report.sent_to_review,
            "fetch_failed": report.fetch_failed, "search_months_failed": len(search_failures),
            "errors": len(report.errors),
        },
        "qc": {
            "dispositions_sum_to_written": (report.candidate_yes + report.candidate_unclear
                                            + report.candidate_no + report.candidate_not_assessable
                                            ) == report.written,
            "every_record_matched_or_reviewed": (index is None
                                                 or report.linked + report.sent_to_review == report.written),
            "written_at_least_fetched_minus_errors": report.written >= report.fetched - len(report.errors),
        },
        "fetch_failures": fetch_failures,
        "search_failures": search_failures,
        "errors": report.errors,
    }
    out = Path(args.out_dir) / f"run_manifest_{args.source_id}_{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def cmd_export(args) -> int:
    store = StagingStore(args.out_dir)
    path = store.export_per_source(args.source_id)
    store.close()
    print(f"wrote {path}")
    return 0


def cmd_sources(args) -> int:
    with open(args.config, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    rows = data.get("sources", []) or []
    if args.mode:
        rows = [r for r in rows if r.get("access_mode") == args.mode]
    if args.ocds:
        rows = [r for r in rows if r.get("is_ocds")]
    for row in rows:
        print(f"{row['source_id']:<70} {row.get('access_mode',''):<7} "
              f"{'OCDS' if row.get('is_ocds') else '':<5} {row.get('country_iso3','')}")
    print(f"-- {len(rows)} source(s)", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline", description="G3O procurement pipeline")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the pipeline for one source_id")
    run.add_argument("source_id")
    run.add_argument("--config", default="config/sources.yaml")
    run.add_argument("--queries", default="config/genai_queries.yaml")
    run.add_argument("--out-dir", default="outputs/staging")
    run.add_argument("--limit", type=int, default=None,
                     help="Cap records for the small-sample smoke run.")
    run.add_argument("--threshold", type=float, default=0.5,
                     help="Classifier score threshold. Set it from the validation "
                          "sample, not from this default.")
    run.add_argument("--strict", action="store_true",
                     help="Abort on the first per-record failure.")
    run.add_argument("--allow-unverified", action="store_true",
                     help="Run against a source row still marked unverified_snapshot.")
    run.add_argument("--since", help="First month of the window, YYYY-MM (with --until).")
    run.add_argument("--until", help="Last month of the window, YYYY-MM, inclusive.")
    run.add_argument("--cache-dir", help="Run-scoped raw payload directory (archive it with the run).")
    run.add_argument("--match", action="store_true",
                     help="Match every staged buyer against the institution master.")
    run.add_argument("--master", default=str(MASTER_DEFAULT), help="master_institutions.csv (read-only).")
    run.add_argument("--ledger", default=str(LEDGER_DEFAULT), help="institution_key_ledger.csv (read-only).")
    run.set_defaults(func=cmd_run)

    export = sub.add_parser("export", help="Re-export a per-source QC CSV")
    export.add_argument("source_id")
    export.add_argument("--out-dir", default="outputs/staging")
    export.set_defaults(func=cmd_export)

    sources = sub.add_parser("sources", help="List configured sources")
    sources.add_argument("--config", default="config/sources.yaml")
    sources.add_argument("--mode", choices=["api", "bulk", "scrape", "manual"])
    sources.add_argument("--ocds", action="store_true", help="OCDS sources only")
    sources.set_defaults(func=cmd_sources)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
