"""Compare the r9 rerun with T-016 (v2.7 as signed) on the same page parts and entailment units (offline)."""
import json
from collections import Counter, defaultdict
from pathlib import Path

R = Path("H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan")
NC = "not covered by this part"


def load(path):
    chunks, ent, meta = defaultdict(dict), {}, {}
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        ans = {q: a for p in r.get("parts", []) for q, a in p["answers"].items()}
        if r["key"].startswith("entail|"):
            ent[r["key"]] = ans.get("core.support_entailment")
        elif r["info"].get("page"):
            k = (r["info"]["page"], r["info"]["chunk"])
            chunks[k].update(ans)
            meta[k] = r["info"]
    return chunks, ent, meta


old, old_ent, _ = load(R / "repilot-v27/answers-t016.jsonl")
new, new_ent, meta = load(R / "repilot-r9/answers-t016.jsonl")
conf = {k for k, a in old.items() if a.get("core.page_verdict", {}).get("choice") == "confirms_activity"}


def stats(store, keys, q):
    xs = [store[k][q] for k in keys if q in store.get(k, {})]
    ps = [x["confidence"] for x in xs if x["confidence"] is not None]
    mc = [store[k][q]["choice"] for k in keys if q in store.get(k, {}) and meta[k]["n_chunks"] > 1]
    return {"n": len(xs), "mean_p": round(sum(ps) / len(ps), 3) if ps else None,
            "p_lt_0.6": round(sum(p < 0.6 for p in ps) / len(ps), 3) if ps else None,
            "nc_multichunk": round(mc.count(NC) / len(mc), 3) if mc else None,
            "dist": dict(Counter(x["choice"] for x in xs).most_common())}


qs = sorted({q for a in new.values() for q in a})
keys = sorted(new)
out = {"parts": len(keys), "confirms_activity_parts": len(conf & set(keys)), "questions": {}}
for q in qs:
    out["questions"][q] = {"all_parts": {"t016": stats(old, keys, q), "r9": stats(new, keys, q)},
                           "confirms_activity": {"t016": stats(old, sorted(conf), q), "r9": stats(new, sorted(conf), q)}}
info = {}
for line in (R / "repilot-r9/answers-t016.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    if r["key"].startswith("entail|"):
        info[r["key"]] = r["info"]["field"]
ef = defaultdict(lambda: {"t016": Counter(), "r9": Counter()})
for k, f in info.items():
    ef[f]["t016"][(old_ent.get(k) or {}).get("choice")] += 1
    ef[f]["r9"][(new_ent.get(k) or {}).get("choice")] += 1
out["entailment"] = {f: {s: dict(c) for s, c in v.items()} for f, v in sorted(ef.items())}
(R / "repilot-r9/compare-r9.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

print(f"{'question':48} {'p t016':>6} {'p r9':>6} {'<.6 t':>6} {'<.6 r9':>6} {'NC t':>5} {'NC r9':>5} | CA p t016 -> r9")
for q, s in out["questions"].items():
    a, c = s["all_parts"], s["confirms_activity"]
    print(f"{q:48} {a['t016']['mean_p']!s:>6} {a['r9']['mean_p']!s:>6} {a['t016']['p_lt_0.6']!s:>6} "
          f"{a['r9']['p_lt_0.6']!s:>6} {a['t016']['nc_multichunk']!s:>5} {a['r9']['nc_multichunk']!s:>5} | "
          f"{c['t016']['mean_p']} -> {c['r9']['mean_p']}")
tt = Counter()
for f, v in out["entailment"].items():
    print("entail", f, v)
    for s in ("t016", "r9"):
        tt[(s, "true")] += v[s].get("true", 0)
        tt[(s, "n")] += sum(v[s].values())
print("entail true:", tt[("t016", "true")], "/", tt[("t016", "n")], "->", tt[("r9", "true")], "/", tt[("r9", "n")])
