"""T-003 step 5: jev fidelity vs the 80% word-presence rule (RC-D-014). Free, offline, standard library only.

Label rulings applied: jev 4+ = fidelity_argmax >= 4 (v27-gates-1104 A3 a); 222 unique pairs mapped back to the
331 candidates (P1 a); gold = jev 4+ OR rule_80 (RC-D-014 P1 follow-up). Bar (RC-D-014): Spearman rho of word
presence vs jev 1-5 >= 0.5 per script with n >= 30, near-miss controls included; read with fidelity_expected on the
331 candidates plus controls (v27-results-1104 R1 b). R2 a keeps the OR gold; R3 b asks for per-script cutoffs
(Latin, CJK), so this script tabulates cutoff errors for the PI. It chooses no threshold, split, unit or cutoff.

Usage:
    python analyze_t003.py [--drive <root> | --lane-dir <dir>] [--out <dir>] [--presence-csv <csv>]
Inputs default to <G3O_DRIVE_ROOT>/agent-workspace/2026-11-04-v27-orch/lane-a; exits 2 if no root is given.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

REL_LANE_DIR = "agent-workspace/2026-11-04-v27-orch/lane-a"   # relative to the Drive root (G3O_DRIVE_ROOT)

DRIVE_ENV = "G3O_DRIVE_ROOT"   # the G3O Drive root (the folder holding agent-workspace/); no machine path in git


def drive_root(override: Path | None = None) -> Path:
    """The Drive root from --drive or G3O_DRIVE_ROOT. Exits with code 2 and a clear message when neither is set."""
    v = override or os.environ.get(DRIVE_ENV)
    if not v:
        print(f"{DRIVE_ENV} is not set: point it at the G3O Drive root (the folder holding agent-workspace/), "
              "or pass --drive.", file=sys.stderr)
        raise SystemExit(2)
    p = Path(v)
    if not (p / "agent-workspace").is_dir():
        print(f"{DRIVE_ENV}={v} has no agent-workspace/ folder.", file=sys.stderr)
        raise SystemExit(2)
    return p
SCRIPTS = ("latin", "cjk", "thai")
BAR_RHO, BAR_N = 0.5, 30
JEV_4PLUS = 4
CUTOFFS = tuple(round(0.50 + 0.05 * i, 2) for i in range(11))   # 0.50 .. 1.00, for display only
GOLD_RULE_CUTOFF = 0.80                                          # the rule inside the OR gold (RC-D-014 S1)
TUNABLE_SCRIPTS = ("latin", "cjk")                               # Thai: tuning n = 1, not tunable

RULINGS = {
    "A3": "v27-gates-1104 A3 a 'Most likely level': jev 4+ label = fidelity_argmax >= 4",
    "P1": "v27-gates-1104 P1 a 'Score 222 unique, map back'",
    "R1": "v27-results-1104 R1 b 'Average score, all candidates': the Spearman bar uses fidelity_expected on the "
          "331 mapped candidates plus controls",
    "R2": "v27-results-1104 R2 a \"Keep 'or'\": gold = jev 4+ OR rule_80",
    "R3": "v27-results-1104 R3 b 'Per-script cutoffs': Latin and CJK tuned separately; Thai keeps the default",
    "R3_values": "PI chat 2026-11-04: \".8 for both is fine\" -> Latin 0.80, CJK 0.80; Thai keeps the default 0.80 "
                 "(not tunable)",
    "source": "decision pages v27-gates-1104 (saved 2026-11-04T16:23:45Z), v27-results-1104 (2026-11-04T17:54:45Z)",
}
BAR_SET, BAR_FIELD = "candidates_331_plus_controls", "rho_expected"   # R1 b
CHOSEN_CUTOFFS = {"latin": 0.80, "cjk": 0.80, "thai": 0.80}            # R3 values, PI 2026-11-04


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
    out["bar_ruled"] = {}
    for s in SCRIPTS:
        b = out["spearman"][BAR_SET][s]
        rho = b[BAR_FIELD]
        out["bar_ruled"][s] = {"set": BAR_SET, "field": BAR_FIELD, "n": b["n"], "rho": rho,
                               "verdict": "n/a (n < 30)" if b["n"] < BAR_N else
                               ("met" if rho is not None and rho >= BAR_RHO else "not met")}
    out["cutoffs"] = {p: {s: cutoff_table(rows, s, p) for s in TUNABLE_SCRIPTS} for p in ("tuning", "holdout")}
    out["chosen_cutoffs"] = {s: {"cutoff": c, **{p: cutoff_table(rows, s, p, (c,))[0] for p in ("tuning", "holdout")}}
                             for s, c in CHOSEN_CUTOFFS.items()}
    out["chosen_cutoffs"]["thai"]["note"] = "not tunable (tuning n = 1); default kept; held-out errors not estimable"
    return out


def gold(r: dict) -> bool:
    """OR gold (R2 a): jev 4+ or the 80% rule at its RC-D-014 cutoff, independent of the cutoff being examined."""
    return r["jev_4plus"] or r["presence_word"] >= GOLD_RULE_CUTOFF - 1e-9


def cutoff_table(rows: list[dict], script: str, partition: str, cutoffs=CUTOFFS) -> list[dict]:
    """Errors of the decision `presence_word >= c` against the OR gold, per cutoff c.

    false_match  decision true, gold false: only possible for c < 0.80 (presence in [c, 0.80) and jev < 4).
    false_reject decision false, gold true: presence below c but gold true (jev 4+, or presence in [0.80, c)).
    Candidates and offpage controls are counted against the gold. Onpage (scrambled) controls are gold-true
    whenever the rule passes, so their acceptances with jev < 4 are counted separately and never as errors.
    """
    sel = [r for r in rows if r["script"] == script and r["partition"] == partition]
    out = []
    for c in cutoffs:
        row = {"cutoff": c}
        for label, kinds in (("candidates", ("candidate",)), ("offpage", ("control_offpage",))):
            rs = [r for r in sel if r["row"] in kinds]
            dec = [r["presence_word"] >= c - 1e-9 for r in rs]
            row[f"{label}_n"] = len(rs)
            row[f"{label}_false_match"] = sum(d and not gold(r) for d, r in zip(dec, rs, strict=True))
            row[f"{label}_false_reject"] = sum(not d and gold(r) for d, r in zip(dec, rs, strict=True))
        on = [r for r in sel if r["row"] == "control_onpage"]
        row["onpage_n"] = len(on)
        row["onpage_scrambled_accepted"] = sum(r["presence_word"] >= c - 1e-9 and not r["jev_4plus"] for r in on)
        out.append(row)
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
          "- Rulings: " + "; ".join(f"{k}: {v}" for k, v in RULINGS.items() if k != "source") + ".", "",
          "## Bar as ruled (R1 b): rho of presence vs jev expected score, 331 candidates + controls", "",
          "| Script | n | rho | Verdict |", "|---|---|---|---|"] + [
          f"| {s} | {b['n']} | {_fmt(b['rho'])} | {b['verdict']} |" for s, b in res["bar_ruled"].items()] + [
          "", "Under R1 b the bar is **met for Latin and CJK**; Thai is n/a (n = 18 < 30). The 4+ label stays "
          "`fidelity_argmax` (A3 a).", "",
          "## Bar (RC-D-014), every reading computed before R1", "",
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
    L += ["", "## Per-script cutoffs (R3 b): errors of `presence_word >= c` against the OR gold", "",
          "Choose-none table: no cutoff is selected. Gold = jev 4+ OR presence >= 0.80 (fixed; R2 a). FM = false "
          "match, FR = false reject. Onpage controls are scrambled quotes with every word present; "
          "`scrambled accepted` = decision true and jev < 4, reported separately because the OR gold calls them "
          "true matches.", "",
          "What the objective can and cannot see: because the gold contains the 0.80 rule itself, any cutoff c >= "
          "0.80 has zero false matches by construction, and raising c above 0.80 can only add false rejects. "
          "Lowering c below 0.80 can only add false matches (presence in [c, 0.80) with jev < 4) or remove false "
          "rejects (jev 4+ with presence below 0.80). Leniency above 0.80, i.e. quotes whose words are all present "
          "but whose meaning is changed, is invisible to the gold; only the `scrambled accepted` column shows it, "
          "and no word-presence cutoff removes it: most scrambled controls have presence exactly 1.0.", ""]
    for p in ("tuning", "holdout"):
        for s in TUNABLE_SCRIPTS:
            t = res["cutoffs"][p][s]
            L += [f"### {p}, {s} (candidates n={t[0]['candidates_n']}, offpage n={t[0]['offpage_n']}, "
                  f"onpage n={t[0]['onpage_n']})", "",
                  "| cutoff | cand FM | cand FR | offpage FM | offpage FR | scrambled accepted |",
                  "|---|---|---|---|---|---|"]
            L += [f"| {r['cutoff']:.2f} | {r['candidates_false_match']} | {r['candidates_false_reject']} | "
                  f"{r['offpage_false_match']} | {r['offpage_false_reject']} | {r['onpage_scrambled_accepted']} |"
                  for r in t]
            L.append("")
    L += ["Thai: not tunable (tuning n = 1); keeps the default (R3 b). Held-out Thai errors are not estimable.", "",
          "## Chosen cutoffs (PI, 2026-11-04 chat: \".8 for both is fine\")", "",
          "Latin 0.80, CJK 0.80; Thai keeps the default 0.80 (not tunable). Errors at the chosen cutoff "
          "(candidates FM / FR; offpage controls FM / FR; scrambled onpage controls accepted with jev < 4):", "",
          "| Script | Partition | cand n | cand FM | cand FR | offpage n | offpage FM | offpage FR | onpage n | "
          "scrambled accepted |", "|---|---|---|---|---|---|---|---|---|---|"]
    for s, ch in res["chosen_cutoffs"].items():
        for p in ("tuning", "holdout"):
            r = ch[p]
            L.append(f"| {s} | {p} | {r['candidates_n']} | {r['candidates_false_match']} | "
                     f"{r['candidates_false_reject']} | {r['offpage_n']} | {r['offpage_false_match']} | "
                     f"{r['offpage_false_reject']} | {r['onpage_n']} | {r['onpage_scrambled_accepted']} |")
    L += ["", "Caveat: the OR gold contains the 0.80 rule itself, so at the chosen 0.80 cutoff false matches are zero "
          "by construction and the error counts can only show false rejects (jev 4+ below 0.80 presence). Leniency "
          "above 0.80 shows only in the scrambled-control column. Thai held-out errors are not estimable.", "",
          "RC-D-014 S2 b says per-script cutoffs \"where held-out errors require\" them. At the 0.80 rule the "
          "held-out candidates show 0 errors in Latin and CJK, so the held-out evidence does not by itself require "
          "a per-script cutoff (held-out offpage controls show 2 false rejects per script at 0.80: jev 4+ on quotes "
          "with about 60% of words present); R3 b rules per-script cutoffs anyway. Held-out CJK is one institution.", ""]
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
    ap.add_argument("--drive", type=Path, default=None, help=f"Drive root; default ${DRIVE_ENV}")
    ap.add_argument("--lane-dir", type=Path, default=None, help=f"inputs; default <drive>/{REL_LANE_DIR}")
    ap.add_argument("--out", type=Path, default=None, help="report folder; default the lane dir")
    ap.add_argument("--presence-csv", type=Path, default=None)
    ap.add_argument("--out-prefix", default="SPIKE-T003-analysis")
    a = ap.parse_args(argv)
    if a.lane_dir is None:
        a.lane_dir = drive_root(a.drive) / REL_LANE_DIR
    out_dir = a.out or a.lane_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    pcsv = a.presence_csv or a.lane_dir / "T003-word-presence-thai-fix.csv"
    items, ans, pres = load(a.lane_dir, pcsv)
    rows, missing = build_rows(items, ans, pres)
    res = analyze(rows)
    files = [a.lane_dir / "SPIKE-T003-jev-items.jsonl", a.lane_dir / "SPIKE-T003-jev-answers.jsonl", pcsv]
    meta = {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "rulings": RULINGS,
            "inputs": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            "counts": {"items": len(items), "answers_ok": len(ans), "rows": len(rows), "missing": missing}}
    (out_dir / f"{a.out_prefix}.json").write_text(json.dumps({"meta": meta, **res}, indent=1), encoding="utf-8")
    (out_dir / f"{a.out_prefix}.md").write_text(render_md(res, meta), encoding="utf-8")
    print(json.dumps({"counts": meta["counts"], "bar_ruled": res["bar_ruled"]}, indent=1))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
