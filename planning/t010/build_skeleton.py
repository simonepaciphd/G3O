"""Build the T-010 codebook skeleton (draft) from the ruling records and source texts.

Integrator tool (T-010, RC-D-002). Every slot text is copied programmatically from a named source and
asserted to occur verbatim there; nothing is retyped. Output: codebook/codebook.yaml in the T-010 worktree.
Run: python build_skeleton.py [--build signed-2.7|r5-draft|r5-signoff] [--out PATH]

Builds (added for RC-D-005, 2026-10-30):
  --build signed-2.7   (default) the signed release 2.7 as signed on 2026-10-30, sha256 d24bbc7c...0764
                       (planning/t010/signoff-record.md); default out codebook/codebook.yaml.
  --build r5-draft     the RC-D-005 candidate: the signed build with the fixes in drafts/fixes-r5.json applied,
                       `release.status: draft`, item statuses unchanged. Default out planning/t010/candidate-r5/.
  --build r5-signoff   the same candidate as the sign-off build: `release.status: signed` and `status: signed` on
                       every build-scope (core) item (RC-D-005 ruling 2 a). It is signed only once the signature
                       record holds its sha256.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml

# RC-D-005 (2026-10-30): PLAN, WT and REPO are this checkout (the tree holding this file), not fixed paths into other
# worktrees, so a build never reads or writes another tree. Before RC-D-005 they were C:/Users/spaci/repos/G3O/planning,
# C:/Users/spaci/worktrees/G3O-integrator and C:/Users/spaci/repos/G3O.
ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "planning"
WT = ROOT
DRIVE = Path("H:/My Drive/Research/G3O")
SRC = {
    "spec": PLAN / "SPEC.md",
    "delta": PLAN / "deltas/RC-D-002.md",
    "r1": PLAN / "t010/codebook-review/codebook-rulings-round1.json",
    "r2": PLAN / "t010/codebook-review/codebook-rulings-round2.json",
    "cx": DRIVE / "archive/planning-drive-copy-superseded-2026-10-26/launch-analysis-pr/index-design/codebook-extension-proposal.md",
    "repilot": DRIVE / "agent-workspace/2026-10-27-unclear-screen/unclear2.py",
    "v25": WT / "g3o/extract/prompts/output_contract.md",
    "v25sys": WT / "g3o/extract/prompts/system_prompt.md",
}
MARK_SPEC = "SPEC text — PI to write or line-edit"
MARK_V25 = "v2.5 text — affected by {r}; PI to rewrite or delete"
MARK_CX = "CX-01.2 text, byte-identical — PI to re-sign as CX-01.3 (r2#3); direction attached"
MARK_NONE = "no approved wording — PI to write"

TEXT = {k: p.read_text(encoding="utf-8") for k, p in SRC.items() if p.suffix != ".json"}
# --spec-rev REV reads SPEC.md from a git revision instead of the working file (default: the working file).
# Added 2026-10-30; SPEC slot anchors are cut against the working SPEC.md v001.7 (use --spec-rev 1b319f5 only to reproduce v001.6).
import sys as _sys
SPEC_REV = _sys.argv[_sys.argv.index("--spec-rev") + 1] if "--spec-rev" in _sys.argv else None
if SPEC_REV:
    TEXT["spec"] = subprocess.run(["git", "-C", str(PLAN.parent), "show", f"{SPEC_REV}:planning/SPEC.md"],
                                  capture_output=True, check=True).stdout.decode("utf-8").replace(chr(13) + chr(10), chr(10))
R1 = {x["id"]: x for x in json.loads(SRC["r1"].read_text(encoding="utf-8"))["items"]}
R2 = {x["n"]: x for x in json.loads(SRC["r2"].read_text(encoding="utf-8"))["items"]}

# ---------------------------------------------------------------- round-3 sources (fold, 2026-10-29)
R3DIR = PLAN / "t010/codebook-review/round3"
DRAFTS = PLAN / "t010/drafts"
FOLD_LOG = PLAN / "t010/fold-log-round3.md"
REPO = ROOT
R3FILE = json.loads((R3DIR / "codebook-rulings-round3.json").read_text(encoding="utf-8"))
R3 = {x["id"]: x for x in R3FILE["items"]}
Q3 = {x["id"]: x for x in json.loads((R3DIR / "questions-r3.json").read_text(encoding="utf-8"))["items"]}
SMAP = json.loads((R3DIR / "questions-r3-sourcemap.json").read_text(encoding="utf-8"))["items"]
DFILE = {"applic": "applicability.json", "values": "value-lists.json", "comb": "combining-rules.json", "cx": "cx-01.3-draft.json"}
DRAFT = {k: json.loads((DRAFTS / f).read_text(encoding="utf-8")) for k, f in DFILE.items()}
MARK_AGENT = "Agent draft — PI to write or line-edit"
MARK_R3 = "round-3 ruling option text — PI to write or line-edit"
RESPELL = ("discontinued_uncertain", "discontinuation_uncertain")  # all-11 approve: the first spelling is adopted
R3_USED: set = set()
CXROW = {r["cx_row"]: r for r in DRAFT["cx"]["rows"]}
CXD_BY_LINE = {r["frozen_text"]: r for r in DRAFT["cx"]["rows"] if r["frozen_text"]}

# ---------------------------------------------------------------- final sign-off sources (PI, chat, 2026-10-30: "all accepted")
FO_FILE = DRAFTS / "final-open.json"
FO = json.loads(FO_FILE.read_text(encoding="utf-8"))
FO_CH = {c["id"]: c for c in FO["choices"]}
FO_W = {w["id"]: w for w in FO["sentences"]}
D3_FILE = PLAN / "deltas/RC-D-003.md"
D3 = D3_FILE.read_text(encoding="utf-8")
ORIGIN_FINAL = 'PI 2026-10-30 "all accepted"'
MARK_FINAL = "PI-approved text (2026-10-30, \"all accepted\") — PI to write or line-edit"
P2_CLAUSE = ", or not asked where CX-51 says so"   # C P2: stale CX-50 clause removed (W03 removed what it pointed to)


def r3choices(rid: str) -> list:
    ch = R3[rid]["choice"]
    return ch if isinstance(ch, list) else [ch.split(",")[0].strip()]


def _cx_row_rulings() -> dict:
    """Round-3 ids per CX-01.3 draft row: the row headings in each question body, plus the sourcemap's mentions."""
    out: dict = {}

    def add(row, qid):
        if qid not in out.setdefault(row, []):
            out[row].append(qid)
    for qid, q in Q3.items():
        for h in re.findall(r"^\*\*(.+?)\*\*", q.get("body") or "", re.M):
            if h in CXROW and qid in R3:
                add(h, qid)
    for qid, ents in SMAP.items():
        for e in ents:
            if not e["file"].startswith("cx-01.3-draft"):
                continue
            for s in e["entries"]:
                for cx in re.findall(r"CX-\d+[a-z]?(?![\d.])", s):
                    if cx in CXROW:
                        add(cx, qid)
                for ln in re.findall(r"\bL(\d+)\b", s):
                    for r in CXROW:
                        if r.startswith(f"pilot.py L{ln} ") or r.startswith(f"pilot.py L{ln}-"):
                            add(r, qid)
    return out


CX_ROW_RULINGS = _cx_row_rulings()


def respell(text: str):
    if RESPELL[0] in text:
        return text.replace(*RESPELL), f"respelled `{RESPELL[0]}` -> `{RESPELL[1]}` (all-11 approve, first spelling)"
    return text, None


def cxd_slot(row: dict, text: str, frozen_text, frozen_source) -> dict:
    """A CX-01.3 draft text slot; the frozen CX-01.2 text stays beside it for the PI's line-edit and re-signature."""
    assert text in row["draft_text"], row["cx_row"]
    t, tr = respell(text)
    rulings = CX_ROW_RULINGS.get(row["cx_row"], [])
    R3_USED.update(rulings)
    d = {"text": t, "origin": "agent-draft",
         "source": f"cx-01.3-draft.json {row['cx_row']}; ruling {', '.join(rulings) if rulings else 'none (no round-3 item names this row)'}",
         "marker": MARK_AGENT, "draft_action": row["action"], "frozen_text": frozen_text, "frozen_source": frozen_source}
    if tr:
        d["transform"] = tr
        R3_USED.add("all-11")
    return d


def _line_of(key: str, s: str) -> int:
    i = TEXT[key].find(s)
    return TEXT[key].count("\n", 0, i) + 1


def spec_row(rid: str) -> str:
    m = re.search(rf"^\| {re.escape(rid)} \| (.*?) \| ", TEXT["spec"], re.M)
    assert m, rid
    return m.group(1)


def cut(s: str, start: str | None, end: str | None) -> str:
    """Return s from start through end inclusive (whole s when both are None); each anchor must be unique."""
    a = 0
    if start is not None:
        assert s.count(start) == 1, f"start not unique/absent: {start[:50]!r}"
        a = s.index(start)
    b = len(s)
    if end is not None:
        assert s.count(end, a) >= 1, f"end absent: {end[:50]!r}"
        b = s.index(end, a) + len(end)
    return s[a:b]


def slot(kind, ref, start=None, end=None, field="mechanism", marker=None):
    """A text slot seeded verbatim from a source. kind: spec | delta | r1 | r2 | cx | repilot | v25 | v25sys | none."""
    if kind == "none":
        return {"text": None, "origin": "none", "source": ref, "marker": MARK_NONE}
    if kind == "spec":
        base, src = spec_row(ref), f"SPEC.md:{_line_of('spec', '| ' + ref + ' |')} {ref}"
    elif kind == "r1":
        item = R1[ref]
        base = item["chosen"][field] if field in item["chosen"] else item[field]
        src = f"codebook-rulings-round1.json {ref}.{field}"
    elif kind == "r2":
        base, src = R2[ref][field if field != "mechanism" else "means"], f"codebook-rulings-round2.json n={ref}"
    elif kind == "cx":
        m = (re.search(rf"^\| {re.escape(ref)}(?: [^|]*?)? \| (.*?) \| (.*?) \|$", TEXT["cx"], re.M)
             or re.search(rf"^\| {re.escape(ref)}(?: [^|]*?)?() \| (.*?) \|$", TEXT["cx"], re.M))
        assert m, ref
        base = m.group(2)
        src = f"codebook-extension-proposal.md:{_line_of('cx', m.group(0))} {ref}"
        marker = marker or MARK_CX
        frozen = cut(base, start, end)
        row = CXD_BY_LINE.get(m.group(0))
        assert row, f"no CX-01.3 draft row whose frozen_text is the CX-01.2 line of {ref}"
        dm = (re.search(rf"^\| {re.escape(ref)}(?: [^|]*?)? \| (.*?) \| (.*?) \|$", row["draft_text"], re.M)
              or re.search(rf"^\| {re.escape(ref)}(?: [^|]*?)?() \| (.*?) \|$", row["draft_text"], re.M))
        assert dm, ref
        return cxd_slot(row, cut(dm.group(2), start, end) if row["action"] == "no_change" else dm.group(2), frozen, src)
    elif kind == "repilot":
        tree = ast.parse(TEXT["repilot"])
        verdict = next(n.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "VERDICT")
        base = ast.literal_eval(verdict)[ref]
        src = f"unclear2.py VERDICT[{ref!r}] (L32-54)"
    elif kind in ("v25", "v25sys", "delta", "cxraw"):
        k = "cx" if kind == "cxraw" else kind
        base, src = TEXT[k], f"{SRC[k].name}"
        marker = marker or (MARK_CX if kind == "cxraw" else None)
    elif kind == "repilot_q":
        tree = ast.parse(TEXT["repilot"])
        base = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith(ref))
        src = "unclear2.py L84-85 (verdict question instructions)"
    else:
        raise ValueError(kind)
    text = cut(base, start, end)
    if kind in ("v25", "v25sys", "delta", "cxraw"):
        src += f":{_line_of('cx' if kind == 'cxraw' else kind, text)}"
    assert text and text in base
    if kind == "cxraw":
        rows = [r for r in DRAFT["cx"]["rows"] if r["frozen_text"] and text in r["frozen_text"] and r["frozen_text"] in TEXT["cx"]]
        assert len(rows) == 1, (text[:40], [r["cx_row"] for r in rows])
        row = rows[0]
        return cxd_slot(row, cut(row["draft_text"], start, end), text, src)
    return {"text": text, "origin": kind, "source": src, "marker": marker or MARK_SPEC}


def v25cell(column: str, value: str) -> dict:
    """Definition cell of a v2.5 vocabulary table row `| `value` | definition | ...`."""
    seg = TEXT["v25"][TEXT["v25"].index("## 4. Controlled vocabularies") :]
    seg = seg[seg.index(f"`{column}`\n") :]
    m = re.search(rf"^\| `{re.escape(value)}` \| (.*?) \|", seg, re.M)
    assert m, (column, value)
    return {"text": m.group(1), "origin": "v25", "source": f"output_contract.md:{_line_of('v25', m.group(0))} §4 {column}",
            "marker": MARK_V25.format(r="R-0xx (see refs)")}


def v25desc(column: str) -> dict:
    m = re.search(rf"^\| \d+ \| `{re.escape(column)}` \| [^|]+ \| [^|]+ \| (.*?) \|$", TEXT["v25"], re.M)
    assert m, column
    return {"text": m.group(1), "origin": "v25", "source": f"output_contract.md:{_line_of('v25', m.group(0))} col {column}",
            "marker": MARK_V25.format(r="R-0xx (see refs)")}


def vals(*pairs):
    """[(code, slot-or-None)]; None -> no approved wording."""
    return [{"code": c, "definition": d if d is not None else slot("none", f"value {c}")} for c, d in pairs]


O = "open"  # field value not yet ruled; listed in the open-items table
WEB, S6, PROC, TXT = "web_extract", "stage6", "procurement", "ai_text"
DEFAULTS = dict(pipelines=[WEB], linkage="jev_choice", coder="classifier", gate="none", answer_type="single",
                rules="none", order_tie_rule="first_in_order", long_page_rule=O, support_required=True,
                downgrade_target="unknown", threshold={"metric": "chosen_answer_probability", "bar": 0.8},
                missing_tokens=["not_asked", "not_documented", "unknown"], input_text="main", visibility="public",
                frozen_signature="none", version_introduced=O, translation_v25="new", status="slot")
MECH = dict(linkage="deterministic", coder="mechanical", pass_="none", round_="none", threshold="none",
            support_required=False, downgrade_target="none", order_tie_rule="none", long_page_rule="none",
            values="none", instruction=None)
DERIVED = dict(MECH, coder="derived")
GATE_GENAI5 = {"item": "core.page_verdict", "values": ["confirms_activity", "ambiguous_genai", "ambiguous_attribution", "other_body", "event_only"]}
GATE_APPLIC = {"table": "applicability keyed on activity_type (r2#8)", "rows": O}
GATE_GOV = {"item": "core.action_type", "values": ["governance"]}
YESNO = ["yes", "no"]
SAFE4 = ["yes", "no", "not_documented", "unclear"]


def item(id_, family, name, level, pass_, round_, instruction, values, refs, **kw):
    d = dict(DEFAULTS)
    d.update(kw)
    p = d.pop("pass_", pass_)
    r = d.pop("round_", round_)
    if "instruction" in kw:
        instruction = d.pop("instruction")
    if "values" in kw:
        values = d.pop("values")
    out = {"id": id_, "family": family, "name": name, "level": level if isinstance(level, list) else [level],
           "pipelines": d["pipelines"], "linkage": d["linkage"], "coder": d["coder"], "pass": p, "round": r,
           "gate": d["gate"], "answer_type": d["answer_type"],
           "instruction": instruction if instruction is not None else "none",
           "values": values, "rules": d["rules"], "order_tie_rule": d["order_tie_rule"],
           "long_page_rule": d["long_page_rule"], "support_required": d["support_required"],
           "downgrade_target": d["downgrade_target"], "threshold": d["threshold"],
           "missing_tokens": d["missing_tokens"], "input_text": d["input_text"], "visibility": d["visibility"],
           "frozen_signature": d["frozen_signature"], "version_introduced": d["version_introduced"],
           "translation_v25": d["translation_v25"], "refs": refs, "status": d["status"]}
    return out


def mech(id_, family, name, level, rules, refs, **kw):
    base = dict(MECH)
    base.update(kw)
    base.setdefault("answer_type", "text")
    p, r = base.pop("pass_"), base.pop("round_")
    return item(id_, family, name, level, p, r, None, "none", refs, rules=rules, **{k: v for k, v in base.items() if k not in ("values", "instruction")})


def derived(id_, family, name, level, rules, refs, **kw):
    return mech(id_, family, name, level, rules, refs, coder="derived", **kw)


def cx_slots(ids):
    return [slot("cx", i) for i in ids]


def direction(xid):
    """Round-1 ruled direction for a CX item (r2#3: choices are direction for the CX-01.3 text)."""
    return {**slot("r1", xid, field="mechanism", marker="direction for CX-01.3, not signed wording"), "role": "direction"}


ITEMS = []
A = ITEMS.append

