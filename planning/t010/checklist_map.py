"""T-010 self-check: map SPEC rows R-010..R-045 (those that exist) and R-087 to codebook items
and shared rules, mechanically, from the signed codebook. Read-only; prints JSON to stdout.

Usage: python -I t010_checklist_map.py <worktree> [<old_checklist.md>]
Item maps to row X when any entry of its `refs` names X (regex \bR-0NN\b).
Shared rule maps to row X when any of its slots' `source` names X.
Vocabulary / combining-convention slots whose `source` names X are listed separately.
Template check: every item has all 27 fields of item-template.md section 2, none null/blank.
"""
import hashlib, json, re, sys, pathlib
import yaml

wt = pathlib.Path(sys.argv[1])
cb_path = wt / "codebook" / "codebook.yaml"
raw = cb_path.read_bytes()
cb = yaml.safe_load(raw.decode("utf-8"))
spec = (wt / "planning" / "SPEC.md").read_text(encoding="utf-8")
tmpl = (wt / "planning" / "t010" / "item-template.md").read_text(encoding="utf-8")

# SPEC rows in range, in SPEC order
rows = []
for m in re.finditer(r"^\| (R-0\d\d) \|", spec, re.M):
    rid = m.group(1)
    n = int(rid[2:])
    if (10 <= n <= 45 or n == 87) and rid not in rows:
        rows.append(rid)

# template fields, section 2 table: "| # | `field` |"
fields = re.findall(r"^\| (\d+) \| `([a-z_0-9]+)`[^|]*\|", tmpl, re.M)
fields = [f for _, f in sorted(fields, key=lambda x: int(x[0]))]
assert len(fields) == 27, fields

def names(rid, s):
    return re.search(r"\b" + re.escape(rid) + r"\b", s) is not None

def slot_sources(node, path=""):
    """yield (path, source) for every dict carrying a 'source' string"""
    if isinstance(node, dict):
        if isinstance(node.get("source"), str):
            yield path, node["source"]
        for k, v in node.items():
            yield from slot_sources(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from slot_sources(v, f"{path}/{i}")

items = cb["items"]
shared = cb["shared_rules"]
out = {"codebook_sha256": hashlib.sha256(raw).hexdigest(), "rows": {}, "template": {}}
for rid in rows:
    it = sorted(i for i, v in items.items() if any(names(rid, str(r)) for r in (v.get("refs") or [])))
    sr = sorted(s for s, v in shared.items() if any(names(rid, src) for _, src in slot_sources(v)))
    other = sorted({p.split("/")[0] + "." + p.split("/")[1]
                    for sec in ("vocabularies", "combining_conventions")
                    for p, src in ((sec + pth, s) for pth, s in slot_sources(cb.get(sec, {})))
                    if names(rid, src)})
    out["rows"][rid] = {"items": it, "shared_rules": sr, "other_slots": other}

missing, blank, open_counts = {}, {}, {}
for iid, v in items.items():
    mf = [f for f in fields if f not in v]
    bf = [f for f in fields if f in v and (v[f] is None or (isinstance(v[f], str) and not v[f].strip())
                                           or v[f] == [] or v[f] == {})]
    if mf: missing[iid] = mf
    if bf: blank[iid] = bf
    for f in fields:
        if v.get(f) == "open":
            open_counts[f] = open_counts.get(f, 0) + 1
    if v.get("id") != iid:
        missing.setdefault(iid, []).append(f"id mismatch: {v.get('id')!r}")
out["template"] = {"fields": fields, "n_items": len(items), "missing": missing, "blank": blank,
                   "open": open_counts,
                   "release_open": [k for k, v in cb["release"].items() if v == "open"]}

if len(sys.argv) > 2:
    old = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
    ids = sorted(set(re.findall(r"`((?:core|proc|text|vocabularies)\.[a-z_0-9.]+)`", old)))
    def exists(i):
        if i in items or i in shared: return True
        if i.startswith("vocabularies."): return i.split(".", 1)[1] in cb["vocabularies"]
        return False
    out["old_ids_missing"] = [i for i in ids if not exists(i)]
    out["old_ids_checked"] = len(ids)

print(json.dumps(out, indent=1))
