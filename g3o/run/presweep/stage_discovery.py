"""Stage 1 runners — the four Serper discovery legs.

Four legs, three artifacts, one query loop (:func:`_issue_queries`):

=====  ======================  ===================================  =====================
leg    stage                   query                                artifact
=====  ======================  ===================================  =====================
1      discovery_general       ``<name> <country> <disamb> official website``  1a
1'     discovery_general_fallback  the same, localized suffix, only where Stage 2 found no site  1a (rewritten)
2      discovery_site_restricted   ``site:<domain> <term>``, one per policy language  1b
open   discovery_evidence_open  ``"<name>" <country> <disamb> "<term>"``, one per policy language  1d
=====  ======================  ===================================  =====================

Legs 1 and 2 are the chain of 2026-08-01. The other two entered on 2026-09-03 on
the PI's direction, each behind its own ``PresweepConfig`` flag, default off, so a
run configured as before issues exactly the queries it issued before.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.credentials import ResolvedCredentials
from g3o.common.paths import institution_dir
from g3o.common.run_state import is_done, mark_done
from g3o.common.timing import stage_timer
from g3o.discovery.domain_pick import pick_domain
from g3o.discovery.query_builder import (
    DEFAULT_EVIDENCE_TERM,
    DOMAIN_QUERY_LANG,
    build_domain_queries,
    build_evidence_query,
    build_open_evidence_queries,
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

# ---------------------------------------------------------------------------
# Per-institution language selection (PI-signed policy, 2026-08-30)
#
# Both discovery legs took a run-level answer — one language tuple, one evidence
# -term dict, identical on every institution of the sample. The signed policy
# answers per country, so the two legs take an optional **resolver** instead: a
# callable handed the projected institution record, returning that row's answer.
#
# Optional, and ``None`` is the run-level path unchanged — byte-for-byte, on
# every run configured without a policy, which is every run to date. Exactly one
# of the pair answers a call: the resolver when given, the fixed argument
# otherwise. Not a precedence rule between two live values; the orchestrator
# passes a resolver only when ``PresweepConfig.language_policy`` is set, and the
# config refuses to carry both a policy and a non-default ``discovery_languages``.
# ---------------------------------------------------------------------------

#: Institution record -> the languages that institution's queries are issued in.
LanguagesFor = Callable[[Mapping[str, Any]], tuple[str, ...]]

#: Institution record -> that institution's leg-2 ``{language: term}`` map.
EvidenceTermsFor = Callable[[Mapping[str, Any]], Mapping[str, str]]


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


# Language tagging in chain mode.
#
# Load-bearing, not cosmetic. ``g3o.report.health`` and
# ``g3o.report.language_readiness`` attribute every URL to the language of the
# query that found it, and ``health._in_lang`` treats a *missing* tag as "not
# in any language" — so a leg that emitted untagged records would silently
# zero out every language-filtered health figure and the readiness bar the
# multilingual subproject depends on.
#
# Both legs now carry their own language per query, and each takes it from its
# own roster: leg 1 from ``DOMAIN_SUFFIX_BY_LANG``, leg 2 from the evidence-term
# roster. That is what makes a multi-language chain run honest at row level
# rather than collapsing to a single run-level claim.
#
# **Leg 1 was English on every institution until 2026-09-03** — its ``official
# website`` suffix was un-localized by PI decision 2026-08-02, so its tag was
# always ``DOMAIN_QUERY_LANG``, and the asymmetry between the legs was the point
# of the note that stood here. The PI reversed that on 2026-09-01 and shaped it
# on 2026-09-03: the first pass is still the one English query, and a second
# pass issues one localized query per non-English policy language only where
# Stage 2 found no site (``_run_discovery_general_fallback``). The tag still
# describes the query that was issued, never the language the run was
# configured for — which is why it comes from the suffix actually used, and why
# a tag with no roster row raises instead of falling back.
#
# ``discovery_leg1_multilingual`` defaults False, so a run configured without it
# still issues exactly one English leg-1 query per institution.
#
# Until 2026-08-02 both legs shared one ``"en"`` constant. That was honest
# about the queries but left ``institution_search_languages`` free to claim a
# language that was never issued; see ``PresweepConfig`` for the other half.


def _note_finding(record: dict[str, Any], query: str, lang: str) -> None:
    """Append a repeat finding of a URL this leg has already recorded.

    Dedup is by URL, so a URL returned by three of an institution's leg-2
    queries is written once. Before 2026-08-30 the losing queries were simply
    dropped, and nothing else recorded them: ``_query_provenance`` stores a
    query's *parameters*, never its result URLs, so the fact that the Arabic
    query also surfaced a page was unrecoverable from the artifact.

    That cost was paid in attribution, not in recall — the union is a true
    union and no URL is lost — but the attribution is what
    ``report.health._merge_url_langs`` and
    ``report.filter_eligibility._url_languages`` read to answer "which
    languages surfaced this URL". With one language per record those functions
    could only ever return a singleton, so a per-language health figure
    measured *which language got there first* and undercounted every language
    behind English in issue order. On a 90-language policy that is most of them.

    ``found_by`` records the whole set, first finder included, so the answer no
    longer depends on query order. It costs nothing: every query in the list was
    issued and paid for whether or not its results are written down.

    ``query`` and ``language`` on the record keep their first-finder meaning —
    they name the query whose title and snippet the record carries, which is
    still a single query's text.
    """
    found_by = record.setdefault(
        "found_by", [{"query": record["query"], "language": record["language"]}]
    )
    entry = {"query": query, "language": lang}
    if entry not in found_by:
        found_by.append(entry)


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


def _issue_queries(
    run_dir: Path,
    inst_id: str,
    stage: str,
    queries: list[tuple[str, str]],
    *,
    leg: str,
    num_results: int,
    options: SerperOptions | None,
    credentials: ResolvedCredentials | None,
    index: dict[str, int],
    records: list[dict[str, Any]],
    provenance: list[dict[str, Any]],
    record_extra: Mapping[str, Any] | None = None,
    provenance_extra: Mapping[str, Any] | None = None,
) -> int:
    """Issue ``queries`` and union their results into ``records`` in place.

    The one query loop every leg runs (2026-09-03; until then legs 1 and 2 each
    carried a copy). Dedup is by URL through ``index``: a URL already present
    gets a :func:`_note_finding` entry, a new one is appended with first-finder
    ``query``/``language`` and a one-entry ``found_by``. ``record_extra`` is
    merged into every *new* record (leg 2 stamps ``site_domain``);
    ``provenance_extra`` into every provenance entry (the fallback pass stamps
    ``pass``). Returns the number of records appended.

    A :class:`SerperRequestError` is recorded to the attrition ledger and
    re-raised (review F1): the caller must not persist a partial artifact that
    reads as "found nothing", so nothing is written here and the caller's
    skip-if-exists resume retries the institution.
    """
    n_new = 0
    for query, lang in queries:
        try:
            result = search_google_detailed(
                query, num_results=num_results, options=options,
                credentials=credentials,
            )
        except SerperRequestError as exc:
            attrition.record(
                run_dir, institution_id=inst_id, stage=stage,
                reason="serper_request_failed", url=query, detail=str(exc),
            )
            raise
        entry = _query_provenance(query, lang, leg, result)
        if provenance_extra:
            entry.update(provenance_extra)
        provenance.append(entry)
        for r in result.results:
            url = r.get("link", "")
            if not url:
                continue
            if url in index:
                _note_finding(records[index[url]], query, lang)
                continue
            index[url] = len(records)
            records.append(
                {
                    **r,
                    "query": query,
                    "language": lang,
                    **(dict(record_extra) if record_extra else {}),
                    "found_by": [{"query": query, "language": lang}],
                }
            )
            n_new += 1
    return n_new


ARTIFACT_1A = "1a_discovery_general.json"
ARTIFACT_1B = "1b_discovery_site_restricted.json"
#: The open evidence leg's artifact. ``1d`` because ``1c`` is the eligibility
#: filter's and the leg runs after it in the roster of things called Stage 1.
ARTIFACT_1D = "1d_discovery_evidence_open.json"


def _read_existing_records(
    run_dir: Path, sample: list[dict[str, Any]], filename: str
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in sample:
        inst_id = synth_institution_id(row)
        path = institution_dir(run_dir, inst_id) / filename
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        out[inst_id] = payload.get("records", [])
    return out


def _read_existing_discovery_general(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    return _read_existing_records(run_dir, sample, ARTIFACT_1A)


def _read_existing_discovery_site_restricted(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    return _read_existing_records(run_dir, sample, ARTIFACT_1B)


def _read_existing_discovery_evidence_open(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    return _read_existing_records(run_dir, sample, ARTIFACT_1D)


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
    credentials: ResolvedCredentials | None = None,
    languages_for: LanguagesFor | None = None,
    leg1_languages_for: LanguagesFor | None = None,
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

    ``languages_for`` (2026-08-30) overrides ``languages`` per institution; see
    the module note. It applies to ``legacy`` only, whose leg 1 *is* the
    language roster — it is honoured here so that legacy mode cannot silently
    keep searching the run-level tuple while leg 2 searches the policy's.

    ``leg1_languages_for`` (2026-09-01) is the ``chain`` counterpart, and a
    separate parameter rather than a reuse of ``languages_for`` because the two
    legs answer to different rosters: a tag can be signed for leg-2 evidence and
    unsigned for a leg-1 suffix, and passing one selector to both would let a
    leg-2 decision silently change the domain-discovery instrument. ``None`` —
    the default, and every run to date — issues the single English domain query,
    byte for byte.
    """
    institution = institution_record(row)
    inst_id = institution["institution_id"]
    path = institution_dir(run_dir, inst_id) / "1a_discovery_general.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return inst_id, payload.get("records", [])
    bypass_url = institution.get("official_site_url")
    if bypass_url:
        # Leg 1 asks "what is this institution's website". When the master
        # already answers that, asking Serper is a credit spent to rediscover a
        # known fact (card 2 §4, 2026-09-01).
        #
        # ``official_site_url`` has bypassed **Stage 2** since 2026-05-09
        # (``stage_classify``, D1+D4), but nothing bypassed Stage 1a:
        # ``_run_discovery_general`` was called on the full sample
        # unconditionally. That cost nothing while the column was null on every
        # master row — which it is today, so this branch is inert on every
        # existing master and the change is measurable as zero. It stops being
        # free the moment the registry carries discovered sites, and it stops
        # being *one* credit the moment leg 1 issues one query per language,
        # which is the change this branch ships alongside.
        #
        # No plausibility check, matching Stage 2's bypass under Q4 (2026-05-09):
        # the runner trusts the master. Trusting it in Stage 2 and re-litigating
        # it here would be two different policies on one column.
        #
        # **An artifact is still written.** Returning early without one would
        # leave no ``1a_discovery_general.json``, and ``report.health`` and
        # ``report.outcomes`` both test that file's existence — a skipped
        # institution would read as one whose queries came back empty, which is
        # the conflation this module's language-tagging note exists to prevent.
        # The envelope carries ``bypassed``/``source``/``url`` in the shape
        # ``2_official_site.json`` already uses, so a reader can separate a
        # deliberate skip from a discovery failure.
        bypass_artifact: dict[str, Any] = {
            "mode": mode,
            "queries": [],
            "records": [],
            "bypassed": True,
            "source": "master_csv",
            "url": bypass_url,
        }
        path.write_text(
            json.dumps(bypass_artifact, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "Stage 1a: %s bypassed — official_site_url present in master (%r); "
            "no leg-1 credit spent",
            inst_id, bypass_url,
        )
        return inst_id, []
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
            # One query per language the institution's policy row names (PI
            # ruling 2026-09-01), or the single English query every run to date
            # issued when no leg-1 selector is supplied. The English arm is never
            # lost: the signed policy's ``always_include`` puts ``en`` in every
            # institution's tuple, so the localized leg is additive and the
            # comparison it enables is within-institution rather than between
            # runs.
            leg1_langs = (
                (DOMAIN_QUERY_LANG,)
                if leg1_languages_for is None
                else tuple(leg1_languages_for(institution))
            )
            queries = build_domain_queries(
                institution["institution_name"],
                leg1_langs,
                institution["country"],
                row.get("disambiguation") or "",
                quote_name=domain_quote_name,
            )
        else:
            # `disambiguation` is read off the raw master row, and the reason
            # has changed, so it is restated rather than left to be inferred.
            # It USED to be that `institution_record()` did not carry the column
            # at all, and adding it there would have changed Stage 2/3/5/6 model
            # input as a side effect of a query change. As of ADJ ruling 2
            # (2026-08-31) the projection DOES carry it, deliberately — see
            # `records.py`. The raw read stays because the two consumers want
            # different things: the query wants the empty string (it is
            # concatenated into query text), the prompt wants `None` (it is JSON
            # a model reads), and keeping the raw read means a future change to
            # the projection's null handling cannot silently rewrite a query.
            # `.get` keeps pre-rollout masters (no such column) working.
            queries = build_queries(
                institution["institution_name"],
                list(languages if languages_for is None else languages_for(institution)),
                country=institution["country"],
                disambiguation=row.get("disambiguation") or "",
            )
        index: dict[str, int] = {}
        records: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        leg = "domain_discovery" if mode == "chain" else "genai_roster"
        # On a SerperRequestError the institution's 1a file is NOT written, so
        # resume (or, under concurrency, the stage-level abort) retries it.
        _issue_queries(
            run_dir, inst_id, stage, queries, leg=leg, num_results=num_results,
            options=options, credentials=credentials,
            index=index, records=records, provenance=provenance,
        )
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
    credentials: ResolvedCredentials | None = None,
    languages_for: LanguagesFor | None = None,
    leg1_languages_for: LanguagesFor | None = None,
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
            credentials=credentials, languages_for=languages_for,
            leg1_languages_for=leg1_languages_for,
        ),
        max_workers=max_workers,
    )
    for inst_id, records in results:
        out[inst_id] = records
    mark_done(run_dir, stage, no_batch=True)
    return out


