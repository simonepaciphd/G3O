"""Cost and wall-time projection per v2.7 extractor mode (PI ruling 134; priced per 130 a).

Arithmetic only: this module imports nothing from the pipeline but :mod:`g3o.common.pricing`
and makes no call. It reads one file, the seeds JSON (below). It is shared by the preflight
(:mod:`g3o.run.preflight`, which shows an estimate for each of the three modes before a
run) and by ``scripts/project_run_cost.py`` (which scales a smoke run's telemetry to a wave).

**Every figure here is an ESTIMATE.** Nothing is blocked on it (ruling 134: the operator
is shown the estimates and chooses; the cost gate is unchanged).

**Seeds live outside this repository** (PI ruling Q177 a). The prior spend, envelope, wave
size, wall time, memory and spike figures, each with its citation, are a private JSON file
read at run time from ``--seeds`` or from ``$G3O_PROJECTION_SEEDS`` (an absolute path, or
one relative to ``$G3O_DRIVE_ROOT``). Its shape::

    {"seeds": {"<name>": {"value": <number>, "source": "<path>:<line>", "note": "..."}}}

with every name in :data:`REQUIRED_SEEDS`. No file, no seed-based estimate: the preflight
then says the seeds are unavailable and goes on.

Inputs (per institution, USD): Serper, Web Unlocker, TypeSafe (jev: Stages 2/3, the
per-page stage, Stage 6), OpenAI (none on v2.7), the per-page extractor at STANDARD
rates, the Stage 6 extractor (quote step; always live) and X35 (unpriced until Q158).

How the three modes differ (``perpage_batch_v27`` module docstring):

- ``no_batch``: every per-page extractor call is live, at standard rates;
- ``mix`` (the default, ruling 134): first-round pass-1 / pass-2 page requests go through
  Message Batches (batch rates), follow-ups stay live (130 a). The batched share of the
  per-page extractor's standard spend is ``first_round_share``;
- ``all_batch``: every per-page extractor call is batched.

Batched spend = standard spend x the rate row's ``batch_discount`` (a multiplier,
``g3o/common/pricing.py``). The long-prompt tier of the rate row is not modelled: the
per-page chunk target sits well under its threshold.

Pages per institution: in seed-only mode the per-page parts are the spike's per-page cost
x the prior wave's scrape-out per institution (the v2.5 instrument), which does NOT count
the pages v2.7 follows. So a seed-only total is withheld unless the operator gives a pages
figure; the per-part figures are still shown, marked.

Wall time = ``n / throughput`` + ``batch rounds x round latency``. The live time a batched
request no longer takes is NOT subtracted. Every batch-mode wall time is a LOWER BOUND:
the round latency is a small spike measurement unless the operator sets it (a batch may
take up to the API's 24 h at wave scale), and the throughput is the v2.5 instrument's.

Memory: a batch mode holds every request queued in a wave in process memory until the
wave is submitted (``BatchExtractor._jobs``). The first wave queues every page's first
request, so the batch modes add ``n x pages x chunks/page x bytes/request`` to the peak.
Bytes/request is the chunk target (a lower bound: the prompt and the Python object
overhead come on top). Peak memory is otherwise not extrapolated from a smoke; the prior
wave's peaks are shown as the reference.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from g3o.common.pricing import HAIKU_5_5_PRICING, pricing_for, usd

ALL_BATCH = "all_batch"
MIX = "mix"
NO_BATCH = "no_batch"
#: same names and order as ``g3o.run.presweep.perpage_batch_v27.EXTRACTOR_MODES`` (ruling 134)
MODES = (ALL_BATCH, MIX, NO_BATCH)
BATCH_MODES = (ALL_BATCH, MIX)

#: the seeds file: an absolute path, or a path relative to ``$G3O_DRIVE_ROOT`` (Q177 a)
SEEDS_ENV = "G3O_PROJECTION_SEEDS"
DRIVE_ENV = "G3O_DRIVE_ROOT"

#: names the seeds file must carry (values are figures; sources stay in the file)
REQUIRED_SEEDS = (
    "envelope_usd",
    "recorded_recompute_low_usd", "recorded_recompute_high_usd",
    "wave4_n", "wave4_wall_s", "wave4_scraped_pages",
    "wave4_serper_usd", "wave4_unlocker_usd", "wave4_unlocker_recompute_high_usd", "wave4_typesafe_usd",
    "wave4_peak_ram_mb", "wave4_peak_swap_mb", "wave5_oom_swap_mb",
    "spike_pages", "spike_chunks", "spike_chunk_target_bytes",
    "spike_h_span_usd", "spike_h_pq_usd", "spike_h_aq_usd", "spike_jev_usd",
    "spike_batch_round_s", "spike_batch_requests",
)

#: parts whose seed-only figure depends on pages per institution
PAGE_PARTS = ("typesafe", "anthropic_perpage")


class SeedsUnavailable(LookupError):
    """No seeds file was given or found (not an error for the preflight)."""


@dataclass(frozen=True)
class Seed:
    value: float
    source: str
    note: str = ""


Seeds = Mapping[str, Seed]


def resolve_seeds_path(explicit: str | os.PathLike[str] | None = None,
                       environ: Mapping[str, str] | None = None) -> Path | None:
    """``explicit``, else ``$G3O_PROJECTION_SEEDS`` (relative to ``$G3O_DRIVE_ROOT`` when not absolute)."""
    if explicit is not None:
        return Path(explicit)
    env = os.environ if environ is None else environ
    raw = env.get(SEEDS_ENV)
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute() and env.get(DRIVE_ENV):
        path = Path(env[DRIVE_ENV]) / path
    return path


def load_seeds(path: str | os.PathLike[str] | None = None,
               environ: Mapping[str, str] | None = None) -> dict[str, Seed]:
    """Read and check the seeds file. Raises :class:`SeedsUnavailable` when there is none."""
    resolved = resolve_seeds_path(path, environ)
    if resolved is None:
        raise SeedsUnavailable(f"no seeds file: pass --seeds or set {SEEDS_ENV} "
                               f"(absolute, or relative to {DRIVE_ENV})")
    if not resolved.is_file():
        raise SeedsUnavailable(f"seeds file not found: {resolved}")
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    entries = raw.get("seeds") if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        raise ValueError("seeds file has no 'seeds' object")
    seeds: dict[str, Seed] = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"seed {name!r} is not an object")
        value, source = entry.get("value"), entry.get("source")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"seed {name!r} has no numeric value")
        if not isinstance(source, str) or ":" not in source:
            raise ValueError(f"seed {name!r} has no 'path:line' source")
        seeds[name] = Seed(float(value), source, str(entry.get("note") or ""))
    missing = [n for n in REQUIRED_SEEDS if n not in seeds]
    if missing:
        raise ValueError(f"seeds file lacks {', '.join(missing)}")
    return seeds


def _v(seeds: Seeds, name: str) -> float:
    return seeds[name].value


def seed_pages_per_institution(seeds: Seeds) -> float:
    """The prior wave's scrape-out per institution (v2.5; v2.7 followed pages not included)."""
    return _v(seeds, "wave4_scraped_pages") / _v(seeds, "wave4_n")


