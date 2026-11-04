"""T-003 80% word-presence rule (RC-D-014 S1, P1). Offline, standard library only.

Rule (Simone, 2026-11-04): a quote matches its source when at least 80% of its
original-language words are present in the source text; text may only be removed
for conciseness or reformulated for clarity.

This script measures presence only (R-042): the share of the quote's tokens that
occur anywhere in the page's tokens. It does not check order or contiguity, so
removal and light rewording are tolerated, as the rule intends.

Counting unit. Space-delimited scripts use words. For CJK and Thai, which do not
delimit words with spaces, the unit is open (RC-D-014 open item 1). The script
reports both `word` (runs of letters and digits, which for CJK/Thai are often
whole clauses) and `char` (single letters/digits), with `rule_80_word` and
`rule_80_char`. `rule_80` uses `word` for space-delimited scripts; for CJK/Thai
it is left blank unless `--nonspaced-unit` is given. A dictionary tokenizer
variant is not computed (it would need a new dependency).

Evidence for that choice (2026-11-04, 331 recovered candidates; negative control =
each quote scored against a random other page of the same script, seed 20261104):
right page >=80% word/char: Latin 260/262 vs 262/262, CJK 62/63 vs 63/63, Thai 6/6
vs 6/6; wrong page >=80% word/char: Latin 11/262 vs 259/262, CJK 2/63 vs 11/63,
Thai 0/6 vs 6/6. Character presence barely separates right from wrong pages.

Inputs: the T-003 recovery files CANDIDATES.jsonl and SOURCE-PAGES.jsonl.
Output: a CSV with one row per candidate. The calibration label itself (jev 4+
or rule_80) is combined later, after the paid jev scoring run.

Usage:
    python word_presence.py --recovery-dir <dir> --out <file.csv> [--threshold 0.8]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path

THRESHOLD = 0.80
NON_SPACED_SCRIPTS = frozenset({"cjk", "thai"})
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


def normalize(text: str) -> str:
    """NFKC and casefold, so width and case variants count as the same token."""
    return unicodedata.normalize("NFKC", text).casefold()


def word_tokens(text: str) -> list[str]:
    return _WORD.findall(normalize(text))


def char_tokens(text: str) -> list[str]:
    return [c for c in normalize(text) if c.isalnum()]


def presence(quote_tokens: list[str], page_tokens: Iterable[str]) -> float | None:
    """Share of quote tokens (with repetition) that occur in the page. None if the quote has no tokens."""
    if not quote_tokens:
        return None
    page = set(page_tokens)
    return sum(t in page for t in quote_tokens) / len(quote_tokens)


def primary_unit(script: str, nonspaced_unit: str | None = None) -> str | None:
    return nonspaced_unit if script.lower() in NON_SPACED_SCRIPTS else "word"


def score(quote: str, page_text: str, script: str, threshold: float = THRESHOLD,
          nonspaced_unit: str | None = None) -> dict:
    qw, qc = word_tokens(quote), char_tokens(quote)
    pw = word_tokens(page_text)
    pc = char_tokens(page_text)
    p_word, p_char = presence(qw, pw), presence(qc, pc)
    unit = primary_unit(script, nonspaced_unit)
    primary = {"word": p_word, "char": p_char}.get(unit)
    return {
        "quote_words": len(qw),
        "quote_chars": len(qc),
        "presence_word": None if p_word is None else round(p_word, 4),
        "presence_char": None if p_char is None else round(p_char, 4),
        "primary_unit": unit or "",
        "rule_80_word": None if p_word is None else p_word >= threshold,
        "rule_80_char": None if p_char is None else p_char >= threshold,
        "rule_80": None if primary is None else primary >= threshold,
    }


def _page_text(page_row: dict) -> str:
    rec = page_row["source_record"]
    if isinstance(rec, str):
        rec = json.loads(rec)
    return rec.get("text") or ""


def run(recovery_dir: Path, out: Path, threshold: float, nonspaced_unit: str | None = None) -> dict:
    pages = {}
    with open(recovery_dir / "SOURCE-PAGES.jsonl", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            pages[row["page_id"]] = row
    n = missing = 0
    by_script: dict[str, list[int]] = {}
    fields = ["candidate_id", "page_id", "script", "text_surface", "quote_words", "quote_chars",
              "presence_word", "presence_char", "rule_80_word", "rule_80_char", "primary_unit", "rule_80",
              "threshold"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(recovery_dir / "CANDIDATES.jsonl", encoding="utf-8") as f, \
            open(out, "w", encoding="utf-8", newline="") as g:
        w = csv.DictWriter(g, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        for line in f:
            c = json.loads(line)
            q = c["saved_quote_record"]
            if isinstance(q, str):
                q = json.loads(q)
            page = pages.get(q["page_id"])
            if page is None:
                missing += 1
                continue
            s = score(q["quote"], _page_text(page), c["script"], threshold, nonspaced_unit)
            w.writerow({"candidate_id": c["candidate_id"], "page_id": q["page_id"], "script": c["script"],
                        "text_surface": c["text_surface"], "threshold": threshold, **s})
            n += 1
            tally = by_script.setdefault(c["script"], [0, 0, 0, 0])
            tally[0] += 1
            tally[1] += s["rule_80"] is True
            tally[2] += s["rule_80"] is None
            tally[3] += s["rule_80_word"] is True
    return {"candidates_scored": n, "missing_page": missing, "threshold": threshold,
            "nonspaced_unit": nonspaced_unit,
            "by_script": {k: {"n": v[0], "rule_80_true": v[1], "rule_80_blank": v[2], "rule_80_word_true": v[3]}
                          for k, v in sorted(by_script.items())}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--recovery-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--nonspaced-unit", choices=["word", "char"], default=None,
                    help="counting unit for CJK/Thai (open PI choice, RC-D-014); omitted = rule_80 blank")
    a = ap.parse_args(argv)
    summary = run(a.recovery_dir, a.out, a.threshold, a.nonspaced_unit)
    json.dump(summary, sys.stdout, indent=1)
    print()
    return 0 if summary["missing_page"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