# ---------------------------------------------------------------- shared rules
SHARED = {
    "core.rule.genai_boundary": [slot("spec", "R-016", "Generative-AI wording:", "for that naming."),
                                 slot("delta", None, "S1 a: translation counts", "a language model produces it.")],
    "core.rule.activity_unit": [slot("spec", "R-017", "One activity = one action", 'linked by a "governs" relation.')],
    "core.rule.ws10_event": [slot("spec", "R-010")],
    "core.rule.ws10_governance": [slot("spec", "R-011")],
    "core.rule.ws10_excluded_only": [slot("spec", "R-012")],
    "core.rule.ws10_proposals": [slot("spec", "R-013")],
    "core.rule.attribution_grain": [slot("r1", "C04", "An activity carried out by", "takes part."),
                                    slot("r1", "C04", "A joint activity counts", "as a participant.")],
    "core.rule.v26_detail_fields": [slot("spec", "R-014", "v2.6 rules:", "institution-wide `no`.")],
    "core.rule.safeguard_attachment": [slot("r1", "C18", "A safeguard in a governance activity", "a recorded relation.")],
    "core.rule.stated_only": [v25desc("reported_outcomes")],
    "core.rule.cx_grain": cx_slots(["CX-01", "CX-02", "CX-03", "CX-04", "CX-05"]),
}

# ---------------------------------------------------------------- pass 1: page
A(item("core.page_verdict", "verdict", "page_verdict", "page", 1, 1,
       slot("repilot_q", "Code this PAGE"),
       vals(("confirms_activity", slot("repilot", "confirms_activity")),
            ("ambiguous_genai", slot("repilot", "ambiguous_genai")),
            ("ambiguous_attribution", slot("repilot", "ambiguous_attribution")),
            ("other_body", slot("repilot", "other_body")),
            ("event_only", slot("repilot", "event_only")),
            ("background_only", slot("repilot", "background_only")),
            ("confirms_absence", slot("spec", "R-015", "v2.5 `confirms_absence` (page states absence;", "no relevant content)")),
            ("no_genai", slot("repilot", "no_genai")),
            ("not_assessable", slot("spec", "R-015", "`not_assessable`, set mechanically", "out of the base for institution-level rates"))),
       ["R-015", "R-016", "C01", "r2#1", "r2#7", "r2#40", "C1 a", "S3 a"],
       rules=[slot("spec", "R-015"), "core.rule.genai_boundary", "core.rule.ws10_event", "core.rule.attribution_grain"],
       long_page_rule={"rule": "priority_order", "order": "S3 a", "text": slot("spec", "R-044", "The verdict order for combining long-page parts has two tiers:", "for completeness only, C1 a).")},
       downgrade_target="tag_only", missing_tokens=["not_assessable (mechanical)"],
       translation_v25={"column": "genai_evidence", "map": O, "unmappable": O}))

A(item("core.disclosure_form", "disclosure", "disclosure_form", "page", 1, 2,
       slot("cxraw", None, "What kind of document is this page?", "this page?"),
       vals(("register_cross_institution", slot("cx", "CX-10")), ("register_single_institution", slot("cx", "CX-10b")),
            ("mandated_report", slot("cx", "CX-12")), ("formal_record", slot("cx", "CX-14")),
            ("informal_official", slot("cx", "CX-15")), ("third_party", slot("cx", "CX-16")), ("unknown", slot("cx", "CX-17"))),
       ["R-020", "X01", "CX-10..CX-18"], frozen_signature="CX-01.2:CX-10..CX-18 (re-sign as CX-01.3)",
       rules=cx_slots(["CX-11", "CX-13", "CX-18"]) + [direction("X01")], long_page_rule="first_section", status="slot",
       gate="none"))
A(item("core.disclosure_scope", "disclosure", "disclosure_scope", "page", 1, 3,
       None, vals(("whole_of_government", slot("cx", "CX-21")), ("multi_institution", slot("cx", "CX-22")),
                  ("single_institution", slot("cx", "CX-23")), ("unknown", slot("cx", "CX-24"))),
       ["R-021", "X02", "CX-20..CX-25"], frozen_signature="CX-01.2:CX-20..CX-25 (re-sign as CX-01.3)",
       gate={"item": "core.disclosure_form", "values": ["register_cross_institution", "register_single_institution", "mandated_report"], "source": "X02"},
       rules=cx_slots(["CX-20", "CX-25"]) + [direction("X02")], long_page_rule="first_section"))
A(item("core.page_complete", "completeness", "page_complete", "page", 1, 2,
       slot("r1", "X17", "'Does the page refer", "it mentions?'"), vals(("yes", None), ("no", None)),
       ["R-030", "X17", "RC-D-002 row 13"], gate=GATE_GENAI5, answer_type="yes_no",
       rules=[slot("spec", "R-030")], long_page_rule="any_yes", pipelines=[WEB], input_text="main"))
A(item("core.source_type", "source", "source_type", "source", 1, 2, None,
       vals(*[(c, v25cell("source_type", c)) for c in ["news_major", "news_trade", "vendor", "academic", "policy_org", "social_media", "procurement_tender", "other"]]),
       ["X21", "r2#25", "r2#30", "R-002"], pipelines=[WEB, PROC, TXT],
       rules=[slot("r2", 25), slot("r2", 30)], gate={"rule": "only pages not typed automatically from domain or address (r2#25)"},
       translation_v25={"column": "source_type", "map": O}))
A(item("core.content_contact_named", "disclosure", "content_contact_named", "page", 1, 2, None, vals(("yes", None), ("no", None)),
       ["R-023", "X06", "CX-51"], frozen_signature="CX-01.2:CX-51 (re-sign as CX-01.3)", answer_type="yes_no",
       rules=cx_slots(["CX-51"]) + [direction("X06")], long_page_rule="any_yes", input_text="main_plus_chrome", gate="F07"))
A(item("core.content_contact_details", "disclosure", "content_contact_details", "page", 1, 2, None, vals(("yes", None), ("no", None)),
       ["R-023", "X06", "CX-51", "r2#48"], frozen_signature="CX-01.2:CX-51 (re-sign as CX-01.3)", answer_type="yes_no",
       rules=cx_slots(["CX-51"]) + [direction("X06")], long_page_rule="any_yes", input_text="main_plus_chrome", gate="F07"))
A(derived("core.content_contact", "disclosure", "content_contact", "page",
          cx_slots(["CX-51"]), ["CX-51", "R-023"], answer_type="yes_no", frozen_signature="CX-01.2:CX-51 (re-sign as CX-01.3)"))
A(mech("core.content_contact_emails", "disclosure", "content_contact_emails", "page",
       [slot("cx", "CX-53", marker=MARK_CX), slot("spec", "R-058"), direction("X08")],
       ["R-023", "R-058", "X08", "CX-53", "S4 a", "r2#48"], answer_type="list", input_text="main_plus_chrome",
       visibility="public_derived", gate={"item": "core.content_contact", "values": ["yes"]},
       frozen_signature="CX-01.2:CX-53 (re-sign as CX-01.3)"))
for nm in ["purpose", "tool_or_model", "vendor", "data", "users", "status_date"]:
    A(derived(f"core.content_{nm}", "disclosure", f"content_{nm}", "page",
                            cx_slots(["CX-50", "CX-51"]) + [slot("r2", 19), direction("X05")], ["R-023", "X05", "CX-51", "r2#19"],
                            answer_type="yes_no", frozen_signature="CX-01.2:CX-51 (re-sign as CX-01.3)"))
for nm in ["human_oversight", "risk_assessment", "user_notification"]:
    A(derived(f"core.content_{nm}", "safeguard", f"content_{nm}", "page",
              cx_slots(["CX-52"]) + [slot("r2", 10), direction("X07")], ["R-023", "X07", "CX-52", "r2#10", "r2#29"],
              answer_type="yes_no", frozen_signature="CX-01.2:CX-52 (re-sign as CX-01.3)"))

# ---------------------------------------------------------------- source-level deterministic fields
SRC_MECH = [
    ("core.source_url", "source_url", [v25desc("source_url"), slot("r1", "X28")], ["X28"], {"column": "source_url", "map": "identity"}),
    ("core.source_title", "source_title", [slot("r1", "X28")], ["X28"], {"column": "source_title", "map": O}),
    ("core.source_access_date", "source_access_date", [v25desc("source_access_date"), slot("r1", "X28")], ["X28"], {"column": "source_access_date", "map": "identity"}),
    ("core.source_language", "source_language", [slot("r1", "X27")], ["X27"], {"column": "source_language", "map": O}),
    ("core.source_on_official_domain", "source_on_official_domain", [slot("r1", "X37")], ["X37"], "new"),
    ("core.syndication_group", "syndication_group", [slot("r1", "X38")], ["X38"], "new"),
    ("core.page_review_state", "page_review_state", [slot("r1", "X39"), slot("r2", 7)], ["X39", "r2#7", "R-015"], "new"),
    ("core.discovery_path", "discovery_path", [slot("r1", "X18")], ["X18", "R-034", "R-036"], "new"),
    ("core.text_source", "text_source", [slot("spec", "R-059", "A per-row `text_source`", "chrome text and links (RC-D-002 F).")], ["R-059", "RC-D-002 F"], "new"),
]
for id_, nm, rules, refs, tr in SRC_MECH:
    A(mech(id_, "source", nm, "source", rules, refs, pipelines=[WEB, PROC, TXT] if nm not in ("discovery_path", "text_source") else [WEB],
           translation_v25=tr, input_text="metadata"))
A(item("core.source_publication_date", "source", "source_publication_date", "source", "none", "none", None, "none",
       ["X26", "R-040", "R-042", "r2#31", "T3"], linkage="extractor", coder="quote_step", answer_type="date",
       rules=[slot("r1", "X26"), slot("r2", 31)], threshold="none", order_tie_rule="none", long_page_rule=O,
       input_text="metadata", pipelines=[WEB, PROC, TXT], translation_v25={"column": "source_publication_date", "map": "identity"}))
A(item("core.source_snippet", "source", "source_snippet", "source", "none", "none", None, "none",
       ["X25", "r2#35"], linkage="extractor", coder="quote_step", answer_type="text",
       rules=[slot("r1", "X25"), slot("r2", 35)], threshold="none", order_tie_rule="none", long_page_rule="none",
       pipelines=[WEB, PROC, TXT], translation_v25={"column": "source_snippet", "map": O}))
A(derived("core.source_credibility", "source", "source_credibility", "source", [slot("r1", "X22")], ["X22", "R-090"],
          answer_type="single", pipelines=[WEB, PROC, TXT], translation_v25={"column": "source_credibility", "map": O}))

# ---------------------------------------------------------------- pass 2: activity
A(item("core.activity_segment", "activity_identity", "activity_relation_within_page", "activity", 2, 1,
       slot("r1", "C07", "The extractor proposes spans;", "not an activity."), O,
       ["R-003", "R-017", "C07", "r2#22", "N7"], linkage="extractor",
       rules=["core.rule.activity_unit", slot("spec", "R-017", "One shared relation list", "within a page (r2#22; activity-16 b; all-11).")],
       long_page_rule={"rule": O, "note": slot("spec", "R-044", "with segmentation linking passages", "(r2#42)")}, support_required=True))
A(item("core.activity_name", "activity_identity", "activity_name", "activity", "none", "none", v25desc("activity_name"), "none",
       ["R-006", "C07"], linkage="extractor", coder="quote_step", answer_type="text", threshold="none",
       order_tie_rule="none", long_page_rule="none", translation_v25={"column": "activity_name", "map": "identity"}))
A(item("core.observed_actor_name", "attribution", "observed_actor_name", "activity", "none", "none", None, "none",
       ["A05", "R-014", "r2#23"], linkage="extractor", coder="quote_step", answer_type="text", threshold="none",
       visibility="internal", rules=[slot("r1", "A05")], order_tie_rule="none", long_page_rule="none"))
A(item("core.observed_actor_relationship", "attribution", "observed_actor_relationship", "activity", 2, 2,
       None, O, ["A05", "R-014", "P06", "r2#4", "r2#23", "C04"],
       rules=[slot("spec", "R-014", "RC-D-002 row 7: the observed-actor", "the C04 grain rule is kept."), slot("r2", 4), slot("r2", 23), "core.rule.attribution_grain"]))
A(item("core.activity_type", "activity_typing", "activity_type", "activity", 2, 2, v25desc("activity_type"),
       vals(*[(c, v25cell("activity_type", c)) for c in ["policy_guidance", "pilot_experiment", "program_initiative", "internal_operational", "public_facing_service", "unknown"]]),
       ["C08", "r2#8"], rules=[slot("v25", None, "**Rule: policy vs. pilot.**", "(with their respective sources)."),
                               slot("v25", None, "**Rule: country-wide program.**", "flag `institution_attribution`.")],
       translation_v25={"column": "activity_type", "map": "identity"}))
A(item("core.action_type", "activity_typing", "action_type", "activity", 2, 2, None,
       vals(("deployment", None), ("governance", None), ("staff_training", None), ("program", None), ("unknown", None)),
       ["A02", "r2#11", "T1", "T4"], rules=[slot("r1", "A02"), slot("r2", 11)]))
A(item("core.adoption_stage", "activity_typing", "adoption_stage", "activity", 2, 3, None,
       vals(*[(c, v25cell("adoption_stage", c)) for c in ["proposed", "announced", "pilot", "production", "discontinued", "unknown"]]),
       ["C09", "R-087", "r2#14", "T1", "R-013"], gate=GATE_APPLIC,
       rules=[slot("r1", "C09"), slot("r2", 14), slot("spec", "R-087"), "core.rule.ws10_proposals",
              {**slot("v25", None, '**"Permanent pilot" rule:**', "full user base.\""), "marker": MARK_V25.format(r="r2#28")}],
       long_page_rule={"rule": "priority_order", "order": O}, translation_v25={"column": "adoption_stage", "map": O}))
A(item("core.procurement_status", "activity_typing", "procurement_status", "activity", 2, 3, None,
       vals(("none_documented", None), ("tender_or_rfp", None), ("award_or_contract", None), ("payment_or_subscription", None), ("unknown", None)),
       ["C09", "r2#14", "r2#12"], pipelines=[WEB, PROC], rules=[slot("r1", "C09"), slot("r2", 14)], gate=GATE_APPLIC))
A(item("core.model_origin", "tool", "model_origin", "activity", 2, 3, None,
       vals(("commercial", None), ("open_weight", None), ("government_developed", None), ("unknown", None)),
       ["C10"], rules=[slot("r1", "C10")], gate=GATE_APPLIC, translation_v25={"column": "access_type", "map": O}))
A(item("core.build_arrangement", "tool", "build_arrangement", "activity", 2, 3, None,
       vals(("off_the_shelf_product", None), ("custom_application_on_external_model", None), ("model_trained_or_fine_tuned_by_institution", None), ("unknown", None)),
       ["C10"], rules=[slot("r1", "C10")], gate=GATE_APPLIC, translation_v25={"column": "access_type", "map": O}))
A(item("core.interface", "tool", "interface", "activity", 2, 3, None, O,
       ["C11", "r2#20"], rules=[slot("r1", "C11"), slot("r2", 20)], gate=GATE_APPLIC,
       translation_v25={"column": "interaction_type", "map": O}))
for fn in ["drafting_writing", "summarization", "translation", "search_retrieval", "code", "image_audio_video", "extraction_classification", "analysis_recommendation"]:
    A(item(f"core.function_{fn}", "tool", f"function_{fn}", "activity", 2, 3, None, vals(("yes", None), ("no", None)),
           ["C11"], answer_type="yes_no", rules=[slot("r1", "C11")], gate=GATE_APPLIC, long_page_rule="any_yes",
           translation_v25={"column": "interaction_type", "map": O}))
A(item("core.tool_name", "tool", "tool_name", "activity", "none", "none", v25desc("tool_name"), "none",
       ["C12", "R-006"], linkage="extractor", coder="quote_step", answer_type="list", rules=[slot("r1", "C12")],
       threshold="none", gate=GATE_APPLIC, order_tie_rule="none", long_page_rule="combined_list",
       translation_v25={"column": "tool_name", "map": "identity"}))
A(item("core.model_name", "tool", "model_name", "activity", "none", "none", None, "none",
       ["C12"], linkage="extractor", coder="quote_step", answer_type="list", rules=[slot("r1", "C12")],
       threshold="none", gate=GATE_APPLIC, order_tie_rule="none", long_page_rule="combined_list"))
A(item("core.contracting_party", "tool", "contracting_party", "activity", "none", "none", None, "none",
       ["r2#24", "r2#13", "T5", "P04"], linkage="extractor", coder="quote_step", answer_type="text",
       rules=[slot("r2", 24), slot("r2", 13)], threshold="none", gate=GATE_APPLIC, order_tie_rule="none",
       pipelines=[WEB, PROC], long_page_rule=O, translation_v25={"column": "vendor", "map": O}))
A(item("core.developer", "tool", "developer", "activity", "none", "none", None, "none",
       ["r2#24", "C13", "T5"], linkage="pipeline", coder="derived", answer_type="text",
       rules=[slot("r2", 24), slot("r1", "C13")], threshold="none", gate=GATE_APPLIC, order_tie_rule="none",
       long_page_rule=O, translation_v25={"column": "vendor", "map": O}))
A(mech("core.developer_basis", "provenance", "developer_basis", "activity", [slot("r2", 24), slot("r2", 57)],
       ["r2#24", "r2#57", "T3"], answer_type="single"))
A(item("core.deployment_mode", "tool", "deployment_mode", "activity", 2, 3, v25desc("deployment_mode"),
       vals(("integrated", slot("r1", "C14", "integrated:", "existing website service).")),
            ("standalone", slot("r1", "C14", "standalone:", "for the GenAI tool.")), ("unknown", None)),
       ["C14", "r2#20"], gate=GATE_APPLIC, translation_v25={"column": "deployment_mode", "map": O}))
