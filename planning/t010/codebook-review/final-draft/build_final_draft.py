"""Render the clean final draft of the G3O codebook (T-010, round 4) for the PI to read and approve.

Reads the built codebook (worktree codebook/codebook.yaml), drafts/fixes-r4.json and the round-3 section map; writes
codebook-final-draft.html and codebook-final-draft.md beside this script. Text is shown exactly as it stands in the
codebook; only provenance fields (sources, markers, origins, references) are left out of the body.
Run: python build_final_draft.py
"""
import hashlib
import html
import json
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
T010 = HERE.parent.parent
CB_PATH = Path("C:/Users/spaci/worktrees/G3O-integrator/codebook/codebook.yaml")
CB_BYTES = CB_PATH.read_bytes()
CB_SHA = hashlib.sha256(CB_BYTES).hexdigest()
CB = yaml.safe_load(CB_BYTES.decode("utf-8"))
FIXES = json.loads((T010 / "drafts/fixes-r4.json").read_text(encoding="utf-8"))["fixes"]
FIXNO = {f["id"]: int(f["id"][2:]) for f in FIXES}
PAREN = next(f for f in FIXES if f["id"] == "FX13")["action"]["paren"]
CONTENT_FIXES = {"FX01", "FX02", "FX04", "FX05", "FX06", "FX07", "FX09"}
SECTIONS = [("page", "What the page says"), ("activity", "Each activity on a page"), ("source", "Facts about each source page"),
            ("institution", "Results for the institution as a whole"), ("record", "Record-keeping on every row")]
ITEM_SECTION = json.loads((T010 / "codebook-review/round3/sections.json").read_text(encoding="utf-8"))["item_section"] | {
    "core.observed_actor_role": "activity", "core.support_rule_name": "record",
    "core.support_status_second_reason": "record", "core.date_upper_bound": "source"}
HIDE = {"source", "origin", "marker", "code_source", "approved_r4", "r4_fixes", "refs", "omitted_tail", "omitted_by", "applied_to",
        "edited_from", "frozen_text", "frozen_source", "transform", "inferred_cells", "status", "moved_from_values"}
HIDE_PREFIX = ("origin_before", "marker_before", "text_before", "source_before")
ANSWER = {"single": "one answer", "multi": "one or more answers", "yes_no": "yes or no", "text": "text", "number": "number",
          "date": "date", "list": "list"}
MISSING = {"not_asked": "not asked", "not_documented": "not documented", "unknown": "unknown", "_NA_": "no activity (_NA_)"}


def label(code: str) -> str:
    return str(code).replace("core.rule.", "").replace("core.", "").replace("_", " ")


def is_slot(x) -> bool:
    return isinstance(x, dict) and "text" in x and "origin" in x


def fixes_of(s: dict) -> list:
    return [x for x in str(s.get("r4_fixes", "")).split(", ") if x]


# ---------------------------------------------------------------- inline formatting
def inline_html(t: str) -> str:
    t = html.escape(t)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    return t.replace("\n", "<br>")


def slot_html(s: dict) -> str:
    if not isinstance(s.get("text"), str):
        return ""
    fx = fixes_of(s)
    body = inline_html(s["text"])
    content = [f for f in fx if f in CONTENT_FIXES]
    if content:
        tags = " ".join(f'<a class="tag" href="#fix-{FIXNO[f]}">proposed change {FIXNO[f]}</a>' for f in content)
        return f'<div class="new">{body} {tags}</div>'
    if fx:
        tags = ", ".join(str(FIXNO[f]) for f in fx)
        return f'<div class="cleaned" title="text cleaned by proposed change {tags}">{body} <a class="tag soft" href="#fix-{FIXNO[fx[0]]}">cleaned ({tags})</a></div>'
    return f"<div>{body}</div>"


