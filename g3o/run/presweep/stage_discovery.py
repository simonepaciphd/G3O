"""Stage 1a/1b runners — general + site-restricted Serper discovery."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.run_state import is_done, mark_done
from g3o.common.timing import stage_timer
from g3o.discovery.domain_pick import pick_domain
from g3o.discovery.query_builder import (
    DEFAULT_EVIDENCE_TERM,
    build_domain_query,
    build_evidence_query,
    build_queries,
)
from g3o.discovery.serper_client import (
    SerperOptions,
    SerperRequestError,
    build_site_query,
    search_google_detailed,
)
from g3o.report.discovery_yield import registrable_domain
from g3o.run.presweep.concurrency import run_concurrent
from g3o.run.presweep.records import (
    _site_domain,
    institution_record,
    synth_institution_id,
)

logger = logging.getLogger(__name__)


def leg1_recall_block(
    master_website: str | None, records: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Did leg 1 surface the institution's own domain, and at what rank?

    This is the health report's one **uncontaminated** accuracy signal, and
    the metric docs/pipeline-status.md §5.1 says the report cannot reach:
    ``% with a usable domain`` reads ~100% because leg 1 nearly always returns
    *some* non-aggregator host, just not the right one. Recall against the
    master is the figure that actually moves when a query regresses — measured
    82.0% on n=200, 2026-08-01.

    It is computed here, at run time, for two reasons. The health report is
    disk-only by design and must not import the master. And no model is
    involved in this comparison, so unlike the Stage 2 pick (see
    ``stage_classify.ground_truth_block``) it cannot be inflated by the
    institution's ``website`` being visible in a prompt.

    Rank is leg 1's own result position, so a rising rank is the early warning
    that fires before recall itself moves.

    Coverage is the master's ``website`` column: ~2% of the registry, and
    national-institution-heavy. A regression canary, not a registry estimate.
    """
    if not master_website:
        return None
    master_domain = registrable_domain(master_website)
    if not master_domain:
        return None
    found = False
    rank: int | None = None
    for r in records:
        if registrable_domain(r.get("link", "")) == master_domain:
            found = True
            position = r.get("position")
            rank = position if isinstance(position, int) else None
            break
    return {
        "master_website": master_website,
        "master_domain": master_domain,
        "leg1_surfaced_domain": found,
        "leg1_rank": rank,
    }


# Language tag carried by both legs of the two-query chain.
#
# Load-bearing, not cosmetic. ``g3o.report.health`` and
# ``g3o.report.language_readiness`` attribute every URL to the language of the
# query that found it, and ``health._in_lang`` treats a *missing* tag as "not
# in any language" — so a leg that emitted untagged records would silently
# zero out every language-filtered health figure and the readiness bar the
# multilingual subproject depends on.
#
# ``"en"`` is the honest value for what this module builds: leg 1's
# ``official website`` suffix and leg 2's bare ``AI`` token are both English,
# whatever ``discovery_languages`` is set to. Native-language legs belong to
# ``subprojects/multilingual-pipeline/`` and must carry their own tag.
_CHAIN_LANG = "en"


def _query_provenance(query: str, lang: str, leg: str, result) -> dict[str, Any]:
    """One entry for an artifact's ``queries`` list, with Serper's echo.

    ``searchParameters`` is Serper's statement of which parameters it actually
    honoured. Recording it per query is what makes a silent parameter drop
    detectable after the fact: an unrecognised value is discarded with HTTP 200
    and no error, so its absence here is the only evidence.
    """
    return {
        "query": query,
        "language": lang,
        "leg": leg,
        "searchParameters": result.search_parameters,
        "from_cache": result.from_cache,
    }


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


