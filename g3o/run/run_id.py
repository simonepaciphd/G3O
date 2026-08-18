"""Minted run identity — the date key (Run API spec v0.1 §2).

``r<YYYYMMDD>T<HHMMSS>Z-<4hex>``, UTC always — e.g. ``r20260809T143012Z-a3f1``.

The timestamp is the semantic payload: ex-post wave classification (§5.4) reads a
run's start time to decide which wave window it falls in, so the id is
human-readable *and* orderable by the thing that matters. The 4-hex suffix is
collision armor, not identity — two launches inside the same UTC second would
otherwise mint the same id.

Two rules keep this honest and are pinned by tests:

* **the manifest is authoritative, not the id.** ``run_started_at`` here parses
  the id string as a convenience; §5.5 classifies from the manifest's
  ``run_started_at``. That ordering is what lets legacy ids (``20260509-presweep``)
  and replication runs classify at all — they have no parseable timestamp, so a
  classifier that read the id string would silently exclude them.
* **a non-conforming id raises.** Returning a fallback (``now``, epoch, ``None``)
  would let a legacy id be classified into whatever window happened to be open.
  Callers that must not raise ask :func:`is_minted_run_id` first.

Kept in its own module, free of pipeline imports, so it is unit-testable in
isolation and cheap for a classifier to import; :mod:`g3o.run.api` re-exports it
as part of the public surface §1 declares.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

#: Human-readable statement of the format, for error messages and docs.
RUN_ID_FORMAT = "r<YYYYMMDD>T<HHMMSS>Z-<4hex>"

#: Bytes of randomness in the suffix — ``secrets.token_hex(2)`` -> 4 hex chars.
SUFFIX_BYTES = 2

_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"

# Anchored, and the suffix is lowercase hex only: an id is either exactly this
# shape or it is not a minted id at all. Deliberately strict — a tolerant
# pattern here would make `run_started_at` accept something whose timestamp it
# then has to guess at.
_RUN_ID_RE = re.compile(r"^r(\d{8}T\d{6}Z)-[0-9a-f]{4}$")


def mint_run_id(now: datetime | None = None) -> str:
    """Mint a fresh run id for ``now`` (default: the current UTC moment).

    Pure apart from the two entropy sources it is *for* — the clock and
    ``secrets`` — both of which the caller can pin: pass ``now`` to fix the
    timestamp, and patch ``secrets.token_hex`` in this module to fix the suffix.
    That is what makes the collision path in :func:`g3o.run.api.launch` testable
    without waiting for a real collision.

    A naive ``now`` raises rather than being assumed UTC: the id's timestamp is
    what wave classification consumes, so silently stamping a local-time moment
    as ``Z`` would misfile a run into a neighbouring window — wrong data, no
    error, and invisible afterwards. Aware datetimes in any zone are converted.
    """
    moment = datetime.now(timezone.utc) if now is None else now
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        raise ValueError(
            f"mint_run_id needs an aware datetime (got naive {moment!r}). The "
            "id's timestamp is what wave classification reads, so a local-time "
            "moment stamped 'Z' would misfile the run silently. Pass "
            "datetime.now(timezone.utc) or an aware datetime in any zone."
        )
    stamp = moment.astimezone(timezone.utc).strftime(_STAMP_FORMAT)
    return f"r{stamp}-{secrets.token_hex(SUFFIX_BYTES)}"


def run_started_at(run_id: str) -> datetime:
    """The UTC moment encoded in a **minted** run id. Raises for anything else.

    Round-trips :func:`mint_run_id` exactly. Raises :class:`ValueError` for a
    legacy or hand-written id (``20260509-presweep``, ``smoke-1``) and for a
    well-shaped id whose stamp is not a real moment (``r20261301T…``) — the
    calendar check comes free from ``strptime`` and is the same discipline the
    contract's date validators apply to provenance blocks.
    """
    match = _RUN_ID_RE.match(run_id or "")
    if match is None:
        raise ValueError(
            f"run id {run_id!r} is not in minted form {RUN_ID_FORMAT}; its start "
            "time is only recoverable from the run manifest (spec §2, §5.5)."
        )
    try:
        parsed = datetime.strptime(match.group(1), _STAMP_FORMAT)
    except ValueError as exc:
        raise ValueError(
            f"run id {run_id!r} has minted shape but its timestamp is not a real "
            f"UTC moment: {exc}"
        ) from exc
    return parsed.replace(tzinfo=timezone.utc)


def is_minted_run_id(run_id: str) -> bool:
    """True iff :func:`run_started_at` would succeed — for callers that can't raise.

    The classification path (§5.5) and any reader that mixes legacy and minted
    ids uses this instead of catching ``ValueError`` around a parse.
    """
    try:
        run_started_at(run_id)
    except ValueError:
        return False
    return True


__all__ = [
    "RUN_ID_FORMAT",
    "SUFFIX_BYTES",
    "is_minted_run_id",
    "mint_run_id",
    "run_started_at",
]
