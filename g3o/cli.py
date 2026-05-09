"""G3O command-line interface.

Subcommands:
  discover                — run institution-driven Serper queries and print results.
  scrape                  — fetch a single URL and print the extracted text.
  classify official-site  — Stage 2 classifier (one institution per call).
  classify triage         — Stage 3 URL triage (one institution per call).
  extract                 — Stage 5 per-page LLM extraction (orchestrated via `presweep`).
  validate                — Stage 6 per-institution LLM consolidation.
  persist                 — Stage 7 deterministic CSV writer.
  presweep                — Phase 3 of Session B: stratified pre-sweep runner.
  verify-model            — One-job Batch API submit to confirm the model id (Q4).

Push #1 implemented `discover` and `scrape`. Session A of Push #2 added the
two `classify` subcommands. Session B (2026-05-09) added `extract` (library
only — invoked via `presweep`), `presweep`, and `verify-model`. Session C
(2026-05-09) added `validate` and `persist`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from g3o.classify.official_site import (
    build_official_site_job,
    parse_official_site_result,
)
from g3o.classify.url_triage import build_triage_job, parse_triage_result
from g3o.common.batch_client import (
    DEFAULT_MODEL,
    fetch_results,
    poll_batch,
    submit_batch,
)
from g3o.discovery.query_builder import build_queries
from g3o.discovery.serper_client import search_google
from g3o.scrape.fetcher import scrape_url


def _cmd_discover(args: argparse.Namespace) -> int:
    languages = [s.strip() for s in args.languages.split(",") if s.strip()]
    queries = build_queries(args.institution, languages)

    seen: set[str] = set()
    records: list[dict] = []
    for query, lang in queries:
        for r in search_google(query, num_results=args.limit):
            url = r.get("link", "")
            if url and url not in seen:
                seen.add(url)
                r["query"] = query
                r["language"] = lang
                records.append(r)

    json.dump(records, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_scrape(args: argparse.Namespace) -> int:
    result = scrape_url(
        args.url,
        force_refresh=args.force_refresh,
        force_render=args.force_render,
    )
    if args.text_only:
        sys.stdout.write(result.text)
    else:
        sys.stdout.write(result.model_dump_json(indent=2))
        sys.stdout.write("\n")
    return 0 if result.text else 1


# ---------------------------------------------------------------------------
# `classify` — Stages 2 and 3
# ---------------------------------------------------------------------------


def _load_institution_row(path: str, expected_id: str | None) -> dict[str, Any]:
    row = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(row, dict):
        raise SystemExit(f"--institution-row must be a JSON object, got {type(row).__name__}")
    if expected_id and row.get("institution_id") != expected_id:
        raise SystemExit(
            f"--institution-id={expected_id!r} does not match institution_row "
            f"institution_id={row.get('institution_id')!r}"
        )
    return row


def _load_candidate_urls(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        urls = data
    elif isinstance(data, dict) and "urls" in data:
        urls = data["urls"]
    elif isinstance(data, dict) and "candidate_urls" in data:
        urls = data["candidate_urls"]
    else:
        raise SystemExit(
            "--candidate-urls must be a JSON list or an object with a 'urls' "
            "or 'candidate_urls' field"
        )
    if not all(isinstance(u, str) for u in urls):
        raise SystemExit("--candidate-urls must contain only strings")
    return list(urls)


def _wait_for_terminal(
    batch_id: str, *, poll_interval: int, max_wait: int
) -> Any:
    deadline = time.monotonic() + max_wait
    status = poll_batch(batch_id)
    while not status.is_terminal:
        if time.monotonic() >= deadline:
            return status
        time.sleep(poll_interval)
        status = poll_batch(batch_id)
    return status


def _cmd_classify_official_site(args: argparse.Namespace) -> int:
    institution = _load_institution_row(args.institution_row, args.institution_id)
    candidate_urls = _load_candidate_urls(args.candidate_urls)
    custom_id = args.custom_id or f"{institution['institution_id']}-stage2"

    job = build_official_site_job(institution, candidate_urls, custom_id=custom_id)
    handle = submit_batch([job], model=args.model)
    submit_record = {
        "batch_id": handle.batch_id,
        "input_file_id": handle.input_file_id,
        "custom_id": custom_id,
        "n_jobs": handle.n_jobs,
    }
    if not args.wait:
        json.dump(submit_record, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    status = _wait_for_terminal(
        handle.batch_id, poll_interval=args.poll_interval, max_wait=args.max_wait
    )
    if not status.is_completed:
        sys.stderr.write(
            f"batch {handle.batch_id} ended in non-completed state: {status.status}\n"
        )
        return 1 if status.is_terminal else 2

    results = list(fetch_results(handle.batch_id, status=status))
    parsed = parse_official_site_result(results[0])
    json.dump(
        {**submit_record, "result": parsed.model_dump()}, sys.stdout, indent=2
    )
    sys.stdout.write("\n")
    return 0


def _cmd_classify_triage(args: argparse.Namespace) -> int:
    institution = _load_institution_row(args.institution_row, args.institution_id)
    candidate_urls = _load_candidate_urls(args.candidate_urls)
    custom_id = args.custom_id or f"{institution['institution_id']}-stage3"

    job = build_triage_job(
        institution,
        candidate_urls,
        official_site=args.official_site,
        custom_id=custom_id,
    )
    handle = submit_batch([job], model=args.model)
    submit_record = {
        "batch_id": handle.batch_id,
        "input_file_id": handle.input_file_id,
        "custom_id": custom_id,
        "n_jobs": handle.n_jobs,
    }
    if not args.wait:
        json.dump(submit_record, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    status = _wait_for_terminal(
        handle.batch_id, poll_interval=args.poll_interval, max_wait=args.max_wait
    )
    if not status.is_completed:
        sys.stderr.write(
            f"batch {handle.batch_id} ended in non-completed state: {status.status}\n"
        )
        return 1 if status.is_terminal else 2

    results = list(fetch_results(handle.batch_id, status=status))
    parsed = parse_triage_result(results[0], expected_urls=candidate_urls)
    json.dump(
        {**submit_record, "result": parsed.model_dump()}, sys.stdout, indent=2
    )
    sys.stdout.write("\n")
    return 0


def _cmd_extract(_args: argparse.Namespace) -> int:
    raise NotImplementedError(
        "Stage 5 extraction is submitted by the per-institution DAG runner; "
        "use `g3o presweep` (Session B) or the production runner (Session C). "
        "The library is at g3o.extract; see g3o/extract/README.md."
    )


def _cmd_validate(args: argparse.Namespace) -> int:
    from g3o.validate import run_consolidate

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        sys.stderr.write(f"--run-dir does not exist or is not a directory: {run_dir}\n")
        return 2
    summary = run_consolidate(
        run_dir,
        model=args.model,
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
        notes=args.notes,
    )
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def _cmd_persist(args: argparse.Namespace) -> int:
    from g3o.persist import write_run_csvs

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        sys.stderr.write(f"--run-dir does not exist or is not a directory: {run_dir}\n")
        return 2
    summary = write_run_csvs(
        run_dir,
        run_id=args.run_id,
        run_model=args.model,
        version=args.version,
        overwrite=args.overwrite,
    )
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# `presweep` — Phase 3 of Session B
# ---------------------------------------------------------------------------


def _cmd_presweep(args: argparse.Namespace) -> int:
    from g3o.common.config import RUNS_DIR
    from g3o.run.presweep import PresweepConfig, run_presweep

    config = PresweepConfig(
        run_id=args.run_id,
        runs_dir=Path(args.runs_dir or RUNS_DIR),
        master_csv=Path(args.master_csv),
        sample_size=args.sample_size,
        seed=args.seed,
        stratification=args.stratification,
        institution_search_languages=args.institution_search_languages,
        discovery_languages=tuple(
            s.strip() for s in args.discovery_languages.split(",") if s.strip()
        ),
        discovery_results_per_query=args.discovery_results_per_query,
        dry_run=not args.execute,
        stop_after=args.stop_after,
        poll_interval=args.poll_interval,
        max_wait_per_stage=args.max_wait_per_stage,
        model=args.model,
    )
    summary = run_presweep(config)
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# `verify-model` — Q4 (2026-05-09)
# ---------------------------------------------------------------------------


def _cmd_verify_model(args: argparse.Namespace) -> int:
    from g3o.run.verify_model import verify_model

    summary = verify_model(
        model=args.model, poll_interval=args.poll_interval, max_wait=args.max_wait
    )
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


def _add_classify_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--institution-id", required=True,
        help="Institution ID (must match institution_row.institution_id).",
    )
    p.add_argument(
        "--institution-row", required=True,
        help="Path to a JSON file with the institution row (id, name, country, "
             "branch, level, ...).",
    )
    p.add_argument(
        "--candidate-urls", required=True,
        help="Path to a JSON file containing the candidate URLs (a JSON list, "
             "or an object with key 'urls' or 'candidate_urls').",
    )
    p.add_argument("--custom-id", default=None, help="Override the per-job custom_id.")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model (default: {DEFAULT_MODEL}).")
    p.add_argument(
        "--wait", action="store_true",
        help="Block on poll_batch until the batch reaches a terminal state, then "
             "print the parsed result.",
    )
    p.add_argument(
        "--poll-interval", type=int, default=30,
        help="Polling interval in seconds when --wait is set (default: 30).",
    )
    p.add_argument(
        "--max-wait", type=int, default=1800,
        help="Maximum total wait in seconds when --wait is set (default: 1800).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="g3o",
        description="G3O production pipeline: discover, scrape, classify, extract, validate.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="Run institution-driven Serper queries.")
    discover.add_argument("--institution", required=True, help="Institution name (verbatim).")
    discover.add_argument(
        "--languages", default="en", help="Comma-separated ISO 639-1 codes (default: en)."
    )
    discover.add_argument(
        "--limit", type=int, default=5, help="Max results per query (default: 5)."
    )
    discover.set_defaults(func=_cmd_discover)

    scrape = sub.add_parser("scrape", help="Fetch and extract content from a single URL.")
    scrape.add_argument("--url", required=True, help="URL to fetch.")
    scrape.add_argument(
        "--force-refresh", action="store_true", help="Bypass the on-disk cache."
    )
    scrape.add_argument(
        "--force-render",
        action="store_true",
        help="Skip html/pdf paths and go straight to the headless renderer.",
    )
    scrape.add_argument(
        "--text-only", action="store_true", help="Print only the extracted text."
    )
    scrape.set_defaults(func=_cmd_scrape)

    classify = sub.add_parser(
        "classify", help="Stages 2 + 3 — official-site and URL-triage classifiers."
    )
    classify_sub = classify.add_subparsers(dest="classify_command", required=True)

    cs_official = classify_sub.add_parser(
        "official-site",
        help="Stage 2 — pick the official institutional homepage from candidate URLs.",
    )
    _add_classify_common_args(cs_official)
    cs_official.set_defaults(func=_cmd_classify_official_site)

    cs_triage = classify_sub.add_parser(
        "triage",
        help="Stage 3 — keep/drop classification for each candidate URL.",
    )
    _add_classify_common_args(cs_triage)
    cs_triage.add_argument(
        "--official-site", default=None,
        help="The official-site URL from Stage 2 (or omit for null).",
    )
    cs_triage.set_defaults(func=_cmd_classify_triage)

    extract = sub.add_parser(
        "extract",
        help="Stage 5 per-page LLM extraction (orchestrated via `presweep`).",
    )
    extract.set_defaults(func=_cmd_extract)

    validate = sub.add_parser(
        "validate",
        help="Stage 6 — per-institution LLM consolidation across Stage 5 extract rows.",
    )
    validate.add_argument(
        "--run-dir",
        required=True,
        help="Path to runs/<run_id>/ directory containing per-institution Stage 5 outputs.",
    )
    validate.add_argument("--model", default=DEFAULT_MODEL)
    validate.add_argument("--poll-interval", type=int, default=60)
    validate.add_argument(
        "--max-wait",
        type=int,
        default=25 * 60 * 60,
        help="Max seconds to wait for the Stage 6 batch (default: 25h ~ SLA + jitter).",
    )
    validate.add_argument(
        "--notes",
        default="none",
        help="Free-text notes recorded into consolidation_metadata.notes.",
    )
    validate.set_defaults(func=_cmd_validate)

    persist = sub.add_parser(
        "persist",
        help="Stage 7 — write the three canonical CSVs from runs/<run_id>/<inst>/6_validate.json.",
    )
    persist.add_argument(
        "--run-dir",
        required=True,
        help="Path to runs/<run_id>/ directory containing per-institution 6_validate.json.",
    )
    persist.add_argument(
        "--run-id",
        required=True,
        help="Run identifier pinned into provenance and the summary CSV.",
    )
    persist.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"run_model recorded in provenance (default: {DEFAULT_MODEL}).",
    )
    persist.add_argument(
        "--version",
        type=int,
        default=1,
        help="v{N} suffix on output filenames (default: 1).",
    )
    persist.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing CSVs at the target paths.",
    )
    persist.set_defaults(func=_cmd_persist)

    presweep = sub.add_parser(
        "presweep",
        help="Stratified pre-sweep runner (Phase 3 of Session B).",
    )
    presweep.add_argument("--run-id", required=True, help="Run identifier (e.g. 20260509-presweep).")
    presweep.add_argument(
        "--master-csv", required=True,
        help="Path to master_institutions.csv (read-only).",
    )
    presweep.add_argument(
        "--runs-dir", default=None,
        help="Output dir for runs/<run_id>/. Defaults to G3O_RUNS_DIR or <repo>/runs.",
    )
    presweep.add_argument("--sample-size", type=int, default=1000)
    presweep.add_argument("--seed", type=int, default=22294)
    presweep.add_argument(
        "--stratification", choices=["equal"], default="equal",
        help="Equal-per-stratum (Q3=equal, 2026-05-09).",
    )
    presweep.add_argument(
        "--institution-search-languages", default="en",
        help="Comma-separated ISO 639-1 codes recorded into per-row institution_search_languages.",
    )
    presweep.add_argument(
        "--discovery-languages", default="en",
        help="Comma-separated ISO 639-1 codes used in Stage 1 query construction.",
    )
    presweep.add_argument("--discovery-results-per-query", type=int, default=5)
    presweep.add_argument(
        "--execute", action="store_true",
        help=(
            "Run Stages 1a/2/1b/3/4/5 live (and Stage 6 with "
            "--stop-after validate). Default is --dry-run (no live submits) "
            "per Session B Q8. Resume is auto-inferred from the presence of "
            "_state/ files in runs/<run_id>/ (Session E Q7=c)."
        ),
    )
    presweep.add_argument(
        "--stop-after",
        choices=[
            "discovery_general",
            "classify_official_site",
            "discovery_site_restricted",
            "classify_triage",
            "scrape",
            "extract",
            "validate",
        ],
        default="extract",
        help=(
            "Stop after this stage (only meaningful with --execute). "
            "Default 'extract' preserves Session B/D launch behavior; pass "
            "'validate' to also run Stage 6 (per Q8=ii Session E fold)."
        ),
    )
    presweep.add_argument("--poll-interval", type=int, default=60)
    presweep.add_argument(
        "--max-wait-per-stage", type=int, default=25 * 60 * 60,
        help="Max seconds to wait per Batch API stage (default: 25h ~ SLA + jitter).",
    )
    presweep.add_argument("--model", default=DEFAULT_MODEL)
    presweep.set_defaults(func=_cmd_presweep)

    verify = sub.add_parser(
        "verify-model",
        help="One-job Batch API submit to confirm the model id (Q4).",
    )
    verify.add_argument("--model", default=DEFAULT_MODEL)
    verify.add_argument("--poll-interval", type=int, default=30)
    verify.add_argument("--max-wait", type=int, default=1800)
    verify.set_defaults(func=_cmd_verify_model)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