# ---------------------------------------------------------------------------
# Leg 1, second pass — the localized fallback (PI ruling 2026-09-03)
#
# English first, localized only on failure. The card-2 probe
# (agent-workspace/2026-09-01-discovery-legs/leg1-suffix-roster/FINDINGS-*.md)
# measured that the localized suffixes add no recall where English already
# succeeds (n=1,412, McNemar p=1.0) and recover roughly a third of the cases
# where it fails (7 of 26, underpowered). So the localized queries are issued
# for exactly the institutions Stage 2 came away from empty-handed, and Stage 2
# is then run again on the widened candidate list. "Failed" is Stage 2's verdict,
# not leg 1's: leg 1 returns ten URLs and cannot tell whether one is the site.
# The alternative — exiting on ``pick_domain``'s heuristic — would have promoted
# a rule the project has deliberately kept advisory since 2026-08-01.
#
# The second pass writes into the SAME ``1a_discovery_general.json``. Leg 1 is
# one leg with two passes, and every reader of the funnel (health, outcomes,
# diff, the 1c filter, triage) reads leg 1 from that file; a sibling artifact
# would have made the fallback's URLs invisible to all of them. The artifact
# stays self-describing: every fallback query is stamped ``pass: "fallback"``
# in ``queries``, every URL keeps ``found_by`` attribution, and a
# ``fallback_pass`` block records what the pass did — or why it did nothing.
# ---------------------------------------------------------------------------

