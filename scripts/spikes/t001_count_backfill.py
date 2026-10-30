"""Reclass plan v2.7, card T-001 (spike): stored-text availability for the documented and unclear back-fill groups.

READ-ONLY over /home/g3o/runs. No fetch, no pipeline run, no DB access, no paid call. Writes only the --out JSON
(droplet scratch ~/reclass-spike-*/). Extends RS-004 enumerate.py / count_pages.py (same run-selection rule,
same md5(source_url) -> scrape-file lookup, same >=200-char stripped-text test, same raw-%PDF test).

Usage: python3 t001_count_backfill.py --uids uid-lists.json --out count-backfill.json [--workers 3]

Groups = RS-025 documented list (9,705) and RS-036 unclear list (27,648), both public-API harvests at
coverage as_of 2026-10-24T14:04:52Z. Two latest-run views per uid:
  snapshot: latest run (by run id) holding the uid among runs whose final summary CSV was written on or before
            the API as_of (reproduces the published state the lists were drawn from);
  current:  latest run among all runs with final CSVs (includes wave 5 `r20261023T134656Z-be8a`, R-070).
Droplet-derived groups (latest verdict yes / unclear) are also computed for both views so the list totals can
be reconciled rather than assumed.

Per (run, institution) counts. "src" = distinct source_url values in final/g3o_activity_sources_v1.csv for that
institution (the page-level answers the run published); "scrape" = every stored file under
institutions/<shard>/<iid>/scrape/ (every page the run fetched and kept).
  pages        distinct pages
  usable200    stored text (stripped) >= 200 chars and not starting with %PDF
  raw_pdf      stored text starting with %PDF (raw bytes, not extracted text), any length
  short        stored file present, text < 200 chars, not %PDF
  no_file      (src only) no stored scrape file for the URL
  triage_keep  URLs kept at triage (3_triage.json decision == keep)
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

RUNS = Path("/home/g3o/runs")
AS_OF = datetime(2026, 10, 24, 14, 4, 52, tzinfo=timezone.utc)
SUMMARY = "g3o_institution_summary_v1.csv"
SOURCES = "g3o_activity_sources_v1.csv"
csv.field_size_limit(1 << 26)


def read_csv(p):
    with open(p, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def classify(p):
    """Return 'usable200' | 'raw_pdf' | 'short' for one stored scrape file."""
    try:
        raw = p.read_bytes()
        if p.name.endswith(".gz"):
            raw = gzip.decompress(raw)
        t = (json.loads(raw).get("text") or "").strip()
    except Exception:
        return "short"
    if t.startswith("%PDF"):
        return "raw_pdf"
    return "usable200" if len(t) >= 200 else "short"


def count_run(args):
    """Counts for the given institution ids of one run."""
    rid, iids = args
    run = RUNS / rid
    iids = set(iids)
    urls = defaultdict(set)
    for s in read_csv(run / "final" / SOURCES):
        if s["institution_id"] in iids and s["source_url"]:
            urls[s["institution_id"]].add(s["source_url"])
    dirs = {}
    root = run / "institutions"
    if root.is_dir():
        for shard in os.scandir(root):
            if shard.is_dir():
                for iid in iids.intersection(os.listdir(shard.path)):
                    dirs.setdefault(iid, Path(shard.path) / iid)
    out = {}
    for iid in iids:
        d = dirs.get(iid)
        files = {}
        if d is not None and (d / "scrape").is_dir():
            for p in (d / "scrape").iterdir():
                files[p.name.split(".")[0]] = p
        cls = {h: classify(p) for h, p in files.items()}
        src = {"pages": 0, "usable200": 0, "raw_pdf": 0, "short": 0, "no_file": 0}
        for u in urls.get(iid, ()):
            src["pages"] += 1
            c = cls.get(hashlib.md5(u.encode("utf-8")).hexdigest())
            src[c or "no_file"] += 1
        scr = {"pages": len(cls), "usable200": 0, "raw_pdf": 0, "short": 0}
        for c in cls.values():
            scr[c] += 1
        keep = None
        if d is not None and (d / "3_triage.json").exists():
            try:
                keep = sum(x.get("decision") == "keep"
                           for x in json.loads((d / "3_triage.json").read_text(encoding="utf-8")).get("decisions", []))
            except Exception:
                keep = None
        out[iid] = {"inst_dir": d is not None, "src": src, "scrape": scr, "triage_keep": keep}
    return rid, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uids", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    t0 = time.time()
    lists = json.loads(Path(a.uids).read_text(encoding="utf-8"))
    listed = {"documented": set(lists["documented"]), "unclear": set(lists["unclear"])}

    runs, snapshot_runs, multi = [], set(), defaultdict(int)
    rows = {}  # (rid, uid) -> (iid, verdict)
    for run in sorted(RUNS.iterdir()):
        summ = run / "final" / SUMMARY
        if not (summ.exists() and (run / "final" / SOURCES).exists()):
            continue
        runs.append(run.name)
        if datetime.fromtimestamp(summ.stat().st_mtime, timezone.utc) <= AS_OF:
            snapshot_runs.add(run.name)
        for r in read_csv(summ):
            uid = r.get("institution_uid")
            if not uid:
                continue
            if (run.name, uid) in rows:
                multi[run.name] += 1
            rows[(run.name, uid)] = (r["institution_id"], r["has_genai_activity"])
        print(f"{time.time()-t0:7.1f}s indexed {run.name}", file=sys.stderr, flush=True)

    latest = {"snapshot": {}, "current": {}}
    for (rid, uid) in rows:
        for view in ("snapshot", "current"):
            if view == "snapshot" and rid not in snapshot_runs:
                continue
            if uid not in latest[view] or rid > latest[view][uid]:
                latest[view][uid] = rid

    derived = {}
    for view in ("snapshot", "current"):
        for g, v in (("documented", "yes"), ("unclear", "unclear")):
            derived[(view, g)] = {u for u, rid in latest[view].items() if rows[(rid, u)][1] == v}

    targets = set().union(listed["documented"], listed["unclear"], *derived.values())
    need = defaultdict(set)
    for u in targets:
        for view in ("snapshot", "current"):
            rid = latest[view].get(u)
            if rid:
                need[rid].add(rows[(rid, u)][0])
    counts = {}
    with ProcessPoolExecutor(a.workers) as ex:
        for rid, res in ex.map(count_run, sorted((r, sorted(i)) for r, i in need.items())):
            counts[rid] = res
            print(f"{time.time()-t0:7.1f}s counted {rid} n={len(res)}", file=sys.stderr, flush=True)

    def rec(view, u):
        rid = latest[view].get(u)
        if rid is None:
            return None
        iid, verdict = rows[(rid, u)]
        return {"run": rid, "institution_id": iid, "verdict": verdict, **counts[rid][iid]}

    per_uid = {}
    for u in sorted(targets):
        s, c = rec("snapshot", u), rec("current", u)
        per_uid[u] = {
            "listed": next((g for g in listed if u in listed[g]), None),
            "snapshot": s,
            "current": c if (c is None or s is None or c["run"] != s["run"]) else "same",
        }

    def totals(uids, view):
        t = {"institutions": len(uids), "not_found_in_runs": 0, "no_inst_dir": 0,
             "inst_zero_src_pages": 0, "inst_zero_usable_src": 0, "inst_zero_usable_scrape": 0,
             "inst_any_raw_pdf_src": 0,
             "src": defaultdict(int), "scrape": defaultdict(int), "triage_keep": 0, "verdicts": defaultdict(int),
             "runs": defaultdict(int)}
        for u in uids:
            r = rec(view, u)
            if r is None:
                t["not_found_in_runs"] += 1
                continue
            t["verdicts"][r["verdict"]] += 1
            t["runs"][r["run"]] += 1
            t["no_inst_dir"] += not r["inst_dir"]
            t["inst_zero_src_pages"] += r["src"]["pages"] == 0
            t["inst_zero_usable_src"] += r["src"]["usable200"] == 0
            t["inst_zero_usable_scrape"] += r["scrape"]["usable200"] == 0
            t["inst_any_raw_pdf_src"] += r["src"]["raw_pdf"] > 0
            t["triage_keep"] += r["triage_keep"] or 0
            for k in ("src", "scrape"):
                for kk, vv in r[k].items():
                    t[k][kk] += vv
        return json.loads(json.dumps(t))

    group_totals = {}
    for view in ("snapshot", "current"):
        for g in ("documented", "unclear"):
            group_totals[f"listed_{g}@{view}"] = totals(listed[g], view)
            group_totals[f"derived_{g}@{view}"] = totals(derived[(view, g)], view)
    recon = {}
    for view in ("snapshot", "current"):
        for g in ("documented", "unclear"):
            d = derived[(view, g)]
            recon[f"{g}@{view}"] = {"listed": len(listed[g]), "derived": len(d),
                                    "listed_and_derived": len(listed[g] & d),
                                    "listed_not_derived": len(listed[g] - d),
                                    "derived_not_listed": len(d - listed[g]),
                                    "examples_listed_not_derived": sorted(listed[g] - d)[:20],
                                    "examples_derived_not_listed": sorted(d - listed[g])[:20]}

    me = Path(__file__).resolve()
    out = {
        "card": "T-001", "plan": "G3O pipeline reclassification v2.7",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": {"path": "scripts/spikes/t001_count_backfill.py",
                   "sha256": hashlib.sha256(me.read_bytes()).hexdigest()},
        "uid_lists": {"path": a.uids, "sha256": hashlib.sha256(Path(a.uids).read_bytes()).hexdigest(),
                      "documented": len(listed["documented"]), "unclear": len(listed["unclear"]),
                      "source": "RS-025 w001-documented-list.json.gz; RS-036 unclear-list.json (API as_of 2026-10-24T14:04:52Z)"},
        "as_of_utc": AS_OF.isoformat(), "runs_with_final": runs, "snapshot_runs_excluded": sorted(set(runs) - snapshot_runs),
        "duplicate_uid_rows_within_run": dict(multi),
        "definitions": __doc__,
        "reconciliation": recon, "group_totals": group_totals,
        "runtime_s": round(time.time() - t0, 1),
        "per_uid": per_uid,
    }
    Path(a.out).write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("reconciliation", "group_totals", "runtime_s", "script")}, indent=1))


if __name__ == "__main__":
    main()
