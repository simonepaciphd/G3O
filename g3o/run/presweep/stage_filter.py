"""Stage 1c runner — deterministic eligibility pre-filter between 1b and triage.

Inserts between ``discovery_site_restricted`` (1b) and ``classify_triage`` (3).
For each institution it screens the path-aware deduped union of the 1a+1b
records with :mod:`g3o.classify.eligibility` and writes one
``1c_filter_eligibility.json`` artifact — a pure function of the 1a/1b
artifacts plus the versioned rule set, so two runs over the same inputs produce
byte-identical output. The 1a/1b artifacts are never mutated.

Modes (memo §Mechanics; config ``filter_mode``):
  ``off``     — no-op: no artifact, Stage 3 consumes the current union unchanged.
  ``shadow``  — artifact written with would-drop decisions; **nothing dropped**,
                no attrition. Stage 3 still sees the full union. (Default.)
  ``enforce`` — artifact written; each drop → one attrition record; Stage 3
                receives pruned discovery dicts containing only ``pass`` URLs.

Enabling ``enforce`` is a PI decision made on measured shadow recall — the
runner just honors the configured mode.

Resume: same shape as 1a/1b — ``.done`` marker short-circuit + per-institution
skip-if-exists. Deterministic (``no_batch=True``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from g3o.classify.eligibility import RULES_VERSION, evaluate
from g3o.common import attrition
from g3o.common.paths import institution_dir
from g3o.common.run_state import is_done, mark_done
from g3o.common.timing import stage_timer
from g3o.run.presweep.records import _dedupe_key, institution_record, synth_institution_id

logger = logging.getLogger(__name__)

STAGE = "filter_eligibility"
ARTIFACT_NAME = "1c_filter_eligibility.json"


def _records_union(
    discovery_general: dict[str, list[dict[str, Any]]],
    discovery_site_restricted: dict[str, list[dict[str, Any]]],
    inst_id: str,
    discovery_evidence_open: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """First-seen, path-aware deduped union of 1a+1b(+1d) *records* for one institution.

    Mirrors :func:`g3o.run.presweep.stage_classify._candidate_urls_union` (same
    ``_dedupe_key`` and 1a-before-1b-before-1d order) but keeps the whole record
    so the 1b keyword screen can read ``title``/``snippet`` — which the URL-only
    triage union discards. Evaluating the first-seen record per dedup key matches
    the canonical URL the triage union would carry downstream.

    ``discovery_evidence_open`` (2026-09-03) is the open evidence leg's records,
    ``None`` on a run without it — every run before that date.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for source in (
        discovery_general.get(inst_id, []),
        discovery_site_restricted.get(inst_id, []),
        (discovery_evidence_open or {}).get(inst_id, []),
    ):
        for r in source:
            url = r.get("link", "")
            if not url:
                continue
            key = _dedupe_key(url)
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