def _discover_general_one(
    run_dir: Path,
    row: dict[str, Any],
    *,
    stage: str,
    languages: tuple[str, ...],
    num_results: int,
    mode: str = "legacy",
    options: SerperOptions | None = None,
    domain_quote_name: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """Process Stage 1a general discovery for one institution.

    Factored out of :func:`_run_discovery_general` so it can be called either
    from a plain loop or submitted to a thread pool unchanged (Stage 1a/1b/4
    concurrency, 2026-07).

    ``mode="legacy"`` is byte-for-byte the original behaviour: the eight-term
    four-slot roster from :func:`build_queries`, 8 credits/institution.

    ``mode="chain"`` (2026-08-01) repurposes Stage 1a as **domain discovery** —
    one ``<name> <country> <disambiguation> official website`` query, 1 credit.
    ``domain_quote_name`` binds the name as an exact phrase instead of a hint;
    see :func:`build_domain_query` for why that defaults off. It stops
    emitting GenAI queries entirely; the GenAI evidence job moves to Stage 1b's
    site-bound leg, and Stage 2's ``classify_official_site`` becomes the
    arbiter it already is architecturally (it receives the same shape of
    candidate-URL list it always did, just from a better query).

    In both modes the query list is a **list** that is unioned and deduped
    over, so drawing on the volume reserve later — an extra leg — stays a
    config change rather than a refactor (PI direction, 2026-08-01).
    """
    institution = institution_record(row)
    inst_id = institution["institution_id"]
    path = run_dir / inst_id / "1a_discovery_general.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return inst_id, payload.get("records", [])
    if not institution["country"]:
        logger.warning(
            "Stage 1a: %s (%r) has no country — discovery query is unscoped and "
            "may false-negative against a more prominent same-named institution",
            inst_id, institution["institution_name"],
        )
    with stage_timer(run_dir, inst_id, stage):
        if mode == "chain":
            # `disambiguation` off the raw master row, not the projected
            # institution record — same reason as the legacy branch below.
            queries = [
                (
                    build_domain_query(
                        institution["institution_name"],
                        institution["country"],
                        row.get("disambiguation") or "",
                        quote_name=domain_quote_name,
                    ),
                    _CHAIN_LANG,
                )
            ]
        else:
            # `disambiguation` is read off the raw master row, not the projected
            # institution record: that projection is serialized to institution.json
            # and fed to the Stage 2/3/5 LLM prompts, so adding a key there would
            # change model input as a side effect of a query change. `.get` keeps
            # pre-rollout masters (no such column) working.
            queries = build_queries(
                institution["institution_name"], list(languages),
                country=institution["country"],
                disambiguation=row.get("disambiguation") or "",
            )
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        leg = "domain_discovery" if mode == "chain" else "genai_roster"
        for query, lang in queries:
            try:
                result = search_google_detailed(
                    query, num_results=num_results, options=options
                )
            except SerperRequestError as exc:
                # Honest failure (review F1): record and abort rather than
                # persist a partial artifact that looks like "found nothing".
                # The institution's 1a file is NOT written, so resume (or,
                # under concurrency, the stage-level abort) retries it.
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="serper_request_failed", url=query, detail=str(exc),
                )
                raise
            provenance.append(_query_provenance(query, lang, leg, result))
            for r in result.results:
                url = r.get("link", "")
                if url and url not in seen:
                    seen.add(url)
                    records.append({**r, "query": query, "language": lang})
        artifact: dict[str, Any] = {
            "mode": mode,
            "queries": provenance,
            "records": records,
        }
        if mode == "chain":
            # The naive first-non-aggregator pick, recorded but NOT acted on:
            # Stage 2 still decides. Persisting it lets the confirmation run
            # score Stage 2's adjudication against the findings' 21/24 naive
            # baseline without paying for a second discovery pass. See
            # g3o.discovery.domain_pick.
            artifact["naive_domain"] = pick_domain(records)
            # Leg-1 recall against the master, read off the raw row for the
            # same reason `disambiguation` is above.
            truth = leg1_recall_block(row.get("website"), records)
            if truth is not None:
                artifact["ground_truth"] = truth
        path.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return inst_id, records


