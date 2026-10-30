"""Command line for the codebook package.

    python -m g3o.codebook generate   # write g3o/codebook/generated/*
    python -m g3o.codebook drift      # check 5 only; exit 1 on any difference (CI)
    python -m g3o.codebook checks     # checks 1-16; exit 1 if any fails (CI)
    python -m g3o.codebook hash       # print the codebook sha256

Options: ``--codebook PATH`` (default ``codebook/codebook.yaml``),
``--previous PATH`` (previous release, for checks 2 and 12), ``--verbose``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from g3o.codebook.checks import check_05_no_drift, default_context, run_checks
from g3o.codebook.generators import generate_all
from g3o.codebook.loader import DEFAULT_CODEBOOK, REPO_ROOT, load_codebook


def _write(repo_root: Path, files) -> None:
    for f in files:
        out = repo_root / f.relpath
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(f.bytes())
        print(f"wrote {f.relpath}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m g3o.codebook")
    ap.add_argument("command", choices=["generate", "drift", "checks", "hash"])
    ap.add_argument("--codebook", default=str(DEFAULT_CODEBOOK))
    ap.add_argument("--previous", default=None)
    ap.add_argument("--repo-root", default=str(REPO_ROOT))
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    cb = load_codebook(args.codebook)
    root = Path(args.repo_root)
    if args.command == "hash":
        print(cb.sha256)
        return 0
    if args.command == "generate":
        _write(root, generate_all(cb))
        return 0

    ctx = default_context(cb, root)
    if args.previous:
        ctx.previous = load_codebook(args.previous)
    results = [check_05_no_drift(cb, ctx)] if args.command == "drift" else run_checks(cb, ctx)
    print(f"codebook release {cb.label} sha256 {cb.sha256}")
    for r in results:
        print(r.line())
        for finding in r.findings:
            print(f"    FAIL {finding}")
        if args.verbose:
            for note in r.notes:
                print(f"    note {note}")
    if args.command == "drift" and results[0].status == "fail":
        print("Regenerate with `python -m g3o.codebook generate` and commit; never edit generated files.")
    return 1 if any(r.status == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
