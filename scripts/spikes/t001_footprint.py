"""T-001: disk footprint (allocated bytes, inode count) of the back-fill institutions' existing institution dirs. Read-only."""
import json, os, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
R = "/home/g3o/runs"
shards = {}
out = {}
for view in ("listed_snapshot", "derived_current"):
    tot = {"inst": 0, "found": 0, "bytes": 0, "files": 0, "scrape_bytes": 0}
    for uid, v in d["per_uid"].items():
        r = v["snapshot"] if view == "listed_snapshot" else (v["snapshot"] if v["current"] == "same" else v["current"])
        if view == "listed_snapshot" and not v["listed"]:
            continue
        if view == "derived_current" and (r is None or r["verdict"] not in ("yes", "unclear")):
            continue
        tot["inst"] += 1
        run, iid = r["run"], r["institution_id"]
        if run not in shards:
            shards[run] = [e.path for e in os.scandir(f"{R}/{run}/institutions") if e.is_dir()]
        for sp in shards[run]:
            p = os.path.join(sp, iid)
            if os.path.isdir(p):
                tot["found"] += 1
                for root, dirs, files in os.walk(p):
                    for f in files:
                        st = os.lstat(os.path.join(root, f))
                        tot["bytes"] += st.st_blocks * 512
                        tot["files"] += 1
                        if root.endswith("/scrape"):
                            tot["scrape_bytes"] += st.st_blocks * 512
                break
    out[view] = tot
    print(view, tot, flush=True)
json.dump(out, open(sys.argv[2], "w"), indent=1)