A(item("core.target_users", "tool", "target_users", "activity", 2, 3, v25desc("target_users"),
       vals(("internal_staff", None), ("public", None), ("both", None), ("unknown", None)),
       ["C15"], rules=[slot("r1", "C15")], gate=GATE_APPLIC, translation_v25={"column": "target_users", "map": "identity"}))
A(item("core.governed_population", "governance", "governed_population", "activity", 2, 3, None,
       vals(("internal_personnel", None), ("external_users", None), ("both", None), ("unknown", None)),
       ["A04", "T4"], rules=[slot("r1", "A04")], gate=GATE_GOV))
A(item("core.governance_form", "governance", "governance_form", "activity", 2, 3, None,
       vals(("dedicated_genai_or_ai_policy_or_guideline", None), ("approved_tool_list_or_endorsement", None), ("clause_in_instrument_on_other_subject", None),
            ("court_or_regulatory_order", None), ("procurement_standard", None), ("unknown", None)),
       ["A03", "S6 c", "r2#29", "T4"], answer_type="multi", order_tie_rule="all_that_apply", gate=GATE_GOV,
       rules=[slot("r1", "A03"), slot("delta", None, "S6 c: `governance_form` becomes multi-select", "and a re-test.")], long_page_rule="combined_list"))
A(item("core.governance_direction", "governance", "governance_direction", "activity", 2, 3, None, O,
       ["r2#58", "T4"], gate=GATE_GOV, rules=[slot("r2", 58)]))
A(item("core.service_domain", "activity_typing", "service_domain", "activity", 2, 3, None, O,
       ["r2#62"], rules=[slot("r2", 62)]))
A(item("core.genai_mechanism_basis", "verdict", "genai_mechanism_basis", "activity", 2, 2, None,
       vals(("named_genai_product_or_model", None), ("explicit_genai_label", None), ("generative_capability_described", None), ("ai_chatbot_or_assistant_label_only", None)),
       ["A01", "C02", "r2#18", "r2#34"], rules=[slot("r1", "A01"), "core.rule.genai_boundary"]))
for nm, ref, tr in [("year_announced", "C16", {"column": "year_announced", "map": "identity"}),
                    ("year_pilot_start", "C17", {"column": "year_deployed", "map": O}),
                    ("year_production_start", "C17", {"column": "year_deployed", "map": O})]:
    A(item(f"core.{nm}", "dates", nm, "activity", 2, 3, slot("r1", "C16", '"In which year', 'first announced?"') if nm == "year_announced" else None,
           {"candidates": "deterministic year extraction, plus unknown (C16)"}, [ref, "r2#50", "O6"],
           rules=[slot("r1", "C16"), slot("r2", 50)] + ([slot("r1", "C17")] if ref == "C17" else []),
           long_page_rule="earliest_year", gate=GATE_APPLIC, answer_type="single", translation_v25=tr))
A(item("core.deployment_scale_number", "scale", "deployment_scale_number", "activity", "none", "none", None, "none",
       ["A09", "C4 a"], linkage="extractor", coder="quote_step", answer_type="number", threshold="none",
       rules=[slot("r1", "A09"), slot("spec", "R-001", "the quote step copies the scale number verbatim", "picks the unit (C4 a)")],
       order_tie_rule="none", long_page_rule=O, gate=GATE_APPLIC))
A(item("core.deployment_scale_unit", "scale", "deployment_scale_unit", "activity", 2, 4, None,
       vals(("licences_or_seats", None), ("users", None), ("interactions", None), ("units_or_departments", None), ("none", None)),
       ["A09", "C4 a"], rules=[slot("r1", "A09")], gate={"item": "core.deployment_scale_number", "values": ["any stated"]}))
for nm, ref in [("human_oversight", "C18"), ("transparency_notice", "C19"), ("data_classification", "C20"), ("risk_assessment", "C21")]:
    A(item(f"core.has_{nm}", "safeguard", f"has_{nm}", "activity", 2, 3, v25desc(f"has_{nm}"),
           vals(*[(c, slot("r1", ref, f"{c}:", "." if c != "unclear" else "applies to this activity.")) for c in SAFE4]),
           [ref, "r2#10", "r2#29", "X07"], rules=["core.rule.safeguard_attachment", slot("r2", 10)], gate=GATE_APPLIC,
           long_page_rule=O, translation_v25={"column": f"has_{nm}", "map": "identity"}))
A(item("core.outcome_kind", "outcomes", "outcome_kind", "activity", 2, 3, None,
       vals(("quantified", None), ("qualitative", None), ("none_reported", None)),
       ["R-024", "CX-61", "X09", "X10", "r2#9", "C22"], frozen_signature="CX-01.2:CX-61 (re-sign as CX-01.3)",
       rules=cx_slots(["CX-61"]) + [direction("X10"), direction("X09"), slot("r2", 9)], gate=GATE_APPLIC,
       translation_v25={"column": "reported_outcomes", "map": O}))
A(item("core.incident_kind", "outcomes", "incident_kind", "activity", 2, 3, None,
       vals(("quantified", None), ("qualitative", None), ("none_reported", None), ("discontinuation_uncertain", None)),
       ["R-024", "CX-61", "X09", "X10", "r2#9", "C2 a", "C23", "r2#38"], frozen_signature="CX-01.2:CX-61 (re-sign as CX-01.3)",
       rules=cx_slots(["CX-61"]) + [direction("X10"), direction("X09"), slot("r2", 9), slot("r2", 38)], gate=GATE_APPLIC,
       translation_v25={"column": "reported_incidents", "map": O}))
for nm, ref in [("reported_outcomes", "C22"), ("reported_incidents", "C23")]:
    A(item(f"core.{nm}", "outcomes", nm, "activity", "none", "none", v25desc(nm), "none",
           [ref, "R-024", "CX-60"], linkage="extractor", coder="quote_step", answer_type="list",
           gate={"item": f"core.{'outcome' if 'outcomes' in nm else 'incident'}_kind", "values": ["not none_reported"]},
           rules=cx_slots(["CX-60"]) + [slot("r1", ref)], threshold="none", order_tie_rule="none", long_page_rule="combined_list",
           frozen_signature="CX-01.2:CX-60 (re-sign as CX-01.3)", translation_v25={"column": nm, "map": O}))
A(item("core.evaluation_documented", "evaluation", "evaluation_documented", ["activity", "page"], 2, 3,
       slot("cxraw", None, "Does this page document an evaluation of this GenAI activity?", "activity?"),
       vals(("results_reported", slot("cx", "CX-30")), ("conducted_no_results", slot("cx", "CX-31")), ("required_or_planned", slot("cx", "CX-32")),
            ("unclear", slot("cx", "CX-33")), ("not_documented", slot("cx", "CX-34"))),
       ["R-022", "X03", "CX-30..CX-40"], frozen_signature="CX-01.2:CX-30..CX-40 (re-sign as CX-01.3)",
       rules=cx_slots(["CX-32b", "CX-32c", "CX-32d", "CX-35", "CX-36", "CX-37", "CX-38", "CX-39", "CX-40"]) + [direction("X03")],
       long_page_rule={"rule": "priority_order", "order": "table order (CX §11.1)"}, gate=GATE_APPLIC))
for et in ["pre_deployment_testing", "pilot_evaluation", "independent_audit", "ongoing_monitoring", "user_feedback", "bias_or_safety_testing"]:
    A(item(f"core.evaluation_type_{et}", "evaluation", f"evaluation_type_{et}", ["activity", "page"], 2, 4, None, vals(("yes", None), ("no", None)),
           ["R-022", "X04", "CX-41"], frozen_signature="CX-01.2:CX-41 (re-sign as CX-01.3)", answer_type="yes_no",
           gate={"item": "core.evaluation_documented", "values": ["results_reported", "conducted_no_results", "required_or_planned"], "after": "downgrades (X04)"},
           rules=cx_slots(["CX-41"]) + [direction("X04")], long_page_rule="any_yes"))
A(derived("core.stage_as_of", "dates", "stage_as_of", "activity", [slot("r1", "A08")], ["A08"], answer_type="date"))
A(derived("core.stage_as_of_basis", "provenance", "stage_as_of_basis", "activity", [slot("r1", "A08"), slot("r2", 57)], ["A08", "r2#57", "T3"], answer_type="single"))
A(derived("core.permanent_pilot", "activity_typing", "permanent_pilot", "activity", [slot("r2", 28)], ["r2#28"], answer_type="yes_no"))
A(derived("core.vendor_claim_only", "quality", "vendor_claim_only", "activity", [slot("r2", 28)], ["r2#28"], answer_type="yes_no"))
A(derived("core.unit_credit", "attribution", "unit_credit", "activity", [slot("r2", 47)], ["r2#47"], answer_type="yes_no"))
A(derived("core.uncertainty_flags", "quality", "uncertainty_flags", ["activity", "row"], [slot("r1", "X24"), slot("r2", 38), slot("r2", 39)],
          ["X24", "r2#38", "r2#39"], answer_type="list", translation_v25={"column": "uncertainty_flags", "map": O}))

# ---------------------------------------------------------------- per-code support
A(item("core.support_entailment", "support", "support_entailment", "row", "none", "none",
       slot("r1", "X35", "'Does this text state", "is <value>?'"), vals(("true", None), ("false", None)),
       ["X35", "R-040", "r2#26"], answer_type="yes_no", rules=[slot("r1", "X35")], long_page_rule="none",
       support_required=False, visibility="internal"))
A(mech("core.support_status", "support", "support_status", "row", [slot("spec", "R-041", "Support-status values:", "(r2#37 merged with r2#53; spellings all-11).")],
       ["R-041", "X40", "r2#37", "r2#53", "r2#40"], answer_type="single", pipelines=[WEB, PROC, TXT]))
A(item("core.supporting_text", "support", "supporting_text", "row", "none", "none", None, "none",
       ["R-040", "R-042", "R-043", "R-058", "X12", "r2#17"], linkage="extractor", coder="quote_step", answer_type="text",
       rules=[slot("spec", "R-040"), slot("spec", "R-042"), slot("spec", "R-043"), slot("spec", "R-058", None, "with no masking.")],
       threshold="none", order_tie_rule="none", long_page_rule="none", support_required=False, input_text="quote_source",
       pipelines=[WEB, PROC, TXT]))

# ---------------------------------------------------------------- Stage 6: institution
A(derived("core.has_genai_activity", "verdict", "has_genai_activity", "institution", [slot("spec", "R-005"), slot("r1", "X29")],
          ["R-005", "X29", "C03", "S2 b", "r2#40", "r2#44", "r2#15", "C5 a", "C1 a"], answer_type="single", pipelines=[S6],
          translation_v25={"column": "has_genai_activity", "map": O}))
A(derived("core.verdict_rule", "provenance", "verdict_rule", "institution", [slot("spec", "R-059", "v2.5 `none` institutions", "(`verdict_rule`, r2#45).")],
          ["R-059", "r2#45"], answer_type="single", pipelines=[S6]))
A(derived("core.evidence_tier", "verdict", "evidence_tier", "institution", [slot("r1", "A06"), slot("r2", 21)], ["A06", "r2#21", "T1", "C5 a"],
          answer_type="single", pipelines=[S6]))
A(derived("core.review_depth", "quality", "review_depth", "institution", [slot("r1", "A07")], ["A07", "R-005"], answer_type="list", pipelines=[S6]))
A(item("core.activity_relation_cross_page", "activity_identity", "activity_relation", "activity", "stage6", 1, None, O,
       ["X30", "R-005", "R-017", "r2#22"], pipelines=[S6],
       rules=[slot("r1", "X30"), "core.rule.activity_unit", slot("spec", "R-017", "One shared relation list", "within a page (r2#22; activity-16 b; all-11).")],
       long_page_rule={"rule": O, "note": "pooled evidence split per r2#6"}))
A(item("core.pooled_activity_fields", "activity_identity", "pooled_activity_fields", "activity", "stage6", 2, None, "none",
       ["X31", "r2#6"], pipelines=[S6], rules=[slot("r1", "X31"), slot("r2", 6)], long_page_rule={"rule": "per item (r2#6)"}))
A(derived("core.confidence", "quality", "confidence", ["source", "activity"], [slot("r2", 27)], ["r2#27", "X23"], answer_type="single",
          pipelines=[WEB, S6], translation_v25={"column": "confidence", "map": O}))
A(derived("core.n_sources", "quality", "n_sources", "activity", [slot("r1", "X32")], ["X32"], answer_type="number", pipelines=[S6]))
A(derived("core.institution_summary", "verdict", "institution_summary", "institution", [slot("r1", "X33")], ["X33", "R-090"], pipelines=[S6],
          translation_v25={"column": "institution_summary", "map": O}))
A(derived("core.cx_display_rollup", "disclosure", "cx_display_rollup", "activity", [slot("r1", "X34")], ["X34"], answer_type="list", pipelines=[S6]))

# ---------------------------------------------------------------- row / run provenance
A(mech("core.codebook_release", "provenance", "codebook_release", "row", [slot("spec", "R-050")], ["R-050", "C3 a", "r2#5", "r2#32"],
       pipelines=[WEB, S6, PROC, TXT], translation_v25={"column": "contract_version", "map": O}))
A(mech("core.setup_pointer", "provenance", "setup_pointer", "row", [slot("r1", "X36"), slot("spec", "R-026")], ["X36", "X20", "R-026", "r2#57"],
       pipelines=[WEB, S6, PROC, TXT]))
A(mech("core.evidence_channel", "provenance", "evidence_channel", "row", [slot("r1", "P15")], ["P15", "R-050"],
       pipelines=[WEB, S6, PROC, TXT], answer_type="single"))
A(mech("core.coder_record", "provenance", "coder_record", "row", [slot("spec", "R-026"), slot("r1", "P10")], ["R-026", "P10", "r2#57"],
       pipelines=[WEB, S6, PROC, TXT], visibility="internal"))

# ---------------------------------------------------------------- proc.* and text.* (not in the v2.7 release build; RC-D-002 A rollout)
for pid, nm in [("P01", "notice_stage"), ("P02", "contract_value"), ("P03", "procedure_type"), ("P07", "contract_period")]:
    A(mech(f"proc.{nm}", "procurement", nm, "contract", [slot("r1", pid)], [pid, "r2#12", "D-008"], pipelines=[PROC], status="slot (module owner proposes; D-008)"))
A(mech("proc.contract_terms", "safeguard", "contract_terms", "contract", [slot("r1", "P05"), slot("r2", 29)], ["P05", "r2#29", "D-008"],
       pipelines=[PROC], status="slot (module owner proposes; D-008)"))
for pid, nm in [("P09", "ai_text_score"), ("P10", "detector_provenance"), ("P12", "document_classification"), ("P13", "sampling_design"), ("P14", "genai_era_cutoff")]:
    A(mech(f"text.{nm}", "ai_text", nm, "document", [slot("r1", pid)], [pid, "D-009"], pipelines=[TXT], status="slot (module owner proposes; D-009)"))
A(mech("text.published_text_ai_use", "ai_text", "published_text_ai_use", "institution", [slot("r1", "P11"), slot("r2", 15)], ["P11", "r2#15", "D-009"],
       pipelines=[TXT], status="slot (module owner proposes; D-009)"))
A(mech("core.language_coverage", "provenance", "language_coverage", "row", [slot("r1", "P16"), slot("r2", 39)], ["P16", "r2#39"],
       pipelines=[PROC, TXT], status="slot (owned by the multilingual subproject)"))

RETIRED = [
    {"name": "genai_evidence", "replaced_by": ["core.page_verdict"], "refs": ["R-015", "C01"]},
    {"name": "access_type", "replaced_by": ["core.model_origin", "core.build_arrangement"], "refs": ["C10", "r2#46"]},
    {"name": "interaction_type", "replaced_by": ["core.interface", "core.function_*"], "refs": ["C11", "r2#46"], "legacy_fill": "not_asked"},
    {"name": "vendor", "replaced_by": ["core.contracting_party", "core.developer"], "refs": ["r2#24", "T5"]},
    {"name": "year_deployed", "replaced_by": ["core.year_pilot_start", "core.year_production_start"], "refs": ["C17", "r2#46"], "legacy_fill": slot("spec", "R-051", "e.g. year_deployed = earlier", "pilot / production year")},
    {"name": "scope_notes", "replaced_by": [], "refs": ["C24", "r2#46"], "legacy_fill": "not_asked"},
    {"name": "contract_version", "replaced_by": ["core.codebook_release"], "refs": ["R-050", "C3 a"]},
]


# ================================================================ round-3 fold (drafts as amended by the round-3 rulings)
# Every text below is loaded from a draft JSON, a ruling record or a ruling option text and asserted verbatim.
MISS = ("not_asked", "not_documented", "unknown")


def r3opt(rid, oid=None, field="mechanism", start=None, end=None, role=None) -> dict:
    """Slot from the text of a chosen round-3 option (questions-r3.json)."""
    chosen = r3choices(rid)
    oid = oid or chosen[0]
    assert oid in chosen, (rid, oid, chosen)
    opt = next(o for o in Q3[rid]["options"] if o["id"] == oid)
    text = cut(opt[field], start, end)
    assert text and text in opt[field]
    R3_USED.add(rid)
    d = {"text": text, "origin": "ruling-r3",
         "source": f"codebook-rulings-round3.json {rid} (choice {oid}); option text questions-r3.json {rid}.{oid}.{field}",
         "marker": MARK_R3}
    if role:
        d["role"] = role
    return d