def slot_md(s: dict) -> str:
    if not isinstance(s.get("text"), str):
        return ""
    fx = fixes_of(s)
    content = [f for f in fx if f in CONTENT_FIXES]
    tag = (" **[proposed change " + ", ".join(str(FIXNO[f]) for f in content) + "]**") if content else \
          ((" _[cleaned: change " + ", ".join(str(FIXNO[f]) for f in fx) + "]_") if fx else "")
    return s["text"].replace("\n", " ") + tag


def generic(x, md: bool, depth: int = 0) -> str:
    """Plain rendering of a structured field (gate, long-page rule, value parts), provenance left out."""
    if is_slot(x):
        return slot_md(x) if md else slot_html(x)
    if isinstance(x, dict):
        rows = []
        for k, v in x.items():
            if k in HIDE or k.startswith(HIDE_PREFIX) or v in (None, "none"):
                continue
            if k == "text" and is_slot(v):
                rows.append(generic(v, md, depth + 1))
                continue
            val = generic(v, md, depth + 1)
            if val:
                rows.append((f"{'  ' * depth}- {label(k)}: {val}") if md else f"<li><span class='k'>{html.escape(label(k))}</span> {val}</li>")
        if not rows:
            return ""
        return ("\n" + "\n".join(rows)) if md else "<ul class='kv'>" + "".join(r if r.startswith("<li") else f"<li>{r}</li>" for r in rows) + "</ul>"
    if isinstance(x, list):
        if all(isinstance(v, str) for v in x):
            return ", ".join((f"`{v}`" if md else f"<code>{html.escape(v)}</code>") for v in x)
        parts = [generic(v, md, depth + 1) for v in x]
        return ("\n".join(f"{'  ' * depth}- {p}" for p in parts if p)) if md else "<ul>" + "".join(f"<li>{p}</li>" for p in parts if p) + "</ul>"
    if isinstance(x, bool):
        return "yes" if x else "no"
    x = str(x)
    if x in CB["shared_rules"]:
        return f"shared rule *{label(x)}*" if md else f"shared rule <a href='#{x}'>{html.escape(label(x))}</a>"
    if re.fullmatch(r"[a-z_0-9.:]+", x):
        return f"`{x}`" if md else f"<code>{html.escape(x)}</code>"
    x = re.sub(PAREN, "", x)     # structural labels only (not wording slots): drop bracketed reference codes for reading
    return x if md else inline_html(x)


def values_block(vals, md: bool) -> str:
    if not isinstance(vals, list):
        return generic(vals, md) if isinstance(vals, dict) else ""
    out = []
    for v in vals:
        if not isinstance(v, dict) or "code" not in v:
            continue
        d = v.get("definition")
        dt = (slot_md(d) if md else slot_html(d)) if is_slot(d) else ""
        out.append(f"- `{v['code']}` — {dt}" if md else f"<li><code class='val'>{html.escape(v['code'])}</code>{dt}</li>")
    return "\n".join(out) if md else "<ul class='vals'>" + "".join(out) + "</ul>"


def values_parts(vals: dict, md: bool) -> str:
    """The two-part relationship item: each list part as a value list, the rest generic."""
    out = []
    for k, v in vals.items():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "code" in v[0]:
            out.append((f"**{label(k)}**\n" + values_block(v, md)) if md else f"<p class='part'>{html.escape(label(k))}</p>" + values_block(v, md))
        elif k not in HIDE:
            g = generic(v, md)
            if g:
                out.append(f"**{label(k)}**: {g}" if md else f"<p class='part'>{html.escape(label(k))}</p>{g}")
    return "\n".join(out)


def rules_block(rules, md: bool) -> str:
    if not isinstance(rules, list):
        return ""
    out = []
    for r in rules:
        if isinstance(r, str):
            out.append(f"- See shared rule: *{label(r)}*" if md else f"<li class='ref'>See shared rule: <a href='#{r}'>{html.escape(label(r))}</a></li>")
        elif is_slot(r):
            role = r.get("role")
            pre = (f"*{role}*: " if md else f"<span class='role'>{html.escape(role)}</span>") if role else ""
            out.append(f"- {pre}{slot_md(r)}" if md else f"<li>{pre}{slot_html(r)}</li>")
    return "\n".join(out) if md else "<ul class='rules'>" + "".join(out) + "</ul>"


