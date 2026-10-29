"""Build a compact, keyboard-driven codebook review page from the three reviewer JSONs.

Usage: python -I build_compact.py   (run from any cwd; paths are relative to this file)
Writes codebook-review-compact.html beside this script.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXCLUDE = {"X42"}  # non-codebook (scraper link persistence): asked in chat


def load(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


core, cx, xp = load("review-core.json"), load("review-cx-support.json"), load("review-cross-pipeline.json")
SEV = {"high": 0, "medium": 1, "low": 2}


def norm_opts(opts):
    out, seen = [], set()
    for o in opts or []:
        oid = (o.get("id") or "x").strip().replace(" ", "-")
        while oid in seen:
            oid += "'"
        seen.add(oid)
        out.append({"id": oid, "label": o.get("label", ""), "mech": o.get("mechanism", ""),
                    "ben": o.get("benefits", ""), "risk": o.get("risks", ""), "commits": o.get("commits_to", "")})
    return out


def ev(e):
    return "; ".join(map(str, e)) if isinstance(e, list) else (e or "")


sections = [("core", "Classification core", "C"), ("core-add", "Core additions", "A"),
            ("cx", "CX-01.2, support, sources, Stage 6", "X"), ("pipe", "Procurement & AI-text additions", "P")]
items = []
for it in core["items"] + cx["items"]:
    if it["id"] in EXCLUDE:
        continue
    f = sorted(it.get("findings") or [], key=lambda x: SEV.get(x.get("severity"), 3))
    sec = {"C": "core", "A": "core-add", "X": "cx"}[it["id"][0]]
    items.append({"id": it["id"], "sec": sec, "name": it.get("name", ""), "linkage": it.get("linkage", ""),
                  "frozen": bool(it.get("frozen")), "addition": it.get("kind") == "addition",
                  "current": it.get("current_text", ""), "source": it.get("current_source", ""),
                  "findings": [{"sev": x.get("severity", ""), "type": x.get("type", ""), "text": x.get("text", ""),
                                "ev": ev(x.get("evidence"))} for x in f],
                  "notes": it.get("notes", ""), "deps": it.get("depends_on") or [], "options": norm_opts(it.get("options"))})
for p in xp.get("proposed_additions") or []:
    items.append({"id": p["id"], "sec": "pipe", "name": f"{p.get('name', '')}", "linkage": p.get("linkage", ""),
                  "frozen": False, "addition": True, "pipeline": p.get("pipeline", ""),
                  "current": "", "source": "", "findings": [], "notes": p.get("situation", ""), "deps": [],
                  "options": norm_opts(p.get("options"))})

PAGE_ID, OUT_NAME, TITLE = "codebook-review-compact-2026-10-29", "codebook-review-compact.html", "G3O codebook v2.7 review"

if "--round2" in sys.argv:
    # Round 2: inconsistencies / gaps / additions over the round-1 rulings.
    PAGE_ID, OUT_NAME, TITLE = "codebook-review-r2-2026-10-29", "codebook-review-r2.html", "G3O codebook v2.7 review, round 2"
    TYPES = [("constraint-conflict", "Constraint conflicts"), ("inconsistency", "Inconsistencies"), ("gap", "Gaps"), ("addition", "Additions")]
    sections = [(k, t, "") for k, t in TYPES]
    items = []
    for fname in ("review-r2-consistency.json", "review-r2-impact.json"):
        if not (HERE / fname).exists():
            continue
        for it in load(fname)["items"]:
            sev = it.get("severity", "")
            items.append({"id": it["id"], "sec": it.get("type") if it.get("type") in dict(TYPES) else "gap",
                          "name": it.get("name", ""), "linkage": "involves " + ", ".join(it.get("involves") or []) if it.get("involves") else "",
                          "frozen": False, "addition": it.get("type") == "addition",
                          "current": "", "source": "",
                          "findings": [{"sev": sev, "type": it.get("type", ""), "text": it.get("situation", ""), "ev": ev(it.get("evidence"))}],
                          "notes": "", "deps": [], "options": norm_opts(it.get("options"))})
    # Pairs the two round-2 reviewers raised independently: decide them together.
    SEE = [("R2C01", "R2P01"), ("R2C18", "R2P07"), ("R2C23", "R2P21", "R2P22"), ("R2C08", "R2P02"),
           ("R2C10", "R2P24"), ("R2C16", "R2P05"), ("R2C35", "R2P27"), ("R2C12", "R2P08")]
    for it in items:
        for grp in SEE:
            if it["id"] in grp:
                it["notes"] = "Overlaps " + ", ".join(x for x in grp if x != it["id"]) + " (raised by the other reviewer); decide together."
    SEVO = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: ([k for k, _ in TYPES].index(x["sec"]), SEVO.get(x["findings"][0]["sev"], 3)))

data = {"id": PAGE_ID, "sections": sections, "items": items}
blob = json.dumps(data, ensure_ascii=False, sort_keys=True)
data["sha"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fafaf8;--panel:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e3e2dc;--acc:#2f5d8a;--accbg:#e8eff7;--hi:#b3261e;--hibg:#fbeae8;--md:#8a5a00;--mdbg:#fbf1df;--ok:#2e6b3a;--okbg:#e6f2e8;--code:#f1f0eb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;--mute:#9d9c95;--line:#33332f;--acc:#8db8e6;--accbg:#22303f;--hi:#f08b82;--hibg:#3a2120;--md:#e6b866;--mdbg:#352a17;--ok:#8fcf9b;--okbg:#1d3022;--code:#2a2a27}}
:root[data-theme=dark]{--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;--mute:#9d9c95;--line:#33332f;--acc:#8db8e6;--accbg:#22303f;--hi:#f08b82;--hibg:#3a2120;--md:#e6b866;--mdbg:#352a17;--ok:#8fcf9b;--okbg:#1d3022;--code:#2a2a27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
header h1{font-size:15px;margin:0 8px 0 0}
.bar{height:6px;flex:1;min-width:120px;background:var(--line);border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:var(--ok);width:0}
button,select{font:inherit;font-size:13px;padding:4px 10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;cursor:pointer}
button.primary{background:var(--acc);color:var(--panel);border-color:var(--acc)}
.wrap{display:grid;grid-template-columns:220px 1fr;max-width:1200px;margin:0 auto}
nav{position:sticky;top:46px;align-self:start;height:calc(100vh - 46px);overflow:auto;padding:12px 8px;border-right:1px solid var(--line);font-size:12.5px}
nav h3{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);margin:12px 6px 4px}
nav a{display:flex;gap:6px;padding:2px 6px;border-radius:4px;color:var(--ink);text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav a.cur{background:var(--accbg)}nav a .d{width:8px;height:8px;border-radius:50%;margin-top:5px;flex:none;background:var(--line)}nav a.done .d{background:var(--ok)}nav a.pend .d{background:var(--md)}
main{padding:12px 16px 80px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:0 0 10px;scroll-margin-top:56px}
.card.cur{outline:2px solid var(--acc)}
.h{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.h b.id{color:var(--acc);font-variant-numeric:tabular-nums}.h .nm{font-weight:600}
.tag{font-size:11px;padding:0 6px;border-radius:9px;background:var(--code);color:var(--mute)}.tag.hi{background:var(--hibg);color:var(--hi)}.tag.fz{background:var(--mdbg);color:var(--md)}.tag.add{background:var(--accbg);color:var(--acc)}
.issue{margin:6px 0 4px;color:var(--ink)}.issue .s{font-weight:600;color:var(--hi)}
.tg{font-size:12px;color:var(--acc);cursor:pointer;margin-right:12px;user-select:none}
.more{display:none;margin:6px 0;padding:8px 10px;background:var(--bg);border-radius:6px;font-size:13px}.more.on{display:block}
.more li{margin:3px 0}.more .src{color:var(--mute);font-size:12px}
.opts{margin-top:6px;display:grid;gap:4px}
.opt{display:grid;grid-template-columns:22px 1fr;gap:4px;padding:5px 8px;border:1px solid var(--line);border-radius:6px;cursor:pointer}
.opt:hover{border-color:var(--acc)}.opt.sel{border-color:var(--acc);background:var(--accbg)}
.opt .k{font-size:11px;color:var(--mute);font-variant-numeric:tabular-nums;padding-top:1px}
.opt .l{font-weight:600}.opt .c{color:var(--mute);font-size:12.5px}
.opt .dt{display:none;font-size:12.5px;margin-top:4px}.opt.x .dt{display:block}.opt .dt p{margin:2px 0}
.row2{display:flex;gap:8px;margin-top:6px;align-items:center}.row2 input{flex:1;font:inherit;font-size:13px;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink)}
.pb{font-size:12px;padding:2px 8px}.pb.on{background:var(--mdbg);color:var(--md);border-color:var(--md)}
code{background:var(--code);padding:0 3px;border-radius:3px;font-size:12.5px}
.help{font-size:12px;color:var(--mute)}
dialog{max-width:760px;width:92vw;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink)}dialog textarea{width:100%;height:50vh;font:12px ui-monospace,monospace;background:var(--bg);color:var(--ink);border:1px solid var(--line)}
@media (max-width:760px){.wrap{grid-template-columns:1fr}nav{display:none}main{padding:10px 16px 80px}}
</style></head><body>
<header><h1>__TITLE__</h1><span id="cnt" class="help"></span><div class="bar"><i id="barfill"></i></div>
<select id="flt"><option value="all">All items</option><option value="open">Unanswered</option><option value="hi">Has high finding</option><option value="frozen">Frozen CX</option><option value="add">Additions</option></select>
<button id="exp" class="primary">Copy reply</button></header>
<div class="wrap"><nav id="nav"></nav><main>
<div class="card"><div class="help">__INTRO__<b>How to use.</b> <kbd>j</kbd>/<kbd>k</kbd> next/previous item · <kbd>1</kbd>–<kbd>9</kbd> pick option · <kbd>p</kbd> leave pending · <kbd>n</kbd> write a note or your own wording · <kbd>f</kbd> findings · <kbd>c</kbd> current text · <kbd>d</kbd> option details. On existing items, option 1 is <b>keep</b> (the current wording, quoted under "current text"). On additions, the options include adding the item or leaving it out. Every other option is agent-drafted, and none is recommended. Answers save in this browser. When you're done, use <b>Copy reply</b> and paste it in chat. Frozen CX items need re-signature to change (R-025), and any enum change costs two version steps (C-007). Drafted by three fresh-context subagents (Claude Code, claude-opus-5-5), session 20261029-claude-v2-c47ab81795f0f95a. Data hash <code id="sha"></code>.</div></div>
<div id="list"></div></main></div>
<dialog id="dlg"><p class="help">Paste this into chat.</p><textarea id="out" readonly></textarea><p><button id="cp" class="primary">Copy</button> <button id="cl">Close</button></p></dialog>
<script type="application/json" id="data">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);const KEY='cbr:'+D.id+':'+D.sha;
let S={};try{S=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){S={}}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}};
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const md=s=>esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>').replace(/\n\n+/g,'<br><br>').replace(/\n- /g,'<br>• ');
const short=(s,n)=>{s=String(s||'');return s.length>n?s.slice(0,n).replace(/\s+\S*$/,'')+' …':s};
document.getElementById('sha').textContent=D.sha;
let cur=0,vis=[];
function state(it){const a=S[it.id];if(!a)return '';if(a.c==='pending')return 'pend';return a.c||a.note?'done':''}
function render(){
 const f=document.getElementById('flt').value;
 vis=D.items.filter(it=>f==='all'||(f==='open'&&!state(it))||(f==='hi'&&it.findings.some(x=>x.sev==='high'))||(f==='frozen'&&it.frozen)||(f==='add'&&it.addition));
 const L=document.getElementById('list');L.innerHTML='';
 vis.forEach((it,i)=>{
  const a=S[it.id]||{};const nh=it.findings.filter(x=>x.sev==='high').length;const top=it.findings[0];
  const el=document.createElement('div');el.className='card';el.id='i-'+it.id;
  el.innerHTML=`<div class="h"><b class="id">${it.id}</b><span class="nm">${md(it.name)}</span>
   ${it.linkage?`<span class="tag">${esc(short(it.linkage,40))}</span>`:''}${it.frozen?'<span class="tag fz">frozen</span>':''}${it.addition?'<span class="tag add">addition'+(it.pipeline?' · '+esc(it.pipeline):'')+'</span>':''}${nh?`<span class="tag hi">${nh} high</span>`:''}</div>
   ${top?`<div class="issue"><span class="s">${esc(top.sev)}:</span> ${md(short(top.text,280))}</div>`:(it.notes?`<div class="issue">${md(short(it.notes,320))}</div>`:'')}
   <div>${it.findings.length?`<span class="tg" data-t="f">findings (${it.findings.length})</span>`:''}${it.current?'<span class="tg" data-t="c">current text</span>':''}${(it.notes&&top)||it.deps.length?'<span class="tg" data-t="n">notes</span>':''}</div>
   <div class="more" data-m="f"><ul>${it.findings.map(x=>`<li><b>${esc(x.sev)}</b> · ${esc(x.type)}: ${md(x.text)} <span class="src">${esc(x.ev)}</span></li>`).join('')}</ul></div>
   <div class="more" data-m="c">${md(it.current)}<div class="src">${esc(it.source)}</div></div>
   <div class="more" data-m="n">${md(it.notes)}${it.deps.length?'<br><span class="src">Depends on: '+esc(it.deps.join(', '))+'</span>':''}</div>
   <div class="opts">${it.options.map((o,k)=>`<div class="opt${a.c===o.id?' sel':''}" data-o="${esc(o.id)}"><span class="k">${k+1}</span><div><div class="l">${md(o.label)}</div><div class="c">${md(short(o.commits,200))}</div>
    <div class="dt"><p><b>How:</b> ${md(o.mech)}</p><p><b>Gains:</b> ${md(o.ben)}</p><p><b>Risks:</b> ${md(o.risk)}</p><p><b>Commits to:</b> ${md(o.commits)}</p></div></div></div>`).join('')}</div>
   <div class="row2"><button class="pb${a.c==='pending'?' on':''}" data-p>pending</button><span class="tg" data-t="d">option details</span><input placeholder="note or your own wording…" value="${esc(a.note||'')}"></div>`;
  el.addEventListener('click',e=>{
   const t=e.target.closest('[data-t]'),o=e.target.closest('[data-o]'),p=e.target.closest('[data-p]');cur=i;mark();
   if(t){const k=t.dataset.t;if(k==='d')el.querySelectorAll('.opt').forEach(x=>x.classList.toggle('x'));else el.querySelector(`[data-m="${k}"]`).classList.toggle('on');return}
   if(o){pick(it,o.dataset.o);return}if(p){pick(it,'pending')}
  });
  el.querySelector('input').addEventListener('input',e=>{S[it.id]=Object.assign(S[it.id]||{},{note:e.target.value});save();nav()});
  L.appendChild(el)});
 nav();mark(false)}
function pick(it,c){const a=S[it.id]||{};a.c=a.c===c?undefined:c;S[it.id]=a;save();
 const el=document.getElementById('i-'+it.id);el.querySelectorAll('.opt').forEach(x=>x.classList.toggle('sel',x.dataset.o===a.c));el.querySelector('[data-p]').classList.toggle('on',a.c==='pending');nav()}
function nav(){const N=document.getElementById('nav');let h='';
 D.sections.forEach(([k,t])=>{const its=D.items.filter(x=>x.sec===k);const dn=its.filter(x=>state(x)).length;h+=`<h3>${esc(t)} · ${dn}/${its.length}</h3>`;
  its.forEach(x=>h+=`<a href="#i-${x.id}" class="${state(x)}${vis[cur]&&vis[cur].id===x.id?' cur':''}"><span class="d"></span>${x.id} ${esc(short(x.name.replace(/`/g,''),26))}</a>`)});
 N.innerHTML=h;const dn=D.items.filter(x=>state(x)).length;document.getElementById('cnt').textContent=dn+' / '+D.items.length;document.getElementById('barfill').style.width=(100*dn/D.items.length)+'%'}
function mark(scroll=true){document.querySelectorAll('.card.cur').forEach(x=>x.classList.remove('cur'));const it=vis[cur];if(!it)return;const el=document.getElementById('i-'+it.id);el.classList.add('cur');if(scroll)el.scrollIntoView({block:'start',behavior:'smooth'});nav()}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'){if(e.key==='Escape')e.target.blur();return}if(e.ctrlKey||e.metaKey||e.altKey)return;
 const it=vis[cur];const el=it&&document.getElementById('i-'+it.id);
 if(e.key==='j'){cur=Math.min(cur+1,vis.length-1);mark()}else if(e.key==='k'){cur=Math.max(cur-1,0);mark()}
 else if(/^[1-9]$/.test(e.key)&&it){const o=it.options[+e.key-1];if(o)pick(it,o.id)}
 else if(e.key==='p'&&it)pick(it,'pending');else if(e.key==='n'&&el){e.preventDefault();el.querySelector('input').focus()}
 else if(e.key==='f'&&el){const m=el.querySelector('[data-m=f]');m&&m.classList.toggle('on')}else if(e.key==='c'&&el){el.querySelector('[data-m=c]').classList.toggle('on')}
 else if(e.key==='d'&&el)el.querySelectorAll('.opt').forEach(x=>x.classList.toggle('x'))});
document.getElementById('flt').onchange=()=>{cur=0;render()};
document.getElementById('exp').onclick=()=>{const lines=[];const js={format:'codebook-review-reply-v1',page_id:D.id,data_sha:D.sha,answers:{}};
 D.items.forEach(it=>{const a=S[it.id];if(!a||(!a.c&&!a.note))return;const o=it.options.find(x=>x.id===a.c);
  lines.push(`${it.id}: ${a.c==='pending'?'pending':o?o.id+' ('+short(o.label,60)+')':'—'}${a.note?' — '+a.note:''}`);js.answers[it.id]={choice:a.c||null,note:a.note||''}});
 const un=D.items.filter(x=>!state(x)).map(x=>x.id);
 document.getElementById('out').value=`Codebook review reply (${lines.length}/${D.items.length} answered)\n`+lines.join('\n')+(un.length?`\nUnanswered: ${un.join(', ')}`:'')+'\n\n```json\n'+JSON.stringify(js)+'\n```';
 document.getElementById('dlg').showModal()};
document.getElementById('cp').onclick=()=>{const t=document.getElementById('out');t.select();try{navigator.clipboard.writeText(t.value)}catch(e){document.execCommand('copy')}};
document.getElementById('cl').onclick=()=>document.getElementById('dlg').close();
render();
</script></body></html>"""

out = HERE / OUT_NAME
INTRO = "" if "--round2" not in sys.argv else "<b>Round 2.</b> Two fresh reviewers checked your 91 round-1 choices (<code>codebook-rulings-round1.json</code>) for conflicts with each other, gaps they leave and further additions, and for conflicts with fixed constraints, SPEC, procurement, the AI-text pipeline and downstream consumers. The options are ways to reconcile or fill each one; none is keep-by-default. SPEC and plan consequences (53 listed) are handled in chat, not here.<br><br>"
out.write_text(HTML.replace("__INTRO__", INTRO).replace("__TITLE__", TITLE).replace("__DATA__", payload), encoding="utf-8")
print(f"{len(items)} items -> {out.as_uri()}")
