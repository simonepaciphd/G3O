"""Convert the three codebook-review JSONs into one decision-page-v1 JSON."""
import json
import sys
from pathlib import Path

S = Path(sys.argv[1])
OUT = Path(sys.argv[2])
core = json.loads((S / "review-core.json").read_text(encoding="utf-8"))
cx = json.loads((S / "review-cx-support.json").read_text(encoding="utf-8"))
xp = json.loads((S / "review-cross-pipeline.json").read_text(encoding="utf-8"))

SEV = {"high": 0, "medium": 1, "low": 2}


def opt(o, substantive=True):
    d = {k: (o.get(k) or "").strip() for k in ("label", "mechanism", "benefits", "risks", "commits_to")}
    oid = (o.get("id") or "").strip().replace(" ", "-") or "x"
    if oid in ("pending", "other"):
        oid = oid + "-opt"
    d["id"] = oid
    for k in ("mechanism", "benefits", "risks"):
        d[k] = d[k] or "Not stated by the reviewer."
    if substantive:
        d["commits_to"] = d["commits_to"] or "Not stated by the reviewer."
    return d


def dedupe(opts):
    seen, out = set(), []
    for o in opts:
        base, n = o["id"], 2
        while o["id"] in seen:
            o["id"] = f"{base}-{n}"
            n += 1
        seen.add(o["id"])
        out.append(o)
    return out


def item_from_review(it, area):
    findings = sorted(it.get("findings") or [], key=lambda f: SEV.get(f.get("severity"), 3))
    nhigh = sum(1 for f in findings if f.get("severity") == "high")
    frozen = " **Frozen CX-01.2 wording: any change needs re-signature (R-025).**" if it.get("frozen") else ""
    kind_word = "Proposed addition" if it.get("kind") == "addition" else "Existing item"
    situation = (
        f"{kind_word} · linkage: `{it.get('linkage', '?')}` · source: `{it.get('current_source') or 'none'}` · "
        f"{len(findings)} finding(s), {nhigh} high.{frozen}"
    )
    if it.get("depends_on"):
        situation += " Depends on: " + ", ".join(it["depends_on"]) + "."
    body = []
    if it.get("current_text"):
        body.append("**Current text (verbatim)**\n\n" + it["current_text"].strip())
    if findings:
        body.append("**Reviewer findings**\n\n" + "\n".join(
            f"- **{f.get('severity', '?')}** · {f.get('type', '')}: {f.get('text', '').strip()} (`{f.get('evidence', '')}`)"
            for f in findings))
    if it.get("notes"):
        body.append("**Notes**\n\n" + it["notes"].strip())
    opts = dedupe([opt(o) for o in it.get("options") or []])
    return {
        "id": it["id"],
        "kind": "substantive",
        "title": it.get("name", ""),
        "situation": situation,
        "body_label": "Current wording and findings",
        "body": "\n\n".join(body) or "No current text.",
        "options": opts,
        "prompt": "Pick one, or write your own wording / line-edit here.",
    }


items = []
for it in core["items"]:
    items.append(item_from_review(it, "core"))
for it in cx["items"]:
    items.append(item_from_review(it, "cx"))

# Cross-pipeline: architecture choice first among the pipeline items.
items.append({
    "id": "ARCH",
    "kind": "substantive",
    "title": "How the single source of truth is built (decide first: the other items are coded into it)",
    "situation": "Ruling S1 makes the codebook the source of truth, linked by code to the jev prompts and the extractor, across pipelines. This item picks the form.",
    "options": dedupe([opt(o) for o in xp.get("architecture_options") or []]),
    "allow_multiple": False,
    "prompt": "Pick one or describe a variant.",
})
for p in xp.get("proposed_additions") or []:
    opts = dedupe([opt(o) for o in p.get("options") or []])
    items.append({
        "id": p["id"],
        "kind": "substantive",
        "title": f"{p.get('name', '')} ({p.get('pipeline', '')})",
        "situation": (p.get("situation") or "Proposed addition from the cross-pipeline review.") + f" Linkage: `{p.get('linkage', '?')}`.",
        "options": opts,
        "prompt": "Pick one, or write your own wording here.",
    })

items.insert(0, items.pop(next(i for i,x in enumerate(items) if x["id"]=="ARCH")))
conf = xp.get("conflicts") or []
cc = (core.get("cross_cutting") or []) + (cx.get("cross_cutting") or [])


def fmt_list(rows):
    out = []
    for r in rows:
        if isinstance(r, dict):
            sev = r.get("severity", "")
            txt = r.get("text") or r.get("description") or ""
            if r.get("title"):
                txt = f"**{r['title']}.** " + (r.get("detail") or txt)
            txt = txt or json.dumps(r, ensure_ascii=False)
            ev = r.get("evidence") or r.get("source") or ""
            if isinstance(ev, list):
                ev = "; ".join(map(str, ev))
            out.append(f"- {('**' + sev + '** · ') if sev else ''}{txt}{(' (`' + ev + '`)') if ev else ''}")
        else:
            out.append(f"- {r}")
    return "\n".join(out)


background = (
    "T-010 (G3O reclassification, Output Contract v2.7 / validate v1.5). Per your ruling S1 the codebook becomes the single source of truth, "
    "linked by code to the jev question sets and the extractor prompts, and shared by the procurement and AI-text-detection pipelines. "
    "Three fresh-context subagents (Claude Code, claude-opus-5-5) reviewed it adversarially, each item against the v2.5 contract on `main` (`375f1ff`), "
    "v2.6 (`052fcb2`, unpushed), the re-pilot 2 wording, CX-01.2 and SPEC v001.5. Every option other than `keep` was drafted by an agent; none carries a recommendation.\n\n"
    "Your choices seed the contract slots, and you still write or line-edit every coding rule before the hash (A-001). "
    "Changing a CX-01.2 item needs re-signature (R-025), and any enum change costs two version steps (C-007).\n\n"
    "**Cross-cutting findings**\n\n" + (fmt_list(cc) or "- none") +
    "\n\n**Cross-pipeline conflicts**\n\n" + (fmt_list(conf) or "- none")
)

page = {
    "format": "decision-page-v1",
    "id": "codebook-review-2026-10-29",
    "title": "G3O codebook v2.7 review",
    "eyebrow": "G3O · reclass T-010 · codebook review",
    "prepared": "2026-10-29",
    "prepared_by": {"harness": "claude-code", "model": "claude-opus-5-5", "session": "20261029-claude-v2-c47ab81795f0f95a"},
    "project": "g3o",
    "background": background,
    "sources": [
        {"label": "Delta RC-D-002 (proposed)", "href": "../../deltas/RC-D-002.md"},
        {"label": "SPEC v001.5", "href": "../../SPEC.md"},
        {"label": "Reviewer JSON (core)", "href": "review-core.json"},
        {"label": "Reviewer JSON (CX/support/Stage 6)", "href": "review-cx-support.json"},
        {"label": "Reviewer JSON (cross-pipeline)", "href": "review-cross-pipeline.json"},
    ],
    "items": items,
}
OUT.write_text(json.dumps(page, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(items)} items -> {OUT}")
