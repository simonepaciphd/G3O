"""T-016 re-pilot of the jev questions generated from the re-signed codebook (release 2.7, sha256 f0b1348c...).

Plan card T-016 (RC-D-005 E9). PI rulings 2026-10-30 (chat): page set 1 a (RS-008 / RS-009 local pages only, no
prior-wording comparison); size 800 random + 50 long pages; 3 a every question on every page (no gates); 7 a the
activity-pass questions see the page only; 8 a uniform random sample; 9 a multi-select items asked as one Choice,
full probability distribution kept (the ticked-value bar is set by the PI after the results); 10 a mechanical
stand-ins for extractor inputs: year candidates by the codebook's deterministic rule (four-digit years 2015-2030 in
the page part), v2.5 `source_snippet` quotes for the entailment question, v2.5 activity pairs within one institution
for the Stage 6 relation question, scale unit not asked. Procedural (accepted): cap USD 8, dry-run first.

Test only: no DB write, no publication, no verdict changed. Paid calls happen only in `run`, which Simone launches.

Modes:
  sample   draw the page sample and the entailment / Stage 6 units (free, local) -> sample.json
  dry-run  build every request the run would send, count requests and estimated tokens, no network (free)
  run      send the requests to jev (paid; needs TYPESAFE_API_KEY); resume-safe, append-only, stops at the cap
  report   per-question answer distributions and chosen-answer probabilities from the answers file (free)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import os
import random
import re
import sys
import tarfile
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GEN = REPO / "g3o" / "codebook" / "generated"
OUT_DIR = Path("H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/repilot-v27")
RS008 = Path("C:/Users/spaci/repos/G3O/runs/r20260830T114940Z-32ea-scrape.tar")
RS009 = [Path("H:/My Drive/Research/G3O/agent-workspace/2026-09-27-jev-compare/pulled/stored-subset.tar"),
         Path("H:/My Drive/Research/G3O/agent-workspace/2026-09-27-jev-compare/pulled/new-run-r20260928T141425Z-7d56.tar")]
META_TAR = Path("H:/My Drive/Research/G3O/agent-workspace/2026-09-27-jev-compare/pulled/analysis-meta.tar")
RS008_REPORT = "stored-runlevel/r20260830T114940Z-32ea/institution_report.csv"
MASTER = Path("H:/My Drive/Research/G3O/inputs/G3O_Institution_Master/data_final/master_institutions.csv")

SEED = 20261030
N_RANDOM, N_LONG, N_ENTAIL, N_PAIRS = 800, 50, 300, 150
CAP_USD = 8.00
PRICE_PER_MTOK = 0.042           # docs.typesafe.ai/models, 2026-10-30: input only, output free
TOK_PER_BYTE = 0.3947            # measured (unclear screen, 2026-10-27); provisional until T-002 calibrates
STATE_CAP_TOK = 24_000           # per chunk; keeps state + the longest question under jev's 32k per-question limit
REQ_CAP_TOK = 60_000             # packing target under jev's 64k per-request limit (state + all questions)
MAX_CHUNKS = 20                  # pages past 20 chunks are truncated and flagged (cost-model assumption)
MAX_SPLITS = 3
MIN_TEXT_BYTES = 200
YEAR_RE = re.compile(r"(?<!\d)(20(?:1[5-9]|2\d|30))(?!\d)")   # codebook C16 rule: four-digit years 2015-2030
SKIPPED = {"core.deployment_scale_unit"}                          # 10 a: no extracted scale number to show
ENTAIL_FIELDS = ["activity_type", "adoption_stage", "deployment_mode", "target_users", "access_type",
                 "interaction_type", "tool_name", "vendor", "has_human_oversight", "has_transparency_notice",
                 "has_data_classification", "has_risk_assessment", "year_announced", "year_deployed"]
NEGATIVE = {"", "_NA_", "no", "unknown", "not_documented", "none", "none_reported", "not_applicable"}


# ---------------------------------------------------------------- codebook-generated inputs
def load_generated():
    q = json.loads((GEN / "jev_questions.json").read_text(encoding="utf-8"))
    sp = (GEN / "system_prompt.md").read_text(encoding="utf-8")

    def section(name):
        m = re.search(rf"## `shared/{re.escape(name)}`\n\nApplies to:[^\n]*\n\n(.+?)(?=\n## |\Z)", sp, re.S)
        return m.group(1).strip()

    return q, section("system_prompt"), section("system_prompt_stage6")


def criteria_of(qd, part=False, years=None):
    crit = {c["code"]: c["text"] for c in qd["criteria"]}
    if years is not None:
        crit = {**{y: y for y in years}, **crit}           # candidates first, then the missing label(s)
    if part:
        pa = qd["part_prompt_answer"]
        crit[pa["label"]] = pa["meaning"]
    return crit


def est_tokens(s: str) -> int:
    return math.ceil(len(s.encode("utf-8")) * TOK_PER_BYTE)


# ---------------------------------------------------------------- corpora
def iter_pages(path: Path):
    """Yield (tar, member, run_id, institution_id) for stored pages with >= MIN_TEXT_BYTES of text."""
    with tarfile.open(path) as t:
        for m in t:
            n = m.name
            if not m.isfile() or "/scrape/" not in n or not (n.endswith(".json") or n.endswith(".json.gz")):
                continue
            parts = n.split("/")
            i = parts.index("institutions")
            yield m, parts[0].replace("-scrape", ""), parts[i + 2]


def read_member(t, m):
    b = t.extractfile(m).read()
    return gzip.decompress(b) if m.name.endswith(".gz") else b


def page_record(t, m):
    try:
        d = json.loads(read_member(t, m))
    except Exception:
        return None
    text = d.get("text") or ""
    return d if len(text.encode("utf-8")) >= MIN_TEXT_BYTES else None


def institution_meta():
    """institution_id -> {name, country, level} from RS-009 institution.json and, for RS-008, master by uid."""
    meta = {}
    for p in RS009:
        with tarfile.open(p) as t:
            for m in t:
                if m.name.endswith("/institution.json"):
                    d = json.loads(read_member(t, m))
                    meta[d["institution_id"]] = {"institution": d.get("institution_name"), "country": d.get("country"),
                                                 "level_of_government": d.get("level_of_government")}
    with tarfile.open(META_TAR) as t:
        rep = list(csv.DictReader(io.TextIOWrapper(t.extractfile(t.getmember(RS008_REPORT)), encoding="utf-8")))
    uid_of = {r["institution_id"]: r["institution_uid"] for r in rep}
    want = {u for i, u in uid_of.items() if i not in meta}
    with MASTER.open(encoding="utf-8", newline="") as f:
        by_uid = {r["institution_uid"]: r for r in csv.DictReader(f) if r["institution_uid"] in want}
    for iid, uid in uid_of.items():
        if iid not in meta and uid in by_uid:
            r = by_uid[uid]
            meta[iid] = {"institution": r["institution_name"], "country": r["country"],
                         "level_of_government": r["government_level"]}
    return meta


def v25_activities():
    """v2.5 gpt-5-nano activity rows from the RS-009 extract files (10 a stand-ins)."""
    rows = []
    for p in RS009:
        with tarfile.open(p) as t:
            for m in t:
                if "/extract/" in m.name and m.isfile():
                    d = json.loads(read_member(t, m))
                    for r in d.get("data", []):
                        if r.get("activity_name") not in (None, "_NA_"):
                            rows.append({k: r.get(k) for k in ["institution_id", "institution_name", "country",
                                         "activity_name", "scope_notes", "source_snippet", "source_url",
                                         "source_title", *ENTAIL_FIELDS]} | {"tar": p.name, "member": m.name})
    return rows


# ---------------------------------------------------------------- sample
def cmd_sample(_a):
    rng = random.Random(SEED)
    pool = []
    for p in [RS008, *RS009]:
        with tarfile.open(p) as t:
            for m, run, iid in iter_pages(p):
                d = page_record(t, m)
                if d:
                    nb = len(d["text"].encode("utf-8"))
                    pool.append({"tar": str(p), "member": m.name, "run_id": run, "institution_id": iid, "bytes": nb})
    is_long = lambda r: r["bytes"] * TOK_PER_BYTE > STATE_CAP_TOK  # noqa: E731
    rand = rng.sample(pool, N_RANDOM)
    taken = {r["member"] for r in rand}
    long_ = rng.sample([r for r in pool if is_long(r) and r["member"] not in taken], N_LONG)
    for r in rand:
        r["stratum"] = "random"
    for r in long_:
        r["stratum"] = "long"
    acts = v25_activities()
    ent = []
    cands = [(a, f) for a in acts for f in ENTAIL_FIELDS
             if a.get("source_snippet") and str(a.get(f) or "").strip() not in NEGATIVE]
    for a, f in rng.sample(cands, min(N_ENTAIL, len(cands))):
        ent.append({"field": f, "value": str(a[f]), "quote": a["source_snippet"], "activity_name": a["activity_name"],
                    "institution_id": a["institution_id"], "source_url": a["source_url"]})
    by_inst = defaultdict(list)
    for a in acts:
        by_inst[a["institution_id"]].append(a)
    all_pairs = [(x, y) for v in by_inst.values() for i, x in enumerate(v) for y in v[i + 1:]]
    pairs = rng.sample(all_pairs, min(N_PAIRS, len(all_pairs)))
    rec = lambda a: {k: a.get(k) for k in ("activity_name", "scope_notes", "source_snippet", "source_url",  # noqa: E731
                                           "source_title", "activity_type", "adoption_stage", "tool_name")}
    out = {"seed": SEED, "pool_pages": len(pool), "pool_long": sum(map(is_long, pool)),
           "v25_activities": len(acts), "entailment_candidates": len(cands), "pair_candidates": len(all_pairs),
           "pages": rand + long_, "entailment": ent,
           "pairs": [{"institution_id": x["institution_id"], "institution": x["institution_name"],
                      "country": x["country"], "first": rec(x), "second": rec(y)} for x, y in pairs]}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "sample.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if not isinstance(v, list)}, indent=1),
          "| pages", len(out["pages"]), "entailment", len(ent), "pairs", len(out["pairs"]))


# ---------------------------------------------------------------- request building
def byte_chunks(text, cap):
    out, cur, size = [], [], 0
    for ch in text:
        b = len(ch.encode("utf-8"))
        if size + b > cap and cur:
            out.append("".join(cur))
            cur, size = [], 0
        cur.append(ch)
        size += b
    out.append("".join(cur))
    return out


def page_units(sample, meta, gen):
    """Yield (key, state, {qid: question-dict}, info) per request, packed under REQ_CAP_TOK."""
    qs, sys_prompt, _ = gen
    page_qs = [q for q in qs["questions"] if q["pass"] in (1, 2) and q["question_id"] not in SKIPPED]
    cap_bytes = int(STATE_CAP_TOK / TOK_PER_BYTE)
    tars = {}
    for pg in sample["pages"]:
        t = tars.setdefault(pg["tar"], tarfile.open(pg["tar"]))
        d = json.loads(read_member(t, t.getmember(pg["member"])))
        cap = cap_bytes
        while True:  # size on the serialized state: JSON escaping inflates text (newlines, quotes)
            chunks = byte_chunks(d["text"], cap)
            if max(est_tokens(json.dumps(c, ensure_ascii=False)) for c in chunks[:MAX_CHUNKS]) + 1_500 <= STATE_CAP_TOK:
                break
            cap = int(cap * 0.85)
        truncated = len(chunks) > MAX_CHUNKS
        chunks = chunks[:MAX_CHUNKS]
        n, part = len(chunks), len(chunks) > 1
        inst = meta.get(pg["institution_id"], {})
        for i, ch in enumerate(chunks):
            state = {"coder_instructions": sys_prompt, "institution": inst.get("institution"),
                     "country": inst.get("country"), "level_of_government": inst.get("level_of_government"),
                     "page_url": d.get("url"), "page_title": d.get("title"), "page_part": f"{i + 1} of {n}",
                     "page_text": ch}
            if part:
                state["part_note"] = qs["part_prompt"]["sentence"]
            years = sorted(set(YEAR_RE.findall(ch)))
            base = est_tokens(json.dumps(state, ensure_ascii=False))
            req, size, r = {}, base, 0
            for q in page_qs:
                yrs = years if "candidates_not_offered" in q else None
                crit = criteria_of(q, part, yrs)
                qt = est_tokens(q["instructions"] + json.dumps(crit, ensure_ascii=False))
                if req and size + qt > REQ_CAP_TOK:
                    yield (f'{pg["member"]}|{i + 1}/{n}|r{r}', state, req, {"page": pg["member"], "chunk": i + 1,
                           "n_chunks": n, "truncated": truncated, "est_tokens": size, "stratum": pg["stratum"]})
                    req, size, r = {}, base, r + 1
                req[q["question_id"]] = {"instructions": q["instructions"], "criteria": crit}
                size += qt
            yield (f'{pg["member"]}|{i + 1}/{n}|r{r}', state, req, {"page": pg["member"], "chunk": i + 1,
                   "n_chunks": n, "truncated": truncated, "est_tokens": size, "stratum": pg["stratum"]})


def side_units(sample, gen):
    qs, sys_prompt, sys6 = gen
    byid = {q["question_id"]: q for q in qs["questions"]}
    qe, q6 = byid["core.support_entailment"], byid["core.activity_relation_cross_page"]
    for j, e in enumerate(sample["entailment"]):
        instr = qe["instructions"].replace("<field>", e["field"].replace("_", " ")).replace("<value>", e["value"])
        state = {"coder_instructions": sys_prompt, "text": e["quote"]}
        req = {"core.support_entailment": {"instructions": instr, "criteria": criteria_of(qe)}}
        yield (f"entail|{j}", state, req, {"unit": "entailment", "field": e["field"], "value": e["value"],
               "est_tokens": est_tokens(json.dumps([state, req], ensure_ascii=False))})
    for j, p in enumerate(sample["pairs"]):
        state = {"coder_instructions": sys6, "institution": p["institution"], "country": p["country"],
                 "first_record": p["first"], "second_record": p["second"]}
        req = {"core.activity_relation_cross_page": {"instructions": q6["instructions"], "criteria": criteria_of(q6)}}
        yield (f"pair|{j}", state, req, {"unit": "stage6_pair",
               "est_tokens": est_tokens(json.dumps([state, req], ensure_ascii=False))})


def all_units():
    sample = json.loads((OUT_DIR / "sample.json").read_text(encoding="utf-8"))
    gen = load_generated()
    meta = institution_meta()
    missing = sorted({p["institution_id"] for p in sample["pages"]} - set(meta))
    yield from page_units(sample, meta, gen)
    yield from side_units(sample, gen)
    if missing:
        print(f"WARNING: no institution metadata for {len(missing)} sampled institutions", file=sys.stderr)


# ---------------------------------------------------------------- modes
def cmd_dry_run(_a):
    c, tok, chunks, trunc = Counter(), Counter(), set(), set()
    qcount = Counter()
    for _key, _state, req, info in all_units():
        unit = info.get("unit", "page")
        c[unit] += 1
        tok[unit] += info["est_tokens"]
        qcount.update(req.keys())
        if unit == "page":
            chunks.add((info["page"], info["chunk"]))
            if info["truncated"]:
                trunc.add(info["page"])
    total = sum(tok.values())
    rep = {"requests": dict(c), "est_tokens": dict(tok), "chunks": len(chunks), "pages_truncated_at_20": len(trunc),
           "questions_asked": len(qcount), "question_asks": sum(qcount.values()),
           "est_usd_central": round(total * PRICE_PER_MTOK / 1e6, 2),
           "est_usd_range": [round(total * f * PRICE_PER_MTOK / 1e6, 2) for f in (0.30 / 0.3947, 0.45 / 0.3947)],
           "cap_usd": CAP_USD, "tokens_per_byte": TOK_PER_BYTE, "note": "range scales tokens/byte 0.30-0.45"}
    (OUT_DIR / "dryrun.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1))


def cmd_run(a):
    sys.path.insert(0, str(REPO))
    import typesafe_sdk as ts

    from g3o.common import jev_client
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set in this shell; set it and rerun.")
    client = ts.TypeSafeClient(api_key=os.environ["TYPESAFE_API_KEY"], model=jev_client.DEFAULT_JEV_MODEL,
                               retry=ts.RetryPolicy(max_retries=5, backoff_initial=1.0, backoff_max=30.0, timeout=None))
    out = OUT_DIR / "answers-t016.jsonl"
    done, spent = set(), 0
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done.add(r["key"])
            spent += r.get("input_tokens", 0)
    cap = a.cap_usd

    def ask(state, req, depth=0):
        qs = {k: ts.Choice(instructions=v["instructions"], criteria=v["criteria"]) for k, v in req.items()}
        try:
            return [jev_client.ask(state, qs, client=client)]
        except Exception as e:
            if "max_tokens_exceeded" in repr(e) and depth < MAX_SPLITS and state.get("page_text"):
                text = state["page_text"]
                res = []
                for j, h in enumerate(byte_chunks(text, max(len(text.encode("utf-8")) // 2, 1))):
                    res += ask({**state, "page_text": h, "page_part": f'{state["page_part"]}.{j + 1}'}, req, depth + 1)
                return res
            raise

    with out.open("a", encoding="utf-8") as f:
        for key, state, req, info in all_units():
            if key in done:
                continue
            if spent * PRICE_PER_MTOK / 1e6 + info["est_tokens"] * PRICE_PER_MTOK / 1e6 > cap:
                print(f"CAP REACHED at {spent} tokens (${spent * PRICE_PER_MTOK / 1e6:.2f})")
                return
            t0 = time.time()
            try:
                res = ask(state, req)
            except Exception as e:
                f.write(json.dumps({"key": key, "info": info, "error": repr(e)[:500], "input_tokens": 0}) + "\n")
                f.flush()
                if isinstance(e, jev_client.JevAccountError):
                    raise
                continue
            tok = sum(r.input_tokens for r in res)
            spent += tok
            f.write(json.dumps({"key": key, "info": info, "input_tokens": tok, "latency_s": round(time.time() - t0, 2),
                                "parts": [{"request_id": r.request_id, "model": r.response_model,
                                           "answers": {q: {"choice": x.choice, "confidence": x.confidence,
                                                           "probabilities": x.probabilities}
                                                       for q, x in r.answers.items()}} for r in res]},
                               ensure_ascii=False) + "\n")
            f.flush()
    print("input tokens", spent, "usd", round(spent * PRICE_PER_MTOK / 1e6, 4))


def cmd_report(_a):
    rows = [json.loads(line) for line in (OUT_DIR / "answers-t016.jsonl").read_text(encoding="utf-8").splitlines()]
    dist, probs, bar, n = defaultdict(Counter), defaultdict(list), Counter(), Counter()
    tokens = sum(r.get("input_tokens", 0) for r in rows)
    for r in rows:
        for p in r.get("parts", []):
            for q, x in p["answers"].items():
                dist[q][x["choice"]] += 1
                n[q] += 1
                if x["confidence"] is not None:
                    probs[q].append(x["confidence"])
                    bar[q] += x["confidence"] >= 0.8
    rep = {"requests": len(rows), "errors": sum("error" in r for r in rows), "input_tokens": tokens,
           "usd": round(tokens * PRICE_PER_MTOK / 1e6, 4),
           "per_question": {q: {"n": n[q], "distribution": dict(dist[q].most_common()),
                                "mean_chosen_probability": round(sum(probs[q]) / len(probs[q]), 3) if probs[q] else None,
                                "share_at_or_above_0.8": round(bar[q] / n[q], 3) if n[q] else None}
                            for q in sorted(n)}}
    (OUT_DIR / "report-t016.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "per_question"}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sample", "dry-run", "run", "report"])
    ap.add_argument("--cap-usd", type=float, default=CAP_USD)
    a = ap.parse_args()
    {"sample": cmd_sample, "dry-run": cmd_dry_run, "run": cmd_run, "report": cmd_report}[a.mode](a)
