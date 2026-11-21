"""T-016 rerun of the five items revised after the r9 rerun (RC-D-007 candidate r10, unsigned).

PI ruling 2026-10-31 (chat): "1b 2a" (revise target_users, deployment_mode and the three year items, then rerun
only those five). Same 315 page parts as rerun_r9 (68 confirms_activity parts + every part of the 50 long pages);
questions are those whose sent text differs from the r9 candidate's; no entailment units (C7 accepted as is, 2 a).
Paid calls happen only in `run`, which Simone launches. Output folder: repilot-r10/.

Modes: prepare (free) | dry-run (free) | run (paid) | report (free)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import repilot_v27 as rp  # noqa: E402
import rerun_r9 as r9  # noqa: E402

CANDIDATE = Path("C:/Users/spaci/worktrees/G3O-rcd007/planning/t010/candidate-r10/codebook-r10-signoff.yaml")
CANDIDATE_SHA = "5f5d1b1fc6ca48d70fbbdb9ebe9c01d4f7829f1e3d60f3386021e03db54c53df"
OUT = Path("H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/repilot-r10")
GEN_ROOT = OUT / "generated-root"
R9_Q = r9.GEN_ROOT / "g3o" / "codebook" / "generated" / "jev_questions.json"
CAP_USD = 1.00


def cmd_prepare(_a):
    if r9.sha256(CANDIDATE) != CANDIDATE_SHA:
        sys.exit("candidate hash differs from the r10 sign-off build; stop")
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "g3o.codebook", "--codebook", str(CANDIDATE), "--repo-root", str(GEN_ROOT),
                    "generate"], cwd=str(CANDIDATE.parents[3]), check=True)
    (OUT / "sample.json").write_bytes((r9.OUT / "sample.json").read_bytes())
    print("sample copied from repilot-r9/")


def generated():
    rp.GEN = GEN_ROOT / "g3o" / "codebook" / "generated"
    qs, sys_prompt, sys6 = rp.load_generated()
    prev = {q["question_id"]: q for q in json.loads(R9_Q.read_text(encoding="utf-8"))["questions"]}
    seen = ("instructions", "criteria")
    changed = [q for q in qs["questions"]
               if {f: q.get(f) for f in seen} != {f: prev.get(q["question_id"], {}).get(f) for f in seen}]
    print("changed questions:", [q["question_id"] for q in changed], file=sys.stderr)
    return {**qs, "questions": changed}, sys_prompt, sys6


def all_units():
    sample = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))
    gen = generated()
    conf = {tuple(x) for x in sample["confirms_activity_parts"]}
    long_pages = {p["member"] for p in sample["pages"] if p["stratum"] == "long"}
    for key, state, req, info in rp.page_units(sample, rp.institution_meta(), gen):
        if info["page"] in long_pages or (info["page"], info["chunk"]) in conf:
            yield key, state, req, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prepare", "dry-run", "run", "report"])
    ap.add_argument("--cap-usd", type=float, default=CAP_USD)
    a = ap.parse_args()
    if a.cap_usd > CAP_USD:
        sys.exit(f"--cap-usd above ${CAP_USD:.2f} is not allowed")
    if a.mode == "prepare":
        return cmd_prepare(a)
    rp.OUT_DIR, rp.CAP_USD, rp.all_units = OUT, CAP_USD, all_units
    {"dry-run": rp.cmd_dry_run, "run": rp.cmd_run, "report": rp.cmd_report}[a.mode](a)


if __name__ == "__main__":
    main()