def item_parts(it: dict, md: bool) -> list:
    rows = []
    if is_slot(it.get("instruction")) and isinstance(it["instruction"].get("text"), str):
        rows.append(("Question", slot_md(it["instruction"]) if md else slot_html(it["instruction"])))
    rows.append(("Answer", ANSWER.get(it.get("answer_type"), str(it.get("answer_type")))))
    if isinstance(it.get("values"), list) and it["values"]:
        rows.append(("Answers and their meaning", values_block(it["values"], md)))
    elif isinstance(it.get("values"), dict):
        rows.append(("Answers and their meaning", values_parts(it["values"], md)))
    if isinstance(it.get("rules"), list) and it["rules"]:
        rows.append(("Rules", rules_block(it["rules"], md)))
    if it.get("gate") not in (None, "none"):
        rows.append(("When it is asked", generic(it["gate"], md)))
    if it.get("long_page_rule") not in (None, "none"):
        rows.append(("Long pages: combining the parts", generic(it["long_page_rule"], md)))
    if it.get("order_tie_rule") not in (None, "none"):
        rows.append(("When several answers fit", label(it["order_tie_rule"])))
    mt = it.get("missing_tokens")
    if isinstance(mt, list) and mt:
        rows.append(("Missing labels it can take", ", ".join(MISSING.get(m, m) for m in mt)))
    meta = f"{label(it.get('coder', ''))}; {', '.join(it.get('level') or [])}; {it.get('visibility', '')}"
    rows.append(("Coded by; level; published", meta))
    return rows


def render_item(iid: str, it: dict, md: bool) -> str:
    name = label(it.get("name") or iid)
    rows = item_parts(it, md)
    if md:
        return f"### {name}\n\n<sub>{iid}</sub>\n\n" + "\n\n".join(f"**{k}.** {v}" for k, v in rows) + "\n"
    body = "".join(f"<div class='row'><div class='rk'>{html.escape(k)}</div><div class='rv'>{v}</div></div>" for k, v in rows)
    return f"<article class='item' id='{iid}'><h3>{html.escape(name)} <span class='iid'>{iid}</span></h3>{body}</article>"


def shared_section(md: bool) -> str:
    out = []
    voc = CB["vocabularies"]
    for k in ("missing", "provenance", "support_status", "relation", "genai_era_cutoff"):
        v = voc[k]
        title = {"missing": "Missing labels", "provenance": "How we know a value", "support_status": "Quote support status",
                 "relation": "Links between activities", "genai_era_cutoff": "Generative-AI era cutoff"}[k]
        parts = []
        if isinstance(v, dict):
            if isinstance(v.get("values"), list) and v["values"] and isinstance(v["values"][0], dict):
                parts.append(("Values", values_block(v["values"], md)))
            elif isinstance(v.get("values"), list):
                parts.append(("Values", generic(v["values"], md)))
            rest = {kk: vv for kk, vv in v.items() if kk != "values"}
            g = generic(rest, md)
            if g:
                parts.append(("Rules", g))
        out.append((title, f"vocabularies.{k}", parts))
    for sid, rules in CB["shared_rules"].items():
        out.append((label(sid).capitalize(), sid, [("Rule", generic(rules, md))]))
    for cid, c in CB["combining_conventions"].items():
        out.append(("Combining long pages: " + label(cid), f"combining_conventions.{cid}", [("Rule", generic(c, md))]))
    if md:
        return "\n".join(f"### {t}\n\n<sub>{i}</sub>\n\n" + "\n\n".join(f"**{k}.** {v}" for k, v in p) + "\n" for t, i, p in out)
    return "".join(f"<article class='item' id='{i}'><h3>{html.escape(t)} <span class='iid'>{i}</span></h3>"
                   + "".join(f"<div class='row'><div class='rk'>{html.escape(k)}</div><div class='rv'>{v}</div></div>" for k, v in p)
                   + "</article>" for t, i, p in out)


