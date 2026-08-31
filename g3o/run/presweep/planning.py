"""Manifest + run-dir lifecycle: plan, layout, resume guard, LLM provenance."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from g3o.common.batch_client import DEFAULT_REASONING_EFFORT
from g3o.common.contract import INSTITUTION_UID_PATTERN
from g3o.common.languages import language_policy_hash
from g3o.common.paths import INSTITUTION_UIDS_KEY, LAYOUT_VERSION, institution_dir
from g3o.common.run_state import done_dir, state_dir
from g3o.discovery.query_builder import genai_terms_roster_hash
from g3o.run.presweep.config import STAGES, PresweepConfig
from g3o.run.presweep.records import (
    _read_master,
    _utc_iso,
    _utc_today,
    institution_record,
    synth_institution_id,
)
from g3o.run.presweep.sampling import stratified_sample
from g3o.run.telemetry import preserve_identity
from g3o.scrape import egress

_INSTITUTION_UID_RE = re.compile(INSTITUTION_UID_PATTERN)


def _institution_uids(sample: list[dict[str, Any]]) -> dict[str, str]:
    """``{institution_id: institution_uid}`` off the raw master rows.

    Read here rather than through :func:`institution_record` on purpose: that
    projection is serialised to ``institution.json`` and embedded verbatim in
    the Stage 2/3/5/6 user prompts, and the uid is bookkeeping that must not
    reach a model (PI ruling 2026-08-14 §3). Same reasoning as the accuracy
    canary's ground-truth read in ``stage_classify``.

    Raises:
        RuntimeError: when any sampled row carries no well-formed
            ``institution_uid``. Refusing at plan time is the point — the
            alternative is discovering it at ingest, after the compute is
            spent, one quarantined row at a time.
    """
    uids: dict[str, str] = {}
    bad: list[str] = []
    for row in sample:
        inst_id = synth_institution_id(row)
        uid = (row.get("institution_uid") or "").strip()
        if not _INSTITUTION_UID_RE.match(uid):
            bad.append(f"{inst_id} (master_row_id={row.get('master_row_id', '')!r}): {uid!r}")
            continue
        uids[inst_id] = uid
    if bad:
        raise RuntimeError(
            f"{len(bad)} sampled institution(s) carry no well-formed institution_uid "
            f"(expected {INSTITUTION_UID_PATTERN}); the master CSV must supply it and "
            "the pipeline will not mint one. First 5: " + "; ".join(bad[:5])
        )
    return uids


def config_snapshot(config: PresweepConfig) -> dict[str, Any]:
    """The JSON-serializable ``PresweepConfig`` snapshot the manifest stores.

    Extracted from :func:`build_manifest` so the snapshot the manifest *stores*
    and the snapshot ``config_hash`` is computed *over* cannot be two different
    dicts — the failure mode being a hash nothing can reproduce from the manifest
    it sits in.
    """
    config_dict: dict[str, Any] = asdict(config)
    config_dict["runs_dir"] = str(config.runs_dir)
    config_dict["master_csv"] = str(config.master_csv)
    config_dict["stratify_keys"] = list(config.stratify_keys)
    config_dict["discovery_languages"] = list(config.discovery_languages)
    # institution_search_languages is a derived property (not a dataclass
    # field), so asdict() above doesn't pick it up — record it explicitly so
    # the manifest and the resume guard below still see it.
    config_dict["institution_search_languages"] = config.institution_search_languages
    # The GenAI-term roster is a module constant in discovery/query_builder.py,
    # not a config field, so asdict() above never saw it and the resume guard
    # had nothing to compare: a run could be resumed against an edited roster —
    # a different query surface, and so a different discovery instrument — with
    # nothing noticing. Recorded explicitly here for the same reason
    # institution_search_languages is, and guarded below.
    config_dict["genai_terms_roster_hash"] = genai_terms_roster_hash()
    # Language policy (2026-08-30). Two keys, for two different failure modes.
    #
    # ``language_policy_hash`` is the roster-hash argument one level up: the
    # signed mapping is a file in the tree, so a run resumed after an edit to
    # it is running a different language instrument than it launched with, and
    # the F7 guard can only see that if the policy has a fingerprint. The id
    # alone would not — an amended ``2026-08-30`` is still ``2026-08-30``.
    #
    # ``institution_search_languages`` is overwritten because under a policy the
    # run has no single answer and the derived property's value is the run-level
    # configuration, not what any row was searched in. Leaving ``"en"`` there
    # would let a reader compute "this run searched English only" off the
    # manifest of a run that issued 91 languages — the A7 misattribution, at the
    # run level. The replacement is deliberately not a language tag: nothing
    # should be able to parse it as one.
    if config.language_policy is None:
        config_dict["language_policy_hash"] = None
    else:
        config_dict["language_policy_hash"] = language_policy_hash(
            config.signed_language_policy
        )
        config_dict["institution_search_languages"] = (
            f"per-institution: language policy {config.language_policy}"
        )
    return config_dict


def build_manifest(
    config: PresweepConfig,
    sample: list[dict[str, Any]],
    *,
    n_strata_observed: int | None = None,
    telemetry_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The run manifest: planning state, plus the §4.1 telemetry block when given.

    One file, two readers, because Run API spec §4.1 names this exact path for the
    telemetry manifest and the planning manifest was already here. They compose
    rather than collide: ``config`` serves as both the planning snapshot and §4.1's
    config snapshot, and ``telemetry_block`` contributes the identity keys
    (``run_started_at``, ``code``, ``contract``, ``credentials``, …).

    ``telemetry_block=None`` — a direct ``run_presweep`` call, and every test that
    predates the Run API — produces the pre-spec manifest byte for byte. Telemetry
    arrives only through ``launch()``, which is what §4.1 says writes it.

    Note the ``config`` snapshot keeps the two derived values the resume guard
    compares (``institution_search_languages``, ``genai_terms_roster_hash``). The
    published fixture describes ``config`` as declared fields only; reality wins
    here, because moving those two out of ``config`` to satisfy the fixture would
    mean rewriting a load-bearing guard to satisfy a document. The backend stores
    the snapshot as ``jsonb`` (§5.2), so two extra keys cost the loader nothing —
    the fixture's *note* needs correcting, not this shape.
    """
    config_dict = config_snapshot(config)
    stages_planned = list(STAGES[: STAGES.index(config.stop_after) + 1])
    manifest: dict[str, Any] = {
        "run_id": config.run_id,
        "run_kind": "pre-sweep",
        # Storage layout marker (docs/storage-layout-v2.md §B2). Every reader
        # calls g3o.common.paths.require_layout on entry and refuses a tree
        # that does not declare this exact version — there is no dual-layout
        # read support.
        "layout_version": LAYOUT_VERSION,
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
        # Key layer (PI ruling 2026-08-14). The manifest carries the master's
        # institution_uid so Stage 7 can stamp it without the value ever
        # entering a prompt; read back by
        # :func:`g3o.common.paths.institution_uid_map`.
        INSTITUTION_UIDS_KEY: _institution_uids(sample),
        # Which egress Stage 4 left from (#90, 2026-08-26). Recorded at plan
        # time, next to the other identity keys rather than inside ``config``:
        # the proxy is an environment parameter like ``USER_AGENT`` and
        # ``RENDER_RECYCLE_AFTER``, so putting it in the config snapshot would
        # change ``config_hash`` for every run past and future to record
        # something no ``PresweepConfig`` field holds. Credentials never appear —
        # ``egress.describe()`` is mode, host:port, and a ``credentialed`` flag.
        # Guarded on resume below: a run whose egress changed halfway measured
        # two different instruments.
        "run_egress": egress.describe(),
    }
    if telemetry_block:
        manifest.update(telemetry_block)
    return manifest


