"""F4 readability measurement (RC-D-015 F4 c, "measure first"). Free, local, read-only, standard library only.

For every locally available stored page text that the v2.7 work uses, compute candidate readability measures and
report their distribution and the pages each candidate threshold would flag. Chooses no threshold: the PI sets it.

Measures (per page, on the stored `text`):
  replacement_share  U+FFFD replacement characters / all characters
  nonprint_share     non-printable characters / all characters: Unicode Cc other than tab, LF, CR, FF, VT, plus
                     Cn (unassigned), Co (private use) and Cs (surrogates). Cf (soft hyphen, ZWJ ...) is not counted.
  letter_share       letters or combining marks in any script (Unicode L*, M*) / non-whitespace characters
  signatures         binary-content markers: pdf_header (%PDF-), pdf_objects (>= 3 `obj`/`endobj`/`stream`
                     tokens), zip (PK\\x03\\x04), null (U+0000), image (PNG, JFIF/Exif, GIF8 magic)
Empty texts get no shares and are counted separately.

Stored bytes: the stored page record (RenderedPage: url, text, title, content_type, fetch_metadata, and since T-014
chrome_text/links/email_links) has no field for the fetched bytes. The script records every key seen per source and
reports `has_bytes_field` per page (any of BYTE_FIELDS present), so the claim is measured, not assumed.

Sources (each optional; a missing one is reported, not fatal):
  RS-008      the scrape tar and run folders under --rs008-dir (env G3O_RS008_DIR)
  RS-009      agent-workspace/2026-09-27-jev-compare/pulled/{stored-subset,new-run-*}.tar under the Drive root
  T002-T003   agent-workspace/2026-11-02-safe-review/t003-recovery/SOURCE-PAGES.jsonl
  T040        agent-workspace/2026-11-04-v27-orch/lane-d/REAL-PAGES.jsonl
Drive root from --drive or G3O_DRIVE_ROOT (exit 2 if neither). Page samples go to the Drive output only.

Usage:
    python readability.py [--drive <root>] [--rs008-dir <runs dir>] [--out <dir>]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import sys
import tarfile
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

DRIVE_ENV = "G3O_DRIVE_ROOT"
RS008_ENV = "G3O_RS008_DIR"
REL_OUT = "agent-workspace/2026-11-05-v27-orch/lane-a"
REL_RS009 = "agent-workspace/2026-09-27-jev-compare/pulled"
RS009_TARS = ("stored-subset.tar", "new-run-r20260928T141425Z-7d56.tar")
REL_T003 = "agent-workspace/2026-11-02-safe-review/t003-recovery/SOURCE-PAGES.jsonl"
REL_T040 = "agent-workspace/2026-11-04-v27-orch/lane-d/REAL-PAGES.jsonl"

BYTE_FIELDS = frozenset({"raw", "bytes", "raw_bytes", "content", "body", "pdf_bytes", "data_b64", "content_b64"})
OK_CONTROLS = frozenset("\t\n\r\x0b\x0c")
NONPRINT_CATS = frozenset({"Cn", "Co", "Cs"})
LETTER_SHARE_CUTS = (0.50, 0.30, 0.10)       # flag when letter_share < cut (candidates, not choices)
REPLACEMENT_CUTS = (0.01, 0.05, 0.10)        # flag when replacement_share > cut
NONPRINT_CUTS = (0.01, 0.05, 0.10)           # flag when nonprint_share > cut
PCTS = (1, 5, 10, 25, 50, 75, 90, 95, 99)
SAMPLE_CHARS = 120
MD_LIST_MAX = 40

_PDF_OBJ = re.compile(r"\b(?:\d+ \d+ obj|endobj|endstream|stream)\b")
_IMAGE = ("\x89PNG", "JFIF", "Exif\x00", "GIF87a", "GIF89a")


# ---- measures ---------------------------------------------------------------------------------------

def signatures(text: str) -> list[str]:
    head = text[:1024]
    out = []
    if "%PDF-" in head:
        out.append("pdf_header")
    if len(_PDF_OBJ.findall(text[:200_000])) >= 3:
        out.append("pdf_objects")
    if "PK\x03\x04" in head:
        out.append("zip")
    if "\x00" in text:
        out.append("null")
    if any(m in head for m in _IMAGE):
        out.append("image")
    return out


def measures(text: str) -> dict:
    n = len(text)
    if n == 0:
        return {"n_chars": 0, "replacement_share": None, "nonprint_share": None, "letter_share": None,
                "signatures": ""}
    repl = nonprint = letters = nonspace = 0
    for ch in text:
        if ch == "�":
            repl += 1
        cat = unicodedata.category(ch)
        if (cat == "Cc" and ch not in OK_CONTROLS) or cat in NONPRINT_CATS:
            nonprint += 1
        if not ch.isspace():
            nonspace += 1
            if cat[0] in "LM":
                letters += 1
    return {"n_chars": n, "replacement_share": round(repl / n, 5), "nonprint_share": round(nonprint / n, 5),
            "letter_share": None if nonspace == 0 else round(letters / nonspace, 5),
            "signatures": ";".join(signatures(text))}


def flags(m: dict) -> list[str]:
    """Candidate-threshold flags for one page (names encode the cut)."""
    out = []
    if m["n_chars"] == 0:
        return ["empty"]
    ls = m["letter_share"]
    for c in LETTER_SHARE_CUTS:
        if ls is None or ls < c:
            out.append(f"letters<{int(c * 100)}%")
    for c in REPLACEMENT_CUTS:
        if m["replacement_share"] > c:
            out.append(f"replacement>{int(c * 100)}%")
    for c in NONPRINT_CUTS:
        if m["nonprint_share"] > c:
            out.append(f"nonprint>{int(c * 100)}%")
    if m["signatures"]:
        out.append("binary_signature")
    return out


ALL_FLAGS = ([f"letters<{int(c * 100)}%" for c in LETTER_SHARE_CUTS]
             + [f"replacement>{int(c * 100)}%" for c in REPLACEMENT_CUTS]
             + [f"nonprint>{int(c * 100)}%" for c in NONPRINT_CUTS] + ["binary_signature", "empty"])


def sample(text: str, k: int = SAMPLE_CHARS) -> str:
    """First k characters with controls escaped, so the sample is one printable line."""
    s = text[:k]
    return "".join(ch if (ch.isprintable() and ch not in "|") else f"\\x{ord(ch):02x}" if ord(ch) < 256
                   else f"\\u{ord(ch):04x}" for ch in s)


def nearest_rank(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


# ---- sources ----------------------------------------------------------------------------------------

def _rec(x):
    return json.loads(x) if isinstance(x, str) else x


def _tar_pages(path: Path, corpus: str) -> Iterator[tuple[str, dict]]:
    with tarfile.open(path) as t:
        for m in t:
            if not (m.isfile() and "/scrape/" in m.name and m.name.endswith(".json.gz")):
                continue
            rec = json.loads(gzip.decompress(t.extractfile(m).read()))
            yield _member_id(corpus, path.stem, m.name), rec


def _member_id(corpus: str, container: str, name: str) -> str:
    """'<corpus>:<run>:<INST>:<hash>' (the T-003 page_id form) from a run-relative member path."""
    parts = name.replace("\\", "/").split("/")
    run = next((p for p in parts if p.startswith("r20") or p.startswith("2026")), container.replace("-scrape", ""))
    inst = next((p for p in parts if p.startswith("INST-")), "?")
    return f"{corpus}:{run}:{inst}:{parts[-1].removesuffix('.json.gz')}"


def iter_sources(drive: Path, rs008: Path | None) -> Iterator[tuple[str, str, dict]]:
    """Yield (source, page_id, record). Missing sources are yielded as ('__missing__', name, {})."""
    if rs008 is None or not rs008.is_dir():
        yield "__missing__", "RS-008 (set --rs008-dir or G3O_RS008_DIR)", {}
    else:
        for tar in sorted(rs008.glob("*-scrape.tar")):
            for pid, rec in _tar_pages(tar, "RS-008"):
                yield "RS-008", pid, rec
        for f in sorted(rs008.glob("*/institutions/*/*/scrape/*.json.gz")):
            rel = f.relative_to(rs008).as_posix()
            yield "RS-008", _member_id("RS-008", "", rel), json.loads(gzip.decompress(f.read_bytes()))
    for name in RS009_TARS:
        p = drive / REL_RS009 / name
        if not p.is_file():
            yield "__missing__", f"RS-009 {name}", {}
            continue
        for pid, rec in _tar_pages(p, "RS-009"):
            yield "RS-009", pid, rec
    p = drive / REL_T003
    if p.is_file():
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            yield "T002-T003", r["page_id"], _rec(r["source_record"])
    else:
        yield "__missing__", "T002-T003 SOURCE-PAGES.jsonl", {}
    p = drive / REL_T040
    if p.is_file():
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            yield "T040", r.get("fixture_id") or r.get("url", "?"), r
    else:
        yield "__missing__", "T040 REAL-PAGES.jsonl", {}


# ---- run --------------------------------------------------------------------------------------------

ROW_FIELDS = ["source", "page_id", "url", "content_type", "text_sha256", "duplicate_of_earlier", "n_chars",
              "replacement_share", "nonprint_share", "letter_share", "signatures", "has_bytes_field", "flags",
              "sample_120"]


def scan(records) -> tuple[list[dict], dict]:
    rows, keys, missing = [], defaultdict(Counter), []
    seen: set[str] = set()
    for source, pid, rec in records:
        if source == "__missing__":
            missing.append(pid)
            continue
        text = rec.get("text") or ""
        keys[source].update(rec.keys())
        m = measures(text)
        fl = flags(m)
        h = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
        ct = rec.get("content_type") or ""
        rows.append({"source": source, "page_id": pid, "url": rec.get("url") or "", "content_type": ct,
                     "text_sha256": h, "duplicate_of_earlier": h in seen, **m,
                     "has_bytes_field": bool(BYTE_FIELDS & set(rec.keys())), "flags": ";".join(fl),
                     "sample_120": sample(text) if fl else ""})
        seen.add(h)
    return rows, {"record_keys": {s: dict(c) for s, c in keys.items()}, "missing_sources": missing}


def summarize(rows: list[dict]) -> dict:
    out = {"by_source": {}, "quantiles": {}, "flag_counts": {}, "flag_by_content_type": {}}
    groups = {"all": rows, "all_unique_text": [r for r in rows if not r["duplicate_of_earlier"]]}
    for s in sorted({r["source"] for r in rows}):
        groups[s] = [r for r in rows if r["source"] == s]
    for g, rs in groups.items():
        out["by_source"][g] = {"pages": len(rs), "empty": sum(r["n_chars"] == 0 for r in rs),
                               "content_type": dict(Counter(r["content_type"] for r in rs)),
                               "has_bytes_field": sum(r["has_bytes_field"] for r in rs)}
        q = {}
        for k in ("replacement_share", "nonprint_share", "letter_share", "n_chars"):
            xs = [r[k] for r in rs if r[k] is not None]
            q[k] = {f"p{p}": nearest_rank(xs, p) for p in PCTS} if xs else {}
            if xs:
                q[k].update(min=min(xs), max=max(xs), nonzero=sum(x > 0 for x in xs))
        out["quantiles"][g] = q
        out["flag_counts"][g] = {f: sum(f in r["flags"].split(";") for r in rs) for f in ALL_FLAGS}
    for f in ALL_FLAGS:
        hit = [r for r in groups["all_unique_text"] if f in r["flags"].split(";")]
        out["flag_by_content_type"][f] = dict(Counter(r["content_type"] for r in hit))
    sigs = Counter(s for r in rows for s in r["signatures"].split(";") if s)
    out["signature_counts"] = dict(sigs)
    return out


def _fmt(v):
    if v is None:
        return "n/a"
    return f"{v:.4f}" if isinstance(v, float) else str(v)


def render_md(rows: list[dict], summ: dict, meta: dict) -> str:
    L = ["# SPIKE-F4: readability of stored page text (RC-D-015 F4 c, measure first)", "",
         f"Generated {meta['generated_at']} by `scripts/spikes/f4/readability.py` (branch `orch1105/a-t003`), free, "
         "local and read-only (no SSH, no droplet, no fetch). Lane A, orchestrator session "
         "`20261104-claude-v2-b18c125048383d63` (claude-opus-5-5).", "",
         "**No threshold is chosen.** The cuts below are candidates to show what each would flag; the PI sets the "
         "readability threshold (RC-D-015 open item 4).", "",
         "## Sources", ""]
    for s, b in summ["by_source"].items():
        L.append(f"- **{s}**: {b['pages']} pages, {b['empty']} empty, content types {b['content_type']}, "
                 f"records with a bytes field: {b['has_bytes_field']}")
    L += [f"- Missing sources: {meta['missing_sources'] or 'none'}", "",
          "Record keys seen per source (to test for stored bytes):", ""]
    L += [f"- {s}: {sorted(k)}" for s, k in meta["record_keys"].items()]
    L += ["", "## Stored bytes", "",
          f"No stored record has a field for the fetched bytes (fields checked: {sorted(BYTE_FIELDS)}). The stored "
          "page record keeps extracted text only. **So 0 flagged pages have stored bytes locally**, and none of the "
          "local corpora can support the F4 c re-extraction step. Whether the droplet keeps raw bytes anywhere "
          "else (outside this record) is not checked here.", "",
          "## Measures", "",
          "- `replacement_share`: U+FFFD / characters.",
          "- `nonprint_share`: Cc (other than tab, LF, CR, VT, FF) + Cn + Co + Cs / characters.",
          "- `letter_share`: letters or combining marks in any script / non-whitespace characters.",
          "- `binary_signature`: %PDF- header, >= 3 PDF object tokens, zip magic, NUL, or image magic.", "",
          "## Distribution (nearest-rank quantiles)", ""]
    for g in ("all", "all_unique_text") + tuple(k for k in summ["quantiles"] if not k.startswith("all")):
        q = summ["quantiles"][g]
        L += [f"### {g}", "", "| measure | " + " | ".join(f"p{p}" for p in PCTS) + " | min | max | nonzero |",
              "|---|" + "---|" * (len(PCTS) + 3)]
        for k, d in q.items():
            if d:
                L.append(f"| {k} | " + " | ".join(_fmt(d[f'p{p}']) for p in PCTS) +
                         f" | {_fmt(d['min'])} | {_fmt(d['max'])} | {d['nonzero']} |")
        L.append("")
    L += ["## Pages flagged at candidate thresholds", "",
          "| flag | " + " | ".join(summ["flag_counts"]) + " |", "|---|" + "---|" * len(summ["flag_counts"])]
    for f in ALL_FLAGS:
        L.append(f"| {f} | " + " | ".join(str(summ["flag_counts"][g][f]) for g in summ["flag_counts"]) + " |")
    L += ["", "Flagged unique texts by content type:", ""]
    L += [f"- {f}: {summ['flag_by_content_type'][f]}" for f in ALL_FLAGS]
    L += ["", f"Binary signature hits (all rows): {summ['signature_counts'] or 'none'}", "",
          f"## Flagged pages (unique texts; first {MD_LIST_MAX} per flag; full list in SPIKE-F4-readability.csv)",
          ""]
    uniq = [r for r in rows if not r["duplicate_of_earlier"]]
    for f in ALL_FLAGS:
        hit = sorted((r for r in uniq if f in r["flags"].split(";")),
                     key=lambda r: (r["letter_share"] if r["letter_share"] is not None else -1))
        if not hit:
            continue
        L += [f"### {f} ({len(hit)})", "", "| page_id | type | chars | letters | repl | nonprint | sig | sample |",
              "|---|---|---|---|---|---|---|---|"]
        for r in hit[:MD_LIST_MAX]:
            L.append(f"| {r['page_id']} | {r['content_type']} | {r['n_chars']} | {_fmt(r['letter_share'])} | "
                     f"{_fmt(r['replacement_share'])} | {_fmt(r['nonprint_share'])} | {r['signatures']} | "
                     f"`{r['sample_120'].replace('`', chr(39))}` |")
        L.append("")
    L += ["## Notes", "",
          "- Duplicates: the same text can appear in several runs or sources (T002-T003 pages are a subset of "
          "RS-008/RS-009 pages); `all_unique_text` counts each text once.",
          "- A low letter share also flags legitimate number-heavy pages (tables, budgets, timetables); the "
          "samples show which flags catch binary noise and which catch tables.",
          "- The local page cache (`cache/` in the pipeline checkout) is not a named v2.7 input and was not scanned.",
          ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--drive", type=Path, default=None)
    ap.add_argument("--rs008-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    v = a.drive or os.environ.get(DRIVE_ENV)
    if not v or not (Path(v) / "agent-workspace").is_dir():
        print(f"{DRIVE_ENV} is not set or has no agent-workspace/; pass --drive.", file=sys.stderr)
        return 2
    drive = Path(v)
    rs = a.rs008_dir or (Path(os.environ[RS008_ENV]) if os.environ.get(RS008_ENV) else None)
    out = a.out or drive / REL_OUT
    out.mkdir(parents=True, exist_ok=True)
    rows, info = scan(iter_sources(drive, rs))
    summ = summarize(rows)
    meta = {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), **info}
    with open(out / "SPIKE-F4-readability.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ROW_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    (out / "SPIKE-F4-readability.json").write_text(json.dumps({"meta": meta, **summ}, indent=1), encoding="utf-8")
    (out / "SPIKE-F4-readability.md").write_text(render_md(rows, summ, meta), encoding="utf-8")
    print(json.dumps({"pages": len(rows), "missing": info["missing_sources"],
                      "flags_unique": summ["flag_counts"]["all_unique_text"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
