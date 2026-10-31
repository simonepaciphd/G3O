"""T-002 spike: offline agreement check between the Haiku legs and the jev legs (free; no network).

PI ruling 3 b (2026-10-31): decide on the Haiku legs after an offline agreement check. This script gives the
evidence only. It reads SPIKE-T002-answers.jsonl, SPIKE-T002-summary.json and SPIKE-T002-dryrun.json (all
read-only) and writes SPIKE-T002-agreement.json and SPIKE-T002-agreement.md next to them.

The Haiku legs and the jev legs do not ask the same questions. jev returns a choice per proxy question;
Haiku returns spans (H-SPAN) or verbatim quotes per v2.7 item (H-PQ, H-AQ), never a value. Every comparison
below is therefore between a jev choice and a Haiku *presence* signal (at least one span, or at least one
non-empty quote for the item). A quote is "what a coder needs to answer the item", which can support a "no"
as well as a "yes", so quote presence is a proxy, not an answer.

Usage: python -I agreement_t002.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import proxy_questions as PQ  # noqa: E402

SPIKES = Path("H:/My Drive/Research/G3O/agent-workspace/2026-10-27-reclass-plan/spikes")
ANSWERS = SPIKES / "SPIKE-T002-answers.jsonl"
SUMMARY = SPIKES / "SPIKE-T002-summary.json"
DRYRUN = SPIKES / "SPIKE-T002-dryrun.json"
OUT_JSON = SPIKES / "SPIKE-T002-agreement.json"
OUT_MD = SPIKES / "SPIKE-T002-agreement.md"

HAIKU_LEGS = ("H-PQ", "H-SPAN", "H-AQ", "B1", "B2")
JEV_LEGS = ("J-P1R1", "J-P1R2", "J-SEG", "J-P2A1", "J-P2A3")

# Activity level: jev J-P2A1 question -> v2.7 pass-2 item quoted by H-AQ, with how close the two concepts are.
# "direct" = same concept in both; "proxy" = related concept, different construct. Engineer's mapping.
P2_MAP = [
    ("evaluation_documented", "core.evaluation_documented", "direct"),
    ("content_human_oversight", "core.has_human_oversight", "direct"),
    ("content_risk_assessment", "core.has_risk_assessment", "direct"),
    ("content_user_notification", "core.has_transparency_notice", "direct"),
    ("content_users", "core.target_users", "proxy"),
    ("content_tool_or_model", "core.genai_mechanism_basis", "proxy"),
    ("content_vendor", "core.procurement_status", "proxy"),
    ("content_status_date", "core.adoption_stage", "proxy"),
    ("content_data", "core.has_data_classification", "proxy"),
]
# Activity-level jev question -> page-level item quoted by H-PQ (same page, any chunk).
P2_PAGE_MAP = [
    ("content_data", "core.content_data", "direct"),
    ("content_contact", "core.content_contact_details", "direct"),
    ("content_contact", "core.content_contact_named", "proxy"),
]
EXCERPT = 180


def load():
    rows = [json.loads(x) for x in ANSWERS.read_text(encoding="utf-8").splitlines() if x.strip()]
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    dry = json.loads(DRYRUN.read_text(encoding="utf-8"))
    return rows, summary, dry


# ---------------------------------------------------------------- statistics

def two_by_two(a: list[bool], b: list[bool]) -> dict:
    """Agreement of two binary raters on the same units: counts, raw agreement, Cohen's kappa, PABAK."""
    n = len(a)
    tt = sum(x and y for x, y in zip(a, b, strict=True))
    tf = sum(x and not y for x, y in zip(a, b, strict=True))
    ft = sum(y and not x for x, y in zip(a, b, strict=True))
    ff = n - tt - tf - ft
    po = (tt + ff) / n if n else None
    pa, pb = (tt + tf) / n if n else 0, (tt + ft) / n if n else 0
    pe = pa * pb + (1 - pa) * (1 - pb)
    kappa = None if not n or pe >= 1 else (po - pe) / (1 - pe)
    return {"n": n, "both_yes": tt, "a_only": tf, "b_only": ft, "both_no": ff,
            "a_yes": tt + tf, "b_yes": tt + ft, "raw_agreement": po, "cohen_kappa": kappa,
            "pabak": None if po is None else 2 * po - 1}


