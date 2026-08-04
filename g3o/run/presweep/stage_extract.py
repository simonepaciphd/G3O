"""Stage 5 runner — per-page LLM extraction, batched across (institution × page)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from g3o.common import attrition
from g3o.common.batch_client import BatchResult
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
        extract_dir = run_dir / inst_id / "extract"
        if extract_dir.is_dir():
            n += sum(1 for _ in extract_dir.glob("*.json"))
    return n


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
            # uncertainty_flags salvage: an illegal value was rewritten to the
            # contract's `none` (or to a cleaned flag list) and the page preserved.
            # Recorded only on the success path (as above) — a page that still
            # failed for an unrelated reason is reported by its actual failure, not
            # as a salvage that did not save it.
            #
            # One record per repair *shape*, not one per page: the shapes are
            # different model errors with different audit weight (a `_NA_` synonym
            # rewrite versus inferring `none` from silence), and the dedup key
            # includes the reason, so they do not collide.
            flags_salvaged = [
                s for s in salvages if isinstance(s, UncertaintyFlagsSalvage)
            ]
            by_reason: dict[str, list[UncertaintyFlagsSalvage]] = {}
            for s in flags_salvaged:
                by_reason.setdefault(s.reason, []).append(s)
            for reason, group in sorted(by_reason.items()):
                rows = sorted(s.row_id for s in group if s.row_id is not None)
                originals = sorted({s.original for s in group})
                attrition.record(
                    run_dir, institution_id=institution_id, stage=stage,
                    reason=reason, url=page.url,
                    detail=f"rows={rows};originals={originals}",
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
            extract_dir = run_dir / institution_id / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            (extract_dir / f"{url_hash(page.url)}.json").write_text(
                json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    custom_id_to_institution = {cid: inst_id for cid, (inst_id, _page) in page_lookup.items()}
    with llm_stage_timer(run_dir, stage, custom_id_to_institution):
        run_chunked_stage(
            run_dir, stage, jobs,
            run_id=run_id, model=model,
            poll_interval=poll_interval, max_wait=max_wait,
            process_chunk_results=_persist,
        )
    return _count_existing_extracts(run_dir, sample)
