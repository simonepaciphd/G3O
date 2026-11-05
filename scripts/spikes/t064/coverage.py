"""T-064 coverage scan: fiscal-year labels and out-of-scope calendar years on stored page texts. Free, local, read-only.

Runs `g3o.extract.years` over every stored page text of RS-008 and RS-009 (located exactly as the F4 readability
spike does: RS-008 from --rs008-dir / G3O_RS008_DIR, RS-009 under the Drive root from --drive / G3O_DRIVE_ROOT)
and reports:
  - per fiscal label kind (fiscal_one, fiscal_two; English and table A markers): labels found, pages, unique texts, and how often a
    label contributes a year the plain literal rule finds nowhere on that page;
  - unmarked year ranges (no fiscal marker; module forms range_lower/range_upper, both four-digit ends, PI 2026-11-05): counted by shape;
  - years written in other calendars or non-ASCII digits, and non-English fiscal markers: counted, not converted
    (RC-D-017 9a "fiscal-year labels only"; the counting patterns here are heuristics for sizing, not rules).
Counts run over unique texts (sha256 of `text`); page totals include duplicates. Examples (10 per form, unique
texts) go to the Drive output only, never to the repo.

Outputs (in --out, default <drive>/agent-workspace/2026-10-27-reclass-plan/spikes):
  SPIKE-T064.md, SPIKE-T064-candidates.csv (every fiscal label on every page with its span), SPIKE-T064-counts.json

Usage:
    python scripts/spikes/t064/coverage.py [--drive <root>] [--rs008-dir <runs dir>] [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from g3o.extract import years as Y  # noqa: E402

_spec = importlib.util.spec_from_file_location("f4_readability", REPO / "scripts/spikes/f4/readability.py")
readability = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(readability)  # type: ignore[union-attr]

REL_OUT = "agent-workspace/2026-10-27-reclass-plan/spikes"
SOURCES = ("RS-008", "RS-009")
N_EXAMPLES = 10
CTX = 60
FISCAL_KINDS = (Y.FISCAL_ONE, Y.FISCAL_TWO)


def _digits(s: str) -> int | None:
    try:
        return int("".join(str(int(ch)) for ch in s))  # int() of one Unicode decimal digit
    except ValueError:
        return None


# Out-of-scope calendars and digit systems (sizing heuristics only).
OTHER = {
    "buddhist_era_marked": re.compile(r"(?:พ\.\s?ศ\.|\bB\.\s?E\.|\bBE)\s*(?:25[5-7][0-9]|๒๕[๕-๗][๐-๙])"),
    "roc_minguo": re.compile(r"民[國国]\s*(?:[0-9０-９]{2,3}|[一二三四五六七八九十百零〇]+)\s*年"),
    "japanese_era": re.compile(r"(?:令和|平成)\s*(?:元|[0-9０-９]{1,2})\s*年"),
    "japanese_era_abbrev_R_H": re.compile(r"(?<![A-Za-z0-9])[RH][0-9]{1,2}(?:\.|年)(?=[0-9]|\s|年|$)"),
    "hijri_marked": re.compile(r"(?<![0-9])1[34][0-9]{2}\s*(?:هـ|AH\b)|\bA\.?H\.?\s*1[34][0-9]{2}|[١][٣٤][٠-٩]{2}\s*هـ?"),
    "solar_hijri_marked": re.compile(r"(?:1[34][0-9]{2}|[۱][۳۴][۰-۹]{2})\s*(?:هجری\s*شمسی|ه\.\s*ش|شمسی)"),
    "persian_digit_year_1394_1409": re.compile(r"(?<![۰-۹])۱(?:۳۹[۴-۹]|۴۰[۰-۹])(?![۰-۹])"),
}
NON_ASCII_GREG = re.compile(r"(?<!\d)(\d{4})(?!\d)")  # Unicode \d on purpose; ASCII matches filtered out below

NON_EN_FISCAL = {
    "es_ano_ejercicio_fiscal": r"\b(?:año|ejercicio)\s+(?:fiscal|presupuestario)\b",
    "fr_exercice_annee_fiscale": r"\bexercice\s+(?:budgétaire|financier|fiscal)\b|\bannée\s+(?:fiscale|budgétaire)\b",
    "de_haushalts_geschaefts_jahr": r"\b(?:Haushalts|Geschäfts|Rechnungs|Wirtschafts)jahr(?:es|s)?\b",
    "it_anno_fiscale_esercizio": r"\banno\s+fiscale\b|\besercizio\s+finanziario\b",
    "pt_ano_fiscal_exercicio": r"\bano\s+fiscal\b|\bexercício\s+(?:financeiro|fiscal)\b",
    "nl_boekjaar_begrotingsjaar": r"\b(?:boek|begrotings)jaar\b",
    "ja_zh_nendo_suffix": r"[0-9０-９]{2,4}\s*年度",
    "zh_cainian_kuaiji": r"财年|財年|会计年度|會計年度|財政年度|财政年度",
    "ko_hoegye_yeondo": r"회계\s*연도",
    "th_pi_ngop_praman": r"ปีงบประมาณ",
}
NON_EN_FISCAL = {k: re.compile(v, re.IGNORECASE) for k, v in NON_EN_FISCAL.items()}
_NUM_NEAR = re.compile(r"[0-9０-９٠-٩۰-۹๐-๙]{2,4}")

# Unmarked two-year ranges (first year 2014-2030), outside any fiscal label: counted, no candidates.
UNMARKED = re.compile(r"(?<![0-9])(20[1-3][0-9])[  ]?[-/‐-―][  ]?([0-9]{4}|[0-9]{2})(?![0-9])")
LETTER_ADJ_LITERAL = re.compile(r"(?<=[A-Za-z])(20(?:1[5-9]|2[0-9]|30))(?![0-9])")


def snippet(text: str, start: int, end: int) -> str:
    a, b = max(0, start - CTX), min(len(text), end + CTX)
    s = text[a:start] + "[[" + text[start:end] + "]]" + text[end:b]
    return s.replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def analyse(text: str) -> dict:
    """Per-text tallies plus the fiscal labels (for the CSV)."""
    literal = {int(m.group(1)) for m in Y._LITERAL.finditer(Y.normalize_digits(text)) if Y.in_range(int(m.group(1)))}
    labels = Y.fiscal_labels(text)
    res: dict = {"labels": [], "kind": Counter(), "adds": Counter(), "adds_any": False, "other": Counter(),
                 "non_en": Counter(), "unmarked": Counter(), "letter_adj": 0, "examples": defaultdict(list)}
    spans = [(f.start, f.end) for f in labels]
    for f in labels:
        kept = sorted({y for y, _ in f.sources()})
        dropped = [y for y in f.years if y not in kept]
        new = [y for y in kept if y not in literal]
        res["kind"][f.kind] += 1
        if not kept:
            res["kind"][f.kind + "_all_out_of_range"] += 1
        if new:
            res["adds"][f.kind] += 1
            res["adds_any"] = True
        res["labels"].append((f, kept, dropped, new))
    for name, rx in OTHER.items():
        ms = list(rx.finditer(text))
        res["other"][name] = len(ms)
        if ms:
            res["examples"]["other_" + name].append(snippet(text, ms[0].start(), ms[0].end()))
    for m in NON_ASCII_GREG.finditer(text):
        s = m.group(1)
        if s.isascii():
            continue
        v = _digits(s)
        if v is not None and Y.in_range(v):
            res["other"]["gregorian_non_ascii_digits_2015_2030"] += 1
    for name, rx in NON_EN_FISCAL.items():
        for m in rx.finditer(text):
            near = name == "ja_zh_nendo_suffix" or _NUM_NEAR.search(text, m.end(), m.end() + 20) \
                or _NUM_NEAR.search(text, max(0, m.start() - 12), m.start())
            if near:
                res["non_en"][name] += 1
                if len(res["examples"]["nonen_" + name]) < 1:
                    res["examples"]["nonen_" + name].append(snippet(text, m.start(), m.end()))
    for m in UNMARKED.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        y1 = int(m.group(1))
        y2 = Y._full_year(m.group(2), base=y1)
        if y2 == y1 + 1:
            key = "consecutive_two_digit" if len(m.group(2)) == 2 else "consecutive_four_digit"
        elif y1 < y2 <= y1 + 15:
            key = "nonconsecutive_two_digit" if len(m.group(2)) == 2 else "nonconsecutive_four_digit"
        else:
            continue  # dates, codes, phone fragments etc.
        res["unmarked"][key] += 1
        if len(res["examples"]["unmarked_" + key]) < 2:
            res["examples"]["unmarked_" + key].append(snippet(text, m.start(), m.end()))
    res["letter_adj"] = sum(1 for _ in LETTER_ADJ_LITERAL.finditer(text))
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive", type=Path)
    ap.add_argument("--rs008-dir", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    drive = a.drive or (Path(os.environ[readability.DRIVE_ENV]) if os.environ.get(readability.DRIVE_ENV) else None)
    if drive is None:
        print(f"set --drive or {readability.DRIVE_ENV}", file=sys.stderr)
        return 2
    rs = a.rs008_dir or (Path(os.environ[readability.RS008_ENV]) if os.environ.get(readability.RS008_ENV) else None)
    out = a.out or drive / REL_OUT
    out.mkdir(parents=True, exist_ok=True)

    tot = {s: Counter() for s in SOURCES + ("all",)}
    uniq = {s: Counter() for s in SOURCES + ("all",)}
    examples: dict[str, list[str]] = defaultdict(list)
    unmarked_examples: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, dict] = {}
    src_seen: set[tuple[str, str]] = set()
    missing: list[str] = []
    csv_path = out / "SPIKE-T064-candidates.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "page_id", "url", "text_sha256", "duplicate_of_earlier", "start", "end", "label_text",
                    "form", "years_named", "years_kept_2015_2030", "years_dropped_out_of_range",
                    "years_not_found_by_literal_rule_on_page"])
        for source, pid, rec in readability.iter_sources(drive, rs):
            if source == "__missing__":
                if pid.startswith(("RS-008", "RS-009")):
                    missing.append(pid)
                continue
            if source not in SOURCES:
                continue
            text = rec.get("text") or ""
            sha = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
            dup = sha in seen
            res = seen[sha] if dup else analyse(text)
            if not dup:
                seen[sha] = {k: v for k, v in res.items() if k not in ("examples",)}
                seen[sha]["labels"] = [(f.start, f.end, f.text, f.kind, f.years, k, d, n) for f, k, d, n in res["labels"]]
            r = seen[sha]
            for bucket in (source, "all"):
                c = tot[bucket]
                c["pages"] += 1
                for k, v in r["kind"].items():
                    c["labels_" + k] += v
                for k in {f[3] for f in r["labels"]}:
                    c["pages_with_" + k] += 1
                c["pages_with_added_year"] += int(r["adds_any"])
            # unique-text tallies (per source: first sighting within that source; "all": first overall)
            for bucket, first in ((source, (source, sha) not in src_seen), ("all", not dup)):
                if not first:
                    continue
                c = uniq[bucket]
                c["texts"] += 1
                for k, v in r["kind"].items():
                    c["labels_" + k] += v
                for k in {f[3] for f in r["labels"]}:
                    c["texts_with_" + k] += 1
                for k, v in r["adds"].items():
                    c["labels_adding_year_" + k] += v
                c["texts_with_added_year"] += int(r["adds_any"])
                for k, v in r["other"].items():
                    c["other_" + k] += v
                    c["texts_other_" + k] += int(v > 0)
                for k, v in r["non_en"].items():
                    c["nonen_" + k] += v
                    c["texts_nonen_" + k] += int(v > 0)
                for k, v in r["unmarked"].items():
                    c["unmarked_" + k] += v
                    c["texts_unmarked_" + k] += int(v > 0)
                c["literal_letter_adjacent"] += r["letter_adj"]
            src_seen.add((source, sha))
            if not dup:
                shown: set[str] = set()  # one example per form per unique text
                for f, kept, _dropped, _new in res["labels"]:
                    if len(examples[f.kind]) < N_EXAMPLES and f.kind not in shown:
                        shown.add(f.kind)
                        examples[f.kind].append(f"`{pid}` {sorted(set(kept)) or '-'} :: {snippet(text, f.start, f.end)}")
                for k, v in res["examples"].items():
                    cap = 3 if k.startswith("unmarked_") else 8
                    if len(unmarked_examples[k]) < cap:
                        unmarked_examples[k].extend(v[: cap - len(unmarked_examples[k])])
            for s0, e0, ltext, kind, named, kept, dropped, new in r["labels"]:
                w.writerow([source, pid, rec.get("url", ""), sha, int(dup), s0, e0, ltext, kind,
                            ";".join(map(str, named)), ";".join(map(str, kept)), ";".join(map(str, dropped)),
                            ";".join(map(str, new))])

    meta = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "module": "g3o/extract/years.py", "missing_sources": missing,
            "year_range": [Y.YEAR_MIN, Y.YEAR_MAX]}
    counts = {"meta": meta, "pages": {k: dict(v) for k, v in tot.items()},
              "unique_texts": {k: dict(v) for k, v in uniq.items()}}
    (out / "SPIKE-T064-counts.json").write_text(json.dumps(counts, indent=2, sort_keys=True), encoding="utf-8")
    (out / "SPIKE-T064.md").write_text(render(counts, examples, unmarked_examples), encoding="utf-8")
    print(json.dumps(counts["unique_texts"]["all"], indent=1, sort_keys=True))
    return 0


def render(counts: dict, examples: dict, unmarked_examples: dict) -> str:
    P, U = counts["pages"], counts["unique_texts"]
    cols = list(SOURCES) + ["all"]
    L = ["# SPIKE-T064 — fiscal-year labels and out-of-scope calendar years on RS-008/RS-009 page texts", "",
         f"Generated {counts['meta']['generated_utc']} by `scripts/spikes/t064/coverage.py` over `g3o/extract/years.py`. "
         "Free, local, read-only. Missing sources: " + (", ".join(counts["meta"]["missing_sources"]) or "none") + ".", "",
         "Unit: unique page texts (sha256 of stored `text`) unless a row says pages. Converted years outside "
         "2015-2030 are dropped exactly like literal ones.", "",
         "| measure | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]

    def row(label, src, key):
        L.append(f"| {label} | " + " | ".join(str(src[c].get(key, 0)) for c in cols) + " |")

    row("pages (incl. duplicates)", P, "pages")
    row("unique texts", U, "texts")
    for k in FISCAL_KINDS:
        row(f"`{k}` labels", U, "labels_" + k)
        row(f"texts with `{k}`", U, "texts_with_" + k)
        row(f"`{k}` labels adding a year the literal rule finds nowhere on the page", U, "labels_adding_year_" + k)
        row(f"`{k}` labels with every candidate year outside 2015-2030 (dropped)", U, "labels_" + k + "_all_out_of_range")
    row("texts where a fiscal label adds a year not found by the literal rule", U, "texts_with_added_year")
    row("pages where a fiscal label adds a year (incl. duplicates)", P, "pages_with_added_year")
    L += ["", "## Unmarked year ranges (no fiscal marker; module gives both four-digit ends, window lifted, PI 2026-11-05)", "",
          "| form | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
    for k in ("consecutive_two_digit", "consecutive_four_digit", "nonconsecutive_two_digit", "nonconsecutive_four_digit"):
        row(f"`{k}` occurrences", U, "unmarked_" + k)
        row(f"texts with `{k}`", U, "texts_unmarked_" + k)
    L += ["", "Counting shape for sizing: first year 2014-2030; second year after the first and at most 15 years later "
          "(the module itself uses a 1900-2099 guard, no span limit). An unmarked two-digit end is not a range end.", ""]
    for k, v in sorted(unmarked_examples.items()):
        if k.startswith("unmarked_"):
            L.append(f"- `{k}`: " + " / ".join(f"`{s}`" for s in v))
    L += ["", "## Out of scope: other calendars, non-ASCII digits (counted, not converted; heuristic patterns)", "",
          "| pattern | occurrences (all) | texts (all) | RS-008 texts | RS-009 texts |", "|---|---|---|---|---|"]
    for k in sorted({x[len("other_"):] for x in U["all"] if x.startswith("other_")}):
        L.append(f"| `{k}` | {U['all'].get('other_' + k, 0)} | {U['all'].get('texts_other_' + k, 0)} | "
                 f"{U['RS-008'].get('texts_other_' + k, 0)} | {U['RS-009'].get('texts_other_' + k, 0)} |")
    L.append(f"| literal year preceded by an ASCII letter (e.g. `H2020`, `FY2025`) | "
             f"{U['all'].get('literal_letter_adjacent', 0)} | | | |")
    L += ["", "## Non-English fiscal-year markers near a number (counted, not converted; needs a lexicon ruling)", "",
          "| marker | occurrences (all) | texts (all) |", "|---|---|---|"]
    for k in sorted(NON_EN_FISCAL):
        L.append(f"| `{k}` | {U['all'].get('nonen_' + k, 0)} | {U['all'].get('texts_nonen_' + k, 0)} |")
    L += ["", "## Out-of-scope examples (first 8 unique texts per pattern; for the T-064 conversions proposal)", ""]
    for k, v in sorted(unmarked_examples.items()):
        if not k.startswith("unmarked_"):
            L.append(f"- `{k}`: " + " / ".join(f"`{s}`" for s in v))
    L += ["", "## Examples (first 10 unique texts per form, one label each; `[[...]]` is the label; list = years kept)", ""]
    for k in FISCAL_KINDS:
        L.append(f"### `{k}`")
        L += [f"{i}. {e}" for i, e in enumerate(examples.get(k, []), 1)] or ["(none found)"]
        L.append("")
    L.append("Every label on every page, with span offsets and kept/dropped years: `SPIKE-T064-candidates.csv`.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
