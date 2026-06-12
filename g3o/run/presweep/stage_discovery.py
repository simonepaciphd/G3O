"""Stage 1a/1b runners — general + site-restricted Serper discovery."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.run_state import is_done, mark_done
from g3o.discovery.query_builder import build_queries
from g3o.discovery.serper_client import (
    SerperRequestError,
    build_site_query,
    search_google,
)
from g3o.run.presweep.records import (
    _site_domain,
    institution_record,
    synth_institution_id,
)

logger = logging.getLogger(__name__)


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