def fmt(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def short(pid: str) -> str:
    """Page id without the corpus/run prefix: INST-xxxxxxx:hash8."""
    parts = pid.split(":")
    return f"{parts[-2]}:{parts[-1][:8]}"


def excerpt(s: str | None) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= EXCERPT else s[:EXCERPT] + "..."


# ---------------------------------------------------------------- indexes

def index(rows):
    calls = [r for r in rows if r.get("kind") in ("jev", "haiku")]
    by_key = {r["key"]: r for r in calls if r.get("key")}
    acts = {r["page_id"]: r for r in rows if r.get("kind") == "activities"}
    quotes = [r for r in rows if r.get("kind") == "quote"]
    # (leg, source_key, code) -> list of non-empty quotes; item_returned flag per (leg, source_key, code)
    qmap, returned = defaultdict(list), {}
    for r in quotes:
        k = (r["leg"], r["source_key"], r["code"])
        returned[k] = r["item_returned"]
        if not r["empty_result"]:
            qmap[k].append(r["quote"])
        else:
            qmap.setdefault(k, [])
    return calls, by_key, acts, quotes, qmap, returned


def page_level(rows, calls, acts, qmap, dry):
    """One record per page: jev verdict (combined), jev max P(GenAI-bearing), Haiku spans, verdict quotes."""
    v25 = {p["page_id"]: p.get("v25_genai_evidence") for p in dry["pages"]}
    script = {p["page_id"]: p["script"] for p in dry["pages"]}
    out = {}
    for pid, a in acts.items():
        j1 = [r for r in calls if r["leg"] == "J-P1R1" and r["page_id"] == pid and r.get("ok")]
        pmax = max((sum(r["answers"]["verdict"]["probabilities"].get(c, 0) for c in PQ.GENAI_BEARING)
                    for r in j1), default=None)
        spans = [r for r in calls if r["leg"] == "H-SPAN" and r["page_id"] == pid]
        n_spans = sum(len((r.get("parsed") or {}).get("spans") or []) for r in spans if r.get("ok"))
        first_span = next((s["passage"] for r in spans if r.get("ok")
                           for s in (r.get("parsed") or {}).get("spans") or []), None)
        pq = [r for r in calls if r["leg"] == "H-PQ" and r["page_id"] == pid]
        vq = [q for r in pq for q in qmap.get(("H-PQ", r["key"], "core.page_verdict"), [])]
        pub = [((r.get("parsed") or {}).get("source_publication_date") or {}) for r in spans if r.get("ok")]
        out[pid] = {
            "page": short(pid), "script": script.get(pid), "n_chunks": len(spans),
            "jev_verdict": a["verdict"], "jev_form": a["form"], "jev_genai_bearing": a["genai_bearing"],
            "jev_confirms": a["verdict"] == "confirms_activity", "jev_max_p_genai_bearing": pmax,
            "haiku_spans": n_spans, "haiku_any_span": n_spans > 0, "haiku_first_span": excerpt(first_span),
            "haiku_verdict_quotes": len(vq), "haiku_any_verdict_quote": bool(vq),
            "haiku_first_verdict_quote": excerpt(vq[0] if vq else None),
            "haiku_pub_date": next((d.get("date") for d in pub if d.get("date")), ""),
            "activities": len(a["activities"]), "v25_genai_evidence": v25.get(pid)}
    return out


# ---------------------------------------------------------------- analyses

def page_genai_agreement(pages):
    ids = sorted(pages)
    sig = {
        "jev_genai_bearing": [pages[p]["jev_genai_bearing"] for p in ids],
        "jev_confirms_activity": [pages[p]["jev_confirms"] for p in ids],
        "hspan_any_span": [pages[p]["haiku_any_span"] for p in ids],
        "hpq_any_verdict_quote": [pages[p]["haiku_any_verdict_quote"] for p in ids],
    }
    pairs = [("jev_genai_bearing", "hspan_any_span"), ("jev_genai_bearing", "hpq_any_verdict_quote"),
             ("jev_confirms_activity", "hspan_any_span"), ("hspan_any_span", "hpq_any_verdict_quote")]
    res = []
    for a, b in pairs:
        t = two_by_two(sig[a], sig[b])
        dis_a = [pages[p]["page"] for p, x, y in zip(ids, sig[a], sig[b], strict=True) if x and not y]
        dis_b = [pages[p]["page"] for p, x, y in zip(ids, sig[a], sig[b], strict=True) if y and not x]
        res.append({"a": a, "b": b, **t, "a_only_pages": dis_a, "b_only_pages": dis_b})
    # v2.5 extract label as a third, older reference (pages that have one)
    with_v25 = [p for p in ids if pages[p]["v25_genai_evidence"]]
    v25_pos = [any(v in ("confirms_activity", "ambiguous") for v in pages[p]["v25_genai_evidence"])
               for p in with_v25]
    v25 = []
    for k in sig:
        sub = [sig[k][ids.index(p)] for p in with_v25]
        v25.append({"a": "v25_activity_or_ambiguous", "b": k, **two_by_two(v25_pos, sub)})
    by_verdict = defaultdict(lambda: Counter())
    for p in ids:
        r = pages[p]
        c = by_verdict[r["jev_verdict"]]
        c["pages"] += 1
        c["with_span"] += r["haiku_any_span"]
        c["with_verdict_quote"] += r["haiku_any_verdict_quote"]
    disagreements = [pages[p] for p in ids
                     if len({pages[p]["jev_genai_bearing"], pages[p]["haiku_any_span"],
                             pages[p]["haiku_any_verdict_quote"]}) > 1]
    return {"pairs": res, "v25_reference": {"n_pages_with_label": len(with_v25), "pairs": v25},
            "by_jev_verdict": {k: dict(v) for k, v in sorted(by_verdict.items())},
            "disagreement_pages": disagreements}


def form_scope_descriptive(pages, calls, qmap):
    """jev disclosure_form value x whether H-PQ quoted anything for core.disclosure_form (descriptive only)."""
    tab = defaultdict(Counter)
    scope_quotes = 0
    for pid, r in pages.items():
        pq = [c for c in calls if c["leg"] == "H-PQ" and c["page_id"] == pid]
        has = any(qmap.get(("H-PQ", c["key"], "core.disclosure_form")) for c in pq)
        scope_quotes += sum(len(qmap.get(("H-PQ", c["key"], "core.disclosure_scope"), [])) for c in pq)
        tab[r["jev_form"]]["quoted" if has else "not_quoted"] += 1
    p1r2 = [c for c in calls if c["leg"] == "J-P1R2" and c.get("ok")]
    return {"form_by_quote_presence": {k: dict(v) for k, v in sorted(tab.items())},
            "hpq_disclosure_scope_nonempty_quotes_all_pages": scope_quotes,
            "jev_p1r2_answers": [{"page": short(c["page_id"]),
                                  "disclosure_scope": c["answers"]["disclosure_scope"]["choice"]} for c in p1r2]}


def activity_agreement(rows, calls, by_key, acts, qmap, returned):
    """J-P2A1 / J-P2A3 choices vs H-AQ (and page-level H-PQ) quote presence, per activity."""
    activities = [(pid, a) for pid, r in acts.items() for a in r["activities"]]
    recs = []
    for pid, a in activities:
        aid = a["activity_id"]
        j = [c for c in calls if c["leg"] == "J-P2A1" and c.get("ok") and c["key"].startswith(f"J-P2A1|{aid}|")]
        j3 = [c for c in calls if c["leg"] == "J-P2A3" and c.get("ok") and c["key"].startswith(f"J-P2A3|{aid}|")]
        haq = [c for c in calls if c["leg"] == "H-AQ" and c.get("activity_id") == aid]
        hpq = [c for c in calls if c["leg"] == "H-PQ" and c["page_id"] == pid]
        ans = {k: v["choice"] for c in j for k, v in c["answers"].items()}
        ans3 = {k: v["choice"] for c in j3 for k, v in c["answers"].items()}
        aq = defaultdict(list)
        ret = {}
        for c in haq:
            for (leg, sk, code), qs in qmap.items():
                if leg == "H-AQ" and sk == c["key"]:
                    aq[code] += qs
                    ret[code] = ret.get(code, False) or returned[(leg, sk, code)]
        pq = defaultdict(list)
        for c in hpq:
            for (leg, sk, code), qs in qmap.items():
                if leg == "H-PQ" and sk == c["key"]:
                    pq[code] += qs
        recs.append({"activity_id": aid, "page": short(pid), "activity_name": a["activity_name"],
                     "jev": ans, "jev_eval_types": ans3, "haq_quotes": dict(aq), "haq_returned": ret,
                     "hpq_quotes": dict(pq)})
    pos = {"yes", "results_reported", "conducted_no_results", "required_or_planned", "unclear"}
    table = []
    for jq, item, strength, src in ([(*m, "H-AQ") for m in P2_MAP] + [(*m, "H-PQ") for m in P2_PAGE_MAP]):
        a_, b_, cells = [], [], []
        for r in recs:
            if jq not in r["jev"]:
                continue
            jyes = r["jev"][jq] in pos
            hq = (r["haq_quotes"] if src == "H-AQ" else r["hpq_quotes"]).get(item, [])
            a_.append(jyes)
            b_.append(bool(hq))
            cells.append({"activity": r["activity_id"].rsplit("|", 1)[1], "page": r["page"],
                          "jev": r["jev"][jq], "haiku_quotes": len(hq)})
        table.append({"jev_question": jq, "haiku_item": item, "haiku_leg": src, "strength": strength,
                      **two_by_two(a_, b_), "cells": cells})
    # J-P2A3 eval types vs H-AQ eval-type quotes (only activities that reached round 3)
    et = []
    for r in recs:
        for k, v in r["jev_eval_types"].items():
            et.append({"activity": r["activity_id"].rsplit("|", 1)[1], "page": r["page"], "question": k,
                       "jev": v, "haiku_quotes": len(r["haq_quotes"].get(f"core.{k}", []))})
    # Items Haiku left out of its answer (schema did not force every item)
    haq_cells = [(r["activity_id"], code, ok) for r in recs for code, ok in r["haq_returned"].items()]
    items_total = len(haq_cells)
    not_returned = sum(not ok for *_, ok in haq_cells)
    nonempty = sum(bool(q) for r in recs for q in r["haq_quotes"].values())
    return {"n_activities": len(recs), "n_pages": len({r["page"] for r in recs}),
            "activities": [{"activity_id": r["activity_id"], "page": r["page"], "activity_name": r["activity_name"],
                            "jev_p2a1": r["jev"]} for r in recs],
            "pairs": table, "eval_types": et,
            "haq_item_cells": items_total, "haq_items_with_quote": nonempty,
            "haq_items_not_returned_by_haiku": not_returned,
            "j_seg": [{"page": short(c["page_id"]), "answers": {k: v["choice"] for k, v in c["answers"].items()}}
                      for c in calls if c["leg"] == "J-SEG" and c.get("ok")]}


def batch_consistency(calls, by_key, qmap):
    """B1/B2 send the same params as their sync counterparts; compare outputs (run-to-run consistency)."""
    out = {}
    for rnd in ("B1", "B2"):
        brs = [c for c in calls if c["leg"] == rnd and c.get("ok")]
        span_cmp, item_a, item_b, jacc, item_rows = [], [], [], [], []
        b_cost, s_cost_same_req, s_cost_at_batch = 0.0, 0.0, 0.0
        for b in brs:
            skey = b["key"][len(rnd) + 1:]
            s = by_key.get(skey)
            if not s or not s.get("ok"):
                continue
            b_cost += b.get("cost_usd") or 0
            s_cost_same_req += s.get("cost_usd") or 0
            s_cost_at_batch += ((s["input_tokens"] * 0.05 + s["output_tokens"] * 0.25) / 1e6)
            if skey.startswith("H-SPAN|"):
                bs = (b.get("parsed") or {}).get("spans") or []
                ss = (s.get("parsed") or {}).get("spans") or []
                bp = {" ".join(x["passage"].split()) for x in bs}
                sp = {" ".join(x["passage"].split()) for x in ss}
                bd = ((b.get("parsed") or {}).get("source_publication_date") or {}).get("date", "")
                sd = ((s.get("parsed") or {}).get("source_publication_date") or {}).get("date", "")
                span_cmp.append({"chunk": short(s["page_id"]) + "#" + s["chunk_id"].rsplit("#", 1)[1],
                                 "sync_spans": len(ss), "batch_spans": len(bs),
                                 "passages_exact_overlap": len(bp & sp), "pub_date_sync": sd, "pub_date_batch": bd,
                                 "pub_date_equal": sd == bd})
            else:
                codes = sorted({code for (leg, sk, code) in qmap if leg == s["leg"] and sk == skey})
                for code in codes:
                    sq = {" ".join(q.split()) for q in qmap.get((s["leg"], skey, code), [])}
                    bq = {" ".join(q.split()) for q in qmap.get((rnd, b["key"], code), [])}
                    item_a.append(bool(sq))
                    item_b.append(bool(bq))
                    if sq or bq:
                        jacc.append(len(sq & bq) / len(sq | bq))
                    item_rows.append({"chunk": short(s["page_id"]), "item": code, "sync": len(sq),
                                      "batch": len(bq), "exact_shared": len(sq & bq)})
        out[rnd] = {
            "requests_compared": len(brs),
            "span_chunks": span_cmp,
            "span_count_equal": sum(x["sync_spans"] == x["batch_spans"] for x in span_cmp),
            "span_any_equal": sum((x["sync_spans"] > 0) == (x["batch_spans"] > 0) for x in span_cmp),
            "pub_date_equal": sum(x["pub_date_equal"] for x in span_cmp),
            "quote_presence": two_by_two(item_a, item_b) if item_a else None,
            "quote_exact_jaccard_mean": sum(jacc) / len(jacc) if jacc else None,
            "quote_items_with_any_quote": len(jacc),
            "quote_items_identical_sets": sum(j == 1.0 for j in jacc),
            "quote_disagreements": [r for r in item_rows if (r["sync"] > 0) != (r["batch"] > 0)],
            "cost_batch_usd": b_cost, "cost_sync_same_requests_usd": s_cost_same_req,
            "cost_sync_tokens_at_batch_price_usd": s_cost_at_batch}
    return out


def costs(summary, rows, pages, quotes):
    n = summary["pages"]
    total = summary["total_cost_usd"]
    per = summary["per_leg"]
    spans = sum(p["haiku_spans"] for p in pages.values())
    nonempty = Counter(q["leg"] for q in quotes if not q["empty_result"])
    items = Counter()
    for q in quotes:
        items[(q["leg"], q["source_key"], q["code"])] += 0
    item_cells = Counter(k[0] for k in items)
    pub = sum(bool(p["haiku_pub_date"]) for p in pages.values())
    legs = {}
    for leg, v in per.items():
        c = v["cost_usd"]
        legs[leg] = {"requests": v["requests"], "input_tokens": v["input_tokens"], "output_tokens": v["output_tokens"],
                     "cost_usd": c, "share_of_total": c / total, "cost_per_1k_pages_usd": c / n * 1000,
                     "cost_per_request_usd": c / v["requests"] if v["requests"] else None,
                     "is_haiku": leg in HAIKU_LEGS}
        if leg in ("H-PQ", "H-AQ", "B1", "B2"):
            legs[leg]["item_cells"] = item_cells.get(leg, 0)
            legs[leg]["nonempty_quotes"] = nonempty.get(leg, 0)
            legs[leg]["cost_per_nonempty_quote_usd"] = c / nonempty[leg] if nonempty.get(leg) else None
    legs["H-SPAN"]["spans_returned"] = spans
    legs["H-SPAN"]["pages_with_span"] = sum(p["haiku_any_span"] for p in pages.values())
    legs["H-SPAN"]["pages_with_pub_date"] = pub
    legs["H-SPAN"]["cost_per_span_usd"] = per["H-SPAN"]["cost_usd"] / spans if spans else None
    haiku = sum(per[k]["cost_usd"] for k in per if k in HAIKU_LEGS)
    jev = sum(per[k]["cost_usd"] for k in per if k in JEV_LEGS)
    # H-SPAN + H-PQ at batch prices, from their measured sync tokens (Batch price is 50% of sync on both)
    sync_fixed = per["H-SPAN"]["cost_usd"] + per["H-PQ"]["cost_usd"]
    return {"pages": n, "total_usd": total, "haiku_usd": haiku, "jev_usd": jev, "haiku_share": haiku / total,
            "per_leg": legs,
            "note_scaling": "H-SPAN and H-PQ run on every chunk (63 chunks / 50 pages), so their per-1k-page cost "
                            "scales with chunks per page. H-AQ, J-SEG, J-P2A1 and J-P2A3 scale with activities "
                            "(6 here, on 3 pages); their per-1k-page figure holds only at this sample's activity "
                            "rate. B1/B2 duplicate H-SPAN/H-PQ/H-AQ requests on the 10-page subset; they buy "
                            "timing and consistency evidence, not new coding information.",
            "h_span_plus_h_pq_at_batch_price_usd": sync_fixed * 0.5,
            "h_span_plus_h_pq_at_batch_price_per_1k_pages_usd": sync_fixed * 0.5 / n * 1000}


LEG_MAP = [
    {"leg": "J-P1R1", "engine": "jev", "unit": "page x chunk (all)",
     "asks": "proxy verdict (unclear2) + proxy disclosure_form (pilot.py); one choice each",
     "comparable_to": "H-SPAN (any span) and H-PQ (core.page_verdict quotes) on page-level GenAI presence; "
                      "H-PQ core.disclosure_form quotes (presence only, descriptive)"},
    {"leg": "J-P1R2", "engine": "jev", "unit": "chunks of register/mandated_report pages (1 here)",
     "asks": "proxy disclosure_scope", "comparable_to": "H-PQ core.disclosure_scope quotes (presence only)"},
    {"leg": "H-SPAN", "engine": "Haiku sync", "unit": "page x chunk (all)",
     "asks": "every GenAI-activity passage + 9 extractor fields (activity_name, actor, unit, tool, model, "
             "contracting party, scale, outcomes, incidents) + publication date with quote",
     "comparable_to": "J-P1R1 verdict on presence only. No jev leg produces passages, field strings or dates.",
     "unique": "The spans are the only source of activities: J-SEG, J-P2A1, J-P2A3 and H-AQ all run on "
               "activities built from H-SPAN passages. Without it, pass 2 has no activity to condition on."},
    {"leg": "H-PQ", "engine": "Haiku sync", "unit": "page x chunk (all)",
     "asks": "verbatim quotes for the 8 v2.7 pass-1 items (no values)",
     "comparable_to": "J-P1R1 (verdict, form) and J-P2A1 content_data / content_contact via presence only",
     "unique": "Quotes for items jev was not asked in the spike (page_complete, source_type, content_contact_named, "
               "content_contact_details, content_data at page level). jev answers but does not quote."},
    {"leg": "J-SEG", "engine": "jev", "unit": "chunks with >= 2 spans on GenAI-bearing pages (1 here)",
     "asks": "pairwise activity relation over H-SPAN passages", "comparable_to": "none (consumes H-SPAN output)"},
    {"leg": "J-P2A1", "engine": "jev", "unit": "activity x chunk (6)",
     "asks": "proxy evaluation_documented + 10 proxy content yes/no",
     "comparable_to": "H-AQ quotes on mapped v2.7 pass-2 items; H-PQ quotes on content_data / contact"},
    {"leg": "J-P2A3", "engine": "jev", "unit": "activities with evaluation in EVAL_SET (1 here)",
     "asks": "6 proxy evaluation types", "comparable_to": "H-AQ core.evaluation_type_* quotes"},
    {"leg": "H-AQ", "engine": "Haiku sync", "unit": "activity x chunk (6)",
     "asks": "verbatim quotes for all 42 v2.7 pass-2 items, including items the applicability table would skip",
     "comparable_to": "J-P2A1 / J-P2A3 on mapped items (presence only)",
     "unique": "Quotes for 27 of the 42 pass-2 items that have no jev counterpart in the spike even by proxy "
               "(activity_type, action_type, functions, governance_*, years, model_origin, ...); 32 have no "
               "direct counterpart."},
    {"leg": "B1", "engine": "Haiku Batch", "unit": "10-page subset (14 chunks x 2)",
     "asks": "identical params to H-SPAN + H-PQ", "comparable_to": "H-SPAN, H-PQ (same prompts: consistency)",
     "unique": "Batch round-trip time and run-to-run consistency only; no new coding information."},
    {"leg": "B2", "engine": "Haiku Batch", "unit": "activities on the subset (1)",
     "asks": "identical params to H-AQ", "comparable_to": "H-AQ (same prompt: consistency)",
     "unique": "As B1."},
]


# ---------------------------------------------------------------- markdown

def md_pair_table(pairs, label_a="A", label_b="B"):
    lines = ["| A | B | n | A yes | B yes | both yes | A only | B only | both no | raw agree | kappa | PABAK |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in pairs:
        lines.append(f"| {p['a']} | {p['b']} | {p['n']} | {p['a_yes']} | {p['b_yes']} | {p['both_yes']} | "
                     f"{p['a_only']} | {p['b_only']} | {p['both_no']} | {fmt(p['raw_agreement'])} | "
                     f"{fmt(p['cohen_kappa'])} | {fmt(p['pabak'])} |")
    return lines


def render_md(res) -> str:
    c, pg, act, bt, fs = res["costs"], res["page_genai"], res["activity"], res["batch"], res["form_scope"]
    L = ["# SPIKE-T002: Haiku vs jev agreement (offline)", "",
         f"Generated {res['generated_by']['at']} by `scripts/spikes/t002/agreement_t002.py` (worktree "
         "`G3O-eng-c`, uncommitted), from `SPIKE-T002-answers.jsonl`, `SPIKE-T002-summary.json` and "
         "`SPIKE-T002-dryrun.json`. Free and offline: no API call. Evidence for PI ruling 3 b; it makes no "
         "recommendation on keeping or dropping any leg.", "",
         "## Read this first", "",
         "- **The legs do not answer the same questions.** jev returns a choice per proxy question (unclear2 "
         "verdict, pilot.py CX questions). Haiku returns passages (H-SPAN) or verbatim quotes per v2.7 item "
         "(H-PQ, H-AQ) and never a value. Every comparison is a jev choice against a Haiku *presence* signal "
         "(at least one span, or at least one quote for the item). A quote can support a `no` as well as a "
         "`yes`, so quote presence is a proxy, not an answer, and disagreement is not error by either side.",
         "- **Sample sizes are small.** 50 pages (63 chunks); 11 GenAI-bearing by jev; 3 pages with "
         "activities (6 activities); 1 activity reached J-P2A3; Batch covers 10 pages and 1 activity. Kappa on "
         "n = 6 is not meaningful and is shown only for completeness. No result here generalises with "
         "confidence.",
         "- **No gold standard.** Neither engine is ground truth; the v2.5 extract label is shown as a third, "
         "older reference on the 17 pages that have one.",
         "- The jev-to-v2.7 item mappings at activity level are the engineer's (marked direct / proxy); the "
         "proxy questions are not the v2.7 items.", "",
         "## 1. Which legs are comparable", "",
         "| Leg | Engine | Unit | Asks | Comparable to | What only it provides |", "|---|---|---|---|---|---|"]
    for m in LEG_MAP:
        L.append(f"| {m['leg']} | {m['engine']} | {m['unit']} | {m['asks']} | {m['comparable_to']} | "
                 f"{m.get('unique', '')} |")
    L += ["", "## 2. Page-level GenAI presence (n = 50 pages)", "",
          "Signals: `jev_genai_bearing` = combined J-P1R1 verdict in {confirms_activity, ambiguous_genai, "
          "ambiguous_attribution, other_body, event_only} (the gate the run used for pass 2); "
          "`jev_confirms_activity` = verdict is confirms_activity; `hspan_any_span` = H-SPAN returned at least one "
          "passage on any chunk; `hpq_any_verdict_quote` = H-PQ returned at least one quote for "
          "`core.page_verdict` on any chunk. A = first signal, B = second.", ""]
    L += md_pair_table(pg["pairs"])
    L += ["", "Pages where only one side is positive:", ""]
    for p in pg["pairs"]:
        L.append(f"- {p['a']} yes, {p['b']} no ({p['a_only']}): {', '.join(p['a_only_pages']) or 'none'}")
        L.append(f"- {p['b']} yes, {p['a']} no ({p['b_only']}): {', '.join(p['b_only_pages']) or 'none'}")
    L += ["", "By jev verdict (pages, of which with an H-SPAN span, of which with an H-PQ verdict quote):", "",
          "| jev verdict | pages | with span | with verdict quote |", "|---|---|---|---|"]
    for k, v in pg["by_jev_verdict"].items():
        L.append(f"| {k} | {v.get('pages', 0)} | {v.get('with_span', 0)} | {v.get('with_verdict_quote', 0)} |")
    L += ["", "### Disagreement pages (the three signals not unanimous)", "",
          "| page | script | jev verdict | jev max P(GenAI-bearing) | spans | verdict quotes | v2.5 label | "
          "first verdict quote (excerpt) |", "|---|---|---|---|---|---|---|---|"]
    for r in pg["disagreement_pages"]:
        v25 = ",".join(r["v25_genai_evidence"] or ["-"])
        q = (r["haiku_first_verdict_quote"] or r["haiku_first_span"] or "").replace("|", "/")
        L.append(f"| {r['page']} | {r['script']} | {r['jev_verdict']} | {fmt(r['jev_max_p_genai_bearing'])} | "
                 f"{r['haiku_spans']} | {r['haiku_verdict_quotes']} | {v25} | {q} |")
    L += ["", f"### v2.5 extract label as reference ({pg['v25_reference']['n_pages_with_label']} pages with a "
          "label; positive = `confirms_activity` or `ambiguous`)", ""]
    L += md_pair_table(pg["v25_reference"]["pairs"])
    L += ["", "### Form and scope (descriptive; no kappa: Haiku gives no value)", "",
          "| jev disclosure_form | H-PQ quoted core.disclosure_form | not quoted |", "|---|---|---|"]
    for k, v in fs["form_by_quote_presence"].items():
        L.append(f"| {k} | {v.get('quoted', 0)} | {v.get('not_quoted', 0)} |")
    L += ["", f"H-PQ returned {fs['hpq_disclosure_scope_nonempty_quotes_all_pages']} non-empty quotes for "
          f"`core.disclosure_scope` across all 63 chunks. J-P1R2 ran on "
          f"{len(fs['jev_p1r2_answers'])} page(s): {fs['jev_p1r2_answers']}.", "",
          f"## 3. Activity level (n = {act['n_activities']} activities on {act['n_pages']} pages)", "",
          "jev positive = `yes` (content questions) or any value other than `not_documented` "
          "(evaluation_documented). Haiku positive = at least one quote for the mapped item (H-AQ for the "
          "activity; H-PQ for page-level items, any chunk of the page). Every activity here is on a "
          "one-chunk page.", "",
          "| jev question | Haiku item | leg | mapping | n | jev yes | Haiku quoted | both yes | jev only | "
          "Haiku only | both no | raw agree |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in act["pairs"]:
        L.append(f"| {p['jev_question']} | {p['haiku_item']} | {p['haiku_leg']} | {p['strength']} | {p['n']} | "
                 f"{p['a_yes']} | {p['b_yes']} | {p['both_yes']} | {p['a_only']} | {p['b_only']} | "
                 f"{p['both_no']} | {fmt(p['raw_agreement'])} |")
    L += ["", "Activities:", ""]
    for a in act["activities"]:
        L.append(f"- {a['page']} {a['activity_id'].rsplit('|', 1)[1]}: {a['activity_name'] or '(no name)'}")
    L += ["", "J-P2A3 (evaluation types, 1 activity) vs H-AQ quotes: "
          + "; ".join(f"{e['question'].replace('evaluation_type_', '')} jev={e['jev']} quotes={e['haiku_quotes']}"
                      for e in act["eval_types"]), "",
          f"H-AQ coverage: {act['haq_item_cells']} activity x item cells; {act['haq_items_with_quote']} with at "
          f"least one quote; {act['haq_items_not_returned_by_haiku']} items Haiku left out of its answer (the "
          "schema does not force every item; recorded as empty).", "",
          f"J-SEG: {act['j_seg']}. No link was `same_activity` or `shared_participation`, so the 4 spans on that "
          "page stayed 4 activities.", "",
          "## 4. Batch vs sync consistency (same params, different calls)", ""]
    for rnd, b in bt.items():
        L.append(f"### {rnd} ({b['requests_compared']} requests)")
        L.append("")
        if b["span_chunks"]:
            n = len(b["span_chunks"])
            L.append(f"- H-SPAN chunks: span count identical {b['span_count_equal']}/{n}; any-span identical "
                     f"{b['span_any_equal']}/{n}; publication date string identical {b['pub_date_equal']}/{n} "
                     "(compare the listed pairs: a differing string can be the same date in another format).")
            for s in b["span_chunks"]:
                if s["sync_spans"] or s["batch_spans"] or not s["pub_date_equal"]:
                    L.append(f"  - {s['chunk']}: spans sync {s['sync_spans']} / batch {s['batch_spans']} "
                             f"(exact passage overlap {s['passages_exact_overlap']}); date '{s['pub_date_sync']}'"
                             f" / '{s['pub_date_batch']}'")
        qp = b["quote_presence"]
        if qp:
            L.append(f"- Quote presence per item (A = sync, B = batch): n {qp['n']}, raw agreement "
                     f"{fmt(qp['raw_agreement'])}, kappa {fmt(qp['cohen_kappa'])}; sync-only {qp['a_only']}, "
                     f"batch-only {qp['b_only']}.")
            L.append(f"- Of {b['quote_items_with_any_quote']} items quoted by either call, "
                     f"{b['quote_items_identical_sets']} have identical quote sets (whitespace-normalised); mean "
                     f"exact Jaccard {fmt(b['quote_exact_jaccard_mean'])} (exact string match after whitespace "
                     "normalisation; a re-cut of the same passage counts as different).")
            if b["quote_disagreements"]:
                L.append("- Presence disagreements: " + "; ".join(
                    f"{d['chunk']} {d['item']} (sync {d['sync']}, batch {d['batch']})"
                    for d in b["quote_disagreements"]))
        L.append(f"- Cost: batch ${b['cost_batch_usd']:.4f}; the same requests sync ${b['cost_sync_same_requests_usd']:.4f}"
                 f"; sync tokens at batch price ${b['cost_sync_tokens_at_batch_price_usd']:.4f}.")
        L.append("")
    L += ["## 5. Cost per leg and what it returns", "",
          f"Total ${c['total_usd']:.4f} on {c['pages']} pages; Haiku ${c['haiku_usd']:.4f} "
          f"({c['haiku_share'] * 100:.1f}%), jev ${c['jev_usd']:.4f}.", "",
          "| Leg | requests | input tok | output tok | cost $ | share | $ per 1k pages | returns |",
          "|---|---|---|---|---|---|---|---|"]
    order = ["H-PQ", "H-SPAN", "H-AQ", "B1", "B2", "J-P1R1", "J-P1R2", "J-SEG", "J-P2A1", "J-P2A3"]
    for leg in order:
        v = c["per_leg"].get(leg)
        if not v:
            continue
        if leg == "H-SPAN":
            ret = (f"{v['spans_returned']} spans on {v['pages_with_span']} pages (${fmt(v['cost_per_span_usd'], 4)}"
                   f" per span); publication date on {v['pages_with_pub_date']} pages")
        elif "nonempty_quotes" in v:
            ret = (f"{v['nonempty_quotes']} non-empty quotes over {v['item_cells']} item cells "
                   f"(${fmt(v['cost_per_nonempty_quote_usd'], 5)} per quote)")
        else:
            ret = "choices"
        L.append(f"| {leg} | {v['requests']} | {v['input_tokens']:,} | {v['output_tokens']:,} | {v['cost_usd']:.4f} "
                 f"| {v['share_of_total'] * 100:.1f}% | {v['cost_per_1k_pages_usd']:.2f} | {ret} |")
    L += ["", f"- {c['note_scaling']}",
          f"- H-SPAN + H-PQ at Batch prices (50% of sync on input and output, from measured sync tokens): "
          f"${c['h_span_plus_h_pq_at_batch_price_usd']:.4f} for 50 pages, "
          f"${c['h_span_plus_h_pq_at_batch_price_per_1k_pages_usd']:.2f} per 1k pages.",
          "- Haiku output tokens include adaptive thinking (billed as output); input dominates cost on every "
          "Haiku leg.", "",
          "## 6. Caveats", "",
          "- Presence-vs-choice comparisons measure whether the two engines *notice* the same material, not "
          "whether they would code it the same way.",
          "- The jev pass-2 legs ran only on activities that H-SPAN produced, so activity-level agreement is "
          "conditional on Haiku having found the activity; it cannot show what jev would do on activities "
          "Haiku missed.",
          "- H-SPAN's task follows the v2.7 activity rule; the jev verdict is the unclear2 proxy. "
          "`event_only` and `ambiguous_genai` pages are GenAI-bearing for the gate but may not contain a "
          "qualifying activity under the span rule, so span absence on them is partly by design.",
          "- One run each; no repeat of the sync legs, so the Batch comparison is the only run-to-run "
          "evidence and covers 10 pages.",
          "- Costs are this sample's; activity-scaled legs depend on the GenAI rate of the frame.", ""]
    return "\n".join(L)


def main():
    rows, summary, dry = load()
    calls, by_key, acts, quotes, qmap, returned = index(rows)
    pages = page_level(rows, calls, acts, qmap, dry)
    meta = next((r for r in rows if r.get("kind") == "meta" and r.get("event") == "start"), {})
    res = {
        "generated_by": {"script": "scripts/spikes/t002/agreement_t002.py", "at": date.today().isoformat(),
                         "inputs": [str(ANSWERS), str(SUMMARY), str(DRYRUN)], "network": False,
                         "run_models": {"jev": meta.get("jev_model"), "haiku": meta.get("haiku_model"),
                                        "haiku_effort": meta.get("haiku_effort")},
                         "codebook": meta.get("codebook")},
        "leg_map": LEG_MAP,
        "page_genai": page_genai_agreement(pages),
        "form_scope": form_scope_descriptive(pages, calls, qmap),
        "activity": activity_agreement(rows, calls, by_key, acts, qmap, returned),
        "batch": batch_consistency(calls, by_key, qmap),
        "costs": costs(summary, rows, pages, quotes),
        "pages": [pages[p] for p in sorted(pages)],
    }
    OUT_JSON.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    OUT_MD.write_text(render_md(res), encoding="utf-8")
    print("wrote", OUT_JSON)
    print("wrote", OUT_MD)


if __name__ == "__main__":
    main()