def r3rec(rid, key, start=None, end=None) -> dict:
    """Slot from a field of the round-3 ruling record itself (e.g. all-03 `reading`)."""
    base = R3[rid][key]
    text = cut(base, start, end)
    assert text and text in base
    R3_USED.add(rid)
    return {"text": text, "origin": "ruling-r3", "source": f"codebook-rulings-round3.json {rid}.{key}", "marker": MARK_R3}


def agent(dkey, entry, base, start=None, end=None, rulings=(), role=None, pattern=None) -> dict:
    """Slot from an agent draft (drafts/*.json); `pattern` takes group 1 of a regex instead of cut anchors."""
    if pattern:
        m = re.search(pattern, base, re.S)
        assert m, (entry, pattern)
        text = m.group(1)
    else:
        text = cut(base, start, end)
    assert text and text in base
    text, tr = respell(text)
    R3_USED.update(rulings)
    d = {"text": text, "origin": "agent-draft",
         "source": f"{DFILE[dkey]} {entry}; ruling {', '.join(rulings) if rulings else 'none (draft convention; no round-3 item names it)'}",
         "marker": MARK_AGENT}
    if tr:
        d["transform"] = tr
    if role:
        d["role"] = role
    return d


def open_slot(what: str, refs: str) -> dict:
    return {"text": None, "origin": "none", "source": refs, "marker": MARK_NONE, "open": O, "open_item": what}


FINAL_USED: set = set()


def fopick(cid, field="mechanism", start=None, end=None, role=None) -> dict:
    """Slot from the picked option of a final-open choice (drafts/final-open.json), approved as drafted."""
    ch = FO_CH[cid]
    opt = next(o for o in ch["options"] if o["id"] == ch["pick"])
    text = cut(opt[field], start, end)
    assert text and text in opt[field]
    FINAL_USED.add(cid)
    d = {"text": text, "origin": f"{ORIGIN_FINAL}; final-open {cid}",
         "source": f"final-open.json choices[{cid}] (pick {ch['pick']}, confidence {ch['confidence']}).options[{ch['pick']}].{field}",
         "marker": MARK_FINAL}
    if role:
        d["role"] = role
    return d


def fosent(wid, start=None, end=None, role=None) -> dict:
    """Slot from the accepted 'after' text of a final-open minimal-edit sentence."""
    base = FO_W[wid]["after"]
    text = cut(base, start, end)
    assert text and text in base
    FINAL_USED.add(wid)
    d = {"text": text, "origin": f"{ORIGIN_FINAL}; final-open {wid}", "source": f"final-open.json sentences[{wid}].after",
         "marker": MARK_FINAL}
    if role:
        d["role"] = role
    return d


def d3(oid, start, end, role=None) -> dict:
    """Slot from the approved delta RC-D-003 (its sections carry the O12-O15 and activity-14 b sign-off text)."""
    text = cut(D3, start, end)
    FINAL_USED.add(oid)
    d = {"text": text, "origin": f"{ORIGIN_FINAL}; RC-D-003 {oid}",
         "source": f"deltas/RC-D-003.md:{D3.count(chr(10), 0, D3.index(text)) + 1} ({oid})", "marker": MARK_FINAL}
    if role:
        d["role"] = role
    return d


ITEMS_BY_ID = {it["id"]: it for it in ITEMS}
I = ITEMS_BY_ID


def addrefs(iid, *rids):
    for r in rids:
        assert r in R3, r
        R3_USED.add(r)
    I[iid]["refs"] = list(I[iid]["refs"]) + [r for r in rids if r not in I[iid]["refs"]]


def addrules(iid, *rules):
    cur = I[iid]["rules"]
    I[iid]["rules"] = (list(cur) if isinstance(cur, list) else []) + list(rules)


def missing_last(order):
    """all-04 b: real answers, then not documented, then unknown; not asked never competes."""
    return [c for c in order if c not in MISS] + [c for c in ("not_documented", "unknown") if c in order]


# ---- 2. questionnaire: CX-01.3 draft rows (edited/no_change rows enter through slot(); here: new, retired, pilot lines)
for it in ITEMS:
    fs = it["frozen_signature"]
    if isinstance(fs, str) and fs.startswith("CX-01.2:"):
        it["frozen_signature"] = "CX-01.3 (draft, unsigned):" + fs[len("CX-01.2:"):].replace(" (re-sign as CX-01.3)", "")


def pilot_slot(rowid, pattern, iid=None):
    row = CXROW[rowid]
    m = re.search(pattern, row["draft_text"], re.S)
    assert m, (rowid, pattern)
    fm = re.search(pattern, row["frozen_text"], re.S) if row["frozen_text"] else None
    return cxd_slot(row, m.group(1), fm.group(1) if fm else None, f"cx-01.3-draft.json {rowid}.frozen_text")


# pilot.py lines the draft edits, attached to their items as classifier lines
addrules("core.disclosure_form", {**pilot_slot("pilot.py L134 FORM[mandated_report]", r'"mandated_report": "(.*?)",'), "role": "classifier_line (mandated_report)"},
         r3opt("page-04", "b", role="direction for CX-13 (wording: final-open W01, in the CX-13 cell)"))
addrefs("core.disclosure_form", "page-03", "page-04", "all-06")
addrefs("core.disclosure_scope", "page-03", "all-06")
addrules("core.evaluation_documented", {**pilot_slot("pilot.py L161 EVAL[required_or_planned]", r'"required_or_planned": "(.*?)",'), "role": "classifier_line (required_or_planned)"})
addrefs("core.evaluation_documented", "activity-29", "activity-30", "all-04")
I["core.evaluation_documented"]["long_page_rule"] = {
    "rule": "priority_order", "order": missing_last([v["code"] for v in I["core.evaluation_documented"]["values"]] + ["unknown"]),
    "source": "table order (CX §11.1); `unknown` placed after `not_documented` per all-04 b"}

# outcome / incident value definitions: OUTCOME_KIND (pilot.py L173-177) and new row CX-61b
OK_ROW = "pilot.py L173-177 OUTCOME_KIND"
for iid in ("core.outcome_kind", "core.incident_kind"):
    for v in I[iid]["values"]:
        if v["code"] in ("quantified", "qualitative", "none_reported"):
            v["definition"] = pilot_slot(OK_ROW, rf'(?m)^    "{v["code"]}": "(.*?)",')
    addrefs(iid, "activity-25", "activity-26")
r61b = CXROW["CX-61b"]
m61b = re.search(r"^\| CX-61b(?: [^|]*?)? \| (.*?) \| (.*?) \|$", r61b["draft_text"], re.M)
next(v for v in I["core.incident_kind"]["values"] if v["code"] == "discontinuation_uncertain")["definition"] = cxd_slot(r61b, m61b.group(2), None, None)
addrules("core.incident_kind", {**cxd_slot(r61b, m61b.group(1), None, None), "role": "value cell of CX-61b"}, r3opt("activity-28", "a"))
addrefs("core.incident_kind", "activity-27", "activity-28", "all-11")

# content_data stays a page question (page-07 a), "no" where the verdict shows no GenAI (page-09 c)
L203 = "pilot.py L203 page_questions content_* instructions"
idx = next(i for i, it in enumerate(ITEMS) if it["id"] == "core.content_data")
ITEMS[idx] = item("core.content_data", "disclosure", "content_data", "page", 1, 2,
                  pilot_slot(L203, r'instructions=f?"(.*?)"'),
                  [{"code": c, "definition": pilot_slot(L203, rf'"{c}": "(.*?)"')} for c in ("yes", "no")],
                  ["R-023", "X05", "CX-51", "r2#19", "page-05", "page-07", "page-09"], answer_type="yes_no",
                  gate={**GATE_GENAI5, "gated_out_value": "no", "source": "page-09 c"},
                  rules=cx_slots(["CX-50", "CX-51"]) + [direction("X05"), r3opt("page-07", "a"), r3opt("page-09", "c")],
                  long_page_rule={"rule": "any_yes", "order": ["yes", "no", "not_documented", "unknown"], "text": fopick("F05")},
                  frozen_signature="CX-01.3 (draft, unsigned):CX-51")
I = ITEMS_BY_ID = {it["id"]: it for it in ITEMS}

# derived page items: what each is computed from (CX-51 / CX-52 drafts, page-08 b, c; page-09 c)
CX51 = CXROW["CX-51"]["draft_text"]
DERIVE = {
    "core.content_purpose": (["core.function_*"], "purpose: the activity's function items", None),
    "core.content_tool_or_model": (["core.tool_name", "core.model_name"], "tool or model: tool or model name", None),
    "core.content_vendor": (["core.developer", "core.contracting_party"], "vendor: model developer, stated or looked up, or contracting party", ("page-08", "c")),
    "core.content_users": (["core.target_users", "core.governed_population"], "users: `target_users` or `governed_population`", ("page-08", "b")),
    "core.content_status_date": (["core.adoption_stage", "core.year_announced", "core.year_pilot_start", "core.year_production_start"],
                                 "status or date: `adoption_stage` or a year field", None),
}
for iid, (src_items, anchor, amend) in DERIVE.items():
    d = {"role": "derivation", "derived_from": src_items,
         "draft": fosent("W02", anchor, anchor)}   # accepted CX-51 sentence (final-open W02); was the agent-draft cut
    R3_USED.add("page-05")
    if amend:
        d["amended_by"] = r3opt(*amend)
    addrules(iid, d, r3opt("page-09", "c", role="direction (wording: final-open W03, in the CX-51 cell)"))
    addrefs(iid, "page-05", "page-06", "page-09", *([amend[0]] if amend else []))
CX52 = CXROW["CX-52"]["draft_text"]
for iid, src in [("core.content_human_oversight", "core.has_human_oversight"), ("core.content_risk_assessment", "core.has_risk_assessment"),
                 ("core.content_user_notification", "core.has_transparency_notice")]:
    assert f"`{src.split('.')[1]}`" in CX52
    addrules(iid, {"role": "derivation", "derived_from": [src],
                   "draft": agent("cx", "CX-52 draft_text", CX52, "`yes` if any activity on the page is `yes`, otherwise `no`.",
                                  "otherwise `no`.", rulings=["page-10"])})
    addrefs(iid, "page-10", "page-11", "page-09")
addrefs("core.content_contact_emails", "page-10", "page-12")
addrefs("core.content_contact_named", "page-05")
addrefs("core.content_contact_details", "page-05")

# retired questionnaire lines (page-06 a, page-11 a)
for r in DRAFT["cx"]["rows"]:
    if r["action"] == "retire":
        nm = re.search(r"CONTENT\[(\w+)\]", r["cx_row"]).group(1)
        rul = CX_ROW_RULINGS.get(r["cx_row"], [])
        R3_USED.update(rul)
        RETIRED.append({"name": r["cx_row"], "kind": "questionnaire line (signed CX-01.2 instrument)", "replaced_by": [f"core.{nm} (derived)"],
                        "refs": rul, "archived_text": {"text": r["frozen_text"], "origin": "cx-01.2",
                                                       "source": f"cx-01.3-draft.json {r['cx_row']}.frozen_text; ruling {', '.join(rul)}",
                                                       "marker": "archived signed text — kept in the archive record"}})
        assert r["frozen_text"] == r["draft_text"]

# ---- 3. applicability (activity-01 approve; amended by activity-03 a, e; activity-04 a, d; activity-05 a)
SHARED["core.rule.applicability_table"] = [r3opt("activity-03", "a", field="label"), r3opt("activity-03", "e", field="label"),
                                           r3opt("activity-04", "a"), r3opt("activity-05", "a"),
                                           r3opt("activity-07", "b", role="quote-step items under the table")]
R3_USED.add("activity-01")
SHARED["core.rule.governance_gate"] = [r3opt("activity-04", "d")]
GATE_GOV["rule"] = "core.rule.governance_gate"
SHARED["core.rule.allowed_type_action_pairs"] = [
    {**r3opt("activity-02", "c"),
     "pairs": [{"activity_type": p["type"], "action_type": p["action"], "status": p["status"], "basis": p["basis"]} for p in FO["pairs"]],
     "pairs_source": f"final-open.json pairs ({ORIGIN_FINAL}; final-open pairs table, O11); inferred, no source gives the list",
     "pairs_confidence": FO["pairs_meta"]["confidence"]},
    d3("O14", "a disallowed pair is flagged for review and no label is changed (activity-02 c; O14)",
       "no label is changed (activity-02 c; O14)", role="handling of a disallowed pair")]
FINAL_USED.add("O11")
for iid in ("core.content_contact_named", "core.content_contact_details"):
    it = I[iid]
    assert it["gate"] == "F07"
    it["gate"] = {**GATE_GENAI5, "gated_out_value": "no", "source": f"final-open F07 ({ORIGIN_FINAL})", "text": fopick("F07")}
AMEND_CELLS = {("core.tool_name", "policy_guidance"): ("not_asked", "ask", "activity-03 a"),
               ("core.model_name", "policy_guidance"): ("not_asked", "ask", "activity-03 a"),
               ("core.developer", "policy_guidance"): ("not_asked", "ask", "activity-03 a (the developer derived from them)"),
               ("core.procurement_status", "policy_guidance"): ("ask", "ask", "activity-03 e (kept)")}
CELLS: dict = {}
for c in DRAFT["applic"]["cells"]:
    CELLS.setdefault(c["item"], []).append(c)
for iid, cells in CELLS.items():
    assert I[iid]["gate"] == GATE_APPLIC, iid
    assert [c["activity_type"] for c in cells] == DRAFT["applic"]["rows"], iid
    g = {"table": GATE_APPLIC["table"], "key": "core.activity_type", "rule": "core.rule.applicability_table",
         "cells": {}, "inferred_cells": [], "amended": [],
         "source": f"applicability.json cells[item={iid}]; ruling activity-01 (approve), activity-03 a, e, activity-04 a, activity-05 a"}
    for c in cells:
        cell = c["cell"]
        am = AMEND_CELLS.get((iid, c["activity_type"]))
        if am:
            assert cell == am[0], (iid, cell)
            if am[1] != cell:
                g["amended"].append({"activity_type": c["activity_type"], "draft": cell, "now": am[1], "ruling": am[2]})
            cell = am[1]
        g["cells"][c["activity_type"]] = cell
        if c["confidence"] != "sourced":
            g["inferred_cells"].append(c["activity_type"])
    if not g["amended"]:
        del g["amended"]
    I[iid]["gate"] = g
    addrefs(iid, "activity-01", "activity-03", "activity-04", "activity-05")
assert not [it["id"] for it in ITEMS if it["gate"] == GATE_APPLIC], "applicability gate left open"
for iid in ("core.activity_type", "core.action_type"):
    addrules(iid, "core.rule.allowed_type_action_pairs")
    addrefs(iid, "activity-02")
addrules("core.action_type", "core.rule.governance_gate")
addrefs("core.action_type", "activity-04")
for iid in ("core.tool_name", "core.model_name", "core.contracting_party", "core.deployment_scale_number", "core.developer"):
    addrules(iid, r3opt("activity-07", "b"))
    addrefs(iid, "activity-07")
for iid in ("core.tool_name", "core.contracting_party", "core.developer", "core.year_pilot_start", "core.year_production_start"):
    tr = I[iid]["translation_v25"]
    I[iid]["translation_v25"] = {**tr, "series_break": r3opt("activity-08", "b")}
    addrefs(iid, "activity-08")
SHARED["core.rule.safeguard_attachment"] = SHARED["core.rule.safeguard_attachment"] + [r3opt("activity-06", "b")]
for nm in ("human_oversight", "transparency_notice", "data_classification", "risk_assessment"):
    addrefs(f"core.has_{nm}", "activity-06")

# ---- 4. value lists (value-lists.json as amended)
VL = {l["target"].split(" ")[0]: l for l in DRAFT["values"]["lists"]}


def vlval(target, entries, how, rulings, label=None):
    R3_USED.update(rulings)
    out = []
    for i, e in enumerate(entries):
        code = e["code"] if isinstance(e, dict) else e
        if code in MISS:
            continue
        v = {"code": code, "definition": slot("none", f"value {code}"),
             "code_source": f"value-lists.json {target} {how}[{i}]; ruling {', '.join(rulings)}"}
        if label:
            v["label"] = label[code]
        out.append(v)
    return out


def alt(target, prefix):
    return next(a for a in VL[target]["alternatives"] if a["label"].startswith(prefix))


# all-01 b, all-07 c, all-08/09/10 (CX-06), all-02 a: missing labels
R3_USED.update(["all-01", "all-07", "all-08", "all-09", "all-10", "all-02", "all-11"])
VOC_MISSING = {
    "values": [e["code"] for e in VL["vocabularies.missing"]["values"]] + ["_NA_"],
    "text": slot("spec", "R-045"),
    "na_label": r3opt("all-01", "b"),
    "published_summary_map": {"map": {"unresolved": "unknown", "not_assessable": "unknown"}, "text": r3opt("all-07", "c"),
                              "label_text": r3opt("all-07", "c", field="label")},
    "cx_mapping_row": cxd_slot(CXROW["CX-06"], re.search(r"^\| CX-06(?: [^|]*?)?() \| (.*?) \|$", CXROW["CX-06"]["draft_text"], re.M).group(2), None, None),
    "cx_mapping_row_location": r3opt("all-10", "a"),
}
for it in ITEMS:
    if "activity" in it["level"] and it["missing_tokens"] == list(MISS):
        it["missing_tokens"] = list(MISS) + ["_NA_"]