def seed_pages_basis(seeds: Seeds) -> str:
    return (f"{seed_pages_per_institution(seeds):.3f} pages/institution = wave-4 v2.5 scrape-out; "
            "v2.7 followed pages not included")


def seed_per_institution(seeds: Seeds, pages_per_institution: float | None = None) -> dict[str, Any]:
    """Per-institution figures from the seeds alone (no smoke), with their basis.

    The per-page parts (jev, extractor) are the spike's per-page cost x pages per
    institution; the rest are the prior wave's cost report / its n. The spike asked proxy
    questions, so its per-page cost is not a v2.7 run estimate. Without
    ``pages_per_institution`` the pages are the seed basis and ``pages_provisional`` is
    True: :func:`project_mode` then withholds the total.
    """
    n4 = _v(seeds, "wave4_n")
    provisional = pages_per_institution is None
    pages = seed_pages_per_institution(seeds) if provisional else pages_per_institution
    spike_pages = _v(seeds, "spike_pages")
    haiku_sync = _v(seeds, "spike_h_span_usd") + _v(seeds, "spike_h_pq_usd") + _v(seeds, "spike_h_aq_usd")
    return {
        "pages_per_institution": pages,
        "pages_basis": seed_pages_basis(seeds) if provisional else "operator (--pages-per-institution)",
        "pages_provisional": provisional,
        "serper_usd": _v(seeds, "wave4_serper_usd") / n4,
        "unlocker_usd": _v(seeds, "wave4_unlocker_usd") / n4,
        # wave 4's jev (Stages 2/3 + validate) stands in for v2.7's Stages 2/3 + Stage 6 jev
        "typesafe_usd": _v(seeds, "wave4_typesafe_usd") / n4 + pages * _v(seeds, "spike_jev_usd") / spike_pages,
        "openai_usd": 0.0,
        "extractor_standard_usd": pages * haiku_sync / spike_pages,
        "stage6_extractor_usd": None,  # quote step: no seed
        "x35_usd": None,  # Q158: unpriced
        "basis": "seeds (prior wave cost report / its n; spike per-page legs)",
    }


