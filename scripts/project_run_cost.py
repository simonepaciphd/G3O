#!/usr/bin/env python3
"""Project a v2.7 wave's cost, wall time and memory per extractor mode from a smoke run.

PI ruling 134: the operator sees an estimated cost and time for each mode (all_batch, mix,
no_batch) before choosing. This script scales a smoke run (default 20 institutions) to a
wave and prints a short table plus the remaining-envelope line
``envelope - recorded spend - wave-5 resume spend``. Arithmetic only: no network, no paid
call, nothing written. The model is :mod:`g3o.common.run_projection` (its docstring states
the assumptions).

Seeds (PI ruling Q177 a): the prior figures and their citations are NOT in this repository.
They are read from ``--seeds FILE`` or ``$G3O_PROJECTION_SEEDS`` (absolute, or relative to
``$G3O_DRIVE_ROOT``); without either the script exits 2. The default ``--n`` and the
envelope come from that file.

Telemetry, one of:
  --run-dir DIR     a smoke run directory: reads ``_cost_report.json`` and, from
                    ``events.jsonl``, the smoke's wall time and its per-page stage page
                    count (pages in; followed pages not included);
  --telemetry FILE  a JSON object of per-institution USD figures (keys as returned by
                    ``seed_per_institution``: serper_usd, unlocker_usd, typesafe_usd,
                    openai_usd, extractor_standard_usd, stage6_extractor_usd, x35_usd,
                    optionally pages_per_institution);
  neither           the seeds alone. The per-page parts then rest on the prior wave's
                    pages per institution (v2.5 scrape-out; v2.7 followed pages not
                    included): no TOTAL is printed unless --pages-per-institution is given.

Remaining envelope (PI ruling Q176 b): ``--recorded-usd`` is the recorded spend on the
RECOMPUTE basis (the cost report's Unlocker undercount corrected), not the raw cost report.
It and the wave-5 resume spend have no default: without both, the remaining envelope is
printed as unknown, with the seeds' last recompute range for reference.

Example:
  python scripts/project_run_cost.py --seeds seeds.json --run-dir runs/r...-smoke \
      --recorded-usd 1800 --wave5-resume-usd 150 --batch-round-hours 2
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from g3o.common import run_projection as rp  # noqa: E402


def _events(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "events.jsonl"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn last line
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _ts(rec: dict[str, Any]) -> datetime | None:
    raw = rec.get("ts")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _smoke_wall_s(events: list[dict[str, Any]]) -> float | None:
    """Seconds from the first timed event to ``run_completed``, or None (events without ``ts`` skipped)."""
    first = done = None
    for rec in events:
        ts = _ts(rec)
        if ts is None:
            continue
        first = first or ts
        if rec.get("event") == "run_completed":
            done = ts
    return None if first is None or done is None else (done - first).total_seconds()


def _smoke_pages(events: list[dict[str, Any]]) -> int | None:
    """Pages into the smoke's per-page stage (``stage_started`` perpage_v27 ``counts_in``), or None."""
    pages = None
    for rec in events:
        if rec.get("event") == "stage_started" and rec.get("stage") == "perpage_v27":
            value = (rec.get("payload") or {}).get("counts_in")
            if isinstance(value, int) and not isinstance(value, bool):
                pages = value  # the last start wins (a resumed run restarts the stage)
    return pages


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seeds", type=Path, default=None,
                   help=f"seeds JSON (default: ${rp.SEEDS_ENV}, absolute or relative to ${rp.DRIVE_ENV})")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--run-dir", type=Path)
    src.add_argument("--telemetry", type=Path)
    p.add_argument("--smoke-n", type=int, default=20, help="institutions in the smoke (default 20)")
    p.add_argument("--n", type=int, default=None, help="institutions to project (default: the seeds' wave4_n)")
    p.add_argument("--recorded-usd", type=float, default=None,
                   help="recorded spend so far, RECOMPUTE basis (Unlocker undercount corrected; Q176 b); no default")
    p.add_argument("--wave5-resume-usd", type=float, default=None, help="wave-5 resume spend (no default)")
    p.add_argument("--envelope-usd", type=float, default=None, help="default: the seeds' envelope_usd")
    p.add_argument("--pages-per-institution", type=float, default=None,
                   help="per-page stage pages per institution (needed for a seed-only TOTAL)")
    p.add_argument("--first-round-share", type=float, default=None)
    p.add_argument("--batch-multiplier", type=float, default=None, help="default: the pricing rate row")
    p.add_argument("--throughput-per-hour", type=float, default=None,
                   help="institutions per hour (seed: prior wave, v2.5)")
    p.add_argument("--batch-round-hours", type=float, default=None,
                   help="one batch round trip (seed: a small spike round; unmeasured at scale)")
    p.add_argument("--mix-rounds", type=int, default=None)
    p.add_argument("--all-batch-rounds", type=int, default=None,
                   help="sequential rounds in all_batch (unknown: shown as a lower bound)")
    p.add_argument("--unlocker-factor", type=float, default=None,
                   help="multiplier on unlocker spend (1.0 = cost-report basis, which under-counts)")
    p.add_argument("--smoke-peak-mb", type=float, default=None, help="the smoke's peak memory (MB), shown")
    p.add_argument("--json", action="store_true", help="print the rows as JSON instead of the table")
    return p


