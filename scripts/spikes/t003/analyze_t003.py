"""T-003 step 5: jev fidelity vs the 80% word-presence rule (RC-D-014). Free, offline, standard library only.

Label rulings applied: jev 4+ = fidelity_argmax >= 4 (v27-gates-1104 A3 a); 222 unique pairs mapped back to the
331 candidates (P1 a); gold = jev 4+ OR rule_80 (RC-D-014 P1 follow-up). Bar (RC-D-014): Spearman rho of word
presence vs jev 1-5 >= 0.5 per script with n >= 30, near-miss controls included.

This script reports; it chooses no threshold, split, unit or cutoff.

Usage:
    python analyze_t003.py --lane-dir <dir> [--presence-csv <csv>] [--out-prefix SPIKE-T003-analysis]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

LANE_DIR = Path("H:/My Drive/Research/G3O/agent-workspace/2026-11-04-v27-orch/lane-a")
SCRIPTS = ("latin", "cjk", "thai")
BAR_RHO, BAR_N = 0.5, 30
JEV_4PLUS = 4


# ---- statistics ------------------------------------------------------------------------------------

def rankdata(xs: list[float]) -> list[float]:
    """Average ranks (1-based), ties share the mean rank."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rho with average ranks for ties (Pearson on ranks). None if either side is constant."""
    return pearson(rankdata(x), rankdata(y))


def table2x2(a: list[bool], b: list[bool]) -> dict:
    """a = jev 4+, b = rule_80."""
    c = Counter(zip(a, b, strict=True))
    return {"both": c[(True, True)], "jev_only": c[(True, False)], "rule_only": c[(False, True)],
            "neither": c[(False, False)], "n": len(a)}


def kappa(t: dict) -> float | None:
    n = t["n"]
    if n == 0:
        return None
    po = (t["both"] + t["neither"]) / n
    pa = (t["both"] + t["jev_only"]) / n
    pb = (t["both"] + t["rule_only"]) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe == 1 else (po - pe) / (1 - pe)


def _r(v, d=4):
    return None if v is None else round(v, d)


# ---- data ------------------------------------------------------------------------------------------

def _bool(s: str) -> bool | None:
    return {"True": True, "False": False}.get(s)