for iid in ("core.page_verdict", "core.observed_actor_relationship", "core.activity_segment", "core.activity_relation_cross_page"):
    addrefs(iid, "all-07")

# interface (all-02 a, all-11, activity-09 a)
I["core.interface"]["values"] = vlval("core.interface", VL["core.interface"]["values"], "values", ["all-11", "activity-09"])
addrules("core.interface", r3opt("activity-09", "a"), r3opt("all-02", "a"))
addrefs("core.interface", "all-02", "all-11", "activity-09")

# governance direction (activity-10 b split; activity-11 a)
split = alt("core.governance_direction", "Split requires and promotes")["values"]
assert [e["code"] for e in VL["core.governance_direction"]["values"] if e["code"] not in MISS and e["code"] != "requires_or_promotes"] == \
       [c for c in split if c not in MISS and c not in ("requires", "promotes")]
I["core.governance_direction"]["values"] = vlval("core.governance_direction", split, "alternatives['Split requires and promotes'].values", ["activity-10"])
addrules("core.governance_direction", r3opt("activity-10", "b", field="label"), r3opt("activity-11", "a"), r3opt("all-02", "a"))
addrefs("core.governance_direction", "all-02", "activity-10", "activity-11")

# service area (activity-12 b COFOG, labels from the option text; activity-13 a + b)
cofog = [e for e in alt("core.service_domain", "Candidate B")["values"] if e["code"] not in MISS]
labels = [s.strip().rstrip(".") for s in Q3["activity-12"]["options"][[o["id"] for o in Q3["activity-12"]["options"]].index("b")]["mechanism"].split("; ")]
assert [l.lower() for l in labels] == [e["source_phrase"].lower() for e in cofog], (labels, cofog)
other_flag = next(f for f in VL["core.service_domain"]["flags"] if "add `other`" in f)
I["core.service_domain"]["values"] = (vlval("core.service_domain", cofog, "alternatives['Candidate B'].values", ["activity-12"],
                                            label={e["code"]: l for e, l in zip(cofog, labels)})
                                      + [{"code": "other", "definition": slot("none", "value other"),
                                          "code_source": "value-lists.json core.service_domain flags ('add `other`'); ruling activity-13 a"}])
I["core.service_domain"].update(answer_type="multi", order_tie_rule="all_that_apply")
addrules("core.service_domain", r3opt("activity-12", "b", field="label"), r3opt("activity-13", "a"), r3opt("activity-13", "b"),
         r3opt("all-02", "a"),
         {**fopick("F09"), "role": "mapping of the round-2 value", "map": {"general_administration": "general_public_services"}})
assert "general_public_services" in [v["code"] for v in I["core.service_domain"]["values"]]
addrefs("core.service_domain", "all-02", "activity-12", "activity-13")
assert "`other`" in other_flag

# whose activity it is: two linked parts (activity-14 b), all-02 a
d2 = alt("core.observed_actor_relationship", "Draft 2")
I["core.observed_actor_relationship"]["values"] = {
    "structure": r3opt("activity-14", "b", field="label")["text"],
    "relationship": vlval("core.observed_actor_relationship", d2["part_1_relationship"], "alternatives['Draft 2'].part_1_relationship", ["activity-14"]),
    "searched_institution_role": vlval("core.observed_actor_relationship", d2["part_2_role_of_searched_institution"],
                                       "alternatives['Draft 2'].part_2_role_of_searched_institution", ["activity-14"]),
    "role_missing_tokens": [e["code"] for e in d2["part_2_role_of_searched_institution"] if e["code"] in MISS],
}
A14_DROPPED = ", not asked (when the relationship is other or unresolved), not documented, unknown."
assert next(o for o in Q3["activity-14"]["options"] if o["id"] == "b")["mechanism"].endswith("unit, joint" + A14_DROPPED)
ROLE_GATE_TEXT = d3("activity-14 b", "the role is asked when the relationship is `other`; skipped only when `unresolved`",
                    "skipped only when `unresolved`", role="gate of the role part")
I["core.observed_actor_relationship"]["values"]["role_gate"] = {
    "part": "searched_institution_role", "keyed_on": "relationship",
    "not_asked_when_relationship": ["unresolved"], "asked_when_relationship_includes": ["other"],
    "gated_out_value": "not_asked", "text": ROLE_GATE_TEXT}
addrules("core.observed_actor_relationship",
         r3opt("activity-14", "b", start="Relationship:", end="unresolved, unknown."),
         {**r3opt("activity-14", "b", start="Role of the searched institution:", end="unit, joint"),
          "omitted_tail": A14_DROPPED,
          "omitted_by": "PI 2026-10-30 (activity-14 b contradiction): the role is asked when the relationship is `other`; "
                        "the gate is in values.role_gate; the missing labels are in values.role_missing_tokens"},
         ROLE_GATE_TEXT,
         r3opt("all-02", "a"),
         {**fosent("W05"), "role": "publication rule (one column)", "pick": fopick("F08")})
addrefs("core.observed_actor_relationship", "all-02", "activity-14", "activity-15")

# earlier actor-role list kept as an internal item (activity-15 a); codes from the v2.6 source cited in value-lists.json
role_flag = next(f for f in VL["core.observed_actor_relationship"]["flags"] if "git 052fcb2:g3o/common/evidence_review.py" in f)
v26 = subprocess.run(["git", "-C", str(REPO), "show", "052fcb2:g3o/common/evidence_review.py"], capture_output=True, text=True, check=True).stdout
v26_roles = re.findall(r'"(\w+)"', re.search(r"class ObservedActor\(BaseModel\):.*?role: Literal\[(.*?)\]", v26, re.S).group(1))
assert ", ".join(v26_roles) in role_flag, (v26_roles, role_flag)
A(item("core.observed_actor_role", "attribution", "observed_actor_role", "activity", 2, 2, None,
       [{"code": c, "definition": slot("none", f"value {c}"),
         "code_source": "git 052fcb2:g3o/common/evidence_review.py ObservedActor.role (cited in value-lists.json core.observed_actor_relationship flags); ruling activity-15 a"}
        for c in v26_roles if c not in MISS],
       ["A05", "R-014", "activity-15", "final-open F06"], visibility="internal", rules=[r3opt("activity-15", "a")],
       long_page_rule={"rule": "same_part_as", "item": "core.observed_actor_relationship", "fallback": "highest_probability",
                       "text": fopick("F06")},
       missing_tokens=list(MISS) + ["_NA_"]))
R3_USED.add("activity-15")

# links between activities (activity-16 b reverse values; activity-17 a; activity-18 b; institution-02 a; all-11 distinct_action)
inv_in = alt("core.activity_segment", "Inverse codes")["values"]
inv_x = alt("core.activity_relation_cross_page", "Inverse codes")["values"]
I["core.activity_segment"]["values"] = vlval("core.activity_segment", inv_in, "alternatives['Inverse codes'].values", ["activity-16", "all-11"])
I["core.activity_relation_cross_page"]["values"] = vlval("core.activity_relation_cross_page", inv_x, "alternatives['Inverse codes'].values", ["activity-16", "all-11"])
addrules("core.activity_segment", r3opt("activity-16", "b"), r3opt("activity-17", "a"), r3opt("activity-18", "b"))
addrules("core.activity_relation_cross_page", r3opt("activity-16", "b"), r3opt("activity-17", "a"), r3opt("institution-02", "a"))
addrefs("core.activity_segment", "activity-16", "activity-17", "activity-18", "all-11")
addrefs("core.activity_relation_cross_page", "activity-16", "activity-17", "institution-01", "institution-02", "all-11")

# provenance (all-11 spellings; shared-01 a date-origin mapping + upper-bound item; shared-02 a definitions)
PROV_DEF = {"stated": r3opt("shared-02", "a", start='"Stated" =', end="whoever copied it"),
            "quoted_by_quote_step": r3opt("shared-02", "a", start='"quoted by the quote step" =', end="copy.")}
r231 = alt("vocabularies.provenance", "Date-origin list")["values"]
s01 = Q3["shared-01"]["options"][0]
assert s01["id"] == "a"
DATE_MAP_SRC = [("metadata", "from_metadata", "Metadata fits", "situation"),
                ("web_address", "from_metadata", "Web address to from metadata", "mechanism"),
                ("page_text_quote", "quoted_by_quote_step", "page quote to quoted by the quote step", "mechanism"),
                ("archive_upper_bound", "looked_up", "archive bound to looked up", "mechanism"),
                ("unknown", "missing-answer labels (vocabularies.missing)", "unknown through the missing-answer labels", "mechanism"),
                ("access_date", "from_metadata", "access date to from metadata", "mechanism")]
for code, _, phrase, where in DATE_MAP_SRC:
    assert phrase in (Q3["shared-01"]["situation"] if where == "situation" else s01["mechanism"]), phrase
    assert code == "access_date" or code in [e["code"] for e in r231], code
VOC_PROV = {
    "values": [{"code": e["code"], "definition": PROV_DEF.get(e["code"], slot("none", f"value {e['code']}")),
                "code_source": f"value-lists.json vocabularies.provenance values[{i}]; ruling all-11"}
               for i, e in enumerate(VL["vocabularies.provenance"]["values"])],
    "text": slot("r2", 57),
    "date_origin_map": {"map": {c: t for c, t, _, _ in DATE_MAP_SRC}, "text": r3opt("shared-01", "a"),
                        "codes_source": "value-lists.json vocabularies.provenance alternatives['Date-origin list as ruled in r2#31'] (+ access date, A08)",
                        "upper_bound_item": "core.date_upper_bound"},
}
A(mech("core.date_upper_bound", "provenance", "date_upper_bound", ["source", "activity"],
       [r3opt("shared-01", "a", start='add a yes/no note', end='upper bound".')], ["shared-01", "r2#31", "T3", "A08"],
       answer_type="yes_no", pipelines=[WEB, PROC, TXT], translation_v25="new"))
I = ITEMS_BY_ID = {it["id"]: it for it in ITEMS}
addrefs("core.stage_as_of_basis", "shared-01")
addrefs("core.developer_basis", "shared-02")

# support status (all-11 spellings; record-01 a, record-02 a, record-03 c)
VOC_SUPPORT = {
    "values": [e["code"] for e in VL["vocabularies.support_status"]["values"]],
    "text": slot("spec", "R-041", "Support-status values:", "(r2#37 merged with r2#53; spellings all-11)."),
    "rule_name_item": "core.support_rule_name", "second_reason_item": "core.support_status_second_reason",
    "rules": [r3opt("record-01", "a"), r3opt("record-02", "a", field="label"), r3opt("record-02", "a"), r3opt("record-03", "c", field="label")],
}
A(mech("core.support_rule_name", "support", "support_rule_name", "row", [r3opt("record-01", "a")], ["R-041", "record-01", "record-02"],
       answer_type="text", pipelines=[WEB, PROC, TXT], gate={"item": "core.support_status", "values": ["set_by_rule"], "gated_out_value": "empty (record-01 a wording)"}))
A(mech("core.support_status_second_reason", "support", "support_status_second_reason", "row", [r3opt("record-03", "c")], ["R-041", "record-03"],
       answer_type="single", pipelines=[WEB, PROC, TXT]))
I = ITEMS_BY_ID = {it["id"]: it for it in ITEMS}
F10_CODES = re.search(r"^Values: (.*?)\. The main status", fopick("F10")["text"]).group(1).split(", ")
assert F10_CODES == ["downgraded_no_quote", "downgraded_low_confidence", "downgraded_quote_not_stating_value"], F10_CODES
assert set(F10_CODES) <= set(VOC_SUPPORT["values"])
I["core.support_status_second_reason"]["values"] = [
    {"code": c, "definition": slot("none", f"value {c}"), "code_source": f"final-open.json choices[F10].options[a]; {ORIGIN_FINAL}; F10, O13"}
    for c in F10_CODES]
I["core.support_status_second_reason"]["gate"] = {"rule": "empty unless two reasons hold (final-open F10)"}
addrules("core.support_status_second_reason", fopick("F10"))
I["core.support_status_second_reason"]["refs"] = list(I["core.support_status_second_reason"]["refs"]) + ["final-open F10", "RC-D-003 O13"]
FINAL_USED.add("O13")
addrules("core.support_status", r3opt("record-02", "a"), r3opt("record-03", "c"))
addrefs("core.support_status", "record-01", "record-02", "record-03", "all-11")

VOC_RELATION = {"values": [e for e in inv_in if e not in MISS], "text": slot("spec", "R-017", "One shared relation list", "within a page (r2#22; activity-16 b; all-11)."),
                "within_page_only": ["not_an_activity"],
                "source": "value-lists.json core.activity_segment alternatives['Inverse codes']; ruling activity-16 b, all-11"}
assert set(VOC_RELATION["values"]) - {"not_an_activity"} == set(c for c in inv_x if c not in MISS)

# ---- 5. combining rules (combining-rules.json as amended) and conventions
COMB = {d["item"]: d for d in DRAFT["comb"]["items"]}
R_COMB = {"core.source_type": ["source-01", "all-06"], "core.source_publication_date": ["source-01", "all-06"],
          "core.activity_segment": ["activity-19"], "core.observed_actor_relationship": ["activity-19", "activity-14", "all-04"],
          "core.adoption_stage": ["activity-21", "all-04"], "core.governance_direction": ["activity-19", "activity-10", "activity-11", "all-04"],
          "core.deployment_scale_number": ["activity-24"], "core.deployment_scale_unit": ["activity-24"],
          "core.target_users": ["activity-22"], "core.governed_population": ["activity-22"],
          "core.incident_kind": ["activity-27", "all-04"], "core.activity_relation_cross_page": ["institution-01", "all-04"]}
for nm in ("activity_type", "action_type", "model_origin", "deployment_mode", "service_domain"):
    R_COMB[f"core.{nm}"] = ["activity-20"]
for nm in ("procurement_status", "build_arrangement", "interface", "genai_mechanism_basis", "outcome_kind"):
    R_COMB[f"core.{nm}"] = ["activity-19", "all-04"]
for nm in ("contracting_party", "developer"):
    R_COMB[f"core.{nm}"] = ["activity-19"]
for nm in ("human_oversight", "transparency_notice", "data_classification", "risk_assessment"):
    R_COMB[f"core.has_{nm}"] = ["activity-23", "all-04"]
assert set(R_COMB) == set(COMB), set(COMB) ^ set(R_COMB)
for iid, d in COMB.items():
    rul = R_COMB[iid]
    lp = {"rule": d["rule"], "source": f"combining-rules.json items[{iid}]; ruling {', '.join(rul)}"}
    order = d["order"]
    if iid == "core.observed_actor_relationship":   # activity-14 b: the two-part order the draft gives
        order = cut(d["basis"], "the relationship part uses ", ", and the role part")[len("the relationship part uses "):-len(", and the role part")].split(" > ")
        lp["role_part"] = agent("comb", f"items[{iid}].basis", d["basis"], "the role part is taken", "produced the relationship", rulings=["activity-14"])
    if iid.startswith("core.has_"):                  # activity-23 b: yes, no, unclear
        order = [c for c in re.search(r"\(b\) priority (.*?),? so an", d["alternative"]).group(1).split(" > ") if c not in MISS]             + [c for c in d["order"] if c in MISS]    # missing labels as in the drafted order, then ranked by all-04 b
        assert [o.lower() for o in order[:3]] == [s.strip().lower() for s in r3opt("activity-23", "b", field="label")["text"].split(",")]
        lp["source"] += " (order: the draft's alternative (b))"
    if order:
        if "requires_or_promotes" in order:          # activity-10 b
            i = order.index("requires_or_promotes")
            order = order[:i] + ["requires", "promotes"] + order[i + 1:]
            lp["rank_of_requires_vs_promotes"] = fopick("F02")
        lp["order"] = missing_last(order)
        if "rank_of_requires_vs_promotes" in lp:   # F02 a: the drafted order is the order the pick states
            assert ", ".join(lp["order"]) + "." == cut(lp["rank_of_requires_vs_promotes"]["text"], "restricts_with_conditions", ".")
    if iid in ("core.target_users", "core.governed_population"):   # activity-22 b: collect, then map
        a = re.findall(r"\{(\w+), (\w+)\} read as `both`", d["alternative"])
        assert a, iid
        lp = {"rule": "combined_list", "then": "mapping step to one value",
              "mapping": {"map": {f"{a[0][0]} + {a[0][1]}": "both"}, "other_lists": fopick("F03")},
              "text": [r3opt("activity-22", "b"), agent("comb", f"items[{iid}].alternative", d["alternative"], pattern=r"^(.*?)(?: \(needs|\. The column)", rulings=["activity-22"])],
              "source": f"combining-rules.json items[{iid}].alternative; ruling activity-22 b"}
    if iid in ("core.deployment_scale_number", "core.deployment_scale_unit"):   # activity-24 b
        lp = {"rule": "combined_list", "pairs": "(number, unit), the unit from the same part as its number",
              "text": [r3opt("activity-24", "b"), agent("comb", f"items[{iid}].alternative", d["alternative"], rulings=["activity-24"])],
              "source": f"combining-rules.json items[{iid}].alternative; ruling activity-24 b"}
    if iid == "core.governance_direction":
        lp["mapping"] = {"map": {"prohibits + permits (across parts)": "restricts_with_conditions"}, "text": r3opt("activity-11", "a")}
    if iid == "core.adoption_stage":
        lp["permanent_pilot_across_parts"] = {"rule": "within_part_only", "known_limit": True, "text": fopick("F01")}
    if iid == "core.service_domain":
        lp["multi_select_vs_single_winner"] = fopick("F04")   # activity-20 a (most sure) meets activity-13 b (several areas)
        lp["rule"] = "combined_list"   # F04 a: every supported area; each area's quote and certainty from the most-sure part
        lp["per_value_producing_part"] = "highest_probability"
        lp["replaces_rule"] = "highest_probability (activity-20 a, before activity-13 b made the item multi-select)"
    if iid == "core.activity_relation_cross_page":
        lp["split_rule"] = r3opt("institution-01", "b")
    I[iid]["long_page_rule"] = lp
    addrefs(iid, *rul)