def seed_first_round_share(seeds: Seeds) -> float:
    """Share of the per-page extractor's standard spend in first-round requests.

    ASSUMPTION: the spike's H-SPAN and H-PQ legs (one request per chunk) stand in for the
    first-round pass-1 / pass-2 page requests, and H-AQ (per activity) for the follow-ups.
    """
    first = _v(seeds, "spike_h_span_usd") + _v(seeds, "spike_h_pq_usd")
    return first / (first + _v(seeds, "spike_h_aq_usd"))


def seed_chunks_per_page(seeds: Seeds) -> float:
    return _v(seeds, "spike_chunks") / _v(seeds, "spike_pages")


def seed_throughput_per_hour(seeds: Seeds) -> float:
    """Institutions per hour, prior wave (v2.5 instrument, all stages)."""
    return _v(seeds, "wave4_n") / (_v(seeds, "wave4_wall_s") / 3600)


@dataclass
class ModeAssumptions:
    """The knobs of the mode comparison; :meth:`from_seeds` fills them from the seeds."""

    first_round_share: float
    throughput_per_hour: float
    batch_round_hours: float
    chunks_per_page: float
    request_bytes: float
    batch_multiplier: float = float(HAIKU_5_5_PRICING["batch_discount"])
    #: sequential batch rounds: mix = the pass-1 then the pass-2 first round (pass-2 needs
    #: pass-1's answer); all_batch = None (chain depth unknown: shown as a lower bound)
    mix_rounds: int = 2
    all_batch_rounds: int | None = None
    unlocker_factor: float = 1.0  # 1.0 = cost-report basis (the report under-counts the Unlocker)

    @classmethod
    def from_seeds(cls, seeds: Seeds, **overrides: Any) -> ModeAssumptions:
        """Seed-derived knobs; an override of None keeps the seed (except ``all_batch_rounds``)."""
        base: dict[str, Any] = {
            "first_round_share": seed_first_round_share(seeds),
            "throughput_per_hour": seed_throughput_per_hour(seeds),
            "batch_round_hours": _v(seeds, "spike_batch_round_s") / 3600,
            "chunks_per_page": seed_chunks_per_page(seeds),
            "request_bytes": _v(seeds, "spike_chunk_target_bytes"),
        }
        base.update({k: v for k, v in overrides.items() if v is not None or k == "all_batch_rounds"})
        return cls(**base)


