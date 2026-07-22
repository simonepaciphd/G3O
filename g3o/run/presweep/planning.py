"""Manifest + run-dir lifecycle: plan, layout, resume guard, LLM provenance."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from g3o.common.batch_client import DEFAULT_REASONING_EFFORT
from g3o.common.run_state import done_dir, state_dir
from g3o.run.presweep.config import STAGES, PresweepConfig
from g3o.run.presweep.records import (
    _read_master,
    _utc_iso,
    _utc_today,
    institution_record,
    synth_institution_id,
)
from g3o.run.presweep.sampling import stratified_sample


def build_manifest(
    config: PresweepConfig,
    sample: list[dict[str, Any]],
    *,
    n_strata_observed: int | None = None,
) -> dict[str, Any]:
    config_dict: dict[str, Any] = asdict(config)
    config_dict["runs_dir"] = str(config.runs_dir)
    config_dict["master_csv"] = str(config.master_csv)
    config_dict["stratify_keys"] = list(config.stratify_keys)
    config_dict["discovery_languages"] = list(config.discovery_languages)
    # institution_search_languages is a derived property (not a dataclass
    # field), so asdict() above doesn't pick it up — record it explicitly so
    # the manifest and the resume guard below still see it.
    config_dict["institution_search_languages"] = config.institution_search_languages
    stages_planned = list(STAGES[: STAGES.index(config.stop_after) + 1])
    return {
        "run_id": config.run_id,
        "run_kind": "pre-sweep",
        "run_date": _utc_today(),
        "run_timestamp": _utc_iso(),
        "run_model": config.model,
        # Request-side generation parameters pinned by the serializer (T1,
        # 2026-06-11). Recorded at plan time so the manifest states what every
        # LLM job in this run sends; the response side lands in
        # ``llm_provenance`` once stages fetch.
        "run_generation_parameters": {"reasoning_effort": DEFAULT_REASONING_EFFORT},
        "run_tool": "g3o.run.presweep",
        "config": config_dict,
        "n_institutions_drawn": len(sample),
        "n_strata_observed": n_strata_observed,
        "stages_planned": stages_planned,
        "institutions": [synth_institution_id(r) for r in sample],
    }


def write_run_layout(
    config: PresweepConfig,
    sample: list[dict[str, Any]],
    *,
    manifest: dict[str, Any],
) -> Path:
    """Create ``runs/<run_id>/`` with manifest + per-institution dirs.

    Idempotent: existing directories are preserved; ``manifest.json`` is
    overwritten. ``inputs/`` is never touched.
    """
    run_dir = config.runs_dir / config.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for row in sample:
        institution = institution_record(row)
        inst_dir = run_dir / institution["institution_id"]
        inst_dir.mkdir(exist_ok=True)
        (inst_dir / "institution.json").write_text(
            json.dumps(institution, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if config.dry_run:
        (run_dir / "_DRY_RUN.txt").write_text(
            "Dry-run: no live submits performed.\n"
            f"Stages planned: {', '.join(manifest['stages_planned'])}\n"
            f"To execute live (rerun with --execute):\n"
            f"  g3o presweep --execute --run-id {config.run_id} "
            f"--sample-size {config.sample_size} --seed {config.seed}\n",
            encoding="utf-8",
        )
    return run_dir


@dataclass
class RunPlan:
    """The pre-run plan: sample drawn, manifest written, per-institution dirs created."""

    run_dir: Path
    sample: list[dict[str, Any]] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


# Config fields whose change between the original launch and a resume would make
# the on-disk artifacts and ``_state/`` inconsistent with a fresh projection
# (review F7). The drawn institution list already captures master-CSV drift and
# sample/seed/stratification changes; these cover the job-semantics args that do
# not alter the sample but would still diverge a resumed run.
_GUARDED_CONFIG_KEYS: tuple[str, ...] = (
    "master_csv",
    "sample_size",
    "seed",
    "stratification",
    "stratify_keys",
    "discovery_languages",
    "discovery_results_per_query",
    "institution_search_languages",
    "model",
)


def _assert_manifest_matches_on_resume(
    run_dir: Path, new_manifest: dict[str, Any]
) -> None:
    """Abort a resume whose fresh projection diverges from the on-disk manifest.

    Resume is signalled by the presence of ``_state/`` (review F7). Before
    :func:`write_run_layout` overwrites ``manifest.json`` and every
    ``institution.json``, compare the freshly drawn institution list and the
    guarded config fields against the existing manifest; on any mismatch raise
    with a readable diff (master CSV drifted — WS3 round 2 actively appends rows
    — or CLI args differ). A fresh run (no ``_state/``) and the seeded dry-run
    layout (manifest present, no ``_state/``) are unaffected: the guard is a
    no-op when ``_state/`` is absent.
    """
    if not state_dir(run_dir).exists():
        return  # fresh run or seeded dry-run layout — nothing to guard
    existing_path = run_dir / "manifest.json"
    if not existing_path.exists():
        return  # state without a manifest is anomalous; nothing to compare
    existing = json.loads(existing_path.read_text(encoding="utf-8"))
    diffs: list[str] = []
    if existing.get("institutions") != new_manifest["institutions"]:
        old_set = set(existing.get("institutions", []))
        new_set = set(new_manifest["institutions"])
        removed = sorted(old_set - new_set)
        added = sorted(new_set - old_set)
        diffs.append(
            f"institution sample changed: n {len(old_set)}→{len(new_set)}, "
            f"{len(removed)} removed, {len(added)} added "
            f"(e.g. removed={removed[:3]}, added={added[:3]})"
        )
    old_cfg = existing.get("config", {})
    new_cfg = new_manifest["config"]
    for key in _GUARDED_CONFIG_KEYS:
        if old_cfg.get(key) != new_cfg.get(key):
            diffs.append(
                f"config.{key}: {old_cfg.get(key)!r} (manifest) "
                f"!= {new_cfg.get(key)!r} (this run)"
            )
    # Pinned generation parameters are part of run identity (T1): a resume on
    # code whose pin differs from the original launch would mix generation
    # regimes within one run. Only compared when the original manifest recorded
    # them (manifests written before 2026-06-11 did not).
    old_gen = existing.get("run_generation_parameters")
    new_gen = new_manifest.get("run_generation_parameters")
    if old_gen is not None and old_gen != new_gen:
        diffs.append(
            f"run_generation_parameters: {old_gen!r} (manifest) "
            f"!= {new_gen!r} (this run)"
        )
    if diffs:
        raise RuntimeError(
            "Resume aborted: _state/ is present under "
            f"{state_dir(run_dir)} but the freshly drawn run does not match the "
            "existing manifest.json. This usually means the master CSV drifted "
            "(WS3 round-2 appends rows) or the CLI args differ from the original "
            "launch. Investigate and resolve before retrying:\n  - "
            + "\n  - ".join(diffs)
        )


def update_manifest_llm_provenance(run_dir: Path) -> dict[str, Any]:
    """Fold response-side LLM provenance from stage state files into the manifest.

    T1 reproducibility floor (2026-06-11): the chunk entries written by
    :func:`g3o.common.run_state.run_chunked_stage` record, per fetched chunk,
    the versioned model id(s) and ``system_fingerprint``(s) the server actually
    answered with, plus the batch ids. This helper aggregates them per stage —
    reading both the active ``_state/{stage}.json`` files (stages interrupted
    mid-flight) and the terminal ``.done/{stage}.json`` markers — and rewrites
    ``manifest.json`` atomically with an ``llm_provenance`` block. The state
    files remain the ground truth; the manifest block is a derived view so the
    run's reproducibility record lives in one researcher-visible artifact.

    Returns the block. No-op returning ``{}`` when there is no manifest or no
    batch-bearing state (dry runs, discovery-only runs).
    """
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    provenance: dict[str, Any] = {}
    candidates: list[Path] = []
    for directory in (state_dir(run_dir), done_dir(run_dir)):
        if directory.is_dir():
            candidates.extend(sorted(directory.glob("*.json")))
    for path in candidates:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stage = payload.get("stage")
        chunks = payload.get("chunks")
        if not stage or not isinstance(chunks, dict):
            continue  # no-batch done markers carry no provenance
        models: set[str] = set()
        fingerprints: set[str] = set()
        batch_ids: list[str] = []
        n_fetched = 0
        for _, entry in sorted(chunks.items(), key=lambda kv: int(kv[0])):
            if entry.get("batch_id"):
                batch_ids.append(entry["batch_id"])
            if entry.get("fetched_at"):
                n_fetched += 1
            models.update(entry.get("response_models") or [])
            fingerprints.update(entry.get("system_fingerprints") or [])
        # A stage present in both _state/ and .done/ (crash between the done
        # write and the state unlink) resolves to the .done copy: done_dir is
        # scanned second and overwrites the entry.
        provenance[stage] = {
            "request_model": payload.get("model"),
            "response_models": sorted(models),
            "system_fingerprints": sorted(fingerprints),
            "batch_ids": batch_ids,
            "n_chunks_planned": len(chunks),
            "n_chunks_fetched": n_fetched,
        }
    if not provenance:
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["llm_provenance"] = provenance
    tmp = manifest_path.with_name(manifest_path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, manifest_path)
    return provenance


def plan_run(config: PresweepConfig) -> RunPlan:
    """Read master, draw sample, write manifest + per-institution dirs. No live calls.

    On resume (``_state/`` present) the freshly drawn sample + guarded config are
    checked against the existing manifest *before* anything is overwritten
    (review F7); a mismatch aborts with a diff.
    """
    rows = list(_read_master(config.master_csv))
    if not rows:
        raise RuntimeError(f"master CSV is empty: {config.master_csv}")
    n_strata_observed = len(
        {tuple(r.get(k, "") for k in config.stratify_keys) for r in rows}
    )
    sample = stratified_sample(
        rows,
        sample_size=config.sample_size,
        seed=config.seed,
        stratify_keys=config.stratify_keys,
    )
    manifest = build_manifest(config, sample, n_strata_observed=n_strata_observed)
    _assert_manifest_matches_on_resume(config.runs_dir / config.run_id, manifest)
    run_dir = write_run_layout(config, sample, manifest=manifest)
    return RunPlan(run_dir=run_dir, sample=sample, manifest=manifest)