I["core.page_verdict"]["long_page_rule"]["tiers"] = r3opt("page-02", "b")
addrefs("core.page_verdict", "page-02")
addrules("core.page_complete", r3opt("page-01", "c", role="direction: note (wording: final-open W04)"), fosent("W04", role="note"))
addrefs("core.page_complete", "page-01")

CONV = DRAFT["comb"]["conventions"]
NOT_COVERED = re.search(r'"(not covered by this part)"', R3FILE["all-03_comment"]).group(1)
COMBINING_CONVENTIONS = {
    "check_then_combine": {"rulings": ["all-03"], "text": [
        agent("comb", "conventions.downgrade_first", CONV["downgrade_first"], rulings=["all-03"]),
        r3rec("all-03", "reading", None, 'the temporary value is never published.'),
        {"text": R3FILE["all-03_comment"], "origin": "ruling-r3", "source": "codebook-rulings-round3.json all-03_comment (PI comment, verbatim)", "marker": MARK_R3}]},
    "not_covered_by_this_part": {"rulings": ["all-03"], "temporary_value": NOT_COVERED, "published": False,
                                 "applies_to": "every question in every part prompt of a long page",
                                 "text": [r3rec("all-03", "reading", "the prompt states", "the temporary value is never published.")],
                                 "generator_check_16": "the generator must add this value to every part prompt (fold-log-round3.md)"},
    "missing_rank": {"rulings": ["all-04"], "order": ["real answers", "not_documented", "unknown"],
                     "text": [r3opt("all-04", "b", field="label"), r3opt("all-04", "b"),
                              agent("comb", "conventions.missing_tokens", CONV["missing_tokens"], "`not_asked` never competes", "is combined.", rulings=["all-04"])]},
    "producing_part": {"rulings": ["all-05"], "text": [agent("comb", "conventions.producing_part", CONV["producing_part"], rulings=["all-05"]), r3opt("all-05", "a")]},
    "first_part": {"rulings": ["all-06"], "text": [r3opt("all-06", "a"), agent("comb", "conventions.stage6", CONV["stage6"], rulings=["all-06"])]},
    "gate_items_first": {"rulings": ["all-04"], "text": [agent("comb", "conventions.combine_gate_items_first", CONV["combine_gate_items_first"], rulings=["all-04"])]},
    "activity_level": {"rulings": [], "text": [agent("comb", "conventions.activity_level", CONV["activity_level"])]},
}

# ---- 6. final sign-off (PI, chat, 2026-10-30: "all accepted"): minimal-edit sentences into the CX-01.3 draft cells,
#         O12 (support status of `no`, negative verdicts, `_NA_`), O15 (institution rule). Picks F01-F10 and O11/O13/O14 and
#         the activity-14 b gate are folded where the open fields were (sections 3-5 above).
CX_EDITS = {"CX-13": [("final-open W01", FO_W["W01"]["before"], FO_W["W01"]["after"])],
            "CX-51": [("final-open W02", FO_W["W02"]["before"], FO_W["W02"]["after"]),
                      ("final-open W03", FO_W["W03"]["before"], FO_W["W03"]["after"])],
            "CX-50": [("C P2 (stale clause removed)", P2_CLAUSE, "")]}


def cx_cell(rowid: str) -> str:
    """Second cell of a CX-01.3 draft row, as slot('cx', ...) takes it for an edited row."""
    dt = CXROW[rowid]["draft_text"]
    return (re.search(rf"^\| {re.escape(rowid)}(?: [^|]*?)? \| (.*?) \| (.*?) \|$", dt, re.M)
            or re.search(rf"^\| {re.escape(rowid)}(?: [^|]*?)?() \| (.*?) \|$", dt, re.M)).group(2)


def apply_final_edits(x, seen) -> int:
    n = 0
    if isinstance(x, dict):
        src = x.get("source") or ""
        row = next((r for r in CX_EDITS if isinstance(src, str) and src.startswith(f"cx-01.3-draft.json {r};")), None)
        if row and x.get("origin") == "agent-draft" and id(x) not in seen:
            seen.add(id(x))
            assert x["text"] == cx_cell(row), row
            t = x["text"]
            for _, before, after in CX_EDITS[row]:
                assert t.count(before) == 1, (row, before[:60])
                t = t.replace(before, after)
            x.update(text=t, origin=f"{ORIGIN_FINAL}; " + ", ".join(w for w, _, _ in CX_EDITS[row]), marker=MARK_FINAL,
                     applied_to=f"cx-01.3-draft.json {row} (agent draft); earlier source: {src}")
            FINAL_USED.update(w.split(" ")[-1] if w.startswith("final-open") else "P2" for w, _, _ in CX_EDITS[row])
            n += 1
        for v in list(x.values()):
            n += apply_final_edits(v, seen)
    elif isinstance(x, list):
        for v in x:
            n += apply_final_edits(v, seen)
    return n


N_CX_EDITED = apply_final_edits([ITEMS, SHARED, VOC_MISSING, VOC_PROV, VOC_SUPPORT, COMBINING_CONVENTIONS], set())
assert N_CX_EDITED > 0

# O12: support status of `no`, negative page verdicts and `_NA_` (record-02 a keeps its text; O12 extends `not_required`)
O12_TEXT = d3("O12", "`not_required`, for `not_documented`, `unknown`, `no` and negative page verdicts",
              "`_NA_` takes `set_by_rule` (O12)", role="which answers take which status")
VOC_SUPPORT["status_by_answer"] = {"not_documented": "not_required", "unknown": "not_required", "no": "not_required",
                                   "negative page verdicts (R-041)": "not_required", "not_asked": "set_by_rule", "_NA_": "set_by_rule",
                                   "text": O12_TEXT}
# PI 2026-10-30 "2a": option texts overridden by O12, O13, O14 are cut before the overridden part (as activity-14 b);
# the kept text is verbatim and the omitted tail is recorded on the slot, never emitted as text.
CUT_2A = {"record-02": ("a", '"Not required"', "O12 (`no` and negative page verdicts also take `not_required`; `_NA_` takes `set_by_rule`)"),
          "activity-02": ("c", "flagged for review", "O14 (a disallowed pair is flagged for review; no label is changed)"),
          "record-03": ("c", "A second reason item", "O13 (a second-reason item, not a combined value)")}
OMITTED_2A = {}


def cut_2a(x, seen) -> int:
    n = 0
    if isinstance(x, dict):
        for rid, (oid, end, by) in CUT_2A.items():
            if x.get("source") == f"codebook-rulings-round3.json {rid} (choice {oid}); option text questions-r3.json {rid}.{oid}.mechanism" \
                    and id(x) not in seen:
                seen.add(id(x))
                full = next(o for o in Q3[rid]["options"] if o["id"] == oid)["mechanism"]
                kept = cut(full, None, end)
                assert x["text"] == full and full.startswith(kept), rid
                OMITTED_2A[rid] = full[len(kept):]
                x.update(text=kept, omitted_tail=full[len(kept):],
                         omitted_by=f'PI 2026-10-30 "2a": overridden by {by}; cut before the overridden part')
                n += 1
        for v in list(x.values()):
            n += cut_2a(v, seen)
    elif isinstance(x, list):
        for v in x:
            n += cut_2a(v, seen)
    return n


N_2A = cut_2a([ITEMS, SHARED, VOC_MISSING, VOC_PROV, VOC_SUPPORT, COMBINING_CONVENTIONS], set())
assert set(OMITTED_2A) == set(CUT_2A) and N_2A == 5, (N_2A, OMITTED_2A)

# PI 2026-10-30 "1a": the W01 insertion also goes into the CX-01.3 classifier line (mandated_report), no backticks
L134_BEFORE = "Otherwise a statutory annual report is formal_record."
L134_AFTER = "Otherwise a statutory annual report or a compliance report under a rule not about AI is formal_record."
assert FO_W["W01"]["after"].replace("`", "") .count(L134_AFTER) == 1   # the same words as W01, backticks dropped
l134 = [r for r in I["core.disclosure_form"]["rules"] if isinstance(r, dict) and r.get("role") == "classifier_line (mandated_report)"]
assert len(l134) == 1 and l134[0]["text"].count(L134_BEFORE) == 1
l134[0].update(text=l134[0]["text"].replace(L134_BEFORE, L134_AFTER), origin='PI 2026-10-30 "1a"; final-open W01', marker=MARK_FINAL,
               edited_from=f"cx-01.3-draft.json pilot.py L134 FORM[mandated_report] (agent draft): {L134_BEFORE!r} -> {L134_AFTER!r}")
FINAL_USED.add("1a")
addrules("core.support_status", O12_TEXT)
I["core.support_status"]["refs"] = list(I["core.support_status"]["refs"]) + ["RC-D-003 O12"]

# O15: institution rule unchanged; the published-summary map applies to summaries only
VOC_MISSING["published_summary_map"]["institution_rule"] = d3(
    "O15", "Inside the institution-level rule both keep their current roles", "stays out of the institution-rate base (O15).")
VOC_MISSING["published_summary_map"]["not_assessable_in_institution_rate_base"] = False
addrules("core.has_genai_activity", VOC_MISSING["published_summary_map"]["institution_rule"])
I["core.has_genai_activity"]["refs"] = list(I["core.has_genai_activity"]["refs"]) + ["RC-D-003 O15"]
FINAL_USED.add("O16")   # the ten mechanical choices of fold-log §4: accepted as folded, no codebook change


def build() -> dict:
    return {
        "release": {"label": O, "status": "draft", "namespaces": ["core", "proc", "text"], "build_scope_v2_7": "core",
                    "signature_record": O, "hash_rule": "sha256 of this file's bytes at sign-off, after slot markers are removed (A-001, P4)",
                    "template": "planning/t010/item-template.md", "built_by": "planning/t010/build_skeleton.py",
                    "folds": {"round3": "planning/t010/fold-log-round3.md (drafts/*.json as amended by codebook-rulings-round3.json)",
                              "final": "planning/t010/fold-log-round3.md, Final fold (drafts/final-open.json and deltas/RC-D-003.md; PI 2026-10-30 \"all accepted\")"}},
        "vocabularies": {
            "missing": VOC_MISSING,
            "provenance": VOC_PROV,
            "support_status": VOC_SUPPORT,
            "relation": VOC_RELATION,
            "pipeline": {"values": [WEB, S6, PROC, TXT]},
            "level": {"values": ["institution", "page", "activity", "source", "contract", "document", "row", "run"]},
            "genai_era_cutoff": {"text": slot("r2", 31)},
        },
        "shared_rules": SHARED,
        "combining_conventions": COMBINING_CONVENTIONS,
        "items": {it["id"]: it for it in ITEMS},
        "retired": RETIRED,
    }


def _str_rep(dumper, data):
    style = "|" if ("\n" in data or len(data) > 100) and not data.endswith(" ") else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


def verify(cb: dict, out: Path, base: dict | None = None) -> None:
    assert len({i["id"] for i in ITEMS}) == len(ITEMS), "duplicate ids"
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    def walk(a, b, path=""):
        if isinstance(a, dict):
            for k in a:
                walk(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, list):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
        else:
            assert a == b, f"round-trip mismatch at {path}"
    walk(cb, loaded)
    for sid, rules in cb["shared_rules"].items():
        for r in rules:
            assert r["text"], sid
    for it in ITEMS:
        for r in (it["rules"] if isinstance(it["rules"], list) else []):
            if isinstance(r, str):
                assert r in cb["shared_rules"], (it["id"], r)
    verify_round3(cb if base is None else base)
    verify_final(cb if base is None else base)
    if base is not None:
        verify_r4(cb, base)


def verify_final(cb: dict) -> None:
    """Final sign-off checks (PI 2026-10-30): pairs table, the five sentences, CX-50 clause, role gate, O12 statuses, verbatim slots."""
    fo_raw = FO_FILE.read_text(encoding="utf-8")
    d3_raw = D3_FILE.read_text(encoding="utf-8")

    def slots(x):
        if isinstance(x, dict):
            if "origin" in x and "text" in x:
                yield x
            for v in x.values():
                yield from slots(v)
        elif isinstance(x, list):
            for v in x:
                yield from slots(v)
    scope = [cb[k] for k in ("vocabularies", "shared_rules", "combining_conventions", "items", "retired")]
    all_slots = list(slots(scope))
    texts = [s["text"] for s in all_slots if isinstance(s["text"], str)]
    # 1. every final-origin slot is verbatim in its source; edited CX cells equal the draft cell with the accepted edits
    n_final = 0
    for s in all_slots:
        if not str(s["origin"]).startswith(ORIGIN_FINAL):
            continue
        n_final += 1
        if "applied_to" in s:
            row = re.match(r"cx-01\.3-draft\.json (\S+) ", s["applied_to"]).group(1)
            t = cx_cell(row)
            for _, before, after in CX_EDITS[row]:
                t = t.replace(before, after)
            assert s["text"] == t, row
        elif "RC-D-003" in s["origin"]:
            assert s["text"] in d3_raw, s["source"]
        else:
            assert json.dumps(s["text"], ensure_ascii=False)[1:-1] in fo_raw, s["source"]
    # 2. pairs table: 30 cells, 18 allowed / 12 flag, every (type, action) once, codes equal the two items' codes
    pr = cb["shared_rules"]["core.rule.allowed_type_action_pairs"][0]["pairs"]
    types = [v["code"] for v in cb["items"]["core.activity_type"]["values"]]
    actions = [v["code"] for v in cb["items"]["core.action_type"]["values"]]
    assert len(pr) == 30 == len(types) * len(actions), len(pr)
    assert {(p["activity_type"], p["action_type"]) for p in pr} == {(t, a) for t in types for a in actions}
    st = [p["status"] for p in pr]
    assert st.count("allowed") == 18 and st.count("flag") == 12 and set(st) == {"allowed", "flag"}, st
    assert FO["pairs_meta"]["counts"] == {"pairs": 30, "allowed": 18, "flag": 12}
    # 3. the five accepted sentences are present verbatim; the replaced draft sentences and the stale CX-50 clause are gone
    for w in ("W01", "W02", "W03", "W04", "W05"):
        assert any(FO_W[w]["after"] in t for t in texts), w
    for w in ("W01", "W02", "W03"):
        assert not any(FO_W[w]["before"] in t for t in texts), w
    assert sum(FO_W["W01"]["after"] in t for t in texts) >= 1
    assert all(FO_W["W02"]["after"] in t and FO_W["W03"]["after"] in t for t in texts if t.startswith("Items: `content_purpose`"))
    assert not any(P2_CLAUSE.strip(", ") in t for t in texts), "stale CX-50 clause still present"
    # 4. role gate: asked when the relationship is `other`; not asked only when `unresolved`
    rel = cb["items"]["core.observed_actor_relationship"]["values"]
    g = rel["role_gate"]
    assert g["not_asked_when_relationship"] == ["unresolved"] and "other" in g["asked_when_relationship_includes"]
    assert "other" in [v["code"] for v in rel["relationship"]] and "unresolved" in [v["code"] for v in rel["relationship"]]
    assert not any("(when the relationship is other or unresolved)" in t for t in texts), "overruled role clause still emitted"
    # 5. O12: `_NA_` -> set_by_rule; `no` and negative page verdicts -> not_required
    sba = cb["vocabularies"]["support_status"]["status_by_answer"]
    assert sba["_NA_"] == "set_by_rule" and sba["not_asked"] == "set_by_rule"
    assert sba["no"] == "not_required" and sba["negative page verdicts (R-041)"] == "not_required"
    assert sba["not_documented"] == sba["unknown"] == "not_required"
    assert set(v for k, v in sba.items() if k != "text") <= set(cb["vocabularies"]["support_status"]["values"])
    # 6. every signed-off choice landed; nothing but procedural/sign-off fields stays open
    need = {f"F{i:02d}" for i in range(1, 11)} | {f"W0{i}" for i in range(1, 6)} | {"O11", "O12", "O13", "O14", "O15", "O16", "activity-14 b", "P2", "1a"}
    assert need <= FINAL_USED, need - FINAL_USED
    left = [p for p in open_paths(cb) if not (p[0] == "items" and p[2] in ("version_introduced", "translation_v25"))
            and ".".join(p) not in ("release.label", "release.signature_record")]
    assert not left, left
    # 7. "1a": the classifier line carries the insertion, without backticks; "2a": no overridden tail is emitted
    l1 = [s for s in all_slots if s["origin"] == 'PI 2026-10-30 "1a"; final-open W01']
    assert len(l1) == 1 and L134_AFTER in l1[0]["text"] and "`" not in l1[0]["text"]
    assert l1[0]["text"] == pilot_slot("pilot.py L134 FORM[mandated_report]", r'"mandated_report": "(.*?)",')["text"].replace(L134_BEFORE, L134_AFTER)
    assert not any(L134_BEFORE in t for t in texts)
    for rid, tail in OMITTED_2A.items():
        core_tail = tail.strip(" .,")
        assert core_tail and not any(core_tail in t for t in texts), (rid, core_tail)
    assert all(s["text"] + s["omitted_tail"] == next(o for o in Q3[r]["options"] if o["id"] == CUT_2A[r][0])["mechanism"]
               for s in all_slots if "omitted_tail" in s for r in [s["source"].split(" ")[1]] if r in CUT_2A)
    assert not any("amended_by" in s for s in all_slots if "omitted_tail" in s)
    print(f"final checks: {n_final} PI-approved slots verbatim; pairs 30 = 18 allowed + 12 flag; W01-W05 present; "
          f"CX-50 clause gone; role gate asked on `other`; O12 statuses; 1a line; 2a tails absent; {len(need)} sign-off ids folded; no substantive open fields")


