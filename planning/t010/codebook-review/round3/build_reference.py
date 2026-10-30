"""Build the plain value-definition reference page for codebook review round 3.

Reads the draft codebook and the four agent drafts; writes codebook-reference.html and sections.json
beside this script. Draft-only values are marked "draft". Run: python -I build_reference.py
"""
import html
import json
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CB = yaml.safe_load(Path("C:/Users/spaci/worktrees/G3O-integrator/codebook/codebook.yaml").read_text(encoding="utf-8"))
DR = HERE.parent.parent / "drafts"
VL = json.loads((DR / "value-lists.json").read_text(encoding="utf-8"))
SECTIONS = [
    ("page", "What the page says", lambda it: it["level"][0] == "page"),
    ("activity", "Each activity on a page", lambda it: it["level"][0] == "activity" and it["pass"] != "stage6" and not it["id"].startswith(("core.n_sources", "core.cx_display", "core.confidence"))),
    ("source", "Facts about each source page", lambda it: it["level"][0] == "source"),
    ("institution", "Results for the institution as a whole", lambda it: it["level"][0] == "institution" or it["pass"] == "stage6" or it["id"] in ("core.n_sources", "core.cx_display_rollup", "core.confidence")),
    ("record", "Record-keeping on every row", lambda it: it["level"][0] in ("row", "run")),
    ("modules", "Procurement and AI-text modules (placeholders)", lambda it: it["level"][0] in ("contract", "document")),
]


def sec_of(it):
    if not it["id"].startswith("core."):
        return "modules"
    for k, _, f in SECTIONS:
        if f(it):
            return k
    return "record"


def draft_codes(target):
    for l in VL["lists"]:
        if l["target"] == target:
            return [v["code"] for v in l.get("values", [])]
    return []


def t(slot):
    if isinstance(slot, dict) and slot.get("text"):
        return slot["text"]
    return None


def esc(s):
    return html.escape(s or "")


rows, secmap = [], {}
for k, label, _ in SECTIONS:
    items = [it for it in CB["items"].values() if sec_of(it) == k]
    rows.append(f'<h2 id="{k}">{esc(label)}</h2>')
    for it in items:
        secmap[it["id"]] = k
        q = t(it["instruction"]) if isinstance(it["instruction"], dict) else None
        rows.append(f'<section id="{esc(it["id"])}"><h3>{esc(it["name"].replace("_", " "))} <code>{esc(it["name"])}</code></h3>')
        if q:
            rows.append(f'<p class="q">Question: {esc(q)}</p>')
        vals = it["values"]
        if isinstance(vals, list):
            rows.append("<table>")
            for v in vals:
                d = t(v["definition"])
                rows.append(f'<tr><td><code>{esc(v["code"])}</code></td><td>{esc(d) if d else "<em>no wording yet</em>"}</td></tr>')
            rows.append("</table>")
        elif vals == "open":
            codes = draft_codes(it["id"])
            if codes:
                rows.append('<table class="draft">' + "".join(f'<tr><td><code>{esc(c)}</code></td><td><em>draft value, no wording yet</em></td></tr>' for c in codes) + "</table>")
            else:
                rows.append("<p><em>values not drafted yet</em></p>")
        else:
            rules = it["rules"] if isinstance(it["rules"], list) else []
            first = next((t(r) for r in rules if isinstance(r, dict) and t(r)), None)
            rows.append(f'<p class="how">How it is filled: {esc(first) if first else "<em>no wording yet</em>"}</p>')
        rows.append("</section>")
rows.append('<h2 id="shared">Shared lists</h2>')
for l in VL["lists"]:
    if not l["target"].startswith("core."):
        rows.append(f'<section><h3>{esc(l["target"])}</h3><table class="draft">' + "".join(
            f'<tr><td><code>{esc(v["code"])}</code></td><td>{esc(v.get("source_phrase"))}</td></tr>' for v in l.get("values", [])) + "</table></section>")
secmap["shared"] = "shared"
nav = " · ".join(f'<a href="#{k}">{esc(lbl)}</a>' for k, lbl, _ in SECTIONS) + ' · <a href="#shared">Shared lists</a>'
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codebook reference</title><style>
:root{{--bg:#fff;--fg:#1d1d1f;--mute:#666;--line:#e3e3e3;--draft:#fff7e0}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161616;--fg:#eee;--mute:#aaa;--line:#333;--draft:#3a3220}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px}}
h2{{margin-top:2em;border-bottom:2px solid var(--line)}} h3{{margin:1.2em 0 .3em;font-size:1.05em}} h3 code{{color:var(--mute);font-weight:normal;font-size:.85em}}
table{{border-collapse:collapse;width:100%}} td{{border-top:1px solid var(--line);padding:4px 8px;vertical-align:top}} td:first-child{{white-space:nowrap;width:1%}}
table.draft td{{background:var(--draft)}} .q,.how{{color:var(--mute);margin:.2em 0}} nav{{font-size:.9em}}
</style></head><body><h1>Codebook reference: values and definitions</h1>
<p>Draft, 2026-10-29. Prepared by Claude Code (claude-opus-5-5), plan integrator. Every definition is copied word for word from its source; nothing here is signed. Shaded rows are draft values without wording.</p>
<nav>{nav}</nav>{''.join(rows)}</body></html>"""
(HERE / "codebook-reference.html").write_text(page, encoding="utf-8")
(HERE / "sections.json").write_text(json.dumps({"sections": [[k, l] for k, l, _ in SECTIONS] + [["shared", "Shared lists"]], "item_section": secmap}, indent=1), encoding="utf-8")
print("file:///" + str(HERE / "codebook-reference.html").replace("\\", "/"))