STAGE_1A_FALLBACK = "discovery_general_fallback"


def _discover_general_fallback_one(
    run_dir: Path,
    row: dict[str, Any],
    official_sites: Mapping[str, str | None],
    *,
    stage: str,
    num_results: int,
    fallback_languages_for: LanguagesFor,
    options: SerperOptions | None = None,
    domain_quote_name: bool = False,
    credentials: ResolvedCredentials | None = None,
) -> tuple[str, list[dict[str, Any]] | None]:
    """The localized leg-1 pass for one institution, or ``None`` if not applicable.

    Not applicable — artifact untouched, nothing returned — when Stage 2 found a
    site, when the master supplied one (the 1a bypass envelope), or when the
    institution never reached 1a. Applicable but empty when the policy names
    English only: recorded in the artifact as ``fallback_pass.reason`` so a
    reader can tell "no localized query exists for this country" from "the
    fallback was never considered".
    """
    institution = institution_record(row)
    inst_id = institution["institution_id"]
    path = institution_dir(run_dir, inst_id) / ARTIFACT_1A
    if not path.exists():
        return inst_id, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("bypassed"):
        return inst_id, None
    if payload.get("fallback_pass") is not None:
        # Resume: this institution's pass already ran (skip-if-exists).
        return inst_id, payload.get("records", [])
    if official_sites.get(inst_id):
        return inst_id, None
    langs = tuple(fallback_languages_for(institution))
    records: list[dict[str, Any]] = payload.get("records", [])
    if not langs:
        payload["fallback_pass"] = {
            "languages": [],
            "n_queries": 0,
            "n_new_records": 0,
            "reason": "policy_names_english_only",
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return inst_id, records
    with stage_timer(run_dir, inst_id, stage):
        queries = build_domain_queries(
            institution["institution_name"],
            langs,
            institution["country"],
            row.get("disambiguation") or "",
            quote_name=domain_quote_name,
        )
        index = {r.get("link", ""): i for i, r in enumerate(records) if r.get("link")}
        provenance: list[dict[str, Any]] = payload.get("queries", [])
        n_new = _issue_queries(
            run_dir, inst_id, stage, queries, leg="domain_discovery",
            num_results=num_results, options=options, credentials=credentials,
            index=index, records=records, provenance=provenance,
            provenance_extra={"pass": "fallback"},
        )
        payload["queries"] = provenance
        payload["records"] = records
        # Recomputed over the union, for the same readers as the first pass.
        payload["naive_domain"] = pick_domain(records)
        truth = leg1_recall_block(row.get("website"), records)
        if truth is not None:
            payload["ground_truth"] = truth
        payload["fallback_pass"] = {
            "languages": list(langs),
            "n_queries": len(queries),
            "n_new_records": n_new,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return inst_id, records


def _fallback_stats_from_disk(
    run_dir: Path, sample: list[dict[str, Any]]
) -> dict[str, int]:
    """Aggregate every ``fallback_pass`` block — the run summary's view of the pass."""
    stats = {
        "n_institutions": 0,
        "n_english_only": 0,
        "n_queries": 0,
        "n_new_records": 0,
    }
    for row in sample:
        inst_id = synth_institution_id(row)
        path = institution_dir(run_dir, inst_id) / ARTIFACT_1A
        if not path.exists():
            continue
        block = json.loads(path.read_text(encoding="utf-8")).get("fallback_pass")
        if block is None:
            continue
        stats["n_institutions"] += 1
        if block.get("reason") == "policy_names_english_only":
            stats["n_english_only"] += 1
        stats["n_queries"] += int(block.get("n_queries", 0))
        stats["n_new_records"] += int(block.get("n_new_records", 0))
    return stats


def _run_discovery_general_fallback(
    run_dir: Path,
    sample: list[dict[str, Any]],
    discovery_general: dict[str, list[dict[str, Any]]],
    official_sites: Mapping[str, str | None],
    *,
    num_results: int,
    fallback_languages_for: LanguagesFor,
    max_workers: int = 1,
    options: SerperOptions | None = None,
    domain_quote_name: bool = False,
    credentials: ResolvedCredentials | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Stage 1a, second pass — localized leg 1 where Stage 2 found no site.

    Returns the leg-1 records dict with the fallback's URLs unioned in, plus the
    pass's statistics. Institutions the pass did not apply to keep their
    first-pass records unchanged. Resume and concurrency follow
    :func:`_run_discovery_general`: a ``.done`` marker short-circuits to disk,
    and without one the per-institution ``fallback_pass`` block is the
    skip-if-exists signal.
    """
    stage = STAGE_1A_FALLBACK
    if is_done(run_dir, stage):
        logger.info("Stage 1a fallback: .done marker present — skipping (resume from disk)")
        return (
            _read_existing_discovery_general(run_dir, sample),
            _fallback_stats_from_disk(run_dir, sample),
        )
    out = dict(discovery_general)
    results = run_concurrent(
        sample,
        lambda row: _discover_general_fallback_one(
            run_dir, row, official_sites, stage=stage, num_results=num_results,
            fallback_languages_for=fallback_languages_for, options=options,
            domain_quote_name=domain_quote_name, credentials=credentials,
        ),
        max_workers=max_workers,
    )
    for inst_id, records in results:
        if records is not None:
            out[inst_id] = records
    mark_done(run_dir, stage, no_batch=True)
    return out, _fallback_stats_from_disk(run_dir, sample)


def _discover_site_restricted_one(
    run_dir: Path,
    row: dict[str, Any],
    official_sites: dict[str, str | None],
    *,
    stage: str,
    languages: tuple[str, ...],
    num_results: int,
    mode: str = "legacy",
    evidence_terms: Mapping[str, str] | None = None,
    options: SerperOptions | None = None,
    credentials: ResolvedCredentials | None = None,
    languages_for: LanguagesFor | None = None,
    evidence_terms_for: EvidenceTermsFor | None = None,
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

    **This is the leg the language policy is about** (2026-08-30). Leg 1's
    ``official website`` suffix is English on every institution, but this leg
    issues one query per *configured* language, so the set it is handed decides
    whether an institution gets an English evidence query at all — which is the
    query production has been running. ``evidence_terms_for`` overrides
    ``evidence_terms`` per institution; the signed policy's ``always_include``
    is what keeps ``en`` in that set for the 120 signed rows that do not name
    it. See the module note.
    """
    institution = institution_record(row)
    inst_id = institution["institution_id"]
    path = institution_dir(run_dir, inst_id) / "1b_discovery_site_restricted.json"
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
            # One query per configured language, each tagged with **its own**
            # code. Credit cost scales linearly: n languages = n leg-2 credits
            # per institution, against the 1.84 credits/institution measured
            # for the single-language chain.
            if evidence_terms_for is not None:
                terms = dict(evidence_terms_for(institution))
            elif evidence_terms is not None:
                terms = dict(evidence_terms)
            else:
                terms = {DOMAIN_QUERY_LANG: DEFAULT_EVIDENCE_TERM}
            wrapped = [
                (build_evidence_query(domain, term), lang)
                for lang, term in terms.items()
            ]
        else:
            base_queries = build_queries(
                institution["institution_name"],
                list(languages if languages_for is None else languages_for(institution)),
                country=institution["country"],
                disambiguation=row.get("disambiguation") or "",
            )
            wrapped = [(build_site_query(q, domain), lang) for q, lang in base_queries]
        index: dict[str, int] = {}
        records: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        leg = "site_evidence" if mode == "chain" else "site_genai_roster"
        _issue_queries(
            run_dir, inst_id, stage, wrapped, leg=leg, num_results=num_results,
            options=options, credentials=credentials,
            index=index, records=records, provenance=provenance,
            record_extra={"site_domain": domain},
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
    evidence_terms: Mapping[str, str] | None = None,
    options: SerperOptions | None = None,
    credentials: ResolvedCredentials | None = None,
    languages_for: LanguagesFor | None = None,
    evidence_terms_for: EvidenceTermsFor | None = None,
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
            mode=mode, evidence_terms=evidence_terms, options=options,
            credentials=credentials, languages_for=languages_for,
            evidence_terms_for=evidence_terms_for,
        ),
        max_workers=max_workers,
    )
    for inst_id, records in results:
        out[inst_id] = records
    mark_done(run_dir, stage, no_batch=True)
    return out


# ---------------------------------------------------------------------------
# The open evidence leg (PI ruling 2026-09-03; measured as card 3, 2026-09-02)
#
# ``"<name>" <country> <disambiguation> "<term>"``, one query per policy language,
# not bound to any site. The retired legacy leg's shape with the signed 90-term
# evidence roster supplying one native term per language where legacy issued
# eight English ones. Card 3 measured it at n=600 through the real Stages
# 1c → 3 → 5: as an addition to the chain it surfaces 45 institutions with
# confirmed GenAI evidence the chain never reaches (7.5% of the sample), 53 of
# them from third-party sources; as a replacement it is worthless; in English
# alone it is significantly worse than the chain. So it runs in every policy
# language, alongside legs 1 and 2, never instead of either.
#
# It runs after Stage 2 and does not feed it: a query for content is not a query
# for a website, and adding third-party pages to the official-site candidate list
# would change the domain instrument as a side effect. Its URLs join the 1a+1b
# union at Stage 1c and triage, where Stage 3 sees them with the official site
# already known — card 3 measured that withholding it moves triage by 0.3%.
# ---------------------------------------------------------------------------

STAGE_1D = "discovery_evidence_open"


def _discover_evidence_open_one(
    run_dir: Path,
    row: dict[str, Any],
    *,
    stage: str,
    num_results: int,
    evidence_terms: Mapping[str, str] | None = None,
    options: SerperOptions | None = None,
    credentials: ResolvedCredentials | None = None,
    evidence_terms_for: EvidenceTermsFor | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """The open evidence leg for one institution. One ``1d`` artifact.

    Term selection is exactly leg 2's (``evidence_terms_for`` per institution
    under a policy, ``evidence_terms`` for a run-level tuple, ``{en: AI}`` when
    neither is given), so the two evidence legs can never disagree about which
    languages an institution is searched in.
    """
    institution = institution_record(row)
    inst_id = institution["institution_id"]
    path = institution_dir(run_dir, inst_id) / ARTIFACT_1D
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return inst_id, payload.get("records", [])
    if evidence_terms_for is not None:
        terms = dict(evidence_terms_for(institution))
    elif evidence_terms is not None:
        terms = dict(evidence_terms)
    else:
        terms = {DOMAIN_QUERY_LANG: DEFAULT_EVIDENCE_TERM}
    with stage_timer(run_dir, inst_id, stage):
        # ``disambiguation`` off the raw master row, not the projected record,
        # for the reason the other legs give: the projection is model input.
        queries = build_open_evidence_queries(
            institution["institution_name"],
            terms,
            institution["country"],
            row.get("disambiguation") or "",
        )
        index: dict[str, int] = {}
        records: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        _issue_queries(
            run_dir, inst_id, stage, queries, leg="evidence_open",
            num_results=num_results, options=options, credentials=credentials,
            index=index, records=records, provenance=provenance,
        )
        path.write_text(
            json.dumps(
                {
                    "mode": "chain",
                    "leg": "evidence_open",
                    "queries": provenance,
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return inst_id, records


def _run_discovery_evidence_open(
    run_dir: Path,
    sample: list[dict[str, Any]],
    *,
    num_results: int,
    max_workers: int = 1,
    evidence_terms: Mapping[str, str] | None = None,
    options: SerperOptions | None = None,
    credentials: ResolvedCredentials | None = None,
    evidence_terms_for: EvidenceTermsFor | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Stage 1d — the open evidence leg. One ``1d_discovery_evidence_open.json`` per institution.

    Every institution of the sample, whether or not Stage 2 found a site: the
    leg's whole value is the third-party evidence a site-bound query cannot
    reach, and an institution without a known site is exactly where nothing else
    is looking. Resume and concurrency as :func:`_run_discovery_general`.
    """
    stage = STAGE_1D
    if is_done(run_dir, stage):
        logger.info("Stage 1d: .done marker present — skipping (resume from disk)")
        return _read_existing_discovery_evidence_open(run_dir, sample)
    out: dict[str, list[dict[str, Any]]] = {}
    results = run_concurrent(
        sample,
        lambda row: _discover_evidence_open_one(
            run_dir, row, stage=stage, num_results=num_results,
            evidence_terms=evidence_terms, options=options,
            credentials=credentials, evidence_terms_for=evidence_terms_for,
        ),
        max_workers=max_workers,
    )
    for inst_id, records in results:
        out[inst_id] = records
    mark_done(run_dir, stage, no_batch=True)
    return out
