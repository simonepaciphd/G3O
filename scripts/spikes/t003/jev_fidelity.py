"""T-003 jev quote-fidelity scoring (RC-D-014 P1). Calibration labels: jev 4+ on a 1-5 scale, or the 80% rule.

One jev Score question per (source chunk, quote) pair: "how accurately does the quote represent the source",
five ordered levels. jev returns levels 0-4; this script stores them and the fidelity 1-5 (= level + 1).

Modes
  dry-run  FREE, offline. Builds the scoring items (recovered candidates + near-miss controls), reconstructs each
           candidate's source chunk with the T-002 chunker, checks chunk sizes against SPIKE-T002-dryrun.json, and
           estimates tokens and cost. Writes SPIKE-T003-jev-items.jsonl and SPIKE-T003-jev-dryrun.json.
  run      PAID. Simone runs it (red line 4). Needs TYPESAFE_API_KEY in the shell. Refuses while the question
           wording is a draft, if the items differ from the dry-run, or if --cap is above $1. Append-only answers
           file with resume: run the same line again and done items are skipped.

Paths
  Inputs and outputs default to folders under the Drive root, read from G3O_DRIVE_ROOT or --drive; with neither
  set the script exits 2. --recovery-dir, --out and --t002-dryrun override single paths.

Items
  candidate  every unique (chunk_id, quote) pair among the 331 recovered candidates (duplicate candidates, e.g.
             sync vs Batch or one quote under two codes, share one item; the mapping is kept).
  control    near-miss controls built from those pairs (seed 20261104), quotes of >= MIN_CONTROL_WORDS words:
             onpage   CONTROL_FRACTION of the words replaced by other words from the same chunk, so word
                      presence stays 1.0 (tests the rule's leniency: all words present, meaning changed);
             offpage  CONTROL_FRACTION of the words replaced by words absent from the page (taken from another
                      page of the same script), so word presence falls to about 1 - CONTROL_FRACTION.
             "Words" are letter-and-digit runs (word_presence.py), so for CJK/Thai a swap replaces a run.

Cost and cap
  jev bills input only ($0.042/M, output free). Estimate: serialized state + question bytes x approved bases
  (Latin 0.305, CJK 0.341, Thai 0.334 tokens/byte), and x 1.90 for the RC-D-013 margin (0.5795 / 0.6479 /
  0.6346). Before each call the run reserves the 64k-token request maximum and stops before any call that could
  take spend past the cap. No halving on max_tokens_exceeded: the failure is recorded (halving could drop the
  quote's support).

PI rulings applied (decision page v27-gates-1104, saved 2026-11-04T16:23:45Z; record
agent-workspace/2026-11-04-v27-orch/decisions/v27-gates-1104.reply.json)
  A1 a "Drafted anchors"          the question wording below, as drafted, no line edits
  A2 a "Both kinds"               onpage + offpage controls, 40% of words swapped
  A3 a "Most likely level"        jev 4+ means fidelity_argmax >= 4 (applied in the step-5 analysis)
  P1 a "Score 222 unique, map back"  one item per unique (chunk_id, quote); candidate_ids kept
  P2 a "Fix now"                  word_presence.py keeps combining marks inside words (Thai)
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

_spec = importlib.util.spec_from_file_location("word_presence", HERE / "word_presence.py")
wp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wp)

# Paths relative to the Drive root (G3O_DRIVE_ROOT); overridable per run.
REL_RECOVERY_DIR = "agent-workspace/2026-11-02-safe-review/t003-recovery"
REL_T002_DRYRUN = "agent-workspace/2026-10-27-reclass-plan/spikes/SPIKE-T002-dryrun.json"
REL_OUT_DIR = "agent-workspace/2026-11-04-v27-orch/lane-a"

DRIVE_ENV = "G3O_DRIVE_ROOT"   # the G3O Drive root (the folder holding agent-workspace/); no machine path in git


def drive_root(override: Path | None = None) -> Path:
    """The Drive root from --drive or G3O_DRIVE_ROOT. Exits with code 2 and a clear message when neither is set."""
    v = override or os.environ.get(DRIVE_ENV)
    if not v:
        print(f"{DRIVE_ENV} is not set: point it at the G3O Drive root (the folder holding agent-workspace/), "
              "or pass --drive.", file=sys.stderr)
        raise SystemExit(2)
    p = Path(v)
    if not (p / "agent-workspace").is_dir():
        print(f"{DRIVE_ENV}={v} has no agent-workspace/ folder.", file=sys.stderr)
        raise SystemExit(2)
    return p

SEED = 20261104
CONTROL_KINDS = ("onpage", "offpage")
CONTROL_FRACTION = 0.4
MIN_CONTROL_WORDS = 3

# ---- T-002 chunker constants (PR #147 t002_core.py), needed to rebuild the source chunk of each quote
T002_TOKENS_PER_BYTE = 0.3947
T002_CHUNK_STATE_TOKENS = 24_000

# ---- Prices and limits
JEV_IN_PER_M = 0.042
JEV_REQUEST_TOKENS = 64_000
JEV_STATE_TOKENS = 32_000
CAP_MAX_USD = 1.00
BASES = {"latin": 0.305, "cjk": 0.341, "thai": 0.334}   # RC-D-013 approved bases (tokens per UTF-8 byte)
MARGIN = 0.90                                           # RC-D-013 uniform margin: effective = base x 1.90

RULINGS = {"A1": "a — Drafted anchors", "A2": "a — Both kinds", "A3": "a — Most likely level",
           "P1": "a — Score 222 unique, map back", "P2": "a — Fix now",
           "source": "decision page v27-gates-1104, saved 2026-11-04T16:23:45Z"}
JEV_4PLUS_FIELD = "fidelity_argmax"   # A3 a: label = most likely level, fidelity >= 4

# ---- The question (RC-D-014 P1; card step 2). Paid runs need an APPROVED status.
WORDING_STATUS = 'APPROVED 2026-11-04 decision page v27-gates-1104 A1: "a — Drafted anchors"'
QUESTION_ID = "quote_fidelity"
QUESTION_INSTRUCTIONS = (
    "How accurately does the quote represent the source? Compare `quote` with `source_text`, both in the "
    "page's original language. A quote may shorten the source by leaving words out, or reword it for clarity; "
    "judge whether it still says what the source says. Judge only how faithful the quote is to the source, not "
    "whether the topic matters."
)
QUESTION_LEVELS = (  # level 0..4 = fidelity 1..5
    "1 - Not represented: the source does not contain what the quote says, or says something different.",
    "2 - Poorly represented: some words or topics appear in the source, but the quote's main statement is not "
    "there or is substantially changed.",
    "3 - Partly represented: the main statement is in the source, but the quote adds, drops or changes an "
    "important detail (for example a name, number, date, scope or negation).",
    "4 - Accurately represented: the quote says what the source says; any difference is left-out text or "
    "light rewording that keeps the meaning.",
    "5 - Exactly represented: the quote appears in the source word for word, apart from case, spacing and "
    "punctuation.",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# =====================================================================================================
# Chunk reconstruction (copy of t002_core.byte_chunks, PR #147 2d743b3; kept identical)
# =====================================================================================================

def utf8_len(s: str) -> int:
    return len(s.encode("utf-8"))


def byte_chunks(text: str, cap: int) -> list[str]:
    if cap < 4:
        raise ValueError("cap must be at least 4 bytes (one UTF-8 character)")
    total = utf8_len(text)
    if total <= cap:
        return [text]
    n = math.ceil(total / cap)
    while True:
        target = math.ceil(total / n)
        out, cur, size = [], [], 0
        for ch in text:
            b = len(ch.encode("utf-8"))
            if size + b > target and cur:
                out.append("".join(cur))
                cur, size = [], 0
            cur.append(ch)
            size += b
        out.append("".join(cur))
        if all(utf8_len(p) <= cap for p in out):
            return out
        n += 1


def t002_chunks(text: str) -> list[str]:
    return byte_chunks(text, int(T002_CHUNK_STATE_TOKENS / T002_TOKENS_PER_BYTE))


def parse_chunk_id(chunk_id: str) -> tuple[int, int]:
    """'<page_id>#c2of3' -> (1, 3): zero-based index, count."""
    tail = chunk_id.rsplit("#c", 1)[1]
    i, n = tail.split("of")
    return int(i) - 1, int(n)


# =====================================================================================================
# Items
# =====================================================================================================

def _rec(x):
    return json.loads(x) if isinstance(x, str) else x


def load_recovery(recovery_dir: Path):
    pages = {}
    with open(recovery_dir / "SOURCE-PAGES.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            rec = _rec(r["source_record"])
            pages[r["page_id"]] = {"text": rec.get("text") or "", "title": rec.get("title") or "",
                                   "url": rec.get("url") or ""}
    cands = []
    with open(recovery_dir / "CANDIDATES.jsonl", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            q = _rec(c["saved_quote_record"])
            cands.append({"candidate_id": c["candidate_id"], "script": c["script"], "page_id": q["page_id"],
                          "chunk_id": q["chunk_id"], "quote": q["quote"]})
    return pages, cands


def make_state(page_part: str, source_text: str, quote: str) -> dict:
    return {"quote": quote, "page_part": page_part, "source_text": source_text}


def question_text() -> str:
    return "\n".join((QUESTION_INSTRUCTIONS,) + QUESTION_LEVELS)


def est_tokens(state: dict, script: str, margin: bool) -> int:
    rate = BASES.get(script, max(BASES.values()))
    if margin:
        rate *= 1 + MARGIN
    b = utf8_len(json.dumps(state, ensure_ascii=False)) + utf8_len(question_text())
    return math.ceil(b * rate)


def _swap(quote: str, k: int, pool: list[str], rng: random.Random) -> tuple[str, list[dict]] | None:
    spans = [m.span() for m in wp._WORD.finditer(quote)]
    if k < 1 or len(spans) < k or not pool:
        return None
    pos = sorted(rng.sample(range(len(spans)), k))
    out, last, swaps = [], 0, []
    for p in pos:
        a, b = spans[p]
        new = rng.choice(pool)
        out += [quote[last:a], new]
        swaps.append({"index": p, "old": quote[a:b], "new": new})
        last = b
    out.append(quote[last:])
    return "".join(out), swaps


def build_controls(pairs: list[dict], chunks: dict[str, str], pages: dict[str, dict],
                   kinds=CONTROL_KINDS, fraction=CONTROL_FRACTION, seed=SEED) -> tuple[list[dict], Counter]:
    rng = random.Random(seed)
    skipped = Counter()
    page_tokens = {pid: set(wp.word_tokens(p["text"])) for pid, p in pages.items()}
    pages_by_script = defaultdict(list)
    for x in pairs:
        if x["page_id"] not in pages_by_script[x["script"]]:
            pages_by_script[x["script"]].append(x["page_id"])
    out = []
    for x in pairs:
        qn = wp.word_tokens(x["quote"])
        if len(qn) < MIN_CONTROL_WORDS:
            skipped[f"{x['script']}:short"] += len(kinds)
            continue
        k = max(1, round(fraction * len(qn)))
        qset = set(qn)
        for kind in kinds:
            if kind == "onpage":
                src = chunks[x["chunk_id"]]
                pool = sorted({m.group(0) for m in wp._WORD.finditer(src)
                               if wp.normalize(m.group(0)) not in qset})
            elif kind == "offpage":
                others = [p for p in pages_by_script[x["script"]] if p != x["page_id"]]
                if not others:
                    skipped[f"{x['script']}:{kind}:no_other_page"] += 1
                    continue
                other = rng.choice(others)
                pool = sorted({m.group(0) for m in wp._WORD.finditer(pages[other]["text"])
                               if wp.normalize(m.group(0)) not in page_tokens[x["page_id"]]})
            else:
                raise ValueError(kind)
            res = _swap(x["quote"], k, pool, rng)
            if res is None:
                skipped[f"{x['script']}:{kind}:no_pool"] += 1
                continue
            quote, swaps = res
            s = wp.score(quote, pages[x["page_id"]]["text"], x["script"])
            out.append({**{f: x[f] for f in ("script", "page_id", "chunk_id", "page_part", "institution")},
                        "item_id": f"N-{kind}-{x['item_id'][2:]}", "kind": "control", "control_kind": kind,
                        "control_of": x["item_id"], "control_fraction": fraction, "swaps": swaps,
                        "quote": quote, "candidate_ids": [], "presence_word": s["presence_word"]})
    return out, skipped


def build_items(recovery_dir: Path, kinds=CONTROL_KINDS, fraction=CONTROL_FRACTION):
    pages, cands = load_recovery(recovery_dir)
    chunks, problems = {}, []
    for c in cands:
        cid = c["chunk_id"]
        if cid in chunks:
            continue
        i, n = parse_chunk_id(cid)
        parts = t002_chunks(pages[c["page_id"]]["text"])
        if len(parts) != n:
            problems.append(f"{cid}: rebuilt {len(parts)} chunks, id says {n}")
            continue
        chunks[cid] = parts[i]
    pairs, by_key = [], {}
    for c in cands:
        if c["chunk_id"] not in chunks:
            continue
        key = (c["chunk_id"], c["quote"])
        if key not in by_key:
            i, n = parse_chunk_id(c["chunk_id"])
            x = {"item_id": "P-" + sha256(c["chunk_id"] + "\n" + c["quote"])[:16], "kind": "candidate",
                 "script": c["script"], "page_id": c["page_id"], "chunk_id": c["chunk_id"],
                 "page_part": f"{i + 1} of {n}", "institution": wp.institution_of(c["page_id"]),
                 "quote": c["quote"], "candidate_ids": []}
            by_key[key] = x
            pairs.append(x)
        by_key[key]["candidate_ids"].append(c["candidate_id"])
    controls, skipped = build_controls(pairs, chunks, pages, kinds, fraction)
    items = pairs + controls
    for x in items:
        st = make_state(x["page_part"], chunks[x["chunk_id"]], x["quote"])
        x["state_sha256"] = sha256(json.dumps(st, ensure_ascii=False, sort_keys=True))
        x["est_tokens"] = est_tokens(st, x["script"], margin=False)
        x["est_tokens_margin"] = est_tokens(st, x["script"], margin=True)
    return items, chunks, pages, {"candidates": len(cands), "problems": problems, "controls_skipped": dict(skipped)}


def items_digest(items: list[dict]) -> str:
    return sha256("\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in items))


def check_chunk_bytes(chunks: dict[str, str], t002_dryrun: Path) -> dict:
    """Compare rebuilt chunk sizes with the bytes the T-002 dry run recorded for each page."""
    if not t002_dryrun.exists():
        return {"checked": 0, "mismatch": [], "note": f"{t002_dryrun} not found"}
    d = json.loads(t002_dryrun.read_text(encoding="utf-8"))
    rec = {p["page_id"]: p.get("chunk_bytes") for p in d["pages"]}
    mismatch, checked = [], 0
    for cid, text in chunks.items():
        pid = cid.rsplit("#c", 1)[0]
        i, _ = parse_chunk_id(cid)
        cb = rec.get(pid)
        if cb is None:
            mismatch.append(f"{cid}: page not in T-002 dry run")
            continue
        checked += 1
        if cb[i] != utf8_len(text):
            mismatch.append(f"{cid}: rebuilt {utf8_len(text)} bytes, T-002 dry run {cb[i]}")
    return {"checked": checked, "mismatch": mismatch}


def jev_cost(tokens: int) -> float:
    return tokens * JEV_IN_PER_M / 1e6


def dry_run(args) -> dict:
    items, chunks, _, notes = build_items(args.recovery_dir, args.control_kinds, args.control_fraction)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "SPIKE-T003-jev-items.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for x in items:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    tab = defaultdict(lambda: {"items": 0, "est_tokens": 0, "est_tokens_margin": 0})
    for x in items:
        k = f"{x['kind'] if x['kind'] == 'candidate' else 'control_' + x['control_kind']}|{x['script']}"
        for kk in (k, "all"):
            tab[kk]["items"] += 1
            tab[kk]["est_tokens"] += x["est_tokens"]
            tab[kk]["est_tokens_margin"] += x["est_tokens_margin"]
    for v in tab.values():
        v["cost_usd"] = round(jev_cost(v["est_tokens"]), 4)
        v["cost_usd_margin"] = round(jev_cost(v["est_tokens_margin"]), 4)
    over = [x["item_id"] for x in items if x["est_tokens_margin"] > JEV_STATE_TOKENS]
    cand = [x for x in items if x["kind"] == "candidate"]
    ctrl = [x for x in items if x["kind"] == "control"]
    summary = {
        "generated_at": now(), "mode": "dry-run", "seed": SEED, "wording_status": WORDING_STATUS,
        "rulings": RULINGS, "jev_4plus_field": JEV_4PLUS_FIELD,
        "question": {"id": QUESTION_ID, "type": "score", "instructions": QUESTION_INSTRUCTIONS,
                     "levels": list(QUESTION_LEVELS), "sha256": sha256(question_text())},
        "controls": {"kinds": list(args.control_kinds), "fraction": args.control_fraction,
                     "min_words": MIN_CONTROL_WORDS, "skipped": notes["controls_skipped"],
                     "presence_word_by_kind": {k: Counter(x["presence_word"] >= 0.8 for x in ctrl
                                                           if x["control_kind"] == k).most_common()
                                               for k in args.control_kinds}},
        "counts": {"recovered_candidates": notes["candidates"], "candidate_items": len(cand),
                   "candidates_mapped": sum(len(x["candidate_ids"]) for x in cand), "control_items": len(ctrl),
                   "chunks": len(chunks), "chunk_problems": notes["problems"]},
        "chunk_bytes_check": check_chunk_bytes(chunks, args.t002_dryrun),
        "estimate": dict(sorted(tab.items())),
        "max_est_tokens_margin": max(x["est_tokens_margin"] for x in items),
        "items_over_32k_state_at_margin": over,
        "cap_usd": CAP_MAX_USD, "reserve_per_call_usd": round(jev_cost(JEV_REQUEST_TOKENS), 6),
        "prices_usd_per_mtok": {"jev_in": JEV_IN_PER_M, "jev_out": 0.0},
        "bases": BASES, "margin": MARGIN,
        "items_sha256": items_digest(items),
    }
    (out / "SPIKE-T003-jev-dryrun.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")
    return summary


# =====================================================================================================
# Paid run
# =====================================================================================================

class CapReached(RuntimeError):
    pass


class Log:
    """Append-only JSONL. Rows with ok=True are done; spend is re-read on resume."""

    def __init__(self, path: Path):
        self.path, self.done, self.spent = path, {}, 0.0
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.spent += r.get("cost_usd") or 0.0
                    if r.get("ok") and r.get("key"):
                        self.done[r["key"]] = r
        self.f = path.open("a", encoding="utf-8", newline="\n")

    def write(self, row: dict):
        row.setdefault("ts", now())
        self.f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        self.f.flush()
        if row.get("ok") and row.get("key"):
            self.done[row["key"]] = row

    def close(self):
        self.f.close()


def score_items(items, chunks, ask, log: Log, cap_usd: float, question, model_note=None) -> dict:
    """Score each item not yet done. `ask(state, {qid: question}) -> JevResult-like`. Stops at the cap."""
    reserve = jev_cost(JEV_REQUEST_TOKENS)
    n_new = n_fail = 0
    for x in items:
        if x["item_id"] in log.done:
            continue
        if log.spent + reserve > cap_usd:
            raise CapReached(f"cap ${cap_usd:.2f}: spent ${log.spent:.4f} + next-call bound ${reserve:.4f}")
        st = make_state(x["page_part"], chunks[x["chunk_id"]], x["quote"])
        base = {"kind": "jev", "key": x["item_id"], "item_kind": x["kind"], "script": x["script"],
                "est_tokens": x["est_tokens"], "state_sha256": x["state_sha256"]}
        t0 = time.perf_counter()
        try:
            res = ask(st, {QUESTION_ID: question})
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ == "JevAccountError":
                log.write({**base, "ok": False, "error": "JevAccountError", "latency_s": time.perf_counter() - t0})
                raise
            log.write({**base, "ok": False, "error": repr(e)[:800],
                       "max_tokens_exceeded": "max_tokens_exceeded" in repr(e), "latency_s": time.perf_counter() - t0})
            n_fail += 1
            continue
        a = res.answers[QUESTION_ID]
        probs = {int(k): v for k, v in (a.probabilities or {}).items()}
        argmax = max(probs, key=lambda k: (probs[k], -k)) if probs else None
        cost = jev_cost(res.input_tokens)
        log.spent += cost
        log.write({**base, "ok": True, "request_id": res.request_id, "response_model": res.response_model,
                   "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "cost_usd": cost,
                   "latency_s": time.perf_counter() - t0, "score_level_expected": a.score,
                   "fidelity_expected": None if a.score is None else a.score + 1,
                   "level_argmax": argmax, "fidelity_argmax": None if argmax is None else argmax + 1,
                   "confidence": a.confidence, "probabilities": probs})
        n_new += 1
    return {"scored_now": n_new, "failed_now": n_fail, "done_total": len(log.done), "spent_usd": round(log.spent, 6)}


def paid_run(args) -> int:
    if not WORDING_STATUS.startswith("APPROVED"):
        sys.exit("Question wording is a DRAFT: the PI must approve it before any paid run (RC-D-014 P1).")
    if args.cap > CAP_MAX_USD:
        sys.exit(f"--cap above ${CAP_MAX_USD:.2f} is refused.")
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set in this shell. Set $env:TYPESAFE_API_KEY first.")
    dr_path = args.out_dir / "SPIKE-T003-jev-dryrun.json"
    if not dr_path.exists():
        sys.exit(f"{dr_path} not found: run dry-run first.")
    dr = json.loads(dr_path.read_text(encoding="utf-8"))
    items, chunks, _, _ = build_items(args.recovery_dir, tuple(dr["controls"]["kinds"]), dr["controls"]["fraction"])
    if items_digest(items) != dr["items_sha256"]:
        sys.exit("Rebuilt items differ from the dry run (items_sha256); re-run dry-run and re-check the estimate.")
    if sha256(question_text()) != dr["question"]["sha256"]:
        sys.exit("Question wording differs from the dry run; re-run dry-run.")
    sys.path.insert(0, str(REPO))
    import typesafe_sdk as ts

    from g3o.common import credentials, jev_client
    client = jev_client.client_from_credentials(credentials.resolve())
    question = ts.Score(instructions=QUESTION_INSTRUCTIONS, criteria=list(QUESTION_LEVELS))
    log = Log(args.out_dir / "SPIKE-T003-jev-answers.jsonl")
    log.write({"kind": "meta", "event": "start", "cap_usd": args.cap, "spent_before_usd": round(log.spent, 6),
               "jev_model": jev_client.DEFAULT_JEV_MODEL, "items_sha256": dr["items_sha256"],
               "question_sha256": dr["question"]["sha256"], "wording_status": WORDING_STATUS})
    try:
        res = score_items(items, chunks, lambda st, qs: jev_client.ask(st, qs, client=client), log, args.cap,
                          question)
    except CapReached as e:
        log.write({"kind": "meta", "event": "cap_reached", "detail": str(e), "spent_usd": round(log.spent, 6)})
        print(str(e))
        log.close()
        return 2
    log.write({"kind": "meta", "event": "end", **res})
    log.close()
    print(json.dumps(res, indent=1))
    return 0 if res["failed_now"] == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    for name in ("dry-run", "run"):
        p = sub.add_parser(name)
        p.add_argument("--drive", type=Path, default=None, help=f"Drive root; default ${DRIVE_ENV}")
        p.add_argument("--recovery-dir", type=Path, default=None, help=f"default <drive>/{REL_RECOVERY_DIR}")
        p.add_argument("--out", "--out-dir", dest="out_dir", type=Path, default=None,
                       help=f"default <drive>/{REL_OUT_DIR}")
        if name == "dry-run":
            p.add_argument("--t002-dryrun", type=Path, default=None, help=f"default <drive>/{REL_T002_DRYRUN}")
            p.add_argument("--control-kinds", type=lambda s: tuple(x for x in s.split(",") if x),
                           default=CONTROL_KINDS, help="comma list of onpage,offpage; empty string for none")
            p.add_argument("--control-fraction", type=float, default=CONTROL_FRACTION)
        else:
            p.add_argument("--cap", type=float, default=CAP_MAX_USD)
    a = ap.parse_args(argv)
    for attr, rel in (("recovery_dir", REL_RECOVERY_DIR), ("out_dir", REL_OUT_DIR), ("t002_dryrun", REL_T002_DRYRUN)):
        if hasattr(a, attr) and getattr(a, attr) is None:
            setattr(a, attr, drive_root(a.drive) / rel)
    if a.mode == "dry-run":
        s = dry_run(a)
        print(json.dumps({k: s[k] for k in ("counts", "chunk_bytes_check", "estimate", "max_est_tokens_margin",
                                            "items_over_32k_state_at_margin", "controls", "items_sha256")},
                         ensure_ascii=False, indent=1))
        return 0 if not s["counts"]["chunk_problems"] and not s["chunk_bytes_check"]["mismatch"] else 1
    return paid_run(a)


if __name__ == "__main__":
    raise SystemExit(main())
