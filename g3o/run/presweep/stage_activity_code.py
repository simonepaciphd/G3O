"""v2.7 pass-2 activity-coding stage (T-023).

Runs :func:`g3o.classify.jev_activity_code.code_page` over pages that pass 1 (T-021)
and the extractor (T-022) have finished, writes one artifact per page and records
part failures and uncoded activities in the run's attrition ledger. The jev call
and the part combiner are injected; orchestrator wiring belongs to T-030.

Artifact: ``<out_dir>/<page_id>.json.gz`` holding :meth:`PageActivityResult.to_dict`
(the per-institution JSON artifacts of DEC-004 a are assembled by T-028/T-030).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from g3o.classify.jev_activity_code import (
    ActivityCoderConfig,
    ActivityPageInput,
    AskFn,
    PageActivityResult,
    code_page,
)
from g3o.common import attrition
from g3o.common.artifact_io import write_artifact

STAGE = "activity_code"
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class StageResult:
    results: tuple[PageActivityResult, ...]
    artifacts: tuple[Path, ...]
    failed_parts: int
    skipped_activities: int


def artifact_path(out_dir: Path, page_id: str) -> Path:
    return Path(out_dir) / f"{_SAFE.sub('_', page_id)}.json"


def run_stage(pages: Iterable[ActivityPageInput], ask_fn: AskFn, config: ActivityCoderConfig, *,
              out_dir: Path | None = None, run_dir: Path | None = None) -> StageResult:
    """Code each page; a jev account error stops the stage (raised), anything else is per part."""
    results: list[PageActivityResult] = []
    paths: list[Path] = []
    failed = skipped = 0
    for inp in pages:
        res = code_page(inp, ask_fn, config)
        results.append(res)
        failed += len(res.failures)
        skipped += len(res.skipped_activities)
        if out_dir is not None:
            p = artifact_path(out_dir, res.page_id)
            p.parent.mkdir(parents=True, exist_ok=True)
            write_artifact(p, json.dumps(res.to_dict(), ensure_ascii=False, sort_keys=True))
            paths.append(p)
        if run_dir is not None:
            for f in res.failures:
                attrition.record(run_dir, institution_id=res.institution_id, stage=STAGE,
                                 reason=f.reason, url=inp.page.url, detail=f.detail,
                                 page_id=res.page_id, activity_id=f.activity_id,
                                 chunk_id=f.chunk_id, round=f.round)
            for aid, reason in res.skipped_activities:
                attrition.record(run_dir, institution_id=res.institution_id, stage=STAGE,
                                 reason=reason, url=inp.page.url, page_id=res.page_id,
                                 activity_id=aid)
    return StageResult(tuple(results), tuple(paths), failed, skipped)


__all__ = ["STAGE", "StageResult", "artifact_path", "run_stage"]
