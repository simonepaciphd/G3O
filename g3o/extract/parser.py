"""Stage 5 result parser.

Takes a single ``BatchResult`` for one (institution × page) extraction job and
returns a validated ``BatchResponse``. Validation errors from
``g3o.common.contract`` are the line of defense — they are NOT caught here.

Per Q1 (2026-05-09, decision (a)): the scrape access date is injected into
the user message and the LLM is instructed to copy it verbatim into every
row's ``source_access_date``. This parser enforces the contract: if any row
disagrees with the supplied ``scrape_access_date``, the parser raises (no
silent overwrite). A parser-side failure here surfaces an LLM contract drift
that would otherwise corrupt provenance.

Salvage: before validation, three independent repairs run over the payload
(see ``salvage.py`` for the reasoning and the boundaries of each).

- ``salvage_group_d_na`` repairs ``confirms_activity`` rows whose Group-D fields
  carry the illegal literal ``_NA_``, substituting the contract's prescribed
  defaults so a real positive finding is not dropped over a schema imperfection.
- ``salvage_uncertainty_flags`` rewrites a malformed ``uncertainty_flags`` to
  the contract's ``none`` (or to a cleaned flag list) on any row, whatever its
  ``genai_evidence``. It declines any value holding an unrecognised token.
- ``salvage_negative_row_group_d`` blanks stray Group-D values on a
  negative-evidence row to ``_NA_``, unless an existence-asserting field is among
  them — in which case the row contradicts itself and is left to fail.

When a ``salvage_sink`` list is supplied, the parser appends one event per
affected row — ``GroupDSalvage``, ``UncertaintyFlagsSalvage`` or
``NegativeRowSalvage``, so callers must discriminate on type — letting the caller
write attrition telemetry. The sink is
populated on the failure path too, since salvage runs before validation.
"""

from __future__ import annotations

import json

from g3o.common.batch_client import BatchResult
from g3o.common.contract import BatchResponse
from g3o.extract.salvage import (
    GroupDSalvage,
    NegativeRowSalvage,
    UncertaintyFlagsSalvage,
    salvage_group_d_na,
    salvage_negative_row_group_d,
    salvage_uncertainty_flags,
)

SalvageEvent = GroupDSalvage | UncertaintyFlagsSalvage | NegativeRowSalvage


def parse_extract_result(
    result: BatchResult,
    *,
    scrape_access_date: str,
    salvage_sink: list[SalvageEvent] | None = None,
) -> BatchResponse:
    """Parse a Stage 5 ``BatchResult`` into a validated ``BatchResponse``.

    Args:
        salvage_sink: if provided, one salvage event per affected row is appended
            to it: a ``GroupDSalvage`` for every ``confirms_activity`` row with
            Group-D ``_NA_`` (both repaired and unsalvageable), and an
            ``UncertaintyFlagsSalvage`` for every row whose ``uncertainty_flags``
            was repaired, and a ``NegativeRowSalvage`` for every negative-evidence
            row carrying stray Group-D values. Populated before validation, so it is available to the
            caller even when this call raises.

    Raises:
        RuntimeError: if the underlying API call failed or returned no content.
        pydantic.ValidationError: on schema / cross-row validation failure.
        ValueError: if the LLM did not copy ``scrape_access_date`` verbatim
            into every row's ``source_access_date`` (Q1=a contract).
    """
    if not result.success:
        raise RuntimeError(
            f"Stage 5 batch result {result.custom_id!r} failed: {result.error}"
        )
    content = result.parsed_content
    if not content:
        raise RuntimeError(
            f"Stage 5 batch result {result.custom_id!r}: empty assistant content"
        )
    payload = json.loads(content)
    events: list[SalvageEvent] = [*salvage_group_d_na(payload)]
    events.extend(salvage_negative_row_group_d(payload))
    if isinstance(payload, dict):
        events.extend(salvage_uncertainty_flags(payload.get("data")))
    if salvage_sink is not None:
        salvage_sink.extend(events)
    response = BatchResponse.model_validate(payload)

    # Q1=a: trust-the-input plus a hard verification that the LLM honored the
    # contract. Any divergence is treated as a parse failure rather than
    # silently overwritten — the researcher can revisit Q1 if drift is
    # observed in practice.
    bad_rows = [
        r for r in response.data if r.source_access_date != scrape_access_date
    ]
    if bad_rows:
        offending_urls = sorted({r.source_url for r in bad_rows})
        offending_dates = sorted({r.source_access_date for r in bad_rows})
        raise ValueError(
            f"Stage 5 result {result.custom_id!r}: "
            f"{len(bad_rows)} row(s) emitted source_access_date "
            f"{offending_dates} but scrape supplied {scrape_access_date!r}; "
            f"affected source_url(s): {offending_urls}"
        )

    return response


__all__ = [
    "parse_extract_result",
    "SalvageEvent",
    "GroupDSalvage",
    "UncertaintyFlagsSalvage",
    "NegativeRowSalvage",
    "salvage_group_d_na",
    "salvage_uncertainty_flags",
    "salvage_negative_row_group_d",
]