def extractor_mode_usd(standard_usd: float, mode: str, *, first_round_share: float,
                       batch_multiplier: float) -> float:
    """Per-page extractor spend in ``mode`` from its all-live (standard) spend (130 a)."""
    if mode == NO_BATCH:
        return standard_usd
    if mode == ALL_BATCH:
        return standard_usd * batch_multiplier
    if mode == MIX:
        return standard_usd * (first_round_share * batch_multiplier + (1.0 - first_round_share))
    raise ValueError(f"mode must be one of {MODES}, got {mode!r}")


def batch_rounds(mode: str, a: ModeAssumptions) -> tuple[int, bool]:
    """(sequential batch rounds, rounds_is_lower_bound)."""
    if mode == NO_BATCH:
        return 0, False
    if mode == MIX:
        return a.mix_rounds, False
    if a.all_batch_rounds is None:
        return a.mix_rounds, True
    return a.all_batch_rounds, False


def batch_queue_mb(n: float, mode: str, pages_per_institution: float, a: ModeAssumptions) -> float:
    """Lower bound on the memory the first wave's queued requests hold (batch modes only)."""
    if mode == NO_BATCH:
        return 0.0
    return n * pages_per_institution * a.chunks_per_page * a.request_bytes / 1e6


def project_mode(per_inst: dict[str, Any], n: float, mode: str, a: ModeAssumptions) -> dict[str, Any]:
    """One mode's row: USD per API, total, wall hours and the batch-queue memory term.

    ``total_usd`` is None while a part is unknown (Stage 6 extractor or X35 without a
    figure); ``total_known_usd`` sums the known parts, with ``unpriced`` naming the rest.
    Both are None (``total_withheld``) when the per-page parts rest on the seed pages basis
    (``per_inst["pages_provisional"]``); the parts are then listed in ``provisional_parts``.
    Every batch-mode wall time is a lower bound (``wall_is_lower_bound``).
    """
    ext = extractor_mode_usd(per_inst["extractor_standard_usd"], mode,
                             first_round_share=a.first_round_share, batch_multiplier=a.batch_multiplier)
    usd_by = {
        "serper": n * per_inst["serper_usd"],
        "unlocker": n * per_inst["unlocker_usd"] * a.unlocker_factor,
        "typesafe": n * per_inst["typesafe_usd"],
        "openai": n * (per_inst.get("openai_usd") or 0.0),
        "anthropic_perpage": n * ext,
        "anthropic_stage6": None if per_inst.get("stage6_extractor_usd") is None
        else n * per_inst["stage6_extractor_usd"],
        "x35": None if per_inst.get("x35_usd") is None else n * per_inst["x35_usd"],
    }
    unpriced = [k for k, v in usd_by.items() if v is None]
    known = round(sum(v for v in usd_by.values() if v is not None), 2)
    withheld = bool(per_inst.get("pages_provisional"))
    rounds, rounds_lower = batch_rounds(mode, a)
    wall = n / a.throughput_per_hour + rounds * a.batch_round_hours
    return {
        "mode": mode,
        "usd": {k: (None if v is None else round(v, 2)) for k, v in usd_by.items()},
        "total_known_usd": None if withheld else known,
        "total_usd": None if (withheld or unpriced) else known,
        "total_withheld": withheld,
        "provisional_parts": list(PAGE_PARTS) if withheld else [],
        "unpriced": unpriced,
        "wall_hours": round(wall, 1),
        "batch_rounds": rounds,
        "rounds_is_lower_bound": rounds_lower,
        "wall_is_lower_bound": mode in BATCH_MODES,
        "batch_queue_mb_lower_bound": round(batch_queue_mb(n, mode, per_inst["pages_per_institution"], a)),
    }


def project_all(per_inst: dict[str, Any], n: float, a: ModeAssumptions) -> list[dict[str, Any]]:
    return [project_mode(per_inst, n, mode, a) for mode in MODES]


