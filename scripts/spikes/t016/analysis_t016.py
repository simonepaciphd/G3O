"""T-016 per-question diagnostics (offline; reads answers-t016.jsonl only)."""
import json, math, sys
from collections import Counter, defaultdict
from pathlib import Path

D = Path("H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/repilot-v27")
NC = "not covered by this part"
rows = [json.loads(x) for x in (D / "answers-t016.jsonl").read_text(encoding="utf-8").splitlines()]

chunks = defaultdict(dict)   # (page, chunk) -> {q: answer}
meta = {}
ent, pair = [], []
for r in rows:
    u = r["info"].get("unit")
    ans = {q: a for p in r["parts"] for q, a in p["answers"].items()}
    if u == "entailment":
        ent.append((r["info"], ans["core.support_entailment"]))
    elif u:
        pair.append(ans)
    else:
        k = (r["info"]["page"], r["info"]["chunk"])
        chunks[k].update(ans)
        meta[k] = r["info"]

def norm_entropy(c, k):
    t = sum(c.values())
    if t == 0 or k < 2:
        return None
    h = -sum(v / t * math.log(v / t) for v in c.values() if v)
    return h / math.log(k)

opts = defaultdict(set)
for a in chunks.values():
    for q, x in a.items():
        opts[q] |= set(x["probabilities"]) - {NC}

out = {}
for q in sorted(opts):
    allc, multi, conf, nog, probs = Counter(), Counter(), Counter(), Counter(), []
    for k, a in chunks.items():
        if q not in a:
            continue
        ch = a[q]["choice"]
        allc[ch] += 1
        if meta[k]["n_chunks"] > 1:
            multi[ch] += 1
        v = a.get("core.page_verdict", {}).get("choice")
        if ch != NC:
            (conf if v == "confirms_activity" else nog if v == "no_genai" else Counter())[ch] += 1
        if a[q]["confidence"] is not None:
            probs.append(a[q]["confidence"])
    sub = Counter({c: n for c, n in allc.items() if c != NC})
    n = sum(allc.values())
    nm = sum(multi.values())
    top, topn = (sub.most_common(1) or [(None, 0)])[0]
    out[q] = {
        "n": n, "k": len(opts[q]),
        "nc_share_multichunk": round(multi[NC] / nm, 3) if nm else None,
        "top": top, "top_share": round(topn / sum(sub.values()), 3) if sub else None,
        "H_norm": round(norm_entropy(sub, len(opts[q])) or 0, 3),
        "mean_p": round(sum(probs) / len(probs), 3) if probs else None,
        "share_p_lt_0.6": round(sum(p < 0.6 for p in probs) / len(probs), 3) if probs else None,
        "dist": dict(sub.most_common()),
        "dist_confirms_activity": dict(conf.most_common()),
        "dist_no_genai": dict(nog.most_common()),
    }

verd = Counter(a.get("core.page_verdict", {}).get("choice") for a in chunks.values())
ef = defaultdict(Counter)
for info, a in ent:
    ef[info["field"]][a["choice"]] += 1
res = {"chunks": len(chunks), "verdicts": dict(verd), "questions": out,
       "entailment": {"n": len(ent), "overall": dict(Counter(a["choice"] for _, a in ent)),
                      "by_field": {f: dict(c) for f, c in ef.items()}},
       "pairs": {q: dict(Counter(a[q]["choice"] for a in pair if q in a)) for q in sorted({q for a in pair for q in a})}}
(Path(sys.argv[1]) if len(sys.argv) > 1 else D / "analysis-t016.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")

print("chunks", len(chunks), "verdicts", dict(verd))
print(f"{'question':45} {'n':>5} {'k':>2} {'NC|mc':>6} {'top':>6} {'Hn':>5} {'p':>5} {'p<.6':>5}  top")
for q, s in out.items():
    print(f"{q:45} {s['n']:5} {s['k']:2} {str(s['nc_share_multichunk']):>6} {str(s['top_share']):>6} {s['H_norm']:5} {str(s['mean_p']):>5} {str(s['share_p_lt_0.6']):>5}  {s['top']}")
print("entailment", res["entailment"])
print("pairs", res["pairs"])
