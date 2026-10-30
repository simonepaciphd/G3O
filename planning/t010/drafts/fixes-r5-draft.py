"""Draft drafts/fixes-r5.json and fixes-r5.md (RC-D-005 candidate) from the signed codebook.

Integrator tool (T-010, RC-D-005), written 2026-10-30 by a subagent of the plan integrator (Claude Code, claude-opus-5-5).
It reads the signed file (codebook/codebook.yaml, sha256 d24bbc7c...0764), writes one entry per change with its
ruling, path, before and after, and applies the entries in order with the builder's own r5_apply_fix(), so every
path and `before` is the state the builder will meet. No slot text is written: entries move, flag or remove data.
Run: python planning/t010/drafts/fixes-r5-draft.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import yaml

T010 = Path(__file__).resolve().parents[1]
ROOT = T010.parents[1]
sys.path.insert(0, str(T010))
from build_skeleton import R5_BASE, r5_apply_fix, r5_resolve, r5_slots  # noqa: E402

SIGNED = ROOT / "codebook/codebook.yaml"
raw = SIGNED.read_bytes()
assert hashlib.sha256(raw).hexdigest() == R5_BASE, "codebook/codebook.yaml is not the signed file"
cb = yaml.safe_load(raw.decode("utf-8"))
I = cb["items"]
CORE = [k for k in I if k.startswith("core.")]
FIXES: list = []
RULING = "PI, chat, 2026-10-30 (t010-rulings.md, RC-D-005 content)"


def get(path):
    parent, k = r5_resolve(cb, path)
    return parent[k]


def fix(fid, ruling, op, what, path=None, paths=None, before=None, after=None, after_by_build=None, **extra):
    f = {"id": fid, "ruling": ruling, "op": op, "what": what}
    if paths is not None:
        f["paths"] = paths
    else:
        f["path"] = path
    if op in ("set", "delete"):
        f["before"] = before if before is not None else (
            [copy.deepcopy(get(p)) for p in paths] if paths is not None and op == "delete" else copy.deepcopy(get(path if paths is None else paths[0])))
    if after_by_build is not None:
        f["after_by_build"] = after_by_build
    elif op != "delete":
        f["after"] = after
    f.update(extra)
    r5_apply_fix(cb, f, "r5-draft")     # draft build; the sign-off build differs only in after_by_build values
    FIXES.append(f)
    return f


# ---------------------------------------------------------------- 2 a: release status and item status
OLD_STATUS = cb["release"]["status"]
fix("R5-01", "2 a", "set", "release.status machine-readable: draft (draft build) / signed (sign-off build)",
    path="release/status", after_by_build={"r5-draft": "draft", "r5-signoff": "signed"})
fix("R5-02", "2 a", "add", "the human sentence of release.status kept in its own key", path="release/status_note", after=OLD_STATUS)
st_paths = [f"items/{k}/status" for k in CORE if I[k]["status"] == "slot"]
fix("R5-03", "2 a", "set", f"status of the {len(st_paths)} build-scope items with status `slot`: `signed` in the sign-off build, "
    "unchanged in the draft build", paths=st_paths, before="slot", after_by_build={"r5-draft": "slot", "r5-signoff": "signed"})
LC = "items/core.language_coverage"
assert get(LC + "/status") == "slot (owned by the multilingual subproject)"
fix("R5-04", "P1; 2 a", "set", "language_coverage status: a template value (`slot`; `signed` in the sign-off build); the owner moves "
    "to its own key (R5-05)", path=LC + "/status", after_by_build={"r5-draft": "slot", "r5-signoff": "signed"})
fix("R5-05", "P1", "add", "language_coverage owner, from the former status text", path=LC + "/owner", after="the multilingual subproject")

# ---------------------------------------------------------------- 13 a: drop the drafter-direction slots
# Status of each direction in the signed text, checked by hand against the signed file; every quote below is asserted
# to occur verbatim at its path (after the drop).
DIRECTIONS = {
    "codebook-rulings-round1.json X01.mechanism": ("done", [
        ("items/core.disclosure_form/values/2/definition", "a reporting obligation that concerns reporting on AI, algorithms or digital systems"),
        ("items/core.disclosure_form/rules/1", "The obligation must be named on the page, except that it may be inferred from the document's genre **when the document's title names AI or algorithmic reporting**. Otherwise a statutory annual report or a compliance report under a rule not about AI is `formal_record`."),
        ("items/core.disclosure_form/rules/3", "Otherwise a statutory annual report or a compliance report under a rule not about AI is formal_record.")],
        "CX-12 (value definition) and CX-13 (rule) were re-worded as directed; CX-01.2 read \"a reporting obligation, such as ...\" and "
        "\"named on the page **or inferred from the document's genre**\". The classifier line carries the same words."),
    "codebook-rulings-round3.json page-04 (choice b); option text questions-r3.json page-04.b.mechanism": ("done", [
        ("items/core.disclosure_form/rules/1", "Otherwise a statutory annual report or a compliance report under a rule not about AI is `formal_record`.")],
        "final-open W01 added compliance reports under rules not about AI to the same sentence of the CX-13 cell."),
    "codebook-rulings-round1.json X02.mechanism": ("done, except `_NA_`, superseded", [
        ("items/core.disclosure_scope/rules/1", "Pages whose `disclosure_form` is `register_cross_institution`, `register_single_institution` or `mandated_report`. On other pages the field is not asked and stores the reserved \"not asked\" label (CX-06)."),
        ("vocabularies/missing/na_label", "Store `not_asked` when a rule skips a question; store `_NA_` on items of a row that has no activity.")],
        "The gate is encoded (gate: core.disclosure_form in the three values). The direction's \"otherwise store `_NA_`\" was not carried "
        "out as written: all-01 b reserves `_NA_` for rows with no activity, and the signed CX cell stores \"not asked\"."),
    "codebook-rulings-round3.json page-01 (choice c); option text questions-r3.json page-01.c.mechanism": ("done", [
        ("items/core.page_complete/rules/1", "Note: `yes` means incomplete (the page refers the reader onward); the name `page_complete` reads the other way.")],
        "final-open W04 wrote the note."),
    "codebook-rulings-round1.json X06.mechanism": ("done in the codebook; the pipeline part is code, not codebook", [
        ("items/core.text_source/rules/0", "records which rows lack chrome text and links")],
        "Both contact items read `input_text: main_plus_chrome` (the main text plus header, footer and navigation). Storing the separate "
        "`chrome_text` is a pipeline change outside the codebook and cannot be checked here."),
    "codebook-rulings-round1.json X08.mechanism": ("done (domain and count; the role-address alternative was not taken)", [
        ("items/core.content_contact_emails/rules/0", "in full and internally only; only the domain part of each address and a count are published"),
        ("items/core.content_contact_emails/rules/1", "Contact e-mails are stored in full internally, and only the domain and a count are published.")],
        "`content_contact_emails` has `visibility: public_derived`."),
    "codebook-rulings-round1.json X05.mechanism": ("done, except `_NA_`, superseded", [
        ("items/core.content_data/instruction", "Does the page state this about any GenAI activity on the page"),
        ("items/core.content_data/rules/1", "`content_data` is asked about any GenAI activity on the page. The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.")],
        "The gate on the five GenAI-bearing verdicts is encoded on `content_data` (and on the contact items by F07); the five derived items "
        "are computed, not asked. The re-wording is in the `content_data` question and the CX-51 cell. \"Store `_NA_` otherwise\" was "
        "superseded by page-09 c (W03): those pages take `no`."),
    "codebook-rulings-round3.json page-09 (choice c); option text questions-r3.json page-09.c.mechanism": ("done", [
        ("items/core.content_purpose/rules/1", "The five derived items and `content_data` apply only on pages whose page verdict is one of the five GenAI-bearing values; on other pages they are `no`.")],
        "final-open W03 wrote it into the CX-51 cell; `content_data` has `gated_out_value: no`."),
    "codebook-rulings-round1.json X07.mechanism": ("done", [
        ("items/core.content_human_oversight/rules/0", "derived from that safeguard's shared four-answer question asked once per activity (`has_human_oversight`, `has_risk_assessment`, `has_transparency_notice`): `yes` if any activity on the page is `yes`, otherwise `no`.")],
        "The `has_*` items are pass-2 classifier items, asked once per activity; the three page items are derived from them."),
    "codebook-rulings-round1.json X10.mechanism": ("done", [
        ("items/core.outcome_kind/rules/0", "over the page text with this activity's span marked")],
        "`outcome_kind` / `incident_kind` are pass 2; `reported_outcomes` / `reported_incidents` are quote-step extractor items gated on them."),
    "codebook-rulings-round1.json X09.mechanism": ("done, with the value `none_reported` for \"none\"", [
        ("items/core.outcome_kind/rules/0", "It answers both whether the page reports an outcome (an incident) of this activity and of what kind; no separate existence question is asked. The outcome or incident text is extracted only when the answer is not `none_reported`."),
        ("items/core.reported_outcomes/rules/0", "for rows coded before CX-01.3 only")],
        "CX-60 now applies to rows coded before CX-01.3 only."),
    "codebook-rulings-round1.json X03.mechanism": ("done (CX-32c narrowed as the direction states)", [
        ("items/core.evaluation_documented/rules/1", "A clause requiring periodic review of the GenAI policy itself is `not_documented`, unless it requires testing, monitoring or evaluation of GenAI tools or their outputs; then it counts as `required_or_planned`.")],
        "CX-01.2 read \"... counts as `required_or_planned`\"; the CX-32c cell was narrowed to the direction's wording, and the classifier line carries it."),
    "codebook-rulings-round1.json X04.mechanism": ("done, except `_NA_`, superseded", [],
        "The six type items are gated on `evaluation_documented` in {results_reported, conducted_no_results, required_or_planned} with "
        "`after: downgrades (X04)`; R-081 downgrades are \"as under R-041\", so both are covered. \"Otherwise store `_NA_`\" is superseded "
        "by all-01 b (\"not asked\")."),
}
def direction_groups() -> dict:
    groups: dict = {}
    for path, s in r5_slots(cb):
        if str(s.get("role", "")).startswith("direction") and "/moved_from_values" not in path:
            groups.setdefault(s["source"], []).append(path)
    return groups


assert set(direction_groups()) == set(DIRECTIONS), set(direction_groups()) ^ set(DIRECTIONS)
n = 6
DROP_LOG = []
for src in list(direction_groups()):
    paths = direction_groups()[src]        # recomputed: an earlier drop shifts later indexes in the same rules list
    status, ev, note = DIRECTIONS[src]
    texts = {get(p)["text"] for p in paths}
    assert len(texts) == 1, src
    f = fix(f"R5-{n:02d}", "13 a", "delete", f"drop the drafter-direction slot ({len(paths)} item(s))", paths=paths,
            direction_text=texts.pop(), direction_source=src, carried_out=status, evidence_note=note,
            evidence=[{"path": p, "quote": q} for p, q in ev])
    DROP_LOG.append(f)
    n += 1
# evidence quotes occur verbatim at their paths after the drops (input_text / visibility / gate facts checked here too)
for f in DROP_LOG:
    for e in f["evidence"]:
        assert e["quote"] in get(e["path"])["text"], (f["id"], e["path"])
assert I["core.content_contact_named"]["input_text"] == I["core.content_contact_details"]["input_text"] == "main_plus_chrome"
assert I["core.content_contact_emails"]["visibility"] == "public_derived"
assert I["core.disclosure_scope"]["gate"]["values"] == ["register_cross_institution", "register_single_institution", "mandated_report"]
assert I["core.content_data"]["gate"]["gated_out_value"] == "no"
assert I["core.evaluation_type_pilot_evaluation"]["gate"]["after"] == "downgrades (X04)"
assert I["core.outcome_kind"]["pass"] == I["core.has_human_oversight"]["pass"] == 2

# ---------------------------------------------------------------- 7 a: cross-page relation order
P = "items/core.activity_relation_cross_page/long_page_rule/order"
old = get(P)
new = []
for c in old:
    new.append(c)
    if c == "component_of_program":
        new.append("has_component")
    if c == "governs":
        new.append("governed_by")
assert set(new) - {"unknown"} == {v["code"] for v in I["core.activity_relation_cross_page"]["values"]}
fix(f"R5-{n:02d}", "7 a", "set", "`has_component` right after `component_of_program`, `governed_by` right after `governs`", path=P, after=new); n += 1

# ---------------------------------------------------------------- 8 b: negative page verdicts
NEG = ["confirms_absence", "no_genai", "background_only", "event_only", "other_body"]
pv_codes = [v["code"] for v in I["core.page_verdict"]["values"]]
assert set(NEG) <= set(pv_codes)
assert "negative page verdicts (R-041)" in cb["vocabularies"]["support_status"]["status_by_answer"]
fix(f"R5-{n:02d}", "8 b", "add", "the negative page verdicts of R-041 as a list, referenced by the support-status rule "
    "(status_by_answer key \"negative page verdicts (R-041)\")", path="vocabularies/support_status/negative_page_verdicts",
    after={"item": "core.page_verdict", "values": NEG, "status_by_answer_key": "negative page verdicts (R-041)", "ruling": "RC-D-005 8 b"}); n += 1

# ---------------------------------------------------------------- 9 a: every part "not covered" on page_verdict
fix(f"R5-{n:02d}", "9 a", "add", "page_verdict: when every part answers \"not covered by this part\", the page answer is `not_assessable` "
    "(exception to R-044's \"not documented\")", path="items/core.page_verdict/long_page_rule/all_parts_not_covered",
    after={"value": "not_assessable", "exception_to": "R-044 (all-03 a, PI comment: \"not documented\")", "ruling": "RC-D-005 9 a"}); n += 1

# ---------------------------------------------------------------- 10 a: pooled fields use their own item's rule
P = "items/core.pooled_activity_fields/long_page_rule"
assert get(P) == {"rule": "per item (r2#6)"}
fix(f"R5-{n:02d}", "10 a", "set", "pooled_activity_fields: a recognised rule type; each pooled field combines by its own item's long_page_rule",
    path=P, after={"rule": "none", "pooled_fields": "each field uses its own item's long_page_rule", "source": "r2#6",
                   "ruling": "RC-D-005 10 a"}); n += 1

# ---------------------------------------------------------------- 11 a: scale number / unit pair
for a_, b_ in (("core.deployment_scale_number", "core.deployment_scale_unit"), ("core.deployment_scale_unit", "core.deployment_scale_number")):
    fix(f"R5-{n:02d}", "11 a", "add", "the number / unit pair counts as supported only if both halves pass the quote check",
        path=f"items/{a_}/support_pair", after={"with": b_, "supported_only_if": "both_halves_pass_quote_check", "ruling": "RC-D-005 11 a"}); n += 1

# ---------------------------------------------------------------- 12 a: `not_documented` offered as a jev choice
assert cb["vocabularies"]["missing"]["values"] == ["not_asked", "not_documented", "unknown", "_NA_"]
fix(f"R5-{n:02d}", "12 a", "add", "which missing label a jev question offers (`not_documented`) and which stay mechanical",
    path="vocabularies/missing/jev_choice",
    after={"offered": ["not_documented"], "mechanical": ["not_asked", "unknown", "_NA_"],
           "meaning": "each item's missing-label rule, named in items.<id>.jev_missing_choice", "ruling": "RC-D-005 12 a"}); n += 1
SILENT = "A silent page gets \"not documented\"; a page that mentions the matter but cannot be settled gets \"unknown\"."
NO_RULE, WITH_RULE, NOT_OFFERED = [], [], []
for k in CORE:
    it = I[k]
    if it["linkage"] != "jev_choice":
        continue
    rules = it["rules"] if isinstance(it["rules"], list) else []
    nd = [f"items/{k}/rules/{i}" for i, r in enumerate(rules) if isinstance(r, dict) and (
        r.get("role") == "missing label not_documented: meaning for this item" or r.get("text") == SILENT)]
    excl = [f"items/{k}/rules/{i}" for i, r in enumerate(rules) if isinstance(r, dict) and r.get("role") == "none_documented against not_documented"]
    if excl:
        v = {"offered": [], "rule": excl, "why": "the item's rule says `not_documented` is not used for this item"}
        NOT_OFFERED.append(k)
    elif "not_documented" not in (it["missing_tokens"] if isinstance(it["missing_tokens"], list) else []):
        v = {"offered": [], "rule": "none", "why": "the item takes no `not_documented`"}
        NOT_OFFERED.append(k)
    elif nd:
        v = {"offered": ["not_documented"], "rule": nd}
        WITH_RULE.append(k)
    else:
        v = {"offered": ["not_documented"], "rule": "none", "why": "no item-level missing-label rule for `not_documented` (listed for a ruling)"}
        NO_RULE.append(k)
    fix(f"R5-{n:02d}", "12 a", "add", "missing label offered as a jev choice, with the rule that gives its meaning",
        path=f"items/{k}/jev_missing_choice", after=v); n += 1

# ---------------------------------------------------------------- 14 a: page_review_state pipelines
P = "items/core.page_review_state/pipelines"
fix(f"R5-{n:02d}", "14 a", "set", "page_review_state: procurement removed from its pipelines", path=P,
    after=[x for x in get(P) if x != "procurement"]); n += 1

# ---------------------------------------------------------------- P1 / P3 structural fixes
fams = []
for it in I.values():
    if it["family"] not in fams:
        fams.append(it["family"])
fix(f"R5-{n:02d}", "P1", "add", "vocabularies.family: the fixed family list (template field 2), in order of first use", path="vocabularies/family",
    after={"values": fams, "source": "the `family` of every item in the signed build"}); n += 1
R044 = ["confirms_activity", "ambiguous_attribution", "ambiguous_genai", "other_body", "event_only", "background_only",
        "confirms_absence", "no_genai", "not_assessable"]
spec = (ROOT / "planning/SPEC.md").read_text(encoding="utf-8")
assert "The S3 a order is: " + ", ".join(R044) + " (`not_assessable` last" in spec
assert set(R044) == set(pv_codes)
P = "items/core.page_verdict/long_page_rule"
assert get(P + "/order") == "S3 a"
fix(f"R5-{n:02d}", "P1", "set", "page_verdict priority order: the explicit S3 a list of SPEC R-044", path=P + "/order", after=R044); n += 1
fix(f"R5-{n:02d}", "P1", "add", "page_verdict two-tier rule, machine-readable: supported verdicts first, then failed ones, each tier in `order`",
    path=P + "/tier_order", after=["supported", "failed"]); n += 1
fix(f"R5-{n:02d}", "P1", "set", "page_verdict missing_tokens: `not_assessable` is a value of the item, not a missing label; the item takes "
    "none of the reserved labels (template: an explicit `none` where a field does not apply); its mechanical status is flagged by P3",
    path="items/core.page_verdict/missing_tokens", after="none"); n += 1
ix = pv_codes.index("not_assessable")
fix(f"R5-{n:02d}", "P3", "add", "not_assessable is never a jev choice (R-015: set mechanically, never a classifier answer)",
    path=f"items/core.page_verdict/values/{ix}/jev_choice", after=False); n += 1
# derivation entries: the draft slot becomes the rule entry itself (same text, same provenance keys)
for k in CORE:
    rules = I[k]["rules"]
    for i, r in enumerate(rules if isinstance(rules, list) else []):
        if isinstance(r, dict) and r.get("role") == "derivation" and "draft" in r and "text" not in r:
            after = dict(r["draft"])
            after.update({kk: vv for kk, vv in r.items() if kk != "draft"})
            fix(f"R5-{n:02d}", "P1", "set", "derivation rule as a text slot: the `draft` slot's keys lifted into the rule entry (text unchanged)",
                path=f"items/{k}/rules/{i}", after=after); n += 1
P = "items/core.observed_actor_role/long_page_rule"
b = get(P)
assert b["rule"] == "same_part_as" and b["fallback"] == "highest_probability"
fix(f"R5-{n:02d}", "P1", "set", "observed_actor_role: a recognised rule type (`highest_probability`, the signed fallback) with a first step "
    "`same_part_as` (the part that produced the relationship), as the scale unit's pairing step; text unchanged", path=P,
    after={"rule": "highest_probability", "first_step": {"same_part_as": b["item"]}, "text": b["text"]}); n += 1
AT_CODES = [v["code"] for v in I["core.activity_type"]["values"]]
for k in CORE:
    g = I[k]["gate"]
    if isinstance(g, dict) and "cells" in g and "key" in g:
        assert set(g["cells"].values()) <= {"ask", "not_asked"} and set(g["cells"]) == set(AT_CODES) | {"unknown"}, k
        after = {"item": g["key"], "values": [c for c, v in g["cells"].items() if v == "ask"]}
        after.update({kk: vv for kk, vv in g.items() if kk != "key"})
        fix(f"R5-{n:02d}", "P1", "set", "applicability table as the template's gate form: item core.activity_type + the types whose cell is "
            "`ask` (cells kept as the table; gated-out cells take `not_asked`)", path=f"items/{k}/gate", after=after); n += 1
for k, gk in (("core.reported_outcomes", "core.outcome_kind"), ("core.reported_incidents", "core.incident_kind")):
    g = I[k]["gate"]
    assert g == {"item": gk, "values": ["not none_reported"]}
    vals = [v["code"] for v in I[gk]["values"] if v["code"] != "none_reported"]
    fix(f"R5-{n:02d}", "P1", "set", "gate \"not none_reported\" as an explicit value list: the gate item's other values (missing labels do not "
        "open the gate)", path=f"items/{k}/gate", after={"item": gk, "values": vals, "as_ruled": "not none_reported"}); n += 1
# refs: the RC-D-005 ruling on each item a ruling changed
for k, r in (("core.activity_relation_cross_page", "RC-D-005 7 a"), ("core.page_verdict", "RC-D-005 8 b, 9 a, P3"),
             ("core.pooled_activity_fields", "RC-D-005 10 a"), ("core.deployment_scale_number", "RC-D-005 11 a"),
             ("core.deployment_scale_unit", "RC-D-005 11 a"), ("core.page_review_state", "RC-D-005 14 a")):
    P = f"items/{k}/refs"
    fix(f"R5-{n:02d}", r.split(" ", 1)[1], "set", "refs: the RC-D-005 ruling added", path=P, after=get(P) + [r]); n += 1

# ---------------------------------------------------------------- write json + md
DOC = {
    "format": "fixes-r5 v1: entries applied in order by build_skeleton.py apply_r5(); op set | add | delete; `before` is the exact value met",
    "status": "candidate for RC-D-005; applied rulings are the PI's (2026-10-30); the encodings are the integrator's P1 defaults, for PI review of the diff",
    "drafted_by": "subagent of the plan integrator, Claude Code, claude-opus-5-5, 2026-10-30",
    "ruling": RULING + ": \"1a, 2a, 3 subagent drafts all & I read and edit/confirm, 4 part of 3, 5 a, 6a, 7a, 8b, 9 a, 10a 11 a 12 a 13a 14a; accept all\"",
    "base_sha256": R5_BASE,
    "lists": {"12a_items_with_rule": WITH_RULE, "12a_items_without_rule": NO_RULE, "12a_items_not_offered": NOT_OFFERED},
    "fixes": FIXES,
}
out = T010 / "drafts/fixes-r5.json"
out.write_text(json.dumps(DOC, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def short(x, n_=160):
    s = json.dumps(x, ensure_ascii=False)
    return s if len(s) <= n_ else s[: n_ - 1] + "…"


md = ["# RC-D-005 candidate fixes (fixes-r5)", "",
      "Claude Code, claude-opus-5-5, subagent of the plan integrator, 2026-10-30. Generated by `drafts/fixes-r5-draft.py` from the signed "
      f"codebook (sha256 `{R5_BASE}`); applied by `build_skeleton.py --build r5-draft | r5-signoff`.", "",
      f"Ruling: {DOC['ruling']}. The encodings below are P1 defaults (\"mechanical structural fixes encoded by the integrator, PI reviews the diff\"). "
      "No slot text is written or edited; ruling 13 a removes slots.", "",
      f"{len(FIXES)} entries. Paths are those met when the entry applies (13 a drops run first, so later rule indexes are post-drop).", ""]
md += ["## Ruling 13 a: drafter-direction slots dropped, and whether each was carried out", "",
       "| Entry | Direction (verbatim) | Items | Carried out in the signed text | Evidence |", "|---|---|---|---|---|"]
for f in DROP_LOG:
    items = sorted({p.split("/")[1] for p in f["paths"]})
    ev = "; ".join(f"`{e['path']}`: \"{e['quote']}\"" for e in f["evidence"])
    md.append(f"| {f['id']} | {f['direction_text']} | {', '.join('`'+i+'`' for i in items)} | {f['carried_out']} | {f['evidence_note']} {ev} |")
md += ["", "## Ruling 12 a: `not_documented` offered as a jev choice", "",
       f"- Items whose rule names the meaning ({len(WITH_RULE)}): {', '.join('`'+k+'`' for k in WITH_RULE)}.",
       f"- Items with no item-level missing-label rule for `not_documented` ({len(NO_RULE)}), listed for a ruling: {', '.join('`'+k+'`' for k in NO_RULE)}.",
       f"- Not offered ({len(NOT_OFFERED)}): {', '.join('`'+k+'`' for k in NOT_OFFERED)}.", "",
       "## All entries", "", "| Entry | Ruling | Op | Path(s) | What | Before | After |", "|---|---|---|---|---|---|---|"]
for f in FIXES:
    ps = f.get("paths") or [f["path"]]
    pth = f"`{ps[0]}`" + (f" (+{len(ps) - 1} more)" if len(ps) > 1 else "")
    bef = short(f.get("before")) if f["op"] != "delete" or len(ps) == 1 else f"{len(ps)} slots, text: {short(f['direction_text'])}"
    aft = short(f["after_by_build"]) if "after_by_build" in f else ("(removed)" if f["op"] == "delete" else short(f.get("after")))
    md.append(f"| {f['id']} | {f['ruling']} | {f['op']} | {pth} | {f['what']} | {bef.replace('|', '/')} | {aft.replace('|', '/')} |")
(T010 / "drafts/fixes-r5.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
print(f"{len(FIXES)} entries; 13a groups {len(DROP_LOG)}; 12a with rule {len(WITH_RULE)}, without {len(NO_RULE)}, not offered {len(NOT_OFFERED)}")