def standard_usd_from_tokens(part: dict[str, Any]) -> float:
    """All-live (standard) USD of an extractor part from its summed token counts.

    Uses the rate row's up-to-threshold tier: summed counts cannot say which requests
    were over the threshold (rare at the per-page chunk target). A part priced in any
    mode thus gets one comparable all-live figure, which :func:`extractor_mode_usd` then
    prices per mode.
    """
    row = pricing_for(part.get("model") or HAIKU_5_5_PRICING["model"])
    if row is None:
        raise ValueError(f"no rate row for extractor model {part.get('model')!r}")
    r = row.get("tiers", {}).get("up_to_threshold", row)

    def n(key: str) -> int:
        return int(part.get(key) or 0)

    return (usd(n("input_tokens"), r["standard_input_per_1m_usd"])
            + usd(n("cache_read_input_tokens"), r["standard_cached_input_per_1m_usd"])
            + usd(n("cache_creation_input_tokens"), r["standard_cache_write_5m_per_1m_usd"])
            + usd(n("output_tokens"), r["standard_output_per_1m_usd"]))


def per_institution_from_cost_report(report: dict[str, Any], n_smoke: int) -> dict[str, Any]:
    """Per-institution figures from a smoke run's ``_cost_report.json`` (v2.7).

    ``by_api`` gives Serper, Unlocker, TypeSafe (Stages 2/3) and OpenAI; ``v27_stage_cost``
    gives the per-page stage (jev to TypeSafe; the extractor re-priced all-live from its
    tokens) and Stage 6 (jev to TypeSafe; its extractor as reported, the quote step being
    live in every mode; X35 as reported, None while unpriced). A missing Stage 6 block
    leaves those parts unknown (None), never zero.
    """
    if n_smoke <= 0:
        raise ValueError("n_smoke must be positive")
    by_api = report.get("by_api") or {}

    def api(name: str) -> float:
        value = (by_api.get(name) or {}).get("usd")
        if value is None:
            raise ValueError(f"cost report has no USD for {name!r}")
        return float(value)

    v27 = report.get("v27_stage_cost") or {}
    perpage = (v27.get("perpage_v27") or {}).get("parts") or {}
    stage6 = v27.get("stage6_v27")
    if not perpage:
        raise ValueError("cost report has no v27_stage_cost.perpage_v27 block (not a v2.7 run?)")
    jev_pp = (perpage.get("jev") or {}).get("usd")
    if jev_pp is None:
        raise ValueError("per-page jev part is unpriced in the cost report")
    typesafe = api("typesafe") + float(jev_pp)
    s6_ext = s6_x35 = None
    if stage6:
        parts = stage6.get("parts") or {}
        jev6 = (parts.get("jev") or {}).get("usd")
        if jev6 is None:
            raise ValueError("Stage 6 jev part is unpriced in the cost report")
        typesafe += float(jev6)
        for name in ("extractor", "x35"):
            part = parts.get(name) or {}
            # a part with no calls cost nothing; one with calls and no USD stays unknown
            value = part.get("usd") if part.get("calls") else 0.0
            if name == "extractor":
                s6_ext = value
            else:
                s6_x35 = value
    ext = perpage.get("extractor") or {}
    return {
        # not in the cost report: the caller sets it (input, the smoke's events, or the seed)
        "pages_per_institution": None,
        "pages_provisional": False,
        "serper_usd": api("serper") / n_smoke,
        "unlocker_usd": api("brightdata_unlocker") / n_smoke,
        "typesafe_usd": typesafe / n_smoke,
        "openai_usd": api("openai") / n_smoke,
        "extractor_standard_usd": standard_usd_from_tokens(ext) / n_smoke,
        "stage6_extractor_usd": None if s6_ext is None else float(s6_ext) / n_smoke,
        "x35_usd": None if s6_x35 is None else float(s6_x35) / n_smoke,
        "extractor_calls": int(ext.get("calls") or 0),
        "extractor_batch_calls": int(ext.get("batch_calls") or 0),
        "basis": f"smoke cost report, n={n_smoke}",
    }


