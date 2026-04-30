"""G3O command-line interface.

Subcommands:
  discover  — run institution-driven Serper queries and print results.
  scrape    — fetch a single URL and print the extracted text.
  extract   — (Push #2) LLM extraction over scraped sources.
  validate  — (Push #2) cross-source merge into the final database.

Push #1 implements `discover` and `scrape`; `extract` and `validate` raise
NotImplementedError pointing at the modules that still need to be built.
"""

from __future__ import annotations

import argparse
import json
import sys

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
    result = scrape_url(args.url, force_refresh=args.force_refresh)
    if args.text_only:
        sys.stdout.write(result.get("text", ""))
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0 if result.get("success") else 1


def _cmd_extract(_args: argparse.Namespace) -> int:
    raise NotImplementedError(
        "Extract layer lands in Push #2. See g3o/extract/README.md for the "
        "interface and g3o/extract/prompts/output_contract.md for the schema."
    )


def _cmd_validate(_args: argparse.Namespace) -> int:
    raise NotImplementedError(
        "Validate layer lands in Push #2. See g3o/validate/README.md."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="g3o",
        description="G3O production pipeline: discover, scrape, extract, validate.",
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
        "--text-only", action="store_true", help="Print only the extracted text."
    )
    scrape.set_defaults(func=_cmd_scrape)

    extract = sub.add_parser("extract", help="(Push #2) LLM extraction.")
    extract.set_defaults(func=_cmd_extract)

    validate = sub.add_parser("validate", help="(Push #2) Cross-source merge.")
    validate.set_defaults(func=_cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
