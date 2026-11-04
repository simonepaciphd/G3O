"""T-040 jev scoring of the agent's real-page fixture labels (RC-D-014 P4: "replace with agent + jev").

One jev Score question per real-page expected value: "how accurately does this label describe the page for the
named institution", five ordered levels (same 1-5 scale as T-003 / RC-D-014 P1). jev returns levels 0-4; the
script stores them and the score 1-5 (= level + 1).

Modes
  dry-run  FREE, offline. Builds one item per scorable real-page label from tests/fixtures/v27/real.json, resolves
           each page from its pinned Drive store (hash-checked), cuts the page to the part holding the label's
           evidence quote when the page is over the state limit, estimates tokens and cost. Writes
           T040-jev-items.jsonl and T040-jev-dryrun.json to --out-dir (with --round R: -R suffixed files).
  --only K --round R  re-score only label key K (repeatable). A relabelled label has key <fixture>#<i>@v<n>, so the
           earlier answer stays in the append-only answers file under its old key and both remain visible.
  run      PAID. Simone runs it (red line 4). Needs TYPESAFE_API_KEY and G3O_DRIVE_ROOT (or --drive). Refuses while WORDING_STATUS is DRAFT, if the
           items differ from the dry-run, or if --cap is above $1. Append-only answers file with resume.

Not scored (no page-label meaning): segmentation counts (n_activities) and institution-level items; they are
covered by the page labels they rest on and by T-041.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FIX = REPO / "tests" / "fixtures" / "v27"
OUT_SUBDIR = (
    "agent-workspace/2026-11-04-v27-orch/lane-d"  # under the Drive root (G3O_DRIVE_ROOT setting)
)

_spec = importlib.util.spec_from_file_location("fixture_text", FIX / "fixture_text.py")
ft = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ft)

JEV_IN_PER_M = 0.042
JEV_REQUEST_TOKENS = 64_000
STATE_TOKENS = 24_000  # page part cap inside the 32k state (T-002 chunk size)
CAP_MAX_USD = 1.00
BASES = {
    "latin": 0.305,
    "cjk": 0.341,
    "thai": 0.334,
}  # RC-D-013 approved bases (tokens per UTF-8 byte)
MARGIN = 0.90  # RC-D-013 uniform margin
SKIP_ITEMS = {"n_activities", "core.has_genai_activity"}

WORDING_STATUS = 'APPROVED 2026-11-04 decision page v27-gates-1104 D3: "a — Approve as drafted"'
QUESTION_ID = "label_fidelity"
QUESTION_INSTRUCTIONS = (
    "How accurately does `label` describe `page_text` for the institution named in `institution`? `item_question` "
    "is the question the label answers and `label_definition` defines the label. Judge only from the page text; "
    "use no outside knowledge."
)
QUESTION_LEVELS = (
    "1 - Wrong: the page clearly calls for a different answer.",
    "2 - Mostly wrong: a different answer fits the page better.",
    "3 - Arguable: the label and another answer fit about equally well.",
    "4 - Right: the label fits the page; another reading is possible but weaker.",
    "5 - Clearly right: the page plainly supports the label and no other answer fits.",
)


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def script_of(text: str) -> str:
    cjk = sum(1 for c in text if "\u3040" <= c <= "\u9fff" or "\uac00" <= c <= "\ud7af")
    thai = sum(1 for c in text if "\u0e00" <= c <= "\u0e7f")
    letters = max(1, sum(c.isalpha() for c in text))
    return "thai" if thai / letters > 0.3 else "cjk" if cjk / letters > 0.3 else "latin"


def page_part(text: str, quote: str | None, script: str) -> tuple[str, str]:
    cap = int(STATE_TOKENS / (BASES[script] * (1 + MARGIN)))
    if len(text.encode("utf-8")) <= cap:
        return text, "whole"
    b = text.encode("utf-8")
    i = text.find(quote) if quote else -1
    start = max(0, len(text[:i].encode("utf-8")) - cap // 2) if i >= 0 else 0
    return b[start : start + cap].decode(
        "utf-8", errors="ignore"
    ), f"bytes {start}-{start + cap} (around evidence quote)"


def label_text(items: dict, item: str, value) -> tuple[str, str]:
    it = items.get(item, {})
    q = (
        (it.get("instruction") or {}).get("text")
        if isinstance(it.get("instruction"), dict)
        else it.get("instruction")
    )
    for v in it.get("values") or []:
        if isinstance(v, dict) and v.get("code") == value:
            return q or item, (v.get("definition") or {}).get("text", "")
    return q or item, "missing-value label: the page does not document this" if value in (
        "not_documented",
    ) else ""


def build_items(drive, only=None):
    import yaml

    items = yaml.safe_load((REPO / "codebook" / "codebook.yaml").read_text(encoding="utf-8"))[
        "items"
    ]
    out = []
    for f in json.loads((FIX / "real.json").read_text(encoding="utf-8"))["fixtures"]:
        if "page_ref" not in f:
            continue
        text = ft.load_real_text(f["page_ref"], drive)
        script = script_of(text)
        for k, e in enumerate(f["expected"]):
            if e["item"] in SKIP_ITEMS:
                continue
            part, where = page_part(text, e.get("evidence_quote"), script)
            q, d = label_text(items, e["item"], e["value"])
            state = {
                "institution": f"{f['institution'].get('name')} ({f['institution'].get('country')})",
                "item_question": q,
                "label": e["value"],
                "label_definition": d,
                "label_scope": e["scope"],
                "page_text": part,
            }
            sb = json.dumps(state, ensure_ascii=False)
            est = int(
                len((sb + QUESTION_INSTRUCTIONS + "".join(QUESTION_LEVELS)).encode("utf-8"))
                * BASES[script]
            )
            out.append(
                {
                    "item_id": ft.label_key(f["fixture_id"], k, e),
                    "fixture_id": f["fixture_id"],
                    "item": e["item"],
                    "label": e["value"],
                    "script": script,
                    "page_part": where,
                    "state": state,
                    "state_sha256": sha256(sb),
                    "est_tokens": est,
                    "est_tokens_margin": int(est * (1 + MARGIN)),
                }
            )
    if only:
        missing = set(only) - {x["item_id"] for x in out}
        if missing:
            raise SystemExit(f"--only keys not among the scorable labels: {sorted(missing)}")
        out = [x for x in out if x["item_id"] in set(only)]
    return out


def files(args):
    """Items and dry-run file names; a named --round gets its own pair so earlier rounds stay as evidence."""
    sfx = f"-{args.round}" if args.round else ""
    return args.out_dir / f"T040-jev-items{sfx}.jsonl", args.out_dir / f"T040-jev-dryrun{sfx}.json"


def digest(items):
    return sha256("\n".join(f"{x['item_id']}|{x['state_sha256']}" for x in items))


def cost(tokens):
    return tokens * JEV_IN_PER_M / 1e6


def dry_run(args):
    items = build_items(args.drive, args.only)
    items_path, dry_path = files(args)
    with items_path.open("w", encoding="utf-8", newline="\n") as fo:
        for x in items:
            fo.write(json.dumps(x, ensure_ascii=False) + "\n")
    tot = sum(x["est_tokens"] for x in items)
    totm = sum(x["est_tokens_margin"] for x in items)
    s = {
        "generated_at": now(),
        "mode": "dry-run",
        "wording_status": WORDING_STATUS,
        "question": {
            "id": QUESTION_ID,
            "instructions": QUESTION_INSTRUCTIONS,
            "levels": list(QUESTION_LEVELS),
        },
        "n_items": len(items),
        "by_script": {k: sum(x["script"] == k for x in items) for k in BASES},
        "est_tokens": tot,
        "est_tokens_margin": totm,
        "cost_usd": round(cost(tot), 4),
        "cost_usd_margin": round(cost(totm), 4),
        "max_est_tokens_margin": max(x["est_tokens_margin"] for x in items),
        "cap_usd": CAP_MAX_USD,
        "reserve_per_call_usd": round(cost(JEV_REQUEST_TOKENS), 6),
        "round": args.round or "r1",
        "only": args.only or None,
        "items_sha256": digest(items),
    }
    dry_path.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        json.dumps(
            {
                k: s[k]
                for k in (
                    "n_items",
                    "by_script",
                    "est_tokens_margin",
                    "cost_usd_margin",
                    "items_sha256",
                )
            }
        )
    )
    return s


def score_fields(probabilities, score) -> dict:
    """Both readings of a jev Score answer on the 1-5 scale.

    jev's ``score`` is the probability-weighted expected level on 0-4, not the most likely level, so it is never
    truncated: ``jev_expected_1_5`` = score + 1 (unrounded); ``jev_argmax_1_5`` = most likely level + 1 (ties go to
    the lower level, as in T-003 jev_fidelity.py); ``level_raw`` = jev's score as returned.
    """
    probs = {int(k): v for k, v in (probabilities or {}).items()}
    argmax = max(probs, key=lambda k: (probs[k], -k)) if probs else None
    return {
        "level_raw": score,
        "jev_argmax_1_5": None if argmax is None else argmax + 1,
        "jev_expected_1_5": None if score is None else score + 1,
    }


def score(items, ask, log_path: Path, cap, question):
    done, spent = set(), 0.0
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                r = json.loads(line)
                spent += r.get("cost_usd") or 0.0
                if r.get("ok"):
                    done.add(r["key"])
    reserve = cost(JEV_REQUEST_TOKENS)
    with log_path.open("a", encoding="utf-8", newline="\n") as fo:
        for x in items:
            if x["item_id"] in done:
                continue
            if spent + reserve > cap:
                print(f"cap ${cap:.2f} reached: spent ${spent:.4f}")
                return 2
            t0 = time.perf_counter()
            try:
                res = ask(x["state"], {QUESTION_ID: question})
            except Exception as e:  # noqa: BLE001
                fo.write(
                    json.dumps(
                        {"key": x["item_id"], "ok": False, "error": repr(e)[:800], "ts": now()}
                    )
                    + "\n"
                )
                if type(e).__name__ == "JevAccountError":
                    raise
                continue
            a = res.answers[QUESTION_ID]
            c = cost(res.input_tokens)
            spent += c
            fo.write(
                json.dumps(
                    {
                        "key": x["item_id"],
                        "ok": True,
                        **score_fields(a.probabilities, a.score),
                        "probabilities": a.probabilities,
                        "confidence": a.confidence,
                        "response_model": res.response_model,
                        "request_id": res.request_id,
                        "input_tokens": res.input_tokens,
                        "cost_usd": c,
                        "latency_s": time.perf_counter() - t0,
                        "ts": now(),
                    },
                    default=str,
                )
                + "\n"
            )
            fo.flush()
    print(f"done; spent ${spent:.4f}")
    return 0


def paid_run(args):
    if WORDING_STATUS.startswith("DRAFT"):
        print("refused: question wording is DRAFT (PI approval needed)")
        return 3
    if args.cap > CAP_MAX_USD:
        print(f"refused: --cap above ${CAP_MAX_USD}")
        return 3
    dr = json.loads(files(args)[1].read_text(encoding="utf-8"))
    items = build_items(args.drive, args.only)
    if digest(items) != dr["items_sha256"]:
        print("refused: items differ from the dry-run; re-run dry-run and re-approve")
        return 3
    import typesafe_sdk as ts

    from g3o.common import credentials, jev_client

    client = jev_client.client_from_credentials(credentials.resolve())
    q = ts.Score(instructions=QUESTION_INSTRUCTIONS, criteria=list(QUESTION_LEVELS))
    return score(
        items,
        lambda st, qs: jev_client.ask(st, qs, client=client),
        args.out_dir / "T040-jev-answers.jsonl",
        args.cap,
        q,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    for name in ("dry-run", "run"):
        p = sub.add_parser(name)
        p.add_argument(
            "--drive",
            type=Path,
            default=None,
            help="G3O Drive root; default: the G3O_DRIVE_ROOT setting",
        )
        p.add_argument("--out-dir", type=Path, default=None, help=f"default: <drive>/{OUT_SUBDIR}")
        p.add_argument(
            "--only",
            action="append",
            default=None,
            help="score only this label key (repeatable), e.g. v27-real-12#0@v2",
        )
        p.add_argument(
            "--round",
            default="",
            help="name of a re-score round (own items/dry-run files); required with --only",
        )
        if name == "run":
            p.add_argument("--cap", type=float, default=CAP_MAX_USD)
    args = ap.parse_args(argv)
    if args.only and not args.round:
        print(
            "error: --only needs --round (keeps earlier dry-run files as evidence)", file=sys.stderr
        )
        return 2
    try:
        args.drive = args.drive or ft.drive_root()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    args.out_dir = args.out_dir or (args.drive / OUT_SUBDIR)
    if args.mode == "dry-run":
        dry_run(args)
        return 0
    return paid_run(args)


if __name__ == "__main__":
    sys.exit(main())