def remaining_envelope(recorded_usd: float | None, wave5_resume_usd: float | None,
                       envelope_usd: float) -> float | None:
    """``envelope - recorded - wave-5 resume``; None while either input is unknown (no default).

    ``recorded_usd`` is on the recompute basis (PI ruling Q176 b: the Unlocker undercount
    of the cost report corrected), not the raw cost report.
    """
    if recorded_usd is None or wave5_resume_usd is None:
        return None
    return round(envelope_usd - recorded_usd - wave5_resume_usd, 2)


def table_notes(per_inst: dict[str, Any], seeds: Seeds | None, rows: Sequence[dict[str, Any]],
                a: ModeAssumptions) -> list[str]:
    """Footer lines naming the pages basis and the wall-time caveats."""
    notes = [f"pages basis: {per_inst.get('pages_basis') or 'unstated'}"]
    if any(r.get("total_withheld") for r in rows):
        notes.append("* rests on the seed pages basis: total withheld (give --pages-per-institution "
                     "to scripts/project_run_cost.py for a total)")
    if any(r.get("wall_is_lower_bound") for r in rows):
        if seeds is not None and a.batch_round_hours == _v(seeds, "spike_batch_round_s") / 3600:
            src = (f"a {_v(seeds, 'spike_batch_requests'):.0f}-request spike round trip "
                   f"({_v(seeds, 'spike_batch_round_s'):.0f} s) per round")
        else:
            src = f"an operator round trip of {a.batch_round_hours:g} h per round"
        notes.append(f">= batch-mode wall time is a lower bound: it adds {src}; the batch round trip "
                     "is unmeasured at wave scale (up to the API's 24 h per batch), and the "
                     "throughput is the v2.5 instrument's")
    return notes


def format_table(rows: list[dict[str, Any]], n: float, notes: Sequence[str] = ()) -> str:
    """A short fixed-width table of :func:`project_all` rows, then ``notes``."""
    cols = ("serper", "unlocker", "typesafe", "anthropic_perpage", "anthropic_stage6", "x35")
    head = ["mode", "serper", "unlocker", "typesafe", "anth_pp", "anth_s6", "x35",
            "total_known", "wall_h", "queue_MB"]
    lines = [f"Projection for n={int(n):,} institutions (ESTIMATES; USD)",
             "  ".join(f"{h:>11}" for h in head)]
    for r in rows:
        mark = set(r.get("provisional_parts") or ())
        cells = [r["mode"]]
        for c in cols:
            v = r["usd"][c]
            cells.append("unpriced" if v is None else f"{v:.2f}{'*' if c in mark else ''}")
        queue = r["batch_queue_mb_lower_bound"]
        cells += [
            "withheld" if r.get("total_withheld") else f"{r['total_known_usd']:.2f}",
            f"{'>=' if r['wall_is_lower_bound'] else ''}{r['wall_hours']:.1f}",
            f"{queue:,}{'*' if mark and queue else ''}",
        ]
        lines.append("  ".join(f"{c:>11}" for c in cells))
    lines += list(notes)
    return "\n".join(lines)


__all__ = [
    "ALL_BATCH", "BATCH_MODES", "DRIVE_ENV", "MIX", "MODES", "NO_BATCH", "PAGE_PARTS",
    "REQUIRED_SEEDS", "SEEDS_ENV",
    "ModeAssumptions", "Seed", "SeedsUnavailable", "batch_queue_mb", "batch_rounds",
    "extractor_mode_usd", "format_table", "load_seeds", "per_institution_from_cost_report",
    "project_all", "project_mode", "remaining_envelope", "resolve_seeds_path",
    "seed_chunks_per_page", "seed_first_round_share", "seed_pages_basis",
    "seed_pages_per_institution", "seed_per_institution", "seed_throughput_per_hour",
    "standard_usd_from_tokens", "table_notes",
]
