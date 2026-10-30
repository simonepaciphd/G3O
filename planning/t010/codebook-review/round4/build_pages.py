"""Build the round-4 wording-review pages (T-010), one per section of the codebook.

PI ruling 2026-10-30, chat: "a (subagent), accept all" (planning/t010/t010-rulings.md).
Reads the codebook, the round-4 definition drafts (../../drafts/definitions-r4.json) and the
round-3 section map; writes one decision-page-v1 JSON per page plus a slot map (*.map.json),
then builds each page with the shared decision-page builder. Every wording slot of the six
review kinds is shown; directions for the questionnaire and archived signed text are not.
The procurement and AI-text placeholders are left out.

Run: python build_pages.py
"""
import json
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
T010 = HERE.parent.parent
CB_PATH = Path("C:/Users/spaci/worktrees/G3O-integrator/codebook/codebook.yaml")
DEFS = T010 / "drafts" / "definitions-r4.json"
SECTIONS = T010 / "codebook-review" / "round3" / "sections.json"
BUILDER = Path("C:/Users/spaci/repos/ai-os-private/personal/skills/_assets/decision-page/build_decision_page.py")
PREPARED_BY = {"harness": "Claude Code", "model": "claude-opus-5-5",
               "session": "drafting subagent of integrator session 20261030-claude-v2-2b8200388885f8f9"}
TODAY = "2026-10-30"

# The six review kinds, keyed by marker prefix, with the label the PI reads.
KINDS = OrderedDict([
    ("SPEC text", "Plan text"),
    ("no approved wording", "New agent draft (round 4)"),
    ("round-3 ruling option text", "Option text you chose in round 3"),
    ("Agent draft", "Agent edit of the signed questionnaire"),
    ("PI-approved text", "Text you approved on 30 October"),
    ("v2.5 text", "Old production text (version 2.5): rewrite or delete"),
])
SKIPPED = ("direction for CX-01.3", "archived signed text")
ORIGIN = {"r1": "from review round 1", "r2": "from review round 2", "spec": "from the specification",
          "delta": "from a plan change", "repilot": "re-pilot wording", "repilot_q": "re-pilot question wording",
          "v25": "version 2.5 contract"}
NEW_ITEM_SECTION = {"core.observed_actor_role": "activity", "core.support_rule_name": "record",
                    "core.support_status_second_reason": "record", "core.date_upper_bound": "source"}
PAGE_LABEL = {"page": "What the page says", "activity": "Each activity on a page", "source": "Facts about each source page",
              "institution": "Results for the institution as a whole", "record": "Record-keeping on every row",
              "shared": "Shared lists, rules and conventions"}
ACTIVITY_PARTS = 3
# Overlap pairs (P4, accepted 2026-10-30): (owner, first slot path suffix, second slot path suffix).
OVERLAPS = [
    ("core.support_status", "rules/0", "rules/3", "the list of support statuses and which answers take which status"),
    ("core.has_genai_activity", "rules/0", "rules/2", "how the institution-level rule treats unresolved and not-assessable pages"),
    ("core.observed_actor_relationship", "rules/0", "rules/6", "when the searched institution's role is asked"),
    ("core.observed_actor_relationship", "rules/0", "rules/8", "how the relationship and role are published as one column"),
    ("vocabularies.support_status", "text", "status_by_answer/text", "the list of support statuses and which answers take which status"),
]
NOT_REQUIRED_SLOT = ("vocabularies.support_status", "rules/2")
LEVEL = {"page": "per page", "activity": "per activity", "source": "per source page", "institution": "per institution",
         "row": "on every row", "run": "per run"}


def kind_of(marker):
    for k in KINDS:
        if marker.startswith(k):
            return k
    if marker.startswith(SKIPPED):
        return None
    raise SystemExit(f"unknown marker: {marker!r}")


