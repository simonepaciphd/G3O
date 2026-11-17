"""T-041 fixture runner: the T-040 v2.7 fixtures through the new-run entry point (PI Q184 a).

Q184 a (2026-11-16) narrows T-041 to the new-run path's A-IDs plus the X35 agreement
check (RC-D-038 139 a); back-fill, transfer and the real-id subset move after T-035.
So the transfer fixtures (``transfers.json``, A-022) are never selected here.

Two modes:

- **dry run (the default)**: no network, no paid call, no client built. Loads and
  validates the fixtures (real pages are read from the Drive store named in each
  ``page_ref`` and their text hash checked), builds the per-fixture plan and prints a
  call-count and token-count estimate with the cited pricing rows of
  :mod:`g3o.common.pricing`. A USD figure is printed only from the projection seeds
  (:mod:`g3o.common.run_projection`, PI Q177 a; each seed carries its own citation);
  without a seeds file no USD estimate is printed. No rate or volume is invented here.
- **live** (``--live``): real calls, run by the PI (red line 4). Refused unless every
  gate of a real v2.7 run passes: the dispatch is built by
  :func:`g3o.run.presweep.v27_entry.build_v27_dispatch` and checked by
  ``orchestrator._require_v27_dispatch`` unchanged (codebook / binding pins, the X35
  wording pin and probability source, ruling 36 a on the default per-page builder,
  the credentials). The extractor mode is forced to ``no_batch`` (DP-030 / RC-D-001 B:
  extractor calls in T-041 are sync). A USD cap (``--max-usd``) is required. The cap is
  SOFT: it is checked between fixtures, so the run stops before the next fixture once the
  journaled spend reaches it, and a single fixture can overshoot it by its own cost.

Each fixture runs in its own run directory, so every journaled call and every X35
call is attributed to one fixture. Expected vs got is compared per expected value and
summarised per A-ID; X35 answers and stated probabilities are recorded per fixture.

Injected-mode fixtures carry given page- or part-level answers and exercise only
deterministic code (``tests/fixtures/v27/build_synthetic.py`` docstring). No adapter
plays those answers into the pipeline yet, so they are planned at zero calls and
reported ``not_run`` with that reason (proposed question in the T-041 runner report).
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import math
import os
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DRIVE_ENV = "G3O_DRIVE_ROOT"
#: Default output folder under the Drive root (PLAN T-041 Outputs).
OUT_SUBDIR = "agent-workspace/2026-10-27-reclass-plan/fixture-run"
#: Run modes; each writes its own output files (review M2: a dry run never overwrites live results).
MODE_DRY, MODE_LIVE = "dry-run", "live"
OUTPUT_NAMES = {
    MODE_DRY: {"plan": "t041-dry-plan.json", "results": "t041-dry-results.json", "report": "T041-REPORT-dry.md"},
    MODE_LIVE: {"plan": "t041-live-plan.json", "results": "t041-live-results.json", "report": "T041-REPORT-live.md",
                "jsonl": "t041-live-fixtures.jsonl"},
}

#: Fixture groups the runner can select (Q184 a: the new-run path only).
GROUP_PIPELINE = "pipeline"  # synthetic, mode pipeline: page text through jev / extractor
GROUP_INJECTED = "injected"  # synthetic, mode injected: given answers, deterministic code only
GROUP_REAL = "real"  # real.json: stored real pages through the new-run path
GROUPS = (GROUP_PIPELINE, GROUP_INJECTED, GROUP_REAL)
#: Fixture kinds never run here (Q184 a: the transfer path moves after T-035).
EXCLUDED_KINDS = frozenset({"real_transfer"})

#: Expected-value outcomes.
PASS, FAIL, NOT_LOCATED = "pass", "fail", "not_located"
#: Per-fixture / per-A-ID outcomes beyond pass / fail. ``partial``: some values passed, the
#: others were not located, none failed (review M5; distinct from ``pass``).
PARTIAL, UNRESOLVED, NOT_RUN = "partial", "unresolved", "not_run"
#: Column order of the per-A-ID table.
A_ID_STATUSES = (PASS, PARTIAL, FAIL, UNRESOLVED, NOT_RUN)
#: The roll-up caveat the report carries (proposed question on the meaning of the roll-up).
A_ID_ROLLUP_NOTE = ("every A-ID of a fixture shares that fixture's whole set of expected values: the fixture "
                    "format ties expected values to the fixture, not to one A-ID, so an A-ID's status here is "
                    "its fixtures' status, not a test of that A-ID alone")
#: How a not-located expected value counts (``--unlocated``); default: it decides nothing.
UNLOCATED_POLICIES = (UNRESOLVED, FAIL)
#: Which fixture pages are the searched pages (``--searched-pages``); the rest are served to the
#: T-025 follow leg from the fixture. Default: a page no other fixture page links to is searched.
SEARCHED_UNLINKED, SEARCHED_ALL = "unlinked", "all"
SEARCHED_POLICIES = (SEARCHED_UNLINKED, SEARCHED_ALL)
#: The official site a fixture run records (``--official-site``). Default: the searched page's host.
OFFICIAL_PAGE_HOST, OFFICIAL_NONE = "page-host", "none"
OFFICIAL_POLICIES = (OFFICIAL_PAGE_HOST, OFFICIAL_NONE)

#: The two known limits of the calibrated quote match (PLAN T-041 progress note, RC-D-021 R-6 a).
QUOTE_MATCH_LIMITS = (
    "A curly apostrophe on the page against a straight one in the quote (or the reverse) is not matched "
    "(RC-D-017 1a; PLAN T-041, RC-D-021 R-6 a).",
    "A quote cut inside an unspaced CJK or Thai run is not matched (RC-D-017 1a; PLAN T-041, RC-D-021 R-6 a).",
)
#: The T-064 line the T-041 report keeps (PLAN T-064 Verification: DP-064e, no fixtures).
#: The cap is checked between fixtures only (help text, printed plan and report say so).
CAP_NOTE = ("the --max-usd cap is soft: it is checked between fixtures, so a single fixture can overshoot "
            "it by its own cost")
#: What the up-front seed check covers (printed in the plan).
SEED_CHECK_NOTE = ("the up-front seed check covers the extractor and jev seed scale only; it excludes X35 and the "
                   "Stage 6 quote step (no seed for either)")
F6C_LINE = ("F6 c: calendar years untested. The calendar and fiscal-year conversion of year candidates "
            "(T-064) has no fixture (DP-064e), so this run does not test it.")


class RunRefused(RuntimeError):
    """A live run refused before any call (a gate did not pass)."""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def drive_root(explicit: str | os.PathLike[str] | None = None,
               environ: Mapping[str, str] | None = None) -> Path | None:
    """The G3O Drive root from ``explicit`` or ``$G3O_DRIVE_ROOT``; None when neither is set."""
    env = os.environ if environ is None else environ
    raw = explicit if explicit is not None else env.get(DRIVE_ENV)
    return Path(raw) if raw else None


def default_out_dir(drive: Path | None) -> Path | None:
    return None if drive is None else drive / OUT_SUBDIR


def default_run_base() -> Path:
    """Where live fixture run directories go by default: a local, non-synced folder under the
    user's home (``~/.g3o/t041-runs``), resolved at run time. Reports stay in ``--out-dir``."""
    return Path.home() / ".g3o" / "t041-runs"