def whats_new(md: bool) -> str:
    dropped = CB["release"].get("r4_dropped", [])
    lines = []
    for f in FIXES:
        opt = next(o for o in f["options"] if o["id"] == f["default"])
        extra = ""
        if f["id"] == "FX08":
            extra = " Dropped: " + "; ".join(f"“{d['text'][:90]}{'…' if len(d['text']) > 90 else ''}”" for d in dropped) + "."
        n = FIXNO[f["id"]]
        if md:
            lines.append(f"{n}. **{f['title']}.** {f['issue']} *Proposed:* {opt['label']}.{extra} (confidence {f['confidence']})")
        else:
            lines.append(f"<li id='fix-{n}'><strong>{html.escape(f['title'])}.</strong> {inline_html(f['issue'])} "
                         f"<span class='prop'>Proposed: {inline_html(opt['label'])}.</span>{inline_html(extra)} "
                         f"<span class='conf'>confidence {f['confidence']}</span></li>")
    return "\n".join(lines) if md else "<ol class='fixes'>" + "".join(lines) + "</ol>"


def main() -> None:
    by_sec = {k: [] for k, _ in SECTIONS}
    modules = []
    for iid, it in CB["items"].items():
        sec = ITEM_SECTION.get(iid, "modules") if iid.startswith("core.") else "modules"
        (modules if sec == "modules" else by_sec[sec]).append((iid, it))
    n_core = sum(len(v) for v in by_sec.values())
    intro = (f"This is the whole codebook for release 2.7 as it would be signed: {n_core} items in five sections, then the shared lists "
             f"and rules. Every text is the approved wording; the {len(FIXES)} proposed changes listed first are the only text you "
             "have not yet seen. Changed text is highlighted where it appears.")
    # ---- markdown
    md = [f"# G3O codebook 2.7 — final draft for approval", "",
          f"Built from `codebook/codebook.yaml`, sha256 `{CB_SHA}`. Not signed; release label and version fields are set at sign-off.", "",
          intro, "", "## What's new since your last approval (proposed changes, pending your approval)", "", whats_new(True), ""]
    for k, title in SECTIONS:
        md += [f"## {title}", ""] + [render_item(i, it, True) for i, it in by_sec[k]]
    md += ["## Shared lists, rules and conventions", "", shared_section(True), "",
           "## Procurement and AI-text modules", "",
           f"{len(modules)} placeholder items for the procurement and AI-text pipelines stay outside the 2.7 build; they move over in a later release.", ""]
    (HERE / "codebook-final-draft.md").write_text("\n".join(md), encoding="utf-8")
    # ---- html
    nav = "".join(f"<a href='#sec-{k}'>{html.escape(t)}</a>" for k, t in SECTIONS) + "<a href='#sec-shared'>Shared lists and rules</a>"
    secs = "".join(f"<section id='sec-{k}'><h2>{html.escape(t)}</h2>" + "".join(render_item(i, it, False) for i, it in by_sec[k]) + "</section>"
                   for k, t in SECTIONS)
    page = TEMPLATE.format(sha=CB_SHA, intro=html.escape(intro), new=whats_new(False), nav=nav, secs=secs,
                           shared=shared_section(False), nmod=len(modules))
    (HERE / "codebook-final-draft.html").write_text(page, encoding="utf-8")
    print(f"items={n_core} modules={len(modules)} fixes={len(FIXES)} codebook sha256={CB_SHA[:16]} "
          f"html={hashlib.sha256((HERE / 'codebook-final-draft.html').read_bytes()).hexdigest()[:16]} -> {HERE}")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>G3O Codebook Draft</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1f2328;--muted:#6a6f76;--line:#e3e0d8;--card:#ffffff;--accent:#2f5d8a;--new:#fff3c4;--newline:#d9a400;--soft:#eef2f6;--code:#f1efe9}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#16181b;--fg:#e6e6e3;--muted:#9aa0a6;--line:#2c3036;--card:#1d2024;--accent:#8ab4e0;--new:#3a3115;--newline:#c9a227;--soft:#232a33;--code:#262a30}}}}
