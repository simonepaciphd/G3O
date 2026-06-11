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
"""

from __future__ import annotations

import csv
import json
import logging
import random
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from g3o.classify.official_site import (
    build_official_site_job,
    parse_official_site_result,
)
from g3o.classify.url_triage import build_triage_job, parse_triage_result
from g3o.common import attrition
from g3o.common import config as _config
from g3o.common.batch_client import DEFAULT_MODEL, BatchResult
from g3o.common.run_state import (
    is_done,
    load_state,
    mark_done,
    run_chunked_stage,
    state_dir,
)
from g3o.discovery.query_builder import build_queries
from g3o.discovery.serper_client import (
    SerperRequestError,
    build_site_query,
    search_google,
    set_live_mode,
)
from g3o.extract import (
    build_extract_jobs,
    parse_extract_result,
)
from g3o.extract.batch import (
    DEFAULT_TEXT_CAP_CHARS,
    DEFAULT_TEXT_CAP_RULE,
    EMPTY_PAGE_MIN_CHARS,
    cap_page_text,
    is_near_empty,
)
from g3o.scrape.fetcher import scrape_url
from g3o.scrape.politeness import (
    DEFAULT_HOST_DELAY_SECONDS,
    HostThrottle,
    RobotsCache,
)
from g3o.scrape.render import RenderedPage, RenderSession

logger = logging.getLogger(__name__)


STRATIFY_KEYS: tuple[str, ...] = ("country", "government_level", "institution_type")
STAGES: tuple[str, ...] = (
    "discovery_general",
    "classify_official_site",
    "discovery_site_restricted",
    "classify_triage",
    "scrape",
    "extract",
    "validate",
)
StageName = Literal[
    "discovery_general",
    "classify_official_site",
    "discovery_site_restricted",
    "classify_triage",
    "scrape",
    "extract",
    "validate",
]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class PresweepConfig:
    run_id: str
    runs_dir: Path
    master_csv: Path
    sample_size: int = 1000
    seed: int = 22294
    stratification: Literal["equal"] = "equal"  # only equal in Session B
    stratify_keys: tuple[str, ...] = STRATIFY_KEYS
    institution_search_languages: str = "en"
    discovery_languages: tuple[str, ...] = ("en",)
    discovery_results_per_query: int = 5
    dry_run: bool = True
    stop_after: StageName = "extract"
    poll_interval: int = 60
    max_wait_per_stage: int = 25 * 60 * 60  # 25h: SLA + jitter
    model: str = DEFAULT_MODEL
    # Stage 5 page-text handling (Session F.2, 2026-06-10). The cap is the D3
    # methodology decision (60k chars, head+tail); the empty-page floor is an
    # engineering parameter (review F5). Surfaced as config so both are
    # documented and overridable rather than buried as literals.
    extract_text_cap_chars: int = DEFAULT_TEXT_CAP_CHARS
    extract_text_cap_rule: str = DEFAULT_TEXT_CAP_RULE
    empty_page_min_chars: int = EMPTY_PAGE_MIN_CHARS
    # Stage 4 scrape politeness (review F14 / Decision D4, 2026-06-10).
    # ``scrape_respect_robots`` = D4 (respect robots.txt; Disallow'd URLs are
    # skipped and logged to the attrition ledger). ``scrape_host_delay_seconds``
    # is the per-host courtesy delay (robots Crawl-delay raises it per host).
    # ``scrape_render_on_download_failure`` keeps the dead-URL render fallback
    # off by default (review F14): rendering every failed GET is an
    # IP-reputation + wall-clock cost. All three are engineering parameters,
    # not methodology surfaces.
    scrape_respect_robots: bool = True
    scrape_host_delay_seconds: float = DEFAULT_HOST_DELAY_SECONDS
    scrape_render_on_download_failure: bool = False


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------


def stratified_sample(
    rows: list[dict[str, Any]],
    *,
    sample_size: int,
    seed: int,
    stratify_keys: tuple[str, ...] = STRATIFY_KEYS,
) -> list[dict[str, Any]]:
    """Equal-per-stratum stratified random sample with deterministic seeding.

    When ``n_strata >= sample_size`` the sample takes one row from each of
    ``sample_size`` randomly-chosen strata. Otherwise each stratum gets a
    quota of ``sample_size // n_strata`` (with remainder distributed to a
    randomly-chosen subset), and any deficit (strata too small to fill their
    quota) is redistributed round-robin to strata that still have rows.
    """
    if sample_size <= 0:
        return []
    rng = random.Random(seed)
    strata: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for r in rows:
        key = tuple(r.get(k, "") for k in stratify_keys)
        strata.setdefault(key, []).append(r)
    if not strata:
        return []
    keys = sorted(strata.keys())
    rng.shuffle(keys)
    for k in keys:
        rng.shuffle(strata[k])
    n_strata = len(keys)
    if n_strata >= sample_size:
        return [strata[k][0] for k in keys[:sample_size]]
    base, rem = divmod(sample_size, n_strata)
    quotas = {k: base + (1 if i < rem else 0) for i, k in enumerate(keys)}
    picked: list[dict[str, Any]] = []
    deficit = 0
    for k in keys:
        avail = strata[k]
        take = min(quotas[k], len(avail))
        picked.extend(avail[:take])
        deficit += quotas[k] - take
        strata[k] = avail[take:]
    while deficit > 0:
        progressed = False
        for k in keys:
            if deficit == 0:
                break
            if strata[k]:
                picked.append(strata[k][0])
                strata[k] = strata[k][1:]
                deficit -= 1
                progressed = True
        if not progressed:
            break
    return picked


# ---------------------------------------------------------------------------
# Per-row projection
# ---------------------------------------------------------------------------


def synth_institution_id(row: dict[str, Any]) -> str:
    """Stable institution_id derived from ``master_row_id``."""
    raw = row.get("master_row_id", "")
    try:
        return f"INST-{int(raw):07d}"
    except (TypeError, ValueError):
        return f"INST-{raw}"


def institution_record(row: dict[str, Any]) -> dict[str, Any]:
    """Project a master CSV row into the institution-row shape Stages 2/3/5 expect.

    ``official_site_url`` (and the optional ``official_site_confidence``) is the
    Stage 2 bypass column owned by WS3 round-2 (spec §6 master-schema dependency,
    2026-05-09). Pre-rollout the column is missing and the projection records
    ``None``; the runner's bypass guard treats ``None`` as "Stage 2 LLM path runs
    as before."
    """
    return {
        "institution_id": synth_institution_id(row),
        "institution_name": row.get("institution_name", ""),
        "country": row.get("country", ""),
        "branch_of_government": row.get("branch", ""),
        "level_of_government": row.get("government_level", ""),
        "institution_type": row.get("institution_type", ""),
        "website": row.get("website") or None,
        "official_site_url": row.get("official_site_url") or None,
        "official_site_confidence": row.get("official_site_confidence") or None,
        "master_row_id": row.get("master_row_id", ""),
    }


def _read_master(path: Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        yield from csv.DictReader(f)


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _dedupe_key(url: str) -> str:
    """Path-aware dedup key for the Stage 1a + 1b URL union (Q3=c, 2026-05-09).

    Folds scheme/netloc casing, drops a leading ``www.``, strips a trailing slash
    from non-root paths, and removes the fragment. Query string and ``;params``
    are left intact (Q3=c rejected aggressive query-param normalization).
    Falls back to the raw URL if parsing fails.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path
    if path.endswith("/"):
        path = path[:-1]  # strip uniformly; root "/" → "" for consistency
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def _site_domain(url: str) -> str | None:
    """Domain extractor for ``site:`` query construction. ``None`` if unparseable."""
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    netloc = parsed.netloc.lower().removeprefix("www.")
    return netloc or None