def run(args: argparse.Namespace, seeds: rp.Seeds) -> dict[str, Any]:
    n = args.n if args.n is not None else int(seeds["wave4_n"].value)
    smoke_wall = None
    if args.run_dir is not None:
        report = json.loads((args.run_dir / "_cost_report.json").read_text(encoding="utf-8"))
        per_inst = rp.per_institution_from_cost_report(report, args.smoke_n)
        events = _events(args.run_dir)
        smoke_wall = _smoke_wall_s(events)
        smoke_pages = _smoke_pages(events)
        if args.pages_per_institution is not None:
            pages, basis = args.pages_per_institution, "operator (--pages-per-institution)"
        elif smoke_pages is not None:
            pages = smoke_pages / args.smoke_n
            basis = (f"smoke per-page stage, {smoke_pages} pages in / {args.smoke_n} institutions "
                     "(events.jsonl; followed pages not included)")
        else:
            pages = rp.seed_pages_per_institution(seeds)
            basis = (f"{rp.seed_pages_basis(seeds)} (no per-page stage page count in the smoke's "
                     "events.jsonl); used for queue_MB only")
        per_inst.update(pages_per_institution=pages, pages_basis=basis, pages_provisional=False)
    elif args.telemetry is not None:
        tel = json.loads(args.telemetry.read_text(encoding="utf-8"))
        pages_arg = args.pages_per_institution if args.pages_per_institution is not None \
            else tel.get("pages_per_institution")
        base = rp.seed_per_institution(seeds, pages_arg)
        per_inst = {**base, **tel, "basis": f"telemetry JSON {args.telemetry.name}"}
        if args.pages_per_institution is None and tel.get("pages_per_institution") is not None:
            per_inst["pages_basis"] = f"telemetry JSON {args.telemetry.name}"
        # the per-page USD come from the telemetry when it gives them, not from the seed pages
        per_inst["pages_provisional"] = base["pages_provisional"] and not (
            {"extractor_standard_usd", "typesafe_usd"} <= tel.keys())
        per_inst["pages_per_institution"] = base["pages_per_institution"]
    else:
        per_inst = rp.seed_per_institution(seeds, args.pages_per_institution)
    a = rp.ModeAssumptions.from_seeds(
        seeds, first_round_share=args.first_round_share, batch_multiplier=args.batch_multiplier,
        throughput_per_hour=args.throughput_per_hour, batch_round_hours=args.batch_round_hours,
        mix_rounds=args.mix_rounds, all_batch_rounds=args.all_batch_rounds,
        unlocker_factor=args.unlocker_factor,
    )
    rows = rp.project_all(per_inst, n, a)
    envelope = args.envelope_usd if args.envelope_usd is not None else seeds["envelope_usd"].value
    remaining = rp.remaining_envelope(args.recorded_usd, args.wave5_resume_usd, envelope)
    warnings = []
    seed_serper = seeds["wave4_serper_usd"].value / seeds["wave4_n"].value
    if per_inst["serper_usd"] < 0.5 * seed_serper:
        warnings.append(
            f"Serper per institution ${per_inst['serper_usd']:.5f} is under half the prior-wave rate "
            f"${seed_serper:.5f}: the smoke may have been served from the SERP cache "
            "(a cached query costs nothing; a fresh wave's do)")
    return {"n": n, "basis": per_inst.get("basis"), "pages_basis": per_inst.get("pages_basis"),
            "per_institution": per_inst, "assumptions": vars(a), "rows": rows,
            "notes": rp.table_notes(per_inst, seeds, rows, a),
            "smoke_wall_s": smoke_wall, "smoke_peak_mb": args.smoke_peak_mb,
            "remaining_envelope_usd": remaining, "recorded_usd": args.recorded_usd,
            "recorded_basis": "recompute (cost report's Unlocker undercount corrected; Q176 b)",
            "wave5_resume_usd": args.wave5_resume_usd, "envelope_usd": envelope, "warnings": warnings}