:root[data-theme="dark"]{{--bg:#16181b;--fg:#e6e6e3;--muted:#9aa0a6;--line:#2c3036;--card:#1d2024;--accent:#8ab4e0;--new:#3a3115;--newline:#c9a227;--soft:#232a33;--code:#262a30}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:900px;margin:0 auto;padding:24px 16px 80px}}
h1{{font-size:1.6rem;margin:0 0 4px}} h2{{font-size:1.3rem;margin:40px 0 12px;padding-top:8px;border-top:2px solid var(--line)}}
h3{{font-size:1.05rem;margin:0 0 10px}}
.meta{{color:var(--muted);font-size:.85rem;word-break:break-all}}
nav{{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.9rem;z-index:2}}
nav a{{color:var(--accent);text-decoration:none}}
.box{{background:var(--new);border-left:4px solid var(--newline);padding:12px 16px;border-radius:6px;margin:20px 0}}
.box h2{{border:0;margin:0 0 8px;padding:0}}
.fixes li{{margin:0 0 10px}} .prop{{font-weight:600}} .conf{{color:var(--muted);font-size:.8rem}}
.item{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin:12px 0}}
.iid{{color:var(--muted);font-weight:400;font-size:.75rem;margin-left:6px}}
.row{{display:grid;grid-template-columns:170px 1fr;gap:4px 14px;padding:6px 0;border-top:1px dashed var(--line)}}
.rk{{color:var(--muted);font-size:.85rem}} .rv{{min-width:0;overflow-wrap:anywhere}}
@media (max-width:600px){{.row{{grid-template-columns:1fr}}}}
ul{{margin:0;padding-left:20px}} li{{margin:3px 0}}
ul.vals{{list-style:none;padding-left:0}} ul.vals li{{padding:3px 0}}
code{{background:var(--code);padding:0 4px;border-radius:4px;font-size:.9em}}
code.val{{font-weight:600;margin-right:8px}}
.role{{display:inline-block;color:var(--muted);font-size:.8rem;margin-right:6px;font-style:italic}}
.part{{margin:8px 0 2px;font-weight:600}} .k{{color:var(--muted);margin-right:4px}}
.new{{background:var(--new);border-left:3px solid var(--newline);padding:2px 8px;border-radius:4px}}
.cleaned{{border-left:3px dotted var(--line);padding-left:8px}}
.tag{{font-size:.75rem;color:var(--accent);white-space:nowrap}} .tag.soft{{color:var(--muted)}}
.rv > div{{display:block}}
</style></head><body><main>
<h1>G3O codebook 2.7 — final draft for approval</h1>
<p class="meta">Built from codebook/codebook.yaml · sha256 {sha} · not signed; the release label and version fields are set at sign-off.</p>
<p>{intro}</p>
<div class="box"><h2>What's new since your last approval</h2><p>Proposed changes, pending your approval. Each is highlighted where it appears; “cleaned” marks text from which only notes, planning remarks or reference codes were removed.</p>{new}</div>
<nav>{nav}</nav>
{secs}
<section id="sec-shared"><h2>Shared lists, rules and conventions</h2>{shared}</section>
<section><h2>Procurement and AI-text modules</h2><p>{nmod} placeholder items for the procurement and AI-text pipelines stay outside the 2.7 build; they move over in a later release.</p></section>
</main></body></html>
"""

if __name__ == "__main__":
    main()
