"""Inspection history — when each institution was last looked at.

The database is the only place that knows what has already been inspected, so
this is the one input the master CSV cannot supply. It is read once, snapshotted,
and thereafter treated as data: a frame built from a snapshot file reproduces
byte-for-byte, a frame built from a live query does not, because the table moves.

**There is no ``run_date`` column on ``g3o.sweeps``.** The columns are
``sweep_uid, run_id, frame_id, institution_uid, sweep_uid_source, loaded_at,
search_verdict, outcome_status``. Two timestamps are therefore available and they
mean different things:

* ``run_id`` carries the moment the sweep *ran* (``r20260824T215623Z-bb4e`` ->
  2026-08-24T21:56:23Z). This is what "distance from last inspection" means.
* ``loaded_at`` is when the loader wrote the row. It misdates every back-load —
  ``r20260824T215623Z-bb4e`` ran on the 24th and loaded on the 26th, and
  ``r20260818T210912Z-33ae`` loaded a day after it ran.

So the run id wins whenever it parses (:func:`g3o.run.run_id.run_started_at`), and
``loaded_at`` is the fallback for legacy ids only. A row with neither is dropped
from the snapshot with a count, never silently dated to now: dating an unknown
inspection to the present would make the institution look freshly inspected and
push it to the back of the tier-2 queue forever.
"""

from __future__ import annotations

import csv
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g3o.run.run_id import is_minted_run_id, run_started_at

logger = logging.getLogger(__name__)

#: Column order of a snapshot CSV. Written by :func:`write_snapshot_csv`, and the
#: only shape :func:`read_snapshot_csv` accepts.
SNAPSHOT_FIELDS: tuple[str, ...] = (
    "institution_uid",
    "last_run_id",
    "last_loaded_at",
    "last_inspected_at",
    "timestamp_source",
    "n_sweeps",
)

#: The query behind a snapshot. Read-only, one row per sweep ever recorded.
SNAPSHOT_QUERY = """
    select institution_uid, run_id, loaded_at
    from g3o.sweeps
    order by institution_uid, run_id
"""

#: Prefix of the self-describing comment line above a snapshot CSV header.
SNAPSHOT_HEADER_KEY = "snapshot_at"


@dataclass(frozen=True)
class InspectionRecord:
    """One institution's most recent inspection."""

    institution_uid: str
    last_run_id: str
    last_loaded_at: datetime | None
    last_inspected_at: datetime
    timestamp_source: str  # "run_id" | "loaded_at"
    n_sweeps: int


@dataclass(frozen=True)
class InspectionSnapshot:
    """Every institution ever inspected, as of :attr:`snapshot_at`.

    ``snapshot_at`` is carried rather than derived because it is the reference
    point the recency weights are measured from. A snapshot read yesterday and
    used today must weight against yesterday, or the weights change while the
    recorded inputs did not.
    """

    snapshot_at: datetime
    source: str
    records: dict[str, InspectionRecord] = field(default_factory=dict)
    n_undated: int = 0

    def __contains__(self, institution_uid: object) -> bool:
        return institution_uid in self.records

    def __len__(self) -> int:
        return len(self.records)

    def age_seconds(self, institution_uid: str) -> float | None:
        """Seconds between the last inspection of ``institution_uid`` and the snapshot."""
        record = self.records.get(institution_uid)
        if record is None:
            return None
        return (self.snapshot_at - record.last_inspected_at).total_seconds()


