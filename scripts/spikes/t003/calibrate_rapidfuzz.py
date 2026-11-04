"""T-003 remainder: rapidfuzz metric/threshold calibration and the quote-length / display-cap table. Free, offline.

Labels (fixed by rulings, not chosen here): gold = jev 4+ (fidelity_argmax >= 4, v27-gates-1104 A3 a) OR the 80%
word-presence rule at 0.80 for every script (RC-D-014 S1/P1, R2 a, RC-D-016). Rows: the 331 recovered candidates
(222 unique pairs mapped back, P1 a) plus the 380 near-miss controls (A2 a). Split: RC-D-014 (20% of institutions,
script-stratified, seed 20261104; `word_presence.assign_partitions`, carried in the presence CSV).

Metrics (rapidfuzz pinned at PINNED_RAPIDFUZZ, DEC-007 a), each a 0-100 score of the quote against the stored page
text (the surface T-024 checks; the chunk score is kept as a diagnostic column):
  partial_ratio_norm    fuzz.partial_ratio on normalized text (NFKC, casefold, punctuation dropped, word runs
                        joined by one space). Best contiguous character alignment: order-sensitive and needs no
                        word segmentation, so it applies to CJK and Thai as is.
  partial_ratio_light   fuzz.partial_ratio on lightly normalized text (NFKC, casefold, whitespace collapsed,
                        punctuation kept). Shows what the punctuation step buys.
  token_set_ratio_norm  fuzz.token_set_ratio on normalized text. Order-insensitive; against a long page it is close
                        to character-weighted word presence, so it largely restates the 80% rule inside the gold.
fuzz.ratio on the whole page is not a candidate: it scores length difference, not presence.

Threshold procedure (procedural, for the error table only; the PI approves metric and threshold, Q-020 b): accept
when score >= t, t an integer 0-100. On the tuning partition, the thresholds minimizing false matches + false
rejects form the argmin set; the reported tuned threshold is its median (lower median for an even count). DP-003
(PI S2 b): a pooled threshold is tuned on all tuning rows; per-script thresholds (Latin, CJK) are tuned and shown
beside it so the PI can see where the pooled one fails on held-out. Thai: not tunable (tuning n = 1), held-out
errors flagged not estimable.

Display cap (DP-004, PI P2 b): quote-length distribution in characters and words by script, and the share of quotes
each candidate cap would truncate. No cap is proposed or chosen.

Usage:
    python calibrate_rapidfuzz.py [--drive <root>] [--out <dir>]
Paths default to folders under the Drive root (G3O_DRIVE_ROOT or --drive); with neither the script exits 2.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


an = _load("analyze_t003")
jf = _load("jev_fidelity")
wp = jf.wp

PINNED_RAPIDFUZZ = "3.14.3"   # DEC-007 a; MIT; cp312 manylinux_2_28 x86_64 wheel on PyPI (see report)

REL_SPIKES = "agent-workspace/2026-10-27-reclass-plan/spikes"
REL_RECOVERY = jf.REL_RECOVERY_DIR
REL_PRESENCE = "agent-workspace/2026-11-04-v27-orch/lane-a/T003-word-presence-thai-fix.csv"

SCRIPTS = ("latin", "cjk", "thai")
TUNABLE = ("latin", "cjk")
THRESHOLDS = tuple(range(0, 101))
SHOW_THRESHOLDS = (50, 60, 70, 75, 80, 85, 90, 95, 100)
CAPS = (100, 150, 200, 250, 300, 400, 500)
PCTS = (10, 25, 50, 75, 90, 95, 99)
THAI_FLAG = "not estimable: Thai tuning n = 1 (RC-D-014)"


# ---- normalization and metrics -----------------------------------------------------------------------

def norm_text(s: str) -> str:
    """NFKC + casefold, punctuation dropped: the word_presence word runs joined by one space."""
    return " ".join(wp.word_tokens(s))


def light_text(s: str) -> str:
    """NFKC + casefold, whitespace collapsed, punctuation kept."""
    return re.sub(r"\s+", " ", wp.normalize(s)).strip()


def metric_specs():
    from rapidfuzz import fuzz
    return {"partial_ratio_norm": (fuzz.partial_ratio, norm_text),
            "partial_ratio_light": (fuzz.partial_ratio, light_text),
            "token_set_ratio_norm": (fuzz.token_set_ratio, norm_text)}


METRICS = ("partial_ratio_norm", "partial_ratio_light", "token_set_ratio_norm")


def check_version(allow_other: bool = False) -> str:
    import rapidfuzz
    v = rapidfuzz.__version__
    if v != PINNED_RAPIDFUZZ and not allow_other:
        print(f"rapidfuzz {v} is installed; this calibration is pinned to {PINNED_RAPIDFUZZ} (DEC-007 a).",
              file=sys.stderr)
        raise SystemExit(2)
    return v


def score_all(rows: list[dict], texts: dict[str, dict]) -> None:
    """Add `<metric>` (page) and `<metric>_chunk` scores to each row. texts[row key] = {quote, page, chunk}."""
    specs = metric_specs()
    cache: dict[tuple[str, str], str] = {}

    def prep(kind: str, key: str, s: str, fn) -> str:
        k = (kind, key)
        if k not in cache:
            cache[k] = fn(s)
        return cache[k]

    for r in rows:
        t = texts[r["item_id"]]
        for name, (fn, normf) in specs.items():
            mode = name.rsplit("_", 1)[1]
            q = normf(t["quote"])
            r[name] = round(fn(q, prep(mode, "page:" + t["page_id"], t["page"], normf)), 2)
            r[name + "_chunk"] = round(fn(q, prep(mode, "chunk:" + t["chunk_id"], t["chunk"], normf)), 2)


# ---- errors and tuning ------------------------------------------------------------------------------

def gold(r: dict) -> bool:
    return an.gold(r)


def errors(rows: list[dict], metric: str, t: float, label=gold) -> dict:
    fm = fr = pos = neg = 0
    for r in rows:
        g, d = label(r), r[metric] >= t
        pos += g
        neg += not g
        fm += d and not g
        fr += (not d) and g
    return {"n": len(rows), "gold_true": pos, "gold_false": neg, "false_match": fm, "false_reject": fr,
            "errors": fm + fr}


def tune(rows: list[dict], metric: str, thresholds=THRESHOLDS) -> dict:
    """argmin set of total errors over integer thresholds; tuned = lower median of that set."""
    errs = {t: errors(rows, metric, t)["errors"] for t in thresholds}
    best = min(errs.values())
    argmin = sorted(t for t, e in errs.items() if e == best)
    return {"tuned": argmin[(len(argmin) - 1) // 2], "argmin_lo": argmin[0], "argmin_hi": argmin[-1],
            "argmin_count": len(argmin), "tuning_errors": best, "n": len(rows)}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)


def rate_block(e: dict) -> dict:
    return {**e,
            "fm_rate": None if not e["gold_false"] else round(e["false_match"] / e["gold_false"], 3),
            "fm_ci95": wilson(e["false_match"], e["gold_false"]),
            "fr_rate": None if not e["gold_true"] else round(e["false_reject"] / e["gold_true"], 3),
            "fr_ci95": wilson(e["false_reject"], e["gold_true"])}


def by_kind(rows: list[dict], metric: str, t: float) -> dict:
    return {k: errors([r for r in rows if r["row"] == k], metric, t)
            for k in ("candidate", "control_onpage", "control_offpage")}


def calibrate(rows: list[dict]) -> dict:
    tun = [r for r in rows if r["partition"] == "tuning"]
    hold = [r for r in rows if r["partition"] == "holdout"]
    out = {}
    for m in METRICS:
        pooled = tune(tun, m)
        per = {s: tune([r for r in tun if r["script"] == s], m) for s in TUNABLE}
        res = {"pooled": pooled, "per_script": per, "holdout": {}, "sweep": {}, "jev_only": {},
               "scrambled_accepted": {},
               # circularity check: how often the metric's decision equals the 80% rule inside the gold
               "agrees_with_rule_80": round(sum((r[m] >= pooled["tuned"]) == (r["presence_word"] >= 0.8 - 1e-9)
                                                for r in rows) / len(rows), 3) if rows else None}
        for s in SCRIPTS:
            hs = [r for r in hold if r["script"] == s]
            blk = {"pooled": {**rate_block(errors(hs, m, pooled["tuned"])), "threshold": pooled["tuned"],
                              "by_kind": by_kind(hs, m, pooled["tuned"])}}
            if s in TUNABLE:
                t = per[s]["tuned"]
                blk["per_script"] = {**rate_block(errors(hs, m, t)), "threshold": t, "by_kind": by_kind(hs, m, t)}
            else:
                blk["flag"] = THAI_FLAG
            res["holdout"][s] = blk
            res["sweep"][s] = {p: [{"t": t, **errors([r for r in rows if r["partition"] == p and r["script"] == s],
                                                     m, t)} for t in SHOW_THRESHOLDS]
                               for p in ("tuning", "holdout")}
            jt = per[s]["tuned"] if s in TUNABLE else pooled["tuned"]
            res["jev_only"][s] = {"threshold": jt,
                                  **rate_block(errors(hs, m, jt, label=lambda r: r["jev_4plus"]))}
            on = [r for r in hs if r["row"] == "control_onpage"]
            res["scrambled_accepted"][s] = {"n": len(on), "threshold": jt,
                                            "accepted_jev_below_4": sum(r[m] >= jt and not r["jev_4plus"]
                                                                        for r in on)}
        out[m] = res
    return out


def page_vs_chunk(rows: list[dict]) -> dict:
    return {m: sum(abs(r[m] - r[m + "_chunk"]) > 1e-9 for r in rows) for m in METRICS}


# ---- quote lengths and caps -------------------------------------------------------------------------

def nearest_rank(xs: list[int], p: float) -> int:
    s = sorted(xs)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def length_table(quotes: list[tuple[str, str]], caps=CAPS) -> dict:
    """quotes = [(script, text)]. Chars = Unicode code points of the stripped quote; words = word_presence runs."""
    out = {}
    for s in SCRIPTS + ("all",):
        qs = [q.strip() for sc, q in quotes if s == "all" or sc == s]
        if not qs:
            continue
        ch = [len(q) for q in qs]
        wd = [len(wp.word_tokens(q)) for q in qs]
        out[s] = {"n": len(qs),
                  "chars": {"min": min(ch), "mean": round(sum(ch) / len(ch), 1), "max": max(ch),
                            **{f"p{p}": nearest_rank(ch, p) for p in PCTS}},
                  "words": {"min": min(wd), "mean": round(sum(wd) / len(wd), 1), "max": max(wd),
                            **{f"p{p}": nearest_rank(wd, p) for p in PCTS}},
                  "truncated": {c: {"count": sum(x > c for x in ch), "share": round(sum(x > c for x in ch) / len(ch), 3)}
                                for c in caps}}
    return out


# ---- data -------------------------------------------------------------------------------------------

def load_all(drive: Path):
    spikes, rec = drive / REL_SPIKES, drive / REL_RECOVERY
    pres = drive / REL_PRESENCE
    items, ans, presence = an.load(spikes, pres)
    rows, missing = an.build_rows(items, ans, presence)
    pages, cands = jf.load_recovery(rec)
    chunks = {}
    for c in cands:
        if c["chunk_id"] not in chunks:
            i, _ = jf.parse_chunk_id(c["chunk_id"])
            chunks[c["chunk_id"]] = jf.t002_chunks(pages[c["page_id"]]["text"])[i]
    by_id = {x["item_id"]: x for x in items}
    texts = {x["item_id"]: {"quote": x["quote"], "page_id": x["page_id"], "chunk_id": x["chunk_id"],
                            "page": pages[x["page_id"]]["text"], "chunk": chunks[x["chunk_id"]]} for x in items}
    for r in rows:
        x = by_id[r["item_id"]]
        r.update(quote=x["quote"], page_id=x["page_id"], chunk_id=x["chunk_id"])
    files = [spikes / "SPIKE-T003-jev-items.jsonl", spikes / "SPIKE-T003-jev-answers.jsonl", pres,
             rec / "CANDIDATES.jsonl", rec / "SOURCE-PAGES.jsonl"]
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return rows, texts, cands, missing, hashes


PAIR_FIELDS = ["pair_row", "item_id", "row_kind", "candidate_id", "control_of", "script", "institution", "page_id",
               "chunk_id", "partition", "holdout", "quote", "quote_chars", "quote_words", "presence_word", "rule_80",
               "fidelity_argmax", "fidelity_expected", "jev_4plus", "gold_label"] + \
              [m for m in METRICS] + [m + "_chunk" for m in METRICS]


def write_pairs(rows: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PAIR_FIELDS, lineterminator="\n")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"pair_row": i, "item_id": r["item_id"], "row_kind": r["row"],
                        "candidate_id": r.get("candidate_id") or "", "control_of": r.get("control_of") or "",
                        "script": r["script"], "institution": r["institution"], "page_id": r["page_id"],
                        "chunk_id": r["chunk_id"], "partition": r["partition"],
                        "holdout": r["partition"] == "holdout", "quote": r["quote"],
                        "quote_chars": len(r["quote"].strip()), "quote_words": len(wp.word_tokens(r["quote"])),
                        "presence_word": r["presence_word"], "rule_80": r["presence_word"] >= 0.8 - 1e-9,
                        "fidelity_argmax": r["fidelity_argmax"], "fidelity_expected": round(r["fidelity_expected"], 4),
                        "jev_4plus": r["jev_4plus"], "gold_label": gold(r),
                        **{m: r[m] for m in METRICS}, **{m + "_chunk": r[m + "_chunk"] for m in METRICS}})


# ---- report -----------------------------------------------------------------------------------------

def _ci(v):
    return "n/a" if v is None else f"[{v[0]:.3f}, {v[1]:.3f}]"


def _rt(v):
    return "n/a" if v is None else f"{v:.3f}"


def render_md(res: dict, meta: dict) -> str:
    L = ["# SPIKE-T003: fuzzy quote matcher calibration and quote-length distribution", "",
         f"Generated {meta['generated_at']} by `scripts/spikes/t003/calibrate_rapidfuzz.py` (branch "
         f"`orch1105/a-t003`), free and offline, rapidfuzz {meta['rapidfuzz']} on Python {meta['python']}. "
         "Lane A of the v2.7 reclassification plan, orchestrator session `20261104-claude-v2-b18c125048383d63` "
         "(claude-opus-5-5).", "",
         "**Nothing here is chosen.** The metric, the threshold (Q-020 b, DP-003) and the website display cap "
         "(DEC-016 c, DP-004) are PI decisions. Tuned thresholds below are the output of a fixed procedure, shown "
         "so the held-out error table can be read; they are not proposals.", "",
         "Companion report: `SPIKE-T003-analysis.md` (jev vs the 80% rule, the RC-D-014 bar). Pairs: "
         "`SPIKE-T003-pairs.csv` (one row per candidate and per control, labels and hold-out flag).", "",
         "## Inputs", ""]
    L += [f"- `{k}` sha256 `{v}`" for k, v in meta["inputs"].items()]
    c = meta["counts"]
    L += [f"- Rows: {c['rows']} ({c['by_kind']}); by partition {c['by_partition']}; missing {c['missing']}.", "",
          "## Labels and split (fixed by rulings)", "",
          "- Gold = jev 4+ (`fidelity_argmax >= 4`, v27-gates-1104 A3 a) OR word presence >= 0.80 (RC-D-014 S1/P1; "
          "R2 a keeps the OR; RC-D-016: 0.80 for Latin, CJK, and Thai by default).",
          "- 222 unique pairs scored by jev, mapped back to 331 candidates (P1 a); 380 near-miss controls, 190 "
          "onpage (40% of words swapped for other words of the same chunk, presence stays ~1.0) and 190 offpage "
          "(40% swapped for words absent from the page) (A2 a).",
          "- Split RC-D-014: 20% of institutions held out, script-stratified, seed 20261104; controls follow their "
          "source quote's institution.", "",
          "**Caveat: the gold contains the 0.80 word-presence rule.** Any pair with presence >= 0.80 is gold-true "
          "whatever jev says. So the scrambled onpage controls (all words present, meaning changed) are mostly "
          "gold-true, and a matcher that rejects them is scored as making false rejects. The table rewards "
          "metrics that behave like word presence. A jev-only diagnostic and a scrambled-acceptance count are "
          "shown beside it; neither is the ruled gold.", "",
          "**Chrome-text gap.** None of the 331 candidates or 50 source pages has chrome text (every candidate's "
          "`text_surface` is `historical_main_text_only`; every page has `chrome_text_available: false`). The "
          "RC-D-002 N33 requirement that calibration pairs include quotes matched against chrome text (T-014) is "
          "**not met**; no chrome pairs exist in the inputs and none were fetched.", "",
          "## Library pin (DEC-007 a)", "",
          f"- rapidfuzz **{PINNED_RAPIDFUZZ}** (the version installed locally and used here; PyPI latest at run time "
          f"{meta['pypi_latest']}). Licence: MIT (PyPI `license_expression`). `requires_python >= 3.10`.",
          "- Droplet wheel: PyPI lists `rapidfuzz-3.14.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl` "
          "(sha256 `6c5f545f454871e6af05753a0172849c82feaf0f521c5ca62ba09e1b382d6382`) and a musllinux_1_2 x86_64 "
          "wheel. The manylinux wheel needs glibc >= 2.28. **The droplet's Python version and glibc were not "
          "checked** (no SSH from this lane); availability holds if it is CPython 3.12 on x86_64 with glibc >= 2.28.",
          "- rapidfuzz is not a dependency in `pyproject.toml`; adding it is T-024's change, not this spike's. "
          "Metric tests skip when it is absent, so the required CI does not exercise them.", "",
          "## Metrics compared", "",
          "Each score is 0-100, the quote against the stored page text (the T-024 surface). Normalized = NFKC, "
          "casefold, punctuation dropped, word runs joined by one space (the `word_presence.py` tokens); light = "
          "NFKC, casefold, whitespace collapsed.", "",
          "| Metric | What it measures | Why a candidate |", "|---|---|---|",
          "| `partial_ratio_norm` | best contiguous character alignment of the quote inside the page | "
          "order-sensitive; no word segmentation, so usable for CJK/Thai; tolerates small edits |",
          "| `partial_ratio_light` | same, punctuation kept | shows what punctuation normalization changes |",
          "| `token_set_ratio_norm` | order-free token overlap | close to the 80% rule; largely restates the gold. "
          "Like the rule, it depends on CJK/Thai run boundaries: a quote cut inside a page's letter run is a "
          "different token (tested: 9 CJK characters inside a 12-character run score < 50) |",
          "", "`fuzz.ratio` on the whole page is excluded: against a page it scores length difference, not presence. "
          f"Page and chunk scores differ on {meta['page_vs_chunk']} rows (the chunk score is a diagnostic column "
          "in the pairs CSV).", "",
          "## Tuning (procedure, not a choice)", "",
          "Accept when score >= t (integer t). On tuning rows, the argmin set minimizes false matches + false "
          "rejects against the gold; the tuned t is its lower median.", "",
          "| Metric | Scope | tuning n | min errors | argmin range | tuned t | decision = 80% rule (all rows) |",
          "|---|---|---|---|---|---|---|"]
    for m, r in res["calibration"].items():
        p = r["pooled"]
        L.append(f"| `{m}` | pooled | {p['n']} | {p['tuning_errors']} | {p['argmin_lo']}-{p['argmin_hi']} | "
                 f"{p['tuned']} | {r['agrees_with_rule_80']:.3f} |")
        for s, q in r["per_script"].items():
            L.append(f"| `{m}` | {s} | {q['n']} | {q['tuning_errors']} | {q['argmin_lo']}-{q['argmin_hi']} | "
                     f"{q['tuned']} | |")
    L += ["", f"Gold-false rows are almost all synthetic offpage controls: gold-false candidates are "
          f"{meta['gold_false_candidates']} by partition. So false-match rates measure rejection of synthetic word swaps, "
          "not of real misquotes; no real negative pairs exist in the inputs."]
    L += ["", "## Held-out error table by script (DP-003)", "",
          "FM = false match (accepted, gold false), rate over gold-false rows; FR = false reject (rejected, gold "
          "true), rate over gold-true rows; 95% Wilson intervals. Rows are candidates plus both control kinds.", "",
          "| Metric | Script | Threshold | t | n | gold T/F | FM | FM rate [95% CI] | FR | FR rate [95% CI] | "
          "FM/FR by kind (cand; onpage; offpage) | flag |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, r in res["calibration"].items():
        for s in SCRIPTS:
            h = r["holdout"][s]
            for which in ("pooled", "per_script"):
                if which not in h:
                    continue
                b = h[which]
                k = b["by_kind"]
                kinds = "; ".join(f"{k[x]['false_match']}/{k[x]['false_reject']}"
                                  for x in ("candidate", "control_onpage", "control_offpage"))
                L.append(f"| `{m}` | {s} | {which} | {b['threshold']} | {b['n']} | {b['gold_true']}/{b['gold_false']} "
                         f"| {b['false_match']} | {_rt(b['fm_rate'])} {_ci(b['fm_ci95'])} | {b['false_reject']} | "
                         f"{_rt(b['fr_rate'])} {_ci(b['fr_ci95'])} | {kinds} | {h.get('flag', '')} |")
    L += ["", "Held-out composition: Latin 6 institutions, CJK 1 institution (all 33 CJK held-out candidates and 20 "
          "controls come from one institution), Thai 1 institution. Intervals are wide; CJK held-out is effectively "
          "one site.", "",
          "## Diagnostics beside the gold (not the ruled label)", "",
          "jev-only label (jev 4+ alone) at the per-script tuned t (pooled for Thai), and scrambled onpage controls "
          "accepted with jev < 4 (counted as correct under the OR gold).", "",
          "| Metric | Script | t | jev-only FM | jev-only FR | onpage n | scrambled accepted |",
          "|---|---|---|---|---|---|---|"]
    for m, r in res["calibration"].items():
        for s in SCRIPTS:
            j, sa = r["jev_only"][s], r["scrambled_accepted"][s]
            L.append(f"| `{m}` | {s} | {j['threshold']} | {j['false_match']}/{j['gold_false']} | "
                     f"{j['false_reject']}/{j['gold_true']} | {sa['n']} | {sa['accepted_jev_below_4']} |")
    L += ["", "## Threshold sweep (errors FM/FR at fixed t, candidates + controls)", ""]
    for m, r in res["calibration"].items():
        L += [f"### `{m}`", "", "| Script | Partition | n | " + " | ".join(f"t={t}" for t in SHOW_THRESHOLDS) + " |",
              "|---|---|---|" + "---|" * len(SHOW_THRESHOLDS)]
        for s in SCRIPTS:
            for p in ("tuning", "holdout"):
                sw = r["sweep"][s][p]
                L.append(f"| {s} | {p} | {sw[0]['n']} | " +
                         " | ".join(f"{x['false_match']}/{x['false_reject']}" for x in sw) + " |")
        L.append("")
    L += ["## Quote-length distribution and display-cap table (DP-004)", "",
          "Chars = Unicode code points of the stripped quote; words = `word_presence.py` runs (for CJK and Thai a "
          "run is often a whole clause, so word counts there are not comparable with Latin). Percentiles are "
          "nearest-rank. Source: the T-002 quotes (Haiku legs); production quotes will come from the T-022/T-032 "
          "prompts, which are not written yet, so their lengths may differ. **No cap is proposed; the PI sets it.**",
          ""]
    for name, tab in res["lengths"].items():
        L += [f"### {name}", "", "| Script | n | unit | min | p10 | p25 | p50 | p75 | p90 | p95 | p99 | max | mean |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for s, b in tab.items():
            for u in ("chars", "words"):
                d = b[u]
                L.append(f"| {s} | {b['n']} | {u} | {d['min']} | " + " | ".join(str(d[f'p{p}']) for p in PCTS) +
                         f" | {d['max']} | {d['mean']} |")
        L += ["", "Share of quotes a cap would truncate (quote longer than the cap, in characters):", "",
              "| Script | n | " + " | ".join(f"{c} chars" for c in CAPS) + " |", "|---|---|" + "---|" * len(CAPS)]
        for s, b in tab.items():
            L.append(f"| {s} | {b['n']} | " + " | ".join(
                f"{b['truncated'][c]['share']:.3f} ({b['truncated'][c]['count']})" for c in CAPS) + " |")
        L.append("")
    L += ["DEC-016 c: the cap applies to the website only; the API keeps the full text.", "",
          "## Not in this report", "",
          "- A chosen metric, threshold or cap (PI decisions).",
          "- Chrome-text pairs (none exist in the inputs; gap above).",
          "- Entailment (R-042 checks presence only).", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--drive", type=Path, default=None, help=f"Drive root; default ${jf.DRIVE_ENV}")
    ap.add_argument("--out", type=Path, default=None, help=f"output folder; default <drive>/{REL_SPIKES}")
    ap.add_argument("--pypi-latest", default="unknown", help="PyPI latest rapidfuzz version seen, for the report")
    ap.add_argument("--allow-other-version", action="store_true")
    a = ap.parse_args(argv)
    drive = jf.drive_root(a.drive)
    v = check_version(a.allow_other_version)
    out = a.out or drive / REL_SPIKES
    rows, texts, cands, missing, hashes = load_all(drive)
    score_all(rows, texts)
    uniq = {}
    for c in cands:
        uniq.setdefault((c["chunk_id"], c["quote"]), c["script"])
    res = {"calibration": calibrate(rows),
           "lengths": {"331 candidates": length_table([(c["script"], c["quote"]) for c in cands]),
                       "222 unique pairs": length_table([(s, q) for (_, q), s in uniq.items()])}}
    meta = {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "rapidfuzz": v,
            "python": sys.version.split()[0], "pypi_latest": a.pypi_latest, "inputs": hashes,
            "page_vs_chunk": page_vs_chunk(rows),
            "gold_false_candidates": {p: sum(1 for r in rows if r["row"] == "candidate" and r["partition"] == p
                                             and not gold(r)) for p in ("tuning", "holdout")},
            "counts": {"rows": len(rows), "missing": missing,
                       "by_kind": dict(Counter(r["row"] for r in rows)),
                       "by_partition": dict(Counter(r["partition"] for r in rows))}}
    write_pairs(rows, out / "SPIKE-T003-pairs.csv")
    (out / "SPIKE-T003-rapidfuzz.json").write_text(json.dumps({"meta": meta, **res}, indent=1, default=str),
                                                    encoding="utf-8")
    (out / "SPIKE-T003.md").write_text(render_md(res, meta), encoding="utf-8")
    summary = {m: {"pooled": r["pooled"]["tuned"], **{s: q["tuned"] for s, q in r["per_script"].items()}}
               for m, r in res["calibration"].items()}
    print(json.dumps({"counts": meta["counts"], "tuned": summary}, indent=1))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
