"""Pre-sweep stratified sample runner (Phase 3 of Session B, 2026-05-09).

Reads ``inputs/G3O_Institution_Master_v2/data_final/master_institutions.csv``
(read-only), draws a stratified random sample by
``country × government_level × institution_type`` (Q3=equal-per-stratum), and
either writes the planning artifacts only (``--dry-run``, default per Q8) or
runs the per-institution DAG live through Stage 5.

Per Q8 (2026-05-09, decision (b)): default mode is ``dry_run=True``. The
``--execute`` path is wired but not exercised in Session B; the staged launch
command is::

    g3o presweep --execute --run-id <id> --sample-size 1000 --seed 22294

Per Q2 (2026-05-09): production sample is ``N=1000``, ``seed=22294``.
Per Q3 (2026-05-09): equal-per-stratum stratification.

Package layout (T3 decomposition, Session F.8 2026-06-12 — pure refactor, no
behavior change): per-stage runner modules (``stage_discovery``,
``stage_classify``, ``stage_scrape``, ``stage_extract``, ``stage_validate``),
run planning/manifest lifecycle (``planning``), sampling (``sampling``),
row projection (``records``), config (``config``), and the thin dispatcher
(``orchestrator``). This ``__init__`` re-exports the pre-split module surface,
so ``g3o.run.presweep`` imports are unchanged.
"""

from g3o.run.presweep.config import (
    STAGES,
    STRATIFY_KEYS,
    PresweepConfig,
)
from g3o.run.presweep.config import (
    StageName as StageName,
)
from g3o.run.presweep.orchestrator import (
    _assert_live_keys as _assert_live_keys,
)
from g3o.run.presweep.orchestrator import (
    run_presweep,
)
from g3o.run.presweep.planning import (
    RunPlan,
    build_manifest,
    plan_run,
    update_manifest_llm_provenance,
    write_run_layout,
)
from g3o.run.presweep.planning import (
    _assert_manifest_matches_on_resume as _assert_manifest_matches_on_resume,
)
from g3o.run.presweep.records import (
    _dedupe_key as _dedupe_key,
)
from g3o.run.presweep.records import (
    institution_record,
    synth_institution_id,
)
from g3o.run.presweep.sampling import stratified_sample
from g3o.run.presweep.stage_classify import (
    _candidate_urls_union as _candidate_urls_union,
)
from g3o.run.presweep.stage_classify import (
    _run_classify_official_site as _run_classify_official_site,
)
from g3o.run.presweep.stage_classify import (
    _run_classify_triage as _run_classify_triage,
)
from g3o.run.presweep.stage_discovery import (
    _run_discovery_general as _run_discovery_general,
)
from g3o.run.presweep.stage_discovery import (
    _run_discovery_site_restricted as _run_discovery_site_restricted,
)
from g3o.run.presweep.stage_extract import _run_extract as _run_extract
from g3o.run.presweep.stage_filter import (
    _run_filter_eligibility as _run_filter_eligibility,
)
from g3o.run.presweep.stage_scrape import _run_scrape as _run_scrape
from g3o.run.presweep.stage_validate import _run_validate as _run_validate

__all__ = [
    "PresweepConfig",
    "RunPlan",
    "STAGES",
    "STRATIFY_KEYS",
    "build_manifest",
    "institution_record",
    "plan_run",
    "run_presweep",
    "stratified_sample",
    "synth_institution_id",
    "update_manifest_llm_provenance",
    "write_run_layout",
]