def _write_manifest_atomic(path: Path, manifest: dict[str, Any]) -> None:
    """Temp file + ``os.replace`` — the ``run_state`` pattern (§4.1).

    The temp name carries pid and thread id so two writers never collide on it
    before either replace lands, matching the cache writers this repo already
    hardened for concurrency.
    """
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)


def write_run_layout(
    config: PresweepConfig,
    sample: list[dict[str, Any]],
    *,
    manifest: dict[str, Any],
) -> Path:
    """Create ``runs/<run_id>/`` with manifest + per-institution dirs.

    Institution dirs are sharded under ``institutions/<shard>/`` (storage
    layout v2, ``docs/storage-layout-v2.md`` §B1); the shard level is created
    on demand by :func:`g3o.common.paths.institution_dir` + ``parents=True``.

    Idempotent: existing directories are preserved; ``manifest.json`` is
    rewritten. ``inputs/`` is never touched.

    Two changes the Run API brought here (spec §4.1). The write is **atomic**
    (temp file + ``os.replace``), because the manifest is now the record a run is
    ingested from and a half-written one after a crash would be an uningestable
    run rather than a re-plannable one. And a resume **preserves the launching
    run's identity**: before this, every invocation refreshed ``run_timestamp``,
    so a resumed run reported the resume moment as its start — and
    ``run_started_at`` is authoritative for wave classification (§5.5), so that
    would have filed a resumed run into whichever window the resume fell in.
    """
    run_dir = config.runs_dir / config.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
        if existing.get("manifest_schema_version"):
            manifest = preserve_identity(existing, manifest)
    _write_manifest_atomic(manifest_path, manifest)
    for row in sample:
        institution = institution_record(row)
        inst_dir = institution_dir(run_dir, institution["institution_id"])
        inst_dir.mkdir(parents=True, exist_ok=True)
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
    # Chain-mode query surface (added 2026-08-02). These were written to the
    # manifest by ``asdict`` from the day the chain shipped but never compared,
    # so a run started in ``chain`` could be resumed in ``legacy`` — a
    # different instrument, different credit cost, and a silently mixed run —
    # without the F7 guard noticing. ``discovery_evidence_terms`` decides which
    # token every leg-2 query carries, which is the same class of methodology
    # surface as the roster A4 covers.
    "discovery_mode",
    "discovery_evidence_term",
    "discovery_evidence_terms",
    # Language policy (added 2026-08-30). The id names which signed mapping ran;
    # the hash catches an edit to that mapping under an unchanged id. Both are
    # the same class of surface as the roster hash beside them — they decide
    # which languages every leg-2 query of every institution is issued in.
    "language_policy",
    "language_policy_hash",
    "discovery_domain_quote_name",
    "serper_autocorrect",
    "model",
    # Scrape/extract job semantics (added 2026-08-04). Same class of gap as the
    # chain keys above: written to the manifest by ``asdict`` since they
    # shipped, never compared. Flipping any of them across a resume leaves the
    # artifacts already on disk inconsistent with a fresh projection — the cap
    # pair decides how much of a page the extractor ever sees and which end
    # survives, ``empty_page_min_chars`` decides what was dropped as empty, and
    # the three scrape knobs decide which URLs were fetched at all and under
    # what politeness regime.
    "empty_page_min_chars",
    "extract_text_cap_chars",
    "extract_text_cap_rule",
    "scrape_respect_robots",
    "scrape_host_delay_seconds",
    "scrape_render_on_download_failure",
    # Issue #96. Same class as the three above — it decides which URLs were
    # fetched at all. Guarded specifically because raising it across a resume
    # produces an institution that holds both a page and a stale
    # ``crawl_delay_exceeded`` row for the same URL, and the ledger is
    # append-only, so that institution reports PROCESSING_FAILED for the rest
    # of the run's life with no way to tell it from a real one.
    "scrape_max_institution_seconds",
    # Roster fingerprint (A4) — see build_manifest. Not a dataclass field; the
    # manifest carries it because the guard needs something to compare.
    "genai_terms_roster_hash",
)

