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
  presweep-report         — Stage-by-stage funnel health report for a finished run.
  run-diff                — Cross-run determinism report over 2+ run dirs (disk-only).
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
from g3o.classify.url_triage import (
    build_triage_job,
    match_triage_decisions,
    parse_triage_result,
)
from g3o.common.batch_client import (
    DEFAULT_MODEL,
    fetch_results,
    poll_batch,
    submit_batch,
)
from g3o.discovery.query_builder import DEFAULT_EVIDENCE_TERM, build_queries
from g3o.discovery.serper_client import search_google
from g3o.scrape.fetcher import scrape_url


def _existing_file(arg: str) -> Path:
    """argparse `type=` callable: resolve `arg` to an existing file or fail
    with a parser-level error before the subcommand body runs."""
    p = Path(arg)
    if not p.is_file():
        raise argparse.ArgumentTypeError(f"file does not exist: {arg}")
    return p


def _existing_dir(arg: str) -> Path:
    """argparse `type=` callable: resolve `arg` to an existing directory or
    fail with a parser-level error before the subcommand body runs."""
    p = Path(arg)
    if not p.is_dir():
        raise argparse.ArgumentTypeError(f"directory does not exist: {arg}")
    return p


def _cmd_discover(args: argparse.Namespace) -> int:
    languages = [s.strip() for s in args.languages.split(",") if s.strip()]
    queries = build_queries(
        args.institution,
        languages,
        country=args.country,
        disambiguation=args.disambiguation,
    )

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
    if not result.text:
        print(f"scrape returned empty content for {args.url}", file=sys.stderr)
        return 1
    return 0


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
    parsed = parse_triage_result(results[0])
    match = match_triage_decisions(candidate_urls, parsed)
    json.dump(
        {
            **submit_record,
            "result": {"decisions": [d.model_dump() for d in match.decisions]},
            "kept_urls": match.kept_urls,
            "attrition": [
                {"url": c.url, "reason": c.reason, "detail": c.detail}
                for c in match.attrition
            ],
        },
        sys.stdout,
        indent=2,
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

    # --run-dir existence is enforced by `type=_existing_dir` in build_parser.
    run_dir = Path(args.run_dir)
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


def _run_date_from_manifest(run_dir: Path) -> str | None:
    """Stage 7 provenance ``run_date`` default, read from the run's manifest.

    Review F18b: ``persist`` previously stamped ``run_date`` = day-of-writing,
    which drifts from the run's actual date whenever CSVs are (re)written on a
    later day. The manifest records the authoritative ``run_date`` at plan time;
    prefer it. Falls back to ``None`` (→ writer uses UTC today, the prior
    behavior) when no manifest or no usable date is present.
    """
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    run_date = manifest.get("run_date")
    return run_date if isinstance(run_date, str) and run_date else None


def _cmd_persist(args: argparse.Namespace) -> int:
    from g3o.persist import write_run_csvs

    # --run-dir existence is enforced by `type=_existing_dir` in build_parser.
    run_dir = Path(args.run_dir)
    summary = write_run_csvs(
        run_dir,
        run_id=args.run_id,
        run_model=args.model,
        version=args.version,
        overwrite=args.overwrite,
        # Provenance accuracy (review F18b): default the date from the manifest
        # rather than today; writer still falls back to UTC today when absent.
        run_date=_run_date_from_manifest(run_dir),
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
        discovery_languages=tuple(
            s.strip() for s in args.discovery_languages.split(",") if s.strip()
        ),
        discovery_results_per_query=args.discovery_results_per_query,
        discovery_mode=args.discovery_mode,
        discovery_evidence_term=args.discovery_evidence_term,
        discovery_domain_quote_name=args.discovery_domain_quote_name,
        # "omit" -> None (no key in the payload at all), "off" -> False.
        serper_autocorrect=None if args.serper_autocorrect == "omit" else False,
        dry_run=not args.execute,
        stop_after=args.stop_after,
        filter_mode=args.filter_mode,
        poll_interval=args.poll_interval,
        max_wait_per_stage=args.max_wait_per_stage,
        model=args.model,
        max_workers=args.max_workers,
    )
    if args.preflight:
        from g3o.run.preflight import PreflightAssumptions, run_preflight

        summary = run_preflight(
            config,
            assumptions=PreflightAssumptions(
                pages_per_institution=args.assume_pages_per_institution,
                page_chars=args.assume_page_chars,
                output_tokens_per_job=args.assume_output_tokens_per_job,
            ),
            verify_model_live=args.verify_model,
            cost_ceiling_usd=args.cost_ceiling,
        )
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
        # Exit non-zero only on a hard readiness failure (keys); the cost ceiling
        # is informational (D7 print-only, 2026-06-10).
        return 0 if summary.get("keys_ok") else 1

    summary = run_presweep(config)
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


# ---------------------------------------------------------------------------
# `verify-model` — Q4 (2026-05-09)
# ---------------------------------------------------------------------------


def _cmd_presweep_report(args: argparse.Namespace) -> int:
    from g3o.report import (
        HealthThresholds,
        compute_health_report,
        compute_language_breakdown,
        render_text_report,
    )

    run_dir = Path(args.run_dir)
    thresholds = None
    if args.thresholds:
        thresholds = HealthThresholds.from_json(args.thresholds)

    if args.language_breakdown:
        breakdown = compute_language_breakdown(run_dir, thresholds=thresholds)
        json_path = run_dir / "_health_report_by_language.json"
        json_path.write_text(
            json.dumps(breakdown, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        json.dump(breakdown, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        sys.stderr.write(f"Per-language JSON report written to: {json_path}\n")
        return 0

    report = compute_health_report(run_dir, thresholds=thresholds, language=args.language)

    # Always write JSON to <run_dir>/_health_report.json (underscore prefix
    # keeps it alongside other run metadata like _attrition.jsonl). A language
    # filter gets its own suffixed file so repeated per-language runs don't
    # clobber each other or the unrestricted report.
    suffix = f"_{args.language}" if args.language else ""
    json_path = run_dir / f"_health_report{suffix}.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Run-level Stage 1c summary (the shadow-recall metric's home — kept out of
    # the per-institution 1c artifacts so those stay byte-reproducible; design
    # memo 2026-07-06). Only written when the filter actually ran.
    filter_block = report.get("filter_eligibility", {})
    if filter_block.get("ran"):
        (run_dir / f"_filter_eligibility_summary{suffix}.json").write_text(
            json.dumps(filter_block, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text_report(report))
        sys.stdout.write("\n")
        sys.stderr.write(f"JSON report written to: {json_path}\n")

    overall = report.get("overall_flag", "green")
    return 2 if overall == "fail" else (1 if overall == "warn" else 0)


def _cmd_run_diff(args: argparse.Namespace) -> int:
    from g3o.report import compute_run_diff, render_run_diff_text

    # Each run-dir's existence is enforced by `type=_existing_dir`; require 2+.
    run_dirs = [Path(d) for d in args.run_dirs]
    if len(run_dirs) < 2:
        sys.stderr.write("run-diff requires at least two run directories\n")
        return 2

    report = compute_run_diff(run_dirs)

    # Machine-readable report lands in the first run dir (underscore prefix
    # keeps it alongside other run metadata like _health_report.json).
    json_path = run_dirs[0] / "_run_diff_report.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    sys.stdout.write(render_run_diff_text(report))
    sys.stdout.write("\n")
    sys.stderr.write(f"JSON report written to: {json_path}\n")
    return 0


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
        "--country", default=None, help="Country/jurisdiction to disambiguate the query (optional)."
    )
    discover.add_argument(
        "--disambiguation",
        default=None,
        help="Master `disambiguation` value (parent geography) to further qualify the "
             "query; added as an unquoted ranking hint, not a binding phrase (optional).",
    )
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
        type=_existing_dir,
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
        type=_existing_dir,
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
        "--master-csv", required=True, type=_existing_file,
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
        "--discovery-languages", default="en",
        help=(
            "Comma-separated ISO 639-1 codes used in Stage 1 query construction. "
            "Also recorded verbatim into per-row institution_search_languages — "
            "not independently settable, so the two can never drift apart."
        ),
    )
    presweep.add_argument(
        "--discovery-results-per-query", type=int, default=10,
        help=(
            "Serper 'num'. Default 10: num truncates and costs a flat 1 credit "
            "either way, so 5 paid for ten results and discarded half. No "
            "measured yield effect. Pass 5 to reproduce a pre-2026-08-01 run."
        ),
    )
    presweep.add_argument(
        "--discovery-mode", choices=("legacy", "chain"), default="chain",
        help=(
            "Stage 1a/1b query strategy. 'chain' (default since 2026-08-01): "
            "leg 1 '<name> <country> <disambiguation> official website' in "
            "Stage 1a and leg 2 'site:<domain> AI' in Stage 1b, 1.84 measured "
            "credits/institution and 64.5%% of institutions with an own-domain "
            "relevant hit. 'legacy': the eight-term four-slot GenAI roster in "
            "both stages, 8.52 measured credits/institution and 20.0%%. See "
            "agent-workspace/2026-08-01-discovery-chain-validation.md."
        ),
    )
    presweep.add_argument(
        "--discovery-evidence-term", default=DEFAULT_EVIDENCE_TERM,
        help=(
            "Leg 2's evidence token (--discovery-mode chain only). One bare "
            "unquoted term by measurement: extra English terms add 0 pp once "
            "site-bound and OR-chains score 4/24 against 16/24. Intended for "
            "the multilingual subproject's native-language legs."
        ),
    )
    presweep.add_argument(
        "--discovery-domain-quote-name", action="store_true",
        help=(
            "Leg 1 only (--discovery-mode chain): bind the institution name as "
            "a Google exact phrase instead of an unquoted hint. Off by default "
            "— the findings identify the quoted name as the primary failure of "
            "the four-slot format, though that evidence was gathered where a "
            "quoted name and a quoted GenAI term both had to match, so it does "
            "not transfer to leg 1 automatically. Provided to A/B the question."
        ),
    )
    presweep.add_argument(
        "--serper-autocorrect", choices=("omit", "off"), default="off",
        help=(
            "Serper's autocorrect parameter. 'off' (default since 2026-08-01) "
            "sends autocorrect=false, so the query recorded in the artifact is "
            "the query Google answered. 'omit' sends no key at all, "
            "reproducing the historical request byte-for-byte — Serper then "
            "defaults it true and Google may silently respell institution "
            "names. Provenance, not recall."
        ),
    )
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
            "filter_eligibility",
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
    presweep.add_argument(
        "--filter-mode",
        choices=["off", "shadow", "enforce"],
        default="shadow",
        help=(
            "Stage 1c eligibility pre-filter mode. 'shadow' (default) writes the "
            "would-drop artifact but drops nothing; 'enforce' sends Stage 3 only "
            "the URLs that pass; 'off' bypasses the filter entirely. Enabling "
            "'enforce' is a PI decision made on measured shadow recall."
        ),
    )
    presweep.add_argument("--poll-interval", type=int, default=60)
    presweep.add_argument(
        "--max-wait-per-stage", type=int, default=25 * 60 * 60,
        help="Max seconds to wait per Batch API stage (default: 25h ~ SLA + jitter).",
    )
    presweep.add_argument("--model", default=DEFAULT_MODEL)
    presweep.add_argument(
        "--max-workers", type=int, default=1,
        help=(
            "Worker count for the deterministic, non-LLM stages (1a discovery, "
            "1b site-restricted discovery, 4 scrape) — a shared "
            "ThreadPoolExecutor size across all three. Default 1 (sequential, "
            "matching pre-concurrency behavior). Stages 2/3/5/6 (OpenAI Batch "
            "API) are unaffected by this flag."
        ),
    )
    presweep.add_argument(
        "--preflight", action="store_true",
        help=(
            "Run no-submit pre-flight checks (keys, planned sample, Stage-5 "
            "chunk/size projection, cost preview) and exit. No state writes, no "
            "production submits. Exits non-zero if a required key is missing."
        ),
    )
    presweep.add_argument(
        "--verify-model", action="store_true",
        help="With --preflight: also run a live 1-job verify-model round-trip "
             "(submits a batch; off by default).",
    )
    presweep.add_argument(
        "--cost-ceiling", type=float, default=None,
        help="With --preflight: report whether the estimated OpenAI Batch cost "
             "exceeds this USD figure (informational; no abort wired — D7).",
    )
    presweep.add_argument(
        "--assume-pages-per-institution", type=int, default=12,
        help="Preflight assumption for the Stage-5 job/chunk projection (default: 12).",
    )
    presweep.add_argument(
        "--assume-page-chars", type=int, default=8000,
        help="Preflight assumption: extracted chars per page, capped at the "
             "text cap (default: 8000).",
    )
    presweep.add_argument(
        "--assume-output-tokens-per-job", type=int, default=600,
        help="Preflight assumption for the cost estimate (default: 600).",
    )
    presweep.set_defaults(func=_cmd_presweep)

    presweep_report = sub.add_parser(
        "presweep-report",
        help="Stage-by-stage funnel health report for a finished presweep run.",
    )
    presweep_report.add_argument(
        "--run-dir",
        required=True,
        type=_existing_dir,
        help="Path to runs/<run_id>/ directory produced by `g3o presweep --execute`.",
    )
    presweep_report.add_argument(
        "--json",
        action="store_true",
        help="Print JSON to stdout instead of the human-readable text summary.",
    )
    presweep_report.add_argument(
        "--thresholds",
        default=None,
        help=(
            "Path to a JSON file with PI-tunable threshold overrides.  "
            "Partial overrides are accepted; unspecified fields use defaults.  "
            "All threshold defaults are documented in g3o.report.HealthThresholds."
        ),
    )
    presweep_report.add_argument(
        "--language",
        default=None,
        help=(
            "Restrict Stages 1a/1b/3/4/5 to URLs discovered by a query tagged "
            "with this ISO 639-1 code (e.g. 'en'). Stage 2 and Stage 6's "
            "has_genai_activity remain pooled across languages; see "
            "language_caveats in the output."
        ),
    )
    presweep_report.add_argument(
        "--language-breakdown",
        action="store_true",
        help=(
            "Print a compact per-language comparison table (one "
            "compute_health_report call per detected language) instead of a "
            "single report. Overrides --language and --json."
        ),
    )
    presweep_report.set_defaults(func=_cmd_presweep_report)

    run_diff = sub.add_parser(
        "run-diff",
        help="Cross-run determinism report over 2+ run dirs (same seed, different run-ids).",
    )
    run_diff.add_argument(
        "run_dirs",
        nargs="+",
        type=_existing_dir,
        metavar="RUN_DIR",
        help=(
            "Two or more runs/<run_id>/ directories to compare. The first is "
            "the baseline for per-institution divergence deltas. The JSON "
            "report is written to the first run dir as _run_diff_report.json."
        ),
    )
    run_diff.set_defaults(func=_cmd_run_diff)

    verify = sub.add_parser(
        "verify-model",
        help="One-job Batch API submit to confirm the model id (Q4).",
    )
    verify.add_argument("--model", default=DEFAULT_MODEL)
    verify.add_argument("--poll-interval", type=int, default=30)
    verify.add_argument("--max-wait", type=int, default=1800)
    verify.set_defaults(func=_cmd_verify_model)

    return parser


def _force_utf8_stdio() -> None:
    """Make stdout/stderr UTF-8 so non-ASCII output cannot kill the process.

    Most subcommands serialise JSON with ``ensure_ascii=False``, so one
    non-Latin institution name — Chinese, Arabic, Cyrillic — raises
    ``UnicodeEncodeError`` on a Windows console running the cp1252 code page.
    The work had already succeeded at that point; only the write died. This is
    what ``PYTHONIOENCODING=utf-8`` was doing as a manual workaround, applied
    automatically so the workaround stops being load-bearing.

    Streams that cannot be reconfigured — pytest's capture objects, or a
    caller that replaced ``sys.stdout`` with its own file-like — are left
    alone rather than being replaced under the caller's feet.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, OSError):
            # io.UnsupportedOperation subclasses both ValueError and OSError.
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
