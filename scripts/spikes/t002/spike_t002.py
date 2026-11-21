"""T-002 spike runner: jev two-pass cost, latency and fan-out on <= 50 pages, plus the Haiku extractor leg.

Plan card: planning/PLAN.md T-002 (origin/main). PI rulings 2026-10-30: DP-001 (50 pages from RS-008 + RS-009, in
proportion, >= 10 CJK/Thai, some long pages, fixed seed), DP-002 (Haiku sync on all pages + a 10-page Message Batches
subset), spending cap $6.

Modes
  dry-run    free. Streams the tars, draws the sample, builds every request the paid run would send (gated legs with
             placeholder inputs), estimates tokens and cost. Writes SPIKE-T002-dryrun.json. Sends nothing.
  run        PAID. Simone runs it (red line 4). Needs TYPESAFE_API_KEY in the environment and ANTHROPIC_API_KEY
             from --env-file. Append-only, resume-safe (done keys are skipped), cap check before every call.
  summarize  free. Reads SPIKE-T002-answers.jsonl and writes SPIKE-T002-summary.json (counts, tokens, latency,
             failures, chunk counts, estimator fit per script, cost per 1k pages).

Legs (paid mode), per page in sample order:
  J-P1R1  jev pass 1, round 1, every page x chunk: re-pilot 2 verdict + CX form            (proxy questions)
  J-P1R2  jev pass 1, round 2, chunks of pages whose form is a register or mandated_report: CX scope
  H-SPAN  Haiku sync, every page x chunk: spans and extractor fields (generated v2.7 extractor sections)
  H-PQ    Haiku sync, every page x chunk: quote step for the page items (generated v2.7 pass-1 items)
  J-SEG   jev segmentation, GenAI-bearing pages, chunks with >= 2 spans: one question per span pair
          (values from the generated v2.7 core.activity_segment section)
  J-P2A1  jev pass 2, every activity x chunk: CX evaluation_documented + 10 content questions
  J-P2A3  jev pass 2, round 3, activities whose evaluation is in EVAL_SET: 6 CX evaluation types
  H-AQ    Haiku sync, every activity x chunk: quote step for every activity item, including items the
          applicability table would skip (RC-D-003 section 12)
  B1/B2   Message Batches on a 10-page subset: B1 = H-SPAN + H-PQ requests, B2 = H-AQ requests (2 sequential rounds)
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import random
import re
import sys
import tarfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

import proxy_questions as PQ  # noqa: E402
import t002_core as C  # noqa: E402

csv.field_size_limit(10**9)

SEED = 20261030
N_PAGES = 50
MIN_NONLATIN = 10           # DP-001: at least 10 CJK/Thai pages
MIN_THAI = 3                # of those, at least 3 Thai, so each script has calibration evidence (engineer's choice)
N_LONG = 6                  # DP-001 "some long pages" (> 1 chunk); this count is the engineer's choice
MAX_LONG_CHUNKS = 8         # long pages drawn only up to 8 chunks, to bound cost (engineer's choice; listed)
N_BATCH = 10                # DP-002
CAP_USD = 6.00
MIN_TEXT_CHARS = 200        # pilot.py eligibility
HAIKU_MODEL = "claude-haiku-5-5"
HAIKU_EFFORT = "medium"
HAIKU_MAX_TOKENS = 16_000
QUOTE_ITEM_TEXT = "full"  # PI ruling 12b (2026-10-31): full item text incl. rules; alternative "definitions" drops the repeated rules

RS008 = [("RS-008", Path("C:/Users/spaci/repos/G3O/runs/r20260830T114940Z-32ea-scrape.tar"))]
RS009 = [("RS-009", Path("H:/My Drive/Research/G3O/agent-workspace/2026-09-27-jev-compare/pulled/stored-subset.tar")),
         ("RS-009", Path("H:/My Drive/Research/G3O/agent-workspace/2026-09-27-jev-compare/pulled/"
                         "new-run-r20260928T141425Z-7d56.tar"))]
MASTER = Path("H:/My Drive/Research/G3O/inputs/G3O_Institution_Master/data_final/master_institutions.csv")
OUT_DIR = Path("H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/spikes")
GEN = REPO / "g3o" / "codebook" / "generated"

MEMBER_RE = re.compile(r"^(?:(?P<run>r\d{8}T\d{6}Z-[0-9a-f]{4})/)?institutions/[^/]+/(?P<inst>INST-\d+)/"
                       r"(?P<kind>scrape|extract)/(?P<h>[0-9a-f]{32})\.json\.gz$")
INST_RE = re.compile(r"^(?:(?P<run>r\d{8}T\d{6}Z-[0-9a-f]{4})/)?institutions/[^/]+/(?P<inst>INST-\d+)/institution\.json$")
RS008_RUN = "r20260830T114940Z-32ea"
REGISTER_FORMS = ("register_cross_institution", "register_single_institution", "mandated_report")
SAME_LINKS = ("same_activity", "shared_participation")  # merged into one activity (generated value definitions)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# =====================================================================================================
# Corpus: stream the tars in place (never extracted), draw the sample, load the chosen pages
# =====================================================================================================

def scan_corpora():
    """One streaming pass over every tar. Returns (candidates, inst_meta, extract_labels, scrape_keys)."""
    cands, inst_meta, labels, keys = [], {}, {}, Counter()
    seen = set()
    for corpus, tar in RS008 + RS009:
        with tarfile.open(tar, "r|") as tf:
            for m in tf:
                if not m.isfile():
                    continue
                mi = INST_RE.match(m.name)
                if mi:
                    d = json.loads(tf.extractfile(m).read())
                    inst_meta[(mi["run"] or RS008_RUN, mi["inst"])] = {
                        "institution_name": d.get("institution_name"), "country": d.get("country"),
                        "level_of_government": d.get("level_of_government"), "source": "institution.json"}
                    continue
                mm = MEMBER_RE.match(m.name)
                if not mm:
                    continue
                run = mm["run"] or RS008_RUN
                d = json.loads(gzip.decompress(tf.extractfile(m).read()))
                if mm["kind"] == "extract":
                    ev = sorted({r.get("genai_evidence") for r in d.get("data") or [] if r.get("genai_evidence")})
                    labels[(run, mm["inst"], mm["h"])] = ev
                    continue
                keys.update(d.keys())
                text = d.get("text") or ""
                fm = d.get("fetch_metadata") or {}
                if fm.get("http_status") not in (200, None) or len(text.strip()) < MIN_TEXT_CHARS:
                    continue
                dedupe = (mm["inst"], mm["h"])
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                nb = C.utf8_len(text)
                sb = C.script_bytes(text)
                cands.append({
                    "page_id": f"{corpus}:{run}:{mm['inst']}:{mm['h']}", "corpus": corpus, "tar": str(tar),
                    "member": m.name, "run_id": run, "institution_id": mm["inst"], "url_hash": mm["h"],
                    "url": d.get("url"), "content_type": d.get("content_type"), "bytes": nb,
                    "script": C.dominant_script(text), "script_bytes": sb,
                    "n_chunks": len(C.byte_chunks(text, C.chunk_byte_cap()))})
    return cands, inst_meta, labels, keys


def _split(total: int, weights: dict[str, int]) -> dict[str, int]:
    """Largest-remainder split of `total` in proportion to `weights`."""
    s = sum(weights.values()) or 1
    raw = {k: total * w / s for k, w in weights.items()}
    out = {k: math.floor(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: total - sum(out.values())]:
        out[k] += 1
    return out


def draw_sample(cands: list[dict], seed: int = SEED) -> tuple[list[dict], dict]:
    """DP-001 draw: corpora in proportion to eligible pages; quotas for CJK/Thai and long pages first, then random."""
    rng = random.Random(seed)
    by_corpus = defaultdict(list)
    for c in sorted(cands, key=lambda c: c["page_id"]):
        by_corpus[c["corpus"]].append(c)
    n_c = _split(N_PAGES, {k: len(v) for k, v in by_corpus.items()})
    q_nl = _split(MIN_NONLATIN, {k: len(v) for k, v in by_corpus.items()})
    q_long = _split(N_LONG, {k: len(v) for k, v in by_corpus.items()})
    picked, notes = [], {"pool": {k: len(v) for k, v in by_corpus.items()}, "n_per_corpus": n_c,
                         "nonlatin_quota": q_nl, "long_quota": q_long,
                         "pool_by_script": {k: dict(Counter(c["script"] for c in v)) for k, v in by_corpus.items()},
                         "pool_long_pages": {k: sum(c["n_chunks"] > 1 for c in v) for k, v in by_corpus.items()},
                         "pool_over_max_long_chunks": {k: sum(c["n_chunks"] > MAX_LONG_CHUNKS for c in v)
                                                       for k, v in by_corpus.items()}}
    shortfall = {"nonlatin": 0, "long": 0}
    for corpus in sorted(by_corpus):
        pool = list(by_corpus[corpus])
        rng.shuffle(pool)
        mine = []
        nl = [p for p in pool if p["script"] in ("cjk", "thai")]
        take = nl[: q_nl[corpus]]
        shortfall["nonlatin"] += q_nl[corpus] - len(take)
        mine += take
        lg = [p for p in pool if 1 < p["n_chunks"] <= MAX_LONG_CHUNKS and p not in mine]
        take = lg[: q_long[corpus]]
        shortfall["long"] += q_long[corpus] - len(take)
        mine += take
        rest = [p for p in pool if p not in mine and p["n_chunks"] <= MAX_LONG_CHUNKS]
        mine += rest[: max(n_c[corpus] - len(mine), 0)]
        picked += mine
    # Shortfalls in one corpus are made up from the other (still seeded).
    for kind, test in (("nonlatin", lambda p: p["script"] in ("cjk", "thai")),
                       ("long", lambda p: 1 < p["n_chunks"] <= MAX_LONG_CHUNKS)):
        if shortfall[kind] > 0:
            extra = [p for p in sorted(cands, key=lambda c: c["page_id"]) if test(p) and p not in picked]
            rng.shuffle(extra)
            for p in extra[: shortfall[kind]]:
                # replace a random plain Latin single-chunk page of the same corpus
                plain = [q for q in picked if q["corpus"] == p["corpus"] and q["script"] == "latin"
                         and q["n_chunks"] == 1]
                if plain:
                    picked.remove(rng.choice(plain))
                picked.append(p)
    # Thai floor inside the non-Latin quota: swap Thai pages in for CJK pages of the same corpus.
    thai = [p for p in sorted(cands, key=lambda c: c["page_id"]) if p["script"] == "thai" and p not in picked
            and p["n_chunks"] <= MAX_LONG_CHUNKS]
    rng.shuffle(thai)
    swaps = 0
    while sum(p["script"] == "thai" for p in picked) < MIN_THAI and thai:
        t = thai.pop()
        cjk = [q for q in picked if q["corpus"] == t["corpus"] and q["script"] == "cjk" and q["n_chunks"] == 1]
        if not cjk:
            continue
        picked.remove(rng.choice(cjk))
        picked.append(t)
        swaps += 1
    notes["thai_swaps"] = swaps
    notes["shortfall_made_up_across_corpora"] = shortfall
    picked.sort(key=lambda p: p["page_id"])
    return picked, notes


def master_lookup(inst_ids: set[str]) -> dict[str, dict]:
    want = {str(int(i.split("-")[1])): i for i in inst_ids}
    out = {}
    with MASTER.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            i = want.get(r["master_row_id"])
            if i:
                out[i] = {"institution_name": r["institution_name"], "country": r["country"],
                          "level_of_government": r["government_level"], "source": "master_institutions.csv"}
    return out


def attach_meta(pages, inst_meta, labels):
    missing = {p["institution_id"] for p in pages if (p["run_id"], p["institution_id"]) not in inst_meta}
    master = master_lookup(missing) if missing else {}
    for p in pages:
        p["institution"] = inst_meta.get((p["run_id"], p["institution_id"])) or master.get(p["institution_id"]) or {
            "institution_name": None, "country": None, "level_of_government": None, "source": "not found"}
        p["v25_genai_evidence"] = labels.get((p["run_id"], p["institution_id"], p["url_hash"]))


def load_texts(pages: list[dict]) -> dict[str, dict]:
    """Second streaming pass: fetch text and title of the chosen members only."""
    want = defaultdict(dict)
    for p in pages:
        want[p["tar"]][p["member"]] = p["page_id"]
    out = {}
    for tar, members in want.items():
        with tarfile.open(tar, "r|") as tf:
            for m in tf:
                pid = members.get(m.name)
                if pid:
                    d = json.loads(gzip.decompress(tf.extractfile(m).read()))
                    out[pid] = {"text": d.get("text") or "", "title": d.get("title") or ""}
                    if len(out) == len(pages):
                        break
    return out


def build_sample():
    cands, inst_meta, labels, keys = scan_corpora()
    pages, notes = draw_sample(cands)
    attach_meta(pages, inst_meta, labels)
    notes["scrape_record_keys"] = dict(keys)
    notes["eligible_candidates"] = len(cands)
    return pages, notes


# =====================================================================================================
# Request builders (shared by dry-run and paid mode)
# =====================================================================================================

def chunk_label(i: int, n: int, sub: str = "") -> str:
    return f"{i + 1} of {n}{sub}"


def p1_state(page, title, text, part):  # unclear2.py state
    ins = page["institution"]
    return {"institution": ins["institution_name"], "country": ins["country"],
            "level_of_government": ins["level_of_government"], "page_url": page["url"],
            "page_title": title, "page_part": part, "page_text": text}


def p2_state(page, title, text, part, activity):  # pilot.py state_for, activity from the Haiku spans
    ins = page["institution"]
    return {"institution": ins["institution_name"], "country": ins["country"],
            "genai_activity": {"activity_name": activity.get("activity_name"), "tool_name": activity.get("tool_name"),
                               "passage": activity.get("passage")},
            "page_url": page["url"], "page_title": title, "page_part": part, "page_text": text}


def seg_state(page, title, text, part, passages):
    ins = page["institution"]
    return {"institution": ins["institution_name"], "country": ins["country"], "page_url": page["url"],
            "page_title": title, "page_part": part, "passages": passages, "page_text": text}


def q(instructions, criteria):
    return {"instructions": instructions, "criteria": dict(criteria)}


Q_P1R1 = {"verdict": q(PQ.VERDICT_INSTRUCTIONS, PQ.VERDICT), "disclosure_form": q(PQ.FORM_INSTRUCTIONS, PQ.FORM)}
Q_P1R2 = {"disclosure_scope": q(PQ.SCOPE_INSTRUCTIONS, PQ.SCOPE)}
Q_P2A1 = {"evaluation_documented": q(PQ.EVAL_INSTRUCTIONS, PQ.EVAL),
          **{k: q(PQ.CONTENT_INSTRUCTIONS_TEMPLATE.format(v=v), PQ.CONTENT_CRITERIA) for k, v in PQ.CONTENT.items()}}
Q_P2A3 = {k: q(PQ.TYPE_INSTRUCTIONS_TEMPLATE.format(v=v) + PQ.EVAL_EMPHASIS, PQ.TYPE_CRITERIA)
          for k, v in PQ.EVAL_TYPES.items()}


def _gen_text(name):
    return (GEN / name).read_text(encoding="utf-8")


def load_generated():
    sp = _gen_text("system_prompt.md")
    m = re.search(r"## `shared/system_prompt`\n\nApplies to:[^\n]*\n\n(.+?)\n\n## ", sp, re.S)
    system = m.group(1).strip()
    sections = _gen_text("extractor_prompt_sections.md")
    body = sections[sections.index("## `core.source_publication_date`"):]
    seg = body[body.index("## `core.activity_segment`"): body.index("## `core.activity_name`")]
    seg_instr = re.search(r"### Instruction\n\n(.+?)\n\n", seg, re.S).group(1).strip()
    seg_values = {}
    for vm in re.finditer(r"#### `(\w+)`\n<!-- value: \w+ -->\n\n(.+?)(?=\n#### |\Z)", seg, re.S):
        seg_values[vm.group(1)] = vm.group(2).strip()
    jq = json.loads(_gen_text("jev_questions.json"))
    manifest = {"codebook_release": jq["codebook_release"], "codebook_sha256": jq["codebook_sha256"],
                "files": {n: hashlib.sha256((GEN / n).read_bytes()).hexdigest()
                          for n in ("system_prompt.md", "extractor_prompt_sections.md", "jev_questions.json")}}
    return {"system": system, "sections": body, "seg_instructions": seg_instr, "seg_values": seg_values,
            "questions": jq["questions"], "manifest": manifest}


def item_block(qn: dict, mode: str = QUOTE_ITEM_TEXT) -> str:
    lines = [f"### `{qn['question_id']}` (column `{qn['column']}`)", qn["instructions"], "Values:"]
    for c in qn["criteria"]:
        t = c["text"] if mode == "full" else c["text"].split("\n\nRules:")[0]
        lines.append(f"- `{c['code']}`: {t}")
    return "\n".join(lines)


def quote_items(gen, level: str) -> list[dict]:
    p = 1 if level == "page" else 2
    return [x for x in gen["questions"] if x["pass"] == p]


# Procedural framing written for the spike (not codebook wording; listed in the return report for review).
SPAN_TASK = ("Below are the codebook's extractor sections, then one page (or one part of one) about the named "
             "institution. Find every passage that describes a generative-AI activity, as the activity rule in "
             "`core.activity_segment` defines one, and for each passage fill the extractor fields from its "
             "sections, copying the exact words from the page; use an empty string when the page does not state "
             "a field. Also give the page's publication date with its verbatim quote, or empty strings.")
QUOTE_TASK = ("Below are coding items, then one page (or one part of one) about the named institution{act}. For each "
              "item, copy from the page every passage that a coder would need to answer it, exactly as written. Do "
              "not answer the items. Give an empty list for an item the text says nothing about.")

SPAN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["source_publication_date", "spans"],
    "properties": {
        "source_publication_date": {"type": "object", "additionalProperties": False, "required": ["date", "quote"],
                                    "properties": {"date": {"type": "string"}, "quote": {"type": "string"}}},
        "spans": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["passage", "activity_name", "observed_actor_name", "organisational_unit", "tool_name",
                         "model_name", "contracting_party", "deployment_scale_number", "reported_outcomes",
                         "reported_incidents"],
            "properties": {k: {"type": "string"} for k in (
                "passage", "activity_name", "observed_actor_name", "organisational_unit", "tool_name", "model_name",
                "contracting_party", "deployment_scale_number", "reported_outcomes", "reported_incidents")}}}}}


def quote_schema(item_ids):
    return {"type": "object", "additionalProperties": False, "required": ["items"],
            "properties": {"items": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["item", "quotes"],
                "properties": {"item": {"type": "string", "enum": list(item_ids)},
                               "quotes": {"type": "array", "items": {"type": "string"}}}}}}}


def page_block(page, title, text, part, activity=None):
    ins = page["institution"]
    head = {"institution": ins["institution_name"], "country": ins["country"], "page_url": page["url"],
            "page_title": title, "page_part": part}
    if activity is not None:
        head["genai_activity"] = {"activity_name": activity.get("activity_name"),
                                  "tool_name": activity.get("tool_name"), "passage": activity.get("passage")}
    return "<page_meta>\n" + json.dumps(head, ensure_ascii=False) + "\n</page_meta>\n<page_text>\n" + text + \
        "\n</page_text>"


def haiku_params(gen, user_text, schema):
    return {"model": HAIKU_MODEL, "max_tokens": HAIKU_MAX_TOKENS, "system": gen["system"],
            "messages": [{"role": "user", "content": user_text}],
            "output_config": {"effort": HAIKU_EFFORT, "format": {"type": "json_schema", "schema": schema}}}


def span_params(gen, page, title, text, part):
    user = SPAN_TASK + "\n\n<extractor_sections>\n" + gen["sections"] + "\n</extractor_sections>\n\n" + \
        page_block(page, title, text, part)
    return haiku_params(gen, user, SPAN_SCHEMA)


def quote_params(gen, page, title, text, part, level, activity=None):
    items = quote_items(gen, level)
    act = ", for the GenAI activity named in page_meta" if activity is not None else ""
    user = QUOTE_TASK.format(act=act) + "\n\n<items>\n" + "\n\n".join(item_block(x) for x in items) + \
        "\n</items>\n\n" + page_block(page, title, text, part, activity)
    return haiku_params(gen, user, quote_schema([x["question_id"] for x in items]))


def params_bytes(p) -> int:
    return C.utf8_len(p["system"]) + C.utf8_len(p["messages"][0]["content"]) + \
        C.utf8_len(json.dumps(p["output_config"]["format"]["schema"]))


def seg_questions(gen, passages: dict[str, str]) -> dict[str, dict]:
    ids = list(passages)
    out = {}
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            instr = (gen["seg_instructions"] + f" First passage: {ids[a]}. Second passage: {ids[b]}. "
                     "The passages are given in the state under `passages`.")
            out[f"{ids[a]}~{ids[b]}"] = q(instr, gen["seg_values"])
    return out


# =====================================================================================================
# Dry run
# =====================================================================================================

SCENARIOS = {  # gated-leg assumptions (not measurements); Haiku output tokens per call per the brief
    "low": {"genai_share": 0.2, "spans_per_genai_chunk": 1, "activities_per_genai_page": 1.0, "register_share": 0.05,
            "eval_share": 0.1, "haiku_out": 1500},
    "central": {"genai_share": 0.4, "spans_per_genai_chunk": 2, "activities_per_genai_page": 1.5,
                "register_share": 0.15, "eval_share": 0.2, "haiku_out": 3000},
    "high": {"genai_share": 1.0, "spans_per_genai_chunk": 4, "activities_per_genai_page": 4.0, "register_share": 0.5,
             "eval_share": 0.5, "haiku_out": 8000},
}


def dry_run(args):
    t0 = time.time()
    gen = load_generated()
    pages, notes = build_sample()
    texts = load_texts(pages)
    placeholder_act = {"activity_name": "PLACEHOLDER activity name", "tool_name": "PLACEHOLDER tool",
                       "passage": "PLACEHOLDER passage " * 20}
    per_page, warnings = [], []
    sizes = defaultdict(list)  # leg -> per-request estimated tokens (fixed legs exact; gated legs per chunk)
    for p in pages:
        t = texts[p["page_id"]]
        parts = C.byte_chunks(t["text"], C.chunk_byte_cap())
        n = len(parts)
        row = {k: p[k] for k in ("page_id", "corpus", "institution_id", "url", "content_type", "bytes", "script",
                                 "script_bytes", "n_chunks", "v25_genai_evidence")}
        row["institution"] = p["institution"]
        row["chunk_bytes"] = [C.utf8_len(x) for x in parts]
        leg_tok = defaultdict(list)
        for i, ch in enumerate(parts):
            part = chunk_label(i, n)
            st = p1_state(p, t["title"], ch, part)
            leg_tok["J-P1R1"].append(C.est_jev_tokens(st, Q_P1R1))
            leg_tok["J-P1R2"].append(C.est_jev_tokens(st, Q_P1R2))
            st_tokens = math.ceil(C.utf8_len(C.state_text(st)) * C.JEV_TOKENS_PER_BYTE)
            if st_tokens > C.JEV_STATE_TOKENS:
                warnings.append(f"{p['page_id']} chunk {part}: state estimate {st_tokens} > 32k")
            passages = {f"P{k + 1}": placeholder_act["passage"] for k in range(2)}
            sst = seg_state(p, t["title"], ch, part, passages)
            sq = seg_questions(gen, passages)
            pq_tok = math.ceil(sum(C.utf8_len(C.question_text(x)) for x in sq.values()) * C.JEV_TOKENS_PER_BYTE)
            sst_tok = math.ceil(C.utf8_len(C.state_text(sst)) * C.JEV_TOKENS_PER_BYTE)
            leg_tok["J-SEG(per pair question)"].append(pq_tok)
            leg_tok["J-SEG(state)"].append(sst_tok)
            leg_tok["J-SEG(pairs per request)"].append((C.JEV_REQUEST_TOKENS - sst_tok - 2000) // pq_tok)
            p2 = p2_state(p, t["title"], ch, part, placeholder_act)
            leg_tok["J-P2A1"].append(C.est_jev_tokens(p2, Q_P2A1))
            leg_tok["J-P2A3"].append(C.est_jev_tokens(p2, Q_P2A3))
            for leg, prm in (("H-SPAN", span_params(gen, p, t["title"], ch, part)),
                             ("H-PQ", quote_params(gen, p, t["title"], ch, part, "page")),
                             ("H-AQ", quote_params(gen, p, t["title"], ch, part, "activity", placeholder_act))):
                tok = math.ceil(params_bytes(prm) / C.HAIKU_BYTES_PER_TOKEN)
                leg_tok[leg].append(tok)
                if tok > C.HAIKU_LONG_PROMPT_TOKENS:
                    warnings.append(f"{p['page_id']} {leg} {part}: prompt estimate {tok} > 100k (long-prompt rate)")
        for k, v in leg_tok.items():
            sizes[k] += v
        row["est_tokens_per_chunk"] = dict(leg_tok)
        per_page.append(row)

    # Fixed request counts (exact) and gated counts (scenario).
    chunks = sum(r["n_chunks"] for r in per_page)
    batch_ids = pick_batch_subset(pages)
    batch_chunks = sum(r["n_chunks"] for r in per_page if r["page_id"] in batch_ids)

    def sum_leg(leg, rows=None):
        rows = rows or per_page
        return sum(sum(r["est_tokens_per_chunk"][leg]) for r in rows)

    seg_q_tokens = sum_leg("J-SEG(per pair question)")  # one pair question, summed over chunks
    seg_cap = min(min(r["est_tokens_per_chunk"]["J-SEG(pairs per request)"]) for r in per_page)
    est = {}
    for name, s in SCENARIOS.items():
        g, sp, a, rs, e, out = (s["genai_share"], s["spans_per_genai_chunk"], s["activities_per_genai_page"],
                                s["register_share"], s["eval_share"], s["haiku_out"])
        pairs = sp * (sp - 1) / 2
        req = {
            "J-P1R1": chunks, "J-P1R2": rs * chunks,
            "H-SPAN": chunks, "H-PQ": chunks,
            "J-SEG": g * chunks * (math.ceil(pairs / seg_cap) if pairs else 0),
            "J-P2A1": g * a * chunks, "J-P2A3": g * a * e * chunks, "H-AQ": g * a * chunks,
            "B1": 2 * batch_chunks, "B2": g * a * batch_chunks,
        }
        jev_tok = {
            "J-P1R1": sum_leg("J-P1R1"), "J-P1R2": rs * sum_leg("J-P1R2"),
            "J-SEG": g * (math.ceil(pairs / seg_cap) * sum_leg("J-SEG(state)") + pairs * seg_q_tokens) if pairs else 0,
            "J-P2A1": g * a * sum_leg("J-P2A1"), "J-P2A3": g * a * e * sum_leg("J-P2A3")}
        b_rows = [r for r in per_page if r["page_id"] in batch_ids]
        h_in = {"H-SPAN": sum_leg("H-SPAN"), "H-PQ": sum_leg("H-PQ"), "H-AQ": g * a * sum_leg("H-AQ"),
                "B1": sum_leg("H-SPAN", b_rows) + sum_leg("H-PQ", b_rows), "B2": g * a * sum_leg("H-AQ", b_rows)}
        h_out = {k: req[k] * out for k in h_in}
        cost = {k: C.jev_cost(v) for k, v in jev_tok.items()}
        for k in h_in:
            cost[k] = C.haiku_cost(h_in[k], h_out[k], batch=k.startswith("B"))
        est[name] = {"assumptions": s, "requests": {k: round(v, 1) for k, v in req.items()},
                     "jev_input_tokens": {k: round(v) for k, v in jev_tok.items()},
                     "haiku_input_tokens": {k: round(v) for k, v in h_in.items()},
                     "haiku_output_tokens": {k: round(v) for k, v in h_out.items()},
                     "cost_usd": {k: round(v, 4) for k, v in cost.items()},
                     "total_usd": round(sum(cost.values()), 4),
                     "under_cap": sum(cost.values()) <= CAP_USD}

    scripts = Counter(r["script"] for r in per_page)
    out = {
        "generated_at": now(), "mode": "dry-run (no request sent)", "seed": SEED, "cap_usd": CAP_USD,
        "codebook": gen["manifest"],
        "estimator": {"jev_tokens_per_byte": C.JEV_TOKENS_PER_BYTE, "chunk_state_tokens": C.CHUNK_STATE_TOKENS,
                      "chunk_byte_cap": C.chunk_byte_cap(), "dp007_margin": "unset",
                      "haiku_bytes_per_token": C.HAIKU_BYTES_PER_TOKEN,
                      "haiku_note": "Haiku tokens estimated as bytes/3.2 (assumption; no free keyless token counter). "
                                    "Output tokens per call unknown: 1.5k / 3k / 8k low / central / high (brief)."},
        "prices_usd_per_mtok": {"jev_in": C.JEV_IN_PER_M, "haiku_sync_in": C.HAIKU_SYNC_IN_PER_M,
                                "haiku_sync_out": C.HAIKU_SYNC_OUT_PER_M, "haiku_batch_in": C.HAIKU_BATCH_IN_PER_M,
                                "haiku_batch_out": C.HAIKU_BATCH_OUT_PER_M},
        "sample": {"n_pages": len(per_page), "n_chunks": chunks, "by_script": dict(scripts),
                   "nonlatin_pages": scripts["cjk"] + scripts["thai"],
                   "long_pages": sum(r["n_chunks"] > 1 for r in per_page),
                   "by_corpus": dict(Counter(r["corpus"] for r in per_page)),
                   "institution_meta_source": dict(Counter(r["institution"]["source"] for r in per_page)),
                   "v25_genai_evidence": dict(Counter(",".join(r["v25_genai_evidence"] or ["(no extract record)"])
                                                  for r in per_page)),
                   "draw_notes": notes, "batch_subset": sorted(batch_ids)},
        "fan_out": {"measurable": False,
                    "reason": "Stored scrape records carry no link field (keys over every scanned record: "
                              + ", ".join(sorted(notes["scrape_record_keys"])) + "); fan-out within 3 hops cannot "
                              "be computed from stored pages and no web fetching is allowed."},
        "fixed_request_counts": {"J-P1R1": chunks, "H-SPAN": chunks, "H-PQ": chunks, "B1": 2 * batch_chunks},
        "max_est_tokens_per_request": {k: max(v) for k, v in sizes.items() if v and "pairs per" not in k},
        "seg_pair_questions_per_request_min": seg_cap,
        "estimates": est, "warnings": warnings, "pages": per_page,
        "self_check": {"J-P1R1 == chunks": True,
                       "note": "Paid-run self-check: J-P1R1 requests == chunks (+ halvings); H-SPAN == H-PQ == chunks; "
                               "J-P2A1 == H-AQ == activities x chunks."},
        "elapsed_s": round(time.time() - t0, 1)}
    path = OUT_DIR / "SPIKE-T002-dryrun.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("sample", "fixed_request_counts", "max_est_tokens_per_request")},
                     indent=1, ensure_ascii=False, default=str)[:4000])
    for k, v in est.items():
        print(k, "total $", v["total_usd"], v["cost_usd"])
    print("warnings:", warnings[:10])
    print("wrote", path)


def pick_batch_subset(pages) -> set[str]:
    """10 pages for the Batch timing subset: seeded, at least 2 CJK/Thai and 1 long page when available."""
    rng = random.Random(SEED + 1)
    pool = sorted(pages, key=lambda p: p["page_id"])
    nl = [p for p in pool if p["script"] in ("cjk", "thai")]
    lg = [p for p in pool if p["n_chunks"] > 1 and p not in nl]
    rng.shuffle(nl)
    rng.shuffle(lg)
    chosen = nl[:2] + lg[:1]
    rest = [p for p in pool if p not in chosen]
    rng.shuffle(rest)
    chosen += rest[: N_BATCH - len(chosen)]
    return {p["page_id"] for p in chosen}


# =====================================================================================================
# Paid run
# =====================================================================================================

class Log:
    """Append-only JSONL with resume: rows with ok=True and a key are 'done'."""

    def __init__(self, path: Path):
        self.path = path
        self.done: dict[str, dict] = {}
        self.split: dict[str, bool] = {}  # jev keys refused with max_tokens_exceeded (halved on resume)
        self.spent = 0.0
        self.by_leg = Counter()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                self.spent += r.get("cost_usd", 0.0) or 0.0
                if r.get("ok") and r.get("key"):
                    self.done[r["key"]] = r
                if r.get("max_tokens_exceeded") and r.get("key"):
                    self.split[r["key"]] = True
        self.f = path.open("a", encoding="utf-8")

    def write(self, row: dict):
        row.setdefault("ts", now())
        self.f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        self.f.flush()
        if row.get("ok") and row.get("key"):
            self.done[row["key"]] = row


def read_env_key(env_file: Path, name: str) -> str | None:
    """Read one variable from a .env file without echoing it."""
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("export "):
            s = s[7:]
        if s.startswith(name + "="):
            v = s[len(name) + 1:].strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            return v or None
    return None


class Runner:
    def __init__(self, args):
        if not os.environ.get("TYPESAFE_API_KEY"):
            sys.exit("TYPESAFE_API_KEY is not set in this shell. Set $env:TYPESAFE_API_KEY first; "
                     "C:/Users/spaci/repos/G3O/.env does not carry it.")
        akey = read_env_key(Path(args.env_file), "ANTHROPIC_API_KEY")
        if not akey:
            sys.exit(f"ANTHROPIC_API_KEY not found in {args.env_file}.")
        try:
            import anthropic
        except ImportError:
            sys.exit("The `anthropic` package is not installed in this Python environment; install it first "
                     "(it is not in the G3O venv as of 2026-10-30).")
        import typesafe_sdk as ts

        from g3o.common import credentials, jev_client
        self.anthropic, self.ts, self.jc = anthropic, ts, jev_client
        self.aclient = anthropic.Anthropic(api_key=akey, max_retries=4)
        del akey
        self.jclient = jev_client.client_from_credentials(credentials.resolve())
        self.log = Log(OUT_DIR / "SPIKE-T002-answers.jsonl")
        self.budget = C.Budget(cap_usd=args.cap, spent_usd=self.log.spent)
        self.gen = load_generated()
        self.ratelimit_recorded = any(k.startswith("meta|ratelimit") for k in self.log.done)

    # ---- jev ----
    def jev(self, leg, key, page, state, questions, depth=0):
        """One jev request with halve-and-retry on max_tokens_exceeded (<= 3). Returns list of (row) per part."""
        if key in self.log.done:
            return [self.log.done[key]]
        if self.log.split.get(key) and depth < C.MAX_SPLITS:  # resume: this part was already halved
            return self._halves(leg, key, page, state, questions, depth)
        self.budget.reserve(C.jev_upper_bound())
        tsq = {qid: self.ts.Choice(instructions=x["instructions"], criteria=x["criteria"])
               for qid, x in questions.items()}
        sb, qb = C.script_bytes(state.get("page_text", "")), C.script_bytes(
            "\n".join(C.question_text(x) for x in questions.values()))
        base = {"kind": "jev", "leg": leg, "key": key, "page_id": page["page_id"], "part": state.get("page_part"),
                "n_questions": len(questions), "state_bytes": C.utf8_len(C.state_text(state)),
                "page_text_script_bytes": sb, "question_bytes": sum(C.utf8_len(C.question_text(x))
                                                                    for x in questions.values()),
                "question_script_bytes": qb, "est_tokens": C.est_jev_tokens(state, questions)}
        t0 = time.perf_counter()
        try:
            res = self.jc.ask(state, tsq, client=self.jclient)
        except self.jc.JevAccountError:
            self.log.write({**base, "ok": False, "error": "JevAccountError", "latency_s": time.perf_counter() - t0})
            raise
        except Exception as e:  # noqa: BLE001
            lat = time.perf_counter() - t0
            too_long = "max_tokens_exceeded" in repr(e)
            self.log.write({**base, "ok": False, "error": repr(e)[:800], "max_tokens_exceeded": too_long,
                            "latency_s": lat, "split_depth": depth})
            if too_long and depth < C.MAX_SPLITS:
                return self._halves(leg, key, page, state, questions, depth)
            return [{**base, "ok": False}]
        lat = time.perf_counter() - t0
        cost = C.jev_cost(res.input_tokens)
        self.budget.commit(cost, leg)
        row = {**base, "ok": True, "request_id": res.request_id, "response_model": res.response_model,
               "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "cost_usd": cost,
               "latency_s": lat, "split_depth": depth,
               "answers": {k: {"choice": a.choice, "confidence": a.confidence, "probabilities": a.probabilities}
                           for k, a in res.answers.items()}}
        self.log.write(row)
        return [row]

    def _halves(self, leg, key, page, state, questions, depth):
        rows = []
        for j, h in enumerate(C.halve(state["page_text"])):
            st = dict(state, page_text=h, page_part=f"{state['page_part']}.{j + 1}")
            rows += self.jev(leg, f"{key}.{j + 1}", page, st, questions, depth + 1)
        return rows

    # ---- Haiku sync ----
    def haiku(self, leg, key, page, chunk_id, params, extra=None):
        if key in self.log.done:
            return self.log.done[key]
        nbytes = params_bytes(params)
        self.budget.reserve(C.haiku_upper_bound(nbytes, params["max_tokens"]))
        base = {"kind": "haiku", "leg": leg, "key": key, "page_id": page["page_id"], "chunk_id": chunk_id,
                "prompt_bytes": nbytes, "est_tokens_bytes_3_2": math.ceil(nbytes / C.HAIKU_BYTES_PER_TOKEN),
                "model": params["model"], "effort": HAIKU_EFFORT, **(extra or {})}
        t0 = time.perf_counter()
        try:
            raw = self.aclient.messages.with_raw_response.create(**params)
            msg = raw.parse()
        except (self.anthropic.AuthenticationError, self.anthropic.PermissionDeniedError) as e:
            self.log.write({**base, "ok": False, "error": repr(e)[:800], "latency_s": time.perf_counter() - t0})
            raise
        except self.anthropic.APIError as e:
            self.log.write({**base, "ok": False, "error": repr(e)[:800], "latency_s": time.perf_counter() - t0})
            return {**base, "ok": False}
        lat = time.perf_counter() - t0
        if not self.ratelimit_recorded:
            self.log.write({"kind": "meta", "key": "meta|ratelimit", "ok": True,
                            "headers": {k: v for k, v in raw.headers.items() if k.lower().startswith(
                                "anthropic-ratelimit")}})
            self.ratelimit_recorded = True
        u = msg.usage
        cost = C.haiku_cost(u.input_tokens, u.output_tokens)
        self.budget.commit(cost, leg)
        text = next((b.text for b in msg.content if b.type == "text"), "")
        parsed, perr = None, None
        try:
            parsed = json.loads(text)
        except ValueError as e:
            perr = repr(e)[:300]
        ok = msg.stop_reason == "end_turn" and parsed is not None
        row = {**base, "ok": ok, "request_id": raw.headers.get("request-id") or msg._request_id, "message_id": msg.id,
               "stop_reason": msg.stop_reason, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
               "cost_usd": cost, "latency_s": lat, "response_text": text, "parsed": parsed, "parse_error": perr}
        if not ok:
            row["error"] = f"stop_reason={msg.stop_reason}; parse_error={perr}"
        self.log.write(row)
        return row

    def write_quotes(self, src_row, page, chunk_id, level, activity_id=None, batch=False):
        """One answers row per (item code, quote); an item with no quote gets a recorded empty result."""
        if not src_row.get("ok"):
            return
        key0 = src_row["key"]
        if f"{key0}|quotes" in self.log.done:
            return
        got = {it["item"]: it.get("quotes") or [] for it in (src_row["parsed"] or {}).get("items", [])}
        for x in quote_items(self.gen, level):
            qs = got.get(x["question_id"], [])
            for k, qt in enumerate(qs or [None]):
                self.log.write({"kind": "quote", "leg": src_row["leg"], "source_key": key0,
                                "request_id": src_row.get("request_id"), "page_id": page["page_id"],
                                "chunk_id": chunk_id, "activity_id": activity_id, "code": x["question_id"],
                                "column": x["column"], "quote_index": k if qt is not None else None, "quote": qt,
                                "empty_result": qt is None, "item_returned": x["question_id"] in got,
                                "batch": batch})
        self.log.write({"kind": "marker", "key": f"{key0}|quotes", "ok": True})

    # ---- one page ----
    def page(self, p, text, title):
        parts = C.byte_chunks(text, C.chunk_byte_cap())
        n = len(parts)
        pid = p["page_id"]
        cids = [f"{pid}#c{i + 1}of{n}" for i in range(n)]
        # J-P1R1
        r1 = []
        for i, ch in enumerate(parts):
            r1 += self.jev("J-P1R1", f"J-P1R1|{cids[i]}", p, p1_state(p, title, ch, chunk_label(i, n)), Q_P1R1)
        ok1 = [r for r in r1 if r.get("ok")]
        verdict = min((r["answers"]["verdict"]["choice"] for r in ok1),
                      key=lambda c: PQ.VERDICT_ORDER.index(c) if c in PQ.VERDICT_ORDER else 99, default=None)
        form = ok1[0]["answers"]["disclosure_form"]["choice"] if ok1 else None  # X16: first chunk's value
        # J-P1R2
        if form in REGISTER_FORMS:
            for i, ch in enumerate(parts):
                self.jev("J-P1R2", f"J-P1R2|{cids[i]}", p, p1_state(p, title, ch, chunk_label(i, n)), Q_P1R2)
        # H-SPAN + H-PQ (every page)
        spans_by_chunk = {}
        for i, ch in enumerate(parts):
            part = chunk_label(i, n)
            sr = self.haiku("H-SPAN", f"H-SPAN|{cids[i]}", p, cids[i], span_params(self.gen, p, title, ch, part))
            spans_by_chunk[i] = ((sr.get("parsed") or {}).get("spans") or []) if sr.get("ok") else []
            qr = self.haiku("H-PQ", f"H-PQ|{cids[i]}", p, cids[i], quote_params(self.gen, p, title, ch, part, "page"))
            self.write_quotes(qr, p, cids[i], "page")
        genai = verdict in PQ.GENAI_BEARING
        activities = []
        if genai:
            # J-SEG per chunk with >= 2 spans; union-find over same/shared links
            for i, spans in spans_by_chunk.items():
                if not spans:
                    continue
                ids = [f"P{k + 1}" for k in range(len(spans))]
                parent = {x: x for x in ids}

                def find(x, parent=parent):
                    while parent[x] != x:
                        x = parent[x]
                    return x
                if len(spans) >= 2:
                    passages = {ids[k]: s["passage"] for k, s in enumerate(spans)}
                    st = seg_state(p, title, parts[i], chunk_label(i, n), passages)
                    st_tok = math.ceil(C.utf8_len(C.state_text(st)) * C.JEV_TOKENS_PER_BYTE)
                    groups = C.pack_questions(seg_questions(self.gen, passages),
                                              C.JEV_REQUEST_TOKENS - st_tok - 2000)
                    for gi, grp in enumerate(groups):
                        for r in self.jev("J-SEG", f"J-SEG|{cids[i]}|g{gi + 1}of{len(groups)}", p, st, grp):
                            for pair, a in (r.get("answers") or {}).items():
                                if a["choice"] in SAME_LINKS:
                                    x, y = pair.split("~")
                                    parent[find(y)] = find(x)
                roots = defaultdict(list)
                for k, x in enumerate(ids):
                    roots[find(x)].append(k)
                for root, members in roots.items():
                    s0 = spans[members[0]]
                    activities.append({"activity_id": f"{cids[i]}|A{root}", "found_in_chunk": i,
                                       "span_ids": [ids[k] for k in members], "activity_name": s0["activity_name"],
                                       "tool_name": s0["tool_name"],
                                       "passage": " ... ".join(spans[k]["passage"] for k in members)})
        if f"activities|{pid}" not in self.log.done:
            self.log.write({"kind": "activities", "key": f"activities|{pid}", "ok": True, "page_id": pid,
                            "verdict": verdict, "form": form, "genai_bearing": genai, "activities": activities,
                            "spans_per_chunk": {str(i): len(v) for i, v in spans_by_chunk.items()}})
        # pass 2 and activity quotes: every activity x chunk
        for act in activities:
            aid = act["activity_id"]
            evs = []
            for i, ch in enumerate(parts):
                st = p2_state(p, title, ch, chunk_label(i, n), act)
                evs += [r for r in self.jev("J-P2A1", f"J-P2A1|{aid}|{cids[i]}", p, st, Q_P2A1) if r.get("ok")]
            ev = min((r["answers"]["evaluation_documented"]["choice"] for r in evs),
                     key=lambda c: list(PQ.EVAL).index(c) if c in PQ.EVAL else 99, default=None)
            if ev in PQ.EVAL_SET:
                for i, ch in enumerate(parts):
                    st = p2_state(p, title, ch, chunk_label(i, n), act)
                    self.jev("J-P2A3", f"J-P2A3|{aid}|{cids[i]}", p, st, Q_P2A3)
            for i, ch in enumerate(parts):
                qr = self.haiku("H-AQ", f"H-AQ|{aid}|{cids[i]}", p, cids[i],
                                quote_params(self.gen, p, title, ch, chunk_label(i, n), "activity", act),
                                {"activity_id": aid})
                self.write_quotes(qr, p, cids[i], "activity", aid)
        return parts, cids, activities

    # ---- Batch subset ----
    def batch_round(self, rnd, reqs):
        """reqs: list of (key, page, chunk_id, level, activity_id, params). Submits once, polls, records latency."""
        skey = f"batch|{rnd}|submitted"
        ekey = f"batch|{rnd}|ended"
        if ekey in self.log.done or not reqs:
            return
        mapping = {f"{rnd}-{k:04d}": r for k, r in enumerate(reqs)}
        if skey in self.log.done:
            bid = self.log.done[skey]["batch_id"]
            t_sub = self.log.done[skey]["submitted_perf_wall"]
        else:
            bound = sum(C.haiku_upper_bound(params_bytes(r[5]), r[5]["max_tokens"], batch=True) for r in reqs)
            self.budget.reserve(bound)
            t_sub = time.time()
            b = self.aclient.messages.batches.create(
                requests=[{"custom_id": cid, "params": r[5]} for cid, r in mapping.items()])
            bid = b.id
            self.log.write({"kind": "batch", "key": skey, "ok": True, "round": rnd, "batch_id": bid,
                            "n_requests": len(reqs), "submitted_perf_wall": t_sub, "reserved_bound_usd": bound,
                            "custom_ids": {cid: r[0] for cid, r in mapping.items()}})
        polls = 0
        while True:
            b = self.aclient.messages.batches.retrieve(bid)
            polls += 1
            if b.processing_status == "ended":
                break
            time.sleep(15)
        t_end = time.time()
        total = 0.0
        for res in self.aclient.messages.batches.results(bid):
            key, page, chunk_id, level, aid, _ = mapping[res.custom_id]
            row = {"kind": "haiku", "leg": rnd, "key": f"{rnd}|{key}", "page_id": page["page_id"],
                   "chunk_id": chunk_id, "activity_id": aid, "batch_id": bid, "custom_id": res.custom_id,
                   "result_type": res.result.type, "ok": False}
            if res.result.type == "succeeded":
                msg = res.result.message
                text = next((bl.text for bl in msg.content if bl.type == "text"), "")
                cost = C.haiku_cost(msg.usage.input_tokens, msg.usage.output_tokens, batch=True)
                total += cost
                self.budget.commit(cost, rnd)
                try:
                    parsed = json.loads(text)
                except ValueError:
                    parsed = None
                row.update(ok=msg.stop_reason == "end_turn" and parsed is not None, message_id=msg.id,
                           stop_reason=msg.stop_reason, input_tokens=msg.usage.input_tokens,
                           output_tokens=msg.usage.output_tokens, cost_usd=cost, response_text=text, parsed=parsed)
            else:
                row["error"] = repr(getattr(res.result, "error", None))[:800]
            self.log.write(row)
            if level in ("page", "activity") and row["ok"]:
                self.write_quotes(row, page, chunk_id, level, aid, batch=True)
        self.log.write({"kind": "batch", "key": ekey, "ok": True, "round": rnd, "batch_id": bid,
                        "round_trip_s": t_end - t_sub, "polls": polls,
                        "server_created_at": str(b.created_at), "server_ended_at": str(b.ended_at),
                        "request_counts": b.request_counts.to_dict() if hasattr(b.request_counts, "to_dict")
                        else str(b.request_counts), "cost_usd_recorded_in_rows": total})

    def run(self, pages, texts):
        self.log.write({"kind": "meta", "ts": now(), "event": "start", "cap_usd": self.budget.cap_usd,
                        "spent_before_usd": self.budget.spent_usd, "codebook": self.gen["manifest"],
                        "jev_model": self.jc.DEFAULT_JEV_MODEL, "haiku_model": HAIKU_MODEL,
                        "haiku_effort": HAIKU_EFFORT, "quote_item_text": QUOTE_ITEM_TEXT,
                        "page_ids": [p["page_id"] for p in pages]})
        results = {}
        try:
            for p in pages:
                t = texts[p["page_id"]]
                results[p["page_id"]] = self.page(p, t["text"], t["title"])
                print(f"page done {p['page_id']}  spent ${self.budget.spent_usd:.4f}", flush=True)
            bset = pick_batch_subset(pages)
            b1, b2 = [], []
            for p in pages:
                if p["page_id"] not in bset:
                    continue
                t = texts[p["page_id"]]
                parts, cids, acts = results[p["page_id"]]
                n = len(parts)
                for i, ch in enumerate(parts):
                    part = chunk_label(i, n)
                    b1.append((f"H-SPAN|{cids[i]}", p, cids[i], "span", None,
                               span_params(self.gen, p, t["title"], ch, part)))
                    b1.append((f"H-PQ|{cids[i]}", p, cids[i], "page", None,
                               quote_params(self.gen, p, t["title"], ch, part, "page")))
                for act in acts:
                    for i, ch in enumerate(parts):
                        b2.append((f"H-AQ|{act['activity_id']}|{cids[i]}", p, cids[i], "activity", act["activity_id"],
                                   quote_params(self.gen, p, t["title"], ch, chunk_label(i, n), "activity", act)))
            self.batch_round("B1", b1)
            self.batch_round("B2", b2)
        except C.CapReached as e:
            self.log.write({"kind": "meta", "event": "cap_reached", "detail": str(e), "spent_usd": self.budget.spent_usd})
            print("CAP REACHED:", e)
            return
        self.log.write({"kind": "meta", "event": "end", "spent_usd": self.budget.spent_usd,
                        "by_leg_this_session": self.budget.by_leg})
        print(f"done. spent ${self.budget.spent_usd:.4f}")


def paid_run(args):
    runner = Runner(args)  # checks keys and packages before the (slow) corpus pass
    pages, notes = build_sample()
    dr = OUT_DIR / "SPIKE-T002-dryrun.json"
    if dr.exists():
        prev = [p["page_id"] for p in json.loads(dr.read_text(encoding="utf-8"))["pages"]]
        if prev != [p["page_id"] for p in pages]:
            sys.exit("Sample differs from SPIKE-T002-dryrun.json; stopping (re-run --dry-run and review first).")
    texts = load_texts(pages)
    runner.run(pages, texts)


# =====================================================================================================
# Summarize (free)
# =====================================================================================================

def summarize(args):
    rows = [json.loads(x) for x in (OUT_DIR / "SPIKE-T002-answers.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]
    calls = [r for r in rows if r.get("kind") in ("jev", "haiku")]
    legs = defaultdict(list)
    for r in calls:
        legs[r["leg"]].append(r)
    per_leg = {}
    for leg, rs in sorted(legs.items()):
        ok = [r for r in rs if r.get("ok")]
        lat = [r["latency_s"] for r in ok if r.get("latency_s") is not None]
        per_leg[leg] = {"requests": len(rs), "ok": len(ok), "failed": len(rs) - len(ok),
                        "max_tokens_exceeded": sum(bool(r.get("max_tokens_exceeded")) for r in rs),
                        "input_tokens": sum(r.get("input_tokens", 0) for r in ok),
                        "output_tokens": sum(r.get("output_tokens", 0) for r in ok),
                        "cost_usd": round(sum(r.get("cost_usd", 0) or 0 for r in rs), 5),
                        "latency_p50_s": C.percentile(lat, 0.5), "latency_p95_s": C.percentile(lat, 0.95)}
    acts = [r for r in rows if r.get("kind") == "activities"]
    pages = {r["page_id"] for r in calls}
    # estimator fit: jev input tokens vs bytes, by dominant script of the page text in the request
    fit = defaultdict(list)
    for r in calls:
        if r["kind"] == "jev" and r.get("ok") and r.get("input_tokens"):
            sb = r["page_text_script_bytes"]
            script = max(C.SCRIPTS, key=lambda s: sb.get(s, 0))
            total_b = r["state_bytes"] + r["question_bytes"]
            fit[script].append({"tpb": r["input_tokens"] / total_b,
                                "err": (r["est_tokens"] - r["input_tokens"]) / r["input_tokens"]})
    est = {s: {"n": len(v), "tokens_per_byte_median": C.percentile([x["tpb"] for x in v], 0.5),
               "tokens_per_byte_max": max(x["tpb"] for x in v),
               "provisional_0_3947_rel_error_min": min(x["err"] for x in v),
               "provisional_0_3947_rel_error_max": max(x["err"] for x in v)} for s, v in fit.items() if v}
    total = sum(r.get("cost_usd", 0) or 0 for r in rows)
    batches = [r for r in rows if r.get("kind") == "batch" and r.get("key", "").endswith("ended")]
    out = {"generated_at": now(), "pages": len(pages), "per_leg": per_leg, "total_cost_usd": round(total, 4),
           "cost_per_1k_pages_usd": round(total / max(len(pages), 1) * 1000, 2),
           "activities_per_page": dict(Counter(len(a["activities"]) for a in acts)),
           "genai_bearing_pages": sum(a["genai_bearing"] for a in acts),
           "chunks_per_page": dict(Counter(n for _, n in {(r["page_id"], int(r["chunk_id"].rsplit("of", 1)[1]))
                                                          for r in calls if r.get("leg") == "H-SPAN"})),
           "estimator_by_script": est,
           "batch_rounds": [{k: b.get(k) for k in ("round", "round_trip_s", "request_counts")} for b in batches],
           "quote_rows": sum(r.get("kind") == "quote" and not r.get("empty_result") for r in rows),
           "empty_quote_results": sum(r.get("kind") == "quote" and bool(r.get("empty_result")) for r in rows),
           "ratelimit_headers": next((r["headers"] for r in rows if r.get("key") == "meta|ratelimit"), None)}
    (OUT_DIR / "SPIKE-T002-summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["dry-run", "run", "summarize"])
    ap.add_argument("--env-file", default="C:/Users/spaci/repos/G3O/.env")
    ap.add_argument("--cap", type=float, default=CAP_USD)
    args = ap.parse_args(argv)
    if args.cap > CAP_USD:
        sys.exit(f"--cap above the PI cap ${CAP_USD:.2f} is not allowed.")
    {"dry-run": dry_run, "run": paid_run, "summarize": summarize}[args.mode](args)


if __name__ == "__main__":
    main()
