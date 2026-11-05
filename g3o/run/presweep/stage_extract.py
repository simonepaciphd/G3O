"""Stage 5 runner — per-page LLM extraction, batched across (institution × page)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.artifact_io import glob_artifacts, write_artifact
from g3o.common.batch_client import BatchResult
from g3o.common.credentials import ResolvedCredentials
from g3o.common.paths import institution_dir
from g3o.common.run_state import is_done, load_state, mark_done, run_chunked_stage
from g3o.common.timing import llm_stage_timer
from g3o.extract import (
    GroupDSalvage,
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
from g3o.extract.parser import SalvageEvent
from g3o.extract.salvage import (
    REASON_FLAGS_SALVAGED,
    REASON_NEGATIVE_ROW_BLANKED,
    REASON_NEGATIVE_ROW_CONTRADICTORY,
    REASON_SALVAGED,
    REASON_UNSALVAGEABLE,
    NegativeRowSalvage,
    UncertaintyFlagsSalvage,
)
from g3o.run.presweep.records import institution_record, synth_institution_id
from g3o.scrape.render import RenderedPage

logger = logging.getLogger(__name__)


def _is_unsalvageable_group_d_failure(
    exc: Exception, salvages: list[SalvageEvent]
) -> bool:
    """True only when ``exc`` is *caused* by an unsalvageable Group-D ``_NA_``.

    Attributes the true failure cause rather than firing on the mere presence of
    an unsalvageable salvage event: a page can carry an unsalvageable event and
    still fail for an unrelated reason (an access-date mismatch, raised as a
    ``RuntimeError`` after model validation, has no ``.errors()``), which must
    stay ``parse_failed``. So we require ``exc`` to be a pydantic-style
    validation error carrying an error that actually concerns one of the
    unsalvageable Group-D fields.
    """
    # The sink is heterogeneous (Group-D and uncertainty_flags events share it),
    # and only Group-D events carry `unsalvageable_fields` — narrow before reading.
    unsalvageable_fields = {
        f
        for s in salvages
        if isinstance(s, GroupDSalvage)
        for f in s.unsalvageable_fields
    }
    if not unsalvageable_fields:
        return False
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return False  # not a ValidationError (e.g. the access-date RuntimeError)
    for err in errors():
        loc = err.get("loc", ())
        msg = err.get("msg", "")
        # Field-level failure on an unsalvageable Group-D column, or the
        # model-level confirms_activity/_NA_ rule naming such a field.
        if loc and loc[-1] in unsalvageable_fields:
            return True
        if "Group D fields are _NA_" in msg and any(
            f in msg for f in unsalvageable_fields
        ):
            return True
    return False


def _is_contradictory_negative_row_failure(
    exc: Exception, salvages: list[SalvageEvent]
) -> bool:
    """True only when ``exc`` is *caused* by a self-contradictory negative row.

    Mirror of :func:`_is_unsalvageable_group_d_failure`, and guarded the same way:
    a page can carry a contradictory event and still fail for an unrelated reason,
    which must stay ``parse_failed``. The validator's message for this rule names
    the offending fields, so we require it to name one of ours.
    """
    fields = {
        f
        for s in salvages
        if isinstance(s, NegativeRowSalvage)
        for f in s.contradictory_fields
    }
    if not fields:
        return False
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return False
    for err in errors():
        msg = err.get("msg", "")
        if "requires every Group D field to be _NA_" in msg and any(
            f in msg for f in fields
        ):
            return True
    return False


def _count_existing_extracts(run_dir: Path, sample: list[dict[str, Any]]) -> int:
    n = 0
    for row in sample:
        inst_id = synth_institution_id(row)
        extract_dir = institution_dir(run_dir, inst_id) / "extract"
        n += len(glob_artifacts(extract_dir))
    return n


def _run_extract(
    run_dir: Path,
    sample: list[dict[str, Any]],
    scraped: Mapping[str, list[RenderedPage]],
    *,
    institution_search_languages: str,
    search_languages_for: Callable[[dict[str, Any]], str] | None = None,
    model: str,
    poll_interval: int,
    max_wait: int,
    run_id: str,
    text_cap_chars: int = DEFAULT_TEXT_CAP_CHARS,
    text_cap_rule: str = DEFAULT_TEXT_CAP_RULE,
    empty_page_min_chars: int = EMPTY_PAGE_MIN_CHARS,
    cost_check_callback: Callable[[str, dict[str, int]], bool] | None = None,
    credentials: ResolvedCredentials | None = None,
    telemetry: Any | None = None,
) -> int:
    """Stage 5 — per-page LLM extraction, batched across (institution × page).

    Resume (Session E; chunked Session F.1): same shape as Stages 2/3.
    Returns the on-disk count of ``<inst>/extract/`` artifacts once the
    stage is complete (equals the parsed-result count on a clean fresh run,
    and stays truthful across chunked resumes where earlier invocations
    already persisted some chunks).

    ``search_languages_for`` (2026-08-30) supersedes the run-level
    ``institution_search_languages`` per institution, under a signed language
    policy. Without it the run-level string is written to every row, which is
    every run to date.
    """
    from g3o.extract.batch import make_custom_id, url_hash

    stage = "extract"
    if is_done(run_dir, stage):
        logger.info("Stage 5: .done marker present — skipping (resume from disk)")
        return _count_existing_extracts(run_dir, sample)

    page_lookup: dict[str, tuple[str, RenderedPage]] = {}
    pairs: list[tuple[dict[str, Any], RenderedPage]] = []
    # Per-institution search-language provenance, keyed by institution_id so
    # consistency check #4 (one string per institution, across its pages) holds
    # by construction rather than by care. Empty under the run-level path, in
    # which case the string below serves every job.
    search_languages: dict[str, str] = {}
    for row in sample:
        institution = institution_record(row)
        inst_id = institution["institution_id"]
        if search_languages_for is not None:
            search_languages[inst_id] = search_languages_for(institution)
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
        institution_search_languages=(
            institution_search_languages
            if search_languages_for is None
            else search_languages
        ),
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
            salvages: list[SalvageEvent] = []
            try:
                parsed = parse_extract_result(
                    result,
                    scrape_access_date=page.fetch_metadata.access_date,
                    salvage_sink=salvages,
                )
            except Exception as exc:
                # A confirms_activity row with Group-D _NA_ in an unsalvageable
                # field (activity_type / activity_name) can't be repaired without
                # a coding/schema decision, so the page still drops here. Tag it
                # distinctly from a generic parse failure so the escalation rate
                # is measurable (see salvage.py) — but only when this exception
                # is actually caused by the unsalvageable field, not merely when
                # an unsalvageable event coexists with an unrelated failure.
                #
                # A negative-evidence row carrying an existence-asserting Group-D
                # value is escalated on the same principle: the model contradicted
                # itself about whether a finding exists, and resolving that is a
                # coding decision. Same guard — attribute only when the exception
                # actually names one of those fields.
                if _is_unsalvageable_group_d_failure(exc, salvages):
                    reason = REASON_UNSALVAGEABLE
                elif _is_contradictory_negative_row_failure(exc, salvages):
                    reason = REASON_NEGATIVE_ROW_CONTRADICTORY
                else:
                    reason = "parse_failed"
                logger.warning("Stage 5 parse failed for %s: %s", result.custom_id, exc)
                attrition.record(
                    run_dir, institution_id=institution_id, stage=stage,
                    reason=reason, url=page.url, detail=str(exc),
                )
                continue
            # Group-D _NA_ salvage: a confirms_activity row's illegal _NA_ was
            # repaired to the contract default and preserved rather than dropped.
            # One ledger record per salvaged page (dedup key includes the url);
            # detail carries the repaired row_ids and field names for audit.
            group_d = [s for s in salvages if isinstance(s, GroupDSalvage)]
            salvaged = [s for s in group_d if s.is_salvageable]
            if salvaged:
                fields = sorted({f for s in salvaged for f in s.salvaged_fields})
                rows = sorted(s.row_id for s in salvaged if s.row_id is not None)
                attrition.record(
                    run_dir, institution_id=institution_id, stage=stage,
                    reason=REASON_SALVAGED, url=page.url,
                    detail=f"rows={rows};fields={','.join(fields)}",
                )
            # uncertainty_flags _NA_ salvage: an illegal whole-value `_NA_` was
            # rewritten to the contract's `none` and the page preserved. Recorded
            # only on the success path (as above) — a page that still failed for
            # an unrelated reason is reported by its actual failure, not as a
            # salvage that did not save it.
            flags_salvaged = [
                s for s in salvages if isinstance(s, UncertaintyFlagsSalvage)
            ]
            if flags_salvaged:
                rows = sorted(
                    s.row_id for s in flags_salvaged if s.row_id is not None
                )
                attrition.record(
                    run_dir, institution_id=institution_id, stage=stage,
                    reason=REASON_FLAGS_SALVAGED, url=page.url,
                    detail=f"rows={rows}",
                )
            # Negative-evidence row carrying stray Group-D values: blanked to _NA_
            # and the page preserved. This repair *discards* model output, so the
            # detail carries the discarded values verbatim — a blanking has to be
            # reconstructible from the ledger, not merely counted.
            blanked = [
                s
                for s in salvages
                if isinstance(s, NegativeRowSalvage) and s.is_salvageable
            ]
            if blanked:
                rows = sorted(s.row_id for s in blanked if s.row_id is not None)
                dropped = sorted(
                    {f"{f}={v!r}" for s in blanked for f, v in s.discarded}
                )
                attrition.record(
                    run_dir, institution_id=institution_id, stage=stage,
                    reason=REASON_NEGATIVE_ROW_BLANKED, url=page.url,
                    detail=f"rows={rows};discarded={dropped}",
                )
            extract_dir = institution_dir(run_dir, institution_id) / "extract"
            # Gzipped, compact (no indent=2), atomic, deterministic — see
            # g3o.common.artifact_io. Writes <url_hash>.json.gz.
            write_artifact(
                extract_dir / f"{url_hash(page.url)}.json",
                json.dumps(parsed.model_dump(), ensure_ascii=False),
            )

    custom_id_to_institution = {cid: inst_id for cid, (inst_id, _page) in page_lookup.items()}
    with llm_stage_timer(run_dir, stage, custom_id_to_institution):
        run_chunked_stage(
            run_dir, stage, jobs,
            run_id=run_id, model=model,
            poll_interval=poll_interval, max_wait=max_wait,
            process_chunk_results=_persist,
            cost_check_callback=cost_check_callback,
            credentials=credentials, telemetry=telemetry,
        )
    return _count_existing_extracts(run_dir, sample)


# ---------------------------------------------------------------------------
# v2.7 pass-1 extraction (T-022)
# ---------------------------------------------------------------------------
#
# Beside the v2.5 runner above, which is unchanged until T-071 (RC-D-017 P4).
# Not called by the orchestrator yet: the call site and the T-021 page artifact
# are T-030's wiring. No head+tail page-text cap on this path (T-022): a request
# over the size guard is refused whole and recorded, never cut.

EXTRACT_V27_STAGE = "extract_v27"
EXTRACT_V27_DIR = "extract_v27"


def _v27_artifact_path(run_dir: Path, institution_id: str, url: str) -> Path:
    from g3o.extract.batch import url_hash

    return institution_dir(run_dir, institution_id) / EXTRACT_V27_DIR / f"{url_hash(url)}.json"


def _v27_has_artifact(run_dir: Path, page: Any) -> bool:
    p = _v27_artifact_path(run_dir, page.institution_id, page.url)
    return p.exists() or p.with_name(p.name + ".gz").exists()


def _v27_write(run_dir: Path, page: Any, payload: dict[str, Any]) -> None:
    write_artifact(
        _v27_artifact_path(run_dir, page.institution_id, page.url),
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )


def _write_v27_state(run_dir: Path, batches: list[dict[str, Any]]) -> None:
    """Record submitted batches (id + custom ids), written after every submit."""
    from g3o.common.run_state import _write_json_atomic, state_path

    _write_json_atomic(state_path(run_dir, EXTRACT_V27_STAGE), {
        "stage": EXTRACT_V27_STAGE, "provider": "anthropic", "batches": batches,
    })


def _run_extract_v27(
    run_dir: Path,
    pages: Sequence[Any],
    *,
    client: Any,
    mode: str = "batch",
    poll_interval: float = 60.0,
    max_wait: float = 24 * 3600.0,
    sleep: Callable[[float], None] = time.sleep,
    cost_check_callback: Callable[[list[Any]], bool] | None = None,
) -> dict[str, int]:
    """Stage 5 (v2.7): pass-1 extraction for pages that have been through jev pass 1.

    ``pages`` are :class:`g3o.extract.request_v27.Pass1Page` objects;
    ``client`` is an :class:`g3o.extract.anthropic_client.AnthropicExtractorClient`
    (tests inject a fake). ``mode`` is ``"sync"`` (testing legs: T-041, T-072)
    or ``"batch"`` (full runs; RC-D-001 B).

    Every page that is processed gets one artifact under
    ``<inst>/extract_v27/<url_hash>.json``: ``status`` ``extracted`` (the parsed
    :class:`~g3o.extract.parser_v27.Pass1Extraction` plus the request plan) or
    ``no_request`` (the plan only, so an incomplete page whose links were not
    measured still says so). A refused, failed or contract-breaking request
    writes no artifact and is recorded in the attrition ledger.

    Resume: pages that already have an artifact are skipped. In batch mode each
    batch id and its custom ids are written to ``_state/extract_v27.json`` after
    its submit; a re-run rejoins those batches, submits only the ones not yet
    sent, and refuses if the recorded batches no longer match the input. ``cost_check_callback``
    receives the jobs before anything is sent; ``False`` stops the stage.

    Returns counts: ``pages``, ``skipped``, ``no_request``, ``refused``,
    ``extracted``, ``failed``.
    """
    from g3o.extract.anthropic_client import split_for_batches
    from g3o.extract.parser_v27 import parse_pass1_result
    from g3o.extract.request_v27 import PROMPT_VERSION, build_jobs

    if mode not in ("sync", "batch"):
        raise ValueError(f"mode must be 'sync' or 'batch', not {mode!r}")
    stage = EXTRACT_V27_STAGE
    counts = dict.fromkeys(("pages", "skipped", "no_request", "refused", "extracted", "failed"), 0)
    counts["pages"] = len(pages)
    if is_done(run_dir, stage):
        logger.info("Stage 5 (v2.7): .done marker present — skipping (resume from disk)")
        counts["skipped"] = len(pages)
        return counts

    ids = [p.page_id for p in pages]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate page_id in Stage 5 (v2.7) input")
    # Plans and batches are built over the whole input, so a resumed run splits
    # them exactly as the first one did; pages already on disk are skipped below.
    done_ids = {p.page_id for p in pages if _v27_has_artifact(run_dir, p)}
    counts["skipped"] = len(done_ids)
    jobs, plans = build_jobs(pages)
    by_page = {p.page_id: p for p in pages}
    for p in pages:
        if p.page_id not in done_ids and not plans[p.page_id].needs_request:
            _v27_write(run_dir, p, {"status": "no_request", "page_id": p.page_id,
                                    "prompt_version": PROMPT_VERSION,
                                    "plan": asdict(plans[p.page_id])})
            counts["no_request"] += 1
    by_cid: dict[str, Any] = {}
    for job in jobs:
        if job.custom_id in by_cid:
            raise ValueError(f"two pages share custom_id {job.custom_id} (same institution and URL)")
        by_cid[job.custom_id] = by_page[job.metadata["page_id"]]

    batches, refused = split_for_batches(jobs)
    for job in refused:
        page = by_cid[job.custom_id]
        if page.page_id in done_ids:
            continue
        attrition.record(run_dir, institution_id=page.institution_id, stage=stage,
                         reason="v27_request_too_large", url=page.url,
                         detail="refused whole; page text is never truncated")
        counts["refused"] += 1
    sendable = [j for b in batches for j in b if by_cid[j.custom_id].page_id not in done_ids]
    submitted: list[dict[str, Any]] = []
    if mode == "batch":
        submitted = list((load_state(run_dir, stage) or {}).get("batches", []))
        if len(submitted) > len(batches) or any(
            rec["custom_ids"] != [j.custom_id for j in batches[n]]
            for n, rec in enumerate(submitted)
        ):
            raise RuntimeError(
                f"Stage 5 (v2.7): the batches in _state/{stage}.json do not match this input; "
                "nothing resubmitted (inspect the state file before re-running)")
        to_send = [j for b in batches[len(submitted):] for j in b]
    else:
        to_send = sendable
    if to_send and cost_check_callback is not None and not cost_check_callback(to_send):
        raise RuntimeError("Stage 5 (v2.7): cost check refused the submission; nothing sent")

    def _persist(result: Any) -> None:
        page = by_cid.get(result.custom_id)
        if page is None:
            logger.warning("Stage 5 (v2.7) result %s matches no request", result.custom_id)
            return
        if _v27_has_artifact(run_dir, page):
            return
        plan = plans[page.page_id]
        try:
            parsed = parse_pass1_result(result, page, plan)
        except Exception as exc:  # recorded in the ledger, never silently dropped
            reason = "v27_extract_failed" if not result.success else "v27_parse_failed"
            attrition.record(run_dir, institution_id=page.institution_id, stage=stage,
                             reason=reason, url=page.url, detail=str(exc))
            counts["failed"] += 1
            return
        _v27_write(run_dir, page, {"status": "extracted", "page_id": page.page_id,
                                   "prompt_version": PROMPT_VERSION, "plan": asdict(plan),
                                   "extraction": asdict(parsed)})
        counts["extracted"] += 1

    if mode == "sync":
        for job in sendable:
            _persist(client.create(job))
    elif sendable:
        for batch in batches[len(submitted):]:
            submitted.append({"batch_id": client.submit_batch(batch),
                              "custom_ids": [j.custom_id for j in batch]})
            _write_v27_state(run_dir, submitted)
        batch_ids = [b["batch_id"] for b in submitted]
        waited = 0.0
        pending = list(batch_ids)
        while True:
            pending = [b for b in pending if client.batch_status(b) != "ended"]
            if not pending:
                break
            if waited >= max_wait:
                raise TimeoutError(f"Stage 5 (v2.7): batches {pending} still running after "
                                   f"{max_wait}s; re-run to rejoin")
            sleep(poll_interval)
            waited += poll_interval
        for batch_id in batch_ids:
            for result in client.batch_results(batch_id):
                _persist(result)
    mark_done(run_dir, stage, no_batch=mode == "sync" or not sendable, n_jobs=len(sendable),
              model=sendable[0].params["model"] if sendable else None)
    return counts