def as_utc(moment: datetime) -> datetime:
    """Coerce ``moment`` to an aware UTC datetime; naive input is read as UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def last_inspected_at(run_id: str, loaded_at: datetime | None) -> tuple[datetime | None, str]:
    """Resolve one sweep's inspection moment, preferring the run id's stamp.

    Returns ``(moment, source)``; ``(None, "none")`` when the id does not parse
    and there is no ``loaded_at`` to fall back on.
    """
    if is_minted_run_id(run_id or ""):
        return run_started_at(run_id), "run_id"
    if loaded_at is not None:
        return as_utc(loaded_at), "loaded_at"
    return None, "none"


def snapshot_from_rows(
    rows: Iterable[tuple[str, str, Any]],
    *,
    snapshot_at: datetime,
    source: str,
) -> InspectionSnapshot:
    """Fold ``(institution_uid, run_id, loaded_at)`` rows into a snapshot.

    Keeps the **latest** inspection per institution, compared on the resolved
    moment rather than on the order the database happened to return rows in.
    """
    best: dict[str, InspectionRecord] = {}
    undated = 0
    for institution_uid, run_id, loaded_at in rows:
        uid = (institution_uid or "").strip()
        if not uid:
            continue
        loaded = as_utc(loaded_at) if isinstance(loaded_at, datetime) else None
        moment, ts_source = last_inspected_at(run_id or "", loaded)
        if moment is None:
            undated += 1
            continue
        prior = best.get(uid)
        newer = prior is None or moment > prior.last_inspected_at
        best[uid] = InspectionRecord(
            institution_uid=uid,
            last_run_id=(run_id or "") if newer else prior.last_run_id,
            last_loaded_at=loaded if newer else prior.last_loaded_at,
            last_inspected_at=moment if newer else prior.last_inspected_at,
            timestamp_source=ts_source if newer else prior.timestamp_source,
            n_sweeps=1 if prior is None else prior.n_sweeps + 1,
        )
    if undated:
        logger.warning(
            "inspection snapshot: %d sweep rows carry neither a parseable run id "
            "nor a loaded_at and were dropped rather than dated to now.",
            undated,
        )
    return InspectionSnapshot(
        snapshot_at=as_utc(snapshot_at), source=source, records=best, n_undated=undated
    )


def snapshot_from_dsn(dsn: str, *, snapshot_at: datetime | None = None) -> InspectionSnapshot:
    """Read ``g3o.sweeps`` and fold it into a snapshot. Read-only, one SELECT."""
    import psycopg  # noqa: PLC0415 - optional, droplet-only

    moment = as_utc(snapshot_at or datetime.now(timezone.utc))
    with psycopg.connect(dsn, connect_timeout=30) as conn, conn.cursor() as cur:
        cur.execute(SNAPSHOT_QUERY)
        rows = cur.fetchall()
    return snapshot_from_rows(rows, snapshot_at=moment, source="g3o.sweeps")


def read_sweeps_csv(path: Path, *, snapshot_at: datetime, source: str) -> InspectionSnapshot:
    """Fold a raw dump of :data:`SNAPSHOT_QUERY` into a snapshot.

    The database lives on the run droplet and the frame is built wherever the
    operator is, so the SELECT and the folding do not always happen on the same
    machine. This is the seam: the remote half is a raw three-column dump with
    no logic in it, and every decision — run-id-beats-``loaded_at``, latest wins,
    undated rows dropped — happens here, in the code the frame's provenance
    names. ``snapshot_at`` is the moment the dump was taken, and must be passed
    because the file cannot know it.
    """
    with open(path, encoding="utf-8", newline="") as f:
        rows = [
            (
                (row.get("institution_uid") or "").strip(),
                (row.get("run_id") or "").strip(),
                datetime.fromisoformat(row["loaded_at"]) if (row.get("loaded_at") or "").strip() else None,
            )
            for row in csv.DictReader(f)
        ]
    return snapshot_from_rows(rows, snapshot_at=snapshot_at, source=source)


def write_snapshot_csv(snapshot: InspectionSnapshot, out_csv: Path) -> int:
    """Write ``snapshot`` to ``out_csv`` sorted by uid; return the row count.

    The snapshot moment rides in a ``# snapshot_at=`` comment line above the
    header so the file is self-describing — a frame built from it records the
    same moment the weights were computed against.
    """
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write(
            f"# {SNAPSHOT_HEADER_KEY}={snapshot.snapshot_at.isoformat()}"
            f" source={snapshot.source}\n"
        )
        writer = csv.DictWriter(f, fieldnames=list(SNAPSHOT_FIELDS), lineterminator="\n")
        writer.writeheader()
        for uid in sorted(snapshot.records):
            r = snapshot.records[uid]
            writer.writerow(
                {
                    "institution_uid": r.institution_uid,
                    "last_run_id": r.last_run_id,
                    "last_loaded_at": r.last_loaded_at.isoformat() if r.last_loaded_at else "",
                    "last_inspected_at": r.last_inspected_at.isoformat(),
                    "timestamp_source": r.timestamp_source,
                    "n_sweeps": r.n_sweeps,
                }
            )
    return len(snapshot.records)


def _snapshot_lines(path: Path) -> Iterator[str]:
    with open(path, encoding="utf-8", newline="") as f:
        yield from f


def read_snapshot_csv(path: Path) -> InspectionSnapshot:
    """Read a snapshot written by :func:`write_snapshot_csv`.

    Raises :class:`ValueError` when the ``# snapshot_at=`` header is missing:
    without it the weights would be measured from an unknown reference point,
    which is exactly the un-reproducibility this module exists to remove.
    """
    snapshot_at: datetime | None = None
    source = f"snapshot:{path.name}"
    body: list[str] = []
    for line in _snapshot_lines(path):
        if line.startswith("#"):
            for token in line.lstrip("#").strip().split():
                key, _, value = token.partition("=")
                if key == SNAPSHOT_HEADER_KEY and value:
                    snapshot_at = as_utc(datetime.fromisoformat(value))
                elif key == "source" and value:
                    source = value
            continue
        body.append(line)
    if snapshot_at is None:
        raise ValueError(
            f"{path} has no '# {SNAPSHOT_HEADER_KEY}=' header line. The recency "
            "weights are measured from that moment, so a snapshot without one "
            "cannot produce a reproducible frame. Re-export it with "
            "`g3o frame snapshot`."
        )
    records: dict[str, InspectionRecord] = {}
    for row in csv.DictReader(body):
        uid = (row.get("institution_uid") or "").strip()
        if not uid:
            continue
        stamp = (row.get("last_inspected_at") or "").strip()
        if not stamp:
            continue
        loaded_raw = (row.get("last_loaded_at") or "").strip()
        records[uid] = InspectionRecord(
            institution_uid=uid,
            last_run_id=(row.get("last_run_id") or "").strip(),
            last_loaded_at=as_utc(datetime.fromisoformat(loaded_raw)) if loaded_raw else None,
            last_inspected_at=as_utc(datetime.fromisoformat(stamp)),
            timestamp_source=(row.get("timestamp_source") or "").strip() or "unknown",
            n_sweeps=int(row.get("n_sweeps") or 1),
        )
    return InspectionSnapshot(snapshot_at=snapshot_at, source=source, records=records)


def empty_snapshot(*, snapshot_at: datetime | None = None) -> InspectionSnapshot:
    """A snapshot asserting nothing has ever been inspected.

    Only reachable behind an explicit ``--assume-none-inspected`` flag. The
    default is to require an inspection source, because "no history supplied"
    and "nothing has been inspected" produce the same frame and mean opposite
    things.
    """
    return InspectionSnapshot(
        snapshot_at=as_utc(snapshot_at or datetime.now(timezone.utc)),
        source="assumed-none",
    )


__all__ = [
    "SNAPSHOT_FIELDS",
    "SNAPSHOT_HEADER_KEY",
    "SNAPSHOT_QUERY",
    "InspectionRecord",
    "InspectionSnapshot",
    "as_utc",
    "empty_snapshot",
    "last_inspected_at",
    "read_snapshot_csv",
    "read_sweeps_csv",
    "snapshot_from_dsn",
    "snapshot_from_rows",
    "write_snapshot_csv",
]