def render(out: dict[str, Any], seeds: rp.Seeds) -> str:
    s = seeds
    lines = [rp.format_table(out["rows"], out["n"], out["notes"]), f"basis: {out['basis']}"]
    unpriced = sorted({k for r in out["rows"] for k in r["unpriced"]})
    if unpriced:
        lines.append(f"unpriced (not in total_known): {', '.join(unpriced)}"
                     + ("; x35: no seed for its volume (rate ruled, Q158 a)" if "x35" in unpriced else ""))
    lines.append(
        f"unlocker: cost-report basis x{out['assumptions']['unlocker_factor']}; the report under-counts "
        f"(prior wave report ${s['wave4_unlocker_usd'].value:,.2f} vs recompute up to "
        f"${s['wave4_unlocker_recompute_high_usd'].value:,.2f}, {s['wave4_unlocker_recompute_high_usd'].source})")
    lines.append(
        f"memory: queue_MB is a lower bound added by the batch modes; reference prior-wave peaks "
        f"RAM {s['wave4_peak_ram_mb'].value:,.0f} MB + swap {s['wave4_peak_swap_mb'].value:,.0f} MB "
        f"({s['wave4_peak_swap_mb'].source}); wave 5 died at swap {s['wave5_oom_swap_mb'].value:,.0f} MB "
        f"({s['wave5_oom_swap_mb'].source})"
        + (f"; smoke peak {out['smoke_peak_mb']:,.0f} MB" if out["smoke_peak_mb"] is not None else ""))
    if out["smoke_wall_s"] is not None:
        lines.append(f"smoke wall time {out['smoke_wall_s']:.0f} s (not used for scaling)")
    basis = f"recorded spend on the {out['recorded_basis']}"
    if out["remaining_envelope_usd"] is None:
        lo, hi = s["recorded_recompute_low_usd"], s["recorded_recompute_high_usd"]
        lines.append(
            f"remaining envelope: unknown (${out['envelope_usd']:,.2f} - recorded "
            f"{out['recorded_usd'] if out['recorded_usd'] is not None else '?'} - wave-5 resume "
            f"{out['wave5_resume_usd'] if out['wave5_resume_usd'] is not None else '?'}); basis: {basis}; "
            f"last recompute cumulative ${lo.value:,.2f}-${hi.value:,.2f} ({hi.source}), reference only")
    else:
        lines.append(
            f"remaining envelope: ${out['envelope_usd']:,.2f} - ${out['recorded_usd']:,.2f} - "
            f"${out['wave5_resume_usd']:,.2f} = ${out['remaining_envelope_usd']:,.2f} (basis: {basis})")
    lines += [f"WARNING: {w}" for w in out["warnings"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        seeds = rp.load_seeds(args.seeds)
    except (rp.SeedsUnavailable, ValueError) as exc:
        sys.stderr.write(f"seeds: {exc}\n")
        return 2
    out = run(args, seeds)
    if args.json:
        json.dump(out, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(render(out, seeds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