def utc_stamp(now: datetime | None = None) -> str:
    """A UTC timestamp for one live invocation's run root (``20261117T031500Z``)."""
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def fresh_run_root(base: Path, stamp: str) -> Path:
    """Create ``<base>/<stamp>`` for one live invocation; refuse if it exists, so a re-run never
    reuses a run directory (its journals would be replayed and its spend counted twice)."""
    root = Path(base) / stamp
    if root.exists():
        raise RunRefused(f"run root already exists: {root} (a live run never reuses a run directory)")
    root.mkdir(parents=True)
    return root


def load_fixtures(fix_dir: Path) -> list[dict[str, Any]]:
    """Every fixture of ``synthetic.json`` and ``real.json`` (transfers are not loaded: Q184 a)."""
    out: list[dict[str, Any]] = []
    for name in ("synthetic.json", "real.json"):
        path = fix_dir / name
        if path.exists():
            out += json.loads(path.read_text(encoding="utf-8"))["fixtures"]
    return out


def fixture_group(fixture: Mapping[str, Any]) -> str | None:
    """``pipeline`` / ``injected`` / ``real``, or None for a kind this runner never runs."""
    kind = fixture.get("kind")
    if kind in EXCLUDED_KINDS:
        return None
    if kind == "real":
        return GROUP_REAL
    if kind == "synthetic" and fixture.get("mode") in (GROUP_PIPELINE, GROUP_INJECTED):
        return str(fixture["mode"])
    return None


