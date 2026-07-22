"""Institution-level final outcome ledger — persistence for
:mod:`g3o.report.outcomes`.

Writes ``runs/<run_id>/institution_report.jsonl`` (one JSON object per line,
one line per institution) and ``runs/<run_id>/institution_report.csv``
(flattened, for spreadsheet use).

Unlike :mod:`g3o.common.attrition`'s true incremental append-as-you-go
ledger, an institution's ``final_status`` is only knowable once the run has
advanced far enough to decide it (it needs a full pass over that
institution's on-disk artifacts, the attrition ledger, and the run's
``--stop-after`` config), so this module recomputes the full report via
:func:`g3o.report.outcomes.compute_institution_report` and rewrites both
files atomically (temp-file + ``os.replace``) each time it is called. The
JSONL *format* matches ``_attrition.jsonl`` (one record per line); the write
pattern is "regenerate the current, complete set" rather than a literal
single-line append, because there is no earlier partial version of an
institution's final status to append after.
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
from typing import Any

from g3o.common.schema import INSTITUTION_REPORT_COLUMNS
from g3o.report.outcomes import compute_institution_report

REPORT_JSONL_NAME = "institution_report.jsonl"
REPORT_CSV_NAME = "institution_report.csv"


def report_jsonl_path(run_dir: Path) -> Path:
    return run_dir / REPORT_JSONL_NAME


def report_csv_path(run_dir: Path) -> Path:
    return run_dir / REPORT_CSV_NAME


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` verbatim (no newline translation) via temp-file + ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def write_institution_report(run_dir: str | Path) -> dict[str, Any]:
    """Compute and persist ``institution_report.{jsonl,csv}``.

    Returns a small summary: total institution count, counts per
    ``final_status`` bucket, and the full list of records.
    """
    run_dir = Path(run_dir)
    records = compute_institution_report(run_dir)

    jsonl_text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    _write_atomic(report_jsonl_path(run_dir), jsonl_text)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=INSTITUTION_REPORT_COLUMNS, extrasaction="raise")
    writer.writeheader()
    for r in records:
        writer.writerow({col: r.get(col) for col in INSTITUTION_REPORT_COLUMNS})
    _write_atomic(report_csv_path(run_dir), buf.getvalue())

    counts: dict[str, int] = {}
    for r in records:
        counts[r["final_status"]] = counts.get(r["final_status"], 0) + 1

    return {
        "n_institutions": len(records),
        "counts_by_final_status": counts,
        "records": records,
    }


def read_institution_report(run_dir: str | Path) -> list[dict[str, Any]]:
    """Read back ``institution_report.jsonl`` (test/inspection helper)."""
    path = report_jsonl_path(Path(run_dir))
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


__all__ = [
    "REPORT_CSV_NAME",
    "REPORT_JSONL_NAME",
    "read_institution_report",
    "report_csv_path",
    "report_jsonl_path",
    "write_institution_report",
]