def _read_existing_filter(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Reconstruct per-institution decision lists from ``1c`` artifacts on disk."""
    out: dict[str, list[dict[str, Any]]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = institution_dir(run_dir, inst_id) / ARTIFACT_NAME
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[inst_id] = payload.get("decisions", [])
    return out


def _dropped_keys(decisions: list[dict[str, Any]]) -> set[str]:
    """Dedup keys of every ``drop`` decision (for pruning under ``enforce``)."""
    return {_dedupe_key(d["url"]) for d in decisions if d.get("decision") == "drop"}


def _prune(
    discovery: dict[str, list[dict[str, Any]]],
    dropped_by_inst: dict[str, set[str]],
) -> dict[str, list[dict[str, Any]]]:
    """Return a copy of a discovery dict with every dropped URL removed."""
    pruned: dict[str, list[dict[str, Any]]] = {}
    for inst_id, records in discovery.items():
        dropped = dropped_by_inst.get(inst_id)
        if not dropped:
            pruned[inst_id] = records
            continue
        pruned[inst_id] = [
            r for r in records if _dedupe_key(r.get("link", "")) not in dropped
        ]
    return pruned


def _write_artifact(
    run_dir: Path, inst_id: str, mode: str, decisions: list[dict[str, Any]]
) -> None:
    """Write one ``1c_filter_eligibility.json`` (deterministic; no timestamps)."""
    inst_dir = institution_dir(run_dir, inst_id)
    if not inst_dir.exists():
        return
    (inst_dir / ARTIFACT_NAME).write_text(
        json.dumps(
            {
                "mode": mode,
                "rules_version": RULES_VERSION,
                "decisions": decisions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _run_filter_eligibility(
    run_dir: Path,
    sample: list[dict[str, Any]],
    discovery_general: dict[str, list[dict[str, Any]]],
    discovery_site_restricted: dict[str, list[dict[str, Any]]],
    *,
    mode: str,
    discovery_evidence_open: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
]:
    """Screen the 1a+1b(+1d) union per institution and honor ``mode``.

    Returns ``(effective_general, effective_site_restricted, stats)`` — the two
    discovery dicts Stage 3 should consume (pruned only under ``enforce``) plus
    a small stats dict for the run summary. Under ``off`` the inputs are
    returned unchanged and nothing is written.

    ``discovery_evidence_open`` (2026-09-03), when given, joins the screened
    union and is pruned in place under ``enforce`` — the caller keeps its own
    reference, which is why it is not a fourth return value: the two-tuple
    contract predates the leg and every caller of it reads positionally.
    """
    if mode == "off":
        logger.info("Stage 1c: filter_mode=off — bypassed, Stage 3 sees full union")
        return discovery_general, discovery_site_restricted, _summary_stats({}, mode)

    if mode not in ("shadow", "enforce"):
        raise ValueError(f"unknown filter_mode: {mode!r} (expected off|shadow|enforce)")

    # Resume: reconstruct decisions from disk instead of re-screening. Under
    # enforce we still (re-)record attrition — attrition.record dedups, so this
    # is a no-op if the drops were already logged, and closes the gap where a
    # prior shadow run's .done marker would otherwise let enforce prune Stage 3
    # silently. Artifacts are not rewritten (byte-identical guarantee).
    if is_done(run_dir, STAGE):
        logger.info("Stage 1c: .done marker present — skipping (resume from disk)")
        decisions_by_inst = _read_existing_filter(run_dir, sample)
    else:
        decisions_by_inst = {}
        for row in sample:
            inst_id = institution_record(row)["institution_id"]
            path = institution_dir(run_dir, inst_id) / ARTIFACT_NAME
            if path.exists():
                # Partial-recovery skip-if-exists (no .done marker yet).
                decisions = json.loads(path.read_text(encoding="utf-8")).get(
                    "decisions", []
                )
            else:
                union = _records_union(
                    discovery_general, discovery_site_restricted, inst_id,
                    discovery_evidence_open,
                )
                if not union:
                    continue
                with stage_timer(run_dir, inst_id, STAGE):
                    decisions = [
                        {"url": r.get("link", ""), **_decision_fields(evaluate(r))}
                        for r in union
                    ]
                    _write_artifact(run_dir, inst_id, mode, decisions)
            decisions_by_inst[inst_id] = decisions
        mark_done(run_dir, STAGE, no_batch=True)

    if mode == "enforce":
        for inst_id, decisions in decisions_by_inst.items():
            _record_enforced_drops(run_dir, inst_id, decisions)

    stats = _summary_stats(decisions_by_inst, mode)

    if mode == "enforce":
        dropped_by_inst = {
            i: _dropped_keys(ds) for i, ds in decisions_by_inst.items()
        }
        if discovery_evidence_open is not None:
            # In place, so the caller's dict is the pruned one (see docstring).
            pruned_open = _prune(discovery_evidence_open, dropped_by_inst)
            discovery_evidence_open.clear()
            discovery_evidence_open.update(pruned_open)
        return (
            _prune(discovery_general, dropped_by_inst),
            _prune(discovery_site_restricted, dropped_by_inst),
            stats,
        )
    return discovery_general, discovery_site_restricted, stats


def _decision_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Keep only the artifact-facing fields of an ``evaluate`` result."""
    return {"decision": result["decision"], "matched_rules": result["matched_rules"]}


def _record_enforced_drops(
    run_dir: Path, inst_id: str, decisions: list[dict[str, Any]]
) -> None:
    """One attrition record per enforced drop (silent drops are forbidden)."""
    from g3o.classify.eligibility import REASON_NO_SIGNAL, REASON_URL_PATTERN

    for d in decisions:
        if d.get("decision") != "drop":
            continue
        matched = d.get("matched_rules", [])
        reason = REASON_NO_SIGNAL if matched == [REASON_NO_SIGNAL] else REASON_URL_PATTERN
        attrition.record(
            run_dir,
            institution_id=inst_id,
            stage=STAGE,
            reason=reason,
            url=d["url"],
            detail=",".join(matched) if matched else None,
        )


def _summary_stats(
    decisions_by_inst: dict[str, list[dict[str, Any]]], mode: str
) -> dict[str, Any]:
    """Deterministic run-summary counts derived from the decision lists."""
    from g3o.classify.eligibility import REASON_NO_SIGNAL

    n_eval = n_pass = n_drop = n_pat = n_sig = 0
    for decisions in decisions_by_inst.values():
        for d in decisions:
            n_eval += 1
            if d.get("decision") == "pass":
                n_pass += 1
            elif d.get("matched_rules") == [REASON_NO_SIGNAL]:
                n_drop += 1
                n_sig += 1
            else:
                n_drop += 1
                n_pat += 1
    return {
        "mode": mode,
        "n_evaluated": n_eval,
        "n_pass": n_pass,
        "n_would_drop": n_drop,
        "n_url_pattern_drop": n_pat,
        "n_no_signal_drop": n_sig,
        # Under enforce every would-drop is actually removed from Stage 3.
        "n_enforced_drop": n_drop if mode == "enforce" else 0,
    }


__all__ = ["STAGE", "ARTIFACT_NAME", "_run_filter_eligibility", "_records_union"]