def select_fixtures(fixtures: Iterable[Mapping[str, Any]], groups: Iterable[str] = GROUPS,
                    ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """The fixtures of ``groups`` (and of ``ids`` when given), in file order."""
    wanted = set(groups)
    unknown = wanted - set(GROUPS)
    if unknown:
        raise ValueError(f"unknown fixture group(s) {sorted(unknown)}; choose from {list(GROUPS)}")
    id_set = set(ids) if ids else None
    out = [dict(f) for f in fixtures if fixture_group(f) in wanted
           and (id_set is None or f["fixture_id"] in id_set)]
    if id_set is not None:
        missing = id_set - {f["fixture_id"] for f in out}
        if missing:
            raise ValueError(f"--fixture id(s) not among the selected groups: {sorted(missing)}")
    return out


def validate_fixture(fixture: Mapping[str, Any]) -> list[str]:
    """Structural problems of one fixture (empty list: none)."""
    problems = []
    for key in ("fixture_id", "kind", "a_ids", "institution", "expected"):
        if key not in fixture:
            problems.append(f"missing {key}")
    if not fixture.get("a_ids"):
        problems.append("no a_ids")
    for k, e in enumerate(fixture.get("expected") or ()):
        if not {"item", "scope", "value"} <= set(e):
            problems.append(f"expected[{k}] lacks item/scope/value")
    group = fixture_group(fixture)
    if group in (GROUP_PIPELINE, GROUP_INJECTED) and not fixture.get("pages"):
        problems.append("synthetic fixture has no pages")
    if group == GROUP_INJECTED and "injected" not in fixture:
        problems.append("injected fixture has no injected answers")
    if group == GROUP_REAL and not (fixture.get("page_ref") or fixture.get("page_refs")):
        problems.append("real fixture has no page_ref")
    return problems


def load_fixture_text_module(fix_dir: Path) -> Any:
    """``tests/fixtures/v27/fixture_text.py`` (synthetic filler text), loaded by path as T-040 does."""
    spec = importlib.util.spec_from_file_location("t041_fixture_text", fix_dir / "fixture_text.py")
    if spec is None or spec.loader is None:
        raise FileNotFoundError(fix_dir / "fixture_text.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def real_refs(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [fixture["page_ref"]] if "page_ref" in fixture else list(fixture.get("page_refs") or ())


def load_real_record(ref: Mapping[str, Any], drive: Path) -> dict[str, Any]:
    """The stored scrape record of one real page; its text hash (and tar member hash) checked.

    Same reading as ``fixture_text.load_real_text`` (JSONL line or tar member, read in
    memory, never extracted), but the whole record is kept (url, title, fetch metadata).
    Raises ValueError on a hash mismatch.
    """
    path = drive / ref["store"]
    if "member" in ref:
        import gzip
        import tarfile

        with tarfile.open(path) as tf:
            member = tf.extractfile(ref["member"])
            if member is None:
                raise ValueError(f"tar member not found: {ref['member']}")
            raw = member.read()
        if hashlib.sha256(raw).hexdigest() != ref["member_sha256"]:
            raise ValueError(f"member hash mismatch for {ref['member']}")
        data = gzip.decompress(raw) if ref["member"].endswith(".gz") else raw
        record = json.loads(data.decode("utf-8", errors="replace"))
    else:
        with path.open(encoding="utf-8") as stream:
            for n, line in enumerate(stream, start=1):
                if n == ref["line_1based"]:
                    record = json.loads(line)["source_record"]
                    break
            else:
                raise ValueError(f"{ref['store']} has no line {ref['line_1based']}")
    text = record.get("text") or ""
    got = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if got != ref["text_sha256"]:
        raise ValueError(f"text hash mismatch for {ref.get('page_id') or ref.get('url')}: {got}")
    return dict(record)


def fixture_pages(fixture: Mapping[str, Any], *, fixture_text: Any = None,
                  drive: Path | None = None) -> list[dict[str, Any]]:
    """The fixture's pages as ``{page_key, url, title, text|None, fetch_ok, links, chrome_text, record}``.

    Synthetic text is assembled by ``fixture_text.page_text`` (filler parts included);
    real text is read from the Drive store (None when no Drive root is given).
    """
    out = []
    if fixture_group(fixture) == GROUP_REAL:
        for k, ref in enumerate(real_refs(fixture)):
            record = load_real_record(ref, drive) if drive is not None else None
            out.append({"page_key": f"r{k}", "url": ref.get("url") or (record or {}).get("url"),
                        "title": (record or {}).get("title", ""),
                        "text": None if record is None else record.get("text") or "",
                        "fetch_ok": True, "links": (record or {}).get("links"),
                        "chrome_text": (record or {}).get("chrome_text"), "record": record})
        return out
    for p in fixture.get("pages") or ():
        if "text" in p:
            text = p["text"]
        elif fixture_text is not None:
            text = fixture_text.page_text(p)
        else:
            text = None
        out.append({"page_key": p["page_key"], "url": p["url"], "title": p.get("title", ""), "text": text,
                    "fetch_ok": p.get("fetch_status") == "ok", "links": list(p.get("links") or ()),
                    "chrome_text": p.get("chrome_text"), "record": None})
    return out


def searched_page_keys(pages: Sequence[Mapping[str, Any]], policy: str = SEARCHED_UNLINKED) -> list[str]:
    """The page keys entering the run as searched pages; the others are only reachable by following."""
    if policy not in SEARCHED_POLICIES:
        raise ValueError(f"searched-pages policy must be one of {SEARCHED_POLICIES}")
    if policy == SEARCHED_ALL:
        return [p["page_key"] for p in pages]
    linked = {link.get("url") for p in pages for link in (p.get("links") or ()) if isinstance(link, Mapping)}
    return [p["page_key"] for p in pages if p["url"] not in linked]


# ---------------------------------------------------------------------------
# Plan and estimate (dry run)
# ---------------------------------------------------------------------------


def _token_estimator() -> Any:
    from g3o.common.page_chunks import TokenEstimator

    return TokenEstimator()


def plan_fixture(fixture: Mapping[str, Any], pages: Sequence[Mapping[str, Any]], *,
                 searched_policy: str = SEARCHED_UNLINKED, chunk_target_bytes: float | None = None,
                 estimator: Any = None) -> dict[str, Any]:
    """One fixture's plan: its pages, searched pages, page-text tokens and lower-bound call counts.

    Calls are LOWER BOUNDS from the page text alone: one jev page round, one extractor
    pass-1 and one pass-2 request per chunk of a searched, fetched page (the spike's
    one-request-per-chunk legs, SPIKE-T002 J-P1R1 / H-SPAN / H-PQ). Activity follow-ups,
    halvings, followed pages, the Stage 6 quote step and X35 depend on the answers and
    are not countable before the run. Chunks need ``chunk_target_bytes`` (a seed); without
    it each page counts as one chunk (a floor). Injected fixtures plan zero calls.
    """
    group = fixture_group(fixture)
    est = estimator if estimator is not None else _token_estimator()
    searched = set(searched_page_keys(pages, searched_policy))
    page_rows, chunks_total, tokens_total, unknown = [], 0, 0, []
    for p in pages:
        coded = group != GROUP_INJECTED and p["page_key"] in searched and p["fetch_ok"]
        text = p.get("text")
        row: dict[str, Any] = {"page_key": p["page_key"], "url": p["url"], "searched": p["page_key"] in searched,
                               "fetch_ok": p["fetch_ok"], "coded": coded}
        if text is None:
            row.update(bytes=None, text_tokens=None, chunks=None)
            if coded:
                unknown.append(p["page_key"])
        else:
            n_bytes = len(text.encode("utf-8"))
            chunks = max(1, math.ceil(n_bytes / chunk_target_bytes)) if chunk_target_bytes else 1
            row.update(bytes=n_bytes, text_tokens=est.tokens(text), chunks=chunks)
            if coded:
                chunks_total += chunks
                tokens_total += row["text_tokens"]
        page_rows.append(row)
    runnable = group in (GROUP_PIPELINE, GROUP_REAL)
    return {
        "fixture_id": fixture["fixture_id"], "group": group, "a_ids": list(fixture["a_ids"]),
        "runnable": runnable,
        "not_run_reason": None if runnable else "injected answers: no adapter plays them into the pipeline yet",
        "pages": page_rows,
        "coded_pages": sum(1 for r in page_rows if r["coded"]),
        "chunks_lower_bound": chunks_total if runnable else 0,
        "page_text_tokens": tokens_total if runnable else 0,
        "pages_text_unavailable": unknown,
        "calls_lower_bound": ({"jev_page_round": chunks_total, "extractor_pass1": chunks_total,
                               "extractor_pass2": chunks_total} if runnable else
                              {"jev_page_round": 0, "extractor_pass1": 0, "extractor_pass2": 0}),
        "n_expected": len(fixture["expected"]),
    }


def pricing_rows(models: Iterable[str]) -> list[dict[str, Any]]:
    """The cited rate rows of :mod:`g3o.common.pricing` for ``models`` (None-priced models flagged)."""
    from g3o.common.pricing import pricing_for

    out = []
    for model in models:
        row = pricing_for(model)
        if row is None:
            out.append({"model": model, "priced": False})
            continue
        out.append({"model": model, "priced": True, "source": row.get("source"),
                    "verified_on": row.get("verified_on"),
                    "standard_input_per_1m_usd": row.get("standard_input_per_1m_usd"),
                    "standard_output_per_1m_usd": row.get("standard_output_per_1m_usd")})
    return out


def estimate(plans: Sequence[Mapping[str, Any]], *, jev_model: str, extractor_model: str, x35_model: str,
             seeds: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Call and token counts over the plans, the cited rate rows, and a USD figure only from seeds.

    ``page_text_input_floor_usd``: the page text alone, read once by each lower-bound call,
    at the standard input rates of the rate rows (sync: DP-030). Prompts, instructions,
    outputs and every uncountable call come on top, so it is a floor, not an estimate.

    ``seed_usd`` (only with seeds): coded pages x the spike's per-page sync Haiku cost
    (H-SPAN + H-PQ + H-AQ) and per-page jev cost, each seed with its own citation. The
    spike asked proxy questions, so this is a scale, not a v2.7 estimate; the Stage 6
    quote step and X35 have no seed and stay unpriced.
    """
    from g3o.common.pricing import pricing_for, usd

    runnable = [p for p in plans if p["runnable"]]
    calls = {k: sum(p["calls_lower_bound"][k] for p in runnable)
             for k in ("jev_page_round", "extractor_pass1", "extractor_pass2")}
    tokens = sum(p["page_text_tokens"] for p in runnable)
    pages = sum(p["coded_pages"] for p in runnable)
    jev_row, ext_row = pricing_for(jev_model), pricing_for(extractor_model)
    floor = None
    if jev_row is not None and ext_row is not None:
        floor = (usd(tokens, jev_row["standard_input_per_1m_usd"])
                 + 2 * usd(tokens, ext_row["standard_input_per_1m_usd"]))
    out: dict[str, Any] = {
        "fixtures_planned": len(plans), "fixtures_runnable": len(runnable),
        "fixtures_not_run": [p["fixture_id"] for p in plans if not p["runnable"]],
        "coded_pages": pages, "page_text_tokens": tokens, "calls_lower_bound": calls,
        "pages_text_unavailable": {p["fixture_id"]: p["pages_text_unavailable"] for p in runnable
                                   if p["pages_text_unavailable"]},
        "pricing_rows": pricing_rows([jev_model, extractor_model, x35_model]),
        "extractor_rate_basis": "standard (sync; DP-030 / RC-D-001 B)",
        "page_text_input_floor_usd": floor,
        "uncounted": ["activity follow-up requests", "halvings", "followed pages", "Stage 6 jev and quote step",
                      "X35 calls", "prompt and instruction tokens", "output tokens"],
        "seed_usd": None,
        "seed_usd_note": "no seeds file: no USD estimate is printed (none exists without one)",
    }
    if seeds:
        def v(name: str) -> Any:
            return seeds[name]

        spike_pages = v("spike_pages").value
        haiku = v("spike_h_span_usd").value + v("spike_h_pq_usd").value + v("spike_h_aq_usd").value
        out["seed_usd"] = {
            "extractor_sync_usd": pages * haiku / spike_pages,
            "jev_usd": pages * v("spike_jev_usd").value / spike_pages,
            "stage6_quote_step_usd": None, "x35_usd": None,
            "formula": "coded_pages x (spike_h_span_usd + spike_h_pq_usd + spike_h_aq_usd) / spike_pages; "
                       "coded_pages x spike_jev_usd / spike_pages",
            "citations": {name: v(name).source for name in
                          ("spike_pages", "spike_h_span_usd", "spike_h_pq_usd", "spike_h_aq_usd", "spike_jev_usd")},
        }
        out["seed_usd_note"] = ("spike proxy (SPIKE-T002 asked proxy questions; not a v2.7 estimate); Stage 6 "
                                "quote step and X35 unpriced (no basis)")
    return out


def format_estimate(est: Mapping[str, Any]) -> str:
    lines = [
        f"fixtures: {est['fixtures_planned']} planned, {est['fixtures_runnable']} runnable, "
        f"{len(est['fixtures_not_run'])} not run (injected: no adapter)",
        f"coded pages: {est['coded_pages']}; page-text tokens (TokenEstimator, DP-007 margins): "
        f"{est['page_text_tokens']}",
        "calls (lower bound): " + ", ".join(f"{k} {n}" for k, n in est["calls_lower_bound"].items()),
        "uncounted: " + "; ".join(est["uncounted"]),
        f"extractor rates: {est['extractor_rate_basis']}",
    ]
    for row in est["pricing_rows"]:
        if row["priced"]:
            lines.append(f"rate row {row['model']}: input ${row['standard_input_per_1m_usd']}/MTok, output "
                         f"${row['standard_output_per_1m_usd']}/MTok (g3o/common/pricing.py; {row['source']}, "
                         f"verified {row['verified_on']})")
        else:
            lines.append(f"rate row {row['model']}: NOT PRICED (no row in g3o/common/pricing.py)")
    floor = est["page_text_input_floor_usd"]
    lines.append("page-text input floor: " + ("unpriced" if floor is None else f"${floor:.4f}")
                 + " (page text only; not an estimate)")
    seed = est["seed_usd"]
    if seed is None:
        lines.append(f"USD estimate: none. {est['seed_usd_note']}")
    else:
        lines.append(f"USD scale from seeds: extractor ${seed['extractor_sync_usd']:.4f}, jev ${seed['jev_usd']:.4f}; "
                     "Stage 6 quote step and X35 unpriced")
        lines.append(f"  formula: {seed['formula']}")
        lines.extend(f"  {k}: {src}" for k, src in seed["citations"].items())
        lines.append(f"  note: {est['seed_usd_note']}")
    lines.append(f"cap: {CAP_NOTE}")
    lines.append(f"seed check: {SEED_CHECK_NOTE}")
    if est["pages_text_unavailable"]:
        lines.append(f"page text unavailable (set {DRIVE_ENV}): {est['pages_text_unavailable']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Expected vs got
# ---------------------------------------------------------------------------


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    return value


def _row_values(row: Mapping[str, Any]) -> Mapping[str, Any]:
    values = row.get("values")
    return values if isinstance(values, Mapping) else {}


def locate_got(storage: Mapping[str, Any] | None, expected: Mapping[str, Any],
               page_urls: Mapping[str, str]) -> tuple[bool, Any]:
    """``(found, value)`` of one expected value in a ``6_storage.json`` document.

    Scopes: ``institution`` -> the summary row's values; ``page`` / ``page:<key>`` ->
    the source row whose values carry that page's URL; ``activity`` / ``activity:<name>``
    -> the activity row named so (``core.activity_name``), or the only activity row.
    Any other scope (``pair``, run telemetry such as ``followed_urls``) is not located:
    no reader is defined for it here.
    """
    if not storage:
        return False, None
    item, scope = expected["item"], str(expected["scope"])
    kind, _, name = scope.partition(":")
    rows: list[Mapping[str, Any]] = []
    if kind == "institution":
        rows = [storage.get("summary") or {}]
    elif kind == "page":
        url = page_urls.get(name) if name else (next(iter(page_urls.values())) if len(page_urls) == 1 else None)
        if url is not None:
            rows = [r for r in (storage.get("sources") or {}).values()
                    if url in {v for v in _row_values(r).values() if isinstance(v, str)}]
    elif kind == "activity":
        acts = list((storage.get("activities") or {}).values())
        if name:
            rows = [r for r in acts if _row_values(r).get("core.activity_name") == name]
        if not rows and len(acts) == 1:
            rows = acts
    for row in rows:
        values = _row_values(row)
        if item in values:
            return True, values[item]
    return False, None


def compare_fixture(fixture: Mapping[str, Any], got: Callable[[Mapping[str, Any]], tuple[bool, Any]],
                    *, unlocated: str = UNRESOLVED) -> dict[str, Any]:
    """Per expected value ``pass`` / ``fail`` / ``not_located``, and per A-ID a status.

    Fixture status (review M5): ``fail`` when any value failed (or, with
    ``unlocated='fail'``, any was not located); ``pass`` only when EVERY value passed;
    ``partial`` when some passed and the rest were not located; ``unresolved`` when none
    was located (or the fixture has no expected value). Every A-ID of the fixture gets the
    fixture's status: the fixture format ties expected values to the fixture, not to one
    A-ID (:data:`A_ID_ROLLUP_NOTE`); no finer mapping is invented here.
    """
    if unlocated not in UNLOCATED_POLICIES:
        raise ValueError(f"unlocated policy must be one of {UNLOCATED_POLICIES}")
    rows = []
    for k, e in enumerate(fixture["expected"]):
        found, value = got(e)
        status = (PASS if _norm(value) == _norm(e["value"]) else FAIL) if found else NOT_LOCATED
        rows.append({"index": k, "item": e["item"], "scope": e["scope"], "expected": e["value"],
                     "got": value if found else None, "status": status})
    statuses = {r["status"] for r in rows}
    if FAIL in statuses or (unlocated == FAIL and NOT_LOCATED in statuses):
        overall = FAIL
    elif statuses == {PASS}:
        overall = PASS
    elif PASS in statuses:
        overall = PARTIAL
    else:
        overall = UNRESOLVED
    return {"fixture_id": fixture["fixture_id"], "expected": rows, "status": overall,
            "a_ids": {a: overall for a in fixture["a_ids"]}}


def not_run_result(fixture: Mapping[str, Any], reason: str) -> dict[str, Any]:
    return {"fixture_id": fixture["fixture_id"], "status": NOT_RUN, "reason": reason,
            "a_ids": {a: NOT_RUN for a in fixture["a_ids"]},
            "expected": [{"index": k, "item": e["item"], "scope": e["scope"], "expected": e["value"],
                          "got": None, "status": NOT_RUN} for k, e in enumerate(fixture["expected"])]}


def a_id_summary(results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Per A-ID, the number of fixtures in each status."""
    out: dict[str, dict[str, int]] = {}
    for r in results:
        for a, status in r["a_ids"].items():
            bucket = out.setdefault(a, {})
            bucket[status] = bucket.get(status, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# X35 recording
# ---------------------------------------------------------------------------


def journal_x35_calls(run_dir: Path) -> list[dict[str, Any]]:
    """Every X35 call journaled in one fixture's run directory, read from the request journals.

    Review M4: the journals are the record of the X35 calls (``RequestJournal._entail``,
    ``stage_validate_v27.py``): an ``x35`` entry holds the answer (``value``) and stated
    ``probability``; an X35 non-answer (PI ruling Q169 b) is an ``x35`` entry with value
    ``support_check.X35_NON_ANSWER``, probability ``None`` and a ``non_answer`` field; an
    ``x35_failed`` entry is a call that came back with a billed response but no answer.
    An ``x35_failed`` entry carrying the old no-response marker is read as absent, as
    ``RequestJournal`` reads it (PI ruling Q163 c). The same calls ``RequestJournal.x35_usages``
    prices, so the summary and the cost agree. Each live invocation has a fresh run root
    (:func:`fresh_run_root`), so no entry comes from an earlier run. A torn final line is
    skipped (PI ruling 131.2 a); a corrupt middle line raises ``ValueError``.
    """
    from g3o.common.paths import iter_institution_dirs
    from g3o.run.presweep import stage_perpage_v27 as spv
    from g3o.run.presweep import stage_validate_v27 as svv

    calls: list[dict[str, Any]] = []
    for inst_dir in iter_institution_dirs(Path(run_dir)):
        for work_dir, name in ((spv.WORK_DIR, spv.JOURNAL), (svv.WORK_DIR, svv.JOURNAL)):
            path = inst_dir / work_dir / name
            if not path.is_file():
                continue
            lines = path.read_bytes().split(b"\n")
            for n, line in enumerate(lines):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    if n == len(lines) - 1:  # torn final record
                        break
                    raise ValueError(f"corrupt journal line {n + 1}: {work_dir}/{name}") from None
                kind, response = entry.get("kind"), entry.get("response") or {}
                if kind == "x35":
                    calls.append({"answer": response.get("value"), "probability": response.get("probability"),
                                  "non_answer": "non_answer" in response, "failed": False})
                elif kind == "x35_failed" and response.get(svv.X35_USAGE_ABSENT) != svv.X35_NO_RESPONSE:
                    calls.append({"answer": None, "probability": None, "non_answer": False, "failed": True})
    return calls


def x35_summary(calls: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """X35 agreement and the spread of stated probabilities over one fixture's calls
    (:func:`journal_x35_calls`).

    Agreement (default definition, proposed question P2): the share of X35 calls answering
    ``true``, i.e. X35 agreeing that the quote supports the extractor's code. ``n_other``
    counts every call that is neither ``true`` nor ``false``: the non-answers
    (``n_non_answer``, PI ruling Q169 b) and the failed calls (``n_failed``) included.
    """
    n = len(calls)
    probs = sorted(float(c["probability"]) for c in calls
                   if isinstance(c.get("probability"), (int, float)) and not isinstance(c.get("probability"), bool))
    n_true = sum(1 for c in calls if c.get("answer") == "true")
    n_false = sum(1 for c in calls if c.get("answer") == "false")
    return {
        "n_calls": n, "n_true": n_true, "n_false": n_false,
        "n_other": n - n_true - n_false,
        "n_non_answer": sum(1 for c in calls if c.get("non_answer")),
        "n_failed": sum(1 for c in calls if c.get("failed")),
        "agreement": (n_true / n) if n else None,
        "n_probability_missing": n - len(probs),
        "probability_min": probs[0] if probs else None,
        "probability_median": statistics.median(probs) if probs else None,
        "probability_max": probs[-1] if probs else None,
        "n_below_0_8": sum(1 for p in probs if p < 0.8),
    }


# ---------------------------------------------------------------------------
# Live run (PAID; run by the PI)
# ---------------------------------------------------------------------------


def require_live_gates(dispatch: Any) -> Any:
    """Refuse unless the dispatch passes every gate of a real v2.7 run; then force sync mode.

    The unwrapped dispatch goes through ``orchestrator._require_v27_dispatch`` unchanged
    (it refuses the X35 stub, the binding pins and ruling 36 a). Only then is the
    extractor mode set to ``no_batch`` (DP-030 / RC-D-001 B).
    """
    from g3o.common import support_check
    from g3o.run.presweep.orchestrator import _require_v27_dispatch

    if dispatch.entail_fn is support_check.run_entailment:
        raise RunRefused("X35 is refused (support_check.run_entailment): the X35 wording pin or probability "
                         "source gate is not open (Q159 a / Q160)")
    _require_v27_dispatch(dispatch)
    return force_sync(dispatch)


def force_sync(dispatch: Any) -> Any:
    """The dispatch with every per-page extractor call live (``no_batch``; DP-030 / RC-D-001 B)."""
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    out = dataclasses.replace(dispatch, extractor_mode=NO_BATCH)
    if out.extractor_mode != NO_BATCH:  # pragma: no cover - dataclasses.replace guarantees it
        raise RunRefused("extractor mode is not no_batch")
    return out


def fixture_institution_row(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """The master-row shape of a fixture institution (``records.institution_record`` reads it)."""
    inst = fixture["institution"]
    raw = str(inst["institution_id"])
    master = raw[len("INST-"):] if raw.startswith("INST-") else raw
    return {"master_row_id": master, "institution_name": inst.get("name", ""), "country": inst.get("country", ""),
            "government_level": inst.get("level", ""), "branch": inst.get("branch", "")}


def fixture_uid(institution_id: str) -> str:
    tail = institution_id.rsplit("-", 1)[-1]
    if tail.isdigit():
        return f"G3O-I-{int(tail):08d}"
    return f"G3O-I-{int(hashlib.sha256(institution_id.encode('utf-8')).hexdigest()[:8], 16) % 10**8:08d}"


def _rendered(page: Mapping[str, Any], access_date: str) -> Any:
    from g3o.scrape.render import FetchMetadata, RenderedPage

    record = page.get("record")
    if record is not None:  # a stored real page: its own record, verbatim
        return RenderedPage.model_validate(record)
    return RenderedPage(url=page["url"], text=page["text"] or "", title=page.get("title") or "",
                        content_type="html",
                        fetch_metadata=FetchMetadata(access_date=access_date, fetch_method="html"),
                        chrome_text=page.get("chrome_text"), links=list(page.get("links") or ()),
                        email_links=[], metadata_dates=[])


def materialise(run_dir: Path, fixture: Mapping[str, Any], pages: Sequence[Mapping[str, Any]], *,
                searched_policy: str, official_policy: str, access_date: str) -> tuple[list[dict], dict, dict]:
    """Write one fixture's run directory (manifest, institution.json, official site) and return
    ``(sample, scraped, served)``: the sample row, the searched pages as stored scrape output
    and the fixture pages the follow leg is served from (by URL)."""
    from g3o.common.paths import LAYOUT_VERSION, MANIFEST_NAME, institution_dir
    from g3o.run.presweep.official_site_v27 import OFFICIAL_SITE_FILE
    from g3o.run.presweep.perpage_inputs_v27 import INSTITUTION_FILE
    from g3o.run.presweep.records import institution_record

    if official_policy not in OFFICIAL_POLICIES:
        raise ValueError(f"official-site policy must be one of {OFFICIAL_POLICIES}")
    row = fixture_institution_row(fixture)
    record = institution_record(row)
    inst_id = record["institution_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / MANIFEST_NAME).write_text(json.dumps({
        "layout_version": LAYOUT_VERSION, "run_id": f"T041-{fixture['fixture_id']}",
        "institutions": [inst_id], "institution_uids": {inst_id: fixture_uid(inst_id)},
        "t041_fixture": fixture["fixture_id"]}, indent=1), encoding="utf-8")
    idir = institution_dir(run_dir, inst_id)
    idir.mkdir(parents=True, exist_ok=True)
    (idir / INSTITUTION_FILE).write_text(json.dumps({**record, "institution_search_languages": []}, indent=1),
                                         encoding="utf-8")
    searched = set(searched_page_keys(pages, searched_policy))
    scraped_pages = [_rendered(p, access_date) for p in pages if p["page_key"] in searched and p["fetch_ok"]]
    if official_policy == OFFICIAL_PAGE_HOST and scraped_pages:
        host = urlparse(scraped_pages[0].url).netloc
        (idir / OFFICIAL_SITE_FILE).write_text(json.dumps({"url": f"https://{host}/"}), encoding="utf-8")
    served = {p["url"]: (_rendered(p, access_date) if p["fetch_ok"] else None) for p in pages}
    return [row], {inst_id: scraped_pages}, served


def fixture_fetch(served: Mapping[str, Any]) -> Callable[[str], Any]:
    """The follow leg's fetch over the fixture's own pages: no network. A URL the fixture
    does not hold, or a page whose fixture fetch status is not ok, is FETCH_FAILED."""
    from g3o.run.presweep.stage_follow import FetchResult

    def fetch(url: str) -> Any:
        page = served.get(url)
        return FetchResult("FETCHED", page) if page is not None else FetchResult("FETCH_FAILED")

    return fetch


def run_live(fixtures: Sequence[Mapping[str, Any]], *, dispatch: Any, run_root: Path, max_usd: float,
             page_loader: Callable[[Mapping[str, Any]], list[dict[str, Any]]], searched_policy: str,
             official_policy: str, unlocated: str, access_date: str,
             run_fn: Callable[..., Any] | None = None,
             cost_fn: Callable[[Path], float | None] | None = None,
             continue_on_error: bool = False,
             on_result: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Run each runnable fixture in its own run directory (PAID). ``dispatch`` must already
    have passed :func:`require_live_gates`. Stops before the next fixture once the
    journaled spend reaches ``max_usd``, or when a fixture's spend cannot be priced. The cap
    is soft (:data:`CAP_NOTE`): a single fixture can overshoot it by its own cost.

    A fixture whose run raised (a stage stop) is recorded as a result. The run then stops
    before the next fixture if that fixture journaled any spend (or its spend cannot be
    priced): a refusal after paid calls (e.g. the T-015 assembler or Stage 6 refusing the
    fixture run directory) would refuse every later fixture too, after their paid calls.
    A refusal with $0 journaled (a gate before any call) lets the run go on.
    ``continue_on_error=True`` (``--continue-on-error``) goes on after a paid stage stop too.

    ``run_root`` is this invocation's own fresh folder (:func:`fresh_run_root`); each fixture
    runs in ``<run_root>/<fixture_id>``, which must not exist yet (refused before any call).
    ``on_result`` is called with each fixture's result as soon as it is final (the script
    appends it to ``t041-live-fixtures.jsonl``, so a crash or Ctrl-C keeps finished fixtures)."""
    from g3o.run.presweep.perpage_batch_v27 import NO_BATCH

    if getattr(dispatch, "extractor_mode", None) != NO_BATCH:
        raise RunRefused("live fixture runs are sync only (DP-030): pass the dispatch through require_live_gates")
    reused = sorted(f["fixture_id"] for f in fixtures
                    if fixture_group(f) != GROUP_INJECTED and (Path(run_root) / f["fixture_id"]).exists())
    if reused:
        raise RunRefused(f"fixture run directories already exist under {run_root}: {reused} "
                         "(a live run never reuses a run directory)")
    if run_fn is None:
        from g3o.run.presweep.orchestrator import run_v27_dispatch as run_fn
    spent, results, stopped = 0.0, [], None

    def keep(result: dict[str, Any]) -> None:
        results.append(result)
        if on_result is not None:  # review M2: each finished fixture is flushed as it completes
            on_result(result)

    for fixture in fixtures:
        if fixture_group(fixture) == GROUP_INJECTED:
            keep(not_run_result(fixture, "injected answers: no adapter plays them into the pipeline yet"))
            continue
        if stopped is not None:
            keep(not_run_result(fixture, stopped))
            continue
        run_dir = Path(run_root) / fixture["fixture_id"]
        pages = page_loader(fixture)
        sample, scraped, served = materialise(run_dir, fixture, pages, searched_policy=searched_policy,
                                              official_policy=official_policy, access_date=access_date)
        live = dataclasses.replace(dispatch, follow_fetch=fixture_fetch(served))
        error = None
        try:
            summary = run_fn(run_dir, sample, scraped, live)
        except Exception as exc:  # a stage stop is a fixture result, recorded for the PI
            summary, error = None, f"{type(exc).__name__}: {exc}"
        storage = _read_storage(run_dir)
        page_urls = {p["page_key"]: p["url"] for p in pages}
        result = compare_fixture(fixture, lambda e, s=storage, u=page_urls: locate_got(s, e, u),
                                 unlocated=unlocated)
        cost = (cost_fn or _journal_cost(dispatch))(run_dir)
        try:  # review M4: from the journals, so non-answers and failed calls are counted
            x35 = x35_summary(journal_x35_calls(run_dir))
        except ValueError as exc:
            x35 = {**x35_summary([]), "journal_error": str(exc)}
        result.update(summary=summary, error=error, x35=x35, cost_usd=cost)
        keep(result)
        if cost is None:
            stopped = "stopped: the previous fixture's spend could not be priced"
        else:
            spent += cost
            if spent >= max_usd:
                stopped = f"stopped: journaled spend ${spent:.4f} reached the cap ${max_usd:.2f}"
            elif error is not None and cost > 0 and not continue_on_error:
                stopped = (f"stopped: fixture {fixture['fixture_id']} stopped with an error after ${cost:.4f} "
                           "of journaled spend (pass --continue-on-error to go on)")
    return {"results": results, "spent_usd": spent, "stopped": stopped}


def _read_storage(run_dir: Path) -> dict[str, Any] | None:
    from g3o.persist.stage6_adapters import STORAGE_ARTIFACT

    hits = sorted(run_dir.glob(f"institutions/*/*/{STORAGE_ARTIFACT}"))
    return json.loads(hits[0].read_text(encoding="utf-8")) if hits else None


def _journal_cost(dispatch: Any) -> Callable[[Path], float | None]:
    """The fixture's spend priced from its request journals (``orchestrator._v27_cost_block``)."""
    def cost(run_dir: Path) -> float | None:
        from g3o.run.presweep.orchestrator import _v27_cost_block

        s = dispatch.settings
        block = _v27_cost_block(run_dir, {}, s.jev_model, s.extractor_model, s.x35_model)
        totals = [entry.get("total_usd") for entry in block.values()]
        return None if any(t is None for t in totals) else float(sum(totals))
    return cost


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


def output_paths(out_dir: Path, mode: str) -> dict[str, Path]:
    """The output files of ``mode`` in ``out_dir`` (:data:`OUTPUT_NAMES`)."""
    if mode not in OUTPUT_NAMES:
        raise ValueError(f"mode must be one of {sorted(OUTPUT_NAMES)}")
    return {k: Path(out_dir) / name for k, name in OUTPUT_NAMES[mode].items()}


def existing_live_outputs(out_dir: Path) -> list[Path]:
    """Live output files already in ``out_dir``: a live run refuses to start over any of them."""
    return [p for p in output_paths(out_dir, MODE_LIVE).values() if p.exists()]


def append_result_jsonl(path: Path, result: Mapping[str, Any]) -> None:
    """Append one fixture's result as a JSON line, flushed and fsynced (review M2)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(result, ensure_ascii=False, default=str)
    with path.open("ab") as stream:
        stream.write(line.encode("utf-8") + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_outputs(out_dir: Path, *, mode: str, plans: Sequence[Mapping[str, Any]], est: Mapping[str, Any],
                  results: Sequence[Mapping[str, Any]], options: Mapping[str, Any],
                  spent_usd: float | None = None, stopped: str | None = None) -> dict[str, Path]:
    """Write the mode's machine-readable plan / results and its report skeleton.

    Dry and live write different files (:data:`OUTPUT_NAMES`). A live write never
    overwrites: it refuses if any live plan / results / report file exists.
    """
    paths = output_paths(out_dir, mode)
    plan_path, results_path, report_path = paths["plan"], paths["results"], paths["report"]
    if mode == MODE_LIVE:
        clash = [p.name for p in (plan_path, results_path, report_path) if p.exists()]
        if clash:
            raise RunRefused(f"live outputs already exist in the output folder: {clash} (never overwritten)")
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps({"plans": list(plans), "estimate": est}, indent=1, ensure_ascii=False),
                         encoding="utf-8")
    doc = {"mode": mode, "options": dict(options), "a_id_summary": a_id_summary(results),
           "results": list(results), "spent_usd": spent_usd, "stopped": stopped}
    results_path.write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    report_path.write_text(report_skeleton(mode=mode, est=est, results=results, options=options,
                                           spent_usd=spent_usd, stopped=stopped), encoding="utf-8")
    return {"plan": plan_path, "results": results_path, "report": report_path}


def report_skeleton(*, mode: str, est: Mapping[str, Any], results: Sequence[Mapping[str, Any]],
                    options: Mapping[str, Any], spent_usd: float | None, stopped: str | None) -> str:
    seed = est.get("seed_usd")
    est_line = ("none (no seeds file; see t041-plan.json for counts and the page-text floor)" if seed is None else
                f"extractor ${seed['extractor_sync_usd']:.4f} + jev ${seed['jev_usd']:.4f} (spike scale; "
                "Stage 6 quote step and X35 unpriced)")
    lines = [
        "# T-041 report: fixtures on the new-run path (Q184 a)",
        "",
        f"Mode: {mode}. Scope (PI Q184 a): new-run path A-IDs plus the X35 agreement check; back-fill, "
        "transfer (A-022) and the real-id subset follow T-035.",
        f"Options: {json.dumps(dict(options), sort_keys=True)}",
        "",
        "## Cost",
        f"- Estimate: {est_line}",
        "- Actual: " + ("n/a (dry run)" if mode == MODE_DRY else
                        "unpriced (a fixture's spend could not be priced)" if spent_usd is None else
                        f"${spent_usd:.4f} (request journals)"),
        f"- Cap: {CAP_NOTE}.",
        f"- Seed check: {SEED_CHECK_NOTE}.",
        *([f"- {stopped}"] if stopped else []),
        "",
        "## Per A-ID",
        f"Fixtures per status. Note: {A_ID_ROLLUP_NOTE}. `{PASS}`: every value of the fixture passed; "
        f"`{PARTIAL}`: some passed, the others were not located, none failed.",
        "",
        "| A-ID | " + " | ".join(A_ID_STATUSES) + " |",
        "|---|" + "---|" * len(A_ID_STATUSES),
    ]
    for a, counts in a_id_summary(results).items():
        lines.append(f"| {a} | " + " | ".join(str(counts.get(s, 0)) for s in A_ID_STATUSES) + " |")
    lines += ["", "## Per fixture (expected vs got)"]
    for r in results:
        lines.append(f"### {r['fixture_id']}: {r['status']}" + (f" ({r.get('reason')})" if r.get("reason") else ""))
        if r.get("error"):
            lines.append(f"- stage stop: {r['error']}")
        if r.get("x35"):
            x = r["x35"]
            lines.append(f"- X35: {x['n_calls']} calls ({x.get('n_non_answer', 0)} non-answers, "
                         f"{x.get('n_failed', 0)} failed), agreement {x['agreement']}, stated probability "
                         f"min {x['probability_min']} / median {x['probability_median']} / max {x['probability_max']}")
        for e in r["expected"]:
            lines.append(f"- [{e['status']}] {e['item']} @ {e['scope']}: expected {e['expected']!r}, got {e['got']!r}")
    lines += [
        "",
        "## Known limits of the quote match",
        *(f"- {limit}" for limit in QUOTE_MATCH_LIMITS),
        "",
        "## Untested",
        f"- {F6C_LINE}",
        "",
        "## Failures for the PI",
        "(PI reads and rules each failure; PLAN T-041 Done condition.)",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "F6C_LINE", "GROUPS", "QUOTE_MATCH_LIMITS", "RunRefused", "a_id_summary", "compare_fixture",
    "estimate", "fixture_fetch", "fixture_group", "fixture_pages", "force_sync", "format_estimate", "journal_x35_calls",
    "load_fixtures", "locate_got", "materialise", "not_run_result", "plan_fixture", "report_skeleton",
    "require_live_gates", "run_live", "searched_page_keys", "select_fixtures", "validate_fixture",
    "write_outputs", "x35_summary",
]
