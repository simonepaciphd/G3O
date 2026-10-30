"""Build the plain-language round-2 codebook review page.

Usage: python -I build_plain.py <plain.json>   (paths relative to this file unless absolute)
Reads the plain-language rewrite (one entry per round-2 item, same item and option IDs as the
reviewer JSONs) and writes codebook-review-r2-plain.html beside this script. Item IDs stay out of
the display; they are kept in the reply so answers map back to the reviewer records.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(p):
    p = Path(p)
    return json.loads((p if p.is_absolute() else HERE / p).read_text(encoding="utf-8"))


plain = {it["id"]: it for it in load(sys.argv[1])["items"]}
TYPES = [("constraint-conflict", "Clashes with fixed commitments"), ("inconsistency", "Your choices that clash"),
         ("gap", "Gaps left open"), ("addition", "Possible additions")]
SEVO = {"high": 0, "medium": 1, "low": 2}
src = []
for fname in ("review-r2-consistency.json", "review-r2-impact.json"):
    src += load(fname)["items"]
missing = [it["id"] for it in src if it["id"] not in plain]
if missing:
    sys.exit("no plain text for: " + ", ".join(missing))

items = []
for it in src:
    p = plain[it["id"]]
    sec = it.get("type") if it.get("type") in dict(TYPES) else "gap"
    want = [o["id"] for o in it["options"]]
    got = [o["id"] for o in p["options"]]
    if want != got:
        sys.exit(f"{it['id']}: option ids {got} != source {want}")
    items.append({"id": it["id"], "sec": sec, "hi": it.get("severity") == "high", "sev": SEVO.get(it.get("severity"), 3),
                  "title": p["title"], "decision": p["decision"], "why": p["why"],
                  "options": [{k: o[k] for k in ("id", "label", "means", "upside", "downside")} for o in p["options"]]})
items.sort(key=lambda x: ([k for k, _ in TYPES].index(x["sec"]), x["sev"]))
for n, it in enumerate(items, 1):
    it["n"] = n
num = {it["id"]: it["n"] for it in items}
# Pairs the two round-2 reviewers raised independently: decide them together.
SEE = [("R2C01", "R2P01"), ("R2C18", "R2P07"), ("R2C23", "R2P21", "R2P22"), ("R2C08", "R2P02"),
       ("R2C10", "R2P24"), ("R2C16", "R2P05"), ("R2C35", "R2P27"), ("R2C12", "R2P08")]
for it in items:
    it["with"] = sorted(num[x] for g in SEE if it["id"] in g for x in g if x != it["id"])

data = {"id": "codebook-review-r2-plain-2026-10-29", "sections": TYPES, "items": items}
data["sha"] = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codebook review, round 2</title>
<style>
:root{--bg:#fafaf8;--panel:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e3e2dc;--acc:#2f5d8a;--accbg:#e8eff7;--hi:#b3261e;--hibg:#fbeae8;--md:#8a5a00;--mdbg:#fbf1df;--ok:#2e6b3a;--okbg:#e6f2e8;--code:#f1f0eb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;--mute:#9d9c95;--line:#33332f;--acc:#8db8e6;--accbg:#22303f;--hi:#f08b82;--hibg:#3a2120;--md:#e6b866;--mdbg:#352a17;--ok:#8fcf9b;--okbg:#1d3022;--code:#2a2a27}}
:root[data-theme=dark]{--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;--mute:#9d9c95;--line:#33332f;--acc:#8db8e6;--accbg:#22303f;--hi:#f08b82;--hibg:#3a2120;--md:#e6b866;--mdbg:#352a17;--ok:#8fcf9b;--okbg:#1d3022;--code:#2a2a27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line);padding:8px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
header h1{font-size:15px;margin:0 8px 0 0}
.bar{height:6px;flex:1;min-width:120px;background:var(--line);border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:var(--ok);width:0}
button,select{font:inherit;font-size:13px;padding:4px 10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;cursor:pointer}
button.primary{background:var(--acc);color:var(--panel);border-color:var(--acc)}
.wrap{display:grid;grid-template-columns:240px 1fr;max-width:1200px;margin:0 auto}
nav{position:sticky;top:46px;align-self:start;height:calc(100vh - 46px);overflow:auto;padding:12px 8px;border-right:1px solid var(--line);font-size:12.5px}
nav h3{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);margin:12px 6px 4px}
nav a{display:flex;gap:6px;padding:2px 6px;border-radius:4px;color:var(--ink);text-decoration:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav a.cur{background:var(--accbg)}nav a .d{width:8px;height:8px;border-radius:50%;margin-top:6px;flex:none;background:var(--line)}nav a.done .d{background:var(--ok)}nav a.pend .d{background:var(--md)}
main{padding:12px 16px 80px;min-width:0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:0 0 12px;scroll-margin-top:56px}
.card.cur{outline:2px solid var(--acc)}
.h{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.h .n{color:var(--mute);font-variant-numeric:tabular-nums;font-size:13px}.h .t{font-weight:600;font-size:15px}
.tag{font-size:11px;padding:0 7px;border-radius:9px;background:var(--hibg);color:var(--hi)}
.q{font-weight:600;margin:6px 0 2px}.why{color:var(--mute);margin:0 0 6px}
.with{font-size:12.5px;color:var(--md);margin:0 0 6px}.with a{color:inherit}
.opts{display:grid;gap:5px}
.opt{display:grid;grid-template-columns:22px 1fr;gap:4px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;cursor:pointer}
.opt:hover{border-color:var(--acc)}.opt.sel{border-color:var(--acc);background:var(--accbg)}
.opt .k{font-size:12px;color:var(--mute);font-variant-numeric:tabular-nums;padding-top:2px}
.opt .l{font-weight:600}.opt .m{font-size:13.5px;margin:1px 0}.opt .pm{font-size:13px;color:var(--mute)}.opt .pm b{color:var(--ink);font-weight:600}
.row2{display:flex;gap:8px;margin-top:8px;align-items:center}.row2 input{flex:1;min-width:0;font:inherit;font-size:13px;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--ink)}
.pb{font-size:12px;padding:2px 8px}.pb.on{background:var(--mdbg);color:var(--md);border-color:var(--md)}
.help{font-size:13px;color:var(--mute)}kbd{font:12px ui-monospace,monospace;background:var(--code);padding:0 4px;border-radius:3px}
dialog{max-width:760px;width:92vw;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink)}dialog textarea{width:100%;height:50vh;font:12px ui-monospace,monospace;background:var(--bg);color:var(--ink);border:1px solid var(--line)}
@media (max-width:760px){.wrap{grid-template-columns:1fr}nav{display:none}}
</style></head><body>
<header><h1>Codebook review, round 2</h1><span id="cnt" class="help"></span><div class="bar"><i id="barfill"></i></div>
<select id="flt"><option value="all">All</option><option value="open">Unanswered</option><option value="hi">Important only</option></select>
<button id="exp" class="primary">Copy reply</button></header>
<div class="wrap"><nav id="nav"></nav><main>
<div class="card"><div class="help">A second review of your round-1 choices found places where they clash with each other or with commitments already made, gaps they leave open, and a few possible additions. Each card asks one question. The options were drafted by reviewers, and none is recommended. Items marked <span class="tag">important</span> are the ones to settle first. Where both reviewers raised the same issue, the card says so: decide those together.<br>
<kbd>j</kbd>/<kbd>k</kbd> next/previous · <kbd>1</kbd>–<kbd>9</kbd> pick an option · <kbd>p</kbd> leave pending · <kbd>n</kbd> write a note or your own answer. Answers are saved in this browser. When you're done, press <b>Copy reply</b> and paste it in chat. <span id="sha" style="opacity:.6"></span></div></div>
<div id="list"></div></main></div>
<dialog id="dlg"><p class="help">Paste this into chat.</p><textarea id="out" readonly></textarea><p><button id="cp" class="primary">Copy</button> <button id="cl">Close</button></p></dialog>
<script type="application/json" id="data">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);const KEY='cbr:'+D.id+':'+D.sha;
let S={};try{S=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){S={}}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}};
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const md=s=>esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<b>$1</b>');
const short=(s,n)=>{s=String(s||'');return s.length>n?s.slice(0,n).replace(/\s+\S*$/,'')+' …':s};
const byN={};D.items.forEach(x=>byN[x.n]=x);
document.getElementById('sha').textContent='Data '+D.sha+'.';
let cur=0,vis=[];
function state(it){const a=S[it.id];if(!a)return '';if(a.c==='pending')return 'pend';return a.c||a.note?'done':''}
function render(){
 const f=document.getElementById('flt').value;
 vis=D.items.filter(it=>f==='all'||(f==='open'&&!state(it))||(f==='hi'&&it.hi));
 const L=document.getElementById('list');L.innerHTML='';
 vis.forEach((it,i)=>{
  const a=S[it.id]||{};
  const el=document.createElement('div');el.className='card';el.id='i-'+it.n;
  el.innerHTML=`<div class="h"><span class="n">${it.n}.</span><span class="t">${md(it.title)}</span>${it.hi?'<span class="tag">important</span>':''}</div>
   <div class="q">${md(it.decision)}</div><div class="why">${md(it.why)}</div>
   ${it.with.length?`<div class="with">Both reviewers raised this; decide together with ${it.with.map(n=>`<a href="#i-${n}">${n}. ${esc(byN[n].title)}</a>`).join(' and ')}.</div>`:''}
   <div class="opts">${it.options.map((o,k)=>`<div class="opt${a.c===o.id?' sel':''}" data-o="${esc(o.id)}"><span class="k">${k+1}</span><div><div class="l">${md(o.label)}</div><div class="m">${md(o.means)}</div><div class="pm"><b>+</b> ${md(o.upside)}<br><b>−</b> ${md(o.downside)}</div></div></div>`).join('')}</div>
   <div class="row2"><button class="pb${a.c==='pending'?' on':''}" data-p>pending</button><input placeholder="note or your own answer…" value="${esc(a.note||'')}"></div>`;
  el.addEventListener('click',e=>{const o=e.target.closest('[data-o]'),p=e.target.closest('[data-p]');cur=i;mark(false);
   if(o){pick(it,o.dataset.o);return}if(p){pick(it,'pending')}});
  el.querySelector('input').addEventListener('input',e=>{S[it.id]=Object.assign(S[it.id]||{},{note:e.target.value});save();nav()});
  L.appendChild(el)});
 nav();mark(false)}
function pick(it,c){const a=S[it.id]||{};a.c=a.c===c?undefined:c;S[it.id]=a;save();
 const el=document.getElementById('i-'+it.n);el.querySelectorAll('.opt').forEach(x=>x.classList.toggle('sel',x.dataset.o===a.c));el.querySelector('[data-p]').classList.toggle('on',a.c==='pending');nav()}
function nav(){const N=document.getElementById('nav');let h='';
 D.sections.forEach(([k,t])=>{const its=D.items.filter(x=>x.sec===k);const dn=its.filter(x=>state(x)).length;h+=`<h3>${esc(t)} · ${dn}/${its.length}</h3>`;
  its.forEach(x=>h+=`<a href="#i-${x.n}" class="${state(x)}${vis[cur]&&vis[cur].id===x.id?' cur':''}"><span class="d"></span>${x.n}. ${esc(short(x.title,30))}</a>`)});
 N.innerHTML=h;const dn=D.items.filter(x=>state(x)).length;document.getElementById('cnt').textContent=dn+' / '+D.items.length;document.getElementById('barfill').style.width=(100*dn/D.items.length)+'%'}
function mark(scroll=true){document.querySelectorAll('.card.cur').forEach(x=>x.classList.remove('cur'));const it=vis[cur];if(!it)return;const el=document.getElementById('i-'+it.n);el.classList.add('cur');if(scroll)el.scrollIntoView({block:'start',behavior:'smooth'});nav()}
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'){if(e.key==='Escape')e.target.blur();return}if(e.ctrlKey||e.metaKey||e.altKey)return;
 const it=vis[cur];const el=it&&document.getElementById('i-'+it.n);
 if(e.key==='j'){cur=Math.min(cur+1,vis.length-1);mark()}else if(e.key==='k'){cur=Math.max(cur-1,0);mark()}
 else if(/^[1-9]$/.test(e.key)&&it){const o=it.options[+e.key-1];if(o)pick(it,o.id)}
 else if(e.key==='p'&&it)pick(it,'pending');else if(e.key==='n'&&el){e.preventDefault();el.querySelector('input').focus()}});
document.getElementById('flt').onchange=()=>{cur=0;render()};
document.getElementById('exp').onclick=()=>{const lines=[];const js={format:'codebook-review-reply-v1',page_id:D.id,data_sha:D.sha,answers:{}};
 D.items.forEach(it=>{const a=S[it.id];if(!a||(!a.c&&!a.note))return;const o=it.options.find(x=>x.id===a.c);
  lines.push(`${it.n}. ${it.title}: ${a.c==='pending'?'pending':o?short(o.label,60):'—'}${a.note?' — '+a.note:''}`);js.answers[it.id]={choice:a.c||null,note:a.note||''}});
 const un=D.items.filter(x=>!state(x)).map(x=>x.n);
 document.getElementById('out').value=`Codebook review round 2 reply (${lines.length}/${D.items.length} answered)\n`+lines.join('\n')+(un.length?`\nUnanswered: ${un.join(', ')}`:'')+'\n\n```json\n'+JSON.stringify(js)+'\n```';
 document.getElementById('dlg').showModal()};
document.getElementById('cp').onclick=()=>{const t=document.getElementById('out');t.select();try{navigator.clipboard.writeText(t.value)}catch(e){document.execCommand('copy')}};
document.getElementById('cl').onclick=()=>document.getElementById('dlg').close();
render();
</script></body></html>"""

out = HERE / "codebook-review-r2-plain.html"
out.write_text(HTML.replace("__DATA__", payload), encoding="utf-8")
print(f"{len(items)} items -> {out.as_uri()}  (data {data['sha']})")
