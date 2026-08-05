"""Cross-run determinism report (``g3o run-diff``).

Compares the per-stage artifacts of two or more run directories that were
produced from the *same seed* under *different run-ids*, and reports where the
pipeline diverged.  Reads only from disk — no network, no API calls, no cost.

Stage comparisons (each read independently; a missing artifact at one stage
never blocks another):

============================  ==============================  ===============
Stage key                     Artifact                        Compared as
============================  ==============================  ===============
``official_site_pick``        ``2_official_site.json``        ``url`` root (Jaccard n/a)
``triage_keep_set``           ``3_triage.json``               kept-URL set (Jaccard)
``scraped_pages``             ``scrape/*.json``               URL set
``extract_outcomes``          ``extract/*.json``              (url, has_genai_activity) pairs
``final_status``              ``6_validate.json``             ``has_genai_activity`` scalar
============================  ==============================  ===============

``official_site_pick`` compares the *root* of each pick
(:func:`g3o.common.urlnorm.site_root`), not the raw URL: Stage 1b already
reduces the pick to a bare host for its ``site:`` query, so two runs that chose
different subpages of the same host were never going to search differently, and
counting that as divergence overstates instability.

Diagnostics
-----------

The five stages above answer *where* runs diverged but not *why*, and two of
their numbers are easy to over-read. :func:`compute_run_diff` therefore also
emits a ``diagnostics`` block (rendered under ``DIAGNOSTICS`` after the agreed
stage report, which it leaves untouched):

``discovery_candidates``
    URL set from ``1a_discovery_general.json`` + ``1b_discovery_site_restricted.json``.
    Without this the report cannot separate "search returned different
    candidates" from "the triage classifier decided differently" — opposite
    fixes. Both artifacts are already on disk; nothing new has to be run.
    Caveat: SERP responses are cached across runs, so this stage agrees by
    construction on a warm cache. It bounds *where* divergence enters; it does
    not measure search-backend stability.

``triage_candidate_set``
    Every URL that reached triage (keep *and* drop). Sits between discovery and
    ``triage_keep_set``, so it isolates the ``1c_filter_eligibility`` step.

``triage_decision_flips``
    Restricted to URLs every run saw, the share whose keep/drop decision
    differs. This is the only clean measure of classifier determinism —
    ``triage_keep_set`` conflates it with candidate churn.

``final_status_reasons``
    Why a run has no verdict. ``_final_status`` returns ``None`` for four
    distinct causes (artifact absent, unreadable, no ``institution`` object,
    null verdict), which render identically as ``(none)``; an absent artifact
    is an unfinished run, not an instability finding.

``run_completeness``
    Per-run artifact census. ``_run_institutions`` counts any on-disk
    subdirectory as present, so an institution whose run crashed but left a
    stub directory reads as legitimately-empty rather than missing.

``set_stage_stats``
    Mean *pairwise* Jaccard and a presence histogram per set stage. N-way
    Jaccard (``|∩ all| / |∪ all|``) confounds how many runs disagree with how
    much they disagree: with three runs, two agreeing perfectly and a third
    lacking one shared URL scores 0%. The histogram (how many runs held each
    URL) also says directly whether majority-vote would recover a stable set.

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
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from g3o.common.artifact_io import glob_artifacts, read_artifact
from g3o.common.paths import (
    institution_dir,
    iter_institution_dirs,
    require_layout,
)
from g3o.common.urlnorm import site_root

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


def _read_artifact_json(path: Path) -> Any | None:
    """Same tolerant contract as :func:`_read_json`, for a gzipped artifact.

    Kept separate rather than folded into ``_read_json``: that helper also reads
    the plain run-level and stage files (``manifest.json``, ``3_triage.json``,
    ``6_validate.json``), which are never gzipped, and routing those through the
    artifact layer would blur which files Phase 2 actually compresses.
    """
    try:
        return json.loads(read_artifact(path))
    except (OSError, ValueError):
        return None


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    payload = _read_json(run_dir / "manifest.json")
    return payload if isinstance(payload, dict) else {}


def _run_id(run_dir: Path) -> str:
    return _load_manifest(run_dir).get("run_id", run_dir.name)


def _labeled_run_ids(dirs: list[Path]) -> list[str]:
    """Per-directory run-id labels, guaranteed unique for use as report keys.

    ``compute_run_diff`` keys its per-run breakdown dicts (``sets``, ``deltas``,
    ``values``) by these labels, so two runs sharing a run_id would silently
    collapse to one key and drop a run from the rendered/serialized report.

    Two directories may *legitimately* share a run_id: comparing same-seed,
    same-run_id outputs written to different directories is exactly the
    determinism test this tool exists for, so a shared run_id is disambiguated
    by directory rather than rejected. Only the degenerate case of the same
    directory passed more than once (nothing to compare) is a hard error.
    """
    resolved = [d.resolve() for d in dirs]
    if len(set(resolved)) != len(resolved):
        raise ValueError(
            "run-diff requires distinct run directories; the same directory "
            "was passed more than once"
        )
    run_ids = [_run_id(d) for d in dirs]
    counts = Counter(run_ids)
    return [
        f"{rid} [{dirs[i]}]" if counts[rid] > 1 else rid
        for i, rid in enumerate(run_ids)
    ]


def _run_institutions(run_dir: Path) -> set[str]:
    """Institutions this run knows about: manifest list, plus on-disk institution dirs.

    The on-disk half goes through :func:`g3o.common.paths.iter_institution_dirs`
    (storage layout v2). Before v2 this walked ``run_dir.iterdir()`` filtering
    only ``_``-prefixed names and ``.done``; ``final/`` is a real direct child of
    a run dir, so every run that had reached Stage 7 silently counted ``final``
    as an institution here.
    """
    insts: set[str] = set(_load_manifest(run_dir).get("institutions", []))
    for d in iter_institution_dirs(run_dir):
        insts.add(d.name)
    return insts


def _probe_json(path: Path) -> tuple[Any | None, str]:
    """Read a JSON artifact, distinguishing *absent* from *unreadable*.

    :func:`_read_json` collapses both to ``None``, which is fine for comparison
    but loses the distinction the diagnostics need: an absent artifact means the
    run never got there, whereas an unreadable one means it did and the write
    failed. Returns ``(payload, reason)`` where reason is ``"ok"``,
    ``"artifact_absent"``, or ``"artifact_unreadable"``.
    """
    if not path.is_file():
        return None, "artifact_absent"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "ok"
    except (OSError, json.JSONDecodeError):
        return None, "artifact_unreadable"


def _official_site(inst_dir: Path) -> str | None:
    """Canonical root of this run's official-site pick (``None`` if no pick).

    Normalised via :func:`site_root` so that two runs picking different
    subpages of the same host compare equal — see the module docstring.
    """
    payload = _read_json(inst_dir / "2_official_site.json")
    if not isinstance(payload, dict):
        return None
    return site_root(payload.get("url"))


def _discovery_candidates(inst_dir: Path) -> frozenset[str]:
    """Union of candidate URLs from Stage 1a and Stage 1b discovery records.

    .. warning::
       Serper responses are cached on disk by ``(query, num_results)`` in a
       cache shared across runs (``g3o.discovery.serper_client``). On a warm
       cache this stage agrees by construction, so agreement here is evidence
       that divergence is *downstream of search* — **not** evidence that the
       search backend is stable. Measuring that needs runs with a cold or
       bypassed cache.
    """
    urls: set[str] = set()
    for name in ("1a_discovery_general.json", "1b_discovery_site_restricted.json"):
        payload = _read_json(inst_dir / name)
        if not isinstance(payload, dict):
            continue
        for rec in payload.get("records", []):
            if isinstance(rec, dict) and rec.get("link"):
                urls.add(rec["link"])
    return frozenset(urls)


def _triage_decisions(inst_dir: Path) -> dict[str, str]:
    """Every triage decision as ``{url: decision}`` — keeps *and* drops.

    ``_triage_keep_set`` sees only the keeps, so it cannot tell a URL that was
    never offered to the classifier from one the classifier rejected.

    If an artifact carries duplicate rows for one URL, ``keep`` wins, so that a
    URL reported here as kept is exactly a URL in ``_triage_keep_set``. Without
    that tie-break the two readers could disagree on the same file and a flip
    would be reported where none exists.
    """
    payload = _read_json(inst_dir / "3_triage.json")
    if not isinstance(payload, dict):
        return {}
    out: dict[str, str] = {}
    for dec in payload.get("decisions", []):
        if not isinstance(dec, dict):
            continue
        url, decision = dec.get("url"), dec.get("decision")
        if url and decision and out.get(url) != "keep":
            out[url] = decision
    return out


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
    urls: set[str] = set()
    for f in glob_artifacts(inst_dir / "scrape"):
        payload = _read_artifact_json(f)
        if isinstance(payload, dict) and payload.get("url"):
            urls.add(payload["url"])
    return frozenset(urls)


def _extract_outcomes(inst_dir: Path) -> frozenset[tuple[str, Any]]:
    """Set of (source_url, has_genai_activity) pairs across every extract row.

    Each ``extract/`` artifact is a dumped ``BatchResponse`` (a ``data`` array of
    contract rows); every row carries ``source_url`` plus the institution-level
    ``has_genai_activity`` verdict.  We read just those two fields, tolerant of
    any row subset.
    """
    pairs: set[tuple[str, Any]] = set()
    for f in glob_artifacts(inst_dir / "extract"):
        payload = _read_artifact_json(f)
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


def _final_status_reason(inst_dir: Path) -> str:
    """Why ``_final_status`` returned what it did, as a reason code.

    ``"ok"`` when a verdict is present; otherwise ``"artifact_absent"``,
    ``"artifact_unreadable"``, ``"no_institution_object"``, or
    ``"verdict_null"``. The first two mean the run did not finish this
    institution; the last two mean it finished and declined to decide. Those are
    different findings and ``(none)`` hides the difference.
    """
    payload, reason = _probe_json(inst_dir / "6_validate.json")
    if reason != "ok":
        return reason
    if not isinstance(payload, dict):
        return "artifact_unreadable"
    institution = payload.get("institution")
    if not isinstance(institution, dict):
        return "no_institution_object"
    if institution.get("has_genai_activity") is None:
        return "verdict_null"
    return "ok"


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


def _mean_pairwise_jaccard(sets: list[frozenset[Any]]) -> float:
    """Mean Jaccard over all run pairs; 1.0 if every set is empty.

    Unlike :func:`_nway_jaccard` this degrades gracefully: with three runs where
    two agree perfectly and the third lacks one shared URL, N-way scores 0.0
    while this scores 2/3 — which is what "two of three runs reproduce" should
    look like.
    """
    scores: list[float] = []
    for a, b in combinations(sets, 2):
        union = a | b
        scores.append(1.0 if not union else len(a & b) / len(union))
    return sum(scores) / len(scores) if scores else 1.0


def _presence_histogram(sets: list[frozenset[Any]]) -> dict[str, int]:
    """How many distinct members were held by exactly k of the runs.

    Keyed by the stringified count so the report stays JSON-round-trippable
    (JSON object keys are always strings). A run of ``{"3": 40, "1": 12}`` over
    three runs reads as "40 URLs unanimous, 12 seen by a single run"; anything
    in the middle is what a majority vote would have to arbitrate.
    """
    counts: Counter[Any] = Counter()
    for s in sets:
        counts.update(s)
    hist: Counter[int] = Counter(counts.values())
    return {str(k): hist[k] for k in sorted(hist, reverse=True)}


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
# Diagnostics — why runs diverged, and which "divergence" is really an
# unfinished run. Additive: never mutates the five agreed stages.
# ---------------------------------------------------------------------------

# Per-institution artifacts censused by ``run_completeness``, in pipeline order.
# ``scrape`` and ``extract`` are directories and count as present when non-empty.
_CENSUS_ARTIFACTS = [
    "1a_discovery_general.json",
    "1b_discovery_site_restricted.json",
    "1c_filter_eligibility.json",
    "2_official_site.json",
    "3_triage.json",
    "scrape",
    "extract",
    "6_validate.json",
]


def _set_stage_summary(
    per_inst_sets: dict[str, list[frozenset[Any]]], run_ids: list[str]
) -> dict[str, Any]:
    """Agreement summary for one set-valued measurement across runs.

    Same divergence accounting as the main stages, plus the pairwise/histogram
    statistics that N-way Jaccard alone cannot express.
    """
    diverged: list[dict[str, Any]] = []
    for inst, sets in per_inst_sets.items():
        if _all_equal(list(sets)):
            continue
        baseline = sets[0]
        deltas = {
            run_ids[i]: {
                "only": sorted(_fmt_member(x) for x in (sets[i] - baseline)),
                "missing": sorted(_fmt_member(x) for x in (baseline - sets[i])),
            }
            for i in range(1, len(sets))
            if (sets[i] - baseline) or (baseline - sets[i])
        }
        diverged.append(
            {
                "institution_id": inst,
                "overlap": round(_nway_jaccard(sets), 4),
                "mean_pairwise_overlap": round(_mean_pairwise_jaccard(sets), 4),
                "presence_histogram": _presence_histogram(sets),
                "deltas": deltas,
            }
        )
    n = len(per_inst_sets)
    n_diverged = len(diverged)
    return {
        "n_diverged": n_diverged,
        "n_agree": n - n_diverged,
        "pct_agree": _pct(n - n_diverged, n),
        "mean_pairwise_overlap_diverged": (
            round(sum(e["mean_pairwise_overlap"] for e in diverged) / n_diverged, 4)
            if n_diverged
            else None
        ),
        "mean_pairwise_overlap_all": (
            round(
                sum(_mean_pairwise_jaccard(s) for s in per_inst_sets.values()) / n, 4
            )
            if n
            else None
        ),
        "presence_histogram": _aggregate_histogram(per_inst_sets),
        "diverged": diverged,
    }


def _aggregate_histogram(
    per_inst_sets: dict[str, list[frozenset[Any]]],
) -> dict[str, int]:
    """Presence histogram pooled over every institution.

    Members are namespaced by institution id before pooling so that the same URL
    appearing under two institutions is counted as two distinct members rather
    than being conflated into one over-counted entry.
    """
    namespaced: list[frozenset[Any]] = []
    for i in range(len(next(iter(per_inst_sets.values()), []))):
        namespaced.append(
            frozenset(
                (inst, m) for inst, sets in per_inst_sets.items() for m in sets[i]
            )
        )
    return _presence_histogram(namespaced) if namespaced else {}


def _triage_flip_summary(
    per_inst_decisions: dict[str, list[dict[str, str]]], run_ids: list[str]
) -> dict[str, Any]:
    """Keep/drop stability restricted to URLs every run actually saw.

    This is the only clean read on classifier determinism: by intersecting the
    candidate sets first, candidate churn is held constant, so a flip here is
    the classifier changing its mind about identical input.
    """
    entries: list[dict[str, Any]] = []
    total_common = 0
    total_flipped = 0
    for inst, dicts in per_inst_decisions.items():
        common = set(dicts[0]).intersection(*(set(d) for d in dicts[1:])) if dicts else set()
        flipped = {u for u in common if len({d[u] for d in dicts}) > 1}
        total_common += len(common)
        total_flipped += len(flipped)
        if flipped:
            entries.append(
                {
                    "institution_id": inst,
                    "n_common": len(common),
                    "n_flipped": len(flipped),
                    "flip_rate": round(len(flipped) / len(common), 4) if common else None,
                    "flips": {
                        u: {run_ids[i]: dicts[i][u] for i in range(len(dicts))}
                        for u in sorted(flipped)
                    },
                }
            )
    n = len(per_inst_decisions)
    return {
        "n_institutions_with_flips": len(entries),
        "n_institutions": n,
        "pct_stable": _pct(n - len(entries), n),
        "n_common_urls": total_common,
        "n_flipped_urls": total_flipped,
        "flip_rate": _pct(total_flipped, total_common),
        "institutions": entries,
    }


def _run_completeness(dirs: list[Path], run_ids: list[str], run_insts: list[set[str]]) -> dict[str, Any]:
    """Per-run artifact census over the institutions that run knows about."""
    out: dict[str, Any] = {}
    for run_dir, rid, insts in zip(dirs, run_ids, run_insts, strict=True):
        counts: dict[str, int] = {}
        for name in _CENSUS_ARTIFACTS:
            n = 0
            for inst in insts:
                p = institution_dir(run_dir, inst) / name
                if p.is_dir():
                    n += 1 if glob_artifacts(p) else 0
                elif p.is_file():
                    n += 1
            counts[name] = n
        out[rid] = {"n_institutions": len(insts), "artifacts": counts}
    return out


def _final_status_reason_summary(
    dirs: list[Path], run_ids: list[str], run_insts: list[set[str]], all_insts: list[str]
) -> dict[str, Any]:
    """Reason-code tally per run, plus the per-institution codes where they differ."""
    per_run: dict[str, dict[str, str]] = {}
    for run_dir, rid, insts in zip(dirs, run_ids, run_insts, strict=True):
        per_run[rid] = {
            inst: (
                _final_status_reason(institution_dir(run_dir, inst))
                if inst in insts
                else "institution_absent"
            )
            for inst in all_insts
        }
    tallies = {rid: dict(Counter(codes.values())) for rid, codes in per_run.items()}
    divergent = {
        inst: {rid: per_run[rid][inst] for rid in run_ids}
        for inst in all_insts
        if len({per_run[rid][inst] for rid in run_ids}) > 1
    }
    return {"tallies": tallies, "divergent_institutions": divergent}


def _compute_diagnostics(
    dirs: list[Path],
    run_ids: list[str],
    run_insts: list[set[str]],
    all_insts: list[str],
    per_inst: dict[str, dict[str, list[Any]]],
) -> dict[str, Any]:
    """Build the whole diagnostics block. Reads only from disk."""

    def _per_inst_reader(fn: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for inst in all_insts:
            vals = []
            for run_dir, insts in zip(dirs, run_insts, strict=True):
                vals.append(fn(institution_dir(run_dir, inst)) if inst in insts else None)
            out[inst] = vals
        return out

    discovery = {
        inst: [v if v is not None else frozenset() for v in vals]
        for inst, vals in _per_inst_reader(_discovery_candidates).items()
    }
    decisions = {
        inst: [v if v is not None else {} for v in vals]
        for inst, vals in _per_inst_reader(_triage_decisions).items()
    }
    candidate_sets = {
        inst: [frozenset(d) for d in dicts] for inst, dicts in decisions.items()
    }

    set_stage_stats = {}
    for stage in sorted(_SET_STAGES):
        sets_by_inst = {
            inst: [
                frozenset() if v is _MISSING else v for v in per_inst[inst][stage]
            ]
            for inst in all_insts
        }
        set_stage_stats[stage] = {
            "mean_pairwise_overlap_all": (
                round(
                    sum(_mean_pairwise_jaccard(s) for s in sets_by_inst.values())
                    / len(all_insts),
                    4,
                )
                if all_insts
                else None
            ),
            "presence_histogram": _aggregate_histogram(sets_by_inst),
        }

    return {
        "discovery_candidates": _set_stage_summary(discovery, run_ids),
        "triage_candidate_set": _set_stage_summary(candidate_sets, run_ids),
        "triage_decision_flips": _triage_flip_summary(decisions, run_ids),
        "final_status_reasons": _final_status_reason_summary(
            dirs, run_ids, run_insts, all_insts
        ),
        "run_completeness": _run_completeness(dirs, run_ids, run_insts),
        "set_stage_stats": set_stage_stats,
    }


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
    for d in dirs:
        require_layout(d)

    run_ids = _labeled_run_ids(dirs)
    run_insts = [_run_institutions(d) for d in dirs]
    all_insts = sorted(set().union(*run_insts))
    n = len(all_insts)

    # Per-institution, per-stage list of values (one entry per run).
    per_inst: dict[str, dict[str, list[Any]]] = {}
    for inst in all_insts:
        stage_values: dict[str, list[Any]] = {s: [] for s in _STAGES}
        for run_dir, insts in zip(dirs, run_insts, strict=True):
            if inst in insts:
                collected = _collect_institution(institution_dir(run_dir, inst))
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
        "diagnostics": _compute_diagnostics(
            dirs, run_ids, run_insts, all_insts, per_inst
        ),
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

    diag = report.get("diagnostics")
    if diag:
        lines.extend(_render_diagnostics(diag, report["run_ids"], n))

    return "\n".join(lines)


def _fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{round(x * 100)}%"


def _fmt_hist(hist: dict[str, int], n_runs: int) -> str:
    """Render a presence histogram as ``3/3: 40  2/3: 5  1/3: 12``.

    An empty histogram is reported as such rather than as agreement: no members
    anywhere means the artifact was never written, and "100% agree" over nothing
    would read as a clean result.
    """
    if not hist:
        return "(no members — artifact absent in every run)"
    return "  ".join(f"{k}/{n_runs}: {v}" for k, v in hist.items())


def _render_diagnostics(diag: dict[str, Any], run_ids: list[str], n: int) -> list[str]:
    """Render the DIAGNOSTICS block appended after the agreed stage report."""
    lines: list[str] = []
    w = lines.append
    n_runs = len(run_ids)

    w("")
    w("=" * 72)
    w("DIAGNOSTICS")
    w("")

    w("UPSTREAM LOCALISATION (is divergence injected by search or by triage?)")
    w("  note: SERP results are cached across runs — discovery_candidates agrees by")
    w("  construction on a warm cache; it bounds where divergence enters, and is not")
    w("  a measurement of search-backend stability.")
    for key, label in (
        ("discovery_candidates", "discovery_candidates"),
        ("triage_candidate_set", "triage_candidate_set"),
    ):
        st = diag[key]
        w(
            f"{label:<24} {_fmt_pct(st['pct_agree'])} agree "
            f"({st['n_diverged']}/{n} diverged, "
            f"mean pairwise {_fmt_pct(st['mean_pairwise_overlap_all'])})"
        )
        w(f"{'':<24}   URL presence  {_fmt_hist(st['presence_histogram'], n_runs)}")

    flips = diag["triage_decision_flips"]
    w("")
    w("TRIAGE CLASSIFIER STABILITY (URLs every run saw — candidate churn held constant)")
    w(
        f"{'triage_decision_flips':<24} {_fmt_pct(flips['pct_stable'])} of institutions stable "
        f"({flips['n_institutions_with_flips']}/{flips['n_institutions']} with >=1 flip)"
    )
    w(
        f"{'':<24}   {flips['n_flipped_urls']}/{flips['n_common_urls']} shared URLs flipped "
        f"keep/drop ({_fmt_pct(flips['flip_rate'])})"
    )

    w("")
    w("SET-STAGE OVERLAP (N-way Jaccard understates partial agreement)")
    for stage, st in diag["set_stage_stats"].items():
        w(
            f"{stage:<24} mean pairwise "
            f"{_fmt_pct(st['mean_pairwise_overlap_all']):>4}"
            f"   presence  {_fmt_hist(st['presence_histogram'], n_runs)}"
        )

    reasons = diag["final_status_reasons"]
    w("")
    w("FINAL_STATUS REASON CODES (an absent artifact is an unfinished run, not a flip)")
    for rid in run_ids:
        tally = reasons["tallies"].get(rid, {})
        detail = "  ".join(f"{k}={v}" for k, v in sorted(tally.items())) or "(none)"
        w(f"  {rid}: {detail}")
    divergent = reasons["divergent_institutions"]
    if divergent:
        noun = "institution" if len(divergent) == 1 else "institutions"
        w(f"  → {len(divergent)} {noun} differ in reason code across runs:")
        for inst, codes in sorted(divergent.items()):
            w(f"    {inst}: " + ", ".join(f"{rid}={codes[rid]}" for rid in run_ids))

    w("")
    w("RUN COMPLETENESS (per-run artifact census)")
    completeness = diag["run_completeness"]
    artifacts = _CENSUS_ARTIFACTS
    w(f"  {'artifact':<38}" + "".join(f"{rid[:14]:>16}" for rid in run_ids))
    for name in artifacts:
        row = "".join(
            f"{completeness[rid]['artifacts'].get(name, 0):>16}" for rid in run_ids
        )
        w(f"  {name:<38}{row}")
    w(
        f"  {'(institutions known)':<38}"
        + "".join(f"{completeness[rid]['n_institutions']:>16}" for rid in run_ids)
    )

    return lines


__all__ = ["compute_run_diff", "render_run_diff_text"]