# Guarded keys whose *absence* from the on-disk manifest is tolerated: a run
# launched before the key existed cannot carry it, so it is compared only when
# recorded. This is the same concession
# :func:`_assert_manifest_matches_on_resume` already makes for
# ``run_generation_parameters``; a key that is recorded and differs still
# aborts.
#
# Membership is a resume-semantics decision, not a refactor (PI, 2026-08-04):
# it trades one unchecked field on pre-existing runs against forcing a fresh
# launch, and the alternative quietly pressures operators into hand-editing
# manifests — strictly worse, because that defeats every other key too.
# Deliberately does **not** cover the chain keys above: those stay strict, so a
# manifest predating the chain still refuses to resume rather than let a mode
# flip through unchecked.
#
# What it buys *today* is nothing, and that is worth stating so the next person
# does not over-read it (verified 2026-08-05, review session). ``build_manifest``
# writes ``layout_version`` and this key together, so the only manifest lacking
# the roster hash also lacks the layout marker — and ``require_layout`` refuses
# that tree a few lines later in ``run_presweep`` regardless. Without the
# tolerance the same run still cannot proceed; only which line reports the
# refusal changes. The one manifest where it is load-bearing is a run launched
# off an unmerged storage-v2 phase branch and resumed after the merge, and no
# such run exists. It is kept as the precedent mechanism for the *next* guarded
# key added to a manifest that predates it (the key-contract work adds several),
# not as protection for this one.
#
# ``scrape_max_institution_seconds`` (issue #96, 2026-08-26) is the first key to
# use this mechanism for what the paragraph above describes: it is guarded, and
# every manifest written before it existed lacks it, including the published run
# ``r20260824T215623Z-bb4e``. Tolerating its absence lets such a run resume; a
# manifest that *does* record it and differs still aborts.
_ABSENT_TOLERATED_CONFIG_KEYS: frozenset[str] = frozenset(
    {"genai_terms_roster_hash", "scrape_max_institution_seconds"}
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
        if key not in old_cfg and key in _ABSENT_TOLERATED_CONFIG_KEYS:
            continue  # manifest predates the key — nothing to compare
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
    # Egress is run identity for the same reason the generation parameters are
    # (#90): the measured recovery from changing it is ~76% of the
    # all-fetch-failed population, so a run that scraped half its institutions
    # direct and half through a proxy has two different scrape instruments in one
    # artifact and no column saying which. Absent-tolerated on the same
    # precedent as ``genai_terms_roster_hash``: manifests written before
    # 2026-08-26 have no ``run_egress``, and refusing to resume them would be a
    # cost with no safety gain, since every one of them predates the proxy
    # existing and so ran direct by construction.
    old_egress = existing.get("run_egress")
    new_egress = new_manifest.get("run_egress")
    if old_egress is not None and old_egress != new_egress:
        diffs.append(
            f"run_egress: {old_egress!r} (manifest) != {new_egress!r} (this run)"
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


def plan_run(
    config: PresweepConfig, *, telemetry: Any | None = None
) -> RunPlan:
    """Read master, draw sample, write manifest + per-institution dirs. No live calls.

    On resume (``_state/`` present) the freshly drawn sample + guarded config are
    checked against the existing manifest *before* anything is overwritten
    (review F7); a mismatch aborts with a diff.
    """
    # Before the master read, because this is the cheapest possible failure and
    # a misconfigured egress is the most expensive one to discover late (#90,
    # 2026-08-27): a proxy URL requests cannot parse does not stop a run, it
    # fails every fetch individually, so the run completes and reports a
    # collapsed yield that looks like the network rather than like a typo.
    # No-op when no proxy is set, which is the default and the common case.
    egress.validate()
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
    # The §4.1 telemetry block needs the drawn sample (for the master build id)
    # and the config snapshot (for config_hash), so it is built here, between the
    # draw and the write — still before any spend, which is what §4.1 requires.
    telemetry_block = None
    if telemetry is not None and telemetry.enabled:
        telemetry_block = telemetry.manifest_block_for(
            config, sample, config_snapshot=config_snapshot(config)
        )
    manifest = build_manifest(
        config, sample,
        n_strata_observed=n_strata_observed,
        telemetry_block=telemetry_block,
    )
    _assert_manifest_matches_on_resume(config.runs_dir / config.run_id, manifest)
    run_dir = write_run_layout(config, sample, manifest=manifest)
    return RunPlan(run_dir=run_dir, sample=sample, manifest=manifest)