R3_ID = re.compile(r"\b(?:all|page|activity|source|institution|record|shared)-\d\d\b")


def open_paths(x, path=()):
    """Every leaf equal to `open`, with its path."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield from open_paths(v, path + (str(k),))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from open_paths(v, path + (str(i),))
    elif x == O:
        yield path


def verify_round3(cb: dict) -> None:
    """Round-3 fold checks: every ruling lands somewhere or is logged; every `open` is logged; every agent/ruling slot is verbatim."""
    # 1. every slot carrying a round-3 origin is verbatim in its source (re-checked from the files, not from memory)
    raw = {k: (DRAFTS / f).read_text(encoding="utf-8") for k, f in DFILE.items()}
    qraw = (R3DIR / "questions-r3.json").read_text(encoding="utf-8")
    rraw = (R3DIR / "codebook-rulings-round3.json").read_text(encoding="utf-8")

    def slots(x):
        if isinstance(x, dict):
            if "origin" in x and "text" in x:
                yield x
            for v in x.values():
                yield from slots(v)
        elif isinstance(x, list):
            for v in x:
                yield from slots(v)

    def enc(t):
        return json.dumps(t, ensure_ascii=False)[1:-1]
    draftvals = [json.loads(r) for r in raw.values()]

    def in_drafts(t):
        def walk(x):
            if isinstance(x, str):
                return t in x
            if isinstance(x, dict):
                return any(walk(v) for v in x.values())
            if isinstance(x, list):
                return any(walk(v) for v in x)
            return False
        return any(walk(d) for d in draftvals)
    n = 0
    for s in slots(cb):
        if s["origin"] == "agent-draft":
            t = s["text"].replace(RESPELL[1], RESPELL[0]) if "transform" in s else s["text"]
            assert in_drafts(t), s["source"]
            if s.get("frozen_text"):
                assert in_drafts(s["frozen_text"]) or s["frozen_text"] in TEXT["cx"], s["source"]
            n += 1
        elif s["origin"] == "ruling-r3":
            assert enc(s["text"]) in qraw or enc(s["text"]) in rraw, s["source"]
            n += 1
    assert n > 0
    # 2. ruling coverage
    log = FOLD_LOG.read_text(encoding="utf-8") if FOLD_LOG.exists() else ""
    scope = {k: cb[k] for k in ("vocabularies", "shared_rules", "combining_conventions", "items")}
    referenced = set(R3_ID.findall(json.dumps(scope, ensure_ascii=False)))
    assert referenced <= set(R3), referenced - set(R3)
    unref = sorted(set(R3) - referenced)
    for rid in unref:
        assert re.search(rf"^\|? ?`?{re.escape(rid)}`?.*no codebook change", log, re.M), f"{rid}: not referenced and not logged as 'no codebook change'"
    assert R3_USED <= set(R3)
    # 3. every open field is logged: item fields by (field, item id) table row; other paths verbatim
    rows = {}
    for ln in log.splitlines():
        m = re.match(r"^\| `([\w.]+)` \| (.*?) \|", ln)
        if m:
            rows.setdefault(m.group(1), []).append(m.group(2))
    missing = []
    for p in open_paths(cb):
        if p[0] == "items":
            iid, field = p[1], p[2]
            if not any("all items" in c or f"`{iid}`" in c for c in rows.get(field, [])):
                missing.append(f"items.{iid}.{field}")
        elif f"`{'.'.join(p)}`" not in log:
            missing.append(".".join(p))
    assert not missing, f"open fields not listed in {FOLD_LOG.name}: {sorted(set(missing))}"
    print(f"round-3 checks: {n} round-3 slots verbatim; {len(referenced)} ruling ids referenced, {len(unref)} logged as no change; "
          f"{len(list(open_paths(cb)))} open leaves all logged")


# ---------------------------------------------------------------- round 4 (PI, chat, 2026-10-30)
# "Reviewed the above; approve all the review items; give a subagent to disambiguate & propose default fixes where
# necessary. I want a single, clean final draft version of the codebook to look at & approve." (t010-rulings.md)
# The round-4 stage runs on a deep copy of the built codebook: verify_round3() and verify_final() keep checking the
# unchanged base, and verify_r4() checks what this stage changed. Slot paths are those of the round-4 page maps.
R4DIR = PLAN / "t010/codebook-review/round4"
R4_DEF_FILE = DRAFTS / "definitions-r4.json"
R4_FIX_FILE = DRAFTS / "fixes-r4.json"
R4_DEF = json.loads(R4_DEF_FILE.read_text(encoding="utf-8"))["entries"]
R4_FIX = {f["id"]: f for f in json.loads(R4_FIX_FILE.read_text(encoding="utf-8"))["fixes"]}
R4_MAPS = sorted(R4DIR.glob("t010-r4-*.map.json"))
ORIGIN_R4DEF = 'PI 2026-10-30 "approve all"; agent draft r4'
APPROVED_R4 = 'PI 2026-10-30 "approve all" (round 4)'
MARK_R4 = 'PI-approved (round 4, 2026-10-30, "approve all"); marker removed at sign-off'
MARK_FIX = "proposed default r4 {fid} (pending PI approval)"
MISSING_CODES = ("not_asked", "not_documented", "unknown", "_NA_")
TEXT_FIXES = ("FX10", "FX11", "FX12", "FX13")
R4_LOG: dict = {}


def r4_get(cb: dict, path: str):
    parts = path.split("/")
    x, rest = (cb["items"][parts[1]], parts[2:]) if parts[0] == "items" else (cb[parts[0]], parts[1:])
    for p in rest:
        x = x[int(p)] if isinstance(x, list) else x[p]
    return x


def r4_page_slots() -> list:
    """(page, card, slot number, path) for every slot on the round-4 pages."""
    out = []
    for f in R4_MAPS:
        page = f.name[len("t010-r4-"):-len(".map.json")]
        for card, v in json.loads(f.read_text(encoding="utf-8")).items():
            for n, p in (v.get("slots") or {}).items():
                out.append((page, card, n, p))
    return out


def r4_unique_core_slots(cb: dict) -> list:
    """Every distinct text slot of the v2.7 build (core items, vocabularies, shared rules, conventions), with a path."""
    seen, out = set(), []

    def walk(x, path):
        if isinstance(x, dict):
            if "origin" in x and "text" in x and id(x) not in seen:
                seen.add(id(x))
                out.append(("/".join(path), x))
            for k, v in x.items():
                walk(v, path + (str(k),))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, path + (str(i),))
    for k in ("vocabularies", "shared_rules", "combining_conventions"):
        walk(cb[k], (k,))
    for iid, it in cb["items"].items():
        if iid.startswith("core."):
            walk(it, ("items", iid))
    return out


def r4_text_fixes(t: str) -> tuple:
    """FX10, FX11, FX12, FX13 on one slot text, in that order; returns (text, ids of the fixes that changed it)."""
    used = []
    for fid in ("FX10", "FX12"):
        for sp in R4_FIX[fid]["action"]["spans"]:
            if sp in t:
                t = t.replace(sp, "")
                used.append(fid)
    cut_at = R4_FIX["FX11"]["action"]["from"]
    if cut_at in t:
        t = t[:t.index(cut_at)]
        used.append("FX11")
    a = R4_FIX["FX13"]["action"]
    t13 = re.sub(a["paren"], "", t)
    t13 = re.sub(a["lead"], lambda m: m.group(1) + "\x00", t13)
    t13 = re.sub("\x00(.)", lambda m: m.group(1).upper(), t13) if a.get("lead_capitalize") else t13.replace("\x00", "")
    if t13 != t:
        t = t13
        used.append("FX13")
    return t, sorted(set(used))


def r4_mark_fix(s: dict, fid: str) -> None:
    s.setdefault("origin_before_r4", s["origin"])
    s.setdefault("marker_before_r4", s["marker"])
    ids = sorted(set([x for x in s.get("r4_fixes", "").split(", ") if x] + [fid]))
    s["r4_fixes"] = ", ".join(ids)
    s["origin"] = s["marker"] = MARK_FIX.format(fid=s["r4_fixes"])


def r4_rule(fid: str, text: str, role: str, **extra) -> dict:
    return {"text": text, "origin": MARK_FIX.format(fid=fid), "source": f"drafts/fixes-r4.json {fid}",
            "marker": MARK_FIX.format(fid=fid), "role": role, "r4_fixes": fid, **extra}


def apply_r4(cb: dict) -> dict:
    """Fold the round-4 approvals and the proposed default fixes into cb, in place. Every path is resolved first."""
    page = [(pg, card, n, p, r4_get(cb, p)) for pg, card, n, p in r4_page_slots()]
    assert len(page) == 546 and all(isinstance(s, dict) and "text" in s for *_, s in page), len(page)
    f_app = [(t, r4_get(cb, t["slot"])) for f in ("FX01", "FX02") for t in R4_FIX[f]["action"]["targets"]]
    f_rep = [r4_get(cb, p) for p in R4_FIX["FX09"]["action"]["targets"]]
    f_drop = []
    for t in R4_FIX["FX08"]["action"]["targets"]:
        head, last = t["slot"].rsplit("/", 1)
        f_drop.append((t, r4_get(cb, head), r4_get(cb, t["slot"])))
    # 1. the 136 definitions, verbatim
    def_objs = {}
    for i, e in enumerate(R4_DEF):
        s = r4_get(cb, e["slot"])
        assert s["text"] is None and s["marker"] == MARK_NONE, e["slot"]
        s.update(text=e["text"], origin=ORIGIN_R4DEF, source_before_r4=s["source"],
                 source=f"drafts/definitions-r4.json entries[{i}] ({e['slot']}); confidence {e['confidence']}",
                 marker_before_r4=s["marker"], marker=MARK_R4)
        def_objs[id(s)] = i
    assert len(def_objs) == 136
    # 2. every page slot approved as shown (a slot shown on two pages records both cards)
    n_app = 0
    for pg, card, n, p, s in page:
        ref = f"page {pg} card {card} slot {n}"
        if "approved_r4" in s:
            s["approved_r4"] += f"; {ref}"
            continue
        if id(s) not in def_objs:
            s["marker_before_r4"] = s["marker"]
            s["marker"] = MARK_R4
            n_app += 1
        s["approved_r4"] = f"{APPROVED_R4}: {ref}"
    # 3. FX09 replacement, then the text fixes on every distinct core slot, then the FX01/FX02 appends
    for s in f_rep:
        assert s["text"] == '"Not required"', s["text"]
        s["text_before_r4"], s["text"] = s["text"], R4_FIX["FX09"]["action"]["text"]
        r4_mark_fix(s, "FX09")
    n_txt = {}
    for _, s in r4_unique_core_slots(cb):
        if not isinstance(s["text"], str) or any(k in s for k in ("frozen_text", "applied_to", "edited_from")) or "FX09" in s.get("r4_fixes", ""):
            continue
        t, used = r4_text_fixes(s["text"])
        if used:
            s["text_before_r4"], s["text"] = s["text"], t
            for fid in used:
                r4_mark_fix(s, fid)
                n_txt[fid] = n_txt.get(fid, 0) + 1
    for t, s in f_app:
        assert id(s) in def_objs and "text_before_r4" not in s, t["slot"]
        s["text_before_r4"], s["text"] = s["text"], s["text"] + t["append"]
        r4_mark_fix(s, "FX01" if t in R4_FIX["FX01"]["action"]["targets"] else "FX02")
    # 4. new rule lines (FX04, FX05, FX07)
    for fid in ("FX04", "FX05", "FX07"):
        a = R4_FIX[fid]["action"]
        it = cb["items"][a["item"]]
        it["rules"] = (it["rules"] if isinstance(it["rules"], list) else []) + [r4_rule(fid, a["text"], a["role"])]
    # 5. FX06: reserved missing labels out of the answer lists (a list shared by several items moves once), kept as rule lines
    a6, moved = R4_FIX["FX06"]["action"], {}
    for iid, code in a6["items"].items():
        it = cb["items"][iid]
        vals = it["values"]
        if id(vals) not in moved:
            hit = [v for v in vals if v["code"] == code]
            assert len(hit) == 1, (iid, code)
            vals.remove(hit[0])
            moved[id(vals)] = hit[0]
        v = moved[id(vals)]
        assert v["code"] == code and code in it["missing_tokens"], iid
        it["rules"] = (it["rules"] if isinstance(it["rules"], list) else []) + [
            r4_rule("FX06", v["definition"]["text"], a6["role"].format(code=code), moved_from_values=v)]
    # 6. FX08: drop the restatement in each pair (a reference by identity, or one key)
    dropped = []
    for t, parent, obj in f_drop:
        if t["kind"] == "reference":
            assert isinstance(parent, list) and sum(x is obj for x in parent) == 1, t["slot"]
            parent[:] = [x for x in parent if x is not obj]
        else:
            key = t["slot"].rsplit("/", 1)[1]
            assert parent.get(key) is obj, t["slot"]
            del parent[key]
        dropped.append({"card": t["card"], "slot": t["slot"], "kind": t["kind"], "kept": t["kept"], "text": obj["text"],
                        "by": MARK_FIX.format(fid="FX08")})
        nested = [x for _, x in r4_unique_core_slots({"vocabularies": {"d": obj}, "shared_rules": {}, "combining_conventions": {}, "items": {}})]
        R4_LOG.setdefault("dropped_ids", set()).update(id(x) for x in nested)   # the slot and any slot inside it (e.g. a pick)
    cb["release"]["folds"]["round4"] = ("planning/t010/drafts/definitions-r4.json and codebook-review/round4/ (PI 2026-10-30 "
                                        "\"approve all\"); drafts/fixes-r4.json (proposed defaults FX01-FX13, pending PI approval)")
    cb["release"]["r4_dropped"] = dropped
    R4_LOG.update(page=page, defs=def_objs, n_app=n_app, n_txt=n_txt, moved=len(moved))
    return cb


def verify_r4(cb: dict, base: dict) -> None:
    """Round-4 checks: approvals, definitions and fixes verbatim, no 'PI to write' marker, check 8, base untouched."""
    live = {id(s): s for _, s in r4_unique_core_slots(cb)}
    reach = set(live) | {id(s) for _, s in r4_unique_core_slots({"vocabularies": {"retired": cb["retired"]}, "shared_rules": {},
                                                                  "combining_conventions": {}, "items": {}})}
    for it in cb["items"].values():               # moved definitions sit inside rule lines; count them as reachable
        for r in (it["rules"] if isinstance(it["rules"], list) else []):
            if isinstance(r, dict) and "moved_from_values" in r:
                reach.add(id(r["moved_from_values"]["definition"]))
    page, dropped_ids = R4_LOG["page"], R4_LOG.get("dropped_ids", set())
    # 1. every page slot is approved (or under a pending fix) and still in the build, unless FX08 dropped it
    for pg, card, n, p, s in page:
        assert "approved_r4" in s and (s["marker"] == MARK_R4 or s["marker"].startswith("proposed default r4 ")), p
        if id(s) in dropped_ids and id(s) not in reach:
            continue
        assert id(s) in reach, (pg, card, n, p)
    n_dropped = sum(1 for *_, s in page if id(s) not in reach)
    # 2. definitions verbatim; an FX01/FX02 append keeps the definition as its prefix
    apps = {t["slot"]: t["append"] for f in ("FX01", "FX02") for t in R4_FIX[f]["action"]["targets"]}
    for *_, p, s in page:
        if id(s) in R4_LOG["defs"]:
            e = R4_DEF[R4_LOG["defs"][id(s)]]
            if e["slot"] in apps:
                assert s["text_before_r4"] == e["text"] and s["text"] == e["text"] + apps[e["slot"]], p
            else:
                assert s["text"] == e["text"], p
    # 3. fixes verbatim
    for s in live.values():
        ids = [x for x in s.get("r4_fixes", "").split(", ") if x]
        if not ids:
            continue
        tf = sorted(set(ids) & set(TEXT_FIXES))
        if tf:
            assert r4_text_fixes(s["text_before_r4"]) == (s["text"], tf), s["source"]
        if "FX09" in ids:
            assert s["text"] == R4_FIX["FX09"]["action"]["text"] and s["text_before_r4"] == '"Not required"'
        if ids == ["FX06"]:
            assert s["text"] == s["moved_from_values"]["definition"]["text"]
        if ids[0] in ("FX04", "FX05", "FX07"):
            assert s["text"] == R4_FIX[ids[0]]["action"]["text"]
    for fid in ("FX04", "FX05", "FX07"):
        a = R4_FIX[fid]["action"]
        assert sum(isinstance(r, dict) and r.get("r4_fixes") == fid for r in cb["items"][a["item"]]["rules"]) == 1, fid
    assert sum(isinstance(r, dict) and r.get("r4_fixes") == "FX06" for it in cb["items"].values()
               for r in (it["rules"] if isinstance(it["rules"], list) else [])) == len(R4_FIX["FX06"]["action"]["items"])
    texts = [s["text"] for s in live.values() if isinstance(s["text"], str)]
    befores = [s["text_before_r4"] for s in live.values() if "text_before_r4" in s]
    for fid in ("FX10", "FX12"):
        for sp in R4_FIX[fid]["action"]["spans"]:
            assert any(sp in b for b in befores), (fid, sp[:60])
            assert not any(sp in t for t in texts), (fid, sp[:60])
    assert not any(R4_FIX["FX11"]["action"]["from"] in t for t in texts)
    assert not any("[wording: PI" in t for t in texts)
    # 4. no "PI to write" marker left in the v2.7 core items
    left = [p for p, s in r4_unique_core_slots(cb) if "PI to write" in str(s.get("marker"))]
    assert not left, left[:5]
    # 5. check 8: no answer code of a core item equals a missing label
    for iid, it in cb["items"].items():
        if iid.startswith("core.") and isinstance(it["values"], list):
            bad = [v["code"] for v in it["values"] if isinstance(v, dict) and v.get("code") in MISSING_CODES]
            assert not bad, (iid, bad)
    # 6. the pairs table stays whole: its codes are answers or the `unknown` missing label
    pr = cb["shared_rules"]["core.rule.allowed_type_action_pairs"][0]["pairs"]
    types = {v["code"] for v in cb["items"]["core.activity_type"]["values"]} | {"unknown"}
    actions = {v["code"] for v in cb["items"]["core.action_type"]["values"]} | {"unknown"}
    assert len(pr) == 30 and all(x["activity_type"] in types and x["action_type"] in actions for x in pr)
    # 7. FX08: the role-gate text is no longer repeated among the relationship's rules; the O12 text is gone
    rel = cb["items"]["core.observed_actor_relationship"]
    assert not any(r is rel["values"]["role_gate"]["text"] for r in rel["rules"])
    assert "text" not in cb["vocabularies"]["support_status"]["status_by_answer"]
    # 8. the base is untouched
    assert not any(s.get("marker") == MARK_R4 or "r4_fixes" in s for _, s in r4_unique_core_slots(base))
    print(f"round-4 checks: 546 page slots approved ({R4_LOG['n_app']} as shown + 136 definitions; {n_dropped} dropped by FX08); "
          f"definitions and fixes verbatim (text fixes {dict(sorted(R4_LOG['n_txt'].items()))}; {R4_LOG['moved']} answer lists cleared by FX06); "
          f"no 'PI to write' marker in core; check 8 holds; pairs table whole; base untouched")


# ---- Translation fold and sign-off build (2026-10-30) ----
# PI, chat, 2026-10-30: "all review approved" (translation table, S1 b) and "approved!" (final draft, FX01-FX13 included);
# "s1 b s2b; accept all" (P1 version_introduced "2.7" on core items, placeholders open; P2 strip markers, keep origin and source;
# P3 signature record). The translation defaults go in verbatim; the sign-off build then strips every marker.
TR_FILE = DRAFTS / "translation-r4.json"
ORIGIN_TR = 'PI 2026-10-30 "all review approved"; agent draft r4 translation'
ORIGIN_FX = 'PI 2026-10-30 "approved!"; fixes-r4 {fid}'
SIGNATURE_RECORD = "planning/t010/signoff-record.md"
PENDING = re.compile(r"proposed default r4 (FX\d\d(?:, FX\d\d)*) \(pending PI approval\)")


def apply_tr(cb: dict) -> int:
    tr = json.loads(TR_FILE.read_text(encoding="utf-8"))
    items = cb["items"]
    n = 0
    for i, e in enumerate(tr["entries"]):
        tv = items[e["item"]]["translation_v25"]
        assert isinstance(tv, dict) and tv["column"] == e["column"], e["item"]
        for leaf in e["leaves"]:
            assert tv[leaf] == O, (e["item"], leaf)
            n += 1
        for k, v in e["default_value"].items():
            assert tv.get(k, O) == O, (e["item"], k)
            tv[k] = v
        tv["origin"], tv["source"] = ORIGIN_TR, f"drafts/translation-r4.json entries[{i}]"
    m = tr["missing_labels_convention"]
    cb["vocabularies"]["missing"]["translation_v25"] = {
        "map": {c["v27"]: c["v25"] for c in m["cells"]}, "origin": ORIGIN_TR,
        "source": "drafts/translation-r4.json missing_labels_convention"}
    assert n == tr["counts"]["open_leaves"], n
    return n


def apply_signoff(cb: dict) -> dict:
    """Strip markers (P2), approve the r4 fixes, set the release label and version_introduced (P1/P3)."""
    stats = {"markers": 0, "fixes": 0}
    folds = cb["release"]["folds"]
    old = "(proposed defaults FX01-FX13, pending PI approval)"
    assert old in folds["round4"]
    folds["round4"] = folds["round4"].replace(old, '(FX01-FX13; PI 2026-10-30 "approved!")')
    folds["translation"] = 'planning/t010/drafts/translation-r4.json (PI 2026-10-30 "all review approved")'
    folds["signoff"] = ('markers stripped, release label 2.7, version_introduced 2.7 on core items '
                        '(PI 2026-10-30 "s1 b s2b; accept all"); CX-01.3 signed in one batch signature (RC-D-004)')

    def walk(x):
        if isinstance(x, dict):
            for k in [k for k in x if k.startswith("marker")]:
                del x[k]
                stats["markers"] += 1
            for k, v in list(x.items()):
                if isinstance(v, str) and PENDING.search(v):
                    x[k] = PENDING.sub(lambda mm: ORIGIN_FX.format(fid=mm.group(1)), v)
                    stats["fixes"] += 1
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(cb)
    rel = cb["release"]
    rel["label"] = "2.7"
    rel["status"] = "release candidate; signed only if the signature record holds this file's sha256"
    rel["signature_record"] = SIGNATURE_RECORD
    core = [it for k, it in cb["items"].items() if k.startswith("core.")]
    for it in core:
        assert it["version_introduced"] == O, it
        it["version_introduced"] = "2.7"
    stats["core_items"] = len(core)
    cx = [it for it in cb["items"].values() if str(it.get("frozen_signature", "")).startswith("CX-01.3 (draft, unsigned):")]
    for it in cx:
        it["frozen_signature"] = "CX-01.3:" + it["frozen_signature"].split(":", 1)[1]
    stats["cx_items"] = len(cx)
    return stats


def verify_signoff(cb: dict) -> None:
    def strings(x, path=()):
        if isinstance(x, dict):
            for k, v in x.items():
                assert not str(k).startswith("marker"), path + (k,)
                yield from strings(v, path + (str(k),))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from strings(v, path + (str(i),))
        elif isinstance(x, str):
            yield path, x
    for path, v in strings(cb):
        assert "pending PI approval" not in v, path
        assert not (path[-1] == "text" and "PI to write" in v), path
    left = list(open_paths(cb))
    assert all(p[0] == "items" and p[2] == "version_introduced" and not p[1].startswith("core.")
               for p in left), left
    assert cb["release"]["label"] == "2.7"
    assert not any("draft, unsigned" in str(it.get("frozen_signature", "")) for it in cb["items"].values())
    print(f"sign-off checks: no markers; no pending fixes; open leaves only placeholder version_introduced ({len(left)})")



# ---- RC-D-005 candidate (2026-10-30) ----
# PI, chat, 2026-10-30 (t010-rulings.md, "RC-D-005 content"): "1a, 2a, 3 subagent drafts all & I read and edit/confirm,
# 4 part of 3, 5 a, 6a, 7a, 8b, 9 a, 10a 11 a 12 a 13a 14a; accept all". This stage applies the rulings that need no new
# wording (2 a, 7 a, 8 b, 9 a, 10 a, 11 a, 12 a, 13 a, 14 a) and the P1 / P3 structural fixes, as data: every change is
# one entry of drafts/fixes-r5.json (path, before, after), applied in file order on the signed build. No slot text is
# written or edited; 13 a only removes slots. verify_r5() checks that every remaining slot text is byte-identical to a
# slot of the signed build and that the only texts gone are the 13 a drops.
R5_FILE = DRAFTS / "fixes-r5.json"
R5_BASE = "d24bbc7c8ad7f5b9165977d86ca33094a0e6a979944f8fcf6515e78570d20764"
BUILDS = ("signed-2.7", "r5-draft", "r5-signoff")
R5_OUT = {"r5-draft": PLAN / "t010/candidate-r5/codebook-r5-draft.yaml",
          "r5-signoff": PLAN / "t010/candidate-r5/codebook-r5-signoff.yaml"}
R5_BUILD_NAME = {"r5-draft": "draft build", "r5-signoff": "sign-off build"}


def r5_resolve(cb: dict, path: str):
    """(parent, key) of a '/'-separated path; list indexes are integers."""
    parts = path.split("/")
    x = cb
    for p in parts[:-1]:
        x = x[int(p)] if isinstance(x, list) else x[p]
    return x, (int(parts[-1]) if isinstance(x, list) else parts[-1])


def r5_apply_fix(cb: dict, f: dict, build: str) -> None:
    """Apply one fixes-r5.json entry. set: the value at each path equals `before` and becomes `after`; add: the key
    is absent and becomes `after`; delete: each path holds its `before` object, which is removed (list items by
    identity, after every path of the entry is resolved, so indexes refer to the state before the entry)."""
    paths = f.get("paths") or [f["path"]]
    after = f["after_by_build"][build] if "after_by_build" in f else f.get("after")
    if f["op"] == "delete":
        befores = f["before"] if "paths" in f else [f["before"]]
        assert len(befores) == len(paths), f["id"]
        targets = []
        for p, before in zip(paths, befores):
            parent, k = r5_resolve(cb, p)
            assert parent[k] == before, (f["id"], p)
            targets.append((parent, k, parent[k]))
        for parent, k, obj in targets:
            if isinstance(parent, list):
                idx = [i for i, x in enumerate(parent) if x is obj]
                assert len(idx) == 1, (f["id"], k)
                del parent[idx[0]]
            else:
                del parent[k]
        return
    for p in paths:
        parent, k = r5_resolve(cb, p)
        if f["op"] == "set":
            assert parent[k] == f["before"], (f["id"], p)
        elif f["op"] == "add":
            assert isinstance(parent, dict) and k not in parent, (f["id"], p)
        else:
            raise ValueError(f["op"])
        parent[k] = copy.deepcopy(after)


def apply_r5(cb: dict, build: str) -> int:
    fx = json.loads(R5_FILE.read_text(encoding="utf-8"))
    assert fx["base_sha256"] == R5_BASE, fx["base_sha256"]
    for f in fx["fixes"]:
        r5_apply_fix(cb, f, build)
    cb["release"]["folds"]["r5"] = ("planning/t010/drafts/fixes-r5.json (RC-D-005: rulings 2 a, 7 a, 8 b, 9 a, 10 a, 11 a, "
                                    "12 a, 13 a, 14 a and P1 / P3 structural fixes; PI 2026-10-30, t010-rulings.md); "
                                    f"{R5_BUILD_NAME[build]}")
    return len(fx["fixes"])


def r5_slots(x, path=""):
    """(path, slot) for every text slot (a mapping with `text` and `origin`)."""
    if isinstance(x, dict):
        if "text" in x and "origin" in x:
            yield path.lstrip("/"), x
        for k, v in x.items():
            yield from r5_slots(v, f"{path}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from r5_slots(v, f"{path}/{i}")


def verify_r5(cb: dict, signed: dict, build: str) -> None:
    """RC-D-005 checks: retained slot texts byte-identical; only the 13 a texts gone; every fix in place; build mode."""
    from collections import Counter
    fx = json.loads(R5_FILE.read_text(encoding="utf-8"))
    new = Counter(s["text"] for _, s in r5_slots(cb) if isinstance(s["text"], str))
    old = Counter(s["text"] for _, s in r5_slots(signed) if isinstance(s["text"], str))
    assert not (new - old), f"slot texts not in the signed build: {list(new - old)[:3]}"
    dropped = Counter()
    for f in fx["fixes"]:
        if f["op"] == "delete":
            for b in (f["before"] if "paths" in f else [f["before"]]):
                dropped.update(s["text"] for _, s in r5_slots(b) if isinstance(s["text"], str))
    assert old - new == dropped, "texts gone differ from the 13 a drops"
    assert not any(str(s.get("role", "")).startswith("direction") for _, s in r5_slots(cb)), "a direction slot remains"
    for f in fx["fixes"]:                       # every set / add is in place (no later entry overwrote it)
        if f["op"] in ("set", "add"):
            want = f["after_by_build"][build] if "after_by_build" in f else f["after"]
            for p in f.get("paths") or [f["path"]]:
                parent, k = r5_resolve(cb, p)
                assert parent[k] == want, (f["id"], p)
    rel = cb["release"]
    assert rel["status"] == {"r5-draft": "draft", "r5-signoff": "signed"}[build]
    core = [it for k, it in cb["items"].items() if k.startswith("core.")]
    assert all(it["status"] == ("signed" if build == "r5-signoff" else "slot") for it in core)
    assert set(cb["vocabularies"]["family"]["values"]) == {it["family"] for it in cb["items"].values()}
    print(f"r5 checks: {sum(new.values())} slot texts, all byte-identical to slots of the signed build; "
          f"{sum(dropped.values())} direction slot texts dropped (13 a); {len(fx['fixes'])} fixes in place; "
          f"release.status {rel['status']}; {len(core)} core items status {core[0]['status']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", choices=BUILDS, default="signed-2.7",
                    help="signed-2.7 reproduces the signed file; r5-draft / r5-signoff build the RC-D-005 candidate")
    ap.add_argument("--out", default=None, help="default: codebook/codebook.yaml (signed-2.7) or planning/t010/candidate-r5/")
    ap.add_argument("--list-open", action="store_true", help="print every open leaf before verifying")
    ap.add_argument("--spec-rev", default=None, help="read SPEC.md from this git revision (read at import time)")
    a = ap.parse_args()
    cb = build()
    base = copy.deepcopy(cb)      # the pre-round-4 codebook; verify_round3() and verify_final() check it unchanged
    apply_r4(cb)
    yaml.add_representer(str, _str_rep, Dumper=yaml.SafeDumper)
    out = Path(a.out) if a.out else (WT / "codebook/codebook.yaml" if a.build == "signed-2.7" else R5_OUT[a.build])
    out.parent.mkdir(parents=True, exist_ok=True)
    # The approved draft is verified first (round-3, final and round-4 checks), in a side file, then signed-off stages run.
    draft = out.with_name(out.stem + ".draft-r4" + out.suffix)
    draft.write_text(yaml.safe_dump(cb, sort_keys=False, allow_unicode=True, width=10_000), encoding="utf-8")
    verify(cb, draft, base)
    draft.unlink()
    n_tr = apply_tr(cb)
    st = apply_signoff(cb)
    print(f"translation leaves filled={n_tr}; markers stripped={st['markers']}; fix origins approved={st['fixes']}; "
          f"version_introduced 2.7 on {st['core_items']} core items; CX-01.3 items {st['cx_items']}")
    header = ("# G3O codebook release 2.7 \u2014 release candidate (T-010). Built by planning/t010/build_skeleton.py.\n"
              "# Every slot text is copied verbatim from its `source`; `origin` records who approved it.\n"
              "# Signed only if planning/t010/signoff-record.md holds this file's sha256 (A-001).\n")
    signed_cb = None
    if a.build != "signed-2.7":
        signed_cb = copy.deepcopy(cb)        # the signed 2.7 content; verify_r5() compares the candidate with it
        n5 = apply_r5(cb, a.build)
        print(f"RC-D-005 fixes applied: {n5} ({a.build})")
        header = (f"# G3O codebook release 2.7 \u2014 RC-D-005 candidate, {R5_BUILD_NAME[a.build]} (T-010). "
                  f"Built by planning/t010/build_skeleton.py --build {a.build}.\n"
                  "# Every slot text is copied verbatim from its `source`; `origin` records who approved it.\n"
                  "# Signed only if planning/t010/signoff-record.md holds this file's sha256 (A-001).\n")
    # CRLF pinned (2026-10-30): the PI signed the bytes written on Windows; this keeps the hash the same on every OS.
    out.write_text(header + yaml.safe_dump(cb, sort_keys=False, allow_unicode=True, width=10_000), encoding="utf-8",
                   newline=chr(13) + chr(10))
    ops = list(open_paths(cb))
    print(f"open leaves={len(ops)} open item fields={len({(p[1], p[2]) for p in ops if p[0] == 'items'})}")
    if a.list_open:
        for p in ops:
            print("OPEN", ".".join(p))
    assert yaml.safe_load(out.read_text(encoding="utf-8")) == cb, "round-trip mismatch"
    verify_signoff(cb)
    if signed_cb is not None:
        verify_r5(cb, signed_cb, a.build)
    n_open = len(ops)
    print(f"items={len(ITEMS)} shared_rules={len(SHARED)} retired={len(RETIRED)} open_fields={n_open} "
          f"sha256={hashlib.sha256(out.read_bytes()).hexdigest()[:16]} -> {out}")


if __name__ == "__main__":
    main()