def _run_discovery_general(
    run_dir: Path,
    sample: list[dict[str, Any]],
    *,
    languages: tuple[str, ...],
    num_results: int,
    max_workers: int = 1,
    mode: str = "legacy",
    options: SerperOptions | None = None,
    domain_quote_name: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Stage 1a — general Serper queries. One ``1a_discovery_general.json`` per institution.

    Resume (Session E): when ``.done/discovery_general.json`` is present, skip
    Serper entirely and reconstruct the records dict from disk. Without a done
    marker, per-institution skip-if-exists protects partial recovery (each
    institution whose ``1a_discovery_general.json`` already exists is loaded
    instead of re-querying Serper — a paid call).

    Concurrency (2026-07): institutions run through
    :func:`g3o.run.presweep.concurrency.run_concurrent`, up to ``max_workers``
    at a time (default 1 = sequential, matching pre-concurrency behavior for
    any direct caller that doesn't pass it). On the first
    :class:`~g3o.discovery.serper_client.SerperRequestError`, in-flight
    institutions finish naturally and not-yet-started ones are cancelled,
    then that exception is re-raised — the stage is not marked done, so
    resume picks up exactly the institutions that never completed.
    """
    stage = "discovery_general"
    if is_done(run_dir, stage):
        logger.info("Stage 1a: .done marker present — skipping (resume from disk)")
        return _read_existing_discovery_general(run_dir, sample)
    out: dict[str, list[dict[str, Any]]] = {}
    results = run_concurrent(
        sample,
        lambda row: _discover_general_one(
            run_dir, row, stage=stage, languages=languages, num_results=num_results,
            mode=mode, options=options, domain_quote_name=domain_quote_name,
        ),
        max_workers=max_workers,
    )
    for inst_id, records in results:
        out[inst_id] = records
    mark_done(run_dir, stage, no_batch=True)
    return out


def _discover_site_restricted_one(
    run_dir: Path,
    row: dict[str, Any],
    official_sites: dict[str, str | None],
    *,
    stage: str,
    languages: tuple[str, ...],
    num_results: int,
    mode: str = "legacy",
    evidence_term: str = DEFAULT_EVIDENCE_TERM,
    options: SerperOptions | None = None,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Process Stage 1b site-restricted discovery for one institution.

    Factored out of :func:`_run_discovery_site_restricted` (Stage 1a/1b/4
    concurrency, 2026-07). Returns ``None`` for the Q2=a skip case (no usable
    official site) so the caller writes nothing for that institution.

    ``mode="legacy"`` wraps each of the eight four-slot roster queries in
    ``site:``, unchanged — the behaviour whose queries return zero results
    **93.2% of the time (179/192)**, because it repeats the institution name
    inside a query already bound to that institution's domain.

    ``mode="chain"`` issues one bare ``site:<domain> AI`` query, 1 credit. The
    token is unquoted and alone by measurement: extra English terms add 0 pp
    once site-bound, and OR-chaining them scores 4/24 against 16/24 for the
    bare token.
    """
    institution = institution_record(row)
    inst_id = institution["institution_id"]
    path = run_dir / inst_id / "1b_discovery_site_restricted.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return inst_id, payload.get("records", [])
    site_url = official_sites.get(inst_id)
    if not site_url:
        return None
    domain = _site_domain(site_url)
    if not domain:
        logger.warning(
            "Stage 1b: %s skipped — official_site_url=%r unparseable", inst_id, site_url
        )
        attrition.record(
            run_dir, institution_id=inst_id, stage=stage,
            reason="official_site_unparseable", url=site_url,
        )
        return None
    with stage_timer(run_dir, inst_id, stage):
        if mode == "chain":
            wrapped = [(build_evidence_query(domain, evidence_term), _CHAIN_LANG)]
        else:
            base_queries = build_queries(
                institution["institution_name"], list(languages),
                country=institution["country"],
                disambiguation=row.get("disambiguation") or "",
            )
            wrapped = [(build_site_query(q, domain), lang) for q, lang in base_queries]
        seen: set[str] = set()
        records: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        leg = "site_evidence" if mode == "chain" else "site_genai_roster"
        for query, lang in wrapped:
            try:
                result = search_google_detailed(
                    query, num_results=num_results, options=options
                )
            except SerperRequestError as exc:
                attrition.record(
                    run_dir, institution_id=inst_id, stage=stage,
                    reason="serper_request_failed", url=query, detail=str(exc),
                )
                raise
            provenance.append(_query_provenance(query, lang, leg, result))
            for r in result.results:
                url = r.get("link", "")
                if url and url not in seen:
                    seen.add(url)
                    records.append(
                        {**r, "query": query, "language": lang, "site_domain": domain}
                    )
        path.write_text(
            json.dumps(
                {
                    "mode": mode,
                    "site_domain": domain,
                    "queries": provenance,
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return inst_id, records


def _run_discovery_site_restricted(
    run_dir: Path,
    sample: list[dict[str, Any]],
    official_sites: dict[str, str | None],
    *,
    languages: tuple[str, ...],
    num_results: int,
    max_workers: int = 1,
    mode: str = "legacy",
    evidence_term: str = DEFAULT_EVIDENCE_TERM,
    options: SerperOptions | None = None,
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

    Concurrency (2026-07): same ``max_workers``/failure-propagation contract
    as :func:`_run_discovery_general`, via
    :func:`g3o.run.presweep.concurrency.run_concurrent`.
    """
    stage = "discovery_site_restricted"
    if is_done(run_dir, stage):
        logger.info("Stage 1b: .done marker present — skipping (resume from disk)")
        return _read_existing_discovery_site_restricted(run_dir, sample)
    out: dict[str, list[dict[str, Any]]] = {}
    results = run_concurrent(
        sample,
        lambda row: _discover_site_restricted_one(
            run_dir, row, official_sites,
            stage=stage, languages=languages, num_results=num_results,
            mode=mode, evidence_term=evidence_term, options=options,
        ),
        max_workers=max_workers,
    )
    for inst_id, records in results:
        out[inst_id] = records
    mark_done(run_dir, stage, no_batch=True)
    return out
