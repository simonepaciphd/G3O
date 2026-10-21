"""Harvest leg — rebuild the official-site overlay from every completed run.

The chain's only derived leg, and the only one that is safe to repeat. Every other
step in :mod:`g3o.run.orchestrate.e2e` either spends something or publishes something;
this one reads finished run directories and writes a projection of them.

Why it sits inside the chain rather than in a cron job: the overlay is worth exactly as
much as it is current, and the moment it is knowably stale is the moment a run finishes.
Running it here means the next round spends this round's discoveries without anyone
remembering to rebuild anything.

**Rebuilt, never appended.** :func:`g3o.report.site_overlay.build_overlay` is
deterministic over its inputs, so the second harvest over an unchanged corpus produces
the same bytes and this leg says so (``changed: false``) rather than writing a new
version of an identical file. That is what makes "after every run" cheap and safe: there
is no incremental state to corrupt and no ordering to get wrong.

**Advisory by construction.** The overlay feeds a *future* run; nothing in the current
one reads it. A failure here must never make a published run read as stopped, so the leg
reports green with the failure in its message unless the caller asked otherwise.

**Then the master-sites refresh** (:func:`refresh_master_sites`, 2026-10-21 ruling
D5 a): the rebuilt overlay joined onto the master the run sampled from, written under
``_site_overlay/master_sites/``, latest copy only. Advisory on the same terms, and it
never writes a fold proposal — that is the PI-gated wave-close step.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.report.site_overlay import (
    PRECEDENCE_MODES,
    build_overlay,
    iter_run_dirs,
    write_overlay,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_OVERLAY_DIRNAME",
    "MASTER_SITES_DIRNAME",
    "OVERLAY_FILENAME",
    "HarvestResult",
    "MasterSitesLegResult",
    "harvest_official_sites",
    "overlay_dir_for",
    "refresh_master_sites",
]

#: Underscore-prefixed so :func:`g3o.report.site_overlay.iter_run_dirs` skips it when
#: it scans ``runs_dir`` — the overlay must never be harvested as if it were a run.
DEFAULT_OVERLAY_DIRNAME = "_site_overlay"

#: Stable name, deliberately undated: this is the path ``presweep
#: --official-sites`` is pointed at, and a name that moved every run would make that
#: flag a thing an operator has to look up before every launch. History lives in
#: ``history.jsonl`` beside it.
OVERLAY_FILENAME = "official_sites.csv"


def overlay_dir_for(runs_dir: Path, overlay_dir: Path | None = None) -> Path:
    return overlay_dir or (runs_dir / DEFAULT_OVERLAY_DIRNAME)


@dataclass
class HarvestResult:
    """What the harvest saw and whether it changed anything."""

    overlay_path: str = ""
    sha256: str = ""
    previous_sha256: str = ""
    changed: bool = False
    runs_scanned: int = 0
    overlay_rows: int = 0
    stats: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def green(self) -> bool:
        """Derived, never set. A separate flag would let a failure report success —
        it did, in review: ``HarvestResult(error=...)`` left ``green`` at its default
        and ``--require-harvest`` sailed straight past the gate it was asked to be."""
        return not self.error

    @property
    def message(self) -> str:
        if self.error:
            return f"overlay NOT rebuilt: {self.error}"
        if not self.changed:
            return (
                f"overlay unchanged at {self.overlay_rows} institutions "
                f"({self.runs_scanned} runs, sha {self.sha256[:12]})"
            )
        return (
            f"overlay rebuilt: {self.overlay_rows} institutions from "
            f"{self.runs_scanned} runs (sha {self.sha256[:12]})"
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "overlay_path": self.overlay_path,
            "sha256": self.sha256,
            "changed": self.changed,
            "runs_scanned": self.runs_scanned,
            "overlay_rows": self.overlay_rows,
        }
        if self.previous_sha256:
            out["previous_sha256"] = self.previous_sha256
        for key in (
            "rows_sharing_site_host",
            "rows_sharing_domain",
            "confidence_counts",
            "records_without_uid",
        ):
            if key in self.stats:
                out[key] = self.stats[key]
        if self.error:
            out["error"] = self.error
        return out


def harvest_official_sites(
    runs_dir: Path,
    *,
    overlay_dir: Path | None = None,
    precedence: str = PRECEDENCE_MODES[0],
) -> HarvestResult:
    """Rebuild the overlay under ``overlay_dir`` from every run in ``runs_dir``.

    Never raises for a harvest that could not run: the caller is a chain whose earlier
    legs may already have published, and an exception here would be indistinguishable
    from a load that failed. The failure lands on the result instead.
    """
    result = HarvestResult()
    try:
        target_dir = overlay_dir_for(runs_dir, overlay_dir)
        overlay_path = target_dir / OVERLAY_FILENAME
        result.overlay_path = str(overlay_path)
        result.previous_sha256 = _previous_sha(target_dir)

        run_dirs = list(iter_run_dirs(runs_dir))
        result.runs_scanned = len(run_dirs)
        if not run_dirs:
            result.error = f"no completed run directories under {runs_dir}"
            return result

        rows, stats = build_overlay(run_dirs, precedence=precedence)
        result.stats = stats
        result.overlay_rows = len(rows)
        result.sha256 = write_overlay(rows, overlay_path)
        result.changed = result.sha256 != result.previous_sha256

        manifest = {
            "overlay_path": str(overlay_path),
            "sha256": result.sha256,
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runs_scanned": result.runs_scanned,
            "stats": stats,
        }
        (target_dir / "official_sites.manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # One line per harvest, so "when did this institution's site first appear"
        # is answerable without keeping every version of a 4 MB CSV.
        with (target_dir / "history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "built_at": manifest["built_at"],
                        "sha256": result.sha256,
                        "changed": result.changed,
                        "runs_scanned": result.runs_scanned,
                        "overlay_rows": result.overlay_rows,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        logger.info("harvest: %s", result.message)
    except Exception as exc:  # noqa: BLE001 — see the docstring: never raise here
        result.error = f"{type(exc).__name__}: {exc}"
        logger.warning("harvest failed: %s", result.error)
    return result


def _previous_sha(target_dir: Path) -> str:
    manifest = target_dir / "official_sites.manifest.json"
    if not manifest.is_file():
        return ""
    try:
        return str(json.loads(manifest.read_text(encoding="utf-8")).get("sha256") or "")
    except (OSError, json.JSONDecodeError):
        return ""


# ----------------------------------------------------------------------------------
# master-sites — the overlay against the master, refreshed after every harvest
# ----------------------------------------------------------------------------------

#: Under the overlay dir, beside ``official_sites.csv``. Latest copy only.
MASTER_SITES_DIRNAME = "master_sites"


@dataclass
class MasterSitesLegResult:
    """What the master-sites refresh did, or why it did not run."""

    out_dir: str = ""
    master_csv: str = ""
    skipped: str = ""
    report: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def green(self) -> bool:
        """A skip is green: no master configured is a state, not a failure."""
        return not self.error

    @property
    def message(self) -> str:
        if self.error:
            return f"master-sites NOT refreshed: {self.error}"
        if self.skipped:
            return f"skipped: {self.skipped}"
        vs = self.report.get("eligible_vs_master") or {}
        return (
            f"master-sites refreshed: {self.report.get('status_counts', {}).get('eligible', 0)}"
            f" eligible picks against {self.report.get('master_rows', 0)} master rows "
            f"(master empty {vs.get('master_empty', 0)}, same host "
            f"{vs.get('same_host', 0)}, different host {vs.get('different_host', 0)})"
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"out_dir": self.out_dir, "master_csv": self.master_csv}
        for key in (
            "master_sha256",
            "overlay_sha256",
            "out_sha256",
            "master_rows",
            "status_counts",
            "eligible_vs_master",
        ):
            if key in self.report:
                out[key] = self.report[key]
        if self.skipped:
            out["skipped"] = self.skipped
        if self.error:
            out["error"] = self.error
        return out


def refresh_master_sites(
    runs_dir: Path,
    *,
    master_csv: Path | None,
    overlay_dir: Path | None = None,
) -> MasterSitesLegResult:
    """Join the freshly harvested overlay onto ``master_csv``, overwriting the last copy.

    Writes ``<overlay-dir>/master_sites/{master_with_official_sites.csv, report.json,
    conflicts.csv}`` via :func:`g3o.report.master_sites.build_master_sites`. **Never a
    fold proposal**: proposing a fold is the wave-close step, run by hand, and an
    approval binds to a proposal's sha — a chain that rewrote proposals after every run
    would be generating things for the PI to sign that nobody asked for.

    Advisory in exactly the harvest's sense, and for the same reason: nothing in this
    run reads it. No master (none passed, none in the run's manifest, or the path is
    not on this machine) is a clean skip; anything else that goes wrong lands on the
    result, never as an exception.
    """
    result = MasterSitesLegResult()
    try:
        target_dir = overlay_dir_for(runs_dir, overlay_dir)
        result.out_dir = str(target_dir / MASTER_SITES_DIRNAME)
        if master_csv is None:
            result.skipped = (
                "no master CSV (none passed and the run's manifest records none)"
            )
            return result
        result.master_csv = str(master_csv)
        if not Path(master_csv).is_file():
            result.skipped = f"master CSV not found on this machine: {master_csv}"
            return result
        overlay_path = target_dir / OVERLAY_FILENAME
        if not overlay_path.is_file():
            result.skipped = f"no overlay at {overlay_path}"
            return result

        from g3o.report.master_sites import build_master_sites

        built = build_master_sites(
            Path(master_csv), overlay_path, target_dir / MASTER_SITES_DIRNAME
        )
        result.report = built.report
        logger.info("master-sites: %s", result.message)
    except Exception as exc:  # noqa: BLE001 — advisory, like the harvest: never raise
        result.error = f"{type(exc).__name__}: {exc}"
        logger.warning("master-sites failed: %s", result.error)
    return result
