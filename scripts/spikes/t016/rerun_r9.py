"""T-016 rerun of the reworded items on the RC-D-007 candidate codebook (r9, unsigned).

PI rulings 2026-10-31 (chat): "3 ok rerun" (small paid rerun of the reworded items); clean copy "approved".
Reuses repilot_v27.py unchanged; only the inputs differ:
  - questions: the jev questions generated from the r9 candidate whose dict differs from the signed release's
    (`g3o/codebook/generated/jev_questions.json` on main); part-prompt block unchanged;
  - page parts: every part whose T-016 page verdict was `confirms_activity`, plus every part of the 50 long pages;
  - entailment: the 300 T-016 units re-asked with the C7 question and plain-word labels; v2.5 fields with no v2.7
    item, or values that are not a v2.7 code of that item, are dropped and counted (fill spec, clean copy);
  - no Stage 6 pairs (the cross-page relation item is unchanged).
Paid calls happen only in `run`, which Simone launches. Output folder: repilot-r9/.

Modes: prepare (free: generate r9 files, write sample.json) | dry-run (free) | run (paid) | report (free)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import repilot_v27 as rp  # noqa: E402

CANDIDATE = Path("C:/Users/spaci/worktrees/G3O-rcd007/planning/t010/candidate-r9/codebook-r9-signoff.yaml")
CANDIDATE_SHA = "f667b063d526d22311ffc328faa88121555da318bbd5580a6237f9c8b89e3b8b"
V27_DIR = rp.OUT_DIR
OUT = Path("H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/repilot-r9")
GEN_ROOT = OUT / "generated-root"
SIGNED_Q = rp.GEN / "jev_questions.json"
CAP_USD = 3.00
ENTAIL_MAP = {f: f"core.{f}" for f in ["activity_type", "adoption_stage", "deployment_mode", "target_users",
                                         "has_human_oversight", "has_transparency_notice", "has_data_classification",
                                         "has_risk_assessment", "year_announced"]}


def sha256(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def items_by_id():
    cb = yaml.safe_load(CANDIDATE.read_text(encoding="utf-8"))
    items = cb["items"]
    return items if isinstance(items, dict) else {it["id"]: it for it in items}


def cmd_prepare(_a):
    if sha256(CANDIDATE) != CANDIDATE_SHA:
        sys.exit("candidate hash differs from the approved clean copy's; stop")
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "g3o.codebook", "--codebook", str(CANDIDATE), "--repo-root", str(GEN_ROOT),
                    "generate"], cwd=str(CANDIDATE.parents[3]), check=True)
    v27 = json.loads((V27_DIR / "sample.json").read_text(encoding="utf-8"))
    conf = set()
    for line in (V27_DIR / "answers-t016.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        for p in r.get("parts", []):
            v = p["answers"].get("core.page_verdict")
            if v and v["choice"] == "confirms_activity":
                conf.add((r["info"]["page"], r["info"]["chunk"]))
    long_pages = {p["member"] for p in v27["pages"] if p["stratum"] == "long"}
    keep_pages = long_pages | {pg for pg, _ in conf}
    sample = {"seed": v27["seed"], "from": "repilot-v27/sample.json", "confirms_activity_parts": sorted(map(list, conf)),
              "pages": [p for p in v27["pages"] if p["member"] in keep_pages], "entailment": v27["entailment"],
              "pairs": []}
    (OUT / "sample.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
    print("pages", len(sample["pages"]), "long", len(long_pages), "confirms_activity parts", len(conf))


def generated():
    gen_dir = GEN_ROOT / "g3o" / "codebook" / "generated"
    rp.GEN = gen_dir
    qs, sys_prompt, sys6 = rp.load_generated()
    signed = {q["question_id"]: q for q in json.loads(SIGNED_Q.read_text(encoding="utf-8"))["questions"]}
    seen = ("instructions", "criteria")  # what jev is sent; item_hash changes with every release
    changed = [q for q in qs["questions"]
               if {f: q.get(f) for f in seen} != {f: signed.get(q["question_id"], {}).get(f) for f in seen}]
    return {**qs, "questions": changed}, sys_prompt, sys6


def entail_units(sample, sys_prompt, qe, items):
    dropped = Counter()
    for j, e in enumerate(sample["entailment"]):
        qid = ENTAIL_MAP.get(e["field"])
        it = items.get(qid)
        if not it:
            dropped[f'{e["field"]}: no v2.7 item'] += 1
            continue
        if "year" in e["field"]:
            vlabel = e["value"] if e["value"].isdigit() else None
        else:
            vals = {v["code"]: v for v in it.get("values") or [] if isinstance(v, dict)}
            vlabel = vals.get(e["value"], {}).get("entailment_label", {}).get("text")
        if not vlabel:
            dropped[f'{e["field"]}: value not a v2.7 code'] += 1
            continue
        instr = (qe["instructions"].replace("<field label>", it["entailment_label"]["text"])
                 .replace("<activity name>", e["activity_name"]).replace("<value label>", vlabel))
        state = {"coder_instructions": sys_prompt, "text": e["quote"]}
        req = {"core.support_entailment": {"instructions": instr, "criteria": rp.criteria_of(qe)}}
        yield (f"entail|{j}", state, req, {"unit": "entailment", "field": e["field"], "item": qid,
               "value": e["value"], "est_tokens": rp.est_tokens(json.dumps([state, req], ensure_ascii=False))})
    print("entailment dropped:", dict(dropped), file=sys.stderr)


def all_units():
    sample = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))
    qs, sys_prompt, sys6 = gen = generated()
    conf = {tuple(x) for x in sample["confirms_activity_parts"]}
    long_pages = {p["member"] for p in sample["pages"] if p["stratum"] == "long"}
    meta = rp.institution_meta()
    for key, state, req, info in rp.page_units(sample, meta, gen):
        if info["page"] in long_pages or (info["page"], info["chunk"]) in conf:
            yield key, state, req, info
    full = json.loads((GEN_ROOT / "g3o/codebook/generated/jev_questions.json").read_text(encoding="utf-8"))
    qe = next(q for q in full["questions"] if q["question_id"] == "core.support_entailment")
    yield from entail_units(sample, sys_prompt, qe, items_by_id())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prepare", "dry-run", "run", "report"])
    ap.add_argument("--cap-usd", type=float, default=CAP_USD)
    a = ap.parse_args()
    if a.cap_usd > CAP_USD:
        sys.exit(f"--cap-usd above ${CAP_USD:.2f} is not allowed")
    if a.mode == "prepare":
        return cmd_prepare(a)
    rp.OUT_DIR, rp.CAP_USD, rp.all_units = OUT, CAP_USD, all_units  # answers/report files land in repilot-r9/
    {"dry-run": rp.cmd_dry_run, "run": rp.cmd_run, "report": rp.cmd_report}[a.mode](a)


if __name__ == "__main__":
    main()