def slots_in(x, p=()):
    out = []
    if isinstance(x, dict):
        if "marker" in x and "text" in x:
            out.append((p, x))
        for k, v in x.items():
            out += slots_in(v, p + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            out += slots_in(v, p + (i,))
    return out


def node_at(root, path):
    for k in path:
        root = root[k]
    return root


def where(owner_node, rel):
    """Plain label for a slot's place inside its item."""
    if rel and rel[0] == "values" and len(rel) >= 3:
        if isinstance(rel[1], int):
            return f"Value `{owner_node['values'][rel[1]]['code']}`"
        if isinstance(rel[2], int):
            part = {"relationship": "Relationship value", "searched_institution_role": "Role value"}.get(rel[1], rel[1])
            return f"{part} `{owner_node['values'][rel[1]][rel[2]]['code']}`"
        if rel[1] == "role_gate":
            return "When the role is asked"
    head = rel[0] if rel else "text"
    names = {"instruction": "Question", "rules": "Rule", "gate": "When it is asked", "long_page_rule": "Long-page rule",
             "translation_v25": "Link to the version 2.5 data", "text": "Wording", "date_origin_map": "Date-origin map",
             "status_by_answer": "Status by answer", "published_summary_map": "Published-summary map",
             "na_label": "Label for rows with no activity", "cx_mapping_row": "Questionnaire map row",
             "cx_mapping_row_location": "Where the map row lives"}
    label = names.get(head, str(head).replace("_", " ").capitalize())
    tail = [str(x).replace("_", " ") for x in rel[1:] if not isinstance(x, int) and x not in ("text",)]
    return label + (f" ({', '.join(tail)})" if tail else "")


def owner_title(owner, node):
    if owner.startswith("core."):
        return node.get("name", owner[5:]).replace("_", " ")
    if owner.startswith("vocabularies."):
        return "Shared list: " + {"provenance": "how we know", "missing": "missing-answer labels",
                                  "support_status": "support status"}.get(owner.split(".", 1)[1], owner.split(".", 1)[1].replace("_", " "))
    if owner.startswith("shared_rules."):
        return "Shared rule: " + owner.split(".", 1)[1].replace("core.rule.", "").replace("_", " ")
    if owner.startswith("combining_conventions."):
        return "Long-page convention: " + owner.split(".", 1)[1].replace("_", " ")
    if owner.startswith("retired."):
        return "Retired item: " + str(node.get("name") or node.get("id") or owner).replace("core.", "").replace("_", " ")
    return owner


def main():
    cb = yaml.safe_load(CB_PATH.read_text(encoding="utf-8"))
    defs = {e["slot"]: e for e in json.loads(DEFS.read_text(encoding="utf-8"))["entries"]}
    item_section = json.loads(SECTIONS.read_text(encoding="utf-8"))["item_section"] | NEW_ITEM_SECTION

    owners = OrderedDict()  # owner -> {"section", "node", "slots": [(rel_path, slot)]}
    totals, skipped, modules = Counter(), Counter(), Counter()
    for p, s in slots_in(cb):
        k = kind_of(s["marker"])
        if p[0] == "items":
            owner, root, rel, sec = p[1], cb["items"][p[1]], p[2:], item_section[p[1]]
        elif p[0] == "retired":
            owner, root, rel, sec = f"retired.{p[1]}", cb["retired"][p[1]], p[2:], "shared"
        elif p[0] in ("vocabularies", "shared_rules", "combining_conventions"):
            owner, root, rel, sec = f"{p[0]}.{p[1]}", node_at(cb, p[:2]), p[2:], "shared"
        else:
            raise SystemExit(f"slot outside known blocks: {p}")
        if k is None:
            skipped[s["marker"][:24]] += 1
            continue
        if sec == "modules":
            modules[k] += 1
            continue
        totals[k] += 1
        o = owners.setdefault(owner, {"section": sec, "node": root, "slots": []})
        o["slots"].append(("/".join(map(str, p)), rel, s, k))

    # pages: activity split into parts of similar slot counts
    by_sec = OrderedDict((s, [o for o, v in owners.items() if v["section"] == s]) for s in PAGE_LABEL)
    pages = []
    for sec, own in by_sec.items():
        if sec != "activity":
            pages.append((sec, None, own))
            continue
        n_all = sum(len(owners[o]["slots"]) for o in own)
        part, acc, cur = 1, 0, []
        for o in own:
            cur.append(o)
            acc += len(owners[o]["slots"])
            if acc >= n_all * part / ACTIVITY_PARTS and part < ACTIVITY_PARTS:
                pages.append((sec, part, cur))
                part, cur = part + 1, []
        pages.append((sec, part, cur))

    report = []
    for n_page, (sec, part, own) in enumerate(pages, 1):
        pid = f"t010-r4-{sec}" + (f"-{part}" if part else "")
        title = f"Codebook wording review: {PAGE_LABEL[sec]}" + (f" (part {part} of {ACTIVITY_PARTS})" if part else "")
        items, smap, counts = [], {}, Counter()
        has_flag = any(o == NOT_REQUIRED_SLOT[0] for o in own)
        n_slots = sum(len(owners[o]["slots"]) for o in own)
        items.append({
            "id": "ALL", "kind": "review", "title": "Batch approval for this whole page",
            "situation": (f"This page shows {n_slots} wording slots in {len(own)} items. Choose the batch option to approve every slot "
                          "you do not mark in an item card below; any item card you answer still overrides it for that item."),
            "options": [{"id": "approve-unmarked", "label": "Approve every slot on this page that I do not mark below"},
                        {"id": "no-batch", "label": "No batch approval: only my item answers count"}],
        })
        if has_flag:
            path = NOT_REQUIRED_SLOT
            items.append({
                "id": "F1", "kind": "review", "title": "Needs your sentence: the support status \"Not required\"",
                "situation": ("After the cut you chose on 30 October, the option text for this status reads only \"Not required\". "
                              "It needs your sentence saying which answers take this status. The status list you approved on "
                              "30 October gives them: not documented, unknown, no, and negative page verdicts."),
                "body": "**Current text:** \"Not required\"", "body_label": "Current text",
                "options": [{"id": "my-sentence", "label": "Use my sentence (in the comments)"},
                            {"id": "agent-draft", "label": "Draft one from the approved list, for my next review"}],
                "prompt": "Your sentence for \"Not required\"",
            })
            smap["F1"] = {"owner": path[0], "slot": f"{path[0].replace('.', '/', 1)}/{path[1]}"}
        n_item = 0
        for o in own:
            v = owners[o]
            n_item += 1
            cid = f"I{n_item:02d}"
            node = v["node"]
            lines, slot_ids = [], {}
            for i, (full, rel, s, k) in enumerate(v["slots"], 1):
                counts[k] += 1
                text = defs[full]["text"] if k == "no approved wording" else s["text"]
                label = KINDS[k] + (f", {ORIGIN[s.get('origin')]}" if k == "SPEC text" and s.get("origin") in ORIGIN else "")
                extra = ""
                if k == "no approved wording":
                    dd = defs[full]
                    extra = f"\n_Draft certainty: {dd['confidence']}._" + (f" **Needs your decision:** {dd['pi_must_decide']}" if dd["pi_must_decide"] else "") \
                        + (f" _Note: {dd['notes']}_" if dd["notes"] else "")
                if (o, "/".join(map(str, rel))) == NOT_REQUIRED_SLOT:
                    extra += "\n**Needs your sentence (see the card at the top of this page).**"
                deletable = " · may be deleted" if k == "v2.5 text" else ""
                lines.append(f"**{i}. {where(node, rel)}** — {label}{deletable}\n{text}{extra}")
                slot_ids[str(i)] = full
            sit = []
            instr = node.get("instruction") if isinstance(node, dict) else None
            if isinstance(instr, dict) and instr.get("text"):
                sit.append(f"Question: {instr['text']}")
            lv = node.get("level") if isinstance(node, dict) else None
            if lv:
                sit.append("Recorded " + " and ".join(LEVEL.get(x, x) for x in lv) + ".")
            kinds_here = Counter(k for *_, k in v["slots"])
            sit.append(f"{len(v['slots'])} slots: " + "; ".join(f"{n} × {KINDS[k][0].lower() + KINDS[k][1:]}" for k, n in kinds_here.items()) + ".")
            items.append({
                "id": cid, "kind": "review", "title": owner_title(o, node), "situation": "\n\n".join(sit),
                "body": "\n\n".join(lines), "body_label": f"Show the {len(v['slots'])} wording slots",
                "options": [{"id": "approve-all", "label": "Approve every slot in this item as shown"},
                            {"id": "approve-edits", "label": "Approve, except the line-edits and deletions in my comments"},
                            {"id": "redraft", "label": "Redraft from my comments and show me again"}],
                "prompt": "By slot number, e.g. \"3: <your wording>\" · \"5 delete\" (old version-2.5 slots only) · \"2 ok\"",
            })
            smap[cid] = {"owner": o, "slots": slot_ids}
        for j, (o, a, b, what) in enumerate([x for x in OVERLAPS if x[0] in own], 1):
            cid_owner = next(c for c, m in smap.items() if m.get("owner") == o and "slots" in m)
            sm = smap[cid_owner]["slots"]
            pre = o.replace(".", "/", 1) if not o.startswith("core.") else f"items/{o}"
            na = next(n for n, full in sm.items() if full == f"{pre}/{a}")
            nb = next(n for n, full in sm.items() if full == f"{pre}/{b}")
            ta, tb = (node_at(cb, [int(x) if x.isdigit() else x for x in f"{pre}/{s}".split("/")])["text"] for s in (a, b))
            items.append({
                "id": f"O{j}", "kind": "review",
                "title": f"Same rule written twice: {owner_title(o, owners[o]['node'])}",
                "situation": (f"Two slots in the item card {cid_owner} say the same thing about {what}: slot {na} (plan text) "
                              f"and slot {nb} (text you approved on 30 October). You asked to keep one of each such pair."),
                "body": f"**Slot {na}, plan text:**\n{ta}\n\n**Slot {nb}, text you approved on 30 October:**\n{tb}",
                "body_label": "Compare the two texts",
                "options": [{"id": "keep-plan", "label": f"Keep slot {na} (plan text); delete slot {nb}"},
                            {"id": "keep-approved", "label": f"Keep slot {nb} (approved text); delete slot {na}"},
                            {"id": "keep-both", "label": "Keep both"}],
            })
            smap[f"O{j}"] = {"owner": o, "pair": [f"{pre}/{a}", f"{pre}/{b}"]}
        bg = [
            f"Review round 4 of the codebook wording. You chose on 30 October that agents draft the missing value "
            f"definitions and you review every wording slot here. This page covers **{PAGE_LABEL[sec].lower()}**"
            + (f", part {part} of {ACTIVITY_PARTS}" if part else "") + ".",
            "Each card is one codebook item. Open \"Show the wording slots\" to read them. Each slot is labelled with where its text came from:",
            "\n".join(f"- **{v}**" for v in KINDS.values()),
            "Answer per item: approve all, approve with line-edits or deletions in the comments (by slot number), or ask for a redraft. "
            "Deletion is open only for old version-2.5 slots and for one slot of each overlap pair. The batch card at the top approves "
            "everything you leave unmarked. No recommendation is given on any wording.",
            "New agent drafts carry a certainty mark; those marked **Needs your decision** rest on no ruling or text for some point.",
        ]
        if n_page == 1:
            bg.append("Not on any page: the procurement and AI-text placeholder items, which sit outside the version 2.7 build, "
                      "and the questionnaire directions and archived signed text, which are not wording to sign.")
        if has_flag:
            bg.append("**One slot needs your sentence:** the support status \"Not required\" (card F1).")
        data = {"format": "decision-page-v1", "id": pid, "title": title, "eyebrow": "G3O codebook · wording review round 4",
                "project": "G3O pipeline reclassification", "prepared": TODAY, "prepared_by": PREPARED_BY,
                "background": "\n\n".join(bg),
                "sources": [{"label": "Round-4 drafts (readable)", "href": "../../drafts/definitions-r4.md"},
                            {"label": "Round-3 codebook reference", "href": "../round3/codebook-reference.html"}],
                "items": items, "slot_map": smap}
        jp = HERE / f"{pid}.json"
        jp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (HERE / f"{pid}.map.json").write_text(json.dumps(smap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(BUILDER), str(jp)], capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"{pid}: builder failed\n{r.stderr}")
        html_text = (HERE / f"{pid}.html").read_text(encoding="utf-8")
        sha = json.loads(html_text.split('<script id="page-data" type="application/json">', 1)[1].split("</script>", 1)[0])["_sha256"]
        report.append({"page": pid, "items": len(own), "slots": sum(counts.values()), "by_kind": dict(counts),
                       "link": r.stdout.strip(), "page_sha256": sha})
    summary = {"pages": report, "slots_on_pages": dict(totals), "slots_on_pages_total": sum(totals.values()),
               "left_out_modules": dict(modules), "left_out_kinds": dict(skipped)}
    (HERE / "pages-index.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