# ---------------------------------------------------------------------------
# Manifest + per-institution layout
# ---------------------------------------------------------------------------


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
    stages_planned = list(STAGES[: STAGES.index(config.stop_after) + 1])
    return {
        "run_id": config.run_id,
        "run_kind": "pre-sweep",
        "run_date": _utc_today(),
        "run_timestamp": _utc_iso(),
        "run_model": config.model,
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


# ---------------------------------------------------------------------------
# Stage runners (--execute mode)
# ---------------------------------------------------------------------------
#
# Resume semantics (Session E, 2026-05-09; chunked Session F.1, 2026-06-10):
#
# Each ``_run_*`` runner is state-aware (Q7=c — auto-inferred from disk):
#
# 1. ``is_done(run_dir, stage)`` → reconstruct the runner's return dict from
#    per-institution artifacts on disk and skip the stage entirely (Q3=e2).
# 2. Active state file present (LLM stages only) → the chunk plan in the
#    state file is canonical (Q4=ii): fetched chunks are skipped, in-flight
#    chunks rejoin polling, not-yet-submitted chunks reconcile-then-submit.
#    All of this lives in ``g3o.common.run_state.run_chunked_stage``; the
#    runners just build the deterministic job list and a persist callback.
# 3. No state, no done marker → fresh run; deterministic stages also support
#    per-artifact skip-if-exists for partial-recovery without a ``.done`` marker.
#
# Failed/cancelled/expired batches do NOT auto-resubmit (Q3=d). The active
# state file remains and the orchestrator raises with the path to the file.


# ---------------------------------------------------------------------------
# Resume helpers — reconstruct each stage's return dict from disk
# ---------------------------------------------------------------------------


def _read_existing_discovery_general(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = run_dir / inst_id / "1a_discovery_general.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[inst_id] = payload.get("records", [])
    return out


def _read_existing_discovery_site_restricted(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = run_dir / inst_id / "1b_discovery_site_restricted.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[inst_id] = payload.get("records", [])
    return out


def _read_existing_official_sites(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, str | None]:
    """Reconstruct Stage 2 output from per-institution ``2_official_site.json``.

    Both bypass envelopes (``{"bypassed": true, ..., "url": ...}``) and parsed
    classifier results (``{"url": ..., "confidence": ..., "rationale": ...}``)
    expose ``url`` at the top level, so the caller treats them uniformly.
    """
    out: dict[str, str | None] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = run_dir / inst_id / "2_official_site.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[inst_id] = payload.get("url")
    return out


def _read_existing_triaged(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = run_dir / inst_id / "3_triage.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        decisions = payload.get("decisions", [])
        out[inst_id] = [d["url"] for d in decisions if d.get("decision") == "keep"]
    return out


def _read_existing_scraped(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[RenderedPage]]:
    out: dict[str, list[RenderedPage]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        scrape_dir = run_dir / inst_id / "scrape"
        if not scrape_dir.is_dir():
            continue
        pages: list[RenderedPage] = []
        for path in sorted(scrape_dir.glob("*.json")):
            pages.append(RenderedPage.model_validate_json(path.read_text(encoding="utf-8")))
        out[inst_id] = pages
    return out


def _count_existing_extracts(run_dir: Path, sample: list[dict[str, Any]]) -> int:
    n = 0
    for row in sample:
        inst_id = synth_institution_id(row)
        extract_dir = run_dir / inst_id / "extract"
        if extract_dir.is_dir():
            n += sum(1 for _ in extract_dir.glob("*.json"))
    return n


def _run_discovery_general(
    run_dir: Path,
    sample: list[dict[str, Any]],
    *,
    languages: tuple[str, ...],
    num_results: int,
) -> dict[str, list[dict[str, Any]]]:
    """Stage 1a — general Serper queries. One ``1a_discovery_general.json`` per institution.

    Resume (Session E): when ``.done/discovery_general.json`` is present, skip
    Serper entirely and reconstruct the records dict from disk. Without a done
    marker, per-institution skip-if-exists protects partial recovery (each
    institution whose ``1a_discovery_general.json`` already exists is loaded
    instead of re-querying Serper — a paid call).
    """
    stage = "discovery_general"
    if is_done(run_dir, stage):
        logger.info("Stage 1a: .done marker present — skipping (resume from disk)")
        return _read_existing_discovery_general(run_dir, sample)
    out: dict[str, list[dict[str, Any]]] = {}
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        path = run_dir / inst_id / "1a_discovery_general.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            out[inst_id] = payload.get("records", [])
            continue
        queries = build_queries(institution["institution_name"], list(languages))
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for query, lang in queries:
            try:
                hits = search_google(query, num_results=num_results)
            except SerperRequestError as exc:
                # Honest failure (review F1): record and abort the stage rather
                # than persist a partial artifact that looks like "found
                # nothing". The institution's 1a file is NOT written and the
                # stage is NOT marked done, so resume retries this institution.
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="serper_request_failed", url=query, detail=str(exc),
                )
                raise
            for r in hits:
                url = r.get("link", "")
                if url and url not in seen:
                    seen.add(url)
                    records.append({**r, "query": query, "language": lang})
        out[inst_id] = records
        path.write_text(
            json.dumps(
                {
                    "queries": [{"query": q, "language": lang} for q, lang in queries],
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    mark_done(run_dir, stage, no_batch=True)
    return out


def _run_discovery_site_restricted(
    run_dir: Path,
    sample: list[dict[str, Any]],
    official_sites: dict[str, str | None],
    *,
    languages: tuple[str, ...],
    num_results: int,
) -> dict[str, list[dict[str, Any]]]:
    """Stage 1b — site-restricted Serper queries (revision 2026-05-09, D1–D2).

    For each institution with a known official site (from Stage 2 LLM output or
    the Stage 2 bypass envelope), reuse :func:`build_queries` with the same
    multilingual GenAI-term roster (Q1=a, 2026-05-09) and wrap each query with
    the ``site:<domain>`` operator from :func:`build_site_query`. Per Q1, the
    query count matches Stage 1a one-for-one.

    Per Q2=a (2026-05-09), institutions with no usable official site (Stage 2
    returned ``None`` and no master bypass) are skipped: no 1b queries are
    issued and no ``1b_discovery_site_restricted.json`` is written. Stage 3
    triage will see only the 1a URL set for those institutions.

    Resume (Session E): same shape as Stage 1a — done-marker short-circuit +
    per-institution skip-if-exists protect Serper spend on partial recovery.
    """
    stage = "discovery_site_restricted"
    if is_done(run_dir, stage):
        logger.info("Stage 1b: .done marker present — skipping (resume from disk)")
        return _read_existing_discovery_site_restricted(run_dir, sample)
    out: dict[str, list[dict[str, Any]]] = {}
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        path = run_dir / inst_id / "1b_discovery_site_restricted.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            out[inst_id] = payload.get("records", [])
            continue
        site_url = official_sites.get(inst_id)
        if not site_url:
            continue
        domain = _site_domain(site_url)
        if not domain:
            logger.warning(
                "Stage 1b: %s skipped — official_site_url=%r unparseable", inst_id, site_url
            )
            attrition.record(
                run_dir, institution_id=inst_id, stage=stage,
                reason="official_site_unparseable", url=site_url,
            )
            continue
        base_queries = build_queries(institution["institution_name"], list(languages))
        wrapped = [(build_site_query(q, domain), lang) for q, lang in base_queries]
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        for query, lang in wrapped:
            try:
                hits = search_google(query, num_results=num_results)
            except SerperRequestError as exc:
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="serper_request_failed", url=query, detail=str(exc),
                )
                raise
            for r in hits:
                url = r.get("link", "")
                if url and url not in seen:
                    seen.add(url)
                    records.append(
                        {**r, "query": query, "language": lang, "site_domain": domain}
                    )
        out[inst_id] = records
        path.write_text(
            json.dumps(
                {
                    "site_domain": domain,
                    "queries": [{"query": q, "language": lang} for q, lang in wrapped],
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    mark_done(run_dir, stage, no_batch=True)
    return out


def _run_classify_official_site(
    run_dir: Path,
    sample: list[dict[str, Any]],
    discovery: dict[str, list[dict[str, Any]]],
    *,
    run_id: str,
    model: str,
    poll_interval: int,
    max_wait: int,
) -> dict[str, str | None]:
    """Stage 2 — official-site classifier batch, with master-CSV bypass guard.

    Bypass (revision 2026-05-09, D1+D4): when the institution row's
    ``official_site_url`` is non-null (WS3 round-2 column), skip the LLM submit/
    poll path entirely and write a ``2_official_site.json`` envelope of the form
    ``{"bypassed": true, "source": "master_csv", "url": "<from master>"}``. Per
    Q4 (2026-05-09) no plausibility check is applied; the runner trusts the
    master. Pre-rollout the column is null everywhere, so every row falls
    through to the LLM path (current production behavior).

    Resume (Session E; chunked Session F.1):
      - ``.done/classify_official_site.json`` present → reconstruct ``out`` from
        per-institution ``2_official_site.json`` files and return.
      - Otherwise the jobs are rebuilt deterministically and handed to
        :func:`run_chunked_stage`, which owns chunking, reconciliation,
        polling, and resume (bypass envelopes rewritten idempotently).
      - All-bypassed sample → no batch submitted; ``mark_done(no_batch=True)``.
      - Mixed bypass + LLM → state file covers the LLM subset only;
        ``bypass_count`` recorded.
    """
    stage = "classify_official_site"
    if is_done(run_dir, stage):
        logger.info("Stage 2: .done marker present — skipping (resume from disk)")
        return _read_existing_official_sites(run_dir, sample)

    out: dict[str, str | None] = {}
    jobs = []
    bypass_count = 0
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        bypass_url = institution.get("official_site_url")
        if bypass_url:
            out[inst_id] = bypass_url
            bypass_count += 1
            inst_dir = run_dir / inst_id
            if inst_dir.exists():
                (inst_dir / "2_official_site.json").write_text(
                    json.dumps(
                        {"bypassed": True, "source": "master_csv", "url": bypass_url},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            continue
        candidate_urls = [r.get("link", "") for r in discovery.get(inst_id, [])]
        candidate_urls = [u for u in candidate_urls if u]
        if not candidate_urls:
            continue
        jobs.append(
            build_official_site_job(
                institution, candidate_urls, custom_id=inst_id
            )
        )
    if not jobs and load_state(run_dir, stage) is None:
        mark_done(run_dir, stage, no_batch=True)
        return out

    def _persist(results: Iterator[BatchResult]) -> None:
        for result in results:
            try:
                parsed = parse_official_site_result(result)
            except Exception as exc:
                logger.warning("Stage 2 parse failed for %s: %s", result.custom_id, exc)
                attrition.record(
                    run_dir, institution_id=result.custom_id, stage=stage,
                    reason="parse_failed", detail=str(exc),
                )
                continue
            out[result.custom_id] = parsed.url
            inst_dir = run_dir / result.custom_id
            if inst_dir.exists():
                (inst_dir / "2_official_site.json").write_text(
                    json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    run_chunked_stage(
        run_dir, stage, jobs,
        run_id=run_id, model=model,
        poll_interval=poll_interval, max_wait=max_wait,
        process_chunk_results=_persist, bypass_count=bypass_count,
    )
    # Disk is authoritative for chunks fetched by a prior (crashed) invocation;
    # this invocation's parses and bypasses override with identical content.
    return {**_read_existing_official_sites(run_dir, sample), **out}


def _candidate_urls_union(
    discovery_general: dict[str, list[dict[str, Any]]],
    discovery_site_restricted: dict[str, list[dict[str, Any]]],
    inst_id: str,
) -> list[str]:
    """Path-aware deduped union of 1a + 1b URLs for one institution (Q3=c)."""
    seen: set[str] = set()
    out: list[str] = []
    for source in (
        discovery_general.get(inst_id, []),
        discovery_site_restricted.get(inst_id, []),
    ):
        for r in source:
            url = r.get("link", "")
            if not url:
                continue
            key = _dedupe_key(url)
            if key in seen:
                continue
            seen.add(key)
            out.append(url)
    return out


def _run_classify_triage(
    run_dir: Path,
    sample: list[dict[str, Any]],
    discovery_general: dict[str, list[dict[str, Any]]],
    discovery_site_restricted: dict[str, list[dict[str, Any]]],
    official_sites: dict[str, str | None],
    *,
    run_id: str,
    model: str,
    poll_interval: int,
    max_wait: int,
) -> dict[str, list[str]]:
    """Stage 3 — URL triage batch over the dedup'd 1a+1b union.

    Per Q3=c (2026-05-09), the candidate set is the path-aware deduped union of
    Stage 1a and Stage 1b records (lowercase scheme + netloc, fold ``www.``,
    strip trailing slash on non-root paths, drop fragment; query string left
    intact). When 1b skipped (no official site), only 1a URLs are seen.

    Resume (Session E; chunked Session F.1): same shape as Stage 2 —
    done-marker short-circuit, then :func:`run_chunked_stage` owns chunking,
    reconciliation, polling, and no-auto-resubmit semantics.
    """
    stage = "classify_triage"
    if is_done(run_dir, stage):
        logger.info("Stage 3: .done marker present — skipping (resume from disk)")
        return _read_existing_triaged(run_dir, sample)

    candidates_by_inst: dict[str, list[str]] = {}
    # Always rebuild the candidates_by_inst lookup so parse_triage_result can
    # validate expected_urls round-trip; it's cheap (in-memory dedup union).
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        candidate_urls = _candidate_urls_union(
            discovery_general, discovery_site_restricted, inst_id
        )
        if candidate_urls:
            candidates_by_inst[inst_id] = candidate_urls

    jobs = []
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        candidate_urls = candidates_by_inst.get(inst_id)
        if not candidate_urls:
            continue
        jobs.append(
            build_triage_job(
                institution,
                candidate_urls,
                official_site=official_sites.get(inst_id),
                custom_id=inst_id,
            )
        )
    if not jobs and load_state(run_dir, stage) is None:
        mark_done(run_dir, stage, no_batch=True)
        return {}

    kept: dict[str, list[str]] = {}

    def _persist(results: Iterator[BatchResult]) -> None:
        for result in results:
            try:
                parsed = parse_triage_result(
                    result, expected_urls=candidates_by_inst.get(result.custom_id)
                )
            except Exception as exc:
                logger.warning("Stage 3 parse failed for %s: %s", result.custom_id, exc)
                attrition.record(
                    run_dir, institution_id=result.custom_id, stage=stage,
                    reason="parse_failed", detail=str(exc),
                )
                continue
            kept_urls = [d.url for d in parsed.decisions if d.decision == "keep"]
            kept[result.custom_id] = kept_urls
            inst_dir = run_dir / result.custom_id
            if inst_dir.exists():
                (inst_dir / "3_triage.json").write_text(
                    json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    run_chunked_stage(
        run_dir, stage, jobs,
        run_id=run_id, model=model,
        poll_interval=poll_interval, max_wait=max_wait,
        process_chunk_results=_persist,
    )
    # Disk covers chunks fetched by a prior invocation (resume).
    return {**_read_existing_triaged(run_dir, sample), **kept}


def _run_scrape(
    run_dir: Path,
    sample: list[dict[str, Any]],
    triaged: dict[str, list[str]],
    *,
    respect_robots: bool = True,
    host_delay_seconds: float = DEFAULT_HOST_DELAY_SECONDS,
    render_on_download_failure: bool = False,
    robots: RobotsCache | None = None,
) -> dict[str, list[RenderedPage]]:
    """Stage 4 — synchronous scrape per (institution × kept URL).

    Per-URL idempotency (Q5=a, Session E 2026-05-09): when the per-run output
    file ``runs/<run_id>/<inst_id>/scrape/<url_hash>.json`` already exists, the
    runner loads the cached :class:`RenderedPage` and skips ``scrape_url`` for
    that URL. The fetcher's global ``page_v2_<md5>`` cache continues to handle
    cross-run reuse below this layer; the runner-side guard protects partial
    crash-recovery within a run, where a partial scrape loop may have written
    some files before crashing.

    Politeness (review F14 / Decision D4, 2026-06-10): the runner owns the
    scrape-ethics policy that the low-level fetcher stays agnostic of. When
    ``respect_robots`` is True, each URL is checked against its host's
    robots.txt for the G3O user-agent; a ``Disallow`` skips the URL and records
    a ``robots_disallowed`` attrition entry (so coverage stays auditable). A
    per-host courtesy delay (``host_delay_seconds``, raised by any robots
    ``Crawl-delay``) throttles same-host requests, and a single reused
    :class:`RenderSession` serves every render fallback in the loop instead of
    launching a browser per URL. ``robots`` may be injected (tests); otherwise
    a run-scoped :class:`RobotsCache` is built when ``respect_robots``.
    """
    from g3o.extract.batch import url_hash

    stage = "scrape"
    if is_done(run_dir, stage):
        logger.info("Stage 4: .done marker present — skipping (resume from disk)")
        return _read_existing_scraped(run_dir, sample)
    if respect_robots and robots is None:
        robots = RobotsCache(_config.USER_AGENT)
    throttle = HostThrottle(host_delay_seconds)
    out: dict[str, list[RenderedPage]] = {}
    with RenderSession() as render_session:
        for row in sample:
            institution = institution_record(row)
            inst_id = institution["institution_id"]
            urls = triaged.get(inst_id, [])
            scrape_dir = run_dir / inst_id / "scrape"
            scrape_dir.mkdir(parents=True, exist_ok=True)
            pages: list[RenderedPage] = []
            for url in urls:
                output_path = scrape_dir / f"{url_hash(url)}.json"
                if output_path.exists():
                    # Q5=a per-run skip: load existing RenderedPage; no refetch.
                    pages.append(
                        RenderedPage.model_validate_json(
                            output_path.read_text(encoding="utf-8")
                        )
                    )
                    continue
                if robots is not None and not robots.allowed(url):
                    logger.info("Stage 4: robots.txt disallows %s — skipping", url)
                    attrition.record(
                        run_dir, institution_id=inst_id, stage=stage,
                        reason="robots_disallowed", url=url,
                    )
                    continue
                throttle.wait(
                    url,
                    extra_delay=robots.crawl_delay(url) if robots is not None else None,
                )
                try:
                    page = scrape_url(
                        url,
                        render_session=render_session,
                        prefer_render_on_download_failure=render_on_download_failure,
                    )
                except Exception as exc:
                    logger.warning("Stage 4 scrape failed for %s (%s): %s", inst_id, url, exc)
                    attrition.record(
                        run_dir, institution_id=inst_id, stage=stage,
                        reason="scrape_failed", url=url, detail=str(exc),
                    )
                    continue
                output_path.write_text(page.model_dump_json(indent=2), encoding="utf-8")
                pages.append(page)
            out[inst_id] = pages
    mark_done(run_dir, stage, no_batch=True)
    return out


def _run_extract(
    run_dir: Path,
    sample: list[dict[str, Any]],
    scraped: dict[str, list[RenderedPage]],
    *,
    institution_search_languages: str,
    model: str,
    poll_interval: int,
    max_wait: int,
    run_id: str,
    text_cap_chars: int = DEFAULT_TEXT_CAP_CHARS,
    text_cap_rule: str = DEFAULT_TEXT_CAP_RULE,
    empty_page_min_chars: int = EMPTY_PAGE_MIN_CHARS,
) -> int:
    """Stage 5 — per-page LLM extraction, batched across (institution × page).

    Resume (Session E; chunked Session F.1): same shape as Stages 2/3.
    Returns the on-disk count of ``<inst>/extract/*.json`` files once the
    stage is complete (equals the parsed-result count on a clean fresh run,
    and stays truthful across chunked resumes where earlier invocations
    already persisted some chunks).
    """
    from g3o.extract.batch import make_custom_id, url_hash

    stage = "extract"
    if is_done(run_dir, stage):
        logger.info("Stage 5: .done marker present — skipping (resume from disk)")
        return _count_existing_extracts(run_dir, sample)

    page_lookup: dict[str, tuple[str, RenderedPage]] = {}
    pairs: list[tuple[dict[str, Any], RenderedPage]] = []
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        for page in scraped.get(inst_id, []):
            # Empty-page filter (review F5): a page with no usable text must not
            # become a Stage 5 job — the contract's data:min_length=1 would
            # otherwise pressure the model to fabricate a row from nothing.
            if is_near_empty(page.text, min_chars=empty_page_min_chars):
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="empty_page_dropped", url=page.url,
                    detail=f"stripped_len={len(page.text.strip())}",
                )
                continue
            # Page-text cap (review F3 / D3): bound the LLM input; the on-disk
            # scrape artifact keeps full text. Record the truncation for audit.
            capped, truncated = cap_page_text(
                page.text, max_chars=text_cap_chars, rule=text_cap_rule
            )
            if truncated:
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="page_text_truncated", url=page.url,
                    detail=f"rule={text_cap_rule}", original_length=len(page.text),
                )
                page = page.model_copy(update={"text": capped})
            cid = make_custom_id(inst_id, page.url)
            pairs.append((institution, page))
            page_lookup[cid] = (inst_id, page)

    if not pairs and load_state(run_dir, stage) is None:
        mark_done(run_dir, stage, no_batch=True)
        return 0
    jobs = build_extract_jobs(
        pairs,
        batch_id=f"{run_id}-extract",
        institution_search_languages=institution_search_languages,
        # Provenance accuracy (review F18a): pass the run's actual model so
        # batch_metadata.model_label reflects it, instead of the literal
        # "gpt-5-nano" fallback in _user_prompt. Mirrors Stage 6's
        # build_consolidate_jobs(model_label=model).
        model_label=model,
    )

    def _persist(results: Iterator[BatchResult]) -> None:
        for result in results:
            institution_id, page = page_lookup.get(result.custom_id, (None, None))
            if institution_id is None or page is None:
                logger.warning(
                    "Stage 5 result %s did not match any input pair", result.custom_id
                )
                continue
            try:
                parsed = parse_extract_result(
                    result, scrape_access_date=page.fetch_metadata.access_date
                )
            except Exception as exc:
                logger.warning("Stage 5 parse failed for %s: %s", result.custom_id, exc)
                attrition.record(
                    run_dir, institution_id=institution_id, stage=stage,
                    reason="parse_failed", url=page.url, detail=str(exc),
                )
                continue
            extract_dir = run_dir / institution_id / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            (extract_dir / f"{url_hash(page.url)}.json").write_text(
                json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    run_chunked_stage(
        run_dir, stage, jobs,
        run_id=run_id, model=model,
        poll_interval=poll_interval, max_wait=max_wait,
        process_chunk_results=_persist,
    )
    return _count_existing_extracts(run_dir, sample)


def _run_validate(
    run_dir: Path,
    sample: list[dict[str, Any]],
    *,
    model: str,
    poll_interval: int,
    max_wait: int,
) -> dict[str, Any]:
    """Stage 6 — per-institution LLM consolidation (Session E fold, Q8=ii).

    Thin wrapper around :func:`g3o.validate.consolidate.run_consolidate`. The
    consolidate driver is itself state-aware (same ``_state/{stage}.json`` +
    ``.done/{stage}.json`` machinery as Stages 2/3/5), so resume semantics are
    uniform across all four LLM stages.
    """
    from g3o.validate.consolidate import run_consolidate

    institution_ids = [synth_institution_id(row) for row in sample]
    return run_consolidate(
        run_dir,
        institution_ids=institution_ids,
        model=model,
        poll_interval=poll_interval,
        max_wait=max_wait,
    )


# ---------------------------------------------------------------------------
# Orchestration entrypoints
# ---------------------------------------------------------------------------


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
    if diffs:
        raise RuntimeError(
            "Resume aborted: _state/ is present under "
            f"{state_dir(run_dir)} but the freshly drawn run does not match the "
            "existing manifest.json. This usually means the master CSV drifted "
            "(WS3 round-2 appends rows) or the CLI args differ from the original "
            "launch. Investigate and resolve before retrying:\n  - "
            + "\n  - ".join(diffs)
        )


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


def _assert_live_keys(config: PresweepConfig) -> None:
    """Hard-fail before a live run if a required API key is unset (review F1).

    Stage 1 discovery always needs Serper; Stages 2/3/5/6 need OpenAI. Failing
    fast at startup beats discovering a missing key after Serper spend (or, worse
    for Serper, silently returning mock results). The OpenAI check is skipped
    when ``--stop-after discovery_general`` means no LLM stage will run.
    """
    if not _config.SERPER_API_KEY:
        raise RuntimeError(
            "SERPER_API_KEY is not set, but --execute requires a live Serper key "
            "for Stage 1 discovery. Refusing to run with mock discovery. Set the "
            "key, or run without --execute (dry run)."
        )
    if config.stop_after != "discovery_general" and not _config.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set, but --execute beyond Stage 1a requires a "
            "live OpenAI key (Stages 2/3/5/6). Set the key, pass "
            "--stop-after discovery_general, or run a dry run."
        )


def run_presweep(config: PresweepConfig) -> dict[str, Any]:
    """End-to-end pre-sweep runner.

    Default ``config.dry_run=True`` writes the planning artifacts and returns;
    the per-stage ``--execute`` path runs Stages 1a/2/1b/3/4/5 (and 6 when
    ``stop_after="validate"``) live, blocking on each Batch API stage's
    terminal state via :func:`g3o.common.run_state.run_chunked_stage`.

    Resume (Session E, Q7=c): if ``--execute`` is invoked against an existing
    ``runs/<run_id>/`` with state files present, each stage runner auto-detects
    them and rejoins polling without re-submitting. Per-URL scrape idempotency
    (Q5=a) covers Stage 4 partial recovery.

    Live-mode gate (review F1, 2026-06-10): ``--execute`` hard-fails at startup
    if the required API keys are unset (no silent mock discovery), and switches
    the Serper client into live mode (no mock results, request failures raise
    rather than degrade to an empty artifact). The key assertion runs before the
    mode switch so a failed gate leaves global state untouched.
    """
    if not config.dry_run:
        _assert_live_keys(config)
    set_live_mode(not config.dry_run)
    plan = plan_run(config)
    summary: dict[str, Any] = {
        "run_id": config.run_id,
        "run_dir": str(plan.run_dir),
        "n_institutions": len(plan.sample),
        "dry_run": config.dry_run,
    }
    if config.dry_run:
        summary["next_step"] = (
            f"g3o presweep --execute --run-id {config.run_id} "
            f"--sample-size {config.sample_size} --seed {config.seed}"
        )
        return summary

    # Guarantee the attrition ledger exists for a live run (empty ⇒ nothing
    # dropped/degraded, a stronger signal than a missing file). Review F4/F15.
    attrition.ensure_ledger(plan.run_dir)

    discovery_general = _run_discovery_general(
        plan.run_dir,
        plan.sample,
        languages=config.discovery_languages,
        num_results=config.discovery_results_per_query,
    )
    summary["n_discovery_general"] = sum(len(v) for v in discovery_general.values())
    if config.stop_after == "discovery_general":
        return summary

    official_sites = _run_classify_official_site(
        plan.run_dir,
        plan.sample,
        discovery_general,
        run_id=config.run_id,
        model=config.model,
        poll_interval=config.poll_interval,
        max_wait=config.max_wait_per_stage,
    )
    summary["n_official_sites"] = sum(1 for v in official_sites.values() if v)
    summary["n_official_sites_bypassed"] = sum(
        1
        for row in plan.sample
        if institution_record(row).get("official_site_url")
    )
    if config.stop_after == "classify_official_site":
        return summary

    discovery_site_restricted = _run_discovery_site_restricted(
        plan.run_dir,
        plan.sample,
        official_sites,
        languages=config.discovery_languages,
        num_results=config.discovery_results_per_query,
    )
    summary["n_discovery_site_restricted"] = sum(
        len(v) for v in discovery_site_restricted.values()
    )
    if config.stop_after == "discovery_site_restricted":
        return summary

    triaged = _run_classify_triage(
        plan.run_dir,
        plan.sample,
        discovery_general,
        discovery_site_restricted,
        official_sites,
        run_id=config.run_id,
        model=config.model,
        poll_interval=config.poll_interval,
        max_wait=config.max_wait_per_stage,
    )
    summary["n_triaged_kept"] = sum(len(v) for v in triaged.values())
    if config.stop_after == "classify_triage":
        return summary

    scraped = _run_scrape(
        plan.run_dir,
        plan.sample,
        triaged,
        respect_robots=config.scrape_respect_robots,
        host_delay_seconds=config.scrape_host_delay_seconds,
        render_on_download_failure=config.scrape_render_on_download_failure,
    )
    summary["n_pages_scraped"] = sum(len(v) for v in scraped.values())
    if config.stop_after == "scrape":
        return summary

    n_extracted = _run_extract(
        plan.run_dir,
        plan.sample,
        scraped,
        institution_search_languages=config.institution_search_languages,
        model=config.model,
        poll_interval=config.poll_interval,
        max_wait=config.max_wait_per_stage,
        run_id=config.run_id,
        text_cap_chars=config.extract_text_cap_chars,
        text_cap_rule=config.extract_text_cap_rule,
        empty_page_min_chars=config.empty_page_min_chars,
    )
    summary["n_extracted"] = n_extracted
    if config.stop_after == "extract":
        return summary

    validate_summary = _run_validate(
        plan.run_dir,
        plan.sample,
        model=config.model,
        poll_interval=config.poll_interval,
        max_wait=config.max_wait_per_stage,
    )
    summary["n_consolidated"] = validate_summary.get("n_consolidated", 0)
    summary["n_validate_failed"] = validate_summary.get("n_failed", 0)
    summary["validate_batch_ids"] = validate_summary.get("batch_ids")
    return summary


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
    "write_run_layout",
]