def load(lane_dir: Path, presence_csv: Path):
    items = [json.loads(line) for line in open(lane_dir / "SPIKE-T003-jev-items.jsonl", encoding="utf-8")]
    ans = {}
    for line in open(lane_dir / "SPIKE-T003-jev-answers.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r.get("kind") == "jev" and r.get("ok"):
            ans[r["key"]] = r
    with open(presence_csv, encoding="utf-8", newline="") as f:
        pres = {r["candidate_id"]: r for r in csv.DictReader(f)}
    return items, ans, pres


def build_rows(items, ans, pres) -> tuple[list[dict], dict]:
    """One row per candidate (mapped from its unique pair) and one per control."""
    part_by_inst = {r["institution"]: r["partition"] for r in pres.values()}
    by_id = {x["item_id"]: x for x in items}
    rows, missing = [], Counter()
    for x in items:
        a = ans.get(x["item_id"])
        if a is None:
            missing["no_answer"] += 1
            continue
        jev = {"fidelity_argmax": a["fidelity_argmax"], "fidelity_expected": a["fidelity_expected"],
               "jev_4plus": a["fidelity_argmax"] >= JEV_4PLUS, "item_id": x["item_id"]}
        if x["kind"] == "candidate":
            for cid in x["candidate_ids"]:
                p = pres.get(cid)
                if p is None:
                    missing["no_presence_row"] += 1
                    continue
                rows.append({**jev, "row": "candidate", "candidate_id": cid, "script": p["script"],
                             "presence_word": float(p["presence_word"]), "rule_80": _bool(p["rule_80"]),
                             "partition": p["partition"], "institution": p["institution"],
                             "unique_first": cid == x["candidate_ids"][0]})
        else:
            src = by_id[x["control_of"]]
            pw = x["presence_word"]
            rows.append({**jev, "row": "control_" + x["control_kind"], "candidate_id": None, "script": x["script"],
                         "presence_word": pw, "rule_80": pw >= 0.8, "control_of": x["control_of"],
                         "partition": part_by_inst.get(src["institution"]), "institution": src["institution"],
                         "unique_first": True})
    return rows, dict(missing)


# ---- analysis --------------------------------------------------------------------------------------

def _rho_block(rs: list[dict]) -> dict:
    x = [r["presence_word"] for r in rs]
    return {"n": len(rs),
            "rho_argmax": _r(spearman(x, [r["fidelity_argmax"] for r in rs])),
            "rho_expected": _r(spearman(x, [r["fidelity_expected"] for r in rs])),
            "presence_distinct_values": len(set(x))}


def _agree_block(rs: list[dict]) -> dict:
    t = table2x2([r["jev_4plus"] for r in rs], [bool(r["rule_80"]) for r in rs])
    return {**t, "kappa": _r(kappa(t)),
            "raw_agreement": _r((t["both"] + t["neither"]) / t["n"]) if t["n"] else None}


def analyze(rows: list[dict]) -> dict:
    sets = {
        "candidates_331": [r for r in rows if r["row"] == "candidate"],
        "unique_222": [r for r in rows if r["row"] == "candidate" and r["unique_first"]],
        "candidates_331_plus_controls": rows,
        "unique_222_plus_controls": [r for r in rows if r["unique_first"]],
    }
    out = {"spearman": {}, "agreement": {}, "bar": {}, "controls": {}, "partition": {}, "fidelity_dist": {}}
    for name, rs in sets.items():
        out["spearman"][name] = {s: _rho_block([r for r in rs if r["script"] == s]) for s in SCRIPTS}
        out["spearman"][name]["all"] = _rho_block(rs)
        out["agreement"][name] = {s: _agree_block([r for r in rs if r["script"] == s]) for s in SCRIPTS}
        out["agreement"][name]["all"] = _agree_block(rs)
    for name in ("candidates_331_plus_controls", "unique_222_plus_controls"):
        out["bar"][name] = {}
        for s in SCRIPTS:
            b = out["spearman"][name][s]
            ok_n = b["n"] >= BAR_N
            out["bar"][name][s] = {
                "n": b["n"], "n_ok": ok_n,
                "meets_argmax": None if not ok_n or b["rho_argmax"] is None else b["rho_argmax"] >= BAR_RHO,
                "meets_expected": None if not ok_n or b["rho_expected"] is None else b["rho_expected"] >= BAR_RHO}
    for kind in ("control_onpage", "control_offpage"):
        rs = [r for r in rows if r["row"] == kind]
        out["controls"][kind] = {}
        for s in SCRIPTS + ("all",):
            sr = [r for r in rs if s == "all" or r["script"] == s]
            if not sr:
                continue
            out["controls"][kind][s] = {
                "n": len(sr), "presence_mean": _r(sum(r["presence_word"] for r in sr) / len(sr)),
                "rule_80_true": sum(bool(r["rule_80"]) for r in sr),
                "jev_4plus": sum(r["jev_4plus"] for r in sr),
                "rule_80_and_jev_4plus": sum(bool(r["rule_80"]) and r["jev_4plus"] for r in sr),
                "rule_80_not_jev_4plus": sum(bool(r["rule_80"]) and not r["jev_4plus"] for r in sr),
                "fidelity_argmax": dict(sorted(Counter(r["fidelity_argmax"] for r in sr).items()))}
    for row_kind in ("candidate", "control_onpage", "control_offpage"):
        out["fidelity_dist"][row_kind] = dict(sorted(Counter(
            r["fidelity_argmax"] for r in rows if r["row"] == row_kind and r["unique_first"]).items()))
    for p in ("tuning", "holdout"):
        out["partition"][p] = {}
        for s in SCRIPTS:
            block = {}
            for label, sel in (("candidates", lambda r: r["row"] == "candidate"),
                               ("controls", lambda r: r["row"] != "candidate")):
                rs = [r for r in rows if r["partition"] == p and r["script"] == s and sel(r)]
                t = table2x2([r["jev_4plus"] for r in rs], [bool(r["rule_80"]) for r in rs])
                block[label] = {**t, "gold_true": t["both"] + t["jev_only"] + t["rule_only"],
                                "disagree": t["jev_only"] + t["rule_only"],
                                "institutions": len({r["institution"] for r in rs})}
            if s == "thai" and p == "holdout":
                block["flag"] = "not estimable: Thai tuning has n=1 (RC-D-014); held-out Thai errors not estimable"
            out["partition"][p][s] = block
    return out


# ---- report ----------------------------------------------------------------------------------------

def _fmt(v):
    return "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def render_md(res: dict, meta: dict) -> str:
    L = ["# SPIKE-T003: jev quote fidelity vs the 80% word-presence rule", "",
         f"Generated {meta['generated_at']} by `scripts/spikes/t003/analyze_t003.py` (branch `orch1104/a-t003-jev`), "
         "free and offline. Lane A, orchestrator session `20261104-claude-v2-87b58de9a1ec1fe0` (claude-opus-5-5).",
         "Reports only: no threshold, split, unit or cutoff is chosen here.", "",
         "## Inputs and rulings", ""]
    for k, v in meta["inputs"].items():
        L.append(f"- `{k}` sha256 `{v}`")
    L += ["- jev 4+ = `fidelity_argmax >= 4` (v27-gates-1104 A3 a). Gold label = jev 4+ OR rule_80 (RC-D-014).",
          "- 222 unique (chunk, quote) pairs scored, mapped back to 331 candidates (P1 a). Controls: 190 onpage + "
          "190 offpage, 40% of words swapped (A2 a). jev model `jev-1.13.0`; paid run $0.131432 (Simone).",
          "- Word presence from the Thai-fixed `word_presence.py` (PR #155). Controls' presence is computed by the "
          "same function at item build time.", "",
          "## Bar (RC-D-014): Spearman rho >= 0.5 per script, n >= 30, controls included", "",
          "| Set | Script | n | rho (argmax) | rho (expected) | Meets bar (argmax / expected) |",
          "|---|---|---|---|---|---|"]
    for name in ("candidates_331_plus_controls", "unique_222_plus_controls"):
        for s in SCRIPTS:
            sp, b = res["spearman"][name][s], res["bar"][name][s]
            meets = "n < 30: bar not applicable" if not b["n_ok"] else \
                f"{'yes' if b['meets_argmax'] else 'no'} / {'yes' if b['meets_expected'] else 'no'}"
            L.append(f"| {name} | {s} | {sp['n']} | {_fmt(sp['rho_argmax'])} | {_fmt(sp['rho_expected'])} | {meets} |")
    L += ["", "## Spearman rho, all sets (presence_word vs jev fidelity 1-5)", "",
          "| Set | Script | n | rho (argmax) | rho (expected) | distinct presence values |", "|---|---|---|---|---|---|"]
    for name, blk in res["spearman"].items():
        for s in SCRIPTS + ("all",):
            b = blk[s]
            L.append(f"| {name} | {s} | {b['n']} | {_fmt(b['rho_argmax'])} | {_fmt(b['rho_expected'])} | "
                     f"{b['presence_distinct_values']} |")
    L += ["", "## 2x2 agreement, jev 4+ vs rule_80", "",
          "| Set | Script | n | both | jev 4+ only | rule only | neither | raw agree | kappa |",
          "|---|---|---|---|---|---|---|---|---|"]
    for name, blk in res["agreement"].items():
        for s in SCRIPTS + ("all",):
            b = blk[s]
            L.append(f"| {name} | {s} | {b['n']} | {b['both']} | {b['jev_only']} | {b['rule_only']} | {b['neither']} "
                     f"| {_fmt(b['raw_agreement'])} | {_fmt(b['kappa'])} |")
    L += ["", "## Near-miss controls", "",
          "| Kind | Script | n | mean presence | rule_80 true | jev 4+ | rule true, jev < 4 | fidelity_argmax counts |",
          "|---|---|---|---|---|---|---|---|"]
    for kind, blk in res["controls"].items():
        for s, b in blk.items():
            L.append(f"| {kind} | {s} | {b['n']} | {_fmt(b['presence_mean'])} | {b['rule_80_true']} | {b['jev_4plus']} "
                     f"| {b['rule_80_not_jev_4plus']} | {b['fidelity_argmax']} |")
    L += ["", "jev fidelity_argmax distribution (unique items): " +
          "; ".join(f"{k} {v}" for k, v in res["fidelity_dist"].items()), "",
          "## Tuning vs held-out (RC-D-014 split, `word_presence.assign_partitions`)", "",
          "Errors are disagreements between jev 4+ and rule_80. Under the OR gold label the rule never "
          "false-matches by construction; its only gold errors are `jev 4+ only` (false rejects).", "",
          "| Partition | Script | Rows | Institutions | n | both | jev 4+ only | rule only | neither | gold true | flag |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p, blk in res["partition"].items():
        for s in SCRIPTS:
            for label in ("candidates", "controls"):
                b = blk[s][label]
                flag = blk[s].get("flag", "") if label == "candidates" else ""
                L.append(f"| {p} | {s} | {label} | {b['institutions']} | {b['n']} | {b['both']} | {b['jev_only']} | "
                         f"{b['rule_only']} | {b['neither']} | {b['gold_true']} | {flag} |")
    L += ["", "## Structural notes", "",
          "- Without controls, word presence is almost constant (nearly every candidate is at or near 1.0), so rho "
          "on candidates alone mostly reflects jev variance; the bar is defined with controls included.",
          "- The gold label is jev 4+ OR rule_80, so any pair the rule passes is gold-true whatever jev says. Onpage "
          "controls (all words present, meaning changed) are therefore gold-true by construction.",
          "- `rho (argmax)` uses jev's most likely level (the A3 a reading of 4+); `rho (expected)` uses the "
          "probability-weighted score. RC-D-014 does not say which jev value the Spearman bar uses.",
          "- `candidates_331` counts duplicate candidates (same chunk and quote) once each; `unique_222` counts "
          "each scored pair once.", ""]
    L += ["", "## Not in this report", "",
          "- Metric/threshold calibration of `rapidfuzz`, the quote-length distribution and the display-cap table "
          "(T-003 outputs still due).", "- Chrome-text pairs (none recoverable; HANDOFF 2026-11-02).", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    import hashlib
    from datetime import datetime, timezone
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lane-dir", type=Path, default=LANE_DIR)
    ap.add_argument("--presence-csv", type=Path, default=None)
    ap.add_argument("--out-prefix", default="SPIKE-T003-analysis")
    a = ap.parse_args(argv)
    pcsv = a.presence_csv or a.lane_dir / "T003-word-presence-thai-fix.csv"
    items, ans, pres = load(a.lane_dir, pcsv)
    rows, missing = build_rows(items, ans, pres)
    res = analyze(rows)
    files = [a.lane_dir / "SPIKE-T003-jev-items.jsonl", a.lane_dir / "SPIKE-T003-jev-answers.jsonl", pcsv]
    meta = {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "inputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            "counts": {"items": len(items), "answers_ok": len(ans), "rows": len(rows), "missing": missing}}
    (a.lane_dir / f"{a.out_prefix}.json").write_text(json.dumps({"meta": meta, **res}, indent=1), encoding="utf-8")
    (a.lane_dir / f"{a.out_prefix}.md").write_text(render_md(res, meta), encoding="utf-8")
    print(json.dumps({"counts": meta["counts"], "bar": res["bar"]}, indent=1))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
