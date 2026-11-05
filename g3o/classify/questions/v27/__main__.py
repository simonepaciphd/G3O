"""``python -m g3o.classify.questions.v27 build|check`` (offline, no API calls)."""

from __future__ import annotations

import sys

from g3o.classify.questions.v27.build import check_sets, write_sets


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["build"]:
        for p in write_sets():
            print(f"wrote {p}")
        return 0
    if args == ["check"]:
        errors = check_sets()
        for e in errors:
            print(f"FAIL {e}")
        print("check: PASS" if not errors else f"check: {len(errors)} failure(s)")
        return 1 if errors else 0
    print("usage: python -m g3o.classify.questions.v27 build|check", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
