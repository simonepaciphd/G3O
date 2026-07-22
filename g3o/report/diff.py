"""Cross-run determinism report (``g3o run-diff``).

Compares the per-stage artifacts of two or more run directories that were
produced from the *same seed* under *different run-ids*, and reports where the
pipeline diverged.  Reads only from disk — no network, no API calls, no cost.

Stage comparisons (each read independently; a missing artifact at one stage
never blocks another):

============================  ==============================  ===============
Stage key                     Artifact                        Compared as
============================  ==============================  ===============
``official_site_pick``        ``2_official_site.json``        ``url`` scalar
``triage_keep_set``           ``3_triage.json``               kept-URL set (Jaccard)
``scraped_pages``             ``scrape/*.json``               URL set
``extract_outcomes``          ``extract/*.json``              (url, has_genai_activity) pairs
``final_status``              ``6_validate.json``             ``has_genai_activity`` scalar
============================  ==============================  ===============

An institution that is missing from a run entirely is treated as *diverged* at
every stage (its per-run value is the :data:`_MISSING` sentinel, unequal to any
real value).  A stage artifact that is absent for an institution that is
otherwise present counts as an *empty* result (empty set / ``None`` scalar), so
two runs that both produced nothing for a stage still agree.

Overlap for set-valued stages uses N-way Jaccard:
``|intersection over all runs| / |union over all runs|``.

Usage::

    from g3o.report.diff import compute_run_diff, render_run_diff_text
    report = compute_run_diff([Path("runs/a"), Path("runs/b")])
    print(render_run_diff_text(report))
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Stage keys in canonical display order (matches the report shape agreed with
# Thomas).
_STAGES = [
    "official_site_pick",
    "triage_keep_set",
    "scraped_pages",
    "extract_outcomes",
    "final_status",
]

# Set-valued stages compare via Jaccard overlap; the rest compare scalars.
_SET_STAGES = frozenset({"triage_keep_set", "scraped_pages", "extract_outcomes"})

# Sentinel for "this institution is absent from this run entirely." Distinct
# from ``None`` (scalar artifact absent) and ``frozenset()`` (set artifact
# absent) so that a missing institution never silently compares equal to a run
# that merely produced nothing for a stage.
_MISSING = object()


# ---------------------------------------------------------------------------
# Disk readers — each guarded so a corrupt/absent file degrades to an empty
# result for *that* stage only.
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    payload = _read_json(run_dir / "manifest.json")
    return payload if isinstance(payload, dict) else {}


def _run_id(run_dir: Path) -> str:
    return _load_manifest(run_dir).get("run_id", run_dir.name)


def _run_institutions(run_dir: Path) -> set[str]:
    """Institutions this run knows about: manifest list ∪ on-disk subdirs."""
    insts: set[str] = set(_load_manifest(run_dir).get("institutions", []))
    if run_dir.is_dir():
        for d in run_dir.iterdir():
            if d.is_dir() and not d.name.startswith("_") and d.name != ".done":
                insts.add(d.name)
    return insts


def _official_site(inst_dir: Path) -> str | None:
    payload = _read_json(inst_dir / "2_official_site.json")
    if not isinstance(payload, dict):
        return None
    return payload.get("url")


def _triage_keep_set(inst_dir: Path) -> frozenset[str]:
    payload = _read_json(inst_dir / "3_triage.json")
    if not isinstance(payload, dict):
        return frozenset()
    return frozenset(
        dec["url"]
        for dec in payload.get("decisions", [])
        if dec.get("decision") == "keep" and dec.get("url")
    )


def _scraped_pages(inst_dir: Path) -> frozenset[str]:
    scrape_dir = inst_dir / "scrape"
    if not scrape_dir.is_dir():
        return frozenset()
    urls: set[str] = set()
    for f in scrape_dir.glob("*.json"):
        payload = _read_json(f)
        if isinstance(payload, dict) and payload.get("url"):
            urls.add(payload["url"])
    return frozenset(urls)


def _extract_outcomes(inst_dir: Path) -> frozenset[tuple[str, Any]]:
    """Set of (source_url, has_genai_activity) pairs across every extract row.

    Each ``extract/*.json`` is a dumped ``BatchResponse`` (a ``data`` array of
    contract rows); every row carries ``source_url`` plus the institution-level
    ``has_genai_activity`` verdict.  We read just those two fields, tolerant of
    any row subset.
    """
    extract_dir = inst_dir / "extract"
    if not extract_dir.is_dir():
        return frozenset()
    pairs: set[tuple[str, Any]] = set()
    for f in extract_dir.glob("*.json"):
        payload = _read_json(f)
        if not isinstance(payload, dict):
            continue
        for row in payload.get("data", []):
            url = row.get("source_url")
            if url:
                pairs.add((url, row.get("has_genai_activity")))
    return frozenset(pairs)


def _final_status(inst_dir: Path) -> str | None:
    payload = _read_json(inst_dir / "6_validate.json")
    if not isinstance(payload, dict):
        return None
    institution = payload.get("institution")
    if not isinstance(institution, dict):
        return None
    return institution.get("has_genai_activity")


def _collect_institution(inst_dir: Path) -> dict[str, Any]:
    """Read all five stage values for one (present) institution in one run."""
    return {
        "official_site_pick": _official_site(inst_dir),
        "triage_keep_set": _triage_keep_set(inst_dir),
        "scraped_pages": _scraped_pages(inst_dir),
        "extract_outcomes": _extract_outcomes(inst_dir),
        "final_status": _final_status(inst_dir),
    }


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def _eq(a: Any, b: Any) -> bool:
    """Equality that treats the _MISSING sentinel as equal only to itself."""
    if a is _MISSING or b is _MISSING:
        return a is b
    return a == b


def _all_equal(values: list[Any]) -> bool:
    first = values[0]
    return all(_eq(v, first) for v in values[1:])


def _nway_jaccard(sets: list[frozenset[Any]]) -> float:
    """|intersection of all sets| / |union of all sets|; 1.0 if all empty."""
    inter: set[Any] = set(sets[0])
    union: set[Any] = set()
    for s in sets:
        inter &= s
        union |= s
    if not union:
        return 1.0
    return len(inter) / len(union)


def _fmt_member(x: Any) -> str:
    """Render a set member for the text/JSON delta lines."""
    if isinstance(x, tuple):
        url, hga = x
        return f"{url} ({hga})"
    return str(x)


def _pct(num: int, denom: int) -> float | None:
    if denom == 0:
        return None
    return round(num / denom, 4)


def _diverged_entry(
    stage: str, inst_id: str, values: list[Any], run_ids: list[str]
) -> dict[str, Any]:
    """Build the per-institution divergence record for one stage."""
    missing_in = [run_ids[i] for i, v in enumerate(values) if v is _MISSING]
    entry: dict[str, Any]

    if stage in _SET_STAGES:
        # A missing institution contributes an empty set to the overlap math.
        sets = [frozenset() if v is _MISSING else v for v in values]
        baseline = sets[0]
        deltas: dict[str, dict[str, list[str]]] = {}
        for i in range(1, len(sets)):
            only = sorted(_fmt_member(x) for x in (sets[i] - baseline))
            missing = sorted(_fmt_member(x) for x in (baseline - sets[i]))
            if only or missing:
                deltas[run_ids[i]] = {"only": only, "missing": missing}
        entry = {
            "institution_id": inst_id,
            "overlap": round(_nway_jaccard(sets), 4),
            "sets": {
                run_ids[i]: sorted(_fmt_member(x) for x in sets[i])
                for i in range(len(sets))
            },
            "deltas": deltas,
        }
    else:
        entry = {
            "institution_id": inst_id,
            "values": {
                run_ids[i]: (None if values[i] is _MISSING else values[i])
                for i in range(len(values))
            },
        }

    if missing_in:
        entry["missing_in"] = missing_in
    return entry


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_run_diff(run_dirs: list[str | Path]) -> dict[str, Any]:
    """Compute a cross-run determinism report over two or more run directories.

    Parameters
    ----------
    run_dirs:
        Two or more ``runs/<run_id>/`` paths (same seed, different run-ids).
        The first directory is the baseline for per-institution ``only`` /
        ``missing`` delta lines.

    Returns
    -------
    dict
        JSON-serialisable report: per-stage agreement counts and diverged
        institutions, the most-divergent stage, and the full-agreement roster.
        Render with :func:`render_run_diff_text`.
    """
    dirs = [Path(d) for d in run_dirs]
    if len(dirs) < 2:
        raise ValueError("run-diff requires at least two run directories")

    run_ids = [_run_id(d) for d in dirs]
    run_insts = [_run_institutions(d) for d in dirs]
    all_insts = sorted(set().union(*run_insts))
    n = len(all_insts)

    # Per-institution, per-stage list of values (one entry per run).
    per_inst: dict[str, dict[str, list[Any]]] = {}
    for inst in all_insts:
        stage_values: dict[str, list[Any]] = {s: [] for s in _STAGES}
        for run_dir, insts in zip(dirs, run_insts, strict=True):
            if inst in insts:
                collected = _collect_institution(run_dir / inst)
            else:
                collected = {s: _MISSING for s in _STAGES}
            for s in _STAGES:
                stage_values[s].append(collected[s])
        per_inst[inst] = stage_values

    diverged_stage_count: dict[str, int] = {inst: 0 for inst in all_insts}
    stages_out: dict[str, Any] = {}
    for s in _STAGES:
        diverged: list[dict[str, Any]] = []
        for inst in all_insts:
            values = per_inst[inst][s]
            if _all_equal(values):
                continue
            diverged_stage_count[inst] += 1
            diverged.append(_diverged_entry(s, inst, values, run_ids))
        n_diverged = len(diverged)
        stage: dict[str, Any] = {
            "n_diverged": n_diverged,
            "n_agree": n - n_diverged,
            "pct_agree": _pct(n - n_diverged, n),
            "diverged": diverged,
        }
        if s == "triage_keep_set":
            overlaps = [e["overlap"] for e in diverged]
            stage["avg_overlap"] = (
                round(sum(overlaps) / len(overlaps), 4) if overlaps else None
            )
        stages_out[s] = stage

    total_diverged = sum(stages_out[s]["n_diverged"] for s in _STAGES)
    most_divergent = (
        max(_STAGES, key=lambda s: stages_out[s]["n_diverged"])
        if total_diverged
        else None
    )
    full_agreement = [inst for inst in all_insts if diverged_stage_count[inst] == 0]

    return {
        "run_ids": run_ids,
        "run_dirs": [str(d) for d in dirs],
        "n_runs": len(dirs),
        "n_institutions": n,
        "stages": stages_out,
        "most_divergent_stage": most_divergent,
        "full_agreement": full_agreement,
        "n_full_agreement": len(full_agreement),
    }


def render_run_diff_text(report: dict[str, Any]) -> str:
    """Render a run-diff report in the exact human-readable shape."""
    lines: list[str] = []
    w = lines.append

    run_ids = report["run_ids"]
    n = report["n_institutions"]
    w(f"Run-diff: {', '.join(run_ids)} (n={n} institutions)")
    w("")
    w("DIVERGENCE BY STAGE")
    for s in _STAGES:
        st = report["stages"][s]
        pct = round((st["pct_agree"] or 0) * 100)
        extra = ""
        if s == "triage_keep_set" and st.get("avg_overlap") is not None:
            extra = f", avg overlap {round(st['avg_overlap'] * 100)}%"
        w(f"{s:<22} {pct}% agree ({st['n_diverged']}/{n} diverged{extra})")

    most = report["most_divergent_stage"]
    if most:
        w(f"→ Most divergence concentrates at {most}.")
    else:
        w("→ No divergence: all runs agree on every stage.")

    for s in _STAGES:
        st = report["stages"][s]
        if not st["diverged"]:
            continue
        w("")
        w(f"DIVERGED INSTITUTIONS ({s})")
        for e in st["diverged"]:
            if s == "triage_keep_set":
                w(f"{e['institution_id']}: {round(e['overlap'] * 100)}% overlap")
            elif s in _SET_STAGES:
                w(f"{e['institution_id']}:")
            else:
                w(f"{e['institution_id']}:")

            if s in _SET_STAGES:
                # Baseline (first run) carries no delta line; report each other
                # run's additions/omissions relative to it.
                for rid in run_ids[1:]:
                    delta = e["deltas"].get(rid)
                    if not delta:
                        continue
                    if delta["only"]:
                        w(f"  {rid} only: {', '.join(delta['only'])}")
                    if delta["missing"]:
                        w(f"  {rid} missing: {', '.join(delta['missing'])}")
            else:
                missing_in = e.get("missing_in", [])
                for rid in run_ids:
                    if rid in missing_in:
                        val = "(missing)"
                    else:
                        v = e["values"][rid]
                        val = "(none)" if v is None else str(v)
                    w(f"  {rid}: {val}")

    w("")
    n_full = report["n_full_agreement"]
    w(f"FULL AGREEMENT: {n_full}/{n} institutions matched on every stage")

    return "\n".join(lines)


__all__ = ["compute_run_diff", "render_run_diff_text"]
