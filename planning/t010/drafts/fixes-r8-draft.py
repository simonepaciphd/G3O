"""Draft drafts/fixes-r8.json and resolutions-r8.json (RC-D-005, the year-rule cut) from the r7 draft candidate.

Resolver subagent of the plan integrator (Claude Code, claude-opus-5-5), 2026-10-30. PI ruling, chat, 2026-10-30
(t010-rulings.md, last section): "approved and cut" -- the clean copy approved in full, and the words " plus `unknown`"
cut from rule 1 of the three year items, cut-only. Nothing else changes.
Run: python planning/t010/drafts/fixes-r8-draft.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import yaml

T010 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(T010))
from build_skeleton import r5_apply_fix, r5_resolve  # noqa: E402

BASE = T010 / "candidate-r7/codebook-r7-draft.yaml"
raw = BASE.read_bytes()
BASE_SHA = hashlib.sha256(raw).hexdigest()
cb = yaml.safe_load(raw.decode("utf-8"))
CUT = " plus `unknown`"
assert len(CUT) == 15
ORIGIN = 'PI 2026-10-30 "approved and cut"'
FIXES = []
for n, iid in enumerate(("core.year_announced", "core.year_pilot_start", "core.year_production_start"), start=1):
    path = f"items/{iid}/rules/0"
    parent, k = r5_resolve(cb, path)
    before = copy.deepcopy(parent[k])
    assert before["text"].count(CUT) == 1, iid
    after = {**before, "text": before["text"].replace(CUT, ""), "origin": ORIGIN + "; cut from: " + before["origin"],
             "text_before_r8": before["text"], "cut_r8": CUT,
             "cut_by": 'PI 2026-10-30 "approved and cut" (RC-D-005: `unknown` no longer offered, 12 a; cut-only, as in "2a")'}
    f = {"id": f"R8-{n:02d}", "ruling": ORIGIN, "op": "set", "what": f"{iid} rule 1: \" plus `unknown`\" cut (15 characters)",
         "path": path, "before": before, "after": after}
    r5_apply_fix(cb, f, "r5-draft")
    FIXES.append(f)
folds = cb["release"]["folds"]
f = {"id": "R8-04", "ruling": ORIGIN, "op": "add", "what": "release.folds.r8 (provenance)", "path": "release/folds/r8",
     "after": 'planning/t010/drafts/fixes-r8.json: " plus `unknown`" cut from rule 1 of the three year items '
              '(PI 2026-10-30 "approved and cut"); clean copy planning/t010/RC-D-005-clean-copy.md approved'}
assert "r8" not in folds
r5_apply_fix(cb, f, "r5-draft")
FIXES.append(f)
out = {"format": "fixes-r8 v1: entries applied in order after fixes-r5, -r6 and -r7 by build_skeleton.py apply_r8()",
       "status": "PI-approved cut (2026-10-30, \"approved and cut\")",
       "drafted_by": "resolver subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30",
       "ruling": 'PI, chat, 2026-10-30 (t010-rulings.md): "approved and cut"',
       "base": "planning/t010/candidate-r7/codebook-r7-draft.yaml", "base_sha256": BASE_SHA, "cut": CUT,
       "slots": [x["path"] for x in FIXES[:3]], "provenance_paths": ["release/folds/r8"], "fixes": FIXES}
(T010 / "drafts/fixes-r8.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
res = {"format": "resolutions-r8 v1", "drafted_by": out["drafted_by"], "ruling": out["ruling"],
       "question": "Rule 1 of year_announced, year_pilot_start and year_production_start reads \"jev Choice over those "
                   "years plus `unknown`\" although `unknown` is no longer offered (round 2, point 1)",
       "recommendation": "cut \" plus `unknown`\", cut-only (as in \"2a\")", "pi_choice": "approved and cut",
       "resolutions": [{"item": x["path"].split("/")[1], "path": x["path"], "origin": ORIGIN,
                        "text_before": x["before"]["text"], "text_after": x["after"]["text"]} for x in FIXES[:3]],
       "clean_copy": 'approved in full (PI 2026-10-30 "approved and cut"), incl. template amendments D1-D8'}
(T010 / "drafts/resolutions-r8.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(FIXES), "entries; base", BASE_SHA[:12])
