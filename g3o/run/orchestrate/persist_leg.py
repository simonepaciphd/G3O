"""Leg 2.5 — Stage 7, as a leg rather than as a thing a human remembers.

Stage 7 is not a member of :data:`g3o.run.presweep.config.STAGES`. It is a
separate CLI verb (``python -m g3o persist``), so a run submitted with
``stop_after: validate`` — every run to date — finishes ``COMPLETED 8/8`` with no
``final/`` directory at all. Run ``r20260824T215623Z-bb4e`` was exactly that: 8/8
at 2026-08-26T08:13:31Z, and Stage 7 ran afterwards because a person typed it.

That is the whole reason this module exists. An unattended chain that goes
submit → ingest has a hole between the two legs that no exit code covers, and the
hole is not "the ingest fails" — :func:`g3o.run.orchestrate.ingest.ingest_run`
refuses a run with no Stage-7 tree, loudly and before the transaction. The hole is
that the run is *finished, correct, and unloaded*, and nothing says so.

Two properties make this a leg and not a wrapper:

* **It gates on the run's state, exactly as leg 3 does.** Stage 7 over a partial
  run produces real CSVs with real rows from a sweep that died mid-flight, and
  nothing downstream can tell them apart afterwards. ``force`` exists for the
  human who means it, and is recorded.
* **Its success criterion is leg 3's precondition.** After writing, it re-reads
  the tree through :func:`~g3o.run.orchestrate.ingest.find_stage7_csvs`. Writing
  a ``final/`` that the loader cannot read is a failure of this leg, discovered
  here, rather than a refusal two legs later — or, before that guard existed, a
  silent publish through the pre-#17 inference.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from g3o.run.orchestrate.ingest import (
    LOADER_SUMMARY_RELPATH,
    IngestError,
    find_stage7_csvs,
)
from g3o.run.orchestrate.status import (
    RunStatus,
    record_leg,
    run_status,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

#: The ``v{N}`` Stage 7 must write for the loader to read it. Derived from the
#: loader's own hardcoded path rather than restated, so the two cannot drift.
LOADER_VERSION = int(LOADER_SUMMARY_RELPATH[-1].rsplit("_v", 1)[1].split(".")[0])


class PersistError(RuntimeError):
    """Stage 7 could not be run, or what it wrote is not loadable."""


@dataclass(frozen=True)
class PersistResult:
    """What Stage 7 wrote, and whether leg 3 would now accept it."""

    run_id: str
    run_dir: Path
    version: int
    summary: dict[str, Any] = field(default_factory=dict)
    activities: Path | None = None
    sources: Path | None = None
    loadable: bool = False

    @property
    def n_load_failures(self) -> int | None:
        """Institutions Stage 7 could not read. ``None`` when it did not say.

        ``None`` and ``0`` are different answers and the difference matters the
        same way it does in :class:`~g3o.run.orchestrate.ingest.IngestCounts`:
        ``0`` is "Stage 7 read every institution", ``None`` is "Stage 7 was not
        asked" — the skipped-because-already-loadable path.
        """
        value = self.summary.get("n_load_failures")
        return value if isinstance(value, int) else None

    @property
    def green(self) -> bool:
        """Written *and* loadable. Written alone is not a result worth reporting."""
        return self.loadable

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "version": self.version,
            "summary": self.summary,
            "activities": str(self.activities) if self.activities else None,
            "sources": str(self.sources) if self.sources else None,
            "loadable": self.loadable,
            "n_load_failures": self.n_load_failures,
        }


def persist_run(
    runs_dir: Path,
    run_id: str,
    *,
    version: int | None = None,
    overwrite: bool = False,
    force: bool = False,
    max_load_failures: int = 0,
    status: RunStatus | None = None,
) -> PersistResult:
    """Write ``final/`` for a finished run, then prove leg 3 could load it.

    Args:
        version: the ``v{N}`` suffix, or None for :data:`LOADER_VERSION` — the
            version the pinned loader reads. Any other value writes a tree
            :func:`find_stage7_csvs` refuses, which is reported here rather than
            at ingest time.

            **None is resolved here rather than in the signature default, and
            that is a fix, not a style.** ``orchestrate persist`` declares
            ``--version`` with ``default=None`` and forwarded it
            unconditionally, so this signature default was never reached and
            Stage 7 wrote ``g3o_activities_vNone.csv``. Nothing downstream
            caught it: the activities and sources globs are ``_v*``, and the
            version-skew refusal in
            :func:`~g3o.run.orchestrate.ingest._assert_loader_readable_summary`
            is guarded on a parsed version being not-None, which ``vNone`` is
            not. Resolving at the one place every caller passes through is what
            stops the next caller reintroducing it by forgetting to omit the
            argument.
        overwrite: replace an existing ``final/``. Without it, a ``final/`` that
            is already loadable is reported as-is instead of being rewritten —
            re-running the chain over a run that is already persisted is a normal
            thing for an automated retry to do, and it should be a no-op, not a
            conflict.
        force: persist a run that is not
            :attr:`~g3o.run.orchestrate.status.RunStatus.publishable`. Recorded.
        max_load_failures: institutions Stage 7 may fail to read before this leg
            refuses. Zero by default, matching the loader's own policy — strict
            by default, explicitly overridable, never silent. Run
            ``r20260824T215623Z-bb4e`` had 0 of 2,909, so the strict default is
            what production already meets rather than an aspiration.
    """
    version = LOADER_VERSION if version is None else version
    run_dir = Path(runs_dir) / run_id
    state = status or run_status(Path(runs_dir), run_id)
    if not state.publishable and not force:
        raise PersistError(
            f"refusing to run Stage 7 for {run_id}: its state is {state.state!r}"
            + (f" ({state.failure.get('error_message')})" if state.failure else "")
            + ". Stage 7 over a partial run writes real CSVs from an incomplete "
            "sweep, and nothing downstream could tell them apart afterwards. Pass "
            "--force to do it deliberately."
        )

    started_at = utc_now_iso()
    already = _already_loadable(run_dir)
    if already is not None and not overwrite:
        activities, sources = already
        logger.info("persist: final/ already loadable for %s; leaving it", run_id)
        result = PersistResult(
            run_id=run_id,
            run_dir=run_dir,
            version=version,
            summary={"skipped": "final/ already present and loadable"},
            activities=activities,
            sources=sources,
            loadable=True,
        )
        record_leg(
            run_dir, "persist", outcome="green", started_at=started_at,
            forced=force, rewrote=False, **_leg_detail(result),
        )
        return result

    summary = _write(run_dir, run_id, version=version, overwrite=overwrite)

    # The leg's own success criterion, and the reason it is not a wrapper: what
    # was written has to be what leg 3 accepts. A tree written at a version the
    # loader does not read is a failure *here*, where the fix is one re-run,
    # rather than a refusal after a monitor has already reported the run loaded.
    try:
        activities, sources = find_stage7_csvs(run_dir)
    except IngestError as exc:
        record_leg(
            run_dir, "persist", outcome="not-green", started_at=started_at,
            forced=force, rewrote=True, version=version,
            summary=summary, loadable=False, error=str(exc),
        )
        raise PersistError(
            f"Stage 7 wrote final/ for {run_id}, and the ingest leg will not load "
            f"it: {exc}"
        ) from exc

    result = PersistResult(
        run_id=run_id,
        run_dir=run_dir,
        version=version,
        summary=summary,
        activities=activities,
        sources=sources,
        loadable=True,
    )
    failures = result.n_load_failures or 0
    if failures > max_load_failures:
        record_leg(
            run_dir, "persist", outcome="not-green", started_at=started_at,
            forced=force, rewrote=True, **_leg_detail(result),
        )
        raise PersistError(
            f"Stage 7 could not read {failures:,} institution(s) for {run_id}, "
            f"over the {max_load_failures:,} allowed. Those institutions are "
            f"absent from final/ and so make no published claim in either "
            f"direction — which is the right outcome only if it was noticed. "
            f"Read {run_dir / 'final'} and the run report, then re-run with "
            f"--max-load-failures if the loss is understood and accepted. "
            f"First few: {summary.get('load_failures', [])[:3]}"
        )
    record_leg(
        run_dir, "persist", outcome="green", started_at=started_at,
        forced=force, rewrote=True, **_leg_detail(result),
    )
    return result


def _leg_detail(result: PersistResult) -> dict[str, Any]:
    """The result as leg-record fields, minus the one that would collide.

    ``record_leg`` takes ``run_dir`` positionally and the record is written
    *inside* that directory, so carrying it in the payload is both a TypeError
    and redundant.
    """
    detail = result.to_dict()
    detail.pop("run_dir", None)
    return detail


def _already_loadable(run_dir: Path) -> tuple[Path, Path] | None:
    """``(activities, sources)`` when ``final/`` is already loadable, else None.

    Swallowing :class:`IngestError` here is deliberate and narrow: the question
    being asked is "is there already a good tree", and every negative answer —
    absent, partial, wrong version — leads to the same next step, which is to
    write one.
    """
    try:
        return find_stage7_csvs(run_dir)
    except IngestError:
        return None


def _write(
    run_dir: Path, run_id: str, *, version: int, overwrite: bool
) -> dict[str, Any]:
    """Call Stage 7. Imported here so the leg costs nothing until it is used."""
    from g3o.cli import _run_date_from_manifest
    from g3o.common.config import OPENAI_MODEL
    from g3o.persist import write_run_csvs

    model = _model_from_manifest(run_dir) or OPENAI_MODEL
    try:
        return write_run_csvs(
            run_dir,
            run_id=run_id,
            run_model=model,
            version=version,
            overwrite=overwrite,
            # The run's own date, not today's: Stage 7 running a day after the
            # sweep must not stamp the sweep with the day it was persisted.
            run_date=_run_date_from_manifest(run_dir),
        )
    except Exception as exc:  # noqa: BLE001 - reported, not interpreted
        raise PersistError(
            f"Stage 7 failed for {run_id}: {type(exc).__name__}: {exc}"
        ) from exc


def _model_from_manifest(run_dir: Path) -> str | None:
    """``run_model`` as the run itself recorded it.

    Read from the manifest rather than taken as an argument for the same reason
    leg 3 reads the master there: the model stamped into a run's provenance is a
    property of that run, and defaulting it to whatever ``OPENAI_MODEL`` says on
    the day Stage 7 happens to run would record the wrong instrument.
    """
    import json

    path = run_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("run_model")
    except (OSError, ValueError):
        return None


def render_persist(result: PersistResult) -> str:
    """Operator-facing rendering. Loadability first, because it is the answer."""
    verdict = "LOADABLE" if result.loadable else "NOT LOADABLE"
    lines = [
        f"Stage 7 — run {result.run_id}",
        f"  {verdict}",
        "",
        f"  version            : v{result.version}",
        f"  activities         : {result.activities}",
        f"  sources            : {result.sources}",
    ]
    if result.summary.get("skipped"):
        lines.append(f"  note               : {result.summary['skipped']}")
    outputs = result.summary.get("outputs")
    if isinstance(outputs, dict):
        for key in ("institution_summary", "activities", "activity_sources"):
            block = outputs.get(key)
            if isinstance(block, dict) and "n_rows" in block:
                lines.append(f"  {key:<19}: {block['n_rows']:,} rows")
    # Never silent: printed whether it is zero or not, like the loader's
    # quarantine count, because zero-because-checked and zero-because-unasked
    # are different facts.
    failures = result.n_load_failures
    lines.append(
        f"  load failures      : {failures if failures is not None else 'not asked'}"
    )
    return "\n".join(lines)


__all__ = [
    "LOADER_VERSION",
    "PersistError",
    "PersistResult",
    "persist_run",
    "render_persist",
]
